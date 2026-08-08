import sys
import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_package_namespace_imports():
    import macro_sim
    import macro_sim.behavior
    import macro_sim.core
    import macro_sim.domain
    import macro_sim.experiments
    import macro_sim.markets
    import macro_sim.reporting
    import macro_sim.systems

    assert macro_sim is not None
    assert macro_sim.core is not None
    assert macro_sim.domain is not None
    assert macro_sim.behavior is not None
    assert macro_sim.markets is not None
    assert macro_sim.systems is not None
    assert macro_sim.reporting is not None
    assert macro_sim.experiments is not None


def test_new_low_risk_module_imports():
    from macro_sim.behavior.planning import plan_consumption
    from macro_sim.core.ledger import Ledger
    from macro_sim.core.policy import Policy
    from macro_sim.domain.agents import Bank, Firm, Household
    from macro_sim.markets.matching import BuyOrder, SellOffer, execute_market

    assert Ledger is not None
    assert Policy is not None
    assert Household is not None
    assert Firm is not None
    assert Bank is not None
    assert BuyOrder is not None
    assert SellOffer is not None
    assert execute_market is not None
    assert plan_consumption is not None


def test_config_imports_from_package_path():
    from macro_sim.config import Config

    assert Config is not None
    assert Config.v124 is not None


def test_config_model_is_canonical_and_legacy_module_is_removed():
    from macro_sim.config import Config
    from macro_sim.config.model import Config as ModelConfig

    assert Config is ModelConfig
    assert importlib.util.find_spec("macro_sim.config.legacy") is None


def test_reporting_and_experiment_imports_from_package_paths():
    from macro_sim.experiments.runlog import RunLogger
    from macro_sim.reporting.diagnostics import plot_dashboard
    from macro_sim.reporting.metrics import compute_tick_metrics

    assert compute_tick_metrics is not None
    assert plot_dashboard is not None
    assert RunLogger is not None


def test_economy_imports_from_package_path():
    from macro_sim.economy import Economy

    assert Economy is not None


def test_economy_exposes_simulation_state_carrier():
    from macro_sim.config import Config
    from macro_sim.core.state import SimulationState
    from macro_sim.economy import Economy

    econ = Economy(Config(n_ticks=1, seed=0))

    assert isinstance(econ.state, SimulationState)
    assert econ.state.cfg is econ.cfg
    assert econ.state.policy is econ.policy
    assert econ.state.rng is econ.rng
    assert econ.state.ledger is econ.ledger
    assert econ.state.households is econ.households
    assert econ.state.firms is econ.firms
    assert econ.state.c_firms is econ.c_firms
    assert econ.state.k_firms is econ.k_firms
    assert econ.state.banks is econ.banks
    assert econ.state.records is econ.records


