## 9. Findings (round 1) — the kernel earned its first theorem

The v1 kernel was only meant to be *plumbing* ("alive and conserving", §7.5). It cleared
that bar cleanly — money conserved to ~1e-9, series bounded and moving, seed-robust. But it
also *over-delivered*: three coupled observations emerged that we never encoded, and they
resolve into a single mechanism that we can now **prove**, not just simulate.

### 9.1 Three emergent observations

Running the default kernel ($\rho=0.5$, single seed, 500 ticks): the economy enjoys ~150–210
ticks of full employment (output pinned at its labor ceiling) and then **collapses** into a
low-activity trap (unemployment ≈ 0.94, output ≈ 6). Instrumenting the money distribution
showed the cause is not on the firm side but the household side:

1. **Monotone drain.** Household-sector money falls essentially monotonically (from ~9930 to
   ~50 of a conserved $M=12000$), pooling in firm deposits.
2. **Capped output, no growth.** Output cannot climb past the labor ceiling; there is no
   channel that raises the production frontier.
3. **No self-rescue.** Once depressed, nothing recycles the sequestered firm cash back into
   demand, so the economy cannot climb out on its own.

All three point at one hole: **the closed kernel has no channel that returns retained firm
earnings to the expenditure stream.** A $\rho$-sweep confirmed it — raising the dividend
payout monotonically lifts output and employment and *un-concentrates* wealth:

| $\rho$ | tail unemployment | tail output | hh money share | hh wealth Gini |
|---|---|---|---|---|
| 0.3 | 0.978 | 2.2 | 0.001 | 0.540 |
| 0.5 | 0.936 | 6.4 | 0.004 | 0.451 |
| 0.7 | 0.658 | 34.2 | 0.026 | 0.209 |
| 0.9 | 0.052 | 94.8 | 0.328 | 0.081 |
| 1.0 | 0.005 | 99.5 | 0.833 | 0.107 |

(Note the side-finding: **the depression is also a wealth-inequality trap** — the drained
state has the highest Gini, since a few households retain the last of the circulating money.
Not encoded; emergent.)

### 9.2 The drain identity (proved)

Let $H_t=\sum_h D_{h,t}$ be household-sector money and $F_t=\sum_f D_{f,t}$ firm-sector money,
with conservation $H_t+F_t=M$. Within a tick there are exactly **three** inter-sector flows
(the only `transfer`s the kernel makes): wages $W_t$ and dividends $V_t$ (firm→hh), and
purchases $E_t$ (hh→firm). Hence the sector-flow identity

$$\Delta H_t \equiv H_t - H_{t-1} = W_t + V_t - E_t. \tag{1}$$

Using $E_t=\sum_f \text{revenue}_{f,t}=R_t$, $W_t=\sum_f \text{wagebill}_{f,t}=B_t$,
$V_t=\rho\sum_f\max(0,\pi_{f,t})$, and $\pi_{f,t}=\text{revenue}_{f,t}-\text{wagebill}_{f,t}$
so that $\sum_f\pi_{f,t}=R_t-B_t=:\Pi_t$, equation (1) becomes the **exact** evolution law,
valid in every regime:

$$\Delta H_t = -\!\!\sum_{f:\,\pi_{f,t}\ge 0}\!\!(1-\rho)\,\pi_{f,t}\;-\!\!\sum_{f:\,\pi_{f,t}<0}\!\!\pi_{f,t}. \tag{12}$$

Profitable firms drain households at rate $(1-\rho)\pi_f\ge 0$; loss-making firms *inject*
(they pay more wages than they take in sales), the $-\pi_f>0$ term. **Boom phase** — when all
firms are profitable ($\pi_{f,t}\ge0\ \forall f$) — (12) collapses to the clean form

$$\boxed{\ \Delta H_t = -(1-\rho)\,\Pi_t\ \le 0\ } \tag{8}$$

so household money is drained at *exactly the rate of retained earnings* $(1-\rho)\Pi_t$.

> **Proposition (inevitability of the drain, boom phase).** In the closed, money-conserving,
> equity-choice-甲, no-investment, no-credit kernel, on any interval where every firm's profit
> is non-negative, $H_t$ is monotonically non-increasing with $\Delta H_t=-(1-\rho)\Pi_t$;
> since $H_t\ge 0$ (A4) it is bounded below, hence **converges**, and (8) forces $\Pi_t\to 0$.
> The economy is driven to a profit-zero, low-activity fixed point. The drain halts **iff**
> $\rho=1$ or $\Pi_t\equiv 0$. Parameters ($\rho,\mu_{\max},\eta,\dots$) set only the *rate*
> of descent and the *location* of $H_\infty$ — not the qualitative outcome. The full path,
> including the depression floor, is governed exactly by (12): the floor is the endogenous
> balance between profitable-firm drain and loss-making-firm injection.

This upgrades "depression happens in this run" to "**for all parameters, the boom phase must
monotonically drain households toward a profit-zero fixed point**" — a conditional, checkable
theorem rather than an observation.

### 9.3 Empirical confirmation

