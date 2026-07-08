# Codebase Modularization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the simulator into high-cohesion, low-coupling modules while preserving existing economic behavior and version regressions.

**Architecture:** Use an incremental strangler refactor. Keep the current root-level public API stable first, introduce a `macro_sim/` package behind compatibility wrappers, then extract systems from `Economy` one bounded mechanism at a time. The tick phase order remains the behavioral spine until every extracted subsystem has regression coverage.

**Tech Stack:** Python 3.12, dataclasses, pytest, numpy, matplotlib; no new runtime dependency in the first refactor wave.

## Global Constraints

- Preserve old public entry points during the transition: `from economy import Economy`, `from config import Config`, `from ledger import Ledger`, etc. must continue to work until callers are migrated intentionally.
- Preserve the hard accounting gates: deposit/loan/securities invariant `sum(deposits) - sum(loans) - bank_securities = M`; reserve invariant `sum(reserves) = reserve_M`.
- Preserve feature-flag discipline: old configs should remain bit-identical unless a change is explicitly marked as a correctness fix.
- Do not start by changing economic mechanisms. First refactor imports, boundaries, and orchestration.
- Treat the existing tests under `tests/` as the primary safety net; add golden regression tests before extracting behavior from `Economy`.
- Keep archived scripts under `archive/` out of the active command surface.
- Keep documentation updates small and local: update `docs/design/current/module-map.md` only after a package boundary actually exists.

---

## Current Module Diagnosis

| File | Current role | Refactor diagnosis |
|---|---|---|
| `economy.py` | World construction, tick scheduler, and all major mechanisms. | Main god object. Keep as facade first, then extract systems. |
| `config.py` | Parameter table, validation, version presets, historical notes. | Useful content, overloaded responsibility. Split after system boundaries stabilize. |
| `ledger.py` | Deposits, loans, reserves, bank securities, hard gates. | Keep cohesive as accounting kernel; move policy/strategy logic out, not invariants. |
| `agents.py` | Household, Firm, Bank, EquityMarket state. | Move to domain package. Later split large `Firm` state by composition. |
| `behavior.py` | Planning equations and decision helpers. | Good pure-ish boundary. Split by behavior area after packaging. |
| `interfaces.py` | Market orders/offers/trades and matching protocols. | Good extraction candidate. Move early to `markets/`. |
| `metrics.py` | Large per-tick observer, reads private `Economy` state. | Later replace with subsystem metric collectors. |
| `diagnostics.py` | Plotting and seed invariance helpers. | Move to reporting after package exists. |
| `runlog.py` | Experiment registry and sweep logging. | Move to experiments after package exists. |
| `policy.py` | Mutable policy levers. | Already cohesive; move early. |
| `run.py` | Minimal ad-hoc entrypoint. | Keep thin; later replace with real CLI. |

## Target Package Shape

```text
macro_sim/
  __init__.py
  economy.py
  config/
    __init__.py
    model.py
    loader.py
    schema.py
  core/
    __init__.py
    ledger.py
    scheduler.py
    state.py
  domain/
    __init__.py
    agents.py
  behavior/
    __init__.py
    planning.py
  markets/
    __init__.py
    matching.py
    goods.py
    capital_goods.py
    labor.py
  systems/
    __init__.py
    planning.py
    credit.py
    settlement.py
    firm_demographics.py
    equity.py
    banking.py
    securities.py
    fiscal.py
    central_bank.py
  reporting/
    __init__.py
    metrics.py
    diagnostics.py
  experiments/
    __init__.py
    runlog.py
```

Root-level modules stay temporarily as compatibility wrappers:

```python
from macro_sim.core.ledger import *
```

Use explicit wrapper files only during migration. Remove them in a later cleanup after tests and user workflows import from `macro_sim`.

## Phase 0: Freeze A Behavioral Baseline

**Files:**
- Create: `tests/test_refactor_golden_baseline.py`
- No production-code changes.

**Interfaces:**
- Consumes: existing `Config` factories and `Economy.run()`.
- Produces: a small deterministic baseline that later refactors must preserve.

- [ ] Add a helper that runs short deterministic configs and returns stable tail records.

