"""The `World` container (PLAN_v20 §0.5 component ②, §5 BSP tick).

v20.0 delivers the substrate only: N economies + residency/currency tags + the BSP tick
SKELETON (an empty coupling barrier + the independent domestic step + an empty dealer
update) + per-economy RNG isolation. No coupling — that lands in v20.1 (FX) and v20.2
(trade). The load-bearing property is that this layer is INERT: N economies run exactly
as N independent closed economies, so `World([cfg])` ≡ `Economy(cfg)` byte-for-byte.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import List

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.world.capital import (
    CBRES_ID,
    EXTERNAL_ISSUER_ID,
    capital_interest,
    seed_reserves,
    settlement_fractions,
)
from macro_sim.world.fx import FXDealer, RateVector
from macro_sim.world.migration import run_migration
from macro_sim.world.trade import grope_rates, prepare_trade, rate_grope_signal, settle_trade

# Per-economy seeds must be far-spaced: each `Economy` derives many substreams as
# `cfg.seed + <offset>` with offsets up to ~90007 and some only 1 apart (e.g. 13000,
# 13001, 13002). A stride this large guarantees economy i's substreams never collide
# with economy j's — the requirement that adding economy B cannot perturb economy A
# (PLAN_v20 §9; what makes the N=1≡dev gate and cumulative bit-identity hold).
ECONOMY_SEED_STRIDE = 1_000_000


def _finite_number(name: str, value) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number, not a boolean")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _bounded_number(
    name: str,
    value,
    *,
    lower: float,
    upper: float | None = None,
    strict_lower: bool = False,
) -> float:
    result = _finite_number(name, value)
    lower_ok = result > lower if strict_lower else result >= lower
    upper_ok = upper is None or result <= upper
    if not lower_ok or not upper_ok:
        if upper is not None:
            domain = f"({lower}, {upper}]" if strict_lower else f"[{lower}, {upper}]"
        else:
            domain = f"> {lower}" if strict_lower else f">= {lower}"
        raise ValueError(f"{name} must be finite and {domain}")
    return result


def _per_economy_values(name: str, value, n: int) -> list:
    if isinstance(value, (list, tuple)):
        if len(value) != n:
            raise ValueError(
                f"{name} must be a scalar or have one value per economy ({n})"
            )
        return list(value)
    return [value] * n


def _validate_sanctions(sanctions, n: int) -> None:
    if sanctions is None:
        return
    if not isinstance(sanctions, (set, frozenset, list, tuple)):
        raise ValueError(
            "sanctions must be a collection of two-economy set/frozenset pairs"
        )
    for pair in sanctions:
        if not isinstance(pair, (set, frozenset)) or len(pair) != 2:
            raise ValueError(
                "sanctions entries must be set/frozenset pairs of two distinct "
                "economy indices"
            )
        for index in pair:
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or not 0 <= index < n
            ):
                raise ValueError(
                    f"sanctions economy indices must be integers in [0, {n - 1}]"
                )


def _validate_world_domains(n: int, values: dict[str, object]) -> None:
    """Validate every non-trade World lever before a coupled tick can mutate state."""
    for name in (
        "fx_friction",
        "fx_trade_cap",
        "capital_mobility",
        "peg_reserves0",
        "peg_reserve_scale",
    ):
        _bounded_number(name, values[name], lower=0.0)

    # This is also a one-step partial-adjustment coefficient, now in log-FX
    # space.  Above one it overshoots the dealer signal and can amplify rather
    # than damp successive imbalances.
    _bounded_number("fx_lambda", values["fx_lambda"], lower=0.0, upper=1.0)

    # This is a partial-adjustment coefficient in
    # ``capital_adjust * (target - current)``.  Above one it overshoots the target
    # and can oscillate/diverge instead of closing the position gap.
    _bounded_number("capital_adjust", values["capital_adjust"], lower=0.0, upper=1.0)
    _bounded_number(
        "periods_per_year",
        values["periods_per_year"],
        lower=0.0,
        strict_lower=True,
    )

    for name in (
        "migration_rate",
        "migration_max_share",
        "remittance_share",
        "remittance_tax",
        "outward_remittance_tax",
        "guest_worker_return",
        "wage_smoothing",
    ):
        _bounded_number(name, values[name], lower=0.0, upper=1.0)

    # capital_control is per-economy (scalar broadcasts): the multi-economy layer stored it as a
    # single world-wide scalar, so one economy could not close its account while others stayed
    # open (the real trilemma configuration). Scalar => same value everywhere (bit-identical).
    for index, item in enumerate(
        _per_economy_values("capital_control", values["capital_control"], n)
    ):
        _bounded_number(f"capital_control[{index}]", item, lower=0.0, upper=1.0)

    immigration_cap = values["immigration_cap"]
    if immigration_cap is not None:
        _bounded_number("immigration_cap", immigration_cap, lower=0.0)

    emigration_cap = values["emigration_cap"]
    if emigration_cap is not None:
        for index, item in enumerate(
            _per_economy_values("emigration_cap", emigration_cap, n)
        ):
            _bounded_number(
                f"emigration_cap[{index}]", item, lower=0.0, upper=1.0
            )

    import_quota = values["import_quota"]
    if import_quota is not None:
        for index, item in enumerate(
            _per_economy_values("import_quota", import_quota, n)
        ):
            _bounded_number(f"import_quota[{index}]", item, lower=0.0)

    _validate_sanctions(values["sanctions"], n)
    # This existing validator also covers scalar/vector shape, finiteness, and
    # the contractual cash-settlement unit interval under runtime mutation.
    settlement_fractions(values["external_interest_settlement_fraction"], n)


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
        external_interest_settlement_fraction=1.0,
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
        tariff=0.0,                              # POLICY (trade): scalar/per-importer tax rate
        import_quota=None,                       # POLICY (trade): cap import VOLUME (share of capacity)
        export_subsidy=None,                     # POLICY (trade): exporter's fiscus subsidises (<0 = export tax)
        capital_control: float = 0.0,            # POLICY (capital): throttle capital flows, in [0,1]
        sanctions=None,                          # POLICY (strategic): frozenset({i,j}) pairs — no bilateral flow
        emigration_cap=None,                     # POLICY (migration): origin restricts its own exit
        outward_remittance_tax: float = 0.0,     # POLICY (migration): HOST taxes outbound remittances
        guest_worker_return: float = 0.0,        # POLICY (migration): temporary migration — return rate
        wage_smoothing: float = 0.02,            # migration reacts to a PERSISTENT wage gap, not a blip
    ):
        if not configs:
            raise ValueError("World needs at least one economy config")
        _validate_world_domains(
            len(configs),
            {
                "fx_lambda": fx_lambda,
                "fx_friction": fx_friction,
                "fx_trade_cap": fx_trade_cap,
                "capital_mobility": capital_mobility,
                "capital_adjust": capital_adjust,
                "external_interest_settlement_fraction": (
                    external_interest_settlement_fraction
                ),
                "periods_per_year": periods_per_year,
                "peg_reserves0": peg_reserves0,
                "peg_reserve_scale": peg_reserve_scale,
                "migration_rate": migration_rate,
                "migration_max_share": migration_max_share,
                "remittance_share": remittance_share,
                "immigration_cap": immigration_cap,
                "remittance_tax": remittance_tax,
                "import_quota": import_quota,
                "capital_control": capital_control,
                "sanctions": sanctions,
                "emigration_cap": emigration_cap,
                "outward_remittance_tax": outward_remittance_tax,
                "guest_worker_return": guest_worker_return,
                "wage_smoothing": wage_smoothing,
            },
        )
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
        self.tariff = tariff                   # trade policy
        self.import_quota = import_quota
        self.export_subsidy = export_subsidy
        # capital policy per economy (0 = free, 1 = closed). A scalar broadcasts to every
        # economy (bit-identical); a vector lets one economy shut its account while others stay open.
        self.capital_control = _per_economy_values("capital_control", capital_control, self.n)
        self.sanctions = sanctions or set()     # strategic: blocked bilateral pairs
        self.emigration_cap = emigration_cap    # migration policy
        self.outward_remittance_tax = outward_remittance_tax
        self.guest_worker_return = guest_worker_return
        self.wage_smoothing = wage_smoothing
        self._rw_ema = None
        self._tariff_rev: List[float] = [0.0] * self.n
        self._export_subsidy_cost: List[float] = [0.0] * self.n
        self.capital_mobility = capital_mobility
        self.capital_adjust = capital_adjust
        # World-level external contract policy.  A scalar applies to every debtor;
        # a sequence selects debtor-specific cash settlement.  Store the expanded
        # vector so the effective policy is explicit in snapshots and diagnostics.
        self.external_interest_settlement_fraction = settlement_fractions(
            external_interest_settlement_fraction, self.n,
        )
        self.periods_per_year = periods_per_year
        self.fx_lambda = fx_lambda
        self.fx_friction = fx_friction
        self.fx_trade_cap = fx_trade_cap
        self._factor_income: List[float] = [0.0] * self.n
        self._factor_income_cash: List[float] = [0.0] * self.n
        self._factor_income_accrued: List[float] = [0.0] * self.n
        self._factor_income_accrual: List[float] = [0.0] * self.n
        self._factor_income_cash_bilateral: List[List[float]] = [
            [0.0] * self.n for _ in range(self.n)
        ]
        self._factor_income_accrued_bilateral: List[List[float]] = [
            [0.0] * self.n for _ in range(self.n)
        ]
        self._factor_income_accrued_unallocated: List[float] = [0.0] * self.n
        # Interest-bearing external PRINCIPAL, distinct from the dealer's full
        # settlement inventory.  Factor-income cash itself changes NFA, but it is
        # current income rather than a new capital-flow contract; recursively
        # charging interest on those settlement balances made a small external
        # position grow geometrically.  Non-interest cross-border flows update this
        # stock at the end of each tick.
        self._factor_interest_principal: List[float] = [0.0] * self.n
        # Persistent contractual external interest not yet settled.  This is a
        # debtor×creditor stock denominated in the debtor's currency.  Locking the
        # creditor here prevents a later portfolio-weight change from transferring
        # an old claim to a new owner.  The row vector remains the legacy aggregate.
        self._factor_income_arrears_bilateral: List[List[float]] = [
            [0.0] * self.n for _ in range(self.n)
        ]
        # A lossless migration bucket for pre-bilateral checkpoints whose scalar
        # arrears cannot yet be assigned because no creditor weights are observable.
        self._factor_income_arrears_unallocated: List[float] = [0.0] * self.n
        self._factor_income_arrears: List[float] = [0.0] * self.n
        self._factor_income_unpaid_tick: List[float] = [0.0] * self.n
        self._factor_income_arrears_cured_tick: List[float] = [0.0] * self.n
        # v21.2 peg / trilemma: economy 0 pegs its rate; the CB absorbs the imbalance onto
        # reserves; reserves hitting zero breaks the peg (devaluation = currency crisis).
        self.peg = peg
        self.peg_anchor = 1 if self.n > 1 else 0   # the currency economy 0 pegs to
        self.peg_reserve_scale = peg_reserve_scale
        self._peg_reserves0 = peg_reserves0
        self._peg_intact = True
        self._pent_up = 0.0            # suppressed depreciation pressure (released on the crisis)
        self._migrant_stock: List[float] = [0.0] * self.n   # v22: emigrants from i, working abroad
        self._remittances: List[float] = [0.0] * self.n     # v22: remittances received by i (curr_i)
        self._current_transfers: List[float] = [0.0] * self.n  # signed gross CA transfers (curr_i)
        self._remittance_tax_rev: List[float] = [0.0] * self.n   # v22: remittance-tax revenue (curr_i)
        self._immigration_binding: List[bool] = [False] * self.n  # v22: is the host's quota binding?
        self.rates: RateVector | None = None
        self.dealer: FXDealer | None = None
        self.world_records: List[dict] = []
        self._prev_import_value: List[float] = [0.0] * self.n   # curr_i, stale coupling
        self._prev_import_volume: List[float] = [0.0] * self.n  # destination-delivered units
        self._last_export_value: List[float] = [0.0] * self.n   # curr_i, export financing
        self._last_export_delivered_volume: List[float] = [0.0] * self.n
        self._last_export_volume: List[float] = [0.0] * self.n  # origin-shipped units
        self._iceberg_loss_volume: List[float] = [0.0] * self.n
        self._export_contract_basic_value: List[float] = [0.0] * self.n
        self._export_barrier_lot_basic_value: List[float] = [0.0] * self.n
        self._export_account_lot_basic_value: List[float] = [0.0] * self.n
        self._export_barrier_lot_contract_gap: List[float] = [0.0] * self.n
        self._export_lot_repricing_gap: List[float] = [0.0] * self.n
        self._export_inventory_withdrawal_price_adjustment: List[float] = (
            [0.0] * self.n
        )
        self._unbacked_export_volume: List[float] = [0.0] * self.n  # shipped without inventory/production
        self._import_source: List[int] = [-1] * self.n          # economy i's cheapest source j
        # Per-importer physical lots reserved from source-country C-firm inventory at
        # the coupling barrier. Reservation prevents a good from being sold both
        # domestically and abroad; settlement returns every unsold unit to its source.
        self._export_reservations: List[dict | None] = [None] * self.n
        if self.couple:
            self.rates = RateVector(self.n)
            self.dealer = FXDealer(self.economies)
            if self.capital:
                # Closed-economy configurations predating government may still be
                # used inside the open-capital World.  Give them an explicit
                # consolidated external-liability issuer instead of silently
                # assigning aggregate NFA service to a commercial bank.
                for econ in self.economies:
                    if not econ.cfg.government:
                        econ.ledger.add_account(EXTERNAL_ISSUER_ID)
                        econ.ledger.allow_negative(EXTERNAL_ISSUER_ID)
        if self.peg and self.n > 1:
            seed_reserves(self, peg_reserves0)     # the CB acquires real FX reserves
        if self.capital:
            # Reserve acquisition creates two dealer settlement legs and one
            # matching official asset.  It is not, by itself, a net private-market
            # capital position on which the coarse factor-income layer should
            # recursively accrue interest.
            self._factor_interest_principal = self.market_external_positions()

    def _validate_domains(self) -> None:
        """Revalidate mutable World levers before any per-tick state change."""
        _validate_world_domains(
            self.n,
            {
                "fx_lambda": self.fx_lambda,
                "fx_friction": self.fx_friction,
                "fx_trade_cap": self.fx_trade_cap,
                "capital_mobility": self.capital_mobility,
                "capital_adjust": self.capital_adjust,
                "external_interest_settlement_fraction": (
                    self.external_interest_settlement_fraction
                ),
                "periods_per_year": self.periods_per_year,
                "peg_reserves0": self._peg_reserves0,
                "peg_reserve_scale": self.peg_reserve_scale,
                "migration_rate": self.migration_rate,
                "migration_max_share": self.migration_max_share,
                "remittance_share": self.remittance_share,
                "immigration_cap": self.immigration_cap,
                "remittance_tax": self.remittance_tax,
                "import_quota": self.import_quota,
                "capital_control": self.capital_control,
                "sanctions": self.sanctions,
                "emigration_cap": self.emigration_cap,
                "outward_remittance_tax": self.outward_remittance_tax,
                "guest_worker_return": self.guest_worker_return,
                "wage_smoothing": self.wage_smoothing,
            },
        )

    def reserves(self) -> float:
        """The pegging CB's FX reserves — a REAL balance (the anchor currency it holds),
        not a scalar. Zero ⇒ the peg cannot be defended.

        The asset survives a policy decision to float.  Hiding it merely because
        ``peg`` was switched off left the reserve-acquisition dealer legs in NFA
        while making their matching asset disappear from both measurement and
        capital dynamics.
        """
        if self.n < 2:
            return 0.0
        led = self.economies[self.peg_anchor].ledger
        return led.balance(CBRES_ID) if led.has_account(CBRES_ID) else 0.0

    def market_external_positions(
        self,
        positions: List[float] | None = None,
        rates: List[float] | None = None,
        reserves: float | None = None,
    ) -> List[float]:
        """Dealer positions net of the CB's explicitly owned reserve asset.

        Values remain in each economy's local currency and retain the dealer sign
        convention (positive = net external liability).  The reserve swap creates
        ``+R`` in the home dealer account and ``-R`` in the anchor account; the
        official asset/liability entries offset exactly and must therefore be
        removed before portfolio targeting or interest-principal measurement.
        """
        if positions is None:
            positions = self.dealer.inventory() if self.dealer is not None else [0.0] * self.n
        result = [float(value) for value in positions]
        if self.n < 2:
            return result
        e = list(self.rates.e if rates is None else rates)
        reserve_asset = self.reserves() if reserves is None else float(reserves)
        if reserve_asset == 0.0:
            return result
        anchor = self.peg_anchor
        result[0] -= reserve_asset * e[0] / e[anchor]
        result[anchor] += reserve_asset
        return result

    # ======================================================================
    # One BSP tick: coupling barrier -> domestic markets -> cross-border
    # settlement -> domestic P&L/commit
    # ======================================================================
    def step(self) -> List[dict]:
        # Runtime policy experiments mutate World attributes directly.  This must
        # precede even the coupling barrier's journal resets so a rejected policy
        # leaves ticks, records, inventories, ledgers and observability untouched.
        self._validate_domains()
        self._coupling_barrier()                              # thin central barrier (moves no money)
        if not self.couple:
            # Preserve the ordinary closed-economy path, including the N=1 byte-identity
            # contract.  There is no reason to expose the coupling seam without a dealer.
            recs = [econ.step() for econ in self.economies]
            self.t += 1
            return recs

        # Snapshot the dealer's position + rates BEFORE any cross-border money moves.
        # The IMPORT leg settles inside the domestic goods phase (households pay the
        # dealer), so the snapshot must precede it — else the flow gate would see only
        # the export leg.
        self._inv0 = self.dealer.inventory()
        self._e0 = self.rates.e
        self._res0 = self.reserves()

        # Every country first clears its domestic goods/capital-goods markets.  Imports
        # are now realized, but P&L, fiscal settlement, metrics, behavioral lags, and
        # sensors remain open.  Mirror exports, factor income, remittances, tariffs,
        # subsidies, and any peg-reserve swap therefore enter the SAME period's accounts.
        for econ in self.economies:
            econ._run_pre_settlement_phases()
        self._dealer_update()
        recs = [econ._run_settlement_and_commit_phases() for econ in self.economies]
        self.t += 1
        return recs

    def _coupling_barrier(self) -> None:
        """The thin central barrier: compute cross-border export demand / import supply
        on last tick's prices + the current rate vector, and grope the rate.

        v20.1: the dealer's net inventory is the groping signal (§3); with zero trade it
        is all-zero ⇒ rates stay flat. Trade injection into the goods sessions lands in
        v20.2. Reductions across economies use fixed economy-id order (§9).
        """
        # Tick journals are observations, never carry-forward stocks.  Reset them
        # even when trade is disabled at run time; successful settlement below
        # overwrites them with this tick's realized values and physical volumes.
        for econ in self.economies:
            econ._fx_import_transaction_value_external = 0.0
            econ._fx_import_value_external = 0.0
            econ._fx_import_delivered_volume_external = 0.0
            econ._fx_import_volume_external = 0.0
            econ._fx_export_transaction_value_external = 0.0
            econ._fx_export_value_external = 0.0
            econ._fx_export_delivered_volume_external = 0.0
            econ._fx_export_shipped_volume_external = 0.0
            econ._fx_export_volume_external = 0.0
            econ._fx_iceberg_loss_volume_external = 0.0
            econ._fx_export_contract_basic_value_external = 0.0
            econ._fx_export_barrier_lot_basic_value_external = 0.0
            econ._fx_export_account_lot_basic_value_external = 0.0
            econ._fx_export_barrier_lot_contract_gap_external = 0.0
            econ._fx_export_lot_repricing_gap_external = 0.0
            econ._fx_export_inventory_withdrawal_price_adjustment_external = 0.0
            econ._tariff_revenue_external = 0.0
            econ._export_subsidy_cost_external = 0.0
        if not self.couple:
            return
        if self.trade:
            prepare_trade(self)               # set each economy's import offer + export order
        else:
            # Runtime policy experiments may turn trade off after an active tick.
            # These are flows, not financing stocks: do not let the last transaction
            # leak into the disabled tick's World current account or fiscal journals.
            self._prev_import_value = [0.0] * self.n
            self._prev_import_volume = [0.0] * self.n
            self._last_export_value = [0.0] * self.n
            self._last_export_delivered_volume = [0.0] * self.n
            self._last_export_volume = [0.0] * self.n
            self._iceberg_loss_volume = [0.0] * self.n
            self._export_contract_basic_value = [0.0] * self.n
            self._export_barrier_lot_basic_value = [0.0] * self.n
            self._export_account_lot_basic_value = [0.0] * self.n
            self._export_barrier_lot_contract_gap = [0.0] * self.n
            self._export_lot_repricing_gap = [0.0] * self.n
            self._export_inventory_withdrawal_price_adjustment = [0.0] * self.n
            self._unbacked_export_volume = [0.0] * self.n
            self._tariff_rev = [0.0] * self.n
            self._export_subsidy_cost = [0.0] * self.n
        # (v20.1 with couple-only and no trade: nothing to set; groping happens in settle.)

    def _dealer_update(self) -> None:
        """Settle realized trade, grope the rate on the dealer's net inventory, book the
        revaluation, and record the World FX gauges (§6/§7).

        v20.1 (couple, no trade): inventory 0, rates flat ⇒ every gauge trivially zero/unit.
        This runs at the explicit Economy coupling seam, before domestic settlement and
        record commit, so all cross-border flows belong to the period that generated them.
        """
        inv0, e0 = self._inv0, self._e0   # snapshotted in step(), before the domestic step

        if self.trade:
            settle_trade(self)                # imports/exports/tariff flows (no groping)
        factor_position_delta = [0.0] * self.n
        if self.capital:
            # Keep the historical one-argument call boundary for diagnostic fault
            # injection while supplying the non-anticipating opening stock through
            # a transient field consumed by ``capital_interest``.
            opening_market = self.market_external_positions(inv0, e0, self._res0)
            self._factor_interest_positions = list(getattr(
                self, "_factor_interest_principal", opening_market,
            ))
            factor_inv0 = self.dealer.inventory()
            try:
                capital_interest(self)            # v21: service opening positions only
            finally:
                del self._factor_interest_positions
            factor_inv1 = self.dealer.inventory()
            factor_position_delta = [
                factor_inv1[i] - factor_inv0[i] for i in range(self.n)
            ]
        if self.migration:
            run_migration(self)               # v22: labor flow + remittances

        # Peg defense is a real FX swap, so it belongs inside the full-tick flow
        # perimeter.  Compute the signal (and execute that swap) before the hard gate;
        # apply the rate move only after the gate has passed.
        grope_signal = rate_grope_signal(self)

        if self.capital:
            # Advance contract principal only by NON-interest external flows.  The
            # current factor-income payment remains in dealer inventory/NFA, but
            # does not become fresh principal and earn interest on itself next tick.
            # Peg defence is already inside ``grope_signal``; netting the matching
            # reserve movement makes that official swap neutral here.
            opening_market = self.market_external_positions(inv0, e0, self._res0)
            closing_market = self.market_external_positions(
                self.dealer.inventory(), e0, self.reserves(),
            )
            principal = list(getattr(
                self, "_factor_interest_principal", opening_market,
            ))
            self._factor_interest_principal = [
                principal[i]
                + (closing_market[i] - opening_market[i])
                - factor_position_delta[i]
                for i in range(self.n)
            ]

        # HARD GATE (pre-grope, so no revaluation contaminates it): the dealer is a
        # passthrough ⇒ its numéraire FLOW ≡ 0 — the multilateral BoP identity.
        self.dealer.assert_flow_is_passthrough(inv0, e0)
        grope_rates(self, grope_signal)       # NOW move the rates (every flow has settled)
        self.dealer.book_revaluation(e0, self.rates)   # the only source of net-worth change

        inv = self.dealer.inventory()
        e = self.rates.e
        bop_numeraire = self.dealer.net_worth_numeraire(self.rates)
        # v21 external-position gauges (numéraire): NFA_i = −(dealer i-position)/e_i (a
        # positive dealer position is a foreign CLAIM on economy i ⇒ i's net foreign
        # LIABILITY); factor income_i (received) = −(i's interest outflow)/e_i.
        # NFA_i = (i's foreign ASSETS) − (foreigners' CLAIMS on i), in the numéraire.
        # The dealer's position is the claims; the pegging CB's FX reserves are a real
        # foreign asset of economy 0 AND a foreign claim on the anchor — the two cancel in
        # the world sum, so Σ_i NFA_i = −(cumulative revaluation) still closes exactly.
        nfa = [-inv[i] / e[i] for i in range(self.n)]
        res = self.reserves()
        if self.n > 1 and res != 0.0:
            a = self.peg_anchor
            nfa[0] += res / e[a]      # economy 0 HOLDS the anchor's currency (a foreign asset)
            nfa[a] -= res / e[a]      # ... which is a foreign claim ON the anchor
        # Flows settled at the opening vector e0.  Closing e is reserved for end-of-
        # tick stocks and revaluation; valuing the CA at post-grope rates creates a
        # mechanical world residual.
        factor_cash = [-self._factor_income[i] / e0[i] for i in range(self.n)]
        factor_accrued = [
            -self._factor_income_accrued[i] / e0[i] for i in range(self.n)
        ]
        remit = [self._remittances[i] / e0[i] for i in range(self.n)]
        transfers = [self._current_transfers[i] / e0[i] for i in range(self.n)]
        tb = [
            (self._last_export_value[i] - self._prev_import_value[i]) / e0[i]
            for i in range(self.n)
        ]
        current_account_cash = [
            tb[i] + factor_cash[i] + transfers[i] for i in range(self.n)
        ]
        current_account_accrued = [
            tb[i] + factor_accrued[i] + transfers[i] for i in range(self.n)
        ]

        # Contractual arrears are end-of-tick stocks and therefore use closing e,
        # unlike cash/accrual flows above.  Every A[i][j] is denominated in debtor
        # i's currency, so creditor assets must also be translated with e_i.
        arrears_bilateral = [
            [
                self._factor_income_arrears_bilateral[i][j] / e[i]
                for j in range(self.n)
            ]
            for i in range(self.n)
        ]
        arrears_unallocated = [
            self._factor_income_arrears_unallocated[i] / e[i]
            for i in range(self.n)
        ]
        arrears_liabilities = [
            self._factor_income_arrears[i] / e[i] for i in range(self.n)
        ]
        arrears_assets = [
            sum(arrears_bilateral[i][j] for i in range(self.n))
            for j in range(self.n)
        ]
        arrears_nfa = [
            arrears_assets[i] - arrears_liabilities[i] for i in range(self.n)
        ]
        arrears_asset_revaluation = [
            sum(
                self._factor_income_arrears_bilateral[debtor][creditor]
                * (1.0 / e[debtor] - 1.0 / e0[debtor])
                for debtor in range(self.n)
            )
            for creditor in range(self.n)
        ]
        arrears_liability_revaluation = [
            self._factor_income_arrears[i] * (1.0 / e[i] - 1.0 / e0[i])
            for i in range(self.n)
        ]
        arrears_nfa_revaluation = [
            arrears_asset_revaluation[i] - arrears_liability_revaluation[i]
            for i in range(self.n)
        ]
        arrears_nfa_transaction_change = [
            factor_accrued[i] - factor_cash[i] for i in range(self.n)
        ]
        augmented_nfa = [nfa[i] + arrears_nfa[i] for i in range(self.n)]
        cash_bilateral = [
            [
                self._factor_income_cash_bilateral[i][j] / e0[i]
                for j in range(self.n)
            ]
            for i in range(self.n)
        ]
        accrued_bilateral = [
            [
                self._factor_income_accrued_bilateral[i][j] / e0[i]
                for j in range(self.n)
            ]
            for i in range(self.n)
        ]
        self.world_records.append(
            {
                "t": self.t,
                "e": list(e),
                "flow_e": list(e0),
                "dealer_inventory": list(inv),
                "import_value": list(self._prev_import_value),
                "import_delivered_volume": list(self._prev_import_volume),
                "import_volume": list(self._prev_import_volume),
                "export_delivered_volume": list(self._last_export_delivered_volume),
                "export_shipped_volume": list(self._last_export_volume),
                "iceberg_loss_volume": list(self._iceberg_loss_volume),
                "export_contract_basic_value": list(
                    self._export_contract_basic_value
                ),
                "export_barrier_lot_basic_value": list(
                    self._export_barrier_lot_basic_value
                ),
                "export_account_lot_basic_value": list(
                    self._export_account_lot_basic_value
                ),
                "export_barrier_lot_contract_gap": list(
                    self._export_barrier_lot_contract_gap
                ),
                "export_lot_repricing_gap": list(self._export_lot_repricing_gap),
                "export_inventory_withdrawal_price_adjustment": list(
                    self._export_inventory_withdrawal_price_adjustment
                ),
                "unbacked_export_volume": list(self._unbacked_export_volume),
                "nfa": nfa,
                "nfa_cash": list(nfa),
                "augmented_nfa": augmented_nfa,
                "factor_income": factor_cash,
                "factor_income_cash": factor_cash,
                "factor_income_accrued": factor_accrued,
                "factor_income_accrual": factor_accrued,
                "factor_income_cash_bilateral": cash_bilateral,
                "factor_income_accrued_bilateral": accrued_bilateral,
                "factor_income_arrears": arrears_liabilities,
                "factor_income_arrears_bilateral": arrears_bilateral,
                "factor_income_arrears_unallocated": arrears_unallocated,
                "factor_income_arrears_assets": arrears_assets,
                "factor_income_arrears_liabilities": arrears_liabilities,
                "factor_income_arrears_nfa": arrears_nfa,
                "factor_income_arrears_nfa_transaction_change": (
                    arrears_nfa_transaction_change
                ),
                "factor_income_arrears_revaluation": arrears_nfa_revaluation,
                "factor_income_unpaid_tick": [
                    self._factor_income_unpaid_tick[i] / e0[i] for i in range(self.n)
                ],
                "factor_income_arrears_cured_tick": [
                    self._factor_income_arrears_cured_tick[i] / e0[i]
                    for i in range(self.n)
                ],
                "bop_numeraire": bop_numeraire,
                "dealer_valuation": self.dealer.valuation,
                "reserves": self.reserves(),
                "peg_intact": self._peg_intact,
                "migrant_stock": list(self._migrant_stock),
                "remittances": remit,
                "current_transfers": transfers,
                "current_account": current_account_cash,
                "current_account_cash": current_account_cash,
                "current_account_accrued": current_account_accrued,
                "current_account_accrual": current_account_accrued,
                "remittance_tax_rev": [self._remittance_tax_rev[i] / e0[i] for i in range(self.n)],
                "immigration_binding": list(self._immigration_binding),
                "tariff_rev": [self._tariff_rev[i] / e0[i] for i in range(self.n)],
                "export_subsidy_cost": [self._export_subsidy_cost[i] / e0[i] for i in range(self.n)],
            }
        )

    def run(self, n_ticks: int | None = None) -> List[List[dict]]:
        n = n_ticks if n_ticks is not None else self.economies[0].cfg.n_ticks
        for _ in range(n):
            self.step()
        return [econ.records for econ in self.economies]

    def sanctioned(self, i: int, j: int) -> bool:
        """Whether economies i and j have severed their bilateral flows (a sanction)."""
        return frozenset({i, j}) in self.sanctions

    # -- convenience -----------------------------------------------------------
    @property
    def records(self) -> List[List[dict]]:
        """Per-economy record series, indexed by economy id."""
        return [econ.records for econ in self.economies]
