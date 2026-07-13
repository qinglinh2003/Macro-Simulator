# V20 Open Economy Plan — Fiat, Foreign Exchange & Coupled Multi-Economy Trade

> **STATUS: DRAFT — DESIGN ONLY, NOT STARTED (2026-07-13).** This document records the
> money+FX+trade module design converged in discussion. No code yet. **S0 (the `World`
> container + instantiable `Economy`) is BLOCKED on coordinating object boundaries with
> the v19 arc** (`feat/tech-tfp-v19` = technical object refactor + exogenous TFP drift),
> which is very likely delivering exactly the instantiable-`Economy` refactor this needs.
> Do NOT build a second parallel object model — see §S0/v19 boundary.
>
> **Scope of THIS plan:** fiat money + foreign exchange + the trade system (Layer A's
> first two flows), under a **fully-coupled multi-economy (L2)** target. International
> capital, migration, the derived-income layer, and governance/strategic interaction are
> **OUT of scope here** — see the full open-economy component panorama + roadmap in §12.
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

## 0.5 The foundational component set — the pinned scope of v20

**Organizing insight — foundation = primitives; the rest of the panorama (§12) = the same
primitives reused with different payloads / rules.** Trade = the cross-border transaction
primitive with a *goods* payload; capital = same primitive, *financial-claim* payload;
migration = same primitive, *person* payload (+ residency change); governance = *rules* on
the primitive; stocks/IIP/systemic = *accumulation* of it. So the base is genuinely small
and reusable, and **v20 = the foundation + the single simplest payload (trade)** — a
complete, completable slice. Everything else adds payloads/rules on the SAME base later
and does **not** re-touch it.

Built on top of N *existing* closed economies (households/firms/banks/CB/treasury —
unchanged), the open-economy foundation is **seven components**:

**Structural (make the open economy exist & stay accounting-closed):**
1. **The two tags — residency + currency-denomination.** The atoms that turn N closed
   economies into one open system: every agent/asset is tagged by which economy it belongs
   to and which money it is denominated in. Without them "cross-border" is undefined; all
   later objects (capital, factor income, foreign holdings, migration) derive from them.
   **Get these wrong and capital/migration/income all require rework — highest-stakes.**
2. **The `World` container + orchestration.** Holds N instantiable `Economy` objects and
   runs the BSP tick (independent domestic step + coupling barrier). This is S0 (rides the
   v19 refactor).
3. **Multi-currency system + exchange-rate vector** (numéraire + derived cross-rates, §2).
4. **The FX conversion mechanism** (the dealer, §3). [2+3+4 = the money/FX layer.]
5. **The cross-border transaction primitive** — real leg one way, claim/money the other,
   honestly settled. Trade is its first payload. **⑤ = decision + substitution-smoothing +
   settlement, not just accounting:** it must include the who-transacts *decision rule*,
   and an Armington-style *substitution smoothing* (perfect substitutes + a friction band
   → bang-bang oscillation that wrecks the §8 quiet baseline).
6. **The BoP accounting spine** — the conservation law closing the open system (multilateral
   `Σ=0`); the open-economy analog of the closed A5 gate. **⑥ must be complete enough to
   book the dealer's cross-currency position AND its valuation/revaluation** — a rate move
   revalues held inventory with no transaction; unbooked, conservation leaks and the spine
   is fiction.

**Epistemic (make the open economy serve its purpose):**
7. **The observability / measurement layer.** The entire point (§0) is to *watch* emergent
   comparative outcomes; without gauges you build an unreadable machine. Trade balance,
   nominal & real exchange rates, terms of trade, specialization pattern, per-good
   export/import volumes, NFA (= dealer inventory) — plus **health flags** for the new
   failure modes (rate groping non-convergence, persistent imbalance, inventory blow-up).
   Foundational to *purpose* and to the per-version diagnostic discipline, not to existence.

