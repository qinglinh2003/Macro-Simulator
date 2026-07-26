extends SceneTree

const MainScript := preload("res://scripts/main.gd")
const LocaleCatalogScript := preload("res://scripts/localization.gd")


func _init() -> void:
	_run.call_deferred()


func _run() -> void:
	LocaleCatalogScript.set_locale("zh_CN")
	OS.set_environment("MACRO_SIM_SKIP_START_MENU", "1")
	var game := MainScript.new()
	root.add_child(game)
	await process_frame
	await process_frame

	var menu_button := _button_with_text(
		game,
		"⌂  " + LocaleCatalogScript.text(
			"desktop.main.fragment.d8c47e9776cf1082"))
	assert(menu_button != null)
	game._playing = true
	menu_button.pressed.emit()
	await process_frame
	assert(not game._playing)
	assert(
		LocaleCatalogScript.resolve(str(game._confirm["title"]))
		== LocaleCatalogScript.text(
			"desktop.main.fragment.e34e61a243bec5e1")
	)
	game._confirm_cancel()
	await process_frame
	assert(game._playing)

	menu_button.pressed.emit()
	await process_frame
	game._confirm_yes()
	await process_frame
	assert(game._start_menu != null)
	assert(game._start_menu.visible)
	assert(game._start_menu._screen == "home")
	assert(game._start_menu._can_continue)

	var continue_button := _button_with_label(
		game._start_menu, LocaleCatalogScript.text("menu.continue"))
	assert(continue_button != null)
	continue_button.pressed.emit()
	await process_frame
	assert(not game._start_menu.visible)

	game.queue_free()
	OS.set_environment("MACRO_SIM_SKIP_START_MENU", "")
	quit(0)


func _button_with_text(node: Node, text: String) -> Button:
	for child: Node in node.get_children():
		if child is Button and (child as Button).text == text:
			return child as Button
		var nested := _button_with_text(child, text)
		if nested != null:
			return nested
	return null


func _button_with_label(node: Node, text: String) -> Button:
	for child: Node in node.get_children():
		if child is Button and _has_label(child, text):
			return child as Button
		var nested := _button_with_label(child, text)
		if nested != null:
			return nested
	return null


func _has_label(node: Node, text: String) -> bool:
	for child: Node in node.get_children():
		if child is Label and (child as Label).text == text:
			return true
		if _has_label(child, text):
			return true
	return false
