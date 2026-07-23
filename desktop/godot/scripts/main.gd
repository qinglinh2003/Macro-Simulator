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
	{"id": "inflation", "label": "通胀(日率)", "color": PURPLE, "bad_up": true, "kind": "pp"},
	{"id": "price_index", "label": "物价指数", "color": BLUE, "bad_up": true, "kind": "num"},
	{"id": "policy_rate", "label": "政策利率", "color": TEAL, "bad_up": false, "kind": "pp"},
	{"id": "gov_deficit_to_gdp", "label": "赤字 / GDP", "color": AMBER, "bad_up": true, "kind": "pp"},
	{"id": "bank_reserves_total", "label": "银行准备金", "color": GREEN, "bad_up": false, "kind": "num"},
	{"id": "poverty_rate", "label": "贫困率", "color": PURPLE, "bad_up": true, "kind": "pp"},
]

# 八维核心指标:每个经济维度只选一个权威公报序列,不读取未发布的逐日状态。
const CORE_DIMENSION_SPEC := [
	{"id": "real_output", "dimension": "增长", "metric": "实际产出", "group": "实体经济", "color": TEAL},
	{"id": "unemployment_rate", "dimension": "就业", "metric": "失业率", "group": "劳动力", "color": AMBER},
	{"id": "inflation", "dimension": "物价", "metric": "通胀", "group": "价格与货币", "color": PURPLE},
	{"id": "gov_deficit_to_gdp", "dimension": "财政", "metric": "赤字/GDP", "group": "财政", "color": BLUE},
	{"id": "credit_to_gdp", "dimension": "金融", "metric": "信贷/GDP", "group": "银行与信贷", "color": TEAL_DK},
	{"id": "poverty_rate", "dimension": "民生", "metric": "贫困率", "group": "分配与福利", "color": GREEN},
	{"id": "population_alive", "dimension": "人口", "metric": "总人口", "group": "人口社会", "color": Color("b0641f")},
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
	"bonds": "国债市场", "capital_market": "资本市场",
	"consumption_strata": "必需品 / 奢侈品分层",
	"demographics_enabled": "人口系统",
	"energy_enabled": "能源部门", "energy_household": "居民能源消费",
	"government": "政府财政账户", "household_credit": "家庭信贷",
	"housing_construction_enabled": "住房建造", "housing_enabled": "住房登记",
	"housing_market_enabled": "住房交易市场", "interbank": "银行间市场",
	"margin_credit": "保证金信贷", "mortgage_enabled": "住房按揭",
	"national_accounts_metrics": "国民账户",
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

# 不能可靠地由字段名推出的核心机制。其余比例、上下限、税率和制度开关由下方
# 规则生成定义；所有说明仍以 registry 的 read_point / semantics 为机制边界。
const POLICY_HELP := {
	"gov_consumption_share": {
		"definition": "政府用于购买商品和服务的目标支出比例。",
		"effect": "提高通常直接扩大公共需求和企业订单，同时增加财政支出；存在赤字目标时可能被该规则覆盖。"},
	"gov_deficit_target": {
		"definition": "财政规则希望维持的政府赤字相对经济规模的目标。",
		"effect": "提高会允许更强的财政净注入，通常支撑需求与就业，但也会更快累积政府债务。"},
	"deficit_u_ref": {
		"definition": "逆周期赤字规则判断劳动力市场松弛程度时采用的失业率参照。",
		"effect": "改变自动稳定器开始扩张或收缩的失业基准，影响财政对就业波动的敏感度。"},
	"deficit_u_cap": {
		"definition": "失业压力最多能够触发的额外逆周期赤字规模。",
		"effect": "提高会放大衰退时的财政托底上限，但增加高失业阶段的借款与债务压力。"},
	"benefit_replacement": {
		"definition": "失业救济相对参考工资的支付比例。",
		"effect": "提高可稳定失业家庭收入和消费，但增加财政支出，并可能改变求职与就业保障计划之间的选择。"},
	"benefit_income_floor": {
		"definition": "在职低收入者可获得补足时采用的最低收入保障标准。",
		"effect": "提高可改善低收入劳动者收入与消费，同时扩大财政转移支付。"},
	"job_guarantee": {
		"definition": "政府是否向未被市场吸收的劳动者提供就业保障岗位。",
		"effect": "启用后可直接吸收失业劳动力并形成收入底线，但需要财政支出并可能与私人部门争夺劳动。"},
	"jg_wage_ratio": {
		"definition": "就业保障岗位工资相对市场参考工资的比例。",
		"effect": "提高会强化工资与收入底线，也会提高公共用工成本并影响私人部门招聘。"},
	"bond_finance_frac": {
		"definition": "财政赤字中通过发行国债而非其他结算方式融资的比例。",
		"effect": "提高会增加国债供给、利息现金流和金融机构可持有的安全资产。"},
	"bond_coupon": {
		"definition": "新发行国债承诺支付的票面利率。",
		"effect": "提高会改善新债对投资者的吸引力，但抬升政府未来利息支出；既有债券票息不会被追溯改写。"},
	"bond_maturity": {
		"definition": "新发行国债从发行到到期偿还的期限。",
		"effect": "延长期限降低短期再融资频率，但增加久期风险；只影响生效后发行的新债。"},
	"monetary_regime": {
		"definition": "政策利率路径采用外生利率、泰勒规则还是手动钉住。",
		"effect": "切换会改变整个利率形成机制，并影响信贷成本、存款收益、资产估值和汇率压力。"},
	"manual_policy_rate": {
		"definition": "手动货币制度下直接钉住的每日政策利率。",
		"effect": "提高通常收紧融资条件并压低需求与估值；降低则相反。仅在手动制度下有效。"},
	"inflation_target": {
		"definition": "泰勒规则判断通胀偏离时采用的每日通胀目标。",
		"effect": "提高目标会在同等通胀下形成更宽松的利率反应；降低目标通常使政策更偏紧。"},
	"taylor_phi_pi": {
		"definition": "泰勒规则对通胀缺口的反应强度。",
		"effect": "提高会让政策利率对通胀偏离作出更大幅度的反应。"},
	"taylor_phi_u": {
		"definition": "泰勒规则对失业缺口的反应强度。",
		"effect": "提高会让政策利率更积极地回应劳动力市场偏冷或偏热。"},
	"rate_inertia": {
		"definition": "当前政策利率在下一期利率决策中保留的权重。",
		"effect": "提高会让利率路径更平滑但响应更慢；降低会加快政策调整。"},
	"infl_ema_lambda": {
		"definition": "通胀平滑指标赋予最新观测的权重。",
		"effect": "提高会让央行更重视近期通胀、反应更快；降低会增强历史平滑。"},
	"omo": {
		"definition": "央行是否通过公开市场操作调节银行准备金。",
		"effect": "启用后央行可围绕准备金目标注入或回笼流动性，影响同业资金条件和银行放贷能力。"},
	"lolr": {
		"definition": "央行是否向遭遇流动性压力但仍可处置的银行提供最后贷款人支持。",
		"effect": "启用可减少流动性冲击演变为银行倒闭的风险，但会扩大央行风险暴露。"},
	"reserve_floor_frac": {
		"definition": "银行准备金相对相关负债必须维持的最低比例。",
		"effect": "提高会增强流动性缓冲，同时占用可用于放贷和投资的资金。"},
	"fx_regime": {
		"definition": "本国汇率采用市场浮动还是盯住锚国货币。",
		"effect": "联系汇率降低名义汇率波动，但需要储备防守并约束国内政策空间；浮动汇率允许价格自行调整。"},
	"peg_anchor": {
		"definition": "联系汇率制度引用其货币价值的锚定经济体。",
		"effect": "更换锚国会重配外汇储备并把本国汇率路径连接到新的参照货币。"},
	"peg_reserve_scale": {
		"definition": "联系汇率防守机制可动用的目标储备规模。",
		"effect": "提高通常增强抵御资本流动和汇率压力的能力，但占用更多外部资产。"},
	"capital_control": {
		"definition": "限制跨境资本流动的强度。",
		"effect": "提高可减缓资本外流和联汇压力，但也压低跨境融资与资本配置。"},
	"bank_capital_constraint": {
		"definition": "银行放贷是否受资本充足约束。",
		"effect": "启用后资本不足的银行会收缩信贷，增强偿付韧性但可能抑制融资和投资。"},
	"bank_target_capital_ratio": {
		"definition": "银行经营时希望维持的资本相对风险资产比例。",
		"effect": "提高会促使银行积累更多资本并更谨慎放贷，降低破产风险但收紧信贷。"},
	"bank_leverage_cap": {
		"definition": "银行总资产相对资本所允许的最高倍数。",
		"effect": "下调会收紧杠杆约束、提高韧性，但可能迫使银行缩减信贷资产。"},
	"mortgage_ltv_cap": {
		"definition": "按揭贷款相对住房抵押价值所允许的最高比例。",
		"effect": "下调要求更高首付并降低银行损失风险，但减少能够获得按揭的家庭。"},
	"mortgage_dsti_cap": {
		"definition": "家庭按揭偿债额相对收入所允许的最高比例。",
		"effect": "下调会加强偿付能力审查并降低违约风险，同时收紧住房信贷。"},
	"energy_rationing": {
		"definition": "能源短缺时在居民与产业之间分配有限供给的优先规则。",
		"effect": "居民优先保护家庭消费，产业优先保护生产；只在供给不足时产生实际差异。"},
	"energy_price_cap": {
		"definition": "能源市场成交价格不得超过的最高水平；零值表示关闭限价。",
		"effect": "下调可压低用户支付价格，但可能放大短缺；配合补偿可缓解供应方损失并增加财政成本。"},
	"spr_target_units": {
		"definition": "政府希望战略能源储备维持的实物库存规模。",
		"effect": "提高增强未来短缺缓冲，但当前补库会增加需求和财政占用。"},
	"spr_flow_cap": {
		"definition": "战略能源储备每日最多可买入或释放的实物量。",
		"effect": "提高可加快危机释放或补库速度，也会放大对当日市场供需的影响。"},
	"sanctions_imposed_on": {
		"definition": "本国当前主动施加贸易制裁的经济体名单。",
		"effect": "加入目标会切断双方贸易流；移除只撤销本国施加的那一份制裁。"},
	"tariff": {
		"definition": "进口商品进入本国市场时征收的从价税率。",
		"effect": "提高通常保护国内生产并增加关税收入，但抬高进口成本并压低进口数量。"},
	"import_quota": {
		"definition": "允许进入本国市场的进口数量上限；不设置表示没有配额。",
		"effect": "下调会直接限制进口供给，可能保护本国产业，也可能造成价格上涨或投入短缺。"},
	"export_subsidy": {
		"definition": "政府对出口交易给予的补贴比例；负值等价于出口税。",
		"effect": "提高可改善出口竞争力和海外份额，但需要财政支出并可能挤压国内供给。"},
}


# 指标全景：所有已启用玩家领域各有独立页签；键名与后端 records 一致。
# fmt: pct=份额%, pt=每tick利率%, idx=指数, num=水平量
const PANEL_GROUPS := [
	{"name": "实体经济", "color": TEAL, "items": [
		["real_output", "实际产出", "num"], ["real_consumption", "实际消费", "num"],
		["aggregate_capital", "资本存量", "num"], ["investment_spending", "投资支出", "num"],
		["inventory_to_sales", "库存/销售", "idx"], ["production_realization_rate", "生产实现率", "pct"]]},
	{"name": "国民账户", "color": Color("286f9f"), "requires": "national_accounts_metrics", "items": [
		["gdp_nominal_expenditure_reconciled", "名义 GDP", "num"],
		["gdp_real_expenditure_reconciled", "实际 GDP", "num"],
		["gdp_deflator", "GDP 平减指数", "idx"],
		["gdp_nominal_household_consumption", "居民消费", "num"],
		["gdp_nominal_fixed_capital_formation", "资本形成", "num"],
		["gdp_nominal_net_exports", "净出口", "num"]]},
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
	{"name": "银行与信贷", "color": TEAL_DK, "requires": "bank_enabled", "items": [
		["total_credit", "信贷总量", "num"], ["bank_capital", "银行资本", "num"],
		["bank_deposit_total", "存款总额", "num"], ["writeoffs", "坏账核销", "num"],
		["total_debt_service_ratio", "偿债比率", "pct"], ["interbank_rate", "同业利率", "pt"]]},
	{"name": "债务与风险", "color": Color("a35454"), "requires": "bank_enabled", "items": [
		["household_debt_total", "家庭债务", "num"],
		["firm_debt_total", "企业债务", "num"],
		["debt_service_to_nominal_gdp", "偿债/GDP", "pct"],
		["household_interest_arrears_closing", "家庭利息拖欠", "num"],
		["bank_realized_credit_losses", "银行信用损失", "num"],
		["hh_bankruptcies", "家庭破产", "num"]]},
	{"name": "资本市场", "color": Color("4a6fa5"), "requires": "capital_market", "items": [
		["equity_market_cap", "股票市值", "num"], ["tobin_q_mean", "托宾 Q", "idx"],
		["equity_wealth_share", "股权财富占比", "pct"], ["equity_turnover", "换手率", "idx"],
		["equity_ownership_gini", "持股基尼", "idx"], ["hh_wealth_gini_incl_equity", "财富基尼(含股)", "idx"]]},
	{"name": "住房市场", "color": Color("8a6b50"), "requires": "housing_enabled", "items": [
		["house_price", "住房价格", "num"], ["homeowner_share", "自有住房率", "pct"],
		["housing_pti_ratio", "房价收入比", "idx"],
		["housing_sales_session", "本期成交", "num"],
		["mortgage_balance_total", "按揭余额", "num"],
		["rent_burden_ratio", "租金负担率", "pct"]]},
	{"name": "能源", "color": Color("b0641f"), "requires": "energy_enabled", "items": [
		["energy_price", "能源价格", "idx"], ["energy_produced", "能源产量", "num"],
		["energy_used", "能源消耗", "num"], ["energy_stock_total", "能源库存", "num"],
		["energy_cost_share", "能源成本占比", "pct"], ["spr_stock", "战略储备", "num"]]},
	{"name": "外部部门", "color": Color("4a6fa5"), "items": [
		["e", "汇率", "idx"], ["nfa", "净对外资产", "num"],
		["current_account", "经常账户", "num"], ["import_value", "进口额", "num"],
		["export_delivered_volume", "出口交付", "num"],
		["remittances", "跨境汇款", "num"]]},
	{"name": "分配与福利", "color": Color("8a5fc0"), "items": [
		["poverty_rate", "贫困率", "pct"], ["income_gini", "收入基尼", "idx"],
		["hh_wealth_gini", "财富基尼", "idx"], ["wage_p90_p10_ratio", "工资 P90/P10", "idx"],
		["welfare_log", "对数福利", "idx"], ["savings_rate", "储蓄率", "pct"]]},
	{"name": "人口社会", "color": Color("2a8a68"), "requires": "demographics_enabled", "items": [
		["population_alive", "总人口", "num"],
		["net_population_growth_rate_annualized", "人口自然增长率", "pct"],
		["birth_rate_per_1000_annualized", "粗出生率", "per_thousand"],
		["death_rate_per_1000_annualized", "粗死亡率", "per_thousand"],
		["dependency_ratio", "总抚养比", "pct"],
		["avg_household_size", "户均规模", "idx"]]},
	{"name": "企业生态", "color": Color("3e7d68"), "items": [
		["firm_count_c", "消费品企业", "num"], ["births", "企业进入", "num"],
		["deaths", "企业退出", "num"], ["n_firms_producing", "生产中企业", "num"],
		["sector_switches", "产业切换", "num"],
		["firm_size_top_share_output", "头部产出份额", "pct"]]},
]

# 每个指标页签使用独立的信息架构。标量历史来自 records，人口、劳动和企业截面
# 来自 desktop runtime 的只读微观聚合；行业名称严格对应模型中的真实部门。
const PANEL_DESCRIPTIONS := {
	"实体经济": "需求、供给与资本形成的同步状态",
	"国民账户": "支出法总量、行业产出与三种核算口径的一致性",
	"劳动力": "就业松弛、岗位缺口与工资脉冲",
	"价格与货币": "价格压力、货币立场与购买力",
	"财政": "收支流量、债务存量与财政空间",
	"银行与信贷": "信用扩张、银行缓冲与偿付压力",
	"债务与风险": "家庭与企业杠杆、拖欠、破产和信用损失",
	"资本市场": "市场规模、估值活跃度与所有权分布",
	"住房市场": "住房存量、交易、按揭、租赁与建设供给",
	"能源": "供需平衡、价格成本与安全库存",
	"外部部门": "汇率、贸易、跨境资产、迁移与汇款",
	"分配与福利": "贫困、储蓄、福利与不平等结构",
	"人口社会": "人口结构、家庭形成、自然变动与代际负担",
	"企业生态": "企业进入退出、经营覆盖、集中度与产业切换",
}

const PANEL_CHARTS := {
	"实体经济": [
		{"type": "sector_matrix", "title": "SECTORS · 部门生产图谱", "note": "产出 · 销售 · 就业",
			"items": []},
		{"type": "line", "title": "DEMAND · 产出与消费", "note": "实际量",
			"items": [["real_output", "实际产出", "num", TEAL],
				["real_consumption", "实际消费", "num", BLUE]]},
		{"type": "line", "title": "CAPITAL · 资本形成", "note": "期初指数=100", "indexed": true,
			"items": [["aggregate_capital", "资本存量", "num", BLUE],
				["investment_spending", "投资支出", "num", AMBER],
				["real_output", "实际产出", "num", TEAL]]},
	],
	"国民账户": [
		{"type": "line", "title": "GDP · 名义与实际总量", "note": "期初指数=100", "indexed": true,
			"items": [["gdp_nominal_expenditure_reconciled", "名义 GDP", "num", BLUE],
				["gdp_real_expenditure_reconciled", "实际 GDP", "num", TEAL],
				["gdp_deflator", "平减指数", "idx", PURPLE]]},
		{"type": "columns", "title": "EXPENDITURE · 支出法构成", "note": "C + I + G + NX",
			"items": [["gdp_nominal_household_consumption", "居民消费 C", "num", TEAL],
				["gdp_nominal_fixed_capital_formation", "资本形成 I", "num", BLUE],
				["gdp_nominal_government_consumption", "政府消费 G", "num", PURPLE],
				["gdp_nominal_net_exports", "净出口 NX", "num", AMBER]]},
		{"type": "columns", "title": "SECTORS · 行业总产出", "note": "当期名义总产出",
			"items": [["gdp_nominal_gross_output_c", "消费品", "num", TEAL],
				["gdp_nominal_gross_output_k", "资本品", "num", BLUE],
				["gdp_nominal_gross_output_e", "能源", "num", AMBER],
				["gdp_nominal_gross_output_housing", "住房建设", "num", Color("8a6b50")]]},
		{"type": "line", "title": "RECONCILIATION · 核算质量", "note": "三种核算口径原始差额占比",
			"items": [["gdp_nominal_three_approach_raw_spread_share", "原始差额率", "pct", RED]]},
		{"type": "line", "title": "APPROACHES · 三种 GDP 口径", "note": "名义值 · 支出法 / 收入法 / 生产法",
			"items": [["gdp_nominal_expenditure_reconciled", "支出法", "num", BLUE],
				["gdp_nominal_income_reconciled", "收入法", "num", PURPLE],
				["gdp_nominal_production", "生产法", "num", TEAL]]},
		{"type": "columns", "title": "INCOME · 收入法构成", "note": "雇员报酬、营业盈余与产品税净额",
			"items": [["gdp_nominal_compensation_of_employees", "雇员报酬", "num", BLUE],
				["gdp_nominal_accrued_gross_operating_surplus", "营业盈余", "num", TEAL],
				["gdp_nominal_net_product_taxes_observed", "产品税净额", "num", AMBER]]},
		{"type": "columns", "title": "CAPITAL FORMATION · 资本形成明细", "note": "私人、公共、住宅与机器设备",
			"items": [["gdp_nominal_private_fixed_capital_formation", "私人投资", "num", TEAL],
				["gdp_nominal_public_fixed_capital_formation", "公共投资", "num", BLUE],
				["gdp_nominal_residential_fixed_capital_formation", "住宅投资", "num", Color("8a6b50")],
				["gdp_nominal_machinery_fixed_capital_formation", "机器设备", "num", PURPLE]]},
		{"type": "line", "title": "TRADE & INVENTORY · 外贸与库存", "note": "名义流量",
			"items": [["gdp_nominal_exports", "出口", "num", TEAL],
				["gdp_nominal_imports", "进口", "num", BLUE],
				["gdp_nominal_inventory_change", "存货变动", "num", AMBER]]},
		{"type": "line", "title": "REAL EXPENDITURE · 实际支出构成", "note": "剔除价格变化后的 C / I / G / NX",
			"items": [["gdp_real_household_consumption", "居民消费 C", "num", TEAL],
				["gdp_real_fixed_capital_formation", "资本形成 I", "num", BLUE],
				["gdp_real_government_consumption", "政府消费 G", "num", PURPLE],
				["gdp_real_net_exports", "净出口 NX", "num", AMBER]]},
		{"type": "line", "title": "TRADE VOLUME · 实际进出口", "note": "以共同基期价格计量",
			"items": [["gdp_real_exports", "实际出口", "num", TEAL],
				["gdp_real_imports", "实际进口", "num", BLUE]]},
	],
	"劳动力": [
		{"type": "employment_sectors", "title": "SECTORS · 部门就业结构", "note": "主业+第二职业 FTE"},
		{"type": "labor_flows", "title": "FLOWS · 劳动力状态与流转", "note": "本次推进的实名账本流量"},
		{"type": "age_participation", "title": "LFPR · 分年龄劳动参与率", "note": "参与率与就业率 · 劳龄口径 18–64"},
	],
	"价格与货币": [
		{"type": "line", "title": "RATES · 价格与利率脉冲", "note": "每日变化率",
			"items": [["inflation", "通胀", "pt", PURPLE],
				["policy_rate", "政策利率", "pt", TEAL],
				["wage_inflation", "工资通胀", "pt", AMBER]]},
		{"type": "line", "title": "PURCHASING POWER · 购买力", "note": "期初指数=100", "indexed": true,
			"items": [["price_index", "物价指数", "idx", BLUE],
				["real_wage", "实际工资", "idx", TEAL],
				["avg_markup", "平均加成", "idx", PURPLE]]},
		{"type": "columns", "title": "STANCE · 当前利率组合", "note": "名义变化率",
			"items": [["inflation", "通胀", "pt", PURPLE],
				["policy_rate", "政策利率", "pt", TEAL],
				["wage_inflation", "工资通胀", "pt", AMBER]]},
	],
	"财政": [
		{"type": "fiscal_flow", "title": "BUDGET MAP · 财政资金地图", "note": "收入来源与支出去向"},
		{"type": "line", "title": "DEBT · 债务轨迹", "note": "期初指数=100", "indexed": true,
			"items": [["gov_debt", "政府债务", "num", BLUE],
				["gov_debt_to_gdp", "债务/GDP", "pct", AMBER]]},
		{"type": "columns", "title": "BUDGET · 本期预算截面", "note": "收支规模",
			"items": [["tax_total", "税收", "num", TEAL],
				["gov_spending", "支出", "num", BLUE],
				["benefit_paid", "转移", "num", PURPLE],
				["gov_deficit", "赤字", "num", AMBER]]},
	],
	"银行与信贷": [
		{"type": "bank_balance", "title": "BALANCE SHEET · 银行资产负债", "note": "信贷资产 · 存款负债 · 资本缓冲"},
		{"type": "line", "title": "STRESS · 偿付与资金价格", "note": "压力指标",
			"items": [["total_debt_service_ratio", "偿债比率", "pct", AMBER],
				["interbank_rate", "同业利率", "pt", PURPLE],
				["writeoffs", "坏账核销", "num", RED]]},
		{"type": "columns", "title": "CREDIT MIX · 信贷去向", "note": "当前贷款存量",
			"items": [["firm_debt_total", "企业", "num", TEAL],
				["household_debt_total_observed", "居民", "num", BLUE],
				["new_loans_total", "本期新增", "num", GREEN],
				["bank_realized_credit_losses", "信用损失", "num", RED]]},
		{"type": "columns", "title": "SYSTEM · 银行体系结构", "note": "机构、同业交易与传染损失",
			"items": [["banks_alive", "存续银行", "num", TEAL],
				["bank_births", "新设", "num", GREEN],
				["bank_deaths", "退出", "num", AMBER],
				["n_bank_failures", "失败", "num", RED],
				["interbank_volume", "同业成交", "num", BLUE],
				["interbank_contagion_loss", "传染损失", "num", PURPLE]]},
	],
	"债务与风险": [
		{"type": "line", "title": "LEVERAGE · 债务存量", "note": "家庭与企业",
			"items": [["household_debt_total", "家庭债务", "num", BLUE],
				["firm_debt_total", "企业债务", "num", TEAL]]},
		{"type": "line", "title": "SERVICE · 偿债与拖欠", "note": "当期压力",
			"items": [["household_contractual_debt_service_due", "合同应偿", "num", BLUE],
				["household_debt_service_reserved", "已预留偿债", "num", GREEN],
				["household_interest_arrears_closing", "期末拖欠", "num", RED],
				["bank_realized_credit_losses", "银行损失", "num", AMBER]]},
		{"type": "bars", "title": "CONCENTRATION · 债务集中度", "note": "Gini 与前10%份额",
			"items": [["household_debt_gini", "家庭债务 Gini", "idx", BLUE],
				["household_debt_top10_share", "家庭前10%", "pct", PURPLE],
				["firm_debt_gini", "企业债务 Gini", "idx", TEAL],
				["firm_debt_top10_share", "企业前10%", "pct", AMBER]]},
		{"type": "columns", "title": "DISTRESS · 风险事件", "note": "新增信贷、破产与偿债率",
			"items": [["new_loans", "新增贷款", "num", GREEN],
				["hh_bankruptcies", "家庭破产", "num", RED],
				["debt_service_to_nominal_gdp", "偿债/GDP", "pct", AMBER],
				["total_debt_service_to_nominal_gdp", "总偿债/GDP", "pct", PURPLE]]},
		{"type": "line", "title": "ARREARS LEDGER · 家庭利息拖欠账", "note": "期初、核销、商品预留与期末存量",
			"items": [["household_interest_arrears_opening", "期初拖欠", "num", AMBER],
				["household_interest_arrears_extinguished", "已消除", "num", GREEN],
				["household_interest_arrears_in_goods_reservation", "商品预留", "num", BLUE],
				["household_interest_arrears_closing", "期末拖欠", "num", RED],
				["household_interest_arrears_stock_flow_residual", "账流差额", "num", PURPLE]]},
	],
	"资本市场": [
		{"type": "firm_bubbles", "title": "VALUATION MAP · 企业估值分布", "note": "横轴 Q · 纵轴投资 · 气泡=市值"},
		{"type": "line", "title": "VALUATION · 估值与交易", "note": "指数",
			"items": [["tobin_q_mean", "托宾 Q", "idx", TEAL],
				["tobin_q_dispersion", "Q 离散度", "idx", PURPLE],
				["equity_turnover", "换手率", "idx", AMBER]]},
		{"type": "bars", "title": "OWNERSHIP · 所有权分布", "note": "份额 / Gini",
			"items": [["equity_wealth_share", "股权财富占比", "pct", TEAL],
				["equity_ownership_gini", "持股基尼", "idx", PURPLE],
				["hh_wealth_gini_incl_equity", "财富基尼", "idx", BLUE]]},
	],
	"住房市场": [
		{"type": "line", "title": "PRICE · 房价、租金与负担", "note": "期初指数=100", "indexed": true,
			"items": [["house_price", "住房价格", "num", Color("8a6b50")],
				["rent_level", "租金水平", "num", TEAL],
				["housing_pti_ratio", "房价收入比", "idx", AMBER],
				["rent_burden_ratio", "租金负担", "pct", PURPLE]]},
		{"type": "columns", "title": "LIQUIDITY · 交易流动性", "note": "挂牌、成交与在市时间",
			"items": [["housing_listings", "挂牌", "num", BLUE],
				["housing_sales_session", "本期成交", "num", GREEN],
				["housing_tom", "平均在市期", "num", AMBER],
				["housing_forced_share", "强制出售", "pct", RED]]},
		{"type": "columns", "title": "MORTGAGE · 按揭与处置", "note": "存量、发放与法拍",
			"items": [["mortgage_count", "按揭笔数", "num", BLUE],
				["mortgage_balance_total", "按揭余额", "num", TEAL],
				["mortgage_originated_tick", "本期发放", "num", GREEN],
				["foreclosures_total", "累计法拍", "num", RED]]},
		{"type": "bars", "title": "TENURE · 居住与租赁结构", "note": "自有、租赁、空置与房东",
			"items": [["homeowner_share", "自有住房率", "pct", TEAL],
				["tenant_share", "租户占比", "pct", BLUE],
				["rental_vacancies", "出租空置", "num", AMBER],
				["landlord_count", "房东家庭", "num", PURPLE]]},
		{"type": "columns", "title": "SUPPLY · 住房建设供给", "note": "竣工、在建、库存与许可",
			"items": [["dwellings_built_total", "累计竣工", "num", GREEN],
				["builder_wip_units", "在建工程", "num", BLUE],
				["builder_inventory_units", "待售库存", "num", AMBER],
				["permits_used_year", "年度许可使用", "num", PURPLE],
				["builder_employment", "建造就业", "num", TEAL]]},
	],
	"能源": [
		{"type": "energy_flow", "title": "FLOW · 能源平衡", "note": "生产 → 销售/使用 → 库存"},
		{"type": "line", "title": "COST · 价格与成本", "note": "期初指数=100", "indexed": true,
			"items": [["energy_price", "能源价格", "idx", Color("b0641f")],
				["energy_cost_share", "能源成本占比", "pct", RED],
				["e_capacity_utilization", "产能利用率", "pct", TEAL]]},
		{"type": "columns", "title": "SECURITY · 供给与库存", "note": "能源实物量",
			"items": [["energy_produced", "产量", "num", GREEN],
				["energy_used", "消耗", "num", AMBER],
				["energy_stock_total", "商业库存", "num", BLUE],
				["spr_stock", "战略储备", "num", PURPLE]]},
	],
	"外部部门": [
		{"type": "line", "title": "TRADE · 进口与出口", "note": "交易与交付规模",
			"items": [["import_value", "进口额", "num", BLUE],
				["export_delivered_volume", "出口交付", "num", TEAL]]},
		{"type": "line", "title": "BALANCE · 经常账户与净资产", "note": "本国口径",
			"items": [["current_account", "经常账户", "num", AMBER],
				["nfa", "净对外资产", "num", PURPLE]]},
		{"type": "line", "title": "FX · 汇率轨迹", "note": "本币/共同计价单位 · 期初=100", "indexed": true,
			"items": [["e", "汇率", "idx", Color("4a6fa5")]]},
		{"type": "columns", "title": "MOBILITY · 人口与汇款", "note": "跨境人口存量与资金流",
			"items": [["migrant_stock", "移民存量", "num", TEAL],
				["remittances", "跨境汇款", "num", BLUE],
				["tariff_rev", "关税收入", "num", AMBER]]},
	],
	"分配与福利": [
		{"type": "lorenz", "title": "LORENZ · 收入与正净财富分布", "note": "越贴近对角线越均等"},
		{"type": "line", "title": "WELFARE · 福利与工资分位", "note": "期初指数=100", "indexed": true,
			"items": [["welfare_log", "对数福利", "idx", GREEN],
				["wage_p90_p10_ratio", "工资 P90/P10", "idx", AMBER],
				["bottom10_consumption", "底部10%消费", "num", BLUE]]},
		{"type": "deciles", "title": "DECILES · 十分位资源份额", "note": "收入与消费各组占比"},
	],
	"人口社会": [
		{"type": "pyramid", "title": "AGE · 人口金字塔", "note": "男左女右 · 当前存活人口"},
		{"type": "line", "title": "DEMOGRAPHY · 人口自然变动", "note": "每日事件",
			"items": [["births_tick", "出生", "num", TEAL],
				["deaths_tick", "死亡", "num", RED],
				["marriages_tick", "结婚", "num", BLUE],
				["divorces_tick", "离婚", "num", AMBER]]},
		{"type": "columns", "title": "DEPENDENCY · 年龄与抚养结构", "note": "人数与抚养比",
			"items": [["child_population", "儿童", "num", BLUE],
				["working_age_population", "劳龄人口", "num", TEAL],
				["elder_population", "老年人口", "num", PURPLE],
				["dependency_ratio", "总抚养比", "pct", AMBER]]},
		{"type": "line", "title": "RATES · 人口率", "note": "年化自然增长与每千人粗率",
			"items": [["net_population_growth_rate_annualized", "自然增长率", "pct", GREEN],
				["birth_rate_per_1000_annualized", "粗出生率", "per_thousand", TEAL],
				["death_rate_per_1000_annualized", "粗死亡率", "per_thousand", RED]]},
		{"type": "bars", "title": "GENERATIONS · 代际人口结构", "note": "儿童、成年人和老年人口占比",
			"items": [["child_share", "儿童", "pct", BLUE],
				["adult_share", "成年人", "pct", TEAL],
				["elder_share", "老年人", "pct", PURPLE]]},
		{"type": "columns", "title": "CONSUMPTION · 代际消费中位数", "note": "按个人年龄组统计",
			"items": [["child_median_consumption", "儿童", "num", BLUE],
				["adult_median_consumption", "成年人", "num", TEAL],
				["elder_median_consumption", "老年人", "num", PURPLE]]},
	],
	"企业生态": [
		{"type": "sector_matrix", "title": "SECTORS · 企业部门生态", "note": "企业数 · 产销 · 用工"},
		{"type": "line", "title": "DEMOGRAPHY · 企业进入退出", "note": "当期企业事件与存量",
			"items": [["firm_count_c", "消费品企业", "num", TEAL],
				["births", "企业进入", "num", GREEN],
				["deaths", "企业退出", "num", RED]]},
		{"type": "columns", "title": "ACTIVITY · 经营覆盖", "note": "生产、销售与融资",
			"items": [["n_firms_producing", "生产中", "num", TEAL],
				["n_firms_selling", "销售中", "num", BLUE],
				["n_firms_borrowing", "借款企业", "num", AMBER],
				["sector_switches", "产业切换", "num", PURPLE]]},
		{"type": "bars", "title": "CONCENTRATION · 企业规模结构", "note": "产出集中度与 Pareto 斜率",
			"items": [["firm_size_gini_output", "规模 Gini", "idx", PURPLE],
				["firm_size_top_share_output", "头部产出份额", "pct", AMBER],
				["firm_size_pareto_slope", "Pareto 斜率", "idx", BLUE],
				["sector_switch_capital", "切换重置资本", "num", RED]]},
	],
}

const WORLD_COMPARE := [
	["real_output", "实际产出", "num"], ["unemployment_rate", "失业率", "pct"],
	["inflation", "通胀", "pt"], ["price_index", "物价指数", "idx"],
	["avg_wage", "平均工资", "num"], ["policy_rate", "政策利率", "pt"],
]

const RANK_METRICS := [
	["score", "综合", "score", false],
	["real_output", "GDP", "num", false], ["unemployment_rate", "失业率", "pct", true],
	["inflation", "通胀", "pt", true], ["avg_wage", "工资", "num", false],
]

var _client
var _outbox: Array = []
var _active_command: Dictionary = {}
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
var _mode := "interactive"
var _tab := "focus"
var _rank_by := "score"
var _score_country := 0               # 世界视图国家表现雷达当前选中经济体
var _goto_panel_group := ""            # 指标全景当前独立页签；核心卡片点击可直达
var _household_selected := -1         # 家庭页当前选中的 demographic household id
var _person_selected := -1            # 企业深链定位到的家庭成员 id
var _household_search := ""           # 家庭号 / 成员号筛选
var _household_sort := "net_worth"    # net_worth | members | debt
var _firm_selected := ""              # 企业页当前选中的 firm id
var _firm_search := ""                # 企业号 / 部门 / 员工号筛选
var _firm_sort := "revenue"           # revenue | earnings | assets
var _stock_selected := ""             # 股市主图当前证券；空=综合指数
var _stock_search := ""               # 行情表代码 / 板块筛选
var _stock_filter := "all"             # all | company | bank
var _stock_sort := "market_cap"        # market_cap | change
var _event_filter := "important"       # important | all | mine
var _last_toasted := ""
var _capture_path := ""
var _capture_ticks := 0
var _capture_target := -1
var _capture_policy_info := ""
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
var _new_game_pending := false


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
		_ensure_start_menu()
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
	var pre_panel := OS.get_environment("MACRO_SIM_CAPTURE_PANEL")
	if not pre_panel.is_empty():
		_goto_panel_group = pre_panel
	var pre_country := OS.get_environment("MACRO_SIM_CAPTURE_COUNTRY")
	if pre_country.is_valid_int():
		_score_country = maxi(0, pre_country.to_int())
	var pre_household := OS.get_environment("MACRO_SIM_CAPTURE_HOUSEHOLD")
	if pre_household.is_valid_int():
		_household_selected = pre_household.to_int()
	var pre_person := OS.get_environment("MACRO_SIM_CAPTURE_PERSON")
	if pre_person.is_valid_int():
		_person_selected = pre_person.to_int()
	var pre_firm := OS.get_environment("MACRO_SIM_CAPTURE_FIRM")
	if not pre_firm.is_empty():
		_firm_selected = pre_firm
	var pre_seat := OS.get_environment("MACRO_SIM_CAPTURE_SEAT")
	if not pre_seat.is_empty():
		_active_seat = pre_seat
	var pre_lever := OS.get_environment("MACRO_SIM_CAPTURE_LEVER")
	if not pre_lever.is_empty():
		_expanded_lever = pre_lever
	_capture_policy_info = OS.get_environment("MACRO_SIM_CAPTURE_POLICY_INFO")


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
		KEY_N:
			_advance_to_next_decision()
		KEY_ESCAPE:
			if _demo_crisis:
				_demo_crisis = false
				_render()


func _ensure_start_menu() -> void:
	if _start_menu != null:
		return
	_start_menu = StartMenuScript.new()
	_start_menu.launch_requested.connect(_on_start_menu_launch)
	_start_menu.continue_requested.connect(_on_start_menu_continue)
	add_child(_start_menu)
	if not _schemas.is_empty() and _start_menu.has_method("set_policy_schemas"):
		_start_menu.call("set_policy_schemas", _start_menu_policy_schemas())


func _on_start_menu_continue() -> void:
	_playing = false
	_confirm.clear()
	if _start_menu != null:
		_start_menu.hide()
	_render()


func _request_return_to_main_menu() -> void:
	var was_playing := _playing
	_playing = false
	_confirm = {
		"title": "返回主菜单",
		"body": "当前模拟将暂停。返回主菜单后，可以选择“继续模拟”回到当前世界，也可以配置并启动一个新世界。",
		"note": "返回主菜单不会重置当前世界；只有启动新模拟时，当前世界才会被替换。",
		"on_cancel": func() -> void: _playing = was_playing,
		"on_yes": _return_to_main_menu,
	}
	_render()


func _return_to_main_menu() -> void:
	_playing = false
	_outbox.clear()
	_ensure_start_menu()
	if _start_menu.has_method("open_home"):
		_start_menu.call("open_home", true)


func _on_start_menu_launch(config: Dictionary) -> void:
	_playing = false
	_outbox.clear()
	var draft: Dictionary = config.get("spec", {})
	_new_game_draft = draft.duplicate(true)
	_mode = str(draft.get("run_mode", "interactive"))
	if _mode not in ["interactive", "realtime", "batch"]:
		_mode = "interactive"
	_new_game_pending = true
	_send({"command": "new_game", "spec": draft})


# ================= 通信 =================
func _send(command: Dictionary) -> void:
	_outbox.append(command)
	_pump()


func _pump() -> void:
	if _client == null or _client.busy or _outbox.is_empty():
		return
	_active_command = _outbox.pop_front()
	_client.send_command(_active_command)


func _on_connected() -> void:
	_set_text("conn", "引擎在线")
	_send({"command": "hello"})
	_send({"command": "get_schema"})


func _on_response(response: Dictionary) -> void:
	var payload: Dictionary = response.get("snapshot", {})
	if payload.has("seats") and payload.has("levers"):
		_schemas = payload.get("seats", {})
		_index_schema()
		if _start_menu != null and _start_menu.has_method("set_policy_schemas"):
			_start_menu.call("set_policy_schemas", _start_menu_policy_schemas())
	else:
		var manifest: Dictionary = payload.get("new_game", {})
		if _new_game_pending \
				and str(_active_command.get("command", "")) == "new_game" \
				and _new_game_response_matches_draft(manifest):
			_new_game_pending = false
			_reset_client_for_new_game(payload)
			_outbox.append({"command": "get_schema"})
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
	if not _capture_policy_info.is_empty() and _lever_info.has(_capture_policy_info) \
			and not _snapshot.is_empty():
		var info_lever: Dictionary = _lever_info[_capture_policy_info]
		var info_perm: Dictionary = _perm_cache.get(_capture_policy_info, {})
		var info_current: Variant = _lever_current(info_lever, info_perm)
		_capture_policy_info = ""
		_show_lever_info(info_lever, info_current)
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
	_active_command.clear()
	_pump()


func _reset_client_for_new_game(payload: Dictionary) -> void:
	_edits.clear()
	_cart.clear()
	_perm_cache.clear()
	_release_hist.clear()
	_last_release_at.clear()
	_scroll_mem.clear()
	_active_seat = "treasury"
	_active_group = ""
	_expanded_lever = ""
	_search = ""
	_policy_scope = "meeting"
	_tab = "focus"
	_goto_panel_group = ""
	_household_selected = -1
	_person_selected = -1
	_household_search = ""
	_firm_selected = ""
	_firm_search = ""
	_stock_selected = ""
	_stock_search = ""
	_score_country = int(
		(payload.get("world", {}) as Dictionary).get("player_economy", 0)
	)
	_last_toasted = ""
	_confirm.clear()
	_demo_crisis = false
	_crisis_dismissed = ""
	_last_tab = ""
	_last_seat = ""
	_last_page = ""


func _on_request_failed(message: String) -> void:
	var failed_new_game := str(_active_command.get("command", "")) == "new_game"
	if _new_game_pending and failed_new_game:
		_new_game_pending = false
		if _start_menu != null and _start_menu.has_method("restore_after_launch_error"):
			_start_menu.call("restore_after_launch_error", message)
	_show_verdict({"status": "rejected", "reason_code": message,
		"decision_id": "err:%d" % Time.get_ticks_msec()})
	_active_command.clear()
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


func _new_game_response_matches_draft(manifest: Dictionary) -> bool:
	# The backend adds provenance such as model_id to the normalized response.
	# Match only fields the client actually submitted so backend upgrades remain
	# transparent to this frontend.
	var normalized: Dictionary = manifest.get("spec", {})
	for raw_key: Variant in _new_game_draft.keys():
		var key := str(raw_key)
		if not normalized.has(key) or normalized[key] != _new_game_draft[key]:
			return false
	return true


func _start_menu_policy_schemas() -> Dictionary:
	var result: Dictionary = _schemas.duplicate(true)
	for seat: String in result.keys():
		for lever: Dictionary in result[seat].get("levers", []):
			var name := str(lever.get("name", ""))
			var group := str(lever.get("decision_group", "other"))
			lever["display_name"] = _cn(name)
			lever["display_group"] = str(GROUP_CN.get(group, group))
			if PERCENT_LEVERS.has(name):
				lever["display_format"] = "percent"
			elif MULTIPLIER_LEVERS.has(name):
				lever["display_format"] = "multiplier"
			elif DAY_LEVERS.has(name):
				lever["display_format"] = "days"
			var choice_labels: Dictionary = CHOICE_CN.get(name, {})
			if not choice_labels.is_empty():
				lever["display_choices"] = choice_labels
	return result


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
	# Godot 默认 Tooltip 偏小且透明度低；统一为适合财经信息的高对比浮层。
	var tooltip_style := _sb(Color("142a38"), Color("3a5260"), 10, 12, 8)
	t.set_stylebox("panel", "TooltipPanel", tooltip_style)
	t.set_font("font", "TooltipLabel", _sans)
	t.set_font_size("font_size", "TooltipLabel", 13)
	t.set_color("font_color", "TooltipLabel", Color("f1f7f8"))
	t.set_color("font_shadow_color", "TooltipLabel", Color(0, 0, 0, 0.32))
	t.set_constant("shadow_offset_x", "TooltipLabel", 0)
	t.set_constant("shadow_offset_y", "TooltipLabel", 1)
	t.set_constant("line_spacing", "TooltipLabel", 4)
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
			return "%.2f%%/日" % (v * 100.0)
		"per_thousand":
			return "%.2f‰" % v
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
			return "%.2f%%/日" % (v * 100.0)
		"price_index":
			return "%.3f" % v
		_:
			return _fmt_val("num", v)


func _cal_str(t: int) -> String:
	var year_day := t % 365
	var quarter := mini(year_day / 91, 3)
	return "第 %d 年 · 第 %d 季 · 第 %d 天" % [
		t / 365 + 1, quarter + 1, year_day - quarter * 91 + 1]


func _cal_short(t: int) -> String:
	return "第 %d 年 · 第 %d 日" % [t / 365 + 1, t % 365 + 1]


func _cal_value(value: Variant) -> String:
	var raw := str(value)
	if value is int or value is float:
		return _cal_short(int(value))
	if raw.is_valid_int():
		return _cal_short(raw.to_int())
	return "日期待定"


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
	var menu_button := _btn("⌂  主菜单", _request_return_to_main_menu)
	menu_button.tooltip_text = "暂停当前模拟并返回主菜单"
	menu_button.custom_minimum_size = Vector2(90, 0)
	_n["main_menu"] = menu_button
	h.add_child(menu_button)
	h.add_child(_vdiv())
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
	var tickl := _lbl("tick 0", 11, Color("68788b"), true)
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
		mb.tooltip_text = "运行模式\n交互：会议开始时暂停，等待你决策\n实时：自动通过非紧急会议；紧急会议仍会暂停"
		var mid: String = m[0]
		mb.pressed.connect(func() -> void:
			if mid == "realtime" and _mode != "realtime":
				_show_hint("实时模式:播放中将自动通过非紧急会议(待生效政策不受影响);紧急会议仍会暂停。")
			_mode = mid
			_render())
		_n["mode_" + mid] = mb
		modes.add_child(mb)
	h.add_child(modes_wrap)
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
	stepb.tooltip_text = "单日步进\n将模拟时间推进 1 天\n快捷键：→"
	tp.add_child(stepb)
	var play := _btn("▶  播放", _toggle_play, true)
	play.tooltip_text = "播放 / 暂停模拟\n快捷键：空格"
	play.custom_minimum_size = Vector2(96, 0)
	_n["play"] = play
	tp.add_child(play)
	for s: int in SPEEDS:
		var sbn := Button.new()
		sbn.text = "%d×" % s
		sbn.add_theme_font_override("font", _mono)
		sbn.add_theme_font_size_override("font_size", 12)
		sbn.tooltip_text = "模拟速度：%d 倍\n快捷键：%d" % [s, SPEEDS.find(s) + 1]
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
	scope.tooltip_text = "政策浏览范围\n在“本会议题”和当前席位的“全部政策”之间切换"
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
	for t: Array in [["focus", "宏观焦点"], ["households", "家庭"], ["firms", "企业"],
			["stocks", "股市"],
			["panels", "指标全景"], ["world", "世界视图"]]:
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
	filter.tooltip_text = "时间线筛选\n依次切换：重点事件 / 全部记录 / 我的操作"
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
	_n["modal_panel"] = mp
	modal_center.add_child(mp)
	var mv := VBoxContainer.new()
	mv.add_theme_constant_override("separation", 12)
	mp.add_child(mv)
	var modal_head := HBoxContainer.new()
	modal_head.add_theme_constant_override("separation", 12)
	mv.add_child(modal_head)
	var head_copy := VBoxContainer.new()
	head_copy.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head_copy.add_theme_constant_override("separation", 3)
	modal_head.add_child(head_copy)
	var eyebrow := _lbl("POLICY INTELLIGENCE · 政策决策档案", 9, Color("748496"), true)
	_n["modal_eyebrow"] = eyebrow
	head_copy.add_child(eyebrow)
	var mtitle := _lbl("", 15, INK)
	mtitle.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mtitle.clip_text = false
	_n["modal_title"] = mtitle
	head_copy.add_child(mtitle)
	var top_close := Button.new()
	top_close.text = "×"
	top_close.flat = true
	top_close.custom_minimum_size = Vector2(34, 34)
	top_close.add_theme_font_size_override("font_size", 20)
	top_close.add_theme_color_override("font_color", Color("6c7a89"))
	top_close.add_theme_color_override("font_hover_color", Color("24384a"))
	top_close.add_theme_stylebox_override("hover", _sb(Color("e8edf3"), Color("d3dce5"), 17, 4))
	top_close.pressed.connect(func() -> void:
		_confirm_cancel())
	_n["modal_top_close"] = top_close
	modal_head.add_child(top_close)
	mv.add_child(_hrule())
	var mb := _lbl("", 12, Color("45535f"))
	mb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	mb.custom_minimum_size = Vector2(400, 0)
	_n["modal_body"] = mb
	mv.add_child(mb)
	var policy_scroll := ScrollContainer.new()
	policy_scroll.visible = false
	policy_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	policy_scroll.custom_minimum_size = Vector2(810, 520)
	_n["modal_policy"] = policy_scroll
	mv.add_child(policy_scroll)
	var policy_content := VBoxContainer.new()
	policy_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	policy_content.custom_minimum_size.x = 790
	policy_content.add_theme_constant_override("separation", 12)
	_n["modal_policy_content"] = policy_content
	policy_scroll.add_child(policy_content)
	var note_panel := PanelContainer.new()
	note_panel.add_theme_stylebox_override("panel", _sb(Color("f6f8fa"), Color("dbe2e9"), 8, 8))
	_n["modal_note_panel"] = note_panel
	var mnote := _lbl("", 10, Color("6b7785"), true)
	mnote.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_n["modal_note"] = mnote
	note_panel.add_child(mnote)
	mv.add_child(note_panel)
	var mrow := HBoxContainer.new()
	mrow.add_theme_constant_override("separation", 9)
	mrow.alignment = BoxContainer.ALIGNMENT_END
	_n["modal_actions"] = mrow
	var modal_cancel := _btn("取消", _confirm_cancel)
	_n["modal_cancel"] = modal_cancel
	mrow.add_child(modal_cancel)
	var modal_confirm := _btn("确认", _confirm_yes, true)
	_n["modal_confirm"] = modal_confirm
	mrow.add_child(modal_confirm)
	mv.add_child(mrow)


func _confirm_yes() -> void:
	var cb: Variant = _confirm.get("on_yes")
	_confirm = {}
	if cb is Callable:
		(cb as Callable).call()
	_render()


func _confirm_cancel() -> void:
	var cb: Variant = _confirm.get("on_cancel")
	_confirm = {}
	if cb is Callable:
		(cb as Callable).call()
	_render()


# ================= 渲染 =================
func _render() -> void:
	var t := int(_snapshot.get("tick", 0))
	_set_text("cal", _cal_str(t))
	_set_text("tick", "tick %d" % t)
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
	for tab in ["focus", "households", "firms", "stocks", "panels", "world"]:
		var tb := _n["tab_" + tab] as Button
		if tab == _tab:
			tb.add_theme_stylebox_override("normal", _sb(Color.WHITE, BLUE_BD, 18, 7, 5))
			tb.add_theme_color_override("font_color", Color("1c4a8f"))
		else:
			tb.add_theme_stylebox_override("normal", _sb(Color(1, 1, 1, 0), Color(0, 0, 0, 0), 18, 7))
			tb.add_theme_color_override("font_color", Color("586a7b"))
	_set_text("tabnote", {
		"focus": "基于已发布公报的跨指标判断",
		"households": "微观家庭 · 成员、资产负债与消费",
		"firms": "微观企业 · 经营、账表、员工与股权",
		"stocks": "每日收盘行情 · 企业股与银行股",
		"panels": "经济运行 · 多维指标与结构分解",
		"world": "多国耦合 · 贸易 / 资本 / 移民",
	}.get(_tab, ""))
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
		var read_only := bool(_confirm.get("read_only", false))
		(_n["modal_panel"] as PanelContainer).add_theme_stylebox_override("panel",
			_sb(Color("f7f9fb"), Color("b8c4d0"), 14, 18, 12) if read_only
			else _sb(Color("f6f8fb"), Color("cdd7e2"), 14, 18))
		(_n["modal_panel"] as Control).custom_minimum_size = Vector2(
			880 if read_only else 440, 0)
		(_n["modal_body"] as Label).custom_minimum_size = Vector2(
			400, 0)
		(_n["modal_body"] as Control).visible = not read_only
		(_n["modal_policy"] as Control).visible = read_only
		(_n["modal_title"] as Label).add_theme_font_size_override(
			"font_size", 20 if read_only else 15)
		(_n["modal_eyebrow"] as Control).visible = read_only
		(_n["modal_top_close"] as Control).visible = read_only
		(_n["modal_actions"] as Control).visible = not read_only
		(_n["modal_cancel"] as Button).text = "取消"
		(_n["modal_confirm"] as Button).visible = not read_only
		_set_text("modal_title", str(_confirm.get("title", "")))
		_set_text("modal_body", str(_confirm.get("body", "")))
		_set_text("modal_note", str(_confirm.get("note", "")))
		(_n["modal_note_panel"] as Control).visible = not str(
			_confirm.get("note", "")).is_empty()
		if read_only:
			_render_policy_brief(
				_confirm.get("lever", {}), _confirm.get("current"))


func _render_tiles() -> void:
	var row := _n["tiles"] as HBoxContainer
	for c in row.get_children():
		c.queue_free()
	var by_id := _releases_by_id()
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
		tile.tooltip_text = "查看指标详情\n打开「指标全景 · %s」" % str(TILE_TO_GROUP.get(sid, ""))
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
			var rline := _lbl("%s发布 · %d日前" % [
				_cal_short(int(rel.get("released_at_tick", 0))), t - ref_end], 9, INK3, true)
			rline.clip_text = true
			v.add_child(rline)
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
			var effective: Variant = decision.get("effective_tick", "?")
			for action in (p.get("actions", []) as Array).slice(0, 1):
				var ar: Dictionary = action
				var row := HBoxContainer.new()
				row.add_child(_lbl("• " + _cn(str(ar.get("lever", ""))),
					10, Color("d9e6eb")))
				row.add_child(_spacer_h())
				row.add_child(_lbl(_cal_value(effective), 10, Color("68d2c2"), true))
				col.add_child(row)
	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 7)
	var jump := _btn("快进至下一决策", _advance_to_next_decision, true)
	jump.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	jump.tooltip_text = "快进至下一次决策\n最多推进 100 天；遇到会议立即暂停\n不会越过决策边界 · 快捷键：N"
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


