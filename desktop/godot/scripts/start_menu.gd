extends Control
## Start Menu v31 — Godot reproduction of docs/design/start_menu_v31.dc.html.
## Every visible simulation option is serialized into NewGameSpec v1 and
## validated by the Python engine before the current run is replaced.

const LocaleCatalogScript := preload("res://scripts/localization.gd")

signal launch_requested(config: Dictionary)
signal continue_requested

const BG := Color("e9edf2")
const PAPER := Color("ffffff")
const PANEL := Color("f6f8fb")
const PANEL2 := Color("f1f4f8")
const LINE := Color("d3dce6")
const LINE2 := Color("e6ebf1")
const INK := Color("16232f")
const INK2 := Color("586a7b")
const INK3 := Color("849098")
const MUTED := Color("96a3b2")
const TEAL := Color("0f9d90")
const TEAL_DK := Color("0c8579")
const TEAL_BG := Color("e6f5f0")
const TEAL_BD := Color("9ad9d0")
const BLUE := Color("2f6fd0")
const BLUE_BG := Color("e6effb")
const BLUE_BD := Color("b6d1f2")
const PURPLE := Color("7a4fd0")
const AMBER := Color("c17d16")
const AMBER_BG := Color("fbf3e2")
const AMBER_BD := Color("e3c489")
const RED := Color("d24a34")
const RED_BG := Color("fdeee9")
const RED_BD := Color("f0bcae")
const GREEN := Color("1f9d63")
const GREEN_BG := Color("e3f4ea")
const GREEN_BD := Color("9ddcb8")
const SECONDS_PER_DAY := 86_400
const MIN_START_YEAR := 1900
const MAX_START_YEAR := 2200
const COUNTRY_SCALE_FIELDS := [
	"n_firms_c", "n_firms_k", "n_firms_e", "n_builders", "n_banks",
]
const POPULATION_LINKED_FIELDS := [
	"n_firms_c", "n_firms_k", "n_firms_e", "n_builders",
]

const STEP_META := [
	["@step.scenario", "SCENARIO"], ["@step.world", "WORLD"],
	["@step.countries", "COUNTRIES"], ["@step.policy", "POLICY"],
	["@step.review", "REVIEW"],
]

const SCENARIOS := [
	{"id": "sandbox", "name": "@scenario.sandbox.name", "desc": "@scenario.sandbox.desc", "caps": "@scenario.sandbox.caps", "duration": "@scenario.sandbox.duration", "reduced": false},
	{"id": "oil", "name": "@scenario.oil.name", "desc": "@scenario.oil.desc", "caps": "@scenario.oil.caps", "duration": "@scenario.oil.duration", "reduced": true},
	{"id": "gfc", "name": "@scenario.gfc.name", "desc": "@scenario.gfc.desc", "caps": "@scenario.gfc.caps", "duration": "@scenario.gfc.duration", "reduced": true},
	{"id": "pandemic", "name": "@scenario.pandemic.name", "desc": "@scenario.pandemic.desc", "caps": "@scenario.pandemic.caps", "duration": "@scenario.pandemic.duration", "reduced": true},
	{"id": "disaster", "name": "@scenario.disaster.name", "desc": "@scenario.disaster.desc", "caps": "@scenario.disaster.caps", "duration": "@scenario.disaster.duration", "reduced": true},
]

const PROFILES := {
	"symmetric": {"name": "@profile.symmetric.name", "desc": "@profile.symmetric.desc", "scale": 1.0, "prod": 1.0, "nec": 0.50},
	"advanced": {"name": "@profile.advanced.name", "desc": "@profile.advanced.desc", "scale": 1.0, "prod": 1.2, "nec": 0.50},
	"developing": {"name": "@profile.developing.name", "desc": "@profile.developing.desc", "scale": 1.5, "prod": 0.75, "nec": 0.65},
	"entrepot": {"name": "@profile.entrepot.name", "desc": "@profile.entrepot.desc", "scale": 0.4, "prod": 1.15, "nec": 0.50},
	"petrostate": {"name": "@profile.petrostate.name", "desc": "@profile.petrostate.desc", "scale": 0.8, "prod": 0.85, "nec": 0.50},
	"custom": {"name": "@profile.custom.name", "desc": "@profile.custom.desc", "scale": 1.0, "prod": 1.0, "nec": 0.50},
}

const COUNTRY_NAMES := [
	"@country.aurelia", "@country.borvia", "@country.petronia",
	"@country.calandria", "@country.meridi", "@country.novania",
	"@country.seraphi", "@country.turan",
]
const COUNTRY_CODES := ["AUR", "BOL", "PET", "KAL", "MER", "NOV", "SER", "TUR"]
const COUNTRY_COLORS := [Color("0f9d90"), Color("2f6fd0"), Color("7a4fd0"), Color("c17d16"), Color("1f9d63"), Color("d24a34"), Color("3f6db2"), Color("0c8579")]

const SEATS := [
	{"id": "cb", "name": "@seat.central_bank", "color": Color("2f6fd0"), "groups": "monetary · liquidity · fx (24)"},
	{"id": "treasury", "name": "@seat.treasury", "color": Color("0f9d90"), "groups": "fiscal · tax · debt (35)"},
	{"id": "regulator", "name": "@seat.regulator", "color": Color("7a4fd0"), "groups": "macropru · structural (28)"},
	{"id": "external", "name": "@seat.external", "color": Color("3f6db2"), "groups": "trade · migration (9)"},
	{"id": "energy", "name": "@seat.energy", "color": Color("c17d16"), "groups": "operations · structure (6)"},
]

const OCCUPANTS := [
	["human", "@occupant.human"], ["null", "@occupant.null"],
	["heuristic", "@occupant.heuristic"], ["rl", "@occupant.rl"],
	["scheduled", "@occupant.scheduled"], ["fuzz", "@occupant.fuzz"],
]

const SEAT_SCHEMA_KEYS := {
	"cb": "central_bank", "treasury": "treasury", "regulator": "regulator",
	"external": "external_affairs", "energy": "energy",
}

const STRUCT_GROUPS := [
	{"name": "@structure.scale", "fields": [["@field.initial_population", "demographics_population", "step"], ["@field.consumer_firms", "n_firms_c", "step"], ["@field.capital_firms", "n_firms_k", "step"], ["@field.energy_firms", "n_firms_e", "step"], ["@field.builders", "n_builders", "step"], ["@field.banks", "n_banks", "step"]]},
	{"name": "@structure.production", "fields": [["@field.base_productivity", "a", "step"], ["@field.capital_share", "alpha", "step"], ["@field.tfp_law", "tfp_law", "select"]]},
	{"name": "@structure.finance", "fields": [["@field.banking_system", "bank_enabled", "toggle"], ["@field.interbank_market", "interbank", "toggle"], ["@field.government_bonds", "bonds", "toggle"], ["@field.capital_market", "capital_market", "toggle"], ["@field.per_firm_equity", "per_firm_equity", "toggle"], ["@field.household_credit", "household_credit", "toggle"]]},
	{"name": "@structure.housing", "fields": [["@field.housing_registry", "housing_enabled", "toggle"], ["@field.housing_market", "housing_market_enabled", "toggle"], ["@field.mortgages", "mortgage_enabled", "toggle"], ["@field.rental_market", "housing_rental_enabled", "toggle"], ["@field.housing_construction", "housing_construction_enabled", "toggle"]]},
	{"name": "@structure.population_industry", "fields": [["@field.demographics", "demographics_enabled", "toggle"], ["@field.consumption_strata", "consumption_strata", "toggle"], ["@field.necessity_share", "necessity_share0", "step"], ["@field.energy_sector", "energy_enabled", "toggle"], ["@field.government", "government", "toggle"], ["@field.national_accounts", "national_accounts_metrics", "toggle"]]},
]

const POLICY_PREVIEW := {
	"treasury": [
		{"group": "@policy_group.fiscal_stance", "id": "fiscal_stance", "levers": [["@policy.gov_consumption_share", "gov_consumption_share", "number", 0.18, 0.005], ["@policy.gov_deficit_target", "gov_deficit_target", "percent", 0.03, 0.005], ["@policy.benefit_replacement", "benefit_replacement", "percent", 0.40, 0.02], ["@policy.job_guarantee", "job_guarantee", "bool", false, 1.0]]},
		{"group": "@policy_group.tax_transfers", "id": "tax_and_transfers", "levers": [["@policy.tax_income_rate", "tax_income_rate", "percent", 0.22, 0.01], ["@policy.tax_consumption_rate", "tax_consumption_rate", "percent", 0.15, 0.01], ["@policy.energy_subsidy_rate", "energy_subsidy_rate", "percent", 0.08, 0.01]]},
		{"group": "@policy_group.debt_management", "id": "debt_management", "levers": [["@policy.bond_finance_frac", "bond_finance_frac", "percent", 0.60, 0.05], ["@policy.bond_maturity", "bond_maturity", "integer", 20, 1.0]]},
	],
	"cb": [
		{"group": "@policy_group.monetary_stance", "id": "monetary_stance", "levers": [["@policy.monetary_regime", "monetary_regime", "regime", "taylor", 0], ["@policy.manual_policy_rate", "manual_policy_rate", "annual_rate", 0.000134, 0.000027], ["@policy.inflation_target", "inflation_target", "annual_rate", 0.000054, 0.000027], ["@policy.taylor_phi_pi", "taylor_phi_pi", "number", 1.5, 0.1]]},
		{"group": "@policy_group.liquidity", "id": "liquidity_operations", "levers": [["@policy.omo", "omo", "bool", true, 1.0], ["@policy.reserve_floor_frac", "reserve_floor_frac", "percent", 0.10, 0.005]]},
		{"group": "@policy_group.fx", "id": "fx_operations", "levers": [["@policy.fx_regime", "fx_regime", "fx", "float", 0], ["@policy.peg_anchor", "peg_anchor", "anchor", "", 0], ["@policy.capital_control", "capital_control", "percent", 0.0, 0.05]]},
	],
	"regulator": [{"group": "@policy_group.macroprudential", "id": "macroprudential", "levers": [["@policy.bank_leverage_cap", "bank_leverage_cap", "integer", 12, 1.0], ["@policy.mortgage_ltv_cap", "mortgage_ltv_cap", "percent", 0.85, 0.05], ["@policy.hh_credit_limit", "hh_credit_limit", "percent", 0.40, 0.05]]}, {"group": "@policy_group.structural_law", "id": "structural_law", "levers": [["@policy.household_bankruptcy", "household_bankruptcy", "bool", true, 1.0], ["@policy.bank_resolution_fund", "bank_resolution_fund", "bool", true, 1.0]]}],
	"external": [{"group": "@policy_group.trade_migration", "id": "trade_and_migration", "levers": [["@policy.tariff", "tariff", "percent", 0.05, 0.01], ["@policy.import_quota", "import_quota", "number", 1.0, 0.05], ["@policy.immigration_cap", "immigration_cap", "percent", 0.25, 0.05], ["@policy.export_subsidy", "export_subsidy", "percent", 0.0, 0.01]]}],
	"energy": [{"group": "@policy_group.energy_operations", "id": "energy_operations", "levers": [["@policy.energy_rationing", "energy_rationing", "ration", "market", 0], ["@policy.energy_price_cap", "energy_price_cap", "number", 0.0, 0.1], ["@policy.soe_price_at_cost", "soe_price_at_cost", "bool", false, 1.0]]}, {"group": "@policy_group.energy_structure", "id": "energy_structure", "levers": [["@policy.soe_efirm", "soe_efirm", "bool", false, 1.0]]}],
}

class _DotGrid extends Control:
	func _draw() -> void:
		for x in range(0, int(size.x) + 26, 26):
			for y in range(0, int(size.y) + 26, 26):
				draw_circle(Vector2(x, y), 1.0, Color("d0d9e3"))


var _sans: SystemFont
var _mono: SystemFont
var _surface: Control
var _screen := "home"
var _step := 1
var _can_continue := false
var _settings_open := false
var _scenario := "sandbox"
var _seed := 7
var _duration := "5y"
var _duration_input_mode := "end_date"
var _custom_duration_ticks := 1_827
var _start_date := {"year": 2000, "month": 1, "day": 1}
var _trade := true
var _capital := true
var _migration := true
var _cross_open := false
var _cross_values := {"fx_lambda": 0.05, "fx_friction": 0.03,
	"fx_trade_cap": 0.15, "capital_mobility": 1.0,
	"capital_adjust": 0.2, "migration_rate": 0.02,
	"migration_max_share": 0.25, "remittance_share": 0.2,
	"wage_smoothing": 0.02, "peg_reserves0": 5000.0}
