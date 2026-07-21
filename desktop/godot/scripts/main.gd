extends Control
## 宏观指挥室 v29.1 — 设计模版:docs/design/policy_room_v29_light.dc.html。
## 前端零经济逻辑;三国耦合世界,玩家持 0 号经济体全部 5 个席位(102 旋钮全落地)。

const SimulationClientScript = preload("res://scripts/simulation_client.gd")

const SPEEDS := [1, 5, 15, 60]

# ---- 设计系统(设计稿原色) ----
const GROUND := Color("e9edf2")
const PANEL := Color("fbfcfd")
const PANEL2 := Color("f1f4f8")
const PANEL3 := Color("f5f7fb")
const LINE := Color("dde4ec")
const LINE2 := Color("d3dce6")
const INK := Color("16232f")
const INK_BODY := Color("2a3948")
const INK2 := Color("5e6f81")
const INK3 := Color("71808f")
const TEAL := Color("0f9d90")
const TEAL_BG := Color("e2f4f1")
const TEAL_BD := Color("9ad9d0")
const TEAL_DK := Color("0c8579")
const BLUE := Color("2f6fd0")
const BLUE_BG := Color("e6effb")
const BLUE_BD := Color("b6d1f2")
const AMBER := Color("c17d16")
const AMBER_BG := Color("fbf0dc")
const AMBER_BD := Color("ecd3a0")
const RED := Color("d24a34")
const RED_BG := Color("fdeee9")
const RED_BD := Color("f0bcae")
const PURPLE := Color("7a4fd0")
const GREEN := Color("1f9d63")

const ECON_COLORS := [Color("0f9d90"), Color("c17d16"), Color("2f6fd0")]

# 公报磁贴(诚实信道:发布日历 + 时滞 + 缺失显式化)
const TILE_SPEC := [
	{"id": "real_output", "label": "实际产出 · GDP", "color": TEAL, "bad_up": false},
	{"id": "unemployment_rate", "label": "失业率", "color": AMBER, "bad_up": true},
	{"id": "inflation", "label": "通胀(每tick)", "color": PURPLE, "bad_up": true},
	{"id": "price_index", "label": "物价指数", "color": BLUE, "bad_up": true},
	{"id": "policy_rate", "label": "政策利率", "color": TEAL, "bad_up": false},
	{"id": "gov_deficit_to_gdp", "label": "赤字 / GDP", "color": AMBER, "bad_up": true},
	{"id": "bank_reserves_total", "label": "银行准备金", "color": GREEN, "bad_up": false},
	{"id": "poverty_rate", "label": "贫困率", "color": PURPLE, "bad_up": true},
]

const SEAT_LIST := [
	{"id": "treasury", "name": "财政部", "tag": "财政 · fiscal"},
	{"id": "central_bank", "name": "央行", "tag": "货币 · monetary"},
	{"id": "regulator", "name": "监管", "tag": "审慎 · prudential"},
	{"id": "external_affairs", "name": "外交贸易", "tag": "对外 · external"},
	{"id": "energy", "name": "能源", "tag": "能源 · energy"},
]

const GROUP_CN := {
	"fiscal_stance": "财政立场", "tax_and_transfers": "税收与转移",
	"debt_management": "债务管理", "monetary_stance": "货币立场",
	"liquidity_operations": "流动性操作", "fx_operations": "外汇操作",
	"macroprudential": "宏观审慎", "structural_law": "结构性法规",
	"trade_and_migration": "贸易与移民", "energy_operations": "能源操作",
	"energy_structure": "能源结构",
}

const LEVER_CN := {
	# 债务管理
	"bond_coupon": "国债票息率", "bond_finance_frac": "赤字债券融资比例",
	"bond_maturity": "国债期限",
	# 能源操作 / 结构
	"energy_price_cap": "能源限价", "energy_rationing": "能源配给规则",
	"soe_price_at_cost": "国有能企成本定价", "spr_flow_cap": "战略储备吞吐上限",
	"spr_target_units": "战略储备目标规模", "soe_efirm": "能源企业国有化",
	# 财政立场
	"benefit_income_floor": "最低收入保障线", "benefit_replacement": "失业救济替代率",
	"deficit_u_cap": "逆周期赤字上限", "deficit_u_ref": "赤字规则失业基准",
	"fiscal_uses_national_accounts_gdp": "财政采用国民账户GDP口径",
	"gov_consumption_share": "政府消费占比", "gov_deficit_target": "财政赤字目标",
	"gov_investment_share": "公共投资占比", "housing_permits": "年度建房许可额度",
	"jg_public_works_share": "以工代赈工程比例", "jg_wage_ratio": "就业保障工资比率",
	"job_guarantee": "就业保障计划", "pension_replacement": "养老金替代率",
	# 外汇操作
	"capital_control": "资本管制强度",
	"external_interest_settlement_fraction": "对外利息结算比例",
	"fx_regime": "汇率制度", "peg_anchor": "联系汇率锚国",
	"peg_reserve_scale": "联汇储备规模",
	# 流动性操作
	"lolr": "最后贷款人机制", "omo": "公开市场操作",
	"omo_drain_frac": "公开市场回笼比例", "omo_index_deposits": "准备金目标盯住存款",
	"omo_reserve_target": "准备金目标水平", "reserve_floor_frac": "法定准备金率下限",
	# 宏观审慎
	"bank_bond_duration_limit": "银行债券久期限额",
	"bank_capital_constraint": "银行资本放贷约束",
	"bank_exposure_limit": "大额风险暴露限额", "bank_leverage_cap": "银行杠杆上限",
	"bank_migrate_on_failure": "倒闭银行存款迁移", "bank_min_capital": "银行最低资本",
	"bank_target_capital_ratio": "银行目标资本充足率",
	"deposit_rate_floor": "存款利率下限",
	"firm_credit_min_dscr": "企业信贷最低偿债覆盖率",
	"hh_credit_limit": "家庭信贷额度上限", "kappa": "信贷扩张乘数 κ",
	"margin_ltv": "融资保证金成数", "margin_max": "融资融券规模上限",
	"mortgage_dsti_cap": "按揭偿债收入比上限", "mortgage_ltv_cap": "按揭成数上限",
	"mortgage_min_capital_ratio": "按揭业务最低资本比率",
	"mortgage_risk_weight": "按揭风险权重",
	"mortgage_stress_rate_addon": "按揭压力测试加点",
	"mortgage_underwriting": "按揭审慎审贷",
	"regulatory_firm_capital_haircut": "企业资本抵押折扣",
	"regulatory_firm_inventory_haircut": "企业存货抵押折扣",
	# 货币立场
	"cb_core_inflation": "盯住核心通胀", "cb_log_inflation": "对数通胀口径",
	"cb_uses_fixed_basket_cpi": "固定篮子CPI口径",
	"infl_ema_lambda": "通胀平滑系数 λ", "inflation_target": "通胀目标",
	"manual_policy_rate": "手动政策利率", "monetary_regime": "货币政策规则",
	"r_max": "政策利率上限", "r_neutral": "中性利率",
	"rate_inertia": "利率平滑惯性", "taylor_phi_pi": "泰勒规则通胀系数 φπ",
	"taylor_phi_u": "泰勒规则失业系数 φu", "u_natural": "自然失业率参数",
	# 结构性法规
	"bank_resolution_fund": "银行处置基金", "bankrupt_persist": "破产记录留存",
	"household_bankruptcy": "个人破产制度",
	"mortgage_arrears_floor": "按揭欠款处置门槛",
	"mortgage_foreclosure_ltv": "法拍触发成数",
	"rental_eviction_arrears": "欠租驱逐门槛",
	"unified_bank_rwa": "统一风险加权资产框架",
	# 税收与转移
	"energy_cap_compensation": "能源限价补偿", "energy_subsidy_rate": "能源补贴率",
	"energy_subsidy_threshold": "能源补贴门槛",
	"housing_in_wealth_tax": "住房纳入财富税", "housing_property_tax": "房产税率",
	"housing_transfer_tax": "房产交易税率", "income_allowance": "所得税起征点",
	"land_fee_share": "土地出让金比例", "land_fee_stock_elasticity": "土地费存量弹性",
	"min_wage": "最低工资", "tax_consumption_rate": "消费税率",
	"tax_energy_rate": "能源税率", "tax_energy_windfall": "能源暴利税率",
	"tax_income_rate": "个人所得税率", "tax_luxury_rate": "奢侈品税率",
	"tax_necessity_rate": "必需品税率", "tax_profit_rate": "企业利润税率",
	"tax_wealth_rate": "财富税率", "wealth_allowance": "财富税起征点",
	# 贸易与移民
	"emigration_cap": "移出人口限额", "export_subsidy": "出口补贴率",
	"guest_worker_return": "客工返回率", "immigration_cap": "移入人口限额",
	"import_quota": "进口配额", "outward_remittance_tax": "汇出汇款税率",
	"remittance_tax": "汇入汇款税率", "sanctions_imposed_on": "对外制裁名单",
	"tariff": "进口关税税率",
}


# 指标全景:9 组 × 6 键(上帝视角,逐 tick 真值;键名与后端 records 一致)
# fmt: pct=份额%, pt=每tick利率%, idx=指数, num=水平量
const PANEL_GROUPS := [
	{"name": "实体经济", "color": TEAL, "items": [
		["real_output", "实际产出", "num"], ["real_consumption", "实际消费", "num"],
		["aggregate_capital", "资本存量", "num"], ["investment_spending", "投资支出", "num"],
		["inventory_to_sales", "库存/销售", "idx"], ["production_realization_rate", "生产实现率", "pct"]]},
	{"name": "劳动力", "color": AMBER, "items": [
		["unemployment_rate", "失业率", "pct"], ["u_natural", "自然失业率", "pct"],
		["underemployed_share", "不充分就业", "pct"], ["vacancies_unfilled", "未填补岗位", "num"],
		["avg_wage", "平均工资", "num"], ["wage_inflation", "工资通胀", "pt"]]},
	{"name": "价格与货币", "color": PURPLE, "items": [
		["price_index", "物价指数", "idx"], ["inflation", "通胀", "pt"],
		["avg_markup", "平均加成", "idx"], ["policy_rate", "政策利率", "pt"],
		["total_money", "广义货币", "num"], ["real_wage", "实际工资", "idx"]]},
	{"name": "财政", "color": BLUE, "items": [
		["gov_debt", "政府债务", "num"], ["gov_deficit", "财政赤字", "num"],
		["tax_total", "税收总额", "num"], ["gov_spending", "政府支出", "num"],
		["benefit_paid", "转移支付", "num"], ["gov_debt_to_gdp", "债务/GDP", "pct"]]},
	{"name": "银行与信贷", "color": TEAL_DK, "items": [
		["total_credit", "信贷总量", "num"], ["bank_capital", "银行资本", "num"],
		["bank_deposit_total", "存款总额", "num"], ["writeoffs", "坏账核销", "num"],
		["total_debt_service_ratio", "偿债比率", "pct"], ["interbank_rate", "同业利率", "pt"]]},
	{"name": "资本市场", "color": Color("4a6fa5"), "items": [
		["equity_market_cap", "股票市值", "num"], ["tobin_q_mean", "托宾 Q", "idx"],
		["equity_wealth_share", "股权财富占比", "pct"], ["equity_turnover", "换手率", "idx"],
		["equity_ownership_gini", "持股基尼", "idx"], ["hh_wealth_gini_incl_equity", "财富基尼(含股)", "idx"]]},
	{"name": "能源", "color": Color("b0641f"), "items": [
		["energy_price", "能源价格", "idx"], ["energy_produced", "能源产量", "num"],
		["energy_used", "能源消耗", "num"], ["energy_stock_total", "能源库存", "num"],
		["energy_cost_share", "能源成本占比", "pct"], ["spr_stock", "战略储备", "num"]]},
	{"name": "分配与福利", "color": Color("8a5fc0"), "items": [
		["poverty_rate", "贫困率", "pct"], ["income_gini", "收入基尼", "idx"],
		["hh_wealth_gini", "财富基尼", "idx"], ["wage_p90_p10_ratio", "工资 P90/P10", "idx"],
		["welfare_log", "对数福利", "idx"], ["savings_rate", "储蓄率", "pct"]]},
	{"name": "人口与企业", "color": Color("2a8a68"), "items": [
		["population_alive", "总人口", "num"], ["working_age_share", "劳龄占比", "pct"],
		["avg_household_size", "户均规模", "idx"], ["births", "出生 / tick", "num"],
		["deaths", "死亡 / tick", "num"], ["firm_count_c", "消费品企业数", "num"]]},
]

