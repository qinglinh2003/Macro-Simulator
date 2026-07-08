"""Age-specific stable-union targets for demographic relationship anchoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class UnionAgeBand:
    start: int
    end: int
    target_share: float

    @property
    def label(self) -> str:
        return f"{self.start}-{self.end}"

    def contains(self, age: int) -> bool:
        return self.start <= age <= self.end


@dataclass(frozen=True)
class UnionTargetProfile:
    name: str
    bands: tuple[UnionAgeBand, ...]

    def band_for_age(self, age: int) -> UnionAgeBand | None:
        for band in self.bands:
            if band.contains(age):
                return band
        return None

    def target_share(self, age: int) -> float:
        band = self.band_for_age(age)
        return 0.0 if band is None else band.target_share


MEDIUM_FAMILY_FORMATION_PROFILE = UnionTargetProfile(
    name="medium_family_formation",
    bands=(
        UnionAgeBand(18, 24, 0.10),
        UnionAgeBand(25, 34, 0.58),
        UnionAgeBand(35, 49, 0.74),
        UnionAgeBand(50, 64, 0.68),
        UnionAgeBand(65, 74, 0.55),
        UnionAgeBand(75, 100, 0.32),
    ),
)


def partnered_share_by_band(people: Iterable[object], profile: UnionTargetProfile) -> dict[str, float]:
    shares: dict[str, float] = {}
    people_list = list(people)
    for band in profile.bands:
        band_people = [
            person
            for person in people_list
            if getattr(person, "alive", True)
            and band.contains(int(getattr(person, "age")))
        ]
        if not band_people:
            continue
        partnered = sum(1 for person in band_people if getattr(person, "partner_id", None) is not None)
        shares[band.label] = float(partnered / len(band_people))
    return shares
