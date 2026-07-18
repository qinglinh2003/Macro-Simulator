"""ExternalPolicy: each economy's OWN external stance (v25 B5, A6 rulings).

The World's cross-border levers were constructor vectors with no per-economy
owner. This object gives the 14 [W] levers a home inside each economy; the
World re-derives its coupling vectors from these at the coupling barrier --
one atomic commit point, so no per-economy ordering skew (§5.1-3).

Sanctions follow A6: unilateral OWNERSHIP (this economy's frozenset of targets),
symmetric EFFECT (the world derives `sanctioned(i,j) = j in imposed[i] or
i in imposed[j]`); an imposer can lift only its own stance.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExternalPolicy:
    # trade
    tariff: float = 0.0                       # importer's tax rate on landed value
    import_quota: "float | None" = None       # cap import VOLUME (share of capacity); None = open
    export_subsidy: float = 0.0               # exporter's fiscus subsidises (<0 = export tax)
    # capital account
    capital_control: float = 0.0              # throttle capital flows, in [0, 1]
    external_interest_settlement_fraction: float = 1.0
    # strategic
    sanctions_imposed_on: frozenset = field(default_factory=frozenset)   # economy ids
    # migration & remittances
    immigration_cap: "float | None" = None    # admit <= cap x pop (None = open)
    emigration_cap: "float | None" = None     # origin restricts its own exit
    remittance_tax: float = 0.0               # origin taxes inbound remittances
    outward_remittance_tax: float = 0.0       # host taxes outbound remittances
    guest_worker_return: float = 0.0          # temporary-migration return rate
    # FX regime (data model from P0; the peg machinery wires in B5b)
    fx_regime: str = "float"                  # {"float", "peg"}
    peg_anchor: "int | None" = None           # anchor economy id (never requires consent, A6)
    peg_reserve_scale: float = 1.0e5
