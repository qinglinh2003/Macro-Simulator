class_name M11FrontendAdapter
extends RefCounted

const SERIES_LIMIT := 160
const SEATS := [
	"treasury", "central_bank", "labor_social", "regulator",
	"external_affairs", "energy",
]

const METRIC_ALIASES := {
	"metric.economy.real_output": "real_output",
	"metric.economy.unemployment_rate": "unemployment_rate",
	"metric.economy.inflation": "inflation",
	"metric.economy.price_index": "price_index",
	"metric.economy.avg_wage": "avg_wage",
	"metric.economy.policy_rate": "policy_rate",
	"metric.economy.population_alive": "population_alive",
	"metric.economy.gov_debt_to_gdp": "gov_debt_to_gdp",
	"metric.economy.gov_deficit_to_gdp": "gov_deficit_to_gdp",
	"metric.economy.credit_to_gdp": "credit_to_gdp",
	"metric.economy.poverty_rate": "poverty_rate",
	"metric.economy.income_gini": "income_gini",
	"metric.economy.energy_price": "energy_price",
	"metric.economy.energy_stock_total": "energy_stock_total",
	"metric.economy.energy_unfilled": "energy_unfilled",
	"metric.world.e": "e",
	"metric.world.nfa": "nfa",
	"metric.world.current_account": "current_account",
	"metric.world.migrant_stock": "migrant_stock",
	"metric.world.remittances": "remittances",
	"metric.source.m4.household_consumption": "real_consumption",
	"metric.source.m4.fixed_capital_formation_nominal": "investment_spending",
	"metric.source.m4.aggregate_capital": "aggregate_capital",
	"metric.source.m4.total_money": "total_money",
	"metric.source.m4.tax_total": "tax_total",
	"metric.source.m4.government_spending": "gov_spending",
	"metric.source.m4.government_deficit": "gov_deficit",
	"metric.source.m4.transfer_payments": "benefit_paid",
	"metric.source.m4.government_consumption": "gov_consumption",
	"metric.source.m4.public_fixed_capital_formation": "public_investment",
	"metric.source.m5.total_loan_principal": "total_credit",
	"metric.source.m5.total_bank_capital": "bank_capital",
	"metric.source.m5.new_credit": "new_loans_total",
	"metric.source.m5.realized_credit_losses": "bank_realized_credit_losses",
	"metric.source.m5.realized_interbank_losses": "interbank_contagion_loss",
	"metric.source.m5.alive_banks": "banks_alive",
	"metric.source.m5.bank_failures": "n_bank_failures",
	"metric.source.m6.household_bankruptcies": "hh_bankruptcies",
	"metric.source.m6.firm_births": "births",
	"metric.source.m6.firm_exits": "deaths",
	"metric.source.m6.sector_retool_capital": "sector_switch_capital",
	"metric.source.m7.employed_fte": "labor_E",
	"metric.source.m7.employed_heads": "labor_employed_heads",
	"metric.source.m7.unemployment": "labor_U",
	"metric.source.m7.job_guarantee": "labor_JG",
	"metric.source.m7.out_of_labor_force": "labor_OLF",
	"metric.source.m7.vacancies": "vacancies_unfilled",
	"metric.source.m7.hires": "labor_hires_total",
	"metric.source.m7.separations": "labor_churn_seps_total",
	"metric.source.m7.mean_household_size": "avg_household_size",
	"metric.source.m7.births": "births_tick",
	"metric.source.m7.deaths": "deaths_tick",
	"metric.source.m7.marriages": "marriages_tick",
	"metric.source.m7.divorces": "divorces_tick",
	"metric.source.m8.energy.production": "energy_produced",
	"metric.source.m8.energy.sold": "energy_used",
	"metric.source.m8.energy.utilization": "e_capacity_utilization",
	"metric.source.m8.energy.strategic_reserve_stock": "spr_stock",
	"metric.source.m8.housing.housing_stock": "dwellings_total",
	"metric.source.m8.housing.homeownership_share": "homeowner_share",
	"metric.source.m8.housing.active_listings": "housing_listings",
	"metric.source.m8.housing.session_sales": "housing_sales_session",
	"metric.source.m8.housing.mean_time_on_market_days": "housing_tom",
	"metric.source.m8.housing.forced_listing_share": "housing_forced_share",
	"metric.source.m8.housing.mortgage_principal_outstanding":
		"mortgage_balance_total",
	"metric.source.m8.housing.mortgage_principal_originated":
		"mortgage_originated_tick",
	"metric.source.m8.housing.foreclosures": "foreclosures_total",
	"metric.source.m8.housing.price_to_income_ratio": "housing_pti_ratio",
	"metric.source.m8.housing.rent_burden_ratio": "rent_burden_ratio",
	"metric.source.m8.housing.property_tax_paid": "property_tax_paid",
	"metric.source.m8.housing.transfer_tax_paid": "transfer_tax_paid",
	"metric.source.m8.housing.dwellings_completed": "dwellings_built_total",
	"metric.source.m8.housing.permits_used": "permits_used_year",
	"metric.source.m8.housing.rent_paid": "rent_paid_total",
	"metric.source.m8.housing.evictions": "evictions_total",
	"metric.source.m9.country.imports_value": "import_value",
	"metric.source.m9.country.exports_volume": "export_delivered_volume",
	"metric.source.m9.country.tariff_revenue": "tariff_rev",
}

const NATIONAL_ACCOUNT_ALIASES := {
	"gdp_deflator": "gdp_deflator",
	"expenditure_reconciled_nominal": "gdp_nominal_expenditure_reconciled",
	"expenditure_reconciled_real": "gdp_real_expenditure_reconciled",
	"household_consumption_nominal": "gdp_nominal_household_consumption",
	"household_consumption_real": "gdp_real_household_consumption",
	"government_consumption_nominal": "gdp_nominal_government_consumption",
	"government_consumption_real": "gdp_real_government_consumption",
	"fixed_capital_formation_nominal": "gdp_nominal_fixed_capital_formation",
	"fixed_capital_formation_real": "gdp_real_fixed_capital_formation",
	"net_exports_nominal": "gdp_nominal_net_exports",
	"net_exports_real": "gdp_real_net_exports",
	"gross_output_consumption_nominal": "gdp_nominal_gross_output_c",
	"gross_output_capital_nominal": "gdp_nominal_gross_output_k",
	"gross_output_energy_nominal": "gdp_nominal_gross_output_e",
	"gross_output_housing_nominal": "gdp_nominal_gross_output_housing",
	"income_reconciled_nominal": "gdp_nominal_income_reconciled",
	"cash_operating_surplus_nominal":
		"gdp_nominal_accrued_gross_operating_surplus",
	"net_product_taxes_observed":
		"gdp_nominal_net_product_taxes_observed",
	"production_nominal": "gdp_nominal_production",
	"compensation_employees_nominal":
		"gdp_nominal_compensation_of_employees",
	"exports_nominal": "gdp_nominal_exports",
	"imports_nominal": "gdp_nominal_imports",
	"inventory_change_nominal": "gdp_nominal_inventory_change",
	"private_fixed_capital_formation_nominal":
		"gdp_nominal_private_fixed_capital_formation",
	"public_fixed_capital_formation_nominal":
		"gdp_nominal_public_fixed_capital_formation",
	"residential_fixed_capital_formation_nominal":
		"gdp_nominal_residential_fixed_capital_formation",
	"machinery_fixed_capital_formation_nominal":
		"gdp_nominal_machinery_fixed_capital_formation",
	"exports_real": "gdp_real_exports",
	"imports_real": "gdp_real_imports",
	"three_approach_raw_spread_share":
		"gdp_nominal_three_approach_raw_spread_share",
	"debt_service_to_nominal_gdp": "debt_service_to_nominal_gdp",
	"total_debt_service_to_nominal_gdp":
		"total_debt_service_to_nominal_gdp",
}

