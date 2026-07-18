"""Pure projected World policy transactions.

Preparation mutates only a pickle-isolated projection.  Publishing that complete
projection is the sole live write, which makes domestic fields, ExternalPolicy-derived
caches, PegState reserve transfers, ledgers, and transition handlers one atomic unit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import pickle
from typing import Any, Iterable, Mapping

from macro_sim.core.external_policy import ExternalPolicy
from macro_sim.core.policy import Policy
from macro_sim.core.policy_registry import (
    REGISTRY,
    commit_prepared_action_batch,
    prepare_action_batch,
)

from .protocol import (
    FrozenMapping,
    PendingDecision,
    canonical_json,
    immutable_json_mapping,
)


class PolicyTransactionError(ValueError):
    def __init__(self, message: str, decision_ids: Iterable[str] = ()) -> None:
        super().__init__(message)
        self.decision_ids = tuple(decision_ids)


def _policy_key(economy_id: int, lever: str) -> str:
    return f"{economy_id}:{lever}"


def _economies(world: Any) -> list[Any]:
    economies = getattr(world, "economies", None)
    return list(economies) if economies is not None else [world]


_TRADE_POLICY_LEVERS = frozenset({"tariff", "import_quota", "export_subsidy"})
_CAPITAL_POLICY_LEVERS = frozenset({
    "capital_control", "external_interest_settlement_fraction",
})
_MIGRATION_POLICY_LEVERS = frozenset({
    "immigration_cap", "emigration_cap", "remittance_tax",
    "outward_remittance_tax", "guest_worker_return",
})
_FX_POLICY_LEVERS = frozenset({"fx_regime", "peg_anchor", "peg_reserve_scale"})


def world_capability_reason(world: Any, lever_name: str) -> str | None:
    """Return why a World-owned runtime mechanism cannot consume this lever."""
    if lever_name not in (
        _TRADE_POLICY_LEVERS | _CAPITAL_POLICY_LEVERS | _MIGRATION_POLICY_LEVERS
        | _FX_POLICY_LEVERS | {"sanctions_imposed_on"}
    ):
        return None
    economies = getattr(world, "economies", None)
    if economies is None:
        return "missing_world_capability:coupling"
    if len(economies) < 2:
        return "missing_world_capability:multiple_economies"
    if lever_name in _TRADE_POLICY_LEVERS and not bool(getattr(world, "trade", False)):
        return "missing_world_capability:trade"
    if lever_name in _CAPITAL_POLICY_LEVERS and not bool(getattr(world, "capital", False)):
        return "missing_world_capability:capital"
    if lever_name in _MIGRATION_POLICY_LEVERS and not bool(getattr(world, "migration", False)):
        return "missing_world_capability:migration"
    if lever_name in _FX_POLICY_LEVERS and not bool(getattr(world, "couple", False)):
        return "missing_world_capability:coupling"
    if lever_name == "sanctions_imposed_on" and not any(
        bool(getattr(world, name, False)) for name in ("trade", "capital", "migration")
    ):
        return "missing_world_capability:cross_border_flow"
    return None


def policy_state(world: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for economy_id, econ in enumerate(_economies(world)):
        # Controller ids are positions in the session's economy collection.  A
        # bare legacy Economy may carry a stale ``economy_id`` left by a former
        # World, but it is unambiguously economy 0 in a one-economy session.
        for name, lever in REGISTRY.items():
            if lever.scope == "external" and not hasattr(econ, "external_policy"):
                # A bare Economy has no cross-border engine surface.  Domestic
                # control remains supported; external levers are simply absent.
                continue
            holder = econ.external_policy if lever.scope == "external" else econ.policy
            result[_policy_key(economy_id, name)] = getattr(holder, name)
    return result


def world_policy_fingerprint(world: Any) -> str:
    """Detect policy/engine advancement that bypassed a controlled session."""
    payload: dict[str, Any] = {
        "tick": int(getattr(world, "t", 0)),
        "policy": policy_state(world),
    }
    if hasattr(world, "peg_states"):
        payload["peg_states"] = {
            str(key): asdict(value) for key, value in sorted(world.peg_states.items())
        }
        payload["sanctions"] = getattr(world, "sanctions", set())
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PreparedWorldPolicyTransaction:
    transaction_id: str
    boundary_tick: int
    base_fingerprint: str
    projected_world: Any
    sealed_world: bytes = field(repr=False)
    projection_digest: str
    decision_ids: tuple[str, ...]
    changes: tuple[FrozenMapping, ...]
    versions_before: FrozenMapping
    versions_after: FrozenMapping


def _pickle_world(world: Any) -> bytes:
    return pickle.dumps(world, protocol=5)


def _policy_projection_blob(world: Any) -> bytes:
    """Serialize current engine state without append-only metric history.

    Policy validation and transition handlers need the complete *current* World
    graph, including ledgers, RNGs, peg state, and agent balance sheets.  They do
    not read historical metric rows.  Copying those ever-growing rows for every
    proposal turns a long controlled run into quadratic work and can require
    several copies of a multi-gigabyte history at once.

    A ControlledSimulationSession is deliberately single-threaded, so temporarily
    detaching the history roots while pickling is safe.  ``finally`` restores the
    exact list objects even when serialization fails.  SimulationState carries a
    second alias to Economy.records and must be detached with it.
    """
    bindings: list[tuple[Any, str, Any]] = []

    def detach(owner: Any, name: str, replacement: Any) -> None:
        if name in getattr(owner, "__dict__", {}):
            bindings.append((owner, name, owner.__dict__[name]))
            setattr(owner, name, replacement)

    try:
        detach(world, "world_records", [])
        for economy in _economies(world):
            empty_records: list[Any] = []
            detach(economy, "records", empty_records)
            state = getattr(economy, "state", None)
            if state is not None:
                detach(state, "records", empty_records)
        return _pickle_world(world)
    finally:
        for owner, name, original in reversed(bindings):
            setattr(owner, name, original)


def clone_world_for_policy_projection(world: Any) -> Any:
    """Return a pickle-isolated current-state graph with empty metric histories."""
    return pickle.loads(_policy_projection_blob(world))


def _reattach_metric_histories(live_world: Any, published_world: Any) -> None:
    """Preserve append-only history roots when publishing a compact projection."""
    if "world_records" in getattr(live_world, "__dict__", {}):
        published_world.world_records = live_world.world_records
    live_economies = _economies(live_world)
    published_economies = _economies(published_world)
    if len(live_economies) != len(published_economies):
        raise PolicyTransactionError("projected World economy count changed")
    for live_economy, published_economy in zip(live_economies, published_economies):
        if "records" not in getattr(live_economy, "__dict__", {}):
            continue
        published_economy.records = live_economy.records
        published_state = getattr(published_economy, "state", None)
        if published_state is not None:
            published_state.records = live_economy.records


def _blob_digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def prepare_world_policy_transaction(
    session: Any,
    due_decisions: Iterable[PendingDecision],
    *,
    transaction_id: str | None = None,
) -> PreparedWorldPolicyTransaction:
    """Prepare all due decisions on an isolated full-World projection."""
    session.assert_boundary_integrity()
    due = tuple(sorted(
        due_decisions,
        key=lambda item: (
            item.decision.accepted_sequence if item.decision.accepted_sequence is not None else -1,
            item.decision.decision_id,
        ),
    ))
    if not due:
        raise PolicyTransactionError("cannot prepare an empty policy transaction")
    live_world = session.world
    base_fingerprint = world_policy_fingerprint(live_world)
    if base_fingerprint != session.policy_fingerprint:
        raise PolicyTransactionError(
            "live policy/world tick changed outside ControlledSimulationSession",
            (item.decision.decision_id for item in due),
        )

    projected = clone_world_for_policy_projection(live_world)
    projected_economies = _economies(projected)
    before_values = policy_state(projected)

    try:
        for pending in due:
            economy_id = pending.context.economy_id
            if not 0 <= economy_id < len(projected_economies):
                raise ValueError(f"economy id out of range: {economy_id}")
            for action in pending.proposal.actions:
                capability_reason = world_capability_reason(projected, action.lever)
                if capability_reason is not None:
                    raise ValueError(f"{action.lever}: {capability_reason}")
                versioned_names = (action.lever,) + tuple(
                    sorted(REGISTRY[action.lever].enabled_if)
                )
                for versioned_name in versioned_names:
                    key = _policy_key(economy_id, versioned_name)
                    expected = pending.proposal.based_on_policy_versions.get(versioned_name)
                    current = session.policy_versions.get(key, 0)
                    if expected is None or expected != current:
                        raise ValueError(
                            f"stale policy version for {versioned_name}: "
                            f"expected {expected}, current {current}"
                        )
            batch = prepare_action_batch(
                projected_economies[economy_id],
                [(action.lever, action.engine_value()) for action in pending.proposal.actions],
                actor=pending.context.seat,
                target=economy_id,
            )
            commit_prepared_action_batch(batch, log_event=False)

        # This performs all dynamic target and joint-peg validation, derives caches,
        # and runs reserve/peg transition mechanics on the projection only.
        if hasattr(projected, "_commit_external_policies"):
            projected._commit_external_policies()
        for econ in projected_economies:
            econ.ledger.assert_conserved()
            econ.ledger.assert_non_negative()
    except Exception as exc:
        ids = tuple(item.decision.decision_id for item in due)
        raise PolicyTransactionError(str(exc), ids) from exc

    after_values = policy_state(projected)
    versions_before: dict[str, int] = {}
    versions_after: dict[str, int] = {}
    changes: list[dict[str, Any]] = []
    requested_order: dict[tuple[int, str], int] = {}
    for pos, pending in enumerate(due):
        for action in pending.proposal.actions:
            requested_order[(pending.context.economy_id, action.lever)] = pos
    for key in sorted(before_values):
        old, new = before_values[key], after_values[key]
        if old == new:
            continue
        economy_text, lever_name = key.split(":", 1)
        economy_id = int(economy_text)
        version = session.policy_versions.get(key, 0)
        versions_before[key] = version
        versions_after[key] = version + 1
        changes.append({
            "economy_id": economy_id,
            "lever": lever_name,
            "scope": REGISTRY[lever_name].scope,
            "old": old,
            "new": new,
            "companion": (economy_id, lever_name) not in requested_order,
        })

    # Seal the validated graph.  ``projected_world`` remains available for audit and
    # diagnostics, but commit verifies it against these immutable bytes and publishes
    # a *new* unpickled graph.  A caller can therefore neither alter it between prepare
    # and commit nor retain a write-through alias after commit.
    sealed_world = _pickle_world(projected)
    projection_digest = _blob_digest(sealed_world)
    tx_id = transaction_id or f"tx:{session.boundary_tick}:{session.next_transaction_sequence}"
    return PreparedWorldPolicyTransaction(
        transaction_id=tx_id,
        boundary_tick=session.boundary_tick,
        base_fingerprint=base_fingerprint,
        projected_world=projected,
        sealed_world=sealed_world,
        projection_digest=projection_digest,
        decision_ids=tuple(item.decision.decision_id for item in due),
        changes=tuple(immutable_json_mapping(change) for change in changes),
        versions_before=immutable_json_mapping(versions_before),
        versions_after=immutable_json_mapping(versions_after),
    )


def commit_world_policy_transaction(
    session: Any,
    prepared: PreparedWorldPolicyTransaction,
) -> tuple[Mapping[str, Any], ...]:
    """Atomically publish a sealed World and update controller bookkeeping.

    All potentially failing serialization, integrity and fingerprint work happens
    before the first live assignment.  The small publication block also restores the
    previous roots if an unexpected assignment failure occurs.
    """
    session.assert_boundary_integrity()
    if prepared.boundary_tick != session.boundary_tick:
        raise PolicyTransactionError("prepared transaction belongs to another boundary")
    if world_policy_fingerprint(session.world) != prepared.base_fingerprint:
        raise PolicyTransactionError("live World changed after transaction preparation")

    try:
        current_projection_blob = _pickle_world(prepared.projected_world)
    except Exception as exc:
        raise PolicyTransactionError(
            f"prepared World projection is no longer serializable: {exc}",
            prepared.decision_ids,
        ) from exc
    if _blob_digest(current_projection_blob) != prepared.projection_digest:
        raise PolicyTransactionError(
            "prepared World projection changed after validation",
            prepared.decision_ids,
        )
    if _blob_digest(prepared.sealed_world) != prepared.projection_digest:
        raise PolicyTransactionError(
            "sealed World projection failed its integrity check",
            prepared.decision_ids,
        )
    try:
        published_world = pickle.loads(prepared.sealed_world)
        _reattach_metric_histories(session.world, published_world)
        published_fingerprint = world_policy_fingerprint(published_world)
    except Exception as exc:
        raise PolicyTransactionError(
            f"sealed World projection cannot be published: {exc}",
            prepared.decision_ids,
        ) from exc

    new_versions = dict(session.policy_versions)
    new_versions.update(prepared.versions_after)
    new_last_effective = dict(session.last_effective_tick)
    for change in prepared.changes:
        new_last_effective[
            _policy_key(change["economy_id"], change["lever"])
        ] = session.boundary_tick

    old_world_dict = session.world.__dict__
    old_versions = session.coordinator.policy_versions
    old_last_effective = session.coordinator.last_effective_tick
    old_sequence = session.next_transaction_sequence
    old_fingerprint = session.policy_fingerprint
    try:
        # Retain the externally held World root identity, while the graph installed
        # below is the independent object decoded from the sealed bytes.
        session.world.__dict__ = published_world.__dict__
        session.coordinator.policy_versions = new_versions
        session.coordinator.last_effective_tick = new_last_effective
        session.next_transaction_sequence = old_sequence + 1
        session.policy_fingerprint = published_fingerprint
    except Exception as exc:
        session.world.__dict__ = old_world_dict
        session.coordinator.policy_versions = old_versions
        session.coordinator.last_effective_tick = old_last_effective
        session.next_transaction_sequence = old_sequence
        session.policy_fingerprint = old_fingerprint
        raise PolicyTransactionError(
            f"failed to publish prepared World transaction: {exc}",
            prepared.decision_ids,
        ) from exc
    return prepared.changes
