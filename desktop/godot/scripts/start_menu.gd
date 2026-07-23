extends Control
## Start Menu v31 — Godot reproduction of docs/design/start_menu_v31.dc.html.
## This layer owns presentation and draft configuration only.  The desktop
## worker currently accepts only `seed` in new_game; unsupported draft fields
## remain visible in the review instead of being silently treated as applied.

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

const STEP_META := [
	["场景与模式", "SCENARIO"], ["世界设置", "WORLD"],
	["国家配置", "COUNTRIES"], ["政府与席位", "GOVERNMENT"],
	["初始政策", "POLICY"], ["检查并开始", "REVIEW"],
]

const SCENARIOS := [
	{"id": "sandbox", "name": "自由沙盒", "desc": "无预设 ShockTape，结果完全由模拟与玩家行为产生", "caps": "无需额外能力", "duration": "开放期限", "reduced": false},
	{"id": "oil", "name": "石油禁运", "desc": "能源产能与进口能力同时受限", "caps": "能源 + 贸易", "duration": "180 天", "reduced": true},
	{"id": "gfc", "name": "全球金融危机", "desc": "信贷供给、需求与生产率受冲击", "caps": "银行体系", "duration": "365 天", "reduced": true},
	{"id": "pandemic", "name": "大流行", "desc": "劳动、生产率、需求、信贷及可选贸易受冲击", "caps": "银行体系", "duration": "365 天", "reduced": true},
	{"id": "disaster", "name": "自然灾害", "desc": "一次性资本损失，加暂时生产率与劳动冲击", "caps": "无需额外能力", "duration": "30 天", "reduced": true},
	{"id": "import", "name": "导入场景", "desc": "读取经校验的 ShockTape JSON", "caps": "由文件声明", "duration": "自定义", "reduced": false},
]

const PROFILES := {
	"symmetric": {"name": "对称基线", "desc": "对称基线，无自动覆盖偏离", "scale": 1.0, "prod": 1.0, "nec": 0.50},
	"advanced": {"name": "发达", "desc": "高生产率经济体 (a ×1.20)", "scale": 1.0, "prod": 1.2, "nec": 0.50},
	"developing": {"name": "发展中", "desc": "账户 ×1.5、生产率 ×0.75", "scale": 1.5, "prod": 0.75, "nec": 0.65},
	"entrepot": {"name": "转口港", "desc": "小型高生产率；开放度未建模", "scale": 0.4, "prod": 1.15, "nec": 0.50, "experimental": true},
	"petrostate": {"name": "资源国", "desc": "暂无石油出口禀赋覆盖", "scale": 0.8, "prod": 0.85, "nec": 0.50, "experimental": true},
	"custom": {"name": "自定义", "desc": "从当前最终值创建并继续覆盖", "scale": 1.0, "prod": 1.0, "nec": 0.50},
}

const COUNTRY_NAMES := ["奥雷利亚", "博尔维亚", "佩特罗尼亚", "卡兰迪亚", "梅里迪", "诺瓦尼亚", "塞拉菲", "图兰"]
const COUNTRY_CODES := ["AUR", "BOL", "PET", "KAL", "MER", "NOV", "SER", "TUR"]
const COUNTRY_COLORS := [Color("0f9d90"), Color("2f6fd0"), Color("7a4fd0"), Color("c17d16"), Color("1f9d63"), Color("d24a34"), Color("3f6db2"), Color("0c8579")]

const SEATS := [
	{"id": "cb", "name": "央行", "color": Color("2f6fd0"), "groups": "monetary · liquidity · fx (24)"},
	{"id": "treasury", "name": "财政部", "color": Color("0f9d90"), "groups": "fiscal · tax · debt (35)"},
	{"id": "regulator", "name": "金融监管", "color": Color("7a4fd0"), "groups": "macropru · structural (28)"},
	{"id": "external", "name": "对外事务", "color": Color("3f6db2"), "groups": "trade · migration (9)"},
	{"id": "energy", "name": "能源", "color": Color("c17d16"), "groups": "operations · structure (6)"},
]

const OCCUPANTS := [
	["human", "人类玩家"], ["null", "固定不动作 (Null)"],
	["heuristic", "启发式 fiscal-v3"], ["rl", "RL 模型 (需 artifact)"],
	["scheduled", "预定脚本"], ["fuzz", "随机探索 (实验室)"],
]

const STRUCT_GROUPS := [
	{"name": "规模", "fields": [["消费品企业", "n_firms_c", "step"], ["资本品企业", "n_firms_k", "step"], ["能源企业", "n_firms_e", "step"], ["银行数", "n_banks", "step"]]},
	{"name": "生产", "fields": [["基础生产率", "a", "step"], ["资本份额", "alpha", "step"], ["TFP 法则", "tfp_law", "select"]]},
	{"name": "金融结构", "fields": [["银行系统", "bank_enabled", "toggle"], ["银行间市场", "interbank", "toggle"], ["政府债券", "bonds", "toggle"], ["资本市场", "capital_market", "toggle"], ["逐企业股票", "per_firm_equity", "toggle"], ["家庭信贷", "household_credit", "toggle"]]},
	{"name": "住房", "fields": [["住房市场", "housing_market_enabled", "toggle"], ["按揭", "mortgage_enabled", "toggle"], ["租赁", "housing_rental_enabled", "toggle"], ["住房建造", "housing_construction_enabled", "toggle"]]},
	{"name": "人口与产业", "fields": [["人口系统", "demographics_enabled", "toggle"], ["必需/奢侈分层", "consumption_strata", "toggle"], ["必需品占比", "necessity_share0", "step"], ["能源部门", "energy_enabled", "toggle"], ["政府", "government", "toggle"], ["国民账户指标", "national_accounts_metrics", "toggle"]]},
]

