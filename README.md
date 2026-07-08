# macro-simulator

Agent-based macroeconomic simulation. The project has grown from the original
closed monetary kernel into a layered closed-economy simulator with firms,
households, banks, fiscal policy, monetary policy, reserves, and securities.
Start with the [current developer brief](docs/design/current/developer-brief.md)
for the active frontier and the [design map](docs/design/README.md) for the full
documentation structure.

The design philosophy (see §0 of the design doc): macro regularities should
**emerge** from a minimal set of micro axioms, never be hard-coded. Accounting
identities are hard invariants; behavioral rules are deliberately simple.

## Start Here

For development work, read in this order:

1. [`docs/design/current/developer-brief.md`](docs/design/current/developer-brief.md) — current frontier and active gaps.
2. [`docs/design/current/development-rules.md`](docs/design/current/development-rules.md) — accounting, modeling, and documentation rules.
3. [`docs/design/README.md`](docs/design/README.md) — map to durable core docs and historical arcs.

## Layout

| Path | Role |
|---|---|
| `macro_sim/economy.py` | Main `Economy` facade and tick scheduler. It wires systems together but delegates phase work to `macro_sim/systems/`. |
| `macro_sim/config/` | Canonical `Config` model, YAML profile loader, typed grouped config views, and validation. |
| `macro_sim/core/` | Accounting and run-state kernel: ledger, policy levers, and `SimulationState`. |
| `macro_sim/domain/` | Agent state: households, firms, banks, and equity-market state. Money balances remain in the ledger. |
| `macro_sim/behavior/` | Pure planning and decision equations: consumption, expectations, pricing, wages, investment, credit demand, portfolio demand. |
| `macro_sim/markets/` | Market matching protocols and trade execution primitives. |
| `macro_sim/systems/` | Phase-level economic mechanisms: planning, credit, labor, goods, settlement, firm demographics, equity, banking, securities, and central bank. |
| `macro_sim/reporting/` | Metrics, diagnostics, and metric collector boundaries. Observation only. |
| `macro_sim/experiments/` | Experiment registry, run logging, and sweep helpers. |
| `docs/design/` | Development-first design docs: current brief, durable core rules, and archived research history. |
| `docs/plans/` | Version-specific implementation plans (`PLAN_v*.md`). |
| `archive/scripts/` | Archived pre-refactor scripts. Preserved for reference; not an active command surface. |
| `artifacts/` | Generated/reference images and small experiment data files. |
| `runs/` | Structured experiment registry with config, full series, and summaries. |
| `run.py` | Thin package-path entrypoint. Configure via constants; no CLI. |

## Experiment registry (`runs/`)

Every run is logged so `config -> outcome` is recoverable and comparable:

```
runs/
  index.jsonl            # one flat row per run: all params (cfg_*) + summary means (m_*)
  <timestamp>_<hash>_<label>/
    config.json          # the exact Config
    series.csv           # full per-tick metrics (~46 columns)
    summary.json         # config + tail stats + health flags + metadata
```

Load `index.jsonl` into pandas to compare configs across experiments:

```python
import pandas as pd
df = pd.read_json("runs/index.jsonl", lines=True)
df[["cfg_rho", "m_unemployment_rate", "m_real_output", "m_hh_wealth_gini"]]
```

Sweeps are one call — `run_sweep(Config(), {"rho": [0.3, 0.5, 0.7, 1.0]}, logger)` runs
the grid and logs each. Recording §4 test-set statistics (Gini, firm-size dispersion) is
pure **observation**, not encoding, so it does not violate §0-ii / §8.2.

## Run

```bash
uv run python run.py                     # run kernel, write diagnostic.png, seed check
uv run python tests/test_conservation.py # ledger foundation tests (zero-dependency)
uv run pytest -n auto -q                 # full parallel regression suite
```

The old plotting, validation, sweep, and scratch scripts are archived under
[`archive/scripts/`](archive/scripts/README.md). Their protocol layer will be
rebuilt during the code refactor.

## Design Notes

The detailed design history, including the original v1 kernel decisions and
later reversals, lives under [`docs/design/history/`](docs/design/history/README.md).
The durable rules live under [`docs/design/core/`](docs/design/core/README.md).
