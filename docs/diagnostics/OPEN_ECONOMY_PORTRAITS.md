# Open-Economy Diagnostic Portraits — Plan & Findings Log

> **STATUS: PLAN (2026-07-15).** Branch `diag/open-economy-portraits`, worktree
> `macro-simulator-openecon`, forked from `dev@0b65f1d` (the v23 merge: the fixed capital
> clock + labour margin + safety net, and the codex diagnostic/accounting framework).
> This document is the running log — the design up front, findings appended as they land.

## Why now

The open-economy layer (v20 money/FX/trade, v21 international capital, v22
migration/remittances) was built on the BROKEN capital clock: capital was economically
absent (K / annual GDP ≈ 0.004), so every cross-border capital, trade-balance and
trilemma result sits on a foundation where the central price of the model did not bind.
With v23 merged, capital is real. The open-economy stylized facts must be re-derived on
the fixed foundation — that is the whole point of these portraits.

## Scientific questions

1. **Do the international identities hold at scale and over long horizons?** BOP, NFA =
   −Σ current account, FX conservation, bilateral trade symmetry — the `diagnose_world`
   identity gates must stay green for a portrait to be valid.
2. **What do the cross-border channels look like now that capital is REAL?** Trade
   balances, capital flows, the trilemma, currency crises — all inherited from a
   zero-capital economy and now expected to differ.
3. **Cross-country shock propagation.** An energy / rate / productivity shock in ONE
   economy → transmission via trade + capital + FX to the others.
4. **Structural-asymmetry stylized facts.** Large vs small, surplus vs deficit, high vs
   low productivity. Does capital flow to the rich or the poor (the allocation puzzle)?
   Do economies converge?

## How the World is driven (verified against dev@0b65f1d)

- `World(configs: List[Config], *, couple, trade, capital, fx_*, capital_mobility, peg,
  migration, remittance_share, tariff, import_quota, export_subsidy, capital_control,
  sanctions, emigration_cap, guest_worker_return, periods_per_year=12.0, ...)`.
- Each economy is a full `Config`, so `Config.v13(**FULL_FRONTIER_FLAGS, ...)` per country
  puts the **v23 fixed foundation** (capital clock, second job, income floor) into every
  economy.
- `World.run(n_ticks) -> List[List[dict]]` (per-economy record streams).
- Identity gates live in `macro_sim/world/world_probes.py::diagnose_world`; the diagnostic
  runner only exercises tiny smoke worlds (n=2, ticks=14, pop=30) — full portraits need a
  dedicated harness.

## Pre-registered risks (the smoke gate must clear these BEFORE any long run)

- **R1 — the World clock.** `periods_per_year` defaults to **12 (monthly)** while the
  underlying economies tick **daily (365/yr)**. Cross-border interest, FX and trade flows
  may be on the wrong calendar — the same class of defect as the v23 capital clock
  (`v` annual × daily flow). **This may itself be a finding.** First smoke screen: are the
  cross-border interest / FX magnitudes sane against the daily domestic flows?
- **R2 — identity conservation under the v23 frontier flags.** v20-v22 were built on the
  old foundation; enabling the full frontier (capital clock, priced balance sheet, realized
  bank P&L, national accounts) may require re-aligning the world identities. Smoke must show
  `diagnose_world` green with the frontier flags on.

## Parallelisation (10 workers)

A coupled World is ONE process (economies are interdependent), so **10 workers = 10
independent World runs**. The design is a causal matrix: a baseline + intervention arms,
each paired with its same-seed baseline for attribution.

**Wave 1 (10 jobs):**

| slot | configuration | tests |
|---|---|---|
| 1-2 | symmetric baseline (N identical economies, full coupling), 2 seeds | steady state + identity baseline |
| 3 | productivity divergence (one economy, higher TFP drift) | allocation puzzle / convergence |
| 4 | energy shock in one economy | trade + FX transmission |
| 5 | rate divergence (one economy hikes) | trilemma: capital inflow + FX appreciation |
| 6 | capital control ON | can it sever slot 5's channel |
| 7 | tariff / import quota | trade-policy cross-border cost |
| 8 | migration OFF vs baseline | labour mobility + remittances |
| 9 | peg vs float | exchange-rate regime |
| 10 | size asymmetry (1 large + small, the v20 vehicle-currency N=3) | centre-periphery |

