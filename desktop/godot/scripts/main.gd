extends Control
## 宏观指挥室 v30.2 — 政策工作台交互优化。
## 前端零经济逻辑;三国耦合世界,玩家持 0 号经济体全部 5 个席位(102 旋钮全落地)。

const SimulationClientScript = preload("res://scripts/simulation_client.gd")
const StartMenuScript = preload("res://scripts/start_menu.gd")

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
const TILE_TO_GROUP := {
	"real_output": "实体经济", "unemployment_rate": "劳动力",
	"inflation": "价格与货币", "price_index": "价格与货币",
	"policy_rate": "价格与货币", "gov_deficit_to_gdp": "财政",
	"bank_reserves_total": "银行与信贷", "poverty_rate": "分配与福利",
}

const TILE_SPEC := [
	{"id": "real_output", "label": "实际产出 · GDP", "color": TEAL, "bad_up": false, "kind": "num"},
	{"id": "unemployment_rate", "label": "失业率", "color": AMBER, "bad_up": true, "kind": "pp"},
	{"id": "inflation", "label": "通胀(每tick)", "color": PURPLE, "bad_up": true, "kind": "pp"},
	{"id": "price_index", "label": "物价指数", "color": BLUE, "bad_up": true, "kind": "num"},
	{"id": "policy_rate", "label": "政策利率", "color": TEAL, "bad_up": false, "kind": "pp"},
	{"id": "gov_deficit_to_gdp", "label": "赤字 / GDP", "color": AMBER, "bad_up": true, "kind": "pp"},
	{"id": "bank_reserves_total", "label": "银行准备金", "color": GREEN, "bad_up": false, "kind": "num"},
	{"id": "poverty_rate", "label": "贫困率", "color": PURPLE, "bad_up": true, "kind": "pp"},
]

# 八维核心指标:每个经济维度只选一个权威公报序列,不读取逐 tick 真值。
const CORE_DIMENSION_SPEC := [
	{"id": "real_output", "dimension": "增长", "metric": "实际产出", "group": "实体经济", "color": TEAL},
	{"id": "unemployment_rate", "dimension": "就业", "metric": "失业率", "group": "劳动力", "color": AMBER},
	{"id": "inflation", "dimension": "物价", "metric": "通胀", "group": "价格与货币", "color": PURPLE},
	{"id": "gov_deficit_to_gdp", "dimension": "财政", "metric": "赤字/GDP", "group": "财政", "color": BLUE},
	{"id": "credit_to_gdp", "dimension": "金融", "metric": "信贷/GDP", "group": "银行与信贷", "color": TEAL_DK},
	{"id": "poverty_rate", "dimension": "民生", "metric": "贫困率", "group": "分配与福利", "color": GREEN},
	{"id": "population_alive", "dimension": "人口", "metric": "总人口", "group": "人口与企业", "color": Color("b0641f")},
	{"id": "current_account", "dimension": "外部", "metric": "经常账户", "tab": "world", "color": Color("4a6fa5")},
]

const SEAT_LIST := [
	{"id": "treasury", "name": "财政部", "tag": "财政 · fiscal", "color": Color("2f6fd0")},
	{"id": "central_bank", "name": "央行", "tag": "货币 · monetary", "color": Color("0f9d90")},
	{"id": "regulator", "name": "监管", "tag": "审慎 · prudential", "color": Color("7a4fd0")},
	{"id": "external_affairs", "name": "外交贸易", "tag": "对外 · external", "color": Color("c17d16")},
	{"id": "energy", "name": "能源", "tag": "能源 · energy", "color": Color("b0641f")},
]

const GROUP_CN := {
	"fiscal_stance": "财政立场", "tax_and_transfers": "税收与转移",
	"debt_management": "债务管理", "monetary_stance": "货币立场",
	"liquidity_operations": "流动性操作", "fx_operations": "外汇操作",
	"macroprudential": "宏观审慎", "structural_law": "结构性法规",
	"trade_and_migration": "贸易与移民", "energy_operations": "能源操作",
	"energy_structure": "能源结构",
}

# 政策值只做呈现层转换；提交仍使用 Registry 给出的 canonical 值。
const CHOICE_CN := {
	"monetary_regime": {"exogenous": "外生利率", "taylor": "泰勒规则", "manual": "手动设定"},
	"fx_regime": {"float": "浮动汇率", "peg": "联系汇率"},
	"energy_rationing": {
		"market": "市场出清", "household_first": "居民优先",
		"industry_first": "产业优先", "proportional": "等比例配给"},
}

const PERCENT_LEVERS := {
	"gov_consumption_share": true, "gov_deficit_target": true,
	"gov_investment_share": true, "deficit_u_ref": true,
	"benefit_replacement": true, "pension_replacement": true,
	"jg_wage_ratio": true, "jg_public_works_share": true,
	"tax_income_rate": true, "tax_profit_rate": true,
	"tax_consumption_rate": true, "tax_wealth_rate": true,
	"tax_luxury_rate": true, "tax_necessity_rate": true,
	"tax_energy_rate": true, "tax_energy_windfall": true,
	"housing_property_tax": true, "housing_transfer_tax": true,
	"land_fee_share": true, "energy_subsidy_rate": true,
	"bond_coupon": true, "bond_finance_frac": true,
	"inflation_target": true, "manual_policy_rate": true,
	"r_neutral": true, "r_max": true, "u_natural": true,
	"rate_inertia": true, "infl_ema_lambda": true,
	"omo_reserve_target": true, "omo_drain_frac": true,
	"reserve_floor_frac": true, "capital_control": true,
	"external_interest_settlement_fraction": true,
	"bank_target_capital_ratio": true, "bank_exposure_limit": true,
	"deposit_rate_floor": true, "mortgage_ltv_cap": true,
	"mortgage_dsti_cap": true, "mortgage_risk_weight": true,
	"mortgage_stress_rate_addon": true,
	"mortgage_min_capital_ratio": true, "margin_ltv": true,
	"regulatory_firm_capital_haircut": true,
	"regulatory_firm_inventory_haircut": true,
	"mortgage_foreclosure_ltv": true, "tariff": true,
	"import_quota": true, "export_subsidy": true,
	"immigration_cap": true, "emigration_cap": true,
	"guest_worker_return": true, "remittance_tax": true,
	"outward_remittance_tax": true,
}

const MULTIPLIER_LEVERS := {
	"deficit_u_cap": true, "benefit_income_floor": true,
	"income_allowance": true, "wealth_allowance": true,
	"energy_subsidy_threshold": true, "land_fee_stock_elasticity": true,
	"taylor_phi_pi": true, "taylor_phi_u": true,
	"bank_leverage_cap": true, "firm_credit_min_dscr": true,
	"hh_credit_limit": true, "kappa": true, "margin_max": true,
}

const DAY_LEVERS := {
	"bond_maturity": true, "bankrupt_persist": true,
	"rental_eviction_arrears": true,
}

const CAPABILITY_CN := {
	"bank_enabled": "银行体系", "bank_realized_pnl": "银行完整损益",
	"bonds": "国债市场", "consumption_strata": "必需品 / 奢侈品分层",
	"energy_enabled": "能源部门", "energy_household": "居民能源消费",
	"government": "政府财政账户", "household_credit": "家庭信贷",
	"housing_construction_enabled": "住房建造", "housing_enabled": "住房登记",
	"housing_market_enabled": "住房交易市场", "interbank": "银行间市场",
	"margin_credit": "保证金信贷", "mortgage_enabled": "住房按揭",
	"omo": "公开市场操作", "soe_efirm": "国有能源企业",
	"coupling": "跨境耦合", "multiple_economies": "多国世界",
	"trade": "国际贸易", "capital": "跨境资本", "migration": "跨境迁移",
	"cross_border_flow": "至少一种跨境流动",
}

const EVENT_TITLES := {
	"decision_context_opened": "政策会议召开",
	"human_proposal_queued": "玩家提案已递交",
	"human_proposal_collected": "玩家提案已汇总",
	"decision_accepted_noop": "会议决定维持现状",
	"decision_accepted_pending": "政策提案获准",
	"decision_accepted": "政策提案获准",
	"decision_rejected": "政策提案被否决",
	"decision_effective": "政策正式生效",
	"decision_cancelled": "待生效政策已撤销",
	"emergency_trigger": "风险警报触发",
	"seat_assignment": "政策席位完成交接",
	"seat_assigned": "政策席位完成交接",
	"shock_announced": "外生冲击预告",
	"shock_started": "外生冲击开始",
	"shock_ended": "外生冲击结束",
}

const REASON_CN := {
	"no_change": "本届会议未调整政策",
	"accepted": "提案通过权威校验",
	"bank_capital_stress": "银行资本压力超过风险阈值",
	"energy_shortage": "能源供应缺口超过风险阈值",
	"liquidity_stress": "银行体系流动性承压",
	"inflation_stress": "通胀偏离政策目标",
	"unemployment_stress": "失业率触发紧急阈值",
	"energy_stress": "能源供给触发紧急阈值",
}

