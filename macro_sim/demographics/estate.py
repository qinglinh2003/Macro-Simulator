"""Estate suspense records for Phase 1 demographic-economy integration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EstateRecord:
    dead_person_id: int
    net_worth: float
    created_tick: int
    household_id: int | None = None
    cleared: bool = False


class EstateRegistry:
    def __init__(self) -> None:
        self._records: dict[int, EstateRecord] = {}

    def create_suspense_estate(
        self,
        dead_person_id: int,
        net_worth: float,
        created_tick: int,
        household_id: int | None = None,
    ) -> EstateRecord:
        record = EstateRecord(
            dead_person_id=dead_person_id,
            net_worth=max(0.0, float(net_worth)),
            created_tick=int(created_tick),
            household_id=household_id,
        )
        self._records[dead_person_id] = record
        return record

    def estate_for(self, dead_person_id: int) -> EstateRecord:
        return self._records[dead_person_id]

    def total_net_worth(self) -> float:
        return sum(record.net_worth for record in self._records.values() if not record.cleared)

    def uncleared_records(self) -> list[EstateRecord]:
        return [record for record in self._records.values() if not record.cleared]
