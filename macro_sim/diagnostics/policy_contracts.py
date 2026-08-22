"""P0 contract generator for the Policy causality and crisis audit.

The generator joins the executable Policy Registry with the reviewed economic
catalog in :mod:`macro_sim.diagnostics.policy_catalog`.  Its output is a
complete, canonically hashed 102-lever ledger.  It does not run the simulator;
dynamic route and effect evidence starts at P1.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping

from macro_sim.core.external_policy import ExternalPolicy
from macro_sim.core.policy import POLICY_SCHEMA_VERSION, Policy
from macro_sim.core.policy_registry import (
    Bool,
    Choices,
    EconomyId,
    EconomySet,
    IntRange,
    Lever,
    NullableRange,
    Range,
    REGISTRY,
    STATE_TRANSITION,
)
from macro_sim.desktop.new_game import NewGameSpec
from macro_sim.diagnostics.policy_catalog import (
    ACTIVATION_FIXTURES,
    CRISIS_ROLES,
    FAILURE_TAXONOMY,
    GROUP_SPECS,
    LEVER_ACTIVATION_OVERRIDES,
    LEVER_HORIZON_OVERRIDES,
    LEVER_PROXIMAL_METRICS,
    METRIC_MATERIALITY,
    SCENARIOS,
)


P0_SCHEMA_VERSION = 1
REFERENCE_BASELINE_SEED = 7
EXPECTED_REGISTRY_COUNT = 102
EXPECTED_GROUP_COUNT = 12


@dataclass(frozen=True, slots=True)
class TreatmentBatch:
    label: str
    actions: tuple[tuple[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "actions": [
                {"lever": name, "value": _json_value(value)}
                for name, value in self.actions
            ],
        }


@dataclass(frozen=True, slots=True)
class PolicyCausalContract:
    lever: str
    policy_schema_version: int
    owner_role: str
    decision_group: str
    scope: str
    validation: Mapping[str, Any]
    reference_baseline: Any
    treatment_batches: tuple[TreatmentBatch, ...]
    capabilities: tuple[str, ...]
    enabled_if: tuple[str, ...]
    shadowed_by: tuple[str, ...]
    semantics: str
    handler_id: str | None
    first_native_read_point: str
    activation_fixture: str
    mechanism_proximal_metrics: tuple[str, ...]
    expected_directions: Mapping[str, str]
    tradeoff_metrics: tuple[str, ...]
    ordinary_scenarios: tuple[str, ...]
    structural_scenarios: tuple[str, ...]
    crisis_roles: Mapping[str, str]
    causal_chain: tuple[str, ...]
    operating_horizon_days: int
    materiality_metrics: tuple[str, ...]
    state_notes: str
    status: str = "p0_ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "lever": self.lever,
            "policy_schema_version": self.policy_schema_version,
            "owner_role": self.owner_role,
            "decision_group": self.decision_group,
            "scope": self.scope,
            "validation": dict(self.validation),
            "reference_baseline": _json_value(self.reference_baseline),
            "treatment_batches": [item.to_dict() for item in self.treatment_batches],
            "capabilities": list(self.capabilities),
            "enabled_if": list(self.enabled_if),
            "shadowed_by": list(self.shadowed_by),
            "semantics": self.semantics,
            "handler_id": self.handler_id,
            "first_native_read_point": self.first_native_read_point,
            "activation_fixture": self.activation_fixture,
            "mechanism_proximal_metrics": list(self.mechanism_proximal_metrics),
            "expected_directions": dict(self.expected_directions),
            "tradeoff_metrics": list(self.tradeoff_metrics),
            "ordinary_scenarios": list(self.ordinary_scenarios),
            "structural_scenarios": list(self.structural_scenarios),
            "crisis_roles": dict(self.crisis_roles),
            "causal_chain": list(self.causal_chain),
            "operating_horizon_days": self.operating_horizon_days,
            "materiality_metrics": list(self.materiality_metrics),
            "state_notes": self.state_notes,
            "status": self.status,
        }


def _json_value(value: Any) -> Any:
    if isinstance(value, frozenset):
        return sorted(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validation_dict(lever: Lever) -> dict[str, Any]:
    validation = lever.validation
    if isinstance(validation, IntRange):
        return {
            "kind": "int_range",
            "minimum": int(validation.lo),
            "maximum": int(validation.hi),
            "controller_max_step": validation.max_step,
        }
    if isinstance(validation, NullableRange):
        return {
            "kind": "nullable_range",
            "minimum": validation.lo,
            "maximum": validation.hi,
            "controller_max_step": validation.max_step,
        }
    if isinstance(validation, Range):
        return {
            "kind": "range",
            "minimum": validation.lo,
            "maximum": validation.hi,
            "controller_max_step": validation.max_step,
        }
    if isinstance(validation, Bool):
        return {"kind": "bool", "choices": [False, True]}
    if isinstance(validation, Choices):
        return {"kind": "enum", "choices": list(validation.values)}
    if isinstance(validation, EconomyId):
        return {"kind": "nullable_economy_id", "minimum": 0}
    if isinstance(validation, EconomySet):
        return {"kind": "economy_id_set", "minimum": 0, "exclude_self": True}
    raise TypeError(
        f"{lever.name}: unsupported validation type {type(validation).__name__}"
    )


def _reference_states() -> tuple[Policy, ExternalPolicy]:
    """Return the current product baseline for treatment planning.

    The stored value is a reference dose anchor, not a claim that every country
    profile starts identically.  An experiment manifest records its actual
    branch baseline separately.
    """

    config = NewGameSpec.default(seed=REFERENCE_BASELINE_SEED).configs()[0]
    return Policy.from_config(config), ExternalPolicy()


def _reference_value(
    lever: Lever,
    policy: Policy,
    external_policy: ExternalPolicy,
) -> Any:
    holder = external_policy if lever.scope == "external" else policy
    return getattr(holder, lever.name)


def _deduplicate(values: Iterable[Any]) -> tuple[Any, ...]:
    output: list[Any] = []
    fingerprints: set[str] = set()
    for value in values:
        fingerprint = canonical_json(value)
        if fingerprint in fingerprints:
            continue
        fingerprints.add(fingerprint)
        output.append(value)
    return tuple(output)


def _numeric_treatments(lever: Lever, baseline: Any) -> tuple[int | float, ...]:
    validation = lever.validation
    assert isinstance(validation, Range)
    integer = isinstance(validation, IntRange)
    scale = lever.control_scale
    if scale is None:
        scale = max((float(validation.hi) - float(validation.lo)) * 0.05, 1.0e-9)
    large = validation.max_step if validation.max_step is not None else scale * 4.0
    deltas = _deduplicate((float(scale), float(large)))
    origin = None if baseline is None else float(baseline)
    candidates: list[int | float] = []

    def add(number: float) -> None:
        number = min(float(validation.hi), max(float(validation.lo), number))
        if integer:
            candidate: int | float = int(round(number))
        else:
            candidate = float(number)
        if baseline is not None and candidate == baseline:
            return
        if validation.check(baseline, candidate) is None:
            candidates.append(candidate)

    if origin is None:
        for delta in deltas:
            if float(validation.lo) <= 0.0 <= float(validation.hi):
                add(delta)
            else:
                add(float(validation.lo) + delta)
    else:
        for delta in deltas:
            add(origin - delta)
            add(origin + delta)
    return _deduplicate(candidates)


def _treatment_values(lever: Lever, baseline: Any) -> tuple[Any, ...]:
    validation = lever.validation
    if isinstance(validation, Bool):
        return (not bool(baseline),)
    if isinstance(validation, Choices):
        return tuple(value for value in validation.values if value != baseline)
    if isinstance(validation, EconomySet):
        return (frozenset({1}),)
    if isinstance(validation, EconomyId):
        return (2,)
    if isinstance(validation, Range):
        values = _numeric_treatments(lever, baseline)
        if not values:
            raise ValueError(f"{lever.name}: no valid numeric treatment was generated")
        return values
    raise TypeError(
        f"{lever.name}: unsupported validation type {type(validation).__name__}"
    )


def _treatment_batches(lever: Lever, baseline: Any) -> tuple[TreatmentBatch, ...]:
    values = _treatment_values(lever, baseline)
    batches: list[TreatmentBatch] = []
    for index, value in enumerate(values, start=1):
        actions: tuple[tuple[str, Any], ...]
        if lever.name == "manual_policy_rate":
            actions = (("manual_policy_rate", value), ("monetary_regime", "manual"))
        elif lever.name == "monetary_regime" and value == "manual":
            actions = (("manual_policy_rate", 1.0e-4), ("monetary_regime", "manual"))
        elif lever.name == "fx_regime" and value == "peg":
            actions = (("peg_anchor", 1), ("fx_regime", "peg"))
        else:
            actions = ((lever.name, value),)
        batches.append(TreatmentBatch(f"arm_{index}", actions))
    return tuple(batches)


def _registry_row(lever: Lever, baseline: Any) -> dict[str, Any]:
    return {
        "lever": lever.name,
        "owner_role": lever.owner_role,
        "decision_group": lever.decision_group,
        "scope": lever.scope,
        "validation": _validation_dict(lever),
        "reference_baseline": _json_value(baseline),
        "requires": sorted(lever.requires),
        "enabled_if": sorted(lever.enabled_if),
        "shadowed_by": list(lever.shadowed_by),
        "semantics": lever.semantics,
        "handler_id": lever.handler_id,
        "read_point": lever.read_point,
        "implementation_lag": lever.implementation_lag,
        "emergency_implementation_lag": lever.emergency_implementation_lag,
        "min_hold_ticks": lever.min_hold_ticks,
        "emergency": lever.emergency,
        "control_scale": lever.control_scale,
        "admin_weight": lever.admin_weight,
        "cost_class": lever.cost_class,
    }


def build_inventory() -> tuple[dict[str, Any], ...]:
    policy, external_policy = _reference_states()
    return tuple(
        _registry_row(
            lever,
            _reference_value(lever, policy, external_policy),
        )
        for lever in REGISTRY.values()
    )


def build_contracts() -> tuple[PolicyCausalContract, ...]:
    policy, external_policy = _reference_states()
    contracts: list[PolicyCausalContract] = []
    for lever in REGISTRY.values():
        group = GROUP_SPECS[(lever.owner_role, lever.decision_group)]
        fixture_id = LEVER_ACTIVATION_OVERRIDES.get(
            lever.name, group.activation_fixture
        )
        baseline = _reference_value(lever, policy, external_policy)
        proximal_metrics = LEVER_PROXIMAL_METRICS[lever.name]
        all_materiality_metrics = tuple(dict.fromkeys(
            proximal_metrics + group.tradeoff_metrics
        ))
        contracts.append(PolicyCausalContract(
            lever=lever.name,
            policy_schema_version=POLICY_SCHEMA_VERSION,
            owner_role=lever.owner_role,
            decision_group=lever.decision_group,
            scope=lever.scope,
            validation=_validation_dict(lever),
            reference_baseline=baseline,
            treatment_batches=_treatment_batches(lever, baseline),
            capabilities=tuple(sorted(lever.requires)),
            enabled_if=tuple(sorted(lever.enabled_if)),
            shadowed_by=lever.shadowed_by,
            semantics=lever.semantics,
            handler_id=lever.handler_id,
            first_native_read_point=lever.read_point,
            activation_fixture=fixture_id,
            mechanism_proximal_metrics=proximal_metrics,
            expected_directions={metric_id: "nonzero" for metric_id in proximal_metrics},
            tradeoff_metrics=group.tradeoff_metrics,
            ordinary_scenarios=group.ordinary_scenarios,
            structural_scenarios=group.structural_scenarios,
            crisis_roles=group.crisis_roles,
            causal_chain=group.causal_chain,
            operating_horizon_days=LEVER_HORIZON_OVERRIDES.get(
                lever.name, group.horizon_days
            ),
            materiality_metrics=all_materiality_metrics,
            state_notes=lever.state_notes,
        ))
    return tuple(contracts)


def verify_p0() -> list[str]:
    errors: list[str] = []
    registry_names = set(REGISTRY)
    policy_names = set(Policy.__dataclass_fields__)
    external_names = set(ExternalPolicy.__dataclass_fields__)

    if len(REGISTRY) != EXPECTED_REGISTRY_COUNT:
        errors.append(
            f"registry count {len(REGISTRY)} != {EXPECTED_REGISTRY_COUNT}"
        )
    if len(policy_names) != 88:
        errors.append(f"Policy field count {len(policy_names)} != 88")
    if len(external_names) != 14:
        errors.append(f"ExternalPolicy field count {len(external_names)} != 14")
    if registry_names != policy_names | external_names:
        errors.append(
            "Registry differs from Policy plus ExternalPolicy fields: "
            f"missing={sorted((policy_names | external_names) - registry_names)}, "
            f"stale={sorted(registry_names - (policy_names | external_names))}"
        )
    if len(GROUP_SPECS) != EXPECTED_GROUP_COUNT:
        errors.append(
            f"group contract count {len(GROUP_SPECS)} != {EXPECTED_GROUP_COUNT}"
        )
    live_groups = {(item.owner_role, item.decision_group) for item in REGISTRY.values()}
    if live_groups != set(GROUP_SPECS):
        errors.append(
            "group catalog differs from Registry: "
            f"missing={sorted(live_groups - set(GROUP_SPECS))}, "
            f"stale={sorted(set(GROUP_SPECS) - live_groups)}"
        )
    if registry_names != set(LEVER_PROXIMAL_METRICS):
        errors.append(
            "proximal metric map differs from Registry: "
            f"missing={sorted(registry_names - set(LEVER_PROXIMAL_METRICS))}, "
            f"stale={sorted(set(LEVER_PROXIMAL_METRICS) - registry_names)}"
        )
    stale_activation_overrides = set(LEVER_ACTIVATION_OVERRIDES) - registry_names
    if stale_activation_overrides:
        errors.append(
            f"stale activation overrides: {sorted(stale_activation_overrides)}"
        )
    stale_horizon_overrides = set(LEVER_HORIZON_OVERRIDES) - registry_names
    if stale_horizon_overrides:
        errors.append(f"stale horizon overrides: {sorted(stale_horizon_overrides)}")

    try:
        contracts = build_contracts()
    except Exception as exc:
        errors.append(f"contract build failed: {type(exc).__name__}: {exc}")
        return errors

    if len(contracts) != len(REGISTRY):
        errors.append(f"contract count {len(contracts)} != registry count {len(REGISTRY)}")
    for contract in contracts:
        lever = REGISTRY[contract.lever]
        if not contract.owner_role or not contract.decision_group:
            errors.append(f"{contract.lever}: owner or decision group is empty")
        if not contract.first_native_read_point:
            errors.append(f"{contract.lever}: native read point is empty")
        if contract.semantics == STATE_TRANSITION and not contract.handler_id:
            errors.append(f"{contract.lever}: state transition has no handler")
        if contract.activation_fixture not in ACTIVATION_FIXTURES:
            errors.append(
                f"{contract.lever}: unknown activation fixture {contract.activation_fixture}"
            )
        if not contract.mechanism_proximal_metrics:
            errors.append(f"{contract.lever}: no mechanism-proximal metric")
        for metric_id in contract.materiality_metrics:
            if metric_id not in METRIC_MATERIALITY:
                errors.append(f"{contract.lever}: no materiality rule for {metric_id}")
        if set(contract.crisis_roles) != set(SCENARIOS):
            errors.append(f"{contract.lever}: crisis matrix is incomplete")
        invalid_roles = set(contract.crisis_roles.values()) - CRISIS_ROLES
        if invalid_roles:
            errors.append(f"{contract.lever}: invalid crisis roles {sorted(invalid_roles)}")
        if set(contract.crisis_roles.values()) == {"not_applicable"}:
            errors.append(f"{contract.lever}: all crisis roles are not_applicable")
        if contract.operating_horizon_days <= 0:
            errors.append(f"{contract.lever}: operating horizon must be positive")
        if not contract.treatment_batches:
            errors.append(f"{contract.lever}: no treatment batch")
        for batch in contract.treatment_batches:
            names = [name for name, _value in batch.actions]
            if contract.lever not in names:
                errors.append(
                    f"{contract.lever}/{batch.label}: target lever missing from batch"
                )
            if len(names) != len(set(names)):
                errors.append(
                    f"{contract.lever}/{batch.label}: duplicate action names"
                )
            for name, value in batch.actions:
                action_lever = REGISTRY.get(name)
                if action_lever is None:
                    errors.append(
                        f"{contract.lever}/{batch.label}: unknown linked lever {name}"
                    )
                    continue
                old_value = (
                    contract.reference_baseline
                    if name == contract.lever
                    else _reference_value(
                        action_lever, *_reference_states()
                    )
                )
                validation_error = action_lever.validation.check(old_value, value)
                if validation_error:
                    errors.append(
                        f"{contract.lever}/{batch.label}/{name}: {validation_error}"
                    )

    for fixture in ACTIVATION_FIXTURES.values():
        if not fixture.preconditions or not fixture.activation_metrics:
            errors.append(f"{fixture.fixture_id}: incomplete activation fixture")
        for metric_id in fixture.activation_metrics:
            if metric_id not in METRIC_MATERIALITY:
                errors.append(
                    f"{fixture.fixture_id}: no materiality rule for {metric_id}"
                )
    for scenario in SCENARIOS.values():
        if not scenario.construction or not scenario.entry_metrics or not scenario.damage_metrics:
            errors.append(f"{scenario.scenario_id}: incomplete scenario contract")
        for metric_id in scenario.entry_metrics + scenario.damage_metrics:
            if metric_id not in METRIC_MATERIALITY:
                errors.append(
                    f"{scenario.scenario_id}: no materiality rule for {metric_id}"
                )
    for failure in FAILURE_TAXONOMY.values():
        if not all((failure.layer, failure.description, failure.default_disposition)):
            errors.append(f"{failure.code}: incomplete failure classification")
    return errors


def build_p0_payload() -> dict[str, Any]:
    errors = verify_p0()
    inventory = build_inventory()
    contracts = tuple(item.to_dict() for item in build_contracts())
    fixtures = {
        name: item.to_dict() for name, item in sorted(ACTIVATION_FIXTURES.items())
    }
    scenarios = {
        name: item.to_dict() for name, item in sorted(SCENARIOS.items())
    }
    materiality = {
        name: item.to_dict() for name, item in sorted(METRIC_MATERIALITY.items())
    }
    failures = {
        name: item.to_dict() for name, item in sorted(FAILURE_TAXONOMY.items())
    }
    hashes = {
        "registry": content_hash(inventory),
        "contracts": content_hash(contracts),
        "activation_fixtures": content_hash(fixtures),
        "scenarios": content_hash(scenarios),
        "materiality": content_hash(materiality),
        "failure_taxonomy": content_hash(failures),
    }
    hashes["p0_root"] = content_hash(hashes)
    return {
        "schema_version": P0_SCHEMA_VERSION,
        "status": "accepted" if not errors else "failed",
        "errors": errors,
        "counts": {
            "levers": len(inventory),
            "contracts": len(contracts),
            "decision_groups": len(GROUP_SPECS),
            "activation_fixtures": len(fixtures),
            "canonical_crises": len(scenarios),
            "materiality_metrics": len(materiality),
            "failure_classes": len(failures),
            "unmapped_levers": sum(
                1
                for contract in contracts
                if not contract["activation_fixture"]
                or not contract["mechanism_proximal_metrics"]
                or set(contract["crisis_roles"]) != set(SCENARIOS)
            ),
            "validation_errors": len(errors),
        },
        "hashes": hashes,
        "inventory": list(inventory),
        "contracts": list(contracts),
        "activation_fixtures": fixtures,
        "scenarios": scenarios,
        "materiality": materiality,
        "failure_taxonomy": failures,
    }


def render_p0_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Policy causality audit P0 ledger",
        "",
        f"Status: **{payload['status']}**  ",
        f"Schema: `{payload['schema_version']}`  ",
        f"Root hash: `{payload['hashes']['p0_root']}`",
        "",
        "## Counts",
        "",
        "| Item | Count |",
        "|---|---:|",
    ]
    for key, value in payload["counts"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend((
        "",
        "## Component hashes",
        "",
        "| Component | SHA-256 |",
        "|---|---|",
    ))
    for key, value in payload["hashes"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend((
        "",
        "## Lever contracts",
        "",
        "| Lever | Owner / group | Type | Activation | Horizon | Crisis roles | Proximal metrics |",
        "|---|---|---|---|---:|---|---|",
    ))
    for contract in payload["contracts"]:
        role_counts = {
            role: sum(1 for value in contract["crisis_roles"].values() if value == role)
            for role in ("primary", "secondary", "safety")
        }
        roles = ", ".join(
            f"{role[0].upper()}={count}" for role, count in role_counts.items()
        )
        metrics = "<br>".join(f"`{item}`" for item in contract["mechanism_proximal_metrics"])
        lines.append(
            f"| `{contract['lever']}` | `{contract['owner_role']}` / "
            f"`{contract['decision_group']}` | `{contract['validation']['kind']}` | "
            f"`{contract['activation_fixture']}` | {contract['operating_horizon_days']} | "
            f"{roles} | {metrics} |"
        )
    lines.extend((
        "",
        "## Canonical crisis readiness",
        "",
        "| Scenario | Readiness | Caveat |",
        "|---|---|---|",
    ))
    for scenario in payload["scenarios"].values():
        lines.append(
            f"| `{scenario['scenario_id']}` | `{scenario['readiness']}` | "
            f"{scenario['caveat'] or '-'} |"
        )
    lines.extend((
        "",
        "## Failure taxonomy",
        "",
        "| Code | Layer | Default disposition | Description |",
        "|---|---|---|---|",
    ))
    for failure in payload["failure_taxonomy"].values():
        lines.append(
            f"| `{failure['code']}` | `{failure['layer']}` | "
            f"`{failure['default_disposition']}` | {failure['description']} |"
        )
    if payload["errors"]:
        lines.extend(("", "## Errors", ""))
        lines.extend(f"- {item}" for item in payload["errors"])
    return "\n".join(lines) + "\n"


__all__ = [
    "EXPECTED_GROUP_COUNT",
    "EXPECTED_REGISTRY_COUNT",
    "P0_SCHEMA_VERSION",
    "PolicyCausalContract",
    "TreatmentBatch",
    "build_contracts",
    "build_inventory",
    "build_p0_payload",
    "canonical_json",
    "content_hash",
    "render_p0_markdown",
    "verify_p0",
]