var _countries: Array = []
var _selected_country := 0
var _player_country := 0
var _profile_mapping_enabled := true
var _population_mapping_enabled := true
var _run_mode := "realtime"
var _seat_occupants: Dictionary = {}
var _calendar_open := false
var _policy_country := 0
var _policy_seat := "treasury"
var _policy_filter := "all"
var _policy_search := ""
var _policy_values: Dictionary = {}
var _policy_schemas: Dictionary = {}
var _settings_values: Dictionary = {}
var _launch_progress := 0
var _launch_error := ""
var _launch_timer: Timer


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	_sans = SystemFont.new()
	_sans.font_names = PackedStringArray(["Hiragino Sans GB", "PingFang SC", "STHeiti", "Helvetica Neue"])
	_mono = SystemFont.new()
	_mono.font_names = PackedStringArray(["IBM Plex Mono", "Menlo", "Monaco"])
	_mono.fallbacks = [_sans]
	_reset_defaults()
	var capture_step := OS.get_environment("MACRO_SIM_CAPTURE_START_STEP")
	if capture_step.is_valid_int() and capture_step.to_int() >= 1:
		_screen = "wizard"
		_step = clampi(capture_step.to_int(), 1, STEP_META.size())
	var capture_duration := OS.get_environment("MACRO_SIM_CAPTURE_START_DURATION")
	if capture_duration in ["1y", "5y", "10y", "custom", "inf"]:
		_duration = capture_duration
	_settings_open = OS.get_environment("MACRO_SIM_CAPTURE_START_SETTINGS") == "1"
	_surface = Control.new()
	_surface.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_surface)
	_launch_timer = Timer.new()
	_launch_timer.wait_time = 0.48
	_launch_timer.timeout.connect(_advance_launch)
	add_child(_launch_timer)
	_render()


func _reset_defaults() -> void:
	_profile_mapping_enabled = true
	_population_mapping_enabled = true
	_countries = [
		_country_record(0, "advanced"),
		_country_record(1, "developing"),
		_country_record(2, "petrostate"),
	]
	for country: Dictionary in _countries:
		_select_profile(country, str(country["profile"]))
	for seat: Dictionary in SEATS:
		_seat_occupants[str(seat["id"])] = "null"


func set_policy_schemas(value: Dictionary) -> void:
	## The engine Registry is authoritative.  POLICY_PREVIEW is only the
	## disconnected-start fallback while the desktop process is connecting.
	_policy_schemas = value.duplicate(true)
	if is_inside_tree() and visible:
		_render()


func open_home(can_continue := true) -> void:
	_launch_timer.stop()
	_can_continue = can_continue
	_screen = "home"
	_settings_open = false
	_launch_error = ""
	show()
	move_to_front()
	_render()


func _country_record(index: int, profile: String = "symmetric") -> Dictionary:
	return {"name": _text(COUNTRY_NAMES[index]), "code": COUNTRY_CODES[index],
		"color": COUNTRY_COLORS[index], "profile": profile, "overrides": {},
		"baseline_overrides": {}, "firm_population_ratios": {}}


func _render() -> void:
	for child in _surface.get_children():
		_surface.remove_child(child)
		child.queue_free()
	_surface.add_child(_backdrop())
	if _screen == "home":
		_build_home(_surface)
	elif _screen == "launching":
		_build_launch(_surface)
	else:
		_build_wizard(_surface)
	if _settings_open:
		_build_settings(_surface)


func _backdrop() -> Control:
	var bg := ColorRect.new()
	bg.color = BG
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	return bg


func _build_home(parent: Control) -> void:
	var grid := _DotGrid.new()
	grid.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	grid.modulate.a = 0.52
	grid.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(grid)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right"]:
		margin.add_theme_constant_override("margin_" + side, 64)
	for side in ["top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 56)
	parent.add_child(margin)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 56)
	margin.add_child(row)
	var brand := VBoxContainer.new()
	brand.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	brand.custom_minimum_size = Vector2(500, 0)
	row.add_child(brand)
	var brand_top := VBoxContainer.new()
	brand_top.add_theme_constant_override("separation", 0)
	var lockup := HBoxContainer.new()
	lockup.add_theme_constant_override("separation", 10)
	var mark := PanelContainer.new()
	mark.custom_minimum_size = Vector2(34, 34)
	mark.add_theme_stylebox_override("panel", _sb(TEAL, TEAL, 9, 0))
	var mark_center := CenterContainer.new()
	mark.add_child(mark_center)
	mark_center.add_child(_label("□", 22, Color.WHITE, true))
	lockup.add_child(mark)
	lockup.add_child(_label("MACRO COMMAND", 12, Color("68788b"), true, true))
	brand_top.add_child(lockup)
	var title := _label("@app.title", 62, INK, true)
	title.add_theme_constant_override("line_spacing", -4)
	var title_margin := MarginContainer.new()
	title_margin.add_theme_constant_override("margin_top", 36)
	title_margin.add_child(title)
	brand_top.add_child(title_margin)
	var accent := ColorRect.new()
	accent.color = TEAL
	accent.custom_minimum_size = Vector2(56, 3)
	accent.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	var accent_margin := MarginContainer.new()
	accent_margin.add_theme_constant_override("margin_top", 25)
	accent_margin.add_theme_constant_override("margin_bottom", 19)
	accent_margin.add_child(accent)
	brand_top.add_child(accent_margin)
	var intro := _label("@app.intro", 15, INK2)
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	intro.custom_minimum_size = Vector2(420, 0)
	brand_top.add_child(intro)
	brand.add_child(brand_top)
	brand.add_child(_v_spacer())
	var build := _label("@app.build", 11, INK3, false, true)
	build.add_theme_constant_override("line_spacing", 7)
	brand.add_child(build)
	var menu_wrap := VBoxContainer.new()
	menu_wrap.custom_minimum_size = Vector2(480, 0)
	row.add_child(menu_wrap)
	menu_wrap.add_child(_v_spacer())
	var menu := VBoxContainer.new()
	menu.add_theme_constant_override("separation", 14)
	menu_wrap.add_child(menu)
	var choices := VBoxContainer.new()
	choices.add_theme_constant_override("separation", 9)
	if _can_continue:
		choices.add_child(_home_choice(
			"▶", "@menu.continue", "@menu.continue_hint", func() -> void:
			continue_requested.emit()
			hide(), true))
	choices.add_child(_home_choice(
		"＋", "@menu.new", "@menu.new_hint", func() -> void:
		_screen = "wizard"; _step = 1; _render(), not _can_continue))
	choices.add_child(_home_choice(
		"⚙", "@menu.settings", "@menu.settings_hint", func() -> void:
		_settings_open = true; _render()))
	choices.add_child(_home_choice(
		"⏻", "@menu.quit", "@menu.quit_hint", func() -> void:
		get_tree().quit()))
	menu.add_child(choices)
	menu_wrap.add_child(_v_spacer())


func _home_choice(icon: String, title: String, subtitle: String,
		on_pick: Callable, primary := false) -> Control:
	var button := Button.new()
	button.custom_minimum_size = Vector2(0, 62)
	button.add_theme_stylebox_override("normal", _sb(PAPER, LINE, 11, 9))
	button.add_theme_stylebox_override("hover", _sb(PAPER, TEAL, 11, 8))
	button.pressed.connect(on_pick)
	var row := HBoxContainer.new()
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_theme_constant_override("separation", 14)
	_fill_inset(row, 12)
	button.add_child(row)
	var iconp := PanelContainer.new()
	iconp.custom_minimum_size = Vector2(32, 32)
	iconp.add_theme_stylebox_override("panel", _sb(TEAL_BG if primary else PANEL2,
		TEAL_BG if primary else PANEL2, 8, 0))
	var ic := CenterContainer.new(); iconp.add_child(ic)
	ic.add_child(_label(icon, 16, TEAL if primary else INK2))
	row.add_child(iconp)
	var text := VBoxContainer.new(); text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	text.add_child(_label(title, 15, INK, true))
	text.add_child(_label(subtitle, 11, INK3))
	row.add_child(text)
	row.add_child(_label("›", 18, Color("b0bcc8")))
	return button


func _build_wizard(parent: Control) -> void:
	var shell := VBoxContainer.new()
	shell.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	parent.add_child(shell)
	shell.add_child(_wizard_header())
	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 0)
	shell.add_child(body)
	body.add_child(_step_navigation())
	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	# Keep the edit region shrinkable so the fixed 322 px summary remains visible
	# on the dense country page; content is clipped rather than widening the shell.
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_NEVER
	var edit_margin := MarginContainer.new()
	edit_margin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	edit_margin.add_theme_constant_override("margin_left", 26)
	edit_margin.add_theme_constant_override("margin_right", 26)
	edit_margin.add_theme_constant_override("margin_top", 22)
	edit_margin.add_theme_constant_override("margin_bottom", 22)
	var content := VBoxContainer.new()
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	edit_margin.add_child(content)
	scroll.add_child(edit_margin)
	body.add_child(scroll)
	match _step:
		1: _step_scenario(content)
		2: _step_world(content)
		3: _step_countries(content)
		4: _step_policy(content)
		_: _step_review(content)
	if _step != STEP_META.size():
		body.add_child(_summary_panel())
	shell.add_child(_wizard_footer())


func _wizard_header() -> Control:
	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(0, 56)
	panel.add_theme_stylebox_override("panel", _sb(PAPER, LINE2, 0, 10))
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 14)
	panel.add_child(row)
	row.add_child(_button("@wizard.home", func() -> void:
		_screen = "home"; _render(), false, 13, true))
	row.add_child(_v_rule(26))
	row.add_child(_label("@wizard.title", 15, INK, true))
	row.add_child(_label("NEW SIMULATION", 11, INK3, false, true))
	row.add_child(_h_spacer())
	row.add_child(_button("⚙", func() -> void:
		_settings_open = true; _render(), false, 15))
	return panel


func _step_navigation() -> Control:
	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(224, 0)
	panel.add_theme_stylebox_override("panel", _sb(PANEL, LINE2, 0, 14))
	var col := VBoxContainer.new(); col.add_theme_constant_override("separation", 5); panel.add_child(col)
	var km := MarginContainer.new(); km.add_theme_constant_override("margin_left", 8); km.add_theme_constant_override("margin_bottom", 6)
	km.add_child(_label("@wizard.flow", 10, INK3, false, true)); col.add_child(km)
	for index in STEP_META.size():
		var number := index + 1
		var active := number == _step
		var done := number < _step
		var button := Button.new(); button.custom_minimum_size = Vector2(0, 51)
		button.add_theme_stylebox_override("normal", _sb(TEAL_BG if active else Color(0, 0, 0, 0), TEAL_BD if active else Color(0, 0, 0, 0), 10, 7))
		button.add_theme_stylebox_override("hover", _sb(PAPER, LINE, 10, 7))
		button.pressed.connect(func() -> void: _step = number; _render())
		var row := HBoxContainer.new(); row.mouse_filter = Control.MOUSE_FILTER_IGNORE; row.add_theme_constant_override("separation", 11); button.add_child(row)
		_fill_inset(row, 8)
		var badge := PanelContainer.new(); badge.custom_minimum_size = Vector2(26, 26)
		badge.add_theme_stylebox_override("panel", _sb(TEAL if active else (TEAL_BD if done else Color("e6ebf1")), TEAL if active else (TEAL_BD if done else Color("e6ebf1")), 8, 0))
		var bc := CenterContainer.new(); badge.add_child(bc); bc.add_child(_label("✓" if done else str(number), 12, Color.WHITE if active or done else INK3, true, true)); row.add_child(badge)
		var names := VBoxContainer.new(); names.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		names.add_child(_label(str(STEP_META[index][0]), 13, INK if active else INK2, active))
		names.add_child(_label(str(STEP_META[index][1]), 9, MUTED, false, true)); row.add_child(names)
		col.add_child(button)
	col.add_child(_v_spacer())
	var note := _panel(Color("eef2f7"), LINE2, 10, 10)
	var nt := _label("@wizard.truths", 11, INK2)
	nt.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; note.add_child(nt); col.add_child(note)
	return panel


func _page_heading(parent: VBoxContainer, title: String, subtitle: String) -> void:
	parent.add_child(_label(title, 20, INK, true))
	var sub := _label(subtitle, 13, Color("68788b")); sub.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var sm := MarginContainer.new(); sm.add_theme_constant_override("margin_top", 3); sm.add_theme_constant_override("margin_bottom", 17); sm.add_child(sub); parent.add_child(sm)


func _step_scenario(parent: VBoxContainer) -> void:
	parent.custom_minimum_size.x = 720
	_page_heading(parent, "@wizard.scenario.title", "@wizard.scenario.desc")
	parent.add_child(_kicker("@wizard.scenario.kicker"))
	var list := VBoxContainer.new(); list.add_theme_constant_override("separation", 8); parent.add_child(list)
	for raw: Dictionary in SCENARIOS:
		var item := raw
		var active := str(item["id"]) == _scenario
		var b := Button.new(); b.custom_minimum_size = Vector2(0, 66)
		b.add_theme_stylebox_override("normal", _sb(TEAL_BG if active else PAPER, TEAL_BD if active else LINE, 11, 11))
		b.add_theme_stylebox_override("hover", _sb(TEAL_BG if active else PAPER, TEAL, 11, 10))
		b.pressed.connect(func() -> void: _scenario = str(item["id"]); _render())
		var row := HBoxContainer.new(); row.mouse_filter = Control.MOUSE_FILTER_IGNORE; row.add_theme_constant_override("separation", 14); b.add_child(row)
		_fill_inset(row, 12)
		row.add_child(_label("◉" if active else "○", 20, TEAL if active else INK3))
		var words := VBoxContainer.new(); words.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var title_row := HBoxContainer.new(); title_row.add_theme_constant_override("separation", 8); title_row.add_child(_label(str(item["name"]), 14, INK, true))
		if bool(item["reduced"]): title_row.add_child(_chip(_text("@wizard.scenario.reduced"), AMBER, AMBER_BG, AMBER_BD))
		words.add_child(title_row); words.add_child(_label(str(item["desc"]), 11, Color("68788b"))); row.add_child(words)
		var meta := VBoxContainer.new(); meta.add_child(_label(str(item["caps"]), 11, INK2, false, true)); meta.add_child(_label(str(item["duration"]), 10, MUTED, false, true)); row.add_child(meta)
		list.add_child(b)


