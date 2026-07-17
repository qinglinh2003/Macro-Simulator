"""v24 portrait finding A1: the rental one-way ratchet.

Legacy rule: ANY unfilled vacancy cuts the rent multiplicatively -- under any
structural surplus the rent decays to zero, kills the rental yield, and takes
the investors' house-price anchor down with it (house prices /750 across all
six 30y-portrait economies, including India whose adult population GREW 13%
against a frozen dwelling stock with 14% vacancies). Fix: frictional-vacancy
deadband + wage-anchored absolute floor, both default-off."""
from __future__ import annotations

import random

from macro_sim.config import Config
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.economy import Economy
from macro_sim.housing.rental import RentalMarket


class _Dwelling:
    def __init__(self, did):
        self.id = did


class _Household:
    def __init__(self, hid, income=1000.0):
        self.id = hid
        self.income_realized = income


class _Housing:
    def __init__(self, owns):
        self.owns = owns                       # hid -> [dwellings]
    def dwellings_of(self, hid):
        return self.owns.get(hid, [])
    def owner_of(self, did):
        for hid, ds in self.owns.items():
            if any(d.id == did for d in ds):
                return hid
        return None


class _Ledger:
    def balance(self, hid):
        return 1.0e6


class _Econ:
    def __init__(self, n_extras, n_seekers):
        landlord = _Household("L", income=1e6)
        seekers = [_Household(f"S{i}") for i in range(n_seekers)]
        self.households = [landlord] + seekers
        self.housing = _Housing({"L": [_Dwelling(0)] + [_Dwelling(i + 1) for i in range(n_extras)]})
        self.housing_market = None
        self.ledger = _Ledger()
        self.rng = random.Random(3)
        self.demographic_bridge = None


def _market(**over):
    m = RentalMarket(rent_level=0.12, rent_adjust=0.5)
    for k, v in over.items():
        setattr(m, k, v)
    return m


def test_legacy_any_vacancy_ratchets_rent_down():
    m = _market()                                   # deadband 0 = legacy
    m.match_tenants(_Econ(n_extras=10, n_seekers=5))   # 5 rented, 5 left vacant
    assert m.rent_level == 0.12 * 0.5               # cut -- and nothing stops it at zero


def test_deadband_treats_frictional_vacancy_as_no_signal():
    m = _market(vacancy_deadband=0.15)
    m.match_tenants(_Econ(n_extras=10, n_seekers=9))    # 9 rented, 1 vacant: 10% <= 15%
    assert m.rent_level == 0.12                     # no cut (legacy would have cut)


def test_floor_stops_the_decay():
    m = _market(vacancy_deadband=0.15, rent_floor=0.10)
    m.match_tenants(_Econ(n_extras=10, n_seekers=5))    # 50% vacancy >> deadband: cut...
    assert m.rent_level == 0.10                     # ...but the wage-anchored floor holds


def test_defaults_off_and_frontier_opt_in():
    cfg = Config.v13(seed=1, n_ticks=5)
    assert cfg.rental_vacancy_deadband == 0.0
    assert cfg.rental_rent_floor_wage_share == 0.0
    assert FULL_FRONTIER_FLAGS["rental_vacancy_deadband"] == 0.15
    assert FULL_FRONTIER_FLAGS["rental_rent_floor_wage_share"] == 0.02


def test_frontier_smoke_runs_with_rental_fix():
    params = dict(FULL_FRONTIER_FLAGS)
    params.update(seed=7, n_households=30, demographics_population=200, n_firms_c=20,
                  n_firms_k=10, n_banks=2, n_ticks=200)
    econ = Economy(Config.v13(**params))
    for _ in range(200):
        econ.step()
    assert econ.rental_market.rent_level >= 0.02 * econ.cfg.w_firm0 - 1e-12
