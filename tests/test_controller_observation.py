from __future__ import annotations

from types import SimpleNamespace

import pytest

from macro_sim.controllers.observation import (
    InstitutionObservation,
    ObjectiveEvaluator,
    ObjectiveSpec,
    ObjectiveTerm,
    ObservationFieldSpec,
    ObservationSpec,
    ReleaseService,
)


def _economy_records(values, key="x"):
    return SimpleNamespace(records=[{"t": tick, key: value} for tick, value in enumerate(values)])


def test_release_lag_and_boundary_gate_use_only_completed_rows():
    # The engine is deliberately already simulated into the future.  A historical
    # observation still may not see those later rows.
    econ = _economy_records([10.0, 20.0, 9999.0])
    spec = ObservationSpec((
        ObservationFieldSpec(
            "x", "x", publication_lag_ticks=2,
        ),
    ))
    service = ReleaseService(spec)

    before = service.observe(econ, 2)
    assert before.release("x").missing_reason == "not_released"

    at_release = service.observe(econ, 3)
    release = at_release.release("x")
    assert release.value == 10.0
    assert release.reference_start_tick == release.reference_end_tick == 0
    assert release.released_at_tick == 3
    assert all(item.released_at_tick <= at_release.boundary_tick for item in at_release.releases)


def test_periodic_and_rolling_releases_do_not_leak_unfinished_period():
    econ = _economy_records([1.0, 2.0, 3.0, 100.0, 200.0, 9999.0])
    spec = ObservationSpec((
        ObservationFieldSpec(
            "quarter", "x", aggregation="mean", window_ticks=3,
            frequency_ticks=3,
        ),
        ObservationFieldSpec(
            "rolling3", "x", aggregation="mean", window_ticks=3,
            frequency_ticks=1,
        ),
    ))
    service = ReleaseService(spec)

    boundary3 = service.observe(econ, 3)
    assert boundary3.release("quarter").value == pytest.approx(2.0)
    assert boundary3.release("rolling3").value == pytest.approx(2.0)
    assert boundary3.release("quarter").reference_end_tick == 2

    # Ticks 3 and 4 are complete now, but the next three-tick period is not.
    # The quarterly release must remain the immutable 0..2 vintage.
    boundary5 = service.observe(econ, 5)
    assert boundary5.release("quarter").value == pytest.approx(2.0)
    assert boundary5.release("quarter").reference_end_tick == 2
    # A true rolling series may use the completed 2..4 window, but never tick 5.
    assert boundary5.release("rolling3").value == pytest.approx((3.0 + 100.0 + 200.0) / 3.0)
    assert boundary5.release("rolling3").reference_end_tick == 4


def test_derived_rolling_series_uses_released_vintages_not_raw_truth():
    # A quarterly base series is the only authorized path into the rolling field.
    # Tick 6 is already present in the engine but is not part of a released quarter.
    econ = _economy_records([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 9999.0])
    spec = ObservationSpec((
        ObservationFieldSpec(
            "quarterly_x", "x", aggregation="mean", window_ticks=3,
            frequency_ticks=3,
        ),
        ObservationFieldSpec(
            "two_quarter_average", "quarterly_x", source="release",
            aggregation="mean", window_ticks=6, frequency_ticks=3,
        ),
    ))
    service = ReleaseService(spec)

    assert service.observe(econ, 3).release("two_quarter_average").missing_reason == "warmup"
    released = service.observe(econ, 6).release("two_quarter_average")
    assert released.value == pytest.approx((2.0 + 5.0) / 2.0)
    assert released.reference_start_tick == 0
    assert released.reference_end_tick == 5
    assert 9999.0 not in [item.value for item in service.history(0, "quarterly_x")]


def test_role_access_filters_confidential_operational_and_oracle_values():
    econ = SimpleNamespace(records=[{
        "t": 0, "public": 1.0, "bank_stress": 2.0,
        "reserves": 3.0, "omniscient": 4.0,
    }])
    spec = ObservationSpec((
        ObservationFieldSpec("public", "public"),
        ObservationFieldSpec(
            "bank_stress", "bank_stress", access_class="confidential",
            roles=frozenset({"regulator"}),
        ),
        ObservationFieldSpec(
            "reserves", "reserves", access_class="operational",
            roles=frozenset({"central_bank"}),
        ),
        ObservationFieldSpec(
            "omniscient", "omniscient", access_class="oracle",
        ),
    ))
    service = ReleaseService(spec)

    public = service.observe(econ, 1, role="public")
    assert public.release("public").value == 1.0
    assert public.release("bank_stress").missing_reason == "access_denied"
    assert public.release("reserves").missing_reason == "access_denied"
    assert public.release("omniscient").missing_reason == "access_denied"

    regulator = service.observe(econ, 1, role="regulator")
    assert regulator.release("bank_stress").value == 2.0
    assert regulator.release("reserves").missing_reason == "access_denied"

    central_bank = service.observe(econ, 1, role="central_bank")
    assert central_bank.release("reserves").value == 3.0
    assert central_bank.release("bank_stress").missing_reason == "access_denied"

    with pytest.raises(ValueError, match="observe_oracle"):
        service.observe(econ, 1, role="oracle")
    oracle = service.observe_oracle(econ, 1)
    assert oracle.release("public").value == 1.0
    assert oracle.release("bank_stress").value == 2.0
    assert oracle.release("reserves").value == 3.0
    assert oracle.release("omniscient").value == 4.0


