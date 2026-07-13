# V18 Consumption Stratification Plan — Necessities, Luxuries & the Deprivation Boundary

> **STATUS: ACTIVE (kickoff 2026-07-13).** Preconditions are MET: the v16 labor arc
> (L0–L6) and the v17 energy arc (17.0–17.5) are both merged into dev and the
> composition gate PASSED (dev@b8fecd4, PARALLEL_LOG 2026-07-13). v18 forks from
> dev@b8fecd4 on `feat/consumption-v18`, worktree `../macro-simulator-v18`.
> Code references below verified against b8fecd4.
>
> **v16/v17 handoff notes that bind this arc:** under `labor_person_efficiency`,
> `f.hired` is in EFFICIENCY units; full-stack acceptance runs should enable the
> v16-L6 flags (footfall/subscale-exit/K-entry) — the K sector starves without them
> under persistent matching. Household energy (17.1) is bought INSIDE the energy
> market session (systems/energy.py:280-295), before production and goods — the
> hierarchy "energy → goods" is already physical in the phase order.

**Goal:** Split the single consumption good into NECESSITY and LUXURY sectors behind a
flag, make the household budget an explicit priority hierarchy, and make "real
inequality" measurable for the first time — Engel's law as an emergent test, group-
specific inflation, and person-level deprivation spells. Deprivation is instrumented
as an OBSERVED DOMAIN BOUNDARY, not resolved by a death mechanism.

