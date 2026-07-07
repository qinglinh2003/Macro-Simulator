## 13. v4 — Firm entry/exit and bankruptcy (endogenous firm demographics)

The cross-cutting mechanism the last three findings converged on: it clears the v3 zombie-freeze
(unfreezing credit), and — via profit-driven entry — puts a **negative feedback on excess profit**.
It also, unavoidably, implements **default** (the bad-debt writeoff), which was going to be v3.5:
an insolvent firm's exit *is* a default. Scope in v1: **C-firms only** (the sector with the
concentration and the zombies). Built on v3 (needs the bank to absorb bad debt).

### 13.1 Two endogenous forces, both anchored (not fiat)

- **Exit = sustained financial insolvency.** A C-firm with financial net worth `D − L < 0` for
  `bankrupt_persist` consecutive ticks goes bankrupt. Uses the *financial* NW (consistent with B7;
  no capital valuation), and the persistence requirement doubles as **zombie cleanup** (a
  persistently insolvent firm is exactly a zombie).
- **Entry = profit above the interest rate.** When profitable incumbents earn a return
  (`profit/capital`, median over profitable C-firms) above the hurdle `r` (the interest rate = the
  economy's cost of capital / normal-profit line), new firms enter at a damped, capped rate
  (`entry_beta`, `entry_max`). This is the "excess profit competed away" mechanism; `r` reuses an
  existing parameter (no new hurdle dial) and previews monetary transmission (higher r ⇒ higher
  entry hurdle ⇒ less entry ⇒ more concentration).

Entry responds to profit, exit to solvency, so **firm count is emergent** — a dynamic balance, not
a fiat constant. The two forces are the pair the competitive ideal rests on ("enter where there's
profit, exit when insolvent"), each anchored in a meaningful quantity (r, net worth).

### 13.2 Bad-debt writeoff — the A5-conserving default (the crux)

An insolvent firm owes Λ it cannot pay; that money was long since spent into households. Cancelling
the debt alone would raise net worth by Λ (A5 break). The conserving primitive:
$$\texttt{write\_off}(borrower, bank, \Lambda):\quad L_{borrower}\!-\!=\!\Lambda \ \text{ and } \ D_{bank}\!-\!=\!\Lambda \ \text{(together)}.$$
$\sum L$ falls by Λ (net worth $+\Lambda$) and $\sum D$ falls by Λ at the bank (net worth $-\Lambda$)
⇒ **A5 invariant.** Economics: the created money stays in households (broad money unchanged); the
**bank's equity absorbs the loss.** A default is a net-worth *redistribution* bank→households,
conserved exactly. Bankruptcy sequence, all A5-safe: repay what cash allows → write off the rest →
scrap capital (real, not money) → remove the firm. Entry is **household-funded** (a transfer, so
conserved) with minimal initial capital created from nothing (capital is a real, non-conserved
asset, like genesis — no A5 effect).

**The bank needs capital.** Its equity (≈ its deposits) absorbs writeoffs; it gets a genesis buffer
`bank_capital_frac · M`. When that is exhausted the bank goes **insolvent** (deposits negative) — a
*systemic* crisis with one bank — which we **allow and observe** (the bank account is exempt from
the A4 non-negativity gate), not halt.

### 13.3 Findings (round 3) — demographics clear zombies but not monopoly

v4 does exactly what it was for, and confirms the honest prediction:

- **A5 holds** through births, deaths, and writeoffs (drift ~1e-9).
- **Zombies cleared / credit unfrozen.** Standing insolvent-firm count ~0 (v3 had ~all-but-one
  C-firm frozen insolvent), so the v3 credit-freeze symptom is gone.
- **Firm count is dynamically stable** — bounded away from 0 and from explosion, with a balanced
  entry↔exit churn.
- **But monopoly persists — the "revolving door."** Incumbent excess profit is *not* competed away
  (markup stays high); new firms enter, are undercut by the scale leader (increasing returns to
  capital, §11.6), go insolvent, and exit — replaced by the next challenger. Entry runs near its
  cap against a persistently high profit signal.

This is progress precisely *because* it is diagnostic: with zombies gone and demographics
isolating the effect, the residual monopoly is now a **clean, standalone** problem — and its
survival pins **the last missing piece as a curb on the *unbounded scale advantage*** (a capacity
limit / decreasing returns / diseconomies of scale), which entry alone cannot supply (§11.6's
increasing-returns mechanism is untouched by it). One honest side-effect to watch: the bank is
*stressed* by the writeoff flow (its buffer is largely consumed), foreshadowing the bank-solvency /
financial-crisis dynamics that a **multi-bank** layer will make first-class.

**Entanglement note.** v4 subsumes the planned v3.5 (default): "insolvent exit" *is* bad-debt
default. What v3.5 would still add on top is the richer crisis machinery — cascades, fire-sale
asset prices, bank runs — layered on this minimal writeoff.

### 13.4 The drain chokes entrepreneurship (an unplanned finding)

Wiring entry up surfaced a mechanism we did not design for. New firms are **household-funded**
(their startup deposits are transferred from a household — the choice made for conservation and to
open a reflux channel). But the §9–§11 **drain** has impoverished households to a *few units of
deposits per capita* in the depressed state. So with a startup cost of the natural size (a genesis
firm's endowment, ~200), **no household can afford to found a firm, and entry never fires at all** —
firms only die, the count bleeds down, and the profit-competition channel is dead on arrival.

This is a **vicious circle the drain closes on itself**: the drain impoverishes households → poor
households cannot fund startups → no new firms enter to hire and recirculate money → the drain
persists. The very mechanism (entry) that could ease the drain is *strangled by* the drain. It is
the §9 theorem striking a new target — not just depressing output and employment, but cutting off
the *creation of firms* that would remedy it. Emergent, not encoded.

The realistic resolution (and what the model needs) is **lean, credit-bootstrapped entry**: startup
deposits must be on the order of drained household wealth (~10, not ~200), with the new firm growing
via v3 credit and retained earnings rather than a large upfront endowment. Under lean startups entry
fires — and **self-limits** correctly: it happens when households have some money and stalls when
they are drained, so entry is naturally pro-cyclical (easy credit/wealth ⇒ more founding). This is
faithful — poor economies genuinely start fewer, smaller, more credit-dependent businesses — and it
records a real policy-relevant channel: **inequality/drain suppresses firm formation.** (It also
foreshadows why household net worth, once equity is attributed to households under choice 乙, will
matter for entry — a hook for that later layer.)

---

## 14. v5 — Diseconomies of scale, and the competition phase diagram

v4 left exactly one piece missing (§13.3): a **counter-force to unbounded scale advantage**. The
runaway of §11.6 is powered by *increasing* returns to capital (more K ⇒ lower unit cost ⇒ lower
price ⇒ more demand ⇒ more K). v5 adds the opposing force — a **diseconomy of scale**, a coordination
cost that *rises* with firm size — and then maps, empirically, the conditions under which it actually
produces competition. The deliverable is not the parameter; it is the **phase diagram**.

### 14.1 The mechanism — coordination cost on the scale of operations

A coordination cost multiplies the unit cost that feeds cost-plus pricing (B3):
$$uc_{f,t} = uc^{\text{labor}}_{f,t}\,\big(1 + \texttt{dis\_slope}\cdot y^{*}_{f,t}\big),$$
so a bigger firm posts a higher price. `dis_slope=0` reproduces v1–v4 exactly (bit-identical
regression). One free dial (§0-iv); the micro slope is fiat, but *optimal size / concentration /
firm count* emerge (§0-ii).

**Scale is measured by output $y^{*}$, not employment $N$ — a correction the data forced.** The
natural first guess (Lucas span-of-control) is that coordination cost rises with *headcount*. It
does not work here, and the reason is diagnostic: our dominant firm is **capital-intensive** — huge
$K$, high output, but *few workers* (Cobb-Douglas gives high output per worker at high $K$). Its
$N$ is *small* (median employment of a producing firm ≈ 1.8), so a labor-based diseconomy misses
its target entirely — `dis_slope·N` is negligible even at absurd slopes. The size that actually runs
away is **output** (producing firms: median $y^{*}\approx175$, max $\approx385$), so the diseconomy
must scale with output. This is the textbook "diseconomies of scale" (cost rising with the *scale of
production*), and it is the correct lever precisely because it tracks the quantity that concentrates.

### 14.2 The competition phase diagram (the deliverable)

Sweep the two market-structure dials with firm-dynamics **on** — **m** (information transparency,
§11.6) × **dis_slope** (diseconomy) — and read concentration at the tail (firm-size Gini over output,
mean of last 150 ticks, 2–6 seeds; 80 C-firms / 40 K-firms / 800 households, 1000 ticks):

```
firm-size Gini            m=1     m=2     m=3     m=5     m=10
dis_slope=0.000          0.734   0.849   0.860   0.938   0.934
dis_slope=0.001          0.708   0.804   0.877   0.915   0.925
dis_slope=0.002          0.634   0.813   0.918   0.923   0.892
dis_slope=0.005          0.577   0.770   0.855   0.874   0.871
dis_slope=0.010          0.594   0.910   0.832   0.894   0.863
```

The low-concentration region is the **m=1 column** — the *left* edge, rising with slope — **not** the
bottom-right cell we pre-registered. Confirmed with 6 seeds at the corner: (m=1) Gini falls
0.693±0.064 → **0.581±0.022** and markup 0.911 → 0.831 as `dis_slope` goes 0→0.005, the variance
*tightening*; while (m=5) Gini barely moves, 0.914±0.018 → 0.864±0.046, staying near winner-take-all.

### 14.3 The surprise — transparency is *antagonistic* to competition

We pre-registered the opposite hypothesis (competition needs transparency **and** diseconomies
together; a diseconomy at m=1 would be inert). The model falsified it. The diseconomy has two possible
feedback channels, and which one is available depends on m:

- **Profit-squeeze → death (works at any m).** Big firm ⇒ high $y^{*}$ ⇒ high $uc$ ⇒ the bounded
  markup cannot cover it ⇒ losses ⇒ deposits bleed ⇒ insolvency ⇒ **bankruptcy (§13.2)**. This needs
  no price comparison — it works through the firm's books, not its customers. It de-concentrates at
  **m=1**: fewer firms survive (count 144→40 as slope rises) but the survivors are **comparable in
  size** (Gini 0.73→0.58) — the signature of oligopoly, not monopoly.
- **Lost-demand (needs m≥2) — and it fails.** high price ⇒ price-comparing buyers avoid the firm ⇒
  it shrinks. This is the channel we bet on. It is *defeated by §11.6's winner-take-all*: under m≥2
  each buyer dumps its entire budget on the single cheapest of the m it samples, so the instant the
  diseconomy pushes the leader off the cheapest perch (its price-rank does rise, 0.24→0.38 — buyers
  *are* now avoiding it), a *different* firm captures everything. Concentration **rotates but never
  falls**; the instantaneous size-Gini stays near winner-take-all even as the identity of the winner
  churns. **Transparency re-concentrates the market faster than the diseconomy can thin the leader.**

So in a world with a capital cost-advantage, *full information is antagonistic to competition* — it
funnels demand to the low-cost firm rather than dispersing it. This directly extends §11.6
(transparency disciplines *prices* but concentrates *markets*): the diseconomy can undo the
concentration **only where transparency is low enough that winner-take-all does not operate.** Note
the standard intuition survives on the price margin — higher m still lowers markups (§11.6) — so
transparency helps consumers on *price* while hurting them on *structure*. A genuine, decoupled
tension, not encoded (§0-ii): nothing in the axioms says "transparency is bad," and the pre-registered
guess said the reverse.

### 14.4 The conjunction is real — but three-dimensional, and different members

The meta-thesis (competition is a **multi-condition conjunction**; every single market-structure
mechanism failed alone — transparency ⇒ concentration §11.6, entry/exit ⇒ revolving door §13.3,
diseconomy alone ⇒ profit-squeeze only) **survives**, but the members are not the ones we guessed.
The competition cell (m=1, `dis_slope≈0.005`) is a conjunction of **diseconomy of scale + free
entry/exit**, at **low transparency**. The dimensionality control confirms entry/exit is
independently necessary: toggling `firm_dynamics` **off** at that cell sends Gini 0.577 → **0.848**
(and markup 0.73 → 0.91) — without exit, the profit-squeezed leader lingers instead of dying, and
concentration returns. So the diseconomy *creates* the losses but **entry/exit is the executioner**;
neither alone suffices.

This maps onto the classic pillars of perfect competition — no increasing returns, free entry/exit,
full information — as *interacting*, not additively-necessary, conditions: the first two are jointly
necessary here, but the third (full information) is **negatively** signed in the presence of a scale
cost-advantage. That inversion is the headline result of v5.

> **Discipline (§0-ii).** Tail averages over 2–6 seeds at a single scale — an *observation* toward
> the §4 held-out set, not a validated regularity. The robust, low-variance claims are: (i) at m=1 the
> output-scaled diseconomy lowers both Gini and markup monotonically; (ii) at m≥2 it does not lower
> Gini; (iii) removing entry/exit at the competition cell restores concentration. The precise critical
> transparency, the oligopoly firm-count, and scale-robustness remain open.

### 14.5 Parameter budget and acceptance

One new free dial: `dis_slope` (free dials ~9→~10; it buys the *only* counter-force to §11.6's
runaway, so it pays its way per §0-iv). `Config.v5()` ships the **competitive cell** the diagram
identified — `search_m=1`, `dis_slope=0.005`, `firm_dynamics` on — *not* the pre-registered
`m≥2, dis_slope=0.02` (which sits in the non-competitive region; the plan's default was empirically
wrong and was corrected). **Acceptance met:** (1) v1–v4 bit-identical at `dis_slope=0` (52 tests
green); (2) the coupling in data — at m=1 raising `dis_slope` materially lowers Gini and markup, at
m≥2 it does not (the conjunction, empirically); (3) the phase diagram + the `firm_dynamics`-off
control resolving competition as a **3-D** conjunction; (4) A5 / conservation untouched (v5 is a
pricing change; no money-flow change). Experiment scripts: `sweep_v5.py` (phase diagram + 3-D
control), `confirm_v5.py` (seed-robust corner + mechanism instrumentation). PLAN_v5.md records the
pre-registered hypothesis (kept, uncorrected, as the falsified prior — the surprise is only legible
against it).

---

## 15. Validation round — the held-out §4 test set, confronted for the first time

Before adding more mechanism, we harvested: the full model (Config.v4 — banks + credit + capital +
firm demographics + cycles; **dis_slope=0**, no market-structure intervention) was run against the
eight §4 macro regularities it was **never told** (§0-ii). 200C/100K/2000H, 4000 ticks, 3 seeds,
burn-in 1000. Harness: `validate_s4.py`. **Score: 6/8, from the axioms alone.**

| # | regularity | statistic | verdict |
|---|---|---|---|
| T1 | Phillips (inflation↓ vs u) | slope −0.11, corr −0.32 | ✅ |
| T2 | Okun (Δu vs Δoutput) | corr **−0.93** | ✅ |
| T3 | BC comovement (I,N,credit,C vs output) | +0.77, +0.94, +0.23, +0.79 | ✅ |
| T4 | endogenous involuntary unemployment | mean 14%, rationing 0.14 | ✅ |
| T5 | fat-tailed growth | excess kurtosis **+0.93** | ✅ |
| T6 | Zipf/Pareto firm size | slope −0.32 (not −1) | ❌ |
| T7 | credit-driven boom-bust (Minsky) | leverage CV 0.90, corr +0.23 | ✅ |
| T8 | heavy-tailed wealth | Gini 0.12, **left**-skewed | ❌ |

**The six passes are genuine** — the money/credit/cycle machinery reproduces the core
business-cycle facts (T2, T3-employment, T5 especially) without being told them. **The two misses
share one root: the model lacks persistent, idiosyncratic, *multiplicative* dynamics.**

- **T6 (firm size).** Concentration exists (sales-Gini ~0.78, dominated by idle firms; active firms
  are similar-sized) but the *shape* is not a power law. Zipf needs **Gibrat's law** (proportional
  random growth); our firms grow by the **accelerator toward a common `K*=v·yᵉ`** — mean-reverting,
  not multiplicative — and entry/exit equalises. No clean tail at any transparency (too-equal at
  m=1, degenerate winner-take-all L-shape at m≥2 — never a −1 slope).
- **T8 (wealth).** Homogeneous households (identical MPC) + equity not attributed (choice 甲) ⇒
  wealth cannot spread. Fix = MPC heterogeneity (§5) and/or the equity→wealth channel (乙).

> **Measurement caveat (recorded so it is not repeated).** Firm "size" is measure-sensitive:
> capital-Gini 0.12 (accelerator mean-reverts K to a common target) vs sales-Gini ~0.78. The T6 miss
> is about **shape (no power law)**, not level; a first writeup that headlined the capital-Gini
> wrongly implied "firms are equal." The standard sales-based measure is the honest one.

Crucially, the two misses independently **re-derived the exact next increments already flagged**
(heterogeneity §5; equity-to-households 乙) — now *earned by a failed test*, not speculative.

## 16. v6 — Capital market: an aggregate equity index, choice 乙, and bubbles

The highest-dependency layer (needs investment+capital ✅v2, interest ✅v3, mature profit dynamics
✅v4), built minimal-core-first because its blast radius is the largest we have taken on. PLAN_v6
records the engineering plan and the aggregate-vs-per-firm fork.

### 16.1 Scope: one aggregate index (per-firm → v6.1)
A single traded asset — the **equity index**, a claim on total C-firm net worth, one price `p_S`.
Households do portfolio choice between deposits (safe, the `r` benchmark) and the index. This keeps
storage O(N_H) and tames the blast radius. Deferred to v6.1: per-firm equity, per-firm Tobin's q →
q-driven investment, and **"founder gets the shares"** equity seeding (needs per-firm ownership).

### 16.2 Price formation — excess-demand groping, not an auctioneer
The price is **not** a posted-price M1 instance and **not** a computed clearing price (that would be
a Walrasian auctioneer, forbidden by §0). It **gropes** on notional excess demand,
`p_{t+1}=p_t·(1+λ_p·clip((D−S)/float))`, while realised trades are **pro-rata rationed** so both
money (deposit transfers via CLEARING) and shares (Σ holdings == float) conserve exactly. Household
demand is the standard **fundamentalist / chartist** split (reusing the adaptive-expectation form on
returns): `pressure = w_f·(value−p)/p` (stabilising) `+ w_c·trend` (**the bubble knob**). The
fundamental is **net asset value** (book/share). A Gordon dividend/`r` anchor was tried first but is
numerically fragile — cyclical dividend dips collapse it to ~0 and drag the price down with it; the
`r`-discounted earnings valuation is deferred to v6.1.

### 16.3 Conservation — and what a bubble *is*
**A5 (money) is untouched:** equity is a claim, not money; trades are deposit transfers. New gate:
**share-float conservation** (Σ holdings == float, machine precision). The payoff is a clean
definition and invariant: `bubble ≡ market cap − book = float·p_S − Σ net worth`, a **non-monetary
valuation phantom** that can inflate and collapse while A5 never moves.

### 16.4 The MPC precursor (run first, for clean T8 attribution)
Config-only heterogeneity (α₁,α₂ drawn mean-preserving-lognormal, `mpc_dispersion`; 0 = bit-identical).
Measured on T8 in isolation: at σ=0.4, wealth **Gini 0.08→0.47, skew −0.7→+1.5 (T8 flips fail→pass)**;
at σ=0.8, skew +5.5, top-10% 0.42 — a genuine heavy tail. **Correction to the prior guess:** static
MPC differences are *not* merely additive — saving is multiplicative over time, so they **compound**
into a heavy tail. So MPC heterogeneity alone carries T8; the equity channel is tested for what it
*adds*.

### 16.5 Findings (round 4)
1. **The naive wealth effect drives the economy into depression.** Wiring equity value into B1
   consumption amplifies the §9 drain: over-consumption → faster money accumulation in firms →
   households drained to 0 → u→1.0 at every scale (vs u≈0.09 without it). So the wealth effect is
   **decoupled** into its own default-**off** dial (`wealth_effect`); the stable core has equity in
   wealth *accounting* (乙, for T8) but not in consumption *behavior*. Turning it on is a studied
   destabiliser, not a default. (Blast radius, exactly as PLAN_v6 warned.)
2. **乙 accounting alone barely moves T8.** With uniform `theta_equity` and no differential returns,
   equity ownership mirrors deposits, so wealth-incl-equity Gini ≈ deposits Gini. The heavy tail is
   MPC's doing; the equity channel needs heterogeneous/compounding returns (per-firm, capital gains)
   to add inequality — a v6.1 hook, same "multiplicative dynamics" root as §15's T6/T8.
3. **Liveness is drain-gated (a §13.4 analog).** In a depressed economy households have no deposits
   to allocate, so the market is stillborn (turnover→0, price→0 while book stays high). The capital
   market only lives in the healthy regime.
4. **Bubbles are reachable, and money conserves through the crash — the headline SFC result.** Below
   ~`w_chartist`≈5 the fundamentalist anchor dominates (price ≈ book); at `w_chartist`≈20 the
   chartist force overwhelms it and Tobin's q spikes to **~15×** book, then crashes back to ~0.5 —
   and **A5 holds throughout (drift ~1e-7)**. A 15× wealth boom-bust with *zero money created or
   destroyed*: the bubble is pure valuation phantom, not money.

### 16.6 Parameter budget & acceptance
New dials: `w_chartist` (bubble knob), `theta_equity`, `lambda_p`, `wealth_effect`,
`equity_ema_lambda`, plus `mpc_dispersion` (precursor) and `float_shares` (scale). `Config.v6()`
ships the **stable core** (`capital_market=True`, `w_chartist=0.2`, `wealth_effect=0`,
`mpc_dispersion=0.4`); `Config.v6_bubble()` raises `w_chartist=20`. **Acceptance met**
(`test_v6_capital_market`, 7/7): (1) v5 bit-identical at `capital_market=False` (full suite green);
(2) money A5 through trading and a bubble/crash; (3) share float conserved exactly; (4) market live
in a healthy economy; (5) 乙 wealth channel active; (6) fundamental limit (`w_chartist=0` ⇒ no
runaway); (7) bubble reachable + money conserved through the crash. Full financial crisis (bubble →
insolvency → bank stress, the 1929/2008 chain) and per-firm equity / q-driven investment are v6.1+.

---

## 17. Derived macro indicators (observation-only)

A pure-observation pass (no mechanism, no conservation impact, all regression bit-identical): the
standard headline rates/ratios that were derivable from existing series but not logged are now
computed each tick in `metrics.py`, so a macro dashboard need not re-derive them post-hoc.

- **Activity/prices:** `nominal_output`, `real_output_growth`, `wage_inflation`, `real_wage`,
  `labor_productivity`.
- **Distribution:** `income_gini` (over per-household realized income), `consumption_gini`,
  `labor_share` (= wages / value added — functional distribution). *(Wealth/firm-size Gini already
  existed.)*
- **Money/credit:** `money_velocity` (nominal output / ΣD), `credit_to_gdp`, `debt_service_ratio`,
  `savings_rate`; `dividend_yield` (v6).

Sanity at the v6 defaults: labor share ≈ 0.61 (real economies ~0.6), and `consumption_gini` <
`income_gini` (consumption smoother than income — the empirically correct ordering). What remains
**absent** needs new mechanism, not a metric: a market interest rate / spread (r is exogenous),
inflation expectations, fiscal/`G` and trade/`NX` (no government, closed economy), and an output
gap (no potential-output concept) — these are logged in §5's roadmap, not here.

---

## 18. v6.1 — Per-firm equity: the substrate works, but the indirect channels are weak

v6.1 turns the v6 aggregate index into a real **per-firm stock market** (`per_firm_equity`; off ⇒ v6
bit-identical). PLAN_v6.1 has the engineering. Two stages: **v6.1a** (per-firm equity + founder
ownership + earnings valuation; market a side-pot) and **v6.1b** (q-driven investment). Built, and
both conservations are exact — money A5 ~1e-8, **per-firm share float ~1e-13** (Σ_h holdings[f] ==
shares_outstanding_f).

### 18.1 What was built (the substrate — solid)
- **Per-firm price discovery.** Each firm's watchers (a sparse **watchlist** of ~k firms per
  household — O(N_H·k), not O(N_H·N_F)) submit orders; price gropes on the firm's own excess demand;
  pro-rata rationed (money + shares conserve per firm).
- **Founder ownership.** A household that funds a v4 startup receives its **entire float**; genesis
  firms are split among watchers. Bankruptcy **wipes** the equity (holders bear the loss; no money
  moves, A5 intact).
- **Earnings valuation (floored residual income).** `fundamental_f = book_f + max(0, ema(π_f −
  r·book_f))/r` — book floors it (the raw Gordon dividend/r anchor collapses on dividend dips, §16),
  r is the discount base, and **q>1 emerges endogenously for firms earning above r** (~25% of firms).
- **q-driven investment (v6.1b).** `I*_f = accelerator × clip(1+λ_q(q_f−1), floor, cap)`.

### 18.2 Finding (round 5): both hoped-for payoffs are weak — the stock market barely feeds back
The pre-registered hopes were T8 via founder capital-gains and a financial→real crisis via q. Neither
materialised, for coherent (and arguably realistic) reasons:

1. **Founder-equity mirrors wealth — it does not reshape the distribution (T8 unmoved).** Equity
   ownership concentrates *exactly where deposit wealth already is* (owner-Gini 0.51 when deposits are
   unequal, 0.08 when homogeneous), so wealth-incl-equity Gini ≈ deposits Gini (0.469 vs 0.471). From
   a homogeneous start it **stays** equal — the capital-gains loop is too weak (small stakes + firm
   churn wipes equity before it can compound and change ranks). Same lesson as §16.5's aggregate 乙.
2. **q-signalling is a weak financial→real channel.** Even with a 50–160× stock bubble AND a strong
   multiplier (λ_q up to 5), `corr(investment, q) ≈ +0.1` — investment stays **accelerator/demand-
   driven**; the share price barely moves real capital. This *matches the empirically weak Tobin's-q
   theory of investment* — firms invest on sales/cash-flow, not their stock price.

**The lesson:** ownership and price-*signalling* are **indirect** channels, and indirect channels
barely reach the real economy. A financial→real crisis (and possibly the wealth tail) needs a
**direct** channel where asset prices *move real resources* — **equity finance** (firms issuing shares
at market prices to fund capex), which is v6.2. This result *earns* v6.2 rather than assuming it.

### 18.3 Parameter budget & acceptance
New: `per_firm_equity`, `watchlist_size`, `shares_per_firm`, `resid_income_lambda`, `lambda_q`
(+q floor/cap). `Config.v61a()` (side-pot) / `Config.v61b()` (+q-investment). **Acceptance met**
(`test_v61_per_firm_equity`, 6/6): (1) v6 bit-identical off; (2) money A5 through per-firm trading
and bankruptcy; (3) per-firm share-float conservation; (4) founder ownership; (5) earnings valuation
gives q>1 for profitable firms; (6) q-investment wired + bounded. The two §18.2 findings are the
substantive result; equity finance (v6.2) is the earned next step.

---

## 19. v6.2 — Equity finance, and why the stock market does not drive the real economy

§18 argued the financial→real crisis needs a **direct** channel. v6.2 builds it — **equity finance**:
a firm with q>1 issues new shares (extra sell-side supply in its own market) at the market price;
the proceeds go to its deposits and fund capex. A bubble should literally pay for an investment boom.
Built (`equity_finance`; off ⇒ v6.1 bit-identical), conserving (money A5, per-firm float), with
issuance tied to book and capped per tick so there is no dilution spiral (a first, share-count-based
rule ran the float up 294× — fixed).

### 19.1 Finding (round 6): the direct channel is weak too — and that is realistic
Equity finance does **not** transmit bubbles into real investment. Under a large stock bubble,
raising `lambda_issue` *lowers* the investment↔q correlation (0.28 → 0.15 → 0.04) and the cash raised
stays tiny (~2.7/tick vs investment ~500). Two reasons, both economically sound:
- **Demand-constrained.** Households must *buy* the new shares with cash; in the (drained) economy
  they have little, so firms can raise little no matter how much they offer.
- **Self-stabilising.** Issuing when q>1 **dilutes** and pushes q back toward 1 — issuance *damps*
  the bubble rather than feeding on it.

This matches the **pecking-order theory** (equity is a minor, last-resort financing source; firms
fund investment from internal cash and debt).

### 19.2 The synthesis across v6–v6.2: the equity market is decoupled from the real economy
Every channel from asset prices to the real economy that we built is weak *in the boom direction*:

| channel | layer | result |
|---|---|---|
| wealth effect (→ consumption) | v6 | destabilises **downward** (amplifies the §9 drain → depression), not a boom |
| q-signal (→ investment) | v6.1b | weak (corr ~0.1) — matches the empirically weak Tobin's-q theory |
| equity finance (→ capex) | v6.2 | small, demand-constrained, **stabilising** — matches pecking-order |

So in this model the stock market is a valuation/ownership/speculation layer that **barely drives real
activity** — arguably realistic. The corollary is sharp: the **1929/2008 financial→real crisis is not
an equity phenomenon**; it must run through the **credit–collateral (balance-sheet / Minsky–Kiyotaki–
Moore) channel** — asset prices → collateral values → credit capacity → real spending. Our B7 caps
leverage on *financial* net worth (D−L) only; making credit capacity depend on **asset/equity values**
(so a bubble expands credit and a crash contracts it) is the earned next layer (v7). A negative result,
but a load-bearing one: it locates the crisis mechanism by ruling out the equity channels.

### 19.3 Acceptance
`Config.v62()` = v6.1b + `equity_finance`, `lambda_issue`. **Met** (`test_v62_equity_finance`, 4/4):
v6.1 bit-identical off; money A5 + per-firm float conserved through issuance; dilution bounded (no
runaway); firms raise cash when q>1. The §19.1–19.2 findings are the result.

---

## 20. v7 — Household consumption credit: you can't debt-finance out of a leaky bucket

The v6 family showed the equity market is decoupled from the real economy (§19); the endogenous-MPC
thread showed inequality and demand deficiency are coupled by the thrift paradox (§16.7). v7's thesis:
**household credit is the missing recirculation channel** — savers' deposits lent to spenders keep
demand up while inequality shows on the balance sheet. Built on the full v6.2 stack (cumulative;
`household_credit`).

### 20.1 Mechanism (mirror the firm B6/B7 to households)
- **B8 demand:** borrow to defend a subsistence consumption floor, `borrow = max(0, max(budget,
  c_min) − deposits − Y^e)`. Blind to the debt stock (a survival rule, not a wealth rule).
- **B9 supply:** debt-to-income cap `L ≤ φ·Y^e` — the only brake, and procyclical (a falling income
  tightens it). Loans create deposits (M2); debt service amortises + pays interest; **no default**.

### 20.2 Finding (round 6 cont.): consumption credit is inert-or-catastrophic — the drain wins again
The pre-registered hope (dissolve the thrift paradox → "rich + poor + prosperous") failed:
- **Healthy economy ⇒ inert.** Nobody is poor enough to hit the floor, so no one borrows (and where
  it does bite mildly, it *lifts* the bottom via a demand boost — not debt).
- **Depressed economy ⇒ catastrophic.** Everyone is below the floor, so everyone borrows → the money
  **drains to firms (§9)** → households can't service → debt piles to the limit → income falls → the
  limit falls → a **debt-deflation trap**: total collapse (u→1, output→0, **100% of households
  underwater**, debt frozen at the cap). Credit didn't dissolve the paradox; it *deepened* it.

**Two roots.** (i) The floor binds on *income*, which is ~equal across households, so it binds for
everyone-or-no-one — never a poor subset. (ii) The **§9 drain** converts borrowing into a trap: the
borrowed money leaks to firms, leaving households the debt (the failure figure: net worth collapses
into a negative pile, not a rich tail). **The lesson — twice over now (equity §19, credit here): you
cannot fix a leaky bucket by pouring in more; the drain defeats any mechanism that just gives
households money to spend.** And credit *without default* is a permanent trap (parallel to v3→v4).
The fix is not consumption credit but **asset credit** (borrow to buy something you keep) → v8.
Acceptance (`test_v7_household_credit`, 5/5): regression, A5 through borrowing+service, credit funds
consumption, debt bounded, net-debtors appear under stress. The debt-trap finding is the result.

---

