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
| $\mathcal{P}_t$ | set of living persons at end of tick $t$; persons are demographic subjects, not necessarily ledger agents |
| $N_t$ | living person headcount, $N_t = |\mathcal{P}_t|$ |
| $\text{Births}_t,\ \text{Deaths}_t,\ \text{Mig}_t$ | recorded demographic flows during tick $t$; migration is zero in the closed-economy kernel unless explicitly enabled |
| $a_{p,t}$ | age of person $p$ at tick $t$ |
| $s_p$ | sex of person $p$ where required by demographic hazards |
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
