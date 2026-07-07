# Implementation plan — v8.1 (Gibrat multiplicative growth → clean power-law tails)

> **Status: engineering plan. Not started.** The one mechanism §22 identified as jointly missing for
> T6 (firm-size Zipf) AND T8 (wealth heavy tail): both have a **flat upper tail (slope ≈ −0.33)**
> because firm growth **mean-reverts** to a common target (accelerator K\*=v·yᵉ) instead of growing
> **multiplicatively** (Gibrat). v8.1 makes firm market share a **multiplicative random walk**, which
> — with the v4 entry/exit barrier — is the canonical Zipf mechanism (Simon 1955 / Gabaix 1999), and
> propagates to wealth through the v8 equity/margin chain.

## 0. Why this fixes BOTH tails at once

- **T6 directly.** Gibrat's law (growth rate independent of size) + a reflecting lower barrier (entry
  of small firms / exit of failures) ⇒ a stationary **Pareto/Zipf** firm-size distribution. Our
  problem is precisely that we have the barrier (v4) but *not* the multiplicative growth (§15).
- **T8 by propagation.** In v8, household wealth = leveraged equity gains, and equity value tracks
  firm success. Once firm SIZE is Zipf (a few huge firms), their EQUITY is worth a heavy-tailed
  amount, so the holders (founders + levered buyers) inherit a heavy wealth tail. **Fix the firm tail
  and the wealth tail follows through the equity channel** — the unification §22.2 called for.

## 1. The mechanism — market share as a multiplicative random walk

Give each C-firm a persistent **attractiveness / customer base** `a_f` (a market-share weight, NOT
money, NOT in any conservation law). Two forces:

1. **Gibrat shock (multiplicative, idiosyncratic).** Each tick `a_f *= exp(σ_g·z − σ_g²/2)`,
   `z~N(0,1)` — a mean-preserving geometric random walk. This is the source of *persistent* size
   divergence the mean-reverting accelerator lacks.
2. **Demand allocated ∝ `a_f`.** In the goods market a buyer picks a seller with probability
   proportional to `a_f` (a size-biased lottery) rather than uniform (m=1) or cheapest (m≥2). Bigger
   customer base ⇒ more sales ⇒ (via B2) higher expected demand ⇒ more production/investment ⇒
   growth. Growth is **proportional** (Gibrat), not winner-take-all, because the shock is
   multiplicative and iid across sizes.

Entry (v4): new firms start with **small `a_f`** (the reflecting barrier). Exit (v4): low-`a_f` firms
earn little → insolvency → die. Barrier + multiplicative growth ⇒ **Zipf**.

## 2. The knife-edge to respect (linear preferential attachment, not super-linear)

Demand ∝ `a_f` (LINEAR) with multiplicative noise + entry ⇒ Zipf. Demand ∝ `a_f^β` with β>1
(super-linear) ⇒ **winner-take-all** (one firm absorbs everything, the §11.6 L-shape); β<1 ⇒ too
equal. So the exponent is a knife-edge around 1, and there is a stable Zipf **window** in
(σ_g, β, entry-rate) — analogous to v8's leverage window. Calibrating into that window is the whole
game; a sweep is part of the deliverable.

## 3. Data model & the matching change

| where | change |
|---|---|
| `agents.py` | `Firm.attractiveness` (`a_f`, ≥0). New entrants seeded small; genesis firms seeded ~1. |
| `interfaces.py` | a new goods-matching mode: buyer samples/chooses a seller with prob ∝ `a_f^β` (size-biased). Reuses the `execute_market` plumbing; only the seller-selection rule changes. |
| `economy.py` | a small step (Phase 1 or 4) that applies the Gibrat shock to every C-firm's `a_f` (seeded RNG); entrants get a small `a_f` in `_birth_c_firm`. |
| `behavior.py` | none — pricing/production untouched; growth enters purely through *realised demand*, so expectations (B2) and the accelerator (B5) carry it without new equations. |

**No pricing/production change** keeps the blast radius small: v8.1 only reallocates the *same* total
demand across firms (a distributional change), so aggregate output/employment are untouched.

## 4. Config (parameter budget)

`gibrat_growth: bool=False` (master; off ⇒ v8 bit-identical) · `gibrat_sigma` (σ_g, shock size —
the core dial) · `pref_attach_beta` (β, demand exponent on `a_f`; ~1 for Zipf) · optional
`gibrat_entry_a0` (entrant seed share). `Config.v81()` = v8 + `gibrat_growth`, β≈1, σ_g calibrated.

## 5. Conservation

**Untouched.** `a_f` is a market-share weight, not money and not shares — it only decides *which*
seller a buyer transacts with. Money still moves by `transfer` in the goods market (A5 exact), shares
still conserve (v6.1), the equity market is unchanged. No new invariant; the existing gates cover it.

## 6. Metrics

Reuse the rank-size machinery. Headline: **upper-tail rank-size slope** for firm size (T6) and for
household net worth (T8) — the flat −0.33 both must move toward a clean **Pareto ≈ −1**. Add
`firm_attractiveness_gini`, `firm_size_pareto_slope`, `wealth_pareto_slope`, and a Gibrat check
(cross-sectional corr of growth rate vs size ≈ 0 — the defining property).

## 7. Tests (tests/test_v81_gibrat.py)

1. **Regression** — `gibrat_growth=False` ⇒ v8 bit-identical.
2. **Gibrat property** — growth rate is ~independent of size (corr(Δlog size, log size) ≈ 0).
3. **Firm-size Zipf** — upper-tail rank-size slope in ~[−1.3, −0.7], and *robust across seeds*
   (fixing §22's noisy −0.75±0.26) with a **steep tail** (not the flat −0.33).
4. **Wealth tail follows** — household net-worth upper-tail slope steepens materially vs v8.
5. **Aggregates preserved** — total output / unemployment unchanged in distribution vs v8 (it's a
   cross-sectional reallocation), so the other §4 regularities can't have moved.
6. Conservation (A5 + shares) intact.

## 8. Milestone / acceptance

**Done** = (1) regression green; (2) the Gibrat property holds; (3) **T6 firm-size upper tail is a
clean, seed-robust Pareto (~−1)**, not the flat −0.33; (4) **T8 wealth upper tail steepens** toward a
power law (the propagation through equity); (5) a **§4 re-validation** confirming the other 7 hold and
T6/T8 move from "shape right / tail flat" toward "clean power-law tail" — ideally **8/8**, or a
documented account of which tail is now clean. Expected caveat: a stable Zipf lives in a bounded
(σ_g, β) window; outside it the economy either stays too equal or tips to winner-take-all — the sweep
maps that window (deliverable, like v5's phase diagram and v8's leverage ceiling).

## 9. Open decisions to confirm before coding
1. **Multiplicative market share (Simon preferential attachment)** — recommended — vs multiplicative
   TFP/productivity (cleaner micro-story, but size only follows if demand also reallocates, so it
   needs this same matching change anyway). Recommend the market-share route as the parsimonious one.
2. **Linear preferential attachment (β≈1)** as the default, swept — recommend.
3. **Reuse v4 entry/exit as the barrier** (no new exit mechanism) — recommend.
4. **Shock is mean-preserving** (no aggregate drift; pure redistribution of shares) — recommend, to
   avoid perturbing the aggregate regularities.
