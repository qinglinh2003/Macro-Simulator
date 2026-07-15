from __future__ import annotations

import json

import pytest

from macro_sim.config import Config
from macro_sim.diagnostics.analysis import detect_run_problems, summarize_run
from macro_sim.diagnostics.models import Finding, Intervention, RunOutcome, RunSpec
from macro_sim.diagnostics.probes import DeepProbeCollector
from macro_sim.diagnostics.runner import (
    HARD_PROBE_KEYS,
    HARD_RECORD_KEYS,
    NATIONAL_ACCOUNTS_RECORD_KEYS,
    _aggregate_issues,
    _ablation_attribution,
    _git_provenance,
    _paired_responses,
    _run_one,
    _stable_digest,
    _validate_run_data,
    _validate_suite_specs,
)
from macro_sim.diagnostics.scenarios import (
    build_frontier_config,
    diagnostic_intervention_window,
    diagnostic_matrix,
    root_cause_matrix,
)
from macro_sim.diagnostics.static_audit import run_static_audit
from macro_sim.economy import Economy


def _spec(**overrides) -> RunSpec:
    values = dict(
        name="test", seed=0, ticks=3, population=40,
        n_firms_c=4, n_firms_k=2, n_banks=1,
    )
    values.update(overrides)
    return RunSpec(**values)


def test_static_audit_surfaces_confirmed_coupling_defects():
    issue_ids = {finding.issue_id for finding in run_static_audit()}
    assert "diagnostics.metrics_not_pure" not in issue_ids
    assert "planning.c_sector_unmet_demand_blind" not in issue_ids
    assert "monetary.direct_demand_channels_missing" not in issue_ids
    assert "pricing.capital_service_cost_missing" not in issue_ids
    assert "accounting.firm_assets_mix_physical_and_nominal" not in issue_ids
    assert "accounting.firm_profit_is_ebitda" not in issue_ids
    assert "accounting.bank_profit_is_gross_interest" not in issue_ids
    assert "banking.interbank_principal_missing" not in issue_ids
    assert "central_bank.omo_counterasset_missing" not in issue_ids
    assert "housing.mortgage_bypasses_underwriting" not in issue_ids
    assert "banking.credit_capital_envelopes_double_count" not in issue_ids
    assert "banking.margin_credit_bypasses_capacity" not in issue_ids
    assert "world.cross_border_settlement_after_domestic_commit" not in issue_ids
    assert "world.exports_unbacked_by_goods" not in issue_ids
    assert "world.trade_disabled_by_consumption_strata" not in issue_ids
    assert "finance.loan_contract_vintages_missing" in issue_ids
    assert "banking.deposit_funding_cost_missing" in issue_ids
    assert "credit.collateral_recovery_missing" in issue_ids
    assert "housing.typed_household_debt_missing" in issue_ids
    assert "accounting.inventory_cogs_matching_missing" in issue_ids


def test_deep_probe_is_an_immutable_read_of_economy_state():
    econ = Economy(Config.v13(
        seed=2, n_ticks=2, n_households=20, demographics_population=40,
        n_firms_c=4, n_firms_k=2, n_banks=1,
    ))
    rec = econ.step()
    before = (
        econ.rng.getstate(), econ._prev_inflation, econ._prev_u,
        econ._prev_nominal_output, econ._price_level,
        tuple(sorted(econ.ledger.snapshot().items())),
    )
    probe = DeepProbeCollector().collect(econ, rec)
    after = (
        econ.rng.getstate(), econ._prev_inflation, econ._prev_u,
        econ._prev_nominal_output, econ._price_level,
        tuple(sorted(econ.ledger.snapshot().items())),
    )
    assert before == after
    assert probe["reported_nominal_output"] == rec["nominal_output"]
    expected_final_demand = (
        sum(h.spent for h in econ.households)
        + float(getattr(econ, "_gov_consumption", 0.0))
        + float(getattr(econ, "_jg_spending", 0.0))
        + float(rec.get("investment_spending", 0.0))
        + float(getattr(econ, "_energy_hh_spend", 0.0))
        + probe["housing_construction_output_proxy"]
        + probe["market_rent_flow"]
        + probe["imputed_owner_rent_proxy"]
        + probe["net_product_taxes_proxy"]
        + probe["inventory_change_value"]
    )
    assert probe["final_demand_proxy"] == pytest.approx(expected_final_demand)