func _lever_kind_description(lever: Dictionary) -> String:
	var kind := str(lever.get("value_kind", "number"))
	var nullable := bool(lever.get("nullable", false))
	match kind:
		"bool":
			return "启用 / 停用型制度开关"
		"choice":
			var options: Array = []
			for option in lever.get("choices", []):
				options.append(_choice_text(str(lever.get("name", "")), option))
			return "制度选项（%s）" % "、".join(options)
		"economy_id":
			return "国家参照选择"
		"economy_set":
			return "国家名单选择"
		"integer":
			return "整数政策参数，范围 %s – %s" % [
				_lever_value_text(lever, lever.get("minimum", 0)),
				_lever_value_text(lever, lever.get("maximum", 0))]
		_:
			var range_text := "连续政策参数，范围 %s – %s" % [
				_lever_value_text(lever, lever.get("minimum", 0.0)),
				_lever_value_text(lever, lever.get("maximum", 0.0))]
			return range_text + ("，也可不设置" if nullable else "")


func _lever_channel_text(lever: Dictionary) -> String:
	var read_point := str(lever.get("read_point", "")).to_lower()
	var group := str(lever.get("decision_group", ""))
	if read_point.contains("energy"):
		return "能源定价、供给分配、补贴或战略储备"
	if read_point.contains("mortgage") or read_point.contains("housing"):
		return "住房融资、交易、建设、违约与处置"
	if read_point.contains("central_bank"):
		return "政策利率、准备金和银行流动性"
	if read_point.contains("banking") or read_point.contains("credit"):
		return "银行授信能力、借款约束和资产负债表风险"
	if read_point.contains("securities"):
		return "国债发行、持有、定价和利息现金流"
	if read_point.contains("trade"):
		return "进出口价格、数量、企业份额和关税收入"
	if read_point.contains("migration"):
		return "人口跨境流动、劳动力供给和汇款"
	if read_point.contains("world") or read_point.contains("capital") \
			or read_point.contains("fx"):
		return "汇率、跨境资本、外汇储备和国际收支"
	if read_point.contains("settlement"):
		return "居民、企业与政府结算以及税后可支配资源"
	if read_point.contains("goods") or read_point.contains("planning"):
		return "商品需求、生产计划、价格和财政收支"
	if read_point.contains("reporting"):
		return "政策规则采用的统计口径和决策信号"
	return {
		"fiscal_stance": "政府支出、总需求、就业与赤字债务",
		"tax_and_transfers": "税后收入、消费成本、分配与财政收入",
		"debt_management": "国债融资、期限结构和偿债成本",
		"monetary_stance": "政策利率反应、融资成本与资产估值",
		"liquidity_operations": "银行准备金、流动性与支付稳定",
		"macroprudential": "信贷供给、杠杆、抵押品与违约风险",
		"structural_law": "破产、处置与金融合同的制度边界",
		"trade_and_migration": "贸易、人口流动和跨境收入",
		"fx_operations": "汇率、资本流动和外汇储备",
		"energy_operations": "能源价格、供给和战略储备",
		"energy_structure": "能源部门产权和长期供给结构",
	}.get(group, "相关部门的预算约束与行为规则")