```python
from config import Config
from economy import Economy


def _tail_signature(cfg):
    records = Economy(cfg).run()
    last = records[-1]
    keys = (
        "total_money",
        "conservation_drift",
        "real_output",
        "price_index",
        "unemployment_rate",
    )
    return {k: round(float(last.get(k, 0.0)), 8) for k in keys}
```

- [ ] Add golden tests for representative frontiers.

```python
def test_baseline_v1_signature_is_deterministic():
    cfg = Config(n_ticks=120, seed=0)
    assert _tail_signature(cfg) == _tail_signature(cfg)


def test_baseline_v12_signature_is_deterministic():
    cfg = Config.v124(n_firms_c=20, n_firms_k=10, n_households=200, n_ticks=120, seed=0)
    assert _tail_signature(cfg) == _tail_signature(cfg)
```

- [ ] Run the focused test.

```bash
uv run pytest tests/test_refactor_golden_baseline.py -q
```

- [ ] Run the full suite before any package move.

```bash
uv run pytest -q
```

- [ ] Commit the baseline test separately.

```bash
git add tests/test_refactor_golden_baseline.py
git commit -m "test: add refactor baseline signatures"
```

## Phase 1: Introduce The Package Without Moving Behavior

**Files:**
- Create: `macro_sim/__init__.py`
- Create: `macro_sim/core/__init__.py`
- Create: `macro_sim/domain/__init__.py`
- Create: `macro_sim/behavior/__init__.py`
- Create: `macro_sim/markets/__init__.py`
- Create: `macro_sim/systems/__init__.py`
- Create: `macro_sim/reporting/__init__.py`
- Create: `macro_sim/experiments/__init__.py`
- Create: `tests/test_package_imports.py`

**Interfaces:**
- Consumes: no model internals.
- Produces: stable package namespace for later moves.

- [ ] Create empty package directories with `__init__.py`.

- [ ] Add import smoke tests.

```python
def test_package_namespace_imports():
    import macro_sim
    import macro_sim.core
    import macro_sim.domain
    import macro_sim.behavior
    import macro_sim.markets
    import macro_sim.systems
    import macro_sim.reporting
    import macro_sim.experiments

    assert macro_sim is not None
```

- [ ] Run smoke and full tests.

```bash
uv run pytest tests/test_package_imports.py -q
uv run pytest -q
```

- [ ] Commit package skeleton separately.

```bash
git add macro_sim tests/test_package_imports.py
git commit -m "refactor: add macro_sim package skeleton"
```

## Phase 2: Move Low-Risk Cohesive Modules Behind Wrappers

**Files:**
- Move: `ledger.py` -> `macro_sim/core/ledger.py`
- Move: `agents.py` -> `macro_sim/domain/agents.py`
- Move: `behavior.py` -> `macro_sim/behavior/planning.py`
- Move: `interfaces.py` -> `macro_sim/markets/matching.py`
- Move: `policy.py` -> `macro_sim/core/policy.py`
- Modify root wrappers: `ledger.py`, `agents.py`, `behavior.py`, `interfaces.py`, `policy.py`
- Modify imports inside moved files to package-relative imports.
- Test: `tests/test_package_imports.py`, existing full suite.

**Interfaces:**
- Consumes: existing root imports from tests and scripts.
- Produces: both old and new import paths.

- [ ] Move one module at a time, starting with `ledger.py`.

- [ ] Replace each root file with a compatibility wrapper.

```python
from macro_sim.core.ledger import *
```

- [ ] After moving `agents.py`, update package imports inside the moved module.

```python
from macro_sim.config.model import Config
```

Use this package import only after `config.py` has been moved or wrappered. Until then, keep the wrapper-compatible root import to minimize blast radius.

- [ ] After moving `interfaces.py`, remove the unreachable line in `PreferentialMatch.seller_order()` where `self.name = "random"` appears after `return live`.

- [ ] Add explicit new-path import tests.

```python
def test_new_core_imports():
    from macro_sim.core.ledger import Ledger
    from macro_sim.domain.agents import Household, Firm, Bank
    from macro_sim.behavior.planning import plan_consumption
    from macro_sim.markets.matching import execute_market

    assert Ledger and Household and Firm and Bank and plan_consumption and execute_market
```

