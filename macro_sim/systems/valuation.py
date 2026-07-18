"""Dimensionally consistent valuation rates for the direct monetary frontier."""

from __future__ import annotations

from typing import Any

from macro_sim.markets.matching import EPS


def floor_safe_price_return(old_price: float, new_price: float) -> float:
    """Return a finite market return when a quote restarts at the price floor.

    A zero/sub-floor quote is a numerical boundary, not an economically meaningful
    transaction price.  Treating the move from that boundary to ``EPS`` as a 100%
    (or infinite) return would inject an artificial chartist signal.  The correct
    no-information update is therefore zero, which lets the existing trend EMA
    decay naturally.
    """
    old = float(old_price)
    if old <= EPS:
        return 0.0
    return (float(new_price) - old) / old


def valuation_discount_rate(econ: Any) -> float:
    """Return the positive per-tick required return used by equity valuations.

    The policy rate, floor and risk premium are all expressed on the model's tick
    clock.  The additive premium keeps valuation finite at the ZLB; unlike the legacy
    ``max(r, 0.01)`` shortcut, a one-basis-point-per-tick policy move is not erased by
    an annual-scale constant.
    """
    cfg = econ.cfg
    return max(
        float(cfg.valuation_discount_floor),
        max(0.0, float(econ._rate)) + float(cfg.valuation_risk_premium),
    )


def residual_income_fundamental(
    *,
    book_value: float,
    residual_income: float,
    shares_outstanding: float,
    discount_rate: float,
) -> float:
    """Book value plus a perpetuity of positive residual income, per share."""
    if shares_outstanding <= EPS:
        return 0.0
    discount = max(EPS, float(discount_rate))
    premium = max(0.0, float(residual_income)) / discount
    # Common equity is a limited-liability residual claim.  Negative accounting
    # book equity is meaningful, but a shareholder cannot owe the issuer through
    # a negative share price.
    return max(
        0.0,
        (float(book_value) + premium) / float(shares_outstanding),
    )
