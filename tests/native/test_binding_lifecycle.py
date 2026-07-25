from __future__ import annotations

import pytest

import macro_sim._native as native


def test_native_version_and_empty_session_lifecycle() -> None:
    assert native.ABI_VERSION == 1
    assert native.engine_version() == "0.6.0-m6"

    session = native.EngineSession(123)
    assert session.session_id == 123
    assert session.tick == 0
    assert session.state is native.SessionState.READY
    assert session.closed is False

    session.close()
    assert session.state is native.SessionState.CLOSED
    assert session.closed is True
    with pytest.raises(RuntimeError, match="already closed"):
        session.close()


def test_session_ids_are_explicit_and_isolated() -> None:
    first = native.EngineSession(7)
    second = native.EngineSession(8)
    assert first.session_id == 7
    assert second.session_id == 8
    assert first.tick == second.tick == 0