Because (1) and (12) are pure consequences of the transfer rules, they must hold **every tick
to machine precision** — an independent check on both the algebra and the ledger. Measured
over the default 500-tick run (`tests/test_household_drain.py`):

- (12) over **all 500 ticks**: max residual $7.3\times10^{-12}$.
- (8) over the **212 all-profitable (boom) ticks**: max residual $7.3\times10^{-12}$.
- $\rho=1$ freezes household money in the boom phase ($|\Delta H_t|<10^{-6}$) — the drain
  stops, exactly as the proposition's "iff".

The simulated $\Delta H_t$ reproduces the pen-and-paper $-(1-\rho)\Pi_t$ to twelve digits.

### 9.4 What this dictates for the roadmap

The theorem localizes the disease to one missing channel, which tells us the *smallest* next
step by parsimony (§0-iv). The retained earnings $(1-\rho)\Pi_t$ are removed from circulation
because nothing spends them. **Investment + capital** (roadmap step 2, ahead of banks) is
the minimal cure: it gives retained earnings an expenditure outlet (treats the drain), lets
capital accumulation raise the output ceiling (treats the cap), and supplies an endogenous
recovery engine (treats the no-self-rescue). It does so **without** introducing money creation
or debt — those (banks/M2) are a strictly larger layer and should come *after*, so each
mechanism's contribution is cleanly attributable. Investment carries a sharp falsifiable
prediction straight out of (8): **once retained earnings are spent on capital, the monotone
firm-deposit accumulation should reverse and drive a self-generated recovery.** If it does,
the causal chain is closed in both directions. This is specified in §10 and is the v2 layer.

---

## 10. v2 — Investment and capital (the two-sector economy)

This section specifies roadmap step 2, in the same "executable on paper" style as §7. It is
the minimal layer that the §9 theorem tells us to build: it gives retained earnings an
expenditure outlet, endogenizes the output ceiling, and supplies a recovery engine — while
adding **no** money creation (that is the strictly larger banks/M2 layer, deliberately
after). Scope inherits everything from the kernel except where extended here.

### 10.1 What v2 adds, and the prediction it must meet

v2 splits the single firm type into **two sectors** and lets consumption firms accumulate
capital by buying from capital firms. The §9 drain is cured through a specific channel that
must be kept visible (10.3). The headline, falsifiable, pass/fail-adjacent prediction (from
(8) in §9.4):

> **Investment reverses the drain.** With retained earnings now spent on capital goods, the
> previously *monotone* firm-deposit accumulation should reverse or stabilize, household
> money should stop its monotone decline, and the economy should settle in a bounded,
> **active** state rather than the v1 depression trap. Endogenous investment-driven cycles
> (multiplier–accelerator) would be a welcome bonus, not a requirement.

### 10.2 Structure and the four locked decisions

- **Two sectors.** $\mathcal{F}_C$ = consumption-goods firms; $\mathcal{F}_K$ =
  capital-goods firms. Households supply labor to **both** and consume only the consumption
  good. $\text{Goods}=\{\text{consumption},\text{capital}\}$ (the §7.3 interface, now live).
- **Shared behavioral core.** Both sectors use the *identical* B2 expectations, B3 cost-plus
  pricing, B4 DNWR wages, and inventory-buffer production targeting. They differ **only** in:
  (i) production function, (ii) which good they make, (iii) who buys it, and (iv) only
  $\mathcal{F}_C$ invests (B5). No second behavior codebase.
- **Cut capital recursion.** $\mathcal{F}_K$ produces with **labor only**; capital
  accumulates **only** in $\mathcal{F}_C$. Deliberate asymmetric simplification.
- **Capital is real, not money.** Buying capital is a deposit transfer (conserved); the
  capital stock $K$ is a real outside asset accumulated by perpetual inventory and is
  **excluded** from money conservation (§1 real-vs-financial; §8.2 warning).

### 10.3 The money-return channel — keep it visible

Investment returns money to households in **two steps**, not one. The transfer
$\mathcal{F}_C\!\to\!\mathcal{F}_K$ (buying machines) is firm-to-firm and does **not** by
itself reach households. The return happens because $\mathcal{F}_K$ is **labor-only**: its
revenue is paid out mostly as **capital-sector wages** to households, plus dividends. So

$$\underbrace{\text{retained earnings of }\mathcal{F}_C}_{\text{previously sequestered}}
\ \xrightarrow{\ \text{buy capital}\ }\ \mathcal{F}_K
\ \xrightarrow{\ \text{wages }B_K\,+\,\text{dividends}\ }\ \text{households}.$$

The cure is **partial**: $\mathcal{F}_K$ itself retains $(1-\rho)\pi_K$, a smaller secondary
drain. Whether household money stabilizes is therefore exactly the **empirical question**
v2 answers — the mechanism is present and visible, the quantitative outcome is not assumed.
Do not expect the $\mathcal{F}_C\!\to\!\mathcal{F}_K$ transfer *alone* to lift household
money; watch $B_K$ (capital-sector wages).

### 10.4 Operational equations (deltas from §7.2)

