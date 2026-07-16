"""Save/resume checkpoints: an engine-neutral container around an engine-specific blob.

Design: docs/checkpoint_design.md. Container layout (a zip, extension ``.msim``):

    header.json    -- engine-NEUTRAL metadata: container/blob format tags, tick, engine
                      class, git commit, config digest. Any future engine (or a game
                      frontend's save-slot UI) reads this without touching the blob.
    state.pkl.gz   -- engine-SPECIFIC state blob. For the Python engine: a gzip'd
                      pickle of the full object graph (World or Economy) plus sidecar
                      state (e.g. probe-collector records). Pickle covers every piece
                      of live state BY CONSTRUCTION -- RNG streams, ledgers, lot books,
                      EMAs, caches, estate suspense -- so there is no "forgot to
                      serialize a field" failure mode while the model is still evolving.

The hand-written, language-neutral state schema is deliberately deferred to the
model-freeze / compiled-engine port; it will slot into this same container as a new
``blob_format``. What survives that engine swap is everything around the blob:
container layout, header schema, ruleset serialization, event-log schema.

SECURITY: loading a pickle executes arbitrary code. This is a local dev tool --
NEVER load a third-party ``.msim``. The game-era structured blob removes this hazard.

Acceptance contract (tests/test_checkpoint.py): a resumed run is bit-identical to an
uninterrupted one, across a process boundary:

    digest(run 2N ticks straight) == digest(run N -> save -> load in a FRESH process -> run N)
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import pickle
import subprocess
import sys
import zipfile
from typing import Any

CONTAINER_FORMAT = "msim-container-v1"
BLOB_FORMAT = "python-pickle-v0"


def state_digest(engine: Any) -> str:
    """Canonical digest of an engine's simulated history, for bit-identity gates.

    sha256 over the json-serialized record rows -- the same discipline as the
    frontier digest. For a World: world_records + every economy's records; for a
    single Economy: its records. A resumed run must reproduce this EXACTLY.
    """
    h = hashlib.sha256()
    economies = getattr(engine, "economies", None)
    if economies is not None:  # World
        for row in getattr(engine, "world_records", []) or []:
            h.update(json.dumps(row, sort_keys=True, default=str).encode())
        for econ in economies:
            for row in econ.records:
                h.update(json.dumps(row, sort_keys=True, default=str).encode())
    else:  # Economy
        for row in engine.records:
            h.update(json.dumps(row, sort_keys=True, default=str).encode())
    return h.hexdigest()


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _config_digest(obj: Any) -> str | None:
    """Best-effort stable digest of the run's config(s) for the header."""
    try:
        cfgs = getattr(obj, "configs", None)
        if cfgs is None:
            cfg = getattr(obj, "cfg", None)
            cfgs = [cfg] if cfg is not None else []
        h = hashlib.sha256()
        for cfg in cfgs:
            h.update(repr(cfg).encode())
        return h.hexdigest()[:16]
    except Exception:
        return None


def save_checkpoint(
    path: str,
    world: Any,
    *,
    tick: int,
    sidecar: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> str:
    """Write an atomic checkpoint container.

    ``world`` is the live engine object (World or Economy). ``sidecar`` carries
    companion state that lives OUTSIDE the engine object and must ride along
    explicitly -- e.g. the probe collector's records list. ``meta`` merges extra
    free-form fields into header.json (seed, out_dir, label, ...).

    Atomicity: the container is written to ``<path>.tmp`` and moved into place
    with ``os.replace`` -- a crash mid-save can never corrupt the previous file.
    """
    payload = {"world": world, "sidecar": sidecar or {}}
    # gzip level 1: the blob is float-heavy simulation state; speed beats ratio.
    blob = gzip.compress(pickle.dumps(payload, protocol=5), compresslevel=1)
    header = {
        "container_format": CONTAINER_FORMAT,
        "blob_format": BLOB_FORMAT,
        "tick": int(tick),
        "engine_class": type(world).__name__,
        "git_commit": _git_commit(),
        "config_digest": _config_digest(world),
        "blob_bytes": len(blob),
    }
    if meta:
        header.update(meta)
    tmp = f"{path}.tmp"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("header.json", json.dumps(header, indent=1, default=str))
        zf.writestr("state.pkl.gz", blob)
    os.replace(tmp, path)
    return path


def read_header(path: str) -> dict[str, Any]:
    """Read the engine-neutral header without touching (or unpickling) the blob."""
    with zipfile.ZipFile(path) as zf:
        return json.loads(zf.read("header.json"))


def load_checkpoint(
    path: str,
    *,
    require_same_commit: bool = False,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Load a checkpoint. Returns ``(world, sidecar, header)``.

    Version guard: the header records the git commit that wrote the state. With
    ``require_same_commit=True`` a mismatch refuses to load -- the class layout may
    have changed, and pickle would either fail loudly or, worse, resume with
    silently stale semantics. The DEFAULT is a warning, not a refusal: day-to-day
    crash forensics is "edit the code, then load the dump", and must be able to.
    """
    with zipfile.ZipFile(path) as zf:
        header = json.loads(zf.read("header.json"))
        if header.get("container_format") != CONTAINER_FORMAT:
            raise ValueError(f"unknown container format: {header.get('container_format')!r}")
        if header.get("blob_format") != BLOB_FORMAT:
            raise ValueError(
                f"blob format {header.get('blob_format')!r} is not readable by this engine "
                f"(expected {BLOB_FORMAT!r})"
            )
        here = _git_commit()
        there = header.get("git_commit")
        if here and there and here != there:
            msg = (f"checkpoint written at commit {there[:12]}, code is at {here[:12]}")
            if require_same_commit:
                raise ValueError(msg + "; pass require_same_commit=False to force")
            print(f"WARNING: {msg} -- resuming anyway", file=sys.stderr)
        payload = pickle.loads(gzip.decompress(zf.read("state.pkl.gz")))
    return payload["world"], payload.get("sidecar", {}), header
