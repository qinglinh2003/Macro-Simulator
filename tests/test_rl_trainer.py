from __future__ import annotations

from dataclasses import replace
import json

import numpy as np
import pytest

import macro_sim.rl.trainer as trainer_module
from macro_sim.controllers.occupants import RLOccupant
from macro_sim.rl.artifact import load_artifact, load_artifact_bundle
from macro_sim.rl.cli import build_parser, main as rl_main
from macro_sim.rl.envs import (
    FiscalStabilizationConfig,
    FiscalStabilizationEnvFactory,
)
from macro_sim.rl.trainer import (
    RLTrainer,
    RunningObservationNormalizer,
    TrainingConfig,
)


def _factory() -> FiscalStabilizationEnvFactory:
    return FiscalStabilizationEnvFactory(FiscalStabilizationConfig(
        horizon_ticks=30,
        decision_period_ticks=15,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
    ))


def _different_factory() -> FiscalStabilizationEnvFactory:
    return FiscalStabilizationEnvFactory(FiscalStabilizationConfig(
        horizon_ticks=45,
        decision_period_ticks=15,
        n_households=12,
        n_firms_c=7,
        n_firms_k=4,
        n_banks=1,
    ))


def _config(output_dir, *, updates: int) -> TrainingConfig:
    return TrainingConfig(
        updates=updates,
        rollout_steps=2,
        num_envs=2,
        seed=701,
        environment_seed_start=70_000,
        parallel=False,
        device="cpu",
        checkpoint_interval=1,
        output_dir=str(output_dir),
    )


def _ppo_overrides():
    return {
        "hidden_sizes": (16, 16),
        "batch_size": 4,
        "update_epochs": 2,
        "entropy_coef": 0.01,
    }


def _assert_nested_state_equal(left, right, *, path: str = "state") -> None:
    """Compare a weights-only checkpoint tree without numerical tolerance."""
    import torch

    assert type(left) is type(right), f"{path} types differ"
    if torch.is_tensor(left):
        assert torch.equal(left, right), f"{path} tensors differ"
        return
    if type(left) is dict:
        assert set(left) == set(right), f"{path} keys differ"
        for key in left:
            _assert_nested_state_equal(
                left[key], right[key], path=f"{path}[{key!r}]",
            )
        return
    if type(left) in {list, tuple}:
        assert len(left) == len(right), f"{path} lengths differ"
        for index, (left_item, right_item) in enumerate(
            zip(left, right, strict=True),
        ):
            _assert_nested_state_equal(
                left_item, right_item, path=f"{path}[{index}]",
            )
        return
    assert left == right, f"{path} values differ"


def test_training_defaults_to_cpu_and_scales_optimizer_rewards():
    assert TrainingConfig().device == "cpu"
    assert TrainingConfig().reward_scale == pytest.approx(0.01)
    arguments = build_parser().parse_args(["train"])
    assert arguments.device == "cpu"
    assert arguments.reward_scale == pytest.approx(0.01)


def test_running_observation_normalizer_round_trip_and_clipping():
    normalizer = RunningObservationNormalizer(2)
    normalizer.update(np.asarray(((1.0, 10.0), (3.0, 14.0))))
    normalized = normalizer.normalize(((1.0, 10.0), (3.0, 14.0)), clip=5.0)
    np.testing.assert_allclose(normalized.mean(axis=0), (0.0, 0.0), atol=1e-7)
    restored = RunningObservationNormalizer(2)
    restored.load_state_dict(normalizer.state_dict())
    np.testing.assert_array_equal(restored.mean, normalizer.mean)
    np.testing.assert_array_equal(restored.scale, normalizer.scale)
    np.testing.assert_array_equal(
        restored.normalize(((100.0, -100.0),), clip=2.0),
        ((2.0, -2.0),),
    )


