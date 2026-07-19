"""Canonical occupant construction, immutable config, and seat identity gates."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import math

import pytest

from macro_sim.config import Config
from macro_sim.controllers.occupants import (
    HeuristicOccupant,
    HumanQueueOccupant,
    NullOccupant,
    RandomFuzzOccupant,
    RLOccupant,
    ScheduledOccupant,
    occupant_from_spec,
    occupant_is_canonical_fresh,
    occupant_spec,
)
from macro_sim.controllers.protocol import PolicyAction, PolicyProposal, canonical_json
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.world import World


def _world(seed: int = 1520) -> World:
    return World([Config.v13(
        seed=seed,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        demographics_population=30,
        n_ticks=20,
        government=True,
    )])


def _mailbox_proposal(context_id: str = "ctx:future") -> PolicyProposal:
    return PolicyProposal(
        proposal_id=f"proposal:{context_id}",
        idempotency_key=f"proposal:{context_id}",
        context_id=context_id,
        actions=(),
        based_on_policy_versions={},
    )


@pytest.mark.parametrize(
    "occupant",
    (
        NullOccupant(),
        HumanQueueOccupant(),
        RandomFuzzOccupant(seed=41, action_probability=0.5, max_actions=3),
        HeuristicOccupant(
            rule_name="inflation_targeting",
            parameters={"target": 0.02, "gain": 0.001},
        ),
        ScheduledOccupant({
            4: (PolicyAction("gov_deficit_target", 0.01),),
            1: (),
        }),
        RLOccupant(policy=lambda _context: ()),
    ),
)
def test_builtin_occupant_specs_roundtrip_to_canonical_fresh_state(occupant):
    spec = occupant_spec(occupant)
    reconstructed = occupant_from_spec(spec)

    assert canonical_json(occupant_spec(reconstructed)) == canonical_json(spec)
    assert occupant_is_canonical_fresh(occupant)
    assert occupant_is_canonical_fresh(reconstructed)
    if isinstance(occupant, RLOccupant):
        assert reconstructed.policy is None


def test_fresh_assignment_rejects_preconsumed_random_and_preloaded_mailboxes():
    random_occupant = RandomFuzzOccupant(seed=42)
    random_occupant._rng.random()
    session = ControlledSimulationSession(_world(1521))
    before = session.events.canonical_bytes()
    with pytest.raises(ValueError, match="canonical initial state"):
        session.assign_seat(0, "treasury", random_occupant)
    assert session.seat_assignments == {}
    assert session.events.canonical_bytes() == before

    human = HumanQueueOccupant()
    human.submit(_mailbox_proposal("ctx:human-preload"), actor="alice")
    with pytest.raises(ValueError, match="canonical initial state"):
        session.assign_seat(0, "treasury", human)

    rl = RLOccupant()
    rl.submit(_mailbox_proposal("ctx:rl-preload"), actor="replay")
    with pytest.raises(ValueError, match="canonical initial state"):
        session.assign_seat(0, "treasury", rl)


def test_fresh_and_restore_assignment_enforce_object_identity():
    session = ControlledSimulationSession(_world(1522))
    first = NullOccupant()
    second = HumanQueueOccupant()
    session.assign_seat(0, "treasury", first)

    with pytest.raises(ValueError, match="already be active or archived"):
        session.assign_seat(0, "central_bank", first)

    session.assign_seat(0, "treasury", second)
    archive_id = session.events.events[-1]["payload"]["archived_outgoing_id"]
    assert session.assignment_archive[archive_id] is first

    with pytest.raises(ValueError, match="already be active or archived"):
        session.assign_seat(0, "central_bank", first)

    session.restore_seat(0, "treasury", archive_id)
    assert session.seat_assignments[(0, "treasury")] is first
    with pytest.raises(ValueError, match="cannot already be active"):
        session.restore_seat(0, "central_bank", archive_id)


def test_occupant_configuration_is_deeply_immutable():
    scheduled = ScheduledOccupant({
        2: (PolicyAction("gov_deficit_target", 0.02),),
    })
    heuristic = HeuristicOccupant(parameters={"gain": 0.1})
    random_occupant = RandomFuzzOccupant(seed=43)

    with pytest.raises(FrozenInstanceError):
        scheduled.schedule = {}
    with pytest.raises(TypeError):
        scheduled.schedule[2] = ()
    with pytest.raises(FrozenInstanceError):
        heuristic.rule_name = "inflation_targeting"
    with pytest.raises(TypeError):
        heuristic.parameters["gain"] = 0.2
    with pytest.raises(FrozenInstanceError):
        random_occupant.seed = 44


@pytest.mark.parametrize(
    ("factory", "error"),
    (
        (lambda: ScheduledOccupant({True: ()}), TypeError),
        (lambda: ScheduledOccupant({-1: ()}), ValueError),
        (lambda: ScheduledOccupant({0: (object(),)}), TypeError),
        (lambda: RandomFuzzOccupant(seed=True), TypeError),
        (lambda: RandomFuzzOccupant(seed=1, action_probability="0.5"), ValueError),
        (lambda: RandomFuzzOccupant(seed=1, action_probability=math.nan), ValueError),
        (lambda: RandomFuzzOccupant(seed=1, action_probability=1.1), ValueError),
        (lambda: RandomFuzzOccupant(seed=1, max_actions=True), TypeError),
        (lambda: RandomFuzzOccupant(seed=1, max_actions=-1), ValueError),
        (lambda: HeuristicOccupant(rule_name="unknown"), ValueError),
        (lambda: HeuristicOccupant(parameters={"gain": True}), ValueError),
        (lambda: HeuristicOccupant(parameters={"gain": math.inf}), ValueError),
        (lambda: HeuristicOccupant(parameters=[]), TypeError),
    ),
)
def test_occupant_constructors_reject_noncanonical_configuration(factory, error):
    with pytest.raises(error):
        factory()


@pytest.mark.parametrize(
    "spec",
    (
        {"type": "null", "extra": 1},
        {
            "type": "random_fuzz", "seed": "1",
            "action_probability": 0.5, "max_actions": 2,
        },
        {
            "type": "random_fuzz", "seed": 1,
            "action_probability": "0.5", "max_actions": 2,
        },
        {
            "type": "scheduled",
            "schedule": {0: []},
        },
        {
            "type": "scheduled",
            "schedule": {"01": []},
        },
        {
            "type": "scheduled",
            "schedule": {"0": ()},
        },
        {
            "type": "scheduled",
            "schedule": {"0": [{"lever": 1, "value": 0}]},
        },
        {
            "type": "scheduled",
            "schedule": {"0": [{"lever": "x", "value": 0, "extra": 1}]},
        },
        {"type": "rl", "replay_mode": "model_pickle"},
    ),
)
def test_occupant_spec_parser_rejects_coercions_and_wrong_shapes(spec):
    with pytest.raises((TypeError, ValueError)):
        occupant_from_spec(spec)


def test_custom_subclasses_and_callable_heuristics_are_not_canonical_events():
    class CustomNull(NullOccupant):
        pass

    custom_subclass = CustomNull()
    custom_rule = HeuristicOccupant(rule=lambda _context: ())
    with pytest.raises(TypeError, match="replay factory"):
        occupant_spec(custom_subclass)
    with pytest.raises(TypeError, match="replay factory"):
        occupant_spec(custom_rule)

    session = ControlledSimulationSession(_world(1523))
    with pytest.raises(TypeError, match="replay factory"):
        session.assign_seat(0, "treasury", custom_subclass)
    # Trusted application genesis remains possible when it is supplied on both
    # sides of a replay and deliberately omitted from the canonical event tape.
    session.assign_seat(0, "treasury", custom_subclass, log_event=False)
    assert session.seat_assignments[(0, "treasury")] is custom_subclass
    assert session.events.events == []