# 二级页:主题化拆分,每页 ≤8 个旋钮；收起态优先单屏浏览。
# 未列入的新旋钮自动落入该席位「其他」页。
const LEVER_PAGES := {
	"treasury": [
		{"name": "预算与赤字", "levers": ["gov_consumption_share", "gov_deficit_target",
			"gov_investment_share", "deficit_u_cap", "deficit_u_ref",
			"fiscal_uses_national_accounts_gdp"]},
		{"name": "就业与保障", "levers": ["job_guarantee", "jg_wage_ratio",
			"jg_public_works_share", "benefit_replacement", "benefit_income_floor",
			"pension_replacement", "housing_permits"]},
		{"name": "核心税率", "levers": ["tax_income_rate", "tax_profit_rate",
			"tax_consumption_rate", "tax_wealth_rate", "tax_luxury_rate",
			"tax_necessity_rate", "tax_energy_rate", "tax_energy_windfall"]},
		{"name": "起征与住房土地", "levers": ["income_allowance", "wealth_allowance",
			"housing_in_wealth_tax", "housing_property_tax", "housing_transfer_tax",
			"land_fee_share", "land_fee_stock_elasticity"]},
		{"name": "补贴与工资", "levers": ["min_wage", "energy_subsidy_rate",
			"energy_subsidy_threshold", "energy_cap_compensation"]},
		{"name": "债务管理", "levers": ["bond_coupon", "bond_finance_frac",
			"bond_maturity"]},
	],
	"central_bank": [
		{"name": "利率规则", "levers": ["monetary_regime", "manual_policy_rate",
			"r_neutral", "r_max", "rate_inertia", "taylor_phi_pi", "taylor_phi_u"]},
		{"name": "通胀目标与口径", "levers": ["inflation_target", "infl_ema_lambda",
			"u_natural", "cb_core_inflation", "cb_log_inflation",
			"cb_uses_fixed_basket_cpi"]},
		{"name": "流动性操作", "levers": ["omo", "omo_reserve_target",
			"omo_index_deposits", "omo_drain_frac", "reserve_floor_frac", "lolr"]},
		{"name": "外汇操作", "levers": ["fx_regime", "peg_anchor", "peg_reserve_scale",
			"capital_control", "external_interest_settlement_fraction"]},
	],
	"regulator": [
		{"name": "银行审慎", "levers": ["bank_min_capital", "bank_target_capital_ratio",
			"bank_capital_constraint", "bank_leverage_cap", "bank_exposure_limit",
			"bank_bond_duration_limit", "bank_migrate_on_failure"]},
		{"name": "按揭与住房", "levers": ["mortgage_ltv_cap", "mortgage_dsti_cap",
			"mortgage_risk_weight", "mortgage_stress_rate_addon",
			"mortgage_min_capital_ratio", "mortgage_underwriting"]},
		{"name": "信贷与杠杆", "levers": ["kappa", "hh_credit_limit",
			"firm_credit_min_dscr", "deposit_rate_floor", "margin_ltv", "margin_max",
			"regulatory_firm_capital_haircut", "regulatory_firm_inventory_haircut"]},
		{"name": "结构性法规", "levers": ["household_bankruptcy", "bankrupt_persist",
			"bank_resolution_fund", "unified_bank_rwa", "mortgage_arrears_floor",
			"mortgage_foreclosure_ltv", "rental_eviction_arrears"]},
	],
	"external_affairs": [
		{"name": "贸易壁垒", "levers": ["tariff", "import_quota", "export_subsidy",
			"sanctions_imposed_on"]},
		{"name": "移民与汇款", "levers": ["immigration_cap", "emigration_cap",
			"guest_worker_return", "remittance_tax", "outward_remittance_tax"]},
	],
	"energy": [
		{"name": "能源操作与结构", "levers": ["energy_price_cap", "energy_rationing",
			"spr_target_units", "spr_flow_cap", "soe_price_at_cost", "soe_efirm"]},
	],
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
var _active_group := ""                # 二级主题页名(空=该席位第一页)
var _expanded_lever := ""              # 手风琴:当前展开的旋钮
var _search := ""
var _policy_scope := "meeting"         # meeting | all；闭会时自动显示全部
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
var _focus_extra := "policy_rate"      # 默认高频序列,早期也能形成可读主图
var _goto_panel_group := ""            # 磁贴点击 -> 全景滚动目标
var _event_filter := "important"       # important | all | mine
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
var _last_tab := ""
var _last_seat := ""
var _last_page := ""
var _last_release_at: Dictionary = {}   # sid -> released_at(磁贴闪光判定)
var _crisis_was_visible := false
var _scroll_mem: Dictionary = {}        # key -> scroll_vertical
var _start_menu: Control
var _new_game_draft: Dictionary = {}


func _ready() -> void:
	_sans = SystemFont.new()
	_sans.font_names = PackedStringArray([
		"Hiragino Sans GB", "STHeiti", "Arial Unicode MS", "Helvetica Neue"])
	_mono = SystemFont.new()
	_mono.font_names = PackedStringArray(["Menlo", "Monaco"])
	_mono.fallbacks = [_sans]
	_build_theme()
	_build_ui()
	if OS.get_environment("MACRO_SIM_SKIP_START_MENU") != "1":
		_start_menu = StartMenuScript.new()
		_start_menu.launch_requested.connect(_on_start_menu_launch)
		_start_menu.continue_requested.connect(func() -> void:
			_playing = false)
		add_child(_start_menu)
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
	if OS.get_environment("MACRO_SIM_CAPTURE_CRISIS") == "1":
		_demo_crisis = true
	var pre := OS.get_environment("MACRO_SIM_CAPTURE_TICKS")
	if pre.is_valid_int():
		_capture_ticks = pre.to_int()
	var pre_tab := OS.get_environment("MACRO_SIM_CAPTURE_TAB")
	if not pre_tab.is_empty():
		_tab = pre_tab
	var pre_seat := OS.get_environment("MACRO_SIM_CAPTURE_SEAT")
	if not pre_seat.is_empty():
		_active_seat = pre_seat
	var pre_lever := OS.get_environment("MACRO_SIM_CAPTURE_LEVER")
	if not pre_lever.is_empty():
		_expanded_lever = pre_lever


func _unhandled_input(event: InputEvent) -> void:
	if _start_menu != null and _start_menu.visible:
		return
	if not (event is InputEventKey):
		return
	var key := event as InputEventKey
	if not key.pressed or key.echo:
		return
	match key.keycode:
		KEY_SPACE:
			_toggle_play()
		KEY_RIGHT, KEY_PERIOD:
			if _awaiting():
				_show_hint("本届会议未闭合:请「提交提案」或「本次不动」。")
				_render()
			else:
				_send({"command": "advance", "ticks": 1})
		KEY_1, KEY_2, KEY_3, KEY_4:
			_speed = SPEEDS[key.keycode - KEY_1]
			_render()
		KEY_G:
			(_n["god_cb"] as Button).button_pressed = not _god
		KEY_N:
			_advance_to_next_decision()
		KEY_ESCAPE:
			if _demo_crisis:
				_demo_crisis = false
				_render()


func _on_start_menu_launch(config: Dictionary) -> void:
	_playing = false
	var draft: Dictionary = config.get("draft", {})
	_new_game_draft = draft.duplicate(true)
	_mode = str(draft.get("run_mode", "interactive"))
	if _mode not in ["interactive", "realtime"]:
		_mode = "interactive"
	_send({"command": "new_game", "seed": int(config.get("seed", 7))})


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
		var splash := _n.get("splash") as Control
		if splash != null and splash.visible:
			var stw2 := create_tween()
			stw2.tween_property(splash, "modulate:a", 0.0, 0.35)
			stw2.tween_callback(func() -> void:
				splash.visible = false)
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
	# Dynamic panels rebuild with queue_free; wait long enough for two layout passes
	# so automated captures reflect the settled UI rather than an empty interim frame.
	await get_tree().create_timer(0.8).timeout
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


func _seat_pages(seat: String) -> Array:
	## 主题页定义 + 该席位未收录旋钮兜底成「其他」页;返回 [{name, levers:[lever dict]}]
	var by_name: Dictionary = {}
	for lever: Dictionary in _schemas.get(seat, {}).get("levers", []):
		by_name[str(lever.get("name"))] = lever
	var out: Array = []
	var used: Dictionary = {}
	for pg: Dictionary in LEVER_PAGES.get(seat, []):
		var levers: Array = []
		for lname in pg["levers"]:
			if by_name.has(str(lname)):
				levers.append(by_name[str(lname)])
				used[str(lname)] = true
		if not levers.is_empty():
			out.append({"name": pg["name"], "levers": levers})
	var leftover: Array = []
	for lname: String in by_name.keys():
		if not used.has(lname):
			leftover.append(by_name[lname])
	if not leftover.is_empty():
		out.append({"name": "其他", "levers": leftover})
	return out


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


func _flag(i: int, fsize := Vector2(18, 12)) -> Control:
	var c := Control.new()
	c.custom_minimum_size = fsize
	c.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var color: Color = ECON_COLORS[i % 3]
	c.draw.connect(func() -> void:
		c.draw_rect(Rect2(Vector2.ZERO, Vector2(fsize.x, fsize.y * 0.62)), color)
		c.draw_rect(Rect2(Vector2(0, fsize.y * 0.62),
			Vector2(fsize.x, fsize.y * 0.38)), color.lightened(0.55))
		c.draw_rect(Rect2(Vector2.ZERO, fsize), Color(0, 0, 0, 0.10), false, 1.0))
	return c


func _cn(lever_name: String) -> String:
	return str(LEVER_CN.get(lever_name, lever_name))


func _choice_text(lever_name: String, value: Variant) -> String:
	var labels: Dictionary = CHOICE_CN.get(lever_name, {})
	return str(labels.get(str(value), str(value)))


func _permission_reason(reason_code: String) -> String:
	if reason_code.begins_with("missing_capability:"):
		var capability := reason_code.trim_prefix("missing_capability:")
		return "需要先在开局结构中启用“%s”" % str(CAPABILITY_CN.get(capability, capability))
	if reason_code.begins_with("missing_world_capability:"):
		var capability := reason_code.trim_prefix("missing_world_capability:")
		return "当前世界未启用“%s”" % str(CAPABILITY_CN.get(capability, capability))
	if reason_code.begins_with("disabled_prerequisite:"):
		var prerequisite := reason_code.trim_prefix("disabled_prerequisite:")
		return "需先启用政策“%s”" % _cn(prerequisite)
	return {
		"pending_conflict": "该政策已有等待生效的决定",
		"minimum_hold": "仍在最短持有期 / 冷却期内",
		"admin_capacity_exceeded": "本决策窗口的行政容量不足",
		"joint_constraint:peg_unavailable": "当前没有合法的联系汇率锚国，或已有其他挂钩国",
		"joint_constraint:no_valid_peg_anchor": "当前没有可用的浮动汇率锚国",
	}.get(reason_code, reason_code.replace("_", " "))


func _seat_color(seat: String) -> Color:
	for spec: Dictionary in SEAT_LIST:
		if str(spec.get("id")) == seat:
			return spec.get("color", TEAL)
	return TEAL


func _cart_entry(lever_name: String) -> Dictionary:
	for item: Dictionary in _cart:
		if str(item.get("lever")) == lever_name:
			return item
	return {}


func _cart_has(lever_name: String) -> bool:
	return not _cart_entry(lever_name).is_empty()


func _reset_lever_draft(lever_name: String) -> void:
	_cart = _cart.filter(func(item: Dictionary) -> bool:
		return str(item.get("lever")) != lever_name)
	_edits.erase(lever_name)
	_render()


func _stage_lever_edit(lever: Dictionary, value: Variant) -> void:
	var lever_name := str(lever.get("name"))
	var semantics := str(lever.get("semantics",
		lever.get("effective_semantics", "")))
	if semantics.contains("transition"):
		_confirm = {
			"title": "制度迁移确认",
			"body": "将「%s」调整为“%s”会切换制度分支，并按较高成本计费。是否保留为本次草稿？" % [
				_cn(lever_name), _lever_value_text(lever, value)],
			"note": "成本类 · 高 · 通过后 %d 天生效" % int(lever.get("implementation_lag", 0)),
			"on_yes": func() -> void:
				_edits[lever_name] = value
				_render(),
		}
		_render()
	else:
		_edits[lever_name] = value
		_render()


func _focus_lever(lever_name: String) -> void:
	var info: Dictionary = _lever_info.get(lever_name, {})
	if info.is_empty():
		return
	_active_seat = str(info.get("owner_role", _active_seat))
	for page: Dictionary in _seat_pages(_active_seat):
		for page_lever: Dictionary in page["levers"]:
			if str(page_lever.get("name")) == lever_name:
				_active_group = str(page["name"])
				break
	_expanded_lever = lever_name
	_search = ""
	(_n["search"] as LineEdit).text = ""
	# 从提案篮返回编辑时，确保该项不被“仅本会议题”过滤掉。
	if _context_for_group(str(info.get("decision_group", ""))).is_empty():
		_policy_scope = "all"
	_render()


func _country_name(i: int) -> String:
	var countries: Array = _world().get("countries", [])
	if i >= 0 and i < countries.size():
		return str((countries[i] as Dictionary).get("name", "经济体%d" % i))
	return "经济体%d" % i


func _seat_name(seat: String) -> String:
	for spec: Dictionary in SEAT_LIST:
		if str(spec.get("id")) == seat:
			return str(spec.get("name"))
	return seat


func _event_group(event: Dictionary) -> String:
	var payload: Dictionary = event.get("payload", {})
	var group := str(payload.get("decision_group", ""))
	if group.is_empty():
		var context_id := str(event.get("context_id", ""))
		var parts := context_id.split(":")
		if parts.size() > 3:
			group = parts[3]
	return str(GROUP_CN.get(group, "紧急处置" if group == "emergency" else group))


func _event_title(event_type: String) -> String:
	if EVENT_TITLES.has(event_type):
		return str(EVENT_TITLES[event_type])
	if event_type.begins_with("shock_"):
		return "外生冲击动态"
	if event_type.begins_with("decision_"):
		return "政策裁决更新"
	if event_type.begins_with("policy_") or event_type.contains("transaction"):
		return "政策执行更新"
	return event_type.replace("_", " ").capitalize()


func _event_detail(event: Dictionary, event_type: String) -> String:
	var parts: Array[String] = []
	var seat := str(event.get("seat", ""))
	if not seat.is_empty() and seat != "<null>":
		parts.append(_seat_name(seat))
	var group := _event_group(event)
	if not group.is_empty():
		parts.append(group)
	var reason := str(event.get("reason", ""))
	if not reason.is_empty() and reason != "<null>":
		parts.append(str(REASON_CN.get(reason, reason.replace("_", " "))))
	elif event_type.begins_with("shock_"):
		var shock_id := str(event.get("shock_id", ""))
		if not shock_id.is_empty() and shock_id != "<null>":
			parts.append(shock_id)
	elif event.get("lever") != null:
		parts.append(_cn(str(event.get("lever"))))
	return " · ".join(parts)


func _event_is_important(event_type: String) -> bool:
	if event_type == "decision_accepted_noop":
		return false
	return event_type == "emergency_trigger" \
		or event_type.begins_with("shock_") \
		or event_type.begins_with("policy_") \
		or event_type.contains("effective") \
		or event_type.contains("rejected") \
		or event_type.contains("failed") \
		or event_type.contains("cancel") \
		or event_type.contains("pending") \
		or event_type.contains("committed")


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
	t.set_stylebox("panel", "PanelContainer", _sb(PANEL, LINE, 13, 12, 10))
	theme = t


func _sb(bg: Color, border: Color, radius: int, margin: int,
		shadow := 0) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(1)
	s.set_corner_radius_all(radius)
	s.set_content_margin_all(margin)
	if shadow > 0:
		s.shadow_color = Color(0.09, 0.14, 0.20, 0.10)
		s.shadow_size = shadow
		s.shadow_offset = Vector2(0, shadow / 3.0)
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


func _fade_in(node: Control) -> void:
	node.modulate.a = 0.0
	var tw := create_tween()
	tw.tween_property(node, "modulate:a", 1.0, 0.16)\
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)


