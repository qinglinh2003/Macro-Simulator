from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.systems.central_bank import assert_omo_balance_sheet, run_omo_phase


def _economy(**overrides) -> Economy:
    params = dict(
        n_firms_c=4,
        n_firms_k=2,
        n_households=20,
        n_banks=2,
        n_ticks=1,
        seed=17,
        omo=True,
        omo_reserve_target=0.0,
        omo_drain_frac=1.0,
    )
    params.update(overrides)
    return Economy(Config.v124(**params))


def test_omo_drain_swaps_reserves_for_equal_bank_cb_claims():
    econ = _economy()
    opening = {bank.id: econ.ledger.reserves(bank.id) for bank in econ.banks}
    opening_total = sum(opening.values())

    run_omo_phase(econ)

    drained = opening_total - sum(econ.ledger.reserves(bank.id) for bank in econ.banks)
    assert drained > 0.0
    assert sum(econ._cb_omo_claims.values()) == pytest.approx(drained)
    assert econ._cb_absorbed == pytest.approx(drained)
    for bank in econ.banks:
        assert econ._cb_omo_claims[bank.id] == pytest.approx(
            opening[bank.id] - econ.ledger.reserves(bank.id)
        )
    assert_omo_balance_sheet(econ)
    econ.ledger.assert_reserves_conserved()


def test_omo_injection_redeems_the_actual_holders_not_every_bank_equally():
    econ = _economy()
    run_omo_phase(econ)
    claims_before = dict(econ._cb_omo_claims)
    assert sum(claims_before.values()) > 0.0

    # Restore the genesis target. With full adjustment this matures every bill.
    econ.policy.omo_reserve_target = 1.0
    run_omo_phase(econ)

    assert econ._cb_absorbed == pytest.approx(0.0, abs=1e-8)
    assert sum(econ._cb_omo_claims.values()) == pytest.approx(0.0, abs=1e-8)
    for bank in econ.banks:
        assert econ.ledger.reserves(bank.id) == pytest.approx(claims_before[bank.id])
    assert_omo_balance_sheet(econ)


def test_failed_bank_cb_claim_moves_with_resolution_before_redemption():
    econ = _economy()
    run_omo_phase(econ)
    failed, survivor = econ.banks
    stranded = econ._cb_omo_claims[failed.id]
    assert stranded > 0.0
    failed.alive = False
    survivor_claim = econ._cb_omo_claims[survivor.id]
    econ.policy.omo_reserve_target = 1.0

    run_omo_phase(econ)

    assert econ._cb_omo_claims[failed.id] == pytest.approx(0.0)
    assert econ._cb_omo_claims[survivor.id] == pytest.approx(0.0, abs=1e-8)
    assert econ.ledger.reserves(survivor.id) == pytest.approx(
        survivor_claim + stranded,
    )
    assert_omo_balance_sheet(econ)
