"""Closed-form behavioral equations of the kernel (spec §7.2).

These are the §2 behavioral axioms made executable. They run during Phase 1
(synchronous planning): each agent reads only the frozen end-of-(t-1) state and
writes its *plan* fields. No money moves here -- transfers happen later, in the
sequential market phases (economy.py).

Phase-1 firing order (spec §6.3, with the wage<->price fix from review):
    B2 expectations -> target inventory/production -> B4 wage -> B3 price -> B1 consumption
Wage MUST precede price: cost-plus uses THIS tick's wage, uc = w_{f,t}/a (§7.2),
so the wage has to be settled before the markup/price step reads it. (This
corrects the §6.3 vs §7.2 ordering inconsistency surfaced in review.)

Degenerate-case guards are explicit and surfaced (spec §8.1), never silent.
"""

from __future__ import annotations

import math
import random

from macro_sim.domain.agents import Firm, Household
from macro_sim.markets.matching import EPS


def diversify_mpc(cfg, households) -> None:
    """Draw household MPC parameters from a mean-preserving lognormal distribution."""
    rng = random.Random(cfg.seed + 90210)
    dispersion = cfg.mpc_dispersion
    mu = -0.5 * dispersion * dispersion
    for household in households:
        household.alpha1 = min(0.99, max(0.01, cfg.alpha1 * rng.lognormvariate(mu, dispersion)))
        household.alpha2 = min(
            household.alpha1 - 1e-6,
            max(0.001, cfg.alpha2 * rng.lognormvariate(mu, dispersion)),
        )


def _sign(x: float) -> float:
    """Sign with a dead zone: |x| < EPS counts as 0 (spec §8.1: I*=0 -> no markup
    change; treat a vanishing inventory gap as no signal, not noise)."""
    if x > EPS:
        return 1.0
    if x < -EPS:
        return -1.0
    return 0.0


# -- B2: adaptive (error-correction) expectations -------------------------------

def update_demand_expectation(firm: Firm) -> None:
    """d^e_{f,t} = d^e_{f,t-1} + lambda_d (signal_{f,t-1} - d^e_{f,t-1})  (§7.2).

    v16-L6: the signal is sales PLUS the firm's share of rationed (unmet) buyer
    demand -- the order-book/footfall term. Without it a stocked-out seller reads
    zero sales as zero demand and expectations spiral to extinction (the K-sector
    deadlock). rationed_prev is identically 0.0 with the flag off (bit-identical)."""
    signal = firm.sales_prev + firm.rationed_prev
    firm.demand_expected += firm.lambda_d * (signal - firm.demand_expected)
    if firm.demand_expected < 0.0:
        firm.demand_expected = 0.0  # demand can't be negative (A4 spirit); guard, surfaced


def update_income_expectation(hh: Household) -> None:
    """Y^e_{h,t} = Y^e_{h,t-1} + lambda_y (Y_{h,t-1} - Y^e_{h,t-1})  (§7.2).

    Y_{h,t-1} = wages + dividends realized last tick (persisted in income_realized).
    """
    hh.y_expected += hh.lambda_y * (hh.income_realized - hh.y_expected)
    if hh.y_expected < 0.0:
        hh.y_expected = 0.0


# -- sector-aware production technology (v2 dispatch; linear == v1) --------------

def produce(firm: Firm, n_labor: float, pubcap_factor: float = 1.0) -> float:
    """Output from ``n_labor`` workers. Linear (v1 / K-sector): y = a N. Cobb-Douglas
    (C-sector): y = A K_{t-1}^α N^{1-α}, with K predetermined (firm.capital = K_{t-1}).
    v9.1: an economy-wide PUBLIC-capital productivity factor (Barro) multiplies output;
    pubcap_factor=1.0 (γ=0 or K_pub=0) ⇒ bit-identical."""
    if n_labor <= 0.0:
        return 0.0
    if firm.tech == "linear":
        return firm.a * n_labor * pubcap_factor
    assert firm.capital > 0.0, "Cobb-Douglas firm needs K>0 (§8.1 guard)"
    return firm.A * firm.capital ** firm.alpha * n_labor ** (1.0 - firm.alpha) * pubcap_factor