**Wave 2:** replicate the 2-3 strongest Wave-1 results across ≥3 seeds (the framework's bar
for promoting a single-seed effect to replicated evidence).

## Scale / horizon staging (do not burn hours on a broken config)

| stage | N | pop/economy | horizon | purpose |
|---|---|---|---|---|
| smoke | 2 | 200 | 2 yr | clear R1 (clock) + R2 (identities) + config path |
| audit | 3 | 500 | 10 yr | mechanisms take shape, matrix debugged |
| production | 3 (opt. 5) | 2000 | 30 yr (10950 daily ticks) | let NFA / capital stocks build; trilemma & convergence play out |

Cost anchor: a single-economy full-frontier 2191-tick run ≈ 13 min. A production World
(3 economies × ~4× pop × ~5× ticks) is HOURS per run; 10 run in parallel (1 core each) so
wall-clock ≈ the slowest single run. Hence the staging: minutes → tens of minutes → hours,
gated at each step.

## Harness (to build)

The diagnostic CLI's causal matrix is single-economy; the world path is smoke-only. Full
portraits need a small harness: build N frontier `Config`s → construct `World` with the
coupling/policy knobs → long run → write per-economy `series.csv` + `diagnose_world`
identity report + per-arm attribution. Reuse `world_probes.diagnose_world`; do not rebuild
the identity gates. Every run writes to a NEW artifact directory (evidence discipline).

## Runtime optimisation (a co-goal of this branch)

**World.step() structure (read from `world/world.py`):** every tick is
`_coupling_barrier()` [joint] → `for econ: _run_pre_settlement_phases()` [N independent] →
`_dealer_update()` [joint] → `[econ._run_settlement_and_commit_phases() ...]` [N independent].
The two N-loops are the domestic economy steps (the bulk of the compute), split by the FX
dealer coupling in the MIDDLE of the tick.

**Honest parallelism assessment:** the coupling is EVERY TICK, so intra-run parallelism
across economies is not tractable — a multiprocessing split would have to serialise the full
per-economy state twice per tick, and a single economy tick is milliseconds, so IPC would cost
more than it saves; the GIL blocks pure-Python threads. The real levers are therefore:

1. **Across-run parallelism** — 10 workers = 10 independent Worlds. Already free; the dominant
   lever. Verify it scales cleanly (BLAS pinned to 1 thread/process).
2. **Single-economy step profiling** — cProfile the domestic tick, optimise the pure-Python hot
   spots. This speeds up EVERY economy in EVERY run (closed and open), so it is the highest-value
   tractable win.
3. **Coupling-barrier overhead** — the barrier resets ~15 journal fields per economy per tick and
   does cross-border reductions; check for O(N²) bilateral loops or redundant recomputation.

Do NOT promise an N× intra-run speedup that the per-tick coupling makes impossible.

### Runtime findings (this branch) — status: MEASURED

**Intra-run parallelism is confirmed NOT tractable (read `_dealer_update`).** The coupling phase
does not merely *read* cross-border summaries — `settle_trade`, `capital_interest` and
`run_migration` reach directly into each economy's ledger and demographic bridge every tick
(`econ.ledger.transfer(funder, DEALER_ID, …)`, `_pay_households` posting into household accounts +
`bridge.post_capital_income`). So economies are NOT state-isolated: a process split would need every
cross-border money movement re-expressed as a returnable per-economy delta and replayed in the
worker, a large invasive refactor with high regression risk against the conservation/identity gates.
Plus the GIL blocks pure-Python threads. Not a quick win — deferred, documented, not attempted.

**Across-run parallelism VERIFIED as the lever.** 8 independent full-frontier runs, BLAS pinned to
1 thread/process: sequential 50.7s → parallel(8) **11.5s = 4.4×** on a 10-core box. Sub-linear only
because per-process import (~2s) is a large fraction of these short (~6s) runs; for the hours-long
production arms that fixed cost amortises to near-linear. `openecon_matrix.py` is the parallel driver.

**Single-economy hot-spot wins landed (bit-identical, help every run, closed or open):**
- The 365× capital-clock double-migration fix (FINDING 1) alone gave **2.3×** (8.5 → 20 ticks/s) by
  removing the phantom investment/depreciation flows the runaway ×365 capital generated.
