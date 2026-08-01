extends SceneTree

const StartMenuScript := preload("res://scripts/start_menu.gd")


func _init() -> void:
	var menu := StartMenuScript.new()
	menu._reset_defaults()
	menu._start_date = {"year": 2000, "month": 1, "day": 1}
	menu._duration = "5y"
	assert(menu._duration_ticks_value() == 1827)
	assert(menu._date_iso(menu._end_date()) == "2005-01-01")

	menu._start_date = {"year": 2024, "month": 2, "day": 29}
	menu._duration = "1y"
	assert(menu._duration_ticks_value() == 365)
	assert(menu._date_iso(menu._end_date()) == "2025-02-28")

	menu._duration = "custom"
	menu._custom_duration_ticks = 2
	assert(menu._date_iso(menu._end_date()) == "2024-03-02")
	assert(menu._draft_manifest()["start_date"] == "2024-02-29")
	assert(menu._draft_manifest()["duration"] == 2)
	assert(not menu._draft_manifest().has("performance_scale"))
	var scale: Dictionary = menu._draft_manifest()["countries"][0]["overrides"]
	assert(scale["n_households"] == 100_000)
	assert(scale["demographics_population"] == 100_000)
	assert(scale["n_firms_c"] == 1_500)
	assert(scale["n_builders"] == 625)

	menu._duration = "inf"
	assert(menu._duration_ticks_value() == null)
	assert(menu._draft_manifest()["duration"] == null)
	menu.free()
	quit(0)
