from __future__ import annotations

from scripts.cpp_migration.comparator import (
    load_tolerance_registry,
    resolve_tolerance,
)


def test_tolerance_registry_is_unique_and_has_no_global_fallback():
    registry = load_tolerance_registry()
    assert len({rule.id for rule in registry}) == len(registry)
    assert resolve_tolerance("$.selected_state.policy_rate", registry).id == (
        "tolerance.trace.rates"
    )
    assert resolve_tolerance("$.unregistered.value", registry) is None
