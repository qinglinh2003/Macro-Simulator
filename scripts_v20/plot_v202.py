"""diagnostic_v202.png — the first real L2: dealer-routed cross-border trade.

Left column: two IDENTICAL economies (clones) — trade flows but nets to zero (the quiet
baseline). Right column: two independent draws — trade flows, a small imbalance appears and
the exchange rate gropes to clear it. Panels: import value, dealer inventory (the trade
balance), and the exchange rate.

    PYTHONPATH=$(pwd) uv run python scripts_v20/plot_v202.py
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


def _cfg() -> Config:
    return Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=250, seed=0)


def _run(base_seed):
    w = World([_cfg(), _cfg()], base_seed=base_seed, trade=True, fx_lambda=0.1)
    w.run()
    return w.world_records


def main() -> None:
    clones = _run(None)      # same seed ⇒ symmetric
    diverse = _run(9)        # independent draws

    fig, axes = plt.subplots(3, 2, figsize=(13, 9))
    for col, (recs, title) in enumerate(
        [(clones, "identical economies (quiet baseline)"), (diverse, "independent draws")]
    ):
        t = [r["t"] for r in recs]
        axes[0][col].plot(t, [r["import_value"][0] for r in recs], label="econ 0 imports", lw=1)
        axes[0][col].plot(t, [r["import_value"][1] for r in recs], label="econ 1 imports", lw=1)
        axes[0][col].set_title(f"import value — {title}")
        axes[1][col].plot(t, [r["dealer_inventory"][0] for r in recs], label="dealer curr0", lw=1)
        axes[1][col].plot(t, [r["dealer_inventory"][1] for r in recs], label="dealer curr1", lw=1)
        axes[1][col].set_title("dealer inventory (trade balance)")
        axes[2][col].plot(t, [r["e"][0] for r in recs], label="e0", lw=1)
        axes[2][col].plot(t, [r["e"][1] for r in recs], label="e1", lw=1)
        axes[2][col].set_title("exchange rate (numéraire basket)")
        for row in range(3):
            axes[row][col].grid(alpha=0.3)
            axes[row][col].legend(fontsize=8)
    fig.suptitle("v20.2 — cross-border trade: balanced under symmetry, groping clears imbalance", fontsize=13)
    fig.tight_layout()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "diagnostic_v202.png")
    fig.savefig(out, dpi=110)
    print(f"wrote {os.path.normpath(out)}")


if __name__ == "__main__":
    main()
