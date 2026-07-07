# Implementation plan — v2 (investment + capital)

Implements DESIGNDOC §10 (v0.9). Companion to the axiom doc; this is the *engineering*
plan, not part of the axiom set. Scope inherits the kernel except where §10 extends it.

Status: **ready to build, pending sign-off.** Architecture locked to Option A.

---

## 0. Architecture decision — A (generalize in place), locked

Single codebase, sector-aware. Add three orthogonal attributes to `Firm` and let v1 be a
genuine special case:

| firm | `tech` | `sells` | `invests` | capital |
|---|---|---|---|---|
| v1 kernel firm | `linear` | `consumption` | no | — |
| v2 C-firm | `cobb_douglas` | `consumption` | yes | yes |
| v2 K-firm | `linear` | `capital` | no | — |

Consequences:
- Matches §10.2 "shared behavioral core, no second codebase."
- **v1 becomes a special case ⇒ the three existing test suites become regression guards.**
  The v1 code path must stay bit-identical: `linear` dispatch returns exactly `a·N`, and
  with no K-firms Phase 3.5 / capital commit are no-ops.
- Rejected Option B (parallel `EconomyV2`): two tick loops drift — the engineering face of
  the §0 parsimony discipline.

---

## 1. Review corrections folded in (the five deltas from the raw plan)

These five points materially affect results or the credibility of the v2 conclusion, so they
are pinned here, not left in conversation.

### 1.1 Dividend/investment cash conflict — surface it, don't let phase order hide it 🟡

Investment (Phase 3.5) and dividends (Phase 4) can compete for the same post-sales cash
(worked example: `D₋₁=0, revenue=100, wagebill=50 ⇒ profit=50`; invest up to 50 leaves 0,
yet dividend `ρ·50` is still owed). Resolution:

1. **Dividends get an A4 cash cap:** transfer `min(owed, live Dₑ)`; never overdraw.
2. **Investment-first precedence is a conscious choice, documented, not accidental.** §10.5
   deliberately orders Phase 3.5 before Phase 4 (so investment can draw on this tick's sales
   revenue), and dividends are the residual claim (economically standard). We *keep* that
   ordering but state plainly that it grants investment first claim on cash.
3. **Record when it binds:** metric `dividend_cash_capped` (count of firm-ticks where the cap
   bit) + `dividend_shortfall` (money not paid). If ≈0 throughout, the precedence never
   matters; if it bites often, we know the ordering is shaping results and revisit.
4. Alternative if true no-priority is ever wanted: resolve investment+dividend against the
   same opening cash by pro-rata rationing. Not adopted (fights §10.5 ordering, adds
   complexity); documented as the fallback.

**Discipline:** the conflict resolution is explicit and accounted for; phase order must not
silently set priority (§8.1 "don't smuggle in assumptions").

### 1.2 K-sector expected-demand cold start — fill the §10.6 vacuum 🟡 transient

C-firms extrapolate past sales; K-firms have **no history** at t=0 (their demand *is*
C-sector investment orders). Seeding K expected demand at 0 ⇒ K-firms don't produce/hire ⇒
**B_K dead on tick 1 ⇒ an artificial initial depression** that confounds "mechanism fails"
with "cold start not wired." Resolution, centralized in `create_k_firm`:

- Seed each K-firm's expected capital-good demand from a rough aggregate steady-state
  investment estimate spread across K-firms:
  `d^e_{K,0} ≈ ( Σ_{C} [ λ_I (v·y^e_{C,0} − K_0) + δ_K K_0 ] ) / n_firms_k`.
- Seed `sales_prev` to the same value so the first B2 update is a neutral no-op (as in v1).
- Mark **transient**; add a check that it washes out (results insensitive to the seed value).

### 1.3 Small-N false alarms — big N for the acceptance/invariance runs

Repeats the v1 lesson. `B_K` (the cure channel) is determined by the K-firms; with only 2 of
them, seed noise in `B_K` could be misread as "drain reversal not robust." Resolution:

- Daily/dev runs may be small; **the §10.8 drain-reversal acceptance and seed-invariance runs
  use large N, especially `n_firms_k ≥ 10`.**
- Defaults raised to `n_firms_c = 15, n_firms_k = 10`; an `acceptance_variant` goes larger.

### 1.4 Quantitative drain-reversal acceptance — use the identity, not a vibe