var _raw: Dictionary = {}
var _series: Array = []
var _world_history: Array = []
var _metadata: Dictionary = {}
var _submitted_spec: Dictionary = {}
var _households := {
	"summary": {}, "items": [], "complete": false,
}
var _firms := {
	"summary": {}, "items": [], "complete": false,
}
var _stock_market := {
	"summary": {}, "securities": [], "history": [],
}
var _entity_boundaries: Dictionary = {}
var _entity_rows: Dictionary = {}
var _entity_pages: Dictionary = {}
var _entity_scopes: Dictionary = {}


func reset(metadata: Dictionary, submitted_spec: Dictionary) -> void:
	_raw.clear()
	_series.clear()
	_world_history.clear()
	_metadata = metadata.duplicate(true)
	_submitted_spec = submitted_spec.duplicate(true)
	_households = {"summary": {}, "items": [], "complete": false}
	_firms = {"summary": {}, "items": [], "complete": false}
	_stock_market = {"summary": {}, "securities": [], "history": []}
	_entity_boundaries.clear()
	_entity_rows.clear()
	_entity_pages.clear()
	_entity_scopes.clear()


func schema_payload(result: Dictionary) -> Dictionary:
	var seats: Dictionary = {}
	for seat in SEATS:
		seats[seat] = {
			"schema_version": result.get("schema_version", 1),
			"economy_id": result.get("economy_id", 0),
			"seat": seat,
			"levers": [],
		}
	for raw_lever: Variant in result.get("levers", []):
		if not raw_lever is Dictionary:
			continue
		var lever := _normalize_lever(raw_lever as Dictionary)
		var owner := str(lever.get("owner_role", ""))
		if seats.has(owner):
			(seats[owner]["levers"] as Array).append(lever)
	return {
		"schema_version": result.get("schema_version", 1),
		"economy_id": result.get("economy_id", 0),
		"seat": "treasury",
		"control_mode": result.get("control_mode", "free_policy"),
		"seats": seats,
		"levers": seats["treasury"]["levers"],
	}


func apply_projection(projection: Dictionary) -> Dictionary:
	var mode := str(projection.get("mode", ""))
	if mode in ["full", "full_resync"]:
		_raw = (projection.get("snapshot", {}) as Dictionary).duplicate(true)
	elif mode == "delta":
		_apply_delta(projection.get("delta", {}))
	else:
		return legacy_snapshot()
	_record_history()
	return legacy_snapshot()


func apply_entity_result(result: Dictionary) -> Dictionary:
	var kind := str(result.get("kind", ""))
	var page: Dictionary = result.get("page", {})
	var boundary := int(page.get("boundary", result.get("boundary", -1)))
	if result.has("rows"):
		_entity_rows[kind] = (
			result.get("rows", []) as Array
		).duplicate(true)
		_entity_pages[kind] = page.duplicate(true)
		_entity_boundaries[kind] = boundary
		if result.has("firm_id"):
			_entity_scopes[kind] = int(result.get("firm_id", 0))
		elif result.has("household_id"):
			_entity_scopes[kind] = int(result.get("household_id", 0))
		else:
			_entity_scopes.erase(kind)
		if kind in [
			"households", "persons", "jobs", "firms",
			"household_persons", "household_jobs",
		]:
			_rebuild_households()
		if kind in [
			"firms", "persons", "jobs", "equities",
			"firm_persons", "firm_jobs",
		]:
			_rebuild_firms()
		if kind in ["equities", "firms", "banks"]:
			_rebuild_stock_market()
	return legacy_snapshot()


func entity_boundary(kind: String) -> int:
	return int(_entity_boundaries.get(kind, -1))


func entity_scope(kind: String) -> int:
	return int(_entity_scopes.get(kind, 0))


func apply_free_policy_state(state: Dictionary) -> Dictionary:
	if _raw.is_empty():
		return {}
	_raw["control_mode"] = "free_policy"
	_raw["free_policy"] = state.duplicate(true)
	return legacy_snapshot()


func legacy_snapshot() -> Dictionary:
	if _raw.is_empty():
		return {}
	var metrics := _metric_point(_raw.get("metrics", []))
	var policies: Dictionary = {}
	for raw_policy: Variant in _raw.get("policies", []):
		if raw_policy is Dictionary:
			var policy := raw_policy as Dictionary
			policies[str(policy.get("lever", ""))] = policy.get("value")
	for lever_name in policies:
		metrics[lever_name] = policies[lever_name]
	var releases: Array = []
	for raw_release: Variant in _raw.get("releases", []):
		if not raw_release is Dictionary:
			continue
		var release := (raw_release as Dictionary).duplicate(true)
		release["released_at_tick"] = release.get("released_at", 0)
		release["reference_end_tick"] = release.get("observed_at", 0)
		releases.append(release)
	var contexts: Array = []
	for raw_context: Variant in _raw.get("contexts", []):
		if raw_context is Dictionary \
				and (raw_context as Dictionary).get("answered_by_proposal") == null:
			contexts.append(_normalize_context(raw_context as Dictionary))
	var pending: Array = []
	for raw_pending: Variant in _raw.get("pending", []):
		if not raw_pending is Dictionary:
			continue
		var item := (raw_pending as Dictionary).duplicate(true)
		var proposal: Dictionary = item.get("proposal", {})
		var decision: Dictionary = item.get("decision", {})
		item["actions"] = proposal.get("actions", [])
		decision["effective_tick"] = decision.get("effective_at")
		decision["reserved_admin_cost"] = decision.get(
			"reserved_administrative_cost", 0.0)
		item["decision"] = decision
		pending.append(item)
	var events: Array = []
	for raw_event: Variant in _raw.get("public_events", []):
		if raw_event is Dictionary:
			var event := (raw_event as Dictionary).duplicate(true)
			event["boundary_tick"] = event.get("boundary", 0)
			events.append(event)
	var world := _world_snapshot()
	return {
		"protocol_version": 5,
		"model_id": _metadata.get("model_id", "native-latest"),
		"tick": _raw.get("boundary", 0),
		"boundary": _raw.get("boundary", 0),
		"phase": _raw.get("phase", "boundary_start"),
		"awaiting_human": _raw.get("awaiting_human", false),
		"control_mode": _raw.get("control_mode", "free_policy"),
		"free_policy": _raw.get("free_policy", {
			"enabled": true,
			"effective_tick": null,
			"actions": [],
		}),
		"metrics": metrics,
		"metric_values": _stable_metric_values(_raw.get("metrics", [])),
		"series": _series.duplicate(true),
		"panel_details": _panel_details(metrics),
		"policy_values": policies,
		"observation": {"releases": releases},
		"contexts": contexts,
		"pending": pending,
		"events": events,
		"event_log": events,
		"shock_bulletins": _raw.get("shock_bulletins", []),
		"capabilities": _all_capabilities(),
		"households": _households,
		"firms": _firms,
		"stock_market": _stock_market,
		"world": world,
		"new_game": {
			"schema_version": _metadata.get("schema_version", 0),
			"model_id": _metadata.get("model_id", "native-latest"),
			"spec": _submitted_spec,
			"duration_ticks": _metadata.get("duration_ticks"),
		},
	}


