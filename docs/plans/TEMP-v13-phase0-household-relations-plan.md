# v13 Phase 0 Household Relations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or test-driven inline execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add genesis-time household and kinship construction for the Phase 0 demographic kernel, using population count as the input and deriving household count from matching.

**Architecture:** Keep the demographic vital-rate/oracle layer separate from the relationship layer. `create_genesis_population()` continues to sample people from the Leslie stable distribution, then optionally applies a deterministic relationship builder that fills `mother_id`, `father_id`, `partner_id`, and `household_id`, and emits household statistics.

**Tech Stack:** Python dataclasses, NumPy RNG, pytest. No new optimization dependency in the first pass; use age-bucketed matching with explicit feasibility/fallback statistics.

## Global Constraints

- Use `n` people as the genesis scale input; do not ask callers for household count.
- Replace ambiguous `parent_id` with `mother_id` and `father_id`.
- Keep parent-child edges semantically strict: only assign a parent ID when sex and age-gap constraints are satisfied.
- Every minor must receive a household with at least one adult, even if strict biological parent assignment is infeasible.
- Relationship generation must not change the age distribution, Leslie matrix, oracle, or headcount identity behavior.
- Relationship randomness must use its own seed stream derived from the genesis seed.
- Output relationship statistics so the generated household structure can be inspected.

---

### Task 1: Data Model and Tests

**Files:**
- Modify: `macro_sim/demographics/agents.py`
- Modify: `macro_sim/demographics/kernel.py`
- Test: `tests/test_demographic_phase0_kernel.py`

**Interfaces:**
- Produces: `Person.mother_id`, `Person.father_id`; `BirthEvent.mother_id`, `BirthEvent.father_id`.
- Removes: `Person.parent_id`, `BirthEvent.parent_id`.

- [ ] Write failing tests that assert genesis people have `mother_id` and `father_id`, and that birth events carry `mother_id`.
- [ ] Update `Person` and `BirthEvent`.
- [ ] Update `MicroDemographicKernel.tick()` newborn/event creation.
- [ ] Run the focused demographic tests.

### Task 2: Relationship Builder

**Files:**
- Create: `macro_sim/demographics/relationships.py`
- Modify: `macro_sim/demographics/kernel.py`
- Modify: `macro_sim/demographics/__init__.py`
- Test: `tests/test_demographic_phase0_relationships.py`

**Interfaces:**
- Produces: `RelationshipConfig`, `RelationshipStats`, `build_genesis_relationships(people, config, seed) -> RelationshipStats`.
- Consumes: `Person` records from genesis sampling.

- [ ] Write failing tests for derived households, minor placement, strict parent age gaps, and relationship statistics.
- [ ] Implement `RelationshipConfig` with adult age, minor age, parent age-gap bounds, spouse age gap, household capacity, and target partnership share.
- [ ] Implement partner matching among adults by sex-compatible, age-close candidates.
- [ ] Create one household per partnered adult pair and one household per single adult.
- [ ] Assign minors to strict mothers first, then strict fathers, then adult guardian household fallback.
- [ ] Return statistics including household count, household size distribution, parent coverage, guardian fallback, and age-gap summaries.

### Task 3: Phase 0 Artifact Integration

**Files:**
- Modify: `macro_sim/demographics/phase0.py`
- Test: `tests/test_demographic_phase0_relationships.py`

**Interfaces:**
- `generate_phase0_artifacts(..., build_relationships: bool = True)` includes `relationship_stats` in `metrics.json`.

- [ ] Write a test that artifact generation records relationship stats.
- [ ] Wire relationship generation into artifact generation.
- [ ] Print a short summary in the CLI output.

### Task 4: Focused Verification

**Files:**
- Test-only.

- [ ] Run `uv run pytest -q tests/test_demographic_phase0_kernel.py tests/test_demographic_phase0_relationships.py`.
- [ ] Generate a small artifact sample and inspect `metrics.json`.
- [ ] Report the relationship statistics to the user.