func _lever_meaning_text(lever: Dictionary) -> String:
	var name := str(lever.get("name", ""))
	var label := _cn(name)
	var player_help: Dictionary = lever.get("player_help", {})
	var help: Dictionary = POLICY_HELP.get(name, {})
	var definition := str(player_help.get("meaning", help.get("definition", "")))
	if definition.is_empty():
		if name.begins_with("tax_") or label.ends_with("税率"):
			definition = "“%s”规定相关计税基数向政府缴纳的比例。" % label
		elif name.contains("allowance") or label.ends_with("起征点"):
			definition = "“%s”规定低于该水平时不计入相应税基的免征额度。" % label
		elif name.contains("cap") or name.contains("limit") or label.ends_with("上限"):
			definition = "“%s”规定相关数量、比例或风险暴露不得超过的最高边界。" % label
		elif name.contains("floor") or name.begins_with("min_") or label.ends_with("下限"):
			definition = "“%s”规定相关价格、收入或资本必须达到的最低边界。" % label
		elif name.ends_with("_share") or name.ends_with("_frac") \
				or name.ends_with("_ratio") or name.ends_with("_ltv"):
			definition = "“%s”规定相关政策量相对其基数的比例。" % label
		elif str(lever.get("value_kind", "")) == "bool":
			definition = "“%s”决定模型是否启用这一制度或操作机制。" % label
		elif str(lever.get("value_kind", "")) == "choice":
			definition = "“%s”决定模型采用哪一种制度运行规则。" % label
		else:
			definition = "“%s”是模型中直接控制%s的政策参数。" % [
				label, _lever_channel_text(lever)]
	return definition


func _lever_effect_text(lever: Dictionary) -> String:
	var name := str(lever.get("name", ""))
	var label := _cn(name)
	var player_help: Dictionary = lever.get("player_help", {})
	var help: Dictionary = POLICY_HELP.get(name, {})
	var effect := str(player_help.get("mechanics", help.get("effect", "")))
	if not effect.is_empty():
		return effect
	if name.begins_with("tax_") or label.ends_with("税率"):
		return "提高通常增加财政收入，同时降低相关主体的税后收入、回报或需求；降低则方向相反。"
	if name.contains("subsidy") or name.contains("benefit") \
			or name.contains("pension"):
		return "提高通常增加受益方可支配资源并支撑需求，同时扩大财政成本。"
	if name.contains("allowance") or label.ends_with("起征点"):
		return "提高会缩小税基、增加纳税方税后资源并减少财政收入；降低则方向相反。"
	if name.contains("haircut") or name.contains("risk_weight"):
		return "提高会降低抵押品或资产的监管认可价值、增加资本占用，通常使信贷更审慎。"
	if name.contains("cap") or name.contains("limit") or label.ends_with("上限"):
		return "下调代表收紧上限，通常降低相关风险或规模，同时限制交易、融资或供给；上调则放宽约束。"
	if name.contains("floor") or name.begins_with("min_") or label.ends_with("下限"):
		return "提高代表抬高最低要求，强化保护或审慎标准，同时增加达标成本并可能减少可获得性。"
	if str(lever.get("value_kind", "")) == "bool":
		return "启用后模型会执行%s机制；停用则绕过该机制。最终宏观影响取决于当时经济状态。" % \
			_lever_channel_text(lever)
	return "调整会先改变%s中的约束或决策，再经交易、结算和资产负债表传导；方向与幅度取决于当时经济状态。" % \
		_lever_channel_text(lever)


func _lever_tradeoffs_text(lever: Dictionary) -> String:
	var player_help: Dictionary = lever.get("player_help", {})
	var text := str(player_help.get("tradeoffs", ""))
	if not text.is_empty():
		return text
	return "这项政策没有脱离情景的唯一最优值。调整前应同时比较目标改善、财政或金融成本，以及对其他部门的间接影响。"


func _lever_watch_text(lever: Dictionary) -> String:
	var player_help: Dictionary = lever.get("player_help", {})
	var text := str(player_help.get("watch", ""))
	if not text.is_empty():
		return text
	return "实际产出、就业、物价、财政与金融稳定"


func _lever_info_tooltip(lever: Dictionary, current: Variant) -> String:
	return "%s  ·  当前 %s\n\n经济学定义\n%s\n\n经济传导\n%s\n\n政策权衡\n%s\n\n点击打开完整政策简报" % [
		_cn(str(lever.get("name", ""))), _lever_value_text(lever, current),
		_tooltip_wrap(_lever_meaning_text(lever)),
		_tooltip_wrap(_lever_effect_text(lever)),
		_tooltip_wrap(_lever_tradeoffs_text(lever))]


func _tooltip_wrap(text: String, preferred_width: int = 34) -> String:
	# Godot 的默认 tooltip 不会自动换行；优先在中文标点后断行，并给长句设置硬上限。
	var result := ""
	var column := 0
	for index in text.length():
		var character := text.substr(index, 1)
		result += character
		if character == "\n":
			column = 0
			continue
		column += 1
		var punctuation := "，；。！？、".contains(character)
		if (column >= preferred_width and punctuation) or column >= preferred_width + 8:
			result += "\n"
			column = 0
	return result.trim_suffix("\n")


func _lever_timing_text(lever: Dictionary) -> String:
	var lag := int(lever.get("implementation_lag", 0))
	return "即时生效" if lag <= 0 else "通过后 %d 天生效" % lag


func _lever_adjustment_text(lever: Dictionary) -> String:
	var hold := int(lever.get("min_hold_ticks", 0))
	var scale: Variant = lever.get("control_scale")
	var max_step: Variant = lever.get("max_step")
	var adjustment := "无固定数值档位"
	if scale != null:
		adjustment = "建议单档 %s" % _lever_value_text(lever, scale)
	if max_step != null:
		adjustment += "；单次最多变动 %s" % _lever_value_text(lever, max_step)
	return "%s；调整后至少保持 %d 天" % [adjustment, hold]


func _lever_semantics_text(lever: Dictionary) -> String:
	return str({
		"immediate": "生效后从下一自然日的相关计算开始使用新值",
		"new-contracts-only": "只影响生效后新签合同，既有存量合同不会被追溯改写",
		"state-transition": "属于制度迁移，生效时会执行一次状态与账本衔接",
	}.get(str(lever.get("semantics", "immediate")), "按注册表规定的生效语义执行"))


func _lever_conditions_text(lever: Dictionary) -> String:
	var requirements: Array = []
	for capability in lever.get("requires", []):
		requirements.append(str(CAPABILITY_CN.get(str(capability), capability)))
	for prerequisite in lever.get("enabled_if", []):
		requirements.append("政策“%s”已启用" % _cn(str(prerequisite)))
	return "无额外前置条件" if requirements.is_empty() else "需要：%s" % "、".join(requirements)


func _lever_boundary_text(lever: Dictionary) -> String:
	var shadowed: Array = []
	for raw_shadow in lever.get("shadowed_by", []):
		var token := str(raw_shadow)
		var base: String = token.split(">")[0].split("=")[0]
		if token == "ZLB/r_max clamp":
			shadowed.append("零利率下限或政策利率上限")
		else:
			shadowed.append(_cn(base) if LEVER_CN.has(base) else token)
	if not shadowed.is_empty():
		return "可能被“%s”等优先规则覆盖；覆盖期间即使改变数值，也可能暂时看不到结果。" % "、".join(shadowed)
	if not str(lever.get("state_notes", "")).is_empty():
		return "这项政策具有情景或状态条件，只有相关市场、合同或危机实际出现时，效果才会进入数据。"
	return "没有登记会直接遮蔽该政策的上层规则；最终幅度仍取决于当时的家庭、企业和金融状态。"


func _lever_cost_text(lever: Dictionary) -> String:
	var cost_cn: String = {
		"regime_switch": "制度切换", "major": "重大调整",
		"ordinary": "常规调整", "operational": "日常操作",
	}.get(str(lever.get("cost_class", "ordinary")), "常规调整")
	return "%.1f · %s" % [float(lever.get("admin_weight", 0.0)), cost_cn]


func _brief_text(text: String, size: int = 12, color: Color = INK2,
		bold: bool = false) -> Label:
	var label := _lbl(text, size, color, bold)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.add_theme_constant_override("line_spacing", 3)
	return label


func _brief_panel(title: String, text: String, accent: Color,
		background: Color = Color.WHITE) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel.add_theme_stylebox_override("panel", _sb(
		background, Color("d7e0e8"), 10, 13, 2))
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 7)
	panel.add_child(content)
	var heading := HBoxContainer.new()
	heading.add_theme_constant_override("separation", 7)
	heading.add_child(_dot(accent, 7))
	heading.add_child(_lbl(title, 10, accent.darkened(0.18), true))
	content.add_child(heading)
	content.add_child(_brief_text(text, 12, Color("384b5d")))
	return panel


func _brief_rule_card(title: String, value: String, accent: Color) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel.custom_minimum_size = Vector2(0, 68)
	panel.add_theme_stylebox_override("panel", _sb(Color.WHITE, Color("d9e1e9"), 8, 11))
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 5)
	panel.add_child(content)
	content.add_child(_lbl(title, 9, accent, true))
	content.add_child(_brief_text(value, 11, Color("405365"), true))
	return panel


func _render_policy_brief(lever_raw: Variant, current: Variant) -> void:
	var content := _n["modal_policy_content"] as VBoxContainer
	for child in content.get_children():
		content.remove_child(child)
		child.queue_free()
	if not lever_raw is Dictionary or (lever_raw as Dictionary).is_empty():
		content.add_child(_brief_text("政策资料暂不可用。", 12, INK3))
		return
	var lever: Dictionary = lever_raw
	var seat_color := _seat_color(str(lever.get("owner_role", "")))

	# Hero: the economic meaning stands on its own. Game implementation details belong below.
	var hero := PanelContainer.new()
	hero.add_theme_stylebox_override("panel", _sb(Color("f0f4f8"), Color("ccd7e1"), 11, 15, 3))
	var hero_row := HBoxContainer.new()
	hero_row.add_theme_constant_override("separation", 16)
	hero.add_child(hero_row)
	var current_col := VBoxContainer.new()
	current_col.custom_minimum_size.x = 185
	current_col.add_theme_constant_override("separation", 5)
	current_col.add_child(_lbl("CURRENT POLICY · 当前生效", 9, Color("6d8092"), true))
	current_col.add_child(_lbl(_lever_value_text(lever, current), 23,
		seat_color.darkened(0.05), true))
	var seat_chip := _chip(
		_seat_name(str(lever.get("owner_role", ""))), seat_color.darkened(0.12),
		Color.WHITE, seat_color.lightened(0.5), 9)
	seat_chip.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	current_col.add_child(seat_chip)
	hero_row.add_child(current_col)
	var hero_divider := ColorRect.new()
	hero_divider.color = Color("d2dce6")
	hero_divider.custom_minimum_size = Vector2(1, 0)
	hero_row.add_child(hero_divider)
	var meaning_col := VBoxContainer.new()
	meaning_col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	meaning_col.add_theme_constant_override("separation", 5)
	meaning_col.add_child(_lbl("ECONOMIC DEFINITION · 经济学定义", 9, Color("6d8092"), true))
	meaning_col.add_child(_brief_text(_lever_meaning_text(lever), 13, Color("263b4d"), true))
	hero_row.add_child(meaning_col)
	content.add_child(hero)

	# The economic transmission and policy trade-off follow the definition.
	var decision_row := HBoxContainer.new()
	decision_row.add_theme_constant_override("separation", 12)
	decision_row.add_child(_brief_panel("ECONOMIC TRANSMISSION · 经济传导", _lever_effect_text(lever),
		Color("386b9d"), Color.WHITE))
	decision_row.add_child(_brief_panel("POLICY TRADE-OFF · 政策权衡", _lever_tradeoffs_text(lever),
		Color("9b6e2c"), Color.WHITE))
	content.add_child(decision_row)

	var watch_panel := PanelContainer.new()
	watch_panel.add_theme_stylebox_override("panel", _sb(Color("f3f7f7"), Color("d5e1e0"), 9, 11))
	var watch_col := VBoxContainer.new()
	watch_col.add_theme_constant_override("separation", 7)
	watch_panel.add_child(watch_col)
	watch_col.add_child(_lbl("MONITOR · 建议观察", 9, Color("4a6f70"), true))
	var watch_flow := HFlowContainer.new()
	watch_flow.add_theme_constant_override("h_separation", 6)
	watch_flow.add_theme_constant_override("v_separation", 6)
	for raw_metric in _lever_watch_text(lever).split("、", false):
		var metric := str(raw_metric).strip_edges()
		if not metric.is_empty():
			watch_flow.add_child(_chip(metric, Color("355d5f"), Color.WHITE, Color("cbdcdb"), 9))
	watch_col.add_child(watch_flow)
	content.add_child(watch_panel)

	var rule_heading := HBoxContainer.new()
	rule_heading.add_theme_constant_override("separation", 8)
	rule_heading.add_child(_lbl("GAME RULES · 游戏规则（非政策定义）", 10, INK3, true))
	rule_heading.add_child(_hrule())
	content.add_child(rule_heading)
	var rules := GridContainer.new()
	rules.columns = 2
	rules.add_theme_constant_override("h_separation", 8)
	rules.add_theme_constant_override("v_separation", 8)
	var rule_accent := Color("536b7e")
	rules.add_child(_brief_rule_card("可选范围", _lever_kind_description(lever), rule_accent))
	rules.add_child(_brief_rule_card("实施时间", _lever_timing_text(lever), rule_accent))
	rules.add_child(_brief_rule_card("调整节奏", _lever_adjustment_text(lever), rule_accent))
	rules.add_child(_brief_rule_card("行政成本", _lever_cost_text(lever), rule_accent))
	content.add_child(rules)

	var execution := HBoxContainer.new()
	execution.add_theme_constant_override("separation", 12)
	execution.add_child(_brief_panel("生效方式", _lever_semantics_text(lever),
		Color("58708a"), Color.WHITE))
	execution.add_child(_brief_panel("前置条件", _lever_conditions_text(lever),
		Color("58708a"), Color.WHITE))
	content.add_child(execution)
	content.add_child(_brief_panel("条件与例外", _lever_boundary_text(lever),
		Color("9a6b10"), Color("fffaf0")))

	var emergency_text := "可在紧急会议中使用，紧急实施滞后为 %s。" % (
		"即时" if lever.get("emergency_implementation_lag") == null
		else "%d 天" % int(lever.get("emergency_implementation_lag", 0))) \
		if bool(lever.get("emergency", false)) else "不在紧急政策白名单，只能通过常规会议调整。"
	content.add_child(_brief_text("权限 · %s · %s\n%s" % [
		_seat_name(str(lever.get("owner_role", ""))),
		str(GROUP_CN.get(str(lever.get("decision_group", "")),
			lever.get("decision_group", "政策"))), emergency_text], 10, INK3))


func _show_lever_info(lever: Dictionary, current: Variant) -> void:
	_confirm = {
		"title": _cn(str(lever.get("name", ""))),
		"body": "",
		"note": "经济学说明用于解释政策含义、传导与权衡，不代表结果承诺；实际效果取决于当时的经济环境。",
		"lever": lever,
		"current": current,
		"read_only": true,
	}
	_render()


func _lever_info_button(lever: Dictionary, current: Variant) -> Button:
	var info := Button.new()
	info.text = "ⓘ"
	info.flat = true
	info.custom_minimum_size = Vector2(27, 27)
	info.add_theme_font_size_override("font_size", 13)
	info.add_theme_color_override("font_color", Color("65798c"))
	info.add_theme_color_override("font_hover_color", Color("285ca8"))
	info.add_theme_stylebox_override("hover", _sb(Color("edf4ff"),
		Color("c9dcf5"), 14, 3))
	info.tooltip_text = _lever_info_tooltip(lever, current)
	info.pressed.connect(func() -> void:
		_show_lever_info(lever, current))
	return info


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
	var base_v: Variant = _lever_current(lever, perm)
	var cart_stale: bool = in_cart and edited and cart_entry.get("value") != draft
	var row := PanelContainer.new()
	row.custom_minimum_size = Vector2(0, 62)
	row.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	row.tooltip_text = "%s\n展开政策编辑器，查看范围、成本和生效时间" % _cn(name)
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
	var name_line := HBoxContainer.new()
	name_line.add_theme_constant_override("separation", 3)
	var title := _lbl(_cn(name), 13, INK)
	title.clip_text = true
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_line.add_child(title)
	name_line.add_child(_lever_info_button(lever, base_v))
	names.add_child(name_line)
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
		status_text = "待生效 · %s" % _cal_value(
			(pending_by[name] as Dictionary).get("effective_tick", "?"))
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
	var policy_values: Dictionary = _snapshot.get("policy_values", {})
	var lever_name := str(lever.get("name", ""))
	if policy_values.has(lever_name):
		return policy_values.get(lever_name)
	var cached: Dictionary = _perm_cache.get(str(lever.get("name")), {})
	if cached.has("current_value"):
		return cached.get("current_value")
	return lever.get("current_value")


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
	tr.add_child(_lever_info_button(lever, base_v))
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
		pr.add_child(_lbl("%s生效" % _cal_value(
			(pend as Dictionary).get("effective_tick", "?")),
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
			addrow.add_child(_lbl("预计 %s 生效" % _cal_short(
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
		input.tooltip_text = "精确输入模型原始值\n例如：3% 请输入 0.03"
		input.add_theme_font_override("font", _mono)
		input.add_theme_font_size_override("font_size", 11)
		input.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 7, 6))
		input.add_theme_stylebox_override("focus", _sb(Color.WHITE, TEAL_BD, 7, 6))
		input.text_submitted.connect(func(text: String) -> void:
			_commit_numeric_input(lever, text, is_int, lo2, hi2))
		direct.add_child(input)
		var apply := _btn("应用数值", func() -> void:
			_commit_numeric_input(lever, input.text, is_int, lo2, hi2))
		apply.tooltip_text = "应用输入值\n若超出本次允许范围，将自动调整到最近边界"
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
		sub += ("" if sub.is_empty() else " · ") + "%s 生效" % _cal_str(et)
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
		"households":
			_render_households_tab(body)
		"firms":
			_render_firms_tab(body)
		"stocks":
			_render_stock_market_tab(body)
		_:
			_render_focus_tab(body)


func _open_firm(firm_id: String) -> void:
	if firm_id.is_empty():
		return
	_firm_selected = firm_id
	_firm_search = ""
	_tab = "firms"
	_scroll_mem.erase("center:firms:detail")
	_render()


func _open_person(person_id: int, household_id: Variant) -> void:
	if person_id < 0 or household_id == null:
		return
	_person_selected = person_id
	_household_selected = int(household_id)
	_household_search = ""
	_tab = "households"
	_scroll_mem.erase("center:households:detail")
	_render()


func _household_summary_card(label: String, value: String,
		color: Color, note: String = "") -> Control:
	var card := PanelContainer.new()
	card.custom_minimum_size.y = 58
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	card.add_theme_stylebox_override("panel", _sb(Color("f8fafc"), Color("e0e7ef"), 10, 8))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 1)
	card.add_child(col)
	col.add_child(_lbl(label, 8, INK3, true))
	var row := HBoxContainer.new()
	row.add_child(_lbl(value, 16, color, true))
	row.add_child(_spacer_h())
	if not note.is_empty():
		row.add_child(_lbl(note, 8, INK3))
	col.add_child(row)
	return card


func _household_sort_value(item: Dictionary) -> float:
	match _household_sort:
		"members":
			return float(item.get("member_count", 0))
		"debt":
			return float(item.get("debt", 0.0))
		_:
			return float(item.get("net_worth", 0.0))


func _household_matches(item: Dictionary) -> bool:
	var query := _household_search.strip_edges().to_lower()
	if query.is_empty():
		return true
	var household_id := str(item.get("household_id", ""))
	var account_id := str(item.get("account_id", "")).to_lower()
	if household_id.contains(query) or account_id.contains(query):
		return true
	for member: Dictionary in item.get("members", []):
		if str(member.get("person_id", "")).contains(query):
			return true
	return false


func _render_households_tab(body: VBoxContainer) -> void:
	var payload: Dictionary = _snapshot.get("households", {})
	var summary: Dictionary = payload.get("summary", {})
	var all_items: Array = payload.get("items", [])
	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 7)
	top.add_child(_household_summary_card("HOUSEHOLDS · 家庭",
		str(int(summary.get("household_count", 0))), TEAL, "户"))
	top.add_child(_household_summary_card("POPULATION · 成员",
		str(int(summary.get("population", 0))), BLUE, "人"))
	top.add_child(_household_summary_card("ASSETS · 总资产",
		_fmt_val("num", float(summary.get("total_assets", 0.0))), PURPLE))
	top.add_child(_household_summary_card("DEBT · 总负债",
		_fmt_val("num", float(summary.get("total_debt", 0.0))), AMBER))
	body.add_child(top)

	var toolbar := PanelContainer.new()
	toolbar.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 10, 6))
	var tools := HBoxContainer.new()
	tools.add_theme_constant_override("separation", 6)
	toolbar.add_child(tools)
	tools.add_child(_lbl("家庭微观档案", 11, INK))
	tools.add_child(_chip("MICRODATA · 家庭账册", Color("5a36a8"),
		Color("f3effc"), Color("d8ccf0"), 8))
	tools.add_child(_spacer_h())
	var search := LineEdit.new()
	search.custom_minimum_size.x = 155
	search.placeholder_text = "家庭号 / 成员ID · 回车"
	search.text = _household_search
	search.add_theme_font_size_override("font_size", 9)
	search.add_theme_color_override("font_color", INK2)
	search.add_theme_color_override("font_placeholder_color", INK3)
	search.add_theme_color_override("caret_color", BLUE)
	search.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 8, 5))
	search.add_theme_stylebox_override("focus", _sb(Color.WHITE, BLUE_BD, 8, 5, 2))
	search.text_submitted.connect(func(value: String) -> void:
		_household_search = value
		_render())
	tools.add_child(search)
	for sort_spec: Array in [["net_worth", "净资产"], ["members", "成员"], ["debt", "负债"]]:
		var sort_id := str(sort_spec[0])
		var sort_button := Button.new()
		sort_button.text = str(sort_spec[1])
		sort_button.add_theme_font_size_override("font_size", 8)
		if sort_id == _household_sort:
			sort_button.add_theme_stylebox_override("normal", _sb(BLUE_BG, BLUE_BD, 8, 5))
			sort_button.add_theme_color_override("font_color", Color("285ca8"))
		sort_button.pressed.connect(func() -> void:
			_household_sort = sort_id
			_render())
		tools.add_child(sort_button)
	body.add_child(toolbar)

	var items: Array = []
	for item: Dictionary in all_items:
		if _household_matches(item):
			items.append(item)
	items.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		var av := _household_sort_value(a)
		var bv := _household_sort_value(b)
		if is_equal_approx(av, bv):
			return int(a.get("household_id", 0)) < int(b.get("household_id", 0))
		return av > bv)
	if items.is_empty():
		var empty := PanelContainer.new()
		empty.size_flags_vertical = Control.SIZE_EXPAND_FILL
		empty.add_theme_stylebox_override("panel", _sb(PANEL, LINE, 12, 18))
		empty.add_child(_lbl("没有匹配的家庭。清空搜索词后重试。", 11, INK3))
		body.add_child(empty)
		return
	var selected_found := false
	for item: Dictionary in items:
		if int(item.get("household_id", -1)) == _household_selected:
			selected_found = true
			break
	if not selected_found:
		_household_selected = int((items[0] as Dictionary).get("household_id", -1))

	var main := HBoxContainer.new()
	main.size_flags_vertical = Control.SIZE_EXPAND_FILL
	main.add_theme_constant_override("separation", 9)
	body.add_child(main)
	var list_shell := PanelContainer.new()
	list_shell.custom_minimum_size.x = 205
	list_shell.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	list_shell.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list_shell.add_theme_stylebox_override("panel", _sb(Color("f7f9fc"), LINE, 11, 7))
	var list_col := VBoxContainer.new()
	list_col.add_theme_constant_override("separation", 6)
	list_shell.add_child(list_col)
	var list_head := HBoxContainer.new()
	list_head.add_child(_lbl("FAMILY INDEX", 8, INK3, true))
	list_head.add_child(_spacer_h())
	list_head.add_child(_lbl("%d / %d" % [items.size(), all_items.size()], 8, INK3, true))
	list_col.add_child(list_head)
	var list_scroll := ScrollContainer.new()
	list_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	list_col.add_child(list_scroll)
	_restore_scroll("center:households:list", list_scroll)
	list_scroll.get_v_scroll_bar().value_changed.connect(func(v: float) -> void:
		_scroll_mem["center:households:list"] = int(v))
	var list_items := VBoxContainer.new()
	list_items.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list_items.add_theme_constant_override("separation", 5)
	list_scroll.add_child(list_items)
	var selected: Dictionary = items[0]
	for item: Dictionary in items:
		var household_id := int(item.get("household_id", -1))
		var active := household_id == _household_selected
		if active:
			selected = item
		var entry := Button.new()
		entry.custom_minimum_size = Vector2(188, 54)
		entry.alignment = HORIZONTAL_ALIGNMENT_LEFT
		entry.text = "家庭 #%03d  ·  %d 人\n总资产 %s  ·  负债 %s" % [
			household_id, int(item.get("member_count", 0)),
			_fmt_val("num", float((item.get("assets", {}) as Dictionary).get("total", 0.0))),
			_fmt_val("num", float(item.get("debt", 0.0)))]
		entry.add_theme_font_size_override("font_size", 8)
		entry.add_theme_stylebox_override("normal", _sb(
			Color("eef5ff") if active else Color.WHITE,
			BLUE_BD if active else Color("dfe6ee"), 9, 7, 3 if active else 0))
		entry.add_theme_color_override("font_color", Color("1f4f91") if active else INK2)
		entry.tooltip_text = "查看家庭 #%03d 的成员与资产负债" % household_id
		entry.pressed.connect(func() -> void:
			_household_selected = household_id
			_person_selected = -1
			_render())
		list_items.add_child(entry)
	main.add_child(list_shell)

	var detail_scroll := ScrollContainer.new()
	detail_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	detail_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	main.add_child(detail_scroll)
	_restore_scroll("center:households:detail", detail_scroll)
	detail_scroll.get_v_scroll_bar().value_changed.connect(func(v: float) -> void:
		_scroll_mem["center:households:detail"] = int(v))
	var detail := VBoxContainer.new()
	detail.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail.add_theme_constant_override("separation", 8)
	detail_scroll.add_child(detail)
	_render_household_detail(detail, selected, str(payload.get("as_of_date", "")))


