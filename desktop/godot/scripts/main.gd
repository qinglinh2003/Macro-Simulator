extends Control

const SimulationClientScript = preload("res://scripts/simulation_client.gd")
const EconomicMapScript = preload("res://scripts/economic_map.gd")
const MetricChartScript = preload("res://scripts/metric_chart.gd")

var _client
var _play_timer: Timer
var _snapshot: Dictionary = {}
var _current_context: Dictionary = {}
var _playing := false
var _capture_path := ""

var _connection_label: Label
var _tick_label: Label
var _phase_label: Label
var _output_value: Label
var _jobs_value: Label
var _inflation_value: Label
var _price_value: Label
var _context_title: Label
var _context_detail: Label
var _lever_selector: OptionButton
var _value_editor: SpinBox
var _apply_button: Button
var _pass_button: Button
var _play_button: Button
var _event_log: RichTextLabel
var _economic_map
var _chart


func _ready() -> void:
	_build_theme()
	_build_ui()
	_client = SimulationClientScript.new()
	add_child(_client)
	_client.connected.connect(_on_connected)
	_client.disconnected.connect(_on_disconnected)
	_client.response_received.connect(_on_response)
	_client.request_failed.connect(_on_request_failed)
	_play_timer = Timer.new()
	_play_timer.wait_time = 0.55
	_play_timer.timeout.connect(_on_play_tick)
	add_child(_play_timer)
	_capture_path = OS.get_environment("MACRO_SIM_CAPTURE_PATH")


func _capture_after_render(path: String) -> void:
	await get_tree().create_timer(0.25).timeout
	var image := get_viewport().get_texture().get_image()
	var error := image.save_png(path)
	if error != OK:
		push_error("Could not save prototype capture (%d)." % error)
	get_tree().quit(error)


func _build_theme() -> void:
	var app_theme := Theme.new()
	app_theme.default_font_size = 15
	app_theme.set_color("font_color", "Label", Color("dce7f2"))
	app_theme.set_color("font_color", "Button", Color("e5edf5"))
	app_theme.set_color("font_color", "OptionButton", Color("e5edf5"))
	var button := _style(Color("18283b"), Color("314862"), 8)
	var button_hover := _style(Color("213952"), Color("4fd1c5"), 8)
	app_theme.set_stylebox("normal", "Button", button)
	app_theme.set_stylebox("hover", "Button", button_hover)
	app_theme.set_stylebox("pressed", "Button", _style(Color("0d817d"), Color("4fd1c5"), 8))
	app_theme.set_stylebox("normal", "OptionButton", button)
	app_theme.set_stylebox("hover", "OptionButton", button_hover)
	theme = app_theme


func _build_ui() -> void:
	var background := ColorRect.new()
	background.color = Color("07101c")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(background)
	var shell := VBoxContainer.new()
	shell.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shell.offset_left = 14
	shell.offset_top = 12
	shell.offset_right = -14
	shell.offset_bottom = -12
	shell.add_theme_constant_override("separation", 10)
	add_child(shell)

	var header_panel := _panel()
	header_panel.custom_minimum_size.y = 62
	shell.add_child(header_panel)
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 10)
	header_panel.add_child(header)
	var title := Label.new()
	title.text = "MACRO COMMAND  /  POLICY ROOM"
	title.add_theme_font_size_override("font_size", 19)
	title.add_theme_color_override("font_color", Color("f2f7fb"))
	header.add_child(title)
	_connection_label = Label.new()
	_connection_label.text = "CONNECTING"
	_connection_label.add_theme_color_override("font_color", Color("f6ad55"))
	header.add_child(_connection_label)
	var header_space := Control.new()
	header_space.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(header_space)
	_tick_label = Label.new()
	_tick_label.text = "DAY 0000"
	_tick_label.add_theme_font_size_override("font_size", 17)
	header.add_child(_tick_label)
	_phase_label = Label.new()
	_phase_label.text = "OFFLINE"
	header.add_child(_phase_label)
	header.add_child(_button("New Game", _on_new_game))
	header.add_child(_button("Step", func(): _send({"command": "advance", "ticks": 1})))
	_play_button = _button("Play", _toggle_play)
	header.add_child(_play_button)
	header.add_child(_button("Fast x5", func(): _send({"command": "advance", "ticks": 5})))

	var columns := HBoxContainer.new()
	columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	columns.add_theme_constant_override("separation", 10)
	shell.add_child(columns)
	_build_dashboard(columns)
	_build_center(columns)
	_build_policy_panel(columns)
	_set_policy_enabled(false)


