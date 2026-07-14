# V21 International Capital Plan — the financial account (the keystone deferred from v20)

> **STATUS: IMPLEMENTED — v21.0–v21.2 built/tested/committed on `feat/capital-v21`
> (forked from v20@78ce471).** v21 adds Layer A's third flow — **financial claims across
> borders**. Reuses the v20 machinery whole; capital = persistent yield-driven positions.
> 7 v21 tests + 18 v20 tests green (capital off ⇒ v20 exactly). Diagnostics v211/v212.
>
> **What landed:** v21.1 (`world/capital.py`) — portfolio-balance target `target_i =
> mobility·(rate_i−r_mean)·M_i`; capital finances a persistent deficit toward it; rate
> gropes toward the capital-sustained position; **high-rate economy = net DEBTOR, pays
> factor income (GNP<GDP wedge, a gauge)** — the carry pattern (commit a671913). v21.2 —
> **peg regime**: the CB freezes the rate + absorbs onto reserves; open capital + an
> independent policy rate drains reserves to zero ⇒ **peg breaks + devaluation (currency
> crisis)**; a matched rate is sustainable but surrenders monetary autonomy — **the
> impossible trinity, emergent** (commit 180fae6).
>
> **Honest simplifications (documented, non-blocking):** factor income is a GAUGE (its
> money flow compounds and destabilises the NFA dynamics — deferred); the NFA sign is
> robust only at sufficient capital mobility (trade noise dominates at low mobility); the
> devaluation is a pent-up-pressure release, not a full re-clearing. Sudden-stop as a
> confidence *shock* (vs the standing rate mismatch here) is a natural next scenario.

## 0. The seam from v20 (why capital is exactly one relaxation)

v20's `settle_trade` gropes the rate to push the dealer's net inventory toward zero — so
**trade balances per economy** (no capital account, no persistent imbalance). Two v20
findings pointed straight here: (#1) the pure-trade layer is "too quiet" *because* nothing
finances a persistent deficit; (#5) the multilateral BoP stock already carries valuation
effects. **The capital account = relax the mean-reversion.** A persistent dealer position
in currency i IS a foreign claim on economy i — economy i's negative net foreign asset
position. Once that position is allowed to persist and to EARN the domestic interest rate,
it becomes a genuine cross-border financial holding, and its flow is driven by yield.

## 1. What v21 adds (objects)

1. **Interest-bearing cross-border positions.** The dealer's held foreign-currency
   inventory earns that currency's deposit/policy rate: economy i's banking system pays
   the dealer interest on the i-money it holds (a `transfer` inside economy i's ledger —
   conserving). This is the yield that motivates holding foreign assets.
2. **Yield-driven capital flows.** Capital flows toward the higher-return currency
   (interest differential + expected appreciation = uncovered interest parity, UIP). A
   persistent inflow to economy i finances its trade deficit — the rate no longer must
   fully clear trade each tick.
3. **NFA / IIP stock.** Each economy's net foreign asset position = foreign holdings of
   its claims − its holdings of foreign claims (= the dealer's position by currency at
   this first cut). The stock the flows accumulate into.
4. **Factor income (Layer B emerges).** The cross-border interest payments are the
   current account's primary-income line — the **GNP ≠ GDP wedge**. A debtor economy pays
   interest abroad (GNP < GDP); a creditor earns it. This falls out of (1) for free.
5. **The financial account of the BoP.** Capital flow = the counterpart to the current
   account: **CA + KA = Δreserves**; with a float and the dealer as residual, CA + KA ≡ 0.

## 2. The load-bearing lever (and the risk)

The **capital mobility × interest sensitivity** knob: how strongly capital chases the rate
differential. High mobility ⇒ UIP binds tightly, the trilemma is sharp, flows are volatile
(sudden-stop-prone). Low mobility ⇒ near-autarkic finance. This is v21's analog of v20's
groping-speed lever, and it carries the same stability risk: the interest→flow→rate→
competitiveness→trade→rate feedback can oscillate (dampened by the same frictions).

## 3. Payoffs (what capital unlocks — the "exciting" open economy)

- **Uncovered interest parity** — high-rate currencies expected to depreciate; the carry.
- **The trilemma / impossible trinity** — fixed rate + open capital ⇒ the CB loses
  monetary autonomy (its Taylor rule collides with the peg; defending the peg drains
  reserves). The headline experiment.
- **Sudden stops / capital flight / currency crises** — a confidence shock reverses the
  flow; under a peg, reserves deplete → devaluation, **reusing the bank-run / reserve-tier
  / LoLR machinery** (v11.4/11.5/12.4) — the crisis emerges, not tuned.
- **Twin deficits, global imbalances, the valuation channel** (v20 finding #5 formalized).

## 4. Staging

- **v21.0** — this plan.
- **v21.1** — interest-bearing cross-border positions + relaxed (yield-driven) mean-
  reversion + NFA gauges + factor income (GNP/GDP wedge). Float only. Gate: **capital flag
  off ⇒ dealer mean-reverts exactly as v20 ⇒ bit-identical to v20**; conservation
  (per-economy ledger + cross-border interest flows); CA + KA ≡ 0.
- **v21.2** — the trilemma: the pegged regime (CB as dealer, reserves as inventory) + open
  capital ⇒ lost monetary autonomy; sudden-stop / currency-crisis scenario reusing the
  bank-run machinery. Diagnostic: the impossible-trinity portrait.

Each stage: flag-gated, per-stage tests, cumulative bit-identity (off ≡ v20), diagnostic.

## 5. Determinism & discipline (inherited)

Fixed economy-id reduction order; per-economy RNG; capital flag off ⇒ v20 byte-identical;
the financial-account identity as a hard gate alongside per-currency conservation.