**Correctly deferred (NOT foundational to v20):** international capital, migration, the
derived-income layer, governance/strategic interaction, stocks/IIP/systemic emergence,
forward-looking expectations (static is fine at the trade-only layer). See §12.

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

**CONVERGED — groping IS the mean-reversion.** The rate gropes on the dealer's **net
inventory** (inventory = accumulated flow imbalance = the excess-demand signal), so
"grope on flow imbalance" and "mean-revert inventory" are one rule, not two.

**CONVERGED — dealer P&L / ownership / revaluation.** The dealer runs a **zero spread**
(pure passthrough) at the base. A rate move revalues its held inventory with no
transaction; that gain/loss is booked to a **World-level valuation account tracked by the
BoP spine (§6)** so conservation never leaks. The dealer's net worth is **unowned** at
v20 (floats, booked for conservation, not distributed to any residents) — ownership /
distribution is a capital-layer concern (§12).

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
   **CONVERGED (§10): tradable = necessity + luxury; non-tradable anchor = housing/land
   (v15); energy & capital goods NOT tradable at the base** (energy-as-intermediate-import
   is a flagged S2 extension). Non-tradable candidates also include labor (until migration).
   *Why it dominates:*
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
is **CONVERGED (§10): proportional iceberg, uniform across pairs at the base** (N=2 has one
pair); per-pair (distance ⇒ gravity, near/large partners trade more) is deferred to S3.

**CONVERGED — trade motive: same good, Armington-differentiated by origin.** Not "same vs
distinct goods" — the resolution is a *single* good whose home and foreign varieties are
**imperfect substitutes** under a CES aggregator with finite elasticity σ. This keeps the
import-competition / comparative-advantage story (low-cost producer exports, high-cost
imports; connects v18) **while killing the perfect-substitute bang-bang** (perfect
substitutes + a friction band ⇒ demand flips discontinuously at the band edge ⇒ oscillation
that wrecks the §8 quiet baseline). σ is a calibrated parameter. The system's **emergent
product is a specialization pattern** — which economy becomes the necessity-exporter, which
the luxury-exporter — the comparative-advantage equilibrium the flows converge toward, the
headline outcome to observe.

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

### 4.5 Structural forks — now CONVERGED (see §10)

- Trade motive → **same good, Armington-differentiated by origin** (§4.2).
- Trade scope → **final goods only at base**; energy-as-intermediate (global value chains,
  the real oil shock connecting v17) is a **flagged S2 extension**, not the base.
- Network shape → **uniform proportional friction at base**; per-pair gravity at S3 (§4.2).
- Tradable partition → **necessity + luxury tradable; housing non-tradable anchor** (§4.1).

### 4.6 Meshing with the existing arcs (v15 / v17 / v18)

v20 reuses far more than it builds. The only genuinely new objects are the `World`
container, the FX dealer, and the rate vector; the trade⊗FX system otherwise **plugs into
existing machinery**. But two inherited *conclusions* must be re-validated under openness,
not assumed to carry over.

