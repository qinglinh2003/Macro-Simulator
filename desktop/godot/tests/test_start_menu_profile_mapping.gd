extends SceneTree

const StartMenuScript := preload("res://scripts/start_menu.gd")
const LocaleCatalogScript := preload("res://scripts/localization.gd")


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

	assert(_has_label(menu, LocaleCatalogScript.text("wizard.mapping.profile")))
	assert(_has_label(menu, LocaleCatalogScript.text("wizard.mapping.population")))
	assert(menu._profile_mapping_enabled)
	assert(menu._population_mapping_enabled)

	var country: Dictionary = menu._countries[0]
	menu._select_profile(country, "symmetric")
	menu._set_structure_number(country, "a", 1.5)
	menu._set_structure_number(country, "demographics_population", 100)
	menu._set_structure_number(country, "n_firms_c", 20)

	assert(country["baseline_overrides"]["a"] == 1.5)
	assert(country["baseline_overrides"]["demographics_population"] == 100)
	assert(country["baseline_overrides"]["n_firms_c"] == 20)

	menu._select_profile(country, "advanced")
	assert(is_equal_approx(
		float(menu._effective_structure_value(country, "a")), 1.8))
	assert(menu._effective_structure_value(
		country, "demographics_population") == 100)
	assert(menu._effective_structure_value(country, "n_firms_c") == 20)

	menu._select_profile(country, "developing")
	assert(is_equal_approx(
		float(menu._effective_structure_value(country, "a")), 1.125))
	assert(menu._effective_structure_value(
		country, "demographics_population") == 150)
	assert(menu._effective_structure_value(country, "n_firms_c") == 30)
	assert(menu._effective_structure_value(country, "n_banks") == 8)

	menu._profile_mapping_enabled = false
	menu._select_profile(country, "petrostate")
	assert(is_equal_approx(
		float(menu._effective_structure_value(country, "a")), 0.85))
	assert(menu._effective_structure_value(
		country, "demographics_population") == 80_000)
	assert(menu._effective_structure_value(country, "n_firms_c") == 1_200)

	menu._toggle_population_mapping()
	assert(not menu._population_mapping_enabled)
	menu._select_profile(country, "developing")
	assert(menu._effective_structure_value(
		country, "demographics_population") == 150_000)
	assert(menu._effective_structure_value(country, "n_firms_c") == 1_500)

	menu._select_profile(country, "symmetric")
	menu._toggle_population_mapping()
	assert(menu._population_mapping_enabled)
	for population in range(81, 89):
		menu._set_structure_number(
			country, "demographics_population", population)
	assert(menu._effective_structure_value(country, "n_firms_c") == 2)
	menu._set_structure_number(country, "demographics_population", 160)
	assert(menu._effective_structure_value(country, "n_firms_c") == 2)
	menu._set_structure_number(country, "n_firms_c", 30)
	menu._set_structure_number(country, "demographics_population", 80)
	assert(menu._effective_structure_value(country, "n_firms_c") == 15)

	var manifest: Dictionary = menu._country_manifest_overrides(country)
	assert(manifest["demographics_population"] == 80)
	assert(manifest["n_households"] == 80)
	assert(manifest["n_firms_c"] == 15)

	menu.queue_free()
	quit(0)


func _has_label(node: Node, text: String) -> bool:
	for child: Node in node.get_children():
		if child is Label and (child as Label).text == text:
			return true
		if _has_label(child, text):
			return true
	return false
