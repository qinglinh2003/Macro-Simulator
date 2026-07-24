from __future__ import annotations

import subprocess

from tools.m1 import bootstrap


def test_version_probe_accepts_parseable_nonzero_exit(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap.shutil, "which", lambda command: f"/bin/{command}")
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            returncode=2,
            stdout="Microsoft C/C++ Optimizing Compiler Version 19.44.35228",
            stderr="",
        ),
    )

    result = bootstrap._version("cl", ("/Bv",))

    assert result["found"] is True
    assert result["version"] == [19, 44, 35228]
    assert result["return_code"] == 2


def test_version_probe_rejects_unparseable_output(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap.shutil, "which", lambda command: f"/bin/{command}")
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            returncode=0,
            stdout="version unavailable",
            stderr="",
        ),
    )

    result = bootstrap._version("example")

    assert result["found"] is False
    assert result["version"] is None
    assert result["return_code"] == 0
