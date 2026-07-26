"""Protocol-v4 desktop worker backed exclusively by native economic state."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from numbers import Integral
from typing import Any

from macro_sim.controllers import DEFAULT_OBSERVATION_SPEC, ReleaseService
from macro_sim.controllers.coordinator import SEATS
from macro_sim.controllers.native_observation import NativeObservationSource
from macro_sim.controllers.protocol import CONTROLLER_SCHEMA_VERSION
from macro_sim.core.policy_registry import (
    Bool,
    Choices,
    EconomyId,
    EconomySet,
    IntRange,
    NullableRange,
    Range,
    REGISTRY,
)
from macro_sim.desktop.native_projection import (
    DESKTOP_PROTOCOL_VERSION,
    NativeDesktopProjection,
)
from macro_sim.desktop.new_game import NewGameSpec
from macro_sim.native_backend import NativeSimulationSession


NATIVE_DESKTOP_PROTOCOL_VERSION = DESKTOP_PROTOCOL_VERSION


def _strict_positive_int(name: str, value: Any, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    checked = int(value)
    if not 1 <= checked <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return checked


def _validation_schema(validation: Any) -> dict[str, Any]:
    if isinstance(validation, IntRange):
        return {
            "value_kind": "integer",
            "minimum": int(validation.lo),
            "maximum": int(validation.hi),
            "nullable": False,
        }
    if isinstance(validation, NullableRange):
        return {
            "value_kind": "number",
            "minimum": validation.lo,
            "maximum": validation.hi,
            "nullable": True,
        }
    if isinstance(validation, Range):
        return {
            "value_kind": "number",
            "minimum": validation.lo,
            "maximum": validation.hi,
            "nullable": False,
        }
    if isinstance(validation, Choices):
        return {
            "value_kind": "choice",
            "choices": list(validation.values),
            "nullable": False,
        }
    if isinstance(validation, Bool):
        return {"value_kind": "bool", "nullable": False}
    if isinstance(validation, EconomyId):
        return {"value_kind": "economy_id", "nullable": True}
    if isinstance(validation, EconomySet):
        return {"value_kind": "economy_set", "nullable": False}
    return {"value_kind": "unknown", "nullable": False}


class NativeSimulationRuntime:
    """Single-writer free-policy runtime for the M10 native desktop path.

    The runtime exposes stable identifiers and typed values.  Localized labels
    remain a Godot/catalog concern; no translated display prose is assembled
    here.
    """

    protocol_version = NATIVE_DESKTOP_PROTOCOL_VERSION

    def __init__(self, *, seed: int = 7) -> None:
        self._seed = seed
        self.reset(seed=seed)

    def reset(
        self, *, seed: int | None = None,
        spec: Mapping[str, Any] | NewGameSpec | None = None,
    ) -> dict[str, Any]:
        if spec is None:
            selected_seed = self._seed if seed is None else seed
            if isinstance(selected_seed, bool) or not isinstance(
                selected_seed, Integral,
            ):
                raise TypeError("seed must be an integer")
            selected_seed = int(selected_seed)
            if not 0 <= selected_seed <= 2_147_483_647:
                raise ValueError("seed is outside the supported range")
            normalized = NewGameSpec.default(
                seed=selected_seed,
            )
        elif isinstance(spec, NewGameSpec):
            normalized = spec
        else:
            normalized = NewGameSpec.from_mapping(spec)
        if seed is not None and normalized.seed != seed:
            raise ValueError("new_game seed and spec.seed disagree")
        session = NativeSimulationSession.create(normalized)
        self._seed = normalized.seed
        self.spec = normalized
        self.session = session
        self.player_economy = normalized.player_country
        self.source = NativeObservationSource(session)
        self.releases = ReleaseService(DEFAULT_OBSERVATION_SPEC)
        self._policy_draft: tuple[dict[str, Any], ...] = ()
        self._last_policy_event: dict[str, Any] | None = None
        self.projection = NativeDesktopProjection(
            session, normalized, self.player_economy
        )
        return self.snapshot()

    @property
    def tick(self) -> int:
        return self.session.tick

    def _run_complete(self) -> bool:
        horizon = self.spec.duration_ticks
        return horizon is not None and self.tick >= horizon

    def stage_policy(self, actions: list[Mapping[str, Any]]) -> dict[str, Any]:
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[int, str]] = set()
        for index, action in enumerate(actions):
            if not isinstance(action, Mapping):
                raise TypeError(f"actions[{index}] must be an object")
            if set(action) not in (
                {"lever", "value"},
                {"economy_id", "lever", "value"},
            ):
                raise ValueError(
                    f"actions[{index}] must contain lever/value and optional economy_id"
                )
            economy_id = action.get("economy_id", self.player_economy)
            if isinstance(economy_id, bool) or not isinstance(economy_id, int):
                raise TypeError(f"actions[{index}].economy_id must be an integer")
            lever_name = action["lever"]
            if not isinstance(lever_name, str) or lever_name not in REGISTRY:
                raise ValueError(f"actions[{index}] names an unknown policy lever")
            key = (economy_id, lever_name)
            if key in seen:
                raise ValueError(f"actions contain duplicate policy lever {key!r}")
            seen.add(key)
            normalized.append({
                "economy_id": economy_id,
                "lever": lever_name,
                "value": action["value"],
            })
        # The native policy batch builder performs full wire/domain and
        # cross-policy validation without mutating the committed World.
        self._policy_draft = self.session.validate_actions(normalized)
        self._last_policy_event = {
            "status": "staged" if normalized else "cleared",
            "accepted_boundary": self.tick,
            "effective_boundary": self.tick + 1 if normalized else None,
            "accepted_tick": self.tick,
            "effective_tick": self.tick + 1 if normalized else None,
            "actions": list(self._policy_draft),
        }
        return self.snapshot()

    def advance(self, ticks: int = 1) -> dict[str, Any]:
        requested = _strict_positive_int("ticks", ticks, 10_000)
        advanced = 0
        while advanced < requested and not self._run_complete():
            actions = self._policy_draft if advanced == 0 else ()
            self.session.advance(actions=actions)
            self.source.refresh()
            self.projection.refresh()
            if actions:
                self._last_policy_event = {
                    "status": "effective",
                    "accepted_boundary": self.tick - 1,
                    "effective_boundary": self.tick,
                    "accepted_tick": self.tick - 1,
                    "effective_tick": self.tick,
                    "actions": list(actions),
                }
                self._policy_draft = ()
            advanced += 1
        result = self.snapshot()
        result["advanced_ticks"] = advanced
        return result

    def _lever_schema(
        self, name: str, current_values: Mapping[str, Any]
    ) -> dict[str, Any]:
        lever = REGISTRY[name]
        row = {
                "name": name,
                "current_value": current_values[name],
                "scope": lever.scope,
                "owner_role": lever.owner_role,
                "decision_group": lever.decision_group,
                "implementation_lag": lever.implementation_lag,
                "emergency_implementation_lag":
                    lever.emergency_implementation_lag,
                "min_hold_ticks": lever.min_hold_ticks,
                "emergency": lever.emergency,
                "control_scale": lever.control_scale,
                "max_step": getattr(lever.validation, "max_step", None),
                "admin_weight": lever.admin_weight,
                "cost_class": lever.cost_class,
                "semantics": lever.semantics,
                "requires": sorted(lever.requires),
                "enabled_if": sorted(lever.enabled_if),
                "shadowed_by": list(lever.shadowed_by),
                "help_key": f"policy.{name}",
        }
        row.update(_validation_schema(lever.validation))
        if isinstance(lever.validation, EconomyId):
            row["choices"] = [
                economy_id
                for economy_id in range(len(self.spec.countries))
                if economy_id != self.player_economy
            ] + [None]
        elif isinstance(lever.validation, EconomySet):
            row["choices"] = [
                economy_id
                for economy_id in range(len(self.spec.countries))
                if economy_id != self.player_economy
            ]
        return row

    def schema(self) -> dict[str, Any]:
        current_values = self.session.policy_values(self.player_economy)
        seats = {
            seat: {
                "schema_version": CONTROLLER_SCHEMA_VERSION,
                "economy_id": self.player_economy,
                "seat": seat,
                "levers": [
                    self._lever_schema(name, current_values)
                    for name, lever in sorted(REGISTRY.items())
                    if lever.owner_role == seat
                ],
            }
            for seat in SEATS
        }
        return {
            "protocol_version": NATIVE_DESKTOP_PROTOCOL_VERSION,
            "control_mode": "free_policy",
            "seats": seats,
            "levers": seats["treasury"]["levers"],
            "seat": "treasury",
            "economy_id": self.player_economy,
            "schema_version": CONTROLLER_SCHEMA_VERSION,
        }

    def entity_page(
        self, kind: str, *, economy_id: int | None = None,
        after_id: int = 0, maximum_rows: int = 256,
    ) -> dict[str, Any]:
        return self.session.probe_page(
            kind,
            economy_id=(
                self.player_economy if economy_id is None else economy_id
            ),
            after_id=after_id,
            maximum_rows=maximum_rows,
        )

    def checkpoint(self) -> bytes:
        return self.session.checkpoint(b'{"client":"native_desktop_m10"}')

    def _client_policy_actions(self) -> list[dict[str, Any]]:
        return [
            {
                "lever": str(action["lever"]),
                "value": action["value"],
            }
            for action in self._policy_draft
            if int(action.get("economy_id", self.player_economy))
            == self.player_economy
        ]

    def _merged_observation(self) -> dict[str, Any]:
        merged: dict[str, dict[str, Any]] = {}
        metadata: dict[str, Any] = {}
        for seat in SEATS:
            observation = self.releases.observe(
                self.source,
                self.tick,
                economy_id=self.player_economy,
                role=seat,
                elapsed_ticks=0,
            ).to_dict()
            for key, value in observation.items():
                if key != "releases":
                    metadata.setdefault(key, value)
            for release in observation.get("releases", []):
                if not isinstance(release, dict):
                    continue
                series_id = str(release.get("series_id", ""))
                held = merged.get(series_id)
                if held is None or (
                    held.get("value") is None
                    and release.get("value") is not None
                ):
                    merged[series_id] = dict(release)
        metadata["releases"] = [
            merged[series_id] for series_id in sorted(merged)
        ]
        return metadata

    def snapshot(self) -> dict[str, Any]:
        boundary = self.tick
        projection = self.projection.snapshot_fields()
        start = date.fromisoformat(self.spec.start_date)
        remaining = (
            None if self.spec.duration_ticks is None else max(
                0, self.spec.duration_ticks - boundary
            )
        )
        draft = list(self._policy_draft)
        client_actions = self._client_policy_actions()
        bulletins = list(self.session.shock_bulletins(
            self.player_economy, boundary,
        ))
        active_shocks = [
            dict(item)
            for item in bulletins
            if str(item.get("status", "")) in {"active", "realizing"}
        ]
        return {
            "protocol_version": NATIVE_DESKTOP_PROTOCOL_VERSION,
            "backend": "native_m10_world",
            "control_mode": "free_policy",
            "boundary": boundary,
            "tick": boundary,
            "date": (start + timedelta(days=boundary)).isoformat(),
            "tick_reference": boundary,
            "phase": "boundary_start",
            "awaiting_human": False,
            "new_game": {
                "schema_version": self.spec.schema_version,
                "model_id": self.spec.model_id,
                "contract_hash": self.spec.contract_hash,
                "spec": self.spec.to_dict(),
                "duration_ticks": self.spec.duration_ticks,
                "run_complete": self._run_complete(),
                "remaining_ticks": remaining,
            },
            "observation": self._merged_observation(),
            "last_verdict": self._last_policy_event,
            **projection,
            "policy_values": self.session.policy_values(self.player_economy),
            "policy_draft": draft,
            "last_policy_event": self._last_policy_event,
            "contexts": [],
            "pending": [],
            "free_policy": {
                "enabled": True,
                "effective_tick": boundary + 1 if client_actions else None,
                "actions": client_actions,
            },
            "shock_bulletins": bulletins,
            "active_shocks": active_shocks,
            "events": (
                [] if self._last_policy_event is None
                else [self._last_policy_event]
            ),
            "shock_events": [],
        }

    def handle(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping):
            raise TypeError("command must be an object")
        name = command.get("command")
        if name in {"hello", "snapshot"}:
            return self.snapshot()
        if name == "new_game":
            return self.reset(
                seed=command.get("seed") if "spec" not in command else None,
                spec=command.get("spec"),
            )
        if name == "advance":
            return self.advance(command.get("ticks", 1))
        if name == "stage_policy":
            actions = command.get("actions", [])
            if not isinstance(actions, list):
                raise TypeError("actions must be an array")
            return self.stage_policy(actions)
        if name == "get_schema":
            return self.schema()
        if name == "entity_page":
            return self.entity_page(
                str(command.get("kind", "")),
                economy_id=command.get("economy_id"),
                after_id=int(command.get("after_id", 0)),
                maximum_rows=int(command.get("maximum_rows", 256)),
            )
        raise ValueError(f"unknown command {name!r}")
