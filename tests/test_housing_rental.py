"""v15.3: rental market -- tenancy flows, tenure choice, emergent landlords.

Tenancies are persistent contracts paying per-tick rent through the person-claim
layer; endings are enforced by the per-session sweep (tenant purchase, landlord title
loss, death, forced listing). Landlords emerge from yield arbitrage, cash-only.
"""

from __future__ import annotations

import pytest

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.housing.rental import Tenancy


def make_econ(**overrides):
    params = dict(
        seed=13,
        n_households=50,
        n_firms_c=50,
        n_firms_k=25,
        n_banks=2,
        demographics_population=500,
        n_ticks=400,
        housing_enabled=True,
        housing_market_enabled=True,
        housing_rental_enabled=True,
    )
    params.update(overrides)
    return Economy(Config.v13(**params))


def force_vacancy(econ) -> int:
    """Give household[1] a second dwelling by transferring household[0]'s home
    (registry-level move; claims untouched -- dwellings are real assets). Returns the
    dwelling the vacancy rule will actually offer: the landlord's home is their FIRST
    owned dwelling by id, so the rentable unit is the second."""
    donor, landlord = econ.households[0], econ.households[1]
    dwelling = econ.housing.dwellings_of(donor.id)[0]
    econ.housing.transfer(dwelling.id, landlord.id)
    return econ.housing.dwellings_of(landlord.id)[1].id


def test_tenancy_forms_and_rent_flows_with_claims_consistent():
    econ = make_econ()
    for _ in range(3):
        econ.step()
    dwelling_id = force_vacancy(econ)
    landlord = econ.housing.owner_of(dwelling_id)
    # run to the next session so the houseless donor household matches as tenant
    tenant_found = None
    for _ in range(65):
        econ.step()                      # claim gates assert every tick: rent postings must hold
        if dwelling_id in econ.rental_market.tenancies:
            tenant_found = econ.rental_market.tenancies[dwelling_id].tenant
            break
    assert tenant_found is not None
    t0_paid = econ.rental_market.rent_paid_total
    for _ in range(30):
        econ.step()
    assert econ.rental_market.rent_paid_total > t0_paid          # rent is flowing
    assert econ.ledger.balance(landlord) >= 0.0


def test_tenancy_ends_when_tenant_buys_a_home():
    econ = make_econ(house_price_income_years=0.05)   # cheap: tenants can buy out
    for _ in range(3):
        econ.step()
    dwelling_id = force_vacancy(econ)
    for _ in range(65):
        econ.step()
        if dwelling_id in econ.rental_market.tenancies:
            break
    tenancy = econ.rental_market.tenancies.get(dwelling_id)
    assert tenancy is not None
    tenant = tenancy.tenant
    # hand the tenant a dwelling (simulating a purchase elsewhere); the SWEEP must end
    # their tenancy -- the unit may legitimately RE-LET to a new tenant afterwards
    other = econ.housing.dwellings_of(econ.households[2].id)[0]
    econ.housing.transfer(other.id, tenant)
    for _ in range(31):                                # one session boundary
        econ.step()
    current = econ.rental_market.tenancies.get(dwelling_id)
    assert current is None or current.tenant != tenant


def test_eviction_after_persistent_arrears():
    econ = make_econ()
    for _ in range(3):
        econ.step()
    rental = econ.rental_market
    dwelling_id = force_vacancy(econ)
    for _ in range(65):
        econ.step()
        if dwelling_id in rental.tenancies:
            break
    tenancy = rental.tenancies[dwelling_id]
    evicted_tenant = tenancy.tenant
    # pin the rent unpayably high: arrears accumulate -> eviction (the unit may then
    # legitimately re-let to a fresh tenant at the normal rent level)
    tenancy.rent_per_tick = 1e9
    before = rental.evictions_total
    for _ in range(rental.eviction_arrears + 2):
        econ.step()
    assert rental.evictions_total == before + 1
    current = rental.tenancies.get(dwelling_id)
    assert current is None or current.tenant != evicted_tenant or current.rent_per_tick < 1e9


def test_landlords_emerge_from_yield_arbitrage():
    """Cheap dwellings + pinned high rent level => yield >> deposit rate: housed
    households with cash buy probate listings as investments."""
    econ = make_econ(seed=31, house_price_income_years=0.05)
    for _ in range(3):
        econ.step()
    econ.rental_market.rent_level = 0.5 * econ._house_price * 0.05   # absurd yield, pinned
    bridge = econ.demographic_bridge
    hh0 = int(bridge.household_id_for_account(econ.households[0].id))
    bridge.stratification.mortality_strata[hh0] = 1e5                # probate supply
    landlord_count = 0
    for _ in range(500):
        econ.step()
        landlord_count = sum(
            1 for h in econ.households if len(econ.housing.dwellings_of(h.id)) > 1
        )
        if landlord_count > 0:
            break
    assert landlord_count > 0
    assert econ.housing_market.sales_total >= 1


def test_rent_level_decays_under_vacancy():
    econ = make_econ()
    rental = econ.rental_market
    for _ in range(3):
        econ.step()
    # a vacancy with no affordable seekers: rent level must fall at sessions
    force_vacancy(econ)
    rental.rent_burden_cap = 0.0                       # nobody can afford: pure vacancy
    r0 = rental.rent_level
    for _ in range(95):
        econ.step()
    assert rental.rent_level < r0


def test_rental_off_leaves_no_trace():
    econ = make_econ(housing_rental_enabled=False)
    assert econ.rental_market is None
    for _ in range(35):
        econ.step()
    assert "tenancy_count" not in econ.records[-1]