- [ ] Run targeted tests after each moved module.

```bash
uv run pytest tests/test_conservation.py tests/test_credit_primitives.py -q
uv run pytest tests/test_behavior_v2.py tests/test_v2_capital.py -q
uv run pytest -q
```

- [ ] Commit each move or small group separately.

```bash
git add -A
git commit -m "refactor: move accounting and domain modules into package"
```

## Phase 3: Move Config Into The Package

**Files:**
- Move: `config.py` -> `macro_sim/config/model.py`
- Create: `macro_sim/config/__init__.py`
- Modify root wrapper: `config.py`
- Test: full suite.

**Interfaces:**
- Consumes: `Config` dataclass and all current version factories.
- Produces: `macro_sim.config.Config`.

- [ ] Move the current monolithic config unchanged to `macro_sim/config/model.py`.

- [ ] Export it from `macro_sim/config/__init__.py`.

```python
from macro_sim.config.model import Config

__all__ = ["Config"]
```

- [ ] Replace root `config.py` with:

```python
from macro_sim.config.model import *
```

- [ ] Update moved package modules to import `Config` from `macro_sim.config`.

- [x] Run full tests.

```bash
uv run pytest -q
```

- [ ] Commit the config move separately.

```bash
git add -A
git commit -m "refactor: move legacy config into package"
```

## Phase 4: Move Reporting And Experiment Helpers

**Files:**
- Move: `metrics.py` -> `macro_sim/reporting/metrics.py`
- Move: `diagnostics.py` -> `macro_sim/reporting/diagnostics.py`
- Move: `runlog.py` -> `macro_sim/experiments/runlog.py`
- Modify root wrappers: `metrics.py`, `diagnostics.py`, `runlog.py`
- Modify imports in `run.py` only if needed.
- Test: full suite plus one lightweight runlog smoke test if runtime is acceptable.

**Interfaces:**
- Consumes: existing metrics record dicts and `RunLogger`.
- Produces: package paths while preserving root imports.

- [ ] Move `metrics.py` unchanged first.

- [ ] Replace root `metrics.py` with:

```python
from macro_sim.reporting.metrics import *
```

- [ ] Move `diagnostics.py` and `runlog.py` after metrics.

- [ ] Replace root wrappers.

```python
from macro_sim.reporting.diagnostics import *
```

```python
from macro_sim.experiments.runlog import *
```

- [x] Run full tests.

```bash
uv run pytest -q
```

- [ ] Commit reporting and experiment moves separately.

```bash
git add -A
git commit -m "refactor: move reporting and experiment helpers into package"
```

## Phase 5: Move Economy Behind A Facade

**Files:**
- Move: `economy.py` -> `macro_sim/economy.py`
- Modify root wrapper: `economy.py`
- Test: full suite.

**Interfaces:**
- Consumes: existing `Economy` constructor and `Economy.run()`.
- Produces: `macro_sim.economy.Economy` while preserving root `Economy`.

- [ ] Move `economy.py` unchanged first.

- [ ] Replace root `economy.py` with:

```python
from macro_sim.economy import *
```

- [ ] Update package-internal imports in `macro_sim/economy.py` to use package paths.

```python
from macro_sim.config import Config
from macro_sim.core.ledger import Ledger
from macro_sim.core.policy import Policy
from macro_sim.domain.agents import Bank, EquityMarket, Firm, Household
from macro_sim.markets.matching import (
    EPS,
    BuyOrder,
    Goods,
    MatchingProtocol,
    PreferentialMatch,
    RandomMatch,
    SampledCompareMatch,
    SellOffer,
    execute_market,
)
from macro_sim.behavior import planning as B
from macro_sim.reporting import metrics
```

- [ ] Run package import and full tests.

```bash
uv run pytest tests/test_package_imports.py -q
uv run pytest -q
```

- [ ] Commit the economy facade move separately.

```bash
git add -A
git commit -m "refactor: move economy facade into package"
```

## Phase 6: Introduce Simulation State Without Extracting Systems

