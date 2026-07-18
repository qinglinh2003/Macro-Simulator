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


class EconomySet:
    """Validation for frozenset-of-economy-id levers (sanctions)."""
    def check(self, old: Any, new: Any) -> str | None:
        if not isinstance(new, frozenset):
            return f"expected a frozenset of economy ids, got {type(new).__name__}"
        for j in new:
            if isinstance(j, bool) or not isinstance(j, int) or j < 0:
                return f"economy ids must be non-negative ints, got {j!r}"
        return None


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
    # (the dead central_bank flag is DELETED; monetary_regime is the rate path now)
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
    _L("manual_policy_rate", NullableRange(0.0, 0.01), requires=frozenset(),
       read_point="systems/central_bank.py::manual branch",
       state_notes="renamed from policy_rate_override; applies ONLY in regime=manual "
                   "(may be staged in any regime; the switch handler checks it)"),
    _L("monetary_regime", Choices(("exogenous", "taylor", "manual")),
       semantics=STATE_TRANSITION, handler_id="monetary_regime_switch",
       read_point="systems/central_bank.py::set_policy_rate (the whole rate path)",
       state_notes="A5: three-state regime replacing the dead central_bank flag; "
                   "switch INTO manual requires manual_policy_rate staged; leaving "
                   "manual clears it (manual <=> rate set); the sensor runs in "
                   "taylor AND manual, off in exogenous"),
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
    # -- [N] levers --
    _L("jg_public_works_share", Range(0.0, 1.0), requires=frozenset({"government"}),
       read_point="systems/settlement.py::JG capital units"),
    _L("deposit_rate_floor", Range(0.0, 0.01),
       requires=frozenset({"bank_enabled", "bank_realized_pnl"}),
       read_point="systems/credit.py::deposit funding cost floor",
       state_notes="the WHOLE deposit-interest leg lives inside finalize_bank_pnl, "
                   "gated on bank_realized_pnl -- without it deposit_rate AND the "
                   "floor are dead (found by the effectiveness scaffold)"),
    # -- fiscal structure (B4e) --
    _L("deficit_u_cap", Range(0.0, 10.0), requires=frozenset({"government"}),
       read_point="systems/goods.py::slack-scaled deficit cap"),
    _L("gov_investment_share", Range(0.0, 0.2), requires=frozenset({"government"}),
       read_point="systems/capital_goods.py::public K budget + settlement accumulation"),
    # -- monetary plumbing (B4e) --
    _L("omo_index_deposits", Bool(), requires=frozenset({"omo"}),
       read_point="systems/central_bank.py::reserve-target indexing"),
    # -- insolvency & eviction law (B4e) --
    _L("bankrupt_persist", Range(1, 3650), read_point="systems/firm_demographics.py::death gate"),
    _L("household_bankruptcy", Bool(), requires=frozenset({"margin_credit"}),
       read_point="systems/equity.py::margin-debt discharge"),
    _L("rental_eviction_arrears", Range(1, 3650),
       read_point="housing/market.py::per-tick sync -> RentalMarket.eviction_arrears"),
    _L("bank_migrate_on_failure", Bool(), requires=frozenset({"bank_enabled"}),
       read_point="systems/banking.py::resolution borrower migration"),
    # -- regulatory (B4e; the haircut pair RENAMED regulatory_*) --
    _L("unified_bank_rwa", Bool(), requires=frozenset({"bank_enabled"}),
       read_point="systems/banking.py::unified_bank_rwa_enabled (helper reads Policy)"),
    _L("firm_credit_min_dscr", Range(0.0, 5.0), requires=frozenset({"bank_enabled"}),
       semantics=NEW_CONTRACTS, handler_id="underwriting_read_at_origination",
       read_point="systems/credit.py::DSCR floor (new loans only by construction)"),
    _L("regulatory_firm_capital_haircut", Range(0.0, 1.0), requires=frozenset({"bank_enabled"}),
       semantics=NEW_CONTRACTS, handler_id="underwriting_read_at_origination",
       read_point="systems/firm_balance_sheet.py::borrowing base",
       state_notes="renamed from firm_capital_haircut (legacy alias)"),
    _L("regulatory_firm_inventory_haircut", Range(0.0, 1.0), requires=frozenset({"bank_enabled"}),
       semantics=NEW_CONTRACTS, handler_id="underwriting_read_at_origination",
       read_point="systems/firm_balance_sheet.py::borrowing base",
       state_notes="renamed from firm_inventory_haircut (legacy alias)"),
    # -- land policy (B4e; elasticity RENAMED) --
    _L("land_fee_share", Range(0.0, 1.0), requires=frozenset({"housing_construction_enabled"}),
       semantics=NEW_CONTRACTS, handler_id="land_fee_at_construction_start",
       read_point="housing/construction.py::land fee at start (new units only)"),
    _L("land_fee_stock_elasticity", Range(0.0, 10.0),
       requires=frozenset({"housing_construction_enabled"}),
       semantics=NEW_CONTRACTS, handler_id="land_fee_at_construction_start",
       read_point="housing/construction.py::land fee convexity",
       state_notes="renamed from land_convexity (legacy alias)"),
    # -- ownership regime (B4e) --
    _L("soe_efirm", Bool(), semantics=STATE_TRANSITION, handler_id="soe_transition",
       read_point="genesis flag -> firm.state_owned; runtime flips via the handler",
       state_notes="the transition handler mutates e_firms[0].state_owned directly; "
                   "dividend routing reads the FIRM state, not the lever"),
    # -- external (B5a): per-economy owners of the World coupling vectors; all
    #    mutations take effect ATOMICALLY at the next coupling barrier --
    _L("tariff", Range(0.0, 5.0), scope="external",
       read_point="world/trade.py::_tariff_rate (importer's own rate)"),
    _L("import_quota", NullableRange(0.0, 100.0), scope="external",
       read_point="world/trade.py::import volume cap (None = open)"),
    _L("export_subsidy", Range(-0.99, 0.99), scope="external",
       read_point="world/trade.py::exporter subsidy (<0 = export tax)"),
    _L("capital_control", Range(0.0, 1.0), scope="external",
       read_point="world/capital.py::flow throttle (1 = closed account)"),
    _L("external_interest_settlement_fraction", Range(0.0, 1.0), scope="external",
       read_point="world/capital.py::external interest cash settlement"),
    _L("sanctions_imposed_on", EconomySet(), scope="external",
       read_point="world/world.py::sanctioned(i,j) OR-derived cache",
       state_notes="A6: unilateral ownership, symmetric effect; an imposer can lift "
                   "only its own stance; scope TODAY = trade partner choice + "
                   "migration destinations (capital flows do NOT consult it)"),
    _L("immigration_cap", NullableRange(0.0, 10.0), scope="external",
       read_point="world/migration.py::per-host admission ceiling (None = open)"),
    _L("emigration_cap", NullableRange(0.0, 10.0), scope="external",
       read_point="world/migration.py::origin exit cap (None = open)"),
    _L("remittance_tax", Range(0.0, 0.9), scope="external",
       read_point="world/migration.py::origin taxes the inflow"),
    _L("outward_remittance_tax", Range(0.0, 0.9), scope="external",
       read_point="world/migration.py::host taxes the outflow"),
    _L("guest_worker_return", Range(0.0, 1.0), scope="external",
       read_point="world/migration.py::host's temporary-migration return rate"),
    # -- FX regime (B5b): fx_regime is the AUTHORITY; peg_economy is derived --
    _L("fx_regime", Choices(("float", "peg")), scope="external",
       semantics=STATE_TRANSITION, handler_id="fx_regime_switch",
       read_point="world/world.py::_reconcile_peg_states (barrier authority)",
       state_notes="A6: no anchor consent; entering peg requires peg_anchor staged; "
                   "adoption acquires reserves at the next barrier; voluntary exit "
                   "releases pent-up pressure ONCE (orderly float still faces it); "
                   "P0: <=1 pegger, anchor never itself pegs"),
    _L("peg_anchor", NullableRange(0, 4096), scope="external",
       semantics=STATE_TRANSITION, handler_id="peg_anchor_change",
       read_point="world/world.py::_reconcile_peg_states",
       state_notes="A6 anchor change: liquidate old-anchor reserves -> convert at "
                   "the current cross -> acquire new -> reset pent_up"),
    _L("peg_reserve_scale", Range(1.0, 1.0e9), scope="external",
       read_point="world/capital.py::peg_defense drain scaling (live sync)"),
]}

