"""Regression gates for equity quotes that reach the numerical price floor."""
from __future__ import annotations

import math

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.markets.matching import EPS
from macro_sim.systems.banking import bank_stock_market
from macro_sim.systems.valuation import floor_safe_price_return


def _economy() -> Economy:
    return Economy(Config.v13(
        seed=1,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        n_ticks=2,
        government=True,
    ))


def test_price_floor_restart_has_no_artificial_return_signal():
    assert floor_safe_price_return(0.0, EPS) == 0.0
    assert floor_safe_price_return(EPS, 2.0 * EPS) == 0.0
    assert floor_safe_price_return(2.0, 3.0) == pytest.approx(0.5)


def test_alive_zero_price_bank_recovers_to_floor_without_dividing_by_zero():
    economy = _economy()
    bank = economy.banks[0]
    assert bank.alive and bank.shares_outstanding > EPS
    bank.share_price = 0.0
    bank.share_trend = 0.5
    trend_lambda = economy.cfg.banking.trend_lambda

    bank_stock_market(economy, rate=0.01)

    assert bank.share_last_price == 0.0
    assert bank.share_price == EPS
    assert bank.share_trend == pytest.approx(0.5 * (1.0 - trend_lambda))
    assert math.isfinite(bank.share_trend)
    assert sum((bank.owners or {}).values()) == pytest.approx(
        bank.shares_outstanding
    )
    economy.ledger.assert_conserved()
    economy.ledger.assert_non_negative()
