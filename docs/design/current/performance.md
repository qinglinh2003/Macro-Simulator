# Performance: the per-tick hot paths (2026-07, branch `perf/tick-hotpaths`)

Measured before/after on identical 200-tick windows, same machine, quiet load
(`before` = dev @ 8345d9a in a worktree):

| scenario | before | after | speedup |
|---|---|---|---|
| v13-light — 1000-person demographics, lifecycle consumption, 4 banks | 1537 ms/tick | **64 ms/tick** | **24×** |
| v12.4 full — 5000 households, 8 banks, all-alive regime | 380 ms/tick | **253 ms/tick** | **1.5×** |

Projected full runs: v13 365t ≈ 0.4 min (was ~9); v12.4 5000t ≈ 21 min early-regime-rate
(actual will be lower since late ticks are cheaper).

## Where the time actually went (cProfile, before)

v13 (demographics): **~85% was accidental quadratics in the bridge layer**, not the kernel.

1. `DemographicEconomicBridge._people_by_household` — a full `state.people` scan per query,
   28k queries/tick (one per flow posting): 2.47B `getattr` calls per 40 ticks. **57%.**
2. `build_household_economic_profiles` — planning called it once per household, and each call
   rebuilt profiles for ALL households from a full population scan. **28%.**
3. `PersonClaimLedger.members_of_household` — `sorted(all sheets)` per call, called from every
   posting/allocation/assert path.
4. The per-tick claim-identity assertion — per household: a linear scan of `econ.households`
   plus a full scan of every bond lot: O(N_hh² + N_hh·N_lots).
5. `expected_remaining_life_years` — rebuilt the whole Gompertz survival curve per household
   member per tick (101k mortality integrals/tick at 1000 people).

v12.x (no demographics): **constant-factor bloat on ~180k `ledger.transfer`s/tick**.

6. Every transfer resolved BOTH accounts through `lambda → settlement_node → bank_for`
   (~40% of the tick).
7. `cfg.banking` / `cfg.securities` etc. are *properties that construct a frozen dataclass on
   every access*; `bank_equity_value` built one per call → 21k builds/tick (~10%).
8. metrics — three duplicate per-household bank-equity arrays + a per-household full scan of
   all bond lots.

## What changed (all value-preserving)

| commit | change |
|---|---|
| f204d2a | `PersonClaimLedger`: maintained household→member-id index (insort; query order unchanged) |
| 78e092b | bridge: per-tick person indexes + profile cache + one-pass bond-face grouping + agent memo. Contract: the kernel owns person mutations → economy invalidates before the kernel window, refreshes once after; inside the window every lookup falls back to the live scan. |
| 2bb223c | memoized RTGS settlement-node resolver; every `_bank_of` write site drops its key |
| 07593aa (partial) | `bank_equity_value` flat read; metrics: shared bank-equity array, one-pass lot grouping |
| de3b532 | kernel: reuse `people_by_id`, drop redundant age recompute, precompute interp grid |
| 427c284 | `Config` grouped views cached on first access (trap tests still hold: views stay the only read surface); `expected_remaining_life_years` lru-cached (pure in (age, frozen rates)) |

## Verification protocol (how "no behavior change" was proven)

- **Full-records fingerprints**: 120-tick runs of v13-light / v123-5000 / v124-5000, pickled
  records + sha256 over `repr(records)`, compared after every patch. Two intentional behavior
  changes landed mid-stream (deceased-debt repayment cap; post-genesis dividend registration),
  each re-baselined explicitly.
- Full suite (327 tests) + golden signatures + config-view trap tests.

### The Python ≥3.12 `sum()` trap

Builtin `sum()` over floats is **Neumaier-compensated** since 3.12. Replacing
`sum(x for x in lots if holder==h)` with a running-scalar group-by accumulation changes the
last bit. Any "same order ⇒ same float" refactor must keep the same *reduction operator*:
group VALUES per key, then `sum()` per key. This was caught by the fingerprints (1-ULP diff
in `bond_wealth_share`), invisible to every tolerance-based test.

## Known remaining costs (accepted for now)

- v12.x is now dominated by honest work: per-firm equity market (33% of the profiled tick),
  transfer+reserve settlement (23%), bank stock market (17%), metrics (13%). Next tier would
  be numpy vectorization of the two market loops — doable but float-reduction order must be
  preserved per household, so it is NOT a mechanical change.
- `household_bond_value` still scans all lots per household (planning's bond-wealth term).
  A per-tick group-by needs an invalidation hook on every lot mutation (issue/mature/redeem
  mutate `_bonds` mid-tick), so it was left alone.
- `state.people` never compacts the dead; every kernel pass is O(all people ever). Fine at
  10k, revisit at 100k+.

## If more speed is needed later (in order of leverage)

1. **Scale first**: the v13 target config (10k people) now costs ~0.6-0.9 s/tick by
   extrapolation; profile THAT before optimizing further — the bridge indexes changed the
   scaling class, not just the constant.
2. numpy SoA for the demographic kernel (ages/alive/household as arrays; survival draws
   vectorized per day). Breaks per-person RNG stream compatibility → a declared new baseline.
3. Vectorized equity/bank market loops (v12.x's remaining 50%).
4. numba/Rust only after 1–3 are exhausted; the ledger's dict-of-accounts and the A5 gates
   port cleanly, but the RNG-stream and float-order guarantees make "bit-identical rewrite"
   a contradiction — a rewrite means new baselines by definition.
