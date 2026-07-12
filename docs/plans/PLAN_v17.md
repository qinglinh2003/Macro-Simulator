# V17 Energy Plan — The First Intermediate Input & the Shock Generator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce energy as the economy's first INTERMEDIATE INPUT and its first structural
EXOGENOUS SHOCK SOURCE. Energy is NOT just another consumption good — it plays three roles at
once: an input to ALL production (intermediate consumption, excluded from GDP), a necessity
consumption good for households (GDP), and a storable commodity (inventory, an outside item
like `f.inventory`). Conflating the first two would double-count GDP; national accounts draw
the intermediate-exclusion line and we draw it in the same place (the v15 three-way-split
discipline, applied to flows instead of assets).

**Why energy (ranked by leverage on standing open threads):**
1. **The deferred shock generator.** The model has owed itself a genuine exogenous shock
   since v11 ("bank failure machinery latent, awaiting a real shock"), through the JG hard
   test (supply shock at capacity + inflation, open thread), to v15.2's double-crash test.
   The working principle — model mechanisms realistically, let phenomena emerge from real
   shocks, never tune a module to manufacture a crisis — has lacked an honest shock origin.
   An E-sector capacity shock is the closed-economy analog of the oil embargo.
2. **Cost-push inflation exists for the first time.** Unit cost becomes
   (wagebill + energy bill)/output, so inflation and unemployment can finally move TOGETHER.
   The fiscal-dominance + JG + Taylor stack has never faced stagflation — the Taylor rule's
   two arguments have never disagreed.
3. **Distributional bite.** Energy is price-inelastic necessity demand: price spikes squeeze
   the bottom of the distribution first. Energy poverty feeds the Phase 3 stratification
   gauges and the economy→vital-rates arc directly.
4. **A government-handle factory.** Energy is the most state-entangled sector in real
   economies: excise, strategic reserves, SOEs, price caps, crisis rationing, windfall
   taxes — the full 2022 European crisis menu becomes a controlled experiment.
5. Fills the recognized goods-structure gap (developer brief) with its highest-leverage
   member: the one category that is simultaneously an input to everything, a household
   necessity, and a natural shock story.

**Honest caveat, resolved by parallelization:** the dev-at-fork labor market is
frictionless (no natural rate), so any employment-cost reading against stagflation would
carry a jump-variable artifact. Per the parallel protocol (§5), the 17.2 EXPERIMENT MATRIX
therefore runs AFTER the composition gate — once, with the v16 labor layer (search friction
+ relationship wages) live, no disclaimer needed. 17.0–17.1 plumbing/quietness acceptance
is unaffected and proceeds inside the arc against spot labor.

**Sequencing (amended by `PLAN_v16v17_parallel.md` — the coordination contract):** v17
develops IN PARALLEL with the v16 labor arc. `feat/energy-v17` forks from the
post-trunk-refactor dev (2b7979a); v17 rebases/merges dev at every v16 stage freeze
(小步跟进); v16 merges into dev first; this arc owns the composition gate after both land.
The housing coupling in 17.5 additionally requires the v15.2 size-gate outcome.

## Global Constraints

- **GDP intermediate exclusion is the accounting keystone**: energy sold to firms is
  intermediate consumption, NEVER GDP; energy sold to households is consumption GDP;
  E-firm capital purchases are investment GDP. A direct identity check (GDP = C + I + G,
  energy intermediates excluded) is part of every stage's acceptance.
- Energy stocks (E-firm output inventory, downstream input inventories, SPR) are OUTSIDE
  items like `f.inventory` — A4/A5 are blind to them by construction. Ledger flows are
  ordinary transfers; no new monetary primitive.
- Energy is CONSUMED in production (destroyed), so no conservation hard gate; instead a
  per-tick flow soft gauge: `produced == used_in_production + household_consumption
  + Δ(all stocks)` within tolerance.
- Every energy signal (price index, coverage, poverty share) inherits BURN-IN DISCARD
  semantics; no downstream channel may smooth genesis relaxation into a baseline.
- Genesis is FITTED AT t0 (the v15 lesson, third application): supply = demand at anchored
  utilization, all input inventories at target coverage — no artificial opening
  shortage/restocking wave. Restock demand must come from CHANGE, not seeded mismatch.
- **Bullwhip watch from day one**: coverage-target restocking + double demand (consumption
  + restock) is the classic inventory-cycle amplifier. Gauges (coverage-days distribution,
  restock share of energy demand, E-inventory volatility) ship in 17.0; the no-shock
  baseline must be QUIET (no limit cycles) before any shock stage begins.