func _apply_delta(raw_delta: Variant) -> void:
	if not raw_delta is Dictionary or _raw.is_empty():
		_raw.clear()
		return
	var delta := raw_delta as Dictionary
	_raw["snapshot_id"] = delta.get("result_snapshot_id", "")
	_raw["snapshot_sequence"] = delta.get("result_sequence", 0)
	for key in [
		"boundary", "phase", "awaiting_human", "event_cursor",
		"release_cursor", "releases", "contexts", "pending", "shock_bulletins",
		"control_mode", "free_policy",
	]:
		if delta.has(key):
			_raw[key] = delta[key]
	_merge_by_key(_raw.get("metrics", []), delta.get("changed_metrics", []),
		"stable_id")
	_merge_by_key(_raw.get("policies", []), delta.get("changed_policies", []),
		"lever")
	_merge_by_key(_raw.get("economies", []), delta.get("changed_economies", []),
		"economy_id")
	var events: Array = _raw.get("public_events", [])
	for event in delta.get("appended_public_events", []):
		events.append(event)
	while events.size() > 1024:
		events.pop_front()
	_raw["public_events"] = events


func _merge_by_key(base_variant: Variant, changes_variant: Variant,
		key: String) -> void:
	if not base_variant is Array or not changes_variant is Array:
		return
	var base := base_variant as Array
	for raw_change: Variant in changes_variant as Array:
		if not raw_change is Dictionary:
			continue
		var change := raw_change as Dictionary
		var found := false
		for index in base.size():
			if base[index] is Dictionary \
					and (base[index] as Dictionary).get(key) == change.get(key):
				base[index] = change.duplicate(true)
				found = true
				break
		if not found:
			base.append(change.duplicate(true))


func _record_history() -> void:
	var point := _metric_point(_raw.get("metrics", []))
	point["tick"] = _raw.get("boundary", 0)
	point["boundary"] = _raw.get("boundary", 0)
	for raw_policy: Variant in _raw.get("policies", []):
		if raw_policy is Dictionary:
			point[str((raw_policy as Dictionary).get("lever", ""))] = \
				(raw_policy as Dictionary).get("value")
	_append_or_replace(_series, point)
	var world_point := _world_point()
	_append_or_replace(_world_history, world_point)


func _append_or_replace(history: Array, point: Dictionary) -> void:
	if not history.is_empty() \
			and int((history[-1] as Dictionary).get("tick", -1)) \
				== int(point.get("tick", -2)):
		history[-1] = point
	else:
		history.append(point)
	while history.size() > SERIES_LIMIT:
		history.pop_front()


func _world_snapshot() -> Dictionary:
	var countries: Array = []
	for index in (_metadata.get("countries", []) as Array).size():
		var country: Dictionary = _metadata.get("countries", [])[index]
		countries.append({
			"economy_id": index,
			"country_id": str(country.get("code", "")).to_lower(),
			"code": country.get("code", ""),
			"name": country.get("name", ""),
			"profile_id": country.get("profile", ""),
		})
	return {
		"countries": countries,
		"player_economy": _metadata.get("player_economy", 0),
		"latest": _world_history[-1] if not _world_history.is_empty() else {},
		"history": _world_history.duplicate(true),
	}


func _world_point() -> Dictionary:
	var result := {
		"tick": _raw.get("boundary", 0),
		"boundary": _raw.get("boundary", 0),
		"economies": [],
		"e": [], "nfa": [], "current_account": [],
		"migrant_stock": [], "remittances": [],
		"export_delivered_volume": [], "import_value": [],
	}
	for raw_economy: Variant in _raw.get("economies", []):
		if not raw_economy is Dictionary:
			continue
		var economy := raw_economy as Dictionary
		var point := _metric_point(economy.get("metrics", []))
		point["economy_id"] = economy.get("economy_id", 0)
		(result["economies"] as Array).append(point)
		for key in [
			"e", "nfa", "current_account", "migrant_stock", "remittances",
			"export_delivered_volume", "import_value",
		]:
			(result[key] as Array).append(float(point.get(key, 0.0)))
	return result


func _metric_point(entries_variant: Variant) -> Dictionary:
	var point: Dictionary = {}
	if not entries_variant is Array:
		return point
	for raw_metric: Variant in entries_variant as Array:
		if not raw_metric is Dictionary:
			continue
		var metric := raw_metric as Dictionary
		var stable_id := str(metric.get("stable_id", ""))
		var value: Variant = metric.get("value")
		if stable_id.is_empty() or value == null:
			continue
		point[stable_id] = value
		var alias := _metric_alias(stable_id)
		if not alias.is_empty():
			point[alias] = value
		_apply_compatibility_aliases(point, stable_id, value)
	var price_index := maxf(float(point.get("price_index", 0.0)), 0.000000001)
	point["real_wage"] = float(point.get("avg_wage", 0.0)) / price_index
	var employed := maxf(float(point.get("labor_E", 0.0)), 1.0)
	point["labor_productivity"] = float(point.get("real_output", 0.0)) / employed
	point["writeoffs"] = float(point.get(
		"writeoffs", point.get("bank_realized_credit_losses", 0.0)))
	point["new_loans"] = float(point.get(
		"new_loans", point.get("new_loans_total", 0.0)))
	point["bank_deaths"] = float(point.get(
		"bank_deaths", point.get("n_bank_failures", 0.0)))
	point["total_debt_service_ratio"] = float(point.get(
		"total_debt_service_ratio",
		point.get("total_debt_service_to_nominal_gdp", 0.0)))
	point["hh_wealth_gini_incl_equity"] = float(point.get(
		"hh_wealth_gini_incl_equity", point.get("hh_wealth_gini", 0.0)))
	point["fiscal_revenue_total"] = float(point.get("tax_total", 0.0)) \
		+ float(point.get("tariff_rev", 0.0))
	point["augmented_gov_spending"] = float(point.get("gov_spending", 0.0))
	point["energy_sold"] = float(point.get(
		"energy_sold", point.get("energy_used", 0.0)))
	point["energy_coverage_mean"] = float(point.get(
		"energy_coverage_mean",
		float(point.get("energy_stock_total", 0.0)) \
			/ maxf(1.0, float(point.get("energy_used", 0.0)))))
	return point


