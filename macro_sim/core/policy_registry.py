"""v25 B3: the declarative policy-lever registry.

One declaration per lever = validation + random-controller domain + RL action
space + frontend form + audit trail (docs/policy_module_v25.md §2). Schema per
the five audit rounds: per-TYPE validation union, owner/scope, effective
semantics (non-immediate semantics must bind a handler id), capability
dependencies (Config mechanism flags required for the lever to mean anything),
`shadowed_by` (levers/states that render this one inert -- executable in
tests/test_policy_effectiveness.py), the unique runtime read-point, and free
state-notes from the B1 coverage matrix.

`set_lever(econ, name, value, actor=...)` is the ONLY sanctioned mutation path
for controllers: validate -> apply -> append an action event (the provisional
envelope; .msim events.log integration lands with the P1 controllers).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- validation types

@dataclass(frozen=True)
class Range:
    lo: float
    hi: float
    max_step: float | None = None       # per-action step cap (None = unbounded)

    def check(self, old: Any, new: Any) -> str | None:
        try:
            v = float(new)
        except (TypeError, ValueError):
            return f"not a number: {new!r}"
        if not (self.lo <= v <= self.hi):
            return f"{v} outside [{self.lo}, {self.hi}]"
        if self.max_step is not None and old is not None:
            if abs(v - float(old)) > self.max_step + 1e-15:
                return f"step {abs(v - float(old)):.4g} exceeds max_step {self.max_step}"
        return None


@dataclass(frozen=True)
class NullableRange(Range):
    def check(self, old: Any, new: Any) -> str | None:
        if new is None:
            return None
        return super().check(old if old is not None else None, new)


@dataclass(frozen=True)
class Bool:
    def check(self, old: Any, new: Any) -> str | None:
        return None if isinstance(new, bool) else f"not a bool: {new!r}"


@dataclass(frozen=True)
class Choices:
    values: tuple[str, ...]

    def check(self, old: Any, new: Any) -> str | None:
        return None if new in self.values else f"{new!r} not in {self.values}"


# ---------------------------------------------------------------- lever schema

IMMEDIATE = "immediate"                  # takes effect on the next tick's reads
NEW_CONTRACTS = "new-contracts-only"     # existing stock never restated
STATE_TRANSITION = "state-transition"    # requires a bound transition handler


@dataclass(frozen=True)
class Lever:
    name: str
    validation: Any
    scope: str = "economy"               # economy | bilateral | world  (all [P] today: economy)
    semantics: str = IMMEDIATE
    handler_id: str | None = None        # REQUIRED when semantics != immediate/new-contracts
    requires: frozenset[str] = frozenset()   # Config capability flags
    shadowed_by: tuple[str, ...] = ()    # levers/states that render this one inert
    read_point: str = ""
    state_notes: str = ""                # B1 coverage-matrix observations

    def __post_init__(self):
        if self.semantics == STATE_TRANSITION and not self.handler_id:
            raise ValueError(f"{self.name}: state-transition semantics with no handler_id")


def _L(name, validation, **kw):
    return Lever(name=name, validation=validation, **kw)


# ---------------------------------------------------------------- the registry (46 [P])

REGISTRY: dict[str, Lever] = {lv.name: lv for lv in [
    # -- fiscal: spending & transfers --
    _L("gov_consumption_share", Range(0.0, 0.6), requires=frozenset({"government"}),
       shadowed_by=("gov_deficit_target>0",),
       read_point="systems/goods.py::tender (elif branch)",
       state_notes="NO-OP while gov_deficit_target>0 (v13 preset defaults 0.03)"),
    _L("gov_deficit_target", Range(0.0, 0.3), requires=frozenset({"government"}),
       read_point="systems/goods.py::tender (if branch)"),
    _L("deficit_u_ref", Range(0.0, 1.0), requires=frozenset({"government"}),
       read_point="systems/goods.py::tender taper"),
    _L("benefit_replacement", Range(0.0, 1.5), requires=frozenset({"government"}),
       shadowed_by=("job_guarantee",),
       read_point="systems/settlement.py::unemployment benefit",
       state_notes="base = UNSOLD labour: zero at full employment AND identically zero "
                   "under the uncapped JG; observable only in slack windows"),
    _L("benefit_income_floor", Range(0.0, 1.5), requires=frozenset({"government"}),
       read_point="systems/settlement.py::in-work top-up"),
    _L("pension_replacement", Range(0.0, 1.5), requires=frozenset({"government"}),
       read_point="systems/settlement.py::pension",
       state_notes="metric note: benefit_paid INCLUDES pensions (double-post)"),
    # -- fiscal: taxes --
    _L("tax_profit_rate", Range(0.0, 0.8), requires=frozenset({"government"}),
       read_point="systems/settlement.py::profit tax"),
    _L("tax_income_rate", Range(0.0, 0.8), requires=frozenset({"government"}),
       read_point="systems/settlement.py::income tax"),
    _L("income_allowance", Range(0.0, 5.0), requires=frozenset({"government"}),
       read_point="systems/settlement.py::income tax allowance"),
    _L("tax_consumption_rate", Range(0.0, 0.6), requires=frozenset({"government"}),
       read_point="systems/goods.py::VAT remit"),
    _L("tax_necessity_rate", NullableRange(0.0, 0.6), requires=frozenset({"government", "consumption_strata"}),
       read_point="systems/goods.py::_vat_rates"),
    _L("tax_luxury_rate", NullableRange(0.0, 0.8), requires=frozenset({"government", "consumption_strata"}),
       read_point="systems/goods.py::_vat_rates"),
    _L("tax_wealth_rate", Range(0.0, 0.05), requires=frozenset({"government"}),
       read_point="systems/settlement.py::wealth tax"),
    _L("wealth_allowance", Range(0.0, 10.0), requires=frozenset({"government"}),
       read_point="systems/settlement.py::wealth tax exemption"),
    _L("tax_energy_rate", Range(0.0, 1.0), requires=frozenset({"government", "energy_enabled"}),
       read_point="systems/energy.py::excise"),
    _L("tax_energy_windfall", Range(0.0, 0.9), requires=frozenset({"government", "energy_enabled"}),
       read_point="systems/energy.py::windfall surtax"),
    # -- energy policy --
    _L("spr_target_units", Range(0.0, 1.0e6), requires=frozenset({"government", "energy_enabled"}),
       read_point="systems/energy.py::SPR"),
    _L("spr_flow_cap", Range(0.0, 1.0e4), requires=frozenset({"government", "energy_enabled"}),
       read_point="systems/energy.py::SPR flow"),
    _L("soe_price_at_cost", Bool(), requires=frozenset({"government", "energy_enabled", "soe_efirm"}),
       read_point="systems/energy.py:251",
       state_notes="FILED direction anomaly: at-cost pricing RAISED market avg ~3%"),
    _L("energy_price_cap", Range(0.0, 1.0e3), requires=frozenset({"government", "energy_enabled"}),
       read_point="systems/energy.py::ask clamp", state_notes="0 = off"),
    _L("energy_rationing", Choices(("market", "household_first", "industry_first")),
       requires=frozenset({"government", "energy_enabled"}),
       read_point="systems/energy.py::shortage allocation",
       state_notes="only observable under SHORTAGE (fixture gap; shock-module territory)"),
    _L("energy_cap_compensation", Bool(), requires=frozenset({"government", "energy_enabled"}),
       read_point="systems/energy.py:469"),
    _L("energy_subsidy_rate", Range(0.0, 1.0), requires=frozenset({"government", "energy_enabled", "energy_household"}),
       read_point="systems/energy.py::household rebate"),
    _L("energy_subsidy_threshold", Range(0.0, 10.0), requires=frozenset({"government", "energy_enabled", "energy_household"}),
       read_point="systems/energy.py::rebate targeting"),
    # -- labour --
    _L("min_wage", Range(0.0, 10.0), requires=frozenset({"government"}),
       read_point="behavior/planning.py::wage floor",
       state_notes="observable via min_wage_binding_firm_share"),
    _L("job_guarantee", Bool(), requires=frozenset({"government"}),
       read_point="systems/settlement.py::JG",
       state_notes="activity (jg_employment) observable only in slack windows; "
                   "job_guarantee_wage metric is a PASSIVE gauge"),
    _L("jg_wage_ratio", Range(0.0, 1.5), requires=frozenset({"government"}),
       read_point="systems/settlement.py::JG wage"),
    # -- monetary: rate rule --
    _L("central_bank", Bool(), requires=frozenset(),
       read_point="DEAD (systems/central_bank.py reads cfg) -- deleted at migration",
       state_notes="strict-xfail; replaced by monetary_regime [N]"),
    _L("inflation_target", Range(-0.02, 0.02), requires=frozenset(),
       read_point="systems/central_bank.py::Taylor gap",
       state_notes="Taylor family inert at the ZLB AND at r_max (two-sided clamp); "
                   "liveness via interior liftoff (pi* = -2e-3)"),
    _L("taylor_phi_pi", Range(0.0, 10.0), requires=frozenset(),
       read_point="systems/central_bank.py", shadowed_by=("ZLB/r_max clamp",)),
    _L("taylor_phi_u", Range(0.0, 10.0), requires=frozenset(),
       read_point="systems/central_bank.py", shadowed_by=("ZLB/r_max clamp",)),
    _L("rate_inertia", Range(0.0, 0.9999), requires=frozenset(),
       read_point="systems/central_bank.py", shadowed_by=("ZLB/r_max clamp",)),
    _L("policy_rate_override", NullableRange(0.0, 0.01), requires=frozenset(),
       read_point="systems/central_bank.py::override (precedes the cfg gate)",
       state_notes="renamed manual_policy_rate at migration; regime==manual <=> set"),
    # -- monetary: beliefs & measurement (B4c migration) --
    _L("r_neutral", Range(0.0, 0.05), read_point="systems/central_bank.py::r_target",
       state_notes="the CB's revisable neutral-rate estimate"),
    _L("u_natural", Range(0.0, 0.5), read_point="systems/central_bank.py::u gap"),
    _L("r_max", Range(1e-6, 0.5), read_point="systems/central_bank.py::ceiling clamp",
       state_notes="the cap that disarmed CBs in the v1 portrait"),
    _L("infl_ema_lambda", Range(1e-4, 1.0), read_point="systems/central_bank.py::sensor"),
    _L("cb_core_inflation", Bool(), requires=frozenset({"energy_enabled"}),
       read_point="reporting/metrics.py::CB input selection"),
    _L("cb_uses_fixed_basket_cpi", Bool(),
       read_point="reporting/metrics.py::CB input selection",
       state_notes="the Germany lesson: the target-index choice is itself policy"),
    _L("cb_log_inflation", Bool(), read_point="reporting/metrics.py::CB input transform"),
    _L("fiscal_uses_national_accounts_gdp", Bool(), requires=frozenset({"government"}),
       read_point="reporting/metrics.py::fiscal GDP basis"),
    # -- Treasury debt management (B4d) --
    _L("bond_finance_frac", Range(0.0, 1.0), requires=frozenset({"bonds", "government"}),
       read_point="systems/securities.py::issuance gate + gap"),
    _L("bond_coupon", Range(0.0, 0.01), requires=frozenset({"bonds"}),
       semantics=NEW_CONTRACTS, handler_id="bond_coupon_cohort",
       read_point="systems/securities.py::lot stamp at issuance; pay/price/merge per lot",
       state_notes="the first real NEW_CONTRACTS cohort: stock is never re-couponed; "
                   "consolidation key includes the coupon so cohorts cannot corrupt"),
    _L("bond_maturity", Range(1, 36500), requires=frozenset({"bonds"}),
       semantics=NEW_CONTRACTS, handler_id="bond_tenor_at_issuance",
       read_point="systems/securities.py::issued_maturity"),
    # -- monetary: quantity tools --
    _L("omo", Bool(), requires=frozenset({"bonds", "interbank"}),
       read_point="systems/central_bank.py::OMO + reporting/metrics.py (B2 fixed)"),
    _L("omo_reserve_target", Range(0.0, 5.0), requires=frozenset({"bonds", "interbank"}),
       read_point="systems/central_bank.py::OMO target"),
    _L("omo_drain_frac", Range(0.0, 1.0), requires=frozenset({"bonds", "interbank"}),
       read_point="systems/central_bank.py::OMO speed"),
    _L("lolr", Bool(), requires=frozenset({"bonds", "interbank"}),
       read_point="systems/banking.py::LOLR",
       state_notes="only observable in a bank-run crisis (fixture gap; X2 world)"),
    # -- macroprudential: banks (B4a migration; all credit-dormant fixture gap for A/B) --
    _L("bank_capital_constraint", Bool(), requires=frozenset({"bank_enabled"}),
       read_point="systems/banking.py::bank_constraint"),
    _L("bank_leverage_cap", Range(0.0, 50.0), requires=frozenset({"bank_enabled"}),
       read_point="systems/banking.py::bank_capacity (min over kappa_bank)",
       state_notes="[N] created per A-track ruling: the REGULATORY ceiling; the per-bank "
                   "appetite draw bank_leverage_mean stays Config physics. 0 = off"),
    _L("bank_target_capital_ratio", Range(0.0, 1.0), requires=frozenset({"bank_enabled"}),
       read_point="systems/credit.py::payout rule x2"),
    _L("bank_exposure_limit", Range(0.0, 1.0), requires=frozenset({"bank_enabled"}),
       read_point="systems/banking.py::concentration room + metrics"),
    _L("bank_min_capital", Range(0.0, 1.0e5), requires=frozenset({"bank_enabled"}),
       read_point="systems/banking.py::charter gate"),
    _L("bank_bond_duration_limit", Range(0.0, 20.0), requires=frozenset({"bonds"}),
       read_point="systems/securities.py::bond-book room"),
    _L("bank_resolution_fund", Bool(), requires=frozenset({"bank_enabled", "government"}),
       read_point="systems/banking.py::resolution backstop x2"),
    _L("reserve_floor_frac", Range(0.0, 1.0), requires=frozenset({"interbank"}),
       read_point="systems/banking.py + securities.py + central_bank.py (indexed OMO)"),
    # -- macroprudential --
    _L("margin_ltv", Range(0.0, 1.0), requires=frozenset({"margin_credit"}),
       read_point="systems/credit.py::margin", state_notes="credit-dormant fixture gap"),
    _L("margin_max", Range(0.0, 10.0), requires=frozenset({"margin_credit"}),
       read_point="systems/credit.py::margin cap", state_notes="credit-dormant fixture gap"),
    _L("kappa", Range(0.0, 20.0), requires=frozenset({"bank_enabled"}),
       read_point="systems/credit.py::firm leverage cap", state_notes="credit-dormant fixture gap"),
    _L("hh_credit_limit", Range(0.0, 20.0), requires=frozenset({"household_credit"}),
       read_point="systems/credit.py::household DTI", state_notes="credit-dormant fixture gap"),
    _L("mortgage_ltv_cap", Range(0.0, 1.0), requires=frozenset({"mortgage_enabled"}),
       read_point="housing/mortgage.py::_sync_policy (per-session B2 channel)"),
    _L("mortgage_underwriting", Bool(), requires=frozenset({"mortgage_enabled"}),
       read_point="housing/mortgage.py::_sync_policy"),
    _L("mortgage_dsti_cap", Range(0.0, 2.0), requires=frozenset({"mortgage_enabled"}),
       semantics=NEW_CONTRACTS, read_point="housing/mortgage.py::_sync_policy"),
    _L("mortgage_stress_rate_addon", Range(0.0, 0.01), requires=frozenset({"mortgage_enabled"}),
       semantics=NEW_CONTRACTS, read_point="housing/mortgage.py::_sync_policy"),
    _L("mortgage_risk_weight", Range(0.0, 2.0), requires=frozenset({"mortgage_enabled"}),
       read_point="housing/mortgage.py::_sync_policy + systems/banking.py::RWA"),
    _L("mortgage_min_capital_ratio", Range(0.0, 1.0), requires=frozenset({"mortgage_enabled"}),
       read_point="housing/mortgage.py::_sync_policy + banking RWA + metrics"),
    _L("mortgage_foreclosure_ltv", Range(0.5, 5.0), requires=frozenset({"mortgage_enabled"}),
       read_point="housing/mortgage.py::_sync_policy (foreclosure law)"),
    _L("mortgage_arrears_floor", Range(0.0, 100.0), requires=frozenset({"mortgage_enabled"}),
       read_point="housing/mortgage.py::_sync_policy (foreclosure law)"),
    # -- housing fiscal --
    _L("housing_permits", Range(0.0, 1.0e5), requires=frozenset({"housing_construction_enabled"}),
       read_point="housing/construction.py::permit quota"),
    _L("housing_transfer_tax", Range(0.0, 0.3), requires=frozenset({"housing_market_enabled"}),
       read_point="housing/market.py::stamp duty",
       state_notes="needs resale transactions (long-horizon fixture gap)"),
    _L("housing_property_tax", Range(0.0, 0.1), requires=frozenset({"housing_enabled"}),
       read_point="housing/market.py::_collect_property_tax"),
    _L("housing_in_wealth_tax", Bool(), requires=frozenset({"housing_enabled"}),
       read_point="systems/settlement.py::wealth-tax base"),
]}


# ---------------------------------------------------------------- mutation API

def set_lever(econ: Any, name: str, value: Any, *, actor: str = "controller",
              target: Any = None) -> None:
    """The sanctioned mutation path: validate -> apply -> log (provisional envelope)."""
    lever = REGISTRY.get(name)
    if lever is None:
        raise KeyError(f"unknown policy lever: {name}")
    for cap in lever.requires:
        if not getattr(econ.cfg, cap, False):
            raise ValueError(f"{name}: missing capability {cap}")
    old = getattr(econ.policy, name, None)
    err = lever.validation.check(old, value)
    if err:
        raise ValueError(f"{name}: {err}")
    setattr(econ.policy, name, value)
    log = getattr(econ, "_policy_action_log", None)
    if log is None:
        log = econ._policy_action_log = []
    log.append({
        "tick": getattr(econ, "t", -1), "actor_economy": getattr(econ, "world_index", 0),
        "lever": name, "old": old, "new": value, "actor": actor,
        "target": target, "direction": None, "scope": lever.scope,
        "sequence": len(log), "schema_version": 0,   # provisional envelope (A6 pending freeze)
    })
