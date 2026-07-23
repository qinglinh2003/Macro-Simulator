from __future__ import annotations

from pathlib import Path

import pytest

from scripts.cpp_migration.common import (
    BaselineWriteError,
    canonical_json_load,
    reject_checked_baseline_target,
)
from scripts.cpp_migration.propose_rebaseline import build_proposal, write_proposal


def test_checked_baseline_roots_are_rejected():
    root = Path(__file__).resolve().parents[3]
    with pytest.raises(BaselineWriteError, match="checked baseline"):
        reject_checked_baseline_target(
            root / "tests/fixtures/m0/expected/proposal"
        )
    with pytest.raises(BaselineWriteError, match="checked baseline"):
        reject_checked_baseline_target(root / "schemas/m0/proposal")


def test_proposal_is_review_only_and_records_tree_changes(tmp_path: Path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (before / "same.json").write_text("same", encoding="utf-8")
    (after / "same.json").write_text("same", encoding="utf-8")
    (after / "new.json").write_text("new", encoding="utf-8")

    proposal = build_proposal(
        reason="Intentional test rebaseline.",
        before_root=before,
        after_root=after,
        old_oracle_commit="a" * 40,
        new_oracle_commit="b" * 40,
    )
    assert proposal["changed_paths"] == ["new.json"]
    assert proposal["application"] == {
        "automatic": False,
        "review_required": True,
        "checked_files_modified": False,
    }

    path = write_proposal(tmp_path / "proposal", proposal)
    assert canonical_json_load(path) == proposal
    with pytest.raises(BaselineWriteError, match="already exists"):
        write_proposal(tmp_path / "proposal", proposal)


def test_empty_rebaseline_reason_is_rejected():
    with pytest.raises(BaselineWriteError, match="must not be empty"):
        build_proposal(
            reason=" ",
            before_root=None,
            after_root=None,
            old_oracle_commit=None,
            new_oracle_commit=None,
        )
