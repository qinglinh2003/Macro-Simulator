extends SceneTree

const MainScript := preload("res://scripts/main.gd")
const LocaleCatalogScript := preload("res://scripts/localization.gd")


func _init() -> void:
	_run.call_deferred()


func _run() -> void:
	LocaleCatalogScript.set_locale("zh-CN")
	OS.set_environment("MACRO_SIM_SKIP_START_MENU", "1")
	var game := MainScript.new()
	root.add_child(game)
	await process_frame
	game._render()
	await process_frame
	assert(
		(game._n["seat_treasury"] as Button).text
		== LocaleCatalogScript.text("seat.treasury")
	)
	assert(
		(game._n["seat_central_bank"] as Button).text
		== LocaleCatalogScript.text("seat.central_bank")
	)
	assert(not _contains_locale_token(game))
	game.queue_free()
	OS.set_environment("MACRO_SIM_SKIP_START_MENU", "")
	quit(0)


func _contains_locale_token(node: Node) -> bool:
	if node is Label and "@{" in (node as Label).text:
		return true
	if node is Button and "@{" in (node as Button).text:
		return true
	if node is Control and "@{" in (node as Control).tooltip_text:
		return true
	for child in node.get_children():
		if _contains_locale_token(child):
			return true
	return false
