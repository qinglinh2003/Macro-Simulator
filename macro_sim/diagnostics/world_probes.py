"""Dynamic diagnostics for the coupled, open-economy ``World`` layer.

The legacy world tests mostly assert identities assembled from the same reported
gauges.  This module instead snapshots the state on both sides of ``World.step`` and
reconstructs cross-border flows in a common numeraire.  It deliberately reports known
model gaps as :class:`~macro_sim.diagnostics.models.Finding` objects; a failed economic
identity is evidence, not a test-harness exception.

The probes are read-only.  They never call the domestic metrics collector (which has
cross-tick state), and they do not alter the world coupling cadence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from macro_sim.config import Config
from macro_sim.diagnostics.models import Finding
from macro_sim.world import World
from macro_sim.world.capital import capital_interest


_EPS = 1.0e-9


def _matrix(n: int) -> list[list[float]]:
    return [[0.0 for _ in range(n)] for _ in range(n)]


def _max_abs(values: Iterable[float]) -> float:
    values = list(values)
    return max((abs(float(value)) for value in values), default=0.0)


def _reserve_nfa_adjustment(
    n: int, reserve: float, e: list[float], *, peg: bool, anchor: int,
) -> list[float]:
    """Per-country NFA contribution of the pegging CB's real FX reserve asset.

    Economy 0 owns the anchor-currency asset and the anchor economy has the matching
    foreign liability.  The two entries therefore cancel in the closed world's NFA.
    """

    adjustment = [0.0] * n
    if peg and n > 1 and reserve != 0.0:
        value = reserve / max(_EPS, e[anchor])
        adjustment[0] += value
        adjustment[anchor] -= value
    return adjustment


def _nfa_from_positions(
    inventory: list[float], e: list[float], reserve: float, *, peg: bool, anchor: int,
) -> list[float]:
    reserve_adjustment = _reserve_nfa_adjustment(
        len(inventory), reserve, e, peg=peg, anchor=anchor,
    )
    return [
        -inventory[i] / max(_EPS, e[i]) + reserve_adjustment[i]
        for i in range(len(inventory))
    ]


def _arrears_nfa_from_state(world: World, e: list[float]) -> list[float]:
    """Value bilateral external-interest claims at the supplied stock FX vector."""
    n = world.n
    matrix = getattr(world, "_factor_income_arrears_bilateral", _matrix(n))
    unallocated = getattr(world, "_factor_income_arrears_unallocated", [0.0] * n)
    legacy = getattr(world, "_factor_income_arrears", [0.0] * n)
    assets = [
        sum(float(matrix[debtor][creditor]) / max(_EPS, e[debtor]) for debtor in range(n))
        for creditor in range(n)
    ]
    liabilities = [
        max(
            float(legacy[debtor]),
            sum(float(value) for value in matrix[debtor]) + float(unallocated[debtor]),
        )
        / max(_EPS, e[debtor])
        for debtor in range(n)
    ]
    return [assets[i] - liabilities[i] for i in range(n)]


@dataclass(frozen=True)
class WorldDiagnosticResult:
    """Serializable output of a small coupled-world probe run."""

    records: tuple[dict[str, Any], ...]
    checks: dict[str, dict[str, Any]]
    findings: tuple[Finding, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": list(self.records),
            "checks": self.checks,
            "findings": [finding.to_dict() for finding in self.findings],
        }


class WorldProbeCollector:
    """Take immutable pre/post snapshots around each completed ``World.step``."""

    def __init__(self, world: World):
        self.world = world
        self.records: list[dict[str, Any]] = []

    def step(self) -> dict[str, Any]:
        world = self.world
        if not world.couple or world.rates is None:
            raise ValueError("world diagnostics require a coupled World")

        pre_e = list(world.rates.e)
        pre_inventory = list(world.dealer.inventory())
        pre_dealer_nw = world.dealer.net_worth_numeraire(world.rates)
        pre_valuation = float(world.dealer.valuation)
        pre_reserves = float(world.reserves())
        pre_arrears_nfa = _arrears_nfa_from_state(world, pre_e)

        domestic_records = world.step()
        reported = world.world_records[-1]
        post_e = list(reported["e"])
        n = world.n
        sources = list(world._import_source)
        imports_local = [float(value) for value in reported["import_value"]]
        import_delivered_volume = [
            float(value) for value in reported.get(
                "import_delivered_volume",
                reported.get("import_volume", [0.0] * n),
            )
        ]
        export_delivered_volume = [
            float(value) for value in reported.get(
                "export_delivered_volume", [0.0] * n,
            )
        ]
        export_shipped_volume = [
            float(value) for value in reported.get(
                "export_shipped_volume", export_delivered_volume,
            )
        ]
        iceberg_loss_volume = [
            float(value) for value in reported.get(
                "iceberg_loss_volume",
                [
                    export_shipped_volume[i] - export_delivered_volume[i]
                    for i in range(n)
                ],
            )
        ]
        export_contract_basic_value = [
            float(value) for value in reported.get(
                "export_contract_basic_value", [0.0] * n,
            )
        ]
        export_barrier_lot_basic_value = [
            float(value) for value in reported.get(
                "export_barrier_lot_basic_value", [0.0] * n,
            )
        ]
        export_account_lot_basic_value = [
            float(value) for value in reported.get(
                "export_account_lot_basic_value", [0.0] * n,
            )
        ]
        export_barrier_lot_contract_gap = [
            float(value) for value in reported.get(
                "export_barrier_lot_contract_gap", [0.0] * n,
            )
        ]
        export_lot_repricing_gap = [
            float(value) for value in reported.get(
                "export_lot_repricing_gap", [0.0] * n,
            )
        ]
        export_inventory_withdrawal_price_adjustment = [
            float(value) for value in reported.get(
                "export_inventory_withdrawal_price_adjustment", [0.0] * n,
            )
        ]
        exports_local = [float(value) for value in world._last_export_value]
        unbacked_export_volume = [
            float(value) for value in reported.get("unbacked_export_volume", [0.0] * n)
        ]

        # M[i][j] = imports of i sourced from j; X[j][i] is the corresponding
        # realized export.  Values use the PRE-grope rates at which this tick's
        # transaction was settled.  If shipping was short, allocate the realized
        # exporter aggregate pro-rata across its destinations.
        bilateral_m = _matrix(n)
        bilateral_x = _matrix(n)
        expected_exports_local = [0.0] * n
        for importer, source in enumerate(sources):
            if source < 0 or source == importer:
                continue
            value_numeraire = imports_local[importer] / max(_EPS, pre_e[importer])
            bilateral_m[importer][source] = value_numeraire
            expected_exports_local[source] += value_numeraire * pre_e[source]
        for exporter in range(n):
            expected = expected_exports_local[exporter]
            fill = exports_local[exporter] / expected if expected > _EPS else 0.0
            for importer in range(n):
                if sources[importer] == exporter:
                    bilateral_x[exporter][importer] = bilateral_m[importer][exporter] * fill

        import_numeraire = [imports_local[i] / max(_EPS, pre_e[i]) for i in range(n)]
        export_numeraire = [exports_local[i] / max(_EPS, pre_e[i]) for i in range(n)]
        trade_balance = [export_numeraire[i] - import_numeraire[i] for i in range(n)]

        # The authoritative domestic record and the live post-step firm state must
        # describe the same revenue.  A gap means dealer-side exports arrived after
        # domestic P&L/metrics commit (the historical sequencing defect).
        post_c_revenue = [sum(float(f.revenue) for f in econ.c_firms) for econ in world.economies]
        official_c_revenue = [float(rec.get("consumption_spending", 0.0)) for rec in domestic_records]
        late_revenue = [post_c_revenue[i] - official_c_revenue[i] for i in range(n)]

        current_account = [float(value) for value in reported["current_account"]]
        current_account_cash = [
            float(value) for value in reported.get("current_account_cash", current_account)
        ]
        current_account_accrued = [
            float(value) for value in reported.get("current_account_accrued", current_account)
        ]
        nfa = [float(value) for value in reported["nfa"]]
        augmented_nfa = [
            float(value) for value in reported.get("augmented_nfa", nfa)
        ]
        factor_income = [float(value) for value in reported["factor_income"]]
        factor_income_cash = [
            float(value) for value in reported.get("factor_income_cash", factor_income)
        ]
        factor_income_accrued = [
            float(value) for value in reported.get("factor_income_accrued", factor_income)
        ]
        factor_income_arrears = [
            float(value) for value in reported.get("factor_income_arrears", [0.0] * n)
        ]
        factor_income_unpaid_tick = [
            float(value) for value in reported.get("factor_income_unpaid_tick", [0.0] * n)
        ]
        factor_income_arrears_cured_tick = [
            float(value)
            for value in reported.get("factor_income_arrears_cured_tick", [0.0] * n)
        ]
        factor_income_arrears_bilateral = [
            [float(value) for value in row]
            for row in reported.get("factor_income_arrears_bilateral", _matrix(n))
        ]
        factor_income_cash_bilateral = [
            [float(value) for value in row]
            for row in reported.get("factor_income_cash_bilateral", _matrix(n))
        ]
        factor_income_accrued_bilateral = [
            [float(value) for value in row]
            for row in reported.get("factor_income_accrued_bilateral", _matrix(n))
        ]
        factor_income_arrears_unallocated = [
            float(value)
            for value in reported.get("factor_income_arrears_unallocated", [0.0] * n)
        ]
        factor_income_arrears_nfa = [
            float(value)
            for value in reported.get("factor_income_arrears_nfa", [0.0] * n)
        ]
        factor_income_arrears_transaction_change = [
            float(value)
            for value in reported.get(
                "factor_income_arrears_nfa_transaction_change", [0.0] * n,
            )
        ]
        factor_income_arrears_revaluation = [
            float(value)
            for value in reported.get("factor_income_arrears_revaluation", [0.0] * n)
        ]
        remittances = [float(value) for value in reported["remittances"]]
        inventory = [float(value) for value in reported["dealer_inventory"]]
        gate_inventory_raw = world.dealer.last_gate_inventory
        gate_inventory = (
            [float(value) for value in gate_inventory_raw]
            if gate_inventory_raw is not None else []
        )
        dealer_nw = float(reported["bop_numeraire"])
        valuation_stock = float(reported["dealer_valuation"])
        post_reserves = float(world.reserves())

        # Every cross-border transaction settles before the actual RateVector.grope call
        # and therefore at ``pre_e``.  (Peg defence currently happens inside
        # ``grope_rates`` but still before RateVector.grope.)  This makes the total dealer
        # flow and the closing-position revaluation independently identifiable from the
        # immutable before/after snapshots.
        inventory_change = [inventory[i] - pre_inventory[i] for i in range(n)]
        dealer_flow = sum(inventory_change[i] / max(_EPS, pre_e[i]) for i in range(n))
        dealer_gross_flow = sum(abs(inventory_change[i]) / max(_EPS, pre_e[i]) for i in range(n))
        dealer_revaluation = sum(
            inventory[i] * (1.0 / max(_EPS, post_e[i]) - 1.0 / max(_EPS, pre_e[i]))
            for i in range(n)
        )
        dealer_nw_change = dealer_nw - pre_dealer_nw
        dealer_booked_revaluation = valuation_stock - pre_valuation

        # Reconstruct current-account components at the transaction rate.  Household
        # remittance receipts remain a distribution gauge; signed gross current
        # transfers are the external-accounting entry.
        raw_factor_local = [float(value) for value in world._factor_income]
        raw_factor_accrued_local = [
            float(value) for value in getattr(world, "_factor_income_accrued", raw_factor_local)
        ]
        raw_remittance_local = [float(value) for value in world._remittances]
        raw_current_transfer_local = [float(value) for value in world._current_transfers]
        trade_balance_transaction = [
            (exports_local[i] - imports_local[i]) / max(_EPS, pre_e[i]) for i in range(n)
        ]
        factor_income_transaction = [
            -raw_factor_local[i] / max(_EPS, pre_e[i]) for i in range(n)
        ]
        factor_income_accrued_transaction = [
            -raw_factor_accrued_local[i] / max(_EPS, pre_e[i]) for i in range(n)
        ]
        remittance_receipts_transaction = [
            raw_remittance_local[i] / max(_EPS, pre_e[i]) for i in range(n)
        ]
        current_transfers_transaction = [
            raw_current_transfer_local[i] / max(_EPS, pre_e[i]) for i in range(n)
        ]
        current_account_components_transaction = [
            trade_balance_transaction[i]
            + factor_income_transaction[i]
            + current_transfers_transaction[i]
            for i in range(n)
        ]
        current_account_accrued_components_transaction = [
            trade_balance_transaction[i]
            + factor_income_accrued_transaction[i]
            + current_transfers_transaction[i]
            for i in range(n)
        ]

        peg = bool(world.peg)
        anchor = int(world.peg_anchor)
        pre_nfa = _nfa_from_positions(
            pre_inventory, pre_e, pre_reserves, peg=peg, anchor=anchor,
        )
        pre_augmented_nfa = [
            pre_nfa[i] + pre_arrears_nfa[i] for i in range(n)
        ]
        nfa_from_positions = _nfa_from_positions(
            inventory, post_e, post_reserves, peg=peg, anchor=anchor,
        )
        reserve_flow = _reserve_nfa_adjustment(
            n, post_reserves - pre_reserves, pre_e, peg=peg, anchor=anchor,
        )
        reserve_revaluation = [0.0] * n
        if peg and n > 1 and post_reserves != 0.0:
            reserve_revaluation = _reserve_nfa_adjustment(
                n, post_reserves, post_e, peg=peg, anchor=anchor,
            )
            reserve_at_old_rate = _reserve_nfa_adjustment(
                n, post_reserves, pre_e, peg=peg, anchor=anchor,
            )
            reserve_revaluation = [
                reserve_revaluation[i] - reserve_at_old_rate[i] for i in range(n)
            ]
        nfa_transaction_flow = [
            -inventory_change[i] / max(_EPS, pre_e[i]) + reserve_flow[i]
            for i in range(n)
        ]
        # Revalue the CLOSING position.  Using the opening position manufactures a
        # residual whenever the tick both trades and changes the exchange rate.
        nfa_revaluation = [
            -inventory[i]
            * (1.0 / max(_EPS, post_e[i]) - 1.0 / max(_EPS, pre_e[i]))
            + reserve_revaluation[i]
            for i in range(n)
        ]

        record = {
            "t": int(reported["t"]),
            "pre_e": pre_e,
            "e": post_e,
            "import_source": sources,
            "bilateral_imports_numeraire": bilateral_m,
            "bilateral_exports_numeraire": bilateral_x,
            "imports_local": imports_local,
            # Compatibility alias plus explicit physical stages.  Imports are
            # destination-delivered; exports are source-shipped and may exceed
            # their delivered counterpart by the iceberg loss.
            "import_volume": import_delivered_volume,
            "import_delivered_volume": import_delivered_volume,
            "export_delivered_volume": export_delivered_volume,
            "export_shipped_volume": export_shipped_volume,
            "iceberg_loss_volume": iceberg_loss_volume,
            "export_contract_basic_value": export_contract_basic_value,
            "export_barrier_lot_basic_value": export_barrier_lot_basic_value,
            "export_account_lot_basic_value": export_account_lot_basic_value,
            "export_barrier_lot_contract_gap": export_barrier_lot_contract_gap,
            "export_lot_repricing_gap": export_lot_repricing_gap,
            "export_inventory_withdrawal_price_adjustment": (
                export_inventory_withdrawal_price_adjustment
            ),
            "exports_local": exports_local,
            "unbacked_export_volume": unbacked_export_volume,
            "imports_numeraire": import_numeraire,
            "exports_numeraire": export_numeraire,
            "trade_balance_numeraire": trade_balance,
            "current_account": current_account,
            "current_account_cash": current_account_cash,
            "current_account_accrued": current_account_accrued,
            "nfa": nfa,
            "augmented_nfa": augmented_nfa,
            "factor_income": factor_income,
            "factor_income_cash": factor_income_cash,
            "factor_income_accrued": factor_income_accrued,
            "factor_income_arrears": factor_income_arrears,
            "factor_income_unpaid_tick": factor_income_unpaid_tick,
            "factor_income_arrears_cured_tick": factor_income_arrears_cured_tick,
            "factor_income_arrears_bilateral": factor_income_arrears_bilateral,
            "factor_income_cash_bilateral": factor_income_cash_bilateral,
            "factor_income_accrued_bilateral": factor_income_accrued_bilateral,
            "factor_income_arrears_unallocated": factor_income_arrears_unallocated,
            "factor_income_arrears_nfa": factor_income_arrears_nfa,
            "factor_income_arrears_nfa_transaction_change": (
                factor_income_arrears_transaction_change
            ),
            "factor_income_arrears_revaluation": factor_income_arrears_revaluation,
            "remittances": remittances,
            "dealer_inventory": inventory,
            "dealer_gate_inventory": gate_inventory,
            "dealer_net_worth_numeraire": dealer_nw,
            "dealer_net_worth_change": dealer_nw_change,
            "dealer_valuation_stock": valuation_stock,
            "dealer_valuation_change": dealer_booked_revaluation,
            "dealer_flow_numeraire": dealer_flow,
            "dealer_gross_flow_numeraire": dealer_gross_flow,
            "dealer_revaluation_numeraire": dealer_revaluation,
            "dealer_flow_revaluation_residual": (
                dealer_nw_change - dealer_flow - dealer_revaluation
            ),
            "dealer_revaluation_booking_residual": (
                dealer_booked_revaluation - dealer_revaluation
            ),
            "pre_dealer_inventory": pre_inventory,
            "pre_dealer_net_worth_numeraire": pre_dealer_nw,
            "pre_dealer_valuation_stock": pre_valuation,
            "pre_reserves": pre_reserves,
            "reserves": post_reserves,
            "peg": peg,
            "peg_anchor": anchor,
            "pre_nfa": pre_nfa,
            "pre_arrears_nfa": pre_arrears_nfa,
            "pre_augmented_nfa": pre_augmented_nfa,
            "nfa_from_positions": nfa_from_positions,
            "nfa_transaction_flow": nfa_transaction_flow,
            "nfa_revaluation": nfa_revaluation,
            "trade_balance_transaction_rate": trade_balance_transaction,
            "factor_income_transaction_rate": factor_income_transaction,
            "factor_income_accrued_transaction_rate": factor_income_accrued_transaction,
            "remittance_receipts_transaction_rate": remittance_receipts_transaction,
            "current_transfers_transaction_rate": current_transfers_transaction,
            "current_account_components_transaction_rate": current_account_components_transaction,
            "current_account_accrued_components_transaction_rate": (
                current_account_accrued_components_transaction
            ),
            "official_c_revenue": official_c_revenue,
            "post_world_c_revenue": post_c_revenue,
            "late_settlement_revenue": late_revenue,
            "periods_per_year": float(world.periods_per_year),
        }
        self.records.append(record)
        return record

    def run(self, ticks: int) -> WorldDiagnosticResult:
        for _ in range(ticks):
            self.step()
        return diagnose_world(self.world, self.records)


def build_small_world(
    *,
    n: int = 2,
    ticks: int = 24,
    population: int = 40,
    consumption_strata: bool = False,
    daily: bool = False,
    base_seed: int = 9,
    peg: bool = False,
    peg_reserves0: float = 100.0,
    peg_reserve_scale: float = 0.02,
    fx_friction: float = 0.03,
) -> World:
    """Build a fast heterogeneous world suitable for a diagnostic smoke run.

    ``daily=True`` selects the v13 one-calendar-day preset.  World keeps
    ``periods_per_year`` as reported metadata, but policy and loan rates are per-tick and
    cross-border factor income must therefore apply the live rate exactly once.
    """

    if n < 2:
        raise ValueError("an open-economy diagnostic needs at least two economies")
    factory = Config.v13 if daily else Config.v124
    configs: list[Config] = []
    for i in range(n):
        # Heterogeneous productivity and policy rates generate identifiable trade,
        # capital and migration flows without a large agent population.
        productivity = 0.7 + 0.6 * i / max(1, n - 1)
        annualish_rate = 0.02 + 0.04 * i / max(1, n - 1)
        overrides: dict[str, Any] = {
            "n_firms_c": 8,
            "n_firms_k": 4,
            "n_households": population,
            "n_ticks": ticks,
            "seed": i,
            "a": productivity,
            "consumption_strata": consumption_strata,
        }
        if not daily:
            # Config rates are per tick.  Use an explicit v13-style daily rate even
            # though the small diagnostic fixture keeps v124's lighter structure.
            overrides["r_interest"] = annualish_rate / 365.0
        configs.append(factory(**overrides))
    return World(
        configs,
        base_seed=base_seed,
        trade=True,
        capital=True,
        migration=True,
        capital_mobility=1.0,
        capital_adjust=0.2,
        migration_rate=0.03,
        remittance_share=0.2,
        peg=peg,
        peg_reserves0=peg_reserves0,
        peg_reserve_scale=peg_reserve_scale,
        fx_friction=fx_friction,
    )


def run_small_world_diagnostic(**kwargs: Any) -> WorldDiagnosticResult:
    """Convenience entry point used by tests and interactive root-cause work."""

    ticks = int(kwargs.pop("ticks", 24))
    world = build_small_world(ticks=ticks, **kwargs)
    return WorldProbeCollector(world).run(ticks)


def _check(passed: bool, **evidence: Any) -> dict[str, Any]:
    return {"passed": bool(passed), **evidence}


def diagnose_world(world: World, records: Iterable[dict[str, Any]]) -> WorldDiagnosticResult:
    """Evaluate external-sector identities and return structured root-cause leads."""

    rows = tuple(records)
    findings: list[Finding] = []
    checks: dict[str, dict[str, Any]] = {}
    n = world.n

    gross_trade = sum(sum(row["imports_numeraire"]) for row in rows)
    unbacked_exports = sum(sum(row["unbacked_export_volume"]) for row in rows)
    gross_physical_exports = sum(
        sum(row.get("export_shipped_volume", row["import_volume"])) for row in rows
    )
    physical_tol = max(1.0e-9, gross_physical_exports * 1.0e-9)
    checks["export_physical_backing"] = _check(
        unbacked_exports <= physical_tol,
        cumulative_unbacked_export_volume=unbacked_exports,
        cumulative_realized_export_volume=gross_physical_exports,
        tolerance=physical_tol,
        mechanism="last exporter fills residual without inventory or production input",
    )
    if rows and unbacked_exports > physical_tol:
        findings.append(Finding(
            issue_id="world.exports_unbacked_by_goods",
            severity="critical",
            confidence="confirmed",
            category="real_accounting",
            claim="Some exports are booked as sales and revenue without inventory or current production backing.",
            evidence=checks["export_physical_backing"],
            suspected_mechanisms=("_ship_exports assigns the final firm the entire remaining order",),
            recommendation=(
                "Reserve and allocate source-country inventory at the coupling barrier, "
                "or synchronously produce exports with explicit labor/capital inputs."
            ),
            detector="world_export_physical_stock_flow",
        ))
    iceberg_identity_residuals: list[float] = []
    delivered_counterpart_residuals: list[float] = []
    gross_delivered = 0.0
    gross_iceberg_loss = 0.0
    for row in rows:
        imports_delivered = row.get(
            "import_delivered_volume", row.get("import_volume", [0.0] * n),
        )
        exports_delivered = row.get("export_delivered_volume", imports_delivered)
        exports_shipped = row.get("export_shipped_volume", exports_delivered)
        iceberg_loss = row.get(
            "iceberg_loss_volume",
            [
                float(exports_shipped[i]) - float(exports_delivered[i])
                for i in range(n)
            ],
        )
        gross_delivered += sum(float(value) for value in imports_delivered)
        gross_iceberg_loss += sum(float(value) for value in iceberg_loss)
        iceberg_identity_residuals.extend(
            float(exports_shipped[i])
            - float(exports_delivered[i])
            - float(iceberg_loss[i])
            for i in range(n)
        )
        delivered_counterpart_residuals.append(
            sum(float(value) for value in exports_delivered)
            - sum(float(value) for value in imports_delivered)
        )
    iceberg_tol = max(
        1.0e-9,
        gross_physical_exports * 1.0e-9,
        gross_delivered * 1.0e-9,
    )
    max_iceberg_residual = max(
        (abs(value) for value in iceberg_identity_residuals), default=0.0,
    )
    max_delivered_residual = max(
        (abs(value) for value in delivered_counterpart_residuals), default=0.0,
    )
    checks["iceberg_physical_identity"] = _check(
        max(max_iceberg_residual, max_delivered_residual) <= iceberg_tol,
        cumulative_delivered_import_volume=gross_delivered,
        cumulative_shipped_export_volume=gross_physical_exports,
        cumulative_iceberg_loss_volume=gross_iceberg_loss,
        max_shipped_delivered_loss_residual=max_iceberg_residual,
        max_export_import_delivered_counterpart_residual=max_delivered_residual,
        tolerance=iceberg_tol,
    )
    if rows and not checks["iceberg_physical_identity"]["passed"]:
        findings.append(Finding(
            issue_id="world.iceberg_physical_identity_broken",
            severity="critical",
            confidence="confirmed",
            category="real_accounting",
            claim=(
                "Origin shipments do not reconcile to destination deliveries plus "
                "iceberg loss."
            ),
            evidence=checks["iceberg_physical_identity"],
            suspected_mechanisms=(
                "trade settlement mixed delivered and source-shipped quantity units",
            ),
            recommendation=(
                "Reserve and settle source units at (1 + friction) times delivered "
                "units and journal the melted quantity explicitly."
            ),
            detector="world_iceberg_physical_identity",
        ))

    contract_gap_values: list[float] = []
    contract_gap_residuals: list[float] = []
    repricing_gap_residuals: list[float] = []
    withdrawal_adjustment_residuals: list[float] = []
    valuation_decomposition_residuals: list[float] = []
    valuation_scale = 0.0
    for row in rows:
        contract = row.get("export_contract_basic_value", [0.0] * n)
        barrier = row.get("export_barrier_lot_basic_value", [0.0] * n)
        account = row.get("export_account_lot_basic_value", [0.0] * n)
        contract_gap = row.get("export_barrier_lot_contract_gap", [0.0] * n)
        repricing_gap = row.get("export_lot_repricing_gap", [0.0] * n)
        adjustment = row.get(
            "export_inventory_withdrawal_price_adjustment", [0.0] * n,
        )
        for i in range(n):
            c = float(contract[i])
            b = float(barrier[i])
            a = float(account[i])
            g_contract = float(contract_gap[i])
            g_repricing = float(repricing_gap[i])
            g_adjustment = float(adjustment[i])
            valuation_scale += abs(c) + abs(b) + abs(a)
            contract_gap_values.append(g_contract)
            contract_gap_residuals.append((b - c) - g_contract)
            repricing_gap_residuals.append((a - b) - g_repricing)
            withdrawal_adjustment_residuals.append((a - c) - g_adjustment)
            valuation_decomposition_residuals.append(
                g_adjustment - g_contract - g_repricing
            )
    valuation_tol = max(1.0e-9, valuation_scale * 1.0e-9)
    valuation_maxima = {
        "max_abs_barrier_lot_contract_gap": _max_abs(contract_gap_values),
        "max_abs_contract_gap_journal_residual": _max_abs(contract_gap_residuals),
        "max_abs_repricing_gap_journal_residual": _max_abs(repricing_gap_residuals),
        "max_abs_withdrawal_adjustment_journal_residual": _max_abs(
            withdrawal_adjustment_residuals
        ),
        "max_abs_valuation_decomposition_residual": _max_abs(
            valuation_decomposition_residuals
        ),
    }
    checks["export_lot_contract_valuation"] = _check(
        max(valuation_maxima.values(), default=0.0) <= valuation_tol,
        cumulative_abs_valuation_scale=valuation_scale,
        tolerance=valuation_tol,
        **valuation_maxima,
    )
    if rows and not checks["export_lot_contract_valuation"]["passed"]:
        findings.append(Finding(
            issue_id="world.export_lot_contract_valuation_broken",
            severity="critical",
            confidence="confirmed",
            category="nominal_accounting",
            claim=(
                "Export contract value is not backed by the reserved barrier-price "
                "lots, or its inventory-withdrawal valuation journals do not decompose."
            ),
            evidence=checks["export_lot_contract_valuation"],
            suspected_mechanisms=(
                "stale aggregate prices entered the binding foreign quote",
                "partial fills consumed a non-proportional subset of heterogeneous lots",
                "barrier-to-account repricing was omitted or double counted",
            ),
            recommendation=(
                "Quote the weighted reserved-lot barrier value, apply one fill fraction "
                "to every lot, and journal account-lot minus contract-basic value as "
                "the nominal inventory-withdrawal adjustment."
            ),
            detector="world_export_lot_contract_valuation",
        ))
    mirror_residuals: list[float] = []
    trade_sum_residuals: list[float] = []
    for row in rows:
        for importer in range(n):
            for exporter in range(n):
                mirror_residuals.append(
                    row["bilateral_imports_numeraire"][importer][exporter]
                    - row["bilateral_exports_numeraire"][exporter][importer]
                )
        trade_sum_residuals.append(sum(row["trade_balance_transaction_rate"]))
    mirror_max = _max_abs(mirror_residuals)
    tb_sum_max = _max_abs(trade_sum_residuals)
    max_tick_trade = max(
        (sum(abs(value) for value in row["imports_numeraire"])
         + sum(abs(value) for value in row["exports_numeraire"]) for row in rows),
        default=0.0,
    )
    trade_tol = max(1.0e-8, max_tick_trade * 1.0e-8)
    checks["bilateral_trade_mirror"] = _check(
        mirror_max <= trade_tol,
        max_abs_residual=mirror_max,
        gross_trade_numeraire=gross_trade,
        evidence_status="derived_allocation_not_independent_journal",
    )
    checks["trade_balance_zero_sum"] = _check(
        tb_sum_max <= trade_tol,
        max_abs_residual=tb_sum_max,
    )
    if mirror_max > trade_tol or tb_sum_max > trade_tol:
        findings.append(Finding(
            issue_id="world.bilateral_trade_not_mirrored",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="Realized bilateral exports do not mirror counterpart imports in one numeraire.",
            evidence={"mirror_max": mirror_max, "tb_sum_max": tb_sum_max, "gross_trade": gross_trade},
            suspected_mechanisms=("source allocation", "FX conversion cadence", "export short shipment"),
            recommendation="Book each bilateral shipment once, then derive both countries' X/M entries from it.",
            detector="world_flow_matrix",
        ))

    # Recompute the hard-gate flow over the WHOLE tick.  The outer snapshot independently
    # verifies that trade, income, transfers, and peg defence all stayed inside the native
    # enforcement perimeter.
    dealer_flows = [row["dealer_flow_numeraire"] for row in rows]
    dealer_flow_scale = max(
        (row["dealer_gross_flow_numeraire"] for row in rows), default=0.0,
    )
    dealer_flow_tol = max(1.0e-8, dealer_flow_scale * 1.0e-8)
    dealer_flow_max = _max_abs(dealer_flows)
    checks["dealer_full_tick_passthrough"] = _check(
        dealer_flow_max <= dealer_flow_tol,
        max_abs_flow=dealer_flow_max,
        tolerance=dealer_flow_tol,
        gross_flow_scale=dealer_flow_scale,
        includes_peg_reserve_transactions=True,
    )
    if rows and dealer_flow_max > dealer_flow_tol:
        findings.append(Finding(
            issue_id="world.dealer_flow_not_passthrough",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="The dealer's full-tick transaction flow creates or destroys numeraire value.",
            evidence=checks["dealer_full_tick_passthrough"],
            suspected_mechanisms=("unpaired cross-border payload", "peg transaction after native gate"),
            recommendation="Gate the final post-transaction dealer position before changing exchange rates.",
            detector="world_full_tick_passthrough",
        ))

    decomposition_residuals = [row["dealer_flow_revaluation_residual"] for row in rows]
    booking_residuals = [row["dealer_revaluation_booking_residual"] for row in rows]
    dealer_decomp_scale = max(
        (abs(row["dealer_net_worth_change"])
         + abs(row["dealer_flow_numeraire"])
         + abs(row["dealer_revaluation_numeraire"]) for row in rows),
        default=0.0,
    )
    dealer_decomp_tol = max(1.0e-9, dealer_decomp_scale * 1.0e-8)
    dealer_decomp_max = max(_max_abs(decomposition_residuals), _max_abs(booking_residuals))
    checks["dealer_flow_valuation_separation"] = _check(
        dealer_decomp_max <= dealer_decomp_tol,
        status="identified",
        max_net_worth_decomposition_residual=_max_abs(decomposition_residuals),
        max_revaluation_booking_residual=_max_abs(booking_residuals),
        max_abs_transaction_flow=dealer_flow_max,
        max_abs_revaluation=_max_abs(row["dealer_revaluation_numeraire"] for row in rows),
        tolerance=dealer_decomp_tol,
        identity="delta_nw = transaction_flow + closing_position_revaluation",
    )
    if rows and dealer_decomp_max > dealer_decomp_tol:
        findings.append(Finding(
            issue_id="world.dealer_flow_revaluation_not_reconciled",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="Dealer net-worth changes do not reconcile to separately measured flow and FX revaluation.",
            evidence=checks["dealer_flow_valuation_separation"],
            recommendation=(
                "Snapshot final transaction positions before groping and book only "
                "their price revaluation."
            ),
            detector="world_dealer_flow_revaluation_bridge",
        ))

    # The reported dealer stock, per-country NFA (including real FX reserves), and the
    # cumulative valuation account form three independent public representations of the
    # same external position.  Check both country allocation and the closed-world total.
    dealer_stock_residuals = [
        row["dealer_net_worth_numeraire"]
        - sum(row["dealer_inventory"][i] / max(_EPS, row["e"][i]) for i in range(n))
        for row in rows
    ]
    nfa_position_residuals = [
        row["nfa"][i] - row["nfa_from_positions"][i]
        for row in rows for i in range(n)
    ]
    world_position_residuals = [
        sum(row["nfa"]) + row["dealer_valuation_stock"] for row in rows
    ]
    stock_scale = max(
        (sum(abs(value) for value in row["nfa"])
         + abs(row["dealer_net_worth_numeraire"]) for row in rows),
        default=0.0,
    )
    stock_tol = max(1.0e-8, stock_scale * 1.0e-8)
    stock_max = max(
        _max_abs(dealer_stock_residuals),
        _max_abs(nfa_position_residuals),
        _max_abs(world_position_residuals),
    )
    checks["external_position_stock_identity"] = _check(
        stock_max <= stock_tol,
        max_dealer_stock_residual=_max_abs(dealer_stock_residuals),
        max_country_nfa_position_residual=_max_abs(nfa_position_residuals),
        max_world_nfa_plus_cumulative_revaluation=_max_abs(world_position_residuals),
        max_fx_reserves=max((row["reserves"] for row in rows), default=0.0),
        reserve_change=_max_abs(row["reserves"] - row["pre_reserves"] for row in rows),
        tolerance=stock_tol,
    )
    if rows and stock_max > stock_tol:
        findings.append(Finding(
            issue_id="world.external_position_stock_identity",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="Dealer positions, real FX reserves, NFA, and cumulative revaluation do not describe one stock.",
            evidence=checks["external_position_stock_identity"],
            recommendation="Derive public NFA and dealer net worth from the same currency-position ledger.",
            detector="world_external_position_stock",
        ))

    # The dealer records the exact position seen by its hard gate.  Equality with the
    # final pre-rate position proves that peg-reserve swaps and every other cross-border
    # cash leg were inside the enforcement perimeter.
    reserve_transaction_ticks = sum(
        abs(row["reserves"] - row["pre_reserves"]) > 1.0e-10 for row in rows
    )
    post_gate_gaps = [
        row["dealer_inventory"][i] - row["dealer_gate_inventory"][i]
        for row in rows if len(row["dealer_gate_inventory"]) == n for i in range(n)
    ]
    peg_gate_covers_flow = not rows or (
        bool(post_gate_gaps) and _max_abs(post_gate_gaps) <= 1.0e-10
    )
    checks["peg_reserve_flow_gate_order"] = _check(
        peg_gate_covers_flow,
        reserve_transaction_ticks=reserve_transaction_ticks,
        max_reserve_change=_max_abs(
            row["reserves"] - row["pre_reserves"] for row in rows
        ),
        full_tick_flow_residual=dealer_flow_max,
        max_post_gate_inventory_change=_max_abs(post_gate_gaps),
        native_order="peg_defense -> assert_flow_is_passthrough -> RateVector.grope",
    )
    if not peg_gate_covers_flow:
        findings.append(Finding(
            issue_id="world.peg_reserve_flow_after_bop_gate",
            severity="critical",
            confidence="confirmed",
            category="coupling_order",
            claim="Real peg-reserve FX swaps execute after the native BoP hard gate.",
            evidence=checks["peg_reserve_flow_gate_order"],
            suspected_mechanisms=("peg_defense is called from grope_rates after passthrough assertion",),
            requested_probes=("post_peg_pre_rate_position_snapshot",),
            recommendation=(
                "Execute peg defence before the passthrough assertion, then grope rates "
                "only after the final transaction position is gated."
            ),
            detector="world_peg_gate_perimeter",
        ))

    # Factor income is now a real, conserving payer-to-recipient flow.  Validate it at
    # the rate at which it settled, rather than repeating the stale claim that it is a
    # gauge-only item.
    factor_sums = [sum(row["factor_income_transaction_rate"]) for row in rows]
    factor_scale = max(
        (sum(abs(value) for value in row["factor_income_transaction_rate"]) for row in rows),
        default=0.0,
    )
    factor_tol = max(1.0e-9, factor_scale * 1.0e-8)
    checks["factor_income_counterparty"] = _check(
        _max_abs(factor_sums) <= factor_tol,
        max_tick_sum=_max_abs(factor_sums),
        gross_factor_income=sum(
            sum(abs(value) for value in row["factor_income_transaction_rate"]) for row in rows
        ),
        tolerance=factor_tol,
    )
    if rows and _max_abs(factor_sums) > factor_tol:
        findings.append(Finding(
            issue_id="world.factor_income_not_zero_sum",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="Real factor-income payments do not have equal recipient counterflows at transaction FX.",
            evidence=checks["factor_income_counterparty"],
            recommendation="Journal each debtor payment and creditor distribution as one signed bilateral flow.",
            detector="world_factor_income_counterparty",
        ))

    accrued_factor_sums = [
        sum(row["factor_income_accrued_transaction_rate"]) for row in rows
    ]
    accrued_factor_scale = max(
        (sum(abs(value) for value in row["factor_income_accrued_transaction_rate"])
         for row in rows),
        default=0.0,
    )
    accrued_factor_tol = max(1.0e-9, accrued_factor_scale * 1.0e-8)
    checks["factor_income_accrual_counterparty"] = _check(
        _max_abs(accrued_factor_sums) <= accrued_factor_tol,
        max_tick_sum=_max_abs(accrued_factor_sums),
        gross_factor_income_accrued=sum(
            sum(abs(value) for value in row["factor_income_accrued_transaction_rate"])
            for row in rows
        ),
        tolerance=accrued_factor_tol,
    )
    if rows and _max_abs(accrued_factor_sums) > accrued_factor_tol:
        findings.append(Finding(
            issue_id="world.factor_income_accrual_not_zero_sum",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="Accrued factor income lacks an equal bilateral creditor claim.",
            evidence=checks["factor_income_accrual_counterparty"],
            suspected_mechanisms=("ownerless current external-interest accrual",),
            recommendation="Allocate every accrual to a locked bilateral creditor claim.",
            detector="world_factor_income_accrual_counterparty",
        ))

    arrears_stocks = [
        sum(max(0.0, value) for value in row.get("factor_income_arrears", ()))
        for row in rows
    ]
    closing_arrears = arrears_stocks[-1] if arrears_stocks else 0.0
    peak_arrears = max(arrears_stocks, default=0.0)
    cumulative_new_arrears = sum(
        sum(max(0.0, value) for value in row.get("factor_income_unpaid_tick", ()))
        for row in rows
    )
    cumulative_cured_arrears = sum(
        sum(max(0.0, value) for value in row.get("factor_income_arrears_cured_tick", ()))
        for row in rows
    )
    arrears_scale = max(1.0, peak_arrears, cumulative_new_arrears)
    arrears_tol = max(_EPS, arrears_scale * 1.0e-10)
    bilateral_row_residuals = [
        row.get("factor_income_arrears", [0.0] * n)[debtor]
        - sum(row.get("factor_income_arrears_bilateral", _matrix(n))[debtor])
        - row.get("factor_income_arrears_unallocated", [0.0] * n)[debtor]
        for row in rows for debtor in range(n)
    ]
    checks["external_interest_service"] = _check(
        closing_arrears <= arrears_tol and _max_abs(bilateral_row_residuals) <= arrears_tol,
        closing_arrears_numeraire=closing_arrears,
        peak_arrears_numeraire=peak_arrears,
        ticks_with_arrears=sum(value > arrears_tol for value in arrears_stocks),
        cumulative_new_arrears_numeraire=cumulative_new_arrears,
        cumulative_cured_arrears_numeraire=cumulative_cured_arrears,
        max_bilateral_row_residual=_max_abs(bilateral_row_residuals),
        payer="consolidated_fiscal_or_external_issuer",
        settlement_control="external_interest_settlement_fraction",
        creditor_allocation="bilateral_locked",
        tolerance=arrears_tol,
    )
    if closing_arrears > arrears_tol:
        findings.append(Finding(
            issue_id="world.external_interest_arrears_without_resolution",
            severity="high",
            confidence="confirmed",
            category="external_solvency",
            claim=(
                "An economy could not service all contractual external interest; "
                "arrears are exposed but no restructuring/default allocation exists."
            ),
            evidence=checks["external_interest_service"],
            suspected_mechanisms=("external claims have no maturity or default contract",),
            recommendation=(
                "Add external debt contracts, arrears stocks, restructuring haircuts, "
                "and creditor loss allocation before calibrating long-horizon capital mobility."
            ),
            detector="world_external_interest_service",
        ))
    if rows and _max_abs(bilateral_row_residuals) > arrears_tol:
        findings.append(Finding(
            issue_id="world.external_interest_arrears_not_bilateral",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="Published debtor arrears do not reconcile to locked bilateral claims.",
            evidence=checks["external_interest_service"],
            recommendation=(
                "Keep the legacy debtor row as the exact sum of bilateral claims plus "
                "explicitly unallocated migrated stock."
            ),
            detector="world_external_interest_bilateral_stock",
        ))

    # Assemble published CA components on the common transaction-rate basis.
    ca_sums = [sum(row["current_account_components_transaction_rate"]) for row in rows]
    cumulative_ca_sum = sum(ca_sums)
    ca_scale = max(
        (sum(abs(value) for value in row["current_account_components_transaction_rate"])
         for row in rows), default=0.0,
    )
    ca_tol = max(1.0e-8, ca_scale * 1.0e-7)
    ca_passed = _max_abs(ca_sums) <= ca_tol and abs(cumulative_ca_sum) <= ca_tol
    checks["current_account_zero_sum"] = _check(
        ca_passed,
        max_tick_sum=_max_abs(ca_sums),
        cumulative_sum=cumulative_ca_sum,
        max_tick_scale=ca_scale,
        fx_basis="pre_grope_transaction_rate",
    )
    if rows and not ca_passed:
        findings.append(Finding(
            issue_id="world.current_account_not_zero_sum",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="The closed world's current accounts do not sum to zero.",
            evidence=checks["current_account_zero_sum"],
            suspected_mechanisms=("unbalanced signed current-transfer journal",),
            requested_probes=("signed_current_transfer_journal",),
            recommendation=(
                "Record signed host debits and gross origin receipts before splitting "
                "household and tax recipients."
            ),
            detector="world_ca_zero_sum",
        ))

    accrual_ca_sums = [
        sum(row["current_account_accrued_components_transaction_rate"])
        for row in rows
    ]
    accrual_ca_scale = max(
        (sum(abs(value) for value in row["current_account_accrued_components_transaction_rate"])
         for row in rows),
        default=0.0,
    )
    accrual_ca_tol = max(1.0e-8, accrual_ca_scale * 1.0e-7)
    checks["current_account_accrual_zero_sum"] = _check(
        _max_abs(accrual_ca_sums) <= accrual_ca_tol,
        max_tick_sum=_max_abs(accrual_ca_sums),
        cumulative_sum=sum(accrual_ca_sums),
        max_tick_scale=accrual_ca_scale,
        fx_basis="pre_grope_transaction_rate",
        tolerance=accrual_ca_tol,
    )
    if rows and _max_abs(accrual_ca_sums) > accrual_ca_tol:
        findings.append(Finding(
            issue_id="world.current_account_accrual_not_zero_sum",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="The closed world's accrual-basis current accounts do not sum to zero.",
            evidence=checks["current_account_accrual_zero_sum"],
            recommendation="Lock every accrued external-interest liability to a creditor asset.",
            detector="world_ca_accrual_zero_sum",
        ))

    # Compare the published CA to the independent transaction-rate reconstruction.
    rate_basis_residuals = [
        row["current_account"][i] - row["current_account_components_transaction_rate"][i]
        for row in rows for i in range(n)
    ]
    rate_basis_scale = max(
        (max(abs(row["current_account"][i]),
             abs(row["current_account_components_transaction_rate"][i]))
         for row in rows for i in range(n)), default=0.0,
    )
    rate_basis_tol = max(1.0e-8, rate_basis_scale * 1.0e-7)
    rate_basis_max = _max_abs(rate_basis_residuals)
    checks["current_account_transaction_rate_basis"] = _check(
        rate_basis_max <= rate_basis_tol,
        max_abs_post_vs_transaction_rate_gap=rate_basis_max,
        tolerance=rate_basis_tol,
    )
    if rows and rate_basis_max > rate_basis_tol:
        findings.append(Finding(
            issue_id="world.current_account_uses_post_grope_fx",
            severity="high",
            confidence="confirmed",
            category="external_measurement",
            claim="Current-account flows are translated at post-grope FX rather than their transaction rate.",
            evidence=checks["current_account_transaction_rate_basis"],
            suspected_mechanisms=("World current-account FX basis diverged from flow_e",),
            recommendation="Value flows at e0 and reserve e1 exclusively for closing stocks and revaluation.",
            measurement_status="legacy_invalid",
            detector="world_ca_fx_basis",
        ))

    accrual_rate_basis_residuals = [
        row["current_account_accrued"][i]
        - row["current_account_accrued_components_transaction_rate"][i]
        for row in rows for i in range(n)
    ]
    accrual_rate_basis_scale = max(
        (max(
            abs(row["current_account_accrued"][i]),
            abs(row["current_account_accrued_components_transaction_rate"][i]),
        ) for row in rows for i in range(n)),
        default=0.0,
    )
    accrual_rate_basis_tol = max(1.0e-8, accrual_rate_basis_scale * 1.0e-7)
    checks["current_account_accrual_transaction_rate_basis"] = _check(
        _max_abs(accrual_rate_basis_residuals) <= accrual_rate_basis_tol,
        max_abs_post_vs_transaction_rate_gap=_max_abs(accrual_rate_basis_residuals),
        tolerance=accrual_rate_basis_tol,
    )

    # First verify the mechanical NFA stock-flow bridge using the closing position for
    # revaluation.  This identity must pass even when the published CA definition is bad.
    nfa_bridge_residuals: list[float] = []
    for row in rows:
        for i in range(n):
            nfa_bridge_residuals.append(
                row["nfa"][i]
                - row["pre_nfa"][i]
                - row["nfa_transaction_flow"][i]
                - row["nfa_revaluation"][i]
            )
    nfa_bridge_scale = max(
        (abs(row["nfa"][i]) + abs(row["pre_nfa"][i])
         for row in rows for i in range(n)), default=0.0,
    )
    nfa_bridge_tol = max(1.0e-8, nfa_bridge_scale * 1.0e-8)
    checks["nfa_flow_revaluation_decomposition"] = _check(
        _max_abs(nfa_bridge_residuals) <= nfa_bridge_tol,
        max_abs_residual=_max_abs(nfa_bridge_residuals),
        tolerance=nfa_bridge_tol,
        valuation_basis="closing_position",
    )
    if rows and _max_abs(nfa_bridge_residuals) > nfa_bridge_tol:
        findings.append(Finding(
            issue_id="world.nfa_flow_revaluation_decomposition",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="NFA changes do not equal balance-sheet transaction flows plus closing-position revaluation.",
            evidence=checks["nfa_flow_revaluation_decomposition"],
            recommendation="Separate transaction and revaluation entries, including both sides of FX reserves.",
            detector="world_nfa_balance_sheet_bridge",
        ))

    augmented_bridge_residuals: list[float] = []
    for row in rows:
        for i in range(n):
            augmented_bridge_residuals.append(
                row["augmented_nfa"][i]
                - row["pre_augmented_nfa"][i]
                - (
                    row["nfa_transaction_flow"][i]
                    + row["factor_income_arrears_nfa_transaction_change"][i]
                )
                - (
                    row["nfa_revaluation"][i]
                    + row["factor_income_arrears_revaluation"][i]
                )
            )
    augmented_bridge_scale = max(
        (abs(row["augmented_nfa"][i]) + abs(row["pre_augmented_nfa"][i])
         for row in rows for i in range(n)),
        default=0.0,
    )
    augmented_bridge_tol = max(1.0e-8, augmented_bridge_scale * 1.0e-8)
    checks["augmented_nfa_flow_revaluation_decomposition"] = _check(
        _max_abs(augmented_bridge_residuals) <= augmented_bridge_tol,
        max_abs_residual=_max_abs(augmented_bridge_residuals),
        tolerance=augmented_bridge_tol,
        identity=(
            "delta_augmented_nfa = cash_nfa_transaction + arrears_transaction "
            "+ cash_nfa_revaluation + arrears_revaluation"
        ),
    )
    if rows and _max_abs(augmented_bridge_residuals) > augmented_bridge_tol:
        findings.append(Finding(
            issue_id="world.augmented_nfa_flow_revaluation_decomposition",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="Augmented NFA does not reconcile cash positions and contractual arrears.",
            evidence=checks["augmented_nfa_flow_revaluation_decomposition"],
            recommendation=(
                "Value closing bilateral arrears at closing FX and separate their "
                "transaction change from revaluation."
            ),
            detector="world_augmented_nfa_balance_sheet_bridge",
        ))

    # Then compare the independently measured NFA transaction flow with the model's CA
    # components.  Its residual is a real reporting failure, not an FX valuation artifact.
    sf_residuals: list[float] = []
    sf_examples: list[dict[str, float | int]] = []
    for current in rows:
        for i in range(n):
            residual = (
                current["nfa_transaction_flow"][i]
                - current["current_account_components_transaction_rate"][i]
            )
            sf_residuals.append(residual)
            if abs(residual) > 1.0e-7 and len(sf_examples) < 4:
                sf_examples.append({
                    "t": current["t"], "economy": i,
                    "nfa_transaction_flow": current["nfa_transaction_flow"][i],
                    "current_account_at_transaction_rate": (
                        current["current_account_components_transaction_rate"][i]
                    ),
                    "residual": residual,
                })
    sf_scale = max(
        (max(abs(row["nfa_transaction_flow"][i]),
             abs(row["current_account_components_transaction_rate"][i]))
         for row in rows for i in range(n)), default=0.0,
    )
    sf_tol = max(1.0e-8, sf_scale * 1.0e-7)
    sf_max = _max_abs(sf_residuals)
    checks["nfa_ca_valuation_reconciliation"] = _check(
        sf_max <= sf_tol,
        max_abs_residual=sf_max,
        tolerance=sf_tol,
        examples=sf_examples,
    )
    if sf_residuals and sf_max > sf_tol:
        findings.append(Finding(
            issue_id="world.nfa_ca_valuation_not_reconciled",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="Recorded current-account components do not equal the balance-sheet NFA transaction flow.",
            evidence=checks["nfa_ca_valuation_reconciliation"],
            suspected_mechanisms=("current-account journal does not match dealer balance-sheet flow",),
            requested_probes=("signed_current_transfer_journal",),
            recommendation=(
                "Derive CA from signed transaction postings and reconcile it to NFA "
                "before applying revaluation."
            ),
            detector="world_nfa_stock_flow",
        ))

    augmented_sf_residuals = [
        row["nfa_transaction_flow"][i]
        + row["factor_income_arrears_nfa_transaction_change"][i]
        - row["current_account_accrued_components_transaction_rate"][i]
        for row in rows for i in range(n)
    ]
    augmented_sf_scale = max(
        (max(
            abs(
                row["nfa_transaction_flow"][i]
                + row["factor_income_arrears_nfa_transaction_change"][i]
            ),
            abs(row["current_account_accrued_components_transaction_rate"][i]),
        ) for row in rows for i in range(n)),
        default=0.0,
    )
    augmented_sf_tol = max(1.0e-8, augmented_sf_scale * 1.0e-7)
    checks["augmented_nfa_accrual_ca_reconciliation"] = _check(
        _max_abs(augmented_sf_residuals) <= augmented_sf_tol,
        max_abs_residual=_max_abs(augmented_sf_residuals),
        tolerance=augmented_sf_tol,
    )
    if rows and _max_abs(augmented_sf_residuals) > augmented_sf_tol:
        findings.append(Finding(
            issue_id="world.augmented_nfa_accrual_ca_not_reconciled",
            severity="critical",
            confidence="confirmed",
            category="external_accounting",
            claim="Accrual current account does not equal augmented-NFA transaction flow.",
            evidence=checks["augmented_nfa_accrual_ca_reconciliation"],
            recommendation=(
                "Bridge the cash NFA flow to accrual CA with the bilateral arrears "
                "claim transaction."
            ),
            detector="world_augmented_nfa_stock_flow",
        ))

    late_gaps = [value for row in rows for value in row["late_settlement_revenue"]]
    late_max = _max_abs(late_gaps)
    export_scale = sum(sum(abs(value) for value in row["exports_numeraire"]) for row in rows)
    late_tol = max(1.0e-8, export_scale * 1.0e-8)
    late_passed = late_max <= late_tol
    checks["domestic_world_settlement_alignment"] = _check(
        late_passed,
        max_unrecorded_revenue=late_max,
        export_scale=export_scale,
        affected_ticks=sum(any(abs(value) > late_tol for value in row["late_settlement_revenue"]) for row in rows),
    )
    if rows and not late_passed:
        findings.append(Finding(
            issue_id="world.cross_border_settlement_after_domestic_commit",
            severity="critical",
            confidence="confirmed",
            category="coupling_order",
            claim="Cross-border exports alter live firm revenue after domestic P&L and metrics were finalized.",
            evidence=checks["domestic_world_settlement_alignment"],
            suspected_mechanisms=("World.step calls Economy.step before settle_trade",),
            requested_probes=("firm revenue before/after dealer update",),
            recommendation=(
                "Move world settlement before domestic P&L/metrics commit, or add an "
                "explicit post-settlement commit phase."
            ),
            detector="world_pre_post_snapshot",
        ))

    strata = any(bool(econ.cfg.consumption_strata) for econ in world.economies)
    strata_passed = not (world.trade and strata and rows and gross_trade <= _EPS)
    checks["consumption_strata_trade_channel"] = _check(
        strata_passed,
        consumption_strata=strata,
        gross_trade_numeraire=gross_trade,
        active_sources=sorted({source for row in rows for source in row["import_source"] if source >= 0}),
    )
    if not strata_passed:
        findings.append(Finding(
            issue_id="world.trade_disabled_by_consumption_strata",
            severity="critical",
            confidence="confirmed",
            category="coupling_order",
            claim="Trade is enabled but the consumption-strata goods path realizes no imports.",
            evidence=checks["consumption_strata_trade_channel"],
            suspected_mechanisms=("split goods sessions return before foreign offer injection",),
            recommendation="Inject the foreign offer into the relevant split sessions before market execution.",
            detector="world_strata_trade_activity",
        ))

    total_remittance = sum(
        sum(row["current_transfers_transaction_rate"]) for row in rows
    )
    remit_scale = sum(
        sum(abs(value) for value in row["current_transfers_transaction_rate"])
        for row in rows
    )
    remit_passed = remit_scale <= _EPS or abs(total_remittance) <= max(_EPS, remit_scale * 1.0e-7)
    checks["remittance_current_account_counterparty"] = _check(
        remit_passed,
        signed_world_sum=total_remittance,
        gross_scale=remit_scale,
        fx_basis="pre_grope_transaction_rate",
    )
    if not remit_passed:
        findings.append(Finding(
            issue_id="world.remittance_account_counterparty_missing",
            severity="high",
            confidence="confirmed",
            category="external_measurement",
            claim="Signed current transfers do not record equal host debits and gross origin credits.",
            evidence=checks["remittance_current_account_counterparty"],
            suspected_mechanisms=(
                "signed transfer journal is incomplete",
            ),
            recommendation=("Journal the signed host outflow and gross origin inflow, then "
                            "split the latter between households and tax revenue."),
            measurement_status="legacy_invalid",
            detector="world_transfer_zero_sum",
        ))

    # Rate convention contract: Config.r_interest and Economy._rate are already
    # per-tick (the domestic debt-service formula is principal * rate).  A second
    # division by World.periods_per_year silently underpays external factor income.
    # Keep periods_per_year as metadata; inspect the exact payment implementation so
    # this detector catches a future reintroduction even without a long dynamic run.
    factor_interest_names = tuple(getattr(capital_interest, "__code__").co_names)
    double_scaled = "periods_per_year" in factor_interest_names
    rate_convention_passed = not double_scaled
    checks["factor_income_rate_convention"] = _check(
        rate_convention_passed,
        policy_rate_unit="per_tick",
        configured_periods_per_year=float(world.periods_per_year),
        factor_income_uses_periods_per_year=double_scaled,
        expected_formula="interest = external_principal * per_tick_rate",
    )
    if not rate_convention_passed:
        findings.append(Finding(
            issue_id="world.factor_income_rate_double_scaled",
            severity="high",
            confidence="confirmed",
            category="time_scale",
            claim="Cross-border factor income divides an already per-tick policy rate by a second frequency factor.",
            evidence=checks["factor_income_rate_convention"],
            suspected_mechanisms=("capital_interest references World.periods_per_year",),
            recommendation="Apply the live per-tick rate once, matching domestic debt service.",
            detector="world_factor_income_rate_static_contract",
        ))

    return WorldDiagnosticResult(records=rows, checks=checks, findings=tuple(findings))