- `economic_bridge`: per-tick claim-posting-id cache — kills ~6.6M redundant owner-list rebuilds
  (matters most at production pop; wash at pop 200).
- `reporting/metrics`: one bond-lot pass for the market-value totals + a shared per-bank delta map
  for the capital snapshots (was ~28M `bond_market_value` calls); ~5% on a bond-heavy run, scales
  with bond-book size over long horizons. Stays pure (does not populate the behavioural bond cache).

## Pre-registered risk R1 — status: LEAD, not yet confirmed

`self.periods_per_year` (default 12) is READ only once, into a domain-validation dict
(`world.py:400`). No interest / FX / carry computation reads it. So either it is vestigial and
cross-border flows correctly use the daily domestic rates, or something that SHOULD convert an
annual rate to per-tick does not — a flow on the wrong clock. Resolve empirically: at smoke,
compare the cross-border interest / carry magnitudes against the daily domestic flows.

## Discipline (inherited)

Freeze source during any diagnostic run (a mid-run edit invalidates it or crashes the
manifest reader). Same-seed twins for attribution; ≥3 seeds before "replicated". Interpret
`measurement_status` literally. Flag-gated fixes default-off bit-identical. Record honest
nulls and refutations, not just confirmations.

---

## FINDINGS LOG

_(appended as they land — newest first)_

### FINDING 5 (open, Tier-1) — the v23 capital-clock fix left an UNDER-DAMPED investment accelerator → long-horizon macro instability

