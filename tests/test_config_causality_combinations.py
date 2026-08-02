from __future__ import annotations

from itertools import combinations

import pytest

from macro_sim.diagnostics.config_combinations import (
    COMBINATION_PACKAGES,
    INTERACTION_FOLLOWUPS,
    CombinationPackage,
    FactorSpec,
    OutcomeSpec,
    _reduce_design,
    fractional_factorial_design,
    interaction_alias_groups,
)
from macro_sim.diagnostics.config_contracts import build_contract_registry
from macro_sim.diagnostics.config_experiment import (
    apply_native_activation_scenario,
    native_joint_treatment_spec,
    native_joint_world_treatment_spec,
    population_scaled_new_game,
)


def test_resolution_four_design_is_balanced_and_orthogonal() -> None:
    factors = tuple(FactorSpec(f"f{index}", -1, 1) for index in range(7))
    arms = fractional_factorial_design(factors)
    assert len(arms) == 16
    assert len({arm.signs for arm in arms}) == 16
    for index in range(7):
        assert sum(arm.signs[index] for arm in arms) == 0
    for left, right in combinations(range(7), 2):
        assert sum(
            arm.signs[left] * arm.signs[right] for arm in arms
        ) == 0
        for main in range(7):
            assert sum(
                arm.signs[main] * arm.signs[left] * arm.signs[right]
                for arm in arms
            ) == 0


def test_fractional_design_reports_two_factor_aliases() -> None:
    factors = tuple(FactorSpec(f"f{index}", -1, 1) for index in range(7))
    aliases = interaction_alias_groups(factors)
    assert set(aliases) == {
        f"f{left}:f{right}" for left, right in combinations(range(7), 2)
    }
    assert all(name in group for name, group in aliases.items())
    assert any(len(group) > 1 for group in aliases.values())


def _synthetic_result(value: float) -> dict:
    summary = {
        "mean": value,
        "final": value,
        "volatility": 0.0,
        "first_window_mean": value,
        "last_window_mean": value,
        "cumulative": value,
        "post_burnin_mean": value,
        "post_burnin_volatility": 0.0,
    }
    return {
        "economy_id": 0,
        "metric_summaries_by_economy": {"0": {"metric.test": summary}},
    }


def test_factorial_reducer_recovers_main_and_interaction_contrasts() -> None:
    package = CombinationPackage(
        package_id="synthetic",
        title="Synthetic",
        scope="root",
        activation_scenario="neutral_baseline",
        days=2,
        countries=1,
        factors=(
            FactorSpec("a", -1, 1),
            FactorSpec("b", -1, 1),
            FactorSpec("c", -1, 1),
        ),
        outcomes=(OutcomeSpec("metric.test", "mean"),),
    )
    arms = fractional_factorial_design(package.factors)
    arm_results = {}
    references = {}
    for seed, offset in ((1, 0.0), (2, 1.0), (3, -1.0), (4, 0.5)):
        arm_results[seed] = [
            _synthetic_result(
                10.0
                + offset
                + 2.0 * arm.signs[0]
                + 3.0 * arm.signs[1]
                + 4.0 * arm.signs[0] * arm.signs[1]
            )
            for arm in arms
        ]
        references[seed] = _synthetic_result(10.0 + offset)
    reduced = _reduce_design(package, arms, arm_results, references)
    outcome = "metric.test|mean|player"
    assert reduced["main_effects"]["a"][outcome]["mean_difference"] == pytest.approx(4.0)
    assert reduced["main_effects"]["b"][outcome]["mean_difference"] == pytest.approx(6.0)
    assert reduced["main_effects"]["c"][outcome]["mean_difference"] == pytest.approx(0.0)
    interaction = reduced["two_factor_interactions"]["a:b"][outcome]
    assert interaction["mean_difference"] == pytest.approx(16.0)


def test_joint_root_treatment_applies_capability_closure() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=77, countries=1
    )
    native_spec = native_joint_treatment_spec(
        baseline,
        treatments={"interbank": False, "amort": 0.002},
    )
    monetary = (
        native_spec.economies[0].domestic_economy.financial_economy
        .monetary_economy
    )
    assert monetary.rules.interbank is False
    assert monetary.rules.bank_runs is False
    assert monetary.rules.firm_amortization == pytest.approx(0.002)
    assert monetary.policy.open_market_operations is False
    assert monetary.policy.lender_of_last_resort is False


def test_joint_world_treatment_preserves_each_requested_level() -> None:
    baseline = population_scaled_new_game(
        population=100_000, days=90, seed=78, countries=3
    )
    native_spec = native_joint_world_treatment_spec(
        baseline,
        treatments={
            "fx_trade_cap": 0.30,
            "capital_mobility": 0.20,
            "migration_rate": 0.005,
        },
    )
    assert native_spec.rules.fx_trade_cap == pytest.approx(0.30)
    assert native_spec.rules.capital_mobility == pytest.approx(0.20)
    assert native_spec.rules.migration_rate == pytest.approx(0.005)


def test_all_seven_packages_use_reviewed_fields_and_valid_activations() -> None:
    assert set(COMBINATION_PACKAGES) == {
        "productive_capacity",
        "labor_institutions",
        "credit_architecture",
        "housing_family",
        "energy_dependence",
        "firm_dynamism",
        "open_economy",
    }
    contracts = {
        (row["scope"], row["field_name"]): row
        for row in build_contract_registry()["contracts"]
    }
    executable = {"screening_ready", "activation_scenario_required"}
    for package in COMBINATION_PACKAGES.values():
        assert 6 <= len(package.factors) <= 7
        for factor in package.factors:
            assert contracts[(package.scope, factor.field)]["status"] in executable
        baseline = population_scaled_new_game(
            population=100_000,
            days=package.days,
            seed=79,
            countries=package.countries,
        )
        for arm in fractional_factorial_design(package.factors):
            native_spec = (
                native_joint_world_treatment_spec(
                    baseline,
                    treatments=arm.treatments,
                )
                if package.scope == "world"
                else native_joint_treatment_spec(
                    baseline,
                    treatments=arm.treatments,
                )
            )
            apply_native_activation_scenario(
                native_spec, scenario=package.activation_scenario
            )


def test_housing_combination_spans_second_annual_feedback() -> None:
    assert COMBINATION_PACKAGES["housing_family"].days >= 800


def test_interaction_followups_are_unaliased_full_factorials() -> None:
    assert len(INTERACTION_FOLLOWUPS) == len(COMBINATION_PACKAGES)
    for package in INTERACTION_FOLLOWUPS.values():
        assert len(package.factors) == 2
        arms = fractional_factorial_design(package.factors)
        assert len(arms) == 4
        assert all(
            aliases == (interaction,)
            for interaction, aliases in interaction_alias_groups(
                package.factors
            ).items()
        )
