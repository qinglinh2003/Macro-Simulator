# V13 Phase 0 Population Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the previous demographic fitting prototype with a Phase 0 population kernel: vital rates, Leslie oracle, genesis sampling, stochastic micro ticks, and pyramid rendering.

**Architecture:** `macro_sim.demographics` becomes a small kernel package. `rates.py` owns biological rates; `leslie.py` owns deterministic matrix/oracle math; `agents.py` owns person/event data; `kernel.py` owns genesis and stochastic ticks; `visualization.py` renders the stable pyramid; `phase0.py` is a thin CLI.

**Tech Stack:** Python 3.12, dataclasses, NumPy, Matplotlib, pytest.

## Global Constraints

- Delete the previous demographic fitting/World-Bank/parameterization prototype code.
- Phase 0 rates accept an economic-state seam later, but run under frozen/no-economy behavior now.
- Headcount identity must be asserted on every stochastic tick.
- Use a dedicated RNG stream for population sampling and vital events.
- Keep birth/death hooks empty but present (`on_birth`, `on_death`) for later ledger coupling.
- Render a tick-0 stable population pyramid derived from the Leslie eigenvector, not hand-shaped bins.

---

## Tasks

- [x] Write Phase 0 tests for vital-rate curves, Leslie eigenstate, genesis sampling, stochastic tick identity, oracle drift, relaxation, and image output.
- [x] Remove old demographic fitting/World-Bank/parameterization modules and tests.
- [x] Implement `rates.py`, `leslie.py`, `agents.py`, `kernel.py`, `visualization.py`, and `phase0.py`.
- [x] Update `macro_sim.demographics.__init__` and `pyproject.toml` CLI scripts.
- [x] Generate a Phase 0 pyramid artifact under `outputs/demographics/phase0_kernel/`.
- [x] Run focused and adjacent regression tests.