const WORLD_COMPARE := [
	["real_output", "实际产出", "num"], ["unemployment_rate", "失业率", "pct"],
	["inflation", "通胀", "pt"], ["price_index", "物价指数", "idx"],
	["avg_wage", "平均工资", "num"], ["policy_rate", "政策利率", "pt"],
]

const RANK_METRICS := [
	["real_output", "GDP", "num", false], ["unemployment_rate", "失业率", "pct", true],
	["inflation", "通胀", "pt", true], ["avg_wage", "工资", "num", false],
]

var _client
var _outbox: Array = []
var _snapshot: Dictionary = {}
var _schemas: Dictionary = {}          # seat -> schema dict
var _lever_info: Dictionary = {}       # lever -> lever dict (all seats merged)
var _lever_group: Dictionary = {}      # lever -> decision_group
var _active_seat := "treasury"
var _edits: Dictionary = {}            # lever -> 本地编辑值(未入篮)
var _cart: Array = []                  # [{lever, from, to, value, group}]
var _perm_cache: Dictionary = {}       # lever -> last permitted action(会议闭合时展示用)
var _release_hist: Dictionary = {}     # sid -> [{v, at}]
var _playing := false
var _speed := 5
var _god := false
var _mode := "interactive"
var _tab := "focus"
var _rank_by := "real_output"
var _filter_mine := false
var _last_toasted := ""
var _capture_path := ""
var _capture_ticks := 0
var _capture_target := -1
var _confirm: Dictionary = {}
var _demo_crisis := false
var _crisis_dismissed := ""

var _sans: SystemFont
var _mono: SystemFont
var _n: Dictionary = {}


func _ready() -> void:
	_sans = SystemFont.new()
	_sans.font_names = PackedStringArray([
		"Hiragino Sans GB", "STHeiti", "Arial Unicode MS", "Helvetica Neue"])
	_mono = SystemFont.new()
	_mono.font_names = PackedStringArray(["Menlo", "Monaco"])
	_mono.fallbacks = [_sans]
	_build_theme()
	_build_ui()
	_client = SimulationClientScript.new()
	add_child(_client)
	_client.connected.connect(_on_connected)
	_client.disconnected.connect(func() -> void:
		_set_text("conn", "已断开 · 重连中"))
	_client.response_received.connect(_on_response)
	_client.request_failed.connect(_on_request_failed)
	var timer := Timer.new()
	timer.wait_time = 1.0
	timer.timeout.connect(_on_play_tick)
	add_child(timer)
	timer.start()
	_capture_path = OS.get_environment("MACRO_SIM_CAPTURE_PATH")
	var pre := OS.get_environment("MACRO_SIM_CAPTURE_TICKS")
	if pre.is_valid_int():
		_capture_ticks = pre.to_int()
	var pre_tab := OS.get_environment("MACRO_SIM_CAPTURE_TAB")
	if not pre_tab.is_empty():
		_tab = pre_tab
	var pre_seat := OS.get_environment("MACRO_SIM_CAPTURE_SEAT")
	if not pre_seat.is_empty():
		_active_seat = pre_seat


# ================= 通信 =================
func _send(command: Dictionary) -> void:
	_outbox.append(command)
	_pump()


func _pump() -> void:
	if _client == null or _client.busy or _outbox.is_empty():
		return
	_client.send_command(_outbox.pop_front())


func _on_connected() -> void:
	_set_text("conn", "引擎在线")
	_send({"command": "hello"})
	_send({"command": "get_schema"})


func _on_response(response: Dictionary) -> void:
	var payload: Dictionary = response.get("snapshot", {})
	if payload.has("seats") and payload.has("levers"):
		_schemas = payload.get("seats", {})
		_index_schema()
	else:
		_snapshot = payload
		_ingest_releases()
		_cache_permitted()
		var verdict: Variant = payload.get("last_verdict")
		if verdict is Dictionary and not (verdict as Dictionary).is_empty():
			_show_verdict(verdict)
		if _playing and _awaiting() and _mode != "realtime":
			_playing = false
	_render()
	if not _capture_path.is_empty() and _outbox.is_empty() and not _client.busy:
		var now := int(_snapshot.get("tick", 0))
		if _capture_target < 0:
			_capture_target = now + _capture_ticks
		if _awaiting() and now < _capture_target:
			for ctx: Dictionary in _contexts():
				_outbox.append({"command": "resolve_context",
					"context_id": str(ctx.get("context_id")), "actions": []})
		elif now < _capture_target:
			_outbox.append({"command": "advance",
				"ticks": mini(_capture_target - now, 100)})
		else:
			var path := _capture_path
			_capture_path = ""
			_capture(path)
	_pump()


func _on_request_failed(message: String) -> void:
	_show_verdict({"status": "rejected", "reason_code": message,
		"decision_id": "err:%d" % Time.get_ticks_msec()})
	_pump()
	if not _capture_path.is_empty() and _outbox.is_empty() and not _client.busy:
		var path := _capture_path
		_capture_path = ""
		_capture(path)


func _capture(path: String) -> void:
	await get_tree().create_timer(0.35).timeout
	var image := get_viewport().get_texture().get_image()
	image.save_png(path)
	get_tree().quit(0)


func _on_play_tick() -> void:
	if not _playing or _demo_crisis:
		return
	if _awaiting():
		if _mode == "realtime" and not _emergency():
			for ctx: Dictionary in _contexts():
				_send({"command": "resolve_context",
					"context_id": str(ctx.get("context_id")), "actions": []})
		return
	_send({"command": "advance", "ticks": _speed})


# ================= 数据 =================
func _index_schema() -> void:
	_lever_info.clear()
	_lever_group.clear()
	for seat: String in _schemas.keys():
		for lever: Dictionary in _schemas[seat].get("levers", []):
			var name := str(lever.get("name"))
			_lever_info[name] = lever
			_lever_group[name] = str(lever.get("decision_group", ""))


func _seat_groups(seat: String) -> Dictionary:
	var out: Dictionary = {}
	for lever: Dictionary in _schemas.get(seat, {}).get("levers", []):
		var g := str(lever.get("decision_group", "其他"))
		if not out.has(g):
			out[g] = []
		out[g].append(lever)
	return out


func _ingest_releases() -> void:
	for rel: Dictionary in _snapshot.get("observation", {}).get("releases", []):
		if rel.get("value") == null:
			continue
		var sid := str(rel.get("series_id"))
		var at := int(rel.get("released_at_tick", -1))
		if not _release_hist.has(sid):
			_release_hist[sid] = []
		var arr: Array = _release_hist[sid]
		if not arr.is_empty() and int(arr[-1]["at"]) >= at:
			continue
		arr.append({"v": float(rel.get("value")), "at": at})
		if arr.size() > 24:
			arr.pop_front()


func _cache_permitted() -> void:
	for ctx: Dictionary in _contexts():
		for item: Dictionary in ctx.get("permitted_actions", []):
			_perm_cache[str(item.get("lever"))] = item


func _awaiting() -> bool:
	return bool(_snapshot.get("awaiting_human", false))


func _contexts() -> Array:
	return _snapshot.get("contexts", [])


func _context_for_group(group: String) -> Dictionary:
	for ctx: Dictionary in _contexts():
		if str(ctx.get("decision_group", "")) == group:
			return ctx
	return {}


func _emergency_context() -> Dictionary:
	for ctx: Dictionary in _contexts():
		if bool(ctx.get("emergency", false)):
			return ctx
	return {}


func _emergency() -> bool:
	return not _emergency_context().is_empty() or _demo_crisis


func _releases_by_id() -> Dictionary:
	var out: Dictionary = {}
	for rel: Dictionary in _snapshot.get("observation", {}).get("releases", []):
		out[str(rel.get("series_id"))] = rel
	return out


func _world() -> Dictionary:
	return _snapshot.get("world", {})


func _cn(lever_name: String) -> String:
	return str(LEVER_CN.get(lever_name, lever_name))


func _country_name(i: int) -> String:
	var countries: Array = _world().get("countries", [])
	if i >= 0 and i < countries.size():
		return str((countries[i] as Dictionary).get("name", "经济体%d" % i))
	return "经济体%d" % i


# ================= 主题/样式 =================
func _build_theme() -> void:
	var t := Theme.new()
	t.default_font = _sans
	t.default_font_size = 13
	t.set_color("font_color", "Label", INK_BODY)
	t.set_color("font_color", "Button", INK_BODY)
	t.set_color("font_color", "CheckBox", Color("586a7b"))
	t.set_color("font_color", "CheckButton", INK_BODY)
	t.set_stylebox("normal", "Button", _sb(Color("eef2f7"), Color("cdd7e2"), 8, 7))
	t.set_stylebox("hover", "Button", _sb(Color("eef2f7"), TEAL, 8, 7))
	t.set_stylebox("pressed", "Button", _sb(TEAL_BG, TEAL_BD, 8, 7))
	t.set_stylebox("disabled", "Button", _sb(Color("eef1f5"), LINE, 8, 7))
	t.set_color("font_disabled_color", "Button", Color("849098"))
	t.set_stylebox("panel", "PanelContainer", _sb(PANEL, LINE, 13, 12))
	theme = t


func _sb(bg: Color, border: Color, radius: int, margin: int) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(1)
	s.set_corner_radius_all(radius)
	s.set_content_margin_all(margin)
	return s


func _lbl(text: String, size: int, color: Color, mono := false) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	if mono:
		l.add_theme_font_override("font", _mono)
	return l


func _chip(text: String, fg: Color, bg: Color, border: Color, size := 11) -> PanelContainer:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", _sb(bg, border, 20, 4))
	p.add_child(_lbl(text, size, fg))
	return p


func _dot(color: Color, dsize := 7.0) -> Control:
	var c := Control.new()
	c.custom_minimum_size = Vector2(dsize, dsize)
	c.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	c.draw.connect(func() -> void:
		c.draw_circle(Vector2(dsize / 2, dsize / 2), dsize / 2, color))
	return c


func _spacer_h() -> Control:
	var c := Control.new()
	c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return c


func _vdiv() -> Control:
	var c := ColorRect.new()
	c.color = LINE
	c.custom_minimum_size = Vector2(1, 30)
	c.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	return c


func _hrule() -> Control:
	var c := ColorRect.new()
	c.color = Color("e6ebf1")
	c.custom_minimum_size = Vector2(0, 1)
	return c


func _btn(text: String, cb: Callable, primary := false) -> Button:
	var b := Button.new()
	b.text = text
	b.pressed.connect(cb)
	if primary:
		b.add_theme_stylebox_override("normal", _sb(TEAL_BG, Color("59b7a8"), 8, 7))
		b.add_theme_color_override("font_color", TEAL_DK)
	return b


func _set_text(key: String, text: String) -> void:
	if _n.has(key) and is_instance_valid(_n[key]):
		(_n[key] as Label).text = text


func _fmt_val(kind: String, v: float) -> String:
	match kind:
		"pct":
			return "%.1f%%" % (v * 100.0)
		"pt":
			return "%.2f%%/t" % (v * 100.0)
		"idx":
			return "%.3f" % v if absf(v) < 10.0 else "%.2f" % v
		_:
			if absf(v) >= 100000.0:
				return "%.0fk" % (v / 1000.0)
			if absf(v) >= 1000.0:
				return "%.1fk" % (v / 1000.0)
			if absf(v) >= 100.0:
				return "%.0f" % v
			return "%.1f" % v if absf(v) >= 1.0 else "%.3f" % v


func _fmt_series(sid: String, v: float) -> String:
	match sid:
		"unemployment_rate", "gov_deficit_to_gdp", "poverty_rate":
			return "%.1f%%" % (v * 100.0)
		"inflation", "policy_rate":
			return "%.2f%%/t" % (v * 100.0)
		"price_index":
			return "%.3f" % v
		_:
			return _fmt_val("num", v)


func _cal_str(t: int) -> String:
	return "第 %d 年 · 第 %d 季 · 第 %d 天" % [
		t / 365 + 1, (t % 365) / 91 + 1, (t % 365) % 91 + 1]


# ================= 布局 =================
func _build_ui() -> void:
	var bgr := ColorRect.new()
	bgr.color = GROUND
	bgr.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(bgr)
	var shell := VBoxContainer.new()
	shell.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shell.offset_left = 14
	shell.offset_top = 12
	shell.offset_right = -14
	shell.offset_bottom = -12
	shell.add_theme_constant_override("separation", 10)
	add_child(shell)
	_build_header(shell)
	var tiles := HBoxContainer.new()
	tiles.add_theme_constant_override("separation", 9)
	shell.add_child(tiles)
	_n["tiles"] = tiles
	_build_main(shell)
	_build_overlays()


