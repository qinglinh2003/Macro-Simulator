import math
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from macro_sim.demographics.agents import Person
from macro_sim.demographics.union import MEDIUM_FAMILY_FORMATION_PROFILE, partnered_share_by_band


def test_medium_family_formation_profile_returns_age_specific_union_targets():
    profile = MEDIUM_FAMILY_FORMATION_PROFILE

    assert profile.name == "medium_family_formation"
    assert math.isclose(profile.target_share(18), 0.10)
    assert math.isclose(profile.target_share(28), 0.58)
    assert math.isclose(profile.target_share(42), 0.74)
    assert math.isclose(profile.target_share(58), 0.68)
    assert math.isclose(profile.target_share(70), 0.55)
    assert math.isclose(profile.target_share(80), 0.32)
    assert profile.target_share(17) == 0.0


def test_partnered_share_by_band_measures_live_adults_against_profile_bands():
    people = [
        Person(id=1, age=22, sex="F", birth_date=date(2000, 1, 1), partner_id=2),
        Person(id=2, age=23, sex="M", birth_date=date(1999, 1, 1), partner_id=1),
        Person(id=3, age=27, sex="F", birth_date=date(1995, 1, 1), partner_id=4),
        Person(id=4, age=28, sex="M", birth_date=date(1994, 1, 1), partner_id=3),
        Person(id=5, age=29, sex="F", birth_date=date(1993, 1, 1)),
        Person(id=6, age=10, sex="M", birth_date=date(2012, 1, 1)),
    ]

    shares = partnered_share_by_band(people, MEDIUM_FAMILY_FORMATION_PROFILE)

    assert shares["18-24"] == 1.0
    assert math.isclose(shares["25-34"], 2 / 3)
    assert "0-17" not in shares
