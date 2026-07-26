from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def _configure_paths(native_dir: Path, source_dir: Path) -> None:
    sys.path.insert(0, str(native_dir))
    sys.path.insert(1, str(source_dir))


def _restore(checkpoint_path: Path) -> int:
    from macro_sim.controllers.native_session import (
        restore_native_controlled_session,
    )
    from macro_sim.controllers.observation import ReleaseSequence
    from macro_sim.desktop.new_game import NewGameSpec

    spec = NewGameSpec.default(seed=1701)
    _world, session, objective = restore_native_controlled_session(
        spec, checkpoint_path.read_bytes(),
    )
    assert objective == b'{"history":"portable"}'
    assert session.events.event_count == 600
    assert session.events.retained_event_count <= 256
    assert session.events.chunk_digests
    session.events.verify()
    histories = [
        history
        for history in session.release_service._history.values()
        if isinstance(history, ReleaseSequence) and len(history) == 200
    ]
    assert len(histories) == 1
    history = histories[0]
    assert history.retained_count <= 64
    assert history.chunk_digests
    assert history[-1].released_at_tick == 199
    print(json.dumps({
        "event_chunks": len(session.events.chunk_digests),
        "event_retained": session.events.retained_event_count,
        "release_chunks": len(history.chunk_digests),
        "release_retained": history.retained_count,
    }, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args()
    native_dir = args.native_dir.resolve()
    source_dir = args.source_dir.resolve()
    _configure_paths(native_dir, source_dir)
    if args.restore is not None:
        return _restore(args.restore)

    from macro_sim.controllers.chunk_store import (
        export_chunk_package,
        put_chunk,
    )
    from macro_sim.controllers.native_envelope import (
        controller_archive_package,
        decode_controller_state,
        encode_controller_state,
    )
    from macro_sim.controllers.native_session import (
        create_native_controlled_session,
    )
    from macro_sim.controllers.observation import Release, ReleaseSequence
    from macro_sim.desktop.new_game import NewGameSpec

    spec = NewGameSpec.default(seed=1701)
    world, session = create_native_controlled_session(spec)
    for sequence in range(600):
        session.events.append(
            "history_stream_probe",
            "derived",
            session.boundary_tick,
            session.phase,
            payload={"probe_sequence": sequence},
        )
    assert session.events.retained_event_count <= 256
    assert session.events.chunk_digests

    field = next(
        item for item in session.release_service.spec.fields
        if item.source != "shock"
    )
    history = ReleaseSequence()
    for boundary in range(200):
        history.append(Release(
            field.series_id,
            float(boundary),
            boundary,
            boundary,
            boundary,
            access_class=field.access_class,
            unit=field.unit,
            economy_id=0,
        ))
    session.release_service._history[(0, field.series_id)] = history
    assert history.retained_count <= 64
    assert history.chunk_digests

    world.sync_controller_state(session)
    envelope = encode_controller_state(session)
    archive = controller_archive_package(session)
    assert len(envelope) < 2_000_000
    event_state = session.events.to_state()["events"]
    release_state = history.to_state()
    assert set(event_state) == {
        "archived_count", "chunk_count", "chunk_head_sha256",
        "chunk_size", "tail", "tail_limit", "total_count",
    }
    assert set(release_state["chunks"]) == {"count", "head_sha256"}
    assert len(archive) > len(envelope)
    decoded = decode_controller_state(
        envelope, archive_package=archive,
    )
    assert decoded["events"].event_count == 600
    assert len(decoded["release_service"]._history[
        (0, field.series_id)
    ]) == 200

    unrelated = put_chunk(b"controller-history-unrelated-chunk")
    extra_archive = export_chunk_package(
        set(session.events.chunk_digests)
        | set(history.chunk_digests)
        | {unrelated}
    )
    try:
        decode_controller_state(
            envelope, archive_package=extra_archive,
        )
    except ValueError as exc:
        assert "exactly match" in str(exc)
    else:
        raise AssertionError(
            "controller envelope accepted an undeclared archive chunk"
        )

    with tempfile.TemporaryDirectory(
        prefix="macro-sim-controller-history-",
    ) as raw:
        checkpoint_path = Path(raw) / "portable.msim"
        checkpoint_path.write_bytes(world.checkpoint_controller(
            session, b'{"history":"portable"}',
        ))
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--native-dir", str(native_dir),
                "--source-dir", str(source_dir),
                "--restore", str(checkpoint_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        assert result["event_chunks"] > 0
        assert result["release_chunks"] > 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
