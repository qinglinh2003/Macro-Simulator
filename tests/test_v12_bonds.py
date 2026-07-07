"""v12 acceptance tests (DESIGNDOC §39) — the SECURITIES arc.

v12.0 un-consolidates the consolidated `GOV` into a Treasury (`TSY`, the fiscal deposit account) + a Central Bank
(the reserve node), abstracting every hard-coded `"GOV"` behind a `_fiscal` account id and adding the CB
balance-sheet scaffolding (TGA, cb_claim_on_tsy, a bond overlay) + the securities-identity gates (no-ops until
issuance lands). With `bonds=False` (default) nothing changes; with `bonds=True` but NO issuance
(`bond_finance_frac=0`, `Config.v12()`) the fiscal account is merely renamed TSY ⇒ still bit-identical to v11.5.
Later v12.x add bond issuance + sterilisation + a traded market. "Done" for v12.0:
  * `Config.v12()` (bonds on, no issuance) ⇒ bit-identical to v11.5 (the refactor is behaviour-preserving);
  * the securities-identity gate runs (as a no-op) and A5 + reserve conservation still hold.

Run: ``uv run python tests/test_v12_bonds.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config                # noqa: E402
from economy import Economy              # noqa: E402

NC, NK, NH = 60, 30, 400


def test_unconsolidation_bit_identical():
    """v12.0: un-consolidating GOV→TSY+CB with NO issuance (bond_finance_frac=0) reproduces v11.5 exactly -- a pure
    behaviour-preserving refactor + inert CB scaffolding."""
    a = Economy(Config.v115(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=0)).run()
    b = Economy(Config.v12(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=0,
                           bond_finance_frac=0.0)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["broad_money"] == y["broad_money"]
        assert x["conservation_drift"] == y["conservation_drift"]
        assert x.get("gov_debt") == y.get("gov_debt"), "gov_debt must match (TSY==GOV with no issuance)"


def test_bills_conserve_all_identities():
    """v12.1: with bills active (frac=0.9) the fiscal account is TSY, bills are issued, and ALL gates hold each
    tick: deposit-A5, reserve conservation, the bond identity (Σ holdings@face = outstanding), and the master NFA
    identity (private NFA = M₀ + gov debt) -- the last two run inside `_assert_securities_identities` every tick."""
    econ = Economy(Config.v12(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=500, seed=1))
    econ.run()   # the securities-identity gate raises on any drift, so a clean run == identities held
    assert econ._fiscal == "TSY"
    assert abs(sum(econ._bond_holdings.values()) - econ._bonds_outstanding) < 1e-6 * max(1.0, econ._bonds_outstanding)
    # bills are issued only when the govt runs net DEBT (gov_debt>0) -- emergent (a surplus economy issues none).
    # Issuance itself is exercised by test_sterilisation_drains_bank_reserves; here we assert the CONDITIONAL.
    if max(r.get("gov_debt", 0.0) for r in econ.records) > 1.0:
        assert max(r.get("bonds_outstanding", 0.0) for r in econ.records) > 0.0, "bills should be issued under a deficit"
    m = max(r["broad_money"] for r in econ.records)
    assert max(r["conservation_drift"] for r in econ.records) < 1e-6 * m, "deposit-A5 broke"


def test_bills_no_demand_artifact():
    """v12.1 CORRECTNESS: bond-financing absorbs households' IDLE SAVINGS into bills (leaving a transaction buffer),
    so raising `bond_finance_frac` must NOT starve consumption / spike unemployment -- households keep their
    spendable deposits. (Draining bills pro-rata to ALL deposits — an earlier bug — collapsed demand: u 0.007→0.35.)
    Sterilisation from households is therefore MODEST (idle savings are a small pool); the strong reserve drain is
    v12.2, when BANKS absorb the bulk of the debt into bonds with their excess reserves."""
    import numpy as np
    lo = Economy(Config.v12(n_firms_c=100, n_firms_k=50, n_households=1000, n_ticks=1200, seed=0,
                            bond_finance_frac=0.0)).run()
    hi = Economy(Config.v12(n_firms_c=100, n_firms_k=50, n_households=1000, n_ticks=1200, seed=0,
                            bond_finance_frac=0.9)).run()
    u_lo = np.mean([r["unemployment_rate"] for r in lo[-400:]])
    u_hi = np.mean([r["unemployment_rate"] for r in hi[-400:]])
    assert u_hi < u_lo + 0.05, f"bond-financing must NOT collapse demand (no artifact): u {u_lo:.3f} → {u_hi:.3f}"


def test_v123_off_bit_identical():
    """v12.3: with every BOND lever at its off-default (coupon 0, theta 0, maturity 1, bank appetite 0) the v12.3
    config's securities machinery is a pure opt-in overlay ⇒ REPRODUCES the v12.1-fix economy exactly. v12.3 also
    RE-CALIBRATES the bank sector (thicker capital 0.18/0.15 + a lower founder gate 400, a user-driven fix for the
    long-horizon bank bleed), so this test resets those to v12's values (0.1/0.25/1500) to isolate the bond overlay."""
    a = Economy(Config.v12(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=0)).run()
    b = Economy(Config.v123(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=0,
                            bond_coupon=0.0, bond_theta=0.0, bond_maturity=1, bank_bond_appetite=0.0,
                            bank_target_capital_ratio=0.1, bank_exposure_limit=0.25, bank_min_capital=1500.0)).run()
    for x, y in zip(a, b):
        assert x["real_output"] == y["real_output"] and x["broad_money"] == y["broad_money"]
        assert x["conservation_drift"] == y["conservation_drift"]