| Existing | What v20 trade⊗FX uses it for | Free win / watch |
|---|---|---|
| **v18 N/L session hierarchy** | the per-session **injection site** for trade (foreign sources added to each session's choice set; exports as extra demand) | *Free:* import competition inherits distributional meaning (necessity imports shield the poor, luxury imports hit the luxury sector). *Watch:* preserve the energy→N→L budget hierarchy (it is physical phase order) and keep injection **flag-off byte-identical**. |
| **v18 group-CPI / price-level index** | the domestic price levels `P_i` for the real exchange rate `real_ij=(e_i/e_j)(P_j/P_i)` | *Free:* the bounded level-index (built to kill the 57× compounding artifact) is exactly the right tool — no new price measure. *Watch:* which group's `P` (tradable basket vs total CPI) defines competitiveness — a §13 choice. |
| **v17 energy (intermediate input + shock)** | **intermediate-goods trade** / global value chains / the *real* oil shock (energy-as-import makes an import a production input) | *Free:* v17's κ capacity cut, only an approximation of an oil shock, becomes a true terms-of-trade/import shock. *Watch:* v18 found the closed-economy energy shock is **deflationary** (demand destruction > cost push) — **re-test under openness**; sign depends on net energy importer/exporter + pass-through of depreciation. Pre-register, don't inherit. |
| **v15 housing / land** | the **non-tradable anchor** (§4.1) that gives the real exchange rate room to move | *Free:* Balassa-Samuelson, Dutch disease, competitiveness all become possible. *Watch:* a cross-module feedback loop (import inflation → real rate → house prices → wealth effect → consumption) — a stability concern for §7 lever 2. |
| **v11.4/11.5/12.4 crisis machinery** | (§12) currency-crisis reuse under a peg | later stage, not this module |

**Two inherited conclusions to re-validate, not assume:** (1) the energy shock's
deflationary sign (v18 finding #3); (2) the energy→N→L hierarchy's semantics once foreign
sources enter the sessions. Three cross-module feedback loops to watch for stability:
import-competition→distribution, energy→supply-chain, exchange-rate→housing-wealth.

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
   equal to the dealer's `i`-inventory** — reconcile as a gate. **The dealer's cross-
   currency revaluation (a rate move re-pricing held inventory with no transaction) is
   booked to a World-level valuation account** — without it, numéraire-denominated
   conservation leaks (§3).
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

## 10. Converged decisions (one row per component)

| Component / fork | Decision | Deferred variant |
|---|---|---|
| Economies (L-level) | **L2 coupled** (§0) | — |
| N at first coupling | **N=2 for S1** (one bilateral rate, no cross-rate burden) | N=3 at S3 (cross-rate + vehicle currency) |
| Settlement medium | **fiats + rate vector** | single world money |
| Rate representation | **numéraire vector, cross-rates derived** | — |
| Basket weights `w_i` | **equal, 1/N** | economy-size weights |
| Regime | **float first** | peg (degenerate until capital, §12) |
| Dealer | **one dedicated `FXDealer`, World-level** | banks-as-dealers |
| Dealer groping | **grope on net inventory** (= mean-reversion, one rule) | — |
| Dealer P&L / ownership | **zero spread; revaluation → World valuation account; unowned** | ownership/distribution at capital layer |
| Tags | **residency + currency as first-class fields; only dealer holds FX o/n** | residents hold FX (capital layer) |
| Trade motive | **same good, Armington-differentiated by origin** (finite σ) | distinct goods / perfect substitutes |
| Trade scope | **final goods only** | energy-as-intermediate = flagged S2 |
| Tradable partition | **necessity + luxury tradable; housing non-tradable anchor** | energy/capital tradable later |
| Friction | **proportional iceberg, uniform across pairs** | per-pair gravity at S3 |
| Trade → session entry | **CES-over-origin inside each v18 session; export = mirror injection; energy→N→L order kept; flag-off byte-identical** | — |
| Real rate: trade vs report | **decisions use per-good Armington relative price; reported REER = CPI-based; tradable/non-tradable gap reported separately** (BS/Dutch disease) | — |
| Character (S2) | **minimal — vary productivity/TFP only first**; shared base config + per-economy override | multi-dim character later |
| Expectations | **static / backward-looking** (stale coupling) | forward-looking at capital layer |
| Parallelism | **serial-first BSP shape** | process pool on profiling evidence |

**Calibration targets (not structural — fit to the §8 quiet baseline):** groping speed λ,
dealer inventory scale/buffer, Armington σ, the genesis rate vector — chosen jointly so
genesis stays quiet and shocks do not oscillate (§7 lever 2).

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

## 12. Out of scope here — the full open-economy component panorama

This module delivers only the first two flows. To see what remains (and why v20 is the
right *first* slice), the whole open economy organizes under one principle: **an open
economy = what can cross a border + who sets the rules on the crossing.** "What can
cross" is a near-closed list, which gives completeness confidence. Three layers:

### Layer A — the flows (what physically crosses)

| Crosses the border | Component | Status |
|---|---|---|
| goods / services | international **trade** | ✅ this module |
| money | **FX** market | ✅ this module |
| financial claims | **international capital** (FDI / portfolio / cross-border lending) | ✗ the keystone gap |
| people (labor) | **migration** / labor mobility | ✗ |
| technology / ideas | **tech diffusion** (imitation, FDI-embodied catch-up) | ✗ (v19 TFP is *exogenous drift*, not cross-border diffusion — coordinate) |

**Capital is the keystone:** it turns a transient trade imbalance into a *persistent*
position (NFA) — mechanically, it is exactly **letting the dealer's (and residents')
inventory drift instead of mean-reverting** (§3). It unlocks the trilemma, sudden stops,
contagion, and gives Layer B and most of Layer C something to bite on.

### Layer B — the derived-income layer (current account *beyond* trade)

Emerges only once capital + people flow; conceptually distinct because it makes **current
account ≠ trade balance** and opens the **GNP ≠ GDP** wedge:

- **Factor income** — returns on foreign-held capital + migrant wages crossing borders.
- **Transfers** — remittances (need migration) + foreign aid (need governance).

### Layer C — governance / regime + strategic interaction (the rules on the flows)

The first layer where economies act with **intent** toward each other, not as mechanical
price-takers:

- **International monetary/financial governance** — the exchange-rate regime as a *system*
  (gold standard / Bretton Woods / dollar system), reserve-currency anchor, **capital
  controls**, international LoLR (IMF, swap lines), crisis resolution. *Includes:*
  - **Pegged regime** = swap the private dealer for the **central bank** as dealer of last
    resort — fixes the price, absorbs all imbalance onto FX **reserves** (its inventory).
  - **Currency crises** = peg + shock + reserve constraint → reserve depletion →
    devaluation, **reusing the bank-run / reserve-tier / LoLR machinery** (v11.4/11.5/
    12.4) — the crisis emerges, it is not tuned.
- **International trade governance** — tariffs/quotas (§4.4 placeholder), trade
  agreements, trade wars, sanctions.
- **Strategic interaction** — competitive devaluation (currency wars), beggar-thy-neighbor
  policy, coordination vs. conflict. Governance only *bites* once trade + capital flows
  are large (capital controls are moot without capital flows; trade wars moot without big
  trade).

### Cross-cutting shocks (ride whichever layer they hit)

- **Terms-of-trade / oil shocks** = shock world prices; energy-as-import (v17) turns the
  domestic capacity cut into the *real* imported-oil shock.

### Dependency ordering (the roadmap beyond v20)

1. **International capital** (keystone) — unlocks Layer B factor income, the trilemma,
   crises, and Layer C's "capital controls / IMF".
2. **Migration** (parallel) — unlocks remittances, the v18 deprivation escape valve,
   cross-border demographic transfer.
3. **Governance + strategic layer** sits on top — only meaningful once flows are large.
4. **Tech diffusion** — a side channel, coordinate with the v19 TFP line.

## 13. Residual opens (all now CALIBRATION, not structure)

Structural forks are converged in §10. What remains is calibration + one implementation
mechanism, all resolved against the §8 quiet baseline rather than by fiat:

- **Groping rule** — form settled: `log e_i += λ·(net_inventory_i/scale)`, then subtract
  `Σ_j w_j log e_j` to re-impose the gauge; fixed-id reduction (Walras: `Σ_i` imbalance
  `≡ 0` = gate #2). *Calibrate:* λ, the inventory scale, and its interaction with the
  normalization projection (the groping/normalization stability question).
- **Armington σ** — calibrate to the quiet baseline (finite, smooths the origin choice).
- **Genesis rate vector** — solve once at setup for multilateral-balanced trade (§8).
- **Session-entry implementation** — the exact CES-over-origin hook in each v18 session,
  proven flag-off byte-identical (foreign-origin weight → 0 reproduces dev). Mechanism,
  not a decision.
