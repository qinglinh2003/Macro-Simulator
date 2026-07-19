"""Open-economy governance policy levers (PLAN_v20 §12 Layer C): tariff (trade), capital
controls (capital), sanctions (strategic). Each is a run-time government lever on a
dealer-routed flow; off ⇒ the prior version's behavior; all conserving.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.world import World
from macro_sim.world.trade import _export_subsidy_settle


def _cfg(a=1.0, r=0.04):
    return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=250, seed=0, a=a, r_interest=r)


def _mean(recs, fn, n=40):
    return sum(fn(r) for r in recs[-n:]) / n


# -- trade policy: tariff -----------------------------------------------------

def test_tariff_is_protective_and_raises_revenue():
    """At the same pre-treatment state, a tariff weakly lowers physical imports.

    A long-run single-seed comparison is not a local policy-sign test: tariff-induced
    FX, income and inventory feedback can eventually move nominal import value in
    either direction.  Keep the two worlds identical until the intervention tick so
    this assertion isolates the buyer-price channel the lever actually implements.
    """
    base = World([_cfg(1.5), _cfg(0.6)], base_seed=9, trade=True)
    tar = World([_cfg(1.5), _cfg(0.6)], base_seed=9, trade=True)
    for _ in range(200):
        base.step()
        tar.step()
    assert base.world_records == tar.world_records

    for e in tar.economies:                          # B5a: per-economy ownership
        e.external_policy.tariff = 0.01
    base.step()
    tar.step()
    for econ in tar.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    imp_base = sum(base.world_records[-1]["import_volume"])
    imp_tar = sum(tar.world_records[-1]["import_volume"])
    assert imp_tar < imp_base                                   # local protective channel
    assert sum(tar.world_records[-1]["tariff_rev"]) > 0.0      # fiscal revenue


# -- capital policy: capital controls (the trilemma's third corner) -----------

def _peg(control):
    lo = Config.v124(
        n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=120,
        seed=0, r_interest=0.02 / 365.0,
    )
    an = Config.v124(
        n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=120,
        seed=0, r_interest=0.05 / 365.0,
    )
    return World([lo, an], base_seed=9, trade=True, capital=True, capital_mobility=3.0 * 365.0,
                 capital_adjust=0.2, peg=True, peg_reserves0=5000.0, peg_reserve_scale=0.04,
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
    """At the same state, a subsidy lowers the foreign buyer price and costs the fiscus.

    As with the tariff sign test, a 250-tick comparison confounds the immediate policy
    channel with the induced FX, income and inventory path.  Those general-equilibrium
    feedbacks need not preserve a cumulative physical-import ranking, so identify the
    implemented price channel on one paired intervention tick.
    """
    base = World([_cfg(1.5), _cfg(0.6)], base_seed=9, trade=True)
    sub = World([_cfg(1.5), _cfg(0.6)], base_seed=9, trade=True)
    for _ in range(200):
        base.step()
        sub.step()
    assert base.world_records == sub.world_records

    sub.economies[1].external_policy.export_subsidy = 0.05   # B5a: economy 1 subsidises its exports
    base.step()
    sub.step()
    for econ in sub.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    assert sub._import_source[0] == 1
    assert sub.world_records[-1]["import_volume"][0] > \
           base.world_records[-1]["import_volume"][0]
    assert sub.world_records[-1]["export_subsidy_cost"][1] > 0.0


def test_export_tax_raises_revenue():
    """A negative subsidy is an export TAX — the exporter's fiscus collects."""
    tax = _trade(export_subsidy=[0.0, -0.05])
    for econ in tax.economies:
        econ.ledger.assert_conserved()
    assert _mean(tax.world_records, lambda r: r["export_subsidy_cost"][1]) < 0.0   # revenue


def test_export_policy_is_allocated_only_to_realized_exporters():
    world = World([_cfg(), _cfg()], trade=True, export_subsidy=[0.05, 0.0])
    econ = world.economies[0]
    exporter, bystander = econ.c_firms[:2]
    exporter_before = econ.ledger.balance(exporter.id)
    bystander_before = econ.ledger.balance(bystander.id)

    cost = _export_subsidy_settle(
        world, 0, econ, 95.0, {exporter.id: 95.0},
    )

    assert cost == pytest.approx(5.0)
    assert econ.ledger.balance(exporter.id) - exporter_before == pytest.approx(5.0)
    assert econ.ledger.balance(bystander.id) == pytest.approx(bystander_before)

    taxed = World([_cfg(), _cfg()], trade=True, export_subsidy=[-0.05, 0.0])
    taxed_econ = taxed.economies[0]
    taxed_exporter = taxed_econ.c_firms[0]
    fiscal_before = taxed_econ.ledger.balance(taxed_econ._fiscal)
    revenue = _export_subsidy_settle(
        taxed, 0, taxed_econ, 105.0, {taxed_exporter.id: 105.0},
    )
    assert revenue == pytest.approx(-5.0)
    assert taxed_econ.ledger.balance(taxed_econ._fiscal) - fiscal_before == pytest.approx(5.0)


# -- migration policy: exit control, host remittance tax, guest workers --------

def _mig(*, run=True, **kw):
    # The gap must be in WAGES, not productivity: this model is demand-constrained, so `a`
    # moves neither output nor wages and would give no wage gap for migration to respond to.
    lo = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=300, seed=0,
                     w_firm0=0.7, p_firm0=0.85, r_interest=0.0,
                     central_bank=False)
    hi = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=300, seed=0,
                     w_firm0=1.4, p_firm0=1.7, r_interest=0.0,
                     central_bank=False)
    w = World([lo, hi], base_seed=9, trade=True, capital=True, migration=True,
              capital_mobility=1.0, migration_rate=0.03, remittance_share=0.2, **kw)
    if run:
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
    base = _mig(run=False)
    taxed = _mig(run=False, outward_remittance_tax=0.30)
    observed = False
    for _ in range(10):
        base.step()
        taxed.step()
        gross = base.world_records[-1]["remittances"][0]
        if gross > 1.0e-9:
            assert taxed.world_records[-1]["remittances"][0] == pytest.approx(0.70 * gross)
            observed = True
            break
    for econ in taxed.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()
    assert observed


def test_guest_worker_regime_damps_the_migrant_stock():
    """POLICY: temporary migration — migrants return home at a rate ⇒ a smaller steady stock."""
    base, guest = _mig(), _mig(guest_worker_return=0.05)
    for econ in guest.economies:
        econ.ledger.assert_conserved()
    assert guest.world_records[-1]["migrant_stock"][0] < base.world_records[-1]["migrant_stock"][0]
