"""Foundation tests for the Ledger (spec §7.6, §8.2).

The ledger is the one module whose bugs would silently poison everything above
it, so it gets pinned down first. These tests assert the three things that make
A1/M0/A4 unbreakable-by-construction:

  * transfer moves money atomically and conserves the total (A1 / M0),
  * negative amounts and overdrafts are rejected (A4, no credit in the kernel),
  * a long randomized sequence of transfers never drifts the money stock.

Zero external dependencies: run directly with ``python3 tests/test_conservation.py``
(also collectible by pytest if installed). Uses only the stdlib ``random`` with a
fixed seed so it is reproducible (spec §7.6: everything seeded).
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger import ConservationError, Ledger, OverdraftError  # noqa: E402


def test_basic_transfer_conserves():
    led = Ledger({"h": 100.0, "f": 50.0})
    led.transfer("h", "f", 30.0)
    assert led.balance("h") == 70.0
    assert led.balance("f") == 80.0
    assert led.total_money == 150.0
    led.assert_conserved()


def test_reject_negative_amount():
    led = Ledger({"h": 100.0, "f": 50.0})
    try:
        led.transfer("h", "f", -10.0)
    except ValueError:
        pass
    else:
        raise AssertionError("negative transfer should raise ValueError")
    # balances untouched (atomic: reject before mutating)
    assert led.balance("h") == 100.0 and led.balance("f") == 50.0


def test_reject_overdraft():
    led = Ledger({"h": 40.0, "f": 0.0})
    try:
        led.transfer("h", "f", 40.01)
    except OverdraftError:
        pass
    else:
        raise AssertionError("overdraft should raise OverdraftError")
    assert led.balance("h") == 40.0 and led.balance("f") == 0.0


def test_spend_exact_full_balance_allowed():
    # A spend of exactly the whole balance must succeed (A4 is <=, not <).
    led = Ledger({"h": 40.0, "f": 0.0})
    led.transfer("h", "f", 40.0)
    assert led.balance("h") == 0.0 and led.balance("f") == 40.0
    led.assert_conserved()


def test_zero_transfer_is_noop():
    led = Ledger({"h": 40.0, "f": 10.0})
    led.transfer("h", "f", 0.0)  # rationed-to-zero trade is normal, not an error
    assert led.balance("h") == 40.0 and led.balance("f") == 10.0


def test_reject_negative_initial_balance():
    try:
        Ledger({"h": -1.0})
    except ValueError:
        pass
    else:
        raise AssertionError("negative genesis endowment should raise ValueError")


def test_unknown_account_raises():
    led = Ledger({"h": 10.0})
    for call in (lambda: led.transfer("h", "ghost", 1.0), lambda: led.transfer("ghost", "h", 1.0)):
        try:
            call()
        except KeyError:
            pass
        else:
            raise AssertionError("transfer touching an unknown account should raise KeyError")


def test_randomized_sequence_conserves():
    """Stress: thousands of random legal transfers must never drift M (M0)."""
    rng = random.Random(12345)
    ids = [f"a{i}" for i in range(30)]
    led = Ledger({aid: rng.uniform(0.0, 1000.0) for aid in ids})
    M0 = led.genesis_money

    for _ in range(20_000):
        src, dst = rng.sample(ids, 2)
        bal = led.balance(src)
        if bal <= 0.0:
            continue
        amount = rng.uniform(0.0, bal)  # always affordable
        led.transfer(src, dst, amount)
        led.assert_conserved()  # gate every single step

    # After 20k float transfers, drift must still be within tolerance.
    assert abs(led.total_money - M0) < 1e-6 * M0, f"drift {led.total_money - M0!r}"
    led.assert_non_negative()


def test_conservation_error_is_detectable():
    # Sanity-check the gate itself: corrupting a balance directly must trip it.
    led = Ledger({"h": 100.0, "f": 100.0})
    led._bal["h"] += 5.0  # simulate a rogue write that bypassed transfer
    try:
        led.assert_conserved()
    except ConservationError:
        pass
    else:
        raise AssertionError("assert_conserved should catch injected money")


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
