extends Control
## 宏观政策室 v29 — 公报制驾驶舱 + schema 驱动工作台 + 原子提案 + 危机横幅。
## 前端零经济逻辑:数据全部来自 worker 快照,修改全部走提案 API。

const SimulationClientScript = preload("res://scripts/simulation_client.gd")
const MetricChartScript = preload("res://scripts/metric_chart.gd")

const TPY := 365
const QT := 91
const SPEEDS := [1, 5, 15, 60]
const HEADLINE := [
	"real_output", "unemployment_rate", "inflation", "price_index",
	"policy_rate", "gov_deficit_to_gdp", "avg_wage",
]
const SERIES_LABEL := {
	"real_output": "GDP(30日窗)", "unemployment_rate": "失业率",
	"inflation": "通胀(年化)", "price_index": "物价指数",
	"policy_rate": "利率(年化)", "gov_deficit_to_gdp": "赤字/GDP",
	"avg_wage": "平均工资",
}
const INK := Color("16283c")        # 藏青墨
const INK2 := Color("5a6b7d")
const INK3 := Color("93a0ad")
const ACCENT := Color("1d4e89")     # 财经藏蓝
const WARN := Color("b26a00")
const CRIT := Color("b3261e")
const GOOD := Color("1e7a46")
const GROUND := Color("f7f5f1")     # 纸白
const PANEL := Color("ffffff")
const PANEL2 := Color("efece6")
const LINE := Color("e0dcd2")

var _client
var _outbox: Array = []
var _snapshot: Dictionary = {}
var _schema: Dictionary = {}
var _groups: Dictionary = {}
var _cart: Dictionary = {}
var _release_hist: Dictionary = {}
var _seen_release: Dictionary = {}
var _playing := false
var _speed := 1
var _god := false
var _last_toasted := ""
var _capture_path := ""

var _connection_label: Label
var _clock_label: Label
var _tick_label: Label
var _tiles_box: HBoxContainer
var _status_label: Label
var _capacity_label: Label
var _levers_box: VBoxContainer
var _cart_box: HBoxContainer
var _cart_cost: Label
var _submit_btn: Button
var _pass_btn: Button
var _events_box: VBoxContainer
var _play_btn: Button
var _paused_label: Label
var _banner: PanelContainer
var _banner_body: Label
var _toast: PanelContainer
var _toast_label: Label
var _toast_timer: Timer
var _play_timer: Timer
var _speed_btns: Array = []


func _ready() -> void:
	_build_theme()
	_build_ui()
	_client = SimulationClientScript.new()
	add_child(_client)
	_client.connected.connect(_on_connected)
	_client.disconnected.connect(func() -> void: _connection_label.text = "已断开·重连中")
	_client.response_received.connect(_on_response)
	_client.request_failed.connect(_on_request_failed)
	_play_timer = Timer.new()
	_play_timer.wait_time = 1.0
	_play_timer.timeout.connect(_on_play_tick)
	add_child(_play_timer)
	_play_timer.start()
	_capture_path = OS.get_environment("MACRO_SIM_CAPTURE_PATH")


# ---------------- 请求队列(client 单飞行请求) ----------------
func _send(command: Dictionary) -> void:
	_outbox.append(command)
	_pump()


func _pump() -> void:
	if _client == null or _client.busy or _outbox.is_empty():
		return
	_client.send_command(_outbox.pop_front())


func _on_connected() -> void:
	_connection_label.text = "已连接"
	_connection_label.add_theme_color_override("font_color", GOOD)
	_send({"command": "hello"})
	_send({"command": "get_schema"})


func _on_response(response: Dictionary) -> void:
	var payload: Dictionary = response.get("snapshot", {})
	if payload.has("levers") and payload.has("seat"):
		_schema = payload
		_index_schema()
	else:
		_snapshot = payload
		_ingest_releases()
		var verdict: Variant = payload.get("last_verdict")
		if verdict is Dictionary and not (verdict as Dictionary).is_empty():
			_maybe_toast(verdict)
		if _playing and _awaiting():
			_playing = false
	_render()
	_pump()
	if not _capture_path.is_empty():
		var path := _capture_path
		_capture_path = ""
		_capture_after_render(path)


func _on_request_failed(message: String) -> void:
	_show_toast("⛔ " + message, false)
	_pump()


