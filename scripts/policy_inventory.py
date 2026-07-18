#!/usr/bin/env python3
"""v25 P0: the machine-verified policy/config classification inventory.

Design: docs/policy_module_v25.md §1. Every field of every manifest source is
classified into EXACTLY ONE bucket, under SOURCE-QUALIFIED ids (Config and Policy
share 43 same-name fields, so bare names cannot prove exclusivity).

Sources (the executable manifest):
  Config (root), Policy, World.__init__ keyword tunables, SocialDynamicsConfig,
  RelationshipConfig, LifecycleHouseholdConfig, config/schema.py derived views
  (classified wholesale as DERIVED_VIEW), plus the curated HARDCODED-institution
  registry (§1.6) with file/pattern verification.
  Excluded as test harness: Phase1AcceptanceConfig.
  Function-default/literal scan beyond the curated registry: staged follow-up
  (reported as such, never silently claimed complete).

Checks (all must pass; tests/test_policy_inventory.py enforces in CI):
  1. every discovered source field appears in exactly one bucket
  2. no stale entries (classified name that no longer exists in the source)
  3. count identities from the design doc hold (86 [P], 0 [C], 14 [W], 0 PENDING,
     3 [N]; candidate arithmetic 86+0+14+3-1(dead central_bank replaced) = 102;
     plus r_interest seed-promoted to PolicySeed.initial_policy_rate)
  4. every hardcoded-registry entry with a pattern is found in its file
"""
from __future__ import annotations

import dataclasses
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from macro_sim.config import Config                                  # noqa: E402
from macro_sim.core.policy import Policy                             # noqa: E402
from macro_sim.world.world import World                              # noqa: E402
from macro_sim.demographics.social import SocialDynamicsConfig       # noqa: E402
from macro_sim.demographics.relationships import RelationshipConfig  # noqa: E402
from macro_sim.demographics.lifecycle_households import LifecycleHouseholdConfig  # noqa: E402
import macro_sim.config.schema as _schema                            # noqa: E402

# ======================================================================
# Classification tables (source-qualified). Buckets are mutually exclusive
# WITHIN a source; the same bare name may appear under different sources.
# ======================================================================

# ---- Policy source: all declared fields are POLICY_LIVE; known defects are
# tracked separately (dead/snapshot/split-brain) in DEFECTS. ----
POLICY_LIVE_EXPECTED = 46

DEFECTS = {  # §1.7 — listed-but-not-runtime-effective (per-lever tests will gate)
    "Policy.central_bank": "DEAD FIELD (rate path reads cfg.central_bank); DELETED at migration, replaced by [N] monetary_regime",
    "World.peg_pressure": "CURRENT DEFECT (A5/A6 cross-issue): peg_defense reads STATIC cfg.r_interest + world MEAN -- Taylor/manual rate moves never affected reserve pressure in any run incl. the portraits; must read live anchor._rate - pegger._rate",
    "Policy.mortgage_dsti_cap": "MortgageBook init snapshot (only LTV re-syncs)",
    "Policy.omo": "metrics enable-check/fallback still read Config (split-brain)",
}

# ---- [N] new target levers (exist in NO source today) ----
POLICY_NEW = {
    "monetary_regime",
    # bank_leverage_cap: IMPLEMENTED in B4a (now a Policy field; left the [N] set)
    # A3/A4 rulings (2026-07-18): the two NEW levers that carry the government's
    # actual choices, cleanly split from the technology/pricing bases kept in Config
    "jg_public_works_share",   # default 1.0 = today's implicit share (bit-identical)
    "deposit_rate_floor",      # default 0.0 = never binds (bit-identical)
}

# ---- Config source ----
CONFIG_POLICY_MIGRATE: set[str] = set()   # B4 COMPLETE: all 39 [C] migrated
# (fiscal B4e; monetary beliefs B4c; quantity B4e; debt mgmt B4d cohort; bank
# macroprudential B4a; mortgage regulation B4b; insolvency/eviction law, energy
# regime, land block and audit reclassifications B4e. The three renames --
# firm_capital_haircut/firm_inventory_haircut -> regulatory_*, land_convexity ->
# land_fee_stock_elasticity -- carry legacy aliases in the registry and appear
# in POLICY_RENAMED_FROM below so their config names stay classified.)

CONFIG_PENDING_RULING: set[str] = set()   # all five closed 2026-07-18

# A5 ruling: Config fields that demote into the PolicySeed (initial stances, not levers)
CONFIG_POLICYSEED_PROMOTED = {"r_interest"}   # -> PolicySeed.initial_policy_rate

