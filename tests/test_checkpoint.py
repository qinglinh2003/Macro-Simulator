"""Checkpoint save/resume acceptance suite (docs/checkpoint_design.md section 7).

The heart of the contract is bit-identity ACROSS A PROCESS BOUNDARY:

    digest(run 2N ticks straight) == digest(run N -> save -> fresh-process load -> run N)

Same-process resume would hide module-global state leaks and hash-seed dependence,
so the resume legs of the identity gates run in a subprocess with PYTHONHASHSEED
deliberately left unpinned.
"""
from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from macro_sim.checkpoint import (  # noqa: E402
    BLOB_FORMAT,
    CONTAINER_FORMAT,
    load_checkpoint,
    read_header,
    save_checkpoint,
    state_digest,
)
from macro_sim.config import Config  # noqa: E402
from macro_sim.economy import Economy  # noqa: E402
from macro_sim.diagnostics.world_probes import (  # noqa: E402
    WorldProbeCollector,
    build_small_world,
    diagnose_world,
)

CHILD = REPO / "tests" / "_checkpoint_child.py"


def make_econ(**overrides):
    """Small but demographically live economy: the claims layer, ledger, bonds and
    RNG streams are all exercised, which is exactly the state a checkpoint must carry."""
    params = dict(
        seed=11,
        n_households=20,
        n_firms_c=20,
        n_firms_k=10,
        n_banks=2,
        demographics_population=120,
        n_ticks=200,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def make_world(ticks=200):
    """Small coupled world WITH peg: FX dealer, reserves and world RNGs in play."""
    return build_small_world(n=2, ticks=ticks, population=40, daily=True, peg=True)


def _resume_in_subprocess(ckpt: Path, n_ticks: int, out: Path) -> str:
    """Run the resume leg in a fresh interpreter and return its state digest."""
    subprocess.run(
        [sys.executable, str(CHILD), str(ckpt), str(n_ticks), str(out)],
        check=True, timeout=600, cwd=REPO,
    )
    return out.read_text().strip()


# -- 1. round-trip smoke ------------------------------------------------------------------

def test_roundtrip_smoke_economy(tmp_path):
    econ = make_econ()
    for _ in range(40):
        econ.step()
    path = tmp_path / "econ.msim"
    save_checkpoint(str(path), econ, tick=econ.t)

    loaded, sidecar, header = load_checkpoint(str(path))
    assert header["tick"] == econ.t
    assert header["engine_class"] == "Economy"
    assert sidecar == {}
    assert loaded.t == econ.t
    assert len(loaded.records) == len(econ.records)
    # the whole simulated history came back intact
    assert state_digest(loaded) == state_digest(econ)
    # and the loaded engine is live: it can step (all gates run inside step)
    loaded.step()
    assert loaded.t == econ.t + 1


# -- 2. bit-identity, Economy, cross-process ----------------------------------------------

def test_bit_identity_economy_cross_process(tmp_path):
    straight = make_econ()
    for _ in range(60):
        straight.step()
    want = state_digest(straight)

    split = make_econ()
    for _ in range(30):
        split.step()
    ckpt = tmp_path / "econ30.msim"
    save_checkpoint(str(ckpt), split, tick=split.t)

    got = _resume_in_subprocess(ckpt, 30, tmp_path / "digest.txt")
    assert got == want, "resumed Economy run diverged from the uninterrupted run"


# -- 3. bit-identity, World (peg on), cross-process ---------------------------------------

def test_bit_identity_world_cross_process(tmp_path):
    straight = make_world()
    for _ in range(60):
        straight.step()
    want = state_digest(straight)

    split = make_world()
    for _ in range(30):
        split.step()
    ckpt = tmp_path / "world30.msim"
    save_checkpoint(str(ckpt), split, tick=split.t)

    got = _resume_in_subprocess(ckpt, 30, tmp_path / "digest.txt")
    assert got == want, "resumed World run diverged from the uninterrupted run"


# -- 4. probe-collector continuity --------------------------------------------------------

def test_probe_collector_continuity(tmp_path):
    straight_world = make_world()
    straight = WorldProbeCollector(straight_world)
    for _ in range(40):
        straight.step()
    want_report = diagnose_world(straight_world, straight.records)

    split_world = make_world()
    split = WorldProbeCollector(split_world)
    for _ in range(20):
        split.step()
    ckpt = tmp_path / "probe20.msim"
    save_checkpoint(str(ckpt), split_world, tick=split_world.t,
                    sidecar={"probe_records": split.records})

    world2, sidecar, _hdr = load_checkpoint(str(ckpt))
    stitched = WorldProbeCollector(world2)
    stitched.records = sidecar["probe_records"]
    for _ in range(20):
        stitched.step()
    got_report = diagnose_world(world2, stitched.records)

    assert len(stitched.records) == len(straight.records)
    assert state_digest(world2) == state_digest(straight_world)
    want_checks = {k: v.get("passed") for k, v in want_report.checks.items()}
    got_checks = {k: v.get("passed") for k, v in got_report.checks.items()}
    assert got_checks == want_checks
    assert [f.issue_id for f in got_report.findings] == [f.issue_id for f in want_report.findings]


# -- 5. atomicity: a failing save never corrupts the previous checkpoint ------------------

def test_atomic_save_preserves_previous(tmp_path, monkeypatch):
    econ = make_econ()
    for _ in range(10):
        econ.step()
    path = tmp_path / "ckpt.msim"
    save_checkpoint(str(path), econ, tick=econ.t)
    good_tick = econ.t

    import macro_sim.checkpoint as cp

    def boom(*a, **k):
        raise RuntimeError("simulated failure mid-serialization")

    monkeypatch.setattr(cp.pickle, "dumps", boom)
    econ.step()
    with pytest.raises(RuntimeError):
        save_checkpoint(str(path), econ, tick=econ.t)
    monkeypatch.undo()

    loaded, _sc, header = load_checkpoint(str(path))
    assert header["tick"] == good_tick
    assert loaded.t == good_tick


# -- 6. header integrity ------------------------------------------------------------------

def test_read_header_without_unpickle_and_format_guards(tmp_path):
    econ = make_econ()
    for _ in range(5):
        econ.step()
    path = tmp_path / "hdr.msim"
    save_checkpoint(str(path), econ, tick=econ.t, meta={"label": "hdr-test"})

    header = read_header(str(path))
    assert header["container_format"] == CONTAINER_FORMAT
    assert header["blob_format"] == BLOB_FORMAT
    assert header["tick"] == econ.t
    assert header["label"] == "hdr-test"
    assert header["blob_bytes"] > 0

    # unknown blob format -> clean ValueError, no partial unpickle
    _rewrite_header(path, tmp_path / "alien.msim", blob_format="cpp-soa-v1")
    with pytest.raises(ValueError, match="blob format"):
        load_checkpoint(str(tmp_path / "alien.msim"))

    # unknown container format -> clean ValueError
    _rewrite_header(path, tmp_path / "alien2.msim", container_format="msim-container-v999")
    with pytest.raises(ValueError, match="container format"):
        load_checkpoint(str(tmp_path / "alien2.msim"))


def _rewrite_header(src: Path, dst: Path, **patch):
    with zipfile.ZipFile(src) as zin:
        header = json.loads(zin.read("header.json"))
        blob = zin.read("state.pkl.gz")
    header.update(patch)
    with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_STORED) as zout:
        zout.writestr("header.json", json.dumps(header))
        zout.writestr("state.pkl.gz", blob)