func _panel_details(metrics: Dictionary) -> Dictionary:
	return {
		"real_economy": {
			"sectors": _sector_details(metrics),
		},
		"labor": {
			"employment_sectors": _employment_sector_details(metrics),
			"states": _labor_state_details(metrics),
			"flows": _labor_flow_details(metrics),
			"participation_by_age": _age_participation_details(metrics),
		},
		"population": {
			"pyramid": _population_pyramid_details(metrics),
		},
		"capital_market": {
			"firms": _capital_market_firm_details(),
		},
		"distribution": {
			"income": _distribution_series(metrics, "income"),
			"wealth": _distribution_series(metrics, "wealth"),
			"consumption": _distribution_series(metrics, "consumption"),
		},
	}


func _apply_compatibility_aliases(
		point: Dictionary, stable_id: String, value: Variant) -> void:
	if stable_id == "metric.source.m5.realized_credit_losses":
		point["writeoffs"] = value
	elif stable_id == "metric.source.m5.bank_failures":
		point["bank_deaths"] = value
	elif stable_id == "metric.source.m5.new_credit":
		point["new_loans"] = value
	elif stable_id == "metric.source.m8.energy.sold":
		point["energy_sold"] = value


func _sector_details(metrics: Dictionary) -> Array:
	var rows: Array = []
	for sector: String in [
		"consumption", "capital", "energy", "construction",
	]:
		var produced_key: String = {
			"consumption": "consumption_output_real",
			"capital": "capital_output_real",
			"energy": "energy_produced",
			"construction": "construction_output",
		}[sector]
		rows.append({
			"sector_id": sector,
			"firm_count": float(metrics.get(
				"firm_count_%s" % (
					"c" if sector == "consumption" else (
						"k" if sector == "capital" else (
							"e" if sector == "energy" else "construction"))),
				0.0)),
			"produced": float(metrics.get(produced_key, 0.0)),
			"sales": float(metrics.get(
				"sector_%s_sales" % sector, 0.0)),
			"employment": float(metrics.get(
				"labor_sector_%s_fte" % sector, 0.0)),
		})
	return rows


func _employment_sector_details(metrics: Dictionary) -> Array:
	var rows: Array = []
	for sector: String in [
		"consumption", "capital", "energy", "construction",
	]:
		rows.append({
			"sector_id": sector,
			"value": float(metrics.get(
				"labor_sector_%s_fte" % sector, 0.0)),
		})
	if float(metrics.get("labor_JG", 0.0)) > 0.0:
		rows.append({
			"sector_id": "job_guarantee",
			"value": float(metrics.get("labor_JG", 0.0)),
		})
	return rows


func _labor_state_details(metrics: Dictionary) -> Array:
	return [
		{
			"state_id": "employed",
			"value": float(metrics.get("labor_employed_heads", 0.0)),
		},
		{
			"state_id": "searching_or_guaranteed",
			"value": float(metrics.get("labor_U", 0.0)) \
				+ float(metrics.get("labor_JG", 0.0)),
		},
		{
			"state_id": "out_of_labor_force",
			"value": float(metrics.get("labor_OLF", 0.0)),
		},
	]


func _labor_flow_details(metrics: Dictionary) -> Array:
	return [
		{
			"flow_id": "hires",
			"value": float(metrics.get("labor_hires_total", 0.0)),
		},
		{
			"flow_id": "recalls",
			"value": float(metrics.get("recalls", 0.0)),
		},
		{
			"flow_id": "job_changes",
			"value": float(metrics.get("job_to_job_moves", 0.0)),
		},
		{
			"flow_id": "separations",
			"value": float(metrics.get("labor_churn_seps_total", 0.0)),
		},
		{
			"flow_id": "layoffs_or_bankruptcy",
			"value": float(metrics.get("demand_layoff_separations", 0.0)) \
				+ float(metrics.get("cash_layoff_separations", 0.0)) \
				+ float(metrics.get("firm_exit_separations", 0.0)),
		},
		{
			"flow_id": "labor_force_exits",
			"value": float(metrics.get("retirement_separations", 0.0)) \
				+ float(metrics.get("death_separations", 0.0)),
		},
	]


func _age_participation_details(metrics: Dictionary) -> Array:
	var rows: Array = []
	for age_id: String in [
		"15_24", "25_34", "35_44", "45_54", "55_64", "65_plus",
	]:
		rows.append({
			"label_id": "age_%s" % age_id,
			"participation_rate": float(metrics.get(
				"age_%s_participation" % age_id, 0.0)),
			"employment_rate": float(metrics.get(
				"age_%s_employment" % age_id, 0.0)),
		})
	return rows


func _population_pyramid_details(metrics: Dictionary) -> Array:
	var rows: Array = []
	for age_id: String in [
		"0_14", "15_24", "25_34", "35_44", "45_54", "55_64",
		"65_plus",
	]:
		rows.append({
			"label_id": "age_%s" % age_id,
			"male": float(metrics.get(
				"pyramid_male_%s" % age_id, 0.0)),
			"female": float(metrics.get(
				"pyramid_female_%s" % age_id, 0.0)),
		})
	return rows


func _capital_market_firm_details() -> Array:
	var rows: Array = []
	for raw_item: Variant in _firms.get("items", []):
		if not raw_item is Dictionary:
			continue
		var item := raw_item as Dictionary
		var equity: Dictionary = item.get("equity", {})
		if not bool(equity.get("enabled", false)):
			continue
		var capital: Dictionary = item.get("capital", {})
		rows.append({
			"q": float(equity.get("tobin_q_ema", 0.0)),
			"investment": float(capital.get("units", 0.0)),
			"market_cap": float(equity.get("market_cap", 0.0)),
		})
	rows.sort_custom(func(left: Dictionary, right: Dictionary) -> bool:
		return float(left.get("market_cap", 0.0)) \
			> float(right.get("market_cap", 0.0)))
	if rows.size() > 64:
		rows.resize(64)
	return rows


func _distribution_series(metrics: Dictionary, prefix: String) -> Dictionary:
	var deciles: Array = []
	for decile in range(1, 11):
		var key := "%s_decile_%d_share" % [prefix, decile]
		if not metrics.has(key):
			return {}
		deciles.append(float(metrics[key]))
	var lorenz: Array = [0.0]
	var cumulative := 0.0
	for share: float in deciles:
		cumulative += share
		lorenz.append(cumulative)
	if cumulative > 0.000000001:
		for index in lorenz.size():
			lorenz[index] = float(lorenz[index]) / cumulative
	return {
		"deciles": deciles,
		"lorenz": lorenz,
	}


func _stable_metric_values(entries_variant: Variant) -> Dictionary:
	var values: Dictionary = {}
	if entries_variant is Array:
		for raw_metric: Variant in entries_variant as Array:
			if raw_metric is Dictionary:
				var metric := raw_metric as Dictionary
				values[str(metric.get("stable_id", ""))] = metric.get("value")
	return values


