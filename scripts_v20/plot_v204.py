"""diagnostic_v204.png — N=3 coupled economies (PLAN_v20 §11 v20.4).

Three economies trade multilaterally. Panels: exchange rates (all vs the numéraire
basket), dealer inventory per currency, and per-economy import value. Cross-rates are
triangular-consistent by construction; a vehicle currency (the dominant source) emerges.

    PYTHONPATH=$(pwd) uv run python scripts_v20/plot_v204.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from macro_sim.config import Config  # noqa: E402
from macro_sim.world import World  # noqa: E402


def main() -> None:
    cfg = lambda: Config.v124(n_firms_c=30, n_firms_k=15, n_households=150, n_ticks=300, seed=0)
    world = World([cfg(), cfg(), cfg()], base_seed=5, trade=True, fx_lambda=0.1)
    world.run()
    wr = world.world_records
    t = [r["t"] for r in wr]
    vehicle = Counter(s for s in world._import_source if s >= 0).most_common(1)[0][0]

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    for i in range(3):
        lab = f"economy {i}" + ("  (vehicle)" if i == vehicle else "")
        axes[0].plot(t, [r["e"][i] for r in wr], label=lab, lw=1)
        axes[1].plot(t, [r["dealer_inventory"][i] for r in wr], label=f"curr {i}", lw=1)
        axes[2].plot(t, [r["import_value"][i] for r in wr], label=f"economy {i}", lw=1)
    axes[0].set_title("exchange rate (numéraire basket)")
    axes[1].set_title("dealer inventory per currency (trade balance)")
    axes[2].set_title("import value")
    r = world.rates
    rt = r.bilateral(0, 1) * r.bilateral(1, 2) * r.bilateral(2, 0)
    axes[0].annotate(f"triangular round-trip = {rt:.10f}", xy=(0.03, 0.03),
                     xycoords="axes fraction", fontsize=8)
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle(f"v20.4 — N=3 multilateral trade (vehicle currency: economy {vehicle})", fontsize=13)
    fig.tight_layout()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "diagnostic_v204.png")
    fig.savefig(out, dpi=110)
    print(f"vehicle currency = economy {vehicle}; triangular round-trip = {rt:.12f}")
    print(f"wrote {os.path.normpath(out)}")


if __name__ == "__main__":
    main()
