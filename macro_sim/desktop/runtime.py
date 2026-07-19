"""Transport-neutral state machine used by the Godot desktop prototype.

The adapter deliberately owns no policy logic.  It translates small JSON commands
into the existing controller and shock APIs so the desktop client cannot mutate the
engine behind their validation, timing, or audit trails.
"""
from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from macro_sim.config import Config
from macro_sim.controllers import (
    ControlledSimulationSession,
    ControllerService,
    HumanQueueOccupant,
)
from macro_sim.shocks import ShockSpec, get_shock_engine
from macro_sim.world import World


PROTOCOL_VERSION = 1
SERIES_LIMIT = 160
METRIC_NAMES = (
    "real_output",
    "unemployment_rate",
    "inflation",
    "price_index",
    "avg_wage",
    "energy_price",
)


def _integer(name: str, value: Any, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _finite_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    number = float(value)
    return number if math.isfinite(number) else default


class SimulationRuntime:
    """Single-writer façade for one interactive simulation run."""

    def __init__(self, *, seed: int = 7) -> None:
        self._seed = seed
        self._proposal_sequence = 0
        self._shock_sequence = 0
        self._history: list[dict[str, float | int]] = []
        self._last_records: list[dict[str, Any]] = []
        self.world: World
        self.session: ControlledSimulationSession
        self.service: ControllerService
        self.reset(seed=seed)

    def reset(self, *, seed: int | None = None) -> dict[str, Any]:
        if seed is not None:
            self._seed = _integer("seed", seed, minimum=0, maximum=2_147_483_647)
        config = Config.v124(
            n_households=80,
            n_firms_c=12,
            n_firms_k=4,
            n_ticks=10_000,
            seed=self._seed,
            energy_enabled=True,
        )
        self.world = World([config])
        self.session = ControlledSimulationSession(self.world, run_mode="interactive")
        self.session.assign_seat(
            0, "treasury", HumanQueueOccupant(), actor="desktop_prototype"
        )
        self.service = ControllerService(self.session)
        self._proposal_sequence = 0
        self._shock_sequence = 0
        self._history = []
        self._last_records = []
        # Open tick-zero decision windows immediately so the UI has something real
        # to operate rather than inventing a separate frontend policy form.
        self.session.advance()
        return self.snapshot()

    def handle(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping):
            raise TypeError("command must be an object")
        name = command.get("command")
        if not isinstance(name, str) or not name:
            raise ValueError("command.command must be a non-empty string")
        if name in {"hello", "snapshot"}:
            return self.snapshot()
        if name == "new_game":
            seed = command.get("seed", self._seed)
            return self.reset(seed=seed)
        if name == "advance":
            ticks = _integer("ticks", command.get("ticks", 1), minimum=1, maximum=100)
            return self.advance(ticks)
        if name == "resolve_context":
            context_id = command.get("context_id")
            if not isinstance(context_id, str) or not context_id:
                raise ValueError("context_id must be a non-empty string")
            actions = command.get("actions", [])
            if not isinstance(actions, list):
                raise TypeError("actions must be an array")
            return self.resolve_context(context_id, actions)
        if name == "trigger_shock":
            return self.trigger_shock()
        raise ValueError(f"unknown command {name!r}")

    def advance(self, ticks: int) -> dict[str, Any]:
        advanced = 0
        while advanced < ticks:
            result = self.session.advance()
            if result.status == "awaiting_human":
                break
            advanced += 1
            self._record_result(result.records)
        snapshot = self.snapshot()
        snapshot["advanced_ticks"] = advanced
        return snapshot

    def resolve_context(
        self, context_id: str, actions: list[Mapping[str, Any]]
    ) -> dict[str, Any]:
        if context_id not in self.session.missing_context_ids:
            raise ValueError("context is not awaiting a desktop decision")
        context = self.session.coordinator.contexts[context_id]
        normalized_actions: list[dict[str, Any]] = []
        for index, action in enumerate(actions):
            if not isinstance(action, Mapping):
                raise TypeError(f"actions[{index}] must be an object")
            if set(action) != {"lever", "value"}:
                raise ValueError(f"actions[{index}] must contain lever and value")
            normalized_actions.append({"lever": action["lever"], "value": action["value"]})
        self._proposal_sequence += 1
        proposal_id = f"desktop:{self._proposal_sequence}:{context_id}"
        self.service.submit_proposal(
            {
                "schema_version": context.schema_version,
                "proposal_id": proposal_id,
                "idempotency_key": proposal_id,
                "context_id": context_id,
                "actions": normalized_actions,
                "reason": "desktop_player_action" if actions else "desktop_player_pass",
                "based_on_policy_versions": dict(context.policy_versions),
            },
            actor="desktop_player",
        )
        result = self.session.advance()
        if result.status == "advanced":
            self._record_result(result.records)
        return self.snapshot()

    def trigger_shock(self) -> dict[str, Any]:
        self._shock_sequence += 1
        start_tick = self.session.boundary_tick + 1
        self.world.schedule_shock(
            ShockSpec(
                shock_id=f"desktop_supply_disruption:{self._shock_sequence}",
                kind="productivity",
                start_tick=start_tick,
                magnitude=0.25,
                duration_ticks=20,
                announcement_tick=start_tick,
                source="desktop_prototype",
                calibration_note="Player-triggered prototype supply disruption.",
                tags=("desktop", "prototype"),
            )
        )
        return self.snapshot()

    def _record_result(self, records: Any) -> None:
        if isinstance(records, list):
            rows = [row for row in records if isinstance(row, dict)]
        elif isinstance(records, dict):
            rows = [records]
        else:
            rows = []
        self._last_records = rows
        if not rows:
            return
        row = rows[0]
        point: dict[str, float | int] = {"tick": self.session.boundary_tick}
        for name in METRIC_NAMES:
            point[name] = _finite_number(row.get(name))
        self._history.append(point)
        del self._history[:-SERIES_LIMIT]

    def snapshot(self) -> dict[str, Any]:
        missing = set(self.session.missing_context_ids)
        contexts = [
            self.service.decision_context(context_id)
            for context_id in self.session.current_context_ids
            if context_id in missing
        ]
        latest = self._history[-1] if self._history else {"tick": 0}
        metrics = {
            name: _finite_number(latest.get(name))
            for name in METRIC_NAMES
        }
        shock_engine = get_shock_engine(self.world)
        shock_events = []
        active_shocks = []
        if shock_engine is not None:
            shock_events = list(shock_engine.events.events[-20:])
            active_shocks = [
                spec.to_dict()
                for spec in shock_engine.specs
                if spec.intensity_at(self.session.boundary_tick) > 0
            ]
        return {
            "protocol_version": PROTOCOL_VERSION,
            "tick": self.session.boundary_tick,
            "phase": self.session.phase,
            "awaiting_human": bool(self.session.missing_context_ids),
            "metrics": metrics,
            "series": list(self._history),
            "contexts": contexts,
            "pending": self.service.pending(economy_id=0),
            "shock_bulletins": self.service.shock_bulletins(
                economy_id=0, seat="treasury"
            )["shock_bulletins"],
            "active_shocks": active_shocks,
            "events": list(self.session.events.events[-30:]),
            "shock_events": shock_events,
        }