func _build_header(shell: VBoxContainer) -> void:
	var hp := PanelContainer.new()
	hp.add_theme_stylebox_override("panel", _sb(PANEL, Color("dbe2ea"), 13, 10))
	shell.add_child(hp)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 14)
	hp.add_child(h)
	var tbox := HBoxContainer.new()
	tbox.add_theme_constant_override("separation", 9)
	h.add_child(tbox)
	tbox.add_child(_lbl("宏观指挥室", 17, INK))
	tbox.add_child(_lbl("MACRO COMMAND · v29", 11, Color("68788b"), true))
	var op := PanelContainer.new()
	op.add_theme_stylebox_override("panel", _sb(TEAL_BG, TEAL_BD, 20, 5))
	var online := HBoxContainer.new()
	online.add_theme_constant_override("separation", 6)
	op.add_child(online)
	online.add_child(_dot(TEAL))
	var conn := _lbl("连接中…", 12, TEAL)
	_n["conn"] = conn
	online.add_child(conn)
	h.add_child(op)
	h.add_child(_vdiv())
	var clock := VBoxContainer.new()
	clock.add_theme_constant_override("separation", 1)
	var cal := _lbl("—", 15, INK)
	_n["cal"] = cal
	clock.add_child(cal)
	var tickl := _lbl("t = 0", 11, Color("68788b"), true)
	_n["tick"] = tickl
	clock.add_child(tickl)
	h.add_child(clock)
	var waitp := PanelContainer.new()
	waitp.add_theme_stylebox_override("panel", _sb(AMBER_BG, AMBER_BD, 20, 5))
	var wbx := HBoxContainer.new()
	wbx.add_theme_constant_override("separation", 7)
	waitp.add_child(wbx)
	wbx.add_child(_dot(AMBER))
	wbx.add_child(_lbl("等待决策", 12, AMBER))
	_n["awaitchip"] = waitp
	h.add_child(waitp)
	h.add_child(_spacer_h())
	var modes := HBoxContainer.new()
	modes.add_theme_constant_override("separation", 2)
	for m: Array in [["interactive", "交互"], ["realtime", "实时"]]:
		var mb := Button.new()
		mb.text = m[1]
		var mid: String = m[0]
		mb.pressed.connect(func() -> void:
			_mode = mid
			_render())
		_n["mode_" + mid] = mb
		modes.add_child(mb)
	h.add_child(modes)
	var god := CheckBox.new()
	god.text = "上帝模式"
	god.toggled.connect(func(v: bool) -> void:
		_god = v
		_render())
	h.add_child(god)
	h.add_child(_vdiv())
	h.add_child(_btn("步进", func() -> void:
		if _awaiting():
			_show_hint("本届会议未闭合,推进被暂停:请「提交提案」或「本次不动」;紧急会议在红色面板里处置。切到「实时」模式可自动通过非紧急会议。")
			_render()
		else:
			_send({"command": "advance", "ticks": 1})))
	var play := _btn("播放", _toggle_play, true)
	_n["play"] = play
	h.add_child(play)
	var speeds := HBoxContainer.new()
	speeds.add_theme_constant_override("separation", 2)
	for s: int in SPEEDS:
		var sbn := Button.new()
		sbn.text = "%d×" % s
		sbn.add_theme_font_override("font", _mono)
		sbn.add_theme_font_size_override("font_size", 12)
		var chosen := s
		sbn.pressed.connect(func() -> void:
			_speed = chosen
			_render())
		_n["speed_%d" % s] = sbn
		speeds.add_child(sbn)
	h.add_child(speeds)


func _toggle_play() -> void:
	_playing = not _playing
	if _playing and _awaiting() and _mode != "realtime":
		_show_hint("播放已就绪,但本届会议未闭合:先「提交提案」或「本次不动」,或切「实时」模式自动通过。")
	_render()


func _build_main(shell: VBoxContainer) -> void:
	var main := HBoxContainer.new()
	main.size_flags_vertical = Control.SIZE_EXPAND_FILL
	main.add_theme_constant_override("separation", 10)
	shell.add_child(main)
	var wbp := PanelContainer.new()
	wbp.custom_minimum_size = Vector2(430, 0)
	wbp.add_theme_stylebox_override("panel", _sb(PANEL, LINE, 13, 0))
	main.add_child(wbp)
	var wb := VBoxContainer.new()
	wbp.add_child(wb)
	_build_workbench(wb)
	var center := VBoxContainer.new()
	center.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	center.add_theme_constant_override("separation", 10)
	main.add_child(center)
	_build_center(center)
	var tlp := PanelContainer.new()
	tlp.custom_minimum_size = Vector2(346, 0)
	tlp.add_theme_stylebox_override("panel", _sb(PANEL, LINE, 13, 0))
	main.add_child(tlp)
	var tl := VBoxContainer.new()
	tlp.add_child(tl)
	_build_timeline(tl)


func _build_workbench(wb: VBoxContainer) -> void:
	var hp := MarginContainer.new()
	hp.add_theme_constant_override("margin_left", 13)
	hp.add_theme_constant_override("margin_right", 13)
	hp.add_theme_constant_override("margin_top", 12)
	hp.add_theme_constant_override("margin_bottom", 10)
	wb.add_child(hp)
	var head := VBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	hp.add_child(head)
	head.add_child(_lbl("SEAT · 席位工作台(玩家持全部席位)", 10, INK3, true))
	var chips := HBoxContainer.new()
	chips.add_theme_constant_override("separation", 5)
	for s: Dictionary in SEAT_LIST:
		var b := Button.new()
		b.text = str(s["name"])
		b.add_theme_font_size_override("font_size", 12)
		var sid := str(s["id"])
		b.pressed.connect(func() -> void:
			_active_seat = sid
			_render())
		_n["seat_" + sid] = b
		chips.add_child(b)
	head.add_child(chips)
	var srow := HBoxContainer.new()
	srow.add_theme_constant_override("separation", 8)
	var stitle := _lbl("财政部", 15, INK)
	_n["seat_title"] = stitle
	srow.add_child(stitle)
	var stag := _chip("财政 · fiscal", Color("647585"), Color(0, 0, 0, 0), LINE2)
	_n["seat_tag"] = stag
	srow.add_child(stag)
	srow.add_child(_spacer_h())
	var cap := _lbl("行政容量 —", 10, INK3, true)
	_n["cap"] = cap
	srow.add_child(cap)
	head.add_child(srow)
	wb.add_child(_hrule())
	var mp := MarginContainer.new()
	mp.add_theme_constant_override("margin_left", 13)
	mp.add_theme_constant_override("margin_top", 6)
	mp.add_theme_constant_override("margin_bottom", 2)
	wb.add_child(mp)
	var meet := _lbl("", 11, INK2)
	_n["meeting"] = meet
	mp.add_child(meet)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	wb.add_child(scroll)
	var lv := VBoxContainer.new()
	lv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lv.add_theme_constant_override("separation", 8)
	scroll.add_child(lv)
	_n["levers"] = lv
	var cf := PanelContainer.new()
	cf.add_theme_stylebox_override("panel", _sb(PANEL3, Color("e6ebf1"), 0, 11))
	wb.add_child(cf)
	var cart := VBoxContainer.new()
	cart.add_theme_constant_override("separation", 8)
	cf.add_child(cart)
	var vslot := VBoxContainer.new()
	_n["verdict_slot"] = vslot
	cart.add_child(vslot)
	var crow := HBoxContainer.new()
	crow.add_theme_constant_override("separation", 8)
	crow.add_child(_lbl("提案篮 · 跨席位原子批", 10, INK3, true))
	var ccount := _lbl("0 项", 11, Color("647585"))
	_n["cart_count"] = ccount
	crow.add_child(ccount)
	crow.add_child(_spacer_h())
	var ccost := _lbl("", 10, Color("647585"), true)
	_n["cart_cost"] = ccost
	crow.add_child(ccost)
	cart.add_child(crow)
	var citems := VBoxContainer.new()
	citems.add_theme_constant_override("separation", 5)
	_n["cart_items"] = citems
	cart.add_child(citems)
	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 8)
	var submit := _btn("提交提案", _submit_cart, true)
	submit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_n["submit"] = submit
	actions.add_child(submit)
	var pass_b := _btn("本次不动", _submit_pass)
	_n["pass"] = pass_b
	actions.add_child(pass_b)
	cart.add_child(actions)


func _build_center(center: VBoxContainer) -> void:
	var tabs := HBoxContainer.new()
	tabs.add_theme_constant_override("separation", 6)
	for t: Array in [["focus", "宏观焦点"], ["panels", "指标全景"], ["world", "世界视图"]]:
		var b := Button.new()
		b.text = t[1]
		var tid: String = t[0]
		b.pressed.connect(func() -> void:
			_tab = tid
			_render())
		_n["tab_" + tid] = b
		tabs.add_child(b)
	tabs.add_child(_spacer_h())
	var tabnote := _lbl("X 轴 = 发布时间(非参考期)", 10, INK3, true)
	_n["tabnote"] = tabnote
	tabs.add_child(tabnote)
	center.add_child(tabs)
	var body := VBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 10)
	_n["center_body"] = body
	center.add_child(body)


func _build_timeline(tl: VBoxContainer) -> void:
	var hp := MarginContainer.new()
	hp.add_theme_constant_override("margin_left", 13)
	hp.add_theme_constant_override("margin_right", 13)
	hp.add_theme_constant_override("margin_top", 12)
	hp.add_theme_constant_override("margin_bottom", 10)
	tl.add_child(hp)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	hp.add_child(head)
	head.add_child(_lbl("EVENTS · 时间线", 10, INK3, true))
	head.add_child(_spacer_h())
	var filter := Button.new()
	filter.text = "全部事件"
	filter.add_theme_font_size_override("font_size", 11)
	filter.pressed.connect(func() -> void:
		_filter_mine = not _filter_mine
		_render())
	_n["filter"] = filter
	head.add_child(filter)
	tl.add_child(_hrule())
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tl.add_child(scroll)
	var ev := VBoxContainer.new()
	ev.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ev.add_theme_constant_override("separation", 8)
	scroll.add_child(ev)
	_n["events"] = ev


func _build_overlays() -> void:
	var crisis := ColorRect.new()
	crisis.color = Color(0.086, 0.137, 0.204, 0.38)
	crisis.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	crisis.visible = false
	_n["crisis"] = crisis
	add_child(crisis)
	var cp := PanelContainer.new()
	cp.add_theme_stylebox_override("panel", _sb(Color("fdeae4"), Color("e79b86"), 16, 0))
	cp.set_anchors_preset(Control.PRESET_CENTER_TOP)
	cp.position = Vector2(120, 70)
	cp.custom_minimum_size = Vector2(1040, 0)
	crisis.add_child(cp)
	var cv := VBoxContainer.new()
	cp.add_child(cv)
	var chp := MarginContainer.new()
	for m in ["margin_left", "margin_right", "margin_top", "margin_bottom"]:
		chp.add_theme_constant_override(m, 14)
	cv.add_child(chp)
	var chead := HBoxContainer.new()
	chead.add_theme_constant_override("separation", 12)
	chp.add_child(chead)
	chead.add_child(_dot(RED, 10))
	var ct := _lbl("紧急会议", 16, Color("7a2418"))
	_n["crisis_title"] = ct
	chead.add_child(ct)
	chead.add_child(_spacer_h())
	chead.add_child(_btn("离开横幅", func() -> void:
		_demo_crisis = false
		_crisis_dismissed = str(_emergency_context().get("context_id", ""))
		_render()))
	var cbp := MarginContainer.new()
	for m in ["margin_left", "margin_right", "margin_bottom"]:
		cbp.add_theme_constant_override(m, 16)
	cv.add_child(cbp)
	var cbody := HBoxContainer.new()
	cbody.add_theme_constant_override("separation", 16)
	cbp.add_child(cbody)
	var snapcol := VBoxContainer.new()
	snapcol.custom_minimum_size = Vector2(420, 0)
	snapcol.add_theme_constant_override("separation", 8)
	snapcol.add_child(_lbl("相关公报快照", 10, Color("9a6a5e"), true))
	_n["crisis_snap"] = snapcol
	cbody.add_child(snapcol)
	var levcol := VBoxContainer.new()
	levcol.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	levcol.add_theme_constant_override("separation", 9)
	var lh := HBoxContainer.new()
	lh.add_theme_constant_override("separation", 8)
	lh.add_child(_lbl("紧急白名单杠杆", 10, Color("9a6a5e"), true))
	lh.add_child(_chip("溢价适用", Color("a0691f"), Color(0, 0, 0, 0), AMBER_BD, 10))
	levcol.add_child(lh)
	_n["crisis_levers"] = levcol
	cbody.add_child(levcol)
	var trig := _btn("▲ 模拟紧急会议", func() -> void:
		_demo_crisis = true
		_render())
	trig.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	trig.position = Vector2(-180, -54)
	trig.add_theme_stylebox_override("normal", _sb(RED_BG, RED_BD, 10, 8))
	trig.add_theme_color_override("font_color", Color("cc5a44"))
	add_child(trig)
	var modal := ColorRect.new()
	modal.color = Color(0.086, 0.137, 0.204, 0.38)
	modal.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	modal.visible = false
	_n["modal"] = modal
	add_child(modal)
	var mp := PanelContainer.new()
	mp.add_theme_stylebox_override("panel", _sb(Color("f6f8fb"), Color("cdd7e2"), 14, 18))
	mp.set_anchors_preset(Control.PRESET_CENTER)
	mp.position = Vector2(420, 300)
	mp.custom_minimum_size = Vector2(440, 0)
	modal.add_child(mp)
	var mv := VBoxContainer.new()
	mv.add_theme_constant_override("separation", 10)
	mp.add_child(mv)
	var mtitle := _lbl("", 15, INK)
	_n["modal_title"] = mtitle
	mv.add_child(mtitle)
	var mb := _lbl("", 12, Color("45535f"))
	mb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	mb.custom_minimum_size = Vector2(400, 0)
	_n["modal_body"] = mb
	mv.add_child(mb)
	var mnote := _lbl("", 11, AMBER, true)
	_n["modal_note"] = mnote
	mv.add_child(mnote)
	var mrow := HBoxContainer.new()
	mrow.add_theme_constant_override("separation", 9)
	mrow.alignment = BoxContainer.ALIGNMENT_END
	mrow.add_child(_btn("取消", func() -> void:
		_confirm = {}
		_render()))
	mrow.add_child(_btn("确认", _confirm_yes, true))
	mv.add_child(mrow)


