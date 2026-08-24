"""Empirical and gameplay freeze for policy causality audit P7.

P7 is a reduction and provenance milestone.  It consumes the frozen P0-P6
contracts and results; it does not run either simulator and it does not repair
an upstream policy, scenario, or performance defect.  The output separates:

* executable Registry domains from recommended UI presets;
* economic explanations from claims about implemented effects;
* model evidence from empirical estimates and model-design priors; and
* qualitative agreement, comparable magnitudes, scope mismatches, and direct
  conflicts.

The empirical source catalog is intentionally small and reviewable.  Sources
are official historical releases, original empirical research, or an explicitly
labelled synthesis.  A source URL is provenance, not an instruction to fetch
mutable network content during acceptance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping

from macro_sim.diagnostics.policy_catalog import METRIC_MATERIALITY, SCENARIOS
from macro_sim.diagnostics.policy_contracts import (
    build_contracts,
    build_inventory,
    build_p0_payload,
    canonical_json,
)


P7_SCHEMA_VERSION = "policy-causality-p7-v1"
P7_SOURCE_REVIEW_DATE = "2026-08-24"
P7_ACCEPTED_UPSTREAM_STATUS = "accepted_with_explicit_defects"
P7_EXPLANATION_FIELDS = ("meaning", "mechanics", "tradeoffs", "watch")


@dataclass(frozen=True, slots=True)
class EmpiricalSource:
    source_id: str
    title: str
    publisher: str
    url: str
    source_class: str
    claim_basis: str
    claim: str
    quantitative_reference: Mapping[str, float | int | str]
    scope_caveat: str
    levers: tuple[str, ...]
    metric_ids: tuple[str, ...]
    reviewed_on: str = P7_SOURCE_REVIEW_DATE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


EMPIRICAL_SOURCES: tuple[EmpiricalSource, ...] = (
    EmpiricalSource(
        "fiscal_multiplier_synthesis",
        "Ten Years after the Financial Crisis: What Have We Learned from the Renaissance in Fiscal Research?",
        "National Bureau of Economic Research",
        "https://www.nber.org/papers/w25531",
        "research_synthesis",
        "evidence_synthesis",
        "Most average spending multipliers reviewed fall between 0.6 and 1; tax-change multipliers mostly fall between -2 and -3.",
        {"spending_multiplier_low": 0.6, "spending_multiplier_high": 1.0,
         "tax_change_multiplier_low": -3.0, "tax_change_multiplier_high": -2.0},
        "A literature synthesis is not a primary estimate and the reported ranges vary by identification, state, horizon, and instrument.",
        ("gov_consumption_share", "gov_investment_share", "tax_income_rate"),
        ("metric.economy.real_output", "metric.source.m4.government_consumption",
         "metric.source.m4.public_fixed_capital_formation", "metric.source.m4.tax_income"),
    ),
    EmpiricalSource(
        "fiscal_state_dependence",
        "Government Spending Multipliers in Good Times and in Bad: Evidence from U.S. Historical Data",
        "National Bureau of Economic Research",
        "https://www.nber.org/papers/w20719",
        "original_empirical_research",
        "empirical_estimate",
        "The study does not find robust evidence that U.S. spending multipliers differ by slack; zero-lower-bound estimates are less conclusive.",
        {},
        "Historical U.S. aggregate estimates do not directly identify this simulator's government-consumption and public-investment rules.",
        ("gov_consumption_share", "gov_investment_share"),
        ("metric.economy.real_output",),
    ),
    EmpiricalSource(
        "narrative_tax_shocks",
        "The Macroeconomic Effects of Tax Changes: Estimates Based on a New Measure of Fiscal Shocks",
        "American Economic Association",
        "https://www.aeaweb.org/articles?id=10.1257/aer.100.3.763",
        "original_empirical_research",
        "empirical_estimate",
        "Narratively identified exogenous tax increases are strongly contractionary for output.",
        {},
        "The paper studies broad legislated U.S. tax changes, not an isolated proportional income-tax rate in this model.",
        ("tax_income_rate", "tax_profit_rate", "tax_consumption_rate"),
        ("metric.economy.real_output", "metric.source.m4.tax_total"),
    ),
    EmpiricalSource(
        "ui_consumption_smoothing",
        "Consumer Spending During Unemployment: Positive and Normative Implications",
        "National Bureau of Economic Research",
        "https://www.nber.org/papers/w25417",
        "original_empirical_research",
        "empirical_estimate",
        "Spending drops sharply when unemployment-insurance benefits expire; duration extensions provide larger consumption-smoothing gains than higher benefit levels in the studied setting.",
        {},
        "The evidence concerns unemployment insurance, while benefit_income_floor is an in-work floor and benefit_replacement is the closer UI analogue.",
        ("benefit_replacement", "benefit_income_floor"),
        ("metric.source.m4.household_consumption", "metric.source.m4.transfer_payments"),
    ),
    EmpiricalSource(
        "minimum_wage_bunching",
        "The Effect of Minimum Wages on Low-Wage Jobs: Evidence from the United States Using a Bunching Estimator",
        "National Bureau of Economic Research",
        "https://www.nber.org/papers/w25434",
        "original_empirical_research",
        "empirical_estimate",
        "Across 138 prominent U.S. state increases, the total number of low-wage jobs was essentially unchanged over five years, with evidence of reduced employment in tradable sectors.",
        {"policy_changes": 138, "follow_up_years": 5},
        "The model expresses its minimum wage relative to a reference wage; dose and labor-market institutions are not directly matched to the state-policy sample.",
        ("min_wage",),
        ("metric.economy.unemployment_rate", "metric.source.m7.mean_hourly_wage"),
    ),
    EmpiricalSource(
        "federal_reserve_lsap",
        "Term Structure Modelling with Supply Factors and the Federal Reserve's Large Scale Asset Purchase Programs",
        "Board of Governors of the Federal Reserve System",
        "https://www.federalreserve.gov/pubs/feds/2012/201237/201237abs.html",
        "central_bank_original_research",
        "empirical_estimate",
        "The first two Federal Reserve large-scale asset-purchase programs and the Maturity Extension Program jointly lowered the 10-year Treasury yield by about 100 basis points in the model estimate.",
        {"combined_ten_year_yield_effect_basis_points": -100.0},
        "The simulator's OMO mechanism reports reserves and flows but not a comparable long-term sovereign yield or purchase-program dose.",
        ("omo", "omo_reserve_target", "omo_drain_frac"),
        ("metric.source.m5.omo_flow", "metric.source.m5.total_reserves"),
    ),
    EmpiricalSource(
        "uk_bank_capital_requirements",
        "Bank capital requirements and balance sheet management practices: has the relationship changed since the crisis?",
        "Bank of England",
        "https://www.bankofengland.co.uk/working-paper/2016/bank-capital-requirements-and-balance-sheet-management-practices-has-the-relationship-changed",
        "central_bank_original_research",
        "empirical_estimate",
        "A one-percentage-point increase in UK bank capital requirements lowered annual loan growth by 8 basis points and risk-weighted-asset growth by 12 basis points in the estimates.",
        {"capital_requirement_change_pp": 1.0, "annual_loan_growth_change_bp": -8.0,
         "annual_rwa_growth_change_bp": -12.0},
        "A target capital ratio is not identical to a regulatory minimum, and the P2 horizon is much shorter than one year.",
        ("bank_target_capital_ratio", "bank_min_capital", "bank_capital_constraint"),
        ("metric.source.m5.new_credit", "metric.source.m5.total_bank_capital"),
    ),
    EmpiricalSource(
        "macroprudential_ltv",
        "The macroeconomic effects of macroprudential policy",
        "Bank for International Settlements",
        "https://www.bis.org/publ/work740.htm",
        "international_organization_original_research",
        "empirical_estimate",
        "Tighter maximum LTV ratios reduce housing credit and house prices; a 10-percentage-point tightening is estimated to reduce output by 1.1 percent over four years, imprecisely and mainly in emerging economies.",
        {"ltv_tightening_pp": 10.0, "four_year_output_change_percent": -1.1},
        "The estimate is heterogeneous and imprecise; the simulator's 30-day binding fixture uses much larger LTV changes.",
        ("mortgage_ltv_cap",),
        ("metric.source.m8.housing.mortgage_originations", "metric.economy.real_output"),
    ),
    EmpiricalSource(
        "us_tariff_pass_through",
        "Economic Impact of Section 232 and 301 Tariffs on U.S. Industries",
        "United States International Trade Commission",
        "https://www.usitc.gov/publications/332/pub5405.pdf",
        "official_retrospective_empirical_analysis",
        "empirical_estimate",
        "U.S. import prices rose about one-for-one with the tariffs; the detailed report estimates roughly a 2 percent fall in covered imports for each 1 percent tariff increase.",
        {"import_price_pass_through_per_1pct_tariff": 1.0,
         "covered_import_change_percent_per_1pct_tariff": -2.0},
        "The estimates cover selected U.S. tariffs and directly affected industries, not an economy-wide uniform tariff or long-run welfare.",
        ("tariff",),
        ("metric.source.m9.country.imports_volume", "metric.source.m9.country.tariff_revenue"),
    ),
    EmpiricalSource(
        "great_recession_output",
        "Why has the initial estimate of real GDP for the fourth quarter of 2008 been revised down so much?",
        "U.S. Bureau of Economic Analysis",
        "https://www.bea.gov/help/faq/1003",
        "official_historical_statistic",
        "official_historical_statistic",
        "The latest cited estimate has U.S. real GDP falling at an 8.9 percent annual rate in 2008 Q4.",
        {"real_gdp_2008q4_annualized_percent": -8.9},
        "One severe financial-recession quarter is a reference episode, not a universal target for a moderate demand shock.",
        (),
        ("metric.economy.real_output",),
    ),
    EmpiricalSource(
        "great_recession_unemployment",
        "The Employment Situation: December 2009",
        "U.S. Bureau of Labor Statistics",
        "https://www.bls.gov/news.release/archives/empsit_01082010.pdf",
        "official_historical_statistic",
        "official_historical_statistic",
        "U.S. unemployment rose from 5.0 percent at the December 2007 recession start to 10.0 percent in late 2009.",
        {"start_unemployment_percent": 5.0, "peak_unemployment_percent": 10.0,
         "increase_percentage_points": 5.0},
        "The 2007-09 episode included financial and housing propagation absent from the accepted model's isolated demand-recession tape.",
        (),
        ("metric.economy.unemployment_rate",),
    ),
)


def _load(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validate_upstream_integrity(
    upstream: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Recompute every upstream manifest, evidence, and acceptance identity."""

    errors: list[str] = []

    def check(stage: str, name: str, observed: Any, expected: Any) -> None:
        if observed != expected:
            errors.append(f"{stage.upper()} {name} hash does not reproduce")

    p2 = upstream["p2"]
    p2_protocol = p2["protocol"]
    p2_manifest = _canonical_hash(p2["experiment_manifest"])
    p2_evidence = _canonical_hash(p2["reports"])
    check("p2", "manifest", p2["hashes"].get("p2_experiment_manifest"), p2_manifest)
    check("p2", "evidence", p2["hashes"].get("p2_evidence"), p2_evidence)
    check(
        "p2",
        "acceptance",
        p2["hashes"].get("p2_acceptance"),
        _canonical_hash({
            "status": p2["status"],
            "errors": p2["errors"],
            "p0_root": p2["p0_root_hash"],
            "experiment_manifest": p2_manifest,
            "protocol": {
                "population": p2_protocol["population_per_country"],
                "seeds": p2_protocol["matched_seeds"],
                "workers": p2_protocol["native_engine_workers"],
                "ordinary_days": p2_protocol["ordinary_days"],
                "activation_days": p2_protocol["activation_days"],
                "burn_in_days": p2_protocol["burn_in_days"],
                "withdrawal_days": p2_protocol["withdrawal_days"],
            },
            "evidence": p2_evidence,
        }),
    )

    p3 = upstream["p3"]
    p3_manifest = _canonical_hash(p3["manifest"])
    p3_evidence = _canonical_hash(p3["reports"])
    check("p3", "manifest", p3["hashes"].get("p3_manifest"), p3_manifest)
    check("p3", "evidence", p3["hashes"].get("p3_evidence"), p3_evidence)
    check(
        "p3",
        "acceptance",
        p3["hashes"].get("p3_acceptance"),
        _canonical_hash({
            "status": p3["status"],
            "errors": p3["errors"],
            "p0_root": p3["p0_root_hash"],
            "protocol": p3["protocol"],
            "manifest": p3_manifest,
            "evidence": p3_evidence,
            "accepted_crises_for_p4": p3["accepted_crises_for_p4"],
        }),
    )

    for stage in ("p4", "p5"):
        payload = upstream[stage]
        manifest_hash = _canonical_hash(payload["manifest"])
        evidence_hash = _canonical_hash(payload["reports"])
        check(stage, "manifest", payload["hashes"].get(f"{stage}_manifest"), manifest_hash)
        check(stage, "evidence", payload["hashes"].get(f"{stage}_evidence"), evidence_hash)
        acceptance = {
            "schema_version": payload["schema_version"],
            "evidence_hash": evidence_hash,
            "errors": payload["errors"],
        }
        if stage == "p4":
            acceptance.update({
                "matrix_hash": _canonical_hash(payload["manifest"]["matrix"]),
                "counts": payload["counts"]["dispositions"],
            })
        else:
            acceptance.update({
                "manifest_hash": manifest_hash,
                "dispositions": payload["counts"]["dispositions"],
            })
        check(
            stage,
            "acceptance",
            payload["hashes"].get(f"{stage}_acceptance"),
            _canonical_hash(acceptance),
        )

    p6 = upstream["p6"]
    p6_manifest_payload = dict(p6["manifest"])
    embedded_p6_manifest = p6_manifest_payload.pop("manifest_hash", None)
    p6_manifest = _canonical_hash(p6_manifest_payload)
    check("p6", "embedded manifest", embedded_p6_manifest, p6_manifest)
    check("p6", "manifest", p6["hashes"].get("p6_manifest"), p6_manifest)
    p6_evidence = _canonical_hash({
        "reports": p6["reports"],
        "rare_event_ledger": p6["rare_event_ledger"],
    })
    check("p6", "evidence", p6["hashes"].get("p6_evidence"), p6_evidence)
    check(
        "p6",
        "acceptance",
        p6["hashes"].get("p6_acceptance"),
        _canonical_hash({
            "status": p6["status"],
            "errors": p6["errors"],
            "explicit_defects": p6["explicit_defects"],
            "source_revision": p6["source_revision"],
            "protocol": p6["protocol"],
            "manifest": p6_manifest,
            "evidence": p6_evidence,
        }),
    )
    return errors