func _keep_scroll(key: String, scroll: ScrollContainer) -> void:
	## 重建前调用:记录;重建后 restore(延迟一帧生效)
	_scroll_mem[key] = scroll.scroll_vertical


func _restore_scroll(key: String, scroll: ScrollContainer) -> void:
	if _scroll_mem.has(key):
		scroll.set_deferred("scroll_vertical", int(_scroll_mem[key]))


func _apply_cursors(node: Node) -> void:
	if node is Button or node is CheckBox or node is CheckButton or node is LineEdit:
		(node as Control).mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	for child in node.get_children():
		_apply_cursors(child)


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
		"unemployment_rate", "gov_deficit_to_gdp", "gov_debt_to_gdp", \
				"credit_to_gdp", "poverty_rate":
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
	var glow := TextureRect.new()
	var grad := Gradient.new()
	grad.colors = PackedColorArray([Color(1, 1, 1, 0.85), Color(1, 1, 1, 0.0)])
	grad.offsets = PackedFloat32Array([0.0, 1.0])
	var gtex := GradientTexture2D.new()
	gtex.gradient = grad
	gtex.fill = GradientTexture2D.FILL_RADIAL
	gtex.fill_from = Vector2(0.5, 0.28)
	gtex.fill_to = Vector2(0.5, 1.0)
	gtex.width = 512
	gtex.height = 512
	glow.texture = gtex
	glow.stretch_mode = TextureRect.STRETCH_SCALE
	glow.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	glow.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(glow)
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
	var splash := ColorRect.new()
	splash.color = GROUND
	splash.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_n["splash"] = splash
	add_child(splash)
	var sv := VBoxContainer.new()
	sv.set_anchors_preset(Control.PRESET_CENTER)
	sv.position = Vector2(-140, -70)
	sv.add_theme_constant_override("separation", 16)
	sv.alignment = BoxContainer.ALIGNMENT_CENTER
	splash.add_child(sv)
	var st := HBoxContainer.new()
	st.add_theme_constant_override("separation", 10)
	st.alignment = BoxContainer.ALIGNMENT_CENTER
	st.add_child(_dot(TEAL, 11.0))
	st.add_child(_lbl("宏观指挥室", 26, INK))
	sv.add_child(st)
	var sub := _lbl("MACRO COMMAND · 三国耦合世界", 12, Color("68788b"), true)
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sv.add_child(sub)
	var spin := _Spinner.new()
	spin.custom_minimum_size = Vector2(30, 30)
	spin.pivot_offset = Vector2(15, 15)
	spin.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	sv.add_child(spin)
	var stw := create_tween().set_loops()
	stw.tween_property(spin, "rotation", TAU, 1.1).from(0.0)
	var sload := _lbl("连接引擎中 · 创世三国经济体…", 12, INK2)
	sload.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sv.add_child(sload)


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
	tbox.add_child(_dot(TEAL, 9.0))
	tbox.add_child(_lbl("宏观指挥室", 17, INK))
	tbox.add_child(_lbl("MACRO COMMAND · v29", 11, Color("68788b"), true))
	var op := PanelContainer.new()
	op.add_theme_stylebox_override("panel", _sb(TEAL_BG, TEAL_BD, 20, 5))
	var online := HBoxContainer.new()
	online.add_theme_constant_override("separation", 6)
	op.add_child(online)
	var live_dot := _dot(TEAL)
	online.add_child(live_dot)
	var breath := create_tween().set_loops()
	breath.tween_property(live_dot, "modulate:a", 0.35, 0.9)\
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	breath.tween_property(live_dot, "modulate:a", 1.0, 0.9)\
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
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
	var yb := _YearBar.new()
	yb.custom_minimum_size = Vector2(150, 5)
	_n["yearbar"] = yb
	clock.add_child(yb)
	h.add_child(clock)
	var waitp := PanelContainer.new()
	waitp.add_theme_stylebox_override("panel", _sb(AMBER_BG, AMBER_BD, 20, 5))
	var wbx := HBoxContainer.new()
	wbx.add_theme_constant_override("separation", 7)
	waitp.add_child(wbx)
	var wdot := _dot(AMBER)
	var wtw := create_tween().set_loops()
	wtw.tween_property(wdot, "modulate:a", 0.3, 0.55).set_trans(Tween.TRANS_SINE)
	wtw.tween_property(wdot, "modulate:a", 1.0, 0.55).set_trans(Tween.TRANS_SINE)
	wbx.add_child(wdot)
	wbx.add_child(_lbl("等待决策", 12, AMBER))
	_n["awaitchip"] = waitp
	h.add_child(waitp)
	h.add_child(_spacer_h())
	var modes_wrap := PanelContainer.new()
	modes_wrap.add_theme_stylebox_override("panel", _sb(PANEL2, LINE, 22, 3))
	var modes := HBoxContainer.new()
	modes.add_theme_constant_override("separation", 2)
	modes_wrap.add_child(modes)
	for m: Array in [["interactive", "交互"], ["realtime", "实时"]]:
		var mb := Button.new()
		mb.text = m[1]
		mb.tooltip_text = "交互:每逢会议暂停等你决策\n实时:播放中自动通过非紧急会议" 
		var mid: String = m[0]
		mb.pressed.connect(func() -> void:
			if mid == "realtime" and _mode != "realtime":
				_show_hint("实时模式:播放中将自动通过非紧急会议(待生效政策不受影响);紧急会议仍会暂停。")
			_mode = mid
			_render())
		_n["mode_" + mid] = mb
		modes.add_child(mb)
	h.add_child(modes_wrap)
	var god := Button.new()
	god.toggle_mode = true
	god.text = "上帝模式"
	god.tooltip_text = "显示逐 tick 真值(快捷键 G)"
	god.add_theme_font_size_override("font_size", 12)
	god.toggled.connect(func(v: bool) -> void:
		_god = v
		_render())
	_n["god_cb"] = god
	h.add_child(god)
	h.add_child(_vdiv())
	var transport := PanelContainer.new()
	transport.add_theme_stylebox_override("panel", _sb(PANEL2, LINE, 22, 4))
	var tp := HBoxContainer.new()
	tp.add_theme_constant_override("separation", 4)
	transport.add_child(tp)
	var stepb := _btn("步进", func() -> void:
		if _awaiting():
			_show_hint("本届会议未闭合,推进被暂停:请「提交提案」或「本次不动」;紧急会议在红色面板里处置。切到「实时」模式可自动通过非紧急会议。")
			_render()
		else:
			_send({"command": "advance", "ticks": 1}))
	stepb.tooltip_text = "推进 1 天(快捷键 →)"
	tp.add_child(stepb)
	var play := _btn("▶  播放", _toggle_play, true)
	play.tooltip_text = "播放 / 暂停(空格)"
	play.custom_minimum_size = Vector2(96, 0)
	_n["play"] = play
	tp.add_child(play)
	for s: int in SPEEDS:
		var sbn := Button.new()
		sbn.text = "%d×" % s
		sbn.add_theme_font_override("font", _mono)
		sbn.add_theme_font_size_override("font_size", 12)
		sbn.tooltip_text = "推进速度(快捷键 1-4)"
		var chosen := s
		sbn.pressed.connect(func() -> void:
			_speed = chosen
			_render())
		_n["speed_%d" % s] = sbn
		tp.add_child(sbn)
	h.add_child(transport)


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
	# 政策编辑是主玩法，给中文名称、状态和精确输入留出稳定宽度。
	wbp.custom_minimum_size = Vector2(440, 0)
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
	tlp.custom_minimum_size = Vector2(330, 0)
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
	head.add_theme_constant_override("separation", 7)
	hp.add_child(head)
	var title_row := HBoxContainer.new()
	title_row.add_child(_lbl("POLICY DESK · 政策工作台", 10, INK3, true))
	title_row.add_child(_spacer_h())
	var seat_brief := _lbl("", 9, INK3, true)
	_n["seat_brief"] = seat_brief
	title_row.add_child(seat_brief)
	head.add_child(title_row)
	var chips := HBoxContainer.new()
	chips.add_theme_constant_override("separation", 5)
	for s: Dictionary in SEAT_LIST:
		var b := Button.new()
		b.text = str(s["name"])
		b.add_theme_font_size_override("font_size", 12)
		var sid := str(s["id"])
		b.pressed.connect(func() -> void:
			_active_seat = sid
			_active_group = ""
			_expanded_lever = ""
			_render())
		_n["seat_" + sid] = b
		chips.add_child(b)
	head.add_child(chips)
	wb.add_child(_hrule())
	var mp := MarginContainer.new()
	mp.add_theme_constant_override("margin_left", 13)
	mp.add_theme_constant_override("margin_top", 6)
	mp.add_theme_constant_override("margin_bottom", 2)
	wb.add_child(mp)
	var meet := _lbl("", 11, INK2)
	_n["meeting"] = meet
	mp.add_child(meet)
	var sm := MarginContainer.new()
	sm.add_theme_constant_override("margin_left", 13)
	sm.add_theme_constant_override("margin_right", 13)
	sm.add_theme_constant_override("margin_top", 4)
	wb.add_child(sm)
	var search_row := HBoxContainer.new()
	search_row.add_theme_constant_override("separation", 6)
	sm.add_child(search_row)
	var search := LineEdit.new()
	search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search.clear_button_enabled = true
	search.placeholder_text = "搜索全部席位的政策…"
	search.add_theme_font_size_override("font_size", 12)
	search.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 8, 6))
	search.add_theme_stylebox_override("focus", _sb(Color.WHITE, TEAL_BD, 8, 6))
	search.text_changed.connect(func(text: String) -> void:
		_search = text.strip_edges()
		_render())
	_n["search"] = search
	search_row.add_child(search)
	var scope := Button.new()
	scope.text = "本会议题"
	scope.tooltip_text = "切换当前席位的本会议题 / 全部政策"
	scope.add_theme_font_size_override("font_size", 11)
	scope.pressed.connect(func() -> void:
		_policy_scope = "all" if _policy_scope == "meeting" else "meeting"
		_expanded_lever = ""
		_render())
	_n["policy_scope"] = scope
	search_row.add_child(scope)
	var gm2 := MarginContainer.new()
	gm2.add_theme_constant_override("margin_left", 13)
	gm2.add_theme_constant_override("margin_right", 13)
	gm2.add_theme_constant_override("margin_top", 5)
	wb.add_child(gm2)
	var gflow := HFlowContainer.new()
	gflow.add_theme_constant_override("h_separation", 4)
	gflow.add_theme_constant_override("v_separation", 4)
	_n["group_chips"] = gflow
	gm2.add_child(gflow)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	wb.add_child(scroll)
	var lv := VBoxContainer.new()
	lv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lv.add_theme_constant_override("separation", 11)
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
	crow.add_child(_lbl("提案篮", 10, INK3, true))
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
	var seg := PanelContainer.new()
	seg.add_theme_stylebox_override("panel", _sb(PANEL2, LINE, 22, 3))
	var segh := HBoxContainer.new()
	segh.add_theme_constant_override("separation", 2)
	seg.add_child(segh)
	for t: Array in [["focus", "宏观焦点"], ["panels", "指标全景"], ["world", "世界视图"]]:
		var b := Button.new()
		b.text = t[1]
		var tid: String = t[0]
		b.pressed.connect(func() -> void:
			_tab = tid
			_render())
		_n["tab_" + tid] = b
		segh.add_child(b)
	tabs.add_child(seg)
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
	filter.text = "重点事件"
	filter.add_theme_font_size_override("font_size", 11)
	filter.tooltip_text = "切换:重点事件 / 全部记录 / 我的操作"
	filter.pressed.connect(func() -> void:
		match _event_filter:
			"important": _event_filter = "all"
			"all": _event_filter = "mine"
			_: _event_filter = "important"
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
	var crisis_center := CenterContainer.new()
	crisis_center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	crisis.add_child(crisis_center)
	var cp := PanelContainer.new()
	cp.add_theme_stylebox_override("panel", _sb(Color("fdeae4"), Color("e79b86"), 16, 0))
	cp.custom_minimum_size = Vector2(1040, 0)
	crisis_center.add_child(cp)
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
	var modal_center := CenterContainer.new()
	modal_center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	modal.add_child(modal_center)
	var mp := PanelContainer.new()
	mp.add_theme_stylebox_override("panel", _sb(Color("f6f8fb"), Color("cdd7e2"), 14, 18))
	mp.custom_minimum_size = Vector2(440, 0)
	modal_center.add_child(mp)
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
	var yb := _n["yearbar"] as _YearBar
	yb.frac = float(t % 365) / 365.0
	yb.queue_redraw()
	(_n["awaitchip"] as Control).visible = _awaiting()
	var playb := _n["play"] as Button
	playb.text = "⏸  暂停" if _playing else "▶  播放"
	if _playing:
		playb.add_theme_stylebox_override("normal", _sb(TEAL, Color("0c8579"), 8, 7))
		playb.add_theme_color_override("font_color", Color.WHITE)
	else:
		playb.add_theme_stylebox_override("normal", _sb(TEAL_BG, Color("59b7a8"), 8, 7))
		playb.add_theme_color_override("font_color", TEAL_DK)
	var godb := _n["god_cb"] as Button
	if _god:
		godb.add_theme_stylebox_override("normal", _sb(
			Color(0.478, 0.31, 0.816, 0.14), PURPLE, 20, 6))
		godb.add_theme_color_override("font_color", Color("5a36a8"))
		godb.text = "◉ 上帝模式"
	else:
		godb.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 20, 6))
		godb.add_theme_color_override("font_color", Color("586a7b"))
		godb.text = "○ 上帝模式"
	for m in ["interactive", "realtime"]:
		var mb := _n["mode_" + m] as Button
		if m == _mode:
			mb.add_theme_stylebox_override("normal", _sb(Color.WHITE, TEAL_BD, 18, 6, 5))
			mb.add_theme_color_override("font_color", TEAL_DK)
		else:
			mb.add_theme_stylebox_override("normal", _sb(Color(1, 1, 1, 0), Color(0, 0, 0, 0), 18, 6))
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
			tb.add_theme_stylebox_override("normal", _sb(Color.WHITE, BLUE_BD, 18, 7, 5))
			tb.add_theme_color_override("font_color", Color("1c4a8f"))
		else:
			tb.add_theme_stylebox_override("normal", _sb(Color(1, 1, 1, 0), Color(0, 0, 0, 0), 18, 7))
			tb.add_theme_color_override("font_color", Color("586a7b"))
	_set_text("tabnote", "X 轴 = 发布时间(非参考期)" if _tab == "focus"
		else "上帝视角 · 逐 tick 真值(公报另见磁贴)")
	(_n["filter"] as Button).text = {
		"important": "重点事件", "all": "全部记录", "mine": "我的操作",
	}.get(_event_filter, "重点事件")
	_render_tiles()
	_render_workbench()
	_render_center()
	_render_events()
	_render_crisis()
	if _tab != _last_tab:
		_fade_in(_n["center_body"] as Control)
		_last_tab = _tab
	if _active_seat != _last_seat or _active_group != _last_page:
		_fade_in(_n["levers"] as Control)
		_last_seat = _active_seat
		_last_page = _active_group
	_apply_cursors(self)
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
		var trest := _sb(PANEL, LINE, 12, 11, 6)
		var thover := _sb(PANEL, spec["color"] if spec["color"] is Color else LINE, 12, 11, 14)
		tile.add_theme_stylebox_override("panel", trest)
		tile.mouse_entered.connect(func() -> void:
			tile.add_theme_stylebox_override("panel", thover))
		tile.mouse_exited.connect(func() -> void:
			tile.add_theme_stylebox_override("panel", trest))
		tile.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		tile.tooltip_text = "点击打开「指标全景 · %s」" % str(TILE_TO_GROUP.get(sid, ""))
		tile.gui_input.connect(func(event: InputEvent) -> void:
			if event is InputEventMouseButton \
					and (event as InputEventMouseButton).pressed \
					and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
				_tab = "panels"
				_goto_panel_group = str(TILE_TO_GROUP.get(sid, ""))
				_render())
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
			var rel_at := int(rel.get("released_at_tick", -1))
			if int(_last_release_at.get(sid, -1)) != rel_at:
				if _last_release_at.has(sid):
					var tcolor: Color = spec["color"]
					var flash := ColorRect.new()
					flash.color = Color(tcolor.r, tcolor.g, tcolor.b, 0.16)
					flash.mouse_filter = Control.MOUSE_FILTER_IGNORE
					flash.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
					tile.add_child(flash)
					var ftw := create_tween()
					ftw.tween_property(flash, "modulate:a", 0.0, 0.9)\
						.set_trans(Tween.TRANS_SINE)
					ftw.tween_callback(flash.queue_free)
				_last_release_at[sid] = rel_at
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
					var mag := ""
					if str(spec.get("kind", "num")) == "pp":
						mag = "%.2fpp" % (absf(curv - prev) * 100.0)
					elif absf(prev) > 1e-9:
						var pct := absf(curv - prev) / absf(prev) * 100.0
						mag = "99%+" if pct > 99.0 else "%.1f%%" % pct
					vr.add_child(_lbl(("▲" if up else "▼") + mag, 10, dc))
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
			var rline := _lbl("t%d发布 · %dd前" % [
				int(rel.get("released_at_tick", 0)), t - ref_end], 9, INK3, true)
			rline.clip_text = true
			v.add_child(rline)
			if _god and truth.has(sid):
				var gl := _lbl("真值 " + _fmt_series(sid, float(truth.get(sid, 0.0)))
					+ " ·(调试)", 9, PURPLE, true)
				gl.clip_text = true
				v.add_child(gl)
		else:
			var wait_row := HBoxContainer.new()
			wait_row.add_theme_constant_override("separation", 6)
			wait_row.add_child(_chip("待发布", Color("849098"), Color("f2f5f9"),
				Color("e0e6ee"), 10))
			v.add_child(wait_row)
			v.add_child(_lbl("— —", 17, Color("c3ccd6"), true))
			var why := str(rel.get("missing_reason", "not_released"))
			var wl := _lbl(why, 9, Color("9aa7b4"), true)
			wl.clip_text = true
			v.add_child(wl)
		row.add_child(tile)


