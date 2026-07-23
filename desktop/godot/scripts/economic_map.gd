class_name EconomicMap
extends Control

var _metrics: Dictionary = {}
var _tick := 0
var _shock_active := false


func set_snapshot(snapshot: Dictionary) -> void:
	_metrics = snapshot.get("metrics", {})
	_tick = int(snapshot.get("tick", 0))
	_shock_active = not (snapshot.get("active_shocks", []) as Array).is_empty()
	queue_redraw()


func _ready() -> void:
	custom_minimum_size = Vector2(620, 330)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _draw() -> void:
	draw_style_box(_box(Color("101a29"), Color("243750"), 14), Rect2(Vector2.ZERO, size))
	var output := float(_metrics.get("real_output", 0.0))
	var employment := clampf(1.0 - float(_metrics.get("unemployment_rate", 0.0)), 0.0, 1.0)
	var pulse := 0.65 + 0.35 * sin(float(_tick) * 0.6)
	var flow_color := Color("4fd1c5") if not _shock_active else Color("ff7657")
	var points := {
		"Households": Vector2(size.x * 0.20, size.y * 0.52),
		"Firms": Vector2(size.x * 0.50, size.y * 0.28),
		"Treasury": Vector2(size.x * 0.79, size.y * 0.52),
		"Energy": Vector2(size.x * 0.50, size.y * 0.76),
	}
	_draw_flow(points["Households"], points["Firms"], flow_color, 2.0 + 2.0 * employment)
	_draw_flow(points["Firms"], points["Treasury"], Color("78a9ff"), 2.0 + pulse)
	_draw_flow(points["Treasury"], points["Households"], Color("b794f4"), 2.0 + pulse)
	_draw_flow(points["Energy"], points["Firms"], flow_color, 2.0 + pulse)
	_draw_node(points["Households"], "HOUSEHOLDS", "Employment %.1f%%" % (employment * 100.0), Color("4fd1c5"))
	_draw_node(points["Firms"], "FIRMS", "Output %.1f" % output, Color("78a9ff"))
	_draw_node(points["Treasury"], "TREASURY", "Policy authority", Color("b794f4"))
	_draw_node(points["Energy"], "ENERGY", "Price %.2f" % float(_metrics.get("energy_price", 0.0)), Color("f6ad55"))
	var banner := "SUPPLY DISRUPTION ACTIVE" if _shock_active else "LIVE ECONOMY NETWORK"
	var banner_color := Color("ff7657") if _shock_active else Color("7890aa")
	draw_string(ThemeDB.fallback_font, Vector2(18, 28), banner, HORIZONTAL_ALIGNMENT_LEFT, -1, 15, banner_color)


func _draw_flow(from: Vector2, to: Vector2, color: Color, width: float) -> void:
	var direction := (to - from).normalized()
	var start := from + direction * 70.0
	var finish := to - direction * 70.0
	draw_line(start, finish, Color(color, 0.72), width, true)
	var side := Vector2(-direction.y, direction.x)
	draw_colored_polygon(PackedVector2Array([
		finish,
		finish - direction * 12.0 + side * 6.0,
		finish - direction * 12.0 - side * 6.0,
	]), color)


func _draw_node(center: Vector2, title: String, detail: String, accent: Color) -> void:
	var rect := Rect2(center - Vector2(72, 38), Vector2(144, 76))
	draw_style_box(_box(Color("172538"), accent, 10), rect)
	draw_string(ThemeDB.fallback_font, center + Vector2(-62, -5), title, HORIZONTAL_ALIGNMENT_CENTER, 124, 15, Color("ecf3fb"))
	draw_string(ThemeDB.fallback_font, center + Vector2(-62, 19), detail, HORIZONTAL_ALIGNMENT_CENTER, 124, 12, Color("91a6bd"))


func _box(background: Color, border: Color, radius: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(radius)
	return style
