# macro-simulator

Agent-based macroeconomic simulation. This repo implements **roadmap step 1** of
[`DESIGNDOC.md`](DESIGNDOC.md): the *closed monetary kernel* — households + firms,
one good, money (deposits) as the only financial instrument, no banks, no
government, no external sector.

The design philosophy (see §0 of the design doc): macro regularities should
**emerge** from a minimal set of micro axioms, never be hard-coded. Accounting
identities are hard invariants; behavioral rules are deliberately simple.

## v1 goal — "alive and conserving", not interesting economics

The v1 bar (design doc §7.5) is intentionally low:

> Run the kernel with the money-conservation assertion **never tripping**, and
> price/output series that are *neither frozen nor exploding*.

Reproducing §4 laws (Phillips curve, Okun's law, …) is **not** a v1 goal — those
are the held-out test set and must not be engineered in.

## Layout

| File | Role |
|---|---|
| `ledger.py` | `transfer(from, to, amount)` — the **only** money mutator; agents have no write access to balances, so conservation (A1/M0) holds by construction. Conservation is a redundant per-tick gate. |
| `config.py` | The full §7.4 parameter budget, each row tagged forced / anchored / scale / transient / FREE. Only five dials are genuinely free: `phi, eta, mu_min, mu_max, omega`. |
| `agents.py` | `Household` / `Firm` state (money lives in the ledger, not here); per-agent parameter fields; cross-tick derived state persisted per §8.1. |
| `interfaces.py` | The two swappable interfaces: `MatchingProtocol` (default `RandomMatch`) and `Goods` (default single good). |
| `behavior.py` | The §7.2 closed-form behavioral equations (B1–B4, B2 expectations) as pure planning functions. |
| `economy.py` | The six-phase tick loop (§6.3): synchronous planning → sequential labor market → sequential goods market → settlement/dividends → accounting gate. |
| `metrics.py` | Rich per-tick metrics (~46 series): flows, distributions (Gini/top-share), price dispersion, inflation, labor gaps. Pure observation. |
| `diagnostics.py` | Diagnostic plot + seed-invariance check (M3(a)). |
| `runlog.py` | Experiment registry: persists every run's config + full series + summary, and a flat cross-run `index.jsonl`. Parameter sweeps. |
| `run.py` | Entrypoint. Configure via constants; no CLI. |

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
```

## Notes on the first run

The kernel is **alive and conserving**: total money is flat (drift ~1e-9), all
series are bounded and moving, and results are seed-robust. The default
parameters produce a boom → depressed-trap transient (employment collapses into a
low-activity attractor). Per design-doc §7.5 that is a **calibration** question
(tuning the five free dials), not a plumbing bug — the conservation gate never
trips, which is the signal that the accounting is sound.

## Design decisions made during implementation

Flagged explicitly rather than silently (per §8.1):

- **Phase-1 order is wage → price** (design doc §6.3/§7.2 corrected in v0.7): cost-plus
  reads the current-tick wage.
- **Continuous labor** (not integer): `floor(D/w)` in §7.2 is treated as a cash cap, not
  a mandate to discretize employment (§8.1).
- **Labor market is not routed through `MatchingProtocol`**: the kernel has no wage to
  shop (inelastic supply, short-side rationing), so price-comparison is meaningless there;
  it uses a dedicated random-order routine on the same seeded RNG. `MatchingProtocol`
  governs the goods market, where price-comparison is the real deferred fork (§5, §7.3).
- **tick-0 cold start** is centralized (`Firm.create`, `Household.create`): no first-tick
  wage raise, neutral first B2 update, `Y^e(0)=0`.
