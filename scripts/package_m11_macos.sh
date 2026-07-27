#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_preset="${MACRO_SIM_BUILD_PRESET:-m11-release}"
build_root="${MACRO_SIM_BUILD_ROOT:-$repository_root/build/native/$build_preset}"
native_root="$build_root/native"
godot_binary="${GODOT:-$(command -v godot || true)}"
output_root="${MACRO_SIM_PACKAGE_ROOT:-$repository_root/build/package}"
output_app="$output_root/Macro Command.app"
host_arch="$(uname -m)"
package_arch="${MACRO_SIM_PACKAGE_ARCH:-$host_arch}"
if [[ "$package_arch" != "arm64" && "$package_arch" != "x86_64" ]]; then
    echo "Unsupported macOS package architecture: $package_arch" >&2
    exit 1
fi
if [[ "$host_arch" != "$package_arch" ]]; then
    echo "The macOS $package_arch package must be built on a $package_arch runner." >&2
    exit 1
fi
package_platform="macos-$package_arch"
output_archive="$output_root/Macro Command-$package_platform.zip"
output_checksum="$output_archive.sha256"
staging_root="$(mktemp -d -t macro-command-package.XXXXXX)"
staging_app="$staging_root/Macro Command.app"

cleanup() {
    rm -rf "$staging_root"
}
trap cleanup EXIT INT TERM

if [[ -z "$godot_binary" || ! -x "$godot_binary" ]]; then
    echo "Godot 4 is required to export the desktop application." >&2
    exit 1
fi
if [[ -e "$output_app" || -e "$output_archive" ||
      -e "$output_checksum" ]]; then
    echo "The package output already exists: $output_root" >&2
    exit 1
fi

cmake_arguments=(--preset "$build_preset")
if [[ -x "$repository_root/.venv/bin/python3" ]]; then
    cmake_arguments+=(
        "-DPython_EXECUTABLE=$repository_root/.venv/bin/python3"
    )
fi
cmake "${cmake_arguments[@]}"
cmake --build --preset "$build_preset" -j 8 \
    --target macro_sim_server macro_sim_launcher

"$godot_binary" --headless \
    --path "$repository_root/desktop/godot" \
    --import
"$godot_binary" --headless \
    --path "$repository_root/desktop/godot" \
    --export-release "macOS universal" "$staging_app"

game_binary="$staging_app/Contents/MacOS/Macro Command"
packaged_game="$game_binary.game"
server_binary="$native_root/macro_sim_server"
launcher_binary="$native_root/macro_sim_launcher"
resource_root="$staging_app/Contents/Resources"
native_resource_root="$resource_root/native"
artifact_root="$native_resource_root/artifacts"
license_root="$resource_root/licenses"

if [[ ! -x "$game_binary" || ! -x "$server_binary" ||
      ! -x "$launcher_binary" ]]; then
    echo "The exported application or native runtime is incomplete." >&2
    exit 1
fi

thinned_game="$game_binary.$package_arch"
lipo "$game_binary" -thin "$package_arch" -output "$thinned_game"
chmod 755 "$thinned_game"
mv "$thinned_game" "$game_binary"
if [[ "$(lipo -archs "$game_binary")" != "$package_arch" ||
      "$(lipo -archs "$server_binary")" != "$package_arch" ||
      "$(lipo -archs "$launcher_binary")" != "$package_arch" ]]; then
    echo "The packaged runtime is not consistently $package_arch." >&2
    exit 1
fi

mv "$game_binary" "$packaged_game"
install -m 755 "$launcher_binary" "$game_binary"
mkdir -p "$artifact_root" "$license_root"
install -m 755 "$server_binary" \
    "$native_resource_root/macro_sim_server"
install -m 644 \
    "$repository_root/macro_sim/rl/artifacts/fiscal_stabilization_v1.msrl" \
    "$artifact_root/fiscal_stabilization_v1.msrl"
install -m 644 "$repository_root/native/vendor/flatbuffers/LICENSE" \
    "$license_root/flatbuffers-LICENSE"
install -m 644 "$repository_root/native/vendor/nlohmann-json/LICENSE.MIT" \
    "$license_root/nlohmann-json-LICENSE"
