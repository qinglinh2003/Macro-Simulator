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

    # -- fiscal: revenue (four tax bases) ---------------------------------
    tax_profit_rate: float = 0.0         # τ_π on positive firm profit (pre-dividend)
    tax_income_rate: float = 0.0         # τ_y on household labour+dividend income
    income_allowance: float = 0.0        # a_x: personal allowance as a fraction of mean income (progressivity)
    tax_consumption_rate: float = 0.0    # τ_c: VAT on goods purchases
    tax_wealth_rate: float = 0.0         # τ_w on household net worth (the stock)
    wealth_allowance: float = 0.0        # progressive wealth-tax exemption as a multiple of mean net worth

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
    omo: bool = False                    # open-market operations on/off (the CB steers reserves)
    omo_reserve_target: float = 0.0      # QE/QT stance: target Σ bank reserves as a FRACTION of genesis reserves
    omo_drain_frac: float = 0.1          # per-tick fraction of the gap to the target moved (drain/inject speed)
    lolr: bool = False                   # lender of last resort on/off (fund an illiquid-but-solvent bank in a run)

    # -- macroprudential (reclassified from Config; defaults preserve v8.5) --
    margin_ltv: float = 0.5              # household margin loan-to-value cap
    margin_max: float = 2.0              # household equity-leverage ceiling
    kappa: float = 3.0                   # firm credit leverage multiple L^max = κ·NW
    hh_credit_limit: float = 2.0         # household debt-to-income (DTI) cap

    @classmethod
    def from_config(cls, cfg) -> "Policy":
        """Seed the live levers from the frozen config (their t=0 stance)."""
        return cls(
            gov_consumption_share=cfg.gov_consumption_share,
            gov_deficit_target=cfg.gov_deficit_target,
            deficit_u_ref=cfg.deficit_u_ref,
            benefit_replacement=cfg.benefit_replacement,
            tax_profit_rate=cfg.tax_profit_rate,
            tax_income_rate=cfg.tax_income_rate,
            income_allowance=cfg.income_allowance,
            tax_consumption_rate=cfg.tax_consumption_rate,
            tax_wealth_rate=cfg.tax_wealth_rate,
            wealth_allowance=cfg.wealth_allowance,
            min_wage=cfg.min_wage,
            job_guarantee=cfg.job_guarantee,
            jg_wage_ratio=cfg.jg_wage_ratio,
            central_bank=cfg.central_bank,
            inflation_target=cfg.inflation_target,
            taylor_phi_pi=cfg.taylor_phi_pi,
            taylor_phi_u=cfg.taylor_phi_u,
            rate_inertia=cfg.rate_inertia,
            # policy_rate_override stays None at t=0 (no hand-set rate until the player sets one)
            omo=cfg.omo,
            omo_reserve_target=cfg.omo_reserve_target,
            omo_drain_frac=cfg.omo_drain_frac,
            lolr=cfg.lolr,
            margin_ltv=cfg.margin_ltv,
            margin_max=cfg.margin_max,
            kappa=cfg.kappa,
            hh_credit_limit=cfg.hh_credit_limit,
        )
