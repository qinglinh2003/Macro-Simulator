# V14 Phase 3 Plan — Individual Economic Position → Individual Vital Rates

**Goal:** Couple each person's ECONOMIC POSITION (household wealth rank) to their OWN
vital rates — the demographic engine of wealth concentration. Phase 2 (complete:
commits 5b99977, c9286c1, f338419) moves the population MEAN through macro scalars;
Phase 3 moves the VARIANCE through individual multipliers. The two are kept orthogonal
by construction.

**Emergent targets (never encoded):** wealth-mortality gradient compounding into
concentration (longer rich lives → longer accumulation → larger estates), heir-count
dilution of poor estates, class endogamy, falling intergenerational mobility. Encoded
are only the three microscopic gradient rules; every distributional consequence must
emerge.

**Hazard composition:**

```
hazard_i = mu(a_i)            biological (Phase 0 rates, frozen)
         x M_t                Phase 2: macro level signal, population-wide scalar
         x m_i                Phase 3: rank gradient, exposure-weighted mean == 1
```

Mean-one is enforced at the EXPOSURE level (mortality multipliers weighted by baseline
hazard sum, fertility multipliers weighted by married-fertile exposure), so expected
aggregate deaths/births are invariant at each annual snapshot: Phase 3 changes WHO,
Phase 2 changes HOW MANY. Attribution stays clean in both directions.

## Global Constraints

- One channel at a time; a channel opens only after the previous one's full acceptance.
- Every gradient parameter defaults to 0.0 = channel off = bit-identical to Phase 2
  state (cumulative discipline: same-seed smoke vs the PRE-feedback baseline).
- Signals are RANKS (percentiles), never amounts: dimensionless, growth/inflation
  immune (no Phase 2 jurisdiction creep), robust to the gini-0.93 tail, and the
  empirical object itself (Chetty 2016 measures mortality against income PERCENTILE).
- Individual multipliers are quantile-BUCKET values (default K=5): bounded caches for
  the derived-rates/e(a) machinery, and a computable stratified oracle.
- Deterministic tie-break everywhere (sort by (net_worth, household_id)): zero/negative
  net-worth ties are common in the claims layer and must not break reproducibility.
- Do not encode: gini targets, mobility numbers, e0 gaps, transition curves. Gradient
  STRENGTH may be calibrated to empirical magnitudes (like TFR); dynamics must emerge.
- Frozen oracle, parameterized twice: freeze economy AND pin the rank snapshot =>
  each bucket relaxes to the Leslie steady state of its (M x m_k)-scaled rates.

---

## Phase 3.0 — Stratification Gauges (observation only, ships first)

Goal: the measurement layer every later channel is judged with, plus the reconnaissance
that decides the rank definition. Pure observation: no hazard touched, bit-identical.

Components:

- `demographics/stratification.py`: `WealthStratification` — annual snapshot (same
  year boundary as `DemoMacroSignal`): household net worth via the wealth-tax formula
  (deposits + equity + bank equity − debt, settlement.py), per-adult-equivalent,
  deterministic rank, K quantile buckets, household→bucket map; persons inherit their
  household's bucket; households formed mid-year default to neutral until next snapshot.
- Bridge owns the object; refresh wired next to `observe_macro`.
- Metrics columns (per bucket, K=5): annual deaths, annual births, wealth share,
  population share; plus `age_rank_corr` (the age-wealth confound gauge) and median
  rank by age band.
- Lineage raw material: bridge keeps an annual `(year, household_id, rank, bucket)`
  history list; a post-processing script (scratchpad) computes intergenerational rank
  correlation and the mobility matrix from it + existing birth/death events.

Acceptance:

- [ ] Same-seed 400t smoke bit-identical to pre-feedback baseline (only new columns).
- [ ] Unit: deterministic tie-break, bucket population balance, wealth shares sum to 1,
      neutral default for unseen households.
- [ ] Baseline reconnaissance on a 10y light run: age-wealth profile decides the rank
      definition — |corr(age, rank)| < 0.3 → plain population rank; otherwise
      within-age-band ranks (10-year cohorts). DECISION GATE for 3.1.
- [ ] Baseline stratification portrait of the certified economy recorded (bucket wealth
      shares, per-bucket vital rates — should show NO mortality/fertility gradient yet).

## Phase 3.1 — Mortality Gradient (the concentration engine)

