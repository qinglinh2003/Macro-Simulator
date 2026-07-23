from __future__ import annotations

from dataclasses import fields

import pytest

from macro_sim.config import Config
from macro_sim.controllers import (
    HeuristicOccupant,
    NullOccupant,
    RLOccupant,
)
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.desktop.new_game import NewGameSpec
from macro_sim.desktop.runtime import PROTOCOL_VERSION, SimulationRuntime


def _automatic_spec(*, seed: int = 41) -> dict:
    value = NewGameSpec.default(seed=seed).to_dict()
    value["run_mode"] = "batch"
    value["seats"] = {seat: "null" for seat in value["seats"]}
    return value


def test_contract_round_trips_and_identifies_the_playable_model() -> None:
    spec = NewGameSpec.default(seed=23)
    restored = NewGameSpec.from_mapping(spec.to_dict())
    assert restored == spec
    assert restored.contract_hash == spec.contract_hash
    assert restored.model_id == "current_playable_v1"


def test_backend_resolves_the_current_model_without_a_client_selector() -> None:
    request = NewGameSpec.default(seed=29).to_dict()
    request.pop("model_id")
    assert NewGameSpec.from_mapping(request).model_id == "current_playable_v1"

    request["model_id"] = "historical-client-value"
    assert NewGameSpec.from_mapping(request).model_id == "current_playable_v1"


def test_playable_preset_activates_every_completed_gameplay_domain() -> None:
    cfg = NewGameSpec.default().configs()[0]
    for flag in (
        "demographics_enabled",
        "housing_enabled",
        "housing_market_enabled",
        "mortgage_enabled",
        "housing_rental_enabled",
        "housing_construction_enabled",
        "labor_fractional_hours",
        "labor_second_job",
        "energy_enabled",
        "energy_household",
        "consumption_strata",
        "deprivation_gauges",
        "family_transfers",
        "sector_switching",
        "national_accounts_metrics",
        "firm_full_pnl",
        "bank_realized_pnl",
        "capital_service_pricing",
        "priced_firm_balance_sheet",
        "monetary_direct_transmission",
    ):
        assert getattr(cfg, flag) is True, flag
    assert cfg.tfp_drift_rate > 0.0
    assert {
        name: sorted(
            capability
            for capability in lever.requires
            if not getattr(cfg, capability, False)
        )
        for name, lever in REGISTRY.items()
        if any(not getattr(cfg, capability, False) for capability in lever.requires)
    } == {}


def test_playable_preset_does_not_regress_any_enabled_v124_feature() -> None:
    playable = NewGameSpec.default().configs()[0]
    historical = Config.v124(
        n_households=80, n_firms_c=12, n_firms_k=4, n_ticks=365, seed=7
    )
    assert [
        item.name for item in fields(Config)
        if getattr(historical, item.name) is True
        and getattr(playable, item.name) is False
    ] == []


def test_new_game_constructs_selected_profiles_world_and_player() -> None:
    raw = _automatic_spec()
    raw["world"]["trade"] = False
    raw["world"]["migration"] = False
    raw["countries"] = [
        {"name": "小港", "code": "PRT", "profile": "entrepot", "overrides": {}},
        {
            "name": "资源国",
            "code": "RES",
            "profile": "petrostate",
            "overrides": {"n_firms_c": 7, "a": 1.4},
        },
    ]
    raw["player_country"] = 1

    runtime = SimulationRuntime(seed=1)
    snapshot = runtime.reset(spec=raw)

    assert snapshot["protocol_version"] == PROTOCOL_VERSION == 3
    assert [row["latin"] for row in snapshot["world"]["countries"]] == ["PRT", "RES"]
    assert snapshot["world"]["player_economy"] == 1
    assert runtime.world.trade is False
    assert runtime.world.migration is False
    assert runtime.world.economies[0].cfg.n_households == 32
    assert runtime.world.economies[1].cfg.n_households == 64
    assert runtime.world.economies[1].cfg.n_firms_c == 7
    assert runtime.world.economies[1].cfg.a == pytest.approx(1.4)
    assert snapshot["tick"] == 1


