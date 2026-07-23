extends SceneTree

const MainScript := preload("res://scripts/main.gd")


func _init() -> void:
	_run.call_deferred()


func _run() -> void:
	var groups: Array = MainScript.PANEL_GROUPS
	var charts: Dictionary = MainScript.PANEL_CHARTS
	var names: Dictionary = {}
	for group: Dictionary in groups:
		var group_name := str(group["name"])
		assert(not names.has(group_name), "duplicate panel group: %s" % group_name)
		names[group_name] = true
		assert((group.get("items", []) as Array).size() == 6,
			"%s must expose six headline indicators" % group_name)
		assert(charts.has(group_name), "%s has no chart definition" % group_name)
		assert((charts[group_name] as Array).size() >= 3,
			"%s needs at least three structural views" % group_name)

	for required_name: String in [
		"国民账户", "债务与风险", "住房市场", "外部部门", "人口社会", "企业生态",
	]:
		assert(names.has(required_name), "missing player-facing domain: %s" % required_name)

	var population_keys := _chart_metric_keys(charts["人口社会"])
	assert(population_keys.has("births_tick"))
	assert(population_keys.has("deaths_tick"))
	assert(not population_keys.has("births"),
		"firm entry must not be presented as a human birth")
	assert(not population_keys.has("deaths"),
		"firm exit must not be presented as a human death")

	var enterprise_keys := _chart_metric_keys(charts["企业生态"])
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