func _metric_alias(stable_id: String) -> String:
	if METRIC_ALIASES.has(stable_id):
		return str(METRIC_ALIASES[stable_id])
	if stable_id.begins_with("metric.economy.na."):
		var field := stable_id.trim_prefix("metric.economy.na.")
		return str(NATIONAL_ACCOUNT_ALIASES.get(field, "gdp_" + field))
	if stable_id.begins_with("metric.source.") \
			or stable_id.begins_with("metric.economy.") \
			or stable_id.begins_with("metric.world."):
		return stable_id.get_slice(".", stable_id.get_slice_count(".") - 1)
	return ""


func _normalize_context(raw: Dictionary) -> Dictionary:
	var context := raw.duplicate(true)
	context["admin_remaining"] = raw.get("administrative_remaining", 0.0)
	context["admin_reserved"] = raw.get("administrative_reserved", 0.0)
	context["admin_capacity"] = raw.get("administrative_capacity", 0.0)
	for raw_action: Variant in context.get("permitted_actions", []):
		if raw_action is Dictionary:
			var action := raw_action as Dictionary
			action["effective_tick"] = action.get("earliest_effective", 0)
	return context


func _contract_tokens(raw: Variant) -> Array:
	if raw is Array:
		return (raw as Array).duplicate()
	var tokens: Array = []
	for token: String in str(raw).split("|", false):
		var normalized := token.strip_edges()
		if not normalized.is_empty():
			tokens.append(normalized)
	return tokens


func _normalize_lever(raw: Dictionary) -> Dictionary:
	var lever := raw.duplicate(true)
	var source_kind := str(lever.get("value_kind", ""))
	if source_kind == "boolean":
		lever["value_kind"] = "bool"
	elif source_kind == "nullable_number":
		lever["value_kind"] = "number"
		lever["nullable"] = true
	lever["min_hold_ticks"] = lever.get("minimum_hold_ticks", 0)
	lever["max_step"] = lever.get("maximum_step")
	lever["admin_weight"] = lever.get("administrative_weight", 0.0)
	lever["requires"] = _contract_tokens(
		lever.get("required_capabilities", []))
	lever["enabled_if"] = _contract_tokens(lever.get("enabled_if", []))
	lever["nullable"] = bool(lever.get(
		"nullable", source_kind in ["nullable_number", "economy_id"]))
	return lever


func _cached_entity_rows(kind: String) -> Array:
	var rows: Variant = _entity_rows.get(kind, [])
	return rows as Array if rows is Array else []


func _cached_entity_page(kind: String) -> Dictionary:
	var page: Variant = _entity_pages.get(kind, {})
	return page as Dictionary if page is Dictionary else {}


func _entity_index(kind: String) -> Dictionary:
	var index: Dictionary = {}
	for raw_row: Variant in _cached_entity_rows(kind):
		if raw_row is Dictionary:
			var row := raw_row as Dictionary
			index[int(row.get("id", 0))] = row
	return index


func _entity_id_value(value: Variant) -> int:
	return int(value) if value != null else 0


func _positive_id(value: Variant) -> Variant:
	var entity_id := _entity_id_value(value)
	return entity_id if entity_id > 0 and entity_id < 4294967295 else null


func _entity_date_label(boundary: int) -> String:
	var start_date := str(_submitted_spec.get("start_date", ""))
	if not start_date.is_empty():
		var start_unix := Time.get_unix_time_from_datetime_string(
			start_date + "T00:00:00")
		return Time.get_date_string_from_unix_time(
			int(start_unix) + boundary * 86400)
	return "Y%d · D%d" % [boundary / 365 + 1, boundary % 365 + 1]


func _person_labor_state(person: Dictionary, jobs: Array) -> String:
	var age := int(person.get("age_days", 0)) / 365
	if age < 15:
		return "minor"
	for job: Dictionary in jobs:
		if bool(job.get("active", false)) and not bool(
				job.get("suspended", false)):
			return "employed"
	if bool(person.get("searching", false)):
		return "searching"
	if age >= 65:
		return "retirement_age"
	return "not_in_labor_force"


func _person_relationship(
		person: Dictionary, household_people: Dictionary,
		head_id: int) -> String:
	var person_id := int(person.get("id", 0))
	var age := int(person.get("age_days", 0)) / 365
	var mother_id := _entity_id_value(person.get("mother_id", 0))
	var father_id := _entity_id_value(person.get("father_id", 0))
	var partner_id := _entity_id_value(person.get("partner_id", 0))
	var guardian_id := _entity_id_value(person.get("guardian_id", 0))
	if mother_id > 0 and household_people.has(mother_id) \
			or father_id > 0 and household_people.has(father_id):
		return "child"
	if partner_id > 0 and household_people.has(partner_id) \
			and person_id != head_id:
		return "partner"
	if guardian_id > 0 and household_people.has(guardian_id):
		return "ward"
	return "minor_member" if age < 18 else "adult_member"


func _employment_projection(
		job: Dictionary, firms_by_id: Dictionary) -> Dictionary:
	var firm_id := int(job.get("firm_id", 0))
	var firm: Dictionary = firms_by_id.get(firm_id, {})
	return {
		"job_id": job.get("id", 0),
		"firm_id": firm_id,
		"sector_id": firm.get("sector", "unknown"),
		"contract_id": (
			"secondary" if bool(job.get("secondary", false)) else "primary"
		),
		"status_id": (
			"separated" if not bool(job.get("active", false))
			else "suspended" if bool(job.get("suspended", false))
			else "active"
		),
		"hours": job.get("hours", 0.0),
		"wage": job.get("wage", 0.0),
		"contract_hours": job.get("hours", 0.0),
		"locked_wage": job.get("wage", 0.0),
		"paid_wage": null,
		"compensation": null,
		"hire_day": job.get("hire_day", 0),
		"separation_day": job.get("separation_day", -1),
		"suspended_since_tick": (
			job.get("suspension_day")
			if int(job.get("suspension_day", -1)) >= 0
			else null
		),
		"suspension_wage": null,
	}