def test_train_export_load_and_rl_occupant_inference(tmp_path):
    trainer = RLTrainer(
        _factory(), _config(tmp_path / "run", updates=1),
        ppo_overrides=_ppo_overrides(),
    )
    result = trainer.train()

    assert result.updates == 1
    assert result.samples == 4
    assert result.simulation_ticks == 60
    assert result.artifact_path.is_file()
    assert result.checkpoint_path.is_file()
    records = [
        json.loads(line)
        for line in result.metrics_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["update"] == 1

    policy = load_artifact(result.artifact_path)
    bundle = load_artifact_bundle(result.artifact_path)
    assert len(bundle.artifact_sha256) == 64
    assert bundle.metadata["training_environment_seed_range"] == {
        "start": 70_000,
        "stop_exclusive": 70_002,
    }
    env = _factory()(70_999)
    observation, info = env.reset(seed=70_999)
    action = policy.predict(
        observation,
        action_mask=info["action_mask"],
        deterministic=True,
    )
    assert action.shape == (1,)
    assert info["action_mask"][0, action[0]]
    proposal = RLOccupant(policy=policy).propose(env.context)
    assert proposal is not None
    assert all(item.lever == "gov_deficit_target" for item in proposal.actions)
    with pytest.raises(ValueError, match="overlap"):
        rl_main([
            "evaluate", str(result.artifact_path),
            "--seeds", "2", "--minimum-pairs", "2",
            "--bootstrap-resamples", "100",
            "--evaluation-seed-start", "70000",
            "--horizon-ticks", "30", "--decision-period-ticks", "15",
            "--households", "8", "--consumer-firms", "5",
            "--capital-firms", "3", "--banks", "1",
        ])


def test_checkpoint_resumes_with_safe_loader_and_preserves_counters(tmp_path):
    output = tmp_path / "resume"
    first = RLTrainer(
        _factory(), _config(output, updates=1),
        ppo_overrides=_ppo_overrides(),
    ).train()
    with first.metrics_path.open("a", encoding="utf-8") as handle:
        handle.write('{"update":2}\n')
    resumed = RLTrainer(
        _factory(), _config(output, updates=2),
        ppo_overrides=_ppo_overrides(),
    ).train(resume_from=first.checkpoint_path)

    assert resumed.updates == 2
    assert resumed.samples == 8
    assert resumed.simulation_ticks == 120
    assert len(resumed.metrics_path.read_text(encoding="utf-8").splitlines()) == 2


def test_episode_aligned_resume_is_bit_exact_for_full_trainer_state(tmp_path):
    import torch

    continuous_trainer = RLTrainer(
        _factory(), _config(tmp_path / "continuous", updates=2),
        ppo_overrides=_ppo_overrides(),
    )
    continuous = continuous_trainer.train()

    resumed_output = tmp_path / "resumed"
    first = RLTrainer(
        _factory(), _config(resumed_output, updates=1),
        ppo_overrides=_ppo_overrides(),
    ).train()
    resumed_trainer = RLTrainer(
        _factory(), _config(resumed_output, updates=2),
        ppo_overrides=_ppo_overrides(),
    )
    resumed = resumed_trainer.train(resume_from=first.checkpoint_path)

    continuous_state = torch.load(
        continuous.checkpoint_path, map_location="cpu", weights_only=True,
    )
    resumed_state = torch.load(
        resumed.checkpoint_path, map_location="cpu", weights_only=True,
    )
    _assert_nested_state_equal(continuous_state, resumed_state)
    assert resumed_trainer.next_environment_seed == 70_004


def test_trainer_aggregates_then_scales_optimizer_rewards_only(
    tmp_path, monkeypatch,
):
    config = replace(
        _config(tmp_path / "reward-scale", updates=1), reward_scale=0.125,
    )
    aggregate_calls = []
    real_aggregate = trainer_module.aggregate_interval_reward

    def aggregate_spy(reward, elapsed_ticks, info):
        result = real_aggregate(reward, elapsed_ticks, info)
        aggregate_calls.append((
            float(reward), int(elapsed_ticks),
            info.get("reward_time_normalization"), result,
        ))
        return result

    monkeypatch.setattr(
        trainer_module, "aggregate_interval_reward", aggregate_spy,
    )
    trainer = RLTrainer(
        _factory(), config, ppo_overrides=_ppo_overrides(),
    )
    captured_rollout_rewards = []
    real_update = trainer.learner.update

    def update_spy(rollout):
        captured_rollout_rewards.append(
            rollout.rewards[:rollout.size].copy(),
        )
        return real_update(rollout)

    monkeypatch.setattr(trainer.learner, "update", update_spy)
    result = trainer.train()

    assert len(aggregate_calls) == config.samples_per_update
    for reward, elapsed, normalization, interval_reward in aggregate_calls:
        assert normalization == "per_tick"
        assert interval_reward == pytest.approx(reward * elapsed)
    unscaled = np.asarray(
        [item[3] for item in aggregate_calls], dtype=np.float64,
    ).reshape(config.rollout_steps, config.num_envs)
    assert len(captured_rollout_rewards) == 1
    np.testing.assert_allclose(
        captured_rollout_rewards[0],
        unscaled * config.reward_scale,
        rtol=1.0e-6,
        atol=1.0e-6,
    )
    record = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    assert record["completed_episode_return_mean"] == pytest.approx(
        float(np.mean(np.sum(unscaled, axis=0))),
    )


def test_resume_rejects_missing_metrics_for_nonempty_checkpoint(tmp_path):
    output = tmp_path / "missing-metrics"
    first = RLTrainer(
        _factory(), _config(output, updates=1),
        ppo_overrides=_ppo_overrides(),
    ).train()
    first.metrics_path.unlink()

    resumed_trainer = RLTrainer(
        _factory(), _config(output, updates=2),
        ppo_overrides=_ppo_overrides(),
    )
    with pytest.raises(ValueError, match="missing metrics.jsonl"):
        resumed_trainer.train(resume_from=first.checkpoint_path)
    assert not first.metrics_path.exists()


def test_checkpoint_rejects_task_drift_and_rejection_is_state_atomic(tmp_path):
    import torch

    output = tmp_path / "source"
    source = RLTrainer(
        _factory(), _config(output, updates=1),
        ppo_overrides=_ppo_overrides(),
    ).train()
    drifted = RLTrainer(
        _different_factory(),
        TrainingConfig(
            updates=1,
            rollout_steps=3,
            num_envs=2,
            seed=701,
            environment_seed_start=70_000,
            parallel=False,
            device="cpu",
            checkpoint_interval=1,
            output_dir=str(tmp_path / "drifted"),
        ),
        ppo_overrides=_ppo_overrides(),
    )
    with pytest.raises(ValueError, match="environment/task contract"):
        drifted.load_checkpoint(source.checkpoint_path)

    payload = torch.load(source.checkpoint_path, weights_only=True)
    payload["completed_updates"] = -1
    first_name = next(iter(payload["learner"]["network"]))
    payload["learner"]["network"][first_name] += 1.0
    poisoned = tmp_path / "poisoned.pt"
    torch.save(payload, poisoned)
    target = RLTrainer(
        _factory(), _config(tmp_path / "target", updates=1),
        ppo_overrides=_ppo_overrides(),
    )
    before = {
        name: value.detach().clone()
        for name, value in target.learner.network.state_dict().items()
    }
    normalizer_before = target.normalizer.state_dict()
    with pytest.raises(ValueError, match="completed_updates"):
        target.load_checkpoint(poisoned)
    for name, value in target.learner.network.state_dict().items():
        assert torch.equal(value, before[name])
    assert target.normalizer.state_dict() == normalizer_before

    skipped_seed_payload = torch.load(source.checkpoint_path, weights_only=True)
    skipped_seed_payload["next_environment_seed"] += 2
    skipped_seed = tmp_path / "skipped-seed.pt"
    torch.save(skipped_seed_payload, skipped_seed)
    with pytest.raises(ValueError, match="next_environment_seed"):
        target.load_checkpoint(skipped_seed)


def test_trainer_fails_fast_for_unexportable_activation_and_partial_episode(tmp_path):
    with pytest.raises(ValueError, match="cannot be exported"):
        RLTrainer(
            _factory(), _config(tmp_path / "activation", updates=1),
            ppo_overrides={**_ppo_overrides(), "activation": "elu"},
        )
    with pytest.raises(ValueError, match="whole fixed-horizon episodes"):
        RLTrainer(
            _factory(),
            TrainingConfig(
                updates=1,
                rollout_steps=1,
                num_envs=2,
                parallel=False,
                device="cpu",
                output_dir=str(tmp_path / "partial"),
            ),
            ppo_overrides=_ppo_overrides(),
        )


def test_mps_checkpoint_resumes_through_next_optimizer_update(tmp_path):
    torch = pytest.importorskip("torch")
    if not torch.backends.mps.is_available():
        pytest.skip("MPS is unavailable")
    config = TrainingConfig(
        updates=1,
        rollout_steps=2,
        num_envs=2,
        seed=702,
        environment_seed_start=71_000,
        parallel=False,
        device="mps",
        checkpoint_interval=1,
        output_dir=str(tmp_path / "mps"),
    )
    trained = RLTrainer(
        _factory(), config, ppo_overrides=_ppo_overrides(),
    ).train()
    restored = RLTrainer(
        _factory(), replace(config, updates=2), ppo_overrides=_ppo_overrides(),
    )
    result = restored.train(resume_from=trained.checkpoint_path)
    assert result.updates == 2
    assert result.samples == 8
    optimizer_moments = [
        value
        for state in restored.learner.optimizer.state.values()
        for name, value in state.items()
        if name != "step"
    ]
    assert optimizer_moments
    assert all(value.device.type == "mps" for value in optimizer_moments)


def test_new_run_refuses_to_overwrite_existing_outputs(tmp_path):
    output = tmp_path / "collision"
    trainer = RLTrainer(
        _factory(), _config(output, updates=1),
        ppo_overrides=_ppo_overrides(),
    )
    trainer.train()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        RLTrainer(
            _factory(), _config(output, updates=1),
            ppo_overrides=_ppo_overrides(),
        ).train()
