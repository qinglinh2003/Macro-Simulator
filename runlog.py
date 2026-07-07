"""Systematic experiment registry: log every config and its outcome.

Each run is persisted so that "parameter set -> economy behavior" is fully
recoverable and cross-run comparable:

  runs/
    index.jsonl                 <- ONE flat row per run (all params + summary
                                   scalars); load into pandas to compare configs
    <run_id>/
      config.json               <- the exact Config used (every field)
      series.csv                <- the full per-tick metrics time series
      summary.json              <- config + tail statistics + health flags + meta

run_id = "<timestamp>_<config-hash>[_<label>]", so identical configs are
distinguishable by time yet the config hash makes accidental duplicates obvious.

Nothing here changes the model; it only observes and records (§8.2 discipline).
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

import metrics
from config import Config
from economy import Economy

# Series summarized in summary.json and surfaced (as m_<key>) in the flat index.
SUMMARY_KEYS: Sequence[str] = (
    "price_index", "inflation", "real_output", "real_consumption",
    "unemployment_rate", "employment", "labor_fill_rate",
    "avg_markup", "avg_wage", "price_cv",
    "inventory", "inventory_investment", "unsatisfied_demand_ratio",
    "consumption_spending", "wages_paid", "dividends_paid",
    "profit_total", "retained_total", "hh_saving",
    "hh_money_share", "hh_wealth_gini", "hh_wealth_top10_share",
    "firm_size_gini_output", "firm_deposits_gini",
    # v2 (present only when capital is enabled; summarize() skips absent keys)
    "c_firm_money", "k_firm_money", "wages_K", "dividends_K",
    "investment_spending", "investment_units", "aggregate_capital", "capital_output",
    "net_drain", "retained_intended_total", "dividend_shortfall", "dividend_cash_capped",
    # v3 (present only when a bank exists)
    "broad_money", "total_credit", "net_worth", "bank_money", "aggregate_leverage",
    "n_firms_borrowing", "new_loans", "credit_wage", "credit_investment", "interest_paid",
)


def _slug(text: str, n: int = 40) -> str:
    keep = "".join(c if (c.isalnum() or c in "-._=") else "-" for c in text)
    return keep[:n].strip("-")


def _config_hash(cfg: Config) -> str:
    payload = json.dumps(dataclasses.asdict(cfg), sort_keys=True).encode()
    return hashlib.sha1(payload).hexdigest()[:8]


def summarize(cfg: Config, records: List[dict], *, burn_in_frac: float = 0.5,
              label: Optional[str] = None, tags: Optional[List[str]] = None,
              notes: str = "", protocol: str = "random") -> Dict:
    """Compute a full summary of a run: config + tail statistics + health flags."""
    n = len(records)
    burn = int(n * burn_in_frac)
    tail = records[burn:] or records

    stats: Dict[str, Dict[str, float]] = {}
    for k in SUMMARY_KEYS:
        col = [r[k] for r in records if k in r]
        tcol = [r[k] for r in tail if k in r]
        if not col:
            continue
        stats[k] = {
            "mean": float(np.mean(tcol)),
            "std": float(np.std(tcol)),
            "min": float(np.min(tcol)),
            "max": float(np.max(tcol)),
            "last": float(col[-1]),
            "class": metrics.classify_series(col),
        }

    max_drift = float(max(r.get("conservation_drift", 0.0) for r in records))
    conserved = max_drift < 1e-6 * max(1.0, records[0]["total_money"])

    # A rough "healthy vs depressed" read (NOT a §4 target -- just triage help).
    u_mean = stats.get("unemployment_rate", {}).get("mean", 1.0)
    out_class = stats.get("real_output", {}).get("class", "frozen")
    price_class = stats.get("price_index", {}).get("class", "frozen")
    health = {
        "conserved": conserved,
        "alive": out_class == "alive" and price_class == "alive",
        "output_class": out_class,
        "price_class": price_class,
        "depressed_trap": u_mean > 0.5,      # heuristic flag, not a verdict
    }

    return {
        "meta": {
            "label": label,
            "tags": tags or [],
            "notes": notes,
            "protocol": protocol,
            "n_ticks": n,
            "burn_in_frac": burn_in_frac,
            "created": datetime.now().isoformat(timespec="seconds"),
            "config_hash": _config_hash(cfg),
        },
        "config": dataclasses.asdict(cfg),
        "conservation": {"max_drift": max_drift, "ok": conserved},
        "health": health,
        "stats": stats,
    }


class RunLogger:
    def __init__(self, root: str = "runs"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.jsonl"

    def log(self, cfg: Config, records: List[dict], *, label: Optional[str] = None,
            tags: Optional[List[str]] = None, notes: str = "",
            protocol: str = "random") -> Dict:
        summary = summarize(cfg, records, label=label, tags=tags, notes=notes, protocol=protocol)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_id = f"{stamp}_{summary['meta']['config_hash']}"
        if label:
            run_id += f"_{_slug(label)}"
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        (run_dir / "config.json").write_text(json.dumps(summary["config"], indent=2, sort_keys=True))
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
        self._write_series_csv(records, run_dir / "series.csv")
        self._append_index(run_id, summary)

        summary["meta"]["run_id"] = run_id
        summary["meta"]["run_dir"] = str(run_dir)
        return summary

    @staticmethod
    def _write_series_csv(records: List[dict], path: Path) -> None:
        cols = metrics.field_order(records)
        with path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in records:
                w.writerow(r)

    def _append_index(self, run_id: str, summary: Dict) -> None:
        """One flat, pandas-friendly row per run: params (cfg_*) + summary (m_*)."""
        row: Dict[str, object] = {
            "run_id": run_id,
            "label": summary["meta"]["label"],
            "created": summary["meta"]["created"],
            "protocol": summary["meta"]["protocol"],
            "n_ticks": summary["meta"]["n_ticks"],
            "conserved": summary["conservation"]["ok"],
            "max_drift": summary["conservation"]["max_drift"],
            "alive": summary["health"]["alive"],
            "depressed_trap": summary["health"]["depressed_trap"],
        }
        for k, v in summary["config"].items():
            row[f"cfg_{k}"] = v
        for k, s in summary["stats"].items():
            row[f"m_{k}"] = s["mean"]        # tail mean is the headline per metric
        with self.index_path.open("a") as fh:
            fh.write(json.dumps(row) + "\n")


def load_index(root: str = "runs") -> List[Dict]:
    path = Path(root) / "index.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Convenience: run + log a single config, or a whole parameter grid
# ---------------------------------------------------------------------------
def run_and_log(cfg: Config, logger: RunLogger, *, label: Optional[str] = None,
                tags: Optional[List[str]] = None, notes: str = "") -> Dict:
    econ = Economy(cfg)
    records = econ.run()
    return logger.log(cfg, records, label=label, tags=tags, notes=notes,
                      protocol=econ.protocol.name)


def run_sweep(base_cfg: Config, grid: Dict[str, Sequence], logger: RunLogger,
              *, tags: Optional[List[str]] = None) -> List[Dict]:
    """Run the Cartesian product of ``grid`` overrides on ``base_cfg``, logging each.

    Example: run_sweep(Config(), {"rho": [0.3,0.5,0.7,1.0], "alpha1": [0.6,0.8]}, logger)
    -> 8 runs, each fully persisted and appended to runs/index.jsonl.
    """
    keys = list(grid)
    summaries: List[Dict] = []
    for combo in product(*[list(grid[k]) for k in keys]):
        overrides = dict(zip(keys, combo))
        cfg = dataclasses.replace(base_cfg, **overrides)
        label = ",".join(f"{k}={v}" for k, v in overrides.items())
        summaries.append(run_and_log(cfg, logger, label=label,
                                     tags=(tags or []) + ["sweep"]))
    return summaries