Expectations (B2), wages (B4), pricing (B3), consumption (B1), settlement/dividends, and the
conservation gate are **unchanged** and apply per sector. What changes or is added:

**Production functions.**
$$\underbrace{y_{C,f,t} = A\, K_{f,t-1}^{\alpha}\, N_{C,f,t}^{\,1-\alpha}}_{\text{consumption sector, }\alpha\in(0,1)},
\qquad
\underbrace{y_{K,f,t} = a_K\, N_{K,f,t}}_{\text{capital sector, labor only}}.$$
Capital is **predetermined** ($K_{f,t-1}$ used this tick), avoiding within-tick simultaneity.

**Labor demand (invert for the production target), cash-capped (A4), continuous.**
$$N^{d}_{C,f,t} = \Big(\tfrac{y^{*}_{C,f,t}}{A\,K_{f,t-1}^{\alpha}}\Big)^{\!1/(1-\alpha)},
\qquad
N^{d}_{K,f,t} = \tfrac{y^{*}_{K,f,t}}{a_K},
\qquad
N^{d,\text{eff}}_{f,t} = \min\!\big(N^{d}_{f,t},\ D_{f,t-1}/w_{f,t}\big).$$

**Unit labor cost for the markup (B3), same rule, capital treated as sunk.**
$$uc_{C,f,t} = \frac{w_{f,t}\,N^{d}_{C,f,t}}{y^{*}_{C,f,t}}\ \ (\text{planned avg. labor cost; rises with output under diminishing returns}),
\qquad
uc_{K,f,t} = \frac{w_{f,t}}{a_K}.$$

**Investment (B5), consumption firms only.**
$$K^{*}_{f,t}=v\,y^{e}_{C,f,t},
\qquad
I^{*}_{f,t}=\max\!\big(0,\ \lambda_I(K^{*}_{f,t}-K_{f,t-1})+\delta_K K_{f,t-1}\big).$$
$I^{*}_{f,t}$ is a notional demand for capital goods, taken to the capital-goods market and
capped by cash and by matched supply (M1):
$$I_{f,t} = \text{realized purchase} \le \min\!\big(I^{*}_{f,t},\ D_{f,t}/p^{K}_{\text{seller}},\ \text{matched capital-good supply}\big).$$

**Capital law of motion (A2 on the real stock).**
$$K_{f,t} = (1-\delta_K)\,K_{f,t-1} + I_{f,t}.$$
New capital is productive from $t+1$.

**Conservation with capital (implementer warning restated).** Money conservation is over
**deposits only**, three sectors:
$$\sum_h D_h + \sum_{f\in\mathcal{F}_C} D_f + \sum_{f\in\mathcal{F}_K} D_f = M \quad \forall t.$$
$K$ is **not** in this sum. The investment purchase is the paired transfer
$\mathcal{F}_C\!\to\!\mathcal{F}_K$ that keeps it balanced.

### 10.5 The v2 tick (deltas from §6.3)

Same synchronous-plan / sequential-markets / settlement / check skeleton. Additions:

- **Phase 1 (plan).** C-firms additionally compute $K^{*},I^{*}$ (B5); K-firms plan
  capital-good production from expected capital-good demand; both sectors compute labor
  demand by inverting their own production functions.
- **Phase 2 (labor market).** Now a **single pool**: both sectors post labor demand and
  compete for the fixed household labor supply (M1, rationed, cash-capped). Wages paid →
  households. Both goods produced.
- **Phase 3 (consumption-goods market).** Unchanged: households buy the consumption good
  from C-firms.
- **Phase 3.5 — NEW (capital-goods market).** C-firms buy capital goods from K-firms (M1,
  rationed, cash-capped). Money $\mathcal{F}_C\!\to\!\mathcal{F}_K$; purchased units leave
  K-firm inventory and enter the buyer's capital stock. (Placed after Phase 3 so investment
  can draw on deposits including this tick's sales revenue; investment is financing out of
  the deposit stock, not a profit-and-loss expense.)
- **Phase 4 (settlement).** Profits and dividends computed for **both** sectors (same rule,
  §7.2). **Capital accumulation** committed: $K_{f,t}=(1-\delta_K)K_{f,t-1}+I_{f,t}$.
- **Phase 5 (check).** Conservation over three sectors of **deposits**; $K$ excluded. Record
  aggregates, now split by sector and including investment, capital stock, and sector money.

### 10.6 Extended state variables

| Agent | State carried across ticks |
|---|---|
| Household $h$ | deposits $D_h$; expected income $Y^{e}_h$ *(unchanged)* |
| C-firm $f\in\mathcal{F}_C$ | deposits $D_f$; consumption-good inventory; **capital $K_f$**; price; wage; markup; expected (consumption) demand; + cross-tick: $K_{f,t-1}$, last $K^{*}$, last $N^{d,\text{eff}}$ & hiring |
| K-firm $f\in\mathcal{F}_K$ | deposits $D_f$; **capital-good inventory**; price; wage; markup; expected (capital-good) demand; + cross-tick: last $N^{d,\text{eff}}$ & hiring |

