"""Entrypoint for v3 -- banks + endogenous money (DESIGNDOC §12).

Runs the v3 economy, logs it, writes the v3 dashboard, sweeps the leverage knob
kappa (the credit-cycle / Minsky dial), and prints the §12.8 acceptance readout:
does A5 hold, is broad money endogenous (alive), does credit relax the cash
constraint, and does it mitigate the v2 long-run deterioration? No CLI.
"""

from __future__ import annotations

import statistics

from config import Config
from diagnostics import plot_cross_run, plot_dashboard_v3, seed_invariance
from economy import Economy
from run import print_index_table
from runlog import RunLogger, load_index, run_sweep


def _tail(recs, key, frac=0.75):
    return statistics.fmean(r.get(key, 0.0) for r in recs[int(len(recs) * frac):])


def main() -> None:
    logger = RunLogger("runs")
    TICKS = 2000   # at the 500C/250K/5000H default this is ~26s/run (~30s budget)

    # -- v2 reference (credit-less long-run deterioration) ---------------------
    v2 = Economy(Config.v2(n_ticks=TICKS, seed=0)).run()

    # -- v3 baseline, logged ---------------------------------------------------
    cfg = Config.v3(n_ticks=TICKS, seed=0)
    print(f"v3 baseline: N_H={cfg.n_households} N_C={cfg.n_firms_c} N_K={cfg.n_firms_k} "
          f"ticks={cfg.n_ticks} | kappa={cfg.kappa} r={cfg.r_interest} amort={cfg.amort}")
    econ = Economy(cfg)
    records = econ.run()
    summary = logger.log(cfg, records, label="v3-baseline", tags=["v3", "baseline"],
                         protocol=econ.protocol.name)
    led = econ.ledger

    # -- §12.8 acceptance readout ----------------------------------------------
    print(f"\nA5 conservation: net_worth={led.net_worth:.6f}  M={led.genesis_money:.1f}  "
          f"max_drift={max(r['conservation_drift'] for r in records):.2e}")
    bm = [r["broad_money"] for r in records]
    print(f"Broad money ΣD: min={min(bm):.0f} max={max(bm):.0f}  -> "
          f"{'ALIVE (endogenous)' if max(bm) - min(bm) > 1 else 'FLAT (inert)'}")
    print(f"Outstanding credit ΣL (end): {led.total_credit:.0f}  "
          f"(wage-credit total={sum(r['credit_wage'] for r in records):.0f}, "
          f"investment={sum(r['credit_investment'] for r in records):.0f})")
    print("\nLong-run mitigation vs v2 (last-quarter tail):")
    print(f"  unemployment:  v2={_tail(v2,'unemployment_rate'):.3f}  v3={_tail(records,'unemployment_rate'):.3f}")
    print(f"  real output:   v2={_tail(v2,'real_output'):7.1f}  v3={_tail(records,'real_output'):7.1f}")
    print(f"  hh money share:v2={_tail(v2,'hh_money_share'):.3f}  v3={_tail(records,'hh_money_share'):.3f}")

    plot_dashboard_v3(records, path="diagnostic_v3.png", title=f"v3 baseline (kappa={cfg.kappa}, r={cfg.r_interest})")
    plot_dashboard_v3(records, path=f"{summary['meta']['run_dir']}/dashboard_v3.png")
    print("\n  v3 dashboard -> diagnostic_v3.png (+ run dir)")

    # -- sweep the leverage knob kappa (the Minsky / credit-cycle dial) --------
    print("\nSweep over leverage kappa:")
    run_sweep(cfg, {"kappa": [2.0, 3.0, 5.0, 8.0]}, logger, tags=["v3", "kappa-sweep"])
    rows = [r for r in load_index("runs") if (r.get("label") or "").startswith("kappa=")]
    cols = ["cfg_kappa", "m_unemployment_rate", "m_real_output",
            "m_total_credit", "m_aggregate_leverage", "m_broad_money", "max_drift"]
    print_index_table(rows, cols)
    plot_cross_run(rows, "cfg_kappa",
                   ["m_unemployment_rate", "m_real_output", "m_total_credit",
                    "m_aggregate_leverage", "m_broad_money", "m_hh_money_share"],
                   path="sweep_v3.png", title="Effect of leverage kappa")
    print("  cross-run sweep figure -> sweep_v3.png")

    # -- seed-invariance (large N) ---------------------------------------------
    print("\nSeed-invariance (seeds 0,1,2; larger N):")
    inv = seed_invariance(cfg, seeds=[0, 1, 2],
                          keys=["price_index", "real_output", "unemployment_rate", "broad_money"])
    for k, s in inv["summary"].items():
        print(f"  {k:20s} mean={s['mean']:.4f}  cv={s['cv']:.3f}  [{'OK' if s['cv'] < 0.15 else 'CHECK'}]")


if __name__ == "__main__":
    main()