"hh_money tail not ≈ 0" is too weak (can't tell "cured" from "dying slowly"). The §9 drain
identity generalizes exactly and becomes the acceptance tool. Household money moves only by
all wages + all dividends − consumption (households don't buy capital). In the boom phase
(both sectors' profits ≥ 0) this collapses to

```
ΔH_t = R_K,t − (1−ρ)(Π_C,t + Π_K,t)
     = investment spending − economy-wide retained earnings
```

(derivation in §4 below; `R_K` = money C-firms pay K-firms = aggregate investment expenditure).
Compared to v1's `ΔH_t = −(1−ρ)Π_t` (pure drain), the new **positive** term `R_K` is the cure.
Therefore:

> **Drain reversal ⇔ investment spending `R_K` exceeds aggregate retained earnings
> `(1−ρ)Π_total`.**

Acceptance test does two things:
- **Accounting (machine precision, every tick):** verify the unconditional identity
  `ΔH_t = B_t + V_t − R_C,t` and, on boom ticks, `ΔH_t = R_K,t − (1−ρ)Π_total,t`. Doubles as a
  ledger-leak check.
- **Economics (quantitative):** assert the boom-phase net drain `(1−ρ)Π_total − R_K` is
  materially smaller than the v1 counterfactual `(1−ρ)Π` (ideally crossing ≤ 0), and that the
  reversal coincides with `R_K` overtaking retained earnings.

### 1.5 Cobb–Douglas unit-cost vintage — write it down, don't default 🟡

`uc_C = w·N^d/y*` is self-referential (pricing uses planned quantities). Fix the vintages
explicitly (§8.1):
- `y*` = the production target (from the t−1 expectation, computed earlier in Phase 1).
- `N^d` = **notional** labor requirement, inverting the production function at `K_{t-1}`,
  **before** the cash cap (so `uc` reflects planned average cost, not rationed hiring).
- `w` = this tick's wage (wage still planned **before** price, per the v1 fix).
Not circular: `y*` and `N^d` are both fixed before pricing.

---

## 2. Module-by-module changes

| module | change |
|---|---|
| `config.py` | Add v2 params: `A, alpha, a_K, v, lambda_I, delta_K, K_firm0, n_firms_c, n_firms_k`, K-firm initial deposits/postings. `capital_enabled` derived from `n_firms_k>0`. `acceptance_variant()` with large N. v1 `Config` unchanged. |
| `agents.py` | `Firm` gains `tech, sells, invests` + capital fields `K, K_prev, k_star_prev, investment, investment_target` + CD params `A, alpha` + B5 params `v, lambda_I, delta_K`. Factories `create_c_firm`, `create_k_firm` (with the §1.2 cold-start seeding); keep `create` (v1). |
| `behavior.py` | Dispatch fns `produce(firm, N)`, `labor_demand_notional(firm, y*)`, `unit_cost(firm, y*, N_d)`; `plan_price` uses `unit_cost` (linear result identical to v1). **New `plan_investment(firm)`** (B5). B1/B2/B4 untouched. Guards: `K>0`, `α∈(0,1)`, `A>0`, `y*=0⇒N^d=0`. |
| `interfaces.py` | Extract the goods-market core into reusable `execute_market(orders, offers, protocol, rng, ledger)`; used by both consumption (Phase 3) and capital (Phase 3.5). `Goods` now length 2. |
| `economy.py` | Sector-aware. Build households + C-firms + K-firms; endow (C-firms `K(0)>0`). Phase 1 adds investment planning + sector labor-demand inversion. Phase 2 single labor pool, `produce` dispatch. Phase 3 sellers = C-firms. **Phase 3.5 NEW** capital market (C buy K) via `execute_market` → sets `firm.investment`. Phase 4 both sectors + **capital commit** `K=(1−δ_K)K+I`, dividends A4-capped (§1.1). Phase 5 conservation over all deposit accounts (K never in ledger). |
| `metrics.py` | Add: per-sector money (hh / C / K), total investment `I_t` (=`R_K`), aggregate capital `ΣK_f`, **`B_K` (capital-sector wages — the cure channel)**, `V_K`, per-sector retained, output-ceiling proxy, sector-split output/employment/prices, `dividend_cash_capped`, `dividend_shortfall`, and the drain-identity terms (`R_K`, `(1−ρ)Π_total`, measured `ΔH`). |
| `diagnostics.py` | v2 dashboard panels: three-sector money, investment & capital stock, **`B_K` over time**, C vs K deposits, output vs `ΣK` ceiling, and a **drain-decomposition panel** (`R_K` vs `(1−ρ)Π_total`, and net `ΔH`). |
| `runlog.py` | Works as-is (asdict config + records); add v2 summary keys. |
| `run.py` | v2 run entry + a `(v, λ_I)` sweep + the quantitative drain-reversal readout (§1.4). |

---

## 3. Key subtleties & guards (must be explicit, never silent)

1. **Predetermined capital:** production uses `K_{t-1}`; capital committed in Phase 4; new
   capital productive from `t+1`. Persist `K_prev`.
2. **Phase 3.5 after Phase 3:** investment finances out of the **deposit stock** (incl. this
   tick's revenue), **not** a P&L expense. Profit = revenue − wagebill (unchanged); investment
   is an asset swap deposits→capital. ⇒ the dividend/investment cash conflict of §1.1.
3. **Cobb–Douglas guards:** `K(0)>0` (else output 0), `α∈(0,1)`, `A>0`; inversion
   `N^d=(y*/(A·K^α))^{1/(1−α)}`, `y*=0⇒N^d=0`; surface `K=0`, don't silently zero.
4. **Conservation unchanged mechanically:** K is never in the ledger, so the all-accounts sum
   auto-excludes it. Add an explicit test that growing K leaves total money invariant.
5. **Accelerator instability expected:** first runs may oscillate/diverge before
   `(v, λ_I, δ_K)` are tuned — calibration, not plumbing (§10.8). `λ_I` damps.
6. **Unit-cost vintage** fixed per §1.5.
7. **K-sector cold start** seeded per §1.2.

---

## 4. The v2 drain identity (derivation — mechanism doc + acceptance tool)

Inter-sector flows touching households: wages `B = B_C + B_K` (firm→hh), dividends
`V = V_C + V_K` (firm→hh), consumption `E = R_C` (hh→firm; households don't buy capital). The
C↔K investment transfer is firm-to-firm and does not touch `H` directly. Hence the
**unconditional** identity (v2 analog of §9's (1)):

```
ΔH_t = B_t + V_t − R_C,t                     [holds every tick, machine precision]
```

Boom phase (Π_C, Π_K ≥ 0, so V = ρΠ_C + ρΠ_K), with Π_C = R_C − B_C, Π_K = R_K − B_K:

```
ΔH = B_C + B_K + ρΠ_C + ρΠ_K − R_C
   = B_K + ρΠ_K − (1−ρ)Π_C        [substitute R_C = Π_C + B_C, cancel B_C]
   = R_K − (1−ρ)(Π_C + Π_K)       [since B_K + ρΠ_K = R_K − (1−ρ)Π_K, as Π_K = R_K − B_K]
```

i.e. **household money change = investment spending − aggregate retained earnings.** The
reflux to households is exactly `B_K + V_K` (capital-sector wages + K-dividends); the residual
`(1−ρ)Π_K` is §10.3's "smaller secondary drain." v1 is the special case `R_K ≡ 0`, recovering
`ΔH = −(1−ρ)Π`. This is the quantitative acceptance instrument of §1.4.

---

## 5. Build order (each layer green before the next)

1. `config` + `agents` (sector fields, factories, cold-start seeding) — data only.
2. `behavior` dispatch (`produce`/`labor_demand`/`unit_cost`) + `plan_investment` →
   **unit tests: CD math + inversion round-trip** (`labor_demand(produce(N)) == N`).
3. Extract `execute_market` → **run the three v1 suites; confirm consumption market is a
   zero-diff regression.**
4. `economy`: Phase 3.5 + capital commit + A4-capped dividends + three-sector conservation.
5. `metrics` + `diagnostics` v2 panels (incl. drain decomposition).
6. `run` v2; verify §10.8 acceptance + seed-invariance (large N).

---

## 6. Acceptance (§10.8) + tests

- **Regression:** the three v1 suites stay green (v1 path bit-identical).
- **Conservation:** three-sector deposit sum = M every tick; `test_conservation_v2`.
- **Capital excluded:** growing K doesn't change total money; `test_capital_excluded_from_money`.
- **Capital law of motion:** `K_t = (1−δ_K)K_{t-1} + I_t` per firm per tick; `test_capital_law`.
- **Drain identity (§1.4):** unconditional `ΔH = B+V−R_C` and boom `ΔH = R_K−(1−ρ)Π_total` to
  machine precision; net drain materially below the v1 counterfactual; `test_drain_reversal`.
- **Alive, not trapped:** bounded active state; output ceiling moves with `ΣK_f`.
- **Seed-invariance (large N):** `test_seed_invariance_v2`.

Endogenous multiplier–accelerator cycles are a welcome bonus, **not** a pass/fail bar.

---

## 7. Parameter starting points (all tentative; retune after first run)

`v≈2.5, λ_I≈0.25, δ_K≈0.05, α≈0.3, A=1 (normalize), a_K≈1 (the A:a_K ratio sets relative
sector prices — meaningful, verify), K_firm0≈20, n_firms_c=15, n_firms_k=10`.

Free behavioral dials go 5 → 7 (`v, λ_I`), justified per §10.7 (they parametrize the cure for
the proved §9 drain, not a fit). `δ_K, α` anchored; `A, a_K, N` scale/transient.

---

## 8. Open items (confirm before or during build)

- §1.1: keep documented investment-first precedence + metric (recommended) vs true pro-rata?
- §7: parameter starting points, especially the `A:a_K` ratio and `K_firm0`.