**Why now (ranked by leverage):**
1. **Completes the goods-structure gap's demand side.** v17 took energy (the input +
   shock member); necessities/luxuries is the remaining named member with
   distributional leverage (developer brief: "energy, durables, necessities, and
   luxury goods are not first-class categories").
2. **It is the cheapest continuation of the v17 grammar.** The v17.1 behavioral
   primitive ("need met first, price-inelastically, up to the budget") generalizes
   from energy to a necessity good verbatim; the E-firm precedent (existing Firm
   grammar + one structural difference) covers the sector split; the headline/core
   index machinery (metrics.py:1369-1392, `cpi_headline`) is the composition target
   for group CPIs.
3. **It multiplies the value of everything v13–v17 built for distribution.** LIFO
   layoffs (v16), energy poverty (v17), housing burden (v15), Phase 3 strata — all
   currently read against a single homogeneous good, so every household faces the
   same price level. Non-homothetic demand makes incidence honest.
4. **A subsistence basket gives the safety net an absolute yardstick.** Benefits, JG
   wage, and pension are all anchored to the mean posted wage
   (systems/settlement.py) — "does the floor cover subsistence?" is currently
   unanswerable. v18 makes it a gauge.
5. **Crisis dynamics get the missing asymmetry**: real recessions concentrate in
   deferrable consumption. Necessity demand should hold while luxury collapses —
   emergent sector cyclicality, readable against the 17.2 stagflation matrix and the
   v15 housing-depression portrait.

**The spine of the arc: measure → structure → validate → policy → couple.** Each stage
flag-gated, default off, flag-off bit-identical to the dev@b8fecd4 baseline
(cumulative discipline); one stage's full acceptance before the next.

---

## Global Constraints

- **No acute-death mechanism — the domain-boundary ruling (settled by research,
  2026-07-12).** Since 2000 there is NO case of large-scale acute mortality from
  purely economic causes: all six IPC famine declarations (Somalia 2011, South Sudan
  2017/2020, Sudan 2024/2025, Gaza 2025) are conflict/blockade-driven; the deepest
  peacetime collapses (Venezuela −75% GDP, Zimbabwe 2008, Sri Lanka 2022, Lebanon)
  produced CHRONIC excess mortality via health-system decay plus EMIGRATION as the
  clearing valve (Venezuela: 7.7M, ~25% of population). The real-world clearing
  mechanisms (migration, humanitarian aid, remittances) are all OUTSIDE a closed
  economy, so simulated starvation deaths would be an artifact of missing mechanisms.
  Instead: the model's validity domain is declared as "acute deprivation gauge ≈ 0";
  runs that breach it get a `summary.json` health flag and their post-breach
  demographic/long-run paths are OUT OF DOMAIN (distributional readouts remain
  valid). Chronic-gradient mortality is a later, separately-anchored coupling (18.4),
  never part of the core.
- **The basket is an external anchor, never a tuning knob.** Basket size is fitted
  once at genesis to an anchored necessity share (see 18.1) and then frozen; it must
  never be adjusted to make deprivation gauges quiet.
- **Housing stays contractual — v15 is not reopened.** Rent is a per-tick
  claim-layer transfer AFTER the goods market (housing/rental.py, economy.py step),
  reaching consumption only next tick via `deposits_prev`; mortgages amortize through
  generic credit. The discretionary hierarchy is therefore energy → necessity →
  luxury ONLY; rent/debt service remain settlement flows. The full canonical ordering
  (energy market → goods N-session → goods L-session → settlement → debt service →
  housing) is documented here once; changing rent's position is out of scope.
- **B1 is untouched.** The consumption budget formula
  (behavior/planning.py, `alpha1·Y^e + alpha2·wealth`) stays one nominal number,
  A4-capped at market time (systems/goods.py:21). The N/L split lives entirely in the
  MARKET PHASE ordering: the necessity session is quantity-targeted, the luxury
  session takes the residual. Inelasticity and Engel behavior must EMERGE from the
  ordering, exactly like v17.1's energy priority.
- **Wealth effects fall on luxury for free — verify, don't re-plumb.** Because the
  necessity purchase is need-quantity-capped, any budget expansion (v15.5 housing
  wealth effect, alpha2) flows to the residual luxury session automatically. This is
  an acceptance check, not a code change.
- Every index/gauge inherits burn-in discard semantics (the housing
  `affordability.py` idiom: discard the genesis transient, then anchor ratios to 1).
- New randomness on dedicated substreams; per-stage `diagnostic_v18x.png`; honest
  acceptance write-ups (nulls as nulls); no Co-Authored-By trailers.
- Intervention handles in **Policy** (run-time mutable), structural parameters in
  Config.

---

## 18.0 — Subsistence Basket & Deprivation Gauges (observation only, the v16-L0 pattern)

**Purpose:** create "deprivation" as a measurement object BEFORE any behavior changes,
and wire the domain-boundary rule. Question answered: *does the current baseline
contain anyone below subsistence — for how long, how deep, and who?*

**Why first:** the instrument must precede the mechanism — 18.1's Engel acceptance,
18.2's incidence readings, and 18.4's couplings all read this gauge; and the pre-split
fact base is needed (if the baseline already shows long deprivation spells, that is a
finding to diagnose before restructuring anything).

Components:

- Basket defined as a MEASUREMENT standard: per-person subsistence need using the
  existing needs-weight machinery (`need_weight_for_person`,
  demographics/economic_bridge.py — children weighted, charged to adults) ×
  a per-need quantity anchor, plus the v17.1 energy need when `energy_household` is
  on. No decision equation reads it.
- Person-level spell counters on REALIZED allocation: the bridge already attributes
  household spending to persons (`post_household_consumption`,
  `consumption_allocated_tick`) — spell state = consecutive days a person's allocated
  real consumption sits below 100% / 60% / 30% of their basket need. Flow-sized
  updates, no full-population scans.
- Gauges: spell-duration distribution, deprivation stock & cumulative person-days per
  threshold, strata & age gradients, and **floor coverage**: benefit / JG wage /
  pension each divided by the basket cost at current prices (the safety net's
  absolute yardstick; all three are wage-anchored today, so coverage is a genuinely
  new signal under price shocks).
- **Domain-boundary health flag**: sustained sub-60% spells (>30 consecutive days) or
  any sustained sub-30% spell (>7 days) set a `deprivation_boundary` health flag in
  `summary.json` (runs registry). Documented semantics: post-breach demographic and
  long-run readings of that run are out of the model's domain; thresholds are
  REPORTING conventions, not biology.
- **RESOURCE GATE on the boundary (added after the 10y portrait).** The acute/chronic
  boundary trip additionally requires the household to be DEPOSIT-POOR (liquid cash
  claim < one period's basket). Reason: `consumption_allocated_tick` is a realized
  FLOW, and during a bank shakeout (v11.5 suspension) a WEALTHY household's flow briefly
  hits zero because its still-owned deposits are frozen — a liquidity artifact the
  flow-only gauge misreads as deprivation (its wealth gradient inverts: the TOP quintile,
  not the bottom, reads "deprived"). The gate excludes those households; genuine
  destitution (flow-poor AND savings-poor) survives it. A raw flow gauge
  (`below100/60/30_share`) is still reported as a broad observation alongside the
  gated `destitute_share`.

Acceptance:

- [ ] Flag off ⇒ bit-identical; on ⇒ only observation columns move. **[MET: macro +
      frontier digests unchanged with non-default knobs; no gauge columns leak.]**
- [ ] Pre-registered (REVISED after the 10y portrait — an honest finding, not a
      violation): the healthy baseline (JG + benefits) produces NO acute deprivation in
      the normal full-employment regime (acute stock == 0 at every low-u tick), but DOES
      breach at the trough of the v13 arc's **second endogenous downcycle + bank
      shakeout** (~year 8.5, u→20%, banks→0). That breach is GENUINE recession
      destitution (~24 of ~600 persons, deposit-poor AND flow-poor — they survive the
      resource gate), confined and transient, destitution share bounded < 0.15. The
      boundary flag correctly marks that trough as out-of-domain. The line also
      discriminates: safety-net-off ⇒ acute stock ~22, destitute ~16%, bottom wealth
      quintile 62% below vs top 8% (emergent gradient). **[MET.]**
- [ ] Gauge continuity test prepared for 18.1 (basket definition must survive the
      sector split with the N-good substituted for the composite good).

## 18.1 — The Sector Split & the Budget Hierarchy (the structural stage)

**Purpose:** non-homothetic demand is born here. Question answered: *does Engel's law
emerge from a priority ordering, with no preference parameters seeded?*

**Why here:** it is the arc's only structural change and must land on 18.0's
instruments. Within the stage the order is: mechanical session split first
(degenerate, statistically baseline-equivalent), hierarchy second.

Components:

- **Firm side (the E-firm precedent):** genesis c-firms are tagged into N-firms and
  L-firms via the existing `sells` field (domain/agents.py) and two lists
  (`econ.n_firms`/`econ.l_firms` alongside `c_firms`); same tech, same labor market
  (v16 rosters — E-firm precedent from the composition gate), same credit, same
  equity, same energy input (`e_coeff` uniform per the v17 ruling). Sector sizes
  fitted at genesis to the anchored aggregate necessity share.
  **Entry chooses a sector** by the per-sector excess-profit signal (the existing
  entry rule evaluated per sector) — NOT frozen (unlike v17's E-sector: these are
  ordinary competitive sectors with many firms; the freeze rationale — shock-summoned
  supply in a 4-firm sector — does not apply).
- **Household side (the v17.1 grammar, second application):** the goods phase becomes
  two sequenced sessions of the existing market protocol. NECESSITY session:
  `BuyOrder(demand = household basket need, budget = A4-capped B1 budget)` — quantity-
  targeted, protocol-native seller choice. LUXURY session:
  `BuyOrder(demand = inf, budget = residual)` — the current semantics verbatim.
  Documented behavioral primitive (B1 extension): "necessity need is met first,
  price-inelastically, up to the budget; luxury takes the residual."
- Government purchases and the capital-goods market are untouched (gov tender stays
  on the cheapest-first path; which sector the government buys from is a documented
  choice — default: both, pro-rata to sector size).
- **Calibration anchors (REVISED after measurement):** the necessity quantity per
  need-unit is anchored to genesis config = `necessity_share0 · w_firm0 / p_firm0` (the
  v17.1 energy-need idiom), FROZEN. Because the v13 genesis is a deep slump, the
  *genesis* necessity share is ~100% (households can only afford necessities in the
  depression — realistic, not a target); it falls over development to a mature ~20–30%
  (a plausible modern essentials share) as consumption grows ~5×. So the meaningful
  calibration target is the MATURE share (20–30%), not a genesis share. The RANK
  GRADIENT is never fitted — and the Engel axis must be expenditure **per need-unit**
  (the fixed necessity need scales with household size, so total-expenditure gradients
  wash out; per need-unit, share ≈ const/E). Measured: bottom-quintile 28.8% vs top
  15.9% = **1.82×** (> the 1.5× bar).

Acceptance:

- [ ] Flag off ⇒ bit-identical (single-session code path preserved verbatim). **[MET:
      macro + frontier digests unchanged with non-default knobs; no sector columns.]**
- [ ] **Engel's law emerges**: necessity share falls with per-need-unit expenditure —
      bottom/top quintile ratio 1.82× (§4-style structural judge; not seeded). **[MET.]**
- [ ] Wealth-effect routing: because the necessity purchase is quantity-capped, budget
      growth flows to the residual luxury session automatically — necessity share falls
      as per-capita expenditure rises (the Engel gradient IS this check). **[MET.]**
- [ ] Baseline QUIET over a long horizon: no sector inventory limit cycles, stable
      relative price after burn-in, sector entry does not oscillate (watch: two
      sectors sharing one entry pool can seesaw — gauge sector entry rates).
- [ ] **Markup watch (pre-registered emergent question):** inelastic N-demand ×
      markup grammar ⇒ does the N-sector pin at `mu_max`? Gauges: sector mean markup,
      time-at-ceiling share, sector HHI (the v17.0 watch transplanted). Reported
      either way; regulated markup is the candidate correction, not a hidden retune.
- [ ] 18.0 gauges continuous across the split (basket now priced in N-goods).

## 18.2 — Indices & Incidence (observation upgrade + validation, zero new mechanism)

**Purpose:** cash out the arc's prize. Questions answered: *is recession consumption
asymmetric (necessities hold, luxuries collapse)? Whose inflation is whose?*

**Why here:** a new structure must first be validated under EXISTING dynamics (the
v17 "quiet baseline before any shock stage" discipline, extended to "correct
composition response under already-certified shocks") before it grows handles.

Components:

- Sector price indices P_N / P_L (sales-weighted, the metrics.py idiom); the
  aggregate CPI composes WITH the existing v17.1 headline/core machinery (core = all
  c-goods = N+L; headline adds energy — one definition, documented, no fork);
  **group-specific CPI** per stratum using each stratum's own expenditure weights —
  plutocratic vs democratic index divergence becomes a reported series.
- Real floor coverage under the group indices (benefits are wage-anchored; coverage
  under an N-price shock is the honest stress signal).
- **Validation experiments (each pre-registered):**
  - Re-run the 17.2 energy shock (machinery landed, matrix run 2026-07-13) with the
    v18 stack on: L-sector contraction deeper than N; strata real-income incidence
    divergent under group CPIs; deprivation spells concentrate in the bottom strata.
  - Re-run the v15 housing-depression portrait (standing to-do) with composition and
    spell readouts.
  - Inflation-incidence experiment: a pinned N-price shock ⇒ quantified gap between
    bottom-stratum and top-stratum inflation (the Phase-2 pinned-signal paradigm).

Acceptance:

- [ ] Composition responses match pre-registration (or the refutation is documented).
- [ ] Acute gauge stays EMPTY across all normal experiments (the domain-boundary rule
      in live use for the first time).
- [ ] Headline artifacts ship as `diagnostic_v182.png` + results notes.

## 18.3 — Policy Handles (the v17 handle-factory tradition)

**Purpose:** turn the structure into a government control surface. Question answered:
*how much do necessity-targeted instruments beat undifferentiated ones,
distributionally, per unit of fiscal cost?*

**Why here:** policy readings need the validated structure responses of 18.2 for
attribution. All handles in Policy, mid-run mutable.

Components:

- **Differential VAT**: per-sector VAT rates (the buyer-side wedge already exists in
  the goods session; the remit grammar transplants from v17.0's energy excise).
  Reduced/zero N-rate is the classic instrument.
- **Necessity subsidy vs cash transfer** (the §34 wealth-allowance reprise on the
  consumption side, pre-registered): equal fiscal cost, compare bottom-strata real
  consumption, deprivation spells, and leakage — the flat instrument should prove
  regressive-in-effect relative to the targeted one. (v17.5's targeted energy-subsidy
  finding is the sibling result — compare against it.)
- **Crisis price cap on necessities**: the 17.4 cap/rationing/compensation triple
  plugged onto the N-sector session — 17.4 machinery is now on dev; generalize,
  don't duplicate.
- **Optional experiment flag:** index benefits/JG to the N-price index instead of the
  mean wage (`floor_index_mode`) — the wage-anchored floor's failure mode under a
  necessity-price shock, made switchable.

Acceptance:

- [ ] Each handle conserves through fiscal (atomic flows, remit tested); off ⇒
      bit-identical.
- [ ] Subsidy-vs-transfer scorecard published honestly (strata consumption, spells,
      fiscal cost, leakage) whichever way it comes out.
- [ ] Cap binding ⇒ measured excess demand + rationing conserves (17.4 acceptance
      shape); `diagnostic_v183.png`.

## 18.4 — Couplings (one at a time, the Phase 2 paired-run paradigm)

**Purpose:** connect deprivation to the rest of the model. Each coupling its own
flag, frozen-reference paired-run acceptance.

**Why last:** couplings read signals (spells, gaps) that 18.0–18.2 must first prove
stationary and trustworthy; the v17.5 closing structure.

Components, in priority order:

1. **Inter-household family transfers**: a kin's sustained subsistence gap triggers
   support transfers along the v13 relation links (parent↔adult-child), through the
   existing person-claim/ledger rails, capped by donor surplus. Reality's first-line
   private clearing mechanism for deprivation; also isolates the truly exposed
   population (no kin, no assets, outside the floor) as a distributional object.
2. **Chronic mortality gradient** (deferrable beyond the arc): exposure-duration-
   weighted hazard adjustment on the existing v13 mortality, effect size anchored to
   the poverty-mortality-gradient literature, applied person-level (the v17.5
   fuel-poverty→mortality channel is the in-repo precedent — same grammar, same
   burn-in signal pattern). Two pre-registered guardrails: (a) the MALTHUSIAN-VALVE
   refutation — deprivation deaths must close <1% of the poverty gap in any crisis
   run, else the effect size is wrong; (b) inequality gauges additionally reported on
   the deceased-inclusive cohort basis (survivorship-bias watch).
3. **Childhood deprivation → e_i interface**: RESERVED only (a documented hook, no
   implementation) — v16-L4's `labor_person_efficiency` is live on dev, so the slot
   exists; the transmission belongs to the Phase 3.4 human-capital arc.

Acceptance:

- [ ] Each coupling: off ⇒ bit-identical; on ⇒ paired-run difference matches
      pre-registration.
- [ ] Family transfers measurably shorten the baseline spell tail (direction
      pre-registered); transfers conserve through the claim identity gates.
- [ ] Chronic channel ships ONLY with both guardrails green; otherwise the effect
      size goes back to the literature.

---

## Explicitly NOT in v18

- **Acute death mechanism** — permanently replaced by the domain-boundary rule
  (reopen only for a deliberate historical-famine scenario arc, if ever).
- **Durables** — a later arc; durables will tag INTO the N/L sectors (appliances vs
  cars) rather than reopening the goods structure.
- **Fertility channel of deprivation** — separately anchored, larger-effect, its own
  coupling arc.
- **Migration valve** — the open-economy arc's material (the research finding: it is
  reality's main deprivation-clearing mechanism, and it is definitionally absent
  here).
- **Household hoarding / storage of goods** — households still hold no inventory
  anywhere in the model (the v17 ruling stands).

## Interactions ledger

- **v16 labor**: person-level income attribution feeds household budgets unchanged;
  floors stay wage-anchored (coverage gauge is the new lens); LIFO-layoff incidence ×
  deprivation spells is a headline 18.2 read. N/L firms are ordinary employers on
  v16 rosters (the composition-gate E-firm precedent). Full-stack runs enable the L6
  flags per the handoff note.
- **v17 energy**: energy keeps first position in the hierarchy (bought inside the
  energy session, before goods — already physical); `e_coeff` uniform across N/L
  firms; energy poverty and consumption deprivation are SEPARATE gauges over the same
  strata; 17.4 cap machinery is the shared implementation base for 18.3's N-cap;
  18.2 composes the group CPIs with `cpi_headline`, one definition.
- **v15 housing**: rent stays contractual post-goods (documented ordering); the
  housing-depression portrait re-runs in 18.2 with composition readouts; the v15.5
  wealth effect must route to luxury for free (18.1 acceptance).
- **Demographics**: basket reuses `need_weight_for_person`; spell gauges read the
  existing person allocation bridge; strata gradients are Phase 3 gauges' direct
  consumers.
- **Firm demographics**: entry gains a sector choice (per-sector profit signal);
  watch sector-entry oscillation (18.1 gauge).

## Sequencing

v18 is the SEQUENTIAL next arc on dev — v16 (labor) and v17 (energy) are already
merged and the composition gate passed (dev@b8fecd4), so there is no parallel
coordination: the flag-off baseline is simply dev@b8fecd4, and 18.2 re-runs the v17.2
shock machinery that already lives on dev. One stage at a time, full acceptance before
the next; 18.4's chronic channel may be deferred beyond the arc without blocking
closure. Branch pushed after every accepted stage (remote backup discipline). On
completion, merge back into dev normally.

## Standing decision log (agreed in design discussion, 2026-07-12)

| Decision | Ruling |
|---|---|
| Acute deprivation deaths | NOT modeled — domain-boundary health flag instead; grounded in the 21st-century evidence review (all famine declarations conflict-driven; peacetime collapses clear through migration/aid, both absent in a closed economy) |
| Chronic mortality | Later coupling (18.4), literature-anchored, Malthusian-valve + survivorship guardrails mandatory |
| Basket | External anchor fitted once at genesis, needs-weighted per person (existing machinery), never tuned to quiet the gauges |
| Hierarchy scope | Discretionary only: energy → N → L; rent/debt service stay contractual settlement flows (v15 not reopened) |
| B1 | Untouched — one nominal budget; the split lives in market-session ordering (v17.1 grammar) |
| N-session form | Quantity-targeted BuyOrder (demand = basket need); L-session = residual, demand=inf (current semantics) |
| Wealth effect | Falls on luxury emergently (N is quantity-capped); acceptance check, not a re-plumb |
| Sector demographics | NOT frozen — entry picks a sector by per-sector profit signal (many-firm competitive sectors; the E-sector freeze rationale doesn't apply) |
| Floors | Stay wage-anchored by default; N-price indexation is an experiment flag (18.3), coverage gauge from 18.0 |
| Government purchases | Both sectors pro-rata by default (documented choice) |
| Aggregate N-share anchor | 40–55% of goods consumption at genesis (excl. energy/housing); the rank gradient must emerge, never fitted |