CONFIG_SHOCK_MODULE = {"energy_shock_at", "energy_shock_magnitude", "energy_shock_duration"}

# Config.X that seed Policy.X via from_legacy_config (the 43 same-name collisions)
# Policy fields WITHOUT a Config counterpart (no legacy seed): the 3 originals +
# every [N] lever implemented into Policy (they seed from PolicySeed, not Config)
_NO_CONFIG_COUNTERPART = {"tax_necessity_rate", "tax_luxury_rate", "policy_rate_override",
                          "bank_leverage_cap"}
# Policy fields renamed at migration: Policy new name -> Config legacy seed name
POLICY_RENAMED_FROM = {
    "regulatory_firm_capital_haircut": "firm_capital_haircut",
    "regulatory_firm_inventory_haircut": "firm_inventory_haircut",
    "land_fee_stock_elasticity": "land_convexity",
}
CONFIG_POLICY_SEED_LEGACY = ({
    f.name for f in dataclasses.fields(Policy)
} - _NO_CONFIG_COUNTERPART - set(POLICY_RENAMED_FROM)) | set(POLICY_RENAMED_FROM.values())

CONFIG_STRUCTURE = {
    "n_households", "n_firms", "n_ticks", "seed", "a", "n_firms_c", "n_firms_k",
    "n_firms_e", "n_banks", "n_builders", "d_household0", "d_firm0", "d_cfirm0",
    "d_kfirm0", "d_efirm0", "d_bank0", "p_firm0", "p_kfirm0", "p_efirm0", "w_firm0",
    "inv_firm0", "inv_kfirm0", "mu_firm0", "demand_e_firm0", "startup_deposits",
    "startup_capital", "float_shares", "shares_per_firm", "watchlist_size",
    "genesis_founder_pool", "founder_owned_genesis", "bank_capital_frac",
    "house_price_income_years", "ticks_per_year", "energy_util0",
    "demographics_population", "K_firm0",
}

CONFIG_PHYSICS = {
    "lambda_d", "lambda_y", "phi", "eta", "mu_min", "mu_max", "theta_price", "delta",
    "wage_indexation", "omega", "theta_wage", "alpha1", "alpha2",
    "lifecycle_alpha_income", "lifecycle_alpha_wealth_draw", "mpc_dispersion",
    "mpc_wealth_curvature", "rho", "search_m", "alpha", "v", "dis_slope",
    "gibrat_sigma", "pref_attach_beta", "pref_price_elasticity", "gibrat_entry_a0",
    "portfolio_adjust", "q_invest_smooth", "lambda_p", "w_chartist", "w_fundamental",
    "theta_equity", "trend_lambda", "wealth_effect", "equity_ema_lambda",
    "resid_income_lambda", "lambda_q", "q_invest_floor", "q_invest_cap",
    "lambda_issue", "hh_subsistence", "hh_amort", "amort",
    "investment_user_cost_elasticity", "investment_user_cost_multiplier_min",
    "investment_user_cost_multiplier_max", "investment_user_cost_floor",
    "valuation_discount_floor", "valuation_risk_premium", "energy_intensity",
    "energy_coverage_ticks", "energy_gap_close", "energy_hoarding_beta",
    "energy_hh_share", "energy_mortality_gamma", "energy_mortality_mult_hi",
    "welfare_quit_hazard", "reservation_markup", "efficiency_sigma",
    "job_search_intensity", "ladder_search_intensity", "ladder_premium",
    "churn_annual", "lambda_fire", "layoff_band", "layoff_target_smooth",
    "suspension_timer", "suspension_quit_discount", "inventory_gap_close",
    "subscale_viability_workers", "subscale_grace_days", "subscale_exit_hazard",
    "k_entry_demand", "k_entry_hazard", "entry_beta", "entry_max",
    "shell_exit_ticks", "real_entry_signal", "entry_hurdle",
    "capital_clock_demand_smoothing", "bank_leverage_mean", "bank_leverage_disp",
    "bank_spread_disp", "bank_search_m", "deposit_rate_disp", "deposit_search_m",
    "bank_equity_lambda", "bank_theta_equity", "bank_entry_beta", "bank_entry_max",
    "run_sensitivity", "run_health_ref", "run_market_weight", "run_fear_persistence",
    "interbank_rate_base", "interbank_tightness", "bond_theta", "bank_bond_appetite",
    "rent_yield0", "rent_adjust", "rent_burden_cap", "rental_investor_premium",
    "housing_ask_markup", "housing_forced_discount", "housing_ask_decay",
    "housing_search_k", "housing_buyer_buffer", "housing_distress_floor",
    "housing_session_interval", "builder_productivity", "builder_demand_seed",
    "housing_wealth_effect", "family_transfer_buffer", "switch_retool_loss",
    "switch_return_gap", "switch_pressure_days", "switch_hazard", "necessity_share0",
    "n_firm_share", "subsistence_share", "tfp_drift_rate", "tfp_drift_sigma",
    "tfp_law", "tfp_learning_theta", "tfp_drift_c", "tfp_drift_k", "tfp_drift_e",
    "public_capital_gamma", "public_capital_depreciation", "lambda_I", "delta_K",
    "A", "a_K", "kappa_E", "a_E",
    # A3/A4 rulings: technology & private-pricing bases stay Config
    "jg_productivity",          # public-works TECHNOLOGY; the government's lever is [N] jg_public_works_share
    "deposit_rate",             # -> deposit_rate_base at migration (private bank pricing base)
    # demography physics
    "demographics_tfr", "demographics_mortality_scale",
    "demographic_marriage_market_interval_days",
    "demographic_annual_marriage_rate_peak", "demographic_annual_divorce_rate_base",
    "demographic_leave_home_min_age", "demographic_leave_home_peak_end_age",
    "demographic_annual_leave_rate_peak", "demographic_annual_leave_rate_late",
    "fertility_income_elasticity", "fertility_mult_lo", "fertility_mult_hi",
    "mortality_income_elasticity", "mortality_mult_lo", "mortality_mult_hi",
    "mortality_rank_gradient", "fertility_rank_gradient", "strat_mult_lo",
    "strat_mult_hi", "marriage_assortativity", "housing_leave_elasticity",
    "housing_leave_mult_lo", "housing_leave_mult_hi", "housing_fertility_elasticity",
    "housing_fertility_mult_lo", "housing_fertility_mult_hi",
}

