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
    """d^e_{f,t} = d^e_{f,t-1} + lambda_d (sales_{f,t-1} - d^e_{f,t-1})  (§7.2)."""
    firm.demand_expected += firm.lambda_d * (firm.sales_prev - firm.demand_expected)
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


def unit_cost(firm: Firm) -> float:
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
    if firm.tech == "linear":
        base = firm.wage / firm.a
    else:
        assert firm.capital > 0.0, "Cobb-Douglas firm needs K>0 (§8.1 guard)"
        y = firm.production_target
        base = (firm.wage * firm.labor_demand_notional / y) if y > EPS \
            else firm.wage / (firm.A * firm.capital ** firm.alpha)   # y*≈0 fallback (uc at N=1)
    return base * (1.0 + firm.dis_slope * firm.production_target)


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
              min_wage: float = 0.0, delta: float = 0.0) -> None:
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
    """
    was_rationed = firm.hired_prev < firm.labor_demand_eff_prev - EPS
    if was_rationed:
        w_target = firm.wage * (1.0 + firm.omega)
    elif delta > 0.0 and firm.labor_demand_eff_prev > EPS:
        # v13 downward wage flexibility: a firm that hired freely last tick lets its wage
        # target drift down by delta. delta=0 keeps the strict-DNWR v12 behavior bit-identical.
        # Without this, a deflation ratchets the real wage up without bound (the ZLB smoke run
        # settled at real wage 4.5x and a 59% job-guarantee share).
        w_target = firm.wage * (1.0 - delta)
    else:
        w_target = firm.wage
    if rng.random() < theta_wage:
        firm.wage = w_target
    # else: posted wage sticks at w_{f,t-1} (already in firm.wage)
    if min_wage > 0.0 and firm.wage < min_wage:
        firm.wage = min_wage           # statutory floor: immediate, not Calvo-gated
    assert firm.wage > 0.0, "wage must stay > 0 (needed for w/a and floor(D/w))"


# -- B3: cost-plus pricing with Calvo stickiness --------------------------------

def plan_price(firm: Firm, rng: random.Random, theta_price: float) -> None:
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

    p_target = (1.0 + firm.markup) * unit_cost(firm)
    if rng.random() < theta_price:
        firm.price = p_target
    # else: posted price sticks at p_{f,t-1}
    assert firm.price > 0.0, "posted price must stay > 0"


# -- B5: investment via the accelerator (v2, consumption firms only) -------------

def plan_investment(firm: Firm, lambda_q: float = 0.0,
                    q_floor: float = 0.5, q_cap: float = 2.0) -> None:
    """Notional capital-good demand I*_{f,t} (B5, §10.4). C-firms only.

        K*_{f,t} = v · y^e_{C,f,t}   (desired capital tracks expected output)
        I*_{f,t} = max(0, λ_I(K* - K_{t-1}) + δ_K K_{t-1}) · g(q_f)

    Partial adjustment (λ_I damps accelerator overshoot) plus depreciation replacement.
    v6.1b: a per-firm Tobin's q multiplier g(q)=clip(1+λ_q(q−1), q_floor, q_cap) tilts
    investment by market valuation -- the financial→real channel (high q ⇒ invest more).
    λ_q=0 (or q=1) ⇒ g=1 ⇒ pure accelerator (bit-identical). Capped later by cash + M1 supply.
    """
    if not firm.invests:
        firm.investment_target = 0.0
        return
    k_star = firm.v * firm.demand_expected   # y^e_C ≈ expected consumption demand
    target = max(0.0, firm.lambda_I * (k_star - firm.capital) + firm.delta_K * firm.capital)
    if lambda_q > 0.0:
        g = min(q_cap, max(q_floor, 1.0 + lambda_q * (firm.tobin_q_ema - 1.0)))   # v8.3: smoothed q
        target *= g
    firm.investment_target = target


# -- B6 / B7: credit demand and supply (v3, decision-only; economy executes) ----

def credit_request(firm: Firm, deposits: float, p_k_est: float) -> float:
    """B6: the cash a firm asks to borrow (§12.4). Gap between planned spending —
    NOTIONAL wage bill (w·N^d, uncapped, since credit is meant to fund it) plus
    desired investment outlay (I*·p^K estimate) — and cash on hand. >=0."""
    wage_need = firm.wage * firm.labor_demand_notional
    investment_need = firm.investment_target * max(0.0, p_k_est)
    return max(0.0, wage_need + investment_need - deposits)


def credit_grant(requested: float, deposits: float, debt: float, kappa: float) -> float:
    """B7: the loan the bank grants (§12.4). Debt is capped at kappa·NW, NW=D−L
    (financial net worth). Returns additional credit this tick, in [0, requested].
    Insolvent (NW<=0) => 0. This one line is the whole Minsky-leverage engine."""
    nw = deposits - debt
    if nw <= 0.0:
        return 0.0
    room = kappa * nw - debt          # headroom above existing debt
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
