# Implementation plan — v6 (capital market: equity, bubbles, and choice 乙)

> **Status: engineering plan, design not fully locked.** Economics discussed in-thread (see the
> v6 design turn). Two design points are ASSUMED here and flagged in §11 for confirmation before
> coding: (a) **single aggregate equity index** this build, per-firm equity → v6.1; (b) stock price
> forms by an **excess-demand groping rule + pro-rata rationing**, NOT a goods-market M1 instance and
> NOT a computed clearing price (no auctioneer, §0). Sequenced AFTER the MPC-heterogeneity precursor
> (§0.2) so T8 attribution stays clean.

The capital market is the highest-dependency layer (needs investment+capital ✅v2, interest ✅v3,
mature profit dynamics ✅v4). It is also the largest blast radius: it introduces asset prices,
speculation, portfolio choice, a wealth-effect demand channel, and bubbles — each coupling to every
existing mechanism. The discipline is therefore **minimal core first, stabilise, then raise the
speculation knob**. Do not chase 1929 on the first run.

---

## 0. Scope, sequencing, and what is deferred

### 0.1 What v6 delivers (aggregate-index version)
- A single traded asset: **the equity index** = a claim on total C-firm net worth. One price `p_S`.
- Households do **portfolio choice**: split wealth between deposits (safe, earns `r`) and the index
  (risky, earns dividends + capital gains).
- Price forms by **excess-demand groping** (disequilibrium, no auctioneer); trades **pro-rata
  rationed** so shares and money both conserve exactly.
- **Choice 乙 activated (aggregate form):** household wealth now includes equity market value, so
  firm net worth finally flows into household wealth → the T8 wealth-channel opens.
- **Aggregate Tobin's q** = market cap / book net worth (a metric now; q-driven investment → v6.1).
- **Bubbles** as an emergent, opt-in-via-knob phenomenon (fundamentalist/chartist demand mix).

### 0.2 Precursor step (separate, do first): MPC heterogeneity
Config-only, zero refactor (α₁,α₂ are already per-household fields, §5). Draw them from a
distribution instead of a constant. Run T8 in isolation → measure how much heterogeneity alone
moves it. **Expectation to set now:** MPC heterogeneity *widens* wealth (additive saving-rate
differences) but likely will **not** produce a heavy tail; the tail needs the multiplicative
equity-return channel v6 adds. So MPC = first cut, v6 = the heavier second cut. Keep them separate
so T8's improvement is attributable.

### 0.3 Deferred to v6.1 (explicitly out of scope here)
Per-firm equity & per-firm price discovery; **choice-② "founder gets the shares"** equity seeding;
firm-level Tobin's q → q-driven investment (replacing/【augmenting】 B5 accelerator); bonds/other
assets; endogenous `r`. All need per-firm holdings, which the aggregate index does not carry.

---

## 1. Data model (agents.py, ledger.py)

| where | change |
|---|---|
| new `EquityMarket` (agents.py) | holds market state: `price` (p_S), `float_shares` (total units, fixed unless new issuance — v6: fixed), `book_value` (Σ C-firm net worth, recomputed each tick), `trend` (adaptive momentum signal on returns), `last_price`. One object, like `Bank`. |
| `Household` | `shares: float` (units of the index held); `equity_value` derived = `shares·p_S`. New per-agent portfolio params (uniform first): `theta_equity` (target equity share of wealth), stock-demand weights inherited from cfg. |
| `Firm` | no new fields for the aggregate version (book value read from existing `capital`, ledger deposits, debt). Per-firm shares → v6.1. |
| `ledger.py` | **NO new ledger instrument.** Shares are NOT money; they live on `Household.shares` + the market. Share *purchases* are ordinary deposit `transfer`s between buyer and seller (money conserves via the existing primitive). Add nothing to the money ledger. |

**Share conservation** is a NEW invariant tracked outside the money ledger: `Σ_h shares_h == float_shares`
every tick. It gets its own gate (a cheap assert, analogous to A5 but for the equity float).

Initial allocation (aggregate, v6): `float_shares` split **equally** across households at genesis;
`book_value₀` sets `p_S₀ = book_value₀ / float_shares` (start at book, zero bubble). Founder-gets-shares
seeding is v6.1 (needs per-firm).

---

## 2. The asset-market primitive (the one genuinely new mechanism)

A new interface function, `clear_equity_market(market, households, ledger, cfg)`, run once per tick.
It is **not** M1 (posted-price rationing) and **not** a computed clearing price. It gropes:

```
# 1. signals (market-level, shared by all households)
book   = Σ C-firm net worth              # (D_f - L_f + capital_f), recomputed
value  = smoothed_dividend / r           # fundamental (Gordon, g=0); r reused from v3
trend  = adaptive avg of recent index returns   # reuse the B2/λ adaptation form, on p_S

# 2. each household's DESIRED holding at the current price p_S (notional)
#    demand pressure = w_f·(value - p_S)/p_S   (fundamentalist, stabilising)
#              + w_c·trend                       (chartist, destabilising  <- the bubble knob)
#    target equity value = theta_equity · wealth_h · clip(1 + demand_pressure, 0, cap)
#    desired Δshares_h = target_equity_value/p_S - shares_h,  budget-capped by deposits_h

# 3. reconcile to a fixed float (both sides can't net-buy): pro-rata ration the LONG side
desired_buy  = Σ max(0, Δshares_h);  desired_sell = Σ max(0, -Δshares_h)
executed     = min(desired_buy, desired_sell)          # short side sets volume
scale buys (or sells) pro-rata so Σ executed Δshares == 0  # shares conserve exactly

# 4. settle: for each executed trade, transfer  |Δshares|·p_S  deposits seller<-buyer (ledger.transfer)
#    update shares_h.  MONEY conserves (transfers), SHARES conserve (Σ Δ = 0).

# 5. grope the price for NEXT tick from the UNMET pressure (disequilibrium, no clearing assumed)
excess = (desired_buy - desired_sell) / float_shares
market.last_price = p_S
market.price = p_S · (1 + lambda_p · clip(excess, -cap, cap))     # market impact
market.trend += trend_lambda · (return_t - market.trend)          # adaptive momentum update
```

Properties bought: (i) no auctioneer — price never assumed to clear, it gropes; (ii) both
conservations exact (money by transfer, shares by pro-rata); (iii) `w_c` is the single bubble knob
(0 ⇒ price tracks fundamental; large ⇒ self-reinforcing runs); (iv) reuses the adaptive-expectation
machinery (trend = B2 form on returns).

---

## 3. Household behavior (behavior.py)

One new decision function `plan_equity_demand(hh, market, r, cfg) -> desired_Δshares` implementing
step 2 above (pure function of frozen state, like every other B-rule). Portfolio target uses total
wealth `W_h = deposits_h + shares_h·p_S`. Homogeneous weights first (`w_f, w_c, theta_equity` from
cfg); per-household heterogeneity is a later config change (fields already per-agent).

**Wealth-effect coupling (the blast radius):** B1's consumption already reads `α₂·wealth`. Under 乙,
`wealth` gains the equity term. **Mitigation baked into the plan:** B1 consumes out of a *smoothed*
equity value (a slow-moving `equity_value_ema`), NOT the raw bubble-prone market cap, so a price spike
doesn't instantly detonate real demand. `α₂` and the equity-smoothing speed are the throttles.

---

## 4. The v6 tick (delta from the v4/v5 tick)

Add ONE new phase, after dividends are settled (households know their income + the market knows
profits/dividends), before end-of-tick metrics:

```
... Phase 4 settlement (revenue, wages, dividends) ...
... Phase 4.5 debt service, Phase 4.7 demographics (v3/v4) ...
NEW Phase 4.9  equity market:
      recompute book & fundamental; plan_equity_demand for all households;
      clear_equity_market (ration + settle + grope price); update trend.
Phase 5  metrics (now incl. price, market cap, bubble gap, equity wealth).
```

Placement rationale: portfolio choice is a reallocation of *end-of-tick* wealth, so it runs after all
income/dividend flows are known. It touches only deposits (via transfer) and `shares`/`price` — no
production or labor coupling within the tick, keeping the change localized.

---

## 5. Conservation & accounting

- **A5 (money) UNCHANGED.** ΣD−ΣL=M still holds to machine precision; equity trades are deposit
  transfers, equity is not money. This is a hard regression: the existing A5 gate must stay green.
- **New gate — share conservation:** `Σ_h shares_h == float_shares` (fixed float in v6).
- **Wealth accounting (new, reported not gated):** `W_h = deposits_h + shares_h·p_S`;
  `total_wealth = M + Σ capital` at book, plus the bubble phantom at market.
