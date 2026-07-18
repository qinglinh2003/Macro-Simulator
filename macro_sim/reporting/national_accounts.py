"""Optional national accounts and fixed-basket consumer-price measurement.

The legacy dashboard deliberately reports a very small kernel statistic:
``price_index`` is the current C-firm sales unit value and ``nominal_output`` is
that unit value times C-sector production.  Those fields are retained because
policy and a large body of historical experiments consume them.  They are not,
however, a CPI or an economy-wide GDP measure.

This module adds a separate, observation-only account when
``Config.national_accounts_metrics`` is true.  Its conventions are explicit:

* nominal GDP is measured at basic prices from domestic C, K, and E gross
  output less energy used as an intermediate input;
* actual K-good sales are gross fixed capital formation; unsold K output is an
  inventory change, never fixed investment merely because it was produced;
* builder work completed this period is residential fixed-capital formation,
  valued at observed labor cost because the only attached dwelling price mixes
  produced structure with unproduced land/scarcity value; secondary-market
  dwelling transfers are asset swaps and are excluded;
* benefits, pensions, household rebates, interest, and other transfers are not
  output; producer-side per-unit energy-cap compensation is reported separately
  as a product-subsidy bridge;
* the production estimate is the reference because physical production and
  input use are observed most completely.  Expenditure and legacy cash-income
  subtotals retain named reconciliation residuals.  The income account also
  reports a sector-level output-minus-cash-revenue accrual bridge, accrued gross
  operating surplus/income, and only then an unexplained remainder.  Economy-
  local external trade journals supply nominal and physical X/M, so observed net
  exports enter the expenditure estimate instead of being hidden inside its
  residual;
* real GDP values current physical quantities at one fixed reference price per
  sector.  Within the model, C, K, E, and builder output each use a common
  physical unit, so a producer entering after economy-wide inflation inherits
  its sector's original reference price.  Entry and exit can therefore change
  real GDP only through sector quantity, not through an entrant-specific price
  vintage.  A sector that did not produce in the reference observation fixes
  its price when positive production is first observed;
* CPI is a chain-linked Laspeyres index.  The first accepted observation fixes
  item quantities and prices.  A zero-sale incumbent uses its posted price and a
  missing/exited item holds its last observed price within the current basket.
  Accepted household quantities accumulate until the configured periodic
  rebase; the replacement basket keeps only currently live products and is
  anchored to the old basket's accepted index level on the rebase observation.
  Entrants therefore remain zero-weight within a basket but acquire weight after
  observed consumption at a rebase, while exited products cannot survive every
  future basket.  Prices are pre-product-tax because VAT/excise currently settle
  on separate fiscal rails without a product-level household tax journal; the
  emitted scope flag makes that limitation machine-visible.

``preview`` is pure.  All base-period and hold-last state advances in ``commit``
after the Economy has accepted the tick, mirroring the reporting purity contract
in :mod:`macro_sim.reporting.metrics`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable


EPS = 1.0e-12

_SECTOR_CODE = {
    "consumption": "c",
    "capital": "k",
    "energy": "e",
    "housing": "h",
}


@dataclass
class ItemFlow:
    """Quantity/value journal for one differentiated final-consumption item."""

    quantity: float = 0.0
    value: float = 0.0

    def add(self, quantity: float, value: float) -> None:
        self.quantity += max(0.0, float(quantity))
        self.value += max(0.0, float(value))

    @property
    def price(self) -> float | None:
        return self.value / self.quantity if self.quantity > EPS else None


def _add_flow(journal: Dict[str, ItemFlow], key: str, quantity: float, value: float) -> None:
    journal.setdefault(key, ItemFlow()).add(quantity, value)


def _goods_key(seller: str) -> str:
    return f"goods:{seller}"


_IMPORTED_GOODS_KEY = _goods_key("FXDEALER")


def _energy_key(seller: str) -> str:
    return f"energy:{seller}"


@dataclass
class NationalAccountsTracker:
    """Committed price bases plus the current tick's observation journals."""

    household_goods: Dict[str, ItemFlow] = field(default_factory=dict)
    household_energy: Dict[str, ItemFlow] = field(default_factory=dict)
    government_goods: Dict[str, ItemFlow] = field(default_factory=dict)
    energy_intermediate_value: float = 0.0
    energy_intermediate_quantity: float = 0.0
    energy_spr_net_value: float = 0.0
    energy_spr_net_quantity: float = 0.0
    tick_firms: tuple[Any, ...] = ()

    cpi_base_quantities: Dict[str, float] = field(default_factory=dict)
    cpi_base_prices: Dict[str, float] = field(default_factory=dict)
    cpi_last_prices: Dict[str, float] = field(default_factory=dict)
    cpi_chain_anchor: float = 1.0
    cpi_rebase_quantities: Dict[str, float] = field(default_factory=dict)
    cpi_observations_since_rebase: int = 0
    cpi_rebase_count: int = 0
    final_use_base_prices: Dict[str, float] = field(default_factory=dict)
    # Real GDP uses common within-sector physical units.  A firm-level base
    # would give an entrant born after inflation a higher real weight than an
    # otherwise identical incumbent and mechanically manufacture real growth.
    sector_output_base_prices: Dict[str, float] = field(default_factory=dict)
    previous_cpi: float | None = None
    cpi_history: list[float] = field(default_factory=list)

    def open_tick(self, econ: Any) -> None:
        """Open empty journals before any market in a new tick clears."""
        self.household_goods.clear()
        self.household_energy.clear()
        self.government_goods.clear()
        self.energy_intermediate_value = 0.0
        self.energy_intermediate_quantity = 0.0
        self.energy_spr_net_value = 0.0
        self.energy_spr_net_quantity = 0.0
        # Retain object references so production/wages of a firm that exits later
        # in this tick remain visible to the period account.
        self.tick_firms = tuple(econ.firms)

    def observe_goods_trades(self, econ: Any, trades: Iterable[Any]) -> None:
        """Journal household final-consumption trades by product/seller."""
        households = {household.id for household in econ.households}
        for trade in trades:
            if trade.buyer in households:
                value = float(trade.value)
                if _goods_key(str(trade.seller)) == _IMPORTED_GOODS_KEY:
                    # Import offers clear at acquisition prices gross of the signed
                    # tariff wedge.  A negative rate is an importer subsidy with an
                    # explicit fiscal cash leg, not a reason to leave C and M on
                    # different price bases.  Strip either sign so the fixed basket
                    # and basic-price expenditure account use the border value.
                    tariff_rate = float(getattr(econ, "_fx_tariff_rate", 0.0))
                    tariff_multiplier = 1.0 + tariff_rate
                    if not math.isfinite(tariff_multiplier) or tariff_multiplier <= 0.0:
                        raise ValueError(
                            "the accepted import tariff must be finite and satisfy "
                            "1 + rate > 0"
                        )
                    value /= tariff_multiplier
                _add_flow(
                    self.household_goods,
                    _goods_key(str(trade.seller)),
                    trade.qty,
                    value,
                )

    def observe_government_goods(
        self, seller: str, quantity: float, value: float
    ) -> None:
        """Journal actual government C-good procurement (not transfers)."""
        _add_flow(self.government_goods, _goods_key(str(seller)), quantity, value)

    def observe_energy_trades(self, econ: Any, trades: Iterable[Any]) -> None:
        """Split energy trades into final use, intermediate stocks, and the SPR."""
        households = {household.id for household in econ.households}
        firms = {firm.id for firm in econ.c_firms + econ.k_firms}
        fiscal = getattr(econ, "_fiscal", None)
        for trade in trades:
            quantity = max(0.0, float(trade.qty))
            value = max(0.0, float(trade.value))
            if trade.buyer in households:
                _add_flow(
                    self.household_energy,
                    _energy_key(str(trade.seller)),
                    quantity,
                    value,
                )
            elif trade.buyer in firms:
                self.energy_intermediate_quantity += quantity
                self.energy_intermediate_value += value
            elif fiscal is not None and trade.buyer == fiscal:
                self.energy_spr_net_quantity += quantity
                self.energy_spr_net_value += value

            # A fiscal seller is an SPR release: its sale is a withdrawal from
            # strategic inventories.  Transaction value is used because the model
            # does not expose the released lot's historical cost on the trade.
            if fiscal is not None and trade.seller == fiscal:
                self.energy_spr_net_quantity -= quantity
                self.energy_spr_net_value -= value

    def commit(self, econ: Any, record: Dict[str, float]) -> None:
        """Advance bases/hold-last prices exactly once for an accepted record."""
        observations = _household_item_flows(self)
        firms_by_id = _firm_by_id(econ, self)
        if not self.cpi_base_quantities:
            quantities, prices = _bootstrap_cpi_basket(econ, self, observations)
            self.cpi_base_quantities = quantities
            self.cpi_base_prices = prices

        # Hold a price for every observed item, including entrants that are not yet
        # in the active basket.  Their accepted price is then available if they are
        # consumed during the rebase window but have zero sales on the rebase day.
        price_keys = set(self.cpi_base_quantities).union(observations)
        for key in price_keys:
            price = _current_item_price(
                econ, self, key, observations, firms_by_id=firms_by_id
            )
            if price is not None and price > EPS:
                self.cpi_last_prices[key] = price

        for key, flow in observations.items():
            if flow.quantity > EPS:
                self.cpi_rebase_quantities[key] = (
                    self.cpi_rebase_quantities.get(key, 0.0) + flow.quantity
                )
        self.cpi_observations_since_rebase += 1

        for key, flow in observations.items():
            if flow.price is not None and flow.price > EPS:
                self.final_use_base_prices.setdefault(key, float(flow.price))

        firms = _firms_for_period(econ, self)
        for sector in ("c", "k", "e", "h", "other"):
            if sector in self.sector_output_base_prices:
                continue
            price = _sector_reference_price(firms, sector, require_output=True)
            if price is not None and price > EPS:
                self.sector_output_base_prices[sector] = price

        accepted_cpi = float(record.get("cpi_fixed_basket", 1.0))
        self.previous_cpi = accepted_cpi
        self.cpi_history.append(accepted_cpi)
        if len(self.cpi_history) > 365:
            del self.cpi_history[:-365]

        if self.cpi_observations_since_rebase >= econ.cfg.cpi_rebase_interval_days:
            _periodic_cpi_rebase(
                econ,
                self,
                observations,
                accepted_cpi=accepted_cpi,
                firms_by_id=firms_by_id,
            )


