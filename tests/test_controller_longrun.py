"""Explicit slow acceptance: 30 years of legal fuzz for three deterministic seeds.

The normal suite skips this file's long cases.  Release acceptance runs it with
``RUN_LONG_CONTROLLER_TESTS=1`` so everyday development does not silently acquire a
multi-minute tax.
"""
from __future__ import annotations

import os

import pytest

from macro_sim.checkpoint import session_digest
from macro_sim.config import Config
from macro_sim.controllers.coordinator import SEATS
from macro_sim.controllers.observation import ObservationSpec, ReleaseService
from macro_sim.controllers.occupants import RandomFuzzOccupant
from macro_sim.controllers.session import ControlledSimulationSession
from macro_sim.controllers.transaction import world_policy_fingerprint
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.world import World


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LONG_CONTROLLER_TESTS") != "1",
    reason="set RUN_LONG_CONTROLLER_TESTS=1 for the 30-year controller acceptance",
)


@pytest.mark.parametrize("seed", [1_101, 1_102, 1_103])
def test_thirty_year_legal_fuzz_conserves_and_remains_registry_valid(seed: int):
    ticks = 30 * 365
    cfg = Config.v13(
        seed=seed,
        n_households=6,
        n_firms_c=4,
        n_firms_k=2,
        n_banks=1,
        n_ticks=ticks + 1,
        government=True,
    )
    # Couple=True exercises the FX/peg derived state without paying the much larger
    # trade/capital long-run cost.  Structural capability masking for trade, capital,
    # migration, and sanctions is covered separately; every lever legal in this World
    # still passes through the same Coordinator and World transaction path.
    session = ControlledSimulationSession(
        World([cfg, cfg], base_seed=seed * 10, couple=True),
        # Release semantics have dedicated acceptance tests.  Empty releases keep
        # this 30-year invariant/fuzz gate on the identical controller and economy
        # RNG path without retaining hundreds of thousands of unused vintages.
        release_service=ReleaseService(ObservationSpec(())),
    )
    for economy_id in range(2):
        for seat_index, seat in enumerate(SEATS):
            session.assign_seat(
                economy_id,
                seat,
                RandomFuzzOccupant(
                    seed=seed * 100 + economy_id * 10 + seat_index,
                    action_probability=0.15,
                    max_actions=1,
                ),
                actor="longrun_fuzz",
                log_event=False,
            )

    try:
        session.run(ticks)
    except Exception as exc:
        exc.add_note(
            f"30-year controller seed={seed}, boundary_tick={session.boundary_tick}, "
            f"world_tick={session.world.t}"
        )
        raise

    assert session.boundary_tick == session.world.t == ticks
    assert session.policy_fingerprint == world_policy_fingerprint(session.world)
    assert session.coordinator.decisions
    session.events.verify()
    assert len(session_digest(session)) == 64
    for economy in session.world.economies:
        economy.ledger.assert_conserved()
        economy.ledger.assert_non_negative()
        for name, lever in REGISTRY.items():
            holder = economy.external_policy if lever.scope == "external" else economy.policy
            value = getattr(holder, name)
            assert lever.validation.check(value, value) is None, name
