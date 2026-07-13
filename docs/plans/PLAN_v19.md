# V19 Plan — Technology as an Object, and Exogenous TFP Drift

> **STATUS: ARC COMPLETE (2026-07-14) — ready to merge.** Branch `feat/tech-tfp-v19`
> from dev@19457d0. Commits: b59f0a6 (19.0 object+seam + 19.1 exogenous drift), 0e26c66
> (19.3 LBD seam + accumulator), cfcae28 (19.1 acceptance close-out + diagnostic_v190),
> + this close-out. Bit-identity gate PASSED (v9/v13/full-stack cumulative digests
> a7b1937f/8aa01d8c/1bce181d, before == after, and again with the new metrics once v19
> keys are excluded — the economic trajectory is provably unchanged when drift is off).
> technology suite 12/12; FULL regression 530 passed / 0 failed (xdist).
>
> **19.2 NOMINAL-ANCHOR AUDIT (pre-registered hypothesis CONFIRMED, with a sharper
> mechanism than expected).** Full stack, TFP drift ON (g=1.4%), same seed, mature-segment
> (yr6-10) mean annual inflation vs pi*=1.97%:
>
> | regime | mature inflation |
> |---|---|
> | frozen (central_bank OFF) | **+0.17%/yr** ← closest to stable |
> | headline Taylor (v13 default) | −4.62%/yr |
> | core Taylor (ex-energy CPI) | **−7.26%/yr** ← worst |
> | control (headline CB, NO drift) | −4.61%/yr |
>
> Findings: (1) **NO regime delivers pi*** — there is no nominal anchor pinning the price
> level to target. (2) **The active CB is the deflation ENGINE, not the cure**: switching
> it OFF leaves prices near-stable (+0.17%), both active regimes deflate hard. Monetary
> overreaction (Bernanke-Gertler-Watson), the same signature as the 17.2 matrix (headline
> Taylor stack does the most damage). (3) **Core-targeting is WORSE than headline**
> (−7.26 vs −4.62): stripping energy, the CB sees more disinflation and eases harder, but
> easing does not stimulate a deflating economy — it deepens the spiral. (4) **TFP drift
> barely moves the nominal outcome** under a fixed regime (headline −4.62 with drift vs
> −4.61 without) — a clean real/nominal dichotomy: real growth passes to quantities, the
> monetary regime governs the price level. diagnostic_v191 shipped.
>
> **Implication for the roadmap:** the nominal-anchor FIX (19.2's contingency) IS needed
> and is now scoped by the audit — the failure is a Taylor rule that mistakes
> productivity/capital-deepening disinflation for demand weakness. Candidate fixes (a
> nominal-GDP / money-growth target, or a productivity-adjusted inflation target) belong
> to a follow-on patch, NOT this arc — the audit's job was to name the failure, which it
> did. Logged as the top open thread for the next monetary patch.
>
> **19.1 ACCEPTANCE (honest, pre-registered + refuted + re-derived):**
> - The pre-registered "yr6-10 per-capita CAGR → g/(1−α)=2.0%" was REFUTED — not a
>   mechanism failure but a mis-specified target: the CONTROL leg (g=0) itself grows
>   6.1%/yr per capita in yr6-10, proving the frontier is NOT on a balanced-growth path
>   there (it is still in the capital-deepening transient — investment/depreciation was
>   still 2.2 at yr10 in the v17 portrait). CAGR-in-transition is the wrong estimator.
> - The MECHANISM is exact: the index Z grows at precisely the imposed g (measured 1.40%
>   from the Z series at g=0.014, to 3 decimals).
> - The growth-accounting identity `ĝ_Y = ĝ_Z + α·ĝ_K + (1−α)·ĝ_L` closes on a CLEAN
>   testbed (v2: no pubcap, no firm churn, no gibrat): Solow residual over yr4-9 is 1.86%
>   at g=1.4% vs 0.25% in the g=0 control — a 1.61pp lift ≈ g; the ~0.4pp absolute gap is
>   discrete-CAGR + heterogeneous-firm aggregation + K-timing bias (the control's 0.25%
>   is the noise floor). On the frontier the same residual reads 17% because pubcap_gamma
>   0.3 + firm entry/exit + gibrat are unmodelled aggregation terms — NOT a drift bug.
> - On the frontier the drift produces an AMPLIFIED transitional response: a +15% Z path
>   by yr10 lifts per-capita output +25.6% — a ~1.7× amplification, consistent with this
>   session's level-shift pass-through of 2.03 (TFP compounds capital deepening). The
>   gain is REAL not nominal: both legs deflate on near-identical price paths (P≈0.235).
> - Caveat: the bare v2 economy destabilises after ~yr12 with or without drift (no
>   stabilisers) — a v2 long-horizon fragility, not a v19 effect. diagnostic_v190 shipped.
>
> Original plan preserved below.
>
> ---
>
> **STATUS: PLAN (2026-07-13).** Branch `feat/tech-tfp-v19` forked from dev@19457d0
> (v18 consumption-stratification arc merged). This is the GROWTH-
> FOUNDATION arc: it does not ship a new market or agent — it collects the scattered,
> frozen productivity parameters into one authority and lets that authority move over
> time. It is deliberately sequenced BEFORE the structural-change (v20) and intermediate-
> goods (v21) arcs, because every one of those runs experiments whose conclusions are
> confounded on the current zero-growth, deflating baseline (see the v17-full-stack
> portrait: per-capita output converges, inflation sits at −8%/yr with a frozen TFP).

**Goal.** (1) Refactor productivity into a single `Technology` object — one writer, one
place to ask "how productive is this sector right now" — leaving every genesis anchor and
every flag-off digest bit-identical. (2) Give that object an exogenous law of motion so
TFP drifts at a trend rate `g`, turning the economy from "Solow without technical
progress" (convergence to a point) into a balanced-growth path. (3) Audit the nominal
anchor once real trend growth exists. The object's step interface is designed so an
endogenous law (learning-by-doing, → 2.x) plugs into the same seam without touching a
single production call site.

---

## Why now (the sequencing argument, made explicit)

The v17-full-stack 10-year portrait (dev, seed 7) established two facts that make this
arc a precondition for everything downstream:

1. **No growth engine.** With `A`, `a`, `a_K` frozen literals, per-capita real output
   growth decays 39% → 42% → 17% → 5% and is converging to zero — textbook Solow with
   no technical progress. K/Y stabilises ~2.8; investment/depreciation still 2.2 (still
   climbing to k*). The model has no mechanism for sustained per-capita growth.
2. **No nominal anchor.** Capital deepening pushes unit costs down against a fixed
   nominal side → −8%/yr deflation, nominal GDP shrinking. You cannot separate "did my
   mechanism raise real output" from "prices drifted" on a baseline that is itself
   drifting 8%/yr.

Both are inputs the downstream arcs need clean: v20 structural change and v21 IO both
estimate responses (relative-price and quantity elasticities) that a deflating,
zero-growth baseline confounds. Fix the foundation first.

---

## The one design decision that governs the whole arc

**Productivity is applied as a time-varying MULTIPLIER at the production seam — the
`Technology` object owns the multiplier; per-firm `A`/`a` stay as the frozen genesis
anchors.** We do NOT mutate `firm.A` per tick.

This reuses an existing, proven precedent: `econ._pubcap_factor` (economy.py:470) is
already an economy-wide productivity multiplier, recomputed at the top of each tick and
threaded into `produce()` / `labor_demand_notional()` at all five production call sites
(systems/production.py:32, systems/energy.py:203, systems/planning.py:43,
systems/firm_demographics.py:65,232). The refactor generalises that one multiplier into
a `Technology`-owned factor.

Why multiplier-at-seam beats mutating `firm.A`:

- **Single authority.** One object answers "current productivity"; no per-firm field to
  keep in sync, no new-entrant seeding to remember (v17's E-firm `A_E` anchor and the
  Cobb-Douglas inversion in `labor_demand_notional` both keep working untouched).
- **Genesis exact.** At t=0 the factor is 1.0, so every anchored genesis quantity — unit
  costs, prices, the `A_E=(κ_E·util0)^α` energy anchor that pins genesis `uc_E == w` — is
  bit-for-bit what it is today. Drift only moves t>0.
- **Bit-identical off.** `tfp_drift_rate=0.0` (default) ⇒ factor ≡ 1.0 ⇒ ×1.0 at every
  seam ⇒ every existing config's cumulative same-seed digest is unchanged.

---

## Stages

### 19.0 — The `Technology` object + production seam (PURE REFACTOR, bit-identical)

Introduce `macro_sim/systems/technology.py` (or `domain/technology.py`): a small state
object owning a per-sector TFP index `Z` — a dict `{"c": 1.0, "k": 1.0, "e": 1.0}` (or a
scalar with a sector view). API:

- `Technology.factor_for(firm) -> float` — the current output multiplier for that firm's
  sector. Round-1: returns 1.0 for all (drift off).
- `Technology.step(econ) -> None` — advance the index one tick. Round-1: no-op.

Wire it: `econ.technology` created in `Economy.__init__` (like `_pubcap_factor=1.0` at
economy.py:197). At the five production call sites, the multiplier passed to
`produce()` / `labor_demand_notional()` becomes the COMPOSITE
`econ._pubcap_factor * econ.technology.factor_for(firm)`. Compute-once helper
`econ._output_factor(firm)` to avoid recomputation and keep the call sites readable.
`produce()`/`labor_demand_notional()` signatures are UNCHANGED (they already take one
multiplier); only the value passed changes, and it is ×1.0 in round-1.

**Gate (hard):**
- Cumulative same-seed digest bit-identical to dev@19457d0 across the reference configs
  (v9 non-demo, v13 frontier, the v17 full stack) — the `persist_hash` discipline.
- Genesis snapshot (t=0 unit costs, prices, `A_E`, the CD inversion) unchanged.
- New observation gauges only (see §Metrics), no behavior.

Tests: `test_technology.py` — factor_for defaults to 1.0; step is a no-op; a frontier
smoke is digest-identical with the object present.

### 19.1 — Exogenous TFP drift (THE capability)

Give `Technology.step` a law of motion. Config knobs (all default 0 ⇒ bit-identical):

- `tfp_drift_rate: float = 0.0` — annual trend growth `g` of the (Hicks-neutral) index,
  applied daily: `Z ← Z · (1 + g/365)`.
- `tfp_drift_sigma: float = 0.0` — optional std of a stochastic term around the trend
  (trend + AR(1) deviation or a small random-walk innovation), drawn on a DEDICATED RNG
  substream `random.Random(cfg.seed + 19_000)` so the main stream is unperturbed.
- Round-1 applies a UNIFORM `g` to all sectors (economy-wide Hicks-neutral progress).
  The object is per-sector-ready; per-sector `g` is a 19.3 knob, not a call-site change.

`Technology.step(econ)` runs at the top of the tick, right where `_pubcap_factor` is
recomputed (economy.py:470, before planning/production), so the whole tick sees a
consistent `Z`.

**Pre-registered acceptance (write BEFORE looking at output):**

- **Balanced-growth rate.** With Cobb-Douglas `y = A·K^α·N^{1-α}` and a Hicks-neutral
  index growing at `g`, long-run per-capita real output grows at `g/(1−α)`. With α=0.3,
  set `g = 1.4%/yr` ⇒ pre-register **per-capita real output growth → ~2.0%/yr** in the
  mature segment (years 6–10, after the capital transition). The linear K-sector grows
  per-worker at `g` directly. Report the measured rate honestly against `g/(1−α)`.
- **Growth accounting closes.** The Solow decomposition
  `ĝ_Y = ĝ_TFP + α·ĝ_K + (1−α)·ĝ_L` holds to tolerance every mature year (a soft gate /
  observation, not a hard halt — it is an estimated identity, not an accounting one).
- **Refute the placebo.** The gain must be REAL, not nominal: confirm real per-capita
  output (÷ price index) grows at ~`g/(1−α)` while the nominal/real split is clean. (This
  is the v14/v16 pass-through lesson — a drift that only moves prices is a null.)

Diagnostic `diagnostic_v190.png`: per-capita output/consumption/capital/real-wage on a
log scale (BGP shows as parallel straight lines), TFP index, growth-accounting bars.

### 19.2 — Nominal-anchor audit

Now that a real trend exists, ask the question the v17 portrait couldn't pose: **does the
central-bank rule deliver its inflation target, or does the −8% deflation persist?**

- Pre-registered hypothesis (from the v17 portrait): the model has no nominal anchor —
  productivity growth + a fixed nominal side yields persistent deflation regardless of
  the Taylor stack; measured inflation will NOT converge to `π*`.
- This is an AUDIT (portrait + experiment across CB regimes: headline-Taylor / core /
  frozen-rate), not a mechanism. If it confirms the anchor is broken, the FIX is scoped
  as a follow-on sub-stage (candidate: the money-growth / nominal-GDP side of the CB
  rule, or the price-index construction) — do not pre-commit a mechanism before the audit
  names the failure. If the anchor holds once TFP grows, report the null and move on.
- Honest-null discipline: whichever way it lands, the finding is logged with the
  arithmetic, not spun.

Diagnostic `diagnostic_v191.png`: inflation vs `π*` under the CB regimes, with and
without drift.

### 19.3 — Per-sector drift + the learning-by-doing seam (SEAM PROOF, flag-gated)

Two demonstrations, both default-off, that lock in the object's design promises:

- **Per-sector `g`.** Show the object holds a per-sector vector: differential drift
  (e.g. lagging energy/services productivity) produces Baumol relative-price drift — a
  real regularity, and the hook the v20 structural-change arc and v18's necessity/luxury
  split will pull on. Purely a config vector; zero call-site change.
- **The LBD interface.** Demonstrate an ENDOGENOUS law — learning-by-doing,
  `Z = Z₀·(cumulative_output)^θ` — plugging into the same `Technology.step(econ)`
  interface with NO change to any production call site. Ship it behind
  `tfp_law="exogenous"|"learning"` (default `"exogenous"`), θ default 0. This is the 2.x
  seam-proof (endogenous growth is a 2.x module, not this arc), not the module itself.

---

## Metrics (observation only)

Add to `reporting/metrics.py`: `tfp_index_c/k/e` (the current `Z` per sector),
`tfp_growth` (annualised `Ẑ`), `solow_residual` (measured TFP growth from the growth-
accounting decomposition — the empirical counterpart to `tfp_growth`, whose GAP is a
model-health signal), and a `per_capita_real_output` convenience series. Ship a
`diagnostic_v19X.png` per sub-stage (per the diagnostic-plot-per-version discipline).

## Working discipline (binds every stage)

- Flag-gated, default-off; cumulative same-seed digest bit-identical to dev@19457d0 at
  every stage while flags are off (`persist_hash`).
- Genesis anchors exact (the `Z(0)=1.0` guarantee); the v17 `A_E` anchor and the CD
  inversion are regression-checked.
- Pre-register + refute; honest nulls (the 19.2 audit especially).
- Dedicated RNG substream `seed + 19_000` for any stochastic drift; the main stream stays
  unperturbed.
- §4 is judge not target (§0-ii): the balanced-growth rate is the acceptance regularity,
  not a fitted knob.

## Out of scope (explicit)

- Endogenous growth (R&D sector, varieties, creative destruction, human capital) — 2.x.
  19.3 only proves the seam; it does not build the engine.
- The nominal-anchor FIX, if 19.2 finds one is needed, is scoped there — not pre-committed.
- Structural change (v20) and intermediate goods / IO (v21) — downstream arcs this one
  unblocks.