def test_energy_probe_exposes_order_classes_capacity_and_investment():
    econ = Economy(Config.v13(
        seed=3, n_ticks=1, n_households=20, demographics_population=40,
        n_firms_c=4, n_firms_k=2, n_firms_e=2, n_banks=1,
        energy_enabled=True, energy_household=True,
    ))
    record = econ.step()
    probe = DeepProbeCollector().collect(econ, record)

    assert probe["energy_orders_total"] == pytest.approx(
        probe["energy_firm_orders"]
        + probe["energy_household_orders"]
        + probe["energy_public_orders"]
    )
    assert probe["energy_capacity_units"] > 0.0
    assert probe["energy_expected_demand"] > 0.0
    assert probe["energy_investment_target_units"] >= probe["energy_investment_units"]


def test_default_matrix_uses_ten_independent_jobs_and_paired_twins():
    specs = diagnostic_matrix(
        ticks=100, population=200, n_firms_c=20, n_firms_k=10, n_banks=2, seeds=5,
    )
    assert len(specs) == 10
    assert len({spec.name for spec in specs}) == 10
    baselines = {spec.pair_id for spec in specs if spec.scenario == "baseline"}
    assert all(spec.pair_id in baselines for spec in specs)
    start, end = diagnostic_intervention_window(90)
    assert start >= end - start
    assert 90 - end >= end - start


def test_causal_matrix_replicates_every_intervention_across_first_seeds():
    specs = diagnostic_matrix(
        ticks=100, population=200, n_firms_c=20, n_firms_k=10, n_banks=2,
        seeds=5, intervention_replicates=3,
    )
    assert len(specs) == 20
    assert len({spec.name for spec in specs}) == 20
    assert {spec.seed for spec in specs if spec.scenario == "baseline"} == set(range(5))
    scenarios = {
        "rate_cut", "rate_hike", "energy_shock", "credit_tightening", "fiscal_expansion",
    }
    for scenario in scenarios:
        arms = [spec for spec in specs if spec.scenario == scenario]
        assert {spec.seed for spec in arms} == {0, 1, 2}
        assert all(spec.pair_id == f"seed-{spec.seed}" for spec in arms)


@pytest.mark.parametrize("replicates", [0, 6])
def test_causal_matrix_rejects_invalid_intervention_replication(replicates):
    with pytest.raises(ValueError, match="intervention_replicates"):
        diagnostic_matrix(
            ticks=100, population=200, n_firms_c=20, n_firms_k=10, n_banks=2,
            seeds=5, intervention_replicates=replicates,
        )


def test_root_cause_matrix_fills_ten_workers_with_named_mechanism_bundle_ablations():
    specs = root_cause_matrix(
        ticks=30, population=40, n_firms_c=4, n_firms_k=2, n_banks=1, seed=7,
    )
    assert len(specs) == 10
    assert len({spec.name for spec in specs}) == 10
    assert specs[0].scenario == "ablation:reference"
    assert all(spec.seed == 7 and spec.intervention is None for spec in specs)
    assert all(build_frontier_config(spec).n_ticks == 30 for spec in specs)
    assert all(build_frontier_config(spec).national_accounts_metrics for spec in specs)
    assert all(build_frontier_config(spec).cb_uses_fixed_basket_cpi for spec in specs)
    assert all(
        build_frontier_config(spec).fiscal_uses_national_accounts_gdp for spec in specs
    )
    no_bank_cap = next(spec for spec in specs if spec.scenario == "ablation:no_bank_capital_cap")
    no_bank_cap_cfg = build_frontier_config(no_bank_cap)
    assert no_bank_cap_cfg.bank_capital_constraint is False
    assert no_bank_cap_cfg.unified_bank_rwa is False
    assert no_bank_cap_cfg.mortgage_underwriting is True
    assert no_bank_cap_cfg.mortgage_min_capital_ratio == pytest.approx(1.0e-12)


