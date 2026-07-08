# v13 Phase 0 Validation Harness Implementation Plan

> **For agentic workers:** Use TDD. The harness must stay lightweight in pytest and leave expensive ensemble validation to the CLI.

**Goal:** Build a one-command Phase 0 validation harness that separates mortality, ungated fertility, multistate marital fertility, and two-sided matching checks.

**Architecture:** Add `macro_sim.demographics.validation` as a reporting/validation layer over the existing demographic kernel and oracles. It writes JSON/CSV artifacts, runs hard invariant checks in-process, and exposes a CLI via `python -m macro_sim.demographics.validation`.

**Tech Stack:** Python dataclasses, CSV/JSON stdlib, NumPy, existing demographics kernel/oracle modules, pytest.

## Global Constraints

- Do not put expensive 20-seed/80-year ensemble runs into default pytest.
- Config A validates mortality-only daily survival and headcount identity.
- Config B validates person-level ungated fertility against the one-dimensional Leslie oracle.
- Config C validates multistate oracle constants and two-sided matching smoke/integrity separately.
- Validation output lives under `outputs/demographics/phase0_validation` by default.
- Leave unrelated visualization, metrics, and time-calibration worktree changes untouched.

---

### Task 1: Harness API and CLI Smoke

**Files:**
- Create: `macro_sim/demographics/validation.py`
- Modify: `macro_sim/demographics/__init__.py`
- Test: `tests/test_demographic_phase0_validation.py`

**Interfaces:**
- `run_phase0_validation(output_dir: str | Path, n: int, years: int, seeds: int | Sequence[int]) -> dict`
- `main(argv: Sequence[str] | None = None) -> int`

Steps:
- [ ] Write failing tests that import `run_phase0_validation`, run a tiny validation, and assert `summary.json`, `spectral_constants.csv`, and config summaries exist.
- [ ] Implement minimal artifact writing and return structure.
- [ ] Export `run_phase0_validation`.

### Task 2: Hard Invariants

**Files:**
- Modify: `macro_sim/demographics/validation.py`
- Test: `tests/test_demographic_phase0_validation.py`

**Interfaces:**
- `validate_headcount_identity(results: list[TickResult]) -> bool`
- `partner_integrity(state: GenesisState) -> dict[str, int]`

Steps:
- [ ] Write tests for headcount identity, hook counts, retained dead persons, parent IDs, and partner integrity.
- [ ] Implement the checks and include them in `summary.json`.

### Task 3: Oracle Alignment Metrics

**Files:**
- Modify: `macro_sim/demographics/validation.py`
- Test: `tests/test_demographic_phase0_validation.py`

**Interfaces:**
- `total_variation(a: np.ndarray, b: np.ndarray) -> float`
- `oracle_alignment_series(...) -> list[dict]`

Steps:
- [ ] Write tests for TV distance and one-dimensional oracle alignment on a small run.
- [ ] Implement Config B alignment CSV with `year`, `alive`, `oracle_alive`, and `tv_distance`.
- [ ] Record multistate spectral constants and steady married profile in the constants CSV.

### Task 4: CLI Output

**Files:**
- Modify: `macro_sim/demographics/validation.py`
- Test: `tests/test_demographic_phase0_validation.py`

**Interfaces:**
- CLI options: `--output-dir`, `--n`, `--years`, `--seeds`, `--start-date`.

Steps:
- [ ] Write a test that calls `main([...])` with a tmp output dir.
- [ ] Implement argparse and print a concise pass/fail summary.
