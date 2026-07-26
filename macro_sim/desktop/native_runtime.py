"""M10 Python desktop worker backed exclusively by native economic state."""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from datetime import date, timedelta
from numbers import Integral
from typing import Any

from macro_sim.controllers import DEFAULT_OBSERVATION_SPEC, ReleaseService
from macro_sim.controllers.native_observation import NativeObservationSource
from macro_sim.core.policy_registry import (
    Bool,
    Choices,
    EconomyId,
    EconomySet,
    NullableRange,
    Range,
    REGISTRY,
)
from macro_sim.desktop.new_game import NewGameSpec
from macro_sim.native_backend import NativeSimulationSession


NATIVE_DESKTOP_PROTOCOL_VERSION = 1
_SERIES_LIMIT = 160


def _strict_positive_int(name: str, value: Any, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    checked = int(value)
    if not 1 <= checked <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return checked


def _validation_schema(validation: Any) -> dict[str, Any]:
    if isinstance(validation, Range):
        return {"kind": "number", "minimum": validation.lo, "maximum": validation.hi}
    if isinstance(validation, NullableRange):
        return {
            "kind": "nullable_number",
            "minimum": validation.lo,
            "maximum": validation.hi,
        }
    if isinstance(validation, Choices):
        return {"kind": "choice", "values": list(validation.values)}
    if isinstance(validation, Bool):
        return {"kind": "boolean"}
    if isinstance(validation, EconomyId):
        return {"kind": "nullable_economy_id"}
    if isinstance(validation, EconomySet):
        return {"kind": "economy_id_set"}
    return {"kind": "unknown"}


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
        self._series: deque[dict[str, Any]] = deque(maxlen=_SERIES_LIMIT)
        self._record_current_frame()
        return self.snapshot()

    @property
    def tick(self) -> int:
        return self.session.tick

    def _run_complete(self) -> bool:
        horizon = self.spec.duration_ticks
        return horizon is not None and self.tick >= horizon

    def _record_current_frame(self) -> None:
        frame = self.session.public_metrics()
        self._series.append({
            "boundary": int(frame["tick"]),
            "economies": [dict(row) for row in frame["economies"]],
        })

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
            self._record_current_frame()
            if actions:
                self._last_policy_event = {
                    "status": "effective",
                    "accepted_boundary": self.tick - 1,
                    "effective_boundary": self.tick,
                    "actions": list(actions),
                }
                self._policy_draft = ()
            advanced += 1
        result = self.snapshot()
        result["advanced_ticks"] = advanced
        return result

    def schema(self) -> dict[str, Any]:
        return {
            "protocol_version": NATIVE_DESKTOP_PROTOCOL_VERSION,
            "backend": "native_m10_world",
            "policy_count": len(REGISTRY),
            "levers": [{
                "id": name,
                "scope": lever.scope,
                "seat_id": lever.owner_role,
                "decision_group_id": lever.decision_group,
                "validation": _validation_schema(lever.validation),
            } for name, lever in REGISTRY.items()],
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

    def snapshot(self) -> dict[str, Any]:
        boundary = self.tick
        current = self.session.public_metrics()
        observation = self.releases.observe(
            self.source,
            boundary,
            economy_id=self.player_economy,
            role="treasury",
            elapsed_ticks=0,
        )
        diagnostics = self.session.probe_economy_diagnostics(
            self.player_economy,
        )
        start = date.fromisoformat(self.spec.start_date)
        return {
            "protocol_version": NATIVE_DESKTOP_PROTOCOL_VERSION,
            "backend": "native_m10_world",
            "control_mode": "free_policy",
            "boundary": boundary,
            "date": (start + timedelta(days=boundary)).isoformat(),
            "tick_reference": boundary,
            "new_game": {
                "contract_hash": self.spec.contract_hash,
                "duration_ticks": self.spec.duration_ticks,
                "run_complete": self._run_complete(),
                "remaining_ticks": (
                    None if self.spec.duration_ticks is None else max(
                        0, self.spec.duration_ticks - boundary,
                    )
                ),
                "player_economy_id": self.player_economy,
                "countries": [{
                    "economy_id": index,
                    "code": country.code,
                    "profile_id": country.profile,
                } for index, country in enumerate(self.spec.countries)],
            },
            "public_metrics": {
                "boundary": int(current["tick"]),
                "economies": [dict(row) for row in current["economies"]],
            },
            "released_observation": observation.to_dict(),
            "series": list(self._series),
            "policy_values": self.session.policy_values(self.player_economy),
            "policy_draft": list(self._policy_draft),
            "last_policy_event": self._last_policy_event,
            "entity_counts": {
                key: diagnostics[key]
                for key in (
                    "households", "firms", "banks", "persons_alive",
                    "jobs_active", "dwellings_active",
                )
            },
            "shock_bulletins": list(self.session.shock_bulletins(
                self.player_economy, boundary,
            )),
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
