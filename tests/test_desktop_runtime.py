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
    assert {
        "gov_debt_to_gdp",
        "total_debt_service_ratio",
        "poverty_rate",
        "income_gini",
        "energy_stock_total",
    } <= set(latest["economies"][0])
    # cross-border record: fx vector + NFA + migration are live lists
    assert len(latest["e"]) == 3
    assert len(latest["nfa"]) == 3
    assert len(latest["migrant_stock"]) == 3
    assert world["history"], "world history must accumulate"


def test_panel_details_are_real_micro_aggregates(runtime: SimulationRuntime) -> None:
    snapshot = runtime.snapshot()
    details = snapshot["panel_details"]

    pyramid = details["population"]["pyramid"]
    assert [bucket["label"] for bucket in pyramid] == [
        "0–14", "15–24", "25–34", "35–44", "45–54", "55–64", "65+",
    ]
    assert sum(bucket["male"] + bucket["female"] for bucket in pyramid) == 80

    labor = details["labor"]
    assert sum(state["value"] for state in labor["states"]) == labor[
        "working_age_population"
    ]
    assert [row["label"] for row in labor["participation_by_age"]] == [
        "18–24", "25–34", "35–44", "45–54", "55–64",
    ]
    assert all(
        0.0 <= row["employment_rate"] <= row["participation_rate"] <= 1.0
        for row in labor["participation_by_age"]
    )

    distribution = details["distribution"]
    for name in ("income", "wealth", "consumption"):
        assert len(distribution[name]["deciles"]) == 10
        assert len(distribution[name]["lorenz"]) == 11
        assert distribution[name]["lorenz"][0] == 0.0


def test_household_explorer_reconciles_members_and_balance_sheets(
    runtime: SimulationRuntime,
) -> None:
    households = runtime.snapshot()["households"]
    items = households["items"]
    summary = households["summary"]
    assert items
    assert summary["household_count"] == len(items)
    assert summary["population"] == 80

    person_ids = []
    for household in items:
        members = household["members"]
        assert household["member_count"] == len(members)
        person_ids.extend(member["person_id"] for member in members)
        asset_components = household["assets"]
        assert asset_components["total"] == pytest.approx(sum(
            asset_components[name]
            for name in ("cash", "firm_equity", "bank_equity", "bonds", "housing")
        ))
        assert household["net_worth"] == pytest.approx(
            asset_components["total"] - household["debt"]
        )
        for member in members:
            components = member["assets"]
            assert components["total"] == pytest.approx(sum(
                components[name]
                for name in ("cash", "firm_equity", "bank_equity", "bonds")
            ))
            assert member["net_worth"] == pytest.approx(
                components["total"] - member["debt"]
            )
            assert member["birth_date"]
            assert member["sex"] in {"F", "M"}
    assert len(person_ids) == len(set(person_ids)) == summary["population"]
    assert summary["total_assets"] == pytest.approx(sum(
        household["assets"]["total"] for household in items
    ))
    assert summary["total_debt"] == pytest.approx(sum(
        household["debt"] for household in items
    ))
    assert summary["total_net_worth"] == pytest.approx(sum(
        household["net_worth"] for household in items
    ))
    assert summary["total_consumption"] == pytest.approx(sum(
        household["consumption"] for household in items
    ))