# ================= 工作台 =================
func _render_workbench() -> void:
	var lv := _n["levers"] as VBoxContainer
	var lscroll := lv.get_parent() as ScrollContainer
	_keep_scroll("levers:%s:%s" % [_active_seat, _active_group], lscroll)
	for c in lv.get_children():
		c.queue_free()
	var open := _awaiting()
	var emg_ctx := _emergency_context()
	var emg := not emg_ctx.is_empty()
	var active_contexts: Array = []
	var active_allowed := 0
	var cap_text := ""
	var permitted: Dictionary = {}
	for ctx: Dictionary in _contexts():
		if str(ctx.get("seat", "")) == _active_seat:
			active_contexts.append(ctx)
			if cap_text.is_empty() and ctx.get("admin_remaining") != null:
				cap_text = "%.1f" % float(ctx.get("admin_remaining"))
		for item: Dictionary in ctx.get("permitted_actions", []):
			permitted[str(item.get("lever"))] = item
			if str(ctx.get("seat", "")) == _active_seat and bool(item.get("allowed", false)):
				active_allowed += 1
	for s: Dictionary in SEAT_LIST:
		var sid := str(s["id"])
		var b := _n["seat_" + sid] as Button
		var n_open := 0
		for ctx: Dictionary in _contexts():
			if str(ctx.get("seat", "")) == sid:
				n_open += 1
		b.text = str(s["name"]) + (" ·%d" % n_open if n_open > 0 else "")
		var scolor: Color = s["color"]
		if sid == _active_seat:
			b.add_theme_stylebox_override("normal", _sb(
				Color(scolor.r, scolor.g, scolor.b, 0.12), scolor, 8, 6))
			b.add_theme_color_override("font_color", scolor.darkened(0.25))
		else:
			b.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 8, 6))
			b.add_theme_color_override("font_color", Color("586a7b"))
	var active_name := _seat_name(_active_seat)
	var brief := ""
	for spec: Dictionary in SEAT_LIST:
		if str(spec.get("id")) == _active_seat:
			brief = str(spec.get("tag", ""))
			break
	_set_text("seat_brief", brief)
	if not open:
		_set_text("meeting", "%s · 政策窗口关闭 · 可浏览现行制度" % active_name)
	elif active_contexts.is_empty():
		_set_text("meeting", "%s · 本届联席会议无待决议题" % active_name)
	else:
		var status := "🚨 紧急授权" if emg else "● 例会授权"
		var cap := "" if cap_text.is_empty() else " · 容量 " + cap_text
		_set_text("meeting", "%s · %s %d 窗口 / %d 项可调%s" % [
			active_name, status, active_contexts.size(), active_allowed, cap])
	var meetl := _n["meeting"] as Label
	meetl.add_theme_color_override("font_color",
		(Color("b02a1c") if emg else Color("9a6b10")) \
		if not active_contexts.is_empty() else INK2)
	var pending_by: Dictionary = {}
	for p in _snapshot.get("pending", []):
		if p is Dictionary:
			var decision: Dictionary = (p as Dictionary).get("decision", {})
			for act in (p as Dictionary).get("actions", []):
				if act is Dictionary:
					pending_by[str((act as Dictionary).get("lever", ""))] = {
						"value": (act as Dictionary).get("value"),
						"effective_tick": decision.get("effective_tick", "?")}
	# 二级页签:主题页(每页 ≤8；搜索时隐藏)
	var gflow := _n["group_chips"] as HFlowContainer
	for c in gflow.get_children():
		c.queue_free()
	var searching := not _search.is_empty()
	var active_open := not active_contexts.is_empty()
	var scope := _n["policy_scope"] as Button
	scope.visible = not searching
	scope.disabled = not active_open
	scope.text = "本会议题" if _policy_scope == "meeting" and active_open else "全部政策"
	if _policy_scope == "meeting" and active_open:
		scope.add_theme_stylebox_override("normal", _sb(AMBER_BG, AMBER_BD, 8, 6))
		scope.add_theme_color_override("font_color", Color("8a6114"))
	else:
		scope.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 8, 6))
		scope.add_theme_color_override("font_color", Color("586a7b"))
	gflow.visible = not searching
	var pages := _seat_pages(_active_seat)
	if not searching and not pages.is_empty():
		var page_names: Array = []
		for pg: Dictionary in pages:
			page_names.append(str(pg["name"]))
		if not page_names.has(_active_group):
			_active_group = str(page_names[0])
		if _policy_scope == "meeting" and active_open:
			var current_page_live := false
			var first_live_page := ""
			for pg: Dictionary in pages:
				var page_live := false
				for lever: Dictionary in pg["levers"]:
					if not _context_for_group(str(lever.get("decision_group", ""))).is_empty():
						page_live = true
						break
				if page_live and first_live_page.is_empty():
					first_live_page = str(pg["name"])
				if page_live and str(pg["name"]) == _active_group:
					current_page_live = true
			if not current_page_live and not first_live_page.is_empty():
				_active_group = first_live_page
		for pg: Dictionary in pages:
			var pname := str(pg["name"])
			var b := Button.new()
			var draft_count := 0
			for lever: Dictionary in pg["levers"]:
				var lever_name := str(lever.get("name"))
				if _edits.has(lever_name) or _cart_has(lever_name):
					draft_count += 1
			b.text = "%s %d" % [pname, (pg["levers"] as Array).size()]
			b.add_theme_font_size_override("font_size", 11)
			if pname == _active_group:
				b.add_theme_stylebox_override("normal", _sb(TEAL_BG, TEAL_BD, 14, 5))
				b.add_theme_color_override("font_color", TEAL_DK)
			else:
				b.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 14, 5))
				b.add_theme_color_override("font_color", Color("586a7b"))
			var live := false
			for lever: Dictionary in pg["levers"]:
				if not _context_for_group(str(_lever_group.get(
						str(lever.get("name")), ""))).is_empty():
					live = true
					break
			if live:
				b.text += " ●"
			b.disabled = _policy_scope == "meeting" and active_open and not live
			if draft_count > 0:
				b.text += " ·%d" % draft_count
			b.pressed.connect(func() -> void:
				_active_group = pname
				_expanded_lever = ""
				_render())
			gflow.add_child(b)
	# 旋钮列表:搜索=跨席位;否则=当前主题页(单屏);手风琴展开
	var rows: Array = []   # [{lever, seat}]
	if searching:
		var needle := _search.to_lower()
		for seat: String in _schemas.keys():
			for lever: Dictionary in _schemas[seat].get("levers", []):
				var lname := str(lever.get("name"))
				if lname.to_lower().contains(needle) \
						or _cn(lname).to_lower().contains(needle) \
						or str(GROUP_CN.get(str(lever.get("decision_group", "")), "")).contains(_search):
					rows.append({"lever": lever, "seat": seat})
	else:
		for pg: Dictionary in pages:
			if str(pg["name"]) != _active_group:
				continue
			for lever: Dictionary in pg["levers"]:
				if _policy_scope == "meeting" and active_open \
						and _context_for_group(str(lever.get("decision_group", ""))).is_empty():
					continue
				rows.append({"lever": lever, "seat": _active_seat})
	if searching:
		var sh := MarginContainer.new()
		sh.add_theme_constant_override("margin_left", 12)
		sh.add_child(_lbl("搜索「%s」· %d 项(全部席位)" % [_search, rows.size()],
			10, INK3, true))
		lv.add_child(sh)
	if rows.is_empty():
		var empty := MarginContainer.new()
		empty.add_theme_constant_override("margin_left", 12)
		empty.add_theme_constant_override("margin_right", 12)
		empty.add_theme_constant_override("margin_top", 8)
		var empty_panel := PanelContainer.new()
		empty_panel.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 9, 10))
		var empty_text := "没有匹配的政策。" if searching \
			else "本主题不在当前会议授权范围；切换为“全部政策”可浏览。"
		var empty_label := _lbl(empty_text, 11, INK3)
		empty_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		empty_panel.add_child(empty_label)
		empty.add_child(empty_panel)
		lv.add_child(empty)
	for rowdef: Dictionary in rows:
		var lever: Dictionary = rowdef["lever"]
		var lname := str(lever.get("name"))
		var cm := MarginContainer.new()
		cm.add_theme_constant_override("margin_left", 12)
		cm.add_theme_constant_override("margin_right", 12)
		if lname == _expanded_lever:
			cm.add_child(_lever_card(lever, permitted, pending_by, open, emg))
		else:
			cm.add_child(_lever_row(lever, str(rowdef["seat"]), permitted,
				pending_by, searching))
		lv.add_child(cm)
	if not open and int(_snapshot.get("tick", 0)) < 30 and not searching:
		var guide := MarginContainer.new()
		guide.add_theme_constant_override("margin_left", 12)
		guide.add_theme_constant_override("margin_right", 12)
		guide.add_theme_constant_override("margin_top", 6)
		var gp := PanelContainer.new()
		gp.add_theme_stylebox_override("panel", _sb(BLUE_BG, BLUE_BD, 10, 10))
		var gv := VBoxContainer.new()
		gv.add_theme_constant_override("separation", 5)
		gp.add_child(gv)
		gv.add_child(_lbl("上手指引", 11, Color("1c4a8f")))
		for tip in ["▶ 播放(空格)推进模拟,遇到会议自动暂停",
				"会议开启时:点旋钮行展开 → 调整 → 加入提案 → 提交",
				"嫌打断多?切「实时」模式自动通过非紧急会议",
				"点顶部磁贴直达指标全景;世界视图看三国关系"]:
			gv.add_child(_lbl("· " + str(tip), 10, Color("3f5d8a")))
		guide.add_child(gp)
		lv.add_child(guide)
	if not open and not searching:
		_append_governing_brief(lv)
	_render_cart(open)
	_restore_scroll("levers:%s:%s" % [_active_seat, _active_group], lscroll)


