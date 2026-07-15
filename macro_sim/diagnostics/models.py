"""Serializable records shared by the diagnostic runner and report generator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class Intervention:
    """A temporary, single-channel intervention applied during a paired run."""

    kind: str
    start_tick: int
    end_tick: int | None = None
    value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunSpec:
    """One independently reproducible simulation job."""

    name: str
    seed: int
    ticks: int
    population: int
    n_firms_c: int
    n_firms_k: int
    n_banks: int
    scenario: str = "baseline"
    pair_id: str | None = None
    intervention: Intervention | None = None
    overrides: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass(frozen=True)
class Finding:
    """One machine-readable diagnosis with its evidentiary and epistemic status."""

    issue_id: str
    severity: str
    confidence: str
    category: str
    claim: str
    evidence: dict[str, Any] = field(default_factory=dict)
    suspected_mechanisms: tuple[str, ...] = ()
    requested_probes: tuple[str, ...] = ()
    recommendation: str = ""
    measurement_status: str = "valid"
    detector: str = ""

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY_ORDER:
            raise ValueError(f"unknown finding severity {self.severity!r}")
        if self.confidence not in {"low", "medium", "high", "confirmed"}:
            raise ValueError(f"unknown confidence {self.confidence!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunOutcome:
    """Small result returned from a worker; full time series stay on disk."""

    spec: RunSpec
    run_dir: str
    elapsed_seconds: float
    summary: dict[str, Any]
    findings: tuple[Finding, ...]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "run_dir": self.run_dir,
            "elapsed_seconds": self.elapsed_seconds,
            "summary": self.summary,
            "findings": [item.to_dict() for item in self.findings],
            "error": self.error,
        }
