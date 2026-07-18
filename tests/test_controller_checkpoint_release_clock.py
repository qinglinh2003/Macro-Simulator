"""Checkpoint guards for the released-information publication clock."""
from __future__ import annotations

import gzip
import json
import pickle
import zipfile
from dataclasses import replace

import pytest

from macro_sim.checkpoint import load_checkpoint, save_checkpoint, session_digest
from macro_sim.config import Config
from macro_sim.controllers.observation import (
    ObservationFieldSpec,
    ObservationSpec,
    Release,
    ReleaseService,
)
from macro_sim.controllers.occupants import HumanQueueOccupant
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.world import World


def _world() -> World:
    cfg = Config.v13(
        seed=1201,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        n_ticks=20,
        government=True,
    )
    return World([cfg])


def _session() -> ControlledSimulationSession:
    return ControlledSimulationSession(_world())


class _OpaqueReleaseService(ReleaseService):
    pass


def _rewrite_session_blob(source, destination, mutate) -> None:
    with zipfile.ZipFile(source) as archive:
        header = json.loads(archive.read("header.json"))
        payload = pickle.loads(gzip.decompress(archive.read("state.pkl.gz")))
    mutate(payload["world"])
    blob = gzip.compress(pickle.dumps(payload, protocol=5), compresslevel=1)
    header["blob_bytes"] = len(blob)
    # The structural validation runs before header identity comparison on load.
    # Keeping this accurate also makes the fixture a well-formed container rather
    # than relying on an unrelated header failure.
    header["session_digest"] = session_digest(payload["world"])
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("header.json", json.dumps(header))
        archive.writestr("state.pkl.gz", blob)


def test_fresh_advanced_and_awaiting_session_release_clocks_checkpoint_normally(tmp_path):
    fresh = _session()
    fresh_path = tmp_path / "fresh.msim"
    save_checkpoint(str(fresh_path), fresh, tick=fresh.boundary_tick)
    fresh_loaded, _, _ = load_checkpoint(str(fresh_path))
    assert session_digest(fresh_loaded) == session_digest(fresh)

    advanced = _session()
    advanced.run(1)
    assert advanced.release_service._last_boundary == {0: 1}
    advanced_path = tmp_path / "advanced.msim"
    save_checkpoint(str(advanced_path), advanced, tick=advanced.boundary_tick)
    advanced_loaded, _, _ = load_checkpoint(str(advanced_path))
    assert session_digest(advanced_loaded) == session_digest(advanced)

    awaiting = _session()
    awaiting.assign_seat(0, "treasury", HumanQueueOccupant())
    result = awaiting.advance()
    assert result.status == "awaiting_human"
    assert awaiting.release_service._last_boundary == {0: 0}
    awaiting_path = tmp_path / "awaiting.msim"
    save_checkpoint(str(awaiting_path), awaiting, tick=awaiting.boundary_tick)
    awaiting_loaded, _, _ = load_checkpoint(str(awaiting_path))
    assert session_digest(awaiting_loaded) == session_digest(awaiting)


def test_release_service_subclass_is_opaque_to_base_clock_validation(tmp_path):
    session = _session()
    custom = _OpaqueReleaseService(ObservationSpec(()))
    custom._last_boundary = {0: session.boundary_tick + 999}
    custom.application_cache = {"future-shaped-but-opaque": object()}
    session.release_service = custom

    path = tmp_path / "opaque-release-subclass.msim"
    save_checkpoint(str(path), session, tick=session.boundary_tick)
    loaded, _, _ = load_checkpoint(str(path))

    assert type(loaded.release_service) is _OpaqueReleaseService
    assert loaded.release_service._last_boundary == custom._last_boundary
    assert set(loaded.release_service.application_cache) == {
        "future-shaped-but-opaque",
    }


@pytest.mark.parametrize(
    "clock",
    (
        {0: True},       # bool is an int subclass but not a valid wire clock
        {0.0: 0},        # economy IDs are strict ints
        {1: 0},          # one-economy session has only economy 0
        {0: 1},          # future relative to a fresh session boundary
    ),
)
def test_save_rejects_malformed_or_future_release_clock(tmp_path, clock):
    session = _session()
    session.release_service._last_boundary = clock

    with pytest.raises(ValueError, match="release clock"):
        save_checkpoint(
            str(tmp_path / "bad-clock.msim"), session, tick=session.boundary_tick,
        )


