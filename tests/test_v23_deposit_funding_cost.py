"""v23: the bank's cost of funds (deposit funding cost).

Bank realized profit was `loan_interest + bond_coupon + interbank - external - credit_losses`
with NO deposit funding cost: deposits were free money, so a bank could never suffer a
net-interest-margin squeeze and a higher policy rate only ever RAISED bank profit.
`interest_by_deposits` looks related but is a DISTRIBUTION rule (it splits leftover dividends by
deposit share); it is not a P&L expense. `deposit_rate` pays real, money-conserving contractual
interest to depositors and books it as the missing expense leg.
"""
from __future__ import annotations

import hashlib
import json

from macro_sim.config import Config
from macro_sim.economy import Economy


def _cfg(**over):
    return Config.v13(seed=3, n_households=40, demographics_population=200, n_firms_c=20,
                      n_firms_k=10, n_banks=3, n_ticks=300, government=True,
                      bank_realized_pnl=True, bank_equity=True, bank_dynamics=True, **over)


def test_deposit_rate_is_off_by_default():
    assert Config.v13(seed=1, n_ticks=5).credit.deposit_rate == 0.0


def _digest(cfg):
    econ = Economy(cfg)
    h = hashlib.sha256()
    for _ in range(cfg.n_ticks):
        r = econ.step()
        h.update(json.dumps({k: (round(v, 9) if isinstance(v, float) else v)
                             for k, v in sorted(r.items())}, default=str).encode())
    return h.hexdigest()[:16]


def test_deposit_rate_zero_is_bit_identical():
    assert _digest(_cfg()) == _digest(_cfg(deposit_rate=0.0))


def test_positive_rate_books_a_funding_cost_and_conserves():
    econ = Economy(_cfg(deposit_rate=5e-5))
    drift = 0.0
    for _ in range(300):
        r = econ.step()
        drift = max(drift, abs(float(r.get("conservation_drift", 0.0) or 0.0)))
        broad = float(r.get("broad_money", r.get("total_money", 1.0)) or 1.0)
    # a real, money-conserving expense leg is now populated
    assert sum(getattr(b, "deposit_funding_cost", 0.0) for b in econ.banks) > 0.0
    assert drift < 1e-6 * max(1.0, broad)


def test_cost_of_funds_can_compress_the_net_interest_margin():
    """With free deposits NIM is definitionally 1.0; a deposit rate near the loan rate must be
    able to push realized bank profit below gross interest income."""
    free = Economy(_cfg(deposit_rate=0.0))
    paid = Economy(_cfg(deposit_rate=1e-4))
    for _ in range(300):
        free.step()
    for _ in range(300):
        paid.step()
    free_profit = sum(getattr(b, "profit", 0.0) for b in free.banks)
    paid_profit = sum(getattr(b, "profit", 0.0) for b in paid.banks)
    paid_cost = sum(getattr(b, "deposit_funding_cost", 0.0) for b in paid.banks)
    assert paid_cost > 0.0
    assert paid_profit < free_profit  # the cost of funds reduces realized profit
