from __future__ import annotations

import json
import socket
import threading

import pytest

from macro_sim.desktop import SimulationRuntime
from macro_sim.desktop.server import _Server


@pytest.fixture
def runtime() -> SimulationRuntime:
    return SimulationRuntime(seed=11)


def _pass_all_contexts(runtime: SimulationRuntime) -> dict:
    snapshot = runtime.snapshot()
    while snapshot["contexts"]:
        snapshot = runtime.resolve_context(snapshot["contexts"][0]["context_id"], [])
    return snapshot


def test_new_game_exposes_real_controller_contexts(runtime: SimulationRuntime) -> None:
    snapshot = runtime.snapshot()
    assert snapshot["tick"] == 0
    assert snapshot["awaiting_human"] is True
    assert {row["decision_group"] for row in snapshot["contexts"]} == {
        "debt_management",
        "fiscal_stance",
        "tax_and_transfers",
    }
    assert any(
        action["lever"] == "gov_deficit_target"
        for context in snapshot["contexts"]
        for action in context["permitted_actions"]
    )


def test_pass_then_advance_runs_real_engine(runtime: SimulationRuntime) -> None:
    snapshot = _pass_all_contexts(runtime)
    assert snapshot["tick"] == 1
    snapshot = runtime.advance(3)
    # Advance is deliberately interruptible: a newly due human decision window
    # stops a requested burst before another engine tick is committed.
    assert snapshot["tick"] == 3
    assert snapshot["advanced_ticks"] == 2
    assert snapshot["awaiting_human"] is True
    assert len(snapshot["series"]) == 3
    assert snapshot["metrics"]["real_output"] > 0


def test_policy_action_uses_controller_proposal_path(runtime: SimulationRuntime) -> None:
    context = next(
        item for item in runtime.snapshot()["contexts"]
        if item["decision_group"] == "fiscal_stance"
    )
    action = next(
        item for item in context["permitted_actions"]
        if item["lever"] == "gov_deficit_target"
    )
    requested = min(action["maximum"], action["current_value"] + action["max_step"])
    snapshot = runtime.resolve_context(
        context["context_id"],
        [{"lever": action["lever"], "value": requested}],
    )
    assert snapshot["awaiting_human"] is True
    assert any(event["event_type"] == "human_proposal_queued" for event in snapshot["events"])
    snapshot = _pass_all_contexts(runtime)
    assert snapshot["tick"] == 1
    assert any(
        item["actions"] == [{"lever": "gov_deficit_target", "value": requested}]
        for item in snapshot["pending"]
    )


def test_shock_is_scheduled_at_next_boundary(runtime: SimulationRuntime) -> None:
    snapshot = runtime.trigger_shock()
    assert snapshot["shock_bulletins"] == []  # not announced early
    snapshot = _pass_all_contexts(runtime)
    bulletin = snapshot["shock_bulletins"][0]
    assert bulletin["start_tick"] == 1
    assert bulletin["kind"] == "productivity"
    assert snapshot["active_shocks"]


def test_bad_command_does_not_advance_state(runtime: SimulationRuntime) -> None:
    before = runtime.snapshot()["tick"]
    with pytest.raises(ValueError, match="unknown command"):
        runtime.handle({"command": "destroy_everything"})
    assert runtime.snapshot()["tick"] == before


def test_ndjson_transport_contains_request_failure(runtime: SimulationRuntime) -> None:
    server = _Server(("127.0.0.1", 0), runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.create_connection(server.server_address, timeout=2) as connection:
            stream = connection.makefile("rwb")
            stream.write(
                json.dumps({"request_id": "bad:1", "command": "unknown"}).encode()
                + b"\n"
            )
            stream.flush()
            failed = json.loads(stream.readline())
            assert failed["request_id"] == "bad:1"
            assert failed["ok"] is False

            stream.write(
                json.dumps({"request_id": "good:1", "command": "snapshot"}).encode()
                + b"\n"
            )
            stream.flush()
            recovered = json.loads(stream.readline())
            assert recovered["request_id"] == "good:1"
            assert recovered["ok"] is True
            assert recovered["snapshot"]["tick"] == 0
            connection.shutdown(socket.SHUT_RDWR)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_get_schema_and_bulletin_observation():
    runtime = SimulationRuntime(seed=7)
    schema = runtime.handle({"command": "get_schema"})
    assert schema["seat"] == "treasury"
    levers = schema["levers"]
    assert isinstance(levers, list) and len(levers) >= 20
    sample = levers[0]
    for key in ("name", "decision_group", "implementation_lag", "min_hold_ticks"):
        assert key in sample
    snap = runtime.handle({"command": "snapshot"})
    obs = snap["observation"]
    assert obs["releases"], "the bulletin layer must be present in every snapshot"
    for release in obs["releases"]:
        assert "series_id" in release and "missing_reason" in release


def test_last_verdict_flows_to_snapshot():
    runtime = SimulationRuntime(seed=7)
    snap = runtime.handle({"command": "snapshot"})
    context = snap["contexts"][0]
    out = runtime.handle({
        "command": "resolve_context",
        "context_id": context["context_id"],
        "actions": [],
    })
    while out.get("contexts"):
        out = runtime.handle({
            "command": "resolve_context",
            "context_id": out["contexts"][0]["context_id"],
            "actions": [],
        })
    out = runtime.handle({"command": "advance", "ticks": 1})
    verdict = out.get("last_verdict")
    assert isinstance(verdict, dict) and str(verdict.get("status", "")).startswith("accepted")
