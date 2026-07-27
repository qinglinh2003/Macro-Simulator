extends Control
## Macro Command v30.2. The desktop is a presentation and command surface;
## the simulation engine remains the sole authority for economic behavior.

const SimulationClientScript = preload("res://scripts/simulation_client.gd")
const M11FrontendAdapterScript = preload("res://scripts/m11_frontend_adapter.gd")
const StartMenuScript = preload("res://scripts/start_menu.gd")
const LocaleCatalogScript = preload("res://scripts/localization.gd")

const SPEEDS := [1, 5, 15, 60]

# ---- Design system ----
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

# Release tiles preserve publication calendars, lag, and explicit missingness.
const TILE_TO_GROUP := {
	"real_output": "real_economy", "unemployment_rate": "labor",
	"inflation": "prices_money", "price_index": "prices_money",
	"policy_rate": "prices_money", "gov_deficit_to_gdp": "fiscal",
	"bank_reserves_total": "banking_credit", "poverty_rate": "distribution",
}

const TILE_SPEC := [
	{"id": "real_output", "label": "@{desktop.main.fragment.60b6b37831c29bca} · GDP", "color": TEAL, "bad_up": false, "kind": "num"},
	{"id": "unemployment_rate", "label": "@{desktop.main.fragment.4546b3d41818bdbf}", "color": AMBER, "bad_up": true, "kind": "pp"},
	{"id": "inflation", "label": "@{desktop.main.fragment.b43cd47df5c0171c}(@{desktop.main.fragment.14937464feefe618})", "color": PURPLE, "bad_up": true, "kind": "pp"},
	{"id": "price_index", "label": "@{desktop.main.fragment.89c07894f37c4102}", "color": BLUE, "bad_up": true, "kind": "num"},
	{"id": "policy_rate", "label": "@{desktop.main.fragment.8003f5e9f9c4a87f}", "color": TEAL, "bad_up": false, "kind": "pp"},
	{"id": "gov_deficit_to_gdp", "label": "@{desktop.main.fragment.7865b21012629320} / GDP", "color": AMBER, "bad_up": true, "kind": "pp"},
	{"id": "bank_reserves_total", "label": "@{desktop.main.fragment.99c2ead02ebe4bae}", "color": GREEN, "bad_up": false, "kind": "num"},
	{"id": "poverty_rate", "label": "@{desktop.main.fragment.9fa5069c139f1dfa}", "color": PURPLE, "bad_up": true, "kind": "pp"},
]

# Each core dimension uses one authoritative released series.
const CORE_DIMENSION_SPEC := [
	{"id": "real_output", "dimension": "@{desktop.main.fragment.e1cf00d81f03c367}", "metric": "@{desktop.main.fragment.60b6b37831c29bca}", "group": "real_economy", "color": TEAL},
	{"id": "unemployment_rate", "dimension": "@{desktop.main.fragment.2c6e0266e1ac28a8}", "metric": "@{desktop.main.fragment.4546b3d41818bdbf}", "group": "labor", "color": AMBER},
	{"id": "inflation", "dimension": "@{desktop.main.fragment.240e892123e10737}", "metric": "@{desktop.main.fragment.b43cd47df5c0171c}", "group": "prices_money", "color": PURPLE},
	{"id": "gov_deficit_to_gdp", "dimension": "@{desktop.main.fragment.f69c325544a29bfe}", "metric": "@{desktop.main.fragment.7865b21012629320}/GDP", "group": "fiscal", "color": BLUE},
	{"id": "credit_to_gdp", "dimension": "@{desktop.main.fragment.a42315e416fa2550}", "metric": "@{desktop.main.fragment.334ec29216cfefb9}/GDP", "group": "banking_credit", "color": TEAL_DK},
	{"id": "poverty_rate", "dimension": "@{desktop.main.fragment.1af7dfd65c353cfc}", "metric": "@{desktop.main.fragment.9fa5069c139f1dfa}", "group": "distribution", "color": GREEN},
	{"id": "population_alive", "dimension": "@{desktop.main.fragment.6909fc6ad79b398d}", "metric": "@{desktop.main.fragment.199dd150fb3a5517}", "group": "population", "color": Color("b0641f")},
	{"id": "current_account", "dimension": "@{desktop.main.fragment.72d71f2db0b4734a}", "metric": "@{desktop.main.fragment.d5ecdc812e1a4f41}", "tab": "world", "color": Color("4a6fa5")},
]

const SEAT_LIST := [
	{"id": "treasury", "name": "@seat.treasury", "tag": "@{desktop.main.fragment.f69c325544a29bfe} · fiscal", "color": Color("2f6fd0")},
	{"id": "central_bank", "name": "@seat.central_bank", "tag": "@{desktop.main.fragment.04ee13cd1dc5602b} · monetary", "color": Color("0f9d90")},
	{"id": "regulator", "name": "@seat.regulator", "tag": "@{desktop.main.fragment.4715621e26b8a39a} · prudential", "color": Color("7a4fd0")},
	{"id": "external_affairs", "name": "@seat.external", "tag": "@{desktop.main.fragment.152131b96f49234c} · external", "color": Color("c17d16")},
	{"id": "energy", "name": "@seat.energy", "tag": "@{desktop.main.fragment.9196f0338a8d16d7} · energy", "color": Color("b0641f")},
]

const GROUP_CN := {
	"fiscal_stance": "@{desktop.main.fragment.43f6933cc681c946}", "tax_and_transfers": "@{desktop.main.fragment.64663ae5bd17dd65}",
	"debt_management": "@{desktop.main.fragment.b3800b69f28ded62}", "monetary_stance": "@{desktop.main.fragment.c377046c8e34fcb4}",
	"liquidity_operations": "@{desktop.main.fragment.9c743e43ab9325f2}", "fx_operations": "@{desktop.main.fragment.04ab5fc4bf852a19}",
	"macroprudential": "@{desktop.main.fragment.e3ed6c9d74e30ff1}", "structural_law": "@{desktop.main.fragment.2c11b7c8e657c355}",
	"trade_and_migration": "@{desktop.main.fragment.a2bd9fd816a4dc32}", "energy_operations": "@{desktop.main.fragment.5a8c4b8f3da8f888}",
	"energy_structure": "@{desktop.main.fragment.96638a61052f9d71}",
}

# Choice labels are presentation-only; submissions use Registry canonical values.
const CHOICE_CN := {
	"monetary_regime": {"exogenous": "@{desktop.main.fragment.dacb3af393ed2897}", "taylor": "@{desktop.main.fragment.172a43aad87e4827}", "manual": "@{desktop.main.fragment.f9730e04f848c894}"},
	"fx_regime": {"float": "@{desktop.main.fragment.fdbfac58d4929d2b}", "peg": "@{desktop.main.fragment.c1ba88409c35cb7a}"},
	"energy_rationing": {
		"market": "@{desktop.main.fragment.c45b3c0f002c4b73}", "household_first": "@{desktop.main.fragment.d119a27b537e205a}",
		"industry_first": "@{desktop.main.fragment.63b3c64f44e37b9b}", "proportional": "@{desktop.main.fragment.45dd655e416b5bda}"},
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
	"bank_enabled": "@{desktop.main.fragment.4b59447693d3cebe}", "bank_realized_pnl": "@{desktop.main.fragment.b88162297e2be3e7}",
	"bonds": "@{desktop.main.fragment.f01ea47030bd2983}", "capital_market": "@{desktop.main.fragment.096a9b89a6ca0eca}",
	"consumption_strata": "@{desktop.main.fragment.25765af2b34419ea} / @{desktop.main.fragment.b6671b3bbdddf517}",
	"demographics_enabled": "@{desktop.main.fragment.190267f080bfe761}",
	"energy_enabled": "@{desktop.main.fragment.ebde6905581cd63b}", "energy_household": "@{desktop.main.fragment.037fd3350ba79442}",
	"government": "@{desktop.main.fragment.093a01f12c6ea203}", "household_credit": "@{desktop.main.fragment.aa64b9d0a0a4029d}",
	"housing_construction_enabled": "@{desktop.main.fragment.7b6367774400949a}", "housing_enabled": "@{desktop.main.fragment.d7cee86069fb2cf8}",
	"housing_market_enabled": "@{desktop.main.fragment.8e809b8d279a6f22}", "interbank": "@{desktop.main.fragment.e90dca7b4168c850}",
	"margin_credit": "@{desktop.main.fragment.1331511548e9f36e}", "mortgage_enabled": "@{desktop.main.fragment.1493224181b590fa}",
	"national_accounts_metrics": "@{desktop.main.fragment.d30755d27f549807}",
	"omo": "@{desktop.main.fragment.095c084bd3a4346c}", "soe_efirm": "@{desktop.main.fragment.bf93a633a0e671fe}",
	"coupling": "@{desktop.main.fragment.5116b40a812677f4}", "multiple_economies": "@{desktop.main.fragment.7cc6ed339a475601}",
	"trade": "@{desktop.main.fragment.7a34cf2881a7bd87}", "capital": "@{desktop.main.fragment.813a545012b8a4e6}", "migration": "@{desktop.main.fragment.43a83cae58843156}",
	"cross_border_flow": "@{desktop.main.fragment.4a7bfb07400aeec0}",
}

const EVENT_TITLES := {
	"decision_context_opened": "@{desktop.main.fragment.0aeadb5f742ebc51}",
	"human_proposal_queued": "@{desktop.main.fragment.a6ccd9289e42652d}",
	"human_proposal_collected": "@{desktop.main.fragment.67cdb1f823c6a64f}",
	"decision_accepted_noop": "@{desktop.main.fragment.ecb123493231d464}",
	"decision_accepted_pending": "@{desktop.main.fragment.3420edb1c6f54235}",
	"decision_accepted": "@{desktop.main.fragment.3420edb1c6f54235}",
	"decision_rejected": "@{desktop.main.fragment.eaf8c9f96858f854}",
	"decision_effective": "@{desktop.main.fragment.2b8a37c307f6270e}",
	"decision_cancelled": "@{desktop.main.fragment.c7abe8c5e1a76afc}",
	"emergency_trigger": "@{desktop.main.fragment.7250fb7b695456be}",
	"seat_assignment": "@{desktop.main.fragment.eb4b0f8ec59d44b0}",
	"seat_assigned": "@{desktop.main.fragment.eb4b0f8ec59d44b0}",
	"shock_announced": "@{desktop.main.fragment.317af555115af871}",
	"shock_started": "@{desktop.main.fragment.598d4c0f87ee05c3}",
	"shock_ended": "@{desktop.main.fragment.28b97fb09434f722}",
}

const REASON_CN := {
	"no_change": "@{desktop.main.fragment.23f5014ed7c8bbd2}",
	"accepted": "@{desktop.main.fragment.5e56e4eea0061b1d}",
	"bank_capital_stress": "@{desktop.main.fragment.953689e5975de1de}",
	"energy_shortage": "@{desktop.main.fragment.efa1bf4d5df8ebd7}",
	"liquidity_stress": "@{desktop.main.fragment.0043294fc8fc68b9}",
	"inflation_stress": "@{desktop.main.fragment.8c56a39abc6af565}",
	"unemployment_stress": "@{desktop.main.fragment.37dabedf3f357b96}",
	"energy_stress": "@{desktop.main.fragment.20500c5502189d96}",
}

#  Secondary pages: thematic splitting, 8 knobs per page; single-screen browsing as priority.
#  The new knob, not included, automatically falls on the "other" page of the seat.
const LEVER_PAGES := {
	"treasury": [
		{"name": "@{desktop.main.fragment.18d12f807b67b127}", "levers": ["gov_consumption_share", "gov_deficit_target",
			"gov_investment_share", "deficit_u_cap", "deficit_u_ref",
			"fiscal_uses_national_accounts_gdp"]},
		{"name": "@{desktop.main.fragment.ac69ca1a175804a3}", "levers": ["job_guarantee", "jg_wage_ratio",
			"jg_public_works_share", "benefit_replacement", "benefit_income_floor",
			"pension_replacement", "housing_permits"]},
		{"name": "@{desktop.main.fragment.c55e81b5476016e8}", "levers": ["tax_income_rate", "tax_profit_rate",
			"tax_consumption_rate", "tax_wealth_rate", "tax_luxury_rate",
			"tax_necessity_rate", "tax_energy_rate", "tax_energy_windfall"]},
		{"name": "@{desktop.main.fragment.72bf885ef5ef4264}", "levers": ["income_allowance", "wealth_allowance",
			"housing_in_wealth_tax", "housing_property_tax", "housing_transfer_tax",
			"land_fee_share", "land_fee_stock_elasticity"]},
		{"name": "@{desktop.main.fragment.25f1fe1a6eec04af}", "levers": ["min_wage", "energy_subsidy_rate",
			"energy_subsidy_threshold", "energy_cap_compensation"]},
		{"name": "@{desktop.main.fragment.b3800b69f28ded62}", "levers": ["bond_coupon", "bond_finance_frac",
			"bond_maturity"]},
	],
	"central_bank": [
		{"name": "@{desktop.main.fragment.3a1e1e12721eb47b}", "levers": ["monetary_regime", "manual_policy_rate",
			"r_neutral", "r_max", "rate_inertia", "taylor_phi_pi", "taylor_phi_u"]},
		{"name": "@{desktop.main.fragment.fa2fde09c7b3b528}", "levers": ["inflation_target", "infl_ema_lambda",
			"u_natural", "cb_core_inflation", "cb_log_inflation",
			"cb_uses_fixed_basket_cpi"]},
		{"name": "@{desktop.main.fragment.9c743e43ab9325f2}", "levers": ["omo", "omo_reserve_target",
			"omo_index_deposits", "omo_drain_frac", "reserve_floor_frac", "lolr"]},
		{"name": "@{desktop.main.fragment.04ab5fc4bf852a19}", "levers": ["fx_regime", "peg_anchor", "peg_reserve_scale",
			"capital_control", "external_interest_settlement_fraction"]},
	],
	"regulator": [
		{"name": "@{desktop.main.fragment.938d29783889c25b}", "levers": ["bank_min_capital", "bank_target_capital_ratio",
			"bank_capital_constraint", "bank_leverage_cap", "bank_exposure_limit",
			"bank_bond_duration_limit", "bank_migrate_on_failure"]},
		{"name": "@{desktop.main.fragment.b9222699ba32dc3b}", "levers": ["mortgage_ltv_cap", "mortgage_dsti_cap",
			"mortgage_risk_weight", "mortgage_stress_rate_addon",
			"mortgage_min_capital_ratio", "mortgage_underwriting"]},
		{"name": "@{desktop.main.fragment.0f170be6a7805462}", "levers": ["kappa", "hh_credit_limit",
			"firm_credit_min_dscr", "deposit_rate_floor", "margin_ltv", "margin_max",
			"regulatory_firm_capital_haircut", "regulatory_firm_inventory_haircut"]},
		{"name": "@{desktop.main.fragment.2c11b7c8e657c355}", "levers": ["household_bankruptcy", "bankrupt_persist",
			"bank_resolution_fund", "unified_bank_rwa", "mortgage_arrears_floor",
			"mortgage_foreclosure_ltv", "rental_eviction_arrears"]},
	],
	"external_affairs": [
		{"name": "@{desktop.main.fragment.4ecb8b11b74aa377}", "levers": ["tariff", "import_quota", "export_subsidy",
			"sanctions_imposed_on"]},
		{"name": "@{desktop.main.fragment.4fa8a3dd172e045d}", "levers": ["immigration_cap", "emigration_cap",
			"guest_worker_return", "remittance_tax", "outward_remittance_tax"]},
	],
	"energy": [
		{"name": "@{desktop.main.fragment.0202bc620c8af373}", "levers": ["energy_price_cap", "energy_rationing",
			"spr_target_units", "spr_flow_cap", "soe_price_at_cost", "soe_efirm"]},
	],
}

const LEVER_CN := {
	#  Debt management
	"bond_coupon": "@{desktop.main.fragment.a585173c1446684d}", "bond_finance_frac": "@{desktop.main.fragment.d46923ba8f73a050}",
	"bond_maturity": "@{desktop.main.fragment.085b9abefa05b261}",
	#  Energy Operations / Structure
	"energy_price_cap": "@{desktop.main.fragment.92b8c1b301d4d45b}", "energy_rationing": "@{desktop.main.fragment.ac19d342b2037632}",
	"soe_price_at_cost": "@{desktop.main.fragment.d2b9feee4224bb53}", "spr_flow_cap": "@{desktop.main.fragment.e5ba2008c5edcf36}",
	"spr_target_units": "@{desktop.main.fragment.1c06da6a0f5635ac}", "soe_efirm": "@{desktop.main.fragment.5b620c447a3ca2c8}",
	#  Financial position
	"benefit_income_floor": "@{desktop.main.fragment.c585ef47657eab56}", "benefit_replacement": "@{desktop.main.fragment.c25d0a9aa000eadd}",
	"deficit_u_cap": "@{desktop.main.fragment.5a93af53068f5132}", "deficit_u_ref": "@{desktop.main.fragment.015681164903cf80}",
	"fiscal_uses_national_accounts_gdp": "@{desktop.main.fragment.0f807468649c122d}GDP@{desktop.main.fragment.101573f333c66203}",
	"gov_consumption_share": "@{desktop.main.fragment.30626a99326a21db}", "gov_deficit_target": "@{desktop.main.fragment.40ce85b44bff0da9}",
	"gov_investment_share": "@{desktop.main.fragment.a26995b981a5ba9c}", "housing_permits": "@{desktop.main.fragment.3eac66a599f28ad0}",
	"jg_public_works_share": "@{desktop.main.fragment.b5a6fdfc541b2a45}", "jg_wage_ratio": "@{desktop.main.fragment.6ea5dda7dac4e378}",
	"job_guarantee": "@{desktop.main.fragment.ed3ed318bad67bc6}", "pension_replacement": "@{desktop.main.fragment.a58c5e1239be71c0}",
	#  Foreign exchange operations
	"capital_control": "@{desktop.main.fragment.6439936fb63d4928}",
	"external_interest_settlement_fraction": "@{desktop.main.fragment.9106c6896b992baf}",
	"fx_regime": "@{desktop.main.fragment.531ba19ccc9f86c2}", "peg_anchor": "@{desktop.main.fragment.9dee57b657117432}",
	"peg_reserve_scale": "@{desktop.main.fragment.3ca8697f0ebe9d99}",
	#  Mobility Operations
	"lolr": "@{desktop.main.fragment.ec48cc31f2b2946d}", "omo": "@{desktop.main.fragment.095c084bd3a4346c}",
	"omo_drain_frac": "@{desktop.main.fragment.9146e11296dabc49}", "omo_index_deposits": "@{desktop.main.fragment.513f94ea8178e5c4}",
	"omo_reserve_target": "@{desktop.main.fragment.134643526fff8c9e}", "reserve_floor_frac": "@{desktop.main.fragment.872ba02fb07bac76}",
	#  Macroprudential
	"bank_bond_duration_limit": "@{desktop.main.fragment.8c9f862f2285a44b}",
	"bank_capital_constraint": "@{desktop.main.fragment.5c4138eb7f8b3943}",
	"bank_exposure_limit": "@{desktop.main.fragment.c0f64929ed919653}", "bank_leverage_cap": "@{desktop.main.fragment.3632c6015b1d9b75}",
	"bank_migrate_on_failure": "@{desktop.main.fragment.77c970a647ab3be1}", "bank_min_capital": "@{desktop.main.fragment.25fea0bd8895f5c0}",
	"bank_target_capital_ratio": "@{desktop.main.fragment.71cae10e6df219df}",
	"deposit_rate_floor": "@{desktop.main.fragment.c80c5ee75fe0662e}",
	"firm_credit_min_dscr": "@{desktop.main.fragment.a907707577a83741}",
	"hh_credit_limit": "@{desktop.main.fragment.8d6ef1893a66d823}", "kappa": "@{desktop.main.fragment.33ad88104e1d081a} κ",
	"margin_ltv": "@{desktop.main.fragment.c7bec59e04d3a3f3}", "margin_max": "@{desktop.main.fragment.e185f3bcd32d6bb8}",
	"mortgage_dsti_cap": "@{desktop.main.fragment.88a527a3b689c347}", "mortgage_ltv_cap": "@{desktop.main.fragment.19b94f60ccac8f04}",
	"mortgage_min_capital_ratio": "@{desktop.main.fragment.629986c1a3935857}",
	"mortgage_risk_weight": "@{desktop.main.fragment.094cbb153df3b56e}",
	"mortgage_stress_rate_addon": "@{desktop.main.fragment.8bf2847b68fa233f}",
	"mortgage_underwriting": "@{desktop.main.fragment.613568eee96fc801}",
	"regulatory_firm_capital_haircut": "@{desktop.main.fragment.db3c0276e4c37296}",
	"regulatory_firm_inventory_haircut": "@{desktop.main.fragment.911222617be8de9d}",
	#  Currency position
	"cb_core_inflation": "@{desktop.main.fragment.09c4de096361f261}", "cb_log_inflation": "@{desktop.main.fragment.6b4ca31e1d4ecfe3}",
	"cb_uses_fixed_basket_cpi": "@{desktop.main.fragment.46df016563619d18}CPI@{desktop.main.fragment.101573f333c66203}",
	"infl_ema_lambda": "@{desktop.main.fragment.ad2534f16ab98669} λ", "inflation_target": "@{desktop.main.fragment.05fa8d2ef1a743ba}",
	"manual_policy_rate": "@{desktop.main.fragment.8ba3071d31d189ed}", "monetary_regime": "@{desktop.main.fragment.1a25cae932198f4e}",
	"r_max": "@{desktop.main.fragment.2b61873825900a46}", "r_neutral": "@{desktop.main.fragment.564804eb66d75139}",
	"rate_inertia": "@{desktop.main.fragment.4eb756067481d462}", "taylor_phi_pi": "@{desktop.main.fragment.43aa7defcf2e0e96} φπ",
	"taylor_phi_u": "@{desktop.main.fragment.0dca991062a58a69} φu", "u_natural": "@{desktop.main.fragment.5031e75a219939da}",
	#  Structural legislation
	"bank_resolution_fund": "@{desktop.main.fragment.1fcd8407f7b0ff0d}", "bankrupt_persist": "@{desktop.main.fragment.46e0fde77d7b6412}",
	"household_bankruptcy": "@{desktop.main.fragment.78722fbb6ccfd004}",
	"mortgage_arrears_floor": "@{desktop.main.fragment.6b5c7b5063af3365}",
	"mortgage_foreclosure_ltv": "@{desktop.main.fragment.aef3569565d12790}",
	"rental_eviction_arrears": "@{desktop.main.fragment.fbcddcf835dfe81c}",
	"unified_bank_rwa": "@{desktop.main.fragment.e26bc1b096794b2c}",
	#  Taxes and transfers
	"energy_cap_compensation": "@{desktop.main.fragment.0372a1d1b1c79cdb}", "energy_subsidy_rate": "@{desktop.main.fragment.c9d16bda7e51dd36}",
	"energy_subsidy_threshold": "@{desktop.main.fragment.06a71dc74091a994}",
	"housing_in_wealth_tax": "@{desktop.main.fragment.81ed8a53b74332c8}", "housing_property_tax": "@{desktop.main.fragment.5c03f26c6487802b}",
	"housing_transfer_tax": "@{desktop.main.fragment.b38e4a60c6706269}", "income_allowance": "@{desktop.main.fragment.b58a3ec038b33c99}",
	"land_fee_share": "@{desktop.main.fragment.1e5b490e71c75f4a}", "land_fee_stock_elasticity": "@{desktop.main.fragment.a2b3c706a157cc07}",
	"min_wage": "@{desktop.main.fragment.aec33b0dadddd48c}", "tax_consumption_rate": "@{desktop.main.fragment.cc05a8a0e5b5f4a1}",
	"tax_energy_rate": "@{desktop.main.fragment.a95569686009fdd9}", "tax_energy_windfall": "@{desktop.main.fragment.43baa8f77e6d211f}",
	"tax_income_rate": "@{desktop.main.fragment.05f0341d936231be}", "tax_luxury_rate": "@{desktop.main.fragment.c3f9a14027528972}",
	"tax_necessity_rate": "@{desktop.main.fragment.625c0dbb850e1b8c}", "tax_profit_rate": "@{desktop.main.fragment.e024fa20c95692f6}",
	"tax_wealth_rate": "@{desktop.main.fragment.4448d7bbac96288e}", "wealth_allowance": "@{desktop.main.fragment.feb467cd8e186081}",
	#  Trade and migration
	"emigration_cap": "@{desktop.main.fragment.86c2b075736216a2}", "export_subsidy": "@{desktop.main.fragment.df4edf7edf81ac23}",
	"guest_worker_return": "@{desktop.main.fragment.c706ad460636c4b8}", "immigration_cap": "@{desktop.main.fragment.7e47992b64f68faa}",
	"import_quota": "@{desktop.main.fragment.195b79e5b12c1cba}", "outward_remittance_tax": "@{desktop.main.fragment.252848445f9ac018}",
	"remittance_tax": "@{desktop.main.fragment.522e9afeb5ec245b}", "sanctions_imposed_on": "@{desktop.main.fragment.a52e6a6864cdfe8b}",
	"tariff": "@{desktop.main.fragment.a0fe74b55dc33755}",
}

#  Core mechanisms cannot be reliably launched by field names. The remaining scales, floors and floors, tax rates and system switches are below
#  Rules generate definitions; all statements remain read point/semantics of registry as mechanism boundaries.
const POLICY_HELP := {
	"gov_consumption_share": {
		"definition": "@{desktop.main.fragment.48bc7f8dc993beb0}",
		"effect": "@{desktop.main.fragment.a16068931eef47c4}"},
	"gov_deficit_target": {
		"definition": "@{desktop.main.fragment.5ceda2278a969731}",
		"effect": "@{desktop.main.fragment.441546357b0817e6}"},
	"deficit_u_ref": {
		"definition": "@{desktop.main.fragment.fce21eb53aa51522}",
		"effect": "@{desktop.main.fragment.c0be48f48a34ffef}"},
	"deficit_u_cap": {
		"definition": "@{desktop.main.fragment.6ba1b442d1cf3899}",
		"effect": "@{desktop.main.fragment.414ffb0d0ef72489}"},
	"benefit_replacement": {
		"definition": "@{desktop.main.fragment.74cfda7c6d9500ea}",
		"effect": "@{desktop.main.fragment.30ef0335779983a4}"},
	"benefit_income_floor": {
		"definition": "@{desktop.main.fragment.817a18e68e04ff0c}",
		"effect": "@{desktop.main.fragment.9c57550439f903a3}"},
	"job_guarantee": {
		"definition": "@{desktop.main.fragment.2bae021567467bbb}",
		"effect": "@{desktop.main.fragment.e140840e59d07b61}"},
	"jg_wage_ratio": {
		"definition": "@{desktop.main.fragment.2da99f39acf97e24}",
		"effect": "@{desktop.main.fragment.f990a74bc1b002a8}"},
	"bond_finance_frac": {
		"definition": "@{desktop.main.fragment.b4a1b479364ed6e2}",
		"effect": "@{desktop.main.fragment.904dd94038896d1c}"},
	"bond_coupon": {
		"definition": "@{desktop.main.fragment.4b7dab28b955782c}",
		"effect": "@{desktop.main.fragment.b7b71960313e46c8}"},
	"bond_maturity": {
		"definition": "@{desktop.main.fragment.32b43d653f0b9122}",
		"effect": "@{desktop.main.fragment.dbe12eb0cf7a776b}"},
	"monetary_regime": {
		"definition": "@{desktop.main.fragment.bfe6daa1466663f1}",
		"effect": "@{desktop.main.fragment.ee266ea5d63141e9}"},
	"manual_policy_rate": {
		"definition": "@{desktop.main.fragment.1fa43d6e1e28af4e}",
		"effect": "@{desktop.main.fragment.57190d3b0def87f4}"},
	"inflation_target": {
		"definition": "@{desktop.main.fragment.528a1e8fc840dd77}",
		"effect": "@{desktop.main.fragment.b90ca4c61ea87d2e}"},
	"taylor_phi_pi": {
		"definition": "@{desktop.main.fragment.dd75b53a08590a48}",
		"effect": "@{desktop.main.fragment.6bea0e019e018653}"},
	"taylor_phi_u": {
		"definition": "@{desktop.main.fragment.66f7b78898b7d252}",
		"effect": "@{desktop.main.fragment.b12538ee06aa053d}"},
	"rate_inertia": {
		"definition": "@{desktop.main.fragment.9af232e59434fff5}",
		"effect": "@{desktop.main.fragment.91e8ffc984b359db}"},
	"infl_ema_lambda": {
		"definition": "@{desktop.main.fragment.a4909f4c8358d271}",
		"effect": "@{desktop.main.fragment.b5e715f775534ba6}"},
	"omo": {
		"definition": "@{desktop.main.fragment.7b424f4f6771be17}",
		"effect": "@{desktop.main.fragment.397366b7e6fb0651}"},
	"lolr": {
		"definition": "@{desktop.main.fragment.ee3354358f0c5dcf}",
		"effect": "@{desktop.main.fragment.b7750f9244a18190}"},
	"reserve_floor_frac": {
		"definition": "@{desktop.main.fragment.f8fcdc058c463fd3}",
		"effect": "@{desktop.main.fragment.d41a5b9683c39662}"},
	"fx_regime": {
		"definition": "@{desktop.main.fragment.14cec5a0711ffeba}",
		"effect": "@{desktop.main.fragment.a5457e293ca412c3}"},
	"peg_anchor": {
		"definition": "@{desktop.main.fragment.ae81eb5dccc4fe2d}",
		"effect": "@{desktop.main.fragment.562af17be361ed39}"},
	"peg_reserve_scale": {
		"definition": "@{desktop.main.fragment.90b6082dec978110}",
		"effect": "@{desktop.main.fragment.30ae8c392b105c77}"},
	"capital_control": {
		"definition": "@{desktop.main.fragment.911a5eed85d523ec}",
		"effect": "@{desktop.main.fragment.ccc65ab5b0e52d79}"},
	"bank_capital_constraint": {
		"definition": "@{desktop.main.fragment.2d3767d2d299d4f9}",
		"effect": "@{desktop.main.fragment.e818608c0fe9a645}"},
	"bank_target_capital_ratio": {
		"definition": "@{desktop.main.fragment.04eb2f53ca12ddc8}",
		"effect": "@{desktop.main.fragment.0816052f9afa2df3}"},
	"bank_leverage_cap": {
		"definition": "@{desktop.main.fragment.7df741dea26482c8}",
		"effect": "@{desktop.main.fragment.656e0666a1e5ec06}"},
	"mortgage_ltv_cap": {
		"definition": "@{desktop.main.fragment.09ff29ab3a81a8bd}",
		"effect": "@{desktop.main.fragment.1481c77a3dfe4276}"},
	"mortgage_dsti_cap": {
		"definition": "@{desktop.main.fragment.7864f39b5cb71061}",
		"effect": "@{desktop.main.fragment.afbd6541487655fe}"},
	"energy_rationing": {
		"definition": "@{desktop.main.fragment.cb52926cca5e0689}",
		"effect": "@{desktop.main.fragment.d483ceb2faadd682}"},
	"energy_price_cap": {
		"definition": "@{desktop.main.fragment.9218c459e5295092}",
		"effect": "@{desktop.main.fragment.47b99086b643f007}"},
	"spr_target_units": {
		"definition": "@{desktop.main.fragment.951ad587a971b4fd}",
		"effect": "@{desktop.main.fragment.6db51089ce0981a3}"},
	"spr_flow_cap": {
		"definition": "@{desktop.main.fragment.99dcff77905bff51}",
		"effect": "@{desktop.main.fragment.e8c1f7f2b122d430}"},
	"sanctions_imposed_on": {
		"definition": "@{desktop.main.fragment.730227c83b0172b5}",
		"effect": "@{desktop.main.fragment.bbccffcb45a01155}"},
	"tariff": {
		"definition": "@{desktop.main.fragment.d69c9836acbb0fc9}",
		"effect": "@{desktop.main.fragment.b1e5dc960e133746}"},
	"import_quota": {
		"definition": "@{desktop.main.fragment.2bacc4900759fe5b}",
		"effect": "@{desktop.main.fragment.a2d3607eca44cb67}"},
	"export_subsidy": {
		"definition": "@{desktop.main.fragment.cb7db3c77bdf022e}",
		"effect": "@{desktop.main.fragment.4a80e19f2ac41a86}"},
}


