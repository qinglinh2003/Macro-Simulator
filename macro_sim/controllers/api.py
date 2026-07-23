"""Privileged, transport-neutral façade for a future frontend/server layer.

``ControllerService`` is an in-process kernel API, not an authentication boundary.
An outer transport must authenticate principals, authorize their seat/run access,
and serialize mutating calls for each session before invoking this façade.
"""
from __future__ import annotations

from typing import Any, Mapping

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

from .coordinator import SEATS
from .protocol import (
    CONTROLLER_SCHEMA_VERSION,
    PolicyAction,
    PolicyProposal,
    canonical_value,
)
from .session import ControlledSimulationSession


def _strict_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


class ControllerService:
    """The minimum privileged v26 kernel contract, independent of transport."""

    def __init__(self, session: ControlledSimulationSession) -> None:
        self.session = session

    def _economy_id(self, economy_id: Any) -> int:
        if isinstance(economy_id, bool) or not isinstance(economy_id, int):
            raise TypeError("economy_id must be an integer")
        economies = getattr(self.session.world, "economies", None)
        economy_count = len(economies) if economies is not None else 1
        if not 0 <= economy_id < economy_count:
            raise ValueError("economy_id is out of range")
        return economy_id

    @staticmethod
    def _seat(seat: Any) -> str:
        if not isinstance(seat, str) or seat not in SEATS:
            raise ValueError(f"unknown policy seat: {seat!r}")
        return seat

    def policy_schema(self, *, economy_id: int, seat: str) -> dict[str, Any]:
        economy_id = self._economy_id(economy_id)
        seat = self._seat(seat)
        economies = getattr(self.session.world, "economies", None)
        economy = (
            economies[economy_id]
            if economies is not None
            else self.session.world
        )
        levers: list[dict[str, Any]] = []
        for name, lever in sorted(REGISTRY.items()):
            if lever.owner_role != seat:
                continue
            if lever.scope == "external" and not hasattr(economy, "external_policy"):
                continue
            validation = lever.validation
            holder = (
                economy.external_policy
                if lever.scope == "external" else economy.policy
            )
            row: dict[str, Any] = {
                "name": name,
                "current_value": getattr(holder, name),
                "scope": lever.scope,
                "owner_role": lever.owner_role,
                "decision_group": lever.decision_group,
                "implementation_lag": lever.implementation_lag,
                "emergency_implementation_lag": lever.emergency_implementation_lag,
                "min_hold_ticks": lever.min_hold_ticks,
                "emergency": lever.emergency,
                "control_scale": lever.control_scale,
                "max_step": getattr(validation, "max_step", None),
                "admin_weight": lever.admin_weight,
                "cost_class": lever.cost_class,
                "semantics": lever.semantics,
                "requires": sorted(lever.requires),
                "enabled_if": sorted(lever.enabled_if),
                "shadowed_by": list(lever.shadowed_by),
                "read_point": lever.read_point,
                "state_notes": lever.state_notes,
            }
            if isinstance(validation, IntRange):
                row.update(
                    value_kind="integer",
                    minimum=int(validation.lo),
                    maximum=int(validation.hi),
                    nullable=False,
                )
            elif isinstance(validation, NullableRange):
                row.update(
                    value_kind="number",
                    minimum=validation.lo,
                    maximum=validation.hi,
                    nullable=True,
                )
            elif isinstance(validation, Range):
                row.update(
                    value_kind="number",
                    minimum=validation.lo,
                    maximum=validation.hi,
                    nullable=False,
                )
            elif isinstance(validation, Bool):
                row.update(value_kind="bool", nullable=False)
            elif isinstance(validation, Choices):
                row.update(
                    value_kind="choice",
                    choices=list(validation.values),
                    nullable=False,
                )
            elif isinstance(validation, EconomyId):
                row.update(
                    value_kind="economy_id",
                    choices=[
                        index
                        for index in range(len(getattr(self.session.world, "economies", [self.session.world])))
                        if index != economy_id
                    ] + [None],
                    nullable=True,
                )
            elif isinstance(validation, EconomySet):
                row.update(
                    value_kind="economy_set",
                    choices=[
                        index
                        for index in range(len(getattr(self.session.world, "economies", [self.session.world])))
                        if index != economy_id
                    ],
                    nullable=False,
                )
            levers.append(row)
        return canonical_value({
            "schema_version": CONTROLLER_SCHEMA_VERSION,
            "economy_id": economy_id,
            "seat": seat,
            "levers": levers,
        })

    def decision_context(self, context_id: str) -> dict[str, Any]:
        context_id = _strict_text("context_id", context_id)
        context = self.session.coordinator.contexts.get(context_id)
        if context is None:
            raise KeyError(context_id)
        return context.to_dict()

    def shock_bulletins(self, *, economy_id: int, seat: str) -> dict[str, Any]:
        """Read the same disclosed shock bulletin available to this policy seat."""
        economy_id = self._economy_id(economy_id)
        seat = self._seat(seat)
        from macro_sim.shocks import get_shock_engine

        shock_engine = get_shock_engine(self.session.world)
        rows = () if shock_engine is None else shock_engine.bulletins(
            economy_id, self.session.boundary_tick, role=seat,
        )
        return canonical_value({
            "schema_version": CONTROLLER_SCHEMA_VERSION,
            "boundary_tick": self.session.boundary_tick,
            "economy_id": economy_id,
            "seat": seat,
            "shock_bulletins": list(rows),
        })

    def pending(self, *, economy_id: int | None = None) -> list[dict[str, Any]]:
        if economy_id is not None:
            economy_id = self._economy_id(economy_id)
        rows = []
        for decision_id, item in sorted(self.session.coordinator.pending.items()):
            if item.status != "accepted_pending":
                continue
            if economy_id is not None and item.context.economy_id != economy_id:
                continue
            rows.append(canonical_value({
                "decision": item.decision,
                "context_id": item.context.context_id,
                "actions": [action.to_dict() for action in item.proposal.actions],
                "status": item.status,
                "reserved_admin_cost": item.reserved_admin_cost,
                "adjustment_cost": item.adjustment_cost,
            }))
        return rows

    def submit_proposal(self, payload: Mapping[str, Any], *, actor: str) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise TypeError("proposal payload must be a mapping")
        actor = _strict_text("actor", actor)
        if not all(isinstance(key, str) for key in payload):
            raise TypeError("proposal payload keys must be strings")
        required = {
            "schema_version", "proposal_id", "idempotency_key", "context_id",
            "actions", "based_on_policy_versions",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"proposal payload missing required fields: {missing}")
        allowed = required | {"reason", "supersedes_proposal_id"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"proposal payload has unknown fields: {unknown}")

        def text_field(name: str) -> str:
            return _strict_text(name, payload[name])

        schema_version = payload["schema_version"]
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise TypeError("schema_version must be an integer")
        if schema_version != CONTROLLER_SCHEMA_VERSION:
            raise ValueError(f"unsupported controller schema version {schema_version}")
        raw_actions = payload["actions"]
        if not isinstance(raw_actions, (list, tuple)):
            raise TypeError("actions must be an array")
        actions = []
        for index, item in enumerate(raw_actions):
            if not isinstance(item, Mapping):
                raise TypeError(f"actions[{index}] must be an object")
            if set(item) != {"lever", "value"}:
                raise ValueError(f"actions[{index}] must contain exactly lever and value")
            lever = _strict_text(f"actions[{index}].lever", item["lever"])
            actions.append(PolicyAction(lever, item["value"]))
        versions = payload["based_on_policy_versions"]
        if not isinstance(versions, Mapping):
            raise TypeError("based_on_policy_versions must be an object")
        reason = payload.get("reason", "")
        if not isinstance(reason, str):
            raise TypeError("reason must be a string")
        supersedes = payload.get("supersedes_proposal_id")
        if supersedes is not None:
            supersedes = _strict_text("supersedes_proposal_id", supersedes)
        proposal = PolicyProposal(
            proposal_id=text_field("proposal_id"),
            idempotency_key=text_field("idempotency_key"),
            context_id=text_field("context_id"),
            actions=tuple(actions),
            reason=reason,
            based_on_policy_versions=versions,
            supersedes_proposal_id=supersedes,
            schema_version=schema_version,
        )
        self.session.submit_human_proposal(proposal, actor=actor)
        existing_id = self.session.coordinator.idempotency.get(proposal.idempotency_key)
        if existing_id is not None:
            return canonical_value(self.session.coordinator.decisions[existing_id])
        return {"status": "queued", "proposal_id": proposal.proposal_id}

    def cancel_pending(self, decision_id: str, *, actor: str) -> dict[str, Any]:
        decision_id = _strict_text("decision_id", decision_id)
        actor = _strict_text("actor", actor)
        return canonical_value(self.session.cancel_pending(decision_id, actor=actor))

    def assign_seat(
        self,
        *,
        economy_id: int,
        seat: str,
        occupant: Any,
        actor: str,
        initialization: str = "fresh",
    ) -> None:
        economy_id = self._economy_id(economy_id)
        seat = self._seat(seat)
        actor = _strict_text("actor", actor)
        initialization = _strict_text("initialization", initialization)
        if initialization != "fresh" and not initialization.startswith("restore:"):
            raise ValueError(
                "initialization must be 'fresh' or 'restore:<id>'"
            )
        if initialization.startswith("restore:"):
            archived_id = initialization.split(":", 1)[1]
            if not archived_id.strip():
                raise ValueError(
                    "initialization must be 'fresh' or 'restore:<id>'"
                )
        if isinstance(occupant, type) or not callable(getattr(occupant, "propose", None)):
            raise TypeError("occupant must implement callable propose(context)")
        self.session.assign_seat(
            economy_id,
            seat,
            occupant,
            actor=actor,
            initialization=initialization,
        )