func _step_world(parent: VBoxContainer) -> void:
	parent.custom_minimum_size.x = 760
	_page_heading(parent, "@wizard.world.title", "@wizard.world.desc")
	var top := GridContainer.new(); top.columns = 2; top.add_theme_constant_override("h_separation", 12); top.add_theme_constant_override("v_separation", 12); parent.add_child(top)
	top.add_child(_counter_card("@wizard.world.country_count", "@wizard.world.country_count_hint", str(_countries.size()), _remove_country, _add_country))
	top.add_child(_seed_card())
	var duration_m := MarginContainer.new(); duration_m.add_theme_constant_override("margin_top", 12); duration_m.add_child(_duration_card()); parent.add_child(duration_m)
	var cross_m := MarginContainer.new(); cross_m.add_theme_constant_override("margin_top", 18); cross_m.add_theme_constant_override("margin_bottom", 8); cross_m.add_child(_kicker("@wizard.cross_border.kicker")); parent.add_child(cross_m)
	var toggles := GridContainer.new(); toggles.columns = 2; toggles.add_theme_constant_override("h_separation", 9); toggles.add_theme_constant_override("v_separation", 9); parent.add_child(toggles)
	toggles.add_child(_toggle_card("@wizard.cross_border.trade", "@wizard.cross_border.trade_desc", _trade, func() -> void: _trade = not _trade; _render()))
	toggles.add_child(_toggle_card("@wizard.cross_border.capital", "@wizard.cross_border.capital_desc", _capital, func() -> void: _capital = not _capital; _render()))
	toggles.add_child(_toggle_card("@wizard.cross_border.migration", "@wizard.cross_border.migration_desc", _migration, func() -> void: _migration = not _migration; _render()))
	toggles.add_child(_toggle_card("@wizard.cross_border.remittances", "@wizard.cross_border.remittances_desc", _migration, func() -> void: _migration = not _migration; _render()))
	var adv := _button(("▼" if _cross_open else "▶") + _text("@wizard.cross_border.advanced"), func() -> void: _cross_open = not _cross_open; _render(), false, 12, true)
	var am := MarginContainer.new(); am.add_theme_constant_override("margin_top", 12); am.add_child(adv); parent.add_child(am)
	if _cross_open:
		var ap := _panel(PANEL, LINE2, 11, 8); parent.add_child(ap)
		var grid := GridContainer.new(); grid.columns = 2; grid.add_theme_constant_override("h_separation", 6); grid.add_theme_constant_override("v_separation", 6); ap.add_child(grid)
		for field: Array in [["@wizard.field.fx_lambda", "fx_lambda", "0.05"], ["@wizard.field.fx_friction", "fx_friction", "0.03"], ["@wizard.field.fx_trade_cap", "fx_trade_cap", "0.15"], ["@wizard.field.capital_mobility", "capital_mobility", "1.00"], ["@wizard.field.capital_adjust", "capital_adjust", "0.20"], ["@wizard.field.migration_rate", "migration_rate", "0.02"], ["@wizard.field.migration_max_share", "migration_max_share", "0.25"], ["@wizard.field.remittance_share", "remittance_share", "0.20"], ["@wizard.field.wage_smoothing", "wage_smoothing", "0.02"], ["@wizard.field.peg_reserves0", "peg_reserves0", "5,000"]]:
			grid.add_child(_mini_field(str(field[0]), str(field[1]), str(field[2])))


func _counter_card(title: String, note: String, value: String, dec: Callable, inc: Callable) -> Control:
	var p := _panel(PAPER, LINE, 12, 14); p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := VBoxContainer.new(); v.add_theme_constant_override("separation", 4); p.add_child(v)
	v.add_child(_label(title, 12, INK2)); v.add_child(_label(note, 10, MUTED, false, true))
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 10)
	row.add_child(_square_button("−", dec, 38)); var val := _label(value, 26, INK, true, true); val.size_flags_horizontal = Control.SIZE_EXPAND_FILL; val.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; row.add_child(val); row.add_child(_square_button("＋", inc, 38)); v.add_child(row)
	return p


func _seed_card() -> Control:
	var p := _panel(PAPER, LINE, 12, 14); p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := VBoxContainer.new(); v.add_theme_constant_override("separation", 4); p.add_child(v)
	v.add_child(_label("@wizard.seed", 12, INK2)); v.add_child(_label("@wizard.seed_hint", 10, MUTED, false, true))
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 8)
	var edit := LineEdit.new(); edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL; edit.text = str(_seed); edit.add_theme_font_override("font", _mono); edit.add_theme_font_size_override("font_size", 15); edit.add_theme_color_override("font_color", INK); edit.add_theme_color_override("caret_color", TEAL); edit.add_theme_stylebox_override("normal", _sb(PANEL, LINE, 9, 8)); edit.text_submitted.connect(func(text: String) -> void: _apply_seed(text)); edit.focus_exited.connect(func() -> void: _apply_seed(edit.text)); row.add_child(edit)
	row.add_child(_square_button("🎲", func() -> void: _seed = randi_range(0, 2147483647); _render(), 38)); row.add_child(_square_button("⧉", func() -> void: DisplayServer.clipboard_set(str(_seed)), 38)); v.add_child(row)
	return p


func _apply_seed(text: String) -> void:
	if text.is_valid_int(): _seed = clampi(text.to_int(), 0, 2147483647)
	_render()


func _duration_card() -> Control:
	var p := _panel(PAPER, LINE, 12, 14); p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := VBoxContainer.new(); v.add_theme_constant_override("separation", 9); p.add_child(v)
	var title := HBoxContainer.new(); title.add_child(_label("@wizard.calendar", 12, INK2)); title.add_child(_h_spacer()); title.add_child(_chip(_text("@wizard.one_tick_day"), TEAL_DK, TEAL_BG, TEAL_BD)); v.add_child(title)
	v.add_child(_label("@wizard.start_date", 10, INK3))
	v.add_child(_date_fields(_start_date, _apply_start_date_component))
	var duration_head := HBoxContainer.new(); duration_head.add_child(_label("@wizard.run_duration", 10, INK3)); duration_head.add_child(_h_spacer()); duration_head.add_child(_label("@wizard.gregorian", 9, MUTED, false, true)); v.add_child(duration_head)
	var flow := HFlowContainer.new(); flow.add_theme_constant_override("h_separation", 6); flow.add_theme_constant_override("v_separation", 6)
	for d: Array in [["1y", "@wizard.duration.1y"], ["5y", "@wizard.duration.5y"], ["10y", "@wizard.duration.10y"], ["custom", "@wizard.duration.custom"], ["inf", "@wizard.duration.infinite"]]:
		var id := str(d[0]); flow.add_child(_select_chip(str(d[1]), _duration == id, func() -> void: _select_duration(id)))
	v.add_child(flow)
	if _duration == "custom":
		var modes := HBoxContainer.new(); modes.add_theme_constant_override("separation", 6)
		for mode: Array in [["end_date", "@wizard.duration.end_date"], ["ticks", "@wizard.duration.ticks"]]:
			var mode_id := str(mode[0]); var mode_chip := _select_chip(str(mode[1]), _duration_input_mode == mode_id, func() -> void: _duration_input_mode = mode_id; _render()); mode_chip.size_flags_horizontal = Control.SIZE_EXPAND_FILL; modes.add_child(mode_chip)
		v.add_child(modes)
		if _duration_input_mode == "end_date":
			v.add_child(_date_fields(_end_date(), _apply_end_date_component))
		else:
			v.add_child(_duration_tick_field())
	var note := _label(_duration_note(), 10, INK3, false, true); note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; v.add_child(note)
	return p


func _date_fields(parts: Dictionary, callback: Callable) -> Control:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	for field: Array in [["@wizard.date.year", "year", 74], ["@wizard.date.month", "month", 54], ["@wizard.date.day", "day", 54]]:
		var box := VBoxContainer.new(); box.size_flags_horizontal = Control.SIZE_EXPAND_FILL; box.add_theme_constant_override("separation", 3)
		var edit := LineEdit.new(); edit.text = str(parts[str(field[1])]); edit.custom_minimum_size = Vector2(int(field[2]), 34); edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL; edit.alignment = HORIZONTAL_ALIGNMENT_CENTER; edit.add_theme_font_override("font", _mono); edit.add_theme_font_size_override("font_size", 13); edit.add_theme_color_override("font_color", INK); edit.add_theme_color_override("caret_color", TEAL); edit.add_theme_stylebox_override("normal", _sb(PANEL, LINE2, 8, 7))
		var key := str(field[1])
		edit.text_submitted.connect(func(text: String) -> void: callback.call(key, text))
		edit.focus_exited.connect(func() -> void: callback.call(key, edit.text))
		box.add_child(edit); var caption := _label(str(field[0]), 9, MUTED); caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; box.add_child(caption); row.add_child(box)
	return row


func _duration_tick_field() -> Control:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 8)
	var edit := LineEdit.new(); edit.text = str(_custom_duration_ticks); edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL; edit.custom_minimum_size.y = 36; edit.add_theme_font_override("font", _mono); edit.add_theme_font_size_override("font_size", 14); edit.add_theme_color_override("font_color", INK); edit.add_theme_color_override("caret_color", TEAL); edit.add_theme_stylebox_override("normal", _sb(PANEL, LINE2, 8, 7)); edit.text_submitted.connect(_apply_duration_ticks); edit.focus_exited.connect(func() -> void: _apply_duration_ticks(edit.text)); row.add_child(edit)
	row.add_child(_label("@wizard.tick_day", 11, INK2, false, true))
	return row


func _select_duration(value: String) -> void:
	if value == "custom" and _duration != "custom":
		var current: Variant = _duration_ticks_value()
		if current != null:
			_custom_duration_ticks = int(current)
	_duration = value
	_render()


func _apply_start_date_component(key: String, text: String) -> void:
	if text.is_valid_int():
		var proposed := _start_date.duplicate()
		proposed[key] = text.to_int()
		_start_date = _normalize_date(proposed, MIN_START_YEAR, MAX_START_YEAR)
		_custom_duration_ticks = mini(_custom_duration_ticks, _maximum_duration_from_start())
	_render()


func _apply_end_date_component(key: String, text: String) -> void:
	if text.is_valid_int():
		var proposed := _end_date()
		proposed[key] = text.to_int()
		proposed = _normalize_date(proposed, int(_start_date["year"]), 9999)
		_custom_duration_ticks = clampi(_date_day(proposed) - _date_day(_start_date), 1, _maximum_duration_from_start())
	_render()


func _apply_duration_ticks(text: String) -> void:
	if text.is_valid_int():
		_custom_duration_ticks = clampi(text.to_int(), 1, _maximum_duration_from_start())
	_render()


func _normalize_date(parts: Dictionary, min_year: int, max_year: int) -> Dictionary:
	var year := clampi(int(parts.get("year", min_year)), min_year, max_year)
	var month := clampi(int(parts.get("month", 1)), 1, 12)
	var day := clampi(int(parts.get("day", 1)), 1, _days_in_month(year, month))
	return {"year": year, "month": month, "day": day}


func _days_in_month(year: int, month: int) -> int:
	if month == 2:
		return 29 if year % 400 == 0 or (year % 4 == 0 and year % 100 != 0) else 28
	if month in [4, 6, 9, 11]:
		return 30
	return 31


func _date_day(parts: Dictionary) -> int:
	var datetime := {"year": int(parts["year"]), "month": int(parts["month"]), "day": int(parts["day"]), "hour": 0, "minute": 0, "second": 0}
	return floori(float(Time.get_unix_time_from_datetime_dict(datetime)) / float(SECONDS_PER_DAY))


func _date_from_day(day_number: int) -> Dictionary:
	var parts := Time.get_date_dict_from_unix_time(day_number * SECONDS_PER_DAY)
	return {"year": int(parts["year"]), "month": int(parts["month"]), "day": int(parts["day"])}


func _date_iso(parts: Dictionary) -> String:
	return "%04d-%02d-%02d" % [int(parts["year"]), int(parts["month"]), int(parts["day"])]


func _add_years(parts: Dictionary, years: int) -> Dictionary:
	var result := parts.duplicate()
	result["year"] = int(parts["year"]) + years
	result["day"] = mini(int(parts["day"]), _days_in_month(int(result["year"]), int(result["month"])))
	return result


func _maximum_duration_from_start() -> int:
	return _date_day({"year": 9999, "month": 12, "day": 31}) - _date_day(_start_date)


func _duration_ticks_value() -> Variant:
	if _duration == "inf":
		return null
	if _duration == "custom":
		return _custom_duration_ticks
	var years: int = int({"1y": 1, "5y": 5, "10y": 10}.get(_duration, 5))
	return _date_day(_add_years(_start_date, int(years))) - _date_day(_start_date)


func _end_date() -> Dictionary:
	var ticks: Variant = _duration_ticks_value()
	if ticks == null:
		return {}
	return _date_from_day(_date_day(_start_date) + int(ticks))


func _duration_note() -> String:
	if _duration == "inf":
		return _format("wizard.duration.open", _date_iso(_start_date))
	return _format("wizard.duration.range", [_date_iso(_start_date), _date_iso(_end_date()), int(_duration_ticks_value())])