func _confirm_yes() -> void:
	var cb: Variant = _confirm.get("on_yes")
	_confirm = {}
	if cb is Callable:
		(cb as Callable).call()
	_render()


# ================= 渲染 =================
func _render() -> void:
	var t := int(_snapshot.get("tick", 0))
	_set_text("cal", _cal_str(t))
	_set_text("tick", "t = %d" % t)
	(_n["awaitchip"] as Control).visible = _awaiting()
	(_n["play"] as Button).text = "暂停" if _playing else "播放"
	for m in ["interactive", "realtime"]:
		var mb := _n["mode_" + m] as Button
		if m == _mode:
			mb.add_theme_stylebox_override("normal", _sb(TEAL_BG, TEAL_BD, 7, 6))
			mb.add_theme_color_override("font_color", TEAL_DK)
		else:
			mb.remove_theme_stylebox_override("normal")
			mb.add_theme_color_override("font_color", Color("586a7b"))
	for s: int in SPEEDS:
		var sbn := _n["speed_%d" % s] as Button
		if s == _speed:
			sbn.add_theme_stylebox_override("normal", _sb(BLUE_BG, BLUE_BD, 7, 6))
			sbn.add_theme_color_override("font_color", Color("3f6db2"))
		else:
			sbn.remove_theme_stylebox_override("normal")
			sbn.add_theme_color_override("font_color", Color("647585"))
	for tab in ["focus", "panels", "world"]:
		var tb := _n["tab_" + tab] as Button
		if tab == _tab:
			tb.add_theme_stylebox_override("normal", _sb(BLUE_BG, BLUE_BD, 9, 8))
			tb.add_theme_color_override("font_color", Color("1c4a8f"))
		else:
			tb.remove_theme_stylebox_override("normal")
			tb.add_theme_color_override("font_color", Color("586a7b"))
	_set_text("tabnote", "X 轴 = 发布时间(非参考期)" if _tab == "focus"
		else "上帝视角 · 逐 tick 真值(公报另见磁贴)")
	(_n["filter"] as Button).text = "仅我的席位" if _filter_mine else "全部事件"
	_render_tiles()
	_render_workbench()
	_render_center()
	_render_events()
	_render_crisis()
	(_n["modal"] as Control).visible = not _confirm.is_empty()
	if not _confirm.is_empty():
		_set_text("modal_title", str(_confirm.get("title", "")))
		_set_text("modal_body", str(_confirm.get("body", "")))
		_set_text("modal_note", str(_confirm.get("note", "")))


func _render_tiles() -> void:
	var row := _n["tiles"] as HBoxContainer
	for c in row.get_children():
		c.queue_free()
	var by_id := _releases_by_id()
	var truth: Dictionary = _snapshot.get("metrics", {})
	var t := int(_snapshot.get("tick", 0))
	for spec: Dictionary in TILE_SPEC:
		var sid := str(spec["id"])
		var tile := PanelContainer.new()
		tile.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		tile.custom_minimum_size = Vector2(0, 118)
		tile.add_theme_stylebox_override("panel", _sb(PANEL, LINE, 12, 11))
		var v := VBoxContainer.new()
		v.add_theme_constant_override("separation", 4)
		tile.add_child(v)
		var lr := HBoxContainer.new()
		lr.add_theme_constant_override("separation", 6)
		lr.add_child(_dot(spec["color"], 6))
		var tlabel := _lbl(str(spec["label"]), 11, INK2)
		tlabel.clip_text = true
		tlabel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		lr.add_child(tlabel)
		v.add_child(lr)
		var rel: Dictionary = by_id.get(sid, {})
		var has := not rel.is_empty() and rel.get("value") != null
		if has:
			var vr := HBoxContainer.new()
			vr.add_theme_constant_override("separation", 6)
			vr.add_child(_lbl(_fmt_series(sid, float(rel.get("value"))), 21, spec["color"], true))
			var hist: Array = _release_hist.get(sid, [])
			if hist.size() >= 2:
				var prev := float(hist[-2]["v"])
				var curv := float(hist[-1]["v"])
				if absf(curv - prev) > 1e-12:
					var up := curv > prev
					var dc: Color = (RED if up else GREEN) if bool(spec["bad_up"]) \
						else (GREEN if up else RED)
					vr.add_child(_lbl("▲" if up else "▼", 11, dc))
			v.add_child(vr)
			var chart := _SparkLine.new()
			chart.color = spec["color"]
			chart.custom_minimum_size = Vector2(0, 22)
			var vals: Array = []
			for hh: Dictionary in _release_hist.get(sid, []):
				vals.append(hh["v"])
			chart.values = vals
			v.add_child(chart)
			var ref_end := int(rel.get("reference_end_tick", t))
			var rline := _lbl("发布 t%d · 止 t%d · 距今 %d天" % [
				int(rel.get("released_at_tick", 0)), ref_end, t - ref_end], 9, INK3, true)
			rline.clip_text = true
			v.add_child(rline)
			if _god and truth.has(sid):
				var gl := _lbl("真值 " + _fmt_series(sid, float(truth.get(sid, 0.0)))
					+ " ·(调试)", 9, PURPLE, true)
				gl.clip_text = true
				v.add_child(gl)
		else:
			v.add_child(_lbl("暂无数据", 13, Color("68788b")))
			var why := str(rel.get("missing_reason", "not_released"))
			var wl := _lbl(why, 10, Color("849098"))
			wl.clip_text = true
			v.add_child(wl)
		row.add_child(tile)


# ================= 工作台 =================
func _render_workbench() -> void:
	var lv := _n["levers"] as VBoxContainer
	for c in lv.get_children():
		c.queue_free()
	var open := _awaiting()
	var emg_ctx := _emergency_context()
	var emg := not emg_ctx.is_empty()
	for s: Dictionary in SEAT_LIST:
		var sid := str(s["id"])
		var b := _n["seat_" + sid] as Button
		var n_open := 0
		for ctx: Dictionary in _contexts():
			if str(ctx.get("seat", "")) == sid:
				n_open += 1
		b.text = str(s["name"]) + (" ·%d" % n_open if n_open > 0 else "")
		if sid == _active_seat:
			b.add_theme_stylebox_override("normal", _sb(BLUE_BG, BLUE_BD, 8, 6))
			b.add_theme_color_override("font_color", Color("1c4a8f"))
		else:
			b.remove_theme_stylebox_override("normal")
			b.add_theme_color_override("font_color", Color("586a7b"))
	var seat_spec: Dictionary = SEAT_LIST[0]
	for s: Dictionary in SEAT_LIST:
		if str(s["id"]) == _active_seat:
			seat_spec = s
	_set_text("seat_title", str(seat_spec["name"]))
	((_n["seat_tag"] as PanelContainer).get_child(0) as Label).text = str(seat_spec["tag"])
	var cap_text := "行政容量 —"
	for ctx: Dictionary in _contexts():
		if str(ctx.get("seat", "")) == _active_seat and ctx.get("admin_remaining") != null:
			cap_text = "行政容量 " + str(ctx.get("admin_remaining"))
			break
	_set_text("cap", cap_text)
	_set_text("meeting", ("🚨 紧急会议 · 仅白名单杠杆可动" if emg
		else "例会开启(%d 个议题)· 调整杠杆后「加入提案」" % _contexts().size()) if open
		else "会议未开 · 只读(推进至会议自动暂停)")
	var permitted: Dictionary = {}
	for ctx: Dictionary in _contexts():
		for item: Dictionary in ctx.get("permitted_actions", []):
			permitted[str(item.get("lever"))] = item
	var pending_by: Dictionary = {}
	for p in _snapshot.get("pending", []):
		if p is Dictionary:
			for act in (p as Dictionary).get("actions", []):
				if act is Dictionary:
					pending_by[str((act as Dictionary).get("lever", ""))] = {
						"value": (act as Dictionary).get("value"),
						"effective_tick": (p as Dictionary).get("effective_tick", "?")}
	var groups := _seat_groups(_active_seat)
	for g: String in groups.keys():
		var gm := MarginContainer.new()
		gm.add_theme_constant_override("margin_left", 12)
		gm.add_theme_constant_override("margin_right", 12)
		var gh := HBoxContainer.new()
		gh.add_theme_constant_override("separation", 8)
		gm.add_child(gh)
		var g_open := not _context_for_group(g).is_empty()
		gh.add_child(_dot(TEAL if g_open else LINE2, 6))
		gh.add_child(_lbl(str(GROUP_CN.get(g, g)) + " · " + g.to_upper(), 10, INK3, true))
		var rule := ColorRect.new()
		rule.color = Color("e6ebf1")
		rule.custom_minimum_size = Vector2(0, 1)
		rule.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		rule.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		gh.add_child(rule)
		lv.add_child(gm)
		for lever: Dictionary in groups[g]:
			var cm := MarginContainer.new()
			cm.add_theme_constant_override("margin_left", 12)
			cm.add_theme_constant_override("margin_right", 12)
			cm.add_child(_lever_card(lever, permitted, pending_by, open, emg))
			lv.add_child(cm)
	_render_cart(open)


func _lever_current(lever: Dictionary, perm: Dictionary) -> Variant:
	if perm.has("current_value"):
		return perm.get("current_value")
	var cached: Dictionary = _perm_cache.get(str(lever.get("name")), {})
	return cached.get("current_value")


