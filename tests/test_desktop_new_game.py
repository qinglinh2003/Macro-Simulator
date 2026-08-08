from __future__ import annotations

from dataclasses import fields, replace
from datetime import date

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
from macro_sim.diagnostics.config_experiment import (
    apply_config_treatment,
    native_treatment_spec,
    population_scaled_new_game,
)
from macro_sim.diagnostics.config_native_baseline import (
    build_native_baseline_audit,
)
from macro_sim.economy import Economy
from macro_sim.native_backend import (
    build_native_new_game_spec,
    build_world_spec,
    build_world_spec_from_configs,
)


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
    assert restored.duration == restored.duration_ticks == 1_827


@pytest.mark.parametrize(
    ("raw_duration", "expected"),
    [
        ("1y", 365),
        ("5y", 1_825),
        ("10y", 3_650),
        ("inf", None),
        (None, None),
        (830, 830),
    ],
)
def test_duration_accepts_legacy_presets_and_exact_tick_counts(
    raw_duration: object,
    expected: int | None,
) -> None:
    raw = NewGameSpec.default().to_dict()
    raw["duration"] = raw_duration

    spec = NewGameSpec.from_mapping(raw)

    assert spec.duration == expected
    assert spec.duration_ticks == expected
    assert spec.to_dict()["duration"] == expected


@pytest.mark.parametrize("duration", [True, 0, -1, 1.5, "365", [], {}])
def test_duration_rejects_non_positive_or_ambiguous_values(duration: object) -> None:
    raw = NewGameSpec.default().to_dict()
    raw["duration"] = duration
    with pytest.raises((TypeError, ValueError)):
        NewGameSpec.from_mapping(raw)


def test_start_date_is_real_genesis_input_and_leap_days_are_exact() -> None:
    raw = NewGameSpec.default().to_dict()
    raw["start_date"] = "2024-02-29"
    raw["duration"] = 366

    spec = NewGameSpec.from_mapping(raw)
    economy = spec.configs()[0]

    assert spec.start_date == "2024-02-29"
    assert economy.simulation_start_date == "2024-02-29"
    assert economy.n_ticks == 366
    assert Economy(economy).demographic_state.current_date == date(2024, 2, 29)


@pytest.mark.parametrize("start_date", [None, "", "2023-02-29", "23-01-01"])
def test_start_date_rejects_non_iso_or_impossible_dates(start_date: object) -> None:
    raw = NewGameSpec.default().to_dict()
    raw["start_date"] = start_date
    with pytest.raises((TypeError, ValueError)):
        NewGameSpec.from_mapping(raw)


def test_start_date_and_duration_must_fit_the_gregorian_calendar() -> None:
    raw = NewGameSpec.default().to_dict()
    raw["start_date"] = date.max.isoformat()
    raw["duration"] = 1
    with pytest.raises(ValueError, match="exceeds the Gregorian calendar"):
        NewGameSpec.from_mapping(raw)


def test_exact_tick_duration_stops_the_desktop_runtime_without_overshoot() -> None:
    raw = _automatic_spec(seed=31)
    raw["start_date"] = "2024-02-28"
    raw["duration"] = 3
    runtime = SimulationRuntime(seed=1)

    initial = runtime.reset(spec=raw)
    final = runtime.advance(20)

    assert initial["tick"] == 1
    assert final["tick"] == 3
    assert final["advanced_ticks"] == 2
    assert final["new_game"]["run_complete"] is True
    assert final["new_game"]["remaining_ticks"] == 0
    assert runtime.world.economies[0].demographic_state.current_date == date(2024, 3, 2)


def test_backend_resolves_the_current_model_without_a_client_selector() -> None:
    request = NewGameSpec.default(seed=29).to_dict()
    request.pop("model_id")
    assert NewGameSpec.from_mapping(request).model_id == "current_playable_v1"

    request["model_id"] = "historical-client-value"
    assert NewGameSpec.from_mapping(request).model_id == "current_playable_v1"


def test_legacy_new_game_without_start_date_uses_original_genesis_date() -> None:
    request = NewGameSpec.default().to_dict()
    request.pop("start_date")
    assert NewGameSpec.from_mapping(request).start_date == "2000-01-01"


