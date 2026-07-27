#!/usr/bin/env bash
set -euo pipefail

prototype_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
native_dir="${MACRO_SIM_NATIVE_DIR:-$prototype_root/build/native/m10-debug/native}"
server_path="${MACRO_SIM_SERVER:-$native_dir/macro_sim_server}"
runtime_root="$(mktemp -d -t macro-simulator-native.XXXXXX)"
bootstrap_path="$runtime_root/worker-bootstrap.json"
ready_path="$runtime_root/worker-ready.json"
client_path="$runtime_root/godot-bootstrap.json"
save_root="${MACRO_SIM_SAVE_ROOT:-$HOME/Library/Application Support/Macro Simulator/saves}"
worker_log="$runtime_root/worker.log"

chmod 700 "$runtime_root"

cleanup() {
    if [[ -n "${worker_pid:-}" ]]; then
        kill -TERM "$worker_pid" 2>/dev/null || true
        wait "$worker_pid" 2>/dev/null || true
    fi
    rm -rf "$runtime_root"
}
trap cleanup EXIT INT TERM

if [[ ! -x "$server_path" ]]; then
    echo "The native desktop worker is not built: $server_path" >&2
    echo "Build it with: cmake --build --preset m10-debug -j 8" >&2
    exit 1
fi
if ! command -v godot >/dev/null 2>&1; then
    echo "Godot 4 is required. Install it with: brew install --cask godot" >&2
    exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
    echo "OpenSSL is required to create the launch capability." >&2
    exit 1
fi

mkdir -p "$save_root"
capability_token="$(openssl rand -hex 32)"
printf '{"token":"%s","save_root":"%s","ready_file":"%s"}' \
    "$capability_token" "$save_root" "$ready_path" >"$bootstrap_path"
chmod 600 "$bootstrap_path"

"$server_path" --bootstrap "$bootstrap_path" >"$worker_log" 2>&1 &
worker_pid=$!

for _ in {1..150}; do
    if [[ -f "$ready_path" ]]; then
        ready_payload="$(<"$ready_path")"
        if [[ "$ready_payload" =~ \"port\":([0-9]+) ]]; then
            worker_port="${BASH_REMATCH[1]}"
            break
        fi
    fi
    if ! kill -0 "$worker_pid" 2>/dev/null; then
        cat "$worker_log" >&2
        exit 1
    fi
    sleep 0.1
done
if [[ -z "${worker_port:-}" ]]; then
    echo "The native desktop worker did not become ready." >&2
    cat "$worker_log" >&2
    exit 1
fi

printf '{"host":"127.0.0.1","port":%s,"protocol_version":5,"token":"%s"}' \
    "$worker_port" "$capability_token" >"$client_path"
chmod 600 "$client_path"
unset capability_token

MACRO_SIM_CLIENT_BOOTSTRAP="$client_path" \
    godot --path "$prototype_root/desktop/godot"
