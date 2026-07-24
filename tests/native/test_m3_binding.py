from __future__ import annotations

import math

import macro_sim._native as native


def test_m3_equation_batch_is_typed_and_ordered() -> None:
    output = native.m3_equation_batch([
        {"kind": "adaptive_expectation", "values": [10.0, 14.0, 0.25]},
        {"kind": "production_plan", "values": [10.0, 2.0, 7.0, 0.25]},
        {"kind": "bond_price", "values": [100.0, 2.0, 0.1, 0.05]},
    ])
    assert output[0] == [11.0]
    assert output[1] == [20.0, 13.25]
    assert math.isclose(output[2][0], 91.32231404958677)


def test_m3_market_batch_returns_commands_without_moving_money() -> None:
    result = native.m3_clear_market(
        [{"order_id": 1, "buyer": 10, "demand": 4.0, "budget": 20.0}],
        [
            {"offer_id": 1, "seller": 20, "stock": 2.0, "price": 4.0, "attractiveness": 1.0},
            {"offer_id": 2, "seller": 30, "stock": 5.0, "price": 2.0, "attractiveness": 1.0},
        ],
        "price_sorted",
        key=[7, 11],
    )
    assert result["trades"][0]["offer_id"] == 2
    assert result["trades"][0]["value"] == 8.0
    assert result["stock_commands"][1] == {
        "offer_id": 2,
        "seller": 30,
        "opening": 5.0,
        "sold": 4.0,
        "closing": 1.0,
    }
    assert result["diagnostics"]["price_sorts"] == 1
