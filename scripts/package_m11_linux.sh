#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_preset="${MACRO_SIM_BUILD_PRESET:-m11-release}"
build_root="${MACRO_SIM_BUILD_ROOT:-$repository_root/build/native/$build_preset}"
native_root="$build_root/native"
godot_binary="${GODOT:-$(command -v godot || command -v godot4 || true)}"
output_root="${MACRO_SIM_PACKAGE_ROOT:-$repository_root/build/package/linux}"
output_bundle="$output_root/Macro Command"
host_arch="$(uname -m)"
if [[ "$host_arch" == "arm64" ]]; then
    host_arch="aarch64"
fi
package_arch="${MACRO_SIM_PACKAGE_ARCH:-$host_arch}"
if [[ "$package_arch" != "x86_64" && "$package_arch" != "aarch64" ]]; then
    echo "Unsupported Linux package architecture: $package_arch" >&2
    exit 1
fi
if [[ "$host_arch" != "$package_arch" ]]; then
    echo "The Linux $package_arch package must be built on a $package_arch runner." >&2
    exit 1
fi
package_platform="linux-$package_arch"
output_archive="$output_root/MacroCommand-$package_platform.tar.gz"
output_checksum="$output_archive.sha256"
staging_root="$(mktemp -d -t macro-command-linux.XXXXXX)"
staging_bundle="$staging_root/Macro Command"

cleanup() {
    rm -rf "$staging_root"
}
trap cleanup EXIT INT TERM

if [[ -z "$godot_binary" || ! -x "$godot_binary" ]]; then
    echo "Godot 4 is required to export the desktop application." >&2
    exit 1
fi
if [[ -e "$output_bundle" || -e "$output_archive" ||
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
mkdir -p "$staging_bundle"
godot_preset="Linux x86_64"
if [[ "$package_arch" == "aarch64" ]]; then
    godot_preset="Linux arm64"
fi
"$godot_binary" --headless \
    --path "$repository_root/desktop/godot" \
    --export-release "$godot_preset" \
    "$staging_bundle/Macro Command.game"

game_binary="$staging_bundle/Macro Command.game"
server_binary="$native_root/macro_sim_server"
launcher_binary="$native_root/macro_sim_launcher"
native_resource_root="$staging_bundle/native"
artifact_root="$native_resource_root/artifacts"
license_root="$staging_bundle/licenses"

if [[ ! -x "$game_binary" || ! -x "$server_binary" ||
      ! -x "$launcher_binary" ]]; then
    echo "The exported application or native runtime is incomplete." >&2
    exit 1
fi
install -m 755 "$launcher_binary" "$staging_bundle/Macro Command"
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
cat >"$staging_bundle/sbom.spdx.json" <<EOF
{"spdxVersion":"SPDX-2.3","dataLicense":"CC0-1.0","SPDXID":"SPDXRef-DOCUMENT","name":"Macro Command Linux $package_arch","documentNamespace":"https://macrocommand.local/spdx/$revision","creationInfo":{"created":"1970-01-01T00:00:00Z","creators":["Tool: macro-sim-package-m11"]},"packages":[{"name":"Macro Command","SPDXID":"SPDXRef-MacroCommand","versionInfo":"$revision","downloadLocation":"NOASSERTION","filesAnalyzed":false,"licenseConcluded":"NOASSERTION","licenseDeclared":"NOASSERTION"},{"name":"Godot Engine","SPDXID":"SPDXRef-Godot","versionInfo":"4.7.1","downloadLocation":"https://godotengine.org/","filesAnalyzed":false,"licenseConcluded":"MIT","licenseDeclared":"MIT"},{"name":"FlatBuffers","SPDXID":"SPDXRef-FlatBuffers","downloadLocation":"https://github.com/google/flatbuffers","filesAnalyzed":false,"licenseConcluded":"Apache-2.0","licenseDeclared":"Apache-2.0"},{"name":"JSON for Modern C++","SPDXID":"SPDXRef-NlohmannJson","downloadLocation":"https://github.com/nlohmann/json","filesAnalyzed":false,"licenseConcluded":"MIT","licenseDeclared":"MIT"},{"name":"picosha2","SPDXID":"SPDXRef-Picosha2","downloadLocation":"https://github.com/okdshin/PicoSHA2","filesAnalyzed":false,"licenseConcluded":"MIT","licenseDeclared":"MIT"}]}
EOF

worker_sha="$(sha256sum "$native_resource_root/macro_sim_server" | awk '{print $1}')"
game_sha="$(sha256sum "$game_binary" | awk '{print $1}')"
artifact_sha="$(sha256sum "$artifact_root/fiscal_stabilization_v1.msrl" | awk '{print $1}')"
cat >"$staging_bundle/release-manifest.json" <<EOF
{"schema_version":1,"revision":"$revision","protocol_version":5,"platform":"$package_platform","components":{"worker_sha256":"$worker_sha","godot_runtime_sha256":"$game_sha","rl_artifact_sha256":"$artifact_sha"}}
EOF

mkdir -p "$output_root"
mv "$staging_bundle" "$output_bundle"
tar --sort=name --mtime="UTC 1970-01-01" --owner=0 --group=0 \
    --numeric-owner -C "$output_root" -czf "$output_archive" \
    "Macro Command"
sha256sum "$output_archive" >"$output_checksum"
echo "$output_bundle"
echo "$output_archive"
