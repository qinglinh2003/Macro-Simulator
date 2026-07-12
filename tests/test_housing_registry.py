"""v15.0: housing registry, genesis endowment, and title flow through household events.

Stock integrity before flows: no market exists yet, so these tests cover the registry
invariants, the genesis allocation, and the two title fault lines identified in design
review -- the marriage-merge orphan sweep and the empty-household escheat.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.housing import HousingRegistry


# ---------------------------------------------------------------------------
# pure registry
# ---------------------------------------------------------------------------

def test_registry_mint_transfer_invariants():
    reg = HousingRegistry()
    a = reg.mint("H1")
    b = reg.mint("H2", units=2.0)
    reg.assert_invariants()
    assert reg.count() == 2
    assert reg.owner_of(a.id) == "H1"
    assert reg.units_of("H2") == 2.0

    reg.transfer(a.id, "H2")
    reg.assert_invariants()
    assert reg.owner_of(a.id) == "H2"
    assert reg.dwellings_of("H1") == []
    assert len(reg.dwellings_of("H2")) == 2
    assert reg.count() == 2                    # transfers conserve the count

    moved = reg.transfer_all("H2", "GOV")
    reg.assert_invariants()
    assert moved == 2
    assert reg.units_of("GOV") == 3.0
    assert b.owner == "GOV"


def test_registry_invariant_catches_corruption():
    reg = HousingRegistry()
    d = reg.mint("H1")
    d.owner = "H2"                             # bypass transfer(): index now stale
    with pytest.raises(AssertionError, match="owner"):
        reg.assert_invariants()


# ---------------------------------------------------------------------------
# economy integration
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def housing_econ():
    cfg = Config.v13(
        seed=5,
        n_households=60,
        n_firms_c=60,
        n_firms_k=30,
        n_banks=2,
        demographics_population=600,
        n_ticks=40,
        housing_enabled=True,
    )
    econ = Economy(cfg)
    # demographics expands econ.households to the demographic household count;
    # genesis mints exactly one dwelling per (post-expansion) genesis household
    econ._genesis_household_count = len(econ.households)
    assert econ.housing.count() == econ._genesis_household_count
    for _ in range(40):
        econ.step()
    return econ


def test_genesis_one_dwelling_per_household(housing_econ):
    econ = housing_econ
    # count conserved through 40 ticks even as NEW households form houseless
    assert econ.housing.count() == econ._genesis_household_count
    assert len(econ.households) >= econ._genesis_household_count
    assert econ._house_price == pytest.approx(3.5 * 365.0)


def test_registry_invariants_hold_through_simulation(housing_econ):
    housing_econ.housing.assert_invariants()   # also asserted every tick inside step()


def test_marriage_merge_sweeps_dwelling_title(housing_econ):
    econ = housing_econ
    # every genesis household owns >= 1 dwelling unless its account was orphaned by a
    # merge -- in which case the sweep must have moved the title, never dropped it
    total_owned = sum(len(econ.housing.dwellings_of(h.id)) for h in econ.households)
    fiscal_owned = len(econ.housing.dwellings_of(econ._fiscal))
    assert total_owned + fiscal_owned == econ.housing.count()


def test_empty_household_dwellings_escheat_to_fiscal():
    cfg = Config.v13(
        seed=9,
        n_households=40,
        n_firms_c=40,
        n_firms_k=20,
        n_banks=2,
        demographics_population=400,
        n_ticks=10,
        housing_enabled=True,
    )
    econ = Economy(cfg)
    for _ in range(5):
        econ.step()
    bridge = econ.demographic_bridge
    target = econ.households[0]
    other = econ.households[1]
    household_id = bridge.household_id_for_account(target.id)
    other_id = bridge.household_id_for_account(other.id)
    # empty the household at the claims-membership level (the source of truth the
    # administration sweep reads), then run the sweep directly
    for person_id in list(bridge.claims.members_of_household(household_id)):
        bridge.claims.set_household(person_id, other_id)
    assert not bridge.claims.members_of_household(household_id)
    before = len(econ.housing.dwellings_of(econ._fiscal))
    bridge._administer_empty_households()
    after = len(econ.housing.dwellings_of(econ._fiscal))
    assert after >= before + 1                 # the empty household's dwelling escheated
    assert econ.housing.dwellings_of(target.id) == []
    econ.housing.assert_invariants()


def test_housing_disabled_leaves_no_trace():
    cfg = Config.v13(
        seed=5,
        n_households=30,
        n_firms_c=30,
        n_firms_k=15,
        n_banks=2,
        demographics_population=300,
        n_ticks=5,
    )
    econ = Economy(cfg)
    assert econ.housing is None
    for _ in range(5):
        econ.step()
    assert "dwellings_total" not in econ.records[-1]