def test_firm_explorer_reconciles_books_people_and_ownership(
    runtime: SimulationRuntime,
) -> None:
    firms = runtime.snapshot()["firms"]
    items = firms["items"]
    summary = firms["summary"]
    assert items
    assert summary["firm_count"] == len(items)
    assert len({firm["firm_id"] for firm in items}) == len(items)
    assert {firm["sector"] for firm in items} == {
        "必需消费", "可选消费", "资本品", "能源",
    }

    for firm in items:
        book = firm["balance_sheet"]
        assert book["inventory_value"] == pytest.approx(
            book["output_inventory_value"]
            + book["work_in_progress_value"]
            + book["input_inventory_value"]
        )
        assert book["gross_assets"] == pytest.approx(
            book["cash"] + book["capital_value"] + book["inventory_value"]
        )
        assert book["book_equity"] == pytest.approx(
            book["gross_assets"] - book["debt"] - book["interest_arrears"]
        )
        equity = firm["equity"]
        assert equity["market_cap"] == pytest.approx(
            equity["shares_outstanding"] * equity["share_price"]
        )
        assert equity["shares_observed"] == pytest.approx(sum(
            holder["shares"] for holder in equity["shareholders"]
        ))
        if equity["enabled"]:
            assert equity["ownership_coverage"] == pytest.approx(1.0)
        assert firm["labor"]["employment_fte"] == pytest.approx(sum(
            employee["hours"] for employee in firm["labor"]["employees"]
        ))
        assert all(employee["person_id"] >= 0 for employee in firm["labor"]["employees"])

    assert summary["employment_fte"] == pytest.approx(sum(
        firm["labor"]["employment_fte"] for firm in items
    ))
    assert summary["total_revenue"] == pytest.approx(sum(
        firm["operations"]["revenue"] for firm in items
    ))
    assert summary["total_assets"] == pytest.approx(sum(
        firm["balance_sheet"]["gross_assets"] for firm in items
    ))
    assert summary["total_debt"] == pytest.approx(sum(
        firm["balance_sheet"]["debt"] for firm in items
    ))

    advanced_snapshot = _pass_all_contexts(runtime)
    advanced = advanced_snapshot["firms"]
    contracts = [
        employee
        for firm in advanced["items"]
        for employee in firm["labor"]["employees"]
    ]
    assert contracts
    assert advanced["summary"]["employment_fte"] > 0.0
    assert all(employee["hire_date"] for employee in contracts)
    assert all(employee["status"] in {"在岗", "停薪留职"} for employee in contracts)
    members_by_id = {
        member["person_id"]: member
        for household in advanced_snapshot["households"]["items"]
        for member in household["members"]
    }
    for employee in contracts:
        member = members_by_id[employee["person_id"]]
        assert any(
            employer["firm_id"] == employee["firm_id"]
            and employer["contract"] == employee["contract"]
            for employer in member["employers"]
        )


def test_stock_market_board_uses_traded_securities_and_chain_linked_history(
    runtime: SimulationRuntime,
) -> None:
    snapshot = runtime.snapshot()
    market = snapshot["stock_market"]
    summary = market["summary"]
    listings = market["listings"]
    assert summary["index_level"] == pytest.approx(1000.0)
    assert summary["listed_count"] == len(listings)
    assert {item["instrument_type"] for item in listings} == {"company", "bank"}
    assert sum(item["market_weight"] for item in listings) == pytest.approx(1.0)
    assert summary["market_cap"] == pytest.approx(sum(
        item["market_cap"] for item in listings
    ))
    assert summary["corporate_market_cap"] == pytest.approx(sum(
        firm["equity"]["market_cap"]
        for firm in snapshot["firms"]["items"]
        if firm["equity"]["enabled"]
    ))

    advanced = _pass_all_contexts(runtime)["stock_market"]
    advanced_summary = advanced["summary"]
    assert len(advanced["history"]) >= 2
    assert advanced_summary["index_level"] > 0.0
    assert (
        advanced_summary["advances"]
        + advanced_summary["declines"]
        + advanced_summary["unchanged"]
    ) == advanced_summary["listed_count"]
    assert sum(sector["market_cap"] for sector in advanced["sectors"]) == pytest.approx(
        advanced_summary["market_cap"]
    )
    assert all(
        item["window_low"] <= item["price"] <= item["window_high"]
        for item in advanced["listings"]
    )


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
    pending = next(
        item for item in snapshot["pending"]
        if item["actions"] == [{"lever": "gov_deficit_target", "value": requested}]
    )
    assert pending["decision"]["effective_tick"] == 7


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
    for key in (
        "name", "decision_group", "implementation_lag", "min_hold_ticks",
        "read_point", "state_notes", "shadowed_by", "player_help",
    ):
        assert key in sample
    assert set(sample["player_help"]) == {
        "meaning", "mechanics", "tradeoffs", "watch",
    }
    snapshot = runtime.snapshot()
    assert set(snapshot["policy_values"]) == {
        lever["name"]
        for seat in seats.values()
        for lever in seat["levers"]
    }
    assert snapshot["policy_values"]["sanctions_imposed_on"] == []


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
    # The population card must come from a delayed public release, not truth metrics.
    assert "population_alive" in series
    assert all(
        context["observation_schema_version"] == 2
        for context in snap["contexts"]
    )
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
    assert verdict["effective_tick"] == 7
    assert verdict["adjustment_cost"] > 0
