# Implementation plan — v7 (household credit: debt-financed consumption)

> **Status: engineering plan. Not started.** The layer earned by the whole v6 family + the
> MPC thread: the stock market can't recycle savings into demand (§19), and endogenous MPC makes
> inequality only by depressing demand (thrift paradox, §16.7). **Household credit is the missing
> recirculation channel** — the rich's savings are *lent to* households who spend, so demand
> survives even as wealth concentrates. It is the one mechanism that can deliver the
> "**rich + poor + prosperous**" cell no prior config reached — and it plants the 2008 seed.

## 0. The thesis (why this layer, in one line)

Every inequality mechanism so far leaked the rich's savings *out* of the demand stream (drain §9;
thrift paradox §16.7). Real prosperous-unequal economies keep it circulating via **financial
intermediation**: savers hold deposits/claims, the bank lends to households who spend, demand holds
up, and inequality shows on the **balance sheet** (rich +net-worth, poor −net-worth) rather than as
a demand collapse. v7 builds exactly this — extending the v3 firm-credit machinery (B6/B7, loans
create deposits, debt service, writeoff) to **households**.

## 1. Scope & staging

- **v7a — borrow to consume (the payoff).** Households borrow to fund a consumption shortfall,
  service the debt, no default (deferred shortfalls, as v3 did for firms). Question it answers: does
  household credit **dissolve the thrift paradox** — keep unemployment low WHILE net-worth inequality
  is high (the "rich + poor + prosperous" cell)?
- **v7b — default & deleveraging (the crisis).** Insolvent households default (writeoff, bank equity
  absorbs), and debt limits tighten procyclically → a **household Minsky / 2008** boom-bust. Staged
  after v7a so the prosperity result is isolated from the crisis dynamics.

## 2. The mechanism (mirror B6/B7 to the household side)

- **Household credit DEMAND (B8).** A household borrows to cover the gap between its planned
  consumption (B1) and its cash: `borrow = max(0, consumption_budget − deposits)`, capped by the
  credit limit (below). So the *drained / high-MPC* households borrow (they have the gap); savers
  don't. This is what sustains demand.
- **Household credit SUPPLY (B9) — debt-to-income limit.** `L_h ≤ φ · Y^e_h` (borrow up to φ×
  expected income). Income-based (households have no collateral yet), and **procyclical by
  construction**: when income falls, the limit tightens → forced deleveraging (the Minsky/2008
  mechanism, for free). Grant `min(demand, φ·Y^e_h − L_h)`.
- **Household debt service.** Amortize a fixed fraction + pay interest r from income, cash-capped;
  shortfalls defer (v7a). Reuses `debt_service_amounts`.
- **Loans create deposits (M2).** `create_loan(h, amount)` → the household's deposits and debt both
  rise; it then spends in the goods market. Reuses the v3 primitive — A5-safe.

## 3. Data model & tick placement

No new ledger instrument — household loans reuse `create_loan` / `repay` / `write_off` (the debt
side of the ledger already keys on any agent id). `Household` gains only bookkeeping scratch
(`credit_new`, `debt_service`). Slots into existing phases:

```
Phase 1     plan (B1 consumption budget)
Phase 1.5   credit  — ADD household borrowing (B8/B9) alongside firm credit; loans create deposits
Phase 2/3   labor, goods — households now spend the borrowed deposits (demand sustained)
Phase 4.5   debt service — ADD household amortization + interest alongside firms
Phase 4.7   demographics — (v7b) ADD household default/writeoff alongside firm bankruptcy
```

## 4. Why this gives "rich + poor + prosperous" (and dissolves the thrift paradox)

Pair v7 with heterogeneous saving (exogenous `mpc_dispersion` or, better, endogenous
`mpc_wealth_curvature`):
- **high-MPC / drained households** hit a consumption gap → **borrow** → spend → demand holds up;
- **low-MPC savers** accumulate **deposits** (the claims the loans are funded against);
- net worth **diverges** — savers positive, borrowers negative — a **balance-sheet inequality** that
  does **not** require a demand collapse.