def test_extracted_system_functions_import():
    from macro_sim.behavior.planning import diversify_mpc
    from macro_sim.systems.banking import (
        assign_banks_genesis,
        bank_capacity,
        bank_economic_capital,
        bank_equity_value,
        bank_constraint,
        bank_fundamental,
        bank_for,
        bank_stock_market,
        draw_bank_kappas,
        draw_bank_spreads,
        draw_deposit_spreads,
        enable_reserves,
        fail_bank,
        find_bank_founder,
        found_bank,
        grant_loan,
        loan_rate_for,
        pay_bank_dividends,
        rate_competition,
        record_bank_credit_loss,
        refresh_loan_books,
        reset_bank_realized_pnl,
        reserve_position,
        resolve_bank_failures,
        run_bank_entry_phase,
        run_bank_runs_phase,
        run_deposit_competition,
        run_interbank_phase,
        settlement_node,
        setup_bank_equity,
        shop_bank,
        update_bank_valuation,
    )
    from macro_sim.systems.capital_goods import run_capital_goods_phase
    from macro_sim.systems.central_bank import run_omo_phase, set_policy_rate
    from macro_sim.systems.credit import finalize_bank_pnl, run_credit_phase, run_debt_service_phase
    from macro_sim.systems.equity import run_equity_phase, run_per_firm_equity_phase
    from macro_sim.systems.firm_demographics import (
        apply_gibrat_shock,
        bankrupt_firm,
        birth_consumption_firm,
        enter_consumption_firms,
        pick_funder,
        run_firm_demographics_phase,
        startup_cash,
    )
    from macro_sim.systems.goods import run_goods_phase
    from macro_sim.systems.labor import run_labor_phase
    from macro_sim.systems.planning import run_planning_phase
    from macro_sim.systems.securities import (
        assert_securities_identities,
        bond_market_value,
        bond_price,
        household_bond_value,
        redeem_household_bonds,
        reindex_bonds,
        run_bill_issuance_phase,
        run_bill_maturity_phase,
    )
    from macro_sim.systems.settlement import run_household_fiscal_phase, run_settlement_phase

    assert set_policy_rate is not None
    assert diversify_mpc is not None
    assert run_planning_phase is not None
    assert run_omo_phase is not None
    assert run_bill_maturity_phase is not None
    assert run_credit_phase is not None
    assert run_labor_phase is not None
    assert run_goods_phase is not None
    assert run_capital_goods_phase is not None
    assert run_settlement_phase is not None
    assert run_debt_service_phase is not None
    assert finalize_bank_pnl is not None
    assert run_firm_demographics_phase is not None
    assert run_equity_phase is not None
    assert run_per_firm_equity_phase is not None
    assert run_interbank_phase is not None
    assert run_bank_runs_phase is not None
    assert resolve_bank_failures is not None
    assert run_bank_entry_phase is not None
    assert run_bill_issuance_phase is not None
    assert run_deposit_competition is not None
    assert run_household_fiscal_phase is not None
    assert assign_banks_genesis is not None
    assert bank_capacity is not None
    assert bank_economic_capital is not None
    assert bank_equity_value is not None
    assert bank_constraint is not None
    assert bank_fundamental is not None
    assert bank_for is not None
    assert bank_stock_market is not None
    assert draw_bank_kappas is not None
    assert draw_bank_spreads is not None
    assert draw_deposit_spreads is not None
    assert enable_reserves is not None
    assert fail_bank is not None
    assert find_bank_founder is not None
    assert found_bank is not None
    assert grant_loan is not None
    assert loan_rate_for is not None
    assert pay_bank_dividends is not None
    assert rate_competition is not None
    assert record_bank_credit_loss is not None
    assert refresh_loan_books is not None
    assert reset_bank_realized_pnl is not None
    assert reserve_position is not None
    assert settlement_node is not None
    assert setup_bank_equity is not None
    assert shop_bank is not None
    assert update_bank_valuation is not None
    assert apply_gibrat_shock is not None
    assert bankrupt_firm is not None
    assert birth_consumption_firm is not None
    assert enter_consumption_firms is not None
    assert pick_funder is not None
    assert startup_cash is not None
    assert assert_securities_identities is not None
    assert bond_market_value is not None
    assert bond_price is not None
    assert household_bond_value is not None
    assert redeem_household_bonds is not None
    assert reindex_bonds is not None


