# v13 Phase 1 Demographic-Economy Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the validated Phase 0 demographic kernel to the closed-economy engine as a one-way population-to-economy layer: people enter, age, work, consume, own claims, form households, die, and transmit wealth without economic state feeding back into vital rates.

**Architecture:** Phase 1 is organized by four population-to-economy channels: birth/death balance-sheet entry and clearing, age-derived labor supply, age-derived lifecycle consumption and asset demand, and death-derived inheritance. Marriage economics, adult leaving-home dynamics, and person-level claim accounting are cross-cutting modules that support those channels. Market settlement may remain at household account level, but every household account must reconcile to person-level ownership claims.

**Tech Stack:** Python dataclasses, existing Phase 0 `Person` and event hooks, existing `Economy`, `Ledger`, `Household`, and market systems, pytest focused tests, and parallel pytest only after major boundaries are complete.

## Implementation Status (2026-07-08)

Phase 1 core is implemented behind `Config.demographics_enabled`:

- Person ownership claims, household profiles, birth/death balance-sheet hooks, estate suspense, automatic inheritance settlement, insolvent-death bank write-off path, age-derived labor supply, finite-life lifecycle consumption, goods/labor/dividend claim posting, community-property marriage/divorce/death settlement, adult leaving-home dynamics, child-cost allocation, person-level metrics, and optional `Economy` integration are in code.
- `Economy` now uses the demographic genesis household count when demographics are enabled, so the model is driven by a population parameter rather than a fixed exogenous household count in that mode.
- `Economy` now wires live marriage/divorce hooks from `MicroDemographicKernel` into the demographic-economic bridge. Live social dynamics are configurable through `Config.demographic_marriage_enabled`, `Config.demographic_divorce_enabled`, `Config.demographic_marriage_market_interval_days`, `Config.demographic_annual_marriage_rate_peak`, and `Config.demographic_annual_divorce_rate_base`.
- Adult leaving-home dynamics now run inside the economic tick when `Config.demographic_adult_leaving_home_enabled` is true. Leaving adults receive a new household account through the bridge, with person claims and ledger accounts synchronized.
- Household-level complex portfolios now reconcile to person-level claims for per-firm equity, aggregate equity, bond face, bank equity, and debt through a tick-end bridge synchronization.
- Current focused demographic gate suite passed in parallel with 10 workers: `87 passed`.
- Integrated demographic economy smoke tests include live social configuration, adult leaving-home account creation, and complex portfolio reconciliation.

Deferred follow-up after this Phase 1 landing:

- Complex asset ownership currently uses tick-end household-to-person reconciliation. This is accounting-safe and covered by identity gates, but it is not yet full transaction-level provenance for every stock/bond/bank-equity trade.
- Inheritance tax timing and public escheat rules remain policy extensions. The default implemented rule settles estates to living spouse/children/parents; estates with no living default heir remain in suspense.

## Global Constraints

- Phase 1 is strictly population -> economy. No Phase 1 rule may let income, wealth, wages, employment, prices, or policy alter birth, death, marriage, divorce, or migration probabilities.
- Every Phase 1 channel must preserve the Phase 0 demographic trajectory for the same seed and demographic configuration. Population counts, events, and social-health invariants must match the frozen-economy baseline.
- Person-level balance sheets are ownership claims. Household ledger accounts may remain the payment surface until a later phase.
- Every household-level deposit, debt, security holding, and realized flow must have a matching person-level posting or documented estate/public-support posting.
- A1/A5 accounting identities are hard gates. Personal claim transfers, marriage dissolution, inheritance, and household splits must never create or destroy aggregate private net worth unless a fiscal transfer, tax, debt write-off, or bank loss explicitly records the counterparty.
- Birth creates a zero-endowment person balance sheet. Gifts and inter vivos transfers are not part of birth.
- Death first clears marital property, then repays debt from the dead person's assets, then creates an estate or bank write-off. If inheritance is not yet enabled, positive estate claims remain in a suspense record. Negative net worth is absorbed by the identified lending bank as a loan write-off; missing creditor identity is a hard error.
- Default marriage property regime is community property: marital gains and losses are split on divorce and on death before estate creation.
- Lifecycle saving behavior must not directly encode an age-saving-rate curve. Encode finite-life consumption smoothing and age-dependent income capacity; verify whether the Modigliani hump emerges.
- Focused tests must run after each task. Broad parallel regression runs happen only at phase gates.

---

## File Structure

- Create `macro_sim/demographics/economic_state.py`
  - Person balance sheets, household economic profiles, need units, labor supply, and claim identity checks.
- Create `macro_sim/demographics/economic_bridge.py`
  - Bridge between demographic household ids, economic household account ids, and person ownership claims.
- Create `macro_sim/demographics/estate.py`
  - Death suspense records, estate creation, and estate clearing before inheritance is enabled.
- Create `macro_sim/demographics/inheritance.py`
  - Default heir selection, estate distribution, and inheritance tax hook.
- Create `macro_sim/demographics/lifecycle.py`
  - Remaining-life estimates, age-income capacity, finite-life annuitized consumption rule, and lifecycle diagnostics.
- Create `macro_sim/demographics/lifecycle_households.py`
  - Adult children leaving parental households and dynamic household-account creation.