- **Bubble metric (the payoff):** `bubble = market_cap − book_value = float·p_S − Σ net_worth`. This
  is a non-monetary valuation phantom: it can inflate and collapse while **A5 never moves**. The
  headline invariant test: run a boom→crash and assert money conservation holds *through the crash*.

---

## 6. Config (parameter budget, per §0-iv)

| param | role | status |
|---|---|---|
| `capital_market: bool = False` | master switch; off ⇒ v5 bit-identical | structural |
| `lambda_p` | price groping / market-impact speed | FREE (stability) |
| `w_fundamental = 1.0` | fundamentalist demand weight | anchored (normalize) |
| `w_chartist` | **the bubble knob** (0 ⇒ near-fundamental) | FREE (core v6 dial) |
| `theta_equity` | target equity share of household wealth | FREE |
| `trend_lambda` | adaptive momentum speed (reuses λ form) | anchored (like λ_d) |
| `equity_ema_lambda` | consumption's equity-wealth smoothing (blast-radius throttle) | FREE (stability) |
| fundamental discount | = `r` (reused from v3) | — |

`Config.v6()` = v4 + `capital_market=True`, `w_chartist` **small** (near-fundamental, stable first
run), `theta_equity` modest. A separate `Config.v6_bubble()` raises `w_chartist` to summon bubbles
once the core is trusted.

---

## 7. Metrics & diagnostics

New series (metrics.py): `stock_price`, `market_cap`, `book_value`, `bubble_gap`, `tobin_q`
(=market_cap/book), `equity_wealth_share` (equity / total household wealth), `hh_wealth_gini` (now
computed on `deposits + equity`), `turnover` (executed volume / float), `equity_demand_pressure`.
New `plot_dashboard_v6` (diagnostics.py): price vs book overlay, bubble gap, wealth-with-equity Gini,
turnover, q. Reuse the existing dashboard scaffolding.

---

## 8. Tests (tests/test_v6_capital_market.py)

1. **Regression** — `capital_market=False` ⇒ bit-identical to v5 (existing 57 tests stay green).
2. **Share conservation** — `Σ shares == float` every tick, through many ticks.
3. **Money A5 survives trading** — A5 drift < 1e-6 with the market active, INCLUDING through a
   deliberately induced crash (high `w_chartist` boom→bust).
4. **乙 opens the wealth channel** — with the market on, household wealth includes a nonzero,
   varying equity component; `hh_wealth_gini(incl. equity)` > `hh_wealth_gini(deposits only)`.
5. **Fundamental limit** — `w_chartist=0` ⇒ price tracks fundamental (|price−value|/value stays
   small); no runaway.
6. **Bubble is reachable** — large `w_chartist` ⇒ price detaches from book (bubble_gap > 0 for a
   sustained window) AND money conservation still holds (ties 3+6: a wealth crash with zero money
   destroyed — the clean SFC result).
7. **Boundedness** — at the `Config.v6()` defaults the system stays bounded (no NaN/inf, price > 0).

## 9. Milestone / acceptance (conservative)

Done = (1) regression green; (2) both conservations exact (money A5 + share float) through trading
and a crash; (3) household wealth genuinely includes a fluctuating equity part and T8 moves in the
right direction; (4) stable & bounded at low `w_chartist`, price anchored to fundamental. **Bonus /
observation targets (not required to pass):** a bubble+crash at high `w_chartist`; a visible
wealth-effect on consumption; aggregate Tobin's q that co-moves with investment. Full financial
crisis (bubble → margin/insolvency → bank stress, the 1929/2008 chain) is a v6.1+ target.

## 10. Blast-radius controls (explicit)

Default `capital_market=False`; `w_chartist` small by default; consumption reacts to *smoothed*
equity wealth; price groping `lambda_p` capped; a hard price floor > 0. First runs at low speculation;
raise `w_chartist` only after the core is regression-green and bounded.

## 11. Open decisions to confirm before coding

1. **Aggregate index (v6) vs per-firm equity (v6.1)** — recommend aggregate first (this plan). If you
   want per-firm from the start (for ②founder-gets-shares + firm-level q), the data model in §1 and
   the primitive in §2 both change materially (O(N_H·N_F), N prices).
2. **Excess-demand groping + pro-rata rationing** (§2) as the price mechanism — confirm we reject both
   the M1-instance framing and any computed clearing price (no auctioneer).
3. **Initial equity allocation** — equal split at genesis (aggregate). Founder-seeding deferred with
   per-firm.
4. **Sequencing** — MPC heterogeneity precursor runs and is measured on T8 *before* v6 starts.
