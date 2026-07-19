"""Foundation tests for v3 credit primitives (DESIGNDOC A5, §12; PLAN_v3 step 1).

The ledger gains money creation (``create_loan``) and destruction (``repay``). Like
``transfer`` for v1/v2, these must make A5 (net worth ΣD − ΣL = M) unbreakable by
construction: broad money ΣD becomes endogenous, but ΣD − ΣL stays pinned to M.

Zero external deps: ``uv run python tests/test_credit_primitives.py`` (also pytest).
Seeded for reproducibility (§7.6).
"""

from __future__ import annotations

import os
import pickle
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro_sim.core.ledger import ConservationError, Ledger, OverdraftError  # noqa: E402


def _fresh():
    # households/firms hold M; a bank account starts at 0 deposits (0 loans).
    return Ledger({"h": 100.0, "f": 50.0, "BANK": 0.0})


def test_create_loan_grows_broad_money_keeps_net_worth():
    led = _fresh()
    M = led.genesis_money
    led.create_loan("f", 40.0)
    assert led.balance("f") == 90.0          # deposit created
    assert led.debt("f") == 40.0             # matching debt
    assert led.total_money == M + 40.0       # broad money grew (endogenous)
    assert led.total_credit == 40.0
    assert abs(led.net_worth - M) < 1e-12    # net worth pinned to M (A5)
    led.assert_conserved()


def test_repay_shrinks_broad_money_keeps_net_worth():
    led = _fresh()
    M = led.genesis_money
    led.create_loan("f", 40.0)
    led.repay("f", 30.0)
    assert led.balance("f") == 60.0
    assert led.debt("f") == 10.0
    assert led.total_money == M + 10.0
    assert abs(led.net_worth - M) < 1e-12
    led.assert_conserved()


def test_full_cycle_returns_to_start():
    led = _fresh()
    M = led.genesis_money
    led.create_loan("f", 25.0)
    led.repay("f", 25.0)
    assert led.balance("f") == 50.0 and led.debt("f") == 0.0
    assert led.total_money == M and led.total_credit == 0.0
    led.assert_conserved()


def test_interest_is_a_transfer_net_worth_unchanged():
    led = _fresh()
    M = led.genesis_money
    led.create_loan("f", 40.0)          # f owes 40, has 90
    led.transfer("f", "BANK", 4.0)      # interest r*L: ordinary transfer to bank
    assert led.balance("f") == 86.0 and led.balance("BANK") == 4.0
    assert led.debt("f") == 40.0        # interest does NOT touch principal
    assert abs(led.net_worth - M) < 1e-12
    led.assert_conserved()


def test_reject_over_repayment():
    led = _fresh()
    led.create_loan("f", 20.0)
    try:
        led.repay("f", 20.01)
    except ValueError:
        pass
    else:
        raise AssertionError("repaying more than owed should raise ValueError")
    assert led.debt("f") == 20.0 and led.balance("f") == 70.0  # untouched


def test_reject_repay_without_cash():
    led = _fresh()
    led.create_loan("f", 40.0)          # f: deposits 90, debt 40
    led.transfer("f", "h", 90.0)        # f spends all cash (still owes 40)
    try:
        led.repay("f", 10.0)
    except OverdraftError:
        pass
    else:
        raise AssertionError("repaying with no cash should raise OverdraftError")


def test_reject_negative_loan():
    led = _fresh()
    for call in (lambda: led.create_loan("f", -1.0), lambda: led.repay("f", -1.0)):
        try:
            call()
        except ValueError:
            pass
        else:
            raise AssertionError("negative loan/repay should raise ValueError")


def test_a5_reduces_to_m0_without_credit():
    # No loans anywhere -> net worth == broad money == M (this is why v1/v2 regress cleanly).
    led = _fresh()
    led.transfer("h", "f", 30.0)
    assert led.total_credit == 0.0
    assert led.net_worth == led.total_money == led.genesis_money
    led.assert_conserved()


def test_a5_gate_catches_injected_money():
    led = _fresh()
    led._bal["h"] += 5.0                 # rogue deposit creation, no matching debt
    try:
        led.assert_conserved()
    except ConservationError:
        pass
    else:
        raise AssertionError("A5 gate should catch money created without debt")


def test_randomized_credit_sequence_conserves_net_worth():
    """Stress: thousands of mixed transfer/create_loan/repay ops never drift net worth."""
    rng = random.Random(2024)
    ids = [f"a{i}" for i in range(20)] + ["BANK"]
    led = Ledger({aid: (0.0 if aid == "BANK" else rng.uniform(0, 500)) for aid in ids})
    M = led.genesis_money
    for _ in range(20_000):
        op = rng.random()
        a = rng.choice(ids)
        if op < 0.45:                                    # transfer
            b = rng.choice(ids)
            bal = led.balance(a)
            if a != b and bal > 0:
                led.transfer(a, b, rng.uniform(0, bal))
        elif op < 0.75:                                  # create_loan
            led.create_loan(a, rng.uniform(0, 100))
        else:                                            # repay
            amt = min(led.debt(a), led.balance(a))
            if amt > 0:
                led.repay(a, rng.uniform(0, amt))
        led.assert_conserved()                           # gate every step
    assert abs(led.net_worth - M) < 1e-6 * max(M, led.total_money)