Rule: `m_k = exp(beta_m * (0.5 - r_k)) / Z`, r_k = bucket median rank, Z = baseline-
hazard-exposure-weighted normalizer (mean-one exact at each snapshot). Kernel death
draw: `s = s_base ** m_i` (exact: G-M hazards closed under scaling, s^m == exp(-m∫mu)).
Per-bucket derived rates (key M_t x m_k) reuse the Phase 2.2 cache => the lifecycle
e(a) table stratifies automatically: the rich annuitize over longer lives and save
more WITHOUT any behavioral code.

Config: `mortality_rank_gradient` (beta_m, default 0.0), clip [0.5, 2.0].
Production calibration: beta_m ≈ 0.8 — from the measured de0/dm ≈ −13y (Phase 2.2)
and the empirical top-bottom quintile e0 gap of 8–10y => m spans ~[0.72, 1.4].

Acceptance ladder (the Phase 2 pattern at bucket granularity):

- [ ] beta_m=0 bit-identical; multiplier identity + exposure-weighted mean==1 asserted
      annually; multipliers change only at year boundaries.
- [ ] Pinned power: extreme gradient (top/bottom 4:1), per-bucket death counts diverge
      >4 sigma in ~800t.
- [ ] Stratified frozen oracle: freeze economy + pin snapshot => per-bucket relaxation
      toward each bucket's scaled Leslie steady state (spectral-level test minimum).
- [ ] ESTATE PROBE (formal step): 10k persons, extreme pinned gradient, crash-tolerant
      runner, claim-identity tolerant asserts — deaths concentrate in poor buckets and
      hammer estate/escheat/negative-cash paths on a new distribution. Budget for
      discovering 1–2 rare-event bugs; they block 3.2 until fixed.
- [ ] Production run: per-quintile e0 fans out to the calibrated gap; gini/top-share
      marginal effect and mobility gauges recorded honestly (direction expected:
      concentration up — but the magnitude is a finding, not a target).

## Phase 3.2 — Fertility Gradient (the dilution side)

Rule: `f_k = exp(beta_f * (0.5 - r_k)) / Z_f`, Z_f weighted by married-fertile
exposure. SIGNED: beta_f > 0 = modern negative gradient (poor households more
children, default), beta_f < 0 = historical positive gradient — one parameter, regime
experiments for free. Kernel: multiply at the same site as Phase 2's F (compose).
The drama is zero new code: more heirs in poor households => estate splitting dilutes
per-child inheritance via the EXISTING v13 machinery.

Config: `fertility_rank_gradient` (default 0.0), clip [0.5, 2.0].

- [ ] Same ladder: bit-identity / exact identities / pinned per-bucket births >4 sigma
      / production run with heir-count and per-child-inheritance gauges.

## Phase 3.3 — Marriage Assortativity (the household-level amplifier)

Rule: matching weight x `exp(-lambda * |r_i - r_j|)` on the candidates' household
ranks inside `apply_marriage_market`. lambda=0 MUST take the original code path
(equal-weight sampling would change rng consumption and destroy bit-identity).
First task is reconnaissance of the current sampling structure.

Config: `marriage_assortativity` (default 0.0).

- [ ] Bit-identity at lambda=0 (code-path guard, not weight equality).
- [ ] Pinned power: spousal rank correlation >> 0 under strong lambda; marriage TOTALS
      approximately preserved (first order) — assortativity changes WHO, not how many.
- [ ] Production run: spousal wealth correlation, household gini marginal effect,
      watch emergent side effects (extreme-rank marriage delay).

## Phase 3.4 — Human Capital Transmission (BLOCKED, do not start)

Parent position → child productivity/wage requires heterogeneous individual earnings
on the ECONOMY side, which does not exist yet. Same economy-side debt as the
supply-side growth thread. Revisit after the economy round.

---

## Order & gates

3.0 gauges → rank-definition gate → 3.1 mortality → estate probe gate → 3.2 fertility
→ 3.3 assortativity → [economy-side round] → 3.4.

Post-Phase-3 research runs (not gates): estate/wealth-tax policy counterfactuals on
intergenerational rank correlation (the policy handles finally have a real gradient to
act on); long-horizon endogenous demography-economy cycles (2k persons x 40–60y,
spectral attribution) — shared with the Phase 2 deferred item.
