# C++ Engine M4 Acceptance (V33)

Status: accepted locally
Branch: `refactor/cpp-m4-v33`
Base: `02a708cdf4077449ae37f221adf6ec6f33e0c353`
Date: 2026-07-24

## 1. Product target

M4 is the first native vertical slice of the latest complete playable engine.
It is not a migration of an old configuration factory.

The executable target contract is generated from:

- `PLAYABLE_MODEL_ID == "current_playable_v1"`;
- all current `PLAYABLE_FEATURE_OVERRIDES`;
- `NewGameSpec.configs()` and the current world builder;
- the current Policy, Shock, Controller, observation, release, desktop, and RL
  sources;
- the complete current configuration and module inventories.

`schemas/m4/current_engine_target.json` records 370 root configuration fields,
61 currently enabled playable overrides, 165 current product source files, and
a unique native owner milestone for every override. Generation fails if the
production builder changes without updating ownership.

M4 does not claim that the complete engine is native. The remaining current
domains are mandatory work:

| Milestone | Required native domains |
|---|---|
| M5 | fiscal, credit, banks, central bank, reserves, RTGS, interbank |
| M6 | bonds, equity, valuation, firm dynamics, bank resolution |
| M7 | persons, families, estates, ownership, persistent labor |
| M8 | energy, housing |
| M9 | trade, FX, international capital, migration, peg, sanctions, shocks |
| M10 | metrics, releases, Controller, Gym/RL, diagnostics adapters |
| M11 | native policy inference, desktop worker, packaging, production cutover |

Production cutover remains forbidden until M11 has accepted the entire current
target.

## 2. Accepted M4 surface

M4 adds a state-owning daily native tick with two closed-economy verticals:

- V0: basic households and firms, spot labor, production, the consumption
  market, cash settlement, firm distributions, metrics, and lag commit.
- V1: V0 plus physical capital, capital firms, accelerator investment, the
  capital-goods market, basic taxation, government demand, Treasury settlement,
  and minimal firm income statements.

The tick runs wholly inside C++. It does not call Python, serialize a
checkpoint, compute a state digest, or copy the full state on its hot path.
Unsupported current capabilities are rejected before genesis instead of being
silently ignored.

The public boundary now includes:

- `EngineSession::advance_tick()` and `advance_ticks()`;
- append-only C ABI capability and M4 simulation functions;
- Python specifications, stepping, snapshots, checkpoints, and phase traces;
- deterministic M4 checkpoint save/restore and state digest;
- independent Python differential and stochastic-panel oracles.

## 3. Correctness and recovery

Accepted properties:

- deterministic fixed-seed execution and exact chunked stepping;
- exact continuation after checkpoint restoration in a fresh process;
- strong tick atomicity across every injected phase fault;
- restoration of balances, components, lags, metrics, RNG counters, and tick;
- money and stock invariants at the commit boundary;
- semantic checkpoint validation and corruption rejection;
- direct M2 accounting mutation rejected after an M4 simulation starts;
- consumption price index excludes capital-goods prices;
- persistent scratch capacity remains stable after warm-up.

## 4. Local validation evidence

The final local validation set includes:

- M4 debug build: 17 of 17 CTest cases passed;
- M4 release build: 17 of 17 CTest cases passed;
- M4 AddressSanitizer build: 12 of 12 CTest cases passed;
- native Python binding regression: 28 of 28 tests passed;
- independent V0/V1 one-tick differential oracle passed;
- 32-seed stochastic panel and exact replay passed;
- fresh-process checkpoint continuation passed;
- isolated wheel smoke passed;
- source-distribution offline-input smoke passed;
- installed C-only consumer smoke passed;
- full repository Python regression passed.

The M4 test matrix also keeps all M0-M3 native, ABI, checkpoint, transaction,
equation, and market tests active.

## 5. Performance evidence

Release P0 workload:

- 5,000 households;
- 525 consumption firms;
- 225 capital firms;
- five warm-up days and 365 measured days;
- fixed seed 206.

Latest local gate result:

- native median tick: 323,875 ns;
- native p95 tick: 367,417 ns;
- native-to-frozen matched-Python median ratio: 0.00025425;
- 2x entity scaling ratio: 2.02369;
- maximum steady-state allocations per day: 0;
- scratch-capacity signature unchanged.

All values pass the frozen M4 budget. This comparison measures the same M4 V1
vertical on both runtimes. It is evidence for the native slice, not a speed
claim for the complete latest engine before M5-M11 are migrated.

## 6. Acceptance decision

M4 is accepted as the first performant, recoverable, packageable native tick
for the latest complete engine migration. It is ready to fast-forward into the
V33 integration branch.

M4 is not a production cutover and does not remove the Python implementation.
Python remains the behavioral oracle and the runtime owner for current modules
scheduled for M5-M11.
