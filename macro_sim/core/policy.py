"""The government's LIVE policy levers (PLAN_v9 §1).

The essential v9 distinction: **`Policy` is the only state mutable DURING a run** — the government's
control surface — while everything in `Config` is frozen at t=0. `Policy` is initialised from `Config`
and (later) updated each tick by a `policy_fn` (default: constant anchored rates ⇒ flows auto-
countercyclical; future: a scripted scenario / human player / RL agent — the interactive layer).

When `government=False` the fiscal levers are 0 and the macroprudential levers equal their `Config`
defaults, so reading them from `Policy` is bit-identical to reading them from `Config` (v8.5 baseline).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Policy:
    # -- fiscal: spending -------------------------------------------------
    gov_consumption_share: float = 0.0   # g: real gov demand = g · potential_output (quantity mode)
    gov_deficit_target: float = 0.0      # if >0: size gov consumption to maintain a deficit of this · GDP
    deficit_u_ref: float = 0.0           # if >0: state-dependent deficit -- scale target by min(1, u/this)
    benefit_replacement: float = 0.0     # b: unemployment benefit = b · wage_ref
    # v23 IN-WORK SUPPORT (a minimum income guarantee). The unemployment benefit above pays for
    # UNSOLD LABOUR (supply - labor_sold - jg_labor): it is a QUANTITY rule. It insures the
    # jobless and is completely blind to a worker who sells ALL of their labour and still earns
    # too little. v16-L4 then made earnings dispersed (pay = wage x e_i, sigma = 0.35), so the
    # model now MANUFACTURES working poor -- but this v9 safety net was designed before person
    # efficiency existed and was never updated for it.
    #
    # The last CRITICAL (welfare.deprivation_domain_boundary) is exactly that hole: the destitute
    # household is a 40-year-old working a FULL 1.0 FTE, earning 56% of median income with 0.07
    # in deposits against a median of 863, and receiving ZERO support -- because they have a job.
    #
    # This lever tops household income up to `income_floor x wage_ref x labour_supply`,
    # REGARDLESS of employment status. 0.0 => the branch never fires => bit-identical.
    benefit_income_floor: float = 0.0
    pension_replacement: float = 0.0     # v13: old-age pension per elder = this · wage_ref (0 = off)

    # -- fiscal: revenue (four tax bases) ---------------------------------
    tax_profit_rate: float = 0.0         # τ_π on positive firm profit (pre-dividend)
    tax_income_rate: float = 0.0         # τ_y on household labour+dividend income
    income_allowance: float = 0.0        # a_x: personal allowance as a fraction of mean income (progressivity)
    tax_consumption_rate: float = 0.0    # τ_c: VAT on goods purchases
    # v18.3 differential VAT (live levers; None ⇒ fall back to τ_c ⇒ bit-identical). Only
    # bind when the consumption split is on. Zero-rating necessities (tax_necessity_rate=0
    # while τ_c>0) is the classic progressive instrument -- the §34 reprise on the
    # consumption side.
    tax_necessity_rate: "float | None" = None
    tax_luxury_rate: "float | None" = None
    tax_wealth_rate: float = 0.0         # τ_w on household net worth (the stock)
    wealth_allowance: float = 0.0        # progressive wealth-tax exemption as a multiple of mean net worth
    tax_energy_rate: float = 0.0         # v17.0: excise on energy purchases (VAT grammar; inert at 0)
    tax_energy_windfall: float = 0.0     # v17.2: profit surtax on E-firms (shock-response instrument)
    spr_target_units: float = 0.0        # v17.3: strategic-reserve stock target (0 = off)
    spr_flow_cap: float = 0.0            # v17.3: max SPR units traded per tick
    soe_price_at_cost: bool = False      # v17.3: the state-owned E-firm prices at unit cost
    energy_price_cap: float = 0.0        # v17.4: market asks clamped at the cap (0 = off)
    energy_rationing: str = "market"     # v17.4: who is cut under shortage (see Config)
    energy_cap_compensation: bool = False  # v17.4: fiscal covers the cap's revenue gap
    energy_subsidy_rate: float = 0.0     # v17.5: rebate share of household energy bills
    energy_subsidy_threshold: float = 0.0  # v17.5: 0 = flat; >0 = deposits-targeted (x mean)

    # -- labour -----------------------------------------------------------
    min_wage: float = 0.0                # wage floor (0 = off)
    job_guarantee: bool = False          # v9.3: uncapped employer of last resort (buffer-stock employment)
    jg_wage_ratio: float = 0.0           # JG wage = this · mean private wage (transitional floor wage)

    # -- monetary (v10 central bank; the rate-rule dials, off => frozen r_interest) --
    central_bank: bool = False           # v10: master switch (rate becomes endogenous)
    inflation_target: float = 0.0        # π*: per-tick inflation target
    taylor_phi_pi: float = 1.5           # φ_π: inflation response (>1 = Taylor principle)
    taylor_phi_u: float = 0.5            # φ_u: unemployment-gap response (0 = pure inflation targeter)
    rate_inertia: float = 0.8            # ρ: rate smoothing / gradualism
    policy_rate_override: "float | None" = None  # if set, the CB uses THIS rate directly (a hand-set hike/cut by
    #                                              the player), bypassing the Taylor rule; None ⇒ the rule decides

    # -- monetary: quantity tools (v12.4 CB; the OMO/QE + LoLR live control surface) --
    # -- monetary: the CB's beliefs & measurement apparatus (B4c migration; the CB
    #    chooses its estimates and its index -- the Germany lesson made this policy) --
    r_neutral: float = 0.01              # r*: the CB's neutral-rate estimate
    u_natural: float = 0.05              # u*: the CB's natural-rate estimate
    r_max: float = 0.10                  # rate ceiling (the cap that disarmed CBs in the v1 portrait)
    infl_ema_lambda: float = 0.02        # the CB's inflation-sensor smoothing
    cb_core_inflation: bool = False      # Taylor input reads CORE (ex-energy)
    cb_uses_fixed_basket_cpi: bool = False  # the CB's target-index choice
    cb_log_inflation: bool = False       # ln(P/P') instead of P/P'-1
    fiscal_uses_national_accounts_gdp: bool = False  # the FISCAL RULE's GDP-measure choice

    # -- Treasury debt management (B4d) --
    bond_finance_frac: float = 0.0       # share of the deficit financed by issuance
    bond_coupon: float = 0.0             # coupon for NEW issues (per-lot cohort; stock never re-couponed)
    bond_maturity: int = 1               # tenor for NEW issues

    omo: bool = False                    # open-market operations on/off (the CB steers reserves)
    omo_reserve_target: float = 0.0      # QE/QT stance: target Σ bank reserves as a FRACTION of genesis reserves
    omo_drain_frac: float = 0.1          # per-tick fraction of the gap to the target moved (drain/inject speed)
    lolr: bool = False                   # lender of last resort on/off (fund an illiquid-but-solvent bank in a run)

    # -- macroprudential: banks (B4a migration) --
    bank_capital_constraint: bool = False   # enforce the per-bank leverage gate (regime)
    bank_leverage_cap: float = 0.0          # [N] regulatory ceiling on kappa_bank (0 = off)
    bank_target_capital_ratio: float = 0.0  # payout above ratio*loan_book
    bank_exposure_limit: float = 0.0        # single borrower <= limit*capital
    bank_min_capital: float = 0.0           # charter gate for de-novo entry
    bank_bond_duration_limit: float = 0.0   # bond book <= k*economic_capital (SVB floor)
    bank_resolution_fund: bool = False      # state absorbs failed-bank residual (regime)
    reserve_floor_frac: float = 0.0         # intraday reserve floor vs deposits

    # -- macroprudential (reclassified from Config; defaults preserve v8.5) --
    margin_ltv: float = 0.5              # household margin loan-to-value cap
    margin_max: float = 2.0              # household equity-leverage ceiling
    kappa: float = 3.0                   # firm credit leverage multiple L^max = κ·NW
    hh_credit_limit: float = 2.0         # household debt-to-income (DTI) cap

    # -- macroprudential: mortgage regulation (B4b migration; all flow through
    #    MortgageBook._sync_policy each session -- the B2 anti-snapshot channel) --
    mortgage_underwriting: bool = False
    mortgage_dsti_cap: float = 0.45
    mortgage_stress_rate_addon: float = 0.02 / 365.0
    mortgage_risk_weight: float = 0.35
    mortgage_min_capital_ratio: float = 0.08
    mortgage_foreclosure_ltv: float = 1.1
    mortgage_arrears_floor: float = 2.0

    # -- v15.5 housing handles (live levers; seeded from Config) --
    mortgage_ltv_cap: float = 0.8        # owner-occupier mortgage LTV (macroprudential)
    housing_permits: int = 50            # dwellings mintable per year (zoning)
    housing_transfer_tax: float = 0.0    # stamp duty on sale price -> fiscal
    housing_property_tax: float = 0.0    # annual rate on dwelling value -> fiscal
    housing_in_wealth_tax: bool = False  # include dwelling value in the wealth-tax base

    @classmethod
    def from_config(cls, cfg) -> "Policy":
        """Seed the live levers from the frozen config (their t=0 stance)."""
        return cls(
            gov_consumption_share=cfg.gov_consumption_share,
            gov_deficit_target=cfg.gov_deficit_target,
            deficit_u_ref=cfg.deficit_u_ref,
            benefit_replacement=cfg.benefit_replacement,
            benefit_income_floor=cfg.benefit_income_floor,
            pension_replacement=getattr(cfg, 'pension_replacement', 0.0),
            tax_profit_rate=cfg.tax_profit_rate,
            tax_income_rate=cfg.tax_income_rate,
            income_allowance=cfg.income_allowance,
            tax_consumption_rate=cfg.tax_consumption_rate,
            tax_wealth_rate=cfg.tax_wealth_rate,
            wealth_allowance=cfg.wealth_allowance,
            tax_energy_rate=getattr(cfg, "tax_energy_rate", 0.0),
            tax_energy_windfall=getattr(cfg, "tax_energy_windfall", 0.0),
            spr_target_units=getattr(cfg, "spr_target_units", 0.0),
            spr_flow_cap=getattr(cfg, "spr_flow_cap", 0.0),
            soe_price_at_cost=getattr(cfg, "soe_price_at_cost", False),
            energy_price_cap=getattr(cfg, "energy_price_cap", 0.0),
            energy_rationing=getattr(cfg, "energy_rationing", "market"),
            energy_cap_compensation=getattr(cfg, "energy_cap_compensation", False),
            energy_subsidy_rate=getattr(cfg, "energy_subsidy_rate", 0.0),
            energy_subsidy_threshold=getattr(cfg, "energy_subsidy_threshold", 0.0),
            min_wage=cfg.min_wage,
            job_guarantee=cfg.job_guarantee,
            jg_wage_ratio=cfg.jg_wage_ratio,
            central_bank=cfg.central_bank,
            inflation_target=cfg.inflation_target,
            taylor_phi_pi=cfg.taylor_phi_pi,
            taylor_phi_u=cfg.taylor_phi_u,
            rate_inertia=cfg.rate_inertia,
            # policy_rate_override stays None at t=0 (no hand-set rate until the player sets one)
            r_neutral=getattr(cfg, "r_neutral", 0.01),
            u_natural=getattr(cfg, "u_natural", 0.05),
            r_max=getattr(cfg, "r_max", 0.10),
            infl_ema_lambda=getattr(cfg, "infl_ema_lambda", 0.02),
            cb_core_inflation=getattr(cfg, "cb_core_inflation", False),
            cb_uses_fixed_basket_cpi=getattr(cfg, "cb_uses_fixed_basket_cpi", False),
            cb_log_inflation=getattr(cfg, "cb_log_inflation", False),
            fiscal_uses_national_accounts_gdp=getattr(cfg, "fiscal_uses_national_accounts_gdp", False),
            bond_finance_frac=getattr(cfg, "bond_finance_frac", 0.0),
            bond_coupon=getattr(cfg, "bond_coupon", 0.0),
            bond_maturity=getattr(cfg, "bond_maturity", 1),
            omo=cfg.omo,
            omo_reserve_target=cfg.omo_reserve_target,
            omo_drain_frac=cfg.omo_drain_frac,
            lolr=cfg.lolr,
            bank_capital_constraint=getattr(cfg, "bank_capital_constraint", False),
            bank_target_capital_ratio=getattr(cfg, "bank_target_capital_ratio", 0.0),
            bank_exposure_limit=getattr(cfg, "bank_exposure_limit", 0.0),
            bank_min_capital=getattr(cfg, "bank_min_capital", 0.0),
            bank_bond_duration_limit=getattr(cfg, "bank_bond_duration_limit", 0.0),
            bank_resolution_fund=getattr(cfg, "bank_resolution_fund", False),
            reserve_floor_frac=getattr(cfg, "reserve_floor_frac", 0.0),
            # bank_leverage_cap is [N]: no legacy Config source, seeds 0.0 (off)
            margin_ltv=cfg.margin_ltv,
            margin_max=cfg.margin_max,
            kappa=cfg.kappa,
            hh_credit_limit=cfg.hh_credit_limit,
            mortgage_ltv_cap=getattr(cfg, "mortgage_ltv_cap", 0.8),
            mortgage_underwriting=getattr(cfg, "mortgage_underwriting", False),
            mortgage_dsti_cap=getattr(cfg, "mortgage_dsti_cap", 0.45),
            mortgage_stress_rate_addon=getattr(cfg, "mortgage_stress_rate_addon", 0.02 / 365.0),
            mortgage_risk_weight=getattr(cfg, "mortgage_risk_weight", 0.35),
            mortgage_min_capital_ratio=getattr(cfg, "mortgage_min_capital_ratio", 0.08),
            mortgage_foreclosure_ltv=getattr(cfg, "mortgage_foreclosure_ltv", 1.1),
            mortgage_arrears_floor=getattr(cfg, "mortgage_arrears_floor", 2.0),
            housing_permits=getattr(cfg, "housing_permits", 50),
            housing_transfer_tax=getattr(cfg, "housing_transfer_tax", 0.0),
            housing_property_tax=getattr(cfg, "housing_property_tax", 0.0),
            housing_in_wealth_tax=getattr(cfg, "housing_in_wealth_tax", False),
        )
