from __future__ import annotations

from datetime import date

import pytest

from macro_sim.config import Config
from macro_sim.demographics.agents import Person
from macro_sim.economy import Economy


def test_demographics_disabled_by_default():
    econ = Economy(Config(n_households=10, n_firms=2, n_ticks=1, seed=3))

    assert getattr(econ, "demographic_state", None) is None
    assert getattr(econ, "demographic_bridge", None) is None


def test_demographics_enabled_advances_one_demographic_day_per_economic_tick():
    econ = Economy(
        Config(
            n_households=50,
            n_firms=4,
            n_ticks=1,
            seed=5,
            demographics_enabled=True,
            demographics_population=50,
            demographic_lifecycle_consumption=True,
        )
    )
    before_tick = econ.demographic_state.tick_index
    before_alive = econ.demographic_state.alive_count

    econ.step()

    assert econ.demographic_state.tick_index == before_tick + 1
    assert econ.demographic_state.alive_count >= 0
    assert econ.demographic_bridge is not None
    assert before_alive > 0


def test_demographic_metrics_are_emitted_when_enabled():
    econ = Economy(
        Config(
            n_households=40,
            n_firms=3,
            n_ticks=1,
            seed=8,
            demographics_enabled=True,
            demographics_population=40,
            demographic_lifecycle_consumption=True,
        )
    )

    rec = econ.step()

    assert rec["demographics_enabled"] == 1.0
    assert rec["person_population_alive"] == econ.demographic_state.alive_count
    assert rec["person_labor_supply"] == rec["labor_supply"]
    assert 0.0 <= rec["person_wealth_gini"] <= 1.0
    assert "estate_suspense_total" in rec
    assert "orphan_support_spending" in rec


def test_demographic_metrics_include_population_denominators_and_per_capita_values():
    econ = Economy(
        Config.v123(
            n_households=80,
            n_firms_c=5,
            n_firms_k=2,
            n_banks=2,
            n_ticks=1,
            seed=9,
            demographics_enabled=True,
            demographics_population=80,
            demographic_lifecycle_consumption=True,
        )
    )

    rec = econ.step()

    assert rec["population_alive"] == rec["person_population_alive"]
    assert rec["adult_population"] == rec["demographic_adults"]
    assert rec["child_population"] == rec["demographic_children"]
    assert rec["elder_population"] == rec["demographic_elders"]
    assert rec["working_age_population"] >= 0.0
    assert rec["child_share"] + rec["adult_share"] + rec["elder_share"] == pytest.approx(1.0)
    assert rec["avg_household_size"] == pytest.approx(
        rec["population_alive"] / max(1.0, rec["demographic_households"])
    )
    assert rec["real_output_per_capita"] == pytest.approx(rec["real_output"] / rec["population_alive"])
    assert rec["real_consumption_per_capita"] == pytest.approx(rec["real_consumption"] / rec["population_alive"])
    assert rec["nominal_output_per_capita"] == pytest.approx(rec["nominal_output"] / rec["population_alive"])
    assert rec["household_income_per_capita"] == pytest.approx(rec["hh_income"] / rec["population_alive"])
    assert rec["household_saving_per_capita"] == pytest.approx(rec["hh_saving"] / rec["population_alive"])
    assert rec["money_per_capita"] == pytest.approx(rec["total_money"] / rec["population_alive"])
    assert rec["gross_household_assets_per_capita"] == pytest.approx(
        rec["gross_household_assets_total"] / rec["population_alive"]
    )
    assert rec["births_tick"] >= 0.0
    assert rec["deaths_tick"] >= 0.0
    assert rec["marriages_tick"] >= 0.0
    assert rec["divorces_tick"] >= 0.0
    assert rec["leaving_home_tick"] >= 0.0
    assert rec["birth_rate_per_1000_annualized"] >= 0.0
    assert rec["death_rate_per_1000_annualized"] >= 0.0