const POLICY_PREVIEW := {
	"treasury": [
		{"group": "财政立场", "id": "fiscal_stance", "levers": [["政府消费份额", "gov_consumption_share", "number", 0.18, 0.005], ["赤字目标 / GDP", "gov_deficit_target", "percent", 0.03, 0.005], ["福利替代率", "benefit_replacement", "percent", 0.40, 0.02], ["就业保障", "job_guarantee", "bool", false, 1.0]]},
		{"group": "税收与转移", "id": "tax_and_transfers", "levers": [["所得税率", "tax_income_rate", "percent", 0.22, 0.01], ["消费税率", "tax_consumption_rate", "percent", 0.15, 0.01], ["能源补贴率", "energy_subsidy_rate", "percent", 0.08, 0.01]]},
		{"group": "债务管理", "id": "debt_management", "levers": [["债券融资占比", "bond_finance_frac", "percent", 0.60, 0.05], ["债券期限", "bond_maturity", "integer", 20, 1.0]]},
	],
	"cb": [
		{"group": "货币立场", "id": "monetary_stance", "levers": [["货币制度", "monetary_regime", "regime", "taylor", 0], ["手动政策利率", "manual_policy_rate", "percent", 0.035, 0.0025], ["通胀目标", "inflation_target", "percent", 0.02, 0.0025], ["泰勒 φπ", "taylor_phi_pi", "number", 1.5, 0.1]]},
		{"group": "流动性操作", "id": "liquidity_operations", "levers": [["公开市场操作", "omo", "bool", true, 1.0], ["准备金下限", "reserve_floor_frac", "percent", 0.10, 0.005]]},
		{"group": "外汇操作", "id": "fx_operations", "levers": [["汇率制度", "fx_regime", "fx", "float", 0], ["锚定经济体", "peg_anchor", "anchor", "", 0], ["资本管制", "capital_control", "percent", 0.0, 0.05]]},
	],
	"regulator": [{"group": "宏观审慎", "id": "macroprudential", "levers": [["银行杠杆上限", "bank_leverage_cap", "integer", 12, 1.0], ["按揭 LTV 上限", "mortgage_ltv_cap", "percent", 0.85, 0.05], ["家庭信贷上限", "hh_credit_limit", "percent", 0.40, 0.05]]}, {"group": "结构法律", "id": "structural_law", "levers": [["家庭破产", "household_bankruptcy", "bool", true, 1.0], ["银行处置基金", "bank_resolution_fund", "bool", true, 1.0]]}],
	"external": [{"group": "贸易与迁移", "id": "trade_and_migration", "levers": [["关税率", "tariff", "percent", 0.05, 0.01], ["进口配额", "import_quota", "number", 1.0, 0.05], ["移民上限", "immigration_cap", "percent", 0.25, 0.05], ["出口补贴", "export_subsidy", "percent", 0.0, 0.01]]}],
	"energy": [{"group": "能源操作", "id": "energy_operations", "levers": [["能源配给", "energy_rationing", "ration", "market", 0], ["能源限价", "energy_price_cap", "number", 0.0, 0.1], ["国企成本定价", "soe_price_at_cost", "bool", false, 1.0]]}, {"group": "能源结构", "id": "energy_structure", "levers": [["国企 e-firm", "soe_efirm", "bool", false, 1.0]]}],
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
var _research := false
var _settings_open := false
var _scenario := "sandbox"
var _scenario_caps_applied: Dictionary = {}
var _seed := 7
var _duration := "5y"
var _perf_scale := "fast"
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
var _run_mode := "interactive"
var _seat_occupants: Dictionary = {}
var _calendar_open := false
var _policy_country := 0
var _policy_seat := "treasury"
var _policy_filter := "all"
var _policy_search := ""
var _policy_values: Dictionary = {}
var _settings_values: Dictionary = {}
var _launch_progress := 0
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
		_step = clampi(capture_step.to_int(), 1, 6)
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
	_countries = [
		_country_record(0, "advanced"),
		_country_record(1, "developing"),
		_country_record(2, "petrostate"),
	]
	for seat: Dictionary in SEATS:
		_seat_occupants[str(seat["id"])] = "human"


func _country_record(index: int, profile: String = "symmetric") -> Dictionary:
	return {"name": COUNTRY_NAMES[index], "code": COUNTRY_CODES[index],
		"color": COUNTRY_COLORS[index], "profile": profile, "overrides": {}}


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
	var title := _label("宏观\n指挥室", 62, INK, true)
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
	var intro := _label("多经济体宏观政策模拟。你是坐在席位上的决策者——一切修改走提案，一切危机走冲击。引擎是唯一权威。", 15, INK2)
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	intro.custom_minimum_size = Vector2(420, 0)
	brand_top.add_child(intro)
	brand.add_child(brand_top)
	brand.add_child(_v_spacer())
	var build := _label("BUILD   dev · v30 UI · v31 新游戏规格\nENGINE  World + ControlledSimulationSession + ControllerService\n© Republic Simulation Works · 单机本地", 11, INK3, false, true)
	build.add_theme_constant_override("line_spacing", 7)
	brand.add_child(build)
	var menu_wrap := VBoxContainer.new()
	menu_wrap.custom_minimum_size = Vector2(480, 0)
	row.add_child(menu_wrap)
	menu_wrap.add_child(_v_spacer())
	var menu := VBoxContainer.new()
	menu.add_theme_constant_override("separation", 14)
	menu_wrap.add_child(menu)
	menu.add_child(_continue_card())
	var choices := VBoxContainer.new()
	choices.add_theme_constant_override("separation", 9)
	choices.add_child(_home_choice("＋", "新建模拟", "六步配置世界、国家与席位", func() -> void:
		_screen = "wizard"; _step = 1; _render(), true))
	choices.add_child(_home_choice("⤓", "载入存档", "3 个存档 · 最近 今天 14:22", func() -> void:
		_screen = "wizard"; _step = 1; _render()))
	choices.add_child(_home_choice("⚙", "设置", "显示、语言、游戏流、存档", func() -> void:
		_settings_open = true; _render()))
	choices.add_child(_home_choice("⏻", "退出", "关闭指挥室", func() -> void:
		get_tree().quit()))
	menu.add_child(choices)
	menu_wrap.add_child(_v_spacer())


func _continue_card() -> Control:
	var panel := _panel(PAPER, LINE, 14, 18)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 11)
	panel.add_child(col)
	var kicker := HBoxContainer.new()
	kicker.add_theme_constant_override("separation", 8)
	kicker.add_child(_dot(GREEN, 7))
	kicker.add_child(_label("最近自动存档", 10, Color("68788b"), false, true))
	col.add_child(kicker)
	col.add_child(_label("奥雷利亚 · 自由沙盒", 17, INK, true))
	var detail := _label("模拟日期 第 3 年 · 第 2 季 · 第 35 天\n3 国 · seed 7 · 交互模式 · 存档于 今天 14:22\nschema v31 · 兼容", 12, INK2, false, true)
	detail.add_theme_constant_override("line_spacing", 4)
	col.add_child(detail)
	var cont := _button("继续游戏 →", func() -> void:
		continue_requested.emit(); hide(), true, 15)
	cont.custom_minimum_size = Vector2(0, 43)
	col.add_child(cont)
	return panel


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
		4: _step_government(content)
		5: _step_policy(content)
		_: _step_review(content)
	if _step != 6:
		body.add_child(_summary_panel())
	shell.add_child(_wizard_footer())


func _wizard_header() -> Control:
	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(0, 56)
	panel.add_theme_stylebox_override("panel", _sb(PAPER, LINE2, 0, 10))
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 14)
	panel.add_child(row)
	row.add_child(_button("← 首页", func() -> void:
		_screen = "home"; _render(), false, 13, true))
	row.add_child(_v_rule(26))
	row.add_child(_label("新建模拟", 15, INK, true))
	row.add_child(_label("NEW SIMULATION", 11, INK3, false, true))
	row.add_child(_h_spacer())
	var modes := PanelContainer.new(); modes.add_theme_stylebox_override("panel", _sb(PANEL2, LINE, 9, 2))
	var mh := HBoxContainer.new(); mh.add_theme_constant_override("separation", 2); modes.add_child(mh)
	for spec: Array in [[false, "普通"], [true, "研究"]]:
		var chosen: bool = spec[0]
		var b := _button(str(spec[1]), func() -> void:
			_research = chosen; _render(), false, 12, _research != chosen)
		if _research == chosen:
			b.add_theme_stylebox_override("normal", _sb(PAPER, PAPER, 7, 5))
		mh.add_child(b)
	row.add_child(modes)
	row.add_child(_button("⚙", func() -> void:
		_settings_open = true; _render(), false, 15))
	return panel


