"""Headline artifact for §14: the competition phase diagram. Three heatmaps
(firm-size Gini, avg markup, # producing firms) over the m x dis_slope grid, from
phase_data_v5.json (produced by sweep_v5.py). The story is in the LEFT column."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

data = json.load(open("phase_data_v5.json"))
slopes = sorted({float(k.split("|")[0]) for k in data})
ms = sorted({int(k.split("|")[1]) for k in data})


def grid(key):
    return np.array([[data[f"{s}|{m}"][key] for m in ms] for s in slopes])


panels = [
    ("gini", "Firm-size Gini (concentration)", "Reds", None),
    ("markup", "Average markup (monopoly profit)", "Oranges", None),
    ("nprod", "# producing firms", "Greens_r", None),
]
fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
for ax, (key, title, cmap, _) in zip(axes, panels):
    G = grid(key)
    im = ax.imshow(G, cmap=cmap, aspect="auto", origin="lower")
    ax.set_xticks(range(len(ms)), [f"m={m}" for m in ms])
    ax.set_yticks(range(len(slopes)), [f"{s:g}" for s in slopes])
    ax.set_xlabel("information transparency  m  (§11.6)")
    ax.set_ylabel("diseconomy slope  dis_slope")
    ax.set_title(title, fontsize=11)
    for i in range(len(slopes)):
        for j in range(len(ms)):
            ax.text(j, i, f"{G[i,j]:.2f}", ha="center", va="center",
                    fontsize=8, color="black")
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

# mark the competition cell (m=1, dis_slope=0.005) on the Gini panel
if 0.005 in slopes and 1 in ms:
    axes[0].add_patch(plt.Rectangle((ms.index(1) - 0.5, slopes.index(0.005) - 0.5), 1, 1,
                                    fill=False, edgecolor="blue", lw=3))
    axes[0].annotate("competition\n(diseconomy + entry/exit,\nLOW transparency)",
                     xy=(ms.index(1), slopes.index(0.005)), xytext=(1.6, 1.3),
                     fontsize=8, color="blue",
                     arrowprops=dict(arrowstyle="->", color="blue"))

fig.suptitle("v5 competition phase diagram (§14): the low-Gini region is the m=1 COLUMN, "
             "not the pre-registered bottom-right.\nTransparency (m≥2) is antagonistic — "
             "winner-take-all rotates the monopoly instead of thinning it.", fontsize=11)
fig.tight_layout(rect=(0, 0, 1, 0.93))
fig.savefig("phase_diagram_v5.png", dpi=120)
print("saved phase_diagram_v5.png")
