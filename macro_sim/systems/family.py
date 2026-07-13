"""v18.4 inter-household family transfers — the first-line private safety net.

Reality's first private mechanism against deprivation is kin support (adult children
support parents, parents support children). The v13 relation links (mother_id/father_id)
+ the person-claim/ledger rails make it cheap. A household that cannot afford its
NECESSITY need from live deposits is topped up by kin households that hold a surplus
above their own need (× a buffer), capped by the recipient's gap and the donor's surplus.

Placed BEFORE the goods phase (after planning), so the transfer relaxes the A4 cash cap
and reaches consumption the same tick. Atomic and conserving: the money moves on the
ledger and the person-claim cash moves equal-and-opposite, so the A5 / claim-identity
gates stay green.

The point the mechanism SURFACES (per PLAN_v18 18.4): the households left exposed are
exactly those with NO kin donor and no assets — a distributional object the arc could
not name before. Off (family_transfers=False) ⇒ the phase is a no-op ⇒ bit-identical.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

EPS = 1e-9


def _necessity_cost(econ: Any, h: Any, p_n: float) -> float:
    """Nominal cost of a household's necessity need at the current necessity price."""
    from macro_sim.systems.goods import _necessity_need_for
    return _necessity_need_for(econ, h) * p_n


def run_family_transfer_phase(econ: Any) -> None:
    cfg = econ.cfg
    if not getattr(cfg, "family_transfers", False):
        return                               # off ⇒ no state touched ⇒ bit-identical
    econ._family_transfer_total = 0.0
    econ._family_transfer_recipients = 0.0
    econ._family_exposed = 0.0
    bridge = getattr(econ, "demographic_bridge", None)
    state = getattr(econ, "demographic_state", None)
    if bridge is None or state is None or not econ.n_firms:
        return
    led = econ.ledger
    buffer = float(getattr(cfg, "family_transfer_buffer", 1.5))
    p_n = sum(f.price for f in econ.n_firms) / max(1, len(econ.n_firms))
    if p_n <= EPS:
        return

    # kin indices over alive persons (built once; O(N))
    alive = [p for p in getattr(state, "people", []) if getattr(p, "alive", True)]
    pby: Dict[int, Any] = {int(p.id): p for p in alive}
    children_index: Dict[int, List[int]] = defaultdict(list)
    for p in alive:
        for parent in (getattr(p, "mother_id", None), getattr(p, "father_id", None)):
            if parent is not None:
                children_index[int(parent)].append(int(p.id))
    hh_members: Dict[int, List[Any]] = defaultdict(list)
    for p in alive:
        hid = getattr(p, "household_id", None)
        if hid is not None:
            hh_members[int(hid)].append(p)

    def _acct(demo_hid: int):
        return bridge.household_to_account.get(int(demo_hid))

    # per economic household: deposits, need cost, demo id
    info = {}
    for h in econ.households:
        demo_hid = bridge.household_id_for_account(h.id)
        dep = led.balance(h.id)
        info[h.id] = (demo_hid, dep, _necessity_cost(econ, h, p_n))

    for h in econ.households:
        demo_hid, dep, need_cost = info[h.id]
        gap = need_cost - dep
        if gap <= EPS:                       # can already afford necessities
            continue
        # kin economic accounts (parents + adult children of every member), excluding self
        kin_accts = set()
        for person in hh_members.get(int(demo_hid), []):
            rel = [getattr(person, "mother_id", None), getattr(person, "father_id", None)]
            rel += children_index.get(int(person.id), [])
            for kin_pid in rel:
                if kin_pid is None:
                    continue
                kp = pby.get(int(kin_pid))
                if kp is None or getattr(kp, "household_id", None) is None:
                    continue
                a = _acct(int(kp.household_id))
                if a is not None and a != h.id:
                    kin_accts.add(a)
        if not kin_accts:
            econ._family_exposed += 1.0
            continue
        # drain donors (surplus above their own need x buffer) until the gap closes
        got = False
        for a in kin_accts:
            if gap <= EPS:
                break
            d_info = info.get(a)
            if d_info is None:
                continue
            _dh, d_dep, d_need = d_info
            surplus = d_dep - d_need * buffer
            if surplus <= EPS:
                continue
            amt = min(gap, surplus)
            if amt <= EPS:
                continue
            led.transfer(a, h.id, amt)
            bridge.post_household_cash_delta(a, -amt, reason="family_transfer")
            bridge.post_household_cash_delta(h.id, amt, reason="transfer_income")
            info[a] = (_dh, d_dep - amt, d_need)        # keep the donor's running balance
            gap -= amt
            econ._family_transfer_total += amt
            got = True
        if got:
            econ._family_transfer_recipients += 1.0
        elif gap > EPS:
            econ._family_exposed += 1.0                 # had kin, but none with surplus
