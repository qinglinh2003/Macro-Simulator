$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildPreset = if ($env:MACRO_SIM_BUILD_PRESET) {
    $env:MACRO_SIM_BUILD_PRESET
} else {
    "m11-release"
}
$BuildRoot = if ($env:MACRO_SIM_BUILD_ROOT) {
    $env:MACRO_SIM_BUILD_ROOT
} else {
    Join-Path $RepositoryRoot "build/native/$BuildPreset"
}
$NativeRoot = Join-Path $BuildRoot "native"
$OutputRoot = if ($env:MACRO_SIM_PACKAGE_ROOT) {
    $env:MACRO_SIM_PACKAGE_ROOT
} else {
    Join-Path $RepositoryRoot "build/package/windows"
}
$OutputBundle = Join-Path $OutputRoot "Macro Command"
$OutputArchive = Join-Path $OutputRoot "MacroCommand-windows-x86_64.zip"
$OutputChecksum = "$OutputArchive.sha256"
$StagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "macro-command-windows." + [guid]::NewGuid().ToString("N")
)
$StagingBundle = Join-Path $StagingRoot "Macro Command"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Program,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]] $Arguments
    )
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program failed with exit code $LASTEXITCODE"
    }
}

try {
    $Godot = if ($env:GODOT) {
        $env:GODOT
    } else {
        $Command = Get-Command godot -ErrorAction SilentlyContinue
        if ($null -eq $Command) {
            $Command = Get-Command godot4 -ErrorAction SilentlyContinue
        }
        if ($null -eq $Command) {
            throw "Godot 4 is required to export the desktop application."
        }
        $Command.Source
    }
    # The plain Windows Godot binary targets the GUI subsystem. PowerShell does
    # not wait for such a process, so the export returns immediately with a
    # stale exit code, prints nothing, and never writes the executable. The
    # console variant shipped alongside it is a console subsystem binary and
    # behaves correctly when driven from a script.
    if ($Godot -match '(?i)\.exe$' -and $Godot -notmatch '(?i)\.console\.exe$') {
        $ConsoleGodot = $Godot -replace '(?i)\.exe$', '.console.exe'
        if (Test-Path -PathType Leaf $ConsoleGodot) {
            $Godot = $ConsoleGodot
        } else {
            Write-Host "Console Godot binary is absent next to $Godot"
        }
    }
    Write-Host "Using Godot executable: $Godot"
    if ((Test-Path $OutputBundle) -or
        (Test-Path $OutputArchive) -or
        (Test-Path $OutputChecksum)) {
        throw "The package output already exists: $OutputRoot"
    }

    $ConfigureArguments = @("--preset", $BuildPreset)
    $VirtualPython = Join-Path $RepositoryRoot ".venv/Scripts/python.exe"
    if (Test-Path $VirtualPython) {
        $ConfigureArguments += "-DPython_EXECUTABLE=$VirtualPython"
    }
    Invoke-Checked cmake @ConfigureArguments
    Invoke-Checked cmake --build --preset $BuildPreset --parallel 8 `
        --target macro_sim_server macro_sim_launcher

    New-Item -ItemType Directory -Force -Path $StagingBundle | Out-Null
    Invoke-Checked $Godot --headless `
        --path (Join-Path $RepositoryRoot "desktop/godot") --import
    Invoke-Checked $Godot --headless `
        --path (Join-Path $RepositoryRoot "desktop/godot") `
        --export-release "Windows x86_64" `
        (Join-Path $StagingBundle "Macro Command.game.exe")

    $GameBinary = Join-Path $StagingBundle "Macro Command.game.exe"
    $ServerBinary = Join-Path $NativeRoot "macro_sim_server.exe"
    $LauncherBinary = Join-Path $NativeRoot "macro_sim_launcher.exe"
    foreach ($Required in @($GameBinary, $ServerBinary, $LauncherBinary)) {
        if (-not (Test-Path -PathType Leaf $Required)) {
            Write-Host "Staging bundle contents:"
            Get-ChildItem -Recurse -Force $StagingBundle |
                ForEach-Object { Write-Host "  $($_.FullName)" }
            Write-Host "Native build output:"
            Get-ChildItem -Force $NativeRoot -Filter *.exe |
                ForEach-Object { Write-Host "  $($_.FullName)" }
            throw "The exported application or native runtime is incomplete: $Required"
        }
    }

    $NativeResourceRoot = Join-Path $StagingBundle "native"
    $ArtifactRoot = Join-Path $NativeResourceRoot "artifacts"
    $LicenseRoot = Join-Path $StagingBundle "licenses"
    New-Item -ItemType Directory -Force -Path $ArtifactRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $LicenseRoot | Out-Null
    Copy-Item $LauncherBinary (Join-Path $StagingBundle "Macro Command.exe")
    Copy-Item $ServerBinary (Join-Path $NativeResourceRoot "macro_sim_server.exe")
    Copy-Item `
        (Join-Path $RepositoryRoot "macro_sim/rl/artifacts/fiscal_stabilization_v1.msrl") `
        (Join-Path $ArtifactRoot "fiscal_stabilization_v1.msrl")
    Copy-Item (Join-Path $RepositoryRoot "native/vendor/flatbuffers/LICENSE") `
        (Join-Path $LicenseRoot "flatbuffers-LICENSE")
    Copy-Item (Join-Path $RepositoryRoot "native/vendor/nlohmann-json/LICENSE.MIT") `
        (Join-Path $LicenseRoot "nlohmann-json-LICENSE")
    Copy-Item (Join-Path $RepositoryRoot "native/vendor/picosha2/LICENSE") `
        (Join-Path $LicenseRoot "picosha2-LICENSE")

    $Signed = $false
    if ($env:MACRO_SIM_SIGN_CERT_SHA1) {
        $SignTool = (Get-Command signtool -ErrorAction Stop).Source
        foreach ($Binary in @(
            (Join-Path $StagingBundle "Macro Command.exe"),
            $GameBinary,
            (Join-Path $NativeResourceRoot "macro_sim_server.exe")
        )) {
            Invoke-Checked $SignTool sign /fd SHA256 `
                /sha1 $env:MACRO_SIM_SIGN_CERT_SHA1 `
                /tr "http://timestamp.digicert.com" /td SHA256 $Binary
        }
        $Signed = $true
    }

    $Revision = (& git -C $RepositoryRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to resolve the source revision."
    }
    $Sbom = [ordered]@{
        spdxVersion = "SPDX-2.3"
        dataLicense = "CC0-1.0"
        SPDXID = "SPDXRef-DOCUMENT"
        name = "Macro Command Windows x86_64"
        documentNamespace = "https://macrocommand.local/spdx/$Revision"
        creationInfo = [ordered]@{
            created = "1970-01-01T00:00:00Z"
            creators = @("Tool: macro-sim-package-m11")
        }
        packages = @(
            [ordered]@{
                name = "Macro Command"
                SPDXID = "SPDXRef-MacroCommand"
                versionInfo = $Revision
                downloadLocation = "NOASSERTION"
                filesAnalyzed = $false
                licenseConcluded = "NOASSERTION"
                licenseDeclared = "NOASSERTION"
            },
            [ordered]@{
                name = "Godot Engine"
                SPDXID = "SPDXRef-Godot"
                versionInfo = "4.7.1"
                downloadLocation = "https://godotengine.org/"
                filesAnalyzed = $false
                licenseConcluded = "MIT"
                licenseDeclared = "MIT"
            },
            [ordered]@{
                name = "FlatBuffers"
                SPDXID = "SPDXRef-FlatBuffers"
                downloadLocation = "https://github.com/google/flatbuffers"
                filesAnalyzed = $false
                licenseConcluded = "Apache-2.0"
                licenseDeclared = "Apache-2.0"
            },
            [ordered]@{
                name = "JSON for Modern C++"
                SPDXID = "SPDXRef-NlohmannJson"
                downloadLocation = "https://github.com/nlohmann/json"
                filesAnalyzed = $false
                licenseConcluded = "MIT"
                licenseDeclared = "MIT"
            },
            [ordered]@{
                name = "picosha2"
                SPDXID = "SPDXRef-Picosha2"
                downloadLocation = "https://github.com/okdshin/PicoSHA2"
                filesAnalyzed = $false
                licenseConcluded = "MIT"
                licenseDeclared = "MIT"
            }
        )
    }
    $Sbom | ConvertTo-Json -Depth 8 -Compress |
        Set-Content -NoNewline -Encoding utf8 `
            (Join-Path $StagingBundle "sbom.spdx.json")

    $Worker = Join-Path $NativeResourceRoot "macro_sim_server.exe"
    $Artifact = Join-Path $ArtifactRoot "fiscal_stabilization_v1.msrl"
    $Manifest = [ordered]@{
        schema_version = 1
        revision = $Revision
        protocol_version = 5
        platform = "windows-x86_64"
        signed = $Signed
        components = [ordered]@{
            worker_sha256 = (
                Get-FileHash -Algorithm SHA256 $Worker
            ).Hash.ToLowerInvariant()
            godot_runtime_sha256 = (
                Get-FileHash -Algorithm SHA256 $GameBinary
            ).Hash.ToLowerInvariant()
            rl_artifact_sha256 = (
                Get-FileHash -Algorithm SHA256 $Artifact
            ).Hash.ToLowerInvariant()
        }
    }
    $Manifest | ConvertTo-Json -Depth 5 -Compress |
        Set-Content -NoNewline -Encoding utf8 `
            (Join-Path $StagingBundle "release-manifest.json")

    New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
    Move-Item $StagingBundle $OutputBundle
    Compress-Archive -Path $OutputBundle -DestinationPath $OutputArchive
    $ArchiveHash = (
        Get-FileHash -Algorithm SHA256 $OutputArchive
    ).Hash.ToLowerInvariant()
    "$ArchiveHash  $([System.IO.Path]::GetFileName($OutputArchive))" |
        Set-Content -Encoding ascii $OutputChecksum
    Write-Output $OutputBundle
    Write-Output $OutputArchive
} finally {
    if (Test-Path $StagingRoot) {
        Remove-Item -Recurse -Force $StagingRoot
    }
}