def _by_lever(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    reports = payload.get("reports", ())
    if not isinstance(reports, list):
        raise ValueError("upstream report ledger is not a list")
    output = {str(item["lever"]): item for item in reports}
    if len(output) != len(reports):
        raise ValueError("upstream report ledger contains duplicate levers")
    return output


def _arm(report: Mapping[str, Any], dose_class: str) -> Mapping[str, Any]:
    arms = [
        item for item in report.get("activation", {}).get("arms", ())
        if item.get("dose_class") == dose_class
    ]
    if len(arms) != 1:
        raise ValueError(
            f"{report.get('lever')}: expected one P2 {dose_class!r} arm"
        )
    return arms[0]


def _effect(
    arm: Mapping[str, Any], metric_id: str, statistic: str,
    field: str = "mean_difference",
) -> float:
    try:
        return float(arm["effects"][metric_id][statistic][field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"missing comparable effect {metric_id}.{statistic}.{field}"
        ) from exc


def _p4_arm(
    report: Mapping[str, Any], lever: str, value: Any, timing: str = "immediate",
) -> Mapping[str, Any]:
    matches = []
    for item in report.get("arm_results", ()):
        actions = item.get("actions", ())
        if item.get("timing") != timing:
            continue
        if any(action.get("lever") == lever and action.get("value") == value for action in actions):
            matches.append(item)
    if len(matches) != 1:
        raise ValueError(f"{lever}: expected one P4 {value!r}/{timing} result")
    return matches[0]


def _p4_effect(
    arm: Mapping[str, Any], metric_id: str, statistic: str,
    field: str = "mean_difference",
) -> float:
    try:
        return float(arm["crisis_effects"][metric_id][statistic][field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"missing comparable P4 effect {metric_id}.{statistic}.{field}"
        ) from exc


def _actions(arm: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(action) for action in arm.get("actions", ())]


def _selected_preset(report: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    disposition = str(report["disposition"])
    if not disposition.startswith("accepted"):
        return "withheld_upstream_defect", []
    arms = list(report.get("activation", {}).get("arms", ()))
    if not arms:
        return "withheld_no_tested_dose", []
    preferred = next(
        (item for item in arms if item.get("dose_class") == "meaningful"),
        arms[-1],
    )
    status = {
        "accepted": "tested_general",
        "accepted_activation_only": "tested_binding_state_only",
        "accepted_expert_only": "tested_expert_only",
        "accepted_structural_long_horizon": "tested_long_horizon",
    }[disposition]
    return status, _actions(preferred)


def _claim_scope(
    p2_report: Mapping[str, Any], p4_report: Mapping[str, Any] | None,
) -> tuple[str, str]:
    p2_disposition = str(p2_report["disposition"])
    if not p2_disposition.startswith("accepted"):
        return (
            "economic_definition_only",
            "The UI may explain the economic concept, but it must not claim a demonstrated implemented effect.",
        )
    if p4_report is None:
        return (
            "mechanism_only",
            "The implemented proximal mechanism is evidenced; no accepted crisis-efficacy claim is available.",
        )
    p4_disposition = str(p4_report["disposition"])
    if p4_disposition == "accepted_crisis_efficacy":
        return (
            "demand_recession_efficacy_with_tradeoffs",
            "A narrow benefit passed in CR_DEMAND_RECESSION; all recorded harms and uncertainty remain part of the claim.",
        )
    if p4_disposition == "safety_concern":
        return (
            "mechanism_and_demand_recession_safety_concern",
            "The mechanism is live, but its accepted demand-recession test found a material safety concern.",
        )
    if p4_disposition == "safety_passed":
        return (
            "mechanism_and_demand_recession_safety_only",
            "The safety screen passed only in CR_DEMAND_RECESSION; this is not an efficacy or universal-safety claim.",
        )
    return (
        "mechanism_with_scenario_specific_result",
        "The mechanism is evidenced, while the P4 result is scenario-specific and does not establish a general benefit.",
    )


def build_empirical_comparisons(
    p2_source: str | Path | Mapping[str, Any],
    p3_source: str | Path | Mapping[str, Any],
    p4_source: str | Path | Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Reduce frozen model results into explicitly scoped empirical comparisons."""

    p2 = _load(p2_source)
    p3 = _load(p3_source)
    p4 = _load(p4_source)
    p2_by_lever = _by_lever(p2)
    p4_by_lever = _by_lever(p4)

    gov_c_local = _arm(p2_by_lever["gov_consumption_share"], "local")
    gov_c_meaningful = _arm(p2_by_lever["gov_consumption_share"], "meaningful")
    gov_i_local = _arm(p2_by_lever["gov_investment_share"], "local")
    gov_i_meaningful = _arm(p2_by_lever["gov_investment_share"], "meaningful")

    def multiplier(arm: Mapping[str, Any], spending_metric: str) -> float:
        spending = _effect(arm, spending_metric, "cumulative")
        return _effect(arm, "metric.economy.real_output", "cumulative") / spending

    tax_arm = _arm(p2_by_lever["tax_income_rate"], "meaningful")
    benefit_arm = _arm(p2_by_lever["benefit_income_floor"], "meaningful")
    benefit_crisis = _p4_arm(
        p4_by_lever["benefit_income_floor"], "benefit_income_floor", 0.2
    )
    min_wage_local = _arm(p2_by_lever["min_wage"], "local")
    min_wage_meaningful = _arm(p2_by_lever["min_wage"], "meaningful")
    rate_crisis = _p4_arm(
        p4_by_lever["manual_policy_rate"], "manual_policy_rate", 0.001
    )
    bank_local = _arm(p2_by_lever["bank_target_capital_ratio"], "local")
    bank_meaningful = _arm(p2_by_lever["bank_target_capital_ratio"], "meaningful")
    ltv_local = _arm(p2_by_lever["mortgage_ltv_cap"], "local")
    ltv_meaningful = _arm(p2_by_lever["mortgage_ltv_cap"], "meaningful")
    tariff_local = _arm(p2_by_lever["tariff"], "local")
    tariff_meaningful = _arm(p2_by_lever["tariff"], "meaningful")

    demand = next(
        item for item in p3["reports"]["crises"]
        if item["scenario_id"] == "CR_DEMAND_RECESSION"
    )
    entry_rows = demand["entry_gate"]["by_seed"]
    output_losses = []
    unemployment_increases = []
    for row in entry_rows:
        by_metric = {item["metric_id"]: item for item in row["rules"]}
        output = by_metric["metric.economy.real_output"]
        unemployment = by_metric["metric.economy.unemployment_rate"]
        output_losses.append(float(output["observed"]) / float(output["baseline_scale"]))
        unemployment_increases.append(float(unemployment["observed"]))
    recovery_days = [
        int(item["persistent_days"]) for item in demand["recovery_gate"]["by_seed"]
    ]

    return [
        {
            "comparison_id": "fiscal_spending_multiplier",
            "source_ids": ["fiscal_multiplier_synthesis", "fiscal_state_dependence"],
            "claim_basis": "mixed_empirical_and_synthesis",
            "model_evidence": {
                "gov_consumption_local_multiplier": multiplier(
                    gov_c_local, "metric.source.m4.government_consumption"
                ),
                "gov_consumption_meaningful_multiplier": multiplier(
                    gov_c_meaningful, "metric.source.m4.government_consumption"
                ),
                "gov_investment_local_multiplier": multiplier(
                    gov_i_local, "metric.source.m4.public_fixed_capital_formation"
                ),
                "gov_investment_meaningful_multiplier": multiplier(
                    gov_i_meaningful, "metric.source.m4.public_fixed_capital_formation"
                ),
            },
            "comparison_status": "direction_and_monotonicity_conflict",
            "assessment": "Government-consumption and investment responses change sign across local and meaningful doses; only the meaningful investment contrast has the conventional positive spending/output sign.",
            "uncertainty": "P2 is a short activation experiment and its cumulative ratio is not a fully identified national-accounts multiplier.",
        },
        {
            "comparison_id": "income_tax_output_response",
            "source_ids": ["fiscal_multiplier_synthesis", "narrative_tax_shocks"],
            "claim_basis": "empirical_estimate",
            "model_evidence": {
                "action": _actions(tax_arm),
                "cumulative_tax_revenue_change": _effect(
                    tax_arm, "metric.source.m4.tax_income", "cumulative"
                ),
                "cumulative_real_output_change": _effect(
                    tax_arm, "metric.economy.real_output", "cumulative"
                ),
            },
            "comparison_status": "direction_conflict",
            "assessment": "The meaningful income-tax cut lowers both tax revenue and real output in P2, opposite the conventional expansionary sign of an exogenous tax cut.",
            "uncertainty": "The model arm is not scaled as a tax change divided by GDP and the P2 horizon is shorter than the empirical studies.",
        },
        {
            "comparison_id": "benefit_consumption_and_poverty",
            "source_ids": ["ui_consumption_smoothing"],
            "claim_basis": "empirical_estimate",
            "model_evidence": {
                "ordinary_poverty_change_pp": 100.0 * _effect(
                    benefit_arm, "metric.economy.poverty_rate", "post_burnin_mean"
                ),
                "demand_recession_poverty_change_pp": 100.0 * _p4_effect(
                    benefit_crisis, "metric.economy.poverty_rate", "post_burnin_mean"
                ),
                "demand_recession_unemployment_change_pp": 100.0 * _p4_effect(
                    benefit_crisis, "metric.economy.unemployment_rate", "post_burnin_mean"
                ),
                "comparable_consumption_effect_available": False,
            },
            "comparison_status": "scope_mismatch_and_missing_primary_outcome",
            "assessment": "The in-work income floor has state-dependent poverty effects and a material unemployment trade-off, but P2/P4 do not provide the directly comparable recipient-consumption estimand from the UI evidence.",
            "uncertainty": "benefit_income_floor is not unemployment insurance; benefit_replacement is conceptually closer but has no accepted crisis benefit in P4.",
        },
        {
            "comparison_id": "minimum_wage_employment",
            "source_ids": ["minimum_wage_bunching"],
            "claim_basis": "empirical_estimate",
            "model_evidence": {
                "local_action": _actions(min_wage_local),
                "local_unemployment_change_pp": 100.0 * _effect(
                    min_wage_local, "metric.economy.unemployment_rate", "post_burnin_mean"
                ),
                "meaningful_action": _actions(min_wage_meaningful),
                "meaningful_unemployment_change_pp": 100.0 * _effect(
                    min_wage_meaningful, "metric.economy.unemployment_rate", "post_burnin_mean"
                ),
            },
            "comparison_status": "qualitative_tension_with_dose_scope_mismatch",
            "assessment": "The local model dose has no unemployment effect, while the larger 1.25 reference-wage floor raises unemployment; the empirical sample does not identify that extreme model dose.",
            "uncertainty": "Aggregate unemployment is not the empirical paper's low-wage-job count, and the model's reference-wage unit has no direct statutory-wage crosswalk.",
        },
        {
            "comparison_id": "manual_rate_recession_response",
            "source_ids": [],
            "claim_basis": "model_design_prior",
            "model_evidence": {
                "action": _actions(rate_crisis),
                "demand_recession_unemployment_change_pp": 100.0 * _p4_effect(
                    rate_crisis, "metric.economy.unemployment_rate", "post_burnin_mean"
                ),
                "cumulative_real_output_change": _p4_effect(
                    rate_crisis, "metric.economy.real_output", "cumulative"
                ),
            },
            "comparison_status": "model_direction_only_no_empirical_magnitude_crosswalk",
            "assessment": "The lower manual-rate arm improves unemployment and cumulative output in the accepted demand recession, matching the design-prior direction.",
            "uncertainty": "The lever is a daily rate and has no frozen conversion to a conventional annual policy-rate shock, so no empirical magnitude claim is permitted.",
        },
        {
            "comparison_id": "open_market_operations_yield_channel",
            "source_ids": ["federal_reserve_lsap"],
            "claim_basis": "empirical_estimate",
            "model_evidence": {
                "reported_model_outcomes": [
                    "metric.source.m5.omo_flow", "metric.source.m5.total_reserves"
                ],
                "comparable_long_yield_available": False,
            },
            "comparison_status": "missing_empirical_outcome",
            "assessment": "The OMO route is live, but the model does not report a comparable long-term sovereign yield or duration-adjusted purchase dose.",
            "uncertainty": "Reserve movements alone cannot validate an LSAP term-premium magnitude.",
        },
        {
            "comparison_id": "bank_capital_credit",
            "source_ids": ["uk_bank_capital_requirements"],
            "claim_basis": "empirical_estimate",
            "model_evidence": {
                "local_action": _actions(bank_local),
                "local_new_credit_relative_change": _effect(
                    bank_local, "metric.source.m5.new_credit", "post_burnin_mean",
                    "mean_relative_difference",
                ),
                "meaningful_action": _actions(bank_meaningful),
                "meaningful_new_credit_relative_change": _effect(
                    bank_meaningful, "metric.source.m5.new_credit", "post_burnin_mean",
                    "mean_relative_difference",
                ),
            },
            "comparison_status": "qualitative_direction_only_nonmonotonic_magnitude",
            "assessment": "Both target-capital-ratio increases reduce new credit, but the larger dose has the smaller response, so the empirical annual magnitude cannot be matched.",
            "uncertainty": "Target ratios differ from regulatory minima and P2 measures a short flow response rather than annual loan growth.",
        },
        {
            "comparison_id": "mortgage_ltv_credit",
            "source_ids": ["macroprudential_ltv"],
            "claim_basis": "empirical_estimate",
            "model_evidence": {
                "local_action": _actions(ltv_local),
                "local_originations_relative_change": _effect(
                    ltv_local, "metric.source.m8.housing.mortgage_originations",
                    "post_burnin_mean", "mean_relative_difference",
                ),
                "meaningful_action": _actions(ltv_meaningful),
                "meaningful_originations_relative_change": _effect(
                    ltv_meaningful, "metric.source.m8.housing.mortgage_originations",
                    "post_burnin_mean", "mean_relative_difference",
                ),
            },
            "comparison_status": "qualitative_match_extreme_dose_mismatch",
            "assessment": "Tighter LTV caps sharply reduce mortgage originations in the model, matching the empirical direction but at non-comparable, extreme fixture doses.",
            "uncertainty": "The model changes the cap to 0.5 and 0.0 over 30 days; the empirical output estimate is for a 10-percentage-point change over four years.",
        },
        {
            "comparison_id": "tariff_import_response",
            "source_ids": ["us_tariff_pass_through"],
            "claim_basis": "official_empirical_estimate",
            "model_evidence": {
                "local_action": _actions(tariff_local),
                "local_import_relative_change": _effect(
                    tariff_local, "metric.source.m9.country.imports_volume",
                    "post_burnin_mean", "mean_relative_difference",
                ),
                "meaningful_action": _actions(tariff_meaningful),
                "meaningful_import_relative_change": _effect(
                    tariff_meaningful, "metric.source.m9.country.imports_volume",
                    "post_burnin_mean", "mean_relative_difference",
                ),
            },
            "comparison_status": "direction_and_magnitude_conflict",
            "assessment": "A 5 percent model tariff raises imports by about 2.09 percent; a 25 percent tariff lowers them by only about 1.19 percent. The local sign conflicts with the official estimate and the larger response is far weaker.",
            "uncertainty": "The USITC estimate is product-specific and multi-year, but neither that scope difference nor horizon explains a positive local import response.",
        },
        {
            "comparison_id": "demand_recession_stylized_facts",
            "source_ids": ["great_recession_output", "great_recession_unemployment"],
            "claim_basis": "official_historical_reference",
            "model_evidence": {
                "mean_peak_output_loss_percent": 100.0 * fmean(output_losses),
                "mean_peak_unemployment_increase_pp": 100.0 * fmean(unemployment_increases),
                "mean_recovery_persistent_days": fmean(recovery_days),
                "entry_seed_support": demand["entry_gate"]["passed_seed_count"],
                "recovery_seed_support": demand["recovery_gate"]["passed_seed_count"],
            },
            "comparison_status": "partial_stylized_match_horizon_mismatch",
            "assessment": "The accepted model recession has the expected output-loss and unemployment ordering and an output decline of historical-recession scale, but its labor response is smaller and its recovery is much faster than the severe 2007-09 reference episode.",
            "uncertainty": "The empirical reference is a severe financial and housing recession; P3 intentionally validates a shorter isolated demand shock, so it is not calibrated to reproduce that episode.",
        },
    ]


def build_p7_manifest(
    p2_source: str | Path | Mapping[str, Any],
    p3_source: str | Path | Mapping[str, Any],
    p4_source: str | Path | Mapping[str, Any],
    p5_source: str | Path | Mapping[str, Any],
    p6_source: str | Path | Mapping[str, Any],
    explanation_source: str | Path | Mapping[str, Any],
) -> dict[str, Any]:
    p0 = build_p0_payload()
    upstream = {
        "p2": _load(p2_source),
        "p3": _load(p3_source),
        "p4": _load(p4_source),
        "p5": _load(p5_source),
        "p6": _load(p6_source),
    }
    explanations = _load(explanation_source)
    errors: list[str] = []
    for stage, payload in upstream.items():
        if payload.get("status") != P7_ACCEPTED_UPSTREAM_STATUS:
            errors.append(f"{stage.upper()} is not frozen with explicit dispositions")
    errors.extend(_validate_upstream_integrity(upstream))
    if upstream["p2"].get("p0_root_hash") != p0["hashes"]["p0_root"]:
        errors.append("P2 does not bind the current P0 root")
    if upstream["p3"].get("p0_root_hash") != p0["hashes"]["p0_root"]:
        errors.append("P3 does not bind the current P0 root")
    expected_upstream = {
        "p2_acceptance": upstream["p2"].get("hashes", {}).get("p2_acceptance"),
        "p3_acceptance": upstream["p3"].get("hashes", {}).get("p3_acceptance"),
        "p4_acceptance": upstream["p4"].get("hashes", {}).get("p4_acceptance"),
        "p5_acceptance": upstream["p5"].get("hashes", {}).get("p5_acceptance"),
        "p6_acceptance": upstream["p6"].get("hashes", {}).get("p6_acceptance"),
    }
    chain_bindings = {
        "p4": ("p2_acceptance", "p3_acceptance"),
        "p5": ("p2_acceptance", "p3_acceptance", "p4_acceptance"),
        "p6": ("p2_acceptance", "p5_acceptance"),
    }
    for stage, upstream_stages in chain_bindings.items():
        stage_manifest = upstream[stage].get("manifest", {})
        for upstream_key in upstream_stages:
            if stage_manifest.get(f"{upstream_key}_hash") != expected_upstream[upstream_key]:
                upstream_label = upstream_key.removesuffix("_acceptance").upper()
                errors.append(
                    f"{stage.upper()} does not bind the frozen "
                    f"{upstream_label} acceptance hash"
                )
    for stage in ("p4", "p5", "p6"):
        if upstream[stage].get("manifest", {}).get("p0_root_hash") != p0["hashes"]["p0_root"]:
            errors.append(f"{stage.upper()} does not bind the current P0 root")

    registry_names = {str(item["lever"]) for item in p0["inventory"]}
    if set(explanations) != registry_names:
        errors.append("policy explanation keys do not exactly match the Registry")
    for lever, explanation in explanations.items():
        if not isinstance(explanation, Mapping):
            errors.append(f"{lever}: explanation is not an object")
            continue
        if set(explanation) != set(P7_EXPLANATION_FIELDS):
            errors.append(f"{lever}: explanation fields are incomplete")
            continue
        if any(not isinstance(explanation[field], str) or not explanation[field].strip()
               for field in P7_EXPLANATION_FIELDS):
            errors.append(f"{lever}: explanation contains an empty field")

    source_payload = [item.to_dict() for item in EMPIRICAL_SOURCES]
    source_ids = [item["source_id"] for item in source_payload]
    if len(source_ids) != len(set(source_ids)):
        errors.append("empirical source catalog contains duplicate source ids")
    for item in source_payload:
        if not item["url"].startswith("https://"):
            errors.append(f"{item['source_id']}: empirical source URL is not HTTPS")
        if item["claim_basis"] not in {
            "empirical_estimate", "official_historical_statistic", "evidence_synthesis"
        }:
            errors.append(f"{item['source_id']}: empirical claim basis is not classified")

    payload = {
        "schema_version": P7_SCHEMA_VERSION,
        "p0_root_hash": p0["hashes"]["p0_root"],
        "upstream_acceptance_hashes": expected_upstream,
        "source_catalog": source_payload,
        "explanation_hash": _canonical_hash(explanations),
        "registry_hash": p0["hashes"]["registry"],
        "contract_hash": p0["hashes"]["contracts"],
        "scenario_catalog_hash": p0["hashes"]["scenarios"],
        "materiality_hash": p0["hashes"]["materiality"],
        "errors": errors,
    }
    payload["manifest_hash"] = _canonical_hash(payload)
    return payload


def build_lever_ledger(
    p2_source: str | Path | Mapping[str, Any],
    p4_source: str | Path | Mapping[str, Any],
    p6_source: str | Path | Mapping[str, Any],
    explanation_source: str | Path | Mapping[str, Any],
) -> list[dict[str, Any]]:
    p2 = _load(p2_source)
    p4 = _load(p4_source)
    p6 = _load(p6_source)
    explanations = _load(explanation_source)
    p2_by_lever = _by_lever(p2)
    p4_by_lever = _by_lever(p4)
    p6_by_lever = _by_lever(p6)
    inventory = {item["lever"]: item for item in build_inventory()}
    contracts = {item.lever: item.to_dict() for item in build_contracts()}
    empirical_by_lever: dict[str, list[str]] = {}
    for source in EMPIRICAL_SOURCES:
        for lever in source.levers:
            empirical_by_lever.setdefault(lever, []).append(source.source_id)

    output = []
    for lever in inventory:
        p2_report = p2_by_lever[lever]
        p4_report = p4_by_lever.get(lever)
        preset_status, preset_actions = _selected_preset(p2_report)
        claim_scope, claim = _claim_scope(p2_report, p4_report)
        p6_report = p6_by_lever.get(lever)
        anchor_ids = empirical_by_lever.get(lever, [])
        output.append({
            "lever": lever,
            "owner_role": inventory[lever]["owner_role"],
            "decision_group": inventory[lever]["decision_group"],
            "registry_domain": inventory[lever]["validation"],
            "reference_baseline": inventory[lever]["reference_baseline"],
            "tested_doses": [
                {
                    "dose_class": item.get("dose_class"),
                    "actions": _actions(item),
                }
                for item in (p2_report.get("activation") or {}).get("arms", ())
            ],
            "recommended_ui_preset_status": preset_status,
            "recommended_ui_actions": preset_actions,
            "economic_explanation": dict(explanations[lever]),
            "claim_scope": claim_scope,
            "player_facing_claim": claim,
            "uncertainty_label": (
                str(p2_report["reason"])
                if not str(p2_report["disposition"]).startswith("accepted")
                else (
                    "No direct empirical anchor; current claim is model evidence only."
                    if not anchor_ids else
                    "Empirical anchor is contextual unless a P7 comparison states comparability."
                )
            ),
            "p2_disposition": p2_report["disposition"],
            "p4_disposition": p4_report["disposition"] if p4_report else None,
            "p6_disposition": p6_report["disposition"] if p6_report else None,
            "empirical_source_ids": anchor_ids,
            "mechanism_metrics": contracts[lever]["mechanism_proximal_metrics"],
            "tradeoff_metrics": contracts[lever]["tradeoff_metrics"],
            "operating_horizon_days": contracts[lever]["operating_horizon_days"],
        })
    return output


def build_crisis_ledger(p3_source: str | Path | Mapping[str, Any]) -> list[dict[str, Any]]:
    p3 = _load(p3_source)
    reports = {item["scenario_id"]: item for item in p3["reports"]["crises"]}
    output = []
    for scenario_id, spec in SCENARIOS.items():
        report = reports[scenario_id]
        accepted = bool(report["accepted"])
        output.append({
            "scenario_id": scenario_id,
            "description": spec.description,
            "p3_disposition": report["disposition"],
            "accepted_for_player_facing_efficacy": accepted,
            "player_facing_claim": (
                "Validated model scenario; empirical comparison remains a scoped historical reference."
                if accepted else
                "Scenario is not accepted for policy-efficacy claims."
            ),
            "uncertainty_label": (
                "The accepted model path is not a calibration to a named historical episode."
                if accepted else str(report["reason"])
            ),
            "empirical_source_ids": (
                ["great_recession_output", "great_recession_unemployment"]
                if scenario_id == "CR_DEMAND_RECESSION" else []
            ),
        })
    return output


def run_p7(
    *,
    artifact_dir: str | Path,
    source_revision: str,
    p2_source: str | Path | Mapping[str, Any],
    p3_source: str | Path | Mapping[str, Any],
    p4_source: str | Path | Mapping[str, Any],
    p5_source: str | Path | Mapping[str, Any],
    p6_source: str | Path | Mapping[str, Any],
    explanation_source: str | Path | Mapping[str, Any],
) -> dict[str, Any]:
    artifact_path = Path(artifact_dir)
    manifest = build_p7_manifest(
        p2_source, p3_source, p4_source, p5_source, p6_source,
        explanation_source,
    )
    errors = list(manifest["errors"])
    levers = build_lever_ledger(p2_source, p4_source, p6_source, explanation_source)
    crises = build_crisis_ledger(p3_source)
    comparisons = build_empirical_comparisons(p2_source, p3_source, p4_source)

    comparison_statuses: dict[str, int] = {}
    for item in comparisons:
        key = str(item["comparison_status"])
        comparison_statuses[key] = comparison_statuses.get(key, 0) + 1
    preset_statuses: dict[str, int] = {}
    for item in levers:
        key = str(item["recommended_ui_preset_status"])
        preset_statuses[key] = preset_statuses.get(key, 0) + 1

    explicit_findings = [
        {
            "finding_id": f"p7.{item['comparison_id']}",
            "status": item["comparison_status"],
            "assessment": item["assessment"],
        }
        for item in comparisons
        if "conflict" in str(item["comparison_status"])
        or str(item["comparison_status"]).startswith("missing_")
    ]
    freeze = {
        "registry_ranges": [
            {
                "lever": item["lever"],
                "domain": item["registry_domain"],
                "basis": "runtime_invariant_not_empirical_calibration",
            }
            for item in levers
        ],
        "recommended_ui_presets": [
            {
                "lever": item["lever"],
                "status": item["recommended_ui_preset_status"],
                "actions": item["recommended_ui_actions"],
                "basis": "frozen_p2_tested_dose",
            }
            for item in levers
        ],
        "policy_explanations": {
            "hash": manifest["explanation_hash"],
            "required_fields": list(P7_EXPLANATION_FIELDS),
            "basis": "economic_definition_with_separate_engine_claim",
        },
        "scenario_manifests": {
            "catalog_hash": manifest["scenario_catalog_hash"],
            "p3_acceptance_hash": manifest["upstream_acceptance_hashes"]["p3_acceptance"],
            "accepted_scenarios": [
                item["scenario_id"] for item in crises
                if item["accepted_for_player_facing_efficacy"]
            ],
        },
        "regression_thresholds": {
            "materiality_hash": manifest["materiality_hash"],
            "metrics": {
                metric_id: spec.to_dict()
                for metric_id, spec in METRIC_MATERIALITY.items()
            },
            "basis": "model_design_prior_unless_metric_row_says_otherwise",
        },
    }
    evidence = {
        "lever_ledger": levers,
        "crisis_ledger": crises,
        "empirical_comparisons": comparisons,
        "explicit_findings": explicit_findings,
        "freeze": freeze,
    }
    payload = {
        "schema_version": P7_SCHEMA_VERSION,
        "status": "accepted_with_explicit_defects" if not errors else "failed",
        "source_revision": source_revision,
        "errors": errors,
        "explicit_findings": explicit_findings,
        "manifest": manifest,
        "counts": {
            "levers": len(levers),
            "policy_explanations": len(levers),
            "ui_presets_available": sum(
                bool(item["recommended_ui_actions"]) for item in levers
            ),
            "ui_presets_withheld": sum(
                not bool(item["recommended_ui_actions"]) for item in levers
            ),
            "preset_statuses": preset_statuses,
            "crises": len(crises),
            "accepted_crises": sum(
                item["accepted_for_player_facing_efficacy"] for item in crises
            ),
            "empirical_sources": len(EMPIRICAL_SOURCES),
            "original_or_official_sources": sum(
                item.source_class != "research_synthesis" for item in EMPIRICAL_SOURCES
            ),
            "empirical_comparisons": len(comparisons),
            "comparison_statuses": comparison_statuses,
            "explicit_findings": len(explicit_findings),
        },
        "lever_ledger": levers,
        "crisis_ledger": crises,
        "empirical_comparisons": comparisons,
        "freeze": freeze,
        "hashes": {
            "p7_manifest": manifest["manifest_hash"],
            "p7_evidence": _canonical_hash(evidence),
        },
        "protocol": {
            "legacy_python_simulator_used": False,
            "native_simulation_executed": False,
            "network_fetch_during_acceptance": False,
            "source_review_date": P7_SOURCE_REVIEW_DATE,
            "empirical_estimates_separate_from_model_design_priors": True,
        },
    }
    payload["hashes"]["p7_acceptance"] = _canonical_hash({
        "status": payload["status"],
        "source_revision": source_revision,
        "errors": errors,
        "manifest": payload["hashes"]["p7_manifest"],
        "evidence": payload["hashes"]["p7_evidence"],
        "protocol": payload["protocol"],
    })
    artifact_path.mkdir(parents=True, exist_ok=True)
    target = artifact_path / "p7_report.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return payload


def render_p7_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Policy causality P7 report",
        "",
        f"Status: `{payload['status']}`",
        "",
        "## Frozen surface",
        "",
        f"- Policy levers: {payload['counts']['levers']}",
        f"- Complete policy explanations: {payload['counts']['policy_explanations']}",
        f"- UI presets available: {payload['counts']['ui_presets_available']}",
        f"- UI presets withheld: {payload['counts']['ui_presets_withheld']}",
        f"- Accepted crisis manifests: {payload['counts']['accepted_crises']} / {payload['counts']['crises']}",
        f"- Empirical sources: {payload['counts']['empirical_sources']}",
        f"- Empirical/model comparisons: {payload['counts']['empirical_comparisons']}",
        "",
        "## Empirical comparisons",
        "",
        "| Comparison | Status | Assessment |",
        "|---|---|---|",
    ]
    for item in payload["empirical_comparisons"]:
        lines.append(
            f"| `{item['comparison_id']}` | `{item['comparison_status']}` | "
            f"{item['assessment']} |"
        )
    lines.extend([
        "",
        "## Explicit findings",
        "",
    ])
    if payload["explicit_findings"]:
        for item in payload["explicit_findings"]:
            lines.append(
                f"- `{item['finding_id']}`: `{item['status']}` — {item['assessment']}"
            )
    else:
        lines.append("- None.")
    lines.extend([
        "",
        "## Hashes",
        "",
        f"- Manifest: `{payload['hashes']['p7_manifest']}`",
        f"- Evidence: `{payload['hashes']['p7_evidence']}`",
        f"- Acceptance: `{payload['hashes']['p7_acceptance']}`",
        "",
    ])
    return "\n".join(lines)


__all__ = [
    "EMPIRICAL_SOURCES",
    "P7_EXPLANATION_FIELDS",
    "P7_SCHEMA_VERSION",
    "P7_SOURCE_REVIEW_DATE",
    "build_crisis_ledger",
    "build_empirical_comparisons",
    "build_lever_ledger",
    "build_p7_manifest",
    "render_p7_markdown",
    "run_p7",
]
