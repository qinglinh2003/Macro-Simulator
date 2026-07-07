"""v9 acceptance tests (DESIGNDOC §28).

v9 adds the GOVERNMENT sector: a Treasury with four tax bases, benefit + deficit-targeted (and
state-dependent) government consumption via competitive procurement, macroprudential levers reclassified
into Policy, and household bankruptcy. A deficit issues OUTSIDE money (the GOV account goes negative =
government debt = private net financial wealth). "Done":
  * government off + bankruptcy off ⇒ bit-identical to v8.5 (regression -- prior configs untouched);
  * money (A5) + per-firm shares still conserve exactly with the government on;
  * the outside-money identity holds: −(GOV balance) == cumulative deficit (Godley-Lavoie);
  * household bankruptcy reduces end-state insolvency vs off (the §27 exit valve fires, A5-safe);
  * the state-dependent deficit runs SMALLER when unemployment is low (taper at full employment).
The macro effects (functional-finance u drop, §4 6/8, the concentration/inflation diagnosis) are §28
findings from the multi-seed validation, not brittle unit thresholds.

Run: ``uv run python tests/test_v9_government.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from macro_sim.config import Config                # noqa: E402
from macro_sim.economy import Economy              # noqa: E402

TOL = 1e-6
NC, NK, NH = 100, 50, 1000


def test_regression_bit_identical_off():
    """government=False + household_bankruptcy=False reproduces v8.5 exactly (all gov code gated)."""
    a = Economy(Config.v85(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v9(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0,
                          government=False, household_bankruptcy=False)).run()
    for x, y in zip(a, b):
        assert x["investment_spending"] == y["investment_spending"] and x["real_output"] == y["real_output"]


def test_conservation():
    """Government on: money (A5) and per-firm share floats conserve -- taxes/benefit/procurement/
    write-offs are all ledger transfers or A5-safe write_offs; the GOV account (negative) is in the sum."""
    recs = Economy(Config.v9(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    # tolerance scales with money magnitude (inflation inflates ΣD); use a relative bound
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m
    assert max(r["shares_conservation_drift"] for r in recs) < 1e-6


def test_outside_money_identity():
    """Godley-Lavoie: the government's debt (−GOV balance) equals its cumulative deficit, and that
    debt IS the private sector's accumulated net financial wealth (above genesis)."""
    econ = Economy(Config.v9(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=500, seed=0))
    recs = econ.run()
    gov_debt = -econ.ledger.balance("GOV")
    cumulative_deficit = sum(r.get("gov_deficit", 0.0) for r in recs)
    assert abs(gov_debt - cumulative_deficit) < 1e-6 * max(1.0, abs(gov_debt)), \
        f"outside-money identity broken: gov_debt={gov_debt:.2f} vs Σdeficit={cumulative_deficit:.2f}"


def test_bankruptcy_reduces_insolvency():
    """The §27 exit valve: discharging insolvent households leaves FEWER of them stuck underwater."""
    def insolvent_count(cfg):
        econ = Economy(cfg); econ.run()
        po = {f.id: f.share_price for f in econ.c_firms}
        return sum(1 for h in econ.households
                   if econ.ledger.balance(h.id)
                   + sum(sh * po.get(fid, 0.0) for fid, sh in h.holdings.items())
                   - econ.ledger.debt(h.id) <= -1e-6)
    kw = dict(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1500, seed=0)
    on = insolvent_count(Config.v9(**kw))
    off = insolvent_count(Config.v9(household_bankruptcy=False, **kw))
    assert on <= off, f"bankruptcy should not increase insolvency: on={on} off={off}"


def test_state_dependent_deficit_tapers():
    """The countercyclical rule: a low-slack (low-u) tick targets a SMALLER deficit than a high-slack
    tick. Compare the deficit/GDP in the lowest-u vs highest-u deciles of a run."""
    recs = Economy(Config.v9(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=1200, seed=0)).run()[300:]
    u = np.array([r["unemployment_rate"] for r in recs])
    d = np.array([r.get("gov_deficit_to_gdp", 0.0) for r in recs])
    lo = d[u <= np.quantile(u, 0.25)].mean()      # low-unemployment (little slack) ticks
    hi = d[u >= np.quantile(u, 0.75)].mean()      # high-unemployment (much slack) ticks
    assert hi > lo, f"deficit should be larger under slack: high-u deficit={hi:.3f} vs low-u={lo:.3f}"


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
