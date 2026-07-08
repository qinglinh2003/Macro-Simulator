# v13 Union Profile Anchoring Implementation Plan

> **For agentic workers:** Use TDD. Add failing tests before production code, then run focused demographics tests.

**Goal:** Anchor Phase 0 partnership/marriage dynamics to an age-specific, reality-shaped union profile instead of a single flat adult married share.

**Architecture:** Introduce a small `macro_sim.demographics.union` module that owns age-band target profiles. Genesis relationship construction, multistate oracle, and social dynamics all consume the same profile so creation, oracle calibration, and micro dynamics do not drift into incompatible marriage regimes.

**Tech Stack:** Python dataclasses, NumPy, existing pytest demographics tests.

## Global Constraints

- Default profile is `medium_family_formation`: 18-24 = 0.10, 25-34 = 0.58, 35-49 = 0.74, 50-64 = 0.68, 65-74 = 0.55, 75-100 = 0.32.
- Treat `partner_id` as stable union / partnered status, not strictly legal marriage.
- Preserve existing biological Phase 0 Leslie tests by keeping `fertility_mode="all_women"` tests explicit.
- Do not remove existing relationship stats; add target-profile checks without broad refactors.

---

### Task 1: Target Profile API

**Files:**
- Create: `macro_sim/demographics/union.py`
- Modify: `macro_sim/demographics/__init__.py`
- Test: `tests/test_demographic_union_profile.py`

**Interfaces:**
- Produces: `UnionAgeBand`, `UnionTargetProfile`, `MEDIUM_FAMILY_FORMATION_PROFILE`, `partnered_share_by_band(people, profile)`.

Steps:
- [ ] Write failing tests for age-band lookup and band-share aggregation.
- [ ] Implement the profile dataclasses and helper.
- [ ] Export the new API from `macro_sim.demographics`.

### Task 2: Genesis Age-Band Matching

**Files:**
- Modify: `macro_sim/demographics/relationships.py`
- Test: `tests/test_demographic_phase0_relationships.py`

**Interfaces:**
- Consumes: `RelationshipConfig.union_target_profile`.
- Produces: genesis populations whose partnered shares roughly follow the profile by age band.

Steps:
- [ ] Add a failing test that genesis matching hits the medium profile within broad stochastic tolerances.
- [ ] Change `_match_partners` to select target female counts per age band instead of a flat adult target.
- [ ] Keep old `target_partnered_adult_share` as a fallback only when `union_target_profile=None`.

### Task 3: Multistate Oracle Anchoring

**Files:**
- Modify: `macro_sim/demographics/social.py`
- Modify: `macro_sim/demographics/multistate.py`
- Test: `tests/test_demographic_multistate_oracle.py`

**Interfaces:**
- Consumes: `SocialDynamicsConfig.union_target_profile`.
- Produces: multistate stable distribution with adult and reproductive-age union shares near the target.

Steps:
- [ ] Add a failing oracle test for adult and female 15-49 target shares.
- [ ] Add `union_target_profile` to `SocialDynamicsConfig`.
- [ ] Let multistate marriage probabilities derive from target current/next age shares when a profile is present.

### Task 4: Micro Dynamic Smoke Calibration

**Files:**
- Test: `tests/test_demographic_phase0_social_dynamics.py`

**Interfaces:**
- Consumes: default `SocialDynamicsConfig`.
- Produces: a 1000-person, multi-year smoke test where married/partnered share does not collapse toward 0.15-0.25.

Steps:
- [ ] Add a moderate-duration smoke test with relaxed stochastic bounds.
- [ ] Raise the default marriage-flow level only enough to keep the micro dynamics near the anchored profile.
- [ ] Run focused demographics regression.