def _tracker(econ: Any) -> NationalAccountsTracker:
    tracker = getattr(econ, "_national_accounts", None)
    if tracker is None:
        raise RuntimeError("national-accounts metrics enabled without a tracker")
    return tracker


def _firms_for_period(econ: Any, tracker: NationalAccountsTracker) -> list[Any]:
    """Opening firms plus entrants, de-duplicated without relying on object hashing."""
    result: list[Any] = []
    seen: set[str] = set()
    for firm in tuple(tracker.tick_firms) + tuple(econ.firms):
        if firm.id not in seen:
            seen.add(firm.id)
            result.append(firm)
    return result


def _output_price(firm: Any) -> float:
    """Current basic output valuation; housing is costed, energy uses market price."""
    if getattr(firm, "sells", "") == "housing":
        produced = max(0.0, float(getattr(firm, "produced", 0.0)))
        wagebill = max(0.0, float(getattr(firm, "wagebill", 0.0)))
        if produced > EPS and wagebill > EPS:
            return wagebill / produced
        return max(
            0.0,
            float(getattr(firm, "wage", 0.0))
            / max(EPS, float(getattr(firm, "a", 0.0))),
        )
    if getattr(firm, "sells", "") == "energy" and firm.sales > EPS:
        realized = firm.revenue / firm.sales
        if realized > EPS:
            return float(realized)
    return max(0.0, float(getattr(firm, "price", 0.0)))


def _sector_of(firm: Any) -> str:
    return _SECTOR_CODE.get(getattr(firm, "sells", ""), "other")


def _sector_reference_price(
    firms: Iterable[Any],
    sector: str,
    *,
    require_output: bool = False,
) -> float | None:
    """Return a common price for one sector's homogeneous physical unit.

    Positive current output supplies the economically relevant weights.  A
    transactionless preview may use the mean posted price as a temporary
    fallback, but ``commit`` passes ``require_output=True`` so a permanent base
    is never frozen from a sector that did not produce in that observation.
    """
    selected = [firm for firm in firms if _sector_of(firm) == sector]
    quantity = sum(
        max(0.0, float(getattr(firm, "produced", 0.0))) for firm in selected
    )
    if quantity > EPS:
        value = sum(
            max(0.0, float(getattr(firm, "produced", 0.0))) * _output_price(firm)
            for firm in selected
        )
        if value > EPS:
            return value / quantity
    if require_output:
        return None
    prices = [_output_price(firm) for firm in selected]
    prices = [price for price in prices if price > EPS]
    return sum(prices) / len(prices) if prices else None


