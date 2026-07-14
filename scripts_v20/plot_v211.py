"""diagnostic_v211.png — the capital account: yield-driven NFA (PLAN_v21 §1).

A high-rate and a low-rate economy trade with an open capital account. Capital flows to the
high-rate economy: it runs a persistent net-foreign-DEBTOR position (NFA < 0) and pays
factor income abroad (GNP < GDP); the low-rate economy is the creditor. The v20 mean-
reverting (no-capital) NFA is overlaid — capital deepens the position.

    PYTHONPATH=$(pwd) uv run python scripts_v20/plot_v211.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from macro_sim.config import Config  # noqa: E402
from macro_sim.world import World  # noqa: E402


def _mk(r):
    return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=300, seed=0, r_interest=r)


def main() -> None:
    on = World([_mk(0.06), _mk(0.02)], base_seed=9, trade=True, capital=True,
               capital_mobility=3.0, capital_adjust=0.2)
    on.run()
    off = World([_mk(0.06), _mk(0.02)], base_seed=9, trade=True)  # v20, no capital
    off.run()
    won, woff = on.world_records, off.world_records
    t = [r["t"] for r in won]

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    axes[0].plot(t, [r["nfa"][0] for r in won], label="hi-rate (capital)", lw=1.2)
    axes[0].plot(t, [r["nfa"][1] for r in won], label="lo-rate (capital)", lw=1.2)
    axes[0].plot(t, [r["nfa"][0] for r in woff], "--", label="hi-rate (v20 no-capital)", lw=0.8, alpha=0.7)
    axes[0].axhline(0, color="k", lw=0.5)
    axes[0].set_title("net foreign asset position (NFA)")
    axes[1].plot(t, [r["e"][0] for r in won], label="e hi-rate", lw=1.2)
    axes[1].plot(t, [r["e"][1] for r in won], label="e lo-rate", lw=1.2)
    axes[1].set_title("exchange rate")
    axes[2].plot(t, [r["factor_income"][0] for r in won], label="hi-rate", lw=1.2)
    axes[2].plot(t, [r["factor_income"][1] for r in won], label="lo-rate", lw=1.2)
    axes[2].axhline(0, color="k", lw=0.5)
    axes[2].set_title("factor income (GNP−GDP wedge)")
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("v21.1 — international capital: high-rate economy = net debtor, pays factor income (the carry)", fontsize=12)
    fig.tight_layout()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "diagnostic_v211.png")
    fig.savefig(out, dpi=110)
    print(f"wrote {os.path.normpath(out)}")


if __name__ == "__main__":
    main()