- Create `macro_sim/demographics/marriage_economics.py`
  - Marriage contracts, marriage snapshots, community-property dissolution, and death/divorce settlement core.
- Modify `macro_sim/demographics/kernel.py`
  - Route demographic events to bridge hooks without embedding economic logic inside the demographic kernel.
- Modify `macro_sim/economy.py`
  - Own optional demographic state and bridge when `demographics_enabled` is true.
- Modify `macro_sim/systems/labor.py`
  - Replace fixed household labor supply `1.0` with demographic household labor supply when enabled.
- Modify `macro_sim/systems/settlement.py`
  - Replace benefit and job-guarantee residual formulas with demographic labor residuals.
- Modify `macro_sim/systems/planning.py`
  - Feed lifecycle household income and wealth inputs into household consumption planning when enabled.
- Modify `macro_sim/systems/goods.py`
  - Post realized household consumption back to person claims.
- Modify `macro_sim/reporting/metrics.py`
  - Add person-level labor, dependency, welfare, lifecycle, and inheritance metrics.
- Add tests:
  - `tests/test_demographic_economic_claims.py`
  - `tests/test_demographic_economic_bridge.py`
  - `tests/test_demographic_birth_death_economics.py`
  - `tests/test_demographic_labor_supply.py`
  - `tests/test_demographic_lifecycle_consumption.py`
  - `tests/test_demographic_marriage_economics.py`
  - `tests/test_demographic_lifecycle_households.py`
  - `tests/test_demographic_inheritance.py`
  - `tests/test_demographic_phase1_baseline_invariance.py`
  - `tests/test_demographic_economy_integration.py`

---

## Phase 1.0: Person Ownership Claims and Baseline Invariance

### Task 1: Add the person claim ledger

**Files:**
- Create: `macro_sim/demographics/economic_state.py`
- Test: `tests/test_demographic_economic_claims.py`

**Interfaces:**
- Produces:
  - `PersonBalanceSheet`
  - `HouseholdEconomicProfile`
  - `PersonClaimLedger`
  - `PersonClaimLedger.add_person(person_id: int, household_id: int, cash_claim: float = 0.0, debt_claim: float = 0.0) -> None`
  - `PersonClaimLedger.balance_sheet(person_id: int) -> PersonBalanceSheet`
  - `PersonClaimLedger.net_worth(person_id: int) -> float`
  - `PersonClaimLedger.total_net_worth() -> float`
  - `PersonClaimLedger.assert_household_claim_identity(household_id: int, deposits: float, debt: float, holdings: dict[str, float]) -> None`

- [ ] **Step 1: Write failing tests**

```python
import pytest

from macro_sim.demographics.economic_state import PersonClaimLedger


def test_person_claims_sum_to_household_deposits_and_debt():
    claims = PersonClaimLedger()
    claims.add_person(1, household_id=10, cash_claim=60.0, debt_claim=5.0)
    claims.add_person(2, household_id=10, cash_claim=40.0, debt_claim=15.0)

    claims.assert_household_claim_identity(
        household_id=10,
        deposits=100.0,
        debt=20.0,
        holdings={},
    )


def test_claim_identity_rejects_unbacked_cash():
    claims = PersonClaimLedger()
    claims.add_person(1, household_id=10, cash_claim=101.0)

    with pytest.raises(AssertionError, match="cash claim mismatch"):
        claims.assert_household_claim_identity(
            household_id=10,
            deposits=100.0,
            debt=0.0,
            holdings={},
        )
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
uv run pytest -q tests/test_demographic_economic_claims.py
```

Expected: fail because `macro_sim.demographics.economic_state` does not exist.

- [ ] **Step 3: Implement `PersonBalanceSheet` and `PersonClaimLedger`**

Implement `PersonBalanceSheet` with:

```python
@dataclass
class PersonBalanceSheet:
    person_id: int
    household_id: int
    cash_claim: float = 0.0
    debt_claim: float = 0.0
    equity_claims: dict[str, float] = field(default_factory=dict)
    bond_face_claim: float = 0.0
    bank_equity_claims: dict[str, float] = field(default_factory=dict)
    labor_income_tick: float = 0.0
    capital_income_tick: float = 0.0
    transfer_income_tick: float = 0.0
    tax_paid_tick: float = 0.0
    consumption_allocated_tick: float = 0.0
```

Implement `PersonClaimLedger` as the only writer of these fields. Use `abs(diff) <= 1e-7` for floating-point identity checks.

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_economic_claims.py
```

Expected: pass.

### Task 2: Add the demographic-economic bridge

**Files:**
- Create: `macro_sim/demographics/economic_bridge.py`
- Test: `tests/test_demographic_economic_bridge.py`

**Interfaces:**
- Consumes:
  - `GenesisState.people`
  - `Economy.households`
  - `Economy.ledger`
- Produces:
  - `DemographicEconomicBridge`
  - `initialize_person_claims_from_households(econ, demographic_state, claim_split_policy: str = "adult_equal") -> DemographicEconomicBridge`
  - `DemographicEconomicBridge.account_for_household_id(household_id: int) -> str`
  - `DemographicEconomicBridge.household_id_for_account(account_id: str) -> int`
  - `DemographicEconomicBridge.assert_all_claim_identities(econ) -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_genesis_claims_seed_adult_equal_and_reconcile_household_cash(econ_stub, demographic_state):
    bridge = initialize_person_claims_from_households(econ_stub, demographic_state)

    assert bridge.claims.balance_sheet(1).cash_claim == 60.0
    assert bridge.claims.balance_sheet(2).cash_claim == 60.0
    assert bridge.claims.balance_sheet(3).cash_claim == 0.0
    bridge.claims.assert_household_claim_identity(0, deposits=120.0, debt=0.0, holdings={})
