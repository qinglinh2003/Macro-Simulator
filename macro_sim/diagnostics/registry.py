"""Metric semantics and observed-series crosswalks for empirical diagnostics.

The simulator emits one record per model day.  A metric registry is deliberately
separate from the record itself: a bare float cannot say whether it is a stock,
flow, rate, or index, and therefore cannot be resampled safely.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Iterable, Mapping


class Frequency(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class TemporalType(StrEnum):
    FLOW = "flow"
    STOCK = "stock"
    RATE = "rate"
    INDEX = "index"


class Aggregation(StrEnum):
    SUM = "sum"
    END = "end"
    MEAN = "mean"
    COMPOUND = "compound"


class Annualization(StrEnum):
    """How the simulator's native value relates to an annual figure."""

    NONE = "none"
    SUM_DAILY_FLOWS = "sum_daily_flows"
    ALREADY_ANNUAL = "already_annual"
    COMPOUND_DAILY_RATE = "compound_daily_rate"
    SIMPLE_DAILY_RATE = "simple_daily_rate"


class TrustStatus(StrEnum):
    VALIDATED = "validated"
    PROXY = "proxy"
    EXPERIMENTAL = "experimental"
    LEGACY_INVALID = "legacy_invalid"


class ValueTransform(StrEnum):
    IDENTITY = "identity"
    PERCENT_TO_RATIO = "percent_to_ratio"
    ANNUAL_PERCENT_TO_DAILY_COMPOUND = "annual_percent_to_daily_compound"
    ANNUAL_PERCENT_TO_DAILY_SIMPLE = "annual_percent_to_daily_simple"
    MONTHLY_INDEX_TO_YOY = "monthly_index_to_yoy"


class ComparisonMode(StrEnum):
    LEVELS = "levels"
    STANDARDIZED = "standardized"
    LOG_CHANGES = "log_changes"
    REBASED_INDEX = "rebased_index"