def test_frontier_diagnostics_prefer_v23_accounts_without_reflagging_legacy_caveats():
    spec = _spec(ticks=4)
    records = [
        {
            "t": tick,
            "genesis_money": 100.0,
            "conservation_drift": 0.0,
            "national_accounts_enabled": 1.0,
            "nominal_gdp": 100.0 + tick,
            "real_gdp": 50.0 + tick,
            "real_gdp_per_capita": 1.0 + 0.1 * tick,
            "cpi_fixed_basket": 1.0 + 0.01 * tick,
            "cpi_fixed_basket_inflation_yoy": 0.0,
        }
        for tick in range(4)
    ]
    probes = [
        {
            "nonfinite_official_values": 0.0,
            "min_inventory": 0.0,
            "min_capital": 0.0,
            "reported_nominal_output": 1.0,
            "final_demand_proxy": 100.0,
            "composition_log_change": 0.10,
            "unit_value_log_change": 0.10,
        }
        for _ in range(4)
    ]

    issue_ids = {finding.issue_id for finding in detect_run_problems(records, probes, spec)}
    assert "measurement.gdp_scope_mismatch" not in issue_ids
    assert "measurement.price_composition" not in issue_ids
    summary = summarize_run(records, probes, spec)
    assert summary["national_accounts_basis"] == "v23"
    assert summary["tail"]["real_gdp"]["mean"] == pytest.approx(52.5)
    assert summary["annualized_price_level_growth"] > 0.0


def test_reconciled_full_firm_pnl_is_not_reflagged_as_ebitda():
    spec = _spec(ticks=2)
    records = [
        {"t": tick, "genesis_money": 100.0, "conservation_drift": 0.0}
        for tick in range(2)
    ]
    probes = [
        {
            "nonfinite_official_values": 0.0,
            "min_inventory": 0.0,
            "min_capital": 0.0,
            "firm_full_pnl_enabled": 1.0,
            "reported_firm_profit": 10.0,
            "capital_depreciation_value_proxy": 100.0,
            "firm_interest_due_proxy": 100.0,
            "firm_pnl_revenue": 100.0,
            "firm_pnl_bridge_max_abs_residual": 0.0,
            "firm_pnl_interest_cash_counter_residual": 0.0,
            "firm_bank_interest_counterparty_residual": 0.0,
        }
        for _ in range(2)
    ]

    issue_ids = {finding.issue_id for finding in detect_run_problems(records, probes, spec)}
    assert "accounting.firm_pnl_omits_capital_cost" not in issue_ids
    assert "accounting.firm_pnl_bridge_broken" not in issue_ids


def test_national_accounts_detector_separates_identity_from_scope_residuals():
    spec = _spec(ticks=2)
    records = []
    for tick in range(2):
        records.append({
            "t": tick,
            "genesis_money": 100.0,
            "conservation_drift": 0.0,
            "national_accounts_enabled": 1.0,
            "nominal_gdp": 100.0,
            "real_gdp": 80.0,
            "gdp_nominal_production": 100.0,
            "gdp_nominal_expenditure_reconciled": 100.0,
            "gdp_nominal_income_reconciled": 100.0,
            "gdp_real_production": 80.0,
            "gdp_real_expenditure_reconciled": 80.0,
            # A large cash-basis income gap is explained by the explicit accrual
            # bridge and is not an unknown scope residual.
            "gdp_nominal_expenditure_reconciliation_residual": 0.0,
            "gdp_nominal_income_reconciliation_residual": 20.0,
            "gdp_nominal_expenditure_residual_share": 0.0,
            "gdp_nominal_income_residual_share": 0.20,
            "gdp_nominal_income_accrual_bridge": 20.0,
            "gdp_nominal_income_accrual_bridge_share": 0.20,
            "gdp_nominal_income_accrued_observed": 100.0,
            "gdp_nominal_income_unexplained_residual": 0.0,
            "gdp_nominal_income_unexplained_residual_share": 0.0,
            "gdp_real_expenditure_residual_share": 0.0,
            "gdp_nominal_three_approach_raw_spread_share": 0.40,
        })
    probes = [
        {"nonfinite_official_values": 0.0, "min_inventory": 0.0, "min_capital": 0.0}
        for _ in range(2)
    ]

    issue_ids = {finding.issue_id for finding in detect_run_problems(records, probes, spec)}
    assert "accounting.national_accounts_reconciliation_drift" not in issue_ids
    assert "accounting.national_accounts_material_scope_residual" not in issue_ids
    summary = summarize_run(records, probes, spec)
    assert summary["tail"]["gdp_nominal_income_accrual_bridge"]["mean"] == 20.0

    records[1]["gdp_nominal_income_accrued_observed"] = 80.0
    records[1]["gdp_nominal_income_unexplained_residual"] = 20.0
    records[1]["gdp_nominal_income_unexplained_residual_share"] = 0.20
    issue_ids = {finding.issue_id for finding in detect_run_problems(records, probes, spec)}
    assert "accounting.national_accounts_material_scope_residual" in issue_ids

    records[1]["gdp_nominal_income_reconciled"] = 90.0
    issue_ids = {finding.issue_id for finding in detect_run_problems(records, probes, spec)}
    assert "accounting.national_accounts_reconciliation_drift" in issue_ids


