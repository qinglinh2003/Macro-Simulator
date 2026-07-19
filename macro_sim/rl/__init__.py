"""Reinforcement-learning toolkit for institutional policy controllers.

The public surface is lazy so spawned simulation workers and inference-only
processes do not import PyTorch. Accessing a training symbol imports its module
on demand; portable artifact loading stays NumPy-only.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "ActorCriticNetwork": ("network", "ActorCriticNetwork"),
    "ArtifactError": ("artifact", "ArtifactError"),
    "ContextCodec": ("codec", "ContextCodec"),
    "DirectionalActionCodec": ("codec", "DirectionalActionCodec"),
    "EvaluationPlan": ("experiment", "EvaluationPlan"),
    "ExperimentResult": ("experiment", "ExperimentResult"),
    "ExperimentSeeds": ("experiment", "ExperimentSeeds"),
    "FISCAL_STABILIZATION_TASK": ("envs", "FISCAL_STABILIZATION_TASK"),
    "FiscalStabilizationConfig": ("envs", "FiscalStabilizationConfig"),
    "FiscalStabilizationEnvFactory": ("envs", "FiscalStabilizationEnvFactory"),
    "HeuristicPolicy": ("baselines", "HeuristicPolicy"),
    "LoadedArtifact": ("artifact", "LoadedArtifact"),
    "MaskedMultiCategorical": ("network", "MaskedMultiCategorical"),
    "NumpyMLPPolicy": ("model", "NumpyMLPPolicy"),
    "PPOConfig": ("algorithm", "PPOConfig"),
    "PPOUpdateStats": ("algorithm", "PPOUpdateStats"),
    "PredictModelPolicy": ("baselines", "PredictModelPolicy"),
    "RLTrainer": ("trainer", "RLTrainer"),
    "RandomMaskedPolicy": ("baselines", "RandomMaskedPolicy"),
    "RemoteEnvironmentError": ("vector_env", "RemoteEnvironmentError"),
    "RolloutBatch": ("buffer", "RolloutBatch"),
    "RunningObservationNormalizer": ("trainer", "RunningObservationNormalizer"),
    "SMDPPPO": ("algorithm", "SMDPPPO"),
    "SMDPRolloutBuffer": ("buffer", "SMDPRolloutBuffer"),
    "SubprocessEnvironmentBatch": ("vector_env", "SubprocessEnvironmentBatch"),
    "SuperiorityRule": ("metrics", "SuperiorityRule"),
    "SynchronousEnvironmentBatch": ("experiment", "SynchronousEnvironmentBatch"),
    "TrainingConfig": ("trainer", "TrainingConfig"),
    "TrainingResult": ("trainer", "TrainingResult"),
    "aggregate_interval_reward": ("experiment", "aggregate_interval_reward"),
    "evaluate_policies": ("experiment", "evaluate_policies"),
    "fiscal_stabilization_objective": ("envs", "fiscal_stabilization_objective"),
    "load_artifact": ("artifact", "load_artifact"),
    "load_artifact_bundle": ("artifact", "load_artifact_bundle"),
    "make_fiscal_stabilization_env": ("envs", "make_fiscal_stabilization_env"),
    "resolve_device": ("algorithm", "resolve_device"),
    "run_episode": ("experiment", "run_episode"),
    "save_artifact": ("artifact", "save_artifact"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(f"{__name__}.{module_name}"), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *_EXPORTS))