```

Fixture shape:

```text
demographic household_id=0 has adult person ids 1,2 and child person id 3
economic account H0 has ledger balance 120.0 and no debt
```

- [ ] **Step 2: Implement adult-equal seeding**

Rules:

```text
live adults in household: split initial household net financial assets equally
minors: zero initial claims unless they already have an explicit inherited claim
households with no adult: put claims on public guardian account or guardian adult if one exists
```

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_economic_bridge.py
```

Expected: pass.

### Task 3: Add the Phase 1 baseline-invariance harness

**Files:**
- Create: `tests/test_demographic_phase1_baseline_invariance.py`
- Modify: `macro_sim/demographics/economic_bridge.py`

**Interfaces:**
- Produces:
  - `run_phase1_invariance_check(rates, n, seed, years, enabled_channels) -> dict`

- [ ] **Step 1: Write failing baseline-invariance tests**

```python
from macro_sim.demographics import Phase0VitalRates, create_genesis_population
from macro_sim.demographics.kernel import MicroDemographicKernel


def test_empty_economic_bridge_does_not_change_population_path():
    rates = Phase0VitalRates()
    base = create_genesis_population(rates, n=500, seed=11)
    with_bridge = create_genesis_population(rates, n=500, seed=11)

    base_kernel = MicroDemographicKernel(rates, rng_seed=12)
    bridge_kernel = MicroDemographicKernel(rates, rng_seed=12)

    for _ in range(365):
        base_result = base_kernel.tick(base)
        bridge_result = bridge_kernel.tick(with_bridge, economic_state=object())
        assert base_result == bridge_result

    assert [(p.id, p.alive, p.age, p.household_id, p.partner_id) for p in base.people] == [
        (p.id, p.alive, p.age, p.household_id, p.partner_id) for p in with_bridge.people
    ]
```

- [ ] **Step 2: Implement invariance helper**

Use identical demographic seeds and compare event counts and person states. Do not compare economic fields.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_phase1_baseline_invariance.py
```

Expected: pass.

---

## Phase 1.1: Birth and Death as Balance-Sheet Entry and Clearing

### Task 4: Birth creates a zero-endowment person balance sheet

**Files:**
- Modify: `macro_sim/demographics/economic_bridge.py`
- Test: `tests/test_demographic_birth_death_economics.py`

**Interfaces:**
- Produces:
  - `DemographicEconomicBridge.on_birth(event, newborn) -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_birth_creates_zero_endowment_balance_sheet(bridge, birth_event, newborn):
    bridge.on_birth(birth_event, newborn)

    sheet = bridge.claims.balance_sheet(newborn.id)
    assert sheet.cash_claim == 0.0
    assert sheet.debt_claim == 0.0
    assert sheet.household_id == newborn.household_id
```

- [ ] **Step 2: Implement `on_birth`**

Birth rule:

```text
newborn gets a person claim record
cash_claim = 0
debt_claim = 0
asset claims = empty
household_id = mother's current household_id
```

Do not transfer assets from parents at birth.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_birth_death_economics.py
```

Expected: pass.

### Task 5: Death creates an estate suspense record after marital settlement hook

**Files:**
- Create: `macro_sim/demographics/estate.py`
- Modify: `macro_sim/demographics/economic_bridge.py`
- Test: `tests/test_demographic_birth_death_economics.py`

**Interfaces:**
- Produces:
  - `EstateRecord`
  - `EstateRegistry`
  - `EstateRegistry.create_suspense_estate(dead_person_id: int, net_worth: float, created_tick: int) -> EstateRecord`
  - `DemographicEconomicBridge.write_off_deceased_debt(person_id: int, unpaid_amount: float, creditor_bank_id: str) -> None`
  - `DemographicEconomicBridge.on_death(event, dead_person) -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_death_moves_positive_net_worth_to_estate_suspense(bridge, death_event, dead_person):
    bridge.claims.add_person(dead_person.id, household_id=0, cash_claim=90.0, debt_claim=10.0)

    bridge.on_death(death_event, dead_person)

    estate = bridge.estates.estate_for(dead_person.id)
    assert estate.net_worth == 80.0
    assert bridge.claims.net_worth(dead_person.id) == 0.0
    assert bridge.claims.total_net_worth(include_estates=True) == 80.0
```

```python
def test_insolvent_death_writes_unpaid_debt_to_lending_bank(bridge, death_event, dead_person):
    bridge.claims.add_person(dead_person.id, household_id=0, cash_claim=30.0, debt_claim=100.0)
    bridge.assign_person_creditor_bank(dead_person.id, "BANK_0")
    bank_before = bridge.bank_capital("BANK_0")

    bridge.on_death(death_event, dead_person)

    assert bridge.estates.estate_for(dead_person.id).net_worth == 0.0
    assert bridge.claims.net_worth(dead_person.id) == 0.0
    assert bridge.death_writeoff_flow == pytest.approx(70.0)
    assert bridge.bank_capital("BANK_0") == pytest.approx(bank_before - 70.0)
```