def test_national_accounts_detector_catches_large_intermittent_scope_residual():
    spec = _spec(ticks=20)
    records = []
    for tick in range(20):
        spike = 0.50 if tick == 19 else 0.0
        records.append({
            "t": tick,
            "genesis_money": 100.0,
            "conservation_drift": 0.0,
            "national_accounts_enabled": 1.0,
            "nominal_gdp": 100.0,
            "real_gdp": 80.0,
            "gdp_nominal_production": 100.0,
            "gdp_nominal_expenditure_reconciled": 100.0,
            "gdp_nominal_income_reconciled": 100.0,
            "gdp_real_production": 80.0,
            "gdp_real_expenditure_reconciled": 80.0,
            "gdp_nominal_expenditure_residual_share": 0.0,
            "gdp_nominal_income_residual_share": 0.0,
            "gdp_nominal_income_accrual_bridge": 0.0,
            "gdp_nominal_income_accrual_bridge_share": 0.0,
            "gdp_nominal_income_accrued_observed": 100.0 - 100.0 * spike,
            "gdp_nominal_income_unexplained_residual": 100.0 * spike,
            "gdp_nominal_income_unexplained_residual_share": spike,
            "gdp_real_expenditure_residual_share": 0.0,
            "gdp_nominal_three_approach_raw_spread_share": spike,
        })
    probes = [
        {"nonfinite_official_values": 0.0, "min_inventory": 0.0, "min_capital": 0.0}
        for _ in records
    ]

    findings = detect_run_problems(records, probes, spec)
    finding = next(
        item for item in findings
        if item.issue_id == "accounting.national_accounts_material_scope_residual"
    )
    assert finding.evidence["tail_median_residual_shares"][
        "nominal_income_unexplained"
    ] == 0.0
    assert finding.evidence["tail_max_residual_shares"][
        "nominal_income_unexplained"
    ] == 0.50


def test_fixed_cpi_yoy_is_not_diagnosed_before_a_full_year_is_observed():
    spec = _spec(ticks=4)

    def records(observed: float) -> list[dict[str, float]]:
        return [{
            "t": float(tick),
            "genesis_money": 100.0,
            "conservation_drift": 0.0,
            "national_accounts_enabled": 1.0,
            "cpi_fixed_basket_inflation_yoy": 0.50,
            "cpi_fixed_basket_inflation_yoy_observed": observed,
        } for tick in range(4)]

    probes = [
        {"nonfinite_official_values": 0.0, "min_inventory": 0.0, "min_capital": 0.0}
        for _ in range(4)
    ]
    unobserved_ids = {
        finding.issue_id for finding in detect_run_problems(records(0.0), probes, spec)
    }
    observed_ids = {
        finding.issue_id for finding in detect_run_problems(records(1.0), probes, spec)
    }
    assert "macro.persistent_price_instability" not in unobserved_ids
    assert "macro.persistent_price_instability" in observed_ids


def test_worker_persists_full_artifact(tmp_path):
    outcome = _run_one(_spec(), str(tmp_path))
    assert outcome.error is None
    run_dir = tmp_path / "runs" / "test"
    assert (run_dir / "series.csv").exists()
    assert (run_dir / "probes.csv").exists()
    assert json.loads((run_dir / "summary.json").read_text())["n_ticks"] == 3


def test_detector_flags_nonfinite_and_conservation_failures():
    spec = _spec(ticks=2)
    records = [
        {"t": 0, "genesis_money": 100.0, "conservation_drift": 0.0},
        {"t": 1, "genesis_money": 100.0, "conservation_drift": 1.0},
    ]
    probes = [
        {"nonfinite_official_values": 0.0, "min_inventory": 0.0, "min_capital": 0.0},
        {"nonfinite_official_values": 1.0, "min_inventory": 0.0, "min_capital": 0.0},
    ]
    issue_ids = {finding.issue_id for finding in detect_run_problems(records, probes, spec)}
    assert "validity.nonfinite_metrics" in issue_ids
    assert "accounting.a5_drift" in issue_ids


