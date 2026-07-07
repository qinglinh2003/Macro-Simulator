## 4. Validation targets — the held-out test set (NOT axioms)

These are macro regularities a good model should **reproduce without being told**. They
are how we judge the axioms above. Encoding any of them as an axiom is forbidden (§0-ii).

- **Phillips relation** — a (possibly unstable, nonlinear) inflation–unemployment
  tradeoff, emerging from B3/B4/M1, never imposed.
- **Okun's law** — comovement of output and unemployment.
- **Business-cycle comovement** — consumption, investment, employment, credit moving
  together at business-cycle frequency; recurrent booms and busts without external shocks.
  *(v2's accelerator (B5) is our first candidate engine for this.)*
- **Endogenous unemployment** — persistent involuntary unemployment as an equilibrium
  outcome of M1 + B4, not an assumption.
- **Fat-tailed aggregate growth** — output/growth-rate distributions with excess kurtosis
  (Laplace-like), not Gaussian.
- **Zipf / Pareto firm-size distribution** — a heavy-tailed size distribution from firm
  entry, growth, and exit.
- **Credit-driven boom–bust** — leverage cycles arising from M2, à la a Minsky dynamic.
- **Wealth-distribution shape** — a right-skewed, heavy-tailed wealth distribution from
  B1 + heterogeneous returns. *(A depression-linked inequality spike already emerged in v1 —
  see §9.1.)*

A run is "successful" to the extent it reproduces these from the micro axioms alone.

---

## 5. Open decisions & roadmap

**Resolved decisions (✅).**

- **Money from genesis** (was: barter vs. money). The prototype starts *with* money:
  households and firms receive an initial deposit endowment at tick 0. "How money
  emerges" is deferred to a future research branch, not the prototype. Rationale: money is
  a *tool* here, not the object of study; the round-1 goal is disequilibrium dynamics and
  emergent cycles, and a barter start would burden the first kernel unnecessarily.
- **Closed economy** (M0). External sector out of scope until the closed economy is stable.
- **Scheduling** (M3). Resolved via the three-axis decomposition: micro queuing order is
  randomized/seeded and integrated out (a robustness test, not a parameter); update
  frequency becomes empirically-anchored $\theta_{\text{price}},\theta_{\text{wage}}$; the
  synchronous-planning / sequential-markets hybrid is shown to be *forced* by information
  availability + conservation, not chosen. The $\alpha_{\text{info}}$ dial stays off by
  default (§0-iv).
- **Equity valuation — choice (甲).** Household wealth $V_h = D_h$ (own deposits only).
  Retained earnings $(1-\rho)\pi_f$ stay in firm deposits and are *not* attributed to
  household net worth. Rationale: parsimony — this removes an entire equity→wealth→
  consumption feedback loop and keeps the first closed loop cleanest. Attributing equity to
  households ("choice 乙") is a natural later increment, tied to the capital-market layer.
- **Matching protocol & goods count — abstracted.** Both behind replaceable interfaces
  (§7.3). Goods count: the kernel is single-good; **v2 activates the multi-good path**
  (consumption + capital), added data + one allocation rule, not a refactor. Matching:
  **now a single continuous *information-transparency* axis** (`SampledCompareMatch(m)`,
  `search_m`) — a buyer samples m random sellers and buys the cheapest. m=1 is zero
  transparency (the old RandomMatch, identical draw); m≥#sellers is full transparency (the
  old PriceSortedMatch). The two former protocols are just the endpoints of this one dial
  (more parsimonious — one parameter replaces two protocols), enabling a transparency sweep
  (§11.6 finding).
- **MPC heterogeneity — later, at zero architectural cost.** $\alpha_1,\alpha_2$ are
  per-household *fields*, initialized uniform in early configs; enabling heterogeneity is a
  config change, not a refactor. It serves the *research* goal ("distribution matters") and
  is layered in once the mechanical loop is trusted.