func _toggle_card(title: String, note: String, on: bool, callback: Callable) -> Control:
	var b := Button.new(); b.custom_minimum_size = Vector2(0, 56); b.size_flags_horizontal = Control.SIZE_EXPAND_FILL; b.add_theme_stylebox_override("normal", _sb(PAPER, TEAL_BD if on else LINE, 10, 9)); b.add_theme_stylebox_override("hover", _sb(PAPER, TEAL, 10, 8)); b.pressed.connect(callback)
	var row := HBoxContainer.new(); row.mouse_filter = Control.MOUSE_FILTER_IGNORE; row.add_theme_constant_override("separation", 11); b.add_child(row); row.add_child(_switch_visual(on))
	_fill_inset(row, 11)
	var text := VBoxContainer.new(); text.size_flags_horizontal = Control.SIZE_EXPAND_FILL; text.add_child(_label(title, 13, INK)); text.add_child(_label(note, 10, INK3)); row.add_child(text); return b


func _mini_field(title: String, internal: String, value: String) -> Control:
	var current := float(_cross_values.get(internal, value.to_float()))
	var display := "%d" % roundi(current) if internal == "peg_reserves0" else "%.2f" % current
	var step := 500.0 if internal == "peg_reserves0" else 0.01
	var p := _panel(PAPER, LINE2, 8, 7); p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 8); p.add_child(row)
	var words := VBoxContainer.new(); words.size_flags_horizontal = Control.SIZE_EXPAND_FILL; words.add_child(_label(title, 12, Color("3a4956"))); words.add_child(_label(internal, 9, MUTED, false, true)); row.add_child(words)
	row.add_child(_square_button("−", func() -> void:
		_cross_values[internal] = maxf(0.0, current - step)
		_render(), 26))
	row.add_child(_label(display, 12, INK, false, true))
	row.add_child(_square_button("＋", func() -> void:
		_cross_values[internal] = current + step
		_render(), 26))
	return p


func _step_countries(parent: VBoxContainer) -> void:
	var row := HBoxContainer.new(); row.size_flags_vertical = Control.SIZE_EXPAND_FILL; row.add_theme_constant_override("separation", 16); parent.add_child(row)
	var left := VBoxContainer.new(); left.custom_minimum_size = Vector2(250, 0); left.add_theme_constant_override("separation", 8); row.add_child(left)
	var lh := HBoxContainer.new(); lh.add_child(_kicker(_format("wizard.countries.kicker", _countries.size()))); lh.add_child(_h_spacer()); lh.add_child(_button("@wizard.countries.add", _add_country, false, 11)); left.add_child(lh)
	for i in _countries.size(): left.add_child(_country_card(i))
	var note := _label("@wizard.countries.stable_ids", 10, MUTED); note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; left.add_child(note)
	var editor := VBoxContainer.new(); editor.size_flags_horizontal = Control.SIZE_EXPAND_FILL; editor.add_theme_constant_override("separation", 10); row.add_child(editor)
	var c: Dictionary = _countries[_selected_country]
	var identity := HBoxContainer.new(); identity.add_theme_constant_override("separation", 12)
	var flag := PanelContainer.new(); flag.custom_minimum_size = Vector2(44, 44); flag.add_theme_stylebox_override("panel", _sb(c["color"], c["color"], 11, 0)); var fc := CenterContainer.new(); flag.add_child(fc); fc.add_child(_label(str(c["code"]), 11, Color.WHITE, true, true)); identity.add_child(flag)
	var idwords := VBoxContainer.new(); idwords.size_flags_horizontal = Control.SIZE_EXPAND_FILL; idwords.add_child(_label(str(c["name"]), 19, INK, true)); idwords.add_child(_label(_format("wizard.countries.core_economy", str(c["code"])), 11, INK3, false, true)); identity.add_child(idwords)
	identity.add_child(_button("@wizard.countries.apply_all", func() -> void: _apply_profile_all(), false, 11))
	identity.add_child(_button("@wizard.countries.restore_profile", func() -> void:
		_select_profile(c, str(c["profile"]))
		_render(), false, 11))
	if _countries.size() > 1:
		identity.add_child(_button("@wizard.countries.delete", _delete_selected_country, false, 11))
	editor.add_child(identity)
	editor.add_child(_kicker("@wizard.countries.profile_kicker"))
	var profiles := GridContainer.new(); profiles.columns = 3; profiles.add_theme_constant_override("h_separation", 8); profiles.add_theme_constant_override("v_separation", 8); editor.add_child(profiles)
	for pid in PROFILES.keys(): profiles.add_child(_profile_card(str(pid)))
	editor.add_child(_profile_mapping_controls())
	var stats := _panel(PANEL, LINE2, 9, 9); var statrow := HBoxContainer.new(); statrow.add_theme_constant_override("separation", 16); stats.add_child(statrow); statrow.add_child(_label(_format("wizard.countries.initial_population", _agent_population(c)), 11, INK2)); statrow.add_child(_label("@wizard.countries.households", 11, INK2)); statrow.add_child(_label(_format("wizard.countries.production_firms", _firm_count(c)), 11, INK2)); editor.add_child(stats)
	editor.add_child(_kicker("@wizard.countries.structure"))
	for group: Dictionary in STRUCT_GROUPS:
		var gh := HBoxContainer.new(); gh.add_child(_label(str(group["name"]), 12, Color("3a4956"), true)); gh.add_child(_h_rule()); editor.add_child(gh)
		var fields := GridContainer.new(); fields.columns = 2; fields.add_theme_constant_override("h_separation", 7); fields.add_theme_constant_override("v_separation", 7); editor.add_child(fields)
		for field: Array in group["fields"]: fields.add_child(_structure_field(c, field))


func _country_card(index: int) -> Control:
	var c: Dictionary = _countries[index]; var active := index == _selected_country
	var b := Button.new(); b.custom_minimum_size = Vector2(0, 70); b.size_flags_horizontal = Control.SIZE_EXPAND_FILL; b.add_theme_stylebox_override("normal", _sb(TEAL_BG if active else PAPER, TEAL_BD if active else LINE, 9, 9)); b.add_theme_stylebox_override("hover", _sb(PAPER, TEAL, 9, 8)); b.pressed.connect(func() -> void: _selected_country = index; _render())
	var col := VBoxContainer.new(); col.mouse_filter = Control.MOUSE_FILTER_IGNORE; col.add_theme_constant_override("separation", 5); b.add_child(col)
	_fill_inset(col, 10)
	var head := HBoxContainer.new(); head.add_theme_constant_override("separation", 7); head.add_child(_dot(c["color"], 8)); head.add_child(_label(str(c["name"]), 13, INK, true)); head.add_child(_h_spacer())
	if index == _player_country:
		head.add_child(_label("@wizard.countries.player", 9, TEAL))
	col.add_child(head)
	var meta := HBoxContainer.new(); meta.add_child(_label(_text(str(PROFILES[str(c["profile"])]["name"])), 10, INK2, false, true)); meta.add_child(_h_spacer()); meta.add_child(_label(_format("wizard.countries.population", _agent_population(c)), 9, MUTED, false, true)); col.add_child(meta)
	return b


func _profile_card(pid: String) -> Control:
	var c: Dictionary = _countries[_selected_country]; var p: Dictionary = PROFILES[pid]; var active := str(c["profile"]) == pid
	var b := Button.new(); b.custom_minimum_size = Vector2(176, 74); b.size_flags_horizontal = Control.SIZE_EXPAND_FILL; b.add_theme_stylebox_override("normal", _sb(TEAL_BG if active else PAPER, TEAL_BD if active else LINE, 10, 9)); b.pressed.connect(func() -> void:
		_select_profile(c, pid)
		_render())
	var v := VBoxContainer.new(); v.mouse_filter = Control.MOUSE_FILTER_IGNORE; v.add_child(_label(str(p["name"]), 13, INK, true)); var d := _label(str(p["desc"]), 10, Color("68788b")); d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; d.max_lines_visible = 2; d.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS; v.add_child(d); _fill_inset(v, 10); b.add_child(v); return b


func _profile_mapping_controls() -> Control:
	var panel := _panel(PANEL, LINE2, 9, 8)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 16)
	panel.add_child(row)
	row.add_child(_mapping_switch(
		"@wizard.mapping.profile",
		"@wizard.mapping.profile_desc",
		_profile_mapping_enabled,
		func() -> void:
			_profile_mapping_enabled = not _profile_mapping_enabled
			_render()))
	row.add_child(_v_rule(34))
	row.add_child(_mapping_switch(
		"@wizard.mapping.population",
		"@wizard.mapping.population_desc",
		_population_mapping_enabled,
		func() -> void: _toggle_population_mapping()))
	return panel


func _mapping_switch(title: String, desc: String, enabled: bool,
		callback: Callable) -> Control:
	var row := HBoxContainer.new()
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_theme_constant_override("separation", 9)
	var text := VBoxContainer.new()
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	text.add_child(_label(title, 11, INK, true))
	text.add_child(_label(desc, 9, MUTED))
	row.add_child(text)
	row.add_child(_switch_button(enabled, callback))
	return row


func _structure_field(country: Dictionary, field: Array) -> Control:
	var key := str(field[1]); var kind := str(field[2]); var overrides: Dictionary = country["overrides"]; var changed := overrides.has(key)
	var p := _panel(BLUE_BG if changed else PAPER, BLUE_BD if changed else LINE2, 9, 8); p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 9); p.add_child(row)
	var text := VBoxContainer.new(); text.size_flags_horizontal = Control.SIZE_EXPAND_FILL; text.add_child(_label(str(field[0]), 12, INK)); text.add_child(_label(key, 9, MUTED, false, true)); row.add_child(text)
	if kind == "toggle":
		var value := bool(overrides.get(key, true)); row.add_child(_switch_button(value, func() -> void:
			_set_structure_toggle(country, key, not value)
			_render()))
	elif kind == "select":
		var option := OptionButton.new()
		for choice: Array in [["exogenous", "@wizard.choice.tfp_exogenous"], ["learning", "@wizard.choice.tfp_learning"]]:
			option.add_item(_text(str(choice[1])))
			option.set_item_metadata(option.item_count - 1, choice[0])
			if str(overrides.get(key, "exogenous")) == str(choice[0]):
				option.select(option.item_count - 1)
		option.item_selected.connect(func(index: int) -> void:
			_set_structure_value(country, key, str(option.get_item_metadata(index)))
			_render())
		option.add_theme_font_size_override("font_size", 11)
		row.add_child(option)
	else:
		var value := float(overrides.get(key, _structure_default(
			key, str(country["profile"]))))
		var step := 1.0 if _is_structure_integer(key) else 0.05
		row.add_child(_mini_stepper(_format_small(value),
			func() -> void:
				_set_structure_number(country, key, value - step),
			func() -> void:
				_set_structure_number(country, key, value + step),
			func(text: String) -> void:
				_apply_structure_number(country, key, text)))
	return p


func _is_structure_integer(key: String) -> bool:
	return key.begins_with("n_") or key == "demographics_population"


func _normalize_structure_number(key: String, value: float) -> Variant:
	var minimum := 2.0 if key == "n_firms_c" \
		else (1.0 if _is_structure_integer(key) \
		else (0.05 if key in ["a", "alpha", "necessity_share0"] else 0.0))
	var maximum := 100_000.0 if _is_structure_integer(key) \
		else (0.95 if key in ["alpha", "necessity_share0"] else INF)
	var normalized := clampf(value, minimum, maximum)
	return roundi(normalized) if _is_structure_integer(key) else normalized


func _set_structure_value(country: Dictionary, key: String, value: Variant,
		record_baseline := true) -> void:
	var overrides: Dictionary = country["overrides"]
	overrides[key] = value
	if record_baseline and str(country["profile"]) == "symmetric":
		var baseline: Dictionary = country["baseline_overrides"]
		baseline[key] = value


func _set_structure_number(country: Dictionary, key: String, value: float) -> void:
	var previous_population := maxi(1, _agent_population(country))
	if key == "demographics_population" and _population_mapping_enabled:
		_ensure_population_ratios(country)
	var normalized: Variant = _normalize_structure_number(key, value)
	_set_structure_value(country, key, normalized)
	if key == "demographics_population" and _population_mapping_enabled:
		var ratios: Dictionary = country["firm_population_ratios"]
		for firm_key: String in POPULATION_LINKED_FIELDS:
			var scaled: Variant = _normalize_structure_number(
				firm_key, float(ratios[firm_key]) * int(normalized))
			_set_structure_value(country, firm_key, scaled)
	elif key in POPULATION_LINKED_FIELDS and _population_mapping_enabled:
		var ratios: Dictionary = country["firm_population_ratios"]
		if ratios.is_empty():
			_refresh_population_ratios(country)
		else:
			ratios[key] = float(normalized) / float(previous_population)
	_render()


func _apply_structure_number(country: Dictionary, key: String, text: String) -> void:
	var normalized := text.strip_edges()
	if _is_structure_integer(key):
		if normalized.is_valid_int():
			_set_structure_number(country, key, float(normalized.to_int()))
		else:
			_render()
	elif normalized.is_valid_float():
		_set_structure_number(country, key, normalized.to_float())
	else:
		_render()