@pytest.mark.parametrize("n_k", [1, 2, 5])
def test_detector_attributes_persistent_sub_half_worker_k_deadlock(n_k):
    spec = _spec(ticks=2)
    records = [
        {
            "t": tick, "genesis_money": 100.0, "conservation_drift": 0.0,
            "investment_target_units": 1.0, "investment_realization_rate": 0.0,
        }
        for tick in range(2)
    ]
    probes = [
        {
            "nonfinite_official_values": 0.0, "min_inventory": 0.0,
            "min_capital": 0.0, "k_output_units": 0.0,
            "k_inventory_units": 0.0, "k_firm_count": float(n_k),
            "persistent_labor_matching": 1.0,
            "labor_fractional_hours": 0.0,
            "k_labor_demand_total": 0.4,
            "k_labor_demand_max": 0.4 / n_k, "k_active_worker_heads": 0.0,
            "k_firms_above_half_worker_gap": 0.0,
        }
        for _ in range(2)
    ]
    issue_ids = {finding.issue_id for finding in detect_run_problems(records, probes, spec)}
    assert "labor.whole_person_k_sector_deadlock" in issue_ids


@pytest.mark.parametrize(("persistent", "fractional"), [(0.0, 0.0), (1.0, 1.0)])
def test_detector_only_applies_whole_person_edge_to_nonfractional_persistent_labor(
    persistent, fractional,
):
    spec = _spec(ticks=2)
    records = [
        {
            "t": tick, "genesis_money": 100.0, "conservation_drift": 0.0,
            "investment_target_units": 1.0, "investment_realization_rate": 0.0,
        }
        for tick in range(2)
    ]
    probes = [
        {
            "nonfinite_official_values": 0.0, "min_inventory": 0.0,
            "min_capital": 0.0, "k_output_units": 0.0,
            "k_inventory_units": 0.0, "k_firm_count": 1.0,
            "persistent_labor_matching": persistent,
            "labor_fractional_hours": fractional,
            "k_labor_demand_total": 0.4, "k_labor_demand_max": 0.4,
            "k_active_worker_heads": 0.0, "k_firms_above_half_worker_gap": 0.0,
        }
        for _ in range(2)
    ]
    issue_ids = {finding.issue_id for finding in detect_run_problems(records, probes, spec)}
    assert "labor.whole_person_k_sector_deadlock" not in issue_ids


def test_detector_separates_job_guarantee_from_open_unemployment():
    spec = _spec(ticks=2)
    records = [
        {
            "t": tick, "genesis_money": 100.0, "conservation_drift": 0.0,
            "person_unemployment_rate": 0.25, "effective_unemployment": 0.0,
            "jg_employment_rate": 0.25,
        }
        for tick in range(2)
    ]
    probes = [
        {"nonfinite_official_values": 0.0, "min_inventory": 0.0, "min_capital": 0.0}
        for _ in range(2)
    ]
    issue_ids = {finding.issue_id for finding in detect_run_problems(records, probes, spec)}
    assert "labor.chronic_slack" not in issue_ids
    assert "labor.large_job_guarantee_buffer" in issue_ids


def test_detector_flags_fractional_single_job_hours_stranded_beside_vacancies():
    spec = _spec(ticks=2)
    records = [
        {
            "t": tick, "genesis_money": 100.0, "conservation_drift": 0.0,
            "person_labor_supply": 100.0, "labor_underemployment_hours": 8.0,
            "labor_underemployed_heads": 16.0, "labor_vacancies": 30.0,
        }
        for tick in range(2)
    ]
    probes = [
        {
            "nonfinite_official_values": 0.0, "min_inventory": 0.0,
            "min_capital": 0.0, "labor_fractional_hours": 1.0,
        }
        for _ in range(2)
    ]

    issue_ids = {finding.issue_id for finding in detect_run_problems(records, probes, spec)}
    assert "labor.fractional_single_job_fragmentation" in issue_ids


