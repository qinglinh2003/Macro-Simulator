"""Entrypoint for v2 -- the two-sector investment + capital economy (DESIGNDOC §10).

Runs the v2 economy, logs it to the registry, writes the v2 dashboard, sweeps the
two new free dials (v, lambda_I), and prints the drain-mitigation readout that is
v2's headline acceptance (§10.8 / PLAN_v2 §1.4): does B_K recirculation lift
household money relative to the v1 depression? No CLI; edit constants below.
"""

from __future__ import annotations

import statistics

from config import Config
from diagnostics import plot_cross_run, plot_dashboard_v2, seed_invariance
from economy import Economy
from run import print_index_table
from runlog import RunLogger, load_index, run_sweep


def _tail(recs, key, frac=0.75):
    tail = recs[int(len(recs) * frac):]
    return statistics.fmean(r[key] for r in tail)


def main() -> None:
    logger = RunLogger("runs")

    # -- v1 reference (for the drain comparison) -------------------------------
    v1 = Economy(Config(n_ticks=600, seed=0)).run()
    v1_share = _tail(v1, "hh_money_share")

    # -- v2 baseline, logged ---------------------------------------------------
    cfg = Config.v2(n_ticks=600, seed=0)
    print(f"v2 baseline: N_H={cfg.n_households} N_C={cfg.n_firms_c} N_K={cfg.n_firms_k} "
          f"ticks={cfg.n_ticks} | v={cfg.v} lambda_I={cfg.lambda_I} delta_K={cfg.delta_K} alpha={cfg.alpha}")
    econ = Economy(cfg)
    records = econ.run()
    summary = logger.log(cfg, records, label="v2-baseline", tags=["v2", "baseline"],
                         protocol=econ.protocol.name)

    print(f"  conserved={summary['conservation']['ok']} max_drift={summary['conservation']['max_drift']:.2e}")
    print(f"  logged -> {summary['meta']['run_dir']}")

    # -- drain-mitigation readout (the §10.8 headline) -------------------------
    v2_share = _tail(records, "hh_money_share")
    print("\nDrain mitigation (last-quarter tail):")
    print(f"  household money share:   v1={v1_share:.4f}   v2={v2_share:.4f}   "
          f"({v2_share / v1_share:.1f}x more retained)")
    print(f"  cure channel B_K wages:  {_tail(records, 'wages_K'):.3f}")
    print(f"  investment spending R_K: {_tail(records, 'investment_spending'):.3f}")
    print(f"  retained (1-rho)Pi:      {_tail(records, 'retained_intended_total'):.3f}")
    net = _tail(records, "net_drain")
    print(f"  net drain (>0 drains):   {net:.3f}   -> "
          f"{'REVERSED' if net < 0 else 'mitigated but not reversed (calibration)'}")
    print(f"  aggregate capital SigmaK: {_tail(records, 'aggregate_capital'):.2f}")
    print(f"  dividend cash-capped:    {_tail(records, 'dividend_cash_capped'):.2f} firms/tick "
          f"(shortfall {_tail(records, 'dividend_shortfall'):.3f})")

    plot_dashboard_v2(records, path="diagnostic_v2.png", title=f"v2 baseline (v={cfg.v}, lambda_I={cfg.lambda_I})")
    plot_dashboard_v2(records, path=f"{summary['meta']['run_dir']}/dashboard_v2.png")
    print("\n  v2 dashboard -> diagnostic_v2.png (+ run dir)")

    # -- sweep the two new free dials (v, lambda_I) ----------------------------
    print("\nSweep over accelerator dials (v, lambda_I):")
    run_sweep(cfg, {"v": [1.5, 2.5, 3.5], "lambda_I": [0.15, 0.35]}, logger, tags=["v2", "accel-sweep"])
    rows = [r for r in load_index("runs") if "v=" in (r.get("label") or "") and "lambda_I=" in (r.get("label") or "")]
    cols = ["cfg_v", "cfg_lambda_I", "m_unemployment_rate", "m_real_output",
            "m_hh_money_share", "m_net_drain", "m_aggregate_capital"]
    print_index_table(rows, cols)
    plot_cross_run(rows, "cfg_v",
                   ["m_hh_money_share", "m_net_drain", "m_real_output",
                    "m_aggregate_capital", "m_unemployment_rate", "m_investment_spending"],
                   path="sweep_v2.png", title="Effect of accelerator ratio v (all lambda_I)")
    print("  cross-run sweep figure -> sweep_v2.png")

    # -- seed-invariance (large N; M3(a)) --------------------------------------
    print("\nSeed-invariance (seeds 0,1,2; larger N):")
    inv = seed_invariance(cfg, seeds=[0, 1, 2],
                          keys=["price_index", "real_output", "unemployment_rate", "hh_money_share"])
    for k, s in inv["summary"].items():
        print(f"  {k:22s} mean={s['mean']:.4f}  cv={s['cv']:.3f}  [{'OK' if s['cv'] < 0.15 else 'CHECK'}]")


if __name__ == "__main__":
    main()