@dataclass(frozen=True)
class ExternalSeriesCrosswalk:
    """An explicit mapping from an external series to one simulator metric."""

    source: str
    series_id: str
    frequency: Frequency
    unit: str
    transform: ValueTransform = ValueTransform.IDENTITY
    target_annualization: Annualization = Annualization.NONE
    comparison_mode: ComparisonMode = ComparisonMode.LEVELS
    geography: str | None = None
    allowed_seasonal_adjustments: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    # Most empirical comparisons aggregate the record named by the target
    # ``MetricSpec``.  A sequence-derived target can instead name the level series
    # from which its comparable model observation must be constructed.  Keeping
    # this in the crosswalk makes the measurement path visible in artifacts and
    # avoids metric-name conditionals in the CLI.
    simulation_source_metric_id: str | None = None
    simulation_transform: ValueTransform = ValueTransform.IDENTITY

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("crosswalk source must be non-empty")
        if not self.series_id.strip():
            raise ValueError("crosswalk series_id must be non-empty")
        if not self.unit.strip():
            raise ValueError("crosswalk unit must be non-empty")
        if (
            self.simulation_source_metric_id is not None
            and not self.simulation_source_metric_id.strip()
        ):
            raise ValueError("simulation_source_metric_id must be non-empty when set")
        if (
            self.simulation_transform != ValueTransform.IDENTITY
            and self.simulation_source_metric_id is None
        ):
            raise ValueError(
                "a non-identity simulation_transform requires an explicit "
                "simulation_source_metric_id"
            )

    def matches(
        self,
        *,
        source: str,
        series_id: str,
        frequency: Frequency,
        unit: str,
        geography: str,
        seasonal_adjustment: str,
    ) -> bool:
        geography_ok = self.geography is None or self.geography.casefold() == geography.casefold()
        seasonal_ok = (
            not self.allowed_seasonal_adjustments
            or seasonal_adjustment in self.allowed_seasonal_adjustments
        )
        return (
            self.source.casefold() == source.casefold()
            and self.series_id.casefold() == series_id.casefold()
            and self.frequency == frequency
            and self.unit == unit
            and geography_ok
            and seasonal_ok
        )

    def apply(self, value: float) -> float:
        """Apply a pointwise source-unit conversion.

        Sequence-dependent transforms deliberately fail here so a caller cannot
        accidentally label a raw index level as an inflation rate.  Use
        :meth:`apply_series` for those transforms.
        """
        if self.transform == ValueTransform.IDENTITY:
            return value
        if self.transform == ValueTransform.PERCENT_TO_RATIO:
            return value / 100.0
        if self.transform == ValueTransform.ANNUAL_PERCENT_TO_DAILY_COMPOUND:
            if value <= -100.0:
                raise ValueError("an annual percentage rate must be greater than -100%")
            return (1.0 + value / 100.0) ** (1.0 / 365.0) - 1.0
        if self.transform == ValueTransform.ANNUAL_PERCENT_TO_DAILY_SIMPLE:
            return value / 100.0 / 365.0
        if self.transform == ValueTransform.MONTHLY_INDEX_TO_YOY:
            raise ValueError("monthly_index_to_yoy requires apply_series with period labels")
        raise AssertionError(f"unhandled transform {self.transform!r}")

    def apply_series(
        self, period_values: Iterable[tuple[str, float]],
    ) -> tuple[tuple[str, float], ...]:
        """Convert one selected-vintage external series into simulator units.

        The monthly-index transform uses an exact calendar lag.  It never treats
        "the twelfth previous row" as twelve months when observations are missing.
        """

        return self._apply_series_transform(self.transform, period_values)

    def apply_simulation_series(
        self, period_values: Iterable[tuple[str, float]],
    ) -> tuple[tuple[str, float], ...]:
        """Transform aggregated simulator-source values into the target concept."""

        return self._apply_series_transform(
            self.simulation_transform, period_values,
        )

    def _apply_series_transform(
        self,
        transform: ValueTransform,
        period_values: Iterable[tuple[str, float]],
    ) -> tuple[tuple[str, float], ...]:
        values = tuple(period_values)
        periods = [period for period, _value in values]
        if len(periods) != len(set(periods)):
            raise ValueError("series conversion requires one selected vintage per period")
        if transform != ValueTransform.MONTHLY_INDEX_TO_YOY:
            return tuple(
                (period, self._apply_point_transform(transform, value))
                for period, value in values
            )
        if self.frequency != Frequency.MONTHLY:
            raise ValueError("monthly_index_to_yoy requires a monthly source series")

        by_month: dict[int, tuple[str, float]] = {}
        for period, value in values:
            try:
                year_text, month_text = period.split("-")
                year, month = int(year_text), int(month_text)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"monthly_index_to_yoy received invalid monthly period {period!r}"
                ) from exc
            if len(year_text) != 4 or len(month_text) != 2 or not 1 <= month <= 12:
                raise ValueError(
                    f"monthly_index_to_yoy received invalid monthly period {period!r}"
                )
            month_number = year * 12 + month - 1
            by_month[month_number] = (period, float(value))

        converted: list[tuple[str, float]] = []
        for month_number in sorted(by_month):
            period, current = by_month[month_number]
            lagged = by_month.get(month_number - 12)
            if lagged is None:
                continue
            lagged_value = lagged[1]
            if current <= 0.0 or lagged_value <= 0.0:
                raise ValueError("monthly CPI index levels must be strictly positive")
            converted.append((period, current / lagged_value - 1.0))
        return tuple(converted)

    @staticmethod
    def _apply_point_transform(transform: ValueTransform, value: float) -> float:
        if transform == ValueTransform.IDENTITY:
            return value
        if transform == ValueTransform.PERCENT_TO_RATIO:
            return value / 100.0
        if transform == ValueTransform.ANNUAL_PERCENT_TO_DAILY_COMPOUND:
            if value <= -100.0:
                raise ValueError("an annual percentage rate must be greater than -100%")
            return (1.0 + value / 100.0) ** (1.0 / 365.0) - 1.0
        if transform == ValueTransform.ANNUAL_PERCENT_TO_DAILY_SIMPLE:
            return value / 100.0 / 365.0
        if transform == ValueTransform.MONTHLY_INDEX_TO_YOY:
            raise ValueError("monthly_index_to_yoy requires period-labelled series values")
        raise AssertionError(f"unhandled transform {transform!r}")