def labor_demand_notional(firm: Firm, y_target: float, pubcap_factor: float = 1.0) -> float:
    """Labor needed to produce ``y_target`` (invert the production fn), PRE cash cap.
    y_target<=0 => 0 (guard, surfaced). Cobb-Douglas inversion needs K>0. v9.1: divide the
    target by the public-capital factor before inverting (pubcap_factor=1.0 ⇒ identical)."""
    if y_target <= EPS:
        return 0.0
    yt = y_target / pubcap_factor
    if firm.tech == "linear":
        return yt / firm.a
    assert firm.capital > 0.0, "Cobb-Douglas firm needs K>0 to invert production (§8.1)"
    return (yt / (firm.A * firm.capital ** firm.alpha)) ** (1.0 / (1.0 - firm.alpha))


def capital_service_cost(
    firm: Firm,
    *,
    replacement_price: float,
    opportunity_rate: float,
) -> float:
    """Nominal per-tick service cost of the opening productive-capital stock.

    ``firm.capital`` is a physical stock, while ``replacement_price`` is money
    per unit of capital goods.  Depreciation and the marginal financing/opportunity
    rate are both per tick, so their product has units of money per tick.  We do
    not subtract contemporaneous CPI inflation: the relevant expectation would be
    *capital-goods* price inflation, for which the model does not yet have a
    committed lagged expectation.  This is therefore the explicit zero-expected-
    capital-gain user-cost convention.
    """
    values = (replacement_price, opportunity_rate, firm.capital, firm.delta_K)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("capital-service inputs must be finite")
    capital_value = max(0.0, float(replacement_price)) * max(0.0, float(firm.capital))
    service_rate = max(0.0, float(firm.delta_K)) + max(0.0, float(opportunity_rate))
    return capital_value * service_rate


def capital_service_unit_cost(
    firm: Firm,
    *,
    replacement_price: float,
    opportunity_rate: float,
) -> float:
    """Allocate nominal capital service over planned physical output.

    A zero-output plan has no units over which a unit cost can honestly be
    allocated.  Returning zero keeps the quote finite and leaves the existing
    zero-plan fallback in charge; the fixed service cost remains observable in
    ``capital_service_cost`` rather than being hidden behind an EPS divisor.
    """
    if firm.production_target <= EPS:
        return 0.0
    return capital_service_cost(
        firm,
        replacement_price=replacement_price,
        opportunity_rate=opportunity_rate,
    ) / float(firm.production_target)


def unit_cost(
    firm: Firm,
    capital_unit_cost: float = 0.0,
    *,
    productivity_adjusted: bool = True,
) -> float:
    """Unit cost for the B3 markup. Base = unit LABOR cost (vintages explicit, PLAN_v2
    §1.5): Cobb-Douglas uc_labor = w N^d / y* (planned avg labor cost); linear = w/a.

    v5 -- diseconomies of scale (§14): a coordination cost RISING with the SCALE OF
    OPERATIONS (planned output y*) multiplies the base, uc = uc_labor * (1 + dis_slope * y*).
    So bigger firms post higher prices. Scale is measured by OUTPUT, not headcount: in this
    model the dominant firm is capital-intensive (huge K, high output, FEW workers), so a
    labor-based (span-of-control) diseconomy would miss it entirely -- the diseconomy must
    track the size that actually runs away, which is output. It curbs monopoly via the
    PROFIT-SQUEEZE channel (high output -> high uc -> bounded markup can't cover it -> losses
    -> insolvency -> death), which works even at m=1. The surprise (§14): this de-concentrates
    ONLY at LOW transparency; under m>=2 winner-take-all the leader is merely rotated, not
    thinned, so concentration persists. With dis_slope=0 (v1-v4) uc is unchanged."""
    y = firm.production_target
    if y > EPS and (productivity_adjusted or firm.tech != "linear"):
        # ``labor_demand_notional`` already reflects the composite TFP/public-capital
        # output factor.  Pricing the planned wage bill over planned output therefore
        # passes linear-sector productivity gains into unit cost instead of leaving
        # them as a pure profit windfall.
        base = firm.wage * firm.labor_demand_notional / y
    elif firm.tech == "linear":
        base = firm.wage / firm.a
    else:
        assert firm.capital > 0.0, "Cobb-Douglas firm needs K>0 (§8.1 guard)"
        base = firm.wage / (firm.A * firm.capital ** firm.alpha)   # y*≈0 fallback (uc at N=1)
    base += firm.energy_intensity * firm.energy_avg_cost   # v17.0: Leontief energy cost/unit (0 when off)
    scaled_variable_cost = base * (1.0 + firm.dis_slope * firm.production_target)
    if capital_unit_cost > 0.0:
        # Long-run price recovery only.  Accounting separately recognizes
        # replacement-cost depreciation and realized cash interest; this term
        # never posts a ledger transfer or a second P&L expense.
        return scaled_variable_cost + capital_unit_cost
    return scaled_variable_cost


