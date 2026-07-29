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
	"metric.source.m5.alive_banks": "banks_alive",
	"metric.source.m5.bank_failures": "n_bank_failures",
	"metric.source.m6.household_bankruptcies": "hh_bankruptcies",
	"metric.source.m6.firm_births": "births",
	"metric.source.m6.firm_exits": "deaths",
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
	"government_consumption_nominal": "gdp_nominal_government_consumption",
	"fixed_capital_formation_nominal": "gdp_nominal_fixed_capital_formation",
	"net_exports_nominal": "gdp_nominal_net_exports",
	"gross_output_consumption_nominal": "gdp_nominal_gross_output_c",
	"gross_output_capital_nominal": "gdp_nominal_gross_output_k",
	"gross_output_energy_nominal": "gdp_nominal_gross_output_e",
	"gross_output_housing_nominal": "gdp_nominal_gross_output_housing",
	"income_reconciled_nominal": "gdp_nominal_income_reconciled",
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
		if kind == "households":
			_apply_household_rows(result.get("rows", []), page)
		elif kind == "firms":
			_apply_firm_rows(result.get("rows", []), page)
		elif kind == "equities":
			_apply_equity_rows(result.get("rows", []), page)
		_entity_boundaries[kind] = boundary
	return legacy_snapshot()


func entity_boundary(kind: String) -> int:
	return int(_entity_boundaries.get(kind, -1))


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
		"panel_details": {},
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
	var price_index := maxf(float(point.get("price_index", 0.0)), 0.000000001)
	point["real_wage"] = float(point.get("avg_wage", 0.0)) / price_index
	var employed := maxf(float(point.get("labor_E", 0.0)), 1.0)
	point["labor_productivity"] = float(point.get("real_output", 0.0)) / employed
	return point


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


func _normalize_lever(raw: Dictionary) -> Dictionary:
	var lever := raw.duplicate(true)
	if str(lever.get("value_kind", "")) == "boolean":
		lever["value_kind"] = "bool"
	lever["min_hold_ticks"] = lever.get("minimum_hold_ticks", 0)
	lever["max_step"] = lever.get("maximum_step")
	lever["admin_weight"] = lever.get("administrative_weight", 0.0)
	lever["requires"] = lever.get("required_capabilities", [])
	lever["nullable"] = false
	return lever


func _apply_household_rows(rows_variant: Variant, page: Dictionary) -> void:
	var items: Array = []
	var total_assets := 0.0
	var total_debt := 0.0
	var population := 0
	if rows_variant is Array:
		for raw_row: Variant in rows_variant as Array:
			if not raw_row is Dictionary:
				continue
			var row := raw_row as Dictionary
			var cash := float(row.get("cash", 0.0))
			var debt := float(row.get("debt", 0.0))
			var member_count := int(row.get("member_count", 0))
			total_assets += cash
			total_debt += debt
			population += member_count
			items.append({
				"household_id": row.get("id", 0),
				"account_id": row.get("account_id", 0),
				"member_count": member_count,
				"members": [],
				"assets": {
					"cash": cash,
					"firm_equity": 0.0,
					"bank_equity": 0.0,
					"bonds": 0.0,
					"total": cash,
				},
				"debt": debt,
				"net_worth": cash - debt,
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
		"as_of_date": "",
	}


func _apply_firm_rows(rows_variant: Variant, page: Dictionary) -> void:
	var items: Array = []
	var employment := 0.0
	var revenue := 0.0
	var earnings := 0.0
	if rows_variant is Array:
		for raw_row: Variant in rows_variant as Array:
			if not raw_row is Dictionary:
				continue
			var row := raw_row as Dictionary
			var employee_count := int(row.get("employee_count", 0))
			var sales := float(row.get("previous_sales", 0.0))
			var price := float(row.get("posted_price", 0.0))
			var row_revenue := sales * price
			var row_earnings := float(row.get("earnings", 0.0))
			var cash := float(row.get("cash", 0.0))
			var debt := float(row.get("debt", 0.0))
			var capital := float(row.get("physical_capital", 0.0))
			var inventory := float(row.get("goods_inventory", 0.0))
			employment += employee_count
			revenue += row_revenue
			earnings += row_earnings
			items.append({
				"firm_id": row.get("id", 0),
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
					"employment_fte": float(employee_count),
					"active_heads": employee_count,
					"contract_count": employee_count,
					"employees": [],
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
					"enabled": int(row.get("equity_id", 0)) > 0,
					"equity_id": row.get("equity_id", 0),
					"shares_outstanding": row.get("outstanding_shares", 0.0),
					"share_price": row.get("share_price", 0.0),
					"last_share_price": row.get("last_share_price", 0.0),
					"market_cap": float(row.get("share_price", 0.0)) \
						* float(row.get("outstanding_shares", 0.0)),
					"fundamental_per_share":
						row.get("fundamental_per_share", 0.0),
					"tobin_q_ema": row.get("tobin_q_ema", 0.0),
					"share_trend": row.get("share_trend", 0.0),
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
		"as_of_date": "",
	}


func _apply_equity_rows(rows_variant: Variant, page: Dictionary) -> void:
	var listings: Array = []
	var market_cap := 0.0
	var advances := 0
	var declines := 0
	var unchanged := 0
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
			var issuer_id: Variant = row.get("issuer_owner_id", 0)
			listings.append({
				"symbol": (
					"BNK%04d" if issuer_kind == "bank" else "F%04d"
				) % int(issuer_id),
				"issuer_kind_id": issuer_kind,
				"issuer_id": issuer_id,
				"can_open_firm": issuer_kind == "firm",
				"sector_id": "banking" if issuer_kind == "bank" else "unknown",
				"price": price,
				"last_price": previous,
				"change": change,
				"market_cap": capitalization,
				"shares": row.get("outstanding_shares", 0.0),
				"fundamental": row.get("fundamental", 0.0),
				"fundamental_gap": (
					0.0 if absf(float(row.get("fundamental", 0.0))) \
						< 0.000000001
					else price / float(row.get("fundamental", 0.0)) - 1.0
				),
			})
	var index_level := 1000.0
	if not listings.is_empty():
		var equal_return := 0.0
		for listing: Dictionary in listings:
			equal_return += float(listing.get("change", 0.0))
		index_level *= 1.0 + equal_return / float(listings.size())
	_stock_market = {
		"index_name": "ALL-SHARE",
		"summary": {
			"index_level": index_level,
			"index_change": index_level / 1000.0 - 1.0,
			"market_cap": market_cap,
			"corporate_market_cap": market_cap,
			"bank_market_cap": 0.0,
			"listed_count": page.get("total_rows", listings.size()),
			"turnover": 0.0,
			"advances": advances,
			"declines": declines,
			"unchanged": unchanged,
		},
		"listings": listings,
		"history": [{
			"tick": _raw.get("boundary", 0),
			"index_level": index_level,
			"prices": {},
		}],
		"sectors": [],
		"as_of_date": "",
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
