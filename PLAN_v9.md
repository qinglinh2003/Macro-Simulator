# PLAN v9 — The Government Sector (Config/Policy split + fiscal + macroprudential control surface)

Status: **design draft for approval.** Cumulative on v8.5. New master flag `government` (off ⇒ bit-identical).

---

## 0. Two ideas that make government special

**(a) Outside money (Godley–Lavoie).** Today the economy has *only inside money* — genesis endowment +
bank loans, netting to a fixed base. The private sector as a whole *cannot net-save*; the §9 drain just
reshuffles a fixed pie. A government that runs a deficit issues **outside money** — net financial assets
the private sector can accumulate:

> **cumulative government deficit = private-sector net financial wealth (above genesis).**

**(b) Government = the only in-simulation control surface.** This project is heading toward *interactive
software where a user plays the government mid-run*. The essential distinction:

> **Government policy is adjustable DURING a run; everything else is frozen at t=0.**

So "government" is not just another mechanism layer — it is the reified set of **mutable policy levers**.
Anything a real policymaker can move in real time (taxes, spending, leverage caps, minimum wage) is a
lever; anything technological/behavioral/structural/initial is frozen Config.

---

## 1. Architecture — `Config` (frozen) vs `Policy` (live). THE FOUNDATION.

```
Config   — structural, set at t=0, immutable:  productivity, N agents, behavioral params,
           market structure, mechanism switches, initial conditions, Gibrat, founder pool …
Policy   — the government's live levers, MUTABLE each tick:  taxes, spending, leverage/credit
           caps, minimum wage.  Initialised from Config defaults.
policy_fn(economy, policy) -> None   — called once per tick BEFORE agents act; updates Policy.
           default  = the automatic-stabilizer rule (fixed rates ⇒ flows auto-countercyclical).
           future   = a scripted scenario / human player / RL agent (the interactive layer).
```

- `Economy` reads **current `Policy`** every tick — the government is the only "live" state.
- **`government=False` ⇒ `policy_fn` is a no-op, fiscal flows are 0, and the reclassified levers hold their
  Config defaults ⇒ bit-identical to v8.5.** (Threading `policy.x` in place of `cfg.x` is a mechanical,
  regression-guarded refactor.)
- This split is what makes every future government function automatically "playable": add a lever to
  `Policy`, read it in the mechanism, expose it to `policy_fn`.

---

## 2. Ontology — Treasury only (central bank is a SEPARATE future layer)

- v9 government = the **fiscal + regulatory state (Treasury)**. It taxes, spends, and sets financial-
  regulation + labor levers. It has **no monetary policy** — the interest rate and money/bond financing
  belong to a later, separate **central-bank layer (v10)**.
- **Government account** = one ledger account, `allow_negative`. Its negative balance is **government debt**
  (not "base money" — that framing waits for the CB). The private sector's matching positive balances are
  its net financial wealth.
- **v9 government debt is non-interest-bearing and financing-abstract.** The money-vs-bond split and any
  debt interest (a rate ⇒ monetary) are **deferred to the CB layer** — flagged, not hidden.

---

## 3. Accounting — A5 untouched

```
Σ_{all incl GOV} D − Σ L = M₀        (A5 verbatim; conservation code unchanged — transfers conserve)
gov_debt ≡ − D_GOV                    (government's negative balance)
Σ_{private} D − Σ L = M₀ + gov_debt   (⇒ private net wealth grows with the cumulative deficit)
```
Spend = `transfer(GOV → agent)`; tax = `transfer(agent → GOV)`. **No new primitive, no new conservation
law.** `gov_debt`, `gov_deficit`, `gov_debt_to_gdp` are derived metrics.

*Simplification (explicit):* single-bank model collapses reserves-vs-deposits; the CB layer will make base
money and bonds explicit.

---

## 4. The Policy levers (the v9 control panel)

Nine live levers, in four groups. Each default is **externally anchored, never tuned to a §4 target (§0-ii)**.

### 4a. Fiscal — spending
- **`gov_consumption_share` g ≈ 0.20** — the government demands `G_c = g · potential_output`
  (`potential = labour_supply · a`) real goods in the goods market and buys them (`GOV → firm`). Steady real
  demand floor (acyclical ⇒ stabilizing). Anchor: real G/GDP ≈ 20%. *(new)*
- **`benefit_replacement` b ≈ 0.4** — each involuntarily-unemployed household gets `b · wage_ref` →
  `income_realized` (feeds B1). The income floor that breaks the v8.5 insolvency→demand loop. Anchor: OECD
  replacement rate. *(new)*