CONFIG_MECHANISM = {
    "demographics_enabled", "demographic_lifecycle_consumption",
    "demographic_marriage_enabled", "demographic_divorce_enabled",
    "demographic_adult_leaving_home_enabled", "housing_enabled",
    "housing_market_enabled", "mortgage_enabled", "housing_rental_enabled",
    "housing_construction_enabled", "labor_accounting", "labor_matching",
    "labor_fractional_hours", "labor_second_job", "labor_suspension",
    "labor_matching_friction", "labor_relationship_wages", "labor_job_ladder",
    "labor_person_efficiency", "labor_participation", "capital_rationed_signal",
    "consumption_rationed_signal", "firm_subscale_exit", "capital_firm_entry",
    "firm_full_pnl", "capital_service_pricing", "priced_firm_balance_sheet",
    "bank_enabled", "bank_realized_pnl", "bank_assignment", "bank_rate_competition",
    "bank_relationship_lock_in", "interbank", "bank_equity", "bank_equity_trading",
    "bank_dynamics", "bank_runs", "bonds", "government", "capital_market",
    "per_firm_equity", "equity_finance", "household_credit",
    "household_interest_arrears", "margin_credit", "gibrat_growth", "firm_dynamics",
    "symmetric_k", "k_replacement_floor", "energy_enabled", "energy_household",
    "deprivation_gauges", "national_accounts_metrics", "consumption_strata",
    "family_transfers", "sector_switching", "monetary_direct_transmission",
    "interest_by_deposits", "index_startup", "capital_annual_clock",
    "pro_rata_dividends",
}

CONFIG_INFRA = {
    "claims_reconcile_interval", "ledger_rel_tol", "bond_maturity_bucket",
    "capital_service_min_utilization", "rental_vacancy_deadband",
    "rental_rent_floor_wage_share", "housing_demand_step", "cpi_item_link_cap",
    "cpi_rebase_interval_days", "demo_feedback_burnin_years",
    "demo_signal_halflife_years", "housing_signal_burnin_years",
    "energy_signal_burnin_years", "deprivation_burnin_years",
    "deprivation_acute_days", "deprivation_chronic_days",
    "_capital_annual_clock_applied", "taylor_phi_pi", "taylor_phi_u",
}
# NOTE: Config.taylor_phi_pi / taylor_phi_u are ALSO in CONFIG_POLICY_SEED_LEGACY;
# they are removed from INFRA below if present in the seed set (exclusivity guard
# would catch it) — kept here ONLY if not seeds. Resolved at table-build time.
CONFIG_INFRA -= CONFIG_POLICY_SEED_LEGACY

