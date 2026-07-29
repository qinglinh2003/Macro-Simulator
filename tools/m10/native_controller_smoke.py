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
    from macro_sim.controllers.coordinator import SEATS
    from macro_sim.controllers.native_session import (
        create_native_controlled_session,
        restore_native_controlled_session,
    )
    from macro_sim.controllers.native_envelope import decode_controller_state
    from macro_sim.controllers.occupants import HumanQueueOccupant, NullOccupant
    from macro_sim.controllers.protocol import PolicyAction, PolicyProposal
    from macro_sim.desktop.new_game import NewGameSpec

    controlled_spec = NewGameSpec.default(seed=1199)
    controlled_world, controlled = create_native_controlled_session(
        controlled_spec,
    )
    opening_target = controlled_world.native_session.policy_values(0)[
        "gov_deficit_target"
    ]
    for seat in SEATS:
        occupant = (
            HumanQueueOccupant()
            if seat == "treasury" else NullOccupant()
        )
        controlled.assign_seat(0, seat, occupant, actor="native-smoke")
    awaiting = controlled.advance()
    assert awaiting.status == "awaiting_human"
    assert controlled.boundary_tick == 0
    assert len(awaiting.contexts) == 12
    assert len(awaiting.missing_context_ids) == 3
    checkpoint = controlled_world.checkpoint_controller(
        controlled, b'{"objective":"controlled-split"}',
    )
    split_world, split, split_objective = restore_native_controlled_session(
        controlled_spec, checkpoint,
    )
    assert split_objective == b'{"objective":"controlled-split"}'
    assert split.phase == controlled.phase
    assert split.missing_context_ids == controlled.missing_context_ids
    assert split.events.head_hash == controlled.events.head_hash

    def submit_treasury(target):
        for context_id in target.current_context_ids:
            context = target.coordinator.contexts[context_id]
            if context.seat != "treasury":
                continue
            actions = ()
            if context.decision_group == "fiscal_stance":
                current = next(
                    item.current_value
                    for item in context.permitted_actions
                    if item.lever == "gov_deficit_target"
                )
                actions = (
                    PolicyAction(
                        "gov_deficit_target", float(current) + 0.005,
                    ),
                )
            proposal_id = f"proposal:{context.context_id}:native-smoke"
            target.submit_human_proposal(
                PolicyProposal(
                    proposal_id=proposal_id,
                    idempotency_key=proposal_id,
                    context_id=context.context_id,
                    actions=actions,
                    reason="native controller smoke",
                    based_on_policy_versions=dict(context.policy_versions),
                ),
                actor="native-smoke-human",
            )

    submit_treasury(controlled)
    submit_treasury(split)
    first = controlled.advance()
    split_first = split.advance()
    assert first.status == "advanced"
    assert split_first == first
    assert controlled.boundary_tick == 1
    assert controlled_world.native_session.tick == 1
    assert len(first.contexts) == 12
    fiscal = [
        decision for decision in first.decisions
        if decision.proposal_id.endswith("fiscal_stance:0:regular:native-smoke")
    ]
    assert len(fiscal) == 1
    assert fiscal[0].status == "accepted_pending"
    assert fiscal[0].effective_tick == 7
    assert (
        controlled_world.native_session.policy_values(0)[
            "gov_deficit_target"
        ]
        == opening_target
    )
    for _ in range(6):
        assert split.advance() == controlled.advance()
        assert (
            split_world.native_session.native_snapshot()["digest"]
            == controlled_world.native_session.native_snapshot()["digest"]
        )
        assert split.events.head_hash == controlled.events.head_hash
    assert controlled.boundary_tick == 7
    assert (
        controlled_world.native_session.policy_values(0)[
            "gov_deficit_target"
        ]
        == opening_target
    )
    effective = controlled.advance()
    split_effective = split.advance()
    assert split_effective == effective
    assert any(
        decision.decision_id == fiscal[0].decision_id
        and decision.status == "effective"
        for decision in effective.decisions
    )
    assert (
        controlled_world.native_session.policy_values(0)[
            "gov_deficit_target"
        ]
        == opening_target + 0.005
    )
    assert (
        split_world.native_session.native_snapshot()["digest"]
        == controlled_world.native_session.native_snapshot()["digest"]
    )
    assert bytes(
        split_world.native_session.bridge.controller_envelope.canonical_payload
    ) == bytes(
        controlled_world.native_session.bridge.controller_envelope.canonical_payload
    )

    fault_world, fault_session = create_native_controlled_session(
        NewGameSpec.default(seed=1200),
    )
    for seat in SEATS:
        fault_session.assign_seat(
            0, seat, NullOccupant(), actor="native-fault-smoke",
        )
    opening_native = fault_world.native_session.native_snapshot()
    opening_payload = bytes(
        fault_world.native_session.bridge.controller_envelope.canonical_payload
    )
    opening_hash = fault_world.native_session.bridge.controller_envelope.hash
    opening_event_head = fault_session.events.head_hash
    for fault_point in (
        "prepare_after_policy",
        "prepare_after_advance",
        "prepare_after_metrics",
        "commit_before_swap",
    ):
        fault_world.inject_controller_fault_for_test(fault_point)
        try:
            fault_session.advance()
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"{fault_point} did not fail")
        assert fault_session.boundary_tick == 0
        assert fault_world.native_session.tick == 0
        assert fault_world.native_session.native_snapshot() == opening_native
        assert fault_session.events.head_hash == opening_event_head
        assert (
            fault_world.native_session.bridge.controller_envelope.hash
            == opening_hash
        )
        assert bytes(
            fault_world.native_session.bridge.controller_envelope.canonical_payload
        ) == opening_payload
    fault_world.inject_controller_fault_for_test("none")
    assert fault_session.advance().status == "advanced"
    assert fault_session.boundary_tick == 1

    build_world, build_session = create_native_controlled_session(
        NewGameSpec.default(seed=1203),
    )
    for seat in SEATS:
        build_session.assign_seat(
            0, seat, NullOccupant(), actor="native-build-fault",
        )
    build_opening = build_world.native_session.native_snapshot()
    build_payload = bytes(
        build_world.native_session.bridge.controller_envelope.canonical_payload
    )
    build_world.inject_controller_fault_for_test("controller_build")
    try:
        build_session.advance()
    except RuntimeError:
        pass
    else:
        raise AssertionError("controller-build fault did not fail")
    assert build_session.boundary_tick == 0
    assert build_world.native_session.native_snapshot() == build_opening
    assert bytes(
        build_world.native_session.bridge.controller_envelope.canonical_payload
    ) == build_payload

    for index, fault_point in enumerate(("cache_rebuild", "publication")):
        post_world, post_session = create_native_controlled_session(
            NewGameSpec.default(seed=1204 + index),
        )
        for seat in SEATS:
            post_session.assign_seat(
                0, seat, NullOccupant(), actor=f"native-{fault_point}",
            )
        post_world.inject_controller_fault_for_test(fault_point)
        try:
            post_session.advance()
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"{fault_point} did not fail")
        assert post_session.boundary_tick == 1
        assert post_world.native_session.tick == 1
        restored_state = decode_controller_state(bytes(
            post_world.native_session.bridge.controller_envelope.canonical_payload
        ))
        assert restored_state["session"]["boundary_tick"] == 1
        assert restored_state["session"]["phase"] == "boundary_start"
        assert restored_state["events"].head_hash == post_session.events.head_hash

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