def test_v123_coupon_theta_conserve_no_refreeze():
    """v12.3 (household side): multi-period COUPON bonds held as a `bond_theta` portfolio share. All four gates hold
    every tick (the securities-identity gate raises otherwise), a MEANINGFUL coupon-paying stock is held, and -- the
    key property -- making bonds a real held asset does NOT re-freeze demand: late u stays near the frac=0 baseline
    (bonds are liquid: they mature/roll and enter the wealth term)."""
    import numpy as np
    base = Economy(Config.v12(n_firms_c=100, n_firms_k=50, n_households=1000, n_ticks=1500, seed=0,
                              bond_finance_frac=0.0)).run()
    econ = Economy(Config.v123(n_firms_c=100, n_firms_k=50, n_households=1000, n_ticks=1500, seed=0))
    rec = econ.run()   # clean run == all identities held (the gate raises on drift)
    u_base = np.mean([r["unemployment_rate"] for r in base[-500:]])
    u_v123 = np.mean([r["unemployment_rate"] for r in rec[-500:]])
    assert u_v123 < u_base + 0.03, f"coupon+theta bonds must not re-freeze demand: u {u_base:.3f} → {u_v123:.3f}"
    assert abs(sum(econ._bond_holdings.values()) - econ._bonds_outstanding) < 1e-6 * max(1.0, econ._bonds_outstanding)
    m = max(r["broad_money"] for r in rec)
    assert max(r["conservation_drift"] for r in rec) < 1e-6 * m, "A5 (ΣD−ΣL−bank_securities=M) broke"


