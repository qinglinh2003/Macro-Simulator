class_name MetricChart
extends Control

var _series: Array = []
var _spark_values: Array = []
var _spark := false


func _ready() -> void:
	if not _spark:
		custom_minimum_size = Vector2(620, 220)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func set_snapshot(snapshot: Dictionary) -> void:
	_series = snapshot.get("series", [])
	queue_redraw()


func set_series(values: Array) -> void:
	## 公报瓦片 sparkline 模式:仅一条折线 + 端点强调。
	_spark = true
	_spark_values = values
	queue_redraw()


func _draw_spark() -> void:
	if _spark_values.size() < 2:
		return
	var lo := INF
	var hi := -INF
	for v in _spark_values:
		lo = minf(lo, float(v))
		hi = maxf(hi, float(v))
	var span := hi - lo
	if span <= 0.0:
		span = 1.0
	var points := PackedVector2Array()
	var n := _spark_values.size()
	for i in n:
		points.append(Vector2(
			2.0 + (size.x - 6.0) * float(i) / float(n - 1),
			size.y - 3.0 - (size.y - 6.0) * (float(_spark_values[i]) - lo) / span))
	draw_polyline(points, Color("8ba3bc"), 1.4, true)
	draw_circle(points[n - 1], 2.4, Color("4fd1c5"))


func _draw() -> void:
	if _spark:
		_draw_spark()
		return
	var style := StyleBoxFlat.new()
	style.bg_color = Color("101a29")
	style.border_color = Color("243750")
	style.set_border_width_all(1)
	style.set_corner_radius_all(12)
	draw_style_box(style, Rect2(Vector2.ZERO, size))
	var plot := Rect2(Vector2(46, 34), size - Vector2(66, 66))
	for i in range(5):
		var y := plot.position.y + plot.size.y * float(i) / 4.0
		draw_line(Vector2(plot.position.x, y), Vector2(plot.end.x, y), Color("213149"), 1.0)
	draw_string(ThemeDB.fallback_font, Vector2(16, 22), "ECONOMIC PULSE", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color("7890aa"))
	draw_string(ThemeDB.fallback_font, Vector2(size.x - 270, 22), "Output", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("4fd1c5"))
	draw_string(ThemeDB.fallback_font, Vector2(size.x - 205, 22), "Unemployment", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("f6ad55"))
	draw_string(ThemeDB.fallback_font, Vector2(size.x - 105, 22), "Inflation", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("b794f4"))
	if _series.size() < 2:
		draw_string(ThemeDB.fallback_font, plot.get_center(), "Advance the simulation to build a history", HORIZONTAL_ALIGNMENT_CENTER, 0, 13, Color("60758d"))
		return
	draw_polyline(_points("real_output", plot, _range_for("real_output")), Color("4fd1c5"), 2.5, true)
	draw_polyline(_points("unemployment_rate", plot, _range_for("unemployment_rate")), Color("f6ad55"), 2.0, true)
	draw_polyline(_points("inflation", plot, _range_for("inflation")), Color("b794f4"), 2.0, true)


func _range_for(key: String) -> Vector2:
	var minimum := INF
	var maximum := -INF
	for point in _series:
		var value := float((point as Dictionary).get(key, 0.0))
		minimum = minf(minimum, value)
		maximum = maxf(maximum, value)
	if is_equal_approx(minimum, maximum):
		var padding := maxf(absf(minimum) * 0.1, 0.01)
		minimum -= padding
		maximum += padding
	return Vector2(minimum, maximum)


func _points(key: String, plot: Rect2, value_range: Vector2) -> PackedVector2Array:
	var points := PackedVector2Array()
	var denominator := maxf(value_range.y - value_range.x, 0.000001)
	for i in range(_series.size()):
		var x := plot.position.x + plot.size.x * float(i) / float(_series.size() - 1)
		var value := float((_series[i] as Dictionary).get(key, 0.0))
		var normalized := (value - value_range.x) / denominator
		points.append(Vector2(x, plot.end.y - normalized * plot.size.y))
	return points