The 10-year audit revealed the economy does NOT settle: over a decade it runs large boom-bust cycles —
CPI level swinging 1.0↔2.3, CB-measured inflation swinging −5% to +16%/yr, and **unemployment spiking to
26% (coupled) / 38% (closed)**. Invisible at the 2-year smoke horizon (the cycle hadn't developed).

**Root-caused by same-seed attribution (closed economy, pop 500, 10 y, bucket=30):**
- **Real-side & closed-economy** — a closed baseline reproduces it (max_u 37.8%), so it is NOT
  open-economy-specific. The CB responds CORRECTLY (rate tracks inflation: ~13%/yr when inflation is
  16%, floored at 0 when inflation is negative) — so it is NOT a monetary-rule bug. The
  factor-income≈0 observation was a red herring (the equilibrium nominal rate genuinely sits near 0).
- **It is the INVESTMENT ACCELERATOR.** Halving `lambda_I` (investment adjustment speed) cuts inflation
  volatility ~55% and price-level CoV ~76% on the cycling seeds without breaking output. Lowering `v`
  (capital-output ratio) instead COLLAPSES the economy (99.9% unemployment) — `v` is structural,
  `lambda_I` is the damping lever. Making `lambda_I` faster (×26) makes it much worse. Classic
  accelerator-multiplier limit cycle.
- **It is a direct consequence of FINDING 1.** Turning the annual clock OFF (capital economically
  absent again, the old broken state) drops peak unemployment 37.8% → 15.6% and halves inflation vol on
  the same seed. The capital-clock fix correctly made capital REAL (`v = 912.5`), which gave the
  accelerator teeth — but the daily `lambda_I = 0.0019` was never re-tuned for now-real capital, leaving
  it under-damped.
- **Seed-dependent** — baseline inflation vol was 8.48 / 4.26 / 4.83 across 3 seeds, and `lambda_I`
  damping helps the worst seeds a lot (s1 −56%, s3 −62%) but slightly worsens an already-calm one (s2).
  So the cure is not simply "halve lambda_I" — it needs a proper multi-seed × multi-horizon calibration.

**Recommended next step (a scoped calibration mini-arc, not a one-line change):** re-tune the investment
damping for the real-capital regime — search `lambda_I` (and possibly the investment rule's structure /
a capital-adjustment cost) for a value that damps the cycle across seeds and horizons WITHOUT collapsing
output. This is the natural sequel to FINDING 1: the clock fix priced capital correctly; the dynamics it
switched on now need damping. 38% unemployment swings are not a realistic business cycle — they are an
over-amplified accelerator.


### The 10-year audit matrix (bucket=30) — DELIVERED, all identities hold; 3 open research threads

With FINDING 4 fixed, the full causal matrix ran at AUDIT scale (n=3, pop 500, **10 years**, all 10
arms) in **~29 min wall** (each arm ~14 min; at bucket=1 a single arm ran >56 min without
finishing). **Every arm passed 24/24 world identities** — the open-economy accounting is sound over a
decade under every intervention (peg, capital control, tariff, energy shock, rate divergence, size
asymmetry). Artifacts: `artifacts/openecon/matrix_audit_b30/`.

The decade dynamics (now visible for the first time) surface three threads for the next phase — these
are ECONOMIC observations to study, NOT identity failures or bugs:

1. **Nominal drift.** CPI drifts UP over the 10 years (baselines ~1.0–2.5; outliers: energy_shock
   econ1 4.5, size_asymmetry large-econ 7.4) despite 2% TFP drift and an active Taylor CB — 2 years
   showed CPI ≈ 1.0. Connects to the existing v19 nominal-anchor arc; worth a dedicated look at whether
   the long-run anchor holds.
2. **Capital shallowing.** K / annual GDP falls from ~2.2 (2 y) to ~1.0–1.4 (10 y) — capital lags
   output growth over the decade. Is investment under-responding to the TFP-driven output path?
3. **Large external positions.** NFA accumulates to the thousands–tens-of-thousands over 10 years;
   extreme under `peg` (pegged econ0 NFA −92k, hemorrhaging under a persistent deficit) and
   `capital_control` (+31k) — the FINDING 3 note that a closed/pegged account lets trade-driven NFA
   grow via slow FX clearing, now visible at decade scale. Whether these stabilise at 20–30 years is
   the production-stage question.


### FINDING 4 (FIXED, commit 311ca09) — long-horizon cost is O(horizon²): the bond lot book grows without bound

> **RESOLVED.** Flag-gated `bond_maturity_bucket` (default 1 = bit-identical). `issued_maturity()`
> snaps a newly issued lot's maturity UP to a grid of that width so a holder's daily buys inside a
> bucket window share a maturity; `consolidate_bonds()` then merges lots sharing `(holder,
> matures_at)` — a par-issued, common-coupon merge that preserves face, cost, holder and maturity, so
> market value, the v12 face identity, per-holder holdings and the master NFA are ALL invariant.
> **Measured (pop 500):** per-tick cost went from 39→233 ms/tick over 1600 ticks at bucket=1 (book
> 4.6k→56k lots) to a **FLAT ~40 ms/tick at bucket=30** (book bounded ~2.4k) — O(horizon²) → O(horizon).
> A 10-year arm drops from ~40-56 min to ~5 min, so multi-decade portraits are now feasible
> (`openecon_matrix --bond-bucket 30`). bucket=1 is bit-identical (digest dcb359c6; 83 tests green).
> The diagnosis that led here is preserved below.



The audit stage (n=3, pop 500, 10 y) was impractically slow — a single arm ran >56 min without
finishing. Root-caused it is NOT the obvious suspects:
- **Per-tick cost is LINEAR in population** (pop 200→500 = 15→37 ms/tick ≈ 2.5×). The per-firm equity
  market's watchlist is capped (`watchlist_size = 15`), so it is O(n_households), not O(pop²).
- **The WorldProbeCollector adds ~0% overhead** (measured 1.00×) — the identity gates are cheap.
- **Nothing else accumulates**: over 1400 ticks, ledger accounts (~385), claims persons (~510),
  loans (~385) and households (~300) are all FLAT.

The sole unbounded accumulator is the **government bond lot book**. Per-tick cost grows 124 → 629
ms/tick over 1400 ticks (5×) with flat population and FEWER firms, tracking `len(econ._bonds)`:

| tick | n_bond_lots | bond_holders | outstanding face |
|---|---|---|---|
| 200 | 4,739 | 49 | ~5,400 |
| 600 | 13,260 | 146 | ~14,300 |
| 1000 | 42,267 | 198 | ~16,200 |
| 1400 | 55,951 | 241 | (stable) |

`run_bill_issuance_phase` appends ONE lot per buying household EVERY tick (daily issuance), each a
1-year bill (`bond_maturity = 365`). Matured lots ARE pruned, but the live book saturates at
~`n_bond_holders × 365` ≈ 100k+ lots at pop 500 — the SAME ~16k of outstanding debt fragmented into
~100k tiny rolling lots (avg face ~0.3). Every tick re-values the whole book (in `_bond_valuations`,
in the metrics totals, and in the per-bank snapshots), so per-tick cost grows linearly with elapsed
ticks → **total simulation cost is O(horizon²)**. This is the blocker for 10–30 year portraits;
per-tick population scaling is fine.

**No bit-identical O() fix exists.** `bond_market_value(lot) = face · unit_price(matures_at − t)` is
linear in face, so aggregate valuations COULD be O(distinct-maturities ≤ 365) instead of O(n_lots) —
but grouping lots by maturity changes the floating-point summation order and breaks the golden
digests. Memoising `unit_price(n)` within the existing per-lot pass IS bit-identical but only saves
the `bond_price` arithmetic (~10-15% of the bond cost), not the O(n_lots) iteration itself.

**Recommended fix (scoped follow-up, not attempted here):** a FLAG-GATED maturity-aggregated bond
valuation — default off ⇒ bit-identical; on ⇒ group faces by maturity bucket and value in O(365),
with the golden digests re-baselined for the flag-on path. This is a careful change to core
securities with strict conservation invariants (the P&L bridge identity, the v12 bond identity, the
master NFA identity), so it wants its own change + test pass rather than a rushed edit mid-session.

**Practical mitigation for portraits now:** the smoke matrix (2 y) is fast and clean (all 10 arms,
24/24 identities). Long-horizon portraits are gated on the bond fix; until then, run at reduced
horizon or with less granular bond issuance.

### FINDING 3 (FIXED, commit a97b902) — `capital_control` was an INCONSISTENT throttle

Surfaced by the smoke causal matrix: the `capital_control` arm produced LARGER external positions
(NFA ≈ 268/572/262) than the open-account `rate_divergence` arm (≈ 80/−32/16) — closing the account
appeared to *inflate* the external sector, backwards from the trilemma.

**Root cause.** `capital_control` throttled the capital FLOW (`capital_financing`) and peg defense by
`(1 − capital_control)`, but `capital_grope_signal` kept groping toward the FULL open-account
`target_positions`. So a fully-closed account (`capital_control = 1.0`) did NOT reduce to zero capital
mobility — the FX rate still chased a capital-sustained position the account was forbidden to finance,
and `capital_control` interpolated inconsistently between its endpoints.

**Fix.** Throttle the grope target by `(1 − capital_control)` too. Verified: `capital_control = 1.0`
is now **byte-identical** to `capital_mobility = 0` (was [104,83,237] vs [161,299,237]);
`capital_control = 0` unchanged (bit-identical, 43 FX/capital/policy/BoP tests pass incl.
`test_capital_controls_save_the_peg`).

**The large closed-account NFA is NOT a bug** (the matrix's first read was wrong). `capital=False`
(no capital layer at all) shows the SAME large NFA [135,267,165]: with capital immobile, trade
imbalances can only clear through slow FX adjustment, so positions build up transiently; it is OPEN
capital (cc=0) that STABILISES the external position to small NFA. Whether the closed-account NFA
stabilises over a 30-year horizon is a portrait question, not a defect.

### FINDING 2 (null, honest) — a −35% energy capacity shock is absorbed by spare capacity

The `energy_shock` arm was byte-identical to baseline. Not a wiring bug: the shock fires
(`sum(energy_shock_active) = 146` ticks, `capacity_kappa` 1.0 → 0.65) but never BINDS —
steady-state energy capacity utilisation is ~49%, so capacity at 65% stays above demand
(`energy_cap_binding = 0`). Spare capacity fully buffers a moderate supply shock — a realistic null.
The matrix arm now uses magnitude 0.6 (capacity → 40%, below the ~49% utilisation) so the constraint
actually bites and the trade/FX transmission channel becomes visible.

### FINDING 1 (RESOLVED, commit 89d6627) — capital explodes 365× via a DOUBLE annual-clock migration in `dataclasses.replace`

**Root cause (the coupling attribution below was WRONG).** `Config._apply_capital_annual_clock`
mutates `v`, `K_firm0`, `A` **in place** inside `__post_init__`. `dataclasses.replace()` copies the
already-migrated field values and **re-runs `__post_init__`**, so the ×365 (`ticks_per_year`)
migration is applied a SECOND time — and it compounds (`replace²` = ×365²). The World applies
`replace(cfg, seed=base_seed + i·stride)` to every economy (`world.py:250`), so every open economy
got genesis firm capital `7300 → 2,664,500` (×365), `aggregate_capital 53.3M`, `CPI 261`,
`K/annual-GDP 652–806`. It is NOT the v21 capital-flow coupling: `capital=False` shows the identical
53.3M, and a standalone `Economy(cfg)` from the SAME cfg object is correct at 146k — the divergence is
purely the World's `replace`. The `.large()/.small()` presets (`model.py:2047-2055`) and experiment
overrides (`runlog.py:216`) were silently double-migrating too.

**Fix.** A `_capital_annual_clock_applied` guard field (default False, `compare=False`). It is a real
dataclass field, so `replace()` copies its `True` value and the second `__post_init__` skips —
migrated exactly once, from any construction path. `capital_annual_clock=False` unchanged.

**Verified.** Smoke n=2/pop200/2y now healthy: `CPI ≈ 1.0` (was 261), `K/annual-GDP ≈ 2.2` (target
~2.5, was 652–806), and **2.3× faster** (8.5 → 20 ticks/s — the runaway ×365 capital was generating
phantom investment + depreciation flows). `replace^k` is now idempotent. 88 capital+world tests green.

**Both pre-registered risks CLEARED on the fixed foundation** (harness now measures them — the earlier
`ext_factor_income` field name and `_world_probe_rows` identity path were both broken; fixed to read
`world.world_records` and to drive `WorldProbeCollector`):
- **R2 (identities):** all **24** `diagnose_world` checks PASS, zero findings. The world identities
  hold with the full v23 frontier flags on.
- **R1 (clock):** cross-border factor income (±1.45e-5, econ0/econ1 mirror to ~zero → passthrough
  conserved) is the **same order** as domestic daily interest (9.5e-5), NOT 365× off. Cross-border
  flows are on the correct daily calendar. NFA small but nonzero (−3.05 / +3.60), current accounts
  mirror (+0.026 / −0.026).

---

### FINDING 1 — ORIGINAL (SUPERSEDED) attribution to capital-flow coupling

Smoke (n=2, pop=200, 2y, FULL_FRONTIER_FLAGS, trade+capital+migration on) is UNHEALTHY:
aggregate_capital ≈ **53.3 MILLION** at the first recorded tick, CPI ≈ 261 (hyperinflation),
K / annual GDP ≈ 652-806 (the fixed single economy is ~1.6).

**53,280,126 / (n_firms_c × K_firm0 = 20 × 7300 = 146,000) = exactly 365.** Capital is 365× too
large — the `ticks_per_year` scale applied an extra time.

Double-migration hypothesis REFUTED: a standalone `Config.v13(**FRONTIER)`, a closed `Economy`,
AND `World[econ].c_firms` genesis capital are ALL 146,000 (correct, single migration). The
construction path is fine. The 365× appears only once the smoke world RUNS with `capital=True`
(capital mobility on) — the explosion is injected by the **cross-border CAPITAL-FLOW coupling
(v21)**, built on the OLD clock and not reconciled with the v23 annual capital clock. The CPI
hyperinflation is downstream: 365× capital → 365× capital-service pricing cost → cost-push.

Next: instrument the first coupled tick — which capital-flow leg multiplies K by ~365 (capital
mobility revaluation? capital-account settlement? a per-period vs per-tick rate in
`world/capital.py`?). This is the R1 clock risk, now CONFIRMED as a real coupling-layer bug.

### Runtime profile (smoke) — the optimisation target
730 ticks × 2 economies × pop 200 = 85.8s (8.5 ticks/s). Top hot spots (cumulative), all in the
per-economy domestic step (so optimising them helps every run, closed or open):
- `run_per_firm_equity_phase` 20.6s (24% of the whole run) — the single biggest cost
- `post_household_equity_trade` 11.6s / 2.15M calls; `_claim_owner_ids` + `_claim_posting_ids`
  6.6M calls each (each equity trade rebuilds the household owner list — redundant recomputation)
- `dict.get` 127M calls; `builtins.sum` 12.5M calls
The per-firm equity market's claim-posting into the demographic bridge is the target. NOT
open-economy-specific.
