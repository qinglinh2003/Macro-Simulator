"""Build and validate the complete M0 Python-oracle contract inventory."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import MISSING, asdict, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
import inspect
import math
from pathlib import Path
import re
import subprocess
from typing import Any

import yaml

from macro_sim.config import Config
from macro_sim.controllers.coordinator import SEATS
from macro_sim.controllers.costs import AdjustmentCostSpec
from macro_sim.controllers.observation import (
    DEFAULT_OBSERVATION_SPEC,
    FISCAL_STABILIZATION_V1_OBSERVATION_SPEC,
)
from macro_sim.controllers.protocol import (
    CONTROLLER_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION,
    DecisionContext,
    PendingDecision,
    PermittedAction,
    PolicyAction,
    PolicyDecision,
    PolicyProposal,
)
from macro_sim.controllers.scheduler import (
    DEFAULT_CALENDARS,
    DEFAULT_TRIGGERS,
    CalendarSpec,
    TriggerNotice,
    TriggerSpec,
)
from macro_sim.controllers.session import (
    AWAITING_HUMAN,
    BOUNDARY_START,
    READY_TO_COMMIT,
    BoundaryResult,
)
from macro_sim.core.external_policy import ExternalPolicy
from macro_sim.core.policy import Policy
from macro_sim.core.phases import PHASES
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
)
from macro_sim.demographics.lifecycle_households import LifecycleHouseholdConfig
from macro_sim.demographics.relationships import RelationshipConfig
from macro_sim.demographics.social import SocialDynamicsConfig
from macro_sim.diagnostics.registry import DEFAULT_REGISTRY
from macro_sim.rl.codec import ContextCodec, DirectionalActionCodec
from macro_sim.rl.envs import (
    FISCAL_STABILIZATION_TASK,
    FiscalStabilizationEnvFactory,
)
from macro_sim.shocks.registry import DEFAULT_SHOCK_REGISTRY
from macro_sim.world.world import World
from scripts import policy_inventory

from .common import (
    REPO_ROOT,
    SchemaError,
    aggregate_hash,
    canonical_json_bytes,
    require_unique_ids,
    sha256_bytes,
    sha256_file,
    validate_stable_id,
)


ORACLE_COMMIT = "c0adcf1f8ea7f69cad28b92e27c9a4509dfdac23"
GENERATOR_VERSION = "m0-inventory-generator-v1"
INVENTORY_FAMILIES = (
    "config",
    "capabilities",
    "policy",
    "shocks",
    "metrics",
    "observations",
    "phases",
    "rng",
    "events",
    "invariants",
    "controller",
    "desktop_protocol",
    "scenarios",
    "probes",
    "modules",
    "m4_v0_v1",
)


def normalize(value: Any) -> Any:
    """Return deterministic JSON-safe data without using unstable repr output."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SchemaError(f"non-finite inventory value: {value!r}")
        return value
    if isinstance(value, Enum):
        return normalize(value.value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return normalize(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): normalize(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (set, frozenset)):
        normalized = [normalize(item) for item in value]
        return sorted(normalized, key=lambda item: canonical_json_bytes(item))
    if isinstance(value, (tuple, list)):
        return [normalize(item) for item in value]
    raise SchemaError(
        f"unsupported inventory value type {type(value).__name__}: {value!r}"
    )


def type_name(annotation: Any) -> str:
    if isinstance(annotation, str):
        return annotation.strip("\"'")
    if annotation is None:
        return "None"
    text = str(annotation).replace("typing.", "")
    match = re.fullmatch(r"<class '([^']+)'>", text)
    if match:
        return match.group(1)
    return text


def field_default(field: Any) -> tuple[str, Any]:
    if field.default is not MISSING:
        return "value", normalize(field.default)
    if field.default_factory is not MISSING:
        return "factory", normalize(field.default_factory())
    return "required", None


def slug(value: str) -> str:
    has_uppercase = any(character.isupper() for character in value)
    value = value.replace("__init__", "init").replace("__", "_")
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    value = re.sub(r"[^A-Za-z0-9_]+", "-", value).strip("-").lower()
    value = value.strip("_")
    value = re.sub(r"_+", "_", value)
    value = re.sub(r"(?<=-)_+", "", value)
    value = re.sub(r"_+(?=-)", "", value)
    value = re.sub(r"-+", "-", value)
    if has_uppercase:
        value = f"case-{value}"
    return value or "root"


def base_row(
    row_id: str,
    kind: str,
    source_path: str,
    source_symbol: str,
    owner_milestone: str,
    *,
    status: str = "active",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": validate_stable_id(row_id),
        "kind": kind,
        "source_path": source_path,
        "source_symbol": source_symbol,
        "status": status,
        "owner_milestone": owner_milestone,
        **normalize(extra),
    }


def payload(
    family: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    metadata: Mapping[str, Any] | None = None,
    aliases: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    sorted_rows = sorted((dict(row) for row in rows), key=lambda row: row["id"])
    require_unique_ids(sorted_rows)
    result = {
        "schema_version": "m0-inventory-v1",
        "family": family,
        "oracle_commit": ORACLE_COMMIT,
        "generator_version": GENERATOR_VERSION,
        "rows": sorted_rows,
        "metadata": normalize({} if metadata is None else metadata),
    }
    if aliases:
        result["aliases"] = normalize(aliases)
    validate_inventory_payload(result)
    return result


def _recursive_keys(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            result.add(str(key))
            result.update(_recursive_keys(item))
    elif isinstance(value, list):
        for item in value:
            result.update(_recursive_keys(item))
    return result


def _config_profile_references() -> dict[str, list[str]]:
    references: dict[str, list[str]] = defaultdict(list)
    for path in sorted((REPO_ROOT / "configs").rglob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key in sorted(_recursive_keys(raw)):
            references[key].append(path.relative_to(REPO_ROOT).as_posix())
    return dict(references)


def _dataclass_rows(
    cls: type,
    *,
    id_prefix: str,
    source_path: str,
    classifications: Mapping[str, set[str]],
    profile_references: Mapping[str, list[str]],
    status_by_name: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    by_name: dict[str, str] = {}
    for classification_name, names in classifications.items():
        for name in names:
            if name in by_name:
                raise SchemaError(f"{cls.__name__}.{name} has duplicate classification")
            by_name[name] = classification_name.lower()
    rows = []
    for field in fields(cls):
        if field.name not in by_name:
            raise SchemaError(f"{cls.__name__}.{field.name} is unclassified")
        default_kind, default = field_default(field)
        rows.append(
            base_row(
                f"{id_prefix}.{slug(field.name)}",
                "config",
                source_path,
                f"{cls.__name__}.{field.name}",
                "m1",
                status=(status_by_name or {}).get(field.name, "active"),
                field_name=field.name,
                declaring_type=cls.__name__,
                annotation=type_name(field.type),
                default_kind=default_kind,
                default=default,
                classification=by_name[field.name],
                profile_references=profile_references.get(field.name, []),
            )
        )
    return rows


def build_config_inventory() -> dict[str, Any]:
    errors = policy_inventory.verify()
    if errors:
        raise SchemaError("policy inventory verification failed: " + "; ".join(errors))
    classifications = policy_inventory.classification()
    references = _config_profile_references()
    rows = _dataclass_rows(
        Config,
        id_prefix="config",
        source_path="macro_sim/config/model.py",
        classifications=classifications["Config"],
        profile_references=references,
    )
    rows.extend(
        _dataclass_rows(
            SocialDynamicsConfig,
            id_prefix="config.social",
            source_path="macro_sim/demographics/social.py",
            classifications=classifications["Social"],
            profile_references=references,
        )
    )
    rows.extend(
        _dataclass_rows(
            RelationshipConfig,
            id_prefix="config.relationship",
            source_path="macro_sim/demographics/relationships.py",
            classifications=classifications["Relationship"],
            profile_references=references,
        )
    )
    rows.extend(
        _dataclass_rows(
            LifecycleHouseholdConfig,
            id_prefix="config.lifecycle-household",
            source_path="macro_sim/demographics/lifecycle_households.py",
            classifications=classifications["Lifecycle"],
            profile_references=references,
        )
    )

    world_classifications = classifications["World"]
    world_by_name = {
        name: group.lower()
        for group, names in world_classifications.items()
        for name in names
    }
    signature = inspect.signature(World.__init__)
    for name, parameter in signature.parameters.items():
        if name in {"self", "configs"}:
            continue
        if name not in world_by_name:
            raise SchemaError(f"World.{name} is unclassified")
        default = None if parameter.default is inspect.Parameter.empty else normalize(parameter.default)
        rows.append(
            base_row(
                f"config.world.{slug(name)}",
                "config",
                "macro_sim/world/world.py",
                f"World.__init__.{name}",
                "m9",
                status="deprecated" if name == "peg_economy" else "active",
                field_name=name,
                declaring_type="World",
                annotation=type_name(parameter.annotation),
                default_kind=(
                    "required"
                    if parameter.default is inspect.Parameter.empty
                    else "value"
                ),
                default=default,
                classification=world_by_name[name],
                profile_references=references.get(name, []),
            )
        )
    return payload(
        "config",
        rows,
        metadata={
            "root_config_field_count": len(fields(Config)),
            "total_tunable_count": len(rows),
            "classification_sources": [
                "scripts/policy_inventory.py",
                "dataclasses.fields",
                "World.__init__ signature",
            ],
        },
        aliases=LEGACY_ALIASES,
    )


CAPABILITY_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "bank_assignment": ("bank_enabled",),
    "bank_dynamics": ("bank_enabled",),
    "bank_equity": ("bank_enabled", "capital_market"),
    "bank_equity_trading": ("bank_enabled", "bank_equity", "capital_market"),
    "bank_rate_competition": ("bank_enabled",),
    "bank_realized_pnl": ("bank_enabled",),
    "bank_relationship_lock_in": ("bank_enabled",),
    "bank_runs": ("bank_enabled",),
    "bonds": ("government",),
    "builder_land_fee_credit": ("housing_construction_enabled",),
    "capital_firm_entry": ("capital_market",),
    "energy_household": ("energy_enabled",),
    "equity_finance": ("capital_market", "per_firm_equity"),
    "household_credit": ("bank_enabled",),
    "household_interest_arrears": ("bank_enabled", "household_credit"),
    "housing_construction_enabled": ("housing_enabled",),
    "housing_market_enabled": ("housing_enabled",),
    "housing_rental_enabled": ("housing_enabled",),
    "interbank": ("bank_enabled",),
    "labor_fractional_hours": ("labor_accounting",),
    "labor_job_ladder": ("labor_matching",),
    "labor_matching_friction": ("labor_matching",),
    "labor_person_efficiency": ("labor_matching",),
    "labor_relationship_wages": ("labor_matching",),
    "labor_second_job": ("labor_matching",),
    "labor_suspension": ("labor_matching",),
    "margin_credit": ("bank_enabled", "capital_market"),
    "monetary_direct_transmission": ("bank_enabled",),
    "mortgage_enabled": ("bank_enabled", "housing_enabled"),
    "per_firm_equity": ("capital_market",),
    "priced_firm_balance_sheet": ("firm_full_pnl",),
    "world.capital": ("world.couple",),
    "world.migration": ("world.couple",),
    "world.trade": ("world.couple",),
}


def _capability_owner(name: str) -> str:
    if name.startswith("world."):
        return "m9"
    if "energy" in name or "housing" in name or "mortgage" in name or "builder" in name:
        return "m8"
    if name.startswith(("demographic", "labor", "family")):
        return "m7"
    if any(token in name for token in ("bank", "credit", "interest", "interbank", "government", "bond")):
        return "m5"
    if any(token in name for token in ("equity", "firm_", "capital_market", "gibrat")):
        return "m6"
    return "m4"


def build_capabilities_inventory() -> dict[str, Any]:
    classifications = policy_inventory.classification()
    rows = []
    mechanism_fields = sorted(classifications["Config"]["MECHANISM"])
    for name in mechanism_fields:
        row_name = name
        rows.append(
            base_row(
                f"capability.{slug(row_name)}",
                "capability",
                "macro_sim/config/model.py",
                f"Config.{name}",
                _capability_owner(row_name),
                config_id=f"config.{slug(name)}",
                dependencies=list(CAPABILITY_DEPENDENCIES.get(row_name, ())),
                validation_evidence=[
                    "macro_sim/desktop/new_game.py",
                    "tests/test_desktop_new_game.py",
                ],
            )
        )
    for name in sorted(classifications["World"]["MECHANISM"]):
        row_name = f"world.{name}"
        rows.append(
            base_row(
                f"capability.world.{slug(name)}",
                "capability",
                "macro_sim/world/world.py",
                f"World.__init__.{name}",
                "m9",
                config_id=f"config.world.{slug(name)}",
                dependencies=list(CAPABILITY_DEPENDENCIES.get(row_name, ())),
                validation_evidence=[
                    "macro_sim/world/world.py::_validate_world_domains",
                    "tests/test_world_domain_validation.py",
                ],
            )
        )
    known = {row["id"].removeprefix("capability.").replace("-", "_") for row in rows}
    for owner, dependencies in CAPABILITY_DEPENDENCIES.items():
        owner_id = owner.replace(".", ".").replace("-", "_")
        if owner_id not in known:
            raise SchemaError(f"capability dependency owner is unknown: {owner}")
        for dependency in dependencies:
            dependency_id = dependency.replace(".", ".").replace("-", "_")
            if dependency_id not in known:
                raise SchemaError(
                    f"capability {owner} references unknown dependency {dependency}"
                )
    return payload(
        "capabilities",
        rows,
        metadata={
            "config_mechanism_count": len(mechanism_fields),
            "world_mechanism_count": len(rows) - len(mechanism_fields),
            "dependency_source": "reviewed M0 capability map",
        },
    )


def _validation_descriptor(value: Any) -> dict[str, Any]:
    if isinstance(value, NullableRange):
        return {
            "value_kind": "nullable_number",
            "minimum": value.lo,
            "maximum": value.hi,
            "max_step": value.max_step,
        }
    if isinstance(value, IntRange):
        return {
            "value_kind": "integer",
            "minimum": int(value.lo),
            "maximum": int(value.hi),
            "max_step": value.max_step,
        }
    if isinstance(value, Range):
        return {
            "value_kind": "number",
            "minimum": value.lo,
            "maximum": value.hi,
            "max_step": value.max_step,
        }
    if isinstance(value, Bool):
        return {"value_kind": "boolean"}
    if isinstance(value, Choices):
        return {"value_kind": "choice", "choices": list(value.values)}
    if isinstance(value, EconomyId):
        return {"value_kind": "nullable_economy_id", "minimum": 0}
    if isinstance(value, EconomySet):
        return {"value_kind": "economy_id_set", "minimum": 0}
    raise SchemaError(f"unknown policy validation type: {type(value).__name__}")


def _policy_owner_milestone(lever: Any) -> str:
    if lever.scope == "external" or lever.owner_role == "external_affairs":
        return "m9"
    if lever.owner_role == "energy" or lever.decision_group.startswith("energy"):
        return "m8"
    if lever.decision_group == "structural_law":
        return "m8"
    if lever.decision_group in {"macroprudential", "liquidity_operations", "monetary_stance"}:
        return "m5"
    if lever.decision_group in {"debt_management", "fiscal_stance", "tax_and_transfers"}:
        return "m5"
    return "m10"


def build_policy_inventory() -> dict[str, Any]:
    policy_defaults = Policy()
    external_defaults = ExternalPolicy()
    domestic_names = {field.name for field in fields(Policy)}
    external_names = {field.name for field in fields(ExternalPolicy)}
    rows = []
    for name, lever in REGISTRY.items():
        if name in domestic_names:
            source_path = "macro_sim/core/policy.py"
            declaring_type = "Policy"
            default = getattr(policy_defaults, name)
        elif name in external_names:
            source_path = "macro_sim/core/external_policy.py"
            declaring_type = "ExternalPolicy"
            default = getattr(external_defaults, name)
        else:
            raise SchemaError(f"registered policy lever has no state field: {name}")
        control = CONTROL_SPECS[name]
        rows.append(
            base_row(
                f"policy.{slug(name)}",
                "policy",
                source_path,
                f"{declaring_type}.{name}",
                _policy_owner_milestone(lever),
                lever_name=name,
                declaring_type=declaring_type,
                default=default,
                scope=lever.scope,
                semantics=lever.semantics,
                handler_id=lever.handler_id,
                validation=_validation_descriptor(lever.validation),
                requires=sorted(lever.requires),
                enabled_if=sorted(lever.enabled_if),
                shadowed_by=list(lever.shadowed_by),
                runtime_read_point=lever.read_point,
                state_notes=lever.state_notes,
                seat=control.owner_role,
                decision_group=control.decision_group,
                implementation_lag=control.implementation_lag,
                emergency_implementation_lag=control.emergency_implementation_lag,
                min_hold_ticks=control.min_hold_ticks,
                emergency=control.emergency,
                control_scale=control.control_scale,
                admin_weight=control.admin_weight,
                cost_class=control.cost_class,
                effectiveness_test="tests/test_policy_effectiveness.py",
            )
        )
    semantics = defaultdict(int)
    for lever in REGISTRY.values():
        semantics[lever.semantics] += 1
    return payload(
        "policy",
        rows,
        metadata={
            "lever_count": len(rows),
            "domestic_count": len(domestic_names),
            "external_count": len(external_names),
            "semantic_counts": dict(semantics),
            "seats": list(SEATS),
            "decision_groups": sorted(
                {spec.decision_group for spec in CONTROL_SPECS.values()}
            ),
        },
        aliases=LEGACY_ALIASES,
    )


def build_shock_inventory() -> dict[str, Any]:
    rows = []
    for kind, definition in DEFAULT_SHOCK_REGISTRY.items():
        rows.append(
            base_row(
                f"shock.{slug(kind)}",
                "shock",
                "macro_sim/shocks/registry.py",
                f"DEFAULT_SHOCK_REGISTRY.{kind}",
                "m9",
                shock_kind=kind,
                channel=definition.channel,
                description=definition.description,
                magnitude_min=definition.magnitude_min,
                magnitude_max=definition.magnitude_max,
                one_shot=definition.one_shot,
                allowed_sectors=sorted(definition.allowed_sectors),
                required_capability=definition.required_capability,
                emergency_seats=list(definition.emergency_seats),
                combination_rule=(
                    "additive_required_return_spread"
                    if kind == "sovereign_risk_premium"
                    else "additive_exchange_rate_pressure"
                    if kind == "capital_outflow_pressure"
                    else "multiplicative_factor_or_registered_one_shot"
                ),
                lifecycle_source=(
                    "native/src/simulation/m9.cpp::shock_addition"
                    if kind in {
                        "sovereign_risk_premium",
                        "capital_outflow_pressure",
                    }
                    else "macro_sim/shocks/engine.py::ShockEngine"
                ),
                replay_source="macro_sim/shocks/spec.py::ShockTape",
            )
        )
    return payload(
        "shocks",
        rows,
        metadata={"default_kind_count": len(rows), "schema_version": 1},
    )


def _small_config(factory: Any, seed: int = 0) -> Config:
    return factory(
        n_households=20,
        n_firms_c=8,
        n_firms_k=4,
        n_firms_e=2,
        n_builders=2,
        n_banks=2,
        n_ticks=1,
        seed=seed,
    )


def _sample_metric_keys() -> tuple[dict[str, set[str]], dict[str, str]]:
    from macro_sim.desktop.runtime import METRIC_NAMES, PANEL_WORLD_METRIC_NAMES
    from macro_sim.economy import Economy

    scopes: dict[str, set[str]] = {"economy": set(), "world": set()}
    types: dict[str, str] = {}
    factories = (Config, Config.v2, Config.v93, Config.v124)
    for offset, factory in enumerate(factories):
        record = Economy(_small_config(factory, offset)).step()
        for name, value in record.items():
            scopes["economy"].add(name)
            types[f"economy:{name}"] = type(value).__name__
    configs = [_small_config(Config.v124, 100), _small_config(Config.v124, 101)]
    world = World(
        configs,
        couple=True,
        trade=True,
        capital=True,
        migration=True,
    )
    world.step()
    for name, value in world.world_records[-1].items():
        scopes["world"].add(name)
        types[f"world:{name}"] = type(value).__name__
    scopes["economy"].update(METRIC_NAMES)
    scopes["world"].update(PANEL_WORLD_METRIC_NAMES)
    for field in DEFAULT_OBSERVATION_SPEC.fields:
        if field.source in scopes:
            scopes[field.source].add(field.source_key.split(".")[0])
    for spec in DEFAULT_REGISTRY:
        scopes["economy"].add(spec.metric_id)
    return scopes, types


def build_metrics_inventory() -> dict[str, Any]:
    scopes, sample_types = _sample_metric_keys()
    diagnostic_specs = {spec.metric_id: normalize(spec.to_dict()) for spec in DEFAULT_REGISTRY}
    observations: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for field in DEFAULT_OBSERVATION_SPEC.fields:
        if field.source in {"economy", "world"}:
            observations[(field.source, field.source_key.split(".")[0])].append(
                normalize(field.to_dict())
            )
    rows = []
    for scope in ("economy", "world"):
        for name in sorted(scopes[scope]):
            obs = observations.get((scope, name), [])
            source_path = (
                "macro_sim/reporting/metrics.py"
                if scope == "economy"
                else "macro_sim/world/world.py"
            )
            source_symbol = (
                "compute_tick_metrics"
                if scope == "economy"
                else "World._dealer_update"
            )
            rows.append(
                base_row(
                    f"metric.{scope}.{slug(name)}",
                    "metric",
                    source_path,
                    source_symbol,
                    "m10",
                    metric_name=name,
                    scope=scope,
                    sample_value_type=sample_types.get(f"{scope}:{name}"),
                    emitted_by_reference_fixture=(
                        f"{scope}:{name}" in sample_types
                    ),
                    diagnostic_spec=diagnostic_specs.get(name),
                    observation_contracts=obs,
                    snapshot_epoch="committed",
                    publication_epoch="published" if obs else None,
                    privilege=(
                        sorted({item["access_class"] for item in obs})
                        if obs
                        else ["internal_or_diagnostic"]
                    ),
                )
            )
    return payload(
        "metrics",
        rows,
        metadata={
            "economy_metric_count": len(scopes["economy"]),
            "world_metric_count": len(scopes["world"]),
            "diagnostic_registry_count": len(diagnostic_specs),
            "sampling_profiles": ["Config", "v2", "v93", "v124", "World.v124.n2"],
        },
    )


def _fiscal_codecs() -> tuple[ContextCodec, DirectionalActionCodec]:
    fields_ = tuple(FISCAL_STABILIZATION_V1_OBSERVATION_SPEC.fields)
    scales = {
        field.series_id: (
            1.0 if field.normalization_scale is None else field.normalization_scale
        )
        for field in fields_
    }
    context = ContextCodec.from_parts(
        economy_id=0,
        seat="treasury",
        action_levers=("gov_deficit_target",),
        observation_series=tuple(scales),
        normalization_scales=scales,
        observation_schema_version=(
            FISCAL_STABILIZATION_V1_OBSERVATION_SPEC.schema_version
        ),
    )
    return context, DirectionalActionCodec.from_context_codec(context)


def build_observations_inventory() -> dict[str, Any]:
    rows = []
    for ordinal, field in enumerate(DEFAULT_OBSERVATION_SPEC.fields):
        rows.append(
            base_row(
                f"observation.release.{slug(field.series_id)}",
                "observation_release",
                "macro_sim/controllers/observation.py",
                f"DEFAULT_OBSERVATION_SPEC.{field.series_id}",
                "m10",
                ordinal=ordinal,
                **field.to_dict(),
            )
        )
    context, action = _fiscal_codecs()
    for ordinal, feature_name in enumerate(context.feature_names):
        rows.append(
            base_row(
                f"observation.rl.fiscal-stabilization-v1.feature-{ordinal:03d}",
                "rl_feature",
                "macro_sim/rl/codec.py",
                "ContextCodec.feature_names",
                "m10",
                ordinal=ordinal,
                task_id=FISCAL_STABILIZATION_TASK,
                feature_name=feature_name,
                dtype="float64",
            )
        )
    return payload(
        "observations",
        rows,
        metadata={
            "release_schema_version": DEFAULT_OBSERVATION_SPEC.schema_version,
            "release_series_count": len(DEFAULT_OBSERVATION_SPEC.fields),
            "fiscal_v1_feature_count": context.observation_dim,
            "fiscal_v1_context_contract_hash": context.contract_hash,
            "fiscal_v1_action_dimension_count": action.action_dim,
            "fiscal_v1_direction_count": 3,
            "fiscal_v1_action_contract_hash": action.contract_hash,
        },
    )


def _load_rows_manifest(name: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = REPO_ROOT / "schemas" / "m0" / "manifests" / name
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SchemaError(f"cannot load {path}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("rows"), list):
        raise SchemaError(f"{path}: expected an object containing rows")
    return [dict(row) for row in raw["rows"]], raw


def build_phases_inventory() -> dict[str, Any]:
    source_rows, raw = _load_rows_manifest("phases.yaml")
    runtime_by_id = {phase.id: phase for phase in PHASES}
    source_by_id = {row["id"]: row for row in source_rows}
    if set(runtime_by_id) != set(source_by_id):
        raise SchemaError("phase manifest and runtime registry contain different IDs")
    for phase_id, phase in runtime_by_id.items():
        row = source_by_id[phase_id]
        expected = (phase.code, phase.ordinal, phase.scope, phase.snapshot_epoch)
        actual = (
            row.get("phase_code"),
            row.get("order"),
            row.get("scope"),
            row.get("snapshot_after"),
        )
        if actual != expected:
            raise SchemaError(
                f"{phase_id}: runtime/manifest phase mismatch "
                f"(runtime={expected!r}, manifest={actual!r})"
            )
    rows = [
        base_row(
            row.pop("id"),
            "phase",
            row.pop("source_path"),
            row.pop("source_symbol"),
            row.pop("owner_milestone"),
            **row,
        )
        for row in source_rows
    ]
    return payload(
        "phases",
        rows,
        metadata={
            "source_schema_version": raw["schema_version"],
            "phase_count": len(rows),
            "explicit_runtime_constants": True,
            "runtime_instrumentation_work_package": "complete",
        },
    )


RNG_CONSTRUCTORS = {
    "random.Random",
    "np.random.default_rng",
    "numpy.random.default_rng",
    "np.random.SeedSequence",
    "numpy.random.SeedSequence",
}
RNG_SEED_FUNCTIONS = {
    "np.random.seed",
    "numpy.random.seed",
    "random.seed",
    "torch.manual_seed",
}
RNG_DRAW_METHODS = {
    "beta",
    "choice",
    "choices",
    "exponential",
    "gamma",
    "gauss",
    "integers",
    "lognormal",
    "normal",
    "poisson",
    "random",
    "sample",
    "shuffle",
    "uniform",
}


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _target_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _call_name(node)
    if isinstance(node, (ast.Tuple, ast.List)):
        return "-".join(filter(None, (_target_name(item) for item in node.elts)))
    return "anonymous"


class _RngVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.module = relative_path.removesuffix(".py").replace("/", ".")
        self.scope: list[str] = []
        self.rows: list[dict[str, Any]] = []
        self.counters: dict[str, int] = defaultdict(int)
        self.constructor_nodes: set[int] = set()

    @property
    def scope_name(self) -> str:
        return ".".join((self.module, *self.scope))

    def _add_constructor(self, call: ast.Call | None, target: str, expression: str) -> None:
        if call is not None:
            self.constructor_nodes.add(id(call))
        key = f"stream:{self.scope_name}:{target}"
        ordinal = self.counters[key]
        self.counters[key] += 1
        suffix = "" if ordinal == 0 else f"-{ordinal}"
        self.rows.append(
            base_row(
                f"rng.stream.{slug(self.scope_name)}.{slug(target)}{suffix}",
                "rng_stream",
                self.relative_path,
                f"{self.scope_name}:{getattr(call, 'lineno', 0)}",
                _module_owner(self.relative_path),
                constructor=expression,
                seed_expression=(
                    ast.unparse(call.args[0])
                    if call is not None and call.args
                    else None
                ),
                target=target,
                scope=self.scope_name,
                checkpointed=not self.relative_path.startswith("macro_sim/rl/algorithm.py"),
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call):
            constructor = _call_name(node.value.func)
            if constructor in RNG_CONSTRUCTORS:
                for target in node.targets:
                    self._add_constructor(node.value, _target_name(target), constructor)
            elif constructor.endswith(".field"):
                for keyword in node.value.keywords:
                    factory = _call_name(keyword.value)
                    if keyword.arg == "default_factory" and factory in RNG_CONSTRUCTORS:
                        for target in node.targets:
                            self._add_constructor(None, _target_name(target), factory)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.value, ast.Call):
            constructor = _call_name(node.value.func)
            if constructor in RNG_CONSTRUCTORS:
                self._add_constructor(node.value, _target_name(node.target), constructor)
            elif constructor.endswith(".field"):
                for keyword in node.value.keywords:
                    factory = _call_name(keyword.value)
                    if keyword.arg == "default_factory" and factory in RNG_CONSTRUCTORS:
                        self._add_constructor(None, _target_name(node.target), factory)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call = _call_name(node.func)
        if call in RNG_CONSTRUCTORS and id(node) not in self.constructor_nodes:
            self._add_constructor(node, "anonymous", call)
        elif call in RNG_SEED_FUNCTIONS:
            self._add_constructor(node, "global-seed", call)
        method = call.rsplit(".", 1)[-1]
        if method in RNG_DRAW_METHODS and "." in call:
            receiver = call.rsplit(".", 1)[0]
            key = f"draw:{self.scope_name}:{receiver}:{method}"
            ordinal = self.counters[key]
            self.counters[key] += 1
            self.rows.append(
                base_row(
                    (
                        f"rng.draw.{slug(self.scope_name)}."
                        f"{slug(receiver)}.{slug(method)}-{ordinal:02d}"
                    ),
                    "rng_draw",
                    self.relative_path,
                    f"{self.scope_name}:{node.lineno}",
                    _module_owner(self.relative_path),
                    receiver=receiver,
                    method=method,
                    scope=self.scope_name,
                    argument_shape=ast.unparse(node),
                )
            )
        self.generic_visit(node)


def build_rng_inventory() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted((REPO_ROOT / "macro_sim").rglob("*.py")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        visitor = _RngVisitor(relative)
        visitor.visit(tree)
        rows.extend(visitor.rows)
    stream_count = sum(row["kind"] == "rng_stream" for row in rows)
    draw_count = sum(row["kind"] == "rng_draw" for row in rows)
    return payload(
        "rng",
        rows,
        metadata={
            "stream_count": stream_count,
            "draw_site_count": draw_count,
            "runtime_semantics": "preserve_python",
            "portable_native_rng": "deferred_to_m1",
        },
    )


def _literal_event_types(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        call = _call_name(node.func)
        if not call.endswith(".events.append"):
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            result.add(first.value)
    return result


def build_events_inventory() -> dict[str, Any]:
    controller_paths = (
        REPO_ROOT / "macro_sim/controllers/coordinator.py",
        REPO_ROOT / "macro_sim/controllers/session.py",
    )
    controller_types = {"proposal_submitted", "timeout"}
    for path in controller_paths:
        controller_types.update(_literal_event_types(path))
    shock_types = {"announced", "started", "ended", "realized"}
    controller_types.update(f"shock_{name}" for name in shock_types)
    rows = [
        base_row(
            f"event.controller.{slug(name)}",
            "event",
            "macro_sim/controllers/events.py",
            f"EventStream:{name}",
            "m10",
            event_type=name,
            stream="controller",
            schema_version=CONTROLLER_SCHEMA_VERSION,
            replay_classes=["input", "derived"],
            ordering_key=["global_sequence"],
            hash_chain=True,
        )
        for name in sorted(controller_types)
    ]
    rows.extend(
        base_row(
            f"event.shock.{slug(name)}",
            "event",
            "macro_sim/shocks/engine.py",
            f"ShockEventStream:{name}",
            "m9",
            event_type=name,
            stream="shock",
            schema_version=1,
            ordering_key=["tick", "event_sequence"],
            hash_chain=True,
        )
        for name in sorted(shock_types)
    )
    return payload(
        "events",
        rows,
        metadata={
            "controller_event_type_count": len(controller_types),
            "shock_event_type_count": len(shock_types),
            "dynamic_expansions": {
                "coordinator_input_event_type": ["proposal_submitted", "timeout"],
                "session_shock_bridge": sorted(f"shock_{name}" for name in shock_types),
            },
        },
    )


def build_invariants_inventory() -> dict[str, Any]:
    source_rows, raw = _load_rows_manifest("invariants.yaml")
    rows = [
        base_row(
            row.pop("id"),
            "invariant",
            row.pop("source_path"),
            row.pop("source_symbol"),
            row.pop("owner_milestone"),
            **row,
        )
        for row in source_rows
    ]
    return payload(
        "invariants",
        rows,
        metadata={
            "source_schema_version": raw["schema_version"],
            "invariant_count": len(rows),
        },
    )


def _dataclass_protocol_row(cls: type, source_path: str) -> dict[str, Any]:
    return base_row(
        f"controller.protocol.{slug(cls.__name__)}",
        "controller_protocol",
        source_path,
        cls.__name__,
        "m10",
        protocol_type=cls.__name__,
        fields=[
            {
                "name": field.name,
                "annotation": type_name(field.type),
                "required": field.default is MISSING and field.default_factory is MISSING,
            }
            for field in fields(cls)
        ],
    )


def build_controller_inventory() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for seat in SEATS:
        rows.append(
            base_row(
                f"controller.seat.{slug(seat)}",
                "controller_seat",
                "macro_sim/controllers/coordinator.py",
                f"SEATS:{seat}",
                "m10",
                seat=seat,
            )
        )
    for group, calendar in DEFAULT_CALENDARS.items():
        rows.append(
            base_row(
                f"controller.group.{slug(group)}",
                "controller_group",
                "macro_sim/controllers/scheduler.py",
                f"DEFAULT_CALENDARS.{group}",
                "m10",
                decision_group=group,
                calendar=asdict(calendar),
                owned_levers=sorted(
                    name
                    for name, spec in CONTROL_SPECS.items()
                    if spec.decision_group == group
                ),
            )
        )
    for trigger in DEFAULT_TRIGGERS:
        rows.append(
            base_row(
                f"controller.trigger.{slug(trigger.trigger_id)}",
                "controller_trigger",
                "macro_sim/controllers/scheduler.py",
                f"DEFAULT_TRIGGERS.{trigger.trigger_id}",
                "m10",
                **asdict(trigger),
            )
        )
    for mode in ("interactive", "realtime", "batch", "replay"):
        rows.append(
            base_row(
                f"controller.run-mode.{mode}",
                "controller_run_mode",
                "macro_sim/controllers/session.py",
                "ControlledSimulationSession.run_mode",
                "m10",
                run_mode=mode,
            )
        )
    for phase in (BOUNDARY_START, AWAITING_HUMAN, READY_TO_COMMIT):
        rows.append(
            base_row(
                f"controller.boundary-phase.{slug(phase)}",
                "controller_boundary_phase",
                "macro_sim/controllers/session.py",
                f"ControlledSimulationSession.phase:{phase}",
                "m10",
                boundary_phase=phase,
            )
        )
    protocol_types = (
        PolicyAction,
        PermittedAction,
        DecisionContext,
        PolicyProposal,
        PolicyDecision,
        PendingDecision,
        BoundaryResult,
        CalendarSpec,
        TriggerSpec,
        TriggerNotice,
    )
    for cls in protocol_types:
        source = (
            "macro_sim/controllers/scheduler.py"
            if cls in {CalendarSpec, TriggerSpec, TriggerNotice}
            else (
                "macro_sim/controllers/session.py"
                if cls is BoundaryResult
                else "macro_sim/controllers/protocol.py"
            )
        )
        rows.append(_dataclass_protocol_row(cls, source))
    context, action = _fiscal_codecs()
    factory = FiscalStabilizationEnvFactory()
    rows.append(
        base_row(
            "controller.rl-task.fiscal-stabilization-v1",
            "rl_task",
            "macro_sim/rl/envs.py",
            "FiscalStabilizationEnvFactory",
            "m10",
            task_id=FISCAL_STABILIZATION_TASK,
            environment_contract=factory.environment_contract,
            environment_contract_hash=factory.environment_contract_hash,
            observation_feature_count=context.observation_dim,
            observation_contract_hash=context.contract_hash,
            action_levers=["gov_deficit_target"],
            action_dimension_count=action.action_dim,
            direction_codes={"down": 0, "hold": 1, "up": 2},
            action_contract_hash=action.contract_hash,
        )
    )
    rows.append(
        base_row(
            "controller.adjustment-cost.default",
            "controller_cost",
            "macro_sim/controllers/costs.py",
            "AdjustmentCostSpec",
            "m10",
            spec=AdjustmentCostSpec(),
        )
    )
    return payload(
        "controller",
        rows,
        metadata={
            "controller_schema_version": CONTROLLER_SCHEMA_VERSION,
            "observation_schema_version": OBSERVATION_SCHEMA_VERSION,
            "seat_count": len(SEATS),
            "decision_group_count": len(DEFAULT_CALENDARS),
            "trigger_count": len(DEFAULT_TRIGGERS),
        },
    )


def _desktop_commands() -> set[str]:
    path = REPO_ROOT / "macro_sim/desktop/runtime.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not isinstance(node.left, ast.Name) or node.left.id != "name":
            continue
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                result.add(comparator.value)
            elif isinstance(comparator, (ast.Set, ast.Tuple, ast.List)):
                result.update(
                    item.value
                    for item in comparator.elts
                    if isinstance(item, ast.Constant)
                    and isinstance(item.value, str)
                )
    return result


def build_desktop_protocol_inventory() -> dict[str, Any]:
    from macro_sim.desktop.runtime import PROTOCOL_VERSION

    commands = _desktop_commands()
    rows = [
        base_row(
            f"desktop.command.{slug(command)}",
            "desktop_command",
            "macro_sim/desktop/runtime.py",
            f"SimulationRuntime.handle:{command}",
            "m11",
            command=command,
            transport="newline_delimited_json",
            request_limit_bytes=1_048_576,
            response_envelope=[
                "ok",
                "request_id",
                "protocol_version",
                "snapshot_or_error",
            ],
            single_writer=True,
        )
        for command in sorted(commands)
    ]
    rows.extend(
        (
            base_row(
                "desktop.response.success",
                "desktop_response",
                "macro_sim/desktop/server.py",
                "_Handler.handle:success",
                "m11",
                fields=["ok", "request_id", "protocol_version", "snapshot"],
            ),
            base_row(
                "desktop.response.error",
                "desktop_response",
                "macro_sim/desktop/server.py",
                "_Handler.handle:error",
                "m11",
                fields=["ok", "request_id", "protocol_version", "error"],
                error_fields=["type", "message"],
            ),
        )
    )
    return payload(
        "desktop_protocol",
        rows,
        metadata={
            "protocol_version": PROTOCOL_VERSION,
            "command_count": len(commands),
            "commands": sorted(commands),
        },
    )


def build_scenarios_inventory() -> dict[str, Any]:
    import json

    rows: list[dict[str, Any]] = []
    for path in sorted((REPO_ROOT / "configs").rglob("*.yaml")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        rows.append(
            base_row(
                f"scenario.config.{slug(path.relative_to(REPO_ROOT / 'configs').as_posix())}",
                "config_scenario",
                relative,
                "yaml_document",
                "m0",
                file_sha256=sha256_file(path),
                top_level_keys=sorted(raw) if isinstance(raw, dict) else [],
            )
        )
    shock_module = REPO_ROOT / "macro_sim/shocks/scenarios.py"
    shock_tree = ast.parse(shock_module.read_text(encoding="utf-8"))
    for node in shock_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.endswith("_scenario"):
            rows.append(
                base_row(
                    f"scenario.shock.{slug(node.name.removesuffix('_scenario'))}",
                    "shock_scenario",
                    "macro_sim/shocks/scenarios.py",
                    node.name,
                    "m9",
                )
            )
    for name in ("diagnostic_matrix", "root_cause_matrix"):
        rows.append(
            base_row(
                f"scenario.diagnostic.{slug(name)}",
                "diagnostic_scenario",
                "macro_sim/diagnostics/scenarios.py",
                name,
                "m10",
            )
        )
    rows.append(
        base_row(
            "scenario.rl.fiscal-stabilization-v1",
            "rl_scenario",
            "macro_sim/rl/envs.py",
            "FiscalStabilizationEnvFactory",
            "m10",
            task_id=FISCAL_STABILIZATION_TASK,
            contract_hash=FiscalStabilizationEnvFactory().environment_contract_hash,
        )
    )
    rows.append(
        base_row(
            "scenario.desktop.smoke",
            "desktop_scenario",
            "scripts/desktop_smoke.py",
            "main",
            "m11",
        )
    )
    fixture_path = REPO_ROOT / "tests/fixtures/m0/manifests/fixtures.json"
    if fixture_path.is_file():
        fixture_manifest = json.loads(fixture_path.read_text(encoding="utf-8"))
        for fixture in fixture_manifest["rows"]:
            rows.append(
                base_row(
                    fixture["id"],
                    "migration_fixture",
                    "schemas/m0/manifests/fixtures.yaml",
                    fixture["id"],
                    "m0",
                    tier=fixture["tier"],
                    deterministic=fixture["deterministic"],
                    duration_ticks=fixture["duration_ticks"],
                    config_contract_sha256=fixture["config_contract_sha256"],
                    genesis_contract_sha256=fixture["genesis_contract_sha256"],
                    gate_classes=fixture["gate_classes"],
                )
            )
    benchmark_raw = yaml.safe_load(
        (REPO_ROOT / "schemas/m0/manifests/benchmark_scenarios.yaml").read_text(
            encoding="utf-8"
        )
    )
    for scenario in benchmark_raw["scenarios"]:
        rows.append(
            base_row(
                f"scenario.benchmark.{slug(scenario['id'])}",
                "benchmark_scenario",
                "schemas/m0/manifests/benchmark_scenarios.yaml",
                scenario["id"],
                "m0",
                workload_kind=scenario["kind"],
                resource_gate=scenario["gate"],
                population=scenario["population"],
                economy_count=scenario["economies"],
                duration_ticks=scenario["ticks"],
                scenario_contract_sha256=sha256_bytes(
                    canonical_json_bytes(normalize(scenario))
                ),
            )
        )
    return payload(
        "scenarios",
        rows,
        metadata={
            "scenario_count": len(rows),
            "migration_fixture_count": sum(
                row["kind"] == "migration_fixture" for row in rows
            ),
        },
    )


def build_probes_inventory() -> dict[str, Any]:
    source_rows, raw = _load_rows_manifest("probe_disposition.yaml")
    rows = [
        base_row(
            row.pop("id"),
            "probe",
            row.pop("source_path"),
            row.pop("source_symbol"),
            row.pop("owner_milestone"),
            status=(
                "oracle_only"
                if row.get("disposition") == "python_oracle_only"
                else "active"
            ),
            **row,
        )
        for row in source_rows
    ]
    return payload(
        "probes",
        rows,
        metadata={
            "source_schema_version": raw["schema_version"],
            "probe_count": len(rows),
            "unresolved_count": 0,
        },
    )


def _module_owner(path: str) -> str:
    if path == "macro_sim/desktop/native_projection.py":
        return "m10"
    if path in {
        "scripts/desktop_smoke.py",
        "scripts/package_m11_linux.sh",
        "scripts/package_m11_macos.sh",
        "scripts/package_m11_windows.ps1",
        "scripts/run_godot_prototype.sh",
    }:
        return "m11"
    if path.startswith("desktop/godot"):
        return "m11"
    if path.startswith(("configs/", "scripts/")):
        return "m0"
    if path.startswith("macro_sim/world") or path.startswith("macro_sim/shocks"):
        return "m9"
    if path.startswith("macro_sim/housing") or "systems/energy" in path:
        return "m8"
    if path.startswith(("macro_sim/demographics", "macro_sim/labor")) or any(
        token in path for token in ("systems/family", "systems/labor")
    ):
        return "m7"
    if any(
        token in path
        for token in (
            "systems/equity",
            "systems/securities",
            "systems/firm_",
            "systems/valuation",
            "systems/capital_goods",
        )
    ):
        return "m6"
    if any(
        token in path
        for token in (
            "systems/banking",
            "systems/central_bank",
            "systems/credit",
            "systems/settlement",
            "core/ledger",
        )
    ):
        return "m5"
    if path.startswith(("macro_sim/controllers", "macro_sim/reporting", "macro_sim/rl", "macro_sim/diagnostics")):
        return "m10"
    if path.startswith("macro_sim/desktop"):
        return "m11"
    if path.startswith(("macro_sim/config", "macro_sim/core", "macro_sim/checkpoint")):
        return "m1"
    if path.startswith(("macro_sim/behavior", "macro_sim/markets")):
        return "m3"
    return "m4"


def _module_action(path: str) -> str:
    if path in {
        "scripts/desktop_smoke.py",
        "scripts/package_m11_linux.sh",
        "scripts/package_m11_macos.sh",
        "scripts/package_m11_windows.ps1",
        "scripts/run_godot_prototype.sh",
    }:
        return "keep_client"
    if path.startswith("scripts/"):
        return "oracle_only"
    if path.startswith(("configs/", "macro_sim/data/")):
        return "keep"
    if path.startswith("desktop/godot"):
        return "keep_client"
    if path.startswith(("macro_sim/diagnostics", "macro_sim/visualization")):
        return "adapter"
    if path.startswith("macro_sim/desktop"):
        return "wrap_native_worker"
    if path.startswith(("macro_sim/controllers", "macro_sim/reporting", "macro_sim/rl")):
        return "port_or_adapter"
    return "port"


def _module_paths() -> list[Path]:
    paths: list[Path] = []
    roots_and_suffixes = (
        (REPO_ROOT / "macro_sim", {".py", ".json", ".msrl"}),
        (REPO_ROOT / "desktop/godot", {".gd", ".tscn", ".godot", ".json", ".svg"}),
        (REPO_ROOT / "scripts", {".ps1", ".py", ".sh"}),
        (REPO_ROOT / "configs", {".yaml"}),
    )
    for root, suffixes in roots_and_suffixes:
        if not root.exists():
            continue
        paths.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in suffixes
            and ".venv" not in path.parts
            and "__pycache__" not in path.parts
        )
    return sorted(set(paths))


def build_modules_inventory() -> dict[str, Any]:
    rows = []
    for path in _module_paths():
        relative = path.relative_to(REPO_ROOT).as_posix()
        rows.append(
            base_row(
                f"module.{slug(relative)}",
                "module",
                relative,
                "module",
                _module_owner(relative),
                action=_module_action(relative),
                role=relative.split("/", 1)[0],
                file_sha256=sha256_file(path),
            )
        )
    return payload(
        "modules",
        rows,
        metadata={
            "module_count": len(rows),
            "unresolved_count": 0,
            "enumerated_roots": ["macro_sim", "desktop/godot", "scripts", "configs"],
        },
    )


def build_m4_inventory() -> dict[str, Any]:
    path = REPO_ROOT / "schemas/m0/manifests/m4_v0_v1.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    verticals = raw.get("verticals") if isinstance(raw, dict) else None
    if not isinstance(verticals, list):
        raise SchemaError("M4 vertical manifest must contain verticals")
    rows = []
    for vertical in verticals:
        item = dict(vertical)
        row_id = item.pop("id")
        rows.append(
            base_row(
                row_id,
                "m4_vertical",
                "schemas/m0/manifests/m4_v0_v1.yaml",
                row_id,
                "m4",
                **item,
            )
        )
    return payload(
        "m4_v0_v1",
        rows,
        metadata={
            "source_schema_version": raw["schema_version"],
            "vertical_count": len(rows),
        },
    )


BUILDERS = {
    "config": build_config_inventory,
    "capabilities": build_capabilities_inventory,
    "policy": build_policy_inventory,
    "shocks": build_shock_inventory,
    "metrics": build_metrics_inventory,
    "observations": build_observations_inventory,
    "phases": build_phases_inventory,
    "rng": build_rng_inventory,
    "events": build_events_inventory,
    "invariants": build_invariants_inventory,
    "controller": build_controller_inventory,
    "desktop_protocol": build_desktop_protocol_inventory,
    "scenarios": build_scenarios_inventory,
    "probes": build_probes_inventory,
    "modules": build_modules_inventory,
    "m4_v0_v1": build_m4_inventory,
}


def build_all_inventories() -> dict[str, dict[str, Any]]:
    return {family: BUILDERS[family]() for family in INVENTORY_FAMILIES}


def validate_inventory_payload(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "family",
        "oracle_commit",
        "generator_version",
        "rows",
        "metadata",
    }
    allowed = required | {"aliases"}
    missing = required - set(value)
    extra = set(value) - allowed
    if missing or extra:
        raise SchemaError(
            f"inventory envelope differs: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    if value["schema_version"] != "m0-inventory-v1":
        raise SchemaError("unsupported inventory schema")
    if value["oracle_commit"] != ORACLE_COMMIT:
        raise SchemaError("inventory oracle commit drift")
    rows = value["rows"]
    if not isinstance(rows, list):
        raise SchemaError("inventory rows must be a list")
    ids = require_unique_ids(rows)
    if tuple(sorted(ids)) != ids:
        raise SchemaError(f"{value['family']} inventory rows are not sorted")
    for row in rows:
        for field in (
            "kind",
            "source_path",
            "source_symbol",
            "status",
            "owner_milestone",
        ):
            if not isinstance(row.get(field), str) or not row[field]:
                raise SchemaError(f"{row['id']}: missing {field}")
        source = REPO_ROOT / row["source_path"]
        if not source.is_file():
            raise SchemaError(f"{row['id']}: evidence path does not exist: {source}")


def validate_cross_references(inventories: Mapping[str, Mapping[str, Any]]) -> None:
    all_ids = {
        row["id"]
        for inventory in inventories.values()
        for row in inventory["rows"]
    }
    capability_names = {
        row["id"].removeprefix("capability.").replace("-", "_")
        for row in inventories["capabilities"]["rows"]
    }
    for row in inventories["capabilities"]["rows"]:
        for dependency in row["dependencies"]:
            if dependency.replace("-", "_") not in capability_names:
                raise SchemaError(
                    f"{row['id']}: unknown capability dependency {dependency}"
                )
    for row in inventories["policy"]["rows"]:
        if f"controller.seat.{slug(row['seat'])}" not in all_ids:
            raise SchemaError(f"{row['id']}: unknown seat {row['seat']}")
        if f"controller.group.{slug(row['decision_group'])}" not in all_ids:
            raise SchemaError(
                f"{row['id']}: unknown decision group {row['decision_group']}"
            )
    for vertical in inventories["m4_v0_v1"]["rows"]:
        for capability_group in ("required", "supported", "rejected"):
            for capability in vertical["capabilities"][capability_group]:
                capability_id = f"capability.{slug(capability)}"
                if capability_id not in all_ids:
                    raise SchemaError(
                        f"{vertical['id']}: unknown capability {capability}"
                    )
        for phase_id in vertical["phases"]:
            if phase_id not in all_ids:
                raise SchemaError(f"{vertical['id']}: unknown phase {phase_id}")
        for metric_id in vertical["metrics"]:
            if metric_id not in all_ids:
                raise SchemaError(f"{vertical['id']}: unknown metric {metric_id}")
        for invariant_id in vertical["invariants"]:
            if invariant_id not in all_ids:
                raise SchemaError(
                    f"{vertical['id']}: unknown invariant {invariant_id}"
                )


def contract_artifact_paths() -> list[Path]:
    roots = (
        REPO_ROOT / "schemas/m0/definitions",
        REPO_ROOT / "schemas/m0/manifests",
        REPO_ROOT / "schemas/m0/inventory",
    )
    return sorted(
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
    )


def build_hash_lock() -> dict[str, Any]:
    artifacts = []
    mapping: dict[str, str] = {}
    for path in contract_artifact_paths():
        relative = path.relative_to(REPO_ROOT).as_posix()
        digest = sha256_file(path)
        mapping[relative] = digest
        id_count = None
        if path.parent.name == "inventory" and path.suffix == ".json":
            import json

            value = json.loads(path.read_text(encoding="utf-8"))
            id_count = len(value.get("rows", []))
        artifacts.append(
            {
                "path": relative,
                "sha256": digest,
                "byte_count": path.stat().st_size,
                "id_count": id_count,
            }
        )
    return {
        "schema_version": "m0-hash-lock-v1",
        "oracle_commit": ORACLE_COMMIT,
        "generator_version": GENERATOR_VERSION,
        "artifacts": artifacts,
        "aggregate_sha256": aggregate_hash(mapping),
    }


def current_tracked_files() -> tuple[str, ...]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line for line in completed.stdout.splitlines() if line)
