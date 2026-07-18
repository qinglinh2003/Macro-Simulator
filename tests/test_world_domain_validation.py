"""Fail-fast domain contracts for mutable non-trade World parameters."""

from __future__ import annotations

from copy import deepcopy

import pytest

from macro_sim.config import Config
from macro_sim.world import World


def _configs() -> list[Config]:
    return [
        Config(n_households=4, n_firms=2, n_ticks=1, seed=11),
        Config(n_households=4, n_firms=2, n_ticks=1, seed=12),
    ]


def _world(**kwargs) -> World:
    return World(
        _configs(),
        base_seed=101,
        trade=True,
        capital=True,
        migration=True,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("fx_lambda", -0.01),
        ("fx_lambda", 1.01),
        ("fx_lambda", float("nan")),
        ("fx_friction", -0.01),
        ("fx_trade_cap", -0.01),
        ("capital_mobility", -0.01),
        ("capital_adjust", -0.01),
        ("capital_adjust", 1.01),
        ("periods_per_year", 0.0),
        ("peg_reserves0", -0.01),
        ("peg_reserve_scale", -0.01),
        ("migration_rate", -0.01),
        ("migration_rate", 1.01),
        ("migration_max_share", -0.01),
        ("migration_max_share", 1.01),
        ("remittance_share", -0.01),
        ("remittance_share", 1.01),
        ("capital_control", -0.01),
        ("capital_control", 1.01),
        ("remittance_tax", -0.01),
        ("remittance_tax", 1.01),
        ("outward_remittance_tax", -0.01),
        ("outward_remittance_tax", 1.01),
        ("guest_worker_return", -0.01),
        ("guest_worker_return", 1.01),
        ("wage_smoothing", -0.01),
        ("wage_smoothing", 1.01),
        ("wage_smoothing", float("inf")),
        ("immigration_cap", -0.01),
        ("emigration_cap", -0.01),
        ("emigration_cap", 1.01),
        ("emigration_cap", [0.0, -0.01]),
        ("emigration_cap", [0.0]),
        ("import_quota", -0.01),
        ("import_quota", [0.0, -0.01]),
        ("import_quota", [0.0]),
        ("sanctions", {frozenset({0, 2})}),
        ("sanctions", {frozenset({0})}),
        ("sanctions", [(0, 1)]),
    ],
)
def test_constructor_rejects_invalid_non_trade_world_domain(name, value):
    with pytest.raises(ValueError, match=name):
        World(_configs(), **{name: value})


def test_valid_domain_boundaries_are_accepted():
    world = World(
        _configs(),
        fx_lambda=1.0,
        fx_friction=0.0,
        fx_trade_cap=0.0,
        capital_mobility=0.0,
        capital_adjust=1.0,
        periods_per_year=0.01,
        peg_reserves0=0.0,
        peg_reserve_scale=0.0,
        migration_rate=1.0,
        migration_max_share=1.0,
        remittance_share=1.0,
        immigration_cap=0.0,
        remittance_tax=1.0,
        import_quota=[0.0, 2.0],
        capital_control=1.0,
        sanctions={frozenset({0, 1})},
        emigration_cap=[0.0, 1.0],
        outward_remittance_tax=1.0,
        guest_worker_return=1.0,
        wage_smoothing=1.0,
    )

    assert world.n == 2