def test_country_counts_replace_the_legacy_global_performance_selector() -> None:
    request = NewGameSpec.default().to_dict()
    request.pop("performance_scale")
    request["countries"][0]["overrides"] = {
        "n_households": 91,
        "n_firms_c": 14,
        "n_firms_k": 5,
        "n_firms_e": 3,
        "n_builders": 6,
        "n_banks": 3,
        "demographics_population": 91,
    }

    spec = NewGameSpec.from_mapping(request)
    config = spec.configs()[0]

    assert spec.performance_scale == "fast"
    assert (
        config.n_households,
        config.n_firms_c,
        config.n_firms_k,
        config.n_firms_e,
        config.n_builders,
        config.n_banks,
        config.demographics_population,
    ) == (91, 14, 5, 3, 6, 3, 91)


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
        and item.name not in {"job_guarantee"}
    ] == []
    assert playable.job_guarantee is False
    assert playable.alpha1 == pytest.approx(0.97)
    assert playable.gov_consumption_share == pytest.approx(0.20)
    assert playable.tax_income_rate == pytest.approx(0.25)
    assert playable.pension_replacement == pytest.approx(0.20)
    assert playable.benefit_income_floor == 0.0
    assert playable.p_firm0 == pytest.approx(0.80)
    assert playable.switch_retool_loss == pytest.approx(0.05)


def test_representative_entities_preserve_population_scaled_genesis_capacity() -> None:
    raw = NewGameSpec.default().to_dict()
    raw["countries"] = raw["countries"][:1]
    raw["countries"][0]["overrides"] = {
        "demographics_population": 1_000,
        "n_households": 1_000,
        "n_firms_c": 15,
        "n_firms_k": 5,
        "n_firms_e": 3,
        "n_builders": 6,
        "n_banks": 2,
    }
    spec = NewGameSpec.from_mapping(raw)
    cfg = replace(spec.configs()[0], rho=0.73)
    economy = build_world_spec_from_configs([cfg]).economies[0]
    real = (
        economy.domestic_economy.financial_economy
        .monetary_economy.real_economy
    )

    assert real.rules.initial_firm_money == pytest.approx(
        cfg.d_firm0 * 4.0
    )
    assert real.rules.initial_consumption_capital == pytest.approx(
        cfg.K_firm0 * 4.0
    )
    assert real.rules.capital_output_ratio == pytest.approx(cfg.v)
    assert real.rules.dividend_payout == pytest.approx(0.73)
    assert real.rules.initial_expected_demand == pytest.approx(
        cfg.demand_e_firm0 * 4.0
    )
    assert economy.energy_rules.initial_producer_cash == pytest.approx(
        cfg.d_efirm0 * (10.0 / 3.0)
    )
    assert economy.housing_rules.initial_builder_cash_buffer == pytest.approx(
        25.0 * (25.0 / 6.0)
    )
    private_opening_money = (
        400 * real.rules.initial_household_money
        + 20 * real.rules.initial_firm_money
        + 3 * economy.energy_rules.initial_producer_cash
        + 6 * economy.housing_rules.initial_builder_cash_buffer
    )
    monetary = (
        economy.domestic_economy.financial_economy.monetary_economy
    )
    assert monetary.rules.opening_capital_per_bank == pytest.approx(
        (
            cfg.d_bank0
            + cfg.bank_capital_frac * private_opening_money
        ) / 2
    )


def test_config_experiment_bridge_routes_security_targets_and_switches() -> None:
    baseline = NewGameSpec.default().configs()[0]
    config = apply_config_treatment(
        [baseline],
        field="per_firm_equity",
        value=False,
    )[0]
    config = replace(
        config,
        bond_theta=0.19,
        theta_equity=0.37,
    )
    economy = build_world_spec_from_configs([config]).economies[0]
    financial = economy.domestic_economy.financial_economy

    assert financial.policy.household_bond_target == pytest.approx(0.19)
    assert financial.rules.household_equity_target == pytest.approx(0.37)
    assert financial.rules.firm_equity is False

    without_capital_market_config = apply_config_treatment(
        [baseline], field="capital_market", value=False
    )[0]
    without_capital_market = build_world_spec_from_configs(
        [without_capital_market_config]
    ).economies[0].domestic_economy.financial_economy
    assert without_capital_market.rules.firm_equity is False
    assert without_capital_market.rules.bank_equity is False
    assert without_capital_market.rules.bank_equity_trading is False
    assert without_capital_market.rules.equity_finance is False
    assert without_capital_market.rules.margin_credit is False


