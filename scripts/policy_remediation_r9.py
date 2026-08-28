#!/usr/bin/env python3
"""Run, freeze, or verify R9 native delivery and product evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.policy_delivery_acceptance import (  # noqa: E402
    R9_ACCEPTED_PHASES,
    build_policy_evidence_catalog,
    build_r9_acceptance,
    reduce_r9_evidence,
    render_r9_markdown,
    run_r9,
    validate_r9_acceptance,
)


DEFAULT_ARTIFACT_DIR = REPOSITORY_ROOT / "artifacts/policy-remediation/r9/final"
DEFAULT_REPORT = DEFAULT_ARTIFACT_DIR / "r9_report.json"
DEFAULT_POLICY_EVIDENCE = REPOSITORY_ROOT / "macro_sim/data/policy_evidence_v39.json"
DEFAULT_EVIDENCE = REPOSITORY_ROOT / "docs/policy_remediation_r9_delivery_evidence_v39.json"
DEFAULT_ACCEPTANCE = REPOSITORY_ROOT / "docs/policy_remediation_r9_acceptance_v39.json"
DEFAULT_MARKDOWN = REPOSITORY_ROOT / "docs/policy_remediation_r9_acceptance_v39.md"
DEFAULT_RL_ARTIFACT = (
    REPOSITORY_ROOT / "macro_sim/rl/artifacts/fiscal_stabilization_v1.msrl"
)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def _phase_acceptances() -> dict[str, dict[str, object]]:
    return {
        phase: _load(
            REPOSITORY_ROOT
            / f"docs/policy_remediation_{phase.lower()}_acceptance_v39.json"
        )
        for phase in R9_ACCEPTED_PHASES
    }


def _write_policy_evidence(path: Path) -> dict[str, object]:
    payload = build_policy_evidence_catalog(_phase_acceptances())
    _write_json(path, payload)
    return payload


def _run(arguments: argparse.Namespace) -> int:
    policy_evidence = _write_policy_evidence(arguments.policy_evidence)
    completed = 0

    def progress(seed: int) -> None:
        nonlocal completed
        completed += 1
        print(f"[{completed}/8] delivery seed={seed}", flush=True)

    payload = run_r9(
        phase_acceptances=_phase_acceptances(),
        policy_evidence=policy_evidence,
        rl_artifact=arguments.rl_artifact,
        source_revision=_revision(),
        jobs=arguments.jobs,
        progress=progress,
    )
    _write_json(arguments.report, payload)
    print(json.dumps({
        "status": payload["status"],
        "counts": payload["counts"],
        "r9_acceptance_hash": payload["hashes"]["r9_acceptance"],
    }, indent=2, sort_keys=True))
    return 0 if payload["status"] == "accepted_with_explicit_limitations" else 1


def _write(arguments: argparse.Namespace) -> int:
    policy_evidence = _write_policy_evidence(arguments.policy_evidence)
    payload = _load(arguments.report)
    evidence = reduce_r9_evidence(payload)
    acceptance = build_r9_acceptance(evidence)
    if (
        acceptance["hashes"]["policy_evidence"]
        != policy_evidence["catalog_sha256"]
    ):
        raise ValueError("R9 report does not bind the regenerated policy evidence")
    _write_json(arguments.evidence, evidence)
    _write_json(arguments.acceptance, acceptance)
    arguments.markdown.write_text(
        render_r9_markdown(acceptance), encoding="utf-8",
    )
    print(json.dumps({
        "status": acceptance["status"],
        "r9_acceptance_hash": acceptance["hashes"]["r9_acceptance"],
        "r9_evidence_hash": acceptance["hashes"]["r9_evidence"],
    }, indent=2, sort_keys=True))
    return 0 if acceptance["status"] == "accepted_with_explicit_limitations" else 1


def _check(arguments: argparse.Namespace) -> int:
    expected_policy_evidence = build_policy_evidence_catalog(
        _phase_acceptances()
    )
    errors: list[str] = []
    if _load(arguments.policy_evidence) != expected_policy_evidence:
        errors.append("committed policy evidence catalog does not reproduce")
    evidence = _load(arguments.evidence)
    acceptance = _load(arguments.acceptance)
    errors.extend(validate_r9_acceptance(evidence, acceptance))
    if arguments.markdown.read_text(encoding="utf-8") != render_r9_markdown(
        acceptance
    ):
        errors.append("committed R9 markdown does not reproduce")
    if errors:
        print(json.dumps({"status": "rejected", "errors": errors}, indent=2))
        return 1
    print(json.dumps({
        "status": acceptance["status"],
        "counts": acceptance["counts"],
        "r9_acceptance_hash": acceptance["hashes"]["r9_acceptance"],
    }, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--catalog", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--policy-evidence", type=Path, default=DEFAULT_POLICY_EVIDENCE)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--acceptance", type=Path, default=DEFAULT_ACCEPTANCE)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--rl-artifact", type=Path, default=DEFAULT_RL_ARTIFACT)
    parser.add_argument("--jobs", type=int, default=8)
    arguments = parser.parse_args()
    if arguments.catalog:
        payload = _write_policy_evidence(arguments.policy_evidence)
        print(json.dumps({
            "catalog_sha256": payload["catalog_sha256"],
            "policies": len(payload["policies"]),
        }, indent=2, sort_keys=True))
        return 0
    if arguments.run:
        return _run(arguments)
    if arguments.write:
        return _write(arguments)
    return _check(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
