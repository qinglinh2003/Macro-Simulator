"""v20 open economy — the multi-economy `World` container.

An open economy is N closed economies coupled at the border. `World` holds N
instantiable `Economy` objects and runs the Bulk-Synchronous-Parallel tick: a thin
central coupling barrier (empty at v20.0; FX in v20.1, trade in v20.2) followed by each
economy's INDEPENDENT domestic step. With every open-economy flag off, a World of N
economies is exactly N independent closed runs, and an N=1 World reproduces
`Economy(cfg)` byte-for-byte (the keystone bit-identity gate).
"""

from macro_sim.world.world import ECONOMY_SEED_STRIDE, World

__all__ = ["World", "ECONOMY_SEED_STRIDE"]
