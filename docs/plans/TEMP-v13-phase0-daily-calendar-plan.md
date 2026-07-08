# v13 Phase 0 Daily Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or test-driven inline execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real Gregorian calendar to the Phase 0 demographic kernel, assign every person a birthday, and advance demographic ages by daily ticks.

**Architecture:** `GenesisState` owns `current_date`; `Person` owns `birth_date` and keeps `age` as completed years. Daily ticks advance `current_date` by one day, refresh completed ages from birthdays, and apply vital rates with a one-day natural-time step.

**Tech Stack:** Python `datetime.date`, `datetime.timedelta`, NumPy RNG, pytest. No new dependencies.

## Global Constraints

- Keep `age` as completed years for bins, relationship matching, and adult/minor checks.
- Add a date-based helper for continuous age so vital rates can read age in years.
- Genesis birth dates must be sampled so each person's completed age at `current_date` equals the Leslie-sampled age bucket.
- Each demographic tick advances exactly one Gregorian calendar day.
- Newborns receive `birth_date=current_date`, `age=0`, and mother's household.
- Leslie oracle remains annual; tests compare micro simulation to oracle at full-year boundaries.

---

### Task 1: Calendar Data Model

**Files:**
- Modify: `macro_sim/demographics/agents.py`
- Modify: `macro_sim/demographics/kernel.py`
- Test: `tests/test_demographic_phase0_calendar.py`

**Interfaces:**
- Produces: `Person.birth_date`, `Person.age_years_on(current_date)`, `GenesisState.current_date`.

- [ ] Write failing tests for genesis birth dates and completed-age consistency.
- [ ] Add date helpers and `birth_date` to `Person`.
- [ ] Add `current_date` to `GenesisState`.

### Task 2: Daily Tick Semantics

**Files:**
- Modify: `macro_sim/demographics/kernel.py`
- Modify: `macro_sim/demographics/rates.py`
- Test: `tests/test_demographic_phase0_calendar.py`
- Test: `tests/test_demographic_phase0_kernel.py`

**Interfaces:**
- Produces: daily `MicroDemographicKernel.tick()` behavior.

- [ ] Write failing tests for one-day advancement, birthday age increment, and newborn birth date.
- [ ] Add `Phase0VitalRates.fertility_rate(age_years)`.
- [ ] Convert death and birth probabilities to one-day natural-time steps.
- [ ] Update annual oracle test to compare at a full-year boundary.

### Task 3: Artifact Metadata and Verification

**Files:**
- Modify: `macro_sim/demographics/phase0.py`
- Test: `tests/test_demographic_phase0_calendar.py`

**Interfaces:**
- Produces: `current_date` in Phase 0 metrics.

- [ ] Write a test that artifact metrics include the calendar date.
- [ ] Add date metadata to `metrics.json`.
- [ ] Run focused demographics tests and generate a sample artifact.