func _step_navigation() -> Control:
	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(224, 0)
	panel.add_theme_stylebox_override("panel", _sb(PANEL, LINE2, 0, 14))
	var col := VBoxContainer.new(); col.add_theme_constant_override("separation", 5); panel.add_child(col)
	var km := MarginContainer.new(); km.add_theme_constant_override("margin_left", 8); km.add_theme_constant_override("margin_bottom", 6)
	km.add_child(_label("配置流程", 10, INK3, false, true)); col.add_child(km)
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
	var nt := _label("配置分五类真相：结构、初始政策、世界、席位、客户端设置——互不混淆。", 11, INK2)
	nt.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; note.add_child(nt); col.add_child(note)
	return panel


func _page_heading(parent: VBoxContainer, title: String, subtitle: String) -> void:
	parent.add_child(_label(title, 20, INK, true))
	var sub := _label(subtitle, 13, Color("68788b")); sub.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var sm := MarginContainer.new(); sm.add_theme_constant_override("margin_top", 3); sm.add_theme_constant_override("margin_bottom", 17); sm.add_child(sub); parent.add_child(sm)


func _step_scenario(parent: VBoxContainer) -> void:
	parent.custom_minimum_size.x = 720
	_page_heading(parent, "场景与基础模型", "选择外生冲击场景与校准模型。历史场景均为约化模型，选择后需确认其建议启用的能力。")
	parent.add_child(_kicker("SCENARIO · 场景"))
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
		if bool(item["reduced"]): title_row.add_child(_chip("约化 · 未校准", AMBER, AMBER_BG, AMBER_BD))
		words.add_child(title_row); words.add_child(_label(str(item["desc"]), 11, Color("68788b"))); row.add_child(words)
		var meta := VBoxContainer.new(); meta.add_child(_label(str(item["caps"]), 11, INK2, false, true)); meta.add_child(_label(str(item["duration"]), 10, MUTED, false, true)); row.add_child(meta)
		list.add_child(b)
	if _scenario not in ["sandbox", "import"] and not bool(_scenario_caps_applied.get(_scenario, false)):
		var requirement := _panel(AMBER_BG, AMBER_BD, 11, 12)
		var requirement_col := VBoxContainer.new()
		requirement_col.add_theme_constant_override("separation", 8)
		requirement.add_child(requirement_col)
		requirement_col.add_child(_label("⚠  「%s」建议启用对应模型能力" % _scenario_name(), 12, Color("7a5111"), true))
		var capability_note := "能源部门 + World 贸易层" if _scenario == "oil" else "银行体系"
		requirement_col.add_child(_label(capability_note + " · 场景不会静默修改国家结构", 11, Color("7a5111")))
		requirement_col.add_child(_button("应用建议能力", func() -> void:
			_scenario_caps_applied[_scenario] = true
			_render(), true, 12))
		var requirement_margin := MarginContainer.new()
		requirement_margin.add_theme_constant_override("margin_top", 12)
		requirement_margin.add_child(requirement)
		parent.add_child(requirement_margin)
	var sp := MarginContainer.new(); sp.add_theme_constant_override("margin_top", 20); sp.add_child(_kicker("BASE MODEL · 基础模型")); parent.add_child(sp)
	var models := HBoxContainer.new(); models.add_theme_constant_override("separation", 9); parent.add_child(models)
	models.add_child(_model_card("稳定 v124", "当前完整模型与推荐校准", true))
	models.add_child(_model_card("研究分支", "允许实验性 Profile 与 Occupant", _research))


func _model_card(title: String, subtitle: String, active: bool) -> Control:
	var p := _panel(TEAL_BG if active else PAPER, TEAL_BD if active else LINE, 11, 12)
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := VBoxContainer.new(); v.add_child(_label(title, 13, INK, true)); v.add_child(_label(subtitle, 11, Color("68788b"))); p.add_child(v)
	return p


func _step_world(parent: VBoxContainer) -> void:
	parent.custom_minimum_size.x = 760
	_page_heading(parent, "世界设置", "世界统一的规模、日历与跨境机制。单国世界将禁用需要交易对手的能力。")
	var top := GridContainer.new(); top.columns = 2; top.add_theme_constant_override("h_separation", 12); top.add_theme_constant_override("v_separation", 12); parent.add_child(top)
	top.add_child(_counter_card("国家数量", "1 – 8 · 默认 3", str(_countries.size()), _remove_country, _add_country))
	top.add_child(_seed_card())
	top.add_child(_duration_card())
	top.add_child(_performance_card())
	var cross_m := MarginContainer.new(); cross_m.add_theme_constant_override("margin_top", 18); cross_m.add_theme_constant_override("margin_bottom", 8); cross_m.add_child(_kicker("CROSS-BORDER · 跨境机制")); parent.add_child(cross_m)
	var toggles := GridContainer.new(); toggles.columns = 2; toggles.add_theme_constant_override("h_separation", 9); toggles.add_theme_constant_override("v_separation", 9); parent.add_child(toggles)
	toggles.add_child(_toggle_card("国际贸易", "World 贸易与汇率传导", _trade, func() -> void: _trade = not _trade; _render()))
	toggles.add_child(_toggle_card("跨境资本", "资本流动与外部结算", _capital, func() -> void: _capital = not _capital; _render()))
	toggles.add_child(_toggle_card("人口迁移", "工资驱动的跨境迁移", _migration, func() -> void: _migration = not _migration; _render()))
	toggles.add_child(_toggle_card("跨境汇款", "依赖迁移机制", _migration, func() -> void: _migration = not _migration; _render()))
	var adv := _button(("▼" if _cross_open else "▶") + "  跨境高级参数    10 项 · 高级", func() -> void: _cross_open = not _cross_open; _render(), false, 12, true)
	var am := MarginContainer.new(); am.add_theme_constant_override("margin_top", 12); am.add_child(adv); parent.add_child(am)
	if _cross_open:
		var ap := _panel(PANEL, LINE2, 11, 8); parent.add_child(ap)
		var grid := GridContainer.new(); grid.columns = 2; grid.add_theme_constant_override("h_separation", 6); grid.add_theme_constant_override("v_separation", 6); ap.add_child(grid)
		for field: Array in [["汇率调整", "fx_lambda", "0.05"], ["汇率摩擦", "fx_friction", "0.03"], ["贸易汇率上限", "fx_trade_cap", "0.15"], ["资本流动强度", "capital_mobility", "1.00"], ["资本调整", "capital_adjust", "0.20"], ["迁移速度", "migration_rate", "0.02"], ["迁移份额上限", "migration_max_share", "0.25"], ["汇回份额", "remittance_share", "0.20"], ["工资平滑", "wage_smoothing", "0.02"], ["挂钩初始储备", "peg_reserves0", "5,000"]]:
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
	v.add_child(_label("随机种子", 12, INK2)); v.add_child(_label("0 – 2,147,483,647 · 可复现", 10, MUTED, false, true))
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 8)
	var edit := LineEdit.new(); edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL; edit.text = str(_seed); edit.add_theme_font_override("font", _mono); edit.add_theme_font_size_override("font_size", 15); edit.add_theme_stylebox_override("normal", _sb(PANEL, LINE, 9, 8)); edit.text_submitted.connect(func(text: String) -> void: _apply_seed(text)); edit.focus_exited.connect(func() -> void: _apply_seed(edit.text)); row.add_child(edit)
	row.add_child(_square_button("🎲", func() -> void: _seed = randi_range(0, 2147483647); _render(), 38)); row.add_child(_square_button("⧉", func() -> void: DisplayServer.clipboard_set(str(_seed)), 38)); v.add_child(row)
	return p


