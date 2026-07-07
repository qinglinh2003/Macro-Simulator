"""Render the v6 diagnostic dashboards (aligned with diagnostic_v2/v3/v4): the stable core
(Config.v6) and the bubble regime (Config.v6_bubble)."""
from config import Config
from economy import Economy
from diagnostics import plot_dashboard_v6

K = dict(n_firms_c=120, n_firms_k=60, n_households=1200, n_ticks=2000, seed=0)

core = Economy(Config.v6(**K)).run()
plot_dashboard_v6(core, "diagnostic_v6.png",
                  title="v6 run — stable core (capital market on, w_chartist=0.2, wealth_effect off)")
print("saved diagnostic_v6.png")

bub = Economy(Config.v6_bubble(**K)).run()
plot_dashboard_v6(bub, "diagnostic_v6_bubble.png",
                  title="v6 run — bubble regime (w_chartist=20): q spikes ~15x then crashes, A5 intact")
print("saved diagnostic_v6_bubble.png")
