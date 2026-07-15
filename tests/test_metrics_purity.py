from __future__ import annotations

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.reporting.metrics import compute_tick_metrics
from macro_sim.systems.deprivation import DeprivationSignal


_MISSING = object()


def _deprivation_state(signal: DeprivationSignal | None):
    if signal is None:
        return None
    return (
        signal.basket_cost0,
        signal.price_ref,
        signal.year,
        signal.years_completed,
        signal._per_unit_sum,
        signal._hh_days,
        signal._price_sum,
        signal._price_days,
        tuple(sorted(signal._prev_cum.items())),
        tuple(sorted((hid, tuple(days)) for hid, days in signal._spells.items())),
        signal.boundary_breached,
    )


def _rng_states(econ: Economy):
    states = []
    for name, value in vars(econ).items():
        getstate = getattr(value, "getstate", None)
        if callable(getstate):
            states.append((name, getstate()))
    if econ.demographic_kernel is not None:
        states.append((
            "demographic_kernel.rng",
            repr(econ.demographic_kernel.rng.bit_generator.state),
        ))
    return tuple(states)


def _metric_transition_state(econ: Economy):
    attrs = (
        "_prev_price_index",
        "_cpi_prev_nec",
        "_cpi_prev_lux",
        "_prev_tax_total",
        "_prev_benefit",
        "_prev_nominal_output",
        "_prev_u",
        "_energy_prev_stock_total",
        "_prev_headline_index",
        "_prev_inflation",
        "_prev_real_output",
        "_prev_avg_wage",
        "_price_level",
    )
    return (
        tuple((name, getattr(econ, name, _MISSING)) for name in attrs),
        tuple(getattr(econ, "_price_index_history", ())),
        _deprivation_state(econ.deprivation_signal),
        _rng_states(econ),
        tuple(sorted(econ.ledger.snapshot().items(), key=lambda item: str(item[0]))),
        len(econ.records),
    )


def _full_observation_economy() -> Economy:
    return Economy(Config.v13(
        seed=4,
        n_ticks=4,
        n_households=20,
        demographics_population=60,
        n_firms_c=8,
        n_firms_k=4,
        n_banks=2,
        housing_enabled=True,
        housing_market_enabled=True,
        mortgage_enabled=True,
        housing_rental_enabled=True,
        housing_construction_enabled=True,
        energy_enabled=True,
        energy_household=True,
        consumption_strata=True,
        deprivation_gauges=True,
        deprivation_burnin_years=1,
        cb_log_inflation=True,
    ))


def test_compute_tick_metrics_is_repeatable_and_does_not_advance_state_or_rng():
    econ = _full_observation_economy()
    for _ in range(4):
        econ.step()

    # These two read caches used to be populated indirectly by the metric function.
    econ._bond_valuation_cache = None
    econ.demographic_bridge._household_profiles_cache = None
    before = _metric_transition_state(econ)

    first = compute_tick_metrics(econ)
    middle = _metric_transition_state(econ)
    second = compute_tick_metrics(econ)
    after = _metric_transition_state(econ)

    assert first == second
    assert before == middle == after
    assert econ._bond_valuation_cache is None
    assert econ.demographic_bridge._household_profiles_cache is None


def test_economy_step_commits_metric_histories_once_even_after_extra_reads():
    econ = _full_observation_economy()
    assert not hasattr(econ, "_price_index_history")

    econ.step()
    assert len(econ._price_index_history) == 1
    dep_days = econ.deprivation_signal._hh_days
    dep_prev = tuple(sorted(econ.deprivation_signal._prev_cum.items()))

    compute_tick_metrics(econ)
    compute_tick_metrics(econ)
    assert len(econ._price_index_history) == 1
    assert econ.deprivation_signal._hh_days == dep_days
    assert tuple(sorted(econ.deprivation_signal._prev_cum.items())) == dep_prev

    econ.step()
    assert len(econ._price_index_history) == 2


def test_deprivation_preview_matches_commit_without_mutating_signal():
    signal = DeprivationSignal(
        subsistence_share=0.5,
        burnin_years=0,
        acute_days=1,
        chronic_days=1,
    )
    observations = [
        (0, [(1, 10, 1.0, 0.0, 40, 0.0, 0.0)]),
        (1, [(1, 10, 1.0, 10.0, 41, 0.0, 0.0)]),
        (2, [(1, 10, 1.0, 10.0, 42, 0.0, 0.0)]),
    ]

    for year, persons in observations:
        before = _deprivation_state(signal)
        first = signal.preview(year=year, price_index=1.0, persons=persons)
        second = signal.preview(year=year, price_index=1.0, persons=persons)
        assert first == second
        assert _deprivation_state(signal) == before
        assert signal.observe(year=year, price_index=1.0, persons=persons) == first

    assert signal.boundary_breached


def test_retained_total_aggregates_distributable_income_before_firm_losses():
    econ = Economy(Config.v13(
        seed=9,
        n_ticks=1,
        n_households=10,
        n_firms_c=2,
        n_firms_k=1,
        n_banks=1,
    ))
    econ.step()
    first, second, third = econ.firms
    first.profit = 10.0
    second.profit = -20.0
    third.profit = 0.0
    econ._dividends_paid = 5.0

    record = compute_tick_metrics(econ)

    assert record["profit_total"] == -10.0
    assert record["retained_total"] == 5.0