def test_paired_experiment_reports_first_stage_and_inactive_credit_channel():
    def windows(kappa: float) -> dict:
        return {
            "bounds": {"pre": [0, 1], "during": [1, 2], "post": [2, 3]},
            "credit_kappa": {"pre": 10.0, "during": kappa, "post": 10.0},
            "new_loans": {"pre": 0.0, "during": 0.0, "post": 0.0},
            "credit_requested_proxy": {"pre": 0.0, "during": 0.0, "post": 0.0},
            "firm_interest_due_proxy": {"pre": 0.0, "during": 0.0, "post": 0.0},
            "firm_credit_leverage_shortfall": {"pre": 0.0, "during": 0.0, "post": 0.0},
            "firm_credit_leverage_constrained_share": {"pre": 0.0, "during": 0.0, "post": 0.0},
            "firm_credit_bank_shortfall": {"pre": 0.0, "during": 0.0, "post": 0.0},
        }

    base_spec = _spec(name="base", scenario="baseline", pair_id="p")
    arm_spec = _spec(
        name="tight", scenario="credit_tightening", pair_id="p",
        intervention=Intervention("kappa_multiplier", 1, 2, 0.5),
    )
    outcomes = [
        RunOutcome(base_spec, "base", 0.0, {
            "response_windows": windows(10.0),
            "causal_provenance": {
                "structural_signature": "same", "pre_intervention_digest": "same",
            },
        }, ()),
        RunOutcome(arm_spec, "tight", 0.0, {
            "response_windows": windows(5.0),
            "causal_provenance": {
                "structural_signature": "same", "pre_intervention_digest": "same",
            },
        }, ()),
    ]
    responses = _paired_responses(outcomes)
    assert responses[0]["causal_validity"]["identified"] is True
    assert responses[0]["first_stage"]["passed"] is True
    assert "post_difference_in_differences" in responses[0]
    assert responses[0]["replication"]["evidence_status"] == "exploratory_single_seed"
    issue = next(
        item for item in _aggregate_issues(outcomes, (), responses)
        if item["issue_id"] == "credit.leverage_cap_nonbinding"
    )
    assert issue["measurement_status"] == "exploratory_single_seed"
    assert issue["confidence"] == "medium"


def _credit_replication_outcomes(proximal_dids: list[float]) -> list[RunOutcome]:
    def windows(kappa: float, proximal: float) -> dict:
        return {
            "bounds": {"pre": [0, 1], "during": [1, 2], "post": [2, 3]},
            "credit_kappa": {"pre": 10.0, "during": kappa, "post": 10.0},
            "new_loans": {"pre": 0.0, "during": proximal, "post": 0.0},
            "firm_credit_leverage_shortfall": {
                "pre": 0.0, "during": 0.0, "post": 0.0,
            },
            "firm_credit_leverage_constrained_share": {
                "pre": 0.0, "during": 0.0, "post": 0.0,
            },
            "firm_credit_bank_shortfall": {
                "pre": 0.0, "during": 0.0, "post": 0.0,
            },
        }

    outcomes: list[RunOutcome] = []
    for seed, proximal in enumerate(proximal_dids):
        pair_id = f"credit-pair-{seed}"
        provenance = {
            "structural_signature": f"structural-{seed}",
            "pre_intervention_digest": f"pre-{seed}",
        }
        base_spec = _spec(
            name=f"credit-base-{seed}", seed=seed,
            scenario="baseline", pair_id=pair_id,
        )
        arm_spec = _spec(
            name=f"credit-arm-{seed}", seed=seed,
            scenario="credit_tightening", pair_id=pair_id,
            intervention=Intervention("kappa_multiplier", 1, 2, 0.5),
        )
        outcomes.extend([
            RunOutcome(base_spec, base_spec.name, 0.0, {
                "response_windows": windows(10.0, 0.0),
                "causal_provenance": provenance,
            }, ()),
            RunOutcome(arm_spec, arm_spec.name, 0.0, {
                "response_windows": windows(5.0, proximal),
                "causal_provenance": provenance,
            }, ()),
        ])
    return outcomes


def test_design_replication_does_not_promote_one_nonbinding_pair_over_counterexamples():
    outcomes = _credit_replication_outcomes([0.0, 1.0, -2.0])
    responses = _paired_responses(outcomes)
    replication = responses[0]["replication"]
    metric = replication["effect_evidence_by_metric"]["new_loans"]

    assert replication["n_valid_pairs_for_scenario"] == 3
    assert replication["design_replication_status"] == "design_replicated"
    assert replication["evidence_status"] == "design_replicated"
    assert metric == {
        "n": 3,
        "median": 0.0,
        "positive_count": 1,
        "negative_count": 1,
        "near_zero_count": 1,
        "near_zero_threshold": 1.0e-10,
        "sign_consistency": pytest.approx(1.0 / 3.0),
        "dominant_direction": "positive",
        "consistent_direction": None,
        "effect_evidence_status": "mixed",
    }

    issue = next(
        item for item in _aggregate_issues(outcomes, (), responses)
        if item["issue_id"] == "credit.leverage_cap_nonbinding"
    )
    assert (issue["severity"], issue["confidence"]) == ("medium", "low")
    assert issue["measurement_status"] == "mixed_effect_evidence"
    assert issue["evidence"]["supporting_pair_count"] == 1
    assert issue["evidence"]["counterexample_pair_count"] == 2
    assert issue["evidence"]["effect_evidence_status"] == "mixed"
    assert issue["affected_runs"] == ["credit-arm-0"]
    assert "scenario-level effect is mixed" in issue["claim"]