func _apply_seed(text: String) -> void:
	if text.is_valid_int(): _seed = clampi(text.to_int(), 0, 2147483647)
	_render()


func _duration_card() -> Control:
	var p := _panel(PAPER, LINE, 12, 14); p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := VBoxContainer.new(); v.add_theme_constant_override("separation", 9); p.add_child(v); v.add_child(_label("运行时长", 12, INK2))
	var flow := HFlowContainer.new(); flow.add_theme_constant_override("h_separation", 6); flow.add_theme_constant_override("v_separation", 6)
	for d: Array in [["1y", "1 年"], ["5y", "5 年"], ["10y", "10 年"], ["inf", "无限"], ["custom", "自定义"]]:
		var id := str(d[0]); flow.add_child(_select_chip(str(d[1]), _duration == id, func() -> void: _duration = id; _render()))
	v.add_child(flow); v.add_child(_label("自然日历 · 5 年共 1,825 天" if _duration == "5y" else "自然日历 · 每年 365 天", 10, INK3, false, true)); return p


func _performance_card() -> Control:
	var p := _panel(PAPER, LINE, 12, 14); p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var v := VBoxContainer.new(); v.add_theme_constant_override("separation", 9); p.add_child(v); v.add_child(_label("性能规模", 12, INK2))
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	for s: Array in [["fast", "快速"], ["standard", "标准"], ["custom", "自定义"]]:
		var id := str(s[0]); var chip := _select_chip(str(s[1]), _perf_scale == id, func() -> void: _perf_scale = id; _render()); chip.size_flags_horizontal = Control.SIZE_EXPAND_FILL; row.add_child(chip)
	v.add_child(row); v.add_child(_label("80 户 · 12+4+2 企业 · 2 银行（当前原型）" if _perf_scale == "fast" else "200 户 · 30+10+4 企业 · 4 银行", 10, INK3, false, true)); return p


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
	var lh := HBoxContainer.new(); lh.add_child(_kicker("国家 · %d" % _countries.size())); lh.add_child(_h_spacer()); lh.add_child(_button("＋ 新增", _add_country, false, 11)); left.add_child(lh)
	for i in _countries.size(): left.add_child(_country_card(i))
	var note := _label("按稳定 country ID 维护引用；删除会列出受影响的 peg / 制裁 / 场景目标。", 10, MUTED); note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; left.add_child(note)
	var editor := VBoxContainer.new(); editor.size_flags_horizontal = Control.SIZE_EXPAND_FILL; editor.add_theme_constant_override("separation", 10); row.add_child(editor)
	var c: Dictionary = _countries[_selected_country]
	var identity := HBoxContainer.new(); identity.add_theme_constant_override("separation", 12)
	var flag := PanelContainer.new(); flag.custom_minimum_size = Vector2(44, 44); flag.add_theme_stylebox_override("panel", _sb(c["color"], c["color"], 11, 0)); var fc := CenterContainer.new(); flag.add_child(fc); fc.add_child(_label(str(c["code"]), 11, Color.WHITE, true, true)); identity.add_child(flag)
	var idwords := VBoxContainer.new(); idwords.size_flags_horizontal = Control.SIZE_EXPAND_FILL; idwords.add_child(_label(str(c["name"]), 19, INK, true)); idwords.add_child(_label("%s · 高生产率核心经济体" % str(c["code"]), 11, INK3, false, true)); identity.add_child(idwords)
	identity.add_child(_button("应用到所有国家", func() -> void: _apply_profile_all(), false, 11))
	identity.add_child(_button("恢复 Profile", func() -> void: c["overrides"] = {}; _render(), false, 11))
	if _countries.size() > 1:
		identity.add_child(_button("删除", _delete_selected_country, false, 11))
	editor.add_child(identity)
	editor.add_child(_kicker("COUNTRY PROFILE · 创世覆盖（非政策）"))
	var profiles := GridContainer.new(); profiles.columns = 3; profiles.add_theme_constant_override("h_separation", 8); profiles.add_theme_constant_override("v_separation", 8); editor.add_child(profiles)
	for pid in PROFILES.keys(): profiles.add_child(_profile_card(str(pid)))
	var stats := _panel(PANEL, LINE2, 9, 9); var statrow := HBoxContainer.new(); statrow.add_theme_constant_override("separation", 16); stats.add_child(statrow); statrow.add_child(_label("最终家庭数  %d" % _households(c), 11, INK2)); statrow.add_child(_label("初始人口  %d（派生）" % roundi(_households(c) * 2.3), 11, INK2)); statrow.add_child(_label("企业数  18", 11, INK2)); editor.add_child(stats)
	editor.add_child(_kicker("结构能力"))
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
		head.add_child(_label("◆ 玩家", 9, TEAL))
	col.add_child(head)
	var meta := HBoxContainer.new(); meta.add_child(_label(str(PROFILES[str(c["profile"])]["name"]), 10, INK2, false, true)); meta.add_child(_h_spacer()); meta.add_child(_label("%d 户" % _households(c), 9, MUTED, false, true)); col.add_child(meta)
	return b


func _profile_card(pid: String) -> Control:
	var c: Dictionary = _countries[_selected_country]; var p: Dictionary = PROFILES[pid]; var active := str(c["profile"]) == pid
	var b := Button.new(); b.custom_minimum_size = Vector2(176, 74); b.size_flags_horizontal = Control.SIZE_EXPAND_FILL; b.add_theme_stylebox_override("normal", _sb(TEAL_BG if active else PAPER, TEAL_BD if active else LINE, 10, 9)); b.pressed.connect(func() -> void: c["profile"] = pid; c["overrides"] = {}; _render())
	var v := VBoxContainer.new(); v.mouse_filter = Control.MOUSE_FILTER_IGNORE; v.add_child(_label(str(p["name"]) + (" · 实验性" if bool(p.get("experimental", false)) else ""), 13, INK, true)); var d := _label(str(p["desc"]), 10, Color("68788b")); d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; d.max_lines_visible = 2; d.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS; v.add_child(d); _fill_inset(v, 10); b.add_child(v); return b