**Initial endowments (v2).** As kernel, plus: each C-firm starts with $K_f(0)>0$ (else
Cobb–Douglas output is 0), and K-firms start with enough deposits to fund a first wage bill.
Total money $M$ over all three sectors is conserved (M0).

### 10.7 Extended parameter budget (deltas; per §0-iv)

New rows on top of §7.4:

| Symbol | Meaning | Default / magnitude | Status |
|---|---|---|---|
| $v$ | desired capital–output ratio (accelerator) | $\sim 2\text{–}3$ (soft) | **free** — core dial; pays its way (unlocks the whole investment/recovery mechanism) |
| $\lambda_I$ | investment adjustment speed (damping) | $(0,1]$ | **free** — the stability knob for accelerator overshoot |
| $\delta_K$ | capital depreciation rate | small | **anchored** (empirical depreciation) + maintenance-investment floor |
| $\alpha$ | capital share (Cobb–Douglas) | $\sim 0.3$ | **anchored** (capital income share) |
| $A$ | TFP, consumption sector | normalize | **scale** — normalizable like $a$ |
| $a_K$ | labor productivity, capital sector | — | **scale**, *but* the $A{:}a_K$ ratio sets relative sector productivity/prices → meaningful, verify |
| $N_{F_C},N_{F_K}$ | firm counts per sector | large enough | **scale** |
| $K_f(0)$ | initial C-firm capital | $>0$ | **transient** (must wash out), but strictly $>0$ required |

**Parsimony read-out (v2).** Genuinely-free behavioral dials go from **5 → 7** (adding $v,
\lambda_I$). This is justified under §0-iv: $v$ and $\lambda_I$ are not fitting knobs but the
*mechanism itself* — they parametrize the cure for the **proved** §9 drain and the newly
**endogenous** output ceiling, unlocking regularities (self-recovery, and candidate
multiplier–accelerator cycles for §4) unobtainable without them. $\delta_K,\alpha$ are
empirically anchored; $A,a_K,N_{F_\bullet}$ are scale. No dial was added that does not pay
its way; the discipline holds.

### 10.8 v2 milestone and acceptance (conservative)

Do not chase §4 laws. v2 "done" is:

1. **Conservation holds.** The three-sector deposit sum equals $M$ every tick (assertion
   never trips); $K$ correctly excluded from that sum.
2. **Drain reversal (the §9.4 prediction).** Sector-money series show the previously
   monotone firm-deposit accumulation reversing or stabilizing, and household money no longer
   monotonically falling — attributable to $B_K$ (capital-sector wages) recirculating
   C-firm retained earnings.
3. **Alive and bounded, not trapped.** The economy settles in a bounded active state, not
   the v1 depression fixed point; the output ceiling now moves with $\sum_f K_f$ (endogenous
   growth of the frontier).

Endogenous investment-driven cycles are a **welcome bonus**, not a pass/fail bar (conservative
acceptance, progressive architecture). Deliver the standard four (kernel/loop, conservation
gate, diagnostic plot, seed-invariance) **plus** the drain-reversal sector-money check.

If v2 holds, the §9 causal chain is closed in both directions: removing the recirculation
channel *caused* the collapse (v1); restoring it *cures* it (v2). Expected first-run caveat
(B5): the accelerator may oscillate or diverge before $(v,\lambda_I,\delta_K)$ are tuned into
a bounded regime — calibration, not plumbing.

---

## 11. Findings (round 2) — endogenous cycles, and the drain theorem goes fractal

v2 was built to test one prediction (§10.8): does giving retained earnings an expenditure
outlet reverse the §9 drain? It did — and running it out to long horizons then revealed two
deeper results the short run hid. All three below are verified against the running system to
machine precision using the §9 identities as instruments.

### 11.1 v2 cures the primary drain and produces genuine business cycles

At short/medium horizons (≲1500 ticks) v2 escapes the v1 depression: household money share
rises **0.4% → 4.7%** (~12× more retained, seed-robust), unemployment falls **93% → ~10%**
(cv≈0.03 at large N), output rises **~6 → ~100**, and capital collapses then endogenously
recovers. Money no longer pools dead in one sector; it circulates
$\mathcal F_C\!\to\!\mathcal F_K\!\to$ households via capital-sector wages $B_K$.

More than that, **a genuine endogenous business cycle emerges** — never encoded. Over 3000+
ticks the capital stock $\sum_f K_f$ oscillates in low-frequency waves (period ~500–750
ticks) with strong comovement — $\mathrm{corr}(\text{output},\text{employment})=0.95$,
$(\text{output},\text{investment})=0.74$, $(\text{output},\text{capital})=0.82$. The
mechanism is the multiplier–accelerator visible directly in the series: the accelerator (B5)
reacts to the *change* in demand, so once capital catches up to demand, investment turns
down (overshoot → collapse), dragging $B_K$ and demand into recession; depreciation then
draws capital down until it is low enough for investment to reignite. Overshoot → collapse →
depreciation → reignition, on repeat.

> **Discipline (§0-ii).** Business-cycle comovement is a §4 *held-out target*. Seeing it
> emerge is strong but is an **observation, not a validated result** — a rigorous claim needs
> detrending, spectral analysis, and many seeds. Recorded as promising, not banked.