func _structure_default(key: String, profile: String = "symmetric") -> float:
	var counts := {
		"demographics_population": 80.0 * float(PROFILES.get(profile, PROFILES["symmetric"])["scale"]),
		"n_firms_c": 12.0,
		"n_firms_k": 4.0,
		"n_firms_e": 2.0,
		"n_builders": 5.0,
		"n_banks": 2.0,
	}
	if counts.has(key):
		return float(counts[key])
	if key == "a":
		return float(PROFILES.get(profile, PROFILES["symmetric"])["prod"])
	if key == "alpha":
		return 0.3
	if key == "necessity_share0":
		return float(PROFILES.get(profile, PROFILES["symmetric"])["nec"])
	return 1.0


func _structure_kind(key: String) -> String:
	for group: Dictionary in STRUCT_GROUPS:
		for field: Array in group["fields"]:
			if str(field[1]) == key:
				return str(field[2])
	return "step"


func _factory_structure_value(key: String, profile: String) -> Variant:
	var kind := _structure_kind(key)
	if kind == "toggle":
		return true
	if kind == "select":
		return "exogenous"
	return _normalize_structure_number(key, _structure_default(key, profile))


func _effective_structure_value(country: Dictionary, key: String) -> Variant:
	var overrides: Dictionary = country["overrides"]
	if overrides.has(key):
		return overrides[key]
	return _factory_structure_value(key, str(country["profile"]))


func _baseline_structure_value(country: Dictionary, key: String) -> Variant:
	var baseline: Dictionary = country["baseline_overrides"]
	if baseline.has(key):
		return baseline[key]
	return _factory_structure_value(key, "symmetric")


func _profile_multiplier(key: String, profile: String) -> float:
	var selected: Dictionary = PROFILES.get(profile, PROFILES["symmetric"])
	var symmetric: Dictionary = PROFILES["symmetric"]
	if key == "demographics_population":
		return float(selected["scale"]) / float(symmetric["scale"])
	if key == "a":
		return float(selected["prod"]) / float(symmetric["prod"])
	if key == "necessity_share0":
		return float(selected["nec"]) / float(symmetric["nec"])
	if key in POPULATION_LINKED_FIELDS and _population_mapping_enabled:
		return float(selected["scale"]) / float(symmetric["scale"])
	return 1.0


func _same_structure_value(left: Variant, right: Variant) -> bool:
	if (left is int or left is float) and (right is int or right is float):
		return is_equal_approx(float(left), float(right))
	return left == right


func _mapped_profile_overrides(country: Dictionary, profile: String) -> Dictionary:
	var result: Dictionary = {}
	for group: Dictionary in STRUCT_GROUPS:
		for field: Array in group["fields"]:
			var key := str(field[1])
			var kind := str(field[2])
			var mapped: Variant = _baseline_structure_value(country, key)
			if kind == "step":
				mapped = _normalize_structure_number(
					key, float(mapped) * _profile_multiplier(key, profile))
			var factory: Variant = _factory_structure_value(key, profile)
			if not _same_structure_value(mapped, factory):
				result[key] = mapped
	return result


func _factory_profile_overrides(profile: String) -> Dictionary:
	var result: Dictionary = {}
	if not _population_mapping_enabled:
		return result
	for key: String in POPULATION_LINKED_FIELDS:
		var linked: Variant = _normalize_structure_number(
			key, float(_factory_structure_value(key, "symmetric")) *
			_profile_multiplier(key, profile))
		var factory: Variant = _factory_structure_value(key, profile)
		if not _same_structure_value(linked, factory):
			result[key] = linked
	return result


func _profile_snapshot(country: Dictionary) -> Dictionary:
	var result: Dictionary = {}
	for group: Dictionary in STRUCT_GROUPS:
		for field: Array in group["fields"]:
			var key := str(field[1])
			result[key] = _effective_structure_value(country, key)
	return result


func _select_profile(country: Dictionary, profile: String) -> void:
	if not PROFILES.has(profile):
		return
	if not country.has("baseline_overrides"):
		country["baseline_overrides"] = {}
	if not country.has("firm_population_ratios"):
		country["firm_population_ratios"] = {}
	if profile == "custom":
		var snapshot := _profile_snapshot(country)
		country["profile"] = profile
		country["overrides"] = snapshot
	else:
		country["profile"] = profile
		country["overrides"] = _mapped_profile_overrides(country, profile) \
			if _profile_mapping_enabled else _factory_profile_overrides(profile)
	_refresh_population_ratios(country)


func _refresh_population_ratios(country: Dictionary) -> void:
	var population := maxi(1, int(_effective_structure_value(
		country, "demographics_population")))
	var ratios: Dictionary = {}
	for key: String in POPULATION_LINKED_FIELDS:
		ratios[key] = float(_effective_structure_value(country, key)) / population
	country["firm_population_ratios"] = ratios


func _ensure_population_ratios(country: Dictionary) -> void:
	if not country.has("firm_population_ratios") \
			or (country["firm_population_ratios"] as Dictionary).is_empty():
		_refresh_population_ratios(country)


func _toggle_population_mapping() -> void:
	_population_mapping_enabled = not _population_mapping_enabled
	if _population_mapping_enabled:
		for country: Dictionary in _countries:
			_refresh_population_ratios(country)
	_render()


func _firm_count(country: Dictionary) -> int:
	var overrides: Dictionary = country["overrides"]
	var total := int(overrides.get("n_firms_c", _structure_default("n_firms_c")))
	total += int(overrides.get("n_firms_k", _structure_default("n_firms_k")))
	if bool(overrides.get("energy_enabled", true)):
		total += int(overrides.get("n_firms_e", _structure_default("n_firms_e")))
	if bool(overrides.get("housing_construction_enabled", true)):
		total += int(overrides.get("n_builders", _structure_default("n_builders")))
	return total


func _set_structure_toggle(country: Dictionary, key: String, enabled: bool) -> void:
	_set_structure_value(country, key, enabled)
	var dependants := {
		"bank_enabled": ["interbank", "bonds", "per_firm_equity",
			"household_credit", "government"],
		"government": ["bonds", "housing_construction_enabled"],
		"capital_market": ["per_firm_equity"],
		"housing_enabled": ["housing_market_enabled", "mortgage_enabled",
			"housing_rental_enabled", "housing_construction_enabled"],
		"housing_market_enabled": ["mortgage_enabled",
			"housing_rental_enabled", "housing_construction_enabled"],
	}
	var requirements := {
		"interbank": ["bank_enabled"],
		"bonds": ["bank_enabled", "government"],
		"per_firm_equity": ["capital_market", "bank_enabled"],
		"household_credit": ["bank_enabled"],
		"government": ["bank_enabled"],
		"housing_market_enabled": ["housing_enabled"],
		"mortgage_enabled": ["housing_market_enabled", "housing_enabled",
			"bank_enabled"],
		"housing_rental_enabled": ["housing_market_enabled", "housing_enabled"],
		"housing_construction_enabled": ["housing_market_enabled",
			"housing_enabled", "government", "bank_enabled"],
	}
	if not enabled:
		for dependant: Variant in dependants.get(key, []):
			_set_structure_toggle(country, str(dependant), false)
	else:
		for requirement: Variant in requirements.get(key, []):
			_set_structure_toggle(country, str(requirement), true)


func _add_country() -> void:
	if _countries.size() >= 8: return
	var used: Dictionary = {}
	for country: Dictionary in _countries:
		used[str(country["code"])] = true
	for index in COUNTRY_CODES.size():
		if not used.has(COUNTRY_CODES[index]):
			var country := _country_record(index)
			_select_profile(country, "symmetric")
			_countries.append(country)
			break
	_render()


func _remove_country() -> void:
	if _countries.size() <= 1: return
	_remove_country_at(_countries.size() - 1)


func _delete_selected_country() -> void:
	if _countries.size() <= 1: return
	_remove_country_at(_selected_country)


func _remove_country_at(removed: int) -> void:
	var broken_pegs: Dictionary = {}
	for raw_key: Variant in _policy_values.keys():
		var key := str(raw_key)
		var parts := key.split(".", true, 2)
		if parts.size() == 3 and str(parts[2]) == "peg_anchor" \
				and _policy_values[key] is int \
				and int(_policy_values[key]) == removed:
			broken_pegs[int(parts[0])] = true
	var remapped: Dictionary = {}
	for raw_key: Variant in _policy_values.keys():
		var key := str(raw_key)
		var parts := key.split(".", true, 2)
		if parts.size() != 3:
			continue
		var economy_id := int(parts[0])
		if economy_id == removed:
			continue
		var lever := str(parts[2])
		var value: Variant = _policy_values[key]
		if lever == "peg_anchor":
			if value is int and int(value) == removed:
				continue
			if value is int and int(value) > removed:
				value = int(value) - 1
		elif lever == "sanctions_imposed_on" and value is Array:
			var targets: Array = []
			for raw_target: Variant in value:
				var target := int(raw_target)
				if target != removed:
					targets.append(target - 1 if target > removed else target)
			value = targets
		if broken_pegs.has(economy_id) and lever == "fx_regime":
			value = "float"
		var new_economy := economy_id - 1 if economy_id > removed else economy_id
		remapped["%d.%s.%s" % [new_economy, str(parts[1]), lever]] = value
	_policy_values = remapped
	_countries.remove_at(removed)
	if _player_country == removed:
		_player_country = 0
	elif _player_country > removed:
		_player_country -= 1
	if _policy_country == removed:
		_policy_country = 0
	elif _policy_country > removed:
		_policy_country -= 1
	_selected_country = mini(removed, _countries.size() - 1)
	_render()


func _apply_profile_all() -> void:
	var profile := str(_countries[_selected_country]["profile"])
	for c: Dictionary in _countries:
		_select_profile(c, profile)
	_render()


func _agent_population(country: Dictionary) -> int:
	var overrides: Dictionary = country["overrides"]
	return int(overrides.get(
		"demographics_population", roundi(_structure_default(
			"demographics_population", str(country["profile"])))))


func _country_manifest_overrides(country: Dictionary) -> Dictionary:
	var result: Dictionary = (country["overrides"] as Dictionary).duplicate(true)
	var profile := str(country["profile"])
	for key: String in COUNTRY_SCALE_FIELDS:
		result[key] = int(result.get(key, roundi(_structure_default(key, profile))))
	var population := int(result.get("demographics_population",
		roundi(_structure_default("demographics_population", profile))))
	result["n_households"] = population
	result["demographics_population"] = population \
		if bool(result.get("demographics_enabled", true)) else 0
	return result


func _step_government(parent: VBoxContainer) -> void:
	parent.custom_minimum_size.x = 820
	_page_heading(parent, "@wizard.government.title", "@wizard.government.desc")
	parent.add_child(_kicker("@wizard.government.player_country")); var countries := HFlowContainer.new(); countries.add_theme_constant_override("h_separation", 8); countries.add_theme_constant_override("v_separation", 8); parent.add_child(countries)
	for i in _countries.size():
		var c: Dictionary = _countries[i]; var idx := i; var b := _select_chip("■  %s  %s" % [str(c["code"]), str(c["name"])], i == _player_country, func() -> void: _player_country = idx; _render()); b.add_theme_color_override("font_color", c["color"] if i == _player_country else INK2); countries.add_child(b)
	var sm := MarginContainer.new(); sm.add_theme_constant_override("margin_top", 18); sm.add_theme_constant_override("margin_bottom", 8); sm.add_child(_kicker(_format("wizard.government.five_seats", str(_countries[_player_country]["name"])))); parent.add_child(sm)
	var seatlist := VBoxContainer.new(); seatlist.add_theme_constant_override("separation", 8); parent.add_child(seatlist)
	for seat: Dictionary in SEATS: seatlist.add_child(_seat_row(seat))
	var note := _label(_format("wizard.government.seat_count", _human_seat_count()), 11, INK3); var nm := MarginContainer.new(); nm.add_theme_constant_override("margin_top", 6); nm.add_child(note); parent.add_child(nm)
	if _countries.size() > 1:
		var om := MarginContainer.new(); om.add_theme_constant_override("margin_top", 18); om.add_theme_constant_override("margin_bottom", 8); om.add_child(_kicker("@wizard.government.other_countries")); parent.add_child(om)
		var others := GridContainer.new(); others.columns = 2; others.add_theme_constant_override("h_separation", 9); others.add_theme_constant_override("v_separation", 9); parent.add_child(others)
		for i in _countries.size():
			if i != _player_country:
				others.add_child(_frozen_country(_countries[i]))
	var rm := MarginContainer.new(); rm.add_theme_constant_override("margin_top", 18); rm.add_theme_constant_override("margin_bottom", 8); rm.add_child(_kicker("@wizard.government.run_mode")); parent.add_child(rm)
	var modes := HBoxContainer.new(); modes.add_theme_constant_override("separation", 9); parent.add_child(modes)
	for mode: Array in [["interactive", "@wizard.mode.interactive", "@wizard.mode.interactive_desc"], ["realtime", "@wizard.mode.realtime", "@wizard.mode.realtime_desc"], ["batch", "@wizard.mode.batch", "@wizard.mode.batch_desc"]]:
		var id := str(mode[0]); var locked := id == "batch" and _human_seat_count() > 0; var p := _mode_card(str(mode[1]), str(mode[2]), _run_mode == id, locked, func() -> void: _run_mode = id; _render()); modes.add_child(p)
	var cal := _button(("▼" if _calendar_open else "▶") + _text("@wizard.government.calendar"), func() -> void: _calendar_open = not _calendar_open; _render(), false, 12, true); var cm := MarginContainer.new(); cm.add_theme_constant_override("margin_top", 12); cm.add_child(cal); parent.add_child(cm)
	if _calendar_open:
		var cp := _panel(PANEL, LINE2, 11, 11); var cv := VBoxContainer.new(); cv.add_theme_constant_override("separation", 7); cp.add_child(cv)
		for line: Array in [["@wizard.calendar.monetary", "@wizard.calendar.month_half", "@wizard.calendar.45_days"], ["@wizard.calendar.quarterly_groups", "@wizard.calendar.quarterly", "@wizard.calendar.91_days"], ["@wizard.calendar.annual_groups", "@wizard.calendar.annual", "@wizard.calendar.365_days"]]:
			var lr := HBoxContainer.new()
			lr.add_child(_label(str(line[0]), 11, Color("3a4956")))
			lr.add_child(_h_spacer())
			lr.add_child(_label(str(line[1]), 11, TEAL_DK, true))
			lr.add_child(_label(str(line[2]), 10, MUTED, false, true))
			cv.add_child(lr)
		parent.add_child(cp)