def test_scenario_policy_and_occupants_are_live_engine_inputs() -> None:
    raw = NewGameSpec.default(seed=67).to_dict()
    raw["scenario"] = "gfc"
    raw["initial_policy_overrides"] = {
        "0.treasury.tax_income_rate": 0.31,
        "0.external.sanctions_imposed_on": [1],
    }
    raw["seats"] = {
        "treasury": "rl",
        "cb": "heuristic",
        "regulator": "null",
        "external": "null",
        "energy": "null",
    }

    runtime = SimulationRuntime(seed=1)
    snapshot = runtime.reset(spec=raw)

    assert runtime.world.economies[0].policy.tax_income_rate == pytest.approx(0.31)
    assert runtime.world.sanctioned(0, 1) is True
    assert runtime.world.shock_engine.specs
    assert {
        type(runtime.session.seat_assignments[(0, seat)])
        for seat in ("regulator", "external_affairs", "energy")
    } == {NullOccupant}
    assert isinstance(runtime.session.seat_assignments[(0, "central_bank")], HeuristicOccupant)
    assert isinstance(runtime.session.seat_assignments[(0, "treasury")], RLOccupant)
    assert runtime.session.seat_assignments[(0, "treasury")].policy is not None
    assert (
        snapshot["new_game"]["controller_assets"]["fiscal_stabilization_v1"]["sha256"]
        == "1cfc9b0f3b0d2f18ea9b54bbc4130ff447936cbb685aa14e01dd35ef28d107e6"
    )
    assert snapshot["new_game"]["spec"]["scenario"] == "gfc"


def test_all_registry_levers_can_enter_through_initial_policy_contract() -> None:
    runtime = SimulationRuntime(seed=73)
    schema = runtime.schema()["seats"]
    seat_alias = {
        "central_bank": "cb",
        "treasury": "treasury",
        "regulator": "regulator",
        "external_affairs": "external",
        "energy": "energy",
    }
    overrides = {
        f"0.{seat_alias[seat]}.{lever['name']}": lever["current_value"]
        for seat, payload in schema.items()
        for lever in payload["levers"]
    }
    # A dependent lever is valid only when its parent is enabled in the same
    # transaction, even if the dependent's value itself remains false.
    overrides["0.energy.soe_efirm"] = True
    assert len(overrides) == len(REGISTRY) == 102
    raw = _automatic_spec(seed=73)
    raw["initial_policy_overrides"] = overrides

    snapshot = runtime.reset(spec=raw)

    assert len(snapshot["new_game"]["spec"]["initial_policy_overrides"]) == 102


def test_rejected_new_game_does_not_replace_the_active_run() -> None:
    runtime = SimulationRuntime(seed=5)
    original_world = runtime.world
    raw = NewGameSpec.default(seed=9).to_dict()
    raw["countries"][0]["overrides"] = {"n_firms_c": 1}

    with pytest.raises(AssertionError, match="sector split needs"):
        runtime.reset(spec=raw)

    assert runtime.world is original_world
    assert runtime.snapshot()["new_game"]["spec"]["seed"] == 5


def test_initial_policy_must_belong_to_the_named_seat() -> None:
    raw = NewGameSpec.default().to_dict()
    raw["initial_policy_overrides"] = {"0.cb.tax_income_rate": 0.2}
    with pytest.raises(ValueError, match="wrong seat"):
        NewGameSpec.from_mapping(raw)


def test_builtin_rl_policy_is_rejected_outside_its_trained_treasury_seat() -> None:
    raw = NewGameSpec.default().to_dict()
    raw["seats"]["cb"] = "rl"
    with pytest.raises(ValueError, match="Treasury-only"):
        NewGameSpec.from_mapping(raw)


def test_genesis_manual_rate_and_peg_survive_the_first_tick() -> None:
    raw = _automatic_spec(seed=79)
    raw["initial_policy_overrides"] = {
        "0.cb.monetary_regime": "manual",
        "0.cb.manual_policy_rate": 0.000134,
        "0.cb.fx_regime": "peg",
        "0.cb.peg_anchor": 1,
    }
    runtime = SimulationRuntime(seed=1)
    runtime.reset(spec=raw)
    economy = runtime.world.economies[0]
    state = runtime.world.peg_states[0]

    assert economy.policy.monetary_regime == "manual"
    assert economy.policy.manual_policy_rate == pytest.approx(0.000134)
    assert economy.external_policy.fx_regime == "peg"
    assert economy.external_policy.peg_anchor == 1
    assert state.intact is True
    assert runtime.world.economies[1].ledger.balance(state.reserve_account_id) > 0.0


@pytest.mark.parametrize("capability", (
    "bank_enabled",
    "interbank",
    "bonds",
    "capital_market",
    "per_firm_equity",
    "household_credit",
    "housing_enabled",
    "housing_market_enabled",
    "mortgage_enabled",
    "housing_rental_enabled",
    "housing_construction_enabled",
    "demographics_enabled",
    "consumption_strata",
    "energy_enabled",
    "government",
    "national_accounts_metrics",
))
def test_visible_parent_switches_produce_valid_dependency_closures(
    capability: str,
) -> None:
    raw = NewGameSpec.default().to_dict()
    raw["countries"][0]["overrides"] = {capability: False}
    config = NewGameSpec.from_mapping(raw).configs()[0]
    assert getattr(config, capability) is False
