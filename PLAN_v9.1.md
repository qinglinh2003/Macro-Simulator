# PLAN v9.1 — Government INVESTMENT → public capital → productivity (the supply side)

Status: **design draft for approval.** Cumulative on v9. New levers default-off ⇒ bit-identical to v9.

---

## 0. Why this is THE fix (from the §28.8 diagnosis)

The thorough diagnosis (§28.8) found v9 net-**negative**: real output/consumption −15%, u +68%, inflation
6×. Root cause: **a persistent deficit in a STATIONARY economy has no productive outlet, so it becomes
inflation + turbulence instead of output.** Our government *spends* but does not *build*.

v9.1 gives the deficit a **productive outlet**: government investment buys real capital goods, accumulates a
**public capital stock**, and public capital **raises every firm's productivity** (Barro 1990). Then:

> deficit → public investment → **capacity grows** → the injected money has more real output to buy →
> **inflation absorbed, turbulence damped**, and — a first for this model — **endogenous growth** (GDP rises,
> so debt/GDP need no longer diverge).

This is the single mechanism that could flip the government from net-negative to net-positive, because it is
the specific thing real government does that we omitted.

## 1. What already exists (audited) vs what's new

**All four foundations are present in v9's active path** (audited in code):
- ① Production function with TFP + capital: `Y_f = A · K_f^α · N_f^{1-α}` ([behavior.py] `produce`).
- ② Capital accumulation + depreciation: `K = (1-δ_K)·K + I` ([economy.py] Phase 4).
- ③ Goods→capital conversion: C-firms buy real capital goods from K-firms ([economy.py] Phase 3.5).
- ④ Government fiscal machinery: GOV account, spending, deficit (v9).

**New (only the last link):**
- (a) a **public capital stock** `K_pub` (economy-wide, reuses the ② accumulation primitive);
- (b) the **K_pub → productivity channel** in `produce` (the actual new mechanism);
- (c) **government investment** as a spending category that buys capital goods and feeds `K_pub`.

## 2. Ontology
- **Public capital `K_pub`** — one economy-wide stock (non-rival: infrastructure/R&D benefits ALL C-firms),
  held on the `Economy`, not per firm. Depreciates each tick.
- **Government investment** — a spending flow: the government buys real capital goods from the K-sector
  (like firms do), and those goods become `K_pub` (not consumed). Deficit-financed via the GOV account.

## 3. The mechanism

### 3a. Public capital in production (Barro 1990, multiplier form)
```
Y_f = A · K_f^α · N_f^{1-α} · (1 + K_pub / K_ref)^γ
```
- `K_ref` = total private C-capital at genesis (fixed normalization) ⇒ the factor starts at **1**.
- `γ` (`public_capital_gamma`) = public-capital output elasticity. γ=0 ⇒ factor≡1 ⇒ **bit-identical**.
  Anchored to the empirical public-capital elasticity (~0.05–0.15), NOT tuned to a §4 target (§0-ii).
- Multiplier (increasing-returns) form, not a rival factor, so no genesis `K_pub>0` is needed and `K_pub=0`
  ⇒ factor 1. Applied to ALL C-firms uniformly (a public good), so it shifts the whole supply curve out.

### 3b. Government investment (buys real capital, builds `K_pub`)
Each tick the government invests `I_pub = gov_investment_share · potential_output` (value), buying capital
goods from **K-firms** (competitive, cheapest-first, like its consumption procurement — §28.6). The real
units bought add to public capital; money flows GOV → K-firm (deficit, GOV goes negative).
```
K_pub ← (1 − δ_pub) · K_pub + (real capital-good units the government bought)
```
`δ_pub` (`public_capital_depreciation`) ≈ δ_K. Side benefit: this is **demand for the K-sector**, which has
been a chronic retained-earnings sink (§11.4).

### 3c. How it damps inflation (the point)
Government investment adds demand (buys K-goods) like consumption — but unlike consumption it **also raises
future supply** (K_pub → productivity → more output next tick). So the injected money meets *growing* real
output instead of a fixed pie ⇒ the 6× inflation of v9 should fall. The deficit finally has somewhere to go.

## 4. Accounting (A5-safe)
Government investment is `transfer(GOV → K-firm)` for real goods — identical in form to gov consumption, so
A5 holds (GOV goes more negative = more government debt = more private net wealth). `K_pub` is a REAL stock
(like firm capital), not money — it never enters the A5 sum, exactly as firm capital doesn't.