func _capture_after_render(path: String) -> void:
	await get_tree().create_timer(0.3).timeout
	var image := get_viewport().get_texture().get_image()
	var error := image.save_png(path)
	if error != OK:
		push_error("Could not save prototype capture (%d)." % error)
	get_tree().quit(error)


# ---------------- 主题与布局 ----------------
func _build_theme() -> void:
	var app_theme := Theme.new()
	# CJK:Godot 默认字体无中文字形(乱码根因)——挂系统中文字体栈
	var cjk := SystemFont.new()
	cjk.font_names = PackedStringArray([
		"Hiragino Sans GB", "STHeiti", "Heiti SC", "Arial Unicode MS",
		"Microsoft YaHei", "Noto Sans CJK SC", "Helvetica Neue"])
	app_theme.default_font = cjk
	app_theme.default_font_size = 14
	app_theme.set_color("font_color", "Label", INK)
	app_theme.set_color("font_color", "Button", INK)
	app_theme.set_color("font_color", "CheckBox", INK)
	app_theme.set_color("font_pressed_color", "Button", Color.WHITE)
	var button := _style(PANEL, LINE, 5, 6)
	app_theme.set_stylebox("normal", "Button", button)
	app_theme.set_stylebox("hover", "Button", _style(PANEL2, ACCENT, 5, 6))
	app_theme.set_stylebox("pressed", "Button", _style(ACCENT, ACCENT, 5, 6))
	app_theme.set_stylebox("disabled", "Button", _style(GROUND, LINE, 5, 6))
	app_theme.set_stylebox("panel", "PanelContainer", _style(PANEL, LINE, 6, 10))
	theme = app_theme


func _style(background: Color, border: Color, radius: int, margin: int = 8) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(radius)
	style.set_content_margin_all(margin)
	return style