# ---- World source (keyword tunables) ----
WORLD_POLICY = {
    "capital_control", "tariff", "import_quota", "export_subsidy", "sanctions",
    "remittance_tax", "outward_remittance_tax", "immigration_cap", "emigration_cap",
    "guest_worker_return", "peg", "peg_anchor", "peg_reserve_scale",
    "external_interest_settlement_fraction",
}
WORLD_PENDING_MIGRATION = {"peg_economy"}   # PROPOSED deletion; blocked on §5.1 multi-pegger ruling
WORLD_STRUCTURE = {"base_seed", "periods_per_year", "peg_reserves0"}
WORLD_MECHANISM = {"couple", "trade", "capital", "migration"}
WORLD_PHYSICS = {
    "fx_lambda", "fx_friction", "fx_trade_cap", "capital_mobility", "capital_adjust",
    "migration_rate", "migration_max_share", "remittance_share", "wage_smoothing",
}

# ---- Nested demographic configs ----
SOCIAL_POLICY_CANDIDATE = {
    "marriage_min_age", "remarriage_cooldown_days", "marriage_close_kin_forbidden",
    "marriage_same_household_forbidden", "divorce_min_marriage_duration_days",
    "custody_mother_priority", "custody_keep_siblings_together",
    "guardianship_enabled", "guardian_prefer_kin",
}
RELATIONSHIP_POLICY_CANDIDATE = {"adult_age"}   # legal adulthood
LIFECYCLE_POLICY_CANDIDATE: set[str] = set()

# ---- Hardcoded-institution registry (§1.6) ----
HARDCODED = [
    # (id, file, verify-pattern-or-None, note)
    ("rate_floor_zero", "macro_sim/systems/central_bank.py", "max(0.0",
     "policy-rate floor hard-coded 0 (r_max exists, r_min does not)"),
    ("working_age_window", "macro_sim/demographics/economic_state.py", "min_age: int = 18",
     "working age 18-64; split labor_min_age/statutory_retirement_age"),
    ("intestate_succession", "macro_sim/demographics/inheritance.py", None,
     "estate tax 0; spouse/children 50/50 succession"),
    ("probate_window", "macro_sim/demographics/economic_bridge.py", None,
     "probate window fixed 365d"),
    ("same_sex_restriction", "macro_sim/demographics/social.py", "a.sex == b.sex",
     "same-sex marriage restriction is a literal"),
    ("marital_gain_split", "macro_sim/demographics/marriage_economics.py", "/ 2.0",
     "50/50 marital-gain split literal"),
    ("ordinary_credit_rwa", None, None, "ordinary-credit RWA fixed 100%"),
    ("resolution_full_cover", None, None, "resolution fund covers 100% of residual"),
    ("lolr_full_gap", None, None, "LoLR funds the full gap"),
    ("mortgage_non_recourse", None, None, "mortgages fixed non-recourse"),
    ("bankruptcy_full_discharge", None, None, "household bankruptcy = full discharge"),
    ("spr_sale_discount", None, None, "SPR sells at 99.9% of market"),
    ("cap_compensation_share", None, None, "energy price-cap compensation = 100% of gap"),
    ("gov_procurement_mix", None, None, "government procurement composition non-adjustable"),
]


# ======================================================================
def discover() -> dict[str, set[str]]:
    fields = {
        "Config": {f.name for f in dataclasses.fields(Config)},
        "Policy": {f.name for f in dataclasses.fields(Policy)},
        "Social": {f.name for f in dataclasses.fields(SocialDynamicsConfig)},
        "Relationship": {f.name for f in dataclasses.fields(RelationshipConfig)},
        "Lifecycle": {f.name for f in dataclasses.fields(LifecycleHouseholdConfig)},
    }
    sig = inspect.signature(World.__init__)
    fields["World"] = {n for n in sig.parameters if n not in ("self", "configs")}
    return fields


