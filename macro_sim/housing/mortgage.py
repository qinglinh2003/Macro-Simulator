"""v15.2 mortgages: collateralization book over the EXISTING household credit rails.

Design (PLAN_v15.md v15.2 notes, applied):
- The loan itself is ordinary non-margin household ledger debt: the certified credit
  machinery already amortizes it (cfg.credit.hh_amort) and charges the FLOATING
  loan_rate_for -- repayment pace and monetary transmission cost zero new code and
  zero new claim postings (creation/repayment/writeoff posting APIs are the ones the
  margin machinery uses).
- This book tracks only what the ledger cannot: WHICH dwelling collateralizes the
  debt. Its balance is a shadow clamped FROM ABOVE by (ledger debt - margin shadow)
  at every session -- the sweep-based reconciliation lesson (household-emptying,
  merges, death settlements and generic amortization all move ledger debt through
  paths this book never sees; deriving truth per session is structurally complete
  where per-event hooks are not).
- Foreclosure: underwater (balance > foreclosure_ltv x collateral value) AND broke
  (deposits < arrears floor) => the creditor bank seizes title, the residual secured
  balance is written off (non-recourse), and the dwelling enters the market as a
  forced bank listing whose sale proceeds stay with the bank.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from macro_sim.markets.matching import EPS
from macro_sim.systems.banking import bank_for


@dataclass
class Mortgage:
    account: str
    dwelling_id: int
    balance: float          # secured-balance shadow, clamped by session maintenance


@dataclass
class MortgageBook:
    ltv_cap: float = 0.8
    foreclosure_ltv: float = 1.1
    arrears_floor: float = 2.0
    loans: dict[str, Mortgage] = field(default_factory=dict)   # one per household (owner-occupier)
    originated_total: float = 0.0
    foreclosures_total: int = 0

    def balance_total(self) -> float:
        return sum(loan.balance for loan in self.loans.values())

    def originate(self, econ: Any, buyer: Any, dwelling_id: int, amount: float) -> None:
        bridge = getattr(econ, "demographic_bridge", None)
        econ.ledger.create_loan(buyer.id, amount)
        if bridge is not None:
            bridge.post_household_debt_creation(buyer.id, amount)
        self.loans[buyer.id] = Mortgage(account=buyer.id, dwelling_id=dwelling_id, balance=amount)
        self.originated_total += amount

    def maintain(self, econ: Any) -> None:
        """Per-session reconciliation: derive each secured balance from the ledger truth,
        close paid-off or collateral-less entries, then run the foreclosure test."""
        led = econ.ledger
        housing = econ.housing
        market = econ.housing_market
        bridge = getattr(econ, "demographic_bridge", None)
        agents = {h.id: h for h in econ.households}
        for account, loan in list(self.loans.items()):
            agent = agents.get(account)
            if agent is None or housing.owner_of(loan.dwelling_id) != account:
                del self.loans[account]           # household gone or title moved: book follows
                continue
            margin_shadow = max(0.0, float(getattr(agent, "margin_debt", 0.0)))
            loan.balance = min(loan.balance, max(0.0, led.debt(account) - margin_shadow))
            if loan.balance <= EPS:
                del self.loans[account]           # amortized away by the credit machinery
                continue
            collateral = econ._house_price * housing.dwellings[loan.dwelling_id].units
            if loan.balance > self.foreclosure_ltv * collateral and led.balance(account) < self.arrears_floor:
                self._foreclose(econ, loan, bridge, market)

    def _foreclose(self, econ: Any, loan: Mortgage, bridge: Any, market: Any) -> None:
        led = econ.ledger
        bank = bank_for(econ, loan.account)
        writeoff = min(loan.balance, led.debt(loan.account))
        if writeoff > EPS:
            led.write_off(loan.account, bank.id, writeoff)
            if bridge is not None:
                bridge.post_household_debt_writeoff(loan.account, writeoff)
                bridge._clamp_margin_debt_shadow(loan.account)
        econ.housing.transfer(loan.dwelling_id, bank.id)
        if market is not None:
            market.list_dwelling(econ, loan.dwelling_id, bank.id, forced=True)
        del self.loans[loan.account]
        self.foreclosures_total += 1
        econ._writeoffs = getattr(econ, "_writeoffs", 0.0) + writeoff
