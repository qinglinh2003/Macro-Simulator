"""Authority, procedure, pending timeline, costs, and policy execution."""
from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations
from typing import Any

from macro_sim.core.policy_control_specs import CONTROL_SPECS
from macro_sim.core.policy_registry import (
    Bool,
    Choices,
    EconomyId,
    EconomySet,
    IntRange,
    LEGACY_ALIASES,
    NullableRange,
    Range,
    REGISTRY,
    commit_prepared_action_batch,
    prepare_action_batch,
)

from .costs import AdjustmentCostSpec
from .events import EventStream
from .observation import OracleObservation
from .protocol import (
    DecisionContext,
    PendingDecision,
    PermittedAction,
    PolicyAction,
    PolicyDecision,
    PolicyProposal,
    canonical_json,
)
from .scheduler import DecisionScheduler
from .transaction import (
    PolicyTransactionError,
    clone_world_for_policy_projection,
    commit_world_policy_transaction,
    prepare_world_policy_transaction,
    world_capability_reason,
)


SEATS = ("central_bank", "energy", "external_affairs", "regulator", "treasury")


def policy_key(economy_id: int, lever: str) -> str:
    return f"{economy_id}:{lever}"


def _economies(world: Any) -> list[Any]:
    return list(getattr(world, "economies", [world]))


