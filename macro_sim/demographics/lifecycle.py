"""Lifecycle consumption primitives for demographic-age lifecycle behavior."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from typing import Any


def expected_remaining_life_years(age: int, rates) -> float:
    """Return expected remaining years of life from an integer age.

    Uses the Phase 0 survival probabilities from `rates.survival_curve()` to form
    survival-at-age ratios:

    sum_{s=age}^{omega} l(s) / l(age)

    Pure in (age, rates); rates is a frozen all-scalar dataclass, so the value is
    memoized -- the uncached version rebuilt the full survival curve per call,
    i.e. per household member per tick under lifecycle consumption.
    """

    if age < 0:
        return 0.0
    if age > rates.omega:
        return 0.0
    return _expected_remaining_life_years_cached(age, rates)


@lru_cache(maxsize=65536)
def _expected_remaining_life_years_cached(age: int, rates) -> float:
    survival_probabilities = list(rates.survival_curve())
    expected_len = rates.omega + 1
    survivorship: list[float] = [1.0]
    for prob in survival_probabilities:
        survivorship.append(survivorship[-1] * float(prob))

    if len(survivorship) < expected_len:
        survivorship.extend([0.0] * (expected_len - len(survivorship)))
    if len(survivorship) > expected_len:
        survivorship = survivorship[:expected_len]

    remaining_life = float(survivorship[age])
    if remaining_life <= 0.0:
        return 0.0

    return sum(life / remaining_life for life in survivorship[age:])


def age_income_capacity(age: int, entry_age: int = 18, retire_age: int = 65) -> float:
    """Return the age-specific earning-capacity factor used by lifecycle income.

    Default profile:
    - age < entry_age: 0.0
    - entry_age <= age <= entry_age+7: linear rise from 0.5 to 1.0
    - entry_age+8 <= age <= retire_age-15: 1.0
    - retire_age-14 <= age < retire_age: linear decline to 0.7
    - age >= retire_age: 0.0
    """

    if age < entry_age or age >= retire_age:
        return 0.0

    ramp_up_end = entry_age + 6
    if age <= ramp_up_end:
        return 0.5 + 0.5 * (age - entry_age) / (ramp_up_end - entry_age)

    if age == ramp_up_end + 1:
        return 1.0

    ramp_down_start = retire_age - 14
    if age < ramp_down_start:
        return 1.0

    decline_years = max(retire_age - ramp_down_start - 1, 1)
    raw = 1.0 - 0.3 * (age - ramp_down_start) / decline_years
    return max(0.0, min(1.0, raw))


def person_wealth_draw(
    net_worth: float, remaining_life_years: float, ticks_per_year: int = 365
) -> float:
    """Daily annuitized draw from current net worth over remaining life."""

    non_negative_wealth = max(float(net_worth), 0.0)
    life_years = max(float(remaining_life_years), 0.0)
    denominator = max(life_years * float(ticks_per_year), 1.0)
    return non_negative_wealth / denominator


def person_permanent_income(
    income_ema: float, age: int, entry_age: int = 18, retire_age: int = 65
) -> float:
    """Permanent-income contribution implied by age-dependent capacity."""

    return float(income_ema) * age_income_capacity(age, entry_age=entry_age, retire_age=retire_age)


def _member_id(member: Any) -> int:
    if isinstance(member, int):
        return int(member)
    if hasattr(member, "id"):
        return int(getattr(member, "id"))
    raise TypeError(f"Unsupported member type {type(member)}")


def _person_age(profile: Any, member: Any, claims: Any) -> int:
    if hasattr(member, "age"):
        return int(getattr(member, "age"))

    person_id = _member_id(member)

    for field in (
        "person_ages",
        "member_ages",
        "ages",
        "age_by_member_id",
        "ages_by_id",
    ):
        mapping = getattr(profile, field, None)
        if isinstance(mapping, dict) and person_id in mapping:
            return int(mapping[person_id])

    return _claim_age(claims, person_id)


def _claim_age(claims: Any, person_id: int) -> int:
    for accessor in (getattr(claims, "age", None), getattr(claims, "person_age", None)):
        if accessor is None:
            continue
        if callable(accessor):
            return int(accessor(person_id))
        if isinstance(accessor, dict):
            if person_id in accessor:
                return int(accessor[person_id])
    raise TypeError(f"Cannot read age for person {person_id}")


def _claim_income_ema(claims: Any, person_id: int) -> float:
    # Direct accessor on claims object.
    for name in ("income_ema", "income"):
        accessor = getattr(claims, name, None)
        if accessor is None:
            continue
        if callable(accessor):
            return float(accessor(person_id))
        if isinstance(accessor, dict) and person_id in accessor:
            return float(accessor[person_id])
        break

    # Balance-sheet accessor.
    sheet = getattr(claims, "balance_sheet", None)
    if callable(sheet):
        account = sheet(person_id)
        if hasattr(account, "income_ema"):
            return float(getattr(account, "income_ema"))

    # Direct person record.
    if isinstance(claims, dict) and person_id in claims:
        record = claims[person_id]
        if hasattr(record, "income_ema"):
            return float(getattr(record, "income_ema"))

    return 0.0


def _claim_net_worth(claims: Any, person_id: int) -> float:
    # Direct accessor on claims object.
    accessor = getattr(claims, "net_worth", None)
    if accessor is not None:
        if callable(accessor):
            return float(accessor(person_id))
        if isinstance(accessor, dict) and person_id in accessor:
            return float(accessor[person_id])

    # Balance-sheet accessor.
    sheet = getattr(claims, "balance_sheet", None)
    if callable(sheet):
        account = sheet(person_id)
        if hasattr(account, "net_worth"):
            return float(getattr(account, "net_worth"))
        if hasattr(account, "cash_claim") and hasattr(account, "debt_claim"):
            return float(getattr(account, "cash_claim")) - float(getattr(account, "debt_claim"))

    # Direct person record.
    if isinstance(claims, dict) and person_id in claims:
        record = claims[person_id]
        if hasattr(record, "net_worth"):
            return float(getattr(record, "net_worth"))
        if hasattr(record, "cash_claim") and hasattr(record, "debt_claim"):
            return float(getattr(record, "cash_claim")) - float(getattr(record, "debt_claim"))

    return 0.0


def _iter_household_member_pairs(profile: Any, claims: Any) -> Iterable[tuple[int, int]]:
    members = getattr(profile, "members", None)
    if members is not None:
        for member in members:
            person_id = _member_id(member)
            yield person_id, _person_age(profile, member, claims)
        return

    member_ids = getattr(profile, "member_ids", None)
    if member_ids is not None:
        for person_id in member_ids:
            person_id = int(person_id)
            person_stub = type("obj", (), {"id": person_id})()
            yield person_id, _person_age(profile, person_stub, claims)
        return

    raise TypeError("profile must expose members or member_ids")


def _need_scale(profile: Any) -> float:
    need_units = getattr(profile, "need_units", None)
    if need_units is None:
        return 1.0
    baseline = float(getattr(profile, "adult_equivalent_baseline", 2.0))
    if baseline <= 0.0:
        return 0.0
    return max(0.0, float(need_units) / baseline)


def household_lifecycle_consumption_budget(
    profile: Any,
    claims: Any,
    rates,
    alpha_income: float,
    alpha_wealth_draw: float,
    ticks_per_year: int = 365,
) -> float:
    """Compute household lifecycle consumption budget from members' incomes/wealth.

    Person-level permanent income and wealth draws are summed, then weighted by
    a household need scale.
    """

    member_pairs = list(_iter_household_member_pairs(profile, claims))
    if not member_pairs:
        return 0.0

    income_budget = 0.0
    wealth_draw_budget = 0.0
    for person_id, age in member_pairs:
        income_ema = _claim_income_ema(claims, person_id)
        net_worth = _claim_net_worth(claims, person_id)

        income_budget += person_permanent_income(income_ema, age)
        remaining_life = expected_remaining_life_years(age, rates)
        wealth_draw_budget += person_wealth_draw(
            net_worth,
            remaining_life_years=remaining_life,
            ticks_per_year=ticks_per_year,
        )

    need_scale = _need_scale(profile)
    budget = need_scale * alpha_income * income_budget + alpha_wealth_draw * wealth_draw_budget
    return max(0.0, float(budget))