#  Indicator panorama: each enabled panel has its own tab and stable backend keys.
#  fmt: pct = share %, pt = interest per tick %, idx = index, num = level
const PANEL_GROUPS := [
	{"id": "real_economy", "name": "@{desktop.main.fragment.c613e26dcc4db0b5}", "color": TEAL, "items": [
		["real_output", "@{desktop.main.fragment.60b6b37831c29bca}", "num"], ["real_consumption", "@{desktop.main.fragment.b63690d28deb0cc0}", "num"],
		["aggregate_capital", "@{desktop.main.fragment.b1b03d6d50c8bdca}", "num"], ["investment_spending", "@{desktop.main.fragment.96d919bb8ec23e4b}", "num"],
		["inventory_to_sales", "@{desktop.main.fragment.780c5fd5b10533dc}/@{desktop.main.fragment.f04b061471b1fd16}", "idx"], ["production_realization_rate", "@{desktop.main.fragment.b1bde29ead0af532}", "pct"]]},
	{"id": "national_accounts", "name": "@{desktop.main.fragment.d30755d27f549807}", "color": Color("286f9f"), "requires": "national_accounts_metrics", "items": [
		["gdp_nominal_expenditure_reconciled", "@{desktop.main.fragment.71fc907cfb4dc132} GDP", "num"],
		["gdp_real_expenditure_reconciled", "@{desktop.main.fragment.e0ae9a3c77ae781d} GDP", "num"],
		["gdp_deflator", "GDP @{desktop.main.fragment.6a1991b82e40df7c}", "idx"],
		["gdp_nominal_household_consumption", "@{desktop.main.fragment.be9cf924408bfa1b}", "num"],
		["gdp_nominal_fixed_capital_formation", "@{desktop.main.fragment.029f64457da1d722}", "num"],
		["gdp_nominal_net_exports", "@{desktop.main.fragment.eafb25a38df7c7c2}", "num"]]},
	{"id": "labor", "name": "@{desktop.main.fragment.d00091cb2bfe9634}", "color": AMBER, "items": [
		["unemployment_rate", "@{desktop.main.fragment.4546b3d41818bdbf}", "pct"], ["u_natural", "@{desktop.main.fragment.1bf04babaee154dd}", "pct"],
		["underemployed_share", "@{desktop.main.fragment.dc93fdfa229b506d}", "pct"], ["vacancies_unfilled", "@{desktop.main.fragment.c9fc9d8969a7dc71}", "num"],
		["avg_wage", "@{desktop.main.fragment.fdc477056b2d48f6}", "num"], ["wage_inflation", "@{desktop.main.fragment.4b3c17787792a6d9}", "pt"]]},
	{"id": "prices_money", "name": "@{desktop.main.fragment.aab5501bd82dde20}", "color": PURPLE, "items": [
		["price_index", "@{desktop.main.fragment.89c07894f37c4102}", "idx"], ["inflation", "@{desktop.main.fragment.b43cd47df5c0171c}", "pt"],
		["avg_markup", "@{desktop.main.fragment.ba19e19b3ae33520}", "idx"], ["policy_rate", "@{desktop.main.fragment.8003f5e9f9c4a87f}", "pt"],
		["total_money", "@{desktop.main.fragment.9eca76ff263a36df}", "num"], ["real_wage", "@{desktop.main.fragment.f0106af3d7386760}", "idx"]]},
	{"id": "fiscal", "name": "@{desktop.main.fragment.f69c325544a29bfe}", "color": BLUE, "items": [
		["gov_debt", "@{desktop.main.fragment.8d6b59cfe9288ceb}", "num"], ["gov_deficit", "@{desktop.main.fragment.2d7e730563828a09}", "num"],
		["tax_total", "@{desktop.main.fragment.f46704f13dceb5a9}", "num"], ["gov_spending", "@{desktop.main.fragment.5f7952230dcd9aff}", "num"],
		["benefit_paid", "@{desktop.main.fragment.c4151305b64340f1}", "num"], ["gov_debt_to_gdp", "@{desktop.main.fragment.095b45ce7df514df}/GDP", "pct"]]},
	{"id": "banking_credit", "name": "@{desktop.main.fragment.76dd27e0821ca6ca}", "color": TEAL_DK, "requires": "bank_enabled", "items": [
		["total_credit", "@{desktop.main.fragment.0bc383f544bd026d}", "num"], ["bank_capital", "@{desktop.main.fragment.fe9d8708034723b5}", "num"],
		["bank_deposit_total", "@{desktop.main.fragment.03acf7cb5656ee50}", "num"], ["writeoffs", "@{desktop.main.fragment.8570c6a44500ff6b}", "num"],
		["total_debt_service_ratio", "@{desktop.main.fragment.11efcd8dc599ab71}", "pct"], ["interbank_rate", "@{desktop.main.fragment.46e9053149aff7d2}", "pt"]]},
	{"id": "debt_risk", "name": "@{desktop.main.fragment.40d3247a91c1eebd}", "color": Color("a35454"), "requires": "bank_enabled", "items": [
		["household_debt_total", "@{desktop.main.fragment.d2cef874cd4f31ad}", "num"],
		["firm_debt_total", "@{desktop.main.fragment.e011facc0e2e08e2}", "num"],
		["debt_service_to_nominal_gdp", "@{desktop.main.fragment.041d6a395228b3a4}/GDP", "pct"],
		["household_interest_arrears_closing", "@{desktop.main.fragment.4371e83ba7df1016}", "num"],
		["bank_realized_credit_losses", "@{desktop.main.fragment.5bc962af39069036}", "num"],
		["hh_bankruptcies", "@{desktop.main.fragment.8063e9732b41f137}", "num"]]},
	{"id": "capital_markets", "name": "@{desktop.main.fragment.096a9b89a6ca0eca}", "color": Color("4a6fa5"), "requires": "capital_market", "items": [
		["equity_market_cap", "@{desktop.main.fragment.c962533795791797}", "num"], ["tobin_q_mean", "@{desktop.main.fragment.262b4d2f27d039c7} Q", "idx"],
		["equity_wealth_share", "@{desktop.main.fragment.3ff371748c070975}", "pct"], ["equity_turnover", "@{desktop.main.fragment.a071a060fcb264ca}", "idx"],
		["equity_ownership_gini", "@{desktop.main.fragment.2e4d457612d85ab9}", "idx"], ["hh_wealth_gini_incl_equity", "@{desktop.main.fragment.6ab21b6833e66390}(@{desktop.main.fragment.08b6efe66850a3e0})", "idx"]]},
	{"id": "housing", "name": "@{desktop.main.fragment.ad67719270cad19a}", "color": Color("8a6b50"), "requires": "housing_enabled", "items": [
		["house_price", "@{desktop.main.fragment.be473d3e46321147}", "num"], ["homeowner_share", "@{desktop.main.fragment.b2bde5d2fcc6341d}", "pct"],
		["housing_pti_ratio", "@{desktop.main.fragment.781f9eb2349a4802}", "idx"],
		["housing_sales_session", "@{desktop.main.fragment.93ce2badb17869b2}", "num"],
		["mortgage_balance_total", "@{desktop.main.fragment.a26affc6332b8144}", "num"],
		["rent_burden_ratio", "@{desktop.main.fragment.da5096f21c424799}", "pct"]]},
	{"id": "energy", "name": "@{desktop.main.fragment.9196f0338a8d16d7}", "color": Color("b0641f"), "requires": "energy_enabled", "items": [
		["energy_price", "@{desktop.main.fragment.264c2c4114eaf977}", "idx"], ["energy_produced", "@{desktop.main.fragment.bab27e15724aac06}", "num"],
		["energy_used", "@{desktop.main.fragment.ea104c0a78b8d079}", "num"], ["energy_stock_total", "@{desktop.main.fragment.90149fcf1ea58d3f}", "num"],
		["energy_cost_share", "@{desktop.main.fragment.77e8df2db61c3f46}", "pct"], ["spr_stock", "@{desktop.main.fragment.ba246184da7bbff6}", "num"]]},
	{"id": "external", "name": "@{desktop.main.fragment.76ac1d5fea76f908}", "color": Color("4a6fa5"), "items": [
		["e", "@{desktop.main.fragment.57ef2c45ef260ee3}", "idx"], ["nfa", "@{desktop.main.fragment.2a34b4aa4ee8731a}", "num"],
		["current_account", "@{desktop.main.fragment.d5ecdc812e1a4f41}", "num"], ["import_value", "@{desktop.main.fragment.1ada65455c2895ba}", "num"],
		["export_delivered_volume", "@{desktop.main.fragment.4db5da905824b9bb}", "num"],
		["remittances", "@{desktop.main.fragment.82bd68e0e3dd55cd}", "num"]]},
	{"id": "distribution", "name": "@{desktop.main.fragment.f7ff5bef360fe23d}", "color": Color("8a5fc0"), "items": [
		["poverty_rate", "@{desktop.main.fragment.9fa5069c139f1dfa}", "pct"], ["income_gini", "@{desktop.main.fragment.bc82cfb1bfbb4494}", "idx"],
		["hh_wealth_gini", "@{desktop.main.fragment.6ab21b6833e66390}", "idx"], ["wage_p90_p10_ratio", "@{desktop.main.fragment.11547412b4531891} P90/P10", "idx"],
		["welfare_log", "@{desktop.main.fragment.3ec8e057df1ade4c}", "idx"], ["savings_rate", "@{desktop.main.fragment.c5286ed8e20619de}", "pct"]]},
	{"id": "population", "name": "@{desktop.main.fragment.ebe5e93cd30676d0}", "color": Color("2a8a68"), "requires": "demographics_enabled", "items": [
		["population_alive", "@{desktop.main.fragment.199dd150fb3a5517}", "num"],
		["net_population_growth_rate_annualized", "@{desktop.main.fragment.b23ecdce954573d5}", "pct"],
		["birth_rate_per_1000_annualized", "@{desktop.main.fragment.f2dd829db4c69625}", "per_thousand"],
		["death_rate_per_1000_annualized", "@{desktop.main.fragment.9ba99193e3c4aa80}", "per_thousand"],
		["dependency_ratio", "@{desktop.main.fragment.23dca1a6ef086b98}", "pct"],
		["avg_household_size", "@{desktop.main.fragment.0c6323e800178262}", "idx"]]},
	{"id": "firms", "name": "@{desktop.main.fragment.069f12042138ce76}", "color": Color("3e7d68"), "items": [
		["firm_count_c", "@{desktop.main.fragment.4fe95cbc41c25b8c}", "num"], ["births", "@{desktop.main.fragment.9bc8563025adf19f}", "num"],
		["deaths", "@{desktop.main.fragment.f7983f7143cd8b68}", "num"], ["n_firms_producing", "@{desktop.main.fragment.a28f4707c5b72df7}", "num"],
		["sector_switches", "@{desktop.main.fragment.e0f3622a02bcec85}", "num"],
		["firm_size_top_share_output", "@{desktop.main.fragment.7646de8d4bac93e9}", "pct"]]},
]

#  Each indicator page is signed using a separate information structure. The target history comes from the records, demographics, labor, and business.
#  Read-only entity snapshots from the desktop runtime; sector IDs match the model.
const PANEL_DESCRIPTIONS := {
	"real_economy": "@{desktop.main.fragment.19ab13eb1f1e51a0}",
	"national_accounts": "@{desktop.main.fragment.5ac8078fcffdc3ce}",
	"labor": "@{desktop.main.fragment.05c5d48eb4da883f}",
	"prices_money": "@{desktop.main.fragment.486e70f82abcef3f}",
	"fiscal": "@{desktop.main.fragment.ebbd948ee03f3299}",
	"banking_credit": "@{desktop.main.fragment.e1f912ef288c5be0}",
	"debt_risk": "@{desktop.main.fragment.469a0e24beb56c4a}",
	"capital_markets": "@{desktop.main.fragment.720ee7bb75f7d1b7}",
	"housing": "@{desktop.main.fragment.ac613566f7a913af}",
	"energy": "@{desktop.main.fragment.8d84ffc395ed3991}",
	"external": "@{desktop.main.fragment.b4449b680b7741d9}",
	"distribution": "@{desktop.main.fragment.19848d193c6c8cc6}",
	"population": "@{desktop.main.fragment.6051a5bdf29503cf}",
	"firms": "@{desktop.main.fragment.da0860ff268e3047}",
}

const PANEL_CHARTS := {
	"real_economy": [
		{"type": "sector_matrix", "title": "SECTORS · @{desktop.main.fragment.56683915e8a0a26c}", "note": "@{desktop.main.fragment.4c97f9db086dc1b9} · @{desktop.main.fragment.f04b061471b1fd16} · @{desktop.main.fragment.2c6e0266e1ac28a8}",
			"items": []},
		{"type": "line", "title": "DEMAND · @{desktop.main.fragment.ab0c82cfd3d88d04}", "note": "@{desktop.main.fragment.ff25493f1cf64344}",
			"items": [["real_output", "@{desktop.main.fragment.60b6b37831c29bca}", "num", TEAL],
				["real_consumption", "@{desktop.main.fragment.b63690d28deb0cc0}", "num", BLUE]]},
		{"type": "line", "title": "CAPITAL · @{desktop.main.fragment.029f64457da1d722}", "note": "@{desktop.main.fragment.86f2998dca14febd}=100", "indexed": true,
			"items": [["aggregate_capital", "@{desktop.main.fragment.b1b03d6d50c8bdca}", "num", BLUE],
				["investment_spending", "@{desktop.main.fragment.96d919bb8ec23e4b}", "num", AMBER],
				["real_output", "@{desktop.main.fragment.60b6b37831c29bca}", "num", TEAL]]},
	],
	"national_accounts": [
		{"type": "line", "title": "GDP · @{desktop.main.fragment.fa3ee80d798867f8}", "note": "@{desktop.main.fragment.86f2998dca14febd}=100", "indexed": true,
			"items": [["gdp_nominal_expenditure_reconciled", "@{desktop.main.fragment.71fc907cfb4dc132} GDP", "num", BLUE],
				["gdp_real_expenditure_reconciled", "@{desktop.main.fragment.e0ae9a3c77ae781d} GDP", "num", TEAL],
				["gdp_deflator", "@{desktop.main.fragment.6a1991b82e40df7c}", "idx", PURPLE]]},
		{"type": "columns", "title": "EXPENDITURE · @{desktop.main.fragment.d95caf0153ffc78f}", "note": "C + I + G + NX",
			"items": [["gdp_nominal_household_consumption", "@{desktop.main.fragment.be9cf924408bfa1b} C", "num", TEAL],
				["gdp_nominal_fixed_capital_formation", "@{desktop.main.fragment.029f64457da1d722} I", "num", BLUE],
				["gdp_nominal_government_consumption", "@{desktop.main.fragment.223be31de4a3a161} G", "num", PURPLE],
				["gdp_nominal_net_exports", "@{desktop.main.fragment.eafb25a38df7c7c2} NX", "num", AMBER]]},
		{"type": "columns", "title": "SECTORS · @{desktop.main.fragment.734c0dcefd410ff4}", "note": "@{desktop.main.fragment.5f323c212f3930de}",
			"items": [["gdp_nominal_gross_output_c", "@{desktop.main.fragment.07c009c26ed383df}", "num", TEAL],
				["gdp_nominal_gross_output_k", "@{desktop.main.fragment.8716cf5fc5d5181c}", "num", BLUE],
				["gdp_nominal_gross_output_e", "@{desktop.main.fragment.9196f0338a8d16d7}", "num", AMBER],
				["gdp_nominal_gross_output_housing", "@{desktop.main.fragment.9a57f79d5b8f28da}", "num", Color("8a6b50")]]},
		{"type": "line", "title": "RECONCILIATION · @{desktop.main.fragment.340d771303952d57}", "note": "@{desktop.main.fragment.f3e5e34056fa953a}",
			"items": [["gdp_nominal_three_approach_raw_spread_share", "@{desktop.main.fragment.abb675e95e02d072}", "pct", RED]]},
		{"type": "line", "title": "APPROACHES · @{desktop.main.fragment.9a5d31af1fe16f07} GDP @{desktop.main.fragment.101573f333c66203}", "note": "@{desktop.main.fragment.484407aacafcf6ea} · @{desktop.main.fragment.69ce9992bfd9510f} / @{desktop.main.fragment.6b182e92b05656d9} / @{desktop.main.fragment.19ff165b5fa4a497}",
			"items": [["gdp_nominal_expenditure_reconciled", "@{desktop.main.fragment.69ce9992bfd9510f}", "num", BLUE],
				["gdp_nominal_income_reconciled", "@{desktop.main.fragment.6b182e92b05656d9}", "num", PURPLE],
				["gdp_nominal_production", "@{desktop.main.fragment.19ff165b5fa4a497}", "num", TEAL]]},
		{"type": "columns", "title": "INCOME · @{desktop.main.fragment.dc35e50bbdd3713f}", "note": "@{desktop.main.fragment.e6cb82b1fcb3bbfc}",
			"items": [["gdp_nominal_compensation_of_employees", "@{desktop.main.fragment.c346fcbc225a2a69}", "num", BLUE],
				["gdp_nominal_accrued_gross_operating_surplus", "@{desktop.main.fragment.979be5701df82ce9}", "num", TEAL],
				["gdp_nominal_net_product_taxes_observed", "@{desktop.main.fragment.7aa3db8ea047016f}", "num", AMBER]]},
		{"type": "columns", "title": "CAPITAL FORMATION · @{desktop.main.fragment.217d1d7ca669ea70}", "note": "@{desktop.main.fragment.36d2a0a5d613697b}",
			"items": [["gdp_nominal_private_fixed_capital_formation", "@{desktop.main.fragment.cdcb6f7c678c81ac}", "num", TEAL],
				["gdp_nominal_public_fixed_capital_formation", "@{desktop.main.fragment.47c7231355664b7b}", "num", BLUE],
				["gdp_nominal_residential_fixed_capital_formation", "@{desktop.main.fragment.6f2f0fbb2164a120}", "num", Color("8a6b50")],
				["gdp_nominal_machinery_fixed_capital_formation", "@{desktop.main.fragment.59ec719b85282a64}", "num", PURPLE]]},
		{"type": "line", "title": "TRADE & INVENTORY · @{desktop.main.fragment.d22e652f8ca2490f}", "note": "@{desktop.main.fragment.37fc4ba17aae4e81}",
			"items": [["gdp_nominal_exports", "@{desktop.main.fragment.7016090059bdfab9}", "num", TEAL],
				["gdp_nominal_imports", "@{desktop.main.fragment.514e5df21b748fda}", "num", BLUE],
				["gdp_nominal_inventory_change", "@{desktop.main.fragment.517358111e3e9d52}", "num", AMBER]]},
		{"type": "line", "title": "REAL EXPENDITURE · @{desktop.main.fragment.800d580fc6c9207b}", "note": "@{desktop.main.fragment.287fca5208feaa56} C / I / G / NX",
			"items": [["gdp_real_household_consumption", "@{desktop.main.fragment.be9cf924408bfa1b} C", "num", TEAL],
				["gdp_real_fixed_capital_formation", "@{desktop.main.fragment.029f64457da1d722} I", "num", BLUE],
				["gdp_real_government_consumption", "@{desktop.main.fragment.223be31de4a3a161} G", "num", PURPLE],
				["gdp_real_net_exports", "@{desktop.main.fragment.eafb25a38df7c7c2} NX", "num", AMBER]]},
		{"type": "line", "title": "TRADE VOLUME · @{desktop.main.fragment.c5a16f371681b925}", "note": "@{desktop.main.fragment.ab37c414ec9a8d61}",
			"items": [["gdp_real_exports", "@{desktop.main.fragment.f40004d6f60d7d71}", "num", TEAL],
				["gdp_real_imports", "@{desktop.main.fragment.2579b48ed1b464f6}", "num", BLUE]]},
	],
	"labor": [
		{"type": "employment_sectors", "title": "SECTORS · @{desktop.main.fragment.26ffdab120ffd9cc}", "note": "@{desktop.main.fragment.6f268293effa1817}+@{desktop.main.fragment.f4f2215f9f6f1312} FTE"},
		{"type": "labor_flows", "title": "FLOWS · @{desktop.main.fragment.0adcf6385611efe5}", "note": "@{desktop.main.fragment.73ec58443ed15263}"},
		{"type": "age_participation", "title": "LFPR · @{desktop.main.fragment.3d27a0e314776ffa}", "note": "@{desktop.main.fragment.af1f1fc6f61258c9} · @{desktop.main.fragment.d27dcbef56e42308} 18–64"},
	],
	"prices_money": [
		{"type": "line", "title": "RATES · @{desktop.main.fragment.f7fae8c95c113488}", "note": "@{desktop.main.fragment.3b79b6780fb98266}",
			"items": [["inflation", "@{desktop.main.fragment.b43cd47df5c0171c}", "pt", PURPLE],
				["policy_rate", "@{desktop.main.fragment.8003f5e9f9c4a87f}", "pt", TEAL],
				["wage_inflation", "@{desktop.main.fragment.4b3c17787792a6d9}", "pt", AMBER]]},
		{"type": "line", "title": "PURCHASING POWER · @{desktop.main.fragment.34fd0abe3a421640}", "note": "@{desktop.main.fragment.86f2998dca14febd}=100", "indexed": true,
			"items": [["price_index", "@{desktop.main.fragment.89c07894f37c4102}", "idx", BLUE],
				["real_wage", "@{desktop.main.fragment.f0106af3d7386760}", "idx", TEAL],
				["avg_markup", "@{desktop.main.fragment.ba19e19b3ae33520}", "idx", PURPLE]]},
		{"type": "columns", "title": "STANCE · @{desktop.main.fragment.41819d902ee9503e}", "note": "@{desktop.main.fragment.910c3e2401a48566}",
			"items": [["inflation", "@{desktop.main.fragment.b43cd47df5c0171c}", "pt", PURPLE],
				["policy_rate", "@{desktop.main.fragment.8003f5e9f9c4a87f}", "pt", TEAL],
				["wage_inflation", "@{desktop.main.fragment.4b3c17787792a6d9}", "pt", AMBER]]},
	],
	"fiscal": [
		{"type": "fiscal_flow", "title": "BUDGET MAP · @{desktop.main.fragment.13f77cede622f7f0}", "note": "@{desktop.main.fragment.14d8f71e5d5fde02}"},
		{"type": "line", "title": "DEBT · @{desktop.main.fragment.57a846a1c87ca9a3}", "note": "@{desktop.main.fragment.86f2998dca14febd}=100", "indexed": true,
			"items": [["gov_debt", "@{desktop.main.fragment.8d6b59cfe9288ceb}", "num", BLUE],
				["gov_debt_to_gdp", "@{desktop.main.fragment.095b45ce7df514df}/GDP", "pct", AMBER]]},
		{"type": "columns", "title": "BUDGET · @{desktop.main.fragment.d8f464c2d30f134e}", "note": "@{desktop.main.fragment.600c022e64747c44}",
			"items": [["tax_total", "@{desktop.main.fragment.653e331c54b9563e}", "num", TEAL],
				["gov_spending", "@{desktop.main.fragment.e679096865859f36}", "num", BLUE],
				["benefit_paid", "@{desktop.main.fragment.ae7c4c83caeb18a5}", "num", PURPLE],
				["gov_deficit", "@{desktop.main.fragment.7865b21012629320}", "num", AMBER]]},
	],
	"banking_credit": [
		{"type": "bank_balance", "title": "BALANCE SHEET · @{desktop.main.fragment.27bd9f30488410e8}", "note": "@{desktop.main.fragment.a8076a5ef01d06eb} · @{desktop.main.fragment.568f506a5c1d51e3} · @{desktop.main.fragment.baadb5544e4943ac}"},
		{"type": "line", "title": "STRESS · @{desktop.main.fragment.242d40b5790eac52}", "note": "@{desktop.main.fragment.0527fff25394cf12}",
			"items": [["total_debt_service_ratio", "@{desktop.main.fragment.11efcd8dc599ab71}", "pct", AMBER],
				["interbank_rate", "@{desktop.main.fragment.46e9053149aff7d2}", "pt", PURPLE],
				["writeoffs", "@{desktop.main.fragment.8570c6a44500ff6b}", "num", RED]]},
		{"type": "columns", "title": "CREDIT MIX · @{desktop.main.fragment.d348bec71ebaec09}", "note": "@{desktop.main.fragment.236e7e8fbc52f5f2}",
			"items": [["firm_debt_total", "@{desktop.main.fragment.409d0719010a46ee}", "num", TEAL],
				["household_debt_total_observed", "@{desktop.main.fragment.22aed2fc142d29f0}", "num", BLUE],
				["new_loans_total", "@{desktop.main.fragment.f56a21f92c51af70}", "num", GREEN],
				["bank_realized_credit_losses", "@{desktop.main.fragment.1dcd23337a1a0440}", "num", RED]]},
		{"type": "columns", "title": "SYSTEM · @{desktop.main.fragment.7d125a25384f8b70}", "note": "@{desktop.main.fragment.14c900d46c623a10}",
			"items": [["banks_alive", "@{desktop.main.fragment.6ebfefd41ab773a3}", "num", TEAL],
				["bank_births", "@{desktop.main.fragment.ba92ba26ea9364b4}", "num", GREEN],
				["bank_deaths", "@{desktop.main.fragment.498e1d59b4d787ee}", "num", AMBER],
				["n_bank_failures", "@{desktop.main.fragment.28384d7afd2e4fa6}", "num", RED],
				["interbank_volume", "@{desktop.main.fragment.fa97e5a35b98c592}", "num", BLUE],
				["interbank_contagion_loss", "@{desktop.main.fragment.171a142aed27428d}", "num", PURPLE]]},
	],
	"debt_risk": [
		{"type": "line", "title": "LEVERAGE · @{desktop.main.fragment.e38b8ddfc30f08f2}", "note": "@{desktop.main.fragment.9fa47bdcf5cd1adc}",
			"items": [["household_debt_total", "@{desktop.main.fragment.d2cef874cd4f31ad}", "num", BLUE],
				["firm_debt_total", "@{desktop.main.fragment.e011facc0e2e08e2}", "num", TEAL]]},
		{"type": "line", "title": "SERVICE · @{desktop.main.fragment.b7c861c177e00379}", "note": "@{desktop.main.fragment.abc939e2ca913882}",
			"items": [["household_contractual_debt_service_due", "@{desktop.main.fragment.fa871132ba185e37}", "num", BLUE],
				["household_debt_service_reserved", "@{desktop.main.fragment.4a0204a109e960f9}", "num", GREEN],
				["household_interest_arrears_closing", "@{desktop.main.fragment.734552749b99fbad}", "num", RED],
				["bank_realized_credit_losses", "@{desktop.main.fragment.ba26d799bd4f7004}", "num", AMBER]]},
		{"type": "bars", "title": "CONCENTRATION · @{desktop.main.fragment.23f435a95808071c}", "note": "Gini @{desktop.main.fragment.749e9657ca6cafb1}10%@{desktop.main.fragment.a81ca4bf0f3d9803}",
			"items": [["household_debt_gini", "@{desktop.main.fragment.d2cef874cd4f31ad} Gini", "idx", BLUE],
				["household_debt_top10_share", "@{desktop.main.fragment.a27dc251eadd7423}10%", "pct", PURPLE],
				["firm_debt_gini", "@{desktop.main.fragment.e011facc0e2e08e2} Gini", "idx", TEAL],
				["firm_debt_top10_share", "@{desktop.main.fragment.2b9870412a5a0a08}10%", "pct", AMBER]]},
		{"type": "columns", "title": "DISTRESS · @{desktop.main.fragment.dcdec027dcdab463}", "note": "@{desktop.main.fragment.f3d18b09d9d6b53c}",
			"items": [["new_loans", "@{desktop.main.fragment.49607c540f0456c4}", "num", GREEN],
				["hh_bankruptcies", "@{desktop.main.fragment.8063e9732b41f137}", "num", RED],
				["debt_service_to_nominal_gdp", "@{desktop.main.fragment.041d6a395228b3a4}/GDP", "pct", AMBER],
				["total_debt_service_to_nominal_gdp", "@{desktop.main.fragment.c417610326355e77}/GDP", "pct", PURPLE]]},
		{"type": "line", "title": "ARREARS LEDGER · @{desktop.main.fragment.d8179e21e8e72929}", "note": "@{desktop.main.fragment.141d799724f2713d}",
			"items": [["household_interest_arrears_opening", "@{desktop.main.fragment.ef419d680060beee}", "num", AMBER],
				["household_interest_arrears_extinguished", "@{desktop.main.fragment.6904831f716678f7}", "num", GREEN],
				["household_interest_arrears_in_goods_reservation", "@{desktop.main.fragment.fda24ddca3af8794}", "num", BLUE],
				["household_interest_arrears_closing", "@{desktop.main.fragment.734552749b99fbad}", "num", RED],
				["household_interest_arrears_stock_flow_residual", "@{desktop.main.fragment.cc9890fbcb181918}", "num", PURPLE]]},
	],
	"capital_markets": [
		{"type": "firm_bubbles", "title": "VALUATION MAP · @{desktop.main.fragment.a90828d709ed8ba5}", "note": "@{desktop.main.fragment.b22bf69bcd81f36f} Q · @{desktop.main.fragment.63338b74fc190a9a} · @{desktop.main.fragment.b4b35dae92ac2997}=@{desktop.main.fragment.7dc0b3b746b81556}"},
		{"type": "line", "title": "VALUATION · @{desktop.main.fragment.170e26bacb3d5bc3}", "note": "@{desktop.main.fragment.754cd05217e9a89c}",
			"items": [["tobin_q_mean", "@{desktop.main.fragment.262b4d2f27d039c7} Q", "idx", TEAL],
				["tobin_q_dispersion", "Q @{desktop.main.fragment.948ba2504cb08ba8}", "idx", PURPLE],
				["equity_turnover", "@{desktop.main.fragment.a071a060fcb264ca}", "idx", AMBER]]},
		{"type": "bars", "title": "OWNERSHIP · @{desktop.main.fragment.07dba4f6b3912e92}", "note": "@{desktop.main.fragment.a81ca4bf0f3d9803} / Gini",
			"items": [["equity_wealth_share", "@{desktop.main.fragment.3ff371748c070975}", "pct", TEAL],
				["equity_ownership_gini", "@{desktop.main.fragment.2e4d457612d85ab9}", "idx", PURPLE],
				["hh_wealth_gini_incl_equity", "@{desktop.main.fragment.6ab21b6833e66390}", "idx", BLUE]]},
	],
	"housing": [
		{"type": "line", "title": "PRICE · @{desktop.main.fragment.650fb49c749dccc7}", "note": "@{desktop.main.fragment.86f2998dca14febd}=100", "indexed": true,
			"items": [["house_price", "@{desktop.main.fragment.be473d3e46321147}", "num", Color("8a6b50")],
				["rent_level", "@{desktop.main.fragment.b790048a0e59a14b}", "num", TEAL],
				["housing_pti_ratio", "@{desktop.main.fragment.781f9eb2349a4802}", "idx", AMBER],
				["rent_burden_ratio", "@{desktop.main.fragment.d21d3161521657c3}", "pct", PURPLE]]},
		{"type": "columns", "title": "LIQUIDITY · @{desktop.main.fragment.5bfd929ac658c574}", "note": "@{desktop.main.fragment.d5e9133e94b8d01a}",
			"items": [["housing_listings", "@{desktop.main.fragment.5be5e24a05937b55}", "num", BLUE],
				["housing_sales_session", "@{desktop.main.fragment.93ce2badb17869b2}", "num", GREEN],
				["housing_tom", "@{desktop.main.fragment.f4afb04435d463c6}", "num", AMBER],
				["housing_forced_share", "@{desktop.main.fragment.afa139cd755cd23b}", "pct", RED]]},
		{"type": "columns", "title": "MORTGAGE · @{desktop.main.fragment.1c75aae141ab0632}", "note": "@{desktop.main.fragment.692c7fb911adba8b}",
			"items": [["mortgage_count", "@{desktop.main.fragment.3c6a7acecf4451a4}", "num", BLUE],
				["mortgage_balance_total", "@{desktop.main.fragment.a26affc6332b8144}", "num", TEAL],
				["mortgage_originated_tick", "@{desktop.main.fragment.4fc00e8dc86f24fe}", "num", GREEN],
				["foreclosures_total", "@{desktop.main.fragment.52fa2429d1a05e4f}", "num", RED]]},
		{"type": "bars", "title": "TENURE · @{desktop.main.fragment.51c9bc955d509b23}", "note": "@{desktop.main.fragment.44154c82a927f813}",
			"items": [["homeowner_share", "@{desktop.main.fragment.b2bde5d2fcc6341d}", "pct", TEAL],
				["tenant_share", "@{desktop.main.fragment.c3bd4c05350df5f0}", "pct", BLUE],
				["rental_vacancies", "@{desktop.main.fragment.e63722e589416df0}", "num", AMBER],
				["landlord_count", "@{desktop.main.fragment.8221b923742482b6}", "num", PURPLE]]},
		{"type": "columns", "title": "SUPPLY · @{desktop.main.fragment.5967b400dce3b5fc}", "note": "@{desktop.main.fragment.1aac84093147af25}",
			"items": [["dwellings_built_total", "@{desktop.main.fragment.01d8309fd2e6aa82}", "num", GREEN],
				["builder_wip_units", "@{desktop.main.fragment.ac099cd82fd7a4dd}", "num", BLUE],
				["builder_inventory_units", "@{desktop.main.fragment.50b26f1e5bac07be}", "num", AMBER],
				["permits_used_year", "@{desktop.main.fragment.a8ddb3bc89cb92bf}", "num", PURPLE],
				["builder_employment", "@{desktop.main.fragment.adc30fd39693c010}", "num", TEAL]]},
	],
	"energy": [
		{"type": "energy_flow", "title": "FLOW · @{desktop.main.fragment.db9d551eec15c4ff}", "note": "@{desktop.main.fragment.76ab7d3b41f2326d} → @{desktop.main.fragment.f04b061471b1fd16}/@{desktop.main.fragment.cdfd0b34e4918648} → @{desktop.main.fragment.780c5fd5b10533dc}"},
		{"type": "line", "title": "COST · @{desktop.main.fragment.26e8fdddbbac4acd}", "note": "@{desktop.main.fragment.86f2998dca14febd}=100", "indexed": true,
			"items": [["energy_price", "@{desktop.main.fragment.264c2c4114eaf977}", "idx", Color("b0641f")],
				["energy_cost_share", "@{desktop.main.fragment.77e8df2db61c3f46}", "pct", RED],
				["e_capacity_utilization", "@{desktop.main.fragment.20761c8ad29f5f78}", "pct", TEAL]]},
		{"type": "columns", "title": "SECURITY · @{desktop.main.fragment.cdbd84f35de4ad86}", "note": "@{desktop.main.fragment.4bc054cd9f1422fc}",
			"items": [["energy_produced", "@{desktop.main.fragment.ad7e8b52525b699b}", "num", GREEN],
				["energy_used", "@{desktop.main.fragment.0214e71438a47cd0}", "num", AMBER],
				["energy_stock_total", "@{desktop.main.fragment.b5d09817d3f6de41}", "num", BLUE],
				["spr_stock", "@{desktop.main.fragment.ba246184da7bbff6}", "num", PURPLE]]},
	],
	"external": [
		{"type": "line", "title": "TRADE · @{desktop.main.fragment.9a50012849bdbedd}", "note": "@{desktop.main.fragment.178d628572b9b176}",
			"items": [["import_value", "@{desktop.main.fragment.1ada65455c2895ba}", "num", BLUE],
				["export_delivered_volume", "@{desktop.main.fragment.4db5da905824b9bb}", "num", TEAL]]},
		{"type": "line", "title": "BALANCE · @{desktop.main.fragment.95e89b0cb919a37e}", "note": "@{desktop.main.fragment.fc791da83e1b0a3e}",
			"items": [["current_account", "@{desktop.main.fragment.d5ecdc812e1a4f41}", "num", AMBER],
				["nfa", "@{desktop.main.fragment.2a34b4aa4ee8731a}", "num", PURPLE]]},
		{"type": "line", "title": "FX · @{desktop.main.fragment.ce2c631e2aa40c82}", "note": "@{desktop.main.fragment.499646ba8cbdeaac}/@{desktop.main.fragment.e060731f1876c318} · @{desktop.main.fragment.11929e9141d1541d}=100", "indexed": true,
			"items": [["e", "@{desktop.main.fragment.57ef2c45ef260ee3}", "idx", Color("4a6fa5")]]},
		{"type": "columns", "title": "MOBILITY · @{desktop.main.fragment.a397915ef9858b76}", "note": "@{desktop.main.fragment.a72de3cb6980daf4}",
			"items": [["migrant_stock", "@{desktop.main.fragment.04ebb06f0c2cfcab}", "num", TEAL],
				["remittances", "@{desktop.main.fragment.82bd68e0e3dd55cd}", "num", BLUE],
				["tariff_rev", "@{desktop.main.fragment.897c0b9c6be037ca}", "num", AMBER]]},
	],
	"distribution": [
		{"type": "lorenz", "title": "LORENZ · @{desktop.main.fragment.9f890afd9118957a}", "note": "@{desktop.main.fragment.b84006c8530d9d6d}"},
		{"type": "line", "title": "WELFARE · @{desktop.main.fragment.6309658265c64df2}", "note": "@{desktop.main.fragment.86f2998dca14febd}=100", "indexed": true,
			"items": [["welfare_log", "@{desktop.main.fragment.3ec8e057df1ade4c}", "idx", GREEN],
				["wage_p90_p10_ratio", "@{desktop.main.fragment.11547412b4531891} P90/P10", "idx", AMBER],
				["bottom10_consumption", "@{desktop.main.fragment.3f049887991b880c}10%@{desktop.main.fragment.80716311485ac4f9}", "num", BLUE]]},
		{"type": "deciles", "title": "DECILES · @{desktop.main.fragment.d576045df3ccfbc8}", "note": "@{desktop.main.fragment.808859bb14950fd4}"},
	],
	"population": [
		{"type": "pyramid", "title": "AGE · @{desktop.main.fragment.09e6d0c410d19e23}", "note": "@{desktop.main.fragment.4cf5a5e165a12a7d} · @{desktop.main.fragment.86b7de3883114c91}"},
		{"type": "line", "title": "DEMOGRAPHY · @{desktop.main.fragment.2d75d06c3a9eae54}", "note": "@{desktop.main.fragment.bc7ad4598ad4f5f9}",
			"items": [["births_tick", "@{desktop.main.fragment.7e3781ea90e9583f}", "num", TEAL],
				["deaths_tick", "@{desktop.main.fragment.82d3130fa58281ea}", "num", RED],
				["marriages_tick", "@{desktop.main.fragment.ed7486a07a29fff1}", "num", BLUE],
				["divorces_tick", "@{desktop.main.fragment.93619bc860a58a44}", "num", AMBER]]},
		{"type": "columns", "title": "DEPENDENCY · @{desktop.main.fragment.39221a8a5eee0200}", "note": "@{desktop.main.fragment.f2720a242b54a62e}",
			"items": [["child_population", "@{desktop.main.fragment.5246f67f9da53c66}", "num", BLUE],
				["working_age_population", "@{desktop.main.fragment.31ec003979b97e3a}", "num", TEAL],
				["elder_population", "@{desktop.main.fragment.2e977476095271e4}", "num", PURPLE],
				["dependency_ratio", "@{desktop.main.fragment.23dca1a6ef086b98}", "pct", AMBER]]},
		{"type": "line", "title": "RATES · @{desktop.main.fragment.105b422e4d1cf07e}", "note": "@{desktop.main.fragment.b1957f97daf9eb4c}",
			"items": [["net_population_growth_rate_annualized", "@{desktop.main.fragment.706834beaa8804e6}", "pct", GREEN],
				["birth_rate_per_1000_annualized", "@{desktop.main.fragment.f2dd829db4c69625}", "per_thousand", TEAL],
				["death_rate_per_1000_annualized", "@{desktop.main.fragment.9ba99193e3c4aa80}", "per_thousand", RED]]},
		{"type": "bars", "title": "GENERATIONS · @{desktop.main.fragment.c88d055d85727e88}", "note": "@{desktop.main.fragment.f2e5b469194e698b}",
			"items": [["child_share", "@{desktop.main.fragment.5246f67f9da53c66}", "pct", BLUE],
				["adult_share", "@{desktop.main.fragment.5558934a5a01277d}", "pct", TEAL],
				["elder_share", "@{desktop.main.fragment.e7118dbe67b3bdab}", "pct", PURPLE]]},
		{"type": "columns", "title": "CONSUMPTION · @{desktop.main.fragment.4813e6543b235b00}", "note": "@{desktop.main.fragment.4a793e834b02f883}",
			"items": [["child_median_consumption", "@{desktop.main.fragment.5246f67f9da53c66}", "num", BLUE],
				["adult_median_consumption", "@{desktop.main.fragment.5558934a5a01277d}", "num", TEAL],
				["elder_median_consumption", "@{desktop.main.fragment.e7118dbe67b3bdab}", "num", PURPLE]]},
	],
	"firms": [
		{"type": "sector_matrix", "title": "SECTORS · @{desktop.main.fragment.f57935012ee94136}", "note": "@{desktop.main.fragment.2d9801c466a2f699} · @{desktop.main.fragment.7085566cb9242aca} · @{desktop.main.fragment.59d94bccf0d498e3}"},
		{"type": "line", "title": "DEMOGRAPHY · @{desktop.main.fragment.983dd9e4a834ed1e}", "note": "@{desktop.main.fragment.04c164cd851ed432}",
			"items": [["firm_count_c", "@{desktop.main.fragment.4fe95cbc41c25b8c}", "num", TEAL],
				["births", "@{desktop.main.fragment.9bc8563025adf19f}", "num", GREEN],
				["deaths", "@{desktop.main.fragment.f7983f7143cd8b68}", "num", RED]]},
		{"type": "columns", "title": "ACTIVITY · @{desktop.main.fragment.8e0e026b1d83ef81}", "note": "@{desktop.main.fragment.77e69321da9da085}",
			"items": [["n_firms_producing", "@{desktop.main.fragment.efc42eb363bcca9a}", "num", TEAL],
				["n_firms_selling", "@{desktop.main.fragment.0d5d67283894ad64}", "num", BLUE],
				["n_firms_borrowing", "@{desktop.main.fragment.c92d44297f50187c}", "num", AMBER],
				["sector_switches", "@{desktop.main.fragment.e0f3622a02bcec85}", "num", PURPLE]]},
		{"type": "bars", "title": "CONCENTRATION · @{desktop.main.fragment.c5d7ef899ce51618}", "note": "@{desktop.main.fragment.3e31215e5ffe8f69} Pareto @{desktop.main.fragment.989c3ad6e54fb7e2}",
			"items": [["firm_size_gini_output", "@{desktop.main.fragment.3dbf2e1f70fed8ba} Gini", "idx", PURPLE],
				["firm_size_top_share_output", "@{desktop.main.fragment.7646de8d4bac93e9}", "pct", AMBER],
				["firm_size_pareto_slope", "Pareto @{desktop.main.fragment.989c3ad6e54fb7e2}", "idx", BLUE],
				["sector_switch_capital", "@{desktop.main.fragment.9ff43644152df958}", "num", RED]]},
	],
}

