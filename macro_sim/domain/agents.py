"""Kernel agents: households and firms (spec §6.1, §7.1).

Money is NOT stored on the agent -- it lives in the Ledger, keyed by the agent's
``id`` (spec §7.6: agents have no direct write access to balances). Everything
here is the *non-money* state an agent carries across ticks: expectations, posted
prices/wages, inventory, and the cross-tick derived quantities that §8.1 warns
must be *persisted* rather than recomputed (recomputation risks the wrong vintage).

Behavioral parameters (alpha1, alpha2, mu, ...) are per-agent FIELDS even though
round-1 config sets them uniform, so heterogeneity later is a config change, not
a refactor (spec §7.6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from macro_sim.config import Config


@dataclass
class Household:
    id: str

    # -- per-agent behavioral parameters (uniform in round 1) --------------
    alpha1: float          # MPC out of expected income (B1)
    alpha2: float          # propensity out of wealth/deposits (B1)
    lambda_y: float        # income-expectation adjustment speed (B2)

    # -- state carried across ticks (§7.1) ---------------------------------
    y_expected: float      # Y^e_h : expected income (wages + dividends)

    # -- within/cross-tick derived (persisted, not recomputed) -------------
    income_realized: float = 0.0   # Y_{h,t}: wages + dividends received THIS tick
    consumption_budget: float = 0.0  # C_{h,t}: desired nominal budget (B1), pre-rationing
    spent: float = 0.0             # realized goods spending this tick (<= budget, <= deposits)
    necessity_spent: float = 0.0   # v18.1: of `spent`, the part on necessities (0 when split off)

    # -- v6 capital market (choice 乙): equity holdings + smoothed equity wealth --------
    shares: float = 0.0            # units of the aggregate equity index held (NOT money; v6 mode)
    equity_value_ema: float = 0.0  # smoothed equity value feeding B1 consumption (blast-radius
                                   # throttle: consume out of slow-moving, not bubble-spiking, wealth)
    # -- v6.1 per-firm equity: a sparse portfolio + the watchlist it actively trades ----
    holdings: dict = field(default_factory=dict)   # firm_id -> shares held (sparse)
    watchlist: list = field(default_factory=list)  # firm_ids this household trades (incl. its own)
    margin_debt: float = 0.0       # v8: equity-collateralised debt (subset of ledger debt; interest-only)
    labor_sold: float = 0.0        # v9: labor units hired THIS tick (of the 1.0 supplied); 1-this = unemployed frac
    jg_labor: float = 0.0          # v9.3: labor units taken by the job guarantee this tick (buffer stock)
    energy_spent: float = 0.0      # v17.1: household energy outlay this tick (consumption GDP)
    energy_units: float = 0.0      # v17.1: energy units bought = consumed this tick (no storage)

    @classmethod
    def create(cls, idx: int, cfg: Config) -> "Household":
        return cls(
            id=f"H{idx}",
            alpha1=cfg.alpha1,
            alpha2=cfg.alpha2,
            lambda_y=cfg.lambda_y,
            y_expected=0.0,  # tick-0 cold start: no history -> expect 0, first-tick
                             # consumption is driven purely by alpha2 * deposits (§8.1).
        )


@dataclass
class Firm:
    id: str

    # -- per-agent behavioral parameters (uniform in round 1) --------------
    lambda_d: float        # demand-expectation adjustment speed (B2)
    phi: float             # target inventory / expected demand
    eta: float             # markup adjustment step (B3)
    mu_min: float          # markup lower bound
    mu_max: float          # markup upper bound
    omega: float           # wage-raise step on shortage (B4)
    a: float               # labor productivity (units/worker/tick)
    rho: float             # dividend payout ratio

    # -- state carried across ticks (§7.1) ---------------------------------
    inventory: float       # I_f : real good held (an outside item, NOT in ledger)
    price: float           # p_f : posted price
    wage: float            # w_f : posted wage
    markup: float          # mu_f
    demand_expected: float  # d^e_f

    # -- cross-tick derived state that rules read (§8.1: must persist) -----
    target_inventory_prev: float = 0.0   # I*_{f,t-1}: for the markup sign signal (B3)
    labor_demand_eff_prev: float = 0.0   # N^{d,eff}_{f,t-1}: for rationing detection (B4)
    hired_prev: float = 0.0              # N_{f,t-1}: realized hiring last tick (B4)
    sales_prev: float = 0.0              # sales_{f,t-1}: feeds demand expectation (B2)
    # v16-L6 footfall: share of UNMET buyer demand (order-book signal; keeps demand
    # observable at zero inventory). Enters B2 alongside sales, NEVER revenue.
    # Both identically 0.0 with the flag off (bit-identical: x + 0.0 == x).
    rationed_demand: float = 0.0
    rationed_prev: float = 0.0
    subscale_ticks: int = 0              # v16-L6: consecutive ticks below the viability line

    # -- within-tick scratch (recomputed each tick) ------------------------
    target_inventory: float = 0.0        # I*_{f,t}
    production_target: float = 0.0       # y*_{f,t}
    labor_demand_notional: float = 0.0   # N^d_{f,t}: pre-cash-cap (used for uc, §1.5)
    labor_demand_eff: float = 0.0        # N^{d,eff}_{f,t}: notional demand capped by cash
    hired: float = 0.0                   # N_{f,t}: realized hiring
    produced: float = 0.0                # y_{f,t}: output added to inventory
    sales: float = 0.0                   # units sold this tick
    revenue: float = 0.0                 # p_f * sales
    wagebill: float = 0.0                # w_f * hired
    profit: float = 0.0                  # revenue - wagebill
    dividend_shortfall: float = 0.0      # dividends owed but cash-capped (A4, §1.1)

    # ======================================================================
    # v2 -- sector attributes + capital (DESIGNDOC §10). Defaults reproduce a
    # v1 kernel firm (linear tech, sells consumption, no investment, no capital),
    # so the v1 code path is bit-identical (PLAN_v2 §0, Option A).
    # ======================================================================
    sells: str = "consumption"           # "consumption" | "capital"
    # v18.1 consumption sub-sector. "" = undifferentiated (the single-good default, keeps
    # all consumption logic bit-identical); "necessity" | "luxury" when the split is on.
    # sells stays "consumption" for both so every existing consumption code path works.
    consumption_sector: str = ""
    tech: str = "linear"                 # "linear" (y=a N) | "cobb_douglas" (y=A K^α N^{1-α})
    invests: bool = False                # only C-firms invest (B5)
    A: float = 1.0                       # TFP (Cobb-Douglas)
    alpha: float = 0.3                   # capital share (Cobb-Douglas)
    v: float = 0.0                       # desired capital-output ratio (B5)
    lambda_I: float = 0.0                # investment adjustment speed (B5)
    delta_K: float = 0.0                 # capital depreciation rate
    dis_slope: float = 0.0               # v5: coordination-cost slope, uc *= (1 + dis_slope*y*)

    capital: float = 0.0                 # K_f: physical capital (real, NOT money/ledger).
                                         # Holds K_{t-1} through the tick; committed to K_t in Phase 4.
    capital_prev: float = 0.0            # K_{f,t-1} snapshot at commit (for the law-of-motion test)
    investment_target: float = 0.0       # I*_{f,t}: notional capital-good demand (B5)
    investment: float = 0.0              # I_{f,t}: realized capital purchased this tick
    insolvent_ticks: int = 0             # v4: consecutive ticks with D-L<0 (bankruptcy counter)
    idle_ticks: int = 0                  # v13: consecutive ticks with no production and no sales (shell-exit counter)

    # v6.1 per-firm equity (DESIGNDOC §18). Each firm is separately traded/valued.
    shares_outstanding: float = 0.0      # this firm's fixed share float (0 = not equitized)
    share_price: float = 1.0             # p_f: per-firm index price (gropes each tick)
    share_last_price: float = 1.0        # previous price (return/trend signal)
    share_trend: float = 0.0             # adaptive momentum of this firm's return (chartist)
    equity_fundamental: float = 0.0      # per-share fundamental (floored residual income)
    residual_income_ema: float = 0.0     # smoothed (π − r·book): the growth-premium driver
    tobin_q: float = 1.0                 # market cap / book (per-firm valuation)
    tobin_q_ema: float = 1.0             # v8.3: SMOOTHED q that actually drives investment (firms
                                         # ignore transient mispricing); == tobin_q when q_invest_smooth=1

    attractiveness: float = 1.0          # v8.1: market-share weight (Gibrat random walk); goods demand
                                         # is allocated ∝ attractiveness^β. NOT money, not in any conservation.

    # v17.0 energy (PLAN_v17). Defaults are inert: capacity_kappa=0 = no capacity edge;
    # energy_intensity=0 = no energy input. Stocks are OUTSIDE items (like inventory):
    # A4/A5 blind, average-cost valuation for the B3 unit cost.
    capacity_kappa: float = 0.0          # >0 (E-firms): output capped at κ·K (the capacity edge)
    energy_intensity: float = 0.0        # e: energy units per output unit (c/k firms when energy on)
    energy_stock: float = 0.0            # input inventory (energy units held for production)
    energy_stock_cost: float = 0.0       # cost basis of the stock (average-cost valuation)
    energy_avg_cost: float = 0.0         # hold-last avg cost per unit (feeds the B3 unit cost)
    energy_used: float = 0.0             # scratch: energy consumed in production this tick
    energy_cost_used: float = 0.0        # scratch: cost of energy consumed (enters profit)
    energy_bought: float = 0.0           # scratch: units bought this tick (restock-share gauge)
    state_owned: bool = False            # v17.3: SOE flag (dividends -> fiscal; optional at-cost pricing)

    @classmethod
    def create(cls, idx: int, cfg: Config) -> "Firm":
        return cls(
            id=f"F{idx}",
            lambda_d=cfg.lambda_d,
            phi=cfg.phi,
            eta=cfg.eta,
            mu_min=cfg.mu_min,
            mu_max=cfg.mu_max,
            omega=cfg.omega,
            a=cfg.a,
            rho=cfg.rho, dis_slope=cfg.dis_slope,
            inventory=cfg.inv_firm0,
            price=cfg.p_firm0,
            wage=cfg.w_firm0,
            markup=cfg.mu_firm0,
            demand_expected=cfg.demand_e_firm0,
            # tick-0 cold start (§8.1, feedback point 3), centralized here:
            #  - no I*_{t-1} yet -> seed with target implied by initial d^e so the
            #    first markup signal is well-defined (sign(I*_prev - inv0)).
            target_inventory_prev=cfg.phi * cfg.demand_e_firm0,
            #  - no prior hiring/rationing -> default "not rationed" so the wage
            #    rule does NOT raise on the first tick.
            labor_demand_eff_prev=0.0,
            hired_prev=0.0,
            #  - no sales history -> seed sales_prev = initial expected demand so the
            #    tick-0 B2 update is a neutral no-op (d^e stays at its seed), rather
            #    than being yanked toward 0 by a spurious "zero sales" reading (§8.1).
            sales_prev=cfg.demand_e_firm0,
        )

    # ----------------------------------------------------------------------
    # v2 factories (DESIGNDOC §10). Both share the kernel behavioral core;
    # they differ only in tech / good / buyer / whether they invest (§10.2).
    # ----------------------------------------------------------------------
    @classmethod
    def create_c_firm(cls, idx: int, cfg: Config) -> "Firm":
        """Consumption-goods firm: Cobb-Douglas y = A K^α N^{1-α}, invests (B5)."""
        return cls(
            id=f"C{idx}",
            lambda_d=cfg.lambda_d, phi=cfg.phi, eta=cfg.eta,
            mu_min=cfg.mu_min, mu_max=cfg.mu_max, omega=cfg.omega,
            a=cfg.a, rho=cfg.rho, dis_slope=cfg.dis_slope,
            inventory=cfg.inv_firm0, price=cfg.p_firm0, wage=cfg.w_firm0,
            markup=cfg.mu_firm0, demand_expected=cfg.demand_e_firm0,
            target_inventory_prev=cfg.phi * cfg.demand_e_firm0,
            sales_prev=cfg.demand_e_firm0,
            sells="consumption", tech="cobb_douglas", invests=True,
            A=cfg.A, alpha=cfg.alpha, v=cfg.v, lambda_I=cfg.lambda_I, delta_K=cfg.delta_K,
            capital=cfg.K_firm0, capital_prev=cfg.K_firm0,   # K_{-1}=K_0 seeds first investment gap
        )

    @classmethod
    def create_k_firm(cls, idx: int, cfg: Config) -> "Firm":
        """Capital-goods firm: labor-only y = a_K N, sells capital, does not invest.

        Cold start (PLAN_v2 §1.2): with no history, seed expected capital-good demand
        from a rough aggregate initial-investment estimate spread over K-firms, so B_K
        (the cure channel) is not dead on tick 1. Marked transient; verify it washes out.
        """
        d_seed = _k_demand_seed(cfg)
        # v2.5 (symmetric_k): K-firms also use capital (Cobb-Douglas) and invest,
        # so their retained earnings get an outlet (§11.4). v2: labor-only, no invest.
        sym = cfg.symmetric_k
        return cls(
            id=f"K{idx}",
            lambda_d=cfg.lambda_d, phi=cfg.phi, eta=cfg.eta,
            mu_min=cfg.mu_min, mu_max=cfg.mu_max, omega=cfg.omega,
            a=cfg.a_K, rho=cfg.rho, dis_slope=cfg.dis_slope,
            inventory=cfg.inv_kfirm0, price=cfg.p_kfirm0, wage=cfg.w_firm0,
            markup=cfg.mu_firm0, demand_expected=d_seed,
            target_inventory_prev=cfg.phi * d_seed,
            sales_prev=d_seed,                              # neutral first B2 update
            sells="capital",
            tech="cobb_douglas" if sym else "linear",
            invests=sym,
            A=cfg.A, alpha=cfg.alpha,
            v=(cfg.v if sym else 0.0), lambda_I=(cfg.lambda_I if sym else 0.0),
            delta_K=(cfg.delta_K if sym else 0.0),
            capital=(cfg.K_firm0 if sym else 0.0),
            capital_prev=(cfg.K_firm0 if sym else 0.0),
        )


@dataclass
class Bank:
    """The single v3 bank (DESIGNDOC §12). Money is in the ledger (its own deposits
    from retained interest); loan assets = the borrowers' debts (also in the ledger).
    This holds only the non-ledger state: reserves (the conserved M it carries, §A5;
    documented, not load-bearing) and per-tick interest bookkeeping.
    """
    id: str = "BANK"
    rho: float = 0.5               # payout ratio of profit (interest income), like a firm
    reserves: float = 0.0          # base money it holds so ΣR = M (set by economy at genesis)
    interest_income: float = 0.0   # interest received this tick (scratch)
    profit: float = 0.0            # = interest_income (no operating costs in minimal v3)
    kappa_bank: float = 10.0       # v11: leverage cap (loan_book ≤ κ_bank·capital) -- risk appetite
    alive: bool = True             # v11: False once insolvent + resolved (removed from lending)
    # v11.5: the bank is OWNED (equity). Shares held by households; profit → dividends to owners; a valuation
    # (mark-to-model, then traded) that also serves as a run distress signal. `owners`: household_id → shares.
    shares_outstanding: float = 0.0
    share_price: float = 0.0
    share_last_price: float = 0.0
    earnings_ema: float = 0.0      # smoothed net profit, for the Gordon-style valuation premium
    owners: dict = None            # household_id -> shares (set at genesis / on de-novo founding)
    share_peak: float = 0.0        # v11.5 runs: recent peak price (the market health signal is price/peak)
    share_trend: float = 0.0       # v11.5 A2: adaptive return momentum (chartist demand → bubbles/crashes)

    @classmethod
    def create(cls, cfg: Config) -> "Bank":
        return cls(id="BANK", rho=cfg.rho)


@dataclass
class EquityMarket:
    """The single v6 aggregate equity index (DESIGNDOC §16). One traded asset = a claim on
    total C-firm net worth. Holds only non-ledger market state: the price (which gropes on
    excess demand -- no auctioneer), the fixed share float, and the fundamental/trend signals.
    Shares live on households (Household.shares); money moves through the ordinary ledger."""
    float_shares: float                 # total index units (fixed in v6; issuance -> v6.1)
    price: float = 1.0                  # p_S: index price (gropes each tick)
    last_price: float = 1.0             # previous price (for the return / trend signal)
    book_value: float = 0.0             # Σ C-firm net worth (recomputed each tick)
    fundamental: float = 0.0            # value per share = smoothed dividend / r (Gordon, g=0)
    dividend_ema: float = 0.0           # smoothed aggregate dividend (feeds the fundamental)
    trend: float = 0.0                  # adaptive momentum of index returns (chartist signal)
    # per-tick scratch (metrics)
    executed_volume: float = 0.0        # units traded this tick
    excess_demand: float = 0.0          # (desired buy - desired sell)/float (drives price)

    @classmethod
    def create(cls, cfg: Config) -> "EquityMarket":
        return cls(float_shares=cfg.float_shares)


def _k_demand_seed(cfg: Config) -> float:
    """Rough aggregate initial capital-good demand per K-firm (PLAN_v2 §1.2, transient).

    Per C-firm initial investment I*_0 = max(0, λ_I(v·y^e_{C,0} − K_0) + δ_K K_0);
    summed over C-firms and split across K-firms.
    """
    ye_c0 = cfg.demand_e_firm0
    i_star_per_c = max(0.0, cfg.lambda_I * (cfg.v * ye_c0 - cfg.K_firm0) + cfg.delta_K * cfg.K_firm0)
    total = i_star_per_c * cfg.n_firms_c
    return total / max(1, cfg.n_firms_k)
