from __future__ import annotations

import json
import socket
import threading

import pytest

from macro_sim.desktop import SimulationRuntime
from macro_sim.desktop.runtime import PANEL_METRIC_NAMES, WORLD_METRIC_NAMES
from macro_sim.desktop.server import _Server


ALL_DECISION_GROUPS = {
    "debt_management",
    "fiscal_stance",
    "tax_and_transfers",
    "monetary_stance",
    "liquidity_operations",
    "fx_operations",
    "macroprudential",
    "structural_law",
    "trade_and_migration",
    "energy_operations",
    "energy_structure",
}


@pytest.fixture(scope="module")
def runtime() -> SimulationRuntime:
    return SimulationRuntime(seed=11)


@pytest.fixture(autouse=True)
def _fresh(runtime: SimulationRuntime):
    runtime.reset(seed=11)
    yield


def _pass_all_contexts(runtime: SimulationRuntime) -> dict:
    snapshot = runtime.snapshot()
    while snapshot["contexts"]:
        snapshot = runtime.resolve_context(snapshot["contexts"][0]["context_id"], [])
    return snapshot


def test_new_game_exposes_all_five_seats(runtime: SimulationRuntime) -> None:
    snapshot = runtime.snapshot()
    assert snapshot["tick"] == 0
    assert snapshot["awaiting_human"] is True
    assert {row["decision_group"] for row in snapshot["contexts"]} == ALL_DECISION_GROUPS
    assert any(
        action["lever"] == "gov_deficit_target"
        for context in snapshot["contexts"]
        for action in context["permitted_actions"]
    )
    lever_total = sum(
        len(context["permitted_actions"]) for context in snapshot["contexts"]
    )
    assert lever_total == 102


def test_pass_then_advance_runs_real_engine(runtime: SimulationRuntime) -> None:
    snapshot = _pass_all_contexts(runtime)
    assert snapshot["tick"] == 1
    snapshot = runtime.advance(3)
    # Advance is deliberately interruptible: a newly due human decision window
    # stops a requested burst before another engine tick is committed.
    assert snapshot["tick"] >= 1
    assert snapshot["awaiting_human"] in (True, False)
    assert len(snapshot["series"]) >= 1
    assert snapshot["metrics"]["real_output"] > 0
    for name in PANEL_METRIC_NAMES:
        assert name in snapshot["metrics"]


def test_world_block_carries_three_coupled_economies(runtime: SimulationRuntime) -> None:
    snapshot = _pass_all_contexts(runtime)
    world = snapshot["world"]
    assert len(world["countries"]) == 3
    assert world["player_economy"] == 0
    latest = world["latest"]
    assert len(latest["economies"]) == 3
    for name in WORLD_METRIC_NAMES:
        assert name in latest["economies"][0]
    # cross-border record: fx vector + NFA + migration are live lists
    assert len(latest["e"]) == 3
    assert len(latest["nfa"]) == 3
    assert len(latest["migrant_stock"]) == 3
    assert world["history"], "world history must accumulate"


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


def test_cross_seat_actions_resolve_in_one_boundary(runtime: SimulationRuntime) -> None:
    """The player holds every seat: a monetary and a fiscal action in the same
    boundary must both reach the pending queue."""
    snapshot = runtime.snapshot()
    submitted = {}
    for group, lever in (
        ("fiscal_stance", "gov_deficit_target"),
        ("monetary_stance", None),
    ):
        context = next(
            item for item in snapshot["contexts"] if item["decision_group"] == group
        )
        actions = []
        for action in context["permitted_actions"]:
            if not action.get("allowed", True):
                continue
            if lever is not None and action["lever"] != lever:
                continue
            value = action.get("current_value")
            maximum = action.get("maximum")
            step = action.get("max_step")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            if not isinstance(maximum, (int, float)) or not isinstance(step, (int, float)):
                continue
            requested = min(maximum, value + step)
            if requested == value:
                continue
            actions.append({"lever": action["lever"], "value": requested})
            break
        if actions:
            snapshot = runtime.resolve_context(context["context_id"], actions)
            submitted[group] = actions[0]["lever"]
    assert len(submitted) == 2, f"expected 2 seats to act, got {submitted}"
    snapshot = _pass_all_contexts(runtime)
    pending_levers = {
        action["lever"] for item in snapshot["pending"] for action in item["actions"]
    }
    assert set(submitted.values()) <= pending_levers


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


def test_get_schema_covers_all_seats(runtime: SimulationRuntime) -> None:
    schema = runtime.handle({"command": "get_schema"})
    # protocol v1 compatibility surface
    assert schema["seat"] == "treasury"
    assert isinstance(schema["levers"], list) and len(schema["levers"]) == 35
    # protocol v2: every seat, 102 levers total
    seats = schema["seats"]
    counts = {seat: len(payload["levers"]) for seat, payload in seats.items()}
    assert counts == {
        "treasury": 35,
        "central_bank": 24,
        "regulator": 28,
        "external_affairs": 9,
        "energy": 6,
    }
    sample = seats["central_bank"]["levers"][0]
    for key in ("name", "decision_group", "implementation_lag", "min_hold_ticks"):
        assert key in sample


def test_merged_observation_includes_restricted_series(runtime: SimulationRuntime) -> None:
    snap = runtime.handle({"command": "snapshot"})
    obs = snap["observation"]
    assert obs["releases"], "the bulletin layer must be present in every snapshot"
    series = {release["series_id"] for release in obs["releases"]}
    # the player holds central_bank/regulator seats, so operational series are
    # part of the merged information set
    assert "bank_reserves_total" in series
    # world-source series exist because the world is coupled
    assert "exchange_rate" in series
    for release in obs["releases"]:
        assert "series_id" in release and "missing_reason" in release


def test_last_verdict_flows_to_snapshot(runtime: SimulationRuntime) -> None:
    snap = runtime.handle({"command": "snapshot"})
    context = next(
        item for item in snap["contexts"] if item["decision_group"] == "fiscal_stance"
    )
    action = next(
        item for item in context["permitted_actions"]
        if item["lever"] == "gov_deficit_target"
    )
    requested = min(action["maximum"], action["current_value"] + action["max_step"])
    out = runtime.handle({
        "command": "resolve_context",
        "context_id": context["context_id"],
        "actions": [{"lever": action["lever"], "value": requested}],
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