func _build_dashboard(columns: HBoxContainer) -> void:
	var left_panel := _panel()
	left_panel.custom_minimum_size.x = 225
	columns.add_child(left_panel)
	var left := VBoxContainer.new()
	left.add_theme_constant_override("separation", 10)
	left_panel.add_child(left)
	left.add_child(_section("NATIONAL DASHBOARD"))
	var nation := Label.new()
	nation.text = "Republic 01\nSimulation seed 7"
	nation.add_theme_color_override("font_color", Color("8ba3bc"))
	left.add_child(nation)
	_output_value = _metric(left, "REAL OUTPUT", "—", Color("4fd1c5"))
	_jobs_value = _metric(left, "UNEMPLOYMENT", "—", Color("f6ad55"))
	_inflation_value = _metric(left, "INFLATION", "—", Color("b794f4"))
	_price_value = _metric(left, "PRICE INDEX", "—", Color("78a9ff"))
	var note := Label.new()
	note.text = "Each simulation tick is one policy\nand production boundary. Decisions\nmay stop time before the next tick."
	note.add_theme_color_override("font_color", Color("60758d"))
	note.add_theme_font_size_override("font_size", 12)
	left.add_child(note)


func _build_center(columns: HBoxContainer) -> void:
	var center := VBoxContainer.new()
	center.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	center.add_theme_constant_override("separation", 10)
	columns.add_child(center)
	_economic_map = EconomicMapScript.new()
	_economic_map.size_flags_vertical = Control.SIZE_EXPAND_FILL
	center.add_child(_economic_map)
	_chart = MetricChartScript.new()
	center.add_child(_chart)


func _build_policy_panel(columns: HBoxContainer) -> void:
	var right_panel := _panel()
	right_panel.custom_minimum_size.x = 335
	columns.add_child(right_panel)
	var right := VBoxContainer.new()
	right.add_theme_constant_override("separation", 9)
	right_panel.add_child(right)
	right.add_child(_section("POLICY DECISION"))
	_context_title = Label.new()
	_context_title.text = "Waiting for the simulation worker"
	_context_title.add_theme_font_size_override("font_size", 18)
	_context_title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	right.add_child(_context_title)
	_context_detail = Label.new()
	_context_detail.add_theme_color_override("font_color", Color("8299b1"))
	_context_detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	right.add_child(_context_detail)
	_lever_selector = OptionButton.new()
	_lever_selector.item_selected.connect(_on_lever_selected)
	right.add_child(_lever_selector)
	_value_editor = SpinBox.new()
	_value_editor.update_on_text_changed = true
	right.add_child(_value_editor)
	var policy_buttons := HBoxContainer.new()
	_apply_button = _button("Apply Policy", _apply_policy)
	_apply_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	policy_buttons.add_child(_apply_button)
	_pass_button = _button("No Change", _pass_context)
	_pass_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	policy_buttons.add_child(_pass_button)
	right.add_child(policy_buttons)
	right.add_child(HSeparator.new())
	right.add_child(_section("CRISIS CONSOLE"))
	var crisis_note := Label.new()
	crisis_note.text = "Inject a real 20-tick productivity disruption.\nIt is announced and applied by the Shock engine."
	crisis_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	crisis_note.add_theme_color_override("font_color", Color("8299b1"))
	right.add_child(crisis_note)
	var shock_button := _button("Trigger Supply Disruption", func(): _send({"command": "trigger_shock"}))
	shock_button.add_theme_color_override("font_color", Color("ff9b82"))
	right.add_child(shock_button)
	right.add_child(_section("EVENT STREAM"))
	_event_log = RichTextLabel.new()
	_event_log.bbcode_enabled = true
	_event_log.fit_content = false
	_event_log.scroll_active = true
	_event_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_event_log.custom_minimum_size.y = 160
	right.add_child(_event_log)


