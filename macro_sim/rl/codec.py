"""Stable, session-free contracts for RL observation and action deployment.

The Gym adapter owns simulation advancement, but a deployed ``RLOccupant`` only
receives a :class:`~macro_sim.controllers.protocol.DecisionContext`.  This module
therefore deliberately encodes *only* data contained in that immutable context.
In particular, Coordinator probe results (the Gym adapter's exact action mask and
cost matrix) are live-session data and are not part of this contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from numbers import Integral, Real
from typing import Any, Mapping, Sequence

import numpy as np

from macro_sim.controllers.protocol import (
    CONTROLLER_SCHEMA_VERSION,
    DecisionContext,
    PermittedAction,
    PolicyAction,
    canonical_json,
)
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


CONTEXT_CODEC_SCHEMA_VERSION = 1
ACTION_CODEC_SCHEMA_VERSION = 1
CONTEXT_ENCODING = "decision_context_base_vector_v1"
ACTION_ENCODING = "directional_policy_actions_v1"


def _strict_int(name: str, value: Any, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _finite(name: str, value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be > 0")
    return result


def _contract_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _exact_keys(value: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{where} keys differ; missing={missing}, extra={extra}")


@dataclass(frozen=True)
class ReleaseFeatureSpec:
    """One released series and its frozen training-time normalization."""

    series_id: str
    normalization_scale: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.series_id, str) or not self.series_id:
            raise ValueError("series_id must be a non-empty string")
        object.__setattr__(
            self,
            "normalization_scale",
            _finite("normalization_scale", self.normalization_scale, positive=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalization_scale": self.normalization_scale,
            "series_id": self.series_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReleaseFeatureSpec":
        if not isinstance(value, Mapping):
            raise TypeError("release feature spec must be a mapping")
        _exact_keys(value, {"series_id", "normalization_scale"}, "release spec")
        return cls(
            series_id=value["series_id"],
            normalization_scale=value["normalization_scale"],
        )


@dataclass(frozen=True)
class LeverFeatureSpec:
    """Registry-derived policy encoding frozen into a model contract."""

    name: str
    kind: str
    minimum: float | int | None = None
    maximum: float | int | None = None
    choices: tuple[Any, ...] = ()
    owner_role: str = ""
    decision_group: str = ""
    control_scale: float | None = None
    max_step: float | None = None

    _KINDS = frozenset({
        "bool", "choices", "economy_id", "economy_set", "integer",
        "number", "nullable_number",
    })

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("lever name must be a non-empty string")
        if self.kind not in self._KINDS:
            raise ValueError(f"unknown lever encoding kind {self.kind!r}")
        if self.minimum is not None:
            object.__setattr__(self, "minimum", _finite("minimum", self.minimum))
        if self.maximum is not None:
            object.__setattr__(self, "maximum", _finite("maximum", self.maximum))
        if self.minimum is not None and self.maximum is not None \
                and self.maximum < self.minimum:
            raise ValueError("lever maximum is below minimum")
        object.__setattr__(self, "choices", tuple(self.choices))
        for name in ("owner_role", "decision_group"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"lever {name} must be a non-empty string")
        for name in ("control_scale", "max_step"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite(name, value, positive=True))
        if self.control_scale is not None and self.max_step is not None \
                and self.control_scale > self.max_step:
            raise ValueError("lever control_scale exceeds max_step")

    def to_dict(self) -> dict[str, Any]:
        return {
            "choices": list(self.choices),
            "control_scale": self.control_scale,
            "decision_group": self.decision_group,
            "kind": self.kind,
            "maximum": self.maximum,
            "max_step": self.max_step,
            "minimum": self.minimum,
            "name": self.name,
            "owner_role": self.owner_role,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LeverFeatureSpec":
        if not isinstance(value, Mapping):
            raise TypeError("lever feature spec must be a mapping")
        _exact_keys(
            value, {
                "name", "kind", "minimum", "maximum", "choices",
                "owner_role", "decision_group", "control_scale", "max_step",
            },
            "lever spec",
        )
        choices = value["choices"]
        if not isinstance(choices, list):
            raise TypeError("lever choices must be a list")
        return cls(
            name=value["name"],
            kind=value["kind"],
            minimum=value["minimum"],
            maximum=value["maximum"],
            choices=tuple(choices),
            owner_role=value["owner_role"],
            decision_group=value["decision_group"],
            control_scale=value["control_scale"],
            max_step=value["max_step"],
        )

    @classmethod
    def from_registry(cls, name: str) -> "LeverFeatureSpec":
        try:
            lever = REGISTRY[name]
            validation = lever.validation
        except KeyError as exc:
            raise ValueError(f"unknown policy lever {name!r}") from exc
        common = {
            "owner_role": lever.owner_role,
            "decision_group": lever.decision_group,
            "control_scale": lever.control_scale,
            "max_step": getattr(validation, "max_step", None),
        }
        if isinstance(validation, EconomySet):
            return cls(name, "economy_set", **common)
        if isinstance(validation, EconomyId):
            return cls(name, "economy_id", **common)
        if isinstance(validation, Bool):
            return cls(name, "bool", **common)
        if isinstance(validation, Choices):
            return cls(
                name, "choices", choices=tuple(validation.values), **common,
            )
        # Order matters: IntRange and NullableRange inherit Range.
        if isinstance(validation, IntRange):
            return cls(
                name, "integer", validation.lo, validation.hi, **common,
            )
        if isinstance(validation, NullableRange):
            return cls(
                name, "nullable_number", validation.lo, validation.hi, **common,
            )
        if isinstance(validation, Range):
            return cls(name, "number", validation.lo, validation.hi, **common)
        raise TypeError(
            f"policy lever {name!r} uses unsupported validation "
            f"{type(validation).__name__}"
        )


@dataclass(frozen=True)
class ContextCodec:
    """Versioned, hashable ``DecisionContext -> float64 vector`` contract.

    ``release_specs`` and registry-derived ``lever_specs`` are embedded rather
    than looked up while encoding.  A loaded artifact separately verifies that
    the runtime registry still has the same shape, preventing silent semantic
    drift after a policy schema change.
    """

    economy_id: int
    seat: str
    release_specs: tuple[ReleaseFeatureSpec, ...]
    lever_specs: tuple[LeverFeatureSpec, ...]
    economy_targets: tuple[int, ...] = ()
    controller_schema_version: int = CONTROLLER_SCHEMA_VERSION
    observation_schema_version: int = 1
    schema_version: int = CONTEXT_CODEC_SCHEMA_VERSION
    encoding: str = CONTEXT_ENCODING

    def __post_init__(self) -> None:
        object.__setattr__(self, "economy_id", _strict_int("economy_id", self.economy_id))
        if not isinstance(self.seat, str) or not self.seat:
            raise ValueError("seat must be a non-empty string")
        object.__setattr__(self, "schema_version", _strict_int(
            "schema_version", self.schema_version, minimum=1,
        ))
        if self.schema_version != CONTEXT_CODEC_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported context codec schema_version {self.schema_version}"
            )
        if self.encoding != CONTEXT_ENCODING:
            raise ValueError(f"unsupported context encoding {self.encoding!r}")
        object.__setattr__(self, "controller_schema_version", _strict_int(
            "controller_schema_version", self.controller_schema_version, minimum=1,
        ))
        if self.controller_schema_version != CONTROLLER_SCHEMA_VERSION:
            raise ValueError(
                "context codec targets an unsupported DecisionContext schema_version"
            )
        object.__setattr__(self, "observation_schema_version", _strict_int(
            "observation_schema_version", self.observation_schema_version, minimum=1,
        ))

        releases = tuple(self.release_specs)
        if not all(isinstance(item, ReleaseFeatureSpec) for item in releases):
            raise TypeError("release_specs must contain ReleaseFeatureSpec values")
        if tuple(sorted(releases, key=lambda item: item.series_id)) != releases:
            raise ValueError("release_specs must be sorted by series_id")
        if len({item.series_id for item in releases}) != len(releases):
            raise ValueError("release_specs contain duplicate series_id values")
        object.__setattr__(self, "release_specs", releases)

        levers = tuple(self.lever_specs)
        if not levers:
            raise ValueError("lever_specs must not be empty")
        if not all(isinstance(item, LeverFeatureSpec) for item in levers):
            raise TypeError("lever_specs must contain LeverFeatureSpec values")
        if tuple(sorted(levers, key=lambda item: item.name)) != levers:
            raise ValueError("lever_specs must be sorted by lever name")
        if len({item.name for item in levers}) != len(levers):
            raise ValueError("lever_specs contain duplicate lever names")
        object.__setattr__(self, "lever_specs", levers)

        targets = tuple(
            _strict_int("economy target", target) for target in self.economy_targets
        )
        if tuple(sorted(set(targets))) != targets:
            raise ValueError("economy_targets must be unique and sorted")
        if self.economy_id in targets:
            raise ValueError("economy_targets cannot contain the controlled economy")
        object.__setattr__(self, "economy_targets", targets)

    @property
    def action_levers(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.lever_specs)

    @property
    def feature_names(self) -> tuple[str, ...]:
        names = ["boundary_tick", "elapsed_ticks"]
        for item in self.release_specs:
            names.extend((
                f"release:{item.series_id}:value",
                f"release:{item.series_id}:missing",
            ))
        names.extend((
            "decision:ticks_to_expiry",
            "decision:emergency",
            "decision:emergency_trigger_present",
            "admin:remaining",
            "admin:reserved",
        ))
        for item in self.lever_specs:
            lever = item.name
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
        return tuple(names)

    @property
    def observation_dim(self) -> int:
        return len(self.feature_names)

    @property
    def contract_hash(self) -> str:
        return _contract_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "controller_schema_version": self.controller_schema_version,
            "economy_id": self.economy_id,
            "economy_targets": list(self.economy_targets),
            "encoding": self.encoding,
            "feature_names": list(self.feature_names),
            "lever_specs": [item.to_dict() for item in self.lever_specs],
            "observation_schema_version": self.observation_schema_version,
            "release_specs": [item.to_dict() for item in self.release_specs],
            "schema_version": self.schema_version,
            "seat": self.seat,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ContextCodec":
        if not isinstance(value, Mapping):
            raise TypeError("context codec must be a mapping")
        expected = {
            "controller_schema_version", "economy_id", "economy_targets",
            "encoding", "feature_names", "lever_specs",
            "observation_schema_version", "release_specs", "schema_version", "seat",
        }
        _exact_keys(value, expected, "context codec")
        if not isinstance(value["release_specs"], list):
            raise TypeError("release_specs must be a list")
        if not isinstance(value["lever_specs"], list):
            raise TypeError("lever_specs must be a list")
        if not isinstance(value["economy_targets"], list):
            raise TypeError("economy_targets must be a list")
        if not isinstance(value["feature_names"], list) or not all(
            isinstance(item, str) for item in value["feature_names"]
        ):
            raise TypeError("feature_names must be a list of strings")
        result = cls(
            economy_id=value["economy_id"],
            seat=value["seat"],
            release_specs=tuple(
                ReleaseFeatureSpec.from_dict(item) for item in value["release_specs"]
            ),
            lever_specs=tuple(
                LeverFeatureSpec.from_dict(item) for item in value["lever_specs"]
            ),
            economy_targets=tuple(value["economy_targets"]),
            controller_schema_version=value["controller_schema_version"],
            observation_schema_version=value["observation_schema_version"],
            schema_version=value["schema_version"],
            encoding=value["encoding"],
        )
        if tuple(value["feature_names"]) != result.feature_names:
            raise ValueError("context codec feature_names do not match its schema")
        return result

    @classmethod
    def from_parts(
        cls,
        *,
        economy_id: int,
        seat: str,
        action_levers: Sequence[str],
        economy_targets: Sequence[int] = (),
        normalization_scales: Mapping[str, float] | None = None,
        observation_series: Sequence[str] = (),
        observation_schema_version: int = 1,
    ) -> "ContextCodec":
        scales = {} if normalization_scales is None else dict(normalization_scales)
        unknown_scales = set(scales) - set(observation_series)
        if unknown_scales:
            raise ValueError(
                f"normalization scales reference unknown series: {sorted(unknown_scales)}"
            )
        release_specs = tuple(
            ReleaseFeatureSpec(name, scales.get(name, 1.0))
            for name in sorted(observation_series)
        )
        lever_names = tuple(sorted(action_levers))
        if len(set(lever_names)) != len(lever_names):
            raise ValueError("action_levers contain duplicates")
        lever_specs = tuple(LeverFeatureSpec.from_registry(name) for name in lever_names)
        for name in lever_names:
            owner = REGISTRY[name].owner_role
            if owner and owner != seat:
                raise ValueError(
                    f"policy lever {name!r} belongs to {owner!r}, not {seat!r}"
                )
        return cls(
            economy_id=economy_id,
            seat=seat,
            release_specs=release_specs,
            lever_specs=lever_specs,
            economy_targets=tuple(sorted(economy_targets)),
            observation_schema_version=observation_schema_version,
        )

    @classmethod
    def from_env(cls, env: Any) -> "ContextCodec":
        """Freeze the deployable subset of an initialized ``ControllerEnv``."""
        required = (
            "economy_id", "seat", "action_levers", "_economy_targets", "session",
        )
        if any(not hasattr(env, name) for name in required):
            raise TypeError("env does not expose the ControllerEnv contract")
        service = getattr(env.session, "release_service", None)
        fields = () if service is None else tuple(service.spec.fields)
        scales = {
            item.series_id: (
                1.0 if item.normalization_scale is None
                else item.normalization_scale
            )
            for item in fields
        }
        observation_schema_version = (
            1 if service is None else service.spec.schema_version
        )
        return cls.from_parts(
            economy_id=env.economy_id,
            seat=env.seat,
            action_levers=env.action_levers,
            economy_targets=env._economy_targets,
            observation_series=tuple(scales),
            normalization_scales=scales,
            observation_schema_version=observation_schema_version,
        )

    def verify_runtime_registry(self) -> None:
        """Fail closed if policy semantics changed since training/export."""
        for frozen in self.lever_specs:
            current = LeverFeatureSpec.from_registry(frozen.name)
            if current != frozen:
                raise ValueError(
                    f"runtime registry schema drift for policy lever {frozen.name!r}"
                )
            owner = REGISTRY[frozen.name].owner_role
            if owner and owner != self.seat:
                raise ValueError(
                    f"runtime owner drift for policy lever {frozen.name!r}"
                )

    def validate_context(self, context: DecisionContext) -> None:
        if not isinstance(context, DecisionContext):
            raise TypeError("policy input must be a DecisionContext")
        if context.schema_version != self.controller_schema_version:
            raise ValueError(
                "DecisionContext schema_version does not match model contract"
            )
        if context.observation_schema_version != self.observation_schema_version:
            raise ValueError(
                "DecisionContext observation schema does not match model contract"
            )
        if context.economy_id != self.economy_id:
            raise ValueError("DecisionContext economy_id does not match model contract")
        if context.seat != self.seat:
            raise ValueError("DecisionContext seat does not match model contract")
        boundary_tick = _strict_int("DecisionContext boundary_tick", context.boundary_tick)
        expires_at = _strict_int("DecisionContext expires_at_tick", context.expires_at_tick)
        _strict_int("DecisionContext elapsed_ticks", context.elapsed_ticks)
        if expires_at < boundary_tick:
            raise ValueError("DecisionContext expires before its boundary")
        expected = set(self.action_levers)
        missing_policy = expected - set(context.current_policy)
        missing_versions = expected - set(context.policy_versions)
        if missing_policy:
            raise ValueError(
                f"DecisionContext is missing current policy: {sorted(missing_policy)}"
            )
        if missing_versions:
            raise ValueError(
                f"DecisionContext is missing policy versions: {sorted(missing_versions)}"
            )
        permitted = {item.lever: item for item in context.permitted_actions}
        universe = set(self.economy_targets)
        for spec in self.lever_specs:
            if spec.kind not in {"economy_id", "economy_set"}:
                continue
            item = permitted.get(spec.name)
            if item is not None:
                choice_universe = {
                    value for value in item.choices if value is not None
                }
                if choice_universe != universe:
                    raise ValueError(
                        f"DecisionContext economy universe drift for {spec.name!r}"
                    )

            values = [context.current_policy[spec.name]]
            if spec.name in context.pending_policy:
                values.append(context.pending_policy[spec.name])
            for value in values:
                if spec.kind == "economy_id":
                    referenced = set() if value is None else {value}
                else:
                    try:
                        referenced = set(value or ())
                    except TypeError as exc:
                        raise ValueError(
                            f"DecisionContext {spec.name!r} target set is invalid"
                        ) from exc
                if any(
                    isinstance(target, bool) or not isinstance(target, Integral)
                    for target in referenced
                ) or not referenced.issubset(universe):
                    raise ValueError(
                        f"DecisionContext {spec.name!r} references an economy "
                        "outside the model contract"
                    )
        for lever in expected:
            version = context.policy_versions[lever]
            _strict_int(f"policy version for {lever!r}", version)
            current = context.current_policy[lever]
            validation = REGISTRY[lever].validation
            engine_current = (
                frozenset(current or ())
                if isinstance(validation, EconomySet) else current
            )
            error = validation.check(engine_current, engine_current)
            if error is not None:
                raise ValueError(
                    f"DecisionContext current value for {lever!r} is invalid: {error}"
                )
            if lever in context.pending_policy:
                pending = context.pending_policy[lever]
                engine_pending = (
                    frozenset(pending or ())
                    if isinstance(validation, EconomySet) else pending
                )
                error = validation.check(engine_current, engine_pending)
                if error is not None:
                    raise ValueError(
                        f"DecisionContext pending value for {lever!r} is invalid: {error}"
                    )
            last = context.last_effective_ticks.get(lever)
            if last is not None:
                _strict_int(f"last effective tick for {lever!r}", last)
            if lever in context.next_eligibility_ticks:
                _strict_int(
                    f"next eligibility tick for {lever!r}",
                    context.next_eligibility_ticks[lever],
                )
            if lever in context.pending_effective_ticks:
                _strict_int(
                    f"pending effective tick for {lever!r}",
                    context.pending_effective_ticks[lever],
                )
        permitted = {item.lever: item for item in context.permitted_actions}
        if len(permitted) != len(context.permitted_actions):
            raise ValueError("DecisionContext contains duplicate permitted actions")
        value_kinds = {
            "bool": "bool",
            "choices": "choice",
            "economy_id": "economy_id",
            "economy_set": "economy_set",
            "integer": "integer",
            "number": "number",
            "nullable_number": "number",
        }
        for spec in self.lever_specs:
            item = permitted.get(spec.name)
            if item is None:
                continue
            current = context.current_policy[spec.name]
            if spec.kind == "economy_set":
                same_current = set(item.current_value or ()) == set(current or ())
            else:
                same_current = item.current_value == current
            if not same_current:
                raise ValueError(
                    f"DecisionContext permitted/current mismatch for {spec.name!r}"
                )
            if item.value_kind != value_kinds[spec.kind]:
                raise ValueError(
                    f"DecisionContext value kind drift for policy lever {spec.name!r}"
                )
            if item.control_scale != spec.control_scale \
                    or item.max_step != spec.max_step:
                raise ValueError(
                    f"DecisionContext action scale drift for policy lever {spec.name!r}"
                )
            if spec.minimum is not None and item.minimum != spec.minimum:
                raise ValueError(
                    f"DecisionContext minimum drift for policy lever {spec.name!r}"
                )
            if spec.maximum is not None and item.maximum != spec.maximum:
                raise ValueError(
                    f"DecisionContext maximum drift for policy lever {spec.name!r}"
                )
            if spec.kind == "choices" and tuple(item.choices) != spec.choices:
                raise ValueError(
                    f"DecisionContext choices drift for policy lever {spec.name!r}"
                )

    def encode(self, context: DecisionContext) -> np.ndarray:
        self.validate_context(context)
        values: list[float] = [
            float(context.boundary_tick), float(context.elapsed_ticks),
        ]
        observation = context.observation
        releases = getattr(observation, "releases", None)
        if releases is None:
            raise TypeError("DecisionContext observation has no typed releases")
        by_series = {item.series_id: item for item in releases}
        expected_series = {item.series_id for item in self.release_specs}
        if set(by_series) != expected_series:
            raise ValueError(
                "DecisionContext release series differ from model contract; "
                f"missing={sorted(expected_series - set(by_series))}, "
                f"extra={sorted(set(by_series) - expected_series)}"
            )
        for spec in self.release_specs:
            release = by_series[spec.series_id]
            raw = release.value
            numeric = (
                float(raw)
                if isinstance(raw, Real) and not isinstance(raw, bool)
                else 0.0
            )
            if numeric != 0.0:
                numeric /= spec.normalization_scale
            values.extend((numeric, float(release.missing_reason is not None)))

        values.extend((
            float(max(0, context.expires_at_tick - context.boundary_tick)),
            float(context.emergency),
            float(context.emergency_trigger is not None),
            float(context.admin_remaining),
            float(context.admin_reserved),
        ))
        permitted = {item.lever: item for item in context.permitted_actions}
        for spec in self.lever_specs:
            lever = spec.name
            item = permitted.get(lever)
            current = context.current_policy[lever]
            pending_present = lever in context.pending_policy
            pending_target = context.pending_policy.get(lever)
            last_effective = context.last_effective_ticks.get(lever)
            pending_effective = context.pending_effective_ticks.get(lever)
            next_eligibility = context.next_eligibility_ticks.get(
                lever, context.boundary_tick,
            )
            values.extend((
                self._encode_policy_value(spec, current, item),
                float(current is None),
                self._encode_policy_value(spec, pending_target, item)
                if pending_present else 0.0,
                float(pending_present and pending_target is None),
                float(pending_present),
                float(context.policy_versions[lever]),
                float(max(0, context.boundary_tick - last_effective))
                if last_effective is not None else 0.0,
                float(last_effective is None),
                float(max(0, next_eligibility - context.boundary_tick)),
                float(max(0, pending_effective - context.boundary_tick))
                if pending_effective is not None else 0.0,
            ))
        result = np.asarray(values, dtype=np.float64)
        if result.shape != (self.observation_dim,):
            raise RuntimeError(
                f"context encoding shape drift: expected {(self.observation_dim,)}, "
                f"got {result.shape}"
            )
        if not np.all(np.isfinite(result)):
            raise ValueError("DecisionContext encodes to NaN or Infinity")
        result.setflags(write=False)
        return result

    def _encode_policy_value(
        self,
        spec: LeverFeatureSpec,
        current: Any,
        item: PermittedAction | None,
    ) -> float:
        if isinstance(current, bool):
            return float(current)
        if spec.kind == "economy_set":
            # The semantic position of an economy must not change when the
            # current decision window filters its permitted choices.
            choices = self.economy_targets
            current_set = set(current or ())
            encoded = sum(
                1 << index
                for index, target in enumerate(choices)
                if target in current_set
            )
            try:
                return float(encoded)
            except OverflowError as exc:
                raise ValueError(
                    f"policy lever {spec.name!r} economy-set encoding overflowed"
                ) from exc
        if isinstance(current, Real) and not isinstance(current, bool):
            encoded = float(current)
            minimum = spec.minimum
            maximum = spec.maximum
            if minimum is not None and maximum is not None and maximum > minimum:
                encoded = (encoded - float(minimum)) / (
                    float(maximum) - float(minimum)
                )
            return encoded
        choices = spec.choices
        if spec.kind == "economy_id":
            choices = self.economy_targets + (None,)
        if choices:
            try:
                return float(list(choices).index(current))
            except ValueError:
                return -1.0
        return 0.0


@dataclass(frozen=True)
class DirectionalActionCodec:
    """Pure-context directional action adapter used by deployed policies.

    The returned mask is intentionally conservative and advisory.  It can test
    local bounds, availability and the two known joint transition templates,
    but not global budget/bilateral state.  Coordinator submission remains the
    sole authority and safely rejects any cross-action constraint violation.
    """

    context_contract_hash: str
    action_dimensions: tuple[tuple[str, int | None], ...]
    schema_version: int = ACTION_CODEC_SCHEMA_VERSION
    encoding: str = ACTION_ENCODING

    def __post_init__(self) -> None:
        if not isinstance(self.context_contract_hash, str) or len(
            self.context_contract_hash
        ) != 64:
            raise ValueError("context_contract_hash must be a SHA-256 hex digest")
        try:
            int(self.context_contract_hash, 16)
        except ValueError as exc:
            raise ValueError("context_contract_hash must be a SHA-256 hex digest") from exc
        object.__setattr__(self, "schema_version", _strict_int(
            "schema_version", self.schema_version, minimum=1,
        ))
        if self.schema_version != ACTION_CODEC_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported action codec schema_version {self.schema_version}"
            )
        if self.encoding != ACTION_ENCODING:
            raise ValueError(f"unsupported action encoding {self.encoding!r}")
        dimensions: list[tuple[str, int | None]] = []
        for value in self.action_dimensions:
            if not isinstance(value, tuple) or len(value) != 2:
                raise TypeError("each action dimension must be a (lever, target) tuple")
            lever, target = value
            if not isinstance(lever, str) or not lever:
                raise ValueError("action dimension lever must be a non-empty string")
            if target is not None:
                target = _strict_int("action target", target)
            dimensions.append((lever, target))
        if len(set(dimensions)) != len(dimensions):
            raise ValueError("action_dimensions contain duplicates")
        object.__setattr__(self, "action_dimensions", tuple(dimensions))

    @property
    def action_dim(self) -> int:
        return len(self.action_dimensions)

    @property
    def contract_hash(self) -> str:
        return _contract_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_dimensions": [list(item) for item in self.action_dimensions],
            "context_contract_hash": self.context_contract_hash,
            "encoding": self.encoding,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_context_codec(cls, codec: ContextCodec) -> "DirectionalActionCodec":
        dimensions: list[tuple[str, int | None]] = []
        for spec in codec.lever_specs:
            if spec.kind == "economy_set":
                dimensions.extend(
                    (spec.name, target) for target in codec.economy_targets
                )
            else:
                dimensions.append((spec.name, None))
        return cls(codec.contract_hash, tuple(dimensions))

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        context_codec: ContextCodec,
    ) -> "DirectionalActionCodec":
        if not isinstance(value, Mapping):
            raise TypeError("action codec must be a mapping")
        _exact_keys(
            value,
            {"action_dimensions", "context_contract_hash", "encoding", "schema_version"},
            "action codec",
        )
        raw_dimensions = value["action_dimensions"]
        if not isinstance(raw_dimensions, list) or any(
            not isinstance(item, list) or len(item) != 2 for item in raw_dimensions
        ):
            raise TypeError("action_dimensions must be a list of [lever, target]")
        result = cls(
            context_contract_hash=value["context_contract_hash"],
            action_dimensions=tuple((item[0], item[1]) for item in raw_dimensions),
            schema_version=value["schema_version"],
            encoding=value["encoding"],
        )
        expected = cls.from_context_codec(context_codec)
        if result != expected:
            raise ValueError("action codec does not match its context codec")
        return result

    def verify_context_codec(self, codec: ContextCodec) -> None:
        if codec.contract_hash != self.context_contract_hash:
            raise ValueError("action codec references a different context contract")
        expected = type(self).from_context_codec(codec)
        if expected.action_dimensions != self.action_dimensions:
            raise ValueError("action dimensions do not match context policy schema")

    def action_mask(
        self, context: DecisionContext, *, context_codec: ContextCodec,
    ) -> np.ndarray:
        self.verify_context_codec(context_codec)
        context_codec.validate_context(context)
        mask = np.zeros((self.action_dim, 3), dtype=np.bool_)
        mask[:, 1] = True
        for index in range(self.action_dim):
            for code in (0, 2):
                codes = np.ones(self.action_dim, dtype=np.int8)
                codes[index] = code
                _actions, selected = self._decode_codes(codes, context)
                mask[index, code] = index in selected
        mask.setflags(write=False)
        return mask

    def decode(
        self,
        codes: Sequence[int] | np.ndarray,
        context: DecisionContext,
        *,
        context_codec: ContextCodec,
        strict: bool = True,
    ) -> tuple[PolicyAction, ...]:
        self.verify_context_codec(context_codec)
        context_codec.validate_context(context)
        checked = self._validate_codes(codes)
        actions, selected = self._decode_codes(checked, context)
        requested = {index for index, code in enumerate(checked) if code != 1}
        if strict and requested != selected:
            rejected = sorted(requested - selected)
            raise ValueError(
                f"directional action requests unavailable dimensions {rejected}"
            )
        return actions

    def _validate_codes(self, codes: Sequence[int] | np.ndarray) -> np.ndarray:
        if isinstance(codes, np.ndarray) and codes.ndim != 1:
            raise ValueError("directional action must be a flat vector")
        try:
            raw = tuple(codes)
        except TypeError as exc:
            raise TypeError("directional action must be a sequence") from exc
        if len(raw) != self.action_dim:
            raise ValueError(
                f"directional action shape must be {(self.action_dim,)}, got {(len(raw),)}"
            )
        checked: list[int] = []
        for value in raw:
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
                raise ValueError("directional action entries must be integer codes")
            code = int(value)
            if code not in (0, 1, 2):
                raise ValueError("directional action codes are 0=down, 1=hold, 2=up")
            checked.append(code)
        return np.asarray(checked, dtype=np.int8)

    def _decode_codes(
        self, codes: np.ndarray, context: DecisionContext,
    ) -> tuple[tuple[PolicyAction, ...], set[int]]:
        permitted = {item.lever: item for item in context.permitted_actions}
        requests: list[tuple[int, str, int | None, int, Any]] = []
        for index, ((lever, target), raw_code) in enumerate(zip(
            self.action_dimensions, codes, strict=True,
        )):
            code = int(raw_code)
            if code == 1:
                continue
            item = permitted.get(lever)
            if item is None or not item.allowed:
                continue
            validation = REGISTRY[lever].validation
            if isinstance(validation, EconomySet):
                if target not in item.choices:
                    continue
                current = set(item.current_value or ())
                desired_present = code == 2
                if (target in current) == desired_present:
                    continue
                value = desired_present
            else:
                value = self._directional_value(item, code)
                if value == item.current_value:
                    continue
            requests.append((index, lever, target, code, value))

        desired: dict[str, Any] = {}
        selected: set[int] = set()
        set_targets: dict[str, set[int]] = {}
        for index, lever, target, code, value in requests:
            item = permitted[lever]
            if isinstance(REGISTRY[lever].validation, EconomySet):
                current = set_targets.setdefault(lever, set(item.current_value or ()))
                if code == 0:
                    current.discard(target)
                else:
                    current.add(target)  # type: ignore[arg-type]
                desired[lever] = sorted(current)
            else:
                desired[lever] = value
            selected.add(index)

        def stage(lever: str, value: Any) -> bool:
            item = permitted.get(lever)
            if item is None or not item.allowed:
                return False
            desired[lever] = value
            return True

        regime_item = permitted.get("monetary_regime")
        rate_item = permitted.get("manual_policy_rate")
        current_regime = None if regime_item is None else regime_item.current_value
        current_rate = None if rate_item is None else rate_item.current_value
        if "monetary_regime" in desired:
            if desired["monetary_regime"] == "manual":
                if desired.get("manual_policy_rate", current_rate) is None:
                    if rate_item is None or not stage(
                        "manual_policy_rate", self._default_numeric(rate_item),
                    ):
                        return (), set()
            elif current_regime == "manual" or "manual_policy_rate" in desired:
                if not stage("manual_policy_rate", None):
                    return (), set()
        elif "manual_policy_rate" in desired:
            if desired["manual_policy_rate"] is None and current_regime == "manual":
                fallback = self._choice_or(regime_item, "taylor", "exogenous")
                if fallback is None or not stage("monetary_regime", fallback):
                    return (), set()
            elif desired["manual_policy_rate"] is not None \
                    and current_regime != "manual":
                if not stage("monetary_regime", "manual"):
                    return (), set()

        fx_item = permitted.get("fx_regime")
        anchor_item = permitted.get("peg_anchor")
        current_fx = None if fx_item is None else fx_item.current_value
        current_anchor = None if anchor_item is None else anchor_item.current_value
        if "fx_regime" in desired:
            if desired["fx_regime"] == "peg":
                if desired.get("peg_anchor", current_anchor) is None:
                    anchor = self._first_economy(anchor_item)
                    if anchor is None or not stage("peg_anchor", anchor):
                        return (), set()
            elif current_fx == "peg" or "peg_anchor" in desired:
                if not stage("peg_anchor", None):
                    return (), set()
        elif "peg_anchor" in desired:
            if desired["peg_anchor"] is None and current_fx == "peg":
                if not stage("fx_regime", "float"):
                    return (), set()
            elif desired["peg_anchor"] is not None and current_fx != "peg":
                if not stage("fx_regime", "peg"):
                    return (), set()

        # Joint templates can intentionally override a contradictory companion
        # request (for example "leave manual" together with "raise manual
        # rate").  Preserve the coherent template, but do not claim that the
        # overridden direction was selected; strict callers then see the conflict.
        for index, lever, target, code, value in requests:
            resolved = desired.get(lever, permitted[lever].current_value)
            if isinstance(REGISTRY[lever].validation, EconomySet):
                reflected = (target in set(resolved or ())) == (code == 2)
            else:
                reflected = resolved == value
            if not reflected:
                selected.discard(index)

        actions: list[PolicyAction] = []
        for lever, value in sorted(desired.items()):
            item = permitted.get(lever)
            if item is None or not item.allowed:
                return (), set()
            current = item.current_value
            if isinstance(REGISTRY[lever].validation, EconomySet):
                if set(value) == set(current or ()):
                    continue
            elif value == current:
                continue
            action = PolicyAction(lever, value)
            validation = REGISTRY[lever].validation
            error = validation.check(current, action.engine_value())
            if error is not None:
                return (), set()
            actions.append(action)
        if not actions:
            return (), set()
        return tuple(actions), selected

    @staticmethod
    def _directional_value(item: PermittedAction, code: int) -> Any:
        if item.value_kind == "bool":
            return code == 2
        if item.choices:
            choices = list(item.choices)
            try:
                index = choices.index(item.current_value)
            except ValueError:
                index = 0
            delta = -1 if code == 0 else 1
            return choices[max(0, min(len(choices) - 1, index + delta))]
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
            value = base + (-float(step) if code == 0 else float(step))
            if item.nullable and code == 0 and item.minimum is not None \
                    and value < float(item.minimum):
                return None
            if item.minimum is not None:
                value = max(float(item.minimum), value)
            if item.maximum is not None:
                value = min(float(item.maximum), value)
            return int(round(value)) if item.value_kind == "integer" else value
        return item.current_value

    @staticmethod
    def _default_numeric(item: PermittedAction) -> float | int:
        value = float(item.minimum) if item.minimum is not None else 0.0
        if item.maximum is not None:
            value = min(value, float(item.maximum))
        return int(round(value)) if item.value_kind == "integer" else value

    @staticmethod
    def _choice_or(
        item: PermittedAction | None, *preferred: str,
    ) -> str | None:
        if item is None:
            return None
        for value in preferred:
            if value in item.choices:
                return value
        return next((value for value in item.choices if isinstance(value, str)), None)

    @staticmethod
    def _first_economy(item: PermittedAction | None) -> int | None:
        if item is None:
            return None
        return next((
            value for value in item.choices
            if isinstance(value, int) and not isinstance(value, bool)
        ), None)
