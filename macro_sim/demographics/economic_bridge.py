"""Bridge between demographic people/households and the economic ledger."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import numpy as np

from macro_sim.demographics.economic_state import (
    CLAIM_TOL,
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
from macro_sim.demographics.rates import expected_life_at_birth
from macro_sim.demographics.marriage_economics import MarriageContract, dissolve_marriage, record_marriage_contract


AGGREGATE_EQUITY_CLAIM_ID = "__aggregate_equity__"
BOND_FACE_CLAIM_ID = "__bond_face__"
BANK_EQUITY_CLAIM_PREFIX = "__bank_equity__:"
BANK_EQUITY_CLAIM_TOL = 1e-4
BANK_EQUITY_DUST_SHARE = 1e-6
BANK_EQUITY_RECONCILE_SHARE = 1e-4


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
    macro_signal: Any | None = None    # v14 Phase 2: DemoMacroSignal (None = feedback plumbing absent)
    stratification: Any | None = None  # v14 Phase 3.0: WealthStratification (observation only)
    _effective_rates_cache: dict[float, Any] = field(default_factory=dict)   # mortality mult -> derived rates
    _e0_cache: dict[float, float] = field(default_factory=dict)              # mortality mult -> e0

    def __post_init__(self) -> None:
        self.account_to_household = {account: household for household, account in self.household_to_account.items()}
        # Per-tick read caches over the demographic state. The demographic kernel owns all person
        # mutations (deaths, marriages, guardianship moves), so the economy invalidates before the
        # kernel runs and refreshes once after it; every economic phase then reads O(1) indexes
        # instead of scanning `state.people` per household (the former O(N_households x N_people)
        # per tick). While invalid (None), all lookups fall back to the original live scans.
        self._people_by_household_index: dict[int, list[Any]] | None = None
        self._person_by_id_index: dict[int, Any] | None = None
        self._household_profiles_cache: dict[int, Any] | None = None
        self._household_agent_by_account: dict[str, Any] = {}

    def invalidate_people_index(self) -> None:
        self._people_by_household_index = None
        self._person_by_id_index = None
        self._household_profiles_cache = None

    def refresh_people_index(self) -> None:
        """Rebuild person indexes from the live demographic state.

        Call only when the demographic state is frozen for the rest of the tick
        (after the kernel tick + household transitions). Order inside each
        household list is `state.people` order, matching the live-scan filter.
        """
        state = self._demographic_state_ref()
        self._household_profiles_cache = None
        if state is None:
            self._people_by_household_index = None
            self._person_by_id_index = None
            return
        by_household: dict[int, list[Any]] = {}
        by_id: dict[int, Any] = {}
        for person in getattr(state, "people", []):
            by_id[int(person.id)] = person
            if getattr(person, "alive", True):
                household_id = getattr(person, "household_id", None)
                if household_id is not None:
                    by_household.setdefault(int(household_id), []).append(person)
        self._people_by_household_index = by_household
        self._person_by_id_index = by_id

    def _demographic_state_ref(self) -> Any | None:
        state = getattr(self, "demographic_state", None)
        if state is None and self.econ is not None:
            state = getattr(self.econ, "demographic_state", None)
        return state

    def account_for_household_id(self, household_id: int) -> str:
        return self.household_to_account[int(household_id)]

    def household_id_for_account(self, account_id: str) -> int:
        return self.account_to_household[account_id]

    # ------------------------------------------------------------------
    # v14 Phase 2: macro -> vital-rate feedback signal
    # ------------------------------------------------------------------
    @property
    def fertility_macro_multiplier(self) -> float:
        mult = self.macro_signal.fertility_mult if self.macro_signal is not None else 1.0
        # v15.5 channel 2.1d: housing affordability (price-to-income) composes
        # multiplicatively with the Phase 2 income channel -- the kernel keeps reading
        # ONE scalar, and each factor is separately flag-gated and neutrality-anchored
        housing_signal = getattr(self.econ, "housing_affordability", None) if self.econ is not None else None
        if housing_signal is not None and housing_signal.fertility_mult != 1.0:
            mult *= housing_signal.fertility_mult
        return mult

    @property
    def mortality_macro_multiplier(self) -> float:
        mult = self.macro_signal.mortality_mult if self.macro_signal is not None else 1.0
        # v17.5: fuel poverty composes multiplicatively (cold-home mortality) -- the
        # v15.5 housing-fertility precedent above; exactly 1.0 when the channel is
        # off, so every pre-energy configuration stays bit-identical.
        energy_signal = getattr(self.econ, "energy_poverty_signal", None) if self.econ is not None else None
        if energy_signal is not None and energy_signal.mortality_mult != 1.0:
            mult *= energy_signal.mortality_mult
        return mult

    @property
    def effective_vital_rates(self) -> Any | None:
        """Mortality-scaled Phase0VitalRates (v14 Phase 2.2).

        Gompertz-Makeham hazards are CLOSED under proportional scaling: hazard x M is
        the same family with (a, b, infant_extra) each x M. Deriving one frozen rates
        instance per multiplier value (annual => a handful per run) means the kernel's
        survival draw AND the memoized e(a) lifecycle table both consume the scaled
        mortality through their existing signatures -- no cache bypass, no drift between
        what kills people and what they annuitize over.
        """
        return self._derived_rates(self.mortality_macro_multiplier)

    @property
    def mortality_strata(self) -> dict[int, float] | None:
        """v14 Phase 3.1: household_id -> mortality multiplier (rank gradient, mean-one).
        None when the channel is off, so the kernel skips the lookup entirely."""
        strat = self.stratification
        if strat is None or not strat.mortality_strata:
            return None
        return strat.mortality_strata

    @property
    def fertility_strata(self) -> dict[int, float] | None:
        strat = self.stratification
        if strat is None or not strat.fertility_strata:
            return None
        return strat.fertility_strata

    @property
    def household_ranks(self) -> dict[int, float] | None:
        """v14 Phase 3.3: wealth-rank snapshot for marriage-market homophily."""
        strat = self.stratification
        if strat is None or not strat.household_rank:
            return None
        return strat.household_rank

    def _person_household_rank(self, person_id: int) -> float | None:
        strat = self.stratification
        if strat is None or not self.claims.has_person(person_id):
            return None
        household_id = self.claims.balance_sheet(person_id).household_id
        if household_id is None:
            return None
        return strat.household_rank.get(int(household_id))

    def _derived_rates(self, multiplier: float) -> Any | None:
        """Scaled Phase0VitalRates for an arbitrary combined multiplier (macro x stratum),
        cached per value (annual updates => a handful of keys per run)."""
        base = getattr(self.econ, "demographic_rates", None) if self.econ is not None else None
        if base is None:
            return None
        if multiplier == 1.0:
            return base
        cached = self._effective_rates_cache.get(multiplier)
        if cached is None:
            cached = dataclasses.replace(
                base,
                makeham_a=base.makeham_a * multiplier,
                gompertz_b=base.gompertz_b * multiplier,
                infant_extra=base.infant_extra * multiplier,
            )
            self._effective_rates_cache[multiplier] = cached
        return cached

    @property
    def e0_effective(self) -> float:
        rates = self.effective_vital_rates
        if rates is None:
            return 0.0
        multiplier = self.mortality_macro_multiplier
        value = self._e0_cache.get(multiplier)
        if value is None:
            value = expected_life_at_birth(rates)
            self._e0_cache[multiplier] = value
        return value

    def observe_macro(self, econ: Any, rec: dict) -> None:
        """Feed one tick of realized macro state into the annual demography signal.

        Called at the END of economy.step (after metrics), so `rec` is the canonical
        per-tick snapshot: the multiplier recorded in `rec` is the one the kernel
        actually used this tick, and any annual rollover computed here only takes
        effect from the next tick's kernel run.
        """
        if self.macro_signal is None:
            return
        state = self._demographic_state_ref()
        if state is None:
            return
        self.macro_signal.observe_tick(
            year=state.current_date.year,
            wages_paid=rec.get("wages_paid", 0.0),
            labor=rec.get("employment", 0.0),
            price=rec.get("price_index", 0.0),
        )
        if self.stratification is not None:
            self.stratification.observe_tick(econ, self, state.current_date.year)

    def assert_all_claim_identities(self, econ: Any | None = None) -> None:
        econ = econ or self.econ
        if econ is None:
            raise RuntimeError("economic ledger is required for claim identity checks")
        bond_face_by_holder = self._bond_face_by_holder(econ)
        for household_id in self.household_to_account:
            self._prune_household_bank_equity_claim_dust(household_id, econ)
        for household_id in self.household_to_account:
            self._normalize_household_bank_equity_claims_to_targets(household_id, econ)
        for household_id, account_id in self.household_to_account.items():
            self.claims.assert_household_claim_identity(
                household_id,
                deposits=econ.ledger.balance(account_id),
                debt=econ.ledger.debt(account_id),
                holdings=self._household_asset_claim_targets(econ, account_id, bond_face_by_holder),
                holding_tolerances=self._household_asset_claim_tolerances(econ),
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
        bond_face_by_holder = self._bond_face_by_holder(econ)
        for household_id, account_id in self.household_to_account.items():
            estate_suspense = self.claims.estate_suspense_by_household.get(household_id, 0.0)
            self.claims.reset_household_financial_claims(
                household_id,
                owner_ids=self._claim_owner_ids(household_id),
                cash=econ.ledger.balance(account_id) - estate_suspense,
                debt=econ.ledger.debt(account_id),
                holdings=self._household_asset_claim_targets(econ, account_id, bond_face_by_holder),
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
        self._normalize_household_bank_equity_claim_to_target(household_id, bank_id)

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
        profiles = self._household_profiles_cache
        if profiles is None:
            state = self._demographic_state_ref()
            if state is None:
                raise RuntimeError("demographic state is required for household profiles")
            profiles = build_household_economic_profiles(state, self.claims)
            # Only memoize while the per-tick people index is valid (state frozen); during the
            # demographic-kernel window every call rebuilds from the live state, as before.
            if self._people_by_household_index is not None:
                self._household_profiles_cache = profiles
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
        # v14 Phase 2.2 + 3.1: households annuitize over the EFFECTIVE life table for
        # their stratum -- combined multiplier = macro level x rank-gradient stratum, so
        # the rich (longer expected lives) spread wealth thinner and save more WITHOUT any
        # behavioral code. Neutral multipliers return the base object (bit-identical off).
        combined = self.mortality_macro_multiplier
        strata = self.mortality_strata
        if strata:
            household_id = self.household_id_for_account(account_id)
            combined *= strata.get(int(household_id), 1.0)
        effective = self._derived_rates(combined)
        if effective is not None:
            rates = effective
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
        self.invalidate_people_index()
        household_id = int(newborn.household_id)
        if self.stratification is not None:
            self.stratification.record_birth(household_id)
        if not self.claims.has_person(int(newborn.id)):
            self.claims.add_person(int(newborn.id), household_id=household_id)

    def on_marriage(self, event: Any) -> None:
        self.invalidate_people_index()
        if self.stratification is not None:
            # pre-merge spousal ranks: the sheets still carry the OLD household ids here
            self.stratification.record_marriage(
                self._person_household_rank(int(event.spouse_a_id)),
                self._person_household_rank(int(event.spouse_b_id)),
            )
        self._sync_demographic_household(int(event.household_id))
        key = self._marriage_key(int(event.spouse_a_id), int(event.spouse_b_id))
        if key not in self.marriage_contracts:
            self.marriage_contracts[key] = record_marriage_contract(event, self.claims)

    def on_divorce(self, event: Any) -> None:
        self.invalidate_people_index()
        key = self._marriage_key(int(event.spouse_a_id), int(event.spouse_b_id))
        contract = self.marriage_contracts.pop(key, None)
        if contract is not None:
            result = dissolve_marriage(contract, self.claims, reason="divorce")
            self._apply_dissolution_transfers(result)
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
            # only ledger-backed debt can be written off there; an unbacked residual claim
            # simply dies with the deceased
            amount = min(amount, max(0.0, float(self.econ.ledger.debt(account_id))))
            if amount <= 0.0:
                return
            self.econ.ledger.write_off(account_id, creditor_bank_id, amount)
            self._clamp_margin_debt_shadow(account_id)
        else:
            self._bank_capital_adjustment[creditor_bank_id] = (
                self._bank_capital_adjustment.get(creditor_bank_id, 0.0) - amount
            )
        self.death_writeoff_flow += amount

    def on_death(self, event: Any, dead_person: Any) -> None:
        self.invalidate_people_index()   # alive-status changed; re-scan live until the next refresh
        person_id = int(dead_person.id)
        if self.stratification is not None:
            self.stratification.record_death(dead_person.household_id)
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
                fiscal = getattr(self.econ, "_fiscal", None) if self.econ is not None else None
                state_can_receive = (
                    fiscal is not None
                    and getattr(self.econ, "ledger", None) is not None
                    and self.econ.ledger.has_account(fiscal)
                )
                if state_can_receive and not self._has_other_household_claimants(person_id, sheet.household_id):
                    # HEIRLESS estate with securities: no default heirs anywhere and nobody left
                    # in the household. Retaining it forever makes a zombie investor; dropping
                    # the claims orphans the account's positions (identity drift). Real probate:
                    # LIQUIDATE, settle the estate's DEBTS first, then the residue passes to
                    # the state (bona vacantia).
                    household_id = sheet.household_id
                    self._liquidate_deceased_securities(person_id, household_id)
                    self._settle_deceased_debt_in_full(person_id, household_id)
                    escheated = self._escheat_deceased_cash(person_id, household_id)
                    self._clear_deceased_claims(person_id, household_id)
                    estate = self.estates.create_suspense_estate(
                        person_id, escheated, tick, household_id=household_id,
                    )
                    estate.net_worth = 0.0
                    estate.cleared = True
                    return
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
            if debt > 0.0:
                # estate debts settle before distribution (real probate order): repay the
                # deceased's attributed share from their cash (cohabitants' cash is protected
                # by the repay cap), write off what the estate cannot cover -- otherwise the
                # cleared sheet strands ledger debt no person claim backs, and the suspense
                # arithmetic (assets - debt) only balances against a debt-free account
                self._settle_deceased_debt_in_full(person_id, household_id)
            self._clear_deceased_claims(person_id, household_id)
            estate = self.estates.create_suspense_estate(person_id, estate_value, tick, household_id=household_id)
            self.claims.register_estate_suspense(estate.net_worth, household_id=household_id)
            return

        unpaid = debt - assets
        bank_id = self._creditor_bank_for_person(person_id, sheet.household_id)
        if bank_id is None:
            raise RuntimeError(f"missing creditor bank for insolvent death of person {person_id}")
        sole_claimant = not self._has_other_household_claimants(person_id, sheet.household_id)
        if sole_claimant:
            # INSOLVENT and nobody left in the household: administer the estate -- liquidate the
            # securities so the creditor recovers from them BEFORE the write-off (previously the
            # claims were dropped and the account's positions were orphaned while the bank ate
            # the full shortfall).
            self._liquidate_deceased_securities(person_id, sheet.household_id)
        unpaid = self._repay_deceased_debt_with_cash(person_id, max_unpaid=unpaid)
        self.write_off_deceased_debt(person_id, unpaid, bank_id)
        self._clear_deceased_claims(person_id, sheet.household_id)
        if sole_claimant:
            # the probate waterfall on the emptied estate account (net of parked suspense):
            # the creditor recovers up to the loss it just booked, any残余 escheats to the
            # state (or stays put in degraded environments without a fiscal account)
            suspense = max(0.0, float(self.claims.estate_suspense_by_household.get(int(sheet.household_id), 0.0)))
            account_id = self.household_to_account.get(int(sheet.household_id))
            if account_id is not None:
                available = max(0.0, float(self.econ.ledger.balance(account_id)) - suspense)
                recovery = min(available, max(0.0, float(unpaid)))
                if recovery > 0.0:
                    self.econ.ledger.transfer(account_id, bank_id, recovery)
                    available -= recovery
                fiscal = getattr(self.econ, "_fiscal", None)
                if available > 0.0 and fiscal is not None and self.econ.ledger.has_account(fiscal):
                    self.econ.ledger.transfer(account_id, fiscal, available)
                    self.econ._escheat_flow = getattr(self.econ, "_escheat_flow", 0.0) + available
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
        ledger_debt = max(0.0, float(self.econ.ledger.debt(account_id)))
        protected_cash = self._other_positive_cash_claims(person_id, sheet.household_id)
        available_cash = max(0.0, ledger_cash - protected_cash)
        # a debt CLAIM only repays up to the ledger loan actually backing it (claims-only debt
        # in stub environments, or historical drift, must not trip the ledger's repay guard)
        pay = min(cash, debt, available_cash, ledger_debt)
        if pay > 0.0:
            self.econ.ledger.repay(account_id, pay)
            sheet.cash_claim -= pay
            sheet.debt_claim = max(0.0, sheet.debt_claim - pay)
            self._clamp_margin_debt_shadow(account_id)
        return max(0.0, float(sheet.debt_claim))

    def _clamp_margin_debt_shadow(self, account_id: str) -> None:
        """Deceased-debt repayment/write-off reduces LEDGER debt; the household agent's
        margin_debt shadow must never exceed it (margin debt is part of ledger debt), or the
        equity phase later over-repays and the ledger raises. Clamp only when provably stale."""
        if self.econ is None or getattr(self.econ, "ledger", None) is None:
            return
        agent = self._household_agent(account_id)
        if agent is None:
            return
        margin = float(getattr(agent, "margin_debt", 0.0) or 0.0)
        if margin <= 0.0:
            return
        ledger_debt = max(0.0, float(self.econ.ledger.debt(account_id)))
        if margin > ledger_debt:
            agent.margin_debt = ledger_debt

    def _other_positive_cash_claims(self, person_id: int, household_id: int) -> float:
        total = 0.0
        for other_id in self.claims.members_of_household(int(household_id)):
            if int(other_id) == int(person_id):
                continue
            total += max(0.0, float(self.claims.balance_sheet(other_id).cash_claim))
        total += max(0.0, float(self.claims.estate_suspense_by_household.get(int(household_id), 0.0)))
        return total

    def _has_other_household_claimants(self, person_id: int, household_id: int) -> bool:
        return any(
            int(other_id) != int(person_id)
            for other_id in self.claims.members_of_household(int(household_id))
        )

    def _liquidate_deceased_securities(self, person_id: int, household_id: int) -> None:
        """Estate liquidation for a deceased with no household co-claimants.

        Bonds are redeemed at face against the Treasury (bills are near-money; the redemption
        posts its own claim updates through the normal bridge plumbing). Firm and bank equity
        positions are CANCELLED share-for-share -- there is no fire-sale market at this
        abstraction, and cancellation is the precedented write-up (firm bankruptcy and bank
        failure already extinguish equity); Σholdings == shares_outstanding is preserved on
        both sides, and the micro write-up accrues to surviving shareholders. Only the
        per-firm-equity market is wired (v6.1+; every v12/v13 config); the aggregate-index
        market has no per-account cancellation channel and is left untouched.
        """
        econ = self.econ
        account_id = self.household_to_account.get(int(household_id))
        if econ is None or getattr(econ, "ledger", None) is None or account_id is None:
            return
        sheet = self.claims.balance_sheet(person_id)
        held_face = float((getattr(econ, "_bond_holdings", {}) or {}).get(account_id, 0.0))
        fiscal = getattr(econ, "_fiscal", None)
        if (held_face > 0.0 or float(sheet.bond_face_claim) > 0.0) and fiscal is not None \
                and econ.ledger.has_account(fiscal):
            from macro_sim.systems.securities import redeem_household_bonds

            # redeem EVERY lot on the account (the estate owns the whole account; claims may
            # carry historical drift, so the lots are the ground truth)
            redeem_household_bonds(econ, account_id, float("inf"))
        agent = self._household_agent(account_id)
        if agent is not None and getattr(getattr(econ, "cfg", None), "per_firm_equity", False):
            holdings = getattr(agent, "holdings", None) or {}
            if holdings:
                firm_by_id = {firm.id: firm for firm in getattr(econ, "c_firms", [])}
                for asset_id, amount in list(holdings.items()):
                    firm = firm_by_id.get(asset_id)
                    if firm is not None:
                        firm.shares_outstanding = max(0.0, firm.shares_outstanding - float(amount))
                    holdings.pop(asset_id, None)
                for member_id in self.claims.members_of_household(int(household_id)):
                    self.claims.balance_sheet(member_id).equity_claims.clear()
        for bank in getattr(econ, "banks", []) or []:
            owners = getattr(bank, "owners", None) or {}
            shares = float(owners.get(account_id, 0.0))
            if shares != 0.0:
                owners.pop(account_id, None)
                bank.shares_outstanding = max(0.0, bank.shares_outstanding - shares)
        for member_id in self.claims.members_of_household(int(household_id)):
            self.claims.balance_sheet(member_id).bank_equity_claims.clear()

    def _extinguish_intra_household_iou(self, dead_person_id: int, household_id: int, amount: float) -> None:
        """The deceased's positive claim beyond the account balance is a claim ON the
        household's negative claimants (an intra-household IOU). Outside heirs cannot collect
        it, so it dies with the deceased: forgive the household debtors pro rata by the same
        amount (their negative cash claims move toward zero). The mirror of
        _absorb_negative_cash_claim. Any residue beyond the debtors' total (pure drift) stays
        a write-down."""
        remaining = float(amount)
        if remaining <= 0.0:
            return
        debtors = [
            (int(pid), -float(self.claims.balance_sheet(pid).cash_claim))
            for pid in self.claims.members_of_household(int(household_id))
            if int(pid) != int(dead_person_id) and float(self.claims.balance_sheet(pid).cash_claim) < 0.0
        ]
        total_owed = sum(owed for _, owed in debtors)
        if total_owed <= 0.0:
            return
        forgiven = min(remaining, total_owed)
        applied = 0.0
        for pid, owed in debtors[:-1]:
            cut = forgiven * owed / total_owed
            self.claims.balance_sheet(pid).cash_claim += cut
            applied += cut
        self.claims.balance_sheet(debtors[-1][0]).cash_claim += forgiven - applied

    def _apply_dissolution_transfers(self, result: Any) -> None:
        """Marital-property equalization is a REAL transfer: when the spouses' sheets sit on
        DIFFERENT accounts (stale contracts across households), the ledger money must move
        with the claim, capped by what the source account can actually pay (A4, net of parked
        estate suspense); any unbacked excess claim is clawed back so claims keep following
        money. Same-account equalizations stay a pure intra-account re-attribution."""
        if self.econ is None or getattr(self.econ, "ledger", None) is None:
            return
        for src_pid, dst_pid, amount in getattr(result, "transfers", []) or []:
            amount = float(amount)
            if amount <= 0.0:
                continue
            src_hh = self.claims.balance_sheet(int(src_pid)).household_id
            dst_hh = self.claims.balance_sheet(int(dst_pid)).household_id
            src_account = self.household_to_account.get(int(src_hh))
            dst_account = self.household_to_account.get(int(dst_hh))
            if src_account is None or dst_account is None or src_account == dst_account:
                continue
            suspense = max(0.0, float(self.claims.estate_suspense_by_household.get(int(src_hh), 0.0)))
            movable = max(0.0, float(self.econ.ledger.balance(src_account)) - suspense)
            move = min(amount, movable)
            if move > 0.0:
                self.econ.ledger.transfer(src_account, dst_account, move)
            shortfall = amount - move
            if shortfall > 1e-12:
                # the source account cannot back this much: reverse the unbacked claim part
                self.claims.transfer_cash_claim(int(dst_pid), int(src_pid), shortfall)

    def _settle_deceased_debt_in_full(self, person_id: int, household_id: int) -> None:
        """Estate debts settle before distribution: repay the deceased's debt from their cash
        (post-liquidation), write off whatever the estate cannot cover against the creditor."""
        residual = self._repay_deceased_debt_with_cash(
            person_id,
            max_unpaid=float(self.claims.balance_sheet(person_id).debt_claim),
        )
        if residual > 0.0:
            bank_id = self._creditor_bank_for_person(person_id, int(household_id))
            if bank_id is not None:
                self.write_off_deceased_debt(person_id, residual, bank_id)

    def _escheat_deceased_cash(self, person_id: int, household_id: int) -> float:
        """Bona vacantia: a solvent estate with no heirs anywhere passes to the state.

        Moves the deceased's attributable cash (their cash claim, capped by the account
        balance net of estate suspense) to the fiscal account. Returns the amount escheated.
        """
        econ = self.econ
        account_id = self.household_to_account.get(int(household_id))
        if econ is None or getattr(econ, "ledger", None) is None or account_id is None:
            return 0.0
        fiscal = getattr(econ, "_fiscal", None)
        if fiscal is None or not econ.ledger.has_account(fiscal):
            return 0.0
        sheet = self.claims.balance_sheet(person_id)
        suspense = max(0.0, float(self.claims.estate_suspense_by_household.get(int(household_id), 0.0)))
        # the estate owns the whole account: everything above parked suspense passes to the
        # state, which also heals any historical claims-vs-ledger drift on this account
        amount = max(0.0, float(econ.ledger.balance(account_id)) - suspense)
        if amount <= 0.0:
            return 0.0
        econ.ledger.transfer(account_id, fiscal, amount)
        sheet.cash_claim -= amount
        econ._escheat_flow = getattr(econ, "_escheat_flow", 0.0) + amount
        return amount

    def _sweep_stranded_dwellings(self) -> None:
        """v15 probate for dwellings, run on the periodic administration sweep: households
        can empty demographically through SEVERAL paths that never touch the claims-empty
        administration (deaths leave the dead members' sheets attached backing estate
        suspense; ORPHAN GUARDIANSHIP moves the last minor out with no bridge hook at all).
        A per-event hook misses whole families of these -- the sweep catches every dwelling
        whose owner household has no living members. Market on: forced probate listing
        (sale proceeds escheat at the moment of sale). Market off: bona-vacantia escheat
        in kind (v15.0 stopgap)."""
        econ = self.econ
        housing = getattr(econ, "housing", None) if econ is not None else None
        if housing is None:
            return
        market = getattr(econ, "housing_market", None)
        fiscal = getattr(econ, "_fiscal", None)
        state = self._demographic_state_ref()
        if state is None:
            return
        living_households = {
            int(person.household_id)
            for person in getattr(state, "people", [])
            if getattr(person, "alive", True) and person.household_id is not None
        }
        for account_id in list(housing.owners()):
            household_id = self.account_to_household.get(account_id)
            if household_id is None or int(household_id) in living_households:
                continue
            if market is not None:
                for dwelling in housing.dwellings_of(account_id):
                    market.list_dwelling(econ, dwelling.id, account_id, forced=True)
            elif fiscal is not None:
                moved = housing.transfer_all(account_id, fiscal)
                if moved:
                    econ._escheat_dwellings = getattr(econ, "_escheat_dwellings", 0) + moved

    def _clear_deceased_claims(self, person_id: int, household_id: int) -> None:
        self._absorb_negative_cash_claim(person_id, household_id)
        self._transfer_residual_asset_claims_to_household_claimants(person_id, household_id)
        self.claims.clear_person_claims(person_id)

    def _absorb_negative_cash_claim(self, person_id: int, household_id: int) -> None:
        sheet = self.claims.balance_sheet(person_id)
        burden = max(0.0, -float(sheet.cash_claim))
        if burden <= 0.0:
            return
        positive_claimants: list[tuple[int, float]] = []
        for other_id in self.claims.members_of_household(int(household_id)):
            if int(other_id) == int(person_id):
                continue
            cash = max(0.0, float(self.claims.balance_sheet(other_id).cash_claim))
            if cash > 0.0:
                positive_claimants.append((int(other_id), cash))
        total_positive = sum(cash for _, cash in positive_claimants)
        if total_positive <= 0.0:
            return
        absorbed = min(burden, total_positive)
        for other_id, cash in positive_claimants:
            self.claims.balance_sheet(other_id).cash_claim -= absorbed * cash / total_positive
        sheet.cash_claim += absorbed

    def _transfer_residual_asset_claims_to_household_claimants(self, person_id: int, household_id: int) -> None:
        recipients = [
            int(other_id)
            for other_id in self.claims.members_of_household(int(household_id))
            if int(other_id) != int(person_id)
        ]
        if not recipients:
            return
        sheet = self.claims.balance_sheet(person_id)
        share = 1.0 / len(recipients)
        for asset_id, amount in list(sheet.equity_claims.items()):
            if amount == 0.0:
                continue
            moved = float(amount) * share
            for recipient_id in recipients:
                target = self.claims.balance_sheet(recipient_id)
                target.equity_claims[asset_id] = target.equity_claims.get(asset_id, 0.0) + moved
        if sheet.bond_face_claim:
            moved = float(sheet.bond_face_claim) * share
            for recipient_id in recipients:
                self.claims.balance_sheet(recipient_id).bond_face_claim += moved
        for bank_id, amount in list(sheet.bank_equity_claims.items()):
            if amount == 0.0:
                continue
            moved = float(amount) * share
            for recipient_id in recipients:
                target = self.claims.balance_sheet(recipient_id)
                target.bank_equity_claims[bank_id] = target.bank_equity_claims.get(bank_id, 0.0) + moved

    def _people_by_household(self, household_id: int) -> list[Any] | None:
        index = self._people_by_household_index
        if index is not None:
            return index.get(int(household_id), [])
        state = self._demographic_state_ref()
        if state is None:
            return None
        return [
            person
            for person in getattr(state, "people", [])
            if getattr(person, "alive", True) and getattr(person, "household_id", None) == household_id
        ]

    def _person_by_id(self, person_id: int) -> Any | None:
        index = self._person_by_id_index
        if index is not None:
            return index.get(int(person_id))
        state = self._demographic_state_ref()
        if state is None:
            return None
        for person in getattr(state, "people", []):
            if int(person.id) == person_id:
                return person
        return None

    def _people_by_id(self) -> dict[int, Any]:
        index = self._person_by_id_index
        if index is not None:
            return index
        state = self._demographic_state_ref()
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
        if amount < 0.0:
            # debits allocate proportional to positive claims (capped) -- an equal split drives
            # small-claim members negative, and later household moves strand the negative
            takes = self.claims._debit_cash_proportional(list(person_ids), -amount)
            if reason == "tax_payment":
                for person_id, take in takes.items():
                    self.claims.balance_sheet(person_id).tax_paid_tick += take
            return
        share = amount / len(person_ids)
        for person_id in person_ids:
            sheet = self.claims.balance_sheet(person_id)
            sheet.cash_claim += share
            if reason == "capital_income":
                sheet.capital_income_tick += share
            elif reason == "transfer_income":
                sheet.transfer_income_tick += share

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
                if amount < 0.0:
                    self._reduce_household_bond_face_claim(household_id, -amount)
                    return
                sheet.bond_face_claim += share
            elif asset_id.startswith(BANK_EQUITY_CLAIM_PREFIX):
                bank_id = asset_id.split(":", 1)[1]
                if amount < 0.0:
                    self._reduce_household_bank_equity_claim(household_id, bank_id, -amount)
                    return
                sheet.bank_equity_claims[bank_id] = sheet.bank_equity_claims.get(bank_id, 0.0) + share
            else:
                if amount < 0.0:
                    self._reduce_household_equity_claim(household_id, asset_id, -amount)
                    return
                sheet.equity_claims[asset_id] = sheet.equity_claims.get(asset_id, 0.0) + share

    def _reduce_household_bond_face_claim(self, household_id: int, amount: float) -> None:
        remaining = max(0.0, float(amount))
        if remaining <= 0.0:
            return
        holders = [
            (person_id, max(0.0, float(self.claims.balance_sheet(person_id).bond_face_claim)))
            for person_id in self.claims.members_of_household(int(household_id))
        ]
        holders = [(person_id, face) for person_id, face in holders if face > 0.0]
        total_face = sum(face for _, face in holders)
        if total_face <= 0.0:
            return
        target = min(remaining, total_face)
        applied = 0.0
        for person_id, face in holders[:-1]:
            cut = min(face, target * face / total_face)
            sheet = self.claims.balance_sheet(person_id)
            sheet.bond_face_claim = max(0.0, sheet.bond_face_claim - cut)
            applied += cut
        last_id, _ = holders[-1]
        last_sheet = self.claims.balance_sheet(last_id)
        last_sheet.bond_face_claim = max(0.0, last_sheet.bond_face_claim - (target - applied))

    def _reduce_household_equity_claim(self, household_id: int, asset_id: str, amount: float) -> None:
        remaining = max(0.0, float(amount))
        if remaining <= 0.0:
            return
        holders = [
            (
                person_id,
                max(0.0, float(self.claims.balance_sheet(person_id).equity_claims.get(asset_id, 0.0))),
            )
            for person_id in self.claims.members_of_household(int(household_id))
        ]
        self._reduce_weighted_claims(
            holders,
            remaining,
            lambda person_id, cut: self._cut_person_equity_claim(person_id, asset_id, cut),
        )

    def _reduce_household_bank_equity_claim(self, household_id: int, bank_id: str, amount: float) -> None:
        remaining = max(0.0, float(amount))
        if remaining <= 0.0:
            return
        holders = [
            (
                person_id,
                max(0.0, float(self.claims.balance_sheet(person_id).bank_equity_claims.get(bank_id, 0.0))),
            )
            for person_id in self.claims.members_of_household(int(household_id))
        ]
        self._reduce_weighted_claims(
            holders,
            remaining,
            lambda person_id, cut: self._cut_person_bank_equity_claim(person_id, bank_id, cut),
        )

    def _normalize_household_bank_equity_claim_to_target(self, household_id: int, bank_id: str) -> None:
        if self.econ is None:
            return
        account_id = self.account_for_household_id(int(household_id))
        target = 0.0
        for bank in getattr(self.econ, "banks", []) or []:
            if getattr(bank, "id", None) != bank_id:
                continue
            target = float((getattr(bank, "owners", None) or {}).get(account_id, 0.0))
            break
        current = sum(
            float(self.claims.balance_sheet(person_id).bank_equity_claims.get(bank_id, 0.0))
            for person_id in self.claims.members_of_household(int(household_id))
        )
        diff = target - current
        tolerance = self._bank_equity_dust_tolerance(self.econ, bank_id)
        if abs(diff) <= tolerance:
            if abs(target) <= tolerance:
                self._reduce_household_bank_equity_claim(household_id, bank_id, current)
            return
        if diff > 0.0:
            person_ids = self._claim_posting_ids(household_id)
            if not person_ids:
                return
            share = diff / len(person_ids)
            for person_id in person_ids:
                sheet = self.claims.balance_sheet(person_id)
                sheet.bank_equity_claims[bank_id] = sheet.bank_equity_claims.get(bank_id, 0.0) + share
            return
        self._reduce_household_bank_equity_claim(household_id, bank_id, -diff)

    def _normalize_household_bank_equity_claims_to_targets(self, household_id: int, econ: Any) -> None:
        for bank in getattr(econ, "banks", []) or []:
            bank_id = str(getattr(bank, "id", ""))
            if not bank_id:
                continue
            account_id = self.account_for_household_id(int(household_id))
            target = float((getattr(bank, "owners", None) or {}).get(account_id, 0.0))
            current = sum(
                float(self.claims.balance_sheet(person_id).bank_equity_claims.get(bank_id, 0.0))
                for person_id in self.claims.members_of_household(int(household_id))
            )
            diff = target - current
            if abs(diff) <= self._bank_equity_dust_tolerance(econ, bank_id):
                continue
            if abs(diff) > self._bank_equity_reconcile_tolerance(econ, bank_id):
                continue
            if diff > 0.0:
                self._add_household_bank_equity_claim(household_id, bank_id, diff)
            else:
                self._reduce_household_bank_equity_claim(household_id, bank_id, -diff)

    def _add_household_bank_equity_claim(self, household_id: int, bank_id: str, amount: float) -> None:
        amount = float(amount)
        if amount <= 0.0:
            return
        members = self.claims.members_of_household(int(household_id))
        holders = [
            (
                person_id,
                max(0.0, float(self.claims.balance_sheet(person_id).bank_equity_claims.get(bank_id, 0.0))),
            )
            for person_id in members
        ]
        holders = [(person_id, value) for person_id, value in holders if value > 0.0]
        if holders:
            total = sum(value for _, value in holders)
            allocated = 0.0
            for person_id, value in holders[:-1]:
                share = amount * value / total
                self.claims.balance_sheet(person_id).bank_equity_claims[bank_id] = (
                    self.claims.balance_sheet(person_id).bank_equity_claims.get(bank_id, 0.0) + share
                )
                allocated += share
            last_id, _ = holders[-1]
            self.claims.balance_sheet(last_id).bank_equity_claims[bank_id] = (
                self.claims.balance_sheet(last_id).bank_equity_claims.get(bank_id, 0.0) + (amount - allocated)
            )
            return
        person_ids = self._claim_posting_ids(household_id)
        if not person_ids:
            return
        share = amount / len(person_ids)
        for person_id in person_ids:
            sheet = self.claims.balance_sheet(person_id)
            sheet.bank_equity_claims[bank_id] = sheet.bank_equity_claims.get(bank_id, 0.0) + share

    def _reduce_weighted_claims(self, holders: list[tuple[int, float]], amount: float, cut_fn: Any) -> None:
        holders = [(person_id, value) for person_id, value in holders if value > 0.0]
        total_value = sum(value for _, value in holders)
        if total_value <= 0.0:
            return
        target = min(float(amount), total_value)
        applied = 0.0
        for person_id, value in holders[:-1]:
            cut = min(value, target * value / total_value)
            cut_fn(person_id, cut)
            applied += cut
        last_id, _ = holders[-1]
        cut_fn(last_id, target - applied)

    def _cut_person_equity_claim(self, person_id: int, asset_id: str, amount: float) -> None:
        sheet = self.claims.balance_sheet(person_id)
        sheet.equity_claims[asset_id] = max(0.0, sheet.equity_claims.get(asset_id, 0.0) - float(amount))
        if sheet.equity_claims[asset_id] <= 1e-12:
            sheet.equity_claims.pop(asset_id, None)

    def _cut_person_bank_equity_claim(self, person_id: int, bank_id: str, amount: float) -> None:
        sheet = self.claims.balance_sheet(person_id)
        sheet.bank_equity_claims[bank_id] = max(0.0, sheet.bank_equity_claims.get(bank_id, 0.0) - float(amount))
        if sheet.bank_equity_claims[bank_id] <= 1e-12:
            sheet.bank_equity_claims.pop(bank_id, None)

    def _household_agent(self, account_id: str) -> Any | None:
        if self.econ is None:
            return None
        agent = self._household_agent_by_account.get(account_id)
        if agent is not None:
            return agent
        for household in getattr(self.econ, "households", []):
            if getattr(household, "id", None) == account_id:
                self._household_agent_by_account[account_id] = household
                return household
        return None

    def _household_asset_claim_targets(
        self,
        econ: Any,
        account_id: str,
        bond_face_by_holder: dict[Any, float] | None = None,
    ) -> dict[str, float]:
        targets: dict[str, float] = {}
        household = self._household_agent(account_id)
        if household is not None:
            if getattr(household, "shares", 0.0):
                targets[AGGREGATE_EQUITY_CLAIM_ID] = float(getattr(household, "shares", 0.0))
            for asset_id, shares in (getattr(household, "holdings", {}) or {}).items():
                if abs(float(shares)) > 0.0:
                    targets[str(asset_id)] = float(shares)
        if bond_face_by_holder is not None:
            bond_face = bond_face_by_holder.get(account_id, 0.0)
        else:
            bond_face = sum(
                float(lot.get("face", 0.0))
                for lot in (getattr(econ, "_bonds", []) or [])
                if lot.get("holder") == account_id
            )
        if abs(bond_face) > 0.0:
            targets[BOND_FACE_CLAIM_ID] = bond_face
        for bank in getattr(econ, "banks", []) or []:
            shares = float(((getattr(bank, "owners", None) or {}).get(account_id, 0.0)))
            outstanding = max(1.0, float(getattr(bank, "shares_outstanding", 0.0) or 0.0))
            dust_tolerance = max(BANK_EQUITY_CLAIM_TOL, CLAIM_TOL, outstanding * BANK_EQUITY_DUST_SHARE)
            if abs(shares) > dust_tolerance:
                targets[f"{BANK_EQUITY_CLAIM_PREFIX}{bank.id}"] = shares
        return targets

    def _household_asset_claim_tolerances(self, econ: Any) -> dict[str, float]:
        tolerances: dict[str, float] = {}
        for bank in getattr(econ, "banks", []) or []:
            tolerances[f"{BANK_EQUITY_CLAIM_PREFIX}{bank.id}"] = self._bank_equity_dust_tolerance(econ, str(bank.id))
        return tolerances

    def _prune_household_bank_equity_claim_dust(self, household_id: int, econ: Any) -> None:
        for person_id in self.claims.members_of_household(int(household_id)):
            sheet = self.claims.balance_sheet(person_id)
            for bank_id, amount in list(sheet.bank_equity_claims.items()):
                if abs(float(amount)) <= self._bank_equity_dust_tolerance(econ, bank_id):
                    sheet.bank_equity_claims.pop(bank_id, None)

    def _bank_equity_dust_tolerance(self, econ: Any, bank_id: str) -> float:
        for bank in getattr(econ, "banks", []) or []:
            if getattr(bank, "id", None) != bank_id:
                continue
            outstanding = max(1.0, float(getattr(bank, "shares_outstanding", 0.0) or 0.0))
            return max(BANK_EQUITY_CLAIM_TOL, CLAIM_TOL, outstanding * BANK_EQUITY_DUST_SHARE)
        return max(BANK_EQUITY_CLAIM_TOL, CLAIM_TOL)

    def _bank_equity_reconcile_tolerance(self, econ: Any, bank_id: str) -> float:
        for bank in getattr(econ, "banks", []) or []:
            if getattr(bank, "id", None) != bank_id:
                continue
            outstanding = max(1.0, float(getattr(bank, "shares_outstanding", 0.0) or 0.0))
            return max(self._bank_equity_dust_tolerance(econ, bank_id), outstanding * BANK_EQUITY_RECONCILE_SHARE)
        return self._bank_equity_dust_tolerance(econ, bank_id)

    @staticmethod
    def _bond_face_by_holder(econ: Any) -> dict[Any, float]:
        """One pass over the bond lots, grouped by holder, then sum() per holder over its values in
        lot order -- the same builtin over the same sequence as the per-account scan it replaces.
        (float sum() is compensated since Python 3.12; naive accumulation differs in the last bit.)"""
        values: dict[Any, list[float]] = {}
        for lot in getattr(econ, "_bonds", []) or []:
            values.setdefault(lot.get("holder"), []).append(float(lot.get("face", 0.0)))
        return {holder: float(sum(vals)) for holder, vals in values.items()}

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
        agent = self._new_household_agent(account_id, idx)
        self.econ.households.append(agent)
        self._household_agent_by_account[account_id] = agent
        # v11.5's id->household map predates household creation; without this, a post-genesis
        # household that buys bank equity is silently skipped by pay_bank_dividends.
        hh_by_id = getattr(self.econ, "_hh_by_id", None)
        if hh_by_id is not None:
            hh_by_id[account_id] = agent
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
        self.invalidate_people_index()   # person membership is changing; re-scan live until refresh
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
        if (
            old_account is not None
            and self.econ is not None
            and not self.claims.members_of_household(old_household_id)
        ):
            # The LAST member just left: by construction they own everything still attached to
            # the old account -- pro-rata rounding residue in agent holdings/bank ownership and
            # the deposits it keeps earning. Without this sweep the orphaned account collects
            # dividends no person claim can absorb (silent posting drops -> identity drift).
            self._sweep_orphaned_account(old_household_id, old_account, person_id, new_account)

    def _sweep_orphaned_account(
        self,
        old_household_id: int,
        old_account: str,
        heir_person_id: int,
        heir_account: str,
    ) -> None:
        econ = self.econ
        heir_sheet = self.claims.balance_sheet(heir_person_id)
        # deposits: estate suspense stays parked on the old household (the identity check counts
        # it on the claims side); everything above it belongs to the leaver.
        suspense = self.claims.estate_suspense_by_household.get(int(old_household_id), 0.0)
        movable = econ.ledger.balance(old_account) - suspense
        if movable > 0.0:
            econ.ledger.transfer(old_account, heir_account, movable)
            heir_sheet.cash_claim += movable
        debt = float(econ.ledger.debt(old_account))
        if debt > 0.0 and hasattr(econ.ledger, "transfer_debt"):
            econ.ledger.transfer_debt(old_account, heir_account, debt)
            heir_sheet.debt_claim += debt
            self._move_margin_debt_shadow(old_account, heir_account, 1.0)
        agent = self._household_agent(old_account)
        if agent is not None:
            shares = float(getattr(agent, "shares", 0.0) or 0.0)
            if shares != 0.0:
                self._adjust_household_equity(old_account, AGGREGATE_EQUITY_CLAIM_ID, -shares)
                self._adjust_household_equity(heir_account, AGGREGATE_EQUITY_CLAIM_ID, shares)
                heir_sheet.equity_claims[AGGREGATE_EQUITY_CLAIM_ID] = (
                    heir_sheet.equity_claims.get(AGGREGATE_EQUITY_CLAIM_ID, 0.0) + shares
                )
            for asset_id, amount in list((getattr(agent, "holdings", {}) or {}).items()):
                if amount == 0.0:
                    continue
                self._adjust_household_equity(old_account, asset_id, -amount)
                self._adjust_household_equity(heir_account, asset_id, amount)
                heir_sheet.equity_claims[asset_id] = heir_sheet.equity_claims.get(asset_id, 0.0) + amount
        for bank in getattr(econ, "banks", []) or []:
            shares = float(((getattr(bank, "owners", None) or {}).get(old_account, 0.0)))
            if shares != 0.0:
                self._adjust_bank_equity_owner(bank.id, old_account, -shares)
                self._adjust_bank_equity_owner(bank.id, heir_account, shares)
                heir_sheet.bank_equity_claims[bank.id] = (
                    heir_sheet.bank_equity_claims.get(bank.id, 0.0) + shares
                )
        residual_faces = [
            float(lot.get("face", 0.0))
            for lot in getattr(econ, "_bonds", []) or []
            if lot.get("holder") == old_account
        ]
        if residual_faces:
            total_face = float(sum(residual_faces))
            if total_face > 0.0:
                self._move_bond_lots(old_account, heir_account, total_face)
                heir_sheet.bond_face_claim += total_face
        housing = getattr(econ, "housing", None)
        if housing is not None:
            # v15.0: dwelling TITLE follows the merge sweep -- an orphaned account holding a
            # dwelling would be a title zombie (the registry analog of the dividend-collecting
            # orphan account this sweep exists to prevent)
            housing.transfer_all(old_account, heir_account)

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
        from macro_sim.systems.securities import bump_bonds_version

        bump_bonds_version(self.econ)   # holder/face/cost were rewritten in place above
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
        # Flavor 7 residue: a negative-cash share an insolvent heir could not back stays on
        # the dead sheet -- absorb it against the source household's positive claimants
        # BEFORE clearing, or the wipe would inflate the household's claims past the ledger.
        if float(self.claims.balance_sheet(dead_id).cash_claim) < 0.0:
            self._absorb_negative_cash_claim(dead_id, household_id)
        self.claims.clear_person_claims(dead_id)
        estate = self.estates.create_suspense_estate(
            dead_id,
            estate_net_worth,
            tick,
            household_id=household_id,
        )
        estate.net_worth = 0.0
        estate.cleared = True
        if self.econ is not None:
            # the claim package just moved to heirs: this IS the inheritance flow (the metric
            # existed since v13 phase 1 but nothing ever wrote it)
            self.econ._inheritance_flow = getattr(self.econ, "_inheritance_flow", 0.0) + estate_net_worth
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
            have_ledger = getattr(self.econ, "ledger", None) is not None
            if cash > 0.0 and src_account != dst_account and have_ledger:
                # An estate distributes what the account actually holds at administration
                # time. The unbacked part of this share is typically an INTRA-HOUSEHOLD IOU
                # (e.g. a guardian's negative claim charged for the children's keep): it is
                # uncollectable by outside heirs, so it dies with the deceased and the
                # household debtors are forgiven the same amount -- both legs of the IOU
                # extinguish together and the household identity is unchanged. Cohabitants'
                # own positive claims stay protected.
                protected = self._other_positive_cash_claims(src_person_id, src_sheet.household_id)
                available = max(0.0, float(self.econ.ledger.balance(src_account)) - protected)
                moved_cash = min(cash, available)
                shortfall = cash - moved_cash
                if shortfall > 0.0:
                    self._extinguish_intra_household_iou(src_person_id, src_sheet.household_id, shortfall)
                src_sheet.cash_claim -= cash
                dst_sheet.cash_claim += moved_cash
                if moved_cash > 0.0:
                    self.econ.ledger.transfer(src_account, dst_account, moved_cash)
            elif cash < 0.0 and src_account != dst_account and have_ledger:
                # Flavor 7 (the mirror): inheriting a NEGATIVE claim means the heir owes the
                # deceased's household the equalizing payment. A penniless heir cannot back
                # it -- the ten-year acceptance run died here on an A4 OverdraftError (heir
                # balance 0.11 vs 4.89 owed). Collect what the heir's account holds net of
                # the cohabitants' protected claims; the uncollectable remainder stays on the
                # dead sheet as a residual negative claim and is absorbed inside the source
                # household by the caller (it dies with the deceased, like every other
                # intra-household IOU no outsider can settle).
                owed = -cash
                protected = self._other_positive_cash_claims(dst_person_id, dst_sheet.household_id)
                available = max(0.0, float(self.econ.ledger.balance(dst_account)) - protected)
                moved = min(owed, available)
                src_sheet.cash_claim += moved
                dst_sheet.cash_claim -= moved
                if moved > 0.0:
                    self.econ.ledger.transfer(dst_account, src_account, moved)
            else:
                # same account (or no ledger): a pure claim relabeling, always backable
                src_sheet.cash_claim -= cash
                dst_sheet.cash_claim += cash

        debt = float(package["debt"]) * fraction
        if debt:
            src_sheet.debt_claim -= debt
            dst_sheet.debt_claim += debt
            if src_account != dst_account and hasattr(self.econ.ledger, "transfer_debt"):
                self.econ.ledger.transfer_debt(src_account, dst_account, debt)
                # ledger debt just left the source account: the source agent's margin_debt
                # shadow must follow, or a later margin call writes off more than the ledger
                # carries (the seed-5 crash at t2519)
                self._clamp_margin_debt_shadow(src_account)

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
            result = dissolve_marriage(contract, self.claims, reason="death")
            self._apply_dissolution_transfers(result)
            if contract_key is not None:
                self.marriage_contracts.pop(contract_key, None)
        else:
            person = self._person_by_id(person_id)
            spouse_id = getattr(person, "partner_id", None) if person is not None else None
        spouse = self._person_by_id(int(spouse_id)) if spouse_id is not None else None
        if spouse is None or not getattr(spouse, "alive", True):
            return None
        return int(spouse_id)

    def administer_estates(self, tick: int, *, probate_window: int = 365, sweep_interval: int = 30) -> None:
        """Periodic probate administration -- the channel that was designed but never wired.

        Parked suspense estates (heirless, cash-only deaths -- mostly genesis people whose
        kinship links do not exist) previously sat in `estate_suspense` forever, a monotone
        money leak that reached 32% of broad money at the 10k x 3650t scale. Heirs cannot
        appear after death, so past the probate window the estate passes to the state
        (bona vacantia), mirroring the securities-estate escheat branch in `on_death`.

        The same sweep administers economic households with no living claimants (frozen
        debt/deposit zombies) and reconciles per-household cash claims against the ledger
        so one-off claim drift heals instead of alarming every tick until the end of the run.
        """
        econ = self.econ
        if econ is None or getattr(econ, "ledger", None) is None:
            return
        for record in self.estates.uncleared_records():
            if record.net_worth <= 0.0:
                record.cleared = True
                continue
            if tick - record.created_tick >= probate_window:
                self._escheat_estate_record(record)
        if sweep_interval > 0 and tick % sweep_interval == 0:
            self._administer_empty_households()
            self._reconcile_household_claims()
            self._sweep_stranded_dwellings()

    def _escheat_estate_record(self, record: Any) -> None:
        econ = self.econ
        fiscal = getattr(econ, "_fiscal", None)
        household_id = record.household_id
        parked = 0.0
        if household_id is not None:
            parked = max(0.0, float(self.claims.estate_suspense_by_household.get(int(household_id), 0.0)))
        amount = min(float(record.net_worth), parked)
        account_id = self.household_to_account.get(int(household_id)) if household_id is not None else None
        if (
            amount > 0.0
            and account_id is not None
            and fiscal is not None
            and econ.ledger.has_account(account_id)
            and econ.ledger.has_account(fiscal)
        ):
            amount = min(amount, max(0.0, float(econ.ledger.balance(account_id))))
            if amount > 0.0:
                econ.ledger.transfer(account_id, fiscal, amount)
                econ._escheat_flow = getattr(econ, "_escheat_flow", 0.0) + amount
        if household_id is not None and amount > 0.0:
            self.claims.clear_estate_suspense(amount, household_id=int(household_id))
        record.net_worth = 0.0
        record.cleared = True

    def _administer_empty_households(self) -> None:
        """Write off the debt and escheat the free cash of economic households whose
        demographic members are all dead. Without this, a household whose last member died
        while carrying margin debt freezes as a permanent negative-net-worth zombie."""
        econ = self.econ
        fiscal = getattr(econ, "_fiscal", None)
        for h in list(getattr(econ, "households", [])):
            household_id = self.account_to_household.get(h.id)
            if household_id is None:
                continue
            if self.claims.members_of_household(int(household_id)):
                continue
            account_id = h.id
            if not econ.ledger.has_account(account_id):
                continue
            debt = float(econ.ledger.debt(account_id))
            if debt > 0.0:
                repay = min(debt, max(0.0, float(econ.ledger.balance(account_id))))
                if repay > 0.0:
                    econ.ledger.repay(account_id, repay)
                residual = float(econ.ledger.debt(account_id))
                if residual > 0.0:
                    bank_id = self._creditor_bank_for_person(-1, int(household_id))
                    if bank_id is not None:
                        econ.ledger.write_off(account_id, bank_id, residual)
                        self._clamp_margin_debt_shadow(account_id)
            suspense = max(0.0, float(self.claims.estate_suspense_by_household.get(int(household_id), 0.0)))
            free_cash = max(0.0, float(econ.ledger.balance(account_id)) - suspense)
            if free_cash > 0.0 and fiscal is not None and econ.ledger.has_account(fiscal):
                econ.ledger.transfer(account_id, fiscal, free_cash)
                econ._escheat_flow = getattr(econ, "_escheat_flow", 0.0) + free_cash
            housing = getattr(econ, "housing", None)
            if housing is not None and fiscal is not None:
                market = getattr(econ, "housing_market", None)
                if market is not None:
                    # v15.1: probate SALE -- the dwelling is listed (forced) with the empty
                    # account as seller; sale proceeds escheat at the moment of sale. Deaths
                    # become the market's involuntary supply floor.
                    for dwelling in housing.dwellings_of(account_id):
                        market.list_dwelling(econ, dwelling.id, account_id, forced=True)
                else:
                    # v15.0 stopgap: bona-vacantia dwellings escheat in kind
                    moved = housing.transfer_all(account_id, fiscal)
                    if moved:
                        econ._escheat_dwellings = getattr(econ, "_escheat_dwellings", 0) + moved

    def _reconcile_household_claims(self) -> None:
        econ = self.econ
        total_adjusted = 0.0
        for h in getattr(econ, "households", []):
            household_id = self.account_to_household.get(h.id)
            if household_id is None or not econ.ledger.has_account(h.id):
                continue
            suspense = max(0.0, float(self.claims.estate_suspense_by_household.get(int(household_id), 0.0)))
            target = float(econ.ledger.balance(h.id)) - suspense
            total_adjusted += self.claims.reconcile_household_cash(int(household_id), target)
        if total_adjusted > 0.0:
            econ._claim_reconciled_flow = getattr(econ, "_claim_reconciled_flow", 0.0) + total_adjusted

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
        self.econ._inheritance_flow = getattr(self.econ, "_inheritance_flow", 0.0) + sum(payments.values())
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

    bridge.refresh_people_index()        # genesis state is final here; spouse lookups below are O(1)
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
