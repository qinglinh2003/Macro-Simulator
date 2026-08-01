extends SceneTree

const MainScript := preload("res://scripts/main.gd")
const FrontendAdapterScript := preload("res://scripts/m11_frontend_adapter.gd")


func _init() -> void:
	_run.call_deferred()


func _run() -> void:
	var groups: Array = MainScript.PANEL_GROUPS
	var charts: Dictionary = MainScript.PANEL_CHARTS
	var ids: Dictionary = {}
	for group: Dictionary in groups:
		var group_id := str(group["id"])
		assert(not ids.has(group_id), "duplicate panel group: %s" % group_id)
		ids[group_id] = true
		assert((group.get("items", []) as Array).size() == 6,
			"%s must expose six headline indicators" % group_id)
		assert(charts.has(group_id), "%s has no chart definition" % group_id)
		assert((charts[group_id] as Array).size() >= 3,
			"%s needs at least three structural views" % group_id)

	for required_id: String in [
		"national_accounts", "debt_risk", "housing", "external",
		"population", "firms",
	]:
		assert(ids.has(required_id), "missing player-facing domain: %s" % required_id)

	var population_keys := _chart_metric_keys(charts["population"])
	assert(population_keys.has("births_tick"))
	assert(population_keys.has("deaths_tick"))
	assert(not population_keys.has("births"),
		"firm entry must not be presented as a human birth")
	assert(not population_keys.has("deaths"),
		"firm exit must not be presented as a human death")

	var enterprise_keys := _chart_metric_keys(charts["firms"])
	assert(enterprise_keys.has("births"))
	assert(enterprise_keys.has("deaths"))
	assert(not enterprise_keys.has("births_tick"))
	assert(not enterprise_keys.has("deaths_tick"))

	var debt_keys := _chart_metric_keys(charts["debt_risk"])
	for maintained_key: String in [
		"new_loans_total", "principal_repaid", "household_interest_paid",
		"loan_interest_paid", "bank_realized_credit_losses",
	]:
		assert(debt_keys.has(maintained_key),
			"debt view is missing native flow: %s" % maintained_key)
	for retired_key: String in [
		"household_contractual_debt_service_due",
		"household_debt_service_reserved",
		"household_interest_arrears_opening",
		"household_interest_arrears_closing",
		"household_interest_arrears_extinguished",
		"household_interest_arrears_in_goods_reservation",
		"household_interest_arrears_stock_flow_residual",
	]:
		assert(not debt_keys.has(retired_key),
			"debt view still references an unmaintained ledger: %s" % retired_key)

	var adapter = FrontendAdapterScript.new()
	var normalized_schema: Dictionary = adapter.schema_payload({
		"schema_version": 1,
		"economy_id": 0,
		"control_mode": "free_policy",
		"levers": [{
			"name": "manual_policy_rate",
			"owner_role": "central_bank",
			"value_kind": "nullable_number",
			"enabled_if": "",
			"required_capabilities": "bank_enabled|government",
		}, {
			"name": "omo_index_deposits",
			"owner_role": "central_bank",
			"value_kind": "boolean",
			"enabled_if": "omo",
			"required_capabilities": "",
		}],
	})
	var normalized_levers: Array = (
		normalized_schema.get("seats", {}) as Dictionary
	).get("central_bank", {}).get("levers", [])
	assert(normalized_levers.size() == 2)
	assert(normalized_levers[0]["value_kind"] == "number")
	assert(normalized_levers[0]["nullable"] == true)
	assert(normalized_levers[0]["requires"] == [
		"bank_enabled", "government"])
	assert(normalized_levers[1]["value_kind"] == "bool")
	assert(normalized_levers[1]["enabled_if"] == ["omo"])
	adapter.reset({}, {})
	var metrics: Array = []
	for prefix: String in ["income", "wealth", "consumption"]:
		for decile in range(1, 11):
			metrics.append({
				"stable_id": "metric.economy.%s_decile_%d_share" % [
					prefix, decile],
				"value": 0.1,
			})
	for metric: Array in [
		["metric.economy.labor_sector_consumption_fte", 12.0],
		["metric.economy.labor_sector_capital_fte", 4.0],
		["metric.economy.labor_sector_energy_fte", 2.0],
		["metric.economy.labor_sector_construction_fte", 3.0],
		["metric.source.m7.employed_heads", 21.0],
		["metric.source.m7.unemployment", 2.0],
		["metric.source.m7.job_guarantee", 1.0],
		["metric.source.m7.out_of_labor_force", 7.0],
		["metric.source.m7.hires", 2.0],
		["metric.source.m7.recalls", 1.0],
		["metric.source.m7.job_to_job_moves", 1.0],
		["metric.source.m7.churn_separations", 1.0],
		["metric.economy.age_15_24_participation", 0.6],
		["metric.economy.age_15_24_employment", 0.5],
		["metric.economy.pyramid_male_0_14", 8.0],
		["metric.economy.pyramid_female_0_14", 7.0],
		["metric.economy.firm_count_c", 3.0],
		["metric.economy.sector_consumption_sales", 10.0],
		["metric.source.m4.consumption_output_real", 11.0],
		["metric.source.m4.tax_profit", 2.0],
		["metric.source.m4.tax_income", 3.0],
		["metric.source.m4.tax_consumption", 4.0],
		["metric.economy.energy_stock_total", 20.0],
		["metric.source.m8.energy.sold", 4.0],
	]:
		metrics.append({
			"stable_id": metric[0],
			"value": metric[1],
		})
	var snapshot: Dictionary = adapter.apply_projection({
		"mode": "full",
		"snapshot": {
			"boundary": 30,
			"metrics": metrics,
			"policies": [],
			"economies": [],
		},
	})
	var distribution: Dictionary = (
		snapshot.get("panel_details", {}) as Dictionary).get(
			"distribution", {})
	for prefix: String in ["income", "wealth", "consumption"]:
		var values: Dictionary = distribution.get(prefix, {})
		assert((values.get("deciles", []) as Array).size() == 10)
		assert((values.get("lorenz", []) as Array).size() == 11)
		assert(absf(float(values["lorenz"][-1]) - 1.0) < 0.000001)
	var details: Dictionary = snapshot.get("panel_details", {})
	var adapted_metrics: Dictionary = snapshot.get("metrics", {})
	assert(is_equal_approx(float(adapted_metrics.get("tax_profit")), 2.0))
	assert(is_equal_approx(float(adapted_metrics.get("tax_income")), 3.0))
	assert(is_equal_approx(float(adapted_metrics.get("tax_consumption")), 4.0))
	assert(is_equal_approx(
		float(adapted_metrics.get("energy_coverage_mean")), 5.0))
	assert((((details.get("labor", {}) as Dictionary).get(
		"employment_sectors", [])) as Array).size() == 5)
	assert((((details.get("labor", {}) as Dictionary).get(
		"states", [])) as Array).size() == 3)
	assert((((details.get("labor", {}) as Dictionary).get(
		"flows", [])) as Array).size() == 6)
	assert((((details.get("labor", {}) as Dictionary).get(
		"participation_by_age", [])) as Array).size() == 6)
	assert((((details.get("population", {}) as Dictionary).get(
		"pyramid", [])) as Array).size() == 7)
	assert((((details.get("real_economy", {}) as Dictionary).get(
		"sectors", [])) as Array).size() == 4)

	adapter.apply_entity_result(_entity_result("households", [{
		"id": 1,
		"account_id": 11,
		"cash": 100.0,
		"debt": 20.0,
		"income_realized": 8.0,
		"spent": 5.0,
		"labor_sold": 1.0,
		"member_count": 1,
	}]))
	adapter.apply_entity_result(_entity_result("persons", [{
		"id": 1,
		"sex": "female",
		"birth_day": -10950,
		"death_day": -1,
		"age_days": 10980,
		"mother_id": 0,
		"father_id": 0,
		"partner_id": 0,
		"guardian_id": 0,
		"household_id": 1,
		"primary_job_id": 1,
		"secondary_job_id": 0,
		"efficiency": 1.0,
		"cash": 100.0,
		"debt": 20.0,
		"firm_equity": 30.0,
		"bank_equity": 10.0,
		"bonds": 10.0,
		"gross_assets": 150.0,
		"net_worth": 130.0,
		"allocated_income": 8.0,
		"allocated_consumption": 5.0,
		"participating": true,
		"searching": false,
		"alive": true,
	}]))
	adapter.apply_entity_result(_entity_result("jobs", [{
		"id": 1,
		"person_id": 1,
		"firm_id": 1,
		"hire_day": 10,
		"separation_day": -1,
		"wage": 8.0,
		"hours": 1.0,
		"secondary": false,
		"suspended": false,
		"active": true,
	}]))
	var firm_row := {
		"id": 1,
		"sector": "consumption",
		"cash": 200.0,
		"debt": 50.0,
		"goods_inventory": 10.0,
		"physical_capital": 100.0,
		"productivity": 1.2,
		"total_factor_productivity": 1.1,
		"posted_price": 2.0,
		"posted_wage": 8.0,
		"markup": 0.2,
		"demand_expected": 12.0,
		"previous_sales": 9.0,
		"previous_hires": 1.0,
		"book_equity": 200.0,
		"earnings": 6.0,
		"interest_arrears": 0.0,
		"eligible_collateral_value": 90.0,
		"borrowing_base_headroom": 40.0,
		"tobin_q_ema": 1.1,
		"defaulted": false,
		"equity_id": 1,
		"outstanding_shares": 100.0,
		"share_price": 2.0,
		"last_share_price": 1.9,
		"peak_share_price": 2.1,
		"fundamental_per_share": 1.8,
		"share_trend": 0.1,
		"active": true,
		"employee_count": 1,
	}
	adapter.apply_entity_result(_entity_result("firms", [firm_row]))
	adapter.apply_entity_result(_entity_result("banks", [{
		"id": 1,
		"closing_capital": 100.0,
		"alive": true,
		"resolved": false,
	}]))
	adapter.apply_entity_result(_entity_result("equities", [{
		"id": 1,
		"issuer_kind": "firm",
		"issuer_owner_id": 1,
		"outstanding_shares": 100.0,
		"price": 2.0,
		"last_price": 1.9,
		"peak_price": 2.1,
		"fundamental": 1.8,
		"active": true,
		"resolved": false,
	}, {
		"id": 2,
		"issuer_kind": "bank",
		"issuer_owner_id": 1,
		"outstanding_shares": 50.0,
		"price": 3.0,
		"last_price": 3.0,
		"peak_price": 3.2,
		"fundamental": 2.8,
		"active": true,
		"resolved": false,
	}]))
	var joined := adapter.legacy_snapshot()
	var households: Array = (
		joined.get("households", {}).get("items", []) as Array)
	assert(households.size() == 1)
	var members: Array = (
		(households[0] as Dictionary).get("members", []) as Array)
	assert(members.size() == 1)
	assert(is_equal_approx(float(
		((households[0] as Dictionary).get("assets", {}) as Dictionary).get(
			"total")), 150.0))
	assert(str((members[0] as Dictionary).get(
		"labor_status_id")) == "employed")
	assert(str((((members[0] as Dictionary).get(
		"employers", []) as Array)[0] as Dictionary).get(
			"sector_id")) == "consumption")
	var firm_items: Array = (
		joined.get("firms", {}).get("items", []) as Array)
	assert(firm_items.size() == 1)
	var firm_employees: Array = (((firm_items[0] as Dictionary).get(
		"labor", {}) as Dictionary).get("employees", []) as Array)
	assert(firm_employees.size() == 1)
	assert(str((firm_employees[0] as Dictionary).get(
		"contract_id")) == "primary")
	assert(is_equal_approx(float((firm_employees[0] as Dictionary).get(
		"contract_hours")), 1.0))
	assert(is_equal_approx(float((firm_employees[0] as Dictionary).get(
		"locked_wage")), 8.0))
	var market: Dictionary = joined.get("stock_market", {})
	var listings: Array = market.get("listings", [])
	assert(listings.size() == 2)
	assert(str((listings[0] as Dictionary).get(
		"instrument_type")) == "company")
	assert(str((listings[0] as Dictionary).get(
		"sector_id")) == "consumption")
	var market_summary: Dictionary = market.get("summary", {})
	assert(is_equal_approx(float(
		market_summary.get("corporate_market_cap")), 200.0))
	assert(is_equal_approx(float(
		market_summary.get("bank_market_cap")), 150.0))
	assert((market.get("sectors", []) as Array).size() == 2)
	quit(0)


func _chart_metric_keys(definitions: Array) -> Dictionary:
	var keys: Dictionary = {}
	for chart: Dictionary in definitions:
		for item: Array in chart.get("items", []):
			if not item.is_empty():
				keys[str(item[0])] = true
	return keys


func _entity_result(kind: String, rows: Array) -> Dictionary:
	return {
		"kind": kind,
		"page": {
			"boundary": 30,
			"total_rows": rows.size(),
			"has_more": false,
		},
		"rows": rows,
	}