func _structure_field(country: Dictionary, field: Array) -> Control:
	var key := str(field[1]); var kind := str(field[2]); var overrides: Dictionary = country["overrides"]; var changed := overrides.has(key)
	var p := _panel(BLUE_BG if changed else PAPER, BLUE_BD if changed else LINE2, 9, 8); p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 9); p.add_child(row)
	var text := VBoxContainer.new(); text.size_flags_horizontal = Control.SIZE_EXPAND_FILL; text.add_child(_label(str(field[0]), 12, INK)); text.add_child(_label(key, 9, MUTED, false, true)); row.add_child(text)
	if kind == "toggle":
		var value := bool(overrides.get(key, true)); row.add_child(_switch_button(value, func() -> void: overrides[key] = not value; _render()))
	elif kind == "select":
		var option := OptionButton.new(); option.add_item("漂移"); option.add_item("学习"); option.add_item("无"); option.add_theme_font_size_override("font_size", 11); row.add_child(option)
	else:
		var value := float(overrides.get(key, 1.0 if key == "a" else 12.0)); row.add_child(_mini_stepper(_format_small(value), func() -> void: overrides[key] = maxf(0.0, value - 1.0); _render(), func() -> void: overrides[key] = value + 1.0; _render()))
	return p


func _add_country() -> void:
	if _countries.size() >= 8: return
	_countries.append(_country_record(_countries.size())); _render()


func _remove_country() -> void:
	if _countries.size() <= 1: return
	_countries.pop_back(); _selected_country = mini(_selected_country, _countries.size() - 1); _player_country = mini(_player_country, _countries.size() - 1); _render()


func _delete_selected_country() -> void:
	if _countries.size() <= 1: return
	_countries.remove_at(_selected_country); _selected_country = 0; _player_country = mini(_player_country, _countries.size() - 1); _render()


func _apply_profile_all() -> void:
	var profile := str(_countries[_selected_country]["profile"])
	for c: Dictionary in _countries: c["profile"] = profile; c["overrides"] = {}
	_render()


func _households(country: Dictionary) -> int:
	var base := 80 if _perf_scale == "fast" else 200
	return roundi(base * float(PROFILES[str(country["profile"])]["scale"]))


func _step_government(parent: VBoxContainer) -> void:
	parent.custom_minimum_size.x = 820
	_page_heading(parent, "政府与 Controller 席位", "选择玩家国家与你持有的席位。其他国家默认无 Controller——政策冻结在开局状态，而不是 AI。")
	parent.add_child(_kicker("玩家国家")); var countries := HFlowContainer.new(); countries.add_theme_constant_override("h_separation", 8); countries.add_theme_constant_override("v_separation", 8); parent.add_child(countries)
	for i in _countries.size():
		var c: Dictionary = _countries[i]; var idx := i; var b := _select_chip("■  %s  %s" % [str(c["code"]), str(c["name"])], i == _player_country, func() -> void: _player_country = idx; _render()); b.add_theme_color_override("font_color", c["color"] if i == _player_country else INK2); countries.add_child(b)
	var sm := MarginContainer.new(); sm.add_theme_constant_override("margin_top", 18); sm.add_theme_constant_override("margin_bottom", 8); sm.add_child(_kicker("%s · 五个政策席位" % str(_countries[_player_country]["name"]))); parent.add_child(sm)
	var seatlist := VBoxContainer.new(); seatlist.add_theme_constant_override("separation", 8); parent.add_child(seatlist)
	for seat: Dictionary in SEATS: seatlist.add_child(_seat_row(seat))
	var note := _label("你持有 %d / 5 个人类席位；其余为自动 Occupant。RL / 预定 / 随机需研究模式。" % _human_seat_count(), 11, INK3); var nm := MarginContainer.new(); nm.add_theme_constant_override("margin_top", 6); nm.add_child(note); parent.add_child(nm)
	if _countries.size() > 1:
		var om := MarginContainer.new(); om.add_theme_constant_override("margin_top", 18); om.add_theme_constant_override("margin_bottom", 8); om.add_child(_kicker("其他国家")); parent.add_child(om)
		var others := GridContainer.new(); others.columns = 2; others.add_theme_constant_override("h_separation", 9); others.add_theme_constant_override("v_separation", 9); parent.add_child(others)
		for i in _countries.size():
			if i != _player_country:
				others.add_child(_frozen_country(_countries[i]))
	var rm := MarginContainer.new(); rm.add_theme_constant_override("margin_top", 18); rm.add_theme_constant_override("margin_bottom", 8); rm.add_child(_kicker("运行方式")); parent.add_child(rm)
	var modes := HBoxContainer.new(); modes.add_theme_constant_override("separation", 9); parent.add_child(modes)
	for mode: Array in [["interactive", "交互", "人类会议无限等待（默认）"], ["realtime", "实时", "墙钟倒计时，超时不动作"], ["batch", "批量", "需全部自动 Occupant"], ["replay", "回放", "由存档 / 事件带决定"]]:
		var id := str(mode[0]); var locked := id == "replay" or (id == "batch" and _human_seat_count() > 0); var p := _mode_card(str(mode[1]), str(mode[2]), _run_mode == id, locked, func() -> void: _run_mode = id; _render()); modes.add_child(p)
	var cal := _button(("▼" if _calendar_open else "▶") + "  制度决策日历    普通模式为自然语言摘要", func() -> void: _calendar_open = not _calendar_open; _render(), false, 12, true); var cm := MarginContainer.new(); cm.add_theme_constant_override("margin_top", 12); cm.add_child(cal); parent.add_child(cm)
	if _calendar_open:
		var cp := _panel(PANEL, LINE2, 11, 11); var cv := VBoxContainer.new(); cv.add_theme_constant_override("separation", 7); cp.add_child(cv)
		for line: Array in [["货币立场 · 流动性操作", "约每 1.5 月", "45 天"], ["财政 · 债务 · 宏观审慎 · 贸易迁移 · 外汇 · 能源操作", "每季度", "91 天"], ["税收转移 · 结构法律 · 能源结构", "每年", "365 天"]]:
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
	for occ: Array in OCCUPANTS:
		if not _research and str(occ[0]) in ["rl", "scheduled", "fuzz"]: continue
		option.add_item(str(occ[1])); option.set_item_metadata(option.item_count - 1, occ[0]); if str(_seat_occupants.get(str(seat["id"]), "human")) == str(occ[0]): option.select(option.item_count - 1)
	var sid := str(seat["id"]); option.item_selected.connect(func(index: int) -> void: _seat_occupants[sid] = str(option.get_item_metadata(index)); _render()); row.add_child(option); return p