func _render_household_detail(parent: VBoxContainer, household: Dictionary,
		as_of_date: String) -> void:
	var household_id := int(household.get("household_id", -1))
	var header := PanelContainer.new()
	header.add_theme_stylebox_override("panel", _sb(Color("f9fbfd"), Color("dce5ee"), 11, 9, 4))
	var header_col := VBoxContainer.new()
	header_col.add_theme_constant_override("separation", 6)
	header.add_child(header_col)
	var title := HBoxContainer.new()
	title.add_child(_dot(TEAL, 8))
	title.add_child(_lbl("家庭 #%03d" % household_id, 15, INK))
	if bool(household.get("is_public_guardian", false)):
		title.add_child(_chip("公共监护家庭", Color("9a6812"), AMBER_BG, AMBER_BD, 8))
	title.add_child(_chip("%d 位成员" % int(household.get("member_count", 0)),
		TEAL_DK, TEAL_BG, TEAL_BD, 8))
	title.add_child(_spacer_h())
	title.add_child(_lbl("截至 %s" % as_of_date, 8, INK3, true))
	header_col.add_child(title)
	var asset: Dictionary = household.get("assets", {})
	var metrics := HBoxContainer.new()
	metrics.add_theme_constant_override("separation", 6)
	metrics.add_child(_household_summary_card("总资产",
		_fmt_val("num", float(asset.get("total", 0.0))), TEAL))
	metrics.add_child(_household_summary_card("负债",
		_fmt_val("num", float(household.get("debt", 0.0))), AMBER))
	metrics.add_child(_household_summary_card("净资产",
		_fmt_val("num", float(household.get("net_worth", 0.0))), PURPLE))
	metrics.add_child(_household_summary_card("本期消费",
		_fmt_val("num", float(household.get("consumption", 0.0))), BLUE))
	header_col.add_child(metrics)
	var allocation := _HouseholdAssetBar.new()
	allocation.values = asset
	allocation.font = _sans
	allocation.custom_minimum_size = Vector2(0, 48)
	header_col.add_child(allocation)
	parent.add_child(header)

	var member_head := HBoxContainer.new()
	member_head.add_child(_lbl("MEMBERS · 成员档案", 9, INK3, true))
	var members: Array = household.get("members", []).duplicate()
	var target_present := false
	for member: Dictionary in members:
		if int(member.get("person_id", -1)) == _person_selected:
			target_present = true
			break
	if target_present:
		member_head.add_child(_chip("已定位 P%03d" % _person_selected,
			Color("285ca8"), BLUE_BG, BLUE_BD, 7))
	member_head.add_child(_spacer_h())
	member_head.add_child(_lbl("个人资产不含家庭层登记的住房产权", 8, INK3))
	parent.add_child(member_head)
	if target_present:
		members.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
			var a_id := int(a.get("person_id", -1))
			var b_id := int(b.get("person_id", -1))
			if a_id == _person_selected:
				return true
			if b_id == _person_selected:
				return false
			return a_id < b_id)
	for member: Dictionary in members:
		parent.add_child(_household_member_card(
			member, int(member.get("person_id", -1)) == _person_selected))


func _household_member_card(member: Dictionary, focused: bool = false) -> Control:
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", _sb(
		Color("f4f8ff") if focused else Color.WHITE,
		BLUE_BD if focused else Color("dfe6ee"), 10, 9, 3 if focused else 0))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 6)
	card.add_child(col)
	var sex := str(member.get("sex", ""))
	var sex_text := "女" if sex == "F" else "男" if sex == "M" else "未知"
	var sex_color := Color("c17b16") if sex == "F" else Color("3274d9")
	var identity := HBoxContainer.new()
	identity.add_theme_constant_override("separation", 6)
	identity.add_child(_dot(sex_color, 8))
	identity.add_child(_lbl("成员 P%03d" % int(member.get("person_id", 0)), 12, INK, true))
	identity.add_child(_chip("%s · %d 岁" % [sex_text, int(member.get("age", 0))],
		sex_color.darkened(0.18), Color(sex_color.r, sex_color.g, sex_color.b, 0.09),
		Color(sex_color.r, sex_color.g, sex_color.b, 0.32), 8))
	identity.add_child(_chip(str(member.get("relationship", "成员")),
		TEAL_DK, TEAL_BG, TEAL_BD, 8))
	if focused:
		identity.add_child(_chip("当前员工", Color("285ca8"), BLUE_BG, BLUE_BD, 8))
	identity.add_child(_spacer_h())
	identity.add_child(_chip(str(member.get("labor_status", "")),
		INK2, PANEL2, LINE2, 8))
	col.add_child(identity)
	var links: Array[String] = []
	if member.get("mother_id") != null:
		links.append("母 P%03d" % int(member.get("mother_id")))
	if member.get("father_id") != null:
		links.append("父 P%03d" % int(member.get("father_id")))
	if member.get("partner_id") != null:
		links.append("伴侣 P%03d" % int(member.get("partner_id")))
	if member.get("guardian_id") != null:
		links.append("监护 P%03d" % int(member.get("guardian_id")))
	var demographic := "出生 %s · %s" % [
		str(member.get("birth_date", "—")), str(member.get("marital_status", "—"))]
	if not links.is_empty():
		demographic += " · " + " / ".join(links)
	col.add_child(_lbl(demographic, 8, INK3, true))

	var assets: Dictionary = member.get("assets", {})
	var finance := HBoxContainer.new()
	finance.add_theme_constant_override("separation", 5)
	finance.add_child(_household_summary_card("个人资产",
		_fmt_val("num", float(assets.get("total", 0.0))), TEAL))
	finance.add_child(_household_summary_card("个人负债",
		_fmt_val("num", float(member.get("debt", 0.0))), AMBER))
	finance.add_child(_household_summary_card("个人净资产",
		_fmt_val("num", float(member.get("net_worth", 0.0))), PURPLE))
	finance.add_child(_household_summary_card("本期消费",
		_fmt_val("num", float(member.get("consumption", 0.0))), BLUE))
	col.add_child(finance)
	col.add_child(_lbl("资产构成  现金 %s · 企业股权 %s · 银行股权 %s · 债券 %s" % [
		_fmt_val("num", float(assets.get("cash", 0.0))),
		_fmt_val("num", float(assets.get("firm_equity", 0.0))),
		_fmt_val("num", float(assets.get("bank_equity", 0.0))),
		_fmt_val("num", float(assets.get("bonds", 0.0)))], 8, INK2, true))
	var income: Dictionary = member.get("income", {})
	var work_text := "收入  劳动 %s · 资本 %s · 转移 %s" % [
		_fmt_val("num", float(income.get("labor", 0.0))),
		_fmt_val("num", float(income.get("capital", 0.0))),
		_fmt_val("num", float(income.get("transfer", 0.0)))]
	col.add_child(_lbl(work_text, 8, INK3, true))
	var employers: Array = member.get("employers", []).duplicate()
	var employer: Variant = member.get("employer")
	if employers.is_empty() and employer is Dictionary:
		employers.append(employer)
	if not employers.is_empty():
		var employment_links := HFlowContainer.new()
		employment_links.add_theme_constant_override("h_separation", 5)
		employment_links.add_theme_constant_override("v_separation", 4)
		employment_links.add_child(_lbl("劳动合同", 8, INK3, true))
		for employment: Dictionary in employers:
			var firm_id := str(employment.get("firm_id", ""))
			var link := Button.new()
			link.text = "%s ↗  %s · %s/%s · %.2f FTE" % [
				firm_id, str(employment.get("sector", "企业")),
				str(employment.get("contract", "合同")), str(employment.get("status", "在岗")),
				float(employment.get("hours", 0.0))]
			link.add_theme_font_size_override("font_size", 8)
			link.add_theme_color_override("font_color", Color("285ca8"))
			link.add_theme_stylebox_override("normal", _sb(Color("eef5ff"), Color("c9dcf5"), 7, 4))
			link.add_theme_stylebox_override("hover", _sb(Color("e2eeff"), BLUE_BD, 7, 4, 2))
			link.tooltip_text = "打开 %s 企业详情" % firm_id
			link.pressed.connect(func() -> void:
				_open_firm(firm_id))
			employment_links.add_child(link)
		col.add_child(employment_links)
	return card


func _firm_number(value: Variant, kind: String = "num") -> String:
	if value == null:
		return "不适用"
	return _fmt_val(kind, float(value))


func _firm_sector_color(sector_code: String) -> Color:
	return {
		"necessity": TEAL,
		"luxury": PURPLE,
		"consumption": BLUE,
		"capital": Color("4a6fa5"),
		"energy": Color("b56b0b"),
		"bank": Color("7a54b3"),
	}.get(sector_code, INK3)


func _firm_sort_value(item: Dictionary) -> float:
	match _firm_sort:
		"earnings":
			return float((item.get("operations", {}) as Dictionary).get("earnings", 0.0))
		"assets":
			return float((item.get("balance_sheet", {}) as Dictionary).get("gross_assets", 0.0))
		_:
			return float((item.get("operations", {}) as Dictionary).get("revenue", 0.0))


func _firm_matches(item: Dictionary) -> bool:
	var query := _firm_search.strip_edges().to_lower()
	if query.is_empty():
		return true
	for text in [item.get("firm_id", ""), item.get("sector", ""),
			item.get("condition", "")]:
		if str(text).to_lower().contains(query):
			return true
	var labor: Dictionary = item.get("labor", {})
	for employee: Dictionary in labor.get("employees", []):
		var person_id := int(employee.get("person_id", -1))
		if str(person_id).contains(query) or ("p%03d" % person_id).contains(query):
			return true
	return false


func _firm_data_panel(title: String, rows: Array, note: String = "") -> Control:
	var panel := PanelContainer.new()
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel.add_theme_stylebox_override("panel", _sb(Color.WHITE, Color("dfe6ee"), 10, 9))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 4)
	panel.add_child(col)
	var head := HBoxContainer.new()
	head.add_child(_lbl(title, 8, INK3, true))
	head.add_child(_spacer_h())
	if not note.is_empty():
		head.add_child(_lbl(note, 7, INK3))
	col.add_child(head)
	for spec: Array in rows:
		var line := HBoxContainer.new()
		line.add_child(_lbl(str(spec[0]), 8, INK2))
		line.add_child(_spacer_h())
		var color: Color = spec[2] if spec.size() > 2 else INK
		line.add_child(_lbl(str(spec[1]), 8, color, true))
		col.add_child(line)
	return panel


func _firm_section_head(parent: VBoxContainer, title: String, note: String = "") -> void:
	var row := HBoxContainer.new()
	row.add_child(_lbl(title, 9, INK3, true))
	row.add_child(_spacer_h())
	if not note.is_empty():
		row.add_child(_lbl(note, 8, INK3))
	parent.add_child(row)


func _render_firms_tab(body: VBoxContainer) -> void:
	var payload: Dictionary = _snapshot.get("firms", {})
	var summary: Dictionary = payload.get("summary", {})
	var all_items: Array = payload.get("items", [])
	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 7)
	top.add_child(_household_summary_card("FIRMS · 企业",
		str(int(summary.get("firm_count", 0))), TEAL, "家"))
	top.add_child(_household_summary_card("EMPLOYMENT · 在岗",
		"%.1f" % float(summary.get("employment_fte", 0.0)), BLUE, "FTE"))
	top.add_child(_household_summary_card("REVENUE · 总营收",
		_fmt_val("num", float(summary.get("total_revenue", 0.0))), PURPLE))
	top.add_child(_household_summary_card("EARNINGS · 总利润",
		_fmt_val("num", float(summary.get("total_earnings", 0.0))), AMBER))
	body.add_child(top)

	var toolbar := PanelContainer.new()
	toolbar.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 10, 6))
	var tools := HBoxContainer.new()
	tools.add_theme_constant_override("separation", 6)
	toolbar.add_child(tools)
	tools.add_child(_lbl("企业微观档案", 11, INK))
	tools.add_child(_chip("LIVE BOOKS · 实时账表", Color("285ca8"),
		Color("eef5ff"), Color("c9dcf5"), 8))
	tools.add_child(_spacer_h())
	var search := LineEdit.new()
	search.custom_minimum_size.x = 145
	search.placeholder_text = "企业 / 部门 / 员工ID · 回车"
	search.text = _firm_search
	search.add_theme_font_size_override("font_size", 9)
	search.add_theme_color_override("font_color", INK2)
	search.add_theme_color_override("font_placeholder_color", INK3)
	search.add_theme_color_override("caret_color", BLUE)
	search.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 8, 5))
	search.add_theme_stylebox_override("focus", _sb(Color.WHITE, BLUE_BD, 8, 5, 2))
	search.text_submitted.connect(func(value: String) -> void:
		_firm_search = value
		_render())
	tools.add_child(search)
	for sort_spec: Array in [["revenue", "营收"], ["earnings", "利润"], ["assets", "资产"]]:
		var sort_id := str(sort_spec[0])
		var sort_button := Button.new()
		sort_button.text = str(sort_spec[1])
		sort_button.add_theme_font_size_override("font_size", 8)
		if sort_id == _firm_sort:
			sort_button.add_theme_stylebox_override("normal", _sb(BLUE_BG, BLUE_BD, 8, 5))
			sort_button.add_theme_color_override("font_color", Color("285ca8"))
		sort_button.pressed.connect(func() -> void:
			_firm_sort = sort_id
			_render())
		tools.add_child(sort_button)
	body.add_child(toolbar)

	var items: Array = []
	for item: Dictionary in all_items:
		if _firm_matches(item):
			items.append(item)
	items.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		var av := _firm_sort_value(a)
		var bv := _firm_sort_value(b)
		if is_equal_approx(av, bv):
			return str(a.get("firm_id", "")) < str(b.get("firm_id", ""))
		return av > bv)
	if items.is_empty():
		var empty := PanelContainer.new()
		empty.size_flags_vertical = Control.SIZE_EXPAND_FILL
		empty.add_theme_stylebox_override("panel", _sb(PANEL, LINE, 12, 18))
		empty.add_child(_lbl("没有匹配的企业。清空搜索词后重试。", 11, INK3))
		body.add_child(empty)
		return
	var selected_found := false
	for item: Dictionary in items:
		if str(item.get("firm_id", "")) == _firm_selected:
			selected_found = true
			break
	if not selected_found:
		_firm_selected = str((items[0] as Dictionary).get("firm_id", ""))

	var main := HBoxContainer.new()
	main.size_flags_vertical = Control.SIZE_EXPAND_FILL
	main.add_theme_constant_override("separation", 9)
	body.add_child(main)
	var list_shell := PanelContainer.new()
	list_shell.custom_minimum_size.x = 205
	list_shell.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	list_shell.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list_shell.add_theme_stylebox_override("panel", _sb(Color("f7f9fc"), LINE, 11, 7))
	var list_col := VBoxContainer.new()
	list_col.add_theme_constant_override("separation", 6)
	list_shell.add_child(list_col)
	var list_head := HBoxContainer.new()
	list_head.add_child(_lbl("COMPANY INDEX", 8, INK3, true))
	list_head.add_child(_spacer_h())
	list_head.add_child(_lbl("%d / %d" % [items.size(), all_items.size()], 8, INK3, true))
	list_col.add_child(list_head)
	var list_scroll := ScrollContainer.new()
	list_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	list_col.add_child(list_scroll)
	_restore_scroll("center:firms:list", list_scroll)
	list_scroll.get_v_scroll_bar().value_changed.connect(func(v: float) -> void:
		_scroll_mem["center:firms:list"] = int(v))
	var list_items := VBoxContainer.new()
	list_items.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list_items.add_theme_constant_override("separation", 5)
	list_scroll.add_child(list_items)
	var selected: Dictionary = items[0]
	for item: Dictionary in items:
		var firm_id := str(item.get("firm_id", ""))
		var active := firm_id == _firm_selected
		if active:
			selected = item
		var operations: Dictionary = item.get("operations", {})
		var labor: Dictionary = item.get("labor", {})
		var entry := Button.new()
		entry.custom_minimum_size = Vector2(188, 57)
		entry.alignment = HORIZONTAL_ALIGNMENT_LEFT
		entry.text = "%s  ·  %s\n营收 %s  ·  利润 %s  ·  %.1f FTE" % [
			firm_id, str(item.get("sector", "企业")),
			_fmt_val("num", float(operations.get("revenue", 0.0))),
			_fmt_val("num", float(operations.get("earnings", 0.0))),
			float(labor.get("employment_fte", 0.0))]
		entry.add_theme_font_size_override("font_size", 8)
		entry.add_theme_stylebox_override("normal", _sb(
			Color("eef5ff") if active else Color.WHITE,
			BLUE_BD if active else Color("dfe6ee"), 9, 7, 3 if active else 0))
		entry.add_theme_color_override("font_color", Color("1f4f91") if active else INK2)
		entry.tooltip_text = "查看 %s 的经营、财务、员工与所有权档案" % firm_id
		entry.pressed.connect(func() -> void:
			_firm_selected = firm_id
			_render())
		list_items.add_child(entry)
	main.add_child(list_shell)

	var detail_scroll := ScrollContainer.new()
	detail_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	detail_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	main.add_child(detail_scroll)
	_restore_scroll("center:firms:detail", detail_scroll)
	detail_scroll.get_v_scroll_bar().value_changed.connect(func(v: float) -> void:
		_scroll_mem["center:firms:detail"] = int(v))
	var detail := VBoxContainer.new()
	detail.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail.add_theme_constant_override("separation", 8)
	detail_scroll.add_child(detail)
	_render_firm_detail(detail, selected, str(payload.get("as_of_date", "")))


func _render_firm_detail(parent: VBoxContainer, firm: Dictionary, as_of_date: String) -> void:
	var operations: Dictionary = firm.get("operations", {})
	var labor: Dictionary = firm.get("labor", {})
	var capital: Dictionary = firm.get("capital", {})
	var book: Dictionary = firm.get("balance_sheet", {})
	var pnl: Dictionary = firm.get("pnl", {})
	var equity: Dictionary = firm.get("equity", {})
	var parameters: Dictionary = firm.get("parameters", {})
	var signals: Dictionary = firm.get("signals", {})
	var bank: Dictionary = firm.get("bank", {})
	var sector_color := _firm_sector_color(str(firm.get("sector_code", "")))
	var condition := str(firm.get("condition", "正常经营"))
	var condition_color := GREEN if condition == "正常经营" else RED

	var header := PanelContainer.new()
	header.add_theme_stylebox_override("panel", _sb(Color("f9fbfd"), Color("dce5ee"), 11, 9, 4))
	var header_col := VBoxContainer.new()
	header_col.add_theme_constant_override("separation", 6)
	header.add_child(header_col)
	var title := HBoxContainer.new()
	title.add_child(_dot(sector_color, 8))
	title.add_child(_lbl(str(firm.get("firm_id", "企业")), 15, INK, true))
	title.add_child(_chip(str(firm.get("sector", "企业")),
		sector_color.darkened(0.15), Color(sector_color.r, sector_color.g, sector_color.b, 0.09),
		Color(sector_color.r, sector_color.g, sector_color.b, 0.30), 8))
	if bool(firm.get("state_owned", false)):
		title.add_child(_chip("国有企业", Color("9a6812"), AMBER_BG, AMBER_BD, 8))
	title.add_child(_chip(condition, condition_color.darkened(0.12),
		Color(condition_color.r, condition_color.g, condition_color.b, 0.09),
		Color(condition_color.r, condition_color.g, condition_color.b, 0.28), 8))
	title.add_child(_spacer_h())
	title.add_child(_lbl("截至 %s" % as_of_date, 8, INK3, true))
	header_col.add_child(title)
	var metrics := HBoxContainer.new()
	metrics.add_theme_constant_override("separation", 6)
	metrics.add_child(_household_summary_card("本期营收",
		_firm_number(operations.get("revenue")), TEAL))
	metrics.add_child(_household_summary_card("本期利润",
		_firm_number(operations.get("earnings")), AMBER))
	metrics.add_child(_household_summary_card("总资产",
		_firm_number(book.get("gross_assets")), PURPLE))
	metrics.add_child(_household_summary_card("债务本金",
		_firm_number(book.get("debt")), BLUE))
	header_col.add_child(metrics)
	var bank_text := "往来银行 %s · 贷款利率 %s" % [
		str(bank.get("bank_id", "无")), _firm_number(bank.get("loan_rate"), "pt")]
	var identity_text := "技术 %s · 产品 %s · %s · %s" % [
		str(firm.get("technology", "—")), str(firm.get("sells", "—")),
		"实施投资" if bool(firm.get("invests", false)) else "不实施投资",
		"独立上市" if bool(equity.get("enabled", false)) else "未发行独立股份"]
	header_col.add_child(_lbl(identity_text + "   |   " + bank_text, 8, INK3, true))
	parent.add_child(header)

	_firm_section_head(parent, "OPERATIONS · 经营与生产", "计划 → 生产 → 销售 → 库存")
	var operating_metrics := HBoxContainer.new()
	operating_metrics.add_theme_constant_override("separation", 5)
	for spec: Array in [
		["需求预期", operations.get("demand_expected"), TEAL],
		["计划产量", operations.get("production_target"), BLUE],
		["实际产量", operations.get("produced"), PURPLE],
		["销量", operations.get("sales"), AMBER],
	]:
		operating_metrics.add_child(_household_summary_card(
			str(spec[0]), _firm_number(spec[1]), spec[2]))
	parent.add_child(operating_metrics)
	var operating_panels := HBoxContainer.new()
	operating_panels.add_theme_constant_override("separation", 7)
	operating_panels.add_child(_firm_data_panel("PRICE & MARGIN · 价格成本", [
		["售价", _firm_number(operations.get("price"))],
		["发布工资", _firm_number(operations.get("wage"))],
		["加成率", _firm_number(operations.get("markup"), "pct")],
		["工资总额", _firm_number(operations.get("wagebill"))],
		["资本服务单位成本", _firm_number(operations.get("pricing_capital_unit_cost")) if bool(operations.get("capital_service_pricing_enabled", false)) else "不适用"],
		["资本服务成本", _firm_number(operations.get("pricing_capital_service_cost")) if bool(operations.get("capital_service_pricing_enabled", false)) else "不适用"],
		["资本服务率", _firm_number(operations.get("pricing_capital_service_rate"), "pct") if bool(operations.get("capital_service_pricing_enabled", false)) else "不适用"],
		["目标库存", _firm_number(operations.get("target_inventory"))],
		["库存实物量", _firm_number(operations.get("inventory"))],
		["受抑需求", _firm_number(operations.get("rationed_demand"))],
	]))
	operating_panels.add_child(_firm_data_panel("REALIZATION · 执行效率", [
		["生产实现率", _firm_number(operations.get("production_realization"), "pct")],
		["产销率", _firm_number(operations.get("sales_realization"), "pct")],
		["名义劳动需求", _firm_number(labor.get("labor_demand_notional"))],
		["有效劳动需求", _firm_number(labor.get("labor_demand_effective"))],
		["劳动效率单位", _firm_number(labor.get("efficiency_units"))],
		["未填岗位", _firm_number(labor.get("vacancies"))],
		["岗位空缺持续", "%d 天" % int(labor.get("vacancy_age", 0))],
		["在岗人数", str(int(labor.get("active_heads", 0)))],
		["在岗 FTE", "%.2f" % float(labor.get("employment_fte", 0.0))],
	]))
	parent.add_child(operating_panels)

	_firm_section_head(parent, "INCOME STATEMENT · 本期损益",
		"完整损益表" if bool(pnl.get("full_statement", false)) else "兼容口径 · legacy profit")
	var pnl_panels := HBoxContainer.new()
	pnl_panels.add_theme_constant_override("separation", 7)
	pnl_panels.add_child(_firm_data_panel("OPERATING · 营业损益", [
		["营业收入", _firm_number(pnl.get("revenue")), TEAL],
		["期初未结收入", _firm_number(pnl.get("revenue_carry_opening"))],
		["期末未结收入", _firm_number(pnl.get("revenue_carry"))],
		["中间投入", _firm_number(pnl.get("intermediate_inputs"))],
		["职工薪酬", _firm_number(pnl.get("compensation"))],
		["EBITDA", _firm_number(pnl.get("ebitda")), PURPLE],
		["资本计价", _firm_number(pnl.get("capital_price"))],
		["折旧", _firm_number(pnl.get("depreciation"))],
		["EBIT", _firm_number(pnl.get("ebit")), PURPLE],
		["税前利润", _firm_number(pnl.get("pre_tax_income")), AMBER],
	]))
	pnl_panels.add_child(_firm_data_panel("FINANCING · 利息税费与分配", [
		["应计利息", _firm_number(pnl.get("interest_accrued"))],
		["到期利息", _firm_number(pnl.get("interest_due"))],
		["实付利息", _firm_number(pnl.get("interest_paid"))],
		["利息缺口", _firm_number(pnl.get("interest_shortfall")), RED],
		["期初利息欠款", _firm_number(pnl.get("interest_arrears_opening"))],
		["期末利息欠款", _firm_number(pnl.get("interest_arrears")), RED],
		["利润税", _firm_number(pnl.get("profit_tax"))],
		["暴利税", _firm_number(pnl.get("windfall_tax"))],
		["净利润", _firm_number(pnl.get("net_income")), AMBER],
		["股息", _firm_number(pnl.get("dividends"))],
		["留存收益", _firm_number(pnl.get("retained_earnings"))],
	]))
	parent.add_child(pnl_panels)

	_firm_section_head(parent, "BALANCE SHEET · 资产负债表", "重置成本计价 · 利息欠款单列")
	var book_panels := HBoxContainer.new()
	book_panels.add_theme_constant_override("separation", 7)
	book_panels.add_child(_firm_data_panel("ASSETS · 资产", [
		["现金", _firm_number(book.get("cash")), TEAL],
		["生产资本", _firm_number(book.get("capital_value"))],
		["产成品库存", _firm_number(book.get("output_inventory_value"))],
		["在产品", _firm_number(book.get("work_in_progress_value"))],
		["投入品库存", _firm_number(book.get("input_inventory_value"))],
		["总资产", _firm_number(book.get("gross_assets")), PURPLE],
	]))
	book_panels.add_child(_firm_data_panel("LIABILITIES & CREDIT · 融资", [
		["债务本金", _firm_number(book.get("debt")), BLUE],
		["利息欠款", _firm_number(book.get("interest_arrears")), RED],
		["账面权益", _firm_number(book.get("book_equity")), PURPLE],
		["合格抵押品", _firm_number(book.get("eligible_collateral_value"))],
		["借款基础", _firm_number(book.get("borrowing_base_proxy"))],
		["新增借款空间", _firm_number(book.get("borrowing_base_headroom")), TEAL],
		["资本折扣", _firm_number(book.get("capital_haircut"), "pct")],
		["库存折扣", _firm_number(book.get("inventory_haircut"), "pct")],
	]))
	parent.add_child(book_panels)
	parent.add_child(_firm_data_panel("VALUATION DETAIL · 实物量与计价依据", [
		["资本实物量", _firm_number(book.get("capital_units"))],
		["资本单位重置价", _firm_number(book.get("capital_unit_price"))],
		["产成品实物量", _firm_number(book.get("output_inventory_units"))],
		["产成品单位计价", _firm_number(book.get("output_inventory_unit_price"))],
		["在产品实物量", _firm_number(book.get("work_in_progress_units"))],
		["投入品实物量", _firm_number(book.get("input_inventory_units"))],
	], "资产重估只改变观察与授信依据，不创造现金"))

	_firm_section_head(parent, "CAPITAL & ENERGY · 资本形成与能源投入")
	var capital_panels := HBoxContainer.new()
	capital_panels.add_theme_constant_override("separation", 7)
	capital_panels.add_child(_firm_data_panel("CAPITAL · 生产资本", [
		["资本实物量", _firm_number(capital.get("units"))],
		["上期资本", _firm_number(capital.get("previous_units"))],
		["投资目标", _firm_number(capital.get("investment_target")) if bool(firm.get("invests", false)) else "不适用"],
		["实际投资", _firm_number(capital.get("investment")) if bool(firm.get("invests", false)) else "不适用"],
		["资本单位重置价", _firm_number(book.get("capital_unit_price"))],
		["折旧率", _firm_number(capital.get("depreciation_rate"), "pct") if bool(firm.get("invests", false)) else "不适用"],
		["产能上限", _firm_number(capital.get("capacity")) if str(firm.get("sector_code", "")) == "energy" else "不适用"],
	]))
	capital_panels.add_child(_firm_data_panel("ENERGY INPUT · 能源投入", [
		["投入库存", _firm_number(capital.get("energy_input_stock")) if str(firm.get("sector_code", "")) != "energy" else "不适用"],
		["投入库存账面成本", _firm_number(capital.get("energy_input_stock_cost")) if str(firm.get("sector_code", "")) != "energy" else "不适用"],
		["库存平均成本", _firm_number(capital.get("energy_input_average_cost")) if str(firm.get("sector_code", "")) != "energy" else "不适用"],
		["本期购入", _firm_number(capital.get("energy_bought")) if str(firm.get("sector_code", "")) != "energy" else "不适用"],
		["本期消耗", _firm_number(capital.get("energy_used")) if str(firm.get("sector_code", "")) != "energy" else "不适用"],
		["能源成本", _firm_number(capital.get("energy_cost_used")) if str(firm.get("sector_code", "")) != "energy" else "不适用"],
	]))
	parent.add_child(capital_panels)

	_firm_section_head(parent, "WORKFORCE · 员工与劳动合同",
		"%d 份合同 · %.2f FTE" % [int(labor.get("contract_count", 0)), float(labor.get("employment_fte", 0.0))])
	parent.add_child(_firm_workforce_panel(labor.get("employees", [])))

	_firm_section_head(parent, "EQUITY & OWNERSHIP · 股权与所有权",
		"逐人持仓 · 不与家庭账户重复")
	parent.add_child(_firm_equity_panel(equity))

	_firm_section_head(parent, "MODEL STATE · 行为、技术参数与退出信号", "只读结构参数与状态信号")
	var parameter_panels := HBoxContainer.new()
	parameter_panels.add_theme_constant_override("separation", 7)
	parameter_panels.add_child(_firm_data_panel("BEHAVIOR · 行为参数", [
		["需求调整 λd", _firm_number(parameters.get("demand_adjustment"))],
		["目标库存率 φ", _firm_number(parameters.get("inventory_target_ratio"))],
		["加成调整 η", _firm_number(parameters.get("markup_adjustment"))],
		["加成下限", _firm_number(parameters.get("markup_min"), "pct")],
		["加成上限", _firm_number(parameters.get("markup_max"), "pct")],
		["工资调整 ω", _firm_number(parameters.get("wage_adjustment"))],
		["股息支付率 ρ", _firm_number(parameters.get("dividend_payout_ratio"), "pct")],
		["协调成本斜率", _firm_number(parameters.get("coordination_cost_slope"))],
	]))
	parameter_panels.add_child(_firm_data_panel("TECH & SIGNALS · 技术与信号", [
		["劳动生产率 a", _firm_number(parameters.get("labor_productivity"))],
		["全要素生产率 A", _firm_number(parameters.get("tfp"))],
		["资本份额 α", _firm_number(parameters.get("capital_share"), "pct")],
		["目标资本产出比 v", _firm_number(parameters.get("capital_output_target"))],
		["投资调整 λI", _firm_number(parameters.get("investment_adjustment"))],
		["能源强度", _firm_number(parameters.get("energy_intensity"))],
		["产能系数 κ", _firm_number(parameters.get("capacity_kappa"))],
		["上期销量", _firm_number(signals.get("previous_sales"))],
		["上期用工", _firm_number(signals.get("previous_hiring"))],
		["上期有效劳动需求", _firm_number(signals.get("previous_effective_labor_demand"))],
		["上期目标库存", _firm_number(signals.get("previous_target_inventory"))],
		["上期受抑需求", _firm_number(signals.get("previous_rationed_demand"))],
		["部门转换压力", "%d 天" % int(signals.get("sector_switch_pressure", 0))],
		["股息支付缺口", _firm_number(signals.get("dividend_shortfall"))],
		["闲置 / 资不抵债 / 低规模", "%d / %d / %d 天" % [
			int(signals.get("idle_ticks", 0)), int(signals.get("insolvent_ticks", 0)),
			int(signals.get("subscale_ticks", 0))], RED if condition != "正常经营" else INK],
	]))
	parent.add_child(parameter_panels)


