#!/usr/bin/env python3
"""Run, freeze, or verify Policy remediation milestone R6."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from scripts.policy_remediation_r6_lib import (
    build_r6_acceptance,
    render_r6_markdown,
    run_r6_crises,
    run_r6_mechanism,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts/policy-remediation/r6/final"
DEFAULT_P3 = ROOT / "docs/policy_remediation_r5_p3_evidence_v39.json"
DEFAULT_P2_EVIDENCE = ROOT / "docs/policy_remediation_r6_p2_evidence_v39.json"
DEFAULT_CRISIS_EVIDENCE = (
    ROOT / "docs/policy_remediation_r6_crisis_evidence_v39.json"
)
DEFAULT_ACCEPTANCE = ROOT / "docs/policy_remediation_r6_acceptance_v39.json"
DEFAULT_MARKDOWN = ROOT / "docs/policy_remediation_r6_acceptance_v39.md"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _revision() -> str:
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, text=True
    ).strip()


def _progress(group: int, total: int, item: object) -> None:
    print(f"mechanism group {group}/{total}: {item.phase} {item.group_id}", flush=True)


def _crisis_progress(scenario_id: str, index: int, total: int) -> None:
    print(f"crisis {index}/{total}: {scenario_id}", flush=True)


def _frozen_crisis(payload: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if key != "seed_runs"
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--p3", type=Path, default=DEFAULT_P3)
    parser.add_argument("--p2-evidence", type=Path, default=DEFAULT_P2_EVIDENCE)
    parser.add_argument(
        "--crisis-evidence", type=Path, default=DEFAULT_CRISIS_EVIDENCE
    )
    parser.add_argument("--acceptance", type=Path, default=DEFAULT_ACCEPTANCE)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    p3 = _load(args.p3)
    if args.run:
        revision = _revision()
        p2 = run_r6_mechanism(
            artifact_dir=args.artifact_dir / "mechanism",
            source_revision=revision,
            resume=not args.no_resume,
            progress=_progress,
        )
        if p2["errors"]:
            print(json.dumps({"p2_errors": p2["errors"]}, indent=2))
            return 1
        crisis = run_r6_crises(
            artifact_dir=args.artifact_dir / "crisis",
            p2_payload=p2,
            p3_payload=p3,
            source_revision=revision,
            resume=not args.no_resume,
            progress=_crisis_progress,
        )
        print(json.dumps({
            "mechanism_status": p2["status"],
            "mechanism_runs": p2["counts"]["executed_native_runs"],
            "crisis_status": crisis["status"],
            "crisis_branches": crisis["counts"]["executed_native_branches"],
            "cache_hits": (
                p2["counts"]["cache_hits"] + crisis["counts"]["cache_hits"]
            ),
        }, indent=2, sort_keys=True))
        return 0 if crisis["status"] == "accepted" else 1

    if args.write:
        p2_source = args.artifact_dir / "mechanism/p2_report.json"
        crisis_source = args.artifact_dir / "crisis/r6_crisis_report.json"
        shutil.copyfile(p2_source, args.p2_evidence)
        _write(args.crisis_evidence, _frozen_crisis(_load(crisis_source)))

    p2 = _load(args.p2_evidence)
    crisis = _load(args.crisis_evidence)
    acceptance = build_r6_acceptance(
        p2_payload=p2,
        crisis_payload=crisis,
        p3_payload=p3,
    )
    rendered = json.dumps(acceptance, indent=2, sort_keys=True) + "\n"
    markdown = render_r6_markdown(acceptance)
    if args.check:
        stale = []
        if not args.acceptance.is_file() or args.acceptance.read_text(
            encoding="utf-8"
        ) != rendered:
            stale.append(str(args.acceptance))
        if not args.markdown.is_file() or args.markdown.read_text(
            encoding="utf-8"
        ) != markdown:
            stale.append(str(args.markdown))
        if stale:
            print("stale R6 acceptance artifacts: " + ", ".join(stale))
            return 1
    else:
        args.acceptance.write_text(rendered, encoding="utf-8")
        args.markdown.write_text(markdown, encoding="utf-8")
    print(json.dumps({
        "status": acceptance["status"],
        "errors": acceptance["errors"],
        "classifications": acceptance["counts"]["classifications"],
        "r6_acceptance_hash": acceptance["hashes"]["r6_acceptance"],
    }, indent=2, sort_keys=True))
    return 0 if acceptance["status"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
