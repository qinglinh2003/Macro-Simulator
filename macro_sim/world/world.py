"""The `World` container (PLAN_v20 §0.5 component ②, §5 BSP tick).

v20.0 delivers the substrate only: N economies + residency/currency tags + the BSP tick
SKELETON (an empty coupling barrier + the independent domestic step + an empty dealer
update) + per-economy RNG isolation. No coupling — that lands in v20.1 (FX) and v20.2
(trade). The load-bearing property is that this layer is INERT: N economies run exactly
as N independent closed economies, so `World([cfg])` ≡ `Economy(cfg)` byte-for-byte.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, List

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

    for name in ("migration_rate", "migration_max_share", "wage_smoothing"):
        _bounded_number(name, values[name], lower=0.0, upper=1.0)

    # B5a: the remittance taxes are per-economy levers now (scalar broadcasts)
    for name in ("remittance_tax", "outward_remittance_tax"):
        for index, item in enumerate(_per_economy_values(name, values[name], n)):
            _bounded_number(f"{name}[{index}]", item, lower=0.0, upper=1.0)

    # per-economy migration policy (scalar broadcasts => bit-identical). remittance_share is the
    # origin diaspora's send-home rate; guest_worker_return is the HOST's temporary-migration return
    # rate. Vectors let e.g. India remit more, or the Gulf/Hub run guest-worker regimes the others do not.
    for name in ("remittance_share", "guest_worker_return"):
        for index, item in enumerate(_per_economy_values(name, values[name], n)):
            _bounded_number(f"{name}[{index}]", item, lower=0.0, upper=1.0)

    # capital_control is per-economy (scalar broadcasts): the multi-economy layer stored it as a
    # single world-wide scalar, so one economy could not close its account while others stayed
    # open (the real trilemma configuration). Scalar => same value everywhere (bit-identical).
    for index, item in enumerate(
        _per_economy_values("capital_control", values["capital_control"], n)
    ):
        _bounded_number(f"capital_control[{index}]", item, lower=0.0, upper=1.0)

    # immigration_cap: None => open borders everywhere; a scalar broadcasts; a vector caps each HOST
    # separately (a host admits <= cap x its population). A very large per-host value = effectively open.
    immigration_cap = values["immigration_cap"]
    if immigration_cap is not None:
        for index, item in enumerate(_per_economy_values("immigration_cap", immigration_cap, n)):
            if item is None:
                continue      # B5a: per-economy None = that host is open (legal mix)
            _bounded_number(f"immigration_cap[{index}]", item, lower=0.0)

    emigration_cap = values["emigration_cap"]
    if emigration_cap is not None:
        for index, item in enumerate(
            _per_economy_values("emigration_cap", emigration_cap, n)
        ):
            if item is None:
                continue      # B5a: per-economy None = that origin is open (legal mix)
            _bounded_number(
                f"emigration_cap[{index}]", item, lower=0.0, upper=1.0
            )

    import_quota = values["import_quota"]
    if import_quota is not None:
        for index, item in enumerate(
            _per_economy_values("import_quota", import_quota, n)
        ):
            if item is None:
                continue      # B5a: per-economy None = that importer is open (legal mix)
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
        fx_spread: float = 0.0,       # DEALER-BLEED FIX A: bid-ask on PRIVATE settlement
                                      # conversions (trade payout, remittances); the margin
                                      # stays in dealer inventory = market-making revenue.
                                      # 0.0 = legacy zero-spread = bit-identical.
        fx_loss_mutualization: bool = False,   # DEALER-BLEED FIX C: annual pro-rata
                                      # settlement of realized dealer losses against member
                                      # fiscal accounts (clearing-union). False = legacy.
        fx_trade_cap: float = 0.15,
        capital_mobility: float = 0.0,
        capital_adjust: float = 0.1,
        external_interest_settlement_fraction=1.0,
        periods_per_year: float = 12.0,
        peg: bool = False,
        peg_economy: int = 0,        # WHICH economy pegs its rate (was hardcoded to 0)
        peg_anchor: int | None = None,  # the currency it pegs TO (None => default, != pegger)
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
        shocks: Any = None,                       # v27: semantic exogenous ShockTape/ShockEngine
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
            econ = Economy(cfg, _defer_shocks=True)
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
        self.couple = couple or trade or capital or migration or peg
        # Any cross-border flow or a legacy constructor-time peg needs the FX layer.
        # A later runtime peg policy cannot manufacture this structural mechanism;
        # Controller capability checks reject it when the World started uncoupled.
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

        # B5a: every cross-border lever now has a per-economy OWNER. Legacy ctor
        # vectors SEED each economy's ExternalPolicy; from then on the world's
        # coupling vectors are re-derived at the coupling barrier (one atomic
        # commit point -- no per-economy ordering skew). Legacy sanction pairs
        # seed BOTH sides (unilateral ownership, symmetric effect, A6).
        from macro_sim.core.external_policy import ExternalPolicy
        from macro_sim.world.trade import lever as _lv

        def _capv(v, i):
            if v is None:
                return None
            if isinstance(v, (list, tuple)):
                return None if v[i] is None else float(v[i])
            return float(v)

        def _lvchk(name, v, i):
            # fail-fast at construction with the LEGACY trade-time message
            if isinstance(v, (list, tuple)) and len(v) != self.n:
                raise ValueError(
                    f"{name} must be a scalar or have one value per economy ({self.n})"
                )
            return _lv(v, i)

        legacy_pairs = sanctions or set()
        # resolve the legacy anchor default HERE (the peg block below runs later):
        # explicit anchor wins; else the first economy that isn't the pegger
        if peg:
            _anchor_resolved = peg_anchor if peg_anchor is not None \
                else (1 if peg_economy != 1 else 0)
        else:
            _anchor_resolved = None
        for i, econ in enumerate(self.economies):
            econ.external_policy = ExternalPolicy(
                tariff=_lvchk("tariff", tariff, i),
                import_quota=_capv(import_quota, i),
                export_subsidy=_lvchk("export_subsidy", export_subsidy, i),
                capital_control=float(self.capital_control[i]),
                external_interest_settlement_fraction=_lv(
                    external_interest_settlement_fraction, i
                ),
                sanctions_imposed_on=frozenset(
                    j for pair in legacy_pairs for j in pair if i in pair and j != i
                ),
                immigration_cap=_capv(immigration_cap, i),
                emigration_cap=_capv(emigration_cap, i),
                remittance_tax=_lv(remittance_tax, i),
                outward_remittance_tax=_lv(outward_remittance_tax, i),
                guest_worker_return=_lv(guest_worker_return, i),
                fx_regime=("peg" if peg and i == peg_economy else "float"),
                peg_anchor=(_anchor_resolved if peg and i == peg_economy else None),
                peg_reserve_scale=float(peg_reserve_scale),
            )
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
        assert 0.0 <= fx_spread < 0.1, "fx_spread must be in [0, 0.1)"
        self.fx_spread = fx_spread
        self.fx_loss_mutualization = bool(fx_loss_mutualization)
        self._conversion_volume = [0.0] * len(configs)   # numeraire, per economy (mutualization key)
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
        # v21.2 peg / trilemma, B5b multi-pegger DATA MODEL (A6): per-pegger PegState
        # keyed by economy id; the legacy world.peg/peg_economy/peg_anchor/_peg_intact/
        # _pent_up surface survives as property shims over the (P0: single) state.
        # peg_economy as AUTHORITY is deleted -- it derives from fx_regime.
        from macro_sim.world.capital import PegState
        self._legacy_peg_economy = peg_economy
        self._legacy_peg_anchor = (
            _anchor_resolved if _anchor_resolved is not None
            else (1 if self.n > 1 and peg_economy != 1 else 0)
        )
        self._legacy_peg_reserve_scale = peg_reserve_scale
        self.peg_states: dict[int, PegState] = {}
        if peg and self.n > 1:
            assert 0 <= peg_economy < self.n, "peg_economy out of range"
            assert 0 <= self._legacy_peg_anchor < self.n \
                and self._legacy_peg_anchor != peg_economy, \
                "peg_anchor must be a valid economy != peg_economy"
            self.peg_states[peg_economy] = PegState(
                anchor=self._legacy_peg_anchor,
                reserve_account_id=f"CBRES:{peg_economy}",
                reserve_scale=peg_reserve_scale,
            )
        self._peg_reserves0 = peg_reserves0
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
        # v27: one World-owned engine realizes multi-economy shocks atomically.
        # Legacy per-Config energy scenarios are translated into the same tape,
        # with explicit economy targets, before binding.
        from macro_sim.shocks import ShockEngine, ShockTape, legacy_energy_spec

        legacy_specs = tuple(
            item for i, econ in enumerate(self.economies)
            if (item := legacy_energy_spec(econ.cfg, economy_id=i)) is not None
        )
        if isinstance(shocks, ShockEngine):
            if shocks.current_tick >= 0:
                raise ValueError("a running ShockEngine cannot seed a new World")
            existing = {item.shock_id for item in shocks.specs}
            additions = tuple(item for item in legacy_specs if item.shock_id not in existing)
            self.shock_engine = ShockEngine(tuple(shocks.specs) + additions)
        else:
            tape = ShockTape.coerce(shocks)
            specs = tape.specs + legacy_specs
            self.shock_engine = ShockEngine(specs) if specs else None
        if self.shock_engine is not None:
            self.shock_engine.bind(self.economies, world=self)
            for econ in self.economies:
                econ.shock_engine = self.shock_engine
        self._commit_external_policies()   # B5a: normalize the coupling vectors from day one

    def schedule_shock(self, spec: Any) -> None:
        """Append a concrete shock at this World boundary."""
        from macro_sim.shocks import ShockEngine

        if self.shock_engine is None:
            candidate = ShockEngine()
            candidate.bind(self.economies, world=self)
            candidate.current_tick = self.t - 1
            candidate.schedule(
                spec, economies=self.economies, world=self, boundary_tick=self.t,
            )
            # Publish the shared identity only after successful validation.
            self.shock_engine = candidate
            for econ in self.economies:
                econ.shock_engine = candidate
            return
        self.shock_engine.schedule(
            spec, economies=self.economies, world=self, boundary_tick=self.t,
        )

    def shock_bulletins(
        self, economy_id: int, *, role: str = "public",
    ) -> tuple[dict[str, Any], ...]:
        if self.shock_engine is None:
            return ()
        return self.shock_engine.bulletins(economy_id, self.t, role=role)

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

    # ---- B5b legacy peg surface: property shims over peg_states (P0: <=1) ----
    def _single_peg(self):
        states = self.__dict__.get("peg_states")
        if states is None:
            return None                       # pre-B5b pickle: no states restored
        # v26 §1.2 fix: a peg HANDOVER (0 exits, 1 adopts) leaves a dead state
        # beside the live one -- accessors must select the ACTIVE peg, never
        # insertion order. Dead states are kept for history (legacy broken-peg
        # record semantics), but they no longer answer for the world.
        for st in states.values():
            if st.intact and not st.exit_pending:
                return st
        for st in states.values():
            if st.exit_pending:
                return st
        return next(iter(states.values()), None)

    @property
    def peg(self) -> bool:
        states = self.__dict__.get("peg_states")
        if states is None:
            return bool(self.__dict__.get("peg", False))
        return any(st.intact or st.exit_pending for st in states.values())

    @property
    def peg_economy(self) -> int:
        states = self.__dict__.get("peg_states")
        if states:
            for i, st in states.items():      # the ACTIVE pegger answers (v26 §1.2)
                if st.intact and not st.exit_pending:
                    return i
            for i, st in states.items():
                if st.exit_pending:
                    return i
            return next(iter(states))
        return int(self.__dict__.get("_legacy_peg_economy",
                                     self.__dict__.get("peg_economy", 0)))

    @property
    def peg_anchor(self) -> int:
        st = self._single_peg()
        if st is not None:
            return st.anchor
        return int(self.__dict__.get("_legacy_peg_anchor",
                                     self.__dict__.get("peg_anchor", 0)))

    @property
    def peg_reserve_scale(self) -> float:
        st = self._single_peg()
        if st is not None:
            return st.reserve_scale
        return float(self.__dict__.get("_legacy_peg_reserve_scale",
                                       self.__dict__.get("peg_reserve_scale", 1.0e5)))

    @property
    def _peg_intact(self) -> bool:
        st = self._single_peg()
        return st.intact if st is not None else bool(self.__dict__.get("_peg_intact", True))

    @_peg_intact.setter
    def _peg_intact(self, value: bool) -> None:
        st = self._single_peg()
        if st is not None:
            st.intact = bool(value)
        else:
            self.__dict__["_peg_intact"] = bool(value)

    @property
    def _pent_up(self) -> float:
        st = self._single_peg()
        return st.pent_up if st is not None else float(self.__dict__.get("_pent_up", 0.0))

    @_pent_up.setter
    def _pent_up(self, value: float) -> None:
        st = self._single_peg()
        if st is not None:
            st.pent_up = float(value)
        else:
            self.__dict__["_pent_up"] = float(value)

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
        st = self._single_peg()
        if st is None:
            led = self.economies[self.peg_anchor].ledger   # pre-B5b pickle fallback
            return led.balance(CBRES_ID) if led.has_account(CBRES_ID) else 0.0
        led = self.economies[st.anchor].ledger
        acct = st.reserve_account_id
        return led.balance(acct) if led.has_account(acct) else 0.0

    def _peg_reserve_balances(self) -> dict[int, float]:
        """Return every pegger's official reserve balance, including old states.

        ``peg_states`` deliberately retains broken and voluntarily exited pegs.  Their
        reserve assets remain live balance-sheet items until an explicit liquidation;
        selecting only the currently active state therefore turns the settlement legs
        of an earlier peg into a spurious private external position after a handoff.
        """
        states = self.__dict__.get("peg_states")
        if states is None:  # pre-B5b checkpoint compatibility
            return {self.peg_economy: self.reserves()}
        balances: dict[int, float] = {}
        for pegger, state in states.items():
            ledger = self.economies[state.anchor].ledger
            account = state.reserve_account_id
            balances[pegger] = (
                float(ledger.balance(account)) if ledger.has_account(account) else 0.0
            )
        return balances

    def market_external_positions(
        self,
        positions: List[float] | None = None,
        rates: List[float] | None = None,
        reserves: Mapping[int, float] | float | None = None,
    ) -> List[float]:
        """Dealer positions net of every CB's explicitly owned reserve asset.

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
        states = self.__dict__.get("peg_states")
        if states is None:  # pre-B5b checkpoint compatibility
            pegger = self.peg_economy
            if reserves is None:
                reserve_asset = self.reserves()
            elif isinstance(reserves, Mapping):
                reserve_asset = float(reserves.get(pegger, 0.0))
            else:
                reserve_asset = float(reserves)
            if reserve_asset != 0.0:
                anchor = self.peg_anchor
                result[pegger] -= reserve_asset * e[pegger] / e[anchor]
                result[anchor] += reserve_asset
            return result

        if reserves is None:
            reserve_balances = self._peg_reserve_balances()
        elif isinstance(reserves, Mapping):
            reserve_balances = reserves
        else:
            # Retain the historical scalar call surface for external callers.  New
            # World snapshots use a per-pegger mapping so old retained assets cannot
            # disappear when the active-peg selector changes.
            reserve_balances = {self.peg_economy: float(reserves)}
        for pegger, state in sorted(states.items()):
            reserve_asset = float(reserve_balances.get(pegger, 0.0))
            if reserve_asset == 0.0:
                continue
            anchor = state.anchor
            result[pegger] -= reserve_asset * e[pegger] / e[anchor]
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
        # audit fix: COMMIT the per-economy policies FIRST, so domain validation
        # sees this tick's stances -- a bad value surfaces on the tick it is set,
        # never one tick late against stale vectors.
        self._commit_external_policies()
        self._validate_domains()
        if self.shock_engine is not None:
            self.shock_engine.begin_tick(self.t, self.economies, world=self)
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
        self._res0 = self._peg_reserve_balances()

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

    def _commit_external_policies(self) -> None:
        """Atomically re-derive the world coupling vectors from each economy's
        ExternalPolicy (B5a). Runs at construction and at the top of every
        coupling barrier: mutations to econ.external_policy anywhere in a tick
        all take effect together at the next barrier."""
        self._fx_spread_margin_tick = 0.0   # per-tick declared dealer margin (numeraire)
        eps = [e.external_policy for e in self.economies]

        # ---- PREPARE (pure): build every derived value into locals ----
        tariff = [p.tariff for p in eps]
        import_quota = (
            None if all(p.import_quota is None for p in eps)
            else [p.import_quota for p in eps]
        )
        export_subsidy = [p.export_subsidy for p in eps]
        capital_control = [float(p.capital_control) for p in eps]
        settlement_fraction = [
            float(p.external_interest_settlement_fraction) for p in eps
        ]
        immigration_cap = (
            None if all(p.immigration_cap is None for p in eps)
            else [p.immigration_cap for p in eps]
        )
        emigration_cap = (
            None if all(p.emigration_cap is None for p in eps)
            else [p.emigration_cap for p in eps]
        )
        remittance_tax = [p.remittance_tax for p in eps]
        outward_remittance_tax = [p.outward_remittance_tax for p in eps]
        guest_worker_return = [p.guest_worker_return for p in eps]
        # sanctions: a DERIVED cache of the unilateral stances (never authoritative)
        sanctions = {
            frozenset({i, j})
            for i, p in enumerate(eps) for j in p.sanctions_imposed_on if j != i
        }

        # ---- VALIDATE (pure): every raisable check runs BEFORE the first write.
        # v26 §1.1/§1.2: an out-of-range sanctions target must never reach the
        # cache; a vetoed commit leaves NO partial state anywhere. ----
        self._validate_peg_constraints(eps)
        _validate_sanctions(sanctions, self.n)
        _validate_world_domains(self.n, {
            "fx_lambda": self.fx_lambda, "fx_friction": self.fx_friction,
            "fx_trade_cap": self.fx_trade_cap,
            "capital_mobility": self.capital_mobility,
            "capital_adjust": self.capital_adjust,
            "external_interest_settlement_fraction": settlement_fraction,
            "periods_per_year": self.periods_per_year,
            "peg_reserves0": self._peg_reserves0,
            "peg_reserve_scale": self.peg_reserve_scale,
            "migration_rate": self.migration_rate,
            "migration_max_share": self.migration_max_share,
            "remittance_share": self.remittance_share,
            "immigration_cap": immigration_cap,
            "remittance_tax": remittance_tax,
            "import_quota": import_quota,
            "capital_control": capital_control,
            "sanctions": sanctions,
            "emigration_cap": emigration_cap,
            "outward_remittance_tax": outward_remittance_tax,
            "guest_worker_return": guest_worker_return,
            "wage_smoothing": self.wage_smoothing,
        })

        # ---- COMMIT: infallible assignments only ----
        self.tariff = tariff
        self.import_quota = import_quota
        self.export_subsidy = export_subsidy
        self.capital_control = capital_control
        self.external_interest_settlement_fraction = settlement_fraction
        self.immigration_cap = immigration_cap
        self.emigration_cap = emigration_cap
        self.remittance_tax = remittance_tax
        self.outward_remittance_tax = outward_remittance_tax
        self.guest_worker_return = guest_worker_return
        self.sanctions = sanctions
        self._reconcile_peg_states(eps)
        self._settle_dealer_mutualization()

    def _settle_dealer_mutualization(self) -> None:
        """DEALER-BLEED FIX C (clearing-union): once a year, a NEGATIVE dealer net
        worth is settled pro-rata by conversion volume against member fiscal
        accounts -- the residual cost of running the exchange-rate system becomes
        an explicit, conserving national expense instead of an unbounded leak."""
        if (
            not self.fx_loss_mutualization
            or self.dealer is None
            or self.t == 0
            or self.t % 365 != 0
        ):
            return
        nw = self.dealer.net_worth_numeraire(self.rates)
        if nw >= -1e-9:
            self._conversion_volume = [0.0] * self.n
            return
        loss = -nw
        vol_total = sum(self._conversion_volume)
        from macro_sim.world.fx import DEALER_ID
        for i, econ in enumerate(self.economies):
            share = (
                self._conversion_volume[i] / vol_total if vol_total > 1e-12
                else 1.0 / self.n
            )
            levy_num = loss * share
            fiscal = getattr(econ, "_fiscal", None)
            if fiscal is None or not econ.ledger.has_account(fiscal):
                continue
            levy_local = levy_num * self.rates.e[i]        # numeraire -> currency i
            if levy_local > 1e-12:
                econ.ledger.transfer(fiscal, DEALER_ID, levy_local)
                econ._fx_mutualization_paid = (
                    getattr(econ, "_fx_mutualization_paid", 0.0) + levy_local
                )
        self._conversion_volume = [0.0] * self.n

    def _validate_peg_constraints(self, eps) -> None:
        """P0 joint peg constraints -- PURE checks, called before any commit write
        so a violation leaves the world untouched (audit fix: true atomicity)."""
        desired = [(i, p) for i, p in enumerate(eps) if p.fx_regime == "peg" and self.n > 1]
        if desired and (not self.couple or self.rates is None):
            raise ValueError("P0 runtime constraint: peg requires the coupled FX layer")
        if len(desired) > 1:
            raise ValueError("P0 runtime constraint: at most ONE pegger")
        for i, p in desired:
            a = p.peg_anchor
            if a is None or not (0 <= a < self.n) or a == i:
                raise ValueError(f"economy {i}: peg requires a valid anchor != self, got {a!r}")
            if eps[a].fx_regime == "peg":
                raise ValueError(f"economy {i}: anchor {a} must not itself peg (no chains/cycles)")

    def _reconcile_peg_states(self, eps) -> None:
        """B5b: fx_regime is the AUTHORITY (A6; peg_economy is derived). At each
        barrier: validate the P0 constraints, adopt new pegs (reserve acquisition
        swap), apply anchor changes (liquidate -> convert -> reset pent_up),
        stage voluntary exits (pent-up released ONCE by peg_defense), and sync
        the live reserve scale."""
        from macro_sim.world.capital import PegState, seed_reserves
        desired = {
            i: p for i, p in enumerate(eps)
            if p.fx_regime == "peg" and self.n > 1
        }
        # voluntary exits: regime flipped to float while an INTACT peg stands
        for i in list(self.peg_states):
            st = self.peg_states[i]
            if i not in desired:
                if st.intact and not st.exit_pending:
                    st.exit_pending = True   # released once by peg_defense, then free float
                continue
            # a re-peg over a BROKEN/EXITED state is a fresh adoption below

            # Anchor change (A6): liquidate old-anchor reserves, convert at the
            # current cross, acquire in the new anchor's ledger, reset pent_up.
            #
            # This also applies when the retained state is no longer intact.  An
            # exited/broken peg may still own a positive reserve asset.  Replacing
            # that state during a later re-adoption without first moving the asset
            # would orphan the old CBRES account: the balance would remain in the
            # old anchor's ledger but disappear from reserve ownership, NFA, and
            # observation records.
            new_anchor = desired[i].peg_anchor
            if new_anchor != st.anchor:
                old_led = self.economies[st.anchor].ledger
                bal = old_led.balance(st.reserve_account_id) \
                    if old_led.has_account(st.reserve_account_id) else 0.0
                if bal > 0.0 and self.rates is not None:
                    from macro_sim.world.fx import DEALER_ID
                    old_led.transfer(st.reserve_account_id, DEALER_ID, bal)
                    converted = bal * self.rates.bilateral(new_anchor, st.anchor)
                    new_led = self.economies[new_anchor].ledger
                    if not new_led.has_account(st.reserve_account_id):
                        new_led.add_account(st.reserve_account_id)
                    new_led.transfer(DEALER_ID, st.reserve_account_id, converted)
                st.anchor = new_anchor
                st.pent_up = 0.0
            st.reserve_scale = float(desired[i].peg_reserve_scale)

        # adoptions: a NEW pegger (or a re-peg after a break/exit)
        for i, p in desired.items():
            st = self.peg_states.get(i)
            if st is not None and st.intact and not st.exit_pending:
                continue                       # already pegging
            self.peg_states[i] = PegState(
                anchor=p.peg_anchor,
                reserve_account_id=f"CBRES:{i}",
                reserve_scale=float(p.peg_reserve_scale),
            )
            if self.rates is not None and self.t > 0:
                # A same-barrier handover temporarily has the old peg's orderly-exit
                # state and the new active state side by side.  Do not let the legacy
                # single-peg accessor send the new war chest to the old CBRES account.
                seed_reserves(self, self._peg_reserves0, pegger=i)

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
                self.dealer.inventory(), e0, self._peg_reserve_balances(),
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
        self.dealer.assert_flow_is_passthrough(
            inv0, e0,
            expected_flow=getattr(self, "_fx_spread_margin_tick", 0.0),
        )
        grope_rates(self, grope_signal)       # NOW move the rates (every flow has settled)
        self.dealer.book_revaluation(e0, self.rates)   # the only source of net-worth change

        inv = self.dealer.inventory()
        e = self.rates.e
        bop_numeraire = self.dealer.net_worth_numeraire(self.rates)
        # v21 external-position gauges (numéraire): NFA_i = −(dealer i-position)/e_i (a
        # positive dealer position is a foreign CLAIM on economy i ⇒ i's net foreign
        # LIABILITY); factor income_i (received) = −(i's interest outflow)/e_i.
        # NFA_i = (i's foreign ASSETS) − (foreigners' CLAIMS on i), in the numéraire.
        # The dealer's position is the claims; every current or former pegging CB's
        # retained FX reserves are a real foreign asset and a matching claim on its
        # anchor.  Each pair cancels in the world sum, so Σ_i NFA_i still equals the
        # negative cumulative dealer revaluation.
        nfa = [-inv[i] / e[i] for i in range(self.n)]
        states = self.__dict__.get("peg_states")
        if states is None:  # pre-B5b checkpoint compatibility
            res = self.reserves()
            if self.n > 1 and res != 0.0:
                anchor = self.peg_anchor
                value = res / e[anchor]
                nfa[self.peg_economy] += value
                nfa[anchor] -= value
        else:
            for pegger, st in sorted(states.items()):
                ledger = self.economies[st.anchor].ledger
                if not ledger.has_account(st.reserve_account_id):
                    continue
                res = ledger.balance(st.reserve_account_id)
                if res == 0.0:
                    continue
                value = res / e[st.anchor]
                nfa[pegger] += value       # the pegger HOLDS the anchor's currency
                nfa[st.anchor] -= value    # ... which is a foreign claim ON the anchor
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
        reserve_balances = self._peg_reserve_balances()
        reserves_by_economy = {
            economy_id: float(reserve_balances.get(economy_id, 0.0))
            for economy_id in range(self.n)
        }
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
                "reserves_by_economy": reserves_by_economy,
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