func _seat_row(seat: Dictionary) -> Control:
	var p := _panel(PAPER, LINE, 11, 10); var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 12); p.add_child(row); row.add_child(_dot(seat["color"], 9)); var name := _label(str(seat["name"]), 14, INK, true); name.custom_minimum_size.x = 96; row.add_child(name); var groups := _label(str(seat["groups"]), 10, MUTED, false, true); groups.size_flags_horizontal = Control.SIZE_EXPAND_FILL; row.add_child(groups)
	var option := OptionButton.new(); option.custom_minimum_size.x = 190; option.add_theme_font_size_override("font_size", 12)
	var sid := str(seat["id"])
	for occ: Array in OCCUPANTS:
		if str(occ[0]) == "rl" and sid != "treasury":
			continue
		option.add_item(_text(str(occ[1]))); option.set_item_metadata(option.item_count - 1, occ[0]); if str(_seat_occupants.get(str(seat["id"]), "human")) == str(occ[0]): option.select(option.item_count - 1)
	option.item_selected.connect(func(index: int) -> void:
		_seat_occupants[sid] = str(option.get_item_metadata(index))
		if _run_mode == "batch" and str(_seat_occupants[sid]) == "human":
			_run_mode = "interactive"
		_render()); row.add_child(option); return p


func _frozen_country(country: Dictionary) -> Control:
	var p := _panel(PANEL, LINE, 10, 10); p.size_flags_horizontal = Control.SIZE_EXPAND_FILL; var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 10); p.add_child(row); row.add_child(_dot(country["color"], 9)); var v := VBoxContainer.new(); v.add_child(_label(str(country["name"]), 13, INK, true)); v.add_child(_label("@wizard.government.no_controller", 10, INK2)); row.add_child(v); return p


func _mode_card(title: String, note: String, active: bool, locked: bool, callback: Callable) -> Control:
	var b := Button.new(); b.custom_minimum_size.y = 72; b.size_flags_horizontal = Control.SIZE_EXPAND_FILL; b.disabled = locked; b.modulate.a = 0.5 if locked else 1.0; b.add_theme_stylebox_override("normal", _sb(TEAL_BG if active else PAPER, TEAL_BD if active else LINE, 10, 10)); b.pressed.connect(callback); var v := VBoxContainer.new(); v.mouse_filter = Control.MOUSE_FILTER_IGNORE; v.add_child(_label(title, 13, INK, true)); var l := _label(note, 10, Color("68788b")); l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; l.max_lines_visible = 2; l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS; v.add_child(l); _fill_inset(v, 10); b.add_child(v); return b


func _human_seat_count() -> int:
	var n := 0
	for value in _seat_occupants.values():
		if str(value) == "human":
			n += 1
	return n


func _step_policy(parent: VBoxContainer) -> void:
	parent.custom_minimum_size.x = 800
	_page_heading(parent, "@wizard.policy.title", "@wizard.policy.desc")
	var selectors := HBoxContainer.new(); selectors.add_theme_constant_override("separation", 8); parent.add_child(selectors)
	var country_opt := OptionButton.new()
	for i in _countries.size():
		country_opt.add_item(str(_countries[i]["name"]) + (_text("@wizard.policy.player_suffix") if i == _player_country else ""))
	country_opt.select(_policy_country)
	country_opt.item_selected.connect(func(index: int) -> void: _policy_country = index; _render())
	selectors.add_child(country_opt)
	var tabs := PanelContainer.new(); tabs.add_theme_stylebox_override("panel", _sb(PANEL2, LINE, 9, 2)); var th := HBoxContainer.new(); th.add_theme_constant_override("separation", 2); tabs.add_child(th)
	for seat: Dictionary in SEATS:
		var sid := str(seat["id"])
		var b := _button(str(seat["name"]), func() -> void: _policy_seat = sid; _render(), false, 11, _policy_seat != sid)
		if _policy_seat == sid:
			b.add_theme_stylebox_override("normal", _sb(PAPER, PAPER, 7, 5))
		th.add_child(b)
	selectors.add_child(tabs)
	var filters := HBoxContainer.new(); filters.add_theme_constant_override("separation", 8); var fm := MarginContainer.new(); fm.add_theme_constant_override("margin_top", 10); fm.add_theme_constant_override("margin_bottom", 13); fm.add_child(filters); parent.add_child(fm)
	var search := LineEdit.new(); search.size_flags_horizontal = Control.SIZE_EXPAND_FILL; search.text = _policy_search; search.placeholder_text = _text("@wizard.policy.search"); search.add_theme_stylebox_override("normal", _sb(PANEL, LINE, 8, 7)); search.text_submitted.connect(func(text: String) -> void: _policy_search = text.strip_edges(); _render()); filters.add_child(search)
	for fil: Array in [["all", "@wizard.filter.all"], ["changed", "@wizard.filter.changed"], ["mine", "@wizard.filter.seat"]]:
		var id := str(fil[0])
		filters.add_child(_select_chip(str(fil[1]), _policy_filter == id, func() -> void: _policy_filter = id; _render()))
	var found := 0
	for raw: Dictionary in _policy_groups_for_seat(_policy_seat):
		var group := raw; var visible_levers: Array = []
		for lev: Array in group["levers"]:
			var key := _policy_key(str(lev[1])); var changed := _policy_values.has(key)
			if _policy_filter == "changed" and not changed: continue
			if not _policy_search.is_empty() and not _text(str(lev[0])).contains(_policy_search) and not str(lev[1]).contains(_policy_search): continue
			if str(lev[1]) == "manual_policy_rate" and str(_policy_value("monetary_regime", "taylor")) != "manual": continue
			if str(lev[1]) == "peg_anchor" and str(_policy_value("fx_regime", "float")) != "peg": continue
			visible_levers.append(lev)
		if visible_levers.is_empty(): continue
		found += visible_levers.size(); var gh := HBoxContainer.new(); gh.add_child(_label(str(group["group"]), 12, Color("3a4956"), true)); gh.add_child(_label(str(group["id"]), 9, MUTED, false, true)); gh.add_child(_h_rule()); parent.add_child(gh)
		var lv := VBoxContainer.new(); lv.add_theme_constant_override("separation", 7); var lm := MarginContainer.new(); lm.add_theme_constant_override("margin_bottom", 8); lm.add_child(lv); parent.add_child(lm)
		for lev: Array in visible_levers:
			lv.add_child(_policy_row(lev))
	if found == 0:
		var empty := _label("@wizard.policy.no_match", 13, MUTED); empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; var em := MarginContainer.new(); em.add_theme_constant_override("margin_top", 40); em.add_child(empty); parent.add_child(em)


func _policy_groups_for_seat(seat: String) -> Array:
	var schema_key := str(SEAT_SCHEMA_KEYS.get(seat, seat))
	var raw_levers: Array = _policy_schemas.get(schema_key, {}).get("levers", [])
	if raw_levers.is_empty():
		return POLICY_PREVIEW.get(seat, [])
	var preview: Dictionary = {}
	for fallback_group: Dictionary in POLICY_PREVIEW.get(seat, []):
		for fallback_lever: Array in fallback_group["levers"]:
			preview[str(fallback_lever[1])] = fallback_lever
	var groups: Array = []
	var group_indexes: Dictionary = {}
	for raw: Dictionary in raw_levers:
		var id := str(raw.get("name", ""))
		var fallback: Array = preview.get(id, [])
		var label := str(raw.get("display_name", fallback[0] if not fallback.is_empty() else id))
		var group_id := str(raw.get("decision_group", "other"))
		if not group_indexes.has(group_id):
			group_indexes[group_id] = groups.size()
			groups.append({"group": str(raw.get("display_group", group_id)),
				"id": group_id, "levers": []})
		var kind := _schema_policy_kind(raw, fallback)
		var current: Variant = raw.get("current_value")
		if current == null and not fallback.is_empty() and not bool(raw.get("nullable", false)):
			current = fallback[3]
		var step: Variant = raw.get("control_scale")
		if step == null:
			step = raw.get("max_step")
		if step == null and not fallback.is_empty():
			step = fallback[4]
		if step == null:
			step = 1.0
		var row: Array = [label, id, kind, current, float(step), raw]
		(groups[int(group_indexes[group_id])]["levers"] as Array).append(row)
	return groups


func _schema_policy_kind(raw: Dictionary, fallback: Array) -> String:
	var id := str(raw.get("name", ""))
	if id == "monetary_regime":
		return "regime"
	if id == "fx_regime":
		return "fx"
	if id == "energy_rationing":
		return "ration"
	if id == "peg_anchor":
		return "anchor"
	if bool(raw.get("nullable", false)) and str(raw.get("value_kind", "")) == "number":
		return "nullable_number"
	if not fallback.is_empty() and str(fallback[2]) in ["annual_rate", "percent"]:
		return str(fallback[2])
	return str(raw.get("value_kind", "number"))


func _policy_row(lever: Array) -> Control:
	var name := str(lever[0]); var id := str(lever[1]); var kind := str(lever[2]); var base: Variant = lever[3]; var step := float(lever[4]); var meta: Dictionary = lever[5] if lever.size() > 5 else {}; var key := _policy_key(id); var changed := _policy_values.has(key); var value: Variant = _policy_values.get(key, base)
	var p := _panel(BLUE_BG if changed else PAPER, BLUE_BD if changed else LINE, 10, 9); var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 12); p.add_child(row)
	var words := VBoxContainer.new(); words.size_flags_horizontal = Control.SIZE_EXPAND_FILL; var nh := HBoxContainer.new(); nh.add_child(_label(name, 13, INK)); nh.add_child(_chip(_text("@wizard.policy.local_override" if changed else "@wizard.policy.inherited"), BLUE if changed else INK2, BLUE_BG if changed else Color("eef2f7"), Color(0, 0, 0, 0))); words.add_child(nh); words.add_child(_label(id, 9, MUTED, false, true)); row.add_child(words)
	if kind == "bool":
		row.add_child(_switch_button(bool(value), func() -> void:
			_set_policy_bool(id, key, not bool(value), meta)))
	elif kind in ["regime", "fx", "ration"]:
		var opts: Array = [["exogenous", "@wizard.choice.exogenous"], ["taylor", "@wizard.choice.taylor"], ["manual", "@wizard.choice.manual"]] if kind == "regime" else ([["float", "@wizard.choice.float"], ["peg", "@wizard.choice.peg"]] if kind == "fx" else [["market", "@wizard.choice.market"], ["household_first", "@wizard.choice.household_first"], ["industry_first", "@wizard.choice.industry_first"]])
		var seg := HBoxContainer.new(); seg.add_theme_constant_override("separation", 2)
		for opt: Array in opts:
			var ov := str(opt[0])
			if id == "fx_regime" and ov == "peg" and _countries.size() <= 1:
				continue
			seg.add_child(_select_chip(str(opt[1]), str(value) == ov, func() -> void:
				_policy_values[key] = ov
				if id == "monetary_regime":
					if ov == "manual":
						_policy_values[_policy_key("manual_policy_rate")] = 0.000134
					else:
						_policy_values.erase(_policy_key("manual_policy_rate"))
				elif id == "fx_regime":
					if ov == "float":
						_policy_values.erase(_policy_key("peg_anchor"))
					elif not _policy_values.has(_policy_key("peg_anchor")):
						for i in _countries.size():
							if i != _policy_country:
								_policy_values[_policy_key("peg_anchor")] = i
								break
				_render()))
		row.add_child(seg)
	elif kind == "choice":
		var generic_options := OptionButton.new()
		for raw_choice: Variant in meta.get("choices", []):
			var choice := str(raw_choice)
			generic_options.add_item(str(meta.get("display_choices", {}).get(choice, choice)))
			generic_options.set_item_metadata(generic_options.item_count - 1, choice)
			if str(value) == choice:
				generic_options.select(generic_options.item_count - 1)
		generic_options.item_selected.connect(func(index: int) -> void:
			_policy_values[key] = generic_options.get_item_metadata(index)
			_render())
		row.add_child(generic_options)
	elif kind == "anchor":
		var op := OptionButton.new()
		var current_anchor: Variant = _policy_values.get(key, null)
		for i in _countries.size():
			if i != _policy_country:
				op.add_item(str(_countries[i]["name"]))
				op.set_item_metadata(op.item_count - 1, i)
				if current_anchor == i:
					op.select(op.item_count - 1)
		op.item_selected.connect(func(index: int) -> void:
			_policy_values[key] = op.get_item_metadata(index)
			_render())
		row.add_child(op)
	elif kind == "economy_set":
		var targets: Array = value.duplicate() if value is Array else []
		var target_flow := HFlowContainer.new()
		target_flow.add_theme_constant_override("h_separation", 5)
		target_flow.add_theme_constant_override("v_separation", 5)
		for i in _countries.size():
			if i == _policy_country:
				continue
			var economy_id := i
			target_flow.add_child(_select_chip(str(_countries[i]["code"]),
				targets.has(economy_id), func() -> void:
					var next_targets: Array = targets.duplicate()
					if next_targets.has(economy_id):
						next_targets.erase(economy_id)
					else:
						next_targets.append(economy_id)
						next_targets.sort()
					_policy_values[key] = next_targets
					_render()))
		row.add_child(target_flow)
	elif kind == "nullable_number":
		var nullable_controls := HBoxContainer.new()
		nullable_controls.add_theme_constant_override("separation", 5)
		if id != "manual_policy_rate":
			nullable_controls.add_child(_select_chip("@wizard.value.unlimited", value == null, func() -> void:
				_policy_values[key] = null
				_render()))
		if value == null:
			nullable_controls.add_child(_button("@wizard.value.set", func() -> void:
				var candidate := float(meta.get("minimum", 0.0)) + step
				_policy_values[key] = minf(candidate, float(meta.get("maximum", candidate)))
				_render(), false, 11))
		else:
			nullable_controls.add_child(_mini_stepper(_policy_format("number", value, meta),
				func() -> void:
					_policy_values[key] = maxf(float(meta.get("minimum", -INF)), float(value) - step)
					_render(),
				func() -> void:
					_policy_values[key] = minf(float(meta.get("maximum", INF)), float(value) + step)
					_render(),
				func(text: String) -> void:
					_apply_policy_number(key, "number", text, meta)))
		row.add_child(nullable_controls)
	else:
		row.add_child(_mini_stepper(_policy_format(kind, value, meta),
			func() -> void:
				var next := maxf(float(meta.get("minimum", -INF)), float(value) - step)
				_policy_values[key] = roundi(next) if kind == "integer" else next
				_render(),
			func() -> void:
				var next := minf(float(meta.get("maximum", INF)), float(value) + step)
				_policy_values[key] = roundi(next) if kind == "integer" else next
				_render(),
			func(text: String) -> void:
				_apply_policy_number(key, kind, text, meta)))
	return p


