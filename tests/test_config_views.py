from types import SimpleNamespace

import pytest


class BankingCfgTrap:
    def __init__(self, view):
        self.banking = view

    def __getattr__(self, name):
        raise AssertionError(f"banking system read legacy cfg.{name}")


class CentralBankCfgTrap:
    def __init__(self, view):
        self.central_banking = view

    def __getattr__(self, name):
        raise AssertionError(f"central_bank system read legacy cfg.{name}")


class CapitalGoodsCfgTrap:
    def __init__(self, view):
        self.capital_goods = view

    def __getattr__(self, name):
        raise AssertionError(f"capital_goods system read legacy cfg.{name}")


class GoodsCfgTrap:
    def __init__(self, view):
        self.goods = view

    def __getattr__(self, name):
        raise AssertionError(f"goods system read legacy cfg.{name}")


class SettlementCfgTrap:
    def __init__(self, view):
        self.settlement = view

    def __getattr__(self, name):
        raise AssertionError(f"settlement system read legacy cfg.{name}")


class PlanningCfgTrap:
    def __init__(self, view):
        self.planning = view

    def __getattr__(self, name):
        raise AssertionError(f"planning system read legacy cfg.{name}")


class SecuritiesCfgTrap:
    def __init__(self, view):
        self.securities = view

    def __getattr__(self, name):
        raise AssertionError(f"securities system read legacy cfg.{name}")


class FirmDemographicsCfgTrap:
    def __init__(self, view):
        self.firm_demographics = view

    def __getattr__(self, name):
        raise AssertionError(f"firm_demographics system read legacy cfg.{name}")


class CreditCfgTrap:
    def __init__(self, view):
        self.credit = view

    def __getattr__(self, name):
        raise AssertionError(f"credit system read legacy cfg.{name}")


class EquityCfgTrap:
    def __init__(self, view):
        self.equity_market = view

    def __getattr__(self, name):
        raise AssertionError(f"equity system read legacy cfg.{name}")


def test_central_bank_system_reads_grouped_config_view_for_policy_rate():
    from macro_sim.systems.central_bank import set_policy_rate

    view = SimpleNamespace(central_bank=False, r_interest=0.037)
    # the CB reads its live dials from econ.policy (the player's control surface);
    # no hand-set rate here, so the frozen-config fallback path must be taken.
    econ = SimpleNamespace(
        cfg=CentralBankCfgTrap(view),
        policy=SimpleNamespace(policy_rate_override=None),
        _rate=0.0,
    )

    set_policy_rate(econ)

    assert econ._rate == pytest.approx(0.037)


def test_banking_system_reads_grouped_config_view_for_capital_constraint():
    from macro_sim.systems.banking import bank_constraint

    view = SimpleNamespace(bank_capital_constraint=True)
    econ = SimpleNamespace(cfg=BankingCfgTrap(view), banks=[object(), object()])

    assert bank_constraint(econ) is True


def test_central_bank_system_reads_grouped_config_view_for_omo_gate():
    from macro_sim.systems.central_bank import run_omo_phase

    # the OMO stance is a LIVE policy dial (econ.policy) since v12.4's CB extraction;
    # bonds/interbank (whether the machinery exists) stay structural config.
    view = SimpleNamespace(bonds=True, interbank=True)
    econ = SimpleNamespace(
        cfg=CentralBankCfgTrap(view),
        policy=SimpleNamespace(omo=False),
        _omo_flow=99.0,
    )

    run_omo_phase(econ)

    assert econ._omo_flow == 0.0


def test_capital_goods_system_reads_grouped_config_view_for_gate():
    from macro_sim.systems.capital_goods import run_capital_goods_phase

    view = SimpleNamespace(capital_enabled=False, government=False, gov_investment_share=0.0)
    econ = SimpleNamespace(cfg=CapitalGoodsCfgTrap(view), _public_investment=99.0, _gov_capital_units=88.0)

    run_capital_goods_phase(econ)

    assert econ._public_investment == 0.0
    assert econ._gov_capital_units == 0.0