- **Markup discipline watch**: few E-firms × inelastic customers × markup grammar. Gauges:
  E-sector mean markup, fraction of time at `mu_max`, E-sector HHI. The no-shock baseline
  must not pin markups at the ceiling; if it does, that is a finding to diagnose (regulated
  markup is the candidate correction), not a parameter to hide.
- Shocks are EXPLICIT scenario flags, never ambient; hoarding/speculation is a separate
  flag, default off (the v15 speculation precedent).
- Each stage flag-gated, default off, bit-identical to the pre-v17 baseline when off
  (cumulative same-seed smoke discipline). Every stage ships its `diagnostic_v17x.png`.
- Intervention handles live in **Policy** (run-time mutable — they are mid-run crisis
  instruments, the exact use-case the Config/Policy split was built for); structural
  parameters live in Config.
- The buyer-ordering point in the energy market session is an INJECTABLE RULE from 17.0
  (default = the native budget-capped cheapest-first). Price caps and priority rationing
  (17.4) plug in there; the interface is reserved now so 17.4 does not re-open the phase.

---

## v17.0 — E-Sector & the Firm-to-Firm Energy Market (production reorder)

Goal: energy exists, is produced under a capacity constraint, is bought and stocked by
downstream firms, and enters their unit cost — with no household demand and no shocks.

Components:

- **E-firm**: the existing Firm grammar (B2 expectations, B3 markup, B4 wages, inventory,
  same labor market, same credit, same equity market) with ONE structural change — the
  production function is CAPACITY-CONSTRAINED: `y_E = min(a_E · L, κ · K_E)`, with κ·K the
  binding edge near baseline. Capital is bought on the EXISTING capital-goods market, so
  short-run supply elasticity ≈ 0 and long-run supply response emerges from capital
  accumulation speed — nothing hand-tuned.
- **Frozen sector demographics**: fixed `n_e_firms` (default 4); entry/exit disabled for
  the whole 17.0–17.4 arc. E-firm entry with a construction lag is a later flag (and the
  lag mechanism generalizes to the v15.4 builder). Rationale: entry signals are
  profit-driven; a shock's excess profits would otherwise summon supply in ticks when
  reality takes years.
- **New phase order**: planning → labor → **ENERGY MARKET** → production → goods. Firms
  buy energy before producing; a firm short of energy cuts output proportionally
  (`y = min(a·L, energy_available / e_coeff)`).
- **Downstream input inventory** (the one genuinely new mechanism): every producing firm
  (c- and k-firms) holds an ENERGY input stock with a target coverage of
  `coverage_ticks` × expected energy use — the phi grammar mirrored onto an input. Restock
  order = gap-closing, budget-capped. Valuation at average cost; energy used enters B3 unit
  cost: `uc = (wagebill + energy_used @ avg_cost) / output` — the heart of cost-push.
- **Energy excise handle** (`tax_energy_rate`, Policy, default 0): the VAT remit grammar
  transplanted. The fiscal stake in energy prices exists from day one, inert by default.
- **Rationing interface reserved**: buyer ordering in the energy session is an injectable
  rule; default native.
- **Genesis fitting**: energy cost share of output anchored at 5–8% (sets `e_coeff`);
  input coverage 30 ticks (= 30 days under the day-tick calendar — the real-world crude
  coverage anchor lands on the tick count for free); E-sector genesis utilization ~0.85
  (headroom so trend growth does not short the market at t1); E-firm count/size fitted so
  supply meets fitted demand.

Acceptance (CLOSED 2026-07-12; commit 444dce3 + the close-out commit; diagnostic_v170.png):

- [x] Flag off ⇒ bit-identical to the pre-v17 baseline (same-seed smoke hash-equal to
      dev@2b7979a on the v13+housing frontier config).
- [x] Flow soft gauge closes every tick (~1e-12; firm EXITS destroy input stock — the
      one honest gap source, exact in no-death worlds); GDP identity holds by the
      sector split (consumption metrics never read E-firms).
- [x] Baseline QUIET — with three structural findings landed en route (PARALLEL_LOG):
      E-firms produce BEFORE the market (stock-out B2 death spiral); unconditional
      depreciation-replacement floor (absorbing death); unfilled demand feeds
      expectations + RESERVE-MARGIN accelerator k*=d^e/(κ·util0) (adaptive accelerator
      chronically lags a growing economy); Cobb-Douglas + capacity clamp,
      A_E=(κ·util0)^α (linear tech ⇒ Baumol relative-price artifact, 7x/decade).
      Frontier residual: moderate ENDOGENOUS capacity-investment cycles (crunch →
      markup episode → catch-up → slack) — emergent, self-correcting, reported not
      tuned; cost share settles ~8-10%.