func _firm_workforce_panel(employees: Array) -> Control:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _sb(Color.WHITE, Color("dfe6ee"), 10, 9))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 5)
	panel.add_child(col)
	if employees.is_empty():
		col.add_child(_lbl("当前没有劳动合同。", 9, INK3))
		return panel
	for i in employees.size():
		var employee: Dictionary = employees[i]
		if i > 0:
			col.add_child(_hrule())
		var sex := str(employee.get("sex", ""))
		var sex_text := "女" if sex == "F" else "男" if sex == "M" else "—"
		var person_id := int(employee.get("person_id", -1))
		var age_text := "—" if employee.get("age") == null else "%d 岁" % int(employee.get("age"))
		var household_text := "—" if employee.get("household_id") == null else "家庭 #%03d" % int(employee.get("household_id"))
		var row := HBoxContainer.new()
		row.add_child(_lbl("P%03d · %s · %s" % [person_id, sex_text, age_text], 9, INK, true))
		row.add_child(_chip(str(employee.get("contract", "合同")), INK2, PANEL2, LINE2, 7))
		if str(employee.get("status", "在岗")) != "在岗":
			row.add_child(_chip(str(employee.get("status")), RED, RED_BG, RED_BD, 7))
		row.add_child(_spacer_h())
		row.add_child(_lbl("%.2f FTE" % float(employee.get("hours", 0.0)), 9, TEAL, true))
		var employee_household: Variant = employee.get("household_id")
		var person_link := Button.new()
		person_link.text = "员工档案 ↗"
		person_link.disabled = employee_household == null
		person_link.add_theme_font_size_override("font_size", 8)
		person_link.add_theme_color_override("font_color", Color("285ca8"))
		person_link.add_theme_stylebox_override("normal", _sb(Color("eef5ff"), Color("c9dcf5"), 7, 4))
		person_link.add_theme_stylebox_override("hover", _sb(Color("e2eeff"), BLUE_BD, 7, 4, 2))
		person_link.tooltip_text = "打开 P%03d 的家庭成员档案" % person_id
		person_link.pressed.connect(func() -> void:
			_open_person(person_id, employee_household))
		row.add_child(person_link)
		col.add_child(row)
		col.add_child(_lbl("%s · 入职 %s · 合同 %.2f FTE · 锁定工资 %s · 实付工资率 %s · 效率 %.2f · 本期薪酬 %s" % [
			household_text, str(employee.get("hire_date", "—")),
			float(employee.get("contract_hours", 0.0)), _firm_number(employee.get("locked_wage")),
			_firm_number(employee.get("paid_wage")), float(employee.get("efficiency", 1.0)),
			_firm_number(employee.get("compensation"))], 8, INK3, true))
		if employee.get("suspended_since_tick") != null:
			col.add_child(_lbl("停薪留职自 %s · 停薪前工资 %s · 合同仍保留召回权" % [
				_cal_short(int(employee.get("suspended_since_tick"))),
				_firm_number(employee.get("suspension_wage"))], 8, RED, true))
	return panel


func _firm_equity_panel(equity: Dictionary) -> Control:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _sb(Color.WHITE, Color("dfe6ee"), 10, 9))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 5)
	panel.add_child(col)
	if not bool(equity.get("enabled", false)):
		col.add_child(_lbl("该企业未发行独立交易股份；股价、市值、Q 与股东名单不适用。", 9, INK3))
		return panel
	var metrics := HBoxContainer.new()
	metrics.add_theme_constant_override("separation", 5)
	metrics.add_child(_household_summary_card("股价", _firm_number(equity.get("share_price")), BLUE))
	metrics.add_child(_household_summary_card("总市值", _firm_number(equity.get("market_cap")), TEAL))
	metrics.add_child(_household_summary_card("托宾 Q", _firm_number(equity.get("tobin_q"), "idx"), PURPLE))
	metrics.add_child(_household_summary_card("基本面/股", _firm_number(equity.get("fundamental_per_share")), AMBER))
	col.add_child(metrics)
	col.add_child(_lbl("流通股 %s · 上期股价 %s · 趋势 %s · 平滑 Q %s · 吸引力 %s · 剩余收益 EMA %s" % [
		_firm_number(equity.get("shares_outstanding")),
		_firm_number(equity.get("last_share_price")),
		_firm_number(equity.get("share_trend"), "idx"),
		_firm_number(equity.get("tobin_q_ema"), "idx"),
		_firm_number(equity.get("attractiveness"), "idx"),
		_firm_number(equity.get("residual_income_ema"))], 8, INK3, true))
	var holders: Array = equity.get("shareholders", [])
	var holder_head := HBoxContainer.new()
	holder_head.add_child(_lbl("SHAREHOLDERS · 全部逐人股东", 8, INK3, true))
	holder_head.add_child(_spacer_h())
	holder_head.add_child(_lbl("%d 人 · 已观察 %s" % [
		int(equity.get("shareholder_count", 0)),
		_firm_number(equity.get("ownership_coverage"), "pct")], 8, INK3))
	col.add_child(holder_head)
	if holders.is_empty():
		col.add_child(_lbl("当前未观察到个人股权索取权。", 8, INK3))
		return panel
	for holder: Dictionary in holders:
		var row := HBoxContainer.new()
		var household_text := "—" if holder.get("household_id") == null else "家庭 #%03d" % int(holder.get("household_id"))
		row.add_child(_lbl("P%03d · %s" % [int(holder.get("person_id", -1)), household_text], 8, INK2, true))
		row.add_child(_spacer_h())
		row.add_child(_lbl("%s 股 · %s · 市值 %s" % [
			_firm_number(holder.get("shares")),
			_firm_number(holder.get("ownership"), "pct"),
			_firm_number(holder.get("market_value"))], 8, INK, true))
		col.add_child(row)
	return panel


func _stock_delta_color(change: float) -> Color:
	if change > 0.0000001:
		return GREEN
	if change < -0.0000001:
		return RED
	return INK3


func _stock_delta_text(change: float) -> String:
	if change > 0.0000001:
		return "▲ +%.2f%%" % (change * 100.0)
	if change < -0.0000001:
		return "▼ %.2f%%" % (change * 100.0)
	return "— 0.00%"


func _stock_summary_card(label: String, value: String, color: Color,
		delta: String = "", note: String = "") -> Control:
	var card := PanelContainer.new()
	card.custom_minimum_size.y = 58
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	card.add_theme_stylebox_override("panel", _sb(Color("f8fafc"), Color("e0e7ef"), 10, 8))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 1)
	card.add_child(col)
	col.add_child(_lbl(label, 8, INK3, true))
	var row := HBoxContainer.new()
	row.add_child(_lbl(value, 16, color, true))
	row.add_child(_spacer_h())
	if not delta.is_empty():
		row.add_child(_lbl(delta, 8, color, true))
	col.add_child(row)
	if not note.is_empty():
		col.add_child(_lbl(note, 7, INK3, true))
	return card


func _stock_listing(listings: Array, symbol: String) -> Dictionary:
	for listing: Dictionary in listings:
		if str(listing.get("symbol", "")) == symbol:
			return listing
	return {}


func _stock_table_cell(text: String, width: float, color: Color = INK2,
		align: HorizontalAlignment = HORIZONTAL_ALIGNMENT_RIGHT,
		mono: bool = true) -> Label:
	var label := _lbl(text, 8, color, mono)
	label.custom_minimum_size.x = width
	label.horizontal_alignment = align
	label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	return label


func _render_stock_market_tab(body: VBoxContainer) -> void:
	var payload: Dictionary = _snapshot.get("stock_market", {})
	var summary: Dictionary = payload.get("summary", {})
	var listings: Array = payload.get("listings", [])
	var history: Array = payload.get("history", [])
	var index_change := float(summary.get("index_change", 0.0))
	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 7)
	top.add_child(_stock_summary_card("AURELIA ALL-SHARE",
		"%.2f" % float(summary.get("index_level", 1000.0)),
		_stock_delta_color(index_change), _stock_delta_text(index_change), "链式市值加权指数"))
	top.add_child(_stock_summary_card("MARKET CAP · 总市值",
		_fmt_val("num", float(summary.get("market_cap", 0.0))), PURPLE, "",
		"%d 只证券" % int(summary.get("listed_count", 0))))
	top.add_child(_stock_summary_card("TURNOVER · 换手率",
		_fmt_val("pct", float(summary.get("turnover", 0.0))), BLUE, "",
		"企业股与银行股市值加权"))
	top.add_child(_stock_summary_card("BREADTH · 市场宽度",
		"%d ↑  %d ↓" % [int(summary.get("advances", 0)), int(summary.get("declines", 0))],
		TEAL, "", "%d 平" % int(summary.get("unchanged", 0))))
	body.add_child(top)

	var toolbar := PanelContainer.new()
	toolbar.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 10, 6))
	var tools := HBoxContainer.new()
	tools.add_theme_constant_override("separation", 5)
	toolbar.add_child(tools)
	tools.add_child(_lbl("AURELIA EXCHANGE", 10, INK, true))
	tools.add_child(_chip("DAILY CLOSE", Color("285ca8"), BLUE_BG, Color("c9dcf5"), 7))
	tools.add_child(_spacer_h())
	var search := LineEdit.new()
	search.custom_minimum_size.x = 112
	search.placeholder_text = "代码 / 板块 · 回车"
	search.text = _stock_search
	search.add_theme_font_size_override("font_size", 8)
	search.add_theme_color_override("font_color", INK2)
	search.add_theme_color_override("font_placeholder_color", INK3)
	search.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 7, 4))
	search.add_theme_stylebox_override("focus", _sb(Color.WHITE, BLUE_BD, 7, 4, 2))
	search.text_submitted.connect(func(value: String) -> void:
		_stock_search = value
		_render())
	tools.add_child(search)
	for filter_spec: Array in [["all", "全部"], ["company", "企业股"], ["bank", "银行股"]]:
		var filter_id := str(filter_spec[0])
		var filter_button := Button.new()
		filter_button.text = str(filter_spec[1])
		filter_button.add_theme_font_size_override("font_size", 8)
		if filter_id == _stock_filter:
			filter_button.add_theme_stylebox_override("normal", _sb(BLUE_BG, BLUE_BD, 7, 4))
			filter_button.add_theme_color_override("font_color", Color("285ca8"))
		filter_button.pressed.connect(func() -> void:
			_stock_filter = filter_id
			_render())
		tools.add_child(filter_button)
	for sort_spec: Array in [["market_cap", "市值"], ["change", "涨跌"]]:
		var sort_id := str(sort_spec[0])
		var sort_button := Button.new()
		sort_button.text = str(sort_spec[1])
		sort_button.add_theme_font_size_override("font_size", 8)
		if sort_id == _stock_sort:
			sort_button.add_theme_stylebox_override("normal", _sb(TEAL_BG, TEAL_BD, 7, 4))
			sort_button.add_theme_color_override("font_color", TEAL_DK)
		sort_button.pressed.connect(func() -> void:
			_stock_sort = sort_id
			_render())
		tools.add_child(sort_button)
	body.add_child(toolbar)

	var selected := _stock_listing(listings, _stock_selected)
	var overview := HBoxContainer.new()
	overview.custom_minimum_size.y = 226
	overview.add_theme_constant_override("separation", 8)
	body.add_child(overview)
	var chart_shell := PanelContainer.new()
	chart_shell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	chart_shell.add_theme_stylebox_override("panel", _sb(Color.WHITE, Color("dfe6ee"), 11, 9, 3))
	var chart_col := VBoxContainer.new()
	chart_col.add_theme_constant_override("separation", 4)
	chart_shell.add_child(chart_col)
	var chart_head := HBoxContainer.new()
	var chart_title := str(payload.get("index_name", "AURELIA ALL-SHARE")) if selected.is_empty() else str(selected.get("symbol", ""))
	chart_head.add_child(_lbl(chart_title, 12, INK, true))
	if not selected.is_empty():
		var selected_color := _firm_sector_color(str(selected.get("sector_code", "")))
		chart_head.add_child(_chip(str(selected.get("sector", "证券")),
			selected_color.darkened(0.15),
			Color(selected_color.r, selected_color.g, selected_color.b, 0.09),
			Color(selected_color.r, selected_color.g, selected_color.b, 0.28), 7))
	chart_head.add_child(_spacer_h())
	if not selected.is_empty():
		var index_button := Button.new()
		index_button.text = "返回综合指数"
		index_button.add_theme_font_size_override("font_size", 8)
		index_button.pressed.connect(func() -> void:
			_stock_selected = ""
			_render())
		chart_head.add_child(index_button)
		if bool(selected.get("can_open_firm", false)):
			var firm_button := Button.new()
			firm_button.text = "企业详情 ↗"
			firm_button.add_theme_font_size_override("font_size", 8)
			var selected_symbol := str(selected.get("symbol", ""))
			firm_button.pressed.connect(func() -> void:
				_open_firm(selected_symbol))
			chart_head.add_child(firm_button)
	chart_col.add_child(chart_head)
	var chart_change := index_change if selected.is_empty() else float(selected.get("change", 0.0))
	var chart_value := float(summary.get("index_level", 1000.0)) if selected.is_empty() else float(selected.get("price", 0.0))
	var quote_line := HBoxContainer.new()
	quote_line.add_child(_lbl("%.3f" % chart_value, 19, _stock_delta_color(chart_change), true))
	quote_line.add_child(_lbl(_stock_delta_text(chart_change), 9, _stock_delta_color(chart_change), true))
	quote_line.add_child(_spacer_h())
	quote_line.add_child(_lbl("截至 %s" % str(payload.get("as_of_date", "")),
		8, INK3, true))
	chart_col.add_child(quote_line)
	var chart_values: Array = []
	for point: Dictionary in history:
		if selected.is_empty():
			chart_values.append(float(point.get("index_level", 0.0)))
		else:
			var prices: Dictionary = point.get("prices", {})
			if prices.has(str(selected.get("symbol", ""))):
				chart_values.append(float(prices[str(selected.get("symbol", ""))]))
	var chart := _StockMarketChart.new()
	chart.values = chart_values
	chart.line_color = _stock_delta_color(chart_change)
	chart.font = _mono
	chart.custom_minimum_size = Vector2(0, 130)
	chart.size_flags_vertical = Control.SIZE_EXPAND_FILL
	chart_col.add_child(chart)
	var chart_note := "总市值 %s · 企业股 %s · 银行股 %s" % [
		_fmt_val("num", float(summary.get("market_cap", 0.0))),
		_fmt_val("num", float(summary.get("corporate_market_cap", 0.0))),
		_fmt_val("num", float(summary.get("bank_market_cap", 0.0)))]
	if not selected.is_empty():
		var valuation: Variant = selected.get("tobin_q") if selected.get("tobin_q") != null else selected.get("price_to_book")
		chart_note = "窗口 %s – %s · 市值 %s · Q/PB %s · 基本面溢价 %s" % [
			_firm_number(selected.get("window_low")), _firm_number(selected.get("window_high")),
			_firm_number(selected.get("market_cap")), _firm_number(valuation, "idx"),
			_firm_number(selected.get("fundamental_gap"), "pct")]
	chart_col.add_child(_lbl(chart_note, 8, INK3, true))
	overview.add_child(chart_shell)

	var pulse_shell := PanelContainer.new()
	pulse_shell.custom_minimum_size.x = 188
	pulse_shell.size_flags_horizontal = Control.SIZE_SHRINK_END
	pulse_shell.add_theme_stylebox_override("panel", _sb(Color("f8fafc"), Color("dfe6ee"), 11, 8))
	var pulse := VBoxContainer.new()
	pulse.add_theme_constant_override("separation", 5)
	pulse_shell.add_child(pulse)
	var breadth_head := HBoxContainer.new()
	breadth_head.add_child(_lbl("MARKET BREADTH", 8, INK3, true))
	breadth_head.add_child(_spacer_h())
	breadth_head.add_child(_lbl("%d / %d / %d" % [
		int(summary.get("advances", 0)), int(summary.get("unchanged", 0)),
		int(summary.get("declines", 0))], 8, INK3, true))
	pulse.add_child(breadth_head)
	var breadth := _StockBreadthChart.new()
	breadth.advances = int(summary.get("advances", 0))
	breadth.unchanged = int(summary.get("unchanged", 0))
	breadth.declines = int(summary.get("declines", 0))
	breadth.font = _sans
	breadth.custom_minimum_size = Vector2(0, 34)
	pulse.add_child(breadth)
	pulse.add_child(_hrule())
	pulse.add_child(_lbl("SECTORS · 板块表现", 8, INK3, true))
	for sector: Dictionary in payload.get("sectors", []):
		var sector_row := HBoxContainer.new()
		var sector_change := float(sector.get("change", 0.0))
		sector_row.add_child(_dot(_stock_delta_color(sector_change), 6))
		sector_row.add_child(_lbl(str(sector.get("label", "")), 8, INK2))
		sector_row.add_child(_spacer_h())
		sector_row.add_child(_lbl(_stock_delta_text(sector_change), 8,
			_stock_delta_color(sector_change), true))
		pulse.add_child(sector_row)
	pulse.add_child(_hrule())
	for metric_spec: Array in [
		["企业平均 Q", _firm_number(summary.get("q_mean"), "idx")],
		["企业股权集中度", _firm_number(summary.get("ownership_gini"), "idx")],
		["企业股权/家庭财富", _firm_number(summary.get("equity_wealth_share"), "pct")],
	]:
		var metric_row := HBoxContainer.new()
		metric_row.add_child(_lbl(str(metric_spec[0]), 8, INK3))
		metric_row.add_child(_spacer_h())
		metric_row.add_child(_lbl(str(metric_spec[1]), 8, INK, true))
		pulse.add_child(metric_row)
	overview.add_child(pulse_shell)

	var visible_listings: Array = []
	var query := _stock_search.strip_edges().to_lower()
	for listing: Dictionary in listings:
		if _stock_filter != "all" and str(listing.get("instrument_type", "")) != _stock_filter:
			continue
		if not query.is_empty() and not str(listing.get("symbol", "")).to_lower().contains(query) \
				and not str(listing.get("sector", "")).to_lower().contains(query):
			continue
		visible_listings.append(listing)
	visible_listings.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		var av := float(a.get(_stock_sort, 0.0))
		var bv := float(b.get(_stock_sort, 0.0))
		if is_equal_approx(av, bv):
			return str(a.get("symbol", "")) < str(b.get("symbol", ""))
		return av > bv)
	var quote_shell := PanelContainer.new()
	quote_shell.size_flags_vertical = Control.SIZE_EXPAND_FILL
	quote_shell.add_theme_stylebox_override("panel", _sb(Color.WHITE, Color("dfe6ee"), 11, 7))
	var quote_col := VBoxContainer.new()
	quote_col.add_theme_constant_override("separation", 4)
	quote_shell.add_child(quote_col)
	var quote_head := HBoxContainer.new()
	quote_head.add_child(_lbl("SECURITIES · 每日收盘行情", 9, INK, true))
	quote_head.add_child(_spacer_h())
	quote_head.add_child(_lbl("%d / %d · 点击代码切换主图" % [visible_listings.size(), listings.size()], 8, INK3))
	quote_col.add_child(quote_head)
	var columns := HBoxContainer.new()
	columns.add_theme_constant_override("separation", 4)
	columns.add_child(_stock_table_cell("代码", 66, INK3, HORIZONTAL_ALIGNMENT_LEFT))
	columns.add_child(_stock_table_cell("板块", 66, INK3, HORIZONTAL_ALIGNMENT_LEFT, false))
	columns.add_child(_stock_table_cell("最新", 58, INK3))
	columns.add_child(_stock_table_cell("涨跌", 60, INK3))
	columns.add_child(_stock_table_cell("总市值", 67, INK3))
	columns.add_child(_stock_table_cell("Q / PB", 52, INK3))
	columns.add_child(_stock_table_cell("基本面差", 60, INK3))
	quote_col.add_child(columns)
	var quote_scroll := ScrollContainer.new()
	quote_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	quote_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	quote_col.add_child(quote_scroll)
	_restore_scroll("center:stocks:quotes", quote_scroll)
	quote_scroll.get_v_scroll_bar().value_changed.connect(func(v: float) -> void:
		_scroll_mem["center:stocks:quotes"] = int(v))
	var rows := VBoxContainer.new()
	rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rows.add_theme_constant_override("separation", 2)
	quote_scroll.add_child(rows)
	if visible_listings.is_empty():
		rows.add_child(_lbl("没有匹配的上市证券。", 9, INK3))
	for listing: Dictionary in visible_listings:
		var symbol := str(listing.get("symbol", ""))
		var active := symbol == _stock_selected
		var row_panel := PanelContainer.new()
		row_panel.add_theme_stylebox_override("panel", _sb(
			Color("eef5ff") if active else Color("fbfcfe"),
			BLUE_BD if active else Color("edf1f5"), 7, 3, 2 if active else 0))
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 4)
		row_panel.add_child(row)
		var symbol_button := Button.new()
		symbol_button.text = symbol
		symbol_button.custom_minimum_size.x = 66
		symbol_button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		symbol_button.add_theme_font_size_override("font_size", 8)
		symbol_button.add_theme_font_override("font", _mono)
		symbol_button.add_theme_color_override("font_color", Color("285ca8"))
		symbol_button.add_theme_stylebox_override("normal", _sb(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 5, 2))
		var selected_symbol := symbol
		symbol_button.pressed.connect(func() -> void:
			_stock_selected = selected_symbol
			_render())
		row.add_child(symbol_button)
		row.add_child(_stock_table_cell(str(listing.get("sector", "")), 66, INK2,
			HORIZONTAL_ALIGNMENT_LEFT, false))
		row.add_child(_stock_table_cell(_firm_number(listing.get("price")), 58, INK))
		var change := float(listing.get("change", 0.0))
		row.add_child(_stock_table_cell(_stock_delta_text(change), 60,
			_stock_delta_color(change)))
		row.add_child(_stock_table_cell(_firm_number(listing.get("market_cap")), 67, INK))
		var valuation: Variant = listing.get("tobin_q") if listing.get("tobin_q") != null else listing.get("price_to_book")
		row.add_child(_stock_table_cell(_firm_number(valuation, "idx"), 52, PURPLE))
		row.add_child(_stock_table_cell(_firm_number(listing.get("fundamental_gap"), "pct"), 60,
			_stock_delta_color(float(listing.get("fundamental_gap", 0.0))) if listing.get("fundamental_gap") != null else INK3))
		rows.add_child(row_panel)
	body.add_child(quote_shell)


