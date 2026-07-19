"""Acceptance tests for reproducible RL experiments and baseline claims."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from macro_sim.config import Config
from macro_sim.controllers.gym_adapter import ControllerEnv
from macro_sim.controllers.scheduler import (
    DEFAULT_CALENDARS,
    CalendarSpec,
    DecisionScheduler,
)
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.rl.baselines import (
    HeuristicPolicy,
    PredictModelPolicy,
    RandomMaskedPolicy,
)
from macro_sim.rl.experiment import (
    CallableEnvironmentFactory,
    EpisodeLimitExceeded,
    EvaluationPlan,
    ExperimentSeeds,
    SynchronousEnvironmentBatch,
    evaluate_policies,
    run_episode,
    aggregate_interval_reward,
)
from macro_sim.rl.metrics import (
    SuperiorityRule,
    judge_against_baselines,
    paired_comparison,
    summarize_metric,
)
from macro_sim.world import World


class _TwoStepEnv:
    """Tiny SMDP used to make discounting and seed pairing exactly inspectable."""

    def __init__(self, genesis_seed: int, counter: Counter[int] | None = None):
        self.genesis_seed = genesis_seed
        self.counter = counter
        self.step_index = 0
        self.closed = False

    @staticmethod
    def _info(elapsed_ticks: int = 0) -> dict[str, Any]:
        return {
            "action_dimensions": (("rate", None),),
            "action_mask": np.asarray(((1, 1, 1),), dtype=np.int8),
            "elapsed_ticks": elapsed_ticks,
            "objective_profile": "human_comparable",
        }

    def reset(self, *, seed=None, options=None):
        del options
        assert seed == self.genesis_seed
        self.step_index = 0
        return np.asarray((float(seed), 0.0)), self._info()

    def step(self, action):
        code = 1 if isinstance(action, dict) and not action else int(
            np.asarray(action).reshape(-1)[0]
        )
        reward = float(code - 1)
        elapsed = (2, 3)[self.step_index]
        self.step_index += 1
        truncated = self.step_index == 2
        return (
            np.asarray((float(self.genesis_seed), float(self.step_index))),
            reward,
            False,
            truncated,
            self._info(elapsed),
        )

    def close(self):
        self.closed = True


class _MaskedUpModel:
    def __init__(self):
        self.masks: list[np.ndarray] = []

    def predict(self, observation, *, action_mask, deterministic):
        assert deterministic
        assert np.asarray(observation).ndim == 1
        self.masks.append(np.asarray(action_mask).copy())
        mask = np.asarray(action_mask)
        return np.where(mask[:, 2], 2, 1).astype(np.int64)


class _MasklessModel:
    def predict(self, observation, *, deterministic):
        del observation, deterministic
        return np.asarray((1,), dtype=np.int64)


def test_seed_schedule_is_reproducible_disjoint_and_policy_local():
    first = ExperimentSeeds.generate(9182, training_count=4, evaluation_count=5)
    second = ExperimentSeeds.generate(9182, training_count=4, evaluation_count=5)

    assert first == second
    assert set(first.training).isdisjoint(first.evaluation)
    assert first.policy_seed(first.evaluation[0], "model") == second.policy_seed(
        second.evaluation[0], "model"
    )
    assert first.policy_seed(first.evaluation[0], "model") != first.policy_seed(
        first.evaluation[0], "random"
    )
    with pytest.raises(ValueError, match="must be disjoint"):
        ExperimentSeeds((1, 2), (2, 3))


def test_model_adapter_requires_and_forwards_advisory_action_mask():
    with pytest.raises(TypeError, match="action_mask"):
        PredictModelPolicy(_MasklessModel())

    model = _MaskedUpModel()
    policy = PredictModelPolicy(model)
    environment = _TwoStepEnv(4)
    result = run_episode(
        environment,
        policy,
        policy_name="model",
        environment_seed=4,
        policy_seed=9,
        gamma_per_tick=0.9,
        max_decisions=3,
    )

    assert result.total_reward == pytest.approx(2.0)
    assert result.discounted_return == pytest.approx(1.0 + 0.9 ** 2)
    assert result.reward_per_tick == pytest.approx(1.0)
    assert result.elapsed_ticks == 5
    assert result.decision_steps == 2
    assert result.truncated and not result.terminated
    assert len(model.masks) == 2


def test_complete_paired_matrix_reuses_one_genesis_per_evaluation_seed():
    calls: Counter[int] = Counter()

    def build(seed: int):
        calls[seed] += 1
        return _TwoStepEnv(seed, calls)

    model = _MaskedUpModel()
    policies = {
        "random": RandomMaskedPolicy(change_probability=1.0, max_changes=1),
        "heuristic": HeuristicPolicy("hold"),
        "model": PredictModelPolicy(model),
    }
    seeds = ExperimentSeeds((101, 102), (201, 202, 203, 204), policy_seed_salt=17)
    plan = EvaluationPlan(
        seeds,
        gamma_per_tick=0.9,
        bootstrap_resamples=200,
        max_decisions=3,
    )

    result = evaluate_policies(CallableEnvironmentFactory(build), policies, plan)

    assert calls == Counter({201: 1, 202: 1, 203: 1, 204: 1})
    assert len(result.episodes) == 12
    assert tuple(item.environment_seed for item in result.episodes_for("model")) == (
        201, 202, 203, 204,
    )
    assert result.summary("model", "discounted_return").mean == pytest.approx(
        1.0 + 0.9 ** 2
    )
    verdict = result.judge(
        "model",
        ("heuristic",),
        rule=SuperiorityRule(
            minimum_pairs=4,
            bootstrap_resamples=200,
            minimum_win_rate=1.0,
        ),
    )
    assert verdict.passed
    assert verdict.comparisons["heuristic"].passed


def test_paired_superiority_rule_is_strict_and_familywise_corrected():
    candidate = {seed: 2.0 + seed / 100.0 for seed in range(6)}
    baselines = {
        "heuristic": {seed: 1.0 + seed / 100.0 for seed in range(6)},
        "random": {seed: 0.0 + seed / 100.0 for seed in range(6)},
    }
    rule = SuperiorityRule(
        confidence_level=0.95,
        minimum_effect=0.25,
        minimum_win_rate=0.8,
        minimum_pairs=6,
        bootstrap_resamples=200,
        bootstrap_seed=8,
    )

    verdict = judge_against_baselines(
        candidate,
        baselines,
        candidate_name="model",
        metric="discounted_return",
        rule=rule,
    )

    assert verdict.passed
    assert all(
        item.difference_summary.confidence_interval.level == pytest.approx(0.975)
        for item in verdict.comparisons.values()
    )
    insufficient = paired_comparison(
        {1: 2.0, 2: 2.0},
        {1: 1.0, 2: 1.0},
        candidate_name="model",
        baseline_name="heuristic",
        metric="discounted_return",
        rule=SuperiorityRule(minimum_pairs=3, bootstrap_resamples=100),
    )
    assert not insufficient.passed
    assert "insufficient_pairs" in insufficient.failure_reasons
    with pytest.raises(ValueError, match="identical seeds"):
        paired_comparison(
            {1: 2.0},
            {2: 1.0},
            candidate_name="model",
            baseline_name="heuristic",
            metric="discounted_return",
            rule=rule,
        )


def test_metric_summary_is_finite_and_bootstrap_reproducible():
    first = summarize_metric(
        (1.0, 2.0, 4.0, 8.0), resamples=500, seed=77,
    )
    second = summarize_metric(
        (1.0, 2.0, 4.0, 8.0), resamples=500, seed=77,
    )
    assert first == second
    assert first.mean == pytest.approx(3.75)
    assert first.confidence_interval.lower <= first.mean
    assert first.confidence_interval.upper >= first.mean
    with pytest.raises(ValueError, match="finite"):
        summarize_metric((1.0, np.nan), resamples=100)


def test_synchronous_batch_stacks_transitions_and_requires_reset_after_end():
    with SynchronousEnvironmentBatch(
        CallableEnvironmentFactory(_TwoStepEnv), (11, 12),
    ) as batch:
        initial = batch.reset()
        assert batch.num_envs == 2
        assert initial.observations.shape == (2, 2)
        assert initial.action_masks.shape == (2, 1, 3)
        first = batch.step((np.asarray((2,)), np.asarray((1,))))
        np.testing.assert_allclose(first.rewards, (1.0, 0.0))
        np.testing.assert_array_equal(first.elapsed_ticks, (2, 2))
        assert not np.any(first.truncated)
        second = batch.step((np.asarray((2,)), np.asarray((0,))))
        np.testing.assert_array_equal(second.truncated, (True, True))
        with pytest.raises(RuntimeError, match="reset"):
            batch.step((np.asarray((1,)), np.asarray((1,))))
        reset = batch.reset()
        assert reset.observations.shape == (2, 2)


def test_incomplete_episode_raises_instead_of_publishing_censored_result():
    with pytest.raises(EpisodeLimitExceeded):
        run_episode(
            _TwoStepEnv(8),
            HeuristicPolicy("hold"),
            policy_name="heuristic",
            environment_seed=8,
            policy_seed=9,
            max_decisions=1,
        )


def test_per_tick_reward_is_aggregated_for_smdp_learning():
    assert aggregate_interval_reward(
        -2.5, 4, {"reward_time_normalization": "per_tick"},
    ) == -10.0
    assert aggregate_interval_reward(
        -2.5, 4, {"reward_time_normalization": "sum"},
    ) == -2.5
    with pytest.raises(ValueError, match="reward_time_normalization"):
        aggregate_interval_reward(-2.5, 4, {"reward_time_normalization": "mystery"})


def test_active_fiscal_heuristic_uses_released_data_and_mask():
    policy = HeuristicPolicy("fiscal_stabilizer")
    info = {
        "action_dimensions": (("gov_deficit_target", None),),
        "action_mask": np.asarray(((False, True, True),)),
        "context": {
            "observation": {
                "releases": [
                    {
                        "series_id": "unemployment_rate",
                        "value": 0.20,
                        "missing_reason": None,
                    },
                    {
                        "series_id": "inflation",
                        "value": 0.005,
                        "missing_reason": None,
                    },
                ],
            },
        },
    }
    action = policy.act(np.zeros(1), info, deterministic=True)
    np.testing.assert_array_equal(action, (2,))


def _real_controller_environment(seed: int) -> ControllerEnv:
    calendars = {
        name: CalendarSpec(period_ticks=1_000, offset_ticks=999, admin_capacity=100.0)
        for name in DEFAULT_CALENDARS
    }
    calendars["monetary_stance"] = CalendarSpec(
        period_ticks=2, admin_capacity=100.0,
    )
    config = Config.v13(
        seed=seed,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        n_ticks=12,
        government=True,
    )
    session = ControlledSimulationSession(
        World([config]),
        scheduler=DecisionScheduler(calendars=calendars, triggers=()),
    )
    return ControllerEnv(
        session,
        economy_id=0,
        seat="central_bank",
        max_boundary_tick=6,
    )


def test_random_heuristic_and_model_run_through_real_controller_env():
    model = _MaskedUpModel()
    result = evaluate_policies(
        CallableEnvironmentFactory(_real_controller_environment),
        {
            "random": RandomMaskedPolicy(change_probability=0.5, max_changes=1),
            "heuristic": HeuristicPolicy("hold"),
            "model": PredictModelPolicy(model),
        },
        EvaluationPlan(
            ExperimentSeeds((901,), (902,), policy_seed_salt=903),
            max_decisions=10,
            bootstrap_resamples=100,
        ),
    )

    assert result.policy_names == ("heuristic", "model", "random")
    assert len(result.episodes) == 3
    assert all(item.truncated for item in result.episodes)
    assert all(item.elapsed_ticks == 6 for item in result.episodes)
    assert all(np.isfinite(item.total_reward) for item in result.episodes)