func _person_projection(
		person: Dictionary, household_people: Dictionary, head_id: int,
		jobs: Array, firms_by_id: Dictionary) -> Dictionary:
	var employers: Array = []
	var labor_income := 0.0
	for job: Dictionary in jobs:
		if not bool(job.get("active", false)):
			continue
		employers.append(_employment_projection(job, firms_by_id))
		if not bool(job.get("suspended", false)):
			labor_income += float(job.get("wage", 0.0)) * float(
				job.get("hours", 0.0))
	var allocated_income := float(person.get("allocated_income", 0.0))
	var gross_assets := float(person.get("gross_assets", 0.0))
	var person_id := int(person.get("id", 0))
	return {
		"person_id": person_id,
		"sex_id": str(person.get("sex", "unknown")),
		"age": int(person.get("age_days", 0)) / 365,
		"age_days": person.get("age_days", 0),
		"birth_day": person.get("birth_day", 0),
		"birth_date": _entity_date_label(int(person.get("birth_day", 0))),
		"death_day": person.get("death_day", -1),
		"mother_id": _positive_id(person.get("mother_id", 0)),
		"father_id": _positive_id(person.get("father_id", 0)),
		"partner_id": _positive_id(person.get("partner_id", 0)),
		"guardian_id": _positive_id(person.get("guardian_id", 0)),
		"relationship_id": _person_relationship(
			person, household_people, head_id),
		"marital_status_id": (
			"partnered" if _entity_id_value(
				person.get("partner_id", 0)) > 0
			else "unpartnered"
		),
		"labor_status_id": _person_labor_state(person, jobs),
		"participating": person.get("participating", false),
		"searching": person.get("searching", false),
		"efficiency": person.get("efficiency", 0.0),
		"assets": {
			"cash": person.get("cash", 0.0),
			"firm_equity": person.get("firm_equity", 0.0),
			"bank_equity": person.get("bank_equity", 0.0),
			"bonds": person.get("bonds", 0.0),
			"total": gross_assets,
		},
		"debt": person.get("debt", 0.0),
		"net_worth": person.get("net_worth", gross_assets),
		"income": {
			"labor": labor_income,
			"capital": maxf(0.0, allocated_income - labor_income),
			"transfer": 0.0,
			"total": allocated_income,
		},
		"consumption": person.get("allocated_consumption", 0.0),
		"employers": employers,
	}


func _rebuild_households() -> void:
	if not _entity_rows.has("households"):
		return
	_apply_household_rows(
		_cached_entity_rows("households"),
		_cached_entity_page("households"))


func _apply_household_rows(rows_variant: Variant, page: Dictionary) -> void:
	var items: Array = []
	var total_assets := 0.0
	var total_debt := 0.0
	var population := 0
	var persons_by_household: Dictionary = {}
	for person_kind: String in ["persons", "household_persons"]:
		for raw_person: Variant in _cached_entity_rows(person_kind):
			if not raw_person is Dictionary:
				continue
			var person := raw_person as Dictionary
			var household_id := int(person.get("household_id", 0))
			if household_id <= 0:
				continue
			if not persons_by_household.has(household_id):
				persons_by_household[household_id] = {}
			(persons_by_household[household_id] as Dictionary)[
				int(person.get("id", 0))
			] = person
	var jobs_by_person: Dictionary = {}
	for job_kind: String in ["jobs", "household_jobs"]:
		for raw_job: Variant in _cached_entity_rows(job_kind):
			if not raw_job is Dictionary:
				continue
			var job := raw_job as Dictionary
			var person_id := int(job.get("person_id", 0))
			if person_id <= 0:
				continue
			if not jobs_by_person.has(person_id):
				jobs_by_person[person_id] = {}
			(jobs_by_person[person_id] as Dictionary)[
				int(job.get("id", 0))
			] = job
	var firms_by_id := _entity_index("firms")
	if rows_variant is Array:
		for raw_row: Variant in rows_variant as Array:
			if not raw_row is Dictionary:
				continue
			var row := raw_row as Dictionary
			var cash := float(row.get("cash", 0.0))
			var debt := float(row.get("debt", 0.0))
			var member_count := int(row.get("member_count", 0))
			var household_id := int(row.get("id", 0))
			var raw_members: Array = (
				persons_by_household.get(household_id, {}) as Dictionary
			).values()
			raw_members.sort_custom(func(left: Dictionary, right: Dictionary) -> bool:
				return int(left.get("id", 0)) < int(right.get("id", 0)))
			var household_people: Dictionary = {}
			var head_id := 0
			var head_age := -1
			for member: Dictionary in raw_members:
				var person_id := int(member.get("id", 0))
				household_people[person_id] = member
				var age_days := int(member.get("age_days", 0))
				if age_days > head_age:
					head_age = age_days
					head_id = person_id
			var members: Array = []
			var assets := {
				"cash": 0.0,
				"firm_equity": 0.0,
				"bank_equity": 0.0,
				"bonds": 0.0,
				"total": 0.0,
			}
			for member: Dictionary in raw_members:
				var person_id := int(member.get("id", 0))
				var member_jobs: Array = (
					jobs_by_person.get(person_id, {}) as Dictionary
				).values()
				var projected := _person_projection(
					member, household_people, head_id,
					member_jobs, firms_by_id)
				members.append(projected)
				var member_assets: Dictionary = projected.get("assets", {})
				for asset_key in assets:
					assets[asset_key] = float(assets[asset_key]) + float(
						member_assets.get(asset_key, 0.0))
			if members.is_empty():
				assets["cash"] = cash
				assets["total"] = cash
			total_assets += float(assets["total"])
			total_debt += debt
			population += member_count
			items.append({
		"household_id": household_id,
				"account_id": row.get("account_id", 0),
				"member_count": member_count,
				"members": members,
				"members_loaded": members.size(),
				"assets": assets,
				"debt": debt,
				"net_worth": float(assets["total"]) - debt,
				"income": row.get("income_realized", 0.0),
				"consumption": row.get("spent", 0.0),
				"labor_sold": row.get("labor_sold", 0.0),
			})
	_households = {
		"summary": {
			"household_count": page.get("total_rows", items.size()),
			"population": population,
			"total_assets": total_assets,
			"total_debt": total_debt,
		},
		"items": items,
		"complete": not bool(page.get("has_more", false)),
		"as_of_date": _entity_date_label(int(page.get("boundary", 0))),
	}


func _rebuild_firms() -> void:
	if not _entity_rows.has("firms"):
		return
	_apply_firm_rows(
		_cached_entity_rows("firms"),
		_cached_entity_page("firms"))


