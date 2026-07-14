"""diagnostic_v221.png — migration & remittances (PLAN_v22).

A low-wage and a high-wage economy. Labor migrates toward the higher wage (a residency
stock); migrants remit home. Panels: migrant stock, remittance inflow, and the labor-
exporter's current account WITH vs WITHOUT remittances — the remittance wedge that turns a
trade deficit into a current-account surplus (the Philippines/Bangladesh pattern).

    PYTHONPATH=$(pwd) uv run python scripts_v20/plot_v221.py
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


def main() -> None:
    poor = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=300, seed=0, a=0.7)
    rich = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=300, seed=0, a=1.3)
    w = World([poor, rich], base_seed=9, trade=True, capital=True, migration=True,
              capital_mobility=1.0, migration_rate=0.03, remittance_share=0.2)
    w.run()
    wr = w.world_records
    t = [r["t"] for r in wr]

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    axes[0].plot(t, [r["migrant_stock"][0] for r in wr], label="poor (sender)", lw=1.3)
    axes[0].plot(t, [r["migrant_stock"][1] for r in wr], label="rich (host)", lw=1.3)
    axes[0].set_title("migrant stock (residency)")
    axes[1].plot(t, [r["remittances"][0] for r in wr], label="poor (receiver)", lw=1.3)
    axes[1].plot(t, [r["remittances"][1] for r in wr], label="rich", lw=1.3)
    axes[1].set_title("remittance inflow (numéraire)")
    axes[2].plot(t, [r["current_account"][0] for r in wr], label="CA (with remittances)", lw=1.3)
    axes[2].plot(t, [r["current_account"][0] - r["remittances"][0] for r in wr],
                 "--", label="trade + factor only", lw=1.0, alpha=0.8)
    axes[2].axhline(0, color="k", lw=0.5)
    axes[2].set_title("poor economy current account")
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("v22.1 — migration & remittances: labor exporter's remittances lift its current account", fontsize=12)
    fig.tight_layout()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "diagnostic_v221.png")
    fig.savefig(out, dpi=110)
    print(f"wrote {os.path.normpath(out)}")


if __name__ == "__main__":
    main()
