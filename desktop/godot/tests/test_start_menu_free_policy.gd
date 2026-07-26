extends SceneTree

const StartMenuScript := preload("res://scripts/start_menu.gd")


func _init() -> void:
	var menu := StartMenuScript.new()
	menu._reset_defaults()

	assert(menu.STEP_META.size() == 5)
	assert(menu._run_mode == "realtime")
	for occupant in menu._seat_occupants.values():
		assert(occupant == "null")

	var spec: Dictionary = menu._draft_manifest()
	assert(spec["run_mode"] == "realtime")
	for occupant in spec["seats"].values():
		assert(occupant == "null")

	menu.free()
	quit(0)
