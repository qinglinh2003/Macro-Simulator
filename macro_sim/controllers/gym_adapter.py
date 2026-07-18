"""Optional Gymnasium-compatible semi-Markov adapter.

Gymnasium is an optional dependency.  The adapter itself remains importable for
frontend/direct-trace tests when Gymnasium is absent; installing the ``rl`` extra
adds formal spaces and ``Env`` inheritance.
"""
from __future__ import annotations

from dataclasses import replace
import pickle
from typing import Any, Mapping, Sequence

import numpy as np

from macro_sim.core.policy_registry import Choices, EconomyId, EconomySet, REGISTRY

from .occupants import HumanQueueOccupant
from .protocol import DecisionContext, PolicyAction, PolicyProposal
from .session import AWAITING_HUMAN, ControlledSimulationSession

try:  # pragma: no cover - exercised when the optional extra is installed
    import gymnasium as gym
    from gymnasium import spaces
    _EnvBase = gym.Env
except ImportError:  # a useful engine/frontend adapter without a heavyweight RL install
    gym = None
    spaces = None
    _EnvBase = object


class ControllerEnv(_EnvBase):
    """One action per server-issued DecisionContext, not one action per tick."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        session: ControlledSimulationSession,
        *,
        economy_id: int,
        seat: str,
        objective_evaluator: Any = None,
        max_boundary_tick: int | None = None,
    ) -> None:
        if isinstance(economy_id, bool) or not isinstance(economy_id, int):
            raise TypeError("economy_id must be an integer")
        if max_boundary_tick is not None and (
            isinstance(max_boundary_tick, bool)
            or not isinstance(max_boundary_tick, int)
            or max_boundary_tick < 0
        ):
            raise ValueError("max_boundary_tick must be a non-negative integer or None")
        valid_seats = frozenset(lever.owner_role for lever in REGISTRY.values())
        if seat not in valid_seats:
            raise ValueError(f"unknown controller seat: {seat}")
        economies = getattr(session.world, "economies", None)
        economy_count = len(economies) if economies is not None else 1
        if not 0 <= economy_id < economy_count:
            raise ValueError("controller economy is out of range")
        economy = economies[economy_id] if economies is not None else session.world
        action_levers = tuple(sorted(
            name
            for name, lever in REGISTRY.items()
            if lever.owner_role == seat
            and (lever.scope != "external" or hasattr(economy, "external_policy"))
        ))
        if not action_levers:
            raise ValueError(f"controller seat {seat!r} owns no policy levers")
        economy_targets = tuple(
            target for target in range(economy_count) if target != economy_id
        )
        dimensions: list[tuple[str, int | None]] = []
        for lever_name in action_levers:
            if isinstance(REGISTRY[lever_name].validation, EconomySet):
                dimensions.extend(
                    (lever_name, target) for target in economy_targets
                )
            else:
                dimensions.append((lever_name, None))

        self.economy_id = economy_id
        self.seat = seat
        self.objective_evaluator = objective_evaluator
        self.max_boundary_tick = max_boundary_tick
        self._objective_genesis = (
            pickle.dumps(objective_evaluator, protocol=5)
            if objective_evaluator is not None else None
        )
        self._genesis_decision_ids = frozenset(session.coordinator.decisions)
        self._charged_adjustment_costs: dict[str, float] = {}
        self._settled_adjustment_costs: set[str] = set()
        self._action_probe_cache: dict[tuple[Any, ...], tuple[bool, float, str]] = {}
        self.session = session
        self.context: DecisionContext | None = None
        self.action_levers = action_levers
        self._economy_targets = economy_targets
        self.action_dimensions = tuple(dimensions)
        self.observation_features = self._observation_feature_names(session)
        if spaces is not None:
            self.action_space = spaces.MultiDiscrete(
                np.full(len(self.action_dimensions), 3, dtype=np.int64)
            )
            obs_len = len(self.observation_features)
            self.observation_space = spaces.Box(
                low=-np.inf, high=np.inf, shape=(obs_len,), dtype=np.float64
            )
        else:
            self.action_space = None
            self.observation_space = None

        assignments_before = dict(session.seat_assignments)
        archive_before = dict(session.assignment_archive)
        sequence_before = session.next_assignment_sequence
        events_before = list(session.events.events)
        event_head_before = session.events.head_hash
        try:
            session.assign_seat(
                economy_id, seat, HumanQueueOccupant(), actor="gym", log_event=False
            )
            genesis = pickle.dumps(session, protocol=5)
        except Exception:
            session.seat_assignments.clear()
            session.seat_assignments.update(assignments_before)
            session.assignment_archive.clear()
            session.assignment_archive.update(archive_before)
            session.next_assignment_sequence = sequence_before
            session.events.events[:] = events_before
            session.events._head_hash = event_head_before
            raise
        self._genesis = genesis

    def _observation_feature_names(
        self, session: ControlledSimulationSession,
    ) -> tuple[str, ...]:
        """Declare the stable, inspectable SMDP vector contract."""
        names = ["boundary_tick", "elapsed_ticks"]
        service = getattr(session, "release_service", None)
        fields = () if service is None else service.spec.fields
        for field in sorted(fields, key=lambda item: item.series_id):
            names.extend((
                f"release:{field.series_id}:value",
                f"release:{field.series_id}:missing",
            ))
        names.extend((
            "decision:ticks_to_expiry",
            "decision:emergency",
            "decision:emergency_trigger_present",
            "admin:remaining",
            "admin:reserved",
        ))
        for lever in self.action_levers:
            names.extend((
                f"policy:{lever}:value",
                f"policy:{lever}:is_none",
                f"policy:{lever}:pending_target",
                f"policy:{lever}:pending_target_is_none",
                f"policy:{lever}:pending_present",
                f"policy:{lever}:version",
                f"policy:{lever}:last_effective_age",
                f"policy:{lever}:last_effective_never",
                f"policy:{lever}:next_eligibility_delta",
                f"policy:{lever}:pending_effective_delta",
            ))
        for lever, target in self.action_dimensions:
            label = lever if target is None else f"{lever}[{target}]"
            names.extend((
                f"action:{label}:down_eligible",
                f"action:{label}:up_eligible",
                f"action:{label}:down_cost",
                f"action:{label}:up_cost",
            ))
        return tuple(names)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        if gym is not None:
            super().reset(seed=seed)
        self.session = pickle.loads(self._genesis)
        self.objective_evaluator = (
            pickle.loads(self._objective_genesis)
            if self._objective_genesis is not None else None
        )
        self._charged_adjustment_costs = {}
        self._settled_adjustment_costs = set(self._genesis_decision_ids)
        self._action_probe_cache = {}
        self.context, _trace = self._seek_next_context()
        if self.context is None:
            raise RuntimeError("no decision context exists before max_boundary_tick")
        self._prime_objective(self.context)
        observation = self._vector(self.context)
        return observation, self._info(self.context, elapsed_ticks=0)

    def step(self, action):
        if self.context is None:
            raise RuntimeError("reset() must be called before step()")
        previous_context = self.context
        previous_tick = previous_context.boundary_tick
        proposal = self.action_to_proposal(action, previous_context)
        event_start = len(self.session.events.events)
        self.session.submit_human_proposal(proposal, actor="gym")
        result = self.session.advance()
        interval_results = [result]
        interval_evaluations = []
        evaluation = self._evaluate_advanced_result(result)
        if evaluation is not None:
            interval_evaluations.append(evaluation)
        if result.status == AWAITING_HUMAN:
            next_context = self._select_target_context(result)
            if next_context is None:
                raise RuntimeError("another human-controlled seat is blocking the Gym environment")
        else:
            next_context, trace = self._seek_next_context(
                on_advanced=lambda item: interval_evaluations.append(item)
            )
            interval_results.extend(trace)
        truncated = next_context is None
        elapsed = self.session.boundary_tick - previous_tick if truncated else (
            next_context.boundary_tick - previous_tick
        )
        output_context = next_context or self._terminal_context(previous_context, elapsed)
        decisions = self._merge_decisions(interval_results)
        decisions = self._tracked_lifecycle_updates(decisions)
        adjustment_cost = self._account_adjustment_cost(decisions)
        reward, objective = self._interval_reward(
            interval_evaluations,
            adjustment_cost=adjustment_cost,
            elapsed_ticks=max(1, elapsed),
        )
        if self.objective_evaluator is not None:
            assert objective is not None
        self.context = None if truncated else next_context
        self._action_probe_cache = {}
        terminated = False
        info = self._info(output_context, elapsed_ticks=elapsed)
        info["decisions"] = [decision.__dict__.copy() for decision in decisions]
        info["interval_trace"] = [
            {
                "boundary_tick": item.boundary_tick,
                "decision_ids": [decision.decision_id for decision in item.decisions],
                "status": item.status,
            }
            for item in interval_results
        ]
        info["interval_events"] = [
            dict(event) for event in self.session.events.events[event_start:]
        ]
        if objective is not None:
            info["objective"] = objective
        if truncated:
            info["terminal_observation"] = True
        return self._vector(output_context), float(reward), terminated, truncated, info

    def action_to_proposal(
        self,
        action: Mapping[str, Any] | Sequence[int] | np.ndarray,
        context: DecisionContext | None = None,
    ) -> PolicyProposal:
        context = context or self.context
        if context is None:
            raise RuntimeError("no active DecisionContext")
        permitted = {item.lever: item for item in context.permitted_actions}
        actions: list[PolicyAction] = []
        if isinstance(action, Mapping):
            for lever, value in sorted(action.items()):
                if lever not in permitted:
                    # Advisory masks are not authority: allow the Coordinator to
                    # reject an adversarial lever safely.
                    actions.append(PolicyAction(str(lever), value))
                elif value != permitted[lever].current_value:
                    actions.append(PolicyAction(str(lever), value))
        else:
            try:
                raw_shape = np.shape(action)
            except (TypeError, ValueError) as exc:
                raise ValueError("directional action must be a flat numeric vector") from exc
            expected_shape = (len(self.action_dimensions),)
            if raw_shape != expected_shape:
                raise ValueError(
                    "directional action must have shape "
                    f"{expected_shape}, got {raw_shape}"
                )
            if isinstance(action, np.ndarray) and action.dtype.kind not in {
                "i", "u", "f",
            }:
                raise ValueError(
                    "directional action entries must be finite non-boolean integers"
                )
            raw_items = tuple(action)
            checked: list[int] = []
            for value in raw_items:
                if isinstance(value, (bool, np.bool_)) or not isinstance(
                    value, (int, float, np.integer, np.floating),
                ):
                    raise ValueError(
                        "directional action entries must be finite "
                        "non-boolean integers"
                    )
                try:
                    numeric = float(value)
                except (OverflowError, TypeError, ValueError) as exc:
                    raise ValueError(
                        "directional action entries must be finite "
                        "non-boolean integers"
                    ) from exc
                if not np.isfinite(numeric) or not numeric.is_integer():
                    raise ValueError(
                        "directional action entries must be finite "
                        "non-boolean integers"
                    )
                code = int(numeric)
                if code not in (0, 1, 2):
                    raise ValueError(
                        "directional action codes are 0=down, 1=hold, 2=up"
                    )
                checked.append(code)
            codes = np.asarray(checked, dtype=np.int64)
            actions, _selected, _cost = self._legal_vector_actions(codes, context)
        proposal_id = f"proposal:{context.context_id}:gym"
        return PolicyProposal(
            proposal_id=proposal_id,
            idempotency_key=proposal_id,
            context_id=context.context_id,
            actions=tuple(actions),
            reason="gym_action",
            based_on_policy_versions=dict(context.policy_versions),
        )

    def _vector_requests(self, codes, context: DecisionContext):
        permitted = {item.lever: item for item in context.permitted_actions}
        requests = []
        for index, ((lever, target), raw_code) in enumerate(zip(
            self.action_dimensions, codes, strict=True,
        )):
            code = int(raw_code)
            if code == 1:
                continue
            item = permitted.get(lever)
            if item is None or not item.allowed:
                continue
            if isinstance(REGISTRY[lever].validation, EconomySet):
                current = set(item.current_value or ())
                desired = target not in current if code == 2 else False
                if (target in current) == desired:
                    continue
            else:
                desired = self._directional_value(item, code)
                if desired == item.current_value:
                    continue
            requests.append((index, lever, target, code, desired))
        return requests

    def _actions_from_requests(self, requests, context: DecisionContext):
        """Resolve directional requests into one coherent atomic target map."""
        permitted = {item.lever: item for item in context.permitted_actions}
        desired: dict[str, Any] = {}
        set_targets: dict[str, set[int]] = {}
        for _index, lever, target, code, value in requests:
            item = permitted[lever]
            if isinstance(REGISTRY[lever].validation, EconomySet):
                current = set_targets.setdefault(lever, set(item.current_value or ()))
                if code == 0:
                    current.discard(target)
                else:
                    current.add(target)
                desired[lever] = sorted(current)
            else:
                desired[lever] = value

        def stage(lever: str, value: Any) -> bool:
            item = permitted.get(lever)
            if item is None or not item.allowed:
                return False
            desired[lever] = value
            return True

        # Monetary-regime transitions are one indivisible template.  Explicit
        # regime intent wins over a conflicting rate direction.
        regime_item = permitted.get("monetary_regime")
        rate_item = permitted.get("manual_policy_rate")
        current_regime = None if regime_item is None else regime_item.current_value
        current_rate = None if rate_item is None else rate_item.current_value
        if "monetary_regime" in desired:
            if desired["monetary_regime"] == "manual":
                if desired.get("manual_policy_rate", current_rate) is None:
                    default_rate = self._default_manual_rate(rate_item)
                    if not stage("manual_policy_rate", default_rate):
                        return None
            elif current_regime == "manual" or "manual_policy_rate" in desired:
                if not stage("manual_policy_rate", None):
                    return None
        elif "manual_policy_rate" in desired:
            if desired["manual_policy_rate"] is None and current_regime == "manual":
                if not stage("monetary_regime", "taylor"):
                    return None
            elif desired["manual_policy_rate"] is not None and current_regime != "manual":
                if not stage("monetary_regime", "manual"):
                    return None

        # Likewise, entering/exiting a peg is represented as a coherent pair.
        fx_item = permitted.get("fx_regime")
        anchor_item = permitted.get("peg_anchor")
        current_fx = None if fx_item is None else fx_item.current_value
        current_anchor = None if anchor_item is None else anchor_item.current_value
        if "fx_regime" in desired:
            if desired["fx_regime"] == "peg":
                if desired.get("peg_anchor", current_anchor) is None:
                    anchor = self._default_peg_anchor(anchor_item)
                    if anchor is None or not stage("peg_anchor", anchor):
                        return None
            elif current_fx == "peg" or "peg_anchor" in desired:
                if not stage("peg_anchor", None):
                    return None
        elif "peg_anchor" in desired:
            if desired["peg_anchor"] is None and current_fx == "peg":
                if not stage("fx_regime", "float"):
                    return None
            elif desired["peg_anchor"] is not None and current_fx != "peg":
                if not stage("fx_regime", "peg"):
                    return None

        actions = []
        for lever, value in sorted(desired.items()):
            item = permitted.get(lever)
            if item is None:
                return None
            current = item.current_value
            if isinstance(REGISTRY[lever].validation, EconomySet):
                if set(value) == set(current or ()):
                    continue
            elif value == current:
                continue
            actions.append(PolicyAction(lever, value))
        return tuple(actions), desired

    def _requests_reflected(self, requests, desired, context: DecisionContext) -> bool:
        permitted = {item.lever: item for item in context.permitted_actions}
        for _index, lever, target, code, value in requests:
            resolved = desired.get(lever, permitted[lever].current_value)
            if isinstance(REGISTRY[lever].validation, EconomySet):
                present = target in set(resolved or ())
                if present != (code == 2):
                    return False
            elif resolved != value:
                return False
        return True

    def _legal_vector_actions(self, codes, context: DecisionContext):
        """Return a deterministic Coordinator-accepted subset of vector intent."""
        selected = []
        selected_indices: set[int] = set()
        final_actions: tuple[PolicyAction, ...] = ()
        final_cost = 0.0
        for request in self._vector_requests(codes, context):
            trial = selected + [request]
            resolved = self._actions_from_requests(trial, context)
            if resolved is None:
                continue
            actions, desired = resolved
            if not self._requests_reflected(trial, desired, context):
                continue
            accepted, cost, _reason = self._probe_actions(actions, context)
            if not accepted:
                continue
            selected = trial
            selected_indices.add(request[0])
            final_actions = actions
            final_cost = cost
        return list(final_actions), selected_indices, final_cost

    def _probe_actions(
        self, actions: Sequence[PolicyAction], context: DecisionContext,
    ) -> tuple[bool, float, str]:
        """Ask an isolated Coordinator; never let a mask mutate live state."""
        action_key = tuple((action.lever, repr(action.value)) for action in actions)
        budget_key = (context.economy_id, context.seat, context.decision_group)
        coordinator = self.session.coordinator
        cache_key = (
            context.context_id,
            action_key,
            coordinator.admin_remaining.get(budget_key, 0.0),
            coordinator.admin_reserved.get(budget_key, 0.0),
            tuple(sorted(
                (decision_id, pending.status)
                for decision_id, pending in coordinator.pending.items()
            )),
        )
        cached = self._action_probe_cache.get(cache_key)
        if cached is not None:
            return cached
        probe_session = pickle.loads(pickle.dumps(self.session, protocol=5))
        proposal_id = f"proposal:{context.context_id}:gym"
        proposal = PolicyProposal(
            proposal_id=proposal_id,
            idempotency_key=proposal_id,
            context_id=context.context_id,
            actions=tuple(actions),
            reason="gym_action_probe",
            based_on_policy_versions=dict(context.policy_versions),
        )
        decision = probe_session.coordinator.submit(
            probe_session, proposal, actor="gym_mask_probe",
        )
        result = (
            decision.status in {"accepted_noop", "accepted_pending"},
            float(decision.adjustment_cost),
            decision.reason_code,
        )
        self._action_probe_cache[cache_key] = result
        return result

    def _default_manual_rate(self, item) -> float:
        economies = getattr(self.session.world, "economies", None)
        economy = (
            economies[self.economy_id]
            if economies is not None else self.session.world
        )
        value = float(getattr(economy, "_rate", economy.cfg.r_interest))
        if item is not None and item.minimum is not None:
            value = max(float(item.minimum), value)
        if item is not None and item.maximum is not None:
            value = min(float(item.maximum), value)
        return value

    @staticmethod
    def _default_peg_anchor(item) -> int | None:
        if item is None:
            return None
        return next(
            (value for value in item.choices if isinstance(value, int)
             and not isinstance(value, bool)),
            None,
        )

    @staticmethod
    def _directional_value(item, code: int):
        if item.value_kind == "bool":
            return code == 2
        if item.value_kind == "economy_set":
            current = set(item.current_value or ())
            if code == 0 and current:
                current.remove(sorted(current)[-1])
            elif code == 2:
                available = [value for value in item.choices if value not in current]
                if available:
                    current.add(available[0])
            return sorted(current)
        if item.choices:
            choices = list(item.choices)
            try:
                index = choices.index(item.current_value)
            except ValueError:
                index = 0
            return choices[max(0, min(len(choices) - 1, index + (-1 if code == 0 else 1)))]
        if item.value_kind in {"number", "integer"}:
            step = item.control_scale or item.max_step
            if step is None:
                return item.current_value
            if item.nullable and item.current_value is None:
                if code == 0:
                    return None
                value = float(item.minimum) if item.minimum is not None else 0.0
                return int(round(value)) if item.value_kind == "integer" else value
            base = float(item.current_value or 0.0)
            value = base + (-step if code == 0 else step)
            if item.nullable and code == 0 and item.minimum is not None \
                    and value < float(item.minimum):
                return None
            if item.minimum is not None:
                value = max(float(item.minimum), value)
            if item.maximum is not None:
                value = min(float(item.maximum), value)
            return int(round(value)) if item.value_kind == "integer" else value
        return item.current_value

    def action_mask(self, context: DecisionContext | None = None) -> np.ndarray:
        context = context or self.context
        if context is None:
            raise RuntimeError("no active DecisionContext")
        return self._direction_metadata(context)[0].copy()

    def _direction_metadata(self, context: DecisionContext):
        mask = np.zeros((len(self.action_dimensions), 3), dtype=np.int8)
        costs = np.zeros((len(self.action_dimensions), 3), dtype=np.float64)
        mask[:, 1] = 1
        for index in range(len(self.action_dimensions)):
            for code in (0, 2):
                codes = np.ones(len(self.action_dimensions), dtype=np.int64)
                codes[index] = code
                actions, selected, cost = self._legal_vector_actions(codes, context)
                if index not in selected or not actions:
                    continue
                mask[index, code] = 1
                costs[index, code] = cost
        return mask, costs

    @staticmethod
    def _merge_decisions(results) -> list[Any]:
        """Keep one final lifecycle snapshot per decision in stable first-seen order."""
        order: list[str] = []
        by_id: dict[str, Any] = {}
        for result in results:
            for decision in result.decisions:
                if decision.decision_id not in by_id:
                    order.append(decision.decision_id)
                by_id[decision.decision_id] = decision
        return [by_id[decision_id] for decision_id in order]

    def _account_adjustment_cost(self, decisions) -> float:
        """Charge a decision once across SMDP steps and realize later refunds."""
        total = 0.0
        refund_fraction = {
            "cancelled": self.session.cost_spec.refund_on_cancel,
            "superseded": self.session.cost_spec.refund_on_supersede,
            "failed_at_execution": self.session.cost_spec.refund_on_failed_execution,
        }
        for decision in decisions:
            decision_id = decision.decision_id
            if decision_id in self._settled_adjustment_costs:
                continue
            pending = self.session.coordinator.pending.get(decision_id)
            already_charged = decision_id in self._charged_adjustment_costs
            if not already_charged and (pending is None or (
                pending.context.economy_id != self.economy_id
                or pending.context.seat != self.seat
            )):
                # BoundaryResult is global.  One agent's reward must never absorb
                # another economy/seat's policy-adjustment cost.
                continue
            if decision.status == "accepted_pending":
                if decision_id not in self._charged_adjustment_costs:
                    cost = float(decision.adjustment_cost)
                    self._charged_adjustment_costs[decision_id] = cost
                    total += cost
                continue
            if decision.status == "effective":
                if decision_id not in self._charged_adjustment_costs:
                    total += float(decision.adjustment_cost)
                else:
                    self._charged_adjustment_costs.pop(decision_id)
                self._settled_adjustment_costs.add(decision_id)
                continue
            fraction = refund_fraction.get(decision.status)
            if fraction is None:
                continue
            if decision_id not in self._charged_adjustment_costs:
                # A proposal can be accepted and reach a terminal lifecycle state
                # between two decision boundaries.  Account for its non-refunded
                # portion even though this environment never observed the pending
                # snapshot on an earlier step.
                total += float(decision.adjustment_cost) * (1.0 - float(fraction))
                self._settled_adjustment_costs.add(decision_id)
                continue
            charged = self._charged_adjustment_costs.pop(decision_id)
            total -= charged * float(fraction)
            self._settled_adjustment_costs.add(decision_id)
        return total

    def _tracked_lifecycle_updates(self, decisions):
        """Surface out-of-band terminal transitions on the next Gym boundary."""
        result = list(decisions)
        present = {decision.decision_id for decision in result}
        for decision_id in tuple(self._charged_adjustment_costs):
            if decision_id in present:
                continue
            decision = self.session.coordinator.decisions.get(decision_id)
            if decision is not None and decision.status in {
                "cancelled", "superseded", "failed_at_execution",
            }:
                result.append(decision)
        return result

    def _released_observation(self, boundary_tick: int, *, elapsed_ticks: int = 1):
        """Return the seat-filtered observation used by the policy context/vector."""
        service = self.session.release_service
        if service is None:
            return self.context.observation if self.context is not None else None
        return service.observe(
            self.session.world,
            boundary_tick,
            economy_id=self.economy_id,
            role=self.seat,
            elapsed_ticks=elapsed_ticks,
        )

    def _objective_profile(self) -> str | None:
        if self.objective_evaluator is None:
            return None
        return (
            "human_comparable"
            if self.objective_evaluator.spec.human_comparable
            else "oracle_research"
        )

    def _objective_observation(
        self, boundary_tick: int, *, elapsed_ticks: int = 1,
    ):
        """Return a reward-only observation without widening policy information."""
        if self.objective_evaluator is None:
            raise RuntimeError("objective observation requested without an evaluator")
        if self.objective_evaluator.spec.human_comparable:
            return self._released_observation(
                boundary_tick, elapsed_ticks=elapsed_ticks,
            )
        service = self.session.release_service
        observe_oracle = getattr(service, "observe_oracle", None)
        if not callable(observe_oracle):
            raise RuntimeError(
                "oracle_research objectives require a ReleaseService with "
                "observe_oracle()"
            )
        return observe_oracle(
            self.session.world,
            boundary_tick,
            economy_id=self.economy_id,
            elapsed_ticks=elapsed_ticks,
        )

    def _release_history(self, boundary_tick: int):
        if self.objective_evaluator is None or self.session.release_service is None:
            return None
        return {
            term.series_id: self.session.release_service.history(
                self.economy_id,
                term.series_id,
                as_of_tick=boundary_tick,
            )
            for term in self.objective_evaluator.spec.terms
        }

    def _prime_objective(self, context: DecisionContext) -> None:
        """Mark reset-time vintages seen so pre-episode releases earn no reward."""
        if self.objective_evaluator is None:
            return
        observation = (
            context.observation
            if self.objective_evaluator.spec.human_comparable
            else self._objective_observation(
                context.boundary_tick, elapsed_ticks=1,
            )
        )
        self.objective_evaluator.evaluate(
            observation,
            adjustment_cost=0.0,
            elapsed_ticks=1,
            release_history=self._release_history(context.boundary_tick),
        )

    def _interval_reward(
        self,
        evaluations,
        *,
        adjustment_cost: float,
        elapsed_ticks: int,
    ) -> tuple[float, dict[str, Any] | None]:
        if self.objective_evaluator is None:
            return -adjustment_cost, None

        spec = self.objective_evaluator.spec
        divisor = elapsed_ticks if spec.time_normalization == "per_tick" else 1
        macro_sum = sum(item.macro_reward for item in evaluations)
        macro_reward = macro_sum / divisor
        raw_cost = float(spec.control_cost_weight) * adjustment_cost
        control_penalty = raw_cost / divisor
        component_names = sorted({
            name for item in evaluations for name in item.components
        })
        components = {
            name: sum(item.components.get(name, 0.0) for item in evaluations) / divisor
            for name in component_names
        }
        missing = dict(evaluations[-1].missing) if evaluations else {
            term.series_id: "no_intervening_tick" for term in spec.terms
        }
        objective = {
            "components": components,
            "control_cost_penalty": control_penalty,
            "elapsed_ticks": elapsed_ticks,
            "macro_reward": macro_reward,
            "missing": missing,
            "profile": self._objective_profile(),
            "total_reward": macro_reward - control_penalty,
        }
        return objective["total_reward"], objective

    def _evaluate_advanced_result(self, result):
        if self.objective_evaluator is None or result.status != "advanced":
            return None
        tick = result.boundary_tick + 1
        observation = self._objective_observation(tick, elapsed_ticks=1)
        return self.objective_evaluator.evaluate(
            observation,
            adjustment_cost=0.0,
            elapsed_ticks=1,
            release_history=self._release_history(tick),
        )

    def _terminal_context(
        self,
        previous: DecisionContext,
        elapsed_ticks: int,
    ) -> DecisionContext:
        boundary = self.session.boundary_tick
        coordinator = self.session.coordinator
        economies = getattr(self.session.world, "economies", None)
        economy = (
            economies[self.economy_id]
            if economies is not None else self.session.world
        )
        current_policy = {
            lever: getattr(
                economy.external_policy
                if REGISTRY[lever].scope == "external" else economy.policy,
                lever,
            )
            for lever in self.action_levers
        }
        terminal_actions = tuple(
            replace(
                item,
                current_value=current_policy[item.lever],
                allowed=False,
                reason_code="episode_horizon",
                earliest_effective_tick=boundary,
            )
            for item in previous.permitted_actions
        )
        versions = {
            lever: coordinator.policy_versions.get(
                f"{self.economy_id}:{lever}", version
            )
            for lever, version in previous.policy_versions.items()
        }
        pending_policy: dict[str, Any] = {}
        pending_effective_ticks: dict[str, int] = {}
        active_pending = tuple(
            pending for pending in coordinator._active_pending()
            if pending.context.economy_id == self.economy_id
        )
        for pending in active_pending:
            for action in pending.proposal.actions:
                if action.lever not in current_policy:
                    continue
                pending_policy[action.lever] = action.value
                pending_effective_ticks[action.lever] = pending.effective_tick

        last_effective_ticks: dict[str, int | None] = {}
        next_eligibility_ticks: dict[str, int] = {}
        for name in self.action_levers:
            lever = REGISTRY[name]
            last = coordinator.last_effective_tick.get(
                f"{self.economy_id}:{name}"
            )
            next_tick = boundary + lever.implementation_lag
            if last is not None:
                next_tick = max(next_tick, last + lever.min_hold_ticks)
            for pending in active_pending:
                if any(action.lever == name for action in pending.proposal.actions):
                    next_tick = max(
                        next_tick, pending.effective_tick + lever.min_hold_ticks,
                    )
            last_effective_ticks[name] = last
            next_eligibility_ticks[name] = next_tick

        budget_key = (
            self.economy_id, previous.seat, previous.decision_group,
        )
        calendar = coordinator.scheduler.calendar_for(previous.decision_group)
        return replace(
            previous,
            context_id=f"terminal:{self.economy_id}:{self.seat}:{boundary}",
            decision_window_id=f"terminal:{boundary}",
            boundary_tick=boundary,
            expires_at_tick=boundary,
            policy_versions=versions,
            observation=self._released_observation(
                boundary, elapsed_ticks=max(1, elapsed_ticks)
            ),
            permitted_actions=terminal_actions,
            pending_policy=pending_policy,
            current_policy=current_policy,
            pending_effective_ticks=pending_effective_ticks,
            emergency=False,
            emergency_trigger=None,
            emergency_bulletin=None,
            elapsed_ticks=max(1, elapsed_ticks),
            last_effective_ticks=last_effective_ticks,
            next_eligibility_ticks=next_eligibility_ticks,
            admin_remaining=coordinator.admin_remaining.get(budget_key, 0.0),
            admin_reserved=coordinator.admin_reserved.get(budget_key, 0.0),
            admin_capacity=calendar.admin_capacity,
        )

    def _seek_next_context(
        self,
        *,
        on_advanced=None,
    ) -> tuple[DecisionContext | None, list[Any]]:
        trace: list[Any] = []
        while True:
            if self.max_boundary_tick is not None \
                    and self.session.boundary_tick >= self.max_boundary_tick:
                return None, trace
            result = self.session.advance()
            trace.append(result)
            if on_advanced is not None:
                evaluation = self._evaluate_advanced_result(result)
                if evaluation is not None:
                    on_advanced(evaluation)
            if result.status != AWAITING_HUMAN:
                continue
            context = self._select_target_context(result)
            if context is not None:
                return context, trace
            raise RuntimeError("another human-controlled seat is blocking the Gym environment")

    def _select_target_context(self, result) -> DecisionContext | None:
        missing = set(result.missing_context_ids)
        target = sorted(
            (
                context for context in result.contexts
                if context.context_id in missing
                and context.economy_id == self.economy_id
                and context.seat == self.seat
            ),
            key=lambda context: context.context_id,
        )
        other = [
            context_id for context_id in missing
            if context_id not in {context.context_id for context in target}
        ]
        if other:
            return None
        return target[0] if target else None

    def _vector(self, context: DecisionContext) -> np.ndarray:
        values: list[float] = [float(context.boundary_tick), float(context.elapsed_ticks)]
        observation = context.observation
        releases = getattr(observation, "releases", ())
        for release in sorted(releases, key=lambda item: item.series_id):
            value = release.value
            numeric = (
                float(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else 0.0
            )
            release_service = self.session.release_service
            if release_service is not None and numeric != 0.0:
                scale = release_service.spec.field(
                    release.series_id
                ).normalization_scale
                if scale is not None:
                    numeric /= float(scale)
            values.extend((numeric, float(release.missing_reason is not None)))
        values.extend((
            float(max(0, context.expires_at_tick - context.boundary_tick)),
            float(context.emergency),
            float(context.emergency_trigger is not None),
            float(context.admin_remaining),
            float(context.admin_reserved),
        ))
        permitted = {item.lever: item for item in context.permitted_actions}
        pending_policy = context.pending_policy
        for lever in self.action_levers:
            item = permitted.get(lever)
            if lever not in context.current_policy:
                raise RuntimeError(
                    f"DecisionContext is missing current_policy snapshot for {lever}"
                )
            current = context.current_policy[lever]
            encoded = self._encode_policy_value(lever, current, item)
            pending_present = lever in pending_policy
            pending_target = pending_policy.get(lever)
            last_effective = context.last_effective_ticks.get(lever)
            pending_effective = context.pending_effective_ticks.get(lever)
            values.extend((
                encoded,
                float(current is None),
                self._encode_policy_value(lever, pending_target, item)
                if pending_present else 0.0,
                float(pending_present and pending_target is None),
                float(pending_present),
                float(context.policy_versions[lever]),
                float(max(0, context.boundary_tick - last_effective))
                if last_effective is not None else 0.0,
                float(last_effective is None),
                float(max(
                    0,
                    context.next_eligibility_ticks[lever] - context.boundary_tick,
                )),
                float(max(0, pending_effective - context.boundary_tick))
                if pending_effective is not None else 0.0,
            ))
        mask, costs = self._direction_metadata(context)
        for index in range(len(self.action_dimensions)):
            values.extend((
                float(mask[index, 0]),
                float(mask[index, 2]),
                float(costs[index, 0]),
                float(costs[index, 2]),
            ))
        if len(values) != len(self.observation_features):
            raise RuntimeError(
                "Gym observation layout drifted: "
                f"expected {len(self.observation_features)}, got {len(values)}"
            )
        return np.asarray(values, dtype=np.float64)

    def _encode_policy_value(self, lever_name: str, current: Any, item: Any) -> float:
        """Encode effective policy even when its decision group is not open."""
        validation = REGISTRY[lever_name].validation
        if isinstance(current, bool):
            return float(current)
        if isinstance(validation, EconomySet):
            choices = (
                tuple(item.choices) if item is not None else self._economy_targets
            )
            current_set = set(current or ())
            return float(sum(
                1 << index
                for index, target in enumerate(choices)
                if target in current_set
            ))
        if isinstance(current, (int, float)):
            encoded = float(current)
            minimum = item.minimum if item is not None else getattr(validation, "lo", None)
            maximum = item.maximum if item is not None else getattr(validation, "hi", None)
            if minimum is not None and maximum is not None and maximum > minimum:
                encoded = (encoded - minimum) / (maximum - minimum)
            return encoded
        choices = tuple(item.choices) if item is not None else (
            validation.values if isinstance(validation, Choices) else ()
        )
        if isinstance(validation, EconomyId) and not choices:
            choices = self._economy_targets + (None,)
        if choices:
            try:
                return float(list(choices).index(current))
            except ValueError:
                return -1.0
        return 0.0

    def _info(self, context: DecisionContext, *, elapsed_ticks: int) -> dict[str, Any]:
        mask, costs = self._direction_metadata(context)
        info = {
            "context": context.to_dict(),
            "context_json": context.to_json(),
            "elapsed_ticks": elapsed_ticks,
            "action_levers": self.action_levers,
            "action_dimensions": self.action_dimensions,
            "action_mask": mask.copy(),
            "action_costs": costs.copy(),
            "observation_features": self.observation_features,
        }
        profile = self._objective_profile()
        if profile is not None:
            info["objective_profile"] = profile
        return info