func _lever_card(lever: Dictionary, permitted: Dictionary,
		pending_by: Dictionary, open: bool, emg: bool) -> Control:
	var name := str(lever.get("name"))
	var perm: Dictionary = permitted.get(name, {})
	var allowed := open and bool(perm.get("allowed", false)) \
		and (not emg or bool(lever.get("emergency", false)))
	var in_cart := _cart.any(func(c: Dictionary) -> bool: return c["lever"] == name)
	var base_v: Variant = _lever_current(lever, perm)
	var edited := _edits.has(name)
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", _sb(
		Color("e6f5f0") if in_cart else Color.WHITE,
		Color("59b7a8") if in_cart else Color("e2e8ef"), 10, 10))
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 7)
	card.add_child(v)
	var tr := HBoxContainer.new()
	tr.add_theme_constant_override("separation", 7)
	tr.add_child(_dot(TEAL if edited else LINE2, 6))
	tr.add_child(_lbl(_cn(name), 13, INK))
	var en := _lbl(name, 9, Color("8a97a5"), true)
	en.clip_text = true
	en.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tr.add_child(en)
	var cost_class := str(lever.get("cost_class", "ordinary"))
	var cost_cn: String = {"regime_switch": "高", "major": "高", "ordinary": "中",
		"operational": "低"}.get(cost_class, "中")
	var cost_fg: Color = AMBER if cost_cn == "高" else (Color("3f6db2") if cost_cn == "中" else INK2)
	tr.add_child(_chip("成本 %.1f · %s" % [float(lever.get("admin_weight", 1.0)), cost_cn],
		cost_fg, Color(0, 0, 0, 0), AMBER_BD if cost_cn == "高" else LINE2, 10))
	v.add_child(tr)
	if allowed:
		v.add_child(_lever_control(lever, perm, base_v))
	else:
		var lockp := PanelContainer.new()
		lockp.add_theme_stylebox_override("panel", _sb(PANEL3, LINE2, 8, 9))
		var lr := HBoxContainer.new()
		lr.add_theme_constant_override("separation", 9)
		lockp.add_child(lr)
		lr.add_child(_chip("锁定", Color("647585"), Color(0, 0, 0, 0), LINE2, 10))
		var reason := str(perm.get("reason_code", ""))
		if emg and not bool(lever.get("emergency", false)):
			reason = "不在紧急白名单"
		elif not open:
			reason = "当前 " + _lever_value_text(lever, base_v) + " · 会议未开"
		elif reason.is_empty() or reason == "<null>":
			reason = "当前 " + _lever_value_text(lever, base_v) + " · 本会议不可动"
		var rl := _lbl(reason, 11, Color("586a7b"))
		rl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		rl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		lr.add_child(rl)
		v.add_child(lockp)
	var meta := HBoxContainer.new()
	meta.add_theme_constant_override("separation", 9)
	var lag := int(lever.get("implementation_lag", 0))
	meta.add_child(_lbl("通过后 %d 天生效" % lag if lag > 0 else "即时生效", 10,
		Color("68788b"), true))
	meta.add_child(_lbl("冷却 %d 天" % int(lever.get("min_hold_ticks", 0)), 10,
		Color("68788b"), true))
	if bool(lever.get("emergency", false)):
		meta.add_child(_lbl("紧急✓", 10, AMBER, true))
	v.add_child(meta)
	var pend: Variant = pending_by.get(name)
	if pend is Dictionary:
		var pp := PanelContainer.new()
		pp.add_theme_stylebox_override("panel", _sb(TEAL_BG, TEAL_BD, 7, 6))
		var pr := HBoxContainer.new()
		pr.add_theme_constant_override("separation", 8)
		pp.add_child(pr)
		pr.add_child(_lbl("待生效队列", 10, TEAL, true))
		pr.add_child(_lbl(_lever_value_text(lever, (pend as Dictionary).get("value")),
			11, TEAL_DK, true))
		pr.add_child(_spacer_h())
		pr.add_child(_lbl("生效 t%s" % str((pend as Dictionary).get("effective_tick", "?")),
			11, Color("2a9184")))
		v.add_child(pp)
	if allowed and edited and not in_cart:
		var add := _btn("加入提案 ＋", func() -> void:
			_add_to_cart(lever, base_v), true)
		add.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		v.add_child(add)
	elif in_cart:
		v.add_child(_lbl("✓ 已在提案篮", 11, TEAL))
	return card


func _lever_value_text(lever: Dictionary, v: Variant) -> String:
	if v == null:
		return "不设(None)"
	if v is bool:
		return "启用" if v else "停用"
	if v is String:
		return v
	if v is Array:
		if (v as Array).is_empty():
			return "无制裁对象"
		var parts: Array = []
		for e in v:
			parts.append(_country_name(int(e)))
		return " + ".join(parts)
	var kind := str(lever.get("value_kind", ""))
	if kind == "economy_id":
		return _country_name(int(v))
	var f := float(v)
	var scale := absf(float(lever.get("control_scale", 1.0)))
	if scale >= 1.0:
		return "%d" % roundi(f)
	if scale < 0.001:
		return "%.5f" % f
	return "%.3f" % f


func _lever_control(lever: Dictionary, perm: Dictionary, base_v: Variant) -> Control:
	var name := str(lever.get("name"))
	var kind := str(perm.get("value_kind", lever.get("value_kind", "number")))
	var choices: Array = perm.get("choices", lever.get("choices", []))
	var cur: Variant = _edits.get(name, base_v)
	if kind == "economy_set":
		return _economy_set_control(name, cur)
	if kind == "economy_id":
		return _economy_id_control(name, cur, choices)
	if not choices.is_empty() and kind == "choice":
		var seg := HBoxContainer.new()
		seg.add_theme_constant_override("separation", 3)
		for opt in choices:
			var b := Button.new()
			b.text = str(opt)
			b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			if str(cur) == str(opt):
				b.add_theme_stylebox_override("normal", _sb(TEAL_BG, TEAL_BD, 6, 6))
				b.add_theme_color_override("font_color", TEAL_DK)
			var value := str(opt)
			b.pressed.connect(func() -> void:
				_edits[name] = value
				_render())
			seg.add_child(b)
		return seg
	if kind == "bool":
		var brow := HBoxContainer.new()
		brow.add_theme_constant_override("separation", 9)
		var sw := CheckButton.new()
		sw.button_pressed = cur == true
		sw.text = "启用" if cur == true else "停用"
		var st := str(lever.get("semantics",
			lever.get("effective_semantics", ""))).contains("transition")
		sw.toggled.connect(func(pressed: bool) -> void:
			if st:
				_confirm = {"title": "状态迁移确认",
					"body": "切换「%s」属状态迁移(STATE_TRANSITION),将改变制度分支并按更高成本计费。确认迁移?" % _cn(name),
					"note": "成本类 · 高 · 通过后 %d 天生效" % int(lever.get("implementation_lag", 0)),
					"on_yes": func() -> void:
						_edits[name] = pressed
						_render()}
				_render()
			else:
				_edits[name] = pressed
				_render())
		brow.add_child(sw)
		if st:
			brow.add_child(_chip("状态迁移", Color("9a7a2e"), Color(0, 0, 0, 0), AMBER_BD, 10))
		return brow
	# 数值(含可空)
	var wrap := VBoxContainer.new()
	wrap.add_theme_constant_override("separation", 5)
	var nullable := bool(perm.get("nullable", lever.get("nullable", false)))
	var srow := HBoxContainer.new()
	srow.add_theme_constant_override("separation", 7)
	var numeric := cur != null and not (cur is bool) and not (cur is String)
	var dec := Button.new()
	dec.text = "−"
	dec.custom_minimum_size = Vector2(38, 0)
	dec.add_theme_font_size_override("font_size", 18)
	srow.add_child(dec)
	var mid := PanelContainer.new()
	mid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mid.add_theme_stylebox_override("panel", _sb(PANEL2, LINE2, 8, 6))
	var midv := VBoxContainer.new()
	mid.add_child(midv)
	var vrow := HBoxContainer.new()
	vrow.add_theme_constant_override("separation", 7)
	vrow.add_child(_lbl(_lever_value_text(lever, cur), 18, INK, true))
	if numeric and _edits.has(name) and base_v != null and not (base_v is bool):
		var delta := float(_edits[name]) - float(base_v)
		if absf(delta) > 1e-12:
			vrow.add_child(_lbl("▲" if delta > 0 else "▼", 11, GREEN if delta > 0 else RED))
	midv.add_child(vrow)
	var scale := float(perm.get("control_scale", lever.get("control_scale", 0.01)))
	var lo := float(perm.get("minimum", lever.get("minimum", 0.0)))
	var hi := float(perm.get("maximum", lever.get("maximum", 0.0)))
	midv.add_child(_lbl("档 %s · 域 %s – %s" % [
		_lever_value_text(lever, scale), _lever_value_text(lever, lo),
		_lever_value_text(lever, hi)], 9, INK3, true))
	srow.add_child(mid)
	var inc := Button.new()
	inc.text = "＋"
	inc.custom_minimum_size = Vector2(38, 0)
	inc.add_theme_font_size_override("font_size", 18)
	srow.add_child(inc)
	dec.disabled = not numeric
	inc.disabled = not numeric
	if numeric:
		var base := float(cur)
		if scale <= 0.0:
			scale = 0.01
		var mstep: Variant = perm.get("max_step", lever.get("max_step"))
		var lo2 := lo
		var hi2 := hi
		if mstep != null and base_v != null and not (base_v is bool):
			lo2 = maxf(lo, float(base_v) - float(mstep))
			hi2 = minf(hi, float(base_v) + float(mstep))
		var is_int := kind == "integer"
		dec.pressed.connect(func() -> void:
			var nv := clampf(float(_edits.get(name, base)) - scale, lo2, hi2)
			_edits[name] = roundi(nv) if is_int else nv
			_render())
		inc.pressed.connect(func() -> void:
			var nv := clampf(float(_edits.get(name, base)) + scale, lo2, hi2)
			_edits[name] = roundi(nv) if is_int else nv
			_render())
	wrap.add_child(srow)
	if nullable:
		var nrow := HBoxContainer.new()
		nrow.add_theme_constant_override("separation", 7)
		var nb := Button.new()
		nb.add_theme_font_size_override("font_size", 11)
		if cur == null:
			nb.text = "设为数值"
			nb.pressed.connect(func() -> void:
				_edits[name] = lo
				_render())
		else:
			nb.text = "置为不设(None)"
			nb.pressed.connect(func() -> void:
				_edits[name] = null
				_render())
		nrow.add_child(nb)
		nrow.add_child(_lbl("可空杠杆:None = 制度不启用", 10, INK3))
		wrap.add_child(nrow)
	return wrap


func _economy_set_control(name: String, cur: Variant) -> Control:
	var wrap := VBoxContainer.new()
	wrap.add_theme_constant_override("separation", 5)
	var selected: Array = []
	if cur is Array:
		for e in cur:
			selected.append(int(e))
	var countries: Array = _world().get("countries", [])
	for i in range(1, maxi(countries.size(), 3)):
		var row := PanelContainer.new()
		var on := selected.has(i)
		row.add_theme_stylebox_override("panel", _sb(
			RED_BG if on else Color.WHITE, RED_BD if on else LINE, 8, 7))
		var r := HBoxContainer.new()
		r.add_theme_constant_override("separation", 8)
		row.add_child(r)
		r.add_child(_dot(ECON_COLORS[i % 3], 8))
		r.add_child(_lbl(_country_name(i), 12, Color("7a2418") if on else INK_BODY))
		r.add_child(_spacer_h())
		var cb := Button.new()
		cb.text = "解除制裁" if on else "施加制裁"
		cb.add_theme_font_size_override("font_size", 11)
		var target := i
		cb.pressed.connect(func() -> void:
			var next: Array = selected.duplicate()
			if next.has(target):
				next.erase(target)
			else:
				next.append(target)
			next.sort()
			_edits[name] = next
			_render())
		r.add_child(cb)
		wrap.add_child(row)
	wrap.add_child(_lbl("OR 语义:任一方向制裁即断流(对方亦可制裁我)", 10, INK3))
	return wrap


func _economy_id_control(name: String, cur: Variant, choices: Array) -> Control:
	var seg := HBoxContainer.new()
	seg.add_theme_constant_override("separation", 3)
	var opts: Array = choices if not choices.is_empty() else [1, 2, null]
	for opt in opts:
		var b := Button.new()
		b.text = "不设" if opt == null else _country_name(int(opt))
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var same := (cur == null and opt == null) or \
			(cur != null and opt != null and int(cur) == int(opt))
		if same:
			b.add_theme_stylebox_override("normal", _sb(TEAL_BG, TEAL_BD, 6, 6))
			b.add_theme_color_override("font_color", TEAL_DK)
		var value: Variant = opt
		b.pressed.connect(func() -> void:
			_edits[name] = value
			_render())
		seg.add_child(b)
	return seg


func _add_to_cart(lever: Dictionary, base_v: Variant) -> void:
	var name := str(lever.get("name"))
	if not _edits.has(name):
		return
	_cart = _cart.filter(func(c: Dictionary) -> bool: return c["lever"] != name)
	_cart.append({"lever": name,
		"group": str(_lever_group.get(name, "")),
		"from": _lever_value_text(lever, base_v),
		"to": _lever_value_text(lever, _edits[name]),
		"value": _edits[name]})
	_render()


