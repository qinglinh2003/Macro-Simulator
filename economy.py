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

import behavior as B
import metrics
from agents import Bank, EquityMarket, Firm, Household
from config import Config
from policy import Policy
from interfaces import (EPS, BuyOrder, Goods, MatchingProtocol, PreferentialMatch,
                        SampledCompareMatch, SellOffer, execute_market)
from ledger import Ledger


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

        self.households: List[Household] = [Household.create(i, cfg) for i in range(cfg.n_households)]
        if cfg.mpc_dispersion > 0.0:
            self._diversify_mpc(cfg)     # heterogeneous savers (T8 precursor); off => bit-identical

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
            kappas = self._draw_bank_kappas(cfg, n)                            # per-bank risk appetite (κ_bank)
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
            self._assign_banks_genesis()
            self._draw_bank_spreads(cfg)
            if cfg.interbank:
                self._enable_reserves()          # v11.4: the reserve overlay + RTGS settlement
                self._draw_deposit_spreads(cfg)  # v11.4: deposit-side competition spreads
        if cfg.bank_equity and self.banks:
            self._setup_bank_equity()            # v11.5: banks become owned (founder class), valued, dividend-paying
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
            self._setup_per_firm_equity(cfg)                     # v6.1
        self._equity_turnover = 0.0                          # scratch (metrics)

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

    def _diversify_mpc(self, cfg: Config) -> None:
        """Draw per-household (alpha1, alpha2) from a mean-preserving lognormal so savers
        differ (T8 precursor, §16). Dedicated RNG -> does NOT perturb the main sim stream, so
        other series stay comparable and mpc_dispersion=0 is trivially bit-identical (skipped)."""
        rng = random.Random(cfg.seed + 90210)
        s = cfg.mpc_dispersion
        mu = -0.5 * s * s                       # lognormal mean = 1 (mean-preserving)
        for h in self.households:
            h.alpha1 = min(0.99, max(0.01, cfg.alpha1 * rng.lognormvariate(mu, s)))
            h.alpha2 = min(h.alpha1 - 1e-6, max(0.001, cfg.alpha2 * rng.lognormvariate(mu, s)))

    def _draw_bank_kappas(self, cfg: Config, n: int) -> list:
        """v11: per-bank leverage cap κ_bank (RISK APPETITE). Dedicated RNG (no main-stream perturbation);
        n=1 or dispersion=0 ⇒ uniform at the mean ⇒ heterogeneity off."""
        if n <= 1 or cfg.bank_leverage_disp <= 0.0:
            return [cfg.bank_leverage_mean] * max(1, n)
        rng = random.Random(cfg.seed + 71177)
        s = cfg.bank_leverage_disp
        mu = -0.5 * s * s                                  # mean-preserving lognormal (mean = 1)
        return [max(1.0, cfg.bank_leverage_mean * rng.lognormvariate(mu, s)) for _ in range(n)]

    def _draw_bank_spreads(self, cfg: Config) -> None:
        """v11.3: each bank's loan-rate spread over the policy rate -- mean 0 (some undercut, some charge more:
        efficiency / market-power heterogeneity, NOT a level change). Dedicated RNG (no main-stream perturbation).
        disp=0 ⇒ all zero ⇒ every loan rate = the policy rate."""
        if not cfg.bank_rate_competition or cfg.bank_spread_disp <= 0.0:
            self._bank_spread = {bk.id: 0.0 for bk in self.banks}
            return
        rng = random.Random(cfg.seed + 82301)
        raw = {bk.id: rng.gauss(0.0, cfg.bank_spread_disp) for bk in self.banks}
        mean = sum(raw.values()) / len(raw)                # de-mean ⇒ EXACTLY mean-preserving (no level tilt)
        self._bank_spread = {bid: s - mean for bid, s in raw.items()}

    def _draw_deposit_spreads(self, cfg: Config) -> None:
        """v11.4: each bank's DEPOSIT-rate spread (mean 0, dedicated RNG). A higher spread = a bank competing
        harder for deposits: it pays its depositors more (attracts them) at the cost of thinner retained capital.
        disp=0 ⇒ all zero ⇒ no deposit competition."""
        if not cfg.interbank or cfg.deposit_rate_disp <= 0.0:
            self._deposit_spread = {bk.id: 0.0 for bk in self.banks}
            return
        rng = random.Random(cfg.seed + 51009)
        raw = {bk.id: rng.gauss(0.0, cfg.deposit_rate_disp) for bk in self.banks}
        mean = sum(raw.values()) / len(raw)
        self._deposit_spread = {bid: s - mean for bid, s in raw.items()}

    def _deposit_competition(self) -> None:
        """v11.4: DEPOSIT-side competition. Pure-depositor households shop for a higher deposit rate -- each samples
        deposit_search_m rival banks and moves its whole deposit relationship to the one paying the most (if it
        beats the incumbent). Borrowers keep their loan-bank relationship (debt>0). The deposit backing (reserves)
        follows the move. So deposits CONCENTRATE at the banks that pay most -- the mirror of v11.3's loan side.
        Off ⇒ no-op."""
        if not (self.cfg.interbank and self.cfg.deposit_rate_disp > 0.0 and len(self.banks) > 1):
            return
        ds = self._deposit_spread
        alive = [b for b in self.banks if b.alive]
        if len(alive) < 2:
            return
        # CONGESTION (realism): a bank's appetite for deposits FALLS as it fills up -- a deposit-heavy bank
        # effectively pays less -- so competition EQUILIBRATES deposit shares instead of collapsing to a monopoly.
        # Effective rate = spread − congestion·(deposit share). Without it, fixed spreads ⇒ all deposits → 1 bank.
        D = {b.id: 0.0 for b in alive}
        for h in self.households:
            bid = self._bank_for(h.id).id
            if bid in D:
                D[bid] += max(0.0, self.ledger.balance(h.id))
        totD = sum(D.values()) or 1.0
        cong = self.cfg.deposit_rate_disp * len(alive)     # ~spans the spread across the share range
        eff = {bid: ds.get(bid, 0.0) - cong * (D[bid] / totD) for bid in D}
        for h in self.households:
            if self.ledger.debt(h.id) > EPS:               # borrowers stay with their loan bank
                continue
            cur = self._bank_for(h.id)
            best, best_ds = cur, eff.get(cur.id, 0.0)
            rivals = [b for b in alive if b is not cur]
            m = min(self.cfg.deposit_search_m, len(rivals))
            sample = rivals if m >= len(rivals) else self._bank_rng.sample(rivals, m)
            for b in sample:
                if eff.get(b.id, 0.0) > best_ds + EPS:
                    best, best_ds = b, eff.get(b.id, 0.0)
            if best is not cur:
                self.ledger.move_reserves(cur.id, best.id,
                                          self.ledger.balance(h.id) - self.ledger.debt(h.id))
                self._bank_of[h.id] = best

    def _setup_bank_equity(self) -> None:
        """v11.5 A1: equitize each bank -- shares vest in a FOUNDER (a minority owner class, like v8.5 firms).
        Price starts = book (capital) per share, so equity value = capital at genesis. Profit then flows to owners
        as dividends (not depositors); the valuation doubles as the run distress signal. Dedicated RNG."""
        rng = random.Random(self.cfg.seed + 43117)
        pool_n = max(1, int(self.cfg.genesis_founder_pool * len(self.households)))
        founders = rng.sample(self.households, min(pool_n, len(self.households)))
        SH = 100.0
        for i, bk in enumerate(self.banks):
            founder = founders[i % len(founders)]
            bk.shares_outstanding = SH
            bk.owners = {founder.id: SH}                       # founder owns 100% (concentrated, like real founders)
            cap = max(0.0, self.ledger.balance(bk.id))
            bk.share_price = bk.share_last_price = bk.share_peak = cap / SH
            bk.earnings_ema = 0.0

    def _pay_bank_dividends(self, bk, payable: float) -> None:
        """v11.5 A1: distribute a bank's payout to its OWNERS pro-rata to shares (was: to depositors). A5-safe
        transfer bank→owner. This turns bank interest income into a CONCENTRATED owner-income stream (§38)."""
        owners = bk.owners or {}
        tot = sum(owners.values())
        if tot <= 0.0:
            return
        for hid, sh in owners.items():
            h = self._hh_by_id.get(hid)
            if h is None:
                continue
            amt = min(payable * sh / tot, self.ledger.balance(bk.id))
            if amt > EPS:
                self.ledger.transfer(bk.id, h.id, amt)
                h.income_realized += amt

    def _bank_fundamental(self, bk, r) -> float:
        """v11.5: mark-to-model value per share = (book capital + capitalized smoothed earnings) / shares."""
        if not bk.alive or bk.shares_outstanding <= 0.0:
            return 0.0
        return (max(0.0, self.ledger.balance(bk.id)) + bk.earnings_ema / r) / bk.shares_outstanding

    def _update_bank_valuation(self) -> None:
        """v11.5 A1/A2: update smoothed bank earnings, then set the share price. A2 OFF ⇒ mark-to-model (price =
        fundamental). A2 ON ⇒ the secondary market gropes the traded price on excess demand (bubbles/crashes). A
        dead bank's price → 0 (owners wiped). Tracks a slow-decaying peak so the run signal (price/peak) shows a
        CRASH."""
        if not self.cfg.bank_equity:
            return
        r = max(self._rate, 0.01)
        lam = self.cfg.bank_equity_lambda
        for bk in self.banks:
            bk.earnings_ema = (1.0 - lam) * bk.earnings_ema + lam * max(0.0, bk.profit)
        if self.cfg.bank_equity_trading:
            self._bank_stock_market(r)                     # A2: traded price (gropes), sets price + trend + peak
        else:
            for bk in self.banks:                          # A1: mark-to-model
                bk.share_last_price = bk.share_price
                bk.share_price = self._bank_fundamental(bk, r)
                if bk.alive:
                    bk.share_peak = max(bk.share_peak * 0.999, bk.share_price)

    def _bank_stock_market(self, r) -> None:
        """v11.5 A2: a secondary bank-stock market -- the SAME mechanism as the per-firm market (§18): households
        target `bank_theta_equity` of wealth in bank stock (allocated by fundamentalist+chartist attractiveness,
        cash-capped); each bank's price GROPES on its own excess demand; trades are pro-rata rationed and settled
        via CLEARING so **shares AND money conserve** (and reserves settle buyer's bank→seller's bank). A chartist
        term (`w_chartist`) lets prices bubble/crash away from the fundamental -- the run trigger."""
        cfg, led = self.cfg, self.ledger
        banks = [b for b in self.banks if b.alive and b.shares_outstanding > EPS]
        for bk in self.banks:
            if not bk.alive:
                bk.share_last_price, bk.share_price = bk.share_price, 0.0
        if not banks:
            return
        fund = {bk.id: self._bank_fundamental(bk, r) for bk in banks}
        orders = {bk.id: [] for bk in banks}
        for h in self.households:
            eq_val = sum((bk.owners or {}).get(h.id, 0.0) * bk.share_price for bk in banks)
            deposits = led.balance(h.id)
            attr = []
            for bk in banks:
                p = bk.share_price
                pr = (cfg.w_fundamental * (fund[bk.id] - p) / p + cfg.w_chartist * bk.share_trend) if p > EPS else 0.0
                attr.append(max(0.0, 1.0 + pr))
            tot = sum(attr)
            target_eq = cfg.bank_theta_equity * (deposits + eq_val)
            deltas = []
            for bk, a in zip(banks, attr):
                w = (a / tot) if tot > EPS else (1.0 / len(banks))
                desired = (target_eq * w / bk.share_price) if bk.share_price > EPS else 0.0
                cur = (bk.owners or {}).get(h.id, 0.0)
                deltas.append((bk, (desired - cur) * cfg.portfolio_adjust))
            buy_cash = sum(d * bk.share_price for bk, d in deltas if d > 0.0)
            scale = min(1.0, deposits / buy_cash) if buy_cash > EPS else 1.0
            for bk, d in deltas:
                d = d * scale if d > 0.0 else max(d, -(bk.owners or {}).get(h.id, 0.0))
                if abs(d) > EPS:
                    orders[bk.id].append((h, d))
        turnover = 0.0
        for bk in banks:
            od = orders[bk.id]
            buy = sum(d for _, d in od if d > 0.0)
            sell = -sum(d for _, d in od if d < 0.0)
            executed = min(buy, sell)
            p = bk.share_price
            if executed > EPS:
                bs, ss = executed / buy, executed / sell
                for h, d in od:
                    if d > 0.0:
                        q = d * bs
                        led.transfer(h.id, "CLEARING", q * p)
                        bk.owners[h.id] = bk.owners.get(h.id, 0.0) + q
                sellers = [(h, -d * ss) for h, d in od if d < 0.0]
                for h, q in sellers:
                    bk.owners[h.id] = bk.owners.get(h.id, 0.0) - q
                    led.transfer("CLEARING", h.id, q * p)
                rem = led.balance("CLEARING")               # drain float residue to the last seller
                if rem > EPS and sellers:
                    led.transfer("CLEARING", sellers[-1][0].id, rem)
                turnover += executed
            excess = (buy - sell) / bk.shares_outstanding if bk.shares_outstanding > EPS else 0.0
            new_p = max(EPS, p * (1.0 + cfg.lambda_p * max(-0.5, min(0.5, excess))))
            bk.share_trend += cfg.trend_lambda * ((new_p - p) / p - bk.share_trend)
            bk.share_last_price, bk.share_price = p, new_p
            bk.share_peak = max(bk.share_peak * 0.999, bk.share_price)
        self._bank_equity_turnover = turnover / max(EPS, sum(bk.shares_outstanding for bk in banks))

    def _entry_banks(self) -> None:
        """v11.5 B: de-novo bank ENTRY (mirrors real chartering + v4 firm entry). When the banking sector's
        return on equity beats the hurdle (the policy rate) -- i.e. banking is profitable -- a household with
        enough wealth FOUNDS a new bank: it puts up `bank_min_capital` (the regulatory minimum, conserved) and
        OWNS it 100%. The entrant undercuts on the loan rate to break in and win borrowers via v11.3 shopping.
        So the bank count stops decaying to oligopoly -- births balance deaths. Off ⇒ no-op."""
        if not (self.cfg.bank_dynamics and self.cfg.bank_equity):
            return
        cfg = self.cfg
        alive = [b for b in self.banks if b.alive]
        tot_cap = sum(max(0.0, self.ledger.balance(b.id)) for b in alive)
        tot_inc = sum(b.interest_income for b in alive)          # this tick's gross interest income
        if tot_cap <= EPS:
            return
        roe = tot_inc / tot_cap                                  # per-tick return on bank equity
        r = max(self._rate, 1e-4)
        prob = max(0.0, min(1.0, cfg.bank_entry_beta * (roe / r - 1.0)))   # entry pressure ∝ excess ROE
        prob *= max(0.0, 1.0 - len(alive) / (2.0 * max(1, cfg.n_banks)))   # CONGESTION: entry stops as the count
        #   grows (real chartering is rare + high-barrier) ⇒ births ≈ deaths, a STABLE count, not hyper-churn.
        for _ in range(cfg.bank_entry_max):
            if self._bank_entry_rng.random() >= prob:
                continue
            founder = self._find_bank_founder(cfg.bank_min_capital)
            if founder is None:
                break
            self._found_bank(founder, cfg.bank_min_capital)

    def _find_bank_founder(self, need: float):
        """v11.5: a random household that can afford the minimum bank capital (sampled, not scanned). v12.4: eligible
        on LIQUID WEALTH = deposits + bonds@market (bonds are sellable, §12.3). 0 bonds ⇒ deposits only ⇒ bit-
        identical. NOTE (user-confirmed, §39.6): at NH2000 with the current wealth distribution almost NO household
        clears `bank_min_capital` in ANY wealth form (deposits/bonds/full NW all ~0 after t≈100), so de-novo entry
        is essentially dead regardless of what wealth we count -- the real lever is the DEATH side (thicker bank
        capital, below), and the deeper fix is a less single-household-cash entry mechanism (IPO / joint founding /
        bridge banks / recapitalisation), deferred."""
        for _ in range(8):
            h = self.households[self._bank_entry_rng.randrange(len(self.households))]
            if self.ledger.balance(h.id) + self._hh_bond_value(h.id) >= need + EPS:
                return h
        return None

    def _found_bank(self, founder, capital: float) -> None:
        """v11.5: charter a new bank -- founder capitalises it (A5-safe transfer; with v11.4 the reserve backing
        follows to the new bank's node) and owns 100%. Entrant undercuts on the loan rate to break in."""
        cfg = self.cfg
        bid = f"BANK_{self._next_bank_id}"
        self._next_bank_id += 1
        s = cfg.bank_leverage_disp
        kappa = max(1.0, cfg.bank_leverage_mean * (self._bank_entry_rng.lognormvariate(-0.5 * s * s, s) if s > 0 else 1.0))
        bk = Bank(id=bid, rho=cfg.rho, kappa_bank=kappa)
        self.banks.append(bk)
        self._bank_ids.add(bid)                                  # BEFORE the transfer so reserves settle to `bid`
        self.ledger.add_account(bid)
        self.ledger.allow_negative(bid)                          # bank equity may go negative (insolvency)
        if self.ledger.balance(founder.id) < capital:            # v12.4: liquidate the founder's bonds for the cash
            self._redeem_hh_bonds(founder.id, capital - self.ledger.balance(founder.id))
        self.ledger.transfer(founder.id, bid, capital)          # founder capitalises (conserved; reserves → bid)
        self._bank_spread[bid] = -abs(self._bank_entry_rng.gauss(0.0, cfg.bank_spread_disp))   # undercut to break in
        self._deposit_spread[bid] = 0.0
        SH = 100.0
        bk.shares_outstanding = SH
        bk.owners = {founder.id: SH}
        px = max(0.0, self.ledger.balance(bid)) / SH
        bk.share_price = bk.share_last_price = bk.share_peak = px
        self._bank_births += 1

    def _phase_bank_runs(self) -> None:
        """v11.5 C: bank RUNS. Depositors flee banks of low HEALTH -- a blend of the MARKET signal (share
        price/peak, a 2008-style stock crash) and the BOOK signal (capital / loan book) -- amplified by a
        system-wide FEAR level (panic contagion). A run is executed as a QUEUE: fleeing depositors are served
        sequentially from the bank's OWN reserves (loans are illiquid; the interbank market is FROZEN -- no one
        funds a bank being run); when reserves are exhausted the bank SUSPENDS and fails from illiquidity. Honest
        scope (§38): with credit thin, banks are nearly fully reserved, so suspension is LATENT -- the active
        halves are the FLIGHT (weak banks bleed deposits) + FEAR contagion. Off ⇒ no-op."""
        cfg = self.cfg
        self._run_flight_volume = 0.0
        if not (cfg.bank_runs and cfg.interbank and len(self.banks) > 1):
            return
        self._bank_fear *= cfg.run_fear_persistence         # panic decays each tick
        alive = [b for b in self.banks if b.alive]
        if len(alive) < 2:
            return
        self._refresh_loan_books()
        health = {}
        for bk in alive:
            lb = self._loan_book.get(bk.id, 0.0)
            book_h = min(1.0, (self.ledger.balance(bk.id) / lb) / max(EPS, cfg.run_health_ref)) if lb > EPS else 1.0
            mkt_h = min(1.0, bk.share_price / bk.share_peak) if bk.share_peak > EPS else 1.0
            health[bk.id] = cfg.run_market_weight * mkt_h + (1.0 - cfg.run_market_weight) * book_h
        safe = max(alive, key=lambda b: health[b.id])       # deposits flee TO the healthiest bank
        deps_by_bank = {}                                    # precompute pure-depositors per bank (O(H), not O(H·B))
        for h in self.households:
            if self.ledger.debt(h.id) <= EPS:
                deps_by_bank.setdefault(self._bank_for(h.id).id, []).append(h)
        for bk in alive:
            if bk is safe:
                continue
            pressure = max(0.0, 0.5 - health[bk.id])         # runs bite below health 0.5
            intensity = min(1.0, cfg.run_sensitivity * pressure + self._bank_fear)
            if intensity <= EPS:
                continue
            queue = [h for h in deps_by_bank.get(bk.id, [])   # its pure depositors who flee (prob = intensity)
                     if self._run_rng.random() < intensity]
            if not queue:
                continue
            self._run_rng.shuffle(queue)
            liquid = self.ledger.reserves(bk.id)              # OWN reserves only; interbank FROZEN during a run
            suspended = False
            for h in queue:
                w = self.ledger.balance(h.id)
                if w <= EPS:
                    continue
                if liquid < w - EPS and cfg.lolr and self._bank_economic_capital(bk) > EPS:
                    # v12.4 LoLR: the bank is ILLIQUID but SOLVENT ⇒ the CB lends it the shortfall (emergency
                    # reserves) so it honours the withdrawal instead of suspending. Liquidity ≠ solvency: an
                    # INSOLVENT bank (economic_capital ≤ 0, e.g. an SVB MTM wipe-out) is NOT rescued ⇒ it still
                    # fails, but ALONE, not by dragging the sector into a liquidity cascade.
                    need = w - liquid
                    self.ledger.issue_reserves(bk.id, need)
                    self._lolr_advances += need
                    liquid += need
                if liquid >= w - EPS:                         # bank can still honour the withdrawal
                    self.ledger.move_reserves(bk.id, safe.id, w)   # ship reserves to the safe bank
                    self._bank_of[h.id] = safe                     # deposit relationship flees
                    liquid -= w
                    self._run_flight_volume += w
                else:
                    suspended = True                          # reserves exhausted (no LoLR / insolvent) → SUSPEND
                    break
            if suspended:
                self._bank_fear = min(1.0, self._bank_fear + 0.25)   # panic spike
                self._fail_bank(bk)                                   # illiquidity failure
            else:
                self._bank_fear = min(1.0, self._bank_fear + 0.02 * len(queue) / len(self.households))

    def _bank_equity_value(self, hid) -> float:
        """v11.5: a household's bank-equity wealth = Σ its shares · each bank's price (0 for dead banks)."""
        if not self.cfg.bank_equity:
            return 0.0
        v = 0.0
        for bk in self.banks:
            sh = (bk.owners or {}).get(hid, 0.0)
            if sh > 0.0:
                v += sh * bk.share_price
        return v

    def _enable_reserves(self) -> None:
        """v11.4: seed the reserve overlay. Genesis reserves = each bank's own capital + its customers' deposits
        (all base money -- no loans exist yet, so reserves fully back deposits+equity). CLEARING + CB nodes start
        at 0. Σ = M₀. Every payment then settles reserves between the payer's and payee's nodes (RTGS, in the
        ledger). Reserve nodes may run negative (a funding deficit / CB base-money issuance)."""
        res = {bk.id: self.ledger.balance(bk.id) for bk in self.banks}
        for a in list(self.firms) + list(self.households):
            res[self._bank_for(a.id).id] += self.ledger.balance(a.id)
        res["CLEARING"] = 0.0
        res["CB"] = 0.0                                     # the central bank (base-money source/sink for GOV)
        self.ledger.enable_reserves(self._settlement_node, res)
        self._reserve_M0 = self.ledger.total_reserves       # v12.4: genesis base money (the OMO target's reference)

    def _assert_securities_identities(self) -> None:
        """v12: the securities-layer conservation gates. NO-OP when bonds off (⇒ v11.5 bit-identical). As the
        stages land they fill in: (1) BOND identity `Σ holdings@face = bonds_outstanding`; (2) the CB balance sheet
        `cb_bonds + cb_claim_on_tsy = Σ bank reserves + TGA + cb_equity`; (3) the MASTER NFA identity `private
        NFA@book = M₀ + cumulative deficit`. For v12.0 there is no issuance ⇒ every sum is 0 ⇒ trivially satisfied."""
        if not self.cfg.bonds:
            return
        held = sum(self._bond_holdings.values())              # (1) bond identity (face)
        assert abs(held - self._bonds_outstanding) <= 1e-6 * max(1.0, abs(self._bonds_outstanding)), \
            f"v12 bond identity broke: Σheld@face={held} vs outstanding={self._bonds_outstanding}"
        # (3) master NFA identity: private NFA (deposits − loans + bonds, @book) = M₀ + total government debt.
        # v12.3: a bank buying a bond via money creation raised ΣD (Treasury credited) AND `held` -- the created
        # money is NOT a net private asset, so subtract `_bank_securities` (it exactly offsets the bank bonds@book).
        gov_debt = self._bonds_outstanding - self.ledger.balance(self._fiscal)   # bonds + deposit-debt (TSY≤0)
        priv_nfa = (self.ledger.total_money - self.ledger.balance(self._fiscal)) \
            - self.ledger.total_credit + held - self.ledger.bank_securities   # (ΣD−D_TSY) − ΣL + bonds − created
        target = self.ledger.genesis_money + gov_debt
        assert abs(priv_nfa - target) <= 1e-6 * max(1.0, abs(target)), \
            f"v12 master NFA broke: private NFA {priv_nfa} vs M₀+gov_debt {target}"
        # (2) the CB balance-sheet gate (with CB bond/claim issuance) is wired in at v12.2 (money creation).

    def _bond_price(self, face: float, n: int, r: float, c: float) -> float:
        """v12.3: flat-yield present value of a bond -- `c·face·Σ_{k=1..n}(1+r)^-k + face·(1+r)^-n`. At `n=1, c=r`
        ⇒ price=face (a PAR bill); a rate HIKE (`r>c`) with `n>1` ⇒ price<face (the DURATION/SVB loss), deeper the
        longer `n`. Used only for wealth / `economic_capital` (MTM) -- NEVER a conservation flow."""
        if n <= 0 or r <= -1.0 + EPS:
            return face
        disc = 1.0 / (1.0 + r)
        pv_principal = face * disc ** n
        if c <= 0.0:
            pv_coupons = 0.0
        elif abs(r) < 1e-12:
            pv_coupons = c * face * n
        else:
            pv_coupons = c * face * (1.0 - disc ** n) / r
        return pv_coupons + pv_principal

    def _bond_market_value(self, lot: dict) -> float:
        """MTM of one lot at the current policy rate. v12.1 PAR bill (maturity 1, coupon 0) ⇒ face (no discount,
        the par convention that keeps v12.1-fix identical); v12.3 multi-period/coupon ⇒ the PV curve."""
        n = lot["matures_at"] - self.t
        if n <= 0:
            return lot["face"]
        if self.cfg.bond_maturity <= 1 and self.cfg.bond_coupon <= 0.0:
            return lot["face"]
        return self._bond_price(lot["face"], n, self._rate, self.cfg.bond_coupon)

    def _reindex_bonds(self) -> None:
        """Rebuild the `_bond_holdings` Σ-face index from the lot list (after issue/redeem/trade)."""
        idx: Dict = {}
        for lot in self._bonds:
            idx[lot["holder"]] = idx.get(lot["holder"], 0.0) + lot["face"]
        self._bond_holdings = idx

    def _hh_bond_value(self, hid) -> float:
        """v12: a holder's bonds valued at MARKET for wealth/consumption (v12.3: sellable ⇒ liquid ⇒ no re-freeze).
        0 when bonds off ⇒ bit-identical."""
        if not self.cfg.bonds:
            return 0.0
        return sum(self._bond_market_value(lot) for lot in self._bonds if lot["holder"] == hid)

    def _redeem_hh_bonds(self, hid, amount: float) -> None:
        """v12.4 (founder liquidity): redeem up to `amount` of a household's bonds early to deposits -- the Treasury
        buys them back at face (the same A5-safe leg as maturity). v12.3 made bonds LIQUID wealth, so a would-be
        bank founder whose capital sits in bonds must be able to turn it into the cash it puts up; without this the
        `bond_theta` deposit-drain silently starves bank ENTRY (the founder pool collapses ⇒ deaths outpace births
        ⇒ the sector bleeds out at long horizons -- the v12.3-introduced bank bleed). Whole lots, until covered."""
        kept, raised = [], 0.0
        for lot in self._bonds:
            if lot["holder"] == hid and raised < amount - EPS:
                self.ledger.transfer(self._fiscal, hid, lot["face"])
                self._bonds_outstanding -= lot["face"]
                raised += lot["face"]
            else:
                kept.append(lot)
        self._bonds = kept
        self._reindex_bonds()

    def _phase_bill_maturity(self) -> None:
        """v12.1-fix ROLLOVER + v12.3 COUPON/MATURITY, at the top of the tick (before planning). (1) pay the
        per-period COUPON `c·face` on every outstanding lot (TSY → holder; a fiscal expense that ADDS to the
        deficit ⇒ refinanced by next issuance); (2) redeem every lot that has reached MATURITY at FACE (TSY →
        holder). One-period bills (maturity 1) mature every tick ⇒ the holder carries pure deposits through the
        whole tick ⇒ bills stay liquid (feed consumption / goods-cap / equity / founding) with NO behavioural-code
        change -- the v12.1-fix. Multi-period bonds (maturity>1) persist across ticks and are valued at market
        (sellable in the secondary market, §B). Redemption injects reserves CB→holder-bank; issuance drains them
        back, cycling the RTGS machinery intraday. Off (bonds off / nothing issued) ⇒ no-op ⇒ bit-identical."""
        cfg = self.cfg
        self._gov_interest_bill = 0.0
        if not (cfg.bonds and cfg.government) or not self._bonds:
            return
        if cfg.bond_coupon > 0.0:                              # (1) per-period coupon (row c) -- a deficit expense
            for lot in self._bonds:
                c = cfg.bond_coupon * lot["face"]
                if c > EPS:
                    self.ledger.transfer(self._fiscal, lot["holder"], c)
                    self._gov_interest_bill += c
        matured = [lot for lot in self._bonds if lot["matures_at"] <= self.t]   # (2) maturity redemption at face
        if matured:
            for lot in matured:
                f = lot["face"]
                if f > EPS:
                    if lot["holder"] in self._bank_ids:      # bank bond: unwind the money creation (§C primitive)
                        self.ledger.bank_redeem_bond(lot["holder"], self._fiscal, f)
                    else:                                    # household bond: ordinary redemption (deposit↔bill)
                        self.ledger.transfer(self._fiscal, lot["holder"], f)
                    self._bonds_outstanding -= f
            self._bonds = [lot for lot in self._bonds if lot["matures_at"] > self.t]
            self._reindex_bonds()

    def _phase_bill_issuance(self) -> None:
        """v12.1-fix (bill ROLLOVER, second half): at the END of the tick the Treasury re-issues one-period bills
        to hit its target of holding `bond_finance_frac` of total government debt as bills (rest stays deposit-
        debt). Because `_phase_bill_maturity` already redeemed everything, `bonds_outstanding` is 0 here, so the
        gap is the full target. Bills are bought only from IDLE SAVINGS -- deposits above a transaction+precaution
        BUFFER (see below) -- so what gets sterilised is the genuine end-of-tick hoard, never this tick's spending
        power (that was fully available during the tick). Achievable bills are Σ idle-capped, so a high
        `bond_finance_frac` sterilises what idle money EXISTS. A bill purchase is a deposit↔bill SWAP whose RTGS
        leg **drains bank reserves to the CB ⇒ STERILISATION** (the interbank keystone). All A5-safe.
        Off (`bond_finance_frac`=0) ⇒ no-op ⇒ bit-identical."""
        cfg = self.cfg
        if not (cfg.bonds and cfg.bond_finance_frac > 0.0 and cfg.government):
            return
        gov_debt = self._bonds_outstanding - self.ledger.balance(self._fiscal)
        if gov_debt <= EPS:
            return
        gap = cfg.bond_finance_frac * gov_debt - self._bonds_outstanding       # >0 issue (bonds≈0 post-maturity)
        if gap <= EPS:
            return
        hh = self.households
        # BUFFER (v12.1-fix step 4): keep a THICKER transaction+precaution cushion liquid than v12.1's bare
        # max(y_expected, d_household0). Deposits below this are NOT idle -- they back near-term consumption
        # (2·expected income) and a real-terms subsistence floor (d_household0 deflated by the price level, the
        # same scaling as start-up cash). Only the excess is swept into bills.
        pfac = self._price_level / cfg.p_firm0
        if cfg.bond_theta > 0.0:
            # v12.3 DEMAND: households actively target `bond_theta` of wealth in bonds. Because bonds now pay a
            # coupon, count as wealth, and mature/roll (LIQUID), a THINNER cash buffer is warranted and holdings
            # are capped at the portfolio target -- this grows a MEANINGFUL stock (vs the v12.1-fix thin residual)
            # WITHOUT re-freezing (consumption is funded first; the buffer + maturity keep cash available).
            idle = {}
            for h in hh:
                d = self.ledger.balance(h.id)
                bm = self._hh_bond_value(h.id)
                thin_buffer = max(h.y_expected, cfg.d_household0 * pfac)
                room = max(0.0, cfg.bond_theta * (d + bm) - bm)          # unfilled portfolio target
                idle[h.id] = min(max(0.0, d - thin_buffer), room)
        else:
            idle = {h.id: max(0.0, self.ledger.balance(h.id) - max(2.0 * h.y_expected, cfg.d_household0 * pfac))
                    for h in hh}
        remaining = gap
        total = sum(idle.values())
        issued = False
        if total > EPS:
            for h in hh:                                   # HOUSEHOLDS buy pro-rata to idle/theta room, cash-capped
                buy = min(remaining * idle[h.id] / total, idle[h.id])
                if buy > EPS:
                    self.ledger.transfer(h.id, self._fiscal, buy)   # deposit → TSY (drains reserves h-bank→CB)
                    self._bonds.append({"holder": h.id, "face": buy, "cost": buy,
                                        "matures_at": self.t + cfg.bond_maturity})   # PAR issue: cost = face
                    self._bonds_outstanding += buy
                    remaining -= buy
                    issued = True
        # v12.3 §C: BANKS absorb the residual financing need out of their EXCESS RESERVES via money creation
        # (`bank_buy_bond_with_reserves`): reserves drain bank→CB (the STRONG sterilisation), the Treasury is
        # financed, and the bank holds the bond (its equity moves only by unrealised P&L ⇒ SVB channel, §D). This
        # is what parks the deficit's flood in BONDS instead of RESERVES, so Σ bank reserves stays near M₀ ⇒ scarce
        # ⇒ the interbank keystone can bind. Each bank invests `bank_bond_appetite` of its reserves per issuing tick
        # (a floor is preserved since appetite<1). Off (appetite 0 / no interbank) ⇒ skipped.
        if cfg.bank_bond_appetite > 0.0 and remaining > EPS and cfg.interbank:
            dep_by_bank: Dict = {}                          # customer deposits per bank (the reserve-requirement base)
            for a in list(self.firms) + list(self.households):
                bid = self._bank_for(a.id).id
                dep_by_bank[bid] = dep_by_bank.get(bid, 0.0) + self.ledger.balance(a.id)
            for bk in [b for b in self.banks if b.alive]:
                if remaining <= EPS:
                    break
                # EXCESS reserves = reserves ABOVE the required floor (reserve_floor_frac·deposits). Banks invest
                # `appetite` of the EXCESS -- never the buffer that backs settlement -- so a bank stays liquid
                # (over-investing is what killed the sector at appetite 0.5-of-total; the SVB risk stays TUNABLE).
                required = cfg.reserve_floor_frac * dep_by_bank.get(bk.id, 0.0)
                excess = max(0.0, self.ledger.reserves(bk.id) - required)
                want = min(cfg.bank_bond_appetite * excess, remaining)
                if cfg.bank_bond_duration_limit > 0.0:       # v12.4 SVB floor: cap the bond BOOK at k·economic capital
                    cur = sum(l["face"] for l in self._bonds if l["holder"] == bk.id)
                    room = cfg.bank_bond_duration_limit * max(0.0, self._bank_economic_capital(bk)) - cur
                    want = min(want, max(0.0, room))
                if want > EPS:
                    self.ledger.bank_buy_bond_with_reserves(bk.id, self._fiscal, want)   # reserves→CB (sterilise)
                    self._bonds.append({"holder": bk.id, "face": want, "cost": want,
                                        "matures_at": self.t + cfg.bond_maturity})
                    self._bonds_outstanding += want
                    remaining -= want
                    issued = True
        if issued:
            self._reindex_bonds()

    def _settlement_node(self, account_id):
        """v11.4: map a ledger account to its RTGS settlement node. Customers → their bank; a bank's own capital
        account → itself; the government (Treasury+CB consolidated) → the CB; CLEARING → its pass-through node."""
        if account_id == self._fiscal:
            return "CB"
        if account_id == "CLEARING" or account_id in self._bank_ids:
            return account_id
        return self._bank_for(account_id).id

    def _reserve_position(self, bank_id) -> float:
        """v11.4: the balance-sheet reserve identity R_k = capital_k + customer-deposits_k − loans_k. Equals the
        RTGS-settled `ledger.reserves(bank_id)` every tick (the settlement invariant) -- used to cross-check."""
        cap = self.ledger.balance(bank_id)
        dep = sum(self.ledger.balance(a.id) for a in list(self.firms) + list(self.households)
                  if self._bank_for(a.id).id == bank_id)
        loans = self._loan_book.get(bank_id, 0.0) if hasattr(self, "_loan_book") else \
            sum(self.ledger.debt(a.id) for a in list(self.firms) + list(self.households)
                if self._bank_for(a.id).id == bank_id)
        return cap + dep - loans

    def _rate_competition(self) -> bool:
        """v11.3: is loan-rate competition (heterogeneous spreads + borrower shopping) active? Off ⇒ one
        system rate, no shopping ⇒ bit-identical to v11.2."""
        return self.cfg.bank_rate_competition and len(self.banks) > 1

    def _loan_rate_for(self, borrower_id) -> float:
        """v11.3: the loan rate a borrower pays = policy rate + its bank's spread (floored at 0). Competition
        off ⇒ the plain policy rate ⇒ bit-identical."""
        if not self._rate_competition():
            return self._rate
        return max(0.0, self._rate + self._bank_spread.get(self._bank_for(borrower_id).id, 0.0))

    def _shop_bank(self, borrower_id, amount: float) -> None:
        """v11.3: the borrower samples bank_search_m rival banks and switches its whole relationship to the
        CHEAPEST one that can fund it (existing debt + the new loan within its leverage headroom). Cheap +
        well-capitalized banks thus WIN market share on price + capacity → concentration emerges. The switch
        moves the borrower's existing debt between loan books (consistent with failure-migration); the incumbent
        is always eligible (already funding the debt). Requires the loan books to be current."""
        cur = self._bank_for(borrower_id)
        debt = self.ledger.debt(borrower_id)
        need = debt + amount
        rate_of = lambda b: max(0.0, self._rate + self._bank_spread.get(b.id, 0.0))
        best, best_rate = cur, rate_of(cur)
        rivals = [b for b in self.banks if b.alive and b is not cur]
        m = min(self.cfg.bank_search_m, len(rivals))
        sample = rivals if m >= len(rivals) else self._bank_rng.sample(rivals, m)
        for b in sample:
            if self._bank_capacity(b) + EPS < need:        # can't fund the whole relationship within its cap
                continue
            if rate_of(b) < best_rate - EPS:
                best, best_rate = b, rate_of(b)
        if best is not cur:                                # move the relationship (debt teleports between books)
            self._loan_book[cur.id] = self._loan_book.get(cur.id, 0.0) - debt
            self._loan_book[best.id] = self._loan_book.get(best.id, 0.0) + debt
            if self.cfg.interbank:                          # v11.4: deposits move with the relationship, so the
                # reserve backing (deposits − loans) follows too -- keeps R_k = cap+dep−loans exact.
                self.ledger.move_reserves(cur.id, best.id,
                                          self.ledger.balance(borrower_id) - self.ledger.debt(borrower_id))
            self._bank_of[borrower_id] = best

    def _assign_banks_genesis(self) -> None:
        """v11: map each firm + household borrower to a bank at genesis. Dedicated RNG (no main-stream
        perturbation). 'by_size': bigger borrowers spread round-robin in size order (a spread that lets
        big borrowers concentrate at few banks → too-big-to-fail); 'random': uniform."""
        rng = random.Random(self.cfg.seed + 60613)
        banks, borrowers = self.banks, list(self.firms) + list(self.households)
        if self.cfg.bank_assignment == "by_size":
            borrowers.sort(key=lambda a: self.ledger.balance(a.id), reverse=True)
            for i, a in enumerate(borrowers):
                self._bank_of[a.id] = banks[i % len(banks)]
        else:
            for a in borrowers:
                self._bank_of[a.id] = banks[rng.randrange(len(banks))]

    def _bank_for(self, aid) -> Bank:
        """v11: the bank a borrower is assigned to. n=1 (empty map) ⇒ banks[0] for everyone ⇒ bit-identical.
        Fallback (unmapped, or a dead default) ⇒ the first alive bank."""
        if not self.banks:
            return None
        bk = self._bank_of.get(aid)
        if bk is not None:
            return bk
        for b in self.banks:                    # default: first alive bank (banks[0] at n=1)
            if b.alive:
                return b
        return self.banks[0]

    def _bank_constraint(self) -> bool:
        """v11: is the per-bank capital/leverage constraint active? Off (default) ⇒ loans grant in full ⇒
        bit-identical to the single-bank model."""
        return self.cfg.bank_capital_constraint and len(self.banks) > 1

    def _refresh_loan_books(self) -> None:
        """v11: recompute each bank's loan book (Σ debt of its borrowers) -- the asset side of the leverage cap."""
        self._loan_book = {bk.id: 0.0 for bk in self.banks}
        for b in self.firms:
            self._loan_book[self._bank_for(b.id).id] += self.ledger.debt(b.id)
        for h in self.households:
            self._loan_book[self._bank_for(h.id).id] += self.ledger.debt(h.id)

    def _bank_economic_capital(self, bank: Bank) -> float:
        """v12.3: a bank's equity capital INCLUDING unrealised bond P&L. A bank buys a bond via money creation
        (`bank_buy_bond_with_reserves`: reserves drain, a deposit is created to finance the Treasury) -- the bond
        is funded by a LIABILITY, so only the unrealised P&L `(market − cost)` touches equity, NOT the full value.
        At par ⇒ 0 (capital unchanged); a rate HIKE marks multi-period bonds below cost ⇒ P&L < 0 ⇒ equity THINS
        (the 2023-SVB channel). No bonds ⇒ = `ledger.balance` ⇒ bit-identical. This is the capital the leverage
        cap, the exposure limit, and the insolvency trigger all read."""
        cap = self.ledger.balance(bank.id)
        if self.cfg.bonds and self._bonds:
            for lot in self._bonds:
                if lot["holder"] == bank.id:
                    cap += self._bond_market_value(lot) - lot["cost"]    # unrealised P&L only (funded by deposit)
        return cap

    def _bank_capacity(self, bank: Bank) -> float:
        """v11: how much more `bank` can lend before hitting its leverage cap (loan_book ≤ κ_bank·capital). v12.3:
        capital is ECONOMIC capital (deposit-capital + bonds@market), so bond MTM losses tighten the cap."""
        if not bank.alive:
            return 0.0
        capital = max(0.0, self._bank_economic_capital(bank))
        return bank.kappa_bank * capital - self._loan_book.get(bank.id, 0.0)

    def _grant_loan(self, borrower_id, amount: float) -> float:
        """v11: create a loan respecting the borrower's bank's leverage cap. If the bank is levered up, the
        borrower gets LESS credit (a credit CRUNCH) -- the loss feeds the real-economy contagion loop.
        Migration to a healthier bank happens on bank FAILURE (resolution), not on every crunch. Constraint
        off ⇒ grant in full (bit-identical)."""
        if not self._bank_constraint():
            self.ledger.create_loan(borrower_id, amount)
            return amount
        if self._rate_competition():                            # v11.3: shop for the cheapest bank with capacity
            self._shop_bank(borrower_id, amount)
        bank = self._bank_for(borrower_id)
        headroom = self._bank_capacity(bank)                    # leverage-cap headroom
        if self.cfg.bank_exposure_limit > 0.0:                  # v11.2: single-borrower large-exposure limit
            capital = max(0.0, self._bank_economic_capital(bank))   # v12.3: economic capital (incl. bonds@market)
            conc = self.cfg.bank_exposure_limit * capital - self.ledger.debt(borrower_id)
            headroom = min(headroom, conc)                      # ≤ exposure_limit·capital per borrower ⇒ diversified
        g = min(amount, max(0.0, headroom))
        if g > EPS:
            self.ledger.create_loan(borrower_id, g)
            self._loan_book[bank.id] += g
        return g

    def _resolve_bank_failures(self) -> None:
        """v11: a bank whose CAPITAL (deposit balance) has gone negative is insolvent -- write-offs overran its
        buffer. Resolution (R2): mark it dead (stops lending), and MIGRATE its borrowers to alive banks (the
        performing ones keep credit; a system-wide failure ⇒ they're crunched). The dead bank's account stays
        in the ledger holding its negative balance (= the realized loss) so A5 is untouched -- no money is
        created or destroyed. Off (constraint disabled) ⇒ no-op."""
        if not self._bank_constraint():
            return
        while True:                                          # v11.4: loop so contagion can CASCADE within a tick
            # v12.3: insolvency on ECONOMIC capital (deposit-capital + bonds@market) -- a rate hike's bond MTM loss
            # can push a bank under even with a positive deposit balance (the SVB channel). No bonds ⇒ = balance.
            newly = [bk for bk in self.banks if bk.alive and self._bank_economic_capital(bk) < -EPS]
            if not newly:
                break
            for bk in newly:
                self._fail_bank(bk)                          # insolvency (capital < 0)

    def _fail_bank(self, bk) -> None:
        """v11 / v11.5: resolve a failed bank -- mark it dead (stops lending), MIGRATE its customers to alive banks
        (the reserve backing follows, v11.4), and socialise its residual loss (negative capital beyond wiped-out
        equity) onto its interbank creditors pro-rata (CONTAGION; can push a lender negative ⇒ cascades on the next
        _resolve pass). Shared by insolvency (_resolve_bank_failures) and run-SUSPENSION (_phase_bank_runs)."""
        bk.alive = False
        self._bank_failures_total += 1
        self._bank_deaths += 1
        alive = [b for b in self.banks if b.alive]
        if self.cfg.bank_migrate_on_failure and alive:
            movers = [aid for aid, b in self._bank_of.items() if b is bk]
            for i, aid in enumerate(movers):
                newbank = alive[i % len(alive)]
                if self.cfg.interbank and self.ledger.has_account(aid):
                    self.ledger.move_reserves(bk.id, newbank.id,
                                              self.ledger.balance(aid) - self.ledger.debt(aid))
                self._bank_of[aid] = newbank
        if self.cfg.interbank and alive:
            loss = -self.ledger.balance(bk.id)
            lenders = {b.id: self.ledger.reserves(b.id) for b in alive if self.ledger.reserves(b.id) > EPS}
            tot = sum(lenders.values())
            if loss > EPS and tot > EPS:
                for sid, sval in lenders.items():
                    amt = min(loss * sval / tot, max(0.0, -self.ledger.balance(bk.id)))
                    if amt > EPS:
                        self.ledger.transfer(sid, bk.id, amt)
                self._interbank_contagion_loss += loss

    def _phase_omo(self) -> None:
        """v12.4 OMO: the CB steers Σ bank reserves toward `omo_reserve_target`·(genesis reserves). It DRAINS by
        absorbing reserves into its own instrument (reverse repo / CB bills -- `retire_reserves`, `_cb_absorbed↑`)
        and INJECTS (QE) by releasing them (`issue_reserves`, `_cb_absorbed↓`, floored at 0). Draining reserves
        below the payment-flow buffer makes them SCARCE ⇒ banks run funding deficits ⇒ the latent §37 interbank
        market BINDS (peak overdraft / interbank_volume turn positive); QE re-floods ⇒ it re-latents (post-2008).
        Reserve conservation holds by construction (issue/retire move Σreserves and _reserve_M together); the
        deposit ledger is untouched. Off (or no banks) ⇒ no-op ⇒ bit-identical to v12.3."""
        cfg = self.cfg
        self._omo_flow = 0.0
        if not (cfg.omo and cfg.bonds and cfg.interbank):
            return
        banks = [b for b in self.banks if b.alive]
        if not banks:
            return
        target = cfg.omo_reserve_target * self._reserve_M0
        current = sum(self.ledger.reserves(b.id) for b in banks)
        move = cfg.omo_drain_frac * (current - target)         # >0 drain, <0 inject (smoothed toward target)
        if move > EPS:                                         # DRAIN: absorb reserves pro-rata to holdings
            pos = {b.id: self.ledger.reserves(b.id) for b in banks if self.ledger.reserves(b.id) > EPS}
            tot = sum(pos.values())
            if tot <= EPS:
                return
            for bid, r in pos.items():
                x = move * r / tot
                self.ledger.retire_reserves(bid, x)
                self._cb_absorbed += x
            self._omo_flow = move
        elif move < -EPS and self._cb_absorbed > EPS:         # INJECT / QE: release what was absorbed
            inject = min(-move, self._cb_absorbed)
            per = inject / len(banks)
            for b in banks:
                self.ledger.issue_reserves(b.id, per)
            self._cb_absorbed -= inject
            self._omo_flow = -inject

    def _phase_interbank(self) -> None:
        """v11.4: the interbank money market. After the tick's payments have settled, each bank has a reserve
        position R_k = ledger.reserves(id) (< 0 ⇒ a funding DEFICIT it covered by borrowing reserves; > 0 ⇒ a
        SURPLUS it lends). Deficit banks pay the interbank RATE on their deficit to surplus banks pro-rata. The
        rate is ENDOGENOUS to market tightness (aggregate deficit / aggregate surplus): ample reserves ⇒ ≈ the
        policy rate; a tight market ⇒ dearer. Interest is a plain deposit transfer between bank capital accounts
        (A5-safe; it also nudges reserves, correctly). A bank's funding cost thins its capital ⇒ can tip it into
        insolvency ⇒ interbank contagion (in _resolve_bank_failures). Off ⇒ no-op."""
        self._interbank_volume = 0.0
        self._interbank_rate = self._rate
        self._payments_blocked = 0.0
        self._interbank_contagion_loss = 0.0            # v11.5: reset here (runs + insolvency both accumulate)
        if not (self.cfg.interbank and len(self.banks) > 1):
            return
        alive = [b for b in self.banks if b.alive]
        # v11.4 gridlock instrumentation (Stage 3, latent): count banks whose INTRADAY reserve minimum breached
        # their intraday-credit limit (−reserve_floor_frac·capital) -- i.e. a payment that would have gridlocked
        # without lender-of-last-resort. In this ample-reserves economy this is ALWAYS 0 (peak overdraft ≈ 0);
        # it activates only when reserves turn scarce (a bond layer / much thicker credit). No invasive blocking.
        if self.cfg.reserve_floor_frac > 0.0:
            for b in alive:
                floor = -self.cfg.reserve_floor_frac * max(0.0, self.ledger.balance(b.id))
                if self.ledger.reserve_min(b.id) < floor - EPS:
                    self._payments_blocked += 1.0
        deficits = {b.id: -self.ledger.reserves(b.id) for b in alive if self.ledger.reserves(b.id) < -EPS}
        surplus = {b.id: self.ledger.reserves(b.id) for b in alive if self.ledger.reserves(b.id) > EPS}
        tot_def, tot_sur = sum(deficits.values()), sum(surplus.values())
        if tot_def <= EPS or tot_sur <= EPS:
            return
        tightness = min(1.0, tot_def / tot_sur)            # ∈ [0,1): deficit relative to the surplus pool
        ib_rate = max(0.0, self._rate + self.cfg.interbank_rate_base + self.cfg.interbank_tightness * tightness)
        self._interbank_rate = ib_rate
        self._interbank_volume = tot_def
        for did, dval in deficits.items():
            interest = min(ib_rate * dval, max(0.0, self.ledger.balance(did)))   # pay from capital (float-safe)
            if interest <= EPS:
                continue
            for sid, sval in surplus.items():              # to surplus lenders pro-rata to their reserves
                amt = min(interest * sval / tot_sur, self.ledger.balance(did))
                if amt > EPS:
                    self.ledger.transfer(did, sid, amt)

    def _setup_per_firm_equity(self, cfg: Config) -> None:
        """v6.1 genesis: equitize each C-firm (its own float, price=book/float so q=1), give each
        household a random watchlist of `watchlist_size` firms, and split every firm's float among
        its watchers (so Σ_h holdings[f] == shares_outstanding, the per-firm conservation gate)."""
        rng = random.Random(cfg.seed + 12345)      # dedicated -> doesn't perturb the main stream
        led, cfirms = self.ledger, self.c_firms
        for f in cfirms:
            f.shares_outstanding = cfg.shares_per_firm
            book = led.balance(f.id) - led.debt(f.id) + f.capital
            f.share_price = f.share_last_price = max(EPS, book / cfg.shares_per_firm)
            f.equity_fundamental = f.share_price
            f.residual_income_ema = 0.0            # premium starts 0 -> fundamental = book -> q=1
        ids = [f.id for f in cfirms]
        k = min(cfg.watchlist_size, len(ids))
        watchers = {fid: [] for fid in ids}
        for h in self.households:
            h.watchlist = rng.sample(ids, k)
            for fid in h.watchlist:
                watchers[fid].append(h)
        by_id = {f.id: f for f in cfirms}
        if cfg.founder_owned_genesis:
            # v8.5: the genesis float vests in a minority founder class -- each firm goes 100% to one
            # random founder (mirrors the run-time funder-owns-100% rule, §ii). Watchers keep their
            # lists so a buy-side market still exists; non-founders just start with zero holdings.
            n_founders = max(1, int(cfg.genesis_founder_pool * len(self.households)))
            founders = rng.sample(self.households, n_founders)
            for f in cfirms:
                fo = founders[rng.randrange(n_founders)]
                fo.holdings[f.id] = fo.holdings.get(f.id, 0.0) + f.shares_outstanding
                if f.id not in fo.watchlist:       # founder can sell down its own block
                    fo.watchlist.append(f.id)
        else:
            for fid, w in watchers.items():
                if not w:                          # guarantee >=1 watcher so the float is allocated
                    h = self.households[rng.randrange(len(self.households))]
                    h.watchlist.append(fid); w = [h]
                share = by_id[fid].shares_outstanding / len(w)
                for h in w:
                    h.holdings[fid] = h.holdings.get(fid, 0.0) + share

    def _gibrat_shock(self) -> None:
        """v8.1: multiply each C-firm's attractiveness (market share) by a mean-preserving lognormal
        shock -- a geometric random walk (Gibrat). With demand ∝ attractiveness^β (PreferentialMatch)
        and the v4 entry/exit barrier, firm sizes grow multiplicatively into a Pareto tail. Dedicated
        RNG so the main market stream is unperturbed (and gibrat_growth=False is bit-identical)."""
        cfg = self.cfg
        if not cfg.gibrat_growth or cfg.gibrat_sigma <= 0.0:
            return
        s = cfg.gibrat_sigma
        mu = -0.5 * s * s                       # lognormal mean = 1 (mean-preserving: no aggregate drift)
        rng = self._gibrat_rng
        for f in self.c_firms:
            f.attractiveness = max(EPS, f.attractiveness * rng.lognormvariate(mu, s))

    # ======================================================================
    # One tick
    # ======================================================================
    def step(self) -> dict:
        self._cb_set_rate()               # v10: set this tick's policy rate (off ⇒ frozen r_interest)
        if self.cfg.interbank and len(self.banks) > 1:   # v11.4: begin this tick's intraday reserve tracking
            self._deposit_competition()                  # depositors migrate toward higher deposit rates
            self.ledger.reset_intraday(list(self._bank_ids) + ["CLEARING", "CB"])
        self._phase_omo()                 # v12.4 only; CB drains/injects reserves BEFORE payments (no-op off)
        # v9.1: the public-capital productivity factor for this tick (from last tick's K_pub). γ=0 ⇒ 1.0.
        self._pubcap_factor = ((1.0 + self.public_capital / self.K_ref) ** self.cfg.public_capital_gamma
                               if self.cfg.public_capital_gamma > 0.0 else 1.0)
        self._phase_bill_maturity()       # v12.1 only; one-period bills mature to deposits BEFORE planning (no-op off)
        self._phase1_plan()
        self._gibrat_shock()              # v8.1 only; multiplicative market-share drift (no-op off)
        self._phase1_5_credit()           # v3 only; no-op when banks disabled
        self._phase2_labor()
        self._phase3_goods()
        self._phase3_5_capital()          # v2 only; no-op when capital disabled
        self._phase4_settlement()
        self._phase4_5_debt_service()     # v3 only; no-op when banks disabled
        self._phase4_7_demographics()     # v4 only; C-firm bankruptcy + entry
        self._phase4_9_equity()           # v6 only; equity market (no-op when disabled)
        self._phase_interbank()           # v11.4 only; money-market funding of reserve deficits (no-op off)
        self._phase_bank_runs()           # v11.5 only; depositor runs (flight + panic; queued withdrawals; no-op off)
        self._resolve_bank_failures()     # v11 only; insolvent banks fail + borrowers migrate (no-op off)
        self._entry_banks()               # v11.5 only; de-novo bank entry when banking is profitable (no-op off)
        self._phase_bill_issuance()        # v12.1 only; Treasury re-issues bills from end-of-tick idle (no-op off)
        rec = self._phase5_check_and_record()
        self._commit_cross_tick_state()
        self.t += 1
        return rec

    def run(self, n_ticks: int = None) -> List[dict]:
        for _ in range(n_ticks if n_ticks is not None else self.cfg.n_ticks):
            self.step()
        return self.records

    def _cb_set_rate(self) -> None:
        """v10 (§33): set this tick's policy rate via a Taylor rule from LAST tick's SMOOTHED inflation and
        unemployment (current-tick values aren't computed yet -- same pattern as the deficit rule's _prev_u):
            r = clip( ρ·r_{-1} + (1-ρ)·[ r* + φ_π·(π̄ - π*) - φ_u·(u - u*) ] , 0, r_max ).
        central_bank off ⇒ the frozen r_interest, so the model is bit-identical. The rate feeds the ALREADY-
        wired transmission (investment/entry hurdle, equity valuation, firm + household debt service)."""
        cfg = self.cfg
        if not cfg.central_bank:
            self._rate = cfg.r_interest
            return
        pol = self.policy
        # smooth the noisy per-tick inflation into the signal the rule reacts to
        self._infl_ema += cfg.infl_ema_lambda * (self._prev_inflation - self._infl_ema)
        u_prev = getattr(self, "_prev_u", cfg.u_natural)
        r_target = (cfg.r_neutral
                    + pol.taylor_phi_pi * (self._infl_ema - pol.inflation_target)
                    - pol.taylor_phi_u * (u_prev - cfg.u_natural))
        r_new = pol.rate_inertia * self._rate + (1.0 - pol.rate_inertia) * r_target
        self._rate = min(cfg.r_max, max(0.0, r_new))          # ZLB + sanity cap

    # ======================================================================
    # Phase 1 -- Expectations & planning (synchronous; read t-1 only)
    # ======================================================================
    def _phase1_plan(self) -> None:
        cfg = self.cfg

        # (a) update expectations from LAST tick's realized outcomes, BEFORE we
        #     reset this tick's accumulators.
        for h in self.households:
            B.update_income_expectation(h)      # consumes h.income_realized (last tick)
        for f in self.firms:
            B.update_demand_expectation(f)      # consumes f.sales_prev

        # (b) reset this-tick accumulators.
        for h in self.households:
            h.income_realized = 0.0
            h.spent = 0.0
            h.consumption_budget = 0.0
            h.labor_sold = 0.0                  # v9: reset per-tick employment (for the benefit)
            h.jg_labor = 0.0                    # v9.3: reset per-tick job-guarantee employment
        for f in self.firms:
            f.hired = f.produced = f.sales = 0.0
            f.revenue = f.wagebill = f.profit = 0.0
            f.investment = f.investment_target = f.dividend_shortfall = 0.0

        # (c) firm plans. Order (PLAN_v2 §1.5): production target -> NOTIONAL labor
        #     demand (needed by Cobb-Douglas unit cost) -> wage -> price (wage BEFORE
        #     price) -> cash-capped labor demand -> investment (C-firms, B5).
        for f in self.firms:
            B.plan_production(f)
            f.labor_demand_notional = B.labor_demand_notional(f, f.production_target, self._pubcap_factor)
            B.plan_wage(f, self.rng, cfg.theta_wage, self.policy.min_wage)
            B.plan_price(f, self.rng, cfg.theta_price)
            # Continuous cash cap (§8.1: floor(D/w) is a cap, not integer employment).
            cash_cap = self.ledger.balance(f.id) / f.wage
            f.labor_demand_eff = max(0.0, min(f.labor_demand_notional, cash_cap))
            if f.invests:
                B.plan_investment(f, cfg.lambda_q, cfg.q_invest_floor, cfg.q_invest_cap)  # B5 (+q, v6.1b)
                # v2.5 diagnostic (PLAN_v2 §1.1 disambiguation): force K-firms to at
                # least replace depreciation, removing the "never invests" failure so
                # any remaining collapse must be the structural absorbing state.
                if cfg.k_replacement_floor and f.sells == "capital":
                    f.investment_target = max(f.investment_target, f.delta_K * f.capital)

        # (d) household consumption budget from expected income + wealth (deposits, plus the weighted equity
        #     wealth effect when v6's wealth_effect>0, plus v12.3 BOND wealth at market). Bonds are near-money
        #     (coupon-paying, sellable, maturing every ≤bond_maturity ticks) so they enter the wealth term
        #     UNGATED by wealth_effect; 0 when bonds off ⇒ bit-identical. This is the v12.1-fix "no re-freeze"
        #     property made explicit: bond wealth supports consumption instead of being a frozen stone.
        we = cfg.wealth_effect
        for h in self.households:
            B.plan_consumption(h, deposits_prev=self.ledger.balance(h.id),
                               equity_wealth=we * h.equity_value_ema + self._hh_bond_value(h.id),
                               curvature=cfg.mpc_wealth_curvature, wealth_ref=cfg.d_household0)

    # ======================================================================
    # Phase 1.5 -- Credit (v3; B6 demand + B7 supply, loans create deposits M2). NEW.
    # ======================================================================
    def _phase1_5_credit(self) -> None:
        """Firms borrow to cover the cash gap of planned spending (wages + investment),
        BEFORE the markets so credit funds this tick's wage bill (relaxing the v1/v2
        cash-capped hiring). Loans create deposits (`create_loan`, A5-safe). Effective
        labor demand is then re-evaluated against the credit-augmented cash."""
        self._credit_wage = self._credit_investment = self._new_loans = 0.0
        if not self.cfg.bank_enabled:
            return
        if self._bank_constraint():
            self._refresh_loan_books()          # v11: bank loan books, for the leverage cap
        cfg = self.cfg
        # capital-price estimate for the investment cash need (mean current K price).
        p_k_est = (sum(f.price for f in self.k_firms) / len(self.k_firms)) if self.k_firms else 0.0
        for f in self.firms:
            deposits = self.ledger.balance(f.id)
            debt = self.ledger.debt(f.id)
            requested = B.credit_request(f, deposits, p_k_est)
            if requested > EPS:
                granted = B.credit_grant(requested, deposits, debt, self.policy.kappa)
                if granted > EPS:
                    granted = self._grant_loan(f.id, granted)  # v11: the bank's capital limit may crunch it
                if granted > EPS:
                    self._new_loans += granted
                    # attribute by purpose (pro-rata to the two needs) -- §B6 diagnostic
                    wage_need = f.wage * f.labor_demand_notional
                    inv_need = f.investment_target * max(0.0, p_k_est)
                    tot = wage_need + inv_need
                    if tot > EPS:
                        self._credit_wage += granted * wage_need / tot
                        self._credit_investment += granted * inv_need / tot
            # re-evaluate effective labor demand against (maybe) augmented cash (A4).
            f.labor_demand_eff = max(0.0, min(f.labor_demand_notional,
                                              self.ledger.balance(f.id) / f.wage))

        # v7: households borrow to defend a subsistence consumption floor (B8). Loans create
        # deposits (M2, A5-safe); the borrowed cash is spent in the goods market this tick, so
        # savers' deposits are recycled into spenders' demand (the thrift-paradox cure, §20).
        self._hh_credit_new = 0.0
        if cfg.household_credit:
            for h in self.households:
                deposits = self.ledger.balance(h.id)
                target, requested = B.household_credit_request(h, deposits, cfg.hh_subsistence)
                h.consumption_budget = target                 # defend the floor in the goods market
                if requested > EPS:
                    headroom = self.policy.hh_credit_limit * h.y_expected - self.ledger.debt(h.id)
                    granted = min(requested, max(0.0, headroom))   # B9: debt-to-income cap
                    if granted > EPS:
                        granted = self._grant_loan(h.id, granted)  # v11: the bank's capital limit may crunch it
                        self._hh_credit_new += granted

    # ======================================================================
    # Phase 2 -- Labor market (sequential; M1, short-side rationing)
    # ======================================================================
    def _phase2_labor(self) -> None:
        # Each household supplies 1.0 unit of labor inelastically. Firms are processed
        # in random order (M3(a)); workers are shuffled ONCE per tick and consumed via a
        # shared pointer (a firm processed later faces the depleted tail -> rationing).
        # This is O(N_H+N_F) instead of O(N_F*N_H): no per-firm reshuffle. The specific
        # worker->firm assignment is idiosyncratic noise, integrated out over seeds (M3(a));
        # a fresh shuffle each tick keeps any single household from being persistently
        # favored. A firm hires up to what its LIVE deposits can pay (A4).
        workers = list(self.households)
        self.rng.shuffle(workers)
        remaining = [1.0] * len(workers)     # parallel array: worker i's residual supply
        n = len(workers)
        p = 0                                # global pointer into the shuffled worker list

        firms_order = list(self.firms)
        self.rng.shuffle(firms_order)
        for f in firms_order:
            need = f.labor_demand_eff
            wage = f.wage
            while need > EPS and p < n:
                affordable = self.ledger.balance(f.id) / wage
                if affordable <= EPS:
                    break                    # firm out of cash -> stop hiring
                avail = remaining[p]
                if avail <= EPS:
                    p += 1
                    continue
                hire = min(need, avail, affordable)
                if hire <= EPS:
                    break
                pay = hire * wage
                self.ledger.transfer(f.id, workers[p].id, pay)   # wages firm -> household
                f.hired += hire
                f.wagebill += pay
                workers[p].income_realized += pay
                workers[p].labor_sold += hire                    # v9: track employment for the benefit
                remaining[p] -= hire
                need -= hire
                if remaining[p] <= EPS:
                    p += 1

            # Production: hired labor yields output added to inventory (§6.3).
            # Sector-aware (B.produce): linear a*N, or Cobb-Douglas A K^α N^{1-α}.
            f.produced = B.produce(f, f.hired, self._pubcap_factor)
            f.inventory += f.produced

    # ======================================================================
    # Phase 3 -- Goods market (sequential; M1, posted prices, rationing)
    # ======================================================================
    def _phase3_goods(self) -> None:
        # Buyers: households with a budget = min(desired budget, LIVE deposits) (A4).
        # The desired budget may exceed this tick's wage income (alpha2 wealth
        # channel) -- do NOT clamp to income; clamp only to live deposits.
        self._tax_consumption = self._gov_consumption = 0.0
        gov = self.cfg.government
        tc = self.policy.tax_consumption_rate if gov else 0.0
        orders: List[BuyOrder] = []
        for h in self.households:
            budget = min(h.consumption_budget, self.ledger.balance(h.id))
            if budget <= EPS:
                continue
            # v9 VAT: the outlay budget buys goods worth budget/(1+τ_c); the rest is reserved for tax.
            orders.append(BuyOrder(account=h.id, demand=float("inf"), budget=budget / (1.0 + tc), ref=h))
        hh_budget_total = sum(o.budget for o in orders)     # notional household spend (for unsat ratio)

        # v9 government procurement budget/units (spent below via a COMPETITIVE tender, not the household
        # preferential market). Two modes: deficit-targeting (spend last-tick revenue + target·GDP −
        # last-tick benefit, so the deficit ≈ target·GDP), or quantity (g·potential_output real units).
        gov_budget, gov_units = 0.0, float("inf")
        if gov:
            pol = self.policy
            if pol.gov_deficit_target > 0.0:
                target = pol.gov_deficit_target
                if pol.deficit_u_ref > 0.0:      # state-dependent: taper toward balance at full employment
                    target *= min(1.0, getattr(self, "_prev_u", pol.deficit_u_ref) / pol.deficit_u_ref)
                gov_budget = max(0.0, getattr(self, "_prev_tax_total", 0.0)
                                 + target * getattr(self, "_prev_nominal_output", 0.0)
                                 - getattr(self, "_prev_benefit", 0.0))
            elif pol.gov_consumption_share > 0.0:
                gov_units = pol.gov_consumption_share * len(self.households) * self.cfg.a
                gov_budget = float("inf")

        # Sellers are the consumption sector only (K-firms sell in Phase 3.5).
        offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f) for f in self.c_firms]
        trades = execute_market(orders, offers, protocol=self.protocol, rng=self.rng, ledger=self.ledger)

        # Push realized results back onto agents.
        spent_by: Dict[str, float] = {}
        for tr in trades:
            spent_by[tr.buyer] = spent_by.get(tr.buyer, 0.0) + tr.value
        for h in self.households:
            h.spent = spent_by.get(h.id, 0.0)
        self._gov_consumption = spent_by.get(self._fiscal, 0.0)      # government's realised real purchases
        for off in offers:
            f: Firm = off.ref
            f.inventory = off.stock              # decremented live during trading
            f.sales = off.sold                   # household purchases (government buys separately below)
            f.revenue = off.sold * off.price     # price fixed within the tick

        # v9 VAT: households remit τ_c on realised goods spending to GOV (reserved above, cash-capped).
        if tc > 0.0:
            for h in self.households:
                vat = min(h.spent * tc, self.ledger.balance(h.id))
                if vat > EPS:
                    self.ledger.transfer(h.id, self._fiscal, vat)
                    self._tax_consumption += vat

        # v9 COMPETITIVE PROCUREMENT: the government buys from the CHEAPEST c-firms first (a tender,
        # lowest-bid-wins), NOT via the household preferential market -- so its demand flows to
        # efficient/low-price firms, countering concentration (T6) and pressing prices down, instead of
        # funneling to the biggest. Deficit-financed (GOV goes negative). Realised sales feed firms'
        # adaptive demand expectations, so they produce for the recurring government demand.
        if gov and gov_budget > EPS and gov_units > EPS:
            led = self.ledger
            ranked = sorted((f for f in self.c_firms if f.inventory > EPS and f.price > EPS),
                            key=lambda f: f.price)
            b, u = gov_budget, gov_units
            for f in ranked:
                if b <= EPS or u <= EPS:
                    break
                q = min(f.inventory, b / f.price, u)
                if q <= EPS:
                    continue
                val = q * f.price
                led.transfer(self._fiscal, f.id, val)
                f.inventory -= q; f.sales += q; f.revenue += val
                self._gov_consumption += val
                b -= val; u -= q

        hh_spent = sum(h.spent for h in self.households)
        # Unsatisfied-demand ratio: fraction of intended budget that could not be
        # spent (stockouts). A first-class residual (§6.3, §6.5), not an error.
        self._unsat_ratio = (1.0 - hh_spent / hh_budget_total) if hh_budget_total > EPS else 0.0

    # ======================================================================
    # Phase 3.5 -- Capital-goods market (v2; sequential, M1, rationed). NEW.
    # ======================================================================
    def _phase3_5_capital(self) -> None:
        """C-firms buy capital goods from K-firms (money F_C -> F_K, firm-to-firm).

        Placed after Phase 3 so investment can draw on the deposit stock INCLUDING
        this tick's sales revenue (§10.5). Investment finances out of deposits (an
        asset swap deposits->capital); it is NOT a P&L expense, so profit below is
        still revenue - wagebill. Orders: demand = I* (units), budget = live cash (A4).
        """
        self._public_investment = self._gov_capital_units = 0.0
        if not self.cfg.capital_enabled:
            return
        orders: List[BuyOrder] = []
        for f in self.investing_firms:          # C-firms, plus K-firms in v2.5
            budget = self.ledger.balance(f.id)
            if f.investment_target <= EPS or budget <= EPS:
                continue
            orders.append(BuyOrder(account=f.id, demand=f.investment_target, budget=budget, ref=f))

        offers = [SellOffer(account=f.id, stock=f.inventory, price=f.price, ref=f) for f in self.k_firms]
        trades = execute_market(orders, offers, protocol=self.protocol, rng=self.rng, ledger=self.ledger)

        bought: Dict[str, float] = {}
        for tr in trades:
            bought[tr.buyer] = bought.get(tr.buyer, 0.0) + tr.qty
        for f in self.c_firms:
            f.investment = bought.get(f.id, 0.0)          # realized capital units (I_{f,t})
        for off in offers:                                # K-firms' sales come from THIS market
            kf: Firm = off.ref
            kf.inventory = off.stock
            kf.sales = off.sold
            kf.revenue = off.sold * off.price

        # v9.1 GOVERNMENT INVESTMENT: buy remaining K-goods (cheapest-first tender, §28.6 style), building
        # public capital. A budget of g_I·GDP -> real capital units accumulate into K_pub (Phase 4). This
        # is demand for the chronically-sink K-sector AND the supply-side outlet for the deficit. GOV pays.
        if self.cfg.government and self.cfg.gov_investment_share > 0.0:
            budget = self.cfg.gov_investment_share * getattr(self, "_prev_nominal_output", 0.0)
            led, b = self.ledger, budget
            for kf in sorted((k for k in self.k_firms if k.inventory > EPS and k.price > EPS),
                             key=lambda k: k.price):
                if b <= EPS:
                    break
                q = min(kf.inventory, b / kf.price)
                if q <= EPS:
                    continue
                val = q * kf.price
                led.transfer(self._fiscal, kf.id, val)
                kf.inventory -= q; kf.sales += q; kf.revenue += val
                self._gov_capital_units += q; self._public_investment += val
                b -= val

    # ======================================================================
    # Phase 4 -- Settlement & distribution
    # ======================================================================
    def _phase4_settlement(self) -> None:
        n_h = len(self.households)
        pol, gov = self.policy, self.cfg.government
        self._tax_profit = self._tax_income = self._tax_wealth = self._benefit_paid = 0.0
        self._jg_spending = self._jg_capital_units = self._jg_employment = 0.0   # v9.3 job guarantee
        # (i) firms pay dividends (cash-capped, A4) into the CLEARING account -- O(N_F).
        total_div = 0.0
        div_by_firm = {}                               # firm_id -> payable (v8.4 pro-rata payout)
        for f in self.firms:
            f.profit = f.revenue - f.wagebill          # investment is NOT a cost (asset swap)
            f.dividend_shortfall = 0.0
            # v9 profit tax (pre-dividend): government takes τ_π of positive profit (cash-capped).
            # Dividends then pay from AFTER-tax profit; retained earnings shrink by the tax.
            ptax = 0.0
            if gov and pol.tax_profit_rate > 0.0 and f.profit > EPS:
                ptax = min(pol.tax_profit_rate * f.profit, self.ledger.balance(f.id))
                if ptax > EPS:
                    self.ledger.transfer(f.id, self._fiscal, ptax)
                    self._tax_profit += ptax
            div_pool = f.rho * max(0.0, f.profit - ptax)   # only positive AFTER-TAX profit pays out
            if div_pool <= EPS:
                continue
            # A4 cash cap (PLAN_v2 §1.1): a firm that spent cash on investment (Phase 3.5)
            # may not cover the full dividend. Cap at live deposits; record the shortfall
            # (documents investment's first claim on cash, not hidden by phase order).
            payable = min(div_pool, self.ledger.balance(f.id))
            f.dividend_shortfall = div_pool - payable
            if payable <= EPS:
                continue
            self.ledger.transfer(f.id, "CLEARING", payable)
            total_div += payable
            div_by_firm[f.id] = payable
            # retained earnings (1-rho)*profit stay in f's deposits automatically.
        # (ii) distribute the CLEARING pool to households. The last recipient absorbs the float
        # remainder so CLEARING drains to exactly 0 (A5 clean).
        self._dividends_paid = total_div
        if total_div > EPS:
            if self.cfg.pro_rata_dividends and self.cfg.per_firm_equity:
                # v8.4: each firm's payout goes to ITS holders in proportion to holdings
                # (Σ_h holdings[f] == shares_outstanding, the per-firm conservation gate). A
                # non-owner earns zero dividend income -- capital income is now differential.
                # Firms with no household holders (the un-equitized K-sector) leave a residual
                # in CLEARING that is split equally -- the homogeneity fallback for unowned equity.
                so = {f.id: f.shares_outstanding for f in self.c_firms}
                for h in self.households:
                    amt = 0.0
                    for fid, sh in h.holdings.items():
                        pay, tot = div_by_firm.get(fid, 0.0), so.get(fid, 0.0)
                        if pay > EPS and sh > EPS and tot > EPS:
                            amt += pay * (sh / tot)
                    if amt > EPS:
                        self.ledger.transfer("CLEARING", h.id, amt)
                        h.income_realized += amt
                residual = self.ledger.balance("CLEARING")     # K-sector dividends + float error
                if residual > EPS:
                    share = residual / n_h
                    for h in self.households[:-1]:
                        self.ledger.transfer("CLEARING", h.id, share)
                        h.income_realized += share
                    last = self.households[-1]
                    rem = self.ledger.balance("CLEARING")
                    if rem > EPS:
                        self.ledger.transfer("CLEARING", last.id, rem)
                        last.income_realized += rem
            else:
                share = total_div / n_h                # equal split (choice 甲 + homogeneity)
                for h in self.households[:-1]:
                    self.ledger.transfer("CLEARING", h.id, share)
                    h.income_realized += share
                last = self.households[-1]
                remainder = self.ledger.balance("CLEARING")
                if remainder > EPS:
                    self.ledger.transfer("CLEARING", last.id, remainder)
                    last.income_realized += remainder

        # v9 household fiscal: progressive income tax, unemployment benefit, wealth tax (all via GOV).
        if gov:
            self._gov_household_fiscal()

        # Capital accumulation committed (A2 on the real stock, §10.4): every investing
        # firm (C, plus K in v2.5). K_{f,t} = (1-δ_K) K_{f,t-1} + I_{f,t}; productive t+1.
        for f in self.investing_firms:
            f.capital_prev = f.capital
            f.capital = (1.0 - f.delta_K) * f.capital + f.investment
        # v9.1/v9.3: public capital accumulates from government investment AND job-guarantee public works,
        # then depreciates (productive next tick). Off (no investment, no JG) => untouched => bit-identical.
        if self.cfg.gov_investment_share > 0.0 or self.policy.job_guarantee:
            self.public_capital = ((1.0 - self.cfg.public_capital_depreciation) * self.public_capital
                                   + getattr(self, "_gov_capital_units", 0.0)
                                   + getattr(self, "_jg_capital_units", 0.0))

    def _gov_household_fiscal(self) -> None:
        """v9 (§28): progressive income tax, unemployment benefit, and wealth tax on households, all
        through the GOV account (negative = government debt = outside money). income_realized is left
        at POST-tax + benefit so B1 sees DISPOSABLE income next tick. All flows are cash-capped and
        conserve (A5) since they are ledger transfers to/from GOV."""
        pol, led, hh = self.policy, self.ledger, self.households
        n_h = len(hh)
        # progressive income tax: τ_y on labour+dividend income ABOVE a personal allowance (= a_x·mean).
        if pol.tax_income_rate > 0.0:
            mean_inc = sum(h.income_realized for h in hh) / max(1, n_h)
            allowance = pol.income_allowance * mean_inc
            for h in hh:
                base = max(0.0, h.income_realized - allowance)
                tax = min(pol.tax_income_rate * base, led.balance(h.id))
                if tax > EPS:
                    led.transfer(h.id, self._fiscal, tax)
                    h.income_realized -= tax                 # disposable income feeds B1
                    self._tax_income += tax
        # v9.3 JOB GUARANTEE: hire every household's residual (unemployed) labour at the JG wage -- UNCAPPED
        # (a buffer stock). Paid as outside money (GOV -> household), like the benefit, and untaxed (runs after
        # the income tax). It REPLACES the dole for takers (the benefit's idle term below nets out jg_labor).
        # The public-works labour builds PUBLIC CAPITAL (jg_productivity units each), reusing the v9.1 K_pub
        # channel. Its deficit is an automatic stabilizer ON TOP of the discretionary target. Off => skipped.
        if pol.job_guarantee and pol.jg_wage_ratio > 0.0:
            wage_ref = sum(f.wage for f in self.firms) / max(1, len(self.firms))
            jg_wage = max(pol.jg_wage_ratio * wage_ref, pol.min_wage)   # respect the statutory floor if set
            for h in hh:
                resid = max(0.0, 1.0 - h.labor_sold)          # unemployed fraction after the private market
                pay = jg_wage * resid
                if pay > EPS:
                    led.transfer(self._fiscal, h.id, pay)            # outside money, like the benefit
                    h.income_realized += pay                  # disposable income -> B1 consumption next tick
                    h.jg_labor = resid                        # buffer-stock employment (suppresses the dole)
                    self._jg_spending += pay
                    self._jg_employment += resid
            self._jg_capital_units = self.cfg.jg_productivity * self._jg_employment  # public works -> K_pub
        # unemployment benefit: b·wage_ref per unit of TRULY-idle labour (1 - labor_sold - jg_labor). Untaxed.
        if pol.benefit_replacement > 0.0:
            wage_ref = sum(f.wage for f in self.firms) / max(1, len(self.firms))
            for h in hh:
                ben = pol.benefit_replacement * wage_ref * max(0.0, 1.0 - h.labor_sold - h.jg_labor)
                if ben > EPS:
                    led.transfer(self._fiscal, h.id, ben)
                    h.income_realized += ben
                    self._benefit_paid += ben
        # wealth tax: τ_w on positive net worth (deposits + equity − debt) ABOVE an exemption, cash-capped.
        # Progressive: allowance = wealth_allowance · mean(positive NW); only NW above it is taxed (only the
        # wealthy pay). wealth_allowance=0 ⇒ allowance 0 ⇒ taxes all positive NW ⇒ bit-identical (flat tax).
        if pol.tax_wealth_rate > 0.0:
            po = {f.id: getattr(f, "share_price", 0.0) for f in self.c_firms}
            nw_of = {}
            for h in hh:
                eq = sum(sh * po.get(fid, 0.0) for fid, sh in h.holdings.items())
                nw_of[h.id] = led.balance(h.id) + eq + self._bank_equity_value(h.id) - led.debt(h.id)  # v11.5: incl bank equity
            allowance = pol.wealth_allowance * (sum(max(0.0, v) for v in nw_of.values()) / max(1, n_h))
            for h in hh:
                base = max(0.0, nw_of[h.id] - allowance)
                wtax = min(pol.tax_wealth_rate * base, led.balance(h.id))
                if wtax > EPS:
                    led.transfer(h.id, self._fiscal, wtax)
                    self._tax_wealth += wtax

    # ======================================================================
    # Phase 4.5 -- Debt service (v3; amortization + interest, no default). NEW.
    # ======================================================================
    def _phase4_5_debt_service(self) -> None:
        """Firms amortize principal (`repay`, shrinks broad money) and pay interest
        (`transfer` to the bank; redistributes, net worth invariant). Shortfalls defer
        (no default in v3). The bank then distributes its interest profit to households
        (closing the interest loop, else the bank becomes a fresh money sink)."""
        self._interest_paid = self._principal_repaid = 0.0
        if not self.cfg.bank_enabled:
            return
        cfg = self.cfg
        for bk in self.banks:                               # v11: reset every bank's per-tick interest
            bk.interest_income = 0.0
        for f in self.firms:
            debt = self.ledger.debt(f.id)
            deposits = self.ledger.balance(f.id)
            principal, interest = B.debt_service_amounts(debt, deposits, self._loan_rate_for(f.id), cfg.amort)
            if principal > EPS:
                self.ledger.repay(f.id, principal)          # principal destroyed (A5-safe)
                self._principal_repaid += principal
            if interest > EPS:
                bk = self._bank_for(f.id)                   # v11: interest to the borrower's own bank
                self.ledger.transfer(f.id, bk.id, interest)   # interest = plain transfer
                self._interest_paid += interest
                bk.interest_income += interest

        # v7: households service their debt too (amortize + interest, cash-capped; shortfalls
        # defer -- no default in v7a). Interest joins the bank's income and is redistributed.
        self._hh_interest = self._hh_principal = 0.0
        if cfg.household_credit or cfg.margin_credit:      # v8: margin debt also accrues interest
            for h in self.households:
                debt = self.ledger.debt(h.id)
                if debt <= EPS:
                    continue
                deposits = self.ledger.balance(h.id)
                # v8: amortize only the CONSUMPTION portion (margin debt is interest-only, repaid by
                # sales/margin calls); interest accrues on TOTAL debt. margin_debt=0 pre-v8 => identical.
                cons_debt = max(0.0, debt - h.margin_debt)
                principal = min(cfg.hh_amort * cons_debt, deposits)
                interest = min(self._loan_rate_for(h.id) * debt, deposits - principal)
                if principal > EPS:
                    self.ledger.repay(h.id, principal)
                    self._hh_principal += principal
                if interest > EPS:
                    bk = self._bank_for(h.id)              # v11: interest to the borrower's own bank
                    self.ledger.transfer(h.id, bk.id, interest)
                    self._hh_interest += interest
                    bk.interest_income += interest

        # Each bank distributes profit (interest income) as dividends and RETAINS the rest as capital (its
        # deposit balance). Two modes: (a) ρ-retention (classic; n=1 ⇒ bit-identical) -- retains ρ forever;
        # (b) BASEL-like (bank_target_capital_ratio>0) -- pays out everything ABOVE target capital = ratio·
        # loan_book, so capital is BOUNDED and realistic (~a % of loans), not an ever-growing hoard. Either way
        # a well-capitalized bank is STABLE and fails only if a loss WAVE overruns its capital.
        ratio = self.cfg.bank_target_capital_ratio
        if ratio > 0.0 and len(self.banks) > 1:
            self._refresh_loan_books()
        comp = self.cfg.interbank and self.cfg.deposit_rate_disp > 0.0 and len(self.banks) > 1
        for bk in self.banks:
            bk.profit = bk.interest_income
            capital = self.ledger.balance(bk.id)
            if ratio > 0.0 and len(self.banks) > 1:
                target = ratio * self._loan_book.get(bk.id, 0.0)
                payable = max(0.0, capital - target)        # pay out excess above the target capital ratio
            else:
                payable = min(bk.rho * max(0.0, bk.profit), capital)   # ρ-retention (bit-identical at n=1)
            if payable <= EPS:
                continue
            if self.cfg.bank_equity:
                self._pay_bank_dividends(bk, payable)       # v11.5: profit → OWNERS (not depositors)
            elif comp:
                # v11.4: deposits are partitioned -- each bank pays its OWN depositors ∝ their deposits (a higher-
                # spread bank thus delivers its depositors a higher return, which is what drew them in).
                own = [(h, max(0.0, self.ledger.balance(h.id))) for h in self.households
                       if self._bank_for(h.id).id == bk.id]
                total_dep = sum(d for _, d in own)
                if total_dep > EPS:
                    for h, d in own:
                        amt = min(payable * d / total_dep, self.ledger.balance(bk.id))
                        if amt > EPS:
                            self.ledger.transfer(bk.id, h.id, amt)
                            h.income_realized += amt
            elif self.cfg.interest_by_deposits:
                # v10.1: deposit interest -- distribute ∝ each household's deposit balance. Float-safe: cap each
                # transfer at the bank's remaining balance; any tiny residue stays in the bank (§12 sink).
                dep = {h.id: max(0.0, self.ledger.balance(h.id)) for h in self.households}
                total_dep = sum(dep.values())
                if total_dep > EPS:
                    for h in self.households:
                        amt = min(payable * dep[h.id] / total_dep, self.ledger.balance(bk.id))
                        if amt > EPS:
                            self.ledger.transfer(bk.id, h.id, amt)
                            h.income_realized += amt
            else:
                share = payable / len(self.households)          # pre-v10.1: equal split (bit-identical)
                for h in self.households:
                    self.ledger.transfer(bk.id, h.id, share)
                    h.income_realized += share
        self._update_bank_valuation()          # v11.5: mark banks to model (also the run distress signal)

    # ======================================================================
    # Phase 4.7 -- Firm demographics (v4; C-firm bankruptcy + profit-driven entry). NEW.
    # ======================================================================
    def _phase4_7_demographics(self) -> None:
        """C-firms that stay financially insolvent (D−L<0) for `bankrupt_persist` ticks go
        bankrupt (bad debt absorbed by the bank, A5-safe); and when incumbent profitable
        C-firms earn a return above the interest rate r, new firms enter (household-funded).
        Entry responds to profit, exit to solvency -- firm count is emergent."""
        self._births = self._deaths = 0
        self._writeoffs = 0.0
        if not self.cfg.firm_dynamics:
            return
        cfg = self.cfg

        # -- deaths: sustained financial insolvency (subsumes zombie cleanup) --
        dead = []
        for f in self.c_firms:
            nw = self.ledger.balance(f.id) - self.ledger.debt(f.id)   # financial NW (matches B7)
            f.insolvent_ticks = f.insolvent_ticks + 1 if nw < -EPS else 0
            if f.insolvent_ticks >= cfg.bankrupt_persist:
                dead.append(f)
        for f in dead:
            self._bankrupt(f)

        # -- entry: profit above the hurdle r attracts entrants --
        self._entry_c_firms()

    def _bankrupt(self, f: Firm) -> None:
        """Liquidate a bankrupt C-firm: repay what cash allows, write off the rest (bank
        equity absorbs), scrap capital (real, not money), remove the firm. All A5-safe."""
        led = self.ledger
        pay = min(led.balance(f.id), led.debt(f.id))
        if pay > EPS:
            led.repay(f.id, pay)                       # repay from cash (destroys money+debt)
        bad = led.debt(f.id)
        if bad > EPS:
            led.write_off(f.id, self._bank_for(f.id).id, bad)     # v11: the borrower's OWN bank absorbs the loss
            self._writeoffs += bad
        residual = led.balance(f.id)                   # solvent surplus (rare; D>L case)
        if residual > EPS:
            led.transfer(f.id, self._bank_for(f.id).id, residual)
        # v6.1: equity is WIPED -- holders bear the loss (equity isn't money, so A5 is untouched);
        # remove the dead firm from every watchlist/holdings. Idiosyncratic risk of concentration.
        if self.cfg.per_firm_equity:
            for h in self.households:
                h.holdings.pop(f.id, None)
                if f.id in h.watchlist:
                    h.watchlist.remove(f.id)
        # capital is a real stock -> scrapped with the firm (no money effect, not in A5).
        self.c_firms.remove(f)
        self.firms.remove(f)
        if f in self.investing_firms:
            self.investing_firms.remove(f)
        led.remove_account(f.id)                       # 0/0 now
        self._deaths += 1

    def _entry_c_firms(self) -> None:
        cfg = self.cfg
        # signal: median return (profit/capital) over *profitable* incumbents (avoid zombie drag)
        rates = sorted(f.profit / f.capital for f in self.c_firms
                       if f.profit > EPS and f.capital > EPS)
        if not rates:
            return
        pr = rates[len(rates) // 2]                    # median incumbent return
        excess = pr - self._rate                       # over the hurdle rate r (cost of capital; v10 policy rate)
        if excess <= 0.0:
            return
        n_desired = cfg.entry_beta * excess * len(self.c_firms)
        n_enter = int(n_desired)
        if self.rng.random() < (n_desired - n_enter):  # stochastic rounding of the fraction
            n_enter += 1
        n_enter = min(cfg.entry_max, n_enter)
        sd = self._startup_cash()                      # v9.2: real-invariant if index_startup
        for _ in range(n_enter):
            funder = self._pick_funder(sd)
            if funder is None:
                break                                  # entry is wealth-constrained
            self._birth_c_firm(funder, sd)

    def _startup_cash(self) -> float:
        """v9.2: the entrant's startup deposits. Fixed nominal by default (an inflation non-neutrality
        ARTIFACT -- under inflation the fixed cash buys ever fewer workers, starving entrants). With
        index_startup, scale it by the price level so entry is REAL-invariant (COLA for new firms)."""
        if not self.cfg.index_startup:
            return self.cfg.startup_deposits
        return self.cfg.startup_deposits * (self._price_level / self.cfg.p_firm0)

    def _pick_funder(self, need: float):
        """A random household that can afford the startup (sampled, not scanned)."""
        for _ in range(12):
            h = self.households[self.rng.randrange(len(self.households))]
            if self.ledger.balance(h.id) >= need:
                return h
        return None

    def _birth_c_firm(self, funder: Household, sd: float = None) -> None:
        cfg = self.cfg
        if sd is None:
            sd = self._startup_cash()
        idx = self._next_c_id
        self._next_c_id += 1
        nf = Firm.create_c_firm(idx, cfg)              # unique id "C{idx}", cold-start seeded
        nf.capital = cfg.startup_capital               # minimal initial capital (real, from nothing)
        nf.capital_prev = cfg.startup_capital
        if cfg.gibrat_growth:
            nf.attractiveness = cfg.gibrat_entry_a0    # v8.1: entrants start SMALL (the reflecting barrier)
        self.ledger.add_account(nf.id)
        if len(self.banks) > 1:                         # v11: the entrant banks where its funder banks -- assign
            self._bank_of[nf.id] = self._bank_for(funder.id)   # BEFORE funding so the v11.4 RTGS transfer settles
        self.ledger.transfer(funder.id, nf.id, sd)     # household funds it (conserved; reserves settle to nf's bank)
        self.c_firms.append(nf)
        self.firms.append(nf)
        self.investing_firms.append(nf)
        # v6.1: the funder OWNS the firm it founded (100% of its float) -- equity ownership tracks
        # entrepreneurship, and the firm joins the funder's watchlist. Wealth→fund→own→appreciate→
        # wealth is the compounding inequality loop (§18).
        if cfg.per_firm_equity:
            nf.shares_outstanding = cfg.shares_per_firm
            book = sd + cfg.startup_capital                         # D + K, no debt at birth
            nf.share_price = nf.share_last_price = max(EPS, book / cfg.shares_per_firm)
            nf.equity_fundamental = nf.share_price
            funder.holdings[nf.id] = funder.holdings.get(nf.id, 0.0) + cfg.shares_per_firm
            if nf.id not in funder.watchlist:
                funder.watchlist.append(nf.id)
        self._births += 1

    # ======================================================================
    # Phase 4.9 -- Equity market (v6; aggregate index). NEW.
    # ======================================================================
    def _phase4_9_equity(self) -> None:
        """Households rebalance between deposits and the equity index. Price gropes on notional
        excess demand (no auctioneer); trades are pro-rata rationed so BOTH shares and money
        conserve exactly (money via CLEARING transfers, shares via matched buy/sell scaling)."""
        if self.cfg.per_firm_equity:
            self._phase4_9_equity_per_firm()          # v6.1: dispatch to the per-firm market
            return
        if self.equity is None:
            return
        cfg, mkt, led = self.cfg, self.equity, self.ledger

        # (1) fundamental = NET ASSET VALUE per share (book = Σ C-firm net worth / float). Robust
        #     and always positive when firms have net worth; fundamentalists mean-revert price to
        #     it, so q=1 at fundamental and bubble = market cap − book. (A Gordon dividend/r anchor
        #     was tried first but is fragile: cyclical dividend dips collapse it to ~0 and drag the
        #     price down with it; the r-discounted earnings valuation is deferred to v6.1, §16.)
        mkt.book_value = sum(led.balance(f.id) - led.debt(f.id) + f.capital for f in self.c_firms)
        mkt.dividend_ema += cfg.lambda_d * (self._dividends_paid - mkt.dividend_ema)  # metric only
        mkt.fundamental = mkt.book_value / mkt.float_shares

        p = mkt.price
        # (2) notional desired Δshares per household at the current price.
        desired = [B.plan_equity_demand(h, mkt, led.balance(h.id), cfg) for h in self.households]
        buy = sum(d for d in desired if d > 0.0)
        sell = -sum(d for d in desired if d < 0.0)
        executed = min(buy, sell)

        # (3) settle the executed volume: ration the LONG side pro-rata so Σ Δshares == 0.
        #     Buyers pay cash into CLEARING; sellers draw from it; last seller drains the fp
        #     remainder so CLEARING returns to exactly 0 (money conserved, like dividends).
        if executed > EPS:
            buy_scale, sell_scale = executed / buy, executed / sell
            sellers = []
            for h, d in zip(self.households, desired):
                if d > 0.0:
                    q = d * buy_scale
                    led.transfer(h.id, "CLEARING", q * p)      # buyer pays cash
                    h.shares += q
                elif d < 0.0:
                    sellers.append((h, -d * sell_scale))
            for h, q in sellers[:-1]:
                led.transfer("CLEARING", h.id, q * p)          # seller receives cash
                h.shares -= q
            if sellers:
                h, q = sellers[-1]
                rem = led.balance("CLEARING")
                if rem > EPS:
                    led.transfer("CLEARING", h.id, rem)       # drain remainder (guard float noise)
                h.shares -= q
        mkt.executed_volume = executed
        self._equity_turnover = executed / mkt.float_shares

        # (4) grope the price for next tick on the UNMET pressure; update the trend (chartist)
        #     signal from the realized return. No clearing is assumed (disequilibrium).
        mkt.excess_demand = (buy - sell) / mkt.float_shares
        new_p = max(EPS, p * (1.0 + cfg.lambda_p * max(-0.5, min(0.5, mkt.excess_demand))))
        ret = (new_p - p) / p
        mkt.trend += cfg.trend_lambda * (ret - mkt.trend)
        mkt.last_price, mkt.price = p, new_p

        # (5) update each household's smoothed equity wealth (feeds B1 next tick; throttle).
        for h in self.households:
            h.equity_value_ema += cfg.equity_ema_lambda * (h.shares * new_p - h.equity_value_ema)

    # ======================================================================
    # Phase 4.9 -- Per-firm stock market (v6.1). NEW.
    # ======================================================================
    def _phase4_9_equity_per_firm(self) -> None:
        """Each C-firm is separately valued (floored residual income), traded (its watchers submit
        orders), priced (gropes on its own excess demand), and gives a per-firm Tobin's q. Money
        (A5) and per-firm share floats both conserve exactly. Founder ownership + capital gains."""
        cfg, led = self.cfg, self.ledger
        r = self._rate                                   # v10: the live policy rate (feeds equity valuation)
        cfirms = self.c_firms

        # (1) valuation: fundamental = book + max(0, ema(π − r·book))/r  (floored residual income).
        book_of = {}
        for f in cfirms:
            book = led.balance(f.id) - led.debt(f.id) + f.capital
            book_of[f.id] = book
            f.residual_income_ema += cfg.resid_income_lambda * ((f.profit - r * book) - f.residual_income_ema)
            premium = (max(0.0, f.residual_income_ema) / r) if r > EPS else 0.0
            f.equity_fundamental = (book + premium) / f.shares_outstanding if f.shares_outstanding > EPS else 0.0
            f.tobin_q = (f.share_price * f.shares_outstanding / book) if book > EPS else 1.0
            # v8.3: the q that DRIVES investment is a smoothed q (firms ignore transient bubbles).
            # q_invest_smooth=1 -> ema = tobin_q exactly (bit-identical); <1 -> sluggish.
            f.tobin_q_ema = f.tobin_q if cfg.q_invest_smooth >= 1.0 \
                else f.tobin_q_ema + cfg.q_invest_smooth * (f.tobin_q - f.tobin_q_ema)

        # (2) per-household desired Δ across its watchlist, allocated by attractiveness, cash-capped.
        #     v8 margin: budget = cash + LTV headroom on equity; bullishness levers the target up to
        #     margin_max of NET WORTH, and buys beyond cash become a margin loan (asset-collateralised).
        by_id = {f.id: f for f in cfirms}
        orders = {f.id: [] for f in cfirms}          # firm_id -> [(household, Δshares)]
        self._hh_margin_new = 0.0
        for h in self.households:
            watch = [by_id[fid] for fid in h.watchlist if fid in by_id]
            if not watch:
                continue
            deposits = led.balance(h.id)
            eq_val = sum(h.holdings.get(f.id, 0.0) * f.share_price for f in watch)
            attr = []
            for f in watch:
                p = f.share_price
                pr = (cfg.w_fundamental * (f.equity_fundamental - p) / p + cfg.w_chartist * f.share_trend) \
                    if p > EPS else 0.0
                attr.append(max(0.0, 1.0 + pr))
            tot = sum(attr)
            if cfg.margin_credit:
                nw = deposits + eq_val - h.margin_debt              # true net worth
                avg_pr = sum(a - 1.0 for a in attr) / len(attr)     # mean demand pressure (bullishness)
                target_share = min(self.policy.margin_max, max(0.0, cfg.theta_equity * (1.0 + avg_pr)))
                target_eq = target_share * nw
                budget = deposits + max(0.0, self.policy.margin_ltv * eq_val - h.margin_debt)   # + LTV headroom
            else:
                target_eq = cfg.theta_equity * (deposits + eq_val)  # v6.1/v6.2 unchanged
                budget = deposits
            adj = cfg.portfolio_adjust                       # v8.2: partial rebalancing (B2 on portfolio)
            deltas = []
            for f, a in zip(watch, attr):
                w = (a / tot) if tot > EPS else (1.0 / len(watch))
                desired = (target_eq * w / f.share_price) if f.share_price > EPS else 0.0
                deltas.append((f, (desired - h.holdings.get(f.id, 0.0)) * adj))
            buy_cash = sum(d * f.share_price for f, d in deltas if d > 0.0)
            if cfg.margin_credit and buy_cash > EPS:                # fund buys beyond cash with margin
                margin_used = max(0.0, min(buy_cash, budget) - deposits)
                if margin_used > EPS:
                    led.create_loan(h.id, margin_used)
                    h.margin_debt += margin_used
                    self._hh_margin_new += margin_used
                    deposits = led.balance(h.id)
            scale = min(1.0, budget / buy_cash) if buy_cash > EPS else 1.0
            for f, d in deltas:
                d = d * scale if d > 0.0 else max(d, -h.holdings.get(f.id, 0.0))
                if abs(d) > EPS:
                    orders[f.id].append((h, d))

        # (3) per firm: aggregate, pro-rata ration the long side, settle (money via CLEARING,
        #     shares matched), grope price + trend. Both conservations exact, per firm.
        #     v6.2 equity finance: a q>1 firm adds NEW shares to the sell side (issuance); its
        #     proceeds go to firm deposits -> funds capex. New shares == new holdings (conserved).
        executed_total = 0.0
        self._equity_raised = 0.0
        for f in cfirms:
            od = orders[f.id]
            buy = sum(d for _, d in od if d > 0.0)
            hsell = -sum(d for _, d in od if d < 0.0)
            # v6.2 issuance: offer new shares worth up to λ_issue·(q−1)·book (bounded by book, and
            # by 20%/tick of the float) -- ties issuance to a real value, not the share COUNT, so no
            # dilution spiral. Converted to shares at the market price. Actual raise is demand-capped.
            issue = 0.0
            if cfg.equity_finance and f.tobin_q > 1.0:
                issue_cash = min(cfg.lambda_issue * (f.tobin_q - 1.0) * book_of[f.id],
                                 0.5 * book_of[f.id])
                issue = min(issue_cash / p, 0.2 * f.shares_outstanding)
            sell_total = hsell + issue
            executed = min(buy, sell_total)
            p = f.share_price
            if executed > EPS:
                bs, ss = executed / buy, executed / sell_total
                for h, d in od:                                # buyers pay cash, gain shares
                    if d > 0.0:
                        q = d * bs
                        led.transfer(h.id, "CLEARING", q * p)
                        h.holdings[f.id] = h.holdings.get(f.id, 0.0) + q
                hsellers = [(h, -d * ss) for h, d in od if d < 0.0]
                for h, q in hsellers:                          # household sellers: existing shares
                    h.holdings[f.id] = h.holdings.get(f.id, 0.0) - q
                    led.transfer("CLEARING", h.id, q * p)
                issued = issue * ss
                if issued > EPS:                               # firm issuance: NEW shares, proceeds to firm
                    f.shares_outstanding += issued
                    rem = led.balance("CLEARING")              # guard float noise (can be a hair negative)
                    if rem > EPS:
                        self._equity_raised += rem
                        led.transfer("CLEARING", f.id, rem)   # drain -> firm deposits
                elif hsellers:                                 # no issuance: drain fp remainder to a seller
                    rem = led.balance("CLEARING")
                    if rem > EPS:
                        led.transfer("CLEARING", hsellers[-1][0].id, rem)
                executed_total += executed
            excess = (buy - sell_total) / f.shares_outstanding if f.shares_outstanding > EPS else 0.0
            new_p = max(EPS, p * (1.0 + cfg.lambda_p * max(-0.5, min(0.5, excess))))
            f.share_trend += cfg.trend_lambda * ((new_p - p) / p - f.share_trend)
            f.share_last_price, f.share_price = p, new_p
        self._equity_turnover = executed_total / max(EPS, sum(f.shares_outstanding for f in cfirms))

        # (5) v8 margin calls: households whose margin debt now exceeds the LTV on their (repriced)
        #     equity delever by repaying from cash -- funded by the forced sells their fallen levered
        #     target triggered this tick. Fire sales feed back into next tick's prices (the crisis).
        self._hh_margin_repaid = 0.0
        if cfg.margin_credit:
            for h in self.households:
                if h.margin_debt <= EPS:
                    continue
                eq = sum(h.holdings.get(fid, 0.0) * by_id[fid].share_price
                         for fid in h.watchlist if fid in by_id)
                excess = h.margin_debt - self.policy.margin_ltv * eq
                if excess > EPS:
                    pay = min(excess, led.balance(h.id))
                    if pay > EPS:
                        led.repay(h.id, pay)
                        h.margin_debt -= pay
                        self._hh_margin_repaid += pay

        # (6) v9 household bankruptcy (§28): a household still INSOLVENT after the margin call (net worth
        #     <= 0 with margin debt it cannot cover) is discharged -- it repays what cash it has, the rest
        #     is WRITTEN OFF (bank equity absorbs, exactly like a firm default), and it keeps its shares.
        #     It emerges with no margin debt (net worth >= 0), curing the demand-death limbo (§27 exit
        #     valve). A5-safe: repay destroys deposit+loan together, write_off cuts loan+bank equity together.
        self._hh_bankruptcies = 0
        if cfg.household_bankruptcy and cfg.margin_credit:
            for h in self.households:
                if h.margin_debt <= EPS:
                    continue
                eq = sum(h.holdings.get(fid, 0.0) * by_id[fid].share_price
                         for fid in h.watchlist if fid in by_id)
                if led.balance(h.id) + eq - h.margin_debt <= 0.0:      # insolvent -> discharge
                    pay = min(led.balance(h.id), h.margin_debt)
                    if pay > EPS:
                        led.repay(h.id, pay); h.margin_debt -= pay
                    if h.margin_debt > EPS:
                        led.write_off(h.id, self._bank_for(h.id).id, h.margin_debt)   # v11: the borrower's OWN bank
                        h.margin_debt = 0.0
                    self._hh_bankruptcies += 1

    # ======================================================================
    # Phase 5 -- Accounting check & recording (A1 hard gate)
    # ======================================================================
    def _phase5_check_and_record(self) -> dict:
        # Hard gates: money conserved (M0/A1) and no negative balances (A4).
        self.ledger.assert_conserved()
        self.ledger.assert_non_negative()
        self.ledger.assert_reserves_conserved()   # v11.4: the reserve overlay conserves too (no-op if off)
        self._assert_securities_identities()      # v12: bond / CB-balance-sheet / master-NFA gates (no-op if off)

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
