"""Metric collector boundaries for reporting.

Collectors let reporting grow by subsystem without making callers know where
each metric block lives. The first collector wraps the legacy whole-economy
snapshot so Phase 9 can introduce the boundary without changing record keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Protocol


class MetricCollector(Protocol):
    def collect_metrics(self, state: Any) -> Dict[str, float]:
        ...


@dataclass(frozen=True)
class EconomyMetricCollector:
    compute: Callable[[Any], Dict[str, float]]

    def collect_metrics(self, state: Any) -> Dict[str, float]:
        return self.compute(state)


def collect_metric_groups(state: Any, collectors: Iterable[MetricCollector]) -> Dict[str, float]:
    record: Dict[str, float] = {}
    for collector in collectors:
        record.update(collector.collect_metrics(state))
    return record