### 4b. Fiscal — revenue (with progressivity)
- **`tax_profit_rate` τ_π ≈ 0.25** — on realised positive profit, *before* dividends (`f → GOV`); dividends
  then pay from after-tax profit. Recycles the §9 drain back out of firms. Anchor: corporate-tax order. *(new)*
- **`tax_income_rate` τ_y ≈ 0.20 + `income_allowance` a_x ≈ (fraction of mean income)** — **progressive**
  income tax: `tax_h = τ_y · max(0, income_h − a_x·mean_income)` on labour+dividend income (benefits
  untaxed). The allowance makes the *average* rate rise with income (a_x=0 ⇒ flat). Progressivity is the
  direct redistribution lever. Anchors: real marginal rate + personal-allowance order. **§0-ii is tightest
  here — we do NOT tune a_x to hit a T8 value.** *(new)*
- **`tax_consumption_rate` τ_c ≈ 0.15** — a VAT/sales tax: in the goods market a household paying `p` for a
  unit also pays `τ_c·p` to GOV. **Regressive** (consumption is a larger share of poor budgets) — the
  counterweight to progressive income/wealth tax, completing the four-base toolkit. Anchor: real VAT. *(new)*
- **`tax_wealth_rate` τ_w ≈ 0.01** — a flat tax on household **net worth** (deposits + equity − debt) per
  tick, `τ_w · max(0, NW_h) → GOV`. Taxes the STOCK, not the flow — the **most direct T8 lever** (and thus
  the strongest H4 tension). Anchor: real net-wealth-tax order (~1%/yr). §0-ii: never tuned to a T8 value. *(new)*