def test_economy_step_uses_extracted_system_functions(monkeypatch):
    import macro_sim.economy as economy_module
    from macro_sim.config import Config
    from macro_sim.economy import Economy

    calls = []

    def fake_reset_bank_pnl(econ):
        calls.append(("reset_bank_pnl", econ))

    def fake_set_policy_rate(econ):
        calls.append(("set_policy_rate", econ))

    def fake_planning(econ):
        calls.append(("planning", econ))

    def fake_omo(econ):
        calls.append(("omo", econ))

    def fake_bill_maturity(econ):
        calls.append(("bill_maturity", econ))

    def fake_gibrat_shock(econ):
        calls.append(("gibrat_shock", econ))

    def fake_credit(econ):
        calls.append(("credit", econ))

    def fake_labor(econ):
        calls.append(("labor", econ))

    def fake_goods(econ):
        calls.append(("goods", econ))

    def fake_capital_goods(econ):
        calls.append(("capital_goods", econ))

    def fake_settlement(econ):
        calls.append(("settlement", econ))

    def fake_debt_service(econ):
        calls.append(("debt_service", econ))

    def fake_firm_demographics(econ):
        calls.append(("firm_demographics", econ))

    def fake_equity(econ):
        calls.append(("equity", econ))

    def fake_interbank(econ):
        calls.append(("interbank", econ))

    def fake_finalize_bank_pnl(econ):
        calls.append(("finalize_bank_pnl", econ))

    def fake_bank_runs(econ):
        calls.append(("bank_runs", econ))

    def fake_resolve_bank_failures(econ):
        calls.append(("resolve_bank_failures", econ))

    def fake_bank_entry(econ):
        calls.append(("bank_entry", econ))

    def fake_bill_issuance(econ):
        calls.append(("bill_issuance", econ))

    def fake_deposit_competition(econ):
        calls.append(("deposit_competition", econ))

    def fake_record(econ):
        calls.append(("record", econ))
        return {"tick": econ.t}

    def fake_commit(econ):
        calls.append(("commit", econ))

    monkeypatch.setattr(economy_module, "reset_bank_realized_pnl", fake_reset_bank_pnl)
    monkeypatch.setattr(economy_module, "set_policy_rate", fake_set_policy_rate)
    monkeypatch.setattr(economy_module, "run_planning_phase", fake_planning)
    monkeypatch.setattr(economy_module, "run_omo_phase", fake_omo)
    monkeypatch.setattr(economy_module, "run_bill_maturity_phase", fake_bill_maturity)
    monkeypatch.setattr(economy_module, "apply_gibrat_shock", fake_gibrat_shock)
    monkeypatch.setattr(economy_module, "run_credit_phase", fake_credit)
    monkeypatch.setattr(economy_module, "run_labor_phase", fake_labor)
    monkeypatch.setattr(economy_module, "run_goods_phase", fake_goods)
    monkeypatch.setattr(economy_module, "run_capital_goods_phase", fake_capital_goods)
    monkeypatch.setattr(economy_module, "run_settlement_phase", fake_settlement)
    monkeypatch.setattr(economy_module, "run_debt_service_phase", fake_debt_service)
    monkeypatch.setattr(economy_module, "run_firm_demographics_phase", fake_firm_demographics)
    monkeypatch.setattr(economy_module, "run_equity_phase", fake_equity)
    monkeypatch.setattr(economy_module, "run_interbank_phase", fake_interbank)
    monkeypatch.setattr(economy_module, "finalize_bank_pnl", fake_finalize_bank_pnl)
    monkeypatch.setattr(economy_module, "run_bank_runs_phase", fake_bank_runs)
    monkeypatch.setattr(economy_module, "resolve_bank_failures", fake_resolve_bank_failures)
    monkeypatch.setattr(economy_module, "run_bank_entry_phase", fake_bank_entry)
    monkeypatch.setattr(economy_module, "run_bill_issuance_phase", fake_bill_issuance)
    monkeypatch.setattr(economy_module, "run_deposit_competition", fake_deposit_competition)

    monkeypatch.setattr(Economy, "_phase5_check_and_record", fake_record)
    monkeypatch.setattr(Economy, "_commit_cross_tick_state", fake_commit)

    econ = Economy(Config.v124(n_ticks=1, seed=0, interbank=True, n_banks=2))
    rec = econ.step()

    assert calls == [
        ("reset_bank_pnl", econ),
        ("set_policy_rate", econ),
        ("deposit_competition", econ),
        ("omo", econ),
        ("bill_maturity", econ),
        ("planning", econ),
        ("gibrat_shock", econ),
        ("credit", econ),
        ("labor", econ),
        ("goods", econ),
        ("capital_goods", econ),
        ("settlement", econ),
        ("debt_service", econ),
        ("firm_demographics", econ),
        ("equity", econ),
        ("interbank", econ),
        ("bank_runs", econ),
        ("resolve_bank_failures", econ),
        ("finalize_bank_pnl", econ),
        ("bank_entry", econ),
        ("bill_issuance", econ),
        ("record", econ),
        ("commit", econ),
    ]
    assert rec == {"tick": 0}


def test_economy_phase_wrappers_are_collapsed():
    from macro_sim.economy import Economy

    collapsed = {
        "_cb_set_rate",
        "_deposit_competition",
        "_phase_omo",
        "_phase_bill_maturity",
        "_phase1_plan",
        "_phase1_5_credit",
        "_phase2_labor",
        "_phase3_goods",
        "_phase3_5_capital",
        "_phase4_settlement",
        "_gov_household_fiscal",
        "_phase4_5_debt_service",
        "_phase4_7_demographics",
        "_phase4_9_equity",
        "_phase4_9_equity_per_firm",
        "_phase_interbank",
        "_phase_bank_runs",
        "_resolve_bank_failures",
        "_entry_banks",
        "_phase_bill_issuance",
    }

    assert collapsed.isdisjoint(Economy.__dict__)


