# V18.5+ Supply-Side Sector Differentiation — the Dual of the Consumption Split

> **STATUS: DRAFT.** The supply-side continuation of the v18 consumption-stratification
> arc (NOT a new v19 — same theme, same branch `feat/consumption-v18`). v18.0–18.4 split
> DEMAND into necessity/luxury; 18.5+ let SUPPLY follow — firms differentiate by which
> class they produce, and capital + entry/exit REALLOCATE between sectors as growth and
> demand composition shift. Structural transformation and Baumol-style relative-price
> change should EMERGE, not be seeded. Builds on the merged v18 core.

**Thesis.** v18 gave half the picture: the rich shift their budget share to luxury, but
no firm reallocates to catch that shift — the sector partition is frozen at genesis
(n_firm_share), entry aside. 18.5+ closes the loop: demand composition → sector returns →
capital reallocation → sector structure → (via the distribution) demand composition. This
is development economics' structural transformation, and it reuses the v16 entry/exit
machinery + the v18 investment channel wholesale.

## The load-bearing decision: SECTORAL CAPITAL FRICTION (the v16-friction analog)

In v18 necessity and luxury firms are technologically IDENTICAL. So if capital moves
between sectors without friction, the two sectors are perfect supply-side substitutes:
capital floods the higher-return sector every tick, equalizes returns instantly, and the
sector structure is pinned by current demand — no gradual transformation, just Walrasian
reshuffling every tick. This is exactly the pre-v16 frictionless-labor pathology.

**The core calibration of this whole extension is therefore how STICKY capital is between
sectors.** Options, in rising explicitness:
- capital is SECTOR-SPECIFIC (a necessity production line is not a luxury line);
- repurposing costs a RETOOLING loss (a fraction of the converted capital) + a LAG;
- entry favors the growing sector (already in v18.1).

Too little friction ⇒ instant clearing (the pathology). Too much ⇒ a frozen structure.
Calibrated right, structural transformation is a DECADES-scale slow process — the whole
point. This friction is v19-that-is-now-18.5's search-friction moment.

---

## 18.5 — Supply-Side Reallocation (differential investment + product-line switching)

**Purpose:** existing capital and new investment flow toward the higher-return sector,
with friction, so sector shares track demand composition GRADUALLY. Two channels, land
the emergent one first:

- **(a) Differential investment (zero new mechanism — reuses v18).** Firms already invest
  through the capital-goods market. A firm in the high-return sector invests more → grows;
  a firm in the low-return sector invests less → its capital depreciates → it shrinks;
  entry favors the growing sector (18.1). **Land this alone first** — sector shares may
  already drift toward demand composition through investment + entry/exit, with NO
  explicit switch. Measure how far it goes before adding machinery.
- **(b) Product-line switching (repurpose EXISTING capital).** A firm in the shrinking
  sector converts its capital to the growing sector, paying `switch_retool_loss` (a
  fraction of converted capital) + a `switch_lag`. This adds capital MOBILITY beyond
  investment (repurposing the stock, not just directing the flow). The retool loss + lag
  is the friction calibration. Switching is triggered by a sustained cross-sector return
  gap (hysteresis band — no per-tick flip-flopping).

**MEASURED FINDING (2026-07-13, the emergent channel is already active).** On a default
10y growth run (output 831→2260, 2.7×): necessity CAPITAL share falls 0.54→0.37 and
luxury firms grow faster (33→110 vs necessity 29→79) — **structural transformation
EMERGES from differential investment + sector-choosing entry alone, no switch needed.**
BUT capital LAGS demand: by year 9 necessity's DEMAND share is 0.233 while its CAPITAL
share is still 0.365 — necessity is OVER-CAPITALIZED by ~13pp because existing capital is
stuck (it leaves only through slow depreciation + differential new investment, never
repurposing). **That measured lag is the quantitative motivation for switching (18.5b):
let stuck capital retool to the growing sector faster.** So 18.5(a) ships as the gauge +
this finding; the built mechanism is the switching layer below.

Acceptance:
- [ ] Off ⇒ bit-identical (both channels flag-gated; the frozen-partition v18.4 baseline
      is the reference).
- [ ] Sector shares RESPOND to demand composition: **[MET emergently — necessity capital
      share 0.54→0.37 over the 10y growth run, tracking the demand fall gradually.]**
- [ ] **Product-line switching SHIPPED (18.5b):** a firm whose sector is out-returned by
      the other for a sustained window retools its capital to that sector, paying
      `switch_retool_loss` at a low `switch_hazard`. Off (non-default knobs) ⇒ bit-identical.
      On ⇒ it FIRES rarely (8 switches / 10y at the conservative default) and CLOSES the
      measured lag: necessity capital share 0.365 → 0.325 at year 9 (toward the 0.223
      demand share — the 13.2pp gap shrinks to 10.2pp). Conserving (drift ~5e-7; retooled
      capital is a real stock). **[MET.]**
