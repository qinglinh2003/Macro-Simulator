"""v21.1 — the international capital account: yield-driven persistent positions (PLAN_v21).

Gates: (1) capital off ⇒ the trade layer is byte-identical to v20; (2) conservation holds
with capital on; (3) a rate differential drives capital to the high-rate economy — its
currency appreciates, it runs a persistent NFA deficit, and it pays factor income abroad
(GNP < GDP); (4) capital creates a LARGER persistent NFA than the mean-reverting v20 layer.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from macro_sim.behavior import planning as B
from macro_sim.config import Config
from macro_sim.systems.banking import fail_bank, settlement_node
from macro_sim.world import World
from macro_sim.world.capital import EXTERNAL_ISSUER_ID, capital_interest
from macro_sim.world.fx import DEALER_ID


_DAYS_PER_YEAR = 365.0
_BASE_TICK_RATE = 0.04 / _DAYS_PER_YEAR
_LOW_TICK_RATE = 0.02 / _DAYS_PER_YEAR
_HIGH_TICK_RATE = 0.06 / _DAYS_PER_YEAR


def _digest(records) -> str:
    h = hashlib.sha256()
    for rec in records:
        for k in sorted(rec.keys()):
            h.update(k.encode())
            h.update(repr(rec[k]).encode())
    return h.hexdigest()


def _cfg(seed=0, r=_BASE_TICK_RATE):
    return Config.v124(
        n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=40,
        seed=seed, r_interest=r,
    )


def test_capital_off_is_v20_trade_identical():
    """capital=False ⇒ economies evolve exactly as the v20 trade layer (the grope
    adjustment and factor income are no-ops)."""
    a = World([_cfg(), _cfg()], base_seed=7, trade=True)                     # no capital
    a.run()
    b = World([_cfg(), _cfg()], base_seed=7, trade=True, capital=False, capital_mobility=5.0)
    b.run()  # capital flag off ⇒ mobility ignored
    for i in range(2):
        assert _digest(a.economies[i].records) == _digest(b.economies[i].records)


def test_capital_conserves():
    hi, lo = _cfg(r=_HIGH_TICK_RATE), _cfg(r=_LOW_TICK_RATE)
    world = World([hi, lo], base_seed=9, trade=True, capital=True,
                  capital_mobility=2.0 * _DAYS_PER_YEAR, periods_per_year=12)
    world.run()
    for econ in world.economies:
        econ.ledger.assert_conserved()
        econ.ledger.assert_non_negative()


def _mean(recs, key, i, n=60):
    tail = recs[-min(n, len(recs)):]
    return sum(r[key][i] for r in tail) / len(tail)


def test_high_rate_economy_runs_deficit_and_pays_factor_income():
    """Interest differential ⇒ capital flows to the high-rate economy: it runs a persistent
    NFA DEFICIT (foreigners accumulate claims on it) and pays factor income abroad (GNP <
    GDP) — the emerging-market carry pattern. Assessed on the settled average (the position
    is a stock the flows converge to; a single tick is noisy)."""
    hi, lo = _cfg(r=_HIGH_TICK_RATE), _cfg(r=_LOW_TICK_RATE)
    world = World([hi, lo], base_seed=9, trade=True, capital=True,
                  capital_mobility=3.0 * _DAYS_PER_YEAR,
                  capital_adjust=0.2, periods_per_year=12)
    world.run()
    wr = world.world_records
    assert _mean(wr, "nfa", 0) < 0.0         # high-rate economy is a net foreign DEBTOR
    assert _mean(wr, "nfa", 1) > 0.0         # low-rate economy is a net foreign CREDITOR
    assert _mean(wr, "factor_income", 0) < 0.0   # debtor pays interest abroad (GNP < GDP)


def test_capital_deepens_nfa_vs_mean_reverting_v20():
    """Capital ON accumulates a larger persistent NFA than the mean-reverting (v20) layer."""
    hi, lo = _cfg(r=_HIGH_TICK_RATE), _cfg(r=_LOW_TICK_RATE)
    on = World(
        [hi, lo], base_seed=9, trade=True, capital=True,
        capital_mobility=3.0 * _DAYS_PER_YEAR, capital_adjust=0.2,
    )
    on.run()
    off = World(
        [_cfg(r=_HIGH_TICK_RATE), _cfg(r=_LOW_TICK_RATE)],
        base_seed=9, trade=True,
    )  # v20 mean-revert
    off.run()
    assert abs(_mean(on.world_records, "nfa", 0)) > abs(_mean(off.world_records, "nfa", 0))


def test_factor_income_uses_the_same_per_tick_rate_as_domestic_debt_service():
    rate = 0.0125
    principal = 1.0
    cfg = Config.v3(
        n_firms_c=2, n_firms_k=1, n_households=4, n_ticks=1,
        r_interest=rate, d_bank0=100.0,
    )
    # A deliberately large reporting frequency proves it does not rescale a rate
    # that Config and the domestic credit system already express per tick.
    world = World(
        [cfg, cfg], base_seed=7, couple=True, capital=True,
        periods_per_year=365.0,
    )
    debtor, creditor = world.economies
    debtor._rate = creditor._rate = rate

    debtor.ledger.transfer(debtor.households[0].id, DEALER_ID, principal)
    creditor.ledger.transfer(DEALER_ID, creditor.households[0].id, principal)
    debtor_inventory_before = debtor.ledger.balance(DEALER_ID)
    creditor_inventory_before = creditor.ledger.balance(DEALER_ID)

    _, domestic_interest = B.debt_service_amounts(
        principal, deposits=10.0, r=rate, amort=0.0,
    )
    capital_interest(world)

    assert world._factor_income == pytest.approx([domestic_interest, -domestic_interest])
    assert debtor.ledger.balance(DEALER_ID) - debtor_inventory_before == pytest.approx(
        domestic_interest
    )
    assert creditor.ledger.balance(DEALER_ID) - creditor_inventory_before == pytest.approx(
        -domestic_interest
    )


def test_external_interest_uses_explicit_aggregate_issuer_not_bank_capital():
    cfg = Config.v3(
        n_firms_c=2, n_firms_k=1, n_households=4, n_ticks=1,
        r_interest=1.0, d_bank0=5.0,
    )
    world = World([cfg, cfg], base_seed=11, couple=True, capital=True)
    debtor, creditor = world.economies
    debtor._rate = creditor._rate = 1.0
    principal = 100.0
    debtor.ledger.transfer(debtor.households[0].id, DEALER_ID, principal)
    creditor.ledger.transfer(DEALER_ID, creditor.households[0].id, principal)

    bank = debtor.bank
    keep = 2.0
    debtor.ledger.transfer(
        bank.id, debtor.households[1].id,
        max(0.0, debtor.ledger.balance(bank.id) - keep),
    )
    opening = debtor.ledger.balance(bank.id)
    issuer_opening = debtor.ledger.balance(EXTERNAL_ISSUER_ID)

    capital_interest(world)

    assert world._factor_income[0] == pytest.approx(principal)
    assert world._factor_income_arrears[0] == pytest.approx(0.0)
    assert debtor.ledger.balance(bank.id) == pytest.approx(opening)
    assert debtor.ledger.balance(EXTERNAL_ISSUER_ID) == pytest.approx(
        issuer_opening - principal
    )
    assert world._factor_income[1] == pytest.approx(-principal)


def test_external_interest_is_independent_of_bank_order_and_bank_pnl():
    cfg = Config.v11(
        n_firms_c=2,
        n_firms_k=1,
        n_households=4,
        n_banks=2,
        n_ticks=1,
        r_interest=0.1,
        d_bank0=100.0,
        bank_equity=True,
    )
    world = World([cfg, cfg], base_seed=19, couple=True, capital=True)
    debtor, creditor = world.economies
    debtor._rate = creditor._rate = 0.1
    principal = 10.0
    debtor.ledger.transfer(debtor.households[0].id, DEALER_ID, principal)
    creditor.ledger.transfer(DEALER_ID, creditor.households[0].id, principal)

    debtor.banks.reverse()
    bank_cash = {bank.id: debtor.ledger.balance(bank.id) for bank in debtor.banks}
    fiscal_opening = debtor.ledger.balance(debtor._fiscal)

    capital_interest(world)

    due = principal * debtor._rate
    assert debtor.ledger.balance(debtor._fiscal) == pytest.approx(fiscal_opening - due)
    assert {
        bank.id: debtor.ledger.balance(bank.id) for bank in debtor.banks
    } == pytest.approx(bank_cash)
    assert all(bank.external_interest_expense == 0.0 for bank in debtor.banks)
    assert debtor.ledger.balance(DEALER_ID) == pytest.approx(principal + due)
    assert debtor._external_interest_fiscal == pytest.approx(due)


def test_fx_dealer_settles_at_clearing_even_after_bank_failure():
    cfg = Config.v11(
        n_firms_c=2,
        n_firms_k=1,
        n_households=4,
        n_banks=2,
        n_ticks=1,
        interbank=True,
    )
    world = World([cfg, cfg], base_seed=29, couple=True, capital=True)
    econ = world.economies[0]
    failed = econ.banks[0]
    payer = next(h for h in econ.households if econ._bank_of[h.id] is failed)
    econ.ledger.transfer(payer.id, DEALER_ID, 1.0)

    assert settlement_node(econ, DEALER_ID) == "CLEARING"
    assert econ._node_of[DEALER_ID] == "CLEARING"
    fail_bank(econ, failed)
    dead_reserves = econ.ledger.reserves(failed.id)
    econ.ledger.transfer(DEALER_ID, payer.id, 0.5)

    assert settlement_node(econ, DEALER_ID) == "CLEARING"
    assert econ.ledger.reserves(failed.id) == pytest.approx(dead_reserves)


def test_peg_reserve_account_settles_at_cb_independent_of_bank_failure():
    cfg = Config.v11(
        n_firms_c=2,
        n_firms_k=1,
        n_households=4,
        n_banks=2,
        n_ticks=1,
        interbank=True,
    )
    world = World(
        [cfg, cfg], base_seed=31, couple=True, capital=True, peg=True,
        peg_reserves0=10.0,
    )
    # CBRES is a real account in the anchor-currency ledger.
    econ = world.economies[world.peg_anchor]
    failed = econ.banks[0]

    assert settlement_node(econ, "CBRES") == "CB"
    # Force the ledger resolver to memoize the account before the failure; the
    # regression was specifically a stale commercial-bank cache entry.
    econ.ledger.transfer("CBRES", DEALER_ID, 0.1)
    assert econ._node_of["CBRES"] == "CB"
    fail_bank(econ, failed)
    dead_reserves = econ.ledger.reserves(failed.id)
    econ.ledger.transfer("CBRES", DEALER_ID, 1.0)

    assert settlement_node(econ, "CBRES") == "CB"
    assert econ.ledger.reserves(failed.id) == pytest.approx(dead_reserves)


def test_factor_income_services_opening_not_same_tick_new_positions():
    cfg = Config.v3(
        n_firms_c=2,
        n_firms_k=1,
        n_households=4,
        n_ticks=1,
        r_interest=0.01,
    )
    world = World([cfg, cfg], base_seed=31, couple=True, capital=True)
    debtor, creditor = world.economies
    debtor._rate = creditor._rate = 0.01
    debtor.ledger.transfer(debtor.households[0].id, DEALER_ID, 100.0)
    creditor.ledger.transfer(DEALER_ID, creditor.households[0].id, 100.0)

    capital_interest(world, positions=[0.0, 0.0])

    assert world._factor_income == pytest.approx([0.0, 0.0])
    capital_interest(world)
    assert world._factor_income == pytest.approx([1.0, -1.0])


def test_unpaid_external_interest_is_a_persistent_arrears_stock():
    cfg = Config.v3(
        n_firms_c=2,
        n_firms_k=1,
        n_households=4,
        n_ticks=1,
        r_interest=0.1,
    )
    world = World([cfg, cfg], base_seed=37, couple=True, capital=True)
    debtor, creditor = world.economies
    debtor._rate = creditor._rate = 0.1
    debtor.ledger.remove_account(EXTERNAL_ISSUER_ID)
    debtor.ledger.transfer(debtor.households[0].id, DEALER_ID, 10.0)
    creditor.ledger.transfer(DEALER_ID, creditor.households[0].id, 10.0)

    capital_interest(world)
    assert world._factor_income_arrears[0] == pytest.approx(1.0)
    assert world._factor_income_unpaid_tick[0] == pytest.approx(1.0)
    capital_interest(world)
    assert world._factor_income_arrears[0] == pytest.approx(2.0)
    assert world._factor_income_unpaid_tick[0] == pytest.approx(1.0)


def test_external_interest_settlement_fraction_validates_scalar_and_country_values():
    cfg = Config.v3(n_firms_c=2, n_firms_k=1, n_households=4, n_ticks=1)

    scalar = World(
        [cfg, cfg], couple=True, capital=True,
        external_interest_settlement_fraction=0.25,
    )
    vector = World(
        [cfg, cfg], couple=True, capital=True,
        external_interest_settlement_fraction=[0.0, 1.0],
    )

    assert scalar.external_interest_settlement_fraction == [0.25, 0.25]
    assert vector.external_interest_settlement_fraction == [0.0, 1.0]
    for invalid in (-0.01, 1.01, float("inf"), [0.5], [0.5, 2.0]):
        with pytest.raises(ValueError, match="external_interest_settlement_fraction"):
            World(
                [cfg, cfg], couple=True, capital=True,
                external_interest_settlement_fraction=invalid,
            )


def test_legal_settlement_policy_creates_and_cures_arrears_with_no_current_due():
    cfg = Config.v3(
        n_firms_c=2, n_firms_k=1, n_households=4, n_ticks=1,
        r_interest=0.1,
    )
    world = World(
        [cfg, cfg], base_seed=41, couple=True, capital=True,
        external_interest_settlement_fraction=0.0,
    )
    debtor, creditor = world.economies
    debtor._rate = creditor._rate = 0.1

    # This is a fully legal World: EXTISSUER exists and remains the aggregate payer.
    assert debtor.ledger.has_account(EXTERNAL_ISSUER_ID)
    capital_interest(world, positions=[10.0, -10.0])

    assert world._factor_income == pytest.approx([0.0, 0.0])
    assert world._factor_income_unpaid_tick == pytest.approx([1.0, 0.0])
    assert world._factor_income_arrears == pytest.approx([1.0, 0.0])
    assert world._factor_income_arrears_bilateral[0] == pytest.approx([0.0, 1.0])

    # No current principal and no current creditor weights: the locked old claim
    # still has an owner and must be serviceable.
    world.external_interest_settlement_fraction = 1.0
    capital_interest(world, positions=[0.0, 0.0])

    assert world._factor_income == pytest.approx([1.0, -1.0])
    assert world._factor_income_accrued == pytest.approx([0.0, 0.0])
    assert world._factor_income_unpaid_tick == pytest.approx([0.0, 0.0])
    assert world._factor_income_arrears_cured_tick == pytest.approx([1.0, 0.0])
    assert world._factor_income_arrears == pytest.approx([0.0, 0.0])
    assert all(sum(row) == pytest.approx(0.0) for row in world._factor_income_arrears_bilateral)


def test_bilateral_arrears_keep_original_creditor_when_current_weights_flip():
    cfg = Config.v3(
        n_firms_c=2, n_firms_k=1, n_households=4, n_ticks=1,
        r_interest=0.1,
    )
    world = World(
        [cfg, cfg, cfg], base_seed=43, couple=True, capital=True,
        external_interest_settlement_fraction=0.0,
    )
    for econ in world.economies:
        econ._rate = 0.1

    capital_interest(world, positions=[10.0, -10.0, 0.0])
    assert world._factor_income_arrears_bilateral[0] == pytest.approx([0.0, 1.0, 0.0])

    # Creditor 2 owns the new principal, but creditor 1 still owns the old arrear.
    world.external_interest_settlement_fraction = 1.0
    capital_interest(world, positions=[10.0, 0.0, -10.0])

    assert world._factor_income_accrued_bilateral[0] == pytest.approx([0.0, 0.0, 1.0])
    assert world._factor_income_cash_bilateral[0] == pytest.approx([0.0, 1.0, 1.0])
    assert world._factor_income == pytest.approx([2.0, -1.0, -1.0])
    assert world._factor_income_arrears == pytest.approx([0.0, 0.0, 0.0])


def test_partial_three_country_settlement_is_fx_conserving_and_row_reconciled():
    cfg = Config.v3(
        n_firms_c=2, n_firms_k=1, n_households=4, n_ticks=1,
        r_interest=0.1,
    )
    world = World(
        [cfg, cfg, cfg], base_seed=47, couple=True, capital=True,
        external_interest_settlement_fraction=[0.25, 1.0, 1.0],
    )
    # Product-one rates: 2, 1, 1/2.
    world.rates.log_e = [math.log(2.0), 0.0, math.log(0.5)]
    for econ in world.economies:
        econ._rate = 0.1

    capital_interest(world, positions=[20.0, -4.0, -3.0])

    assert world._factor_income_accrued_bilateral[0] == pytest.approx([0.0, 0.8, 1.2])
    assert world._factor_income_cash_bilateral[0] == pytest.approx([0.0, 0.2, 0.3])
    assert world._factor_income_arrears_bilateral[0] == pytest.approx([0.0, 0.6, 0.9])
    assert world._factor_income_arrears[0] == pytest.approx(1.5)
    assert sum(world._factor_income_cash[i] / world.rates.e[i] for i in range(3)) == pytest.approx(0.0)
    assert sum(world._factor_income_accrued[i] / world.rates.e[i] for i in range(3)) == pytest.approx(0.0)


def test_legacy_debtor_only_arrears_migrate_without_loss_then_lock_owner():
    cfg = Config.v3(
        n_firms_c=2, n_firms_k=1, n_households=4, n_ticks=1,
        r_interest=0.0,
    )
    world = World(
        [cfg, cfg, cfg], base_seed=53, couple=True, capital=True,
        external_interest_settlement_fraction=0.0,
    )
    world._factor_income_arrears = [2.0, 0.0, 0.0]
    del world._factor_income_arrears_bilateral
    del world._factor_income_arrears_unallocated

    # A pre-bilateral checkpoint with no observable owner retains the full scalar.
    capital_interest(world, positions=[0.0, 0.0, 0.0])
    assert world._factor_income_arrears == pytest.approx([2.0, 0.0, 0.0])
    assert world._factor_income_arrears_unallocated == pytest.approx([2.0, 0.0, 0.0])

    # Once a creditor is observable, migration locks the old stock exactly once.
    capital_interest(world, positions=[0.0, -1.0, 1.0])
    assert world._factor_income_arrears_unallocated == pytest.approx([0.0, 0.0, 0.0])
    assert world._factor_income_arrears_bilateral[0] == pytest.approx([0.0, 2.0, 0.0])
    assert sum(world._factor_income_arrears_bilateral[0]) == pytest.approx(
        world._factor_income_arrears[0]
    )


def test_default_full_settlement_matches_the_legacy_aggregate_distribution():
    cfg = Config.v3(
        n_firms_c=2, n_firms_k=1, n_households=4, n_ticks=1,
        r_interest=0.0,
    )
    world = World([cfg, cfg, cfg, cfg], base_seed=59, couple=True, capital=True)
    world.rates.log_e = [math.log(2.0), 0.0, math.log(0.5), 0.0]
    world.economies[0]._rate = 0.1
    world.economies[1]._rate = 0.2
    world.economies[2]._rate = world.economies[3]._rate = 0.0

    # In the common numeraire: debtors +10,+10; creditors -8,-12.
    capital_interest(world, positions=[20.0, 10.0, -4.0, -12.0])

    # Legacy full settlement collected 2/2 + 2/1 = 3 numeraire and distributed
    # it by current creditor weights 8:12.  The bilateral implementation must
    # preserve that default cash result while retaining its richer ownership data.
    assert world.external_interest_settlement_fraction == [1.0] * 4
    assert world._factor_income == pytest.approx([2.0, 2.0, -0.6, -1.8])
    assert world._factor_income_arrears == pytest.approx([0.0] * 4)
    assert sum(world._factor_income[i] / world.rates.e[i] for i in range(4)) == pytest.approx(0.0)
