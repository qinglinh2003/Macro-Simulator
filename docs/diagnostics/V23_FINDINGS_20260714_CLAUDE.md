# V23 Diagnostic Session 2 — Root Causes Found and Fixed (2026-07-14)

Continues [`V23_FINDINGS_20260714.md`](./V23_FINDINGS_20260714.md). That document listed
1 critical, 10 high and 1 medium finding and scoped three P0s. This session found the ROOT
CAUSE underneath most of them, fixed three defects, and re-ran the suite to verify.

| Item | State |
|---|---|
| Working branch | `fix/v23-release-blockers` |
| Fix commit | `1fb9c2a` |
| Final evidence | `artifacts/diagnostics/claude-final-v3` (2191 ticks, 5 baselines, 10 workers) |
| Pre-fix comparison | `artifacts/diagnostics/claude-audit-01` (same suite, unfixed source) |
| New tests | 14 (capital clock 6, dust jobs 3, second contract 5) |
| Suite | 930 passed / 2 failed before this session's test fixes; see §5 |

---

## 1. The root cause: the capital clock

`plan_investment` computes `K* = v * demand_expected`. On the daily calendar
`demand_expected` is a **per-tick** flow, but `v` is the textbook capital-output ratio
measured against **annual** output. v13's daily migration converted `lambda_I`, `delta_K`,
`r_interest`, `amort`, `eta` and the inflation target — **and missed `v`**. The desired
capital stock was therefore `ticks_per_year` too small.

Measured: **K / annual GDP = 0.004** against a configured 2.5.

This is not a cosmetic ratio. In Cobb-Douglas, capital earns the share `alpha` **by
construction, independent of the units of K** — but the cost of REPLACING it is
`delta * K`, which was 365x too small. **Capital earned 30% of output while costing almost
nothing to maintain.** Every capital-priced quantity was inert with it: the
capital-service price term, collateral value, and the P&L depreciation charge were all
365x too small, which is why the capital-service pricing patch could not bite.

### The fix (`capital_annual_clock`, default off => every preset bit-identical)

A JOINT migration, because patching `v` alone would demand a 365x capital stock from a
genesis stock sized for the old rule:

```
v       -> v * S            desired capital now tracks ANNUAL output
K_firm0 -> K_firm0 * S      genesis capital at the new scale
A       -> A * S**(-alpha)  Cobb-Douglas output EXACTLY invariant: A' K'^a == A K^a
```

Genesis production is bit-preserved (`A*K^alpha = 2.456456` on both sides), so genesis
output, prices, wages and unit costs do not move — while the capital STOCK, its
depreciation flow, its service cost and its collateral value all become economically real.

`a_K` must be recalibrated with it. It was **never calibrated**: under the broken clock the
K sector was economically inert, so its productivity never bound. At `a_K=1.0` the
now-real replacement flow consumes ~1/3 of the labour force and drives a cost-push spiral
(measured: -15%/yr growth, CPI 4.1x). A capital good and a consumption good carry the same
genesis price, so they must embody comparable labour per unit: `a_K = 2.4` tracks measured
C-sector labour productivity. A validator rejects the uncalibrated combination.

### What it resolved (2191-tick causal matrix, 5 baselines)

| Finding | Before | After |
|---|---|---|
| `welfare.deprivation_domain_boundary` | **CRITICAL**, seeds 0/1/3 | resolved |
| `energy.structural_rationing` | HIGH, all 5 baselines | resolved |
| `production.plan_realization_failure` | HIGH, all 5 baselines | resolved |
| `monetary.easing_blocked_by_zlb` | HIGH | resolved |
| K / annual GDP | 0.004 | **1.6** |
| investment / GDP | 0.2% | **10%** |

The ZLB result matters methodologically: with the structural deflation gone the policy rate
leaves the floor, so **the monetary experiments become identifiable again**. The handoff doc
correctly warned not to read the old ZLB arm as "easing has no channel" — it was unidentified.

---

## 2. The chain this closes (and what v17/v19 got wrong)

**Capital was a free input, and the pricing rule manufactured the deflation.**

`unit_cost` = unit LABOUR cost (+ energy), and B3 posts `p = (1 + markup) * unit_cost`. As
the economy accumulates capital and substitutes it for labour, labour input per unit falls,
so unit cost falls, so posted prices fall — while the capital that REPLACED that labour was
never charged, because the clock bug had made it economically nil. Real economies do not
deflate from capital deepening precisely because the capital has to be paid for.

This explains, in one stroke:
- the persistent -4..-8%/yr deflation in every v17/v19 portrait;
- **why the v19 exogenous TFP drift could not stop it** (drift lowers unit LABOUR cost, so
  it deflates MORE — exactly what the v19 audit measured);
- and it **corrects the v19 headline**: the audit concluded "the active Taylor CB is the
  deflation engine". The CB was reacting to a deflation the COST SIDE manufactured. It was
  an amplifier, not the cause.