func _apply_firm_rows(rows_variant: Variant, page: Dictionary) -> void:
	var items: Array = []
	var employment := 0.0
	var revenue := 0.0
	var earnings := 0.0
	var persons_by_id := _entity_index("persons")
	var firm_persons := _entity_index("firm_persons")
	for person_id: Variant in firm_persons:
		persons_by_id[person_id] = firm_persons[person_id]
	var equities_by_issuer: Dictionary = {}
	for raw_equity: Variant in _cached_entity_rows("equities"):
		if not raw_equity is Dictionary:
			continue
		var equity := raw_equity as Dictionary
		if str(equity.get("issuer_kind", "")) == "firm":
			equities_by_issuer[int(equity.get(
				"issuer_owner_id", 0))] = equity
	var jobs_by_firm: Dictionary = {}
	var jobs_by_id := _entity_index("jobs")
	var firm_jobs := _entity_index("firm_jobs")
	for job_id: Variant in firm_jobs:
		jobs_by_id[job_id] = firm_jobs[job_id]
	for raw_job: Variant in jobs_by_id.values():
		if not raw_job is Dictionary:
			continue
		var job := raw_job as Dictionary
		var firm_id := int(job.get("firm_id", 0))
		if firm_id <= 0:
			continue
		if not jobs_by_firm.has(firm_id):
			jobs_by_firm[firm_id] = []
		(jobs_by_firm[firm_id] as Array).append(job)
	if rows_variant is Array:
		for raw_row: Variant in rows_variant as Array:
			if not raw_row is Dictionary:
				continue
			var row := raw_row as Dictionary
			var firm_id := int(row.get("id", 0))
			var employee_count := int(row.get("employee_count", 0))
			var sales := float(row.get("previous_sales", 0.0))
			var price := float(row.get("posted_price", 0.0))
			var row_revenue := sales * price
			var row_earnings := float(row.get("earnings", 0.0))
			var cash := float(row.get("cash", 0.0))
			var debt := float(row.get("debt", 0.0))
			var capital := float(row.get("physical_capital", 0.0))
			var inventory := float(row.get("goods_inventory", 0.0))
			var employees: Array = []
			var employment_fte := 0.0
			var active_heads: Dictionary = {}
			for job: Dictionary in jobs_by_firm.get(firm_id, []):
				if not bool(job.get("active", false)):
					continue
				var person_id := int(job.get("person_id", 0))
				var person: Dictionary = persons_by_id.get(person_id, {})
				var projected := _employment_projection(
					job, {firm_id: row})
				projected["person_id"] = person_id
				projected["household_id"] = _positive_id(
					person.get("household_id", 0))
				projected["sex_id"] = person.get("sex", "unknown")
				projected["age"] = int(person.get("age_days", 0)) / 365 \
					if not person.is_empty() else null
				projected["efficiency"] = person.get("efficiency", 0.0)
				employees.append(projected)
				active_heads[person_id] = true
				if not bool(job.get("suspended", false)):
					employment_fte += float(job.get("hours", 0.0))
			employment += employee_count
			revenue += row_revenue
			earnings += row_earnings
			var equity_row: Dictionary = equities_by_issuer.get(firm_id, {})
			var share_price := float(equity_row.get(
				"price", row.get("share_price", 0.0)))
			var last_share_price := float(equity_row.get(
				"last_price", row.get("last_share_price", 0.0)))
			var outstanding_shares := float(equity_row.get(
				"outstanding_shares", row.get("outstanding_shares", 0.0)))
			items.append({
				"firm_id": firm_id,
				"sector_id": row.get("sector", "unknown"),
				"condition_id": "operating" if bool(
					row.get("active", false)) else "exited",
				"operations": {
					"revenue": row_revenue,
					"earnings": row_earnings,
					"sales": sales,
					"price": price,
					"wage": row.get("posted_wage", 0.0),
					"markup": row.get("markup", 0.0),
					"demand_expected": row.get("demand_expected", 0.0),
					"inventory": inventory,
				},
				"labor": {
					"employment_fte": (
						employment_fte
						if not employees.is_empty()
						else float(employee_count)
					),
					"active_heads": (
						active_heads.size()
						if not employees.is_empty()
						else employee_count
					),
					"contract_count": (
						employees.size()
						if not employees.is_empty()
						else employee_count
					),
					"employees": employees,
				},
				"capital": {
					"units": capital,
				},
				"balance_sheet": {
					"cash": cash,
					"debt": debt,
					"capital_value": capital,
					"output_inventory_value": inventory * price,
					"gross_assets": cash + capital + inventory * price,
					"book_equity": row.get("book_equity", 0.0),
					"interest_arrears": row.get("interest_arrears", 0.0),
					"eligible_collateral_value":
						row.get("eligible_collateral_value", 0.0),
					"borrowing_base_headroom":
						row.get("borrowing_base_headroom", 0.0),
				},
				"pnl": {
					"revenue": row_revenue,
					"net_income": row_earnings,
					"interest_arrears": row.get("interest_arrears", 0.0),
				},
				"equity": {
					"enabled": _entity_id_value(equity_row.get(
						"id", row.get("equity_id", 0))) > 0,
					"equity_id": equity_row.get(
						"id", row.get("equity_id", 0)),
					"shares_outstanding": outstanding_shares,
					"share_price": share_price,
					"last_share_price": last_share_price,
					"market_cap": share_price * outstanding_shares,
					"fundamental_per_share":
						equity_row.get(
							"fundamental",
							row.get("fundamental_per_share", 0.0)),
					"tobin_q_ema": row.get("tobin_q_ema", 0.0),
					"share_trend": equity_row.get(
						"trend", row.get("share_trend", 0.0)),
				},
				"parameters": {
					"labor_productivity": row.get("productivity", 0.0),
					"tfp": row.get("total_factor_productivity", 0.0),
				},
				"signals": {
					"previous_sales": sales,
					"previous_hiring": row.get("previous_hires", 0.0),
					"insolvent_ticks": row.get("insolvent_days", 0),
					"sector_switch_pressure":
						row.get("sector_switch_pressure_days", 0),
				},
			})
	_firms = {
		"summary": {
			"firm_count": page.get("total_rows", items.size()),
			"employment_fte": employment,
			"total_revenue": revenue,
			"total_earnings": earnings,
		},
		"items": items,
		"complete": not bool(page.get("has_more", false)),
		"as_of_date": _entity_date_label(int(page.get("boundary", 0))),
	}


func _rebuild_stock_market() -> void:
	if not _entity_rows.has("equities"):
		return
	_apply_equity_rows(
		_cached_entity_rows("equities"),
		_cached_entity_page("equities"))


