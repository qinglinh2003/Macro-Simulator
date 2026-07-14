"""v20 bit-identity smoke: the `World` container is inert.

    PYTHONPATH=$(pwd) uv run python scripts_v20/smoke.py

Verifies, on both the macro and the full frontier stack, that:
  * World([cfg])  digests identically to a bare Economy(cfg)   — the N=1 ≡ dev gate;
  * an N=2 World's two economies are independent (adding B does not perturb A).

Because v20.0 does not touch `Economy` at all, the closed-economy frontier digest is
unchanged from dev — this smoke asserts the WRAPPER preserves it.
"""

from __future__ import annotations

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macro_sim.config import Config              # noqa: E402
from macro_sim.economy import Economy            # noqa: E402
from macro_sim.world import ECONOMY_SEED_STRIDE, World  # noqa: E402

WORLDS = {
    "macro": lambda seed=0, **e: Config.v124(
        n_firms_c=60, n_firms_k=30, n_households=400, n_ticks=400, seed=seed, **e),
    "frontier": lambda seed=0, **e: Config.v13(
        seed=seed, n_households=50, n_firms_c=50, n_firms_k=25, n_banks=2,
        demographics_population=500, n_ticks=730,
        housing_enabled=True, housing_market_enabled=True,
        energy_enabled=True, energy_household=True, **e),
}


def digest(records) -> str:
    h = hashlib.sha256()
    for rec in records:
        for k in sorted(rec.keys()):
            h.update(k.encode())
            h.update(repr(rec[k]).encode())
    return h.hexdigest()


def main() -> int:
    ok = True
    for name, mk in WORLDS.items():
        bare = Economy(mk())
        bare.run()
        bare_d = digest(bare.records)

        w1 = World([mk()])
        w1.run()
        w1_d = digest(w1.economies[0].records)
        gate1 = w1_d == bare_d
        ok &= gate1
        print(f"[{'OK ' if gate1 else 'FAIL'}] {name}: N=1 World ≡ bare  {w1_d[:16]}")

        w2 = World([mk(), mk()], base_seed=100)
        w2.run()
        for i in range(2):
            solo = Economy(mk(seed=100 + i * ECONOMY_SEED_STRIDE))
            solo.run()
            gate2 = digest(w2.economies[i].records) == digest(solo.records)
            ok &= gate2
            print(f"[{'OK ' if gate2 else 'FAIL'}] {name}: N=2 econ[{i}] independent")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
