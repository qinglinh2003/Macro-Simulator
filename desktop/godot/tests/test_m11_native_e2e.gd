extends SceneTree

const MainScript := preload("res://scripts/main.gd")
const DriverScript := preload("res://tests/m11_native_e2e_driver.gd")

var _game


func _init() -> void:
	_run.call_deferred()


func _run() -> void:
	OS.set_environment("MACRO_SIM_SKIP_START_MENU", "1")
	_game = MainScript.new()
	root.add_child(_game)
	var driver = DriverScript.new()
	var succeeded := await driver.run(_game)
	_game.queue_free()
	OS.set_environment("MACRO_SIM_SKIP_START_MENU", "")
	quit(0 if succeeded else 2)
