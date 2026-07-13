"""The `World` container (PLAN_v20 §0.5 component ②, §5 BSP tick).

v20.0 delivers the substrate only: N economies + residency/currency tags + the BSP tick
SKELETON (an empty coupling barrier + the independent domestic step + an empty dealer
update) + per-economy RNG isolation. No coupling — that lands in v20.1 (FX) and v20.2
(trade). The load-bearing property is that this layer is INERT: N economies run exactly
as N independent closed economies, so `World([cfg])` ≡ `Economy(cfg)` byte-for-byte.
"""

from __future__ import annotations

from dataclasses import replace
from typing import List

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.world.capital import capital_interest
from macro_sim.world.fx import FXDealer, RateVector
from macro_sim.world.migration import run_migration
from macro_sim.world.trade import prepare_trade, settle_trade

# Per-economy seeds must be far-spaced: each `Economy` derives many substreams as
# `cfg.seed + <offset>` with offsets up to ~90007 and some only 1 apart (e.g. 13000,
# 13001, 13002). A stride this large guarantees economy i's substreams never collide
# with economy j's — the requirement that adding economy B cannot perturb economy A
# (PLAN_v20 §9; what makes the N=1≡dev gate and cumulative bit-identity hold).
ECONOMY_SEED_STRIDE = 1_000_000


