"""Person-level economic claims for the demographic layer.

Phase 1 keeps the existing household ledger accounts as the payment surface, but
adds a person-level ownership layer beneath them.  The claim ledger is therefore
not a second money ledger; it is the decomposition of each household account into
personal ownership claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


CLAIM_TOL = 1e-7


@dataclass
class PersonBalanceSheet:
    person_id: int
    household_id: int
    cash_claim: float = 0.0
    debt_claim: float = 0.0
    equity_claims: dict[str, float] = field(default_factory=dict)
    bond_face_claim: float = 0.0
    bank_equity_claims: dict[str, float] = field(default_factory=dict)
    labor_income_tick: float = 0.0
    capital_income_tick: float = 0.0
    transfer_income_tick: float = 0.0
    tax_paid_tick: float = 0.0
    consumption_allocated_tick: float = 0.0
    income_ema: float = 0.0

    @property
    def gross_assets(self) -> float:
        return (
            self.cash_claim
            + self.bond_face_claim
            + sum(self.equity_claims.values())
            + sum(self.bank_equity_claims.values())
        )

    @property
    def net_worth(self) -> float:
        return self.gross_assets - self.debt_claim


@dataclass
class HouseholdEconomicProfile:
    household_id: int
    member_ids: list[int]
    ages: dict[int, int]
    labor_supply: float
    child_count: int
    adult_count: int
    elder_count: int
    need_units: float
    dependency_ratio: float
    adult_equivalent_baseline: float = 2.0


class PersonClaimLedger:
    """Single writer for person-level claims."""

    def __init__(self) -> None:
        self._sheets: dict[int, PersonBalanceSheet] = {}
        self.estate_suspense_net_worth: float = 0.0
        self.estate_suspense_by_household: dict[int, float] = {}

    def add_person(
        self,
        person_id: int,
        household_id: int,
        cash_claim: float = 0.0,
        debt_claim: float = 0.0,
    ) -> None:
        if person_id in self._sheets:
            raise ValueError(f"person {person_id!r} already has economic claims")
        self._sheets[person_id] = PersonBalanceSheet(
            person_id=person_id,
            household_id=household_id,
            cash_claim=float(cash_claim),
            debt_claim=float(debt_claim),
        )

    def has_person(self, person_id: int) -> bool:
        return person_id in self._sheets

    def balance_sheet(self, person_id: int) -> PersonBalanceSheet:
        return self._sheets[person_id]

    def members_of_household(self, household_id: int) -> list[int]:
        return [
            person_id
            for person_id, sheet in sorted(self._sheets.items())
            if sheet.household_id == household_id
        ]

    def set_household(self, person_id: int, household_id: int) -> None:
        self._sheets[person_id].household_id = household_id

    def net_worth(self, person_id: int) -> float:
        return self._sheets[person_id].net_worth

    def total_net_worth(self, *, include_estates: bool = False) -> float:
        total = sum(sheet.net_worth for sheet in self._sheets.values())
        if include_estates:
            total += self.estate_suspense_net_worth
        return total

    def register_estate_suspense(self, net_worth: float, household_id: int | None = None) -> None:
        self.estate_suspense_net_worth += float(net_worth)
        if household_id is not None:
            household_id = int(household_id)
            self.estate_suspense_by_household[household_id] = (
                self.estate_suspense_by_household.get(household_id, 0.0) + float(net_worth)
            )

    def clear_estate_suspense(self, net_worth: float, household_id: int | None = None) -> None:
        self.estate_suspense_net_worth -= float(net_worth)
        if abs(self.estate_suspense_net_worth) <= CLAIM_TOL:
            self.estate_suspense_net_worth = 0.0
        if household_id is not None:
            household_id = int(household_id)
            self.estate_suspense_by_household[household_id] = (
                self.estate_suspense_by_household.get(household_id, 0.0) - float(net_worth)
            )
            if abs(self.estate_suspense_by_household[household_id]) <= CLAIM_TOL:
                self.estate_suspense_by_household.pop(household_id, None)

    def credit_cash(self, person_id: int, amount: float, *, household_id: int | None = None) -> None:
        if person_id not in self._sheets:
            if household_id is None:
                raise KeyError(f"person {person_id!r} has no balance sheet")
            self.add_person(person_id, household_id=household_id)
        self._sheets[person_id].cash_claim += float(amount)

    def transfer_cash_claim(self, src_person_id: int, dst_person_id: int, amount: float) -> None:
        if amount < 0:
            raise ValueError("claim transfer amount must be non-negative")
        if amount == 0.0:
            return
        self._sheets[src_person_id].cash_claim -= float(amount)
        self._sheets[dst_person_id].cash_claim += float(amount)

    def clear_person_claims(self, person_id: int) -> None:
        sheet = self._sheets[person_id]
        sheet.cash_claim = 0.0
        sheet.debt_claim = 0.0
        sheet.equity_claims.clear()
        sheet.bond_face_claim = 0.0
        sheet.bank_equity_claims.clear()

    def reset_household_financial_claims(
        self,
        household_id: int,
        *,
        owner_ids: Iterable[int],
        cash: float,
        debt: float,
        holdings: dict[str, float],
    ) -> None:
        """Overwrite stock claims for one demographic household.

        This is the bridge-level synchronization primitive used when legacy
        household markets have already mutated their aggregate portfolios.  It
        deliberately preserves per-tick income/consumption fields, but resets the
        stock decomposition so person claims sum back to the household ledger and
        portfolio state.
        """
        member_ids = self.members_of_household(household_id)
        if not member_ids:
            return
        owners = [int(person_id) for person_id in owner_ids if int(person_id) in member_ids]
        if not owners:
            owners = member_ids
        for person_id in member_ids:
            sheet = self._sheets[person_id]
            sheet.cash_claim = 0.0
            sheet.debt_claim = 0.0
            sheet.equity_claims.clear()
            sheet.bond_face_claim = 0.0
            sheet.bank_equity_claims.clear()

        cash_share = float(cash) / len(owners)
        debt_share = float(debt) / len(owners)
        for person_id in owners:
            sheet = self._sheets[person_id]
            sheet.cash_claim = cash_share
            sheet.debt_claim = debt_share

        for asset_id, amount in holdings.items():
            share = float(amount) / len(owners)
            for person_id in owners:
                sheet = self._sheets[person_id]
                if asset_id == "__bond_face__":
                    sheet.bond_face_claim += share
                elif asset_id.startswith("__bank_equity__:"):
                    bank_id = asset_id.split(":", 1)[1]
                    sheet.bank_equity_claims[bank_id] = sheet.bank_equity_claims.get(bank_id, 0.0) + share
                else:
                    sheet.equity_claims[asset_id] = sheet.equity_claims.get(asset_id, 0.0) + share

    def post_household_cash_flow(
        self,
        household_id: int,
        *,
        amount: float,
        reason: str,
        person_ids: Iterable[int] | None = None,
    ) -> None:
        recipients = list(person_ids) if person_ids is not None else self.members_of_household(household_id)
        if not recipients or amount == 0.0:
            return
        share = float(amount) / len(recipients)
        for person_id in recipients:
            sheet = self._sheets[person_id]
            sheet.cash_claim += share
            if reason == "labor_income":
                sheet.labor_income_tick += share
                sheet.income_ema += 0.05 * (share - sheet.income_ema)
            elif reason == "capital_income":
                sheet.capital_income_tick += share
            elif reason == "transfer_income":
                sheet.transfer_income_tick += share

    def allocate_household_consumption(
        self,
        household_id: int,
        *,
        amount: float,
        person_ids: Iterable[int] | None = None,
    ) -> None:
        members = list(person_ids) if person_ids is not None else self.members_of_household(household_id)
        if not members or amount == 0.0:
            return
        share = float(amount) / len(members)
        for person_id in members:
            sheet = self._sheets[person_id]
            sheet.cash_claim -= share
            sheet.consumption_allocated_tick += share

    def allocate_person_consumption(self, person_id: int, amount: float) -> None:
        if amount == 0.0:
            return
        sheet = self._sheets[person_id]
        sheet.cash_claim -= float(amount)
        sheet.consumption_allocated_tick += float(amount)

    def allocate_household_debt_repayment(
        self,
        household_id: int,
        *,
        amount: float,
        person_ids: Iterable[int] | None = None,
    ) -> None:
        members = list(person_ids) if person_ids is not None else self.members_of_household(household_id)
        if not members or amount == 0.0:
            return
        share = float(amount) / len(members)
        for person_id in members:
            sheet = self._sheets[person_id]
            sheet.cash_claim -= share
            sheet.debt_claim = max(0.0, sheet.debt_claim - share)

    def assert_household_claim_identity(
        self,
        household_id: int,
        deposits: float,
        debt: float,
        holdings: dict[str, float],
    ) -> None:
        members = [self._sheets[pid] for pid in self.members_of_household(household_id)]
        cash = sum(sheet.cash_claim for sheet in members) + self.estate_suspense_by_household.get(household_id, 0.0)
        debt_claim = sum(sheet.debt_claim for sheet in members)
        if abs(cash - deposits) > CLAIM_TOL:
            raise AssertionError(
                f"cash claim mismatch for household {household_id}: claims={cash} ledger={deposits}"
            )
        if abs(debt_claim - debt) > CLAIM_TOL:
            raise AssertionError(
                f"debt claim mismatch for household {household_id}: claims={debt_claim} ledger={debt}"
            )
        actual_holdings: dict[str, float] = {}
        for sheet in members:
            if abs(sheet.bond_face_claim) > CLAIM_TOL:
                actual_holdings["__bond_face__"] = actual_holdings.get("__bond_face__", 0.0) + sheet.bond_face_claim
            for asset_id, amount in sheet.equity_claims.items():
                if abs(amount) > CLAIM_TOL:
                    actual_holdings[asset_id] = actual_holdings.get(asset_id, 0.0) + amount
            for bank_id, amount in sheet.bank_equity_claims.items():
                if abs(amount) > CLAIM_TOL:
                    asset_id = f"__bank_equity__:{bank_id}"
                    actual_holdings[asset_id] = actual_holdings.get(asset_id, 0.0) + amount

        for asset_id in set(holdings) | set(actual_holdings):
            expected = holdings.get(asset_id, 0.0)
            if asset_id == "__bond_face__":
                actual = actual_holdings.get(asset_id, 0.0)
            elif asset_id.startswith("__bank_equity__:"):
                actual = actual_holdings.get(asset_id, 0.0)
            else:
                actual = actual_holdings.get(asset_id, 0.0)
            if abs(actual - expected) > CLAIM_TOL:
                raise AssertionError(
                    f"holding claim mismatch for household {household_id}/{asset_id}: "
                    f"claims={actual} ledger={expected}"
                )


def _age_of(person: Any) -> int:
    return int(getattr(person, "age"))


def labor_supply_for_person(person: Any, current_date: object | None = None, min_age: int = 18, max_age: int = 64) -> float:
    _ = current_date
    if not getattr(person, "alive", True):
        return 0.0
    age = _age_of(person)
    return 1.0 if min_age <= age <= max_age else 0.0


def need_weight_for_person(person: Any) -> float:
    age = _age_of(person)
    if age < 18:
        return 0.65
    if age >= 65:
        return 0.9
    return 1.0


def build_household_economic_profiles(state: Any, claims: PersonClaimLedger) -> dict[int, HouseholdEconomicProfile]:
    del claims
    grouped: dict[int, list[Any]] = {}
    for person in getattr(state, "people"):
        if not getattr(person, "alive", True):
            continue
        household_id = getattr(person, "household_id", None)
        if household_id is None:
            continue
        grouped.setdefault(int(household_id), []).append(person)

    profiles: dict[int, HouseholdEconomicProfile] = {}
    for household_id, people in grouped.items():
        member_ids = [int(person.id) for person in people]
        ages = {int(person.id): _age_of(person) for person in people}
        labor_supply = sum(labor_supply_for_person(person, getattr(state, "current_date", None)) for person in people)
        child_count = sum(1 for person in people if _age_of(person) < 18)
        elder_count = sum(1 for person in people if _age_of(person) >= 65)
        adult_count = len(people) - child_count - elder_count
        dependents = child_count + elder_count
        dependency_ratio = dependents / max(adult_count, 1)
        profiles[household_id] = HouseholdEconomicProfile(
            household_id=household_id,
            member_ids=member_ids,
            ages=ages,
            labor_supply=labor_supply,
            child_count=child_count,
            adult_count=adult_count,
            elder_count=elder_count,
            need_units=sum(need_weight_for_person(person) for person in people),
            dependency_ratio=dependency_ratio,
        )
    return profiles