```python
def test_insolvent_death_without_known_creditor_bank_halts(bridge, death_event, dead_person):
    bridge.claims.add_person(dead_person.id, household_id=0, cash_claim=30.0, debt_claim=100.0)

    with pytest.raises(RuntimeError, match="missing creditor bank"):
        bridge.on_death(death_event, dead_person)
```

- [ ] **Step 2: Implement estate suspense and bank write-off**

Phase 1.1 rule:

```text
if dead person assets >= debt:
  repay debt from dead person's assets
  move remaining positive net worth to estate suspense
if dead person assets < debt:
  use all dead person's assets to repay debt
  unpaid debt = debt - assets
  reduce the dead person's debt claim to zero
  reduce the creditor bank's loan asset and capital/equity by unpaid debt
  create a zero-value estate suspense record
  record death_writeoff_flow += unpaid debt
if creditor bank cannot be identified for unpaid debt:
  raise RuntimeError("missing creditor bank")
```

This keeps A5 explicit: household/person debt falls only because the matching bank loan asset and bank equity absorb the loss. It is not a fiscal transfer and not inherited by children or spouse in Phase 1.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_birth_death_economics.py
```

Expected: pass.

### Task 6: Gate birth/death economic hooks against population feedback

**Files:**
- Modify: `tests/test_demographic_phase1_baseline_invariance.py`
- Modify: `macro_sim/demographics/economic_bridge.py`

**Interfaces:**
- Consumes:
  - `DemographicEconomicBridge.on_birth`
  - `DemographicEconomicBridge.on_death`

- [ ] **Step 1: Write invariance test with hooks enabled**

```python
def test_birth_death_economic_hooks_do_not_change_demographic_path():
    result = run_phase1_invariance_check(
        rates=Phase0VitalRates(),
        n=500,
        seed=21,
        years=3,
        enabled_channels=["birth_death_balance_sheet"],
    )
    assert result["event_sequence_equal"] is True
    assert result["alive_by_age_equal"] is True
```

- [ ] **Step 2: Implement hook wiring**

Wire `MicroDemographicKernel(on_birth=bridge.on_birth, on_death=bridge.on_death)` in the test harness only. Do not attach to full `Economy` yet.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_birth_death_economics.py tests/test_demographic_phase1_baseline_invariance.py
```

Expected: pass.

---

## Phase 1.2: Age-Derived Labor Supply

### Task 7: Compute demographic labor supply and dependency ratios

**Files:**
- Modify: `macro_sim/demographics/economic_state.py`
- Test: `tests/test_demographic_labor_supply.py`

**Interfaces:**
- Produces:
  - `labor_supply_for_person(person, current_date, min_age: int = 18, max_age: int = 64) -> float`
  - `need_weight_for_person(person) -> float`
  - `build_household_economic_profiles(state, claims) -> dict[int, HouseholdEconomicProfile]`

- [ ] **Step 1: Write failing tests**

```python
def test_household_labor_supply_counts_working_age_people_only(state_with_ages, claims):
    state = state_with_ages([8, 35, 37, 71])
    profiles = build_household_economic_profiles(state, claims)

    assert profiles[0].labor_supply == 2.0
    assert profiles[0].child_count == 1
    assert profiles[0].elder_count == 1
    assert profiles[0].dependency_ratio == 1.0
```

- [ ] **Step 2: Implement default categories**

Defaults:

```text
child: age < 18, labor_supply=0, need_weight=0.65
worker: 18 <= age <= 64, labor_supply=1, need_weight=1.0
elder: age >= 65, labor_supply=0, need_weight=0.9
```

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_labor_supply.py
```

Expected: pass.

### Task 8: Replace private labor supply `1.0` with demographic supply

**Files:**
- Modify: `macro_sim/systems/labor.py`
- Modify: `macro_sim/demographics/economic_bridge.py`
- Test: `tests/test_demographic_labor_supply.py`

**Interfaces:**
- Produces:
  - `DemographicEconomicBridge.household_labor_supply(account_id: str) -> float`
  - `DemographicEconomicBridge.post_labor_income(account_id: str, worker_person_ids: list[int], amount: float) -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_labor_phase_uses_demographic_supply_when_enabled(econ_with_demographic_bridge):
    run_labor_phase(econ_with_demographic_bridge)

    assert econ_with_demographic_bridge.households[0].labor_sold <= 2.0
    assert econ_with_demographic_bridge.households[1].labor_sold == 0.0
```

```python
def test_labor_phase_uses_legacy_supply_when_demographics_disabled(econ_without_demographics):
    run_labor_phase(econ_without_demographics)

    assert all(h.labor_sold <= 1.0 for h in econ_without_demographics.households)
```

- [ ] **Step 2: Implement supply fallback**

In `macro_sim/systems/labor.py`, replace the fixed residual array with:

```python
remaining = [
    econ.demographic_bridge.household_labor_supply(worker.id)
    if getattr(econ, "demographic_bridge", None) is not None
    else 1.0
    for worker in workers
]
```

Post labor income to the bridge after each wage transfer. Phase 1.2 may allocate wage income equally among currently available working-age members of that household.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_labor_supply.py
```

