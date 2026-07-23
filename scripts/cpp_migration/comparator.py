"""Strict registered comparisons for Python/native migration artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
import math
from pathlib import Path
import re
from statistics import NormalDist
from typing import Any

import yaml

from .common import REPO_ROOT, SchemaError, canonical_json_bytes, sha256_bytes


MANIFEST_ROOT = REPO_ROOT / "schemas/m0/manifests"


@dataclass(frozen=True, slots=True)
class ToleranceRule:
    id: str
    pattern: str
    comparison_class: str
    absolute_tolerance: float
    relative_tolerance: float
    non_finite_policy: str


@dataclass(frozen=True, slots=True)
class ComparisonFailure:
    path: str
    reason: str
    rule_id: str | None
    expected: Any
    actual: Any


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SchemaError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SchemaError(f"{path}: document root must be an object")
    return value


def load_tolerance_registry(
    path: Path = MANIFEST_ROOT / "tolerances.yaml",
) -> tuple[ToleranceRule, ...]:
    raw = _load_yaml(path)
    if raw.get("schema_version") != "m0-tolerance-registry-v1":
        raise SchemaError("unsupported tolerance registry schema")
    result = []
    seen = set()
    for row in raw.get("rows", []):
        if row["id"] in seen:
            raise SchemaError(f"duplicate tolerance ID {row['id']}")
        seen.add(row["id"])
        if row["comparison_class"] not in {
            "exact_semantic",
            "absolute_relative_numeric",
            "event_window",
        }:
            raise SchemaError(f"{row['id']}: unsupported comparison class")
        for evidence_field in ("evidence",):
            if not (REPO_ROOT / row[evidence_field]).is_file():
                raise SchemaError(f"{row['id']}: missing evidence")
        result.append(
            ToleranceRule(
                id=row["id"],
                pattern=row["pattern"],
                comparison_class=row["comparison_class"],
                absolute_tolerance=float(row["absolute_tolerance"]),
                relative_tolerance=float(row["relative_tolerance"]),
                non_finite_policy=row["non_finite_policy"],
            )
        )
    return tuple(result)


def _pattern_matches(pattern: str, path: str) -> bool:
    expression = re.escape(pattern).replace(r"\*", ".*")
    return re.fullmatch(expression, path) is not None


def resolve_tolerance(
    path: str,
    registry: tuple[ToleranceRule, ...],
) -> ToleranceRule | None:
    matches = [rule for rule in registry if _pattern_matches(rule.pattern, path)]
    if not matches:
        return None
    matches.sort(
        key=lambda rule: (rule.pattern.count("*"), -len(rule.pattern), rule.id)
    )
    return matches[0]


def compare_numeric(
    path: str,
    expected: int | float,
    actual: int | float,
    registry: tuple[ToleranceRule, ...],
) -> ComparisonFailure | None:
    rule = resolve_tolerance(path, registry)
    if rule is None:
        return ComparisonFailure(path, "unknown_tolerance", None, expected, actual)
    left = float(expected)
    right = float(actual)
    if not math.isfinite(left) or not math.isfinite(right):
        if rule.non_finite_policy == "reject":
            return ComparisonFailure(
                path,
                "non_finite",
                rule.id,
                expected,
                actual,
            )
    if rule.comparison_class == "exact_semantic":
        matched = type(expected) is type(actual) and expected == actual
    elif rule.comparison_class == "event_window":
        matched = abs(left - right) <= rule.absolute_tolerance
    else:
        matched = math.isclose(
            left,
            right,
            rel_tol=rule.relative_tolerance,
            abs_tol=rule.absolute_tolerance,
        )
    if matched:
        return None
    return ComparisonFailure(path, "numeric_mismatch", rule.id, expected, actual)


def first_artifact_difference(
    expected: Any,
    actual: Any,
    registry: tuple[ToleranceRule, ...],
    path: str = "$",
) -> ComparisonFailure | None:
    if isinstance(expected, bool) or isinstance(actual, bool):
        if type(expected) is not type(actual) or expected != actual:
            return ComparisonFailure(path, "exact_mismatch", None, expected, actual)
        return None
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return compare_numeric(path, expected, actual, registry)
    if type(expected) is not type(actual):
        return ComparisonFailure(path, "type_mismatch", None, expected, actual)
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            child = f"{path}.{key}"
            if key not in expected or key not in actual:
                return ComparisonFailure(
                    child,
                    "missing_field",
                    None,
                    expected.get(key),
                    actual.get(key),
                )
            failure = first_artifact_difference(
                expected[key],
                actual[key],
                registry,
                child,
            )
            if failure is not None:
                return failure
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return ComparisonFailure(
                f"{path}.length",
                "length_mismatch",
                None,
                len(expected),
                len(actual),
            )
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            failure = first_artifact_difference(
                left,
                right,
                registry,
                f"{path}[{index}]",
            )
            if failure is not None:
                return failure
        return None
    if expected != actual:
        return ComparisonFailure(path, "exact_mismatch", None, expected, actual)
    return None


def run_comparator_self_test(path: Path) -> None:
    raw = _load_yaml(path)
    if raw.get("schema_version") != "m0-comparator-cases-v1":
        raise SchemaError("unsupported comparator case schema")
    registry = load_tolerance_registry()
    for case in raw.get("cases", []):
        failure = compare_numeric(
            case["path"],
            case["expected"],
            case["actual"],
            registry,
        )
        outcome = "pass" if failure is None else "fail"
        if outcome != case["outcome"]:
            raise SchemaError(
                f"{case['id']}: expected {case['outcome']}, observed {outcome}"
            )
        reason = None if failure is None else failure.reason
        if reason != case["failure_reason"]:
            raise SchemaError(
                f"{case['id']}: expected reason {case['failure_reason']}, "
                f"observed {reason}"
            )


def validate_statistical_registry(
    path: Path = MANIFEST_ROOT / "statistical_panels.yaml",
) -> dict[str, Any]:
    raw = _load_yaml(path)
    if raw.get("schema_version") != "m0-statistical-panels-v1":
        raise SchemaError("unsupported statistical panel schema")
    if raw.get("family_wise_alpha") != 0.05 or raw.get("correction") != "holm":
        raise SchemaError("statistical panels must use alpha 0.05 with Holm correction")
    ids = set()
    for row in raw.get("rows", []):
        if row["id"] in ids:
            raise SchemaError(f"duplicate statistical panel {row['id']}")
        ids.add(row["id"])
        seeds = row["seeds"]
        if len(seeds) != len(set(seeds)) or len(seeds) < 8:
            raise SchemaError(f"{row['id']}: seed panel is not frozen or large enough")
        if row["decision_procedure"] != "tost":
            raise SchemaError(f"{row['id']}: equivalence requires TOST")
        standard_error = row["pilot_standard_deviation"] / math.sqrt(len(seeds))
        critical = NormalDist().inv_cdf(1.0 - raw["family_wise_alpha"])
        computed_power = NormalDist().cdf(
            row["equivalence_margin"] / standard_error - critical
        )
        if computed_power < 0.8:
            raise SchemaError(f"{row['id']}: computed power is below 80%")
        if abs(computed_power - row["power"]) > 0.01:
            raise SchemaError(f"{row['id']}: declared power does not match pilot")
        if not (REPO_ROOT / row["evidence"]).is_file():
            raise SchemaError(f"{row['id']}: missing pilot evidence")
    return raw


def validate_semantic_panels(
    path: Path = MANIFEST_ROOT / "semantic_panels.yaml",
) -> dict[str, Any]:
    raw = _load_yaml(path)
    if raw.get("schema_version") != "m0-semantic-panels-v1":
        raise SchemaError("unsupported semantic panel schema")
    invariant_ids = {
        row["id"]
        for row in _load_yaml(MANIFEST_ROOT / "invariants.yaml")["rows"]
    }
    for row in raw.get("rows", []):
        if row["expected_sign"] not in {"positive", "negative", "nonpositive", "nonnegative"}:
            raise SchemaError(f"{row['id']}: invalid expected sign")
        if row["peak_window_ticks"][0] > row["peak_window_ticks"][1]:
            raise SchemaError(f"{row['id']}: invalid peak window")
        if row["recovery_window_ticks"][0] > row["recovery_window_ticks"][1]:
            raise SchemaError(f"{row['id']}: invalid recovery window")
        if not set(row["identity_invariants"]) <= invariant_ids:
            raise SchemaError(f"{row['id']}: unknown invariant")
        if not (REPO_ROOT / row["python_evidence"]).is_file():
            raise SchemaError(f"{row['id']}: missing Python oracle evidence")
    return raw


VOLATILE_REPEATABILITY_FIELDS = {
    "captured_at_utc",
    "duration_ns",
    "environment",
    "peak_rss_bytes",
    "raw_samples_ns",
    "statistics_ns",
    "stdout",
    "stderr",
}


def normalized_repeatability_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalized_repeatability_value(item)
            for key, item in sorted(value.items())
            if key not in VOLATILE_REPEATABILITY_FIELDS
        }
    if isinstance(value, list):
        return [normalized_repeatability_value(item) for item in value]
    return value


def repeatability_tree_digest(root: Path) -> str:
    if not root.is_dir():
        raise SchemaError(f"repeatability root does not exist: {root}")
    entries = {}
    import json

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
            payload = canonical_json_bytes(normalized_repeatability_value(value))
        else:
            payload = path.read_bytes()
        entries[relative] = sha256_bytes(payload)
    return sha256_bytes(canonical_json_bytes(entries))