func _frozen_country(country: Dictionary) -> Control:
	var p := _panel(PANEL, LINE, 10, 10); p.size_flags_horizontal = Control.SIZE_EXPAND_FILL; var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 10); p.add_child(row); row.add_child(_dot(country["color"], 9)); var v := VBoxContainer.new(); v.add_child(_label(str(country["name"]), 13, INK, true)); v.add_child(_label("无 Controller · 政策自开局起保持不变", 10, INK2)); row.add_child(v); return p


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
	_page_heading(parent, "初始政策", "按 国家 → 席位 → 决策组 组织，全部继承模型预设；最终实现将由 Policy Registry schema 生成。仅改动项进入差异摘要。")
	var selectors := HBoxContainer.new(); selectors.add_theme_constant_override("separation", 8); parent.add_child(selectors)
	var country_opt := OptionButton.new()
	for i in _countries.size():
		country_opt.add_item(str(_countries[i]["name"]) + (" · 玩家" if i == _player_country else ""))
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
	var search := LineEdit.new(); search.size_flags_horizontal = Control.SIZE_EXPAND_FILL; search.text = _policy_search; search.placeholder_text = "搜索中文名 / 内部名…"; search.add_theme_stylebox_override("normal", _sb(PANEL, LINE, 8, 7)); search.text_submitted.connect(func(text: String) -> void: _policy_search = text.strip_edges(); _render()); filters.add_child(search)
	for fil: Array in [["all", "全部"], ["changed", "只看已改"], ["mine", "本席位"]]:
		var id := str(fil[0])
		filters.add_child(_select_chip(str(fil[1]), _policy_filter == id, func() -> void: _policy_filter = id; _render()))
	var found := 0
	for raw: Dictionary in POLICY_PREVIEW.get(_policy_seat, []):
		var group := raw; var visible_levers: Array = []
		for lev: Array in group["levers"]:
			var key := _policy_key(str(lev[1])); var changed := _policy_values.has(key)
			if _policy_filter == "changed" and not changed: continue
			if not _policy_search.is_empty() and not str(lev[0]).contains(_policy_search) and not str(lev[1]).contains(_policy_search): continue
			if str(lev[1]) == "manual_policy_rate" and str(_policy_value("monetary_regime", "taylor")) != "manual": continue
			if str(lev[1]) == "peg_anchor" and str(_policy_value("fx_regime", "float")) != "peg": continue
			visible_levers.append(lev)
		if visible_levers.is_empty(): continue
		found += visible_levers.size(); var gh := HBoxContainer.new(); gh.add_child(_label(str(group["group"]), 12, Color("3a4956"), true)); gh.add_child(_label(str(group["id"]), 9, MUTED, false, true)); gh.add_child(_h_rule()); parent.add_child(gh)
		var lv := VBoxContainer.new(); lv.add_theme_constant_override("separation", 7); var lm := MarginContainer.new(); lm.add_theme_constant_override("margin_bottom", 8); lm.add_child(lv); parent.add_child(lm)
		for lev: Array in visible_levers:
			lv.add_child(_policy_row(lev))
	if found == 0:
		var empty := _label("无匹配杠杆——调整搜索或筛选。", 13, MUTED); empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; var em := MarginContainer.new(); em.add_theme_constant_override("margin_top", 40); em.add_child(empty); parent.add_child(em)


func _policy_row(lever: Array) -> Control:
	var name := str(lever[0]); var id := str(lever[1]); var kind := str(lever[2]); var base: Variant = lever[3]; var step := float(lever[4]); var key := _policy_key(id); var changed := _policy_values.has(key); var value: Variant = _policy_values.get(key, base)
	var p := _panel(BLUE_BG if changed else PAPER, BLUE_BD if changed else LINE, 10, 9); var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 12); p.add_child(row)
	var words := VBoxContainer.new(); words.size_flags_horizontal = Control.SIZE_EXPAND_FILL; var nh := HBoxContainer.new(); nh.add_child(_label(name, 13, INK)); nh.add_child(_chip("本国覆盖" if changed else "继承预设", BLUE if changed else INK2, BLUE_BG if changed else Color("eef2f7"), Color(0, 0, 0, 0))); words.add_child(nh); words.add_child(_label(id, 9, MUTED, false, true)); row.add_child(words)
	if kind == "bool": row.add_child(_switch_button(bool(value), func() -> void: _policy_values[key] = not bool(value); _render()))
	elif kind in ["regime", "fx", "ration"]:
		var opts: Array = [["exogenous", "外生"], ["taylor", "泰勒"], ["manual", "手动"]] if kind == "regime" else ([["float", "浮动"], ["peg", "盯住"]] if kind == "fx" else [["market", "市场"], ["household_first", "居民优先"], ["industry_first", "产业优先"]])
		var seg := HBoxContainer.new(); seg.add_theme_constant_override("separation", 2)
		for opt: Array in opts:
			var ov := str(opt[0])
			seg.add_child(_select_chip(str(opt[1]), str(value) == ov, func() -> void: _policy_values[key] = ov; _render()))
		row.add_child(seg)
	elif kind == "anchor":
		var op := OptionButton.new(); op.add_item("— 选锚（浮动国）—")
		op.set_item_metadata(0, "")
		for i in _countries.size():
			if i != _policy_country:
				op.add_item(str(_countries[i]["name"]))
				op.set_item_metadata(op.item_count - 1, i)
		op.item_selected.connect(func(index: int) -> void:
			_policy_values[key] = op.get_item_metadata(index)
			_render())
		row.add_child(op)
	else:
		row.add_child(_mini_stepper(_policy_format(kind, value), func() -> void: _policy_values[key] = maxf(0.0, float(value) - step); _render(), func() -> void: _policy_values[key] = float(value) + step; _render()))
	return p


func _policy_key(lever: String) -> String: return "%d.%s.%s" % [_policy_country, _policy_seat, lever]
func _policy_value(lever: String, fallback: Variant) -> Variant: return _policy_values.get(_policy_key(lever), fallback)
func _policy_format(kind: String, value: Variant) -> String:
	if kind == "percent": return "%.1f%%" % (float(value) * 100.0)
	if kind == "integer": return "%d" % roundi(float(value))
	return "%.3f" % float(value)


