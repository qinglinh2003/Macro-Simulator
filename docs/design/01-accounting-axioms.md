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

