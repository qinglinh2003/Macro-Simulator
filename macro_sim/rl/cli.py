"""Command-line training and paired evaluation for controller policies."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from macro_sim.controllers.protocol import canonical_value

from .artifact import load_artifact_bundle
from .baselines import HeuristicPolicy, PredictModelPolicy, RandomMaskedPolicy
from .envs import FiscalStabilizationConfig, FiscalStabilizationEnvFactory
from .experiment import EvaluationPlan, ExperimentSeeds, evaluate_policies
from .metrics import SuperiorityRule
from .trainer import RLTrainer, TrainingConfig


def _hidden_sizes(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "hidden sizes must be comma-separated integers"
        ) from exc
    if not result or any(size <= 0 for size in result):
        raise argparse.ArgumentTypeError("hidden sizes must be positive integers")
    return result


def _environment_config(arguments: argparse.Namespace) -> FiscalStabilizationConfig:
    return FiscalStabilizationConfig(
        horizon_ticks=arguments.horizon_ticks,
        decision_period_ticks=arguments.decision_period_ticks,
        n_households=arguments.households,
        n_firms_c=arguments.consumer_firms,
        n_firms_k=arguments.capital_firms,
        n_banks=arguments.banks,
    )


def _add_environment_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--horizon-ticks", type=int, default=730)
    parser.add_argument("--decision-period-ticks", type=int, default=15)
    parser.add_argument("--households", type=int, default=20)
    parser.add_argument("--consumer-firms", type=int, default=15)
    parser.add_argument("--capital-firms", type=int, default=8)
    parser.add_argument("--banks", type=int, default=2)


def _train(arguments: argparse.Namespace) -> int:
    environment_config = _environment_config(arguments)
    rollout_steps = arguments.rollout_steps
    if rollout_steps is None:
        rollout_steps = (
            environment_config.horizon_ticks - 1
        ) // environment_config.decision_period_ticks + 1
    config = TrainingConfig(
        updates=arguments.updates,
        rollout_steps=rollout_steps,
        num_envs=arguments.num_envs,
        seed=arguments.seed,
        environment_seed_start=arguments.environment_seed_start,
        parallel=not arguments.sync,
        start_method=arguments.start_method,
        worker_timeout_seconds=arguments.worker_timeout_seconds,
        device=arguments.device,
        observation_clip=arguments.observation_clip,
        reward_scale=arguments.reward_scale,
        checkpoint_interval=arguments.checkpoint_interval,
        output_dir=arguments.output_dir,
    )
    overrides = {
        "activation": arguments.activation,
        "batch_size": arguments.batch_size,
        "entropy_coef": arguments.entropy_coef,
        "gamma": arguments.gamma,
        "gae_lambda": arguments.gae_lambda,
        "hidden_sizes": arguments.hidden_sizes,
        "learning_rate": arguments.learning_rate,
        "update_epochs": arguments.update_epochs,
    }
    trainer = RLTrainer(
        FiscalStabilizationEnvFactory(environment_config),
        config,
        ppo_overrides=overrides,
    )
    result = trainer.train(resume_from=arguments.resume)
    print(json.dumps({
        "artifact_path": str(result.artifact_path),
        "checkpoint_path": str(result.checkpoint_path),
        "device": result.device,
        "metrics_path": str(result.metrics_path),
        "samples": result.samples,
        "simulation_ticks": result.simulation_ticks,
        "updates": result.updates,
        "wall_time_seconds": result.wall_time_seconds,
    }, indent=2, sort_keys=True))
    return 0


def _evaluate(arguments: argparse.Namespace) -> int:
    artifact = load_artifact_bundle(arguments.model)
    policy = artifact.policy
    environment_config = _environment_config(arguments)
    environment_factory = FiscalStabilizationEnvFactory(environment_config)
    metadata = artifact.metadata
    trained_contract = metadata.get("environment_contract")
    trained_contract_hash = metadata.get("environment_contract_hash")
    normalized_trained_contract = (
        canonical_value(dict(trained_contract))
        if isinstance(trained_contract, Mapping) else None
    )
    if canonical_value(normalized_trained_contract) != canonical_value(
        environment_factory.environment_contract
    ) \
            or trained_contract_hash != environment_factory.environment_contract_hash:
        raise ValueError(
            "model training environment contract does not match evaluation task"
        )
    seed_range = metadata.get("training_environment_seed_range")
    if not isinstance(seed_range, dict) and not hasattr(seed_range, "get"):
        raise ValueError("model artifact does not declare its training seed range")
    training_start = seed_range.get("start")
    training_stop = seed_range.get("stop_exclusive")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (training_start, training_stop)
    ) or not 0 <= training_start < training_stop <= 2**63:
        raise ValueError("model artifact training seed range is invalid")
    evaluation = tuple(
        range(arguments.evaluation_seed_start, arguments.evaluation_seed_start + arguments.seeds)
    )
    overlap = [
        seed for seed in evaluation if training_start <= seed < training_stop
    ]
    if overlap:
        raise ValueError(
            "evaluation seeds overlap model training seeds; "
            f"first overlap={overlap[0]}"
        )
    probe = environment_factory(evaluation[0])
    try:
        if artifact.context_contract_hash != probe.context_codec.contract_hash \
                or artifact.action_contract_hash != probe.action_codec.contract_hash:
            raise ValueError(
                "model vector codecs do not match the evaluation environment"
            )
    finally:
        close = getattr(probe, "close", None)
        if callable(close):
            close()
    seeds = ExperimentSeeds(
        # The validated range remains in artifact provenance. Do not materialize
        # an untrusted, potentially enormous metadata range into memory.
        training=(),
        evaluation=evaluation,
        policy_seed_salt=arguments.policy_seed_salt,
    )
    plan = EvaluationPlan(
        seeds=seeds,
        gamma_per_tick=arguments.gamma,
        deterministic_models=True,
        max_decisions=(
            environment_config.horizon_ticks
            // environment_config.decision_period_ticks + 2
        ),
        bootstrap_resamples=arguments.bootstrap_resamples,
        bootstrap_seed=arguments.bootstrap_seed,
    )
    fiscal_parameters = {
        "inflation_ceiling": 0.01,
        "inflation_emergency": 0.02,
        "unemployment_enter": 0.10,
        "unemployment_exit": 0.06,
    }
    random_policy = RandomMaskedPolicy(
        change_probability=arguments.random_change_probability,
        max_changes=1,
    )
    result = evaluate_policies(
        environment_factory,
        {
            "heuristic": HeuristicPolicy(
                "fiscal_stabilizer", fiscal_parameters,
            ),
            "model": PredictModelPolicy(policy),
            "no_action": HeuristicPolicy("hold"),
            "random": random_policy,
        },
        plan,
    )
    superiority_rule = SuperiorityRule(
        confidence_level=arguments.confidence_level,
        minimum_effect=arguments.minimum_effect,
        minimum_win_rate=arguments.minimum_win_rate,
        minimum_pairs=arguments.minimum_pairs,
        bootstrap_resamples=arguments.bootstrap_resamples,
        bootstrap_seed=arguments.bootstrap_seed,
    )
    verdict = result.judge(
        "model",
        ("random", "heuristic", "no_action"),
        metric=arguments.metric,
        rule=superiority_rule,
    )
    payload = {
        "artifact": {
            "action_contract_hash": artifact.action_contract_hash,
            "artifact_sha256": artifact.artifact_sha256,
            "context_contract_hash": artifact.context_contract_hash,
            "metadata": canonical_value(dict(artifact.metadata)),
            "model_contract_hash": artifact.model_contract_hash,
            "path": str(Path(arguments.model).expanduser().resolve()),
        },
        "environment": {
            "contract": environment_factory.environment_contract,
            "contract_hash": environment_factory.environment_contract_hash,
        },
        "experiment": result.to_dict(),
        "policy_contracts": {
            "heuristic": {
                "parameters": fiscal_parameters,
                "rule_name": "fiscal_stabilizer",
            },
            "model": {"deterministic": True},
            "no_action": {"parameters": {}, "rule_name": "hold"},
            "random": {
                "change_probability": random_policy.change_probability,
                "max_changes": random_policy.max_changes,
            },
        },
        "summaries": {
            name: result.summary(name, arguments.metric).to_dict()
            for name in result.policy_names
        },
        "superiority_rule": {
            "bootstrap_resamples": superiority_rule.bootstrap_resamples,
            "bootstrap_seed": superiority_rule.bootstrap_seed,
            "confidence_level": superiority_rule.confidence_level,
            "familywise_confidence": superiority_rule.familywise_confidence,
            "minimum_effect": superiority_rule.minimum_effect,
            "minimum_pairs": superiority_rule.minimum_pairs,
            "minimum_win_rate": superiority_rule.minimum_win_rate,
        },
        "verdict": verdict.to_dict(),
    }
    output = json.dumps(payload, indent=2, sort_keys=True)
    if arguments.output is None:
        print(output)
    else:
        target = Path(arguments.output).expanduser().resolve()
        if target.exists():
            raise FileExistsError(f"refusing to overwrite evaluation output: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + "\n", encoding="utf-8")
        print(str(target))
    return 0 if verdict.passed else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="macro-rl",
        description="Train and independently evaluate macro policy controllers.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    train = commands.add_parser("train", help="train SMDP PPO and export a policy")
    _add_environment_arguments(train)
    train.add_argument("--updates", type=int, default=50)
    train.add_argument("--rollout-steps", type=int)
    train.add_argument("--num-envs", type=int, default=4)
    train.add_argument("--seed", type=int, default=42)
    train.add_argument("--environment-seed-start", type=int, default=10_000)
    train.add_argument("--device", choices=("auto", "cpu", "mps"), default="cpu")
    train.add_argument("--sync", action="store_true", help="disable process workers")
    train.add_argument("--start-method", default="spawn")
    train.add_argument("--worker-timeout-seconds", type=float, default=300.0)
    train.add_argument("--output-dir", default="runs/fiscal_stabilization_v1")
    train.add_argument("--resume")
    train.add_argument("--checkpoint-interval", type=int, default=5)
    train.add_argument("--observation-clip", type=float, default=10.0)
    train.add_argument("--reward-scale", type=float, default=0.01)
    train.add_argument("--hidden-sizes", type=_hidden_sizes, default=(128, 128))
    train.add_argument("--activation", choices=("tanh", "relu"), default="tanh")
    train.add_argument("--learning-rate", type=float, default=3.0e-4)
    train.add_argument("--batch-size", type=int, default=196)
    train.add_argument("--update-epochs", type=int, default=10)
    train.add_argument("--gamma", type=float, default=0.999)
    train.add_argument("--gae-lambda", type=float, default=0.995)
    train.add_argument("--entropy-coef", type=float, default=0.01)
    train.set_defaults(handler=_train)

    evaluate = commands.add_parser(
        "evaluate", help="paired held-out comparison against registered baselines",
    )
    _add_environment_arguments(evaluate)
    evaluate.add_argument("model")
    evaluate.add_argument("--seeds", type=int, default=20)
    evaluate.add_argument("--evaluation-seed-start", type=int, default=1_000_000)
    evaluate.add_argument("--policy-seed-salt", type=int, default=7001)
    evaluate.add_argument("--gamma", type=float, default=0.999)
    evaluate.add_argument(
        "--metric",
        choices=("discounted_return", "total_reward", "reward_per_tick"),
        default="discounted_return",
    )
    evaluate.add_argument("--random-change-probability", type=float, default=0.25)
    evaluate.add_argument("--confidence-level", type=float, default=0.95)
    evaluate.add_argument("--minimum-effect", type=float, default=0.0)
    evaluate.add_argument("--minimum-win-rate", type=float, default=0.5)
    evaluate.add_argument("--minimum-pairs", type=int, default=20)
    evaluate.add_argument("--bootstrap-resamples", type=int, default=10_000)
    evaluate.add_argument("--bootstrap-seed", type=int, default=9001)
    evaluate.add_argument("--output")
    evaluate.set_defaults(handler=_evaluate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "evaluate" and arguments.seeds < arguments.minimum_pairs:
        raise ValueError("--seeds must be at least --minimum-pairs")
    return int(arguments.handler(arguments))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
