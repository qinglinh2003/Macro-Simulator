"""Existing Python controller stack over the authoritative native M10 World."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable

from macro_sim.core.external_policy import ExternalPolicy
from macro_sim.core.policy import Policy
from macro_sim.core.policy_registry import EconomySet, REGISTRY

from .protocol import FrozenMapping, PendingDecision, immutable_json_mapping


def _normalized_value(name: str, value: Any) -> Any:
    if isinstance(REGISTRY[name].validation, EconomySet):
        return frozenset(value)
    return value


@dataclass(frozen=True, slots=True)
class NativePreparedPolicyTransaction:
    transaction_id: str
    boundary_tick: int
    base_fingerprint: str
    decision_ids: tuple[str, ...]
    actions: tuple[dict[str, Any], ...]
    projected_values: tuple[dict[str, Any], ...]
    changes: tuple[FrozenMapping, ...]
    versions_before: FrozenMapping
    versions_after: FrozenMapping


@dataclass(slots=True)
class NativeControllerBoundary:
    prepared: Any
    preview_token: Any
    opening_tick: int
    next_tick: int
    records: list[dict[str, Any]]


class _NativeEconomyView:
    """Policy/config/release view; never an economic state owner."""

    def __init__(self, world: "NativeControlledWorld", economy_id: int) -> None:
        self._world = world
        self.economy_id = economy_id
        self.cfg = world.configs[economy_id]
        self.t = world.t
        self.policy = Policy()
        self.external_policy = ExternalPolicy()
        source = getattr(world, "source", None)
        self.records = (
            source.economies[economy_id].records
            if source is not None else []
        )
        self._policy_action_log: list[dict[str, Any]] = []


class _ProjectionLedger:
    """Policy-only projection has no balances, but keeps reconciliation generic."""

    @staticmethod
    def assert_conserved() -> None:
        return None

    @staticmethod
    def assert_non_negative() -> None:
        return None


class _NativePolicyProjection:
    """Small policy graph validated against the native World without agent copies."""

    def __init__(
        self, owner: "NativeControlledWorld", values: Iterable[dict[str, Any]],
    ) -> None:
        self._owner = owner
        self.t = owner.t
        self.trade = owner.trade
        self.capital = owner.capital
        self.migration = owner.migration
        self.couple = owner.couple
        self.configs = owner.configs
        self.economies = [
            _NativeEconomyView(self, economy_id)
            for economy_id in range(len(self.configs))
        ]
        for economy in self.economies:
            economy.ledger = _ProjectionLedger()
        self._install_policy_values(tuple(values))

    def _install_policy_values(
        self, values: tuple[dict[str, Any], ...],
    ) -> None:
        for economy_id, policy_values in enumerate(values):
            economy = self.economies[economy_id]
            for name, lever in REGISTRY.items():
                holder = (
                    economy.external_policy
                    if lever.scope == "external" else economy.policy
                )
                setattr(holder, name, _normalized_value(name, policy_values[name]))

    def _policy_values(self) -> tuple[dict[str, Any], ...]:
        output: list[dict[str, Any]] = []
        for economy in self.economies:
            output.append({
                name: getattr(
                    economy.external_policy
                    if lever.scope == "external" else economy.policy,
                    name,
                )
                for name, lever in REGISTRY.items()
            })
        return tuple(output)

    def clone_policy_projection(self) -> "_NativePolicyProjection":
        return type(self)(self._owner, self._policy_values())

    def _commit_external_policies(self) -> None:
        live = tuple(
            self._owner.native_session.policy_values(economy_id)
            for economy_id in range(len(self.economies))
        )
        projected = self._policy_values()
        actions = [
            {
                "economy_id": economy_id,
                "lever": name,
                "value": value,
            }
            for economy_id, values in enumerate(projected)
            for name, value in values.items()
            if value != _normalized_value(name, live[economy_id][name])
        ]
        validated = self._owner.native_session.projected_policy_values(actions)
        self._install_policy_values(validated)


class NativeControlledWorld:
    """Compatibility view used by schedulers, releases, and policy validation."""

    native_controller_backend = True

    def __init__(
        self, native_session: NativeSimulationSession, configs: Iterable[Any],
        *, trade: bool, capital: bool, migration: bool,
    ) -> None:
        from .native_observation import NativeObservationSource

        self.native_session = native_session
        self.configs = tuple(configs)
        self.t = native_session.tick
        self.trade = bool(trade)
        self.capital = bool(capital)
        self.migration = bool(migration)
        self.couple = len(self.configs) > 1
        self.source = NativeObservationSource(native_session)
        self.world_records = self.source.world_records
        self.economies = [
            _NativeEconomyView(self, economy_id)
            for economy_id in range(len(self.configs))
        ]
        self._staged_actions: tuple[dict[str, Any], ...] = ()
        self._test_fault_point = "none"
        self._install_policy_values(tuple(
            native_session.policy_values(economy_id)
            for economy_id in range(len(self.configs))
        ))

    @staticmethod
    def _release_cursor(session: Any) -> int:
        history = getattr(session.release_service, "_history", {})
        return sum(len(rows) for rows in history.values())

    def sync_controller_state(self, session: Any) -> str:
        """Publish the reconstructable Python controller root into C++ authority."""
        from .native_envelope import encode_controller_state

        if session.world is not self:
            raise ValueError("controller session is bound to another World")
        if session.boundary_tick != self.t:
            raise ValueError("controller/native boundary differs during envelope sync")
        payload = encode_controller_state(session)
        ordered_keys = sorted(session.coordinator.policy_versions)
        versions = [
            int(session.coordinator.policy_versions[key])
            for key in ordered_keys
        ]
        payload_digest = hashlib.sha256(payload).hexdigest()
        operation_id = (
            f"controller-sync:{self.t}:{len(session.events.events)}:"
            f"{payload_digest[:16]}"
        )
        return self.native_session.sync_controller_envelope(
            payload,
            event_sequence=len(session.events.events),
            release_cursor=self._release_cursor(session),
            decision_versions=versions,
            effective_versions=versions,
            operation_id=operation_id,
        )

    def capture_controller_state(self, session: Any) -> bytes:
        from .native_envelope import encode_controller_state

        return encode_controller_state(session)

    def restore_controller_state(self, session: Any, payload: bytes) -> None:
        from .native_envelope import (
            decode_controller_state,
            install_controller_state,
        )

        install_controller_state(session, decode_controller_state(payload))
        self.t = self.native_session.tick
        self.source.refresh()
        self._staged_actions = ()
        self._install_policy_values(tuple(
            self.native_session.policy_values(economy_id)
            for economy_id in range(len(self.economies))
        ))
        for economy in self.economies:
            economy.t = self.t

    def checkpoint_controller(
        self, session: Any, objective_envelope: bytes = b"{}",
    ) -> bytes:
        self.sync_controller_state(session)
        return self.native_session.checkpoint(objective_envelope)

    def _install_policy_values(
        self, values: tuple[dict[str, Any], ...],
    ) -> None:
        for economy_id, policy_values in enumerate(values):
            economy = self.economies[economy_id]
            for name, lever in REGISTRY.items():
                holder = (
                    economy.external_policy
                    if lever.scope == "external" else economy.policy
                )
                setattr(holder, name, _normalized_value(name, policy_values[name]))

    def native_shock_observable(
        self, key: str, economy_id: int, as_of_tick: int,
        *, role: str = "public",
    ) -> float:
        return self.source.native_shock_observable(
            key, economy_id, as_of_tick, role=role,
        )

    def native_shock_bulletins(
        self, economy_id: int, as_of_tick: int, *, role: str = "public",
    ):
        return self.source.native_shock_bulletins(
            economy_id, as_of_tick, role=role,
        )

    def clone_policy_projection(self) -> _NativePolicyProjection:
        return _NativePolicyProjection(
            self,
            tuple(
                self.native_session.policy_values(economy_id)
                for economy_id in range(len(self.economies))
            ),
        )

    def step(self) -> list[dict[str, Any]]:
        actions = self._staged_actions
        self.native_session.advance(actions=actions)
        self.source.refresh()
        self.t = self.native_session.tick
        for economy in self.economies:
            economy.t = self.t
        self._staged_actions = ()
        return [
            dict(economy.records[-1]) if economy.records else {}
            for economy in self.economies
        ]

    def prepare_controller_boundary(self) -> NativeControllerBoundary:
        """Prepare and expose one private metric preview without publishing C++."""
        opening_tick = self.t
        native_faults = {
            "prepare_after_policy",
            "prepare_after_advance",
            "prepare_after_metrics",
            "commit_before_swap",
        }
        prepared = self.native_session.prepare_boundary(
            actions=self._staged_actions,
            fault_point=(
                self._test_fault_point
                if self._test_fault_point in native_faults else "none"
            ),
        )
        try:
            preview = prepared.lease.preview
            next_tick = int(preview["next_tick"])
            preview_token = self.source.begin_preview(
                dict(preview["public_metrics"]),
            )
            self.t = next_tick
            for economy in self.economies:
                economy.t = next_tick
            records = [
                dict(economy.records[-1]) if economy.records else {}
                for economy in self.economies
            ]
            return NativeControllerBoundary(
                prepared=prepared,
                preview_token=preview_token,
                opening_tick=opening_tick,
                next_tick=next_tick,
                records=records,
            )
        except Exception:
            self.native_session.abort_prepared_boundary(prepared)
            raise

    def inject_controller_fault_for_test(self, fault_point: str) -> None:
        """Select one native fault ordinal for the next controlled boundary."""
        allowed = {
            "none",
            "prepare_after_policy",
            "prepare_after_advance",
            "prepare_after_metrics",
            "commit_before_swap",
            "controller_build",
            "cache_rebuild",
            "publication",
        }
        if fault_point not in allowed:
            raise ValueError(f"unknown M10 fault point {fault_point!r}")
        self._test_fault_point = fault_point

    def commit_controller_boundary(
        self, session: Any, boundary: NativeControllerBoundary,
    ) -> None:
        """Atomically swap the prepared native World and completed controller root."""
        from .native_envelope import encode_controller_state

        if self._test_fault_point == "controller_build":
            raise RuntimeError("injected M10 controller-build fault")
        payload = encode_controller_state(session)
        ordered_keys = sorted(session.coordinator.policy_versions)
        versions = [
            int(session.coordinator.policy_versions[key])
            for key in ordered_keys
        ]
        self.source.end_preview(boundary.preview_token)
        self.t = boundary.opening_tick
        for economy in self.economies:
            economy.t = boundary.opening_tick
        try:
            self.native_session.commit_prepared_boundary(
                boundary.prepared,
                payload=payload,
                event_sequence=len(session.events.events),
                release_cursor=self._release_cursor(session),
                decision_versions=versions,
                effective_versions=versions,
            )
        except Exception:
            self.native_session.abort_prepared_boundary(boundary.prepared)
            self._staged_actions = ()
            self._install_policy_values(tuple(
                self.native_session.policy_values(economy_id)
                for economy_id in range(len(self.economies))
            ))
            raise

        self._staged_actions = ()
        cache_error: RuntimeError | None = None
        try:
            if self._test_fault_point == "cache_rebuild":
                raise RuntimeError("injected M10 cache-rebuild fault")
            self.source.refresh()
        except Exception as exc:
            # The just-committed envelope is authoritative.  Rebuild the Python
            # metric cache from native history instead of exposing a half cache.
            from .native_observation import NativeObservationSource

            self.source = NativeObservationSource(self.native_session)
            self.world_records = self.source.world_records
            for economy_id, economy in enumerate(self.economies):
                economy.records = self.source.economies[economy_id].records
            if self._test_fault_point == "cache_rebuild":
                cache_error = RuntimeError(
                    "injected M10 cache-rebuild fault; cache reconstructed"
                )
                cache_error.__cause__ = exc
        self.t = self.native_session.tick
        for economy in self.economies:
            economy.t = self.t
        actual = [
            dict(economy.records[-1]) if economy.records else {}
            for economy in self.economies
        ]
        if actual != boundary.records:
            raise RuntimeError("native committed metrics differ from prepared preview")
        if cache_error is not None:
            raise cache_error
        if self._test_fault_point == "publication":
            raise RuntimeError(
                "injected M10 publication fault after complete commit"
            )

    def abort_controller_boundary(
        self, boundary: NativeControllerBoundary,
    ) -> None:
        if self.source._preview_token is boundary.preview_token:
            self.source.end_preview(boundary.preview_token)
        self.t = boundary.opening_tick
        for economy in self.economies:
            economy.t = boundary.opening_tick
        self.native_session.abort_prepared_boundary(boundary.prepared)
        self._staged_actions = ()
        self._install_policy_values(tuple(
            self.native_session.policy_values(economy_id)
            for economy_id in range(len(self.economies))
        ))

    def prepare_controller_policy_transaction(
        self, controller_session: Any,
        due_decisions: Iterable[PendingDecision], transaction_id: str | None,
    ) -> NativePreparedPolicyTransaction:
        from .transaction import (
            PolicyTransactionError,
            policy_state,
            world_capability_reason,
            world_policy_fingerprint,
        )

        due = tuple(sorted(
            due_decisions,
            key=lambda item: (
                item.decision.accepted_sequence
                if item.decision.accepted_sequence is not None else -1,
                item.decision.decision_id,
            ),
        ))
        if not due:
            raise PolicyTransactionError(
                "cannot prepare an empty policy transaction",
            )
        base_fingerprint = world_policy_fingerprint(self)
        if base_fingerprint != controller_session.policy_fingerprint:
            raise PolicyTransactionError(
                "live policy/world tick changed outside ControlledSimulationSession",
                (item.decision.decision_id for item in due),
            )
        actions: list[dict[str, Any]] = []
        try:
            for pending in due:
                economy_id = pending.context.economy_id
                if not 0 <= economy_id < len(self.economies):
                    raise ValueError(f"economy id out of range: {economy_id}")
                for action in pending.proposal.actions:
                    capability_reason = world_capability_reason(
                        self, action.lever,
                    )
                    if capability_reason is not None:
                        raise ValueError(
                            f"{action.lever}: {capability_reason}",
                        )
                    for versioned_name in (
                        action.lever,
                        *tuple(sorted(REGISTRY[action.lever].enabled_if)),
                    ):
                        key = f"{economy_id}:{versioned_name}"
                        expected = pending.proposal.based_on_policy_versions.get(
                            versioned_name,
                        )
                        current = controller_session.policy_versions.get(key, 0)
                        if expected is None or expected != current:
                            raise ValueError(
                                f"stale policy version for {versioned_name}: "
                                f"expected {expected}, current {current}"
                            )
                    actions.append({
                        "economy_id": economy_id,
                        "lever": action.lever,
                        "value": action.engine_value(),
                    })
            projected = self.native_session.projected_policy_values(actions)
        except Exception as exc:
            ids = tuple(item.decision.decision_id for item in due)
            raise PolicyTransactionError(str(exc), ids) from exc

        before_values = policy_state(self)
        after_values = {
            f"{economy_id}:{name}": _normalized_value(name, value)
            for economy_id, values in enumerate(projected)
            for name, value in values.items()
        }
        versions_before: dict[str, int] = {}
        versions_after: dict[str, int] = {}
        changes: list[dict[str, Any]] = []
        requested = {
            (item.context.economy_id, action.lever)
            for item in due for action in item.proposal.actions
        }
        for key in sorted(before_values):
            old = before_values[key]
            new = after_values[key]
            if old == new:
                continue
            economy_text, lever_name = key.split(":", 1)
            economy_id = int(economy_text)
            version = controller_session.policy_versions.get(key, 0)
            versions_before[key] = version
            versions_after[key] = version + 1
            changes.append({
                "economy_id": economy_id,
                "lever": lever_name,
                "scope": REGISTRY[lever_name].scope,
                "old": old,
                "new": new,
                "companion": (economy_id, lever_name) not in requested,
            })
        tx_id = transaction_id or (
            f"native-tx:{controller_session.boundary_tick}:"
            f"{controller_session.next_transaction_sequence}"
        )
        return NativePreparedPolicyTransaction(
            transaction_id=tx_id,
            boundary_tick=controller_session.boundary_tick,
            base_fingerprint=base_fingerprint,
            decision_ids=tuple(
                item.decision.decision_id for item in due
            ),
            actions=tuple(actions),
            projected_values=projected,
            changes=tuple(
                immutable_json_mapping(change) for change in changes
            ),
            versions_before=immutable_json_mapping(versions_before),
            versions_after=immutable_json_mapping(versions_after),
        )

    def commit_controller_policy_transaction(
        self, controller_session: Any,
        prepared: NativePreparedPolicyTransaction,
    ) -> tuple[FrozenMapping, ...]:
        from .transaction import PolicyTransactionError, world_policy_fingerprint

        if prepared.boundary_tick != controller_session.boundary_tick:
            raise PolicyTransactionError(
                "prepared transaction belongs to another boundary",
                prepared.decision_ids,
            )
        if world_policy_fingerprint(self) != prepared.base_fingerprint:
            raise PolicyTransactionError(
                "live World changed after transaction preparation",
                prepared.decision_ids,
            )
        if self._staged_actions:
            raise PolicyTransactionError(
                "native boundary already has a staged policy batch",
                prepared.decision_ids,
            )
        self._install_policy_values(prepared.projected_values)
        self._staged_actions = prepared.actions
        controller_session.coordinator.policy_versions.update(
            prepared.versions_after,
        )
        for change in prepared.changes:
            controller_session.coordinator.last_effective_tick[
                f"{change['economy_id']}:{change['lever']}"
            ] = controller_session.boundary_tick
        controller_session.next_transaction_sequence += 1
        controller_session.policy_fingerprint = world_policy_fingerprint(self)
        return prepared.changes


def create_native_controlled_session(
    spec: Any, *, worker_count: int = 8,
) -> tuple[NativeControlledWorld, Any]:
    """Create the existing five-seat controller over a native economic World."""
    from macro_sim.native_backend import NativeSimulationSession

    from .session import ControlledSimulationSession

    native = NativeSimulationSession.create(spec, worker_count=worker_count)
    world = NativeControlledWorld(
        native,
        spec.configs(),
        trade=bool(spec.world["trade"]),
        capital=bool(spec.world["capital"]),
        migration=bool(spec.world["migration"]),
    )
    controlled = ControlledSimulationSession(
        world, run_mode=spec.run_mode,
    )
    world.sync_controller_state(controlled)
    return world, controlled


def restore_native_controlled_session(
    spec: Any,
    checkpoint: bytes,
    *,
    worker_count: int = 8,
) -> tuple[NativeControlledWorld, Any, bytes]:
    """Restore a complete M10 native World plus neutral Python controller cache."""
    from macro_sim.native_backend import NativeSimulationSession

    from .native_envelope import (
        decode_controller_state,
        install_controller_state,
    )
    from .session import ControlledSimulationSession
    from .transaction import world_policy_fingerprint

    native, objective = NativeSimulationSession.restore(
        spec, checkpoint, worker_count=worker_count,
    )
    world = NativeControlledWorld(
        native,
        spec.configs(),
        trade=bool(spec.world["trade"]),
        capital=bool(spec.world["capital"]),
        migration=bool(spec.world["migration"]),
    )
    payload = bytes(native.bridge.controller_envelope.canonical_payload)
    decoded = decode_controller_state(payload)
    controlled = ControlledSimulationSession(
        world, run_mode=decoded["session"]["run_mode"],
    )
    install_controller_state(controlled, decoded)
    controlled.assert_boundary_integrity()
    if controlled.policy_fingerprint != world_policy_fingerprint(world):
        raise ValueError(
            "restored controller policy fingerprint does not match native World"
        )
    if controlled.events.head_hash != decoded["events"].head_hash:
        raise ValueError("restored controller event head changed during installation")
    return world, controlled, objective
