"""v11.3 acceptance tests (DESIGNDOC §36).

v11.3 adds loan-rate COMPETITION on the v11.2 realistic-bank stack. Each bank posts a mean-preserving loan-rate
spread over the policy rate (some undercut, some charge more); borrowers SHOP -- they sample bank_search_m rivals
and switch their whole relationship to the cheapest bank that has capacity to fund it. So market share is won on
price + capacity (not assigned at genesis): cheap, well-capitalized banks grow their loan book and concentration
/ too-big-to-fail EMERGES. "Done":
  * competition OFF (or n_banks=1) ⇒ bit-identical to v11.2 (one system rate, no shopping);
  * money (A5) conserves with competition on;
  * the spreads are mean-preserving -- the AVERAGE loan rate is unchanged, only the dispersion is new;
  * a realized cross-borrower rate dispersion EMERGES (banks charge different rates);
  * loan-book concentration (HHI) EMERGES above the even-split floor (share won on price, not handed out).

Run: ``uv run python tests/test_v113_competition.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                       # noqa: E402
from config import Config                # noqa: E402
from economy import Economy              # noqa: E402

NC, NK, NH = 100, 50, 1000


def test_regression_bit_identical_off():
    """Competition OFF reproduces v11.2 exactly (no spreads, no shopping)."""
    a = Economy(Config.v112(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0)).run()
    b = Economy(Config.v113(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=300, seed=0,
                            bank_rate_competition=False)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["broad_money"] == y["broad_money"]
        assert x["conservation_drift"] == y["conservation_drift"]


def test_single_bank_bit_identical():
    """With n_banks=1 the competition flag is inert (one bank ⇒ no rivals to undercut) ⇒ v10.2 exactly."""
    a = Economy(Config.v102(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0)).run()
    b = Economy(Config.v113(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=250, seed=0, n_banks=1)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["broad_money"] == y["broad_money"]


def test_conservation_with_competition():
    """Money (A5) conserves with competition on -- shopping only moves the loan RELATIONSHIP between books;
    interest is still a plain transfer and no money is created or destroyed."""
    recs = Economy(Config.v113(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    m = max(r["broad_money"] for r in recs)
    assert max(r["conservation_drift"] for r in recs) < 1e-6 * m


def test_spreads_are_mean_preserving():
    """The per-bank spreads sum (mean) to ~0 -- competition is a DISPERSION, not a level change to the average
    cost of credit (so it isolates the sorting/competition mechanism, §0-ii)."""
    econ = Economy(Config.v113(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=10, seed=0))
    spreads = list(econ._bank_spread.values())
    assert len(spreads) == Config.v113().n_banks
    assert abs(sum(spreads)) < 1e-12, f"spreads should be mean-preserving: sum={sum(spreads)}"
    assert np.std(spreads) > 0.0, "with disp>0 the spreads should actually disperse"


def test_rate_dispersion_emerges():
    """A realized cross-borrower loan-rate dispersion emerges (banks charge different rates); it is ~zero
    when competition is off."""
    on = Economy(Config.v113(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    off = Economy(Config.v112(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=600, seed=0)).run()
    sd_on = np.mean([r.get("bank_rate_spread_sd", 0.0) for r in on[-300:]])
    sd_off = np.mean([r.get("bank_rate_spread_sd", 0.0) for r in off[-300:]])
    assert sd_on > 1e-5, f"loan-rate dispersion should emerge with competition: {sd_on:.2e}"
    assert sd_off < 1e-9, f"no dispersion without competition: {sd_off:.2e}"


def test_concentration_emerges():
    """Loan-book concentration (HHI) rises above the even-split floor (1/n_banks): market share is WON on
    price + capacity by cheap, well-capitalized banks, not handed out equally."""
    recs = Economy(Config.v113(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=800, seed=0)).run()
    n = float(Config.v113().n_banks)
    hhi = np.mean([r.get("bank_loanbook_hhi", 0.0) for r in recs[-300:]])
    assert hhi > 1.0 / n + 1e-3, f"competition should concentrate loan books above the 1/n floor: HHI={hhi:.3f} vs {1/n:.3f}"


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
