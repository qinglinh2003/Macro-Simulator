# V15 Housing Plan — Dwellings as an Asset Class

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce housing as the economy's second household asset class. A dwelling is
NOT a good: its CONSTRUCTION is a capital good (GDP), its SERVICE FLOW is a consumption
good (GDP), the DWELLING ITSELF is an asset (registry + balance sheet, resale is a
net-worth-conserving swap, never GDP). Modeling the bundle as one "good" would book
resales as consumption and break the A5 semantics — the three-way split is how national
accounts draw the line, and we draw it in the same place.

**Why housing (ranked by leverage on standing open threads):**
1. Bank survival — mortgages are the missing long-duration collateralized book (both
   v13 bank extinctions trace to a short-duration, high-beta asset mix).
2. Monetary transmission — policy rate → mortgage burden → household sector; the Taylor
   rule finally bites households, not just firm credit.
3. The demographic layer gets its demand object — leaving home, marriage, death are all
   housing events; population structure becomes real demand.
4. Wealth structure — housing is the middle-class asset; reshapes the SHAPE of the
   gini (currently 0.93, purely equity-driven top concentration).
5. Endogenous credit-house-price cycles — the classic financial-accelerator engine.

**Sequencing:** v15 starts AFTER Phase 3 (3.1–3.3) completes. The stratification gauges
(Phase 3.0, shipped) will then measure how housing reshapes wealth stratification.

## Global Constraints

- **The v13 estate lesson is architectural here**: every estate bug family came from an
  asset class missing from death settlement. Housing enters the person-claim identity
  and the estate liquidation path in v15.0, BEFORE any market exists.
- Every transaction is ATOMIC: ledger transfer + registry title change + person-claim
  postings in one function; claim-identity hard gate asserts after every market session.
- Price revaluation touches NO ledger entry (like equity marks): A4/A5 are blind to
  house prices by construction.
- Registry invariants asserted per tick: every dwelling has exactly one owner; dwelling
  count is conserved until construction (v15.4) explicitly mints new ones.
- Each stage is flag-gated, default off, bit-identical to v14 when off (cumulative
  same-seed smoke discipline vs the pre-feedback baseline).
- Every consumer of the house-price signal inherits BURN-IN DISCARD semantics
  (macro_signal lesson): the housing market has its own genesis relaxation and no
  downstream channel may smooth it into a baseline.
- Heterogeneity red lines: NO quality dimension in v15 (observationally equivalent to
  size until quality has its own dynamics — filtering/renovation is a future v16
  module); NO location (single region). Size is the only sanctioned axis, behind a
  data-driven gate (below).
- Thin-market realism: housing acceptance runs need >= 1k households; diagnostics lean
  on time-on-market / forced-sale share / listing stock, which are more stable than the
  price index at low volume.

---

## v15.0 — Registry & Genesis (stock integrity before flows)

Goal: dwellings exist, are owned, are valued (frozen), and flow through death — with
zero market and zero dynamics change.

Components:

- `HousingRegistry`: dwelling id → owner account; parallel to `h.holdings` in every
  valuation surface (net worth, claim targets `__housing__`, estate inventory).
- Genesis: ONE homogeneous dwelling (≡ 1 housing unit) per genesis household, 100%
  owner-occupied, no mortgage. Newly formed households (leaving home / marriage) start
  houseless — they are the emergent buyers/renters later, not a pathology now (housing
  is a pure asset until v15.3; houseless only means one less balance-sheet item).
- Frozen valuation: price anchor ≈ 3–4x annual household income (arbitrary genesis
  posting, relaxes later like p_firm0).
- Estate path: deceased owners' dwellings enter the estate inventory; with no market
  yet, title transfers to heirs in kind at frozen valuation (probate-sale listing
  replaces this in v15.1).
- Wealth tax: housing EXEMPT initially (real-world precedent; avoids a fiscal base
  jump). "Housing into the wealth-tax base" becomes an explicit policy experiment.

Acceptance:

- [ ] Flag off => bit-identical; flag on => only new observation columns move.
- [ ] Estate probe: death→inheritance→escheat full path with dwellings, claim
      identities hold (10k-scale tolerant-assert probe, v13 runner reused).
- [ ] Registry invariants (single owner, conserved count) hard-gated per tick.

## v15.1 — Resale Market (the secondary market IS the housing market)

Secondary before primary: ~85–90% of real transactions are existing homes, and five
agreed mechanisms hard-depend on resale (probate sales, foreclosure disposal, landlord
entry, divorce settlement, price discovery itself). Construction (primary) waits until
v15.4 — without a resale price there is no signal to build against.

