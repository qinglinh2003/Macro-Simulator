# V20 Open Economy Plan — Fiat, Foreign Exchange & Coupled Multi-Economy Trade

> **STATUS: DRAFT — DESIGN ONLY, NOT STARTED (2026-07-13).** This document records the
> money+FX+trade module design converged in discussion. No code yet. **S0 (the `World`
> container + instantiable `Economy`) is BLOCKED on coordinating object boundaries with
> the v19 arc** (`feat/tech-tfp-v19` = technical object refactor + exogenous TFP drift),
> which is very likely delivering exactly the instantiable-`Economy` refactor this needs.
> Do NOT build a second parallel object model — see §S0/v19 boundary.
>
> **Scope of THIS plan:** fiat money + foreign exchange + the trade system, under a
> **fully-coupled multi-economy (L2)** target. Capital account, pegged regimes, currency
> crises, and migration are named but **OUT of scope here** (they all grow from one seam —
> see §12 TODO).
>
> Branch `feat/open-economy-v20` forked from dev@19457d0 (v16 labor + v17 energy + v18
> consumption all merged).

---

## 0. The decision that frames everything: L2, fully coupled

The user has ruled: **L2 — N distinct full economies that trade with EACH OTHER**,
general equilibrium, emergent contagion. Not a small-open-economy (one economy vs an
exogenous rest-of-world stub), not L1 (N economies each facing a common *exogenous*
world without mutual coupling). The rest-of-world is **the other N−1 real economies**,
whose prices are endogenous.

The payoff is a **comparative-macro laboratory**: give each economy a *character*
(productivity/TFP, demographics, policy regime, sector mix, financial structure), run
them coupled, and watch emergent comparative outcomes — who runs surplus/deficit, whose
currency appreciates/depreciates, who imports inflation, whether a shock in one
propagates through trade + exchange rates.

## 1. First-principles grounding (why these objects and no others)

Three closed economies, each already at its own internal equilibrium, "discover" each
other. Their relative prices generically **do not match** — that price gradient is the
stored potential; everything below is the system discharging down it.

The seed is a **single agent in A wanting one good from B**. Every component is *forced*
by that seed:

1. **Money is local.** A's money is a claim on A's goods + A's tax system; B does not
   accept it. ⇒ any cross-border purchase needs **currency conversion** ⇒ FX exists.
2. **The FX market is a dealer with inventory**, not an abstract curve. Concretely: an
   agent holding a deposit account in *every* economy's banking system (correspondent /
   nostro-vostro), quoting a rate, absorbing flow imbalance into a multi-currency
   inventory. This is literally how real FX settles: an OTC dealer market where each
   currency settles in its **own** home system and only *ownership* crosses the border.
3. **A trade imbalance is a foreign claim's accounting shadow.** You cannot have goods
   flow one way without a claim flowing the other; the dealer's *inventory* is where that
   claim sits. (Capital account = later, when inventory is allowed to *drift* — §12.)
4. **The exchange rate is a groping price, not a Walrasian jump.** Frictionless instant
   clearing is the pathology this model has paid for twice (labor v16, capital v18); the
   dealer's inventory is the buffer that lets the rate grope.

## 2. Exchange-rate representation — the numéraire as a gauge, cross-rates derived

Do NOT track N(N−1)/2 bilateral rates and police consistency. Represent **N rates
against an abstract world numéraire**: `e_i` = units of currency `i` per numéraire unit.
Bilateral rate `i↔j = e_i / e_j`; **all cross-rates derive from the single vector `e` ⇒
triangular no-arbitrage holds by construction.** Groping acts only on the **N−1
independent** ratios.

**The numéraire is a measuring rod, NOT an asset.** Nobody holds it, nobody settles in
it, the dealer has NO inventory of it. It is purely the denominator we quote rates
against. It is emphatically **not** a world/vehicle currency (which would be a real
settlement asset with dealer inventory — that is an emergent behavioral object, §2.2).

### 2.1 Gauge freedom → why a normalization is mandatory

Only the ratios `e_i/e_j` (N−1 of them) are physical. Multiplying every `e_i` by a common
λ leaves all bilateral rates unchanged — a **gauge freedom**; the overall scale is a
redundant degree of freedom with no economic meaning. **The numéraire is exactly the
choice that fixes this gauge.** We therefore **re-normalize the `e` vector every tick**
(project it back onto the gauge-fixing surface); otherwise the overall scale random-walks
— invisible to the economics but corrosive to determinism, to any numéraire-denominated
quantity, and to numerical hygiene (`e_i` drifting toward 0/∞).

