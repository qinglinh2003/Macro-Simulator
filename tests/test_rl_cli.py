from __future__ import annotations

import json

import numpy as np
import pytest

from macro_sim.controllers.protocol import canonical_value
from macro_sim.rl.artifact import save_artifact
from macro_sim.rl.cli import main as rl_main
from macro_sim.rl.codec import ContextCodec, DirectionalActionCodec
from macro_sim.rl.envs import (
    FiscalStabilizationConfig,
    FiscalStabilizationEnvFactory,
)
from macro_sim.rl.model import NumpyMLPPolicy


def _config(*, horizon_ticks: int = 1) -> FiscalStabilizationConfig:
    return FiscalStabilizationConfig(
        horizon_ticks=horizon_ticks,
        decision_period_ticks=1,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
    )


def _artifact(tmp_path, *, mismatched_codec: bool = False):
    factory = FiscalStabilizationEnvFactory(_config())
    environment = factory(91)
    try:
        context_codec = environment.context_codec
        if mismatched_codec:
            payload = context_codec.to_dict()
            payload["economy_id"] = 1
            context_codec = ContextCodec.from_dict(payload)
        action_codec = DirectionalActionCodec.from_context_codec(context_codec)
        output_dim = action_codec.action_dim * 3
        bias = np.zeros(output_dim, dtype=np.float32)
        bias.reshape(action_codec.action_dim, 3)[:, 1] = 1.0
        policy = NumpyMLPPolicy(
            context_codec,
            action_codec,
            (np.zeros(
                (output_dim, context_codec.observation_dim), dtype=np.float32,
            ),),
            (bias,),
        )
    finally:
        environment.close()
    return save_artifact(
        tmp_path / ("codec-mismatch.msrl" if mismatched_codec else "policy.msrl"),
        policy,
        metadata={
            "environment_contract": factory.environment_contract,
            "environment_contract_hash": factory.environment_contract_hash,
            "training_environment_seed_range": {
                "start": 100,
                "stop_exclusive": 102,
            },
        },
    )


def _evaluate_arguments(model, *, output=None, horizon_ticks: int = 1):
    arguments = [
        "evaluate", str(model),
        "--seeds", "2",
        "--minimum-pairs", "2",
        "--bootstrap-resamples", "100",
        # The one-tick smoke task intentionally ties the deterministic policies.
        # A permissive, explicitly registered threshold exercises exit-code 0;
        # statistical-gate rejection is covered by experiment/metrics tests.
        "--minimum-effect", "-0.01",
        "--minimum-win-rate", "0",
        "--evaluation-seed-start", "1000",
        "--horizon-ticks", str(horizon_ticks),
        "--decision-period-ticks", "1",
        "--households", "8",
        "--consumer-firms", "5",
        "--capital-firms", "3",
        "--banks", "1",
    ]
    if output is not None:
        arguments.extend(("--output", str(output)))
    return arguments


def test_cli_evaluate_valid_artifact_writes_complete_provenance(tmp_path):
    model = _artifact(tmp_path)
    output = tmp_path / "evaluation.json"

    assert rl_main(_evaluate_arguments(model, output=output)) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    factory = FiscalStabilizationEnvFactory(_config())
    assert payload["artifact"]["path"] == str(model.resolve())
    assert len(payload["artifact"]["artifact_sha256"]) == 64
    assert payload["environment"] == {
        "contract": canonical_value(factory.environment_contract),
        "contract_hash": factory.environment_contract_hash,
    }
    assert payload["experiment"]["policy_names"] == [
        "heuristic", "model", "no_action", "random",
    ]
    assert set(payload["summaries"]) == {
        "heuristic", "model", "no_action", "random",
    }
    assert payload["verdict"]["candidate"] == "model"
    assert payload["verdict"]["passed"] is True


def test_cli_evaluate_rejects_environment_contract_mismatch(tmp_path):
    model = _artifact(tmp_path)

    with pytest.raises(ValueError, match="environment contract"):
        rl_main(_evaluate_arguments(model, horizon_ticks=2))


def test_cli_evaluate_rejects_vector_codec_mismatch(tmp_path):
    model = _artifact(tmp_path, mismatched_codec=True)

    with pytest.raises(ValueError, match="vector codecs"):
        rl_main(_evaluate_arguments(model))
