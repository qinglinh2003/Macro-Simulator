from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.native_dir))
    sys.path.insert(1, str(args.source_dir))

    from macro_sim.desktop.new_game import NewGameSpec
    from macro_sim.native_backend import NativeSimulationSession
    from macro_sim.reporting.native_stream import (
        CHUNK_MAGIC,
        NativeMetricStream,
    )

    spec = NewGameSpec.default(seed=955)
    with tempfile.TemporaryDirectory(prefix="macro-sim-m10-history-") as raw:
        directory = Path(raw)
        session = NativeSimulationSession.create(
            spec, history_capacity_frames=8,
        )
        stream = NativeMetricStream(
            directory / "stream", chunk_frames=3,
        )
        assert stream.sync(session) == 1
        for _ in range(20):
            session.advance()
            assert stream.sync(session) == 1
            assert stream.pending_frames < 3
            assert stream.retained_buffer_bytes < 100_000
        stream.flush()
        assert stream.pending_frames == 0
        assert stream.next_sequence == session.history_bounds()[
            "next_sequence"
        ]

        manifest_path = directory / "stream/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["next_sequence"] == 21
        assert len(manifest["chunks"]) == 7
        for chunk in manifest["chunks"]:
            path = directory / "stream/chunks" / (
                chunk["sha256"] + ".bin"
            )
            payload = path.read_bytes()
            assert payload.startswith(CHUNK_MAGIC)
            assert hashlib.sha256(payload).hexdigest() == chunk["sha256"]
            assert len(payload) == chunk["byte_count"]

        checkpoint = session.checkpoint(b'{"history":"external"}')
        restored, objective = NativeSimulationSession.restore(
            spec, checkpoint,
        )
        assert objective == b'{"history":"external"}'
        resumed = NativeMetricStream(
            directory / "stream", chunk_frames=3,
        )
        assert resumed.sync(restored) == 0
        restored.advance()
        assert resumed.sync(restored) == 1
        resumed.close()
        assert resumed.next_sequence == 22
        reloaded = NativeMetricStream(
            directory / "stream", chunk_frames=3,
        )
        assert reloaded.next_sequence == 22

        corrupt_directory = directory / "semantic-corruption"
        shutil.copytree(directory / "stream", corrupt_directory)
        corrupt_manifest_path = corrupt_directory / "manifest.json"
        corrupt_manifest = json.loads(
            corrupt_manifest_path.read_text(encoding="utf-8")
        )
        corrupt_chunk = corrupt_manifest["chunks"][0]
        old_digest = corrupt_chunk["sha256"]
        old_path = corrupt_directory / "chunks" / f"{old_digest}.bin"
        damaged = bytearray(old_path.read_bytes())
        damaged[0] ^= 0x01
        new_digest = hashlib.sha256(damaged).hexdigest()
        (corrupt_directory / "chunks" / f"{new_digest}.bin").write_bytes(
            damaged
        )
        old_path.unlink()
        corrupt_chunk["sha256"] = new_digest
        corrupt_manifest_path.write_text(
            json.dumps(
                corrupt_manifest, ensure_ascii=True, allow_nan=False,
                separators=(",", ":"), sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        try:
            NativeMetricStream(corrupt_directory, chunk_frames=3)
        except ValueError as exc:
            assert "header" in str(exc) or "canonical" in str(exc)
        else:
            raise AssertionError("history stream accepted semantic corruption")

        lagged_session = NativeSimulationSession.create(
            spec, history_capacity_frames=2,
        )
        lagged_session.advance(3)
        lagged = NativeMetricStream(
            directory / "lagged", chunk_frames=2,
        )
        try:
            lagged.sync(lagged_session)
        except RuntimeError as exc:
            assert "fell behind" in str(exc)
        else:
            raise AssertionError("history stream accepted a silent gap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
