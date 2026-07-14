"""Open-economy governance policy levers (PLAN_v20 §12 Layer C): tariff (trade), capital
controls (capital), sanctions (strategic). Each is a run-time government lever on a
dealer-routed flow; off ⇒ the prior version's behavior; all conserving.
"""

from __future__ import annotations

from macro_sim.config import Config
from macro_sim.world import World


def _cfg(a=1.0, r=0.04):
    return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=250, seed=0, a=a, r_interest=r)


def _mean(recs, fn, n=40):
    return sum(fn(r) for r in recs[-n:]) / n


# -- trade policy: tariff -----------------------------------------------------

def test_tariff_is_protective_and_raises_revenue():
    base = World([_cfg(1.5), _cfg(0.6)], base_seed=9, trade=True)
    base.run()
    tar = World([_cfg(1.5), _cfg(0.6)], base_seed=9, trade=True, tariff=0.01)
    tar.run()
    for econ in tar.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    imp_base = _mean(base.world_records, lambda r: sum(r["import_value"]))
    imp_tar = _mean(tar.world_records, lambda r: sum(r["import_value"]))
    assert imp_tar < imp_base                                   # protective (fewer imports)
    assert _mean(tar.world_records, lambda r: sum(r["tariff_rev"])) > 0.0   # fiscal revenue


# -- capital policy: capital controls (the trilemma's third corner) -----------

def _peg(control):
    lo = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=0, r_interest=0.02)
    an = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=0, r_interest=0.05)
    return World([lo, an], base_seed=9, trade=True, capital=True, capital_mobility=3.0,
                 capital_adjust=0.2, peg=True, peg_reserves0=5000.0, peg_reserve_scale=0.02,
                 capital_control=control)


def test_capital_controls_save_the_peg():
    """Peg + an independent rate breaks WITHOUT controls (reserves drain) but SURVIVES with
    controls — closing the capital account is the trilemma's third corner (peg + autonomy)."""
    free = _peg(0.0)
    free.run()
    closed = _peg(0.95)
    closed.run()
    assert any(not r["peg_intact"] for r in free.world_records)     # free capital ⇒ crisis
    assert all(r["peg_intact"] for r in closed.world_records)       # controls ⇒ peg survives


# -- strategic: sanctions -----------------------------------------------------

def test_sanctions_sever_bilateral_trade():
    """A sanction zeroes the pair's bilateral flow; for N=2 that is autarky (no trade)."""
    world = World([_cfg(1.5), _cfg(0.6)], base_seed=9, trade=True, sanctions={frozenset({0, 1})})
    world.run()
    for econ in world.economies:
        econ.ledger.assert_conserved()
    assert sum(sum(r["import_value"]) for r in world.world_records) == 0.0


# -- trade policy: quantity controls & export levers ---------------------------

def _trade(**kw):
    w = World([_cfg(1.5), _cfg(0.6)], base_seed=9, trade=True, **kw)
    w.run()
    return w


def test_import_quota_is_a_quantity_control():
    """A quota caps the VOLUME admitted (unlike the tariff's price control)."""
    base, quota = _trade(), _trade(import_quota=0.01)
    for econ in quota.economies:
        econ.ledger.assert_conserved()
    assert _mean(quota.world_records, lambda r: sum(r["import_value"])) < \
           _mean(base.world_records, lambda r: sum(r["import_value"]))


def test_export_subsidy_wins_share_at_fiscal_cost():
    """An exporter's subsidy makes its goods cheaper abroad ⇒ it wins export share, and its
    own fiscus funds the gap (the mercantilist trade)."""
    base = _trade()
    sub = _trade(export_subsidy=[0.0, 0.05])          # economy 1 subsidises its exports
    for econ in sub.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    # economy 0 imports MORE from the now-cheaper economy 1
    assert _mean(sub.world_records, lambda r: r["import_value"][0]) > \
           _mean(base.world_records, lambda r: r["import_value"][0])
    assert _mean(sub.world_records, lambda r: r["export_subsidy_cost"][1]) > 0.0   # fiscus paid


def test_export_tax_raises_revenue():
    """A negative subsidy is an export TAX — the exporter's fiscus collects."""
    tax = _trade(export_subsidy=[0.0, -0.05])
    for econ in tax.economies:
        econ.ledger.assert_conserved()
    assert _mean(tax.world_records, lambda r: r["export_subsidy_cost"][1]) < 0.0   # revenue


# -- migration policy: exit control, host remittance tax, guest workers --------

def _mig(**kw):
    # The gap must be in WAGES, not productivity: this model is demand-constrained, so `a`
    # moves neither output nor wages and would give no wage gap for migration to respond to.
    lo = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=300, seed=0,
                     w_firm0=0.7, p_firm0=0.85)
    hi = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=300, seed=0,
                     w_firm0=1.4, p_firm0=1.7)
    w = World([lo, hi], base_seed=9, trade=True, capital=True, migration=True,
              capital_mobility=1.0, migration_rate=0.03, remittance_share=0.2, **kw)
    w.run()
    return w


def test_emigration_cap_blocks_exit():
    """POLICY: the ORIGIN restricts its own people from leaving."""
    base, capped = _mig(), _mig(emigration_cap=0.02)
    for econ in capped.economies:
        econ.ledger.assert_conserved()
    assert capped.world_records[-1]["migrant_stock"][0] < base.world_records[-1]["migrant_stock"][0]


def test_host_outward_remittance_tax_skims_the_outflow():
    """POLICY: the HOST taxes remittances leaving (the Gulf pattern) ⇒ less reaches origin."""
    base, taxed = _mig(), _mig(outward_remittance_tax=0.30)
    for econ in taxed.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    assert _mean(taxed.world_records, lambda r: r["remittances"][0]) < \
           _mean(base.world_records, lambda r: r["remittances"][0])


def test_guest_worker_regime_damps_the_migrant_stock():
    """POLICY: temporary migration — migrants return home at a rate ⇒ a smaller steady stock."""
    base, guest = _mig(), _mig(guest_worker_return=0.05)
    for econ in guest.economies:
        econ.ledger.assert_conserved()
    assert guest.world_records[-1]["migrant_stock"][0] < base.world_records[-1]["migrant_stock"][0]