def test_demographic_economy_smoke_run_preserves_claim_identities():
    econ = Economy(
        Config(
            n_households=60,
            n_firms=5,
            n_ticks=10,
            seed=13,
            demographics_enabled=True,
            demographics_population=60,
            demographic_lifecycle_consumption=True,
        )
    )

    for _ in range(10):
        econ.step()
        econ.demographic_bridge.assert_all_claim_identities(econ)


def test_demographic_bridge_reconciles_complex_portfolios_in_live_economy():
    econ = Economy(
        Config(
            n_households=80,
            n_firms=6,
            n_firms_c=6,
            n_firms_k=3,
            n_ticks=3,
            seed=21,
            demographics_enabled=True,
            demographics_population=80,
            demographic_lifecycle_consumption=True,
            bank_enabled=True,
            bank_equity=True,
            government=True,
            bonds=True,
            capital_market=True,
            per_firm_equity=True,
            firm_dynamics=True,
        )
    )

    econ.demographic_bridge.assert_all_claim_identities(econ)
    for _ in range(3):
        econ.step()
        econ.demographic_bridge.assert_all_claim_identities(econ)


def test_live_complex_portfolios_do_not_require_tick_end_reconcile():
    econ = Economy(
        Config(
            n_households=80,
            n_firms=6,
            n_firms_c=6,
            n_firms_k=3,
            n_ticks=2,
            seed=41,
            demographics_enabled=True,
            demographics_population=80,
            demographic_lifecycle_consumption=True,
            bank_enabled=True,
            bank_equity=True,
            government=True,
            bonds=True,
            bond_finance_frac=0.2,
            bond_theta=0.05,
            capital_market=True,
            per_firm_equity=True,
            firm_dynamics=True,
            margin_credit=True,
        )
    )

    def fail_reconcile(*args, **kwargs):
        raise AssertionError("tick-end reconciliation should not be required")

    econ.demographic_bridge.reconcile_financial_claims_from_economy = fail_reconcile

    for _ in range(2):
        econ.step()
        econ.demographic_bridge.assert_all_claim_identities(econ)


def test_demographic_social_dynamics_are_configured_as_live_when_enabled():
    econ = Economy(
        Config(
            n_households=40,
            n_firms=3,
            n_ticks=1,
            seed=31,
            demographics_enabled=True,
            demographics_population=40,
            demographic_marriage_enabled=True,
            demographic_divorce_enabled=True,
            demographic_marriage_market_interval_days=7,
        )
    )

    social = econ.demographic_kernel.social_config
    assert social.marriage_enabled
    assert social.divorce_enabled
    assert social.marriage_market_interval_days == 7


def test_adult_leaving_home_runs_inside_economy_step_and_creates_account():
    econ = Economy(
        Config(
            n_households=80,
            n_firms=4,
            n_ticks=1,
            seed=32,
            demographics_enabled=True,
            demographics_population=80,
            demographic_adult_leaving_home_enabled=True,
            demographic_leave_home_min_age=18,
            demographic_annual_leave_rate_peak=365.0,
        )
    )
    parent = next(person for person in econ.demographic_state.people if person.alive and person.age >= 35)
    old_household_id = int(parent.household_id)
    child = Person(
        id=econ.demographic_state.next_person_id,
        age=23,
        sex="F",
        birth_date=date(econ.demographic_state.current_date.year - 23, 1, 1),
        mother_id=parent.id,
        household_id=old_household_id,
    )
    econ.demographic_state.next_person_id += 1
    econ.demographic_state.people.append(child)
    econ.demographic_bridge.claims.add_person(child.id, household_id=old_household_id)

    econ.step()

    assert child.household_id != old_household_id
    assert child.household_id in econ.demographic_bridge.household_to_account
    account_id = econ.demographic_bridge.account_for_household_id(child.household_id)
    assert econ.ledger.has_account(account_id)
    assert econ.demographic_bridge.claims.balance_sheet(child.id).household_id == child.household_id
