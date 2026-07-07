## 3. Layer III — Market & institutional axioms (protocols)

How agents *meet*, *transact*, and how the system *steps*. These are structural choices
about the simulation's mechanics; unlike §2 they are less about individual psychology and
more about the rules of the arena.

### M0 — Closed economy (prototype scope) 🔒

**Natural language.** The prototype economy is *closed*: no exports, imports, exchange
rate, or cross-border capital flows. All money and all claims circulate strictly among the
domestic agents. The external sector is the last layer on the roadmap (§5) and is out of
scope until the closed economy is stable.

**Formal.** The agent set $\mathcal{A}$ is fixed and complete; there is no "rest of world"
sink or source. Consequently the accounting invariant A1 holds with no external residual —
in particular, with no money creation (before banks) the total money stock is conserved
exactly:
$$\sum_{i \in \mathcal{A}} h_{i,\text{money},t} = M \quad (\text{constant}) \qquad \forall t.$$
This makes A1 especially crisp to test: total *money* must be invariant every tick, full
stop. (v2 adds a real capital stock; capital is **not** money and is excluded from this
sum — §10.)

### M1 — Decentralized matching, posted prices, rationing 🔒

**Natural language.** There is no central market maker. In each period a subset of buyers
and sellers are matched (randomly, or through limited search), and trade occurs at the
seller's posted price. When a seller's supply is exhausted, remaining buyers go
unsatisfied; when a buyer's budget or willingness is exhausted, remaining goods go unsold.
Realized aggregate trade is bounded by both notional demand and notional supply and
generally equals neither.

**Formal.** Let a matching function $M_t$ pair agents into transacting couples over a
subset of $\mathcal{A}$. For a matched buyer–seller pair the realized quantity is
$$q_{t} = \min\big(d_{t},\, s_{t}\big),$$
demand $d_t$ and available supply $s_t$. At the market level,
$$Q_t = \sum_{\text{matches}} q_t \ \le\ \min\Big(\textstyle\sum d_t,\ \sum s_t\Big),$$
with strict inequality generic. The labor-market instance of M1 is search-and-matching in
the Diamond–Mortensen–Pissarides sense.

**Why.** This is the operational form of "no auctioneer" (§0). The unsatisfied residuals —
unsold inventory, unfilled vacancies, involuntary unemployment — are the raw material of
business cycles.

**v2 instances.** M1 governs *three* markets in v2, all by the same protocol: (i) a single
**labor market** where both firm sectors compete for the fixed household labor supply;
(ii) the **consumption-goods market**; and (iii) the new **capital-goods market** where
consumption firms buy from capital firms and investment demand can be *rationed* — making
the capital sector an endogenous bottleneck/amplifier.

### M2 — Endogenous money: loans create deposits 🟡

*(Active only once banks $\mathcal{B}$ are introduced.)*

**Natural language.** When a bank makes a loan it simultaneously creates a matching
deposit. Lending is not the re-lending of pre-existing reserves; banks are not constrained
by a reserve multiplier. They are constrained by capital, expected profitability, and the
perceived creditworthiness of borrowers. Reserves are settled *after* the fact.

**Formal.** A new loan of size $\Lambda$ from bank $b$ to borrower $i$ is the simultaneous
creation of two offsetting entries:
$$\Delta h_{i,\text{loan},t} = -\Lambda \ \ (\text{borrower liability}),\quad
\Delta h_{b,\text{loan},t} = +\Lambda \ \ (\text{bank asset}),$$
$$\Delta h_{i,\text{deposit},t} = +\Lambda \ \ (\text{borrower asset}),\quad
\Delta h_{b,\text{deposit},t} = -\Lambda \ \ (\text{bank liability}).$$
The broad money stock rises by $\Lambda$. This respects A1 exactly (all four entries net
to zero). Lending capacity is governed by a constraint of the form
$g\big(\text{capital}_b,\ \text{expected return},\ \text{borrower risk}\big) \ge 0$,
**not** by a reserves $\times$ multiplier relation.

**Note.** This is the modern central-bank consensus and contradicts the textbook
money-multiplier story (see Bank of England, McLeay–Radia–Thomas, *Money creation in the
modern economy*, 2014). Flagged because older references still teach the multiplier;
we deliberately do not. Endogenous credit creation is the engine we expect to generate
boom–bust dynamics on its own. **Note it breaks M0's exact money conservation** — but not
conservation itself: the correct anchor becomes **A5** (net financial worth $\sum D-\sum L=M$),
with base money $R$ carrying the conserved $M$.

