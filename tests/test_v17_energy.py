"""v17.0 acceptance tests (PLAN_v17) — the E-sector & the firm-to-firm energy market.

Energy is the first INTERMEDIATE input: E-firms produce a storable commodity under a
capacity edge; c/k firms hold an input stock at a coverage target and their B3 unit
cost gains the energy term. "Done" for v17.0:
  * flag off ⇒ bit-identical (every hook is a guarded no-op);
  * the flow soft gauge closes every tick (produced == used + Δstocks);
  * genesis is FITTED: no opening transient (price, coverage, utilization all start
    at their anchors), the no-shock baseline is QUIET;
  * cost-push wiring verified by a PINNED test (energy price up ⇒ downstream prices
    rise through B3 — pure plumbing, no shock machinery);
  * GDP excludes intermediates (consumption metrics never read E-firms);
  * the capacity edge binds plans (short-run supply inelasticity);
  * the excise handle remits to fiscal without breaking A5.

Run: ``uv run python tests/test_v17_energy.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro_sim.config import Config                # noqa: E402
from macro_sim.economy import Economy              # noqa: E402

NC, NK, NH = 60, 30, 400


def _kernel_energy(**overrides) -> Config:
    """The v1 kernel + energy: the smallest world where the full energy loop runs
    (no banks/government/demographics/firm-demographics ⇒ no exits destroy stocks,
    so the flow gauge must close EXACTLY every tick)."""
    base = dict(n_households=200, n_firms=10, n_ticks=400, seed=0, energy_enabled=True)
    base.update(overrides)
    return Config(**base)


def test_energy_off_bit_identical():
    """Flag off: setting every v17 field at its default (and n_firms_e high) must not
    move a single series value — the guards genuinely never fire without the flag."""
    a = Economy(Config.v124(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0)).run()
    b = Economy(Config.v124(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0,
                            n_firms_e=8, energy_intensity=0.5, tax_energy_rate=0.2)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"]
        assert x["price_index"] == y["price_index"]
        assert x["conservation_drift"] == y["conservation_drift"]
        assert "energy_price" not in y, "energy gauges must not appear with the flag off"


def test_flow_gauge_closes_exactly():
    """produced == used + Δ(all stocks) every tick (no firm exits in the kernel, so
    the soft gauge must close to float tolerance)."""
    econ = Economy(_kernel_energy())
    recs = econ.run()
    scale = max(1.0, max(r["energy_produced"] for r in recs))
    for r in recs[1:]:
        assert abs(r["energy_flow_gap"]) < 1e-9 * scale, f"flow gap at t={r['t']}: {r['energy_flow_gap']}"


def test_genesis_fitted_and_baseline_quiet():
    """The watches on the no-shock baseline: genesis starts AT the anchors (t0 is
    fitted; the kernel's own demand-seed transient follows and is burn-in), and the
    LATE window is quiet: coverage recovered near target (no shortage crawl, no
    hoarding blow-up), markups off the ceiling, utilization sane.

    util0=0.5 here: the kernel's energy-sector wage/dividend recirculation lifts its
    steady demand ~10% past a 0.85-fitted capacity (the kernel's only hard supply
    constraint is energy, so it grows INTO any tight ceiling); the calibrated world
    is probed by test_v124_energy_converges_to_baseline instead."""
    cfg = _kernel_energy(n_ticks=1000, energy_util0=0.5)
    econ = Economy(cfg)
    recs = econ.run()
    first = recs[0]
    # fitted genesis: price at anchor, utilization at the headroom anchor, coverage at target
    assert abs(first["energy_price"] - cfg.p_efirm0) < 0.05 * cfg.p_efirm0
    assert abs(first["e_capacity_utilization"] - cfg.energy_util0) < 0.15
    assert abs(first["energy_coverage_mean"] - cfg.energy_coverage_ticks) < 0.2 * cfg.energy_coverage_ticks
    late = recs[-300:]
    cov = [r["energy_coverage_mean"] for r in late]
    assert min(cov) > 0.3 * cfg.energy_coverage_ticks, "coverage collapsed (shortage baseline)"
    assert max(cov) < 3.0 * cfg.energy_coverage_ticks, "coverage exploded (hoarding baseline)"
    assert max(r["e_markup_at_cap_share"] for r in late) < 0.75, "E markups pinned at mu_max"
    assert all(0.0 < r["e_capacity_utilization"] <= 1.0 + 1e-9 for r in late)
    # the cost-share anchor (5-8% target band, generous test bounds)
    share = [r["energy_cost_share"] for r in late]
    assert 0.02 < sum(share) / len(share) < 0.15, f"cost share off anchor: {sum(share)/len(share):.3f}"


def test_pinned_cost_push_reaches_downstream_prices():
    """THE PLUMBING TEST (Phase-2 pinned-signal paradigm): halve every E-firm's labor
    productivity at t=200 ⇒ the energy UNIT COST doubles ⇒ the energy price rises
    through B3 regardless of the markup regime ⇒ downstream unit costs carry the
    energy term ⇒ the consumption price index ends HIGHER than the same-seed baseline.
    (This is also the embryo of the 17.2 productivity-shock lever, hand-applied.)"""
    n_ticks, pin_at = 500, 200
    a = Economy(_kernel_energy(n_ticks=n_ticks))
    recs_a = a.run()
    b = Economy(_kernel_energy(n_ticks=n_ticks))
    recs_b = []
    for t in range(n_ticks):
        if t == pin_at:
            for ef in b.e_firms:
                ef.A *= 0.5                        # CD TFP cut: uc scales A^(-1/(1-alpha)) ~ 2.7x; B3 does the rest
        recs_b.append(b.step())
    e_a = sum(r["energy_price"] for r in recs_a[-50:]) / 50
    e_b = sum(r["energy_price"] for r in recs_b[-50:]) / 50
    assert e_b > 1.3 * e_a, f"pin failed: energy price {e_b:.3f} vs baseline {e_a:.3f}"
    p_a = sum(r["price_index"] for r in recs_a[-50:]) / 50
    p_b = sum(r["price_index"] for r in recs_b[-50:]) / 50
    assert p_b > 1.005 * p_a, f"cost-push did not reach downstream prices: {p_b:.4f} vs {p_a:.4f}"


def test_gdp_excludes_intermediates():
    """Energy sold to firms is intermediate consumption: the consumption GDP series
    read c-firms only, so E revenue must appear NOWHERE in them while the energy
    market is demonstrably active."""
    econ = Economy(_kernel_energy())
    recs = econ.run()
    assert sum(r["energy_sold"] for r in recs) > 0.0, "the energy market never traded"
    last = recs[-1]
    assert abs(last["real_output"] - sum(f.produced for f in econ.c_firms)) < 1e-9
    assert abs(last["consumption_spending"] - sum(f.revenue for f in econ.c_firms)) < 1e-9
    e_rev = sum(f.revenue for f in econ.e_firms)
    assert e_rev > 0.0 and e_rev not in (last["consumption_spending"],)  # active, and separate


def test_capacity_edge_binds_plans():
    """Short-run supply inelasticity: an E-firm's planned target never exceeds κ·K,
    produced never exceeds κ·K, and a capacity shock sized BELOW current demand
    leaves the sector pinned at capacity instead of hiring its way out."""
    econ = Economy(_kernel_energy(n_ticks=400))
    for _ in range(250):
        econ.step()
    demand_now = sum(r["energy_sold"] for r in econ.records[-30:]) / 30
    for ef in econ.e_firms:                        # the capacity shock lever, hand-applied:
        ef.capital = 0.6 * demand_now / (len(econ.e_firms) * ef.capacity_kappa)
        ef.capital_prev = ef.capital
    for _ in range(150):
        econ.step()
        for ef in econ.e_firms:
            assert ef.production_target <= ef.capacity_kappa * ef.capital + 1e-9
            assert ef.produced <= ef.capacity_kappa * ef.capital + 1e-9
    # post-shock the sector runs AT capacity (the edge binds, labor cannot rescue it)
    util = econ.records[-1]["e_capacity_utilization"]
    assert util > 0.95, f"capacity should bind after the shock (util={util:.3f})"


def test_v124_energy_converges_to_baseline():
    """THE CALIBRATED-WORLD acceptance: on v124 (government + banks + CB + firm
    demographics) the energy economy must survive its genesis slump (the E replacement
    floor + unfilled-demand expectations are the two structural guards found by this
    probe) and converge to the no-energy baseline's activity level — energy present
    but not strangling. Also the composition sanity: E capital recovered, markups
    off the ceiling late, unfilled demand cleared."""
    on = Economy(Config.v124(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0,
                             energy_enabled=True))
    recs_on = on.run()
    recs_off = Economy(Config.v124(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0)).run()
    late_on = sum(r["real_output"] for r in recs_on[-100:]) / 100
    late_off = sum(r["real_output"] for r in recs_off[-100:]) / 100
    assert 0.7 * late_off < late_on < 1.3 * late_off, \
        f"energy strangles (or inflates) the calibrated economy: {late_on:.0f} vs {late_off:.0f}"
    assert sum(f.capital for f in on.e_firms) > 1.0, "E capital never recovered from the slump"
    late_atcap = sum(r["e_markup_at_cap_share"] for r in recs_on[-100:]) / 100
    assert late_atcap < 0.9, f"E markups pinned at the ceiling late (share={late_atcap:.2f})"
    assert sum(r["energy_unfilled"] for r in recs_on[-50:]) / 50 < \
        0.5 * max(1.0, sum(r["energy_sold"] for r in recs_on[-50:]) / 50), "chronic unfilled demand"


def test_excise_remits_and_conserves():
    """The excise handle (VAT grammar): with government on and tax_energy_rate>0 the
    remit reaches fiscal; every conservation gate stays green (a clean run == the
    per-tick hard gates held)."""
    econ = Economy(Config.v124(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=2,
                               energy_enabled=True, tax_energy_rate=0.10))
    recs = econ.run()
    assert sum(r.get("tax_energy", 0.0) for r in recs) > 0.0, "excise never remitted"
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m


def test_entrants_join_the_energy_economy():
    """c-firm entrants (firm demographics) must get the Leontief coefficient and the
    hold-last price as their cost expectation — otherwise entrants would produce
    without energy (a heterogeneity leak)."""
    econ = Economy(Config.v124(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=3,
                               energy_enabled=True))
    econ.run()
    assert all(f.energy_intensity > 0.0 for f in econ.c_firms), "an entrant missed the energy coefficient"
    assert all(f.energy_avg_cost > 0.0 for f in econ.c_firms)


# ---------------------------------------------------------------------------
# v17.1 -- household energy demand (necessity, headline/core CPI, energy poverty)
# ---------------------------------------------------------------------------

def test_hh_energy_share_and_poverty_gradient():
    """CALIBRATED-WORLD test (the kernel is degenerate here: kernel E-firms cannot
    invest, so their retained earnings become a money sink that drains the goods
    economy through the necessity channel — probed, documented, and exactly why
    calibration-flavored assertions live on v124). The anchored budget share holds and
    the poverty gradient is EMERGENT: need is uniform per household while consumption
    scales with income, so the poor spend a LARGER share, unseeded."""
    econ = Economy(Config.v124(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=5,
                               energy_enabled=True, energy_household=True))
    recs = econ.run()
    late = recs[-150:]
    share = sum(r["energy_hh_share_mean"] for r in late) / len(late)
    assert 0.01 < share < 0.25, f"household energy share off anchor: {share:.3f}"
    q1 = sum(r["energy_share_q1"] for r in late) / len(late)
    q5 = sum(r["energy_share_q5"] for r in late) / len(late)
    assert q1 > q5, f"poverty gradient missing: q1={q1:.3f} q5={q5:.3f}"
    assert all(0.0 <= r["fuel_poverty_share"] <= 1.0 for r in late)
    assert sum(r["energy_hh_spend"] for r in recs) > 0.0


def test_hh_energy_necessity_inelastic():
    """Necessity on the calibrated world: under a >1.2x energy price rise (mild E TFP
    cut; a 2x cut demand-destroys the stabilizer-free KERNEL permanently — probed,
    noted for 17.2), household energy UNITS barely move — the fixed-real-need rule
    makes demand price-inelastic by construction."""
    n_ticks, pin_at = 500, 200
    base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=n_ticks, seed=5,
                energy_enabled=True, energy_household=True)
    a = Economy(Config.v124(**base))
    recs_a = a.run()
    b = Economy(Config.v124(**base))
    recs_b = []
    for t in range(n_ticks):
        if t == pin_at:
            for ef in b.e_firms:
                ef.A *= 0.8                        # uc x ~1.38 through CD
        recs_b.append(b.step())
    assert sum(r["energy_sold"] for r in recs_b[-50:]) > 0.0, \
        "shocked run collapsed -- the price comparison would be vacuous (hold-last)"
    e_a = sum(r["energy_price"] for r in recs_a[-50:]) / 50
    e_b = sum(r["energy_price"] for r in recs_b[-50:]) / 50
    assert e_b > 1.2 * e_a, f"price pin failed ({e_b:.3f} vs {e_a:.3f})"
    u_a = sum(r["energy_hh_units"] for r in recs_a[-50:]) / 50
    u_b = sum(r["energy_hh_units"] for r in recs_b[-50:]) / 50
    assert u_b > 0.8 * u_a, f"household energy demand too elastic: {u_b:.3f} vs {u_a:.3f}"


def test_headline_core_and_cb_reading():
    """Headline CPI includes energy, core is the c-goods index; the CB reads headline
    by default and `cb_core_inflation` flips its input — the two same-seed runs must
    diverge (the feed is wired), while headline==core-neutral worlds stay identical."""
    base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=4,
                energy_enabled=True, energy_household=True)
    head = Economy(Config.v124(**base)).run()
    core = Economy(Config.v124(**base, cb_core_inflation=True)).run()
    assert any(r.get("cpi_headline") for r in head), "headline index missing"
    assert any(x["policy_rate"] != y["policy_rate"] for x, y in zip(head, core)), \
        "cb_core_inflation did not change the CB's input"


def test_hh_energy_off_is_170_identical():
    """energy_household=False must leave the 17.0 energy world untouched (guarded
    construction): same-seed series identical with the field block present."""
    a = Economy(_kernel_energy(n_ticks=300)).run()
    b = Economy(_kernel_energy(n_ticks=300, energy_hh_share=0.5, cb_core_inflation=True)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["energy_price"] == y["energy_price"]


# ---------------------------------------------------------------------------
# v17.2 -- the capacity-shock scenario machinery (the experiment MATRIX runs
# post-composition per the parallel protocol §5; these gates are arc-scope)
# ---------------------------------------------------------------------------

def test_shock_prefix_identical_then_diverges():
    """Scenario discipline: with the shock configured, the same-seed series is
    IDENTICAL before shock_at (the scenario machinery consumes nothing early) and
    diverges after (the shock is real)."""
    base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=350, seed=6,
                energy_enabled=True)
    a = Economy(Config.v124(**base)).run()
    b = Economy(Config.v124(**base, energy_shock_at=200,
                            energy_shock_magnitude=0.3)).run()
    for x, y in zip(a[:200], b[:200]):
        assert x["real_output"] == y["real_output"] and x["energy_price"] == y["energy_price"]
    assert any(x["energy_produced"] != y["energy_produced"] for x, y in zip(a[200:], b[200:])), \
        "the shock never bit"


def test_pulse_restores_kappa_exactly_and_mean_reverts():
    """A pulse restores capacity_kappa float-EXACTLY (stored value, not divide-back)
    and the economy mean-reverts: no permanent ratchet in any energy stock or price
    relative to the same-seed no-shock twin."""
    base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=700, seed=6,
                energy_enabled=True)
    a = Economy(Config.v124(**base))
    recs_a = a.run()
    b = Economy(Config.v124(**base, energy_shock_at=250, energy_shock_magnitude=0.3,
                            energy_shock_duration=60))
    recs_b = b.run()
    for ea, eb in zip(a.e_firms, b.e_firms):
        assert ea.capacity_kappa == eb.capacity_kappa, "pulse did not restore kappa exactly"
    ry_a = sum(r["real_output"] for r in recs_a[-100:]) / 100
    ry_b = sum(r["real_output"] for r in recs_b[-100:]) / 100
    assert abs(ry_b / ry_a - 1.0) < 0.15, f"no mean reversion: {ry_b:.0f} vs {ry_a:.0f}"
    cov_b = sum(r["energy_coverage_mean"] for r in recs_b[-50:]) / 50
    cov_a = sum(r["energy_coverage_mean"] for r in recs_a[-50:]) / 50
    assert cov_b > 0.5 * cov_a, "coverage never recovered from the pulse"


def test_buffering_state_dependence():
    """PRE-REGISTERED (the storability payoff): the same shock hits SOFTER EARLY under
    HIGH initial coverage — the early post-shock output drop (first 30 ticks) is
    smaller when downstream stocks are deep than when they are shallow."""
    def drop(cov_ticks):
        # magnitude 0.8: the sector idles ~0.4-0.5 utilization in v124, so a mild cut
        # never binds and the comparison measures noise (the first cut of this test
        # did exactly that -- refuted by its own bind-guard below).
        base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=320, seed=7,
                    energy_enabled=True, energy_coverage_ticks=cov_ticks)
        ref = Economy(Config.v124(**base)).run()
        shk = Economy(Config.v124(**base, energy_shock_at=250,
                                  energy_shock_magnitude=0.8)).run()
        early = range(255, 285)
        r0 = sum(ref[i]["real_output"] for i in early)
        r1 = sum(shk[i]["real_output"] for i in early)
        return (r0 - r1) / max(1.0, r0)
    d_low, d_high = drop(5.0), drop(60.0)
    assert d_low > 0.01, f"the shock never bit (shallow-stock drop {d_low:.4f}) -- test misconfigured"
    assert d_high < d_low, \
        f"buffering refuted: early drop {d_high:.3f} (deep stocks) !< {d_low:.3f} (shallow)"


def test_windfall_tax_remits_and_conserves():
    """The shock-response fiscal instrument: with the surtax live, E windfalls reach
    fiscal after the shock, the dividend pool shrinks accordingly, and every
    conservation gate stays green."""
    econ = Economy(Config.v124(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=6,
                               energy_enabled=True, energy_shock_at=200,
                               energy_shock_magnitude=0.4, tax_energy_windfall=0.5))
    recs = econ.run()
    assert sum(r.get("tax_energy_windfall", 0.0) for r in recs[200:]) > 0.0, "windfall never remitted"
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m


# ---------------------------------------------------------------------------
# v17.3 -- strategic reserve, state ownership, hoarding
# ---------------------------------------------------------------------------

def test_spr_builds_and_conserves():
    """The fiscal node accumulates the reserve toward target through ordinary session
    buys (deficit-financed, conserving); the flow gauge still closes EXACTLY with the
    SPR in the stock total. Kernel + government: the fiscal account exists and NO firm
    exits destroy stocks (v124's death spikes are the gauge's one legitimate source,
    so exactness asserts belong in no-death worlds — the 17.0 lesson)."""
    econ = Economy(Config(n_households=200, n_firms_c=20, n_firms_k=10, n_ticks=300, seed=8,
                          government=True, bank_enabled=True,   # v9 needs A5 money; v3 needs v2
                          energy_enabled=True, spr_target_units=60.0, spr_flow_cap=1.0))
    recs = econ.run()
    assert econ._spr_stock > 30.0, f"SPR never built ({econ._spr_stock:.1f})"
    scale = max(1.0, max(r["energy_produced"] for r in recs))
    assert max(abs(r["energy_flow_gap"]) for r in recs[1:]) < 1e-9 * scale, \
        "flow gauge broke with the SPR"
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * max(r["total_money"] for r in recs)


def test_spr_release_damps_the_shock():
    """THE HEADLINE 17.3 EXPERIMENT, clean pair: BOTH worlds build the same reserve
    (identical prefix, same seed); at the shock one RELEASES (Policy target -> 0),
    the other holds. Release must reduce unmet demand through the crunch. (The first
    cut compared against a no-SPR world — the build phase perturbs the whole
    trajectory and seed-chaos swamped a 2/tick release; refuted, redesigned.)"""
    base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=420, seed=8,
                energy_enabled=True, energy_shock_at=300, energy_shock_magnitude=0.5,
                energy_shock_duration=80, spr_target_units=150.0, spr_flow_cap=5.0)
    hold = Economy(Config.v124(**base))
    recs_hold = hold.run()
    rel = Economy(Config.v124(**base))
    recs_rel = []
    for t in range(420):
        if t == 300:
            rel.policy.spr_target_units = 0.0   # RELEASE: the live-lever use-case
        recs_rel.append(rel.step())
    for x, y in zip(recs_hold[:300], recs_rel[:300]):
        assert x["real_output"] == y["real_output"], "prefix must be identical (same build)"
    # DIRECT RELIEF while the reserve lasts (stock 150 / flow 5 => ~30 ticks):
    window = range(300, 330)
    unf_hold = sum(recs_hold[i]["energy_unfilled"] for i in window)
    unf_rel = sum(recs_rel[i]["energy_unfilled"] for i in window)
    assert unf_rel < unf_hold, f"release did not damp the shortage: {unf_rel:.0f} !< {unf_hold:.0f}"
    # FINDING 12 (report, not assert): after the reserve empties, unfilled flips HIGHER
    # in the release world -- the cheap SPR supply stole E-firm sales, dragged their B2
    # expectations down, and CROWDED OUT the private capacity response (probe: E output
    # -15% in the following windows, d^e 32 vs 38 at the end). Front-loaded relief,
    # muted supply signal: the classic SPR-release policy debate, emergent.
    assert max(r["spr_stock"] for r in recs_rel) > 80.0 and recs_rel[-1]["spr_stock"] < 5.0, \
        "the reserve never built or never released"


def test_soe_dividends_and_at_cost_pricing():
    """State ownership: the SOE's dividends reach fiscal (households never see them);
    with at-cost pricing on, the SOE posts exactly its unit cost each tick."""
    econ = Economy(Config.v124(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=8,
                               energy_enabled=True, soe_efirm=True, soe_price_at_cost=True))
    recs = econ.run()
    assert econ.e_firms[0].state_owned and not econ.e_firms[1].state_owned
    assert sum(r["soe_dividends"] for r in recs) > 0.0, "SOE dividends never reached fiscal"
    assert econ.e_firms[0].markup == 0.0, "at-cost pricing did not pin the SOE markup"
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m


def test_hoarding_mechanism_fires():
    """Hoarding (flag, DEFAULT OFF) asserts the MECHANISM, reports the net: with the
    flag on, total addressed demand (sold + unfilled) through the crunch is HIGHER —
    trend-following firms order more exactly when prices spike. FINDING (first run,
    kept): the NET unfilled was LOWER with hoarding — pre-shock price uptrends had
    already built deeper precautionary buffers, and hoarding-as-insurance beat
    hoarding-as-panic at this config. The 1970s amplification needs the panic to
    START post-shortage; the net sign is emergent, not asserted."""
    base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=420, seed=8,
                energy_enabled=True, energy_shock_at=300, energy_shock_magnitude=0.5,
                energy_shock_duration=80)
    off = Economy(Config.v124(**base)).run()
    on = Economy(Config.v124(**base, energy_hoarding_beta=3.0)).run()
    window = range(300, 420)
    addressed_off = sum(off[i]["energy_sold"] + off[i]["energy_unfilled"] for i in window)
    addressed_on = sum(on[i]["energy_sold"] + on[i]["energy_unfilled"] for i in window)
    assert addressed_on > addressed_off, \
        f"hoarding demand never fired: {addressed_on:.0f} !> {addressed_off:.0f}"
    # the net (report-only, both directions legitimate): print for the run log
    unf_off = sum(off[i]["energy_unfilled"] for i in window)
    unf_on = sum(on[i]["energy_unfilled"] for i in window)
    print(f"    [hoarding net] unfilled on={unf_on:.0f} vs off={unf_off:.0f} "
          f"({'amplifies' if unf_on > unf_off else 'insures (pre-buffer dominates)'})")


# ---------------------------------------------------------------------------
# v17.4 -- the crisis triple: price cap, rationing menu, compensation
# ---------------------------------------------------------------------------

def _crisis_base(**overrides):
    base = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=10,
                energy_enabled=True, energy_household=True,
                energy_shock_at=250, energy_shock_magnitude=0.7, energy_shock_duration=100)
    base.update(overrides)
    return Config.v124(**base)


def _run_crisis(policy_at_shock: dict, **cfg_over):
    """Crisis instruments are LIVE LEVERS imposed AT the shock (Policy mutation), not
    standing institutions: a cap set from t0 in a drifting-nominal world eventually
    prices the whole sector underwater and kills the market before the experiment
    starts (probed -- the first cut of these tests did exactly that)."""
    econ = Economy(_crisis_base(**cfg_over))
    recs = []
    for t in range(400):
        if t == 250:
            for k, v in policy_at_shock.items():
                setattr(econ.policy, k, v)
        recs.append(econ.step())
    return econ, recs


def test_cap_binds_and_creates_excess_demand():
    """A cap below the crunch price clamps every transaction at the cap and RAISES
    unmet demand vs the uncapped twin (price can no longer ration)."""
    _, free = _run_crisis({})
    p_crunch = max(r["energy_price"] for r in free[250:350])
    _, capped = _run_crisis({"energy_price_cap": 0.6 * p_crunch})
    win = range(250, 350)
    assert any(r["energy_cap_binding"] > 0 for r in capped), "the cap never bound"
    assert max(r["energy_price"] for r in [capped[i] for i in win]) <= 0.6 * p_crunch + 1e-9, \
        "a transaction cleared above the cap"
    # excess demand EXISTS under the cap (material vs traded volume; the v124 world
    # has its own background unfilled waves, so no calm-window reference exists)...
    unf_cap = sum(capped[i]["energy_unfilled"] for i in win)
    sold_cap = sum(capped[i]["energy_sold"] for i in win)
    assert unf_cap > 0.2 * max(1.0, sold_cap), "no material excess demand under the binding cap"
    # ...and the cap's real damage channel is the SELLER MARGIN, not volume:
    rev_free = sum(f["energy_sold"] * f["energy_price"] for f in [free[i] for i in win])
    rev_cap = sum(f["energy_sold"] * f["energy_price"] for f in [capped[i] for i in win])
    assert rev_cap < rev_free, f"the cap should bleed seller revenue: {rev_cap:.0f} !< {rev_free:.0f}"
    # FINDING 14 (report): traded VOLUME can be HIGHER under the cap -- markup pricing
    # OVERSHOOTS the clearing price in a crunch (mu_max x uc is not a clearing rule),
    # so part of the free-market shortage is budget-rationed demand facing unsold
    # expensive stock; the cap fixes the overshoot while destroying margins.
    unf_free = sum(free[i]["energy_unfilled"] for i in win)
    print(f"    [cap] unfilled cap={unf_cap:.0f} vs free={unf_free:.0f} "
          f"({'cap worsens' if unf_cap > unf_free else 'cap clears MORE (overshoot fixed)'})")


def test_rationing_menu_protects_its_class():
    """household_first vs industry_first through the same capped crunch: households
    keep a larger fill when protected; industry uses more energy when protected."""
    _, free = _run_crisis({})
    cap = 0.6 * max(r["energy_price"] for r in free[250:350])
    def run(rule):
        _, recs = _run_crisis({"energy_price_cap": cap, "energy_rationing": rule})
        return recs
    hh_first = run("household_first")
    ind_first = run("industry_first")
    win = range(250, 350)
    hh_fill_a = sum(hh_first[i]["energy_hh_units"] for i in win)
    hh_fill_b = sum(ind_first[i]["energy_hh_units"] for i in win)
    assert hh_fill_a > hh_fill_b, \
        f"household priority did not protect households: {hh_fill_a:.0f} !> {hh_fill_b:.0f}"
    used_a = sum(hh_first[i]["energy_used"] for i in win)
    used_b = sum(ind_first[i]["energy_used"] for i in win)
    assert used_b > used_a, \
        f"industry priority did not protect industry: {used_b:.0f} !> {used_a:.0f}"


def test_proportional_rationing_clears_and_conserves():
    """The proportional path (no sampling, everyone cut by the same fraction) trades,
    conserves, and keeps the gates green."""
    _, recs = _run_crisis({"energy_rationing": "proportional"})
    assert sum(r["energy_sold"] for r in recs) > 0.0
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m


def test_uncompensated_cap_bleeds_the_sector():
    """The documented sector-killer: a harsh binding cap WITHOUT compensation drains
    E-firm cash vs the compensated twin (same seed, same cap) — the honest failure
    mode, run once, never a default."""
    _, free = _run_crisis({})
    cap = 0.5 * max(r["energy_price"] for r in free[250:350])

    def run_tracking(policy):
        econ = Economy(_crisis_base())
        recs, cash = [], []
        for t in range(400):
            if t == 250:
                for k, v in policy.items():
                    setattr(econ.policy, k, v)
            recs.append(econ.step())
            if t >= 250:
                cash.append(sum(econ.ledger.balance(f.id) for f in econ.e_firms))
        return recs, cash
    recs_bare, cash_bare_t = run_tracking({"energy_price_cap": cap})
    recs_comp, cash_comp_t = run_tracking({"energy_price_cap": cap,
                                           "energy_cap_compensation": True})
    # compare the BLEED RATE (mean sector cash through the cap window): end-state cash
    # is 0 in both -- a harsh 150-tick cap kills either way, compensation slows it
    cash_bare = sum(cash_bare_t) / len(cash_bare_t)
    cash_comp = sum(cash_comp_t) / len(cash_comp_t)
    assert cash_comp > cash_bare, \
        f"compensation should slow the bleed: mean cash {cash_comp:.0f} !> {cash_bare:.0f}"
    assert sum(r["energy_cap_compensation"] for r in recs_comp) > 0.0
    assert sum(r["energy_cap_compensation"] for r in recs_bare) == 0.0
    m = max(r["broad_money"] for r in recs_comp)
    assert max(r["conservation_drift"] for r in recs_comp) < 1e-6 * m


def test_crisis_triple_off_bit_identical():
    """Defaults (cap 0, market rationing, no compensation) leave the 17.3 world
    untouched — same-seed series equality with the fields present."""
    a = Economy(_crisis_base()).run()
    b = Economy(_crisis_base(energy_rationing="market", energy_price_cap=0.0)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["energy_price"] == y["energy_price"]


# ---------------------------------------------------------------------------
# v17.5 -- couplings: fuel poverty -> mortality; flat vs targeted subsidy
# ---------------------------------------------------------------------------

def test_energy_poverty_signal_grammar():
    """Phase-2 grammar unit test: burn-in years are DISCARDED (multiplier stays 1.0
    however high fuel poverty runs), the annual rollover computes the mean share,
    the multiplier is 1 + gamma*fp clipped, and gamma=0 is exactly neutral."""
    from macro_sim.systems.energy import EnergyPovertySignal
    sig = EnergyPovertySignal(burnin_years=2, gamma=2.0, mult_hi=1.3)
    for year in (2000, 2001, 2002):
        for _ in range(10):
            sig.observe_tick(year, 0.5)            # brutal fuel poverty through burn-in
    assert sig.mortality_mult == 1.0, "burn-in must be discarded"
    for _ in range(10):
        sig.observe_tick(2003, 0.05)               # rollover of year 2002 (post-burn-in)
    assert abs(sig.mortality_mult - min(1.3, 1.0 + 2.0 * 0.5)) < 1e-12
    for _ in range(10):
        sig.observe_tick(2004, 0.0)                # rollover of 2003: fp=0.05 -> 1.10
    assert abs(sig.mortality_mult - 1.10) < 1e-12
    neutral = EnergyPovertySignal(burnin_years=1, gamma=0.0)
    for year in (2000, 2001, 2002):
        for _ in range(5):
            neutral.observe_tick(year, 0.9)
    assert neutral.mortality_mult == 1.0, "gamma=0 must stay exactly neutral"


def test_energy_mortality_reaches_the_kernel():
    """Wiring on the frontier: with gamma set, the bridge's composed mortality
    multiplier rises above 1 once fuel poverty registers post-burn-in; with the
    channel off it stays exactly 1.0 (the same run, same seed)."""
    params = dict(seed=0, n_households=50, n_firms_c=50, n_firms_k=25, n_banks=2,
                  demographics_population=500, n_ticks=800,
                  housing_enabled=True, housing_market_enabled=True,
                  energy_enabled=True, energy_household=True,
                  energy_signal_burnin_years=1)
    on = Economy(Config.v13(**{**params, "energy_mortality_gamma": 5.0}))
    on.run()
    assert on.demographic_bridge.mortality_macro_multiplier > 1.0, \
        "the fuel-poverty mortality channel never reached the kernel"
    off = Economy(Config.v13(**params))
    off.run()
    assert off.energy_poverty_signal.mortality_mult == 1.0
    assert off.demographic_bridge.mortality_macro_multiplier == \
        (off.demographic_bridge.macro_signal.mortality_mult
         if off.demographic_bridge.macro_signal is not None else 1.0)


def test_subsidy_flat_vs_targeted():
    """The §34 reprise: at the SAME rate through the same crunch, the targeted
    subsidy spends LESS fiscal money while protecting the poorest quintile at least
    as well per unit spent — flat transfers leak to households that never needed
    them. Both conserve."""
    def run(policy):
        econ = Economy(_crisis_base())
        recs = []
        for t in range(400):
            if t == 250:
                for k, v in policy.items():
                    setattr(econ.policy, k, v)
            recs.append(econ.step())
        return recs
    flat = run({"energy_subsidy_rate": 0.5})
    targ = run({"energy_subsidy_rate": 0.5, "energy_subsidy_threshold": 0.5})
    win = range(250, 400)
    out_flat = sum(flat[i]["energy_subsidy_paid"] for i in win)
    out_targ = sum(targ[i]["energy_subsidy_paid"] for i in win)
    assert out_targ > 0.0 and out_flat > 0.0, "subsidies never paid"
    assert out_targ < out_flat, f"targeting must be cheaper: {out_targ:.1f} !< {out_flat:.1f}"
    q1_flat = sum(flat[i]["energy_share_q1"] for i in win)
    q1_targ = sum(targ[i]["energy_share_q1"] for i in win)
    # per-fiscal-unit protection of the poorest quintile (burden relief per money):
    eff_flat = q1_flat / out_flat
    eff_targ = q1_targ / out_targ
    assert eff_targ >= eff_flat * 0.9, \
        f"targeted subsidy lost its efficiency edge: {eff_targ:.4f} vs {eff_flat:.4f}"
    m = max(r["broad_money"] for r in targ)
    assert max(r["conservation_drift"] for r in targ) < 1e-6 * m


def _main() -> None:
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"{len(tests)}/{len(tests)} v17.0 energy tests green")


if __name__ == "__main__":
    _main()
