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
	_assert_header_bounds(game, "first layout")
	game._render()
	await process_frame

	_assert_header_bounds(game, "rendered layout")
	var menu_center := (game._n["main_menu"] as Control).get_global_rect().get_center().y
	var play_center := (game._n["play"] as Control).get_global_rect().get_center().y
	assert(absf(menu_center - play_center) <= 2.0,
		"identity and transport controls must share one visual baseline")
	var policy_scope := game._n["policy_scope"] as Button
	var policy_search := game._n["search"] as LineEdit
	assert(not policy_scope.visible,
		"a closed policy desk must not show an inactive scope selector")
	assert(policy_search.get_global_rect().size.x >= 390.0,
		"policy search must reclaim the closed scope selector space")

	# Long metric identifiers in these panorama pages previously propagated
	# their intrinsic width into the main HBox and pushed the timeline offscreen.
	var timeline_panel := game._n["timeline_panel"] as Control
	var timeline_x := timeline_panel.get_global_rect().position.x
	game._tab = "panels"
	for panel_group: String in ["population", "debt_risk", "national_accounts"]:
		game._goto_panel_group = panel_group
		game._render()
		await process_frame
		await process_frame
		var timeline_rect := timeline_panel.get_global_rect()
		assert(absf(timeline_rect.position.x - timeline_x) <= 1.0,
			"%s displaced the timeline" % panel_group)
		assert(timeline_rect.end.x <= VIEWPORT_SIZE.x,
			"%s pushed the timeline outside the viewport" % panel_group)
		_assert_horizontal_bounds(
			game._n["center_body"] as Control,
			(game._n["center_frame"] as Control).get_global_rect(), panel_group)

	# Institutional seat controls must have discrete hit rectangles.  This guards
	# against restoring the overflowing single-row HBox implementation.
	var seats: Array[Control] = []
	for seat_id: String in ["treasury", "central_bank", "regulator",
			"external_affairs", "energy", "labor_social"]:
		seats.append(game._n["seat_" + seat_id] as Control)
	for left_index in seats.size():
		for right_index in range(left_index + 1, seats.size()):
			assert(not seats[left_index].get_global_rect().intersects(
				seats[right_index].get_global_rect()),
				"seat controls %d and %d overlap" % [left_index, right_index])
	assert(seats[3].get_global_rect().position.y
		> seats[0].get_global_rect().position.y,
		"the policy desk must wrap seats into a second row")

	game.queue_free()
	OS.set_environment("MACRO_SIM_SKIP_START_MENU", "")
	quit(0)


func _assert_header_bounds(game: Control, phase: String) -> void:
	# Every transport control must remain in the logical launch viewport both
	# before and after the first localized render.
	for key: String in ["main_menu", "mode_interactive", "mode_realtime",
			"play", "speed_1", "speed_5", "speed_15", "speed_60"]:
		var control := game._n[key] as Control
		var rect := control.get_global_rect()
		assert(rect.position.x >= 0.0,
			"%s: %s starts outside the viewport" % [phase, key])
		assert(rect.end.x <= VIEWPORT_SIZE.x,
			"%s: %s exceeds the launch viewport" % [phase, key])


func _assert_horizontal_bounds(node: Node, bounds: Rect2, panel_group: String) -> void:
	if node is Control:
		var control := node as Control
		if control.visible and control.get_global_rect().size.x > 0.0:
			var rect := control.get_global_rect()
			assert(rect.position.x >= bounds.position.x - 1.0,
				"%s contains a control left of the center frame" % panel_group)
			assert(rect.end.x <= bounds.end.x + 1.0,
				"%s contains a control right of the center frame" % panel_group)
	for child: Node in node.get_children():
		_assert_horizontal_bounds(child, bounds, panel_group)
