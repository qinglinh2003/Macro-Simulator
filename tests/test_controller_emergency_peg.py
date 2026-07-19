"""Causal emergency drill: a boundary response cannot rescue an already-broken peg."""
from __future__ import annotations

from macro_sim.config import Config
from macro_sim.controllers.occupants import ScheduledOccupant
from macro_sim.controllers.protocol import PolicyAction
from macro_sim.controllers.scheduler import (
    DEFAULT_CALENDARS,
    CalendarSpec,
    DecisionScheduler,
    TriggerSpec,
)
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.world import World


def _drill(trigger_threshold: float) -> ControlledSimulationSession:
    pegger = Config.v13(
        seed=101,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        n_ticks=20,
        government=True,
        central_bank=False,
        r_interest=0.01,
    )
    anchor = Config.v13(
        seed=102,
        n_households=8,
        n_firms_c=5,
        n_firms_k=3,
        n_banks=1,
        n_ticks=20,
        government=True,
        central_bank=False,
        r_interest=0.05,
    )
    world = World(
        [pegger, anchor],
        trade=True,
        capital=True,
        capital_mobility=1.0,
        capital_adjust=0.1,
        peg=True,
        peg_economy=0,
        peg_anchor=1,
        peg_reserves0=10.0,
        peg_reserve_scale=0.1,
    )
    calendars = {
        name: CalendarSpec(1_000, offset_ticks=999, admin_capacity=100.0)
        for name in DEFAULT_CALENDARS
    }
    trigger = TriggerSpec(
        "peg_reserve_emergency",
        "reserves",
        enter_threshold=trigger_threshold,
        exit_threshold=trigger_threshold + 1.0,
        direction="below",
        min_persist_ticks=1,
        cooldown_ticks=30,
        authorized_seats=("central_bank",),
        decision_group="fx_operations",
    )
    session = ControlledSimulationSession(
        world,
        scheduler=DecisionScheduler(calendars=calendars, triggers=(trigger,)),
    )
    # No regular meeting occurs in the drill.  Whenever the server opens the
    # emergency context, the occupant orders an orderly float at lag zero.
    session.assign_seat(
        0,
        "central_bank",
        ScheduledOccupant({
            tick: (PolicyAction("fx_regime", "float"),)
            for tick in range(1, 10)
        }),
        actor="drill",
        log_event=False,
    )
    session.run(4)
    return session


def test_peg_emergency_response_works_at_next_boundary_but_not_after_break():
    early = _drill(5.0)   # first tick leaves 2.44 reserves; respond at boundary 1
    late = _drill(0.1)    # threshold is seen only at boundary 2, after tick-1 break

    early_types = [event["event_type"] for event in early.events.events]
    late_types = [event["event_type"] for event in late.events.events]

    assert "policy_transaction_effective" in early_types
    assert "forced_system_transition" not in early_types
    assert early.world.peg_states[0].intact is False
    assert early.world.reserves() > 0.0

    assert "forced_system_transition" in late_types
    assert "decision_accepted_noop" in late_types
    assert late.world.reserves() == 0.0
    early.events.verify()
    late.events.verify()
