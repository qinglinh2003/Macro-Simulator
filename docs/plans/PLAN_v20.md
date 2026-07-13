# V20 Open Economy Plan — Fiat, Foreign Exchange & Coupled Multi-Economy Trade

> **STATUS: DRAFT — DESIGN ONLY, NOT STARTED (2026-07-13).** This document records the
> money+FX module design converged in discussion. No code yet. **S0 (the `World`
> container + instantiable `Economy`) is BLOCKED on coordinating object boundaries with
> the v19 arc** (`feat/tech-tfp-v19` = technical object refactor + exogenous TFP drift),
> which is very likely delivering exactly the instantiable-`Economy` refactor this needs.
> Do NOT build a second parallel object model — see §S0/v19 boundary.
>
> **Scope of THIS plan:** fiat money + foreign exchange + the minimal trade that gives FX
> something to clear, under a **fully-coupled multi-economy (L2)** target. Capital
> account, pegged regimes, currency crises, and migration are named but **OUT of scope
> here** (they all grow from one seam — see §11 TODO).
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
   claim sits. (Capital account = later, when inventory is allowed to *drift* — §11.)
4. **The exchange rate is a groping price, not a Walrasian jump.** Frictionless instant
   clearing is the pathology this model has paid for twice (labor v16, capital v18); the
   dealer's inventory is the buffer that lets the rate grope.

## 2. Exchange-rate representation — numéraire vector, cross-rates derived

Do NOT track N(N−1)/2 bilateral rates and police consistency. Represent **N rates
against an abstract world numéraire**: `e_i` = units of currency `i` per numéraire unit.

- Bilateral rate `i↔j = e_i / e_j`; **all cross-rates derive from the single vector `e`
  ⇒ triangular no-arbitrage holds by construction.**
- Groping/clearing act only on the **N−1 independent `e_i`** (one numéraire anchor).
- The numéraire is a *representation* choice; it does **not** prevent one currency
  behaviorally *emerging* as the settlement/vehicle currency (an N≥3 phenomenon, later).

## 3. The FX dealer — a World-level object

The dealer is the ONE object that sees all economies, so it lives in the **`World`/
coupling layer**, not inside any single `Economy` (this is also where the BSP barrier
lives — §4). It holds a deposit account in each of the N banking systems, quotes the
rate vector `e`, and absorbs residual flow imbalance into inventory.

**Inventory semantics = the trade/capital boundary (refined):**
- **Pure-trade layer (this plan):** dealer inventory **mean-reverts to zero** — the rate
  gropes in the direction that pushes inventory back to zero. Foreign positions are
  *transient buffers*; trade balances over the groping horizon, **not** every tick.
- **Capital-account layer (§11):** inventory (and residents) may **drift** into a
  persistent, *chosen* asset position driven by yield, not just residual buffering.

(This supersedes the earlier "force conversion within the tick" framing — that was the
Walrasian version. Under groping, the honest statement is *mean-reverting inventory*.)

Start with **one dedicated `FXDealer`** (simplest); banks-as-dealers (more realistic
correspondent picture) is a later refinement.

## 4. The tick — Bulk Synchronous Parallel (BSP)

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

## 5. Accounting keystone — four hard gates

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

## 6. Load-bearing levers — two, the second is L2-specific

1. **Iceberg trade friction** — sets the *degree of integration*. Frictionless ⇒ law of
   one price ⇒ prices equalize instantly ⇒ the border loses meaning (degenerate). This is
   the FX-layer analog of search friction (v16) and retool friction (v18.5).
2. **Groping speed × dealer inventory-buffer size (jointly)** — sets the **stability of
   the coupled system**. Too fast / buffer too small ⇒ oscillation (the feedback-
   instability risk). Too slow ⇒ rates lag fundamentals, imbalances persist. This pair is
   calibrated against the quiet multi-economy baseline (§7).

## 7. Genesis / quiet baseline (L2)

At genesis, all N economies are in a **balanced** state: trade balances *multilaterally*
at the initial rate vector, rates are flat, no economy accumulates. With the flag on but
nothing pushing, the coupled system must **stay quiet** (rates flat, trade balanced). If
it drifts at genesis, the calibration is wrong. Only *then* perturb one economy's
character and watch divergence. (Standard project discipline: quiet baseline first.)

## 8. Determinism checklist (non-negotiable under bit-identity)

- **Fixed reduction order** across economies (sort by id before summing — float addition
  is non-associative; nondeterministic arrival order → different bits).
- **Per-economy independent, deterministically-seeded RNG** (results must not depend on
  scheduling).
- **Fixed coupling cadence** — every tick to start (correctness first); relax to every
  `K` ticks (fixed `K`, *not* data-dependent "sync when necessary", which would break
  reproducibility) only if profiling demands. The FX friction we need for stability
  conveniently also makes slow-moving coupling variables safe to exchange every `K`.
- Dealer updates also run in fixed order.

## 9. Design forks — settled positions

| Fork | Options | Decision |
|---|---|---|
| Economies | SOE stub / L1 parallel / **L2 coupled** | **L2** (user ruling §0) |
| Settlement medium | single world money / **fiats + rates** | fiats + rate vector |
| Rate representation | bilateral matrix / **numéraire vector** | numéraire vector, cross-rates derived |
| Regime | **float first** / peg | float; peg is degenerate until capital flows exist (§11) |
| Dealer | **dedicated FXDealer** / banks | dedicated first; banks later |
| Trade motive | **same goods, diff productivity** / distinct goods | same goods (import competition, connects v18); distinct-goods later |
| Parallelism | **serial-first BSP shape** / process pool now | serial-first; parallelize on profiling evidence |

## 10. Staging (L2 is the target; still built in layers)

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

## 11. Out of scope here — the one seam everything grows from

All of the following grow from **letting the dealer's (and residents') inventory drift
persistently instead of mean-reverting** — i.e. the capital account:

- **Capital account / capital flows** (yield-driven persistent positions) → NFA,
  covered/uncovered interest parity, the impossible trinity.
- **Pegged regime** = swap the private dealer for the **central bank** as dealer of last
  resort: fixes the price, absorbs all imbalance onto FX **reserves** (its inventory).
- **Currency crises** = a peg + a shock + the reserve constraint → reserve depletion →
  devaluation, **reusing the existing bank-run / reserve-tier / LoLR machinery** (v11.4/
  v11.5/v12.4) — the crisis emerges, it is not tuned.
- **Terms-of-trade / oil shocks** = shock RoW world prices; energy-as-import turns v17's
  domestic capacity cut into the real imported-oil shock.
- **Migration** = the deprivation escape valve v18 flagged as missing in a closed economy
  (deprived households emigrate instead of lingering out-of-domain) + foreign labor.

## 12. Open drill-downs (next design sessions)

- The exact `e_i` groping rule (functional form, speed parameter, inventory-feedback term).
- Iceberg friction parameterization (per-unit vs proportional; per-pair vs uniform).
- Which existing goods are tradable, and how export demand / import supply enter the
  goods session without disturbing its flag-off byte-identity.
- Whether the FXDealer is dedicated or the banks collectively (correspondent picture).
