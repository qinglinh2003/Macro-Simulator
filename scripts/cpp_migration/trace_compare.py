"""First-divergence reporting for canonical phase traces."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class TraceDivergence:
    record_index: int
    phase_id: str | None
    field_path: str
    expected: Any
    actual: Any
    comparison_rule: str = "exact_semantic"


def _first_value_difference(
    expected: Any,
    actual: Any,
    path: str = "$",
) -> tuple[str, Any, Any] | None:
    if type(expected) is not type(actual):
        return path, expected, actual
    if isinstance(expected, dict):
        keys = sorted(set(expected) | set(actual))
        for key in keys:
            child = f"{path}.{key}"
            if key not in expected:
                return child, None, actual[key]
            if key not in actual:
                return child, expected[key], None
            difference = _first_value_difference(expected[key], actual[key], child)
            if difference is not None:
                return difference
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}.length", len(expected), len(actual)
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            difference = _first_value_difference(left, right, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    if expected != actual:
        return path, expected, actual
    return None


def first_trace_divergence(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
) -> TraceDivergence | None:
    common = min(len(expected), len(actual))
    for index in range(common):
        difference = _first_value_difference(expected[index], actual[index])
        if difference is not None:
            path, left, right = difference
            return TraceDivergence(
                record_index=index,
                phase_id=expected[index].get("phase_id"),
                field_path=path,
                expected=left,
                actual=right,
            )
    if len(expected) != len(actual):
        phase_id = None
        if common < len(expected):
            phase_id = expected[common].get("phase_id")
        elif common < len(actual):
            phase_id = actual[common].get("phase_id")
        return TraceDivergence(
            record_index=common,
            phase_id=phase_id,
            field_path="$.record_count",
            expected=len(expected),
            actual=len(actual),
        )
    return None


def load_json_lines(path: Path) -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: trace record must be an object")
        records.append(value)
    return records
