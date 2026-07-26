from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--ticks", type=int, default=400)
    args = parser.parse_args()
    sys.path.insert(0, str(args.native_dir))
    sys.path.insert(1, str(args.source_dir))

    from macro_sim.desktop.new_game import NewGameSpec
    from macro_sim.native_backend import NativeSimulationSession

    session = NativeSimulationSession.create(NewGameSpec.default(seed=7))
    session.advance(actions=(
        {"lever": "tax_income_rate", "value": 0.7},
    ))
    while session.tick < args.ticks:
        session.advance()
    assert session.tick == args.ticks
    print("M10 policy stress completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
