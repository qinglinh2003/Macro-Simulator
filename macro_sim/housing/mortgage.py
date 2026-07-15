"""Mortgages over the existing household credit rails.

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
- Optional underwriting is a pure pre-flight decision made before any sale posting.
  It combines LTV, stressed DSTI and a bank-specific risk-weighted mortgage envelope;
  the optional unified-bank-RWA frontier makes that envelope common to mortgage,
  firm and consumer credit while retaining the historical gross-loan caps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from macro_sim.markets.matching import EPS
from macro_sim.systems.banking import (
    bank_economic_capital,
    bank_for,
    bank_rwa_capacity,
    loan_rate_for,
    record_bank_credit_loss,
    unified_bank_rwa_enabled,
)


@dataclass
class Mortgage:
    account: str
    dwelling_id: int
    balance: float          # secured-balance shadow, clamped by session maintenance
    bank_id: str = ""       # current creditor relationship; reconciled each session


@dataclass(frozen=True)
class MortgageDecision:
    """Side-effect-free underwriting result consumed by the housing market."""

    approved: bool
    reason: str
    amount: float
    bank_id: str = ""
    contract_rate: float = 0.0       # per tick, same unit as domestic debt service
    qualifying_income: float = 0.0   # per tick, committed lagged adaptive income
    stressed_payment: float = 0.0    # per tick
    available_capacity: float = 0.0  # principal headroom after mortgage RWA


@dataclass
class MortgageBook:
    ltv_cap: float = 0.8
    foreclosure_ltv: float = 1.1
    arrears_floor: float = 2.0
    underwriting_enabled: bool = False
    dsti_cap: float = 0.45
    stress_rate_addon: float = 0.02 / 365.0
    risk_weight: float = 0.35
    min_capital_ratio: float = 0.08
    loans: dict[str, Mortgage] = field(default_factory=dict)   # one per household (owner-occupier)
    originated_total: float = 0.0
    originated_tick: float = 0.0
    foreclosures_total: int = 0

    def balance_total(self) -> float:
        return sum(loan.balance for loan in self.loans.values())

    def bank_balance_total(self, bank_id: str) -> float:
        """Outstanding secured principal attributed to one creditor bank."""
        return sum(loan.balance for loan in self.loans.values() if loan.bank_id == bank_id)

    def apply_ordinary_principal_repayment(
        self,
        account: str,
        amount: float,
        ordinary_debt_before: float,
    ) -> float:
        """Allocate a generic household repayment across the mortgage shadow.

        Ledger household debt combines mortgages and unsecured consumer credit.
        On the normal repayment rail, reduce the secured shadow pro rata with its
        share of pre-payment ordinary debt.  Without this hook, amortization followed
        by new consumer borrowing could leave the mortgage shadow unchanged and give
        unsecured exposure the mortgage risk weight.

        Returns the principal allocated to the mortgage component.
        """
        loan = self.loans.get(account)
        principal = max(0.0, float(amount))
        ordinary = max(0.0, float(ordinary_debt_before))
        if loan is None or principal <= EPS or ordinary <= EPS:
            return 0.0
        secured_before = min(max(0.0, float(loan.balance)), ordinary)
        secured_repayment = min(
            secured_before,
            principal * secured_before / ordinary,
        )
        loan.balance = max(0.0, secured_before - secured_repayment)
        if loan.balance <= EPS:
            del self.loans[account]
        return secured_repayment

    def bank_capacity(self, econ: Any, bank: Any) -> float:
        """Mortgage principal headroom under the active RWA capital envelope.

        ``capital / min_capital_ratio`` is the maximum mortgage RWA supported by
        current economic capital.  In legacy mode only existing mortgages consume
        it.  Unified mode deducts firm/consumer exposure at 100% and existing secured
        mortgages at ``risk_weight`` from one bank-wide envelope.
        """
        if bank is None or not bank.alive:
            return 0.0
        if unified_bank_rwa_enabled(econ):
            return bank_rwa_capacity(
                econ,
                bank,
                new_loan_risk_weight=self.risk_weight,
                min_capital_ratio=self.min_capital_ratio,
                # Underwriting occurs after borrower principal service.  The
                # intra-credit cache intentionally serves sequential grants earlier
                # in the tick and can still contain repaid principal; the live
                # ledger plus mortgage shadow is authoritative here.
                use_cache=False,
            )
        capital = max(0.0, bank_economic_capital(econ, bank))
        rwa_room = (
            capital / self.min_capital_ratio
            - self.risk_weight * self.bank_balance_total(bank.id)
        )
        return max(0.0, rwa_room / self.risk_weight)

    def underwrite(
        self,
        econ: Any,
        buyer: Any,
        dwelling_id: int,
        price: float,
        amount: float,
    ) -> MortgageDecision:
        """Return a pure approval decision; never post cash, debt, or title.

        Income and debt service are both per-tick quantities.  The live loan rate is
        used once and the stress add-on is already configured in per-tick units, so
        there is no annual-rate rescaling in this path.
        """
        amount = max(0.0, float(amount))
        price = max(0.0, float(price))

        def reject(reason: str, **evidence: float | str) -> MortgageDecision:
            return MortgageDecision(False, reason, amount, **evidence)

        if amount <= EPS or price <= EPS:
            return reject("invalid_amount")
        if buyer.id in self.loans:
            return reject("existing_mortgage")
        if amount > self.ltv_cap * price + EPS:
            return reject("ltv")

        bank = bank_for(econ, buyer.id)
        if bank is None or not bank.alive:
            return reject("bank_unavailable")
        bank_id = bank.id
        contract_rate = max(0.0, float(loan_rate_for(econ, buyer.id)))

        # ``income_realized`` is only a partial within-tick flow here: wages and
        # family transfers may have posted, while benefits, dividends and other
        # settlement income have not.  Underwrite against the committed adaptive
        # expectation, which was updated from the complete prior-tick income before
        # this tick's journal reset.  This avoids phase-order-dependent approvals and
        # prevents a current one-off windfall from being capitalized into the loan.
        expected_income = max(0.0, float(getattr(buyer, "y_expected", 0.0)))
        qualifying_income = expected_income
        if qualifying_income <= EPS:
            return reject(
                "income",
                bank_id=bank_id,
                contract_rate=contract_rate,
                qualifying_income=qualifying_income,
            )

        existing_debt = max(0.0, float(econ.ledger.debt(buyer.id)))
        margin_debt = min(existing_debt, max(0.0, float(getattr(buyer, "margin_debt", 0.0))))
        amortizing_debt = existing_debt - margin_debt + amount
        interest_bearing_debt = existing_debt + amount
        stressed_rate = contract_rate + self.stress_rate_addon
        stressed_payment = (
            float(econ.cfg.credit.hh_amort) * amortizing_debt
            + stressed_rate * interest_bearing_debt
        )
        if stressed_payment > self.dsti_cap * qualifying_income + EPS:
            return reject(
                "dsti",
                bank_id=bank_id,
                contract_rate=contract_rate,
                qualifying_income=qualifying_income,
                stressed_payment=stressed_payment,
            )

        capacity = self.bank_capacity(econ, bank)
        if amount > capacity + EPS:
            return reject(
                "bank_capacity",
                bank_id=bank_id,
                contract_rate=contract_rate,
                qualifying_income=qualifying_income,
                stressed_payment=stressed_payment,
                available_capacity=capacity,
            )
        return MortgageDecision(
            True,
            "approved",
            amount,
            bank_id=bank_id,
            contract_rate=contract_rate,
            qualifying_income=qualifying_income,
            stressed_payment=stressed_payment,
            available_capacity=capacity,
        )

    def originate(
        self,
        econ: Any,
        buyer: Any,
        dwelling_id: int,
        amount: float,
        *,
        price: float | None = None,
        decision: MortgageDecision | None = None,
    ) -> bool:
        """Create a mortgage, returning ``False`` without mutation when rejected."""
        bank = bank_for(econ, buyer.id)
        if self.underwriting_enabled:
            if price is None:
                return False
            # Re-check at the mutation boundary.  Earlier approved buyers in the same
            # session have already entered ``loans``, so portfolio capacity cannot be
            # overbooked by a batch of stale previews.
            fresh = self.underwrite(econ, buyer, dwelling_id, price, amount)
            if not fresh.approved:
                return False
            if decision is not None and (
                not decision.approved
                or decision.bank_id != fresh.bank_id
                or abs(decision.amount - fresh.amount) > EPS
            ):
                return False
            decision = fresh
            bank_id = decision.bank_id
        else:
            bank_id = bank.id if bank is not None else ""

        bridge = getattr(econ, "demographic_bridge", None)
        econ.ledger.create_loan(buyer.id, amount)
        if bridge is not None:
            bridge.post_household_debt_creation(buyer.id, amount)
        self.loans[buyer.id] = Mortgage(
            account=buyer.id,
            dwelling_id=dwelling_id,
            balance=amount,
            bank_id=bank_id,
        )
        # The unified credit phase keeps an O(1) gross-loan cache.  Housing settles
        # later in the same tick, so mutate that cache at the same boundary as the
        # ledger and mortgage shadow; a second buyer cannot reuse stale headroom.
        if unified_bank_rwa_enabled(econ) and isinstance(getattr(econ, "_loan_book", None), dict):
            econ._loan_book[bank_id] = econ._loan_book.get(bank_id, 0.0) + amount
        self.originated_total += amount
        self.originated_tick += amount
        return True

    def maintain(self, econ: Any) -> None:
        """Per-session reconciliation: derive each secured balance from the ledger truth,
        close paid-off or collateral-less entries, then run the foreclosure test."""
        # v15.5: the LTV cap is a LIVE macroprudential lever (Policy), synced per session
        self.ltv_cap = float(getattr(econ.policy, "mortgage_ltv_cap", self.ltv_cap))
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
            creditor = bank_for(econ, account)
            if creditor is not None:
                # `_bank_of` is the authoritative creditor relationship used by the
                # shared interest and failure rails; keep the mortgage portfolio
                # attribution aligned after bank migration/resolution.
                loan.bank_id = creditor.id
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
        bank = next((candidate for candidate in econ.banks if candidate.id == loan.bank_id), None)
        if bank is None:
            bank = bank_for(econ, loan.account)
        if bank is None:
            raise AssertionError("mortgage foreclosure requires a creditor bank")
        principal_before = max(0.0, float(led.debt(loan.account)))
        writeoff = min(loan.balance, principal_before)
        if writeoff > EPS:
            led.write_off(loan.account, bank.id, writeoff)
            record_bank_credit_loss(econ, bank.id, writeoff)
            from macro_sim.systems.credit import (
                extinguish_household_interest_arrears_for_writeoff,
            )
            extinguish_household_interest_arrears_for_writeoff(
                econ,
                loan.account,
                principal_before=principal_before,
                principal_reduction=writeoff,
            )
            if bridge is not None:
                bridge.post_household_debt_writeoff(loan.account, writeoff)
                bridge._clamp_margin_debt_shadow(loan.account)
        econ.housing.transfer(loan.dwelling_id, bank.id)
        if market is not None:
            market.list_dwelling(econ, loan.dwelling_id, bank.id, forced=True)
        self.loans.pop(loan.account, None)
        self.foreclosures_total += 1
        econ._writeoffs = getattr(econ, "_writeoffs", 0.0) + writeoff