const WORLD_COMPARE := [
	["real_output", "@{desktop.main.fragment.60b6b37831c29bca}", "num"], ["unemployment_rate", "@{desktop.main.fragment.4546b3d41818bdbf}", "pct"],
	["inflation", "@{desktop.main.fragment.b43cd47df5c0171c}", "pt"], ["price_index", "@{desktop.main.fragment.89c07894f37c4102}", "idx"],
	["avg_wage", "@{desktop.main.fragment.fdc477056b2d48f6}", "num"], ["policy_rate", "@{desktop.main.fragment.8003f5e9f9c4a87f}", "pt"],
]

const RANK_METRICS := [
	["score", "@{desktop.main.fragment.4a0d4edef9c7bfdd}", "score", false],
	["real_output", "GDP", "num", false], ["unemployment_rate", "@{desktop.main.fragment.4546b3d41818bdbf}", "pct", true],
	["inflation", "@{desktop.main.fragment.b43cd47df5c0171c}", "pt", true], ["avg_wage", "@{desktop.main.fragment.11547412b4531891}", "num", false],
]

var _client
var _outbox: Array = []
var _active_command: Dictionary = {}
var _snapshot: Dictionary = {}
var _schemas: Dictionary = {}          # seat -> schema dict
var _lever_info: Dictionary = {}       # lever -> lever dict (all seats merged)
var _lever_group: Dictionary = {}      # lever -> decision_group
var _active_seat := "treasury"
var _active_group := ""                #  Second thematic page title (empty = first page of the seat)
var _expanded_lever := ""              #  accordion: currently expanding knob
var _search := ""
var _policy_scope := "meeting"         #  meeting all; automatically showing all at close of session
var _edits: Dictionary = {}            #  lever-> Local Editor Value (not in basket)
var _cart: Array = []                  # [{lever, from, to, value, group}]
var _perm_cache: Dictionary = {}       #  Last - > displayed action (for closed sessions)
var _release_hist: Dictionary = {}     # sid -> [{v, at}]
var _playing := false
var _speed := 5
var _mode := "interactive"
var _control_mode := "controller"
var _tab := "focus"
var _rank_by := "score"
var _score_country := 0               #  World View National Performance Radar Current Selected Economy Body
var _goto_panel_group := ""            #  Indicator Panorama Current Independent Page Signing; core card hits directly
var _household_selected := -1         #  Current selected family page
var _person_selected := -1            #  Family members located in a deep enterprise chain id
var _household_search := ""           #  Family number / Member number filter
var _household_sort := "net_worth"    # net_worth | members | debt
var _firm_selected := ""              #  Current selected business page
var _firm_search := ""                #  Enterprise / Department / employee sift Select
var _firm_sort := "revenue"           # revenue | earnings | assets
var _stock_selected := ""             #  Stock market master chart current securities; empty = composite index
var _stock_search := ""               #  Line Sheet Code / Board Filter
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
var _last_release_at: Dictionary = {}   #  Sid - > restored at
var _crisis_was_visible := false
var _scroll_mem: Dictionary = {}        # key -> scroll_vertical
var _start_menu: Control
var _new_game_draft: Dictionary = {}
var _new_game_pending := false
var _m11_adapter
var _entity_requested: Dictionary = {}


func _ready() -> void:
	_sans = SystemFont.new()
	_sans.font_names = PackedStringArray([
		"Hiragino Sans GB", "STHeiti", "Arial Unicode MS", "Helvetica Neue"])
	_mono = SystemFont.new()
	_mono.font_names = PackedStringArray(["Menlo", "Monaco"])
	_mono.fallbacks = [_sans]
	_build_theme()
	_build_ui()
	_m11_adapter = M11FrontendAdapterScript.new()
	if OS.get_environment("MACRO_SIM_SKIP_START_MENU") != "1":
		_ensure_start_menu()
	_client = SimulationClientScript.new()
	add_child(_client)
	_client.connected.connect(_on_connected)
	_client.disconnected.connect(func() -> void:
		_set_text("conn", "@{desktop.main.fragment.1f0ac6953e0411c0} · @{desktop.main.fragment.ab7e3afbecbdafbe}"))
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
			if _awaiting() and not _free_policy_enabled():
				_show_hint("@{desktop.main.fragment.e864ee0d87b36635}:@{desktop.main.fragment.4b259599fea7f435}")
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
		"title": "@{desktop.main.fragment.e34e61a243bec5e1}",
		"body": "@{desktop.main.fragment.de760ef20490995d}",
		"note": "@{desktop.main.fragment.916a18b7846abb04}",
		"on_cancel": func() -> void: _playing = was_playing,
		"on_yes": _return_to_main_menu,
	}
	_render()


func _return_to_main_menu() -> void:
	_playing = false
	_outbox.clear()
	if not _snapshot.is_empty():
		_send({"command": "close_session"})
		_snapshot.clear()
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


#  Synchronization helper.
func _send(command: Dictionary) -> void:
	_outbox.append(command)
	_pump()


func _pump() -> void:
	if _client == null or _client.busy or _outbox.is_empty():
		return
	_active_command = _outbox.pop_front()
	_client.send_command(_active_command)


func _on_connected() -> void:
	_set_text("conn", "@{desktop.main.fragment.94090d9c9a2ca568}")
	_send({"command": "hello"})


func _on_response(response: Dictionary) -> void:
	var result: Dictionary = response.get("result", {})
	var command_name := str(_active_command.get("command", ""))
	var payload: Dictionary = {}
	if command_name == "get_schema":
		payload = _m11_adapter.schema_payload(result)
		_control_mode = str(payload.get("control_mode", _control_mode))
		_schemas = payload.get("seats", {})
		_index_schema()
		if _start_menu != null and _start_menu.has_method("set_policy_schemas"):
			_start_menu.call("set_policy_schemas", _start_menu_policy_schemas())
	elif command_name == "new_game":
		_m11_adapter.reset(result, _new_game_draft)
		payload = _m11_adapter.apply_projection(result.get("projection", {}))
		_new_game_pending = false
		_reset_client_for_new_game(payload)
		_outbox.append({"command": "get_schema"})
		_snapshot = payload
	elif command_name == "entity_page":
		payload = _m11_adapter.apply_entity_result(result)
		_snapshot = payload
		var entity_kind := str(result.get(
			"kind", _active_command.get("kind", "")))
		_entity_requested.erase(entity_kind)
	elif result.has("projection"):
		payload = _m11_adapter.apply_projection(result.get("projection", {}))
		_snapshot = payload
	elif command_name == "snapshot":
		payload = _m11_adapter.apply_projection(result)
		_snapshot = payload
	elif command_name == "load_slot":
		_m11_adapter.reset(result, {})
		payload = _m11_adapter.apply_projection(result.get("projection", {}))
		_reset_client_for_new_game(payload)
		_snapshot = payload
		_outbox.append({"command": "get_schema"})
	if not payload.is_empty():
		_control_mode = str(payload.get("control_mode", _control_mode))
		_reconcile_free_policy_queue()
		_ingest_releases()
		_cache_permitted()
		var splash := _n.get("splash") as Control
		if splash != null and splash.visible:
			var stw2 := create_tween()
			stw2.tween_property(splash, "modulate:a", 0.0, 0.35)
			stw2.tween_callback(func() -> void:
				splash.visible = false)
		var verdict: Variant = result.get("decision")
		if verdict is Dictionary and not (verdict as Dictionary).is_empty():
			_show_verdict(verdict)
		if _playing and _awaiting() and _mode != "realtime" \
				and not _free_policy_enabled():
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
	_entity_requested.clear()


func _on_request_failed(message: String) -> void:
	var failed_new_game := str(_active_command.get("command", "")) == "new_game"
	if _new_game_pending and failed_new_game:
		_new_game_pending = false
		if _start_menu != null and _start_menu.has_method("restore_after_launch_error"):
			_start_menu.call("restore_after_launch_error", message)
	if str(_active_command.get("command", "")) == "entity_page":
		_entity_requested.erase(str(_active_command.get("kind", "")))
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
	var texture := get_viewport().get_texture()
	if texture == null:
		push_error("Automated capture requires a rendering backend.")
		get_tree().quit(2)
		return
	var image := texture.get_image()
	if image == null:
		push_error("Automated capture could not read the viewport texture.")
		get_tree().quit(2)
		return
	image.save_png(path)
	get_tree().quit(0)


func _on_play_tick() -> void:
	if not _playing or (_demo_crisis and not _free_policy_enabled()):
		return
	if _awaiting() and not _free_policy_enabled():
		if _mode == "realtime" and not _emergency():
			for ctx: Dictionary in _contexts():
				_send({"command": "resolve_context",
					"context_id": str(ctx.get("context_id")), "actions": []})
		return
	_send({"command": "advance", "ticks": _speed})


#  Synchronization helper.
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
	##  Build theme pages and append ungrouped levers to the final page.
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
		out.append({"name": "@{desktop.main.fragment.d2909f1647e7c891}", "levers": leftover})
	return out


func _seat_groups(seat: String) -> Dictionary:
	var out: Dictionary = {}
	for lever: Dictionary in _schemas.get(seat, {}).get("levers", []):
		var g := str(lever.get("decision_group", "@{desktop.main.fragment.d2909f1647e7c891}"))
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


func _free_policy_enabled() -> bool:
	return _control_mode == "free_policy" \
		or str(_snapshot.get("control_mode", "")) == "free_policy"


func _reconcile_free_policy_queue() -> void:
	if not _free_policy_enabled() or _cart.is_empty():
		return
	var pending: Array = _snapshot.get("free_policy", {}).get("actions", [])
	if not pending.is_empty():
		return
	var values: Dictionary = _snapshot.get("policy_values", {})
	for item: Dictionary in _cart:
		var name := str(item.get("lever", ""))
		if not values.has(name) or values[name] != item.get("value"):
			return
	_cart.clear()
	_edits.clear()


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


func _domain_text(domain: String, value_id: String, fallback := "") -> String:
	var safe_fallback := fallback
	if safe_fallback.is_empty():
		safe_fallback = value_id.replace("_", " ").capitalize()
	return LocaleCatalogScript.text(
		"domain.%s.%s" % [domain, value_id], safe_fallback)


func _row_domain_text(
		row: Dictionary,
		domain: String,
		id_field: String,
		legacy_field: String,
		fallback_id: String) -> String:
	var value_id := str(row.get(id_field, row.get(legacy_field, fallback_id)))
	return _domain_text(domain, value_id)


func _sector_text(row: Dictionary) -> String:
	return _row_domain_text(row, "sector", "sector_id", "sector", "unknown")


func _condition_text(row: Dictionary) -> String:
	return _row_domain_text(
		row, "condition", "condition_id", "condition", "unknown")


func _panel_group_name(group_id: String) -> String:
	for group: Dictionary in PANEL_GROUPS:
		if str(group.get("id", "")) == group_id:
			return LocaleCatalogScript.resolve(str(group.get("name", group_id)))
	return group_id


func _permission_reason(reason_code: String) -> String:
	if reason_code.begins_with("missing_capability:"):
		var capability := reason_code.trim_prefix("missing_capability:")
		return "@{desktop.main.fragment.ceec702b8e211824}%s”" % str(CAPABILITY_CN.get(capability, capability))
	if reason_code.begins_with("missing_world_capability:"):
		var capability := reason_code.trim_prefix("missing_world_capability:")
		return "@{desktop.main.fragment.57f5f4990c6d6098}%s”" % str(CAPABILITY_CN.get(capability, capability))
	if reason_code.begins_with("disabled_prerequisite:"):
		var prerequisite := reason_code.trim_prefix("disabled_prerequisite:")
		return "@{desktop.main.fragment.d8b96c90a864f591}%s”" % _cn(prerequisite)
	return {
		"pending_conflict": "@{desktop.main.fragment.93e4c72a5d75be63}",
		"minimum_hold": "@{desktop.main.fragment.bf11f06e60b7bf5f} / @{desktop.main.fragment.9cf1671304bdf004}",
		"admin_capacity_exceeded": "@{desktop.main.fragment.76db622d3552f2af}",
		"joint_constraint:peg_unavailable": "@{desktop.main.fragment.2e173fb06567aafd}",
		"joint_constraint:no_valid_peg_anchor": "@{desktop.main.fragment.e6e8cbeca1195a9c}",
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
	if _free_policy_enabled():
		_sync_free_policy_queue()
	_render()


func _set_policy_edit(lever: Dictionary, value: Variant) -> void:
	var lever_name := str(lever.get("name"))
	_edits[lever_name] = value
	if _free_policy_enabled():
		# Free-policy edits are commands, not proposals. Keep the current tick
		# immutable and replace the complete next-boundary batch immediately.
		_add_to_cart(lever, _lever_current(lever, {}))
	else:
		_render()


func _stage_lever_edit(lever: Dictionary, value: Variant) -> void:
	var lever_name := str(lever.get("name"))
	if _free_policy_enabled():
		_set_policy_edit(lever, value)
		return
	var semantics := str(lever.get("semantics",
		lever.get("effective_semantics", "")))
	if semantics.contains("transition"):
		_confirm = {
			"title": "@{desktop.main.fragment.e04581fb23040b7a}",
			"body": "@{desktop.main.fragment.2676b2e92c3452ff}%s@{desktop.main.fragment.262098faceaa38b6}%s@{desktop.main.fragment.9a4f9eb9e97abdff}" % [
				_cn(lever_name), _lever_value_text(lever, value)],
			"note": "@{desktop.main.fragment.40d46f4142faec44} · @{desktop.main.fragment.b1c27820fec23edb} · @{desktop.main.fragment.da348369158b4e9e} %d @{desktop.main.fragment.cccf58ef16e9afe4}" % int(lever.get("implementation_lag", 0)),
			"on_yes": func() -> void:
				_set_policy_edit(lever, value),
		}
		_render()
	else:
		_set_policy_edit(lever, value)


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
	#  Keep an edited proposal visible when returning from the proposal basket.
	if _context_for_group(str(info.get("decision_group", ""))).is_empty():
		_policy_scope = "all"
	_render()


func _country_name(i: int) -> String:
	var countries: Array = _world().get("countries", [])
	if i >= 0 and i < countries.size():
		return str((countries[i] as Dictionary).get("name", "@{desktop.main.fragment.875f07b0b3723010}%d" % i))
	return "@{desktop.main.fragment.875f07b0b3723010}%d" % i


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
	return str(GROUP_CN.get(group, "@{desktop.main.fragment.68057913cfe371f2}" if group == "emergency" else group))


func _event_title(event_type: String) -> String:
	if EVENT_TITLES.has(event_type):
		return str(EVENT_TITLES[event_type])
	if event_type.begins_with("shock_"):
		return "@{desktop.main.fragment.e692be404f47b00a}"
	if event_type.begins_with("decision_"):
		return "@{desktop.main.fragment.e45bac3986af7081}"
	if event_type.begins_with("policy_") or event_type.contains("transaction"):
		return "@{desktop.main.fragment.342fe609c72c09d8}"
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


#  Synchronization helper.
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
	#  Godot default tooltip is small and less transparent; uniform as a high-comparison float suitable for financial information.
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
	l.text = LocaleCatalogScript.resolve(text)
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
	b.text = LocaleCatalogScript.resolve(text)
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
	##  Pre-reconstruction call: records; post-reconstruction restore (delayed entry into force of one frame)
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
		(_n[key] as Label).text = LocaleCatalogScript.resolve(text)


func _fmt_val(kind: String, v: float) -> String:
	match kind:
		"pct":
			return "%.1f%%" % (v * 100.0)
		"pt":
			return LocaleCatalogScript.format(
				"desktop.format.rate_per_day", v * 100.0)
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
			return LocaleCatalogScript.format(
				"desktop.format.rate_per_day", v * 100.0)
		"price_index":
			return "%.3f" % v
		_:
			return _fmt_val("num", v)


func _cal_str(t: int) -> String:
	var year_day := t % 365
	var quarter := mini(year_day / 91, 3)
	return LocaleCatalogScript.format("desktop.calendar.full", [
		t / 365 + 1, quarter + 1, year_day - quarter * 91 + 1])


func _cal_short(t: int) -> String:
	return LocaleCatalogScript.format(
		"desktop.calendar.short", [t / 365 + 1, t % 365 + 1])


func _cal_value(value: Variant) -> String:
	var raw := str(value)
	if value is int or value is float:
		return _cal_short(int(value))
	if raw.is_valid_int():
		return _cal_short(raw.to_int())
	return "@{desktop.main.fragment.da41b98e395499be}"


#  Synchronization helper.
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
	st.add_child(_lbl("@{desktop.main.fragment.73169097f403db72}", 26, INK))
	sv.add_child(st)
	var sub := _lbl("MACRO COMMAND · @{desktop.main.fragment.2483b7077faefe1a}", 12, Color("68788b"), true)
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sv.add_child(sub)
	var spin := _Spinner.new()
	spin.custom_minimum_size = Vector2(30, 30)
	spin.pivot_offset = Vector2(15, 15)
	spin.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	sv.add_child(spin)
	var stw := create_tween().set_loops()
	stw.tween_property(spin, "rotation", TAU, 1.1).from(0.0)
	var sload := _lbl("@{desktop.main.fragment.2af295a5eea998b4} · @{desktop.main.fragment.9dd6ecef8da54cee}", 12, INK2)
	sload.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sv.add_child(sload)


func _build_header(shell: VBoxContainer) -> void:
	var hp := PanelContainer.new()
	hp.add_theme_stylebox_override("panel", _sb(PANEL, Color("dbe2ea"), 13, 10))
	shell.add_child(hp)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 14)
	hp.add_child(h)
	var menu_button := _btn("⌂  @{desktop.main.fragment.d8c47e9776cf1082}", _request_return_to_main_menu)
	menu_button.tooltip_text = "@{desktop.main.fragment.a917151f6055da74}"
	menu_button.custom_minimum_size = Vector2(90, 0)
	_n["main_menu"] = menu_button
	h.add_child(menu_button)
	h.add_child(_vdiv())
	var tbox := HBoxContainer.new()
	tbox.add_theme_constant_override("separation", 9)
	h.add_child(tbox)
	tbox.add_child(_dot(TEAL, 9.0))
	tbox.add_child(_lbl("@{desktop.main.fragment.73169097f403db72}", 17, INK))
	tbox.add_child(_lbl("MACRO COMMAND", 11, Color("68788b"), true))
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
	var conn := _lbl("@{desktop.main.fragment.ee9ebe523d4205f8}", 12, TEAL)
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
	wbx.add_child(_lbl("@{desktop.main.fragment.eddd69f83ff60cfe}", 12, AMBER))
	_n["awaitchip"] = waitp
	h.add_child(waitp)
	h.add_child(_spacer_h())
	var modes_wrap := PanelContainer.new()
	_n["modes_wrap"] = modes_wrap
	modes_wrap.add_theme_stylebox_override("panel", _sb(PANEL2, LINE, 22, 3))
	var modes := HBoxContainer.new()
	modes.add_theme_constant_override("separation", 2)
	modes_wrap.add_child(modes)
	for m: Array in [["interactive", "@{desktop.main.fragment.99f1b08f6464952c}"], ["realtime", "@{desktop.main.fragment.c69ec2ffb0db8ca4}"]]:
		var mb := Button.new()
		mb.text = m[1]
		mb.tooltip_text = "@{desktop.main.fragment.87ed126f7bd1121e}\n@{desktop.main.fragment.66bba32fb837bee4}\n@{desktop.main.fragment.4c643d2e18d8f950}"
		var mid: String = m[0]
		mb.pressed.connect(func() -> void:
			if mid == "realtime" and _mode != "realtime":
				_show_hint("@{desktop.main.fragment.00dbe842b551e866}:@{desktop.main.fragment.cf6f6acf36f45320}(@{desktop.main.fragment.a3d7d03ea4a571bd});@{desktop.main.fragment.349c7af1f9137215}")
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
	var stepb := _btn("@{desktop.main.fragment.18a29569240cf047}", func() -> void:
		if _awaiting() and not _free_policy_enabled():
			_show_hint("@{desktop.main.fragment.e864ee0d87b36635},@{desktop.main.fragment.3c1f0ce319b70d38}:@{desktop.main.fragment.6bc9059a94e3eb32};@{desktop.main.fragment.bc551cf3a4703042}")
			_render()
		else:
			_send({"command": "advance", "ticks": 1}))
	stepb.tooltip_text = "@{desktop.main.fragment.967615a6c5a8f47c}\n@{desktop.main.fragment.820e5d75acc363e6} 1 @{desktop.main.fragment.49da61ceeea2f271}\n@{desktop.main.fragment.d27c41a46f649ee3}"
	tp.add_child(stepb)
	var play := _btn("▶  @{desktop.main.fragment.c3396195e91ccdd8}", _toggle_play, true)
	play.tooltip_text = "@{desktop.main.fragment.c3396195e91ccdd8} / @{desktop.main.fragment.631f743a6244c4f5}\n@{desktop.main.fragment.f6671bd389bc80fe}"
	play.custom_minimum_size = Vector2(96, 0)
	_n["play"] = play
	tp.add_child(play)
	for s: int in SPEEDS:
		var sbn := Button.new()
		sbn.text = "%d×" % s
		sbn.add_theme_font_override("font", _mono)
		sbn.add_theme_font_size_override("font_size", 12)
		sbn.tooltip_text = "@{desktop.main.fragment.b8a29fa7b314c3ea}%d @{desktop.main.fragment.16729fb40af5af9b}\n@{desktop.main.fragment.10b775695af17455}%d" % [s, SPEEDS.find(s) + 1]
		var chosen := s
		sbn.pressed.connect(func() -> void:
			_speed = chosen
			_render())
		_n["speed_%d" % s] = sbn
		tp.add_child(sbn)
	h.add_child(transport)


func _toggle_play() -> void:
	_playing = not _playing
	if _playing and _awaiting() and _mode != "realtime" \
			and not _free_policy_enabled():
		_show_hint("@{desktop.main.fragment.ac0b38470539c75c},@{desktop.main.fragment.cbe267255ddd4d4c}:@{desktop.main.fragment.3b596b973430b48c},@{desktop.main.fragment.b0f2ab3c31ffd8b3}")
	_render()


func _build_main(shell: VBoxContainer) -> void:
	var main := HBoxContainer.new()
	main.size_flags_vertical = Control.SIZE_EXPAND_FILL
	main.add_theme_constant_override("separation", 10)
	shell.add_child(main)
	var wbp := PanelContainer.new()
	#  The policy editor is the main game, leaving a stable width for Chinese names, status and precise input.
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
	title_row.add_child(_lbl("POLICY DESK · @{desktop.main.fragment.1445d3624f03880e}", 10, INK3, true))
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
	search.placeholder_text = LocaleCatalogScript.text("desktop.free.search_placeholder")
	search.add_theme_font_size_override("font_size", 12)
	search.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 8, 6))
	search.add_theme_stylebox_override("focus", _sb(Color.WHITE, TEAL_BD, 8, 6))
	search.text_changed.connect(func(text: String) -> void:
		_search = text.strip_edges()
		_render())
	_n["search"] = search
	search_row.add_child(search)
	var scope := Button.new()
	scope.text = "@{desktop.main.fragment.fe8af2657e540cbd}"
	scope.tooltip_text = "@{desktop.main.fragment.a7d8f1624cd08199}\n@{desktop.main.fragment.7f98f9c6a3409542}"
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
	var cart_title := _lbl("@{desktop.main.fragment.788dc700d8faa6eb}", 10, INK3, true)
	_n["cart_title"] = cart_title
	crow.add_child(cart_title)
	var ccount := _lbl("0 @{desktop.main.fragment.49ccde43a1549791}", 11, Color("647585"))
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
	var submit := _btn("@{desktop.main.fragment.bed494cc5491181a}", _submit_cart, true)
	submit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_n["submit"] = submit
	actions.add_child(submit)
	var pass_b := _btn("@{desktop.main.fragment.1966f4dfc00757e5}", _submit_pass)
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
	for t: Array in [["focus", "@{desktop.main.fragment.d7a0d892505502a2}"], ["households", "@{desktop.main.fragment.a70a77c75b1dc74f}"], ["firms", "@{desktop.main.fragment.409d0719010a46ee}"],
			["stocks", "@{desktop.main.fragment.b6f19996399ce673}"],
			["panels", "@{desktop.main.fragment.6ec65d0d0d3d72e1}"], ["world", "@{desktop.main.fragment.036bf7c22dc51057}"]]:
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
	var tabnote := _lbl("X @{desktop.main.fragment.3a3bdd4b3c4f458e} = @{desktop.main.fragment.e8ff4d335dee5d55}(@{desktop.main.fragment.369421adfa2cd18a})", 10, INK3, true)
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
	head.add_child(_lbl("EVENTS · @{desktop.main.fragment.f1241a97b0821a99}", 10, INK3, true))
	head.add_child(_spacer_h())
	var filter := Button.new()
	filter.text = "@{desktop.main.fragment.f3f75c13a660d243}"
	filter.add_theme_font_size_override("font_size", 11)
	filter.tooltip_text = "@{desktop.main.fragment.c25f3537a70b2d91}\n@{desktop.main.fragment.bf4f7b0a7eae4b75} / @{desktop.main.fragment.e4257920848098bb} / @{desktop.main.fragment.375eb6ab5a1dfc56}"
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
	var ct := _lbl("@{desktop.main.fragment.f8ce4c400c738850}", 16, Color("7a2418"))
	_n["crisis_title"] = ct
	chead.add_child(ct)
	chead.add_child(_spacer_h())
	chead.add_child(_btn("@{desktop.main.fragment.11f808026b8acefb}", func() -> void:
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
	snapcol.add_child(_lbl("@{desktop.main.fragment.0373c11cfe446b07}", 10, Color("9a6a5e"), true))
	_n["crisis_snap"] = snapcol
	cbody.add_child(snapcol)
	var levcol := VBoxContainer.new()
	levcol.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	levcol.add_theme_constant_override("separation", 9)
	var lh := HBoxContainer.new()
	lh.add_theme_constant_override("separation", 8)
	lh.add_child(_lbl("@{desktop.main.fragment.bc7f5e5a2fbf6239}", 10, Color("9a6a5e"), true))
	lh.add_child(_chip("@{desktop.main.fragment.2f662f44baea6c40}", Color("a0691f"), Color(0, 0, 0, 0), AMBER_BD, 10))
	levcol.add_child(lh)
	_n["crisis_levers"] = levcol
	cbody.add_child(levcol)
	var trig := _btn("▲ @{desktop.main.fragment.bd7ddfac990b705e}", func() -> void:
		_demo_crisis = true
		_render())
	_n["crisis_trigger"] = trig
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
	var eyebrow := _lbl("POLICY INTELLIGENCE · @{desktop.main.fragment.4e0a158ede9ac602}", 9, Color("748496"), true)
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
	var modal_cancel := _btn("@{desktop.main.fragment.2cd0f3be8738a86c}", _confirm_cancel)
	_n["modal_cancel"] = modal_cancel
	mrow.add_child(modal_cancel)
	var modal_confirm := _btn("@{desktop.main.fragment.36f33adaf0942634}", _confirm_yes, true)
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


#  Synchronization helper.
func _render() -> void:
	var t := int(_snapshot.get("tick", 0))
	_set_text("cal", _cal_str(t))
	_set_text("tick", "tick %d" % t)
	var yb := _n["yearbar"] as _YearBar
	yb.frac = float(t % 365) / 365.0
	yb.queue_redraw()
	var free_policy := _free_policy_enabled()
	(_n["awaitchip"] as Control).visible = _awaiting() and not free_policy
	(_n["modes_wrap"] as Control).visible = not free_policy
	(_n["crisis_trigger"] as Control).visible = not free_policy
	var playb := _n["play"] as Button
	playb.text = "⏸  @{desktop.main.fragment.8d12fc0d4eb26021}" if _playing else "▶  @{desktop.main.fragment.c3396195e91ccdd8}"
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
		"focus": "@{desktop.main.fragment.a6ff5a6d73255807}",
		"households": "@{desktop.main.fragment.e459b9ef649fba5a} · @{desktop.main.fragment.19afc3114ec3cd82}",
		"firms": "@{desktop.main.fragment.5eb46fdbe9cbc02e} · @{desktop.main.fragment.00a6570bb25bae5b}",
		"stocks": "@{desktop.main.fragment.d43d3298be5af7a1} · @{desktop.main.fragment.3fc2012bf90922c0}",
		"panels": "@{desktop.main.fragment.a12d6b20a0cecdb9} · @{desktop.main.fragment.a45bd34388926c09}",
		"world": "@{desktop.main.fragment.80b1e81fc794712c} · @{desktop.main.fragment.26a59f85b3eb5fc4} / @{desktop.main.fragment.59831fc48b368a54} / @{desktop.main.fragment.8948bde020cb3af2}",
	}.get(_tab, ""))
	(_n["filter"] as Button).text = {
		"important": "@{desktop.main.fragment.f3f75c13a660d243}", "all": "@{desktop.main.fragment.e4257920848098bb}", "mine": "@{desktop.main.fragment.375eb6ab5a1dfc56}",
	}.get(_event_filter, "@{desktop.main.fragment.f3f75c13a660d243}")
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
		(_n["modal_cancel"] as Button).text = "@{desktop.main.fragment.2cd0f3be8738a86c}"
		(_n["modal_confirm"] as Button).visible = not read_only
		_set_text("modal_title", str(_confirm.get("title", "")))
		_set_text("modal_body", str(_confirm.get("body", "")))
		_set_text("modal_note", str(_confirm.get("note", "")))
		(_n["modal_note_panel"] as Control).visible = not str(
			_confirm.get("note", "")).is_empty()
		if read_only:
			_render_policy_brief(
				_confirm.get("lever", {}), _confirm.get("current"))
	_localize_tree(self)
	call_deferred("_request_visible_entity_page")


