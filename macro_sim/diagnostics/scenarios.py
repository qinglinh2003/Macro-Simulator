"""Supported production-like configurations and paired diagnostic matrices."""

from __future__ import annotations

from typing import Any

from macro_sim.config import Config
from macro_sim.diagnostics.models import Intervention, RunSpec


# This is the union actually used by the v16-v18 frontier experiments.  Experimental
# feedback elasticities remain zero: a production baseline should exercise institutions,
# not silently choose a research hypothesis about fertility or mortality.
FULL_FRONTIER_FLAGS: dict[str, Any] = {
    "firm_full_pnl": True,
    "bank_realized_pnl": True,
    "bank_relationship_lock_in": True,
    "household_interest_arrears": True,
    "capital_service_pricing": True,
    "priced_firm_balance_sheet": True,
    "monetary_direct_transmission": True,
    "national_accounts_metrics": True,
    "cb_uses_fixed_basket_cpi": True,
    "fiscal_uses_national_accounts_gdp": True,
    "housing_enabled": True,
    "housing_market_enabled": True,
    "mortgage_enabled": True,
    "mortgage_underwriting": True,
    "unified_bank_rwa": True,
    "housing_rental_enabled": True,
    "housing_construction_enabled": True,
    "energy_enabled": True,
    "energy_household": True,
    "labor_matching": "persistent",
    "labor_fractional_hours": True,
    # v23 P0: the intensive margin needs a SECOND contract to be coherent. Greedy per-firm
    # allocation leaves one part-time marginal worker at every firm, and with a single Job
    # those residual hours were unsellable -- they drained into the job guarantee while firms
    # posted vacancies, production fell short of plan, and the B3 markup ratcheted into runaway
    # inflation. Same-seed twin (3 seeds, 1460t): underemployment hours 13.7 -> 5.1 FTE, labour
    # fill 73.8% -> 91.0%, markup 0.55 -> 0.50, inflation +5.6% -> -0.4%.
    "labor_second_job": True,
    "labor_matching_friction": True,
    "labor_relationship_wages": True,
    "labor_job_ladder": True,
    "labor_person_efficiency": True,
    "capital_rationed_signal": True,
    "consumption_rationed_signal": True,
    "firm_subscale_exit": True,
    "capital_firm_entry": True,
    "consumption_strata": True,
    "deprivation_gauges": True,
    "family_transfers": True,
    "sector_switching": True,
    # v19's production technology must be live in the production frontier.  Two per cent
    # is a scenario assumption, not an acceptance target.
    "tfp_drift_rate": 0.02,
    # v23 P0 (capital clock).  `v` is an ANNUAL capital-output ratio but plan_investment
    # multiplies it by a PER-TICK demand flow, so the desired capital stock was 365x too
    # small (measured K / annual GDP ~0.004 against a configured 2.5).  The joint migration
    # rescales (v, K_firm0, A) with genesis output exactly invariant.  a_K must be recalibrated
    # with it: it was never binding while the K sector was economically inert, and at 1.0 the
    # now-real replacement flow would consume ~1/3 of the labour force.
    "capital_annual_clock": True,
    "a_K": 2.4,
}