# -- target inventory & production (B-plan) -------------------------------------

def plan_production(firm: Firm, gap_close: float = 1.0) -> None:
    """I*_{f,t} = phi d^e ;  y*_{f,t} = max(0, d^e + gap_close (I* - I_{f,t-1}))  (§7.2).

    firm.inventory is still the end-of-(t-1) stock at planning time.

    gap_close (v13) throttles how much of the inventory gap enters TODAY's production target.
    1.0 reproduces the one-shot v12 rule exactly. On a one-day tick a multi-day inventory
    cover (phi in days of demand) with one-shot closing asks for phi days of output at once --
    the daily-calibrated economy ran at a 2% labor fill rate before this throttle existed.
    """
    firm.target_inventory = firm.phi * firm.demand_expected
    gap = firm.target_inventory - firm.inventory
    firm.production_target = max(0.0, firm.demand_expected + gap_close * gap)


# -- B4: wages (raise on shortage, never cut; DNWR floor automatic) --------------

def plan_wage(firm: Firm, rng: random.Random, theta_wage: float,
              min_wage: float = 0.0, delta: float = 0.0,
              expected_inflation: float = 0.0, wage_indexation: float = 0.0) -> None:
    """Wage offer w_{f,t} (§7.2).

    Target rises only if the firm was labor-rationed last tick
    (N_{f,t-1} < N^{d,eff}_{f,t-1}); otherwise it holds. Because the target never
    falls, the DNWR floor (delta = 0) is automatic. The posted wage catches up to
    target with per-tick probability theta_wage (Calvo form, M3(b)).

    min_wage (a Policy lever, v9.3): a legal wage floor. It binds IMMEDIATELY and
    bypasses Calvo stickiness -- a statutory minimum is not subject to the firm's
    own repricing hazard; when the floor is above the posted wage the firm must
    comply this tick. min_wage=0 => the branch never fires => bit-identical.

    tick-0 cold start: labor_demand_eff_prev and hired_prev are both 0 (agents.py),
    so "rationed" is False on the first tick -> no first-tick raise (§8.1, point 3).

    v23 WAGE INDEXATION. Until now this rule was PURELY a labour-market tightness rule --
    prices appear nowhere in it -- so the nominal wage was anchored to nothing and the REAL
    wage was a free-floating residual. That was survivable only while the model deflated:

      * `delta` (the downward drift) was added in v13 to stop a DEFLATION from ratcheting the
        real wage up without bound. But that deflation was itself an ARTEFACT of the capital
        clock bug: capital was economically absent, so the pricing rule never charged for it.
      * With the clock fixed prices RISE, and with the second contract labour is well supplied,
        so firms hire freely and the `delta` drift fires constantly -- driving NOMINAL wages
        DOWN through an inflation. Measured (baseline_s1): wage inflation -0.5%/yr against
        price inflation +7.4%/yr, with the real wage collapsing 0.954 -> 0.792 (-17%), which is
        what pushes households under the subsistence basket.

    A patch built for a bug became a defect once the bug was fixed. Real wage-setting indexes to
    prices (explicitly, or through bargaining). With `wage_indexation` > 0 the tightness terms
    apply to the REAL wage and expected inflation is the nominal baseline:

        w_target = w * (1 + indexation * pi_e (+ omega if rationed | - delta if hiring freely))

    `expected_inflation` is COMMITTED observation state -- the same lag/EMA the monetary
    transmission reads, never this tick's price. wage_indexation=0 => bit-identical.
    """
    drift = wage_indexation * float(expected_inflation)
    was_rationed = firm.hired_prev < firm.labor_demand_eff_prev - EPS
    if was_rationed:
        w_target = firm.wage * (1.0 + drift + firm.omega)
    elif delta > 0.0 and firm.labor_demand_eff_prev > EPS:
        # v13 downward wage flexibility: a firm that hired freely last tick lets its wage
        # target drift down by delta. delta=0 keeps the strict-DNWR v12 behavior bit-identical.
        # Under indexation the cut is in REAL terms: it can no longer drive the NOMINAL wage
        # down while prices are rising.
        w_target = firm.wage * (1.0 + drift - delta)
    else:
        w_target = firm.wage * (1.0 + drift)
    if rng.random() < theta_wage:
        firm.wage = w_target
    # else: posted wage sticks at w_{f,t-1} (already in firm.wage)
    if min_wage > 0.0 and firm.wage < min_wage:
        firm.wage = min_wage           # statutory floor: immediate, not Calvo-gated
    assert firm.wage > 0.0, "wage must stay > 0 (needed for w/a and floor(D/w))"