func _append_governing_brief(parent: VBoxContainer) -> void:
	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 12)
	margin.add_theme_constant_override("margin_right", 12)
	margin.add_theme_constant_override("margin_top", 7)
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _sb(
		Color("162b3a"), Color("315467"), 11, 12, 8))
	margin.add_child(panel)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 8)
	panel.add_child(col)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	head.add_child(_dot(Color("58c8b9"), 7))
	head.add_child(_lbl("EXECUTIVE BRIEF · 执政简报", 10, Color("9db8c8"), true))
	head.add_child(_spacer_h())
	head.add_child(_lbl("政策窗口已关闭", 10, Color("68d2c2")))
	col.add_child(head)
	var releases: Array = _snapshot.get("observation", {}).get("releases", [])
	var released := 0
	for release in releases:
		if release is Dictionary and (release as Dictionary).get("value") != null:
			released += 1
	var pending: Array = _snapshot.get("pending", [])
	var risks := (_snapshot.get("active_shocks", []) as Array).size() \
		+ (_snapshot.get("shock_bulletins", []) as Array).size()
	var stats := HBoxContainer.new()
	stats.add_theme_constant_override("separation", 6)
	for item: Array in [
		["公报", "%d/%d" % [released, releases.size()]],
		["待实施", str(pending.size())],
		["当前风险", str(risks)],
	]:
		var stat := PanelContainer.new()
		stat.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		stat.add_theme_stylebox_override("panel", _sb(
			Color("1d3546"), Color("315467"), 7, 7))
		var sv := VBoxContainer.new()
		stat.add_child(sv)
		sv.add_child(_lbl(str(item[0]), 9, Color("8ca5b5")))
		sv.add_child(_lbl(str(item[1]), 14, Color("e8f2f4"), true))
		stats.add_child(stat)
	col.add_child(stats)
	if pending.is_empty():
		col.add_child(_lbl("暂无等待实施的政策。推进时间以等待下一轮公报与会议。",
			10, Color("b4c5cf")))
	else:
		col.add_child(_lbl("即将实施", 9, Color("8ca5b5"), true))
		for raw in pending.slice(0, 3):
			var p: Dictionary = raw
			var decision: Dictionary = p.get("decision", {})
			var effective := str(decision.get("effective_tick", "?"))
			for action in (p.get("actions", []) as Array).slice(0, 1):
				var ar: Dictionary = action
				var row := HBoxContainer.new()
				row.add_child(_lbl("• " + _cn(str(ar.get("lever", ""))),
					10, Color("d9e6eb")))
				row.add_child(_spacer_h())
				row.add_child(_lbl("t" + effective, 10, Color("68d2c2"), true))
				col.add_child(row)
	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 7)
	var jump := _btn("快进至下一决策", _advance_to_next_decision, true)
	jump.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	jump.tooltip_text = "最多推进 100 天；遇到会议会立即暂停，不会越过决策边界（快捷键 N）"
	actions.add_child(jump)
	var focus := _btn("查看宏观", func() -> void:
		_tab = "focus"
		_render())
	focus.add_theme_stylebox_override("normal", _sb(
		Color("203b4d"), Color("426175"), 8, 7))
	focus.add_theme_color_override("font_color", Color("d9e6eb"))
	actions.add_child(focus)
	col.add_child(actions)
	parent.add_child(margin)


func _advance_to_next_decision() -> void:
	if _awaiting():
		_show_hint("已有政策会议等待处理，模拟保持暂停。")
		return
	_show_hint("正在快进；遇到下一次政策会议将自动暂停（最多推进 100 天）。")
	_send({"command": "advance", "ticks": 100})


func _lever_row(lever: Dictionary, seat: String, permitted: Dictionary,
		pending_by: Dictionary, show_seat: bool) -> Control:
	## 收起态同时交代现值、草稿/队列目标和可操作状态；点击进入精确编辑。
	var name := str(lever.get("name"))
	var perm: Dictionary = permitted.get(name, {})
	var cart_entry := _cart_entry(name)
	var in_cart := not cart_entry.is_empty()
	var edited := _edits.has(name)
	var pending := pending_by.has(name)
	var allowed := bool(perm.get("allowed", false))
	var draft: Variant = _edits.get(name)
	var cart_stale: bool = in_cart and edited and cart_entry.get("value") != draft
	var row := PanelContainer.new()
	row.custom_minimum_size = Vector2(0, 62)
	row.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	row.tooltip_text = "点击展开「%s」的编辑器" % _cn(name)
	var accent: Color = AMBER if cart_stale else (TEAL if (edited or in_cart) \
		else (AMBER if pending else _seat_color(seat)))
	var row_bg := AMBER_BG if cart_stale else (TEAL_BG if in_cart \
		else (BLUE_BG if edited else (Color("fcfdfe") if allowed else Color("f6f8fa"))))
	var row_bd := AMBER_BD if cart_stale else (TEAL_BD if in_cart \
		else (BLUE_BD if edited else Color("d7e0e9")))
	var style_rest := _sb(row_bg, row_bd, 12, 10, 4)
	var style_hover := _sb(row_bg.lightened(0.018),
		accent.lightened(0.12), 12, 10, 7)
	row.add_theme_stylebox_override("panel", style_rest)
	row.mouse_entered.connect(func() -> void:
		row.add_theme_stylebox_override("panel", style_hover))
	row.mouse_exited.connect(func() -> void:
		row.add_theme_stylebox_override("panel", style_rest))
	var r := HBoxContainer.new()
	r.add_theme_constant_override("separation", 10)
	row.add_child(r)
	var rail := PanelContainer.new()
	rail.custom_minimum_size = Vector2(3, 30)
	rail.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	rail.add_theme_stylebox_override("panel", _sb(accent, accent, 2, 0))
	r.add_child(rail)
	var names := VBoxContainer.new()
	names.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	names.alignment = BoxContainer.ALIGNMENT_CENTER
	names.add_theme_constant_override("separation", 2)
	var title := _lbl(_cn(name), 13, INK)
	title.clip_text = true
	names.add_child(title)
	var sub := HBoxContainer.new()
	sub.add_theme_constant_override("separation", 6)
	if show_seat:
		sub.add_child(_lbl(_seat_name(seat), 9, _seat_color(seat)))
	var en := _lbl(name, 9, Color("8a97a5"), true)
	en.clip_text = true
	en.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sub.add_child(en)
	names.add_child(sub)
	r.add_child(names)
	var base_v: Variant = _lever_current(lever, perm)
	var value_col := VBoxContainer.new()
	value_col.alignment = BoxContainer.ALIGNMENT_CENTER
	value_col.add_theme_constant_override("separation", 2)
	value_col.custom_minimum_size = Vector2(122, 0)
	var value_text := _lever_value_text(lever, base_v)
	if edited:
		value_text += " → " + _lever_value_text(lever, draft)
	elif pending:
		value_text += " → " + _lever_value_text(lever,
			(pending_by[name] as Dictionary).get("value"))
	var value := _lbl(value_text, 12, AMBER if cart_stale else (
		TEAL_DK if (edited or pending or in_cart) else INK2), true)
	value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	value.clip_text = true
	value_col.add_child(value)
	var status_text := ""
	var status_color := INK3
	if cart_stale:
		status_text = "草稿有改动 · 待更新"
		status_color = AMBER
	elif in_cart:
		status_text = "已加入提案篮"
		status_color = TEAL_DK
	elif edited:
		status_text = "未入篮草稿"
		status_color = BLUE
	elif pending:
		status_text = "待生效 · t%s" % str((pending_by[name] as Dictionary).get("effective_tick", "?"))
		status_color = AMBER
	elif allowed:
		status_text = "本会可调整"
		status_color = GREEN
	else:
		status_text = "查看制度"
	var status_bg := Color("f1f4f7")
	var status_border := Color("dce3ea")
	if cart_stale or pending:
		status_bg = Color("fff7e8")
		status_border = Color("efd39b")
	elif edited or in_cart:
		status_bg = Color("e9f7f4")
		status_border = Color("b9e1d9")
	elif allowed:
		status_bg = Color("edf8f2")
		status_border = Color("c9e7d5")
	var status_row := HBoxContainer.new()
	status_row.add_child(_spacer_h())
	status_row.add_child(_chip(status_text, status_color,
		status_bg, status_border, 9))
	value_col.add_child(status_row)
	r.add_child(value_col)
	var caret := _lbl("⌄", 13, Color("8190a0"))
	caret.custom_minimum_size.x = 12
	caret.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	r.add_child(caret)
	row.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton \
				and (event as InputEventMouseButton).pressed \
				and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
			_focus_lever(name))
	return row


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
	var cart_entry := _cart_entry(name)
	var in_cart := not cart_entry.is_empty()
	var base_v: Variant = _lever_current(lever, perm)
	var edited := _edits.has(name)
	var draft_v: Variant = _edits.get(name, base_v)
	var changed: bool = edited and draft_v != base_v
	var cart_stale: bool = in_cart and edited and cart_entry.get("value") != draft_v
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", _sb(
		AMBER_BG if cart_stale else (Color("e6f5f0") if in_cart else Color.WHITE),
		AMBER_BD if cart_stale else (Color("59b7a8") if in_cart else Color("e2e8ef")),
		13, 12, 6))
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 9)
	card.add_child(v)
	var tr := HBoxContainer.new()
	tr.add_theme_constant_override("separation", 7)
	var fold := Button.new()
	fold.text = "▴"
	fold.flat = true
	fold.add_theme_font_size_override("font_size", 11)
	fold.pressed.connect(func() -> void:
		_expanded_lever = ""
		_render())
	tr.add_child(fold)
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
	var state := PanelContainer.new()
	state.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 8, 7))
	var state_row := HBoxContainer.new()
	state_row.add_theme_constant_override("separation", 7)
	state.add_child(state_row)
	state_row.add_child(_lbl("当前", 9, INK3, true))
	state_row.add_child(_lbl(_lever_value_text(lever, base_v), 12, INK2, true))
	if edited:
		state_row.add_child(_lbl("→", 11, TEAL))
		state_row.add_child(_lbl("草稿", 9, TEAL, true))
		state_row.add_child(_lbl(_lever_value_text(lever, draft_v), 12,
			AMBER if cart_stale else TEAL_DK, true))
	state_row.add_child(_spacer_h())
	if cart_stale:
		state_row.add_child(_lbl("提案篮尚未同步", 9, AMBER))
	elif in_cart:
		state_row.add_child(_lbl("已在提案篮", 9, TEAL_DK))
	v.add_child(state)
	if allowed:
		v.add_child(_lever_control(lever, perm, base_v))
		var companion := _lever_companion_note(name, draft_v)
		if not companion.is_empty():
			var note_panel := PanelContainer.new()
			note_panel.add_theme_stylebox_override("panel", _sb(BLUE_BG, BLUE_BD, 7, 7))
			var note := _lbl("联动 · " + companion, 10, Color("315d96"))
			note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			note_panel.add_child(note)
			v.add_child(note_panel)
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
		else:
			reason = _permission_reason(reason)
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
	if edited:
		var addrow := HBoxContainer.new()
		addrow.add_theme_constant_override("separation", 9)
		if not changed:
			addrow.add_child(_lbl("草稿与当前值相同，不会产生政策动作", 10, INK3))
		elif allowed and (not in_cart or cart_stale):
			var add := _btn("更新提案篮" if cart_stale else "加入提案 ＋", func() -> void:
				_add_to_cart(lever, base_v), true)
			addrow.add_child(add)
			var lag2 := int(lever.get("implementation_lag", 0))
			addrow.add_child(_lbl("预计 t%d 生效" % (
				int(_snapshot.get("tick", 0)) + maxi(lag2, 1)), 10, INK3, true))
		elif in_cart:
			addrow.add_child(_lbl("✓ 草稿与提案篮一致", 11, TEAL_DK))
		else:
			addrow.add_child(_lbl("当前窗口不可提交此草稿", 10, AMBER))
		addrow.add_child(_spacer_h())
		var reset := _btn("移出并撤销" if in_cart else "恢复当前值", func() -> void:
			_reset_lever_draft(name))
		reset.add_theme_font_size_override("font_size", 10)
		addrow.add_child(reset)
		v.add_child(addrow)
	return card


