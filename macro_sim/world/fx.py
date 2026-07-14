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

    def book_revaluation(self, rates: RateVector) -> float:
        """Book the numéraire revaluation of held inventory since last tick (no
        transaction) into the valuation account, and return this tick's delta. At flat
        rates + zero inventory this is 0 (v20.1)."""
        nw = self.net_worth_numeraire(rates)
        delta = nw - self._prev_networth
        self.valuation += delta
        self._prev_networth = nw
        return delta
