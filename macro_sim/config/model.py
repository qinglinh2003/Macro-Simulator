"""Canonical configuration model for the closed monetary kernel (spec §7.4).

Every free quantity lives here in ONE place so description length is visible and
the parsimony question (spec §0-iv) is forced on each row. Status legend:

  forced      -- pinned by an identity/axiom, not free (e.g. delta = 0, DNWR)
  anchored    -- has an empirical target to calibrate to
  scale       -- normalizable / a size knob; must not change stationary behavior
  transient   -- initial conditions; must wash out; verify
  FREE        -- a genuine behavioral dial to scrutinize / minimize

Round 1 sets every behavioral parameter to a single common value, but the values
are handed to *per-agent fields* (spec §7.6): enabling heterogeneity later is
swapping this config for a distribution, not a refactor.

Of ~18 knobs, only FIVE are genuinely free: phi, eta, mu_min, mu_max, omega.
That count is the parsimony target we protect (spec §7.4 read-out).
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field


def _cached_view(builder):
    """Build a grouped config view once and reuse it (perf).

    The view dataclasses are frozen snapshots of Config fields, and Config is frozen-by-
    discipline after t=0 (Policy is the only run-time-mutable state), so the first-access
    snapshot is the run's truth. Hot paths read views per call (e.g. bond valuation per
    lot); without the cache each access CONSTRUCTED a fresh frozen dataclass -- tens of
    thousands of builds per tick. The cache lives in __dict__ under a private key, which
    dataclass __eq__/__repr__ ignore.
    """
    key = "_view_" + builder.__name__

    @property
    @functools.wraps(builder)
    def prop(self):
        cached = self.__dict__.get(key)
        if cached is None:
            cached = builder(self)
            self.__dict__[key] = cached
        return cached

    return prop


@dataclass
class Config:
    # -- agent counts (scale: results must be robust above some threshold) --
    n_households: int = 100          # N_H  -- scale
    n_firms: int = 10                # N_F  -- scale

    # -- horizon & reproducibility -----------------------------------------
    n_ticks: int = 500
    seed: int = 0                    # single seed feeds ALL randomness (§7.6)

    # -- production (scale: a is a unit normalization) ---------------------
    a: float = 1.0                   # labor productivity, units/worker/tick -- scale

    # -- expectations (B2), anchored (softly) to expectation stickiness ----
    lambda_d: float = 0.3            # firm demand-expectation adjustment speed
    lambda_y: float = 0.3            # household income-expectation adjustment speed

    # -- inventory / production plan ---------------------------------------
    phi: float = 0.75                # target inventory / expected demand -- FREE

    # -- pricing (B3), cost-plus markup + Calvo stickiness -----------------
    eta: float = 0.05               # markup adjustment step -- FREE
    mu_min: float = 0.0             # markup lower bound -- FREE
    mu_max: float = 1.0             # markup upper bound -- FREE
    theta_price: float = 0.25       # reprice probability / tick -- anchored (Nakamura-Steinsson)

    # -- wages (B4), DNWR floor + raise-on-shortage ------------------------
    delta: float = 0.0              # downward wage flexibility -- FORCED (strict DNWR floor)
    # v23: B4 was PURELY a labour-tightness rule -- prices appear nowhere in it -- so the nominal
    # wage was anchored to nothing and the REAL wage was a free-floating residual. `delta` was
    # added in v13 to stop a DEFLATION ratcheting the real wage up, but that deflation was an
    # ARTEFACT of the capital-clock bug. With the clock fixed prices RISE, and with labour well
    # supplied the delta drift now pushes NOMINAL wages DOWN through an inflation (measured:
    # wage -0.5%/yr against prices +7.4%/yr; real wage -17%; households fall under the
    # subsistence basket). With indexation the tightness terms apply to the REAL wage and
    # committed expected inflation is the nominal baseline. 0.0 => bit-identical.
    wage_indexation: float = 0.0    # 0 = no price feedback (legacy); 1 = full indexation
    omega: float = 0.02             # wage-raise step on labor shortage -- FREE
    theta_wage: float = 0.15        # rewage probability / tick -- anchored (wage-rigidity data)

    # -- consumption (B1), choice (甲): V_h = D_h --------------------------
    alpha1: float = 0.8             # MPC out of expected income -- anchored; 0<alpha2<alpha1<1
    alpha2: float = 0.05            # propensity out of wealth (deposits) -- anchored
    demographics_enabled: bool = False  # v13 Phase 1: attach the demographic kernel to the economy
    demographics_population: int = 0    # 0 => seed one person per economic household account
    demographic_lifecycle_consumption: bool = False  # use finite-life household consumption budget
    lifecycle_alpha_income: float = 0.8
    lifecycle_alpha_wealth_draw: float = 1.0
    demographic_marriage_enabled: bool = True
    demographic_divorce_enabled: bool = True
    demographic_marriage_market_interval_days: int = 30
    demographic_annual_marriage_rate_peak: float = 0.30
    demographic_annual_divorce_rate_base: float = 0.012
    demographic_adult_leaving_home_enabled: bool = True
    demographic_leave_home_min_age: int = 22
    demographic_leave_home_peak_end_age: int = 30
    demographic_annual_leave_rate_peak: float = 0.25
    demographic_annual_leave_rate_late: float = 0.05
    # -- v14 Phase 2: macro -> vital-rate feedback (economy modulates fertility/mortality).
    # One shared signal (annual real wage: level x_t via 5y-EWMA/baseline, cycle z_t vs
    # pre-update EWMA), separately flag-gated channels. elasticity 0.0 = channel off and
    # bit-identical to the pre-feedback baseline. Multipliers are KERNEL-LEVEL scalars:
    # individual economic position never enters a hazard here (Phase 3 boundary).
    demo_feedback_burnin_years: int = 4       # genesis-transient years DISCARDED from the signal
                                              # (certified 10y replay: real wage ~3x over years 1-4
                                              # relaxing from arbitrary initial prices; the EWMA
                                              # must never smooth that slope into the baseline)
    demo_signal_halflife_years: float = 5.0   # EWMA half-life separating level from cycle
    fertility_income_elasticity: float = 0.0  # eps in F = clip(x^-eps, lo, hi); 0 = off -- FREE
    fertility_mult_lo: float = 0.5
    fertility_mult_hi: float = 1.5
    mortality_income_elasticity: float = 0.0  # gamma in M = clip(x^-gamma, lo, hi); 0 = off -- FREE
    mortality_mult_lo: float = 0.7
    mortality_mult_hi: float = 1.3
    # Per-country GENESIS vital rates. The multi-economy World bolted N economies together but
    # left the demographic kernel on its single hardcoded Phase0VitalRates() default, so every
    # economy shared ONE age pyramid -- "aging-rich vs young-developing" was inexpressible.
    # These wire the two rates that shape the pyramid into Config: create_genesis_population
    # derives the STABLE age distribution from them, so low TFR + low mortality => an OLD pyramid
    # and high TFR => a YOUNG one, and the same rates drive fertility/mortality over the run.
    # Defaults exactly match Phase0VitalRates() => a config that leaves them is bit-identical.
    demographics_tfr: float = 2.5             # total fertility rate (children/woman); pyramid youth
    demographics_mortality_scale: float = 1.0  # x on the Gompertz-Makeham hazard (>1 = shorter life)
    # Reconcile the person-claim layer to the household ledger every N ticks (0 = off = never mid-run
    # = bit-identical). Long, high-churn runs strand tiny cash-claim residues across household moves
    # that accumulate past CLAIM_TOL and trip the claims identity gate; periodic reconciliation
    # dissolves them by resetting each household's claims to its ledger balance (the source of truth).
    claims_reconcile_interval: int = 0
    # -- v14 Phase 3: rank-gradient strata (individual position -> individual hazard).
    # Bucket multiplier exp(beta*(0.5-rank)), EXPOSURE-weighted mean 1 (Phase 3 moves WHO,
    # Phase 2 moves HOW MANY). 0.0 = off = bit-identical. fertility gradient is SIGNED
    # (>0 modern negative gradient: poor households more children).
    mortality_rank_gradient: float = 0.0      # beta_m; production calibration ~0.8 -- FREE
    fertility_rank_gradient: float = 0.0      # beta_f, signed -- FREE
    strat_mult_lo: float = 0.5
    strat_mult_hi: float = 2.0
    marriage_assortativity: float = 0.0       # 3.3: years of age-mismatch per unit rank distance -- FREE
    # -- v15.0 housing: title registry + genesis endowment (frozen price, zero market).
    # A dwelling is a REAL asset in a registry, never money: A4/A5 are blind to it.
    housing_enabled: bool = False           # one homogeneous dwelling per genesis household
    house_price_income_years: float = 3.5   # frozen genesis valuation anchor (x annual wage income)
    # -- v15.1 resale market (posted asks, monthly sessions, cash-constrained regime).
    housing_market_enabled: bool = False    # requires housing_enabled
    housing_session_interval: int = 30      # matching cadence (marriage-market precedent)
    housing_ask_markup: float = 0.05        # voluntary ask over the reference price
    housing_forced_discount: float = 0.10   # probate/foreclosure asks under it
    housing_ask_decay: float = 0.03         # per-session cut while unsold
    housing_search_k: int = 5               # buyer sees the k cheapest listings
    housing_buyer_buffer: float = 0.25      # deposits share a buyer keeps
    housing_distress_floor: float = 5.0     # deposits below this list the home
    # -- v15.2 mortgages: ordinary non-margin household ledger debt (the certified credit
    # machinery amortizes it at hh_amort and charges the FLOATING loan rate -- monetary
    # transmission for free); the book only tracks collateralization + foreclosure.
    mortgage_enabled: bool = False          # requires housing_market_enabled
    mortgage_ltv_cap: float = 0.8           # macroprudential handle, live from day one
    mortgage_foreclosure_ltv: float = 1.1   # foreclose when secured balance > this x value
    mortgage_arrears_floor: float = 2.0     # ...AND deposits below this floor
    # Dedicated mortgage underwriting.  This is deliberately separate from the
    # corporate-loan gross-exposure cap: housing collateral receives its own risk
    # weight and competes for a bank-specific mortgage portfolio envelope.
    mortgage_underwriting: bool = False
    mortgage_dsti_cap: float = 0.45          # stressed per-tick debt service / qualifying income
    mortgage_stress_rate_addon: float = 0.02 / 365.0  # per-tick add-on (~2pp annual stress)
    mortgage_risk_weight: float = 0.35       # residential-mortgage RWA weight
    mortgage_min_capital_ratio: float = 0.08 # bank capital / mortgage RWA floor
    # One bank-wide risk-weighted lending envelope.  When enabled, ordinary
    # firm/consumer credit receives a 100% risk weight and secured mortgages use
    # ``mortgage_risk_weight``; both draw on the same capital / RWA limit.  The
    # historical gross-loan kappa and large-exposure gates remain additional caps.
    unified_bank_rwa: bool = False
    # -- v15.3 rental market: tenancies as persistent flows; rent level is an independent
    # market state (vacancy pressure cuts it, unhoused demand raises it); landlords
    # emerge from yield arbitrage (cash-only buy-to-let; leverage is a later flag).
    housing_rental_enabled: bool = False    # requires housing_market_enabled
    rent_yield0: float = 0.05               # genesis annual rent / price anchor
    rent_adjust: float = 0.02               # per-session rent-level step
    rent_burden_cap: float = 0.40           # tenant affordability cap vs realized income
    rental_eviction_arrears: int = 30       # consecutive shortfall ticks before eviction
    rental_investor_premium: float = 0.02   # buy-to-let when yield > deposit rate + premium
    # -- v15.4 construction: primary market + the long-run price anchor. Builders ride
    # the native firm grammar (B1/B2, labor market, settlement); scarcity comes from a
    # convex LAND FEE to the fiscal at minting and a yearly PERMIT quota (zoning handle).
    # -- v15.5 couplings: ONE affordability signal (annual, burn-in discard), per-channel
    # flags. Leave-home reads the rent burden (unaffordable rents delay leaving home =>
    # cohabitation); fertility (channel 2.1d) reads price-to-income (housing as the
    # child-rearing cost). 0.0 = channel off = bit-identical.
    housing_signal_burnin_years: int = 4
    housing_leave_elasticity: float = 0.0     # lambda in L = clip(burden^-lambda, lo, hi) -- FREE
    housing_leave_mult_lo: float = 0.5
    housing_leave_mult_hi: float = 1.5
    housing_fertility_elasticity: float = 0.0 # 2.1d eps in F = clip(pti^-eps, lo, hi) -- FREE
    housing_fertility_mult_lo: float = 0.5
    housing_fertility_mult_hi: float = 1.5
    housing_construction_enabled: bool = False   # requires housing_market_enabled
    n_builders: int = 5
    builder_productivity: float = 0.002     # dwelling units per labor-tick (~1.4 worker-years/unit)
    builder_demand_seed: float = 0.005      # cold-start expected dwelling demand per tick
    land_fee_share: float = 0.2             # land fee = share x price x (stock/stock0)^convexity
    land_convexity: float = 1.0
    housing_permits: int = 50               # dwellings mintable per year (zoning quota; live Policy lever)
    # -- v15.5 policy handles + wealth-effect flag (all default off = bit-identical)
    housing_transfer_tax: float = 0.0       # stamp duty on sale price -> fiscal (live lever)
    housing_property_tax: float = 0.0       # annual rate on dwelling value -> fiscal (live lever)
    housing_in_wealth_tax: bool = False     # include dwellings in the wealth-tax base (live lever)
    housing_wealth_effect: float = 0.0      # housing value weight in the consumption wealth term
                                            # (empirically WEAK vs financial wealth; the honest
                                            # default is the emergent down-payment effect) -- FREE
    # -- v16-L0 labor accounting: the five-state taxonomy (E/U/S/JG/OLF), aggregate
    # stocks, vacancy stock, and the per-tick stock identity HARD GATE (the labor A5).
    # Pure observation under the spot market; rosters make the states real at L1.
    labor_accounting: bool = True
    # -- v16-L1: persistent person-level rosters. "spot" (default) keeps the certified
    # daily market verbatim; "persistent" attaches employment to PERSONS with four
    # separation classes and adjustment dynamics (labor hoarding -> Okun).
    labor_matching: str = "spot"
    # Optional intensive margin for persistent jobs. A private Job remains a
    # one-person/one-firm relationship but may carry fractional daily hours; JG and
    # benefits fill the person's residual labor supply. Off preserves the certified
    # whole-person path and its random stream exactly.
    labor_fractional_hours: bool = False
    # v23 P0: with one Job per person, greedy per-firm allocation leaves a part-time MARGINAL
    # worker at every firm whose residual hours are UNSELLABLE -- measured 13-24 FTE idle while
    # firms posted 180-235 vacancies, the residue draining into the job guarantee (fill 85.7%,
    # JG 11.7%). The resulting production shortfall ratcheted the B3 markup into runaway
    # inflation. labor_second_job lets a firm buy a part-timer's unsold hours as ONE additional
    # contract at a DIFFERENT firm, capped so nobody sells more than 1.0 FTE in total.
    labor_second_job: bool = False
    churn_annual: float = 0.28              # exogenous quits + individual dismissals (~2.4%/mo)
    lambda_fire: float = 0.03               # per-tick closure of the layoff gap (hoarding dial)
    layoff_band: float = 0.05               # hysteresis band as a fraction of target headcount
    layoff_target_smooth: float = 0.02      # daily EMA on the firing target (hire fast, fire slow)
    # -- v16-L1b suspension: the employment LOLR. Cash-crunched firms SUSPEND (LIFO)
    # instead of firing: match kept, no pay, no debt; recall in place within the timer,
    # else auto-layoff. Suspended workers search as recall unemployment (accept an
    # offer iff wage >= quit_discount x suspended wage).
    labor_suspension: bool = False
    suspension_timer: int = 45
    suspension_quit_discount: float = 0.9
    # -- v16-L2 matching friction: hiring through contacts; u* is born here and the
    # JG becomes a searchable buffer (JG workers hold no Job link => searchers by
    # construction). search intensity ~0.15/day => mean unemployment ~2 months.
    labor_matching_friction: bool = False
    job_search_intensity: float = 0.15
    # -- v16-L3 relationship wages (the pass-through prize) + L3b job ladder.
    labor_relationship_wages: bool = False
    labor_job_ladder: bool = False
    ladder_search_intensity: float = 0.03
    ladder_premium: float = 0.05
    # -- v16-L4 person efficiency: the human-capital slot. e_i ~ lognormal MEAN ONE,
    # drawn once at FIRST hire (dedicated substream seed+16_002); earnings = wage x e_i
    # (wage_of is the single authority -- every cash gate prices it); f.hired counts
    # EFFICIENCY UNITS (feeds production); labor_sold counts heads on the legacy
    # path and FTE hours when labor_fractional_hours is enabled (feeds JG/welfare).
    labor_person_efficiency: bool = False
    efficiency_sigma: float = 0.35
    # -- v16-L5 participation margin: the reservation wage. Outside option = what the
    # welfare state pays a non-worker (max of JG wage and benefit rate); jobless search
    # iff expected earnings (wage_ref x e_i) >= markup x outside, incumbents paid below
    # it quit to welfare at a daily hazard. A SEARCH decision: non-searchers stay in
    # partition-U on welfare (memo-gauged); the JG/benefit machinery is untouched.
    labor_participation: bool = False
    reservation_markup: float = 1.0
    welfare_quit_hazard: float = 0.02
    # -- v16-L6 sub-person firm scale. The whole-person employment grammar imposes a
    # MINIMUM VIABLE FIRM SCALE; industries fragmented below it (the K sector at this
    # calibration: ~0.1 worker/firm) starve and go extinct through an information
    # deadlock (empty shelf -> zero sales -> zero expected demand). Two orthogonal
    # mechanisms, one per defect:
    # (1) footfall -- unmet capital-market buy orders enter sellers' demand
    #     expectations (an order book: demand stays observable at zero inventory);
    capital_rationed_signal: bool = False
    # v23 C-sector counterpart.  Unlike the historical K-sector equal split,
    # only residual demand attached to an isolated, protocol-defined diagnostic
    # seller visit enters that seller's next-period expectation.  This is an
    # estimator, not a transaction-history observation.  Default off
    # preserves both behavior and the legacy RNG stream.
    consumption_rationed_signal: bool = False
    # (2) subscale exit -- a firm whose expected demand stays below the viability
    #     line (in workers) exits by liquidation at a daily HAZARD (staggered, so
    #     survivors inherit the demand share and the consolidation self-terminates).
    #     Builders are EXEMPT (their demand is hard-cyclical by design; their
    #     demography belongs to the housing grammar).
    firm_subscale_exit: bool = False
    subscale_viability_workers: float = 0.5   # "cannot justify half a person"
    subscale_grace_days: int = 180            # sustained sub-viability before at-risk
    subscale_exit_hazard: float = 1.0 / 90.0  # daily exit prob once at risk (~3mo)
    # (3) demand-driven K ENTRY -- the expanding half of the consolidation story:
    #     when EVERY incumbent K-firm is capacity-short (notional labor demand above
    #     k_entry_demand x viability), a new K-firm enters at a daily hazard, funded
    #     from SECTOR RETAINED EARNINGS (the cash-richest incumbent seeds it -- the
    #     spin-off shortcut; founder-household K equity is deferred with the rest of
    #     K-sector equity). Exit prunes overshoot => firm count becomes an emergent
    #     equilibrium of the two hazards.
    capital_firm_entry: bool = False
    k_entry_demand: float = 2.0               # entry line, in multiples of viability
    k_entry_hazard: float = 1.0 / 60.0        # daily entry prob while the sector is short
    mpc_dispersion: float = 0.0     # (CONTROL, demoted) cross-household dispersion of (alpha1,
                                    # alpha2): exogenous saving-preference heterogeneity. Kept as a
                                    # comparison against the endogenous mechanism below. 0 = off. -- FREE
    mpc_wealth_curvature: float = 1.0  # γ in the B1 wealth term α2·W_ref·(V/W_ref)^γ. γ=1 = linear
                                    # (bit-identical). γ<1 = BUFFER-STOCK: marginal MPC out of wealth
                                    # ~ γ·(V/W_ref)^(γ-1) FALLS with wealth, so the rich (endogenously)
                                    # have low MPC -- the realistic causality (wealth→MPC), and a
                                    # HOMOGENEOUS rule, so inequality emerges not assumed (§16.7). -- FREE

    # -- settlement / dividends (choice 甲) --------------------------------
    rho: float = 0.5                # dividend payout ratio of positive profit -- anchored
    # Full cash-basis firm income statement.  Off keeps the historical
    # EBITDA-like ``Firm.profit`` and phase order exactly; the production
    # diagnostic frontier turns it on to close depreciation, interest, tax,
    # distribution and retained-earnings bridges explicitly.
    firm_full_pnl: bool = False
    # Long-run cost-plus quotes include replacement-cost service of opening
    # productive capital: P_K * K * (depreciation + marginal financing rate).
    # This is a pricing recovery term, not an additional accounting expense.
    capital_service_pricing: bool = False
    # Nominal firm asset valuation and asset-related credit ceiling.  Physical
    # capital is priced at committed replacement cost; output inventories use the
    # lower of posted value and observable unit replacement cost, while purchased
    # inputs retain carrying cost.  The lending channel is only a borrowing-base proxy:
    # liens, priority and recovery on default remain outside this flag.
    priced_firm_balance_sheet: bool = False
    firm_capital_haircut: float = 0.30
    firm_inventory_haircut: float = 0.50

    # -- genesis endowments (transient: must not affect stationary behavior)
    d_household0: float = 100.0     # each household's tick-0 deposits
    d_firm0: float = 200.0          # each firm's tick-0 deposits (must fund a first wage bill)

    # -- initial firm postings/stocks (transient: should wash out) ---------
    p_firm0: float = 1.2            # initial posted price
    w_firm0: float = 1.0            # initial posted wage (must be > 0)
    inv_firm0: float = 10.0         # initial inventory
    mu_firm0: float = 0.2           # initial markup
    demand_e_firm0: float = 10.0    # initial expected demand (seeds d^e, avoids div-by-zero)

    # -- market structure: information transparency (buyer price comparison) --
    search_m: int = 1               # buyers compare m random sellers, buy the cheapest.
                                    # 1 = zero transparency (RandomMatch); large (>= n_firms)
                                    # = full transparency (perfect price comparison). The
                                    # single dial spanning the competition axis. -- FREE

    # ======================================================================
    # v2 -- investment + capital (DESIGNDOC §10). Inactive unless n_firms_k>0.
    # Free behavioral dials go 5 -> 7 (v, lambda_I); both pay their way (§10.7).
    # ======================================================================
    n_firms_c: int = 15             # N_{F_C}: consumption-goods firms -- scale (v2 only)
    n_firms_k: int = 0              # N_{F_K}: capital-goods firms -- scale. 0 => v1 kernel
                                    # (default). Set >0 (e.g. via Config.v2()) to enable v2.
    symmetric_k: bool = False       # v2.5: if True, K-firms also use capital (Cobb-Douglas)
                                    # and invest -- undoes the "cut capital recursion" (§10.2)
                                    # to give K-firm retained earnings an outlet (§11.4).
    k_replacement_floor: bool = False  # v2.5 diagnostic: force K-firms to invest at least
                                    # delta_K*K each tick (always replace depreciation),
                                    # to separate "accelerator under-sizes K* => never
                                    # invests" (calibration) from "capital-goods supply
                                    # needs capital => absorbing zero state" (structural).

    # ======================================================================
    # v3 -- banks + endogenous money (DESIGNDOC §12). Inactive unless bank_enabled.
    # Money conservation (M0) is superseded by net-worth conservation (A5).
    # ======================================================================
    bank_enabled: bool = False      # v3 master switch (a single bank; loans create deposits)
    # Explicit realized bank income statement (loan/bond/interbank income less
    # funding expense and write-offs).  Historical version presets retain their
    # certified gross-interest payout rule until this v23 migration is enabled.
    bank_realized_pnl: bool = False
    kappa: float = 3.0              # max leverage multiple L^max = kappa*NW -- FREE (core; Minsky knob)
    r_interest: float = 0.01        # loan interest rate / tick -- anchored/free (exogenous in v3)
    amort: float = 0.1             # principal repaid / tick (fraction of debt) -- FREE
    d_bank0: float = 0.0           # bank genesis deposits (reserves = M carry the conserved M)

    bank_capital_frac: float = 0.0  # v4: bank genesis equity = frac * (non-bank M), the
                                    # loss-absorbing buffer for bad-debt writeoffs. 0 = v3.

    # ======================================================================
    # v11 -- MULTI-BANK: "loan-book banks" (DESIGNDOC §35; PLAN_v11). Partition the loan book among n_banks
    # accounts, each with a FINITE capital buffer (its own deposit balance = genesis equity share + retained
    # interest − its write-offs). Deposits stay a single global pool (no interbank settlement, no reserve tier).
    # A bank fails when write-offs exhaust its capital; borrowers migrate; contagion runs through the REAL
    # economy (crunch → defaults). n_banks=1 => one BANK => bit-identical to the single-bank model.
    # ======================================================================
    n_banks: int = 1                # v11: number of banks (1 = single-bank, bit-identical); genesis equity split
    bank_leverage_mean: float = 10.0  # mean per-bank leverage cap κ_bank (loan_book ≤ κ_bank·capital); ~real 10-15×
    bank_leverage_disp: float = 0.0   # cross-bank dispersion of κ_bank (RISK APPETITE heterogeneity; 0 = uniform)
    bank_assignment: str = "random"   # how borrowers map to banks: "random" | "by_size"
    bank_capital_constraint: bool = False  # v11: enable the κ_bank lending limit (the credit crunch); off = free lending
    bank_migrate_on_failure: bool = True  # v11: on failure, migrate borrowers to alive banks (else they stay at the
                                          # dead bank, crunched).
    bank_target_capital_ratio: float = 0.0  # v11: if >0, banks pay out earnings above target capital = ratio·loan_book
                                            # (Basel-like; BOUNDED, realistic) instead of hoarding ρ-retention forever.
                                            # 0 = ρ-retention (bit-identical). Anchored ~0.1 (real bank leverage ratio).
    bank_exposure_limit: float = 0.0  # v11.2: LARGE-EXPOSURE limit -- a single borrower's debt at a bank ≤ this·(bank
                                      # capital). 0 = off (bit-identical). Anchored to Basel (~0.25 of capital); forces
                                      # DIVERSIFICATION, so a thin bank survives any single default (only a WAVE breaks it).

    # ======================================================================
    # v11.3 -- loan-rate COMPETITION (DESIGNDOC §36). Banks post HETEROGENEOUS loan-rate spreads over the policy
    # rate (mean-preserving: some cheaper, some dearer -- efficiency / market-power heterogeneity, NOT a level
    # change to the average cost of credit). Borrowers SHOP: sample bank_search_m banks and take the cheapest one
    # WITH lending capacity for the whole relationship, so cheap + well-capitalized banks WIN market share (dynamic,
    # endogenous) -> loan-book concentration / too-big-to-fail EMERGES rather than being assigned. The rate a
    # borrower actually pays = policy rate + its bank's spread (floored at 0). Off (or n_banks=1) ⇒ one system rate,
    # no shopping ⇒ bit-identical to v11.2.
    # ======================================================================
    bank_rate_competition: bool = False   # v11.3 master switch (heterogeneous loan-rate spreads + borrower shopping)
    # Keep an originated loan with its recorded creditor until a modeled payoff,
    # refinance or loan sale exists. Default off preserves certified v11.x
    # relationship reassignment; the v23 frontier opts into contract integrity.
    bank_relationship_lock_in: bool = False
    bank_spread_disp: float = 0.0         # cross-bank SD of the (mean-0) loan-rate spread, per-tick rate units; 0 = uniform
    bank_search_m: int = 2                # # rival banks a borrower samples when shopping for the cheapest (search friction)

    # ======================================================================
    # v11.4 -- deposit partitioning + a RESERVE tier + the INTERBANK market, with full intra-tick RTGS
    # settlement (DESIGNDOC §37; PLAN_v11.4). Deposits become bank-specific: every payment settles RESERVES
    # between the payer's and payee's banks in real time (a reserve OVERLAY hooked in Ledger.transfer -- the
    # deposit ledger + A5 are untouched). A reserve-short bank borrows in the interbank market at an ENDOGENOUS
    # (tightness-driven) rate; a payment BLOCKS if it cannot source reserves within its intraday-credit limit
    # (gridlock). A failed debtor bank's loss reassigns to its interbank creditors (contagion). Banks also
    # compete on a DEPOSIT rate (depositors migrate toward higher rates). interbank=False ⇒ v11.3 bit-identical.
    # ======================================================================
    interbank: bool = False               # v11.4 master switch (reserve overlay + RTGS settlement + interbank market)
    interbank_rate_base: float = 0.0      # baseline interbank spread over the policy rate (money market ≈ policy)
    interbank_tightness: float = 0.0      # endogenous interbank-rate sensitivity to market tightness (deficit/surplus)
    reserve_floor_frac: float = 0.0       # intraday-credit limit: a bank's reserves may fall to −this·capital (0 = unlimited)
    deposit_rate_disp: float = 0.0        # cross-bank SD of the (mean-0) deposit-rate spread (deposit-side competition)
    deposit_search_m: int = 2             # # rival banks a depositor samples when shopping for a higher deposit rate

    # ======================================================================
    # v11.5 -- bank DEMOGRAPHICS & OWNERSHIP (DESIGNDOC §38; PLAN_v11.5). Banks gain the firm-style entry/exit +
    # ownership structure: they are FOUNDED by owners (de novo, profit-driven), OWNED (profit → dividends to
    # shareholders, not depositors; a tradeable bank-stock market with a valuation that doubles as a run distress
    # signal), and can die from a RUN (queued withdrawals from own reserves + panic/contagion) as well as from
    # write-offs. Each flag off ⇒ bit-identical.
    # ======================================================================
    bank_equity: bool = False             # A1: banks are owned; profit → owner dividends; mark-to-model valuation
    bank_equity_lambda: float = 0.1       # smoothing of bank earnings for the Gordon-style valuation premium
    bank_equity_trading: bool = False     # A2: a secondary bank-stock market (households trade; price gropes)
    bank_theta_equity: float = 0.1        # households' target share of wealth in bank equity (trading)
    bank_dynamics: bool = False           # B: de-novo bank ENTRY when banking is profitable (ROE > hurdle)
    bank_min_capital: float = 0.0         # regulatory minimum equity to found a bank (the entry gate)
    bank_entry_beta: float = 0.0          # entry sensitivity to excess bank ROE (damped, like firm entry)
    bank_entry_max: int = 1               # max de-novo banks per tick (cap)
    bank_runs: bool = False               # C: depositor runs (queued withdrawals; panic-flight + contagion)
    run_sensitivity: float = 0.0          # flight intensity as bank health falls (logistic slope; 0 = no runs)
    run_health_ref: float = 0.1           # health threshold below which flight accelerates (~the capital ratio)
    run_market_weight: float = 0.5        # weight on the MARKET signal (price/peak) vs the BOOK signal (cap ratio)
    run_fear_persistence: float = 0.9     # decay of the system-wide fear level (panic contagion memory)

    # ======================================================================
    # v12 -- the SECURITIES arc (DESIGNDOC §39; PLAN_v12). Un-consolidate the central bank from the Treasury
    # (GOV → TSY + CB, a proper CB balance sheet: reserves = CB liability, bonds + TSY-claim = CB assets, TGA =
    # Treasury's account at the CB) and finance the deficit with BONDS, which STERILISE reserves ⇒ reserves turn
    # SCARCE ⇒ the funding-side machinery latent since §37/§38 (interbank / gridlock / run liquidity-suspension)
    # activates. A bond has three values -- face (bond identity), book (bank-money invariant), market (wealth /
    # economic_capital). bonds=False ⇒ TSY behaves exactly as GOV ⇒ bit-identical to v11.5. Staged v12.0→v12.4.
    # ======================================================================
    bonds: bool = False                   # v12 master: un-consolidate GOV→TSY+CB (+ later, bond issuance)
    bond_finance_frac: float = 0.0        # share of the deficit financed by issuing bonds (rest money-financed)
    bond_coupon: float = 0.0              # per-tick coupon rate on bonds (v12.1 one-period PAR bill: 0; v12.3: ≈policy rate)
    bond_theta: float = 0.0               # households' target share of wealth held in bonds (v12.3)
    # v12.3: multi-period bonds → the three values DIVERGE (duration/SVB). maturity 1 + coupon 0 ⇒ v12.1 PAR bill.
    bond_maturity: int = 1                # periods to maturity (1 = one-period bill; >1 ⇒ market≠face on a rate move)
    # v23 perf (FINDING 4): daily issuance of long bills fragments the book into ~n_holders x
    # bond_maturity tiny lots, and every tick re-values all of them ⇒ O(horizon^2). Snapping the
    # maturity of newly issued lots to a bucket grid of this width lets same-bucket daily buys by a
    # holder MERGE, cutting the live lot count (and every bond pass) by ~this factor. 1 = one lot per
    # issuance day = exact (t + bond_maturity), NO merging ⇒ bit-identical. >1 shifts maturity onto
    # the grid (a real, flagged economic change) and re-bases the golden digests for that path.
    bond_maturity_bucket: int = 1
    bank_bond_appetite: float = 0.0       # bank's target share of EXCESS reserves put into bonds (money-creating drain)
    # v12.4: the CB's quantity tools. Off ⇒ bit-identical to v12.3 (the CB never creates/destroys base money).
    omo: bool = False                     # open-market ops: drain reserves toward a target ⇒ interbank market binds
    omo_reserve_target: float = 0.0       # target Σ bank reserves as a FRACTION of genesis (0 ⇒ no OMO; e.g. 0.3)
    omo_drain_frac: float = 0.1           # per-tick fraction of the gap to the target drained/injected (smoothing)
    # v13: a fixed NOMINAL reserve target detaches from the economy once the price level moves
    # (the 10k x 3650t run drained 135M of reserves against an 868k target while deposits grew
    # 100x -- LOLR became the system's only funding). Indexing targets reserves the payment
    # system actually needs: omo_reserve_target x reserve_floor_frac x SigmaD (live deposits).
    omo_index_deposits: bool = False      # False => genesis-anchored target (v12.4, bit-identical)
    cb_log_inflation: bool = False        # CB reads ln(P/P_prev) instead of P/P_prev - 1: kills the
    #                                       Jensen noise bias that inflated the per-tick inflation EMA ~7x
    lolr: bool = False                    # lender of last resort: CB funds a run-hit bank ⇒ no suspension cascade
    bank_bond_duration_limit: float = 0.0 # cap a bank's bond book at k·economic_capital (0 ⇒ no cap; the SVB floor)
    bank_resolution_fund: bool = False    # deposit-insurance/resolution: the STATE absorbs a failed bank's residual
    #                                       loss instead of socialising it onto survivors (breaks insolvency contagion)

    # ======================================================================
    # v4 -- firm entry/exit + bankruptcy (DESIGNDOC §13). C-sector only in v1.
    # ======================================================================
    firm_dynamics: bool = False     # v4 master switch (C-firm death + profit-driven entry)
    bankrupt_persist: int = 10      # ticks a C-firm may be insolvent (D-L<0) before it dies
    entry_beta: float = 0.4         # entry sensitivity to excess profit -- FREE (damped)
    entry_max: int = 3              # max new firms per tick (cap; prevents entry overshoot)
    # v13 entry/exit hygiene. Both default OFF => bit-identical to v12.4. At the 10k x 3650t
    # scale the nominal entry signal (profit / capital UNITS vs the policy rate) saturates under
    # inflation so entry pegs at entry_max forever, while never-trading shells (positive net
    # worth by construction: indexed startup cash, no debt) can never die through the insolvency
    # rule -- firm_count exploded to ~3.2k with 6% active, polluting stats and tick time.
    shell_exit_ticks: int = 0       # liquidate a C-firm idle (no production AND no sales) this long; 0 = off
    real_entry_signal: bool = False  # deflate the entry profit-rate by the price level + entrants start with 0 inventory
    inventory_gap_close: float = 1.0  # fraction of the inventory gap entering TODAY's production target (1.0 = v12 one-shot)
    entry_hurdle: float = 0.0       # risk premium added to the policy rate in the entry condition (0 = v12; at the ZLB entry never turned off)
    startup_deposits: float = 15.0   # new firm's initial deposits (from a household; conserved).
                                    # Lean: ~ household wealth in the drained state; firm grows via credit.
    startup_capital: float = 10.0   # new firm's initial capital (real asset, from nothing)

    # ======================================================================
    # v5 -- diseconomies of scale (DESIGNDOC §14).
    # A coordination cost RISING with the SCALE OF OPERATIONS (planned output y*) enters
    # unit cost -> price, so big firms post higher prices. Scale is measured by OUTPUT, not
    # headcount: the dominant firm is capital-intensive (huge output, FEW workers), so a
    # labor/span-of-control version is inert. The SURPRISE finding (§14): this de-concentrates
    # only at LOW transparency (search_m=1) via the profit-squeeze->death channel; under
    # winner-take-all transparency (search_m>=2) it fails, because whoever is momentarily
    # cheapest grabs everything and concentration merely rotates. Transparency is ANTAGONISTIC
    # to competition here, not required for it -- the reverse of the pre-registered guess.
    # ======================================================================
    dis_slope: float = 0.0          # coordination cost slope: uc *= (1 + dis_slope*y*) -- FREE
                                    # (core v5 dial; scale-of-operations cost. 0 = v1-v4)

    # ======================================================================
    # v6 -- capital market: a single aggregate equity index (DESIGNDOC §16; PLAN_v6).
    # Households split wealth between deposits (safe, earns r) and the index (a claim on total
    # C-firm net worth). Price gropes on notional excess demand (no auctioneer); trades are
    # pro-rata rationed so shares AND money conserve. Demand = fundamentalist (value-price,
    # stabilising) + chartist (price trend, the BUBBLE knob). Activates choice 乙 (equity enters
    # household wealth). capital_market=False => v5 bit-identical.
    # ======================================================================
    capital_market: bool = False    # v6 master switch (equity index + portfolio choice)
    lambda_p: float = 0.10          # price groping / market-impact speed -- FREE (stability)
    w_chartist: float = 0.0         # chartist (trend-extrapolation) demand weight -- FREE
                                    # (THE bubble knob; 0 => price tracks fundamental)
    w_fundamental: float = 1.0      # fundamentalist (value-price) demand weight -- anchored (normalize)
    theta_equity: float = 0.30      # target equity share of household wealth -- FREE
    trend_lambda: float = 0.3       # adaptive momentum speed on index returns -- anchored (~lambda_d)
    wealth_effect: float = 0.0      # weight of (smoothed) equity value in B1 consumption. 0 =
                                    # equity affects WEALTH ACCOUNTING (乙, for T8) but NOT
                                    # consumption -- the stable core. >0 turns on the wealth-effect
                                    # demand channel, which amplifies the §9 drain (§16). -- FREE
    equity_ema_lambda: float = 0.1  # equity-wealth smoothing for the wealth effect -- FREE (throttle)
    float_shares: float = 1000.0    # total index units (fixed; issuance -> v6.1) -- scale

    # ======================================================================
    # v6.1 -- per-firm equity (DESIGNDOC §18; PLAN_v6.1). Turns the aggregate index into a
    # real per-firm stock market: each firm has its own shares/price, founders own the firms
    # they fund, valuation reflects earnings (floored residual income), and (v6.1b) a high
    # market valuation q lifts investment. per_firm_equity=False => v6 aggregate, bit-identical.
    # ======================================================================
    per_firm_equity: bool = False   # v6.1 master switch (per-firm stock market)
    watchlist_size: int = 15        # # firms each household actively trades (sparse portfolio) -- scale
    shares_per_firm: float = 100.0  # each firm's fixed share float -- scale
    resid_income_lambda: float = 0.1  # smoothing of residual income for valuation -- anchored
    lambda_q: float = 0.0           # q -> investment sensitivity (v6.1b; 0 = side-pot, no feedback) -- FREE
    q_invest_floor: float = 0.5     # min investment multiplier g(q) (q-crash floor) -- anchored
    q_invest_cap: float = 2.0       # max investment multiplier g(q) (q-bubble cap) -- anchored

    # v6.2 -- equity finance (DESIGNDOC §19): the DIRECT financial->real channel. A firm with
    # q>1 issues new shares (extra sell-side supply in its own market) at the market price; the
    # proceeds go to firm deposits and fund capex. So a bubble literally pays for investment
    # (and a crash starves it). equity_finance=False => v6.1, bit-identical.
    equity_finance: bool = False    # v6.2 master switch (share issuance to fund investment)
    lambda_issue: float = 0.0       # issuance intensity: issue ~ lambda_issue·(q-1)·float -- FREE

    # ======================================================================
    # v7 -- household credit (DESIGNDOC §20): debt-financed consumption. Households borrow to
    # defend a subsistence consumption floor when income+deposits fall short, up to a debt-to-
    # income limit. This RECYCLES savers' deposits into spenders' demand -- the channel the
    # thrift paradox (§16.7) lacked -- so the economy can be prosperous AND unequal (savers hold
    # deposits, borrowers hold debt = balance-sheet inequality). household_credit=False => v6.x.
    # ======================================================================
    household_credit: bool = False  # v7 master switch (household borrowing to consume)
    # Carry unpaid household loan interest as a memo stock.  It is deliberately
    # outside ledger principal, loan books and RWA; historical presets keep the
    # old principal-first, no-arrears settlement until this migration is enabled.
    household_interest_arrears: bool = False
    hh_subsistence: float = 0.0     # consumption floor c_min households borrow to defend (0=off) -- FREE
    hh_credit_limit: float = 2.0    # debt-to-income cap: L_h <= this · Y^e_h -- FREE (the key dial)
    hh_amort: float = 0.1           # household debt amortization fraction / tick -- anchored

    # ======================================================================
    # v8 -- household MARGIN credit (DESIGNDOC §21): borrow to buy EQUITY, not consume. The debt is
    # collateralised by the equity (LTV limit), so borrowing brings an ASSET (not just debt). When
    # bullish, households lever up (target equity share > 1) -> leveraged gains CONCENTRATE wealth
    # (T8); a price drop triggers margin calls -> forced deleveraging (fire sales) -> the credit-
    # collateral crisis. Needs per_firm_equity. margin_credit=False => v7 bit-identical.
    # ======================================================================
    margin_credit: bool = False     # v8 master switch (household leverage into equity)
    margin_ltv: float = 0.5         # max margin debt as a fraction of equity value (loan-to-value) -- FREE
    margin_max: float = 2.0         # cap on target equity share of net worth (leverage ceiling) -- FREE

    # ======================================================================
    # v8.1 -- Gibrat multiplicative growth (DESIGNDOC §23): each firm's market share (attractiveness)
    # follows a geometric random walk, and goods demand is allocated ∝ attractiveness^β. With the v4
    # entry/exit barrier this is the canonical Zipf mechanism (Simon/Gabaix) -- the multiplicative
    # growth §22 found missing for T6 AND T8. gibrat_growth=False => v8 bit-identical.
    # ======================================================================
    gibrat_growth: bool = False     # v8.1 master switch (multiplicative market-share growth)
    gibrat_sigma: float = 0.05      # per-tick lognormal shock size on attractiveness -- FREE (core dial)
    pref_attach_beta: float = 1.0   # demand exponent on attractiveness (β≈1 = Zipf; >1 = winner-take-all) -- FREE
    pref_price_elasticity: float = 0.0  # v9.1: PRICE competition in demand (∝ attr^β / price^ε). ε=0 ⇒ pure
    #   preferential (bit-identical). ε>0 restores the demand-side price brake -- cheaper firms win more
    #   demand -- keeping Zipf while disciplining prices/concentration (the §28.5 household-demand fix) -- FREE
    gibrat_entry_a0: float = 0.2    # entrant's initial attractiveness (the reflecting barrier) -- FREE

    # ======================================================================
    # v8.2 -- adaptive portfolio adjustment (DESIGNDOC §24). Applies the B2 adaptive-expectation
    # discipline to the ONE decision that lacked it: portfolio rebalancing. Households move only a
    # fraction λ toward their ideal equity target each tick (partial adjustment), instead of the
    # unrealistic instant full rebalance. Founders (100%-owned firms) then delever SLOWLY, so
    # concentrated ownership of Gibrat winners EMERGES (not imposed) -> a cleaner wealth Pareto tail.
    # λ=1.0 => v8.1 bit-identical. λ chosen INDEPENDENTLY (= λ_I), NOT tuned to a target slope (§0-ii).
    # ======================================================================
    portfolio_adjust: float = 1.0   # λ: fraction of the equity gap traded per tick (1=instant rebalance) -- anchored

    # ======================================================================
    # v8.3 -- weaken the Tobin's-q → investment channel (DESIGNDOC §25). Empirically q has a WEAK,
    # SLUGGISH effect on investment (accelerator + cash flow dominate; firms ignore transient
    # mispricing / bubbles). Our default (lambda_q=0.3 on the INSTANT market q) over-transmits stock
    # noise into real investment -> spurious macro volatility. v8.3 lowers lambda_q and makes
    # investment follow a SMOOTHED q. q_invest_smooth=1.0 => instant q => v8.1 bit-identical.
    # ======================================================================
    q_invest_smooth: float = 1.0    # EMA speed of the q that drives investment (1=instant; <1=sluggish) -- anchored

    # ======================================================================
    # v8.4 -- dividends flow to shareholders PRO-RATA (DESIGNDOC §26). In the per-firm regime we track
    # who owns what (h.holdings[f.id]) yet pay dividends EQUALLY per capita -- an accounting
    # inconsistency inherited from the v6 aggregate-index era ("choice 甲 homogeneity"). Pro-rata is
    # the correctness fix: each firm's payout goes to ITS holders in proportion to their shares, so
    # a non-owner earns zero dividend income and the cash-flow return to equity is differential (like
    # the capital-gains channel already is). pro_rata_dividends=False => equal split => bit-identical.
    # Needs per_firm_equity (the aggregate/pre-v6 regimes have no per-firm holdings to prorate over).
    # ======================================================================
    pro_rata_dividends: bool = False   # v8.4: distribute each firm's dividend by holdings, not per capita

    # ======================================================================
    # v8.5 -- founder-owned genesis (DESIGNDOC §27). At t=0 v6.1 splits each firm's float EQUALLY
    # among its (many) watchers -- diffuse ownership that caps how concentrated the wealth tail (T8)
    # can get, since no household starts with a big block. Firms FOUNDED later already vest 100% in
    # their funder (economy.py §ii); founder_owned_genesis extends that to the genesis cohort: a
    # minority "founder class" owns the initial float, mirroring real entrepreneurial concentration.
    # founder_owned_genesis=False => equal split => bit-identical. Needs per_firm_equity.
    # ======================================================================
    founder_owned_genesis: bool = False   # v8.5: genesis float vests in a founder class, not all watchers
    genesis_founder_pool: float = 0.1     # fraction of households eligible to found (minority owner class)

    # ======================================================================
    # v9 -- the GOVERNMENT sector (DESIGNDOC §28; PLAN_v9). A Treasury (fiscal + macroprudential state;
    # the central bank is a separate future layer). The government is the ONLY state mutable during a run
    # (its levers live in a Policy object, seeded from these fields); everything else is frozen at t=0.
    # A government running a deficit issues OUTSIDE money -- net financial assets the private sector can
    # accumulate (cumulative deficit = private net wealth). The GOV ledger account may go negative (=
    # government debt); A5 is untouched (transfers conserve). government=False => all fiscal levers 0 and
    # the macroprudential levers hold their existing defaults => bit-identical to v8.5.
    # ======================================================================
    government: bool = False              # v9 master switch (Treasury: taxes, spends, macroprudential)
    gov_consumption_share: float = 0.0    # g: real gov goods demand = g·potential_output -- anchored (~0.2 G/GDP)
    gov_deficit_target: float = 0.0       # if >0: size gov consumption to MAINTAIN a deficit of this·GDP
    #   (tax-financed G + a controlled deficit); overrides the quantity mode. 0 => quantity mode (g above)
    deficit_u_ref: float = 0.0            # if >0: STATE-DEPENDENT deficit -- scale the target by min(1, u/this),
    deficit_u_cap: float = 1.0            # v13: max multiple of the deficit target under slack (1.0 = v12 cap)
    #   so it runs the full deficit under slack (u>=ref) but TAPERS to balance at full employment (u->0),
    #   stopping the injection from becoming pure inflation. Anchored to the natural rate (~0.05). 0=fixed target
    benefit_replacement: float = 0.0      # b: unemployment benefit = b·wage_ref -- anchored (OECD replacement)
    # v23: a minimum income guarantee, tested on INCOME rather than on unsold hours. The benefit
    # above is a QUANTITY rule and is blind to a worker who sells ALL their labour and still
    # earns too little -- which v16-L4's earnings dispersion (pay = wage x e_i) manufactures.
    # 0.0 => never fires => bit-identical.
    benefit_income_floor: float = 0.0     # top income up to this x wage_ref x labour supply
    pension_replacement: float = 0.0      # v13: old-age pension per elder person = this · wage_ref (0 = off).
                                          # The only transfer reaching non-workers: without it elder households
                                          # with no savings sit at the consumption floor (audit: elder/adult
                                          # median consumption fell to 0.13, poverty ~44% at full employment)
    tax_profit_rate: float = 0.0          # τ_π on positive firm profit (pre-dividend) -- anchored (corporate tax)
    tax_income_rate: float = 0.0          # τ_y marginal rate on household labour+dividend income -- anchored
    income_allowance: float = 0.0         # a_x: personal allowance as fraction of mean income (progressivity; 0=flat)
    tax_consumption_rate: float = 0.0     # τ_c: VAT on goods purchases -- anchored (real VAT); REGRESSIVE
    tax_wealth_rate: float = 0.0          # τ_w on household net worth per tick -- anchored (~1%/yr); the T8 lever
    wealth_allowance: float = 0.0         # progressive wealth-tax exemption as a MULTIPLE of mean net worth (0=flat,
                                          # no threshold => bit-identical; >0 => only above-threshold NW taxed, realistic)
    min_wage: float = 0.0                 # wage floor (0=off) -- anchored to min/median-wage ratio when on
    household_bankruptcy: bool = False    # discharge deeply-underwater households' margin debt (write_off) -- §27 exit valve

    # ======================================================================
    # v9.1 -- government INVESTMENT -> public capital -> productivity (DESIGNDOC §29; PLAN_v9.1). The supply
    # side the government lacked. Government investment buys real capital goods (from K-firms), accumulating
    # an economy-wide PUBLIC capital stock K_pub that raises EVERY C-firm's productivity (Barro 1990):
    #   Y_f = A·K_f^α·N_f^(1-α) · (1 + K_pub/K_ref)^γ.  This gives the deficit a PRODUCTIVE outlet -> capacity
    # grows -> the injection is absorbed as output not inflation -> ENDOGENOUS GROWTH (breaks stationarity).
    # gov_investment_share=0 OR public_capital_gamma=0 => factor 1 => bit-identical to v9.
    # ======================================================================
    gov_investment_share: float = 0.0     # g_I: public investment as a share of potential output/tick -- anchored (~3-5% public inv/GDP)
    public_capital_gamma: float = 0.0     # γ: output elasticity to public capital -- anchored (~0.05-0.15); 0=off
    public_capital_depreciation: float = 0.05  # δ_pub: public capital depreciation/tick -- anchored (≈ δ_K)

    # ======================================================================
    # v9.3 -- LABOR welfare (DESIGNDOC §32). §31 found welfare at the bottom is an EMPLOYMENT story, so this
    # targets the labor market directly. Two levers: (1) a real min_wage floor (now WIRED in plan_wage --
    # a statutory floor that binds immediately, bypassing Calvo); (2) a JOB GUARANTEE (employer of last resort,
    # WPA-style): after the private market clears, the government hires EVERY household's residual (unemployed)
    # labor at a JG wage -- UNCAPPED (a buffer stock, the defining feature) -- paid as outside money (like the
    # benefit), and that public-works labor builds PUBLIC CAPITAL (reuses the v9.1 K_pub channel). It REPLACES
    # the dole for takers, and its deficit swings ON TOP of the discretionary target (an automatic stabilizer).
    # job_guarantee=False => bit-identical. jg_productivity is a technological param (stays Config, like γ);
    # the on/off switch and the JG wage are Policy levers (the government's live control surface). UBI skipped.
    # ======================================================================
    job_guarantee: bool = False           # v9.3: uncapped employer of last resort (buffer-stock employment)
    jg_wage_ratio: float = 0.0            # JG wage = this · mean private wage (a transitional floor wage, <1)
    jg_productivity: float = 0.0          # public-capital units built per unit of JG labor (0 = pure income floor)

    # ======================================================================
    # v10 -- the CENTRAL BANK: an endogenous policy interest rate (DESIGNDOC §33; PLAN_v10). Promotes the frozen
    # r_interest to a per-tick POLICY rate set by a Taylor rule:
    #   r = clip( ρ·r_{-1} + (1-ρ)·[ r* + φ_π·(π̄ - π*) - φ_u·(u - u*) ] , 0, r_max ).
    # The legacy transmission is wired to debt service, entry and asset valuation; the
    # direct investment/consumption/credit decisions remain behind the separately
    # reviewable ``monetary_direct_transmission`` flag below. central_bank=False =>
    # r ≡ r_interest. Rate-rule params are Policy (the CB's live control surface);
    # neutral rate, natural u, EMA smoothing and cap are Config (structural).
    # ======================================================================
    central_bank: bool = False            # v10: master switch; off => frozen r_interest => bit-identical
    inflation_target: float = 0.0         # π*: per-tick inflation target (Policy lever)
    taylor_phi_pi: float = 1.5            # φ_π: inflation response; >1 = the Taylor principle (Policy lever)
    taylor_phi_u: float = 0.5             # φ_u: unemployment-gap response; 0 = pure inflation targeter (Policy)
    rate_inertia: float = 0.8             # ρ: rate smoothing / gradualism (Policy lever)
    r_neutral: float = 0.01               # r*: neutral policy rate -- defaults to r_interest (Config, structural)
    u_natural: float = 0.05               # u*: reference/natural unemployment for the gap term (Config)
    infl_ema_lambda: float = 0.02         # λ: EMA smoothing of the noisy per-tick inflation signal (Config)
    r_max: float = 0.10                   # rate sanity cap per tick (Config)

    # Optional direct monetary-demand transmission.  The legacy model has rate-sensitive
    # debt cash flows and asset prices but no direct user-cost, household debt-budget, or
    # firm debt-service-capacity decision.  Keeping one master switch off preserves every
    # historical decision and random draw; the v23 diagnostic frontier enables it.
    monetary_direct_transmission: bool = False
    investment_user_cost_elasticity: float = 0.5  # elasticity to the real user-cost ratio
    investment_user_cost_multiplier_min: float = 0.5
    investment_user_cost_multiplier_max: float = 1.5
    investment_user_cost_floor: float = 1.0e-9    # per-tick floor for ZLB/negative-real-rate cases
    firm_credit_min_dscr: float = 1.25            # expected operating cash flow / contractual service
    # Unified per-tick required return for direct-mode bank and per-firm equity
    # valuation.  A risk premium, not an annual-scale magic floor, keeps the ZLB
    # finite and continuous on the daily v13 clock.
    valuation_discount_floor: float = 1.0e-9
    valuation_risk_premium: float = 1.34e-4

    # ======================================================================
    # v10.1 -- the bank pays interest BY DEPOSITS, not split equally (DESIGNDOC §33; PLAN_v10.1). The v3 bank
    # split its collected loan interest EQUALLY across all households ("bank dividend", plumbing to close the
    # interest loop) -- which paid interest even to zero-deposit hand-to-mouth households (MPC 0.8, spent in
    # full), over-strengthening the interest-income demand channel. The correct recipient is the DEPOSITOR,
    # in proportion to deposits. interest_by_deposits=True routes payable ∝ D_h. A correctness fix, not a
    # policy lever; NO separate deposit rate yet (that corridor is a later add). False => equal split =>
    # bit-identical to v10.
    # ======================================================================
    interest_by_deposits: bool = False    # v10.1: distribute bank interest ∝ household deposits (else equal split)
    # v23: contractual deposit interest -- the bank's COST OF FUNDS. interest_by_deposits above is
    # a DISTRIBUTION rule (it splits leftover dividends by deposit share); it is not a P&L expense.
    # This pays deposit_rate x deposit each tick as a real bank->depositor transfer, booked against
    # bank profit so a net-interest-margin squeeze becomes possible. 0 => bit-identical.
    deposit_rate: float = 0.0             # per-tick contractual interest paid on household deposits

    # ======================================================================
    # v9.2 -- remove the fixed-nominal-startup money NON-NEUTRALITY (DESIGNDOC §30). New firms enter with a
    # fixed NOMINAL cash endowment (startup_deposits); under inflation that buys ever fewer workers, so
    # entrants are starved -> die -> the incumbent tail concentrates (the artifact behind the T6/inflation
    # link). index_startup scales the endowment by the price level (a COLA for new firms) so ENTRY is
    # REAL-invariant. False => bit-identical. This is a modeling-bug fix, not a policy lever (§30).
    # ======================================================================
    index_startup: bool = False           # v9.2: price-index the startup endowment (real-invariant entry)

    # v23 P0 (capital clock): `v` is the ANNUAL capital-output ratio, but plan_investment
    # multiplies it by a PER-TICK demand flow. On the daily calendar that makes the desired
    # capital stock ticks_per_year too small (measured K / annual GDP ~0.004 vs the configured
    # 2.5). capital_annual_clock re-derives the joint set (v, K_firm0, A) in __post_init__ so
    # genesis output is exactly invariant; default off => every existing preset bit-identical.
    capital_annual_clock: bool = False
    # Idempotency guard for the in-place annual-clock migration. It mutates v/K_firm0/A in
    # __post_init__, and dataclasses.replace() re-runs __post_init__ on already-migrated
    # values -- so without this flag every replace() (World per-economy reseed, the .large()/
    # .small() presets, experiment overrides) would re-scale by ticks_per_year AGAIN (365x,
    # compounding). As a real field it is copied by replace(), so a migrated config stays
    # migrated exactly once. Not user-set; excluded from equality so it never distinguishes
    # two otherwise-identical configs.
    _capital_annual_clock_applied: bool = field(default=False, repr=False, compare=False)
    ticks_per_year: float = 365.0   # calendar scale used by the annual-clock derivation
    # v23 FINDING 5: the annual clock makes capital REAL (v -> v*S=912.5), and the desired-capital
    # rule K* = v * demand_expected then AMPLIFIES the demand-expectation EMA ~912x into the capital
    # stock. With the daily demand memory (lambda_d) unchanged, firms size a ~12-year capital stock
    # off a ~130-day demand estimate, so daily demand noise drives a large boom-bust accelerator
    # cycle (unemployment spiking to ~38% over a decade). Smoothing the demand expectation at the
    # SOURCE damps the cycle far better than slowing the investment RESPONSE (which costs output): a
    # 3-seed x 6-factor sweep found lambda_d *= 0.5 the robust optimum -- it minimises inflation
    # volatility AND peak unemployment AND raises output, non-monotonically (0.75 and 0.15 are both
    # worse). Applied ONLY when the clock is on, so every clock-off preset stays bit-identical.
    capital_clock_demand_smoothing: float = 0.5
    v: float = 2.5                  # desired capital-output ratio vs ANNUAL output -- FREE (core)
    lambda_I: float = 0.25          # investment adjustment / damping speed -- FREE (stability)
    delta_K: float = 0.05           # capital depreciation rate -- anchored (+ maint. floor)
    alpha: float = 0.3              # capital share, Cobb-Douglas -- anchored (capital income share)
    A: float = 1.0                  # TFP, consumption sector -- scale (normalize)
    a_K: float = 1.0                # labor productivity, capital sector -- scale (A:a_K ratio meaningful)

    # v19 (PLAN_v19): technology as an object -- an economy-wide TFP index Z(t) applied as a
    # production-seam MULTIPLIER (like _pubcap_factor), NOT a per-firm A mutation. All defaults
    # keep Z pinned at 1.0 => every pre-v19 config bit-identical.
    tfp_drift_rate: float = 0.0     # annual trend growth g of the Hicks-neutral index (0 = frozen)
    tfp_drift_sigma: float = 0.0    # std of the i.i.d. innovation on the daily growth rate (0 = deterministic)
    tfp_law: str = "exogenous"      # "exogenous" (trend) | "learning" (endogenous LBD seam, 2.x)
    tfp_learning_theta: float = 0.0 # learning-by-doing elasticity Z=(cumout/base)^theta (0 = inert)
    tfp_drift_c: float = 0.0        # per-sector trend overrides (0 = use the uniform tfp_drift_rate)
    tfp_drift_k: float = 0.0
    tfp_drift_e: float = 0.0

    # v2 initial endowments / postings (transient; K_firm0 strictly > 0)
    K_firm0: float = 20.0           # initial C-firm capital (must be > 0 for Cobb-Douglas)
    d_cfirm0: float = 200.0         # C-firm tick-0 deposits
    d_kfirm0: float = 200.0         # K-firm tick-0 deposits (fund a first wage bill)
    p_kfirm0: float = 1.2           # K-firm initial posted price
    inv_kfirm0: float = 5.0         # K-firm initial capital-good inventory

    # ======================================================================
    # v17.0 -- energy: the first INTERMEDIATE input (PLAN_v17). E-firms produce a
    # storable commodity under a CAPACITY edge (y = min(a·L, κ·K)); c/k firms need
    # energy_intensity units per output unit (Leontief), hold an input stock at a
    # coverage target, and energy cost enters the B3 unit cost. Energy sold to firms
    # is intermediate consumption (never GDP); the E-sector's demographics are FROZEN
    # through the 17.x arc. energy_enabled=False => no E-firms exist, every hook is
    # a guarded no-op => bit-identical.
    # ======================================================================
    energy_enabled: bool = False        # v17.0 master switch (E-sector + energy market)
    n_firms_e: int = 4                  # E-firm count (frozen; entry needs a construction lag, later flag)
    energy_intensity: float = 0.05      # e: energy units per unit of c/k output (uniform in v1)
    energy_coverage_ticks: float = 30.0 # downstream input-stock target, in ticks of expected use
                                        # (30 days on the day-tick calendar = the crude-stock anchor)
    energy_gap_close: float = 0.05      # restock gap-closing throttle (the phi-grammar mirror; the
                                        # v13 one-shot-closing lesson applies to input stocks too)
    kappa_E: float = 1.0                # capacity edge: energy units per unit of E-capital per tick
    a_E: float = 1.0                    # E-firm labor productivity. NOTE: B3 prices at markup on
                                        # LABOR cost, so a sector's relative price is pinned by its
                                        # labor productivity -- the 5-8% cost-share anchor forces
                                        # a_E ~ a (p_E ~ (1+mu)w/a_E). The capacity edge still binds
                                        # PLANS (planning caps y* at kappa*K before labor inversion),
                                        # so supply stays short-run inelastic under demand surges.
    energy_util0: float = 0.85          # genesis capacity utilization (headroom so trend growth
                                        # does not short the market at t1)
    d_efirm0: float = 200.0             # E-firm tick-0 deposits
    p_efirm0: float = 1.2               # E-firm initial posted price (genesis avg-cost anchor)
    tax_energy_rate: float = 0.0        # excise on energy purchases (Policy lever; VAT grammar; inert)
    # -- v17.1 household energy: necessity demand in the SAME market session (so the
    # 17.4 rationing menu can arbitrate households vs industry). No household storage.
    # Need is UNIFORM per household in v1 (size scaling arrives with the 17.5 housing
    # coupling, where the size objects live); price-inelasticity is emergent from the
    # buy-need-first rule, not assumed.
    energy_household: bool = False      # v17.1 flag (requires energy_enabled)
    energy_hh_share: float = 0.07       # genesis anchor: household energy spend / steady
                                        # household consumption (~w_firm0) => need units
                                        # = share * w_firm0 / p_efirm0, fixed thereafter
    cb_core_inflation: bool = False     # CB Taylor input reads CORE (ex-energy) instead of
                                        # headline once households buy energy -- the classic
                                        # "which index through a supply shock" experiment
    # -- v17.2 the capacity shock SCENARIO (the model's first deliberate exogenous
    # shock; a SCENARIO, never a default). kappa multiplier: capacity_kappa *= (1-mag)
    # at shock_at; a pulse (duration>0) restores it exactly. The accelerator's v stays
    # at its genesis technology -- after a PERMANENT cut the sector re-expands K through
    # the unfilled-demand channel, slowly (that lag IS the experiment). Magnitudes are
    # calibrated-world territory: a 2x cut kills the stabilizer-free kernel outright.
    energy_shock_at: int = 0            # tick the shock lands (0 = no shock, bit-identical)
    energy_shock_magnitude: float = 0.0 # fractional capacity cut (0.3 = -30% kappa)
    energy_shock_duration: int = 0      # 0 = permanent step; >0 = pulse of this many ticks
    tax_energy_windfall: float = 0.0    # Policy: profit surtax on E-firms (shock-response
                                        # fiscal instrument; reduces the dividend pool)
    # -- v17.3 strategic reserve, state ownership, hoarding --
    spr_target_units: float = 0.0       # Policy: SPR stock target (0 = off). Below target the
                                        # fiscal node BUYS in the session (deficit-financed,
                                        # conserving); above it (e.g. release: target -> 0) it
                                        # SELLS at just under the cheapest ask, proceeds -> fiscal
    spr_flow_cap: float = 0.0           # Policy: max units the SPR trades per tick
    soe_efirm: bool = False             # E0 is STATE-OWNED: its dividends flow to fiscal
                                        # (ownership without shares -- the K-firm precedent
                                        # says E-firms are not equitized)
    soe_price_at_cost: bool = False     # Policy: the SOE prices at unit cost (markup 0, no
                                        # Calvo) -- the market-power discipline experiment
    energy_hoarding_beta: float = 0.0   # firms scale the coverage target by (1 + beta *
                                        # max(0, energy price trend)) -- the 1970s queue
                                        # amplifier, a separate flag, DEFAULT OFF
    # -- v17.4 the crisis triple (one mechanism in reality: a binding cap creates
    # excess demand => a rationing rule must answer WHO IS CUT, and E-firm losses
    # => a compensation transfer, or the cap is a documented sector-killer).
    energy_price_cap: float = 0.0       # Policy: market asks clamped at the cap (0 = off)
    energy_rationing: str = "market"    # Policy: market | household_first | industry_first
                                        # | proportional. Priority classes clear in two
                                        # sequential sessions (the native shuffle would
                                        # destroy a mere ordering); proportional allocates
                                        # each seller's stock pro-rata to remaining demand
    energy_cap_compensation: bool = False  # Policy: fiscal covers (posted - cap) x sold
    # -- v17.5 couplings (each its own dial, 0/off = bit-identical) --
    energy_mortality_gamma: float = 0.0 # fuel poverty -> mortality: M = clip(1 + gamma*fp, 1, hi);
                                        # Phase-2 grammar (annual, burn-in discard) -- FREE
    energy_mortality_mult_hi: float = 1.3
    energy_signal_burnin_years: int = 4
    energy_subsidy_rate: float = 0.0    # Policy: rebate share of household energy bills
    energy_subsidy_threshold: float = 0.0  # Policy: 0 = flat; >0 = only households with
                                        # deposits < this x mean (the §34 targeting reprise)
    # housing x energy (need ∝ dwelling size): AWAITS the v15.2 size gate -- the
    # registry's size scalar is still identically 1.0, so the coupling would be
    # observationally vacuous; lands when the gate opens. Efficiency investment
    # (e_coeff falls with investment): optional per plan, deferred with it.

    # ===================== v18: consumption stratification ========================
    # -- v18.0 subsistence basket & deprivation gauges (OBSERVATION ONLY) --
    # The basket is an external MEASUREMENT standard, not a decision input: a
    # per-person subsistence real-consumption floor (needs-weighted), fitted once at
    # genesis to a fraction of mean per-capita consumption (the poverty-line idiom),
    # then FROZEN. Coverage = realized real consumption / basket cost at current
    # prices; spell counters track consecutive days below the 100/60/30% thresholds.
    # A sustained ACUTE spell sets a DOMAIN-BOUNDARY health flag: per the research
    # ruling (PLAN_v18), acute deprivation is NOT a death mechanism -- it marks the
    # edge of the model's validity domain (post-breach demographic/long-run paths are
    # out of domain; distributional readouts stay valid). Off => bit-identical.
    deprivation_gauges: bool = False       # v18.0 master flag (observation only)
    subsistence_share: float = 0.5         # basket = share x genesis mean per-capita real
                                           # consumption (needs-weighted per person); fitted
                                           # at genesis, then frozen (external anchor)
    deprivation_burnin_years: int = 3      # discard the genesis relaxation before anchoring
                                           # (the housing/energy-signal burn-in idiom; 3y
                                           # clears the worst of the v13 genesis clearing slump)
    deprivation_acute_days: int = 7        # a sub-30% spell this long trips the domain flag
    deprivation_chronic_days: int = 30     # a sub-60% spell this long trips the domain flag

    # -- v23 optional national accounts (OBSERVATION ONLY) --
    # Adds a fixed-basket CPI and explicit production/expenditure/income GDP
    # components with reconciliation residuals.  This is deliberately independent
    # of every fiscal/policy consumer: the legacy price/output sensors remain the
    # behavioral inputs until a separately reviewed migration enables them.
    national_accounts_metrics: bool = False
    # Separately gated consumers of the observation layer.  The fixed-basket CPI
    # feeds only the next-tick Taylor sensor; fiscal procurement/investment uses
    # lagged economy-wide nominal GDP.  Both remain off for historical trajectories.
    cb_uses_fixed_basket_cpi: bool = False
    fiscal_uses_national_accounts_gdp: bool = False
    # Refresh expenditure weights periodically while chain-linking the new
    # Laspeyres basket to the accepted index level on the rebase observation.
    # A calendar-year default prevents firm entry/exit from leaving permanent
    # zombie/zero-weight products without turning short-run substitution into CPI.
    cpi_rebase_interval_days: int = 365

    # -- v18.1 sector split & the budget hierarchy (the structural stage) --
    # Consumption goods split into NECESSITY and LUXURY sectors. The household goods
    # phase becomes two sequenced sessions of the existing market protocol: NECESSITY
    # first (quantity-targeted at a fixed per-need-unit basket -- the non-homothetic
    # primitive), LUXURY takes the residual budget. Engel's law (necessity SHARE falls
    # with income) must EMERGE from the fixed necessity quantity, not be seeded. The
    # necessity need is anchored to genesis config (the v17.1 energy-need idiom:
    # quantity = share x w_firm0 / p_firm0 per need-unit), never to realized (transient)
    # consumption. c-firms are tagged necessity/luxury by `n_firm_share`; entry picks a
    # sector by per-sector profit. Off => single session => bit-identical.
    consumption_strata: bool = False       # v18.1 master flag
    necessity_share0: float = 0.5          # genesis necessity share of goods consumption
                                           # (the 40-55% anchor); sets the per-need-unit
                                           # necessity quantity = share x w_firm0 / p_firm0
    n_firm_share: float = 0.5              # fraction of c-firms tagged NECESSITY (sector sizes;
                                           # the rest are LUXURY). Entry picks a sector by profit.

    # -- v18.4 inter-household family transfers (the first-line private safety net) --
    # A household that cannot afford its necessity need from live deposits is topped up
    # by kin households (parents / adult children, via the v13 relation links) holding a
    # surplus above their own need x a buffer. Atomic + conserving through the person-
    # claim/ledger rails; surfaces the truly exposed (no kin, no assets). Off ⇒ no-op ⇒
    # bit-identical. Needs the sector split (necessity price) + demographics (kin links).
    family_transfers: bool = False         # v18.4 master flag
    family_transfer_buffer: float = 1.5    # a donor keeps its own need x this before giving

    # -- v18.5 supply-side reallocation: product-line SWITCHING --
    # The emergent investment+entry channel already reallocates capital toward the growing
    # sector, but EXISTING capital is stuck (necessity is over-capitalized ~13pp vs its
    # shrunk demand). Switching lets a firm RETOOL its stuck capital to the other sector,
    # closing the demand-capital lag -- at a cost (a fraction of capital lost) and with
    # friction (a sustained return gap + a low hazard), so structural transformation stays
    # a slow, non-oscillating process (the v16 search-friction analog on the supply side).
    # Off ⇒ no-op ⇒ bit-identical. Needs the sector split.
    sector_switching: bool = False         # v18.5 master flag
    switch_retool_loss: float = 0.3        # fraction of capital lost when a firm retools
    switch_return_gap: float = 0.5         # the other sector's profit rate must beat own by this
    switch_pressure_days: int = 60         # sustained ticks of the gap before a firm is eligible
    switch_hazard: float = 0.01            # daily switch probability once eligible (rare)

    def __post_init__(self) -> None:
        self._apply_capital_annual_clock()
        self._validate()

    def _apply_capital_annual_clock(self) -> None:
        """v23 P0: the desired-capital rule mixes an ANNUAL ratio with a DAILY flow.

        `plan_investment` computes `K* = v * demand_expected`. On the daily calendar
        `demand_expected` is a PER-TICK flow, but `v` is the textbook capital-output ratio
        measured against ANNUAL output. v13's daily migration converted `lambda_I`, `delta_K`,
        `r_interest`, `amort`, `eta` and the inflation target, but MISSED `v` -- so the desired
        capital stock is `ticks_per_year` times too small and the measured K / annual GDP lands
        at ~0.004 instead of ~2.5. Capital then earns the Cobb-Douglas share alpha while costing
        almost nothing to replace: depreciation, the capital-service price term, collateral value
        and the P&L depreciation charge are all ~365x too small.

        The migration is JOINT, not a local patch on `v` (which alone would demand a 365x capital
        stock the economy has to build from a genesis stock sized for the old rule):

            v        -> v * S            desired capital now tracks ANNUAL output
            K_firm0  -> K_firm0 * S      genesis capital starts at the new scale
            A        -> A * S**(-alpha)  Cobb-Douglas output is EXACTLY invariant at genesis:
                                         A' K'^a = (A S^-a)(S K)^a = A K^a

        so genesis output, prices, wages and unit costs are bit-preserved, while the capital
        STOCK, its depreciation flow, its service cost and its collateral value all become
        economically meaningful. Default off => every existing preset is bit-identical.
        """
        if not self.capital_annual_clock:
            return
        if self._capital_annual_clock_applied:
            return                      # already migrated (e.g. copied through dataclasses.replace)
        scale = float(self.ticks_per_year)
        if scale <= 1.0:
            return
        self.v *= scale
        self.K_firm0 *= scale
        self.A *= scale ** (-self.alpha)
        # FINDING 5: damp the demand-expectation EMA that the now-912x-amplified capital target
        # reads, so the real-capital accelerator does not cycle on daily demand noise. Factor 1.0
        # leaves it unchanged (recovers the pre-fix clock behaviour for A/B comparison).
        self.lambda_d *= self.capital_clock_demand_smoothing
        self._capital_annual_clock_applied = True

    @property
    def capital_enabled(self) -> bool:
        """v2 is active when a capital-goods sector exists."""
        return self.n_firms_k > 0

    @_cached_view
    def banking(self):
        """Passive grouped view of banking parameters for future system extraction."""
        from macro_sim.config.schema import BankingConfig

        return BankingConfig(
            bank_enabled=self.bank_enabled,
            bank_realized_pnl=self.bank_realized_pnl,
            n_banks=self.n_banks,
            seed=self.seed,
            bank_leverage_mean=self.bank_leverage_mean,
            bank_leverage_disp=self.bank_leverage_disp,
            bank_assignment=self.bank_assignment,
            bank_capital_constraint=self.bank_capital_constraint,
            unified_bank_rwa=self.unified_bank_rwa,
            mortgage_risk_weight=self.mortgage_risk_weight,
            mortgage_min_capital_ratio=self.mortgage_min_capital_ratio,
            bank_migrate_on_failure=self.bank_migrate_on_failure,
            bank_target_capital_ratio=self.bank_target_capital_ratio,
            bank_exposure_limit=self.bank_exposure_limit,
            bank_rate_competition=self.bank_rate_competition,
            bank_relationship_lock_in=self.bank_relationship_lock_in,
            bank_spread_disp=self.bank_spread_disp,
            bank_search_m=self.bank_search_m,
            interbank=self.interbank,
            interbank_rate_base=self.interbank_rate_base,
            interbank_tightness=self.interbank_tightness,
            reserve_floor_frac=self.reserve_floor_frac,
            deposit_rate_disp=self.deposit_rate_disp,
            deposit_search_m=self.deposit_search_m,
            bank_equity=self.bank_equity,
            bank_equity_lambda=self.bank_equity_lambda,
            bank_equity_trading=self.bank_equity_trading,
            bank_theta_equity=self.bank_theta_equity,
            bank_dynamics=self.bank_dynamics,
            bank_min_capital=self.bank_min_capital,
            bank_entry_beta=self.bank_entry_beta,
            bank_entry_max=self.bank_entry_max,
            bank_runs=self.bank_runs,
            run_sensitivity=self.run_sensitivity,
            run_health_ref=self.run_health_ref,
            run_market_weight=self.run_market_weight,
            run_fear_persistence=self.run_fear_persistence,
            lolr=self.lolr,
            bank_resolution_fund=self.bank_resolution_fund,
            bonds=self.bonds,
            rho=self.rho,
            genesis_founder_pool=self.genesis_founder_pool,
            w_fundamental=self.w_fundamental,
            w_chartist=self.w_chartist,
            portfolio_adjust=self.portfolio_adjust,
            lambda_p=self.lambda_p,
            trend_lambda=self.trend_lambda,
        )

    @_cached_view
    def central_banking(self):
        """Passive grouped view of central-bank policy and reserve-quantity parameters."""
        from macro_sim.config.schema import CentralBankConfig

        return CentralBankConfig(
            central_bank=self.central_bank,
            r_interest=self.r_interest,
            infl_ema_lambda=self.infl_ema_lambda,
            u_natural=self.u_natural,
            r_neutral=self.r_neutral,
            r_max=self.r_max,
            omo=self.omo,
            bonds=self.bonds,
            interbank=self.interbank,
            omo_reserve_target=self.omo_reserve_target,
            omo_drain_frac=self.omo_drain_frac,
            omo_index_deposits=self.omo_index_deposits,
            cb_log_inflation=self.cb_log_inflation,
            reserve_floor_frac=self.reserve_floor_frac,
        )

    @_cached_view
    def capital_goods(self):
        """Passive grouped view of capital-goods market parameters."""
        from macro_sim.config.schema import CapitalGoodsConfig

        return CapitalGoodsConfig(
            capital_enabled=self.capital_enabled,
            government=self.government,
            gov_investment_share=self.gov_investment_share,
            rationed_signal=self.capital_rationed_signal,
        )

    @_cached_view
    def goods(self):
        """Passive grouped view of consumption-goods market parameters."""
        from macro_sim.config.schema import GoodsConfig

        return GoodsConfig(
            government=self.government,
            a=self.a,
            consumption_strata=self.consumption_strata,
            rationed_signal=self.consumption_rationed_signal,
            monetary_direct_transmission=self.monetary_direct_transmission,
            household_interest_arrears=self.household_interest_arrears,
        )

    @_cached_view
    def settlement(self):
        """Passive grouped view of settlement and household fiscal-flow parameters."""
        from macro_sim.config.schema import SettlementConfig

        return SettlementConfig(
            government=self.government,
            firm_full_pnl=self.firm_full_pnl,
            capital_service_pricing=self.capital_service_pricing,
            priced_firm_balance_sheet=self.priced_firm_balance_sheet,
            pro_rata_dividends=self.pro_rata_dividends,
            per_firm_equity=self.per_firm_equity,
            gov_investment_share=self.gov_investment_share,
            public_capital_depreciation=self.public_capital_depreciation,
            jg_productivity=self.jg_productivity,
        )

    @_cached_view
    def planning(self):
        """Passive grouped view of phase-1 planning parameters."""
        from macro_sim.config.schema import PlanningConfig

        return PlanningConfig(
            theta_wage=self.theta_wage,
            inventory_gap_close=self.inventory_gap_close,
            delta=self.delta,
            wage_indexation=self.wage_indexation,
            theta_price=self.theta_price,
            firm_full_pnl=self.firm_full_pnl,
            capital_service_pricing=self.capital_service_pricing,
            lambda_q=self.lambda_q,
            q_invest_floor=self.q_invest_floor,
            q_invest_cap=self.q_invest_cap,
            k_replacement_floor=self.k_replacement_floor,
            wealth_effect=self.wealth_effect,
            mpc_wealth_curvature=self.mpc_wealth_curvature,
            d_household0=self.d_household0,
            demographic_lifecycle_consumption=self.demographic_lifecycle_consumption,
            lifecycle_alpha_income=self.lifecycle_alpha_income,
            lifecycle_alpha_wealth_draw=self.lifecycle_alpha_wealth_draw,
            housing_wealth_effect=self.housing_wealth_effect,
            alpha2=self.alpha2,
            monetary_direct_transmission=self.monetary_direct_transmission,
            investment_user_cost_elasticity=self.investment_user_cost_elasticity,
            investment_user_cost_multiplier_min=self.investment_user_cost_multiplier_min,
            investment_user_cost_multiplier_max=self.investment_user_cost_multiplier_max,
            investment_user_cost_floor=self.investment_user_cost_floor,
            hh_amort=self.hh_amort,
        )

    @_cached_view
    def demographics(self):
        """Passive grouped view of demographic-economy integration parameters."""
        from macro_sim.config.schema import DemographicsConfig

        return DemographicsConfig(
            demographics_enabled=self.demographics_enabled,
            demographics_population=self.demographics_population,
            demographic_lifecycle_consumption=self.demographic_lifecycle_consumption,
            lifecycle_alpha_income=self.lifecycle_alpha_income,
            lifecycle_alpha_wealth_draw=self.lifecycle_alpha_wealth_draw,
            demographic_marriage_enabled=self.demographic_marriage_enabled,
            demographic_divorce_enabled=self.demographic_divorce_enabled,
            demographic_marriage_market_interval_days=self.demographic_marriage_market_interval_days,
            demographic_annual_marriage_rate_peak=self.demographic_annual_marriage_rate_peak,
            demographic_annual_divorce_rate_base=self.demographic_annual_divorce_rate_base,
            demographic_adult_leaving_home_enabled=self.demographic_adult_leaving_home_enabled,
            demographic_leave_home_min_age=self.demographic_leave_home_min_age,
            demographic_leave_home_peak_end_age=self.demographic_leave_home_peak_end_age,
            demographic_annual_leave_rate_peak=self.demographic_annual_leave_rate_peak,
            demographic_annual_leave_rate_late=self.demographic_annual_leave_rate_late,
            demo_feedback_burnin_years=self.demo_feedback_burnin_years,
            demo_signal_halflife_years=self.demo_signal_halflife_years,
            fertility_income_elasticity=self.fertility_income_elasticity,
            fertility_mult_lo=self.fertility_mult_lo,
            fertility_mult_hi=self.fertility_mult_hi,
            mortality_income_elasticity=self.mortality_income_elasticity,
            mortality_mult_lo=self.mortality_mult_lo,
            mortality_mult_hi=self.mortality_mult_hi,
        )

    @_cached_view
    def securities(self):
        """Passive grouped view of government securities parameters."""
        from macro_sim.config.schema import SecuritiesConfig

        return SecuritiesConfig(
            bonds=self.bonds,
            government=self.government,
            bond_maturity=self.bond_maturity,
            bond_maturity_bucket=self.bond_maturity_bucket,
            bond_coupon=self.bond_coupon,
            bond_finance_frac=self.bond_finance_frac,
            p_firm0=self.p_firm0,
            d_household0=self.d_household0,
            bond_theta=self.bond_theta,
            bank_bond_appetite=self.bank_bond_appetite,
            interbank=self.interbank,
            reserve_floor_frac=self.reserve_floor_frac,
            bank_bond_duration_limit=self.bank_bond_duration_limit,
        )

    @_cached_view
    def firm_demographics(self):
        """Passive grouped view of consumption-firm entry, exit, and growth parameters."""
        from macro_sim.config.schema import FirmDemographicsConfig

        return FirmDemographicsConfig(
            firm_dynamics=self.firm_dynamics,
            bankrupt_persist=self.bankrupt_persist,
            entry_hurdle=self.entry_hurdle,
            shell_exit_ticks=self.shell_exit_ticks,
            real_entry_signal=self.real_entry_signal,
            entry_beta=self.entry_beta,
            entry_max=self.entry_max,
            index_startup=self.index_startup,
            startup_deposits=self.startup_deposits,
            p_firm0=self.p_firm0,
            startup_capital=self.startup_capital,
            gibrat_growth=self.gibrat_growth,
            gibrat_sigma=self.gibrat_sigma,
            gibrat_entry_a0=self.gibrat_entry_a0,
            per_firm_equity=self.per_firm_equity,
            shares_per_firm=self.shares_per_firm,
        )

    @_cached_view
    def credit(self):
        """Passive grouped view of credit creation and debt-service parameters."""
        from macro_sim.config.schema import CreditConfig

        return CreditConfig(
            bank_enabled=self.bank_enabled,
            firm_full_pnl=self.firm_full_pnl,
            bank_realized_pnl=self.bank_realized_pnl,
            household_interest_arrears=self.household_interest_arrears,
            household_credit=self.household_credit,
            hh_subsistence=self.hh_subsistence,
            amort=self.amort,
            margin_credit=self.margin_credit,
            hh_amort=self.hh_amort,
            bank_target_capital_ratio=self.bank_target_capital_ratio,
            interbank=self.interbank,
            deposit_rate_disp=self.deposit_rate_disp,
            bank_equity=self.bank_equity,
            interest_by_deposits=self.interest_by_deposits,
            deposit_rate=self.deposit_rate,
            monetary_direct_transmission=self.monetary_direct_transmission,
            firm_credit_min_dscr=self.firm_credit_min_dscr,
        )

    @_cached_view
    def equity_market(self):
        """Passive grouped view of aggregate and per-firm equity-market parameters."""
        from macro_sim.config.schema import EquityConfig

        return EquityConfig(
            seed=self.seed,
            per_firm_equity=self.per_firm_equity,
            shares_per_firm=self.shares_per_firm,
            watchlist_size=self.watchlist_size,
            founder_owned_genesis=self.founder_owned_genesis,
            genesis_founder_pool=self.genesis_founder_pool,
            lambda_d=self.lambda_d,
            lambda_p=self.lambda_p,
            trend_lambda=self.trend_lambda,
            equity_ema_lambda=self.equity_ema_lambda,
            resid_income_lambda=self.resid_income_lambda,
            q_invest_smooth=self.q_invest_smooth,
            w_fundamental=self.w_fundamental,
            w_chartist=self.w_chartist,
            margin_credit=self.margin_credit,
            theta_equity=self.theta_equity,
            portfolio_adjust=self.portfolio_adjust,
            equity_finance=self.equity_finance,
            lambda_issue=self.lambda_issue,
            household_bankruptcy=self.household_bankruptcy,
            priced_firm_balance_sheet=self.priced_firm_balance_sheet,
        )

    @classmethod
    def v2(cls, **overrides) -> "Config":
        """Construct a v2 (investment + capital) config. Enables the capital sector
        (n_firms_k>0) with the PLAN_v2 §7 tentative defaults; override as needed."""
        base = dict(n_firms_c=500, n_firms_k=250, n_households=5000)
        base.update(overrides)
        return cls(**base)

    @classmethod
    def v25(cls, **overrides) -> "Config":
        """v2.5: symmetrized capital sector (§11.4). K-firms also use capital and
        invest, giving their retained earnings an outlet. Tests the falsifiable
        'partial cure' prediction for the secondary K-sink."""
        base = dict(n_firms_c=15, n_firms_k=10, symmetric_k=True)
        base.update(overrides)
        return cls(**base)

    @classmethod
    def v3(cls, **overrides) -> "Config":
        """v3: banks + endogenous money (§12). The v2 two-sector economy plus a single
        bank; firms borrow (B6) to cover cash gaps, loans create deposits (M2), the
        conservation anchor becomes A5. PLAN_v3 §7 tentative defaults; override as needed."""
        base = dict(n_firms_c=500, n_firms_k=250, n_households=5000, bank_enabled=True)
        base.update(overrides)
        return cls(**base)

    @classmethod
    def v4(cls, **overrides) -> "Config":
        """v4: firm entry/exit + bankruptcy (§13). v3 plus C-firm demographics — insolvent
        firms go bankrupt (bad debt absorbed by the bank), profitable sectors attract entry.
        Needs bank capital (bank_capital_frac) to absorb writeoffs. PLAN_v4 tentative defaults."""
        base = dict(n_firms_c=500, n_firms_k=250, n_households=5000,
                    bank_enabled=True, firm_dynamics=True, bank_capital_frac=0.05)
        base.update(overrides)
        return cls(**base)

    @classmethod
    def v5(cls, **overrides) -> "Config":
        """v5: diseconomies of scale (§14). v4 PLUS a coordination cost rising with the
        scale of operations (output). Defaults sit at the COMPETITIVE cell the phase
        diagram identified: dis_slope>0 AT LOW transparency (search_m=1). This is the
        surprise of §14 -- competition emerges from diseconomy + free entry/exit WITHOUT
        price transparency; m>=2 winner-take-all actively blocks it. The (m x dis_slope)
        phase diagram is the deliverable (sweep_v5.py); this default is its low-Gini corner."""
        base = dict(n_firms_c=500, n_firms_k=250, n_households=5000,
                    bank_enabled=True, firm_dynamics=True, bank_capital_frac=0.05,
                    search_m=1, dis_slope=0.005)
        base.update(overrides)
        return cls(**base)

    @classmethod
    def v6(cls, **overrides) -> "Config":
        """v6: capital market (§16). v4 PLUS a single aggregate equity index and household
        portfolio choice, activating choice 乙 (equity enters household wealth). Ships near the
        FUNDAMENTAL regime (w_chartist small) so the first economy is stable; Config.v6_bubble()
        raises the chartist weight to summon bubbles once the core is trusted. Note: v6 does NOT
        inherit v5's diseconomy (dis_slope=0) -- the equity layer is studied on the plain v4 base;
        add search_m/dis_slope overrides to combine."""
        base = dict(n_firms_c=500, n_firms_k=250, n_households=5000,
                    bank_enabled=True, firm_dynamics=True, bank_capital_frac=0.05,
                    capital_market=True, w_chartist=0.2, mpc_dispersion=0.4)
        base.update(overrides)
        return cls(**base)

    @classmethod
    def v6_bubble(cls, **overrides) -> "Config":
        """v6 with the chartist (bubble) knob turned up -- for studying bubble/crash and the
        money-conservation-through-crash result. w_chartist must be large enough (~20) to
        overwhelm the fundamentalist mean-reversion; below that the price stays near book.
        Blast radius is largest here; expect large q swings (bubbles to ~15x book, then crashes)."""
        base = dict(w_chartist=20.0, lambda_p=0.4)
        return cls.v6(**{**base, **overrides})

    @classmethod
    def v61a(cls, **overrides) -> "Config":
        """v6.1a: per-firm stock market, DISTRIBUTION only (§18). v6 core + per-firm equity +
        founder ownership + residual-income valuation, but the market is still a side-pot
        (lambda_q=0, wealth_effect=0) so production is untouched. Tests whether founder ownership
        + capital gains produce the T8 wealth tail without the endogenous-MPC thrift cost."""
        return cls.v6(**{**dict(per_firm_equity=True, lambda_q=0.0), **overrides})

    @classmethod
    def v61b(cls, **overrides) -> "Config":
        """v6.1b: adds q-driven investment (the financial->real channel) as a small multiplier on
        the accelerator. Turned on alone (wealth effect still off) to isolate it."""
        return cls.v6(**{**dict(per_firm_equity=True, lambda_q=0.3), **overrides})

    @classmethod
    def v62(cls, **overrides) -> "Config":
        """v6.2: equity finance (§19) -- the DIRECT financial->real channel. v6.1b (per-firm equity
        + q-investment) PLUS share issuance: a high-q firm issues shares to raise capex funds. With a
        bubble (raise w_chartist) this is where asset prices should finally drive a real investment
        boom-bust. Ships with both q-tilt and issuance on."""
        return cls.v6(**{**dict(per_firm_equity=True, lambda_q=0.3,
                                equity_finance=True, lambda_issue=0.2), **overrides})

    @classmethod
    def v7(cls, **overrides) -> "Config":
        """v7: household credit (§20), ADDED ON TOP of the full v6.2 financial stack -- configs are
        CUMULATIVE, no prior layer is dropped. So v7 carries: banks + firm credit + firm dynamics
        (v3/v4), per-firm equity + q-investment + equity finance (v6.1/v6.2), AND now households
        that borrow to defend a subsistence consumption floor. hh_subsistence is calibrated per
        scale; endogenous MPC / other regimes are experimental overrides, not baked into the base."""
        return cls.v62(**{**dict(household_credit=True, hh_subsistence=0.5,
                                 hh_credit_limit=2.0), **overrides})

    @classmethod
    def v8(cls, **overrides) -> "Config":
        """v8: household MARGIN credit (§21), added on top of the full v7 stack (cumulative).
        Households can borrow against their equity (LTV) to lever into stocks -- so borrowing brings
        an ASSET, leverage concentrates capital gains (T8), and price drops trigger margin calls →
        the credit-collateral crisis. Ships with margin on; raise w_chartist for a leveraged bubble."""
        return cls.v7(**{**dict(margin_credit=True, margin_ltv=0.5, margin_max=2.0), **overrides})

    @classmethod
    def v81(cls, **overrides) -> "Config":
        """v8.1: Gibrat multiplicative growth (§23), on the full v8 stack (cumulative). Firm market
        share random-walks multiplicatively and demand is allocated ∝ share^β; with entry/exit this
        is the Simon/Gabaix Zipf mechanism -- the missing multiplicative growth for T6 (firm size)
        AND, via the equity/margin chain, T8 (wealth). β≈1 for Zipf; a (σ,β) window gives clean tails."""
        return cls.v8(**{**dict(gibrat_growth=True, gibrat_sigma=0.05, pref_attach_beta=1.0), **overrides})

    @classmethod
    def v82(cls, **overrides) -> "Config":
        """v8.2: adaptive portfolio adjustment (§24), on the full v8.1 stack (cumulative). Households
        rebalance their equity only PARTIALLY toward the ideal each tick (the B2 adaptive-expectation
        discipline, previously missing on this one decision), so slow-delevering founders keep
        concentrated stakes in Gibrat winners -> concentrated ownership EMERGES and the wealth Pareto
        tail should clean up. λ set to λ_I (0.25), INDEPENDENTLY, not tuned to a target slope (§0-ii)."""
        return cls.v81(**{**dict(portfolio_adjust=0.25), **overrides})

    @classmethod
    def v83(cls, **overrides) -> "Config":
        """v8.3 (step 1): weaken the Tobin's-q → investment channel (§25) to match the empirically
        weak, sluggish q-elasticity -- lower lambda_q (0.3→0.1) and drive investment off a SMOOTHED q
        (firms ignore transient bubbles). Built on v8.1 (portfolio still instant; v8.2 re-tested in
        step 2 once this calms the economy). Calibrated on realism, NOT tuned to a target (§0-ii)."""
        return cls.v81(**{**dict(lambda_q=0.1, q_invest_smooth=0.1), **overrides})

    @classmethod
    def v84(cls, **overrides) -> "Config":
        """v8.4 (step 1): dividends flow to shareholders PRO-RATA (§26), on the full v8.3 stack
        (cumulative). Fixes the per-firm accounting inconsistency (we track holdings but paid
        dividends per capita). A correctness fix, not a tuned lever: on its own the still-diffuse
        genesis ownership means the wealth tail barely moves -- founder-owned genesis (step 2) and
        heterogeneous payout (step 3) come next. Nothing here is calibrated to a target (§0-ii)."""
        return cls.v83(**{**dict(pro_rata_dividends=True), **overrides})

    @classmethod
    def v85(cls, **overrides) -> "Config":
        """v8.5 (step 2): founder-owned genesis (§27), on the full v8.4 stack (cumulative). The
        genesis float vests in a minority founder class instead of splitting equally among all
        watchers, so a few households start with concentrated blocks -- the structural lever for the
        T8 wealth tail. Pre-registered risk: founders may rebalance their blocks down toward the
        theta_equity target, eroding concentration unless churn is also limited. Pool fraction
        anchored to real business-ownership rates (~10%), NOT tuned to a target slope (§0-ii)."""
        return cls.v84(**{**dict(founder_owned_genesis=True), **overrides})

    @classmethod
    def v9(cls, **overrides) -> "Config":
        """v9: the government sector (§28), on the full v8.5 stack (cumulative). A Treasury with four
        tax bases (profit, progressive income, VAT, wealth), two spends (consumption, unemployment
        benefit), the reclassified macroprudential caps, and household bankruptcy. Deficit issues
        outside money (GOV account goes negative). Every rate anchored to real magnitudes, NONE tuned
        to a §4 target (§0-ii). min_wage stays off by default (a lever, tested separately). Monetary
        policy (interest rate, bonds) is deferred to the separate central-bank layer (v10)."""
        return cls.v85(**{**dict(
            government=True,
            # deficit-targeting fiscal stance: government consumption is sized to MAINTAIN a ~3%-of-GDP
            # deficit (real-world normal range) -- tax-financed G plus a controlled deficit. The low
            # unemployment this yields is EMERGENT (functional finance: a demand-starved economy needs
            # a modest outside-money injection), NOT tuned to a target (§0-ii). Quantity mode (g=0.20)
            # overheats a stationary economy (u->0, debt explodes); deficit-targeting is self-limiting.
            gov_consumption_share=0.0, gov_deficit_target=0.03, deficit_u_ref=0.05, benefit_replacement=0.40,
            tax_profit_rate=0.25, tax_income_rate=0.20, income_allowance=0.50,
            tax_consumption_rate=0.15, tax_wealth_rate=0.002,   # ~0.2× the per-tick return r (real wealth
            #   taxes are a small fraction of the return, NOT of the stock/tick); flow taxes at real rates
            min_wage=0.0, household_bankruptcy=True,
        ), **overrides})

    @classmethod
    def v91(cls, **overrides) -> "Config":
        """v9.1: government INVESTMENT -> public capital -> productivity (§29), on the full v9 stack. The
        supply side -- government investment builds an economy-wide public capital stock that raises every
        firm's productivity (Barro 1990), giving the deficit a PRODUCTIVE outlet. THE VALIDATED RESULT:
        it flips the government from net-NEGATIVE (v9) to net-POSITIVE -- real output +37%, real consumption
        +38%, u 0.30->0.06 vs v9 (and above v8.5). §0-ii/§0-iv HONESTY: this uses STRONG parameters
        (g_I=0.10, γ=0.3) ~2-3× the empirical anchors (real public-inv/GDP ~4%, public-capital elasticity
        ~0.1); at anchored strength the effect is too weak to overcome v9's problems in this model. Not
        tuned to a §4 target -- tuned (honestly, above-anchor) to demonstrate the supply-side mechanism (§29)."""
        return cls.v9(**{**dict(gov_investment_share=0.10, public_capital_gamma=0.3), **overrides})

    @classmethod
    def v92(cls, **overrides) -> "Config":
        """v9.2: remove the fixed-nominal-startup money non-neutrality (§30), on the v9.1 supply-side stack.
        New firms' cash endowment is price-indexed (real-invariant entry), so inflation no longer starves
        entrants. Tests whether that artifact was the T6/inflation-concentration link and how much of the
        inflation 'cost' was a modeling bug vs a real friction. A correctness fix, not tuned (§0-ii)."""
        return cls.v91(**{**dict(index_startup=True), **overrides})

    @classmethod
    def v93(cls, **overrides) -> "Config":
        """v9.3: LABOR welfare on the v9.2 stack (§32). §31 found welfare at the bottom is an EMPLOYMENT story,
        so this adds a JOB GUARANTEE -- the government hires every household's residual (unemployed) labor at a
        transitional JG wage (jg_wage_ratio·mean wage), UNCAPPED (a buffer stock), paid as outside money; the
        public-works labor builds public capital (jg_productivity, reusing the v9.1 K_pub channel). It replaces
        the dole for takers; its deficit is an automatic stabilizer on top of the discretionary target. min_wage
        is now WIRED (a real statutory floor in plan_wage) but left OFF here -- tested as a separate probe, since
        a wage floor's disemployment effect cuts against the same channel. job_guarantee=False => v9.2 exactly."""
        return cls.v92(**{**dict(job_guarantee=True, jg_wage_ratio=0.5, jg_productivity=0.5), **overrides})

    @classmethod
    def v10(cls, **overrides) -> "Config":
        """v10: the CENTRAL BANK -- an endogenous policy interest rate (Taylor rule), on the v9.3 stack (§33).
        r_interest becomes a per-tick rate r = ρ·r_{-1} + (1-ρ)·[r* + φ_π·(π̄-π*) - φ_u·(u-u*)], clipped [0,r_max].
        The legacy entry, valuation and debt-service channels already read the rate, so
        this preset makes that rate respond to inflation and slack; direct demand decisions
        are enabled separately. **STANCE = 'gentle'** (§33 investigation): the target
        is anchored to the economy's own STRUCTURAL inflation (~0.012/tick, the fiscally-set level -- NOT a §4
        target, §0-ii), with moderate φ_π=1.2, φ_u=1.0. This is the tuned stance: v9.3's inflation is fiscally
        DOMINATED (deficit-driven, flat above zero deficit) so the CB cannot lower the level; its real job is
        STABILIZATION, and gentle delivers the lowest, most-stable inflation + best aggregate welfare -- at a
        (regressive) unemployment cost. The naive low target (0.001) over-tightens permanently (a diagnosed
        failure). central_bank=False => bit-identical to v9.3."""
        return cls.v93(**{**dict(central_bank=True, inflation_target=0.012, taylor_phi_pi=1.2,
                                 taylor_phi_u=1.0, rate_inertia=0.8), **overrides})

    @classmethod
    def v101(cls, **overrides) -> "Config":
        """v10.1: the bank pays interest BY DEPOSITS (∝ D_h), not split equally, on the v10 stack (§33). Fixes
        the v3 equal-split shortcut that paid interest even to zero-deposit households -- the root of v10's
        over-strong interest-income demand channel. A correctness fix (no separate deposit rate yet); pre-
        registers whether routing interest to savers flattens the rate-output hump toward conventional (§0-ii).
        interest_by_deposits=False => bit-identical to v10."""
        return cls.v10(**{**dict(interest_by_deposits=True), **overrides})

    @classmethod
    def v102(cls, **overrides) -> "Config":
        """v10.2: PROGRESSIVE wealth tax -- a threshold (exempt below 1× mean net worth) on the v10.1 stack (§34).
        The flat wealth tax taxed even zero/low-net-worth hand-to-mouth households, destroying their demand; a
        threshold spares them so only above-average wealth pays. At the SAME rate (0.002) this is decisively
        PRO-POOR and lowers unemployment (bottom-decile C +9%, income poverty ~halved, u 0.083->0.057) while
        cutting concentration MORE (better targeted at the rich). Anchored to real wealth taxes, which all carry
        a large exemption (§0-ii). wealth_allowance=0 => flat => bit-identical to v10.1."""
        return cls.v101(**{**dict(wealth_allowance=1.0), **overrides})

    @classmethod
    def v11(cls, **overrides) -> "Config":
        """v11: MULTI-BANK ("loan-book banks", §35) on the v10.2 stack. The loan book is partitioned among
        n_banks accounts, each a FINITE capital buffer (its own deposit balance) with a heterogeneous leverage
        cap κ_bank (RISK APPETITE). Banks pay out to stay THIN (capital ≈ loan_book/κ), fail when write-offs
        exhaust capital, and their borrowers MIGRATE (contagion via the real economy). Endogenous bank crises
        are STATE-DEPENDENT -- they need concentration + thin capital + volatility, so on the stable full-
        employment frontier they are ~dormant (few defaults; §35 shows them on fragile/concentrated bases).
        n_banks=1 OR bank_capital_constraint=False ⇒ bit-identical to v10.2."""
        return cls.v102(**{**dict(n_banks=8, bank_capital_constraint=True, bank_leverage_mean=10.0,
                                  bank_leverage_disp=0.6), **overrides})

    @classmethod
    def v112(cls, **overrides) -> "Config":
        """v11.2: a REALISTIC bank capital regime on the v11 multi-bank stack (§35). Two real institutions
        replace the (unrealistic) unbounded ρ-hoard: (1) a Basel-like CAPITAL RATIO -- banks pay out earnings
        above target capital = 0.1·loan_book (~the real bank leverage ratio) ⇒ capital is BOUNDED & thin like a
        real bank; (2) a LARGE-EXPOSURE limit -- a single borrower ≤ 0.25·(bank capital) (Basel) ⇒ banks are
        DIVERSIFIED, so a thin bank survives any single default and fails only in a genuine loss WAVE. Params
        anchored to reality (§0-ii) -- the resulting failure rate is REPORTED, not tuned. Off ⇒ v11."""
        return cls.v11(**{**dict(bank_target_capital_ratio=0.1, bank_exposure_limit=0.25), **overrides})

    @classmethod
    def v113(cls, **overrides) -> "Config":
        """v11.3: loan-rate COMPETITION on the v11.2 realistic-bank stack (§36). Banks post heterogeneous
        loan-rate spreads over the policy rate (mean-preserving -- some undercut, some charge more), and
        borrowers SHOP for the cheapest bank with capacity. So market share is won on PRICE + capacity, not
        assigned at genesis: cheap, well-capitalized banks grow their loan book and concentration / too-big-to-
        fail EMERGES. bank_spread_disp anchored to real cross-bank loan-rate dispersion (~a third of the policy
        rate); the resulting concentration + any failures are REPORTED, not tuned (§0-ii). Off ⇒ bit-identical
        to v11.2."""
        return cls.v112(**{**dict(bank_rate_competition=True, bank_spread_disp=0.003, bank_search_m=2), **overrides})

    @classmethod
    def v114(cls, **overrides) -> "Config":
        """v11.4: deposit partitioning + a RESERVE tier + the INTERBANK market (full intra-tick RTGS), on the
        v11.3 stack (§37). Every payment settles reserves between banks in real time; a reserve-short bank
        borrows interbank at an endogenous (tightness-driven) rate; payments can GRIDLOCK at the intraday-credit
        limit; failures cascade through interbank claims; and banks compete on a deposit rate. Params anchored
        to reality (§0-ii); emergent behaviour reported, not tuned. Off ⇒ v11.3 bit-identical."""
        # deposit_rate_disp defaults to 0 (deposit competition OFF): with reserves hyper-abundant there is no
        # genuine funding-scarcity DRIVER for deposit competition, so imposed exogenous deposit spreads degenerate
        # (monopoly + sector collapse) rather than equilibrate -- a §37 finding. The machinery is opt-in
        # (deposit_rate_disp>0) but off in the shipped config; the real unlock is a bond layer (scarce reserves).
        return cls.v113(**{**dict(interbank=True, interbank_rate_base=0.0, interbank_tightness=0.5,
                                  reserve_floor_frac=0.25, deposit_rate_disp=0.0), **overrides})

    @classmethod
    def v115(cls, **overrides) -> "Config":
        """v11.5: bank DEMOGRAPHICS & OWNERSHIP on the v11.4 stack (§38). Banks are OWNED (a founder class holds
        the genesis banks; profit → shareholder dividends; a tradeable bank-stock market whose valuation is also a
        run distress signal), FOUNDED de novo when banking is profitable (so the count stops decaying to
        oligopoly), and can die from a RUN (queued withdrawals from own reserves + panic/contagion). Params
        anchored; emergent results reported, not tuned. Each sub-flag off ⇒ bit-identical to v11.4."""
        return cls.v114(**{**dict(
            bank_equity=True, bank_equity_trading=True, bank_theta_equity=0.1,
            # bank_min_capital anchored HIGH (~2× a genesis bank's capital): real de-novo banks must be WELL-
            # capitalised, so entrants SURVIVE (long-lived) rather than dying fast → realistic LOW churn (a few
            # births/deaths over thousands of ticks), not the firm-like near-total turnover thin entrants caused.
            bank_dynamics=True, bank_min_capital=1500.0, bank_entry_beta=0.02, bank_entry_max=1,
            bank_runs=True, run_sensitivity=8.0, run_health_ref=0.1, run_market_weight=0.5,
        ), **overrides})

    @classmethod
    def v12(cls, **overrides) -> "Config":
        """v12 (securities arc) on the v11.5 stack (§39). v12.0 un-consolidated the CB/Treasury (GOV → TSY + CB,
        a proper CB balance sheet + TGA); v12.1 finances `bond_finance_frac` of the government debt with one-period
        PAR bills held by households (deposit↔bill swaps that STERILISE reserves -- drain bank reserves to the CB).
        Default frac=0.9 (most real govt debt is bonds). FINDING (§39): sterilisation drains bank reserves from
        M₀+deficit down to the M₀ FLOOR, but M₀ ≫ payment flows, so the interbank keystone stays latent -- full
        activation needs OMO (the CB draining below M₀ by selling bonds), deferred to v12.4. `bonds=False` OR
        `bond_finance_frac=0` ⇒ bit-identical to v11.5. Coupons/duration/traded market/OMO are later v12.x."""
        return cls.v115(**{**dict(bonds=True, bond_finance_frac=0.9, bond_coupon=0.0, bond_theta=0.0), **overrides})

    @classmethod
    def v123(cls, **overrides) -> "Config":
        """v12.3 (§39.5) on the v12 base: bonds gain MATURITY + a COUPON + a market price, so the three values
        (face/book/market) DIVERGE — the duration/SVB channel. Households target `bond_theta` of wealth in bonds
        (a liquid safe asset that pays coupon ⇒ a MEANINGFUL stock forms, unlike the v12.1-fix thin residual);
        banks put `bank_bond_appetite` of excess reserves into bonds (money-creating ⇒ the STRONG reserve drain);
        a rate HIKE marks multi-period bonds below face ⇒ `economic_capital` thins ⇒ crunch/failure/runs (SVB).
        Every new lever at its off-default ⇒ the v12.1-fix economy; `bonds=False` ⇒ bit-identical to v11.5."""
        # bank_bond_appetite defaults to 0: the bank balance-sheet primitives (money-creating bond purchase,
        # `_bank_securities`, economic_capital) are BUILT + conservation-verified, but activating the live bank
        # bond drain collapses the thin-equity sector -- it needs the capital floor + LoLR of v12.4.
        # BANK-SECTOR HEALTH (a user-driven fix): v12.3's `bond_theta` deposit-drain + the fixed `bank_min_capital`
        # =1500 (unaffordable at NH2000 ⇒ 0 births) made the sector BLEED to 0 over long horizons. The fix is BOTH
        # sides: thicker capital (`bank_target_capital_ratio` 0.1→0.18, `bank_exposure_limit` 0.25→0.15 ⇒ fewer
        # deaths) AND a founder threshold the wealth distribution can actually clear (`bank_min_capital` 1500→400
        # ⇒ births ~keep pace, low churn). At NH2000/4000t this holds the count at ~11 (births≈deaths), not 0.
        return cls.v12(**{**dict(bond_coupon=0.01, bond_theta=0.15, bond_maturity=8, bank_bond_appetite=0.0,
                                 bank_target_capital_ratio=0.18, bank_exposure_limit=0.15, bank_min_capital=400.0),
                          **overrides})

    @classmethod
    def v124(cls, **overrides) -> "Config":
        """v12.4 (§39.6): the CB's QUANTITY tools close the securities arc. OMO drains reserves toward a target
        (reverse repo / CB bills) ⇒ reserves turn SCARCE ⇒ the latent §37 interbank market BINDS; LoLR funds an
        illiquid-but-solvent bank in a run ⇒ no suspension cascade; a duration limit caps each bank's bond book at
        k·economic capital ⇒ SVB losses are bounded. This is the HEALTHY default (on the v123 bank-health base):
        GENTLE OMO (target = genesis reserves, slow drain) + a LIGHT, SHORT bank bond book, so the CB tools + a
        live bank bond drain run WITHOUT collapsing the sector -- at NH2000/4000t the bank count holds ~11. For the
        interbank-activation STRESS test (drain reserves hard ⇒ overdrafts + a heavy long bank book ⇒ SVB), use
        `Config.v124_stress()`. Every new lever off ⇒ v123; bonds off ⇒ v11.5."""
        return cls.v123(**{**dict(omo=True, lolr=True, omo_reserve_target=1.0, omo_drain_frac=0.03,
                                  bank_bond_appetite=0.03, bank_bond_duration_limit=0.5, bond_maturity=4,
                                  bank_resolution_fund=True),
                           **overrides})

    @classmethod
    def v124_stress(cls, **overrides) -> "Config":
        """v12.4 STRESS test: drain reserves HARD (`omo_reserve_target`=0.3·genesis) so the §37 interbank market
        BINDS (peak overdraft ≫ 0), and load banks with a HEAVY, LONG-duration bond book (`bank_bond_appetite`=0.2,
        `bank_bond_duration_limit`=2, `bond_maturity`=8) so the SVB channel bites. NOT a healthy baseline -- it
        deliberately stresses the funding + duration channels to exhibit them (some banks fail; that is the point)."""
        return cls.v124(**{**dict(omo_reserve_target=0.3, omo_drain_frac=0.1, bank_bond_appetite=0.2,
                                  bank_bond_duration_limit=2.0, bond_maturity=8), **overrides})

    @classmethod
    def v13(cls, **overrides) -> "Config":
        """v13: the demographic economy on a ONE-CALENDAR-DAY tick (the tick the demographic kernel
        already assumes: kernel.py advances current_date by 1 day; ticks_per_year=365 throughout).

        The v12.x rate family was calibrated for an abstract 'period' tick; run on a day calendar it
        pays annual-scale rates 365x too often -- the 10k x 3650t audit traced the 45x price level,
        the 116M debt snowball (coupon 1%/tick = the whole cash deficit), the -111M reserves and the
        44% poverty rate to exactly that mismatch. This preset bakes in:

        1. configs/calibrations/daily_tick.yaml (rates, adjustment speeds, EMAs / 365-day scale)
        2. structural hygiene: demand price-elasticity ON (zero elasticity left NO price-competition
           channel: markups saturated at mu_max from t29 and HHI ran 0.6-0.9), a REAL entry signal +
           idle-shell exit (entry pegged at entry_max for 10 years while shells never died), the K
           replacement floor (net capital formation had gone negative), zero entrant inventory
           (3/tick x 10 units of goods appeared ex nihilo)
        3. policy plumbing: deposit-indexed OMO reserve target and the log inflation sensor
        4. demographics enabled at the 10k-person default of the visualization harness
        """
        daily = dict(
            # planning, expectations, price, wage, consumption
            lambda_d=0.0076, lambda_y=0.0076, theta_price=0.0037,
            # wage Calvo: ~quarterly resets with ~0.75% moves (effective ~3%/yr). daily_tick.yaml
            # scaled BOTH the hazard and the step -- the product (the actual adjustment speed)
            # came out 7e-7/tick and posted wages froze at 1.000 for entire runs
            theta_wage=0.011,
            alpha2=5.5e-5,
            # inventory: two weeks of demand cover, closed ~5%/day. daily_tick.yaml said phi=60
            # (a quarter's 0.75 cover re-read in days) but plan_production closes the WHOLE gap
            # in one tick -- every firm demanded ~60 days of output at once (labor fill hit 2%)
            phi=14.0, inventory_gap_close=0.05,
            # markup step (continuous, per tick): mu walked 0.05/day to its cap within a
            # month at period scale; 6.7e-4/day drifts ~9pp of markup per year
            eta=6.7e-4,
            # wage step per Calvo reset (see theta_wage above); delta is set in `structural`
            omega=0.0075,
            # production, investment, capital
            lambda_I=0.0019, delta_K=2.28e-4, lambda_q=0.0076, q_invest_smooth=1.0,
            public_capital_depreciation=2.28e-4,
            # credit, interest, debt service
            r_interest=1.34e-4, r_neutral=1.34e-4, r_max=5.0e-4,
            amort=0.0011, hh_amort=5.5e-4, bank_spread_disp=4.466666666666667e-5,
            interbank_rate_base=0.0, interbank_tightness=0.0013698630136986301,
            deposit_rate_disp=0.0,
            # central bank and inflation rule
            inflation_target=5.4e-5, infl_ema_lambda=0.0019, rate_inertia=0.9924,
            taylor_phi_u=0.0014, omo_drain_frac=0.094,
            # securities
            bond_coupon=1.08e-4, bond_maturity=365,
            # firm entry/exit and growth
            bankrupt_persist=548, gibrat_sigma=0.0052,
            # equity, portfolios, margin, bank equity
            lambda_p=0.13, trend_lambda=0.023, equity_ema_lambda=0.0076,
            resid_income_lambda=0.0019, portfolio_adjust=0.048,
            bank_equity_lambda=0.0019, run_fear_persistence=0.952,
            # fiscal stock tax (flow tax rates stay ratios on current flows)
            tax_wealth_rate=5.479452054794521e-6,
        )
        structural = dict(
            # v9.1 deliberately inherited demonstration-strength public-capital
            # parameters (10% investment, gamma=0.3).  They are documented there
            # as 2--3x empirical anchors and are not a defensible daily production
            # baseline: with the slower daily depreciation they drive the public-
            # capital multiplier above 3 within two years.  Keep the historical
            # v9.1--v12 presets intact, but put v13 on the anchors stated by the
            # original design (roughly 4% public investment and gamma=0.1).
            gov_investment_share=0.04,
            public_capital_gamma=0.10,
            pref_price_elasticity=1.0,   # restore the demand-side price brake (R3)
            real_entry_signal=True,      # deflated entry signal + zero entrant inventory (R5/A2)
            shell_exit_ticks=365,        # idle shells liquidate after a year (R5)
            k_replacement_floor=True,    # K-firms at least replace depreciation (R6)
            delta=0.0075,                # symmetric downward wage step when hiring is easy (escapes the ZLB deflation ratchet)
            entry_hurdle=1.34e-4,        # ~5%/yr equity premium: entry needs profit above rate + premium, not just above a floored rate
            omo_index_deposits=True,     # reserve target follows deposits, not genesis (R4)
            cb_log_inflation=True,       # Jensen-free inflation sensor (M1)
            demographics_enabled=True,
            demographic_lifecycle_consumption=True,
            pension_replacement=0.4,     # old-age pension at the unemployment-benefit replacement rate
            deficit_u_cap=4.0,           # fiscal stimulus scales with slack (up to 4x the 3%-GDP target)
        )
        return cls.v124(**{**daily, **structural, **overrides})

    def _validate(self) -> None:
        """Guard the axiom-forced relations up front (fail loud, not silently)."""
        assert self.a > 0, "productivity a must be > 0 (spec §8.1 degenerate guard)"
        assert self.w_firm0 > 0, "initial wage must be > 0 before w/a and floor(D/w)"
        assert 0 < self.alpha2 < self.alpha1 < 1, "B1 requires 0 < alpha2 < alpha1 < 1"
        assert not self.cb_uses_fixed_basket_cpi or self.national_accounts_metrics, \
            "fixed-basket CPI policy input requires national-accounts metrics"
        assert not self.cb_uses_fixed_basket_cpi or self.central_bank, \
            "fixed-basket CPI policy input requires the central bank"
        assert not self.fiscal_uses_national_accounts_gdp or self.national_accounts_metrics, \
            "national-accounts fiscal input requires national-accounts metrics"
        assert not self.fiscal_uses_national_accounts_gdp or self.government, \
            "national-accounts fiscal input requires government"
        assert (isinstance(self.cpi_rebase_interval_days, int)
                and not isinstance(self.cpi_rebase_interval_days, bool)
                and self.cpi_rebase_interval_days >= 1), \
            "fixed-basket CPI rebase interval must be a positive integer number of days"
        assert self.demographics_population >= 0, "demographics_population must be >= 0"
        assert self.demographics_tfr >= 0.0, "demographics_tfr must be >= 0"
        assert self.demographics_mortality_scale > 0.0, "demographics_mortality_scale must be > 0"
        assert self.lifecycle_alpha_income >= 0.0 and self.lifecycle_alpha_wealth_draw >= 0.0, "lifecycle alphas must be >= 0"
        assert self.demographic_marriage_market_interval_days >= 1, "demographic marriage interval must be >= 1 day"
        assert self.demographic_annual_marriage_rate_peak >= 0.0, "demographic marriage rate must be >= 0"
        assert self.demographic_annual_divorce_rate_base >= 0.0, "demographic divorce rate must be >= 0"
        assert self.demographic_leave_home_min_age >= 0, "leave-home min age must be >= 0"
        assert self.demographic_leave_home_peak_end_age >= self.demographic_leave_home_min_age, "leave-home peak end must be >= min age"
        assert self.demographic_annual_leave_rate_peak >= 0.0 and self.demographic_annual_leave_rate_late >= 0.0, "leave-home rates must be >= 0"
        assert self.demo_feedback_burnin_years >= 1, "demo feedback burn-in must be >= 1 year"
        assert self.demo_signal_halflife_years > 0.0, "demo signal half-life must be > 0"
        assert self.fertility_income_elasticity >= 0.0 and self.mortality_income_elasticity >= 0.0, "feedback elasticities must be >= 0"
        assert 0.0 < self.fertility_mult_lo <= 1.0 <= self.fertility_mult_hi, "fertility multiplier bounds must bracket the neutral 1.0"
        assert 0.0 < self.mortality_mult_lo <= 1.0 <= self.mortality_mult_hi, "mortality multiplier bounds must bracket the neutral 1.0"
        assert self.mortality_rank_gradient >= 0.0, "mortality rank gradient must be >= 0 (rich live longer)"
        assert 0.0 < self.strat_mult_lo <= 1.0 <= self.strat_mult_hi, "stratum multiplier bounds must bracket the neutral 1.0"
        assert self.house_price_income_years > 0.0, "housing genesis anchor must be > 0"
        assert not (self.housing_market_enabled and not self.housing_enabled), "housing market requires the registry"
        assert self.housing_session_interval >= 1, "housing session interval must be >= 1 tick"
        assert 0.0 <= self.housing_ask_decay < 1.0 and 0.0 <= self.housing_forced_discount < 1.0, "housing ask cuts are fractions"
        assert 0.0 <= self.housing_buyer_buffer < 1.0, "housing buyer buffer is a deposits fraction"
        assert self.housing_search_k >= 1, "buyers must see at least one listing"
        assert not (self.mortgage_enabled and not self.housing_market_enabled), "mortgages require the resale market"
        assert 0.0 < self.mortgage_ltv_cap < 1.0, "mortgage LTV cap is a fraction of price"
        assert self.mortgage_foreclosure_ltv >= 1.0, "foreclosure triggers only underwater (>= 1x collateral)"
        assert not self.mortgage_underwriting or self.mortgage_enabled, "mortgage underwriting requires mortgages"
        assert not self.mortgage_underwriting or self.bank_enabled, "mortgage underwriting requires banks"
        assert 0.0 < self.mortgage_dsti_cap <= 1.0, "mortgage DSTI cap must be in (0, 1]"
        assert self.mortgage_stress_rate_addon >= 0.0, "mortgage stress-rate add-on is per-tick and non-negative"
        assert self.mortgage_risk_weight > 0.0, "mortgage risk weight must be positive"
        assert self.mortgage_min_capital_ratio > 0.0, "mortgage capital ratio must be positive"
        assert not self.unified_bank_rwa or self.bank_enabled, "unified bank RWA requires banks"
        assert not (self.unified_bank_rwa and self.mortgage_enabled) or self.mortgage_underwriting, (
            "unified bank RWA requires mortgage underwriting when mortgages are enabled"
        )
        assert not (self.housing_rental_enabled and not self.housing_market_enabled), "rentals require the resale market"
        assert not (self.housing_construction_enabled and not self.housing_market_enabled), "construction requires the resale market"
        assert self.housing_signal_burnin_years >= 1, "housing signal burn-in must be >= 1 year"
        assert self.housing_leave_elasticity >= 0.0 and self.housing_fertility_elasticity >= 0.0, "housing coupling elasticities must be >= 0"
        assert 0.0 < self.housing_leave_mult_lo <= 1.0 <= self.housing_leave_mult_hi, "leave multiplier bounds must bracket 1.0"
        assert 0.0 < self.housing_fertility_mult_lo <= 1.0 <= self.housing_fertility_mult_hi, "housing fertility bounds must bracket 1.0"
        assert not ((self.housing_leave_elasticity > 0.0 or self.housing_fertility_elasticity > 0.0)
                    and not self.housing_rental_enabled), "housing couplings need the rental market (rent signal)"
        assert self.n_builders >= 1 or not self.housing_construction_enabled, "construction needs at least one builder"
        assert self.builder_productivity > 0.0 and 0.0 <= self.land_fee_share and self.land_convexity >= 0.0, "builder params out of range"
        assert self.housing_permits >= 0, "permit quota must be >= 0"
        assert 0.0 <= self.housing_transfer_tax < 1.0 and 0.0 <= self.housing_property_tax < 1.0, "housing tax rates are fractions"
        assert self.housing_wealth_effect >= 0.0, "housing wealth effect must be >= 0"
        assert self.labor_matching in ("spot", "persistent"), "labor_matching must be 'spot' or 'persistent'"
        assert not (self.labor_matching == "persistent" and not self.demographics_enabled), "persistent labor needs persons (demographics)"
        assert not (self.labor_matching == "persistent" and not self.labor_accounting), "persistent labor requires the accounting gate"
        assert not (self.labor_fractional_hours and self.labor_matching != "persistent"), "fractional hours need persistent jobs"
        assert 0.0 <= self.churn_annual < 1.0 and 0.0 < self.lambda_fire <= 1.0 and self.layoff_band >= 0.0, "labor dynamics params out of range"
        assert not (self.labor_suspension and self.labor_matching != "persistent"), "suspension needs persistent rosters"
        # v23 P0: under the annual capital clock the K sector must actually SUPPLY the
        # (now economically real) replacement flow. a_K=1.0 was never calibrated -- with the
        # broken clock the K sector was inert, so its productivity never bound. At a_K=1.0 a
        # 2.5x-GDP capital stock needs ~1/3 of the labour force to maintain, which starves the
        # C sector and drives a cost-push spiral (measured: -15%/yr growth, CPI 4.1x). Capital
        # and consumption goods carry the SAME genesis price, so they must embody comparable
        # labour per unit: a_K should track C-sector labour productivity (~2.4 measured).
        assert not (self.capital_annual_clock and self.a_K <= 1.0), (
            "capital_annual_clock needs a calibrated capital-goods productivity: a_K<=1.0 makes "
            "the K sector consume ~1/3 of labour (cost-push spiral). Set a_K ~ C-sector labour "
            "productivity (~2.4)."
        )
        assert self.tfp_law in ("exogenous", "learning"), "tfp_law must be 'exogenous' or 'learning'"
        assert self.tfp_drift_sigma >= 0.0, "tfp_drift_sigma is a std, must be >= 0"
        assert self.tfp_learning_theta >= 0.0, "tfp_learning_theta must be >= 0"
        assert self.suspension_timer >= 1 and 0.0 < self.suspension_quit_discount <= 1.5, "suspension params out of range"
        assert not (self.labor_person_efficiency and self.labor_matching != "persistent"), "person efficiency needs persistent rosters (e_i lives on hires)"
        assert self.efficiency_sigma >= 0.0, "efficiency_sigma must be non-negative"
        assert not (self.labor_participation and self.labor_matching != "persistent"), "participation margin needs persistent rosters"
        assert self.reservation_markup >= 0.0 and 0.0 <= self.welfare_quit_hazard <= 1.0, "participation params out of range"
        assert self.subscale_viability_workers >= 0.0 and self.subscale_grace_days >= 1, "subscale exit params out of range"
        assert 0.0 <= self.subscale_exit_hazard <= 1.0, "subscale_exit_hazard is a daily probability"
        assert self.k_entry_demand >= 1.0 and 0.0 <= self.k_entry_hazard <= 1.0, "K entry params out of range"
        assert not (self.labor_matching_friction and self.labor_matching != "persistent"), "matching friction needs persistent rosters"
        assert not (self.labor_relationship_wages and self.labor_matching != "persistent"), "relationship wages need persistent rosters"
        assert not (self.labor_job_ladder and not self.labor_relationship_wages), "the job ladder needs relationship wages (it compares against job.wage)"
        assert 0.0 < self.ladder_search_intensity <= 1.0 and self.ladder_premium >= 0.0, "ladder params out of range"
        assert 0.0 < self.job_search_intensity <= 1.0 or not self.labor_matching_friction, "search intensity is a daily contact probability"
        assert self.rent_yield0 > 0.0 and 0.0 <= self.rent_adjust < 1.0, "rent level params out of range"
        assert 0.0 < self.rent_burden_cap <= 1.0, "rent burden cap is an income fraction"
        assert self.rental_eviction_arrears >= 1, "eviction needs at least one missed tick"
        # v17.0 energy guards
        assert self.n_firms_e >= 1 or not self.energy_enabled, "energy needs at least one E-firm"
        assert self.energy_intensity >= 0.0, "energy intensity must be >= 0"
        assert self.energy_coverage_ticks >= 0.0, "energy coverage target must be >= 0"
        assert 0.0 < self.energy_gap_close <= 1.0, "energy restock throttle in (0,1]"
        assert self.kappa_E > 0.0 and self.a_E > 0.0, "E-sector productivities must be > 0"
        assert 0.0 < self.energy_util0 <= 1.0, "genesis utilization is a fraction"
        assert 0.0 <= self.tax_energy_rate < 1.0, "energy excise is a fraction"
        assert not (self.energy_household and not self.energy_enabled), "household energy requires the E-sector"
        assert 0.0 < self.energy_hh_share < 1.0, "household energy share anchor is a fraction"
        assert not (self.energy_shock_at > 0 and not self.energy_enabled), "the capacity shock needs the E-sector"
        assert 0.0 <= self.energy_shock_magnitude < 1.0, "shock magnitude is a fractional capacity cut"
        assert self.energy_shock_duration >= 0, "shock duration must be >= 0 (0 = permanent)"
        assert 0.0 <= self.tax_energy_windfall < 1.0, "windfall surtax is a fraction"
        assert self.spr_target_units >= 0.0 and self.spr_flow_cap >= 0.0, "SPR params must be >= 0"
        assert not (self.spr_target_units > 0.0 and not (self.energy_enabled and self.government)), \
            "the SPR needs the E-sector and a fiscal account"
        assert not (self.soe_efirm and not (self.energy_enabled and self.government)), \
            "the SOE needs the E-sector and a fiscal account"
        assert not (self.soe_price_at_cost and not self.soe_efirm), "at-cost pricing needs the SOE"
        assert self.energy_hoarding_beta >= 0.0, "hoarding beta must be >= 0"
        assert self.energy_price_cap >= 0.0, "the price cap must be >= 0 (0 = off)"
        assert self.energy_rationing in ("market", "household_first", "industry_first", "proportional"), \
            "unknown energy rationing rule"
        assert not (self.energy_cap_compensation and not self.government), \
            "cap compensation needs a fiscal account"
        assert self.energy_mortality_gamma >= 0.0, "mortality gamma must be >= 0"
        assert self.energy_mortality_mult_hi >= 1.0, "mortality cap must be >= 1"
        assert self.energy_signal_burnin_years >= 1, "energy signal burn-in must be >= 1 year"
        assert 0.0 <= self.energy_subsidy_rate < 1.0, "subsidy rate is a fraction"
        assert self.energy_subsidy_threshold >= 0.0, "subsidy threshold must be >= 0"
        assert not (self.energy_mortality_gamma > 0.0 and not self.energy_household), \
            "the fuel-poverty mortality channel needs household energy"
        # v18.0 deprivation gauges (observation only)
        assert not (self.deprivation_gauges and not self.demographics_enabled), \
            "deprivation gauges need person-level consumption (demographics)"
        assert 0.0 < self.subsistence_share <= 1.0, \
            "subsistence share is a fraction of mean per-capita consumption"
        assert self.deprivation_burnin_years >= 1, "deprivation burn-in must be >= 1 year"
        assert self.deprivation_acute_days >= 1 and self.deprivation_chronic_days >= 1, \
            "deprivation spell thresholds must be >= 1 day"
        # v18.1 sector split
        assert 0.0 < self.necessity_share0 < 1.0, "necessity share is a fraction of goods consumption"
        assert 0.0 < self.n_firm_share < 1.0, "necessity-firm share must be a strict fraction"
        assert not (self.consumption_strata and self.n_firms_c < 2), \
            "the sector split needs at least 2 c-firms (one per sector)"
        # v18.4 family transfers
        assert self.family_transfer_buffer >= 1.0, "the donor buffer must be >= 1 (keep own need first)"
        assert not (self.family_transfers and not self.consumption_strata), \
            "family transfers need the necessity price (the sector split)"
        assert not (self.family_transfers and not self.demographics_enabled), \
            "family transfers need person-level kin links (demographics)"
        # v18.5 sector switching
        assert 0.0 <= self.switch_retool_loss < 1.0, "retool loss is a fraction of capital"
        assert 0.0 <= self.switch_hazard <= 1.0, "switch hazard is a daily probability"
        assert self.switch_return_gap >= 0.0 and self.switch_pressure_days >= 1, \
            "switch gap/pressure must be non-negative / >= 1 day"
        assert not (self.sector_switching and not self.consumption_strata), \
            "sector switching needs the necessity/luxury split"
        assert 0.0 <= self.theta_price <= 1.0, "theta_price is a probability"
        assert 0.0 <= self.theta_wage <= 1.0, "theta_wage is a probability"
        assert self.mu_min <= self.mu_max, "markup bounds out of order"
        assert 0.0 <= self.rho <= 1.0, "dividend payout ratio must be in [0,1]"
        assert 0.0 <= self.firm_capital_haircut <= 1.0, \
            "firm capital haircut must be in [0,1]"
        assert 0.0 <= self.firm_inventory_haircut <= 1.0, \
            "firm inventory haircut must be in [0,1]"
        assert 0.0 <= self.delta < 0.01, "delta is a SLOW downward wage drift (v12 strict DNWR = 0; v13 allows a small positive step)"
        assert self.n_firms > 0 and self.n_households > 0
        # v2 guards (only bite when capital is enabled, but cheap to always check)
        assert 0.0 < self.alpha < 1.0, "Cobb-Douglas capital share alpha in (0,1)"
        assert self.A > 0.0 and self.a_K > 0.0, "sector productivities must be > 0"
        assert 0.0 < self.lambda_I <= 1.0, "investment adjustment speed in (0,1]"
        assert 0.0 <= self.delta_K < 1.0, "depreciation rate in [0,1)"
        assert self.v > 0.0, "capital-output ratio must be > 0"
        assert self.search_m >= 1, "search sample size m must be >= 1"
        assert not self.capital_enabled or self.K_firm0 > 0.0, "C-firm needs K(0)>0"
        # v3 guards
        assert self.kappa > 1.0, "leverage multiple kappa must be > 1 (B7)"
        assert self.r_interest >= 0.0, "interest rate must be >= 0"
        assert 0.0 <= self.amort <= 1.0, "amortization fraction in [0,1]"
        assert not self.bank_enabled or self.capital_enabled, "v3 builds on v2 (needs the capital sector)"
        # v4 guards
        assert self.bank_capital_frac >= 0.0, "bank capital fraction must be >= 0"
        assert self.bankrupt_persist >= 1, "bankrupt_persist must be >= 1 tick"
        assert self.entry_beta >= 0.0 and self.entry_max >= 0, "entry knobs must be >= 0"
        assert self.startup_deposits > 0.0 and self.startup_capital > 0.0, "startup deposits/capital > 0"
        assert not self.firm_dynamics or self.bank_enabled, "v4 needs the bank (bad-debt writeoff)"
        assert self.dis_slope >= 0.0, "diseconomy slope must be >= 0"
        assert self.mpc_dispersion >= 0.0, "mpc_dispersion (sigma) must be >= 0"
        assert 0.0 < self.mpc_wealth_curvature <= 1.0, "MPC wealth curvature γ in (0,1]"
        # v6 guards
        assert not self.capital_market or self.capital_enabled, "v6 equity needs the capital sector"
        assert self.lambda_p > 0.0, "price groping speed must be > 0"
        assert self.w_chartist >= 0.0 and self.w_fundamental >= 0.0, "demand weights must be >= 0"
        assert 0.0 <= self.theta_equity <= 1.0, "target equity share in [0,1]"
        assert 0.0 < self.trend_lambda <= 1.0, "trend adaptation speed in (0,1]"
        assert 0.0 < self.equity_ema_lambda <= 1.0, "equity smoothing speed in (0,1]"
        assert self.float_shares > 0.0, "share float must be > 0"
        # v6.1 guards
        assert not self.per_firm_equity or self.capital_market, "v6.1 needs the capital market on"
        assert not self.per_firm_equity or self.firm_dynamics, "v6.1 founder ownership needs firm_dynamics"
        assert self.watchlist_size >= 1, "watchlist_size must be >= 1"
        assert self.shares_per_firm > 0.0, "shares_per_firm must be > 0"
        assert 0.0 < self.resid_income_lambda <= 1.0, "residual-income smoothing in (0,1]"
        assert self.lambda_q >= 0.0, "q-investment sensitivity must be >= 0"
        assert 0.0 <= self.q_invest_floor <= 1.0 <= self.q_invest_cap, "q multiplier bounds: floor<=1<=cap"
        assert not self.equity_finance or self.per_firm_equity, "v6.2 equity finance needs per-firm equity"
        assert self.lambda_issue >= 0.0, "issuance intensity must be >= 0"
        # v7 guards
        assert not self.household_credit or self.bank_enabled, "v7 household credit needs the bank"
        assert not self.household_interest_arrears or self.bank_enabled, \
            "household interest arrears require banks"
        assert self.hh_subsistence >= 0.0, "subsistence floor must be >= 0"
        assert self.hh_credit_limit >= 0.0, "household debt-to-income cap must be >= 0"
        assert 0.0 <= self.hh_amort <= 1.0, "household amortization fraction in [0,1]"
        # v8 guards
        assert not self.margin_credit or self.per_firm_equity, "v8 margin credit needs per-firm equity"
        assert not self.pro_rata_dividends or self.per_firm_equity, "v8.4 pro-rata dividends needs per-firm equity"
        assert not self.founder_owned_genesis or self.per_firm_equity, "v8.5 founder-owned genesis needs per-firm equity"
        assert 0.0 < self.genesis_founder_pool <= 1.0, "genesis_founder_pool is a fraction in (0,1]"
        # v9 government -- fiscal rates are proportions; wealth/consumption/income can't be confiscatory
        assert not self.government or self.bank_enabled, "v9 government needs the banking system (A5 money)"
        for _r in (self.tax_profit_rate, self.tax_income_rate, self.tax_consumption_rate, self.tax_wealth_rate):
            assert 0.0 <= _r < 1.0, "tax rates must be in [0,1)"
        assert self.wealth_allowance >= 0.0, "v10.2 wealth_allowance (exemption × mean NW) must be >= 0"
        # v11 multi-bank
        assert self.n_banks >= 1, "v11 n_banks must be >= 1"
        assert self.bank_leverage_mean >= 1.0 and self.bank_leverage_disp >= 0.0, "v11 leverage mean >= 1, disp >= 0"
        assert self.bank_assignment in ("random", "by_size"), "v11 bank_assignment ∈ {random, by_size}"
        assert self.bank_target_capital_ratio >= 0.0 and self.bank_exposure_limit >= 0.0, "v11 bank ratios >= 0"
        # v11.3 loan-rate competition
        assert self.bank_spread_disp >= 0.0, "v11.3 bank_spread_disp must be >= 0"
        assert self.bank_search_m >= 1, "v11.3 bank_search_m must be >= 1"
        assert not self.bank_rate_competition or self.bank_enabled, "v11.3 loan-rate competition needs the bank"
        # v11.4 reserve tier + interbank
        assert self.interbank_rate_base >= 0.0 and self.interbank_tightness >= 0.0, "v11.4 interbank rate params >= 0"
        assert self.reserve_floor_frac >= 0.0, "v11.4 reserve_floor_frac must be >= 0"
        assert self.deposit_rate_disp >= 0.0 and self.deposit_search_m >= 1, "v11.4 deposit-competition params"
        assert not self.interbank or self.bank_enabled, "v11.4 interbank/reserve tier needs the bank"
        # v11.5 bank demographics & ownership
        assert 0.0 < self.bank_equity_lambda <= 1.0, "v11.5 bank_equity_lambda in (0,1]"
        assert 0.0 <= self.bank_theta_equity <= 1.0, "v11.5 bank_theta_equity in [0,1]"
        assert self.bank_min_capital >= 0.0 and self.bank_entry_beta >= 0.0 and self.bank_entry_max >= 0, "v11.5 entry params >= 0"
        assert self.run_sensitivity >= 0.0 and self.run_health_ref >= 0.0, "v11.5 run params >= 0"
        assert 0.0 <= self.run_market_weight <= 1.0 and 0.0 <= self.run_fear_persistence <= 1.0, "v11.5 run weights in [0,1]"
        assert not self.bank_equity or self.bank_enabled, "v11.5 bank equity needs the bank"
        assert not self.bank_equity_trading or self.bank_equity, "v11.5 bank trading needs bank equity"
        assert not self.bank_dynamics or self.bank_equity, "v11.5 bank entry needs bank equity (founder owns it)"
        assert not self.bank_runs or self.interbank, "v11.5 bank runs need the reserve tier (queued withdrawals)"
        # v12 securities
        assert not self.bonds or self.bank_enabled, "v12 bonds need the banking/reserve system"
        assert not self.bonds or self.government, "v12 bonds need the government (Treasury)"
        assert 0.0 <= self.bond_finance_frac <= 1.0, "v12 bond_finance_frac in [0,1]"
        assert self.bond_coupon >= 0.0 and 0.0 <= self.bond_theta <= 1.0, "v12 bond coupon/theta ranges"
        assert self.bond_maturity >= 1, "v12.3 bond_maturity ≥ 1 (1 = one-period bill)"
        assert self.bond_maturity_bucket >= 1, "bond_maturity_bucket ≥ 1 (1 = exact daily maturity, bit-identical)"
        assert 0.0 < self.capital_clock_demand_smoothing <= 1.0, "capital_clock_demand_smoothing in (0,1] (1 = no damping)"
        assert 0.0 <= self.bank_bond_appetite <= 1.0, "v12.3 bank_bond_appetite in [0,1]"
        assert 0.0 <= self.omo_reserve_target and 0.0 < self.omo_drain_frac <= 1.0, "v12.4 OMO target≥0, drain∈(0,1]"
        assert self.bank_bond_duration_limit >= 0.0, "v12.4 bank_bond_duration_limit ≥ 0"
        assert not (self.omo or self.lolr) or self.bonds, "v12.4 OMO/LoLR need the securities layer (bonds)"
        assert not (self.bank_capital_constraint and self.n_banks > 1) or self.bank_enabled, "v11 needs the bank"
        assert not self.bank_relationship_lock_in or self.bank_enabled, \
            "bank relationship lock-in requires banks"
        assert 0.0 <= self.gov_consumption_share < 1.0, "gov_consumption_share is a fraction in [0,1)"
        assert 0.0 <= self.benefit_replacement <= 1.0, "benefit_replacement is a fraction in [0,1]"
        assert self.income_allowance >= 0.0 and self.min_wage >= 0.0, "allowance and min_wage must be >= 0"
        assert not self.household_bankruptcy or self.margin_credit, "household bankruptcy needs margin credit (the debt to discharge)"
        # v9.1 public capital
        assert self.gov_investment_share >= 0.0 and self.public_capital_gamma >= 0.0, "v9.1 shares/γ must be >= 0"
        assert 0.0 <= self.public_capital_depreciation < 1.0, "public capital depreciation in [0,1)"
        assert not (self.gov_investment_share > 0.0) or self.government, "v9.1 gov investment needs the government"
        assert not (self.gov_investment_share > 0.0) or self.capital_enabled, "v9.1 gov investment needs the K-sector"
        # v9.3 labor: job guarantee is a fiscal (outside-money) program -> needs the government
        assert self.jg_wage_ratio >= 0.0 and self.jg_productivity >= 0.0, "v9.3 JG wage ratio / productivity must be >= 0"
        assert not self.job_guarantee or self.government, "v9.3 job guarantee needs the government (outside money)"
        # v10 central bank: the policy rate needs the banking system (r_interest lives there)
        assert not self.central_bank or self.bank_enabled, "v10 central bank needs the banking system (r_interest)"
        assert self.taylor_phi_pi >= 0.0 and self.taylor_phi_u >= 0.0, "v10 Taylor responses must be >= 0"
        assert 0.0 <= self.rate_inertia < 1.0, "v10 rate inertia ρ in [0,1)"
        assert self.r_neutral >= 0.0 and self.r_max > 0.0, "v10 neutral rate >= 0 and r_max > 0"
        assert 0.0 < self.infl_ema_lambda <= 1.0, "v10 inflation-EMA λ in (0,1]"
        assert 0.0 <= self.u_natural <= 1.0, "v10 natural u in [0,1]"
        assert not self.monetary_direct_transmission or self.bank_enabled, \
            "direct monetary transmission requires loan contracts"
        assert self.investment_user_cost_elasticity >= 0.0, \
            "investment user-cost elasticity must be non-negative"
        assert 0.0 < self.investment_user_cost_multiplier_min <= 1.0 \
            <= self.investment_user_cost_multiplier_max, \
            "investment user-cost multiplier bounds must bracket 1"
        assert self.investment_user_cost_floor > 0.0, \
            "investment user-cost floor must be positive"
        assert self.firm_credit_min_dscr >= 1.0, \
            "firm credit minimum DSCR must be at least 1"
        assert self.valuation_discount_floor > 0.0, \
            "valuation discount floor must be positive per tick"
        assert self.valuation_risk_premium >= 0.0, \
            "valuation risk premium must be non-negative per tick"
        assert 0.0 <= self.margin_ltv < 1.0, "margin LTV in [0,1)"
        assert self.margin_max >= 1.0, "margin_max (leverage ceiling) must be >= 1"
        # v8.1 guards
        assert self.gibrat_sigma >= 0.0, "gibrat_sigma must be >= 0"
        assert self.pref_attach_beta >= 0.0, "preferential-attachment beta must be >= 0"
        assert self.pref_price_elasticity >= 0.0, "preferential price elasticity must be >= 0"
        assert self.gibrat_entry_a0 > 0.0, "entrant attractiveness a0 must be > 0"
        assert 0.0 < self.portfolio_adjust <= 1.0, "portfolio adjustment speed in (0,1]"
        assert 0.0 < self.q_invest_smooth <= 1.0, "q-investment smoothing speed in (0,1]"

    # Convenience for the M3(a) seed-invariance run (spec §8.3, point 4):
    # bigger N so aggregates are not dominated by small-sample sampling noise
    # (feedback point 4 -- avoid false "result depends on seed" alarms).
    def invariance_variant(self, seed: int) -> "Config":
        # Larger N so aggregates are not dominated by winner-take-all concentration
        # noise (which is severe at small N). Cheap now that the markets/dividends are
        # O(N) rather than O(N_F*N_H).
        from dataclasses import replace
        if self.capital_enabled:
            return replace(self, n_firms_c=150, n_firms_k=75, n_households=1500, seed=seed)
        return replace(self, n_firms=200, n_households=2000, seed=seed)

    def acceptance_variant(self, seed: int = 0) -> "Config":
        """Large-N config for the §10.8 drain-reversal acceptance / seed runs.
        Especially n_firms_k>=10 so B_K (the cure channel) is not dominated by
        small-sample noise (review point 3)."""
        from dataclasses import replace
        return replace(self, n_firms_c=40, n_firms_k=20, n_households=800, seed=seed)
