"""Transport-neutral state machine used by the Godot desktop prototype.

The adapter deliberately owns no policy logic.  It translates small JSON commands
into the existing controller and shock APIs so the desktop client cannot mutate the
engine behind their validation, timing, or audit trails.

v29.1: the interactive run is a 3-economy coupled world (trade + capital +
migration, dealer-routed FX).  The player holds all five seats of economy 0;
economies 1-2 run unmanned (no decision contexts, frozen genesis policy).
"""
from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from macro_sim.config import Config
from macro_sim.controllers import (
    ControlledSimulationSession,
    ControllerService,
    HumanQueueOccupant,
)
from macro_sim.controllers.coordinator import SEATS
from macro_sim.controllers.protocol import canonical_value
from macro_sim.shocks import ShockSpec, get_shock_engine
from macro_sim.systems.banking import bank_for, loan_rate_for
from macro_sim.systems.firm_balance_sheet import firm_balance_sheet
from macro_sim.world import World
from macro_sim.world.country import ADVANCED, DEVELOPING, PETROSTATE


PROTOCOL_VERSION = 2
SERIES_LIMIT = 160
PLAYER_ECONOMY = 0

COUNTRIES = (
    {"name": "奥雷利亚", "latin": "AURELIA", "profile": ADVANCED},
    {"name": "博尔维亚", "latin": "BORVIA", "profile": DEVELOPING},
    {"name": "佩特罗尼亚", "latin": "PETRONIA", "profile": PETROSTATE},
)

# Per-economy series kept for every economy (world comparison + scorecard).
WORLD_METRIC_NAMES = (
    "real_output",
    "production_realization_rate",
    "unemployment_rate",
    "underemployed_share",
    "inflation",
    "inflation_target",
    "price_index",
    "avg_wage",
    "real_wage",
    "policy_rate",
    "population_alive",
    "gov_debt_to_gdp",
    "gov_deficit_to_gdp",
    "total_credit",
    "bank_capital",
    "writeoffs",
    "total_debt_service_ratio",
    "poverty_rate",
    "income_gini",
    "hh_wealth_gini",
    "welfare_log",
    "energy_price",
    "energy_produced",
    "energy_used",
    "energy_stock_total",
    "spr_stock",
)

# Rich god-view series kept for the player economy only (指标全景 panels).
# Grouping/labels live in the client; the runtime just serializes the keys.
# Every key verified present in the v124 desktop config's records.
PANEL_METRIC_NAMES = (
    # real economy
    "real_output", "real_consumption", "aggregate_capital",
    "investment_spending", "inventory_to_sales", "production_realization_rate",
    # labor
    "unemployment_rate", "u_natural", "underemployed_share",
    "vacancies_unfilled", "avg_wage", "wage_inflation",
    # prices & money
    "price_index", "inflation", "avg_markup", "policy_rate",
    "total_money", "real_wage",
    # fiscal
    "gov_debt", "gov_deficit", "tax_total", "gov_spending",
    "benefit_paid", "gov_debt_to_gdp",
    # banking & credit
    "total_credit", "bank_capital", "bank_deposit_total",
    "writeoffs", "total_debt_service_ratio", "interbank_rate",
    # capital market
    "equity_market_cap", "tobin_q_mean", "equity_wealth_share",
    "equity_turnover", "equity_ownership_gini", "hh_wealth_gini_incl_equity",
    # energy
    "energy_price", "energy_produced", "energy_used",
    "energy_stock_total", "energy_cost_share", "spr_stock",
    # distribution & welfare
    "poverty_rate", "income_gini", "hh_wealth_gini",
    "wage_p90_p10_ratio", "welfare_log", "savings_rate",
    # demography & firms
    "population_alive", "working_age_share", "avg_household_size",
    "births", "deaths", "firm_count_c",
    # domain-specific panel anatomy (kept out of the six headline cards)
    "real_output_growth", "labor_productivity", "labor_share",
    "labor_E", "labor_U", "labor_JG", "labor_OLF", "labor_employed_heads",
    "labor_hires_total", "labor_churn_seps_total", "labor_layoff_seps_total",
    "labor_bankruptcy_seps_total", "labor_death_seps_total", "labor_recalls_total",
    "labor_suspensions_total", "labor_ladder_moves_total", "labor_welfare_quits_total",
    "tax_profit", "tax_income", "tax_consumption", "tax_wealth", "tax_energy",
    "gov_consumption", "jg_spending", "public_investment", "gov_interest_bill",
    "augmented_gov_spending", "fiscal_revenue_total",
    "firm_debt_total", "household_debt_total_observed", "firm_credit_share",
    "household_credit_share", "new_loans_total", "bank_realized_credit_losses",
    "tobin_q_dispersion", "n_firms_q_above_1", "investment_q_corr",
    "energy_sold", "energy_unfilled", "energy_coverage_mean",
    "energy_capacity_utilization", "energy_flow_gap", "e_hhi",
    "poverty_gap", "bottom10_consumption", "median_real_household_income",
    "household_underwater_share", "person_income_gini", "person_wealth_gini",
    "child_dependency_ratio", "elder_dependency_ratio",
    "n_firms_necessity", "n_firms_luxury",
)

METRIC_NAMES = WORLD_METRIC_NAMES + (
    "avg_wage",
    "energy_price",
)

WORLD_RECORD_KEYS = (
    "e",
    "nfa",
    "current_account",
    "migrant_stock",
    "remittances",
    "import_value",
    "export_delivered_volume",
    "tariff_rev",
    "dealer_valuation",
    "peg_intact",
)


