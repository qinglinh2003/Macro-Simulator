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

### P3 — Mortality hazard 🟡

*(Active once the population layer exists.)*

**Natural language.** Each living person faces an individual death hazard. In the frozen
demographic kernel this hazard depends only on demographic state, chiefly age and sex. Any
economic dependence is added later as a specific micro mechanism, not smuggled in as an
aggregate fact.

**Formal.**
$$\Pr(p \text{ dies during } t) = \mu(a_{p,t}, s_p;\ \theta_\mu,\ E_t),$$
where $E_t$ is the economic state read by the hazard function. In Phase 0,
$E_t=\varnothing$ or `FrozenEconomicState`, so the hazard reduces to
$$\mu(a_{p,t}, s_p;\ \theta_\mu).$$

**Discipline.** "The rich live longer" is not an axiom. A later heterogeneous mortality
channel may let $\mu$ respond to a person's own consumption, wealth, health capital, or
access to care; the aggregate wealth-longevity gradient must then emerge and be validated
in §4.

**Why 🟡.** Age-specific mortality is the minimal micro primitive required for non-immortal
agents. The baseline functional form is tentative; the discipline that it is an individual
hazard, not an encoded macro regularity, is locked by §0-ii.

### P4 — Fertility hazard 🟡

*(Active once birth dynamics exist.)*

**Natural language.** Births arise from individual fertility hazards, not from an imposed
macro population path. In the frozen demographic kernel the hazard depends only on age,
sex, and eligibility. Economic coupling is added later through individual or household
mechanisms.

**Formal.**
$$\Pr(p \text{ gives birth during } t) = m(a_{p,t}, s_p,\text{eligibility}_{p,t};\ \theta_m,\ E_t).$$
In Phase 0, $E_t=\varnothing$ or `FrozenEconomicState`, so the hazard reduces to a baseline
age-specific fertility schedule.

**Discipline.** The demographic transition is not an axiom. A later macro or heterogeneous
fertility channel may let $m$ respond to income, job stability, child cost, housing cost,
public transfers, or household composition; declining fertility with development must be a
held-out target in §4, not a primitive hard-coded here.

**Why 🟡.** Birth hazards are the minimal source of new persons. The baseline age schedule
is empirical and revisable; the "micro hazard first, macro regularity as validation"
discipline is not.

---