func _step_review(parent: VBoxContainer) -> void:
	parent.custom_minimum_size.x = 900
	_page_heading(parent, "建国与运行清单", "最终值按解析顺序解释来源。请复核后启动。")
	var banners := HBoxContainer.new(); banners.add_theme_constant_override("separation", 9); parent.add_child(banners)
	banners.add_child(_validation_card("✓", "0 错误", "阻断启动", GREEN, GREEN_BG, GREEN_BD)); banners.add_child(_validation_card("⚠", "1 警告", "允许启动", AMBER, AMBER_BG, AMBER_BD)); banners.add_child(_validation_card("ℹ", "1 信息", "仅提示", BLUE, BLUE_BG, BLUE_BD))
	var wm := MarginContainer.new(); wm.add_theme_constant_override("margin_top", 12); wm.add_theme_constant_override("margin_bottom", 12); var warning := _panel(AMBER_BG, AMBER_BD, 9, 9); var wr := HBoxContainer.new(); wr.add_theme_constant_override("separation", 9); warning.add_child(wr); wr.add_child(_label("⚠", 13, AMBER)); var wt := _label("当前桌面 new_game 协议只消费 seed；国家、场景、席位和初始政策已进入清单，但暂不伪装为已注入引擎。", 12, Color("7a5111")); wt.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; wt.size_flags_horizontal = Control.SIZE_EXPAND_FILL; wr.add_child(wt); wr.add_child(_label("PROTOCOL", 9, MUTED, false, true)); wm.add_child(warning); parent.add_child(wm)
	var manifest := GridContainer.new(); manifest.columns = 2; manifest.add_theme_constant_override("h_separation", 12); manifest.add_theme_constant_override("v_separation", 12); parent.add_child(manifest)
	var scenario := _scenario_name()
	var country_rows: Array = []
	for c: Dictionary in _countries:
		country_rows.append([str(c["name"]), "%s · %d 户" % [str(PROFILES[str(c["profile"])]["name"]), _households(c)]])
	manifest.add_child(_manifest_card("WORLD · 世界", BLUE, [["国家数", str(_countries.size())], ["日历", "每年 365 天"], ["时长", _duration_label()], ["seed", str(_seed)], ["跨境", _cross_label()]]))
	manifest.add_child(_manifest_card("COUNTRIES · 国家", TEAL, country_rows))
	manifest.add_child(_manifest_card("GOVERNMENT · 政府", PURPLE, [["玩家国家", str(_countries[_player_country]["name"])], ["人类席位", "%d / 5" % _human_seat_count()], ["会议模式", _run_mode], ["他国", "%d 国政策冻结" % (_countries.size() - 1)]]))
	manifest.add_child(_manifest_card("POLICY · 初始政策", AMBER, [["相对预设", "%d 项改动" % _policy_values.size()], ["注入状态", "等待新游戏协议"], ["货币制度", str(_policy_value("monetary_regime", "taylor"))], ["汇率制度", str(_policy_value("fx_regime", "float"))]]))
	manifest.add_child(_manifest_card("SCENARIO · 场景", RED, [["场景", scenario], ["校准", "约化 / 原型" if _scenario != "sandbox" else "—"], ["ShockTape", "等待新游戏协议"]]))
	manifest.add_child(_manifest_card("REPRODUCIBILITY · 可复现", Color("3f6db2"), [["模型版本", "Config.v124"], ["schema", "v31"], ["base_seed", "%d → +i×1e6" % _seed], ["协议", "desktop v2 · seed only"]]))


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
	var head := HBoxContainer.new(); head.add_child(_kicker("本局摘要")); head.add_child(_h_spacer()); head.add_child(_dot(AMBER, 6)); head.add_child(_label("协议待接", 10, AMBER)); col.add_child(head)
	col.add_child(_summary_section("场景", [["场景", _scenario_name()], ["模型", "稳定 v124"]])); col.add_child(_summary_section("世界", [["国家", str(_countries.size())], ["时长", _duration_label()], ["seed", str(_seed)], ["跨境", _cross_label()]]))
	var cr: Array = []
	for c: Dictionary in _countries.slice(0, 4):
		cr.append([str(c["code"]), str(PROFILES[str(c["profile"])]["name"])])
	col.add_child(_summary_section("国家", cr))
	col.add_child(_summary_section("政府", [["玩家国", str(_countries[_player_country]["name"])], ["人类席位", "%d/5" % _human_seat_count()], ["模式", _run_mode]]))
	col.add_child(_summary_section("政策", [["改动", "%d 项" % _policy_values.size()]]))
	col.add_child(_v_spacer())
	var protocol := _label("当前 worker 仅接收 seed\n其余配置等待 new_game v31", 10, AMBER, false, true); protocol.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; col.add_child(protocol); return p


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
	var p := PanelContainer.new(); p.custom_minimum_size = Vector2(0, 60); p.add_theme_stylebox_override("panel", _sb(PAPER, LINE2, 0, 12)); var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 12); p.add_child(row); row.add_child(_button("返回", _go_back, false, 13)); row.add_child(_h_spacer())
	var dots := HBoxContainer.new(); dots.add_theme_constant_override("separation", 6)
	for i in 6:
		var bar := ColorRect.new()
		bar.color = TEAL if i + 1 == _step else (TEAL_BD if i + 1 < _step else LINE)
		bar.custom_minimum_size = Vector2(22 if i + 1 == _step else 6, 6)
		dots.add_child(bar)
	row.add_child(dots)
	row.add_child(_label("第 %d / 6 步" % _step, 11, INK3, false, true))
	row.add_child(_h_spacer())
	if _step == 6: row.add_child(_button("▶  启动模拟", _begin_launch, true, 14))
	else: row.add_child(_button("下一步 →", func() -> void: _step += 1; _render(), true, 14))
	return p


func _go_back() -> void:
	if _step > 1:
		_step -= 1
	else:
		_screen = "home"
	_render()


func _begin_launch() -> void:
	_screen = "launching"; _launch_progress = 0; _launch_timer.start(); _render()


func _advance_launch() -> void:
	_launch_progress += 1
	if _launch_progress >= 4:
		_launch_timer.stop()
		launch_requested.emit({"seed": _seed, "draft": _draft_manifest()})
		hide()
	else: _render()


func _build_launch(parent: Control) -> void:
	var center := CenterContainer.new(); center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); parent.add_child(center); var col := VBoxContainer.new(); col.custom_minimum_size.x = 440; col.add_theme_constant_override("separation", 10); center.add_child(col); var h := HBoxContainer.new(); h.alignment = BoxContainer.ALIGNMENT_CENTER; h.add_theme_constant_override("separation", 12); h.add_child(_label("◌", 25, TEAL, true)); h.add_child(_label("正在建立世界", 19, INK, true)); var hm := MarginContainer.new(); hm.add_theme_constant_override("margin_bottom", 20); hm.add_child(h); col.add_child(hm)
	var defs: Array = [["创建 %d 个经济体" % _countries.size(), "%d 户" % _total_households()], ["绑定场景 ShockTape", _scenario_name()], ["分配政策席位", "%d 人类" % _human_seat_count()], ["派生 RNG 子流", "seed %d" % _seed]]
	for i in defs.size(): var done := i < _launch_progress; var active := i == _launch_progress; var p := _panel(PAPER, TEAL_BD if active else LINE2, 10, 10); p.modulate.a = 1.0 if done or active else 0.5; var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 12); p.add_child(row); var mark := _chip("✓" if done else ("·" if active else ""), Color.WHITE, GREEN if done else (TEAL if active else LINE), Color(0, 0, 0, 0)); row.add_child(mark); var text := _label(str(defs[i][0]), 13, INK); text.size_flags_horizontal = Control.SIZE_EXPAND_FILL; row.add_child(text); row.add_child(_label(str(defs[i][1]), 11, MUTED, false, true)); col.add_child(p)


func _draft_manifest() -> Dictionary:
	return {"scenario": _scenario, "duration": _duration, "performance_scale": _perf_scale,
		"world": {"trade": _trade, "capital": _capital, "migration": _migration},
		"countries": _countries.duplicate(true), "player_country": _player_country,
		"run_mode": _run_mode, "seats": _seat_occupants.duplicate(true),
		"initial_policy_overrides": _policy_values.duplicate(true)}