# -- B3: cost-plus pricing with Calvo stickiness --------------------------------

def plan_price(
    firm: Firm,
    rng: random.Random,
    theta_price: float,
    capital_unit_cost: float = 0.0,
    *,
    productivity_adjusted: bool = True,
) -> None:
    """Posted price p_{f,t} (§7.2, B3). MUST run after plan_wage (uc reads firm.wage)
    and after labor_demand_notional is set (Cobb-Douglas uc needs N^d).

    uc = unit_cost(firm) (w/a linear; w N^d/y* Cobb-Douglas) ; markup adapts to the
    local inventory signal s = sign(I*_{f,t-1} - I_{f,t-1}) (understocked => raise) ;
    p* = (1+mu) uc ; posted price catches up to p* with probability theta_price.
    """
    assert firm.a > 0.0, "productivity a must be > 0 (§8.1 guard)"
    # markup signal: last tick's target vs last tick's realized stock (both persisted;
    # firm.inventory is still end-of-(t-1) here).
    s = _sign(firm.target_inventory_prev - firm.inventory)
    firm.markup = min(firm.mu_max, max(firm.mu_min, firm.markup + firm.eta * s))

    p_target = (1.0 + firm.markup) * unit_cost(
        firm,
        capital_unit_cost,
        productivity_adjusted=productivity_adjusted,
    )
    if rng.random() < theta_price:
        firm.price = p_target
    # else: posted price sticks at p_{f,t-1}
    assert firm.price > 0.0, "posted price must stay > 0"


# -- B5: investment via the accelerator (v2, consumption firms only) -------------

