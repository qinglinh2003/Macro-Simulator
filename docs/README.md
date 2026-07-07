# Documentation

This directory keeps long-form project documentation out of the repository root.

- [`design/`](design/README.md) — development-first design docs: current brief, durable core rules, and archived research history.
- [`plans/`](plans/README.md) — version-specific implementation plans.
- [`../archive/`](../archive/README.md) — archived scripts and other pre-refactor reference material.
- [`../artifacts/`](../artifacts/README.md) — generated/reference images and small experiment artifacts.

The root [`README.md`](../README.md) remains the quick project entry point.
Use [`design/current/module-map.md`](design/current/module-map.md) when you need
to connect a model concept to the current `macro_sim/` package path. Older
history files may mention root modules such as `economy.py` or `metrics.py`;
those names are historical references, not the active import surface.