func _request_visible_entity_page() -> void:
	if _client == null or _snapshot.is_empty():
		return
	var kind: String = {
		"households": "households",
		"firms": "firms",
		"stocks": "equities",
	}.get(_tab, "")
	if kind.is_empty():
		return
	var boundary := int(_snapshot.get("tick", -1))
	if _m11_adapter.entity_boundary(kind) == boundary \
			or int(_entity_requested.get(kind, -2)) == boundary:
		return
	_entity_requested[kind] = boundary
	_send({
		"command": "entity_page",
		"kind": kind,
		"economy_id": int(
			(_snapshot.get("world", {}) as Dictionary).get(
				"player_economy", 0)),
		"after_id": 0,
		"maximum_rows": 256,
	})


func _localize_tree(node: Node) -> void:
	if node is Label:
		(node as Label).text = LocaleCatalogScript.resolve((node as Label).text)
	elif node is RichTextLabel:
		(node as RichTextLabel).text = LocaleCatalogScript.resolve(
			(node as RichTextLabel).text)
	elif node is Button:
		(node as Button).text = LocaleCatalogScript.resolve((node as Button).text)
	elif node is LineEdit:
		(node as LineEdit).placeholder_text = LocaleCatalogScript.resolve(
			(node as LineEdit).placeholder_text)
	elif node is TextEdit:
		(node as TextEdit).placeholder_text = LocaleCatalogScript.resolve(
			(node as TextEdit).placeholder_text)
	if node is Control:
		(node as Control).tooltip_text = LocaleCatalogScript.resolve(
			(node as Control).tooltip_text)
	if node is OptionButton:
		var selector := node as OptionButton
		for index in selector.item_count:
			selector.set_item_text(
				index, LocaleCatalogScript.resolve(selector.get_item_text(index)))
	for child in node.get_children():
		_localize_tree(child)


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
		tile.tooltip_text = "@{desktop.main.fragment.b2e3ffb8c796691f}\n@{desktop.main.fragment.69b22e58d0b124bd} · %s」" % _panel_group_name(
			str(TILE_TO_GROUP.get(sid, "")))
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
			var rline := _lbl("%s@{desktop.main.fragment.b61f333b91b21f79} · %d@{desktop.main.fragment.503ecc0ed6fca314}" % [
				_cal_short(int(rel.get("released_at_tick", 0))), t - ref_end], 9, INK3, true)
			rline.clip_text = true
			v.add_child(rline)
		else:
			var wait_row := HBoxContainer.new()
			wait_row.add_theme_constant_override("separation", 6)
			wait_row.add_child(_chip("@{desktop.main.fragment.07901db4aad361d9}", Color("849098"), Color("f2f5f9"),
				Color("e0e6ee"), 10))
			v.add_child(wait_row)
			v.add_child(_lbl("— —", 17, Color("c3ccd6"), true))
			var why := str(rel.get("missing_reason", "not_released"))
			var wl := _lbl(why, 9, Color("9aa7b4"), true)
			wl.clip_text = true
			v.add_child(wl)
		row.add_child(tile)


#  Synchronization helper.
func _render_workbench() -> void:
	var lv := _n["levers"] as VBoxContainer
	var lscroll := lv.get_parent() as ScrollContainer
	_keep_scroll("levers:%s:%s" % [_active_seat, _active_group], lscroll)
	for c in lv.get_children():
		c.queue_free()
	var free_policy := _free_policy_enabled()
	var open := free_policy or _awaiting()
	var emg_ctx := _emergency_context()
	var emg := not free_policy and not emg_ctx.is_empty()
	var active_contexts: Array = []
	var active_allowed := 0
	var cap_text := ""
	var permitted: Dictionary = {}
	if free_policy:
		active_contexts.append({"seat": _active_seat})
		var policy_values: Dictionary = _snapshot.get("policy_values", {})
		for seat: String in _schemas.keys():
			for lever: Dictionary in _schemas.get(seat, {}).get("levers", []):
				var item := lever.duplicate(true)
				var name := str(item.get("name", ""))
				item["allowed"] = true
				item["max_step"] = null
				item["current_value"] = policy_values.get(
					name, item.get("current_value"))
				permitted[name] = item
				if seat == _active_seat:
					active_allowed += 1
	else:
		for ctx: Dictionary in _contexts():
			if str(ctx.get("seat", "")) == _active_seat:
				active_contexts.append(ctx)
				if cap_text.is_empty() and ctx.get("admin_remaining") != null:
					cap_text = "%.1f" % float(ctx.get("admin_remaining"))
			for item: Dictionary in ctx.get("permitted_actions", []):
				permitted[str(item.get("lever"))] = item
				if str(ctx.get("seat", "")) == _active_seat \
						and bool(item.get("allowed", false)):
					active_allowed += 1
	for s: Dictionary in SEAT_LIST:
		var sid := str(s["id"])
		var b := _n["seat_" + sid] as Button
		var n_open := 0
		if not free_policy:
			for ctx: Dictionary in _contexts():
				if str(ctx.get("seat", "")) == sid:
					n_open += 1
		b.text = str(s["name"]) + (
			"" if free_policy else (" ·%d" % n_open if n_open > 0 else ""))
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
	if free_policy:
		_set_text("meeting",
			LocaleCatalogScript.format("desktop.free.header", active_name))
	elif not open:
		_set_text("meeting", "%s · @{desktop.main.fragment.58ef70be957cea2d} · @{desktop.main.fragment.b3e8eb037c4c3bba}" % active_name)
	elif active_contexts.is_empty():
		_set_text("meeting", "%s · @{desktop.main.fragment.50fc365b776171f7}" % active_name)
	else:
		var status := "🚨 @{desktop.main.fragment.7ac9f30d469518a3}" if emg else "● @{desktop.main.fragment.227d598dd9387039}"
		var cap := "" if cap_text.is_empty() else " · @{desktop.main.fragment.d8272b3c5f197b58} " + cap_text
		_set_text("meeting", "%s · %s %d @{desktop.main.fragment.9efe01f647d67d91} / %d @{desktop.main.fragment.c94913ca0622e9ea}%s" % [
			active_name, status, active_contexts.size(), active_allowed, cap])
	var meetl := _n["meeting"] as Label
	meetl.add_theme_color_override("font_color", TEAL_DK if free_policy else (
		(Color("b02a1c") if emg else Color("9a6b10"))
		if not active_contexts.is_empty() else INK2))
	var pending_by: Dictionary = {}
	if free_policy:
		var free_pending: Dictionary = _snapshot.get("free_policy", {})
		var effective: Variant = free_pending.get(
			"effective_tick", int(_snapshot.get("tick", 0)) + 1)
		for act in free_pending.get("actions", []):
			if act is Dictionary:
				pending_by[str((act as Dictionary).get("lever", ""))] = {
					"value": (act as Dictionary).get("value"),
					"effective_tick": effective}
	else:
		for p in _snapshot.get("pending", []):
			if p is Dictionary:
				var decision: Dictionary = (p as Dictionary).get("decision", {})
				for act in (p as Dictionary).get("actions", []):
					if act is Dictionary:
						pending_by[str((act as Dictionary).get("lever", ""))] = {
							"value": (act as Dictionary).get("value"),
							"effective_tick": decision.get("effective_tick", "?")}
	#  Secondary Page Signing: Themes Pages (≤8 per page; hidden during search)
	var gflow := _n["group_chips"] as HFlowContainer
	for c in gflow.get_children():
		c.queue_free()
	var searching := not _search.is_empty()
	var active_open := not active_contexts.is_empty()
	var scope := _n["policy_scope"] as Button
	if free_policy:
		_policy_scope = "all"
	scope.visible = not searching and not free_policy
	scope.disabled = not active_open
	scope.text = "@{desktop.main.fragment.fe8af2657e540cbd}" if _policy_scope == "meeting" and active_open else "@{desktop.main.fragment.aa62abe9efa2901e}"
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
		if not free_policy and _policy_scope == "meeting" and active_open:
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
			var live := free_policy
			if not free_policy:
				for lever: Dictionary in pg["levers"]:
					if not _context_for_group(str(_lever_group.get(
							str(lever.get("name")), ""))).is_empty():
						live = true
						break
			if live and not free_policy:
				b.text += " ●"
			b.disabled = not free_policy and _policy_scope == "meeting" \
				and active_open and not live
			if draft_count > 0:
				b.text += " ·%d" % draft_count
			b.pressed.connect(func() -> void:
				_active_group = pname
				_expanded_lever = ""
				_render())
			gflow.add_child(b)
	#  Cylinder List: Search = cross-seat; otherwise = current theme page (one screen); accordion development
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
				if not free_policy and _policy_scope == "meeting" and active_open \
						and _context_for_group(str(lever.get("decision_group", ""))).is_empty():
					continue
				rows.append({"lever": lever, "seat": _active_seat})
	if searching:
		var sh := MarginContainer.new()
		sh.add_theme_constant_override("margin_left", 12)
		sh.add_child(_lbl("@{desktop.main.fragment.d94aa4bc1ba2a23c}%s」· %d @{desktop.main.fragment.49ccde43a1549791}(@{desktop.main.fragment.e864e4811f1ca72c})" % [_search, rows.size()],
			10, INK3, true))
		lv.add_child(sh)
	if rows.is_empty():
		var empty := MarginContainer.new()
		empty.add_theme_constant_override("margin_left", 12)
		empty.add_theme_constant_override("margin_right", 12)
		empty.add_theme_constant_override("margin_top", 8)
		var empty_panel := PanelContainer.new()
		empty_panel.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 9, 10))
		var empty_text := "@{desktop.main.fragment.92e72040bc2431ce}" if searching \
			else "@{desktop.main.fragment.aa3b8a95534f1738}"
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
	if not free_policy and not open and int(_snapshot.get("tick", 0)) < 30 \
			and not searching:
		var guide := MarginContainer.new()
		guide.add_theme_constant_override("margin_left", 12)
		guide.add_theme_constant_override("margin_right", 12)
		guide.add_theme_constant_override("margin_top", 6)
		var gp := PanelContainer.new()
		gp.add_theme_stylebox_override("panel", _sb(BLUE_BG, BLUE_BD, 10, 10))
		var gv := VBoxContainer.new()
		gv.add_theme_constant_override("separation", 5)
		gp.add_child(gv)
		gv.add_child(_lbl("@{desktop.main.fragment.43d4c4981dfbfba6}", 11, Color("1c4a8f")))
		for tip in ["▶ @{desktop.main.fragment.c3396195e91ccdd8}(@{desktop.main.fragment.bfa4a6e0fe42ac28})@{desktop.main.fragment.d7113f03689a10a4},@{desktop.main.fragment.d918dc1679308091}",
				"@{desktop.main.fragment.c0112ef0a6076953}:@{desktop.main.fragment.25506417c44bbfa8} → @{desktop.main.fragment.f65c42a2540befe5} → @{desktop.main.fragment.ea53dafb2b03ec3e} → @{desktop.main.fragment.08a85f4ab4bab9ca}",
				"@{desktop.main.fragment.3e77fe0645075379}?@{desktop.main.fragment.b46d89eb3c1a0aac}",
				"@{desktop.main.fragment.402004f8d4e7318a};@{desktop.main.fragment.751f8369f49c9fcd}"]:
			gv.add_child(_lbl("· " + str(tip), 10, Color("3f5d8a")))
		guide.add_child(gp)
		lv.add_child(guide)
	if not free_policy and not open and not searching:
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
	head.add_child(_lbl("EXECUTIVE BRIEF · @{desktop.main.fragment.8125d217bd797ad9}", 10, Color("9db8c8"), true))
	head.add_child(_spacer_h())
	head.add_child(_lbl("@{desktop.main.fragment.7fdf29cf09f90953}", 10, Color("68d2c2")))
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
		["@{desktop.main.fragment.1d6571193d7a584e}", "%d/%d" % [released, releases.size()]],
		["@{desktop.main.fragment.2b868142a6f667a5}", str(pending.size())],
		["@{desktop.main.fragment.88a8fa0ea83e9561}", str(risks)],
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
		col.add_child(_lbl("@{desktop.main.fragment.50f9f61416dda499}",
			10, Color("b4c5cf")))
	else:
		col.add_child(_lbl("@{desktop.main.fragment.503a406b6681761a}", 9, Color("8ca5b5"), true))
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
	var jump := _btn("@{desktop.main.fragment.7d83f69d94ae7dcd}", _advance_to_next_decision, true)
	jump.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	jump.tooltip_text = "@{desktop.main.fragment.ecc6c552f474e6a0}\n@{desktop.main.fragment.e710cfccd80e3d6f} 100 @{desktop.main.fragment.15a4a25be6a61d1c}\n@{desktop.main.fragment.8fe60bd7ce74d003} · @{desktop.main.fragment.10b775695af17455}N"
	actions.add_child(jump)
	var focus := _btn("@{desktop.main.fragment.a669946c97b805d2}", func() -> void:
		_tab = "focus"
		_render())
	focus.add_theme_stylebox_override("normal", _sb(
		Color("203b4d"), Color("426175"), 8, 7))
	focus.add_theme_color_override("font_color", Color("d9e6eb"))
	actions.add_child(focus)
	col.add_child(actions)
	parent.add_child(margin)


func _advance_to_next_decision() -> void:
	if _free_policy_enabled():
		_show_hint(LocaleCatalogScript.text("desktop.free.advance_month"))
		_send({"command": "advance", "ticks": 30})
		return
	if _awaiting():
		_show_hint("@{desktop.main.fragment.38a86edae74dc71a}")
		return
	_show_hint("@{desktop.main.fragment.8b3653792875febd} 100 @{desktop.main.fragment.c343c78f974e59cd}")
	_send({"command": "advance", "ticks": 100})


func _lever_kind_description(lever: Dictionary) -> String:
	var kind := str(lever.get("value_kind", "number"))
	var nullable := bool(lever.get("nullable", false))
	match kind:
		"bool":
			return "@{desktop.main.fragment.f4f0ead1116b5b62} / @{desktop.main.fragment.712296747c88b676}"
		"choice":
			var options: Array = []
			for option in lever.get("choices", []):
				options.append(_choice_text(str(lever.get("name", "")), option))
			return "@{desktop.main.fragment.a8fb30e4820f09ad}%s）" % "、".join(options)
		"economy_id":
			return "@{desktop.main.fragment.b19d1f40d310808d}"
		"economy_set":
			return "@{desktop.main.fragment.88dd8d3f31e644d5}"
		"integer":
			return "@{desktop.main.fragment.4b8e09e0abf9ba42} %s – %s" % [
				_lever_value_text(lever, lever.get("minimum", 0)),
				_lever_value_text(lever, lever.get("maximum", 0))]
		_:
			var range_text := "@{desktop.main.fragment.4f9064f4e0eef26a} %s – %s" % [
				_lever_value_text(lever, lever.get("minimum", 0.0)),
				_lever_value_text(lever, lever.get("maximum", 0.0))]
			return range_text + ("@{desktop.main.fragment.077099468884b194}" if nullable else "")


func _lever_channel_text(lever: Dictionary) -> String:
	var read_point := str(lever.get("read_point", "")).to_lower()
	var group := str(lever.get("decision_group", ""))
	if read_point.contains("energy"):
		return "@{desktop.main.fragment.465f7e67671ed6fb}"
	if read_point.contains("mortgage") or read_point.contains("housing"):
		return "@{desktop.main.fragment.bdf05925a2d9e76d}"
	if read_point.contains("central_bank"):
		return "@{desktop.main.fragment.53cb66eb5ee67ad8}"
	if read_point.contains("banking") or read_point.contains("credit"):
		return "@{desktop.main.fragment.170ee7ecd2ffef3d}"
	if read_point.contains("securities"):
		return "@{desktop.main.fragment.631e7bdf8ac0751e}"
	if read_point.contains("trade"):
		return "@{desktop.main.fragment.f3bf02be1457ce4e}"
	if read_point.contains("migration"):
		return "@{desktop.main.fragment.52ad6c253dccc303}"
	if read_point.contains("world") or read_point.contains("capital") \
			or read_point.contains("fx"):
		return "@{desktop.main.fragment.185e5dba53f3ae81}"
	if read_point.contains("settlement"):
		return "@{desktop.main.fragment.8268463d1dd50521}"
	if read_point.contains("goods") or read_point.contains("planning"):
		return "@{desktop.main.fragment.7b6afca6f183a8e6}"
	if read_point.contains("reporting"):
		return "@{desktop.main.fragment.88cdfedcb38a63f4}"
	return {
		"fiscal_stance": "@{desktop.main.fragment.d37adcd3d4049d7b}",
		"tax_and_transfers": "@{desktop.main.fragment.c826597498921634}",
		"debt_management": "@{desktop.main.fragment.fc58ff5fa4e1c6e8}",
		"monetary_stance": "@{desktop.main.fragment.70b7b14a617b9bb2}",
		"liquidity_operations": "@{desktop.main.fragment.d7520ac35a86e514}",
		"macroprudential": "@{desktop.main.fragment.a88db9709a253142}",
		"structural_law": "@{desktop.main.fragment.c47ce83565f7f1b2}",
		"trade_and_migration": "@{desktop.main.fragment.fe58146812ec118e}",
		"fx_operations": "@{desktop.main.fragment.7adcb41dcbb35202}",
		"energy_operations": "@{desktop.main.fragment.f32c36a75cc2be88}",
		"energy_structure": "@{desktop.main.fragment.d90c070e461b898d}",
	}.get(group, "@{desktop.main.fragment.88f8134cd5088f7b}")