def investment_user_cost_multiplier(
    *,
    nominal_loan_rate: float,
    expected_inflation: float,
    neutral_nominal_rate: float,
    inflation_target: float,
    depreciation: float,
    elasticity: float,
    multiplier_min: float,
    multiplier_max: float,
    user_cost_floor: float,
) -> float:
    """Return a bounded investment response to the expected real user cost.

    All rates are per tick.  The current cost is ``r_loan - pi_expected + delta``;
    its neutral benchmark is ``r_neutral_loan - pi_target + delta``.  Nominal rates
    respect the ZLB, while a positive cost floor makes negative-real-rate states
    finite.  The multiplier is a constant-elasticity response to their ratio and is
    clipped explicitly, so an inflation spike cannot make desired capital diverge.
    """
    values = (
        nominal_loan_rate, expected_inflation, neutral_nominal_rate,
        inflation_target, depreciation, elasticity, multiplier_min,
        multiplier_max, user_cost_floor,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("user-cost inputs must be finite")
    if elasticity <= 0.0:
        return 1.0
    current = max(
        user_cost_floor,
        max(0.0, nominal_loan_rate) - expected_inflation + max(0.0, depreciation),
    )
    neutral = max(
        user_cost_floor,
        max(0.0, neutral_nominal_rate) - inflation_target + max(0.0, depreciation),
    )
    response = (current / neutral) ** (-elasticity)
    return min(multiplier_max, max(multiplier_min, response))


def plan_investment(
    firm: Firm,
    lambda_q: float = 0.0,
    q_floor: float = 0.5,
    q_cap: float = 2.0,
    *,
    nominal_loan_rate: float | None = None,
    expected_inflation: float = 0.0,
    neutral_nominal_rate: float = 0.0,
    inflation_target: float = 0.0,
    user_cost_elasticity: float = 0.0,
    user_cost_multiplier_min: float = 0.5,
    user_cost_multiplier_max: float = 1.5,
    user_cost_floor: float = 1.0e-9,
) -> None:
    """Notional capital-good demand I*_{f,t} (B5, §10.4). C-firms only.

        K*_{f,t} = v · y^e_{C,f,t}   (desired capital tracks expected output)
        I*_{f,t} = max(0, λ_I(K* - K_{t-1}) + δ_K K_{t-1}) · g(q_f)

    Partial adjustment (λ_I damps accelerator overshoot) plus depreciation replacement.
    v6.1b: a per-firm Tobin's q multiplier g(q)=clip(1+λ_q(q−1), q_floor, q_cap) tilts
    investment by market valuation -- the financial→real channel (high q ⇒ invest more).
    With an explicit loan rate, a second bounded multiplier responds to the expected
    real financing user cost plus depreciation, relative to the neutral-rate
    benchmark.  Omitting the rate keeps the historical accelerator bit-identical.
    Capped later by cash + M1 supply.
    """
    if not firm.invests:
        firm.investment_target = 0.0
        return
    k_star = firm.v * firm.demand_expected   # y^e_C ≈ expected consumption demand
    target = max(0.0, firm.lambda_I * (k_star - firm.capital) + firm.delta_K * firm.capital)
    if lambda_q > 0.0:
        g = min(q_cap, max(q_floor, 1.0 + lambda_q * (firm.tobin_q_ema - 1.0)))   # v8.3: smoothed q
        target *= g
    if nominal_loan_rate is not None:
        target *= investment_user_cost_multiplier(
            nominal_loan_rate=nominal_loan_rate,
            expected_inflation=expected_inflation,
            neutral_nominal_rate=neutral_nominal_rate,
            inflation_target=inflation_target,
            depreciation=firm.delta_K,
            elasticity=user_cost_elasticity,
            multiplier_min=user_cost_multiplier_min,
            multiplier_max=user_cost_multiplier_max,
            user_cost_floor=user_cost_floor,
        )
    firm.investment_target = target


# -- B6 / B7: credit demand and supply (v3, decision-only; economy executes) ----

def credit_request(firm: Firm, deposits: float, p_k_est: float) -> float:
    """B6: the cash a firm asks to borrow (§12.4). Gap between planned spending —
    NOTIONAL wage bill (w·N^d, uncapped, since credit is meant to fund it) plus
    desired investment outlay (I*·p^K estimate) — and cash on hand. >=0."""
    wage_need = firm.wage * firm.labor_demand_notional
    investment_need = firm.investment_target * max(0.0, p_k_est)
    return max(0.0, wage_need + investment_need - deposits)


def firm_debt_service_headroom(
    *,
    expected_operating_cash_flow: float,
    debt: float,
    loan_rate: float,
    amort: float,
    min_dscr: float,
) -> float:
    """Additional debt consistent with a transparent one-tick DSCR constraint.

    Expected operating cash flow is the pre-financing cash available for contractual
    principal plus interest.  Both ``loan_rate`` and ``amort`` are per tick, matching
    actual debt service.  At a zero service rate the constraint is non-binding; at
    positive rates, a hike can only weakly reduce headroom.
    """
    service_rate = max(0.0, loan_rate) + max(0.0, amort)
    if service_rate <= EPS:
        return math.inf
    supported_total_debt = max(0.0, expected_operating_cash_flow) / (
        max(1.0, min_dscr) * service_rate
    )
    return max(0.0, supported_total_debt - max(0.0, debt))


def credit_grant(
    requested: float,
    deposits: float,
    debt: float,
    kappa: float,
    *,
    book_equity: float | None = None,
    borrowing_base_proxy: float | None = None,
    expected_operating_cash_flow: float | None = None,
    loan_rate: float = 0.0,
    amort: float = 0.0,
    min_dscr: float = 1.0,
) -> float:
    """B7: additional credit allowed by leverage, assets, and optional DSCR.

    The historical path caps debt at ``kappa * (deposits - debt)``.  Callers may
    instead supply nominal ``book_equity`` plus a gross-debt
    ``borrowing_base_proxy`` frozen before origination.  Existing debt is then
    deducted once from each gross ceiling.  The borrowing base is not a claim
    priority or default-recovery model; those legal/settlement layers remain
    explicitly out of scope.
    """
    nw = deposits - debt if book_equity is None else book_equity
    if nw <= 0.0:
        return 0.0
    room = kappa * nw - debt          # headroom above existing debt
    if borrowing_base_proxy is not None:
        room = min(room, max(0.0, borrowing_base_proxy) - debt)
    if expected_operating_cash_flow is not None:
        room = min(room, firm_debt_service_headroom(
            expected_operating_cash_flow=expected_operating_cash_flow,
            debt=debt,
            loan_rate=loan_rate,
            amort=amort,
            min_dscr=min_dscr,
        ))
    return max(0.0, min(requested, room))


def debt_service_amounts(debt: float, deposits: float, r: float, amort: float):
    """Principal + interest a firm pays this tick (§12.4), decision-only. Amortize a
    fixed fraction of debt (capped by cash), then pay interest r·L from what's left;
    any shortfall defers (no default in v3). Returns (principal, interest); the
    economy then calls ledger.repay(principal) and ledger.transfer(interest → bank)."""
    if debt <= EPS:
        return 0.0, 0.0
    principal = min(amort * debt, deposits)
    interest = min(r * debt, deposits - principal)   # from cash after amortization
    return principal, interest


# -- B1: consumption out of expected income and wealth (choice 甲) ---------------

def plan_consumption(hh: Household, deposits_prev: float, equity_wealth: float = 0.0,
                     curvature: float = 1.0, wealth_ref: float = 1.0) -> None:
    """Desired nominal consumption budget C_{h,t} = alpha1 Y^e + alpha2 D_{t-1} (§7.2).

    Choice (甲): wealth V_h = D_h, so the wealth term is just deposits. This is a
    *budget*, capped later by LIVE deposits in the goods market (A4) -- it may
    exceed this tick's wage income by dipping into the alpha2 wealth channel, and
    that is intended (do NOT clamp it to current income). Unspent budget stays as
    deposits (= saving).
    """
    # v6 wealth EFFECT: equity value (already weighted by cfg.wealth_effect at the call site,
    # and smoothed) enters the B1 wealth term. This is SEPARATE from choice 乙's wealth
    # ACCOUNTING (metrics): the effect is off (equity_wealth=0) by default because it amplifies
    # the §9 drain (§16). 0 pre-v6 and when wealth_effect=0 -> bit-identical.
    wealth = deposits_prev + equity_wealth
    # Buffer-stock (§16.7): wealth term is CONCAVE (γ<1), so the marginal MPC out of wealth
    # α2·γ·(V/W_ref)^(γ-1) FALLS as wealth rises -- the rich endogenously have low MPC (realistic
    # causality wealth→MPC), from a rule identical for everyone. Normalized by W_ref so γ=1 is
    # EXACTLY the linear term (bit-identical); the branch keeps that exact in floating point.
    if curvature >= 1.0:
        wealth_term = hh.alpha2 * wealth
    else:
        wealth_term = hh.alpha2 * wealth_ref * (max(0.0, wealth) / wealth_ref) ** curvature
    hh.consumption_budget = hh.alpha1 * hh.y_expected + wealth_term
    if hh.consumption_budget < 0.0:
        hh.consumption_budget = 0.0


def household_contractual_debt_service(
    *,
    debt: float,
    margin_debt: float,
    loan_rate: float,
    amort: float,
    interest_arrears: float = 0.0,
) -> float:
    """Scheduled household cash service for the next settlement, per tick.

    Ordinary consumer and mortgage principal amortizes; margin principal remains
    callable in the equity phase and is therefore excluded here.  Interest applies
    to all live ledger debt, exactly as in household debt settlement.  Carried
    interest is a memo claim: it increases cash service without becoming principal
    or attracting interest itself.
    """
    live_debt = max(0.0, debt)
    margin = min(live_debt, max(0.0, margin_debt))
    amortizing = live_debt - margin
    return (
        max(0.0, interest_arrears)
        + max(0.0, amort) * amortizing
        + max(0.0, loan_rate) * live_debt
    )


def reserve_household_debt_service(
    consumption_budget: float,
    *,
    deposits: float,
    debt: float,
    margin_debt: float,
    loan_rate: float,
    amort: float,
    interest_arrears: float = 0.0,
) -> float:
    """Cash-cap desired goods spending so contractual debt service remains available.

    This is a plan, not a transfer: actual principal and interest are posted once in
    the debt-service phase, so the reservation cannot double-charge the household.
    A cash-rich debtor whose planned spending already leaves enough for service is
    unchanged; subtracting service directly from the *budget* would create a false
    income effect.  A cash-poor debtor is capped at deposits less scheduled service.
    """
    service = household_contractual_debt_service(
        debt=debt,
        margin_debt=margin_debt,
        loan_rate=loan_rate,
        amort=amort,
        interest_arrears=interest_arrears,
    )
    spendable_cash = max(0.0, float(deposits) - service)
    return min(max(0.0, float(consumption_budget)), spendable_cash)


# -- v6: portfolio choice (equity vs deposits) ----------------------------------

def plan_equity_demand(hh: Household, market, deposits: float, cfg) -> float:
    """Desired change in index holdings at the current price (§16, decision-only). The target
    equity share of wealth is `theta_equity` tilted by a demand pressure that mixes two forces:

        pressure = w_fundamental·(value − p)/p   (fundamentalist: buy cheap → STABILISING)
                 + w_chartist·trend               (chartist: chase the trend → the BUBBLE knob)

    target equity value = clip(theta_equity·(1+pressure), 0, 0.95) · wealth, wealth = D + shares·p.
    Budget-capped by cash on hand (buys) and by holdings (sells). Returns desired Δshares."""
    p = market.price
    if p <= EPS:
        return 0.0
    wealth = deposits + hh.shares * p
    pressure = (cfg.w_fundamental * (market.fundamental - p) / p
                + cfg.w_chartist * market.trend)
    target_share = min(0.95, max(0.0, cfg.theta_equity * (1.0 + pressure)))
    d = target_share * wealth / p - hh.shares
    if d > 0.0:
        return min(d, deposits / p)        # can only buy with cash on hand
    return max(d, -hh.shares)              # can only sell what is held


# -- B8: household credit demand (v7) -- borrow to defend a subsistence floor ---

def household_credit_request(hh: Household, deposits: float, subsistence: float):
    """B8 (§20, decision-only): a household defends a consumption target = max(B1 budget,
    subsistence floor) and borrows the shortfall of its means (deposits + EXPECTED income) below
    that target. So only households whose means fall short of subsistence borrow -- the drained/
    poor -- while savers don't. Returns (target, borrow_request>=0); the economy caps the borrow
    by the debt-to-income limit and calls create_loan (loans create deposits, M2, A5-safe)."""
    target = max(hh.consumption_budget, subsistence)
    return target, max(0.0, target - deposits - hh.y_expected)
