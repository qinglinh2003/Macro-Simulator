"""Versioned new-game contract and the production desktop-game preset.

Historical ``Config.v*`` factories are research/calibration lineage.  The desktop
game instead composes every completed gameplay system explicitly so adding a new
module cannot silently leave it disabled in the player-facing build.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from datetime import date, timedelta
import hashlib
import math
import re
from typing import Any

from macro_sim.config import Config
from macro_sim.controllers.protocol import (
    canonical_json,
    canonical_value,
    immutable_json_mapping,
)
from macro_sim.core.policy_registry import REGISTRY
from macro_sim.shocks import (
    ShockTape,
    global_financial_crisis_scenario,
    natural_disaster_scenario,
    oil_embargo_scenario,
    pandemic_scenario,
)
from macro_sim.world.country import (
    ADVANCED,
    DEVELOPING,
    LAND_SCARCE_ENTREPOT,
    PETROSTATE,
    SYMMETRIC,
    CountryProfile,
)


NEW_GAME_SCHEMA_VERSION = 1
PLAYABLE_MODEL_ID = "current_playable_v1"
MAX_COUNTRIES = 8
MAX_DURATION_TICKS = (date.max - date.min).days

# This is intentionally a production preset, not another historical Config version.
# Policy instruments keep their neutral opening stance but every structural system
# needed to operate them is present.
PLAYABLE_FEATURE_OVERRIDES: dict[str, Any] = {
    # Complete firm/bank accounts and the v23 production foundation.
    "firm_full_pnl": True,
    "bank_realized_pnl": True,
    "bank_relationship_lock_in": True,
    "household_interest_arrears": True,
    "capital_service_pricing": True,
    "priced_firm_balance_sheet": True,
    "monetary_direct_transmission": True,
    "national_accounts_metrics": True,
    "cb_uses_fixed_basket_cpi": True,
    "fiscal_uses_national_accounts_gdp": True,
    "capital_annual_clock": True,
    "capital_clock_demand_smoothing": 0.5,
    "capital_service_min_utilization": 0.1,
    "cpi_item_link_cap": 5.0,
    "a_K": 2.4,
    # Households consume against a smoothed permanent-income estimate.  A high
    # propensity is therefore appropriate on the daily clock; 0.90 leaves a
    # persistent aggregate-demand leakage and 13-15% no-shock unemployment.
    "alpha1": 0.97,
    "p_firm0": 0.80,
    "p_kfirm0": 0.80,
    # Energy is an intermediate necessity with a different unit technology.
    # Its cost-consistent opening price is (1 + markup) * wage / productivity,
    # not the normalized final-goods price.
    "p_efirm0": 1.20,
    # Two weeks of downstream energy cover with a gradual replenishment rule
    # absorbs ordinary delivery noise without turning every stock drawdown into
    # a month-long hoarding wave.
    "energy_coverage_ticks": 14.0,
    "energy_gap_close": 0.02,
    # Genesis must start near the flow rate the available workforce can
    # sustain.  The historical ten-unit expectation scales to roughly 0.8
    # units per person and creates an artificial full-employment inventory
    # boom followed by mass suspensions.  At 6.25 units the aggregate opening
    # plan is close to the observed no-shock output rate.
    "demand_e_firm0": 6.25,
    # Inventory coverage is a stock measured in days.  Seed the same fourteen
    # days used by the production rule so firms do not spend their first
    # quarter manufacturing a missing genesis stock.  Both values scale with
    # representative-firm size in the native bridge.
    "inv_firm0": 87.5,
    "inv_kfirm0": 87.5,
    # Population dynamics, macro feedback and individual stratification.
    "demographics_enabled": True,
    "demographic_lifecycle_consumption": True,
    "fertility_income_elasticity": 0.06,
    "mortality_income_elasticity": 0.04,
    "mortality_rank_gradient": 0.8,
    "fertility_rank_gradient": 0.5,
    "marriage_assortativity": 1.0,
    "claims_reconcile_interval": 1,
    "ledger_rel_tol": 1.0e-8,
    # Housing registry, resale, credit, rent, construction and feedback channels.
    "housing_enabled": True,
    "housing_market_enabled": True,
    "mortgage_enabled": True,
    "mortgage_underwriting": True,
    "unified_bank_rwa": True,
    "housing_rental_enabled": True,
    "housing_construction_enabled": True,
    "builder_land_fee_credit": True,
    # A balanced genesis already owns one dwelling per household.  Seeding
    # construction demand in that state creates fractional projects and debt
    # without a corresponding buyer.  New building should start from uncovered
    # household demand instead.
    "builder_demand_seed": 0.0,
    # Listings can become cheaper than replacement cost, but an inhabited
    # economy should not drive the representative dwelling price toward zero
    # merely because an old listing remains unsold for several years.
    "housing_ask_floor_wage_share": 2.0,
    # A 3% monthly markdown compounds to almost 31% per year and turns normal
    # listing duration into a synthetic housing crash.  Half a percent per
    # session preserves price discovery without the mechanical ratchet.
    "housing_ask_decay": 0.005,
    "rental_vacancy_deadband": 0.15,
    "rental_rent_floor_wage_share": 0.02,
    "rental_eviction_arrears": 90,
    "housing_demand_step": 0.03,
    "housing_leave_elasticity": 1.0,
    "housing_fertility_elasticity": 0.5,
    "housing_wealth_effect": 0.1,
    # The complete persistent person-level labor grammar.
    "labor_matching": "persistent",
    "labor_fractional_hours": True,
    "labor_second_job": True,
    "labor_suspension": True,
    "labor_matching_friction": True,
    "labor_relationship_wages": True,
    "labor_job_ladder": True,
    "labor_person_efficiency": True,
    "labor_participation": True,
    "capital_rationed_signal": True,
    # Keep revealed consumer rationing available as an experiment, but do not
    # enable it in the stable baseline.  With daily ordering, transient genesis
    # stockouts otherwise become a persistent demand signal and create a
    # self-induced boom-bust cycle in an economy without an external shock.
    "consumption_rationed_signal": False,
    "firm_subscale_exit": True,
    "capital_firm_entry": True,
    # Daily-clock principal schedules: roughly 2.5-year business credit and
    # 5-year unsecured household credit.
    "amort": 1.0 / (365.0 * 2.5),
    "hh_amort": 1.0 / (365.0 * 5.0),
    # Energy, household necessity demand and demographic coupling.
    "energy_enabled": True,
    "energy_household": True,
    "energy_hoarding_beta": 1.0,
    "energy_mortality_gamma": 2.0,
    # Consumption strata, deprivation, private transfers and supply reallocation.
    "consumption_strata": True,
    "deprivation_gauges": True,
    "family_transfers": True,
    "sector_switching": True,
    # Product-line conversion is structural reallocation, not wholesale
    # destruction of an otherwise serviceable plant.  The historical 30% loss
    # turned a normal Engel-curve transition into a multi-year investment shock
    # at large population scale.
    "switch_retool_loss": 0.05,
    # Technology is live rather than a frozen object.
    "tfp_drift_rate": 0.02,
    # Long-run securities hygiene and the working-poor safety-net closure.
    "bond_maturity_bucket": 30,
    "gov_consumption_share": 0.20,
    "tax_income_rate": 0.25,
    "pension_replacement": 0.20,
    "benefit_income_floor": 0.0,
    "job_guarantee": False,
}

PERFORMANCE_PRESETS: dict[str, dict[str, int]] = {
    "fast": {
        "n_households": 80,
        "n_firms_c": 12,
        "n_firms_k": 4,
        "n_firms_e": 2,
        "n_banks": 2,
    },
    "standard": {
        "n_households": 200,
        "n_firms_c": 30,
        "n_firms_k": 10,
        "n_firms_e": 4,
        "n_banks": 4,
    },
}

# Legacy request/save tokens remain readable, but the normalized contract stores
# a finite duration as its exact number of simulation days (1 tick == 1 day).
DURATION_TICKS: dict[str, int | None] = {
    "1y": 365,
    "5y": 5 * 365,
    "10y": 10 * 365,
    "inf": None,
}

PROFILE_BY_ID: dict[str, CountryProfile] = {
    "symmetric": SYMMETRIC,
    "advanced": ADVANCED,
    "developing": DEVELOPING,
    "entrepot": LAND_SCARCE_ENTREPOT,
    "petrostate": PETROSTATE,
    "custom": SYMMETRIC,
}

SEAT_ALIASES = {
    "cb": "central_bank",
    "treasury": "treasury",
    "labor_social": "labor_social",
    "regulator": "regulator",
    "external": "external_affairs",
    "energy": "energy",
}

OCCUPANT_TYPES = frozenset(
    {"human", "null", "heuristic", "rl", "scheduled", "fuzz"}
)

CONFIG_OVERRIDE_FIELDS = frozenset({
    "n_households", "n_firms_c", "n_firms_k", "n_firms_e", "n_builders", "n_banks",
    "demographics_population",
    "a", "alpha", "tfp_law",
    "bank_enabled", "interbank", "bonds", "capital_market",
    "per_firm_equity", "household_credit",
    "housing_enabled", "housing_market_enabled", "mortgage_enabled",
    "housing_rental_enabled", "housing_construction_enabled",
    "demographics_enabled", "consumption_strata", "necessity_share0",
    "energy_enabled", "government", "national_accounts_metrics",
})

WORLD_NUMBER_FIELDS = frozenset({
    "fx_lambda", "fx_friction", "fx_trade_cap", "capital_mobility",
    "capital_adjust", "migration_rate", "migration_max_share",
    "remittance_share", "wage_smoothing", "peg_reserves0",
})

# Start-menu switches are capability choices, not raw dataclass writes.  Turning a
# parent off deterministically turns off its dependants so every visible switch
# produces a valid, playable structural variant.  Direct API callers still cannot
# smuggle these derived fields through the public override whitelist.
CAPABILITY_DISABLE_CASCADE: dict[str, dict[str, Any]] = {
    "housing_enabled": {
        "housing_market_enabled": False,
        "mortgage_enabled": False,
        "housing_rental_enabled": False,
        "housing_construction_enabled": False,
    },
    "housing_market_enabled": {
        "mortgage_enabled": False,
        "housing_rental_enabled": False,
        "housing_construction_enabled": False,
    },
    "mortgage_enabled": {
        "mortgage_underwriting": False,
    },
    "housing_rental_enabled": {
        "housing_leave_elasticity": 0.0,
        "housing_fertility_elasticity": 0.0,
    },
    "national_accounts_metrics": {
        "cb_uses_fixed_basket_cpi": False,
        "fiscal_uses_national_accounts_gdp": False,
    },
    "demographics_enabled": {
        "demographic_lifecycle_consumption": False,
        "demographic_marriage_enabled": False,
        "demographic_divorce_enabled": False,
        "demographic_adult_leaving_home_enabled": False,
        "labor_matching": "spot",
        "labor_fractional_hours": False,
        "labor_second_job": False,
        "labor_suspension": False,
        "labor_matching_friction": False,
        "labor_relationship_wages": False,
        "labor_job_ladder": False,
        "labor_person_efficiency": False,
        "labor_participation": False,
        "deprivation_gauges": False,
        "family_transfers": False,
        "energy_mortality_gamma": 0.0,
        "housing_leave_elasticity": 0.0,
        "housing_fertility_elasticity": 0.0,
    },
    "labor_fractional_hours": {
        "labor_second_job": False,
    },
    "labor_relationship_wages": {
        "labor_job_ladder": False,
    },
    "consumption_strata": {
        "family_transfers": False,
        "sector_switching": False,
    },
    "energy_enabled": {
        "energy_household": False,
        "energy_shock_at": 0,
        "spr_target_units": 0.0,
        "soe_efirm": False,
        "soe_price_at_cost": False,
        "energy_mortality_gamma": 0.0,
    },
    "per_firm_equity": {
        "equity_finance": False,
        "margin_credit": False,
        "pro_rata_dividends": False,
        "founder_owned_genesis": False,
        "household_bankruptcy": False,
    },
    "margin_credit": {
        "household_bankruptcy": False,
    },
    "bank_equity": {
        "bank_equity_trading": False,
        "bank_dynamics": False,
    },
    "firm_dynamics": {
        "per_firm_equity": False,
    },
    "capital_market": {
        "per_firm_equity": False,
        "bank_equity": False,
        "bank_equity_trading": False,
        "bank_dynamics": False,
    },
    "interbank": {
        "bank_runs": False,
        "omo": False,
        "lolr": False,
    },
    "bonds": {
        "omo": False,
        "lolr": False,
    },
    "government": {
        "bonds": False,
        "fiscal_uses_national_accounts_gdp": False,
        "gov_investment_share": 0.0,
        "job_guarantee": False,
        "housing_construction_enabled": False,
        "spr_target_units": 0.0,
        "soe_efirm": False,
        "soe_price_at_cost": False,
        "energy_cap_compensation": False,
    },
    "bank_enabled": {
        "bank_realized_pnl": False,
        "bank_relationship_lock_in": False,
        "bank_rate_competition": False,
        "bank_capital_constraint": False,
        "bank_equity": False,
        "bank_equity_trading": False,
        "bank_dynamics": False,
        "bank_runs": False,
        "household_interest_arrears": False,
        "monetary_direct_transmission": False,
        "mortgage_underwriting": False,
        "unified_bank_rwa": False,
        "central_bank": False,
        "cb_uses_fixed_basket_cpi": False,
        "government": False,
        "firm_dynamics": False,
        "interbank": False,
        "bonds": False,
        "household_credit": False,
        "per_firm_equity": False,
    },
}


def _structural_overrides(value: Mapping[str, Any]) -> dict[str, Any]:
    """Expand parent-off choices until their complete dependency closure is stable."""
    resolved = dict(value)
    changed = True
    while changed:
        changed = False
        for parent, dependants in CAPABILITY_DISABLE_CASCADE.items():
            if resolved.get(parent) is not False:
                continue
            for name, dependant_value in dependants.items():
                if resolved.get(name, object()) != dependant_value:
                    resolved[name] = dependant_value
                    changed = True
    return resolved


def _strict_int(name: str, value: Any, *, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def _text(name: str, value: Any, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{name} must contain 1..{maximum} characters")
    return normalized


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True)
class CountrySpec:
    name: str
    code: str
    profile: str
    overrides: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Any, *, index: int) -> "CountrySpec":
        if not isinstance(value, Mapping):
            raise TypeError(f"countries[{index}] must be an object")
        allowed = {"name", "code", "profile", "overrides", "color"}
        extra = set(value) - allowed
        if extra:
            raise ValueError(f"countries[{index}] has unknown fields {sorted(extra)}")
        name = _text(f"countries[{index}].name", value.get("name"), maximum=40)
        code = _text(f"countries[{index}].code", value.get("code"), maximum=5).upper()
        if re.fullmatch(r"[A-Z][A-Z0-9]{1,4}", code) is None:
            raise ValueError(f"countries[{index}].code must be 2..5 ASCII letters/digits")
        profile = value.get("profile")
        if profile not in PROFILE_BY_ID:
            raise ValueError(f"countries[{index}].profile is unknown")
        raw_overrides = value.get("overrides", {})
        if not isinstance(raw_overrides, Mapping):
            raise TypeError(f"countries[{index}].overrides must be an object")
        unknown = set(raw_overrides) - CONFIG_OVERRIDE_FIELDS
        if unknown:
            raise ValueError(
                f"countries[{index}].overrides has unsupported fields {sorted(unknown)}"
            )
        config_types = {item.name: item.type for item in fields(Config)}
        normalized: dict[str, Any] = {}
        for key, raw in raw_overrides.items():
            annotation = config_types[key]
            if annotation is bool or annotation == "bool":
                if not isinstance(raw, bool):
                    raise TypeError(f"countries[{index}].overrides.{key} must be boolean")
                normalized[key] = raw
            elif key == "tfp_law":
                if raw not in {"exogenous", "learning"}:
                    raise ValueError("tfp_law must be exogenous or learning")
                normalized[key] = raw
            elif key == "demographics_population":
                normalized[key] = _strict_int(
                    f"countries[{index}].overrides.{key}",
                    raw,
                    low=0,
                    high=10_000_000,
                )
            elif key in {
                "n_households", "n_firms_c", "n_firms_k",
                "n_firms_e", "n_builders", "n_banks",
            }:
                normalized[key] = _strict_int(
                    f"countries[{index}].overrides.{key}",
                    raw,
                    low=1,
                    high=10_000_000,
                )
            else:
                normalized[key] = _finite(
                    f"countries[{index}].overrides.{key}", raw
                )
        return cls(
            name=name,
            code=code,
            profile=str(profile),
            overrides=immutable_json_mapping(normalized),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "code": self.code,
            "profile": self.profile,
            "overrides": dict(self.overrides),
        }


@dataclass(frozen=True)
class NewGameSpec:
    schema_version: int
    model_id: str
    seed: int
    start_date: str
    scenario: str
    duration: int | None
    performance_scale: str
    world: Mapping[str, Any]
    countries: tuple[CountrySpec, ...]
    player_country: int
    run_mode: str
    seats: Mapping[str, str]
    initial_policy_overrides: Mapping[str, Any]

    @classmethod
    def default(cls, *, seed: int = 7) -> "NewGameSpec":
        return cls.from_mapping({
            "schema_version": NEW_GAME_SCHEMA_VERSION,
            "seed": seed,
            "start_date": "2000-01-01",
            "scenario": "sandbox",
            # Five Gregorian calendar years from the default genesis date.
            "duration": 1_827,
            "performance_scale": "fast",
            "world": {
                "trade": True,
                "capital": True,
                "migration": True,
                "fx_lambda": 0.05,
                "fx_friction": 0.03,
                "fx_trade_cap": 0.15,
                "capital_mobility": 1.0,
                "capital_adjust": 0.2,
                "migration_rate": 0.0005,
                "migration_max_share": 0.25,
                "remittance_share": 0.2,
                "wage_smoothing": 0.02,
                "peg_reserves0": 5000.0,
            },
            "countries": [
                {"name": "Aurelia", "code": "AUR", "profile": "advanced", "overrides": {}},
                {"name": "Borvia", "code": "BOL", "profile": "developing", "overrides": {}},
                {"name": "Petronia", "code": "PET", "profile": "petrostate", "overrides": {}},
            ],
            "player_country": 0,
            "run_mode": "interactive",
            "seats": {
                "treasury": "human",
                "cb": "human",
                "labor_social": "human",
                "regulator": "human",
                "external": "human",
                "energy": "human",
            },
            "initial_policy_overrides": {},
        })

    @classmethod
    def from_mapping(cls, value: Any) -> "NewGameSpec":
        if not isinstance(value, Mapping):
            raise TypeError("new_game spec must be an object")
        expected = {
            "schema_version", "seed", "scenario", "duration",
            "world", "countries", "player_country",
            "run_mode", "seats", "initial_policy_overrides",
        }
        allowed = expected | {"model_id", "start_date", "performance_scale"}
        if not expected <= set(value) or not set(value) <= allowed:
            raise ValueError(
                "new_game spec fields differ; "
                f"missing={sorted(expected - set(value))}, "
                f"extra={sorted(set(value) - allowed)}"
            )
        schema_version = _strict_int(
            "schema_version", value["schema_version"],
            low=NEW_GAME_SCHEMA_VERSION, high=NEW_GAME_SCHEMA_VERSION,
        )
        # model_id is response provenance, never a client-side selector.  Older
        # saved request envelopes may still echo it; every new run deliberately
        # resolves to the backend's current production model.
        seed = _strict_int("seed", value["seed"], low=0, high=2_147_483_647)
        raw_start_date = value.get("start_date", "2000-01-01")
        if not isinstance(raw_start_date, str):
            raise TypeError("start_date must be an ISO Gregorian date")
        try:
            parsed_start_date = date.fromisoformat(raw_start_date)
        except ValueError as exc:
            raise ValueError(
                "start_date must be an ISO Gregorian date (YYYY-MM-DD)"
            ) from exc
        start_date = parsed_start_date.isoformat()
        scenario = value["scenario"]
        if scenario not in {"sandbox", "oil", "gfc", "pandemic", "disaster"}:
            raise ValueError(f"unsupported scenario {scenario!r}")
        raw_duration = value["duration"]
        if raw_duration is None:
            duration = None
        elif isinstance(raw_duration, str):
            if raw_duration not in DURATION_TICKS:
                raise ValueError(f"unsupported duration {raw_duration!r}")
            duration = DURATION_TICKS[raw_duration]
        else:
            duration = _strict_int(
                "duration",
                raw_duration,
                low=1,
                high=MAX_DURATION_TICKS,
            )
        calendar_horizon = duration if duration is not None else 100_000
        try:
            parsed_start_date + timedelta(days=calendar_horizon)
        except OverflowError as exc:
            raise ValueError(
                "start_date plus duration exceeds the Gregorian calendar"
            ) from exc
        # New clients submit final agent counts per country.  This preset is
        # retained only as a fallback for legacy sparse manifests.
        performance_scale = value.get("performance_scale", "fast")
        if performance_scale not in PERFORMANCE_PRESETS:
            raise ValueError(f"unsupported performance scale {performance_scale!r}")

        raw_world = value["world"]
        if not isinstance(raw_world, Mapping):
            raise TypeError("world must be an object")
        expected_world = {"trade", "capital", "migration"} | set(WORLD_NUMBER_FIELDS)
        if set(raw_world) != expected_world:
            raise ValueError(
                "world fields differ; "
                f"missing={sorted(expected_world - set(raw_world))}, "
                f"extra={sorted(set(raw_world) - expected_world)}"
            )
        world: dict[str, Any] = {}
        for key in ("trade", "capital", "migration"):
            if not isinstance(raw_world[key], bool):
                raise TypeError(f"world.{key} must be boolean")
            world[key] = raw_world[key]
        for key in WORLD_NUMBER_FIELDS:
            world[key] = _finite(f"world.{key}", raw_world[key])

        raw_countries = value["countries"]
        if not isinstance(raw_countries, list):
            raise TypeError("countries must be an array")
        if not 1 <= len(raw_countries) <= MAX_COUNTRIES:
            raise ValueError(f"countries must contain 1..{MAX_COUNTRIES} entries")
        countries = tuple(
            CountrySpec.from_mapping(item, index=index)
            for index, item in enumerate(raw_countries)
        )
        if len({item.code for item in countries}) != len(countries):
            raise ValueError("country codes must be unique")
        player_country = _strict_int(
            "player_country", value["player_country"],
            low=0, high=len(countries) - 1,
        )
        run_mode = value["run_mode"]
        if run_mode not in {"interactive", "realtime", "batch"}:
            raise ValueError(f"unsupported run_mode {run_mode!r}")

        raw_seats = value["seats"]
        if not isinstance(raw_seats, Mapping):
            raise TypeError("seats must be an object")
        if set(raw_seats) != set(SEAT_ALIASES):
            raise ValueError("seats must assign all six policy institutions")
        seats: dict[str, str] = {}
        for alias, occupant in raw_seats.items():
            if occupant not in OCCUPANT_TYPES:
                raise ValueError(f"unknown occupant type {occupant!r} for {alias}")
            canonical_seat = SEAT_ALIASES[alias]
            if occupant == "rl" and canonical_seat != "treasury":
                raise ValueError(
                    "the built-in fiscal_stabilization_v1 RL policy is Treasury-only"
                )
            seats[canonical_seat] = str(occupant)
        if run_mode == "batch" and "human" in seats.values():
            raise ValueError("batch mode cannot contain human seats")

        raw_policy = value["initial_policy_overrides"]
        if not isinstance(raw_policy, Mapping):
            raise TypeError("initial_policy_overrides must be an object")
        policy = dict(canonical_value(dict(raw_policy)))
        for key in policy:
            parts = key.split(".", 2)
            if len(parts) != 3 or not parts[0].isdigit():
                raise ValueError(f"initial policy key {key!r} is not economy.seat.lever")
            economy_id = int(parts[0])
            if not 0 <= economy_id < len(countries):
                raise ValueError(f"initial policy key {key!r} targets an unknown country")
            if parts[1] not in SEAT_ALIASES:
                raise ValueError(f"initial policy key {key!r} has an unknown seat")
            if not parts[2]:
                raise ValueError(f"initial policy key {key!r} has an empty lever")
            lever = REGISTRY.get(parts[2])
            if lever is None:
                raise ValueError(f"initial policy key {key!r} names an unknown lever")
            if lever.owner_role != SEAT_ALIASES[parts[1]]:
                raise ValueError(
                    f"initial policy key {key!r} assigns a lever to the wrong seat"
                )

        return cls(
            schema_version=schema_version,
            model_id=PLAYABLE_MODEL_ID,
            seed=seed,
            start_date=start_date,
            scenario=str(scenario),
            duration=duration,
            performance_scale=str(performance_scale),
            world=immutable_json_mapping(world),
            countries=countries,
            player_country=player_country,
            run_mode=str(run_mode),
            seats=immutable_json_mapping(seats),
            initial_policy_overrides=immutable_json_mapping(policy),
        )

    @property
    def duration_ticks(self) -> int | None:
        return self.duration

    @property
    def contract_hash(self) -> str:
        return hashlib.sha256(
            canonical_json(self.to_dict()).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "seed": self.seed,
            "start_date": self.start_date,
            "scenario": self.scenario,
            "duration": self.duration,
            "performance_scale": self.performance_scale,
            "world": dict(self.world),
            "countries": [country.to_dict() for country in self.countries],
            "player_country": self.player_country,
            "run_mode": self.run_mode,
            "seats": {
                alias: self.seats[canonical]
                for alias, canonical in SEAT_ALIASES.items()
            },
            "initial_policy_overrides": dict(self.initial_policy_overrides),
        }

    def configs(self) -> list[Config]:
        scale = PERFORMANCE_PRESETS[self.performance_scale]
        ticks = self.duration_ticks or 100_000
        base = Config.v13(
            **PLAYABLE_FEATURE_OVERRIDES,
            **scale,
            n_ticks=ticks,
            seed=self.seed,
            simulation_start_date=self.start_date,
        )
        result: list[Config] = []
        for country in self.countries:
            profile = PROFILE_BY_ID[country.profile]
            cfg = profile.apply(base)
            if country.overrides:
                cfg = replace(cfg, **_structural_overrides(country.overrides))
            result.append(cfg)
        return result

    def shock_tape(self) -> ShockTape | None:
        if self.scenario == "sandbox":
            return None
        horizon = self.duration_ticks
        start_tick = 365 if horizon is None else min(365, max(30, horizon // 4))
        ids = tuple(range(len(self.countries)))
        if self.scenario == "oil":
            return oil_embargo_scenario(start_tick=start_tick, economy_ids=ids)
        if self.scenario == "gfc":
            return global_financial_crisis_scenario(
                start_tick=start_tick, economy_ids=ids
            )
        if self.scenario == "pandemic":
            return pandemic_scenario(
                start_tick=start_tick,
                duration_ticks=365,
                economy_ids=ids,
                include_trade=bool(self.world["trade"]),
            )
        return natural_disaster_scenario(start_tick=start_tick, economy_ids=ids)
