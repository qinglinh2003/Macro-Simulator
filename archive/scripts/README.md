# Archived Scripts

These scripts are preserved for historical reference only. They were useful
during earlier diagnostic and validation rounds, but the script/protocol layer
will be redesigned during the upcoming code refactor.

Do not treat this directory as an active API or supported command surface.
Internal docstrings may still mention old paths such as `scripts/...`; those
comments are archival.

## Contents

| Directory | Historical role |
|---|---|
| [`plots/`](plots/README.md) | Diagnostic plot generators. |
| [`validation/`](validation/README.md) | Held-out macro validation scripts. |
| [`experiments/`](experiments/README.md) | Reusable experiment sweeps and confirmations. |
| [`scratch/`](scratch/README.md) | One-off diagnostic probes. |
| [`runs/`](runs/README.md) | Legacy version-specific run entrypoints. |
| [`prun.py`](prun.py) | Parallel run helper used by old scripts. |

The active model code remains at the repository root until it is packaged in a
separate refactor.
