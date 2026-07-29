extends SceneTree

const MainScript := preload("res://scripts/main.gd")
const LocaleCatalogScript := preload("res://scripts/localization.gd")

const VIEWPORT_SIZE := Vector2(1440, 900)


func _init() -> void:
	_run.call_deferred()


func _run() -> void:
	LocaleCatalogScript.set_locale("zh_CN")
	OS.set_environment("MACRO_SIM_SKIP_START_MENU", "1")
	var game := MainScript.new()
	game.size = VIEWPORT_SIZE
	root.add_child(game)
	await process_frame
	game._render()
	await process_frame

	# Every transport control must remain in the logical launch viewport.
	for key: String in ["main_menu", "mode_interactive", "mode_realtime",
			"play", "speed_1", "speed_5", "speed_15", "speed_60"]:
		var control := game._n[key] as Control
		var rect := control.get_global_rect()
		assert(rect.position.x >= 0.0, "%s starts outside the viewport" % key)
		assert(rect.end.x <= VIEWPORT_SIZE.x,
			"%s exceeds the launch viewport" % key)

	# Institutional seat controls must have discrete hit rectangles.  This guards
	# against restoring the overflowing single-row HBox implementation.
	var seats: Array[Control] = []
	for seat_id: String in ["treasury", "central_bank", "regulator",
			"external_affairs", "energy"]:
		seats.append(game._n["seat_" + seat_id] as Control)
	for left_index in seats.size():
		for right_index in range(left_index + 1, seats.size()):
			assert(not seats[left_index].get_global_rect().intersects(
				seats[right_index].get_global_rect()),
				"seat controls %d and %d overlap" % [left_index, right_index])

	game.queue_free()
	OS.set_environment("MACRO_SIM_SKIP_START_MENU", "")
	quit(0)
