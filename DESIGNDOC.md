# Axioms of the Agent-Based Macroeconomy

**A living specification.**
Version `2.23` · Status: **draft, round 34 — v12 the SECURITIES arc (v12.0–v12.4, CLOSED): un-consolidate the CB, issue BONDS, sterilise reserves (§39). v12.4 (§39.6): the CB's QUANTITY tools — the reserve total becomes VARIABLE (`issue_reserves`/`retire_reserves`, gate `Σreserves=_reserve_M` exact by construction ⇒ every prior config bit-identical); **OMO drains reserves scarce ⇒ the §37 interbank market, latent since v11.4, finally BINDS** (peak overdraft ≈11k, interbank_volume>0, up from exactly 0 — the arc's keystone), QE re-latents; LoLR funds an illiquid-but-solvent bank (no suspension cascade) + a duration limit caps the bank bond book. `test_v12_bonds` 9/9, 30-suite green, `diagnostic_v124.png`. Honest scope: OMO→interbank is the clean verified win; durable large-bank-bond survival needs banks to RETAIN equity (a v11.5 recalibration). NEXT (health lever, not plumbing): v13 search-matching LABOUR (natural rate ⇒ T4). v12.3 (§39.5): bonds gain MATURITY+COUPON+market price (three values DIVERGE); households hold a `bond_theta` portfolio (liquid, no re-freeze — SHIPPED ON); the BANK balance sheet + duration/SVB are BUILT & conservation-verified (ledger refactor: `_bank_securities` first-class, A5 gate → `ΣD−ΣL−_bank_securities=M`, money-creating `bank_buy_bond_with_reserves`, `economic_capital=balance+bond-P&L`) but gated OFF (`bank_bond_appetite=0`) because the live bank drain collapses the thin-equity sector at a 5–7% rate vs 1% coupon (the 2023-SVB structure) with no LoLR ⇒ activation is v12.4. `test_v12_bonds` 6/6, 30-suite green, `diagnostic_v123.png`. The keystone tier, accounting HARDENED over 4 review rounds. Core rules: a bond has THREE values — face (bond identity Σholdings@face=outstanding), book (bank-money invariant ΣD−ΣL−Σbank-bonds@book=M₀), market (wealth/economic_capital); a BANK buying a govt bond CREATES money, a HOUSEHOLD buying is a deposit↔bond swap; MASTER conservation (mix-independent, book) = private NFA = M₀ + cumulative deficit = govt total net liability; the CB un-consolidates into TSY (fiscal deposit acct) + CB (reserves=liability, bonds+TSY-claim=assets), with a TGA (Treasury's cash at the CB = the SAME cash as D_TSY from the reserve side, never a 2nd asset). v12.0: GOV→TSY+CB behind a `_fiscal` id + inert CB scaffolding + securities-identity gates as no-ops ⇒ BIT-IDENTICAL to v11.5 (no diagnostic — bit-identical versions add nothing). v12.1: Treasury holds `bond_finance_frac` of debt as one-period PAR bills (face=book=market, coupon 0) held by households; all four gates hold every tick. FINDING (an ARTIFACT caught via the diagnostic, then corrected): a first cut allocated bills pro-rata to ALL deposits → drained TRANSACTION balances → cash-capped B1 consumption → demand collapse (u 0.007→0.35); FIX-1 = buy bills only from IDLE SAVINGS (deposits above a transaction buffer). A SECOND artifact then showed over LONG runs: idle-savings bills never matured (the phase targeted a STOCK, netted the gap) → a FREEZE RATCHET locked savings into non-spendable zero-coupon bills → the α2·D consumption term withered → downward spiral (u→0.25, bonds→3.06M at f=0.9/4000t, while gov_debt stayed IDENTICAL to f=0 ⇒ pure private-liquidity composition, NOT fiscal; NOT bank crowding-out — banks_alive recovers). FIX-2 (v12.1-fix, bill ROLLOVER) = honour "one-period bill" literally: `_phase_bill_maturity` redeems every bill to deposits at the TOP of the tick (bills liquid all tick ⇒ feed consumption/goods-cap/equity/founding with NO behavioural-code change) + `_phase_bill_issuance` re-sweeps only end-of-tick idle over a THICKER buffer. Result: f=0.9 now BIT-IDENTICAL to f=0 in u/banks_alive/gov_debt across all windows (pre-registered, confirmed); the planned haircut/`_make_cash` bridge dropped as unnecessary. New honest consequence: intra-tick-liquid + zero-coupon ⇒ no reason to hold OVERNIGHT ⇒ bill stock collapses to a thin residual (~33k, ~0.5% of debt) ⇒ sterilisation minimal; a MEANINGFUL bond stock needs the DEMAND side (coupon + `bond_theta`) = v12.3, which will now grow it WITHOUT re-freezing (bills are liquid). `Config.v12()` = frac 0.9; off (or frac=0) ⇒ bit-identical. New levers bonds/bond_finance_frac/bond_coupon/bond_theta; `test_v12_bonds` 3/3 (incl. no-demand-artifact); full regression green (30 scripts). Next: v12.2 bank balance sheet (bank buys bonds with RESERVES → money creation, economic_capital) → v12.3 traded market + duration/SVB → v12.4 OMO/QE (activates interbank) + LoLR. Prior (§38): v11.5 bank demographics.** · Last updated: 2026-07-07

---

## 0. Purpose and epistemic stance

This document specifies the *axioms* of an agent-based macroeconomic simulation: the
minimal set of primitives from which we want complex macro behavior to **emerge**,
rather than be assumed. It is the constitution of the project. Everything downstream —
architecture, scheduling, data structures, validation — should be derivable from or
consistent with what is written here.

We maintain three hard distinctions throughout. They are the backbone of the whole
design; if a proposed rule cannot be placed cleanly into one of these buckets, that is a
signal it has not been thought through.

**(i) Identities vs. behavior.**
An *identity* is true by definition (double-entry accounting, stock–flow relations,
budget constraints). It is not an empirical claim about the world, costs nothing to
impose, and holds under every school of thought. A *behavioral* rule is an empirical
claim about how agents act. Only behavioral rules involve a genuine tradeoff between
"what theory/evidence supports" and "what we simplify for tractability." Identities we
assert as hard invariants; behavior we choose, justify, and remain ready to revise.

**(ii) Micro rules are axioms; macro regularities are the test set.**
Agent-level rules are our *model*. Aggregate regularities — Okun's law, the Phillips
relation, business-cycle comovement, fat-tailed growth, Zipf-distributed firm size — are
our *held-out validation targets* (§4). We must **never** encode a macro regularity as an
axiom. Doing so is training on the test set: the model would reproduce the fact by
construction, telling us nothing. A good model reproduces facts it was never told.

**(iii) No auctioneer.**
There is no Walrasian auctioneer and no market-clearing assumption anywhere. Trade
happens in *disequilibrium*, through decentralized bilateral matching, at posted prices,
with rationing. Unemployment, inventory cycles, and credit booms are expected to arise
*from* the permanent failure of markets to clear, not in spite of it. This is elevated to
a structural axiom in §3.

**(iv) Parsimony — the governing objective.**
The project's goal is to reproduce **as many** macro laws and empirical regularities (§4)
as possible from **as few** axioms as possible. Axiom count and free-parameter count are
costs; reproduced facts are the payoff; we maximize facts-explained per axiom. In an
ML idiom this is a minimum-description-length / compression stance: the axiom set is the
program, the reproduced stylized facts are what it explains, and a shorter program that
explains more is strictly better. This principle has teeth and outranks convenience:

- Adding an axiom or a free parameter must **pay its way** — it should unlock a regularity
  we could not otherwise get, not merely improve a fit. A parameter tuned to match a target
  is suspect; one *forced* by an identity or a robust micro fact is not.
- When two formulations reproduce the same facts, the one with fewer primitives wins.
- Optional knobs (e.g. $\alpha_{\text{info}}$ in M3) stay **out** of the model until a
  specific question demands them.
- This is why §0-ii matters doubly: encoding a macro fact directly is not just circular,
  it is also *expensive* — it spends description length to buy nothing.

Parsimony is the tie-breaker and the discipline behind every "should we add this?" decision.

### Status tags used below

- 🔒 **locked** — foundational; we do not expect to revise this.
- 🟡 **tentative** — adopted for a round, but a live candidate for revision.
- ⚪ **open** — flagged decision, not yet made (see §5).

---

## Notation

| Symbol | Meaning |
|---|---|
| $t \in \{0,1,2,\dots\}$ | discrete time (one *period* / *tick*) |
| $\mathcal{A}$ | set of all agents; partitioned into households $\mathcal{H}$, firms $\mathcal{F}$, banks $\mathcal{B}$, government $g$, central bank $cb$ (added as institutions are introduced) |
| $\mathcal{F}_C,\ \mathcal{F}_K$ | (v2) consumption-goods firms; capital-goods firms. $\mathcal{F}=\mathcal{F}_C\cup\mathcal{F}_K$ |
| $\mathcal{K}$ | set of financial instrument types (deposits, loans, cash, bonds, equity, …) |
| $h_{i,k,t}$ | holdings of instrument $k$ by agent $i$ at end of $t$, signed: **asset $> 0$, liability $< 0$** |
| $\mathcal{K}_{\text{in}}$ | *inside* instruments — financial claims that are one agent's asset and another's liability |
| $\mathcal{K}_{\text{out}}$ | *outside* items — real assets, commodities, capital, with no offsetting liability |
| $NW_{i,t}$ | net worth of agent $i$ |
| $Y^{d}_{i,t}$ | disposable income |
| $C_{i,t}$ | nominal consumption expenditure |
| $V_{i,t}$ | net (financial) wealth, $V_{i,t}=\sum_{k\in\mathcal K_{\text{in}}} h_{i,k,t}$ |
| $p_{i,t}$ | price posted by seller $i$ |
| $w_{i,t}$ | nominal wage |
| $\mathbb{E}_{i,t}[\cdot]$ | agent $i$'s subjective expectation formed at $t$ |
| $K_{f,t}$ | (v2) physical capital stock of firm $f$ (a real / outside asset) |
| $I_{f,t}$ | (v2) real investment (capital goods acquired) by firm $f$ in $t$ |
| $\delta_K$ | (v2) capital depreciation rate — *distinct from* B4's wage-flexibility $\delta$ |
| $v$ | (v2) desired capital–output ratio (accelerator target) |
| $\lambda_I$ | (v2) investment adjustment speed (partial-adjustment damping) |
| $\alpha$ | (v2) capital share in the Cobb–Douglas consumption technology |
| $A$ | (v2) total factor productivity, consumption sector |
| $a_K$ | (v2) labor productivity, capital sector ($y_K=a_K N_K$) |
| $D_i,\ L_i$ | (v3) deposits held / loan debt owed by agent $i$ (both $\ge 0$) |
| $R_i$ | (v3) base money (bank reserves) held by $i$ — the *outside* instrument carrying the conserved $M$; $\sum_i R_i = M$ |
| $\kappa$ | (v3) maximum leverage multiple (bank credit cap $L^{\max}=\kappa\,NW$) |
| $r$ | (v3) loan interest rate (exogenous in v3) |

Sign convention: for any agent, assets are positive and liabilities negative, so
$NW_{i,t} = \sum_{k} h_{i,k,t}$ summed over both financial and real holdings.

---

## 1. Layer I — Accounting axioms (identities) 🔒

These are the physics of the world. They are non-negotiable, hold every period for every
agent, and should be implemented as **runtime assertions** that halt the simulation on
violation. They are the only invariants we can fully trust while debugging.

### A1 — Double-entry / stock–flow consistency 🔒

**Natural language.** Every unit of financial value has a source and a destination.
Nothing appears or disappears. One agent's financial asset is exactly another agent's
liability, so across all agents the net holding of every inside instrument is zero.

**Formal.** For every inside instrument and every period,
$$\sum_{i \in \mathcal{A}} h_{i,k,t} = 0 \qquad \forall\, k \in \mathcal{K}_{\text{in}},\ \forall t.$$

Equivalently, in Godley–Lavoie *transactions-flow matrix* form: let $T_{r,i,t}$ be the
signed flow of transaction type $r$ for agent $i$ (sources $+$, uses $-$). Then

$$\underbrace{\sum_{i} T_{r,i,t} = 0 \ \ \forall r}_{\text{every flow has a counterparty (row sums)}}
\qquad\text{and}\qquad
\underbrace{\sum_{r} T_{r,i,t} = 0 \ \ \forall i}_{\text{each agent's budget balances (column sums)}}.$$

The column-sum condition is A3 (budget constraint); the row-sum condition is the "quadruple
entry" property — every transaction touches (at least) two agents and two accounts, and
the whole matrix nets to zero.

**Why.** This is definitional, school-agnostic, and free. It gives us a hard conserved
quantity to test against every tick.

> **Real vs. financial (matters from v2 on).** A1 conserves *financial* claims. A *real*
> outside asset — a produced good, or a unit of capital — is **not** a claim on anyone and
> has no offsetting liability, so it is **not** part of any conserved sum. Producing a good
> or a machine creates real value out of labor; it does not create or destroy money.
> Buying a machine is a *deposit transfer* (conserved); the machine itself is a real stock
> that simply accumulates. See §10's implementer warning — do not put capital into the
> money-conservation assertion.

### A2 — Stock–flow dynamics 🔒

**Natural language.** Stocks are the running accumulation of flows. A balance can only
change by a flow into or out of it.

**Formal.**
$$h_{i,k,t} = h_{i,k,t-1} + f_{i,k,t},$$
where $f_{i,k,t}$ is the net flow of instrument $k$ into agent $i$ during period $t$.
Stocks are the discrete integral of flows; no stock changes without a corresponding flow.
(The capital law of motion $K_{f,t}=(1-\delta_K)K_{f,t-1}+I_{f,t}$ in §10 is A2 applied to
the real capital stock.)

### A3 — Budget / balance-sheet constraint 🔒

**Natural language.** For each agent, over each period, sources of funds equal uses of
funds. Spending plus net accumulation of assets equals income plus net new borrowing. The
change in net worth equals saving plus revaluation.

**Formal (funds).**
$$\underbrace{\text{spending}_{i,t} + \Delta(\text{financial assets})_{i,t}}_{\text{uses}}
= \underbrace{\text{income}_{i,t} + \Delta(\text{liabilities})_{i,t}}_{\text{sources}}.$$

**Formal (net worth).**
$$\Delta NW_{i,t} = \underbrace{\big(Y^{d}_{i,t} - C_{i,t}\big)}_{\text{saving}} + \underbrace{\kappa_{i,t}}_{\text{capital gains/revaluation}}.$$

For a bare household holding only deposits $D$, A3 collapses to the intuitive
$C_{i,t} + \Delta D_{i,t} = Y^{d}_{i,t}$.

### A4 — Feasibility & non-negativity 🔒

**Natural language.** You cannot hold, consume, or produce a negative quantity of a real
good. And no agent can spend resources it does not have and cannot borrow — a would-be
buyer with no money simply fails to transact. This last clause is where disequilibrium
*enters*: demand can go unsatisfied.

**Formal.**
$$x_{i,k,t} \ge 0 \quad \forall k \in \mathcal{K}_{\text{out}} \text{ (real goods)},$$
$$\text{spending}_{i,t} \ \le\ \underbrace{L_{i,t}}_{\text{liquid resources}} + \underbrace{B_{i,t}}_{\text{credit available}}.$$

The gap between *notional* demand (what the agent wanted) and *effective* demand (what the
budget permits) is a first-class object, not an error. It is a primary channel through
which recessions propagate. (In v2 this applies to *investment* demand too: a firm's
capital-goods order is capped by its cash, and by what the capital sector can supply.)

### A5 — Net financial worth conservation (the full form of conservation under credit) 🔒

*(The operative anchor from v3 on; supersedes M0 once banks exist.)*

**Natural language.** Once a bank can lend, "total money is constant" (M0) **no longer holds**
— a loan creates a deposit, so broad money (the sum of deposits) expands and contracts. But
conservation is not lost; it **generalizes**. Every newly created unit of money is matched by
an equal new debt, so while *money* is not conserved, *net financial worth* is: broad money
minus outstanding credit equals the base money, and that is constant. M0 is merely the
no-credit special case of this deeper law.

**Formal.** With deposits $D_i\ge 0$ held and loan debt $L_i\ge 0$ owed by agent $i$,
$$\sum_i D_i - \sum_i L_i = M \qquad \forall t,$$
where $M$ is the base money fixed at genesis. With no credit ($\sum_i L_i=0$) this reduces to
$\sum_i D_i = M$ — exactly M0. With outstanding credit $\Lambda$, broad money is
$\sum_i D_i = M+\Lambda$ and total debt $\sum_i L_i=\Lambda$, whose difference is invariant.
Equivalently, summing over every financial instrument (deposits and loans net to zero by A1;
base money carries the residual), $\sum_i\sum_{k} h_{i,k,t} = M$.

**Where the $M$ lives — base money.** The conserved $M$ does not vanish when deposits become
inside money; it **migrates** to a new *outside* instrument, **base money (bank reserves) $R$**,
with $\sum_i R_i = M$. In v1/v2 the deposits themselves were the outside money carrying $M$
(hence $\sum D=M$); once a bank issues deposits as *its liabilities*, those deposits become
inside money (net zero across holders and the bank), and the bank holds $M$ in reserves so its
balance sheet is consistent and the system's net worth still equals $M$. This is **not** a
money multiplier (M2 rejects that): reserves do not *limit* lending, they merely *carry* the
conserved base money. It also corrects a natural slip — net worth is $M$, **not** zero; the
$=0$ "pure inside money" world would require the public to be born in debt, contradicting the
locked "money from genesis" endowment (§5).

**Why the anchor.** v1/v2 were debugged against $\sum D=M$ to ~1e-9. v3 keeps an equally hard,
equally machine-checkable gate — **assert $\sum_i D_i-\sum_i L_i=M$ every tick, halt on drift**
(and $\sum_i R_i=M$). The M2 four-entry loan keeps the difference invariant *by construction*,
exactly as `transfer` kept $\sum D$ invariant: route principal creation/repayment through a
`create_loan`/`repay` primitive (four atomic entries) so A5 cannot be violated by construction,
and treat interest as an ordinary `transfer` (it redistributes deposits, changing no aggregate
net worth and leaving $\sum D-\sum L$ untouched). Broad money $\sum_i D_i$ is now a **recorded,
endogenous series** — the signature of a credit economy — not an asserted invariant. That
series going from a flat line to a live one *is* the mark of entering a credit economy.

---

## 2. Layer II — Behavioral axioms (decision rules)

These are empirical claims about agent behavior. Design principle: **start insultingly
simple.** The simpler the rule, the cleaner and more interpretable the emergence, and the
less we risk mistaking hand-coded structure for genuine emergence. Fortunately, for this
layer the simplifications we *want* mostly coincide with what post-2008 empirical
macro *supports* — the elegant DSGE assumptions (rational expectations, market clearing,
representative agent) are both the hardest to implement in an ABM and the weakest
empirically, so we lose little by dropping them.

### B1 — Consumption out of income and wealth 🟡

**Natural language.** Households consume an increasing fraction of income; the marginal
propensity to consume (MPC) lies strictly between 0 and 1 and **declines with wealth**.
Poor, liquidity-constrained households spend nearly all marginal income; wealthy
households spend little of it.

**Formal (Godley–Lavoie linear form).**
$$C_{i,t} = \alpha_1^{i}\, Y^{d}_{i,t} + \alpha_2^{i}\, V_{i,t-1},
\qquad 0 < \alpha_2^{i} < \alpha_1^{i} < 1.$$

This two-term structure already delivers a *declining average propensity in wealth*: a
household with little wealth consumes at a rate near $\alpha_1$ (high), one with large $V$
proportionally less. Cross-household heterogeneity in $\alpha_1^{i}$ (equivalently, an
MPC that is a decreasing function of liquid wealth, $\text{MPC}_i = \alpha_1(V_i)$ with
$\alpha_1' < 0$) reproduces the empirically central *MPC heterogeneity*.

**Evidence.** One of the most robust facts in macro: high MPC among constrained /
low-liquid-wealth households (tax-rebate experiments, e.g. Johnson–Parker–Souleles;
the HANK literature, Kaplan–Moll–Violante). It is why the *distribution* of wealth
matters for aggregate dynamics — not a detail we can average away.

**Open (⚪, see §5).** Whether MPC heterogeneity enters in round 1 or a later round.

### B2 — Adaptive / extrapolative expectations 🔒

**Natural language.** Agents forecast the future by extrapolating the recent past and
correcting past errors. They are *not* rational-expectations forecasters with model-
consistent beliefs.

**Formal (error-correction / exponential smoothing).**
$$\mathbb{E}_{i,t}[z_{t+1}] = \mathbb{E}_{i,t-1}[z_{t}] + \lambda\big(z_{t} - \mathbb{E}_{i,t-1}[z_{t}]\big), \qquad \lambda \in (0,1].$$

**Formal (extrapolative alternative).**
$$\mathbb{E}_{i,t}[z_{t+1}] = z_{t} + \gamma\,(z_{t} - z_{t-1}), \qquad \gamma \ge 0.$$

**Why.** Here the simplification and the evidence point the *same* way: survey data
reject full-information rational expectations and show systematic, predictable forecast
errors (information rigidity; Coibion–Gorodnichenko). We adopt the simpler rule with a
clear conscience. Locked because rational expectations is not on the table for an ABM.

### B3 — Cost-plus pricing with stickiness 🟡

**Natural language.** Firms set prices as a markup over unit cost, not by equating
marginal cost and marginal revenue. They change prices infrequently, adjusting the markup
in response to local signals (inventory, unfilled demand) rather than to any global
market price.

**Formal (target price).**
$$p^{*}_{i,t} = (1 + \mu_{i,t})\, uc_{i,t},$$
with unit cost $uc_{i,t}$ and markup $\mu_{i,t}$ updated adaptively from a local signal
$s_{i,t}$ (e.g. inventory relative to target, or the sign of unfilled demand):
$$\mu_{i,t} = \mu_{i,t-1} + \eta \cdot s_{i,t}.$$

**Formal (stickiness, $Ss$/menu-cost form).** The posted price updates only when the
target has drifted beyond a band:
$$p_{i,t} =
\begin{cases}
p^{*}_{i,t}, & \text{if } \left|\dfrac{p^{*}_{i,t} - p_{i,t-1}}{p_{i,t-1}}\right| > \bar{s},\\[1.2ex]
p_{i,t-1}, & \text{otherwise.}
\end{cases}$$
(A Calvo-style alternative — update with probability $\theta$ each period — is an
acceptable substitute; the $Ss$ form is more ABM-native.)

**Evidence.** Micro price data show infrequent adjustment (Nakamura–Steinsson;
Bils–Klenow). Direct surveys of firms find cost-plus is the dominant self-reported
pricing rule (Blinder, *Asking About Prices*). Again simplicity and evidence coincide,
and with no auctioneer a local pricing rule is anyway the only option.

**v2 note.** Both firm sectors use *this same rule*, with the markup taken over **unit
labor cost** (capital is a predetermined, already-paid sunk stock, so marginal cost is
labor). See §10.4 for the sector-specific unit-cost expressions.

### B4 — Wage stickiness and downward nominal rigidity 🔒

**Natural language.** Nominal wages adjust sluggishly and are especially resistant to
*cuts*: firms lay workers off rather than reduce nominal wages.

**Formal (downward floor).**
$$w_{i,t} \ge (1-\delta)\, w_{i,t-1}, \qquad \delta \ \text{small (often } \delta = 0,\ \text{a strict floor).}$$
Upward moves follow a separate rule responding to labor-market tightness and/or expected
inflation. *(This $\delta$ is wage-flexibility; capital depreciation in v2 is the distinct
symbol $\delta_K$.)*

**Why locked.** DNWR is a very robust fact (a spike at zero in the distribution of
nominal wage changes) and is close to a *necessary condition* for unemployment to emerge
endogenously: without it, wages would fall until labor cleared and involuntary
unemployment could not persist. Since endogenous unemployment is a core target (§4), the
mechanism that permits it is foundational.

### B5 — Investment via the accelerator 🟡

*(Active from v2, when the capital-goods sector exists.)*

**Natural language.** Firms invest to keep their capital stock in proportion to the output
they expect to produce. When expected demand rises, desired capital rises with it, so
investment is driven by the *change* in demand, not its level — the accelerator. Firms
close the gap to desired capital only partially each period (adjustment is cautious and
costly) and also invest to replace worn-out capital.

**Formal.** Desired capital tracks expected output through a capital–output ratio $v$:
$$K^{*}_{f,t} = v\, y^{e}_{f,t}.$$
Desired investment closes a fraction $\lambda_I$ of the gap and covers depreciation:
$$I^{*}_{f,t} = \max\!\Big(0,\ \lambda_I\big(K^{*}_{f,t}-K_{f,t-1}\big) + \delta_K K_{f,t-1}\Big),
\qquad \lambda_I\in(0,1].$$
Investment is a *notional demand for capital goods*; it is then capped by cash (A4) and by
what the capital sector can supply (M1 rationing). See §10.4.

**Evidence.** The accelerator is among the oldest and most robust regularities of
investment (Clark, 1917; the flexible-accelerator tradition): at business-cycle frequency
investment tracks the change in output/sales far more than it tracks interest rates or
current profits. It is also, by design, the mechanism most likely to *generate* endogenous
cycles — coupled with the consumption multiplier (B1) it is the Samuelson
multiplier–accelerator, which produces self-sustaining fluctuations from very simple parts.

**Status 🟡, and an honest warning.** The accelerator is the chosen v2 investment rule. A
profit-rate / return-driven rule, and (much later, once a capital market *and* an interest
rate exist) a true Tobin's $q$, are alternatives deferred to their proper layers — see §5.
$\lambda_I$ is deliberately a **damping knob**: the pure accelerator is famously prone to
overshoot and divergence, so partial adjustment is expected to be *necessary* to land in a
"fluctuating but bounded" regime. Just as the kernel's first run was expected to flatline,
v2's first run may **oscillate or even diverge** — that is calibration of $(v,\lambda_I,
\delta_K)$, not a bug (§7.5 discipline).

### B6 — Credit demand: firms borrow to cover a cash shortfall 🟡

*(Active from v3, when banks exist.)*

**Natural language.** A4 always permitted spending up to *liquid resources + credit available*;
the kernel and v2 simply pinned credit to zero. v3 **opens that credit term.** A firm that plans
to spend more than its cash — on its wage bill, its investment, or both — asks the bank to fund
the gap. Firms are passive credit *demanders*: they first plan (wages, and investment via B5),
then borrow only the shortfall, capped by the bank (B7). Opening the credit term is a *single*
mechanism, not two — it applies to any cash-constrained spending, so restricting it to
investment-only would be an added special case (longer description; §0-iv), not a simpler model.

**Formal.** Firm $f$'s planned cash use is its target wage bill plus desired investment outlay;
its shortfall is
$$\text{gap}_{f,t} = \max\!\big(0,\ \underbrace{w_{f,t}N^{d}_{f,t} + p^{K}I^{*}_{f,t}}_{\text{planned spending}} - D_{f,t}\big).$$
The firm requests a loan of $\text{gap}_{f,t}$, granted up to the B7 cap. Borrowed funds are new
deposits (M2), available immediately for this tick's wages and investment.

**Attribution — a monitored quantity.** Opening *wage* credit **relaxes the v1/v2 cash-capped
hiring**, a constraint central to how unemployment emerged. This is a real change to a core
mechanism, not a free feature. So credit is **logged by purpose** (investment vs wage): even as
the mechanism changes, we can read off at the observation layer how much of any output/employment
gain is *credit-financed* versus demand-driven. This split is a first-class v3 diagnostic (§12).

**Why 🟡.** Borrow-to-cover-any-gap is the minimal faithful form of "open A4's credit term."
Household consumer credit and richer firm liability management are later increments.

### B7 — Credit supply: a net-worth leverage limit 🟡

*(Active from v3.)*

**Natural language.** The bank decides how much to lend by one rule: a borrower may owe at most
a fixed multiple of its net worth. This leverage constraint is deliberately the *only* thing the
bank computes — no default-probability model, no risk pricing. The point is what it makes
**emerge**: in a downturn a firm's net worth shrinks, so its borrowing capacity automatically
tightens — **credit is procyclical.** Booms lift net worth → more credit → more boom; busts cut
net worth → credit withdrawn → deeper bust. The Minsky leverage cycle falls out of this one line,
with no complex bank behavior.

**Formal.** Firm $f$'s (financial) net worth is $NW_{f,t}=D_{f,t}-L_{f,t}$ — deposits minus debt.
The bank caps total debt at
$$L^{\max}_{f,t} = \kappa\, NW_{f,t}, \qquad \kappa>1,$$
so new credit this tick is $\le \max(0,\ L^{\max}_{f,t}-L_{f,t})$. If $NW_{f,t}\le 0$ (insolvent),
no new credit.

**Why *financial* net worth (not incl. capital), 🟡.** Deposits already move procyclically (firms
are cash-rich in booms), so $D-L$ alone delivers procyclical leverage — enough to test the credit
cycle at its simplest. Counting the real capital stock as collateral (valuing $K$ at $p^K$) would
*amplify* procyclicality (a stronger Minsky channel) but adds capital valuation and its own
procyclicality; deferred to **v3.1**. Multiple competing banks, risk-priced rates, and a
bank-capital constraint are later. The bank does **not** estimate default (v3 has none).

---

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

## 21. v8 — Household margin credit: borrowing that finally brings an asset

§20 showed household *consumption* credit brings only debt (you consume the asset; it drains to
firms). The fix (from the double-entry logic): households must borrow to buy **assets they retain**.
v8 adds **margin credit** — households borrow *against their equity* (an LTV limit) to lever into
stocks, on the full v7/v6.2 stack (cumulative; `margin_credit`, off ⇒ v7 bit-identical).

### 21.1 Mechanism
- **Levered demand.** When `margin_credit`, a household's target equity share of NET WORTH rises
  with bullishness (mean demand pressure) up to `margin_max`; buys beyond cash are funded by a
  **margin loan** capped by `margin_ltv · equity_value`. So the borrowed money buys an asset — debt
  and equity both go up, net worth is (initially) unchanged, but the position is *leveraged*.
- **Margin calls.** After repricing, a household whose margin debt exceeds the LTV on its (fallen)
  equity **delevers** — repays from cash raised by the forced sells its dropped levered target
  triggered. Fire sales feed next tick's prices (the crisis channel).
- Margin debt is **interest-only** (the consumption-debt amortisation doesn't touch it); repaid by
  sales/calls. Both conservations exact (A5 ~1e-8, per-firm float ~1e-12).

### 21.2 Finding (round 7): the first mechanism to concentrate wealth WITHOUT crushing everyone
1. **Borrowing brings an asset.** Unlike v7 (consumption debt → net-debtors underwater), margin debt
   is equity-collateralised: borrowers hold the asset against it and **stay solvent** on full net
   worth (cash + equity − debt). The original problem is solved.
2. **Leverage concentrates wealth in a bubble.** At the default appetite (`theta_equity=0.3`), a
   leveraged bubble raises the top-decile share of full net worth and the net-worth Gini (to ~0.32
   at 120 firms) versus a near-flat calm baseline — capital gains, amplified by leverage, accrue to
   whoever levered into the winners. This is the **first** layer to produce real wealth
   concentration *without* the demand collapse (v7 thrift/debt trap) or the mirror-only inertia (v6
   equity). Magnitude is scale-sensitive (clearer at moderate N).
3. **Leverage has an endogenous stability ceiling.** Push the equity appetite higher
   (`theta_equity≥0.7`) and leverage **runs away** — equity ≈ margin debt, net worth collapses to
   ~0, the economy freezes. Too much margin is self-destructive: the credit-collateral fragility,
   emergent. So the concentration lives in a bounded window between "no leverage" and "leverage
   blow-up".
4. **Margin amplifies volatility** (output CV ~0.05 → ~0.09) — the leverage/margin-call feedback is
   destabilising, the seed of the credit-collateral crisis (a full boom-bust-cascade needs multi-
   bank contagion, still out).

### 21.3 Parameter budget & acceptance
New: `margin_credit`, `margin_ltv`, `margin_max`. `Config.v8()` = v7 + margin on. **Acceptance met**
(`test_v8_margin_credit`, 5/5): v7 bit-identical off; money + per-firm-float conservation through
margin borrowing and calls; borrowing brings assets (borrowers not underwater); leverage
concentrates in a bubble; margin calls deleverage. The §21.2 findings — concentration without
collapse, and the leverage ceiling — are the substantive result: **v8 is the first layer to make
"a few get rich" happen through a realistic, conserving mechanism.**

---

## 22. §4 re-validation on the full v8 stack — 7/8, and the wealth tail finally right-shaped

Re-ran the §4 held-out validation (`validate_v8.py`) on `Config.v8()` (everything on: banks, credit,
capital, firm demographics, per-firm equity + q-investment + equity finance, household consumption
credit, **household margin credit**), 200C/100K/2000H, 4000 ticks, 3 seeds, T8 measured on **full net
worth** (cash + equity − debt). **Score 7/8** — up from v4's 6/8, and, crucially, *not bought by
breaking the others*.

| target | verdict | v8 | vs v4 baseline |
|---|---|---|---|
| T1 Phillips | ✅ | slope −0.02, corr −0.12 | weaker, still negative |
| T2 Okun | ✅ | **−0.87** | robust |
| T3 BC comovement | ✅ | I +0.75, N +0.97, **credit +0.52**, C +0.88 | credit comovement **stronger** (was +0.23) |
| T4 endogenous unemployment | ✅ | mean 0.19, range 0–**0.73** | higher & more volatile (margin) |
| T5 fat-tailed growth | ✅ | excess kurt +0.83 | ~unchanged |
| T6 Zipf firm size | ✅* | output slope −0.86 (this run); **−0.75±0.26** over 5 seeds | steepened from −0.38, but noisy + flat tail |
| T7 credit boom-bust | ✅ | lev CV 0.19, **corr +0.56** | comovement **stronger** (was +0.23) |
| T8 wealth tail | ❌* | skew +0.23, **kurt +15.3**, top-10% **0.45**, upper-tail slope −0.33 | flipped shape, but outlier-driven |

### 22.1 Margin credit did not damage the cycle regularities — it strengthened some
The risk was that leverage/margin-call volatility would wreck the business-cycle facts. It did the
opposite: **T3 (credit comovement +0.23→+0.52) and T7 (credit–output +0.23→+0.56) both strengthened**
— credit and the real cycle are now more tightly coupled, as one expects once households as well as
firms borrow procyclically. The cost is more volatile unemployment (T4 range to 0.73) — the intended
crisis seed, not a bug.

### 22.2 T6 and T8: both concentrated harder, but both have the SAME flat tail
v8 pushed both distributions toward concentration — but neither has a clean power-law *tail*, and the
diagnosis is identical for both.
- **T8 (wealth).** v4 baseline was left-skewed and thin (skew −0.53, excess kurt −0.32, top-10% 0.12
  — "everyone equal"). v8 flips it: **right-skewed (+0.23), heavy-tailed (kurt +15.3), concentrated
  (top-10% 0.45)** — leveraged capital gains build a real elite, the first realistic conserving
  mechanism to get the *right qualitative shape*. But the upper-tail rank-size slope is **−0.33**
  (flat, far from Pareto −1) and the +15 kurtosis is a **few leverage outliers**, not a smooth power
  law. So the strict criterion (skew>0.5 + clean tail) marks it FAIL.
- **T6 (firm size).** The full-distribution slope steepened from −0.38 (v4) to **−0.75±0.26** over 5
  seeds (this validation's −0.86 was a lucky draw in that noisy range) — a real concentration gain,
  but *noisy* (per-seed −0.41 to −1.19) and, again, the **upper-tail is flat (−0.32)**.

**The unification.** Both upper tails sit at ≈ −0.33 — neither firm size nor wealth is a smooth
power law; both are "concentrated body, flat/outlier tail." The single missing ingredient is the
same: **multiplicative (Gibrat) growth** — persistent proportional random growth that spreads the
top continuously into a Pareto tail instead of piling it on a few outliers. Add that one mechanism
and both T6 and T8 should convert from "shape roughly right" to "clean power-law tail" together.
T6's "✅" here is therefore best read as **borderline/noisy**, not a robust pass.

---

## 23. v8.1 — Gibrat growth closes the last gap: 8/8 held-out regularities

§22 pinned the one missing ingredient for T6 (firm-size Zipf) AND T8 (wealth tail): **multiplicative
(Gibrat) growth**, absent because firm size mean-reverts to a common accelerator target. v8.1 supplies
it, on the full v8 stack (cumulative; `gibrat_growth`, off ⇒ v8 bit-identical).

### 23.1 Mechanism (Simon/Gabaix, as a demand-allocation change only)
- **Market share as a geometric random walk.** Each C-firm carries an attractiveness `a_f`;
  each tick `a_f *= exp(σ_g·z − σ_g²/2)` (mean-preserving lognormal — a Gibrat shock, no aggregate
  drift).
- **Size-biased demand.** The goods market allocates demand ∝ `a_f^β` (`PreferentialMatch`), so a
  bigger customer base sells more → grows more, *proportionally* (β≈1 = linear preferential
  attachment). Entrants start small (`a0` = the reflecting barrier), failures exit (v4). Barrier +
  multiplicative growth ⇒ **Pareto**. It touches only *which* seller a buyer picks — money and shares
  conservation are untouched (no new invariant).

### 23.2 Finding (round 8): 8/8 — every held-out §4 regularity, for the first time
Re-validation (`validate_v81.py`, `Config.v81`, 200C/2000H, 4000 ticks, 3 seeds): **8/8**.
- **T6 much improved, near Zipf but still noisy.** Firm-size output rank-size slope **−1.25** in the
  validation (from v8's flat −0.75±0.26 and v4's −0.38). But a 3-seed σ-sweep (150C, upper tail) is
  *noisy and non-monotonic* — σ=0.02→−1.23±0.46, 0.03→−1.76, 0.05→−0.80±0.05, 0.08→−1.06 — so the
  slope lands **around** Zipf across σ rather than the σ knob setting it precisely, and it is
  measure/scale-sensitive (upper-tail −0.80 vs full −1.25 at σ=0.05). So: dramatically steeper than
  the old flat tail and genuinely in the Pareto range, **but not a clean, stable −1**.
- **T8 flips to PASS.** Full-net-worth skew **+2.11** (was +0.23 under v8), excess kurt +36 — the Zipf
  firm tail propagates to wealth through the v8 equity/margin chain, clearing the skew criterion.
- The other six hold; T5 growth is now *very* fat (excess kurt +52) and cycles/comovement survive.

### 23.3 Two honest caveats — 8/8 is not "solved"
1. **T8's tail is still not a clean Pareto.** It passes on skew+kurtosis (right-skewed, heavy), but the
   wealth *upper-tail* slope is −0.42 (vs firm size's −1.25) — the +36 kurtosis is outlier-driven. The
   throttle is §18's **ownership diversification**: the Zipf firms are broadly held (genesis split +
   portfolio rebalancing), so wealth inherits only *part* of the firm tail. A clean wealth Pareto would
   need concentrated, persistent ownership of the winners (a v8.2 hook: founders/levered buyers holding
   the Gibrat winners without diversifying).
2. **Concentration is not free.** At the default σ, unemployment rises to ~0.39 (from v8's 0.19): funnelling
   demand onto a Zipf-few firms strands labour at the losers. So 8/8 sits in a regime that is *more
   concentrated and more depressed* — the same concentration↔employment tension seen throughout, now on
   the demand side. The interesting frontier is the σ that buys a clean tail at the least employment cost.

### 23.4 Parameter budget & acceptance
New: `gibrat_growth`, `gibrat_sigma`, `pref_attach_beta`, `gibrat_entry_a0`. `Config.v81()` = v8 + Gibrat.
**Acceptance met** (`test_v81_gibrat`, 5/5): v8 bit-identical off; A5 + share conservation (demand-
allocation change only); market share disperses (Gibrat); firm-size upper tail is a steep power law
(not the flat −0.33); wealth tail steepens (modestly). And the headline: the §4 re-validation reads
**8/8** — the model now reproduces every held-out macro regularity from the micro axioms alone, though
T8's tail is outlier-driven not yet a clean Pareto, and at an employment cost.

---

## 24. v8.2 — Adaptive portfolio rebalancing: a pre-registered experiment that was falsified

§23 left T8's wealth *tail* outlier-driven (upper-tail −0.42), diagnosed (§18) as **ownership
diversification**: the Zipf firms are broadly held, so wealth doesn't inherit the firm tail. The
proposed fix — *without* imposing concentration (which would violate §0-ii) — was to apply the **B2
adaptive-expectation discipline to the one decision that lacked it: portfolio rebalancing.** Households
move only a fraction λ (`portfolio_adjust`) toward their ideal equity target each tick (partial
adjustment) instead of instant full rebalancing, so founders delever slowly and concentrated ownership
of Gibrat winners should *emerge*. λ was set to λ_I (0.25) **independently**, and the outcome
**pre-registered**: the tail should steepen to ~−0.6…−0.8, but *not* to a clean −1 (the genesis-broad-
ownership + churn ceiling).

### 24.1 Finding (round 9): the mechanism works, the effect does not survive scale — falsified
- **The mechanism is sound and §0-ii-clean.** `portfolio_adjust=1.0` ⇒ v8.1 bit-identical; λ<1
  genuinely slows rebalancing (turnover ~halves) and conserves. It fixes a real inconsistency (every
  other decision used adaptive expectations; portfolio was instant).
- **But the goal failed at scale.** At 120 firms the smoke looked promising (ownership Gini
  0.54→0.62, wealth upper tail −0.41→−0.57). **It did not replicate at the 200C/4000-tick validation
  scale: wealth upper tail −0.42→−0.40 — no steepening at all.** The 120C effect was a small-N
  artifact; the founder-concentration channel is too weak against **genesis firms being structurally
  broadly held** and **entrant churn wiping would-be-concentrated founders** before they compound.
- **And it has a real macro cost — bigger than the scorecard suggested.** A 3-seed side-by-side
  (150C, `investigate`) shows the *robust* changes are not the wealth tail (noisy) but: turnover −45%
  (the mechanism), **firms MORE concentrated** (firm-size slope −0.86→−1.40, Gini 0.85→0.92, robust),
  and — the headline — **the economy is markedly more depressed: unemployment 0.14→0.40 (+176%),
  output −28%, both robust.** (An earlier 120C smoke had u *falling* — that was a seed artifact; the
  robust sign is a large *rise*.) The scorecard slip (T3 +0.27→+0.11, T6 −1.46) is the noisy tip of
  this. So v8.2 does not *earn* the default — it depresses output for no robust distributional gain.
  The surprising channel (wealth effect is off, yet slow *equity* trading hits the *real* economy):
  it must run through the equity→investment links (q-driven investment §18 / equity finance §19) —
  slower trading reshapes the q distribution, concentrating investment onto fewer firms and stranding
  labour at the rest. That "trading speed → q → real concentration/employment" feedback is a genuine
  (unplanned) observation worth its own check.

### 24.2 What it teaches (the falsification is the value)
The pre-registration paid off: I predicted "improves but not clean," chose λ on independent grounds,
did not tune to −1, and the model **honestly said no** — even more negatively than predicted (no
robust improvement at scale). The clean lesson: **a clean wealth Pareto tail is not reachable by
making rebalancing sticky.** It requires attacking the two structural ceilings directly — **genesis
firms owned by few founders (not split among watchers)** and **lower churn / more persistent winners**
— so that the Gibrat firm tail (which v8.1 *does* produce) can actually flow to concentrated holders.
That is the real v8.3/v9 target; v8.2 rules out the cheaper route.

### 24.3 Status
`portfolio_adjust` is kept as a legitimate, more-realistic dial (`Config.v82()`), but **the canonical
frontier stays v8.1 (8/8)** — v8.2 is off by default (`portfolio_adjust=1.0`). Acceptance
(`test_v82_portfolio`, 4/4): regression bit-identical at λ=1; conservation; partial adjustment slows
rebalancing. The downstream tail effect is a §24 finding (weak, scale-fragile, falsified at scale),
deliberately not a unit threshold.

---

## 25. v8.3 — Weakening the Tobin's-q → investment channel (realism + stability), and v8.2 ruled out

The v8.2 investigation (§24) was muddied by a **spurious macro volatility**: the same config gave
u=0.14 with one seed subset and 0.40 with another. The culprit: our **Tobin's-q → investment**
channel was **over-strong and too fast** — `lambda_q=0.3` applied to the *instant, bubble-laden*
market q every tick, whereas empirically q has a **weak, sluggish** effect on investment (accelerator
+ cash flow dominate; firms ignore transient mispricing). So stock-market noise was being pumped
straight into real investment. v8.3 fixes this in two disciplined steps.

### 25.1 Step 1 — weaken + smooth q→investment (realism-justified, pre-registered)
Lower `lambda_q` (0.3→0.1) and drive investment off a **smoothed** q (`q_invest_smooth`; investment
follows `tobin_q_ema`, not the instant price). Calibrated on the empirical low q-elasticity, **not**
tuned to any target (§0-ii); `q_invest_smooth=1` ⇒ v8.1 bit-identical. **Pre-registered:** the economy
should get calmer with no regularity broken. **Confirmed (5 seeds, 150C):** seed spread of unemployment
fell **0.138→0.093 (−33%)** and of output **216→157 (−27%)**; it even ran *healthier* (u 0.35→0.27,
output +14%); and the **§4 re-validation held 8/8** (T3 credit comovement recovered to +0.32, T8 skew
*strengthened* +2.11→+3.57). A clean **realism + stability** win at no cost — over-strong q-investment
was a genuine (unplanned) volatility bug, now fixed.

### 25.2 Step 2 — with the economy calm, re-test v8.2 (slow rebalancing): ruled out
The point of step 1 was to make v8.2's effect *measurable* (the shaky scale steadied). Re-tested in
the calm v8.3 economy (5 seeds, tight spreads): **v8.2 does nothing for the wealth tail** — upper-tail
slope −0.52→−0.51 (identical), and ownership concentration does **not** rise (0.653→0.644). The
earlier "v8.2 helped / hurt" signals were all q-driven volatility noise. **Verdict: slow rebalancing is
definitively ruled out as a wealth-tail fix; `portfolio_adjust` stays off by default.** (This also
retro-corrects §24: v8.2 does *not* robustly depress the economy — that was the same q-volatility
artifact.)

### 25.3 Where this leaves T8
The wealth tail is still ≈ −0.52 (heavy but not a clean Pareto −1). Two candidate fixes are now both
**ruled out** — Gibrat propagation (§23, gives the *body* not a clean tail) and sticky rebalancing
(§24/§25). The remaining lever is the **structural** one §24.2 named: **genesis firms owned by few
founders (not split among watchers) + lower churn**, so the Gibrat firm tail can flow to concentrated,
persistent holders. That is the real v8.4/v9 target.

### 25.4 Status & acceptance
`Config.v83()` = v8.1 + weakened/smoothed q — the **new recommended frontier** (more realistic, calmer,
8/8). Mechanism defaults unchanged (`lambda_q=0.3`, `q_invest_smooth=1.0`) so v8.1 and all prior layers
stay bit-identical baselines. `test_v83_q_channel` (regression + smoother-q + conservation). The
two-step design paid off: step 1 fixed a real bug and enabled clean measurement; step 2 then cleanly
falsified v8.2 — neither result was available while the economy was shaking.

---

## §26 v8.4 — dividends pro-rata to shareholders (a correctness fix that, alone, destabilizes)

**Config:** `pro_rata_dividends` (default False ⇒ bit-identical). `Config.v84()` = v8.3 + on. Needs `per_firm_equity`.

### 26.1 The inconsistency it fixes
Since v6.1 we track *who owns what* (`h.holdings[f.id]`), yet dividends were split EQUALLY per capita
([economy.py] Phase-4 (ii)) — a "choice 甲 homogeneity" leftover from the v6 aggregate-index era. So a
100%-owner and a zero-share household received identical dividend income. Pro-rata routes each firm's
payout to ITS holders in proportion to holdings; a non-owner earns zero dividend income. The K-sector
(un-equitized) dividends have no household holders, so they stay on the equal-split path as a residual
(the homogeneity fallback for unowned equity). Money (A5) and share floats still conserve exactly.

By Miller–Modigliani the capital-gains channel was *already* pro-rata (hold more → gain more on a price
rise); only the **dividend cash** channel was broken. So this is a consistency fix, pre-registered to
**barely move T8** while genesis ownership is still diffuse.

### 26.2 Finding — in ISOLATION it is a net macro negative
- Pre-registered mechanism **confirmed**: pro-rata raises cross-household **income Gini** (dividend income
  is now concentrated). `test_v84_dividends` asserts this.
- But §4 drops **8/8 → 7/8**: **T3 credit comovement** falls below the 0.2 bar. Same-seed 5-seed: credit
  comovement **+0.31 → +0.13**; 6-seed per-seed pass-rate 5/6 → 2/6 — a systematic DOWNWARD shift with
  *smaller* variance (0.15→0.07), i.e. a real effect, **not** T3's usual seed-noise.
- Macro levels (same seeds): mean **u 0.259 → 0.295**, seed spread **×3** (0.026→0.084), output cyclical
  CV 0.22→0.35. The whole economy got **more volatile**, not just T3.

### 26.3 Mechanism — equal-split dividends were an accidental automatic stabilizer
Profit (hence dividends) is procyclical. Equal-split spread that procyclical cash to *all* households —
a "follow-the-cycle universal dividend" that propped up demand and synchronized balance sheets. Pro-rata
sends it to a few low-MPC owners instead, removing the stabilizer. Credit-component decomposition: the
procyclicality of **every** credit type falls (firm +0.16→+0.10, household consumption +0.07→**0.00**,
margin +0.07→+0.02) — concentrated dividend income **desynchronizes household borrowing** from the cycle.

### 26.4 The insight (why this matters beyond T3)
Wealth concentration (T8) and macro stability (T3, u) **trade off in a model with no stabilizers**. Real
economies get both only via the machinery we lack: fiscal transfers, progressive tax, unemployment
insurance, a central bank. Our chronic high-u, the T3 break, and the hard-to-sharpen T8 tail may be
**three faces of one gap: no stabilizer.**

### 26.5 Status
Kept, off by default. We do **not** roll back a more-correct mechanism to protect a score (§0-ii). It is
step 1 of a structural change; §27 completes it. `test_v84_dividends` (3).

---

## §27 v8.5 — founder-owned genesis (the surprise: it FIXES stability, and the reason isn't concentration)

**Config:** `founder_owned_genesis` (default False ⇒ bit-identical) + `genesis_founder_pool=0.1`
(fraction of households that may found; anchored to the ~10% real business-ownership rate, NOT tuned).
`Config.v85()` = v8.4 + on. Needs `per_firm_equity`.

### 27.1 What changed
At t=0, v6.1 split each firm's float equally among its (many) watchers — diffuse ownership. v8.5 vests
the genesis float in a minority founder class (each firm 100% to one random founder), mirroring the
run-time "funder owns 100%" rule. Pre-registered **risk**: instant rebalancing (`portfolio_adjust=1`)
may dissolve the blocks — founders sell down toward their θ_equity target.

### 27.2 Result — §4 **8/8**, and it was the OPPOSITE of my prediction
Same 5 seeds, head-to-head: **v8.4 diffuse 7/8** (T3 credit +0.13, mean u 0.274, u-range 0–**1.00**) vs
**v8.5 founder 8/8** (T3 credit **+0.29**, mean u **0.175**, u-range 0–0.85, T8 tail slope −0.87). Founder
genesis **restored T3, cut unemployment 36%, removed the total-collapse (u=1) crises, kept the clean T8
tail.** My pre-registered worry (more concentration → less stable) is **falsified**. `test_v85_founder` (3).

### 27.3 Mechanism — three cheaper hypotheses refuted, one survives
The puzzle: founder concentration **erodes** (ownership Gini converges to v8.4's ~0.82 by mid-run), so the
benefit is *not* persistent concentration. Ruling out, with data:
1. **Concentration persists** — NO. Ownership Gini early 0.33→ mid 0.78 → late 0.81, same as diffuse.
2. **Lower aggregate leverage** — NO. Steady-state margin debt ~8500 and total credit ~9000 are identical.
3. **Fire-sale cascade drives the collapse** — NO. Fire-sale volume identical (~40 mean), and
   `corr(fire-saleₜ, uₜ₊₁) = −0.13` in **both** — fire sales slightly *precede lower* u; they are normal
   plumbing, not the trigger.

**Surviving mechanism — household insolvency → demand destruction (a self-reinforcing loop).** The one
hard discriminator is **wipeouts**: diffuse genesis ends with **173/2000 (8.7%) households insolvent**
(net worth ≤ 0) and max individual leverage **52×**; founder genesis **36 (1.8%)** and **14×**. Chain:
diffuse genesis makes every household a small, **homogeneous, levered** holder → a crash wipes out many at
once → wiped-out households are **demand-dead** (B1 wealth term ≤ 0) → aggregate demand collapses →
**deeper/longer recessions** (time with u>0.5: **21% vs 5%**; u>0.9: **2% vs 0%**) → prices crash more →
more wipeouts. Founder genesis endows equity in *unlevered* founders and leaves most households
equity-light, so far fewer are exposed enough to ignite the loop.

*Honest caveat:* the softest link is *why* diffuse over-levers — attributed to homogeneous synchronized
exposure; the OUTCOME (5× more wipeouts → demand destruction) is directly in the data, the ignition detail
is not fully isolated.

### 27.4 Status
`Config.v85()` = **new recommended frontier**: §4 **8/8**, and strictly healthier than the prior v8.3 8/8
(fixed the pro-rata T3 regression, u ~0.27→~0.18, cleaner T8 tail −0.87). Nothing tuned to a target — the
founder pool is externally anchored and the 8/8 *emerged*.

### 27.5 Open items
- **Full-NW-Gini metric artifact:** `hh_full_networth_gini` collapses to ~0.05 after t≈2500 (both v8.4 and
  v8.5) while `hh_wealth_gini_incl_equity` stays ~0.70 — leverage compresses *net* worth even as *gross*
  wealth stays concentrated. Present in both modes; the min-shift normalization likely degenerates under
  negative net worth. Decide which wealth measure T8 should use.
- **Tobin-q dispersion outlier:** a single tiny-book firm can spike `tobin_q_dispersion` to ~10³ for one
  tick; harmless but a valuation floor would clean it.
- **Does founder+lower-churn persist concentration?** v8.5 alone doesn't hold the blocks. v8.6 candidate:
  founder genesis + slow rebalancing (`portfolio_adjust`<1) — would test whether persistent concentration
  sharpens T8 *beyond* −0.87. (v8.2's slow-rebalance was falsified WITHOUT founder genesis; the combination
  is untested.)

### 27.6 Methods — parallel runs
Seed sweeps now fan across all cores: `prun.py` (`run_jobs(jobs)`), `validate_parallel.py <factory>
<seeds>` (parallel §4). ~7.5× on the 10-core M5. Every result above is 5-seed unless noted.

---

## §28 v9 — the GOVERNMENT sector (built, diagnosed net-NEGATIVE, being repaired)

**Status: in progress.** The government mechanism is built, conserving (A5), and bit-identical when off
(`government=False` ⇒ v8.5, still 8/8). But the default `Config.v9()` scores **§4 5/8** — the government
is a net drag. The diagnosis (§28.4) found the fault is in our *fiscal mechanism*, not "government is bad."

### 28.1 What v9 is — the interactive control surface (PLAN_v9)
A consolidated **Treasury** (central bank deferred to v10). The organising idea: **`Policy` is the only
state mutable DURING a run** (the government's levers — taxes, spending, macroprudential caps); everything
else is frozen `Config`. This split (`policy.py`, seeded from `Config`) is the foundation for the eventual
interactive-software vision. A government running a deficit issues **outside money** (its `GOV` ledger
account goes negative = government debt = private net financial wealth; A5 untouched since transfers
conserve — required making `allow_negative` actually exempt an account from the overdraft gate in
`transfer`, a latent gap).

### 28.2 The build (all A5-safe, off ⇒ bit-identical)
- **Four tax bases:** profit (pre-dividend), **progressive** income (marginal rate above a personal
  allowance), VAT (in the goods market), wealth (on net worth). Flow taxes at real rates; wealth tax
  re-anchored to ~0.2× the per-tick return (a stock tax per tick ≠ a flow tax).
- **Two spends:** unemployment benefit (to the involuntarily unemployed, into `income_realized`),
  government consumption (a buyer in the goods market).
- **Deficit-targeting rule:** gov consumption is sized so the deficit ≈ `gov_deficit_target·GDP`
  (tax-financed G + a controlled deficit). The pure-quantity mode (`g·potential`) overheats a stationary
  economy (u→0, debt explodes); deficit-targeting is self-limiting.
- **Macroprudential:** `margin_ltv`, `margin_max`, `kappa`, `hh_credit_limit` reclassified from Config
  dials into live `Policy` levers.
- **Household bankruptcy:** an insolvent household (net worth ≤0 after the margin call) is discharged —
  repay what cash it has, WRITE OFF the rest (bank absorbs, like a firm default), keep shares, emerge with
  no margin debt. The §27 demand-death exit valve.
- **Normalised fiscal metrics:** `gov_deficit_to_revenue`, `gov_deficit_to_gdp`, `gov_debt_to_gdp` (raw
  stocks are unreadable). Also a float-robustness guard on the CLEARING drains (`> EPS`).

### 28.3 What works, and the §4 verdict
- **Fiscal works early/medium:** a maintained **2–5%-of-GDP deficit** (real-world normal) drives u from
  ~0.05 to ~0.005 and eliminates deep recessions — the functional-finance result (a demand-starved economy
  needs the outside money the §9 drain denies it). **Balanced budget fails** (u stuck ~0.5): a taxing,
  hoarding government *is* a private-sector drain (SFC identity: gov surplus = private deficit).
- **Bankruptcy helps the long run:** late-window u **0.449→0.319** (a continuous ~0.03/tick discharge
  recycles insolvent households back into demand). The §27 intuition confirmed.
- **§4 = 5/8.** Passes T1, T2, **T4 (mean u 0.185)**, T5, **T8**. Fails **T3** (credit comovement −0.02),
  **T6** (firm Zipf slope −2.62, Gini 0.88), **T7** (credit boom-bust). The government is OFF by default,
  so v8.5's 8/8 frontier is preserved; v9 is an opt-in layer that currently trades §4 fit for the mechanism.

### 28.4 DIAGNOSIS — one confirmed error; the long-run degradation is UNPINNED (honest)
Real government is decisively net-positive; ours is net-negative ⇒ **our fiscal design is flawed.** One
error is confirmed; the other proposed cause did not survive testing, and the underlying long-run
degradation resisted ~6 hypotheses. Reported honestly, warts included.
- **Error (CONFIRMED) — the deficit rule was not state-dependent.** A fixed 3%-of-GDP deficit *regardless of
  slack* means that once the economy hits full employment the injection has no idle capacity to activate and
  becomes pure **inflation** (price 1.3→10.5). Fix 2 (§28.6) confirmed the mechanism: tapering the deficit at
  full employment cut inflation to 8.2 and restored **T7**.
- **Credit decoupling (T3, T7)** is *partly realistic*, not an error: a large fiscal state makes the economy
  less credit-cycle-driven, so credit-output comovement falls. (Fix 2 recovered T7 anyway.)
- **Corrected over-attribution #1 (missing supply side):** an early diagnosis blamed the net-negative on the
  absent supply side (no public investment raising productivity). Real *limitation* (our government "spends"
  but doesn't "build"), but NOT the cause — pure tax-and-spend is genuinely positive in a demand-starved
  economy (and is, early). Deferred as a genuine future improvement, not a bug.
- **Corrected over-attribution #2 (procurement concentration):** the leading "government funnels procurement
  to the biggest firms → concentration → long-run u" story was **falsified**. (a) **Competitive procurement**
  (buy cheapest) was NULL — the government is a *minority* of demand. (b) The concentration is HOUSEHOLD-side
  (households buy by attractiveness, never price, §28.5) — but making household demand **price-sensitive**
  (∝ attr^β/price^ε) was ALSO null: over 4000 ticks the Gibrat attractiveness spread reaches orders of
  magnitude, so price^ε (prices vary a few ×) can't counter it. (c) Worse, **concentration→u itself is not
  established:** varying β left firm-output-Gini pinned at ~0.94 while u ranged 0.36–0.51, and the within-run
  corr(Gini,u) is only +0.29 (and that Gini is confounded by ~140 idle firms). So the T6 failure is real and
  robust, but it is **not shown to cause** the long-run u.
- **The long-run u degradation is UNPINNED.** Hypotheses tested and refuted/unsupported (~6): household
  insolvency (~4/1000, households *gain* money share), inflation-as-driver (halving the deficit barely moved
  u), household leverage (very-tight margin cut debt 55k→18k, u unmoved), gov-procurement concentration
  (competitive null), household price-insensitivity (ε null), firm-concentration-as-cause (β test above). It
  is a subtle Gibrat-×-government long-horizon interaction that one-shot experiments could not crack — a
  first-class **open question** needing a dedicated study, not more single guesses. One untested lead: the
  government suppresses the deep crises that, in v8.5, periodically *reset* firm concentration (u there
  mean-reverts to ~0.11; in v9 it degrades) — "stability breeds concentration," Minsky-flavoured.

### 28.5 Structural note — nobody price-competes on the demand side
Since v8.1, the goods market uses PreferentialMatch (demand ∝ attractiveness^β) for **all** buyers, so
**households do not compare prices** — a strong assumption adopted to get the Zipf firm-size law (T6).
Consumers are partly brand-driven (justifying it) but also price-sensitive (which we dropped), removing a
demand-side price brake — plausibly contributing to the v9 inflation. A more realistic demand would blend
both (∝ attractiveness^β / price^ε), keeping Zipf *and* restoring price discipline (deferred, larger change).

### 28.6 Repairs and results — §4 5/8 → **6/8**
1. **Competitive procurement (`_phase3_goods`):** gov demand now buys from the **cheapest** c-firms first (a
   tender), not via PreferentialMatch. **Result: NULL on §4** — it barely moved concentration/u/price.
   Diagnosis corrected: the government is a *minority* of demand; **firm concentration is driven by
   HOUSEHOLD preferential demand** (the majority, which never price-competes — §28.5), so re-routing the
   government's slice can't fix it. Kept anyway as a realism improvement (governments *do* tender).
2. **State-dependent deficit (`deficit_u_ref`):** the deficit target is scaled by `min(1, u/u_ref)` — full
   deficit under slack, **tapering to balance at full employment**. **Result: a real win.** It restored the
   countercyclical stabilizer (deficit ≈0 when u low, ~2% when u high), cut late-run inflation (price index
   11.5→8.2), and — the §4 payoff — **T7 flipped FAIL→PASS** (credit boom-bust comoves again, +0.04→+0.20).
   T3 improved (−0.02→+0.14, near the 0.2 bar) and T6 eased (−2.62→−1.97, Gini 0.88→0.81) but both still fail.

3. **Household price-sensitive demand (`pref_price_elasticity` ε; ∝ attr^β/price^ε):** built to fix the
   household-side concentration (§28.5). **Result: NULL on T6** — firm-output-Gini stayed ~0.92 and the
   Pareto slope ~−1.7 across ε∈{0.5,1,2}; only mild inflation relief (8→6.5). The Gibrat attractiveness
   spread (orders of magnitude over 4000 ticks) swamps price^ε (a few ×). Kept as a realistic, off-by-default
   lever (ε=0 ⇒ bit-identical); it is NOT the T6 fix we hoped.

**Net: `Config.v9()` scores §4 6/8** (fails T3 marginally, T6). Both remaining fails trace to the long-run
firm-concentration/degradation whose cause is **unpinned** (§28.4) — not reachable by any fiscal, procurement,
or demand-side lever we tried.

### 28.7 Deferred (future layers)
- **The long-run-degradation study** (§28.4): the open question. Lead to test — does the government suppress
  the crises that reset concentration? Needs firm turnover/death-rate + attractiveness-spread analysis
  (v8.5 vs v9), not another one-shot macro run.
- **Supply-side public investment** (gov spending → public capital → productivity): the missing role that
  makes real government decisively net-positive (we modeled the government that *spends*, not that *builds*).
- **Central bank (v10):** interest rate, bonds, bond interest, lender of last resort.
- Neutral+SME procurement, consumption/wealth-tax experiments, min-wage lever (built, off by default),
  `pref_price_elasticity` (built, off — didn't fix T6 but disciplines prices).

### 28.8 THOROUGH v8.5-vs-v9 diagnosis (5 seeds, proper scale, full 4000 ticks)
The definitive comparison (supersedes the scattered one-shot findings above). It answers both questions and,
in doing so, **reverses my §28.4 stance on the supply side**.

**Part B — is v9 better or worse? WORSE, on nearly every welfare/stability dimension.**

| dimension | v8.5 | v9 | |
|---|---|---|---|
| unemployment mean | 0.174 | **0.292** | worse +68% |
| unemployment sd / frac u>0.5 | 0.156 / 5% | 0.243 / **23%** | worse (4.5× deep recessions) |
| u early/mid/late | 0.05/0.28/**0.10** | 0.01/0.24/**0.42** | better early, degrades late |
| real output | 1865 | **1581** | worse −15% |
| output CV | 0.167 | **0.314** | worse 2× |
| **real consumption (welfare)** | 1881 | **1608** | **worse −15%** |
| price index (late) / inflation | 1.27 / 0.002 | **8.0 / 0.013** | worse 6× |
| income / wealth / **consumption** Gini | 0.32 / 0.72 / 0.198 | 0.34 / 0.74 / 0.198 | ≈ same |
| **household money share (§9 drain)** | 0.054 | **0.190** | **better 3.5×** |

The government's ONE win — reversing the §9 drain (households finally hold money) — is **hollow**: real
consumption is *lower* (−15%) despite the higher money share, because the inflation it causes erodes the
money and output falls. It put money in households' hands and then inflated it away.

**Part A — the T3 and T6 causal chains.**
- **T3 (credit comovement), partly realistic.** Decomposition: **firm credit turns counter-cyclical**
  (+0.01→−0.11) and **consumption de-couples** (+0.75→+0.56). The deficit supplies demand that isn't
  credit-financed, so credit stops driving the cycle. A large fiscal state genuinely is less credit-driven.
- **T6 (firm concentration) — and the crisis-reset hypothesis is REFUTED.** v9's firm sector **churns MORE,
  not less**: births +71% (1.55→2.66) AND deaths +71% (1.57→2.66), yet **half the firms survive** (129→60)
  and concentration jumps (Gini 0.80→0.95, Pareto −0.53→−1.95). So it is not "government suppresses the
  resets" (the opposite of the data) nor "procurement funnels to giants" (falsified). It is: the government's
  **inflationary, volatile environment** (price 6×, output CV 2×) kills small firms faster, only giants
  survive, and entrants churn in and die without establishing. Concentration is a *symptom of the turbulence*.

**Synthesis — one causal chain, and the corrected conclusion.**
> In a **stationary economy** (fixed productivity) a persistent government deficit has **no productive
> outlet**, so it becomes **inflation + volatility** rather than output → a turbulent environment that
> lowers real output/consumption and churns-and-concentrates the firm sector → the long-run degradation.

This **corrects §28.4**: I had said the missing supply side was "a real limitation but NOT the cause" of the
net-negative. The thorough data says otherwise — **the missing supply side IS the long-run cause.** Pure
tax-and-spend is positive *early* (demand support, u→0), but with **no public-investment outlet** the
sustained deficit inflates and degrades. A real government's deficit funds investment that grows capacity and
absorbs the injection; ours only spends. **So the government that *builds* (not just *spends*) is not a
"nice-to-have" — it is the specific fix that would turn v9 net-positive.** That is the clear next target.
*(Still not fully pinned: why deficit→inflation is so violent here (6×), and the exact turbulence→death
threshold — but the direction, magnitude, and the supply-side conclusion are now solid.)*

---

## §29 v9.1 — the SUPPLY SIDE: government investment → public capital → productivity (the FIX, VALIDATED)

**§28.8's prediction confirmed.** Giving the government the missing supply side flips it from net-NEGATIVE
(v9) to net-**POSITIVE** — and above v8.5. This is the payoff of the whole government arc.

### 29.1 Mechanism (all foundations already existed; only the last link is new)
Government investment buys real capital goods from the K-sector (cheapest-first tender), accumulating an
economy-wide **public capital stock** `K_pub` (`= (1-δ_pub)K_pub + gov capital units`, reusing the firm
capital-accumulation primitive). `K_pub` raises EVERY C-firm's productivity (Barro 1990):
```
Y_f = A · K_f^α · N_f^{1-α} · (1 + K_pub / K_ref)^γ         (K_ref = genesis private C-capital; factor ≥ 1)
```
`gov_investment_share=0` or `γ=0` ⇒ factor 1 ⇒ bit-identical. `K_pub` is a REAL stock (not money), so A5 is
untouched. Side benefit: it is demand for the chronically-sink K-sector (§11.4).

### 29.2 The welfare verdict — v9.1 wins on REAL output, REAL consumption, AND unemployment (5 seeds)
| (steady-state, real terms) | v8.5 (no govt) | v9 (govt, no supply) | **v9.1 (supply side)** |
|---|---|---|---|
| real output | 1878 | 1563 | **2582** (+37% vs v8.5) |
| **real consumption (welfare)** | 1893 | 1589 | **2612** (+38%) |
| unemployment | 0.168 | 0.299 | **0.060** |
| price index (nominal) | 1.4 | 5.2 | 13.9 |

v9 alone was *worse* than v8.5 (§28.8); **v9.1 is decisively better than both.** The public-capital
productivity boost (factor→~1.33) grows real capacity, so the deficit finally buys more real output, not
just higher prices. The one blemish is a higher **nominal** price level — but welfare is REAL, and real
output/consumption are the highest of all three. **The government that BUILDS is net-positive, as in reality.**

### 29.3 §0-ii / §0-iv HONESTY (read this before trusting the win)
The default `Config.v91()` uses **STRONG** parameters — `gov_investment_share=0.10`, `public_capital_gamma
=0.3` — roughly **2–3× the empirical anchors** (real public-investment/GDP ~4%, public-capital output
elasticity ~0.1). At the *anchored* strength the effect is a mere ~3% productivity boost — **too weak to
overcome v9's inflation/degradation in this model**. So the honest reading: the supply-side **mechanism is
validated and the direction is certainly right**, but our model needs an above-empirical public-capital
elasticity to see the flip. NOT tuned to a §4 target (§0-ii intact); tuned — openly, above-anchor — to
demonstrate the mechanism. Why our response is weak: γ~0.1 is modest, K_pub converges to a bounded *level*
(not endogenous growth), and the small K-sector bottlenecks large public investment.

### 29.4 What failed along the way (kept honestly)
- **Composition shift (fund investment WITHIN the deficit, not on top):** collapsed the economy — carving the
  investment out drove government *consumption* (the C-sector's demand floor) to zero, and the small K-sector
  couldn't absorb the investment. Reverted to on-top (investment adds to the deficit → the inflation cost).
- So there is **no free lunch**: consumption supports C-demand (inflationary), investment builds capacity
  (K-sector-bottlenecked, lagged). The real gains come from the *productivity* channel, at a nominal-inflation cost.

### 29.5 §4 and the growth caveat
`K_pub` gives a bounded productivity *level* boost (converges to steady state), so the economy is **near-
stationary with a one-time capacity lift**, not runaway growth — §4's stationarity assumptions still roughly
hold. Score: **§4 = 6/8** (same as v9 — the scorecard tests *structure*, not welfare *levels*, so the real
output/consumption/employment gains don't register). Fails T3 (now the *investment* comovement, +0.07) and
T6 (the rank-size slope came back `nan` — a **measurement breakdown**: the productivity boost + idle firms
degenerate the log-log fit, worth fixing). Notably **T4 mean u = 0.059** — near full employment, the welfare
win showing through a passing test. Read alongside the higher nominal price level.

### 29.6 Status & open items
`Config.v91()` = the supply-side frontier; government off ⇒ v8.5 8/8 preserved; `test_v91_public_capital`.
Open: reduce the nominal inflation without collapsing demand (tax-financed investment? a bigger K-sector?);
endogenous GROWTH (vs level) needs stronger increasing returns; the v10 central bank (rates + growth).

---

## §30 v9.2 — money (non-)neutrality & the indexed-startup fix

### 30.1 The question (a user challenge)
Under money neutrality, inflation is supposed to be a veil — nominal prices rescale, real allocations don't
move. So (the challenge went) our inflation should be roughly *harmless*. I first agreed. Then I **ran it**,
and retracted: **this economy is decisively NON-neutral.**

### 30.2 The test — flex the prices, watch real output move (v9.1 stack, 5 seeds)
Money is non-neutral iff a *purely nominal* knob shifts real outcomes. The cleanest such knob is Calvo price
stickiness `theta_price` (the fraction of firms that may reprice each tick) — flexing it changes nothing real
under neutrality. It changes a lot:
| `theta_price` (higher = more flexible) | real output | unemployment |
|---|---|---|
| 0.10 (sticky, the default) | 2065 | 0.264 |
| 0.60 (flexible) | **2859** (+38%) | **0.036** |
Making prices *more flexible* raises real output ~38% and nearly clears the labor market. **The real cost of
inflation here is sticky-price MISALLOCATION, not the price level itself.** Neutrality fails because the model
has four genuine nominal rigidities: DNWR (strict wage floor, δ=0, §…), Calvo price stickiness, the fixed
nominal loan rate, and the fixed nominal startup endowment. Inflation interacts with each to move real things.

### 30.3 v9.2 — isolate & remove ONE rigidity: the fixed-nominal startup endowment
Entrants get a fixed NOMINAL cash endowment (`startup_deposits`). Under inflation that buys ever fewer workers,
so late entrants are starved → die young → the incumbent tail concentrates. Hypothesis: **this artifact is the
T6/inflation-concentration link.** `index_startup=True` scales the endowment by the price level (a COLA for new
firms) ⇒ **real-invariant entry**. `False` ⇒ bit-identical. A **correctness fix, not a policy lever, not tuned**
(§0-ii): it removes a real non-neutrality regardless of what it does to any §4 target.

### 30.4 Result — NULL on concentration (the honest non-finding)
Indexing entry did **not** move the firm-size tail (5 seeds):
| | firm-size Gini | Pareto slope | real output |
|---|---|---|---|
| v9.1 (fixed-nominal entry) | 0.98 | −2.59 | 2681 |
| v9.2 (indexed entry) | 0.97 | −2.65 | 2640 |
So the startup artifact was **not** the concentration driver. **Concentration is a deep Gibrat / preferential-
attachment property** — unpinned by *every* lever tried (insolvency, leverage, inflation, procurement, price-
insensitivity, crisis-reset, and now indexed entry; §28.8 list). It stays an **open question**, logged, not
tuned away. v9.2 is kept anyway — it correctly kills one non-neutrality and is real-invariant by construction.

### 30.5 Verdict
The inflation cost that matters is **sticky-price misallocation** — a nominal friction whose proper instrument
is a **central bank** (rates, expectations), i.e. **v10**, not another fiscal lever. This corrects my initial
"inflation is probably harmless": in a model *with* nominal rigidities, it is not. `Config.v92()` = v9.1 +
indexed entry; government off ⇒ v8.5 8/8 preserved.

---

## §31 Distributional welfare metrics — the poor are the unemployed

### 31.1 Why (min_wage / subsistence were invisible)
We had labor-floor levers (`min_wage`, `hh_subsistence`) but **no metric that could see them** — every verdict
was an *aggregate* (real output, mean u). So we added a distributional block to `metrics.py` (pure observation,
**bit-identical**, no behavior touched): relative **poverty rate** (consumption < 50% of median), FGT **poverty
gap**, **bottom-decile real consumption** (Rawlsian), **log social welfare** (CRRA/utilitarian mean-log),
**Sen welfare** (mean × (1−Gini)), **income-poverty rate**, and **consumption-floor share** (≤ subsistence).

### 31.2 The verdict — re-reading the whole government arc through the bottom tail (5 seeds)
| | poverty rate | poverty gap | income-pov | **bottom-10% real C** | log-welfare | Sen | cons-Gini |
|---|---|---|---|---|---|---|---|
| v8.5 (no govt) | 0.024 | 0.281 | 0.143 | 0.535 | −0.212 | 0.76 | 0.21 |
| v9 (govt, no supply) | 0.027 | 0.306 | 0.136 | **0.312** | **−0.749** | **0.46** | 0.19 |
| **v9.1 (supply side)** | **0.008** | **0.205** | **0.058** | **0.581** | −0.274 | 0.72 | **0.15** |

- **v9 was REGRESSIVE.** Its damage (§28.8) fell *hardest on the bottom*: bottom-decile real consumption
  collapsed −42% (0.535→0.312), log-welfare −0.21→−0.75, Sen 0.76→0.46. A deficit with no supply outlet
  doesn't just shrink the pie — it shrinks it **from the bottom**.
- **v9.1 is PRO-POOR.** Income poverty **halved** (0.143→0.058), poverty rate cut two-thirds, bottom-decile
  consumption the highest of all three. The supply-side win reaches the bottom.

### 31.3 The mechanism — welfare at the bottom is an EMPLOYMENT story
The through-line: whatever moves **unemployment** moves the bottom decile. v9 raised u to 0.30 → the poor
(who are largely the unemployed) got poorer; v9.1 cut u to 0.06 → they got jobs, wages, consumption. The
productivity boost reaches the poor **through jobs, not through cheaper goods.** This is the pivotal finding
for what comes next: **the highest-leverage anti-poverty instrument in this model is the labor market.**

### 31.4 Discovery — `min_wage` was a no-op flag
Wiring check for the labor version turned up that `min_wage` **existed in `Config` but was never read** —
`plan_wage` never applied a floor. So every prior run's `min_wage` was inert. **v9.3 fixes this first** (a real
wage floor in `plan_wage`), then adds a **job guarantee** (uncapped employer of last resort) — both aimed
squarely at the employment channel §31.3 identifies. (UBI deliberately skipped: least-targeted, and §31.3 says
the lever is *jobs*, not untargeted transfers.)

---

## §32 v9.3 — LABOR welfare: the job guarantee is a state-dependent employment instrument

§31 found welfare at the bottom is an **employment** story, so v9.3 targets the labor market directly. Two
levers: the now-wired **min_wage** floor, and a **JOB GUARANTEE** (employer of last resort). Both foundations
already existed — the JG reuses the benefit's outside-money flow and the v9.1 public-capital channel.

### 32.1 Mechanism (all primitives already existed)
After the private labour market clears, the government hires **every household's residual (unemployed) labour**
at a transitional JG wage (`jg_wage_ratio · mean wage`), **UNCAPPED** — a buffer stock, the defining feature.
It is paid as **outside money** (GOV → household, exactly the benefit's flow, so A5 holds) and **replaces the
dole** for takers (the benefit nets out `jg_labor`). The public-works labour builds **public capital**
(`jg_productivity` units each, reusing the v9.1 K_pub stock). Its deficit swings **on top** of the discretionary
target — an **automatic stabilizer** (§29.4's lesson: carving spending *within* the target collapses demand;
the JG is on-top). Crucially the JG touches only **household** state — the firm-side `unemployment_rate` metric
(T4) is left exactly as-is; we add `effective_unemployment` (no-income) and `jg_employment` (the buffer size).
`job_guarantee=False & min_wage=0` ⇒ **bit-identical to v9.2**.

### 32.2 The verdict — the JG's effect scales with the SLACK it finds (battery: NC=200/NK=100/NH=2000, 4 seeds)
| (steady state) | v9 | **v9+JG** | v9.1 | **v9.3** = v9.1+JG |
|---|---|---|---|---|
| real output | 1586 | **2001** (+26%) | 2536 | **2615** |
| private u (firm-side) | 0.270 | **0.143** | 0.039 | **0.023** |
| effective u (no income) | 0.270 | **0.001** | 0.039 | **0.000** |
| JG employment (buffer) | — | **0.142** | — | **0.023** |
| bottom-10% real C | 0.304 | **0.409** (+35%) | 0.602 | **0.610** |
| log welfare | −0.746 | **−0.525** | −0.282 | **−0.251** |
| Sen welfare | 0.457 | **0.552** | 0.720 | **0.732** |
| consumption Gini | 0.199 | **0.168** | 0.139 | **0.131** |
| deficit / GDP | 0.021 | 0.049 | −0.012 | −0.005 |
| price index (nominal) | 4.05 | 5.98 | 8.96 | 8.74 |

**The JG is a state-dependent instrument — it does exactly as much as the slack requires:**
- **On the demand-starved v9 (u=0.27), it is decisive.** The buffer stock swells to **14% of the labour force**
  and works through TWO channels: (a) direct — it clears *effective* (no-income) unemployment to ≈0; (b) a
  **demand multiplier** — JG wages fund consumption → firms sell more → **private** hiring rises (u 0.27→**0.14**).
  It doesn't just warehouse the unemployed, it **reflates** a demand-starved economy: real output +26%,
  bottom-decile consumption +35%, log-welfare −0.75→−0.53, Sen +0.10, Gini −0.03. This is the direct payoff of
  §31.3 (the poor are the unemployed → give them jobs).
- **On the near-full-employment v9.1 (u=0.04), it is nearly dormant** — the buffer is only 2.3%, mopping up the
  residual the supply side left. Correct buffer-stock behaviour. It still nudges **every** welfare metric the
  right way (log-welfare −0.282→−0.251, income poverty 0.033→0.020, Gini 0.139→0.131), so **`Config.v93()` is the
  new welfare frontier** — a small strict improvement over v9.1.

### 32.3 Cost and an honest blemish
The JG is **deficit-financed and mildly inflationary** — on v9 it adds ~2.8pp to the deficit/GDP (an automatic
stabilizer, so it self-shrinks as slack clears) and lifts the price level ~48%. And a genuine distributional
nuance: **on v9+JG, relative *income* poverty ROSE (0.131→0.159)** even as consumption welfare rose across the
board — because the JG wage (0.5× mean) lifts people only *partway*, so many clear the consumption floor while
still sitting below half of median income. The **consumption**-based measures (the truer welfare read here —
what people actually eat) all improved; the relative *income* line is the one caveat. Recorded, not smoothed over.

### 32.4 min_wage, UBI, and §4
`min_wage` is now a **real** statutory floor (§31.4 fixed the no-op): it binds immediately, bypassing Calvo
(`test_min_wage_floor_binds`). It is left **off** in the default v9.3 — a wage floor's disemployment effect cuts
*against* the same employment channel, so it is kept as a separately-tested lever, not bundled into the frontier.
**UBI skipped** (least-targeted; §31.3 says the lever is jobs). §4 is not re-scored here — the scorecard tests
*structure*, not welfare *levels* (§29.5), and the JG is a welfare lever; a full §4 run on v9.3 is the natural
next check. `test_v93_labor` (5/5); off ⇒ v9.2 bit-identical; full 22-suite regression green.

---

## §33 v10 + v10.1 — the CENTRAL BANK: an endogenous policy rate, and why monetary policy is defanged here

The monetary leg of the policy triad (fiscal ✓ supply ✓ monetary ✗). §30 named it: the sticky-price inflation
cost is "the v10 central bank's job." What v10 actually revealed is deeper — in this economy, conventional
monetary policy barely works, for reasons that turned into the most instructive investigation of the arc.

### 33.1 The mechanism (v10) — one thing: an endogenous policy rate
The frozen `r_interest` becomes a per-tick **policy rate** set by a Taylor rule (tick start, from last tick's
smoothed inflation + unemployment):
```
r = clip( ρ·r_{-1} + (1-ρ)·[ r* + φ_π·(π̄ - π*) - φ_u·(u - u*) ] , 0, r_max )
```
The whole transmission was **already wired to `r_interest`** — the investment/entry hurdle (`return − r`),
equity valuation (`book + ema(π−r·book)/r`), and firm+household debt service (`r·debt`). So v10 only makes the
rate MOVE; no new stock, no new money ⇒ A5 trivially holds. `central_bank=False` ⇒ bit-identical. It is a
**rate-only** bank: no bonds/OMO/reserves/QE (all need a securities layer — PLAN_v10 §9, a deferred v11).

### 33.2 The diagnosis — a "perverse" transmission that turned out to be a real defect
First validation looked alarming: higher r → higher output. Not a bug in v10 — the rate–output relation is
**hump-shaped** (clean on stationary v8.5: output peaks at r≈0.02, contractionary on *both* sides). The
conventional sign holds on the upper branch; the **low branch** was perverse because of an over-strong
**interest-income demand channel**, whose root was a v3-bank shortcut: the bank **split collected interest
EQUALLY across all households** ("bank dividend", plumbing to close the loop) — paying interest even to
zero-deposit hand-to-mouth households (MPC 0.8, spent in full), maximising the demand injection.

### 33.3 v10.1 — pay interest BY DEPOSITS (the fix)
The correct recipient of interest is the **depositor, ∝ deposits**. `interest_by_deposits=True` routes
`payable · D_h/ΣD` (a single bank→household transfer ⇒ A5 untouched; `False` ⇒ bit-identical). On the clean
**v8.5** this **restores conventional monotone-contractionary transmission** — output now falls and u rises
with r across the range (r 0.005→0.05: output 1715→1176, u 0.25→0.47). The equal-split really was the distortion.

### 33.4 But on the FULL v9.3 stack the central bank is DOUBLY DEFANGED (the investigation)
Deposit-proportional did **not** make the full stack conventional. Two independent forces neuter monetary policy:
- **Fiscal dominance (investigation B):** v9.3's inflation is **entirely deficit-driven** — zero deficit ⇒
  inflation ≈ 0 (but u explodes to 0.48, the demand-starved economy); *any* positive deficit ⇒ inflation pins at
  ~0.012 and stays **flat** (0.011→0.012 across deficit 0.015→0.05). The deficit that buys full employment
  brings ~0.012 inflation, period. **The rate cannot reach a fiscally-set price level.**
- **The JG stabilizer (investigation C1):** the job guarantee catches workers a rate hike displaces from private
  firms — with the JG off, a hike raises u **3× more** (r 0.005→0.05: u 0.025→0.082 vs 0.014→0.040). The JG's
  automatic stabilization **absorbs monetary contraction.**
So on v9.3, higher r stays (weakly) expansionary and inflation is untouchable — a conventional Taylor rule
**cannot** work. This is a genuine macro result (fiscal dominance + an employer-of-last-resort blunting the rate),
not a modeling failure.

### 33.5 The tuned stance — 'gentle', and the honest verdict (investigation C2)
The naive default (target 0.001 ≪ the 0.012 structural level) is **pathological** — it reads "inflation far
above target" forever and permanently over-tightens (rate→0.038), worst on nearly every metric. Tuning study
(battery, 4 seeds, means + volatility vs no-CB):
| stance | infl | u | infl-vol | welfare-log | bottom-10% C |
|---|---|---|---|---|---|
| no central bank | 0.0117 | 0.025 | 0.159 | −0.262 | 0.598 |
| target 0.001 (naive) | 0.0189 | 0.059 | 0.234 | −0.215 | 0.587 |
| **gentle (t0.012, φπ1.2, φu1.0)** | **0.0103** | 0.083 | **0.150** | **−0.158** | 0.562 |
| leaning (t0.012, φπ1.5, φu0.0) | 0.0140 | 0.024 | 0.182 | −0.290 | 0.563 |

**No stance Pareto-beats no-CB** (fiscal dominance guarantees a sacrifice ratio). But **'gentle'** — target
anchored to the *structural* inflation, moderate φ — is the only stance that beats no-CB on **inflation level,
inflation volatility, AND aggregate welfare** simultaneously. That is the central bank's real job under fiscal
dominance: **stabilize, don't dominate.** `Config.v10()` adopts gentle as its default. **Honest cost:** gentle's
disinflation is **regressive** — higher u and a lower bottom decile (0.562 vs 0.598), the sacrifice falling on
the poor (the same employment channel as §31). A rate anchored to structure isn't a free lunch; it is a
dual-mandate *choice*, exposed as a live Policy lever.

### 33.6 Status, discipline, deferred
`Config.v10()` = gentle CB on the v9.3 stack; `Config.v101()` = v10 + deposit-proportional interest (the correct
bank). §0-ii: CB params anchored to real monetary magnitudes / the economy's own structural inflation, never to
a §4 target; the perverse-transmission and fiscal-dominance findings were pre-registered probes, honestly
reported (the CB is weaker than hoped). `central_bank=False & interest_by_deposits=False` ⇒ v9.3 bit-identical;
`test_v10_central_bank` (5/5), `test_v101_deposit_interest` (4/4); full 24-suite regression green. **Deferred**
(PLAN_v10 §9): bonds / OMO / reserves / QE (a securities layer, v11); a separate deposit *rate* & loan–deposit
spread (corridor); un-consolidating the CB from the Treasury. **The standing lesson:** with a monetary-financed
deficit and a job guarantee, the economy self-stabilizes fiscally, and monetary policy is left a stabilization
role at a regressive cost — a coherent, if humbling, place for the central bank to enter.

---

## §34 v10.2 — a PROGRESSIVE wealth tax (the threshold that stops taxing the poor)

### 34.1 The defect a threshold fixes
The v9 wealth tax was **flat** — `τ_w` on *all* positive net worth, including zero/low-net-worth hand-to-mouth
households. Real wealth taxes universally carry a large exemption (only the wealthy pay); ours did not. Worse,
in a demand-constrained economy, taxing a cash-poor household's tiny net worth **destroys its consumption** —
a progressive-by-name tax acting regressively. v10.2 adds `wealth_allowance` (exemption = `wealth_allowance ·
mean positive net worth`); only wealth above it is taxed. `wealth_allowance=0` ⇒ flat ⇒ bit-identical.

### 34.2 The verdict — the threshold is decisively pro-poor (v10.1 base, 4 seeds)
Same rate, threshold off vs on (exempt below 1× mean NW):
| | wealth-tax revenue | bottom-10% C | income poverty | wealth Gini | unemployment |
|---|---|---|---|---|---|
| flat 0.002 (v10.1 default) | 334 | 0.562 | 0.180 | 0.762 | 0.083 |
| **progressive 0.002 (v10.2)** | 142 | **0.614** | **0.086** | **0.714** | **0.057** |
| flat 0.02 | 2290 | 0.509 | 0.221 | 0.786 | 0.086 |
| progressive 0.02 | 1111 | **0.569** | **0.162** | **0.683** | **0.071** |

At the default rate the threshold lifts bottom-decile consumption **+9%**, **halves income poverty**
(0.180→0.086), cuts unemployment (0.083→**0.057**), and cuts concentration MORE (Gini 0.762→0.714) — for half
the revenue (only the rich now pay). Mechanism: the flat tax was **demand-destroying at the bottom** (taxing
cash-poor small savers → less spending → higher u); the threshold spares them, so demand holds and the tax
lands only where it should. A tiny cost: slightly lower output and marginally higher inflation (the spared poor
spend a little more).

### 34.3 The reframe (this corrects an earlier over-attribution)
The demand-drain investigation had found "a stronger wealth tax hurts welfare (regressive-through-inflation)."
§34 localizes that: the harm was largely the **flat** structure taxing the poor, not the wealth tax per se.
With a threshold the wealth tax is a genuinely **pro-poor** distributional tool — it drains the idle hoard and
cuts concentration *without* collateral-damaging the bottom. (It still does not "make the economy come alive":
it cannot lower inflation at constant employment or substitute for the deficit's net outside money — those
remain supply-side / fiscal questions.)

### 34.4 Status
`Config.v102()` = v10.1 + `wealth_allowance=1.0` (exempt below mean net worth) — a strict welfare improvement to
the frontier (pro-poor, lower u, less concentration). `wealth_allowance` is a **Policy** lever (the government's
live tax-progressivity dial); the tax rate stays the anchored 0.002. Anchored to real wealth taxes (all carry
exemptions; §0-ii). `wealth_allowance=0` ⇒ v10.1 bit-identical; `test_v102_progressive_wealth` (4/4); full
regression green.

---

## §35 v11 — MULTI-BANK: a realistic "loan-book banks" system (stable; a latent failure machinery)

The financial-sector arc: a single unfailable bank becomes a **system of banks** with realistic complexity —
each with its own capital, loan book, and leverage limit. **Framing (a corrected one, see 35.4):** the goal is
a *realistic banking system*, NOT a crisis demo. Real banks are well-capitalized and rarely fail; ours should
too. The failure machinery is built and correct, but **LATENT** under normal conditions — it awaits a genuine
(future, exogenous) shock. Converged scope: the cheap half (deposits stay global, no reserve/settlement tier).

### 35.1 The design — "loan-book banks" (deposits stay global)
Deposits remain a **single global pool** (payments unchanged, no interbank settlement, no reserve tier — A5
barely touched). Only the **loan book** is partitioned among `n_banks` accounts. The key trick: **a bank's
capital IS its own deposit balance** — the existing `write_off(borrower, BANK, amt)` already makes bad debt
shrink the bank's deposits; with ONE bank that buffer is the whole money supply (never fails), with N accounts
each is **finite**. `n_banks=1` ⇒ one "BANK" ⇒ **bit-identical to v10.2** (the whole v2–v10.2 chain is the
one-bank special case; 26/26 regression). Interest and write-offs route to the borrower's own bank (`bank_of`);
the redistribution total is unchanged.

### 35.2 A realistic, stable banking system
- **Well-capitalized banks:** a bank **retains ρ of its interest income** (pays out the rest as dividends, like
  a firm) → it builds an **adequate capital buffer** and is **STABLE under normal conditions** — it does NOT
  fail from ordinary idiosyncratic defaults (write-offs ≪ retained earnings). This is the realistic behaviour.
- **Heterogeneous leverage limits:** each bank draws a cap `κ_bank` (mean ± dispersion) — risk-appetite
  heterogeneity, so under stress the aggressive/thin banks fail first (selective, not uniform).
- **The leverage cap (`bank_capital_constraint`):** a bank lends only while `loan_book ≤ κ_bank·capital`. On the
  stable frontier banks are well-capitalized so it **rarely binds** (realistic — banks usually have adequate
  capital); it activates only when capital is impaired.
- **The LATENT failure machinery:** if a loss WAVE overruns a bank's capital its balance goes negative ⇒
  insolvent. **Resolution:** marked dead (stops lending), borrowers migrate (`bank_migrate_on_failure`), its
  account **keeps the negative balance = the realized loss** ⇒ A5 untouched (no money created/destroyed).
  Contagion would run through the **real economy**. All correct and conserving — but dormant absent a shock.

### 35.3 Verification — realistic, stable, frontier-preserving
- **Stable (realistic):** `Config.v11()` (n_banks=8) runs **0 bank failures** under normal conditions; banks
  are well-capitalized; output/employment/money-distribution are healthy (~v10.2).
- **Frontier-preserving:** §4 = **6/8** (same as v10.2 — T7 recovers; the multi-bank structure with stable
  banks doesn't distort credit dynamics). `n_banks=1` OR `bank_capital_constraint=False` ⇒ bit-identical.
- **The failure path is CORRECT (not just untested):** under a deliberately EXTREME stress config (many very
  thin, aggressive banks — capital frac 0.005, κ 15 — on a volatile base) banks **do** fail (~26 of 40) and A5
  holds through every failure. So the machinery is exercised and conserving; it simply isn't triggered by a
  healthy economy — exactly as a real banking system behaves.

### 35.4 A corrected course, status & deferred
**Corrected framing (kept honestly):** the first build optimised for *producing crises* — a "thin-bank" payout
(banks pay out to the bare-minimum capital = loan_book/κ) that left every bank one bad tick from insolvency, so
`Config.v11()` **chronically collapsed** (3–8 of 8 banks failing, §4 dropping to 5/8 via a broken T7). That was
**anti-realistic** — real banks don't fail that easily. Corrected to the ρ-retention payout above: banks build
capital and are stable. Lesson (general): **model the mechanism realistically; don't tune a module to manufacture
a phenomenon** — let phenomena (here, bank failures) emerge from genuine shocks, not from a fragile calibration.

`Config.v11()` = v10.2 + `n_banks=8`, `bank_capital_constraint=True` (latent), heterogeneous κ. New levers:
`n_banks`, `bank_leverage_mean/disp`, `bank_assignment`, `bank_capital_constraint`, `bank_migrate_on_failure`
(Config). `test_v11_banks` (5/5); `n_banks=1` ⇒ v10.2 bit-identical; A5 holds through failures; §4 = 6/8; full
26-suite regression green. **Deferred** (PLAN_v11 §8): an **exogenous-shock lever** (to actually stress the
banks); by-size assignment → too-big-to-fail; rate competition; deposit insurance (fiscal); and — needing the
reserve tier, a separate arc of doubtful value here (§33) — **deposit partitioning → interbank / bank runs**,
and **reserves → reserve requirements / LoLR / OMO / QE**.

### 35.5 v11.2 — realistic bank capital (Basel), and a natural-rate insight
**The realism gap in v11.** ρ-retention keeps banks stable but makes them **hoard capital without bound** — by
tick 4000 the banks hold **~2× broad money** in idle deposits (a diagnosed un-realism; real banks hold ~10% of
loans as capital, not an ever-growing cash pile).

**v11.2 — two real institutions replace the hoard** (`Config.v112()` = v11 + these, off ⇒ v11 bit-identical):
- **A Basel CAPITAL RATIO** (`bank_target_capital_ratio=0.1`): banks pay out earnings ABOVE target capital =
  0.1·loan_book (~the real bank leverage ratio) ⇒ capital is **bounded & thin** (leverage ~10, ~3% of money).
- **A LARGE-EXPOSURE limit** (`bank_exposure_limit=0.25`): a single borrower ≤ 0.25·(bank capital), Basel-style
  ⇒ banks are **DIVERSIFIED**, so a thin bank survives any single default; only a loss WAVE breaks it.
Params anchored to reality (§0-ii); the resulting failure rate is **reported, not tuned**: ~1.7/8 banks fail
(emergent), in waves, and the failures **amplify recessions through the real economy** (corr(u, banks-alive)
≈ −0.26 — a bank-crisis → credit-crunch → recession feedback; u spikes to ~0.6 in episodes).

**Two findings this exposed:**
1. **The bank hoard was propping up "realistic" unemployment.** Isolating the two levers: it is the **payout**
   (banks stop hoarding) — NOT the exposure limit, NOT the JG — that drops mean u from ~0.05 to ~0.01. v11's
   idle hoard **drained demand** (household money share 0.22, consumption 24.7k); v11.2's payout **recirculates**
   it (share 0.28, consumption +38% → 34k) ⇒ fuller employment. So v11's "healthy 5% u" was partly an artefact
   of an *unrealistic* bank money-sink.
2. **The model has no NATURAL RATE — the labour market is FRICTIONLESS.** `_phase2_labor` matches instantly, so
   whenever aggregate demand ≥ supply, u → 0. The model has genuine **cyclical / demand-deficient** unemployment
   (involuntary, from the §9 drain + DNWR) but NOT **frictional / structural** unemployment (which needs search
   frictions + worker/job heterogeneity — Mortensen-Pissarides). So **u≈0 at full demand is CORRECT for a
   frictionless economy**; the gap vs reality (~4–5% natural rate) is the missing search-friction layer. This is
   why v11.2 fails **T4** (mean u too low once the hoard-drain is gone) — an honest structural gap, not a bug.

**§4 = 4/8** on `Config.v112()` (T7 breaks — capital-constrained credit changes the cycle; T4 breaks — the
frictionless labour market has no natural-rate floor). Honest (§0-ii: a judge, not a target — Basel params not
tuned to it). `test_v11_banks` 7/7 (adds `test_v112_realistic_capital`, `test_v112_off_bit_identical`); off ⇒
v11 bit-identical; full regression green. **The realistic-banking frontier is `Config.v112()`** (thin,
diversified, bounded); v11 (ρ-hoard, §4 6/8) is kept as its predecessor. **Deferred: a search-and-matching
LABOUR layer (v12)** — an endogenous natural rate would also make the CB's NAIRU real and the JG buffer cleaner.

## §36 v11.3 — loan-rate COMPETITION: market share won on price, and emergent too-big-to-fail

The banking-layer realism arc continues (the user's "拆借、竞争" list, §35.4 deferred). v11.2 banks are realistic
in *capital* but **static in market structure**: a borrower is assigned to a bank at genesis and stays there,
and every bank charges the same rate. Real banks **compete on price** and borrowers **shop** — so market share
is *won*, not handed out. v11.3 adds that, staying inside the cheap "loan-book banks" architecture (deposits
still global — no reserve tier; deposit-side competition / interbank / runs remain for the deposit-partitioning
arc, §35.4).

### 36.1 The design — heterogeneous spreads + borrower shopping
- **A per-bank loan-rate spread** over the policy rate (`bank_spread_disp` = the cross-bank SD): each bank draws
  a spread once (dedicated RNG). It is **mean-preserving** (de-meaned to sum exactly 0) — some banks undercut,
  some charge more (efficiency / market-power heterogeneity), but the **average cost of credit is unchanged**,
  so the layer isolates the *sorting/competition* mechanism rather than shifting the rate level (§0-ii).
- **The rate a borrower pays** = `max(0, policy_rate + spread_of_its_bank)` (`_loan_rate_for`), wired into firm
  and household debt service. Competition off ⇒ the plain policy rate ⇒ **bit-identical**.
- **Borrower shopping** (`_shop_bank`, in `_grant_loan`): when a borrower seeks new credit it samples
  `bank_search_m` rivals (search friction — imperfect information) and switches its **whole relationship** to
  the cheapest one **that has leverage capacity to fund it** (existing debt + the new loan ≤ κ·capital). The
  incumbent is always eligible. The switch moves the borrower's existing debt between loan books (same primitive
  as failure-migration, A5-neutral). So **cheap, well-capitalized banks win share** — but a cheap bank fills its
  capacity and spills the marginal borrower to the next-cheapest, so it grows without becoming a trivial monopoly.

`Config.v113()` = v11.2 + `bank_rate_competition=True`, `bank_spread_disp=0.003` (~⅓ of the policy rate, anchored
to real cross-bank loan-rate dispersion), `bank_search_m=2`. Off (or `n_banks=1`) ⇒ v11.2 bit-identical.

### 36.2 The result — competition concentrates the sector and raises failures (real economy insulated)
8-seed head-to-head (NC100/NK50/NH1000, 2000 ticks, `Config.v112` vs `Config.v113`), tail-mean:

| metric | v11.2 | v11.3 | reading |
|---|---|---|---|
| loan-book Gini | 0.33 | **0.50** | competition **concentrates** the banking sector (+50%) |
| loan-book HHI | 0.19 | **0.27** | well above the even-split floor 0.125 — share is **won on price** |
| loan-rate dispersion (SD) | 0.000 | **0.0025** | a real cross-borrower rate spread emerges |
| bank failures (of 8) | 1.5 | **3.1** | concentration → **too-big-to-fail fragility** (roughly doubles) |
| unemployment | 0.00 | 0.00 | **real economy untouched** |
| real output | 1298 | 1304 | flat (+0.5%) |

**The finding (emergent, reported not tuned):** price competition → winners take share → the loan book
**concentrates** → bigger banks carry bigger books → when one fails it takes **more** with it, so failures
roughly **double** (1.5→3.1 of 8). This is the classic **competition → concentration → too-big-to-fail** channel,
emerging from a price mechanism + a capital constraint, not imposed. Yet the **real economy is insulated**
(u stays 0, output flat): the fiscal deficit + JG hold demand at full employment, so bank failures here
*reallocate* credit among survivors rather than *drain* aggregate demand (the §35.5 hoard-drain channel is
already gone). A genuine exogenous shock (deferred) is what would turn this latent fragility into a real
recession — exactly the realistic ordering (build the fragile structure honestly; let crises come from shocks).

### 36.3 Verification & status
`test_v113_competition` **6/6**: competition off ⇒ v11.2 bit-identical; `n_banks=1` ⇒ v10.2 bit-identical; A5
conserves with competition on; the spreads are exactly mean-preserving; a rate dispersion emerges (≈0 off); the
loan-book HHI rises above the 1/n floor. New metrics `bank_loanbook_hhi`, `bank_rate_spread_sd`. New Config
levers `bank_rate_competition`, `bank_spread_disp`, `bank_search_m`. Full **27-suite regression green**; A5 holds.
**Deferred (still, §35.4):** the deposit-partitioning + reserve tier that unlocks **interbank lending (拆借),
bank runs, and deposit-side competition** — the next big banking-realism step.

## §37 v11.4 — the RESERVE tier + intra-tick RTGS + interbank market: correct, and a diagnosis of why it's latent

The 枢纽. Since v3 deposits were a **single global pool** — a household's money wasn't "at" a bank — which blocks
everything on the funding side (interbank 拆借, runs, deposit competition). v11.4 **partitions deposits**, adds a
**reserve tier** with **full intra-tick RTGS settlement** (the user's explicit choice over a net-settlement
shortcut), an **interbank money market**, and **deposit-side competition**. The build is correct and conserving;
the headline result is a **structural diagnosis** of when a reserve/interbank tier can matter in this economy.

### 37.1 The architecture — a reserve OVERLAY at the one settlement choke point
The deposit ledger stays **exactly as before** (every v2–v11.3 behaviour + the deposit-A5 gate are untouched).
Reserves are a **second accounting layer**: since **every** payment funnels through `Ledger.transfer`, reserve
settlement is hooked **there** (one method, zero call-site edits) — on a payment `src→dst`, reserves move between
`settlement_bank(src)` and `settlement_bank(dst)` (customer→its bank; a bank→itself; CLEARING→a pass-through node;
**GOV→the CB**, the base-money source/sink). `create_loan`/`repay`/`write_off` need no settlement — they preserve
`R_k = capital_k + deposits_k − loans_k` by construction. **Two hard-gated conservation laws:** deposit-A5
(unchanged) **and** reserve conservation (Σ reserves = M₀). Genesis reserves = each bank's capital + its customers'
deposits (all base money; no loans yet). `interbank=False` (or `n_banks=1`) ⇒ **v11.3 bit-identical**.

**A key identity, proven and verified:** at the end of every tick the RTGS-settled reserves equal the balance-
sheet identity `R_k = capital+deposits−loans` **exactly** (drift ~7e-8). This means net-settlement and full RTGS
give the *same* tick-level reserve positions — RTGS only adds *intra-tick* granularity (a bank transiently short
mid-tick), which is the only reason to pay for it (and it needs deposit/loan/reserve backing to **follow** every
relationship switch — shopping, deposit migration, failure migration — via `move_reserves`, else the identity drifts).

### 37.2 The build (all A5-safe; `interbank=True` on the v11.3 stack ⇒ `Config.v114()`)
- **Intra-tick RTGS settlement** + per-tick **intraday-overdraft tracking** (`reserve_min`): the lowest reserve a
  bank touches mid-tick — the peak intraday funding need.
- **Interbank money market:** a reserve-deficit bank borrows from surplus banks; the **rate is endogenous to
  market tightness** (`policy + interbank_tightness·(deficit/surplus)`); interest is a plain transfer; a failed
  debtor bank's residual loss reassigns to its interbank creditors pro-rata (**contagion cascade**, a while-loop).
- **Gridlock instrumentation** (Stage 3): a would-block counter vs the intraday-credit limit
  (`−reserve_floor_frac·capital`) — no invasive payment-blocking built (see the finding: it can never fire here).
- **Deposit-side competition** (opt-in via `deposit_rate_disp>0`; ships OFF — see §37.3): banks post mean-preserving
  **deposit-rate spreads** and pure depositors **shop** (`deposit_search_m`) and migrate toward the higher rate;
  deposits being partitioned, a bank pays its OWN depositors. Absent a funding motive it degenerates (see below).

### 37.3 THE FINDING — the reserve/interbank tier is CORRECT but LATENT (a diagnosis, not a bug)
**No bank ever runs reserve-short — peak intraday overdraft is EXACTLY 0 in every regime** (default, low-, and
zero-deficit), so the interbank market, intraday funding, and gridlock **never activate**. Why (measured): total
credit is only **3.4% of broad money** (money multiplier D/M₀ = **1.03** vs a real 5–10), so nearly all money is
**base money** held as reserves; each bank sits on a reserve buffer **~20× its own per-tick payment flow**; and the
**unsterilised deficit** floods still more reserves in (Σ reserves = M₀ − GOV, ever-growing). Reserves are
hyper-abundant relative to payment flows ⇒ nothing can stress the funding side. This is the **ample-reserves
regime** (post-2008), pushed to an extreme by **thin credit + no bond sterilisation**. The whole funding-liquidity
complex (interbank, gridlock, and the *funding motive* for deposit competition) is **latent** — like v11's failure
machinery — and activates only in a **scarce-reserves** regime: a future **bond/securities layer** that sterilises
the deficit's reserve injections (its true purpose, revealed here), or much thicker credit. Reported, not tuned.

**Deposit-side competition ALSO lacks a genuine driver here — and DEGENERATES** (a third face of the same root):
with reserves hyper-abundant, banks don't need deposits to fund loans, so there is no equilibrating force behind
an imposed exogenous deposit-rate spread. Forced on, depositors all pile into the top-rate bank — **deposit-market
HHI → ~1.0 (monopoly)** and the sector **collapses** (7–8/8 banks fail over a long horizon), regardless of a
congestion damping term. So it ships **OFF** (`deposit_rate_disp=0`): the machinery exists and conserves, but it
cannot produce a realistic result absent a real funding motive. Deposit competition, like interbank lending, needs
a **scarce-reserves** regime (a bond layer) where deposits genuinely fund lending. **The clean v11.4 deliverable is
the correct, conserving reserve/RTGS/interbank INFRASTRUCTURE** — not an active funding-side phenomenon, which this
economy's structure cannot yet support.

### 37.4 Verification & status
`test_v114_interbank` **7/7**: `interbank=False` ⇒ v11.3 bit-identical; `n_banks=1` ⇒ v10.2 bit-identical;
deposit-A5 conserves with the overlay on AND through interbank contagion; reserves conserve (Σ=M₀) AND the RTGS
settlement matches the `R_k=cap+dep−loans` identity each tick; the interbank market is latent (peak overdraft ≈0,
no gridlock); and deposit competition degenerates when forced on (so the shipped default stays near the even-split
floor — it's off). New Ledger primitives (`enable_reserves`,
`_settle_reserves`, `move_reserves`, `reset_intraday`, `assert_reserves_conserved`); new metrics (`bank_reserves_total`,
`cb_reserves`, `interbank_rate/volume`, `interbank_contagion_loss`, `peak_intraday_overdraft`, `payments_gridlocked`,
`bank_deposit_hhi`); new Config levers `interbank`, `interbank_rate_base`, `interbank_tightness`, `reserve_floor_frac`,
`deposit_rate_disp`, `deposit_search_m`. Full **28-suite regression green**; both conservation laws hold.
**Deferred (now well-motivated): a BOND/securities layer** — sterilises the deficit's reserve flood ⇒ scarce
reserves ⇒ the interbank market + gridlock activate ⇒ and it hands the CB OMO/QE. Also **bank runs** (need a
depositor-flight rule on the same partitioning).

## §38 v11.5 — bank DEMOGRAPHICS & OWNERSHIP: entry, equity + a bank-stock market, and runs

The gap a user spotted: banks only ever **died** (insolvency → dead → borrowers migrate to survivors), never
**born** — so the count decayed monotonically toward oligopoly. v11.5 gives banks the firm-style **entry/exit +
ownership** structure: banks are **founded by owners** (de novo), **owned** (profit → shareholder dividends via a
tradeable **bank-stock market**), and can die from a **run** as well as write-offs. It completes the firm↔bank
symmetry. Four opt-in sub-flags, each off ⇒ bit-identical; A5 + reserve conservation + bank-**share** conservation
all hard-gated.

### 38.1 A — equity-ification + a full secondary bank-stock market
- **Ownership:** each bank has `shares_outstanding` + `owners`; genesis banks vest in a **founder class** (v8.5).
  **Bank profit → OWNERS** as dividends (was: to depositors). **Bank equity enters household wealth** (metrics +
  the wealth-tax base); on **failure** price → 0, owners wiped (first-loss).
- **A flagged distributional shift (a finding, not plumbing):** redirecting bank interest income from **depositors**
  (broad) to **owners** (a concentrated founder class) makes bank profit a **wealth-concentration channel** and,
  by draining broad demand, *raises* failures (≈2→4) — a real, reported effect.
- **The market (full v6-style, per bank):** households target `bank_theta_equity` of wealth in bank stock
  (fundamentalist + chartist demand), each bank's price **gropes** on its own excess demand, trades are pro-rata
  rationed and settled via CLEARING so **shares AND money conserve** (drift ~1e-14; reserves settle buyer's
  bank→seller's). The chartist term bubbles/crashes prices away from the fundamental — the **run trigger**.
  Result: prices trade at 0.7–1.0× their own peak (live distress signals), and founder ownership **deconcentrates**
  to the whole population via trading.

### 38.2 B — de-novo bank ENTRY (profit-driven), calibrated for REALISTIC LOW churn
When the banking sector's **ROE beats the policy-rate hurdle**, a household with ≥ `bank_min_capital` **founds** a
bank (A5-safe transfer; the reserve backing follows to the new node) and **owns it 100%**; the entrant **undercuts**
on the loan rate to break in and win borrowers via v11.3 shopping. A **congestion** term makes chartering rare +
self-limiting. **A CALIBRATION lesson (a user caught it):** the first cut used a low capital gate
(`bank_min_capital=200`) → **thin entrants that failed fast** → an unrealistic **near-total turnover** (116 births
/ 108 deaths over 4000 ticks — 87% of all banks ever created had died; banks churned like *firms*, whereas real
banks are long-lived and both failures + de-novo entry are RARE). **Fix (a sweep, `min_capital`×`entry_beta`):**
`bank_min_capital` is the dominant lever (it's founder-wealth-gated) — anchoring it **HIGH (1500, ~2× a genesis
bank's capital)** makes entrants **well-capitalised ⇒ they SURVIVE**, cutting churn **~12×** to a realistic
regime: at the diagnostic scale (200C/100K/2000H, 4000 ticks) **~9 births / ~11 deaths, count stable ~6** — banks
long-lived, entry rare, failures few. Entry OFF ⇒ the count only decays. (`bank_min_capital` is founder-wealth-
constrained, so smaller economies sustain fewer banks — realistic consolidation.)

### 38.3 C — bank RUNS (queued withdrawals; flight active, liquidity-suspension latent)
Depositors flee banks of low **HEALTH** — a blend of the **market** signal (share price / recent peak, the
2008-style stock crash) and the **book** signal (capital / loan book) — amplified by a system-wide **FEAR** level
(panic contagion). A run executes as a **QUEUE** (like `_phase2_labor`): fleeing depositors are served sequentially
from the bank's **OWN reserves** (loans are illiquid; **interbank FROZEN** — no one funds a bank being run); when
reserves are exhausted the bank **SUSPENDS** and fails from **illiquidity**. **Honest scope (the recurring fact):**
with credit thin, banks are nearly fully reserved (reserves ≈ deposits), so the queue rarely exhausts reserves ⇒
**liquidity-suspension is LATENT**; the **active** halves are the **flight** (weak banks bleed deposits — ~17k
cumulative over ~90 episodes at NH1000) + the **fear/acceleration** of already-weak banks toward failure (alive 3
vs 6 with runs off). Full liquidity crises await scarce reserves (the bond layer).

### 38.4 Verification & status
`Config.v115()` = v11.4 + all four sub-flags. `test_v115_bank_demographics` **6/6**: each
sub-flag off ⇒ prior bit-identical; A5 + reserve + **share** conservation hold through dividends, trading, entry,
and runs; entry founds banks + sustains the count (off only decays); dividends reach owners (bank-ownership Gini
> 0); runs produce deposit flight. New Bank fields + Ledger reuse; new metrics (`bank_births/deaths`,
`bank_equity_total/gini`, `bank_deposit_flight`, `bank_fear`, `bank_min_price_peak`, `bank_stock_turnover`); new
Config levers `bank_equity(_lambda/_trading)`, `bank_theta_equity`, `bank_dynamics`, `bank_min_capital`,
`bank_entry_beta/_max`, `bank_runs`, `run_sensitivity/_health_ref/_market_weight/_fear_persistence`. Full
**29-suite regression green**. **Deferred: the BOND layer** (activates the interbank market, gridlock, AND runs'
liquidity-suspension) + deposit insurance / resolution funds (temper the now-realistic contagion).

## §39 v12 — the SECURITIES arc: un-consolidate the CB, issue BONDS, sterilise reserves

The keystone tier (PLAN_v12, **hardened over 4 accounting-review rounds**). It un-consolidates the central bank
from the Treasury and finances the deficit with **bonds**, whose purpose is to **sterilise reserves** ⇒ turn them
scarce ⇒ activate the funding-side machinery left LATENT in §37/§38. Built in small stages; v12.0 + v12.1 landed.

### 39.1 The accounting (the review's core corrections)
*Government bonds are NOT a stock-market overlay* — a bond is at once a Treasury liability, a CB asset, a bank
asset, a household asset, and a reserve tool, and the bookings must differ. The load-bearing rules:
- **A bond has THREE values, each used in exactly one identity: FACE** (the bond identity `Σ holdings@face =
  outstanding`), **BOOK/carrying** (the bank-money invariant), **MARKET** (wealth / bank `economic_capital` only).
- **A bank buying a govt bond CREATES money** (like a loan) ⇒ `ΣD − ΣL − Σ(bank-bonds@book) = M₀`; a **household**
  buying is a deposit↔bond swap (money-neutral). *(bank bonds arrive at v12.2.)*
- **MASTER conservation (mix-independent, at book/nominal):** `private NFA (ΣD_priv − ΣL_priv + private bonds) =
  M₀ + cumulative deficit = government total net liability`. The single-number M₀ is a special case.
- **Un-consolidated structure:** `TSY` (fiscal deposit account, replaces GOV) + `CB` (reserves = liability;
  bonds + claim-on-TSY = assets); the **TGA** = the Treasury's account at the CB (the same cash as `D_TSY` seen
  from the reserve side — *not* a second asset). `bonds=False` ⇒ TSY≡GOV ⇒ bit-identical to v11.5.

### 39.2 v12.0 — un-consolidate (a bit-identical refactor)
`GOV` splits into `TSY`+`CB` behind a `_fiscal` account id; the CB balance-sheet scaffolding (TGA, cb_claim, bond
overlay) + the three securities-identity gates run as **no-ops** when there is no issuance. `Config.v12(bond_
finance_frac=0)` is **bit-identical to v11.5** (the fiscal account merely renamed TSY). (No diagnostic — a
bit-identical version's plot carries no new information.)

### 39.3 v12.1 — households hold PAR bills; the corrected finding (an artifact caught via the diagnostic)
The Treasury targets holding `bond_finance_frac` of its debt as **one-period PAR bills** (`face=book=market`,
coupon 0 — no `p/x`/duration yet), issued to / redeemed from households (deposit↔bill swaps whose RTGS leg drains
bank reserves to the CB). All four gates hold every tick (deposit-A5, reserve conservation, bond identity, master
NFA). **A first cut allocated bills pro-rata to ALL household deposits — and the diagnostic caught an ARTIFACT:**
it drained households' *transaction* balances (money share 0.19→0.03), and since B1 consumption is cash-capped on
deposits (bills aren't spendable here), **demand collapsed — u 0.007 → 0.35** as f 0→0.9. That is not economics,
it is the minimal mechanism starving transactions. **FIX:** bills are bought only from households' **IDLE SAVINGS**
(deposits above a transaction buffer ≈ expected income), so transaction balances are preserved ⇒ **no artifact**
(u stays ~0.001–0.02 across all f). **The honest consequence:** household idle savings are a **small pool** (~10%
of the debt), so **household bond-financing — and its sterilisation — is MODEST** (bonds barely rise with f; they
are savings-capped, not f-capped). **The strong reserve drain must come from BANKS** (v12.2): banks hold the
excess reserves (§37) to absorb the *bulk* of the government debt into bonds. So the interbank keystone awaits
**v12.2** (banks buy bonds with reserves ⇒ real drain) **+ v12.4** (OMO drains below M₀). *(The earlier "reserves →
M₀ floor" reading was the artifact version — draining transaction deposits, not real sterilisation.)*
`Config.v12()` = frac 0.9 (a policy target, savings-capped in v12.1); off (or frac=0) ⇒ bit-identical.

**A SECOND artifact caught by the standing diagnostic (→ v12.1-fix, bill ROLLOVER).** Over a *long* run the
idle-savings version still bled: by 4000 ticks u climbed to **~0.25 at f=0.9** (vs ~0.02 at f=0). A f=0-vs-0.9
time-series decomposition pinned the cause — and it was **NOT** bank crowding-out (my first guess): `banks_alive`
dips mid-run but **RECOVERS to ~4.5**, *higher* than f=0's, so the sector is not the late driver. The real cause is
a **freeze RATCHET**: the old single `_phase_debt_management` targeted a STOCK (`0.9·gov_debt`) and only netted the
gap, so once bought, bills **never matured back to deposits**. Idle savings were locked into non-spendable,
zero-coupon bills *permanently*; the `α2·D` wealth term of B1 consumption withered; and — because the sweep buffer
`max(y_expected,·)` shrinks as income falls — a **downward spiral** (bond stock ratcheted to **3.06M**; crucially
`gov_debt` stayed IDENTICAL to f=0, proving the damage was pure private-liquidity *composition*, not any fiscal
difference). **FIX = honour "one-period bill" literally.** Split the phase in two: `_phase_bill_maturity` redeems
EVERY bill to deposits at the **top** of the tick (before planning), so for the whole tick the holder carries pure
deposits — bills now feed consumption, the goods-market live-deposit cap, equity/bank-stock buys, and start-up /
founding capital **with no change to the deposit-only behavioural code**; `_phase_bill_issuance` re-sweeps only the
genuine *end-of-tick* idle, now over a **thicker buffer** `max(2·y_expected, d_household0·price)`. **Result: f=0.9
is bit-identical to f=0 in u, banks_alive, AND gov_debt across all four 1000-tick windows** (the pre-registered
prediction, confirmed) — the "stone" became "cash". This made the once-planned haircut / `_make_cash` liquidity
bridge **unnecessary** (dropped). **New honest consequence:** once bills are intra-tick liquid *and* pay no coupon,
households have no reason to hold them OVERNIGHT, so the bill stock collapses to a thin **residual (~33k, ~0.5% of
debt, vs the frozen 3.06M)** — sterilisation is now minimal. A *meaningful* bond stock (a genuine safe asset + a
real sterilisation lever) needs the **demand** side — coupon income + portfolio choice (`bond_theta`) — which is
**v12.3**; and it will now grow the stock **without re-freezing**, precisely because bills are liquid. *(This
supersedes the earlier "bank-deposit crowding-out" reading of the late-u dip — that channel is real but secondary
and mid-run; the dominant driver was the freeze ratchet, now removed.)*

### 39.4 Verification & status
`test_v12_bonds` 3/3 (bit-identical at frac=0; all four identities hold with bills active; **no demand artifact** —
raising f keeps u low). Bill ROLLOVER phases `_phase_bill_maturity` (top of tick) + `_phase_bill_issuance` (end),
both no-ops at frac=0 (bit-identical preserved). New Config levers `bonds`, `bond_finance_frac`, `bond_coupon`,
`bond_theta`; new ledger scaffolding
(`_fiscal`, TGA, `cb_claim_on_tsy`, `_bond_holdings`, `_bonds_outstanding`) + the securities gate; new metrics
(`bonds_outstanding`, `hh_bond_wealth`, redefined `gov_debt`, corrected `bank_reserves_total`=BANK-side). Full
**regression green (all 30 test scripts)**; pre-registered f=0-vs-0.9 time-series check confirmed (post-rollover u
tracks f=0 bit-for-bit across four windows).

### 39.5 v12.3 — bonds become a REAL asset: maturity + coupon + a household portfolio + the bank balance sheet (SVB)
v12.3 folds in what was v12.2+v12.3 of the plan (PLAN_v12.3.md). Bonds gain **maturity, a coupon, and a market
price**, so the **three values finally diverge**: `_bonds` is now a list of LOTS `{holder, face, cost, matures_at}`;
`price(face,n,r,c) = c·face·Σ(1+r)^−k + face·(1+r)^−n` (a rate HIKE with `n>1` ⇒ `market < face`). Built in gated
sub-steps, every new lever off ⇒ the v12.1-fix economy (`test_v123_off_bit_identical`), `bonds=False` ⇒ v11.5.

**A+B (households, SHIPPED ON).** A per-period **coupon** (`bond_coupon`, a fiscal expense that adds to the
deficit) gives bonds a reason to be held; households target `bond_theta` of wealth in bonds, funded from
post-consumption surplus over a thinner buffer (justified because bonds now pay a coupon, enter the B1 wealth term,
and mature/roll ⇒ **liquid**). **Pre-registered #2 confirmed:** making bonds a real held asset does NOT re-freeze
demand — late u stays at the frac=0 baseline (`test_v123_coupon_theta_conserve_no_refreeze`). Honest scope: the
household stock is inherently surplus-limited (a deliberate ~θ share, not a runaway), so a bond has three tracked
values but households alone can't build a large book — that is intrinsically a BANK phenomenon.

**C — the LEDGER REFACTOR (the hardest accounting in the arc).** A bank cannot buy bonds "with reserves" as a
deposit transfer: its own deposit-capital is ~0 (v11.5 pays profits out as dividends) and reserves are a DERIVED
overlay of the deposit ledger (`R_k = capital+deposits−loans`). So reserves/securities are promoted to first-class:
a new `bank_buy_bond_with_reserves` primitive (reserves drain bank→CB ⇒ **sterilisation**; the Treasury is credited
spendable funds ⇒ **money creation**; `_bank_securities += amount` offsets), the core **A5 gate is redefined to
`ΣD − ΣL − _bank_securities = M`** (=old gate when `_bank_securities=0` ⇒ every existing config bit-identical), the
master-NFA gate subtracts `_bank_securities`, and `bank_redeem_bond` unwinds it at maturity. **All four gates hold
through banks buying/redeeming bonds via money creation (identΔ ≈ 3e-13).** `economic_capital = ledger.balance +
Σ(market − cost)` (unrealised P&L only — the bond is deposit-funded) is wired into the leverage cap, the exposure
limit, and the insolvency trigger.

**D — SVB duration channel (wired + proven; live activation DEFERRED to v12.4).** A rate hike marks a bank's
multi-period bonds below cost ⇒ `economic_capital` thins ⇒ crunch/insolvency — proven in a controlled test
(`test_svb_duration_channel_and_bank_securities_conserve`). **Honest finding (the reason `bank_bond_appetite=0` by
default):** turning the live bank drain ON collapses the sector at ANY positive appetite — banks are **thinly
capitalised in equity** (~tens) but a bond book is thousands, and the CB's Taylor rule swings the policy rate to
5–7% vs a 1% coupon ⇒ enormous MTM losses instantly wipe the tiny equity buffer (**exactly the 2023-SVB structure**),
while draining reserves to scarcity cascades the §37/§38 run/gridlock machinery with no Lender of Last Resort. So
the bank balance sheet + strong drain + SVB are **BUILT and conservation-verified but gated OFF**; their stable
activation needs a **capital floor + LoLR + OMO = v12.4** — precisely the plan's staging. New levers `bond_coupon`,
`bond_theta`, `bond_maturity`, `bank_bond_appetite`; `Config.v123()`. New metrics (`bond_book_total`,
`bond_market_total`, `bond_mtm_pnl`, `bank_bond_face`, `bank_economic_capital_min`, `gov_interest_bill`).
`test_v12_bonds` **6/6**; full **30-suite green**; `diagnostic_v123.png`. **Next: v12.4** — LoLR + a bank capital
floor + OMO/QE, which together let the strong bank drain + SVB run LIVE (and re-latent the interbank market post-QE).

### 39.6 v12.4 — the CB's quantity tools: OMO / QE / LoLR (the interbank keystone finally BINDS; arc closed)
v12.4 (PLAN_v12.4.md) closes the securities arc. The one architectural change: the **reserve total becomes
VARIABLE** — the un-consolidated CB is the source/sink of base money. Two ledger primitives, `issue_reserves(node,x)`
/ `retire_reserves(node,x)`, move `_reserves[node]` AND `_reserve_M` together, so the gate `Σ reserves = _reserve_M`
**stays exact by construction** (=the fixed-total v11.4 gate when nothing is issued ⇒ every prior config
bit-identical); the deposit ledger `ΣD−ΣL−_bank_securities=M` is untouched (reserves are a separate overlay).

**OMO — the headline, CONFIRMED.** `_phase_omo` steers Σ bank reserves toward `omo_reserve_target`·(genesis) by
absorbing them into the CB's own instrument (reverse repo / CB bills — the modern drain, e.g. the Fed's ON RRP),
`retire_reserves` + `_cb_absorbed↑`; QE is the mirror. **Draining reserves scarce makes the §37 interbank market —
latent since v11.4 — finally BIND**: at `target=0.3` the pre-registered signal fired (peak intraday overdraft ≈11k,
`interbank_volume`>0, up from EXACTLY 0), `_reserve_M` correctly fell as base money was destroyed, all four
conservation gates held. QE re-floods ⇒ it re-latents (the post-2008 story). This is the keystone the whole arc was
built to reach.

**LoLR + the SVB floor.** In `_phase_bank_runs`, an illiquid-but-**solvent** bank (economic_capital > 0) is funded
by the CB (`issue_reserves`, `_lolr_advances`) instead of suspending — liquidity ≠ solvency, so an INSOLVENT bank
(SVB MTM wipe-out) still fails, but **alone**, not by dragging the sector into a liquidity cascade. A duration limit
caps each bank's bond book at `k·economic_capital` so a rate hike can't wipe it.

**THE BANK BLEED and its fix (user-driven).** A user flagged that the diagnostic showed `banks_alive→0`. Diagnosis
(ablation + a founder-pool trace): NOT the coupon/theta/OMO levers per se (at NH1000/2500t all configs keep 5–8
banks) but a **scale × horizon** failure of the v11.5 demographics — de-novo ENTRY was structurally DEAD (roe/r ≈
10× so the profit hurdle was fine, but `eligible_founders = 0`: at NH2000, with `bond_theta` draining deposits,
**no household clears `bank_min_capital=1500` in ANY wealth form** — deposits, +bonds, or full NW). With births ≈ 0
and a steady death rate, the count bleeds to 0 over 4000 ticks. **The fix is BOTH sides:** thicker capital
(`bank_target_capital_ratio` 0.1→**0.18**, `bank_exposure_limit` 0.25→**0.15** ⇒ fewer deaths) **and** a founder
gate the wealth distribution can clear (`bank_min_capital` 1500→**400** ⇒ births resume; 800 was still too high,
150 over-churns — the 116/108 problem). At NH2000/4000t this holds the count at **~11 (births≈deaths, low churn)**,
not 0. (A reserve-tolerance bug OMO exposed was also fixed: `assert_reserves_conserved` keyed its tolerance off the
*current* `_reserve_M`, which OMO drains small, tripping on normal float error — now keyed off the stable deposit
base money.) **Deferred (the deeper structural gap the user identified):** de-novo entry is still too
single-household-cash — it should allow **joint founding / bank IPO / bridge banks on resolution / recapitalisation
/ an indexed `bank_min_capital`**; the founder-liquidity path (`_redeem_hh_bonds`, count bonds@market toward
eligibility) is in place but insufficient alone.

`Config.v124()` is now the **HEALTHY** default (gentle OMO `target=1.0`/`drain=0.03` + a light short bank book
`appetite=0.03`/`duration_limit=0.5`/`maturity=4`); `Config.v124_stress()` is the interbank-activation STRESS test
(`target=0.3`, heavy long book — deliberately exhibits overdrafts + SVB failures). **Honest scope:** the clean
verified win is **OMO→interbank activation** + the conservation-safe CB balance sheet; the real economy is
fiscally insulated throughout (JG + deficit hold u≈0.01–0.05 across all bank outcomes). New levers `omo`/
`omo_reserve_target`/`omo_drain_frac`/`lolr`/`bank_bond_duration_limit`; new metrics (`cb_absorbed`, `omo_flow`,
`lolr_advances`, `reserve_M`); `test_v12_bonds` **9/9** (reserve create/destroy conservation, LoLR funds-a-solvent-
bank, off⇒bit-identical); full **30-suite green**; `diagnostic_v123/v124.png`. **The securities arc (v12.0–v12.4)
is CLOSED.** Next major direction (§0-ii health lever, not more plumbing): **v13 — a search-and-matching LABOUR
layer** (an endogenous natural rate ⇒ T4).

---

## Change log

| Version | Date | Change |
| 2.23 | 2026-07-07 | **v12.4 — the CB's quantity tools: OMO / QE / LoLR; the interbank keystone finally BINDS; securities arc CLOSED (§39.6).** One architectural change: the **reserve total becomes VARIABLE** — the un-consolidated CB is the source/sink of base money. Two ledger primitives `issue_reserves`/`retire_reserves` move `_reserves[node]` AND `_reserve_M` together ⇒ the gate `Σreserves=_reserve_M` **stays exact by construction** (=the v11.4 fixed-total gate when nothing is issued ⇒ **every prior config bit-identical**); the deposit ledger `ΣD−ΣL−_bank_securities=M` is untouched. **OMO (the headline, CONFIRMED):** `_phase_omo` absorbs reserves into the CB's own instrument (reverse repo / CB bills — the modern drain) toward `omo_reserve_target`·genesis; **draining reserves scarce makes the §37 interbank market — LATENT since v11.4 — finally BIND** (peak intraday overdraft ≈11k, `interbank_volume`>0, up from EXACTLY 0; `_reserve_M` falls as base money is destroyed; all four gates hold). QE re-floods ⇒ re-latents (post-2008). **LoLR:** an illiquid-but-**solvent** bank in a run is funded by the CB (`issue_reserves`, `_lolr_advances`) instead of suspending — liquidity≠solvency, so an insolvent (SVB) bank still fails but ALONE, no liquidity cascade; a duration limit caps each bank's bond book at k·economic_capital. `Config.v124()`. **Honest scope:** the clean verified win is **OMO→interbank activation** + the conservation-safe CB balance sheet; the bank sector's baseline fragility is a v11.5 property (thin equity) largely orthogonal to the real economy (JG+deficit hold u≈0.01–0.02 even at banks_alive→0), so durable large-bank-bond survival needs banks to RETAIN equity (a v11.5 recalibration, a separate lever). New levers `omo`/`omo_reserve_target`/`omo_drain_frac`/`lolr`/`bank_bond_duration_limit`; new metrics (`cb_absorbed`, `omo_flow`, `lolr_advances`, `reserve_M`); `test_v12_bonds` **9/9** (incl. reserve create/destroy conservation, LoLR-funds-solvent-bank, off⇒bit-identical); full **30-suite green**; `diagnostic_v124.png`. **Securities arc (v12.0–v12.4) CLOSED.** Next (health lever, not plumbing): **v13 search-matching LABOUR** (natural rate ⇒ T4). |
| 2.22 | 2026-07-07 | **v12.3 — bonds become a REAL asset: maturity + coupon + a household portfolio + the bank balance sheet / SVB (§39.5).** Bonds gain **maturity, a coupon, and a market price**, so the **three values diverge** (`_bonds` = lots `{holder,face,cost,matures_at}`; `price=PV(face,n,r,c)`, rate hike + `n>1` ⇒ `market<face`). **A+B (SHIPPED ON):** a per-period **coupon** (fiscal expense) + a household `bond_theta` portfolio funded from post-consumption surplus; bonds enter the B1 wealth term and mature/roll ⇒ **liquid** ⇒ **pre-registered #2 confirmed: no re-freeze** (late u = frac=0 baseline). Honest scope: the household stock is surplus-limited (a deliberate ~θ share) — a large book is intrinsically a BANK phenomenon. **C — the LEDGER REFACTOR (hardest accounting in the arc):** banks have ~0 deposit-capital and reserves are a derived overlay, so reserves/securities are promoted to first-class — new `bank_buy_bond_with_reserves` (reserves drain bank→CB = sterilisation; Treasury credited = money creation; `_bank_securities` offsets) + `bank_redeem_bond`; the **core A5 gate is redefined to `ΣD−ΣL−_bank_securities=M`** (=old gate when 0 ⇒ every existing config **bit-identical**), the master-NFA gate subtracts `_bank_securities`, and `economic_capital = balance + Σ(market−cost)` feeds the leverage cap / exposure limit / insolvency. **All four gates hold through banks buying/redeeming via money creation (identΔ≈3e-13).** **D — SVB duration channel** (rate hike → MTM loss → economic_capital thins → failure) is **wired + proven in a controlled test**. **HONEST FINDING (⇒ `bank_bond_appetite=0` default):** the live bank drain collapses the sector at ANY positive appetite — banks are **thinly capitalised** (equity ~tens vs a bond book of thousands) and the CB rate swings to **5–7% vs a 1% coupon** ⇒ enormous MTM losses wipe the tiny buffer (**the 2023-SVB structure**), while draining reserves to scarcity cascades the §37/§38 run/gridlock machinery with **no LoLR**. So the bank balance sheet + strong drain + SVB are **built & conservation-verified but gated off**; stable activation needs a **capital floor + LoLR + OMO = v12.4** (the plan's staging). New levers `bond_coupon`/`bond_theta`/`bond_maturity`/`bank_bond_appetite`, `Config.v123()`; new metrics (three values, `bank_bond_face`, `bank_economic_capital_min`, `gov_interest_bill`); `test_v12_bonds` **6/6** (incl. the SVB duration test + coupon/theta no-refreeze + off⇒bit-identical); full **30-suite green**; `diagnostic_v123.png`. |
| 2.21 | 2026-07-07 | **v12.1-fix — bill ROLLOVER: bonds stop being a "stone", become a safe LIQUID asset (§39.3).** A user asked why the v12 diagnostic's late-sample u spiked *higher* than before. A f=0-vs-0.9 time-series decomposition refuted my earlier "bank-deposit crowding-out" reading (`banks_alive` dips mid-run but RECOVERS to ~4.5) and pinned a **freeze RATCHET**: the single `_phase_debt_management` targeted a STOCK and only netted the gap, so once bought, one-period bills **never matured** → idle savings locked into non-spendable zero-coupon bills → the `α2·D` consumption term withered → downward spiral (**u→0.25, bonds→3.06M** at f=0.9/4000t, while `gov_debt` stayed IDENTICAL to f=0 ⇒ pure private-liquidity *composition*, not fiscal). **FIX (honour "one-period bill" literally):** split into `_phase_bill_maturity` — redeem EVERY bill to deposits at the **top** of the tick (bills liquid all tick ⇒ feed consumption / goods-market cap / equity+bank-stock buys / founding capital with **no change to the deposit-only behavioural code**) — and `_phase_bill_issuance` — re-sweep only genuine **end-of-tick idle** over a **thicker buffer** `max(2·y_expected, d_household0·price)`. **Pre-registered prediction, confirmed:** f=0.9 is now **bit-identical to f=0** in u / banks_alive / gov_debt across all four 1000-tick windows (**u 0.019, not 0.25**); the once-planned haircut / `_make_cash` liquidity bridge is **unnecessary, dropped**. **New honest consequence:** intra-tick-liquid + zero-coupon ⇒ no reason to hold OVERNIGHT ⇒ bill stock collapses to a thin **residual (~33k, ~0.5% of debt, vs the frozen 3.06M)** ⇒ sterilisation minimal; a *meaningful* bond stock needs the **demand** side (coupon income + portfolio choice `bond_theta`) = **v12.3**, which will now grow it **without re-freezing** because bills are liquid. Both phases no-op at frac=0 ⇒ bit-identical preserved. `test_v12_bonds` **3/3**; full **regression green (30 scripts)**; `diagnostic_v12.png` re-rendered. |
|---|---|---|
| 2.20 | 2026-07-07 | **v12 — the SECURITIES arc (v12.0–v12.1): un-consolidate the CB, issue BONDS, sterilise reserves (§39).** The keystone tier, its accounting **hardened over 4 review rounds**. **Core rules:** a bond has THREE values — **face** (bond identity `Σ holdings@face=outstanding`), **book** (bank-money invariant), **market** (wealth/economic_capital); a **bank** buying a govt bond CREATES money (`ΣD−ΣL−Σbank-bonds@book=M₀`), a **household** buying is a deposit↔bond swap; the **MASTER conservation** (mix-independent, at book) is `private NFA = M₀ + cumulative deficit = govt total net liability`; the CB is un-consolidated into **TSY** (fiscal deposit acct) + **CB** (reserves=liability, bonds+TSY-claim=assets) with a **TGA** (the Treasury's cash at the CB — the SAME cash as `D_TSY` seen from the reserve side, never a 2nd asset). **v12.0** splits `GOV`→`TSY`+`CB` behind a `_fiscal` id + inert CB scaffolding + the securities-identity gates as no-ops ⇒ **bit-identical to v11.5** (no diagnostic — a bit-identical version's plot adds nothing). **v12.1** has the Treasury hold `bond_finance_frac` of its debt as **one-period PAR bills** (face=book=market, coupon 0) issued to/redeemed from households (deposit↔bill swaps that drain bank reserves to the CB); all four gates hold every tick. **THE FINDING (an ARTIFACT caught via the diagnostic, then corrected):** a first cut allocated bills pro-rata to ALL deposits ⇒ it drained households' TRANSACTION balances (money share 0.19→0.03) and, since B1 consumption is cash-capped on deposits, **collapsed demand (u 0.007→0.35)** — not economics, the minimal mechanism starving transactions. FIX: buy bills only from households' **IDLE SAVINGS** (deposits above a transaction buffer) ⇒ **no artifact** (u stays ~0.001–0.02 across f). **Honest consequence:** household idle savings are a SMALL pool (~10% of debt), so household bond-financing + its sterilisation is **MODEST** (bonds are savings-capped, not f-capped). **The strong reserve drain must come from BANKS (v12.2)** — they hold the excess reserves (§37) to absorb the bulk of the debt into bonds; the interbank keystone awaits v12.2 + v12.4 (OMO). `Config.v12()` = frac 0.9 (a policy target, savings-capped in v12.1); off (or frac=0) ⇒ bit-identical. New levers `bonds`, `bond_finance_frac`, `bond_coupon`, `bond_theta`; new metrics (`bonds_outstanding`, `hh_bond_wealth`, redefined `gov_debt`, corrected `bank_reserves_total`=BANK-side); `test_v12_bonds` 3/3; full **31-suite regression green**. **Next:** v12.2 bank balance sheet (money creation, economic_capital) → v12.3 traded market + duration/SVB → v12.4 OMO/QE (activates interbank) + LoLR. |
| 2.19 | 2026-07-06 | **v11.5 — bank DEMOGRAPHICS & OWNERSHIP: entry, equity + a bank-stock market, and runs (§38).** Fixes a gap a user spotted: banks only ever DIED (insolvency → migrate to survivors), never BORN, so the count decayed to oligopoly. v11.5 gives banks the firm-style **entry/exit + ownership** structure. **A — equity + a full v6-style secondary bank-stock market:** banks are OWNED (genesis banks vest in a founder class); **profit → shareholder DIVIDENDS** (not depositors); a tradeable market where households target `bank_theta_equity` of wealth, prices GROPE on excess demand with a chartist bubble/crash term, trades pro-rata rationed so **shares AND money conserve** (drift ~1e-14). Bank equity enters household wealth; failure wipes owners. **Flagged finding:** redirecting bank income depositors→OWNERS makes bank profit a **wealth-concentration channel** and, draining broad demand, *raises* failures (~2→4). Prices trade 0.7–1.0× peak (distress signals); founder ownership **deconcentrates** to the population via trading. **B — de-novo ENTRY (profit-driven):** when bank ROE beats the policy-rate hurdle a household with ≥`bank_min_capital` FOUNDS a bank (A5-safe; reserves follow) and owns it 100%, undercutting to break in; a **congestion** term keeps chartering rare + self-limiting. **CALIBRATION (a user caught it):** a low capital gate (200) made thin entrants fail fast → an unrealistic **near-total turnover** (116 births/108 deaths over 4000 ticks, banks churning like FIRMS). A sweep showed `bank_min_capital` is the dominant (founder-wealth-gated) lever; anchoring it **HIGH (1500, ~2× a genesis bank's capital)** makes entrants WELL-CAPITALISED ⇒ they SURVIVE, cutting churn **~12×** to a realistic **~9 births/~11 deaths, count stable ~6** (long-lived banks, rare entry, few failures). **C — bank RUNS:** depositors flee low-HEALTH banks (blend of share price/peak + capital ratio), amplified by a system FEAR level; a run executes as a **QUEUE** served from the bank's OWN reserves (loans illiquid; **interbank FROZEN**), SUSPENDING (illiquidity failure) when reserves exhaust. **Honest scope:** thin credit ⇒ banks nearly fully reserved ⇒ **liquidity-suspension LATENT**; the ACTIVE halves are **flight** (~17k cumulative deposits fleeing weak banks) + **fear/acceleration** of weak-bank death (alive 3 vs 6). `Config.v115()`; each sub-flag off ⇒ bit-identical. New metrics (`bank_births/deaths`, `bank_equity_total/gini`, `bank_deposit_flight`, `bank_fear`, `bank_min_price_peak`); new levers `bank_equity(_lambda/_trading)`, `bank_theta_equity`, `bank_dynamics`, `bank_min_capital`, `bank_entry_beta/_max`, `bank_runs`, `run_sensitivity/_health_ref/_market_weight/_fear_persistence`. `test_v115_bank_demographics` **6/6**; full **29-suite regression green**; A5 + reserve + share conservation all hold. **Deferred: the BOND layer** (activates interbank + gridlock + runs' liquidity-suspension) + deposit insurance / resolution funds. |
| 2.18 | 2026-07-06 | **v11.4 — the RESERVE tier + intra-tick RTGS + interbank market: correct, and a diagnosis of why it's LATENT (§37).** The 枢纽: since v3 deposits were a single global pool, blocking the whole funding side (interbank 拆借, runs, deposit competition). v11.4 **partitions deposits** and adds a **reserve tier** with **full intra-tick RTGS settlement** (the user's explicit choice), an **interbank money market** (endogenous tightness-driven rate + contagion cascade), and **deposit-side competition**. **Architecture:** a reserve **OVERLAY** — the deposit ledger + A5 gate are untouched; since every payment funnels through `Ledger.transfer`, reserve settlement is hooked **there** (one method, zero call-site edits): a payment settles reserves between the payer's & payee's banks (GOV→the CB, the base-money source/sink). **Two hard-gated conservation laws:** deposit-A5 (unchanged) + reserve conservation (Σ=M₀). **Proven+verified identity:** end-of-tick RTGS-settled reserves = the balance-sheet `R_k=capital+deposits−loans` **exactly** (drift 7e-8) ⇒ net-settlement and full RTGS give the *same* tick-level positions; RTGS only adds intra-tick granularity (reserve backing follows every relationship switch via `move_reserves`). **THE FINDING (reported, not tuned):** the interbank market / intraday funding / gridlock are **CORRECT but LATENT** — **peak intraday overdraft is EXACTLY 0** in every regime (default/low/zero deficit), no bank ever runs reserve-short. Why (measured): credit is only **3.4% of broad money** (money multiplier D/M₀ = **1.03** vs a real 5–10), so nearly all money is **base money** held as reserves; each bank's reserve buffer is **~20× its own per-tick payment flow**; and the **unsterilised deficit** floods more reserves in (Σ reserves = M₀ − GOV, ever-growing). This is the **ample-reserves regime**, extreme from **thin credit + no bond sterilisation** — the funding-liquidity complex (interbank, gridlock, and the funding *motive* for deposit competition) is latent, activating only under **scarce reserves** (a future **bond layer** sterilising the deficit — its true purpose, revealed here — or much thicker credit). **Deposit-side competition ALSO lacks a genuine driver here and DEGENERATES** (a third face of the same root: no funding scarcity ⇒ no equilibrating force): forced on, depositors all pile into the top-rate bank (deposit-**HHI → ~1.0**, monopoly + 7–8/8 sector collapse) regardless of a congestion term ⇒ it ships **OFF** (`deposit_rate_disp=0`). The clean deliverable is the correct, conserving reserve/RTGS/interbank **infrastructure**, not an active funding-side phenomenon (which this economy's structure can't yet support). `Config.v114()` = v11.3 + `interbank=True`; off (or `n_banks=1`) ⇒ bit-identical. New Ledger primitives (`enable_reserves`, `move_reserves`, `reset_intraday`, `assert_reserves_conserved`); new metrics (`bank_reserves_total`, `cb_reserves`, `interbank_rate/volume`, `peak_intraday_overdraft`, `payments_gridlocked`, `bank_deposit_hhi`); new Config levers `interbank`, `interbank_rate_base`, `interbank_tightness`, `reserve_floor_frac`, `deposit_rate_disp`, `deposit_search_m`. `test_v114_interbank` **7/7**; full **28-suite regression green**; both conservation laws hold. **Deferred (now well-motivated): a BOND/securities layer** (sterilise reserves ⇒ activate interbank + gridlock; hands the CB OMO/QE) + **bank runs**. |
| 2.17 | 2026-07-06 | **v11.3 — loan-rate COMPETITION: market share won on price, and emergent too-big-to-fail (§36).** The banking-layer realism arc (the user's "竞争" list). v11.2 banks are realistic in *capital* but **static in market structure** — a borrower is assigned a bank at genesis and every bank charges the same rate. v11.3 makes banks **compete on price** and borrowers **shop**: each bank draws a **mean-preserving** loan-rate spread over the policy rate (`bank_spread_disp`; de-meaned to sum 0 ⇒ the *average* cost of credit is unchanged, isolating the sorting mechanism, §0-ii), the rate a borrower pays = `policy_rate + its bank's spread` (wired into debt service), and when a borrower seeks new credit it **samples `bank_search_m` rivals and switches its whole relationship to the cheapest bank with capacity to fund it** (`_shop_bank`; incumbent always eligible; the switch moves existing debt between loan books, A5-neutral, same primitive as failure-migration). So **cheap, well-capitalized banks WIN market share** — but a cheap bank fills its leverage capacity and spills the marginal borrower onward, so it grows without a trivial monopoly. **Result (8 seeds, `Config.v112` vs `Config.v113`, emergent — reported not tuned):** competition **concentrates the sector** (loan-book Gini 0.33→**0.50**, HHI 0.19→**0.27** vs the 0.125 even-split floor), a real **rate dispersion** emerges (SD 0→0.0025), and bank **failures roughly DOUBLE** (1.5→**3.1** of 8) — the classic **competition → concentration → too-big-to-fail** channel (bigger banks carry bigger books ⇒ each failure takes more with it). **Yet the real economy is INSULATED** (u stays 0, output +0.5%): the fiscal deficit + JG hold demand at full employment, so failures *reallocate* credit among survivors rather than *drain* demand (the §35.5 hoard-drain is already gone) — a genuine exogenous shock (deferred) is what would turn this latent fragility into a recession, the realistic ordering. `Config.v113()` = v11.2 + `bank_rate_competition=True`, `bank_spread_disp=0.003` (~⅓ the policy rate), `bank_search_m=2`; off (or `n_banks=1`) ⇒ bit-identical. New metrics `bank_loanbook_hhi`, `bank_rate_spread_sd`; new Config levers `bank_rate_competition`, `bank_spread_disp`, `bank_search_m`. `test_v113_competition` **6/6**; full **27-suite regression green**; A5 holds. **Deferred (§35.4):** the deposit-partitioning + reserve tier that unlocks **interbank lending (拆借), bank runs, deposit-side competition** — the next big banking-realism step. |
| 2.16 | 2026-07-06 | **v11 — MULTI-BANK: a realistic "loan-book banks" system (stable; a latent failure machinery) (§35).** The single unfailable bank becomes `n_banks` accounts, each with its own capital, loan book, and heterogeneous leverage cap κ_bank. **Deposits stay a single global pool** (no interbank settlement, no reserve tier ⇒ A5 barely touched); only the **loan book** is partitioned. **The trick:** a bank's capital *is its own deposit balance* (reuses `write_off`), so with N accounts each buffer is finite. **FRAMING (corrected — kept honestly):** the goal is a **REALISTIC banking system, not a crisis demo** — real banks are well-capitalized and rarely fail. Banks **retain ρ of interest** → build adequate capital → are **STABLE** under normal conditions: `Config.v11()` = **0 failures**, healthy output, **§4 = 6/8** (T7 recovers ⇒ frontier preserved). The leverage cap + failure machinery are built and **CORRECT** (under a deliberately EXTREME-stress config banks *do* fail — ~26/40 — and **A5 holds through every failure**) but **LATENT** — they await a genuine future exogenous shock, not a fragile calibration. **Corrected course:** the first build optimised for *producing crises* via a "thin-bank" payout (capital = bare-minimum loan_book/κ), which left every bank one bad tick from insolvency ⇒ **chronic collapse** (3–8/8 failing, §4→5/8, T7 broken) — anti-realistic; reverted to ρ-retention. **General lesson: model the mechanism realistically; don't tune a module to manufacture a phenomenon.** `Config.v11()` = v10.2 + `n_banks=8`, heterogeneous κ; new Config levers `n_banks`, `bank_leverage_mean/disp`, `bank_assignment`, `bank_capital_constraint`, `bank_migrate_on_failure`. `n_banks=1` **OR** `bank_capital_constraint=False` ⇒ **v10.2 bit-identical** (26-suite regression green; A5 holds THROUGH failures); `test_v11_banks` (5/5). **Deferred** (PLAN_v11 §8): an **exogenous-shock lever** (to actually stress the banks); by-size assignment → too-big-to-fail; deposit insurance; and — needing the reserve tier (doubtful value here, §33) — interbank / bank runs, reserves / LoLR / OMO / QE. **v11.2 (§35.5) — realistic bank capital + a natural-rate insight** (`Config.v112()`, the realistic-banking frontier): ρ-retention was UN-realistic (banks hoard ~2× broad money in idle deposits). Two real Basel institutions replace it — a **CAPITAL RATIO** (`bank_target_capital_ratio=0.1`: pay out above 0.1·loans ⇒ thin, bounded, leverage ~10) + a **LARGE-EXPOSURE limit** (`bank_exposure_limit=0.25`: single borrower ≤ 0.25·capital ⇒ diversified). Params anchored to reality (§0-ii); emergent **~1.7/8 failures** (reported, NOT tuned), in **waves that amplify recessions** through the real economy (corr(u, banks-alive) ≈ −0.26; u spikes to ~0.6). **Two findings:** (1) **v11's "realistic 5% u" was an artefact** — the idle hoard *drained demand*; isolating the levers, it is the **payout** (not the exposure limit, not the JG) that recirculates it (+38% consumption) ⇒ u→~0.01. (2) **The model has NO NATURAL RATE — the labour market is FRICTIONLESS** (`_phase2_labor` matches instantly): it has cyclical/demand-deficient unemployment but NOT frictional/structural, so **u≈0 at full demand is CORRECT** for a frictionless economy; the ~5% real natural rate needs a **search-matching LABOUR layer (deferred v12)**. **§4 = 4/8** on v11.2 (T7: capital-constrained credit; T4: no natural-rate floor) — honest (§0-ii). New levers `bank_target_capital_ratio`, `bank_exposure_limit`; `test_v11_banks` **7/7**; off ⇒ v11 bit-identical. |
| 2.15 | 2026-07-06 | **v10.2 — a PROGRESSIVE wealth tax: the threshold that stops taxing the poor (§34).** The v9 wealth tax was **flat** — `τ_w` on *all* positive net worth, including zero/low-net-worth hand-to-mouth households (real wealth taxes all carry a large exemption; ours didn't). In a demand-constrained economy that **destroys the poor's consumption** — progressive-by-name, regressive in effect. v10.2 adds **`wealth_allowance`** (exemption = `wealth_allowance · mean positive NW`; only wealth above it is taxed); `=0` ⇒ flat ⇒ **bit-identical**. **Decisively pro-poor (v10.1 base, 4 seeds, same rate 0.002):** bottom-decile C **+9%** (0.562→0.614), income poverty **~halved** (0.180→0.086), unemployment **0.083→0.057**, wealth Gini **0.762→0.714** (concentration cut MORE) — for **half the revenue** (only the rich now pay). Mechanism: the flat tax was **demand-destroying at the bottom** (taxing cash-poor small savers → less spending → higher u); the threshold spares them. Tiny cost: slightly lower output + marginally higher inflation. **This corrects an earlier over-attribution** — the demand-drain investigation's "a stronger wealth tax hurts welfare" was largely the **flat structure** taxing the poor, not the wealth tax itself; with a threshold it is a genuinely pro-poor tool that drains the idle hoard + cuts concentration without collateral damage. (Still does NOT "come alive": can't lower inflation at constant employment or substitute for the deficit's net outside money — supply-side/fiscal questions.) `Config.v102()` = v10.1 + `wealth_allowance=1.0`; a **strict welfare improvement** to the frontier. `wealth_allowance` is a **Policy** lever (live tax-progressivity dial); rate stays the anchored 0.002. `test_v102_progressive_wealth` (4/4); off ⇒ v10.1 bit-identical; full regression green. |
| 2.14 | 2026-07-06 | **v10 + v10.1 — the CENTRAL BANK (endogenous policy rate), and why monetary policy is DEFANGED here (§33).** **v10:** `r_interest` becomes a per-tick **policy rate** via a Taylor rule `r = clip(ρ·r₋₁ + (1-ρ)·[r* + φπ(π̄−π*) − φu(u−u*)], 0, r_max)`. The transmission (entry hurdle `return−r`, equity valuation `book+ema(π−r·book)/r`, debt service `r·debt`) was **already wired to `r_interest`**, so this only makes the rate move — no new money ⇒ **A5 trivial**; `central_bank=False` ⇒ **bit-identical**. **Rate-only bank** (bonds/OMO/reserves/QE deferred to v11 — need a securities layer, PLAN_v10 §9). **Diagnosis:** validation looked *perverse* (higher r → higher output), but the relation is **HUMP-shaped** (clean v8.5: output peaks r≈0.02, contractionary both sides). The low-branch perversion traced to a **v3-bank defect** — the bank split collected interest **EQUALLY across all households**, paying even zero-deposit hand-to-mouth ones (MPC 0.8, spent in full), over-strengthening the interest-income demand channel. **v10.1:** pay interest **BY DEPOSITS** (∝ D_h; `interest_by_deposits`, off ⇒ bit-identical) — the correct recipient. On **v8.5 this RESTORES conventional monotone-contractionary transmission** (r 0.005→0.05: output 1715→1176, u 0.25→0.47). **But on the full v9.3 stack the CB is DOUBLY DEFANGED:** (1) **fiscal dominance** — inflation is deficit-driven (zero deficit ⇒ ~0 inflation but u→0.48; any deficit ⇒ ~0.012, *flat*), the rate can't reach it; (2) **the JG absorbs monetary contraction** (a hike raises u **3× more** with the JG off). So a conventional Taylor rule **cannot** work here — a genuine macro result (fiscal dominance + employer-of-last-resort), not a bug. **Tuning study (battery, 4 seeds, means + volatility):** the naive low target (0.001 ≪ structural 0.012) **over-tightens permanently** (worst on nearly everything); the adopted default is **'gentle'** (target≈structural 0.012, φπ1.2, φu1.0) — the **only** stance beating no-CB on inflation **level (0.0103) + volatility (0.150) + aggregate welfare (welfLog −0.158)** simultaneously. The CB's real job under fiscal dominance is **stabilization, not domination**. **Honest cost:** gentle's disinflation is **regressive** — higher u (0.083) and a lower bottom decile (0.562 vs 0.598), the sacrifice on the poor (the §31 employment channel). `Config.v10()` = gentle CB; `Config.v101()` = +deposit-prop. New `test_v10_central_bank` (5/5), `test_v101_deposit_interest` (4/4); `central_bank=False & interest_by_deposits=False` ⇒ **v9.3 bit-identical**; full **24-suite regression green**. New levers: `central_bank`, `inflation_target`, `taylor_phi_pi/phi_u`, `rate_inertia` (Policy — live CB control surface), `r_neutral`, `u_natural`, `infl_ema_lambda`, `r_max`, `interest_by_deposits` (Config — structural). **Standing lesson:** a monetary-financed deficit + a job guarantee make the economy self-stabilize FISCALLY, leaving monetary policy a stabilization role at a regressive cost. |
| 2.13 | 2026-07-06 | **v9.3 — LABOR welfare: the JOB GUARANTEE, a state-dependent employment instrument (§32).** After the private labour market clears, the government hires every household's residual (unemployed) labour at a transitional JG wage, **UNCAPPED** (a buffer stock). Paid as **outside money** (GOV→household, reusing the benefit flow ⇒ A5 holds), **replaces the dole** for takers, and the public-works labour **builds public capital** (reuses the v9.1 K_pub channel). Deficit swings **on-top** of the discretionary target (an automatic stabilizer; §29.4 showed within-target carving collapses demand). It touches only **household** state ⇒ the firm-side `unemployment_rate` (T4) is untouched; added `effective_unemployment` + `jg_employment`. **Effect scales with SLACK (battery NC=200/NK=100/NH=2000, 4 seeds):** on demand-starved **v9 (u=0.27) it is decisive** — buffer = **14%** of labour, clears effective u to ≈0, and **reflates via a demand multiplier** (JG wages → consumption → private hiring, u 0.27→**0.14**): real output **+26%**, bottom-decile consumption **+35%**, log-welfare −0.75→−0.53, Sen +0.10, Gini −0.03. On near-full-employment **v9.1 (u=0.04) it is nearly dormant** (buffer 2.3%) — a small strict improvement on **every** welfare metric ⇒ **`Config.v93()` = the new welfare frontier**. **Cost:** +2.8pp deficit/GDP (self-shrinking) + ~mild inflation. **Honest blemish:** on v9+JG relative **income** poverty ROSE (0.131→0.159) even as consumption welfare rose — the low JG wage (0.5× mean) lifts people only partway (consumption measures, the truer read, all improved). **`min_wage` now WIRED** — a real statutory floor in `plan_wage` that binds immediately, bypassing Calvo (§31.4 fixed the no-op) — but left **OFF** by default (disemployment cuts the same channel; kept as a separate lever). **UBI skipped** (least-targeted). Also renamed `v96`→`v92` earlier this round is unrelated. New `test_v93_labor` (5/5); `job_guarantee=False & min_wage=0` ⇒ **v9.2 bit-identical**; full 22-suite regression green. **§4 not re-scored on v9.3** (scorecard tests structure, not welfare — the natural next check). New Config levers: `job_guarantee`, `jg_wage_ratio` (Policy — live control surface), `jg_productivity` (Config — technological). |
| 2.12 | 2026-07-06 | **Documentation catch-up + clean renumber (§30, §31); no new model layer.** **(1) Renumber v9.6→v9.2** (startup indexation): `Config.v96`→`Config.v92`, comments relabeled, no external callers — so the v9.x line is chronological (v9.1 supply, v9.2 indexed startup, v9.3 next = labor). **(2) §30 money (NON-)neutrality.** A user challenge (neutrality ⇒ inflation harmless) was tested and **refuted**: flexing a purely nominal knob — Calvo `theta_price` 0.10→0.60 — lifts real output 2065→2859 (+38%) and clears the labor market (u 0.264→0.036). **The real inflation cost is sticky-price MISALLOCATION**, a nominal friction whose instrument is the v10 central bank; this retracts my earlier too-quick "inflation is probably harmless." **v9.2** isolates & removes one of the four rigidities (DNWR, Calvo, fixed loan rate, fixed-nominal startup) — the startup endowment is now **price-indexed ⇒ real-invariant entry** (`index_startup`; `False`⇒bit-identical; correctness fix, not a policy lever, not tuned §0-ii). Result: **NULL on firm concentration** (Gini 0.98→0.97, Pareto −2.59→−2.65). The startup artifact was NOT the T6 driver; **concentration is a deep Gibrat/preferential-attachment property, unpinned after ~7 refuted hypotheses** — kept as a first-class open question. `Config.v92()`; govt off ⇒ v8.5 8/8. **(3) §31 distributional welfare metrics** (added to `metrics.py`, pure observation, **bit-identical**): relative poverty rate, FGT poverty gap, bottom-decile real consumption (Rawlsian), log/CRRA social welfare, Sen welfare, income-poverty rate, consumption-floor share. Re-reading the government arc through the bottom tail (5 seeds): **v9 was REGRESSIVE** — its damage fell hardest on the poor (bottom-decile real C 0.535→0.312, −42%; Sen 0.76→0.46); **v9.1 is PRO-POOR** — income poverty **halved** (0.143→0.058), bottom-decile C highest of all three. **Mechanism: welfare at the bottom is an EMPLOYMENT story** — whatever moves u moves the bottom decile (the poor are largely the unemployed). **Discovery: `min_wage` was a NO-OP flag** (present in Config, never read in `plan_wage`). Sets up **v9.3 labor welfare** (wire the wage floor, add an uncapped job guarantee; UBI skipped as least-targeted). |
| 2.11 | 2026-07-05 | **v9.1 — the SUPPLY SIDE: government investment → public capital → productivity, VALIDATED (§29).** Government investment buys real capital goods from the K-sector (cheapest tender), building an economy-wide public capital stock `K_pub` that raises every C-firm's productivity, Barro-style: `Y_f = A·K_f^α·N_f^{1-α}·(1+K_pub/K_ref)^γ`. K_pub is a REAL stock (A5 untouched); `gov_investment_share=0` or `γ=0` ⇒ bit-identical. **Confirms §28.8 and FLIPS the government net-negative→net-POSITIVE:** real output +37%, real consumption +38%, u 0.30→0.06 vs v9 (and above v8.5). The government that BUILDS is net-positive, as in reality. **§0-ii/§0-iv honesty:** default uses STRONG params (g_I=0.10, γ=0.3) ~2–3× the empirical anchors (public-inv/GDP ~4%, elasticity ~0.1); at anchored strength the boost is ~3% — too weak to flip it in this model. Mechanism validated, direction certain, but needs above-empirical elasticity. **Failed honestly:** the composition shift (fund investment WITHIN the deficit) collapsed the economy (carving it out zeroed gov consumption = the C-sector demand floor; the small K-sector bottlenecks large investment) — reverted to on-top (adds to the deficit → the nominal-inflation cost). No free lunch. §4 = 6/8 (structure, not welfare; T6 slope `nan` = a measurement breakdown; T4 mean u 0.059). New `test_v91_public_capital` (4/4); `Config.v91()`; PLAN_v9.1.md. Open: cut nominal inflation without collapsing demand; endogenous GROWTH (vs level) needs stronger returns; v10 central bank. |
| 2.10 | 2026-07-05 | **v9 — the GOVERNMENT sector, built and diagnosed net-NEGATIVE (§28); repairs queued.** A consolidated Treasury (central bank → v10). Foundation: the **Config/Policy split** (`policy.py`) — Policy is the only run-time-mutable state (the interactive control surface); everything else is frozen Config. A deficit issues **outside money** (GOV account goes negative = government debt = private net wealth; needed fixing `allow_negative` to actually exempt `transfer`'s overdraft gate — a latent bug). Built: four tax bases (profit, **progressive** income, VAT, wealth), unemployment benefit, **deficit-targeting** government consumption, the four macroprudential caps reclassified into Policy, and **household bankruptcy** (discharge insolvent households via write_off). `government=False` ⇒ bit-identical to v8.5 (8/8 preserved); 19/19 regression green. **Findings:** a maintained **2–5%-of-GDP deficit** drives u ~0.05→~0.005 early (functional finance; balanced budget fails — gov surplus = private drain); **bankruptcy helps the long run** (late-u 0.449→0.319). BUT `Config.v9()` scores **§4 5/8** (fails T3 credit comovement, T6 firm Zipf, T7 credit boom-bust). **Diagnosis (§28.4):** the net-negative is our *fiscal design*, not government per se — (1) gov procurement routed through **PreferentialMatch funnels demand to the biggest firms** → over-concentration (T6) + the long-run-u degradation (one mechanism, two symptoms); (2) the **deficit isn't state-dependent** → inflation once at full employment (price 1.3→10.5). Ruled out as the driver: household insolvency, inflation-alone, and leverage (3 checks). Corrected an over-attribution to "missing supply side" (real limitation, not the cause). **Repairs (§28.6):** state-dependent deficit → §4 **6/8** (tamed inflation 11.5→8.2, flipped T7 FAIL→PASS); competitive procurement and household price-sensitivity (`pref_price_elasticity` ε) both **NULL** on the concentration. **Honest correction:** the "procurement→concentration→u" story was falsified, and firm-concentration-as-cause-of-u is itself unsupported (varying β pinned Gini while u moved). The **long-run degradation cause is UNPINNED** after ~6 refuted hypotheses — a first-class open question (§28.4). New `policy.py`; `test_v9_government.py` (5/5); levers built-and-off: ε, min-wage. **Thorough 5-seed diagnosis (§28.8): v9 is WORSE than v8.5 overall** (output/consumption −15%, u +68%, inflation 6×, volatility 2×, firms halved+concentrated; its §9-drain reversal is hollow — inflation erodes it). T3 = fiscal substitutes for credit cyclicality (partly real); T6 = the inflationary/volatile environment churns (births+deaths +71%) and concentrates the firm sector (crisis-reset hypothesis refuted — MORE turnover, not less). Root cause: persistent deficit in a stationary economy has no productive outlet → inflation/turbulence. **Corrects the earlier "supply-side isn't the cause" claim — it IS the long-run cause; the fix is a government that BUILDS (public investment→capacity), the clear next target.** Deferred: v10 central bank. |
| 2.9 | 2026-07-05 | **v8.5 — founder-owned genesis is the new §4 8/8 frontier (§27).** Genesis float vests in a minority founder class (`founder_owned_genesis`; `genesis_founder_pool=0.1` anchored to ~10% real business ownership) instead of splitting equally among watchers. `founder_owned_genesis=False`⇒bit-identical. **Same-seed head-to-head: v8.4 diffuse 7/8 (T3 credit +0.13, mean u 0.274, u→1.00) vs v8.5 founder 8/8 (T3 +0.29, mean u 0.175, u→0.85, T8 tail −0.87).** Founder genesis RESTORED the T3 regression pro-rata had caused, cut unemployment 36%, removed total-collapse crises — the OPPOSITE of the pre-registered "more concentration → less stable" worry (falsified). **Mechanism (3 cheaper hypotheses refuted by data):** concentration does NOT persist (ownership Gini converges to ~0.82), aggregate leverage is identical (~8500 margin debt), fire-sales are identical and `corr(fire,u₊₁)=−0.13` in both — NOT a cascade. **Surviving:** diffuse genesis makes every household a small homogeneous levered holder → crashes wipe out 5× more households (**173 vs 36 insolvent**, max lev 52× vs 14×) → demand-dead wiped-out households deepen recessions (u>0.5: 21% vs 5%) in a self-reinforcing loop; founder genesis breaks the ignition. New `test_v85_founder` (3). Also added parallel run infra (`prun.py`, `validate_parallel.py`, ~7.5× on 10-core M5). Open: full-NW-Gini metric artifact; v8.6 = founder+slow-rebalance to test persistent concentration. |
| 2.8 | 2026-07-05 | **v8.4 — dividends pro-rata to shareholders; a correctness fix that, alone, destabilizes (§26).** Per-firm regime tracked ownership yet paid dividends equally per capita (a v6 aggregate-era leftover); `pro_rata_dividends` routes each firm's payout to its holders by holdings (K-sector residual stays equal-split). `False`⇒bit-identical. Confirmed pre-registered: raises income Gini. BUT §4 8/8→7/8 — **T3 credit comovement +0.31→+0.13** (systematic shift, smaller variance ⇒ real, not noise), and macro got more volatile (mean u 0.259→0.295, seed spread ×3). **Mechanism:** equal-split dividends were an accidental automatic stabilizer (procyclical cash spread to all households); concentrating it desynchronizes ALL household borrowing from the cycle (credit-component procyclicality all fall). **Insight:** wealth concentration (T8) vs macro stability (T3/u) trade off in a model with no fiscal/monetary stabilizer. Kept off-by-default; NOT rolled back to protect a score (§0-ii) — it's step 1, completed by v8.5 (§27). New `test_v84_dividends` (3). |
| 2.7 | 2026-07-05 | **v8.3 — weakened the Tobin's-q → investment channel; fixed a spurious-volatility bug and ruled out v8.2 (§25).** The §24 mess (v8.2's effect flipping sign by seed) traced to an over-strong, too-fast q→investment channel (`lambda_q=0.3` on the *instant* bubble-laden q) pumping stock noise into real investment — a genuine volatility bug vs the empirically weak, sluggish q-elasticity. **Step 1 (realism-justified, pre-registered):** lower `lambda_q` (0.3→0.1) + drive investment off a **smoothed** q (`q_invest_smooth`; `tobin_q_ema`). `q_invest_smooth=1`⇒v8.1 bit-identical. Result (5 seeds): seed spread of u **−33%**, output **−27%** (calmer), *healthier* (u 0.35→0.27), and **§4 held 8/8** (T3 recovered +0.32, T8 skew +2.11→+3.57). A realism+stability win at no cost. **Step 2:** with the economy now calm (clean measurement), re-tested v8.2 — **slow rebalancing does nothing for the wealth tail** (upper-tail −0.52→−0.51, ownership 0.653→0.644): definitively ruled out, stays off. Retro-corrects §24 (v8.2 doesn't robustly depress the economy — that was the q-volatility artifact). Wealth tail still ≈−0.52 (not clean Pareto); both cheap fixes (Gibrat propagation, sticky rebalancing) now ruled out → the real lever is structural (founder-owned genesis firms + lower churn, v8.4). `Config.v83()` = new recommended frontier (defaults unchanged, prior layers bit-identical). New `test_v83_q_channel` (3). The two-step design was the point: fix the bug, then measure cleanly. |
| 2.6 | 2026-07-05 | **v8.2 (adaptive portfolio rebalancing) — a pre-registered experiment, FALSIFIED (§24).** Applied the B2 adaptive-expectation discipline to the one decision that lacked it: portfolio rebalancing (`portfolio_adjust` = λ, fraction of the equity gap traded per tick; 1.0 ⇒ v8.1 bit-identical). Goal: slow rebalancing → founders hold Gibrat winners → concentrated ownership *emerges* → cleaner wealth Pareto tail. λ set to λ_I (0.25) **independently**, outcome **pre-registered** (steepen to ~−0.6…−0.8, not clean −1), §0-ii-disciplined. **Result: the mechanism works (turnover halves, conserves, §0-ii-clean — fixes a real inconsistency) but the effect does NOT survive scale.** 120C smoke steepened the wealth tail (−0.41→−0.57) but the 200C/4000-tick §4 re-validation showed no steepening (−0.42→−0.40), and the scorecard slipped 8/8→6/8 (T3 credit comovement +0.27→+0.11; T6 noisy slope −1.46). **Lesson: a clean wealth Pareto is NOT reachable via sticky rebalancing** — the genesis-broad-ownership + entrant-churn ceilings dominate; the real fix is structural (founder-owned genesis firms + lower churn), a v8.3/v9 target. `portfolio_adjust` kept as a realistic dial but off by default; canonical frontier stays v8.1 (8/8). New `test_v82_portfolio` (4). The pre-registration made this a clean falsification. |
| 2.5 | 2026-07-05 | **v8.1 built (Gibrat growth) — 8/8 held-out regularities (§23).** Implemented §23 on the full v8 stack (cumulative): each C-firm's market-share attractiveness `a_f` follows a mean-preserving geometric random walk (Gibrat shock), and goods demand is allocated ∝ `a_f^β` (`PreferentialMatch`); with the v4 entry/exit barrier this is the Simon/Gabaix Zipf mechanism — the multiplicative growth §22 found missing. It's a demand-allocation change only, so A5 + share conservation are untouched (`gibrat_growth=False` ⇒ v8 bit-identical). **§4 re-validation: 8/8 — every held-out macro regularity from the micro axioms alone, the first time.** T6 firm-size slope **−1.25** (near Zipf, from v8's noisy −0.75) — but a 3-seed σ-sweep is noisy/non-monotonic (−0.80 to −1.76), so it lands *around* Zipf, not a clean stable −1. T8 flips to PASS (full-net-worth skew **+2.11**, kurt +36 — the Zipf firm tail propagates to wealth via the equity/margin chain). **Two honest caveats (§23.3):** (1) T8's wealth *tail* is still not a clean Pareto (upper-tail −0.42, outlier-driven) — throttled by §18 ownership diversification; a clean wealth tail needs concentrated persistent ownership of the Gibrat winners (v8.2 hook). (2) Concentration costs employment — u rises to ~0.39 (from 0.19); 8/8 sits in a more-concentrated, more-depressed regime. New `test_v81_gibrat` (5). Fixed a stale "NOT power-law" string in the validator. |
| 2.41 | 2026-07-05 | **§4 re-validation on the full v8 stack — 7/8 (§22).** Re-ran the held-out validation on `Config.v8()` (T8 on full net worth = cash+equity−debt). **Margin credit did not damage the cycle facts — it strengthened them**: T3 credit comovement +0.23→+0.52, T7 credit–output +0.23→+0.56 (households now borrow procyclically too); cost is more volatile unemployment (T4 range to 0.73, the crisis seed). **T8 flipped shape** (skew −0.53→+0.23, excess kurt −0.32→**+15.3**, top-10% 0.12→**0.45**) — the first realistic conserving mechanism to get a right-skewed heavy-tailed wealth distribution — **but the tail is outlier-driven, not a clean power law** (upper-tail slope −0.33), so the strict criterion marks it ❌. **T6 steepened** too (−0.38→−0.75±0.26 over 5 seeds, noisy) with the **same flat tail** (−0.32). **Unification: T6 and T8 share one missing ingredient — multiplicative (Gibrat) growth** — to convert "concentrated body, flat tail" into a clean Pareto tail. `validate_v8.py`. |
| 2.4 | 2026-07-05 | **v8 built (household margin credit) — the first mechanism to concentrate wealth without collapse.** Implemented §21: households borrow AGAINST their equity (LTV) to lever into stocks (`margin_credit`; off ⇒ v7 bit-identical). Levered demand (target equity share of net worth rises with bullishness up to `margin_max`, buys beyond cash = a margin loan capped by `margin_ltv·equity`); **margin calls** delever over-LTV households (fire sales). Margin debt interest-only. Both conservations exact (A5 ~1e-8, per-firm float ~1e-12). **Finding (round 7): borrowing finally brings an ASSET.** (1) Unlike v7's consumption debt (net-debtors underwater), margin debt is equity-collateralised — borrowers stay solvent on full net worth. (2) **Leverage concentrates wealth in a bubble** (top-decile share & net-worth Gini rise, ~0.32 at 120 firms, vs near-flat calm) — the FIRST layer to make "a few get rich" happen *without* the demand collapse (v7) or mirror-inertia (v6). (3) **Endogenous leverage ceiling**: pushing equity appetite up (`theta_equity≥0.7`) → runaway leverage → net worth →0 → frozen (credit-collateral fragility). (4) Margin amplifies volatility (output CV 0.05→0.09) — the crisis seed. New `test_v8_margin_credit` (5). |
| 2.35 | 2026-07-05 | **v7 built (household consumption credit) — the debt trap.** Implemented §20 on the full v6.2 stack (cumulative): households borrow to defend a subsistence floor (B8), capped by a debt-to-income limit (B9); loans create deposits; debt service; no default. **Finding: consumption credit is inert-or-catastrophic.** Healthy economy ⇒ nobody borrows (inert, even mildly lifts the bottom via demand); depressed economy ⇒ everyone borrows → money drains to firms (§9) → debt-deflation trap → total collapse (u→1, 100% underwater). Two roots: the floor binds on ~equal income (all-or-none, never a poor subset), and the §9 drain converts borrowing into a trap (money leaks to firms, households keep the debt). **Lesson (twice now, equity §19 + credit §20): you can't debt-finance out of a leaky bucket — the drain defeats any give-households-money mechanism; the fix is asset credit (v8), not consumption credit.** Also: credit without default is a permanent trap (parallel to v3→v4). Corrected an earlier design slip — v7 was first mis-built on the v4 base (dropping the capital market); configs are CUMULATIVE, so v7 now sits on v6.2. New `test_v7_household_credit` (5). |
| 2.3 | 2026-07-04 | **v6.2 built (equity finance) — and the stock market is decoupled from the real economy.** Implemented §19: a q>1 firm issues new shares (extra sell-side supply in its own market) at the market price; proceeds fund capex — the DIRECT financial→real channel (`equity_finance`; off ⇒ v6.1 bit-identical). Conserving (money A5, per-firm float); issuance tied to book + capped per tick (a first share-count-based rule spiralled the float 294× — fixed). **Finding (round 6): the direct channel is weak too.** Under a bubble, raising `lambda_issue` *lowers* corr(investment,q) (0.28→0.04) and cash raised stays tiny (~2.7 vs investment ~500) — because issuance is **demand-constrained** (households must buy it; they're drained) and **self-stabilising** (issuing dilutes → q falls back). Matches **pecking-order theory**. **Synthesis (v6–v6.2):** all three asset-price→real channels are weak in the boom direction — wealth-effect destabilises *downward* (§16), q-signal weak (§18, matching weak Tobin's-q theory), equity finance small & stabilising (pecking-order). So the equity market is decoupled from real activity, and the **1929/2008 crisis is a credit–collateral (Minsky/Kiyotaki–Moore) phenomenon, not an equity one** — making credit capacity depend on asset values is the earned v7. New `test_v62_equity_finance` (4). |
| 2.2 | 2026-07-04 | **v6.1 built (per-firm equity) — substrate solid, indirect channels weak.** Implemented §18: the v6 aggregate index becomes a per-firm stock market (`per_firm_equity`; off ⇒ v6 bit-identical). Each firm separately **valued** (floored residual income `book + max(0,ema(π−r·book))/r` — book floors it, r discounts, q>1 emerges for firms earning above r), **traded** (sparse **watchlists**, O(N_H·k)), and **priced** (own groping + Tobin's q). **Founder ownership**: funding a v4 startup grants its full float; bankruptcy wipes the equity (holders bear it, A5 intact). **v6.1b** q-driven investment (accelerator × clip(1+λ_q(q−1))). Both conservations exact (money A5 ~1e-8, **per-firm share float ~1e-13**). **Finding (round 5): both hoped-for payoffs are weak.** (1) Founder-equity **mirrors** deposit wealth (owner-Gini 0.51 when unequal, 0.08 when homogeneous; wealth-incl-equity Gini ≈ deposits Gini) → **does not reshape T8**; capital-gains loop too weak (small stakes + churn). (2) q-signalling is a **weak financial→real channel** — even a 50–160× bubble with λ_q≤5 gives corr(investment,q)≈+0.1; investment stays accelerator/demand-driven (matching the empirically weak q-theory of investment). **Lesson:** indirect channels (ownership, price-signal) barely feed the real economy; a financial→real crisis needs the **direct** channel — **equity finance** (issuing shares at market to fund capex) → v6.2, now *earned*. New `test_v61_per_firm_equity` (6). PLAN_v6.1 records the plan. |
| 2.1 | 2026-07-04 | **§17 derived macro indicators (observation-only, no mechanism).** Added the standard headline rates/ratios that were derivable but unlogged, computed each tick in `metrics.py` (all regression bit-identical, no conservation impact): `nominal_output`, `real_output_growth`, `wage_inflation`, `real_wage`, `labor_productivity`; **`income_gini`** and `consumption_gini` (the distribution side was previously wealth/firm-size only) and **`labor_share`** (functional distribution); `money_velocity`, `credit_to_gdp`, `debt_service_ratio`, `savings_rate`, `dividend_yield`. Sanity: labor share ≈ 0.61, consumption Gini < income Gini (both realistic). Genuinely absent (need mechanism, not a metric): market interest rate/spread (r exogenous), inflation expectations, fiscal/trade, output gap. |
| 2.0 | 2026-07-04 | **v6 built and accepted (capital market: aggregate equity index + choice 乙 + bubbles).** Implemented §16 minimal-core-first. New `EquityMarket` (one price, fixed float), `Household.shares`, **Phase 4.9**: households do portfolio choice (fundamentalist `w_f·(value−p)/p` + chartist `w_c·trend`); price **gropes on notional excess demand** (no auctioneer, §0), trades **pro-rata rationed** so money (A5) AND the share float both conserve to machine precision. Fundamental = **net asset value** (book/share) after a Gordon dividend/`r` anchor proved fragile (dividend dips collapse it). Choice **乙 activated** (equity enters household wealth accounting). **MPC-heterogeneity precursor** (`mpc_dispersion`, config-only, bit-identical at 0) run first for clean attribution: **it alone flips T8** (Gini 0.08→0.47, skew −0.7→+1.5 at σ=0.4; +5.5 at σ=0.8) — static MPC differences *compound* multiplicatively into a heavy tail, correcting the prior "merely additive" guess. **Findings (round 4):** (1) the naive **wealth effect drives the economy to depression** (u→1.0 by amplifying the §9 drain) — decoupled into a default-**off** `wealth_effect` dial; the stable core has 乙-accounting without the consumption channel; (2) **乙 accounting alone barely moves T8** (uniform θ_equity ⇒ equity mirrors deposits; needs compounding/heterogeneous returns — same multiplicative-dynamics gap as §15); (3) **liveness is drain-gated** (§13.4 analog: drained households can't trade → market stillborn in depression); (4) **bubbles reachable and money conserves through the crash** — at `w_chartist≈20` Tobin's q spikes to ~15× book then crashes, A5 drift ~1e-7 throughout (a 15× wealth boom-bust with zero money created/destroyed; the bubble is a pure valuation phantom = market cap − book). `Config.v6()` = stable core; `Config.v6_bubble()` = w_chartist 20. New `test_v6_capital_market` (7); full suite green. Per-firm equity / q-driven investment / full 1929-2008 crisis chain → v6.1+. PLAN_v6.md records the plan. |
| 1.9 | 2026-07-04 | **§15 validation round — the §4 held-out set confronted for the first time (6/8).** Ran the full model (Config.v4, dis_slope=0) against the 8 macro regularities it was never told (§0-ii): 200C/100K/2000H, 4000 ticks, 3 seeds (`validate_s4.py`). **Passes (6):** Phillips (−0.11), **Okun (−0.93)**, business-cycle comovement (employment +0.94, I +0.77, C +0.79, credit +0.23), endogenous involuntary unemployment (14%), **fat-tailed growth (excess kurtosis +0.93)**, credit-driven boom-bust (leverage CV 0.90). **Misses (2), sharing one root — no persistent multiplicative dynamics:** T6 Zipf firm size (concentration exists, sales-Gini ~0.78, but not a power law — accelerator growth mean-reverts to a common K*, not Gibrat) and T8 heavy-tailed wealth (homogeneous MPC + equity-not-attributed ⇒ wealth can't spread). Both misses independently re-derived the already-flagged next increments (heterogeneity §5, equity-to-households 乙), now earned by a failed test. Recorded a firm-size **measurement caveat** (capital-Gini 0.12 vs sales-Gini 0.78; the miss is about shape, not level). No model change — a pure harvest/observation round. |
| 1.8 | 2026-07-04 | **v5 built and accepted (diseconomies of scale) — and the pre-registered hypothesis was falsified.** Implemented §14: a coordination cost multiplies unit cost → price, $uc = uc^{\text{labor}}(1+\texttt{dis\_slope}\cdot y^{*})$. **Scale is measured by OUTPUT, not headcount** — the dominant firm is capital-intensive (huge output, ~1.8 workers), so a Lucas span-of-control (labor) diseconomy is inert; the size that runs away is output. `dis_slope=0` ⇒ v1–v4 bit-identical (52 tests green). **The deliverable is the competition phase diagram** (m × dis_slope, firm_dynamics on). **Surprise (§14.3): the reverse of the pre-registered guess.** We bet competition needed transparency **and** diseconomies together (bottom-right cell); the diagram put the low-concentration region on the **m=1 column** (Gini 0.73→0.58, markup 0.91→0.83 as slope rises; 6-seed CI tight, ±0.02), while **m≥2 barely de-concentrates** (stays ~0.9). Mechanism: the diseconomy works via **profit-squeeze → insolvency → death** (any m), *not* lost-demand (needs m≥2) — and the lost-demand channel is **defeated by §11.6 winner-take-all**: under m≥2 each buyer dumps its whole budget on the cheapest sampled seller, so pushing the leader off the cheapest perch merely *rotates* the monopoly (price-rank 0.24→0.38, Gini unmoved). So **full information is antagonistic to competition** given a capital cost-advantage — it funnels demand to the low-cost firm (transparency still lowers *markups*, §11.6: helps price, hurts structure). **The conjunction thesis survives but 3-dimensionally** (§14.4): competition = diseconomy + free entry/exit at low m; the `firm_dynamics`-off control at the competition cell restores concentration (Gini 0.58→0.85), so entry/exit is independently necessary (the diseconomy makes the losses, exit is the executioner). `Config.v5()` ships the **competitive cell** (`search_m=1, dis_slope=0.005`), correcting the plan's empirically-wrong `m≥2, dis_slope=0.02` default. New test `test_v5_diseconomies`; A5/conservation untouched (pricing-only change). Scripts `sweep_v5.py` / `confirm_v5.py`; PLAN_v5.md kept as the falsified prior. |
| 0.9 | 2026-07-03 | **v2 (investment + capital) specified.** Added **B5** (accelerator investment $K^{*}=v\,y^{e}$, partial-adjustment $I^{*}=\max(0,\lambda_I(K^{*}-K_{t-1})+\delta_K K_{t-1})$, 🟡, with overshoot/divergence warning). Added **§10** — two-sector economy ($\mathcal{F}_C$ Cobb–Douglas w/ capital, $\mathcal{F}_K$ labor-only; shared behavioral core; cut capital recursion; capital-goods market as a third M1 instance, rationable): operational equations, the two-step money-return channel (capital-sector wages) made explicit, the v2 tick (new Phase 3.5), extended state, extended parameter budget (free dials 5→7, $v,\lambda_I$ justified), and conservative v2 acceptance with the falsifiable drain-reversal prediction from §9.4. Recorded all v2 decisions in §5 (independent capital sector; shared core; cut recursion; accelerator+damping; rationable investment; depreciation on; Cobb–Douglas; capital excluded from money conservation). Fixed the **$\delta$ naming collision** — depreciation is $\delta_K$, distinct from B4's wage-flexibility $\delta$. Extended notation, roadmap (capital market added as a later hub for equity 乙 / Tobin's $q$), A1/A2/A4/M0/M1 cross-notes, and §8 handoff (capital-not-money warning; v2 deliverable). Tobin's $q$ formally deferred to the capital-market layer (needs share prices + an interest rate). |
| 1.7 | 2026-07-04 | **v4 built and accepted (firm entry/exit + bankruptcy).** Implemented §13. Ledger gained `write_off` (bad debt: borrower debt ↓ = bank equity ↓, A5-safe), `add_account`/`remove_account`, and a bank exemption from the A4 non-negativity gate (its equity may go negative = insolvency, observed). Bank gets a genesis capital buffer (`bank_capital_frac·M`). New **Phase 4.7 (demographics)**: C-firms insolvent (D−L<0) for `bankrupt_persist` ticks go **bankrupt** (repay → write off → scrap capital → remove); **profit-driven entry** (median incumbent return `profit/capital` > the hurdle `r`) at a damped, capped rate, **household-funded** (conserving) with lean startup deposits + minimal from-nothing capital. Entry↔exit make firm count **emergent**. **Acceptance met:** A5 holds through births/deaths/writeoffs (~1e-9); **zombies cleared** (standing insolvent count ~0 vs v3's ~all-but-one → credit unfreezes); firm count dynamically stable (bounded, balanced churn ~0.5/tick); writeoffs absorbed by bank equity (bank *stressed* but solvent). **Finding (round 3, §13.3):** demographics clear zombies but **do not cure monopoly** — the *revolving door* (entrants undercut by the scale leader, §11.6, die, are replaced), incumbent excess profit not competed away. This isolates the last piece: a **curb on unbounded scale advantage** (capacity limit / decreasing returns). **Unplanned finding (§13.4): the drain chokes entrepreneurship** — because entry is household-funded and the §9 drain has left households with only a few units each, a natural-sized startup cost means *no household can fund a firm and entry never fires* (a vicious circle: drain → poor households → no founding → drain persists); the model needs **lean, credit-bootstrapped startups** (~drained household wealth), which fire and self-limit pro-cyclically. Notably v4 **subsumes the planned v3.5** (insolvent exit *is* default; richer crisis machinery — cascades, bank runs — is what a multi-bank layer adds). New tests `test_v4_demographics` (5) + ledger writeoff/lifecycle (4); 57 tests green. PLAN_v4.md records the build. |
| 1.6 | 2026-07-04 | **Information transparency as one continuous dial, and a decoupling finding.** Unified RandomMatch + PriceSortedMatch into `SampledCompareMatch(m)` (`search_m`): a buyer samples m random sellers and buys the cheapest — m=1 = zero transparency (RandomMatch, bit-identical draw), m≥#sellers = full transparency (PriceSortedMatch). One dial replaces two protocols (more parsimonious); RandomMatch is now the m=1 special case, so all prior RandomMatch results are re-read as the *zero-transparency limit*. **Finding (§4-adjacent observation, §0-ii):** sweeping m on a v2 economy, **markup falls smoothly and monotonically with transparency** (0.92→0.36, m=1→100 — competition disciplines the *price level*), but **firm concentration jumps sharply at m=1→2** (size-Gini 0.80→0.97, #producing 25→~3) then plateaus — the *opposite* of the naive "transparency⇒competition". Mechanism: increasing returns to capital (Cobb-Douglas: more K ⇒ lower unit cost ⇒ lower price) + price transparency ⇒ the low-cost firm attracts buyers ⇒ runs away; blind matching (m=1) preserves many firms by spreading demand. So transparency **disciplines prices but concentrates markets** — two decoupled channels. Confounded by the absence of firm entry/exit (Gini 0.97 = the no-exit winner-take-all), so a clean market-structure-vs-transparency characterization **reinforces the need for entry/exit**. Suite green at the m=1 default. |
| 1.5 | 2026-07-04 | **Scaled up + O(N) markets (perf), and a firm-concentration finding.** Optimized the three O(N_F·N_H) hotspots to O(N_F+N_H): dividend distribution (via a CLEARING account — result-preserving), the labor market (shuffle workers once + shared pointer instead of a per-firm reshuffle), and the goods market (live-seller random-pick + swap-pop instead of shuffling every seller per buyer). **~31× speedup** (100C/50K/1000H, 300 ticks: 22s → 0.7s); 450 firms + 3000 households now runs ~8s/1000 ticks with A5 intact. The labor/goods changes alter the RNG stream, so runs are no longer bit-identical to pre-opt, but all **identity-based** guards survive unchanged (conservation, A5, the §9 drain identity to ~1e-12, capital law, credit primitives) and seed-invariance is *cleaner* at scale (real_output cv 0.16→0.015). Bumped `Config.v2()/v3()` default scale to **500C/250K/5000H** (750 firms, 5000 households — a single 2000-tick simulation is ~26s, A5 exact). Tests are pinned to small N (20C/10K/200H) to stay fast (~14s suite). Fixed the v1-kernel seed test: in the depressed kernel real_output is a near-zero *residual* whose relative noise is high and does not shrink with N — the seed-invariant macro fact is the depression itself (unemployment cv~0.01), so the test now checks the robust state indicators. **Finding:** larger N cleans medium-horizon statistics and yields a real firm-size distribution, but the **winner-take-all still dominates the long run** even at 300 firms (3000 ticks: 32/300 producing, size-Gini 0.93, rank-size slope −2.26, *steeper* than Zipf −1). This concentration is **pre-existing** (v1/v2, from RandomMatch cumulative advantage with no counter-force), not caused by v3 credit — it merely turns the credit system inert (all potential borrowers become insolvent zombies). Scale is necessary but **not sufficient**; **firm entry/exit** (a cross-cutting mechanism) is required for a healthy long-run population and a proper Zipf tail. |
| 1.4 | 2026-07-04 | **v3 built and accepted (banks + endogenous money).** Implemented §12 in the one codebase (opt-in `Config.v3()`; v1/v2/v2.5 remain bit-identical regression guards). Ledger gained a second inside instrument (loans) + `create_loan`/`repay` primitives; the conservation gate became **A5** (ΣD−ΣL=M), which reduces to M0 when there is no credit — hence zero regression. Added a single `Bank` agent, **B6** credit demand (borrow to cover the cash gap of planned wages+investment; Phase 1.5, before markets), **B7** leverage-capped supply (κ·NW), debt service (Phase 4.5: amortize + interest, no default, shortfalls defer), and bank interest→dividend distribution (closes the loop). **Acceptance (§12.8) met:** A5 to machine precision (net worth = M, drift ~1e-8); **broad money ΣD is endogenous/alive** (15000→~15370, the flat line came alive) while net worth stays pinned to M; credit is created and **funds wages** (working-capital relief, §11.5); bounded, leverage cap respected; it **mitigates** the v2 long-run deterioration (tail unemployment 0.85→0.69, output 19→38) but does **not** cure it — drained firms don't qualify (B7) and their debt *freezes* without write-off, which now concretely motivates **v3.5 (default)**. New tests `test_credit_primitives` (10), `test_v3_credit` (5); 46 tests total green. `metrics`/`diagnostics` gained broad-money/credit/leverage series + a v3 dashboard. Long-run seed-invariance is [CHECK] on u/output (the §11.2 super-cycle phase-dependence), rock-solid on broad money (cv 0.003). PLAN_v3.md records the build. |
| 1.3 | 2026-07-04 | **v3 (banks + endogenous money) specified — the layer §11.5 earned.** Added **A5 — net-worth conservation** 🔒: with credit, M0 ($\sum D=M$) is superseded by $\sum_i D_i-\sum_i L_i=M$ (broad money − outstanding credit = base money, constant); M0 is its no-credit special case. Introduced **base money / reserves $R$** ($\sum R=M$) as the new *outside* instrument carrying the conserved $M$ — correcting an earlier "$=0$" slip (net worth is $M$, not zero, since the locked "money from genesis" endowment gives the public positive net worth with no debt; the conserved $M$ *migrates* to base money when deposits become bank liabilities). Added **B6** (credit demand: firms borrow to cover *any* cash shortfall — wages + investment, framed as opening A4's single credit term, not two mechanisms; logged by purpose so attribution survives the relaxed cash-capped hiring) and **B7** (credit supply: leverage cap $L^{\max}=\kappa\,NW$ on *financial* net worth $D-L$, from which procyclical credit / a Minsky cycle emerges with no bank risk model; capital-as-collateral → v3.1). Specialized **M2**: single bank, exogenous rate $r$, fixed-proportion amortization, **no default** (default/crisis → v3.5). Added **§12** (v3 tick with new Phase 1.5 credit + Phase 4.5 debt-service; extended state incl. bank reserves; parameter budget, free dials 7→~9 with $\kappa$ justified; conservative milestone — A5 to machine precision, broad money endogenous & alive, credit relaxes the cash constraint, bounded). Updated notation ($D,L,R,\kappa,r$) and roadmap (v2 done; v2.5 falsified; v3 = banks, v3.5 = crisis). |
| 1.2 | 2026-07-03 | **§11.5: both parsimonious fixes for the K-sink fail — banks earned.** Tested the two cheaper cures before committing to M2. (1) **Symmetrizing capital (v2.5)** robustly collapses the economy (K→0, u→100%) across all params; a replacement-floor test proves it is the *structural* supply-side absorbing state (floored K-firms want to invest ~1.89/tick but realize 0.00, 100% supply-rationed), **not** calibration — vindicating §10.2's recursion cut as stability-critical. (2) **Raising ρ** is boxed between opposed failure modes — retain too much ⇒ money sink; retain too little ⇒ working-capital starvation (ρ=1 ⇒ firms can't pre-fund Phase-2 wages before Phase-3 revenue ⇒ u=100%) — so no ρ cures the sink by construction. Both failing in diagnosable ways makes **banks/M2 an earned conclusion, not a roadmap default**: both pathologies share one root — a *fixed* money stock a hoarding sector can monopolize — which M2 endogenous money dissolves (loans *create* deposits for cash-short borrowers; **not** re-lending K's idle deposits, the multiplier story M2 rejects). Added opt-in `symmetric_k` / `k_replacement_floor` toggles (v1/v2 regression bit-identical). Next: design M2. |
| 1.1 | 2026-07-03 | **§11 Findings (round 2): endogenous cycles + the fractal drain.** Long-horizon study (3000 & 10 000 ticks, 3 seeds, conservation ~1e-8). (1) v2 produces a **genuine endogenous business cycle** (multiplier–accelerator; period ~500–750 ticks; comovement corr output–employment 0.95, –investment 0.74, –capital 0.82) — logged as a §4 *observation*, not a validated result. (2) The §9 drain theorem is **fractal** — any sector retaining profit without a recirculation channel is a sink; the long run shows v2 **transfers** the drain from households to the K-sector (K-money saturates ~80% of M, bounded by M; unemployment drifts up in all seeds), not eliminates it. (3) Unlike v1's monotone sink, the **K-sink oscillates** (sink in boom, source in bust — the −π<0 injection of (12)), driving a slow ~2500–3000-tick super-cycle; "self-correcting but painful". Verified with the §9 identities as guards: household identity holds to 8.9e-16 at the deepest trough (u=0.999) ⇒ the near-total-unemployment phase is a *real* depression, not numerical; K-budget identity to 5.7e-11 with 100% of bust ticks releasing money (~⅓ of M injected during downturns). Roadmap: **symmetrize the capital sector (v2.5) before banks** — targets the self-inflicted asymmetry, no money creation, with a falsifiable "partial cure" prediction. |
| 1.0 | 2026-07-03 | **v2 built and accepted (investment + capital).** Implemented §10 in one codebase (Option A: `Firm` gains `tech`/`sells`/`invests` + capital; v1 is the special case, its three suites now regression guards — all bit-identical). Added: sector-aware production dispatch (Cobb-Douglas C / linear K) + B5 accelerator; reusable `execute_market` for the consumption and new capital-goods markets; Phase 3.5 capital market; capital law of motion; A4-capped dividends with a `dividend_cash_capped` metric (the §1.1 investment-vs-dividend cash conflict, surfaced not hidden — binds ~0.03 firms/tick, so the ordering is moot); K-sector cold-start seeding (B_K alive on tick 1). **Acceptance (§10.8) met:** 3-sector conservation (drift ~1e-9); the v2 drain identity ΔH = R_K − (1−ρ)Π_total verified to machine precision (unconditional and boom forms); drain **substantially mitigated** — households retain ~12× more money than v1 (share 0.4%→4.7%), unemployment **93%→~10%** (seed-robust, cv~0.03), output ~6→~100, capital collapses then endogenously recovers (multiplier–accelerator cycles, a welcome bonus). Full drain reversal (net_drain<0) not reached at tentative params — calibration, per §10.8. New tests: `test_behavior_v2`, `test_v2_capital`. PLAN_v2.md records the build. |
| 0.8 | 2026-07-03 | **First theorem + systematic logging.** Added §9 (Findings, round 1): the three emergent observations (monotone household drain, capped output, no self-rescue) and their resolution into the **drain identity** — the exact per-tick law $\Delta H_t=-\sum_{\pi\ge0}(1-\rho)\pi_f-\sum_{\pi<0}\pi_f$ (12), collapsing in the boom phase to $\Delta H_t=-(1-\rho)\Pi_t$ (8), with a convergence proposition ("depression inevitable", parameters set rate not fate). Verified against the simulation to machine precision (max residual 7.3e-12 over all ticks; `tests/test_household_drain.py`). Added rich per-tick metrics (`metrics.py`, ~46 series incl. flows + Gini/top-share distributions) and an experiment registry (`runlog.py`: per-run config+series+summary, flat `index.jsonl`, parameter sweeps). Roadmap implication recorded: next layer is investment + capital (before banks), with a falsifiable recovery prediction from (8). |
| 0.7 | 2026-07-03 | **Consistency fix + first kernel implementation.** Corrected the §6.3-vs-§7.2 ordering inconsistency: wage (B4) now fires *before* price (B3) in both sections, since cost-plus $uc=w_{f,t}/a$ reads the current wage (dependency is one-way, so the order is forced). Implemented roadmap step 1 in Python (`ledger`, `config`, `agents`, `interfaces`, `behavior`, `economy`, `diagnostics`, `run`): six-phase tick, `transfer`-only money movement, per-tick conservation gate, diagnostic plot, seed-invariance check. v1 bar met — money conserved (drift ~1e-9), series alive & bounded, seed-robust (cv<0.11). Observed a boom→depressed-trap transient (high unemployment); per §7.5 that is calibration, not plumbing. |
| 0.6 | 2026-07-03 | Added §8 — handoff notes addressed to the implementing agent: underspecified points with directed resolutions (abstract units; continuous-first quantities; degenerate-case guards; cross-tick derived state to persist); hard disciplines (implement §7 only, no §4-inducing mechanism, transfer primitive not bypassed, everything seeded); and v1 deliverables (kernel + conservation gate + diagnostic plot + seed-invariance check). |
| 0.5 | 2026-07-03 | Resolved all remaining open decisions: MPC heterogeneity → later via per-agent fields (zero refactor cost); proto-labor → confirmed; locked round-1 simplifications (sign-only markup signal, equal dividend split, own-sales-only observability, no wage inflation-indexation). Added §7.6 implementation commitments (transfer primitive making A1/M0 unbreakable by construction; per-agent parameter fields; seeded RNG; Python+numpy). No open decisions block the kernel. |
| 0.4 | 2026-07-03 | Recorded equity choice (甲) and abstracted matching/goods as deferrable interfaces. Added §7 — closed-form kernel equations (expectations, production, cost-plus pricing with Calvo stickiness, DNWR wages, consumption, settlement/dividends, conservation gate), the two default interfaces, a full **parameter budget table** with §0-iv status per row (only five genuinely-free dials), and a deliberately-minimal v1 milestone ("alive and conserving"). |
| 0.3 | 2026-07-03 | Added §0-iv **parsimony** as the governing objective (MDL/compression framing; free parameters must pay their way). Rewrote M3 into a three-axis decomposition (micro queuing order → randomize + robustness test; update frequency → empirically-anchored $\theta$; information timing → forced hybrid), elevated 🟡→🔒; added optional off-by-default $\alpha_{\text{info}}$ dial. Marked scheduling resolved in §5. |
| 0.2 | 2026-07-03 | Added M0 (closed economy) 🔒. Resolved two open decisions: money from genesis, closed-economy scope. Added §6 — minimal kernel entities, initial endowments, and the full phase-by-phase single-tick specification (provisional scheduling and single-good choices). |
| 0.1 | 2026-07-03 | Initial draft. Established §0 epistemic stance (identities vs. behavior; micro-axioms vs. macro-test-set; no auctioneer). Accounting axioms A1–A4 locked. Behavioral axioms B1–B4. Market/institutional axioms M1–M3. Validation targets and roadmap. |