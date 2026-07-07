"""v5 competition phase diagram: firm-size Gini / markup / #producers over the
m (transparency) x dis_slope (diseconomy) grid, firm_dynamics ON. Diseconomy now
scales with OUTPUT (y*), so slopes are small (overhead dis_slope*y*, y*~100-400).

Tail = mean over the last TAIL ticks, averaged across seeds. Prints three grids and
dumps JSON for the heatmap. Also runs the firm_dynamics-OFF control at one cell."""
import json
import numpy as np
from config import Config
from economy import Economy

MS = [1, 2, 3, 5, 10]
SLOPES = [0.0, 0.001, 0.002, 0.005, 0.01]
SEEDS = [0, 1]
TICKS = 1000
TAIL = 150
NC, NK, NH = 80, 40, 800


def tail_stats(cfg):
    rec = Economy(cfg).run()
    t = rec[-TAIL:]
    return {
        "gini": np.mean([r["firm_size_gini_output"] for r in t]),
        "markup": np.mean([r["avg_markup"] for r in t]),
        "nprod": np.mean([r["n_firms_producing"] for r in t]),
        "nfirms": np.mean([r.get("firm_count_c", np.nan) for r in t]),
    }


def cell(m, slope, fd=True):
    acc = {}
    for sd in SEEDS:
        cfg = Config.v4(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=TICKS,
                        search_m=m, dis_slope=slope, seed=sd)
        cfg.firm_dynamics = fd
        for k, v in tail_stats(cfg).items():
            acc.setdefault(k, []).append(v)
    return {k: float(np.mean(v)) for k, v in acc.items()}


grid = {}
for slope in SLOPES:
    for m in MS:
        grid[(slope, m)] = cell(m, slope)
        c = grid[(slope, m)]
        print(f"slope={slope:<6} m={m:<3} gini={c['gini']:.3f} "
              f"markup={c['markup']:.3f} nprod={c['nprod']:.1f} nC={c['nfirms']:.1f}")


def show(key, title):
    print(f"\n{title}")
    print("        " + "".join(f"m={m:<6}" for m in MS))
    for slope in SLOPES:
        row = "".join(f"{grid[(slope,m)][key]:<8.3f}" for m in MS)
        print(f"slope={slope:<5} | {row}")


show("gini", "PHASE DIAGRAM: firm-size Gini (concentration)")
show("markup", "avg markup")
show("nprod", "# producing firms")

# 3-D control: at the best competition cell (highest m, mid slope), toggle dynamics off.
best = min(grid.items(), key=lambda kv: kv[1]["gini"])
(bs, bm), bstat = best
print(f"\nlowest-Gini cell: slope={bs} m={bm} -> gini={bstat['gini']:.3f} markup={bstat['markup']:.3f}")
ctrl_on = grid[(bs, bm)]
ctrl_off = cell(bm, bs, fd=False)
print(f"  firm_dynamics ON : gini={ctrl_on['gini']:.3f} markup={ctrl_on['markup']:.3f} nprod={ctrl_on['nprod']:.1f}")
print(f"  firm_dynamics OFF: gini={ctrl_off['gini']:.3f} markup={ctrl_off['markup']:.3f} nprod={ctrl_off['nprod']:.1f}")
print("  => competition is", "3-D (needs entry/exit)" if ctrl_off["gini"] > ctrl_on["gini"] + 0.08
      else "2-D (survives without entry/exit)")

json.dump({f"{s}|{m}": grid[(s, m)] for s in SLOPES for m in MS},
          open("phase_data_v5.json", "w"), indent=2)
print("\nsaved phase_data_v5.json")