Expected: pass.

### Task 9: Scale JG and unemployment benefits by demographic labor residual

**Files:**
- Modify: `macro_sim/systems/settlement.py`
- Modify: `macro_sim/demographics/economic_bridge.py`
- Test: `tests/test_demographic_labor_supply.py`

**Interfaces:**
- Consumes:
  - `DemographicEconomicBridge.household_labor_supply(account_id: str) -> float`
  - `DemographicEconomicBridge.post_transfer_income(account_id: str, amount: float, reason: str) -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_unemployment_benefit_uses_demographic_labor_supply(econ_with_demographic_bridge):
    # H0 has labor supply 3.0 and sold 1.0 labor.
    run_household_fiscal_phase(econ_with_demographic_bridge)

    assert econ_with_demographic_bridge._benefit_paid == pytest.approx(2.0 * expected_unit_benefit)
```

- [ ] **Step 2: Implement residual helper**

Use:

```python
def _household_labor_supply(econ, household):
    bridge = getattr(econ, "demographic_bridge", None)
    return bridge.household_labor_supply(household.id) if bridge is not None else 1.0
```

Then:

```python
resid = max(0.0, labor_supply - h.labor_sold)
benefit_base = max(0.0, labor_supply - h.labor_sold - h.jg_labor)
```

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_labor_supply.py
```

Expected: pass.

---

## Phase 1.3: Age-Derived Lifecycle Consumption, Saving, and Asset Demand

### Task 10: Add finite-life consumption smoothing primitives

**Files:**
- Create: `macro_sim/demographics/lifecycle.py`
- Test: `tests/test_demographic_lifecycle_consumption.py`

**Interfaces:**
- Produces:
  - `expected_remaining_life_years(age: int, rates) -> float`
  - `age_income_capacity(age: int, entry_age: int = 18, retire_age: int = 65) -> float`
  - `person_wealth_draw(net_worth: float, remaining_life_years: float, ticks_per_year: int = 365) -> float`
  - `person_permanent_income(income_ema: float, age: int, entry_age: int = 18, retire_age: int = 65) -> float`

- [ ] **Step 1: Write failing tests**

```python
def test_remaining_life_declines_with_age():
    rates = Phase0VitalRates()

    assert expected_remaining_life_years(25, rates) > expected_remaining_life_years(70, rates)
```

```python
def test_person_wealth_draw_rises_as_remaining_life_shortens():
    wealth = 100.0

    young_daily = person_wealth_draw(wealth, remaining_life_years=50.0)
    old_daily = person_wealth_draw(wealth, remaining_life_years=10.0)

    assert old_daily > young_daily
```

```python
def test_person_wealth_draw_ignores_negative_net_worth():
    assert person_wealth_draw(-100.0, remaining_life_years=30.0) == 0.0
```

```python
def test_person_permanent_income_uses_income_capacity_not_saving_rate():
    income_ema = 10.0

    child_income = person_permanent_income(income_ema, age=12)
    prime_income = person_permanent_income(income_ema, age=40)
    retired_income = person_permanent_income(income_ema, age=70)

    assert child_income == 0.0
    assert prime_income == income_ema
    assert retired_income == 0.0
```

- [ ] **Step 2: Implement primitives without encoding a saving-rate curve**

Rules:

```text
expected_remaining_life_years uses the Phase 0 survival curve.
expected_remaining_life_years(age) = sum_{s=age}^{omega} l(s) / l(age), converted to years.
age_income_capacity is an earning-capacity profile, not a saving-rate profile.
person_wealth_draw = max(net_worth, 0) / max(remaining_life_years * ticks_per_year, 1).
person_permanent_income = income_ema * age_income_capacity(age).
```

Default `age_income_capacity(age)`:

```text
age < 18: 0.0
18 <= age <= 25: linearly rises from 0.5 to 1.0
26 <= age <= 50: 1.0
51 <= age <= 64: linearly falls from 1.0 to 0.7
age >= 65: 0.0
```

This profile is an income-capacity endowment. Do not add `saving_rate_by_age`, `target_wealth_by_age`, or any direct age-saving rule.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_lifecycle_consumption.py
```

Expected: pass.

### Task 11: Build household lifecycle consumption budgets

**Files:**
- Modify: `macro_sim/demographics/lifecycle.py`
- Modify: `macro_sim/demographics/economic_bridge.py`
- Modify: `macro_sim/systems/planning.py`
- Test: `tests/test_demographic_lifecycle_consumption.py`

**Interfaces:**
- Produces:
  - `household_lifecycle_consumption_budget(profile, claims, rates, alpha_income: float, alpha_wealth_draw: float, ticks_per_year: int = 365) -> float`
  - `DemographicEconomicBridge.household_control_income(account_id: str) -> float`
  - `DemographicEconomicBridge.household_control_wealth(account_id: str) -> float`

- [ ] **Step 1: Write failing tests**