def test_economy_helper_clusters_are_owned_by_system_modules():
    from macro_sim.economy import Economy

    extracted_helpers = {
        "_bankrupt",
        "_entry_c_firms",
        "_startup_cash",
        "_pick_funder",
        "_birth_c_firm",
        "_bond_price",
        "_bond_market_value",
        "_reindex_bonds",
        "_hh_bond_value",
        "_redeem_hh_bonds",
    }

    assert extracted_helpers.isdisjoint(Economy.__dict__)


def test_banking_routing_helpers_are_owned_by_banking_system():
    from macro_sim.economy import Economy

    extracted_helpers = {
        "_assign_banks_genesis",
        "_bank_for",
        "_bank_constraint",
        "_refresh_loan_books",
        "_reserve_position",
        "_rate_competition",
        "_loan_rate_for",
    }

    assert extracted_helpers.isdisjoint(Economy.__dict__)


def test_remaining_banking_helpers_are_owned_by_banking_system():
    from macro_sim.economy import Economy

    extracted_helpers = {
        "_grant_loan",
        "_shop_bank",
        "_bank_capacity",
        "_bank_economic_capital",
        "_setup_bank_equity",
        "_pay_bank_dividends",
        "_bank_fundamental",
        "_update_bank_valuation",
        "_bank_stock_market",
        "_bank_equity_value",
        "_find_bank_founder",
        "_found_bank",
        "_fail_bank",
        "_enable_reserves",
        "_settlement_node",
    }

    assert extracted_helpers.isdisjoint(Economy.__dict__)


def test_remaining_mechanism_helpers_are_owned_by_system_modules():
    from macro_sim.economy import Economy

    extracted_helpers = {
        "_diversify_mpc",
        "_draw_bank_kappas",
        "_draw_bank_spreads",
        "_draw_deposit_spreads",
        "_assert_securities_identities",
        "_setup_per_firm_equity",
        "_gibrat_shock",
    }

    assert extracted_helpers.isdisjoint(Economy.__dict__)