func _render_focus_tab(body: VBoxContainer) -> void:
	var brief := _macro_brief()
	var fp := PanelContainer.new()
	var fv := VBoxContainer.new()
	fv.add_theme_constant_override("separation", 10)
	fp.add_child(fv)
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 8)
	header.add_child(_lbl("MACRO BRIEF", 10, INK3, true))
	header.add_child(_lbl("决策简报", 14, INK))
	header.add_child(_spacer_h())
	header.add_child(_chip("公报覆盖 %d / 8" % int(brief["coverage"]),
		TEAL_DK, TEAL_BG, TEAL_BD, 9))
	if int(brief["risk_count"]) > 0:
		header.add_child(_chip("风险事件 %d" % int(brief["risk_count"]),
		RED, RED_BG, RED_BD, 9))
	fv.add_child(header)
	var content := HBoxContainer.new()
	content.add_theme_constant_override("separation", 10)
	fv.add_child(content)
	var map_shell := PanelContainer.new()
	map_shell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	map_shell.add_theme_stylebox_override("panel", _sb(
		Color("f7f9fc"), Color("e0e7ef"), 11, 10))
	var map_col := VBoxContainer.new()
	map_col.add_theme_constant_override("separation", 4)
	map_shell.add_child(map_col)
	var map_head := HBoxContainer.new()
	map_head.add_child(_lbl("经济相位", 11, INK_BODY))
	map_head.add_child(_lbl("增长动能 × 价格压力", 9, INK3, true))
	map_head.add_child(_spacer_h())
	map_head.add_child(_lbl("基于已发布公报", 9, INK3))
	map_col.add_child(map_head)
	var phase_map := _MacroPhaseMap.new()
	phase_map.custom_minimum_size = Vector2(0, 184)
	phase_map.has_phase = bool(brief["phase_ready"])
	phase_map.x_value = float(brief["x"])
	phase_map.y_value = float(brief["y"])
	phase_map.phase = str(brief["phase"])
	phase_map.point_color = brief["tone"]
	phase_map.font = _sans
	map_col.add_child(phase_map)
	content.add_child(map_shell)
	var judgement := VBoxContainer.new()
	judgement.custom_minimum_size.x = 238
	judgement.add_theme_constant_override("separation", 7)
	content.add_child(judgement)
	judgement.add_child(_lbl("本期判断", 9, INK3, true))
	var phase_label := _lbl(str(brief["phase"]), 19, brief["tone"])
	judgement.add_child(phase_label)
	var summary := _lbl(str(brief["summary"]), 10, INK2)
	summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	judgement.add_child(summary)
	judgement.add_child(_brief_signal("政策张力", str(brief["tension"]),
		brief["tone"]))
	judgement.add_child(_brief_signal("政策传导", str(brief["transmission"]), BLUE))
	judgement.add_child(_brief_signal("数据可信度", str(brief["data_quality"]),
		TEAL_DK if int(brief["coverage"]) >= 6 else AMBER))
	body.add_child(fp)
	var sp := PanelContainer.new()
	sp.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sv := VBoxContainer.new()
	sv.add_theme_constant_override("separation", 9)
	sp.add_child(sv)
	_append_core_dimensions(sv)
	body.add_child(sp)


func _macro_brief() -> Dictionary:
	## 只综合已发布公报与公开政策状态；不读取未发布数据来判断经济相位。
	var releases := _releases_by_id()
	var now := int(_snapshot.get("tick", 0))
	var coverage := 0
	var max_lag := 0
	var latest_release := -1
	for spec: Dictionary in CORE_DIMENSION_SPEC:
		var release: Dictionary = releases.get(str(spec["id"]), {})
		if release.is_empty() or release.get("value") == null:
			continue
		coverage += 1
		latest_release = maxi(latest_release,
			int(release.get("released_at_tick", -1)))
		max_lag = maxi(max_lag, maxi(0,
			now - int(release.get("reference_end_tick", now))))
	var output_hist: Array = _release_hist.get("real_output", [])
	var inflation_release: Dictionary = releases.get("inflation", {})
	var phase_ready := output_hist.size() >= 2 \
		and not inflation_release.is_empty() \
		and inflation_release.get("value") != null
	var x_value := 0.0
	var y_value := 0.0
	if output_hist.size() >= 2:
		var previous := float((output_hist[-2] as Dictionary).get("v", 0.0))
		var current := float((output_hist[-1] as Dictionary).get("v", 0.0))
		if absf(previous) > 1e-9:
			x_value = clampf(((current - previous) / absf(previous)) / 0.05, -1.0, 1.0)
	if not inflation_release.is_empty() and inflation_release.get("value") != null:
		var inflation := float(inflation_release.get("value"))
		var target := float((_snapshot.get("metrics", {}) as Dictionary).get(
			"inflation_target", 0.02))
		if _perm_cache.has("inflation_target"):
			var target_perm: Dictionary = _perm_cache["inflation_target"]
			if target_perm.get("current_value") != null:
				target = float(target_perm.get("current_value"))
		y_value = clampf((inflation - target) / maxf(absf(target), 0.005), -1.0, 1.0)
	var phase := "初始观察期"
	var summary := "正在建立首轮公报基线；原始指标与趋势见下方八维卡片。"
	var tension := "至少需要两期产出公报，才能形成跨指标判断"
	var tone: Color = INK2
	if phase_ready:
		if x_value < -0.18 and y_value > 0.18:
			phase = "滞胀压力"
			summary = "增长动能转弱，同时价格压力高于政策参照。"
			tension = "稳增长与稳物价相互牵制，避免单目标过度反应"
			tone = RED
		elif x_value > 0.18 and y_value > 0.18:
			phase = "需求偏热"
			summary = "增长与价格压力同步走强，顺周期风险正在上升。"
			tension = "关注需求扩张是否继续推高价格压力"
			tone = AMBER
		elif x_value < -0.18 and y_value < -0.18:
			phase = "需求偏弱"
			summary = "增长动能和价格压力同时偏弱，经济处于收缩象限。"
			tension = "稳需求优先级上升，同时保留政策缓冲"
			tone = BLUE
		elif x_value > 0.18 and y_value < -0.18:
			phase = "低压扩张"
			summary = "增长动能为正，同时价格压力低于政策参照。"
			tension = "保护扩张动能，并监测低价格压力是否持续"
			tone = TEAL
		elif x_value > 0.18:
			phase = "温和扩张"
			summary = "增长动能为正，价格压力仍接近政策参照。"
			tension = "维持政策连续性，监测扩张是否向过热迁移"
			tone = TEAL
		elif x_value < -0.18:
			phase = "增长承压"
			summary = "增长动能转弱，但价格压力尚未形成显著约束。"
			tension = "评估需求支持，同时避免过早消耗政策空间"
			tone = BLUE
		elif y_value > 0.18:
			phase = "价格偏高"
			summary = "增长接近中枢，价格压力高于政策参照。"
			tension = "稳价优先级上升，关注紧缩对增长的滞后影响"
			tone = AMBER
		elif y_value < -0.18:
			phase = "价格偏低"
			summary = "增长接近中枢，价格压力低于政策参照。"
			tension = "关注低价格压力是否演变为需求不足"
			tone = BLUE
		else:
			phase = "接近平衡"
			summary = "增长动能与价格压力均未显著偏离中枢。"
			tension = "当前没有单一目标占据绝对优先级"
			tone = GREEN
	var pending_count := (_snapshot.get("pending", []) as Array).size()
	var transmission := "暂无政策等待实施"
	if _awaiting():
		transmission = "%d 个会议窗口等待决策" % _contexts().size()
	elif pending_count > 0:
		transmission = "%d 项已通过政策等待生效" % pending_count
	var data_quality := "尚无核心公报发布"
	if coverage > 0:
		data_quality = "%d/8 已发布 · 最大滞后 %d 天" % [coverage, max_lag]
		if latest_release >= 0:
			data_quality += " · 截止 %s" % _cal_short(latest_release)
	var risk_count := (_snapshot.get("active_shocks", []) as Array).size() \
		+ (_snapshot.get("shock_bulletins", []) as Array).size()
	return {
		"coverage": coverage, "risk_count": risk_count,
		"phase_ready": phase_ready, "x": x_value, "y": y_value,
		"phase": phase, "summary": summary, "tension": tension,
		"transmission": transmission, "data_quality": data_quality,
		"tone": tone,
	}


func _brief_signal(title: String, text: String, color: Color) -> Control:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _sb(
		Color("f7f9fc"), Color("e2e8ef"), 8, 7))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 7)
	panel.add_child(row)
	row.add_child(_dot(color, 6))
	var col := VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 1)
	row.add_child(col)
	col.add_child(_lbl(title, 8, INK3, true))
	var detail := _lbl(text, 9, INK_BODY)
	detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	col.add_child(detail)
	return panel


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
	card.tooltip_text = "查看维度详情\n打开%s" % ("世界视图" if target_tab == "world" \
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
	var source_label := _lbl("%s发布 · 滞后 %d 日" % [_cal_short(released_at), lag],
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
	var valid_groups: Array = []
	for grp: Dictionary in PANEL_GROUPS:
		valid_groups.append(str(grp["name"]))
	if _goto_panel_group.is_empty() or _goto_panel_group not in valid_groups:
		_goto_panel_group = str(PANEL_GROUPS[0]["name"])
	var nav_shell := PanelContainer.new()
	nav_shell.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 11, 6))
	body.add_child(nav_shell)
	var nav := HFlowContainer.new()
	nav.add_theme_constant_override("h_separation", 5)
	nav.add_theme_constant_override("v_separation", 5)
	nav_shell.add_child(nav)
	var active_group: Dictionary = PANEL_GROUPS[0]
	for grp: Dictionary in PANEL_GROUPS:
		var group_name := str(grp["name"])
		var group_color: Color = grp["color"]
		var active := group_name == _goto_panel_group
		if active:
			active_group = grp
		var tab := Button.new()
		tab.text = group_name
		tab.add_theme_font_size_override("font_size", 10)
		tab.add_theme_stylebox_override("normal", _sb(
			Color(group_color.r, group_color.g, group_color.b, 0.10) if active else Color.WHITE,
			Color(group_color.r, group_color.g, group_color.b, 0.72) if active else LINE2,
			9, 6, 3 if active else 0))
		tab.add_theme_color_override("font_color",
			group_color.darkened(0.18) if active else INK2)
		tab.pressed.connect(func() -> void:
			_goto_panel_group = group_name
			_scroll_mem["center:panels"] = 0
			_render())
		nav.add_child(tab)
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
	var group_color: Color = active_group["color"]
	var group_name := str(active_group["name"])
	var header := PanelContainer.new()
	var header_style := _sb(PANEL,
		Color(group_color.r, group_color.g, group_color.b, 0.42), 12, 10, 5)
	header_style.border_width_left = 4
	header.add_theme_stylebox_override("panel", header_style)
	var header_row := HBoxContainer.new()
	header_row.add_theme_constant_override("separation", 8)
	header.add_child(header_row)
	header_row.add_child(_dot(group_color, 8))
	var heading := VBoxContainer.new()
	heading.add_theme_constant_override("separation", 1)
	heading.add_child(_lbl(group_name, 15, INK))
	heading.add_child(_lbl(str(PANEL_DESCRIPTIONS.get(group_name, "")), 10, INK2))
	header_row.add_child(heading)
	header_row.add_child(_spacer_h())
	header_row.add_child(_chip("ECONOMY · 结构与趋势", group_color.darkened(0.18),
		Color(group_color.r, group_color.g, group_color.b, 0.08),
		Color(group_color.r, group_color.g, group_color.b, 0.35), 9))
	col.add_child(header)
	var requirement := str(active_group.get("requires", ""))
	var capabilities: Dictionary = _snapshot.get("capabilities", {})
	if not requirement.is_empty() and not bool(capabilities.get(requirement, false)):
		var disabled := PanelContainer.new()
		disabled.add_theme_stylebox_override("panel", _sb(
			Color("f6f8fa"), Color("d8e0e8"), 11, 16))
		var disabled_text := _lbl(
			"该经济体未启用「%s」能力，因此本页没有可解释的运行指标。" %
			str(CAPABILITY_CN.get(requirement, requirement)), 11, INK2)
		disabled_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		disabled.add_child(disabled_text)
		col.add_child(disabled)
		return
	var series: Array = _snapshot.get("series", [])
	var latest: Dictionary = _snapshot.get("metrics", {})
	var details: Dictionary = _snapshot.get("panel_details", {})
	_render_panel_kpis(col, active_group, latest, series)
	var charts: Array = PANEL_CHARTS.get(group_name, [])
	if charts.size() == 1:
		col.add_child(_panel_chart(charts[0], latest, series, group_color, details))
	elif charts.size() >= 2:
		var chart_row := HBoxContainer.new()
		chart_row.add_theme_constant_override("separation", 10)
		for chart_index in 2:
			var chart_panel := _panel_chart(
				charts[chart_index], latest, series, group_color, details)
			chart_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			chart_row.add_child(chart_panel)
		col.add_child(chart_row)
	for chart_index in range(2, charts.size()):
		col.add_child(_panel_chart(
			charts[chart_index], latest, series, group_color, details))


func _render_panel_kpis(parent: VBoxContainer, group: Dictionary,
		latest: Dictionary, series: Array) -> void:
	var items: Array = group.get("items", [])
	var color: Color = group.get("color", TEAL)
	for row_index in 2:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		for column_index in 3:
			var item_index := row_index * 3 + column_index
			if item_index >= items.size():
				break
			var card := _panel_kpi_card(items[item_index], latest, series, color)
			card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			row.add_child(card)
		parent.add_child(row)


func _panel_kpi_card(item: Array, latest: Dictionary,
		series: Array, color: Color) -> Control:
	var key := str(item[0])
	var label := str(item[1])
	var kind := str(item[2])
	var card := PanelContainer.new()
	card.custom_minimum_size.y = 82
	var rest := _sb(Color("f8fafc"), Color("e0e7ef"), 10, 9)
	var hover := _sb(Color.WHITE, Color(color.r, color.g, color.b, 0.65), 10, 9, 7)
	card.add_theme_stylebox_override("panel", rest)
	card.mouse_entered.connect(func() -> void:
		card.add_theme_stylebox_override("panel", hover))
	card.mouse_exited.connect(func() -> void:
		card.add_theme_stylebox_override("panel", rest))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 3)
	card.add_child(col)
	var title := HBoxContainer.new()
	title.add_theme_constant_override("separation", 5)
	title.add_child(_dot(color, 6))
	title.add_child(_lbl(label, 10, INK2))
	title.add_child(_spacer_h())
	title.add_child(_lbl(key, 8, INK3, true))
	col.add_child(title)
	var value_row := HBoxContainer.new()
	var has_data := not series.is_empty()
	var current := float(latest.get(key, 0.0))
	value_row.add_child(_lbl(_fmt_val(kind, current) if has_data else "—",
		19, color if has_data else Color("a2adb8"), true))
	value_row.add_child(_spacer_h())
	if series.size() >= 2:
		var previous := float((series[-2] as Dictionary).get(key, current))
		value_row.add_child(_lbl(_panel_delta(kind, previous, current), 9, INK3, true))
	col.add_child(value_row)
	var spark := _SparkLine.new()
	spark.color = color
	spark.custom_minimum_size = Vector2(0, 20)
	var values := _panel_values(series, key)
	spark.values = values
	col.add_child(spark)
	if not values.is_empty():
		var low := INF
		var high := -INF
		for raw in values:
			low = minf(low, float(raw))
			high = maxf(high, float(raw))
		card.tooltip_text = "%s · %s\n当前：%s\n窗口区间：%s — %s" % [
			label, key, _fmt_val(kind, current),
			_fmt_val(kind, low), _fmt_val(kind, high)]
	return card


func _panel_delta(kind: String, previous: float, current: float) -> String:
	var delta := current - previous
	if absf(delta) <= 1e-12:
		return "— 持平"
	var arrow := "▲" if delta > 0.0 else "▼"
	if kind in ["pct", "pt"]:
		return "%s %.2fpp" % [arrow, absf(delta) * 100.0]
	if kind == "per_thousand":
		return "%s %.2f‰" % [arrow, absf(delta)]
	if absf(previous) > 1e-9:
		return "%s %.1f%%" % [arrow, absf(delta / previous) * 100.0]
	return "%s %s" % [arrow, _fmt_val(kind, absf(delta))]


func _panel_values(series: Array, key: String) -> Array:
	var values: Array = []
	for point: Dictionary in series:
		values.append(float(point.get(key, 0.0)))
	return values


func _panel_chart(spec: Dictionary, latest: Dictionary,
		series: Array, fallback_color: Color, details: Dictionary = {}) -> Control:
	var chart_type := str(spec.get("type", "line"))
	var panel := PanelContainer.new()
	panel.custom_minimum_size.y = 218 if chart_type in [
		"age_participation", "pyramid", "sector_matrix", "deciles"] else 198
	panel.add_theme_stylebox_override("panel", _sb(
		Color("fbfcfd"), Color("dde5ed"), 11, 10, 4))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 5)
	panel.add_child(col)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 7)
	head.add_child(_lbl(str(spec.get("title", "CHART")), 9, INK3, true))
	head.add_child(_spacer_h())
	head.add_child(_lbl(str(spec.get("note", "")), 8, INK3))
	col.add_child(head)
	var data: Array = []
	for item: Array in spec.get("items", []):
		var key := str(item[0])
		var kind := str(item[2])
		var color: Color = item[3] if item.size() > 3 else fallback_color
		data.append({
			"key": key, "label": str(item[1]), "kind": kind, "color": color,
			"values": _panel_values(series, key),
			"value": float(latest.get(key, 0.0)),
			"text": _fmt_val(kind, float(latest.get(key, 0.0))),
		})
	var chart_height := 166.0 if panel.custom_minimum_size.y > 200.0 else 145.0
	if chart_type == "employment_sectors":
		var sectors := _PanelCompositionChart.new()
		sectors.data = (details.get("labor", {}) as Dictionary).get("employment_sectors", [])
		sectors.font = _sans
		sectors.colors = [TEAL, BLUE, GREEN, PURPLE, AMBER, Color("64748b")]
		sectors.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(sectors)
	elif chart_type == "labor_flows":
		var labor := _PanelLaborFlowChart.new()
		var labor_details: Dictionary = details.get("labor", {})
		labor.states = labor_details.get("states", [])
		labor.flows = labor_details.get("flows", [])
		labor.font = _sans
		labor.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(labor)
	elif chart_type == "age_participation":
		var age_chart := _PanelAgeParticipationChart.new()
		age_chart.data = (details.get("labor", {}) as Dictionary).get("participation_by_age", [])
		age_chart.font = _sans
		age_chart.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(age_chart)
	elif chart_type == "pyramid":
		var pyramid := _PanelPyramidChart.new()
		pyramid.data = (details.get("population", {}) as Dictionary).get("pyramid", [])
		pyramid.font = _sans
		pyramid.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(pyramid)
	elif chart_type == "sector_matrix":
		var sector_chart := _PanelSectorMatrixChart.new()
		sector_chart.data = (details.get("real_economy", {}) as Dictionary).get("sectors", [])
		sector_chart.font = _sans
		sector_chart.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(sector_chart)
	elif chart_type == "lorenz":
		var lorenz := _PanelLorenzChart.new()
		var dist: Dictionary = details.get("distribution", {})
		lorenz.income = (dist.get("income", {}) as Dictionary).get("lorenz", [])
		lorenz.wealth = (dist.get("wealth", {}) as Dictionary).get("lorenz", [])
		lorenz.font = _sans
		lorenz.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(lorenz)
	elif chart_type == "deciles":
		var deciles := _PanelDecileChart.new()
		var dist: Dictionary = details.get("distribution", {})
		deciles.income = (dist.get("income", {}) as Dictionary).get("deciles", [])
		deciles.consumption = (dist.get("consumption", {}) as Dictionary).get("deciles", [])
		deciles.font = _sans
		deciles.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(deciles)
	elif chart_type == "firm_bubbles":
		var bubbles := _PanelBubbleChart.new()
		bubbles.data = (details.get("capital_market", {}) as Dictionary).get("firms", [])
		bubbles.font = _sans
		bubbles.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(bubbles)
	elif chart_type == "energy_flow":
		var energy_flow := _PanelEnergyFlowChart.new()
		energy_flow.values = latest
		energy_flow.font = _sans
		energy_flow.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(energy_flow)
	elif chart_type == "fiscal_flow":
		var fiscal_flow := _PanelFiscalFlowChart.new()
		fiscal_flow.values = latest
		fiscal_flow.font = _sans
		fiscal_flow.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(fiscal_flow)
	elif chart_type == "bank_balance":
		var bank_balance := _PanelBankBalanceChart.new()
		bank_balance.values = latest
		bank_balance.font = _sans
		bank_balance.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(bank_balance)
	elif chart_type == "bars":
		var bars := _PanelBarChart.new()
		bars.data = data
		bars.font = _sans
		bars.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(bars)
	elif chart_type == "columns":
		var columns := _PanelColumnChart.new()
		columns.data = data
		columns.font = _sans
		columns.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(columns)
	else:
		var line := _PanelLineChart.new()
		line.data = data
		line.indexed = bool(spec.get("indexed", false))
		line.font = _sans
		line.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(line)
	return panel


func _score_target(value: float, target: float, tolerance: float) -> float:
	return clampf(100.0 * exp(-absf(value - target) / maxf(tolerance, 0.000001)),
		0.0, 100.0)


func _score_low(value: float, failure_level: float) -> float:
	return 100.0 * (1.0 - clampf(maxf(value, 0.0) / maxf(failure_level, 0.000001),
		0.0, 1.0))


func _score_growth(current: float, baseline: float, scale: float) -> float:
	if absf(baseline) <= 1e-9:
		return 50.0
	var growth := (current - baseline) / absf(baseline)
	return clampf(100.0 / (1.0 + exp(-2.0 * growth / maxf(scale, 0.000001))),
		0.0, 100.0)


func _world_economy_at(history: Array, history_index: int,
		country_index: int) -> Dictionary:
	if history.is_empty():
		return {}
	var point: Dictionary = history[clampi(history_index, 0, history.size() - 1)]
	var economies: Array = point.get("economies", [])
	return economies[country_index] if country_index >= 0 and country_index < economies.size() else {}


func _world_value_at(point: Dictionary, key: String, country_index: int) -> float:
	var values: Variant = point.get(key, [])
	if values is Array and country_index >= 0 and country_index < (values as Array).size():
		return float((values as Array)[country_index])
	if values is Dictionary:
		return float((values as Dictionary).get(str(country_index),
			(values as Dictionary).get(country_index, 0.0)))
	return 0.0


func _country_scorecard(world: Dictionary, country_index: int,
		history_index := -1) -> Dictionary:
	## 固定“均衡发展”合同：结果变量、目标偏离与自身趋势；政策工具不计分。
	var history: Array = world.get("history", [])
	if history.is_empty():
		return {"overall": 0.0, "grade": "数据不足", "dimensions": []}
	var index := history.size() - 1 if history_index < 0 else clampi(
		history_index, 0, history.size() - 1)
	var point: Dictionary = history[index]
	var economy := _world_economy_at(history, index, country_index)
	if economy.is_empty():
		return {"overall": 0.0, "grade": "数据不足", "dimensions": []}
	var baseline_index := maxi(0, index - 30)
	var baseline := _world_economy_at(history, baseline_index, country_index)
	var output := float(economy.get("real_output", 0.0))
	var output_base := float(baseline.get("real_output", output))
	var wage := float(economy.get("real_wage", economy.get("avg_wage", 0.0)))
	var wage_base := float(baseline.get("real_wage", baseline.get("avg_wage", wage)))
	var output_growth := (output - output_base) / absf(output_base) \
		if absf(output_base) > 1e-9 else 0.0
	var wage_growth := (wage - wage_base) / absf(wage_base) \
		if absf(wage_base) > 1e-9 else 0.0
	var realization := float(economy.get("production_realization_rate", 0.0))
	var prosperity := 0.45 * _score_growth(output, output_base, 0.12) \
		+ 0.30 * _score_growth(wage, wage_base, 0.08) \
		+ 0.25 * _score_target(realization, 1.0, 0.35)
	var unemployment := float(economy.get("unemployment_rate", 0.0))
	var underemployment := float(economy.get("underemployed_share", 0.0))
	var employment := 0.65 * _score_low(unemployment, 0.20) \
		+ 0.35 * _score_low(underemployment, 0.25)
	var inflation_target := float(economy.get("inflation_target", 0.02))
	var price_sum := 0.0
	var price_count := 0
	for price_index in range(maxi(0, index - 29), index + 1):
		var price_economy := _world_economy_at(history, price_index, country_index)
		if price_economy.is_empty():
			continue
		price_sum += _score_target(float(price_economy.get("inflation", 0.0)),
			inflation_target, maxf(absf(inflation_target), 0.01))
		price_count += 1
	var price_stability := price_sum / float(maxi(price_count, 1))
	var debt_ratio := maxf(0.0, float(economy.get("gov_debt_to_gdp", 0.0)))
	var deficit_ratio := float(economy.get("gov_deficit_to_gdp", 0.0))
	var fiscal := 0.55 * _score_low(debt_ratio, 2.0) \
		+ 0.45 * _score_target(deficit_ratio, 0.0, 0.08)
	var credit := absf(float(economy.get("total_credit", 0.0)))
	var capital := float(economy.get("bank_capital", 0.0))
	var capital_score := 70.0 if credit <= 1e-9 else clampf(
		maxf(capital, 0.0) / credit / 0.12 * 100.0, 0.0, 100.0)
	var debt_service := float(economy.get("total_debt_service_ratio", 0.0))
	var writeoff_ratio := absf(float(economy.get("writeoffs", 0.0))) / maxf(credit, 1.0)
	var financial := 0.45 * capital_score \
		+ 0.35 * _score_low(debt_service, 0.50) \
		+ 0.20 * _score_low(writeoff_ratio, 0.05)
	var poverty := float(economy.get("poverty_rate", 0.0))
	var income_gini := clampf(float(economy.get("income_gini", 0.0)), 0.0, 1.0)
	var wealth_gini := clampf(float(economy.get("hh_wealth_gini", 0.0)), 0.0, 1.0)
	var welfare := 0.40 * _score_low(poverty, 0.40) \
		+ 0.25 * (100.0 * (1.0 - income_gini)) \
		+ 0.20 * (100.0 * (1.0 - wealth_gini)) \
		+ 0.15 * _score_growth(float(economy.get("welfare_log", 0.0)),
			float(baseline.get("welfare_log", economy.get("welfare_log", 0.0))), 0.08)
	var current_account := _world_value_at(point, "current_account", country_index)
	var nfa := _world_value_at(point, "nfa", country_index)
	var ca_ratio := current_account / maxf(absf(output), 1.0)
	var nfa_ratio := nfa / maxf(absf(output), 1.0)
	var external := 0.65 * _score_target(ca_ratio, 0.0, 0.12) \
		+ 0.35 * clampf(100.0 / (1.0 + exp(-2.0 * nfa_ratio / 0.25)), 0.0, 100.0)
	var energy_used := float(economy.get("energy_used", 0.0))
	var energy_produced := float(economy.get("energy_produced", 0.0))
	var energy_stock := float(economy.get("energy_stock_total", 0.0)) \
		+ float(economy.get("spr_stock", 0.0))
	var supply_score := 70.0 if energy_used <= 1e-9 else clampf(
		energy_produced / energy_used * 100.0, 0.0, 100.0)
	var stock_score := 70.0 if energy_used <= 1e-9 else clampf(
		energy_stock / energy_used / 30.0 * 100.0, 0.0, 100.0)
	var resilience := 0.50 * external + 0.25 * supply_score + 0.25 * stock_score
	var dimensions: Array = [
		{"label": "繁荣增长", "score": prosperity,
			"detail": "近 30 日产出 %+.1f%% · 实际工资 %+.1f%%" % [output_growth * 100.0, wage_growth * 100.0]},
		{"label": "充分就业", "score": employment,
			"detail": "失业 %.1f%% · 不充分就业 %.1f%%" % [unemployment * 100.0, underemployment * 100.0]},
		{"label": "价格稳定", "score": price_stability,
			"detail": "日通胀 %.2f%% · 目标 %.2f%%" % [float(economy.get("inflation", 0.0)) * 100.0, inflation_target * 100.0]},
		{"label": "财政韧性", "score": fiscal,
			"detail": "债务/GDP %.1f%% · 赤字/GDP %.1f%%" % [float(economy.get("gov_debt_to_gdp", 0.0)) * 100.0, deficit_ratio * 100.0]},
		{"label": "金融稳定", "score": financial,
			"detail": "资本/信贷 %.1f%% · 偿债 %.1f%%" % [maxf(capital, 0.0) / maxf(credit, 1.0) * 100.0, debt_service * 100.0]},
		{"label": "民生分配", "score": welfare,
			"detail": "贫困 %.1f%% · 收入 Gini %.3f" % [poverty * 100.0, income_gini]},
		{"label": "外部能源", "score": resilience,
			"detail": "经常账户/产出 %+.1f%% · 能源覆盖 %.1f×" % [ca_ratio * 100.0, energy_produced / maxf(energy_used, 0.000001)]},
	]
	var weights := [0.18, 0.14, 0.14, 0.14, 0.14, 0.14, 0.12]
	var overall := 0.0
	for dimension_index in dimensions.size():
		(dimensions[dimension_index] as Dictionary)["score"] = clampf(
			float((dimensions[dimension_index] as Dictionary)["score"]), 0.0, 100.0)
		overall += float((dimensions[dimension_index] as Dictionary)["score"]) \
			* float(weights[dimension_index])
	var grade := "危机"
	if overall >= 80.0:
		grade = "卓越"
	elif overall >= 65.0:
		grade = "稳健"
	elif overall >= 50.0:
		grade = "承压"
	elif overall >= 35.0:
		grade = "脆弱"
	return {"overall": overall, "grade": grade, "dimensions": dimensions}


