#!/usr/bin/env python3
"""Compare the native M2 accounting core with a small Python reference."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
import json
import math
from pathlib import Path
import random
import sys
from typing import Any


@dataclass
class ReferenceLoan:
    lender: int
    borrower: int
    account: int
    principal: float
    active: bool = True


class ReferenceLedger:
    def __init__(self) -> None:
        self.balances = {account: 0.0 for account in range(1, 16)}
        for account in range(6, 14):
            self.balances[account] = 100.0
        self.nodes = {
            account: (1 if (account - 6) % 2 == 0 else 2)
            for account in range(6, 14)
        }
        self.nodes.update({1: 1, 2: 2, 3: 1, 4: 1, 5: 1, 14: 1, 15: 2})
        self.reserves = {1: 400.0, 2: 400.0}
        self.loans: list[ReferenceLoan] = []
        self.counters: dict[int, int] = {
            stream: 0 for stream in range(1, 6)
        }

    def transfer(self, source: int, destination: int, amount: float) -> None:
        if amount < 0.0 or not math.isfinite(amount):
            raise ValueError("invalid_argument")
        if self.balances[source] - amount < -1.0e-8:
            raise ValueError("insufficient_funds")
        self.balances[source] += -amount
        self.balances[destination] += amount
        source_node = self.nodes[source]
        destination_node = self.nodes[destination]
        if source_node != destination_node:
            self.reserves[source_node] += -amount
            self.reserves[destination_node] += amount

    def originate(self, borrower: int, account: int, amount: float) -> int:
        if borrower != account - 5:
            raise ValueError("contract_violation")
        self.balances[account] += amount
        self.loans.append(
            ReferenceLoan(
                lender=self.nodes[account],
                borrower=borrower,
                account=account,
                principal=amount,
            )
        )
        return len(self.loans)

    def repay(self, loan_id: int, account: int, amount: float) -> None:
        loan = self.loans[loan_id - 1]
        if loan.account != account or amount > loan.principal + 1.0e-8:
            raise ValueError("contract_violation")
        if self.balances[account] - amount < -1.0e-8:
            raise ValueError("insufficient_funds")
        self.balances[account] += -amount
        loan.principal += -amount
        if loan.principal == 0.0:
            loan.active = False

    def increment(self, stream: int, amount: int) -> None:
        self.counters[stream] = self.counters.get(stream, 0) + amount


def _load_native(native_dir: Path) -> Any:
    sys.path.insert(0, str(native_dir))
    return importlib.import_module("_native")


def _family(error: BaseException) -> str:
    return str(error).split(":", maxsplit=1)[0]


def _assert_close(left: float, right: float) -> None:
    if not math.isclose(left, right, rel_tol=1.0e-13, abs_tol=1.0e-13):
        raise AssertionError(f"numeric mismatch: {left!r} != {right!r}")


def _compare(reference: ReferenceLedger, snapshot: dict[str, Any]) -> None:
    accounts = {item["id"]: item for item in snapshot["accounts"]}
    for account, expected in reference.balances.items():
        _assert_close(accounts[account]["balance"], expected)
    reserves = {item["node"]: item["balance"] for item in snapshot["reserves"]}
    for node, expected in reference.reserves.items():
        _assert_close(reserves[node], expected)
    if len(snapshot["loans"]) != len(reference.loans):
        raise AssertionError("loan count mismatch")
    for actual, expected in zip(snapshot["loans"], reference.loans, strict=True):
        if (
            actual["lender"] != expected.lender
            or actual["borrower_id"] != expected.borrower
            or actual["borrower_account"] != expected.account
            or actual["active"] != expected.active
        ):
            raise AssertionError("loan identity mismatch")
        _assert_close(actual["principal"], expected.principal)
    if snapshot["counters"] != reference.counters:
        raise AssertionError("named counter mismatch")


def _run_seed(native: Any, seed: int, operations: int) -> tuple[int, int]:
    rng = random.Random(seed)
    reference = ReferenceLedger()
    session = native.EngineSession(seed + 1)
    spec = native.GenesisSpec()
    spec.households = 8
    spec.consumption_firms = 2
    spec.settlement_banks = 2
    spec.opening_money = 800.0
    spec.seed = seed
    for stream in range(1, 6):
        spec.add_counter_stream(stream)
    session.initialize_m2(spec)
    accepted = 0

    for operation in range(operations):
        choice = rng.random()
        batch = native.SettlementBatch()
        if choice < 0.55:
            source = rng.randrange(6, 14)
            destination = rng.randrange(6, 14)
            while destination == source:
                destination = rng.randrange(6, 14)
            maximum = min(reference.balances[source], 25.0)
            amount = round(rng.random() * maximum, 6)
            batch.transfer(source, destination, amount)
            reference.transfer(source, destination, amount)
        elif choice < 0.75:
            borrower = rng.randrange(1, 9)
            account = borrower + 5
            amount = round(1.0 + rng.random() * 19.0, 6)
            batch.originate_loan(
                reference.nodes[account],
                native.OwnerKind.HOUSEHOLD,
                borrower,
                account,
                amount,
                0.01 + rng.random() * 0.09,
                operation,
                operation + 365,
            )
            reference.originate(borrower, account, amount)
        elif choice < 0.9 and reference.loans:
            live = [
                (index + 1, loan)
                for index, loan in enumerate(reference.loans)
                if loan.active and loan.principal > 0.0
            ]
            if live:
                loan_id, loan = rng.choice(live)
                maximum = min(loan.principal, reference.balances[loan.account])
                amount = round(rng.random() * maximum, 6)
                batch.repay_loan(loan_id, loan.account, amount)
                reference.repay(loan_id, loan.account, amount)
            else:
                stream = rng.randrange(1, 6)
                amount = rng.randrange(1, 5)
                batch.increment_counter(stream, amount)
                reference.increment(stream, amount)
        else:
            stream = rng.randrange(1, 6)
            amount = rng.randrange(1, 5)
            batch.increment_counter(stream, amount)
            reference.increment(stream, amount)
        session.apply_batch(batch)
        accepted += 1
        if operation % 17 == 0:
            _compare(reference, session.accounting_snapshot())

    invalid_batch = native.SettlementBatch()
    source = rng.randrange(6, 14)
    destination = 6 if source != 6 else 7
    invalid_batch.transfer(
        source,
        destination,
        reference.balances[source] + 1000.0,
    )
    try:
        reference.transfer(
            source,
            destination,
            reference.balances[source] + 1000.0,
        )
    except ValueError as reference_error:
        expected_family = str(reference_error)
    else:
        raise AssertionError("reference accepted an invalid overdraft")
    before = session.digest()
    try:
        session.apply_batch(invalid_batch)
    except RuntimeError as native_error:
        if _family(native_error) != expected_family:
            raise AssertionError(
                f"error family mismatch: {_family(native_error)} "
                f"!= {expected_family}"
            ) from native_error
    else:
        raise AssertionError("native engine accepted an invalid overdraft")
    if session.digest() != before:
        raise AssertionError("rejected native batch mutated state")

    checkpoint = session.checkpoint()
    clone = native.EngineSession(seed + 1001)
    clone.restore_checkpoint(checkpoint)
    if clone.digest() != session.digest():
        raise AssertionError("checkpoint clone digest mismatch")
    _compare(reference, clone.accounting_snapshot())
    _compare(reference, session.accounting_snapshot())
    return accepted, 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--operations-per-seed", type=int, default=100)
    arguments = parser.parse_args()
    if arguments.seeds < 1 or arguments.operations_per_seed < 1:
        parser.error("seed and operation counts must be positive")

    native = _load_native(arguments.native_dir)
    accepted = 0
    rejected = 0
    for seed in range(arguments.seeds):
        seed_accepted, seed_rejected = _run_seed(
            native,
            seed,
            arguments.operations_per_seed,
        )
        accepted += seed_accepted
        rejected += seed_rejected
    print(
        json.dumps(
            {
                "accepted_operations": accepted,
                "invalid_cases": rejected,
                "operations_per_seed": arguments.operations_per_seed,
                "schema_version": "m2-differential-oracle-v1",
                "seeds": arguments.seeds,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
