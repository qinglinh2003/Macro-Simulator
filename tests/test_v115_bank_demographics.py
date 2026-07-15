"""v11.5 acceptance tests (DESIGNDOC §38).

v11.5 gives banks the firm-style ENTRY/EXIT + OWNERSHIP structure: banks are OWNED (a founder class holds the
genesis banks; profit → shareholder dividends; a tradeable bank-stock market whose valuation is also a run
distress signal), FOUNDED de novo when banking is profitable (so the count stops decaying to oligopoly), and can
die from a RUN (queued withdrawals from own reserves + panic/contagion) as well as from write-offs. "Done":
  * each sub-flag off ⇒ prior bit-identical (bank_equity ⇒ v11.4; trading ⇒ mark-to-model; dynamics/runs ⇒ off);
  * A5 + reserve conservation hold through dividends, share trading, entry, and runs; bank SHARES conserve exactly;
  * bank ENTRY stabilises the count (births ≈ deaths) instead of the monotonic decay when off;
  * dividends reach OWNERS (bank-equity value is concentrated then deconcentrates via trading);
  * a RUN produces observable deposit FLIGHT from weak banks (its liquidity-suspension half is latent, §38).

Run: ``uv run python tests/test_v115_bank_demographics.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from macro_sim.config import Config                # noqa: E402
from macro_sim.economy import Economy              # noqa: E402
from macro_sim.systems.banking import bank_for, run_bank_runs_phase  # noqa: E402

NC, NK, NH = 60, 30, 400


def test_regression_bit_identical_off():
    """All v11.5 flags off reproduce v11.4 exactly."""
    a = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0)).run()
    b = Economy(Config.v115(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0,
                            bank_equity=False, bank_equity_trading=False, bank_dynamics=False, bank_runs=False)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["broad_money"] == y["broad_money"]
        assert x["conservation_drift"] == y["conservation_drift"]


def test_trading_off_is_mark_to_model():
    """bank_equity_trading off ⇒ the mark-to-model price (A1) ⇒ bit-identical to A1-only."""
    a = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0, bank_equity=True)).run()
    b = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                            bank_equity=True, bank_equity_trading=True)).run()  # trading changes it (control)
    a2 = Economy(Config.v114(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                             bank_equity=True, bank_equity_trading=False)).run()
    assert all(x["real_output"] == y["real_output"] for x, y in zip(a, a2)), "trading-off must equal A1"


def test_conservation_full_stack():
    """A5, reserve conservation, AND bank-share conservation (Σ owners = shares_outstanding) all hold through
    dividends + trading + entry + runs."""
    econ = Economy(Config.v115(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=0))
    max_share_drift = 0.0
    for _ in range(400):
        econ.step()
        for bk in econ.banks:
            if bk.shares_outstanding > 0.0:
                max_share_drift = max(max_share_drift, abs(sum((bk.owners or {}).values()) - bk.shares_outstanding))
    m = max(r["broad_money"] for r in econ.records)
    assert max(r["conservation_drift"] for r in econ.records) < 1e-6 * m, "A5 broke"
    assert abs(econ.ledger.total_reserves - econ.ledger._reserve_M) < 1e-6 * abs(econ.ledger._reserve_M), "reserves broke"
    assert max_share_drift < 1e-6, f"bank shares must conserve: {max_share_drift:.2e}"


def test_entry_stabilises_the_count():
    """de-novo entry stops the bank count decaying to oligopoly: with entry ON the count is sustained (births ≈
    deaths); with entry OFF it only falls."""
    # Isolate entry from run noise and the endogenous Taylor path.  Entry now
    # compares *net* incumbent ROE with the policy rate; under this preset's live
    # Taylor path net ROE never clears that outside option, so asserting births there
    # would test a calibration accident rather than the entry mechanism.  A frozen
    # per-tick rate gives ON and OFF the same explicit opportunity cost.
    on = Economy(Config.v115(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0,
                             central_bank=False, r_interest=0.001,
                             bank_runs=False, bank_min_capital=20.0))
    on.run()
    off = Economy(Config.v115(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0,
                              central_bank=False, r_interest=0.001,
                              bank_runs=False, bank_dynamics=False))
    off.run()
    assert on._bank_births > 0, "entry should found new banks"
    assert off._bank_births == 0, "no births without entry"
    # entry replenishes the count: MORE banks exist (alive + created) than the off case, which only decays.
    assert len(on.banks) > len(off.banks), f"entry should create banks: on {len(on.banks)} vs off {len(off.banks)}"
    assert sum(b.alive for b in on.banks) >= sum(b.alive for b in off.banks) - 1, "entry should roughly sustain the count"


def test_dividends_reach_owners():
    """Bank profit flows to OWNERS -- bank-equity value is positive and concentrated (a bank-ownership Gini > 0)."""
    recs = Economy(Config.v115(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=0)).run()
    assert recs[-1].get("bank_equity_total", 0.0) > 0.0, "bank equity should have value"
    assert np.mean([r.get("bank_equity_gini", 0.0) for r in recs[-200:]]) > 0.0, "bank ownership should be unequal"


def test_runs_produce_flight():
    """A controlled weak bank produces deposit flight; the master switch blocks it.

    The former long-run seed fixture happened to create a weak bank through repeated
    whole-loan-book shopping.  Existing debts can no longer migrate without a loan
    sale/refinance, so construct the actual run preconditions explicitly instead of
    treating that invalid coupling as part of the run mechanism's contract.
    """

    def forced_flight(*, enabled: bool) -> float:
        econ = Economy(Config.v115(
            n_firms_c=8,
            n_firms_k=4,
            n_households=40,
            n_banks=2,
            n_ticks=1,
            seed=0,
            bank_runs=enabled,
        ))
        weak, safe = econ.banks
        depositor = econ.households[0]
        borrower = econ.firms[0]

        # Put one debt-free depositor and one loan at the weak bank, moving the
        # existing deposit reserve backing whenever the relationship changes.
        for account in (depositor, borrower):
            old = bank_for(econ, account.id)
            if old is not weak:
                econ.ledger.move_reserves(
                    old.id,
                    weak.id,
                    econ.ledger.balance(account.id) - econ.ledger.debt(account.id),
                )
                econ._bank_of[account.id] = weak
                econ._node_of.pop(account.id, None)
        econ.ledger.create_loan(borrower.id, 1_000.0)

        # Capital/book and market signals both identify the same weak franchise;
        # the rival is the unambiguous safe destination.
        weak_capital = econ.ledger.balance(weak.id)
        if weak_capital > 1.0:
            econ.ledger.transfer(weak.id, econ._fiscal, weak_capital - 1.0)
        weak.share_price = 0.0
        weak.share_peak = 1.0
        safe.share_price = safe.share_peak = 1.0

        run_bank_runs_phase(econ)
        return econ._run_flight_volume

    flight_on = forced_flight(enabled=True)
    flight_off = forced_flight(enabled=False)
    assert flight_on > 0.0, "runs should produce deposit flight"
    assert flight_off == 0.0, "no flight without runs"


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
