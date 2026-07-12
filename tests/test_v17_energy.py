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
                ef.a *= 0.5                        # uc = w/a doubles; B3 does the rest
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


def _main() -> None:
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"{len(tests)}/{len(tests)} v17.0 energy tests green")


if __name__ == "__main__":
    _main()
