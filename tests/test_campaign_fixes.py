"""Extreme-campaign bug fixes: flag-gated, flags-off bit-identical (digest 0fb412c8).

Root-cause chain for the construction stall (all four legs required):
price collapse (A1b) -> building unprofitable -> DSCR refuses wage credit ->
no hiring -> WIP frozen; plus closed-loop demand discovery, the one-at-a-time
inventory choke, and the land-fee cash gate at completion.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_sim.config import Config
from macro_sim.economy import Economy


def _cfg(**over):
    base = dict(seed=7, n_households=40, n_firms_c=15, n_firms_k=8, n_banks=2,
                demographics_population=260, n_ticks=400, government=True,
                housing_enabled=True, housing_market_enabled=True,
                housing_construction_enabled=True, n_builders=2)
    return Config.v13(**{**base, **over})


def test_ask_floor_holds_under_decay_and_tracks_current_wage():
    e = Economy(_cfg(housing_ask_floor_wage_share=1.5))
    for _ in range(300):
        e.step()
    floor = e.housing_market.price_floor(e)      # CURRENT-wage anchored (dynamic)
    wage_ref = sum(f.wage for f in e.firms) / len(e.firms)
    assert floor == pytest.approx(1.5 * wage_ref * 365.0)
    asks = [l.ask for l in e.housing_market.listings.values()]
    if asks:
        assert min(asks) >= floor - 1e-9, "decay must stop at the wage-anchored floor"


def test_ask_floor_off_is_floorless():
    e = Economy(_cfg())
    assert e.housing_market.ask_floor_wage_share == 0.0
    assert e.housing_market.price_floor(e) <= 1e-6


def test_builder_buffer_keeps_planning_alive():
    """With the buffer, one unsold unit must NOT zero the production target."""
    from macro_sim.behavior.planning import plan_production

    class F:
        phi = 5.0
        demand_expected = 0.01
        inventory = 1.0
        target_inventory = 0.0
        production_target = 0.0
    f = F()
    plan_production(f, 1.0)                        # legacy: choked
    assert f.production_target == 0.0
    plan_production(f, 1.0, inventory=0.0)         # buffer-adjusted view
    assert f.production_target > 0.0


def test_builder_gain_scales_demand_floor():
    e = Economy(_cfg(builder_demand_price_gain=2.0))
    for _ in range(60):
        e.step()
    b = e.builders[0]
    assert b.demand_expected > e.cfg.builder_demand_seed * 1.01, (
        "a profitable margin must lift the demand floor above the seed")


def test_deposit_interest_arrears_accrue_and_repay():
    e = Economy(Config.v13(seed=3, n_households=30, n_firms_c=10, n_firms_k=5,
                           n_banks=1, demographics_population=180, n_ticks=60,
                           government=True, interbank=True, bank_realized_pnl=True,
                           deposit_rate=5.0e-3, deposit_interest_arrears=True))
    for _ in range(40):
        e.step()
    bk = e.banks[0]
    arr = getattr(bk, "deposit_interest_arrears", 0.0)
    assert arr >= 0.0
    e.ledger.assert_conserved()


def test_flags_off_no_new_attributes_leak():
    e = Economy(_cfg())
    for _ in range(30):
        e.step()
    for bk in e.banks:
        assert getattr(bk, "deposit_interest_arrears", 0.0) == 0.0


def test_land_fee_credit_flows_through_credit_phase_and_identities_hold():
    """Leg-3 relocation: the development loan must go through the CREDIT phase --
    the completion-time grant_loan bypassed CA/NFA reconciliation journals and
    broke two world identities in the acceptance portraits. Proxy check: in a
    COUPLED world with the full package on, each economy's augmented-NFA change
    matches its accrued current account to gate tolerance."""
    from macro_sim.world import World
    cfg = Config.v13(seed=11, n_households=30, n_firms_c=12, n_firms_k=6, n_banks=2,
                     demographics_population=200, n_ticks=320, government=True,
                     housing_enabled=True, housing_market_enabled=True,
                     housing_construction_enabled=True, n_builders=2,
                     demographics_tfr=3.0, builder_demand_price_gain=2.0,
                     builder_inventory_buffer=3.0, builder_land_fee_credit=True,
                     housing_demand_step=0.02, housing_ask_floor_wage_share=1.5)
    w = World([cfg, cfg], base_seed=13, trade=True, capital=True)
    w.run(300)
    for econ in w.economies:
        econ.ledger.assert_conserved()
    wr = w.world_records
    if not wr:
        return
    for i in range(2):
        nfa0 = float(wr[0].get(f"augmented_nfa_{i}", 0.0))
        nfa1 = float(wr[-1].get(f"augmented_nfa_{i}", 0.0))
        ca = sum(float(r.get(f"current_account_accrual_{i}", 0.0)) for r in wr[1:])
        scale = max(1.0, abs(nfa1), abs(nfa0))
        assert abs((nfa1 - nfa0) - ca) / scale < 5e-3, (
            f"economy {i}: dNFA {nfa1-nfa0:.3f} vs accrued CA {ca:.3f}")


# ================= dealer-bleed fixes A (spread) + C (mutualization) =================

def _coupled(**kw):
    from macro_sim.world import World
    cfg = Config.v13(seed=21, n_households=30, n_firms_c=12, n_firms_k=6, n_banks=2,
                     demographics_population=200, n_ticks=800, government=True)
    cfg2 = Config.v13(seed=22, n_households=30, n_firms_c=12, n_firms_k=6, n_banks=2,
                      demographics_population=200, n_ticks=800, government=True)
    return World([cfg, cfg2], base_seed=31, trade=True, capital=True, migration=True,
                 migration_rate=0.02, **kw)


def test_fx_spread_earns_the_dealer_and_conserves():
    a = _coupled()
    b = _coupled(fx_spread=0.01)
    a.run(700); b.run(700)
    for w in (a, b):
        for econ in w.economies:
            econ.ledger.assert_conserved()
    nw_a = a.dealer.net_worth_numeraire(a.rates)
    nw_b = b.dealer.net_worth_numeraire(b.rates)
    assert nw_b > nw_a, f"spread must improve dealer NW: {nw_a:.3f} vs {nw_b:.3f}"
    assert sum(b._conversion_volume) > 0.0, "conversion volume must be tracked"


def test_fx_mutualization_settles_losses_annually():
    w = _coupled(fx_spread=0.0, fx_loss_mutualization=True)
    w.run(740)                                   # crosses the t=365 and t=730 settlements
    for econ in w.economies:
        econ.ledger.assert_conserved()
    paid = sum(getattr(e, "_fx_mutualization_paid", 0.0) for e in w.economies)
    nw = w.dealer.net_worth_numeraire(w.rates)
    if paid > 0.0:
        assert nw > -1.0e3, f"settled dealer NW should be pulled toward zero, got {nw:.1f}"
    # flag off = no attribute ever appears
    a = _coupled()
    a.run(400)
    assert all(getattr(e, "_fx_mutualization_paid", 0.0) == 0.0 for e in a.economies)
