#!/usr/bin/env python3
"""Run, freeze, or verify Policy remediation milestone R7."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from scripts.policy_remediation_r7_lib import (
    build_r7_acceptance,
    freeze_r7_evidence,
    render_r7_markdown,
    run_r7,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts/policy-remediation/r7/final"
DEFAULT_R6_P2 = ROOT / "docs/policy_remediation_r6_p2_evidence_v39.json"
DEFAULT_R6_ACCEPTANCE = ROOT / "docs/policy_remediation_r6_acceptance_v39.json"
DEFAULT_EVIDENCE = ROOT / "docs/policy_remediation_r7_scale_evidence_v39.json"
DEFAULT_ACCEPTANCE = ROOT / "docs/policy_remediation_r7_acceptance_v39.json"
DEFAULT_MARKDOWN = ROOT / "docs/policy_remediation_r7_acceptance_v39.md"


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


def _progress(row: object, cached: bool) -> None:
    print(
        f"R7 population={row['population']} lever={row['lever']} "
        f"seed={row['seed']} elapsed={row['elapsed_seconds']:.1f}s "
        f"{'cache' if cached else 'fresh'}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--r6-p2", type=Path, default=DEFAULT_R6_P2)
    parser.add_argument(
        "--r6-acceptance", type=Path, default=DEFAULT_R6_ACCEPTANCE
    )
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--acceptance", type=Path, default=DEFAULT_ACCEPTANCE)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    if args.run:
        report = run_r7(
            artifact_dir=args.artifact_dir,
            source_revision=_revision(),
            r6_p2=_load(args.r6_p2),
            r6_acceptance=_load(args.r6_acceptance),
            resume=not args.no_resume,
            progress=_progress,
        )
        print(json.dumps({
            "status": report["status"],
            "errors": report["errors"],
            "records": report["counts"]["run_records"],
            "cache_hits": report["counts"]["cache_hits"],
            "dispositions": report["counts"]["dispositions"],
        }, indent=2, sort_keys=True))
        return 0 if report["status"] == "accepted" else 1

    if args.write:
        source = _load(args.artifact_dir / "r7_report.json")
        _write(args.evidence, freeze_r7_evidence(source))

    evidence = _load(args.evidence)
    acceptance = build_r7_acceptance(evidence)
    rendered = json.dumps(acceptance, indent=2, sort_keys=True) + "\n"
    markdown = render_r7_markdown(acceptance)
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
            print("stale R7 acceptance artifacts: " + ", ".join(stale))
            return 1
    else:
        args.acceptance.write_text(rendered, encoding="utf-8")
        args.markdown.write_text(markdown, encoding="utf-8")
    print(json.dumps({
        "status": acceptance["status"],
        "errors": acceptance["errors"],
        "counts": acceptance["counts"],
        "r7_acceptance_hash": acceptance["hashes"]["r7_acceptance"],
    }, indent=2, sort_keys=True))
    return 0 if acceptance["status"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
