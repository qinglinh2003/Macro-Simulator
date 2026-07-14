"""The foreign-exchange layer (PLAN_v20 §2, §3): the numéraire rate vector + the dealer.

v20.1 installs this machinery and proves it INERT with zero trade — rates stay flat, the
dealer holds zero inventory, the balance of payments is trivially balanced. The dealer's
account plumbing and groping become load-bearing in v20.2 when trade flows arrive.
"""

from __future__ import annotations

import math
from typing import List

# The dealer's account id inside every economy's ledger (its nostro balance in that
# currency). A NEGATIVE balance = the dealer owes currency i = foreigners hold a net
# claim on economy i (economy i ran a trade surplus).
DEALER_ID = "FXDEALER"


class BalanceOfPaymentsError(Exception):
    """The dealer's numéraire FLOW was not zero — a cross-border payload created or
    destroyed value. The open-economy analog of `ConservationError`: always a bug, never
    economics."""


class RateVector:
    """N nominal exchange rates against an abstract geometric-basket numéraire (§2).

    ``e_i`` = units of currency ``i`` per numéraire unit. Only the ratios ``e_i/e_j`` are
    physical (a gauge freedom); the equal-weight geometric-basket normalization
    ``Σ (1/N) log e_i = 0`` fixes the one redundant scale DOF and is re-applied every
    tick. Genesis: all ``e_i = 1`` (balanced, symmetric — already normalized).
    """

    def __init__(self, n: int):
        self.n = n
        self.log_e: List[float] = [0.0] * n
        self._normalize()

    def _normalize(self) -> None:
        mean = sum(self.log_e) / self.n
        self.log_e = [x - mean for x in self.log_e]

    @property
    def e(self) -> List[float]:
        return [math.exp(x) for x in self.log_e]

    def bilateral(self, i: int, j: int) -> float:
        """Units of currency ``i`` per unit of currency ``j`` = ``e_i / e_j``. Derived
        from the single vector, so triangular no-arbitrage holds by construction (§2)."""
        return math.exp(self.log_e[i] - self.log_e[j])

    def to_numeraire(self, amount: float, i: int) -> float:
        """Value ``amount`` units of currency ``i`` in the numéraire = ``amount / e_i``."""
        return amount / math.exp(self.log_e[i])

    def grope(self, signal: List[float], lam: float) -> None:
        """Move each log-rate on its currency's imbalance ``signal`` (the dealer's net
        inventory in v20.2 — grope IS mean-reversion, one rule, §3), then re-impose the
        gauge. Reductions are already in fixed economy-id order. With zero signal the
        rates are unchanged (v20.1)."""
        if lam == 0.0 or not any(signal):
            return
        for i in range(self.n):
            self.log_e[i] += lam * signal[i]
        self._normalize()


class FXDealer:
    """The World-level FX dealer (§3): one deposit account in every economy's ledger.

    Its per-currency inventory is its balance in that economy's ledger. Zero spread; the
    dealer is unowned at v20 (net worth floats, booked for conservation, not distributed).
    A rate move revalues its held inventory with no transaction — booked to ``valuation``
    (the World valuation account) so numéraire-denominated conservation never leaks (§6).
    """

    def __init__(self, economies):
        self.economies = economies
        for econ in economies:
            econ.ledger.add_account(DEALER_ID)
            econ.ledger.allow_negative(DEALER_ID)   # may owe currency i (a foreign claim)
        self.valuation = 0.0          # cumulative revaluation P&L in numéraire
        self._prev_networth = 0.0     # last tick's net worth in numéraire (for revaluation)

    def inventory(self) -> List[float]:
        """Net position in each currency = the dealer's ledger balance in that economy."""
        return [econ.ledger.balance(DEALER_ID) for econ in self.economies]

    def net_worth_numeraire(self, rates: RateVector) -> float:
        """Σ_i inventory_i valued in the numéraire."""
        inv = self.inventory()
        return sum(rates.to_numeraire(inv[i], i) for i in range(len(inv)))

    def assert_flow_is_passthrough(self, inv0, e0, tol: float = 1e-6) -> float:
        """**The open-economy hard gate — the multilateral BoP / passthrough identity.**

        The dealer is a zero-spread intermediary: every cross-border transaction credits it
        in one currency and debits it an EQUAL NUMÉRAIRE VALUE in another (an importer's
        payment funds the exporter; a remittance collected funds the payout; a tariff skim
        is exactly the gap between the gross and the base). So the tick's FLOW — its
        position change valued at the rates the flows happened at — must be ZERO:

            FLOW = Σ_i (inv1_i − inv0_i) / e0_i  ≡  0.

        A nonzero FLOW means some cross-border payload created or destroyed value. This is
        the analog of the closed economy's `ConservationError` — always a bug, never
        economics. Unlike a gauge, it can actually fail. Called BEFORE the rates grope, so
        no revaluation contaminates it.
        """
        inv1 = self.inventory()
        flow = sum((inv1[i] - inv0[i]) / e0[i] for i in range(len(inv1)))
        scale = max(1.0, sum(abs(inv1[i]) / e0[i] for i in range(len(inv1))))
        if abs(flow) > tol * scale:
            raise BalanceOfPaymentsError(
                f"dealer flow is not a passthrough (multilateral BoP violated): "
                f"flow={flow!r} numéraire (tol={tol * scale:.3e}) — a cross-border payload "
                f"created or destroyed value"
            )
        return flow

    def book_revaluation(self, e0, rates: RateVector) -> float:
        """Re-price the END-OF-TICK position from the pre-grope rates ``e0`` to the new
        rates. This is the ONLY source of change in the dealer's numéraire net worth (the
        flow being zero by the gate above), so the world identity closes exactly:

            Σ_i NFA_i  =  −(cumulative revaluation)

        — the world's apparent net position with itself is EXACTLY the accumulated valuation
        effect (the valuation channel), not zero but fully explained.
        """
        inv = self.inventory()
        e1 = rates.e
        reval = sum(inv[i] * (1.0 / e1[i] - 1.0 / e0[i]) for i in range(len(inv)))
        self.valuation += reval
        self._prev_networth = self.net_worth_numeraire(rates)
        return reval