def _state_before_step(world: World) -> dict:
    return {
        "world_tick": world.t,
        "economy_ticks": [econ.t for econ in world.economies],
        "world_records": deepcopy(world.world_records),
        "economy_records": [deepcopy(econ.records) for econ in world.economies],
        "inventories": [
            [(firm.id, firm.inventory) for firm in econ.firms]
            for econ in world.economies
        ],
        "ledger_balances": [
            deepcopy(econ.ledger.snapshot()) for econ in world.economies
        ],
        "ledger_loans": [
            deepcopy(econ.ledger._loans) for econ in world.economies
        ],
        "ledger_reserves": [
            deepcopy(econ.ledger._reserves) for econ in world.economies
        ],
        "ledger_bank_securities": [
            econ.ledger.bank_securities for econ in world.economies
        ],
        "external_journals": [
            tuple(
                (hasattr(econ, name), getattr(econ, name, None))
                for name in (
                    "_fx_import_transaction_value_external",
                    "_fx_import_value_external",
                    "_fx_import_delivered_volume_external",
                    "_fx_import_volume_external",
                    "_fx_export_transaction_value_external",
                    "_fx_export_value_external",
                    "_fx_export_delivered_volume_external",
                    "_fx_export_shipped_volume_external",
                    "_fx_export_volume_external",
                    "_fx_iceberg_loss_volume_external",
                    "_fx_export_contract_basic_value_external",
                    "_fx_export_barrier_lot_basic_value_external",
                    "_fx_export_account_lot_basic_value_external",
                    "_fx_export_barrier_lot_contract_gap_external",
                    "_fx_export_lot_repricing_gap_external",
                    "_fx_export_inventory_withdrawal_price_adjustment_external",
                )
            )
            for econ in world.economies
        ],
        "reservations": deepcopy(world._export_reservations),
        "migrant_stock": list(world._migrant_stock),
        "wage_ema": deepcopy(world._rw_ema),
        "rates": list(world.rates.log_e),
        "dealer_inventory": world.dealer.inventory(),
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        # world PHYSICS knobs: still direct attributes
        ("fx_lambda", -0.1),
        ("fx_lambda", 1.1),
        ("capital_adjust", 1.1),
        ("migration_rate", 1.1),
        ("_peg_reserves0", -1.0),
        # B5a-DERIVED vectors: the malformed value goes in at the AUTHORITY (an
        # economy's own stance); the commit derives it, validation rejects it.
        ("external:1:import_quota", -0.1),
        ("external:0:sanctions_imposed_on", frozenset({2})),   # id out of range (n=2)
    ],
)
def test_runtime_mutation_fails_before_any_coupled_step_state_change(name, value):
    world = _world()
    # Non-zero sentinels prove validation runs before the coupling barrier's journal reset.
    for i, econ in enumerate(world.economies, start=1):
        econ._fx_import_transaction_value_external = 10.0 * i
        econ._fx_import_value_external = 10.0 * i
        econ._fx_import_delivered_volume_external = 20.0 * i
        econ._fx_import_volume_external = 20.0 * i
        econ._fx_export_transaction_value_external = 30.0 * i
        econ._fx_export_value_external = 30.0 * i
        econ._fx_export_delivered_volume_external = 40.0 * i
        econ._fx_export_shipped_volume_external = 50.0 * i
        econ._fx_export_volume_external = 50.0 * i
        econ._fx_iceberg_loss_volume_external = 10.0 * i
        econ._fx_export_contract_basic_value_external = 60.0 * i
        econ._fx_export_barrier_lot_basic_value_external = 61.0 * i
        econ._fx_export_account_lot_basic_value_external = 63.0 * i
        econ._fx_export_barrier_lot_contract_gap_external = 1.0 * i
        econ._fx_export_lot_repricing_gap_external = 2.0 * i
        econ._fx_export_inventory_withdrawal_price_adjustment_external = 3.0 * i
    if name.startswith("external:"):
        _, idx, field = name.split(":")
        setattr(world.economies[int(idx)].external_policy, field, value)
    else:
        setattr(world, name, value)
    before = _state_before_step(world)

    with pytest.raises(ValueError):
        world.step()

    assert _state_before_step(world) == before


def test_invalid_guest_worker_return_cannot_create_negative_migrant_stock():
    world = _world()
    world._migrant_stock[0] = 2.0
    # B5a: guest_worker_return is a HOST stance now -- the malformed value enters
    # at the authority and must be rejected when the commit derives the vector.
    world.economies[0].external_policy.guest_worker_return = 1.1
    before = _state_before_step(world)

    with pytest.raises(ValueError, match="guest_worker_return"):
        world.step()

    assert world._migrant_stock == [2.0, 0.0]
    assert _state_before_step(world) == before


def test_valid_runtime_domain_check_is_observation_only():
    world = _world(
        capital_adjust=1.0,
        emigration_cap=[0.0, 1.0],
        import_quota=[0.0, 1.0],
        sanctions={frozenset({0, 1})},
    )
    before = _state_before_step(world)

    world._validate_domains()

    assert _state_before_step(world) == before