func _build_ui() -> void:
	var background := ColorRect.new()
	background.color = GROUND
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(background)
	var shell := VBoxContainer.new()
	shell.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shell.offset_left = 14
	shell.offset_top = 10
	shell.offset_right = -14
	shell.offset_bottom = -10
	shell.add_theme_constant_override("separation", 8)
	add_child(shell)

	# 顶栏
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 14)
	shell.add_child(header)
	var title := Label.new()
	title.text = "宏观政策室"
	var serif := SystemFont.new()
	serif.font_names = PackedStringArray([
		"Songti SC", "STSong", "SimSun", "Georgia", "serif"])
	title.add_theme_font_override("font", serif)
	title.add_theme_font_size_override("font_size", 21)
	header.add_child(title)
	var sub := Label.new()
	sub.text = "v29 · 真引擎 · 财政席"
	sub.add_theme_color_override("font_color", INK3)
	header.add_child(sub)
	_connection_label = Label.new()
	_connection_label.text = "连接中…"
	_connection_label.add_theme_color_override("font_color", WARN)
	header.add_child(_connection_label)
	var god := CheckBox.new()
	god.text = "上帝模式"
	god.toggled.connect(func(v: bool) -> void:
		_god = v
		_render())
	header.add_child(god)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(spacer)
	_clock_label = Label.new()
	_clock_label.add_theme_font_size_override("font_size", 16)
	header.add_child(_clock_label)
	_tick_label = Label.new()
	_tick_label.add_theme_color_override("font_color", INK3)
	header.add_child(_tick_label)

	# 公报瓦片带
	var tiles_scroll := ScrollContainer.new()
	tiles_scroll.custom_minimum_size = Vector2(0, 104)
	tiles_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	shell.add_child(tiles_scroll)
	_tiles_box = HBoxContainer.new()
	_tiles_box.add_theme_constant_override("separation", 8)
	tiles_scroll.add_child(_tiles_box)

	# 主区
	var split := HSplitContainer.new()
	split.size_flags_vertical = Control.SIZE_EXPAND_FILL
	split.split_offset = 760
	shell.add_child(split)

	var wb_panel := PanelContainer.new()
	split.add_child(wb_panel)
	var wb := VBoxContainer.new()
	wb.add_theme_constant_override("separation", 6)
	wb_panel.add_child(wb)
	var wb_head := HBoxContainer.new()
	wb_head.add_theme_constant_override("separation", 12)
	wb.add_child(wb_head)
	var wb_title := Label.new()
	wb_title.text = "财政部工作台"
	wb_title.add_theme_font_size_override("font_size", 15)
	wb_head.add_child(wb_title)
	_status_label = Label.new()
	_status_label.add_theme_color_override("font_color", INK2)
	wb_head.add_child(_status_label)
	var wb_sp := Control.new()
	wb_sp.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	wb_head.add_child(wb_sp)
	_capacity_label = Label.new()
	_capacity_label.add_theme_color_override("font_color", INK3)
	wb_head.add_child(_capacity_label)
	var levers_scroll := ScrollContainer.new()
	levers_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	wb.add_child(levers_scroll)
	_levers_box = VBoxContainer.new()
	_levers_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_levers_box.add_theme_constant_override("separation", 2)
	levers_scroll.add_child(_levers_box)
	var cart_lbl := Label.new()
	cart_lbl.text = "提案(原子批 · 一起过或一起拒)"
	cart_lbl.add_theme_color_override("font_color", INK3)
	cart_lbl.add_theme_font_size_override("font_size", 11)
	wb.add_child(cart_lbl)
	var cart_scroll := ScrollContainer.new()
	cart_scroll.custom_minimum_size = Vector2(0, 36)
	cart_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	wb.add_child(cart_scroll)
	_cart_box = HBoxContainer.new()
	_cart_box.add_theme_constant_override("separation", 6)
	cart_scroll.add_child(_cart_box)
	var cart_row := HBoxContainer.new()
	cart_row.add_theme_constant_override("separation", 8)
	wb.add_child(cart_row)
	_submit_btn = Button.new()
	_submit_btn.text = "提交提案"
	_submit_btn.pressed.connect(_submit_cart)
	cart_row.add_child(_submit_btn)
	_pass_btn = Button.new()
	_pass_btn.text = "本次不动"
	_pass_btn.pressed.connect(_submit_pass)
	cart_row.add_child(_pass_btn)
	_cart_cost = Label.new()
	_cart_cost.add_theme_color_override("font_color", INK3)
	cart_row.add_child(_cart_cost)

	var tl_panel := PanelContainer.new()
	split.add_child(tl_panel)
	var tl := VBoxContainer.new()
	tl_panel.add_child(tl)
	var tl_lbl := Label.new()
	tl_lbl.text = "事件时间线"
	tl_lbl.add_theme_font_size_override("font_size", 14)
	tl.add_child(tl_lbl)
	var ev_scroll := ScrollContainer.new()
	ev_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tl.add_child(ev_scroll)
	_events_box = VBoxContainer.new()
	_events_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ev_scroll.add_child(_events_box)

	# 危机横幅
	_banner = PanelContainer.new()
	_banner.visible = false
	_banner.add_theme_stylebox_override("panel", _style(Color("f7e3e1"), CRIT, 6, 12))
	shell.add_child(_banner)
	var bb := HBoxContainer.new()
	bb.add_theme_constant_override("separation", 12)
	_banner.add_child(bb)
	var bt := Label.new()
	bt.text = "🚨 紧急会议"
	bt.add_theme_font_size_override("font_size", 15)
	bt.add_theme_color_override("font_color", CRIT)
	bb.add_child(bt)
	_banner_body = Label.new()
	_banner_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_banner_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bb.add_child(_banner_body)

	# 驱动条
	var drive := HBoxContainer.new()
	drive.add_theme_constant_override("separation", 8)
	shell.add_child(drive)
	drive.add_child(_button("新开局", func() -> void:
		_release_hist.clear()
		_seen_release.clear()
		_cart.clear()
		_send({"command": "new_game"})
		_send({"command": "get_schema"})))
	drive.add_child(_button("步进 1 日", func() -> void:
		_send({"command": "advance", "ticks": 1})))
	_play_btn = _button("▶ 播放", func() -> void:
		_playing = not _playing
		_render())
	drive.add_child(_play_btn)
	for s: int in SPEEDS:
		var b := Button.new()
		b.text = "%d×" % s
		b.toggle_mode = true
		b.button_pressed = s == _speed
		var chosen := s
		b.pressed.connect(func() -> void:
			_speed = chosen
			_render())
		_speed_btns.append(b)
		drive.add_child(b)
	drive.add_child(_button("⏭ 到下一事件", func() -> void:
		_send({"command": "advance", "ticks": 100})))
	drive.add_child(_button("💥 供给冲击", func() -> void:
		_send({"command": "trigger_shock"})))
	var dsp := Control.new()
	dsp.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	drive.add_child(dsp)
	_paused_label = Label.new()
	_paused_label.add_theme_color_override("font_color", ACCENT)
	drive.add_child(_paused_label)

	# 判决吐司
	_toast = PanelContainer.new()
	_toast.visible = false
	_toast.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	_toast.position = Vector2(-430, 56)
	_toast.custom_minimum_size = Vector2(400, 0)
	_toast_label = Label.new()
	_toast_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_toast.add_child(_toast_label)
	add_child(_toast)
	_toast_timer = Timer.new()
	_toast_timer.one_shot = true
	_toast_timer.wait_time = 4.5
	_toast_timer.timeout.connect(func() -> void: _toast.visible = false)
	add_child(_toast_timer)


