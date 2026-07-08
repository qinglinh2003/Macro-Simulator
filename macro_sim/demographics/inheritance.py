"""Default inheritance rules for Phase 1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from macro_sim.demographics.economic_state import PersonClaimLedger
from macro_sim.demographics.estate import EstateRecord


@dataclass
class HeirDistribution:
    spouse_id: int | None = None
    child_ids: list[int] = field(default_factory=list)
    parent_ids: list[int] = field(default_factory=list)


def _alive(person: Any | None) -> bool:
    return person is not None and bool(getattr(person, "alive", True))


def select_default_heirs(
    dead_person: Any,
    people_by_id: dict[int, Any],
    *,
    spouse_id_override: int | None = None,
) -> HeirDistribution:
    spouse_id = spouse_id_override if spouse_id_override is not None else getattr(dead_person, "partner_id", None)
    if spouse_id is not None and not _alive(people_by_id.get(spouse_id)):
        spouse_id = None

    dead_id = int(dead_person.id)
    child_ids = sorted(
        int(person.id)
        for person in people_by_id.values()
        if _alive(person)
        and (getattr(person, "mother_id", None) == dead_id or getattr(person, "father_id", None) == dead_id)
    )

    parent_ids = []
    for parent_id in (getattr(dead_person, "mother_id", None), getattr(dead_person, "father_id", None)):
        if parent_id is not None and _alive(people_by_id.get(parent_id)):
            parent_ids.append(int(parent_id))

    return HeirDistribution(spouse_id=spouse_id, child_ids=child_ids, parent_ids=parent_ids)


def settle_estate(
    estate: EstateRecord,
    heirs: HeirDistribution,
    claims: PersonClaimLedger,
    inheritance_tax_rate: float = 0.0,
    public_estate_account_id: int | None = None,
) -> dict[int, float]:
    if estate.cleared:
        return {}
    gross = max(0.0, estate.net_worth)
    tax = gross * max(0.0, inheritance_tax_rate)
    distributable = gross - tax

    payments: dict[int, float] = {}
    if heirs.spouse_id is not None and heirs.child_ids:
        payments[int(heirs.spouse_id)] = distributable * 0.5
        child_share = distributable * 0.5 / len(heirs.child_ids)
        for child_id in heirs.child_ids:
            payments[int(child_id)] = payments.get(int(child_id), 0.0) + child_share
    elif heirs.spouse_id is not None:
        payments[int(heirs.spouse_id)] = distributable
    elif heirs.child_ids:
        child_share = distributable / len(heirs.child_ids)
        for child_id in heirs.child_ids:
            payments[int(child_id)] = child_share
    elif heirs.parent_ids:
        parent_share = distributable / len(heirs.parent_ids)
        for parent_id in heirs.parent_ids:
            payments[int(parent_id)] = parent_share
    elif public_estate_account_id is not None:
        payments[int(public_estate_account_id)] = distributable

    for person_id, amount in payments.items():
        claims.credit_cash(person_id, amount, household_id=-1)
    claims.clear_estate_suspense(gross, household_id=estate.household_id)
    estate.net_worth = 0.0
    estate.cleared = True
    return payments