install -m 644 "$repository_root/native/vendor/picosha2/LICENSE" \
    "$license_root/picosha2-LICENSE"

revision="$(git -C "$repository_root" rev-parse HEAD)"
cat >"$resource_root/sbom.spdx.json" <<EOF
{"spdxVersion":"SPDX-2.3","dataLicense":"CC0-1.0","SPDXID":"SPDXRef-DOCUMENT","name":"Macro Command macOS $package_arch","documentNamespace":"https://macrocommand.local/spdx/$revision","creationInfo":{"created":"1970-01-01T00:00:00Z","creators":["Tool: macro-sim-package-m11"]},"packages":[{"name":"Macro Command","SPDXID":"SPDXRef-MacroCommand","versionInfo":"$revision","downloadLocation":"NOASSERTION","filesAnalyzed":false,"licenseConcluded":"NOASSERTION","licenseDeclared":"NOASSERTION"},{"name":"Godot Engine","SPDXID":"SPDXRef-Godot","versionInfo":"4.7.1","downloadLocation":"https://godotengine.org/","filesAnalyzed":false,"licenseConcluded":"MIT","licenseDeclared":"MIT"},{"name":"FlatBuffers","SPDXID":"SPDXRef-FlatBuffers","downloadLocation":"https://github.com/google/flatbuffers","filesAnalyzed":false,"licenseConcluded":"Apache-2.0","licenseDeclared":"Apache-2.0"},{"name":"JSON for Modern C++","SPDXID":"SPDXRef-NlohmannJson","downloadLocation":"https://github.com/nlohmann/json","filesAnalyzed":false,"licenseConcluded":"MIT","licenseDeclared":"MIT"},{"name":"picosha2","SPDXID":"SPDXRef-Picosha2","downloadLocation":"https://github.com/okdshin/PicoSHA2","filesAnalyzed":false,"licenseConcluded":"MIT","licenseDeclared":"MIT"}]}
EOF

signing_identity="${MACRO_SIM_CODESIGN_IDENTITY:--}"
signing_arguments=(--force --sign "$signing_identity")
if [[ "$signing_identity" == "-" ]]; then
    signing_arguments+=(--timestamp=none)
else
    signing_arguments+=(--options runtime --timestamp)
fi
codesign "${signing_arguments[@]}" "$packaged_game"
codesign "${signing_arguments[@]}" \
    "$native_resource_root/macro_sim_server"
codesign "${signing_arguments[@]}" "$game_binary"

server_sha="$(shasum -a 256 "$native_resource_root/macro_sim_server" | awk '{print $1}')"
game_sha="$(shasum -a 256 "$packaged_game" | awk '{print $1}')"
artifact_sha="$(shasum -a 256 "$artifact_root/fiscal_stabilization_v1.msrl" | awk '{print $1}')"
cat >"$resource_root/release-manifest.json" <<EOF
{"schema_version":1,"revision":"$revision","protocol_version":5,"platform":"$package_platform","components":{"worker_sha256":"$server_sha","godot_runtime_sha256":"$game_sha","rl_artifact_sha256":"$artifact_sha"}}
EOF

codesign "${signing_arguments[@]}" "$staging_app"
codesign --verify --deep --strict "$staging_app"

notary_profile="${MACRO_SIM_NOTARY_PROFILE:-}"
if [[ -n "$notary_profile" ]]; then
    if [[ "$signing_identity" == "-" ]]; then
        echo "Notarization requires a production signing identity." >&2
        exit 1
    fi
    notarization_archive="$staging_root/notarization.zip"
    ditto -c -k --sequesterRsrc --keepParent \
        "$staging_app" "$notarization_archive"
    xcrun notarytool submit "$notarization_archive" \
        --keychain-profile "$notary_profile" --wait
    xcrun stapler staple "$staging_app"
    codesign --verify --deep --strict "$staging_app"
    spctl --assess --type execute "$staging_app"
fi

mkdir -p "$output_root"
mv "$staging_app" "$output_app"
ditto -c -k --sequesterRsrc --keepParent \
    "$output_app" "$output_archive"
shasum -a 256 "$output_archive" >"$output_checksum"
echo "$output_app"
echo "$output_archive"