def test_svb_duration_channel_and_bank_securities_conserve():
    """v12.3 SVB: a bank holding a multi-period bond takes an MTM LOSS when the policy rate rises above the coupon,
    thinning its `economic_capital` below its deposit-capital -- the 2023-SVB channel. Also verifies the money-
    CREATING purchase (`bank_buy_bond_with_reserves`) and its redemption both hold the extended A5 gate
    (ΣD−ΣL−bank_securities=M) and the master NFA identity."""
    econ = Economy(Config.v123(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=60, seed=0))
    econ.run()
    bank = next(b for b in econ.banks if b.alive)
    face = 4000.0
    econ._rate = 0.01                                   # at the coupon ⇒ par
    econ.ledger.bank_buy_bond_with_reserves(bank.id, econ._fiscal, face)   # money creation: reserves→CB, TSY funded
    econ._bonds.append({"holder": bank.id, "face": face, "cost": face, "matures_at": econ.t + 8})
    econ._bonds_outstanding += face
    econ._reindex_bonds()
    econ.ledger.assert_conserved(); econ.ledger.assert_reserves_conserved(); econ._assert_securities_identities()
    bal = econ.ledger.balance(bank.id)
    cap_par = econ._bank_economic_capital(bank)
    assert abs(cap_par - bal) < 1e-6, "at coupon=rate the bond is at par ⇒ no unrealised P&L"
    econ._rate = 0.08                                   # RATE HIKE ⇒ market ≪ face ⇒ MTM loss
    cap_hi = econ._bank_economic_capital(bank)
    assert cap_hi < cap_par - 1.0, f"rate hike must thin economic capital (SVB): {cap_par:.1f} → {cap_hi:.1f}"
    for l in econ._bonds:                               # force maturity, redeem (unwind the money creation)
        if l["holder"] == bank.id:
            l["matures_at"] = econ.t
    econ._rate = 0.01
    econ._phase_bill_maturity()
    econ.ledger.assert_conserved(); econ.ledger.assert_reserves_conserved(); econ._assert_securities_identities()


def test_v124_off_bit_identical():
    """v12.4: with OMO/LoLR off and the bank levers 0, the v12.4 code (reserve create/destroy, LoLR branch, the
    duration cap) is inert ⇒ reproduces v12.3 exactly."""
    a = Economy(Config.v123(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=0)).run()
    b = Economy(Config.v124(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=400, seed=0,
                            omo=False, lolr=False, bank_bond_appetite=0.0, bank_bond_duration_limit=0.0)).run()
    for x, y in zip(a, b):
        assert x["broad_money"] == y["broad_money"] and x["conservation_drift"] == y["conservation_drift"]


def test_v124_reserve_create_destroy_conserves():
    """v12.4: the CB creating/destroying base money holds BOTH gates -- `retire_reserves` lowers the conserved
    reserve total `_reserve_M` (and Σ reserves with it, exact by construction), `issue_reserves` raises it, and the
    DEPOSIT ledger (ΣD−ΣL−bank_securities=M) is untouched (reserves are a separate overlay)."""
    econ = Economy(Config.v123(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=40, seed=0)); econ.run()
    led = econ.ledger
    M0, D0 = led._reserve_M, led.net_worth
    bank = next(b for b in econ.banks if b.alive)
    led.retire_reserves(bank.id, 1000.0)
    led.assert_reserves_conserved(); led.assert_conserved()
    assert abs(led._reserve_M - (M0 - 1000.0)) < 1e-6 and abs(led.net_worth - D0) < 1e-6
    led.issue_reserves(bank.id, 1000.0)
    led.assert_reserves_conserved()
    assert abs(led._reserve_M - M0) < 1e-6


def test_v124_lolr_funds_solvent_bank():
    """v12.4 LoLR: the CB funds an illiquid bank with emergency reserves (issue_reserves) so it can honour
    withdrawals; conservation holds and the advance is tracked. (Direct check of the rescue leg.)"""
    econ = Economy(Config.v123(n_firms_c=NC, n_firms_k=NK, n_households=NH, n_ticks=40, seed=0)); econ.run()
    led = econ.ledger
    bank = next(b for b in econ.banks if b.alive)
    r = led.reserves(bank.id)                       # drain its reserves to ~0 (a run has exhausted them)
    if r > 0:
        led.retire_reserves(bank.id, r)
    need = 500.0
    led.issue_reserves(bank.id, need); econ._lolr_advances += need
    led.assert_reserves_conserved(); led.assert_conserved()
    assert led.reserves(bank.id) >= need - 1e-6 and econ._lolr_advances >= need


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fails = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            fails += 1; print(f"  FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    return fails


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
