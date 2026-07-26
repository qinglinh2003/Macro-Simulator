from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.native_dir))
    sys.path.insert(1, str(args.source_dir))

    from macro_sim.desktop.new_game import NewGameSpec
    from macro_sim.core.external_policy import ExternalPolicy
    from macro_sim.core.policy import Policy
    from macro_sim.core.policy_registry import REGISTRY
    from macro_sim.native_backend import (
        NATIVE_POLICY_LEVERS,
        NativeSimulationSession,
        build_world_spec,
    )

    for scenario in ("sandbox", "oil", "gfc", "pandemic", "disaster"):
        spec = replace(NewGameSpec.default(seed=941), scenario=scenario)
        world_spec = build_world_spec(spec)
        assert len(world_spec.economies) == len(spec.countries)
        assert len(world_spec.external_policies) == len(spec.countries)
        if scenario != "sandbox":
            assert world_spec.shocks

    spec = NewGameSpec.default(seed=942)
    session = NativeSimulationSession.create(spec)
    assert session.tick == 0
    assert set(NATIVE_POLICY_LEVERS) == set(REGISTRY)
    opening_policy = Policy.from_config(spec.configs()[0])
    opening_external = ExternalPolicy()
    for lever_name, lever in REGISTRY.items():
        source = opening_external if lever.scope == "external" else opening_policy
        session._policy_batch((
            {"lever": lever_name, "value": getattr(source, lever_name)},
        ))
    session.advance(actions=(
        {"lever": "tax_income_rate", "value": 0.31},
        {"lever": "tariff", "value": 0.08},
    ))
    assert session.tick == 1
    assert (
        session.bridge.domestic_policy(0).fiscal_monetary.income_tax_rate
        == 0.31
    )
    assert session.bridge.external_policies()[0].tariff == 0.08
    generation = session.bridge.policy_generation
    session.advance()
    assert session.tick == 2
    assert session.bridge.policy_generation == generation

    checkpoint = session.checkpoint(b'{"objective":"native"}')
    restored, objective = NativeSimulationSession.restore(spec, checkpoint)
    assert restored.tick == session.tick
    assert objective == b'{"objective":"native"}'
    assert restored.native_snapshot()["digest"] == session.native_snapshot()["digest"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