def diagnostic_intervention_window(ticks: int) -> tuple[int, int]:
    """Return a pre/during/post-friendly intervention window.

    The old 65%-of-run start left a 90-tick smoke run with only two post-treatment
    observations.  Reserve at least one treatment-width on both sides and use a
    longer recovery window when the horizon permits it.
    """

    if ticks < 6:
        start = max(1, ticks // 3)
        return start, max(start + 1, min(ticks, 2 * ticks // 3))
    width = max(2, min(180, ticks // 6))
    start = max(width, ticks // 2)
    if start + 2 * width > ticks:
        start = max(width, ticks - 2 * width)
    return start, min(ticks, start + width)


def build_frontier_config(spec: RunSpec) -> Config:
    params: dict[str, Any] = {
        **FULL_FRONTIER_FLAGS,
        "seed": spec.seed,
        # Compatibility floor only; Economy derives accounts from the person population.
        "n_households": max(50, spec.population // 10),
        "demographics_population": spec.population,
        "n_firms_c": spec.n_firms_c,
        "n_firms_k": spec.n_firms_k,
        "n_banks": spec.n_banks,
        "n_ticks": spec.ticks,
        **spec.overrides,
    }
    if spec.scenario == "energy_shock":
        start = spec.intervention.start_tick if spec.intervention else int(spec.ticks * 0.65)
        end = spec.intervention.end_tick if spec.intervention else start + 180
        params.update(
            energy_shock_at=start,
            energy_shock_magnitude=(spec.intervention.value if spec.intervention else 0.35),
            energy_shock_duration=max(1, end - start),
        )
    return Config.v13(**params)


def diagnostic_matrix(
    *,
    ticks: int,
    population: int,
    n_firms_c: int,
    n_firms_k: int,
    n_banks: int,
    seeds: int = 5,
    intervention_replicates: int = 1,
) -> list[RunSpec]:
    """Paired causal matrix with configurable cross-seed intervention replication.

    The ten-job default is five baselines plus one same-seed arm for each of five
    interventions.  Increasing ``intervention_replicates`` applies every intervention
    to the first N baseline seeds, so N=3 produces five baselines plus fifteen arms.
    This preserves the v17 lesson that arms whose policy differs before the shock are
    not causal twins while allowing the runner to promote replicated evidence.
    """

    if seeds < 1:
        raise ValueError("seeds must be at least 1")
    if not 1 <= intervention_replicates <= seeds:
        raise ValueError("intervention_replicates must be between 1 and seeds")

    def spec(
        name: str,
        seed: int,
        *,
        scenario: str = "baseline",
        intervention: Intervention | None = None,
    ) -> RunSpec:
        return RunSpec(
            name=name,
            seed=seed,
            ticks=ticks,
            population=population,
            n_firms_c=n_firms_c,
            n_firms_k=n_firms_k,
            n_banks=n_banks,
            scenario=scenario,
            pair_id=f"seed-{seed}",
            intervention=intervention,
        )

    baseline_count = max(5, seeds)
    jobs = [spec(f"baseline_s{seed}", seed) for seed in range(baseline_count)]
    start, end = diagnostic_intervention_window(ticks)
    interventions = (
        ("rate_cut", "policy_rate", 0.0),
        ("rate_hike", "policy_rate", 3.5e-4),
        ("energy_shock", "energy_capacity", 0.35),
        ("credit_tightening", "kappa_multiplier", 0.5),
        ("fiscal_expansion", "deficit_target", 0.06),
    )
    for scenario, variable, value in interventions:
        jobs.extend(
            spec(
                f"{scenario}_s{seed}",
                seed,
                scenario=scenario,
                intervention=Intervention(variable, start, end, value),
            )
            for seed in range(intervention_replicates)
        )
    return jobs


def root_cause_matrix(
    *,
    ticks: int,
    population: int,
    n_firms_c: int,
    n_firms_k: int,
    n_banks: int,
    seed: int = 0,
) -> list[RunSpec]:
    """Ten permanent mechanism ablations for structural root-cause attribution.

    These are not temporary treatment twins and are therefore reported separately
    from impulse responses.  One common seed removes Monte-Carlo noise; the reference
    plus nine one-mechanism removals fill ten independent CPU workers.
    """

    variants: tuple[tuple[str, dict[str, Any]], ...] = (
        ("reference", {}),
        ("no_jg_capital", {"jg_productivity": 0.0}),
        ("no_job_guarantee", {"job_guarantee": False, "jg_productivity": 0.0}),
        ("no_gov_investment", {"gov_investment_share": 0.0}),
        ("no_public_productivity", {"public_capital_gamma": 0.0}),
        ("no_public_capital_system", {
            "jg_productivity": 0.0, "gov_investment_share": 0.0,
            "public_capital_gamma": 0.0,
        }),
        ("no_exogenous_tfp", {"tfp_drift_rate": 0.0}),
        ("spot_labor", {
            "labor_matching": "spot", "labor_fractional_hours": False,
            "labor_matching_friction": False,
            "labor_relationship_wages": False, "labor_job_ladder": False,
            "labor_person_efficiency": False,
        }),
        ("no_lifecycle_consumption", {"demographic_lifecycle_consumption": False}),
        # Remove every capital/RWA supply ceiling while retaining borrower-side
        # mortgage LTV and DSTI underwriting.  Merely disabling the historical
        # gross-loan gate is no longer a valid ablation once the frontier also
        # enables the unified RWA envelope and mortgage portfolio capacity.
        ("no_bank_capital_cap", {
            "bank_capital_constraint": False,
            "unified_bank_rwa": False,
            "mortgage_min_capital_ratio": 1.0e-12,
        }),
    )
    return [
        RunSpec(
            name=f"ablation_{name}", seed=seed, ticks=ticks, population=population,
            n_firms_c=n_firms_c, n_firms_k=n_firms_k, n_banks=n_banks,
            scenario=f"ablation:{name}", overrides=overrides,
        )
        for name, overrides in variants
    ]


def profile_defaults(profile: str) -> dict[str, int]:
    profiles = {
        "smoke": dict(ticks=90, population=200, n_firms_c=20, n_firms_k=10, n_banks=2),
        "audit": dict(ticks=730, population=1000, n_firms_c=50, n_firms_k=25, n_banks=4),
        "production": dict(ticks=1825, population=2000, n_firms_c=100, n_firms_k=50, n_banks=4),
        "soak": dict(ticks=3650, population=10000, n_firms_c=500, n_firms_k=250, n_banks=8),
    }
    try:
        return dict(profiles[profile])
    except KeyError as exc:
        raise ValueError(f"unknown diagnostic profile {profile!r}; choose {', '.join(profiles)}") from exc