**Files:**
- Create: `macro_sim/core/state.py`
- Modify: `macro_sim/economy.py`
- Test: full suite.

**Interfaces:**
- Consumes: current `Economy` attributes.
- Produces: a `SimulationState` dataclass that can gradually absorb public state.

- [x] Add a minimal state dataclass.

```python
from dataclasses import dataclass, field
from random import Random
from typing import Any


@dataclass
class SimulationState:
    cfg: Any
    policy: Any
    rng: Random
    ledger: Any
    households: list
    firms: list
    c_firms: list
    k_firms: list
    banks: list
    records: list = field(default_factory=list)
```

- [x] Construct `SimulationState` at the end of `Economy.__init__` while keeping the old attributes.

```python
self.state = SimulationState(
    cfg=self.cfg,
    policy=self.policy,
    rng=self.rng,
    ledger=self.ledger,
    households=self.households,
    firms=self.firms,
    c_firms=self.c_firms,
    k_firms=self.k_firms,
    banks=self.banks,
    records=self.records,
)
```

- [x] Do not rewrite phase methods to use `state` yet. This phase only creates a stable carrier for future systems.

- [ ] Run full tests.

```bash
uv run pytest -q
```

- [ ] Commit state introduction separately.

```bash
git add -A
git commit -m "refactor: introduce simulation state carrier"
```

## Phase 7: Extract Economy Systems One At A Time

**Files:**
- Create under `macro_sim/systems/` as mechanisms are extracted.
- Modify: `Economy.step()` only to delegate phase bodies.
- Test: for large batches, run one unified parallel regression after the batch lands.

**Extraction order:**

1. `planning.py`: `_phase1_plan`
2. `labor.py`: `_phase2_labor`
3. `goods.py`: `_phase3_goods`
4. `capital_goods.py`: `_phase3_5_capital`
5. `settlement.py`: `_phase4_settlement`, `_gov_household_fiscal`
6. `credit.py`: `_phase1_5_credit`, `_phase4_5_debt_service`
7. `firm_demographics.py`: `_phase4_7_demographics`, `_bankrupt`, `_entry_c_firms`, `_birth_c_firm`
8. `equity.py`: `_phase4_9_equity`, `_phase4_9_equity_per_firm`
9. `banking.py`: bank assignment, shopping, failure, runs, bank equity
10. `securities.py`: bonds, bill maturity/issuance, bond valuation, securities identities
11. `central_bank.py`: `_cb_set_rate`, `_phase_omo`

Current progress: `planning.py`, `labor.py`, `goods.py`, `capital_goods.py`, `settlement.py`,
`credit.py`, `firm_demographics.py`, `equity.py`, `banking.py`, `securities.py`, and
`central_bank.py` have been extracted as thin orchestration functions. Several deeper helper
methods still live on `Economy` intentionally (`_bankrupt`, `_entry_c_firms`, bank founding/failure
helpers, bond valuation/index helpers, and loan-book helpers); those are the next refinement layer
after behavior-preserving phase extraction.

**Interfaces:**
- Each system consumes `SimulationState` plus the existing `Economy` facade only where unavoidable.
- Each system produces the same side effects as the original phase method.

- [x] For the completed extractions, copy the body first and delegate from the old method.

```python
def _phase2_labor(self) -> None:
    self.labor_system.run_private_labor_market(self.state)
```

- [x] Keep the old method name until tests and external callers stop depending on it.

- [x] Add focused tests for the extracted system entry points.

- [x] Run relevant focused tests and then the full suite for the first wave.

- [x] Run one unified parallel regression for the batched second wave.

```bash
uv run pytest tests/test_v2_capital.py tests/test_v3_credit.py -q
uv run pytest -n auto -q
```

- [ ] Commit extracted systems in a clean history once the current batch stabilizes.

```bash
git add -A
git commit -m "refactor: extract labor market system"
```

## Phase 7.5: Turn Thin Systems Into Real Boundaries

**Files:**
- Modify: `macro_sim/economy.py`
- Modify: selected `macro_sim/systems/*.py`
- Modify: focused tests that still call private phase methods.
- Test: focused structural tests first, then one unified parallel regression.