This is precisely the recirculation the thrift paradox lacked: the savers' money, instead of leaking
out of the demand stream, is **lent to the spenders and spent**. The prediction to test: endogenous
MPC **without** credit depresses (u↑, §16.7); endogenous MPC **with** v7 stays prosperous (u low)
while net-worth Gini is high. If so, v7 delivers the cell that has eluded every prior layer.

## 5. Conservation

- **A5 untouched** — household loans use the same create/repay/writeoff primitives as firms; ΣD−ΣL=M
  holds through borrowing, service, and (v7b) default.
- Household debt can exceed deposits ⇒ **negative net worth** is now normal for borrowers; A4
  (non-negative *deposits*) still holds (you can't spend cash you don't have — borrowing raises cash
  first). Net worth, not deposits, carries the inequality.

## 6. Config (parameter budget)

`household_credit: bool=False` (master; off ⇒ v6.x bit-identical) · `hh_credit_limit` (φ,
debt-to-income multiple — THE dial) · `hh_amort` (household amortization rate) · reuse `r_interest`.
v7b: `hh_default: bool`, `hh_bankrupt_persist`. `Config.v7()` = a v3/v4 base + `household_credit`
+ heterogeneous MPC (so a saver/borrower split exists).

## 7. Metrics

- **`hh_net_worth_gini`** (deposits − debt per household) — **the headline**: the balance-sheet
  inequality that should be HIGH while u is LOW.
- `household_debt_total`, `household_credit_new`, `household_leverage` (ΣL_h / ΣY), `share_in_debt`
  (fraction with debt > 0), `debt_to_income` distribution, `consumption_credit_financed`
  (consumption funded by new borrowing).
- v7b: `household_defaults`, `household_writeoffs`.

## 8. Tests (tests/test_v7_household_credit.py)

1. **Regression** — `household_credit=False` ⇒ v6.x bit-identical.
2. **A5** — conserved through household borrowing + debt service (+ default in v7b).
3. **Loans create deposits & fund consumption** — a borrowing household's deposits rise then flow to
   goods (demand it couldn't otherwise make).
4. **Debt-to-income limit binds** — `L_h ≤ φ·Y^e_h` every household, every tick.
5. **Balance-sheet inequality** — with heterogeneous MPC + credit, `hh_net_worth_gini` >
   deposits-only Gini (borrowers go negative, savers positive).
6. **The payoff (characterisation)** — endogenous MPC + household credit keeps unemployment
   materially BELOW the same γ without credit (thrift paradox mitigated), at higher net-worth Gini.

## 9. Milestone / acceptance (conservative)

**v7a done** = regression green; A5 conserved through household credit; the debt-to-income limit
binds; loans demonstrably fund consumption; **and the payoff: a config with net-worth Gini HIGH and
unemployment LOW simultaneously** — the "rich + poor + prosperous" cell, shown against the
credit-off thrift-paradox baseline. **v7b** (bonus / next): household default + procyclical limits
produce a debt-driven boom-bust; the bank absorbs writeoffs (stress, maybe insolvency); A5 holds
through the crisis.

## 10. Open decisions to confirm before coding
1. **Income-based debt limit** (`L ≤ φ·Y^e`) vs wealth/collateral-based — recommend income-based
   (we have no household collateral; keeps it clean and procyclical).
2. **Borrow to fund the consumption-budget gap** vs a richer consumption-smoothing rule — recommend
   the simple gap rule first.
3. **Pair with endogenous MPC** (the realistic saver/spender split) as the headline `Config.v7()`,
   with exogenous `mpc_dispersion` as a control — recommend yes.
4. **Default/crisis (v7b) staged after v7a** — recommend yes (isolate the prosperity result first).
5. Same interest rate `r` for households as firms (no spread yet) — recommend yes for v7a.
