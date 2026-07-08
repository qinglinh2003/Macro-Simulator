# V13 Population Layer Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a population layer that starts from a self-consistent demographic kernel and then couples population and economy in attribution-preserving phases.

**Architecture:** Vital-rate functions expose the coupling seam from day one:
`rate(person, demographic_state, economic_state, policy_state)`. Phase 0 feeds them a frozen/no-economic state so they reduce to biological baseline rates; the frozen mode remains a permanent oracle and debugging bench.

**Tech Stack:** Python 3.12, dataclasses, NumPy, Matplotlib, existing `macro_sim` package, pytest.

## Global Constraints

- Preserve P1 person headcount stock-flow consistency every tick.
- Preserve P2 ledger compatibility for every vital event that touches economic accounts.
- Do not encode demographic transition, wealth-longevity gradient, age-wealth hump, or inheritance concentration as axioms.
- Keep population RNG independent from future economic RNG streams.
- Add one coupling channel at a time and always compare against the frozen demographic baseline.

---

## Phase 0 — Self-Consistent Population Kernel

Goal: build the demographic engine under frozen economy.

Components:

- Vital rates: Gompertz-Makeham mortality, fertility hump calibrated by TFR, sex ratio at birth, age cap.
- Leslie matrix derived from the rates.
- Stable age distribution from the dominant Leslie eigenvector.
- Genesis population sampled from that stable distribution.
- Stochastic micro tick with birth/death events and empty `on_birth` / `on_death` hooks.
- Deterministic Leslie oracle running in parallel.
- Stable pyramid rendering.

Acceptance:

- Genesis pyramid is sampled from the stable eigenvector.
- Stochastic micro simulation tracks the Leslie oracle within sampling error.
- Headcount identity closes exactly every tick.
- Perturbed age structures relax toward the stable distribution at the spectral damping rate.

## Phase 1 — Population Feeds Economy, No Feedback

Goal: let population structure affect economic aggregates while vital rates still ignore economic state.

Channels:

- Birth/death as economic-account entry/cleanup only when account boundaries are crossed.
- Age to labor supply.
- Age to lifecycle consumption, saving, and asset demand.
- Death to estate settlement and inheritance.

Acceptance:

- Demographic path is pointwise identical to Phase 0 under the same population RNG seed.
- Economic changes are attributable to population structure alone.

## Phase 2 — Macro Feedback Into Vital Rates

Goal: close macro economic feedback loops one at a time.

Candidate channels:

- Fertility responds to aggregate income, child cost, unemployment, transfers, or housing-cost proxy.
- Mortality responds to aggregate income, public health/welfare, or poverty proxy.
- Migration remains an external/open-economy hook, not a closed-economy default.

Acceptance:

- Deviations from the frozen baseline are attributable to the newly closed macro feedback channel.

## Phase 3 — Heterogeneous Agent-Level Feedback

Goal: make population dynamics a driver of wealth concentration.

Candidate channels:

- Differential mortality by own resources.
- Differential fertility by own income, class, and household stability.
- Household formation and assortative matching.
- Estate settlement, inheritance, estate tax, and household closure.

Acceptance:

- Wealth concentration can be decomposed into lifecycle accumulation, bequests, and differential vital rates by toggling channels.

## Phase 4 — Calibration And Research Outputs

Goal: calibrate and use the coupled population-economic model.

Targets:

- Realistic e0, TFR, stable age distribution, and demographic transition.
- Wealth-longevity gradient.
- Age-wealth hump.
- Inheritance contribution to upper-tail wealth.
- Generation-wave and business-cycle interactions.