**Chosen normalization — symmetric geometric currency basket:**
`Σ_i w_i · log(e_i) = 0`  (i.e. `Π_i e_i^{w_i} = 1`), weights `w_i` fixed at genesis.
- **Symmetric** — privileges no single currency (a single-currency anchor `e_1≡1` would
  let currency 1's own inflation/noise contaminate every measured rate; rejected for a
  comparative lab).
- **Geometric / log-space** — the correct space for ratio objects (halving vs doubling
  symmetric); an arithmetic mean would be dominated by the numerically largest `e_i`.
- One scalar constraint pins the one redundant DOF, leaving exactly N−1 physical rates.
- Weights: start **equal (`1/N`)**; economy-size weighting is an option (deferred).

### 2.2 Numéraire (measurement) ⊥ vehicle currency (behavior)

The numéraire is the **modeler's measurement gauge**; a vehicle/reserve currency is an
**emergent behavioral outcome** (which currency agents route settlement through / hold as
reserves, an N≥3 phenomenon). These are **orthogonal** — we can measure against a
symmetric basket while, say, currency 2 endogenously becomes the settlement hub. Keeping
them separate is scientific hygiene: the measurement convention must not prejudge the
emergent outcome we want to observe.

### 2.3 The numéraire's three roles (the dealer does NOT need it operationally)