def _item_sector(key: str) -> str | None:
    kind, _, _ = key.partition(":")
    if kind == "goods":
        return "c"
    if kind == "energy":
        return "e"
    return None


def _household_item_flows(tracker: NationalAccountsTracker) -> Dict[str, ItemFlow]:
    return {**tracker.household_goods, **tracker.household_energy}


def _firm_by_id(econ: Any, tracker: NationalAccountsTracker) -> Dict[str, Any]:
    return {firm.id: firm for firm in _firms_for_period(econ, tracker)}


def _current_item_price(
    econ: Any,
    tracker: NationalAccountsTracker,
    key: str,
    observations: Dict[str, ItemFlow],
    *,
    firms_by_id: Dict[str, Any] | None = None,
) -> float | None:
    flow = observations.get(key)
    if flow is not None and flow.price is not None and flow.price > EPS:
        return float(flow.price)

    _, _, seller = key.partition(":")
    index = _firm_by_id(econ, tracker) if firms_by_id is None else firms_by_id
    firm = index.get(seller)
    if firm is not None:
        price = _output_price(firm)
        if price > EPS:
            return price

    # Missing imports and exited products use the last accepted price.  On the
    # base observation the base price itself is the only honest hold-last value.
    return tracker.cpi_last_prices.get(key, tracker.cpi_base_prices.get(key))


def _bootstrap_cpi_basket(
    econ: Any,
    tracker: NationalAccountsTracker,
    observations: Dict[str, ItemFlow],
) -> tuple[Dict[str, float], Dict[str, float]]:
    quantities = {
        key: flow.quantity
        for key, flow in observations.items()
        if flow.quantity > EPS and flow.price is not None and flow.price > EPS
    }
    prices = {
        key: float(observations[key].price)
        for key in quantities
    }
    if quantities:
        return quantities, prices

    # A completely transactionless first observation cannot reveal expenditure
    # weights.  Use one physical unit of each incumbent C product, explicitly and
    # deterministically, rather than turning the index into that period's unit value.
    for firm in econ.c_firms:
        price = _output_price(firm)
        if price > EPS:
            key = _goods_key(firm.id)
            quantities[key] = 1.0
            prices[key] = price
    return quantities, prices


def _live_cpi_item_keys(econ: Any) -> set[str]:
    """Products eligible for a new basket at the accepted rebase boundary."""
    keys = {_goods_key(firm.id) for firm in econ.c_firms}
    if getattr(econ.cfg, "energy_household", False):
        keys.update(_energy_key(firm.id) for firm in econ.e_firms)
    return keys


def _periodic_cpi_rebase(
    econ: Any,
    tracker: NationalAccountsTracker,
    observations: Dict[str, ItemFlow],
    *,
    accepted_cpi: float,
    firms_by_id: Dict[str, Any],
) -> bool:
    """Replace the basket without changing its accepted boundary index level.

    Quantities are the household quantities accumulated over the completed
    rebase window.  Filtering them against the live product set removes exited
    products.  If an entirely transactionless window leaves no weights, retain
    live old weights; if none survive, use the deterministic genesis bootstrap.
    A failed rebase remains due and is retried after the next accepted observation.
    """
    eligible = _live_cpi_item_keys(econ)
    # Imports are supplied by the external-sector settlement account rather
    # than a domestic Firm, so they cannot appear in ``_live_cpi_item_keys``.
    # Treat positive consumption anywhere in the completed rebase window as
    # evidence that the aggregate import item is live.  A full zero-import
    # window then removes it, while a one-off import does not remain forever.
    if tracker.cpi_rebase_quantities.get(_IMPORTED_GOODS_KEY, 0.0) > EPS:
        eligible.add(_IMPORTED_GOODS_KEY)
    quantities = {
        key: quantity
        for key, quantity in tracker.cpi_rebase_quantities.items()
        if key in eligible and quantity > EPS
    }
    if not quantities:
        quantities = {
            key: quantity
            for key, quantity in tracker.cpi_base_quantities.items()
            if key in eligible and quantity > EPS
        }
    if not quantities:
        bootstrap_quantities, _ = _bootstrap_cpi_basket(econ, tracker, observations)
        quantities = {
            key: quantity
            for key, quantity in bootstrap_quantities.items()
            if key in eligible and quantity > EPS
        }

    prices: Dict[str, float] = {}
    accepted_quantities: Dict[str, float] = {}
    for key, quantity in quantities.items():
        price = _current_item_price(
            econ, tracker, key, observations, firms_by_id=firms_by_id
        )
        if price is None or price <= EPS:
            continue
        accepted_quantities[key] = quantity
        prices[key] = float(price)

    if not accepted_quantities:
        return False

    tracker.cpi_base_quantities = accepted_quantities
    tracker.cpi_base_prices = prices
    tracker.cpi_chain_anchor = accepted_cpi if accepted_cpi > EPS else 1.0
    tracker.cpi_last_prices.update(prices)
    tracker.cpi_rebase_quantities.clear()
    tracker.cpi_observations_since_rebase = 0
    tracker.cpi_rebase_count += 1
    return True