def test_config_exposes_passive_banking_config_view():
    from macro_sim.config import BankingConfig, Config

    cfg = Config.v124(
        seed=123,
        n_banks=7,
        bank_leverage_mean=12.0,
        bank_leverage_disp=0.2,
        bank_assignment="by_size",
        bank_capital_constraint=True,
        unified_bank_rwa=True,
        bank_migrate_on_failure=False,
        bank_target_capital_ratio=0.18,
        bank_exposure_limit=0.15,
        bank_rate_competition=True,
        bank_spread_disp=0.03,
        bank_search_m=4,
        interbank=True,
        interbank_rate_base=0.01,
        interbank_tightness=0.4,
        reserve_floor_frac=0.12,
        deposit_rate_disp=0.02,
        deposit_search_m=5,
        bank_equity=True,
        bank_equity_lambda=0.2,
        bank_equity_trading=True,
        bank_theta_equity=0.22,
        bank_dynamics=True,
        bank_min_capital=50.0,
        bank_entry_beta=0.3,
        bank_entry_max=2,
        bank_runs=True,
        run_sensitivity=0.8,
        run_health_ref=0.12,
        run_market_weight=0.6,
        run_fear_persistence=0.85,
        lolr=True,
    )

    assert isinstance(cfg.banking, BankingConfig)
    assert cfg.banking.bank_enabled is cfg.bank_enabled
    assert cfg.banking.n_banks == cfg.n_banks
    assert cfg.banking.seed == cfg.seed
    assert cfg.banking.bank_leverage_mean == cfg.bank_leverage_mean
    assert cfg.banking.bank_leverage_disp == cfg.bank_leverage_disp
    assert cfg.banking.bank_assignment == cfg.bank_assignment
    assert cfg.banking.bank_capital_constraint is cfg.bank_capital_constraint
    assert cfg.banking.unified_bank_rwa is cfg.unified_bank_rwa
    assert cfg.banking.mortgage_risk_weight == cfg.mortgage_risk_weight
    assert cfg.banking.mortgage_min_capital_ratio == cfg.mortgage_min_capital_ratio
    assert cfg.banking.bank_migrate_on_failure is cfg.bank_migrate_on_failure
    assert cfg.banking.bank_target_capital_ratio == cfg.bank_target_capital_ratio
    assert cfg.banking.bank_exposure_limit == cfg.bank_exposure_limit
    assert cfg.banking.bank_rate_competition is cfg.bank_rate_competition
    assert cfg.banking.bank_spread_disp == cfg.bank_spread_disp
    assert cfg.banking.bank_search_m == cfg.bank_search_m
    assert cfg.banking.interbank is cfg.interbank
    assert cfg.banking.interbank_rate_base == cfg.interbank_rate_base
    assert cfg.banking.interbank_tightness == cfg.interbank_tightness
    assert cfg.banking.reserve_floor_frac == cfg.reserve_floor_frac
    assert cfg.banking.deposit_rate_disp == cfg.deposit_rate_disp
    assert cfg.banking.deposit_search_m == cfg.deposit_search_m
    assert cfg.banking.bank_equity is cfg.bank_equity
    assert cfg.banking.bank_equity_lambda == cfg.bank_equity_lambda
    assert cfg.banking.bank_equity_trading is cfg.bank_equity_trading
    assert cfg.banking.bank_theta_equity == cfg.bank_theta_equity
    assert cfg.banking.bank_dynamics is cfg.bank_dynamics
    assert cfg.banking.bank_min_capital == cfg.bank_min_capital
    assert cfg.banking.bank_entry_beta == cfg.bank_entry_beta
    assert cfg.banking.bank_entry_max == cfg.bank_entry_max
    assert cfg.banking.bank_runs is cfg.bank_runs
    assert cfg.banking.run_sensitivity == cfg.run_sensitivity
    assert cfg.banking.run_health_ref == cfg.run_health_ref
    assert cfg.banking.run_market_weight == cfg.run_market_weight
    assert cfg.banking.run_fear_persistence == cfg.run_fear_persistence
    assert cfg.banking.lolr is cfg.lolr
    assert cfg.banking.bonds is cfg.bonds
    assert cfg.banking.rho == cfg.rho
    assert cfg.banking.genesis_founder_pool == cfg.genesis_founder_pool
    assert cfg.banking.w_fundamental == cfg.w_fundamental
    assert cfg.banking.w_chartist == cfg.w_chartist
    assert cfg.banking.portfolio_adjust == cfg.portfolio_adjust
    assert cfg.banking.lambda_p == cfg.lambda_p
    assert cfg.banking.trend_lambda == cfg.trend_lambda


def test_config_exposes_passive_central_bank_config_view():
    from macro_sim.config import CentralBankConfig, Config

    cfg = Config.v124(
        central_bank=True,
        r_interest=0.025,
        infl_ema_lambda=0.4,
        u_natural=0.07,
        r_neutral=0.015,
        r_max=0.25,
        omo=True,
        omo_reserve_target=0.35,
        omo_drain_frac=0.2,
    )

    assert isinstance(cfg.central_banking, CentralBankConfig)
    assert cfg.central_banking.central_bank is cfg.central_bank
    assert cfg.central_banking.r_interest == cfg.r_interest
    assert cfg.central_banking.infl_ema_lambda == cfg.infl_ema_lambda
    assert cfg.central_banking.u_natural == cfg.u_natural
    assert cfg.central_banking.r_neutral == cfg.r_neutral
    assert cfg.central_banking.r_max == cfg.r_max
    assert cfg.central_banking.omo is cfg.omo
    assert cfg.central_banking.bonds is cfg.bonds
    assert cfg.central_banking.interbank is cfg.interbank
    assert cfg.central_banking.omo_reserve_target == cfg.omo_reserve_target
    assert cfg.central_banking.omo_drain_frac == cfg.omo_drain_frac


def test_config_exposes_passive_capital_goods_config_view():
    from macro_sim.config import CapitalGoodsConfig, Config

    cfg = Config.v91(
        n_firms_k=5,
        government=True,
        gov_investment_share=0.08,
    )

    assert isinstance(cfg.capital_goods, CapitalGoodsConfig)
    assert cfg.capital_goods.capital_enabled is cfg.capital_enabled
    assert cfg.capital_goods.government is cfg.government
    assert cfg.capital_goods.gov_investment_share == cfg.gov_investment_share


def test_config_exposes_passive_goods_config_view():
    from macro_sim.config import Config, GoodsConfig

    cfg = Config.v9(government=True, a=1.7, household_interest_arrears=True)

    assert isinstance(cfg.goods, GoodsConfig)
    assert cfg.goods.government is cfg.government
    assert cfg.goods.a == cfg.a
    assert cfg.goods.household_interest_arrears is cfg.household_interest_arrears