func _lever_meaning_text(lever: Dictionary) -> String:
	var name := str(lever.get("name", ""))
	var label := _cn(name)
	var player_help: Dictionary = lever.get("player_help", {})
	var help: Dictionary = POLICY_HELP.get(name, {})
	var definition := str(player_help.get("meaning", help.get("definition", "")))
	if definition.is_empty():
		if name.begins_with("tax_") or label.ends_with("@{desktop.main.fragment.9401d14fdcb4e892}"):
			definition = "“%s@{desktop.main.fragment.6e1742fefa82026f}" % label
		elif name.contains("allowance") or label.ends_with("@{desktop.main.fragment.0fa1371672e99f5a}"):
			definition = "“%s@{desktop.main.fragment.ca6a26a4f26cb584}" % label
		elif name.contains("cap") or name.contains("limit") or label.ends_with("@{desktop.main.fragment.8e7ddbeee310a5a5}"):
			definition = "“%s@{desktop.main.fragment.b3c742b651a24dbf}" % label
		elif name.contains("floor") or name.begins_with("min_") or label.ends_with("@{desktop.main.fragment.2c3f8d6ce49a60fa}"):
			definition = "“%s@{desktop.main.fragment.06ea117d90b53c5e}" % label
		elif name.ends_with("_share") or name.ends_with("_frac") \
				or name.ends_with("_ratio") or name.ends_with("_ltv"):
			definition = "“%s@{desktop.main.fragment.09e3b0b1011f28fc}" % label
		elif str(lever.get("value_kind", "")) == "bool":
			definition = "“%s@{desktop.main.fragment.c5bd883c30881df9}" % label
		elif str(lever.get("value_kind", "")) == "choice":
			definition = "“%s@{desktop.main.fragment.373bfa9b136eeeb3}" % label
		else:
			definition = "“%s@{desktop.main.fragment.d885bedf8044258e}%s@{desktop.main.fragment.296aeb395e00a42d}" % [
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
	if name.begins_with("tax_") or label.ends_with("@{desktop.main.fragment.9401d14fdcb4e892}"):
		return "@{desktop.main.fragment.e77fc0b5e5657dba}"
	if name.contains("subsidy") or name.contains("benefit") \
			or name.contains("pension"):
		return "@{desktop.main.fragment.ce668b23c08463da}"
	if name.contains("allowance") or label.ends_with("@{desktop.main.fragment.0fa1371672e99f5a}"):
		return "@{desktop.main.fragment.c581d92ef6f49afe}"
	if name.contains("haircut") or name.contains("risk_weight"):
		return "@{desktop.main.fragment.4979001f7c4a2a42}"
	if name.contains("cap") or name.contains("limit") or label.ends_with("@{desktop.main.fragment.8e7ddbeee310a5a5}"):
		return "@{desktop.main.fragment.bc6b4023aeb8d933}"
	if name.contains("floor") or name.begins_with("min_") or label.ends_with("@{desktop.main.fragment.2c3f8d6ce49a60fa}"):
		return "@{desktop.main.fragment.ece96b1668174c4c}"
	if str(lever.get("value_kind", "")) == "bool":
		return "@{desktop.main.fragment.bd105468d9296cc1}%s@{desktop.main.fragment.818a1e82f06a0935}" % \
			_lever_channel_text(lever)
	return "@{desktop.main.fragment.25c7272706f546f3}%s@{desktop.main.fragment.a4f51a6025cdaaae}" % \
		_lever_channel_text(lever)


func _lever_tradeoffs_text(lever: Dictionary) -> String:
	var player_help: Dictionary = lever.get("player_help", {})
	var text := str(player_help.get("tradeoffs", ""))
	if not text.is_empty():
		return text
	return "@{desktop.main.fragment.5f8967522cc77b1a}"


func _lever_watch_text(lever: Dictionary) -> String:
	var player_help: Dictionary = lever.get("player_help", {})
	var text := str(player_help.get("watch", ""))
	if not text.is_empty():
		return text
	return "@{desktop.main.fragment.8b13fd9c72b17bbb}"


func _lever_info_tooltip(lever: Dictionary, current: Variant) -> String:
	return "%s  ·  @{desktop.main.fragment.cb62ebd689ee8f20} %s\n\n@{desktop.main.fragment.1157213b813000e2}\n%s\n\n@{desktop.main.fragment.245ab851face3d9b}\n%s\n\n@{desktop.main.fragment.48ca9369c9040c19}\n%s\n\n@{desktop.main.fragment.83f2cdb2592b380c}" % [
		_cn(str(lever.get("name", ""))), _lever_value_text(lever, current),
		_tooltip_wrap(_lever_meaning_text(lever)),
		_tooltip_wrap(_lever_effect_text(lever)),
		_tooltip_wrap(_lever_tradeoffs_text(lever))]


func _tooltip_wrap(text: String, preferred_width: int = 34) -> String:
	#  Godot 's default tooltip does not automatically break lines; priority is given to breaking lines after the Chinese tab and setting a hard limit for long sentences.
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
	if _free_policy_enabled():
		return LocaleCatalogScript.text("desktop.free.timing")
	var lag := int(lever.get("implementation_lag", 0))
	return "@{desktop.main.fragment.79f5c00849e70543}" if lag <= 0 else "@{desktop.main.fragment.da348369158b4e9e} %d @{desktop.main.fragment.cccf58ef16e9afe4}" % lag


func _lever_adjustment_text(lever: Dictionary) -> String:
	if _free_policy_enabled():
		return LocaleCatalogScript.text("desktop.free.adjustment")
	var hold := int(lever.get("min_hold_ticks", 0))
	var scale: Variant = lever.get("control_scale")
	var max_step: Variant = lever.get("max_step")
	var adjustment := "@{desktop.main.fragment.a57b6fdc0251f83e}"
	if scale != null:
		adjustment = "@{desktop.main.fragment.a39a1c5b04add294} %s" % _lever_value_text(lever, scale)
	if max_step != null:
		adjustment += "@{desktop.main.fragment.5e922c3dbec4fc86} %s" % _lever_value_text(lever, max_step)
	return "%s@{desktop.main.fragment.f5da2b74cea86c2e} %d @{desktop.main.fragment.49da61ceeea2f271}" % [adjustment, hold]


func _lever_semantics_text(lever: Dictionary) -> String:
	return str({
		"immediate": "@{desktop.main.fragment.06002c47bdb5d9e8}",
		"new-contracts-only": "@{desktop.main.fragment.8409f518637c751a}",
		"state-transition": "@{desktop.main.fragment.7dca615266ac9e51}",
	}.get(str(lever.get("semantics", "immediate")), "@{desktop.main.fragment.5cbbdf0381a8a3d5}"))


func _lever_conditions_text(lever: Dictionary) -> String:
	var requirements: Array = []
	for capability in lever.get("requires", []):
		requirements.append(str(CAPABILITY_CN.get(str(capability), capability)))
	for prerequisite in lever.get("enabled_if", []):
		requirements.append("@{desktop.main.fragment.2200d80940b75c1f}%s@{desktop.main.fragment.f510117cd7d7be44}" % _cn(str(prerequisite)))
	return "@{desktop.main.fragment.33f852615de926b1}" if requirements.is_empty() else "@{desktop.main.fragment.97c27cdca015aa89}%s" % "、".join(requirements)


func _lever_boundary_text(lever: Dictionary) -> String:
	var shadowed: Array = []
	for raw_shadow in lever.get("shadowed_by", []):
		var token := str(raw_shadow)
		var base: String = token.split(">")[0].split("=")[0]
		if token == "ZLB/r_max clamp":
			shadowed.append("@{desktop.main.fragment.3aff3b853288ac70}")
		else:
			shadowed.append(_cn(base) if LEVER_CN.has(base) else token)
	if not shadowed.is_empty():
		return "@{desktop.main.fragment.3eb61c394d7d9bf9}%s@{desktop.main.fragment.bab739f820ea9fca}" % "、".join(shadowed)
	if not str(lever.get("state_notes", "")).is_empty():
		return "@{desktop.main.fragment.4b46fe24c96fd40f}"
	return "@{desktop.main.fragment.90d45325b9dab96d}"


func _lever_cost_text(lever: Dictionary) -> String:
	if _free_policy_enabled():
		return LocaleCatalogScript.text("desktop.free.cost")
	var cost_cn: String = {
		"regime_switch": "@{desktop.main.fragment.3090b183dc295243}", "major": "@{desktop.main.fragment.bb7d02f0cceecd83}",
		"ordinary": "@{desktop.main.fragment.d55cc2145168659e}", "operational": "@{desktop.main.fragment.d088a57270bb2245}",
	}.get(str(lever.get("cost_class", "ordinary")), "@{desktop.main.fragment.d55cc2145168659e}")
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
		content.add_child(_brief_text("@{desktop.main.fragment.41cd94251cb3d6eb}", 12, INK3))
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
	current_col.add_child(_lbl("CURRENT POLICY · @{desktop.main.fragment.f6814fea9925bef5}", 9, Color("6d8092"), true))
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
	meaning_col.add_child(_lbl("ECONOMIC DEFINITION · @{desktop.main.fragment.1157213b813000e2}", 9, Color("6d8092"), true))
	meaning_col.add_child(_brief_text(_lever_meaning_text(lever), 13, Color("263b4d"), true))
	hero_row.add_child(meaning_col)
	content.add_child(hero)

	# The economic transmission and policy trade-off follow the definition.
	var decision_row := HBoxContainer.new()
	decision_row.add_theme_constant_override("separation", 12)
	decision_row.add_child(_brief_panel("ECONOMIC TRANSMISSION · @{desktop.main.fragment.245ab851face3d9b}", _lever_effect_text(lever),
		Color("386b9d"), Color.WHITE))
	decision_row.add_child(_brief_panel("POLICY TRADE-OFF · @{desktop.main.fragment.48ca9369c9040c19}", _lever_tradeoffs_text(lever),
		Color("9b6e2c"), Color.WHITE))
	content.add_child(decision_row)

	var watch_panel := PanelContainer.new()
	watch_panel.add_theme_stylebox_override("panel", _sb(Color("f3f7f7"), Color("d5e1e0"), 9, 11))
	var watch_col := VBoxContainer.new()
	watch_col.add_theme_constant_override("separation", 7)
	watch_panel.add_child(watch_col)
	watch_col.add_child(_lbl("MONITOR · @{desktop.main.fragment.bb505e6a0774debf}", 9, Color("4a6f70"), true))
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
	rule_heading.add_child(_lbl(
		"@desktop.free.execution_heading" if _free_policy_enabled()
		else "GAME RULES · @{desktop.main.fragment.ad4ff9ec3d88e93d}", 10, INK3, true))
	rule_heading.add_child(_hrule())
	content.add_child(rule_heading)
	var rules := GridContainer.new()
	rules.columns = 2
	rules.add_theme_constant_override("h_separation", 8)
	rules.add_theme_constant_override("v_separation", 8)
	var rule_accent := Color("536b7e")
	rules.add_child(_brief_rule_card("@{desktop.main.fragment.a164227bb693e47f}", _lever_kind_description(lever), rule_accent))
	rules.add_child(_brief_rule_card("@{desktop.main.fragment.dc971e40a1ff0cf6}", _lever_timing_text(lever), rule_accent))
	rules.add_child(_brief_rule_card("@{desktop.main.fragment.c817de8105cc4ede}", _lever_adjustment_text(lever), rule_accent))
	rules.add_child(_brief_rule_card(
		"@desktop.free.constraint_heading" if _free_policy_enabled() else "@{desktop.main.fragment.4e2f4f352727d794}",
		_lever_cost_text(lever), rule_accent))
	content.add_child(rules)

	var execution := HBoxContainer.new()
	execution.add_theme_constant_override("separation", 12)
	execution.add_child(_brief_panel("@{desktop.main.fragment.ec0ce66a5204a180}", _lever_semantics_text(lever),
		Color("58708a"), Color.WHITE))
	execution.add_child(_brief_panel("@{desktop.main.fragment.03c2827b3f016d3d}", _lever_conditions_text(lever),
		Color("58708a"), Color.WHITE))
	content.add_child(execution)
	content.add_child(_brief_panel("@{desktop.main.fragment.f8a9796756e209f0}", _lever_boundary_text(lever),
		Color("9a6b10"), Color("fffaf0")))

	if _free_policy_enabled():
		content.add_child(_brief_text(
			LocaleCatalogScript.text("desktop.free.brief_footer"),
			10, INK3))
	else:
		var emergency_text := "@{desktop.main.fragment.149114eaab866e7b} %s。" % (
			"@{desktop.main.fragment.2da85532337f2387}" if lever.get("emergency_implementation_lag") == null
			else "%d @{desktop.main.fragment.49da61ceeea2f271}" % int(lever.get("emergency_implementation_lag", 0))) \
			if bool(lever.get("emergency", false)) else "@{desktop.main.fragment.061a5a02f5c7eeec}"
		content.add_child(_brief_text("@{desktop.main.fragment.978cbca6265d1af2} · %s · %s\n%s" % [
			_seat_name(str(lever.get("owner_role", ""))),
			str(GROUP_CN.get(str(lever.get("decision_group", "")),
				lever.get("decision_group", "@{desktop.main.fragment.6993cb35989038ca}"))), emergency_text], 10, INK3))


func _show_lever_info(lever: Dictionary, current: Variant) -> void:
	_confirm = {
		"title": _cn(str(lever.get("name", ""))),
		"body": "",
		"note": "@{desktop.main.fragment.fef28fad0600db26}",
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
	##  The present value, the draft/queue target and the operational status of the collection; click into the exact editing.
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
	row.tooltip_text = LocaleCatalogScript.format(
		"desktop.free.row_tooltip", _cn(name))
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
		status_text = "@{desktop.main.fragment.358dce5dde4247a0} · @{desktop.main.fragment.f591f3067a342198}"
		status_color = AMBER
	elif in_cart:
		status_text = LocaleCatalogScript.text("desktop.free.status_queued") \
			if _free_policy_enabled() else "@{desktop.main.fragment.1bd538423c2b7202}"
		status_color = TEAL_DK
	elif edited:
		status_text = "@{desktop.main.fragment.3a013c5308141367}"
		status_color = BLUE
	elif pending:
		status_text = "@{desktop.main.fragment.211daec74a20bd9b} · %s" % _cal_value(
			(pending_by[name] as Dictionary).get("effective_tick", "?"))
		status_color = AMBER
	elif allowed:
		status_text = LocaleCatalogScript.text("desktop.free.status_adjustable") \
			if _free_policy_enabled() else "@{desktop.main.fragment.b7ae526ec0a29f6a}"
		status_color = GREEN
	else:
		status_text = "@{desktop.main.fragment.0b2d7cb5d3d6694c}"
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
	if not _free_policy_enabled():
		var cost_class := str(lever.get("cost_class", "ordinary"))
		var cost_cn: String = {"regime_switch": "@{desktop.main.fragment.b1c27820fec23edb}", "major": "@{desktop.main.fragment.b1c27820fec23edb}",
			"ordinary": "@{desktop.main.fragment.a567bdaa11367f26}", "operational": "@{desktop.main.fragment.aa9e366f68d3d097}"}.get(cost_class, "@{desktop.main.fragment.a567bdaa11367f26}")
		var cost_fg: Color = AMBER if cost_cn == "@{desktop.main.fragment.b1c27820fec23edb}" \
			else (Color("3f6db2") if cost_cn == "@{desktop.main.fragment.a567bdaa11367f26}" else INK2)
		tr.add_child(_chip("@{desktop.main.fragment.639de58eb608d490} %.1f · %s" % [
			float(lever.get("admin_weight", 1.0)), cost_cn],
			cost_fg, Color(0, 0, 0, 0),
			AMBER_BD if cost_cn == "@{desktop.main.fragment.b1c27820fec23edb}" else LINE2, 10))
	v.add_child(tr)
	var state := PanelContainer.new()
	state.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 8, 7))
	var state_row := HBoxContainer.new()
	state_row.add_theme_constant_override("separation", 7)
	state.add_child(state_row)
	state_row.add_child(_lbl("@{desktop.main.fragment.cb62ebd689ee8f20}", 9, INK3, true))
	state_row.add_child(_lbl(_lever_value_text(lever, base_v), 12, INK2, true))
	if edited:
		state_row.add_child(_lbl("→", 11, TEAL))
		state_row.add_child(_lbl("@{desktop.main.fragment.2a2fd29bd27a6eb9}", 9, TEAL, true))
		state_row.add_child(_lbl(_lever_value_text(lever, draft_v), 12,
			AMBER if cart_stale else TEAL_DK, true))
	state_row.add_child(_spacer_h())
	if cart_stale:
		state_row.add_child(_lbl("@{desktop.main.fragment.709e1c69f478b92b}", 9, AMBER))
	elif in_cart:
		state_row.add_child(_lbl("@{desktop.main.fragment.47f94c663a6584be}", 9, TEAL_DK))
	v.add_child(state)
	if allowed:
		v.add_child(_lever_control(lever, perm, base_v))
		var companion := _lever_companion_note(name, draft_v)
		if not companion.is_empty():
			var note_panel := PanelContainer.new()
			note_panel.add_theme_stylebox_override("panel", _sb(BLUE_BG, BLUE_BD, 7, 7))
			var note := _lbl("@{desktop.main.fragment.6f24351d9f52af86} · " + companion, 10, Color("315d96"))
			note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			note_panel.add_child(note)
			v.add_child(note_panel)
	else:
		var lockp := PanelContainer.new()
		lockp.add_theme_stylebox_override("panel", _sb(PANEL3, LINE2, 8, 9))
		var lr := HBoxContainer.new()
		lr.add_theme_constant_override("separation", 9)
		lockp.add_child(lr)
		lr.add_child(_chip("@{desktop.main.fragment.ff9872a023e3a8aa}", Color("647585"), Color(0, 0, 0, 0), LINE2, 10))
		var reason := str(perm.get("reason_code", ""))
		if emg and not bool(lever.get("emergency", false)):
			reason = "@{desktop.main.fragment.538aa5d497c5ad7e}"
		elif not open:
			reason = "@{desktop.main.fragment.cb62ebd689ee8f20} " + _lever_value_text(lever, base_v) + " · @{desktop.main.fragment.ecb92a184724d4bf}"
		elif reason.is_empty() or reason == "<null>":
			reason = "@{desktop.main.fragment.cb62ebd689ee8f20} " + _lever_value_text(lever, base_v) + " · @{desktop.main.fragment.de90517707d9287a}"
		else:
			reason = _permission_reason(reason)
		var rl := _lbl(reason, 11, Color("586a7b"))
		rl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		rl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		lr.add_child(rl)
		v.add_child(lockp)
	var meta := HBoxContainer.new()
	meta.add_theme_constant_override("separation", 9)
	if _free_policy_enabled():
		meta.add_child(_lbl("@desktop.free.next_day", 10, TEAL_DK, true))
		meta.add_child(_lbl("@desktop.free.no_restrictions", 10,
			Color("68788b"), true))
	else:
		var lag := int(lever.get("implementation_lag", 0))
		meta.add_child(_lbl(
			"@{desktop.main.fragment.da348369158b4e9e} %d @{desktop.main.fragment.cccf58ef16e9afe4}" % lag if lag > 0 else "@{desktop.main.fragment.79f5c00849e70543}", 10,
			Color("68788b"), true))
		meta.add_child(_lbl("@{desktop.main.fragment.6cac16b39789379a} %d @{desktop.main.fragment.49da61ceeea2f271}" % int(
			lever.get("min_hold_ticks", 0)), 10, Color("68788b"), true))
		if bool(lever.get("emergency", false)):
			meta.add_child(_lbl("@{desktop.main.fragment.009038a63d875104}", 10, AMBER, true))
	v.add_child(meta)
	var pend: Variant = pending_by.get(name)
	if pend is Dictionary:
		var pp := PanelContainer.new()
		pp.add_theme_stylebox_override("panel", _sb(TEAL_BG, TEAL_BD, 7, 6))
		var pr := HBoxContainer.new()
		pr.add_theme_constant_override("separation", 8)
		pp.add_child(pr)
		pr.add_child(_lbl(
			"@desktop.free.queue_title" if _free_policy_enabled() else "@{desktop.main.fragment.1be538253bf451de}",
			10, TEAL, true))
		pr.add_child(_lbl(_lever_value_text(lever, (pend as Dictionary).get("value")),
			11, TEAL_DK, true))
		pr.add_child(_spacer_h())
		pr.add_child(_lbl("%s@{desktop.main.fragment.c997444643299f36}" % _cal_value(
			(pend as Dictionary).get("effective_tick", "?")),
			11, Color("2a9184")))
		v.add_child(pp)
	if edited:
		var addrow := HBoxContainer.new()
		addrow.add_theme_constant_override("separation", 9)
		if not changed:
			addrow.add_child(_lbl("@{desktop.main.fragment.77d0b5c253e19434}", 10, INK3))
		elif allowed and (not in_cart or cart_stale):
			var add_label := (
				LocaleCatalogScript.text("desktop.free.update")
				if cart_stale else LocaleCatalogScript.text("desktop.free.add")
			) if _free_policy_enabled() else (
				"@{desktop.main.fragment.02ab3cf32e801598}" if cart_stale else "@{desktop.main.fragment.ea53dafb2b03ec3e} ＋")
			var add := _btn(add_label, func() -> void:
				_add_to_cart(lever, base_v), true)
			addrow.add_child(add)
			var effective_tick := int(_snapshot.get("tick", 0)) + (
				1 if _free_policy_enabled() else maxi(
					int(lever.get("implementation_lag", 0)), 1))
			addrow.add_child(_lbl("@{desktop.main.fragment.535c45e2209695ea} %s @{desktop.main.fragment.c997444643299f36}" % _cal_short(
				effective_tick), 10, INK3, true))
		elif in_cart:
			addrow.add_child(_lbl("✓ @{desktop.main.fragment.02a9ee7c3b12f8e0}", 11, TEAL_DK))
		else:
			addrow.add_child(_lbl("@{desktop.main.fragment.7060c2e2b2ad970e}", 10, AMBER))
		addrow.add_child(_spacer_h())
		var reset := _btn("@{desktop.main.fragment.ca762c08e695b97a}" if in_cart else "@{desktop.main.fragment.8e68cfde3335b62a}", func() -> void:
			_reset_lever_draft(name))
		reset.add_theme_font_size_override("font_size", 10)
		addrow.add_child(reset)
		v.add_child(addrow)
	return card


func _lever_value_text(lever: Dictionary, v: Variant) -> String:
	if v == null:
		return "@{desktop.main.fragment.2f5f1d6fbfb061ed}"
	if v is bool:
		return "@{desktop.main.fragment.f4f0ead1116b5b62}" if v else "@{desktop.main.fragment.4e6fd0e28c55860b}"
	if v is String:
		return _choice_text(str(lever.get("name", "")), v)
	if v is Array:
		if (v as Array).is_empty():
			return "@{desktop.main.fragment.0ab6dbe8254ee4b2}"
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
		return "%d @{desktop.main.fragment.49da61ceeea2f271}" % roundi(f)
	if name == "housing_permits":
		return "%d @{desktop.main.fragment.82839948fc37f173}/@{desktop.main.fragment.62ef900a8f5d5bff}" % roundi(f)
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
				return "@{desktop.main.fragment.210df1723a5b7ec3}"
		"manual_policy_rate":
			return "@{desktop.main.fragment.1be652f41742f8fc} = @{desktop.main.fragment.faf0f41e52321f76}"
		"fx_regime":
			if str(draft_value) == "peg":
				return "@{desktop.main.fragment.013c44c6c45b9f88}"
		"peg_anchor":
			return "@{desktop.main.fragment.ff3733a772303c4b}"
	return ""


func _commit_numeric_input(lever: Dictionary, text: String, is_int: bool,
		minimum: float, maximum: float) -> void:
	var cleaned := text.strip_edges()
	if not cleaned.is_valid_float():
		_show_hint("@{desktop.main.fragment.9b47ff78ff66de10} 3% @{desktop.main.fragment.2087c777c06fefe5} 0.03。")
		return
	var value := clampf(cleaned.to_float(), minimum, maximum)
	_set_policy_edit(lever, roundi(value) if is_int else value)


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
		sw.text = "@{desktop.main.fragment.f4f0ead1116b5b62}" if cur == true else "@{desktop.main.fragment.4e6fd0e28c55860b}"
		var st := str(lever.get("semantics",
			lever.get("effective_semantics", ""))).contains("transition")
		sw.toggled.connect(func(pressed: bool) -> void:
			_stage_lever_edit(lever, pressed))
		brow.add_child(sw)
		if st:
			brow.add_child(_chip("@{desktop.main.fragment.a3407877e497ee2d}", Color("9a7a2e"), Color(0, 0, 0, 0), AMBER_BD, 10))
		return brow
	#  Values (including empty): Step is suitable for exploration and enter directly for precision.
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
	var range_text := "@{desktop.main.fragment.6fd7d22b7b5f051e} %s · @{desktop.main.fragment.049bc88d2bf11492} %s – %s" % [
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
			_set_policy_edit(lever, roundi(next) if is_int else next))
		inc.pressed.connect(func() -> void:
			var next := clampf(float(_edits.get(name, local_base)) + scale, lo2, hi2)
			_set_policy_edit(lever, roundi(next) if is_int else next))
	wrap.add_child(srow)
	if numeric:
		var direct := HBoxContainer.new()
		direct.add_theme_constant_override("separation", 6)
		var input := LineEdit.new()
		input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		input.text = _lever_raw_value_text(lever, cur)
		input.placeholder_text = "@{desktop.main.fragment.b83026a4d929fb37}"
		input.tooltip_text = "@{desktop.main.fragment.9b6328b156a3eda7}\n@{desktop.main.fragment.2eeeceff78bfedeb}3% @{desktop.main.fragment.60120ff05f5c62b9} 0.03"
		input.add_theme_font_override("font", _mono)
		input.add_theme_font_size_override("font_size", 11)
		input.add_theme_stylebox_override("normal", _sb(Color.WHITE, LINE2, 7, 6))
		input.add_theme_stylebox_override("focus", _sb(Color.WHITE, TEAL_BD, 7, 6))
		input.text_submitted.connect(func(text: String) -> void:
			_commit_numeric_input(lever, text, is_int, lo2, hi2))
		direct.add_child(input)
		var apply := _btn("@{desktop.main.fragment.e83ac7975d285b2e}", func() -> void:
			_commit_numeric_input(lever, input.text, is_int, lo2, hi2))
		apply.tooltip_text = "@{desktop.main.fragment.161b6e0c65686598}\n@{desktop.main.fragment.d113838bdbc7c9dd}"
		direct.add_child(apply)
		wrap.add_child(direct)
		wrap.add_child(_lbl("@{desktop.main.fragment.4b666fe3e1b99945} %s · @{desktop.main.fragment.fedab312d817edf3} %s – %s" % [
			_lever_raw_value_text(lever, cur), _lever_raw_value_text(lever, lo),
			_lever_raw_value_text(lever, hi)], 9, INK3, true))
	if nullable:
		var nrow := HBoxContainer.new()
		nrow.add_theme_constant_override("separation", 7)
		var nb := Button.new()
		nb.add_theme_font_size_override("font_size", 11)
		if cur == null:
			nb.text = "@{desktop.main.fragment.cc14fa9eb31a437b}"
			nb.pressed.connect(func() -> void:
				_set_policy_edit(lever, lo))
		else:
			nb.text = "@{desktop.main.fragment.b91ee99c241f7afd}"
			nb.pressed.connect(func() -> void:
				_set_policy_edit(lever, null))
		nrow.add_child(nb)
		nrow.add_child(_lbl("@{desktop.main.fragment.2f5f1d6fbfb061ed} = @{desktop.main.fragment.3240bf1b9d8bd477}", 10, INK3))
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
		cb.text = "@{desktop.main.fragment.d5dba4d0099fea49}" if on else "@{desktop.main.fragment.816ccd6acc7c1848}"
		cb.add_theme_font_size_override("font_size", 11)
		var target := i
		cb.pressed.connect(func() -> void:
			var next: Array = selected.duplicate()
			if next.has(target):
				next.erase(target)
			else:
				next.append(target)
			next.sort()
			_set_policy_edit(_lever_info.get(name, {}), next))
		r.add_child(cb)
		wrap.add_child(row)
	wrap.add_child(_lbl("OR @{desktop.main.fragment.becb5df9dbcbfe12}:@{desktop.main.fragment.f7516d377d702735}(@{desktop.main.fragment.d1201225f541f361})", 10, INK3))
	return wrap


func _economy_id_control(name: String, cur: Variant, choices: Array) -> Control:
	var seg := HBoxContainer.new()
	seg.add_theme_constant_override("separation", 3)
	var opts: Array = choices if not choices.is_empty() else [1, 2, null]
	for opt in opts:
		var b := Button.new()
		b.text = "@{desktop.main.fragment.03b6f87d3f3f5f29}" if opt == null else _country_name(int(opt))
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var same := (cur == null and opt == null) or \
			(cur != null and opt != null and int(cur) == int(opt))
		if same:
			b.add_theme_stylebox_override("normal", _sb(TEAL_BG, TEAL_BD, 6, 6))
			b.add_theme_color_override("font_color", TEAL_DK)
		var value: Variant = opt
		b.pressed.connect(func() -> void:
			_set_policy_edit(_lever_info.get(name, {}), value))
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
	if _free_policy_enabled():
		_sync_free_policy_queue()
	_render()


func _sync_free_policy_queue() -> void:
	if not _free_policy_enabled():
		return
	var actions: Array = []
	for item: Dictionary in _cart:
		actions.append({
			"lever": str(item.get("lever", "")),
			"value": item.get("value"),
		})
	_send({"command": "stage_policy", "actions": actions})


