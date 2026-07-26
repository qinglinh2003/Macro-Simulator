from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.native_dir))
    sys.path.insert(1, str(args.source_dir))

    from macro_sim.rl.artifact import load_artifact
    from macro_sim.rl.baselines import HeuristicPolicy, PredictModelPolicy
    from macro_sim.rl.experiment import (
        EvaluationPlan,
        ExperimentSeeds,
        SynchronousEnvironmentBatch,
        evaluate_policies,
    )
    from macro_sim.rl.native_envs import (
        NativeFiscalStabilizationEnvFactory,
        make_native_fiscal_stabilization_env,
    )

    artifact_path = (
        args.source_dir
        / "macro_sim"
        / "rl"
        / "artifacts"
        / "fiscal_stabilization_v1.msrl"
    )
    model = load_artifact(artifact_path)
    factory = NativeFiscalStabilizationEnvFactory(worker_count=8)

    environment = factory(1201)
    observation, info = environment.reset(seed=1201)
    assert observation.shape == (101,)
    assert info["context_contract_hash"] == model.context_codec.contract_hash
    assert info["action_contract_hash"] == model.action_codec.contract_hash
    releases = {
        item["series_id"]: item
        for item in info["context"]["observation"]["releases"]
    }
    assert len(releases) == 42
    assert releases["oracle_daily_output"]["missing_reason"] == "access_denied"
    assert releases["bank_reserves_total"]["missing_reason"] == "access_denied"
    assert info["action_mask"].tolist() == [[False, True, True]]

    _next, reward, terminated, truncated, next_info = environment.step([2])
    assert np.isfinite(reward)
    assert not terminated and not truncated
    assert environment.boundary_tick == 15
    assert next_info["decisions"][0]["status"] == "effective"
    assert next_info["decisions"][0]["effective_tick"] == 7
    assert next_info["action_mask"].tolist() == [[False, True, False]]

    clone = environment.clone()
    left = environment.step([1])
    right = clone.step([1])
    assert np.array_equal(left[0], right[0])
    assert left[1:4] == right[1:4]
    assert left[4]["objective"] == right[4]["objective"]
    assert np.array_equal(
        left[4]["action_mask"], right[4]["action_mask"],
    )

    with SynchronousEnvironmentBatch(factory, (1301, 1302)) as batch:
        reset = batch.reset()
        assert reset.observations.shape == (2, 101)
        assert reset.action_masks.shape == (2, 1, 3)
        transition = batch.step(np.asarray([[1], [1]], dtype=np.int64))
        assert transition.observations.shape == (2, 101)
        assert transition.elapsed_ticks.tolist() == [15, 15]

    plan = EvaluationPlan(
        seeds=ExperimentSeeds(training=(), evaluation=(1401, 1402)),
        bootstrap_resamples=100,
        max_decisions=64,
    )
    result = evaluate_policies(
        factory,
        {
            "fiscal_stabilizer": HeuristicPolicy("fiscal_stabilizer"),
            "hold": HeuristicPolicy("hold"),
            "rl_artifact": PredictModelPolicy(model),
        },
        plan,
    )
    assert len(result.episodes) == 6
    for episode in result.episodes:
        assert episode.terminated
        assert not episode.truncated
        assert episode.elapsed_ticks == 730
        assert episode.decision_steps == 49
        assert np.isfinite(episode.total_reward)

    # A fresh constructor remains available after the paired evaluation closes.
    fresh = make_native_fiscal_stabilization_env(1501)
    fresh.reset()
    fresh.close()
    print("M10 native controller/RL smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
