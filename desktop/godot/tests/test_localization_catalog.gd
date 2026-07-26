extends SceneTree

const LocaleCatalogScript := preload("res://scripts/localization.gd")


func _init() -> void:
	LocaleCatalogScript.set_locale("en")
	assert(LocaleCatalogScript.locale() == "en")
	assert(LocaleCatalogScript.text("menu.new") == "New simulation")
	assert(LocaleCatalogScript.resolve("@profile.advanced.name") == "Advanced")
	assert(
		LocaleCatalogScript.resolve("Create @{menu.new} now")
		== "Create New simulation now"
	)
	assert(LocaleCatalogScript.resolve("AUR") == "AUR")
	assert(LocaleCatalogScript.text("missing.key") == "missing.key")
	assert(LocaleCatalogScript.text("desktop.free.queue_title") == "Next-day policy queue")

	LocaleCatalogScript.set_locale("zh-CN")
	assert(LocaleCatalogScript.locale() == "zh_CN")
	assert(LocaleCatalogScript.text("menu.new") != "New simulation")
	assert(not LocaleCatalogScript.text("menu.new").is_empty())
	assert(
		LocaleCatalogScript.resolve("@{menu.new}")
		== LocaleCatalogScript.text("menu.new")
	)
	assert(
		LocaleCatalogScript.text("desktop.free.queue_title")
		!= "Next-day policy queue"
	)
	quit(0)