# renamed levers keep their legacy config names callable (deprecation path)
LEGACY_ALIASES = {
    "firm_capital_haircut": "regulatory_firm_capital_haircut",
    "firm_inventory_haircut": "regulatory_firm_inventory_haircut",
    "land_convexity": "land_fee_stock_elasticity",
    "policy_rate_override": "manual_policy_rate",
}

# STATE_TRANSITION handlers: applied by set_lever AFTER the Policy field mutation
def _handler_soe_transition(econ, old, new):
    if getattr(econ, "e_firms", None):
        econ.e_firms[0].state_owned = bool(new)

def _handler_monetary_regime_switch(econ, old, new):
    # A5 atomicity: manual <=> manual_policy_rate set. Entering manual requires the
    # rate to be STAGED already (stage first, then switch -- one observable step);
    # leaving manual clears it so a stale rate can never silently re-apply later.
    if new == "manual" and econ.policy.manual_policy_rate is None:
        raise ValueError("monetary_regime=manual requires manual_policy_rate staged first")
    if old == "manual" and new != "manual":
        econ.policy.manual_policy_rate = None


def _handler_fx_regime_switch(econ, old, new):
    # staging validation only -- the mechanics run at the next coupling barrier
    if new == "peg":
        a = econ.external_policy.peg_anchor
        me = getattr(econ, "economy_id", None)
        if a is None:
            raise ValueError("fx_regime=peg requires peg_anchor staged first")
        if me is not None and a == me:
            raise ValueError("an economy cannot peg to itself")


