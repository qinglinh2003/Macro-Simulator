from __future__ import annotations

import pytest

import macro_sim._native as native


def make_session(session_id: int = 501) -> native.EngineSession:
    spec = native.GenesisSpec()
    spec.households = 4
    spec.consumption_firms = 2
    spec.settlement_banks = 2
    spec.opening_money = 400.0
    spec.seed = 77
    spec.add_counter_stream(9)
    session = native.EngineSession(session_id)
    session.initialize_m2(spec)
    return session


def test_batch_snapshot_and_checkpoint_round_trip() -> None:
    session = make_session()
    batch = native.SettlementBatch()
    batch.transfer(6, 7, 12.5)
    batch.originate_loan(
        1,
        native.OwnerKind.HOUSEHOLD,
        1,
        6,
        20.0,
        0.04,
        0,
        365,
    )
    batch.increment_counter(9, 3)
    receipt = session.apply_batch(batch)
    assert receipt["created_loans"] == [1]
    assert receipt["before"] != receipt["after"]
    snapshot = session.accounting_snapshot()
    accounts = {item["id"]: item["balance"] for item in snapshot["accounts"]}
    assert accounts[6] == 107.5
    assert accounts[7] == 112.5
    assert snapshot["loans"][0]["principal"] == 20.0
    assert snapshot["counters"] == {9: 3}

    clone = native.EngineSession(502)
    clone.restore_checkpoint(session.checkpoint())
    assert clone.digest() == session.digest()
    assert clone.accounting_snapshot() == session.accounting_snapshot()


def test_rejected_batch_preserves_digest() -> None:
    session = make_session()
    before = session.digest()
    batch = native.SettlementBatch()
    batch.transfer(6, 7, 1000.0)
    with pytest.raises(RuntimeError, match="insufficient_funds"):
        session.apply_batch(batch)
    assert session.digest() == before
