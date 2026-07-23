# macro-simulator

Agent-based macroeconomic simulation. The project has grown from the original
closed monetary kernel into a multi-country economic game engine with firms,
households, population dynamics, labor, housing, energy, banks, securities,
fiscal and monetary institutions, external trade/capital/migration, exogenous
shocks, human/heuristic/RL controllers, checkpoints, and a Godot desktop client.
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
| `macro_sim/world/` | Multi-economy BSP coordination, FX, trade, capital, migration, sanctions, and peg regimes. |
| `macro_sim/config/` | Canonical `Config` model, YAML profile loader, typed grouped config views, and validation. |
| `macro_sim/core/` | Accounting and run-state kernel: ledger, policy levers, and `SimulationState`. |
| `macro_sim/domain/` | Agent state: households, firms, banks, and equity-market state. Money balances remain in the ledger. |
| `macro_sim/behavior/` | Pure planning and decision equations: consumption, expectations, pricing, wages, investment, credit demand, portfolio demand. |
| `macro_sim/markets/` | Market matching protocols and trade execution primitives. |
| `macro_sim/systems/` | Phase-level economic mechanisms: planning, credit, labor, goods, settlement, firm demographics, equity, banking, securities, and central bank. |
| `macro_sim/reporting/` | Metrics, diagnostics, and metric collector boundaries. Observation only. |
| `macro_sim/experiments/` | Experiment registry, run logging, and sweep helpers. |
| `macro_sim/controllers/` | Institutional decision contexts, schedules, policy coordination, human/heuristic/RL occupants, and the semi-Markov Gym adapter. |
| `macro_sim/rl/` | Optional SMDP PPO training, paired baseline evaluation, safe portable artifacts, and NumPy deployment. |
| `macro_sim/shocks/` | Immutable exogenous shock tapes, semantic realization engine, stochastic materialization, and historical crisis templates. |
| `macro_sim/demographics/`, `macro_sim/labor/`, `macro_sim/housing/` | Population, relationships, household formation, labor state, and housing institutions. |
| `macro_sim/desktop/`, `desktop/godot/` | Single-writer desktop protocol worker and native Godot client. |
| `schemas/m0/`, `scripts/cpp_migration/` | v33 Python-oracle contracts, traces, fixtures, benchmarks, and migration gates. |
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

Controller RL training is optional and does not add PyTorch to the normal engine:

```bash
uv sync --extra train
uv run --extra train macro-rl train --updates 50 --num-envs 8 --device cpu \
  --output-dir runs/rl-fiscal-v1
uv run --extra train macro-rl evaluate runs/rl-fiscal-v1/policy.msrl --seeds 20 \
  --evaluation-seed-start 1000000 --output runs/rl-fiscal-v1/evaluation.json
```

See [`docs/rl_training_v26.md`](docs/rl_training_v26.md) for the task contract,
checkpoint rules, Apple Silicon guidance, and the held-out superiority gate.

See [`docs/shocks_v27.md`](docs/shocks_v27.md) for the exogenous shock contract,
Controller visibility rules, historical templates, and checkpoint/replay gates.

The old plotting, validation, sweep, and scratch scripts are archived under
[`archive/scripts/`](archive/scripts/README.md). Current diagnostics, RL, and
desktop protocol surfaces live under `macro_sim/` and are covered by M0
migration contracts.

The C++ migration begins with a behavior-preserving Python-oracle freeze:

```bash
uv run python scripts/cpp_migration/generate_inventory.py --check
uv run python scripts/cpp_migration/run_m0_gate.py --class pr
```

## Design Notes

The detailed design history, including the original v1 kernel decisions and
later reversals, lives under [`docs/design/history/`](docs/design/history/README.md).
The durable rules live under [`docs/design/core/`](docs/design/core/README.md).
