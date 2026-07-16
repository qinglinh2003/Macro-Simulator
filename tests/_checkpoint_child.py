"""Subprocess leg of the checkpoint bit-identity gate (tests/test_checkpoint.py).

Loads a checkpoint in a FRESH interpreter (the design's non-negotiable process
boundary: same-process resume can hide module-global state and hash-seed
dependence), steps the engine the requested number of ticks, and writes the
canonical state digest to the output path.

Usage: python tests/_checkpoint_child.py CKPT_PATH N_TICKS OUT_PATH
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_sim.checkpoint import load_checkpoint, state_digest


def main() -> None:
    ckpt_path, n_ticks, out_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    engine, _sidecar, _header = load_checkpoint(ckpt_path)
    for _ in range(n_ticks):
        engine.step()
    Path(out_path).write_text(state_digest(engine))


if __name__ == "__main__":
    main()