func _panel() -> PanelContainer:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _style(Color("0c1725"), Color("20334a"), 11, 14))
	return panel


func _style(background: Color, border: Color, radius: int, margin: int = 8) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(radius)
	style.content_margin_left = margin
	style.content_margin_right = margin
	style.content_margin_top = margin
	style.content_margin_bottom = margin
	return style


func _section(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 12)
	label.add_theme_color_override("font_color", Color("607f9f"))
	return label


func _metric(parent: VBoxContainer, title: String, value: String, color: Color) -> Label:
	var box := VBoxContainer.new()
	var heading := Label.new()
	heading.text = title
	heading.add_theme_font_size_override("font_size", 11)
	heading.add_theme_color_override("font_color", Color("698198"))
	box.add_child(heading)
	var label := Label.new()
	label.text = value
	label.add_theme_font_size_override("font_size", 25)
	label.add_theme_color_override("font_color", color)
	box.add_child(label)
	parent.add_child(box)
	return label


func _button(text: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.pressed.connect(callback)
	return button


func _on_connected() -> void:
	_connection_label.text = "ENGINE ONLINE"
	_connection_label.add_theme_color_override("font_color", Color("4fd1c5"))
	_send({"command": "snapshot"})


func _on_disconnected() -> void:
	_connection_label.text = "RECONNECTING"
	_connection_label.add_theme_color_override("font_color", Color("ff7657"))
	_stop_playing()
	_set_policy_enabled(false)


func _on_request_failed(message: String) -> void:
	_connection_label.text = "ENGINE ERROR"
	_context_detail.text = message
	_stop_playing()


func _on_response(response: Dictionary) -> void:
	_snapshot = response.get("snapshot", {})
	_render_snapshot()
	if not _capture_path.is_empty():
		var path := _capture_path
		_capture_path = ""
		_capture_after_render(path)


func _render_snapshot() -> void:
	var tick := int(_snapshot.get("tick", 0))
	var phase := str(_snapshot.get("phase", "unknown"))
	_tick_label.text = "DAY %04d" % tick
	_phase_label.text = phase.replace("_", " ").to_upper()
	var metrics: Dictionary = _snapshot.get("metrics", {})
	_output_value.text = "%.1f" % float(metrics.get("real_output", 0.0))
	_jobs_value.text = "%.2f%%" % (100.0 * float(metrics.get("unemployment_rate", 0.0)))
	_inflation_value.text = "%+.2f%%" % (100.0 * float(metrics.get("inflation", 0.0)))
	_price_value.text = "%.3f" % float(metrics.get("price_index", 0.0))
	_economic_map.set_snapshot(_snapshot)
	_chart.set_snapshot(_snapshot)
	_render_context()
	_render_events()
	if bool(_snapshot.get("awaiting_human", false)):
		_stop_playing()


func _render_context() -> void:
	var contexts: Array = _snapshot.get("contexts", [])
	_lever_selector.clear()
	if contexts.is_empty():
		_current_context = {}
		_context_title.text = "No decision required"
		_context_detail.text = "The economy is ready for the next tick."
		_set_policy_enabled(false)
		return
	_current_context = contexts[0]
	var group := str(_current_context.get("decision_group", "policy"))
	_context_title.text = group.replace("_", " ").capitalize()
	_context_detail.text = "Treasury meeting at day %d  •  %d decision%s waiting" % [
		int(_current_context.get("boundary_tick", 0)), contexts.size(), "" if contexts.size() == 1 else "s"
	]
	for raw_action in _current_context.get("permitted_actions", []):
		var action: Dictionary = raw_action
		if bool(action.get("allowed", false)) and str(action.get("value_kind")) in ["number", "integer"]:
			_lever_selector.add_item(str(action.get("lever", "policy")).replace("_", " ").capitalize())
			_lever_selector.set_item_metadata(_lever_selector.item_count - 1, action)
	_set_policy_enabled(true)
	_apply_button.disabled = _lever_selector.item_count == 0
	if _lever_selector.item_count > 0:
		_on_lever_selected(0)


func _on_lever_selected(index: int) -> void:
	if index < 0 or index >= _lever_selector.item_count:
		return
	var action: Dictionary = _lever_selector.get_item_metadata(index)
	_value_editor.min_value = float(action.get("minimum", -1000000.0))
	_value_editor.max_value = float(action.get("maximum", 1000000.0))
	var step_value = action.get("max_step")
	if step_value == null:
		step_value = action.get("control_scale", 0.01)
	_value_editor.step = maxf(float(step_value), 0.000001)
	_value_editor.value = float(action.get("current_value", 0.0))
	_value_editor.suffix = "  effective day %d" % int(action.get("earliest_effective_tick", 0))


func _apply_policy() -> void:
	if _current_context.is_empty() or _lever_selector.selected < 0:
		return
	var action: Dictionary = _lever_selector.get_item_metadata(_lever_selector.selected)
	var value: Variant = _value_editor.value
	if str(action.get("value_kind")) == "integer":
		value = int(round(_value_editor.value))
	_send({
		"command": "resolve_context",
		"context_id": _current_context.get("context_id"),
		"actions": [{"lever": action.get("lever"), "value": value}],
	})


func _pass_context() -> void:
	if _current_context.is_empty():
		return
	_send({"command": "resolve_context", "context_id": _current_context.get("context_id"), "actions": []})


func _set_policy_enabled(enabled: bool) -> void:
	_lever_selector.disabled = not enabled
	_value_editor.editable = enabled
	_apply_button.disabled = not enabled
	_pass_button.disabled = not enabled


func _render_events() -> void:
	var lines: Array[String] = []
	var events: Array = _snapshot.get("events", [])
	var start := maxi(0, events.size() - 12)
	for index in range(events.size() - 1, start - 1, -1):
		var event: Dictionary = events[index]
		var event_type := str(event.get("event_type", "event")).replace("_", " ")
		var status := str(event.get("status", ""))
		var suffix := "  [color=#7890aa]%s[/color]" % status if not status.is_empty() else ""
		lines.append("[color=#4fd1c5]D%04d[/color]  %s%s" % [int(event.get("boundary_tick", 0)), event_type, suffix])
	var bulletins: Array = _snapshot.get("shock_bulletins", [])
	for bulletin in bulletins:
		lines.push_front("[color=#ff7657]D%04d  shock: %s[/color]" % [int((bulletin as Dictionary).get("start_tick", 0)), str((bulletin as Dictionary).get("kind", "unknown"))])
	_event_log.text = "\n".join(lines) if not lines.is_empty() else "[color=#60758d]No events yet.[/color]"


func _send(command: Dictionary) -> void:
	_client.send_command(command)


func _on_new_game() -> void:
	_stop_playing()
	_send({"command": "new_game", "seed": 7})


func _toggle_play() -> void:
	if _playing:
		_stop_playing()
	elif not bool(_snapshot.get("awaiting_human", true)):
		_playing = true
		_play_button.text = "Pause"
		_play_timer.start()


func _stop_playing() -> void:
	_playing = false
	if is_instance_valid(_play_timer):
		_play_timer.stop()
	if is_instance_valid(_play_button):
		_play_button.text = "Play"


func _on_play_tick() -> void:
	if _playing and not _client.busy:
		_send({"command": "advance", "ticks": 1})