func _render_cart(open: bool) -> void:
	var items := _n["cart_items"] as VBoxContainer
	for c in items.get_children():
		c.queue_free()
	_set_text("cart_count", "%d 项" % _cart.size())
	_set_text("cart_cost", "" if _cart.is_empty() else "提交将闭合本次全部议题")
	if _cart.is_empty():
		items.add_child(_lbl("尚无动作。任意席位调整杠杆后「加入提案」,一起提交、一起裁决。",
			11, Color("7a8593")))
	for c: Dictionary in _cart:
		var rowp := PanelContainer.new()
		rowp.add_theme_stylebox_override("panel", _sb(Color.WHITE, LINE, 7, 6))
		var r := HBoxContainer.new()
		r.add_theme_constant_override("separation", 8)
		rowp.add_child(r)
		r.add_child(_lbl(str(GROUP_CN.get(str(c["group"]), c["group"])), 10, INK3))
		r.add_child(_lbl(_cn(str(c["lever"])), 12, Color("23323f")))
		r.add_child(_spacer_h())
		r.add_child(_lbl(str(c["from"]), 11, Color("586a7b"), true))
		r.add_child(_lbl("→", 11, TEAL))
		r.add_child(_lbl(str(c["to"]), 11, TEAL_DK, true))
		var rm := Button.new()
		rm.text = "×"
		rm.flat = true
		var key := str(c["lever"])
		rm.pressed.connect(func() -> void:
			_cart = _cart.filter(func(x: Dictionary) -> bool: return x["lever"] != key)
			_edits.erase(key)
			_render())
		r.add_child(rm)
		items.add_child(rowp)
	(_n["submit"] as Button).disabled = not open or _cart.is_empty()
	(_n["pass"] as Button).disabled = not open


func _show_hint(text: String) -> void:
	var slot := _n["verdict_slot"] as VBoxContainer
	for c in slot.get_children():
		c.queue_free()
	var vp := PanelContainer.new()
	vp.add_theme_stylebox_override("panel", _sb(AMBER_BG, AMBER_BD, 9, 9))
	var r := HBoxContainer.new()
	r.add_theme_constant_override("separation", 9)
	vp.add_child(r)
	r.add_child(_lbl("!", 15, AMBER))
	var tl := _lbl(text, 11, Color("8a6114"))
	tl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	tl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	r.add_child(tl)
	var x := Button.new()
	x.text = "×"
	x.flat = true
	x.pressed.connect(func() -> void:
		for c in slot.get_children():
			c.queue_free())
	r.add_child(x)
	slot.add_child(vp)


func _show_verdict(v: Dictionary) -> void:
	var key := str(v.get("decision_id", v.get("proposal_id", "")))
	if key == _last_toasted or key.is_empty():
		return
	_last_toasted = key
	var slot := _n["verdict_slot"] as VBoxContainer
	for c in slot.get_children():
		c.queue_free()
	var status := str(v.get("status", "?"))
	var ok := status.begins_with("accepted") or status == "noop"
	var vp := PanelContainer.new()
	vp.add_theme_stylebox_override("panel", _sb(
		Color("e3f4ea") if ok else RED_BG,
		Color("59b7a8") if ok else RED_BD, 9, 9))
	var r := HBoxContainer.new()
	r.add_theme_constant_override("separation", 9)
	vp.add_child(r)
	r.add_child(_lbl("✓" if ok else "✕", 15, GREEN if ok else RED))
	var col := VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_child(_lbl("判决 · " + status, 12, GREEN if ok else RED))
	var reason := str(v.get("reason_code", ""))
	var sub := ""
	if not reason.is_empty() and reason != "<null>":
		sub = reason
	if v.get("effective_tick") != null:
		sub += ("" if sub.is_empty() else " · ") + "生效 t" + str(v.get("effective_tick"))
	if not sub.is_empty():
		var sl := _lbl(sub, 11, Color("526475"))
		sl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		col.add_child(sl)
	r.add_child(col)
	var x := Button.new()
	x.text = "×"
	x.flat = true
	x.pressed.connect(func() -> void:
		for c in slot.get_children():
			c.queue_free())
	r.add_child(x)
	slot.add_child(vp)


func _submit_cart() -> void:
	if _cart.is_empty():
		return
	var by_group: Dictionary = {}
	for c: Dictionary in _cart:
		var g := str(c["group"])
		if not by_group.has(g):
			by_group[g] = []
		by_group[g].append({"lever": c["lever"], "value": c["value"]})
	for ctx: Dictionary in _contexts():
		var g := str(ctx.get("decision_group", ""))
		_send({"command": "resolve_context",
			"context_id": str(ctx.get("context_id")),
			"actions": by_group.get(g, [])})
	_cart.clear()
	_edits.clear()


func _submit_pass() -> void:
	for ctx: Dictionary in _contexts():
		_send({"command": "resolve_context",
			"context_id": str(ctx.get("context_id")), "actions": []})
	_cart.clear()
	_edits.clear()


# ================= 中央区 =================
func _render_center() -> void:
	var body := _n["center_body"] as VBoxContainer
	for c in body.get_children():
		c.queue_free()
	match _tab:
		"world":
			_render_world_tab(body)
		"panels":
			_render_panels_tab(body)
		_:
			_render_focus_tab(body)


func _render_focus_tab(body: VBoxContainer) -> void:
	var fp := PanelContainer.new()
	var fv := VBoxContainer.new()
	fv.add_theme_constant_override("separation", 6)
	fp.add_child(fv)
	var legend := HBoxContainer.new()
	legend.add_theme_constant_override("separation", 14)
	legend.add_child(_lbl("宏观焦点 · 公报序列", 14, INK))
	legend.add_child(_spacer_h())
	for item: Array in [["实际产出", TEAL], ["失业率", AMBER], ["通胀", PURPLE]]:
		var li := HBoxContainer.new()
		li.add_theme_constant_override("separation", 5)
		var swatch := ColorRect.new()
		swatch.color = item[1]
		swatch.custom_minimum_size = Vector2(16, 3)
		swatch.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		li.add_child(swatch)
		li.add_child(_lbl(str(item[0]), 11, Color("4a5a6b")))
		legend.add_child(li)
	fv.add_child(legend)
	var chart := _FocusChart.new()
	chart.custom_minimum_size = Vector2(0, 250)
	chart.series = [
		{"vals": _hist_vals("real_output"), "color": TEAL, "width": 2.4},
		{"vals": _hist_vals("unemployment_rate"), "color": AMBER, "width": 1.8},
		{"vals": _hist_vals("inflation"), "color": PURPLE, "width": 1.8},
	]
	chart.shock_active = not _snapshot.get("active_shocks", []).is_empty()
	chart.font = _sans
	fv.add_child(chart)
	var notes := HBoxContainer.new()
	notes.add_theme_constant_override("separation", 10)
	notes.add_child(_lbl("t 时刻仅显示 released_at ≤ t 的公报", 11, INK2))
	notes.add_child(_lbl("·", 11, LINE2))
	notes.add_child(_lbl("缺失显式化,禁止零填 / 前值补", 11, INK2))
	notes.add_child(_lbl("·", 11, LINE2))
	notes.add_child(_lbl("365 tick = 1 年", 11, INK2))
	fv.add_child(notes)
	body.add_child(fp)
	var sp := PanelContainer.new()
	sp.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sv := VBoxContainer.new()
	sv.add_theme_constant_override("separation", 9)
	sp.add_child(sv)
	sv.add_child(_lbl("SERIES · 公报小图(近 24 期发布)", 10, INK3, true))
	var grid := HBoxContainer.new()
	grid.add_theme_constant_override("separation", 10)
	grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sv.add_child(grid)
	for spec: Dictionary in [TILE_SPEC[0], TILE_SPEC[1], TILE_SPEC[2], TILE_SPEC[4]]:
		var sid := str(spec["id"])
		var card := PanelContainer.new()
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		card.add_theme_stylebox_override("panel", _sb(PANEL3, Color("e6ebf1"), 10, 10))
		var cv := VBoxContainer.new()
		cv.add_theme_constant_override("separation", 5)
		card.add_child(cv)
		var hr := HBoxContainer.new()
		hr.add_theme_constant_override("separation", 6)
		hr.add_child(_dot(spec["color"], 6))
		hr.add_child(_lbl(str(spec["label"]).split(" · ")[0], 11, Color("516375")))
		cv.add_child(hr)
		var hist: Array = _release_hist.get(sid, [])
		if hist.is_empty():
			cv.add_child(_lbl("暂无发布", 12, INK3))
		else:
			cv.add_child(_lbl(_fmt_series(sid, float(hist[-1]["v"])), 17, spec["color"], true))
			var sl := _SparkLine.new()
			sl.color = spec["color"]
			sl.custom_minimum_size = Vector2(0, 30)
			var vals: Array = []
			for hh: Dictionary in hist:
				vals.append(hh["v"])
			sl.values = vals
			cv.add_child(sl)
			cv.add_child(_lbl("发布 t%d" % int(hist[-1]["at"]), 9, INK3, true))
		grid.add_child(card)
	body.add_child(sp)


func _render_panels_tab(body: VBoxContainer) -> void:
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	body.add_child(scroll)
	var col := VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 10)
	scroll.add_child(col)
	var series: Array = _snapshot.get("series", [])
	var latest: Dictionary = _snapshot.get("metrics", {})
	for grp: Dictionary in PANEL_GROUPS:
		var gp := PanelContainer.new()
		var gv := VBoxContainer.new()
		gv.add_theme_constant_override("separation", 8)
		gp.add_child(gv)
		var gh := HBoxContainer.new()
		gh.add_theme_constant_override("separation", 8)
		gh.add_child(_dot(grp["color"], 8))
		gh.add_child(_lbl(str(grp["name"]), 13, INK))
		gh.add_child(_spacer_h())
		gh.add_child(_lbl("真值 · 逐tick", 9, INK3, true))
		gv.add_child(gh)
		var grid := GridContainer.new()
		grid.columns = 3
		grid.add_theme_constant_override("h_separation", 9)
		grid.add_theme_constant_override("v_separation", 9)
		gv.add_child(grid)
		for item: Array in grp["items"]:
			var key := str(item[0])
			var card := PanelContainer.new()
			card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			card.add_theme_stylebox_override("panel", _sb(PANEL3, Color("e6ebf1"), 9, 8))
			var cv := VBoxContainer.new()
			cv.add_theme_constant_override("separation", 3)
			card.add_child(cv)
			cv.add_child(_lbl(str(item[1]), 10, Color("516375")))
			cv.add_child(_lbl(_fmt_val(str(item[2]), float(latest.get(key, 0.0))),
				15, grp["color"], true))
			var sl := _SparkLine.new()
			sl.color = grp["color"]
			sl.custom_minimum_size = Vector2(120, 24)
			var vals: Array = []
			for point: Dictionary in series:
				vals.append(float(point.get(key, 0.0)))
			sl.values = vals
			cv.add_child(sl)
			grid.add_child(card)
		col.add_child(gp)