---

## 3. Second finding: dust jobs (a crash)

Every fractional allocation site tested hours against `EPS` (~1e-9) — a float-dust
threshold — while the downstream pay guard ALSO tested `rate * hours` against `EPS`. The two
were mathematically inconsistent: a job whose hours sat just above EPS produced pay BELOW
EPS for any wage under 1.0, and the "non-positive pay" assertion killed the run.

Observed: `baseline_s1` died at 2191 ticks with `pay = 9.2e-10`.

`MIN_JOB_HOURS = 1e-6` is an economic floor rather than a dust one: still economically nil
(it can never displace a genuine part-time match) but far enough above the dust that
`rate * hours` cannot collapse through EPS for any plausible wage.

---

## 4. Third finding: the single-Job intensive margin (the P0 the handoff scoped)

Greedy per-firm allocation leaves exactly ONE part-time MARGINAL worker at each firm. With
one Job per person those residual hours were **unsellable**: 13-24 FTE idle while firms
posted 180-235 vacancies, the residue draining into the job guarantee.

The macro consequence was not small. Once the capital clock was fixed and labour demand rose,
the single-Job margin could not match it:

```
labour cannot match -> production realization 0.61-0.81 -> inventories 24-71% BELOW target
   -> the B3 markup ratchets 0.28 -> 0.62 -> RUNAWAY INFLATION
```

Measured on the fixed clock (2191t, 3 seeds): fractional mode ran **117% ± 173** inflation
against **6.8% ± 14** for whole-person jobs. The intensive margin, as implemented, was the
direct cause of the inflation.

### The fix (`labor_second_job`, default off)

A person may hold ONE additional contract at a DIFFERENT firm, capped so their total hours
never exceed 1.0 FTE. Dual job-holding recovers essentially all of the stranded margin.

**Two accounting semantics are the sharp edge, and the hard gates caught both:**
- an extra contract is an **INTENSIVE-margin** event: FTE moves, HEADS do not. Booking it as
  a hire broke the labour head-flow identity (`heads=249 but prev + net flows = 250`).
- a relationship wage belongs to a **CONTRACT**, not a person. The person-scoped `wage_of`
  quoted the PRIMARY job's locked wage to whichever firm asked, so a second employer budgeted
  its own posted wage and paid the other firm's — overrunning its live cash and tripping the
  cash guard.

Every firm-scoped read now resolves the contract at that firm (`job_at`); person-scoped reads
use `total_hours`.

