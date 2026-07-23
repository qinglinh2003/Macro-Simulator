from __future__ import annotations

from scripts.cpp_migration.comparator import validate_semantic_panels


def test_semantic_panels_cover_all_required_policy_and_shock_domains():
    manifest = validate_semantic_panels()
    domains = {row["domain"] for row in manifest["rows"]}
    assert {
        "fiscal",
        "monetary",
        "prudential_banking",
        "housing",
        "energy",
        "trade_sanctions",
        "peg_fx",
        "migration_external_capital",
        "shocks",
    } <= domains
    assert all(row["python_evidence"] for row in manifest["rows"])
