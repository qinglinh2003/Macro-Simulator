"""v24 portrait finding A2-root: zombie AFC death-spiral pricing.

A shrinking firm with a large legacy capital stock spreads its FIXED capital
service cost over a vanishing planned output: unit capital cost -> unbounded,
posted price -> ~270x the sector median (Germany portrait, goods:C3 at 396 vs
median 1.48), captive deprivation demand keeps buying, and the chained
fixed-basket CPI explodes. The fix floors the allocation base at a share of the
output the capital was SIZED for (y_ref = K / v)."""
from __future__ import annotations

from macro_sim.behavior import planning as B
from macro_sim.config import Config
from macro_sim.diagnostics.scenarios import FULL_FRONTIER_FLAGS
from macro_sim.economy import Economy


class _FakeFirm:
    tech = "cobb"
    def __init__(self, capital, target):
        self.capital = capital
        self.production_target = target
        self.delta_K = 0.05 / 365.0


def _uc(firm, min_output=0.0):
    return B.capital_service_unit_cost(
        firm, replacement_price=1.0, opportunity_rate=0.0001, min_output=min_output)


def test_unfloored_unit_capital_cost_explodes_as_output_vanishes():
    firm = _FakeFirm(capital=912.5 * 100.0, target=100.0)   # capital sized for y=100 at v=912.5
    healthy = _uc(firm)
    firm.production_target = 0.1                            # demand collapsed 1000x
    dying = _uc(firm)
    assert dying > 900 * healthy                            # the death spiral (unbounded AFC)


def test_min_output_floor_bounds_the_dying_firm_quote():
    v = 912.5
    firm = _FakeFirm(capital=v * 100.0, target=100.0)
    healthy = _uc(firm)
    firm.production_target = 0.1
    floored = _uc(firm, min_output=0.1 * firm.capital / v)  # util floor 0.1 => base >= 10 units
    assert floored <= 10.0 * healthy + 1e-12                # pass-through capped at 1/floor
    # and the floor NEVER binds for a healthy firm (bit-identity above the line)
    firm.production_target = 100.0
    assert _uc(firm, min_output=0.1 * firm.capital / v) == _uc(firm)


def test_flag_default_off_and_frontier_opt_in():
    assert Config.v13(seed=1, n_ticks=5).capital_service_min_utilization == 0.0
    assert FULL_FRONTIER_FLAGS["capital_service_min_utilization"] == 0.1


def test_frontier_smoke_runs_with_floor():
    params = dict(FULL_FRONTIER_FLAGS)
    params.update(seed=7, n_households=30, demographics_population=200, n_firms_c=20,
                  n_firms_k=10, n_banks=2, n_ticks=150)
    econ = Economy(Config.v13(**params))
    for _ in range(150):
        econ.step()          # all conservation/identity gates run inside
    assert econ.t == 150
