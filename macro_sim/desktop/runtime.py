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

# Compact per-economy series kept for every economy (world comparison charts).
WORLD_METRIC_NAMES = (
    "real_output",
    "unemployment_rate",
    "inflation",
    "price_index",
    "avg_wage",
    "policy_rate",
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
        base = Config.v124(
            n_households=80,
            n_firms_c=12,
            n_firms_k=4,
            n_ticks=100_000,
            seed=self._seed,
            energy_enabled=True,
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
            advanced += 1
            self._record_result(result.records)
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

    def _record_result(self, records: Any) -> None:
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
