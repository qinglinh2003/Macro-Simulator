# v13 Marital Fertility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or test-driven inline execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a marriage-gated fertility mode backed by a sex-aware two-state multistate Leslie oracle.

**Architecture:** Make marriage-gated fertility the default. Keep the old one-dimensional Leslie oracle as the explicit all-women fertility baseline. Add `macro_sim/demographics/multistate.py` for `age × sex × marital_status` indexing, matrix construction, stable distribution, married-female profile, and marital-fertility calibration. `MicroDemographicKernel` gets an explicit `fertility_mode` switch so the legacy all-women mode remains available for baseline/oracle tests.

**Tech Stack:** Python dataclasses, NumPy eigensystem routines, pytest. No new dependencies.

## Global Constraints

- First version uses two marital states only: `single` and `married`.
- State space is `age × sex × marital_status`, not just age × marital.
- Micro marriage remains a matching process; the multistate oracle is a linear approximation using age/sex transition hazards.
- Marital fertility must be calibrated so weighted TFR under the oracle's married-female profile matches `Phase0VitalRates.tfr`.
- Married-only micro fertility must produce no newborn with `father_id is None`.
- Married-only fertility is the default. All-women fertility must be requested explicitly with `fertility_mode="all_women"`.

---

### Task 1: Multistate Oracle

**Files:**
- Create: `macro_sim/demographics/multistate.py`
- Modify: `macro_sim/demographics/__init__.py`
- Test: `tests/test_demographic_multistate_oracle.py`

**Interfaces:**
- Produces: `MaritalState`, `Sex`, `MultiStateIndex`, `build_multistate_leslie_matrix`, `stable_multistate_distribution`, `married_female_share_by_age`.

### Task 2: Marital Fertility Calibration

**Files:**
- Modify: `macro_sim/demographics/multistate.py`
- Modify: `macro_sim/demographics/rates.py`
- Test: `tests/test_demographic_multistate_oracle.py`

**Interfaces:**
- Produces: `calibrate_marital_fertility_curve(rates, stable_vector, index)`.
- Produces: `Phase0VitalRates.fertility_shape_curve()`.

### Task 3: Micro Birth Gate

**Files:**
- Modify: `macro_sim/demographics/kernel.py`
- Test: `tests/test_demographic_marital_fertility.py`

**Interfaces:**
- Produces: `fertility_mode: "all_women" | "married_only"` and optional `marital_fertility_curve`.

### Task 4: Focused Verification

**Files:**
- Test-only.

- [ ] Run multistate tests.
- [ ] Run marital fertility tests.
- [ ] Run focused demographic tests.
- [ ] Run a small married-only simulation and report births/father coverage.
