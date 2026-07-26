extends SceneTree

const MainScript := preload("res://scripts/main.gd")


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
	quit(0)


func _chart_metric_keys(definitions: Array) -> Dictionary:
	var keys: Dictionary = {}
	for chart: Dictionary in definitions:
		for item: Array in chart.get("items", []):
			if not item.is_empty():
				keys[str(item[0])] = true
	return keys