- [x] Cost-push wiring verified by the pinned TFP test (E unit cost up ⇒ downstream
      prices up through B3); the frontier diagnostic independently shows cost-push
      inflation during endogenous crunches (on-world yoy +0.2-0.4 vs flat baseline).
- [x] Bullwhip + markup + HHI gauges live in metrics and diagnostic_v170.png.

## v17.1 — Household Energy Demand (the necessity & the CPI)

- Per-household energy NEED ∝ household size (scale anchored so household energy spending
  lands at 5–10% of consumption); purchased BEFORE the goods market — necessity priority,
  budget-capped by live deposits (A4). No household storage (households hold no goods
  inventory anywhere in the model; household hoarding is a possible future flag).
- DOCUMENTED BEHAVIORAL PRIMITIVE: "energy need is met first, price-inelastically, up to
  the budget" — a rule like B1, its inelasticity emergent from the priority ordering.
- Household energy enters consumption GDP and the price index. Metrics report BOTH headline
  (with energy) and core (without) inflation; the CB's Taylor input defaults to headline
  with a `cb_core_inflation` flag as the experiment (which index should a CB read through a
  supply shock — a classic, now askable).
- Energy poverty gauges: bill share of income per household; share of households above the
  10% threshold (the classic fuel-poverty line); rank gradient across the Phase 3 strata.

Acceptance:

- [ ] Flag off ⇒ 17.0 bit-identical; on ⇒ macro baseline undisturbed apart from documented
      composition shifts (some consumption budget is now energy).
- [ ] Energy budget share in the anchored band across the distribution; poverty gauges show
      a rank gradient (the poor spend a larger share — emergent, not seeded).
- [ ] Necessity verified: measured price elasticity of household energy demand ≪ goods
      demand elasticity (emergent from the priority rule).
- [ ] Headline vs core indices both live; burn-in discard respected downstream.

## v17.2 — The Shock Machinery & the Stagflation Experiments

- **Scenario flag**: multiplicative κ shock (sector-wide capacity), parameterized by
  magnitude, duration, and profile (step vs pulse). OFF ⇒ bit-identical. This is the
  model's first deliberate exogenous shock — it is a SCENARIO, never a default.
- **State-dependence protocol** (what storability buys): the same shock run against LOW vs
  HIGH initial coverage (paired seeds) — impact delay and peak should scale with the
  buffer. Pre-registered before running.
- **Windfall tax handle** (Policy): profit surtax on E-firms, the shock-response fiscal
  instrument.
- **The experiment matrix** (each pre-registered): shock × {Taylor gentle / Taylor off,
  deficit rule on/off, JG at capacity}. The JG HARD TEST (supply shock at capacity +
  inflation — the standing open thread) is executed here and the thread closed or updated.
  Per protocol §5 the matrix runs AFTER the composition gate, with v16 labor live (the JG
  tested is the L2-recast buffer-stock JG — strictly more valuable than the spot-era one).
- Pre-registration note for the matrix: energy-shortage output cuts
  (`y = min(a·L, energy/e_coeff)`) × v16-L1 labor hoarding ⇒ a FLATTER Okun response under
  energy shocks than under demand shocks (firms hold labor through temporary shortages).
  Expected, not a bug.
- Shock machinery, buffering acceptance, and windfall tax land inside the arc (spot labor
  is fine for them — their gates are inventory/price dynamics, not employment readings).

Acceptance:

- [ ] Shock off ⇒ bit-identical; pulse shock fully mean-reverts (no ratchet in any stock).
- [ ] Inventory buffering visible: impact delay/peak vary with initial coverage as
      pre-registered (or the refutation is documented).
- [ ] The stagflation signature exists: inflation ↑ while output ↓ — the first time the
      model produces it; decomposition attributes it to the cost channel (unit-cost series).
- [ ] JG hard test executed and written up; windfall tax conserves through fiscal.

## v17.3 — Strategic Reserve, State Ownership & Hoarding

- **SPR**: the fiscal node holds an energy stock (outside item). Policy handles: build rate
  (buys on the open market) and release rule (sells during shocks). The headline experiment
  re-runs a 17.2 shock with SPR release vs without.
- **SOE via equity** (cheap by construction — the equity grammar supports any holder):
  fiscal holds the shares of one E-firm ⇒ dividends flow to fiscal, windfalls partially
  auto-recovered. Separate flag: SOE PRICES AT COST (fixed low markup) — the market-power
  discipline experiment (does one non-markup-seeking firm cap private markups?).
- **Hoarding flag** (default OFF): firms over-target restock when expecting price rises —
  the 1970s queue amplifier, switchable, reported not tuned.

Acceptance:

- [ ] SPR build/release conserves (ledger flows + flow gauge through the fiscal stock);
      release measurably damps the shock price path vs the 17.2 reference.
- [ ] SOE dividends reach fiscal; SOE-at-cost effect on private E-markups measured and
      reported either way.
- [ ] Hoarding ON amplifies the shock (documented); OFF ⇒ bit-identical.

## v17.4 — Price Cap, Rationing & Compensation (the crisis triple)

The three ship TOGETHER because they are one mechanism in reality: a cap below the clearing
price creates excess demand (⇒ a rationing rule must answer WHO IS CUT) and E-firm losses
(⇒ a compensation transfer, or the cap is a sector-killer — which is itself a documented
scenario, not the default).

- **Price cap** (Policy, mid-run capable): E-firm asks clamped at the cap.
- **Rationing rule** plugged into the 17.0 interface, menu: proportional curtailment /
  household-priority (industry curtailed) / industry-priority. The Germany-2022 question —
  protect consumption or protect production — becomes a controlled comparison.
- **Compensation transfer**: fiscal covers the E-firm revenue gap under the cap (bounded,
  explicit); the uncompensated variant is run once, honestly, as the sector-insolvency
  scenario.
- **The arc's headline artifact**: same shock × {no intervention / SPR release / cap +
  compensation + household priority / SOE parity pricing} — the 2022 European policy menu
  as one controlled experiment, with distributional (energy poverty, strata) and macro
  (inflation, output, fiscal cost) scorecards.

Acceptance:

- [ ] Cap binding ⇒ measured excess demand; rationing conserves quantities; atomic flows.
- [ ] Uncompensated-cap run documents E-firm insolvency (the honest failure mode).
- [ ] Household-priority vs industry-priority produce distinct macro paths (protecting
      consumption vs production), decomposed and written up.
- [ ] The four-way policy comparison ships as `diagnostic_v174.png` + a results note.
- [ ] All flags off ⇒ bit-identical.

## v17.5 — Couplings (one at a time, the Phase 2 acceptance paradigm)

Each its own flag, each with frozen-reference/paired-run acceptance:

- **Housing × energy** (requires the v15.2 size-gate outcome): household energy need scales
  with dwelling size — the housing stock becomes an energy-demand structure.
- **Energy poverty → vital rates**: the Phase 2 channel grammar (pinned-signal acceptance,
  burn-in discard) applied to the fuel-poverty share — cold-home mortality has real
  empirical backing; effect sizes anchored, not tuned.
- **Efficiency investment** (gated, optional): firms lower `e_coeff` by investing —
  capital-energy substitution, giving the long-run demand elasticity that Leontief denies
  in the short run.
- **Targeted vs flat energy subsidy**: the §34 wealth-allowance reprise — flat subsidies
  should prove regressive-in-effect, targeted ones pro-poor. Pre-registered.

---

## Standing decision log (agreed in design discussion, 2026-07-12)

| Decision | Ruling |
|---|---|
| Storable? | Yes — oil-like commodity; the storable grammar (posted price, inventory, markup) is the model's native grammar; non-storable would need foreign machinery (capacity clearing/instant rationing) |
| Who stores | E-firms (own output) + downstream firms (input stock, coverage-target) + SPR (17.3); households never (no household inventory exists anywhere in the model) |
| Storage physics | No decay, no capacity limit (matches existing `f.inventory`); both are future levers |
| E-firm production | `min(a_E·L, κ·K)`, capacity-binding near baseline — short-run supply inelasticity is THE load-bearing property; without it shocks dissolve through hiring |
| Sector demographics | FROZEN (n=4) through 17.4; entry later, and only with a construction lag |
| Pricing | Native markup grammar; regulated markup is a handle (and the candidate fix if baseline markups pin at `mu_max`); merit-order never in this arc |
| Input intensity | One uniform `e_coeff` across c/k-firms in v1; sectoral differentiation later |
| Input inventory valuation | Average cost, feeding B3 unit cost |
| Shock form | Multiplicative κ scenario flag (magnitude/duration/profile); the model's first deliberate exogenous shock; hoarding a separate default-off flag |
| GDP line | Intermediate exclusion; identity check in every stage's acceptance |
| CPI | Headline includes energy; CB reads headline by default, `cb_core_inflation` is the experiment |
| Government handles | Excise in 17.0 (inert), windfall 17.2, SPR + SOE 17.3, cap/rationing/compensation triple 17.4; all in Policy, not Config |
| Rationing interface | Reserved in 17.0 (injectable buyer ordering); implemented in 17.4 |
| Labor caveat | RESOLVED by parallelization: the 17.2 experiment matrix runs once, after the composition gate, with v16 relationship wages live (protocol §5) — no disclaimed runs |