## 5. Levers (Config + Policy; all default 0 ⇒ bit-identical)
- **`gov_investment_share`** (g_I) — public investment as a share of potential output/tick. Anchored to real
  public-investment/GDP (~3–5%). A `Policy` lever (a government can change it in-run).
- **`public_capital_gamma`** (γ) — productivity elasticity to public capital. Anchored (~0.05–0.15). Config
  (a technological/structural constant, not a run-time policy dial).
- **`public_capital_depreciation`** (δ_pub) — ≈ δ_K. Config.
- `Config.v91()` = v9 + `gov_investment_share≈0.04`, `public_capital_gamma≈0.1`.

## 6. Tick placement
- **Phase 3.5 (capital market):** after C-firms buy capital, the government buys `I_pub` of the remaining
  K-goods (competitive), records the real units.
- **Phase 4 (settlement):** `K_pub ← (1−δ_pub)K_pub + gov_capital_units` (alongside firm capital accumulation).
- **Production (Phase 2):** `produce` multiplies by `(1 + K_pub/K_ref)^γ` (a per-tick factor computed once).

## 7. §0 discipline
- **§0-ii:** γ, g_I, δ_pub all anchored to real magnitudes; pre-register outcomes; never tune to a §4 value.
- **§0-iv parsimony:** two new dials (g_I, γ) + one reused (δ). One new real stock, zero new primitives.
- **Cumulative:** `gov_investment_share=0` or `γ=0` ⇒ bit-identical to v9 ⇒ v8.5 8/8 still preserved off.

## 8. Pre-registered hypotheses

| # | Hypothesis | Expected | Falsifier |
|---|---|---|---|
| H1 | Public investment absorbs the deficit → **less inflation** | v9's 6× → far lower | inflation unchanged |
| H2 | Public capital raises productivity → **higher real output & consumption** | reverse v9's −15% | no output gain |
| H3 | Capacity growth → **debt/GDP stabilises** (GDP grows) | bounded, not diverging | still diverges |
| H4 | Growth gives small firms room → **T6 eases** (less over-concentration) | Gini/slope toward Zipf | unchanged |
| H5 | The economy becomes **non-stationary (endogenous growth)** | GDP trends up | — (a paradigm change, see §9) |

Overarching pre-registration: **v9.1 should move the government from net-NEGATIVE (§28.8) toward
net-positive.** If it doesn't (γ too weak to matter, or growth destabilises), that is a clean, reportable result.

## 9. The big caveat — this breaks stationarity (a new paradigm)
Every prior version was **stationary** (fixed productivity; levels fluctuate around a constant). Public
capital + continuous investment makes productivity, output, prices, and nominal stocks **trend upward
(endogenous growth)**. Consequences to handle before trusting results:
- **§4 measures assume stationarity** — cyclical detrending (rolling-mean) already removes a slow trend, but
  distribution/level tests (T4 mean-u, T8) must be read on a GROWING economy; may need growth-adjustment.
- **Debt/GDP, credit/GDP** become the right lens (ratios, not levels) — and endogenous growth is exactly what
  lets them converge.
- This is a **genuine new layer**, not a knob: validate the growth path is sane (steady, not explosive)
  before reading anything else.

## 10. Deferred
- Endogenous productivity growth from PRIVATE R&D; human capital; public capital congestion (rival form);
  optimal public-investment rules; the v10 central bank (now more important — growth + interest rates).

## 11. Build order
1. `agents/economy`: add `Economy.public_capital` (K_pub) + `K_ref` (genesis private C-capital); a per-tick
   `pubcap_factor = (1 + K_pub/K_ref)^γ`.
2. `behavior.produce(firm, n_labor, pubcap_factor=1.0)`: multiply output by the factor (default 1 ⇒ identical);
   same for `invert_production`. Thread the factor at the call sites.
3. `config`/`policy`: `gov_investment_share`, `public_capital_gamma`, `public_capital_depreciation`; `Config.v91()`.
4. `economy`: government K-goods purchase (Phase 3.5, competitive) → `gov_capital_units`; `K_pub` accumulation
   + depreciation (Phase 4).
5. `metrics`: `public_capital`, `public_investment`, `pubcap_factor`, `real_output_growth` (exists), a
   trend/growth read.
6. `tests/test_v91_public_capital.py`: off ⇒ bit-identical; A5; K_pub accumulates & depreciates; γ>0 raises
   output; growth path is finite (not explosive).
7. Validate: growth-path sanity → then v9.1-vs-v9 battery (rerun §28.8's comparison) → §4 (with the growth
   caveat) → a v9.1 diagnostic.
8. DESIGNDOC §29.