def _integer(name: str, value: Any, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _finite_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if not isinstance(value, (int, float)):
        return default
    number = float(value)
    return number if math.isfinite(number) else default


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return _finite_number(value)
    return str(value)


class SimulationRuntime:
    """Single-writer façade for one interactive simulation run."""

    def __init__(self, *, seed: int = 7) -> None:
        self._seed = seed
        self._proposal_sequence = 0
        self._shock_sequence = 0
        self.world: World
        self.session: ControlledSimulationSession
        self.service: ControllerService
        self.reset(seed=seed)

    def reset(self, *, seed: int | None = None) -> dict[str, Any]:
        if seed is not None:
            self._seed = _integer("seed", seed, minimum=0, maximum=2_147_483_647)
        # The desktop world uses the daily demographic economy and the existing
        # person-level labor market.  Without these flags a visually rich labor
        # page would have to fabricate age/sex/sector records from household FTEs.
        base = Config.v13(
            n_households=80,
            n_firms_c=12,
            n_firms_k=4,
            n_ticks=100_000,
            seed=self._seed,
            energy_enabled=True,
            energy_household=True,
            consumption_strata=True,
            labor_matching="persistent",
            labor_matching_friction=True,
            labor_relationship_wages=True,
            labor_job_ladder=True,
            labor_person_efficiency=True,
            labor_participation=True,
        )
        configs = [spec["profile"].apply(base) for spec in COUNTRIES]
        self.world = World(
            configs,
            base_seed=self._seed,
            trade=True,
            capital=True,
            migration=True,
            capital_mobility=1.0,
            capital_adjust=0.2,
        )
        self.session = ControlledSimulationSession(self.world, run_mode="interactive")
        for seat in SEATS:
            self.session.assign_seat(
                PLAYER_ECONOMY, seat, HumanQueueOccupant(), actor="desktop_prototype"
            )
        self.service = ControllerService(self.session)
        self._proposal_sequence = 0
        self._shock_sequence = 0
        self._panel_history: list[dict[str, float | int]] = []
        self._world_history: list[dict[str, Any]] = []
        self._labor_flow_counters: dict[str, float] = {}
        self._labor_flow_delta: dict[str, float] = {}
        self._last_verdict: dict[str, Any] | None = None
        self._pending_verdict_pid: str | None = None
        # Open tick-zero decision windows immediately so the UI has something real
        # to operate rather than inventing a separate frontend policy form.
        self.session.advance()
        return self.snapshot()

    def handle(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping):
            raise TypeError("command must be an object")
        name = command.get("command")
        if not isinstance(name, str) or not name:
            raise ValueError("command.command must be a non-empty string")
        if name in {"hello", "snapshot"}:
            return self.snapshot()
        if name == "new_game":
            seed = command.get("seed", self._seed)
            return self.reset(seed=seed)
        if name == "advance":
            ticks = _integer("ticks", command.get("ticks", 1), minimum=1, maximum=100)
            return self.advance(ticks)
        if name == "resolve_context":
            context_id = command.get("context_id")
            if not isinstance(context_id, str) or not context_id:
                raise ValueError("context_id must be a non-empty string")
            actions = command.get("actions", [])
            if not isinstance(actions, list):
                raise TypeError("actions must be an array")
            return self.resolve_context(context_id, actions)
        if name == "trigger_shock":
            return self.trigger_shock()
        if name == "get_schema":
            return self.schema()
        raise ValueError(f"unknown command {name!r}")

    def schema(self) -> dict[str, Any]:
        seats = {
            seat: dict(self.service.policy_schema(economy_id=PLAYER_ECONOMY, seat=seat))
            for seat in SEATS
        }
        return {
            "protocol_version": PROTOCOL_VERSION,
            "seats": seats,
            # protocol v1 clients read a flat treasury schema
            "levers": seats["treasury"]["levers"],
            "seat": "treasury",
            "economy_id": PLAYER_ECONOMY,
            "schema_version": seats["treasury"]["schema_version"],
        }

    def advance(self, ticks: int) -> dict[str, Any]:
        advanced = 0
        while advanced < ticks:
            result = self.session.advance()
            if result.status == "awaiting_human":
                break
            self._record_result(result.records, accumulate_flows=advanced > 0)
            advanced += 1
        snapshot = self.snapshot()
        snapshot["advanced_ticks"] = advanced
        return snapshot

    def resolve_context(
        self, context_id: str, actions: list[Mapping[str, Any]]
    ) -> dict[str, Any]:
        if context_id not in self.session.missing_context_ids:
            raise ValueError("context is not awaiting a desktop decision")
        context = self.session.coordinator.contexts[context_id]
        normalized_actions: list[dict[str, Any]] = []
        for index, action in enumerate(actions):
            if not isinstance(action, Mapping):
                raise TypeError(f"actions[{index}] must be an object")
            if set(action) != {"lever", "value"}:
                raise ValueError(f"actions[{index}] must contain lever and value")
            normalized_actions.append({"lever": action["lever"], "value": action["value"]})
        self._proposal_sequence += 1
        proposal_id = f"desktop:{self._proposal_sequence}:{context_id}"
        decision = self.service.submit_proposal(
            {
                "schema_version": context.schema_version,
                "proposal_id": proposal_id,
                "idempotency_key": proposal_id,
                "context_id": context_id,
                "actions": normalized_actions,
                "reason": "desktop_player_action" if actions else "desktop_player_pass",
                "based_on_policy_versions": dict(context.policy_versions),
            },
            actor="desktop_player",
        )
        if normalized_actions:
            self._pending_verdict_pid = proposal_id
        result = self.session.advance()
        if result.status == "advanced":
            self._record_result(result.records)
        return self.snapshot()

    def trigger_shock(self) -> dict[str, Any]:
        self._shock_sequence += 1
        start_tick = self.session.boundary_tick + 1
        self.world.schedule_shock(
            ShockSpec(
                shock_id=f"desktop_supply_disruption:{self._shock_sequence}",
                kind="productivity",
                start_tick=start_tick,
                magnitude=0.25,
                duration_ticks=20,
                announcement_tick=start_tick,
                source="desktop_prototype",
                calibration_note="Player-triggered prototype supply disruption.",
                tags=("desktop", "prototype"),
            )
        )
        return self.snapshot()

    def _record_result(self, records: Any, *, accumulate_flows: bool = False) -> None:
        if isinstance(records, list):
            rows = [row for row in records if isinstance(row, dict)]
        elif isinstance(records, dict):
            rows = [records]
        else:
            rows = []
        if not rows:
            return
        tick = self.session.boundary_tick
        # player-economy god-view panel point
        panel_point: dict[str, float | int] = {"tick": tick}
        player_row = rows[PLAYER_ECONOMY] if len(rows) > PLAYER_ECONOMY else rows[0]
        for name in PANEL_METRIC_NAMES:
            panel_point[name] = _finite_number(player_row.get(name))
        self._panel_history.append(panel_point)
        del self._panel_history[:-SERIES_LIMIT]
        flow_counter_names = (
            "labor_hires_total", "labor_churn_seps_total",
            "labor_layoff_seps_total", "labor_bankruptcy_seps_total",
            "labor_death_seps_total", "labor_recalls_total",
            "labor_suspensions_total", "labor_ladder_moves_total",
            "labor_welfare_quits_total",
        )
        current_counters = {
            name: _finite_number(player_row.get(name)) for name in flow_counter_names
        }
        tick_flow_delta = {
            name: max(0.0, value - self._labor_flow_counters.get(name, 0.0))
            for name, value in current_counters.items()
        }
        self._labor_flow_delta = {
            name: tick_flow_delta[name] + (
                self._labor_flow_delta.get(name, 0.0) if accumulate_flows else 0.0
            )
            for name in flow_counter_names
        }
        self._labor_flow_counters = current_counters
        # world point: per-economy compact metrics + cross-border record
        world_point: dict[str, Any] = {"tick": tick, "economies": []}
        for row in rows:
            world_point["economies"].append(
                {name: _finite_number(row.get(name)) for name in WORLD_METRIC_NAMES}
            )
        world_records = getattr(self.world, "world_records", None)
        if world_records:
            latest = world_records[-1]
            if isinstance(latest, dict):
                for key in WORLD_RECORD_KEYS:
                    world_point[key] = _jsonable(latest.get(key))
        self._world_history.append(world_point)
        del self._world_history[:-SERIES_LIMIT]

    def _merged_observation(self) -> dict[str, Any]:
        """Union of the five seat bulletins for the player economy.

        The player holds every seat, so their information set is the union of
        the per-seat access classes.  Keyed by series_id; a released value from
        any seat wins over a masked one.
        """
        merged: dict[str, dict[str, Any]] = {}
        meta: dict[str, Any] = {}
        for seat in SEATS:
            observation = self.session._observation(PLAYER_ECONOMY, seat, 0)
            payload = (
                observation.to_dict()
                if hasattr(observation, "to_dict")
                else observation
            )
            if not isinstance(payload, dict):
                continue
            for key, value in payload.items():
                if key != "releases":
                    meta.setdefault(key, value)
            for release in payload.get("releases", []):
                if not isinstance(release, dict):
                    continue
                series_id = str(release.get("series_id"))
                held = merged.get(series_id)
                if held is None or (
                    held.get("value") is None and release.get("value") is not None
                ):
                    merged[series_id] = dict(release)
        result = dict(meta)
        result["releases"] = [merged[k] for k in sorted(merged)]
        return result

    @staticmethod
    def _distribution(values: list[float]) -> dict[str, list[float]]:
        """Return decile shares and a compact Lorenz curve for non-negative values."""
        ordered = sorted(max(0.0, _finite_number(value)) for value in values)
        if not ordered:
            return {"deciles": [0.0] * 10, "lorenz": [0.0] * 11}
        total = sum(ordered)
        if total <= 1e-12:
            return {"deciles": [0.0] * 10, "lorenz": [0.0] * 11}
        deciles = [0.0] * 10
        for index, value in enumerate(ordered):
            bucket = min(9, int(index * 10 / len(ordered)))
            deciles[bucket] += value / total
        lorenz = [0.0]
        running = 0.0
        for share in deciles:
            running += share
            lorenz.append(min(1.0, running))
        lorenz[-1] = 1.0
        return {"deciles": deciles, "lorenz": lorenz}

    def _panel_details(self) -> dict[str, Any]:
        """Read-only micro aggregates for visualizations that scalar records cannot express."""
        econ = self.world.economies[PLAYER_ECONOMY]
        state = getattr(econ, "demographic_state", None)
        people = [
            person for person in getattr(state, "people", ())
            if getattr(person, "alive", True)
        ]
        pyramid_bands = (
            ("0–14", 0, 14), ("15–24", 15, 24), ("25–34", 25, 34),
            ("35–44", 35, 44), ("45–54", 45, 54), ("55–64", 55, 64),
            ("65+", 65, 200),
        )
        pyramid = []
        for label, low, high in pyramid_bands:
            bucket = [person for person in people if low <= int(person.age) <= high]
            pyramid.append({
                "label": label,
                "male": sum(1 for person in bucket if str(person.sex).upper() == "M"),
                "female": sum(1 for person in bucket if str(person.sex).upper() == "F"),
            })

        lm = getattr(econ, "labor_market", None)
        active_primary: dict[int, Any] = {}
        active_secondary: dict[int, Any] = {}
        nonsearch: set[int] = set()
        if lm is not None:
            suspended = set(getattr(lm, "suspended", {}) or {})
            active_primary = {
                int(pid): job for pid, job in (getattr(lm, "jobs", {}) or {}).items()
                if int(pid) not in suspended
            }
            active_secondary = {
                int(pid): job for pid, job in (getattr(lm, "second_jobs", {}) or {}).items()
                if int(pid) not in suspended
            }
            nonsearch = {int(pid) for pid in (getattr(lm, "nonsearch", set()) or set())}

        participation = []
        for label, low, high in (
            ("18–24", 18, 24), ("25–34", 25, 34), ("35–44", 35, 44),
            ("45–54", 45, 54), ("55–64", 55, 64),
        ):
            eligible = [person for person in people if low <= int(person.age) <= high]
            ids = {int(person.id) for person in eligible}
            participants = max(0, len(ids) - len(ids & nonsearch))
            employed = len(ids & set(active_primary))
            participation.append({
                "label": label,
                "population": len(ids),
                "participation_rate": participants / len(ids) if ids else 0.0,
                "employment_rate": employed / len(ids) if ids else 0.0,
            })

        working_ids = {int(person.id) for person in people if 18 <= int(person.age) <= 64}
        employed_heads = len(working_ids & set(active_primary))
        nonsearch_heads = len(working_ids & nonsearch)
        searching_or_guaranteed = max(0, len(working_ids) - employed_heads - nonsearch_heads)
        accounts = getattr(econ, "labor_accounts", None)
        jg_fte = _finite_number(getattr(accounts, "job_guarantee", 0.0))
        labor_states = [
            {"label": "就业 E", "value": employed_heads},
            {"label": "求职/保障 U·JG", "value": searching_or_guaranteed},
            {"label": "非劳动力 N", "value": nonsearch_heads},
        ]

        firm_sector: dict[str, str] = {}
        for firm in getattr(econ, "c_firms", ()):
            sector = str(getattr(firm, "consumption_sector", ""))
            firm_sector[str(firm.id)] = (
                "必需消费" if sector == "necessity" else
                "可选消费" if sector == "luxury" else "消费品"
            )
        for firm in getattr(econ, "k_firms", ()):
            firm_sector[str(firm.id)] = "资本品"
        for firm in getattr(econ, "e_firms", ()):
            firm_sector[str(firm.id)] = "能源"
        sector_order = ("必需消费", "可选消费", "消费品", "资本品", "能源")
        sector_hours = {label: 0.0 for label in sector_order}
        if lm is not None:
            for job in list(active_primary.values()) + list(active_secondary.values()):
                label = firm_sector.get(str(job.firm_id), "消费品")
                sector_hours[label] = sector_hours.get(label, 0.0) + _finite_number(
                    getattr(job, "hours", 1.0), 1.0
                )
        else:
            for firm in getattr(econ, "firms", ()):
                label = firm_sector.get(str(firm.id), "消费品")
                sector_hours[label] = sector_hours.get(label, 0.0) + _finite_number(
                    getattr(firm, "hired", 0.0)
                )
        employment_sectors = [
            {"label": label, "value": sector_hours[label]}
            for label in sector_order if sector_hours[label] > 1e-9
        ]
        if jg_fte > 1e-9:
            employment_sectors.append({"label": "就业保障", "value": jg_fte})

        flow = self._labor_flow_delta
        labor_flows = [
            {"label": "新招聘", "value": flow.get("labor_hires_total", 0.0)},
            {"label": "召回", "value": flow.get("labor_recalls_total", 0.0)},
            {"label": "岗位转换", "value": flow.get("labor_ladder_moves_total", 0.0)},
            {"label": "主动离职", "value": flow.get("labor_churn_seps_total", 0.0)},
            {"label": "裁员/破产", "value": (
                flow.get("labor_layoff_seps_total", 0.0)
                + flow.get("labor_bankruptcy_seps_total", 0.0)
                + flow.get("labor_suspensions_total", 0.0)
            )},
            {"label": "退出劳动力", "value": flow.get("labor_welfare_quits_total", 0.0)},
        ]

        sector_rows = []
        for label, firms in (
            ("必需消费", [f for f in getattr(econ, "c_firms", ()) if getattr(f, "consumption_sector", "") == "necessity"]),
            ("可选消费", [f for f in getattr(econ, "c_firms", ()) if getattr(f, "consumption_sector", "") == "luxury"]),
            ("消费品", [f for f in getattr(econ, "c_firms", ()) if not getattr(f, "consumption_sector", "")]),
            ("资本品", list(getattr(econ, "k_firms", ()))),
            ("能源", list(getattr(econ, "e_firms", ()))),
        ):
            if not firms:
                continue
            sector_rows.append({
                "label": label,
                "firms": len(firms),
                "produced": sum(_finite_number(getattr(firm, "produced", 0.0)) for firm in firms),
                "sales": sum(_finite_number(getattr(firm, "sales", 0.0)) for firm in firms),
                "inventory": sum(_finite_number(getattr(firm, "inventory", 0.0)) for firm in firms),
                "employment": sector_hours.get(label, 0.0),
            })

        capital_firms = []
        for firm in getattr(econ, "c_firms", ()):
            market_cap = _finite_number(getattr(firm, "share_price", 0.0)) * _finite_number(
                getattr(firm, "shares_outstanding", 0.0)
            )
            if market_cap <= 0.0:
                continue
            capital_firms.append({
                "label": str(firm.id),
                "q": _finite_number(getattr(firm, "tobin_q", 0.0)),
                "investment": _finite_number(getattr(firm, "investment", 0.0)),
                "market_cap": market_cap,
            })

        bridge = getattr(econ, "demographic_bridge", None)
        person_income: list[float] = []
        person_wealth: list[float] = []
        if bridge is not None:
            for person in people:
                person_id = int(person.id)
                if not bridge.claims.has_person(person_id):
                    continue
                sheet = bridge.claims.balance_sheet(person_id)
                person_income.append(_finite_number(
                    sheet.labor_income_tick + sheet.capital_income_tick
                    + sheet.transfer_income_tick
                ))
                person_wealth.append(_finite_number(sheet.net_worth))
        live_households = [
            household for household in getattr(econ, "households", ())
            if bridge is None or bridge.household_has_living_members(household.id)
        ]
        consumption = [_finite_number(household.spent) for household in live_households]

        return {
            "labor": {
                "states": labor_states,
                "employment_sectors": employment_sectors,
                "flows": labor_flows,
                "participation_by_age": participation,
                "working_age_population": len(working_ids),
                "jg_fte": jg_fte,
            },
            "population": {"pyramid": pyramid},
            "real_economy": {"sectors": sector_rows},
            "capital_market": {"firms": capital_firms},
            "distribution": {
                "income": self._distribution(person_income),
                "wealth": self._distribution(person_wealth),
                "consumption": self._distribution(consumption),
            },
        }

    def _firm_snapshot(self) -> dict[str, Any]:
        """Current operating, financial, workforce and ownership books by firm."""
        econ = self.world.economies[PLAYER_ECONOMY]
        state = getattr(econ, "demographic_state", None)
        people = [
            person for person in getattr(state, "people", ())
            if getattr(person, "alive", True)
        ]
        people_by_id = {int(person.id): person for person in people}
        bridge = getattr(econ, "demographic_bridge", None)
        lm = getattr(econ, "labor_market", None)
        suspensions = (getattr(lm, "suspended", {}) or {}) if lm is not None else {}
        suspended = set(suspensions)
        primary_jobs = (getattr(lm, "jobs", {}) or {}) if lm is not None else {}
        second_jobs = (getattr(lm, "second_jobs", {}) or {}) if lm is not None else {}

        k_ids = {str(firm.id) for firm in getattr(econ, "k_firms", ())}
        e_ids = {str(firm.id) for firm in getattr(econ, "e_firms", ())}
        full_pnl = bool(getattr(econ.cfg, "firm_full_pnl", False))
        priced_books = bool(getattr(econ.cfg, "priced_firm_balance_sheet", False))
        items: list[dict[str, Any]] = []

        for firm in getattr(econ, "firms", ()):
            firm_id = str(firm.id)
            consumption_sector = str(getattr(firm, "consumption_sector", ""))
            if firm_id in e_ids:
                sector = "能源"
                sector_code = "energy"
            elif firm_id in k_ids:
                sector = "资本品"
                sector_code = "capital"
            elif consumption_sector == "necessity":
                sector = "必需消费"
                sector_code = "necessity"
            elif consumption_sector == "luxury":
                sector = "可选消费"
                sector_code = "luxury"
            else:
                sector = "消费品"
                sector_code = "consumption"

            employees: list[dict[str, Any]] = []
            for contract_type, jobs in (("主业", primary_jobs), ("第二职业", second_jobs)):
                for person_id_raw, job in jobs.items():
                    if str(getattr(job, "firm_id", "")) != firm_id:
                        continue
                    person_id = int(person_id_raw)
                    person = people_by_id.get(person_id)
                    is_suspended = contract_type == "主业" and person_id in suspended
                    suspension = suspensions.get(person_id) if is_suspended else None
                    hours = max(0.0, _finite_number(getattr(job, "hours", 1.0), 1.0))
                    efficiency = (
                        _finite_number(lm.e_of(person_id), 1.0)
                        if lm is not None else 1.0
                    )
                    paid_wage = (
                        _finite_number(lm.wage_of(person_id, firm))
                        if lm is not None else _finite_number(getattr(firm, "wage", 0.0))
                    )
                    employees.append({
                        "firm_id": firm_id,
                        "person_id": person_id,
                        "sex": str(getattr(person, "sex", "")) if person is not None else None,
                        "age": int(getattr(person, "age", 0)) if person is not None else None,
                        "household_id": (
                            int(person.household_id)
                            if person is not None and person.household_id is not None else None
                        ),
                        "contract": contract_type,
                        "status": "停薪留职" if is_suspended else "在岗",
                        "suspended_since_tick": (
                            int(getattr(suspension, "since_tick", 0))
                            if suspension is not None else None
                        ),
                        "suspension_wage": (
                            _finite_number(getattr(suspension, "wage_at", 0.0))
                            if suspension is not None else None
                        ),
                        "hire_date": str(getattr(job, "hire_date", "")),
                        "hours": 0.0 if is_suspended else hours,
                        "contract_hours": hours,
                        "locked_wage": _finite_number(getattr(job, "wage", 0.0)),
                        "paid_wage": paid_wage,
                        "efficiency": efficiency,
                        "compensation": 0.0 if is_suspended else paid_wage * hours,
                    })
            employees.sort(key=lambda row: (row["status"] != "在岗", row["person_id"]))
            active_ids = {
                int(row["person_id"]) for row in employees if row["status"] == "在岗"
            }
            employment_fte = sum(float(row["hours"]) for row in employees)

            shares_outstanding = max(
                0.0, _finite_number(getattr(firm, "shares_outstanding", 0.0))
            )
            share_price = max(0.0, _finite_number(getattr(firm, "share_price", 0.0)))
            shareholders: list[dict[str, Any]] = []
            if bridge is not None and shares_outstanding > 0.0:
                for person in people:
                    person_id = int(person.id)
                    if not bridge.claims.has_person(person_id):
                        continue
                    sheet = bridge.claims.balance_sheet(person_id)
                    shares = max(
                        0.0, _finite_number(sheet.equity_claims.get(firm_id, 0.0))
                    )
                    if shares <= 1e-12:
                        continue
                    shareholders.append({
                        "person_id": person_id,
                        "household_id": (
                            int(person.household_id)
                            if person.household_id is not None else None
                        ),
                        "shares": shares,
                        "ownership": shares / shares_outstanding,
                        "market_value": shares * share_price,
                    })
            shareholders.sort(key=lambda row: float(row["shares"]), reverse=True)
            shares_observed = sum(float(row["shares"]) for row in shareholders)

            sheet = firm_balance_sheet(econ, firm)
            bank = bank_for(econ, firm_id)
            bank_id = str(bank.id) if bank is not None else None
            loan_rate = _finite_number(loan_rate_for(econ, firm_id)) if bank is not None else None
            produced = _finite_number(getattr(firm, "produced", 0.0))
            sales = _finite_number(getattr(firm, "sales", 0.0))
            production_target = _finite_number(getattr(firm, "production_target", 0.0))
            revenue = _finite_number(getattr(firm, "revenue", 0.0))
            profit = _finite_number(getattr(firm, "profit", 0.0))
            net_income = _finite_number(getattr(firm, "pnl_net_income", 0.0))
            earnings = net_income if full_pnl else profit
            if full_pnl:
                pnl_snapshot: dict[str, Any] = {
                    "full_statement": True,
                    "revenue": _finite_number(firm.pnl_revenue),
                    "revenue_carry_opening": _finite_number(firm.pnl_revenue_carry_opening),
                    "revenue_carry": _finite_number(firm.pnl_revenue_carry),
                    "intermediate_inputs": _finite_number(firm.pnl_intermediate_inputs),
                    "compensation": _finite_number(firm.pnl_compensation),
                    "ebitda": _finite_number(firm.pnl_ebitda),
                    "capital_price": _finite_number(firm.pnl_capital_price),
                    "depreciation": _finite_number(firm.pnl_depreciation),
                    "ebit": _finite_number(firm.pnl_ebit),
                    "interest_accrued": _finite_number(firm.pnl_interest_accrued),
                    "interest_due": _finite_number(firm.pnl_interest_due),
                    "interest_paid": _finite_number(firm.pnl_interest_expense),
                    "interest_shortfall": _finite_number(firm.pnl_interest_shortfall),
                    "interest_arrears_opening": _finite_number(firm.pnl_interest_arrears_opening),
                    "interest_arrears": _finite_number(firm.pnl_interest_arrears),
                    "pre_tax_income": _finite_number(firm.pnl_pre_tax_income),
                    "profit_tax": _finite_number(firm.pnl_profit_tax),
                    "windfall_tax": _finite_number(firm.pnl_windfall_tax),
                    "net_income": net_income,
                    "dividends": _finite_number(firm.pnl_dividends_paid),
                    "retained_earnings": _finite_number(firm.pnl_retained_earnings),
                }
            else:
                dividends = max(
                    0.0,
                    _finite_number(getattr(firm, "rho", 0.0)) * max(0.0, profit)
                    - _finite_number(getattr(firm, "dividend_shortfall", 0.0)),
                )
                pnl_snapshot = {
                    "full_statement": False,
                    "revenue": revenue,
                    "revenue_carry_opening": None,
                    "revenue_carry": None,
                    "intermediate_inputs": _finite_number(getattr(firm, "energy_cost_used", 0.0)),
                    "compensation": _finite_number(getattr(firm, "wagebill", 0.0)),
                    "ebitda": profit,
                    "capital_price": None,
                    "depreciation": None,
                    "ebit": None,
                    "interest_accrued": None,
                    "interest_due": None,
                    "interest_paid": None,
                    "interest_shortfall": None,
                    "interest_arrears_opening": None,
                    "interest_arrears": None,
                    "pre_tax_income": profit,
                    "profit_tax": None,
                    "windfall_tax": None,
                    "net_income": profit,
                    "dividends": dividends,
                    "retained_earnings": profit - dividends,
                }
            idle_ticks = int(getattr(firm, "idle_ticks", 0))
            insolvent_ticks = int(getattr(firm, "insolvent_ticks", 0))
            subscale_ticks = int(getattr(firm, "subscale_ticks", 0))
            if insolvent_ticks > 0:
                condition = "偿付风险"
            elif idle_ticks > 0:
                condition = "闲置观察"
            elif subscale_ticks > 0:
                condition = "规模预警"
            else:
                condition = "正常经营"

            items.append({
                "firm_id": firm_id,
                "sector": sector,
                "sector_code": sector_code,
                "condition": condition,
                "state_owned": bool(getattr(firm, "state_owned", False)),
                "sells": str(getattr(firm, "sells", "")),
                "technology": str(getattr(firm, "tech", "")),
                "invests": bool(getattr(firm, "invests", False)),
                "bank": {"bank_id": bank_id, "loan_rate": loan_rate},
                "operations": {
                    "capital_service_pricing_enabled": bool(
                        getattr(econ.cfg, "capital_service_pricing", False)
                    ),
                    "demand_expected": _finite_number(getattr(firm, "demand_expected", 0.0)),
                    "target_inventory": _finite_number(getattr(firm, "target_inventory", 0.0)),
                    "production_target": production_target,
                    "produced": produced,
                    "sales": sales,
                    "revenue": revenue,
                    "inventory": _finite_number(getattr(firm, "inventory", 0.0)),
                    "rationed_demand": _finite_number(getattr(firm, "rationed_demand", 0.0)),
                    "production_realization": produced / production_target if production_target > 0 else None,
                    "sales_realization": sales / produced if produced > 0 else None,
                    "price": _finite_number(getattr(firm, "price", 0.0)),
                    "wage": _finite_number(getattr(firm, "wage", 0.0)),
                    "markup": _finite_number(getattr(firm, "markup", 0.0)),
                    "wagebill": _finite_number(getattr(firm, "wagebill", 0.0)),
                    "pricing_capital_price": _finite_number(getattr(firm, "pricing_capital_price", 0.0)),
                    "pricing_capital_service_rate": _finite_number(getattr(firm, "pricing_capital_service_rate", 0.0)),
                    "pricing_capital_service_cost": _finite_number(getattr(firm, "pricing_capital_service_cost", 0.0)),
                    "pricing_capital_unit_cost": _finite_number(getattr(firm, "pricing_capital_unit_cost", 0.0)),
                    "profit": profit,
                    "earnings": earnings,
                },
                "labor": {
                    "active_heads": len(active_ids),
                    "contract_count": len(employees),
                    "employment_fte": employment_fte,
                    "efficiency_units": _finite_number(getattr(firm, "hired", 0.0)),
                    "labor_demand_notional": _finite_number(getattr(firm, "labor_demand_notional", 0.0)),
                    "labor_demand_effective": _finite_number(getattr(firm, "labor_demand_eff", 0.0)),
                    "vacancies": max(0.0, _finite_number(getattr(firm, "labor_demand_eff", 0.0)) - _finite_number(getattr(firm, "hired", 0.0))),
                    "vacancy_age": int((getattr(lm, "vacancy_age", {}) or {}).get(firm_id, 0)) if lm is not None else 0,
                    "employees": employees,
                },
                "capital": {
                    "units": _finite_number(getattr(firm, "capital", 0.0)),
                    "previous_units": _finite_number(getattr(firm, "capital_prev", 0.0)),
                    "investment_target": _finite_number(getattr(firm, "investment_target", 0.0)),
                    "investment": _finite_number(getattr(firm, "investment", 0.0)),
                    "depreciation_rate": _finite_number(getattr(firm, "delta_K", 0.0)),
                    "energy_input_stock": _finite_number(getattr(firm, "energy_stock", 0.0)),
                    "energy_input_average_cost": _finite_number(getattr(firm, "energy_avg_cost", 0.0)),
                    "energy_input_stock_cost": _finite_number(getattr(firm, "energy_stock_cost", 0.0)),
                    "energy_bought": _finite_number(getattr(firm, "energy_bought", 0.0)),
                    "energy_used": _finite_number(getattr(firm, "energy_used", 0.0)),
                    "energy_cost_used": _finite_number(getattr(firm, "energy_cost_used", 0.0)),
                    "capacity": (
                        _finite_number(getattr(firm, "capacity_kappa", 0.0))
                        * _finite_number(getattr(firm, "capital", 0.0))
                    ),
                },
                "balance_sheet": {
                    "valuation_basis": "replacement_cost",
                    "priced_book_enabled": priced_books,
                    "cash": _finite_number(sheet.cash),
                    "capital_units": _finite_number(sheet.capital_units),
                    "capital_unit_price": _finite_number(sheet.capital_unit_price),
                    "capital_value": _finite_number(sheet.capital_value),
                    "output_inventory_units": _finite_number(sheet.output_inventory_units),
                    "output_inventory_unit_price": _finite_number(sheet.output_inventory_unit_price),
                    "output_inventory_value": _finite_number(sheet.output_inventory_value),
                    "work_in_progress_units": _finite_number(sheet.work_in_progress_units),
                    "work_in_progress_value": _finite_number(sheet.work_in_progress_value),
                    "input_inventory_units": _finite_number(sheet.input_inventory_units),
                    "input_inventory_value": _finite_number(sheet.input_inventory_value),
                    "inventory_value": _finite_number(sheet.inventory_value),
                    "gross_assets": _finite_number(sheet.gross_assets),
                    "debt": _finite_number(sheet.debt),
                    "interest_arrears": _finite_number(sheet.interest_arrears),
                    "book_equity": _finite_number(sheet.book_equity),
                    "eligible_collateral_value": _finite_number(sheet.eligible_collateral_value),
                    "borrowing_base_proxy": _finite_number(sheet.borrowing_base_proxy),
                    "borrowing_base_headroom": _finite_number(sheet.borrowing_base_headroom),
                    "capital_haircut": _finite_number(sheet.capital_haircut),
                    "inventory_haircut": _finite_number(sheet.inventory_haircut),
                },
                "pnl": pnl_snapshot,
                "equity": {
                    "enabled": shares_outstanding > 0.0,
                    "shares_outstanding": shares_outstanding,
                    "share_price": share_price,
                    "last_share_price": _finite_number(getattr(firm, "share_last_price", 0.0)),
                    "share_trend": _finite_number(getattr(firm, "share_trend", 0.0)),
                    "market_cap": shares_outstanding * share_price,
                    "fundamental_per_share": _finite_number(getattr(firm, "equity_fundamental", 0.0)),
                    "residual_income_ema": _finite_number(getattr(firm, "residual_income_ema", 0.0)),
                    "tobin_q": _finite_number(getattr(firm, "tobin_q", 0.0)),
                    "tobin_q_ema": _finite_number(getattr(firm, "tobin_q_ema", 0.0)),
                    "attractiveness": _finite_number(getattr(firm, "attractiveness", 0.0)),
                    "shareholder_count": len(shareholders),
                    "shares_observed": shares_observed,
                    "ownership_coverage": shares_observed / shares_outstanding if shares_outstanding > 0 else None,
                    "shareholders": shareholders,
                },
                "parameters": {
                    "demand_adjustment": _finite_number(getattr(firm, "lambda_d", 0.0)),
                    "inventory_target_ratio": _finite_number(getattr(firm, "phi", 0.0)),
                    "markup_adjustment": _finite_number(getattr(firm, "eta", 0.0)),
                    "markup_min": _finite_number(getattr(firm, "mu_min", 0.0)),
                    "markup_max": _finite_number(getattr(firm, "mu_max", 0.0)),
                    "wage_adjustment": _finite_number(getattr(firm, "omega", 0.0)),
                    "labor_productivity": _finite_number(getattr(firm, "a", 0.0)),
                    "tfp": _finite_number(getattr(firm, "A", 0.0)),
                    "capital_share": _finite_number(getattr(firm, "alpha", 0.0)),
                    "capital_output_target": _finite_number(getattr(firm, "v", 0.0)),
                    "investment_adjustment": _finite_number(getattr(firm, "lambda_I", 0.0)),
                    "dividend_payout_ratio": _finite_number(getattr(firm, "rho", 0.0)),
                    "coordination_cost_slope": _finite_number(getattr(firm, "dis_slope", 0.0)),
                    "energy_intensity": _finite_number(getattr(firm, "energy_intensity", 0.0)),
                    "capacity_kappa": _finite_number(getattr(firm, "capacity_kappa", 0.0)),
                },
                "signals": {
                    "idle_ticks": idle_ticks,
                    "insolvent_ticks": insolvent_ticks,
                    "subscale_ticks": subscale_ticks,
                    "previous_sales": _finite_number(getattr(firm, "sales_prev", 0.0)),
                    "previous_hiring": _finite_number(getattr(firm, "hired_prev", 0.0)),
                    "previous_effective_labor_demand": _finite_number(getattr(firm, "labor_demand_eff_prev", 0.0)),
                    "previous_target_inventory": _finite_number(getattr(firm, "target_inventory_prev", 0.0)),
                    "previous_rationed_demand": _finite_number(getattr(firm, "rationed_prev", 0.0)),
                    "sector_switch_pressure": int(getattr(firm, "switch_pressure", 0)),
                    "dividend_shortfall": _finite_number(getattr(firm, "dividend_shortfall", 0.0)),
                },
            })

        sector_counts: dict[str, int] = {}
        for item in items:
            label = str(item["sector"])
            sector_counts[label] = sector_counts.get(label, 0) + 1
        return {
            "as_of_date": str(getattr(state, "current_date", "")),
            "summary": {
                "firm_count": len(items),
                "sector_counts": sector_counts,
                "employment_fte": sum(float(item["labor"]["employment_fte"]) for item in items),
                "active_heads": len({
                    int(row["person_id"])
                    for item in items for row in item["labor"]["employees"]
                    if row["status"] == "在岗"
                }),
                "total_revenue": sum(float(item["operations"]["revenue"]) for item in items),
                "total_earnings": sum(float(item["operations"]["earnings"]) for item in items),
                "total_assets": sum(float(item["balance_sheet"]["gross_assets"]) for item in items),
                "total_debt": sum(float(item["balance_sheet"]["debt"]) for item in items),
                "total_market_cap": sum(float(item["equity"]["market_cap"]) for item in items),
            },
            "items": items,
        }

    def _household_snapshot(self) -> dict[str, Any]:
        """Current household and person balance sheets for the household explorer."""
        econ = self.world.economies[PLAYER_ECONOMY]
        state = getattr(econ, "demographic_state", None)
        bridge = getattr(econ, "demographic_bridge", None)
        if state is None or bridge is None:
            return {
                "as_of_date": None,
                "summary": {
                    "household_count": 0,
                    "population": 0,
                    "total_assets": 0.0,
                    "total_debt": 0.0,
                    "total_net_worth": 0.0,
                    "total_consumption": 0.0,
                },
                "items": [],
            }

        people = [person for person in state.people if getattr(person, "alive", True)]
        grouped: dict[int, list[Any]] = {}
        for person in people:
            household_id = getattr(person, "household_id", None)
            if household_id is not None:
                grouped.setdefault(int(household_id), []).append(person)

        firm_prices = {
            str(firm.id): _finite_number(getattr(firm, "share_price", 0.0))
            for firm in getattr(econ, "firms", ())
        }
        aggregate_equity_price = _finite_number(
            getattr(getattr(econ, "equity", None), "price", 0.0)
        )
        bank_prices = {
            str(bank.id): _finite_number(getattr(bank, "share_price", 0.0))
            for bank in getattr(econ, "banks", ())
        }
        lm = getattr(econ, "labor_market", None)
        suspended = set(getattr(lm, "suspended", {}) or {}) if lm is not None else set()
        primary_jobs = (getattr(lm, "jobs", {}) or {}) if lm is not None else {}
        second_jobs = (getattr(lm, "second_jobs", {}) or {}) if lm is not None else {}
        nonsearch = {
            int(person_id)
            for person_id in (getattr(lm, "nonsearch", set()) or set())
        } if lm is not None else set()
        firm_sector: dict[str, str] = {}
        for firm in getattr(econ, "c_firms", ()):
            subsector = str(getattr(firm, "consumption_sector", ""))
            firm_sector[str(firm.id)] = (
                "必需消费" if subsector == "necessity" else
                "可选消费" if subsector == "luxury" else "消费品"
            )
        for firm in getattr(econ, "k_firms", ()):
            firm_sector[str(firm.id)] = "资本品"
        for firm in getattr(econ, "e_firms", ()):
            firm_sector[str(firm.id)] = "能源"

        household_agents = {str(household.id): household for household in econ.households}
        public_guardian_id = getattr(state, "public_guardian_household_id", None)
        housing = getattr(econ, "housing", None)
        house_price = _finite_number(getattr(econ, "_house_price", 0.0))
        items: list[dict[str, Any]] = []

        for household_id in sorted(grouped):
            account_id = bridge.household_to_account.get(household_id)
            if account_id is None:
                continue
            member_people = sorted(grouped[household_id], key=lambda person: int(person.id))
            member_ids = {int(person.id) for person in member_people}
            member_rows: list[dict[str, Any]] = []
            household_components = {
                "cash": 0.0,
                "firm_equity": 0.0,
                "bank_equity": 0.0,
                "bonds": 0.0,
                "housing": 0.0,
            }
            household_debt = 0.0
            household_consumption = 0.0
            household_income = 0.0

            for person in member_people:
                person_id = int(person.id)
                if not bridge.claims.has_person(person_id):
                    continue
                sheet = bridge.claims.balance_sheet(person_id)
                firm_equity = 0.0
                for asset_id, shares in sheet.equity_claims.items():
                    price = (
                        aggregate_equity_price
                        if str(asset_id) == "__aggregate_equity__"
                        else firm_prices.get(str(asset_id), 0.0)
                    )
                    firm_equity += _finite_number(shares) * (
                        price if price > 0.0 else 1.0
                    )
                bank_equity = sum(
                    _finite_number(shares) * (
                        bank_prices.get(str(bank_id), 0.0)
                        if bank_prices.get(str(bank_id), 0.0) > 0.0 else 1.0
                    )
                    for bank_id, shares in sheet.bank_equity_claims.items()
                )
                cash = _finite_number(sheet.cash_claim)
                bonds = _finite_number(sheet.bond_face_claim)
                debt = max(0.0, _finite_number(sheet.debt_claim))
                gross_assets = cash + firm_equity + bank_equity + bonds
                consumption = max(0.0, _finite_number(sheet.consumption_allocated_tick))
                labor_income = _finite_number(sheet.labor_income_tick)
                capital_income = _finite_number(sheet.capital_income_tick)
                transfer_income = _finite_number(sheet.transfer_income_tick)
                total_income = labor_income + capital_income + transfer_income

                partner_id = getattr(person, "partner_id", None)
                parent_ids = [
                    int(parent_id) for parent_id in (
                        getattr(person, "mother_id", None),
                        getattr(person, "father_id", None),
                    ) if parent_id is not None
                ]
                guardian_id = getattr(person, "guardian_id", None)
                if household_id == public_guardian_id and int(person.age) < 18:
                    relationship = "公共监护"
                elif guardian_id is not None and int(guardian_id) in member_ids:
                    relationship = "被监护人"
                elif any(parent_id in member_ids for parent_id in parent_ids):
                    relationship = "子女"
                elif partner_id is not None and int(partner_id) in member_ids:
                    relationship = "伴侣"
                elif int(person.age) < 18:
                    relationship = "未成年成员"
                else:
                    relationship = "成年成员"

                employers: list[dict[str, Any]] = []
                for contract_name, contract_jobs in (
                    ("主业", primary_jobs), ("第二职业", second_jobs)
                ):
                    contract_job = contract_jobs.get(person_id)
                    if contract_job is None:
                        continue
                    employer_id = str(contract_job.firm_id)
                    is_suspended = contract_name == "主业" and person_id in suspended
                    employers.append({
                        "firm_id": employer_id,
                        "sector": firm_sector.get(employer_id, "企业"),
                        "contract": contract_name,
                        "status": "停薪留职" if is_suspended else "在岗",
                        "hours": (
                            0.0 if is_suspended else
                            _finite_number(getattr(contract_job, "hours", 1.0), 1.0)
                        ),
                        "contract_hours": _finite_number(
                            getattr(contract_job, "hours", 1.0), 1.0
                        ),
                        "wage": _finite_number(getattr(contract_job, "wage", 0.0)),
                        "hire_date": str(getattr(contract_job, "hire_date", "")),
                    })
                active_employers = [
                    item for item in employers if item["status"] == "在岗"
                ]
                if active_employers:
                    labor_status = "就业"
                    employer = active_employers[0]
                elif int(person.age) < 18:
                    labor_status = "未成年"
                    employer = None
                elif int(person.age) > 64:
                    labor_status = "退休年龄"
                    employer = None
                elif person_id in nonsearch:
                    labor_status = "非劳动力"
                    employer = None
                else:
                    labor_status = "求职/就业保障"
                    employer = None

                member_rows.append({
                    "person_id": person_id,
                    "age": int(person.age),
                    "sex": str(person.sex),
                    "birth_date": str(person.birth_date),
                    "relationship": relationship,
                    "marital_status": "有伴侣" if partner_id is not None else "无伴侣",
                    "partner_id": int(partner_id) if partner_id is not None else None,
                    "mother_id": int(person.mother_id) if person.mother_id is not None else None,
                    "father_id": int(person.father_id) if person.father_id is not None else None,
                    "guardian_id": int(guardian_id) if guardian_id is not None else None,
                    "labor_status": labor_status,
                    "employer": employer,
                    "employers": employers,
                    "assets": {
                        "cash": cash,
                        "firm_equity": firm_equity,
                        "bank_equity": bank_equity,
                        "bonds": bonds,
                        "total": gross_assets,
                    },
                    "debt": debt,
                    "net_worth": gross_assets - debt,
                    "consumption": consumption,
                    "income": {
                        "labor": labor_income,
                        "capital": capital_income,
                        "transfer": transfer_income,
                        "total": total_income,
                    },
                })
                household_components["cash"] += cash
                household_components["firm_equity"] += firm_equity
                household_components["bank_equity"] += bank_equity
                household_components["bonds"] += bonds
                household_debt += debt
                household_consumption += consumption
                household_income += total_income

            housing_units = (
                _finite_number(housing.units_of(account_id)) if housing is not None else 0.0
            )
            housing_value = housing_units * house_price
            household_components["housing"] = housing_value
            total_assets = sum(household_components.values())
            household_agent = household_agents.get(str(account_id))
            items.append({
                "household_id": household_id,
                "account_id": str(account_id),
                "is_public_guardian": household_id == public_guardian_id,
                "member_count": len(member_rows),
                "assets": {**household_components, "total": total_assets},
                "debt": household_debt,
                "net_worth": total_assets - household_debt,
                "consumption": household_consumption,
                "income": household_income,
                "housing_units": housing_units,
                "desired_consumption": _finite_number(
                    getattr(household_agent, "consumption_budget", 0.0)
                ),
                "members": member_rows,
            })

        summary = {
            "household_count": len(items),
            "population": sum(int(item["member_count"]) for item in items),
            "total_assets": sum(float(item["assets"]["total"]) for item in items),
            "total_debt": sum(float(item["debt"]) for item in items),
            "total_net_worth": sum(float(item["net_worth"]) for item in items),
            "total_consumption": sum(float(item["consumption"]) for item in items),
        }
        return {
            "as_of_date": str(getattr(state, "current_date", "")),
            "summary": summary,
            "items": items,
        }

    def snapshot(self) -> dict[str, Any]:
        missing = set(self.session.missing_context_ids)
        contexts = [
            self.service.decision_context(context_id)
            for context_id in self.session.current_context_ids
            if context_id in missing
        ]
        latest_panel = self._panel_history[-1] if self._panel_history else {"tick": 0}
        metrics = {
            name: _finite_number(latest_panel.get(name))
            for name in PANEL_METRIC_NAMES
        }
        shock_engine = get_shock_engine(self.world)
        shock_events = []
        active_shocks = []
        if shock_engine is not None:
            shock_events = list(shock_engine.events.events[-20:])
            active_shocks = [
                spec.to_dict()
                for spec in shock_engine.specs
                if spec.intensity_at(self.session.boundary_tick) > 0
            ]
        # the DECISION is asynchronous: the coordinator emits a decision_* event
        # once the boundary collects every context -- surface the one matching
        # the player's latest proposal as last_verdict for the UI toast
        if getattr(self, "_pending_verdict_pid", None):
            for event in reversed(list(self.session.events.events)[-60:]):
                if (
                    isinstance(event, dict)
                    and str(event.get("event_type", "")).startswith("decision_")
                    and event.get("proposal_id") == self._pending_verdict_pid
                ):
                    decision_id = event.get("decision_id")
                    decision = self.session.coordinator.decisions.get(decision_id)
                    if decision is not None:
                        self._last_verdict = _jsonable(canonical_value(decision))
                    else:
                        self._last_verdict = {
                            "status": str(event.get("event_type"))
                            .removeprefix("decision_"),
                            "proposal_id": event.get("proposal_id"),
                            "decision_id": decision_id,
                            "reason_code": event.get("reason"),
                            "effective_tick": event.get("effective_tick"),
                        }
                    self._pending_verdict_pid = None
                    break
        latest_world = self._world_history[-1] if self._world_history else {}
        return {
            "protocol_version": PROTOCOL_VERSION,
            "observation": self._merged_observation(),
            "last_verdict": self._last_verdict,
            "tick": self.session.boundary_tick,
            "phase": self.session.phase,
            "awaiting_human": bool(self.session.missing_context_ids),
            "metrics": metrics,
            "series": list(self._panel_history),
            "panel_details": _jsonable(self._panel_details()),
            "households": _jsonable(self._household_snapshot()),
            "firms": _jsonable(self._firm_snapshot()),
            "world": {
                "countries": [
                    {"name": spec["name"], "latin": spec["latin"]}
                    for spec in COUNTRIES
                ],
                "player_economy": PLAYER_ECONOMY,
                "latest": _jsonable(latest_world),
                "history": _jsonable(self._world_history),
            },
            "contexts": contexts,
            "pending": self.service.pending(economy_id=PLAYER_ECONOMY),
            "shock_bulletins": self.service.shock_bulletins(
                economy_id=PLAYER_ECONOMY, seat="treasury"
            )["shock_bulletins"],
            "active_shocks": active_shocks,
            "events": list(self.session.events.events[-30:]),
            "shock_events": shock_events,
        }
