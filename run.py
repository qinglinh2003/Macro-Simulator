"""Entrypoint for the closed monetary kernel (spec roadmap step 1, §8.3).

Runs the kernel, logs every run to the experiment registry (runs/), writes a
diagnostic plot, and runs a small parameter sweep so "config -> outcome" is
recorded systematically. The v1 success bar is only "alive and conserving"
(§7.5). Configure via constants below; no CLI framework, kept minimal.
"""

from __future__ import annotations

from macro_sim.config import Config
from macro_sim.reporting.diagnostics import plot_cross_run, plot_dashboard, seed_invariance
from macro_sim.economy import Economy
from macro_sim.experiments.runlog import RunLogger, load_index, run_and_log, run_sweep


def _fmt(v, w=9, p=3):
    return f"{v:>{w}.{p}f}" if isinstance(v, (int, float)) else f"{str(v):>{w}}"


def print_index_table(rows, cols):
    print("  " + "".join(f"{c.replace('cfg_','').replace('m_',''):>13}" for c in cols))
    for r in rows:
        print("  " + "".join(f"{_fmt(r.get(c,''), 13, 3)}" for c in cols))


def main() -> None:
    logger = RunLogger("runs")

    # -- baseline run, fully logged --------------------------------------------
    cfg = Config()
    print(f"Baseline: N_H={cfg.n_households} N_F={cfg.n_firms} ticks={cfg.n_ticks} seed={cfg.seed}")
    econ = Economy(cfg)
    records = econ.run()
    summary = logger.log(cfg, records, label="baseline", tags=["baseline"],
                         protocol=econ.protocol.name)

    print(f"  conserved={summary['conservation']['ok']} "
          f"max_drift={summary['conservation']['max_drift']:.2e}  "
          f"alive={summary['health']['alive']}  "
          f"depressed_trap={summary['health']['depressed_trap']}")
    print(f"  logged -> {summary['meta']['run_dir']}")

    plot_dashboard(records, path="diagnostic.png", title="Kernel baseline (rho=0.5)", rho=cfg.rho)
    plot_dashboard(records, path=f"{summary['meta']['run_dir']}/dashboard.png",
                   title="Kernel baseline (rho=0.5)", rho=cfg.rho)
    print("  18-panel dashboard -> diagnostic.png (+ run dir)")

    # -- parameter sweep: the dividend-payout leak (rho) -----------------------
    print("\nSweep over rho (dividend payout ratio):")
    run_sweep(cfg, {"rho": [0.3, 0.5, 0.7, 0.9, 1.0]}, logger, tags=["rho-sweep"])

    # -- cross-run readout + comparison figure from the registry ---------------
    print("\nRegistry index (runs/index.jsonl):")
    rows = load_index("runs")
    rho_rows = [r for r in rows if r.get("label", "").startswith("rho=")]
    cols = ["cfg_rho", "m_unemployment_rate", "m_real_output",
            "m_price_index", "m_hh_money_share", "m_hh_wealth_gini", "max_drift"]
    print_index_table(rho_rows, cols)
    plot_cross_run(rho_rows, "cfg_rho",
                   ["m_unemployment_rate", "m_real_output", "m_price_index",
                    "m_hh_money_share", "m_hh_wealth_gini", "m_avg_markup"],
                   path="sweep_rho.png", title="Effect of dividend payout rho")
    print("  cross-run sweep figure -> sweep_rho.png")

    # -- seed-invariance (M3(a)) -----------------------------------------------
    print("\nSeed-invariance (seeds 0,1,2; larger N):")
    inv = seed_invariance(cfg, seeds=[0, 1, 2])
    for k, s in inv["summary"].items():
        flag = "OK" if s["cv"] < 0.15 else "CHECK"
        print(f"  {k:22s} mean={s['mean']:.4f}  cv={s['cv']:.3f}  [{flag}]")


if __name__ == "__main__":
    main()
