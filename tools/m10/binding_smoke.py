from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _native(native_dir: Path):
    sys.path.insert(0, str(native_dir))
    import _native as native  # type: ignore[import-not-found]

    return native


def _world(native):
    economy = native.M8SimulationSpec()
    population = economy.domestic_economy
    monetary = population.financial_economy.monetary_economy
    real = monetary.real_economy
    real.vertical = native.M4Vertical.CAPITAL_FISCAL
    real.households = 8
    real.consumption_firms = 2
    real.capital_firms = 1
    real.seed = 910
    real.requested_capabilities = (1 << 0) | (1 << 1)
    monetary.rules.bank_count = 2
    monetary.rules.opening_capital_per_bank = 100.0
    population.financial_economy.rules.entry_beta = 0.0
    population.financial_economy.rules.bank_entry_beta = 0.0
    population.population.initial_persons = 16
    population.rules.fertility = False
    population.rules.mortality = False
    population.rules.marriage = False
    population.rules.divorce = False
    economy.energy_rules.producer_count = 1

    spec = native.M9WorldSpec()
    spec.economies = [economy]
    spec.external_policies = [native.ExternalPolicy()]
    return native.WorldSession.create(spec)


def _envelope(native, engine, payload: bytes):
    value = native.CanonicalControllerEnvelope()
    value.boundary = engine.tick
    value.policy_generation = engine.policy_generation
    value.decision_versions = [0, 0]
    value.effective_versions = [0, 0]
    value.canonical_payload = payload
    digest = value.seal()
    assert len(digest) == 64
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-dir", type=Path, required=True)
    args = parser.parse_args()
    native = _native(args.native_dir)

    world = _world(native)
    engine = native.NativeWorldEngineSession.create(world, 8)
    initial = _envelope(native, engine, b'{"phase":"boundary_start"}')
    bridge = native.HybridControlledBridge.create(engine, initial)

    policy = world.domestic_policy(0)
    policy.fiscal_monetary.income_tax_rate = 0.37
    policies = native.WorldPolicyBatch()
    policies.expected_tick = bridge.tick
    policies.expected_generation = 0
    policies.domestic = [policy]
    policies.external = world.external_policies()
    batch = native.SealedControlBatch()
    batch.operation_id = "m10-binding-boundary"
    batch.expected_controller_hash = bridge.controller_envelope.hash
    batch.policies = policies
    batch.advance_ticks = 1
    batch.worker_count = 1

    previous_envelope = bridge.controller_envelope
    lease = bridge.prepare_boundary(batch)
    assert lease.active
    assert lease.preview["next_tick"] == 1
    next_envelope = previous_envelope
    next_envelope.boundary = 1
    next_envelope.policy_generation = 1
    next_envelope.event_sequence = 1
    next_envelope.decision_versions = [1, 0]
    next_envelope.effective_versions = [1, 0]
    next_envelope.canonical_payload = b'{"phase":"committed"}'
    next_envelope.seal()
    result = bridge.commit_boundary(lease, next_envelope)
    assert result["next_tick"] == 1
    assert bridge.tick == 1
    assert bridge.public_metrics()["tick"] == 1

    shock = native.ShockSpec()
    shock.id = 10_001
    shock.kind = native.ShockKind.HOUSEHOLD_DEMAND
    shock.economy_id = 0
    shock.start_tick = bridge.tick
    shock.announcement_tick = bridge.tick
    shock.duration = 1
    shock.magnitude = 0.20
    shock_envelope = bridge.controller_envelope
    shock_envelope.event_sequence += 1
    shock_envelope.canonical_payload = b'{"command":"schedule_shock"}'
    shock_envelope.seal()
    transition = native.ControllerEnvelopeTransition()
    transition.operation_id = "m10-binding-shock"
    transition.expected_prior_hash = bridge.controller_envelope.hash
    transition.next = shock_envelope
    shock_receipt = bridge.schedule_shock(shock, transition)
    assert shock_receipt["operation_id"] == "m10-binding-shock"
    assert shock_receipt["boundary"] == 1
    bridge.acknowledge_receipt("m10-binding-shock")

    checkpoint = bridge.checkpoint(b'{"horizon":365}')
    restored = native.HybridControlledBridge.restore_checkpoint(checkpoint)
    loaded = restored["bridge"]
    assert loaded.tick == 1
    assert restored["objective_envelope"] == b'{"horizon":365}'
    assert loaded.controller_envelope.hash == bridge.controller_envelope.hash
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
