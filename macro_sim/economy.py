"""The six-phase single-tick loop of the closed monetary kernel (spec §6.3).

Scheduling is the M3 hybrid: planning is synchronous (every agent reads the same
frozen end-of-(t-1) state), then the labor and goods markets resolve sequentially
under a random participant ordering (live balances, so A4 holds as money moves),
then settlement and the accounting hard gate close the period.

All money movement goes through ``ledger.transfer`` (spec §7.6): wages firm->hh,
purchases hh->firm, dividends firm->hh. The good is a real outside item held as
firm inventory -- created by production, destroyed by consumption -- and is NOT
money, so it never touches the ledger.
"""

from __future__ import annotations

import random
from typing import Dict, List

from macro_sim.behavior.planning import diversify_mpc
from macro_sim.config import Config
from macro_sim.core.ledger import Ledger
from macro_sim.core.policy import Policy
from macro_sim.core.state import SimulationState
from macro_sim.demographics import Phase0VitalRates, create_genesis_population
from macro_sim.demographics.economic_bridge import initialize_person_claims_from_households
from macro_sim.demographics.kernel import MicroDemographicKernel
from macro_sim.demographics.lifecycle_households import LifecycleHouseholdConfig, apply_leaving_home_dynamics
from macro_sim.demographics.macro_signal import DemoMacroSignal
from macro_sim.demographics.stratification import WealthStratification
from macro_sim.housing import HousingRegistry
from macro_sim.housing.market import HousingMarket, run_housing_market_phase
from macro_sim.housing.mortgage import MortgageBook
from macro_sim.housing.construction import create_builders
from macro_sim.housing.rental import RentalMarket
from macro_sim.demographics.social import SocialDynamicsConfig
from macro_sim.domain.agents import Bank, EquityMarket, Firm, Household
from macro_sim.markets.matching import (
    EPS,
    Goods,
    MatchingProtocol,
    PreferentialMatch,
    SampledCompareMatch,
)
from macro_sim.reporting import metrics
from macro_sim.systems.banking import (
    assign_banks_genesis,
    draw_bank_kappas,
    draw_bank_spreads,
    draw_deposit_spreads,
    enable_reserves,
    resolve_bank_failures,
    run_bank_entry_phase,
    run_bank_runs_phase,
    run_deposit_competition,
    run_interbank_phase,
    setup_bank_equity,
)
from macro_sim.systems.capital_goods import run_capital_goods_phase
from macro_sim.systems.central_bank import run_omo_phase, set_policy_rate
from macro_sim.systems.credit import run_credit_phase, run_debt_service_phase
from macro_sim.systems.equity import run_equity_phase, setup_per_firm_equity
from macro_sim.systems.firm_demographics import apply_gibrat_shock, run_firm_demographics_phase
from macro_sim.systems.goods import run_goods_phase
from macro_sim.systems.labor import run_labor_phase
from macro_sim.systems.planning import run_planning_phase
from macro_sim.systems.securities import (
    assert_securities_identities,
    run_bill_issuance_phase,
    run_bill_maturity_phase,
)
from macro_sim.systems.settlement import run_settlement_phase