func _build_settings(parent: Control) -> void:
	var shade := ColorRect.new(); shade.color = Color(0.086, 0.137, 0.204, 0.34); shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); parent.add_child(shade); var center := CenterContainer.new(); center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); shade.add_child(center); var panel := _panel(PAPER, LINE, 16, 0); panel.custom_minimum_size = Vector2(880, 650); center.add_child(panel); var shell := VBoxContainer.new(); panel.add_child(shell)
	var headp := MarginContainer.new(); headp.add_theme_constant_override("margin_left", 20); headp.add_theme_constant_override("margin_right", 20); headp.add_theme_constant_override("margin_top", 14); headp.add_theme_constant_override("margin_bottom", 14); var head := HBoxContainer.new(); head.add_theme_constant_override("separation", 10); headp.add_child(head); head.add_child(_label("设置", 16, INK, true)); head.add_child(_label("客户端偏好 · 不写入经济 Config", 11, INK3, false, true)); head.add_child(_h_spacer()); head.add_child(_square_button("×", func() -> void: _settings_open = false; _render(), 30)); shell.add_child(headp); shell.add_child(_h_line())
	var bodym := MarginContainer.new(); bodym.size_flags_vertical = Control.SIZE_EXPAND_FILL; bodym.add_theme_constant_override("margin_left", 20); bodym.add_theme_constant_override("margin_right", 20); bodym.add_theme_constant_override("margin_top", 18); bodym.add_theme_constant_override("margin_bottom", 18); var grid := GridContainer.new(); grid.columns = 2; grid.add_theme_constant_override("h_separation", 16); grid.add_theme_constant_override("v_separation", 16); bodym.add_child(grid); shell.add_child(bodym)
	for group: Array in [["显示", [["全屏", "toggle", false], ["UI 缩放", "value", "100%"], ["界面密度", "value", "舒适"]]], ["语言与数字", [["语言", "value", "简体中文"], ["数字缩写", "toggle", true]]], ["可访问性", [["色觉安全色板", "toggle", false], ["减少动效", "toggle", false], ["高对比度", "toggle", true]]], ["游戏流", [["默认交互模式", "value", "交互"], ["实时决策时限", "value", "30 s"], ["开局暂停", "toggle", true]]], ["存档", [["自动存档", "toggle", true], ["保留份数", "value", "10"]]], ["开发者", [["上帝视角（真值）", "toggle", false], ["显示内部字段名", "toggle", true], ["音频", "value", "待实现"]]]]: grid.add_child(_settings_group(str(group[0]), group[1]))
	shell.add_child(_h_line()); var footm := MarginContainer.new(); footm.add_theme_constant_override("margin_left", 20); footm.add_theme_constant_override("margin_right", 20); footm.add_theme_constant_override("margin_top", 12); footm.add_theme_constant_override("margin_bottom", 12); var foot := HBoxContainer.new(); foot.add_child(_label("⟳ 分辨率 / 语言更改需要重启", 10, AMBER, false, true)); foot.add_child(_h_spacer()); foot.add_child(_button("还原默认", func() -> void: pass, false, 12)); foot.add_child(_button("应用", func() -> void: _settings_open = false; _render(), true, 12)); footm.add_child(foot); shell.add_child(footm)


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
			return str(scenario["name"])
	return "自由沙盒"


func _duration_label() -> String: return {"1y": "1 年", "5y": "5 年", "10y": "10 年", "inf": "无限", "custom": "自定义"}.get(_duration, _duration)
func _cross_label() -> String: return " · ".join(["贸易" if _trade else "", "资本" if _capital else "", "迁移" if _migration else ""].filter(func(x: String) -> bool: return not x.is_empty()))
func _total_households() -> int:
	var total := 0
	for country: Dictionary in _countries:
		total += _households(country)
	return total


func _sb(bg: Color, border: Color, radius: int, padding: int) -> StyleBoxFlat:
	var s := StyleBoxFlat.new(); s.bg_color = bg; s.border_color = border
	for side in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]: s.set_border_width(side, 1); s.set_corner_radius(side, radius); s.set_content_margin(side, padding)
	return s


func _panel(bg: Color, border: Color, radius: int, padding: int) -> PanelContainer:
	var p := PanelContainer.new(); p.add_theme_stylebox_override("panel", _sb(bg, border, radius, padding)); return p


func _label(text: String, size: int, color: Color, bold := false, mono := false) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_override("font", _mono if mono else _sans)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	if bold:
		l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.15))
	return l


func _button(text: String, callback: Callable, primary := false, size := 12, flat := false) -> Button:
	var b := Button.new(); b.text = text; b.add_theme_font_override("font", _sans); b.add_theme_font_size_override("font_size", size); b.add_theme_color_override("font_color", Color.WHITE if primary else INK2); b.add_theme_stylebox_override("normal", _sb(TEAL if primary else (Color(0, 0, 0, 0) if flat else PANEL2), TEAL_DK if primary else (Color(0, 0, 0, 0) if flat else LINE), 9, 8)); b.add_theme_stylebox_override("hover", _sb(TEAL_DK if primary else PAPER, TEAL_DK if primary else TEAL, 9, 7)); b.pressed.connect(callback); return b


func _square_button(text: String, callback: Callable, side: int) -> Button:
	var b := _button(text, callback, false, 14); b.custom_minimum_size = Vector2(side, side); return b


func _select_chip(text: String, active: bool, callback: Callable) -> Button:
	var b := _button(text, callback, false, 12); b.add_theme_color_override("font_color", TEAL_DK if active else INK2); b.add_theme_stylebox_override("normal", _sb(TEAL_BG if active else PANEL, TEAL_BD if active else LINE2, 8, 7)); return b


func _switch_visual(on: bool) -> Control:
	var p := PanelContainer.new(); p.custom_minimum_size = Vector2(38, 22); p.add_theme_stylebox_override("panel", _sb(TEAL if on else Color("cdd7e2"), TEAL if on else Color("cdd7e2"), 11, 2)); var l := _label("    ●" if on else "●", 15, Color.WHITE); l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; p.add_child(l); return p


func _switch_button(on: bool, callback: Callable) -> Button:
	var b := Button.new(); b.text = "    ●" if on else "●"; b.custom_minimum_size = Vector2(38, 22); b.add_theme_font_size_override("font_size", 14); b.add_theme_color_override("font_color", Color.WHITE); b.add_theme_stylebox_override("normal", _sb(TEAL if on else Color("cdd7e2"), TEAL if on else Color("cdd7e2"), 11, 2)); b.pressed.connect(callback); return b


func _mini_stepper(value: String, dec: Callable, inc: Callable) -> Control:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 2); row.add_child(_square_button("−", dec, 28)); var l := _label(value, 12, INK, false, true); l.custom_minimum_size.x = 58; l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; row.add_child(l); row.add_child(_square_button("＋", inc, 28)); return row


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