**Goal:**
Phase 7 made the module files exist. Phase 7.5 removes the temporary coupling that would otherwise make
those modules cosmetic: thin `_phase...` wrappers should disappear, `step()` should call extracted systems
directly, and helper clusters should move behind their owning system modules.

**Scope for the first 7.5 pass:**

1. Collapse phase wrappers whose only body is a call to an extracted function:
   `_cb_set_rate`, `_deposit_competition`, `_phase_omo`, `_phase_bill_maturity`,
   `_phase1_plan`, `_phase1_5_credit`, `_phase2_labor`, `_phase3_goods`,
   `_phase3_5_capital`, `_phase4_settlement`, `_gov_household_fiscal`,
   `_phase4_5_debt_service`, `_phase4_7_demographics`, `_phase4_9_equity`,
   `_phase4_9_equity_per_firm`, `_phase_interbank`, `_phase_bank_runs`,
   `_resolve_bank_failures`, `_entry_banks`, and `_phase_bill_issuance`.
2. Extract the firm-demographics helper cluster:
   `_bankrupt`, `_entry_c_firms`, `_startup_cash`, `_pick_funder`, `_birth_c_firm`.
3. Extract the securities helper cluster:
   `_bond_price`, `_bond_market_value`, `_reindex_bonds`, `_hh_bond_value`,
   `_redeem_hh_bonds`.
4. Keep the banking/credit deep helper cluster for a later pass because it is shared across credit,
   runs, failure resolution, loan shopping, bank entry, and securities capital marking.

**Completion criteria:**

- [x] `Economy.step()` directly calls extracted system functions in the existing tick order.
- [x] Active tests no longer call private phase wrappers.
- [x] `Economy.__dict__` no longer defines the collapsed phase wrapper names.
- [x] `firm_demographics.py` owns the firm entry/bankruptcy helpers it uses.
- [x] `securities.py` owns bond valuation, bond indexing, household bond valuation, and household bond redemption.
- [x] One focused structural test run passes.
- [x] One full parallel regression passes.

```bash
uv run pytest tests/test_package_imports.py tests/test_v10_central_bank.py::test_taylor_rule_responds_to_inflation tests/test_v101_deposit_interest.py::test_interest_goes_to_depositors tests/test_v12_bonds.py::test_svb_duration_channel_and_bank_securities_conserve -q
uv run pytest -n auto -q
```

**Remaining 7.5 rounds:**

**Batch verification policy:** 7.5b-2, 7.5b-3, and 7.5b-4 are executed as one
batch. Run only lightweight structural/import checks during the batch; run the
banking-focused regression set and one full parallel regression after all three
rounds are complete.

7.5b-1 **Bank routing and loan-book primitives** (first, lowest risk):

- [x] Move `_assign_banks_genesis`, `_bank_for`, `_bank_constraint`, `_refresh_loan_books`,
  `_reserve_position`, `_rate_competition`, and `_loan_rate_for` into `systems/banking.py`.
- [x] Update active systems and metrics to call these module functions.
- [x] Leave `_grant_loan`, `_shop_bank`, `_bank_capacity`, and `_bank_economic_capital` in `Economy`
  for the next banking/credit pass.
- [x] Run focused structural tests and banking/credit tests.
- [x] Run full parallel regression.

7.5b-2 **Credit supply and borrower shopping**:

- [x] Move `_grant_loan`, `_shop_bank`, `_bank_capacity`, `_bank_economic_capital`, and related
  exposure-limit logic behind `systems/credit.py` / `systems/banking.py` with one clear ownership
  decision.
- [x] Update `credit.py`, `securities.py`, and `metrics.py` to stop calling those `Economy` helpers.
- [x] Preserve the exact leverage-cap and large-exposure behavior.

7.5b-3 **Bank equity, dividends, and entry**:

- [x] Move `_setup_bank_equity`, `_pay_bank_dividends`, `_bank_fundamental`,
  `_update_bank_valuation`, `_bank_stock_market`, `_bank_equity_value`, `_find_bank_founder`,
  and `_found_bank` into `systems/banking.py`.
- [x] Keep bank ownership/share-price semantics and genesis founder assignment bit-identical.