func _button(text: String, callback: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.pressed.connect(callback)
	return b


# ---------------- 播放循环 ----------------
func _on_play_tick() -> void:
	if not _playing:
		return
	if _awaiting():
		_playing = false
		_render()
		return
	_send({"command": "advance", "ticks": _speed})


# ---------------- 数据 ----------------
func _index_schema() -> void:
	_groups.clear()
	for lever: Dictionary in _schema.get("levers", []):
		var g := str(lever.get("decision_group", "其他"))
		if not _groups.has(g):
			_groups[g] = []
	# 保序追加
	for lever: Dictionary in _schema.get("levers", []):
		_groups[str(lever.get("decision_group", "其他"))].append(lever)


func _ingest_releases() -> void:
	var obs: Dictionary = _snapshot.get("observation", {})
	for rel: Dictionary in obs.get("releases", []):
		if rel.get("value") == null:
			continue
		var sid := str(rel.get("series_id"))
		var at := int(rel.get("released_at_tick", -1))
		if int(_seen_release.get(sid, -1)) >= at:
			continue
		_seen_release[sid] = at
		if not _release_hist.has(sid):
			_release_hist[sid] = []
		var arr: Array = _release_hist[sid]
		arr.append(float(rel.get("value")))
		if arr.size() > 24:
			arr.pop_front()


func _awaiting() -> bool:
	return bool(_snapshot.get("awaiting_human", false))


func _contexts() -> Array:
	return _snapshot.get("contexts", [])


func _active_context() -> Dictionary:
	for ctx: Dictionary in _contexts():
		if bool(ctx.get("emergency", false)):
			return ctx
	return _contexts()[0] if not _contexts().is_empty() else {}


func _maybe_toast(v: Dictionary) -> void:
	var key := str(v.get("decision_id", v.get("proposal_id", "")))
	if key == _last_toasted or key.is_empty():
		return
	_last_toasted = key
	var status := str(v.get("status", "?"))
	var ok := status.begins_with("accepted")
	var text := ("✅ " if ok else "⛔ ") + "判决:" + status
	var reason := str(v.get("reason_code", ""))
	if not reason.is_empty() and reason != "<null>":
		text += "\nreason: " + reason
	if v.get("effective_tick") != null:
		text += "\n生效 tick:" + str(v.get("effective_tick"))
	_show_toast(text, ok)


func _show_toast(text: String, ok: bool) -> void:
	_toast_label.text = text
	_toast_label.add_theme_color_override("font_color", INK if ok else CRIT)
	_toast.visible = true
	_toast_timer.start()


# ---------------- 渲染 ----------------
func _fmt_date(t: int) -> String:
	return "第 %d 年 第 %d 季 第 %d 日" % [t / TPY + 1, (t % TPY) / QT + 1, (t % TPY) % QT + 1]


func _fmt_value(sid: String, v: float) -> String:
	match sid:
		"unemployment_rate", "gov_deficit_to_gdp", "poverty_rate":
			return "%.1f%%" % (v * 100.0)
		"inflation", "policy_rate":
			return "%.2f%%" % (v * TPY * 100.0)
		"price_index":
			return "%.3f" % v
		_:
			return "%.1f" % v


func _render() -> void:
	var t := int(_snapshot.get("tick", 0))
	_clock_label.text = _fmt_date(t)
	_tick_label.text = "tick %d" % t
	_play_btn.text = "⏸ 暂停" if _playing else "▶ 播放"
	for i in _speed_btns.size():
		_speed_btns[i].button_pressed = SPEEDS[i] == _speed
	_paused_label.text = "⏸ AWAITING_HUMAN · 引擎冻结" if _awaiting() else ""
	_render_tiles()
	_render_workbench()
	_render_events()
	_render_banner()


func _render_tiles() -> void:
	for child in _tiles_box.get_children():
		child.queue_free()
	var obs: Dictionary = _snapshot.get("observation", {})
	var by_id: Dictionary = {}
	for rel: Dictionary in obs.get("releases", []):
		by_id[str(rel.get("series_id"))] = rel
	var truth: Dictionary = _snapshot.get("metrics", {})
	var t := int(_snapshot.get("tick", 0))
	for sid: String in HEADLINE:
		var tile := PanelContainer.new()
		tile.custom_minimum_size = Vector2(164, 96)
		var v := VBoxContainer.new()
		v.add_theme_constant_override("separation", 1)
		tile.add_child(v)
		var lbl := Label.new()
		lbl.text = str(SERIES_LABEL.get(sid, sid))
		lbl.add_theme_font_size_override("font_size", 11)
		lbl.add_theme_color_override("font_color", INK2)
		v.add_child(lbl)
		var rel: Dictionary = by_id.get(sid, {})
		if rel.is_empty() or rel.get("value") == null:
			var missing := Label.new()
			missing.text = "暂无数据"
			missing.add_theme_color_override("font_color", INK3)
			v.add_child(missing)
			var why := Label.new()
			why.text = str(rel.get("missing_reason", "not_in_spec"))
			why.add_theme_font_size_override("font_size", 9)
			why.add_theme_color_override("font_color", INK3)
			v.add_child(why)
		else:
			var val := Label.new()
			val.text = _fmt_value(sid, float(rel.get("value")))
			val.add_theme_font_size_override("font_size", 19)
			v.add_child(val)
			var meta := Label.new()
			meta.text = "发布 t=%d · T−%d" % [
				int(rel.get("released_at_tick", 0)),
				t - int(rel.get("reference_end_tick", t))]
			meta.add_theme_font_size_override("font_size", 9)
			meta.add_theme_color_override("font_color", INK3)
			v.add_child(meta)
			if _god and truth.has(sid):
				var tv := Label.new()
				tv.text = "真值 " + _fmt_value(sid, float(truth.get(sid, 0.0)))
				tv.add_theme_font_size_override("font_size", 9)
				tv.add_theme_color_override("font_color", WARN)
				v.add_child(tv)
			var chart = MetricChartScript.new()
			chart.custom_minimum_size = Vector2(0, 20)
			if chart.has_method("set_series"):
				chart.set_series(_release_hist.get(sid, []))
			v.add_child(chart)
		_tiles_box.add_child(tile)


func _render_workbench() -> void:
	for child in _levers_box.get_children():
		child.queue_free()
	var open := _awaiting()
	var ctx := _active_context()
	var emg := bool(ctx.get("emergency", false))
	_status_label.text = ("🚨 紧急会议 · 白名单可动" if emg else "例会开启 · 可提案") if open \
		else "会议未开 · 只读(推进至会议自动暂停)"
	var remaining: Variant = ctx.get("admin_remaining")
	_capacity_label.text = ("行政容量:" + str(remaining)) if remaining != null else ""
	var permitted: Dictionary = {}
	for item: Dictionary in ctx.get("permitted_actions", []):
		permitted[str(item.get("lever"))] = item
	var current_policy: Dictionary = ctx.get("current_policy", {})
	var pending_by_lever: Dictionary = {}
	for p in _snapshot.get("pending", []):
		if p is Dictionary:
			pending_by_lever[str((p as Dictionary).get("lever", ""))] = p
	for g: String in _groups.keys():
		var gh := Label.new()
		gh.text = g.to_upper()
		gh.add_theme_font_size_override("font_size", 10)
		gh.add_theme_color_override("font_color", INK3)
		_levers_box.add_child(gh)
		for lever: Dictionary in _groups[g]:
			_levers_box.add_child(
				_lever_row(lever, permitted, pending_by_lever, open, emg, current_policy))
	_render_cart(open)


func _lever_row(lever: Dictionary, permitted: Dictionary, pending: Dictionary,
		open: bool, emg: bool, current_policy: Dictionary = {}) -> Control:
	var name := str(lever.get("name"))
	var perm: Dictionary = permitted.get(name, {})
	if not perm.has("current_value") and current_policy.has(name):
		perm = perm.duplicate()
		perm["current_value"] = current_policy.get(name)
	var allowed := open and bool(perm.get("allowed", false)) \
		and (not emg or bool(lever.get("emergency", false)))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	var name_box := VBoxContainer.new()
	name_box.custom_minimum_size = Vector2(250, 0)
	name_box.add_theme_constant_override("separation", 0)
	var nm := Label.new()
	nm.text = name
	name_box.add_child(nm)
	var small := Label.new()
	small.text = "时滞%d · 冷却%d%s" % [
		int(lever.get("implementation_lag", 0)),
		int(lever.get("min_hold_ticks", 0)),
		" · 紧急✓" if bool(lever.get("emergency", false)) else ""]
	small.add_theme_font_size_override("font_size", 9)
	small.add_theme_color_override("font_color", INK3)
	name_box.add_child(small)
	row.add_child(name_box)
	var cur_v: Variant = perm.get("current_value")
	var cur := Label.new()
	cur.custom_minimum_size = Vector2(92, 0)
	cur.text = _lever_value_text(cur_v) if perm.has("current_value") else "—"
	var pend: Variant = pending.get(name)
	if pend is Dictionary:
		cur.text += "\n→ %s(t=%s)" % [
			_lever_value_text((pend as Dictionary).get("value")),
			str((pend as Dictionary).get("effective_tick", "?"))]
		cur.add_theme_font_size_override("font_size", 11)
		cur.add_theme_color_override("font_color", WARN)
	row.add_child(cur)
	row.add_child(_lever_control(lever, perm, allowed))
	var info := Label.new()
	var reason := str(perm.get("reason_code", ""))
	if emg and not bool(lever.get("emergency", false)):
		info.text = "不在紧急白名单"
	elif not allowed and not reason.is_empty() and reason != "<null>":
		info.text = reason
	info.add_theme_font_size_override("font_size", 10)
	info.add_theme_color_override("font_color", INK3)
	row.add_child(info)
	row.modulate = Color(1, 1, 1, 1.0 if allowed else 0.55)
	return row


func _lever_value_text(v: Variant) -> String:
	if v == null:
		return "未设"
	if v is bool:
		return "开" if v else "关"
	if v is String:
		return v
	var f := float(v)
	if absf(f) < 0.01 and f != 0.0:
		return "%.5f" % f
	return "%.3f" % f


func _lever_control(lever: Dictionary, perm: Dictionary, allowed: bool) -> Control:
	var name := str(lever.get("name"))
	var kind := str(perm.get("value_kind", lever.get("value_kind", "number")))
	var choices: Array = perm.get("choices", lever.get("choices", []))
	var box := HBoxContainer.new()
	box.add_theme_constant_override("separation", 4)
	var base_v: Variant = perm.get("current_value")
	var cur: Variant = _cart.get(name, base_v)
	if not choices.is_empty():
		for opt in choices:
			var b := Button.new()
			b.text = str(opt)
			b.toggle_mode = true
			b.button_pressed = str(cur) == str(opt)
			b.disabled = not allowed
			var value := str(opt)
			b.pressed.connect(func() -> void:
				_cart_set(name, value))
			box.add_child(b)
		return box
	if kind == "bool":
		var opts := [["关", false], ["开", true]]
		for opt in opts:
			var b := Button.new()
			b.text = opt[0]
			b.toggle_mode = true
			b.button_pressed = cur == opt[1]
			b.disabled = not allowed
			var value: bool = opt[1]
			b.pressed.connect(func() -> void:
				_cart_set(name, value))
			box.add_child(b)
		return box
	# 数值步进器:±control_scale,钳制于 current±max_step 与取值域
	var dec := Button.new()
	dec.text = "−"
	box.add_child(dec)
	var vl := Label.new()
	vl.custom_minimum_size = Vector2(84, 0)
	vl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vl.text = _lever_value_text(cur)
	if _cart.has(name):
		vl.add_theme_color_override("font_color", ACCENT)
	box.add_child(vl)
	var inc := Button.new()
	inc.text = "＋"
	box.add_child(inc)
	var numeric := base_v != null and not (base_v is bool) and not (base_v is String)
	dec.disabled = not allowed or not numeric
	inc.disabled = not allowed or not numeric
	if numeric:
		var base := float(base_v)
		var scale := float(perm.get("control_scale", lever.get("control_scale", 0.01)))
		if scale <= 0.0:
			scale = 0.01
		var lo := float(perm.get("minimum", lever.get("minimum", -1e30)))
		var hi := float(perm.get("maximum", lever.get("maximum", 1e30)))
		var mstep: Variant = perm.get("max_step", lever.get("max_step"))
		if mstep != null:
			lo = maxf(lo, base - float(mstep))
			hi = minf(hi, base + float(mstep))
		var lo2 := lo
		var hi2 := hi
		dec.pressed.connect(func() -> void:
			_cart_set(name, clampf(float(_cart.get(name, base)) - scale, lo2, hi2)))
		inc.pressed.connect(func() -> void:
			_cart_set(name, clampf(float(_cart.get(name, base)) + scale, lo2, hi2)))
	return box


func _cart_set(lever_name: String, value: Variant) -> void:
	_cart[lever_name] = value
	_render_workbench()


func _render_cart(open: bool) -> void:
	for child in _cart_box.get_children():
		child.queue_free()
	if _cart.is_empty():
		var empty := Label.new()
		empty.text = "购物车为空"
		empty.add_theme_color_override("font_color", INK3)
		_cart_box.add_child(empty)
	for lever_name: String in _cart.keys():
		var chip := Button.new()
		chip.text = "%s → %s  ×" % [lever_name, _lever_value_text(_cart[lever_name])]
		var key := lever_name
		chip.pressed.connect(func() -> void:
			_cart.erase(key)
			_render_workbench())
		_cart_box.add_child(chip)
	_submit_btn.disabled = not open or _cart.is_empty()
	_pass_btn.disabled = not open
	_cart_cost.text = ("动作 %d 项 · 生效按各杠杆时滞" % _cart.size()) \
		if not _cart.is_empty() else ""


func _submit_cart() -> void:
	var ctx := _active_context()
	if ctx.is_empty():
		return
	var actions: Array = []
	for lever_name: String in _cart.keys():
		actions.append({"lever": lever_name, "value": _cart[lever_name]})
	_send({
		"command": "resolve_context",
		"context_id": str(ctx.get("context_id")),
		"actions": actions,
	})
	_cart.clear()


func _submit_pass() -> void:
	var ctx := _active_context()
	if ctx.is_empty():
		return
	_send({
		"command": "resolve_context",
		"context_id": str(ctx.get("context_id")),
		"actions": [],
	})
	_cart.clear()


func _render_events() -> void:
	for child in _events_box.get_children():
		child.queue_free()
	var merged: Array = []
	for ev in _snapshot.get("events", []):
		if ev is Dictionary:
			merged.append(ev)
	for ev in _snapshot.get("shock_events", []):
		if ev is Dictionary:
			merged.append(ev)
	merged.reverse()
	for ev: Dictionary in merged.slice(0, 40):
		var line := Label.new()
		line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		var kind := str(ev.get("event_type", ev.get("kind", "event")))
		var t_ev: Variant = ev.get("boundary_tick", ev.get("tick", "?"))
		var detail := str(ev.get("status", ev.get("shock_id", ev.get("lever", ""))))
		line.text = "t%s · %s%s" % [str(t_ev), kind,
			("" if detail.is_empty() else " · " + detail)]
		line.add_theme_font_size_override("font_size", 11)
		line.add_theme_color_override("font_color", INK2)
		_events_box.add_child(line)


func _render_banner() -> void:
	var ctx := _active_context()
	var emg := bool(ctx.get("emergency", false))
	_banner.visible = emg
	if emg:
		_banner_body.text = "触发器:%s · 仅紧急白名单杠杆可动 · 决策前引擎冻结" \
			% str(ctx.get("emergency_trigger", "—"))
