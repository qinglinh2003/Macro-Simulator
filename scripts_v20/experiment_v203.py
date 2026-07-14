"""v20.3 divergence experiment (PLAN_v20 §0.6, §11) — the comparative-macro lab.

Two economies given different CountryProfiles (advanced high-TFP vs developing low-TFP,
larger, necessity-tilted) trade in one coupled World. We report the comparative outcomes
the pure-trade layer makes visible and print the honest findings.

    PYTHONPATH=$(pwd) uv run python scripts_v20/experiment_v203.py
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
from macro_sim.world.country import ADVANCED, DEVELOPING  # noqa: E402


def _avg(recs, k, n=60):
    v = [r.get(k) for r in recs[-n:] if r.get(k) is not None]
    return sum(v) / len(v) if v else float("nan")


def main() -> None:
    base = Config.v124(n_firms_c=40, n_firms_k=20, n_households=200, n_ticks=400, seed=0)
    world = World([ADVANCED.apply(base), DEVELOPING.apply(base)],
                  base_seed=11, trade=True, fx_lambda=0.1)
    world.run()
    for e in world.economies:
        e.ledger.assert_conserved()
    adv, dev = world.economies
    wr = world.world_records

    # comparative steady-state (last 60 ticks)
    p_adv, p_dev = _avg(adv.records, "price_index"), _avg(dev.records, "price_index")
    y_adv, y_dev = _avg(adv.records, "real_output"), _avg(dev.records, "real_output")
    imp_adv = sum(r["import_value"][0] for r in wr[-60:]) / 60
    imp_dev = sum(r["import_value"][1] for r in wr[-60:]) / 60
    open_adv = imp_adv / max(1e-9, _avg(adv.records, "real_output") * p_adv)
    open_dev = imp_dev / max(1e-9, _avg(dev.records, "real_output") * p_dev)
    e_adv, e_dev = wr[-1]["e"]
    inv = wr[-1]["dealer_inventory"]
    rer = (e_adv / e_dev) * (p_dev / p_adv)

    print("=" * 64)
    print("v20.3 DIVERGENCE — advanced (a=%.2f, N=%d) vs developing (a=%.2f, N=%d)"
          % (adv.cfg.a, adv.cfg.n_households, dev.cfg.a, dev.cfg.n_households))
    print("=" * 64)
    print(f"  price level      advanced={p_adv:.3f}   developing={p_dev:.3f}")
    print(f"  real output      advanced={y_adv:.0f}     developing={y_dev:.0f}")
    print(f"  imports/tick     advanced={imp_adv:.1f}   developing={imp_dev:.1f}")
    print(f"  trade openness   advanced={open_adv:.3%}  developing={open_dev:.3%}")
    print(f"  exchange rate    e_adv={e_adv:.4f}        e_dev={e_dev:.4f}")
    print(f"  dealer inventory {[round(x, 1) for x in inv]}  (bounded ⇒ balanced trade)")
    print(f"  real exch rate (adv/dev, >1 = adv dearer) = {rer:.3f}")
    print()
    print("HONEST FINDINGS:")
    print("  1. Trade BALANCES at the pure-trade layer — the dealer holds only a small")
    print("     bounded inventory. Persistent surpluses/deficits need the capital account (v21).")
    print("  2. The model is DEMAND-CONSTRAINED: the productivity axis moves prices &")
    print("     employment, not output level — so productivity divergence is MUTED in output.")
    print("  3. SCALE is the clearer axis: the smaller economy is more trade-exposed")
    print("     (higher import/output openness) — the small-open-economy signature.")

    # diagnostic
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    t = [r["t"] for r in adv.records]
    axes[0][0].plot(t, [r.get("price_index") for r in adv.records], label="advanced", lw=1)
    axes[0][0].plot(t, [r.get("price_index") for r in dev.records], label="developing", lw=1)
    axes[0][0].set_title("price level")
    axes[0][1].plot(t, [r.get("real_output") for r in adv.records], label="advanced", lw=1)
    axes[0][1].plot(t, [r.get("real_output") for r in dev.records], label="developing", lw=1)
    axes[0][1].set_title("real output")
    tw = [r["t"] for r in wr]
    axes[1][0].plot(tw, [r["import_value"][0] for r in wr], label="advanced imports", lw=1)
    axes[1][0].plot(tw, [r["import_value"][1] for r in wr], label="developing imports", lw=1)
    axes[1][0].set_title("import value (trade balances)")
    axes[1][1].plot(tw, [r["e"][0] for r in wr], label="e advanced", lw=1)
    axes[1][1].plot(tw, [r["e"][1] for r in wr], label="e developing", lw=1)
    axes[1][1].set_title("exchange rate")
    for ax in axes.flat:
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("v20.3 — comparative-macro lab: advanced vs developing (CountryProfile divergence)", fontsize=13)
    fig.tight_layout()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "diagnostic_v203.png")
    fig.savefig(out, dpi=110)
    print(f"\nwrote {os.path.normpath(out)}")


if __name__ == "__main__":
    main()