def classification() -> dict[str, dict[str, set[str]]]:
    return {
        "Config": {
            "POLICY_MIGRATE": CONFIG_POLICY_MIGRATE,
            "PENDING_RULING": CONFIG_PENDING_RULING,
            "SHOCK_MODULE": CONFIG_SHOCK_MODULE,
            "POLICY_SEED_LEGACY": CONFIG_POLICY_SEED_LEGACY,
            "POLICYSEED_PROMOTED": CONFIG_POLICYSEED_PROMOTED,
            "STRUCTURE": CONFIG_STRUCTURE,
            "PHYSICS": CONFIG_PHYSICS,
            "MECHANISM": CONFIG_MECHANISM,
            "INFRA": CONFIG_INFRA,
        },
        "Policy": {"POLICY_LIVE": {f.name for f in dataclasses.fields(Policy)}},
        "World": {
            "POLICY_WORLD": WORLD_POLICY,
            "PENDING_MIGRATION": WORLD_PENDING_MIGRATION,
            "STRUCTURE": WORLD_STRUCTURE,
            "MECHANISM": WORLD_MECHANISM,
            "PHYSICS": WORLD_PHYSICS,
        },
        "Social": {
            "NESTED_POLICY_CANDIDATE": SOCIAL_POLICY_CANDIDATE,
            "NESTED_PHYSICS": {f.name for f in dataclasses.fields(SocialDynamicsConfig)}
                              - SOCIAL_POLICY_CANDIDATE,
        },
        "Relationship": {
            "NESTED_POLICY_CANDIDATE": RELATIONSHIP_POLICY_CANDIDATE,
            "NESTED_PHYSICS": {f.name for f in dataclasses.fields(RelationshipConfig)}
                              - RELATIONSHIP_POLICY_CANDIDATE,
        },
        "Lifecycle": {
            "NESTED_POLICY_CANDIDATE": LIFECYCLE_POLICY_CANDIDATE,
            "NESTED_PHYSICS": {f.name for f in dataclasses.fields(LifecycleHouseholdConfig)}
                              - LIFECYCLE_POLICY_CANDIDATE,
        },
    }


def verify() -> list[str]:
    errors: list[str] = []
    fields = discover()
    tables = classification()

    for source, discovered in fields.items():
        buckets = tables[source]
        seen: dict[str, str] = {}
        for bucket, names in buckets.items():
            for n in names:
                if n in seen:
                    errors.append(f"DUPLICATE {source}.{n}: {seen[n]} AND {bucket}")
                seen[n] = bucket
        unclassified = discovered - set(seen)
        stale = set(seen) - discovered
        for n in sorted(unclassified):
            errors.append(f"UNCLASSIFIED {source}.{n}")
        for n in sorted(stale):
            errors.append(f"STALE {source}.{n} (classified as {seen[n]}, not in source)")

    # derived views: wholesale
    views = [n for n in dir(_schema)
             if inspect.isclass(getattr(_schema, n)) and dataclasses.is_dataclass(getattr(_schema, n))]
    if len(views) < 5:
        errors.append(f"schema.py derived views suspiciously few: {views}")

    # count identities (docs/policy_module_v25.md)
    c = {
        "P": len(fields["Policy"]),
        "C": len(CONFIG_POLICY_MIGRATE),
        "W": len(WORLD_POLICY),
        "PENDING": len(CONFIG_PENDING_RULING),
        "N": len(POLICY_NEW),
    }
    expect = {"P": 86, "C": 0, "W": 14, "PENDING": 0, "N": 3}   # B4 COMPLETE: all [C] migrated
    for k, v in expect.items():
        if c[k] != v:
            errors.append(f"COUNT {k}: {c[k]} != {v}")
    candidates = c["P"] + c["C"] + c["W"] + c["N"] - 1   # −1: dead Policy.central_bank replaced by monetary_regime
    if candidates != 102:
        errors.append(f"COUNT candidates: {candidates} != 102 (A5/A6 closed: 46+39+14+4-1)")

    # hardcoded registry verification
    for hid, fname, pattern, _note in HARDCODED:
        if fname is None:
            continue
        p = ROOT / fname
        if not p.exists():
            errors.append(f"HARDCODED {hid}: missing file {fname}")
        elif pattern is not None and pattern not in p.read_text():
            errors.append(f"HARDCODED {hid}: pattern {pattern!r} not found in {fname}")
    return errors


def main() -> int:
    errors = verify()
    fields = discover()
    total = sum(len(v) for v in fields.values())
    print(f"sources: " + ", ".join(f"{k}={len(v)}" for k, v in fields.items()) + f"  (total {total})")
    print(f"policy candidates: 86[P] + 0[C] + 14[W] + 3[N] - 1(dead) = 102 ; PENDING = 0 ; +1 seed-promoted (r_interest -> initial_policy_rate)")
    print(f"hardcoded registry: {len(HARDCODED)} entries "
          f"({sum(1 for h in HARDCODED if h[1] is not None)} file-verified, rest curated)")
    print("NOTE: function-default/literal scan beyond the curated registry is a staged follow-up.")
    if errors:
        print(f"\n{len(errors)} ERRORS:")
        for e in errors:
            print("  " + e)
        return 1
    print("\nOK: every source field classified exactly once; counts match the design doc.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