def test_three_supporting_pairs_promote_nonbinding_claim_as_consistent_effect():
    outcomes = _credit_replication_outcomes([0.0, 0.0, 0.0])
    responses = _paired_responses(outcomes)
    metric = responses[0]["replication"]["effect_evidence_by_metric"]["new_loans"]

    assert metric["n"] == 3
    assert metric["near_zero_count"] == 3
    assert metric["sign_consistency"] == pytest.approx(1.0)
    assert metric["consistent_direction"] == "near_zero"
    assert metric["effect_evidence_status"] == "consistent"

    issue = next(
        item for item in _aggregate_issues(outcomes, (), responses)
        if item["issue_id"] == "credit.leverage_cap_nonbinding"
    )
    assert (issue["severity"], issue["confidence"]) == ("high", "high")
    assert issue["measurement_status"] == "replicated_consistent_effect"
    assert issue["evidence"]["supporting_pair_count"] == 3
    assert issue["evidence"]["counterexample_pair_count"] == 0
    assert issue["evidence"]["claim_replication_status"] == (
        "replicated_consistent_support"
    )


def test_first_stage_rejects_a_treatment_move_in_the_wrong_direction():
    def windows(rate: float) -> dict:
        return {
            "bounds": {"pre": [0, 1], "during": [1, 2], "post": [2, 3]},
            "policy_rate": {"pre": 0.01, "during": rate, "post": 0.01},
        }

    base = _spec(name="base", scenario="baseline", pair_id="p")
    alleged_hike = _spec(
        name="arm", scenario="rate_hike", pair_id="p",
        intervention=Intervention("policy_rate", 1, 2, 0.0),
    )
    provenance = {"structural_signature": "same", "pre_intervention_digest": "same"}
    responses = _paired_responses([
        RunOutcome(base, "base", 0.0, {
            "response_windows": windows(0.01), "causal_provenance": provenance,
        }, ()),
        RunOutcome(alleged_hike, "arm", 0.0, {
            "response_windows": windows(0.005), "causal_provenance": provenance,
        }, ()),
    ])
    assert responses[0]["during_level_difference"]["policy_rate"] < 0.0
    assert responses[0]["first_stage"]["expected_direction"] == "increase"
    assert responses[0]["first_stage"]["passed"] is False
    issue_ids = {item["issue_id"] for item in _aggregate_issues([], (), responses)}
    assert issue_ids == {"experiment.rate_hike.no_first_stage"}


def test_paired_experiment_rejects_pre_treatment_divergence():
    bounds = {"bounds": {"pre": [0, 1], "during": [1, 2], "post": [2, 3]}}
    base = _spec(name="base", scenario="baseline", pair_id="p")
    arm = _spec(
        name="arm", scenario="rate_hike", pair_id="p",
        intervention=Intervention("policy_rate", 1, 2, 0.01),
    )
    outcomes = [
        RunOutcome(base, "base", 0.0, {
            "response_windows": bounds,
            "causal_provenance": {"structural_signature": "same", "pre_intervention_digest": "a"},
        }, ()),
        RunOutcome(arm, "arm", 0.0, {
            "response_windows": bounds,
            "causal_provenance": {"structural_signature": "same", "pre_intervention_digest": "b"},
        }, ()),
    ]
    responses = _paired_responses(outcomes)
    assert responses[0]["causal_validity"]["identified"] is False
    issues = _aggregate_issues(outcomes, (), responses)
    assert {item["issue_id"] for item in issues} == {"experiment.rate_hike.invalid_causal_pair"}


def test_causal_digest_distinguishes_nonfinite_failure_modes():
    assert _stable_digest({"value": float("nan")}) != _stable_digest({"value": float("inf")})
    assert _stable_digest({"value": float("inf")}) != _stable_digest({"value": float("-inf")})