func _set_policy_bool(id: String, key: String, next: bool, meta: Dictionary) -> void:
	if next:
		for raw_parent: Variant in meta.get("enabled_if", []):
			_policy_values[_policy_key(str(raw_parent))] = true
	else:
		var schema_key := str(SEAT_SCHEMA_KEYS.get(_policy_seat, _policy_seat))
		for raw: Dictionary in _policy_schemas.get(schema_key, {}).get("levers", []):
			if id in raw.get("enabled_if", []):
				_policy_values.erase(_policy_key(str(raw.get("name", ""))))
	_policy_values[key] = next
	_render()


func _policy_key(lever: String) -> String: return "%d.%s.%s" % [_policy_country, _policy_seat, lever]
func _policy_value(lever: String, fallback: Variant) -> Variant: return _policy_values.get(_policy_key(lever), fallback)


func _apply_policy_number(key: String, kind: String, text: String, meta: Dictionary) -> void:
	var normalized := text.strip_edges().replace(
		_text("@wizard.value.annual_suffix"), ""
	).replace("%", "").replace("×", "").replace(
		_text("@wizard.value.day_suffix"), ""
	).strip_edges()
	if not normalized.is_valid_float():
		_render()
		return
	var value := normalized.to_float()
	var display_format := str(meta.get("display_format", ""))
	if display_format == "percent" or kind == "percent":
		value /= 100.0
	elif kind == "annual_rate":
		if value <= -100.0:
			_render()
			return
		value = pow(1.0 + value / 100.0, 1.0 / 365.0) - 1.0
	value = clampf(
		value,
		float(meta.get("minimum", -INF)),
		float(meta.get("maximum", INF)),
	)
	_policy_values[key] = roundi(value) if kind == "integer" else value
	_render()


func _policy_format(kind: String, value: Variant, meta: Dictionary = {}) -> String:
	if value == null:
		return _text("@wizard.value.unset")
	var display_format := str(meta.get("display_format", ""))
	if display_format == "percent":
		var pct := float(value) * 100.0
		return ("%.4f%%" if absf(pct) < 0.1 and absf(pct) > 0.0 else "%.2f%%") % pct
	if display_format == "multiplier": return "%.2f×" % float(value)
	if display_format == "days": return _format("wizard.value.days", roundi(float(value)))
	if kind == "annual_rate":
		return _format("wizard.value.annual_rate", (pow(1.0 + float(value), 365.0) - 1.0) * 100.0)
	if kind == "percent": return "%.1f%%" % (float(value) * 100.0)
	if kind == "integer": return "%d" % roundi(float(value))
	if absf(float(meta.get("control_scale", 1.0))) < 0.001:
		return "%.5f" % float(value)
	return "%.3f" % float(value)


func _step_review(parent: VBoxContainer) -> void:
	parent.custom_minimum_size.x = 900
	_page_heading(parent, "@wizard.review.title", "@wizard.review.desc")
	var banners := HBoxContainer.new(); banners.add_theme_constant_override("separation", 9); parent.add_child(banners)
	banners.add_child(_validation_card("✓", "@wizard.review.protocol_complete", "@wizard.review.engine_validation", GREEN, GREEN_BG, GREEN_BD))
	banners.add_child(_validation_card("✓", "@wizard.review.config_bound", "@wizard.review.not_preview", GREEN, GREEN_BG, GREEN_BD))
	banners.add_child(_validation_card("ℹ", "@wizard.review.reproducible", "@wizard.review.versioned_seed", BLUE, BLUE_BG, BLUE_BD))
	if not _launch_error.is_empty():
		var error_box := _panel(RED_BG, RED_BD, 9, 10)
		var error_text := _label(_format("wizard.review.rejected", _launch_error), 12, RED)
		error_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		error_box.add_child(error_text)
		parent.add_child(error_box)
	var manifest := GridContainer.new(); manifest.columns = 2; manifest.add_theme_constant_override("h_separation", 12); manifest.add_theme_constant_override("v_separation", 12); parent.add_child(manifest)
	var scenario := _scenario_name()
	var country_rows: Array = []
	for c: Dictionary in _countries:
		country_rows.append([str(c["name"]), "%s · %s" % [_text(str(PROFILES[str(c["profile"])]["name"])), _format("wizard.countries.population", _agent_population(c))]])
	manifest.add_child(_manifest_card("@wizard.manifest.world", BLUE, [["@wizard.field.country_count", str(_countries.size())], ["@wizard.start_date", _date_iso(_start_date)], ["@wizard.run_duration", _duration_label()], ["@wizard.field.end_date", "@wizard.field.no_end" if _duration == "inf" else _date_iso(_end_date())], ["seed", str(_seed)], ["@wizard.field.cross_border", _cross_label()]]))
	manifest.add_child(_manifest_card("@wizard.manifest.countries", TEAL, country_rows))
	manifest.add_child(_manifest_card("@wizard.manifest.policy", AMBER, [["@wizard.field.relative_preset", _format("wizard.field.change_count", _policy_values.size())], ["@wizard.field.application_state", "@wizard.field.atomic_launch"], ["@wizard.field.monetary_regime", str(_policy_value("monetary_regime", "taylor"))], ["@wizard.field.fx_regime", str(_policy_value("fx_regime", "float"))]]))
	manifest.add_child(_manifest_card("@wizard.manifest.scenario", RED, [["@wizard.field.scenario", scenario], ["@wizard.field.calibration", "@wizard.field.reduced_prototype" if _scenario != "sandbox" else "—"], ["ShockTape", "@wizard.field.shock_tape_bound"]]))
	manifest.add_child(_manifest_card("@wizard.manifest.reproducibility", Color("3f6db2"), [["schema", "NewGameSpec v1"], ["base_seed", "%d → +i×1e6" % _seed], ["@wizard.field.config_authority", "@wizard.field.backend_config"], ["@wizard.field.protocol", "desktop v4"]]))


func _validation_card(icon: String, title: String, sub: String, fg: Color, bg: Color, border: Color) -> Control:
	var p := _panel(bg, border, 10, 10); p.size_flags_horizontal = Control.SIZE_EXPAND_FILL; var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 9); p.add_child(row); row.add_child(_label(icon, 16, fg)); var v := VBoxContainer.new(); v.add_child(_label(title, 13, fg, true)); v.add_child(_label(sub, 10, INK3)); row.add_child(v); return p


func _manifest_card(title: String, accent: Color, rows: Array) -> Control:
	var p := _panel(PAPER, LINE, 12, 12)
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 7)
	p.add_child(v)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 8)
	h.add_child(_dot(accent, 7))
	h.add_child(_label(title, 10, Color("68788b"), false, true))
	v.add_child(h)
	for raw: Array in rows:
		var row := HBoxContainer.new()
		var key := _label(str(raw[0]), 11, INK2)
		key.custom_minimum_size.x = 96
		row.add_child(key)
		var value := _label(str(raw[1]), 12, INK)
		value.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(value)
		v.add_child(row)
	return p


func _summary_panel() -> Control:
	var p := PanelContainer.new(); p.custom_minimum_size = Vector2(322, 0); p.add_theme_stylebox_override("panel", _sb(PANEL, LINE2, 0, 14)); var col := VBoxContainer.new(); col.add_theme_constant_override("separation", 12); p.add_child(col)
	var head := HBoxContainer.new(); head.add_child(_kicker("@wizard.summary.title")); head.add_child(_h_spacer()); head.add_child(_dot(GREEN, 6)); head.add_child(_label("@wizard.summary.connected", 10, GREEN)); col.add_child(head)
	col.add_child(_summary_section("@wizard.summary.scenario", [["@wizard.field.scenario", _scenario_name()]])); col.add_child(_summary_section("@wizard.summary.world", [["@wizard.field.country_count", str(_countries.size())], ["@wizard.summary.start", _date_iso(_start_date)], ["@wizard.summary.duration", _duration_label()], ["@wizard.summary.end", "@wizard.field.no_end" if _duration == "inf" else _date_iso(_end_date())], ["seed", str(_seed)], ["@wizard.field.cross_border", _cross_label()]]))
	var cr: Array = []
	for c: Dictionary in _countries.slice(0, 4):
		cr.append([str(c["code"]), _text(str(PROFILES[str(c["profile"])]["name"]))])
	col.add_child(_summary_section("@wizard.summary.countries", cr))
	col.add_child(_summary_section("@wizard.summary.policy", [["@wizard.summary.changes", _format("wizard.summary.change_count", _policy_values.size())]]))
	col.add_child(_v_spacer())
	var protocol := _label("@wizard.summary.protocol", 10, GREEN, false, true); protocol.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; col.add_child(protocol); return p


func _summary_section(title: String, rows: Array) -> Control:
	var wrap := VBoxContainer.new()
	wrap.add_theme_constant_override("separation", 6)
	wrap.add_child(_label(title, 11, INK2, true))
	var p := _panel(PAPER, LINE2, 9, 8)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 5)
	p.add_child(v)
	for raw: Array in rows:
		var row := HBoxContainer.new()
		var key := _label(str(raw[0]), 11, INK3)
		key.custom_minimum_size.x = 64
		row.add_child(key)
		var value := _label(str(raw[1]), 11, INK)
		value.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		row.add_child(value)
		v.add_child(row)
	wrap.add_child(p)
	return wrap


func _wizard_footer() -> Control:
	var p := PanelContainer.new(); p.custom_minimum_size = Vector2(0, 60); p.add_theme_stylebox_override("panel", _sb(PAPER, LINE2, 0, 12)); var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 12); p.add_child(row); row.add_child(_button("@wizard.nav.back", _go_back, false, 13)); row.add_child(_h_spacer())
	var dots := HBoxContainer.new(); dots.add_theme_constant_override("separation", 6)
	for i in STEP_META.size():
		var bar := ColorRect.new()
		bar.color = TEAL if i + 1 == _step else (TEAL_BD if i + 1 < _step else LINE)
		bar.custom_minimum_size = Vector2(22 if i + 1 == _step else 6, 6)
		dots.add_child(bar)
	row.add_child(dots)
	row.add_child(_label(_format("wizard.nav.step", _step), 11, INK3, false, true))
	row.add_child(_h_spacer())
	if _step == STEP_META.size(): row.add_child(_button("@wizard.nav.launch", _begin_launch, true, 14))
	else: row.add_child(_button("@wizard.nav.next", func() -> void: _step += 1; _render(), true, 14))
	return p


func _go_back() -> void:
	if _step > 1:
		_step -= 1
	else:
		_screen = "home"
	_render()


func _begin_launch() -> void:
	_screen = "launching"; _launch_progress = 0; _launch_error = ""; _launch_timer.start(); _render()


func restore_after_launch_error(message: String) -> void:
	_launch_timer.stop()
	_launch_error = message
	_screen = "wizard"
	_step = STEP_META.size()
	show()
	_render()