def _cpi_preview(
    econ: Any, tracker: NationalAccountsTracker
) -> tuple[float, float, Dict[str, float], Dict[str, float]]:
    observations = _household_item_flows(tracker)
    firms_by_id = _firm_by_id(econ, tracker)
    if tracker.cpi_base_quantities:
        quantities = tracker.cpi_base_quantities
        base_prices = tracker.cpi_base_prices
    else:
        quantities, base_prices = _bootstrap_cpi_basket(econ, tracker, observations)

    base_cost = sum(quantities[key] * base_prices[key] for key in quantities)
    current_cost = 0.0
    # v24 portrait finding A2-index: a chained fixed basket is unstable against a single
    # pathological item -- one runaway (or collapsed) price enters the window's ratio and
    # the rebase chain records it PERMANENTLY (Germany x3041 while headline stayed x1.19;
    # residual x70 even after the zombie-pricing root fix). The cap clamps each item's
    # price RELATIVE TO ITS OWN BASE within one chain window; broad-based inflation moves
    # every item together and passes through untouched, repeated genuine trends compound
    # across windows. 0.0 = off = bit-identical.
    link_cap = float(getattr(econ.cfg, "cpi_item_link_cap", 0.0))
    if base_cost > EPS:
        for key, quantity in quantities.items():
            price = _current_item_price(
                econ, tracker, key, observations, firms_by_id=firms_by_id
            )
            if price is None or price <= EPS:
                price = base_prices[key]
            if link_cap > 0.0:
                base_price = base_prices[key]
                if base_price > EPS:
                    price = min(max(price, base_price / link_cap), base_price * link_cap)
            current_cost += quantity * price
        level = tracker.cpi_chain_anchor * current_cost / base_cost
    else:
        level = tracker.cpi_chain_anchor
    previous = tracker.previous_cpi
    inflation = level / previous - 1.0 if previous is not None and previous > EPS else 0.0
    return level, inflation, quantities, base_prices


def _item_base_price(
    tracker: NationalAccountsTracker,
    key: str,
    fallback: float,
    firms_by_id: Dict[str, Any],
) -> float:
    # Imported consumption is its own aggregate item.  Giving it the domestic
    # C-sector base would erase changes in the terms of trade and make real C and
    # real M use different price concepts.  Prefer the item's first accepted
    # acquisition price; the current border unit value is an honest first-period
    # fallback before ``commit`` has fixed that base.
    if key == _IMPORTED_GOODS_KEY:
        if key in tracker.final_use_base_prices:
            return tracker.final_use_base_prices[key]
        if key in tracker.cpi_base_prices:
            return tracker.cpi_base_prices[key]
        return fallback
    _, _, seller = key.partition(":")
    sector = _item_sector(key)
    if sector is not None and sector in tracker.sector_output_base_prices:
        return tracker.sector_output_base_prices[sector]
    if sector is not None:
        current_sector_price = _sector_reference_price(firms_by_id.values(), sector)
        if current_sector_price is not None and current_sector_price > EPS:
            return current_sector_price
    if key in tracker.cpi_base_prices:
        return tracker.cpi_base_prices[key]
    if key in tracker.final_use_base_prices:
        return tracker.final_use_base_prices[key]
    firm = firms_by_id.get(seller)
    if firm is not None:
        return _output_price(firm)
    return fallback


def _flow_real_value(
    tracker: NationalAccountsTracker,
    journal: Dict[str, ItemFlow],
    firms_by_id: Dict[str, Any],
) -> float:
    return sum(
        flow.quantity
        * _item_base_price(tracker, key, flow.price or 0.0, firms_by_id)
        for key, flow in journal.items()
    )


def _energy_base_price(econ: Any, tracker: NationalAccountsTracker, firms: list[Any]) -> float:
    committed = tracker.sector_output_base_prices.get("e")
    if committed is not None and committed > EPS:
        return committed
    current = _sector_reference_price(firms, "e")
    if current is not None and current > EPS:
        return current
    return max(EPS, float(getattr(econ.cfg, "p_efirm0", 1.0)))


