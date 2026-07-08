"""Marriage-property accounting for Phase 1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from macro_sim.demographics.economic_state import PersonClaimLedger


@dataclass
class MarriageContract:
    spouse_a_id: int
    spouse_b_id: int
    household_id: int
    start_tick: int
    start_date: date
    basis_by_person: dict[int, float]

    @property
    def spouse_ids(self) -> tuple[int, int]:
        return (self.spouse_a_id, self.spouse_b_id)


@dataclass
class DissolutionResult:
    reason: str
    transfers: list[tuple[int, int, float]] = field(default_factory=list)
    target_net_worth: dict[int, float] = field(default_factory=dict)


def record_marriage_contract(event, claims: PersonClaimLedger) -> MarriageContract:
    spouse_a_id = int(event.spouse_a_id)
    spouse_b_id = int(event.spouse_b_id)
    return MarriageContract(
        spouse_a_id=spouse_a_id,
        spouse_b_id=spouse_b_id,
        household_id=int(event.household_id),
        start_tick=int(event.tick),
        start_date=event.date,
        basis_by_person={
            spouse_a_id: claims.net_worth(spouse_a_id),
            spouse_b_id: claims.net_worth(spouse_b_id),
        },
    )


def dissolve_marriage(
    contract: MarriageContract,
    claims: PersonClaimLedger,
    *,
    reason: Literal["divorce", "death"],
) -> DissolutionResult:
    a, b = contract.spouse_ids
    current = {a: claims.net_worth(a), b: claims.net_worth(b)}
    gains = {
        person_id: current[person_id] - contract.basis_by_person.get(person_id, 0.0)
        for person_id in (a, b)
    }
    target_gain = (gains[a] + gains[b]) / 2.0
    targets = {
        person_id: contract.basis_by_person.get(person_id, 0.0) + target_gain
        for person_id in (a, b)
    }
    result = DissolutionResult(reason=reason, target_net_worth=dict(targets))

    excess_a = current[a] - targets[a]
    if excess_a > 1e-9:
        claims.transfer_cash_claim(a, b, excess_a)
        result.transfers.append((a, b, excess_a))
    elif excess_a < -1e-9:
        amount = -excess_a
        claims.transfer_cash_claim(b, a, amount)
        result.transfers.append((b, a, amount))
    return result