def test_warmup_and_missing_source_are_explicit_not_nan_sentinels():
    econ = SimpleNamespace(records=[{"t": 0, "x": 1.0}, {"t": 1}])
    spec = ObservationSpec((
        ObservationFieldSpec(
            "x2", "x", aggregation="mean", window_ticks=2,
            frequency_ticks=1, require_full_window=True,
        ),
    ))
    service = ReleaseService(spec)

    warmup = service.observe(econ, 1).release("x2")
    assert warmup.value is None
    assert warmup.missing_reason == "warmup"
    assert "NaN" not in warmup.to_json()

    missing = service.observe(econ, 2).release("x2")
    assert missing.value is None
    assert missing.missing_reason == "source_missing"


def test_world_series_selects_only_the_requested_economy():
    e0 = _economy_records([1.0])
    e1 = _economy_records([2.0])
    world = SimpleNamespace(
        economies=[e0, e1],
        world_records=[{"t": 0, "trade_balance": [10.0, -10.0]}],
    )
    spec = ObservationSpec((
        ObservationFieldSpec(
            "trade_balance", "trade_balance", source="world",
            economy_indexed=True,
        ),
    ))
    service = ReleaseService(spec)

    assert service.observe(world, 1, economy_id=0).release("trade_balance").value == 10.0
    assert service.observe(world, 1, economy_id=1).release("trade_balance").value == -10.0


def test_observation_and_spec_json_are_stable_and_field_order_independent():
    econ = SimpleNamespace(records=[{"t": 0, "a": 1.0, "b": 2.0}])
    a = ObservationFieldSpec("a", "a")
    b = ObservationFieldSpec("b", "b")
    left_spec = ObservationSpec((b, a))
    right_spec = ObservationSpec((a, b))

    left = ReleaseService(left_spec).observe(econ, 1, role="treasury")
    right = ReleaseService(right_spec).observe(econ, 1, role="treasury")

    assert left_spec.to_json() == right_spec.to_json()
    assert left.to_json_bytes() == right.to_json_bytes()
    assert left.to_json() == left.to_json()
    assert [release.series_id for release in left.releases] == ["a", "b"]


def test_objective_reward_uses_released_values_and_time_normalized_control_cost():
    econ = SimpleNamespace(records=[{"t": 0, "inflation": 3.0}])
    observation_spec = ObservationSpec((
        ObservationFieldSpec("inflation", "inflation"),
    ))
    observation = ReleaseService(observation_spec).observe(
        econ, 1, role="central_bank", elapsed_ticks=4,
    )
    objective = ObjectiveSpec(
        terms=(ObjectiveTerm(
            "inflation", "target", target_or_bounds=2.0,
            weight=2.0, normalization_scale=1.0,
        ),),
        control_cost_weight=0.5,
        time_normalization="per_tick",
    )
    result = ObjectiveEvaluator(objective, observation_spec).evaluate(
        observation, adjustment_cost=2.0,
    )

    assert result.components["inflation"] == pytest.approx(-2.0)
    assert result.macro_reward == pytest.approx(-2.0)
    assert result.control_cost_penalty == pytest.approx(0.25)
    assert result.total_reward == pytest.approx(-2.25)
    assert result.elapsed_ticks == 4


def test_objective_window_uses_published_vintages_not_hidden_engine_rows():
    econ = _economy_records([1.0, 3.0, 1000.0])
    observation_spec = ObservationSpec((ObservationFieldSpec("x", "x"),))
    releases = ReleaseService(observation_spec)
    releases.observe(econ, 1)
    observation = releases.observe(econ, 2, elapsed_ticks=1)
    objective = ObjectiveSpec((
        ObjectiveTerm("x", "target", 0.0, evaluation_window=2),
    ))
    evaluator = ObjectiveEvaluator(objective, observation_spec)
    result = evaluator.evaluate(
        observation,
        release_history={"x": releases.history(0, "x", as_of_tick=2)},
    )

    # Mean of published values 1 and 3 is 2; the already-present tick-2 row is
    # not released until boundary 3 and must not enter the score.
    assert result.components["x"] == pytest.approx(-4.0)


def test_human_comparable_objective_rejects_oracle_series():
    observation_spec = ObservationSpec((
        ObservationFieldSpec("future_truth", "future_truth", access_class="oracle"),
    ))
    objective = ObjectiveSpec((
        ObjectiveTerm("future_truth", "maximize"),
    ), human_comparable=True)

    with pytest.raises(ValueError, match="oracle"):
        ObjectiveEvaluator(objective, observation_spec)

    # An explicitly labelled oracle-research profile may use it.
    ObjectiveEvaluator(
        ObjectiveSpec((ObjectiveTerm("future_truth", "maximize"),), human_comparable=False),
        observation_spec,
    )


def test_observation_rejects_future_release_even_if_manually_constructed():
    from macro_sim.controllers.observation import Release

    with pytest.raises(ValueError, match="future"):
        InstitutionObservation(
            boundary_tick=3,
            economy_id=0,
            role="public",
            releases=(Release("x", 1.0, 0, 0, released_at_tick=4),),
        )