func _lever_value_text(lever: Dictionary, v: Variant) -> String:
	if v == null:
		return "未设置"
	if v is bool:
		return "启用" if v else "停用"
	if v is String:
		return _choice_text(str(lever.get("name", "")), v)
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
	var name := str(lever.get("name", ""))
	if PERCENT_LEVERS.has(name):
		var pct := f * 100.0
		return ("%.4f%%" if absf(pct) < 0.1 and absf(pct) > 0.0 else "%.2f%%") % pct
	if MULTIPLIER_LEVERS.has(name):
		return "%.2f×" % f
	if DAY_LEVERS.has(name):
		return "%d 天" % roundi(f)
	if name == "housing_permits":
		return "%d 套/年" % roundi(f)
	var scale := absf(float(lever.get("control_scale", 1.0)))
	if scale >= 1.0:
		return "%d" % roundi(f)
	if scale < 0.001:
		return "%.5f" % f
	return "%.3f" % f


func _lever_raw_value_text(lever: Dictionary, v: Variant) -> String:
	if v == null:
		return ""
	if str(lever.get("value_kind", "")) == "integer":
		return str(roundi(float(v)))
	return str(float(v))


func _lever_companion_note(lever_name: String, draft_value: Variant) -> String:
	match lever_name:
		"monetary_regime":
			if str(draft_value) == "manual":
				return "切换为手动设定时，必须把“手动政策利率”作为同批动作加入提案。"
		"manual_policy_rate":
			return "该值只在“货币政策规则 = 手动设定”时生效；切换制度时必须同批提交。"
		"fx_regime":
			if str(draft_value) == "peg":
				return "启用联系汇率时，必须在同批提案中选择一个浮动汇率锚国。"
		"peg_anchor":
			return "锚国只在联系汇率制度下生效；锚国无需同意，但不能形成链式或循环挂钩。"
	return ""


func _commit_numeric_input(lever: Dictionary, text: String, is_int: bool,
		minimum: float, maximum: float) -> void:
	var cleaned := text.strip_edges()
	if not cleaned.is_valid_float():
		_show_hint("请输入有效数字；百分比仍按模型值填写，例如 3% 输入 0.03。")
		return
	var value := clampf(cleaned.to_float(), minimum, maximum)
	_edits[str(lever.get("name"))] = roundi(value) if is_int else value
	_render()


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
			b.text = _choice_text(name, opt)
			b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			if str(cur) == str(opt):
				b.add_theme_stylebox_override("normal", _sb(TEAL_BG, TEAL_BD, 6, 6))
				b.add_theme_color_override("font_color", TEAL_DK)
			var value := str(opt)
			b.pressed.connect(func() -> void:
				if str(cur) != value:
					_stage_lever_edit(lever, value))
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
			_stage_lever_edit(lever, pressed))
		brow.add_child(sw)
		if st:
			brow.add_child(_chip("状态迁移", Color("9a7a2e"), Color(0, 0, 0, 0), AMBER_BD, 10))
		return brow
	# 数值（含可空）：步进适合探索，直接输入负责精确操作。
	var wrap := VBoxContainer.new()
	wrap.add_theme_constant_override("separation", 6)
	var nullable := bool(perm.get("nullable", lever.get("nullable", false)))
	var numeric := cur != null and not (cur is bool) and not (cur is String)
	var scale := float(perm.get("control_scale", lever.get("control_scale", 0.01)))
	if scale <= 0.0:
		scale = 0.01
	var lo := float(perm.get("minimum", lever.get("minimum", 0.0)))
	var hi := float(perm.get("maximum", lever.get("maximum", 0.0)))
	var lo2 := lo
	var hi2 := hi
	var max_step: Variant = perm.get("max_step", lever.get("max_step"))
	if max_step != null and base_v != null and not (base_v is bool):
		lo2 = maxf(lo, float(base_v) - float(max_step))
		hi2 = minf(hi, float(base_v) + float(max_step))
	var is_int := kind == "integer"
	var srow := HBoxContainer.new()
	srow.add_theme_constant_override("separation", 7)
	var dec := Button.new()
	dec.text = "−"
	dec.custom_minimum_size = Vector2(40, 0)
	dec.add_theme_font_size_override("font_size", 18)
	srow.add_child(dec)
	var mid := PanelContainer.new()
	mid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mid.add_theme_stylebox_override("panel", _sb(PANEL2, LINE2, 8, 7))
	var midv := VBoxContainer.new()
	midv.add_theme_constant_override("separation", 1)
	mid.add_child(midv)
	var vrow := HBoxContainer.new()
	vrow.add_theme_constant_override("separation", 7)
	var display := _lbl(_lever_value_text(lever, cur), 18, INK, true)
	display.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vrow.add_child(display)
	if numeric and _edits.has(name) and base_v != null and not (base_v is bool):
		var delta := float(_edits[name]) - float(base_v)
		if absf(delta) > 1e-12:
			vrow.add_child(_lbl("▲" if delta > 0 else "▼", 11,
				GREEN if delta > 0 else RED))
	midv.add_child(vrow)
	var range_text := "单档 %s · 本次 %s – %s" % [
		_lever_value_text(lever, scale), _lever_value_text(lever, lo2),
		_lever_value_text(lever, hi2)]
	midv.add_child(_lbl(range_text, 9, INK3, true))
	srow.add_child(mid)
	var inc := Button.new()
	inc.text = "＋"
	inc.custom_minimum_size = Vector2(40, 0)
	inc.add_theme_font_size_override("font_size", 18)
	srow.add_child(inc)
	dec.disabled = true
	inc.disabled = true
	if numeric:
		var local_base := float(cur)
		dec.disabled = local_base <= lo2 + 1e-12
		inc.disabled = local_base >= hi2 - 1e-12
		dec.pressed.connect(func() -> void:
			var next := clampf(float(_edits.get(name, local_base)) - scale, lo2, hi2)
			_edits[name] = roundi(next) if is_int else next
			_render())
		inc.pressed.connect(func() -> void:
			var next := clampf(float(_edits.get(name, local_base)) + scale, lo2, hi2)
			_edits[name] = roundi(next) if is_int else next
			_render())
	wrap.add_child(srow)
	if numeric:
		var direct := HBoxContainer.new()
		direct.add_theme_constant_override("separation", 6)
		var input := LineEdit.new()
		input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		input.text = _lever_raw_value_text(lever, cur)
		input.placeholder_text = "输入模型值"
		input.tooltip_text = "精确输入 canonical 模型值；百分比 3% 输入 0.03"
		input.add_theme_font_override("font", _mono)
		input.add_theme_font_size_override("font_size", 11)
		input.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 7, 6))
		input.add_theme_stylebox_override("focus", _sb(Color.WHITE, TEAL_BD, 7, 6))
		input.text_submitted.connect(func(text: String) -> void:
			_commit_numeric_input(lever, text, is_int, lo2, hi2))
		direct.add_child(input)
		var apply := _btn("应用数值", func() -> void:
			_commit_numeric_input(lever, input.text, is_int, lo2, hi2))
		apply.tooltip_text = "输入超出本次可调范围时会夹到最近边界"
		direct.add_child(apply)
		wrap.add_child(direct)
		wrap.add_child(_lbl("模型值 %s · 制度全域 %s – %s" % [
			_lever_raw_value_text(lever, cur), _lever_raw_value_text(lever, lo),
			_lever_raw_value_text(lever, hi)], 9, INK3, true))
	if nullable:
		var nrow := HBoxContainer.new()
		nrow.add_theme_constant_override("separation", 7)
		var nb := Button.new()
		nb.add_theme_font_size_override("font_size", 11)
		if cur == null:
			nb.text = "设置数值"
			nb.pressed.connect(func() -> void:
				_edits[name] = lo
				_render())
		else:
			nb.text = "取消该限制"
			nb.pressed.connect(func() -> void:
				_edits[name] = null
				_render())
		nrow.add_child(nb)
		nrow.add_child(_lbl("未设置 = 不启用该上限或限制", 10, INK3))
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
	if _edits[name] == base_v:
		_reset_lever_draft(name)
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
	var admin_total := 0.0
	for cart_item: Dictionary in _cart:
		var info: Dictionary = _lever_info.get(str(cart_item.get("lever")), {})
		admin_total += float(info.get("admin_weight", 0.0))
	_set_text("cart_cost", "" if _cart.is_empty() else "行政容量 %.1f" % admin_total)
	if _cart.is_empty():
		items.add_child(_lbl("尚无动作。展开旋钮形成草稿，再加入提案篮统一裁决。",
			11, Color("7a8593")))
	for c: Dictionary in _cart:
		var key := str(c["lever"])
		var stale: bool = _edits.has(key) and _edits[key] != c.get("value")
		var rowp := PanelContainer.new()
		rowp.add_theme_stylebox_override("panel", _sb(
			AMBER_BG if stale else Color.WHITE, AMBER_BD if stale else LINE, 7, 6))
		var r := HBoxContainer.new()
		r.add_theme_constant_override("separation", 6)
		rowp.add_child(r)
		r.add_child(_lbl(_cn(str(c["lever"])), 12, Color("23323f")))
		r.add_child(_spacer_h())
		if stale:
			r.add_child(_lbl("有新草稿", 9, AMBER))
		r.add_child(_lbl(str(c["from"]), 11, Color("586a7b"), true))
		r.add_child(_lbl("→", 11, TEAL))
		r.add_child(_lbl(str(c["to"]), 11, TEAL_DK, true))
		var edit := Button.new()
		edit.text = "编辑"
		edit.flat = true
		edit.add_theme_font_size_override("font_size", 10)
		edit.pressed.connect(func() -> void:
			_focus_lever(key))
		r.add_child(edit)
		var rm := Button.new()
		rm.text = "×"
		rm.flat = true
		rm.pressed.connect(func() -> void:
			_reset_lever_draft(key))
		r.add_child(rm)
		items.add_child(rowp)
	var subb := _n["submit"] as Button
	subb.text = "提交提案(%d)" % _cart.size() if not _cart.is_empty() else "提交提案"
	subb.disabled = not open or _cart.is_empty()
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
	_fade_in(vp)


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
	var status_cn: String = {
		"accepted_pending": "提案获准 · 等待实施",
		"accepted_effective": "提案获准 · 已经生效",
		"accepted_noop": "会议完成 · 维持现状",
		"accepted": "政策提案获准",
		"rejected": "政策提案未通过",
		"cancelled": "待实施政策已撤销",
	}.get(status, status.replace("_", " "))
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
	col.add_child(_lbl(str(status_cn), 12, GREEN if ok else RED))
	var reason := str(v.get("reason_code", ""))
	var sub := ""
	if not reason.is_empty() and reason != "<null>":
		sub = str(REASON_CN.get(reason, reason.replace("_", " ")))
	if v.get("effective_tick") != null:
		var et := int(v.get("effective_tick"))
		sub += ("" if sub.is_empty() else " · ") + "生效 t%d(%s)" % [et, _cal_str(et)]
	var cost := float(v.get("adjustment_cost", 0.0))
	var admin := float(v.get("reserved_admin_cost", 0.0))
	if cost > 0.0 or admin > 0.0:
		sub += ("" if sub.is_empty() else " · ") + "调整成本 %.2f / 行政容量 %.2f" % [cost, admin]
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
	_fade_in(vp)