- **Proto-labor in the kernel — confirmed.** The kernel keeps the simplified
  production→wage→income link. A dividend-only income channel cannot bootstrap a circular
  flow, so proto-labor is the minimal honest loop. Fuller search-and-matching richness is
  layered in with later versions.
- **Round-1 modelling simplifications (locked for parsimony).** Sign-only markup signal;
  equal dividend split across households; firms observe own sales only (not lost sales); no
  expected-inflation wage indexation (deferred to a wage–price-spiral study).

**v2 resolved decisions (✅) — investment + capital.**

- **Independent capital-goods sector.** Two firm sectors: $\mathcal{F}_C$ (consumption
  goods) and $\mathcal{F}_K$ (capital goods). Chosen over "same good doubling as capital"
  for extensibility toward multi-sector / input–output structure, and because it makes the
  money-return channel (capital-sector wages) *explicit and verifiable* rather than hidden.
- **Shared behavioral core.** Both sectors run the identical B2/B3/B4 + inventory-buffer
  logic; they differ **only** in production function, output good, buyer, and the fact that
  only $\mathcal{F}_C$ invests. No second behavior codebase (parsimony).
- **Cut the capital recursion.** $\mathcal{F}_K$ produces with **labor only**
  ($y_K=a_K N_K$); capital accumulates **only** in $\mathcal{F}_C$. A deliberate asymmetric
  simplification to keep v2 finite; symmetrizing is a later option.
- **Investment rule = accelerator + partial adjustment** (B5). Accepted with eyes open to
  overshoot/divergence; $\lambda_I$ is the damping knob. Profit-rate driver and true Tobin's
  $q$ deferred.
- **Investment is rationable (M1).** Capital-goods orders go through M1 and can be
  short-side rationed; the capital sector is an endogenous bottleneck.
- **Depreciation on** ($\delta_K$). Prevents unbounded $K$ and provides a permanent
  maintenance-investment floor (a standing recirculation channel). Cheap; kept.
- **Consumption technology = Cobb–Douglas** $y_C=A K^\alpha N_C^{1-\alpha}$; smooth, standard,
  substitutable. Leontief (fixed proportions) deferred as a supply-bottleneck variant.
- **Capital is a real stock, excluded from money conservation.** Only the deposit flow that
  buys capital enters M0; $K$ itself accumulates by perpetual inventory and must **not** be
  summed into the money-conservation assertion (§1 real-vs-financial; §10 warning).
- **v2 acceptance = conservative, architecture = progressive.** Pass on: conservation still
  holds; the §9 drain reverses/stabilizes; economy stays bounded and active (no v1 trap).
  Endogenous investment cycles are a welcome bonus, not a pass/fail bar.

**Open decisions (⚪).** None block v2. Future forks (post-v2): equity→wealth (乙) and a
**capital market** (equity trading, share prices, financial wealth effects); **banks &
endogenous money (M2)** with debt/leverage/Minsky dynamics and an interest rate; **true
Tobin's $q$** once that capital market and interest rate exist; government/fiscal;
central bank/monetary policy; firm entry/exit; heterogeneity deepening; external sector.
(The capital market is understood as the eventual *hub* into which equity, Tobin's $q$, and
financial-cycle dynamics all connect; it is intentionally late because it needs investment,
an interest rate, and mature profit dynamics beneath it first.)

**Build order (add a layer only after the previous one is stable and A1–A4 never trip).**

1. **Kernel** — households + firms + one good (proto-labor). *Done (v1); §9.* Earned the
   drain theorem.
2. **Investment + capital** — two-sector economy, accelerator (B5). *Done (v2); §10–§11.*
   Cured the primary drain and produced endogenous cycles; the long run exposed a *fractal*
   secondary drain in the capital sector (§11.2–3). *(v2.5 symmetrization was tried to cure it
   and **falsified** — structurally unstable, §11.5; not on the path.)*
