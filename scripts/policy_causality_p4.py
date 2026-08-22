#!/usr/bin/env python3
"""Run the resumable native P4 single-policy crisis evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from macro_sim.diagnostics.policy_crisis_effects import (  # noqa: E402
    render_p4_markdown,
    run_p4,
)
from macro_sim.diagnostics.policy_scenarios import DEFAULT_P3_SEEDS  # noqa: E402


def _revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts/policy-audit/p4",
    )
    parser.add_argument(
        "--p2-report",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts/policy-audit/p2/p2_report.json",
    )
    parser.add_argument(
        "--p3-report",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts/policy-audit/p3/p3_report.json",
    )
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--population", type=int, default=100_000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--seeds",
        type=int,
        nargs=8,
        default=DEFAULT_P3_SEEDS,
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--fail-on-incomplete", action="store_true")
    arguments = parser.parse_args()

    completed = 0

    def progress(seed: int, lever: str, arm: str, timing: str, cached: bool) -> None:
        nonlocal completed
        completed += 1
        state = "cache" if cached else "fresh"
        print(
            f"[{completed}] seed={seed} lever={lever} arm={arm} "
            f"timing={timing} {state}",
            flush=True,
        )

    payload = run_p4(
        artifact_dir=arguments.artifact_dir,
        p2_payload=_load(arguments.p2_report),
        p3_payload=_load(arguments.p3_report),
        source_revision=_revision(),
        seeds=tuple(arguments.seeds),
        population=arguments.population,
        workers=arguments.workers,
        jobs=arguments.jobs,
        resume=not arguments.no_resume,
        progress=progress,
    )
    markdown_output = arguments.markdown_output
    if markdown_output is None:
        markdown_output = arguments.artifact_dir / "p4_report.md"
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_p4_markdown(payload), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "counts": payload["counts"],
        "p4_acceptance_hash": payload["hashes"]["p4_acceptance"],
    }, indent=2, sort_keys=True))
    if arguments.fail_on_incomplete and payload["status"] not in {
        "accepted",
        "accepted_with_explicit_defects",
    }:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
