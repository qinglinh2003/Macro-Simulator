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

## Discipline (inherited)

Freeze source during any diagnostic run (a mid-run edit invalidates it or crashes the
manifest reader). Same-seed twins for attribution; ≥3 seeds before "replicated". Interpret
`measurement_status` literally. Flag-gated fixes default-off bit-identical. Record honest
nulls and refutations, not just confirmations.

---

## FINDINGS LOG

_(appended as they land — newest first)_

### (pending) Smoke — R1 clock + R2 identities
Not yet run. First gate before any long horizon.
