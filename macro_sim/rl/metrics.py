"""Dependency-light statistical gates for reproducible policy benchmarks."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class _FrozenObjectMapping(Mapping[str, Any]):
    """Pickle-safe immutable mapping for non-JSON statistical objects."""

    _items: tuple[tuple[str, Any], ...]

    def __init__(self, values: Mapping[str, Any]):
        object.__setattr__(self, "_items", tuple(sorted(values.items())))

    def __getitem__(self, key: str) -> Any:
        for item_key, value in self._items:
            if item_key == key:
                return value
        raise KeyError(key)

    def __iter__(self):
        return (key for key, _value in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __reduce__(self):
        return (type(self), (dict(self._items),))


def _probability(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    value = float(value)
    if not 0.0 < value < 1.0:
        raise ValueError(f"{name} must be strictly between zero and one")
    return value


def _finite_values(values: Sequence[float]) -> np.ndarray:
    raw = tuple(values)
    if any(isinstance(value, (bool, np.bool_)) for value in raw):
        raise ValueError("metric values must be numeric and non-boolean")
    try:
        result = np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("metric values must be numeric") from exc
    if result.ndim != 1 or result.size == 0:
        raise ValueError("metric values must be a non-empty one-dimensional sequence")
    if not np.all(np.isfinite(result)):
        raise ValueError("metric values must all be finite")
    return result


@dataclass(frozen=True)
class ConfidenceInterval:
    level: float
    lower: float
    upper: float
    method: str
    resamples: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "lower": self.lower,
            "method": self.method,
            "resamples": self.resamples,
            "upper": self.upper,
        }


def bootstrap_mean_confidence_interval(
    values: Sequence[float],
    *,
    confidence_level: float = 0.95,
    resamples: int = 10_000,
    seed: int = 0,
) -> ConfidenceInterval:
    """Return a deterministic percentile-bootstrap CI for the sample mean.

    Sampling is chunked so evaluation over many seeds does not allocate the full
    ``resamples x episodes`` index matrix.  A one-observation sample produces a
    correctly labelled degenerate interval; superiority rules separately enforce
    a scientifically meaningful minimum pair count.
    """

    values_array = _finite_values(values)
    confidence_level = _probability("confidence_level", confidence_level)
    if isinstance(resamples, bool) or not isinstance(resamples, int):
        raise TypeError("resamples must be an integer")
    if resamples < 100:
        raise ValueError("resamples must be at least 100")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise TypeError("bootstrap seed must be an integer")
    seed = int(seed)
    if seed < 0:
        raise ValueError("bootstrap seed must be non-negative")
    if values_array.size == 1:
        value = float(values_array[0])
        return ConfidenceInterval(
            confidence_level, value, value, "percentile_bootstrap", resamples,
        )
    rng = np.random.default_rng(seed)
    means = np.empty(resamples, dtype=np.float64)
    chunk_size = min(2_048, resamples)
    for start in range(0, resamples, chunk_size):
        stop = min(start + chunk_size, resamples)
        indices = rng.integers(
            0, values_array.size, size=(stop - start, values_array.size),
        )
        means[start:stop] = values_array[indices].mean(axis=1)
    alpha = 1.0 - confidence_level
    lower, upper = np.quantile(means, (alpha / 2.0, 1.0 - alpha / 2.0))
    return ConfidenceInterval(
        confidence_level,
        float(lower),
        float(upper),
        "percentile_bootstrap",
        resamples,
    )


@dataclass(frozen=True)
class MetricSummary:
    count: int
    mean: float
    standard_deviation: float
    standard_error: float
    median: float
    minimum: float
    maximum: float
    confidence_interval: ConfidenceInterval

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence_interval": self.confidence_interval.to_dict(),
            "count": self.count,
            "maximum": self.maximum,
            "mean": self.mean,
            "median": self.median,
            "minimum": self.minimum,
            "standard_deviation": self.standard_deviation,
            "standard_error": self.standard_error,
        }


def summarize_metric(
    values: Sequence[float],
    *,
    confidence_level: float = 0.95,
    resamples: int = 10_000,
    seed: int = 0,
) -> MetricSummary:
    data = _finite_values(values)
    count = int(data.size)
    standard_deviation = float(np.std(data, ddof=1)) if count > 1 else 0.0
    return MetricSummary(
        count=count,
        mean=float(np.mean(data)),
        standard_deviation=standard_deviation,
        standard_error=standard_deviation / math.sqrt(count),
        median=float(np.median(data)),
        minimum=float(np.min(data)),
        maximum=float(np.max(data)),
        confidence_interval=bootstrap_mean_confidence_interval(
            data,
            confidence_level=confidence_level,
            resamples=resamples,
            seed=seed,
        ),
    )


@dataclass(frozen=True)
class SuperiorityRule:
    """Pre-registered definition of "better than a baseline".

    A comparison passes only when all of the following hold:

    * at least ``minimum_pairs`` identical evaluation seeds are present;
    * the paired bootstrap CI lower bound is *strictly greater* than
      ``minimum_effect``;
    * the candidate wins at least ``minimum_win_rate`` of paired seeds.

    When several baselines are required, ``familywise_confidence`` applies a
    Bonferroni correction and the candidate must pass every comparison.  This is
    deliberately stricter than merely observing a larger sample mean.
    """

    confidence_level: float = 0.95
    minimum_effect: float = 0.0
    minimum_win_rate: float = 0.5
    minimum_pairs: int = 20
    bootstrap_resamples: int = 10_000
    bootstrap_seed: int = 0
    familywise_confidence: bool = True

    def __post_init__(self) -> None:
        _probability("confidence_level", self.confidence_level)
        if isinstance(self.minimum_effect, bool) or not isinstance(
            self.minimum_effect, (int, float),
        ) or not math.isfinite(float(self.minimum_effect)):
            raise ValueError("minimum_effect must be finite")
        if isinstance(self.minimum_win_rate, bool) or not isinstance(
            self.minimum_win_rate, (int, float),
        ) or not math.isfinite(float(self.minimum_win_rate)):
            raise ValueError("minimum_win_rate must be finite")
        if not 0.0 <= float(self.minimum_win_rate) <= 1.0:
            raise ValueError("minimum_win_rate must be between zero and one")
        if isinstance(self.minimum_pairs, bool) or not isinstance(self.minimum_pairs, int):
            raise TypeError("minimum_pairs must be an integer")
        if self.minimum_pairs < 2:
            raise ValueError("minimum_pairs must be at least two")
        if isinstance(self.bootstrap_resamples, bool) \
                or not isinstance(self.bootstrap_resamples, int):
            raise TypeError("bootstrap_resamples must be an integer")
        if self.bootstrap_resamples < 100:
            raise ValueError("bootstrap_resamples must be at least 100")
        if isinstance(self.bootstrap_seed, bool) \
                or not isinstance(self.bootstrap_seed, int):
            raise TypeError("bootstrap_seed must be an integer")
        if self.bootstrap_seed < 0:
            raise ValueError("bootstrap_seed must be non-negative")


@dataclass(frozen=True)
class PairedComparison:
    candidate: str
    baseline: str
    metric: str
    paired_seeds: tuple[int, ...]
    difference_summary: MetricSummary
    win_rate: float
    tie_rate: float
    loss_rate: float
    minimum_effect: float
    minimum_win_rate: float
    minimum_pairs: int
    passed: bool
    failure_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline,
            "candidate": self.candidate,
            "difference_summary": self.difference_summary.to_dict(),
            "failure_reasons": list(self.failure_reasons),
            "loss_rate": self.loss_rate,
            "metric": self.metric,
            "minimum_effect": self.minimum_effect,
            "minimum_pairs": self.minimum_pairs,
            "minimum_win_rate": self.minimum_win_rate,
            "paired_seeds": list(self.paired_seeds),
            "passed": self.passed,
            "tie_rate": self.tie_rate,
            "win_rate": self.win_rate,
        }


def paired_comparison(
    candidate_scores: Mapping[int, float],
    baseline_scores: Mapping[int, float],
    *,
    candidate_name: str,
    baseline_name: str,
    metric: str,
    rule: SuperiorityRule,
    confidence_level: float | None = None,
    bootstrap_seed: int | None = None,
) -> PairedComparison:
    """Compare exact common-random-number pairs; never silently drop seeds."""

    candidate_keys = set(candidate_scores)
    baseline_keys = set(baseline_scores)
    if any(
        isinstance(seed, (bool, np.bool_))
        or not isinstance(seed, (int, np.integer))
        or int(seed) < 0
        for seed in candidate_keys | baseline_keys
    ):
        raise ValueError("paired comparison keys must be non-negative integer seeds")
    if candidate_keys != baseline_keys:
        missing_candidate = sorted(baseline_keys - candidate_keys)
        missing_baseline = sorted(candidate_keys - baseline_keys)
        raise ValueError(
            "paired comparison requires identical seeds; "
            f"missing candidate={missing_candidate}, missing baseline={missing_baseline}"
        )
    if not candidate_keys:
        raise ValueError("paired comparison requires at least one seed")
    paired_seeds = tuple(sorted(candidate_keys))
    candidate_values = _finite_values([
        candidate_scores[seed] for seed in paired_seeds
    ])
    baseline_values = _finite_values([
        baseline_scores[seed] for seed in paired_seeds
    ])
    differences = candidate_values - baseline_values
    level = rule.confidence_level if confidence_level is None else confidence_level
    seed = rule.bootstrap_seed if bootstrap_seed is None else bootstrap_seed
    summary = summarize_metric(
        differences,
        confidence_level=level,
        resamples=rule.bootstrap_resamples,
        seed=seed,
    )
    tolerance = np.finfo(np.float64).eps * np.maximum(
        1.0,
        np.maximum(np.abs(candidate_values), np.abs(baseline_values)),
    )
    wins = int(np.sum(differences > tolerance))
    losses = int(np.sum(differences < -tolerance))
    ties = len(paired_seeds) - wins - losses
    count = len(paired_seeds)
    win_rate = wins / count
    reasons: list[str] = []
    if count < rule.minimum_pairs:
        reasons.append("insufficient_pairs")
    if summary.confidence_interval.lower <= float(rule.minimum_effect):
        reasons.append("confidence_bound_not_above_minimum_effect")
    if win_rate < float(rule.minimum_win_rate):
        reasons.append("win_rate_below_minimum")
    return PairedComparison(
        candidate=candidate_name,
        baseline=baseline_name,
        metric=metric,
        paired_seeds=paired_seeds,
        difference_summary=summary,
        win_rate=win_rate,
        tie_rate=ties / count,
        loss_rate=losses / count,
        minimum_effect=float(rule.minimum_effect),
        minimum_win_rate=float(rule.minimum_win_rate),
        minimum_pairs=rule.minimum_pairs,
        passed=not reasons,
        failure_reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class BenchmarkVerdict:
    candidate: str
    metric: str
    comparisons: Mapping[str, PairedComparison]
    passed: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "comparisons",
            _FrozenObjectMapping(self.comparisons),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "comparisons": {
                name: comparison.to_dict()
                for name, comparison in self.comparisons.items()
            },
            "metric": self.metric,
            "passed": self.passed,
        }


def judge_against_baselines(
    candidate_scores: Mapping[int, float],
    baseline_scores: Mapping[str, Mapping[int, float]],
    *,
    candidate_name: str,
    metric: str,
    rule: SuperiorityRule,
) -> BenchmarkVerdict:
    if not baseline_scores:
        raise ValueError("at least one baseline is required")
    baseline_count = len(baseline_scores)
    confidence = rule.confidence_level
    if rule.familywise_confidence and baseline_count > 1:
        confidence = 1.0 - (1.0 - confidence) / baseline_count
    comparisons: dict[str, PairedComparison] = {}
    for index, (name, scores) in enumerate(sorted(baseline_scores.items())):
        comparisons[name] = paired_comparison(
            candidate_scores,
            scores,
            candidate_name=candidate_name,
            baseline_name=name,
            metric=metric,
            rule=rule,
            confidence_level=confidence,
            bootstrap_seed=rule.bootstrap_seed + index,
        )
    return BenchmarkVerdict(
        candidate=candidate_name,
        metric=metric,
        comparisons=comparisons,
        passed=all(item.passed for item in comparisons.values()),
    )