def preview(econ: Any) -> Dict[str, float]:
    """Return the optional account without mutating tracker, economy, RNG, or ledger."""
    tracker = _tracker(econ)
    firms = _firms_for_period(econ, tracker)
    firms_by_id = {firm.id: firm for firm in firms}
    c_firms = [firm for firm in firms if getattr(firm, "sells", "") == "consumption"]
    k_firms = [firm for firm in firms if getattr(firm, "sells", "") == "capital"]
    sector_real_prices = {
        sector: tracker.sector_output_base_prices.get(sector)
        or _sector_reference_price(firms, sector)
        or 0.0
        for sector in ("c", "k", "e", "h", "other")
    }

    output_nominal: Dict[str, float] = {
        "c": 0.0, "k": 0.0, "e": 0.0, "h": 0.0, "other": 0.0,
    }
    output_real: Dict[str, float] = {
        "c": 0.0, "k": 0.0, "e": 0.0, "h": 0.0, "other": 0.0,
    }
    cash_revenue_nominal: Dict[str, float] = {
        "c": 0.0, "k": 0.0, "e": 0.0, "h": 0.0, "other": 0.0,
    }
    for firm in firms:
        sector = _sector_of(firm)
        quantity = max(0.0, float(getattr(firm, "produced", 0.0)))
        current_price = _output_price(firm)
        base_price = sector_real_prices[sector] or current_price
        output_nominal[sector] += quantity * current_price
        output_real[sector] += quantity * base_price
        cash_revenue_nominal[sector] += float(getattr(firm, "revenue", 0.0))

    energy_intermediate_nominal = sum(
        max(0.0, float(getattr(firm, "energy_cost_used", 0.0)))
        for firm in c_firms + k_firms
    )
    energy_used = sum(
        max(0.0, float(getattr(firm, "energy_used", 0.0)))
        for firm in c_firms + k_firms
    )
    energy_base_price = _energy_base_price(econ, tracker, firms)
    energy_intermediate_real = energy_used * energy_base_price

    gross_output_nominal = sum(output_nominal.values())
    gross_output_real = sum(output_real.values())
    gdp_nominal_production = gross_output_nominal - energy_intermediate_nominal
    gdp_real_production = gross_output_real - energy_intermediate_real
    gdp_deflator = (
        gdp_nominal_production / gdp_real_production
        if abs(gdp_real_production) > EPS
        else 0.0
    )

    cpi, cpi_inflation, cpi_quantities, _ = _cpi_preview(econ, tracker)
    cpi_yoy_observed = len(tracker.cpi_history) >= 365
    cpi_yoy_base = tracker.cpi_history[0] if cpi_yoy_observed else cpi
    cpi_yoy = cpi / cpi_yoy_base - 1.0 if cpi_yoy_base > EPS else 0.0
    final_items = _household_item_flows(tracker)
    final_quantity = sum(flow.quantity for flow in final_items.values())
    final_value = sum(flow.value for flow in final_items.values())
    unit_value = final_value / final_quantity if final_quantity > EPS else 0.0

    hh_goods_nominal = sum(flow.value for flow in tracker.household_goods.values())
    if not tracker.household_goods:
        hh_goods_nominal = sum(float(household.spent) for household in econ.households)
    hh_energy_nominal = sum(flow.value for flow in tracker.household_energy.values())
    if not tracker.household_energy:
        hh_energy_nominal = float(getattr(econ, "_energy_hh_spend", 0.0))
    hh_final_nominal = hh_goods_nominal + hh_energy_nominal

    hh_goods_real = _flow_real_value(tracker, tracker.household_goods, firms_by_id)
    hh_energy_real = _flow_real_value(tracker, tracker.household_energy, firms_by_id)
    # Only a manually assembled/non-standard observation can lack either journal.
    # Its explicit fallback is deflation by the fixed basket, never a unit value.
    if not tracker.household_goods and hh_goods_nominal > EPS:
        hh_goods_real = hh_goods_nominal / max(EPS, cpi)
    if not tracker.household_energy and hh_energy_nominal > EPS:
        hh_energy_real = hh_energy_nominal / max(EPS, cpi)
    hh_final_real = hh_goods_real + hh_energy_real

    government_nominal = float(getattr(econ, "_gov_consumption", 0.0))
    government_real = _flow_real_value(
        tracker, tracker.government_goods, firms_by_id
    )
    if not tracker.government_goods and abs(government_nominal) > EPS:
        deflator = gdp_deflator if gdp_deflator > EPS else 1.0
        government_real = government_nominal / deflator

    machinery_fixed_nominal = sum(
        max(0.0, firm.sales) * _output_price(firm) for firm in k_firms
    )
    machinery_fixed_real = sum(
        max(0.0, firm.sales)
        * (sector_real_prices["k"] or _output_price(firm))
        for firm in k_firms
    )
    # Builder ``produced`` is work put in place this tick.  It is current
    # residential construction whether it remains WIP, is minted, or is sold;
    # resale of an old dwelling never enters this firm-production flow.
    residential_fixed_nominal = output_nominal["h"]
    residential_fixed_real = output_real["h"]
    fixed_nominal = machinery_fixed_nominal + residential_fixed_nominal
    fixed_real = machinery_fixed_real + residential_fixed_real
    public_fixed_nominal = min(
        machinery_fixed_nominal,
        max(0.0, float(getattr(econ, "_public_investment", 0.0))),
    )
    jg_spending = max(0.0, float(getattr(econ, "_jg_spending", 0.0)))
    jg_capital_units = max(0.0, float(getattr(econ, "_jg_capital_units", 0.0)))
    jg_productivity = max(0.0, float(getattr(econ.cfg, "jg_productivity", 0.0)))
    # The model defines positive-productivity JG labor as own-account public
    # construction: current labor creates the reported public-capital units.  Cost
    # valuation can therefore use the observed wage bill without inventing a sale.
    # At zero productivity the same payment is explicitly an income floor, so it
    # must remain a transfer rather than being manufactured into output.
    jg_public_works_observed = (
        jg_productivity > EPS and jg_capital_units > EPS
    )
    jg_own_account_capital_at_cost = (
        jg_spending if jg_public_works_observed else 0.0
    )
    jg_own_account_capital_units = (
        jg_capital_units if jg_public_works_observed else 0.0
    )
    jg_income_floor_transfer = (
        jg_spending if jg_productivity <= EPS else 0.0
    )
    expanded_fixed_nominal = fixed_nominal + jg_own_account_capital_at_cost
    expanded_public_fixed_nominal = (
        public_fixed_nominal + jg_own_account_capital_at_cost
    )

    inventory_nominal: Dict[str, float] = {"c": 0.0, "k": 0.0, "e": 0.0}
    inventory_real: Dict[str, float] = {"c": 0.0, "k": 0.0, "e": 0.0}
    for firm in firms:
        sector = _sector_of(firm)
        if sector not in inventory_nominal:
            continue
        delta_units = float(firm.produced) - float(firm.sales)
        inventory_nominal[sector] += delta_units * _output_price(firm)
        inventory_real[sector] += delta_units * (
            sector_real_prices[sector] or _output_price(firm)
        )

    # World exports are contracted against opening inventory at the coupling
    # barrier, before current-tick planning can reprice firms.  The raw physical
    # inventory formula above values every withdrawal at the current account price.
    # Replace only the exported withdrawal's current-price value with its actual
    # producer-basic contract value.  This is a nominal transaction-price timing
    # adjustment, not extra output and not a real-volume change.
    inventory_c_before_export_withdrawal_adjustment = inventory_nominal["c"]
    export_inventory_withdrawal_price_adjustment = float(getattr(
        econ,
        "_fx_export_inventory_withdrawal_price_adjustment_external",
        0.0,
    ))
    inventory_nominal["c"] += export_inventory_withdrawal_price_adjustment

    export_contract_basic_value_journal = float(getattr(
        econ, "_fx_export_contract_basic_value_external", 0.0,
    ))
    export_barrier_lot_basic_value = float(getattr(
        econ, "_fx_export_barrier_lot_basic_value_external", 0.0,
    ))
    export_account_lot_basic_value = float(getattr(
        econ, "_fx_export_account_lot_basic_value_external", 0.0,
    ))
    export_barrier_lot_contract_gap = float(getattr(
        econ, "_fx_export_barrier_lot_contract_gap_external", 0.0,
    ))
    export_lot_repricing_gap = float(getattr(
        econ, "_fx_export_lot_repricing_gap_external", 0.0,
    ))

    downstream_inventory_nominal = (
        tracker.energy_intermediate_value - energy_intermediate_nominal
    )
    downstream_inventory_real = (
        tracker.energy_intermediate_quantity - energy_used
    ) * energy_base_price
    spr_inventory_nominal = tracker.energy_spr_net_value
    spr_inventory_real = tracker.energy_spr_net_quantity * energy_base_price
    inventory_total_nominal = (
        sum(inventory_nominal.values())
        + downstream_inventory_nominal
        + spr_inventory_nominal
    )
    inventory_total_real = (
        sum(inventory_real.values())
        + downstream_inventory_real
        + spr_inventory_real
    )

    # The World cash/BoP journal is the price paid by the non-resident.  The
    # production account is deliberately at producer basic prices, so bridge an
    # export subsidy (positive fiscal cost) or export tax (negative cost) back to
    # the amount retained by the producer.  Keep the transaction value observable:
    # it remains the correct value for the current account and dealer settlement.
    exports_transaction_nominal = max(
        0.0, float(getattr(
            econ,
            "_fx_export_transaction_value_external",
            getattr(econ, "_fx_export_value_external", 0.0),
        ))
    )
    export_policy_basic_price_bridge = float(
        getattr(econ, "_export_subsidy_cost_external", 0.0)
    )
    exports_nominal = max(
        0.0,
        exports_transaction_nominal + export_policy_basic_price_bridge,
    )
    imports_nominal = max(
        0.0, float(getattr(
            econ,
            "_fx_import_transaction_value_external",
            getattr(econ, "_fx_import_value_external", 0.0),
        ))
    )
    exports_volume = max(
        0.0, float(getattr(
            econ,
            "_fx_export_shipped_volume_external",
            getattr(econ, "_fx_export_volume_external", 0.0),
        ))
    )
    exports_delivered_volume = max(0.0, float(getattr(
        econ, "_fx_export_delivered_volume_external", exports_volume,
    )))
    iceberg_loss_volume = max(0.0, float(getattr(
        econ,
        "_fx_iceberg_loss_volume_external",
        exports_volume - exports_delivered_volume,
    )))
    imports_volume = max(
        0.0, float(getattr(
            econ,
            "_fx_import_delivered_volume_external",
            getattr(econ, "_fx_import_volume_external", 0.0),
        ))
    )
    export_base_price = sector_real_prices["c"]
    if export_base_price <= EPS and exports_volume > EPS:
        export_base_price = exports_nominal / exports_volume
    import_current_unit_value = (
        imports_nominal / imports_volume if imports_volume > EPS else 0.0
    )
    import_base_price = _item_base_price(
        tracker,
        _IMPORTED_GOODS_KEY,
        import_current_unit_value,
        firms_by_id,
    )
    exports_real = exports_volume * max(0.0, export_base_price)
    imports_real = imports_volume * max(0.0, import_base_price)
    net_exports_nominal = exports_nominal - imports_nominal
    net_exports_real = exports_real - imports_real

    # Satellite valuation bridges.  Keep the compatibility GDP path untouched:
    # fiscal and behavioral consumers still read ``nominal_gdp`` below.  The
    # current production account already includes the signed export-policy bridge,
    # but E output is valued at its capped transaction price because compensation
    # is deliberately not booked as firm revenue.  Add only the actually settled
    # producer compensation to obtain the corrected basic-price observation.
    energy_cap_product_subsidy = max(
        0.0, float(getattr(econ, "_energy_cap_comp", 0.0))
    )
    export_product_subsidy_signed = export_policy_basic_price_bridge
    import_duty_signed = float(
        getattr(econ, "_tariff_revenue_external", 0.0)
    )
    vat_observed = float(getattr(econ, "_tax_consumption", 0.0))
    energy_excise_observed = float(getattr(econ, "_tax_energy", 0.0))
    observed_net_product_taxes = (
        vat_observed
        + energy_excise_observed
        + import_duty_signed
        - export_product_subsidy_signed
        - energy_cap_product_subsidy
    )
    corrected_basic_price_nominal = (
        gdp_nominal_production + energy_cap_product_subsidy
    )
    market_price_nominal = (
        corrected_basic_price_nominal + observed_net_product_taxes
    )
    expanded_production_candidate = (
        corrected_basic_price_nominal + jg_own_account_capital_at_cost
    )

    expenditure_nominal = (
        hh_final_nominal
        + government_nominal
        + fixed_nominal
        + inventory_total_nominal
        + net_exports_nominal
    )
    expenditure_real = (
        hh_final_real
        + government_real
        + fixed_real
        + inventory_total_real
        + net_exports_real
    )
    expenditure_residual_nominal = gdp_nominal_production - expenditure_nominal
    expenditure_residual_real = gdp_real_production - expenditure_real

    compensation = sum(float(getattr(firm, "wagebill", 0.0)) for firm in firms)
    cash_operating_surplus = sum(
        float(getattr(firm, "revenue", 0.0))
        - float(getattr(firm, "wagebill", 0.0))
        - float(getattr(firm, "energy_cost_used", 0.0))
        for firm in firms
    )
    income_observed = compensation + cash_operating_surplus
    income_residual = gdp_nominal_production - income_observed
    # Firm ``revenue`` is a cash/realisation observation, whereas production GDP
    # recognises current output when it is produced.  Report that timing and asset-
    # sale difference explicitly instead of treating it as an unknown income-side
    # gap.  Housing is especially important: current builder WIP raises output
    # before sale, while resale of an existing dwelling raises cash revenue without
    # creating current production.
    output_sales_accrual = {
        sector: output_nominal[sector] - cash_revenue_nominal[sector]
        for sector in output_nominal
    }
    cash_intermediate_nominal = sum(
        float(getattr(firm, "energy_cost_used", 0.0)) for firm in firms
    )
    # Production currently subtracts C/K energy inputs.  Keep any difference from
    # the all-firm cash-income perimeter visible so future sector extensions cannot
    # silently reintroduce an income/production scope mismatch.
    intermediate_scope_adjustment = (
        cash_intermediate_nominal - energy_intermediate_nominal
    )
    income_accrual_bridge = (
        sum(output_sales_accrual.values()) + intermediate_scope_adjustment
    )
    accrued_gross_operating_surplus = (
        cash_operating_surplus + income_accrual_bridge
    )
    accrued_income_observed = compensation + accrued_gross_operating_surplus
    expanded_compensation_candidate = (
        compensation + jg_own_account_capital_at_cost
    )
    unexplained_income_residual = (
        gdp_nominal_production - accrued_income_observed
    )
    raw_spread = max(gdp_nominal_production, expenditure_nominal, income_observed) - min(
        gdp_nominal_production, expenditure_nominal, income_observed
    )
    nominal_scale = max(EPS, abs(gdp_nominal_production))
    real_scale = max(EPS, abs(gdp_real_production))

    transfers_excluded = (
        float(getattr(econ, "_benefit_paid", 0.0))
        + float(getattr(econ, "_energy_subsidy_paid", 0.0))
        + float(getattr(econ, "_family_transfer_total", 0.0))
    )

    current_items = set(final_items)
    current_items.update(_goods_key(firm.id) for firm in econ.c_firms)
    if getattr(econ.cfg, "energy_household", False):
        current_items.update(_energy_key(firm.id) for firm in econ.e_firms)
    entry_items = current_items.difference(cpi_quantities)
    demographic_state = getattr(econ, "demographic_state", None)
    population = float(
        getattr(demographic_state, "alive_count", len(econ.households))
        if demographic_state is not None
        else len(econ.households)
    )
    return {
        "national_accounts_enabled": 1.0,
        "legacy_price_index_is_c_sector_unit_value": 1.0,
        "consumption_unit_value": unit_value,
        "consumption_unit_value_observed": 1.0 if final_quantity > EPS else 0.0,
        "consumption_unit_value_quantity": final_quantity,
        "cpi_fixed_basket": cpi,
        "cpi_fixed_basket_inflation": cpi_inflation,
        "cpi_fixed_basket_inflation_yoy": cpi_yoy,
        "cpi_fixed_basket_inflation_yoy_observed": float(cpi_yoy_observed),
        "cpi_fixed_basket_items": float(len(cpi_quantities)),
        "cpi_fixed_basket_entry_items_excluded": float(len(entry_items)),
        "cpi_fixed_basket_chain_anchor": tracker.cpi_chain_anchor,
        "cpi_fixed_basket_rebase_interval_days": float(
            econ.cfg.cpi_rebase_interval_days
        ),
        "cpi_fixed_basket_rebase_count": float(tracker.cpi_rebase_count),
        "cpi_fixed_basket_observations_since_rebase": float(
            tracker.cpi_observations_since_rebase
        ),
        "cpi_fixed_basket_rebase_due_on_commit": float(
            tracker.cpi_observations_since_rebase + 1
            >= econ.cfg.cpi_rebase_interval_days
        ),
        "cpi_fixed_basket_observations_until_rebase": float(max(
            0,
            econ.cfg.cpi_rebase_interval_days
            - tracker.cpi_observations_since_rebase,
        )),

        "nominal_gdp": gdp_nominal_production,
        "real_gdp": gdp_real_production,
        "nominal_gdp_per_capita": (
            gdp_nominal_production / population if population > EPS else 0.0
        ),
        "real_gdp_per_capita": (
            gdp_real_production / population if population > EPS else 0.0
        ),
        "gdp_deflator": gdp_deflator,
        "gdp_real_uses_common_sector_base_prices": 1.0,
        "gdp_real_base_price_c": sector_real_prices["c"],
        "gdp_real_base_price_k": sector_real_prices["k"],
        "gdp_real_base_price_e": sector_real_prices["e"],
        "gdp_real_base_price_housing": sector_real_prices["h"],
        "gdp_nominal_gross_output_c": output_nominal["c"],
        "gdp_nominal_gross_output_k": output_nominal["k"],
        "gdp_nominal_gross_output_e": output_nominal["e"],
        "gdp_nominal_gross_output_housing": output_nominal["h"],
        "gdp_nominal_gross_output_other": output_nominal["other"],
        "gdp_nominal_gross_output": gross_output_nominal,
        "gdp_nominal_intermediate_energy": energy_intermediate_nominal,
        "gdp_nominal_production": gdp_nominal_production,
        "gdp_nominal_energy_cap_product_subsidy": (
            energy_cap_product_subsidy
        ),
        "gdp_nominal_export_product_subsidy_signed": (
            export_product_subsidy_signed
        ),
        "gdp_nominal_import_duty_signed": import_duty_signed,
        "gdp_nominal_vat_observed": vat_observed,
        "gdp_nominal_energy_excise_observed": energy_excise_observed,
        "gdp_nominal_net_product_taxes_observed": observed_net_product_taxes,
        "gdp_nominal_basic_price_corrected_observed": (
            corrected_basic_price_nominal
        ),
        "gdp_nominal_market_price_observed": market_price_nominal,
        "gdp_jg_public_works_output_observed": float(
            jg_public_works_observed
        ),
        "gdp_nominal_jg_own_account_capital_at_cost": (
            jg_own_account_capital_at_cost
        ),
        "gdp_real_jg_own_account_capital_units": (
            jg_own_account_capital_units
        ),
        "gdp_nominal_jg_income_floor_transfer": jg_income_floor_transfer,
        "gdp_nominal_expanded_production_candidate": (
            expanded_production_candidate
        ),
        "gdp_real_gross_output_c": output_real["c"],
        "gdp_real_gross_output_k": output_real["k"],
        "gdp_real_gross_output_e": output_real["e"],
        "gdp_real_gross_output_housing": output_real["h"],
        "gdp_real_gross_output_other": output_real["other"],
        "gdp_real_gross_output": gross_output_real,
        "gdp_real_intermediate_energy": energy_intermediate_real,
        "gdp_real_production": gdp_real_production,

        "gdp_nominal_household_consumption": hh_final_nominal,
        "gdp_nominal_household_consumption_goods": hh_goods_nominal,
        "gdp_nominal_household_consumption_energy": hh_energy_nominal,
        "gdp_nominal_government_consumption": government_nominal,
        "gdp_nominal_fixed_capital_formation": fixed_nominal,
        "gdp_nominal_machinery_fixed_capital_formation": machinery_fixed_nominal,
        "gdp_nominal_residential_fixed_capital_formation": residential_fixed_nominal,
        "gdp_nominal_private_fixed_capital_formation": fixed_nominal - public_fixed_nominal,
        "gdp_nominal_public_fixed_capital_formation": public_fixed_nominal,
        "gdp_nominal_expanded_fixed_capital_formation_candidate": (
            expanded_fixed_nominal
        ),
        "gdp_nominal_expanded_public_fixed_capital_formation_candidate": (
            expanded_public_fixed_nominal
        ),
        "gdp_nominal_inventory_change_c": inventory_nominal["c"],
        "gdp_nominal_inventory_change_c_before_export_withdrawal_adjustment": (
            inventory_c_before_export_withdrawal_adjustment
        ),
        "gdp_nominal_export_inventory_withdrawal_transaction_price_adjustment": (
            export_inventory_withdrawal_price_adjustment
        ),
        "gdp_nominal_inventory_change_k": inventory_nominal["k"],
        "gdp_nominal_inventory_change_e": inventory_nominal["e"],
        "gdp_nominal_inventory_change_energy_inputs": downstream_inventory_nominal,
        "gdp_nominal_inventory_change_spr": spr_inventory_nominal,
        "gdp_nominal_inventory_change": inventory_total_nominal,
        "gdp_nominal_exports": exports_nominal,
        "gdp_nominal_exports_transaction_value": exports_transaction_nominal,
        "gdp_nominal_export_policy_basic_price_bridge": (
            export_policy_basic_price_bridge
        ),
        "gdp_external_export_contract_basic_value": (
            export_contract_basic_value_journal
        ),
        "gdp_external_export_barrier_lot_basic_value": (
            export_barrier_lot_basic_value
        ),
        "gdp_external_export_account_lot_basic_value": (
            export_account_lot_basic_value
        ),
        "gdp_external_export_barrier_lot_contract_gap": (
            export_barrier_lot_contract_gap
        ),
        "gdp_external_export_lot_repricing_gap": export_lot_repricing_gap,
        "gdp_nominal_imports": imports_nominal,
        "gdp_nominal_net_exports": net_exports_nominal,
        "gdp_nominal_expenditure_observed": expenditure_nominal,
        "gdp_nominal_expenditure_reconciliation_residual": expenditure_residual_nominal,
        "gdp_nominal_expenditure_residual_share": (
            abs(expenditure_residual_nominal) / nominal_scale
        ),
        "gdp_nominal_expenditure_reconciled": expenditure_nominal + expenditure_residual_nominal,

        "gdp_real_household_consumption": hh_final_real,
        "gdp_real_government_consumption": government_real,
        "gdp_real_fixed_capital_formation": fixed_real,
        "gdp_real_machinery_fixed_capital_formation": machinery_fixed_real,
        "gdp_real_residential_fixed_capital_formation": residential_fixed_real,
        "gdp_real_inventory_change_c": inventory_real["c"],
        "gdp_real_inventory_change_k": inventory_real["k"],
        "gdp_real_inventory_change_e": inventory_real["e"],
        "gdp_real_inventory_change_energy_inputs": downstream_inventory_real,
        "gdp_real_inventory_change_spr": spr_inventory_real,
        "gdp_real_inventory_change": inventory_total_real,
        "gdp_real_exports": exports_real,
        "gdp_real_imports": imports_real,
        "gdp_real_net_exports": net_exports_real,
        "gdp_external_export_volume": exports_volume,
        "gdp_external_export_shipped_volume": exports_volume,
        "gdp_external_export_delivered_volume": exports_delivered_volume,
        "gdp_external_iceberg_loss_volume": iceberg_loss_volume,
        "gdp_external_import_volume": imports_volume,
        "gdp_real_export_base_price_c": export_base_price,
        "gdp_real_import_base_price_fxdealer": import_base_price,
        "gdp_real_expenditure_observed": expenditure_real,
        "gdp_real_expenditure_reconciliation_residual": expenditure_residual_real,
        "gdp_real_expenditure_residual_share": (
            abs(expenditure_residual_real) / real_scale
        ),
        "gdp_real_expenditure_reconciled": expenditure_real + expenditure_residual_real,

        "gdp_nominal_compensation_of_employees": compensation,
        "gdp_nominal_expanded_compensation_candidate": (
            expanded_compensation_candidate
        ),
        "gdp_nominal_cash_operating_surplus": cash_operating_surplus,
        "gdp_nominal_income_observed": income_observed,
        "gdp_nominal_income_reconciliation_residual": income_residual,
        "gdp_nominal_income_residual_share": abs(income_residual) / nominal_scale,
        "gdp_nominal_income_reconciled": income_observed + income_residual,
        "gdp_nominal_income_output_sales_accrual_c": output_sales_accrual["c"],
        "gdp_nominal_income_output_sales_accrual_k": output_sales_accrual["k"],
        "gdp_nominal_income_output_sales_accrual_e": output_sales_accrual["e"],
        "gdp_nominal_income_output_sales_accrual_housing": output_sales_accrual["h"],
        "gdp_nominal_income_output_sales_accrual_other": output_sales_accrual["other"],
        "gdp_nominal_income_intermediate_scope_adjustment": (
            intermediate_scope_adjustment
        ),
        "gdp_nominal_income_accrual_bridge": income_accrual_bridge,
        "gdp_nominal_income_accrual_bridge_share": (
            abs(income_accrual_bridge) / nominal_scale
        ),
        "gdp_nominal_accrued_gross_operating_surplus": (
            accrued_gross_operating_surplus
        ),
        "gdp_nominal_income_accrued_observed": accrued_income_observed,
        "gdp_nominal_income_unexplained_residual": unexplained_income_residual,
        "gdp_nominal_income_unexplained_residual_share": (
            abs(unexplained_income_residual) / nominal_scale
        ),
        "gdp_nominal_production_reconciliation_residual": 0.0,
        "gdp_nominal_three_approach_raw_spread": raw_spread,
        "gdp_nominal_three_approach_raw_spread_share": raw_spread / nominal_scale,
        "gdp_reconciliation_is_scope_bridge_not_validation": 1.0,
        "gdp_excluded_transfer_payments": transfers_excluded,
        "gdp_unpriced_jg_compensation": jg_spending,
        # Compatibility flag retained at false: Economy-local journals now put
        # X-M directly into both expenditure estimates.  Any remaining residual
        # is another scope/valuation gap, not an unidentified external balance.
        "gdp_expenditure_residual_includes_unobserved_net_exports": 0.0,
        "gdp_expenditure_includes_observed_net_exports": 1.0,
        # The compatibility headline omits producer-side energy-cap compensation.
        # Mark that limitation rather than silently claiming a complete basic-price
        # basis; the additive corrected field above supplies the explicit bridge.
        "gdp_price_basis_is_basic_prices": float(
            energy_cap_product_subsidy <= EPS
        ),
        # The dwelling resale quote mixes produced structure with unproduced
        # land/scarcity value.  Until those are split, work put in place uses the
        # builder's observed labor cost and assumes zero accrued operating surplus.
        "gdp_housing_construction_uses_factor_cost": 1.0,
        # Rental transfers exist, but the model has no produced flow of landlord
        # services and no owner-occupier imputed rent, so neither is invented here.
        "gdp_scope_excludes_imputed_housing_services": 1.0,
        "gdp_scope_excludes_unpriced_financial_services": 1.0,
        # The model journals VAT/excise on separate fiscal rails after the market
        # trade, so this first account indexes pre-product-tax acquisition prices.
        "cpi_fixed_basket_excludes_product_taxes": 1.0,
    }


def commit(econ: Any, record: Dict[str, float]) -> None:
    """Commit state for the account after the tick record has been accepted."""
    _tracker(econ).commit(econ, record)