# -- 7. version guard ---------------------------------------------------------------------

def test_version_guard(tmp_path, capsys):
    econ = make_econ()
    for _ in range(5):
        econ.step()
    path = tmp_path / "vguard.msim"
    save_checkpoint(str(path), econ, tick=econ.t)

    stale = tmp_path / "stale.msim"
    _rewrite_header(path, stale, git_commit="deadbeef" * 5)

    # strict mode refuses cross-commit state
    with pytest.raises(ValueError, match="commit"):
        load_checkpoint(str(stale), require_same_commit=True)

    # default mode warns but loads (crash forensics edits code, then loads the dump)
    loaded, _sc, _hdr = load_checkpoint(str(stale))
    assert loaded.t == econ.t
    assert "WARNING" in capsys.readouterr().err


# -- 8. crash forensics dump --------------------------------------------------------------

def test_crash_dump_on_assertion(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO / "scripts"))
    from openecon_portrait import run_portrait

    real_step = WorldProbeCollector.step
    calls = {"n": 0}

    def stepping_mine(self):
        calls["n"] += 1
        if calls["n"] > 5:
            raise AssertionError("synthetic identity-gate failure")
        return real_step(self)

    monkeypatch.setattr(WorldProbeCollector, "step", stepping_mine)

    out = tmp_path / "run"
    with pytest.raises(AssertionError, match="synthetic"):
        run_portrait(n=2, pop=60, years=20 / 365, out_dir=str(out))

    dump = out / "crash_state.msim"
    assert dump.exists(), "crash dump was not written"
    world, sidecar, header = load_checkpoint(str(dump))
    assert header["engine_class"] == "World"
    assert world.t == 5                      # exactly the completed ticks before the failure
    assert len(sidecar["probe_records"]) == 5
    world.step()                             # pre-mortem state is live and steppable
    assert world.t == 6


# -- 9. rolling checkpoint + resume through the runner ------------------------------------

def test_runner_checkpoint_and_resume(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO / "scripts"))
    from openecon_portrait import run_portrait

    years = 30 / 365
    straight_dir = tmp_path / "straight"
    summary_straight = run_portrait(n=2, pop=60, years=years, out_dir=str(straight_dir))

    # leg 1: crash the run at tick 20 with a rolling checkpoint every 10 ticks
    real_step = WorldProbeCollector.step
    calls = {"n": 0}

    def dying_step(self):
        calls["n"] += 1
        if calls["n"] > 20:
            raise AssertionError("synthetic crash at tick 20")
        return real_step(self)

    monkeypatch.setattr(WorldProbeCollector, "step", dying_step)
    resumed_dir = tmp_path / "resumed"
    with pytest.raises(AssertionError):
        run_portrait(n=2, pop=60, years=years, out_dir=str(resumed_dir),
                     checkpoint_every=10)
    monkeypatch.undo()

    ckpt = resumed_dir / "checkpoint.msim"
    assert ckpt.exists()
    assert read_header(str(ckpt))["tick"] == 20

    # leg 2: resume from the rolling checkpoint and finish the horizon
    summary_resumed = run_portrait(n=2, pop=60, years=years, out_dir=str(resumed_dir),
                                   resume=str(ckpt))

    # the stitched run must equal the uninterrupted one where it matters
    assert summary_resumed["identity"] == summary_straight["identity"]
    for a, b in zip(summary_straight["per_economy"], summary_resumed["per_economy"]):
        assert a == b
    straight_csv = (straight_dir / "economy_0.csv").read_bytes()
    resumed_csv = (resumed_dir / "economy_0.csv").read_bytes()
    assert straight_csv == resumed_csv, "per-economy series diverged across resume"
    assert (straight_dir / "world_series.csv").read_bytes() == \
           (resumed_dir / "world_series.csv").read_bytes()