### 4c. Macroprudential — reclassified from existing Config dials (NOT new mechanisms)
These four already exist as "FREE behavioral dials"; they are really **financial-regulation levers**, so
they move into `Policy` (default values unchanged ⇒ bit-identical when the government doesn't touch them):
- **`margin_ltv` (0.5)** — household margin loan-to-value cap.
- **`margin_max` (2.0)** — household equity-leverage ceiling.
- **`kappa` (3.0)** — firm credit leverage multiple `L^max = κ·NW`.
- **`hh_credit_limit` (2.0)** — household debt-to-income (DTI) cap.
Making these live enables **macroprudential policy** — e.g. countercyclical tightening (E32) is then just a
`policy_fn` that lowers `margin_ltv`/`kappa` when leverage/prices run hot. (The *rule* is future; v9 just
makes the levers live + settable.)

### 4d. Labor
- **`min_wage` (0, off)** — a floor: posted/paid wages `≥ min_wage`. Interacts with employment + household
  income. Anchor: real minimum-to-median-wage ratio when on. *(new)*

**Emergent, not levers:** `gov_deficit`, `gov_debt`, `gov_debt_to_gdp`.

---

## 5. Structural completeness (not a lever) — household bankruptcy resolution

Today an insolvent household (net worth ≤ 0, our 173/2000 finding) is stuck in an **unphysical limbo**:
margin calls only repay from cash ([economy.py:864]), so with no cash the debt hangs forever and the
household stays demand-dead. Real bankruptcy discharges the debt (fresh start). Add: a deeply/persistently
underwater household has its margin debt **written off** (bank absorbs, exactly like firm default via the
existing `write_off` primitive); its net worth resets to ~0 and consumption recovers to income-based. This
is the **exit valve** for the §27 insolvency→demand-destruction loop and a *realism fix*, independent of the
fiscal state. (A `bankrupt_persist`-style threshold governs it — a legal-regime parameter, kept in Config.)

---

## 6. Tick placement
- **Goods market:** government submits real demand `G_c`, buys, pays firms.
- **Settlement (Phase 4):** (1) profit realised → (2) profit tax `f→GOV` → (3) dividends on after-tax profit
  (pro-rata) → (4) income tax `h→GOV` (progressive) → (5) unemployment benefit `GOV→unemployed` into
  `income_realized` → (6) household bankruptcy resolution → (7) existing capital, etc.
- **Pre-tick:** `policy_fn` sets the live levers (default: constant anchored rates).

No behavioural axiom changes; the government adds transfers, one goods-market buyer, and a resolution step.

---

## 7. §0 discipline
- **§0-ii:** every default (`g, b, τ_π, τ_y, a_x, min_wage`, and the four macroprudential caps) anchored to
  real rates. **Pre-register outcomes; never tune to hit u≈5% or any T-value.** Progressivity `a_x` is the
  most tempting to tune — hardest discipline, most important to hold.
- **§0-iv parsimony:** the honest cost of the chosen scope is **~7 new fiscal/labor dials + 4 reclassified
  caps**. Justified by the interactive-control-surface goal; deficit/debt stay emergent; zero new
  primitives/axioms.
- **Cumulative:** `government=False` ⇒ bit-identical to v8.5. `Config.v9()` = v8.5 + `government=True`.

---

## 8. Pre-registered hypotheses

| # | Hypothesis | Expected | Falsifier |
|---|---|---|---|
| H1 | Income floor + G_c lower **mean u** toward realistic | u ≪ 0.18 | u unchanged |
| H2 | **Deep-recession freq** (u>0.5) collapses | 21%/5% → low | no change |
| H3 | **T3** holds or improves (stabilizer smooths cycle) | ≥ pass | T3 breaks |
| H4 | **T8 tail** may FLATTEN under progressive tax + transfers | weaker tail — the honest cost | — |
| H5 | **gov debt/GDP** stabilises (self-limiting) | bounded | runaway debt |
| H6 | Household **bankruptcy** revives demand-dead households | fewer chronic-insolvent hh | no effect |

**H4 tension (pre-registered):** redistribution can undo T8. Real economies keep fat wealth tails *despite*
progressive tax because the floor is on income/consumption, not top-end accumulation — so modest anchored
`b, a_x` may leave T8 intact. **We measure and report either way; we never shrink a lever to save T8.**
Deeper open question (§10): our households are *immortal* → no dynastic wealth → single-generation T8 may be
inherently capped; the real fix could be a **household lifecycle + bequest** layer, not any tax.

---

## 9. Metrics to add
`gov_balance`, `gov_debt`, `gov_deficit`, `gov_debt_to_gdp`, `tax_profit`, `tax_income`, `benefit_paid`,
`gov_consumption`, `gov_spending_share_of_gdp`, `hh_bankruptcies`, `benefit_share_of_income`,
`income_tax_progressivity` (effective-rate slope). A5 drift gate unchanged.

---

## 10. Deferred to future layers (with reasons)
- **v10 Central Bank (separate, per your call):** policy interest rate `r_interest` (currently a frozen
  Config const → becomes a CB lever), base-money vs **bonds** financing of the deficit, **bond interest**
  (A6 — a regressive income channel + a risk-free asset that reshapes the equity/margin portfolio choice),
  lender-of-last-resort, bank capital requirement (`bank_capital_frac` promoted).
- **Household lifecycle + bequest (a demographic layer, ~firm-demographics-sized):** enables **inheritance
  tax (B14)** AND, more importantly, **dynastic wealth** — a candidate *structural* answer to the persistent
  T8 tail (immortal households can't build multi-generational fortunes). Flagged as a first-class future
  target, not a tax.
- **Others:** consumption/wealth tax, price controls (`mu_max` as a ceiling), entry/competition policy
  (antitrust → T6), bailouts, discretionary fiscal timing.

---

## 11. Build order
1. **Architecture:** introduce `Policy` (mutable) holding the 9 levers, initialised from Config; add
   `policy_fn` hook (default no-op when `government=False`, automatic-stabilizer rule when on). Thread
   `policy.{margin_ltv,margin_max,kappa,hh_credit_limit}` in place of the `cfg.*` reads (regression-guarded).
2. **Ledger:** add `GOV` account (`allow_negative`); confirm A5 gate passes with it included.
3. **Config:** `government`, `tax_profit_rate=0.25`, `tax_income_rate=0.20`, `income_allowance=…`,
   `benefit_replacement=0.4`, `gov_consumption_share=0.20`, `min_wage=0`; `Config.v9()`; validations.
4. **economy.py:** goods-market government buyer; Phase-4 profit tax → income tax (progressive) → benefit →
   household bankruptcy resolution; min-wage floor in the wage step.
5. **metrics.py:** the §9 block.
6. **tests/test_v9_government.py:** bit-identical off; A5 + new-metric conservation; `gov_deficit =
   (τ_π+τ_y) − (b+G_c)` and `−gov_balance` = cumulative deficit; benefit reaches the unemployed;
   progressive tax hits high earners harder; a min-wage floor binds; a bankruptcy discharges & revives.
7. **validate_parallel.py v9 0,1,2,3,4** + macro-levels vs v8.5 + a v9 diagnostic dashboard.
8. **DESIGNDOC §28.**