@dataclass
class PolicyCoordinator:
    scheduler: DecisionScheduler
    events: EventStream
    cost_spec: AdjustmentCostSpec
    policy_versions: dict[str, int]
    last_effective_tick: dict[str, int]
    pending: dict[str, PendingDecision]
    contexts: dict[str, DecisionContext]
    decisions: dict[str, PolicyDecision]
    idempotency: dict[str, str]
    idempotency_payload: dict[str, str]
    proposal_for_context: dict[str, str]
    admin_remaining: dict[tuple[int, str, str], float]
    admin_reserved: dict[tuple[int, str, str], float]
    admin_replenished_at: dict[tuple[int, str, str], int]
    next_decision_sequence: int

    @classmethod
    def create(
        cls,
        world: Any,
        scheduler: DecisionScheduler,
        events: EventStream,
        cost_spec: AdjustmentCostSpec | None = None,
    ) -> "PolicyCoordinator":
        versions: dict[str, int] = {}
        for default_id, _econ in enumerate(_economies(world)):
            for name, lever in REGISTRY.items():
                if lever.scope == "external" and not hasattr(_econ, "external_policy"):
                    continue
                versions[policy_key(default_id, name)] = 0
        return cls(
            scheduler=scheduler,
            events=events,
            cost_spec=cost_spec or AdjustmentCostSpec(),
            policy_versions=versions,
            last_effective_tick={},
            pending={},
            contexts={},
            decisions={},
            idempotency={},
            idempotency_payload={},
            proposal_for_context={},
            admin_remaining={},
            admin_reserved={},
            admin_replenished_at={},
            next_decision_sequence=0,
        )

    @staticmethod
    def _pending_order(item: PendingDecision) -> tuple[int, int, str]:
        sequence = item.decision.accepted_sequence
        return (
            item.effective_tick,
            sequence if sequence is not None else -1,
            item.decision.decision_id,
        )

    def _active_pending(
        self,
        *,
        through_tick: int | None = None,
        exclude: PendingDecision | None = None,
    ) -> list[PendingDecision]:
        result = [
            item for item in self.pending.values()
            if item.status == "accepted_pending"
            and item is not exclude
            and (through_tick is None or item.effective_tick <= through_tick)
        ]
        result.sort(key=self._pending_order)
        return result

    def _admin_window_marker(
        self,
        economy_id: int,
        decision_group: str,
        boundary_tick: int,
    ) -> int:
        """Identify the institutional calendar cycle containing a boundary.

        Emergency notices may open contexts on several consecutive boundaries.
        Administrative capacity belongs to the decision group's meeting cycle,
        so those notices share a budget instead of minting a fresh budget each
        time. Replenishment is lazy: the first context in a new cycle installs
        that cycle's capacity.
        """
        calendar = self.scheduler.calendar_for(decision_group)
        extra = self.scheduler.economy_offsets.get(
            (economy_id, decision_group), 0,
        )
        offset = (calendar.offset_ticks + extra) % calendar.period_ticks
        cycle = (boundary_tick - offset) // calendar.period_ticks
        return offset + cycle * calendar.period_ticks

    def _reservation_is_in_installed_window(
        self,
        pending: PendingDecision,
    ) -> bool:
        """Whether a pending decision's reservation belongs to the live budget.

        A new institutional calendar cycle replenishes capacity and clears the
        previous cycle's reservation ledger.  A late cancellation, supersede, or
        execution must not refund/subtract that expired reservation against the new
        cycle, where it could mint capacity or consume an unrelated reservation.
        """
        key = (
            pending.context.economy_id,
            pending.context.seat,
            pending.context.decision_group,
        )
        reservation_marker = self._admin_window_marker(
            pending.context.economy_id,
            pending.context.decision_group,
            pending.context.boundary_tick,
        )
        return self.admin_replenished_at.get(key) == reservation_marker

    def _projected_value_at(
        self,
        session: Any,
        economy_id: int,
        lever_name: str,
        effective_tick: int,
        *,
        exclude: PendingDecision | None = None,
    ) -> Any:
        """Project a direct policy field through the accepted pending timeline.

        This lightweight projection is used for masks.  Submission performs a
        full pickle-isolated engine projection, including transition companions
        and World reconciliation, before accepting a decision.
        """
        lever = REGISTRY[lever_name]
        econ = _economies(session.world)[economy_id]
        holder = econ.external_policy if lever.scope == "external" else econ.policy
        value = getattr(holder, lever_name)
        for pending in self._active_pending(
            through_tick=effective_tick, exclude=exclude,
        ):
            if pending.context.economy_id != economy_id:
                continue
            for action in pending.proposal.actions:
                if action.lever == lever_name:
                    value = action.engine_value()
        return value

    def _resolve_superseded(
        self,
        proposal: PolicyProposal,
        context: DecisionContext,
    ) -> tuple[PendingDecision | None, str | None]:
        """Resolve same- or cross-context cancel-and-replace targets."""
        prior = self.proposal_for_context.get(context.context_id)
        requested = proposal.supersedes_proposal_id
        if prior is not None and requested != prior:
            return None, "context_already_answered"
        if prior is None and requested is None:
            return None, None

        target_id = requested if requested is not None else prior
        matches = [
            item for item in self.pending.values()
            if item.proposal.proposal_id == target_id
            and item.status == "accepted_pending"
        ]
        if len(matches) != 1:
            return None, (
                "supersede_target_ambiguous" if len(matches) > 1
                else "proposal_not_supersedable"
            )
        target = matches[0]
        if (
            target.context.economy_id != context.economy_id
            or target.context.seat != context.seat
        ):
            return None, "supersede_scope_mismatch"
        replacement_levers = tuple(sorted(
            LEGACY_ALIASES.get(action.lever, action.lever)
            for action in proposal.actions
        ))
        if replacement_levers != tuple(sorted(target.touched_levers)):
            return None, "supersede_lever_mismatch"
        return target, None

    @staticmethod
    def _dynamic_reference_error(
        proposal: PolicyProposal,
        *,
        economy_id: int,
        world_size: int,
    ) -> str | None:
        """Validate runtime-sized references without ever leaking TypeError."""
        try:
            for action in proposal.actions:
                if action.lever == "sanctions_imposed_on":
                    # Validate the immutable wire sequence before converting it to
                    # frozenset.  Python considers True == 1 and 1.0 == 1, so an
                    # early set conversion can otherwise erase an invalid element.
                    raw_targets = action.value
                    if not isinstance(raw_targets, (list, tuple, set, frozenset)):
                        return "dynamic_reference:invalid_sanctions_target"
                    for target in raw_targets:
                        if (
                            type(target) is not int
                            or not 0 <= target < world_size
                            or target == economy_id
                        ):
                            return "dynamic_reference:invalid_sanctions_target"
                    value = action.engine_value()
                    if not isinstance(value, frozenset):
                        return "dynamic_reference:invalid_sanctions_target"
                elif action.lever == "peg_anchor":
                    value = action.engine_value()
                    if value is None:
                        continue
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, int)
                        or not 0 <= value < world_size
                        or value == economy_id
                    ):
                        return "dynamic_reference:invalid_peg_anchor"
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
            return "dynamic_reference:malformed_reference"
        return None

    @staticmethod
    def _reconcile_projected_world(projected: Any) -> None:
        if hasattr(projected, "_commit_external_policies"):
            projected._commit_external_policies()
        for econ in _economies(projected):
            econ.ledger.assert_conserved()
            econ.ledger.assert_non_negative()

    @staticmethod
    def _projected_policy_state(projected: Any) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for economy_id, econ in enumerate(_economies(projected)):
            for name, lever in REGISTRY.items():
                if lever.scope == "external" and not hasattr(econ, "external_policy"):
                    continue
                holder = (
                    econ.external_policy if lever.scope == "external"
                    else econ.policy
                )
                result[policy_key(economy_id, name)] = getattr(holder, name)
        return result

    @staticmethod
    def _peg_conflict_ids(
        world: Any,
        pending_items: tuple[PendingDecision, ...],
    ) -> set[str]:
        """Return the decisions that create a same-boundary peg contest.

        The World currently has one cross-economy exclusivity constraint: at
        most one economy may peg. An incumbent that remains pegged is state, not
        a competing proposal; every would-be entrant loses symmetrically. When
        the incumbent exits, only multiple entrants form the minimal conflict.
        """
        economies = _economies(world)
        if not all(hasattr(econ, "external_policy") for econ in economies):
            return set()
        regimes = [econ.external_policy.fx_regime for econ in economies]
        entrants: dict[int, str] = {}
        for pending in pending_items:
            for action in pending.proposal.actions:
                if action.lever != "fx_regime":
                    continue
                value = action.engine_value()
                regimes[pending.context.economy_id] = value
                if value == "peg":
                    entrants[pending.context.economy_id] = (
                        pending.decision.decision_id
                    )
                else:
                    entrants.pop(pending.context.economy_id, None)
        peggers = {idx for idx, regime in enumerate(regimes) if regime == "peg"}
        if len(peggers) <= 1:
            return set()
        return {
            decision_id for economy_id, decision_id in entrants.items()
            if economy_id in peggers
        }

    def _apply_pending_sequence(
        self,
        projected: Any,
        pending_items: tuple[PendingDecision, ...],
        effective_tick: int,
        last_effective: dict[str, int],
        *,
        validate_controls: bool,
    ) -> None:
        """Apply a same-boundary sequence to an isolated World graph."""
        economies = _economies(projected)
        for pending in sorted(pending_items, key=self._pending_order):
            economy_id = pending.context.economy_id
            econ = economies[economy_id]
            if validate_controls:
                for action in pending.proposal.actions:
                    lever = REGISTRY[action.lever]
                    for versioned_name in (
                        action.lever,
                        *tuple(sorted(lever.enabled_if)),
                    ):
                        key = policy_key(economy_id, versioned_name)
                        expected = pending.proposal.based_on_policy_versions.get(
                            versioned_name
                        )
                        current = self.policy_versions.get(key, 0)
                        projected_change = (
                            last_effective.get(key)
                            != self.last_effective_tick.get(key)
                        )
                        if expected != current or projected_change:
                            raise ValueError(
                                f"{action.lever}: stale projected policy version "
                                f"for {versioned_name}"
                            )
                    holder = (
                        econ.external_policy if lever.scope == "external"
                        else econ.policy
                    )
                    old = getattr(holder, action.lever)
                    value = action.engine_value()
                    if old != value:
                        last = last_effective.get(policy_key(economy_id, action.lever))
                        if last is not None \
                                and effective_tick < last + lever.min_hold_ticks:
                            raise ValueError(
                                f"{action.lever}: minimum_hold until "
                                f"{last + lever.min_hold_ticks}"
                            )
                    spec = CONTROL_SPECS[action.lever]
                    if isinstance(lever.validation, Range) \
                            and spec.max_step is not None \
                            and old is not None and value is not None:
                        distance = abs(float(value) - float(old))
                        if distance > spec.max_step + 1e-15:
                            raise ValueError(
                                f"{action.lever}: step {distance:.4g} "
                                f"exceeds max_step {spec.max_step}"
                            )
            batch = prepare_action_batch(
                econ,
                [
                    (action.lever, action.engine_value())
                    for action in pending.proposal.actions
                ],
                actor=pending.context.seat,
                target=economy_id,
            )
            commit_prepared_action_batch(batch, log_event=False)

    def _apply_projected_group(
        self,
        projected: Any,
        pending_items: tuple[PendingDecision, ...],
        effective_tick: int,
        last_effective: dict[str, int],
    ) -> tuple[Any, dict[str, int]]:
        candidate_world = clone_world_for_policy_projection(projected)
        before = self._projected_policy_state(candidate_world)
        self._apply_pending_sequence(
            candidate_world,
            pending_items,
            effective_tick,
            last_effective,
            validate_controls=True,
        )
        self._reconcile_projected_world(candidate_world)
        after = self._projected_policy_state(candidate_world)
        updated_last = dict(last_effective)
        for key, old in before.items():
            if after[key] != old:
                updated_last[key] = effective_tick
        return candidate_world, updated_last

    def _project_conservative_group(
        self,
        projected: Any,
        pending_items: tuple[PendingDecision, ...],
        effective_tick: int,
        last_effective: dict[str, int],
    ) -> tuple[Any, dict[str, int]]:
        """Project the same conservative conflict rule used by execution."""
        peg_conflicts = self._peg_conflict_ids(projected, pending_items)
        pending_items = tuple(
            item for item in pending_items
            if item.decision.decision_id not in peg_conflicts
        )
        if not pending_items:
            return projected, last_effective
        try:
            return self._apply_projected_group(
                projected, pending_items, effective_tick, last_effective,
            )
        except (KeyError, ValueError, TypeError, OverflowError):
            pass

        attempts = 0
        for size in range(len(pending_items) - 1, 0, -1):
            valid: list[tuple[PendingDecision, ...]] = []
            for subset in combinations(pending_items, size):
                attempts += 1
                if attempts > 4_096:
                    return projected, last_effective
                try:
                    self._apply_projected_group(
                        projected, subset, effective_tick, last_effective,
                    )
                except (KeyError, ValueError, TypeError, OverflowError):
                    continue
                valid.append(subset)
            if not valid:
                continue
            safe_ids = {
                item.decision.decision_id for item in valid[0]
            }
            for subset in valid[1:]:
                safe_ids.intersection_update(
                    item.decision.decision_id for item in subset
                )
            safe = tuple(
                item for item in pending_items
                if item.decision.decision_id in safe_ids
            )
            if not safe:
                return projected, last_effective
            try:
                return self._apply_projected_group(
                    projected, safe, effective_tick, last_effective,
                )
            except (KeyError, ValueError, TypeError, OverflowError):
                return projected, last_effective
        return projected, last_effective

    def _project_candidate_batch(
        self,
        session: Any,
        context: DecisionContext,
        proposal: PolicyProposal,
        effective_tick: int,
        *,
        superseded: PendingDecision | None,
    ):
        """Validate against state projected to the proposed effective boundary."""
        projected = clone_world_for_policy_projection(session.world)
        timeline = self._active_pending(
            through_tick=effective_tick, exclude=superseded,
        )

        projected_last_effective = dict(self.last_effective_tick)
        same_tick: list[PendingDecision] = []
        for tick in sorted({item.effective_tick for item in timeline}):
            group = tuple(item for item in timeline if item.effective_tick == tick)
            if tick < effective_tick:
                projected, projected_last_effective = (
                    self._project_conservative_group(
                        projected, group, tick, projected_last_effective,
                    )
                )
            else:
                same_tick.extend(group)

        # Existing decisions at the candidate boundary and the candidate reconcile
        # together, enabling positive dependencies such as an atomic peg handoff.
        # World-level conflicts are deliberately deferred to joint execution.
        if same_tick:
            self._apply_pending_sequence(
                projected,
                tuple(same_tick),
                effective_tick,
                projected_last_effective,
                validate_controls=False,
            )

        projected_economies = _economies(projected)
        econ = projected_economies[context.economy_id]
        for action in proposal.actions:
            lever = REGISTRY[action.lever]
            value = action.engine_value()
            # Strict type/domain validation without Registry's legacy max-step
            # hook.  C1 max-step is a controller procedure, not a set_lever rule.
            err = lever.validation.check(None, value)
            if err:
                raise ValueError(f"{action.lever}: {err}")
            spec = CONTROL_SPECS[action.lever]
            if isinstance(lever.validation, Range) and spec.max_step is not None:
                holder = econ.external_policy if lever.scope == "external" else econ.policy
                old = getattr(holder, action.lever)
                if old is not None and value is not None \
                        and abs(float(value) - float(old)) > spec.max_step + 1e-15:
                    raise ValueError(
                        f"{action.lever}: step {abs(float(value) - float(old)):.4g} "
                        f"exceeds max_step {spec.max_step}"
                    )

        candidate = prepare_action_batch(
            econ,
            [(action.lever, action.engine_value()) for action in proposal.actions],
            actor=context.seat,
            target=context.economy_id,
        )
        commit_prepared_action_batch(candidate, log_event=False)
        # Do not reconcile the candidate's own effective group here.  Multiple
        # independently authorized proposals can be mutually inconsistent (for
        # example two would-be peggers); they must enter the pending due set and
        # receive symmetric minimal-conflict treatment at joint execution rather
        # than letting submission order pick a winner.  The mask still reports
        # known peg constraints, and dynamic references were checked above.
        return candidate, projected_last_effective

    def open_context(
        self,
        session: Any,
        economy_id: int,
        seat: str,
        decision_group: str,
        observation: Any,
        *,
        expires_at_tick: int,
        emergency: bool = False,
        emergency_trigger: str | None = None,
        elapsed_ticks: int = 0,
    ) -> DecisionContext:
        session.assert_boundary_integrity()
        if isinstance(observation, OracleObservation):
            raise ValueError("OracleObservation cannot enter an occupant DecisionContext")
        if seat not in SEATS:
            raise ValueError(f"unknown policy seat: {seat}")
        if emergency:
            if not isinstance(emergency_trigger, str) or not emergency_trigger:
                raise ValueError("emergency context requires a trigger id")
            marker = f"emergency:{emergency_trigger}"
        else:
            if emergency_trigger is not None:
                raise ValueError("regular context cannot carry an emergency trigger")
            marker = "regular"
        context_id = (
            f"ctx:{economy_id}:{seat}:{decision_group}:{session.boundary_tick}:{marker}"
        )
        existing = self.contexts.get(context_id)
        if existing is not None:
            return existing
        key = (economy_id, seat, decision_group)
        calendar = self.scheduler.calendar_for(decision_group)
        window_marker = self._admin_window_marker(
            economy_id, decision_group, session.boundary_tick,
        )
        if self.admin_replenished_at.get(key) != window_marker:
            self.admin_remaining[key] = calendar.admin_capacity
            self.admin_reserved[key] = 0.0
            self.admin_replenished_at[key] = window_marker

        permitted = self._permitted_actions(
            session, economy_id, seat, decision_group, emergency=emergency
        )
        economies = _economies(session.world)
        econ = economies[economy_id]
        seat_levers = tuple(sorted(
            name
            for name, lever in REGISTRY.items()
            if lever.owner_role == seat
            and (lever.scope != "external" or hasattr(econ, "external_policy"))
        ))
        current_policy = {
            name: getattr(
                econ.external_policy
                if REGISTRY[name].scope == "external" else econ.policy,
                name,
            )
            for name in seat_levers
        }
        version_names = set(seat_levers)
        for name in seat_levers:
            version_names.update(REGISTRY[name].enabled_if)
        versions = {
            name: self.policy_versions[policy_key(economy_id, name)]
            for name in sorted(version_names)
        }
        active_pending = tuple(
            item for item in self._active_pending()
            if item.context.economy_id == economy_id
        )
        pending_policy: dict[str, Any] = {}
        pending_effective_ticks: dict[str, int] = {}
        for pending_item in active_pending:
            for action in pending_item.proposal.actions:
                if action.lever not in current_policy:
                    continue
                pending_policy[action.lever] = action.value
                pending_effective_ticks[action.lever] = pending_item.effective_tick
        last_effective_ticks: dict[str, int | None] = {}
        next_eligibility_ticks: dict[str, int] = {}
        visible_cost_estimates: dict[str, dict[str, Any]] = {}
        for name in seat_levers:
            lever = REGISTRY[name]
            key_name = policy_key(economy_id, name)
            last = self.last_effective_tick.get(key_name)
            lag = lever.emergency_implementation_lag \
                if emergency and lever.emergency_implementation_lag is not None \
                else lever.implementation_lag
            next_tick = session.boundary_tick + lag
            if last is not None:
                next_tick = max(next_tick, last + lever.min_hold_ticks)
            for pending_item in active_pending:
                if any(action.lever == name for action in pending_item.proposal.actions):
                    next_tick = max(
                        next_tick,
                        pending_item.effective_tick + lever.min_hold_ticks,
                    )
            last_effective_ticks[name] = last
            next_eligibility_ticks[name] = next_tick

            weights = self.cost_spec.class_weights[lever.cost_class]
            one_step_adjustment = weights.fixed + weights.l1 + weights.l2
            if emergency:
                one_step_adjustment *= self.cost_spec.emergency_premium
            visible_cost_estimates[name] = {
                "cost_class": lever.cost_class,
                "control_scale": lever.control_scale,
                "admin_if_changed": (
                    self.cost_spec.proposal_admin_overhead + lever.admin_weight
                ),
                "adjustment_for_one_control_step": one_step_adjustment,
            }
        budget_key = (economy_id, seat, decision_group)
        emergency_bulletin = None
        if emergency:
            emergency_bulletin = {
                "trigger_id": emergency_trigger,
                "generated_at_tick": session.boundary_tick,
                "expires_at_tick": expires_at_tick,
                "decision_group": decision_group,
            }
            shock_bulletins = getattr(observation, "shock_bulletins", ())
            if shock_bulletins:
                emergency_bulletin["shock_bulletins"] = list(shock_bulletins)
        context = DecisionContext(
            context_id=context_id,
            decision_window_id=f"window:{context_id}",
            economy_id=economy_id,
            seat=seat,
            decision_group=decision_group,
            boundary_tick=session.boundary_tick,
            expires_at_tick=expires_at_tick,
            policy_versions=versions,
            observation=observation,
            permitted_actions=tuple(permitted),
            pending_policy=pending_policy,
            current_policy=current_policy,
            pending_effective_ticks=pending_effective_ticks,
            emergency=emergency,
            emergency_trigger=emergency_trigger,
            elapsed_ticks=elapsed_ticks,
            last_effective_ticks=last_effective_ticks,
            next_eligibility_ticks=next_eligibility_ticks,
            admin_remaining=self.admin_remaining.get(budget_key, 0.0),
            admin_reserved=self.admin_reserved.get(budget_key, 0.0),
            admin_capacity=calendar.admin_capacity,
            visible_cost_estimates=visible_cost_estimates,
            emergency_bulletin=emergency_bulletin,
        )
        self.contexts[context_id] = context
        return context

    def _permitted_actions(
        self,
        session: Any,
        economy_id: int,
        seat: str,
        decision_group: str,
        *,
        emergency: bool,
    ) -> list[PermittedAction]:
        economies = _economies(session.world)
        econ = economies[economy_id]
        result: list[PermittedAction] = []
        pending_levers = {
            (item.context.economy_id, action.lever)
            for item in self.pending.values() if item.status == "accepted_pending"
            for action in item.proposal.actions
        }
        for name, lever in sorted(REGISTRY.items()):
            if lever.owner_role != seat:
                continue
            if lever.scope == "external" and not hasattr(econ, "external_policy"):
                continue
            if not emergency and lever.decision_group != decision_group:
                continue
            if emergency and not lever.emergency:
                continue
            holder = econ.external_policy if lever.scope == "external" else econ.policy
            current = getattr(holder, name)
            lag = lever.emergency_implementation_lag \
                if emergency and lever.emergency_implementation_lag is not None \
                else lever.implementation_lag
            reason = None
            capability_reason = world_capability_reason(session.world, name)
            if capability_reason is not None:
                reason = capability_reason
            for capability in sorted(lever.requires):
                if reason is None and not getattr(econ.cfg, capability, False):
                    reason = f"missing_capability:{capability}"
                    break
            if reason is None and (economy_id, name) in pending_levers:
                reason = "pending_conflict"
            last = self.last_effective_tick.get(policy_key(economy_id, name))
            if reason is None and last is not None \
                    and session.boundary_tick + lag < last + lever.min_hold_ticks:
                reason = "minimum_hold"
            if reason is None:
                for prerequisite in sorted(lever.enabled_if):
                    if not self._projected_value_at(
                        session,
                        economy_id,
                        prerequisite,
                        session.boundary_tick + lag,
                    ):
                        reason = f"disabled_prerequisite:{prerequisite}"
                        break
            validation = lever.validation
            value_kind = "unknown"
            minimum = maximum = None
            choices: tuple[Any, ...] = ()
            nullable = isinstance(validation, (NullableRange, EconomyId))
            if isinstance(validation, IntRange):
                value_kind, minimum, maximum = "integer", int(validation.lo), int(validation.hi)
            elif isinstance(validation, (Range, NullableRange)):
                value_kind, minimum, maximum = "number", validation.lo, validation.hi
            elif isinstance(validation, Bool):
                value_kind = "bool"
            elif isinstance(validation, Choices):
                value_kind, choices = "choice", validation.values
            elif isinstance(validation, EconomyId):
                value_kind = "economy_id"
                choices = tuple(idx for idx in range(len(economies)) if idx != economy_id)
                if name == "peg_anchor":
                    target_tick = session.boundary_tick + lag
                    choices = tuple(
                        idx for idx in choices
                        if self._projected_value_at(
                            session, idx, "fx_regime", target_tick,
                        ) != "peg"
                    )
                choices += (None,)
            elif isinstance(validation, EconomySet):
                value_kind = "economy_set"
                choices = tuple(idx for idx in range(len(economies)) if idx != economy_id)

            if reason is None and name == "fx_regime":
                target_tick = session.boundary_tick + lag
                projected_regime = self._projected_value_at(
                    session, economy_id, "fx_regime", target_tick,
                )
                if projected_regime == "float":
                    anchor = self._projected_value_at(
                        session, economy_id, "peg_anchor", target_tick,
                    )
                    available_anchors = tuple(
                        idx for idx in range(len(economies))
                        if idx != economy_id
                        and self._projected_value_at(
                            session, idx, "fx_regime", target_tick,
                        ) != "peg"
                    )
                    anchor_ok = (
                        isinstance(anchor, int)
                        and not isinstance(anchor, bool)
                        and 0 <= anchor < len(economies)
                        and anchor != economy_id
                        and self._projected_value_at(
                            session, anchor, "fx_regime", target_tick,
                        ) != "peg"
                    ) or bool(available_anchors)
                    other_pegger = any(
                        idx != economy_id
                        and self._projected_value_at(
                            session, idx, "fx_regime", target_tick,
                        ) == "peg"
                        for idx in range(len(economies))
                    )
                    if not anchor_ok or other_pegger:
                        reason = "joint_constraint:peg_unavailable"
            if reason is None and name == "peg_anchor" \
                    and current is None and choices == (None,):
                reason = "joint_constraint:no_valid_peg_anchor"

            budget_key = (economy_id, seat, decision_group)
            minimum_admin = self.cost_spec.proposal_admin_overhead + lever.admin_weight
            if reason is None and self.admin_remaining.get(budget_key, 0.0) \
                    + 1e-12 < minimum_admin:
                reason = "admin_capacity_exceeded"
            result.append(PermittedAction(
                lever=name,
                current_value=current,
                allowed=reason is None,
                reason_code=reason,
                value_kind=value_kind,
                minimum=minimum,
                maximum=maximum,
                choices=choices,
                nullable=nullable,
                control_scale=lever.control_scale,
                max_step=CONTROL_SPECS[name].max_step,
                earliest_effective_tick=session.boundary_tick + lag,
            ))
        return result

    def submit(
        self,
        session: Any,
        proposal: PolicyProposal,
        *,
        actor: str,
        input_event_type: str = "proposal_submitted",
        input_already_recorded: bool = False,
        input_origin: str = "direct",
    ) -> PolicyDecision:
        session.assert_boundary_integrity()
        if not isinstance(proposal, PolicyProposal):
            raise TypeError("proposal must be a PolicyProposal")
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("actor must be a non-empty string")
        if not isinstance(input_event_type, str) or input_event_type not in {
            "proposal_submitted", "timeout",
        }:
            raise ValueError(
                "input_event_type must be 'proposal_submitted' or 'timeout'"
            )
        if not isinstance(input_already_recorded, bool):
            raise TypeError("input_already_recorded must be a boolean")
        if not isinstance(input_origin, str) or input_origin not in {
            "automatic", "direct", "external",
        }:
            raise ValueError(
                "input_origin must be 'automatic', 'direct', or 'external'"
            )
        proposal_dict = proposal.to_dict()
        proposal_payload = canonical_json(proposal_dict)
        existing_id = self.idempotency.get(proposal.idempotency_key)
        if existing_id is not None:
            existing = self.decisions[existing_id]
            if self.idempotency_payload.get(proposal.idempotency_key) != proposal_payload:
                raise ValueError("idempotency key was reused with a different proposal payload")
            return existing

        context = self.contexts.get(proposal.context_id)
        if not input_already_recorded:
            self.events.append(
                input_event_type,
                "input",
                session.boundary_tick,
                session.phase,
                economy_id=context.economy_id if context else None,
                seat=context.seat if context else None,
                actor=actor,
                context_id=proposal.context_id,
                proposal_id=proposal.proposal_id,
                requested_actions=proposal_dict["actions"],
                payload={
                    "proposal": proposal_dict,
                    "input_origin": input_origin,
                },
            )

        def reject(
            rejected_context: DecisionContext | None, reason: str,
        ) -> PolicyDecision:
            return self._reject(
                session,
                proposal,
                rejected_context,
                reason,
                proposal_payload=proposal_payload,
            )

        if any(
            decision.proposal_id == proposal.proposal_id
            for decision in self.decisions.values()
        ):
            return reject(context, "duplicate_proposal_id")
        if context is None:
            return reject(None, "unknown_context")
        if proposal.schema_version != context.schema_version:
            return reject(context, "schema_version_conflict")
        if session.boundary_tick > context.expires_at_tick:
            return reject(context, "context_expired")
        superseded, supersede_error = self._resolve_superseded(proposal, context)
        if supersede_error is not None:
            return reject(context, supersede_error)

        canonical_actions: list[PolicyAction] = []
        seen: set[str] = set()
        try:
            for action in proposal.actions:
                canonical = LEGACY_ALIASES.get(action.lever, action.lever)
                if canonical not in REGISTRY:
                    raise KeyError(canonical)
                if canonical in seen:
                    raise ValueError(f"duplicate canonical lever: {canonical}")
                seen.add(canonical)
                canonical_actions.append(PolicyAction(canonical, action.value))
        except (KeyError, ValueError, TypeError) as exc:
            return reject(context, f"invalid_actions:{exc}")
        if tuple(canonical_actions) != proposal.actions:
            proposal = replace(proposal, actions=tuple(canonical_actions))

        permitted = {item.lever: item for item in context.permitted_actions}
        for action in proposal.actions:
            item = permitted.get(action.lever)
            if item is None:
                return reject(context, "unauthorized_lever")
            # Most masks are advisory projections: pending conflicts may be
            # intentionally superseded and same-boundary World conflicts are
            # arbitrated atomically at execution.  A structurally absent World
            # mechanism, however, can never become legal during this run.
            if not item.allowed and (item.reason_code or "").startswith(
                "missing_world_capability:"
            ):
                return reject(context, item.reason_code or "forbidden_action")
            expected = proposal.based_on_policy_versions.get(action.lever)
            current = self.policy_versions[policy_key(context.economy_id, action.lever)]
            if expected != current:
                return reject(context, "stale_policy_version")
            for prerequisite in REGISTRY[action.lever].enabled_if:
                expected_pre = proposal.based_on_policy_versions.get(prerequisite)
                current_pre = self.policy_versions[
                    policy_key(context.economy_id, prerequisite)
                ]
                if expected_pre != current_pre:
                    return reject(context, "stale_prerequisite_version")
            if any(
                other.context.economy_id == context.economy_id
                and other.status == "accepted_pending"
                and action.lever in other.touched_levers
                and other is not superseded
                for other in self.pending.values()
            ):
                return reject(context, "pending_conflict")

        world_size = len(_economies(session.world))
        dynamic_error = self._dynamic_reference_error(
            proposal,
            economy_id=context.economy_id,
            world_size=world_size,
        )
        if dynamic_error is not None:
            return reject(context, dynamic_error)

        lags = [
            (
                REGISTRY[action.lever].emergency_implementation_lag
                if context.emergency
                and REGISTRY[action.lever].emergency_implementation_lag is not None
                else REGISTRY[action.lever].implementation_lag
            )
            for action in proposal.actions
        ]
        effective_tick = session.boundary_tick + max(lags, default=0)
        try:
            batch, projected_last_effective = self._project_candidate_batch(
                session,
                context,
                proposal,
                effective_tick,
                superseded=superseded,
            )
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            return reject(context, f"registry_validation:{exc}")
        for action in proposal.actions:
            lever = REGISTRY[action.lever]
            for versioned_name in (
                action.lever,
                *tuple(sorted(lever.enabled_if)),
            ):
                key = policy_key(context.economy_id, versioned_name)
                if projected_last_effective.get(key) \
                        != self.last_effective_tick.get(key):
                    reason = (
                        "stale_projected_policy_version"
                        if versioned_name == action.lever
                        else "stale_projected_prerequisite_version"
                    )
                    return reject(context, reason)
        changed = tuple(entry for entry in batch.entries if entry.old != entry.new)
        if not changed:
            # A target can look like a no-op only because an accepted pending
            # dependency is projected to establish it first. Keep such a proposal
            # pending: if that dependency later loses a joint-conflict vote, this
            # action still enforces its promised target instead of silently
            # finalizing a no-op that never became true.
            live_econ = _economies(session.world)[context.economy_id]
            changed = tuple(
                replace(
                    entry,
                    old=getattr(
                        live_econ.external_policy
                        if entry.lever.scope == "external"
                        else live_econ.policy,
                        entry.name,
                    ),
                )
                for entry in batch.entries
                if getattr(
                    live_econ.external_policy
                    if entry.lever.scope == "external"
                    else live_econ.policy,
                    entry.name,
                ) != entry.new
            )
        for entry in changed:
            last = projected_last_effective.get(
                policy_key(context.economy_id, entry.name)
            )
            if last is not None and effective_tick < last + entry.lever.min_hold_ticks:
                return reject(context, "minimum_hold")
        if not changed:
            if superseded is not None:
                self._supersede(session, superseded, proposal.proposal_id)
            decision = self._new_decision(
                proposal, "accepted_noop", "no_change", session.boundary_tick,
                effective_tick=None,
            )
            self._remember(
                proposal, context, decision, proposal_payload=proposal_payload,
            )
            self.events.append(
                "decision_accepted_noop", "derived", session.boundary_tick, session.phase,
                economy_id=context.economy_id, seat=context.seat, actor="coordinator",
                context_id=context.context_id, proposal_id=proposal.proposal_id,
                decision_id=decision.decision_id, status=decision.status,
                reason=decision.reason_code,
            )
            return decision

        admin_cost = self.cost_spec.admin_cost(changed)
        adjustment_cost = self.cost_spec.estimate(changed, emergency=context.emergency)
        budget_key = (context.economy_id, context.seat, context.decision_group)
        remaining = self.admin_remaining.get(budget_key, 0.0)
        supersede_key = (
            (
                superseded.context.economy_id,
                superseded.context.seat,
                superseded.context.decision_group,
            )
            if superseded is not None else None
        )
        supersede_refund = 0.0
        if superseded is not None and supersede_key == budget_key \
                and self._reservation_is_in_installed_window(superseded):
            supersede_refund = (
                superseded.reserved_admin_cost * self.cost_spec.refund_on_supersede
            )
        if admin_cost > remaining + supersede_refund + 1e-12:
            return reject(context, "admin_capacity_exceeded")
        if superseded is not None:
            self._supersede(session, superseded, proposal.proposal_id)
            remaining = self.admin_remaining.get(budget_key, 0.0)
        self.admin_remaining[budget_key] = remaining - admin_cost
        self.admin_reserved[budget_key] = self.admin_reserved.get(budget_key, 0.0) + admin_cost

        decision = self._new_decision(
            proposal,
            "accepted_pending",
            "accepted",
            session.boundary_tick,
            effective_tick=effective_tick,
            admin_cost=admin_cost,
            adjustment_cost=adjustment_cost,
        )
        pending = PendingDecision(
            decision=decision,
            proposal=proposal,
            context=context,
            reserved_admin_cost=admin_cost,
            adjustment_cost=adjustment_cost,
        )
        self.pending[decision.decision_id] = pending
        self._remember(
            proposal, context, decision, proposal_payload=proposal_payload,
        )
        self.events.append(
            "decision_accepted", "derived", session.boundary_tick, session.phase,
            economy_id=context.economy_id, seat=context.seat, actor="coordinator",
            context_id=context.context_id, proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id, status=decision.status,
            reason=decision.reason_code,
            requested_actions=[action.to_dict() for action in proposal.actions],
            payload={
                "effective_tick": effective_tick,
                "reserved_admin_cost": admin_cost,
                "adjustment_cost": adjustment_cost,
            },
        )
        return decision

    def _new_decision(
        self,
        proposal: PolicyProposal,
        status: str,
        reason: str,
        accepted_tick: int | None,
        *,
        effective_tick: int | None,
        admin_cost: float = 0.0,
        adjustment_cost: float = 0.0,
    ) -> PolicyDecision:
        sequence = self.next_decision_sequence
        self.next_decision_sequence += 1
        return PolicyDecision(
            decision_id=f"decision:{sequence:012d}",
            proposal_id=proposal.proposal_id,
            status=status,
            reason_code=reason,
            accepted_tick=accepted_tick,
            effective_tick=effective_tick,
            accepted_sequence=sequence,
            reserved_admin_cost=admin_cost,
            adjustment_cost=adjustment_cost,
        )

    def _supersede(
        self,
        session: Any,
        pending: PendingDecision,
        replacement_proposal_id: str,
    ) -> None:
        pending.status = "superseded"
        pending.decision = replace(
            pending.decision, status="superseded", reason_code="superseded"
        )
        self.decisions[pending.decision.decision_id] = pending.decision
        self._refund(pending, self.cost_spec.refund_on_supersede)
        self.events.append(
            "decision_superseded", "derived", session.boundary_tick, session.phase,
            economy_id=pending.context.economy_id, seat=pending.context.seat,
            actor="coordinator", context_id=pending.context.context_id,
            proposal_id=pending.proposal.proposal_id,
            decision_id=pending.decision.decision_id,
            status="superseded", reason="superseded",
            payload={"replacement_proposal_id": replacement_proposal_id},
        )

    def _remember(
        self,
        proposal: PolicyProposal,
        context: DecisionContext,
        decision: PolicyDecision,
        *,
        proposal_payload: str,
    ) -> None:
        self.decisions[decision.decision_id] = decision
        self.idempotency[proposal.idempotency_key] = decision.decision_id
        self.idempotency_payload.setdefault(
            proposal.idempotency_key, proposal_payload
        )
        self.proposal_for_context[context.context_id] = proposal.proposal_id

    def _reject(
        self,
        session: Any,
        proposal: PolicyProposal,
        context: DecisionContext | None,
        reason: str,
        *,
        proposal_payload: str,
    ) -> PolicyDecision:
        decision = self._new_decision(
            proposal, "rejected", reason, None, effective_tick=None
        )
        self.decisions[decision.decision_id] = decision
        self.idempotency[proposal.idempotency_key] = decision.decision_id
        self.idempotency_payload.setdefault(
            proposal.idempotency_key, proposal_payload
        )
        self.events.append(
            "decision_rejected", "derived", session.boundary_tick, session.phase,
            economy_id=context.economy_id if context else None,
            seat=context.seat if context else None,
            actor="coordinator", context_id=proposal.context_id,
            proposal_id=proposal.proposal_id, decision_id=decision.decision_id,
            status="rejected", reason=reason,
        )
        return decision

    def cancel(self, session: Any, decision_id: str, *, actor: str) -> PolicyDecision:
        session.assert_boundary_integrity()
        if not isinstance(decision_id, str) or not decision_id:
            raise ValueError("decision_id must be a non-empty string")
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("actor must be a non-empty string")
        pending = self.pending.get(decision_id)
        if pending is None or pending.status != "accepted_pending":
            raise ValueError("decision is not active pending")
        # Invalid and duplicate requests are not events.  Append only after every
        # precondition has passed so the input stream remains a replayable record
        # of accepted external commands rather than an attempted-request log.
        self.events.append(
            "pending_cancel_requested", "input", session.boundary_tick, session.phase,
            actor=actor, decision_id=decision_id,
        )
        pending.status = "cancelled"
        old = pending.decision
        updated = replace(old, status="cancelled", reason_code="cancelled")
        pending.decision = updated
        self.decisions[decision_id] = updated
        self._refund(pending, self.cost_spec.refund_on_cancel)
        self.events.append(
            "decision_cancelled", "derived", session.boundary_tick, session.phase,
            economy_id=pending.context.economy_id, seat=pending.context.seat,
            actor="coordinator", context_id=pending.context.context_id,
            proposal_id=pending.proposal.proposal_id, decision_id=decision_id,
            status="cancelled", reason="cancelled",
        )
        return updated

    def _prepare_due_transaction(
        self,
        session: Any,
        pending_items: tuple[PendingDecision, ...],
    ):
        """Revalidate Coordinator controls before preparing an execution subset."""
        try:
            projected = clone_world_for_policy_projection(session.world)
            self._apply_pending_sequence(
                projected,
                pending_items,
                session.boundary_tick,
                self.last_effective_tick,
                validate_controls=True,
            )
        except Exception as exc:
            raise PolicyTransactionError(
                str(exc),
                (item.decision.decision_id for item in pending_items),
            ) from exc
        return prepare_world_policy_transaction(session, pending_items)

    def _pairwise_unambiguous_due_subset(
        self,
        session: Any,
        due: tuple[PendingDecision, ...],
    ):
        """Scalable conservative fallback that preserves obvious safe decisions."""
        individually_valid: list[PendingDecision] = []
        for item in due:
            try:
                self._prepare_due_transaction(session, (item,))
            except PolicyTransactionError:
                continue
            individually_valid.append(item)

        conflicted: set[str] = set()
        for left, right in combinations(individually_valid, 2):
            try:
                self._prepare_due_transaction(session, (left, right))
            except PolicyTransactionError:
                conflicted.update((
                    left.decision.decision_id,
                    right.decision.decision_id,
                ))
        safe = tuple(
            item for item in individually_valid
            if item.decision.decision_id not in conflicted
        )
        if not safe:
            return (), None
        try:
            return safe, self._prepare_due_transaction(session, safe)
        except PolicyTransactionError:
            return (), None

    def _conservative_due_subset(self, session: Any, due: list[PendingDecision]):
        """Return only candidates common to every largest valid transaction.

        Trying the full due set first preserves positive dependencies such as a
        same-boundary peg exit+entry handoff.  If the set is invalid, executing an
        arbitrary maximal subset would privilege one side of a symmetric conflict.
        We therefore intersect all largest valid subsets: only unambiguously
        unrelated decisions may proceed; every ambiguous conflict candidate fails.
        """
        original_due = tuple(due)
        peg_conflicts = self._peg_conflict_ids(session.world, original_due)
        due = [
            item for item in due
            if item.decision.decision_id not in peg_conflicts
        ]
        if not due:
            return (), None, "joint_world_conflict"

        try:
            prepared = self._prepare_due_transaction(session, tuple(due))
            return (
                tuple(due),
                prepared,
                "joint_world_conflict" if peg_conflicts else None,
            )
        except PolicyTransactionError as full_error:
            failure_reason = str(full_error)

        attempts = 0
        max_attempts = 4_096
        for size in range(len(due) - 1, 0, -1):
            valid: list[tuple[PendingDecision, ...]] = []
            for subset in combinations(due, size):
                attempts += 1
                if attempts > max_attempts:
                    safe, prepared = self._pairwise_unambiguous_due_subset(
                        session, tuple(due),
                    )
                    return (
                        safe,
                        prepared,
                        "joint_world_conflict:conservative_search_limit",
                    )
                try:
                    self._prepare_due_transaction(session, subset)
                except PolicyTransactionError:
                    continue
                valid.append(subset)
            if not valid:
                continue

            safe_ids = {
                item.decision.decision_id for item in valid[0]
            }
            for subset in valid[1:]:
                safe_ids.intersection_update(
                    item.decision.decision_id for item in subset
                )
            safe = tuple(
                item for item in due if item.decision.decision_id in safe_ids
            )
            if not safe:
                return (), None, "joint_world_conflict"
            try:
                prepared = self._prepare_due_transaction(session, safe)
            except PolicyTransactionError:
                # The intersection can itself be invalid when validity relies on
                # complementary actions.  Executing none is the conservative rule.
                return (), None, "joint_world_conflict"
            return safe, prepared, "joint_world_conflict"
        return (), None, failure_reason

    def execute_due(self, session: Any) -> list[PolicyDecision]:
        session.assert_boundary_integrity()
        due = [
            item for item in self.pending.values()
            if item.status == "accepted_pending" and item.effective_tick == session.boundary_tick
        ]
        due.sort(key=lambda item: item.decision.accepted_sequence or -1)
        if not due:
            return []

        candidates, prepared, exclusion_reason = self._conservative_due_subset(
            session, due,
        )
        candidate_ids = {item.decision.decision_id for item in candidates}
        for item in due:
            if item.decision.decision_id not in candidate_ids:
                self._fail_execution(
                    session, item, exclusion_reason or "joint_world_conflict",
                )
        if prepared is None:
            return [self.decisions[item.decision.decision_id] for item in due]

        try:
            changes = commit_world_policy_transaction(session, prepared)
        except PolicyTransactionError as exc:
            for item in candidates:
                self._fail_execution(session, item, str(exc))
            return [self.decisions[item.decision.decision_id] for item in due]

        for item in candidates:
            item.status = "effective"
            item.decision = replace(item.decision, status="effective", reason_code="effective")
            self.decisions[item.decision.decision_id] = item.decision
            key = (item.context.economy_id, item.context.seat, item.context.decision_group)
            if self._reservation_is_in_installed_window(item):
                self.admin_reserved[key] = max(
                    0.0, self.admin_reserved.get(key, 0.0) - item.reserved_admin_cost
                )
        self.events.append(
            "policy_transaction_effective", "derived", session.boundary_tick, session.phase,
            transaction_id=prepared.transaction_id, actor="policy_executor",
            status="effective", effective_changes=changes,
            policy_versions_before=prepared.versions_before,
            policy_versions_after=prepared.versions_after,
            payload={"decision_ids": prepared.decision_ids},
        )
        return [self.decisions[item.decision.decision_id] for item in due]

    def _fail_execution(self, session: Any, pending: PendingDecision, reason: str) -> None:
        pending.status = "failed_at_execution"
        pending.decision = replace(
            pending.decision, status="failed_at_execution", reason_code=reason
        )
        self.decisions[pending.decision.decision_id] = pending.decision
        self._refund(pending, self.cost_spec.refund_on_failed_execution)
        self.events.append(
            "decision_failed_at_execution", "derived", session.boundary_tick, session.phase,
            economy_id=pending.context.economy_id, seat=pending.context.seat,
            actor="policy_executor", context_id=pending.context.context_id,
            proposal_id=pending.proposal.proposal_id,
            decision_id=pending.decision.decision_id,
            status="failed_at_execution", reason=reason,
        )

    def _refund(self, pending: PendingDecision, fraction: float) -> None:
        key = (pending.context.economy_id, pending.context.seat, pending.context.decision_group)
        if not self._reservation_is_in_installed_window(pending):
            return
        refund = pending.reserved_admin_cost * fraction
        self.admin_remaining[key] = self.admin_remaining.get(key, 0.0) + refund
        self.admin_reserved[key] = max(
            0.0, self.admin_reserved.get(key, 0.0) - pending.reserved_admin_cost
        )
