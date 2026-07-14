"""diagnostic_v200.png — the `World` container runs N economies independently.

Two structurally-identical economies (same config, different seed) run side by side in
one N=2 World with NO coupling (v20.0). The panels show they evolve as genuinely
independent draws — the visual counterpart of the bit-identity gate.

    PYTHONPATH=$(pwd) uv run python scripts_v20/plot_v200.py
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

SERIES = [
    ("price_index", "price index"),
    ("real_output", "real output"),
    ("unemployment_rate", "unemployment"),
    ("hh_wealth_gini", "wealth Gini"),
]


def main() -> None:
    cfg = lambda: Config.v124(n_firms_c=60, n_firms_k=30, n_households=400, n_ticks=400, seed=0)
    world = World([cfg(), cfg()], base_seed=2024)
    world.run()

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for ax, (key, title) in zip(axes.flat, SERIES):
        for i, econ in enumerate(world.economies):
            ys = [r.get(key, float("nan")) for r in econ.records]
            ax.plot(ys, label=f"economy {i} ({econ.currency})", lw=1.1)
        ax.set_title(title)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("v20.0 — two independent economies in one uncoupled World (N=2)", fontsize=13)
    fig.tight_layout()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "diagnostic_v200.png")
    fig.savefig(out, dpi=110)
    print(f"wrote {os.path.normpath(out)}")


if __name__ == "__main__":
    main()
