# Documentation

This directory keeps long-form project documentation out of the repository root.

- [`design/`](design/README.md) — development-first design docs: current brief, durable core rules, and archived research history.
- [`diagnostics/`](diagnostics/README.md) — runtime probes, causal/root-cause matrices, and observed-data contracts.
- [`plans/`](plans/README.md) — version-specific implementation plans.
- [`policy_module_v25.md`](policy_module_v25.md) — canonical Policy module design.
- [`controllers_v26.md`](controllers_v26.md) — institutional Controller design and
  acceptance contract, with the current
  [lever](controller_levers_v26.md) and
  [observation](controller_observations_v26.md) review tables.
- [`rl_training_v26.md`](rl_training_v26.md) — SMDP PPO training, held-out
  baseline evaluation, portable model artifacts, and engine deployment.
- [`shocks_v27.md`](shocks_v27.md) — semantic exogenous ShockTape/ShockEngine,
  economic coupling channels, disclosure rules, checkpoint/replay, and historical
  scenario composition.
- [`start_menu_design_v31.md`](start_menu_design_v31.md) — Claude Design-ready
  desktop start-menu and new-game specification covering country profiles, the
  complete Config/initial-Policy surfaces, World coupling, controllers, shocks,
  validation, and client settings.
- [`cpp_engine_refactor_v33.md`](cpp_engine_refactor_v33.md) — measured C++20
  engine architecture, complete module disposition, interoperability contracts,
  staged migration, and semantic/performance acceptance gates.
- [`cpp_engine_m0_execution_plan_v33.md`](cpp_engine_m0_execution_plan_v33.md) —
  executable M0 work packages for freezing Python contracts, traces, fixtures,
  benchmarks, acceptance rules, diagnostics, and migration gates.
- [`../archive/`](../archive/README.md) — archived scripts and other pre-refactor reference material.
- [`../artifacts/`](../artifacts/README.md) — generated/reference images and small experiment artifacts.

The root [`README.md`](../README.md) remains the quick project entry point.
Use [`design/current/module-map.md`](design/current/module-map.md) when you need
to connect a model concept to the current `macro_sim/` package path. Older
history files may mention root modules such as `economy.py` or `metrics.py`;
those names are historical references, not the active import surface.

The current v23 patch status is summarized at the top of
[`plans/PLAN_v23.md`](plans/PLAN_v23.md). Runtime, causal, and observed-data
verification—including the limits that remain outside the present patch—is
documented in [`diagnostics/README.md`](diagnostics/README.md).