7.5b-4 **Bank failure, reserve routing, and settlement identity**:

- [x] Move `_fail_bank`, `_enable_reserves`, `_settlement_node`, and the remaining reserve/failure
  plumbing into `systems/banking.py` or a small `systems/reserves.py` if the boundary is cleaner.
- [x] This is last because ledger reserve callbacks and failure contagion are the riskiest accounting
  surface.
- [x] Run lightweight structural/import checks during the batch.
- [x] Run focused banking/security regression set for the full batch.
- [x] Run one full parallel regression for the full batch.

## Phase 7.6: Close Remaining Economy Helper Clusters

**Files:**
- Modify: `macro_sim/economy.py`
- Modify: `macro_sim/behavior/planning.py`
- Modify: `macro_sim/systems/banking.py`
- Modify: `macro_sim/systems/equity.py`
- Modify: `macro_sim/systems/firm_demographics.py`
- Modify: `macro_sim/systems/securities.py`
- Modify: `tests/test_package_imports.py`
- Test: lightweight structural checks, focused regression, then one full parallel regression.

**Goal:**
After Phase 7.5, `Economy` should be close to a facade: world construction,
tick scheduling, accounting/recording, and cross-tick lifecycle glue. Move the
remaining mechanism helpers to their owning modules before starting config and
metrics refactors.

- [x] Move `_diversify_mpc` into `behavior/planning.py`.
- [x] Move `_draw_bank_kappas`, `_draw_bank_spreads`, and `_draw_deposit_spreads`
  into `systems/banking.py`.
- [x] Move `_assert_securities_identities` into `systems/securities.py`.
- [x] Move `_setup_per_firm_equity` into `systems/equity.py`.
- [x] Move `_gibrat_shock` into `systems/firm_demographics.py`.
- [x] Keep `_phase5_check_and_record` and `_commit_cross_tick_state` in `Economy`
  for now; they are tick lifecycle glue, not economic mechanisms.
- [x] Run lightweight structural/import checks.
- [x] Run focused regression for the touched mechanism areas.
- [x] Run one full parallel regression.

## Phase 8: Split Config After System Boundaries Exist

**Files:**
- Create: `macro_sim/config/schema.py`
- Create: `macro_sim/config/presets.py`
- Modify: `macro_sim/config/model.py`
- Test: lightweight structural checks and parallel focused checks per config group; one full parallel regression after Phase 8 is complete.

**Interfaces:**
- Consumes: current `Config.v*()` factories.
- Produces: grouped config structures while preserving `Config.v124(...)`.

- [x] Start with passive nested dataclasses without changing call sites.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class BankingConfig:
    bank_enabled: bool
    n_banks: int
    bank_target_capital_ratio: float
    bank_exposure_limit: float
```

- [x] Add conversion properties on legacy `Config`.

```python
@property
def banking(self) -> BankingConfig:
    return BankingConfig(
        bank_enabled=self.bank_enabled,
        n_banks=self.n_banks,
        bank_target_capital_ratio=self.bank_target_capital_ratio,
        bank_exposure_limit=self.bank_exposure_limit,
    )
