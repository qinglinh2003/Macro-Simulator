"""R8 native policy-package robustness experiments.

R8 consumes the accepted R1-R7 remediation artifacts.  It does not reuse the
old P5 estimates: the nine package definitions are rebuilt from current
Registry doses and executed against the repaired R5 crisis/state checkpoints.
Python schedules immutable native checkpoints and reduces maintained metrics;
all economic ticks execute in the C++ engine.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from macro_sim.diagnostics.policy_catalog import METRIC_MATERIALITY
from macro_sim.diagnostics.policy_combinations import (
    P5_SEVERITIES,
    _atomic_json,
    _canonical_hash,
    _run_seed,
    analyze_p5,
)
from macro_sim.diagnostics.policy_contracts import (
    PolicyCausalContract,
    build_contracts,
)
from macro_sim.diagnostics.policy_scenarios import (
    CRISIS_MANIFESTS,
    DEFAULT_P3_SEEDS,
)
from macro_sim import native_backend


R8_SCHEMA_VERSION = "policy-remediation-r8-v1"
R8_POPULATION = 100_000
R8_WORKERS = 8
R8_SEEDS = tuple(DEFAULT_P3_SEEDS)
R8_ACCEPTED_PHASES = tuple(f"R{index}" for index in range(1, 8))


@dataclass(frozen=True, slots=True)
class FactorDirection:
    lever: str
    treatment_label: str
    treatment_is_high: bool = True
    additional_high_actions: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class R8PackageBlueprint:
    package_id: str
    title: str
    scenario_id: str
    alternative_state: str
    factors: tuple[FactorDirection, ...]
    guardrails: tuple[tuple[str, int], ...]
    isolated_pair: tuple[str, str]


def _factor(
    lever: str,
    label: str,
    *,
    treatment_is_high: bool = True,
    additional_high_actions: tuple[tuple[str, Any], ...] = (),
) -> FactorDirection:
    return FactorDirection(
        lever=lever,
        treatment_label=label,
        treatment_is_high=treatment_is_high,
        additional_high_actions=additional_high_actions,
    )


R8_PACKAGE_BLUEPRINTS: tuple[R8PackageBlueprint, ...] = (
    R8PackageBlueprint(
        package_id="recession_response",
        title="Recession response",
        scenario_id="CR_DEMAND_RECESSION",
        alternative_state="BASE_SLACK",
        factors=(
            _factor("manual_policy_rate", "arm_1"),
            _factor("gov_consumption_share", "arm_4"),
            _factor("gov_deficit_target", "arm_4"),
            _factor("benefit_income_floor", "arm_2"),
            _factor("job_guarantee", "arm_1"),
        ),
        guardrails=(
            ("metric.economy.inflation", -1),
            ("metric.economy.gov_deficit_to_gdp", -1),
            ("metric.economy.gov_debt_to_gdp", -1),
            ("metric.economy.income_gini", -1),
        ),
        isolated_pair=("gov_consumption_share", "benefit_income_floor"),
    ),
    R8PackageBlueprint(
        package_id="anti_inflation",
        title="Anti-inflation response",
        scenario_id="CR_SUPPLY_STAGFLATION",
        alternative_state="BASE_TIGHT",
        factors=(
            _factor("inflation_target", "arm_3"),
            _factor("taylor_phi_pi", "arm_4"),
            _factor("gov_deficit_target", "arm_3"),
            _factor("energy_price_cap", "arm_1"),
            _factor("gov_investment_share", "arm_4"),
        ),
        guardrails=(
            ("metric.economy.unemployment_rate", -1),
            ("metric.economy.poverty_rate", -1),
            ("metric.economy.gov_deficit_to_gdp", -1),
            ("metric.economy.gov_debt_to_gdp", -1),
        ),
        isolated_pair=("inflation_target", "gov_deficit_target"),
    ),
    R8PackageBlueprint(
        package_id="bank_liquidity",
        title="Bank liquidity response",
        scenario_id="CR_BANK_RUN",
        alternative_state="BASE_NORMAL",
        factors=(
            _factor("omo", "arm_1", treatment_is_high=False),
            _factor("reserve_floor_frac", "arm_3"),
            _factor("lolr", "arm_1", treatment_is_high=False),
            _factor("deposit_rate_floor", "arm_2"),
            _factor("omo_reserve_target", "arm_4"),
        ),
        guardrails=(
            ("metric.economy.inflation", -1),
            ("metric.economy.gov_deficit_to_gdp", -1),
            ("metric.economy.gov_debt_to_gdp", -1),
            ("metric.economy.unemployment_rate", -1),
        ),
        isolated_pair=("omo", "lolr"),
    ),
    R8PackageBlueprint(
        package_id="bank_solvency",
        title="Bank solvency response",
        scenario_id="CR_BANK_RUN",
        alternative_state="STRUCT_LOW_PRODUCTIVITY",
        factors=(
            _factor("bank_capital_constraint", "arm_1", treatment_is_high=False),
            _factor("bank_leverage_cap", "arm_2"),
            _factor("bank_exposure_limit", "arm_3"),
            _factor("bank_migrate_on_failure", "arm_1", treatment_is_high=False),
            _factor("bank_resolution_fund", "arm_1", treatment_is_high=False),
        ),
        guardrails=(
            ("metric.economy.inflation", -1),
            ("metric.economy.gov_deficit_to_gdp", -1),
            ("metric.economy.gov_debt_to_gdp", -1),
            ("metric.economy.unemployment_rate", -1),
        ),
        isolated_pair=("bank_capital_constraint", "bank_resolution_fund"),
    ),
    R8PackageBlueprint(
        package_id="housing_cycle",
        title="Housing-cycle response",
        scenario_id="CR_HOUSING_BUST",
        alternative_state="STRUCT_HOUSING_SHORTAGE",
        factors=(
            _factor("mortgage_underwriting", "arm_1", treatment_is_high=False),
            _factor("mortgage_ltv_cap", "arm_3"),
            _factor("mortgage_dsti_cap", "arm_3"),
            _factor("mortgage_min_capital_ratio", "arm_4"),
            _factor("housing_permits", "arm_4"),
        ),
        guardrails=(
            ("metric.economy.inflation", -1),
            ("metric.economy.poverty_rate", -1),
            ("metric.economy.gov_deficit_to_gdp", -1),
            ("metric.economy.gov_debt_to_gdp", -1),
        ),
        isolated_pair=("mortgage_ltv_cap", "housing_permits"),
    ),
    R8PackageBlueprint(
        package_id="energy_emergency",
        title="Energy-emergency response",
        scenario_id="CR_ENERGY_EMBARGO",
        alternative_state="STRUCT_ENERGY_DEPENDENCE",
        factors=(
            _factor(
                "spr_target_units",
                "arm_2",
                additional_high_actions=(("spr_flow_cap", 1000.0),),
            ),
            _factor("energy_rationing", "arm_1"),
            _factor("energy_price_cap", "arm_1"),
            _factor("energy_cap_compensation", "arm_1"),
            _factor("energy_subsidy_rate", "arm_2"),
        ),
        guardrails=(
            ("metric.economy.unemployment_rate", -1),
            ("metric.economy.poverty_rate", -1),
            ("metric.economy.gov_deficit_to_gdp", -1),
            ("metric.economy.gov_debt_to_gdp", -1),
        ),
        isolated_pair=("energy_price_cap", "energy_cap_compensation"),
    ),
    R8PackageBlueprint(
        package_id="external_crisis",
        title="External and currency response",
        scenario_id="CR_PEG_PRESSURE",
        alternative_state="STRUCT_EXTERNAL_IMBALANCE",
        factors=(
            _factor("fx_regime", "arm_1"),
            _factor("peg_reserve_scale", "arm_4"),
            _factor("manual_policy_rate", "arm_2"),
            _factor("capital_control", "arm_2"),
            _factor("tariff", "arm_2"),
        ),
        guardrails=(
            ("metric.economy.inflation", -1),
            ("metric.economy.unemployment_rate", -1),
            ("metric.economy.poverty_rate", -1),
            ("metric.economy.gov_debt_to_gdp", -1),
        ),
        isolated_pair=("manual_policy_rate", "capital_control"),
    ),
    R8PackageBlueprint(
        package_id="poverty_and_employment",
        title="Poverty and employment response",
        scenario_id="CR_DEMAND_RECESSION",
        alternative_state="STRUCT_HIGH_POVERTY",
        factors=(
            _factor("tax_income_rate", "arm_3"),
            _factor("benefit_income_floor", "arm_2"),
            _factor("min_wage", "arm_2"),
            _factor("benefit_replacement", "arm_4"),
            _factor("job_guarantee", "arm_1"),
        ),
        guardrails=(
            ("metric.economy.real_output", 1),
            ("metric.economy.inflation", -1),
            ("metric.economy.gov_deficit_to_gdp", -1),
            ("metric.economy.gov_debt_to_gdp", -1),
        ),
        isolated_pair=("tax_income_rate", "benefit_income_floor"),
    ),
    R8PackageBlueprint(
        package_id="debt_sustainability",
        title="Sovereign-debt response",
        scenario_id="CR_SOVEREIGN_STRESS",
        alternative_state="STRUCT_POPULATION_AGING",
        factors=(
            _factor("gov_deficit_target", "arm_3"),
            _factor("bond_finance_frac", "arm_4"),
            _factor("bond_coupon", "arm_3"),
            _factor("bond_maturity", "arm_3"),
            _factor("omo", "arm_1", treatment_is_high=False),
        ),
        guardrails=(
            ("metric.economy.inflation", -1),
            ("metric.economy.unemployment_rate", -1),
            ("metric.economy.poverty_rate", -1),
            ("metric.economy.gov_deficit_to_gdp", -1),
        ),
        isolated_pair=("gov_deficit_target", "bond_maturity"),
    ),
)


def _contracts() -> dict[str, PolicyCausalContract]:
    return {contract.lever: contract for contract in build_contracts()}


def _assert_native_build(repo_root: Path) -> dict[str, str]:
    module = native_backend._load_native()
    loaded = Path(str(module.__file__)).resolve()
    expected_dir = (repo_root / "build/native/m11-release/native").resolve()
    if loaded.parent != expected_dir:
        raise RuntimeError(
            "R8 formal evidence must load the current worktree native extension; "
            f"loaded {loaded}, expected a module under {expected_dir}. "
            "Prefix the command with PYTHONPATH=build/native/m11-release/native:."
        )
    return {
        "extension_path": loaded.relative_to(repo_root.resolve()).as_posix(),
        "extension_sha256": hashlib.sha256(loaded.read_bytes()).hexdigest(),
    }


def _batch_actions(
    contract: PolicyCausalContract,
    label: str,
) -> dict[str, Any]:
    batch = next(
        (item for item in contract.treatment_batches if item.label == label),
        None,
    )
    if batch is None:
        raise ValueError(f"{contract.lever}: unknown treatment batch {label}")
    return dict(batch.actions)


def _factor_payload(
    spec: FactorDirection,
    contracts: Mapping[str, PolicyCausalContract],
) -> dict[str, Any]:
    contract = contracts[spec.lever]
    treatment = _batch_actions(contract, spec.treatment_label)
    for lever, value in spec.additional_high_actions:
        treatment[lever] = value
    names = set(treatment)
    baseline = {name: contracts[name].reference_baseline for name in names}
    high = treatment if spec.treatment_is_high else baseline
    low = baseline if spec.treatment_is_high else treatment

    allowed: dict[str, set[str]] = {}
    for name in names:
        source = contracts[name]
        values = [source.reference_baseline]
        values.extend(
            value
            for candidate in contracts.values()
            for batch in candidate.treatment_batches
            for action_name, value in batch.actions
            if action_name == name
        )
        allowed[name] = {_canonical_hash(value) for value in values}
    for side, actions in (("low", low), ("high", high)):
        for name, value in actions.items():
            if _canonical_hash(value) not in allowed[name]:
                raise ValueError(
                    f"{spec.lever}: {side} action {name}={value!r} is not a "
                    "current Registry baseline or preregistered treatment"
                )
    return {
        "factor_id": spec.lever,
        "dose_source": spec.treatment_label,
        "treatment_is_high": spec.treatment_is_high,
        "low_actions": [
            {"lever": name, "value": value} for name, value in sorted(low.items())
        ],
        "high_actions": [
            {"lever": name, "value": value} for name, value in sorted(high.items())
        ],
    }


def _scenario_outcomes(scenario_id: str) -> tuple[tuple[str, int], ...]:
    manifest = CRISIS_MANIFESTS[scenario_id]
    outcomes: dict[str, int] = {}
    for rule in (manifest.primary_damage, *manifest.propagation_rules):
        if rule.metric_id not in METRIC_MATERIALITY:
            continue
        sign = -1 if rule.direction == "increase" else 1
        previous = outcomes.setdefault(rule.metric_id, sign)
        if previous != sign:
            raise ValueError(
                f"{scenario_id}: conflicting directions for {rule.metric_id}"
            )
    if not outcomes:
        raise ValueError(f"{scenario_id}: no maintained primary outcomes")
    return tuple(sorted(outcomes.items()))


def _phase_hash(payload: Mapping[str, Any], phase: str) -> str:
    hashes = payload.get("hashes", {})
    key = f"{phase.lower()}_acceptance"
    value = hashes.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{phase}: missing acceptance hash")
    return value


def _component_evidence(
    lever: str,
    *,
    ledger_by_lever: Mapping[str, Mapping[str, Any]],
    r6_by_lever: Mapping[str, Mapping[str, Any]],
    r7_by_lever: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    ledger = ledger_by_lever[lever]
    if lever in r6_by_lever:
        classification = str(r6_by_lever[lever]["classification"])
        if classification == "removed":
            raise ValueError(f"{lever}: removed R6 lever cannot enter R8")
        result = {
            "source_phase": "R6",
            "classification": classification,
        }
        if lever in r7_by_lever:
            disposition = str(r7_by_lever[lever]["scale_disposition"])
            if disposition not in {
                "finite_size_confirmed",
                "finite_size_dependency_modeled",
            }:
                raise ValueError(f"{lever}: R7 scale evidence is not accepted")
            result["scale_disposition"] = disposition
        return result

    phases = [str(item) for item in ledger.get("phase_ids", ())]
    if phases:
        return {
            "source_phase": phases[-1],
            "classification": str(ledger["remediation_class"]),
        }
    if ledger.get("remediation_class") != "no_change_evidence":
        raise ValueError(f"{lever}: has neither accepted phase nor no-change ruling")
    return {
        "source_phase": "R0_no_change",
        "classification": "no_change",
    }


def build_r8_manifest(
    *,
    phase_acceptances: Mapping[str, Mapping[str, Any]],
    r5_p3_payload: Mapping[str, Any],
    remediation_ledger: Mapping[str, Any],
) -> dict[str, Any]:
    if set(phase_acceptances) != set(R8_ACCEPTED_PHASES):
        raise ValueError("R8 requires exactly the accepted R1-R7 payloads")
    phase_hashes: dict[str, str] = {}
    for phase in R8_ACCEPTED_PHASES:
        payload = phase_acceptances[phase]
        if payload.get("status") != "accepted":
            raise ValueError(f"{phase}: remediation phase is not accepted")
        phase_hashes[phase] = _phase_hash(payload, phase)

    if r5_p3_payload.get("status") not in {
        "accepted",
        "accepted_with_explicit_defects",
    }:
        raise ValueError("R5 crisis/state evidence is not accepted")
    if (
        phase_acceptances["R5"].get("p3_hashes", {}).get("p3_evidence")
        != r5_p3_payload.get("hashes", {}).get("p3_evidence")
    ):
        raise ValueError("R5 acceptance does not bind the supplied crisis evidence")
    crisis_reports = {
        str(item["scenario_id"]): item
        for item in r5_p3_payload["reports"]["crises"]
    }
    state_reports = {
        str(item["scenario_id"]): item
        for item in r5_p3_payload["reports"]["states"]
    }
    contracts = _contracts()
    ledger_by_lever = {
        str(item["lever"]): item for item in remediation_ledger["policies"]
    }
    r6_by_lever = {
        str(item["lever"]): item for item in phase_acceptances["R6"]["reports"]
    }
    r7_by_lever = {
        str(item["lever"]): item for item in phase_acceptances["R7"]["reports"]
    }
    if set(ledger_by_lever) != set(contracts):
        raise ValueError("R8 remediation ledger does not cover the Registry")

    packages: list[dict[str, Any]] = []
    for blueprint in R8_PACKAGE_BLUEPRINTS:
        if not crisis_reports.get(blueprint.scenario_id, {}).get("accepted"):
            raise ValueError(f"{blueprint.package_id}: crisis is not accepted")
        if not state_reports.get(blueprint.alternative_state, {}).get("accepted"):
            raise ValueError(f"{blueprint.package_id}: alternative state is not accepted")
        if len(blueprint.factors) != 5 or len({x.lever for x in blueprint.factors}) != 5:
            raise ValueError(f"{blueprint.package_id}: requires five unique factors")
        factors = [
            {
                **_factor_payload(spec, contracts),
                "accepted_component_evidence": _component_evidence(
                    spec.lever,
                    ledger_by_lever=ledger_by_lever,
                    r6_by_lever=r6_by_lever,
                    r7_by_lever=r7_by_lever,
                ),
            }
            for spec in blueprint.factors
        ]
        action_owners: dict[str, str] = {}
        for factor in factors:
            for side in ("low_actions", "high_actions"):
                for action in factor[side]:
                    action_lever = str(action["lever"])
                    owner = action_owners.setdefault(action_lever, factor["factor_id"])
                    if owner != factor["factor_id"]:
                        raise ValueError(
                            f"{blueprint.package_id}: {action_lever} belongs to "
                            f"both {owner} and {factor['factor_id']}"
                        )
        primary = _scenario_outcomes(blueprint.scenario_id)
        primary_metrics = {item[0] for item in primary}
        guardrails = tuple(
            item for item in blueprint.guardrails if item[0] not in primary_metrics
        )
        for metric_id, _sign in (*primary, *guardrails):
            if metric_id not in METRIC_MATERIALITY:
                raise ValueError(
                    f"{blueprint.package_id}: unknown materiality metric {metric_id}"
                )
        packages.append({
            "package_id": blueprint.package_id,
            "title": blueprint.title,
            "scenario_id": blueprint.scenario_id,
            "required_levers": [item.lever for item in blueprint.factors],
            "factor_levers": [item.lever for item in blueprint.factors],
            "alternative_state": blueprint.alternative_state,
            "primary_outcomes": [list(item) for item in primary],
            "guardrails": [list(item) for item in guardrails],
            "isolated_pair": list(blueprint.isolated_pair),
            "runnable": True,
            "blockers": [],
            "factors": factors,
            "design": {
                "kind": "regular_fraction",
                "runs": 16,
                "resolution": "IV",
                "component_ablations": 5,
                "isolated_pair_followup": list(blueprint.isolated_pair),
                "severities": list(P5_SEVERITIES),
                "withdrawal": True,
                "alternative_state": True,
            },
        })
    if len(packages) != 9 or len({item["package_id"] for item in packages}) != 9:
        raise ValueError("R8 must define exactly nine packages")
    return {
        "schema_version": R8_SCHEMA_VERSION,
        "upstream_acceptance_hashes": phase_hashes,
        "r5_p3_evidence_hash": r5_p3_payload["hashes"]["p3_evidence"],
        "remediation_ledger_hash": remediation_ledger["hashes"]["r0_acceptance"],
        "main_severity": "moderate",
        "robustness_severities": list(P5_SEVERITIES),
        "packages": packages,
    }


def _component_roles(report: Mapping[str, Any]) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {
        "essential": [],
        "supportive": [],
        "redundant": [],
        "harmful": [],
    }
    primary_signs = dict(report["primary_outcomes"])
    guardrail_signs = dict(report["guardrails"])
    main_effects = report["factorial_analysis"]["main_effects"]
    ablations = report["dominance"]["by_factor"]
    for factor in report["factors"]:
        factor_id = str(factor["factor_id"])
        harmful = any(
            bool(effect["material"])
            and float(effect["mean_difference"]) * int(
                primary_signs.get(metric_id, guardrail_signs.get(metric_id, 0))
            ) < 0.0
            and effect.get("confidence_low") is not None
            and effect.get("confidence_high") is not None
            and (
                float(effect["confidence_high"]) < 0.0
                if int(primary_signs.get(metric_id, guardrail_signs.get(metric_id, 0))) > 0
                else float(effect["confidence_low"]) > 0.0
            )
            for metric_id, effect in main_effects[factor_id].items()
        )
        essential = any(
            item.get("share_of_full_benefit") is not None
            and float(item["share_of_full_benefit"]) >= 0.20
            and item.get("confidence_low") is not None
            and float(item["confidence_low"]) > 0.0
            for item in ablations[factor_id].values()
        )
        material = any(bool(item["material"]) for item in main_effects[factor_id].values())
        if harmful:
            roles["harmful"].append(factor_id)
        elif essential:
            roles["essential"].append(factor_id)
        elif not material:
            roles["redundant"].append(factor_id)
        else:
            roles["supportive"].append(factor_id)
    return roles


def _gate_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "primary_benefit": bool(report["full_package"]["supported_primary_metrics"]),
        "guardrails": not bool(
            report["full_package"]["primary_harms"]
            or report["full_package"]["guardrail_failures"]
        ),
        "withdrawal": bool(report["withdrawal"]["passed"]),
        "severity": bool(report["severity_robustness"]["passed"]),
        "alternative_state": bool(report["alternative_state_robustness"]["passed"]),
        "factorial_complete": (
            len(report["factorial_analysis"]["main_effects"]) == 5
            and len(report["factorial_analysis"]["two_factor_interactions"]) == 10
        ),
        "ablations_complete": len(report["dominance"]["by_factor"]) == 5,
    }


def run_r8(
    *,
    artifact_dir: Path,
    phase_acceptances: Mapping[str, Mapping[str, Any]],
    r5_p3_payload: Mapping[str, Any],
    remediation_ledger: Mapping[str, Any],
    source_revision: str,
    repo_root: Path,
    seeds: Sequence[int] = R8_SEEDS,
    population: int = R8_POPULATION,
    workers: int = R8_WORKERS,
    jobs: int = 4,
    resume: bool = True,
    progress: Callable[[int, str, str, bool], None] | None = None,
) -> dict[str, Any]:
    if tuple(seeds) != R8_SEEDS:
        raise ValueError("R8 requires the eight frozen matched seeds")
    if population != R8_POPULATION:
        raise ValueError("R8 acceptance requires 100,000 persons per country")
    if workers != R8_WORKERS:
        raise ValueError("R8 acceptance requires exactly eight native workers")
    if jobs < 1:
        raise ValueError("R8 concurrent jobs must be positive")
    native_build = _assert_native_build(repo_root)
    manifest = build_r8_manifest(
        phase_acceptances=phase_acceptances,
        r5_p3_payload=r5_p3_payload,
        remediation_ledger=remediation_ledger,
    )
    seed_runs: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(jobs, len(seeds))) as executor:
        futures = {
            executor.submit(
                _run_seed,
                seed=seed,
                runnable_packages=manifest["packages"],
                manifest_payload=manifest,
                p3_payload=r5_p3_payload,
                population=population,
                workers=workers,
                source_revision=source_revision,
                artifact_dir=artifact_dir,
                resume=resume,
                progress=progress,
                execution_schema_version=R8_SCHEMA_VERSION,
                require_frozen_checkpoints=False,
            ): seed
            for seed in seeds
        }
        for future in as_completed(futures):
            seed_runs.append(future.result())
    seed_runs.sort(key=lambda item: int(item["seed"]))
    checkpoint_identity = {
        "crisis_current_matches": sum(
            bool(value)
            for item in seed_runs
            for value in item["crisis_checkpoint_matches_r5"].values()
        ),
        "crisis_current_mismatches": sum(
            not bool(value)
            for item in seed_runs
            for value in item["crisis_checkpoint_matches_r5"].values()
        ),
        "state_current_matches": sum(
            bool(value)
            for item in seed_runs
            for value in item["state_checkpoint_matches_r5"].values()
        ),
        "state_current_mismatches": sum(
            not bool(value)
            for item in seed_runs
            for value in item["state_checkpoint_matches_r5"].values()
        ),
    }
    reports, errors = analyze_p5(
        packages=manifest["packages"],
        seeds=seeds,
        artifact_dir=artifact_dir,
    )
    for report in reports:
        if report.get("invalid_branches"):
            continue
        report["component_roles"] = _component_roles(report)
        report["gate_summary"] = _gate_summary(report)
    if any(
        not report.get("gate_summary", {}).get("factorial_complete")
        or not report.get("gate_summary", {}).get("ablations_complete")
        for report in reports
    ):
        errors.append("R8 did not complete every factorial and ablation gate")
    dispositions: dict[str, int] = {}
    for report in reports:
        name = str(report["disposition"])
        dispositions[name] = dispositions.get(name, 0) + 1
    evidence_hash = _canonical_hash(reports)
    acceptance_core = {
        "schema_version": R8_SCHEMA_VERSION,
        "manifest_hash": _canonical_hash(manifest),
        "evidence_hash": evidence_hash,
        "dispositions": dispositions,
        "errors": errors,
    }
    payload = {
        "schema_version": R8_SCHEMA_VERSION,
        "status": "accepted" if not errors else "incomplete",
        "source_revision": source_revision,
        "protocol": {
            "population_per_country": population,
            "seeds": list(seeds),
            "native_workers": workers,
            "concurrent_jobs": jobs,
            "legacy_python_simulator_used": False,
            "native_build": native_build,
            "r5_checkpoint_policy": (
                "record_expected_and_current_identity; branch_from_current_R8_source"
            ),
        },
        "manifest": manifest,
        "seed_runs": seed_runs,
        "counts": {
            "packages": len(reports),
            "executed_native_branches": sum(item["executed"] for item in seed_runs),
            "cache_hits": sum(item["cache_hits"] for item in seed_runs),
            "dispositions": dispositions,
            "checkpoint_identity": checkpoint_identity,
        },
        "reports": reports,
        "errors": errors,
        "hashes": {
            "r8_manifest": _canonical_hash(manifest),
            "r8_evidence": evidence_hash,
            "r8_acceptance": _canonical_hash(acceptance_core),
        },
    }
    _atomic_json(artifact_dir / "r8_report.json", payload)
    return payload


def reduce_r8_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    reports = []
    for report in payload["reports"]:
        reports.append({
            "package_id": report["package_id"],
            "scenario_id": report["scenario_id"],
            "alternative_state": report["alternative_state"],
            "disposition": report["disposition"],
            "reason": report["reason"],
            "gate_summary": report.get("gate_summary"),
            "component_roles": report.get("component_roles"),
            "supported_primary_metrics": report.get("full_package", {}).get(
                "supported_primary_metrics", []
            ),
            "primary_harms": report.get("full_package", {}).get("primary_harms", []),
            "guardrail_failures": report.get("full_package", {}).get(
                "guardrail_failures", []
            ),
            "dominant_components": report.get("dominance", {}).get(
                "dominant_components", []
            ),
            "isolated_pair": report.get("isolated_pair_followup", {}).get("pair", []),
        })
    return {
        "schema_version": R8_SCHEMA_VERSION,
        "status": payload["status"],
        "source_revision": payload["source_revision"],
        "protocol": payload["protocol"],
        "counts": payload["counts"],
        "upstream_acceptance_hashes": payload["manifest"][
            "upstream_acceptance_hashes"
        ],
        "reports": reports,
        "errors": payload["errors"],
        "hashes": payload["hashes"],
    }


def build_r8_acceptance(evidence: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    reports = list(evidence.get("reports", ()))
    if evidence.get("status") != "accepted":
        errors.append("R8 execution evidence is not accepted")
    if len(reports) != 9 or len({item.get("package_id") for item in reports}) != 9:
        errors.append("R8 evidence does not exactly cover nine packages")
    for report in reports:
        gates = report.get("gate_summary") or {}
        if not gates.get("factorial_complete") or not gates.get("ablations_complete"):
            errors.append(
                f"{report.get('package_id')}: factorial or ablation evidence is incomplete"
            )
        roles = report.get("component_roles") or {}
        classified = [
            lever
            for role in ("essential", "supportive", "redundant", "harmful")
            for lever in roles.get(role, ())
        ]
        if len(classified) != 5 or len(set(classified)) != 5:
            errors.append(
                f"{report.get('package_id')}: component roles do not cover five factors"
            )
    evidence_hash = _canonical_hash(evidence)
    gate_counts = {
        key: sum(
            bool((report.get("gate_summary") or {}).get(key)) for report in reports
        )
        for key in (
            "primary_benefit",
            "guardrails",
            "withdrawal",
            "severity",
            "alternative_state",
            "factorial_complete",
            "ablations_complete",
        )
    }
    role_counts = {
        role: sum(
            len((report.get("component_roles") or {}).get(role, ()))
            for report in reports
        )
        for role in ("essential", "supportive", "redundant", "harmful")
    }
    core = {
        "schema_version": R8_SCHEMA_VERSION,
        "evidence_hash": evidence_hash,
        "upstream_acceptance_hashes": evidence.get("upstream_acceptance_hashes"),
        "gate_counts": gate_counts,
        "component_role_counts": role_counts,
        "errors": errors,
    }
    return {
        **core,
        "status": "accepted" if not errors else "rejected",
        "source_revision": evidence.get("source_revision"),
        "counts": evidence.get("counts"),
        "protocol": evidence.get("protocol"),
        "reports": reports,
        "hashes": {
            "r8_evidence": evidence_hash,
            "r8_acceptance": _canonical_hash(core),
        },
    }


def validate_r8_acceptance(
    evidence: Mapping[str, Any],
    acceptance: Mapping[str, Any],
) -> list[str]:
    expected = build_r8_acceptance(evidence)
    if dict(acceptance) != expected:
        return ["committed R8 acceptance does not reproduce"]
    return []


def render_r8_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Policy remediation R8 acceptance",
        "",
        f"- Status: `{payload['status']}`",
        f"- Packages: {payload['counts']['packages']}",
        f"- Native branches: {payload['counts']['executed_native_branches']}",
        f"- Cache hits: {payload['counts']['cache_hits']}",
        f"- Population per country: {payload['protocol']['population_per_country']:,}",
        f"- Matched seeds: {len(payload['protocol']['seeds'])}",
        f"- Native workers per session: {payload['protocol']['native_workers']}",
        "- Legacy Python simulator used: no",
        f"- Acceptance hash: `{payload['hashes']['r8_acceptance']}`",
        "",
        "## Package ledger",
        "",
        "| Package | Crisis | Disposition | Primary | Guardrail | Withdrawal | Severity | Alternative state |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for report in payload["reports"]:
        gates = report.get("gate_summary", {})
        mark = lambda key: "pass" if gates.get(key) else "fail"  # noqa: E731
        lines.append(
            f"| `{report['package_id']}` | `{report['scenario_id']}` | "
            f"`{report['disposition']}` | {mark('primary_benefit')} | "
            f"{mark('guardrails')} | {mark('withdrawal')} | {mark('severity')} | "
            f"{mark('alternative_state')} |"
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "R8_PACKAGE_BLUEPRINTS",
    "R8_SCHEMA_VERSION",
    "build_r8_acceptance",
    "build_r8_manifest",
    "reduce_r8_evidence",
    "render_r8_markdown",
    "run_r8",
    "validate_r8_acceptance",
]