def test_goods_system_reads_grouped_config_view_for_government_gate():
    import random

    from macro_sim.systems.goods import run_goods_phase

    view = SimpleNamespace(government=False, a=1.0)
    econ = SimpleNamespace(
        cfg=GoodsCfgTrap(view),
        policy=SimpleNamespace(tax_consumption_rate=0.0),
        households=[],
        c_firms=[],
        protocol=object(),
        rng=random.Random(0),
        ledger=SimpleNamespace(),
        _fiscal="GOV",
    )

    run_goods_phase(econ)

    assert econ._tax_consumption == 0.0
    assert econ._gov_consumption == 0.0


def test_settlement_system_reads_grouped_config_view_for_government_gate():
    from macro_sim.systems.settlement import run_settlement_phase

    view = SimpleNamespace(
        government=False,
        pro_rata_dividends=False,
        per_firm_equity=False,
        gov_investment_share=0.0,
        public_capital_depreciation=0.05,
        jg_productivity=0.0,
    )
    econ = SimpleNamespace(
        cfg=SettlementCfgTrap(view),
        policy=SimpleNamespace(tax_profit_rate=0.0, job_guarantee=False),
        households=[],
        firms=[],
        investing_firms=[],
    )

    run_settlement_phase(econ)

    assert econ._tax_profit == 0.0
    assert econ._benefit_paid == 0.0


def test_planning_system_reads_grouped_config_view_for_consumption_budget(monkeypatch):
    import random

    import macro_sim.systems.planning as planning_module
    from macro_sim.systems.planning import run_planning_phase

    monkeypatch.setattr(planning_module, "household_bond_value", lambda econ, household_id: 0.0)

    view = SimpleNamespace(
        theta_wage=0.0,
        theta_price=0.0,
        lambda_q=0.0,
        q_invest_floor=0.5,
        q_invest_cap=2.0,
        k_replacement_floor=False,
        wealth_effect=0.0,
        mpc_wealth_curvature=1.0,
        d_household0=100.0,
    )
    household = SimpleNamespace(
        id="H0",
        y_expected=10.0,
        lambda_y=0.0,
        income_realized=0.0,
        spent=0.0,
        consumption_budget=0.0,
        labor_sold=0.0,
        jg_labor=0.0,
        equity_value_ema=0.0,
        alpha1=0.8,
        alpha2=0.05,
    )
    econ = SimpleNamespace(
        cfg=PlanningCfgTrap(view),
        policy=SimpleNamespace(min_wage=0.0),
        households=[household],
        firms=[],
        rng=random.Random(0),
        ledger=SimpleNamespace(balance=lambda account_id: 100.0),
        _pubcap_factor=1.0,
    )

    run_planning_phase(econ)

    assert household.consumption_budget == pytest.approx(13.0)


def test_securities_system_reads_grouped_config_view_for_bond_market_value():
    from macro_sim.systems.securities import bond_market_value

    view = SimpleNamespace(bond_maturity=1, bond_coupon=0.0)
    econ = SimpleNamespace(cfg=SecuritiesCfgTrap(view), t=0, _rate=0.05)

    assert bond_market_value(econ, {"face": 100.0, "matures_at": 3}) == pytest.approx(100.0)


def test_firm_demographics_system_reads_grouped_config_view_for_startup_cash():
    from macro_sim.systems.firm_demographics import startup_cash

    view = SimpleNamespace(index_startup=True, startup_deposits=20.0, p_firm0=2.0)
    econ = SimpleNamespace(cfg=FirmDemographicsCfgTrap(view), _price_level=3.0)

    assert startup_cash(econ) == pytest.approx(30.0)


def test_credit_system_reads_grouped_config_view_for_bank_gate():
    from macro_sim.systems.credit import run_credit_phase

    view = SimpleNamespace(bank_enabled=False)
    econ = SimpleNamespace(cfg=CreditCfgTrap(view))

    run_credit_phase(econ)

    assert econ._new_loans == 0.0


def test_equity_system_reads_grouped_config_view_for_market_gate():
    from macro_sim.systems.equity import run_equity_phase

    view = SimpleNamespace(per_firm_equity=False)
    econ = SimpleNamespace(cfg=EquityCfgTrap(view), equity=None)

    run_equity_phase(econ)

    assert econ.equity is None
