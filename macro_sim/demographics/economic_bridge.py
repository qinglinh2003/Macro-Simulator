"""Bridge between demographic people/households and the economic ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import numpy as np

from macro_sim.demographics.economic_state import (
    HouseholdEconomicProfile,
    PersonClaimLedger,
    build_household_economic_profiles,
    labor_supply_for_person,
    need_weight_for_person,
)
from macro_sim.demographics.estate import EstateRegistry
from macro_sim.demographics.inheritance import select_default_heirs, settle_estate
from macro_sim.demographics.kernel import MicroDemographicKernel, count_alive_by_age, create_genesis_population
from macro_sim.demographics.lifecycle import household_lifecycle_consumption_budget
from macro_sim.demographics.marriage_economics import MarriageContract, dissolve_marriage, record_marriage_contract


AGGREGATE_EQUITY_CLAIM_ID = "__aggregate_equity__"
BOND_FACE_CLAIM_ID = "__bond_face__"
BANK_EQUITY_CLAIM_PREFIX = "__bank_equity__:"


@dataclass
class ChildCostAllocation:
    child_id: int
    parent_charges: dict[int, float] = field(default_factory=dict)
    public_charge: float = 0.0


@dataclass
class DemographicEconomicBridge:
    claims: PersonClaimLedger
    household_to_account: dict[int, str]
    estates: EstateRegistry = field(default_factory=EstateRegistry)
    econ: Any | None = None
    person_creditor_bank: dict[int, str] = field(default_factory=dict)
    marriage_contracts: dict[frozenset[int], MarriageContract] = field(default_factory=dict)
    death_writeoff_flow: float = 0.0
    orphan_support_spending: float = 0.0
    _bank_capital_adjustment: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.account_to_household = {account: household for household, account in self.household_to_account.items()}

    def account_for_household_id(self, household_id: int) -> str:
        return self.household_to_account[int(household_id)]

    def household_id_for_account(self, account_id: str) -> int:
        return self.account_to_household[account_id]

    def assert_all_claim_identities(self, econ: Any | None = None) -> None:
        econ = econ or self.econ
        if econ is None:
            raise RuntimeError("economic ledger is required for claim identity checks")
        for household_id, account_id in self.household_to_account.items():
            self.claims.assert_household_claim_identity(
                household_id,
                deposits=econ.ledger.balance(account_id),
                debt=econ.ledger.debt(account_id),
                holdings=self._household_asset_claim_targets(econ, account_id),
            )

    def reconcile_financial_claims_from_economy(self, econ: Any | None = None) -> None:
        """Synchronize person stock claims to aggregate household accounts.

        Legacy market modules still mutate household-level portfolios directly.
        This bridge-level reconciliation keeps the new person ownership layer
        accounting-safe until those market modules are taught to post
        person-level trade events themselves.
        """
        econ = econ or self.econ
        if econ is None:
            raise RuntimeError("economic ledger is required for claim reconciliation")
        for household_id, account_id in self.household_to_account.items():
            estate_suspense = self.claims.estate_suspense_by_household.get(household_id, 0.0)
            self.claims.reset_household_financial_claims(
                household_id,
                owner_ids=self._claim_owner_ids(household_id),
                cash=econ.ledger.balance(account_id) - estate_suspense,
                debt=econ.ledger.debt(account_id),
                holdings=self._household_asset_claim_targets(econ, account_id),
            )

    def household_labor_supply(self, account_id: str) -> float:
        household_id = self.household_id_for_account(account_id)
        people = self._people_by_household(household_id)
        if people is None:
            return 0.0
        return sum(labor_supply_for_person(person) for person in people)

    def household_has_living_members(self, account_id: str) -> bool:
        household_id = self.household_id_for_account(account_id)
        people = self._people_by_household(household_id)
        return bool(people)

    def working_age_person_ids(self, account_id: str) -> list[int]:
        household_id = self.household_id_for_account(account_id)
        people = self._people_by_household(household_id) or []
        return [
            int(person.id)
            for person in people
            if labor_supply_for_person(person) > 0.0 and self.claims.has_person(int(person.id))
        ]

    def post_labor_income(
        self,
        account_id: str,
        amount: float,
        worker_person_ids: list[int] | None = None,
    ) -> None:
        household_id = self.household_id_for_account(account_id)
        recipients = worker_person_ids if worker_person_ids is not None else self.working_age_person_ids(account_id)
        self.claims.post_household_cash_flow(
            household_id,
            amount=amount,
            reason="labor_income",
            person_ids=recipients,
        )

    def post_transfer_income(self, account_id: str, amount: float, reason: str = "transfer_income") -> None:
        household_id = self.household_id_for_account(account_id)
        self.claims.post_household_cash_flow(household_id, amount=amount, reason="transfer_income")

    def post_capital_income(self, account_id: str, amount: float) -> None:
        household_id = self.household_id_for_account(account_id)
        self.claims.post_household_cash_flow(household_id, amount=amount, reason="capital_income")

    def post_household_cash_delta(self, account_id: str, amount: float, *, reason: str = "cash_flow") -> None:
        household_id = self.household_id_for_account(account_id)
        self._post_household_cash_delta(household_id, amount, reason=reason)

    def post_household_tax_payment(self, account_id: str, amount: float) -> None:
        household_id = self.household_id_for_account(account_id)
        self._post_household_cash_delta(household_id, -float(amount), reason="tax_payment")

    def post_household_debt_creation(self, account_id: str, amount: float) -> None:
        household_id = self.household_id_for_account(account_id)
        self._post_household_cash_delta(household_id, float(amount), reason="debt_creation")
        self._post_household_debt_delta(household_id, float(amount))

    def post_household_debt_repayment(self, account_id: str, amount: float) -> None:
        household_id = self.household_id_for_account(account_id)
        self._post_household_cash_delta(household_id, -float(amount), reason="debt_repayment")
        self._post_household_debt_delta(household_id, -float(amount))

    def post_household_debt_writeoff(self, account_id: str, amount: float) -> None:
        household_id = self.household_id_for_account(account_id)
        self._post_household_debt_delta(household_id, -float(amount))

    def post_household_equity_trade(
        self,
        account_id: str,
        asset_id: str,
        *,
        cash_delta: float,
        share_delta: float,
    ) -> None:
        household_id = self.household_id_for_account(account_id)
        self._post_household_cash_delta(household_id, cash_delta, reason="asset_trade")
        self._post_household_equity_delta(household_id, str(asset_id), share_delta)

    def post_household_bond_trade(self, account_id: str, *, cash_delta: float, face_delta: float) -> None:
        household_id = self.household_id_for_account(account_id)
        self._post_household_cash_delta(household_id, cash_delta, reason="bond_trade")
        self._post_household_equity_delta(household_id, BOND_FACE_CLAIM_ID, face_delta)

    def post_household_bank_equity_trade(
        self,
        account_id: str,
        bank_id: str,
        *,
        cash_delta: float,
        share_delta: float,
    ) -> None:
        household_id = self.household_id_for_account(account_id)
        self._post_household_cash_delta(household_id, cash_delta, reason="bank_equity_trade")
        self._post_household_equity_delta(
            household_id,
            f"{BANK_EQUITY_CLAIM_PREFIX}{bank_id}",
            share_delta,
        )

    def claim_cash_sum(self, account_id: str) -> float:
        household_id = self.household_id_for_account(account_id)
        return sum(self.claims.balance_sheet(person_id).cash_claim for person_id in self.claims.members_of_household(household_id))

    def consumption_allocated_sum(self, account_id: str) -> float:
        household_id = self.household_id_for_account(account_id)
        return sum(
            self.claims.balance_sheet(person_id).consumption_allocated_tick
            for person_id in self.claims.members_of_household(household_id)
        )

    def household_profile(self, account_id: str):
        household_id = self.household_id_for_account(account_id)
        state = getattr(self, "demographic_state", None)
        if state is None and self.econ is not None:
            state = getattr(self.econ, "demographic_state", None)
        if state is None:
            raise RuntimeError("demographic state is required for household profiles")
        profiles = build_household_economic_profiles(state, self.claims)
        if household_id in profiles:
            return profiles[household_id]
        return HouseholdEconomicProfile(
            household_id=household_id,
            member_ids=[],
            ages={},
            labor_supply=0.0,
            child_count=0,
            adult_count=0,
            elder_count=0,
            need_units=0.0,
            dependency_ratio=0.0,
        )

    def household_lifecycle_consumption_budget(
        self,
        account_id: str,
        rates: Any,
        *,
        alpha_income: float,
        alpha_wealth_draw: float,
        ticks_per_year: int = 365,
    ) -> float:
        return household_lifecycle_consumption_budget(
            self.household_profile(account_id),
            self.claims,
            rates,
            alpha_income=alpha_income,
            alpha_wealth_draw=alpha_wealth_draw,
            ticks_per_year=ticks_per_year,
        )

    def create_household_for_person(self, person_id: int) -> str:
        if self.econ is None or getattr(self.econ, "ledger", None) is None:
            raise RuntimeError("economic ledger is required to create a household account")
        person = self._person_by_id(int(person_id))
        if person is None or getattr(person, "household_id", None) is None:
            raise RuntimeError(f"person {person_id!r} has no demographic household")
        new_household_id = int(person.household_id)
        if new_household_id in self.household_to_account:
            account_id = self.household_to_account[new_household_id]
            self._sync_person_to_household(int(person_id), new_household_id)
            return account_id

        account_id = self._ensure_household_account(new_household_id)
        self._sync_person_to_household(int(person_id), new_household_id)
        return account_id

    def household_control_income(self, account_id: str) -> float:
        household_id = self.household_id_for_account(account_id)
        return sum(
            self.claims.balance_sheet(person_id).income_ema
            for person_id in self.claims.members_of_household(household_id)
        )

    def household_control_wealth(self, account_id: str) -> float:
        household_id = self.household_id_for_account(account_id)
        return sum(
            self.claims.balance_sheet(person_id).net_worth
            for person_id in self.claims.members_of_household(household_id)
        )

    def post_household_consumption(
        self,
        account_id: str,
        amount: float | None = None,
        *,
        spent: float | None = None,
        fixed_share: float = 0.30,
    ) -> None:
        if spent is None:
            if amount is None:
                raise TypeError("post_household_consumption requires amount or spent")
            spent = amount
        household_id = self.household_id_for_account(account_id)
        total = float(spent)
        if total <= 0.0:
            return
        people = self._people_by_household(household_id) or []
        adult_ids = [
            int(person.id)
            for person in people
            if getattr(person, "alive", True)
            and int(getattr(person, "age", 0)) >= 18
            and self.claims.has_person(int(person.id))
        ]
        if not adult_ids:
            adult_ids = self.claims.members_of_household(household_id)
        fixed = total * max(0.0, min(1.0, fixed_share))
        variable = total - fixed
        self.claims.allocate_household_consumption(household_id, amount=fixed, person_ids=adult_ids)

        weighted_charges: dict[int, float] = {person_id: 0.0 for person_id in adult_ids}
        for person in people:
            person_id = int(person.id)
            weight = need_weight_for_person(person)
            charge_to = person_id if person_id in adult_ids else None
            if charge_to is None and adult_ids:
                per_adult = weight / len(adult_ids)
                for adult_id in adult_ids:
                    weighted_charges[adult_id] = weighted_charges.get(adult_id, 0.0) + per_adult
            elif charge_to is not None:
                weighted_charges[charge_to] = weighted_charges.get(charge_to, 0.0) + weight
        total_weight = sum(weighted_charges.values())
        if total_weight <= 0.0:
            self.claims.allocate_household_consumption(household_id, amount=variable, person_ids=adult_ids)
            return
        for person_id, weight in weighted_charges.items():
            self.claims.allocate_person_consumption(person_id, variable * weight / total_weight)

    def allocate_child_cost(self, child_id: int, amount: float) -> ChildCostAllocation:
        child = self._person_by_id(int(child_id))
        if child is None:
            raise KeyError(f"unknown child {child_id!r}")
        living_parent_ids: list[int] = []
        for parent_id in (getattr(child, "mother_id", None), getattr(child, "father_id", None)):
            if parent_id is None:
                continue
            parent = self._person_by_id(int(parent_id))
            if parent is not None and getattr(parent, "alive", True) and self.claims.has_person(int(parent_id)):
                living_parent_ids.append(int(parent_id))
        total = float(amount)
        if living_parent_ids:
            share = total / len(living_parent_ids)
            charges = {parent_id: share for parent_id in living_parent_ids}
            for parent_id in living_parent_ids:
                self.claims.allocate_person_consumption(parent_id, share)
            return ChildCostAllocation(child_id=int(child_id), parent_charges=charges, public_charge=0.0)

        self.orphan_support_spending += total
        if self.econ is not None:
            self.econ._orphan_support_spending = getattr(self.econ, "_orphan_support_spending", 0.0) + total
        return ChildCostAllocation(child_id=int(child_id), parent_charges={}, public_charge=total)

    def on_birth(self, event: Any, newborn: Any) -> None:
        household_id = int(newborn.household_id)
        if not self.claims.has_person(int(newborn.id)):
            self.claims.add_person(int(newborn.id), household_id=household_id)

    def on_marriage(self, event: Any) -> None:
        self._sync_demographic_household(int(event.household_id))
        key = self._marriage_key(int(event.spouse_a_id), int(event.spouse_b_id))
        if key not in self.marriage_contracts:
            self.marriage_contracts[key] = record_marriage_contract(event, self.claims)

    def on_divorce(self, event: Any) -> None:
        key = self._marriage_key(int(event.spouse_a_id), int(event.spouse_b_id))
        contract = self.marriage_contracts.pop(key, None)
        if contract is not None:
            dissolve_marriage(contract, self.claims, reason="divorce")
        self._sync_demographic_household(int(event.household_a_id))
        self._sync_demographic_household(int(event.household_b_id))

    def assign_person_creditor_bank(self, person_id: int, bank_id: str) -> None:
        self.person_creditor_bank[int(person_id)] = bank_id

    def bank_capital(self, bank_id: str) -> float:
        if self.econ is not None and getattr(self.econ, "ledger", None) is not None:
            return self.econ.ledger.balance(bank_id)
        return self._bank_capital_adjustment.get(bank_id, 0.0)

    def write_off_deceased_debt(self, person_id: int, unpaid_amount: float, creditor_bank_id: str) -> None:
        amount = float(unpaid_amount)
        if amount <= 0.0:
            return
        if self.econ is not None and getattr(self.econ, "ledger", None) is not None:
            account_id = self.account_for_household_id(self.claims.balance_sheet(person_id).household_id)
            self.econ.ledger.write_off(account_id, creditor_bank_id, amount)
        else:
            self._bank_capital_adjustment[creditor_bank_id] = (
                self._bank_capital_adjustment.get(creditor_bank_id, 0.0) - amount
            )
        self.death_writeoff_flow += amount

    def on_death(self, event: Any, dead_person: Any) -> None:
        person_id = int(dead_person.id)
        if not self.claims.has_person(person_id):
            self.claims.add_person(person_id, household_id=int(dead_person.household_id or 0))
        surviving_spouse_id = self._dissolve_marriage_for_death(person_id)
        sheet = self.claims.balance_sheet(person_id)
        assets = max(0.0, sheet.gross_assets)
        debt = max(0.0, sheet.debt_claim)
        tick = int(getattr(event, "tick", 0))

        if assets >= debt:
            if self._settle_deceased_claim_package_if_possible(
                dead_person,
                surviving_spouse_id=surviving_spouse_id,
                tick=tick,
            ):
                return
            package = self._claim_package(person_id)
            if self._retained_estate_required(package):
                estate_net_worth = self._package_net_worth(package)
                self.estates.create_suspense_estate(
                    person_id,
                    estate_net_worth,
                    tick,
                    household_id=sheet.household_id,
                )
                return
            estate_value = assets - debt
            household_id = sheet.household_id
            self.claims.clear_person_claims(person_id)
            estate = self.estates.create_suspense_estate(person_id, estate_value, tick, household_id=household_id)
            self.claims.register_estate_suspense(estate.net_worth, household_id=household_id)
            return

        unpaid = debt - assets
        bank_id = self._creditor_bank_for_person(person_id, sheet.household_id)
        if bank_id is None:
            raise RuntimeError(f"missing creditor bank for insolvent death of person {person_id}")
        unpaid = self._repay_deceased_debt_with_cash(person_id, max_unpaid=unpaid)
        self.write_off_deceased_debt(person_id, unpaid, bank_id)
        self.claims.clear_person_claims(person_id)
        self.estates.create_suspense_estate(person_id, 0.0, tick, household_id=sheet.household_id)

    def _creditor_bank_for_person(self, person_id: int, household_id: int) -> str | None:
        bank_id = self.person_creditor_bank.get(int(person_id))
        if bank_id is not None:
            return bank_id
        if self.econ is None:
            return None
        account_id = self.household_to_account.get(int(household_id))
        if account_id is None:
            return None
        bank = None
        bank_of = getattr(self.econ, "_bank_of", None)
        if isinstance(bank_of, dict):
            bank = bank_of.get(account_id)
        if bank is None and getattr(self.econ, "banks", None):
            try:
                from macro_sim.systems.banking import bank_for

                bank = bank_for(self.econ, account_id)
            except (AttributeError, KeyError):
                bank = None
        bank_id = getattr(bank, "id", None)
        if bank_id is not None:
            self.person_creditor_bank[int(person_id)] = bank_id
        return bank_id

    def _repay_deceased_debt_with_cash(self, person_id: int, *, max_unpaid: float) -> float:
        sheet = self.claims.balance_sheet(person_id)
        if self.econ is None or getattr(self.econ, "ledger", None) is None:
            return max(0.0, float(max_unpaid))
        account_id = self.account_for_household_id(sheet.household_id)
        debt = max(0.0, float(sheet.debt_claim))
        cash = max(0.0, float(sheet.cash_claim))
        ledger_cash = max(0.0, float(self.econ.ledger.balance(account_id)))
        protected_cash = self._other_positive_cash_claims(person_id, sheet.household_id)
        available_cash = max(0.0, ledger_cash - protected_cash)
        pay = min(cash, debt, available_cash)
        if pay > 0.0:
            self.econ.ledger.repay(account_id, pay)
            sheet.cash_claim -= pay
            sheet.debt_claim = max(0.0, sheet.debt_claim - pay)
        return max(0.0, float(sheet.debt_claim))

    def _other_positive_cash_claims(self, person_id: int, household_id: int) -> float:
        total = 0.0
        for other_id in self.claims.members_of_household(int(household_id)):
            if int(other_id) == int(person_id):
                continue
            total += max(0.0, float(self.claims.balance_sheet(other_id).cash_claim))
        total += max(0.0, float(self.claims.estate_suspense_by_household.get(int(household_id), 0.0)))
        return total

    def _people_by_household(self, household_id: int) -> list[Any] | None:
        state = getattr(self, "demographic_state", None)
        if state is None:
            state = getattr(self.econ, "demographic_state", None) if self.econ is not None else None
        if state is None:
            return None
        return [
            person
            for person in getattr(state, "people", [])
            if getattr(person, "alive", True) and getattr(person, "household_id", None) == household_id
        ]

    def _person_by_id(self, person_id: int) -> Any | None:
        state = getattr(self, "demographic_state", None)
        if state is None:
            state = getattr(self.econ, "demographic_state", None) if self.econ is not None else None
        if state is None:
            return None
        for person in getattr(state, "people", []):
            if int(person.id) == person_id:
                return person
        return None

    def _people_by_id(self) -> dict[int, Any]:
        state = getattr(self, "demographic_state", None)
        if state is None:
            state = getattr(self.econ, "demographic_state", None) if self.econ is not None else None
        if state is None:
            return {}
        return {int(person.id): person for person in getattr(state, "people", [])}

    def _claim_owner_ids(self, household_id: int) -> list[int]:
        people = self._people_by_household(household_id) or []
        adults = [
            int(person.id)
            for person in people
            if int(getattr(person, "age", 0)) >= 18 and self.claims.has_person(int(person.id))
        ]
        if adults:
            return adults
        return self.claims.members_of_household(household_id)

    def _claim_posting_ids(self, household_id: int) -> list[int]:
        owners = [person_id for person_id in self._claim_owner_ids(household_id) if self.claims.has_person(person_id)]
        if owners:
            return owners
        return self.claims.members_of_household(household_id)

    def _post_household_cash_delta(self, household_id: int, amount: float, *, reason: str) -> None:
        amount = float(amount)
        if amount == 0.0:
            return
        person_ids = self._claim_posting_ids(household_id)
        if not person_ids:
            return
        share = amount / len(person_ids)
        for person_id in person_ids:
            sheet = self.claims.balance_sheet(person_id)
            sheet.cash_claim += share
            if reason == "capital_income" and share > 0.0:
                sheet.capital_income_tick += share
            elif reason == "transfer_income" and share > 0.0:
                sheet.transfer_income_tick += share
            elif reason == "tax_payment" and share < 0.0:
                sheet.tax_paid_tick += -share

    def _post_household_debt_delta(self, household_id: int, amount: float) -> None:
        amount = float(amount)
        if amount == 0.0:
            return
        if amount > 0.0:
            person_ids = self._claim_posting_ids(household_id)
            if not person_ids:
                return
            share = amount / len(person_ids)
            for person_id in person_ids:
                self.claims.balance_sheet(person_id).debt_claim += share
            return

        reduction = -amount
        member_ids = self.claims.members_of_household(household_id)
        if not member_ids:
            return
        debt_total = sum(max(0.0, self.claims.balance_sheet(person_id).debt_claim) for person_id in member_ids)
        if debt_total <= 0.0:
            return
        target = min(reduction, debt_total)
        applied = 0.0
        debtors = [person_id for person_id in member_ids if self.claims.balance_sheet(person_id).debt_claim > 0.0]
        for person_id in debtors[:-1]:
            sheet = self.claims.balance_sheet(person_id)
            cut = target * sheet.debt_claim / debt_total
            sheet.debt_claim = max(0.0, sheet.debt_claim - cut)
            applied += cut
        sheet = self.claims.balance_sheet(debtors[-1])
        sheet.debt_claim = max(0.0, sheet.debt_claim - (target - applied))

    def _post_household_equity_delta(self, household_id: int, asset_id: str, amount: float) -> None:
        amount = float(amount)
        if amount == 0.0:
            return
        person_ids = self._claim_posting_ids(household_id)
        if not person_ids:
            return
        share = amount / len(person_ids)
        for person_id in person_ids:
            sheet = self.claims.balance_sheet(person_id)
            if asset_id == BOND_FACE_CLAIM_ID:
                sheet.bond_face_claim += share
            elif asset_id.startswith(BANK_EQUITY_CLAIM_PREFIX):
                bank_id = asset_id.split(":", 1)[1]
                sheet.bank_equity_claims[bank_id] = sheet.bank_equity_claims.get(bank_id, 0.0) + share
            else:
                sheet.equity_claims[asset_id] = sheet.equity_claims.get(asset_id, 0.0) + share

    def _household_agent(self, account_id: str) -> Any | None:
        if self.econ is None:
            return None
        for household in getattr(self.econ, "households", []):
            if getattr(household, "id", None) == account_id:
                return household
        return None

    def _household_asset_claim_targets(self, econ: Any, account_id: str) -> dict[str, float]:
        targets: dict[str, float] = {}
        household = self._household_agent(account_id)
        if household is not None:
            if getattr(household, "shares", 0.0):
                targets[AGGREGATE_EQUITY_CLAIM_ID] = float(getattr(household, "shares", 0.0))
            for asset_id, shares in (getattr(household, "holdings", {}) or {}).items():
                if abs(float(shares)) > 0.0:
                    targets[str(asset_id)] = float(shares)
        bond_face = sum(
            float(lot.get("face", 0.0))
            for lot in (getattr(econ, "_bonds", []) or [])
            if lot.get("holder") == account_id
        )
        if abs(bond_face) > 0.0:
            targets[BOND_FACE_CLAIM_ID] = bond_face
        for bank in getattr(econ, "banks", []) or []:
            shares = float(((getattr(bank, "owners", None) or {}).get(account_id, 0.0)))
            if abs(shares) > 0.0:
                targets[f"{BANK_EQUITY_CLAIM_PREFIX}{bank.id}"] = shares
        return targets

    def _ensure_household_account(self, household_id: int) -> str:
        household_id = int(household_id)
        if household_id in self.household_to_account:
            return self.household_to_account[household_id]
        if self.econ is None or getattr(self.econ, "ledger", None) is None:
            raise RuntimeError("economic ledger is required to create a household account")
        idx = len(getattr(self.econ, "households", []))
        account_id = f"H{idx}"
        while self.econ.ledger.has_account(account_id):
            idx += 1
            account_id = f"H{idx}"
        self.econ.ledger.add_account(account_id)
        self.econ.households.append(self._new_household_agent(account_id, idx))
        self.household_to_account[household_id] = account_id
        self.account_to_household[account_id] = household_id
        return account_id

    def _new_household_agent(self, account_id: str, idx: int) -> Any:
        household_cls = type(self.econ.households[0]) if getattr(self.econ, "households", None) else SimpleNamespace
        if hasattr(household_cls, "create") and getattr(self.econ, "cfg", None) is not None:
            return household_cls.create(idx, self.econ.cfg)
        try:
            return household_cls(account_id)
        except TypeError:
            return SimpleNamespace(id=account_id)

    def _sync_demographic_household(self, household_id: int) -> None:
        self._ensure_household_account(household_id)
        state = getattr(self, "demographic_state", None)
        if state is None:
            state = getattr(self.econ, "demographic_state", None) if self.econ is not None else None
        if state is None:
            return
        for person in getattr(state, "people", []):
            if getattr(person, "alive", True) and getattr(person, "household_id", None) == household_id:
                self._sync_person_to_household(int(person.id), household_id)

    def _sync_person_to_household(self, person_id: int, household_id: int) -> None:
        if not self.claims.has_person(person_id):
            self.claims.add_person(person_id, household_id=household_id)
            return
        sheet = self.claims.balance_sheet(person_id)
        old_household_id = sheet.household_id
        if old_household_id == household_id:
            return
        old_account = self.household_to_account.get(old_household_id)
        new_account = self._ensure_household_account(household_id)
        if old_account is not None and self.econ is not None:
            self._normalize_household_cash_claims_to_deposits(old_household_id, old_account)
            self._move_person_aggregate_claims(person_id, old_account, new_account)
        self.claims.set_household(person_id, household_id)

    def _normalize_household_cash_claims_to_deposits(self, household_id: int, account_id: str) -> None:
        if self.econ is None or getattr(self.econ, "ledger", None) is None:
            return
        member_ids = self.claims.members_of_household(household_id)
        if not member_ids:
            return
        deposits = max(0.0, float(self.econ.ledger.balance(account_id)))
        positives = {
            person_id: max(0.0, float(self.claims.balance_sheet(person_id).cash_claim))
            for person_id in member_ids
        }
        positive_total = sum(positives.values())
        allocated = 0.0
        if positive_total > 0.0:
            for person_id in member_ids[:-1]:
                share = deposits * positives[person_id] / positive_total
                self.claims.balance_sheet(person_id).cash_claim = share
                allocated += share
            self.claims.balance_sheet(member_ids[-1]).cash_claim = deposits - allocated
            return
        share = deposits / len(member_ids)
        for person_id in member_ids[:-1]:
            self.claims.balance_sheet(person_id).cash_claim = share
            allocated += share
        self.claims.balance_sheet(member_ids[-1]).cash_claim = deposits - allocated

    def _move_person_aggregate_claims(self, person_id: int, old_account: str, new_account: str) -> None:
        if old_account == new_account or self.econ is None:
            return
        sheet = self.claims.balance_sheet(person_id)
        cash = float(sheet.cash_claim)
        if cash > 0.0:
            self.econ.ledger.transfer(old_account, new_account, cash)
        elif cash < 0.0:
            self.econ.ledger.transfer(new_account, old_account, -cash)

        debt = float(sheet.debt_claim)
        if debt > 0.0 and hasattr(self.econ.ledger, "transfer_debt"):
            old_debt_total = max(0.0, float(self.econ.ledger.debt(old_account)))
            self.econ.ledger.transfer_debt(old_account, new_account, debt)
            if old_debt_total > 0.0:
                self._move_margin_debt_shadow(old_account, new_account, debt / old_debt_total)

        for asset_id, amount in list(sheet.equity_claims.items()):
            if amount == 0.0:
                continue
            self._adjust_household_equity(old_account, asset_id, -amount)
            self._adjust_household_equity(new_account, asset_id, amount)
        if sheet.bond_face_claim:
            self._move_bond_lots(old_account, new_account, sheet.bond_face_claim)
        for bank_id, amount in list(sheet.bank_equity_claims.items()):
            if amount == 0.0:
                continue
            self._adjust_bank_equity_owner(bank_id, old_account, -amount)
            self._adjust_bank_equity_owner(bank_id, new_account, amount)

    def _adjust_household_equity(self, account_id: str, asset_id: str, delta: float) -> None:
        household = self._household_agent(account_id)
        if household is None or delta == 0.0:
            return
        if asset_id == AGGREGATE_EQUITY_CLAIM_ID:
            household.shares = float(getattr(household, "shares", 0.0)) + float(delta)
            if abs(household.shares) <= 1e-9:
                household.shares = 0.0
            return
        if not hasattr(household, "holdings") or getattr(household, "holdings") is None:
            household.holdings = {}
        household.holdings[asset_id] = household.holdings.get(asset_id, 0.0) + float(delta)
        if abs(household.holdings[asset_id]) <= 1e-9:
            household.holdings.pop(asset_id, None)

    def _move_margin_debt_shadow(self, old_account: str, new_account: str, fraction: float) -> None:
        fraction = max(0.0, min(1.0, float(fraction)))
        if fraction <= 0.0:
            return
        old_household = self._household_agent(old_account)
        new_household = self._household_agent(new_account)
        if old_household is None or new_household is None:
            return
        old_margin_debt = max(0.0, float(getattr(old_household, "margin_debt", 0.0)))
        if old_margin_debt <= 0.0:
            return
        moved = old_margin_debt * fraction
        old_household.margin_debt = max(0.0, old_margin_debt - moved)
        new_household.margin_debt = max(0.0, float(getattr(new_household, "margin_debt", 0.0))) + moved

    def _move_bond_lots(self, old_account: str, new_account: str, face_amount: float) -> None:
        if self.econ is None or face_amount <= 0.0:
            return
        remaining = float(face_amount)
        moved_lots: list[dict] = []
        for lot in list(getattr(self.econ, "_bonds", []) or []):
            if remaining <= 1e-9:
                break
            if lot.get("holder") != old_account:
                continue
            face = float(lot.get("face", 0.0))
            if face <= 0.0:
                continue
            moved = min(face, remaining)
            if moved >= face - 1e-9:
                lot["holder"] = new_account
                remaining -= face
                continue
            ratio = moved / face
            moved_lot = dict(lot)
            moved_lot["holder"] = new_account
            moved_lot["face"] = moved
            if "cost" in moved_lot:
                moved_lot["cost"] = float(moved_lot["cost"]) * ratio
                lot["cost"] = float(lot["cost"]) * (1.0 - ratio)
            lot["face"] = face - moved
            moved_lots.append(moved_lot)
            remaining -= moved
        if moved_lots:
            self.econ._bonds.extend(moved_lots)
        self._reindex_bonds_if_present()

    def _reindex_bonds_if_present(self) -> None:
        if self.econ is None or not hasattr(self.econ, "_bond_holdings"):
            return
        idx: dict[Any, float] = {}
        for lot in getattr(self.econ, "_bonds", []) or []:
            idx[lot["holder"]] = idx.get(lot["holder"], 0.0) + float(lot.get("face", 0.0))
        self.econ._bond_holdings = idx

    def _adjust_bank_equity_owner(self, bank_id: str, account_id: str, delta: float) -> None:
        if self.econ is None or delta == 0.0:
            return
        for bank in getattr(self.econ, "banks", []) or []:
            if getattr(bank, "id", None) != bank_id:
                continue
            if getattr(bank, "owners", None) is None:
                bank.owners = {}
            bank.owners[account_id] = bank.owners.get(account_id, 0.0) + float(delta)
            if abs(bank.owners[account_id]) <= 1e-9:
                bank.owners.pop(account_id, None)
            return

    def _settle_deceased_claim_package_if_possible(
        self,
        dead_person: Any,
        *,
        surviving_spouse_id: int | None,
        tick: int,
    ) -> bool:
        people_by_id = self._people_by_id()
        if not people_by_id:
            return False
        heirs = select_default_heirs(dead_person, people_by_id, spouse_id_override=surviving_spouse_id)
        weights = self._inheritance_weights(heirs)
        if not weights:
            return False

        dead_id = int(dead_person.id)
        dead_sheet = self.claims.balance_sheet(dead_id)
        household_id = dead_sheet.household_id
        package = self._claim_package(dead_id)
        for heir_id in weights:
            if not self.claims.has_person(int(heir_id)):
                heir = people_by_id.get(int(heir_id))
                if heir is not None and getattr(heir, "household_id", None) is not None:
                    self.claims.add_person(int(heir_id), household_id=int(heir.household_id))
        for heir_id, weight in weights.items():
            self._transfer_claim_package(dead_id, int(heir_id), package, weight)
        estate_net_worth = max(0.0, float(package["cash"]) + float(package["bond_face"])
                               + sum(package["equity"].values())
                               + sum(package["bank_equity"].values())
                               - float(package["debt"]))
        self.claims.clear_person_claims(dead_id)
        estate = self.estates.create_suspense_estate(
            dead_id,
            estate_net_worth,
            tick,
            household_id=household_id,
        )
        estate.net_worth = 0.0
        estate.cleared = True
        return True

    def _inheritance_weights(self, heirs: Any) -> dict[int, float]:
        if heirs.spouse_id is not None and heirs.child_ids:
            weights = {int(heirs.spouse_id): 0.5}
            child_share = 0.5 / len(heirs.child_ids)
            for child_id in heirs.child_ids:
                weights[int(child_id)] = weights.get(int(child_id), 0.0) + child_share
            return weights
        if heirs.spouse_id is not None:
            return {int(heirs.spouse_id): 1.0}
        if heirs.child_ids:
            share = 1.0 / len(heirs.child_ids)
            return {int(child_id): share for child_id in heirs.child_ids}
        if heirs.parent_ids:
            share = 1.0 / len(heirs.parent_ids)
            return {int(parent_id): share for parent_id in heirs.parent_ids}
        return {}

    def _claim_package(self, person_id: int) -> dict[str, Any]:
        sheet = self.claims.balance_sheet(person_id)
        return {
            "cash": float(sheet.cash_claim),
            "debt": float(sheet.debt_claim),
            "equity": dict(sheet.equity_claims),
            "bond_face": float(sheet.bond_face_claim),
            "bank_equity": dict(sheet.bank_equity_claims),
        }

    def _retained_estate_required(self, package: dict[str, Any]) -> bool:
        return (
            float(package["bond_face"]) != 0.0
            or any(float(amount) != 0.0 for amount in package["equity"].values())
            or any(float(amount) != 0.0 for amount in package["bank_equity"].values())
        )

    def _package_net_worth(self, package: dict[str, Any]) -> float:
        return max(
            0.0,
            float(package["cash"])
            + float(package["bond_face"])
            + sum(float(amount) for amount in package["equity"].values())
            + sum(float(amount) for amount in package["bank_equity"].values())
            - float(package["debt"]),
        )

    def _transfer_claim_package(
        self,
        src_person_id: int,
        dst_person_id: int,
        package: dict[str, Any],
        fraction: float,
    ) -> None:
        if fraction <= 0.0:
            return
        src_sheet = self.claims.balance_sheet(src_person_id)
        dst_sheet = self.claims.balance_sheet(dst_person_id)
        src_account = self.account_for_household_id(src_sheet.household_id)
        dst_account = self.account_for_household_id(dst_sheet.household_id)

        cash = float(package["cash"]) * fraction
        if cash:
            src_sheet.cash_claim -= cash
            dst_sheet.cash_claim += cash
            if src_account != dst_account:
                if cash > 0.0:
                    self.econ.ledger.transfer(src_account, dst_account, cash)
                else:
                    self.econ.ledger.transfer(dst_account, src_account, -cash)

        debt = float(package["debt"]) * fraction
        if debt:
            src_sheet.debt_claim -= debt
            dst_sheet.debt_claim += debt
            if src_account != dst_account and hasattr(self.econ.ledger, "transfer_debt"):
                self.econ.ledger.transfer_debt(src_account, dst_account, debt)

        for asset_id, amount in package["equity"].items():
            moved = float(amount) * fraction
            if moved == 0.0:
                continue
            src_sheet.equity_claims[asset_id] = src_sheet.equity_claims.get(asset_id, 0.0) - moved
            if abs(src_sheet.equity_claims[asset_id]) <= 1e-9:
                src_sheet.equity_claims.pop(asset_id, None)
            dst_sheet.equity_claims[asset_id] = dst_sheet.equity_claims.get(asset_id, 0.0) + moved
            if src_account != dst_account:
                self._adjust_household_equity(src_account, asset_id, -moved)
                self._adjust_household_equity(dst_account, asset_id, moved)

        bond_face = float(package["bond_face"]) * fraction
        if bond_face:
            src_sheet.bond_face_claim -= bond_face
            dst_sheet.bond_face_claim += bond_face
            if abs(src_sheet.bond_face_claim) <= 1e-9:
                src_sheet.bond_face_claim = 0.0
            if src_account != dst_account:
                self._move_bond_lots(src_account, dst_account, bond_face)

        for bank_id, amount in package["bank_equity"].items():
            moved = float(amount) * fraction
            if moved == 0.0:
                continue
            src_sheet.bank_equity_claims[bank_id] = src_sheet.bank_equity_claims.get(bank_id, 0.0) - moved
            if abs(src_sheet.bank_equity_claims[bank_id]) <= 1e-9:
                src_sheet.bank_equity_claims.pop(bank_id, None)
            dst_sheet.bank_equity_claims[bank_id] = dst_sheet.bank_equity_claims.get(bank_id, 0.0) + moved
            if src_account != dst_account:
                self._adjust_bank_equity_owner(bank_id, src_account, -moved)
                self._adjust_bank_equity_owner(bank_id, dst_account, moved)

    @staticmethod
    def _marriage_key(spouse_a_id: int, spouse_b_id: int) -> frozenset[int]:
        return frozenset({int(spouse_a_id), int(spouse_b_id)})

    def _dissolve_marriage_for_death(self, person_id: int) -> int | None:
        contract_key = None
        contract = None
        for key, candidate in self.marriage_contracts.items():
            if person_id in key:
                contract_key = key
                contract = candidate
                break
        spouse_id = None
        if contract is not None:
            spouse_ids = [pid for pid in contract.spouse_ids if pid != person_id]
            spouse_id = spouse_ids[0] if spouse_ids else None
            dissolve_marriage(contract, self.claims, reason="death")
            if contract_key is not None:
                self.marriage_contracts.pop(contract_key, None)
        else:
            person = self._person_by_id(person_id)
            spouse_id = getattr(person, "partner_id", None) if person is not None else None
        spouse = self._person_by_id(int(spouse_id)) if spouse_id is not None else None
        if spouse is None or not getattr(spouse, "alive", True):
            return None
        return int(spouse_id)

    def _settle_estate_if_possible(
        self,
        estate: Any,
        dead_person: Any,
        *,
        surviving_spouse_id: int | None,
    ) -> None:
        people_by_id = self._people_by_id()
        if not people_by_id:
            return
        heirs = select_default_heirs(dead_person, people_by_id, spouse_id_override=surviving_spouse_id)
        heir_ids = [
            person_id
            for person_id in ([heirs.spouse_id] if heirs.spouse_id is not None else [])
            + list(heirs.child_ids)
            + list(heirs.parent_ids)
            if person_id is not None
        ]
        if not heir_ids:
            return
        for heir_id in heir_ids:
            if not self.claims.has_person(int(heir_id)):
                heir = people_by_id.get(int(heir_id))
                if heir is not None and getattr(heir, "household_id", None) is not None:
                    self.claims.add_person(int(heir_id), household_id=int(heir.household_id))
        payments = settle_estate(estate, heirs, self.claims)
        if self.econ is None or getattr(self.econ, "ledger", None) is None:
            return
        src_account = self.account_for_household_id(int(estate.household_id))
        for heir_id, amount in payments.items():
            if amount <= 0.0:
                continue
            dst_household_id = self.claims.balance_sheet(int(heir_id)).household_id
            dst_account = self.account_for_household_id(dst_household_id)
            if dst_account != src_account:
                self.econ.ledger.transfer(src_account, dst_account, amount)


def initialize_person_claims_from_households(
    econ: Any,
    demographic_state: Any,
    claim_split_policy: str = "adult_equal",
) -> DemographicEconomicBridge:
    if claim_split_policy != "adult_equal":
        raise ValueError("only adult_equal claim split is implemented in Phase 1")

    household_ids = sorted(
        {
            int(person.household_id)
            for person in getattr(demographic_state, "people")
            if getattr(person, "alive", True) and getattr(person, "household_id", None) is not None
        }
    )
    accounts = [household.id for household in econ.households]
    if len(household_ids) > len(accounts):
        raise ValueError("not enough economic household accounts for demographic households")

    mapping = {household_id: accounts[idx] for idx, household_id in enumerate(household_ids)}
    claims = PersonClaimLedger()
    bridge = DemographicEconomicBridge(
        claims=claims,
        household_to_account=mapping,
        estates=EstateRegistry(),
        econ=econ,
    )
    bridge.demographic_state = demographic_state

    people_by_household: dict[int, list[Any]] = {household_id: [] for household_id in household_ids}
    for person in getattr(demographic_state, "people"):
        if getattr(person, "alive", True) and getattr(person, "household_id", None) is not None:
            people_by_household[int(person.household_id)].append(person)

    for household_id, people in people_by_household.items():
        account_id = mapping[household_id]
        adults = [person for person in people if int(person.age) >= 18]
        owners = adults or people
        owner_ids = {int(person.id) for person in owners}
        for person in sorted(people, key=lambda p: p.id):
            claims.add_person(
                int(person.id),
                household_id=household_id,
                cash_claim=0.0,
                debt_claim=0.0,
            )
        claims.reset_household_financial_claims(
            household_id,
            owner_ids=owner_ids,
            cash=econ.ledger.balance(account_id),
            debt=econ.ledger.debt(account_id),
            holdings=bridge._household_asset_claim_targets(econ, account_id),
        )

    registered: set[frozenset[int]] = set()
    for person in getattr(demographic_state, "people"):
        if not getattr(person, "alive", True) or getattr(person, "partner_id", None) is None:
            continue
        spouse_id = int(person.partner_id)
        key = bridge._marriage_key(int(person.id), spouse_id)
        if key in registered:
            continue
        spouse = bridge._person_by_id(spouse_id)
        if spouse is None or not getattr(spouse, "alive", True) or getattr(spouse, "partner_id", None) != person.id:
            continue
        event = SimpleNamespace(
            spouse_a_id=int(person.id),
            spouse_b_id=spouse_id,
            household_id=int(person.household_id),
            tick=0,
            date=getattr(demographic_state, "current_date", None),
        )
        bridge.marriage_contracts[key] = record_marriage_contract(event, claims)
        registered.add(key)
    return bridge


def _phase1_person_state(state: Any) -> list[tuple]:
    return [
        (p.id, p.alive, p.age, p.household_id, p.partner_id, p.mother_id, p.father_id, p.death_tick)
        for p in state.people
    ]


def run_phase1_invariance_check(
    *,
    rates: Any,
    n: int,
    seed: int,
    years: int,
    enabled_channels: list[str] | None = None,
) -> dict[str, bool]:
    del enabled_channels
    base = create_genesis_population(rates, n=n, seed=seed)
    bridged = create_genesis_population(rates, n=n, seed=seed)

    class _Household:
        def __init__(self, account_id: str) -> None:
            self.id = account_id

    class _Econ:
        def __init__(self, state: Any) -> None:
            household_ids = sorted(
                {
                    int(person.household_id)
                    for person in state.people
                    if person.alive and person.household_id is not None
                }
            )
            self.households = [_Household(f"H{idx}") for idx, _ in enumerate(household_ids)]
            initial = {household.id: 0.0 for household in self.households}
            initial["BANK_0"] = 0.0
            from macro_sim.core.ledger import Ledger

            self.ledger = Ledger(initial)

    econ = _Econ(bridged)
    bridge = initialize_person_claims_from_households(econ, bridged)
    base_kernel = MicroDemographicKernel(rates, rng_seed=seed + 1)
    bridge_kernel = MicroDemographicKernel(rates, rng_seed=seed + 1, on_birth=bridge.on_birth, on_death=bridge.on_death)

    for _ in range(int(years * 365)):
        base_kernel.tick(base)
        bridge_kernel.tick(bridged, economic_state=bridge)

    base_events = [(event.tick, event.person_id) for event in base.birth_events + base.death_events]
    bridge_events = [(event.tick, event.person_id) for event in bridged.birth_events + bridged.death_events]
    return {
        "event_sequence_equal": base_events == bridge_events,
        "alive_by_age_equal": np.array_equal(count_alive_by_age(base.people, rates.omega), count_alive_by_age(bridged.people, rates.omega)),
        "person_state_equal": _phase1_person_state(base) == _phase1_person_state(bridged),
    }
