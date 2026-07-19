#!/usr/bin/env bash
set -euo pipefail

prototype_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
prototype_port="${MACRO_SIM_PORT:-47821}"
worker_log="$(mktemp -t macro-simulator-worker.XXXXXX.log)"

cleanup() {
    if [[ -n "${worker_pid:-}" ]]; then
        kill "$worker_pid" 2>/dev/null || true
        wait "$worker_pid" 2>/dev/null || true
    fi
    rm -f "$worker_log"
}
trap cleanup EXIT INT TERM

cd "$prototype_root"
uv run python -m macro_sim.desktop.server --port "$prototype_port" >"$worker_log" 2>&1 &
worker_pid=$!

for _ in {1..40}; do
    if grep -q '"status": "ready"' "$worker_log"; then
        break
    fi
    if ! kill -0 "$worker_pid" 2>/dev/null; then
        cat "$worker_log" >&2
        exit 1
    fi
    sleep 0.1
done

if ! command -v godot >/dev/null 2>&1; then
    echo "Godot 4 is required. Install it with: brew install --cask godot" >&2
    exit 1
fi

MACRO_SIM_PORT="$prototype_port" godot --path "$prototype_root/desktop/godot"