Transaction dynamics (posted-price + inventory-pressure, the model's native market
grammar):

- LISTING INFLOW, staged: forced first — probate sales (estates list until sold, under
  the probate-window discipline), divorce settlements, liquidity distress (deposits
  below consumption floor). Voluntary motives arrive with later stages (yield v15.3,
  fit v15.3+). v15.1 volume ≈ homeowner death flow absorbed by young buyers: thin and
  honest. The involuntary flow is the thin market's price-discovery floor.
- LISTING BOOK: ask = reference (transaction index, hold-last) × markup; unsold =>
  ask decays per session (the firm's unsold-inventory price cut, transplanted);
  foreclosure listings (v15.2) start discounted and decay faster.
- MATCHING SESSION every 30 ticks (the marriage-market cadence precedent): buyers =
  houseless households with capacity, random order; search friction — each buyer sees
  only the k cheapest listings (cheapest-first quote pattern); buys the cheapest
  affordable one at ask. Budget cap v15.1 = deposits × (1 − buffer); v15.2 adds
  down-payment + LTV capacity.
- NO transaction fees in v1 (fees are a money sink needing an A5 destination); a
  transfer tax → fiscal is a later explicit policy handle (stamp-duty experiments).
- DOCUMENTED BEHAVIORAL PRIMITIVE: "houseless households with liquidity seek to own"
  is a rule (like B1 consumption), grounded in the service flow only at v15.3.
- Price index: session transaction-weighted, hold-last; burn-in discard downstream.
- NO extrapolative-expectation term in asks or bids: speculation is a separate flag
  (default off) — bubbles must be a switchable experiment, never an implicit default.

What lands here for free: mark-to-market housing wealth flows into net worth, the
Phase 3 rank snapshot, and claim targets — house-price PAPER volatility is born here.
Its macro teeth (collateral, default) wait for v15.2 — giving the clean regime pair
"volatility without leverage vs volatility with leverage" for cycle attribution.
Expected regime: with prices at 3–4x income and no credit, v15.1 is a CASH-CONSTRAINED
market (few buyers, buyer's market, low volume) — documented as the reference regime
that v15.2's credit unlock gets compared against.

Acceptance:

- [ ] Atomicity + registry invariants + claim gate through market sessions.
- [ ] Price discovery survives thinness (TOM / forced-share / listing stock as primary
      gauges; index with hold-last never NaNs).
- [ ] Transaction volume correlates with demographic event flow (deaths, divorces,
      household formation) — the flow IS demographic by construction.
- [ ] First-buyer wealth composition shift visible (deposits→housing swap; consumption
      contracts via the alpha2 deposit term — the "down-payment effect" emerges from
      the existing consumption rule, zero new code).

## v15.2 — Mortgages (volatility grows teeth; the bank-survival test)

> **Implementation notes (2026-07-12 night session — why v15.2 was deliberately NOT
> started overnight, and how to start it):** household ledger debt is SHARED between
> margin loans and any future mortgage, and the v13 margin-shadow drift family was
> born exactly at "a write_off cleared the ledger while a shadow stayed". A mortgage
> book therefore needs its own shadow discipline from the first line:
> `MortgageLoan(household, dwelling_id, balance, rate)` book on the bank/bridge, with
> EVERY ledger op that can touch household debt (repay / write_off / transfer_debt in
> merge sweeps, divorce splits, death settlement) mirrored into the book the way
> `_clamp_margin_debt_shadow` / `_move_margin_debt_shadow` do it -- and an every-tick
> identity gate: sum(margin shadow + mortgage book) == ledger debt per household.
> Servicing wants its own step in run_debt_service_phase (households currently only
> service margin via the equity phase). Origination changes the buyer budget to
> down-payment + LTV*price and books loan-creates-deposit through the ledger's
> create_loan. Foreclosure = seize title -> forced listing at discount -> writedown
> with the book mirrored. None of this is hard, but ALL of it is fault-line work that
> deserves a fresh session with the estate probe green, not a 3am patch.

- FLOATING RATE first (reprices with the policy rate: fastest transmission, no
  refinancing machinery). Fixed-rate + refinancing + lock-in is a later flag.
- LTV cap (live macroprudential policy handle from day one), amortizing schedule,
  underwater default => foreclosure => bank-owned listing => discounted disposal =>
  fire-sale supply pressing prices — the financial accelerator closes here.
- Genesis book: START FROM ZERO (mechanism acceptance uses pinned/amplified scenarios,
  not a mature book). DECISION GATE at stage end: measure the book's maturation
  timescale; if research runs need a steady-state cross-section, add the synthetic
  genesis book flag — (purchase-age distribution × years-elapsed amortization), with
  a DEDICATED conservation-gate validation (genesis loans are debt without a spendable
  deposit twin; the bank balance sheet must be squared explicitly).
- Stress scenarios: default waves; the DOUBLE-CRASH test (equity and housing marked
  down together — both books share the bank balance sheet).

Acceptance:

- [ ] Credit unlock regime shift vs v15.1 (volume and price level up) — the natural
      experiment "credit availability unlocks the market".
- [ ] Foreclosure conserves through A4 (collateral disposal never overdrafts).
- [ ] Bank book duration/collateralization gauges; the bank-survival question gets its
      honest answer here (the v13 extinctions are the reference pathology).
- [ ] SIZE GATE (end of stage): per-quintile housing wealth shares from the Phase 3
      gauges — if multi-dwelling holding already gives distributional spread, stay
      homogeneous; if housing wealth is too flat, activate the size scalar:
      one field s per dwelling (set at construction/genesis), service ∝ s, trades
      remain whole-dwelling, market still discovers ONE per-unit price. Genesis sizes
      then ∝ household need_units (mean 1) — fitted at t0, so reallocation demand comes
      from demographic CHANGE, not from seeded mismatch (no artificial opening wave).
      Never wealth-proportional (stratification must emerge).

## v15.3 — Rental Market & Tenure Choice

- Housing services enter consumption (imputed rent for owner-occupiers, cash rent to
  landlord households); rent market clears between owner households with spare
  dwellings and houseless households.
- Landlords EMERGE: households buy additional dwellings when rental yield beats the
  deposit rate + premium — housing joins the asset menu and closes the arbitrage
  triangle (deposits / equity / housing).
- The two demand faces become measurable: need-driven (demographic, price-inelastic)
  vs investment (yield-driven, elastic); their mix is a standing cycle-amplitude gauge.

- [ ] Rent-to-price ratio in a sane band; tenure split emerges (poor rent, rich hold);
      landlord concentration measured by the stratification gauges.

## v15.4 — Construction (primary market, long-run anchor)

- Builder sector on the K-firm pattern (labor + capital => new dwellings into the
  registry); construction is GDP.
- LONG-RUN PRICE ANCHOR decision (must be settled before this stage, ideally at 15.1
  design time): convex construction cost in the aggregate stock (scarcity => secular
  real appreciation is possible) + PERMIT QUOTA as a zoning policy handle. Without
  scarcity, marginal-cost pricing pins the long-run price to construction cost and
  housing cannot appreciate — the "middle-class asset" motivation dies.

- [ ] Supply elasticity calibrated against demand signals; stock growth cointegrates
      with household count; dwelling-count invariant updated to "minted by builders
      only".

## v15.5 — Couplings & Policy Handles (one at a time, Phase 2 acceptance paradigm)

Each its own flag, each with the frozen-reference/paired-run acceptance:

- Leaving-home / marriage read housing availability (the affordability buffer ALREADY
  exists: unaffordable housing => delayed leaving home => cohabitation — the model's
  existing lifecycle machinery is the safety valve; no homelessness pathology).
- Affordability => fertility (channel 2.1d: the p_house/income input the original
  Phase 2 table wanted, now with a real object behind it; burn-in discard inherited).
- Consumption wealth effect from housing (default OFF, empirically much weaker than
  financial wealth; the honest default is the down-payment effect already emergent).
- Policy handles: property tax / transfer tax (stamp duty) / LTV macroprudential /
  housing-into-wealth-tax-base / permit quota. Elderly downsizing as optional
  lifecycle behavior.

---

## Standing decision log (agreed in design review, 2026-07-11)

| Decision | Ruling |
|---|---|
| Housing as a good? | No — asset + service good + construction good (three-way split) |
| Heterogeneity | Size scalar only, behind the v15.2-end gate; quality deferred to a future filtering module (needs its own dynamics); location deferred to multi-region |
| Secondary market | It IS v15.1; primary (construction) waits until v15.4 |
| Genesis | 1 homogeneous dwelling per household, 100% owned, no mortgage; new households houseless; anchor 3–4x income; synthetic mortgage book behind a gate; wealth-tax exemption initially |
| Volatility landing | Paper in v15.1; teeth (collateral/default/bank capital) in v15.2; consumption wealth effect gated in v15.5 |
| Mortgage form | Floating first; fixed+refi later flag |
| Speculation | Separate flag, default off — bubbles are an experiment, not a default |
| Fees | None in v1; transfer tax as a later fiscal policy handle |