class World:
    """A container of N coupled economies.

    Parameters
    ----------
    configs:
        One `Config` per economy. Their structure defines each economy's *character*
        (§0.6 `CountryProfile`); at v20.0 they are typically identical.
    base_seed:
        If given, each economy is re-seeded to ``base_seed + i * ECONOMY_SEED_STRIDE``
        so N structurally-identical configs become N INDEPENDENT draws (the identical-
        economy quiet baseline, §8). If ``None``, each config keeps its own seed — so
        ``World([cfg])`` reproduces ``Economy(cfg)`` exactly (the bit-identity gate).
    """

    def __init__(
        self,
        configs: List[Config],
        *,
        base_seed: int | None = None,
        couple: bool = False,
        trade: bool = False,
        capital: bool = False,
        fx_lambda: float = 0.05,
        fx_friction: float = 0.03,
        fx_trade_cap: float = 0.15,
        capital_mobility: float = 0.0,
        capital_adjust: float = 0.1,
        periods_per_year: float = 12.0,
        peg: bool = False,
        peg_reserves0: float = 5000.0,
        peg_reserve_scale: float = 1.0e5,
        migration: bool = False,
        migration_rate: float = 0.02,
        migration_max_share: float = 0.25,
        remittance_share: float = 0.2,
        immigration_cap: float | None = None,   # POLICY: host admits ≤ cap × pop (None = open)
        remittance_tax: float = 0.0,             # POLICY: origin taxes inbound remittances
    ):
        if not configs:
            raise ValueError("World needs at least one economy config")
        self.economies: List[Economy] = []
        for i, cfg in enumerate(configs):
            if base_seed is not None:
                cfg = replace(cfg, seed=base_seed + i * ECONOMY_SEED_STRIDE)
            econ = Economy(cfg)
            # Residency + currency tags (§0.5 component ①). At v20.0 only labels: an
            # agent's residency is which economy owns it; the currency labels the money.
            # These deepen (per-asset denomination) once capital/trade need them.
            econ.economy_id = i
            econ.currency = f"CUR{i}"
            self.economies.append(econ)
        self.n = len(self.economies)
        self.t = 0

        # v20.1 FX layer. couple=False ⇒ no FX objects, no dealer accounts ⇒ the World is
        # exactly v20.0 (bit-identical). couple=True installs the rate vector + the dealer
        # (one account per economy); with zero trade it is INERT (rates flat, inventory 0).
        self.couple = couple or trade or capital or migration   # any cross-border flow needs the FX layer
        self.trade = trade
        self.capital = capital                 # v21: persistent cross-border positions
        self.migration = migration             # v22: labor flow + remittances
        self.migration_rate = migration_rate
        self.migration_max_share = migration_max_share
        self.remittance_share = remittance_share
        # v22 migration POLICY (run-time government levers, distinct from the structural
        # knobs above): the immigration cap/quota + the remittance tax.
        self.immigration_cap = immigration_cap
        self.remittance_tax = remittance_tax
        self.capital_mobility = capital_mobility
        self.capital_adjust = capital_adjust
        self.periods_per_year = periods_per_year
        self.fx_lambda = fx_lambda
        self.fx_friction = fx_friction
        self.fx_trade_cap = fx_trade_cap
        self._factor_income: List[float] = [0.0] * self.n
        # v21.2 peg / trilemma: economy 0 pegs its rate; the CB absorbs the imbalance onto
        # reserves; reserves hitting zero breaks the peg (devaluation = currency crisis).
        self.peg = peg
        self.peg_reserve_scale = peg_reserve_scale
        self._reserves = peg_reserves0
        self._peg_intact = True
        self._pent_up = 0.0            # suppressed depreciation pressure (released on the crisis)
        self._migrant_stock: List[float] = [0.0] * self.n   # v22: emigrants from i, working abroad
        self._remittances: List[float] = [0.0] * self.n     # v22: remittances received by i (curr_i)
        self._remittance_tax_rev: List[float] = [0.0] * self.n   # v22: remittance-tax revenue (curr_i)
        self._immigration_binding: List[bool] = [False] * self.n  # v22: is the host's quota binding?
        self.rates: RateVector | None = None
        self.dealer: FXDealer | None = None
        self.world_records: List[dict] = []
        self._prev_import_value: List[float] = [0.0] * self.n   # curr_i, stale coupling
        self._last_export_value: List[float] = [0.0] * self.n   # curr_i, export financing
        self._import_source: List[int] = [-1] * self.n          # economy i's cheapest source j
        if self.couple:
            self.rates = RateVector(self.n)
            self.dealer = FXDealer(self.economies)

    # ======================================================================
    # One BSP tick: coupling barrier -> independent domestic step -> dealer
    # ======================================================================
    def step(self) -> List[dict]:
        self._coupling_barrier()                              # thin central barrier
        recs = [econ.step() for econ in self.economies]       # INDEPENDENT domestic step
        self._dealer_update(recs)                             # dealer inventory update
        self.t += 1
        return recs

    def _coupling_barrier(self) -> None:
        """The thin central barrier: compute cross-border export demand / import supply
        on last tick's prices + the current rate vector, and grope the rate.

        v20.1: the dealer's net inventory is the groping signal (§3); with zero trade it
        is all-zero ⇒ rates stay flat. Trade injection into the goods sessions lands in
        v20.2. Reductions across economies use fixed economy-id order (§9).
        """
        if not self.couple:
            return
        if self.trade:
            prepare_trade(self)               # set each economy's import offer + export order
        # (v20.1 with couple-only and no trade: nothing to set; groping happens in settle.)

    def _dealer_update(self, recs: List[dict]) -> None:
        """Settle realized trade, grope the rate on the dealer's net inventory, book the
        revaluation, and record the World FX gauges (§6/§7).

        v20.1 (couple, no trade): inventory 0, rates flat ⇒ every gauge trivially zero/unit.
        """
        if not self.couple:
            return
        if self.trade:
            settle_trade(self)                # read imports, update stale state, grope rate
        if self.capital:
            capital_interest(self)            # v21: factor income on cross-border positions
        if self.migration:
            run_migration(self)               # v22: labor flow + remittances
        self.dealer.book_revaluation(self.rates)
        inv = self.dealer.inventory()
        e = self.rates.e
        bop_numeraire = self.dealer.net_worth_numeraire(self.rates)
        # v21 external-position gauges (numéraire): NFA_i = −(dealer i-position)/e_i (a
        # positive dealer position is a foreign CLAIM on economy i ⇒ i's net foreign
        # LIABILITY); factor income_i (received) = −(i's interest outflow)/e_i.
        nfa = [-inv[i] / e[i] for i in range(self.n)]
        factor = [-self._factor_income[i] / e[i] for i in range(self.n)]
        # v22 full current account (numéraire) = trade balance + factor income + remittances.
        remit = [self._remittances[i] / e[i] for i in range(self.n)]
        tb = [(self._last_export_value[i] - self._prev_import_value[i]) / e[i] for i in range(self.n)]
        current_account = [tb[i] + factor[i] + remit[i] for i in range(self.n)]
        self.world_records.append(
            {
                "t": self.t,
                "e": list(e),
                "dealer_inventory": list(inv),
                "import_value": list(self._prev_import_value),
                "nfa": nfa,
                "factor_income": factor,
                "bop_numeraire": bop_numeraire,
                "dealer_valuation": self.dealer.valuation,
                "reserves": self._reserves,
                "peg_intact": self._peg_intact,
                "migrant_stock": list(self._migrant_stock),
                "remittances": remit,
                "current_account": current_account,
                "remittance_tax_rev": [self._remittance_tax_rev[i] / e[i] for i in range(self.n)],
                "immigration_binding": list(self._immigration_binding),
            }
        )

    def run(self, n_ticks: int | None = None) -> List[List[dict]]:
        n = n_ticks if n_ticks is not None else self.economies[0].cfg.n_ticks
        for _ in range(n):
            self.step()
        return [econ.records for econ in self.economies]

    # -- convenience -----------------------------------------------------------
    @property
    def records(self) -> List[List[dict]]:
        """Per-economy record series, indexed by economy id."""
        return [econ.records for econ in self.economies]
