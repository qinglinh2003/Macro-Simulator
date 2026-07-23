"""Current multi-economy Bulk-Synchronous-Parallel World container.

World coordinates independent domestic economies at registered cross-border
boundaries. Depending on capabilities, it owns FX/dealer settlement, trade,
external capital, migration, sanctions, peg reserves, global invariants, and
publication. With coupling disabled, N economies remain independent; an N=1
World preserves the bare Economy behavior tripwire.
"""

from macro_sim.world.world import ECONOMY_SEED_STRIDE, World

__all__ = ["World", "ECONOMY_SEED_STRIDE"]
