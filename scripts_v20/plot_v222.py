"""diagnostic_v222.png — migration POLICY (PLAN_v22): immigration cap + remittance tax.

The government's two run-time levers on the people flow. Left: an immigration quota on the
host throttles the migrant stock (blocking wage convergence). Right: an origin remittance
tax diverts part of the inflow to the fiscal account (revenue vs the net reaching households).

    PYTHONPATH=$(pwd) uv run python scripts_v20/plot_v222.py
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


def _pair():
    return (Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=300, seed=0, a=0.7),
            Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=300, seed=0, a=1.3))


def _run(**kw):
    w = World([*_pair()], base_seed=9, trade=True, capital=True, migration=True,
              capital_mobility=1.0, migration_rate=0.03, remittance_share=0.2, **kw)
    w.run()
    return w.world_records


def main() -> None:
    openb = _run()
    capped = _run(immigration_cap=0.03)
    taxed = _run(remittance_tax=0.25)
    t = [r["t"] for r in openb]

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    axes[0].plot(t, [r["migrant_stock"][0] for r in openb], label="open borders", lw=1.3)
    axes[0].plot(t, [r["migrant_stock"][0] for r in capped], label="immigration cap 3%", lw=1.3)
    axes[0].set_title("migrant stock — the immigration quota")
    axes[1].plot(t, [r["remittances"][0] for r in taxed], label="net to households", lw=1.3)
    axes[1].plot(t, [r["remittance_tax_rev"][0] for r in taxed], label="tax → fiscal", lw=1.3)
    axes[1].plot(t, [r["remittances"][0] for r in openb], "--", label="no tax (gross)", lw=0.9, alpha=0.7)
    axes[1].set_title("remittances — the 25% remittance tax")
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("v22 migration POLICY — immigration quota throttles the flow; remittance tax funds the fiscus", fontsize=12)
    fig.tight_layout()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "diagnostic_v222.png")
    fig.savefig(out, dpi=110)
    print(f"wrote {os.path.normpath(out)}")


if __name__ == "__main__":
    main()