func _submit_cart() -> void:
	if _cart.is_empty():
		return
	_show_hint("已递交 %d 项动作,闭合本届会议,裁决将在边界返回…" % _cart.size())
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
	var extra_label := "通胀"
	var extra_color: Color = PURPLE
	for tsp: Dictionary in TILE_SPEC:
		if str(tsp["id"]) == _focus_extra:
			extra_label = str(tsp["label"]).split("(")[0].split(" · ")[0]
			extra_color = tsp["color"]
	if _focus_extra == "inflation":
		extra_color = PURPLE
	elif _focus_extra == "policy_rate":
		extra_color = BLUE
	var fp := PanelContainer.new()
	var fv := VBoxContainer.new()
	fv.add_theme_constant_override("separation", 6)
	fp.add_child(fv)
	var legend := HBoxContainer.new()
	legend.add_theme_constant_override("separation", 14)
	legend.add_child(_lbl("宏观焦点 · 公报序列", 14, INK))
	legend.add_child(_spacer_h())
	for item: Array in [["实际产出", TEAL], ["失业率", AMBER], [extra_label, extra_color]]:
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
	var focus_defs: Array = [
		["real_output", "实际产出", TEAL, 2.4, true],
		["unemployment_rate", "失业率", AMBER, 1.8, false],
		[_focus_extra, extra_label, extra_color, 1.8, false],
	]
	var fseries: Array = []
	for fd: Array in focus_defs:
		var sid := str(fd[0])
		var vals := _hist_vals(sid)
		fseries.append({"vals": vals, "color": fd[2], "width": fd[3], "fill": fd[4],
			"label": fd[1],
			"last_text": _fmt_series(sid, float(vals[-1])) if not vals.is_empty() else "",
			"fmt": func(v: float) -> String: return _fmt_series(sid, v)})
	chart.series = fseries
	chart.shock_active = not _snapshot.get("active_shocks", []).is_empty()
	chart.font = _sans
	chart.mouse_exited.connect(func() -> void:
		chart.hover_pos = Vector2(-1, -1)
		chart.queue_redraw())
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
	_append_core_dimensions(sv)
	body.add_child(sp)


func _append_core_dimensions(parent: VBoxContainer) -> void:
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	head.add_child(_lbl("CORE 8 · 八维核心指标", 10, INK3, true))
	head.add_child(_spacer_h())
	head.add_child(_lbl("增长 · 就业 · 物价 · 财政 · 金融 · 民生 · 人口 · 外部",
		8, Color("8a97a5")))
	parent.add_child(head)
	var releases := _releases_by_id()
	var now := int(_snapshot.get("tick", 0))
	var grid := VBoxContainer.new()
	grid.add_theme_constant_override("separation", 7)
	grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	parent.add_child(grid)
	for row_index in 2:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		row.size_flags_vertical = Control.SIZE_EXPAND_FILL
		grid.add_child(row)
		for column_index in 4:
			var spec: Dictionary = CORE_DIMENSION_SPEC[row_index * 4 + column_index]
			row.add_child(_core_dimension_card(spec, releases, now))


func _core_dimension_card(spec: Dictionary, releases: Dictionary, now: int) -> Control:
	var sid := str(spec["id"])
	var color: Color = spec["color"]
	var target_tab := str(spec.get("tab", "panels"))
	var target_group := str(spec.get("group", ""))
	var card := PanelContainer.new()
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	card.size_flags_vertical = Control.SIZE_EXPAND_FILL
	card.custom_minimum_size = Vector2(0, 121)
	card.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	var rest := _sb(Color("f7f9fc"), Color("e2e8ef"), 10, 9)
	var hover := _sb(Color.WHITE, color, 10, 9, 7)
	card.add_theme_stylebox_override("panel", rest)
	card.mouse_entered.connect(func() -> void:
		card.add_theme_stylebox_override("panel", hover))
	card.mouse_exited.connect(func() -> void:
		card.add_theme_stylebox_override("panel", rest))
	card.tooltip_text = "打开%s" % ("世界视图" if target_tab == "world" \
		else "「%s」指标全景" % target_group)
	card.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton \
				and (event as InputEventMouseButton).pressed \
				and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
			_open_core_dimension(target_tab, target_group))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 4)
	card.add_child(col)
	var title := HBoxContainer.new()
	title.add_theme_constant_override("separation", 5)
	title.add_child(_dot(color, 7))
	title.add_child(_lbl("%s · %s" % [spec["dimension"], spec["metric"]],
		10, INK2))
	title.add_child(_spacer_h())
	title.add_child(_lbl("↗", 10, INK3))
	col.add_child(title)
	var rel: Dictionary = releases.get(sid, {})
	var hist: Array = _release_hist.get(sid, [])
	if rel.is_empty() or rel.get("value") == null:
		col.add_child(_lbl("尚未发布", 18, Color("a2adb8"), true))
		col.add_child(_lbl("等待首期公报", 9, INK3))
		return card
	var value_row := HBoxContainer.new()
	value_row.add_theme_constant_override("separation", 5)
	value_row.add_child(_lbl(_fmt_series(sid, float(rel.get("value"))),
		19, color, true))
	value_row.add_child(_spacer_h())
	if hist.size() >= 2:
		value_row.add_child(_lbl(_release_movement(sid,
			float(hist[-2]["v"]), float(hist[-1]["v"])), 9, INK2, true))
	col.add_child(value_row)
	var spark := _SparkLine.new()
	spark.color = color
	spark.custom_minimum_size = Vector2(0, 28)
	var values: Array = []
	for point: Dictionary in hist:
		values.append(point["v"])
	spark.values = values
	col.add_child(spark)
	var released_at := int(rel.get("released_at_tick", now))
	var reference_at := int(rel.get("reference_end_tick", released_at))
	var lag := maxi(0, now - reference_at)
	var source_label := _lbl("发布 t%d · 滞后 %d日" % [released_at, lag],
		9, INK3, true)
	source_label.clip_text = true
	col.add_child(source_label)
	return card


func _release_movement(sid: String, previous: float, current: float) -> String:
	var delta := current - previous
	if absf(delta) <= 1e-12:
		return "持平"
	var arrow := "▲" if delta > 0.0 else "▼"
	if sid in ["unemployment_rate", "inflation", "gov_deficit_to_gdp",
			"gov_debt_to_gdp", "credit_to_gdp", "poverty_rate"]:
		return "%s%.2fpp" % [arrow, absf(delta) * 100.0]
	if absf(previous) > 1e-9:
		var percent := absf(delta / previous) * 100.0
		return "%s%s" % [arrow,
			"99%+" if percent > 99.0 else "%.1f%%" % percent]
	return "%s%s" % [arrow, _fmt_series(sid, absf(delta))]


func _open_core_dimension(target_tab: String, group: String) -> void:
	_tab = target_tab
	if target_tab == "panels":
		_goto_panel_group = group
	_render()


