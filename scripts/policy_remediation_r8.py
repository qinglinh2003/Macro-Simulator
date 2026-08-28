#!/usr/bin/env python3
"""Run, freeze, or verify R8 native policy-package evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.policy_package_robustness import (  # noqa: E402
    R8_ACCEPTED_PHASES,
    build_r8_acceptance,
    reduce_r8_evidence,
    render_r8_markdown,
    run_r8,
    validate_r8_acceptance,
)


DEFAULT_ARTIFACT_DIR = REPOSITORY_ROOT / "artifacts/policy-remediation/r8/final"
DEFAULT_EVIDENCE = (
    REPOSITORY_ROOT / "docs/policy_remediation_r8_package_evidence_v39.json"
)
DEFAULT_ACCEPTANCE = (
    REPOSITORY_ROOT / "docs/policy_remediation_r8_acceptance_v39.json"
)
DEFAULT_MARKDOWN = REPOSITORY_ROOT / "docs/policy_remediation_r8_acceptance_v39.md"


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
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _phase_acceptances() -> dict[str, dict[str, object]]:
    return {
        phase: _load(
            REPOSITORY_ROOT
            / f"docs/policy_remediation_{phase.lower()}_acceptance_v39.json"
        )
        for phase in R8_ACCEPTED_PHASES
    }


def _run(arguments: argparse.Namespace) -> int:
    completed = 0

    def progress(seed: int, package: str, branch: str, cached: bool) -> None:
        nonlocal completed
        completed += 1
        state = "cache" if cached else "fresh"
        print(
            f"[{completed}] seed={seed} package={package} branch={branch} {state}",
            flush=True,
        )

    payload = run_r8(
        artifact_dir=arguments.artifact_dir,
        phase_acceptances=_phase_acceptances(),
        r5_p3_payload=_load(
            REPOSITORY_ROOT / "docs/policy_remediation_r5_p3_evidence_v39.json"
        ),
        remediation_ledger=_load(
            REPOSITORY_ROOT / "docs/policy_remediation_ledger_v39.json"
        ),
        source_revision=_revision(),
        repo_root=REPOSITORY_ROOT,
        jobs=arguments.jobs,
        resume=not arguments.no_resume,
        progress=progress,
    )
    print(json.dumps({
        "status": payload["status"],
        "counts": payload["counts"],
        "r8_acceptance_hash": payload["hashes"]["r8_acceptance"],
    }, indent=2, sort_keys=True))
    return 0 if payload["status"] == "accepted" else 1


def _write(arguments: argparse.Namespace) -> int:
    report_path = arguments.artifact_dir / "r8_report.json"
    payload = _load(report_path)
    evidence = reduce_r8_evidence(payload)
    acceptance = build_r8_acceptance(evidence)
    _write_json(arguments.evidence, evidence)
    _write_json(arguments.acceptance, acceptance)
    arguments.markdown.write_text(
        render_r8_markdown(acceptance),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": acceptance["status"],
        "r8_acceptance_hash": acceptance["hashes"]["r8_acceptance"],
        "r8_evidence_hash": acceptance["hashes"]["r8_evidence"],
    }, indent=2, sort_keys=True))
    return 0 if acceptance["status"] == "accepted" else 1


def _check(arguments: argparse.Namespace) -> int:
    evidence = _load(arguments.evidence)
    acceptance = _load(arguments.acceptance)
    errors = validate_r8_acceptance(evidence, acceptance)
    if errors:
        print(json.dumps({"status": "rejected", "errors": errors}, indent=2))
        return 1
    expected_markdown = render_r8_markdown(acceptance)
    if arguments.markdown.read_text(encoding="utf-8") != expected_markdown:
        print(json.dumps({
            "status": "rejected",
            "errors": ["committed R8 markdown does not reproduce"],
        }, indent=2))
        return 1
    print(json.dumps({
        "status": "accepted",
        "counts": acceptance["counts"],
        "gate_counts": acceptance["gate_counts"],
        "component_role_counts": acceptance["component_role_counts"],
        "r8_acceptance_hash": acceptance["hashes"]["r8_acceptance"],
    }, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--acceptance", type=Path, default=DEFAULT_ACCEPTANCE)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--no-resume", action="store_true")
    arguments = parser.parse_args()
    if arguments.run:
        return _run(arguments)
    if arguments.write:
        return _write(arguments)
    return _check(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