3. **Money & banks** (M2) — endogenous credit; money conservation (M0) superseded by net-worth
   conservation (A5). The layer §11.5 *earned*. *Done (v3); §12.* A5 holds to machine precision,
   broad money is endogenous (alive), credit funds wages and *mitigates* the §11.2 deterioration —
   but does not cure it (drained firms don't qualify, debt freezes without default). **No default**;
   default / bankruptcy / crisis cascades are **v3.5** — now motivated by that frozen debt.
4. **Capital market** — equity trading + share prices; shift to equity choice 乙; enables
   true Tobin's $q$ and financial-cycle dynamics. (Hub; needs 2–3 beneath it.)
5. **Government** (taxes, transfers, fiscal policy) — the first countercyclical stabilizer.
6. **Central bank** (policy rate, transmission through M2/B3).
7. **External sector** (trade, cross-border flows).

*(Cross-cutting deepenings — MPC/return heterogeneity, firm entry/exit, richer
labor-market matching — are woven into whichever layer they most naturally attach to,
rather than being standalone steps. **Firm entry/exit + bankruptcy is done — v4, §13** —
and it subsumed the planned v3.5 default, since an insolvent firm's exit is a bad-debt
default. Buyer price-comparison is done too — the transparency dial, §5/§11.6.)*

---

## 6. Prototype: the minimal kernel and its single-tick specification

This section operationalizes roadmap step 1 (§5). It fixes *what happens, in what order,*
within one period, since M3 tells us the order is not neutral. Everything here is scoped to
the **closed monetary kernel** and inherits the provisional choices flagged in §5.

### 6.1 Kernel entities

Two agent types, one good, money (deposits) as the only financial instrument.

- **Households** $\mathcal{H}$. Hold money; supply labor; earn wages and dividends; consume
  the good; save the remainder. Own the firms.
- **Firms** $\mathcal{F}$. Hold money; hire labor; produce the good; hold inventory; post a
  price and a wage; earn revenue; pay a wage bill; distribute part of profit as dividends,
  retain the rest.

**Instruments.** Money (deposit) $D$ — the only financial claim. The good — a real
(outside) item held as firm inventory or consumed by households.

**Note on a proto-labor link.** A closed *monetary* economy needs a circular flow of
income, so even the "goods-only" kernel needs a minimal production→wage→income channel.
The kernel therefore includes a *simplified* labor step (inelastic supply, short-side
rationing); the richer search-and-matching labor market with genuine unemployment dynamics
is a later layer. In the kernel, "unemployment" is just the unhired residual.

### 6.2 Initial endowments (tick 0)

Per the resolved money decision: households are endowed with deposits, and firms are
endowed with *enough* deposits to fund a first wage bill (a firm with zero cash could never
start the loop, since in the kernel there is no bank credit — M2 is inactive). Total money
$M = \sum_{\mathcal H} D + \sum_{\mathcal F} D$ is then conserved forever (M0).

### 6.3 The tick, phase by phase

Scheduling follows the hybrid of M3: **planning is synchronous** (every agent reads the
*same* frozen end-of-$t{-}1$ state), then **markets resolve sequentially** (live balances,
so A4 is respected as money moves), then **settlement and the accounting check** close the
period. Market participant ordering $\pi$ is randomized each tick.

**Phase 0 — Carry over.**
Load end-of-$(t{-}1)$ stocks: household deposits, firm deposits, firm inventories, posted
prices $p_{i,t-1}$, wages $w_{i,t-1}$, and the aggregates needed for expectations.

**Phase 1 — Expectations & planning (synchronous; read $t{-}1$ only).**
Every agent computes plans against the frozen prior state; no one sees anyone else's
Phase-1 output.
- Households: expected income $\mathbb{E}_{h,t}[Y]$ via B2.
- Firms: expected demand $\mathbb{E}_{f,t}[d]$ via B2 (from past sales).
- Firms: production target $y^{*}_{f,t}$ from expected demand and an inventory buffer rule
  (produce toward a target stock).
- Firms: **wage offer** $w_{f,t}$ via B4 — adjust subject to the downward floor.
- Firms: **price** $p_{f,t}$ via B3 — update markup from the $t{-}1$ inventory/unfilled-
  demand signal, then apply the stickiness band (change only if drift exceeds $\bar s$).
- Households: **planned consumption** $C^{*}_{h,t}$ via B1, from expected income and
  wealth $V_{h,t-1}$.

> **Ordering note (wage before price).** B4 must fire *before* B3: cost-plus pricing in
> §7.2 uses the current period's wage, $uc_{f,t}=w_{f,t}/a$, so the wage has to be settled
> before the markup/price step reads it. B4 itself depends only on whether the firm was
> labor-rationed *last* tick, not on this tick's price, so the dependency is one-way and
> the order is forced. (This corrects an earlier §6.3-vs-§7.2 inconsistency that listed
> price before wage.)

**Phase 2 — Labor market (sequential; M1).**
- Firms post labor demand implied by $y^{*}_{f,t}$; households supply labor inelastically.
- Match under random ordering $\pi$; each firm hires up to what its **deposits can pay**
  (A4 — no credit in the kernel, so the wage bill is capped by cash on hand). Short-side
  rationing determines realized employment; unhired households are this tick's unemployed.
- **Wages paid:** money flows firm $\to$ household (A1/A2/A3 all move together).
- **Production:** hired labor yields output added to firm inventory.

**Phase 3 — Goods market (sequential; M1).**
- Households, now holding this tick's wage income, demand the good up to $C^{*}_{h,t}$,
  **capped by their deposits** (A4).
- Match buyers to firms under random ordering $\pi$; trade at the firm's posted price;
  realized quantity $= \min(\text{demand at that seller},\ \text{seller inventory})$.
- **Payment:** money flows household $\to$ firm; inventory decremented. Record the
  residuals — **unsatisfied demand** and **unsold inventory** — as first-class outputs
  (they feed next tick's Phase-1 signals and the §4 diagnostics).

**Phase 4 — Settlement & distribution.**
- Firm profit $\pi_{f,t} = \text{revenue}_{f,t} - \text{wagebill}_{f,t}$.
- **Dividends:** firms distribute a fraction of (non-negative) profit to household owners;
  money flows firm $\to$ household. Retained earnings stay as firm deposits. This is the
  second household income channel and closes the profit loop.
- Commit all stock updates (A2): deposits and inventories to their end-of-$t$ values.

**Phase 5 — Accounting check & recording (A1 hard gate).**
- **Assert money conservation (M0):** $\sum_{\mathcal H}D + \sum_{\mathcal F}D = M$,
  unchanged from tick 0. Any drift halts the run.
- **Assert** each agent's budget balanced (A3) and all quantities non-negative (A4).
- **Record aggregates** for $t$: price index, real output, employment/unemployment,
  unsold inventory, average markup, etc. — both for next tick's expectations and for the
  §4 held-out validation.

### 6.4 The circular flow, in one line

Money sloshes around a closed loop and is never created or destroyed in the kernel:
$$\text{firms} \xrightarrow{\text{wages, dividends}} \text{households}
\xrightarrow{\text{purchases}} \text{firms},$$
with A1 guaranteeing the two arrows always net to zero across the system. The *interesting*
behavior lives entirely in the residuals — unsold goods, unhired labor, unspent income —
i.e. in the ways the loop **fails to balance smoothly**, which is exactly the
disequilibrium that §0-iii promised would do the work. *(v2 adds a third node — the capital
sector — and a second real flow; the loop and its residuals grow accordingly, §10.)*

### 6.5 Minimal aggregates to log (kernel)

Price index $P_t$, real output $Y_t$, employment $N_t$ and unemployment rate $u_t$,
inventory stock, unsatisfied-demand ratio, average markup $\bar\mu_t$, and the money
distribution across sectors (as a conservation cross-check). These are the raw series the
§4 validation will later be run against.

---

## 7. The closed kernel: equations, interfaces, and parameter budget

This section makes the round-1 kernel *executable on paper*. It converts the templates of
§2/§6 into closed-form update rules, fixes the two abstract interfaces with minimal
defaults, and lists every free parameter in one budget table (per §0-iv). Scope: closed
(M0), monetary, single good, households + firms, equity choice (甲).

### 7.1 State variables

| Agent | State carried across ticks |
|---|---|
| Household $h$ | deposits $D_h$; expected income $Y^{e}_h$ |
| Firm $f$ | deposits $D_f$; inventory $I_f$; posted price $p_f$; posted wage $w_f$; markup $\mu_f$; expected demand $d^{e}_f$ |

Household wealth is $V_h = D_h$ (choice 甲). Total money $M=\sum_h D_h+\sum_f D_f$ is
invariant (M0).

### 7.2 Closed-form behavioral equations

Ordered as they fire within a tick (§6.3). All "$t{-}1$" quantities are the frozen
prior-period values read during synchronous planning.

**Expectations (B2).** Adaptive, error-correction:
$$d^{e}_{f,t} = d^{e}_{f,t-1} + \lambda_d\big(\text{sales}_{f,t-1} - d^{e}_{f,t-1}\big), \qquad
Y^{e}_{h,t} = Y^{e}_{h,t-1} + \lambda_y\big(Y_{h,t-1} - Y^{e}_{h,t-1}\big),$$
with $\lambda_d,\lambda_y\in(0,1]$ and $Y_{h,t-1}$ = wages + dividends realized last tick.

**Target inventory & production (B-plan).**
$$I^{*}_{f,t} = \phi\, d^{e}_{f,t}, \qquad
y^{*}_{f,t} = \max\!\big(0,\ d^{e}_{f,t} + I^{*}_{f,t} - I_{f,t-1}\big).$$

**Production function.** Linear in labor:
$$y_{f,t} = a\, N_{f,t},$$
$a$ = productivity (units per worker per tick). Notional labor demand
$N^{d}_{f,t} = y^{*}_{f,t}/a$, **capped by cash (A4)**: a firm cannot commit a wage bill it
cannot pay,
$$N^{d,\text{eff}}_{f,t} = \min\!\Big(\, y^{*}_{f,t}/a,\ \big\lfloor D_{f,t-1}/w_{f,t} \big\rfloor \Big).$$

**Wages (B4).** *(Fires before pricing — see the ordering note in §6.3; cost-plus below
reads this tick's $w_{f,t}$.)* Raise on labor shortage, never cut (DNWR floor automatic
since the target never falls):
$$w^{*}_{f,t} = \begin{cases} w_{f,t-1}(1+\omega) & \text{if firm was labor-rationed last tick } (N_{f,t-1}<N^{d,\text{eff}}_{f,t-1})\\ w_{f,t-1} & \text{otherwise}\end{cases}
\qquad
w_{f,t} = \begin{cases} w^{*}_{f,t} & \text{w.p. } \theta_{\text{wage}}\\ w_{f,t-1} & \text{w.p. } 1-\theta_{\text{wage}}\end{cases}$$

**Pricing (B3).** Unit (labor) cost and cost-plus target:
$$uc_{f,t} = \frac{w_{f,t}}{a}, \qquad p^{*}_{f,t} = (1+\mu_{f,t})\, uc_{f,t}.$$
Markup adapts to the local inventory signal
$s_{f,t} = \operatorname{sign}\!\big(I^{*}_{f,t-1} - I_{f,t-1}\big)$ (understocked $\Rightarrow$
demand strong $\Rightarrow$ raise markup):
$$\mu_{f,t} = \operatorname{clip}\big(\mu_{f,t-1} + \eta\, s_{f,t},\ \mu_{\min},\ \mu_{\max}\big).$$
Stickiness is the M3(b) Calvo form — the *posted* price catches up to target only when the
reprice draw fires:
$$p_{f,t} = \begin{cases} p^{*}_{f,t} & \text{w.p. } \theta_{\text{price}}\\ p_{f,t-1} & \text{w.p. } 1-\theta_{\text{price}}\end{cases}$$

**Consumption (B1), choice (甲).** Desired nominal consumption budget:
$$C_{h,t} = \alpha_1\, Y^{e}_{h,t} + \alpha_2\, D_{h,t-1}, \qquad 0<\alpha_2<\alpha_1<1.$$
Realized spending in the goods market is $\le \min(C_{h,t},\, D_{h,t})$ at live deposits
(A4); unspent budget remains as deposits (= saving).

**Settlement & dividends (choice 甲).** Per firm,
$$\text{revenue}_{f,t} = p_{f,t}\cdot\text{sales}_{f,t}, \quad
\text{wagebill}_{f,t} = w_{f,t} N_{f,t}, \quad
\pi_{f,t} = \text{revenue}_{f,t} - \text{wagebill}_{f,t}.$$
Dividends pay out a fraction of positive profit, split equally across households (ownership
abstracted to equal shares in the kernel):
$$\text{Div}_{h,t} = \frac{1}{N_H}\sum_{f} \rho\,\max(0,\pi_{f,t}),\qquad
\text{retained}_{f,t} = (1-\rho)\max(0,\pi_{f,t})\ \text{stays in } D_f.$$

**Conservation (A1/M0) — the hard gate.** Every flow above is a paired $\pm$ deposit move
(wages firm→hh, purchases hh→firm, dividends firm→hh), so
$$\sum_h D_{h,t} + \sum_f D_{f,t} = M \quad \forall t.$$
Assert this each tick; halt on any drift.

### 7.3 The two abstract interfaces (minimal defaults)

**`MatchingProtocol.match(buyers, sellers)` → transacting pairs.**
Default `RandomMatch`: shuffle participants (seeded, per M3(a)); each buyer is paired to a
random seller with stock; trade quantity $=\min(\text{buyer budget}/p_{\text{seller}},\ \text{seller stock})$;
buyers do **not** compare prices. Alternative implementation `PriceSortedMatch`
(buyers prefer cheaper sellers → price competition) is the same interface, deferred. Used
for both the labor market and the goods market — and, in v2, the capital-goods market.

**`Goods` — the commodity set.**
Default $|\text{Goods}|=1$. Code always iterates over the set (never a hard-coded scalar),
so multi-good is *added data* plus one demand-allocation rule, not a refactor. **v2 uses
$\text{Goods}=\{\text{consumption},\text{capital}\}$** — the interface's reason for
existing. Kernel allocation is trivial (all consumption budget → the single good).

### 7.4 Parameter budget (per §0-iv)

Every free quantity, with its status. The point of the table is to make description length
*visible* and force the parsimony question on each row. Legend: **forced** (pinned by an
identity/axiom, not free), **anchored** (has an empirical target to calibrate to),
**scale/transient** (should not affect stationary behavior — a robustness check, not a
true value), **free** (a genuine behavioral dial to scrutinize / minimize).

| Symbol | Meaning | Default / magnitude | Status |
|---|---|---|---|
| $a$ | labor productivity | $1$ (unit normalization) | scale — normalizable to 1 by choice of units |
| $\delta$ | downward wage flexibility | $0$ | **forced** by B4 (strict DNWR floor) |
| $\theta_{\text{price}}$ | reprice probability / tick | anchored to price-change frequency | **anchored** (Nakamura–Steinsson, Bils–Klenow) |
| $\theta_{\text{wage}}$ | rewage probability / tick | anchored to wage-change frequency | **anchored** (wage-rigidity data) |
| $\alpha_1$ | MPC out of expected income | $\sim 0.6\text{–}0.9$ | **anchored** (MPC evidence) |
| $\alpha_2$ | propensity out of wealth | small, $\ll\alpha_1$ | **anchored** (wealth effect on consumption) |
| $\rho$ | dividend payout ratio | $\sim 0.3\text{–}0.6$ | **anchored** (corporate payout ratios) |
| $\lambda_d,\lambda_y$ | expectation adjustment speed | $\sim 0.2\text{–}0.5$ | **anchored** (expectation stickiness, softly) |
| $\phi$ | target inventory / expected demand | $\sim 0.5\text{–}1$ | **free** — scrutinize |
| $\eta$ | markup adjustment step | small | **free** — scrutinize |
| $\mu_{\min},\mu_{\max}$ | markup bounds | e.g. $[0,\ 1]$ | **free** — scrutinize |
| $\omega$ | wage-raise step on shortage | small | **free** — scrutinize |
| $N_H,N_F$ | agent counts | large enough for statistics | **scale** — results must be robust above threshold |
| $D_h(0),D_f(0)$ | initial deposits | set $M$ and its split | **transient** — must not affect stationary behavior; verify |
| $p_f(0),w_f(0),I_f(0),\mu_f(0)$ | initial postings/stocks | any sane positive values | **transient** — should wash out; verify |

**Parsimony read-out (kernel).** Of ~18 knobs, only **five** are genuinely free behavioral
dials ($\phi,\eta,\mu_{\min},\mu_{\max},\omega$); the rest are normalizable ($a$), forced
($\delta$), empirically anchored ($\theta,\alpha,\rho,\lambda$), or scale/transient
($N,\text{initial conditions}$). That small free-dial count is the parsimony target we
protect: any future addition must justify enlarging it (§0-iv). *(v2 adds two — see §10.7.)*

### 7.5 First milestone (deliberately minimal)

Do **not** aim for §4 laws yet. The v1 success criterion is only:

> Run the kernel for $N$ ticks with the money-conservation assertion (7.2) **never
> tripping**, and with price/output series that are *neither frozen nor exploding* — i.e.
> alive and bounded.

"Alive and conserving" first; "reproduces the Phillips curve" much later. Separating these
keeps early debugging honest: at any moment we know whether we are fixing *plumbing* (a
conservation or feasibility bug) or *economics* (a dynamics/calibration question).

### 7.6 Implementation commitments (engineering, not axioms)

These are code-level decisions — not part of the axiom set, but committed now because they
shape the build.

- **Accounting as a structural primitive.** All money movement goes through a single
  `transfer(from, to, amount)` channel that debits one account and credits another in one
  operation. Agents have **no** direct write access to their own balances. A1/M0 then
  cannot be violated *by construction*; the tick-end assertion (§7.2) becomes a redundant
  safety net rather than the primary defense. This is the single most important early
  decision for debuggability.
- **Per-agent parameter fields.** Behavioral parameters ($\alpha_1,\alpha_2,\mu,\dots$;
  and in v2 $v,\lambda_I,\dots$) are stored per agent even when config sets them uniform, so
  enabling heterogeneity later is a config change, not a refactor.
- **Seeded RNG throughout.** All randomness (matching order per M3(a), any stochastic
  reprice/rewage draws) flows from a single seeded generator, so runs are reproducible and
  the M3(a) invariance test (re-run across seeds) is first-class.
- **Language/stack.** Python + numpy; clear object/array agent representation first,
  vectorization deferred until correctness is established and a profile justifies it.

---

## 8. Handoff notes for the implementing agent

This document is a specification, but its reader is an autonomous coding agent that will
otherwise fill gaps by guessing. This section addresses that reader directly. Read §0
(especially §0-iv, parsimony) and §7 (kernel) or §10 (v2) before writing code; then honor
the following.

### 8.1 Underspecified points — resolve as directed, do not free-style

Where the spec is silent, these are the intended resolutions. If a case arises that is
*not* covered here, **stop and ask, or mark the assumption explicitly in code** — do not
silently fill it.

- **Units.** One tick = one abstract period (not bound to a week/month). Money is in
  abstract units. θ, λ, etc. are per-tick. Do not attach real-world calendar meaning.
- **Continuous vs. integer.** Start with **continuous** labor, output, inventory, sales,
  and (v2) capital (smoother series, easier to judge "alive vs. exploding"). The
  $\lfloor D/w\rfloor$ in §7.2 is a cash cap, not a mandate to make employment integer; with
  continuous labor read it as $D/w$.
- **Degenerate-case guards.** Guard, and *document*, at least: $a>0$; $w_f>0$ before any
  $D/w$ or $w/a$; $I^{*}=0$ in the markup sign (gap sign $=0$, no markup change); a firm
  with no sales history (initialize $d^{e}$ from initial conditions). **v2 additions:**
  a C-firm must start with $K_f(0)>0$ (else Cobb–Douglas output is 0); guard the labor
  inversion $N^d_C=(y^*/(A K^\alpha))^{1/(1-\alpha)}$ against $K=0$ and $y^*=0$; never let
  $K$ go negative (investment floored at 0; depreciation cannot exceed stock). These guards
  must not silently change behavior — surface them.
- **Cross-tick derived state.** §7.1/§10.6 list the *minimum*. Any prior-period derived
  quantity a rule reads must be persisted: last target inventory $I^{*}_{f,t-1}$ (markup
  signal), last effective labor demand and hiring (rationing detection), and **(v2)**
  $K_{f,t-1}$ and the last capital target for the accelerator. Persist rather than
  recompute (recomputation risks the wrong vintage).

### 8.2 Hard disciplines — non-negotiable

- **Implement the current layer and nothing more.** For v1, §7 only; for v2, §7+§10 only.
  Do **not** add features to make the economics "look better": no expected-inflation
  indexation, no smarter pricing, no interest rate, no equity market, no attempt to induce
  a Phillips curve or any §4 regularity. §4 facts are the *held-out test set* (§0-ii);
  producing them by adding mechanism is failure, not success. Parsimony (§0-iv) binds the
  implementer: do not add free dials beyond those tabulated (five in §7.4, seven in §10.7).
- **Accounting is structural, not checked-after.** All money movement goes through the
  single `transfer(from, to, amount)` primitive; agents get **no** direct write access to
  balances (§7.6). Do not bypass this "for efficiency." The per-tick conservation assertion
  must also run — as a redundant net, not the primary defense.
- **(v2) Capital is not money.** The money-conservation assertion sums **deposits only**,
  across all three sectors. **Never** add the capital stock $K$ (or capital-good inventory
  valued somehow) into that sum — buying capital is a deposit *transfer* (conserved); $K$ is
  a real stock that accumulates. Putting $K$ in the money check is the classic v2 bug and
  will make a correct model look broken.
- **Everything seeded.** All randomness derives from one seeded generator so runs reproduce
  exactly and the seed-invariance test is meaningful.

### 8.3 Deliverables — what "done" looks like

The v1 target is §7.5 ("alive and conserving"); the v2 target is §10.8. In both cases
deliver: the layer's kernel/loop wired to its equations; the conservation gate (halts on
drift or A4 violation); a diagnostic plot (bounded and moving series); and a seed-invariance
check across ≥3 seeds (a seed-dependent result is an artifact, not a finding). **v2 must
additionally deliver** the drain-reversal check of §10.8: sector-level money series showing
that the previously monotone firm-deposit accumulation reverses or stabilizes and household
money stops falling — the falsifiable prediction from §9.4.

---

