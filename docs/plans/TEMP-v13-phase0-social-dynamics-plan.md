# v13 Phase 0 Social Dynamics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or test-driven inline execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add daily marriage, divorce, and minor guardianship dynamics to the frozen Phase 0 demographic kernel.

**Architecture:** Keep social dynamics in `macro_sim/demographics/social.py`. `MicroDemographicKernel.tick()` advances biological events and delegates partner/household transitions to focused helpers. Parent IDs remain biological; household and guardian IDs represent care/residence and may change.

**Tech Stack:** Python dataclasses, `datetime.date`, NumPy RNG, pytest. No new dependencies.

## Global Constraints

- First version is frozen-economy only: no income, wealth, unemployment, or policy feedback.
- Default rates are intentionally conservative to avoid noisy household churn.
- Marriage is heterosexual, monogamous, adult-only, and close-kin-forbidden in Phase 0.
- Divorce splits households but never rewrites biological `mother_id` / `father_id`.
- Minors must always have `household_id`; if no kin household is available, use a public guardian household.
- Events must be explicit: `MarriageEvent`, `DivorceEvent`, and `GuardianshipEvent`.

---

### Task 1: Event Data Model and Config

**Files:**
- Modify: `macro_sim/demographics/agents.py`
- Create: `macro_sim/demographics/social.py`
- Modify: `macro_sim/demographics/kernel.py`
- Test: `tests/test_demographic_phase0_social_dynamics.py`

**Interfaces:**
- Produces: `SocialDynamicsConfig`, `MarriageEvent`, `DivorceEvent`, `GuardianshipEvent`.
- Adds person fields: `guardian_id`, `guardian_household_reason`, `marriage_start_date`, `marriage_count`, `last_divorce_date`, `last_widowed_date`.

### Task 2: Divorce and Guardianship

**Files:**
- Modify: `macro_sim/demographics/social.py`
- Modify: `macro_sim/demographics/kernel.py`
- Test: `tests/test_demographic_phase0_social_dynamics.py`

**Interfaces:**
- Produces: `apply_divorce_dynamics(...)` and `repair_minor_guardianship(...)`.

### Task 3: Marriage Market

**Files:**
- Modify: `macro_sim/demographics/social.py`
- Modify: `macro_sim/demographics/kernel.py`
- Test: `tests/test_demographic_phase0_social_dynamics.py`

**Interfaces:**
- Produces: `apply_marriage_market(...)`.

### Task 4: Verification

**Files:**
- Test-only.

- [ ] Run `uv run pytest -q tests/test_demographic_phase0_kernel.py tests/test_demographic_phase0_relationships.py tests/test_demographic_phase0_calendar.py tests/test_demographic_phase0_social_dynamics.py`.
- [ ] Generate a sample multi-year run and report marriage/divorce/guardianship event counts.