def test_config_exposes_passive_settlement_config_view():
    from macro_sim.config import Config, SettlementConfig

    cfg = Config.v93(
        pro_rata_dividends=True,
        gov_investment_share=0.11,
        public_capital_depreciation=0.04,
        jg_productivity=0.6,
    )

    assert isinstance(cfg.settlement, SettlementConfig)
    assert cfg.settlement.government is cfg.government
    assert cfg.settlement.pro_rata_dividends is cfg.pro_rata_dividends
    assert cfg.settlement.per_firm_equity is cfg.per_firm_equity
    assert cfg.settlement.gov_investment_share == cfg.gov_investment_share
    assert cfg.settlement.public_capital_depreciation == cfg.public_capital_depreciation
    assert cfg.settlement.jg_productivity == cfg.jg_productivity


def test_config_exposes_passive_planning_config_view():
    from macro_sim.config import Config, PlanningConfig

    cfg = Config.v83(
        theta_wage=0.2,
        theta_price=0.35,
        lambda_q=0.12,
        q_invest_floor=0.7,
        q_invest_cap=1.8,
        wealth_effect=0.15,
        mpc_wealth_curvature=0.8,
        d_household0=125.0,
    )

    assert isinstance(cfg.planning, PlanningConfig)
    assert cfg.planning.theta_wage == cfg.theta_wage
    assert cfg.planning.theta_price == cfg.theta_price
    assert cfg.planning.lambda_q == cfg.lambda_q
    assert cfg.planning.q_invest_floor == cfg.q_invest_floor
    assert cfg.planning.q_invest_cap == cfg.q_invest_cap
    assert cfg.planning.wealth_effect == cfg.wealth_effect
    assert cfg.planning.mpc_wealth_curvature == cfg.mpc_wealth_curvature
    assert cfg.planning.d_household0 == cfg.d_household0


def test_config_exposes_passive_securities_config_view():
    from macro_sim.config import Config, SecuritiesConfig

    cfg = Config.v124(
        bond_maturity=5,
        bond_coupon=0.025,
        bond_finance_frac=0.75,
        bond_theta=0.2,
        bank_bond_appetite=0.3,
        reserve_floor_frac=0.12,
        bank_bond_duration_limit=2.5,
    )

    assert isinstance(cfg.securities, SecuritiesConfig)
    assert cfg.securities.bonds is cfg.bonds
    assert cfg.securities.government is cfg.government
    assert cfg.securities.bond_maturity == cfg.bond_maturity
    assert cfg.securities.bond_coupon == cfg.bond_coupon
    assert cfg.securities.bond_finance_frac == cfg.bond_finance_frac
    assert cfg.securities.p_firm0 == cfg.p_firm0
    assert cfg.securities.d_household0 == cfg.d_household0
    assert cfg.securities.bond_theta == cfg.bond_theta
    assert cfg.securities.bank_bond_appetite == cfg.bank_bond_appetite
    assert cfg.securities.interbank is cfg.interbank
    assert cfg.securities.reserve_floor_frac == cfg.reserve_floor_frac
    assert cfg.securities.bank_bond_duration_limit == cfg.bank_bond_duration_limit


def test_config_exposes_passive_firm_demographics_config_view():
    from macro_sim.config import Config, FirmDemographicsConfig

    cfg = Config.v92(
        bankrupt_persist=8,
        entry_beta=0.33,
        entry_max=4,
        startup_deposits=25.0,
        startup_capital=12.0,
        gibrat_growth=True,
        gibrat_sigma=0.07,
        gibrat_entry_a0=0.3,
        shares_per_firm=150.0,
    )

    assert isinstance(cfg.firm_demographics, FirmDemographicsConfig)
    assert cfg.firm_demographics.firm_dynamics is cfg.firm_dynamics
    assert cfg.firm_demographics.bankrupt_persist == cfg.bankrupt_persist
    assert cfg.firm_demographics.entry_beta == cfg.entry_beta
    assert cfg.firm_demographics.entry_max == cfg.entry_max
    assert cfg.firm_demographics.index_startup is cfg.index_startup
    assert cfg.firm_demographics.startup_deposits == cfg.startup_deposits
    assert cfg.firm_demographics.p_firm0 == cfg.p_firm0
    assert cfg.firm_demographics.startup_capital == cfg.startup_capital
    assert cfg.firm_demographics.gibrat_growth is cfg.gibrat_growth
    assert cfg.firm_demographics.gibrat_sigma == cfg.gibrat_sigma
    assert cfg.firm_demographics.gibrat_entry_a0 == cfg.gibrat_entry_a0
    assert cfg.firm_demographics.per_firm_equity is cfg.per_firm_equity
    assert cfg.firm_demographics.shares_per_firm == cfg.shares_per_firm