func _render_world_tab(body: VBoxContainer) -> void:
	var world := _world()
	var latest: Dictionary = world.get("latest", {})
	var econs: Array = latest.get("economies", [])
	if econs.is_empty():
		var ep := PanelContainer.new()
		ep.size_flags_vertical = Control.SIZE_EXPAND_FILL
		var ev := VBoxContainer.new()
		ep.add_child(ev)
		ev.add_child(_lbl("世界视图 · 三国耦合", 14, INK))
		ev.add_child(_lbl("推进模拟以积累世界数据(贸易/资本/移民已耦合)。", 12, INK2))
		body.add_child(ep)
		return
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	body.add_child(scroll)
	var col := VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 10)
	scroll.add_child(col)
	# --- 经济体卡片行 ---
	var cards := HBoxContainer.new()
	cards.add_theme_constant_override("separation", 9)
	for i in econs.size():
		var e: Dictionary = econs[i]
		var card := PanelContainer.new()
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var mine := i == int(world.get("player_economy", 0))
		card.add_theme_stylebox_override("panel", _sb(
			Color("eef7f5") if mine else PANEL,
			TEAL_BD if mine else LINE, 12, 11))
		var cv := VBoxContainer.new()
		cv.add_theme_constant_override("separation", 4)
		card.add_child(cv)
		var hr := HBoxContainer.new()
		hr.add_theme_constant_override("separation", 7)
		var flag := ColorRect.new()
		flag.color = ECON_COLORS[i % 3]
		flag.custom_minimum_size = Vector2(18, 12)
		flag.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		hr.add_child(flag)
		hr.add_child(_lbl(_country_name(i), 13, INK))
		if mine:
			hr.add_child(_chip("我", TEAL, Color(0, 0, 0, 0), TEAL_BD, 9))
		cv.add_child(hr)
		var rows: Array = [
			["GDP", _fmt_val("num", float(e.get("real_output", 0.0)))],
			["失业", _fmt_val("pct", float(e.get("unemployment_rate", 0.0)))],
			["通胀", _fmt_val("pt", float(e.get("inflation", 0.0)))],
			["汇率 e", "%.4f" % _fx_at(latest, i)],
		]
		for rr: Array in rows:
			var r2 := HBoxContainer.new()
			r2.add_theme_constant_override("separation", 6)
			r2.add_child(_lbl(str(rr[0]), 10, INK2))
			r2.add_child(_spacer_h())
			r2.add_child(_lbl(str(rr[1]), 12, ECON_COLORS[i % 3], true))
			cv.add_child(r2)
		cards.add_child(card)
	col.add_child(cards)
	# --- 排名 ---
	var rp := PanelContainer.new()
	var rv := VBoxContainer.new()
	rv.add_theme_constant_override("separation", 7)
	rp.add_child(rv)
	var rh := HBoxContainer.new()
	rh.add_theme_constant_override("separation", 8)
	rh.add_child(_lbl("RANK · 多国排名", 10, INK3, true))
	rh.add_child(_spacer_h())
	for rm: Array in RANK_METRICS:
		var b := Button.new()
		b.text = str(rm[1])
		b.add_theme_font_size_override("font_size", 11)
		var key := str(rm[0])
		if key == _rank_by:
			b.add_theme_stylebox_override("normal", _sb(BLUE_BG, BLUE_BD, 7, 5))
			b.add_theme_color_override("font_color", Color("1c4a8f"))
		b.pressed.connect(func() -> void:
			_rank_by = key
			_render())
		rh.add_child(b)
	rv.add_child(rh)
	var rank_kind := "num"
	var rank_asc := false
	for rm: Array in RANK_METRICS:
		if str(rm[0]) == _rank_by:
			rank_kind = str(rm[2])
			rank_asc = bool(rm[3])
	var order: Array = []
	for i in econs.size():
		order.append([i, float((econs[i] as Dictionary).get(_rank_by, 0.0))])
	order.sort_custom(func(a: Array, b: Array) -> bool:
		return (a[1] < b[1]) if rank_asc else (a[1] > b[1]))
	var maxv := 0.000001
	for row: Array in order:
		maxv = maxf(maxv, absf(float(row[1])))
	for pos in order.size():
		var row: Array = order[pos]
		var i := int(row[0])
		var rr := HBoxContainer.new()
		rr.add_theme_constant_override("separation", 9)
		rr.add_child(_lbl("#%d" % (pos + 1), 12, INK3, true))
		var flag := ColorRect.new()
		flag.color = ECON_COLORS[i % 3]
		flag.custom_minimum_size = Vector2(14, 10)
		flag.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		rr.add_child(flag)
		rr.add_child(_lbl(_country_name(i), 12, INK_BODY))
		var barwrap := Control.new()
		barwrap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		barwrap.custom_minimum_size = Vector2(0, 12)
		var frac := absf(float(row[1])) / maxv
		var color: Color = ECON_COLORS[i % 3]
		barwrap.draw.connect(func() -> void:
			barwrap.draw_rect(Rect2(Vector2(0, 3),
				Vector2(barwrap.size.x, 6)), Color("edf1f6"))
			barwrap.draw_rect(Rect2(Vector2(0, 3),
				Vector2(barwrap.size.x * frac, 6)), color))
		rr.add_child(barwrap)
		rr.add_child(_lbl(_fmt_val(rank_kind, float(row[1])), 12, ECON_COLORS[i % 3], true))
		rv.add_child(rr)
	col.add_child(rp)
	# --- 对比小图 ---
	var cmp := PanelContainer.new()
	var cmpv := VBoxContainer.new()
	cmpv.add_theme_constant_override("separation", 8)
	cmp.add_child(cmpv)
	var ch := HBoxContainer.new()
	ch.add_theme_constant_override("separation", 10)
	ch.add_child(_lbl("COMPARE · 多国对比", 10, INK3, true))
	ch.add_child(_spacer_h())
	for i in econs.size():
		var li := HBoxContainer.new()
		li.add_theme_constant_override("separation", 5)
		var swatch := ColorRect.new()
		swatch.color = ECON_COLORS[i % 3]
		swatch.custom_minimum_size = Vector2(14, 3)
		swatch.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		li.add_child(swatch)
		li.add_child(_lbl(_country_name(i), 10, Color("4a5a6b")))
		ch.add_child(li)
	cmpv.add_child(ch)
	var cgrid := GridContainer.new()
	cgrid.columns = 3
	cgrid.add_theme_constant_override("h_separation", 9)
	cgrid.add_theme_constant_override("v_separation", 9)
	cmpv.add_child(cgrid)
	var whist: Array = world.get("history", [])
	for item: Array in WORLD_COMPARE:
		var key := str(item[0])
		var card := PanelContainer.new()
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		card.add_theme_stylebox_override("panel", _sb(PANEL3, Color("e6ebf1"), 9, 8))
		var cv := VBoxContainer.new()
		cv.add_theme_constant_override("separation", 3)
		card.add_child(cv)
		cv.add_child(_lbl(str(item[1]), 10, Color("516375")))
		var ml := _MultiLine.new()
		ml.custom_minimum_size = Vector2(140, 42)
		var all_series: Array = []
		for i in econs.size():
			var vals: Array = []
			for point: Dictionary in whist:
				var pe: Array = point.get("economies", [])
				if i < pe.size():
					vals.append(float((pe[i] as Dictionary).get(key, 0.0)))
			all_series.append({"vals": vals, "color": ECON_COLORS[i % 3]})
		ml.series = all_series
		cv.add_child(ml)
		var vrow := HBoxContainer.new()
		vrow.add_theme_constant_override("separation", 8)
		for i in econs.size():
			vrow.add_child(_lbl(_fmt_val(str(item[2]),
				float((econs[i] as Dictionary).get(key, 0.0))), 10,
				ECON_COLORS[i % 3], true))
		cv.add_child(vrow)
		cgrid.add_child(card)
	col.add_child(cmp)
	# --- 国际关系:贸易 / 金融 / 移民 ---
	var rel := PanelContainer.new()
	var relv := VBoxContainer.new()
	relv.add_theme_constant_override("separation", 8)
	rel.add_child(relv)
	var relh := HBoxContainer.new()
	relh.add_theme_constant_override("separation", 8)
	relh.add_child(_lbl("RELATIONS · 贸易 / 金融 / 移民", 10, INK3, true))
	relh.add_child(_spacer_h())
	relh.add_child(_lbl("经由结算枢纽(FX dealer)的通道量", 9, INK3))
	relv.add_child(relh)
	var relrow := HBoxContainer.new()
	relrow.add_theme_constant_override("separation", 10)
	relv.add_child(relrow)
	var map := _RelationsMap.new()
	map.custom_minimum_size = Vector2(360, 240)
	map.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	map.font = _sans
	var mnames: Array = []
	for i in econs.size():
		mnames.append(_country_name(i))
	map.names = mnames
	map.colors = ECON_COLORS
	map.exports = _num_list(latest.get("export_delivered_volume", []))
	map.imports = _num_list(latest.get("import_value", []))
	map.migrants = _num_list(latest.get("migrant_stock", []))
	map.remit = _num_list(latest.get("remittances", []))
	relrow.add_child(map)
	var bars := VBoxContainer.new()
	bars.custom_minimum_size = Vector2(280, 0)
	bars.add_theme_constant_override("separation", 7)
	relrow.add_child(bars)
	_bar_block(bars, "汇率 e(numéraire)", _num_list(latest.get("e", [])), "%.4f", false)
	_bar_block(bars, "净外国资产 NFA", _num_list(latest.get("nfa", [])), "%.1f", true)
	_bar_block(bars, "经常账户(近30t累计)", _ca_sum(whist), "%.1f", true)
	_bar_block(bars, "海外移民存量", _num_list(latest.get("migrant_stock", [])), "%.2f", false)
	_bar_block(bars, "汇款流入", _num_list(latest.get("remittances", [])), "%.3f", false)
	var foot := HBoxContainer.new()
	foot.add_theme_constant_override("separation", 10)
	foot.add_child(_lbl("FX 做市商估值 %.2f" % float(latest.get("dealer_valuation", 0.0)),
		10, INK3, true))
	foot.add_child(_lbl("·", 10, LINE2))
	foot.add_child(_lbl("联系汇率 " + ("完好" if bool(latest.get("peg_intact", true))
		else "已破防"), 10, INK3))
	relv.add_child(foot)
	col.add_child(rel)


func _fx_at(latest: Dictionary, i: int) -> float:
	var e: Array = latest.get("e", [])
	return float(e[i]) if i < e.size() else 1.0


func _num_list(v: Variant) -> Array:
	var out: Array = []
	if v is Array:
		for x in v:
			out.append(float(x) if (x is float or x is int) else 0.0)
	elif v is Dictionary:
		var keys: Array = (v as Dictionary).keys()
		keys.sort()
		for k in keys:
			out.append(float((v as Dictionary)[k]))
	return out


func _ca_sum(whist: Array) -> Array:
	var out: Array = []
	var tail: Array = whist.slice(maxi(0, whist.size() - 30))
	for point: Dictionary in tail:
		var ca: Array = point.get("current_account", [])
		for i in ca.size():
			while out.size() <= i:
				out.append(0.0)
			out[i] = float(out[i]) + float(ca[i])
	return out


func _bar_block(parent: VBoxContainer, title: String, vals: Array,
		fmt: String, signed: bool) -> void:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", _sb(PANEL3, Color("e6ebf1"), 8, 7))
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 4)
	p.add_child(v)
	v.add_child(_lbl(title, 9, INK3, true))
	var maxv := 0.000001
	for x in vals:
		maxv = maxf(maxv, absf(float(x)))
	for i in vals.size():
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 7)
		var flag := ColorRect.new()
		flag.color = ECON_COLORS[i % 3]
		flag.custom_minimum_size = Vector2(10, 8)
		flag.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		row.add_child(flag)
		var barwrap := Control.new()
		barwrap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		barwrap.custom_minimum_size = Vector2(0, 10)
		var value := float(vals[i])
		var frac := absf(value) / maxv
		var bc: Color = (GREEN if value >= 0 else RED) if signed else ECON_COLORS[i % 3]
		barwrap.draw.connect(func() -> void:
			barwrap.draw_rect(Rect2(Vector2(0, 2),
				Vector2(barwrap.size.x, 6)), Color("edf1f6"))
			barwrap.draw_rect(Rect2(Vector2(0, 2),
				Vector2(barwrap.size.x * frac, 6)), bc))
		row.add_child(barwrap)
		row.add_child(_lbl(fmt % value, 10, INK_BODY, true))
		v.add_child(row)
	parent.add_child(p)


func _hist_vals(sid: String) -> Array:
	var out: Array = []
	for h: Dictionary in _release_hist.get(sid, []):
		out.append(float(h["v"]))
	return out


# ================= 时间线 =================
func _render_events() -> void:
	var box := _n["events"] as VBoxContainer
	for c in box.get_children():
		c.queue_free()
	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 12)
	margin.add_theme_constant_override("margin_right", 12)
	margin.add_theme_constant_override("margin_top", 10)
	var inner := VBoxContainer.new()
	inner.add_theme_constant_override("separation", 8)
	margin.add_child(inner)
	box.add_child(margin)
	for bulletin in _snapshot.get("shock_bulletins", []):
		if not (bulletin is Dictionary):
			continue
		var bp := PanelContainer.new()
		bp.add_theme_stylebox_override("panel", _sb(Color("fbe3db"), RED_BD, 10, 9))
		var bv := VBoxContainer.new()
		bv.add_theme_constant_override("separation", 3)
		bp.add_child(bv)
		var br := HBoxContainer.new()
		br.add_theme_constant_override("separation", 7)
		br.add_child(_dot(RED, 7))
		br.add_child(_lbl("冲击预告", 10, Color("cc5a44")))
		br.add_child(_spacer_h())
		br.add_child(_lbl("t%s" % str((bulletin as Dictionary).get("start_tick", "?")),
			10, Color("9a6a5e"), true))
		bv.add_child(br)
		bv.add_child(_lbl(str((bulletin as Dictionary).get("shock_id",
			(bulletin as Dictionary).get("kind", "shock"))), 12, Color("8a3a2c")))
		inner.add_child(bp)
	var merged: Array = []
	for ev in _snapshot.get("events", []):
		if ev is Dictionary:
			merged.append(ev)
	for ev in _snapshot.get("shock_events", []):
		if ev is Dictionary:
			merged.append(ev)
	merged.reverse()
	for ev: Dictionary in merged.slice(0, 36):
		var actor := str(ev.get("actor", ""))
		var mine := actor.contains("desktop") or actor.contains("player")
		if _filter_mine and not mine:
			continue
		var etype := str(ev.get("event_type", ev.get("kind", "event")))
		var color := Color("586a7b")
		if etype.contains("accepted") or etype.contains("committed"):
			color = GREEN
		elif etype.contains("rejected") or etype.contains("failed"):
			color = RED
		elif etype.contains("context") or etype.contains("proposal"):
			color = TEAL
		elif etype.contains("seat"):
			color = PURPLE
		elif etype.contains("shock"):
			color = AMBER
		var r := HBoxContainer.new()
		r.add_theme_constant_override("separation", 9)
		var railv := VBoxContainer.new()
		railv.add_child(_dot(color, 8))
		var rail := ColorRect.new()
		rail.color = Color("dbe2ea")
		rail.custom_minimum_size = Vector2(1, 10)
		rail.size_flags_vertical = Control.SIZE_EXPAND_FILL
		rail.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		railv.add_child(rail)
		r.add_child(railv)
		var col := VBoxContainer.new()
		col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var trr := HBoxContainer.new()
		trr.add_theme_constant_override("separation", 7)
		trr.add_child(_lbl(etype, 10, color))
		if mine:
			trr.add_child(_chip("我", TEAL, Color(0, 0, 0, 0), TEAL_BD, 9))
		trr.add_child(_spacer_h())
		trr.add_child(_lbl("t%s" % str(ev.get("boundary_tick", ev.get("tick", "?"))),
			9, INK3, true))
		col.add_child(trr)
		var detail := str(ev.get("status", ev.get("shock_id",
			ev.get("lever", ev.get("reason", "")))))
		if not detail.is_empty() and detail != "<null>":
			var dl := _lbl(detail, 12, Color("33424f"))
			dl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			col.add_child(dl)
		r.add_child(col)
		inner.add_child(r)