- [ ] **Reallocation-rate watch (bullwhip analog, from day one):** gauge sector capital
      share + switch flow. The no-shock baseline must be QUIET — no limit cycles. **[MET:
      switches ~0.001/tick, max 2, no oscillation over 10y.]** The friction (retool loss +
      sustained-gap + low hazard) keeps transformation slow: switching closes ~23% of the
      lag, the rest stays with the emergent investment/entry channel — a realistic split.
- [ ] Structural transformation EMERGES: **[MET emergently — see the 18.5(a) finding.]**

## 18.6 — Multi-Product / Mixed Firms (the general case)

**Purpose:** a firm allocates its capacity/labor across BOTH lines by relative marginal
profit; single-product and switching are its corner cases (100/0 ↔ 0/100). This is the
realistic conglomerate and the general reallocation object.

Components:
- Per-firm two-sector production: the firm splits labor (and sector-specific capital)
  between an N-line and an L-line, allocating toward the higher marginal return with the
  same retooling friction (18.5) on the capital split.
- Two inventories, two posted prices per firm (the B2/B3 grammar per line).
- Sells into BOTH sessions (n-session from the N-line, l-session from the L-line).

Acceptance:
- [ ] Off (or single-line firms) ⇒ reduces to 18.5 bit-identical.
- [ ] A firm shifts its capacity mix toward the higher-return line, frictionally.
- [ ] Aggregate sector structure matches the 18.5 single-product+switching outcome within
      a corridor (the general case nests the special case — a consistency check).
- [ ] Conservation + the stock-flow gates hold with two inventories per firm.

## 18.7 — Couplings & Validation (Baumol, the deflation anatomy, the feedback loop)

**Purpose:** cash out the structural economics the supply split unlocks. Each experiment
pre-registered.

- **Baumol / structural change — the headline pre-registered prediction.** Claim: relative
  prices diverge WITHOUT any seeded sectoral productivity gap — necessity relative price
  FALLS (quantity-capped demand saturates as productivity/supply grows), luxury relative
  price is SUPPORTED (income-elastic demand grows). Test on a growth scenario; report the
  necessity/luxury relative-price path. Optional 18.7b: add a sectoral productivity
  asymmetry and test whether Baumol is driven by the DEMAND cap (v18 structure) or the
  TECHNOLOGY gap (the classic story) — a clean decomposition.
- **The deflation-puzzle anatomy (closes the v18.2 open question).** v18.2 found the
  aggregate price index falling under the energy shock. Decompose it with the v18.2 group
  CPI + the 18.5 sector structure: is the aggregate "deflation" a COMPOSITION artifact —
  a necessity-price collapse (supply growth into capped demand) masking luxury inflation?
  Pre-registered: attribute the aggregate move to N vs L contributions.
- **The distribution → structure → distribution feedback loop (the prize AND the risk).**
  With supply reallocating, the loop closes: concentration → luxury demand → luxury sector
  returns → capital into luxury → (its ownership/wages) → concentration. This is the first
  complete feedback. RISK: it is a positive loop — watch for runaway concentration or limit
  cycles (the 18.5 reallocation-rate watch extended to the wealth/structure coupling).
  Report the loop's gain and stability, don't assume it converges.

Acceptance:
- [ ] Baumol relative-price divergence emerges (or is refuted) on a pre-registered growth
      run; the demand-cap-vs-technology decomposition documented.
- [ ] Deflation anatomy: the aggregate price move decomposed into N/L contributions; the
      "necessity-collapse composition" hypothesis confirmed or refuted.
- [ ] Feedback-loop stability characterized (gain, convergence/oscillation); no silent
      runaway; `diagnostic_v185.png` (structural-transformation portrait).

---

## Sequencing & relationship to the v18 core

Builds on the merged v18 core (18.0–18.4). One stage at a time, flag-off bit-identical to
the cumulative baseline, per-stage diagnostic + honest write-up (the arc's discipline).
The whole v18 arc (demand 18.0–18.4 + supply 18.5–18.7) merges into dev when the supply
side lands — the two halves are one picture.

## Standing decision log (agreed 2026-07-13)

| Decision | Ruling |
|---|---|
| Scope | v18.x extension (same arc/branch), NOT a new v19 — supply-side dual of the demand split |
| Load-bearing lever | SECTORAL CAPITAL FRICTION (retool loss + lag) — the v16 search-friction analog; without it sectors clear instantly |
| Reallocation channels | differential investment (emergent, land first) → product-line switching (repurpose stock) → multi-product firms (general case) |
| Baumol driver | test whether it emerges from the DEMAND cap (v18 quantity-capped necessity) alone, before adding a technology asymmetry |
| Deflation puzzle | the v18.2 aggregate-deflation open question gets a structural anatomy here (necessity-collapse composition hypothesis) |
| Feedback loop | distribution→structure→distribution closes here; treated as a STABILITY risk with a reallocation-rate/concentration watch, not assumed convergent |