**v3 specialization (🟡, partially locked).** v3 first activates M2 with the simplest active bank:
- **A single bank** (banking sector): an active decision-maker with exactly one lending rule (B7).
- **Firms borrow to cover any cash shortfall** (B6) — wages and investment alike (opening A4's
  credit term as one mechanism); logged by purpose so attribution survives. Household credit deferred.
- **Exogenous fixed interest rate $r$.** How the rate is *set* belongs to the central-bank layer;
  v3 only asks what *having* an interest rate does.
- **Fixed-proportion amortization**; loans revolve (drawn on a shortfall, repaid as cash allows).
- **No default in v3.** Bankruptcy, bad-debt write-offs, and cascades — the heart of a financial
  crisis — are **v3.5**. One mechanism at a time: v3 establishes endogenous money and the leverage
  cycle; v3.5 adds the crash.

The accounting consequence is A5: money conservation (M0) is superseded by net-worth conservation
($\sum D-\sum L=M$), with base money $R$ ($\sum R=M$) as the outside instrument carrying $M$.

### M3 — Scheduling: three distinct axes, not one knob 🔒

The order in which agents act materially changes aggregate outcomes and can decide whether
the system is stable or divergent — so it is a first-class design object. But "order" bundles
**three different things**, each with its own correct treatment. Collapsing them into a
single "sequential vs. synchronous" switch is a mistake.

**(a) Micro queuing order — who transacts first within one market.**
Within a single round of matching, position in the queue affects who gets rationed. In
reality this is *idiosyncratic noise* (who happens to arrive first). It is therefore **not**
a behavioral parameter and has no "true" value. We **integrate it out**: randomize the
participant ordering $\pi$ every tick (seeded, reproducible), and re-run across seeds. A
macro result that depends on this ordering is an **artifact, not a finding** — so this axis
doubles as a built-in robustness / invariance test.
$$\text{realized } S_t \text{ must be (statistically) invariant to } \pi \quad\Rightarrow\quad \text{result is credible.}$$

**(b) Decision-update frequency — how often an agent re-plans (re-prices, re-wages).**
This is real, economically meaningful, and *measurable* (menu-cost / Calvo: micro data say
how often firms change prices). It is already implicit in the B3/B4 stickiness; we make it
**explicit** as parameters, but *empirically anchored* ones, not free dials:
$$\theta_{\text{price}},\ \theta_{\text{wage}} \in [0,1] \quad=\quad \text{per-tick probability an agent revisits its price / wage.}$$
Calibrate to observed adjustment frequencies rather than tuning to taste.

**(c) Information timing — does an agent act on current or last-period state.**
This is the genuine synchronous-vs-asynchronous axis. Crucially, it is **mostly locked by
physics, not chosen**, once you separate the two kinds of state an agent reads:

- *Macro signals* (price index, average wage, unemployment) used for expectations/planning
  **do not yet exist within the current period** — they are only computable once the period
  closes. So "plan on last period's aggregates" is not laziness; it is how reality works
  (you know last month's CPI, not this instant's). This block is *necessarily*
  synchronous-read-stale.
- *Own balances and a counterparty's remaining stock* **must** be read live at the moment of
  trade, or an agent could spend money it no longer has — violating A4 and money conservation
  (M0). So market execution is *necessarily* sequential-read-live.

Thus the "planning synchronous / markets sequential" hybrid of §6.3 is **not** a free choice
we happened to make — it is the *unique self-consistent* scheme forced by information
availability plus the conservation laws. What remains genuinely free is narrow.

**Formal.** Per-agent update $U$, state $S_t$.
- *Synchronous block* (planning): $S_t^{\text{plan}} = \bigoplus_i U_i^{\text{plan}}(A_{t-1})$, all reading the frozen prior aggregates $A_{t-1}$.
- *Sequential block* (markets): $S_t^{(0)}=S_t^{\text{plan}}$, then $S_t^{(j)} = U_{\pi(j)}^{\text{mkt}}\!\big(S_t^{(j-1)}\big)$ under random ordering $\pi$; realized $S_t$ depends on $\pi$ only up to the invariance required by (a).

**Optional research dial (⚪, off by default).** If we ever want to *study* reaction speed
directly, we may add $\alpha_{\text{info}} \in [0,1]$: the fraction of agents whose planning
uses partially-revealed current-period information (the "fast movers"). $\alpha_{\text{info}}=0$
is pure synchronous; $\alpha_{\text{info}}=1$ is maximally reactive. This is explicitly a
**dial for sensitivity experiments, not a parameter with a true value** — and by the
parsimony principle (§0-iv) it stays out of the model unless a specific question demands it.

**Why now 🔒.** Elevated from 🟡: axes (a) and (c) are pinned by robustness methodology and
by physics respectively, and (b) is just the explicit face of already-locked stickiness.
Little here is actually discretionary anymore.

---

