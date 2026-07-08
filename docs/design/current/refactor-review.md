# Refactor Review

This note reviews the package refactor after Phase 10. It is intentionally
short and development-facing: the goal is to identify what should be improved
next, not to retell the refactor history.

## Findings

### Important: `Config` is still the largest remaining god object

Code: `macro_sim/config/model.py`, `macro_sim/config/loader.py`, `macro_sim/config/schema.py`, `configs/`

`model.py` still owns defaults, validation, Python version factories, derived
flags, and grouped-view projection. The YAML loader and `configs/` profiles are
now the preferred path for run configuration, and the grouped dataclasses in
`schema.py` remain useful read boundaries for systems. The remaining risk is
that new model layers can still expand one giant parameter table unless the next
round moves presets and validation into smaller modules.

Recommended next step: split `model.py` into smaller files such as
`validation.py` and YAML-backed presets, then retire the Python `Config.v*()`
factories as tests and scripts move to `load_config_file(...)`.

### Important: `BankingConfig` is too broad

Code: `macro_sim/config/schema.py`, `macro_sim/systems/banking.py`

`BankingConfig` currently collects loan-book controls, rate competition,
deposit competition, reserve/interbank controls, bank equity, bank entry, bank
runs, and shared equity-demand knobs. This was acceptable as a migration step
because it removed scattered flat config reads, but it is not a final cohesive
boundary.

Recommended next step: split it into smaller views such as
`BankLoanConfig`, `InterbankConfig`, `BankEquityConfig`, and `BankRunConfig`.

### Important: `metrics.py` has a collector boundary, but not real collectors yet

Code: `macro_sim/reporting/collectors.py`, `macro_sim/reporting/metrics.py`

`collectors.py` creates the protocol and aggregation surface, but
`metrics.py` still contains one large whole-economy snapshot. This preserves
keys safely, but subsystem metrics remain coupled to private `Economy` state.

Recommended next step: move one metric block at a time into collectors owned by
the matching subsystem, starting with banking/securities because those blocks
already correspond to extracted systems.

### Moderate: `Economy` is a cleaner facade, but construction is still coupled

Code: `macro_sim/economy.py`

The tick loop now delegates phase work to systems, which is the right direction.
However, `Economy.__init__` still constructs households, firms, banks, fiscal
accounts, bonds, equity markets, RNG streams, and scratch state directly. This
keeps initialization order fragile.

Recommended next step: extract builders for genesis state, banking setup,
government/securities setup, and equity setup before changing economic
mechanisms.

### Moderate: Behavior helpers still accept broad config-like objects

Code: `macro_sim/behavior/planning.py`

Most systems now read grouped config views, but behavior helpers such as
`diversify_mpc()` and `plan_equity_demand()` still accept broad config-like
objects. They are pure enough, but their parameter contracts are implicit.

Recommended next step: introduce narrow behavior parameter dataclasses or pass
explicit scalar parameters where the helper only needs a few knobs.

## What Looks Good

- The root compatibility wrappers are gone; active imports now use package
  paths.
- Phase systems have clearer ownership than before the refactor.
- Accounting remains centralized in the ledger, not spread across agents.
- Config grouping is a good transitional boundary even though it should be
  split further.
- Tests now include package import smoke tests, config-view trap tests, and
  metric collector boundary tests.

## Suggested Next Slice

1. Split config presets and validation out of `model.py`.
2. Split `BankingConfig` into cohesive subviews.
3. Extract subsystem metric collectors from `metrics.py`.
4. Extract genesis/build setup from `Economy.__init__`.

Do these in that order. The first two reduce accidental coupling; the latter
two reduce file size and improve local reasoning.