def test_save_rejects_release_history_ahead_of_clock(tmp_path):
    session = _session()
    session.release_service._last_boundary[0] = 0
    session.release_service._history[(0, "forged")] = [
        Release(
            "forged",
            1.0,
            reference_start_tick=0,
            reference_end_tick=0,
            released_at_tick=1,
            economy_id=0,
        ),
    ]

    with pytest.raises(ValueError, match="release history.*ahead"):
        save_checkpoint(
            str(tmp_path / "future-history.msim"),
            session,
            tick=session.boundary_tick,
        )


def test_load_rejects_future_release_clock_even_in_well_formed_container(tmp_path):
    source = _session()
    valid_path = tmp_path / "valid.msim"
    tampered_path = tmp_path / "future-clock.msim"
    save_checkpoint(str(valid_path), source, tick=source.boundary_tick)

    def move_clock_ahead(session) -> None:
        session.release_service._last_boundary[0] = session.boundary_tick + 1

    _rewrite_session_blob(valid_path, tampered_path, move_clock_ahead)
    with pytest.raises(ValueError, match="release clock.*ahead"):
        load_checkpoint(str(tampered_path))


@pytest.mark.parametrize("bad_index", (True, 0, -1, 999))
def test_save_rejects_malformed_or_unreachable_next_period_index(tmp_path, bad_index):
    session = _session()
    session.run(1)
    session.release_service._next_period_index[(0, "policy_rate")] = bad_index

    with pytest.raises(ValueError, match="next release period"):
        save_checkpoint(
            str(tmp_path / "bad-next-period.msim"),
            session,
            tick=session.boundary_tick,
        )


def test_load_rejects_next_period_rollback_that_would_repeat_a_release(tmp_path):
    source = _session()
    source.run(1)
    valid_path = tmp_path / "valid-next-period.msim"
    tampered_path = tmp_path / "rolled-back-next-period.msim"
    assert source.release_service._next_period_index[(0, "policy_rate")] == 2
    assert len(source.release_service._history[(0, "policy_rate")]) == 1
    save_checkpoint(str(valid_path), source, tick=source.boundary_tick)

    def roll_back_period(session) -> None:
        session.release_service._next_period_index[(0, "policy_rate")] = 1

    _rewrite_session_blob(valid_path, tampered_path, roll_back_period)
    with pytest.raises(ValueError, match="next release period.*unreachable"):
        load_checkpoint(str(tampered_path))


def test_warmup_and_missing_releases_are_reachable_checkpoint_history(tmp_path):
    releases = ReleaseService(ObservationSpec((
        ObservationFieldSpec(
            "warmup",
            "missing_source",
            window_ticks=3,
            frequency_ticks=1,
            require_full_window=True,
        ),
        ObservationFieldSpec(
            "missing",
            "missing_source",
            window_ticks=1,
            frequency_ticks=1,
        ),
    )))
    session = ControlledSimulationSession(_world(), release_service=releases)
    session.run(1)
    assert releases.history(0, "warmup")[0].missing_reason == "warmup"
    assert releases.history(0, "missing")[0].missing_reason == "source_missing"

    path = tmp_path / "warmup-missing.msim"
    save_checkpoint(str(path), session, tick=session.boundary_tick)
    loaded, _, _ = load_checkpoint(str(path))
    assert session_digest(loaded) == session_digest(session)


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"reference_start_tick": 1}, "period is unreachable"),
        ({"unit": "tampered-unit"}, "metadata disagrees"),
        ({"access_class": "oracle"}, "metadata disagrees"),
    ),
)
def test_load_rejects_release_window_or_fixed_metadata_tampering(
    tmp_path, changes, error,
):
    releases = ReleaseService(ObservationSpec((
        ObservationFieldSpec(
            "windowed",
            "price_index",
            unit="index",
            window_ticks=3,
            frequency_ticks=1,
        ),
    )))
    source = ControlledSimulationSession(_world(), release_service=releases)
    source.run(3)
    valid_path = tmp_path / "valid-windowed.msim"
    tampered_path = tmp_path / f"tampered-{next(iter(changes))}.msim"
    save_checkpoint(str(valid_path), source, tick=source.boundary_tick)

    def tamper(session) -> None:
        history = session.release_service._history[(0, "windowed")]
        assert history[2].reference_start_tick == 0
        assert history[2].reference_end_tick == 2
        history[2] = replace(history[2], **changes)

    _rewrite_session_blob(valid_path, tampered_path, tamper)
    with pytest.raises(ValueError, match=error):
        load_checkpoint(str(tampered_path))


def test_bare_world_checkpoint_is_not_subject_to_controller_release_clock_guard(tmp_path):
    world = _world()
    path = tmp_path / "bare-world.msim"
    save_checkpoint(str(path), world, tick=world.t)
    loaded, _, _ = load_checkpoint(str(path))
    assert isinstance(loaded, World)