### 11.2 The §9 drain theorem is fractal — and the long run proves v2 only *transfers* it

The §9 proposition, stated for v1's household sector, is really a **universal structural
principle**: *any sector that retains positive profit with no recirculation channel is a
money sink.* In v1 that sector was "all firms"; v2 gave $\mathcal F_C$'s retained earnings an
outlet (investment → $B_K$) and filled that sink — but we never gave $\mathcal F_K$ one, so
the theorem **reasserts itself, unbidden, in the capital sector.**

The 10 000-tick / 3-seed adjudication makes this concrete. K-sector money climbs and
**saturates at ~80% of $M$** (bounded — the money-stock ceiling $M$ binds; it is *not* an
unbounded runaway), while unemployment drifts **up in every seed** (early 0.10–0.18 → late
0.43–0.94) and C-firm deposits are progressively drained. So v2 did not *eliminate* the
disease — it **transferred** it from households to the consumption-production sector and
**slowed it** by ~an order of magnitude in time. The beautiful ~10% cycles of the medium run
are the expansion phase of a much slower structure, not the steady state. (The long run is
**not** seed-invariant — endpoint severity depends on which phase of the slow cycle a run
ends in; short-run seed-invariance does not extend here.)

### 11.3 The secondary sink *oscillates* — it is a sink in boom, a source in bust

This is the essential difference from v1, and it must not be flattened. v1's sink was
**monotone** ($\Delta H_t\le 0$ strictly, §9). The K-sink is not — it **oscillates**, and (12)
explains exactly why. The K-sector budget identity is

$$\Delta(\text{K money})_t = R_{K,t} - B_{K,t} - V_{K,t} = \Pi_{K,t} - V_{K,t}.$$

In **boom** ($\Pi_K>0$): $\Delta=(1-\rho)\Pi_K>0$ — K accumulates, a **sink**. In **bust**
($\Pi_K<0$): dividends $V_K=0$, so $\Delta=\Pi_K<0$ — K **releases**, a **source**. That
release is precisely the $-\pi<0$ term of (12): a loss-making sector *injects* money. So the
mechanism self-limits: K hoards until it starves its own customers, C-profit and investment
collapse, K then makes losses and disgorges what it hoarded, funding a partial recovery — the
engine of the slow **super-cycle** (~2500–3000 ticks) riding atop the fast accelerator cycle.
v2 is therefore **self-correcting but painfully so** — the correction is triggered only by
deep depression, closer to a "recession-liquidation" dynamic than to v1's irreversible slide.

**Verified to machine precision (the §9 identities as guards):**
- Household identity $\Delta H_t = B_t+V_t-R_{C,t}$ holds every tick; at the **deepest trough**
  ($t{=}6984$, $u{=}0.999$, capital ≈ 0) the residual is $8.9\times10^{-16}$, and over all 2932
  $u>0.9$ ticks the max residual is $7.4\times10^{-13}$. **An exact accounting identity cannot
  hold at machine precision in a numerically broken state**, so the near-total-unemployment
  phase is a *real* deep depression, not a degenerate numerical corner. (This is the theorem's
  second use: guarding our reading of extreme states.)
- K-sector budget identity holds to $5.7\times10^{-11}$; across the run K **accumulates** on
  its 8440 boom ticks (mean $\Delta=+1.77$) and **releases** on all 1281 bust ticks (mean
  $\Delta=-3.85$; 100% releasing), injecting ~4928 (≈⅓ of $M$) back during downturns.

### 11.4 What this dictates: symmetrize capital (v2.5) before banks

Two cures are on the table; parsimony (§0-iv) orders them.

- **v2.5 — symmetrize the capital sector (recommended next).** The K-sink's root cause is an
  asymmetry *we introduced* for simplicity ("cut capital recursion", §10.2): $\mathcal F_K$ is
  labor-only and cannot invest, so its retained earnings have no outlet. Letting K-firms also
  use capital and invest gives those earnings a channel — **without** money creation, keeping
  the clean regime where our identities remain guards. It is small, safely bounded (capital
  predetermined + depreciating + cash-capped: no within-tick recursion), and carries a sharp
  **falsifiable prediction**: since K-firms would buy capital *from* K-firms (an intra-sector
  wash at the sector level), the cure acts only indirectly — through extra K-production →
  higher $B_K$ wage leakage — so it should **partially, not fully, drain the secondary sink.**
  Full cure ⇒ the sink was pure self-inflicted asymmetry; partial cure ⇒ an intrinsic
  component remains, which is exactly what only banks can address. Either outcome sharpens the
  case for M2.
- **Banks / M2 (later, reserved).** A qualitative layer (breaks money conservation, adds debt,
  leverage, Minsky dynamics). It treats the *general* disease — money stuck anywhere,
  recirculated by credit — and should be spent on what only it can do (financial crises pushing
  a healthy economy off a cliff), not on a sink we dug ourselves.