class Economy:
    def __init__(self, cfg: Config, *, protocol: MatchingProtocol = None, goods: Goods = None):
        self.cfg = cfg
        # v9: the government's LIVE levers (the only mutable-during-run state). Seeded from cfg, so
        # government=False keeps the macroprudential caps at their v8.5 defaults => bit-identical.
        self.policy = Policy.from_config(cfg)
        self.rng = random.Random(cfg.seed)          # single seeded generator (§7.6)
        # v8.1: size-biased (preferential) demand when Gibrat growth is on; else transparency dial.
        self.protocol = protocol or (PreferentialMatch(cfg.pref_attach_beta, cfg.pref_price_elasticity)
                                     if cfg.gibrat_growth else SampledCompareMatch(cfg.search_m))
        self._gibrat_rng = random.Random(cfg.seed + 777)   # dedicated -> main stream unperturbed
        self.goods = goods or Goods()

        self.demographic_rates = None
        self.demographic_state = None
        self.demographic_bridge = None
        self.demographic_kernel = None
        self._demographic_household_rng = random.Random(cfg.seed + 13_002)
        household_count = cfg.n_households
        if cfg.demographics_enabled:
            self.demographic_rates = Phase0VitalRates()
            population = cfg.demographics_population or cfg.n_households
            self.demographic_state = create_genesis_population(
                self.demographic_rates,
                n=population,
                seed=cfg.seed + 13_000,
            )
            household_count = len(
                {
                    int(person.household_id)
                    for person in self.demographic_state.people
                    if person.alive and person.household_id is not None
                }
            )

        self.households: List[Household] = [Household.create(i, cfg) for i in range(household_count)]
        if cfg.mpc_dispersion > 0.0:
            diversify_mpc(cfg, self.households)     # heterogeneous savers (T8 precursor); off => bit-identical

        # Firm sectors. v1 (capital disabled): one consumption sector, linear tech.
        # v2: consumption firms (Cobb-Douglas, invest) + capital firms (labor-only).
        balances: Dict[str, float] = {h.id: cfg.d_household0 for h in self.households}
        if cfg.capital_enabled:
            self.c_firms: List[Firm] = [Firm.create_c_firm(i, cfg) for i in range(cfg.n_firms_c)]
            self.k_firms: List[Firm] = [Firm.create_k_firm(i, cfg) for i in range(cfg.n_firms_k)]
            for f in self.c_firms:
                balances[f.id] = cfg.d_cfirm0
            for f in self.k_firms:
                balances[f.id] = cfg.d_kfirm0
        else:
            self.c_firms = [Firm.create(i, cfg) for i in range(cfg.n_firms)]
            self.k_firms = []
            for f in self.c_firms:
                balances[f.id] = cfg.d_firm0
        self.firms: List[Firm] = self.c_firms + self.k_firms   # all firms (single labor pool)
        self.investing_firms: List[Firm] = [f for f in self.firms if f.invests]  # C (+ K in v2.5)

        # v9.1: economy-wide PUBLIC capital (a non-rival stock; government investment builds it, it raises
        # every firm's productivity). K_ref = genesis private C-capital, so the factor (1+K_pub/K_ref)^γ
        # starts at 1. public_capital=0 or γ=0 ⇒ factor 1 ⇒ bit-identical.
        self.public_capital = 0.0
        self.K_ref = max(EPS, sum(f.capital for f in self.c_firms))
        self._pubcap_factor = 1.0
        self._price_level = cfg.p_firm0          # v9.2: current price level (updated each tick in metrics)

        # v3/v11: bank(s) (money creators). Each holds its own deposits (retained interest = capital) and
        # reserves = M (§A5 label). v11: n_banks accounts, splitting the genesis equity buffer; n_banks=1 ⇒ a
        # single "BANK" ⇒ bit-identical. bank capital = the account's deposit balance (absorbs write-offs).
        self.bank: Bank = None
        self.banks: List[Bank] = []
        if cfg.bank_enabled:
            non_bank_M = sum(balances.values())
            total_capital = cfg.d_bank0 + cfg.bank_capital_frac * non_bank_M   # genesis loss-absorbing buffer
            n = max(1, cfg.n_banks)
            ids = ["BANK"] if n == 1 else [f"BANK_{k}" for k in range(n)]
            kappas = draw_bank_kappas(cfg, n)                                  # per-bank risk appetite (κ_bank)
            for k, bid in enumerate(ids):
                self.banks.append(Bank(id=bid, rho=cfg.rho, kappa_bank=kappas[k]))
                balances[bid] = total_capital / n                             # split the buffer evenly
            self.bank = self.banks[0]                                         # compat / the n=1 bank

        # Dividend clearing account (perf): firms pay dividends into it, it distributes
        # equally to households -> O(N_F+N_H) instead of O(N_F*N_H). Holds 0 at tick end.
        balances["CLEARING"] = 0.0
        # v9/v12: the government (fiscal) deposit account. Starts at 0 (part of M0); goes NEGATIVE as it deficit-
        # spends (= government debt = outside money the private sector net-accumulates). transfers conserve => A5.
        # v12: un-consolidate -- this is the TREASURY (TSY); the central bank is the separate reserve node "CB".
        # `_fiscal` is the fiscal-account id: self._fiscal (consolidated, bonds off ⇒ bit-identical) or "TSY" (bonds on).
        self._fiscal = "TSY" if cfg.bonds else "GOV"
        if cfg.government:
            balances[self._fiscal] = 0.0

        self.ledger = Ledger(balances)
        for bk in self.banks:
            bk.reserves = self.ledger.genesis_money          # = M (label)
            self.ledger.allow_negative(bk.id)                # equity may go negative (insolvency)
        if cfg.government:
            self.ledger.allow_negative(self._fiscal)         # government debt (its negative balance)

        if cfg.demographics_enabled:
            self.demographic_bridge = initialize_person_claims_from_households(self, self.demographic_state)
            self.demographic_kernel = MicroDemographicKernel(
                self.demographic_rates,
                rng_seed=cfg.seed + 13_001,
                on_birth=self.demographic_bridge.on_birth,
                on_death=self.demographic_bridge.on_death,
                on_marriage=self.demographic_bridge.on_marriage,
                on_divorce=self.demographic_bridge.on_divorce,
                social_config=self._demographic_social_config(),
            )
            # v14 Phase 3.0 gauges + 3.1/3.2 rank-gradient strata (gradients 0.0 = pure observation)
            self.demographic_bridge.stratification = WealthStratification(
                mortality_gradient=cfg.mortality_rank_gradient,
                fertility_gradient=cfg.fertility_rank_gradient,
                mult_lo=cfg.strat_mult_lo,
                mult_hi=cfg.strat_mult_hi,
            )
            # v14 Phase 2: macro->demography signal (pure observation until an elasticity is set)
            self.demographic_bridge.macro_signal = DemoMacroSignal(
                halflife_years=cfg.demo_signal_halflife_years,
                burnin_years=cfg.demo_feedback_burnin_years,
                fertility_elasticity=cfg.fertility_income_elasticity,
                fertility_mult_lo=cfg.fertility_mult_lo,
                fertility_mult_hi=cfg.fertility_mult_hi,
                mortality_elasticity=cfg.mortality_income_elasticity,
                mortality_mult_lo=cfg.mortality_mult_lo,
                mortality_mult_hi=cfg.mortality_mult_hi,
            )
        # v15.0 housing: title registry + genesis endowment. One homogeneous dwelling per
        # genesis household, 100% owner-occupied, no mortgage; newly formed households start
        # houseless (they are the emergent buyers/renters of later stages). Price is FROZEN
        # at the genesis anchor -- no market until v15.1, stock integrity before flows.
        self.housing = None
        self.housing_market = None
        self.mortgage_book = None
        self.rental_market = None
        self._house_price = 0.0
        if cfg.housing_enabled:
            self.housing = HousingRegistry()
            self._house_price = cfg.house_price_income_years * 365.0 * cfg.w_firm0
            for h in self.households:
                self.housing.mint(h.id)
            if cfg.housing_market_enabled:
                # v15.1 resale market: probate/distress listings, monthly sessions
                self.housing_market = HousingMarket(
                    session_interval=cfg.housing_session_interval,
                    ask_markup=cfg.housing_ask_markup,
                    forced_discount=cfg.housing_forced_discount,
                    ask_decay=cfg.housing_ask_decay,
                    search_k=cfg.housing_search_k,
                    buyer_buffer=cfg.housing_buyer_buffer,
                    distress_floor=cfg.housing_distress_floor,
                )
            if cfg.mortgage_enabled:
                # v15.2: collateralization book over the existing household credit rails
                self.mortgage_book = MortgageBook(
                    ltv_cap=cfg.mortgage_ltv_cap,
                    foreclosure_ltv=cfg.mortgage_foreclosure_ltv,
                    arrears_floor=cfg.mortgage_arrears_floor,
                )
            self._genesis_dwellings = self.housing.count()
            if cfg.housing_rental_enabled:
                # v15.3: tenancy flows + emergent landlords; rent level seeded off the
                # genesis price anchor, independent thereafter
                self.rental_market = RentalMarket(
                    rent_yield0=cfg.rent_yield0,
                    rent_adjust=cfg.rent_adjust,
                    rent_burden_cap=cfg.rent_burden_cap,
                    eviction_arrears=cfg.rental_eviction_arrears,
                    investor_premium=cfg.rental_investor_premium,
                    rent_level=cfg.rent_yield0 * self._house_price / 365.0,
                )
            if cfg.housing_construction_enabled:
                # v15.4: builder firms on the native grammar; land fee + permits anchor
                create_builders(self, cfg)
        # v12 CB balance-sheet scaffolding (inert when bonds off): reserves = CB liability; assets = bonds it holds
        # + its claim on the TSY; TGA = the Treasury's account at the CB. Bonds are a separate overlay.
        self._cb_claim_on_tsy = 0.0
        self._tga = 0.0
        self._bonds_outstanding = 0.0
        self._bond_holdings: Dict = {}                       # holder_id -> Σ face held (fast index; banks+households+CB)
        # v12.3: bonds are LOTS (cohorts) carrying maturity + cost, so the three values diverge. Each lot is a dict
        # {holder, face, cost, matures_at}. `_bond_holdings` stays the Σ-face index (v12.1 metrics/consumption).
        # maturity 1 + coupon 0 ⇒ a one-period PAR bill ⇒ the v12.1-fix rollover path.
        self._bonds: List[dict] = []
        self._gov_interest_bill = 0.0                        # coupon paid this tick (a fiscal expense → deficit)
        # v12.4: CB quantity-tool state. `_cb_absorbed` = reserves the CB has DRAINED from banks into its own
        # reserve-absorbing instrument (reverse repo / CB bills -- the modern OMO drain, e.g. the Fed's ON RRP);
        # `_reserve_M0` = genesis reserve total (the OMO target is a fraction of it); `_lolr_advances` = outstanding
        # emergency reserves lent to run-hit banks.
        self._cb_absorbed = 0.0
        self._reserve_M0 = 0.0
        self._lolr_advances = 0.0
        self._omo_flow = 0.0                                 # this tick's net reserve drain(+)/inject(−) via OMO
        # v11: assign each borrower (firms + households) to a bank. n=1 ⇒ trivial (all → banks[0]); the
        # assignment runs ONLY when n>1 so it consumes no main-stream RNG at n=1 (bit-identical).
        self._bank_of: Dict = {}
        # account -> settlement-node memo for the RTGS resolver (perf). Entries are dropped at every
        # `_bank_of` write site, so a hit always equals what `settlement_node` would recompute.
        self._node_of: Dict = {}
        self._bank_failures_total = 0            # v11: cumulative bank insolvencies
        # v11.3: per-bank loan-rate spread (mean-preserving) + a dedicated shopping RNG (no main-stream
        # perturbation). Off (or n=1) ⇒ all spreads 0 ⇒ every loan rate = the policy rate ⇒ bit-identical.
        self._bank_spread: Dict = {}
        self._deposit_spread: Dict = {}                    # v11.4: per-bank deposit-rate spread (mean 0)
        self._bank_rng = random.Random(cfg.seed + 90007)
        # v11.4 interbank/reserve scratch (metrics read via getattr; safe defaults)
        self._interbank_rate = 0.0
        self._interbank_volume = 0.0
        self._interbank_contagion_loss = 0.0
        self._payments_blocked = 0.0
        self._bank_ids: set = {bk.id for bk in self.banks}
        self._hh_by_id = {h.id: h for h in self.households}   # v11.5: id → household (dividends; no hh exit)
        if len(self.banks) > 1:
            assign_banks_genesis(self)
            draw_bank_spreads(self)
            if cfg.interbank:
                enable_reserves(self)            # v11.4: the reserve overlay + RTGS settlement
                draw_deposit_spreads(self)        # v11.4: deposit-side competition spreads
        if cfg.bank_equity and self.banks:
            setup_bank_equity(self)              # v11.5: banks become owned (founder class), valued, dividend-paying
        self._bank_fear = 0.0                    # v11.5: system-wide run panic level
        self._bank_births = self._bank_deaths = 0
        self._next_bank_id = len(self.banks)     # v11.5: unique-id counter for de-novo banks
        self._bank_entry_rng = random.Random(cfg.seed + 33911)   # dedicated (no main-stream perturbation)
        self._run_rng = random.Random(cfg.seed + 77003)          # dedicated (bank-run flight draws)
        self._run_flight_volume = 0.0

        # v6 aggregate equity index OR v6.1 per-firm stock market (mutually exclusive).
        self.equity: EquityMarket = None
        if cfg.capital_market and not cfg.per_firm_equity:
            # aggregate index: float split EQUALLY; price = book/float so bubble gap starts 0.
            self.equity = EquityMarket.create(cfg)
            book0 = sum(self.ledger.balance(f.id) - self.ledger.debt(f.id) + f.capital
                        for f in self.c_firms)
            self.equity.book_value = book0
            self.equity.price = self.equity.last_price = max(EPS, book0 / cfg.float_shares)
            self.equity.fundamental = self.equity.price
            self.equity.dividend_ema = cfg.r_interest * book0    # Gordon anchor starts at book
            per_hh = cfg.float_shares / len(self.households)
            for h in self.households:
                h.shares = per_hh
                h.equity_value_ema = per_hh * self.equity.price
        elif cfg.capital_market and cfg.per_firm_equity:
            setup_per_firm_equity(self)                           # v6.1
        self._equity_turnover = 0.0                          # scratch (metrics)
        if self.demographic_bridge is not None:
            self.demographic_bridge.reconcile_financial_claims_from_economy(self)

        # v4 firm-demographics state: unique-id counter (never reuse indices) + scratch.
        self._next_c_id = cfg.n_firms_c
        self._births = self._deaths = 0
        self._writeoffs = 0.0

        self.records: List[dict] = []
        self.t = 0
        self._prev_price_index = None   # for per-tick inflation (metrics.py)
        self._prev_real_output = None   # for per-tick output growth (metrics.py)
        self._prev_avg_wage = None      # for per-tick wage inflation (metrics.py)
        self._dividends_paid = 0.0      # dividends transferred this tick (metrics.py)
        self._unsat_ratio = 0.0
        # v3 scratch (0 when bank disabled -> metrics ignore)
        self._credit_wage = self._credit_investment = 0.0
        self._interest_paid = self._principal_repaid = 0.0
        self._new_loans = 0.0
        # v10 central bank: the live policy rate + smoothed inflation signal. off ⇒ _rate ≡ r_interest.
        self._rate = cfg.r_interest
        self._infl_ema = cfg.inflation_target       # neutral start (deviation 0 ⇒ r starts at r_neutral)
        self._prev_inflation = cfg.inflation_target
        self.state = SimulationState(
            cfg=self.cfg,
            policy=self.policy,
            rng=self.rng,
            ledger=self.ledger,
            households=self.households,
            firms=self.firms,
            c_firms=self.c_firms,
            k_firms=self.k_firms,
            banks=self.banks,
            records=self.records,
        )

    # ======================================================================
    # One tick
    # ======================================================================
    def step(self) -> dict:
        set_policy_rate(self)             # v10: set this tick's policy rate (off ⇒ frozen r_interest)
        if self.cfg.interbank and len(self.banks) > 1:   # v11.4: begin this tick's intraday reserve tracking
            run_deposit_competition(self)                # depositors migrate toward higher deposit rates
            self.ledger.reset_intraday(list(self._bank_ids) + ["CLEARING", "CB"])
        run_omo_phase(self)               # v12.4 only; CB drains/injects reserves BEFORE payments (no-op off)
        # v9.1: the public-capital productivity factor for this tick (from last tick's K_pub). γ=0 ⇒ 1.0.
        self._pubcap_factor = ((1.0 + self.public_capital / self.K_ref) ** self.cfg.public_capital_gamma
                               if self.cfg.public_capital_gamma > 0.0 else 1.0)
        run_bill_maturity_phase(self)     # v12.1 only; one-period bills mature to deposits BEFORE planning (no-op off)
        if self.demographic_kernel is not None:
            # The kernel window mutates people (deaths/marriages/guardianship moves), so the bridge
            # falls back to live scans inside it; afterwards the state is frozen for the rest of the
            # tick and every economic phase reads the rebuilt O(1) person indexes.
            self._inheritance_flow = 0.0
            self._escheat_flow = 0.0
            self.demographic_bridge.invalidate_people_index()
            self.demographic_kernel.tick(self.demographic_state, economic_state=self.demographic_bridge)
            self._run_demographic_household_transitions()
            self.demographic_bridge.administer_estates(self.t)   # probate: escheat parked estates, settle empty households
            self.demographic_bridge.refresh_people_index()
        run_planning_phase(self)
        apply_gibrat_shock(self)          # v8.1 only; multiplicative market-share drift (no-op off)
        run_credit_phase(self)            # v3 only; no-op when banks disabled
        run_labor_phase(self)
        run_goods_phase(self)
        run_capital_goods_phase(self)     # v2 only; no-op when capital disabled
        run_settlement_phase(self)
        run_debt_service_phase(self)      # v3 only; no-op when banks disabled
        run_housing_market_phase(self)    # v15.1 only; monthly resale sessions (no-op off)
        run_firm_demographics_phase(self) # v4 only; C-firm bankruptcy + entry
        run_equity_phase(self)            # v6 only; equity market (no-op when disabled)
        run_interbank_phase(self)         # v11.4 only; money-market funding of reserve deficits (no-op off)
        run_bank_runs_phase(self)         # v11.5 only; depositor runs (flight + panic; queued withdrawals; no-op off)
        resolve_bank_failures(self)       # v11 only; insolvent banks fail + borrowers migrate (no-op off)
        run_bank_entry_phase(self)        # v11.5 only; de-novo bank entry when banking is profitable (no-op off)
        run_bill_issuance_phase(self)     # v12.1 only; Treasury re-issues bills from end-of-tick idle (no-op off)
        rec = self._phase5_check_and_record()
        if self.demographic_bridge is not None:
            # feed the macro->demography signal AFTER metrics: rec carries the multiplier the
            # kernel used this tick; an annual rollover here reaches the kernel next tick
            self.demographic_bridge.observe_macro(self, rec)
        self._commit_cross_tick_state()
        self.t += 1
        return rec

    def _demographic_social_config(self) -> SocialDynamicsConfig:
        cfg = self.cfg
        return SocialDynamicsConfig(
            marriage_enabled=cfg.demographic_marriage_enabled,
            divorce_enabled=cfg.demographic_divorce_enabled,
            marriage_market_interval_days=cfg.demographic_marriage_market_interval_days,
            annual_marriage_rate_peak=cfg.demographic_annual_marriage_rate_peak,
            annual_divorce_rate_base=cfg.demographic_annual_divorce_rate_base,
            marriage_assortativity=cfg.marriage_assortativity,
        )

    def _run_demographic_household_transitions(self) -> None:
        if not self.cfg.demographic_adult_leaving_home_enabled:
            return
        events = apply_leaving_home_dynamics(
            self.demographic_state,
            LifecycleHouseholdConfig(
                leave_home_min_age=self.cfg.demographic_leave_home_min_age,
                leave_home_peak_end_age=self.cfg.demographic_leave_home_peak_end_age,
                annual_leave_rate_peak=self.cfg.demographic_annual_leave_rate_peak,
                annual_leave_rate_late=self.cfg.demographic_annual_leave_rate_late,
            ),
            self._demographic_household_rng,
        )
        if not events:
            return
        if not hasattr(self.demographic_state, "leaving_home_events"):
            self.demographic_state.leaving_home_events = []
        self.demographic_state.leaving_home_events.extend(events)
        for event in events:
            self.demographic_bridge.create_household_for_person(event.person_id)

    def run(self, n_ticks: int = None) -> List[dict]:
        for _ in range(n_ticks if n_ticks is not None else self.cfg.n_ticks):
            self.step()
        return self.records

    # ======================================================================
    # Phase 5 -- Accounting check & recording (A1 hard gate)
    # ======================================================================
    def _phase5_check_and_record(self) -> dict:
        # Hard gates: money conserved (M0/A1) and no negative balances (A4).
        self.ledger.assert_conserved()
        self.ledger.assert_non_negative()
        self.ledger.assert_reserves_conserved()   # v11.4: the reserve overlay conserves too (no-op if off)
        assert_securities_identities(self)        # v12: bond / CB-balance-sheet / master-NFA gates (no-op if off)
        if self.housing is not None:
            self.housing.assert_invariants()      # v15.0: single owner per dwelling; count conserved
        if self.demographic_bridge is not None:
            self.demographic_bridge.assert_all_claim_identities(self)

        # Rich per-tick snapshot (metrics.py) -- pure observation.
        rec = metrics.compute_tick_metrics(self)
        self.records.append(rec)
        return rec

    # ======================================================================
    # Commit cross-tick derived state (§8.1: persist, don't recompute)
    # ======================================================================
    def _commit_cross_tick_state(self) -> None:
        for f in self.firms:
            f.target_inventory_prev = f.target_inventory
            f.labor_demand_eff_prev = f.labor_demand_eff
            f.hired_prev = f.hired
            f.sales_prev = f.sales
        # households: income_realized persists as-is (consumed next tick's Phase 1).