```

- [x] Migrate one system at a time to read grouped config, starting with the extracted system that has the fewest config fields.

- [x] Add `CentralBankConfig` / `Config.central_banking` as the first low-risk grouped config view.

- [x] Migrate `systems/central_bank.py` to read `econ.cfg.central_banking`.

- [x] During each config-group migration, run only lightweight structural checks and parallel focused checks.

- [x] Run focused central-bank regression for the `CentralBankConfig` migration.

- [x] Re-run focused central-bank regression in parallel (`-n auto`) before moving to the next config group.

- [x] Add `CapitalGoodsConfig` / `Config.capital_goods` and migrate `systems/capital_goods.py`.

- [x] Run parallel focused regression for the `CapitalGoodsConfig` migration.

- [x] Add `GoodsConfig` / `Config.goods` and migrate `systems/goods.py`.

- [x] Run parallel focused regression for the `GoodsConfig` migration.

- [x] Add `SettlementConfig` / `Config.settlement` and migrate `systems/settlement.py`.

- [x] Run parallel focused regression for the `SettlementConfig` migration.

- [x] Add `PlanningConfig` / `Config.planning` and migrate `systems/planning.py`.

- [x] Run parallel focused regression for the `PlanningConfig` migration.

- [x] Add `SecuritiesConfig` / `Config.securities` and migrate `systems/securities.py`.

- [x] Run parallel focused regression for the `SecuritiesConfig` migration.

- [x] Add `FirmDemographicsConfig` / `Config.firm_demographics` and migrate `systems/firm_demographics.py`.

- [x] Run parallel focused regression for the `FirmDemographicsConfig` migration.

- [x] Add `CreditConfig` / `Config.credit` and migrate `systems/credit.py`.

- [x] Run parallel focused regression for the `CreditConfig` migration.

- [x] Add `EquityConfig` / `Config.equity_market` and migrate `systems/equity.py`.

- [x] Run parallel focused regression for the `EquityConfig` migration.

- [x] Expand `BankingConfig` / `Config.banking` and migrate `systems/banking.py`.

- [x] Run parallel focused regression for the expanded `BankingConfig` migration.

- [x] Run one full parallel regression after all Phase 8 config groups are migrated.

```bash
uv run pytest -n auto -q
```

- [ ] Commit each config group migration separately.

```bash
git add -A
git commit -m "refactor: add grouped banking config view"
```

## Phase 9: Decouple Metrics From Private Economy State

**Files:**
- Create: `macro_sim/reporting/collectors.py`
- Modify: `macro_sim/reporting/metrics.py`
- Modify extracted systems to expose metric collectors.
- Test: full suite.

**Interfaces:**
- Consumes: `SimulationState` and per-system public snapshots.
- Produces: the same record keys as current `compute_tick_metrics(econ)`.

- [x] Add collector protocol.

```python
from typing import Protocol


class MetricCollector(Protocol):
    def collect_metrics(self, state) -> dict:
        ...
```

- [x] Move the whole-economy tick snapshot behind `EconomyMetricCollector` as the first collector boundary.

- [x] Preserve existing record keys exactly.

- [x] Run tests that assert key presence and full suite.

```bash
uv run pytest -q
```

- [ ] Commit each metric block separately.

```bash
git add -A
git commit -m "refactor: extract banking metric collector"
```

## Phase 10: Remove Transitional Compatibility Wrappers

**Files:**
- Delete root wrappers only after all active imports use `macro_sim.*`.
- Modify tests and `run.py` to import package paths.
- Test: full suite.

**Interfaces:**
- Consumes: package imports.
- Produces: clean package-only codebase.

- [x] Replace root imports in tests.

```python
from macro_sim.config import Config
from macro_sim.economy import Economy
```

- [x] Search for remaining root imports.

```bash
rg -n "from (config|economy|ledger|agents|behavior|interfaces|metrics|diagnostics|runlog|policy) import|import (config|economy|ledger|agents|behavior|interfaces|metrics|diagnostics|runlog|policy)" .
```

- [x] Delete wrappers after search confirms active code no longer uses them.

- [ ] Run full tests.

```bash
uv run pytest -q
```

- [ ] Commit wrapper removal separately.

```bash
git add -A
git commit -m "refactor: remove legacy root module wrappers"
```

## Verification Policy

Before any phase is considered complete, run:

```bash
uv run pytest -q
```

For package moves, additionally run:

```bash
python3 - <<'PY'
from config import Config
from economy import Economy
from ledger import Ledger
from macro_sim.config import Config as PackageConfig

assert Config is PackageConfig
assert Economy
assert Ledger
PY
```

For extracted systems, compare at least one old/new deterministic signature in the same commit. The preferred pattern is: add delegation, run full suite, then inspect that representative final records remain identical under the same seed.

## Recommended First Execution Slice

Start with Phases 0-2 only:

1. Add golden baseline tests.
2. Add the package skeleton.
3. Move `ledger.py`, `interfaces.py`, `policy.py`, `agents.py`, and `behavior.py` behind compatibility wrappers.

This slice gives immediate structure without touching `Economy` behavior. It also proves whether the current test suite is strong enough to protect the deeper extraction work.