A trivial calibration lever ($\rho_K$: pay out more of K-profit) exists as a control arm but
only masks the sink; symmetrization is the principled structural fix.

### 11.5 Both parsimonious fixes fail — banks are *earned*, not assumed

Before spending the heavy banks layer, we tested the two cheaper cures. Both failed, each in a
cleanly diagnosable way — and that pattern is itself the strongest possible argument for M2.

**Symmetrization (v2.5) is structurally unstable — falsified, not mis-implemented.** Letting
K-firms also use capital and invest (undoing §10.2's "cut the recursion") **robustly collapses
the economy** to $K=0$, output $=0$, $u=100\%$ across every parameter tried ($\delta_K, A, a_K,
K_0, N_K$). Two failure modes were disentangled to be sure it was structural, not a calibration
artifact:
- *Demand side (calibration):* the accelerator sizes a K-firm's desired capital
  $K^{*}=v\,d^{e}$ from its capital-good demand *in units* (~3.4), giving $K^{*}\approx 8.4$ —
  below its stock — so it never reinvests and lets capital depreciate.
- *Supply side (structural, the real killer):* capital-good output now itself requires capital
  ($y_K=A K_K^{\alpha}N_K^{1-\alpha}$), so a dip in $K$ lowers capital-good supply, which starves
  replacement, which lowers $K$ further — an **absorbing zero state with no floor.**

A decisive test separates them: adding a **replacement floor** (force each K-firm to invest at
least $\delta_K K$, removing the demand-side "never invests" failure entirely) **still
collapses** — and the smoking gun is that floored K-firms *want* to invest (~1.89/tick) but
realize **0.00, 100% supply-rationed.** So the collapse is the supply-side absorbing state,
independent of calibration. **This vindicates §10.2's recursion cut as stability-critical**: a
capital-goods sector that depends on capital has a no-floor collapse trap.

**Raising the payout $\rho$ is caught between two opposed failure modes.** $\rho\to1$ *does*
stop retained-earnings hoarding (§9), but it breaks the economy the *other* way: with no
retained profit, firms have no **working capital**, and since wages are paid (Phase 2) *before*
sales revenue arrives (Phase 3), cash-starved firms cannot fund their wage bill → $u=100\%$. So
the two constraints are structurally opposed — *retain too much ⇒ money sink; retain too little
⇒ working-capital starvation* — and no $\rho$ is clean **by construction** (independent of the
single-seed super-cycle-phase noise that also muddies $\rho$ comparisons). The healthy band is
interior, but the lever cannot *cure* the sink, only trade it against starvation.

**Conclusion (earned).** The secondary K-sink resists both parsimonious fixes: the structural
one (symmetrize) is unstable by an absorbing trap; the calibration one ($\rho$) is boxed between
sink and starvation. The deeper diagnosis: *both* pathologies stem from the same root — a
**fixed** money stock ($M$ constant, M0) that a hoarding sector can monopolize, starving
everyone else's circulation and working capital. The mechanism that dissolves that root without
recursion or a payout trade-off is exactly **M2 endogenous money** (§3): loans *create*
deposits, so a cash-starved borrower receives **newly created** money — it is **not** re-lending
K's idle deposits (that is the money-multiplier story M2 rejects). Credit does not *recirculate*
the hoarded pile; it **removes the zero-sum constraint that made hoarding fatal.** With
endogenous money, hoarding in K persists but no longer strangles the rest, because funding is no
longer gated by a fixed stock. Banks/M2 is therefore no longer a roadmap default — it is the
mechanism two failed experiments have *demanded*, and the failures also tell us *precisely what
it must do*: create money for cash-short borrowers (wages, investment). The cleanest motivation
the project has produced for any layer — not "the roadmap says so," but "every cheaper option
fails in a diagnosable way, and the reserved mechanism's specific job is now pinned by the
failures."

### 11.6 Information transparency decouples price discipline from market structure

Making buyer price-comparison a continuous dial (`SampledCompareMatch(m)`: sample m sellers,
buy the cheapest; m=1 blind, m large = full comparison; §5) turned the old "RandomMatch vs
PriceSortedMatch" binary into an axis we could **sweep**. The result is two decoupled effects
moving in *opposite* directions with transparency:

- **Price level — markup falls smoothly and monotonically** with m (~0.92 at m=1 → ~0.36 at
  m=100). Competition on price works exactly as expected, and continuously: each extra seller
  a buyer compares squeezes the markup further.
- **Market structure — concentration *rises*, sharply, at m=1→2** (firm-size Gini 0.80 → 0.97;
  producing firms 25 → ~3 of 100), then plateaus. This is the **opposite** of the naive
  "transparency ⇒ competition ⇒ many firms." The mechanism is increasing returns to capital
  (Cobb-Douglas: more capital ⇒ lower unit cost ⇒ lower price) **coupled with** price
  transparency: the moment buyers can compare (m≥2), they funnel to the low-cost firm, which
  grows, gets cheaper, and runs away. Blind matching (m=1) *preserves* many firms precisely by
  spreading demand at random. So **transparency disciplines prices but concentrates markets.**

> **Discipline (§0-ii, and a confound).** This is an *observation*, not a validated §4 result
> (single scale, 3 seeds, 1000 ticks). And it is confounded: with **no firm entry/exit**, every
> configuration trends to the winner-take-all (Gini ≈ 0.97), so the extreme concentration is
> partly the *no-exit* pathology, not transparency alone. A clean characterization of the
> market-structure ↔ transparency relation (is there a stable oligopoly at intermediate m?
> where is the critical transparency?) therefore **needs firm entry/exit first** — this
> experiment sharpens that need. The markup↓ result is robust to the confound.

---

## 12. v3 — Banks and endogenous money (the credit layer)

This operationalizes roadmap step 3, in the same "executable on paper" style as §7 and §10. It
is the layer §11.5 *earned*: two failed parsimonious fixes for the K-sink proved the disease is a
**fixed money stock** a hoarding sector can monopolize, and M2 endogenous money dissolves it. v3
adds a bank, opens A4's credit term, and switches the hard anchor from money conservation (M0) to
net-worth conservation (A5). It adds **no default** — that is v3.5. Scope inherits v2 except where
extended.

### 12.1 What v3 adds, and the prediction it must meet

A single bank; firms borrow (B6) to cover any cash gap (wages + investment); the bank lends up to
a leverage multiple of financial net worth (B7); loans create deposits (M2); fixed-proportion
amortization and an exogenous rate $r$; no default. The falsifiable prediction, straight from
§11.5:

> **Endogenous money relaxes the fixed-stock strangulation.** Cash-short firms fund wages and
> investment with *newly created* deposits, so hoarding in the K-sector no longer starves the
> rest. Broad money $\sum D$ becomes a **live series** (credit expanding and contracting) instead
> of a flat line, while net worth $\sum D-\sum L$ stays pinned to $M$. The economy should stay
> bounded and active rather than deteriorating into the §11.2 super-cycle depression. A **credit
> cycle** (leverage-driven boom–bust, Minsky) would be a welcome §4 observation, not a pass/fail
> bar.

### 12.2 Structure and decisions

- **Single bank** $\mathcal{B}$: an active money-creator with exactly one lending rule (B7).
- **Firms are passive credit demanders** (B6): borrow only the shortfall of planned spending
  (wage bill + desired investment) over cash, up to the B7 cap. Credit is logged **by purpose**
  (investment vs wage) so the relaxed cash-capped hiring (§B6) stays attributable.
- **Loans create deposits** (M2, four-entry via a `create_loan` primitive) → A5 unbreakable by
  construction.
- **Fixed-proportion amortization**; **exogenous interest $r$** (rate-setting → central-bank layer).
- **No default** (firms service or roll over; shortfalls defer, never trigger bankruptcy) →
  default/crisis is **v3.5**.
- **Financial net worth only** in B7 ($D-L$); capital-as-collateral → v3.1.
- **Base money / reserves $R$**: the bank holds $M$ of reserves so deposits are backed and its
  balance sheet is consistent; $\sum R=M$ (§A5). Not a multiplier — reserves *carry* $M$, do not
  *limit* lending.

### 12.3 The accounting shift — A5 is the new gate

See A5. The hard gate moves from $\sum D=M$ (M0) to $\sum_i D_i-\sum_i L_i=M$; additionally
$\sum R=M$. Broad money $\sum D$ is now an **endogenous recorded series**, not an assertion.
Interest is a plain `transfer` (redistributes; net worth invariant); principal creation/repayment
goes through `create_loan`/`repay` (moves $\sum D$ and $\sum L$ together; net worth invariant).

### 12.4 Operational equations (deltas from §10.4)

Everything in v2 is unchanged except the cash constraint (A4's credit term is now live) and the
two new credit steps.

**Credit demand (B6).** Cash gap and requested loan:
$$\text{gap}_{f,t}=\max\!\big(0,\ w_{f,t}N^{d}_{f,t}+p^{K}I^{*}_{f,t}-D_{f,t}\big),\qquad
\Lambda^{\text{req}}_{f,t}=\text{gap}_{f,t}.$$

**Credit supply (B7).** Financial net worth and leverage cap:
$$NW_{f,t}=D_{f,t}-L_{f,t},\qquad
\Lambda_{f,t}=\max\!\big(0,\ \min(\Lambda^{\text{req}}_{f,t},\ \kappa\,NW_{f,t}-L_{f,t})\big).$$

**Loan creation (M2).** $\;D_{f}\mathrel{+}=\Lambda,\ L_{f}\mathrel{+}=\Lambda$ (borrower);
bank loan-asset $+\Lambda$, bank deposit-liability $-\Lambda$. $\sum D-\sum L$ invariant.

**Debt service (amortization + interest).** Each tick the firm repays principal
$\min(\text{amort}\cdot L_{f,t},\ D_{f,t})$ via `repay` (shrinks broad money) and pays interest
$\min(r\,L_{f,t},\ \text{cash after amort})$ via `transfer` to the bank. Any shortfall **defers**
(no penalty, no default in v3). Bank profit is interest received minus its own wage/operating
costs (in the minimal v3 the bank has no labor; its profit is retained interest, distributed to
households as dividends like any firm, closing the loop).

### 12.5 The v3 tick (deltas from §10.5)

Same synchronous-plan / sequential-markets / settlement / check skeleton. Additions:

- **Phase 1 (plan).** As v2: expectations, production target, wage, price, desired investment
  $I^{*}$ (B5), and the wage-bill target $w_f N^{d}_f$.
- **Phase 1.5 — NEW (credit).** Each firm computes its cash gap over *planned* spending (wages +
  investment) and requests a loan (B6); the bank grants up to the B7 cap; `create_loan` credits
  the deposit (M2). Placed **before the markets** so credit can fund *this* tick's wage bill —
  this is what relaxes the v1/v2 cash-capped hiring.
- **Phase 2 (labor).** As v2, but the hiring cash-cap now reads deposits *including* new credit.
- **Phase 3 / 3.5 (consumption / capital markets).** As v2; investment is now fundable by credit.
- **Phase 4 (settlement).** Profits, dividends (both firm sectors + the bank), capital committed.
- **Phase 4.5 — NEW (debt service).** Amortization (`repay`) + interest (`transfer`), per 12.4;
  shortfalls defer.
- **Phase 5 (check).** Assert **A5** ($\sum D-\sum L=M$) and $\sum R=M$ — not M0. Record broad
  money $\sum D$, total credit $\sum L$, bank equity, aggregate leverage, and credit split by
  purpose (investment vs wage).

### 12.6 Extended state variables

| Agent | State carried across ticks |
|---|---|
| Household $h$ | deposits $D_h$; expected income $Y^{e}_h$ *(unchanged)* |
| Firm $f$ | *(as v2)* + **loan debt $L_f$** |
| Bank $b$ | reserves $R_b=M$; per-borrower loan assets $\{L_f\}$; deposit liabilities; own deposits (retained interest) |

**Initial endowments (v3).** As v2, plus: firms start with $L_f(0)=0$; the bank starts with
reserves $R=M$ (= the genesis deposit total) and zero loans, so its balance sheet nets to zero
equity and A5 holds at $t=0$ ($\sum D-\sum L=M$).

### 12.7 Extended parameter budget (deltas; per §0-iv)

| Symbol | Meaning | Default / magnitude | Status |
|---|---|---|---|
| $\kappa$ | max leverage multiple (B7) | $\sim 2\text{–}5$ | **free** — core dial; controls procyclical-leverage strength / the Minsky flavor; and the taming knob for credit's positive feedback |
| $r$ | loan interest rate | small, e.g. $0.5\text{–}2\%$/tick | **anchored/free** — has an empirical referent but exogenous in v3; endogenized at the central-bank layer |
| amort | principal repaid / tick | $\sim 0.05\text{–}0.1$ | **free** — sets debt-rollover speed |
| $R(0)$, bank equity | bank genesis reserves/capital | $R=M$ | **transient/scale** — set by genesis; verify washes out |

**Parsimony read-out (v3).** Genuinely-free behavioral dials go **7 → ~9** (adding $\kappa$, and
$r$/amort if treated as free). Justified under §0-iv: $\kappa$ is not a fitting knob but the
*mechanism* — it parametrizes procyclical leverage, unlocking the **credit-driven boom–bust**
that §4 explicitly lists and that v1/v2 cannot produce; $r$ is the price of debt. No dial was
added that does not pay its way.

### 12.8 v3 milestone and acceptance (conservative)

Do not chase §4 laws. v3 "done" is:

1. **A5 holds.** $\sum D-\sum L=M$ and $\sum R=M$ every tick, to machine precision (assertion
   never trips). Broad money $\sum D$ is correctly a *live, endogenous* series — no longer a flat
   line, no longer asserted.
2. **Credit relaxes the cash constraint.** There exist ticks where a firm's wage bill or
   investment was cash-constrained in v2 but is credit-funded in v3 — read off the credit-by-purpose
   log (B6). This directly checks that A4's credit term is doing work.
3. **Bounded and active, not trapped.** The economy stays bounded and does not deteriorate into
   the §11.2 super-cycle depression the way credit-less v2 did over long horizons.

A **credit cycle / Minsky leverage dynamics** is a welcome §4 *observation* (candidate for
"credit-driven boom–bust"), not a pass/fail bar — and per §0-ii it is recorded as observed, not
validated, until studied rigorously. Deliver the standard four (loop, conservation→A5 gate,
diagnostic plot, seed-invariance) **plus** the broad-money endogeneity series and the
credit-by-purpose split.

**Expected first-run caveat.** Credit is a positive-feedback amplifier; v3's first run may be
**more volatile — or divergent — than v2**. $\kappa$ is the primary taming knob (as $\lambda_I$
was for the accelerator). Divergence with A5 intact is calibration, not plumbing.

If v3 holds, §11.5's earned conclusion is confirmed constructively: the fixed-stock strangulation
was the root, and endogenous money dissolves it — while planting the leverage cycle whose *crash*
(default, §4 credit-boom-bust in full) v3.5 will complete.

---