func _score_bar(dimension: Dictionary, color: Color) -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 7)
	var label := _lbl(str(dimension.get("label", "")), 9, INK2)
	label.custom_minimum_size.x = 62
	row.add_child(label)
	var bar := Control.new()
	bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.custom_minimum_size = Vector2(0, 12)
	var fraction := clampf(float(dimension.get("score", 0.0)) / 100.0, 0.0, 1.0)
	bar.draw.connect(func() -> void:
		bar.draw_rect(Rect2(Vector2(0, 3), Vector2(bar.size.x, 6)), Color("e8edf3"))
		bar.draw_rect(Rect2(Vector2(0, 3), Vector2(bar.size.x * fraction, 6)), color)
		bar.draw_circle(Vector2(bar.size.x * fraction, 6), 3.5, color))
	row.add_child(bar)
	var score := _lbl("%d" % roundi(float(dimension.get("score", 0.0))), 10, color, true)
	score.custom_minimum_size.x = 24
	score.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(score)
	row.tooltip_text = "%s\n%s" % [str(dimension.get("label", "")),
		str(dimension.get("detail", ""))]
	return row


func _country_scorecard_panel(world: Dictionary) -> Control:
	var history: Array = world.get("history", [])
	var latest: Dictionary = world.get("latest", {})
	var economies: Array = latest.get("economies", [])
	_score_country = clampi(_score_country, 0, maxi(0, economies.size() - 1))
	var scorecard := _country_scorecard(world, _score_country)
	var dimensions: Array = scorecard.get("dimensions", [])
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _sb(PANEL, LINE, 13, 11, 7))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 8)
	panel.add_child(col)
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 8)
	header.add_child(_lbl("NATIONAL SCORECARD · 国家表现", 10, INK3, true))
	header.add_child(_lbl(_country_name(_score_country), 13, INK))
	header.add_child(_spacer_h())
	header.add_child(_chip("均衡发展 · 固定权重", INK2, PANEL3, LINE2, 9))
	col.add_child(header)
	var content := HBoxContainer.new()
	content.add_theme_constant_override("separation", 10)
	col.add_child(content)
	var radar_shell := PanelContainer.new()
	radar_shell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	radar_shell.add_theme_stylebox_override("panel", _sb(Color("f8fafc"), LINE, 10, 7))
	var radar := _CountryRadar.new()
	radar.custom_minimum_size = Vector2(300, 245)
	radar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	radar.font = _sans
	radar.color = ECON_COLORS[_score_country % 3]
	for dimension: Dictionary in dimensions:
		radar.labels.append(str(dimension.get("label", "")))
		radar.scores.append(float(dimension.get("score", 0.0)))
	if not economies.is_empty() and not dimensions.is_empty():
		for dimension_index in dimensions.size():
			var total := 0.0
			var count := 0
			for country_index in economies.size():
				var peer := _country_scorecard(world, country_index)
				var peer_dimensions: Array = peer.get("dimensions", [])
				if dimension_index < peer_dimensions.size():
					total += float((peer_dimensions[dimension_index] as Dictionary).get("score", 0.0))
					count += 1
			radar.comparison.append(total / float(maxi(count, 1)))
	radar_shell.add_child(radar)
	content.add_child(radar_shell)
	var side := VBoxContainer.new()
	side.custom_minimum_size.x = 245
	side.add_theme_constant_override("separation", 6)
	content.add_child(side)
	var total_row := HBoxContainer.new()
	total_row.add_child(_lbl("综合表现", 10, INK3, true))
	total_row.add_child(_spacer_h())
	var overall := float(scorecard.get("overall", 0.0))
	var score_color: Color = GREEN if overall >= 65.0 else (AMBER if overall >= 45.0 else RED)
	total_row.add_child(_lbl("%d" % roundi(overall), 27, score_color, true))
	total_row.add_child(_lbl("/100", 10, INK3, true))
	side.add_child(total_row)
	var prior_index := maxi(0, history.size() - 31)
	var prior := _country_scorecard(world, _score_country, prior_index)
	var change := overall - float(prior.get("overall", overall))
	var grade_row := HBoxContainer.new()
	grade_row.add_child(_chip(str(scorecard.get("grade", "数据不足")), score_color,
		Color(score_color.r, score_color.g, score_color.b, 0.09),
		Color(score_color.r, score_color.g, score_color.b, 0.35), 9))
	grade_row.add_child(_spacer_h())
	grade_row.add_child(_lbl("近 30 日 %+.1f" % change, 9,
		GREEN if change > 0.0 else (RED if change < 0.0 else INK3), true))
	side.add_child(grade_row)
	for dimension: Dictionary in dimensions:
		side.add_child(_score_bar(dimension, ECON_COLORS[_score_country % 3]))
	if not dimensions.is_empty():
		var ordered := dimensions.duplicate(true)
		ordered.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
			return float(a.get("score", 0.0)) > float(b.get("score", 0.0)))
		var insight := PanelContainer.new()
		insight.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 8, 6))
		var insight_label := _lbl("强项 · %s    短板 · %s" % [
			str((ordered[0] as Dictionary).get("label", "")),
			str((ordered[-1] as Dictionary).get("label", ""))], 9, INK2)
		insight.add_child(insight_label)
		side.add_child(insight)
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 10)
	footer.add_child(_lbl("实线 · 当前国家", 9, ECON_COLORS[_score_country % 3]))
	footer.add_child(_lbl("虚线 · 三国均值", 9, INK3))
	footer.add_child(_spacer_h())
	footer.add_child(_lbl("结果变量评分 · 政策工具不计分 · 目标偏离双向扣分",
		9, INK3))
	col.add_child(footer)
	return panel


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
	_score_country = clampi(_score_country, 0, maxi(0, econs.size() - 1))
	for i in econs.size():
		var e: Dictionary = econs[i]
		var card := PanelContainer.new()
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var mine := i == int(world.get("player_economy", 0))
		var selected := i == _score_country
		var wrest := _sb(
			Color(ECON_COLORS[i % 3].r, ECON_COLORS[i % 3].g,
				ECON_COLORS[i % 3].b, 0.10) if selected else (Color("eef7f5") if mine else PANEL),
			ECON_COLORS[i % 3] if selected else (TEAL_BD if mine else LINE),
			12, 11, 8 if selected else 6)
		var whover := _sb(Color("eef7f5") if mine else Color.WHITE,
			ECON_COLORS[i % 3], 12, 11, 13)
		card.add_theme_stylebox_override("panel", wrest)
		card.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		card.tooltip_text = "选择%s，查看七维国家表现评分" % _country_name(i)
		card.mouse_entered.connect(func() -> void:
			card.add_theme_stylebox_override("panel", whover))
		card.mouse_exited.connect(func() -> void:
			card.add_theme_stylebox_override("panel", wrest))
		var country_id := i
		card.gui_input.connect(func(event: InputEvent) -> void:
			if event is InputEventMouseButton \
					and (event as InputEventMouseButton).pressed \
					and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
				_score_country = country_id
				_render())
		var cv := VBoxContainer.new()
		cv.add_theme_constant_override("separation", 4)
		card.add_child(cv)
		var hr := HBoxContainer.new()
		hr.add_theme_constant_override("separation", 7)
		hr.add_child(_flag(i))
		hr.add_child(_lbl(_country_name(i), 13, INK))
		if mine:
			hr.add_child(_chip("我", TEAL, Color(0, 0, 0, 0), TEAL_BD, 9))
		hr.add_child(_spacer_h())
		var country_score := _country_scorecard(world, i)
		var overall := float(country_score.get("overall", 0.0))
		hr.add_child(_chip("%d" % roundi(overall), ECON_COLORS[i % 3],
			Color(ECON_COLORS[i % 3].r, ECON_COLORS[i % 3].g,
				ECON_COLORS[i % 3].b, 0.07),
			Color(ECON_COLORS[i % 3].r, ECON_COLORS[i % 3].g,
				ECON_COLORS[i % 3].b, 0.30), 9))
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
	col.add_child(_country_scorecard_panel(world))
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
		var rank_value := float(_country_scorecard(world, i).get("overall", 0.0)) \
			if _rank_by == "score" else float((econs[i] as Dictionary).get(_rank_by, 0.0))
		order.append([i, rank_value])
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
		var rank_text := "%d" % roundi(float(row[1])) if rank_kind == "score" \
			else _fmt_val(rank_kind, float(row[1]))
		rr.add_child(_lbl(rank_text, 12, ECON_COLORS[i % 3], true))
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
	_bar_block(bars, "经常账户（近 30 日累计）", _ca_sum(whist), "%.1f", true)
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
		br.add_child(_lbl(_cal_value((bulletin as Dictionary).get("start_tick", "?")),
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
	var last_time_label := ""
	for ev: Dictionary in visible_events.slice(0, 36):
		var tick_var: Variant = ev.get("boundary_tick", ev.get("tick", "?"))
		var group_time := _cal_value(tick_var)
		if group_time != last_time_label:
			last_time_label = group_time
			var sep := HBoxContainer.new()
			sep.add_theme_constant_override("separation", 7)
			var sline := ColorRect.new()
			sline.color = Color("e6ebf1")
			sline.custom_minimum_size = Vector2(10, 1)
			sline.size_flags_vertical = Control.SIZE_SHRINK_CENTER
			sep.add_child(sline)
			sep.add_child(_lbl(group_time, 9, Color("9aa7b4"), true))
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
		title.tooltip_text = "事件协议标识\n" + etype
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
class _StockMarketChart extends Control:
	## 模型只提供每日成交价，因此这里绘制真实收盘序列，不合成 OHLC/K 线。
	var values: Array = []
	var line_color := Color("0f9d90")
	var font: Font

	func _draw() -> void:
		var plot := Rect2(Vector2(7, 8), size - Vector2(64, 22))
		if plot.size.x <= 0.0 or plot.size.y <= 0.0:
			return
		for grid_index in 4:
			var grid_y := plot.position.y + plot.size.y * float(grid_index) / 3.0
			draw_line(Vector2(plot.position.x, grid_y), Vector2(plot.end.x, grid_y),
				Color("e5ebf1"), 1.0)
		if values.is_empty():
			draw_string(font, Vector2(plot.position.x, plot.get_center().y + 4.0),
				"等待首个收盘行情", HORIZONTAL_ALIGNMENT_CENTER, plot.size.x, 9,
				Color("8794a2"))
			return
		var low := float(values[0])
		var high := low
		for raw_value: Variant in values:
			low = minf(low, float(raw_value))
			high = maxf(high, float(raw_value))
		var raw_span := high - low
		var padding := maxf(raw_span * 0.12, maxf(absf(high), 1.0) * 0.0015)
		low -= padding
		high += padding
		var span := maxf(high - low, 0.000001)
		var points := PackedVector2Array()
		for index in values.size():
			var x_fraction := float(index) / float(maxi(values.size() - 1, 1))
			var y_fraction := (float(values[index]) - low) / span
			points.append(Vector2(
				plot.position.x + plot.size.x * x_fraction,
				plot.end.y - plot.size.y * y_fraction))
		if points.size() == 1:
			points.append(Vector2(plot.end.x, points[0].y))
		var area := PackedVector2Array(points)
		area.append(Vector2(plot.end.x, plot.end.y))
		area.append(Vector2(plot.position.x, plot.end.y))
		draw_colored_polygon(area, Color(line_color.r, line_color.g, line_color.b, 0.10))
		draw_polyline(points, line_color, 2.0, true)
		draw_circle(points[-1], 4.2, Color.WHITE)
		draw_circle(points[-1], 2.8, line_color)
		draw_string(font, Vector2(plot.end.x + 7.0, plot.position.y + 5.0),
			"%.3f" % high, HORIZONTAL_ALIGNMENT_LEFT, 50.0, 8, Color("8794a2"))
		draw_string(font, Vector2(plot.end.x + 7.0, plot.end.y + 3.0),
			"%.3f" % low, HORIZONTAL_ALIGNMENT_LEFT, 50.0, 8, Color("8794a2"))
		draw_string(font, Vector2(plot.position.x, size.y - 2.0),
			"%d 个每日收盘点" % values.size(), HORIZONTAL_ALIGNMENT_LEFT,
			plot.size.x, 8, Color("8794a2"))


class _StockBreadthChart extends Control:
	var advances := 0
	var unchanged := 0
	var declines := 0
	var font: Font

	func _draw() -> void:
		var total := advances + unchanged + declines
		if total <= 0:
			draw_string(font, Vector2(0, 19), "等待行情",
				HORIZONTAL_ALIGNMENT_CENTER, size.x, 9, Color("8794a2"))
			return
		var bar := Rect2(Vector2(0, 4), Vector2(size.x, 11))
		var cursor := bar.position.x
		var specs := [
			[advances, Color("20a566")],
			[unchanged, Color("aeb9c5")],
			[declines, Color("d64b38")],
		]
		for spec: Array in specs:
			var segment_width := bar.size.x * float(spec[0]) / float(total)
			if segment_width > 0.0:
				draw_rect(Rect2(Vector2(cursor, bar.position.y),
					Vector2(segment_width, bar.size.y)), spec[1])
			cursor += segment_width
		draw_string(font, Vector2(0, 31), "上涨", HORIZONTAL_ALIGNMENT_LEFT,
			50, 8, Color("20a566"))
		draw_string(font, Vector2(0, 31), "平盘", HORIZONTAL_ALIGNMENT_CENTER,
			size.x, 8, Color("7c8997"))
		draw_string(font, Vector2(size.x - 50, 31), "下跌", HORIZONTAL_ALIGNMENT_RIGHT,
			50, 8, Color("d64b38"))


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


class _HouseholdAssetBar extends Control:
	var values: Dictionary = {}
	var font: Font
	var parts := [
		["cash", "现金", Color("16a394")],
		["firm_equity", "企业股权", Color("3274d9")],
		["bank_equity", "银行股权", Color("7950c7")],
		["bonds", "债券", Color("c78318")],
		["housing", "住房", Color("7a8b9b")],
	]

	func _draw() -> void:
		var total := 0.0
		for part: Array in parts:
			total += maxf(0.0, float(values.get(str(part[0]), 0.0)))
		var bar := Rect2(2, 3, size.x - 4, 13)
		draw_rect(bar, Color("e9eef4"))
		if total <= 1e-9:
			draw_string(font, Vector2(0, 38), "暂无正资产",
				HORIZONTAL_ALIGNMENT_CENTER, size.x, 8, Color("849098"))
			return
		var cursor := bar.position.x
		for part: Array in parts:
			var value := maxf(0.0, float(values.get(str(part[0]), 0.0)))
			var width := bar.size.x * value / total
			draw_rect(Rect2(cursor, bar.position.y, width, bar.size.y), part[2])
			cursor += width
		var cell_width := size.x / float(parts.size())
		for index in parts.size():
			var part: Array = parts[index]
			var value := maxf(0.0, float(values.get(str(part[0]), 0.0)))
			var x := index * cell_width
			draw_rect(Rect2(x + 2, 27, 6, 6), part[2])
			draw_string(font, Vector2(x + 11, 34), "%s %.0f%%" % [
				str(part[1]), value / total * 100.0],
				HORIZONTAL_ALIGNMENT_LEFT, cell_width - 10, 7, Color("5e6f81"))


class _PanelCompositionChart extends Control:
	var data: Array = []
	var colors: Array = []
	var font: Font

	func _draw() -> void:
		var total := 0.0
		for item: Dictionary in data:
			total += maxf(0.0, float(item.get("value", 0.0)))
		if total <= 1e-9:
			draw_string(font, Vector2(0, size.y * 0.52), "尚无就业记录",
				HORIZONTAL_ALIGNMENT_CENTER, size.x, 10, Color("849098"))
			return
		var bar := Rect2(2, 12, size.x - 4, 24)
		draw_rect(bar, Color("edf1f6"))
		var cursor := bar.position.x
		for index in data.size():
			var item: Dictionary = data[index]
			var share := maxf(0.0, float(item.get("value", 0.0))) / total
			var width := bar.size.x * share
			var color: Color = colors[index % colors.size()] if not colors.is_empty() else Color.GRAY
			draw_rect(Rect2(cursor, bar.position.y, width, bar.size.y), color)
			cursor += width
		for index in data.size():
			var item: Dictionary = data[index]
			var column := index % 2
			var row := index / 2
			var cell_width := size.x / 2.0
			var x := column * cell_width + 3.0
			var y := 58.0 + row * 23.0
			var color: Color = colors[index % colors.size()] if not colors.is_empty() else Color.GRAY
			draw_rect(Rect2(x, y - 8, 8, 8), color)
			draw_string(font, Vector2(x + 14, y), str(item.get("label", "")),
				HORIZONTAL_ALIGNMENT_LEFT, cell_width - 66, 9, Color("506172"))
			var share := maxf(0.0, float(item.get("value", 0.0))) / total
			draw_string(font, Vector2(x, y), "%.1f%%" % (share * 100.0),
				HORIZONTAL_ALIGNMENT_RIGHT, cell_width - 8, 9, color)


class _PanelLaborFlowChart extends Control:
	var states: Array = []
	var flows: Array = []
	var font: Font
	var colors := [Color("21a179"), Color("c78216"), Color("64748b")]

	func _draw() -> void:
		var state_total := 0.0
		for state: Dictionary in states:
			state_total += maxf(0.0, float(state.get("value", 0.0)))
		var bar := Rect2(2, 8, size.x - 4, 18)
		draw_rect(bar, Color("edf1f6"))
		var cursor := bar.position.x
		for index in states.size():
			var state: Dictionary = states[index]
			var share := maxf(0.0, float(state.get("value", 0.0))) / maxf(1.0, state_total)
			var width := bar.size.x * share
			draw_rect(Rect2(cursor, bar.position.y, width, bar.size.y), colors[index % colors.size()])
			cursor += width
		for index in states.size():
			var state: Dictionary = states[index]
			var x := 2.0 + index * size.x / maxf(1.0, states.size())
			var share := maxf(0.0, float(state.get("value", 0.0))) / maxf(1.0, state_total)
			draw_string(font, Vector2(x, 43), "%s %.0f%%" % [
				str(state.get("label", "")), share * 100.0],
				HORIZONTAL_ALIGNMENT_LEFT, size.x / maxf(1.0, states.size()) - 3, 8,
				colors[index % colors.size()])
		var max_flow := 1.0
		for item: Dictionary in flows:
			max_flow = maxf(max_flow, float(item.get("value", 0.0)))
		for index in flows.size():
			var item: Dictionary = flows[index]
			var column := index % 2
			var row := index / 2
			var cell_width := size.x / 2.0 - 7.0
			var x := 2.0 + column * (size.x / 2.0 + 3.0)
			var y := 59.0 + row * 26.0
			var value := float(item.get("value", 0.0))
			draw_string(font, Vector2(x, y + 9), str(item.get("label", "")),
				HORIZONTAL_ALIGNMENT_LEFT, 68, 8, Color("5e6f81"))
			draw_rect(Rect2(x + 70, y + 2, maxf(8.0, cell_width - 96.0), 7), Color("edf1f6"))
			draw_rect(Rect2(x + 70, y + 2,
				maxf(8.0, cell_width - 96.0) * value / max_flow, 7), Color("2f72d6"))
			draw_string(font, Vector2(x, y + 9), "%.0f" % value,
				HORIZONTAL_ALIGNMENT_RIGHT, cell_width, 8, Color("2a3948"))


class _PanelAgeParticipationChart extends Control:
	var data: Array = []
	var font: Font

	func _draw() -> void:
		if data.is_empty():
			return
		var plot := Rect2(Vector2(28, 22), size - Vector2(38, 48))
		for grid in 3:
			var y := plot.end.y - plot.size.y * float(grid) / 2.0
			draw_line(Vector2(plot.position.x, y), Vector2(plot.end.x, y), Color("e5ebf1"))
			draw_string(font, Vector2(0, y + 3), "%d%%" % (grid * 50),
				HORIZONTAL_ALIGNMENT_RIGHT, 24, 7, Color("849098"))
		var slot := plot.size.x / float(data.size())
		for index in data.size():
			var item: Dictionary = data[index]
			var participation := clampf(float(item.get("participation_rate", 0.0)), 0.0, 1.0)
			var employment := clampf(float(item.get("employment_rate", 0.0)), 0.0, 1.0)
			var bar_width := minf(24.0, slot * 0.24)
			var center := plot.position.x + slot * (index + 0.5)
			var p_height := plot.size.y * participation
			var e_height := plot.size.y * employment
			draw_rect(Rect2(center - bar_width - 2, plot.end.y - p_height, bar_width, p_height), Color("16a394"))
			draw_rect(Rect2(center + 2, plot.end.y - e_height, bar_width, e_height), Color("3274d9"))
			draw_string(font, Vector2(center - slot / 2.0, plot.end.y + 15), str(item.get("label", "")),
				HORIZONTAL_ALIGNMENT_CENTER, slot, 8, Color("5e6f81"))
			draw_string(font, Vector2(center - slot / 2.0, plot.end.y - p_height - 4),
				"%.0f%%" % (participation * 100.0), HORIZONTAL_ALIGNMENT_CENTER, slot, 7, Color("087f74"))
		draw_rect(Rect2(plot.position.x, 4, 8, 8), Color("16a394"))
		draw_string(font, Vector2(plot.position.x + 12, 12), "劳动参与率",
			HORIZONTAL_ALIGNMENT_LEFT, 70, 8, Color("5e6f81"))
		draw_rect(Rect2(plot.position.x + 82, 4, 8, 8), Color("3274d9"))
		draw_string(font, Vector2(plot.position.x + 94, 12), "就业率",
			HORIZONTAL_ALIGNMENT_LEFT, 60, 8, Color("5e6f81"))


class _PanelPyramidChart extends Control:
	var data: Array = []
	var font: Font

	func _draw() -> void:
		if data.is_empty():
			return
		var max_count := 1.0
		for item: Dictionary in data:
			max_count = maxf(max_count, maxf(
				float(item.get("male", 0.0)), float(item.get("female", 0.0))))
		var center := size.x / 2.0
		var label_width := 40.0
		var half_width := maxf(20.0, center - label_width / 2.0 - 18.0)
		var row_height := (size.y - 25.0) / float(data.size())
		for row in data.size():
			var item: Dictionary = data[data.size() - 1 - row]
			var y := 10.0 + row * row_height
			var male := float(item.get("male", 0.0))
			var female := float(item.get("female", 0.0))
			var male_width := half_width * male / max_count
			var female_width := half_width * female / max_count
			draw_rect(Rect2(center - label_width / 2.0 - male_width, y + 2, male_width, row_height - 5), Color("3274d9"))
			draw_rect(Rect2(center + label_width / 2.0, y + 2, female_width, row_height - 5), Color("c78318"))
			draw_string(font, Vector2(center - label_width / 2.0, y + row_height - 7), str(item.get("label", "")),
				HORIZONTAL_ALIGNMENT_CENTER, label_width, 8, Color("5e6f81"))
			draw_string(font, Vector2(2, y + row_height - 7), "%.0f" % male,
				HORIZONTAL_ALIGNMENT_RIGHT, center - label_width / 2.0 - 8, 7, Color("3274d9"))
			draw_string(font, Vector2(center + label_width / 2.0 + 5, y + row_height - 7), "%.0f" % female,
				HORIZONTAL_ALIGNMENT_LEFT, half_width, 7, Color("c78318"))
		draw_string(font, Vector2(2, size.y - 1), "男  ◀",
			HORIZONTAL_ALIGNMENT_RIGHT, center - 22, 8, Color("3274d9"))
		draw_string(font, Vector2(center + 22, size.y - 1), "▶  女",
			HORIZONTAL_ALIGNMENT_LEFT, center - 24, 8, Color("c78318"))


class _PanelSectorMatrixChart extends Control:
	var data: Array = []
	var font: Font

	func _draw() -> void:
		if data.is_empty():
			return
		var max_produced := 1.0
		var max_sales := 1.0
		var max_employment := 1.0
		for item: Dictionary in data:
			max_produced = maxf(max_produced, float(item.get("produced", 0.0)))
			max_sales = maxf(max_sales, float(item.get("sales", 0.0)))
			max_employment = maxf(max_employment, float(item.get("employment", 0.0)))
		var name_width := minf(86.0, size.x * 0.23)
		var metric_width := (size.x - name_width - 8.0) / 3.0
		for column in 3:
			draw_string(font, Vector2(name_width + column * metric_width, 11),
				str(["产出", "销售", "就业FTE"][column]),
				HORIZONTAL_ALIGNMENT_CENTER, metric_width, 8, Color("849098"))
		var row_height := (size.y - 22.0) / float(data.size())
		for row in data.size():
			var item: Dictionary = data[row]
			var y := 22.0 + row * row_height
			draw_string(font, Vector2(2, y + 11), "%s · %d家" % [
				str(item.get("label", "")), int(item.get("firms", 0))],
				HORIZONTAL_ALIGNMENT_LEFT, name_width - 4, 8, Color("506172"))
			var values := [float(item.get("produced", 0.0)), float(item.get("sales", 0.0)), float(item.get("employment", 0.0))]
			var maxima := [max_produced, max_sales, max_employment]
			var colors := [Color("16a394"), Color("3274d9"), Color("c78318")]
			for column in 3:
				var x := name_width + column * metric_width + 5.0
				var width := metric_width - 10.0
				draw_rect(Rect2(x, y + 4, width, 8), Color("edf1f6"))
				draw_rect(Rect2(x, y + 4, width * values[column] / maxima[column], 8), colors[column])


class _PanelLorenzChart extends Control:
	var income: Array = []
	var wealth: Array = []
	var font: Font

	func _curve(values: Array, plot: Rect2, color: Color) -> void:
		if values.size() < 2:
			return
		var points := PackedVector2Array()
		for index in values.size():
			points.append(Vector2(
				plot.position.x + plot.size.x * float(index) / float(values.size() - 1),
				plot.end.y - plot.size.y * clampf(float(values[index]), 0.0, 1.0)))
		draw_polyline(points, color, 2.0, true)

	func _draw() -> void:
		var plot := Rect2(Vector2(24, 18), size - Vector2(34, 35))
		draw_line(Vector2(plot.position.x, plot.end.y), Vector2(plot.end.x, plot.position.y), Color("b9c5d1"), 1.0)
		draw_line(Vector2(plot.position.x, plot.end.y), Vector2(plot.end.x, plot.end.y), Color("aebbc8"))
		draw_line(Vector2(plot.position.x, plot.end.y), Vector2(plot.position.x, plot.position.y), Color("aebbc8"))
		_curve(income, plot, Color("7950c7"))
		_curve(wealth, plot, Color("3274d9"))
		draw_rect(Rect2(plot.position.x, 2, 8, 8), Color("7950c7"))
		draw_string(font, Vector2(plot.position.x + 12, 10), "个人收入",
			HORIZONTAL_ALIGNMENT_LEFT, 58, 8, Color("5e6f81"))
		draw_rect(Rect2(plot.position.x + 76, 2, 8, 8), Color("3274d9"))
		draw_string(font, Vector2(plot.position.x + 88, 10), "个人正净财富",
			HORIZONTAL_ALIGNMENT_LEFT, 90, 8, Color("5e6f81"))
		draw_string(font, Vector2(plot.position.x, size.y - 1), "人口累计份额 →",
			HORIZONTAL_ALIGNMENT_RIGHT, plot.size.x, 8, Color("849098"))


class _PanelDecileChart extends Control:
	var income: Array = []
	var consumption: Array = []
	var font: Font

	func _draw() -> void:
		if income.size() < 10 or consumption.size() < 10:
			return
		var plot := Rect2(Vector2(24, 22), size - Vector2(34, 45))
		var max_value := 0.01
		for value in income + consumption:
			max_value = maxf(max_value, float(value))
		var slot := plot.size.x / 10.0
		for index in 10:
			var income_h := plot.size.y * float(income[index]) / max_value
			var consumption_h := plot.size.y * float(consumption[index]) / max_value
			var width := minf(15.0, slot * 0.28)
			var center := plot.position.x + slot * (index + 0.5)
			draw_rect(Rect2(center - width - 1, plot.end.y - income_h, width, income_h), Color("7950c7"))
			draw_rect(Rect2(center + 1, plot.end.y - consumption_h, width, consumption_h), Color("16a394"))
			draw_string(font, Vector2(plot.position.x + slot * index, plot.end.y + 14), "D%d" % (index + 1),
				HORIZONTAL_ALIGNMENT_CENTER, slot, 7, Color("6f7d89"))
		draw_rect(Rect2(plot.position.x, 3, 8, 8), Color("7950c7"))
		draw_string(font, Vector2(plot.position.x + 12, 11), "收入份额",
			HORIZONTAL_ALIGNMENT_LEFT, 55, 8, Color("5e6f81"))
		draw_rect(Rect2(plot.position.x + 72, 3, 8, 8), Color("16a394"))
		draw_string(font, Vector2(plot.position.x + 84, 11), "消费份额",
			HORIZONTAL_ALIGNMENT_LEFT, 55, 8, Color("5e6f81"))


class _PanelBubbleChart extends Control:
	var data: Array = []
	var font: Font

	func _draw() -> void:
		if data.is_empty():
			draw_string(font, Vector2(0, size.y * 0.52), "尚无逐企业估值记录",
				HORIZONTAL_ALIGNMENT_CENTER, size.x, 10, Color("849098"))
			return
		var q_max := 1.0
		var inv_max := 1.0
		var cap_max := 1.0
		for item: Dictionary in data:
			q_max = maxf(q_max, float(item.get("q", 0.0)))
			inv_max = maxf(inv_max, float(item.get("investment", 0.0)))
			cap_max = maxf(cap_max, float(item.get("market_cap", 0.0)))
		var plot := Rect2(Vector2(25, 10), size - Vector2(37, 30))
		draw_line(Vector2(plot.position.x, plot.end.y), Vector2(plot.end.x, plot.end.y), Color("bac6d2"))
		draw_line(Vector2(plot.position.x, plot.end.y), Vector2(plot.position.x, plot.position.y), Color("bac6d2"))
		var q_one_x := plot.position.x + plot.size.x / maxf(1.0, q_max * 1.1)
		draw_line(Vector2(q_one_x, plot.position.y), Vector2(q_one_x, plot.end.y), Color("d3dae2"))
		for item: Dictionary in data:
			var q := maxf(0.0, float(item.get("q", 0.0)))
			var investment := maxf(0.0, float(item.get("investment", 0.0)))
			var cap := maxf(0.0, float(item.get("market_cap", 0.0)))
			var point := Vector2(
				plot.position.x + plot.size.x * q / maxf(1.0, q_max * 1.1),
				plot.end.y - plot.size.y * investment / maxf(1.0, inv_max * 1.1))
			var radius := 3.0 + 8.0 * sqrt(cap / cap_max)
			draw_circle(point, radius, Color(0.18, 0.45, 0.85, 0.28))
			draw_arc(point, radius, 0, TAU, 20, Color("3274d9"), 1.0)
		draw_string(font, Vector2(plot.position.x, size.y - 1), "托宾 Q →",
			HORIZONTAL_ALIGNMENT_RIGHT, plot.size.x, 8, Color("849098"))


class _PanelEnergyFlowChart extends Control:
	var values: Dictionary = {}
	var font: Font

	func _node(rect: Rect2, title: String, value: float, color: Color) -> void:
		draw_rect(rect, Color(color.r, color.g, color.b, 0.10))
		draw_rect(rect, color, false, 1.0)
		draw_string(font, rect.position + Vector2(0, 17), title,
			HORIZONTAL_ALIGNMENT_CENTER, rect.size.x, 8, Color("5e6f81"))
		draw_string(font, rect.position + Vector2(0, 36), "%.1f" % value,
			HORIZONTAL_ALIGNMENT_CENTER, rect.size.x, 12, color)

	func _draw() -> void:
		var node_w := minf(112.0, size.x * 0.25)
		var node_h := 48.0
		var y := 26.0
		var left := Rect2(3, y, node_w, node_h)
		var center := Rect2((size.x - node_w) / 2.0, y, node_w, node_h)
		var right := Rect2(size.x - node_w - 3, y, node_w, node_h)
		_node(left, "生产", float(values.get("energy_produced", 0.0)), Color("21a179"))
		_node(center, "市场销售", float(values.get("energy_sold", 0.0)), Color("3274d9"))
		_node(right, "生产使用", float(values.get("energy_used", 0.0)), Color("c78318"))
		draw_line(Vector2(left.end.x + 4, y + node_h / 2), Vector2(center.position.x - 4, y + node_h / 2), Color("9cabb9"), 2.0)
		draw_line(Vector2(center.end.x + 4, y + node_h / 2), Vector2(right.position.x - 4, y + node_h / 2), Color("9cabb9"), 2.0)
		var stock := float(values.get("energy_stock_total", 0.0))
		var reserve := float(values.get("spr_stock", 0.0))
		var coverage := float(values.get("energy_coverage_mean", 0.0))
		draw_string(font, Vector2(3, 103), "商业+部门库存  %.1f" % stock,
			HORIZONTAL_ALIGNMENT_LEFT, size.x * 0.44, 9, Color("506172"))
		draw_string(font, Vector2(size.x * 0.44, 103), "战略储备  %.1f" % reserve,
			HORIZONTAL_ALIGNMENT_LEFT, size.x * 0.30, 9, Color("7950c7"))
		draw_string(font, Vector2(3, 125), "库存覆盖 %.1f 天 · 未满足需求 %.1f" % [
			coverage, float(values.get("energy_unfilled", 0.0))],
			HORIZONTAL_ALIGNMENT_LEFT, size.x - 6, 8, Color("849098"))


class _PanelFiscalFlowChart extends Control:
	var values: Dictionary = {}
	var font: Font

	func _draw_stack(rect: Rect2, parts: Array, total: float) -> void:
		var cursor := rect.position.y
		for part: Dictionary in parts:
			var value := maxf(0.0, float(part.get("value", 0.0)))
			var height := rect.size.y * value / maxf(total, 1e-9)
			draw_rect(Rect2(rect.position.x, cursor, rect.size.x, height), part.get("color", Color.GRAY))
			cursor += height

	func _draw() -> void:
		var revenues := [
			{"label": "所得", "value": float(values.get("tax_income", 0.0)), "color": Color("16a394")},
			{"label": "消费", "value": float(values.get("tax_consumption", 0.0)), "color": Color("3274d9")},
			{"label": "企业", "value": float(values.get("tax_profit", 0.0)), "color": Color("7950c7")},
			{"label": "其他", "value": maxf(0.0, float(values.get("fiscal_revenue_total", 0.0)) - float(values.get("tax_income", 0.0)) - float(values.get("tax_consumption", 0.0)) - float(values.get("tax_profit", 0.0))), "color": Color("7a8b9b")},
		]
		var spending := [
			{"label": "政府消费", "value": float(values.get("gov_consumption", 0.0)), "color": Color("3274d9")},
			{"label": "转移", "value": float(values.get("benefit_paid", 0.0)), "color": Color("7950c7")},
			{"label": "公共投资", "value": float(values.get("public_investment", 0.0)), "color": Color("16a394")},
			{"label": "其他", "value": maxf(0.0, float(values.get("augmented_gov_spending", 0.0)) - float(values.get("gov_consumption", 0.0)) - float(values.get("benefit_paid", 0.0)) - float(values.get("public_investment", 0.0))), "color": Color("c78318")},
		]
		var revenue_total := maxf(0.0, float(values.get("fiscal_revenue_total", 0.0)))
		var spending_total := maxf(0.0, float(values.get("augmented_gov_spending", 0.0)))
		var max_total := maxf(1.0, maxf(revenue_total, spending_total))
		var base_y := size.y - 28.0
		var max_h := size.y - 52.0
		var bar_w := minf(54.0, size.x * 0.14)
		var rev_rect := Rect2(size.x * 0.23 - bar_w / 2, base_y - max_h * revenue_total / max_total, bar_w, max_h * revenue_total / max_total)
		var spend_rect := Rect2(size.x * 0.70 - bar_w / 2, base_y - max_h * spending_total / max_total, bar_w, max_h * spending_total / max_total)
		_draw_stack(rev_rect, revenues, maxf(revenue_total, 1e-9))
		_draw_stack(spend_rect, spending, maxf(spending_total, 1e-9))
		draw_string(font, Vector2(0, 11), "收入 %.1f" % revenue_total,
			HORIZONTAL_ALIGNMENT_CENTER, size.x * 0.46, 9, Color("087f74"))
		draw_string(font, Vector2(size.x * 0.5, 11), "支出 %.1f" % spending_total,
			HORIZONTAL_ALIGNMENT_CENTER, size.x * 0.46, 9, Color("2f72d6"))
		draw_string(font, Vector2(0, size.y - 5), "赤字为正 = 净注入  %.1f" % float(values.get("gov_deficit", 0.0)),
			HORIZONTAL_ALIGNMENT_CENTER, size.x, 8, Color("849098"))


class _PanelBankBalanceChart extends Control:
	var values: Dictionary = {}
	var font: Font

	func _bar(y: float, label: String, value: float, maximum: float, color: Color) -> void:
		draw_string(font, Vector2(2, y + 10), label,
			HORIZONTAL_ALIGNMENT_LEFT, 76, 8, Color("5e6f81"))
		var x := 80.0
		var width := maxf(20.0, size.x - 145.0)
		draw_rect(Rect2(x, y + 2, width, 9), Color("edf1f6"))
		draw_rect(Rect2(x, y + 2, width * maxf(0.0, value) / maximum, 9), color)
		draw_string(font, Vector2(x + width + 5, y + 10), "%.1f" % value,
			HORIZONTAL_ALIGNMENT_RIGHT, 56, 8, color)

	func _draw() -> void:
		var credit := float(values.get("total_credit", 0.0))
		var deposits := float(values.get("bank_deposit_total", 0.0))
		var capital := float(values.get("bank_capital", 0.0))
		var maximum := maxf(1.0, maxf(credit, maxf(deposits, capital)))
		_bar(15, "信贷资产", credit, maximum, Color("16a394"))
		_bar(48, "存款负债", deposits, maximum, Color("3274d9"))
		_bar(81, "资本缓冲", capital, maximum, Color("21a166"))
		var capital_ratio := capital / maxf(credit, 1e-9)
		draw_string(font, Vector2(2, 129), "资本/信贷 %.1f%% · 本期核销 %.1f" % [
			capital_ratio * 100.0, float(values.get("writeoffs", 0.0))],
			HORIZONTAL_ALIGNMENT_LEFT, size.x - 4, 8, Color("849098"))


class _PanelLineChart extends Control:
	var data: Array = []   # [{values, label, text, color}]
	var indexed := false
	var font: Font

	func _display_values(item: Dictionary) -> Array:
		var raw: Array = item.get("values", [])
		if not indexed:
			return raw
		var base := 0.0
		for value in raw:
			if absf(float(value)) > 1e-9:
				base = float(value)
				break
		if absf(base) <= 1e-9:
			return raw
		var out: Array = []
		for value in raw:
			out.append(100.0 + (float(value) - base) / absf(base) * 100.0)
		return out

	func _draw() -> void:
		var legend_x := 4.0
		for item: Dictionary in data:
			var color: Color = item.get("color", Color.GRAY)
			draw_circle(Vector2(legend_x + 3.0, 10.0), 3.0, color)
			var legend := "%s %s" % [str(item.get("label", "")), str(item.get("text", ""))]
			draw_string(font, Vector2(legend_x + 10.0, 14.0), legend,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 8, Color("5e6f81"))
			legend_x += font.get_string_size(legend,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 8).x + 24.0
		var plot := Rect2(Vector2(4, 25), size - Vector2(8, 34))
		for grid_index in 4:
			var gy := plot.position.y + plot.size.y * float(grid_index) / 3.0
			draw_line(Vector2(plot.position.x, gy), Vector2(plot.end.x, gy),
				Color("e7ecf2"), 1.0)
		var prepared: Array = []
		var low := INF
		var high := -INF
		for item: Dictionary in data:
			var values := _display_values(item)
			prepared.append(values)
			for value in values:
				low = minf(low, float(value))
				high = maxf(high, float(value))
		if low == INF:
			draw_string(font, Vector2(plot.position.x, plot.get_center().y),
				"推进模拟以积累每日历史",
				HORIZONTAL_ALIGNMENT_CENTER, plot.size.x, 10, Color("849098"))
			return
		if is_equal_approx(low, high):
			var padding := maxf(absf(low) * 0.08, 0.01)
			low -= padding
			high += padding
		var span := maxf(high - low, 0.000001)
		if low < 0.0 and high > 0.0:
			var zero_y := plot.end.y - (0.0 - low) / span * plot.size.y
			draw_line(Vector2(plot.position.x, zero_y), Vector2(plot.end.x, zero_y),
				Color("c9d3de"), 1.0)
		for data_index in data.size():
			var values: Array = prepared[data_index]
			if values.is_empty():
				continue
			var points := PackedVector2Array()
			for value_index in values.size():
				var px := plot.position.x if values.size() == 1 else (
					plot.position.x + plot.size.x * float(value_index) / float(values.size() - 1))
				var py := plot.end.y - (float(values[value_index]) - low) / span * plot.size.y
				points.append(Vector2(px, py))
			var color: Color = (data[data_index] as Dictionary).get("color", Color.GRAY)
			if points.size() >= 2:
				draw_polyline(points, color, 1.8, true)
			draw_circle(points[-1], 3.0, color)
		draw_string(font, Vector2(plot.position.x, size.y - 1),
			"最近 %d 日" % int((data[0] as Dictionary).get("values", []).size()) if not data.is_empty() else "",
			HORIZONTAL_ALIGNMENT_RIGHT, plot.size.x, 8, Color("849098"))


class _PanelBarChart extends Control:
	var data: Array = []
	var font: Font

	func _draw() -> void:
		if data.is_empty():
			return
		var max_value := 0.000001
		for item: Dictionary in data:
			max_value = maxf(max_value, absf(float(item.get("value", 0.0))))
		var row_height := size.y / float(data.size())
		for item_index in data.size():
			var item: Dictionary = data[item_index]
			var y := row_height * float(item_index)
			var value := float(item.get("value", 0.0))
			var color: Color = RED if value < 0.0 else item.get("color", Color.GRAY)
			draw_string(font, Vector2(2, y + 13), str(item.get("label", "")),
				HORIZONTAL_ALIGNMENT_LEFT, 84, 9, Color("5e6f81"))
			var bar_x := 88.0
			var bar_width := maxf(10.0, size.x - bar_x - 64.0)
			var bar_y := y + 6.0
			draw_rect(Rect2(bar_x, bar_y, bar_width, 8), Color("edf1f6"))
			draw_rect(Rect2(bar_x, bar_y,
				bar_width * absf(value) / max_value, 8), color)
			draw_string(font, Vector2(bar_x + bar_width + 6.0, y + 14),
				str(item.get("text", "")), HORIZONTAL_ALIGNMENT_RIGHT, 56, 9,
				Color("2a3948"))


class _PanelColumnChart extends Control:
	var data: Array = []
	var font: Font

	func _draw() -> void:
		if data.is_empty():
			return
		var low := 0.0
		var high := 0.0
		for item: Dictionary in data:
			var value := float(item.get("value", 0.0))
			low = minf(low, value)
			high = maxf(high, value)
		if is_equal_approx(low, high):
			high = low + 1.0
		var plot := Rect2(Vector2(4, 18), size - Vector2(8, 44))
		var span := maxf(high - low, 0.000001)
		var zero_y := plot.end.y - (0.0 - low) / span * plot.size.y
		draw_line(Vector2(plot.position.x, zero_y), Vector2(plot.end.x, zero_y),
			Color("cbd6e1"), 1.0)
		var slot_width := plot.size.x / float(data.size())
		for item_index in data.size():
			var item: Dictionary = data[item_index]
			var value := float(item.get("value", 0.0))
			var value_y := plot.end.y - (value - low) / span * plot.size.y
			var top := minf(value_y, zero_y)
			var height := maxf(2.0, absf(value_y - zero_y))
			var color: Color = RED if value < 0.0 else item.get("color", Color.GRAY)
			var bar_width := minf(42.0, slot_width * 0.58)
			var bar_x := plot.position.x + slot_width * (float(item_index) + 0.5) - bar_width / 2.0
			draw_rect(Rect2(bar_x, top, bar_width, height),
				Color(color.r, color.g, color.b, 0.82))
			var text_y := maxf(10.0, top - 4.0)
			draw_string(font, Vector2(plot.position.x + slot_width * float(item_index), text_y),
				str(item.get("text", "")), HORIZONTAL_ALIGNMENT_CENTER, slot_width, 8, color)
			draw_string(font, Vector2(plot.position.x + slot_width * float(item_index), size.y - 7),
				str(item.get("label", "")), HORIZONTAL_ALIGNMENT_CENTER, slot_width, 8,
				Color("5e6f81"))


class _MacroPhaseMap extends Control:
	var has_phase := false
	var x_value := 0.0
	var y_value := 0.0
	var phase := "初始观察期"
	var point_color := Color("5e6f81")
	var font: Font

	func _draw() -> void:
		var plot := Rect2(Vector2(34, 15), size - Vector2(46, 43))
		var half := plot.size / 2.0
		var center := plot.get_center()
		# 四象限仅承担“关系解释”，不重复绘制原始指标序列。
		draw_rect(Rect2(plot.position, half), Color(0.824, 0.29, 0.204, 0.045))
		draw_rect(Rect2(Vector2(center.x, plot.position.y), half),
			Color(0.757, 0.49, 0.086, 0.045))
		draw_rect(Rect2(Vector2(plot.position.x, center.y), half),
			Color(0.184, 0.435, 0.816, 0.035))
		draw_rect(Rect2(center, half), Color(0.059, 0.616, 0.565, 0.04))
		draw_rect(plot, Color("dce4ec"), false, 1.0)
		draw_line(Vector2(center.x, plot.position.y), Vector2(center.x, plot.end.y),
			Color("cbd6e1"), 1.0)
		draw_line(Vector2(plot.position.x, center.y), Vector2(plot.end.x, center.y),
			Color("cbd6e1"), 1.0)
		draw_string(font, plot.position + Vector2(7, 14), "滞胀压力",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("ad6658"))
		draw_string(font, Vector2(center.x + 7, plot.position.y + 14), "需求偏热",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("a8782e"))
		draw_string(font, Vector2(plot.position.x + 7, plot.end.y - 7), "需求偏弱",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("5878a8"))
		draw_string(font, Vector2(center.x + 7, plot.end.y - 7), "低压扩张",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("408c82"))
		draw_string(font, Vector2(plot.position.x, size.y - 7),
			"收缩  ←        增长动能        →  扩张",
			HORIZONTAL_ALIGNMENT_CENTER, plot.size.x, 9, Color("71808f"))
		draw_string(font, Vector2(plot.position.x, 10), "价格压力 ↑",
			HORIZONTAL_ALIGNMENT_CENTER, plot.size.x, 9, Color("71808f"))
		if has_phase:
			var point := Vector2(
				center.x + clampf(x_value, -1.0, 1.0) * plot.size.x * 0.43,
				center.y - clampf(y_value, -1.0, 1.0) * plot.size.y * 0.40)
			draw_line(Vector2(point.x, center.y), point,
				Color(point_color.r, point_color.g, point_color.b, 0.25), 1.0)
			draw_line(Vector2(center.x, point.y), point,
				Color(point_color.r, point_color.g, point_color.b, 0.25), 1.0)
			draw_circle(point, 10.0, Color(1, 1, 1, 0.92))
			draw_circle(point, 6.5, point_color)
			draw_arc(point, 11.5, 0, TAU, 30,
				Color(point_color.r, point_color.g, point_color.b, 0.35), 1.0, true)
			var label_width := font.get_string_size(phase,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 10).x + 14.0
			var label_x := minf(point.x + 12.0, plot.end.x - label_width - 4.0)
			var label_y := clampf(point.y - 12.0, plot.position.y + 20.0, plot.end.y - 23.0)
			draw_rect(Rect2(label_x, label_y, label_width, 21), Color(1, 1, 1, 0.94))
			draw_rect(Rect2(label_x, label_y, label_width, 21),
				Color(point_color.r, point_color.g, point_color.b, 0.35), false, 1.0)
			draw_string(font, Vector2(label_x + 7, label_y + 14), phase,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 10, point_color)
		else:
			draw_string(font, Vector2(plot.position.x, center.y + 4),
				"等待第二期产出与通胀公报",
				HORIZONTAL_ALIGNMENT_CENTER, plot.size.x, 11, Color("71808f"))


class _CountryRadar extends Control:
	var labels: Array = []
	var scores: Array = []
	var comparison: Array = []
	var color := Color("0f9d90")
	var font: Font

	func _points(values: Array, center: Vector2, radius: float) -> PackedVector2Array:
		var points := PackedVector2Array()
		for index in labels.size():
			var angle := -PI / 2.0 + TAU * float(index) / float(maxi(labels.size(), 1))
			var fraction := clampf(float(values[index]) / 100.0, 0.0, 1.0) \
				if index < values.size() else 0.0
			points.append(center + Vector2(cos(angle), sin(angle)) * radius * fraction)
		return points

	func _closed(points: PackedVector2Array) -> PackedVector2Array:
		var closed := PackedVector2Array(points)
		if not points.is_empty():
			closed.append(points[0])
		return closed

	func _draw_dashed(a: Vector2, b: Vector2, dash_color: Color) -> void:
		var length := a.distance_to(b)
		var steps := maxi(1, int(length / 7.0))
		for step in steps:
			if step % 2 == 1:
				continue
			var start := a.lerp(b, float(step) / float(steps))
			var finish := a.lerp(b, minf(1.0, float(step + 1) / float(steps)))
			draw_line(start, finish, dash_color, 1.2, true)

	func _draw() -> void:
		if labels.size() < 3:
			draw_string(font, Vector2(0, size.y / 2.0), "等待国家评分数据",
				HORIZONTAL_ALIGNMENT_CENTER, size.x, 10, Color("849098"))
			return
		var center := Vector2(size.x / 2.0, size.y / 2.0 + 4.0)
		var radius := minf(size.x * 0.30, size.y * 0.34)
		for ring in [0.25, 0.50, 0.75, 1.0]:
			var ring_values: Array = []
			for _index in labels.size():
				ring_values.append(100.0 * float(ring))
			draw_polyline(_closed(_points(ring_values, center, radius)),
				Color("dce4ec"), 1.0, true)
		for index in labels.size():
			var angle := -PI / 2.0 + TAU * float(index) / float(labels.size())
			var outer := center + Vector2(cos(angle), sin(angle)) * radius
			draw_line(center, outer, Color("e2e8ef"), 1.0)
			var label_pos := center + Vector2(cos(angle), sin(angle)) * (radius + 20.0)
			draw_string(font, Vector2(label_pos.x - 38.0, label_pos.y + 3.0),
				str(labels[index]), HORIZONTAL_ALIGNMENT_CENTER, 76.0, 9, Color("5e6f81"))
		if comparison.size() == labels.size():
			var peer_points := _points(comparison, center, radius)
			for index in peer_points.size():
				_draw_dashed(peer_points[index], peer_points[(index + 1) % peer_points.size()],
					Color("8795a4"))
		var score_points := _points(scores, center, radius)
		if score_points.size() >= 3:
			draw_colored_polygon(score_points, Color(color.r, color.g, color.b, 0.15))
			draw_polyline(_closed(score_points), color, 2.2, true)
			for point in score_points:
				draw_circle(point, 3.2, Color.WHITE)
				draw_circle(point, 2.1, color)
		draw_circle(center, 2.2, Color("aeb9c5"))


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
