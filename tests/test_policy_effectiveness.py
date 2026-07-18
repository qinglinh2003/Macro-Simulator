"""v25 P0: per-lever effectiveness tests (B1 coverage matrix).

Pattern: same-seed twin; arm B mutates ONLY econ.policy mid-run; assert the
observable responds (or, for shadowed/dead levers, assert the documented
non-response). A digest gate cannot catch dead fields; this can.

Batch 1 = fiscal domain (this file section 2) + monetary exemplars (section 3).
Baseline arm is computed once per fixture and cached module-wide."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_sim.config import Config
from macro_sim.economy import Economy

TICKS, SPLIT, TAIL = 240, 120, 100

FIXTURES = {
    # one rich fiscal fixture serves most levers; NOTE Config.v13 presets
    # gov_deficit_target=0.03 (the deficit branch is ACTIVE -- shadowing tests rely on it)
    "fiscal": dict(
        seed=17, n_households=40, n_firms_c=25, n_firms_k=12, n_banks=2,
        demographics_population=260, n_ticks=400,
        government=True, tax_income_rate=0.10, tax_consumption_rate=0.10,
        tax_profit_rate=0.15, tax_wealth_rate=0.001,
        benefit_replacement=0.3, pension_replacement=0.3,
        job_guarantee=True, jg_wage_ratio=0.6,
        central_bank=True, inflation_target=5.4e-5,
    ),
    "fiscal_nojg": dict(
        seed=17, n_households=40, n_firms_c=25, n_firms_k=12, n_banks=2,
        demographics_population=260, n_ticks=400,
        government=True, tax_income_rate=0.10, tax_consumption_rate=0.10,
        benefit_replacement=0.3, job_guarantee=False,
    ),
    "strata": dict(
        seed=19, n_households=40, n_firms_c=24, n_firms_k=12, n_banks=2,
        demographics_population=260, n_ticks=400,
        government=True, tax_consumption_rate=0.15, consumption_strata=True,
    ),
}

_BASELINE: dict[str, Economy] = {}


def _econ(fixture):
    return Economy(Config.v13(**FIXTURES[fixture]))


def _baseline(fixture):
    if fixture not in _BASELINE:
        e = _econ(fixture)
        for _ in range(TICKS):
            e.step()
        _BASELINE[fixture] = e
    return _BASELINE[fixture]


def _tail(econ, key):
    return sum(float(r.get(key, 0.0)) for r in econ.records[-TAIL:])


def run_b(mutate, fixture="fiscal"):
    b = _econ(fixture)
    for t in range(TICKS):
        if t == SPLIT:
            mutate(b.policy)
        b.step()
    return b


def assert_moves(key, mutate, direction, fixture="fiscal", min_rel=0.02):
    a = _baseline(fixture)
    b = run_b(mutate, fixture)
    va, vb = _tail(a, key), _tail(b, key)
    if direction == "up":
        assert vb > va * (1 + min_rel), f"{key}: {va:.3f} -> {vb:.3f} (expected up)"
    elif direction == "down":
        assert vb < va * (1 - min_rel), f"{key}: {va:.3f} -> {vb:.3f} (expected down)"
    else:  # "same"
        assert vb == pytest.approx(va), f"{key}: {va:.6f} -> {vb:.6f} (expected inert)"
    return va, vb


# ================= section 2: FISCAL batch =================

def test_tax_income_rate_live():
    assert_moves("tax_income", lambda p: setattr(p, "tax_income_rate", 0.30), "up")

def test_income_allowance_live():
    assert_moves("tax_income", lambda p: setattr(p, "income_allowance", 1.0), "down")

def test_tax_consumption_rate_live():
    assert_moves("tax_consumption", lambda p: setattr(p, "tax_consumption_rate", 0.25), "up")

def test_tax_profit_rate_live():
    assert_moves("tax_profit", lambda p: setattr(p, "tax_profit_rate", 0.40), "up")

def test_tax_wealth_rate_live():
    assert_moves("tax_wealth", lambda p: setattr(p, "tax_wealth_rate", 0.01), "up")

def test_wealth_allowance_live():
    def m(p):
        p.tax_wealth_rate = 0.01          # make the base visible first
        p.wealth_allowance = 0.0
    def m2(p):
        p.tax_wealth_rate = 0.01
        p.wealth_allowance = 3.0
    b_flat = run_b(m); b_allow = run_b(m2)
    assert _tail(b_allow, "tax_wealth") < _tail(b_flat, "tax_wealth") * 0.98

def _slack_pure_benefit(fixture, mutate):
    a = _econ(fixture)
    b = _econ(fixture)
    for t in range(150):
        if t == 30:
            mutate(b.policy)
        a.step()
        b.step()
    win = slice(30, 150)
    pure = lambda e: sum(float(r.get("benefit_paid", 0.0)) - float(r.get("pension_paid", 0.0))
                         for r in e.records[win])
    return pure(a), pure(b)


def test_benefit_replacement_live_without_jg():
    """THREE observable subtleties (all filed):
    1. benefit_paid INCLUDES pensions (settlement.py:265 double-posts) -- observe the
       pure component.
    2. the benefit pays for UNSOLD labour -> only a SLACK window (genesis clearing,
       early u ~40%) can observe the rate.
    3. SHADOWED BY job_guarantee=True: an UNCAPPED JG absorbs all unsold labour, so
       the benefit base is identically zero -- registry `shadowed_by` relationship."""
    pa, pb = _slack_pure_benefit("fiscal_nojg",
                                 lambda p: setattr(p, "benefit_replacement", 0.7))
    assert pa > 0.0, "JG-off fixture must pay real unemployment benefits in the slack window"
    assert pb > pa * 1.10, f"{pa:.2f} -> {pb:.2f}"


def test_benefit_replacement_shadowed_by_job_guarantee():
    """With the uncapped JG on, the unemployment-benefit base is identically zero and
    the rate lever is inert -- the executable form of `shadowed_by: job_guarantee`."""
    pa, pb = _slack_pure_benefit("fiscal",
                                 lambda p: setattr(p, "benefit_replacement", 0.7))
    assert pa == pytest.approx(0.0) and pb == pytest.approx(0.0)

def test_benefit_income_floor_live():
    assert_moves("benefit_paid", lambda p: setattr(p, "benefit_income_floor", 0.8), "up")

def test_pension_replacement_live():
    assert_moves("pension_paid", lambda p: setattr(p, "pension_replacement", 0.7), "up")

def test_gov_deficit_target_live():
    assert_moves("gov_consumption", lambda p: setattr(p, "gov_deficit_target", 0.10), "up")

def test_deficit_u_ref_live():
    # raising u_ref shrinks the state-dependent multiplier min(cap, u/u_ref)
    assert_moves("gov_consumption", lambda p: setattr(p, "deficit_u_ref", 0.60), "down")

def test_min_wage_live():
    a = _baseline("fiscal")
    b = run_b(lambda p: setattr(p, "min_wage", 1.3))
    assert _tail(b, "min_wage_binding_firm_share") > _tail(a, "min_wage_binding_firm_share"), \
        "a binding minimum wage must bind somewhere"

def test_jg_wage_ratio_live():
    assert_moves("job_guarantee_wage", lambda p: setattr(p, "jg_wage_ratio", 0.95), "up",
                 min_rel=0.01)

def test_job_guarantee_toggle_live():
    """OBSERVABLE NOTE: the job_guarantee_wage METRIC is a passive posted-wage gauge
    (jg_wage_ratio x mean wage, metrics.py:948) computed regardless of the flag; the
    activity gauge is jg_employment, and JG is dormant at low u -- so the toggle is
    only observable in a SLACK window. Genesis clearing provides one (early u ~40%):
    toggle OFF at t=30 and compare jg_employment over the genesis-slack window."""
    a = _econ("fiscal")
    b = _econ("fiscal")
    for t in range(150):
        if t == 30:
            b.policy.job_guarantee = False
        a.step()
        b.step()
    win = slice(30, 150)
    jg_a = sum(float(r.get("jg_employment", 0.0)) for r in a.records[win])
    jg_b = sum(float(r.get("jg_employment", 0.0)) for r in b.records[win])
    assert jg_a > 0.0, "fixture must exercise JG in the genesis-slack window"
    assert jg_b < jg_a * 0.5, f"JG off must collapse jg employment: {jg_a:.1f} -> {jg_b:.1f}"

def test_gov_consumption_share_shadowed_by_deficit_target():
    """PRECEDENCE TRAP (registry `shadowed_by`, executable): while gov_deficit_target>0
    the share lever is a documented NO-OP."""
    assert_moves("gov_consumption",
                 lambda p: setattr(p, "gov_consumption_share", 0.25), "same")

def test_gov_consumption_share_live_when_unshadowed():
    def m(p):
        p.gov_deficit_target = 0.0
        p.gov_consumption_share = 0.25
    a = _baseline("fiscal")
    b = run_b(m)
    assert _tail(b, "gov_consumption") != pytest.approx(_tail(a, "gov_consumption"))

# --- differential VAT (strata fixture) ---

def test_tax_necessity_rate_live():
    def m(p):
        p.tax_necessity_rate = 0.0        # zero-rate necessities
        p.tax_luxury_rate = 0.15
    a = _baseline("strata")
    b = run_b(m, "strata")
    assert _tail(b, "tax_consumption") < _tail(a, "tax_consumption") * 0.98

def test_tax_luxury_rate_live():
    def m(p):
        p.tax_necessity_rate = 0.15
        p.tax_luxury_rate = 0.40
    a = _baseline("strata")
    b = run_b(m, "strata")
    assert _tail(b, "tax_consumption") > _tail(a, "tax_consumption") * 1.02


# ================= section 3: MONETARY exemplars =================

def test_policy_rate_override_live():
    b = run_b(lambda p: setattr(p, "policy_rate_override", 0.0005))
    assert b.records[-1].get("policy_rate", 0.0) == pytest.approx(0.0005)

@pytest.mark.xfail(reason="1.7: Policy.central_bank is a DEAD FIELD (rate path reads cfg); "
                          "deleted at migration, replaced by monetary_regime", strict=True)
def test_policy_central_bank_flag_live():
    a = _baseline("fiscal")
    b = run_b(lambda p: setattr(p, "central_bank", False))
    assert b.records[-1].get("policy_rate") != a.records[-1].get("policy_rate")


# ================= section 4: MONETARY batch 2 (Taylor + quantity tools) =================

FIXTURES["monetary"] = dict(
    seed=21, n_households=40, n_firms_c=25, n_firms_k=12, n_banks=3,
    demographics_population=260, n_ticks=400, government=True, central_bank=True,
    bonds=True, bond_finance_frac=0.5, interbank=True, omo=True,
    omo_reserve_target=1.0, omo_drain_frac=0.1,
)


def _rate_tail(e):
    return [float(r.get("policy_rate", 0.0)) for r in e.records[-TAIL:]]


# STATE-DEPENDENT SHADOWING (B1 finding, filed): the v13 world sits at the ZLB (the v19
# deflation engine) -- the policy rate is clipped at the hard-coded 0 floor, so the WHOLE
# Taylor family is inert in ordinary fixtures (both arms read 0.0 identically). Liveness
# is therefore tested via LIFTOFF: cutting pi* BELOW realized inflation turns the gap
# positive and the rate leaves the floor -- the lever itself creates the observable state.
# Registry note: effectiveness can be STATE-dependent; the matrix records the state used.

_LIFT = -2.0e-3   # tuned INTERIOR liftoff: mean rate ~3.7e-4, sd ~1.1e-4, between the
#                   floor 0 and r_max 5e-4 (a stronger lift ceilings BOTH arms at r_max --
#                   the upper-bound twin of the ZLB shadowing)


def _lifted(mutate_extra=None, fixture="fiscal"):
    def m(p):
        p.inflation_target = _LIFT
        if mutate_extra:
            mutate_extra(p)
    return run_b(m, fixture)


def test_inflation_target_live_via_liftoff():
    a = _baseline("fiscal")                      # ZLB-pinned: tail rate == 0
    b = _lifted()
    ra, rb = sum(_rate_tail(a)), sum(_rate_tail(b))
    assert ra == pytest.approx(0.0) and rb > 0.0,         f"cutting pi* below realized inflation must lift the rate: {ra:.4f} -> {rb:.4f}"


def test_taylor_phi_pi_live():
    b1 = _lifted(lambda p: setattr(p, "taylor_phi_pi", 1.5))
    b2 = _lifted(lambda p: setattr(p, "taylor_phi_pi", 4.0))
    r1, r2 = sum(_rate_tail(b1)), sum(_rate_tail(b2))
    assert r2 > r1 * 1.05, f"bigger phi_pi must amplify the positive gap: {r1:.4f} vs {r2:.4f}"


def test_taylor_phi_u_live():
    b1 = _lifted(lambda p: setattr(p, "taylor_phi_u", 0.0))
    b2 = _lifted(lambda p: setattr(p, "taylor_phi_u", 3.0))
    r1, r2 = sum(_rate_tail(b1)), sum(_rate_tail(b2))
    assert r2 < r1, f"bigger phi_u must drag the rate down via the u-gap: {r1:.4f} vs {r2:.4f}"


def test_rate_inertia_live():
    import statistics as st
    def smooth(e):
        r = _rate_tail(e)
        return st.pstdev([r[i+1] - r[i] for i in range(len(r)-1)])
    b1 = _lifted(lambda p: setattr(p, "rate_inertia", 0.5))
    b2 = _lifted(lambda p: setattr(p, "rate_inertia", 0.995))
    assert smooth(b2) < smooth(b1),         f"inertia must smooth the lifted path: {smooth(b1):.3g} -> {smooth(b2):.3g}"


def test_omo_toggle_live():
    a = _baseline("monetary")
    b = run_b(lambda p: setattr(p, "omo", False), fixture="monetary")
    assert _tail(a, "omo_flow") != 0.0, "baseline OMO must be flowing"
    assert abs(_tail(b, "omo_flow")) < abs(_tail(a, "omo_flow")) * 0.1, \
        "OMO off must kill the flow"


def test_omo_reserve_target_live():
    a = _baseline("monetary")
    b = run_b(lambda p: setattr(p, "omo_reserve_target", 0.3), fixture="monetary")
    ra = float(a.records[-1].get("reserve_M", 0.0))
    rb = float(b.records[-1].get("reserve_M", 0.0))
    assert rb < ra * 0.9, f"QT target must drain reserves: {ra:.0f} -> {rb:.0f}"


def test_omo_drain_frac_live():
    # same target, different speeds: the fast drainer is further along shortly after the split
    def arm(frac):
        def m(p):
            p.omo_reserve_target = 0.3
            p.omo_drain_frac = frac
        e = _econ("monetary")
        for t in range(SPLIT + 40):
            if t == SPLIT:
                m(e.policy)
            e.step()
        return float(e.records[-1].get("reserve_M", 0.0))
    slow, fast = arm(0.02), arm(0.5)
    assert fast < slow * 0.95, f"faster drain must be further along: slow={slow:.0f} fast={fast:.0f}"


@pytest.mark.skip(reason="LOLR is only observable in a bank-run crisis; calm fixtures leave "
                         "lolr_advances==0. Covered by the X2 extreme world; a run-crisis "
                         "fixture is a deferred B1 item.")
def test_lolr_toggle_live():
    pass


# ================= section 5: MACROPRUDENTIAL (deferred: credit-dormant fixtures) =========

_CREDIT_DORMANT = ("v13 small stable economies are credit-dormant (firms self-finance; "
                   "total_credit==0 for 150+ ticks even with thin firms + hh_subsistence) -- "
                   "the cap levers multiply a zero base. Needs a stressed/credit-hungry "
                   "fixture (deferred B1 item); the X2 extreme world (leverage 24x, "
                   "hh_credit_limit 4.0) exercises the caps at 14k scale.")

@pytest.mark.skip(reason=_CREDIT_DORMANT)
def test_kappa_live():
    pass

@pytest.mark.skip(reason=_CREDIT_DORMANT)
def test_hh_credit_limit_live():
    pass

@pytest.mark.skip(reason=_CREDIT_DORMANT)
def test_margin_ltv_live():
    pass

@pytest.mark.skip(reason=_CREDIT_DORMANT)
def test_margin_max_live():
    pass


# ================= section 6: ENERGY batch 3 =================

FIXTURES["energy"] = dict(
    seed=31, n_households=40, n_firms_c=25, n_firms_k=12, n_banks=2,
    demographics_population=260, n_ticks=400, government=True,
    energy_enabled=True, energy_household=True, n_firms_e=4, soe_efirm=True,
    tax_energy_rate=0.05, energy_subsidy_rate=0.2,
)


def test_tax_energy_rate_live():
    assert_moves("tax_energy", lambda p: setattr(p, "tax_energy_rate", 0.20), "up",
                 fixture="energy")


def test_energy_subsidy_rate_live():
    assert_moves("energy_subsidy_paid", lambda p: setattr(p, "energy_subsidy_rate", 0.5),
                 "up", fixture="energy")


def test_energy_subsidy_threshold_live():
    # deposits-targeting the subsidy must pay out LESS than the flat version
    assert_moves("energy_subsidy_paid",
                 lambda p: setattr(p, "energy_subsidy_threshold", 0.5), "down",
                 fixture="energy")


def test_energy_price_cap_live():
    a = _baseline("energy")
    b = run_b(lambda p: setattr(p, "energy_price_cap", 0.8), fixture="energy")
    pa = _tail(a, "energy_price") / TAIL
    pb = _tail(b, "energy_price") / TAIL
    assert pa > 0.9 and pb <= 0.8 + 1e-6, f"cap must clamp asks: {pa:.3f} -> {pb:.3f}"


def test_energy_cap_compensation_live():
    # under a binding cap, compensation restores the SOE's revenue vs cap-alone
    def cap_only(p):
        p.energy_price_cap = 0.8
    def cap_comp(p):
        p.energy_price_cap = 0.8
        p.energy_cap_compensation = True
    b1 = run_b(cap_only, fixture="energy")
    b2 = run_b(cap_comp, fixture="energy")
    # same-seed twins => noise is correlated; a small strict margin is reliable
    assert _tail(b2, "soe_dividends") > _tail(b1, "soe_dividends") * 1.002


def test_spr_target_units_live():
    a = _baseline("energy")
    b = run_b(lambda p: (setattr(p, "spr_target_units", 50.0),
                         setattr(p, "spr_flow_cap", 2.0)), fixture="energy")
    assert float(a.records[-1].get("spr_stock", 0.0)) == 0.0
    assert float(b.records[-1].get("spr_stock", 0.0)) > 0.0, "SPR must start stockpiling"


def test_spr_flow_cap_live():
    def arm(cap):
        def m(p):
            p.spr_target_units = 50.0
            p.spr_flow_cap = cap
        e = _econ("energy")
        for t in range(SPLIT + 60):
            if t == SPLIT:
                m(e.policy)
            e.step()
        return float(e.records[-1].get("spr_stock", 0.0))
    slow, fast = arm(0.1), arm(2.0)
    assert fast > slow * 1.5, f"a larger flow cap must stockpile faster: {slow:.2f} vs {fast:.2f}"


def test_tax_energy_windfall_live():
    a = _baseline("energy")
    b = run_b(lambda p: setattr(p, "tax_energy_windfall", 0.5), fixture="energy")
    assert _tail(a, "tax_energy_windfall") == pytest.approx(0.0)
    assert _tail(b, "tax_energy_windfall") > 0.0, "windfall surtax must collect from profitable E-firms"


def test_soe_price_at_cost_live():
    """LIVE, but with a FILED DIRECTION ANOMALY: pricing the SOE at unit cost RAISED the
    market average energy price ~3% in this fixture (cost <= markup price should pull the
    ask average DOWN). Either the price metric is transaction/composition-weighted in a
    way that inverts, or SOE unit cost exceeds its markup-discounted ask -- to
    investigate. The lever is proven effective (path departs); direction unasserted."""
    a = _baseline("energy")
    b = run_b(lambda p: setattr(p, "soe_price_at_cost", True), fixture="energy")
    va, vb = _tail(a, "energy_price"), _tail(b, "energy_price")
    assert vb != pytest.approx(va, rel=1e-6), f"lever must move the price path: {va:.2f} vs {vb:.2f}"


@pytest.mark.skip(reason="energy_rationing order is only observable under SHORTAGE with "
                         "per-sector allocation gauges; needs a shock/shortage fixture "
                         "(deferred; the energy_shock_* levers belong to the shock module).")
def test_energy_rationing_live():
    pass


# ================= section 7: HOUSING batch 3 =================

FIXTURES["housing"] = dict(
    seed=33, n_households=40, n_firms_c=25, n_firms_k=12, n_banks=2,
    demographics_population=260, n_ticks=400, government=True, tax_wealth_rate=0.001,
    housing_enabled=True, housing_market_enabled=True, housing_construction_enabled=True,
    n_builders=3, housing_property_tax=0.01, housing_transfer_tax=0.05,
)


def test_housing_property_tax_live():
    assert_moves("property_tax_paid", lambda p: setattr(p, "housing_property_tax", 0.03),
                 "up", fixture="housing")


def test_housing_permits_live():
    a = _baseline("housing")
    b = run_b(lambda p: setattr(p, "housing_permits", 0), fixture="housing")
    built_after = lambda e: (float(e.records[-1].get("dwellings_built_total", 0.0))
                             - float(e.records[SPLIT].get("dwellings_built_total", 0.0)))
    assert built_after(a) > 0.0, "baseline must keep building"
    assert built_after(b) == pytest.approx(0.0), "permits=0 must stall construction"


def test_housing_in_wealth_tax_live():
    assert_moves("tax_wealth", lambda p: setattr(p, "housing_in_wealth_tax", True), "up",
                 fixture="housing")


@pytest.mark.skip(reason="housing_transfer_tax needs SALES; the small fixture produces "
                         "zero resale transactions in 400t (probate listings require "
                         "deaths + unhoused buyers). Long-horizon housing fixture "
                         "deferred with the mortgage-lever batch.")
def test_housing_transfer_tax_live():
    pass


# ================= section 8: B2 defect-fix verifications =================

def test_omo_metrics_follow_policy_not_config():
    """B2(b): the metrics' OMO gate reads POLICY (split-brain fixed): toggling
    policy.omo off must zero the REPORTED target, not just the behaviour."""
    b = run_b(lambda p: setattr(p, "omo", False), fixture="monetary")
    tail_target = [float(r.get("omo_reserve_target_value", 0.0)) for r in b.records[-TAIL:]]
    assert max(tail_target) == pytest.approx(0.0), \
        "metrics must report a zero OMO target once policy turns OMO off"