def test_config_bridge_recognizes_canonical_by_size_bank_assignment() -> None:
    baseline = NewGameSpec.default().configs()[0]
    economy = build_world_spec_from_configs(
        [replace(baseline, bank_assignment="by_size")]
    ).economies[0]
    monetary = economy.domestic_economy.financial_economy.monetary_economy

    assert monetary.rules.assign_banks_by_size is True


def test_config_experiment_bridge_matches_bank_disable_cascade() -> None:
    config = apply_config_treatment(
        [NewGameSpec.default().configs()[0]],
        field="bank_enabled",
        value=False,
    )[0]
    economy = build_world_spec_from_configs([config]).economies[0]
    financial = economy.domestic_economy.financial_economy
    monetary = financial.monetary_economy

    assert monetary.rules.household_credit is False
    assert monetary.rules.interbank is False
    assert monetary.rules.rate_competition is False
    assert monetary.rules.relationship_lock_in is False
    assert financial.rules.bank_equity is False
    assert financial.rules.bank_equity_trading is False
    assert financial.rules.bank_dynamics is False


def test_firm_dynamics_disable_cascade_is_valid_and_explicit() -> None:
    config = apply_config_treatment(
        [NewGameSpec.default().configs()[0]],
        field="firm_dynamics",
        value=False,
    )[0]
    assert config.firm_dynamics is False
    assert config.per_firm_equity is False
    assert config.equity_finance is False
    assert config.margin_credit is False


def test_labor_capability_disable_cascades_are_valid_and_explicit() -> None:
    baseline = NewGameSpec.default().configs()[0]
    without_fractional_hours = apply_config_treatment(
        [baseline], field="labor_fractional_hours", value=False
    )[0]
    assert without_fractional_hours.labor_second_job is False

    without_relationship_wages = apply_config_treatment(
        [baseline], field="labor_relationship_wages", value=False
    )[0]
    assert without_relationship_wages.labor_job_ladder is False


def test_demography_disable_cascade_closes_lifecycle_events() -> None:
    config = apply_config_treatment(
        [NewGameSpec.default().configs()[0]],
        field="demographics_enabled",
        value=False,
    )[0]
    assert config.demographic_lifecycle_consumption is False
    assert config.demographic_marriage_enabled is False
    assert config.demographic_divorce_enabled is False
    assert config.demographic_adult_leaving_home_enabled is False


def test_config_experiment_bridge_routes_complete_world_rules() -> None:
    configs = NewGameSpec.default(seed=53).configs()[:2]
    world = build_world_spec_from_configs(
        configs,
        world_overrides={
            "trade": True,
            "capital": True,
            "migration": True,
            "fx_lambda": 0.07,
            "fx_friction": 0.02,
            "fx_spread": 0.004,
            "fx_loss_mutualization": True,
            "fx_trade_cap": 0.11,
            "capital_mobility": 0.08,
            "capital_adjust": 0.09,
            "migration_rate": 0.015,
            "migration_max_share": 0.20,
            "remittance_share": 0.25,
            "wage_smoothing": 0.03,
            "peg_reserves0": 6_000.0,
        },
    )

    assert world.rules.trade is True
    assert world.rules.capital is True
    assert world.rules.migration is True
    assert world.rules.fx_adjustment == pytest.approx(0.07)
    assert world.rules.fx_friction == pytest.approx(0.02)
    assert world.rules.fx_spread == pytest.approx(0.004)
    assert world.rules.fx_loss_mutualization is True
    assert world.rules.fx_trade_cap == pytest.approx(0.11)
    assert world.rules.capital_mobility == pytest.approx(0.08)
    assert world.rules.capital_adjustment == pytest.approx(0.09)
    assert world.rules.migration_rate == pytest.approx(0.015)
    assert world.rules.migration_max_share == pytest.approx(0.20)
    assert world.rules.remittance_share == pytest.approx(0.25)
    assert world.rules.wage_smoothing == pytest.approx(0.03)
    assert world.rules.initial_peg_reserves == pytest.approx(6_000.0)