# ================= 危机遮罩 =================
func _render_crisis() -> void:
	var real_ctx := _emergency_context()
	var on := _emergency()
	if not real_ctx.is_empty() \
			and str(real_ctx.get("context_id", "")) == _crisis_dismissed:
		on = _demo_crisis
	(_n["crisis"] as Control).visible = on
	if not on:
		return
	var ctx := _emergency_context()
	var trig := str(ctx.get("emergency_trigger",
		"manual_demo" if _demo_crisis else "—"))
	_set_text("crisis_title", "紧急会议 · 触发器:%s" % trig)
	var snapcol := _n["crisis_snap"] as VBoxContainer
	for c in snapcol.get_children():
		if c is PanelContainer:
			c.queue_free()
	var by_id := _releases_by_id()
	for sid in ["unemployment_rate", "inflation", "policy_rate"]:
		var rel: Dictionary = by_id.get(sid, {})
		var rp := PanelContainer.new()
		rp.add_theme_stylebox_override("panel", _sb(RED_BG, RED_BD, 8, 8))
		var rr := HBoxContainer.new()
		rr.add_theme_constant_override("separation", 9)
		rp.add_child(rr)
		var label: String = sid
		for spec: Dictionary in TILE_SPEC:
			if str(spec["id"]) == sid:
				label = str(spec["label"])
		rr.add_child(_lbl(label, 12, Color("7a3327")))
		rr.add_child(_spacer_h())
		rr.add_child(_lbl(_fmt_series(sid, float(rel.get("value")))
			if rel.get("value") != null else "暂无", 15, RED, true))
		snapcol.add_child(rp)
	var levcol := _n["crisis_levers"] as VBoxContainer
	for c in levcol.get_children():
		if c is PanelContainer or c is Button or c is Label:
			c.queue_free()
	var ctx_perm: Dictionary = {}
	for item: Dictionary in ctx.get("permitted_actions", []):
		ctx_perm[str(item.get("lever"))] = item
	var count := 0
	for seat: String in _schemas.keys():
		for lever: Dictionary in _schemas[seat].get("levers", []):
			if count >= 2 or not bool(lever.get("emergency", false)):
				continue
			var name := str(lever.get("name"))
			var perm: Dictionary = ctx_perm.get(name, {})
			var base_v: Variant = _lever_current(lever, perm)
			if base_v == null or base_v is bool or base_v is String:
				continue
			count += 1
			var lp := PanelContainer.new()
			lp.add_theme_stylebox_override("panel", _sb(RED_BG, RED_BD, 9, 9))
			var lvv := VBoxContainer.new()
			lvv.add_theme_constant_override("separation", 6)
			lp.add_child(lvv)
			lvv.add_child(_lbl(_cn(name) + "(紧急)", 12, Color("6b2317")))
			lvv.add_child(_lever_control(lever, perm, base_v))
			levcol.add_child(lp)
	if _demo_crisis:
		levcol.add_child(_lbl("演示模式:真实紧急会议由 TriggerSpec 在边界打开(v26)。",
			10, Color("9a6a5e")))
	var submit := _btn("提交紧急处置", func() -> void:
		if _demo_crisis:
			_demo_crisis = false
			_render()
			return
		# 危机面板无「加入提案」步骤:把白名单杠杆的编辑值直接装篮提交;
		# 无编辑时等价「本次不动」,保证玩家总能走出紧急会议。
		for lname: String in _edits.keys():
			var linfo: Dictionary = _lever_info.get(lname, {})
			if bool(linfo.get("emergency", false)):
				_add_to_cart(linfo, _lever_current(linfo, {}))
		if _cart.is_empty():
			_submit_pass()
		else:
			_submit_cart())
	submit.add_theme_stylebox_override("normal", _sb(RED, Color("c23f2a"), 9, 9))
	submit.add_theme_color_override("font_color", Color.WHITE)
	levcol.add_child(submit)


# ================= 绘图控件 =================
class _SparkLine extends Control:
	var values: Array = []
	var color: Color = Color("0f9d90")

	func _draw() -> void:
		if values.size() < 2:
			return
		var lo := INF
		var hi := -INF
		for v in values:
			lo = minf(lo, float(v))
			hi = maxf(hi, float(v))
		var span := hi - lo
		if span <= 0.0:
			span = 1.0
		var pts := PackedVector2Array()
		var n := values.size()
		for i in n:
			pts.append(Vector2(
				2.0 + (size.x - 4.0) * float(i) / float(n - 1),
				size.y - 2.0 - (size.y - 4.0) * (float(values[i]) - lo) / span))
		draw_polyline(pts, color, 1.6, true)
		draw_circle(pts[n - 1], 2.4, color)


class _MultiLine extends Control:
	var series: Array = []   # [{vals, color}]

	func _draw() -> void:
		var lo := INF
		var hi := -INF
		var any := false
		for s: Dictionary in series:
			for v in s.get("vals", []):
				any = true
				lo = minf(lo, float(v))
				hi = maxf(hi, float(v))
		if not any:
			return
		var span := hi - lo
		if span <= 0.0:
			span = 1.0
		for s: Dictionary in series:
			var vals: Array = s.get("vals", [])
			if vals.size() < 2:
				continue
			var pts := PackedVector2Array()
			var n := vals.size()
			for i in n:
				pts.append(Vector2(
					2.0 + (size.x - 4.0) * float(i) / float(n - 1),
					size.y - 2.0 - (size.y - 4.0) * (float(vals[i]) - lo) / span))
			draw_polyline(pts, s.get("color", Color.GRAY), 1.5, true)


class _FocusChart extends Control:
	var series: Array = []
	var shock_active := false
	var font: Font

	func _draw() -> void:
		var plot := Rect2(Vector2(8, 8), size - Vector2(16, 30))
		for i in range(5):
			var y := plot.position.y + plot.size.y * float(i) / 4.0
			draw_line(Vector2(plot.position.x, y), Vector2(plot.end.x, y),
				Color("e6ebf1"), 1.0)
		if shock_active:
			var band := Rect2(Vector2(plot.end.x - plot.size.x * 0.25, plot.position.y),
				Vector2(plot.size.x * 0.12, plot.size.y))
			draw_rect(band, Color(0.824, 0.29, 0.204, 0.08))
			draw_string(font,
				Vector2(band.position.x + 4, plot.position.y + 14), "冲击生效中",
				HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color("cc5a44"))
		var any := false
		for s: Dictionary in series:
			var vals: Array = s.get("vals", [])
			if vals.size() < 2:
				continue
			any = true
			var lo := INF
			var hi := -INF
			for v in vals:
				lo = minf(lo, float(v))
				hi = maxf(hi, float(v))
			var span := hi - lo
			if span <= 0.0:
				span = 1.0
			var pts := PackedVector2Array()
			var n := vals.size()
			for i in n:
				pts.append(Vector2(
					plot.position.x + plot.size.x * float(i) / float(n - 1),
					plot.end.y - plot.size.y * (float(vals[i]) - lo) / span))
			draw_polyline(pts, s.get("color", Color.GRAY), float(s.get("width", 2.0)), true)
		if not any:
			draw_string(font, plot.get_center() + Vector2(-140, 0),
				"推进模拟以积累公报序列(发布日历驱动)",
				HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("60758d"))
		draw_string(font, Vector2(plot.end.x - 80, size.y - 6),
			"发布时间 →", HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color("849098"))


class _RelationsMap extends Control:
	## 三国关系图:节点三角布局 + 中心结算枢纽;
	## 实线=出口流(→枢纽),虚线=进口流(枢纽→),紫点=移民,琥珀点=汇款。
	var names: Array = []
	var colors: Array = []
	var exports: Array = []
	var imports: Array = []
	var migrants: Array = []
	var remit: Array = []
	var font: Font

	func _norm(vals: Array, i: int) -> float:
		var maxv := 0.000001
		for v in vals:
			maxv = maxf(maxv, absf(float(v)))
		if i >= vals.size():
			return 0.0
		return absf(float(vals[i])) / maxv

	func _draw() -> void:
		var n := names.size()
		if n == 0:
			return
		var center := size / 2.0
		var radius := minf(size.x, size.y) * 0.36
		var node_pos: Array = []
		for i in n:
			var angle := -PI / 2.0 + TAU * float(i) / float(n)
			node_pos.append(center + Vector2(cos(angle), sin(angle)) * radius)
		draw_circle(center, 17.0, Color("edf1f6"))
		draw_arc(center, 17.0, 0, TAU, 32, Color("cdd7e2"), 1.2, true)
		draw_string(font, center + Vector2(-11, 4), "枢纽",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color("68788b"))
		for i in n:
			var p: Vector2 = node_pos[i]
			var dir := (center - p).normalized()
			var a := p + dir * 22.0
			var b := center - dir * 20.0
			var perp := Vector2(-dir.y, dir.x)
			var wexp := 1.0 + 5.0 * _norm(exports, i)
			draw_line(a + perp * 5.0, b + perp * 5.0,
				Color(0.122, 0.616, 0.388, 0.85), wexp, true)
			var wimp := 1.0 + 5.0 * _norm(imports, i)
			var total := (b - a).length()
			var steps := maxi(1, int(total / 8.0))
			for k in steps:
				if k % 2 == 1:
					continue
				var t0 := float(k) / float(steps)
				var t1 := minf(1.0, float(k + 1) / float(steps))
				draw_line(
					(b - perp * 5.0).lerp(a - perp * 5.0, t0),
					(b - perp * 5.0).lerp(a - perp * 5.0, t1),
					Color(0.184, 0.435, 0.816, 0.7), wimp, true)
			var wm := _norm(migrants, i)
			if wm > 0.01:
				var mid := (a + b) / 2.0 + perp * 13.0
				draw_circle(mid, 2.5 + 4.0 * wm, Color(0.478, 0.31, 0.816, 0.65))
			var wr := _norm(remit, i)
			if wr > 0.01:
				var mid2 := (a + b) / 2.0 - perp * 13.0
				draw_circle(mid2, 2.0 + 3.5 * wr, Color(0.757, 0.49, 0.086, 0.7))
		for i in n:
			var p: Vector2 = node_pos[i]
			var c: Color = colors[i % colors.size()] if not colors.is_empty() else Color.GRAY
			draw_circle(p, 15.0, Color(c.r, c.g, c.b, 0.14))
			draw_circle(p, 9.0, c)
			var label := str(names[i])
			var off := Vector2(-float(label.length()) * 5.5, 30.0) \
				if p.y > center.y else Vector2(-float(label.length()) * 5.5, -22.0)
			draw_string(font, p + off, label,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color("2a3948"))
		var ly := size.y - 10.0
		draw_line(Vector2(8, ly), Vector2(26, ly), Color(0.122, 0.616, 0.388, 0.9), 2.5, true)
		draw_string(font, Vector2(30, ly + 4), "出口", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("68788b"))
		draw_line(Vector2(64, ly), Vector2(82, ly), Color(0.184, 0.435, 0.816, 0.7), 1.5, true)
		draw_string(font, Vector2(86, ly + 4), "进口", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("68788b"))
		draw_circle(Vector2(126, ly), 3.0, Color(0.478, 0.31, 0.816, 0.7))
		draw_string(font, Vector2(133, ly + 4), "移民", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("68788b"))
		draw_circle(Vector2(172, ly), 3.0, Color(0.757, 0.49, 0.086, 0.7))
		draw_string(font, Vector2(179, ly + 4), "汇款", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("68788b"))