def test_config_exposes_passive_credit_config_view():
    from macro_sim.config import Config, CreditConfig

    cfg = Config.v115(
        household_credit=True,
        hh_subsistence=0.7,
        hh_amort=0.08,
        amort=0.12,
        margin_credit=True,
        bank_target_capital_ratio=0.14,
        interbank=True,
        deposit_rate_disp=0.02,
        bank_equity=True,
        interest_by_deposits=True,
        household_interest_arrears=True,
    )

    assert isinstance(cfg.credit, CreditConfig)
    assert cfg.credit.bank_enabled is cfg.bank_enabled
    assert cfg.credit.household_interest_arrears is cfg.household_interest_arrears
    assert cfg.credit.household_credit is cfg.household_credit
    assert cfg.credit.hh_subsistence == cfg.hh_subsistence
    assert cfg.credit.amort == cfg.amort
    assert cfg.credit.margin_credit is cfg.margin_credit
    assert cfg.credit.hh_amort == cfg.hh_amort
    assert cfg.credit.bank_target_capital_ratio == cfg.bank_target_capital_ratio
    assert cfg.credit.interbank is cfg.interbank
    assert cfg.credit.deposit_rate_disp == cfg.deposit_rate_disp
    assert cfg.credit.bank_equity is cfg.bank_equity
    assert cfg.credit.interest_by_deposits is cfg.interest_by_deposits


def test_config_exposes_passive_equity_config_view():
    from macro_sim.config import Config, EquityConfig

    cfg = Config.v115(
        seed=42,
        shares_per_firm=175.0,
        watchlist_size=7,
        founder_owned_genesis=True,
        genesis_founder_pool=0.12,
        lambda_d=0.22,
        lambda_p=0.11,
        trend_lambda=0.4,
        equity_ema_lambda=0.2,
        resid_income_lambda=0.18,
        q_invest_smooth=0.15,
        w_fundamental=0.7,
        w_chartist=0.3,
        margin_credit=True,
        theta_equity=0.25,
        portfolio_adjust=0.5,
        equity_finance=True,
        lambda_issue=0.17,
        household_bankruptcy=True,
    )

    assert isinstance(cfg.equity_market, EquityConfig)
    assert cfg.equity_market.seed == cfg.seed
    assert cfg.equity_market.per_firm_equity is cfg.per_firm_equity
    assert cfg.equity_market.shares_per_firm == cfg.shares_per_firm
    assert cfg.equity_market.watchlist_size == cfg.watchlist_size
    assert cfg.equity_market.founder_owned_genesis is cfg.founder_owned_genesis
    assert cfg.equity_market.genesis_founder_pool == cfg.genesis_founder_pool
    assert cfg.equity_market.lambda_d == cfg.lambda_d
    assert cfg.equity_market.lambda_p == cfg.lambda_p
    assert cfg.equity_market.trend_lambda == cfg.trend_lambda
    assert cfg.equity_market.equity_ema_lambda == cfg.equity_ema_lambda
    assert cfg.equity_market.resid_income_lambda == cfg.resid_income_lambda
    assert cfg.equity_market.q_invest_smooth == cfg.q_invest_smooth
    assert cfg.equity_market.w_fundamental == cfg.w_fundamental
    assert cfg.equity_market.w_chartist == cfg.w_chartist
    assert cfg.equity_market.margin_credit is cfg.margin_credit
    assert cfg.equity_market.theta_equity == cfg.theta_equity
    assert cfg.equity_market.portfolio_adjust == cfg.portfolio_adjust
    assert cfg.equity_market.equity_finance is cfg.equity_finance
    assert cfg.equity_market.lambda_issue == cfg.lambda_issue
    assert cfg.equity_market.household_bankruptcy is cfg.household_bankruptcy