func _render_cart(open: bool) -> void:
	var items := _n["cart_items"] as VBoxContainer
	for c in items.get_children():
		c.queue_free()
	var free_policy := _free_policy_enabled()
	_set_text("cart_title", "@desktop.free.queue_title" if free_policy else "@{desktop.main.fragment.788dc700d8faa6eb}")
	_set_text("cart_count", "%d @{desktop.main.fragment.49ccde43a1549791}" % _cart.size())
	var admin_total := 0.0
	for cart_item: Dictionary in _cart:
		var info: Dictionary = _lever_info.get(str(cart_item.get("lever")), {})
		admin_total += float(info.get("admin_weight", 0.0))
	_set_text("cart_cost", (
		"" if _cart.is_empty() else LocaleCatalogScript.text("desktop.free.next_day")
	) if free_policy else (
		"" if _cart.is_empty() else "@{desktop.main.fragment.1fb9f23e95936512} %.1f" % admin_total))
	if _cart.is_empty():
		items.add_child(_lbl(
			"@desktop.free.empty"
			if free_policy else
			"@{desktop.main.fragment.4bbfdd102a0e912e}",
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
			r.add_child(_lbl("@{desktop.main.fragment.1a53e1bf07e33fd4}", 9, AMBER))
		r.add_child(_lbl(str(c["from"]), 11, Color("586a7b"), true))
		r.add_child(_lbl("→", 11, TEAL))
		r.add_child(_lbl(str(c["to"]), 11, TEAL_DK, true))
		var edit := Button.new()
		edit.text = "@{desktop.main.fragment.051836569928a9f9}"
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
	subb.text = (
		LocaleCatalogScript.format("desktop.free.advance_apply", _cart.size())
		if not _cart.is_empty() else
		LocaleCatalogScript.text("desktop.free.advance")
	) if free_policy else (
		"@{desktop.main.fragment.bed494cc5491181a}(%d)" % _cart.size()
		if not _cart.is_empty() else "@{desktop.main.fragment.bed494cc5491181a}")
	subb.disabled = not open or _cart.is_empty()
	var pass_button := _n["pass"] as Button
	pass_button.text = LocaleCatalogScript.text("desktop.free.clear") \
		if free_policy else "@{desktop.main.fragment.1966f4dfc00757e5}"
	pass_button.disabled = not open or (free_policy and _cart.is_empty())


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
	var ok := status.begins_with("accepted") or status in [
		"noop", "staged", "effective", "cleared"]
	var status_cn: String = {
		"staged": LocaleCatalogScript.text("desktop.free.verdict_staged"),
		"effective": LocaleCatalogScript.text("desktop.free.verdict_effective"),
		"cleared": LocaleCatalogScript.text("desktop.free.verdict_cleared"),
		"accepted_pending": "@{desktop.main.fragment.5086395efca32968} · @{desktop.main.fragment.16f658a708c19d5d}",
		"accepted_effective": "@{desktop.main.fragment.5086395efca32968} · @{desktop.main.fragment.d537d79bda2cbe31}",
		"accepted_noop": "@{desktop.main.fragment.219de38dec04f366} · @{desktop.main.fragment.ccc7db219beb1b65}",
		"accepted": "@{desktop.main.fragment.3420edb1c6f54235}",
		"rejected": "@{desktop.main.fragment.91a2cc776c3e7abe}",
		"cancelled": "@{desktop.main.fragment.20867bd9171988f8}",
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
		sub += ("" if sub.is_empty() else " · ") + "%s @{desktop.main.fragment.c997444643299f36}" % _cal_str(et)
	var cost := float(v.get("adjustment_cost", 0.0))
	var admin := float(v.get("reserved_admin_cost", 0.0))
	if cost > 0.0 or admin > 0.0:
		sub += ("" if sub.is_empty() else " · ") + "@{desktop.main.fragment.a9b6ed2a4fe759b2} %.2f / @{desktop.main.fragment.1fb9f23e95936512} %.2f" % [cost, admin]
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
	if _free_policy_enabled():
		_sync_free_policy_queue()
		_show_hint(LocaleCatalogScript.format(
			"desktop.free.queued_hint", _cart.size()))
		_send({"command": "advance", "ticks": 1})
		return
	_show_hint("@{desktop.main.fragment.1035301822dc0bca} %d @{desktop.main.fragment.7a1b24ce9ff18c46},@{desktop.main.fragment.ced0f218babe28f7},@{desktop.main.fragment.c37e7cec46810691}" % _cart.size())
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
	if _free_policy_enabled():
		_cart.clear()
		_edits.clear()
		_sync_free_policy_queue()
		_render()
		return
	for ctx: Dictionary in _contexts():
		_send({"command": "resolve_context",
			"context_id": str(ctx.get("context_id")), "actions": []})
	_cart.clear()
	_edits.clear()


#  Synchronization helper.
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


func _canonical_entity_id(value: Variant) -> String:
	if value is int:
		return str(int(value))
	if value is float and is_equal_approx(float(value), roundf(float(value))):
		return str(int(roundf(float(value))))
	return str(value)


func _firm_display_id(firm: Dictionary) -> String:
	var symbol := str(firm.get("symbol", ""))
	if not symbol.is_empty():
		return symbol
	var firm_id := _canonical_entity_id(firm.get("firm_id", ""))
	return "F%04d" % int(firm_id) if firm_id.is_valid_int() else firm_id


func _open_firm(firm_id: Variant) -> void:
	var canonical_id := _canonical_entity_id(firm_id)
	if canonical_id.is_empty():
		return
	_firm_selected = canonical_id
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
	top.add_child(_household_summary_card("HOUSEHOLDS · @{desktop.main.fragment.a70a77c75b1dc74f}",
		str(int(summary.get("household_count", 0))), TEAL, "@{desktop.main.fragment.e79bc08ca05db2c5}"))
	top.add_child(_household_summary_card("POPULATION · @{desktop.main.fragment.6e6d6ddbb7c1a453}",
		str(int(summary.get("population", 0))), BLUE, "@{desktop.main.fragment.50f5d65d57290f75}"))
	top.add_child(_household_summary_card("ASSETS · @{desktop.main.fragment.cce7e7779e0b03eb}",
		_fmt_val("num", float(summary.get("total_assets", 0.0))), PURPLE))
	top.add_child(_household_summary_card("DEBT · @{desktop.main.fragment.defbe45aeb8fe825}",
		_fmt_val("num", float(summary.get("total_debt", 0.0))), AMBER))
	body.add_child(top)

	var toolbar := PanelContainer.new()
	toolbar.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 10, 6))
	var tools := HBoxContainer.new()
	tools.add_theme_constant_override("separation", 6)
	toolbar.add_child(tools)
	tools.add_child(_lbl("@{desktop.main.fragment.ad667e9d4d328745}", 11, INK))
	tools.add_child(_chip("MICRODATA · @{desktop.main.fragment.ed66a2d79e1451a0}", Color("5a36a8"),
		Color("f3effc"), Color("d8ccf0"), 8))
	tools.add_child(_spacer_h())
	var search := LineEdit.new()
	search.custom_minimum_size.x = 155
	search.placeholder_text = "@{desktop.main.fragment.a975674660df1cac} / @{desktop.main.fragment.6e6d6ddbb7c1a453}ID · @{desktop.main.fragment.fa6686e96460ad32}"
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
	for sort_spec: Array in [["net_worth", "@{desktop.main.fragment.be2f841884cb268c}"], ["members", "@{desktop.main.fragment.6e6d6ddbb7c1a453}"], ["debt", "@{desktop.main.fragment.2a5946bee7716fae}"]]:
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
		empty.add_child(_lbl("@{desktop.main.fragment.02b896a6e57c3b4b}", 11, INK3))
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
		entry.text = "@{desktop.main.fragment.a70a77c75b1dc74f} #%03d  ·  %d @{desktop.main.fragment.50f5d65d57290f75}\n@{desktop.main.fragment.cce7e7779e0b03eb} %s  ·  @{desktop.main.fragment.2a5946bee7716fae} %s" % [
			household_id, int(item.get("member_count", 0)),
			_fmt_val("num", float((item.get("assets", {}) as Dictionary).get("total", 0.0))),
			_fmt_val("num", float(item.get("debt", 0.0)))]
		entry.add_theme_font_size_override("font_size", 8)
		entry.add_theme_stylebox_override("normal", _sb(
			Color("eef5ff") if active else Color.WHITE,
			BLUE_BD if active else Color("dfe6ee"), 9, 7, 3 if active else 0))
		entry.add_theme_color_override("font_color", Color("1f4f91") if active else INK2)
		entry.tooltip_text = "@{desktop.main.fragment.40e7d4ff17b61ddb} #%03d @{desktop.main.fragment.a436c03f4c4f9dcf}" % household_id
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
	title.add_child(_lbl("@{desktop.main.fragment.a70a77c75b1dc74f} #%03d" % household_id, 15, INK))
	if bool(household.get("is_public_guardian", false)):
		title.add_child(_chip("@{desktop.main.fragment.c3bae215e4e3c22e}", Color("9a6812"), AMBER_BG, AMBER_BD, 8))
	title.add_child(_chip("%d @{desktop.main.fragment.2b1b34438e7bef46}" % int(household.get("member_count", 0)),
		TEAL_DK, TEAL_BG, TEAL_BD, 8))
	title.add_child(_spacer_h())
	title.add_child(_lbl("@{desktop.main.fragment.2df59604068d1179} %s" % as_of_date, 8, INK3, true))
	header_col.add_child(title)
	var asset: Dictionary = household.get("assets", {})
	var metrics := HBoxContainer.new()
	metrics.add_theme_constant_override("separation", 6)
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.cce7e7779e0b03eb}",
		_fmt_val("num", float(asset.get("total", 0.0))), TEAL))
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.2a5946bee7716fae}",
		_fmt_val("num", float(household.get("debt", 0.0))), AMBER))
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.be2f841884cb268c}",
		_fmt_val("num", float(household.get("net_worth", 0.0))), PURPLE))
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.2206a38da9b66c95}",
		_fmt_val("num", float(household.get("consumption", 0.0))), BLUE))
	header_col.add_child(metrics)
	var allocation := _HouseholdAssetBar.new()
	allocation.values = asset
	allocation.font = _sans
	allocation.custom_minimum_size = Vector2(0, 48)
	header_col.add_child(allocation)
	parent.add_child(header)

	var member_head := HBoxContainer.new()
	member_head.add_child(_lbl("MEMBERS · @{desktop.main.fragment.ee653d17be237793}", 9, INK3, true))
	var members: Array = household.get("members", []).duplicate()
	var target_present := false
	for member: Dictionary in members:
		if int(member.get("person_id", -1)) == _person_selected:
			target_present = true
			break
	if target_present:
		member_head.add_child(_chip("@{desktop.main.fragment.47ed180be4d6f265} P%03d" % _person_selected,
			Color("285ca8"), BLUE_BG, BLUE_BD, 7))
	member_head.add_child(_spacer_h())
	member_head.add_child(_lbl("@{desktop.main.fragment.8b75b585e8e109ae}", 8, INK3))
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
	var sex_id := str(member.get(
		"sex_id",
		"female" if str(member.get("sex", "")) == "F"
		else "male" if str(member.get("sex", "")) == "M"
		else "unknown"))
	var sex_text := _domain_text("sex", sex_id)
	var sex_color := Color("c17b16") if sex_id == "female" else Color("3274d9")
	var identity := HBoxContainer.new()
	identity.add_theme_constant_override("separation", 6)
	identity.add_child(_dot(sex_color, 8))
	identity.add_child(_lbl("@{desktop.main.fragment.6e6d6ddbb7c1a453} P%03d" % int(member.get("person_id", 0)), 12, INK, true))
	identity.add_child(_chip("%s · %d @{desktop.main.fragment.43e84a7a98a4fc35}" % [sex_text, int(member.get("age", 0))],
		sex_color.darkened(0.18), Color(sex_color.r, sex_color.g, sex_color.b, 0.09),
		Color(sex_color.r, sex_color.g, sex_color.b, 0.32), 8))
	identity.add_child(_chip(_row_domain_text(
		member, "relationship", "relationship_id", "relationship", "member"),
		TEAL_DK, TEAL_BG, TEAL_BD, 8))
	if focused:
		identity.add_child(_chip("@{desktop.main.fragment.48fdfedb9384a927}", Color("285ca8"), BLUE_BG, BLUE_BD, 8))
	identity.add_child(_spacer_h())
	identity.add_child(_chip(_row_domain_text(
		member, "labor_state", "labor_status_id", "labor_status", "unknown"),
		INK2, PANEL2, LINE2, 8))
	col.add_child(identity)
	var links: Array[String] = []
	if member.get("mother_id") != null:
		links.append("@{desktop.main.fragment.1a3205c3a91ea555} P%03d" % int(member.get("mother_id")))
	if member.get("father_id") != null:
		links.append("@{desktop.main.fragment.ca4c64d9ae27fa4a} P%03d" % int(member.get("father_id")))
	if member.get("partner_id") != null:
		links.append("@{desktop.main.fragment.7c4bbd93aa6e2e18} P%03d" % int(member.get("partner_id")))
	if member.get("guardian_id") != null:
		links.append("@{desktop.main.fragment.10dde3dd123a4243} P%03d" % int(member.get("guardian_id")))
	var demographic := "@{desktop.main.fragment.7e3781ea90e9583f} %s · %s" % [
		str(member.get("birth_date", "—")),
		_row_domain_text(
			member, "marital_status", "marital_status_id",
			"marital_status", "unknown")]
	if not links.is_empty():
		demographic += " · " + " / ".join(links)
	col.add_child(_lbl(demographic, 8, INK3, true))

	var assets: Dictionary = member.get("assets", {})
	var finance := HBoxContainer.new()
	finance.add_theme_constant_override("separation", 5)
	finance.add_child(_household_summary_card("@{desktop.main.fragment.9ec10ddf5fc84f39}",
		_fmt_val("num", float(assets.get("total", 0.0))), TEAL))
	finance.add_child(_household_summary_card("@{desktop.main.fragment.b01b38c4ad1087c8}",
		_fmt_val("num", float(member.get("debt", 0.0))), AMBER))
	finance.add_child(_household_summary_card("@{desktop.main.fragment.43bfdd9c9c47d5c1}",
		_fmt_val("num", float(member.get("net_worth", 0.0))), PURPLE))
	finance.add_child(_household_summary_card("@{desktop.main.fragment.2206a38da9b66c95}",
		_fmt_val("num", float(member.get("consumption", 0.0))), BLUE))
	col.add_child(finance)
	col.add_child(_lbl("@{desktop.main.fragment.190f51d6d2301b94}  @{desktop.main.fragment.118f18e6840546c1} %s · @{desktop.main.fragment.22e64656444bc55f} %s · @{desktop.main.fragment.20646c88cdfdcf6b} %s · @{desktop.main.fragment.9dc4139eaedd31c5} %s" % [
		_fmt_val("num", float(assets.get("cash", 0.0))),
		_fmt_val("num", float(assets.get("firm_equity", 0.0))),
		_fmt_val("num", float(assets.get("bank_equity", 0.0))),
		_fmt_val("num", float(assets.get("bonds", 0.0)))], 8, INK2, true))
	var income: Dictionary = member.get("income", {})
	var work_text := "@{desktop.main.fragment.117d8f914d8e21a1}  @{desktop.main.fragment.e82f854c8903d9f7} %s · @{desktop.main.fragment.59831fc48b368a54} %s · @{desktop.main.fragment.ae7c4c83caeb18a5} %s" % [
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
		employment_links.add_child(_lbl("@{desktop.main.fragment.a88316fab089cc26}", 8, INK3, true))
		for employment: Dictionary in employers:
			var firm_id := _canonical_entity_id(employment.get("firm_id", ""))
			var link := Button.new()
			link.text = "%s ↗  %s · %s/%s · %.2f FTE" % [
				firm_id, _sector_text(employment),
				_row_domain_text(
					employment, "contract", "contract_id", "contract", "unknown"),
				_row_domain_text(
					employment, "employment_status", "status_id", "status", "active"),
				float(employment.get("hours", 0.0))]
			link.add_theme_font_size_override("font_size", 8)
			link.add_theme_color_override("font_color", Color("285ca8"))
			link.add_theme_stylebox_override("normal", _sb(Color("eef5ff"), Color("c9dcf5"), 7, 4))
			link.add_theme_stylebox_override("hover", _sb(Color("e2eeff"), BLUE_BD, 7, 4, 2))
			link.tooltip_text = "@{desktop.main.fragment.c771248e511fbf93} %s @{desktop.main.fragment.f174790c7949fe48}" % firm_id
			link.pressed.connect(func() -> void:
				_open_firm(firm_id))
			employment_links.add_child(link)
		col.add_child(employment_links)
	return card


func _firm_number(value: Variant, kind: String = "num") -> String:
	if value == null:
		return "@{desktop.main.fragment.2746d995801b1cc8}"
	return _fmt_val(kind, float(value))


func _optional_number(value: Variant, fallback := 0.0) -> float:
	if value == null or not (value is int or value is float):
		return fallback
	return float(value)


func _firm_sector_color(sector_code: String) -> Color:
	return {
		"necessity": TEAL,
		"luxury": PURPLE,
		"consumption": BLUE,
		"capital": Color("4a6fa5"),
		"energy": Color("b56b0b"),
		"housing": Color("8a6b50"),
		"bank": Color("7a54b3"),
		"banking": Color("7a54b3"),
	}.get(sector_code, INK3)


func _firm_sort_value(item: Dictionary) -> float:
	match _firm_sort:
		"earnings":
			return _optional_number(
				(item.get("operations", {}) as Dictionary).get("earnings"))
		"assets":
			return _optional_number(
				(item.get("balance_sheet", {}) as Dictionary).get("gross_assets"))
		_:
			return _optional_number(
				(item.get("operations", {}) as Dictionary).get("revenue"))


func _firm_matches(item: Dictionary) -> bool:
	var query := _firm_search.strip_edges().to_lower()
	if query.is_empty():
		return true
	for text in [
		item.get("firm_id", ""),
		_firm_display_id(item),
		item.get("sector_id", item.get("sector", "")),
			_sector_text(item),
			item.get("condition_id", item.get("condition", "")),
			_condition_text(item),
	]:
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
	top.add_child(_household_summary_card("FIRMS · @{desktop.main.fragment.409d0719010a46ee}",
		str(int(summary.get("firm_count", 0))), TEAL, "@{desktop.main.fragment.c8ae97be80f3867c}"))
	top.add_child(_household_summary_card("EMPLOYMENT · @{desktop.main.fragment.1d5c46b3a1725a35}",
		"%.1f" % float(summary.get("employment_fte", 0.0)), BLUE, "FTE"))
	top.add_child(_household_summary_card("REVENUE · @{desktop.main.fragment.0cd72d69cc8bc116}",
		_fmt_val("num", float(summary.get("total_revenue", 0.0))), PURPLE))
	top.add_child(_household_summary_card("EARNINGS · @{desktop.main.fragment.d401d3b11b80d307}",
		_fmt_val("num", float(summary.get("total_earnings", 0.0))), AMBER))
	body.add_child(top)

	var toolbar := PanelContainer.new()
	toolbar.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 10, 6))
	var tools := HBoxContainer.new()
	tools.add_theme_constant_override("separation", 6)
	toolbar.add_child(tools)
	tools.add_child(_lbl("@{desktop.main.fragment.49c6520ca010dad7}", 11, INK))
	tools.add_child(_chip("LIVE BOOKS · @{desktop.main.fragment.cd7ccd9c05c642a7}", Color("285ca8"),
		Color("eef5ff"), Color("c9dcf5"), 8))
	tools.add_child(_spacer_h())
	var search := LineEdit.new()
	search.custom_minimum_size.x = 145
	search.placeholder_text = "@{desktop.main.fragment.409d0719010a46ee} / @{desktop.main.fragment.f128cdf1dae21223} / @{desktop.main.fragment.a1f5d5fcbdc4d510}ID · @{desktop.main.fragment.fa6686e96460ad32}"
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
	for sort_spec: Array in [["revenue", "@{desktop.main.fragment.c5678fcca666b891}"], ["earnings", "@{desktop.main.fragment.86df9b5b13baec22}"], ["assets", "@{desktop.main.fragment.5f45bb826b168fde}"]]:
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
		empty.add_child(_lbl("@{desktop.main.fragment.8057cc6b5612788c}", 11, INK3))
		body.add_child(empty)
		return
	var selected_found := false
	for item: Dictionary in items:
		if _canonical_entity_id(item.get("firm_id", "")) == _firm_selected:
			selected_found = true
			break
	if not selected_found:
		_firm_selected = _canonical_entity_id(
			(items[0] as Dictionary).get("firm_id", ""))

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
		var firm_id := _canonical_entity_id(item.get("firm_id", ""))
		var firm_display_id := _firm_display_id(item)
		var active := firm_id == _firm_selected
		if active:
			selected = item
		var operations: Dictionary = item.get("operations", {})
		var labor: Dictionary = item.get("labor", {})
		var entry := Button.new()
		entry.custom_minimum_size = Vector2(188, 57)
		entry.alignment = HORIZONTAL_ALIGNMENT_LEFT
		entry.text = "%s  ·  %s\n@{desktop.main.fragment.c5678fcca666b891} %s  ·  @{desktop.main.fragment.86df9b5b13baec22} %s  ·  %.1f FTE" % [
			firm_display_id, _sector_text(item),
			_firm_number(operations.get("revenue")),
			_firm_number(operations.get("earnings")),
			float(labor.get("employment_fte", 0.0))]
		entry.add_theme_font_size_override("font_size", 8)
		entry.add_theme_stylebox_override("normal", _sb(
			Color("eef5ff") if active else Color.WHITE,
			BLUE_BD if active else Color("dfe6ee"), 9, 7, 3 if active else 0))
		entry.add_theme_color_override("font_color", Color("1f4f91") if active else INK2)
		entry.tooltip_text = "@{desktop.main.fragment.db8db0530432bd15} %s @{desktop.main.fragment.9eebf5bc000570d2}" % firm_display_id
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
	var sector_id := str(firm.get(
		"sector_id", firm.get("sector_code", firm.get("sector", "unknown"))))
	var sector_color := _firm_sector_color(sector_id)
	var condition_id := str(firm.get(
		"condition_id", firm.get("condition", "unknown")))
	var condition := _condition_text(firm)
	var condition_color := GREEN if condition_id in ["operating", "trading"] else RED

	var header := PanelContainer.new()
	header.add_theme_stylebox_override("panel", _sb(Color("f9fbfd"), Color("dce5ee"), 11, 9, 4))
	var header_col := VBoxContainer.new()
	header_col.add_theme_constant_override("separation", 6)
	header.add_child(header_col)
	var title := HBoxContainer.new()
	title.add_child(_dot(sector_color, 8))
	title.add_child(_lbl(_firm_display_id(firm), 15, INK, true))
	title.add_child(_chip(_sector_text(firm),
		sector_color.darkened(0.15), Color(sector_color.r, sector_color.g, sector_color.b, 0.09),
		Color(sector_color.r, sector_color.g, sector_color.b, 0.30), 8))
	if bool(firm.get("state_owned", false)):
		title.add_child(_chip("@{desktop.main.fragment.7abe5186f9e43a4f}", Color("9a6812"), AMBER_BG, AMBER_BD, 8))
	title.add_child(_chip(condition, condition_color.darkened(0.12),
		Color(condition_color.r, condition_color.g, condition_color.b, 0.09),
		Color(condition_color.r, condition_color.g, condition_color.b, 0.28), 8))
	title.add_child(_spacer_h())
	title.add_child(_lbl("@{desktop.main.fragment.2df59604068d1179} %s" % as_of_date, 8, INK3, true))
	header_col.add_child(title)
	var metrics := HBoxContainer.new()
	metrics.add_theme_constant_override("separation", 6)
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.64cde6f0e91e6075}",
		_firm_number(operations.get("revenue")), TEAL))
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.38c8b7cc8eb104d8}",
		_firm_number(operations.get("earnings")), AMBER))
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.cce7e7779e0b03eb}",
		_firm_number(book.get("gross_assets")), PURPLE))
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.5b7fff09607b842c}",
		_firm_number(book.get("debt")), BLUE))
	header_col.add_child(metrics)
	var bank_text := "@{desktop.main.fragment.96244265daad22c3} %s · @{desktop.main.fragment.2478189c98835384} %s" % [
		str(bank.get("bank_id", "@{desktop.main.fragment.484d55613910eb8c}")), _firm_number(bank.get("loan_rate"), "pt")]
	var identity_text := "@{desktop.main.fragment.4aa1a3c6743f7d8e} %s · @{desktop.main.fragment.aea82737cc01867d} %s · %s · %s" % [
		str(firm.get("technology", "—")), str(firm.get("sells", "—")),
		"@{desktop.main.fragment.8f7a04462c1a9ca1}" if bool(firm.get("invests", false)) else "@{desktop.main.fragment.cfe9174e514ae6e4}",
		"@{desktop.main.fragment.5bf5a63f1a877c6d}" if bool(equity.get("enabled", false)) else "@{desktop.main.fragment.fb08d8804ef10514}"]
	header_col.add_child(_lbl(identity_text + "   |   " + bank_text, 8, INK3, true))
	parent.add_child(header)

	_firm_section_head(parent, "OPERATIONS · @{desktop.main.fragment.728d2ec69c3d5351}", "@{desktop.main.fragment.0f6b1949b093e352} → @{desktop.main.fragment.76ab7d3b41f2326d} → @{desktop.main.fragment.f04b061471b1fd16} → @{desktop.main.fragment.780c5fd5b10533dc}")
	var operating_metrics := HBoxContainer.new()
	operating_metrics.add_theme_constant_override("separation", 5)
	for spec: Array in [
		["@{desktop.main.fragment.e3683d8bf1807c73}", operations.get("demand_expected"), TEAL],
		["@{desktop.main.fragment.a7a232bc82286590}", operations.get("production_target"), BLUE],
		["@{desktop.main.fragment.a98c596e050c6caf}", operations.get("produced"), PURPLE],
		["@{desktop.main.fragment.7c348c349ca33032}", operations.get("sales"), AMBER],
	]:
		operating_metrics.add_child(_household_summary_card(
			str(spec[0]), _firm_number(spec[1]), spec[2]))
	parent.add_child(operating_metrics)
	var operating_panels := HBoxContainer.new()
	operating_panels.add_theme_constant_override("separation", 7)
	operating_panels.add_child(_firm_data_panel("PRICE & MARGIN · @{desktop.main.fragment.ad404ac387ebabc1}", [
		["@{desktop.main.fragment.4ea47b184e0109b9}", _firm_number(operations.get("price"))],
		["@{desktop.main.fragment.c6c5ff02c8fd0341}", _firm_number(operations.get("wage"))],
		["@{desktop.main.fragment.7bcb26c545e304ac}", _firm_number(operations.get("markup"), "pct")],
		["@{desktop.main.fragment.41a463a21ac72cef}", _firm_number(operations.get("wagebill"))],
		["@{desktop.main.fragment.d1d87bb4f796870c}", _firm_number(operations.get("pricing_capital_unit_cost")) if bool(operations.get("capital_service_pricing_enabled", false)) else "@{desktop.main.fragment.2746d995801b1cc8}"],
		["@{desktop.main.fragment.350a9e802ab66c2f}", _firm_number(operations.get("pricing_capital_service_cost")) if bool(operations.get("capital_service_pricing_enabled", false)) else "@{desktop.main.fragment.2746d995801b1cc8}"],
		["@{desktop.main.fragment.3bf9b5f7a4e449b6}", _firm_number(operations.get("pricing_capital_service_rate"), "pct") if bool(operations.get("capital_service_pricing_enabled", false)) else "@{desktop.main.fragment.2746d995801b1cc8}"],
		["@{desktop.main.fragment.0d06b51c2fc0f7a2}", _firm_number(operations.get("target_inventory"))],
		["@{desktop.main.fragment.e8e79d02cc0e44a6}", _firm_number(operations.get("inventory"))],
		["@{desktop.main.fragment.603465f2eb1bdce0}", _firm_number(operations.get("rationed_demand"))],
	]))
	operating_panels.add_child(_firm_data_panel("REALIZATION · @{desktop.main.fragment.97e728f608e78366}", [
		["@{desktop.main.fragment.b1bde29ead0af532}", _firm_number(operations.get("production_realization"), "pct")],
		["@{desktop.main.fragment.1fa87836d750f23d}", _firm_number(operations.get("sales_realization"), "pct")],
		["@{desktop.main.fragment.a3cdad2d23e23c83}", _firm_number(labor.get("labor_demand_notional"))],
		["@{desktop.main.fragment.f0756220064f45e0}", _firm_number(labor.get("labor_demand_effective"))],
		["@{desktop.main.fragment.7c5bdffca729b39c}", _firm_number(labor.get("efficiency_units"))],
		["@{desktop.main.fragment.8e33aaf8bffffe00}", _firm_number(labor.get("vacancies"))],
		["@{desktop.main.fragment.5df82226ae52ef7d}", "%d @{desktop.main.fragment.49da61ceeea2f271}" % int(labor.get("vacancy_age", 0))],
		["@{desktop.main.fragment.bb8651b67f248073}", str(int(labor.get("active_heads", 0)))],
		["@{desktop.main.fragment.1d5c46b3a1725a35} FTE", "%.2f" % float(labor.get("employment_fte", 0.0))],
	]))
	parent.add_child(operating_panels)

	_firm_section_head(parent, "INCOME STATEMENT · @{desktop.main.fragment.e9de5a8191ae4ed4}",
		"@{desktop.main.fragment.f1916d5a7b4c4091}" if bool(pnl.get("full_statement", false)) else "@{desktop.main.fragment.6f8c90caea8fe61e} · legacy profit")
	var pnl_panels := HBoxContainer.new()
	pnl_panels.add_theme_constant_override("separation", 7)
	pnl_panels.add_child(_firm_data_panel("OPERATING · @{desktop.main.fragment.9fa734fd308d24ff}", [
		["@{desktop.main.fragment.071f96c56f57b206}", _firm_number(pnl.get("revenue")), TEAL],
		["@{desktop.main.fragment.c50a45c58d0f0cee}", _firm_number(pnl.get("revenue_carry_opening"))],
		["@{desktop.main.fragment.2418384af4e161e1}", _firm_number(pnl.get("revenue_carry"))],
		["@{desktop.main.fragment.ec224a16f56eab00}", _firm_number(pnl.get("intermediate_inputs"))],
		["@{desktop.main.fragment.485210992a616033}", _firm_number(pnl.get("compensation"))],
		["EBITDA", _firm_number(pnl.get("ebitda")), PURPLE],
		["@{desktop.main.fragment.318a62c940f464eb}", _firm_number(pnl.get("capital_price"))],
		["@{desktop.main.fragment.7367bcbf15189952}", _firm_number(pnl.get("depreciation"))],
		["EBIT", _firm_number(pnl.get("ebit")), PURPLE],
		["@{desktop.main.fragment.cc0b56deb49b74eb}", _firm_number(pnl.get("pre_tax_income")), AMBER],
	]))
	pnl_panels.add_child(_firm_data_panel("FINANCING · @{desktop.main.fragment.dff4462c3b421652}", [
		["@{desktop.main.fragment.aabfcbca00157bd0}", _firm_number(pnl.get("interest_accrued"))],
		["@{desktop.main.fragment.522fba731ad97ddd}", _firm_number(pnl.get("interest_due"))],
		["@{desktop.main.fragment.1799dfe556a75fa8}", _firm_number(pnl.get("interest_paid"))],
		["@{desktop.main.fragment.2d00a2f975515f8e}", _firm_number(pnl.get("interest_shortfall")), RED],
		["@{desktop.main.fragment.a735518c54f41828}", _firm_number(pnl.get("interest_arrears_opening"))],
		["@{desktop.main.fragment.a5c9b693c9445bd7}", _firm_number(pnl.get("interest_arrears")), RED],
		["@{desktop.main.fragment.b52675c6688e33b4}", _firm_number(pnl.get("profit_tax"))],
		["@{desktop.main.fragment.d3b8be64a0d78358}", _firm_number(pnl.get("windfall_tax"))],
		["@{desktop.main.fragment.766b90a3050e76d1}", _firm_number(pnl.get("net_income")), AMBER],
		["@{desktop.main.fragment.22d78417d1660071}", _firm_number(pnl.get("dividends"))],
		["@{desktop.main.fragment.ab103640e4ae4829}", _firm_number(pnl.get("retained_earnings"))],
	]))
	parent.add_child(pnl_panels)

	_firm_section_head(parent, "BALANCE SHEET · @{desktop.main.fragment.1aaf5d8c339cc79b}", "@{desktop.main.fragment.e1854bd27f6140be} · @{desktop.main.fragment.32f912c4d1359f4e}")
	var book_panels := HBoxContainer.new()
	book_panels.add_theme_constant_override("separation", 7)
	book_panels.add_child(_firm_data_panel("ASSETS · @{desktop.main.fragment.5f45bb826b168fde}", [
		["@{desktop.main.fragment.118f18e6840546c1}", _firm_number(book.get("cash")), TEAL],
		["@{desktop.main.fragment.0f302c8533c5d143}", _firm_number(book.get("capital_value"))],
		["@{desktop.main.fragment.e2401afaf2fec118}", _firm_number(book.get("output_inventory_value"))],
		["@{desktop.main.fragment.20682482079102af}", _firm_number(book.get("work_in_progress_value"))],
		["@{desktop.main.fragment.0d6b4b7817e8ed69}", _firm_number(book.get("input_inventory_value"))],
		["@{desktop.main.fragment.cce7e7779e0b03eb}", _firm_number(book.get("gross_assets")), PURPLE],
	]))
	book_panels.add_child(_firm_data_panel("LIABILITIES & CREDIT · @{desktop.main.fragment.bac9adc1df9582bf}", [
		["@{desktop.main.fragment.5b7fff09607b842c}", _firm_number(book.get("debt")), BLUE],
		["@{desktop.main.fragment.0cd8835322b75655}", _firm_number(book.get("interest_arrears")), RED],
		["@{desktop.main.fragment.91c0d0c18821c431}", _firm_number(book.get("book_equity")), PURPLE],
		["@{desktop.main.fragment.2a880b968579099c}", _firm_number(book.get("eligible_collateral_value"))],
		["@{desktop.main.fragment.c3a198b0f7f53676}", _firm_number(book.get("borrowing_base_proxy"))],
		["@{desktop.main.fragment.06696065e8b93c8f}", _firm_number(book.get("borrowing_base_headroom")), TEAL],
		["@{desktop.main.fragment.cbd4465331d4a053}", _firm_number(book.get("capital_haircut"), "pct")],
		["@{desktop.main.fragment.4461ec6c6adbd0f4}", _firm_number(book.get("inventory_haircut"), "pct")],
	]))
	parent.add_child(book_panels)
	parent.add_child(_firm_data_panel("VALUATION DETAIL · @{desktop.main.fragment.2890260adb7af5fc}", [
		["@{desktop.main.fragment.dba470f82ed56428}", _firm_number(book.get("capital_units"))],
		["@{desktop.main.fragment.3a14efdd342906b0}", _firm_number(book.get("capital_unit_price"))],
		["@{desktop.main.fragment.aa1a48221d7a2f1f}", _firm_number(book.get("output_inventory_units"))],
		["@{desktop.main.fragment.a6e7baf53a18bd19}", _firm_number(book.get("output_inventory_unit_price"))],
		["@{desktop.main.fragment.4d46f27ebc324b8c}", _firm_number(book.get("work_in_progress_units"))],
		["@{desktop.main.fragment.0175915995cd3e01}", _firm_number(book.get("input_inventory_units"))],
	], "@{desktop.main.fragment.10a80ff2ef6536ee}"))

	_firm_section_head(parent, "CAPITAL & ENERGY · @{desktop.main.fragment.298a82054f4333d0}")
	var capital_panels := HBoxContainer.new()
	capital_panels.add_theme_constant_override("separation", 7)
	capital_panels.add_child(_firm_data_panel("CAPITAL · @{desktop.main.fragment.0f302c8533c5d143}", [
		["@{desktop.main.fragment.dba470f82ed56428}", _firm_number(capital.get("units"))],
		["@{desktop.main.fragment.24e6130455bd30ec}", _firm_number(capital.get("previous_units"))],
		["@{desktop.main.fragment.acbbbe6ae7081918}", _firm_number(capital.get("investment_target")) if bool(firm.get("invests", false)) else "@{desktop.main.fragment.2746d995801b1cc8}"],
		["@{desktop.main.fragment.81f6c5c209a6df49}", _firm_number(capital.get("investment")) if bool(firm.get("invests", false)) else "@{desktop.main.fragment.2746d995801b1cc8}"],
		["@{desktop.main.fragment.3a14efdd342906b0}", _firm_number(book.get("capital_unit_price"))],
		["@{desktop.main.fragment.c3651a9d267f05f9}", _firm_number(capital.get("depreciation_rate"), "pct") if bool(firm.get("invests", false)) else "@{desktop.main.fragment.2746d995801b1cc8}"],
		["@{desktop.main.fragment.216b769329454cc7}", _firm_number(capital.get("capacity")) if str(firm.get("sector_code", "")) == "energy" else "@{desktop.main.fragment.2746d995801b1cc8}"],
	]))
	capital_panels.add_child(_firm_data_panel("ENERGY INPUT · @{desktop.main.fragment.333a81b9da7feff0}", [
		["@{desktop.main.fragment.74a281ff68b56ada}", _firm_number(capital.get("energy_input_stock")) if str(firm.get("sector_code", "")) != "energy" else "@{desktop.main.fragment.2746d995801b1cc8}"],
		["@{desktop.main.fragment.4fd24f52729ab2b1}", _firm_number(capital.get("energy_input_stock_cost")) if str(firm.get("sector_code", "")) != "energy" else "@{desktop.main.fragment.2746d995801b1cc8}"],
		["@{desktop.main.fragment.a1fa98b21ff6d725}", _firm_number(capital.get("energy_input_average_cost")) if str(firm.get("sector_code", "")) != "energy" else "@{desktop.main.fragment.2746d995801b1cc8}"],
		["@{desktop.main.fragment.3d6e09387320b0f9}", _firm_number(capital.get("energy_bought")) if str(firm.get("sector_code", "")) != "energy" else "@{desktop.main.fragment.2746d995801b1cc8}"],
		["@{desktop.main.fragment.8e5125d4af08e3fc}", _firm_number(capital.get("energy_used")) if str(firm.get("sector_code", "")) != "energy" else "@{desktop.main.fragment.2746d995801b1cc8}"],
		["@{desktop.main.fragment.91d87b06b80472ea}", _firm_number(capital.get("energy_cost_used")) if str(firm.get("sector_code", "")) != "energy" else "@{desktop.main.fragment.2746d995801b1cc8}"],
	]))
	parent.add_child(capital_panels)

	_firm_section_head(parent, "WORKFORCE · @{desktop.main.fragment.1d223584d993a49d}",
		"%d @{desktop.main.fragment.33e4a7c51e662103} · %.2f FTE" % [int(labor.get("contract_count", 0)), float(labor.get("employment_fte", 0.0))])
	parent.add_child(_firm_workforce_panel(labor.get("employees", [])))

	_firm_section_head(parent, "EQUITY & OWNERSHIP · @{desktop.main.fragment.c30ef26f876eea36}",
		"@{desktop.main.fragment.5e1d15ae7877b5c5} · @{desktop.main.fragment.71013b918d5c459f}")
	parent.add_child(_firm_equity_panel(equity))

	_firm_section_head(parent, "MODEL STATE · @{desktop.main.fragment.9bab1c1eecf1d218}", "@{desktop.main.fragment.37cc615063967c90}")
	var parameter_panels := HBoxContainer.new()
	parameter_panels.add_theme_constant_override("separation", 7)
	parameter_panels.add_child(_firm_data_panel("BEHAVIOR · @{desktop.main.fragment.8644d815ac16b1af}", [
		["@{desktop.main.fragment.48b3379895aaff95} λd", _firm_number(parameters.get("demand_adjustment"))],
		["@{desktop.main.fragment.aed83664d1629b0a} φ", _firm_number(parameters.get("inventory_target_ratio"))],
		["@{desktop.main.fragment.20594db239b71bc3} η", _firm_number(parameters.get("markup_adjustment"))],
		["@{desktop.main.fragment.9f67b0cfc23d90d8}", _firm_number(parameters.get("markup_min"), "pct")],
		["@{desktop.main.fragment.38b32010d1d6f612}", _firm_number(parameters.get("markup_max"), "pct")],
		["@{desktop.main.fragment.9745314511c2cf9f} ω", _firm_number(parameters.get("wage_adjustment"))],
		["@{desktop.main.fragment.df6d2bd469a88b08} ρ", _firm_number(parameters.get("dividend_payout_ratio"), "pct")],
		["@{desktop.main.fragment.84acc6a7f702923e}", _firm_number(parameters.get("coordination_cost_slope"))],
	]))
	parameter_panels.add_child(_firm_data_panel("TECH & SIGNALS · @{desktop.main.fragment.9fcf39be6bfe11ab}", [
		["@{desktop.main.fragment.94e7a17c7762184c} a", _firm_number(parameters.get("labor_productivity"))],
		["@{desktop.main.fragment.ca50fa2d89be18c0} A", _firm_number(parameters.get("tfp"))],
		["@{desktop.main.fragment.2b1d7bafa3f0ea6b} α", _firm_number(parameters.get("capital_share"), "pct")],
		["@{desktop.main.fragment.c7ed8c1d97950c31} v", _firm_number(parameters.get("capital_output_target"))],
		["@{desktop.main.fragment.82d5d087f8766ffc} λI", _firm_number(parameters.get("investment_adjustment"))],
		["@{desktop.main.fragment.bcb4ce27872b0a8f}", _firm_number(parameters.get("energy_intensity"))],
		["@{desktop.main.fragment.b4ebd01146aa5850} κ", _firm_number(parameters.get("capacity_kappa"))],
		["@{desktop.main.fragment.a4b37109e521203d}", _firm_number(signals.get("previous_sales"))],
		["@{desktop.main.fragment.aa9d10a173169e4d}", _firm_number(signals.get("previous_hiring"))],
		["@{desktop.main.fragment.81d7c25e0bfcd5a3}", _firm_number(signals.get("previous_effective_labor_demand"))],
		["@{desktop.main.fragment.972bff3759c3cba7}", _firm_number(signals.get("previous_target_inventory"))],
		["@{desktop.main.fragment.f28901dc4184faca}", _firm_number(signals.get("previous_rationed_demand"))],
		["@{desktop.main.fragment.8254bf9ba0967355}", "%d @{desktop.main.fragment.49da61ceeea2f271}" % int(signals.get("sector_switch_pressure", 0))],
		["@{desktop.main.fragment.a108341fd957bd97}", _firm_number(signals.get("dividend_shortfall"))],
			["@{desktop.main.fragment.223968d251413035} / @{desktop.main.fragment.6c179e80e534963c} / @{desktop.main.fragment.8ae5a1586ac58227}", "%d / %d / %d @{desktop.main.fragment.49da61ceeea2f271}" % [
				int(signals.get("idle_ticks", 0)), int(signals.get("insolvent_ticks", 0)),
				int(signals.get("subscale_ticks", 0))],
				RED if condition_id != "operating" else INK],
	]))
	parent.add_child(parameter_panels)