@dataclass(frozen=True)
class MetricSpec:
    """Machine-readable meaning and measurement status of a simulator field."""

    metric_id: str
    concept: str
    unit: str
    native_frequency: Frequency
    temporal_type: TemporalType
    aggregation: Aggregation
    annualization: Annualization
    trust_status: TrustStatus
    caveats: tuple[str, ...] = ()
    crosswalks: tuple[ExternalSeriesCrosswalk, ...] = ()

    def __post_init__(self) -> None:
        if not self.metric_id.strip() or not self.concept.strip() or not self.unit.strip():
            raise ValueError("metric_id, concept, and unit must be non-empty")
        allowed = {
            TemporalType.FLOW: {Aggregation.SUM},
            TemporalType.STOCK: {Aggregation.END},
            TemporalType.RATE: {Aggregation.MEAN, Aggregation.COMPOUND},
            TemporalType.INDEX: {Aggregation.END, Aggregation.MEAN},
        }
        if self.aggregation not in allowed[self.temporal_type]:
            raise ValueError(
                f"{self.metric_id}: {self.temporal_type} cannot use {self.aggregation} aggregation"
            )
        if self.native_frequency != Frequency.DAILY:
            raise ValueError("the current simulator registry only accepts native daily metrics")
        if self.trust_status != TrustStatus.VALIDATED and not self.caveats:
            raise ValueError(f"{self.metric_id}: non-validated metrics must state a caveat")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetricRegistry:
    """Immutable collection of unique metric specifications."""

    _specs: Mapping[str, MetricSpec] = field(repr=False)

    @classmethod
    def from_specs(cls, specs: Iterable[MetricSpec]) -> "MetricRegistry":
        specs = tuple(specs)
        by_id: dict[str, MetricSpec] = {}
        external_keys: dict[
            tuple[str, str, Frequency, str, str | None, ValueTransform], str
        ] = {}
        for spec in specs:
            if spec.metric_id in by_id:
                raise ValueError(f"duplicate metric_id {spec.metric_id!r}")
            by_id[spec.metric_id] = spec
            for item in spec.crosswalks:
                key = (
                    item.source.casefold(), item.series_id.casefold(), item.frequency,
                    item.unit, item.geography.casefold() if item.geography else None,
                    item.transform,
                )
                previous = external_keys.get(key)
                if previous is not None:
                    raise ValueError(
                        f"external series transform {item.source}/{item.series_id} "
                        f"({item.transform.value}) maps to both {previous!r} and "
                        f"{spec.metric_id!r}"
                    )
                external_keys[key] = spec.metric_id
        for target in specs:
            for crosswalk in target.crosswalks:
                source = crosswalk.simulation_source_metric_id
                if source is not None and source not in by_id:
                    raise ValueError(
                        f"{target.metric_id}: simulation source metric {source!r} "
                        "is not registered"
                    )
        return cls(MappingProxyType(by_id))

    def get(self, metric_id: str) -> MetricSpec:
        try:
            return self._specs[metric_id]
        except KeyError as exc:
            raise KeyError(f"unregistered metric_id {metric_id!r}") from exc

    def __contains__(self, metric_id: object) -> bool:
        return metric_id in self._specs

    def __iter__(self):
        return iter(self._specs.values())

    def resolve_crosswalk(
        self,
        metric_id: str,
        *,
        source: str,
        series_id: str,
        frequency: Frequency,
        unit: str,
        geography: str,
        seasonal_adjustment: str,
    ) -> ExternalSeriesCrosswalk:
        spec = self.get(metric_id)
        matches = [
            item for item in spec.crosswalks
            if item.matches(
                source=source, series_id=series_id, frequency=frequency, unit=unit,
                geography=geography, seasonal_adjustment=seasonal_adjustment,
            )
        ]
        if len(matches) != 1:
            raise ValueError(
                f"{metric_id}: expected one registered crosswalk for "
                f"{source}/{series_id} ({frequency}, {unit}, {geography}), found {len(matches)}"
            )
        return matches[0]

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {spec.metric_id: spec.to_dict() for spec in self}