func _apply_equity_rows(rows_variant: Variant, page: Dictionary) -> void:
	var listings: Array = []
	var market_cap := 0.0
	var corporate_market_cap := 0.0
	var bank_market_cap := 0.0
	var advances := 0
	var declines := 0
	var unchanged := 0
	var q_sum := 0.0
	var q_count := 0
	var firms_by_id := _entity_index("firms")
	var banks_by_id := _entity_index("banks")
	var sector_totals: Dictionary = {}
	if rows_variant is Array:
		for raw_row: Variant in rows_variant as Array:
			if not raw_row is Dictionary:
				continue
			var row := raw_row as Dictionary
			var price := float(row.get("price", 0.0))
			var previous := float(row.get("last_price", price))
			var change := 0.0 if absf(previous) < 0.000000001 \
				else price / previous - 1.0
			if change > 0.0000001:
				advances += 1
			elif change < -0.0000001:
				declines += 1
			else:
				unchanged += 1
			var capitalization := price * float(
				row.get("outstanding_shares", 0.0))
			market_cap += capitalization
			var issuer_kind := str(row.get("issuer_kind", "firm"))
			var issuer_id := int(row.get("issuer_owner_id", 0))
			var issuer: Dictionary = (
				banks_by_id.get(issuer_id, {})
				if issuer_kind == "bank"
				else firms_by_id.get(issuer_id, {})
			)
			var sector_id := (
				"banking" if issuer_kind == "bank"
				else str(issuer.get("sector", "unknown"))
			)
			var book_value := float(
				issuer.get(
					"closing_capital" if issuer_kind == "bank"
					else "book_equity",
					0.0))
			var price_to_book: Variant = (
				capitalization / book_value
				if book_value > 0.000000001 else null
			)
			var tobin_q: Variant = (
				null if issuer_kind == "bank"
				else issuer.get("tobin_q_ema")
			)
			if tobin_q != null:
				q_sum += float(tobin_q)
				q_count += 1
			if issuer_kind == "bank":
				bank_market_cap += capitalization
			else:
				corporate_market_cap += capitalization
			if not sector_totals.has(sector_id):
				sector_totals[sector_id] = {
					"market_cap": 0.0,
					"weighted_change": 0.0,
					"count": 0,
				}
			var sector_total: Dictionary = sector_totals[sector_id]
			sector_total["market_cap"] = float(
				sector_total["market_cap"]) + capitalization
			sector_total["weighted_change"] = float(
				sector_total["weighted_change"]) + change * maxf(
					capitalization, 0.000000001)
			sector_total["count"] = int(sector_total["count"]) + 1
			listings.append({
				"symbol": (
					"BNK%04d" if issuer_kind == "bank" else "F%04d"
				) % issuer_id,
				"security_id": row.get("id", 0),
				"issuer_kind_id": issuer_kind,
				"issuer_id": issuer_id,
				"can_open_firm": issuer_kind == "firm",
				"instrument_type": (
					"bank" if issuer_kind == "bank" else "company"
				),
				"sector_id": sector_id,
				"condition_id": (
					"delisted" if not bool(row.get("active", false))
					else "solvency_risk" if bool(
						issuer.get(
							"resolved" if issuer_kind == "bank"
							else "defaulted",
							false))
					else "trading"
				),
				"price": price,
				"last_price": previous,
				"change": change,
				"market_cap": capitalization,
				"shares": row.get("outstanding_shares", 0.0),
				"fundamental": row.get("fundamental", 0.0),
				"tobin_q": tobin_q,
				"price_to_book": price_to_book,
				"window_low": minf(price, previous),
				"window_high": maxf(
					maxf(price, previous),
					float(row.get("peak_price", price))),
				"fundamental_gap": (
					0.0 if absf(float(row.get("fundamental", 0.0))) \
						< 0.000000001
					else price / float(row.get("fundamental", 0.0)) - 1.0
				),
			})
	var daily_return := 0.0
	if not listings.is_empty():
		for listing: Dictionary in listings:
			daily_return += float(listing.get("change", 0.0))
		daily_return /= float(listings.size())
	var boundary := int(page.get("boundary", _raw.get("boundary", 0)))
	var previous_history: Array = (
		_stock_market.get("history", []) as Array
	).duplicate(true)
	var prices: Dictionary = {}
	for listing: Dictionary in listings:
		prices[str(listing.get("symbol", ""))] = listing.get("price", 0.0)
	var prices_by_tick: Dictionary = {}
	for old_point: Dictionary in previous_history:
		prices_by_tick[int(old_point.get("tick", -1))] = (
			old_point.get("prices", {}) as Dictionary).duplicate(true)
	prices_by_tick[boundary] = prices
	var history: Array = []
	var baseline_cap := 0.0
	for series_point: Dictionary in _series:
		var aggregate_cap := float(series_point.get(
			"equity_market_cap", 0.0))
		if aggregate_cap <= 0.000000001:
			continue
		if baseline_cap <= 0.000000001:
			baseline_cap = aggregate_cap
		var point_tick := int(series_point.get("tick", 0))
		history.append({
			"tick": point_tick,
			"index_level": 1000.0 * aggregate_cap / baseline_cap,
			"prices": prices_by_tick.get(point_tick, {}),
		})
	if history.is_empty():
		history = previous_history
		while not history.is_empty() and int(
				(history[-1] as Dictionary).get("tick", -1)) >= boundary:
			history.pop_back()
		var base_index := (
			float((history[-1] as Dictionary).get(
				"index_level", 1000.0))
			if not history.is_empty() else 1000.0
		)
		history.append({
			"tick": boundary,
			"index_level": base_index * (1.0 + daily_return),
			"prices": prices,
		})
	elif int((history[-1] as Dictionary).get("tick", -1)) == boundary:
		(history[-1] as Dictionary)["prices"] = prices
	elif market_cap > 0.000000001:
		history.append({
			"tick": boundary,
			"index_level": 1000.0 * market_cap / baseline_cap,
			"prices": prices,
		})
	if history.size() > SERIES_LIMIT:
		history = history.slice(history.size() - SERIES_LIMIT)
	var index_level := float(
		(history[-1] as Dictionary).get("index_level", 1000.0)
	) if not history.is_empty() else 1000.0
	if history.size() >= 2:
		var previous_index := float(
			(history[-2] as Dictionary).get("index_level", index_level))
		if absf(previous_index) > 0.000000001:
			daily_return = index_level / previous_index - 1.0
	var sectors: Array = []
	for sector_id: String in sector_totals:
		var sector_total: Dictionary = sector_totals[sector_id]
		var sector_cap := float(sector_total.get("market_cap", 0.0))
		sectors.append({
			"sector_id": sector_id,
			"market_cap": sector_cap,
			"change": (
				float(sector_total.get("weighted_change", 0.0)) / sector_cap
				if sector_cap > 0.000000001 else 0.0
			),
			"listed_count": sector_total.get("count", 0),
		})
	sectors.sort_custom(func(left: Dictionary, right: Dictionary) -> bool:
		return float(left.get("market_cap", 0.0)) \
			> float(right.get("market_cap", 0.0)))
	var current_metrics := _metric_point(_raw.get("metrics", []))
	var turnover := 0.0
	if market_cap > 0.000000001:
		turnover = float(current_metrics.get(
			"equity_turnover", 0.0)) / market_cap
	_stock_market = {
		"index_name": "ALL-SHARE",
		"summary": {
			"index_level": index_level,
			"index_change": daily_return,
			"market_cap": market_cap,
			"corporate_market_cap": corporate_market_cap,
			"bank_market_cap": bank_market_cap,
			"listed_count": page.get("total_rows", listings.size()),
			"turnover": turnover,
			"advances": advances,
			"declines": declines,
			"unchanged": unchanged,
			"q_mean": current_metrics.get(
				"tobin_q_mean",
				q_sum / float(q_count) if q_count > 0 else null),
			"ownership_gini": current_metrics.get(
				"equity_ownership_gini"),
			"equity_wealth_share": current_metrics.get(
				"equity_wealth_share"),
		},
		"listings": listings,
		"history": history,
		"sectors": sectors,
		"as_of_date": _entity_date_label(boundary),
	}


func _all_capabilities() -> Dictionary:
	return {
		"national_accounts_metrics": true,
		"demographics_enabled": true,
		"housing_enabled": true,
		"housing_market_enabled": true,
		"mortgage_enabled": true,
		"housing_rental_enabled": true,
		"housing_construction_enabled": true,
		"firm_dynamics": true,
		"sector_switching": true,
		"bank_enabled": true,
		"household_credit": true,
		"capital_market": true,
		"energy_enabled": true,
	}