def test_native_treatment_overlay_preserves_computed_bridge_semantics() -> None:
    baseline = population_scaled_new_game(
        population=1_000, days=30, seed=59
    )
    control = build_native_new_game_spec(baseline)
    base_config = baseline.configs()[0]
    base_economy = control.economies[0]
    base_population = base_economy.domestic_economy
    base_financial = base_population.financial_economy
    base_monetary = base_financial.monetary_economy
    base_real = base_monetary.real_economy
    private_opening_money = (
        base_real.households * base_real.rules.initial_household_money
        + (base_real.consumption_firms + base_real.capital_firms)
        * base_real.rules.initial_firm_money
        + base_economy.energy_rules.producer_count
        * base_economy.energy_rules.initial_producer_cash
        + base_economy.housing_rules.builder_count
        * base_economy.housing_rules.initial_builder_cash_buffer
    )

    capital_fraction = base_config.bank_capital_frac + 0.01
    capital_treatment = native_treatment_spec(
        baseline, field="bank_capital_frac", value=capital_fraction
    )
    capital_rules = (
        capital_treatment.economies[0]
        .domestic_economy.financial_economy.monetary_economy.rules
    )
    assert capital_rules.opening_capital_per_bank == pytest.approx(
        base_monetary.rules.opening_capital_per_bank
        + 0.01 * private_opening_money / base_monetary.rules.bank_count
    )

    opening_capital_treatment = native_treatment_spec(
        baseline, field="K_firm0", value=base_config.K_firm0 * 1.2
    )
    treated_real = (
        opening_capital_treatment.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy
    )
    assert treated_real.rules.initial_consumption_capital == pytest.approx(
        base_real.rules.initial_consumption_capital * 1.2
    )

    energy_share_treatment = native_treatment_spec(
        baseline, field="energy_hh_share", value=0.12
    )
    treated_energy = energy_share_treatment.economies[0].energy_rules
    assert treated_energy.household_need == pytest.approx(
        0.12 * treated_energy.initial_wage / treated_energy.initial_price
    )

    appetite_treatment = native_treatment_spec(
        baseline, field="bank_bond_appetite", value=0.23
    )
    assert (
        appetite_treatment.economies[0]
        .domestic_economy.financial_economy.policy.bank_bond_appetite
        == pytest.approx(0.23)
    )

    mortality_treatment = native_treatment_spec(
        baseline, field="demographics_mortality_scale", value=1.25
    )
    treated_vital = mortality_treatment.economies[0].domestic_economy.rules.vital_rates
    base_vital = base_population.rules.vital_rates
    mortality_ratio = 1.25 / base_config.demographics_mortality_scale
    assert treated_vital.makeham_a == pytest.approx(
        base_vital.makeham_a * mortality_ratio
    )
    assert treated_vital.gompertz_b == pytest.approx(
        base_vital.gompertz_b * mortality_ratio
    )

    date_treatment = native_treatment_spec(
        baseline, field="simulation_start_date", value="2024-02-29"
    )
    assert (
        date_treatment.economies[0].domestic_economy.population.start_calendar_day
        == date(2024, 2, 29).toordinal()
    )

    government_treatment = native_treatment_spec(
        baseline, field="government", value=False
    )
    government_real = (
        government_treatment.economies[0]
        .domestic_economy.financial_economy.monetary_economy.real_economy
    )
    assert government_real.requested_capabilities & (1 << 1) == 0
    assert (
        government_treatment.economies[0]
        .domestic_economy.financial_economy.rules.bonds
        is False
    )


def test_native_product_baseline_audit_covers_every_mapped_field() -> None:
    payload = build_native_baseline_audit(
        population=1_000, seed=61, countries=2
    )
    assert payload["field_count"] == 226
    assert payload["status_counts"].get("projection_missing", 0) == 0
    assert payload["status_counts"].get("product_baseline_divergence", 0) == 0
    rows = {row["field_name"]: row for row in payload["rows"]}
    assert rows["K_firm0"]["status"] == "density_scaled"
    assert rows["theta_equity"]["status"] == "exact"
    assert rows["marriage_assortativity"]["status"] == "exact"


def test_new_game_constructs_selected_profiles_world_and_player() -> None:
    raw = _automatic_spec()
    raw["world"]["trade"] = False
    raw["world"]["migration"] = False
    raw["countries"] = [
        {"name": "Port Republic", "code": "PRT", "profile": "entrepot", "overrides": {}},
        {
            "name": "Resource Republic",
            "code": "RES",
            "profile": "petrostate",
            "overrides": {"n_firms_c": 7, "a": 1.4},
        },
    ]
    raw["player_country"] = 1

    runtime = SimulationRuntime(seed=1)
    snapshot = runtime.reset(spec=raw)

    assert snapshot["protocol_version"] == PROTOCOL_VERSION == 4
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
        "labor_social": "null",
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
        for seat in ("labor_social", "regulator", "external_affairs", "energy")
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
        "labor_social": "labor_social",
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