def _handler_peg_anchor_change(econ, old, new):
    me = getattr(econ, "economy_id", None)
    if new is not None and me is not None and new == me:
        raise ValueError("an economy cannot anchor to itself")


HANDLERS = {
    "soe_transition": _handler_soe_transition,
    "monetary_regime_switch": _handler_monetary_regime_switch,
    "fx_regime_switch": _handler_fx_regime_switch,
    "peg_anchor_change": _handler_peg_anchor_change,
}


# ---------------------------------------------------------------- mutation API

def set_lever(econ: Any, name: str, value: Any, *, actor: str = "controller",
              target: Any = None) -> None:
    """The sanctioned mutation path: validate -> apply -> log (provisional envelope)."""
    if name in LEGACY_ALIASES:
        import warnings
        warnings.warn(f"policy lever '{name}' was renamed '{LEGACY_ALIASES[name]}'",
                      DeprecationWarning, stacklevel=2)
        name = LEGACY_ALIASES[name]
    lever = REGISTRY.get(name)
    if lever is None:
        raise KeyError(f"unknown policy lever: {name}")
    for cap in lever.requires:
        if not getattr(econ.cfg, cap, False):
            raise ValueError(f"{name}: missing capability {cap}")
    holder = econ.external_policy if lever.scope == "external" else econ.policy
    old = getattr(holder, name, None)
    err = lever.validation.check(old, value)
    if err:
        raise ValueError(f"{name}: {err}")
    if lever.semantics == STATE_TRANSITION:
        # handler may VETO (raise) -- run it before the mutation so a rejected
        # transition leaves the policy untouched; it sees (old, new) and may
        # adjust companion state (SOE flags, staged rates) atomically
        HANDLERS[lever.handler_id](econ, old, value)
    setattr(holder, name, value)
    log = getattr(econ, "_policy_action_log", None)
    if log is None:
        log = econ._policy_action_log = []
    log.append({
        "tick": getattr(econ, "t", -1), "actor_economy": getattr(econ, "world_index", 0),
        "lever": name, "old": old, "new": value, "actor": actor,
        "target": target, "direction": None, "scope": lever.scope,
        "sequence": len(log), "schema_version": 0,   # provisional envelope (A6 pending freeze)
    })