func _advance_launch() -> void:
	_launch_progress += 1
	if _launch_progress >= 4:
		_launch_timer.stop()
		launch_requested.emit({"spec": _draft_manifest()})
		hide()
	else: _render()


func _build_launch(parent: Control) -> void:
	var center := CenterContainer.new(); center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); parent.add_child(center); var col := VBoxContainer.new(); col.custom_minimum_size.x = 440; col.add_theme_constant_override("separation", 10); center.add_child(col); var h := HBoxContainer.new(); h.alignment = BoxContainer.ALIGNMENT_CENTER; h.add_theme_constant_override("separation", 12); h.add_child(_label("◌", 25, TEAL, true)); h.add_child(_label("@wizard.launch.building", 19, INK, true)); var hm := MarginContainer.new(); hm.add_theme_constant_override("margin_bottom", 20); hm.add_child(h); col.add_child(hm)
	var defs: Array = [[_format("wizard.launch.economies", _countries.size()), _format("wizard.launch.population", _total_population_seed())], ["@wizard.launch.scenario", _scenario_name()], ["@wizard.manifest.policy", _format("wizard.summary.change_count", _policy_values.size())], ["@wizard.launch.rng", "seed %d" % _seed]]
	for i in defs.size(): var done := i < _launch_progress; var active := i == _launch_progress; var p := _panel(PAPER, TEAL_BD if active else LINE2, 10, 10); p.modulate.a = 1.0 if done or active else 0.5; var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 12); p.add_child(row); var mark := _chip("✓" if done else ("·" if active else ""), Color.WHITE, GREEN if done else (TEAL if active else LINE), Color(0, 0, 0, 0)); row.add_child(mark); var text := _label(str(defs[i][0]), 13, INK); text.size_flags_horizontal = Control.SIZE_EXPAND_FILL; row.add_child(text); row.add_child(_label(str(defs[i][1]), 11, MUTED, false, true)); col.add_child(p)


func _draft_manifest() -> Dictionary:
	var world := {"trade": _trade, "capital": _capital, "migration": _migration}
	world.merge(_cross_values, true)
	var countries: Array = []
	for country: Dictionary in _countries:
		countries.append({"name": str(country["name"]), "code": str(country["code"]),
			"profile": str(country["profile"]),
			"overrides": _country_manifest_overrides(country)})
	return {"schema_version": 1, "seed": _seed, "start_date": _date_iso(_start_date),
		"scenario": _scenario, "duration": _duration_ticks_value(),
		"world": world,
		"countries": countries, "player_country": _player_country,
		"run_mode": _run_mode, "seats": _seat_occupants.duplicate(true),
		"initial_policy_overrides": _policy_values.duplicate(true)}


func _build_settings(parent: Control) -> void:
	var shade := ColorRect.new(); shade.color = Color(0.086, 0.137, 0.204, 0.34); shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); parent.add_child(shade); var center := CenterContainer.new(); center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); shade.add_child(center); var panel := _panel(PAPER, LINE, 16, 0); panel.custom_minimum_size = Vector2(880, 650); center.add_child(panel); var shell := VBoxContainer.new(); panel.add_child(shell)
	var headp := MarginContainer.new(); headp.add_theme_constant_override("margin_left", 20); headp.add_theme_constant_override("margin_right", 20); headp.add_theme_constant_override("margin_top", 14); headp.add_theme_constant_override("margin_bottom", 14); var head := HBoxContainer.new(); head.add_theme_constant_override("separation", 10); headp.add_child(head); head.add_child(_label("@settings.title", 16, INK, true)); head.add_child(_label("@settings.subtitle", 11, INK3, false, true)); head.add_child(_h_spacer()); head.add_child(_square_button("×", func() -> void: _settings_open = false; _render(), 30)); shell.add_child(headp); shell.add_child(_h_line())
	var bodym := MarginContainer.new(); bodym.size_flags_vertical = Control.SIZE_EXPAND_FILL; bodym.add_theme_constant_override("margin_left", 20); bodym.add_theme_constant_override("margin_right", 20); bodym.add_theme_constant_override("margin_top", 18); bodym.add_theme_constant_override("margin_bottom", 18); var grid := GridContainer.new(); grid.columns = 2; grid.add_theme_constant_override("h_separation", 16); grid.add_theme_constant_override("v_separation", 16); bodym.add_child(grid); shell.add_child(bodym)
	for group: Array in [["@settings.group.display", [["@settings.fullscreen", "toggle", false], ["@settings.ui_scale", "value", "100%"], ["@settings.density", "value", "@settings.comfortable"]]], ["@settings.group.language", [["@settings.language", "value", "@settings.language.zh_cn"], ["@settings.number_abbreviation", "toggle", true]]], ["@settings.group.accessibility", [["@settings.color_safe", "toggle", false], ["@settings.reduce_motion", "toggle", false], ["@settings.high_contrast", "toggle", true]]], ["@settings.group.saves", [["@settings.autosave", "toggle", true], ["@settings.keep_count", "value", "10"]]], ["@settings.group.developer", [["@settings.show_internal", "toggle", true], ["@settings.audio", "value", "@settings.not_implemented"]]]]: grid.add_child(_settings_group(str(group[0]), group[1]))
	shell.add_child(_h_line()); var footm := MarginContainer.new(); footm.add_theme_constant_override("margin_left", 20); footm.add_theme_constant_override("margin_right", 20); footm.add_theme_constant_override("margin_top", 12); footm.add_theme_constant_override("margin_bottom", 12); var foot := HBoxContainer.new(); foot.add_child(_label("@settings.restart", 10, AMBER, false, true)); foot.add_child(_h_spacer()); foot.add_child(_button("@settings.restore", func() -> void: pass, false, 12)); foot.add_child(_button("@settings.apply", func() -> void: _settings_open = false; _render(), true, 12)); footm.add_child(foot); shell.add_child(footm)


func _settings_group(title: String, items: Array) -> Control:
	var wrap := VBoxContainer.new()
	wrap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	wrap.add_theme_constant_override("separation", 7)
	wrap.add_child(_label(title, 12, Color("3a4956"), true))
	for item: Array in items:
		var p := _panel(PANEL, LINE2, 9, 8)
		var row := HBoxContainer.new()
		p.add_child(row)
		var item_label := _label(str(item[0]), 12, INK)
		item_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(item_label)
		if str(item[1]) == "toggle":
			var key := str(item[0])
			var current := bool(_settings_values.get(key, bool(item[2])))
			row.add_child(_switch_button(current, func() -> void:
				_settings_values[key] = not current
				_render()))
		else:
			row.add_child(_label(str(item[2]), 11, INK2, false, true))
		wrap.add_child(p)
	return wrap


func _scenario_name() -> String:
	for scenario: Dictionary in SCENARIOS:
		if str(scenario["id"]) == _scenario:
			return _text(str(scenario["name"]))
	return _text("@scenario.sandbox.name")


func _duration_label() -> String:
	if _duration == "inf":
		return _text("@wizard.duration.infinite")
	var prefix: String = _text(str({"1y": "@wizard.duration.1y", "5y": "@wizard.duration.5y", "10y": "@wizard.duration.10y", "custom": "@wizard.duration.custom"}.get(_duration, "@wizard.duration.custom")))
	return "%s · %s" % [prefix, _format("wizard.value.days", int(_duration_ticks_value()))]
func _cross_label() -> String: return " · ".join([_text("@wizard.cross.trade") if _trade else "", _text("@wizard.cross.capital") if _capital else "", _text("@wizard.cross.migration") if _migration else ""].filter(func(x: String) -> bool: return not x.is_empty()))
func _total_population_seed() -> int:
	var total := 0
	for country: Dictionary in _countries:
		total += _agent_population(country)
	return total


func _sb(bg: Color, border: Color, radius: int, padding: int) -> StyleBoxFlat:
	var s := StyleBoxFlat.new(); s.bg_color = bg; s.border_color = border
	for side in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]: s.set_border_width(side, 1); s.set_corner_radius(side, radius); s.set_content_margin(side, padding)
	return s


func _panel(bg: Color, border: Color, radius: int, padding: int) -> PanelContainer:
	var p := PanelContainer.new(); p.add_theme_stylebox_override("panel", _sb(bg, border, radius, padding)); return p


func _label(text: String, size: int, color: Color, bold := false, mono := false) -> Label:
	var l := Label.new()
	l.text = _text(text)
	l.add_theme_font_override("font", _mono if mono else _sans)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	if bold:
		l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.15))
	return l


func _button(text: String, callback: Callable, primary := false, size := 12, flat := false) -> Button:
	var b := Button.new(); b.text = _text(text); b.add_theme_font_override("font", _sans); b.add_theme_font_size_override("font_size", size); b.add_theme_color_override("font_color", Color.WHITE if primary else INK2); b.add_theme_stylebox_override("normal", _sb(TEAL if primary else (Color(0, 0, 0, 0) if flat else PANEL2), TEAL_DK if primary else (Color(0, 0, 0, 0) if flat else LINE), 9, 8)); b.add_theme_stylebox_override("hover", _sb(TEAL_DK if primary else PAPER, TEAL_DK if primary else TEAL, 9, 7)); b.pressed.connect(callback); return b


func _text(value: String) -> String:
	return LocaleCatalogScript.resolve(value)


func _format(key: String, values: Variant) -> String:
	return LocaleCatalogScript.format(key, values)


func _square_button(text: String, callback: Callable, side: int) -> Button:
	var b := _button(text, callback, false, 14); b.custom_minimum_size = Vector2(side, side); return b


func _select_chip(text: String, active: bool, callback: Callable) -> Button:
	var b := _button(text, callback, false, 12); b.add_theme_color_override("font_color", TEAL_DK if active else INK2); b.add_theme_stylebox_override("normal", _sb(TEAL_BG if active else PANEL, TEAL_BD if active else LINE2, 8, 7)); return b


func _switch_visual(on: bool) -> Control:
	var p := PanelContainer.new(); p.custom_minimum_size = Vector2(38, 22); p.add_theme_stylebox_override("panel", _sb(TEAL if on else Color("cdd7e2"), TEAL if on else Color("cdd7e2"), 11, 2)); var l := _label("    ●" if on else "●", 15, Color.WHITE); l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; p.add_child(l); return p


func _switch_button(on: bool, callback: Callable) -> Button:
	var b := Button.new(); b.text = "    ●" if on else "●"; b.custom_minimum_size = Vector2(38, 22); b.add_theme_font_size_override("font_size", 14); b.add_theme_color_override("font_color", Color.WHITE); b.add_theme_stylebox_override("normal", _sb(TEAL if on else Color("cdd7e2"), TEAL if on else Color("cdd7e2"), 11, 2)); b.pressed.connect(callback); return b


func _mini_stepper(value: String, dec: Callable, inc: Callable, commit := Callable()) -> Control:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 2); row.add_child(_square_button("−", dec, 28))
	if commit.is_valid():
		var edit := LineEdit.new(); edit.text = value; edit.custom_minimum_size = Vector2(78, 28); edit.alignment = HORIZONTAL_ALIGNMENT_CENTER; edit.add_theme_font_override("font", _mono); edit.add_theme_font_size_override("font_size", 12); edit.add_theme_color_override("font_color", INK); edit.add_theme_color_override("caret_color", TEAL); edit.add_theme_stylebox_override("normal", _sb(PANEL, LINE2, 7, 5)); edit.text_submitted.connect(func(text: String) -> void: commit.call(text)); edit.focus_exited.connect(func() -> void: commit.call(edit.text)); row.add_child(edit)
	else:
		var l := _label(value, 12, INK, false, true); l.custom_minimum_size.x = 58; l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; row.add_child(l)
	row.add_child(_square_button("＋", inc, 28))
	return row


func _format_small(value: float) -> String: return "%d" % roundi(value) if is_equal_approx(value, roundf(value)) else "%.2f" % value
func _kicker(text: String) -> Label: return _label(text, 10, INK3, false, true)
func _chip(text: String, fg: Color, bg: Color, border: Color) -> Control:
	var p := _panel(bg, border, 5, 4); p.add_child(_label(text, 9, fg)); return p
func _dot(color: Color, size: int) -> ColorRect:
	var d := ColorRect.new(); d.color = color; d.custom_minimum_size = Vector2(size, size); d.size_flags_vertical = Control.SIZE_SHRINK_CENTER; return d
func _h_spacer() -> Control: var c := Control.new(); c.size_flags_horizontal = Control.SIZE_EXPAND_FILL; return c
func _v_spacer() -> Control: var c := Control.new(); c.size_flags_vertical = Control.SIZE_EXPAND_FILL; return c
func _v_rule(height: int) -> ColorRect: var c := ColorRect.new(); c.color = LINE2; c.custom_minimum_size = Vector2(1, height); return c
func _h_rule() -> Control: var c := ColorRect.new(); c.color = LINE2; c.custom_minimum_size.y = 1; c.size_flags_horizontal = Control.SIZE_EXPAND_FILL; c.size_flags_vertical = Control.SIZE_SHRINK_CENTER; return c
func _h_line() -> ColorRect: var c := ColorRect.new(); c.color = LINE2; c.custom_minimum_size.y = 1; return c


func _fill_inset(control: Control, margin: int) -> void:
	control.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	control.offset_left = margin
	control.offset_top = margin
	control.offset_right = -margin
	control.offset_bottom = -margin