**Same-seed twin (the handoff doc's required evidence), 3 seeds, 1460t:**

| | second_job off | second_job on |
|---|---|---|
| underemployment hours | 13.7 FTE | **5.1 FTE** |
| labour fill | 73.8% | **91.0%** |
| markup | 0.55 | 0.50 |
| inflation | +5.6% | **-0.4%** |

It resolved `labor.fractional_single_job_fragmentation`, `macro.implausible_per_capita_growth`
and `macro.persistent_price_instability`.

---

## 5. Final state (2191 ticks, all three fixes, `claude-final-v3`)

Resolved across the session: **1 CRITICAL + 6 HIGH.**

Still open:

| Finding | Severity | Note |
|---|---|---|
| `welfare.deprivation_domain_boundary` | CRITICAL | **Character completely changed.** Destitution peak fell from **14.4% -> 0.2%** and the banking sector no longer collapses (7-8 banks alive, RWA utilisation 0.20, vs "all commercial banks are gone"). 0.2% of ~130 households is LESS THAN ONE household: the sticky boundary now latches on an individual outcome, not a systemic crisis. Diagnose that household's resource shortfall; the real signal alongside it is a **12% fall in the real wage** (0.914 -> 0.803) as nominal wages lag 5-17% inflation. |
| `banking.rwa_capital_breach` | HIGH (new) | Sector capital is ample (aggregate RWA utilisation **0.20**) but at least one bank sits at **1.08** of its own envelope, 86% of the tail. **See §5.1: the obvious hypothesis was tested and REFUTED — the breach is a benign concentration/stock effect, not a credit-allocation failure.** |
| `monetary.easing_blocked_by_zlb` | HIGH | Returned once inflation fell to ~0. Now a genuine nominal-anchor question rather than an artefact of a manufactured deflation. |
| `banking.deposit_funding_cost_missing` | HIGH | known scope limit (unchanged) |
| `credit.collateral_recovery_missing` | HIGH | known scope limit (unchanged) |
| `finance.loan_contract_vintages_missing` | HIGH | known scope limit (unchanged) |
| `housing.typed_household_debt_missing` | HIGH | known scope limit (unchanged) |
| `labor.large_job_guarantee_buffer` | HIGH | unchanged |
| `accounting.inventory_cogs_matching_missing` | MEDIUM | known scope limit (unchanged) |
| `credit.leverage_cap_nonbinding` | MEDIUM | new; consistent with the ample sector capital above |

### 5.1 The lock-in / RWA hypothesis: TESTED AND REFUTED

The natural reading of the RWA breach was: `bank_relationship_lock_in` forces a borrower with
existing debt back to its own lender, so if that lender is capital-breached the borrower is
starved **even though the sector has 80% headroom** — credit failing to reach where capital is.
It would have made typed loan contracts the keystone that unblocks everything.

Same-seed twin, lock-in on vs off (3 seeds, 1460t):

| lock_in | sector RWA util | total credit | destitute | real GDP | production realization | inflation |
|---|---|---|---|---|---|---|
| **on** | 0.210 | **17961** | 0.000 | 479.3 | 0.744 | 2.77% |
| off | 0.154 | **11779** | 0.000 | 486.2 | 0.758 | 0.83% |

**Refuted, and in the opposite direction.** Turning lock-in OFF *reduces* credit by 34%, and the
real economy is essentially unchanged (GDP 479 vs 486, destitution zero in both). Lock-in does
not starve borrowers; it CONCENTRATES lending at a few relationship banks — which is what pushes
an individual bank over its own envelope while the sector keeps 80% headroom. The breach is a
**grandfathered stock/concentration state with no measured macro harm**, exactly as the suite's
own recommendation suspected ("separate grandfathered stock breaches from new-credit decisions").

Side finding worth keeping: **relationship lending is expansionary** — lock-in raises total credit
by 52% and inflation from 0.8% to 2.8%. That is a behavioural result, not a defect.

### Test state

- The 3 fixes ship 14 new tests, all green.
- `tests/test_labor_fractional_hours.py` was reading `lm.jobs[pid]` for K-firm rosters. With a
  second contract that returns the WRONG contract (the person's primary may be at a C-firm), so
  it now resolves per firm via `job_at`. Its `assert partial_k_jobs` guard also asserted an
  INCIDENTAL property (that some K worker is part-time), which a calibrated `a_K` need not
  produce; the reconciliation identities it exists to check are now asserted unconditionally.
  6/6 green.
- `tests/test_sector_switching.py::test_switching_closes_the_gap_and_conserves` **fails, and it
  is NOT from this session's fixes.** Its world uses `labor_matching="spot"` and leaves
  `capital_annual_clock`/`labor_second_job` off, so none of the three fixes is on its code path
  (verified: `v/K_firm0/A` untouched at 2.5/20.0/1.0). The test PASSES on committed HEAD
  (264d1d2) with the whole uncommitted patch set stashed — and `macro_sim/systems/switching.py`
  is in that uncommitted set. **Attribution: the inherited patch set, not the capital clock.**

  Note on isolation: you CANNOT separate the two by stashing. `1fb9c2a` edited files the
  inherited patch set had already modified (`config/model.py`, `labor/persistent.py`,
  `labor/accounting.py`, `economy.py`), so the commit necessarily baked in their state of those
  files. Stashing `macro_sim/` then reverts the OTHER inherited files and leaves an inconsistent
  tree that fails at import. The attribution above rests on the code-path argument plus the
  clean-HEAD pass, not on a stash experiment.

---

## 6. Methodology notes (paid for the hard way)

- The suite's evidence gates are real. Editing source while a matrix runs invalidated one run
  (`validity.source_changed_during_run`) and crashed another in `inspect.findsource`. **Freeze
  the source for the whole run.**
- The labour head-flow identity and the firm cash guard each caught a genuine semantic error in
  the second-contract implementation within one tick. Do not weaken them.
- `git stash push macro_sim/ tests/` stashes the ENTIRE uncommitted patch set, not just your
  own work. Commit before using it as an isolation tool.

## 7. Recommended next steps

1. ~~Prove or refute the lock-in/RWA hypothesis~~ — **DONE, refuted (§5.1).** The RWA breach is a
   benign concentration/stock state with no measured macro harm. Do not spend an arc on it, and
   do NOT justify typed loan contracts with it.
2. **Diagnose the single destitute household** in `baseline_s1` from tick 1717. This is the last
   CRITICAL, and its character has completely changed: 0.2% destitution (< 1 household) with a
   healthy banking sector, against 14.4% and a total bank wipeout before the fixes. Look at the
   **12% real-wage decline** (0.914 -> 0.803) that accompanies it — nominal wages are lagging
   5-17% inflation, which is the plausible mechanism.
3. **The nominal anchor** (`monetary.easing_blocked_by_zlb`) is now a GENUINE question rather
   than an artefact. With the cost side fixed, the deflation is no longer manufactured, so the
   v19 nominal-anchor audit is worth re-running on this foundation — its old headline ("the CB
   is the deflation engine") was measured on the broken clock and is superseded.
4. The remaining known scope limits (deposit funding cost, collateral recovery, typed loan
   contracts, inventory COGS) stand on their own merits as accounting completeness, not as
   blockers surfaced by these findings.
