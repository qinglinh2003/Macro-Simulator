# PLAN v10.1 — Bank pays interest BY DEPOSITS (fixing the equal-split distortion)

Status: **design draft.** Cumulative on v10. New flag default-off ⇒ bit-identical to v10.

---

## 0. The defect (found while diagnosing v10)

v10's rate transmission looked "perverse" (higher r → higher output on the low branch). The diagnosis (a
hump-shaped rate–output relation, §33) traced the low-branch expansion to an over-strong **interest-income
demand channel**, whose root is a modeling shortcut in the v3 bank:

> The bank collects loan interest from borrowers, then **splits it EQUALLY among all households**
> ([economy.py] `share = payable / len(households)`), framed as a "bank dividend." This was plumbing to
> "close the interest loop" (else the bank hoards all money — a sink), never a model of deposit interest.

Equal-split is wrong two ways: (1) it pays interest to households with **no deposits** (hand-to-mouth, MPC 0.8
⇒ spent in full), maximising the demand injection; (2) it ignores the deposit structure the ledger already
tracks. The economically correct recipient of interest is the **depositor, in proportion to deposits**.

## 1. The fix (minimal, correctness-first)

Distribute the bank's payable interest **∝ each household's deposit balance** (deposit interest), instead of
equally:
```
household h receives:  payable · D_h / Σ_k D_k          (D = deposit balance; was payable / N)
```
- Keeps it a single flow (bank → households) — no new stock, no new money ⇒ A5 untouched.
- `interest_by_deposits=False` ⇒ the equal-split path ⇒ **bit-identical to v10 and all prior**.
- Config (structural bank mechanics), NOT a Policy dial. `Config.v101()` = v10 + `interest_by_deposits=True`.
- Float-safe: each transfer capped at the bank's remaining balance (never overdraft); tiny residue stays in
  the bank (the documented small sink), exactly as before.

Deliberately **minimal**: this round does NOT introduce a separate deposit *rate* r_d / a loan–deposit spread
(that is the corridor system, §9 of PLAN_v10 — a later add). We only fix WHO receives the interest, not the
rate structure. Spread stays implicitly zero; the bank still retains (1−ρ) as today.

## 2. Pre-registered hypotheses (§0-ii)

| # | Hypothesis | Expected | Falsifier |
|---|---|---|---|
| H1 (correctness, ~certain) | Interest accrues to depositors ∝ deposits | high-deposit households receive proportionally more; zero-deposit households receive ~0 | equal receipts |
| H2 (the real question) | Routing interest to savers **weakens the low-branch expansion** → the hump flattens toward conventional (monotone-contractionary) | rate–output relation less humped than v10 | unchanged hump |
| H3 (honest caveat) | H2 may PARTLY FAIL because MPC is **uniform** (α₁=0.8): savers spend the interest income at 0.8 too, so the aggregate injection may be similar | if H2 weak ⇒ the missing piece is **MPC heterogeneity** (savers save more), a candidate v10.2 | — |

**Pre-registration:** the fix is correct regardless of H2. If deposit-proportional alone does NOT restore
conventional transmission, that is a clean, reportable result pointing at MPC heterogeneity as the next lever —
NOT a reason to keep the wrong equal-split.

## 3. Build order
1. `config`: `interest_by_deposits: bool = False`; `Config.v101()`.
2. `economy._phase4_5_debt_service`: branch the redistribution block — proportional-to-deposits when on,
   equal-split (unchanged) when off; float-safe capping.
3. `tests/test_v101_deposit_interest.py`: off ⇒ bit-identical; A5 + shares conserve; a high-deposit household
   receives strictly more than a low-deposit one (H1); re-check the rate sweep shape (H2, as a soft check).
4. Re-run the rate diagnostic (v10.1 vs v10) — does the low branch flatten?
5. DESIGNDOC §33 (v10 + v10.1 together): the CB, the hump diagnosis, the equal-split defect, this fix, the
   re-test verdict. Full regression.
