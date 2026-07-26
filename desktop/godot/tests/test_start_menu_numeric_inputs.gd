extends SceneTree

const StartMenuScript := preload("res://scripts/start_menu.gd")


func _init() -> void:
	_run.call_deferred()


func _run() -> void:
	var menu := StartMenuScript.new()
	root.add_child(menu)
	await process_frame
	menu._screen = "wizard"
	menu._step = 3
	menu._render()
	await process_frame

	var population := _line_edit(menu, "80")
	assert(population != null)
	population.text_submitted.emit("95")
	await process_frame
	assert(menu._countries[0]["overrides"]["demographics_population"] == 95)

	var invalid_population := _line_edit(menu, "95")
	assert(invalid_population != null)
	invalid_population.text_submitted.emit("95.5")
	await process_frame
	assert(menu._countries[0]["overrides"]["demographics_population"] == 95)

	var productivity := _line_edit(menu, "1.20")
	assert(productivity != null)
	productivity.text_submitted.emit("1.75")
	await process_frame
	assert(is_equal_approx(
		float(menu._countries[0]["overrides"]["a"]), 1.75))

	menu._step = 4
	menu._render()
	await process_frame
	var policy_number := _line_edit(menu, "0.180")
	assert(policy_number != null)
	policy_number.text_submitted.emit("0.25")
	await process_frame
	assert(is_equal_approx(
		float(menu._policy_values["0.treasury.gov_consumption_share"]), 0.25))

	var policy_percent := _line_edit(menu, "22.0%")
	assert(policy_percent != null)
	policy_percent.text_submitted.emit("30")
	await process_frame
	assert(is_equal_approx(
		float(menu._policy_values["0.treasury.tax_income_rate"]), 0.30))

	menu._policy_seat = "cb"
	menu._render()
	await process_frame
	var annual_rate := _line_edit(
		menu, menu._format("wizard.value.annual_rate", 1.99))
	assert(annual_rate != null)
	annual_rate.text_submitted.emit("4.00")
	await process_frame
	var daily_rate := pow(1.04, 1.0 / 365.0) - 1.0
	assert(is_equal_approx(
		float(menu._policy_values["0.cb.inflation_target"]), daily_rate))

	menu.queue_free()
	quit(0)


func _line_edit(node: Node, text: String) -> LineEdit:
	for child: Node in node.get_children():
		if child is LineEdit and (child as LineEdit).text == text:
			return child as LineEdit
		var nested := _line_edit(child, text)
		if nested != null:
			return nested
	return null
