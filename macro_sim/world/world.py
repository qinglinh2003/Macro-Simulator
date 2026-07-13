"""The `World` container (PLAN_v20 §0.5 component ②, §5 BSP tick).

v20.0 delivers the substrate only: N economies + residency/currency tags + the BSP tick
SKELETON (an empty coupling barrier + the independent domestic step + an empty dealer
update) + per-economy RNG isolation. No coupling — that lands in v20.1 (FX) and v20.2
(trade). The load-bearing property is that this layer is INERT: N economies run exactly
as N independent closed economies, so `World([cfg])` ≡ `Economy(cfg)` byte-for-byte.
"""

from __future__ import annotations

from dataclasses import replace
from typing import List

from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.world.fx import FXDealer, RateVector

# Per-economy seeds must be far-spaced: each `Economy` derives many substreams as
# `cfg.seed + <offset>` with offsets up to ~90007 and some only 1 apart (e.g. 13000,
# 13001, 13002). A stride this large guarantees economy i's substreams never collide
# with economy j's — the requirement that adding economy B cannot perturb economy A
# (PLAN_v20 §9; what makes the N=1≡dev gate and cumulative bit-identity hold).
ECONOMY_SEED_STRIDE = 1_000_000


class World:
    """A container of N coupled economies.

    Parameters
    ----------
    configs:
        One `Config` per economy. Their structure defines each economy's *character*
        (§0.6 `CountryProfile`); at v20.0 they are typically identical.
    base_seed:
        If given, each economy is re-seeded to ``base_seed + i * ECONOMY_SEED_STRIDE``
        so N structurally-identical configs become N INDEPENDENT draws (the identical-
        economy quiet baseline, §8). If ``None``, each config keeps its own seed — so
        ``World([cfg])`` reproduces ``Economy(cfg)`` exactly (the bit-identity gate).
    """

    def __init__(
        self,
        configs: List[Config],
        *,
        base_seed: int | None = None,
        couple: bool = False,
        fx_lambda: float = 0.0,
    ):
        if not configs:
            raise ValueError("World needs at least one economy config")
        self.economies: List[Economy] = []
        for i, cfg in enumerate(configs):
            if base_seed is not None:
                cfg = replace(cfg, seed=base_seed + i * ECONOMY_SEED_STRIDE)
            econ = Economy(cfg)
            # Residency + currency tags (§0.5 component ①). At v20.0 only labels: an
            # agent's residency is which economy owns it; the currency labels the money.
            # These deepen (per-asset denomination) once capital/trade need them.
            econ.economy_id = i
            econ.currency = f"CUR{i}"
            self.economies.append(econ)
        self.n = len(self.economies)
        self.t = 0

        # v20.1 FX layer. couple=False ⇒ no FX objects, no dealer accounts ⇒ the World is
        # exactly v20.0 (bit-identical). couple=True installs the rate vector + the dealer
        # (one account per economy); with zero trade it is INERT (rates flat, inventory 0).
        self.couple = couple
        self.fx_lambda = fx_lambda
        self.rates: RateVector | None = None
        self.dealer: FXDealer | None = None
        self.world_records: List[dict] = []
        if couple:
            self.rates = RateVector(self.n)
            self.dealer = FXDealer(self.economies)

    # ======================================================================
    # One BSP tick: coupling barrier -> independent domestic step -> dealer
    # ======================================================================
    def step(self) -> List[dict]:
        self._coupling_barrier()                              # thin central barrier
        recs = [econ.step() for econ in self.economies]       # INDEPENDENT domestic step
        self._dealer_update(recs)                             # dealer inventory update
        self.t += 1
        return recs

    def _coupling_barrier(self) -> None:
        """The thin central barrier: compute cross-border export demand / import supply
        on last tick's prices + the current rate vector, and grope the rate.

        v20.1: the dealer's net inventory is the groping signal (§3); with zero trade it
        is all-zero ⇒ rates stay flat. Trade injection into the goods sessions lands in
        v20.2. Reductions across economies use fixed economy-id order (§9).
        """
        if not self.couple:
            return
        signal = self.dealer.inventory()                      # zero at v20.1 (no flows yet)
        self.rates.grope(signal, self.fx_lambda)

    def _dealer_update(self, recs: List[dict]) -> None:
        """Book the dealer's revaluation and record the World FX gauges (§6/§7).

        v20.1: no trade ⇒ inventory 0, rates flat ⇒ every gauge is trivially zero/unit.
        """
        if not self.couple:
            return
        self.dealer.book_revaluation(self.rates)
        inv = self.dealer.inventory()
        e = self.rates.e
        # Multilateral BoP in the numéraire = the dealer's net worth (Σ inventory_i / e_i);
        # ≡ 0 to float tolerance when trade is balanced / absent (gate #2, §6).
        bop_numeraire = self.dealer.net_worth_numeraire(self.rates)
        self.world_records.append(
            {
                "t": self.t,
                "e": list(e),
                "dealer_inventory": list(inv),
                "bop_numeraire": bop_numeraire,
                "dealer_valuation": self.dealer.valuation,
            }
        )

    def run(self, n_ticks: int | None = None) -> List[List[dict]]:
        n = n_ticks if n_ticks is not None else self.economies[0].cfg.n_ticks
        for _ in range(n):
            self.step()
        return [econ.records for econ in self.economies]

    # -- convenience -----------------------------------------------------------
    @property
    def records(self) -> List[List[dict]]:
        """Per-economy record series, indexed by economy id."""
        return [econ.records for econ in self.economies]