func _firm_workforce_panel(employees: Array) -> Control:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _sb(Color.WHITE, Color("dfe6ee"), 10, 9))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 5)
	panel.add_child(col)
	if employees.is_empty():
		col.add_child(_lbl("@{desktop.main.fragment.a1cf643b1b134052}", 9, INK3))
		return panel
	for i in employees.size():
		var employee: Dictionary = employees[i]
		if i > 0:
			col.add_child(_hrule())
		var sex_id := str(employee.get(
			"sex_id",
			"female" if str(employee.get("sex", "")) == "F"
			else "male" if str(employee.get("sex", "")) == "M"
			else "unknown"))
		var sex_text := _domain_text("sex", sex_id)
		var person_id := int(employee.get("person_id", -1))
		var age_text := "—" if employee.get("age") == null else "%d @{desktop.main.fragment.43e84a7a98a4fc35}" % int(employee.get("age"))
		var household_text := "—" if employee.get("household_id") == null else "@{desktop.main.fragment.a70a77c75b1dc74f} #%03d" % int(employee.get("household_id"))
		var row := HBoxContainer.new()
		row.add_child(_lbl("P%03d · %s · %s" % [person_id, sex_text, age_text], 9, INK, true))
		row.add_child(_chip(_row_domain_text(
			employee, "contract", "contract_id", "contract", "unknown"),
			INK2, PANEL2, LINE2, 7))
		var employment_status_id := str(employee.get(
			"status_id", employee.get("status", "active")))
		if employment_status_id != "active":
			row.add_child(_chip(_domain_text(
				"employment_status", employment_status_id),
				RED, RED_BG, RED_BD, 7))
		row.add_child(_spacer_h())
		row.add_child(_lbl("%.2f FTE" % float(employee.get("hours", 0.0)), 9, TEAL, true))
		var employee_household: Variant = employee.get("household_id")
		var person_link := Button.new()
		person_link.text = "@{desktop.main.fragment.f60282c6d68918d5} ↗"
		person_link.disabled = employee_household == null
		person_link.add_theme_font_size_override("font_size", 8)
		person_link.add_theme_color_override("font_color", Color("285ca8"))
		person_link.add_theme_stylebox_override("normal", _sb(Color("eef5ff"), Color("c9dcf5"), 7, 4))
		person_link.add_theme_stylebox_override("hover", _sb(Color("e2eeff"), BLUE_BD, 7, 4, 2))
		person_link.tooltip_text = "@{desktop.main.fragment.c771248e511fbf93} P%03d @{desktop.main.fragment.e142aa841b836ab7}" % person_id
		person_link.pressed.connect(func() -> void:
			_open_person(person_id, employee_household))
		row.add_child(person_link)
		col.add_child(row)
		var hire_text := str(employee.get("hire_date", ""))
		if hire_text.is_empty() and employee.get("hire_day") != null:
			hire_text = _cal_short(int(employee.get("hire_day")))
		if hire_text.is_empty():
			hire_text = "—"
		col.add_child(_lbl("%s · @{desktop.main.fragment.db69901a9202d20f} %s · @{desktop.main.fragment.06c891807ee3feec} %.2f FTE · @{desktop.main.fragment.e11646a02c1553f6} %s · @{desktop.main.fragment.b5ad66754cde276d} %s · @{desktop.main.fragment.2810c1ae78fdf74e} %.2f · @{desktop.main.fragment.fc792be83b1c575e} %s" % [
			household_text, hire_text,
			float(employee.get("contract_hours", 0.0)), _firm_number(employee.get("locked_wage")),
			_firm_number(employee.get("paid_wage")), float(employee.get("efficiency", 1.0)),
			_firm_number(employee.get("compensation"))], 8, INK3, true))
		if employee.get("suspended_since_tick") != null:
			col.add_child(_lbl("@{desktop.main.fragment.422db1ea9e3b0b29} %s · @{desktop.main.fragment.802a6e8a29d4b7ed} %s · @{desktop.main.fragment.d657d37417081d24}" % [
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
		col.add_child(_lbl("@{desktop.main.fragment.f01f6eee9d3297d8}Q @{desktop.main.fragment.fab604ac9f830cca}", 9, INK3))
		return panel
	var metrics := HBoxContainer.new()
	metrics.add_theme_constant_override("separation", 5)
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.8cfec2d97162292d}", _firm_number(equity.get("share_price")), BLUE))
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.443f68162261153e}", _firm_number(equity.get("market_cap")), TEAL))
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.262b4d2f27d039c7} Q", _firm_number(equity.get("tobin_q"), "idx"), PURPLE))
	metrics.add_child(_household_summary_card("@{desktop.main.fragment.95531b1576d29a5b}/@{desktop.main.fragment.2294d4828398494a}", _firm_number(equity.get("fundamental_per_share")), AMBER))
	col.add_child(metrics)
	col.add_child(_lbl("@{desktop.main.fragment.adb05a0ce851e772} %s · @{desktop.main.fragment.04d9bd6f93637454} %s · @{desktop.main.fragment.9b59e637c83810ab} %s · @{desktop.main.fragment.b3275d61c8f82f90} Q %s · @{desktop.main.fragment.26cf61f1176e547f} %s · @{desktop.main.fragment.579b73a4a9cd6a29} EMA %s" % [
		_firm_number(equity.get("shares_outstanding")),
		_firm_number(equity.get("last_share_price")),
		_firm_number(equity.get("share_trend"), "idx"),
		_firm_number(equity.get("tobin_q_ema"), "idx"),
		_firm_number(equity.get("attractiveness"), "idx"),
		_firm_number(equity.get("residual_income_ema"))], 8, INK3, true))
	var holders: Array = equity.get("shareholders", [])
	var holder_head := HBoxContainer.new()
	holder_head.add_child(_lbl("SHAREHOLDERS · @{desktop.main.fragment.e063878252f1e8b5}", 8, INK3, true))
	holder_head.add_child(_spacer_h())
	holder_head.add_child(_lbl("%d @{desktop.main.fragment.50f5d65d57290f75} · @{desktop.main.fragment.1932dbcadd1440e5} %s" % [
		int(equity.get("shareholder_count", 0)),
		_firm_number(equity.get("ownership_coverage"), "pct")], 8, INK3))
	col.add_child(holder_head)
	if holders.is_empty():
		col.add_child(_lbl("@{desktop.main.fragment.672a37c72db23807}", 8, INK3))
		return panel
	for holder: Dictionary in holders:
		var row := HBoxContainer.new()
		var holder_kind_id := str(holder.get("holder_kind_id", "person"))
		var holder_text := ""
		if holder_kind_id == "household":
			holder_text = "@{desktop.main.fragment.a70a77c75b1dc74f} #%03d" % int(
				holder.get("holder_id", holder.get("household_id", -1)))
		else:
			var household_text := (
				"—" if holder.get("household_id") == null
				else "@{desktop.main.fragment.a70a77c75b1dc74f} #%03d" % int(
					holder.get("household_id")))
			holder_text = "P%03d · %s" % [
				int(holder.get("person_id", -1)), household_text]
		row.add_child(_lbl(holder_text, 8, INK2, true))
		row.add_child(_spacer_h())
		row.add_child(_lbl("%s @{desktop.main.fragment.2294d4828398494a} · %s · @{desktop.main.fragment.7dc0b3b746b81556} %s" % [
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
		_stock_delta_color(index_change), _stock_delta_text(index_change), "@{desktop.main.fragment.881bd789d73af261}"))
	top.add_child(_stock_summary_card("MARKET CAP · @{desktop.main.fragment.443f68162261153e}",
		_fmt_val("num", float(summary.get("market_cap", 0.0))), PURPLE, "",
		"%d @{desktop.main.fragment.72dda437ee3cf19c}" % int(summary.get("listed_count", 0))))
	top.add_child(_stock_summary_card("TURNOVER · @{desktop.main.fragment.a071a060fcb264ca}",
		_fmt_val("pct", float(summary.get("turnover", 0.0))), BLUE, "",
		"@{desktop.main.fragment.36aa5fc5c1cf6c87}"))
	top.add_child(_stock_summary_card("BREADTH · @{desktop.main.fragment.415ca79bb06313d8}",
		"%d ↑  %d ↓" % [int(summary.get("advances", 0)), int(summary.get("declines", 0))],
		TEAL, "", "%d @{desktop.main.fragment.2527ecf9122b145b}" % int(summary.get("unchanged", 0))))
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
	search.placeholder_text = "@{desktop.main.fragment.e6f04ffbaa424001} / @{desktop.main.fragment.37e7edd15ff69fbc} · @{desktop.main.fragment.fa6686e96460ad32}"
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
	for filter_spec: Array in [["all", "@{desktop.main.fragment.5c55a67935af8f45}"], ["company", "@{desktop.main.fragment.78b4f9789537cff0}"], ["bank", "@{desktop.main.fragment.a6e9ec707b3a6c96}"]]:
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
	for sort_spec: Array in [["market_cap", "@{desktop.main.fragment.7dc0b3b746b81556}"], ["change", "@{desktop.main.fragment.4a825a8623a729e2}"]]:
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
		var selected_sector_id := str(selected.get(
			"sector_id", selected.get("sector_code", "unknown")))
		var selected_color := _firm_sector_color(selected_sector_id)
		chart_head.add_child(_chip(_sector_text(selected),
			selected_color.darkened(0.15),
			Color(selected_color.r, selected_color.g, selected_color.b, 0.09),
			Color(selected_color.r, selected_color.g, selected_color.b, 0.28), 7))
	chart_head.add_child(_spacer_h())
	if not selected.is_empty():
		var index_button := Button.new()
		index_button.text = "@{desktop.main.fragment.5db5f3ae9751b3d6}"
		index_button.add_theme_font_size_override("font_size", 8)
		index_button.pressed.connect(func() -> void:
			_stock_selected = ""
			_render())
		chart_head.add_child(index_button)
		if bool(selected.get("can_open_firm", false)):
			var firm_button := Button.new()
			firm_button.text = "@{desktop.main.fragment.f174790c7949fe48} ↗"
			firm_button.add_theme_font_size_override("font_size", 8)
			var selected_issuer_id: Variant = selected.get(
				"issuer_id", selected.get("symbol", ""))
			firm_button.pressed.connect(func() -> void:
				_open_firm(selected_issuer_id))
			chart_head.add_child(firm_button)
	chart_col.add_child(chart_head)
	var chart_change := index_change if selected.is_empty() else float(selected.get("change", 0.0))
	var chart_value := float(summary.get("index_level", 1000.0)) if selected.is_empty() else float(selected.get("price", 0.0))
	var quote_line := HBoxContainer.new()
	quote_line.add_child(_lbl("%.3f" % chart_value, 19, _stock_delta_color(chart_change), true))
	quote_line.add_child(_lbl(_stock_delta_text(chart_change), 9, _stock_delta_color(chart_change), true))
	quote_line.add_child(_spacer_h())
	quote_line.add_child(_lbl("@{desktop.main.fragment.2df59604068d1179} %s" % str(payload.get("as_of_date", "")),
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
	var chart_note := "@{desktop.main.fragment.443f68162261153e} %s · @{desktop.main.fragment.78b4f9789537cff0} %s · @{desktop.main.fragment.a6e9ec707b3a6c96} %s" % [
		_fmt_val("num", float(summary.get("market_cap", 0.0))),
		_fmt_val("num", float(summary.get("corporate_market_cap", 0.0))),
		_fmt_val("num", float(summary.get("bank_market_cap", 0.0)))]
	if not selected.is_empty():
		var valuation: Variant = selected.get("tobin_q") if selected.get("tobin_q") != null else selected.get("price_to_book")
		chart_note = "@{desktop.main.fragment.9efe01f647d67d91} %s – %s · @{desktop.main.fragment.7dc0b3b746b81556} %s · Q/PB %s · @{desktop.main.fragment.c63fcd5ca035e9e5} %s" % [
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
	pulse.add_child(_lbl("SECTORS · @{desktop.main.fragment.625d2024ec712328}", 8, INK3, true))
	for sector: Dictionary in payload.get("sectors", []):
		var sector_row := HBoxContainer.new()
		var sector_change := float(sector.get("change", 0.0))
		sector_row.add_child(_dot(_stock_delta_color(sector_change), 6))
		sector_row.add_child(_lbl(_sector_text(sector), 8, INK2))
		sector_row.add_child(_spacer_h())
		sector_row.add_child(_lbl(_stock_delta_text(sector_change), 8,
			_stock_delta_color(sector_change), true))
		pulse.add_child(sector_row)
	pulse.add_child(_hrule())
	for metric_spec: Array in [
		["@{desktop.main.fragment.eb8030ff262018d3} Q", _firm_number(summary.get("q_mean"), "idx")],
		["@{desktop.main.fragment.d9d82bbc6edcaf71}", _firm_number(summary.get("ownership_gini"), "idx")],
		["@{desktop.main.fragment.22e64656444bc55f}/@{desktop.main.fragment.0192798883e6f270}", _firm_number(summary.get("equity_wealth_share"), "pct")],
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
		if not query.is_empty() \
				and not str(listing.get("symbol", "")).to_lower().contains(query) \
				and not str(listing.get(
					"sector_id", listing.get("sector", ""))).to_lower().contains(query) \
				and not _sector_text(listing).to_lower().contains(query):
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
	quote_head.add_child(_lbl("SECURITIES · @{desktop.main.fragment.d43d3298be5af7a1}", 9, INK, true))
	quote_head.add_child(_spacer_h())
	quote_head.add_child(_lbl("%d / %d · @{desktop.main.fragment.144cda2838b5f44f}" % [visible_listings.size(), listings.size()], 8, INK3))
	quote_col.add_child(quote_head)
	var columns := HBoxContainer.new()
	columns.add_theme_constant_override("separation", 4)
	columns.add_child(_stock_table_cell("@{desktop.main.fragment.e6f04ffbaa424001}", 66, INK3, HORIZONTAL_ALIGNMENT_LEFT))
	columns.add_child(_stock_table_cell("@{desktop.main.fragment.37e7edd15ff69fbc}", 66, INK3, HORIZONTAL_ALIGNMENT_LEFT, false))
	columns.add_child(_stock_table_cell("@{desktop.main.fragment.569af1a47dbdf053}", 58, INK3))
	columns.add_child(_stock_table_cell("@{desktop.main.fragment.4a825a8623a729e2}", 60, INK3))
	columns.add_child(_stock_table_cell("@{desktop.main.fragment.443f68162261153e}", 67, INK3))
	columns.add_child(_stock_table_cell("Q / PB", 52, INK3))
	columns.add_child(_stock_table_cell("@{desktop.main.fragment.26cba1cc99083b9a}", 60, INK3))
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
		rows.add_child(_lbl("@{desktop.main.fragment.caa0ebc7c538da3c}", 9, INK3))
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
		row.add_child(_stock_table_cell(_sector_text(listing), 66, INK2,
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
	header.add_child(_lbl("@{desktop.main.fragment.0cdad50ddeb96889}", 14, INK))
	header.add_child(_spacer_h())
	header.add_child(_chip("@{desktop.main.fragment.697bb3775eddb106} %d / 8" % int(brief["coverage"]),
		TEAL_DK, TEAL_BG, TEAL_BD, 9))
	if int(brief["risk_count"]) > 0:
		header.add_child(_chip("@{desktop.main.fragment.dcdec027dcdab463} %d" % int(brief["risk_count"]),
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
	map_head.add_child(_lbl("@{desktop.main.fragment.894eb82897e90894}", 11, INK_BODY))
	map_head.add_child(_lbl("@{desktop.main.fragment.5bd3b5af44a16b17} × @{desktop.main.fragment.20ea8f201a36f7bb}", 9, INK3, true))
	map_head.add_child(_spacer_h())
	map_head.add_child(_lbl("@{desktop.main.fragment.e3aac624596cf440}", 9, INK3))
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
	judgement.add_child(_lbl("@{desktop.main.fragment.10a7574969435ab6}", 9, INK3, true))
	var phase_label := _lbl(str(brief["phase"]), 19, brief["tone"])
	judgement.add_child(phase_label)
	var summary := _lbl(str(brief["summary"]), 10, INK2)
	summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	judgement.add_child(summary)
	judgement.add_child(_brief_signal("@{desktop.main.fragment.55ab66cb19c98aa6}", str(brief["tension"]),
		brief["tone"]))
	judgement.add_child(_brief_signal("@{desktop.main.fragment.a52b929279f57fa8}", str(brief["transmission"]), BLUE))
	judgement.add_child(_brief_signal("@{desktop.main.fragment.ec386822fda050bb}", str(brief["data_quality"]),
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
	##  Only a combination of published bulletins and open policy status; no unpublished data are read to judge economics.
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
	var phase := "@{desktop.main.fragment.25f6cdf3722d33b8}"
	var summary := "@{desktop.main.fragment.84cf4955e0190f8d}"
	var tension := "@{desktop.main.fragment.476acb20e22ba0e5}"
	var tone: Color = INK2
	if phase_ready:
		if x_value < -0.18 and y_value > 0.18:
			phase = "@{desktop.main.fragment.43b666feeeb6487c}"
			summary = "@{desktop.main.fragment.94fe0a2628b9b099}"
			tension = "@{desktop.main.fragment.229c33d4c5754514}"
			tone = RED
		elif x_value > 0.18 and y_value > 0.18:
			phase = "@{desktop.main.fragment.e8080680ffdb93b6}"
			summary = "@{desktop.main.fragment.6e41791bb639107d}"
			tension = "@{desktop.main.fragment.e2e1e13877a45f55}"
			tone = AMBER
		elif x_value < -0.18 and y_value < -0.18:
			phase = "@{desktop.main.fragment.8ee04f36861892b7}"
			summary = "@{desktop.main.fragment.b097f62c9071787f}"
			tension = "@{desktop.main.fragment.08069470df5a84ab}"
			tone = BLUE
		elif x_value > 0.18 and y_value < -0.18:
			phase = "@{desktop.main.fragment.fea642af5f0c14ef}"
			summary = "@{desktop.main.fragment.c7bbb4c0fdb6d4fa}"
			tension = "@{desktop.main.fragment.0e4117212d5efdd4}"
			tone = TEAL
		elif x_value > 0.18:
			phase = "@{desktop.main.fragment.7dd1811580892144}"
			summary = "@{desktop.main.fragment.d6f5c59075950c0f}"
			tension = "@{desktop.main.fragment.b17d51b68097346f}"
			tone = TEAL
		elif x_value < -0.18:
			phase = "@{desktop.main.fragment.3986d09f96a9a77c}"
			summary = "@{desktop.main.fragment.8085916f54b6e4f9}"
			tension = "@{desktop.main.fragment.14605e0cba8d121e}"
			tone = BLUE
		elif y_value > 0.18:
			phase = "@{desktop.main.fragment.19639ef7cffdbb23}"
			summary = "@{desktop.main.fragment.1c47dbe288f3d070}"
			tension = "@{desktop.main.fragment.6a820e3750a75d55}"
			tone = AMBER
		elif y_value < -0.18:
			phase = "@{desktop.main.fragment.4292d7909760d523}"
			summary = "@{desktop.main.fragment.3d55ddf9c6e0d618}"
			tension = "@{desktop.main.fragment.7ae4c3788c5ea83c}"
			tone = BLUE
		else:
			phase = "@{desktop.main.fragment.03859372e29bb4fa}"
			summary = "@{desktop.main.fragment.c28f9989e90ecc68}"
			tension = "@{desktop.main.fragment.30ea8c0bcc4f1fbe}"
			tone = GREEN
	var pending_count := (_snapshot.get("pending", []) as Array).size()
	var transmission := "@{desktop.main.fragment.b6ee3baba5ccc4f1}"
	if _awaiting():
		transmission = "%d @{desktop.main.fragment.3936297f58ce52f3}" % _contexts().size()
	elif pending_count > 0:
		transmission = "%d @{desktop.main.fragment.b60ebe48c5737db0}" % pending_count
	var data_quality := "@{desktop.main.fragment.aa8baaafe914c574}"
	if coverage > 0:
		data_quality = "%d/8 @{desktop.main.fragment.d334724d6b2fa32e} · @{desktop.main.fragment.8e77e42cf0a2023b} %d @{desktop.main.fragment.49da61ceeea2f271}" % [coverage, max_lag]
		if latest_release >= 0:
			data_quality += " · @{desktop.main.fragment.fb37c61898d5a2c7} %s" % _cal_short(latest_release)
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
	head.add_child(_lbl("CORE 8 · @{desktop.main.fragment.f5cf7610c9234aa0}", 10, INK3, true))
	head.add_child(_spacer_h())
	head.add_child(_lbl("@{desktop.main.fragment.e1cf00d81f03c367} · @{desktop.main.fragment.2c6e0266e1ac28a8} · @{desktop.main.fragment.240e892123e10737} · @{desktop.main.fragment.f69c325544a29bfe} · @{desktop.main.fragment.a42315e416fa2550} · @{desktop.main.fragment.1af7dfd65c353cfc} · @{desktop.main.fragment.6909fc6ad79b398d} · @{desktop.main.fragment.72d71f2db0b4734a}",
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
	card.tooltip_text = "@{desktop.main.fragment.4344b9c932cd2a58}\n@{desktop.main.fragment.c771248e511fbf93}%s" % ("@{desktop.main.fragment.036bf7c22dc51057}" if target_tab == "world" \
		else "「%s@{desktop.main.fragment.bb12a8574625dbe1}" % target_group)
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
		col.add_child(_lbl("@{desktop.main.fragment.98d5200f51face49}", 18, Color("a2adb8"), true))
		col.add_child(_lbl("@{desktop.main.fragment.7d3700550a037943}", 9, INK3))
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
	var source_label := _lbl("%s@{desktop.main.fragment.b61f333b91b21f79} · @{desktop.main.fragment.d7718e74c3af68c2} %d @{desktop.main.fragment.85217f7aff778414}" % [_cal_short(released_at), lag],
		9, INK3, true)
	source_label.clip_text = true
	col.add_child(source_label)
	return card


func _release_movement(sid: String, previous: float, current: float) -> String:
	var delta := current - previous
	if absf(delta) <= 1e-12:
		return "@{desktop.main.fragment.a9105fc058c4896a}"
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
		valid_groups.append(str(grp["id"]))
	if _goto_panel_group.is_empty() or _goto_panel_group not in valid_groups:
		_goto_panel_group = str(PANEL_GROUPS[0]["id"])
	var nav_shell := PanelContainer.new()
	nav_shell.add_theme_stylebox_override("panel", _sb(PANEL3, LINE, 11, 6))
	body.add_child(nav_shell)
	var nav := HFlowContainer.new()
	nav.add_theme_constant_override("h_separation", 5)
	nav.add_theme_constant_override("v_separation", 5)
	nav_shell.add_child(nav)
	var active_group: Dictionary = PANEL_GROUPS[0]
	for grp: Dictionary in PANEL_GROUPS:
		var group_id := str(grp["id"])
		var group_name := str(grp["name"])
		var group_color: Color = grp["color"]
		var active := group_id == _goto_panel_group
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
			_goto_panel_group = group_id
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
	var group_id := str(active_group["id"])
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
	heading.add_child(_lbl(str(PANEL_DESCRIPTIONS.get(group_id, "")), 10, INK2))
	header_row.add_child(heading)
	header_row.add_child(_spacer_h())
	header_row.add_child(_chip("ECONOMY · @{desktop.main.fragment.25fea06069b1ff3d}", group_color.darkened(0.18),
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
			"@{desktop.main.fragment.df3fb562e88d7212}%s@{desktop.main.fragment.333886bd93369c11}" %
			str(CAPABILITY_CN.get(requirement, requirement)), 11, INK2)
		disabled_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		disabled.add_child(disabled_text)
		col.add_child(disabled)
		return
	var series: Array = _snapshot.get("series", [])
	var latest: Dictionary = _snapshot.get("metrics", {})
	var details: Dictionary = _snapshot.get("panel_details", {})
	_render_panel_kpis(col, active_group, latest, series)
	var charts: Array = PANEL_CHARTS.get(group_id, [])
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
		card.tooltip_text = "%s · %s\n@{desktop.main.fragment.66064880566620cf}%s\n@{desktop.main.fragment.f389cad7abd3c941}%s — %s" % [
			label, key, _fmt_val(kind, current),
			_fmt_val(kind, low), _fmt_val(kind, high)]
	return card


func _panel_delta(kind: String, previous: float, current: float) -> String:
	var delta := current - previous
	if absf(delta) <= 1e-12:
		return "— @{desktop.main.fragment.a9105fc058c4896a}"
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


func _labeled_rows(rows: Array, domain: String, id_field: String) -> Array:
	var labeled: Array = []
	for raw_row: Variant in rows:
		if not raw_row is Dictionary:
			continue
		var row := (raw_row as Dictionary).duplicate(true)
		if row.has(id_field):
			row["label"] = _domain_text(domain, str(row[id_field]))
		elif row.has("label"):
			row["label"] = LocaleCatalogScript.resolve(str(row["label"]))
		else:
			row["label"] = _domain_text(domain, "unknown")
		if not row.has("firms") and row.has("firm_count"):
			row["firms"] = row["firm_count"]
		labeled.append(row)
	return labeled


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
			"key": key,
			"label": LocaleCatalogScript.resolve(str(item[1])),
			"kind": kind,
			"color": color,
			"values": _panel_values(series, key),
			"value": float(latest.get(key, 0.0)),
			"text": _fmt_val(kind, float(latest.get(key, 0.0))),
		})
	var chart_height := 166.0 if panel.custom_minimum_size.y > 200.0 else 145.0
	if chart_type == "employment_sectors":
		var sectors := _PanelCompositionChart.new()
		sectors.data = _labeled_rows(
			(details.get("labor", {}) as Dictionary).get(
				"employment_sectors", []),
			"sector", "sector_id")
		sectors.font = _sans
		sectors.colors = [TEAL, BLUE, GREEN, PURPLE, AMBER, Color("64748b")]
		sectors.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(sectors)
	elif chart_type == "labor_flows":
		var labor := _PanelLaborFlowChart.new()
		var labor_details: Dictionary = details.get("labor", {})
		labor.states = _labeled_rows(
			labor_details.get("states", []), "labor_state", "state_id")
		labor.flows = _labeled_rows(
			labor_details.get("flows", []), "labor_flow", "flow_id")
		labor.font = _sans
		labor.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(labor)
	elif chart_type == "age_participation":
		var age_chart := _PanelAgeParticipationChart.new()
		age_chart.data = _labeled_rows(
			(details.get("labor", {}) as Dictionary).get(
				"participation_by_age", []),
			"age_group", "label_id")
		age_chart.font = _sans
		age_chart.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(age_chart)
	elif chart_type == "pyramid":
		var pyramid := _PanelPyramidChart.new()
		pyramid.data = _labeled_rows(
			(details.get("population", {}) as Dictionary).get("pyramid", []),
			"age_group", "label_id")
		pyramid.font = _sans
		pyramid.custom_minimum_size = Vector2(0, chart_height)
		col.add_child(pyramid)
	elif chart_type == "sector_matrix":
		var sector_chart := _PanelSectorMatrixChart.new()
		sector_chart.data = _labeled_rows(
			(details.get("real_economy", {}) as Dictionary).get("sectors", []),
			"sector", "sector_id")
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
	##  Fixed “balanced development” contracts: outcome variables, target deviations and trends; policy instruments do not count.
	var history: Array = world.get("history", [])
	if history.is_empty():
		return {"overall": 0.0, "grade": "@{desktop.main.fragment.22e2dceb6a845f5e}", "dimensions": []}
	var index := history.size() - 1 if history_index < 0 else clampi(
		history_index, 0, history.size() - 1)
	var point: Dictionary = history[index]
	var economy := _world_economy_at(history, index, country_index)
	if economy.is_empty():
		return {"overall": 0.0, "grade": "@{desktop.main.fragment.22e2dceb6a845f5e}", "dimensions": []}
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
		{"label": "@{desktop.main.fragment.9e595590da50f012}", "score": prosperity,
			"detail": "@{desktop.main.fragment.03aeb7c768b4cb8e} 30 @{desktop.main.fragment.2270c5fa0874a4d3} %+.1f%% · @{desktop.main.fragment.f0106af3d7386760} %+.1f%%" % [output_growth * 100.0, wage_growth * 100.0]},
		{"label": "@{desktop.main.fragment.63e76e239ef28c5d}", "score": employment,
			"detail": "@{desktop.main.fragment.9fa4c944be11cd8d} %.1f%% · @{desktop.main.fragment.dc93fdfa229b506d} %.1f%%" % [unemployment * 100.0, underemployment * 100.0]},
		{"label": "@{desktop.main.fragment.ca01c0c6352d168a}", "score": price_stability,
			"detail": "@{desktop.main.fragment.8e2831ed21f269bf} %.2f%% · @{desktop.main.fragment.57060c88a36bf3d0} %.2f%%" % [float(economy.get("inflation", 0.0)) * 100.0, inflation_target * 100.0]},
		{"label": "@{desktop.main.fragment.e235731852b87b21}", "score": fiscal,
			"detail": "@{desktop.main.fragment.095b45ce7df514df}/GDP %.1f%% · @{desktop.main.fragment.7865b21012629320}/GDP %.1f%%" % [float(economy.get("gov_debt_to_gdp", 0.0)) * 100.0, deficit_ratio * 100.0]},
		{"label": "@{desktop.main.fragment.2e0030609682f222}", "score": financial,
			"detail": "@{desktop.main.fragment.59831fc48b368a54}/@{desktop.main.fragment.334ec29216cfefb9} %.1f%% · @{desktop.main.fragment.041d6a395228b3a4} %.1f%%" % [maxf(capital, 0.0) / maxf(credit, 1.0) * 100.0, debt_service * 100.0]},
		{"label": "@{desktop.main.fragment.8653391f9199aaf2}", "score": welfare,
			"detail": "@{desktop.main.fragment.47786c3fc872cc69} %.1f%% · @{desktop.main.fragment.117d8f914d8e21a1} Gini %.3f" % [poverty * 100.0, income_gini]},
		{"label": "@{desktop.main.fragment.a04b020b47b31a6e}", "score": resilience,
			"detail": "@{desktop.main.fragment.d5ecdc812e1a4f41}/@{desktop.main.fragment.4c97f9db086dc1b9} %+.1f%% · @{desktop.main.fragment.31da51891f3b1115} %.1f×" % [ca_ratio * 100.0, energy_produced / maxf(energy_used, 0.000001)]},
	]
	var weights := [0.18, 0.14, 0.14, 0.14, 0.14, 0.14, 0.12]
	var overall := 0.0
	for dimension_index in dimensions.size():
		(dimensions[dimension_index] as Dictionary)["score"] = clampf(
			float((dimensions[dimension_index] as Dictionary)["score"]), 0.0, 100.0)
		overall += float((dimensions[dimension_index] as Dictionary)["score"]) \
			* float(weights[dimension_index])
	var grade := "@{desktop.main.fragment.67a532217bd0252c}"
	if overall >= 80.0:
		grade = "@{desktop.main.fragment.5102bbdbe111177a}"
	elif overall >= 65.0:
		grade = "@{desktop.main.fragment.752a14b3f6a7f3e9}"
	elif overall >= 50.0:
		grade = "@{desktop.main.fragment.062a4aa494000648}"
	elif overall >= 35.0:
		grade = "@{desktop.main.fragment.34dd51fd4277cc9d}"
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
	header.add_child(_lbl("NATIONAL SCORECARD · @{desktop.main.fragment.5ba2cbbd8718da04}", 10, INK3, true))
	header.add_child(_lbl(_country_name(_score_country), 13, INK))
	header.add_child(_spacer_h())
	header.add_child(_chip("@{desktop.main.fragment.2e46561da998c486} · @{desktop.main.fragment.b860d7f0446b3423}", INK2, PANEL3, LINE2, 9))
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
	total_row.add_child(_lbl("@{desktop.main.fragment.3b564729a5e8e0c7}", 10, INK3, true))
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
	grade_row.add_child(_chip(str(scorecard.get("grade", "@{desktop.main.fragment.22e2dceb6a845f5e}")), score_color,
		Color(score_color.r, score_color.g, score_color.b, 0.09),
		Color(score_color.r, score_color.g, score_color.b, 0.35), 9))
	grade_row.add_child(_spacer_h())
	grade_row.add_child(_lbl("@{desktop.main.fragment.03aeb7c768b4cb8e} 30 @{desktop.main.fragment.85217f7aff778414} %+.1f" % change, 9,
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
		var insight_label := _lbl("@{desktop.main.fragment.c2157628600afccc} · %s    @{desktop.main.fragment.9112d07e75535d19} · %s" % [
			str((ordered[0] as Dictionary).get("label", "")),
			str((ordered[-1] as Dictionary).get("label", ""))], 9, INK2)
		insight.add_child(insight_label)
		side.add_child(insight)
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 10)
	footer.add_child(_lbl("@{desktop.main.fragment.cada027120f11896} · @{desktop.main.fragment.12ca862720842c7a}", 9, ECON_COLORS[_score_country % 3]))
	footer.add_child(_lbl("@{desktop.main.fragment.3978a356f89e996e} · @{desktop.main.fragment.b3ae061812b83877}", 9, INK3))
	footer.add_child(_spacer_h())
	footer.add_child(_lbl("@{desktop.main.fragment.a8a61b72d47f42bc} · @{desktop.main.fragment.2913fa293cb473bd} · @{desktop.main.fragment.544dd9946df2adf5}",
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
		ev.add_child(_lbl("@{desktop.main.fragment.036bf7c22dc51057} · @{desktop.main.fragment.8ee919ab874db1bf}", 14, INK))
		ev.add_child(_lbl("@{desktop.main.fragment.b3ca9f149e3c4691}(@{desktop.main.fragment.26a59f85b3eb5fc4}/@{desktop.main.fragment.59831fc48b368a54}/@{desktop.main.fragment.0062878de0557b90})。", 12, INK2))
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
	#  --- Economy Card Line---
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
		card.tooltip_text = "@{desktop.main.fragment.c11330b85234f9c0}%s@{desktop.main.fragment.fc5795d29214d7b7}" % _country_name(i)
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
			hr.add_child(_chip("@{desktop.main.fragment.b70bb4acc0484cf0}", TEAL, Color(0, 0, 0, 0), TEAL_BD, 9))
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
			["@{desktop.main.fragment.9fa4c944be11cd8d}", _fmt_val("pct", float(e.get("unemployment_rate", 0.0)))],
			["@{desktop.main.fragment.b43cd47df5c0171c}", _fmt_val("pt", float(e.get("inflation", 0.0)))],
			["@{desktop.main.fragment.57ef2c45ef260ee3} e", "%.4f" % _fx_at(latest, i)],
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
	#  --- Ranking--
	var rp := PanelContainer.new()
	var rv := VBoxContainer.new()
	rv.add_theme_constant_override("separation", 7)
	rp.add_child(rv)
	var rh := HBoxContainer.new()
	rh.add_theme_constant_override("separation", 8)
	rh.add_child(_lbl("RANK · @{desktop.main.fragment.16e42d1344f38ecc}", 10, INK3, true))
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
	#  --- International relations: trade / finance / migration —
	var whist: Array = world.get("history", [])
	var rel := PanelContainer.new()
	var relv := VBoxContainer.new()
	relv.add_theme_constant_override("separation", 8)
	rel.add_child(relv)
	var relh := HBoxContainer.new()
	relh.add_theme_constant_override("separation", 8)
	relh.add_child(_lbl("RELATIONS · @{desktop.main.fragment.26a59f85b3eb5fc4} / @{desktop.main.fragment.a42315e416fa2550} / @{desktop.main.fragment.8948bde020cb3af2}", 10, INK3, true))
	relh.add_child(_spacer_h())
	relh.add_child(_lbl("@{desktop.main.fragment.348a6d388a4cd4da}(FX dealer)@{desktop.main.fragment.4a8d9f3dac306909}", 9, INK3))
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
	_bar_block(bars, "@{desktop.main.fragment.57ef2c45ef260ee3} e(numéraire)", _num_list(latest.get("e", [])), "%.4f", false)
	_bar_block(bars, "@{desktop.main.fragment.0473fc54c7daa4ca} NFA", _num_list(latest.get("nfa", [])), "%.1f", true)
	_bar_block(bars, "@{desktop.main.fragment.187c5d25114d44ba} 30 @{desktop.main.fragment.85f3344ea237b508}", _ca_sum(whist), "%.1f", true)
	_bar_block(bars, "@{desktop.main.fragment.736a80ece54a0d2e}", _num_list(latest.get("migrant_stock", [])), "%.2f", false)
	_bar_block(bars, "@{desktop.main.fragment.4d547295c20b7c8d}", _num_list(latest.get("remittances", [])), "%.3f", false)
	var foot := HBoxContainer.new()
	foot.add_theme_constant_override("separation", 10)
	foot.add_child(_lbl("FX @{desktop.main.fragment.0a228373feeb0e8d} %.2f" % float(latest.get("dealer_valuation", 0.0)),
		10, INK3, true))
	foot.add_child(_lbl("·", 10, LINE2))
	foot.add_child(_lbl("@{desktop.main.fragment.c1ba88409c35cb7a} " + ("@{desktop.main.fragment.955d487fd519f6e6}" if bool(latest.get("peg_intact", true))
		else "@{desktop.main.fragment.3a0bbe4fff215251}"), 10, INK3))
	relv.add_child(foot)
	col.add_child(rel)
	#  --- Small comparative figures ---
	var cmp := PanelContainer.new()
	var cmpv := VBoxContainer.new()
	cmpv.add_theme_constant_override("separation", 8)
	cmp.add_child(cmpv)
	var ch := HBoxContainer.new()
	ch.add_theme_constant_override("separation", 10)
	ch.add_child(_lbl("COMPARE · @{desktop.main.fragment.84a68297118edc17}", 10, INK3, true))
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


#  Synchronization helper.
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
		br.add_child(_lbl("@{desktop.main.fragment.9fe09a4c585bd333}", 10, Color("cc5a44")))
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
			#  The same boundary, the same trigger, is often sent to multiple seats; the default view is merged into one.
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
		var empty_text := "@{desktop.main.fragment.94f86851262e5a2f}" if _event_filter == "important" else "@{desktop.main.fragment.c766ec492fb8034d}"
		empty.add_child(_lbl(empty_text + "\n@{desktop.main.fragment.da613f0aa48efc64}",
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
		title.tooltip_text = "@{desktop.main.fragment.eeb38fe8a7328345}\n" + etype
		trr.add_child(title)
		if mine:
			trr.add_child(_chip("@{desktop.main.fragment.b70bb4acc0484cf0}", TEAL, Color(0, 0, 0, 0), TEAL_BD, 9))
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


#  Synchronization helper.
func _render_crisis() -> void:
	if _free_policy_enabled():
		(_n["crisis"] as Control).visible = false
		_crisis_was_visible = false
		return
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
	_set_text("crisis_title", "@{desktop.main.fragment.f8ce4c400c738850} · @{desktop.main.fragment.35a4e49d34672cb1}:%s" % trig)
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
			if rel.get("value") != null else "@{desktop.main.fragment.b336a174cd1fad05}", 15, RED, true))
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
			lvv.add_child(_lbl(_cn(name) + "(@{desktop.main.fragment.0efa477b24b1f3c7})", 12, Color("6b2317")))
			lvv.add_child(_lever_control(lever, perm, base_v))
			levcol.add_child(lp)
	if _demo_crisis:
		levcol.add_child(_lbl("@{desktop.main.fragment.05f5cdc5ee4a0f7e}:@{desktop.main.fragment.a6cb7867205f5dca} TriggerSpec @{desktop.main.fragment.222c6aff7dbd231c}(v26)。",
			10, Color("9a6a5e")))
	var submit := _btn("@{desktop.main.fragment.2415d3072d249473}", func() -> void:
		if _demo_crisis:
			_demo_crisis = false
			_render()
			return
		#  The crisis panel does not have the "add to the proposal" step: submit the editorial value of the white list leverage directly to the basket.
		#  No editing is the equivalent of "not moving this time" to ensure that players always get out of emergency meetings.
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


#  Synchronization helper.
class _StockMarketChart extends Control:
	##  The model only provides a daily bargain, so the real collection sequence is drawn here and does not synthesize the OHLC/K line.
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
				LocaleCatalogScript.resolve(str("@{desktop.main.fragment.ad47923c0b883880}")), HORIZONTAL_ALIGNMENT_CENTER, plot.size.x, 9,
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
			LocaleCatalogScript.resolve(str("%.3f" % high)), HORIZONTAL_ALIGNMENT_LEFT, 50.0, 8, Color("8794a2"))
		draw_string(font, Vector2(plot.end.x + 7.0, plot.end.y + 3.0),
			LocaleCatalogScript.resolve(str("%.3f" % low)), HORIZONTAL_ALIGNMENT_LEFT, 50.0, 8, Color("8794a2"))
		draw_string(font, Vector2(plot.position.x, size.y - 2.0),
			LocaleCatalogScript.resolve(str("%d @{desktop.main.fragment.f6ee2eb155f0496d}" % values.size())), HORIZONTAL_ALIGNMENT_LEFT,
			plot.size.x, 8, Color("8794a2"))


class _StockBreadthChart extends Control:
	var advances := 0
	var unchanged := 0
	var declines := 0
	var font: Font

	func _draw() -> void:
		var total := advances + unchanged + declines
		if total <= 0:
			draw_string(font, Vector2(0, 19), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.51e6f8e083bedbf6}")),
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
		draw_string(font, Vector2(0, 31), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.5304a679d7a0df04}")), HORIZONTAL_ALIGNMENT_LEFT,
			50, 8, Color("20a566"))
		draw_string(font, Vector2(0, 31), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.80baca0a82ecfe42}")), HORIZONTAL_ALIGNMENT_CENTER,
			size.x, 8, Color("7c8997"))
		draw_string(font, Vector2(size.x - 50, 31), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.7bede945da28916a}")), HORIZONTAL_ALIGNMENT_RIGHT,
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
		["cash", "@{desktop.main.fragment.118f18e6840546c1}", Color("16a394")],
		["firm_equity", "@{desktop.main.fragment.22e64656444bc55f}", Color("3274d9")],
		["bank_equity", "@{desktop.main.fragment.20646c88cdfdcf6b}", Color("7950c7")],
		["bonds", "@{desktop.main.fragment.9dc4139eaedd31c5}", Color("c78318")],
		["housing", "@{desktop.main.fragment.65024b83e8cb8448}", Color("7a8b9b")],
	]

	func _draw() -> void:
		var total := 0.0
		for part: Array in parts:
			total += maxf(0.0, float(values.get(str(part[0]), 0.0)))
		var bar := Rect2(2, 3, size.x - 4, 13)
		draw_rect(bar, Color("e9eef4"))
		if total <= 1e-9:
			draw_string(font, Vector2(0, 38), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.47106d28424871b6}")),
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
			draw_string(font, Vector2(x + 11, 34), LocaleCatalogScript.resolve(str("%s %.0f%%" % [
				str(part[1]), value / total * 100.0])),
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
			draw_string(font, Vector2(0, size.y * 0.52), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.c604aff38c595627}")),
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
			draw_string(font, Vector2(x + 14, y), LocaleCatalogScript.resolve(str(str(item.get("label", "")))),
				HORIZONTAL_ALIGNMENT_LEFT, cell_width - 66, 9, Color("506172"))
			var share := maxf(0.0, float(item.get("value", 0.0))) / total
			draw_string(font, Vector2(x, y), LocaleCatalogScript.resolve(str("%.1f%%" % (share * 100.0))),
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
			draw_string(font, Vector2(x, 43), LocaleCatalogScript.resolve(str("%s %.0f%%" % [
				str(state.get("label", "")), share * 100.0])),
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
			draw_string(font, Vector2(x, y + 9), LocaleCatalogScript.resolve(str(str(item.get("label", "")))),
				HORIZONTAL_ALIGNMENT_LEFT, 68, 8, Color("5e6f81"))
			draw_rect(Rect2(x + 70, y + 2, maxf(8.0, cell_width - 96.0), 7), Color("edf1f6"))
			draw_rect(Rect2(x + 70, y + 2,
				maxf(8.0, cell_width - 96.0) * value / max_flow, 7), Color("2f72d6"))
			draw_string(font, Vector2(x, y + 9), LocaleCatalogScript.resolve(str("%.0f" % value)),
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
			draw_string(font, Vector2(0, y + 3), LocaleCatalogScript.resolve(str("%d%%" % (grid * 50))),
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
			draw_string(font, Vector2(center - slot / 2.0, plot.end.y + 15), LocaleCatalogScript.resolve(str(str(item.get("label", "")))),
				HORIZONTAL_ALIGNMENT_CENTER, slot, 8, Color("5e6f81"))
			draw_string(font, Vector2(center - slot / 2.0, plot.end.y - p_height - 4),
				LocaleCatalogScript.resolve(str("%.0f%%" % (participation * 100.0))), HORIZONTAL_ALIGNMENT_CENTER, slot, 7, Color("087f74"))
		draw_rect(Rect2(plot.position.x, 4, 8, 8), Color("16a394"))
		draw_string(font, Vector2(plot.position.x + 12, 12), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.e48413edc017608c}")),
			HORIZONTAL_ALIGNMENT_LEFT, 70, 8, Color("5e6f81"))
		draw_rect(Rect2(plot.position.x + 82, 4, 8, 8), Color("3274d9"))
		draw_string(font, Vector2(plot.position.x + 94, 12), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.f1a55c785cd3afce}")),
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
			draw_string(font, Vector2(center - label_width / 2.0, y + row_height - 7), LocaleCatalogScript.resolve(str(str(item.get("label", "")))),
				HORIZONTAL_ALIGNMENT_CENTER, label_width, 8, Color("5e6f81"))
			draw_string(font, Vector2(2, y + row_height - 7), LocaleCatalogScript.resolve(str("%.0f" % male)),
				HORIZONTAL_ALIGNMENT_RIGHT, center - label_width / 2.0 - 8, 7, Color("3274d9"))
			draw_string(font, Vector2(center + label_width / 2.0 + 5, y + row_height - 7), LocaleCatalogScript.resolve(str("%.0f" % female)),
				HORIZONTAL_ALIGNMENT_LEFT, half_width, 7, Color("c78318"))
		draw_string(font, Vector2(2, size.y - 1), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.4e79758a99006223}  ◀")),
			HORIZONTAL_ALIGNMENT_RIGHT, center - 22, 8, Color("3274d9"))
		draw_string(font, Vector2(center + 22, size.y - 1), LocaleCatalogScript.resolve(str("▶  @{desktop.main.fragment.0ab4610b9257c298}")),
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
				LocaleCatalogScript.resolve(str(str(["@{desktop.main.fragment.4c97f9db086dc1b9}", "@{desktop.main.fragment.f04b061471b1fd16}", "@{desktop.main.fragment.2c6e0266e1ac28a8}FTE"][column]))),
				HORIZONTAL_ALIGNMENT_CENTER, metric_width, 8, Color("849098"))
		var row_height := (size.y - 22.0) / float(data.size())
		for row in data.size():
			var item: Dictionary = data[row]
			var y := 22.0 + row * row_height
			draw_string(font, Vector2(2, y + 11), LocaleCatalogScript.resolve(str("%s · %d@{desktop.main.fragment.c8ae97be80f3867c}" % [
				str(item.get("label", "")), int(item.get("firms", 0))])),
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
		draw_string(font, Vector2(plot.position.x + 12, 10), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.74b1cd2121521fcf}")),
			HORIZONTAL_ALIGNMENT_LEFT, 58, 8, Color("5e6f81"))
		draw_rect(Rect2(plot.position.x + 76, 2, 8, 8), Color("3274d9"))
		draw_string(font, Vector2(plot.position.x + 88, 10), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.a015979455bc147e}")),
			HORIZONTAL_ALIGNMENT_LEFT, 90, 8, Color("5e6f81"))
		draw_string(font, Vector2(plot.position.x, size.y - 1), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.0b5a6fe96ecedd01} →")),
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
			draw_string(font, Vector2(plot.position.x + slot * index, plot.end.y + 14), LocaleCatalogScript.resolve(str("D%d" % (index + 1))),
				HORIZONTAL_ALIGNMENT_CENTER, slot, 7, Color("6f7d89"))
		draw_rect(Rect2(plot.position.x, 3, 8, 8), Color("7950c7"))
		draw_string(font, Vector2(plot.position.x + 12, 11), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.869784698f2c9523}")),
			HORIZONTAL_ALIGNMENT_LEFT, 55, 8, Color("5e6f81"))
		draw_rect(Rect2(plot.position.x + 72, 3, 8, 8), Color("16a394"))
		draw_string(font, Vector2(plot.position.x + 84, 11), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.f46a5765185637cb}")),
			HORIZONTAL_ALIGNMENT_LEFT, 55, 8, Color("5e6f81"))


class _PanelBubbleChart extends Control:
	var data: Array = []
	var font: Font

	func _draw() -> void:
		if data.is_empty():
			draw_string(font, Vector2(0, size.y * 0.52), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.07616b07cc485e4b}")),
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
		draw_string(font, Vector2(plot.position.x, size.y - 1), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.262b4d2f27d039c7} Q →")),
			HORIZONTAL_ALIGNMENT_RIGHT, plot.size.x, 8, Color("849098"))


class _PanelEnergyFlowChart extends Control:
	var values: Dictionary = {}
	var font: Font

	func _node(rect: Rect2, title: String, value: float, color: Color) -> void:
		draw_rect(rect, Color(color.r, color.g, color.b, 0.10))
		draw_rect(rect, color, false, 1.0)
		draw_string(font, rect.position + Vector2(0, 17), LocaleCatalogScript.resolve(str(title)),
			HORIZONTAL_ALIGNMENT_CENTER, rect.size.x, 8, Color("5e6f81"))
		draw_string(font, rect.position + Vector2(0, 36), LocaleCatalogScript.resolve(str("%.1f" % value)),
			HORIZONTAL_ALIGNMENT_CENTER, rect.size.x, 12, color)

	func _draw() -> void:
		var node_w := minf(112.0, size.x * 0.25)
		var node_h := 48.0
		var y := 26.0
		var left := Rect2(3, y, node_w, node_h)
		var center := Rect2((size.x - node_w) / 2.0, y, node_w, node_h)
		var right := Rect2(size.x - node_w - 3, y, node_w, node_h)
		_node(left, "@{desktop.main.fragment.76ab7d3b41f2326d}", float(values.get("energy_produced", 0.0)), Color("21a179"))
		_node(center, "@{desktop.main.fragment.f6b3e938eedcddbb}", float(values.get("energy_sold", 0.0)), Color("3274d9"))
		_node(right, "@{desktop.main.fragment.5b026b70ce28ec94}", float(values.get("energy_used", 0.0)), Color("c78318"))
		draw_line(Vector2(left.end.x + 4, y + node_h / 2), Vector2(center.position.x - 4, y + node_h / 2), Color("9cabb9"), 2.0)
		draw_line(Vector2(center.end.x + 4, y + node_h / 2), Vector2(right.position.x - 4, y + node_h / 2), Color("9cabb9"), 2.0)
		var stock := float(values.get("energy_stock_total", 0.0))
		var reserve := float(values.get("spr_stock", 0.0))
		var coverage := float(values.get("energy_coverage_mean", 0.0))
		draw_string(font, Vector2(3, 103), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.b1c05328552e878a}+@{desktop.main.fragment.225c96cb80b6490f}  %.1f" % stock)),
			HORIZONTAL_ALIGNMENT_LEFT, size.x * 0.44, 9, Color("506172"))
		draw_string(font, Vector2(size.x * 0.44, 103), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.ba246184da7bbff6}  %.1f" % reserve)),
			HORIZONTAL_ALIGNMENT_LEFT, size.x * 0.30, 9, Color("7950c7"))
		draw_string(font, Vector2(3, 125), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.54e84ad6189abdab} %.1f @{desktop.main.fragment.49da61ceeea2f271} · @{desktop.main.fragment.3fd7877cd3c8238d} %.1f" % [
			coverage, float(values.get("energy_unfilled", 0.0))])),
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
			{"label": "@{desktop.main.fragment.7787b9a545c5de4c}", "value": float(values.get("tax_income", 0.0)), "color": Color("16a394")},
			{"label": "@{desktop.main.fragment.80716311485ac4f9}", "value": float(values.get("tax_consumption", 0.0)), "color": Color("3274d9")},
			{"label": "@{desktop.main.fragment.409d0719010a46ee}", "value": float(values.get("tax_profit", 0.0)), "color": Color("7950c7")},
			{"label": "@{desktop.main.fragment.d2909f1647e7c891}", "value": maxf(0.0, float(values.get("fiscal_revenue_total", 0.0)) - float(values.get("tax_income", 0.0)) - float(values.get("tax_consumption", 0.0)) - float(values.get("tax_profit", 0.0))), "color": Color("7a8b9b")},
		]
		var spending := [
			{"label": "@{desktop.main.fragment.223be31de4a3a161}", "value": float(values.get("gov_consumption", 0.0)), "color": Color("3274d9")},
			{"label": "@{desktop.main.fragment.ae7c4c83caeb18a5}", "value": float(values.get("benefit_paid", 0.0)), "color": Color("7950c7")},
			{"label": "@{desktop.main.fragment.47c7231355664b7b}", "value": float(values.get("public_investment", 0.0)), "color": Color("16a394")},
			{"label": "@{desktop.main.fragment.d2909f1647e7c891}", "value": maxf(0.0, float(values.get("augmented_gov_spending", 0.0)) - float(values.get("gov_consumption", 0.0)) - float(values.get("benefit_paid", 0.0)) - float(values.get("public_investment", 0.0))), "color": Color("c78318")},
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
		draw_string(font, Vector2(0, 11), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.117d8f914d8e21a1} %.1f" % revenue_total)),
			HORIZONTAL_ALIGNMENT_CENTER, size.x * 0.46, 9, Color("087f74"))
		draw_string(font, Vector2(size.x * 0.5, 11), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.e679096865859f36} %.1f" % spending_total)),
			HORIZONTAL_ALIGNMENT_CENTER, size.x * 0.46, 9, Color("2f72d6"))
		draw_string(font, Vector2(0, size.y - 5), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.44b6a26cdf8bb924} = @{desktop.main.fragment.c0896daadb215d4b}  %.1f" % float(values.get("gov_deficit", 0.0)))),
			HORIZONTAL_ALIGNMENT_CENTER, size.x, 8, Color("849098"))


class _PanelBankBalanceChart extends Control:
	var values: Dictionary = {}
	var font: Font

	func _bar(y: float, label: String, value: float, maximum: float, color: Color) -> void:
		draw_string(font, Vector2(2, y + 10), LocaleCatalogScript.resolve(str(label)),
			HORIZONTAL_ALIGNMENT_LEFT, 76, 8, Color("5e6f81"))
		var x := 80.0
		var width := maxf(20.0, size.x - 145.0)
		draw_rect(Rect2(x, y + 2, width, 9), Color("edf1f6"))
		draw_rect(Rect2(x, y + 2, width * maxf(0.0, value) / maximum, 9), color)
		draw_string(font, Vector2(x + width + 5, y + 10), LocaleCatalogScript.resolve(str("%.1f" % value)),
			HORIZONTAL_ALIGNMENT_RIGHT, 56, 8, color)

	func _draw() -> void:
		var credit := float(values.get("total_credit", 0.0))
		var deposits := float(values.get("bank_deposit_total", 0.0))
		var capital := float(values.get("bank_capital", 0.0))
		var maximum := maxf(1.0, maxf(credit, maxf(deposits, capital)))
		_bar(15, "@{desktop.main.fragment.a8076a5ef01d06eb}", credit, maximum, Color("16a394"))
		_bar(48, "@{desktop.main.fragment.568f506a5c1d51e3}", deposits, maximum, Color("3274d9"))
		_bar(81, "@{desktop.main.fragment.baadb5544e4943ac}", capital, maximum, Color("21a166"))
		var capital_ratio := capital / maxf(credit, 1e-9)
		draw_string(font, Vector2(2, 129), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.59831fc48b368a54}/@{desktop.main.fragment.334ec29216cfefb9} %.1f%% · @{desktop.main.fragment.122041156a7d5677} %.1f" % [
			capital_ratio * 100.0, float(values.get("writeoffs", 0.0))])),
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
			draw_string(font, Vector2(legend_x + 10.0, 14.0), LocaleCatalogScript.resolve(str(legend)),
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
				LocaleCatalogScript.resolve(str("@{desktop.main.fragment.69e50cb4b72735d4}")),
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
			LocaleCatalogScript.resolve(str("@{desktop.main.fragment.997a5e6e513f2a90} %d @{desktop.main.fragment.85217f7aff778414}" % int((data[0] as Dictionary).get("values", []).size()) if not data.is_empty() else "")),
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
			draw_string(font, Vector2(2, y + 13), LocaleCatalogScript.resolve(str(str(item.get("label", "")))),
				HORIZONTAL_ALIGNMENT_LEFT, 84, 9, Color("5e6f81"))
			var bar_x := 88.0
			var bar_width := maxf(10.0, size.x - bar_x - 64.0)
			var bar_y := y + 6.0
			draw_rect(Rect2(bar_x, bar_y, bar_width, 8), Color("edf1f6"))
			draw_rect(Rect2(bar_x, bar_y,
				bar_width * absf(value) / max_value, 8), color)
			draw_string(font, Vector2(bar_x + bar_width + 6.0, y + 14),
				LocaleCatalogScript.resolve(str(str(item.get("text", "")))), HORIZONTAL_ALIGNMENT_RIGHT, 56, 9,
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
				LocaleCatalogScript.resolve(str(str(item.get("text", "")))), HORIZONTAL_ALIGNMENT_CENTER, slot_width, 8, color)
			draw_string(font, Vector2(plot.position.x + slot_width * float(item_index), size.y - 7),
				LocaleCatalogScript.resolve(str(str(item.get("label", "")))), HORIZONTAL_ALIGNMENT_CENTER, slot_width, 8,
				Color("5e6f81"))


class _MacroPhaseMap extends Control:
	var has_phase := false
	var x_value := 0.0
	var y_value := 0.0
	var phase := "@{desktop.main.fragment.25f6cdf3722d33b8}"
	var point_color := Color("5e6f81")
	var font: Font

	func _draw() -> void:
		var plot := Rect2(Vector2(34, 15), size - Vector2(46, 43))
		var half := plot.size / 2.0
		var center := plot.get_center()
		#  The quadrant is limited to a “relationship interpretation” and does not duplicate the original indicator series.
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
		draw_string(font, plot.position + Vector2(7, 14), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.43b666feeeb6487c}")),
			HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("ad6658"))
		draw_string(font, Vector2(center.x + 7, plot.position.y + 14), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.e8080680ffdb93b6}")),
			HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("a8782e"))
		draw_string(font, Vector2(plot.position.x + 7, plot.end.y - 7), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.8ee04f36861892b7}")),
			HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("5878a8"))
		draw_string(font, Vector2(center.x + 7, plot.end.y - 7), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.fea642af5f0c14ef}")),
			HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("408c82"))
		draw_string(font, Vector2(plot.position.x, size.y - 7),
			LocaleCatalogScript.resolve(str("@{desktop.main.fragment.c9c62e7bc3d850f1}  ←        @{desktop.main.fragment.5bd3b5af44a16b17}        →  @{desktop.main.fragment.58d9feb27a837c35}")),
			HORIZONTAL_ALIGNMENT_CENTER, plot.size.x, 9, Color("71808f"))
		draw_string(font, Vector2(plot.position.x, 10), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.20ea8f201a36f7bb} ↑")),
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
			draw_string(font, Vector2(label_x + 7, label_y + 14), LocaleCatalogScript.resolve(str(phase)),
				HORIZONTAL_ALIGNMENT_LEFT, -1, 10, point_color)
		else:
			draw_string(font, Vector2(plot.position.x, center.y + 4),
				LocaleCatalogScript.resolve(str("@{desktop.main.fragment.b73549f042ce86f7}")),
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
			draw_string(font, Vector2(0, size.y / 2.0), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.f5174a6a7f63da74}")),
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
				LocaleCatalogScript.resolve(str(str(labels[index]))), HORIZONTAL_ALIGNMENT_CENTER, 76.0, 9, Color("5e6f81"))
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
	##  Trinational relationship chart: Node Triangular Layout + Centre Clearing Hub;
	##  Real = export flows (hubs), nodes = import flows (hubs), purple = immigrants, Amber = remittances.
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
		draw_string(font, center + Vector2(-11, 4), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.bc0d2e59923c651b}")),
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
			draw_string(font, p + off, LocaleCatalogScript.resolve(str(label)),
				HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color("2a3948"))
		var ly := size.y - 10.0
		draw_line(Vector2(8, ly), Vector2(26, ly), Color(0.122, 0.616, 0.388, 0.9), 2.5, true)
		draw_string(font, Vector2(30, ly + 4), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.7016090059bdfab9}")), HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("68788b"))
		draw_line(Vector2(64, ly), Vector2(82, ly), Color(0.184, 0.435, 0.816, 0.7), 1.5, true)
		draw_string(font, Vector2(86, ly + 4), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.514e5df21b748fda}")), HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("68788b"))
		draw_circle(Vector2(126, ly), 3.0, Color(0.478, 0.31, 0.816, 0.7))
		draw_string(font, Vector2(133, ly + 4), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.8948bde020cb3af2}")), HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("68788b"))
		draw_circle(Vector2(172, ly), 3.0, Color(0.757, 0.49, 0.086, 0.7))
		draw_string(font, Vector2(179, ly + 4), LocaleCatalogScript.resolve(str("@{desktop.main.fragment.bfe16f1bdae540f8}")), HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color("68788b"))
