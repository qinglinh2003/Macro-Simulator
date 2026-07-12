"""v15.0 housing registry: title, not money.

A dwelling is a REAL asset: it lives in this registry, never in the money ledger.
Transactions (v15.1+) couple a ledger transfer with a title change atomically; price
revaluation touches neither. The registry enforces the two stock invariants the plan
hard-gates per tick:

  - every dwelling has exactly one owner (the owner index is a partition);
  - dwellings are never created or destroyed outside mint() (construction, v15.4)
    -- transfers conserve the count.

Owners are ledger account ids (household accounts, or the fiscal account for
escheated bona-vacantia dwellings). v15.0 ships the registry with a FROZEN price and
zero market: stock integrity before flows.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Dwelling:
    id: int
    owner: str
    units: float = 1.0   # size scalar; stays 1.0 until the v15.2-end size gate opens


@dataclass
class HousingRegistry:
    dwellings: dict[int, Dwelling] = field(default_factory=dict)
    _by_owner: dict[str, set[int]] = field(default_factory=dict)
    _next_id: int = 0
    minted: int = 0

    def mint(self, owner: str, units: float = 1.0) -> Dwelling:
        dwelling = Dwelling(id=self._next_id, owner=owner, units=float(units))
        self._next_id += 1
        self.minted += 1
        self.dwellings[dwelling.id] = dwelling
        self._by_owner.setdefault(owner, set()).add(dwelling.id)
        return dwelling

    def transfer(self, dwelling_id: int, new_owner: str) -> None:
        dwelling = self.dwellings[dwelling_id]
        old = self._by_owner.get(dwelling.owner)
        if old is not None:
            old.discard(dwelling.id)
            if not old:
                del self._by_owner[dwelling.owner]
        dwelling.owner = new_owner
        self._by_owner.setdefault(new_owner, set()).add(dwelling.id)

    def transfer_all(self, old_owner: str, new_owner: str) -> int:
        """Move every dwelling of old_owner (household merge sweep / escheat). Returns count."""
        ids = list(self._by_owner.get(old_owner, ()))
        for dwelling_id in ids:
            self.transfer(dwelling_id, new_owner)
        return len(ids)

    def owner_of(self, dwelling_id: int) -> str:
        return self.dwellings[dwelling_id].owner

    def dwellings_of(self, owner: str) -> list[Dwelling]:
        return [self.dwellings[i] for i in sorted(self._by_owner.get(owner, ()))]

    def units_of(self, owner: str) -> float:
        return sum(d.units for d in self.dwellings_of(owner))

    def count(self) -> int:
        return len(self.dwellings)

    def owners(self) -> list[str]:
        return sorted(self._by_owner)

    def assert_invariants(self) -> None:
        indexed = 0
        for owner, ids in self._by_owner.items():
            assert ids, f"housing registry: empty owner bucket {owner!r}"
            for dwelling_id in ids:
                dwelling = self.dwellings.get(dwelling_id)
                assert dwelling is not None, f"housing registry: indexed dwelling {dwelling_id} missing"
                assert dwelling.owner == owner, (
                    f"housing registry: dwelling {dwelling_id} owner {dwelling.owner!r} != index {owner!r}"
                )
            indexed += len(ids)
        assert indexed == len(self.dwellings), (
            f"housing registry: owner index covers {indexed} of {len(self.dwellings)} dwellings"
        )
        assert len(self.dwellings) == self.minted, (
            f"housing registry: {len(self.dwellings)} dwellings vs {self.minted} minted -- "
            "dwellings must never be created or destroyed outside mint()"
        )