```python
def test_same_wealth_older_household_draws_more_annuitized_wealth_than_young_household():
    young_budget = household_lifecycle_consumption_budget(
        profile=household_profile_with_ages([30, 31]),
        claims=claims_with_net_worths({1: 50.0, 2: 50.0}, income_emas={1: 5.0, 2: 5.0}),
        rates=Phase0VitalRates(),
        alpha_income=0.6,
        alpha_wealth_draw=1.0,
    )
    old_budget = household_lifecycle_consumption_budget(
        profile=household_profile_with_ages([72, 73]),
        claims=claims_with_net_worths({1: 50.0, 2: 50.0}, income_emas={1: 5.0, 2: 5.0}),
        rates=Phase0VitalRates(),
        alpha_income=0.6,
        alpha_wealth_draw=1.0,
    )

    assert old_budget > young_budget
```

```python
def test_household_lifecycle_budget_sums_person_wealth_draws_not_average_life():
    mixed_age_budget = household_lifecycle_consumption_budget(
        profile=household_profile_with_ages([30, 80]),
        claims=claims_with_net_worths({1: 50.0, 2: 50.0}, income_emas={1: 5.0, 2: 0.0}),
        rates=Phase0VitalRates(),
        alpha_income=0.6,
        alpha_wealth_draw=1.0,
    )
    young_budget = household_lifecycle_consumption_budget(
        profile=household_profile_with_ages([30, 30]),
        claims=claims_with_net_worths({1: 50.0, 2: 50.0}, income_emas={1: 5.0, 2: 5.0}),
        rates=Phase0VitalRates(),
        alpha_income=0.6,
        alpha_wealth_draw=1.0,
    )

    assert mixed_age_budget > young_budget
```

- [ ] **Step 2: Implement household rule**

Formula:

```text
person_permanent_income_i = income_ema_i * age_income_capacity(age_i)
person_wealth_draw_i = max(net_worth_i, 0) / max(expected_remaining_life_years(age_i) * ticks_per_year, 1)
income_budget = alpha_income * sum_i(person_permanent_income_i)
wealth_draw_budget = alpha_wealth_draw * sum_i(person_wealth_draw_i)
need_scale = household need units / adult-equivalent baseline
budget = max(0, need_scale * income_budget + wealth_draw_budget)
```

Do not compute `net_worth_household / e_bar_household` in the first version. The household rule must sum person-level wealth draws so that two people with the same household wealth but different ages produce different wealth-consumption flows through their own remaining lifetimes.

Do not include an explicit age-saving-rate target, target age-wealth profile, or target aggregate saving rate.

- [ ] **Step 3: Connect to planning behind a switch**

When demographics lifecycle consumption is enabled, use this budget for `h.consumption_budget`. When disabled, keep existing `B.plan_consumption`.

- [ ] **Step 4: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_lifecycle_consumption.py
```

Expected: pass.

### Task 12: Post realized household consumption to person claims

**Files:**
- Modify: `macro_sim/demographics/economic_bridge.py`
- Modify: `macro_sim/systems/goods.py`
- Test: `tests/test_demographic_lifecycle_consumption.py`

**Interfaces:**
- Produces:
  - `DemographicEconomicBridge.post_household_consumption(account_id: str, spent: float, fixed_share: float = 0.30) -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_consumption_posting_preserves_household_cash_claim_sum():
    bridge = bridge_with_household_cash_claims(account_id="H0", person_cash={1: 100.0, 2: 100.0, 3: 0.0})

    bridge.post_household_consumption("H0", spent=60.0, fixed_share=0.30)

    assert bridge.claim_cash_sum("H0") == pytest.approx(140.0)
    assert bridge.consumption_allocated_sum("H0") == pytest.approx(60.0)
```

- [ ] **Step 2: Implement posting**

Rules:

```text
fixed component: 30% of spending, charged equally to adult household owners
variable component: 70% of spending, allocated by need weights
child variable component: charged to living parents in Phase 1.7; before then, charged to household adult owners
```

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_lifecycle_consumption.py
```

Expected: pass.

---

## Phase 1.4: Death-Derived Inheritance

### Task 13: Implement default inheritance from estate suspense

**Files:**
- Create: `macro_sim/demographics/inheritance.py`
- Modify: `macro_sim/demographics/estate.py`
- Test: `tests/test_demographic_inheritance.py`

**Interfaces:**
- Produces:
  - `HeirDistribution`
  - `select_default_heirs(dead_person, people_by_id) -> HeirDistribution`
  - `settle_estate(estate, heirs, claims, inheritance_tax_rate: float = 0.0) -> None`

- [ ] **Step 1: Write failing tests**

```python
def test_estate_transfers_to_spouse_and_children_without_changing_total_private_wealth():
    before = claims.total_net_worth(include_estates=True)

    settle_estate(estate, heirs=HeirDistribution(spouse_id=2, child_ids=[3, 4]), claims=claims)

    assert claims.net_worth(1) == 0.0
    assert claims.net_worth(2) == pytest.approx(50.0)
    assert claims.net_worth(3) == pytest.approx(25.0)
    assert claims.net_worth(4) == pytest.approx(25.0)
    assert claims.total_net_worth(include_estates=True) == pytest.approx(before)
```

- [ ] **Step 2: Implement default rule**

Default:

```text
living spouse receives 50%
living children split 50%
if no spouse and children exist: children split 100%
if no spouse and no children: living parents split 100%
if no heirs: transfer to public estate account as escheat transfer, not tax revenue
inheritance_tax_rate default is 0
```

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_inheritance.py
```

Expected: pass.

### Task 14: Apply marriage dissolution before estate creation

**Files:**
- Create: `macro_sim/demographics/marriage_economics.py`
- Modify: `macro_sim/demographics/economic_bridge.py`
- Test: `tests/test_demographic_marriage_economics.py`

**Interfaces:**
- Produces:
  - `MarriageContract`
  - `record_marriage_contract(event, claims) -> MarriageContract`
  - `dissolve_marriage(contract, claims, reason: Literal["divorce", "death"]) -> DissolutionResult`

- [ ] **Step 1: Write failing tests**

```python
def test_marriage_records_basis_without_equalizing_claims():
    contract = record_marriage_contract(event, claims)

    assert contract.basis_by_person[1] == 100.0
    assert contract.basis_by_person[2] == 20.0
    assert claims.net_worth(1) == 100.0
    assert claims.net_worth(2) == 20.0
```

```python
def test_death_settles_community_property_before_estate_creation():
    # A basis=100 current=200; B basis=20 current=40.
    # Marital gains are 100 and 20; each target gain is 60.
    bridge.on_death(death_event_for_a, dead_spouse_a)

    assert bridge.claims.net_worth(2) == pytest.approx(80.0)
    assert bridge.estates.estate_for(1).net_worth == pytest.approx(160.0)
```

- [ ] **Step 2: Implement community-property settlement**

Rules:

```text
marital_gain_i = current_net_worth_i - marriage_basis_i
marital_pool = marital_gain_a + marital_gain_b
target_i = marriage_basis_i + marital_pool / 2
redistribution occurs through person-claim transfers only
aggregate person net worth is unchanged
```

Allow negative marital gains; marital losses are split as well.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_marriage_economics.py tests/test_demographic_inheritance.py
```

Expected: pass.

---

## Cross-Cutting Module A: Adult Leaving Home and Dynamic Households

### Task 15: Add adult child leaving-home dynamics

**Files:**
- Create: `macro_sim/demographics/lifecycle_households.py`
- Modify: `macro_sim/demographics/kernel.py`
- Modify: `macro_sim/demographics/economic_bridge.py`
- Test: `tests/test_demographic_lifecycle_households.py`

**Interfaces:**
- Produces:
  - `LifecycleHouseholdConfig`
  - `apply_leaving_home_dynamics(state, config, rng) -> list[LeavingHomeEvent]`
  - `DemographicEconomicBridge.create_household_for_person(person_id: int) -> str`

- [ ] **Step 1: Write failing tests**

```python
def test_adult_child_leaves_home_and_keeps_parent_links():
    child = adult_child(age=23, household_id=0, mother_id=1, father_id=2)

    events = apply_leaving_home_dynamics(
        state,
        config=LifecycleHouseholdConfig(annual_leave_rate_peak=365.0),
        rng=rng,
    )

    assert events
    assert child.household_id != 0
    assert child.mother_id == 1
    assert child.father_id == 2
```

- [ ] **Step 2: Implement default leaving-home rule**

Default:

```text
eligible: alive, age >= 22, no partner, lives with at least one parent
annual hazard: 0.25 for ages 22-30
annual hazard: 0.05 after age 30 if still in parental household
result: new scale-1 household account and same parent links
```

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_lifecycle_households.py
```

Expected: pass.

---

## Cross-Cutting Module B: Children, Guardianship Costs, and Public Support

### Task 16: Allocate child costs to living parents or public support

**Files:**
- Modify: `macro_sim/demographics/economic_bridge.py`
- Modify: `macro_sim/systems/goods.py`
- Test: `tests/test_demographic_lifecycle_consumption.py`

**Interfaces:**
- Produces:
  - `DemographicEconomicBridge.allocate_child_cost(child_id: int, amount: float) -> ChildCostAllocation`

- [ ] **Step 1: Write failing tests**

```python
def test_child_costs_split_between_living_parents():
    allocation = bridge.allocate_child_cost(child_id=3, amount=30.0)

    assert allocation.parent_charges == {1: 15.0, 2: 15.0}
    assert allocation.public_charge == 0.0
```

```python
def test_orphan_child_costs_go_to_public_support():
    allocation = bridge.allocate_child_cost(child_id=3, amount=30.0)

    assert allocation.parent_charges == {}
    assert allocation.public_charge == 30.0
```

- [ ] **Step 2: Implement allocation rule**

Rule:

```text
one or more living parents: living parents pay equally
no living parents: public guardian pays
```

Public support must be visible as fiscal support spending in metrics. It is not hidden household income.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_lifecycle_consumption.py
```

Expected: pass.

---

## Cross-Cutting Module C: Metrics and Integrated Smoke Runs

### Task 17: Add Phase 1 person-level metrics

**Files:**
- Modify: `macro_sim/reporting/metrics.py`
- Test: `tests/test_demographic_economic_bridge.py`

**Metrics:**

```text
demographics_enabled
person_population_alive
person_labor_supply
person_employment_rate
person_unemployment_rate
dependency_ratio
child_dependency_ratio
elder_dependency_ratio
person_income_gini
person_consumption_gini
person_wealth_gini
adult_median_consumption
child_median_consumption
elder_median_consumption
estate_suspense_total
inheritance_flow
public_guardian_children
orphan_support_spending
```