_SA = ("seasonally_adjusted", "not_seasonally_adjusted")


DEFAULT_REGISTRY = MetricRegistry.from_specs(
    (
        MetricSpec(
            "real_gdp", "Fixed-price domestic value added at basic prices",
            "model_base_period_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "The current account excludes imputed housing and financial services.",
                "Economy-local X/M are observed, but the external product perimeter currently covers consumption goods rather than a full balance of payments.",
                "Production is the scope anchor; expenditure uses an explicit reconciliation residual, while income reports both the legacy cash gap and an output-sales accrual bridge before exposing any unexplained remainder. These reconciliations are not independent validation.",
            ),
            crosswalks=(ExternalSeriesCrosswalk(
                "FRED", "GDPC1", Frequency.QUARTERLY,
                "billions_chained_2017_usd_saar",
                target_annualization=Annualization.SUM_DAILY_FLOWS,
                comparison_mode=ComparisonMode.LOG_CHANGES,
                geography="USA", allowed_seasonal_adjustments=("seasonally_adjusted",),
                caveats=(
                    "Compare growth dynamics only; simulator levels use abstract units and a fixed model-price base.",
                    "FRED GDP has broader service, tax, and external-sector scope than the current simulator account.",
                ),
            ),),
        ),
        MetricSpec(
            "nominal_gdp", "Domestic value added at current basic prices", "model_currency",
            Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "The compatibility headline is basic-price complete only when no producer-side energy-cap compensation is paid; use gdp_nominal_basic_price_corrected_observed when that product subsidy is non-zero.",
                "It excludes productive JG own-account public construction, imputed housing, and financial services; the separately named expanded fields are satellite candidates and do not drive policy.",
                "Economy-local X/M are observed, but the external product perimeter currently covers consumption goods rather than a full balance of payments.",
                "Production is the scope anchor; expenditure uses an explicit reconciliation residual, while income reports both the legacy cash gap and an output-sales accrual bridge before exposing any unexplained remainder. These reconciliations are not independent validation.",
            ),
            crosswalks=(ExternalSeriesCrosswalk(
                "FRED", "GDP", Frequency.QUARTERLY, "billions_usd_saar",
                target_annualization=Annualization.SUM_DAILY_FLOWS,
                comparison_mode=ComparisonMode.LOG_CHANGES, geography="USA",
                allowed_seasonal_adjustments=("seasonally_adjusted",),
                caveats=(
                    "Compare growth dynamics only; simulator levels use abstract currency units.",
                    "FRED GDP is at market prices and has broader service and external-sector scope.",
                ),
            ),),
        ),
        MetricSpec(
            "gdp_nominal_energy_cap_product_subsidy",
            "Settled producer-side energy price-cap compensation",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Classified as a product subsidy because payment is the per-unit gap between the producer's posted price and the capped transaction price; household energy rebates are separate transfers.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_export_product_subsidy_signed",
            "Signed export product subsidy at producer basic prices",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Positive values are subsidies and negative values are export taxes; the same signed bridge is already included in the compatibility production account.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_import_duty_signed",
            "Signed observed import duty or importer subsidy",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Positive values are duties and negative values are importer subsidies settled through the fiscal account.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_vat_observed", "Observed cash VAT on household goods",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "This is the cash-capped amount actually remitted, not an invented accrual for unpaid tax.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_energy_excise_observed",
            "Observed cash excise on energy purchases",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "This is the cash-capped amount actually remitted on energy trades.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_net_product_taxes_observed",
            "Observed product taxes less product subsidies",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Combines observed VAT, energy excise and signed import duty, less the signed export-policy subsidy and energy-cap producer compensation; unmodeled other taxes on production are not inferred.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_basic_price_corrected_observed",
            "Compatibility production GDP plus the observed energy-cap product subsidy",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "An additive observation-only correction; it does not replace nominal_gdp in fiscal or behavioral consumers.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_market_price_observed",
            "Observed nominal GDP at market prices",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Constructed from corrected basic-price GDP plus observed net product taxes; other production taxes and unpaid tax accruals remain outside scope.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_jg_own_account_capital_at_cost",
            "Productive JG own-account public construction valued at wage cost",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS,
            TrustStatus.EXPERIMENTAL,
            caveats=(
                "Non-zero only when positive configured JG productivity creates observed public-capital units; a zero-productivity income floor is not output.",
            ),
        ),
        MetricSpec(
            "gdp_real_jg_own_account_capital_units",
            "Physical public-capital units created by productive JG labor",
            "model_public_capital_units", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS,
            TrustStatus.EXPERIMENTAL,
            caveats=(
                "A physical satellite flow only; no fixed-price JG GDP aggregate is inferred without a committed JG base price.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_jg_income_floor_transfer",
            "Zero-productivity JG income-floor transfer",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=("Explicitly excluded from production and capital formation.",),
        ),
        MetricSpec(
            "gdp_nominal_expanded_production_candidate",
            "Corrected basic-price production plus productive JG own-account construction",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS,
            TrustStatus.EXPERIMENTAL,
            caveats=("Observation-only satellite candidate; it does not drive policy.",),
        ),
        MetricSpec(
            "gdp_nominal_expanded_fixed_capital_formation_candidate",
            "Fixed capital formation including productive JG own-account construction",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS,
            TrustStatus.EXPERIMENTAL,
            caveats=("Adds only cost-valued JG construction backed by public-capital units.",),
        ),
        MetricSpec(
            "gdp_nominal_expanded_public_fixed_capital_formation_candidate",
            "Public fixed capital formation including productive JG own-account construction",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS,
            TrustStatus.EXPERIMENTAL,
            caveats=(
                "Adds only cost-valued JG construction backed by observed public-capital units; zero-productivity income-floor payments are excluded.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_expanded_compensation_candidate",
            "Firm compensation plus productive JG public-works compensation",
            "model_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS,
            TrustStatus.EXPERIMENTAL,
            caveats=("Excludes zero-productivity JG income-floor payments.",),
        ),
        MetricSpec(
            "gdp_nominal_exports", "Economy-local exports at current basic prices",
            "model_currency", Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Directly observed from the Economy external-trade journal, whose current product scope is consumption goods rather than the full balance-of-payments perimeter.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_imports", "Economy-local imports at current basic prices",
            "model_currency", Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Directly observed from the Economy external-trade journal, net of the separately journaled tariff wedge; services and other unmodeled products remain out of scope.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_net_exports", "Economy-local nominal exports less imports",
            "model_currency", Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "X-M is observed rather than inferred from the GDP residual, but inherits the external journal's consumption-goods product scope.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_inventory_change_c_before_export_withdrawal_adjustment",
            "C-goods inventory change before export withdrawal repricing",
            "model_currency", Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Diagnostic counterfactual only; the official nominal inventory line includes the separately journaled export-withdrawal transaction-price adjustment.",
            ),
        ),
        MetricSpec(
            "gdp_nominal_export_inventory_withdrawal_transaction_price_adjustment",
            "Export inventory withdrawal adjustment from contract to current lot prices",
            "model_currency", Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Nominal timing/valuation bridge for opening inventory exported after firms reprice; it does not alter real exports or real inventory volume.",
            ),
        ),
        MetricSpec(
            "gdp_external_export_contract_basic_value",
            "Export contract value at basic prices after export policy settlement",
            "model_currency", Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=("Must equal the realized reserved lots valued at barrier prices.",),
        ),
        MetricSpec(
            "gdp_external_export_barrier_lot_basic_value",
            "Realized export lots valued at coupling-barrier prices",
            "model_currency", Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=("Diagnostic lot journal for the binding foreign contract.",),
        ),
        MetricSpec(
            "gdp_external_export_account_lot_basic_value",
            "Realized export lots valued at current accounting prices",
            "model_currency", Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=("Used to value the nominal withdrawal of exported inventory.",),
        ),
        MetricSpec(
            "gdp_external_export_barrier_lot_contract_gap",
            "Barrier-lot value less export contract basic value",
            "model_currency", Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.VALIDATED,
            caveats=("A hard diagnostic residual expected to be zero each tick.",),
        ),
        MetricSpec(
            "gdp_external_export_lot_repricing_gap",
            "Current-account lot value less barrier-time lot value",
            "model_currency", Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "May be positive or negative; it is a valuation timing bridge, not additional output.",
            ),
        ),
        MetricSpec(
            "gdp_real_exports", "Exports valued at the common C-sector base price",
            "model_base_period_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Physical export volume currently covers consumption goods and is valued at the domestic C-sector base price.",
            ),
        ),
        MetricSpec(
            "gdp_real_imports", "Imports valued at the FXDEALER item base price",
            "model_base_period_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Physical import volume currently covers consumption goods and is valued at the first accepted goods:FXDEALER acquisition price.",
            ),
        ),
        MetricSpec(
            "gdp_real_net_exports", "Fixed-price exports less imports",
            "model_base_period_currency", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=(
                "Real X-M is directly constructed from physical trade journals but remains limited to the modeled consumption-goods external perimeter.",
            ),
        ),
        MetricSpec(
            "cpi_fixed_basket", "Periodically rebased chain-linked Laspeyres household-consumption price index",
            "index_base_1", Frequency.DAILY, TemporalType.INDEX, Aggregation.MEAN,
            Annualization.NONE, TrustStatus.VALIDATED,
            caveats=(
                "The current product journal is pre-VAT/excise, so the index excludes product taxes.",
                "Weights are fixed within each configured rebase window; observed entrants acquire weight only at a chain-linked periodic rebase.",
            ),
            crosswalks=(ExternalSeriesCrosswalk(
                "FRED", "CPIAUCSL", Frequency.MONTHLY, "index_1982_1984_100",
                comparison_mode=ComparisonMode.REBASED_INDEX, geography="USA",
                allowed_seasonal_adjustments=("seasonally_adjusted",),
                caveats=(
                    "Both paths are rebased for comparison; model and U.S. CPI baskets and tax scope differ.",
                ),
            ),),
        ),
        MetricSpec(
            "cpi_fixed_basket_inflation_yoy",
            "Official trailing-365-day CPI change; empirical comparison is exact-month YoY",
            "ratio",
            Frequency.DAILY, TemporalType.RATE, Aggregation.MEAN,
            Annualization.ALREADY_ANNUAL, TrustStatus.VALIDATED,
            caveats=(
                "The official daily record remains unobserved until 365 prior accepted CPI observations exist.",
                "Empirical comparison does not average that daily trailing-365 field; it derives exact same-calendar-month inflation from monthly cpi_fixed_basket levels.",
                "It inherits the chain-linked basket's current exclusion of product taxes.",
            ),
            crosswalks=(ExternalSeriesCrosswalk(
                "FRED", "CPIAUCSL", Frequency.MONTHLY, "index_1982_1984_100",
                transform=ValueTransform.MONTHLY_INDEX_TO_YOY,
                comparison_mode=ComparisonMode.LEVELS, geography="USA",
                allowed_seasonal_adjustments=("seasonally_adjusted",),
                caveats=(
                    "Both model and external 12-month inflation are derived from monthly index levels as CPI_t / CPI_t-12 - 1.",
                    "A month without an exact same-month observation one year earlier is omitted rather than interpolated.",
                ),
                simulation_source_metric_id="cpi_fixed_basket",
                simulation_transform=ValueTransform.MONTHLY_INDEX_TO_YOY,
            ),),
        ),
        MetricSpec(
            "real_output", "Consumption-sector physical output", "model_consumption_units",
            Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=("Excludes capital and energy final output; it is not real GDP.",),
        ),
        MetricSpec(
            "real_output_per_capita", "Consumption-sector physical output per living person",
            "model_consumption_units_per_person", Frequency.DAILY, TemporalType.FLOW,
            Aggregation.SUM, Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=("The numerator is the simulator's consumption-sector output proxy.",),
        ),
        MetricSpec(
            "real_consumption", "Physical consumption goods sold", "model_consumption_units",
            Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.PROXY,
            caveats=("Does not include housing or all energy services.",),
        ),
        MetricSpec(
            "nominal_output", "Legacy nominal consumption-output valuation", "model_currency",
            Frequency.DAILY, TemporalType.FLOW, Aggregation.SUM,
            Annualization.SUM_DAILY_FLOWS, TrustStatus.LEGACY_INVALID,
            caveats=("C-sector-only pseudo-GDP; unsuitable for level calibration.",),
        ),
        MetricSpec(
            "price_index", "Sales-weighted consumption unit value", "model_currency_per_unit",
            # Monthly CPI releases represent the month's price experience; a daily
            # transaction index is therefore averaged, not sampled at month-end.
            Frequency.DAILY, TemporalType.INDEX, Aggregation.MEAN, Annualization.NONE,
            TrustStatus.LEGACY_INVALID,
            caveats=("Composition changes contaminate inflation; this is not a fixed-basket CPI.",),
        ),
        MetricSpec(
            "inflation_yoy", "Trailing-365-day change in the consumption unit value", "ratio",
            Frequency.DAILY, TemporalType.RATE, Aggregation.MEAN,
            Annualization.ALREADY_ANNUAL, TrustStatus.LEGACY_INVALID,
            caveats=("Inherits the composition bias of price_index.",),
        ),
        MetricSpec(
            "person_unemployment_rate", "Unemployed share of model persons in the labor force",
            "ratio", Frequency.DAILY, TemporalType.RATE, Aggregation.MEAN,
            Annualization.NONE, TrustStatus.PROXY,
            caveats=(
                "This demographic bridge subtracts private hires from person labor supply and therefore counts job-guarantee participants as unemployed; it has no survey unemployment crosswalk.",
            ),
        ),
        MetricSpec(
            "labor_u_rate", "Unemployed searching share of the model labor force, with job-guarantee participants separated",
            "ratio", Frequency.DAILY, TemporalType.RATE, Aggregation.MEAN,
            Annualization.NONE, TrustStatus.PROXY,
            caveats=(
                "The model separates job-guarantee participants from unemployed searchers, but its labor-force and activity definitions are not fully harmonized to the household survey.",
            ),
            crosswalks=(ExternalSeriesCrosswalk(
                "FRED", "UNRATE", Frequency.MONTHLY, "percent",
                transform=ValueTransform.PERCENT_TO_RATIO,
                geography="USA", allowed_seasonal_adjustments=("seasonally_adjusted",),
                caveats=(
                    "Use for descriptive comparison only pending a formal bridge from model JG/search states to household-survey employment status.",
                ),
            ),),
        ),
        MetricSpec(
            "unemployment_rate", "Unfilled household labor-supply share", "ratio",
            Frequency.DAILY, TemporalType.RATE, Aggregation.MEAN,
            Annualization.NONE, TrustStatus.PROXY,
            caveats=("Household-agent denominator differs from a person-level unemployment rate.",),
        ),
        MetricSpec(
            "policy_rate", "Central-bank per-day policy rate", "daily_ratio",
            Frequency.DAILY, TemporalType.RATE, Aggregation.MEAN,
            Annualization.SIMPLE_DAILY_RATE, TrustStatus.VALIDATED,
            crosswalks=(ExternalSeriesCrosswalk(
                "FRED", "FEDFUNDS", Frequency.MONTHLY, "annual_percent",
                transform=ValueTransform.ANNUAL_PERCENT_TO_DAILY_SIMPLE,
                geography="USA", allowed_seasonal_adjustments=("not_seasonally_adjusted",),
                caveats=(
                    "FEDFUNDS annual percent is divided by 100 and 365 to match the simulator's simple per-day policy clock; no effective-rate compounding is imposed.",
                ),
            ),),
        ),
        MetricSpec(
            "total_money", "Ledger net financial worth / money stock", "model_currency",
            Frequency.DAILY, TemporalType.STOCK, Aggregation.END, Annualization.NONE,
            TrustStatus.PROXY,
            caveats=("Model ledger aggregate is not harmonized to M1, M2, or a financial-accounts concept.",),
        ),
    )
)