def test_intervention_arm_findings_do_not_become_baseline_defects():
    finding = Finding(
        issue_id="arm.only", severity="high", confidence="confirmed", category="test",
        claim="arm only",
    )
    base = RunOutcome(_spec(name="base", scenario="baseline"), "base", 0.0, {}, ())
    arm = RunOutcome(_spec(name="arm", scenario="rate_hike"), "arm", 0.0, {}, (finding,))
    assert _aggregate_issues([base, arm], (), []) == []


def test_suite_rejects_an_intervention_disguised_as_a_baseline():
    disguised = _spec(
        scenario="baseline",
        intervention=Intervention("policy_rate", 1, 2, 0.0),
    )
    with pytest.raises(ValueError, match="baseline runs cannot carry interventions"):
        _validate_suite_specs([disguised])


def test_schema_gate_fails_closed_on_missing_probe_column():
    spec = _spec(ticks=1)
    records = [{
        "t": 0, "genesis_money": 1.0, "conservation_drift": 0.0,
        "reserve_conservation_drift": 0.0, "shares_conservation_drift": 0.0,
        "real_output": 1.0, "price_index": 1.0, "policy_rate": 0.0,
        "new_loans": 0.0, "effective_unemployment": 0.0,
    }]
    probes = [{
        "t": 0.0, "nonfinite_official_values": 0.0, "min_inventory": 0.0,
        "min_capital": 0.0, "reported_nominal_output": 1.0, "credit_kappa": 1.0,
    }]
    findings = _validate_run_data(records, probes, spec)
    assert [finding.issue_id for finding in findings] == ["validity.diagnostic_data_incomplete"]
    assert "final_demand_proxy" in findings[0].evidence["probes_missing_required_fields"]


@pytest.mark.parametrize(
    "missing_key",
    (
        "gdp_nominal_income_unexplained_residual_share",
        "gdp_nominal_market_price_observed",
        "gdp_nominal_expanded_public_fixed_capital_formation_candidate",
    ),
)
def test_schema_gate_requires_national_accounts_diagnostic_columns(missing_key):
    spec = _spec(ticks=1)
    record = {key: 0.0 for key in HARD_RECORD_KEYS | NATIONAL_ACCOUNTS_RECORD_KEYS}
    probe = {key: 0.0 for key in HARD_PROBE_KEYS}
    record["t"] = 0
    probe["t"] = 0
    record.pop(missing_key)

    findings = _validate_run_data([record], [probe], spec)

    assert [finding.issue_id for finding in findings] == [
        "validity.diagnostic_data_incomplete"
    ]
    assert missing_key in findings[0].evidence[
        "records_missing_required_fields"
    ]


def test_ablation_attribution_reports_same_seed_structural_effect():
    def outcome(name: str, scenario: str, value: float) -> RunOutcome:
        spec = _spec(name=name, scenario=scenario)
        return RunOutcome(spec, name, 0.0, {
            "tail": {"real_output": {"mean": value}}, "probe_tail": {},
            "diagnostic_validity": "passed",
        }, ())

    result = _ablation_attribution([
        outcome("ref", "ablation:reference", 100.0),
        outcome("tfp", "ablation:no_exogenous_tfp", 80.0),
    ])
    assert "mechanism-bundle" in result["method"]
    assert result["design"] == {
        "seed_count": 1,
        "evidence_status": "exploratory_single_seed",
        "causal_scope": "named_mechanism_bundle_not_atomic_mechanism",
        "replication_required_for_effect_claim": True,
        "caveat": (
            "Several arms intentionally switch a coherent bundle of related "
            "features, so their deltas cannot identify one atomic mechanism."
        ),
    }
    effect = result["comparisons"][0]
    assert effect["mechanism_removed"] == "no_exogenous_tfp"
    assert effect["relative_change_from_reference"]["real_output"] == pytest.approx(-0.2)


def test_ablation_attribution_excludes_schema_invalid_runs():
    ref = RunOutcome(_spec(name="ref", scenario="ablation:reference"), "ref", 0.0, {
        "diagnostic_validity": "failed",
    }, ())
    arm = RunOutcome(_spec(name="arm", scenario="ablation:no_exogenous_tfp"), "arm", 0.0, {
        "diagnostic_validity": "passed", "tail": {}, "probe_tail": {},
    }, ())
    assert _ablation_attribution([ref, arm]) == {}


def test_git_provenance_is_repo_rooted_not_caller_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    provenance = _git_provenance()
    assert provenance["revision"] != "unknown"
    assert provenance["source_diff_sha256"]