def test_roundoff_tracking_explains_only_ledger_generated_drift():
    led = Ledger({"GOV": 0.0, "h": 1575.0, "x": 0.0})
    led.allow_negative("GOV")
    led.transfer("GOV", "h", 1e8)
    for _ in range(10_000):
        led.transfer("GOV", "x", 1e-9)

    raw_drift = led.net_worth - led.genesis_money
    assert abs(raw_drift) > 5e-6
    assert abs(raw_drift - led._a5_roundoff_drift) < 1e-12
    led.assert_conserved()

    # A write that bypasses the double-entry API has no tracked residual and must
    # still trip the gate even after a long numerically ill-conditioned sequence.
    led._bal["h"] += 1e-5
    try:
        led.assert_conserved()
    except ConservationError:
        pass
    else:
        raise AssertionError("tracked roundoff must not hide a rogue single-leg write")


def test_pre_roundoff_tracking_checkpoint_lazily_migrates_on_first_write():
    led = Ledger({"GOV": 0.0, "h": 10.0})
    led.allow_negative("GOV")
    del led._a5_roundoff_drift
    del led._reserve_roundoff_drift
    restored = pickle.loads(pickle.dumps(led, protocol=5))

    restored.transfer("GOV", "h", 0.1)

    assert hasattr(restored, "_a5_roundoff_drift")
    restored.assert_conserved()


def test_write_off_conserves_and_hits_bank_equity():
    """Bad-debt writeoff (v4): net worth invariant; the bank's deposits absorb the loss."""
    led = Ledger({"h": 100.0, "f": 0.0, "BANK": 50.0})
    M = led.genesis_money
    led.create_loan("f", 40.0)          # f: deposits 40, debt 40
    led.transfer("f", "h", 40.0)        # f spends the loan (broad money now in h); f: D0 L40
    led.write_off("f", "BANK", 40.0)    # firm bankrupt, bank equity absorbs 40
    assert led.debt("f") == 0.0
    assert led.balance("BANK") == 10.0          # bank equity 50 - 40
    assert abs(led.net_worth - M) < 1e-12       # A5 intact (redistributed, not lost)
    led.assert_conserved()


def test_write_off_can_make_bank_insolvent():
    """If writeoffs exceed bank equity, bank deposits go negative (insolvency) -- allowed
    and observed, not an A4 halt."""
    led = Ledger({"h": 100.0, "f": 0.0, "BANK": 10.0})
    led.allow_negative("BANK")
    led.create_loan("f", 40.0); led.transfer("f", "h", 40.0)
    led.write_off("f", "BANK", 40.0)            # 40 loss vs 10 equity
    assert led.balance("BANK") == -30.0         # bank insolvent
    led.assert_conserved()                       # A5 still holds
    led.assert_non_negative()                    # bank exempt -> does NOT raise


def test_add_and_remove_account_conserve():
    led = Ledger({"h": 100.0, "BANK": 0.0})
    M = led.genesis_money
    led.add_account("newfirm")                   # 0 deposits, 0 debt -> M unchanged
    assert led.net_worth == M
    led.transfer("h", "newfirm", 30.0)           # household funds the startup (conserving)
    assert led.balance("newfirm") == 30.0
    led.assert_conserved()
    led.transfer("newfirm", "h", 30.0)           # drain it back to 0 before removal
    led.remove_account("newfirm")
    assert led.net_worth == M
    led.assert_conserved()


def test_remove_nonzero_account_raises():
    led = Ledger({"h": 100.0})
    led.add_account("f"); led.transfer("h", "f", 10.0)
    try:
        led.remove_account("f")                  # f still holds 10 -> must refuse
    except ValueError:
        pass
    else:
        raise AssertionError("removing a nonzero account should raise")


def test_remove_account_rejects_sub_tolerance_deposit_or_debt_dust():
    """Account deletion must never use the operational float tolerance as a sink."""
    for kind in ("deposit", "debt"):
        led = Ledger({"h": 100.0, "f": 0.0})
        if kind == "deposit":
            led._bal["f"] = 1e-12
        else:
            led._loans["f"] = 1e-12
        try:
            led.remove_account("f")
        except ValueError:
            pass
        else:
            raise AssertionError(f"removing {kind} dust should raise")


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fails = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            fails += 1; print(f"  FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    return fails


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