- [ ] **Step 1: Write failing tests**

Use a synthetic `PersonClaimLedger` with known income, consumption, and wealth values. Assert exact aggregate metrics and Gini values within tolerance.

- [ ] **Step 2: Implement metric extraction**

When demographics are disabled, emit `demographics_enabled=False` and omit Phase 1 person metrics from the record.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest -q tests/test_demographic_economic_bridge.py
```

Expected: pass.

### Task 18: Wire an integrated demographic-economy smoke run

**Files:**
- Modify: `macro_sim/economy.py`
- Test: `tests/test_demographic_economy_integration.py`

**Interfaces:**
- Produces:
  - config switch `demographics_enabled`
  - `Economy.demographic_state`
  - `Economy.demographic_bridge`

- [ ] **Step 1: Write failing smoke tests**

```python
def test_demographic_economy_smoke_run_preserves_claim_identities():
    econ = Economy(config_with_demographics_enabled)

    for _ in range(30):
        econ.step()
        econ.demographic_bridge.assert_all_claim_identities(econ)
```

```python
def test_demographics_disabled_smoke_run_still_steps():
    econ = Economy(config_with_demographics_disabled)

    for _ in range(30):
        econ.step()
```

- [ ] **Step 2: Hook daily demographic tick into economic tick**

Use one calendar day per economic tick under the current time-calibration plan. Demographic events that change household composition fire before economic planning for that tick.

- [ ] **Step 3: Verify focused integration**

Run:

```bash
uv run pytest -q tests/test_demographic_economy_integration.py
```

Expected: pass.

### Task 19: Run the Phase 1 gate suite

**Files:**
- Test-only task.

- [ ] **Step 1: Run focused Phase 0 + Phase 1 suite in parallel**

Run:

```bash
uv run pytest -q -n auto \
  tests/test_demographic_phase0_kernel.py \
  tests/test_demographic_phase0_relationships.py \
  tests/test_demographic_phase0_calendar.py \
  tests/test_demographic_phase0_social_dynamics.py \
  tests/test_demographic_multistate_oracle.py \
  tests/test_demographic_marital_fertility.py \
  tests/test_demographic_union_profile.py \
  tests/test_demographic_phase0_validation.py \
  tests/test_demographic_economic_claims.py \
  tests/test_demographic_economic_bridge.py \
  tests/test_demographic_birth_death_economics.py \
  tests/test_demographic_labor_supply.py \
  tests/test_demographic_lifecycle_consumption.py \
  tests/test_demographic_marriage_economics.py \
  tests/test_demographic_lifecycle_households.py \
  tests/test_demographic_inheritance.py \
  tests/test_demographic_phase1_baseline_invariance.py \
  tests/test_demographic_economy_integration.py
```

Expected: all selected tests pass.

- [ ] **Step 2: Run a light simulation**

Run:

```bash
uv run python run.py --config configs/demographics_phase1_light.yaml
```

Expected:

```text
run completes
claim identities checked every tick
demographics_enabled=True appears in metrics
population trajectory matches Phase 0 baseline event counts for same seed
```

---

## Acceptance Gates

Phase 1 is accepted only if all gates pass:

- Population path gate: Phase 1 economic hooks do not change Phase 0 demographic events or alive-by-age paths for the same demographic seed.
- Claim identity gate: each live household account reconciles to person cash, debt, and security claims.
- Birth gate: every newborn has a zero-endowment person balance sheet and does not receive hidden parental transfers.
- Death gate: marital settlement runs before debt clearing and estate creation; positive net worth enters estate suspense or inheritance; negative net worth writes unpaid debt to the identified lending bank and records `death_writeoff_flow`; missing creditor identity halts.
- Labor gate: private labor supply and unemployment/JG residuals are based on working-age live people, not household count.
- Lifecycle gate: consumption behavior uses finite-life smoothing and age income capacity; no explicit age-saving-rate target is encoded.
- Marriage gate: marriage creates a snapshot and does not equalize wealth during marriage; divorce and death share the same community-property settlement core.
- Household gate: adult leaving-home events preserve parent links and create valid economic household accounts.
- Child-cost gate: children are always charged to living parents or visible public support.
- Inheritance gate: estate settlement uses transfers and conserves aggregate private wealth net of explicit taxes or public escheat transfers.
- Metrics gate: person-level labor, consumption, wealth, estate, inheritance, and dependency metrics are emitted when demographics are enabled.
- Regression gate: focused Phase 0 + Phase 1 suite passes in parallel.

## Self-Review Notes

- The plan now follows the four Phase 1 channels: 1.1 birth/death balance-sheet entry and clearing, 1.2 age-derived labor supply, 1.3 age-derived lifecycle consumption and asset demand, and 1.4 death-derived inheritance.
- Marriage economics is treated as a cross-cutting settlement institution for household control and inheritance, not as the main Phase 1 spine.
- The strongest new invariant is population-path invariance: Phase 1 economic hooks may change money and claims, but not demographic events.
- The largest modeling risk is Phase 1.3. The plan avoids hard-coding a Modigliani saving curve and instead uses finite-life annuitized consumption plus age-income capacity, then asks metrics to measure the emergent age-wealth profile.