The dealer only ever does **bilateral swaps** (currency `i` for `j`) and holds real-
currency inventory — it needs no numéraire to operate. The numéraire serves only us:
(1) compact rate vector with self-consistent derived cross-rates; (2) a common unit for
aggregate gates/metrics — the multilateral BoP identity `Σ_i (trade balance_i in
numéraire) ≡ 0` (gate #2) is stated in it; (3) gauge-fixing for the groping (§2.1).

### 2.4 Nominal vs real — do not read `e_i` as "real" anything

The numéraire fixes the **nominal** books. **Trade is driven by the REAL exchange rate,
not the nominal one:** `real_ij = (e_i/e_j) · (P_j/P_i)`, derived from nominal rates +
domestic price levels. Under the basket normalization the numéraire is itself a basket of
the currencies, so it inflates with the world — `e_i` measures nominal relative currency
value only. The economics runs on the derived real rate; §4–§5's trade decisions use it.

## 3. The FX dealer — a World-level object

The dealer is the ONE object that sees all economies, so it lives in the **`World`/
coupling layer**, not inside any single `Economy` (this is also where the BSP barrier
lives — §5). It holds a deposit account in each of the N banking systems, quotes the
rate vector `e`, and absorbs residual flow imbalance into inventory.

**Inventory semantics = the trade/capital boundary (refined):**
- **Pure-trade layer (this plan):** dealer inventory **mean-reverts to zero** — the rate
  gropes in the direction that pushes inventory back to zero. Foreign positions are
  *transient buffers*; trade balances over the groping horizon, **not** every tick.
- **Capital-account layer (§12):** inventory (and residents) may **drift** into a
  persistent, *chosen* asset position driven by yield, not just residual buffering.

(This supersedes the earlier "force conversion within the tick" framing — that was the
Walrasian version. Under groping, the honest statement is *mean-reverting inventory*.)

Start with **one dedicated `FXDealer`** (simplest); banks-as-dealers (more realistic
correspondent picture) is a later refinement.

## 4. The international trade system — N local markets, arbitrage-connected

**Organizing frame: trade is N *local* goods markets connected by arbitrage, NOT one
world market.** Each economy keeps its own price per good (v18's sessions stay local); a
"world price" is an *emergent summary*, never a primitive. The alternative — one global
market per good clearing at a single world price — would destroy the local session
structure and is not agent-native, so it is **rejected**. This choice is what lets the
trade system fit the BSP tick (§5) and the model's emergence philosophy.

**Architectural stance: trade extends the goods market's *choice set*; it is NOT a
bolt-on aggregate flow.** A domestic buyer's choice set gains foreign sources (buy abroad
if cheaper, net of rate + friction); a domestic seller may ship to whichever market pays
more. There is no separate "trade module" moving aggregate quantities — the same v18
session decision now ranges over foreign options, fed in via the §5 barrier.

### 4.1 The two defining knobs (they set the system's character)

1. **Tradable / non-tradable partition — the highest-leverage structural choice.**
   Tradable candidates: energy (v17), necessity, luxury, capital goods. Non-tradable:
   housing/land (v15 — the natural anchor), labor (until migration). *Why it dominates:*
   the non-tradable sector is what lets the **real exchange rate move at all**. If
   everything trades, prices equalize and the real rate is pinned (degenerate). Housing as
   the non-tradable anchor gives room for real-rate movement, persistent price-level gaps,
   **Balassa-Samuelson** (richer ⇒ dearer non-tradables), **Dutch disease** (an export
   boom appreciates the real rate and hollows out other tradables), and competitiveness.
2. **Degree of integration — the friction dial (= §7 lever 1).** Iceberg friction runs
   from ∞ (autarky = back to closed) to 0 (law of one price = full integration). Its
   microstructure is a **no-arbitrage band**: a price gap within friction cost ⇒ no trade;
   beyond it ⇒ arbitrage flows close the gap. The system's micro = N local prices
   partially levelled by bands. Baseline: **moderate openness** (some trade, balanced).

### 4.2 Structure: a trade network, and what it produces

With N economies, each good has a **bilateral flow matrix** (who ships to whom). Friction
may be **per-pair** (distance ⇒ gravity-like trade: near/large partners trade more) or
**uniform** (symmetric network). Under the tentative "same goods, different productivity"
motive (§10 fork), trade is **inter-industry / arbitrage-driven**: the low-cost producer
of a good exports it, the high-cost one imports it. The system's **emergent product is a
specialization pattern** — which economy becomes the necessity-exporter, which the
luxury-exporter — the comparative-advantage equilibrium the flows converge toward. That
pattern is the headline outcome to observe.

### 4.3 Trade ⊗ FX — one set of transactions, two dual books

Every cross-border transaction is **simultaneously** a real leg (good `i→j`) and a payment
leg (money `j→i`, via FX conversion). So the trade layer *feeds* the FX layer: aggregate
export/import values per currency → currency excess demands → rate groping (§5, §13
sketch). The **trade balance (goods view) and the BoP (money view) are the same thing
seen from two sides** — the dual books that gates #1/#2 keep consistent. "The
international trade system" is precisely **trade layer ⊗ FX layer**, one system.

### 4.4 Border policy + the distributional politics (place-holders)

Tariffs, quotas, export subsidies sit **on the flows** as Policy-layer (run-time) levers
— reserve the slots even if inert first. They connect to the politics: opening is **not
Pareto-improving within an economy** (cheap-import consumers win, undercut producers
lose), the origin of trade barriers and a hook into the v18 distributional line.

### 4.5 Structural forks still OPEN (not locked — see §10, §13)

- **Same goods, different productivity** (import competition, connects v18) **vs distinct
  goods per economy** (pure variety gains).
- **Final-goods trade only vs intermediate-goods trade** — energy-as-tradable-intermediate
  makes an import a production *input*, creating **global value chains**: an energy
  exporter's shock propagates through importers' costs (the real oil shock, connects v17).
- **Trade-network shape** — per-pair (gravity) vs uniform friction.

## 5. The tick — Bulk Synchronous Parallel (BSP)

Each tick has two parts: a **thin central coupling barrier** + a **heavy independent
domestic step**. The data crossing the barrier is tiny (aggregate export demands, import
supplies, prices per tradable good); the domestic compute is large (thousands of agents)
— a favorable computation/communication ratio.

```
per tick:
  1. COUPLING BARRIER (central, deterministic, thin):
       using LAST tick's domestic prices + current rate vector e:
         - compute each economy's export demand (foreign demand for its goods)
           and import availability (what it can source abroad, at what price)
         - grope e on each currency's flow imbalance
         - reductions across economies use a FIXED order (sort by economy id)
  2. DOMESTIC STEP (per economy, INDEPENDENT -> parallelizable):
         run the full domestic tick, with
           - export demand injected as extra demand into the goods market
           - imports injected as extra supply / competition
         uses only the barrier's outputs; never touches other economies' in-flight state
  3. DEALER INVENTORY UPDATE from realized net flows -> feeds next tick's groping
```

**Trade decisions use last tick's prices** — this is the *fixed-cadence stale coupling*:
it (a) makes the domestic step cleanly parallel, (b) is economically defensible (trade
decisions ride on yesterday's prices; order/shipping lags are real), and (c) keeps the
**domestic goods phase almost unchanged** (trade is just injected demand/supply terms),
which protects modularity and bit-identity.

**Engineering discipline:** the tick is *written* in this BSP shape (independent domestic
step + one explicit narrow barrier) but **implemented serially first** (a `for` loop over
economies) — deterministic and debuggable. Swap the serial loop for a process pool
**only** when profiling justifies it and N/run-length warrant it. Premature
multiprocessing buys ~2–3× on small N at the cost of IPC + determinism hazards +
debugging pain. Single-machine multicore is the ceiling worth targeting; distributed
(multi-machine) is over-engineering for a handful of economies.

## 6. Accounting keystone — four hard gates

1. **Per-currency conservation (up to dealer inventory):**
   `Δ(currency i stock) = domestic_creation_i − destruction_i + Δ(dealer_i_inventory)`.
   Balanced cross-border flows do NOT change currency `i`'s stock (an exporter is paid in
   `i`-money that an importer already spent). A5 holds per economy with residual **exactly
   equal to the dealer's `i`-inventory** — reconcile as a gate.
2. **Multilateral BoP identity:** `Σ_i (trade balance_i, valued in numéraire) ≡ 0` (one
   economy's export is another's import). This is the closed-economy conservation law's
   L2 analog and must hold to the penny.
3. **N=1, coupling OFF ≡ closed dev, bit-identical.** The bridge that pins the whole
   refactor to the project's discipline. A one-economy `World` with the FX flag off must
   reproduce dev's frontier digest byte-for-byte.
4. **Triangular consistency assertion:** cross-rates from `e_i/e_j` are arbitrage-free by
   construction — assert cheaply as a guard.

## 7. Load-bearing levers — two, the second is L2-specific

1. **Iceberg trade friction** — sets the *degree of integration*. Frictionless ⇒ law of
   one price ⇒ prices equalize instantly ⇒ the border loses meaning (degenerate). This is
   the FX-layer analog of search friction (v16) and retool friction (v18.5).
2. **Groping speed × dealer inventory-buffer size (jointly)** — sets the **stability of
   the coupled system**. Too fast / buffer too small ⇒ oscillation (the feedback-
   instability risk). Too slow ⇒ rates lag fundamentals, imbalances persist. This pair is
   calibrated against the quiet multi-economy baseline (§8).

## 8. Genesis / quiet baseline (L2)

At genesis, all N economies are in a **balanced** state: trade balances *multilaterally*
at the initial rate vector, rates are flat, no economy accumulates. With the flag on but
nothing pushing, the coupled system must **stay quiet** (rates flat, trade balanced). If
it drifts at genesis, the calibration is wrong. Only *then* perturb one economy's
character and watch divergence. (Standard project discipline: quiet baseline first.)

## 9. Determinism checklist (non-negotiable under bit-identity)

- **Fixed reduction order** across economies (sort by id before summing — float addition
  is non-associative; nondeterministic arrival order → different bits).
- **Per-economy independent, deterministically-seeded RNG** (results must not depend on
  scheduling).
- **Fixed coupling cadence** — every tick to start (correctness first); relax to every
  `K` ticks (fixed `K`, *not* data-dependent "sync when necessary", which would break
  reproducibility) only if profiling demands. The FX friction we need for stability
  conveniently also makes slow-moving coupling variables safe to exchange every `K`.
- Dealer updates also run in fixed order.

## 10. Design forks — settled vs open

**Settled:**

| Fork | Options | Decision |
|---|---|---|
| Economies | SOE stub / L1 parallel / **L2 coupled** | **L2** (user ruling §0) |
| Settlement medium | single world money / **fiats + rates** | fiats + rate vector |
| Rate representation | bilateral matrix / **numéraire vector** | numéraire vector, cross-rates derived |
| Regime | **float first** / peg | float; peg is degenerate until capital flows exist (§12) |
| Dealer | **dedicated FXDealer** / banks | dedicated first; banks later |
| Parallelism | **serial-first BSP shape** / process pool now | serial-first; parallelize on profiling evidence |

**Still open (trade-system structure — §4.5):** same-goods-diff-productivity vs distinct
goods; final-only vs intermediate trade (energy); per-pair (gravity) vs uniform friction;
the tradable/non-tradable partition itself.

## 11. Staging (L2 is the target; still built in layers)

- **S0 — prerequisite refactor.** `World` container + instantiable `Economy`; **N=1,
  coupling off ≡ closed dev (gate #3).** No coupling yet. **BLOCKED on v19 boundary.**
- **S1 — first real L2.** 2 economies, coupling on, trade only, rates grope, inventory
  mean-reverts. Two balanced economies stay balanced (quiet baseline).
- **S2 — divergence.** Give the 2 economies different characters → watch divergence
  (surplus/deficit, appreciation/depreciation). Import competition hits the v18 N/L
  sectors; terms-of-trade shock connects to v17 (energy as an import = the real oil
  shock).
- **S3 — generalize to N.** Numéraire + derived cross-rates + multilateral balance;
  vehicle-currency emergence becomes observable (N≥3).
- **S4 — capital account.** Dealer/residents hold persistent, yield-driven positions →
  NFA, interest parity, the trilemma.

Each stage: flag-gated, per-stage tests, cumulative bit-identity, a `diagnostic_v2XX.png`.

## S0 / v19 boundary coordination (do this FIRST, before any code)

The v19 arc (`feat/tech-tfp-v19`) is "technical object refactor + exogenous TFP drift."
Its object refactor is **very likely the instantiable-`Economy` foundation S0 needs.**
Before writing S0, agree with the v19 line on:

- **Who delivers the instantiable `Economy`** (self-contained: own config, agents, banks,
  CB, treasury, RNG streams) and what its public surface is.
- **Where the `World` container hangs** and how it owns/orchestrates N economies + the
  World-level FX dealer + the rate vector.
- **RNG ownership**: per-economy independent streams seeded deterministically; the
  coupling/dealer layer's own stream (if any).
- Confirming the **N=1 ≡ closed-dev bit-identity gate** survives the refactor (it should
  be the refactor's own acceptance test too — shared interest).

Building a second, parallel object model here would collide with v19. This section must
resolve before S0 code.

## 12. Out of scope here — the one seam everything grows from

All of the following grow from **letting the dealer's (and residents') inventory drift
persistently instead of mean-reverting** — i.e. the capital account:

- **Capital account / capital flows** (yield-driven persistent positions) → NFA,
  covered/uncovered interest parity, the impossible trinity.
- **Pegged regime** = swap the private dealer for the **central bank** as dealer of last
  resort: fixes the price, absorbs all imbalance onto FX **reserves** (its inventory).
- **Currency crises** = a peg + a shock + the reserve constraint → reserve depletion →
  devaluation, **reusing the existing bank-run / reserve-tier / LoLR machinery** (v11.4/
  v11.5/v12.4) — the crisis emerges, it is not tuned.
- **Terms-of-trade / oil shocks** = shock world prices; energy-as-import turns v17's
  domestic capacity cut into the real imported-oil shock.
- **Migration** = the deprivation escape valve v18 flagged as missing in a closed economy
  (deprived households emigrate instead of lingering out-of-domain) + foreign labor.

## 13. Open drill-downs (next design sessions)

- ✅ **RESOLVED — abstract numéraire** (§2): a gauge choice, not an asset; symmetric
  geometric-basket normalization `Π e_i^{w_i}=1` re-applied each tick; numéraire ⊥ vehicle
  currency; nominal-vs-real distinction. *Remaining sub-choices:* basket weights `w_i`
  (equal to start) and whether re-normalization interacts with groping stability.
- The exact `e_i` groping rule — **sketch:** `log e_i += λ·(X_i/scale)` on currency-`i`
  excess-demand `X_i`, then subtract `Σ_j w_j log e_j` to re-impose the gauge; `Σ_i X_i ≡
  0` (Walras / gate #2) with fixed-id reduction. *Open:* speed `λ`, scale term,
  inventory-feedback coupling, and the groping/normalization stability interaction.
- **Tradable/non-tradable partition** (§4.1) — which of energy/necessity/luxury/capital
  are tradable; housing as the non-tradable anchor.
- Iceberg friction parameterization (per-unit vs proportional; per-pair vs uniform).
- How export demand / import supply enter the v18 goods session (energy→N→L hierarchy)
  without disturbing its flag-off byte-identity.
- Whether the FXDealer is dedicated or the banks collectively (correspondent picture).