func _render_panels_tab(body: VBoxContainer) -> void:
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	body.add_child(scroll)
	_restore_scroll("center:panels", scroll)
	scroll.get_v_scroll_bar().value_changed.connect(func(v: float) -> void:
		_scroll_mem["center:panels"] = int(v))
	var col := VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 10)
	scroll.add_child(col)
	var series: Array = _snapshot.get("series", [])
	var latest: Dictionary = _snapshot.get("metrics", {})
	var nav := HFlowContainer.new()
	nav.add_theme_constant_override("h_separation", 5)
	nav.add_theme_constant_override("v_separation", 4)
	col.add_child(nav)
	var goto_target: Control = null
	for grp: Dictionary in PANEL_GROUPS:
		var gp := PanelContainer.new()
		if str(grp["name"]) == _goto_panel_group:
			goto_target = gp
		var gcolor: Color = grp["color"]
		var gsb := _sb(PANEL, Color(gcolor.r, gcolor.g, gcolor.b, 0.45), 13, 12, 8)
		gsb.border_width_left = 4
		gp.add_theme_stylebox_override("panel", gsb)
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
			var kind := str(item[2])
			var card := PanelContainer.new()
			card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			var prest := _sb(PANEL3, Color("e6ebf1"), 9, 8)
			var phover := _sb(Color.WHITE, grp["color"], 9, 8, 8)
			card.add_theme_stylebox_override("panel", prest)
			card.mouse_entered.connect(func() -> void:
				card.add_theme_stylebox_override("panel", phover))
			card.mouse_exited.connect(func() -> void:
				card.add_theme_stylebox_override("panel", prest))
			var cv := VBoxContainer.new()
			cv.add_theme_constant_override("separation", 3)
			card.add_child(cv)
			cv.add_child(_lbl(str(item[1]), 10, Color("516375")))
			cv.add_child(_lbl(_fmt_val(kind, float(latest.get(key, 0.0))),
				15, grp["color"], true))
			var sl := _SparkLine.new()
			sl.color = grp["color"]
			sl.custom_minimum_size = Vector2(120, 24)
			var vals: Array = []
			var vlo := INF
			var vhi := -INF
			for point: Dictionary in series:
				var pv := float(point.get(key, 0.0))
				vals.append(pv)
				vlo = minf(vlo, pv)
				vhi = maxf(vhi, pv)
			sl.values = vals
			cv.add_child(sl)
			if not vals.is_empty():
				card.tooltip_text = "%s(%s)\n当前 %s · 区间低 %s · 高 %s · 近 %d tick" % [
					str(item[1]), key,
					_fmt_val(kind, float(latest.get(key, 0.0))),
					_fmt_val(kind, vlo), _fmt_val(kind, vhi), vals.size()]
			grid.add_child(card)
		col.add_child(gp)
	for grp: Dictionary in PANEL_GROUPS:
		var gname := str(grp["name"])
		var gcolor2: Color = grp["color"]
		var nb := Button.new()
		nb.text = gname
		nb.add_theme_font_size_override("font_size", 11)
		nb.add_theme_stylebox_override("normal", _sb(Color.WHITE,
			Color(gcolor2.r, gcolor2.g, gcolor2.b, 0.5), 14, 5))
		nb.add_theme_color_override("font_color", gcolor2.darkened(0.2))
		nb.pressed.connect(func() -> void:
			_goto_panel_group = gname
			_render())
		nav.add_child(nb)
	if goto_target != null:
		_goto_panel_group = ""
		var target := goto_target
		scroll.call_deferred("ensure_control_visible", target)


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
	_restore_scroll("center:world", scroll)
	scroll.get_v_scroll_bar().value_changed.connect(func(v: float) -> void:
		_scroll_mem["center:world"] = int(v))
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
		var wrest := _sb(Color("eef7f5") if mine else PANEL,
			TEAL_BD if mine else LINE, 12, 11, 6)
		var whover := _sb(Color("eef7f5") if mine else PANEL,
			ECON_COLORS[i % 3], 12, 11, 13)
		card.add_theme_stylebox_override("panel", wrest)
		card.mouse_entered.connect(func() -> void:
			card.add_theme_stylebox_override("panel", whover))
		card.mouse_exited.connect(func() -> void:
			card.add_theme_stylebox_override("panel", wrest))
		var cv := VBoxContainer.new()
		cv.add_theme_constant_override("separation", 4)
		card.add_child(cv)
		var hr := HBoxContainer.new()
		hr.add_theme_constant_override("separation", 7)
		hr.add_child(_flag(i))
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
		var gspark := _SparkLine.new()
		gspark.color = ECON_COLORS[i % 3]
		gspark.custom_minimum_size = Vector2(0, 18)
		var gvals: Array = []
		for point: Dictionary in world.get("history", []):
			var pe: Array = point.get("economies", [])
			if i < pe.size():
				gvals.append(float((pe[i] as Dictionary).get("real_output", 0.0)))
		gspark.values = gvals
		cv.add_child(gspark)
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
		var lead := pos == 0
		rr.add_child(_lbl("#%d" % (pos + 1), 13 if lead else 12,
			Color("1c4a8f") if lead else INK3, true))
		rr.add_child(_flag(i, Vector2(14, 10)))
		rr.add_child(_lbl(_country_name(i), 13 if lead else 12,
			INK if lead else INK_BODY))
		var barwrap := Control.new()
		barwrap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		barwrap.custom_minimum_size = Vector2(0, 12)
		var frac := absf(float(row[1])) / maxv
		var color: Color = ECON_COLORS[i % 3]
		barwrap.draw.connect(func() -> void:
			barwrap.draw_rect(Rect2(Vector2(0, 3),
				Vector2(barwrap.size.x, 6)), Color("edf1f6"))
			var w := barwrap.size.x * frac
			barwrap.draw_rect(Rect2(Vector2(0, 3), Vector2(w, 6)), color)
			barwrap.draw_circle(Vector2(w, 6), 4.0, color))
		rr.add_child(barwrap)
		rr.add_child(_lbl(_fmt_val(rank_kind, float(row[1])), 12, ECON_COLORS[i % 3], true))
		rv.add_child(rr)
	col.add_child(rp)
	# --- 国际关系:贸易 / 金融 / 移民 ---
	var whist: Array = world.get("history", [])
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
	map.custom_minimum_size = Vector2(290, 236)
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
	bars.custom_minimum_size = Vector2(248, 0)
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
		ml.custom_minimum_size = Vector2(110, 42)
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
		row.add_child(_flag(i, Vector2(10, 8)))
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
	var escroll := box.get_parent() as ScrollContainer
	_keep_scroll("events", escroll)
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
		var pulse_dot := _dot(RED, 7)
		var ptw := create_tween().set_loops()
		ptw.tween_property(pulse_dot, "modulate:a", 0.3, 0.6)\
			.set_trans(Tween.TRANS_SINE)
		ptw.tween_property(pulse_dot, "modulate:a", 1.0, 0.6)\
			.set_trans(Tween.TRANS_SINE)
		br.add_child(pulse_dot)
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
	var visible_events: Array = []
	var seen_important: Dictionary = {}
	for raw in merged:
		var ev: Dictionary = raw
		var etype := str(ev.get("event_type", ev.get("kind", "event")))
		var actor := str(ev.get("actor", ""))
		var mine := actor.contains("desktop") or actor.contains("player")
		if _event_filter == "mine" and not mine:
			continue
		if _event_filter == "important" and not _event_is_important(etype):
			continue
		if _event_filter == "important":
			# 同一边界、同一触发器常向多个席位各发一次；默认视图合并为一条。
			var dedupe := "%s|%s|%s" % [
				str(ev.get("boundary_tick", ev.get("tick", "?"))),
				etype, str(ev.get("reason", ev.get("shock_id", "")))]
			if seen_important.has(dedupe):
				continue
			seen_important[dedupe] = true
		visible_events.append(ev)
	if visible_events.is_empty():
		var empty := PanelContainer.new()
		empty.add_theme_stylebox_override("panel", _sb(PANEL3, Color("e6ebf1"), 9, 10))
		var empty_text := "暂无重点事件" if _event_filter == "important" else "当前筛选下没有记录"
		empty.add_child(_lbl(empty_text + "\n模拟推进后，危机、政策裁决和生效记录会出现在这里。",
			11, Color("7b8996")))
		inner.add_child(empty)
	var last_tick_s := ""
	for ev: Dictionary in visible_events.slice(0, 36):
		var tick_var: Variant = ev.get("boundary_tick", ev.get("tick", "?"))
		var group_tick := str(int(tick_var)) if tick_var is float else str(tick_var)
		if group_tick != last_tick_s:
			last_tick_s = group_tick
			var sep := HBoxContainer.new()
			sep.add_theme_constant_override("separation", 7)
			var sline := ColorRect.new()
			sline.color = Color("e6ebf1")
			sline.custom_minimum_size = Vector2(10, 1)
			sline.size_flags_vertical = Control.SIZE_SHRINK_CENTER
			sep.add_child(sline)
			sep.add_child(_lbl("t" + group_tick, 9, Color("9aa7b4"), true))
			var sline2 := ColorRect.new()
			sline2.color = Color("e6ebf1")
			sline2.custom_minimum_size = Vector2(0, 1)
			sline2.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			sline2.size_flags_vertical = Control.SIZE_SHRINK_CENTER
			sep.add_child(sline2)
			inner.add_child(sep)
		var actor := str(ev.get("actor", ""))
		var mine := actor.contains("desktop") or actor.contains("player")
		var etype := str(ev.get("event_type", ev.get("kind", "event")))
		var color := Color("586a7b")
		if etype.contains("emergency"):
			color = RED
		elif etype.contains("accepted") or etype.contains("committed"):
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
		if etype.contains("accepted"):
			railv.add_child(_lbl("✓", 10, color))
		elif etype.contains("rejected") or etype.contains("failed"):
			railv.add_child(_lbl("✕", 10, color))
		else:
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
		var title := _lbl(_event_title(etype), 11, color)
		title.tooltip_text = "协议事件: " + etype
		trr.add_child(title)
		if mine:
			trr.add_child(_chip("我", TEAL, Color(0, 0, 0, 0), TEAL_BD, 9))
		trr.add_child(_spacer_h())
		col.add_child(trr)
		var detail := _event_detail(ev, etype)
		if not detail.is_empty():
			var dl := _lbl(detail, 12, Color("33424f"))
			dl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			col.add_child(dl)
		r.add_child(col)
		inner.add_child(r)
	_restore_scroll("events", escroll)


# ================= 危机遮罩 =================
func _render_crisis() -> void:
	var real_ctx := _emergency_context()
	var on := _emergency()
	if not real_ctx.is_empty() \
			and str(real_ctx.get("context_id", "")) == _crisis_dismissed:
		on = _demo_crisis
	var overlay := _n["crisis"] as Control
	overlay.visible = on
	if on and not _crisis_was_visible:
		_fade_in(overlay)
	_crisis_was_visible = on
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
class _Spinner extends Control:
	func _draw() -> void:
		var c := size / 2.0
		var r := minf(size.x, size.y) / 2.0 - 3.0
		draw_arc(c, r, 0, TAU, 40, Color("dbe2ea"), 3.0, true)
		draw_arc(c, r, 0, TAU * 0.28, 16, Color("0f9d90"), 3.0, true)


class _YearBar extends Control:
	var frac := 0.0

	func _draw() -> void:
		var h := 3.0
		var y := (size.y - h) / 2.0
		draw_rect(Rect2(0, y, size.x, h), Color("e6ebf1"))
		draw_rect(Rect2(0, y, size.x * frac, h), Color("0f9d90"))
		for q in [0.25, 0.5, 0.75]:
			draw_rect(Rect2(size.x * q - 0.5, y - 1.5, 1.0, h + 3.0),
				Color("cdd7e2"))
		draw_circle(Vector2(size.x * frac, y + h / 2.0), 2.6, Color("0c8579"))


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
		var poly := PackedVector2Array(pts)
		poly.append(Vector2(pts[n - 1].x, size.y - 1.0))
		poly.append(Vector2(pts[0].x, size.y - 1.0))
		draw_colored_polygon(poly, Color(color.r, color.g, color.b, 0.10))
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
	var hover_pos := Vector2(-1, -1)

	func _gui_input(event: InputEvent) -> void:
		if event is InputEventMouseMotion:
			hover_pos = (event as InputEventMouseMotion).position
			queue_redraw()

	func _plot_rect() -> Rect2:
		return Rect2(Vector2(8, 8), size - Vector2(88, 30))

	func _draw() -> void:
		var plot := _plot_rect()
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
		var endpoints: Array = []
		var all_pts: Array = []
		for s: Dictionary in series:
			var vals: Array = s.get("vals", [])
			if vals.size() < 2:
				all_pts.append(PackedVector2Array())
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
			all_pts.append(pts)
			var scolor: Color = s.get("color", Color.GRAY)
			if s.get("fill", false) and n >= 2:
				var poly := PackedVector2Array(pts)
				poly.append(Vector2(pts[n - 1].x, plot.end.y))
				poly.append(Vector2(pts[0].x, plot.end.y))
				draw_colored_polygon(poly, Color(scolor.r, scolor.g, scolor.b, 0.07))
			draw_polyline(pts, scolor, float(s.get("width", 2.0)), true)
			draw_circle(pts[n - 1], 3.0, scolor)
			endpoints.append({"y": pts[n - 1].y, "color": scolor,
				"text": str(s.get("last_text", ""))})
		# 右缘末值标签(避让重叠)
		endpoints.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
			return float(a["y"]) < float(b["y"]))
		var last_y := -INF
		for ep: Dictionary in endpoints:
			var y := maxf(float(ep["y"]), last_y + 15.0)
			last_y = y
			draw_string(font, Vector2(plot.end.x + 8.0, y + 4.0), str(ep["text"]),
				HORIZONTAL_ALIGNMENT_LEFT, -1, 10, ep["color"])
		# 悬停十字线 + 取值气泡
		if any and plot.has_point(hover_pos):
			draw_line(Vector2(hover_pos.x, plot.position.y),
				Vector2(hover_pos.x, plot.end.y), Color(0.16, 0.25, 0.35, 0.25), 1.0)
			var frac := (hover_pos.x - plot.position.x) / plot.size.x
			var lines: Array = []
			for si in series.size():
				var pts: PackedVector2Array = all_pts[si]
				if pts.is_empty():
					continue
				var idx := clampi(roundi(frac * float(pts.size() - 1)), 0, pts.size() - 1)
				var sdef: Dictionary = series[si]
				draw_circle(pts[idx], 4.2, Color.WHITE)
				draw_circle(pts[idx], 3.0, sdef.get("color", Color.GRAY))
				var vals: Array = sdef.get("vals", [])
				lines.append({"color": sdef.get("color", Color.GRAY),
					"text": "%s  %s" % [str(sdef.get("label", "")),
						str(sdef.get("fmt", Callable()).call(float(vals[idx]))
							if sdef.get("fmt") is Callable else "%.3f" % float(vals[idx]))]})
			if not lines.is_empty():
				var bw := 0.0
				for ln: Dictionary in lines:
					bw = maxf(bw, font.get_string_size(str(ln["text"]),
						HORIZONTAL_ALIGNMENT_LEFT, -1, 10).x)
				var bh := float(lines.size()) * 15.0 + 10.0
				var bx := minf(hover_pos.x + 12.0, plot.end.x - bw - 18.0)
				var by := plot.position.y + 6.0
				draw_rect(Rect2(bx, by, bw + 16.0, bh), Color(1, 1, 1, 0.95))
				draw_rect(Rect2(bx, by, bw + 16.0, bh), Color("d3dce6"), false, 1.0)
				for li in lines.size():
					var ln: Dictionary = lines[li]
					draw_circle(Vector2(bx + 8.0, by + 12.0 + float(li) * 15.0), 3.0,
						ln["color"])
					draw_string(font, Vector2(bx + 15.0, by + 16.0 + float(li) * 15.0),
						str(ln["text"]), HORIZONTAL_ALIGNMENT_LEFT, -1, 10,
						Color("2a3948"))
		if not any:
			draw_string(font, plot.get_center() + Vector2(-140, 0),
				"推进模拟以积累公报序列(发布日历驱动)",
				HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("60758d"))
		draw_string(font, Vector2(plot.end.x - 66, size.y - 6),
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
			var exp_color := Color(0.122, 0.616, 0.388, 0.85)
			draw_line(a + perp * 5.0, b + perp * 5.0, exp_color, wexp, true)
			var tip := (a + perp * 5.0).lerp(b + perp * 5.0, 0.62)
			var ah := 4.0 + wexp
			draw_colored_polygon(PackedVector2Array([
				tip + dir * ah, tip - dir * ah * 0.4 + perp * ah * 0.6,
				tip - dir * ah * 0.4 - perp * ah * 0.6]), exp_color)
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
