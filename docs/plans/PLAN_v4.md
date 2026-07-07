# Implementation plan — v4 (firm entry/exit + bankruptcy)

The cross-cutting mechanism the last three findings converged on: it clears zombies (unfreezes
credit), and — via profit-driven entry — competes down monopoly *profit* (structure may persist;
that would isolate the "increasing-returns" root for a later scale-cap). Builds on v3 (needs the
bank for bad-debt writeoff). Opt-in behind a flag; v1/v2/v3 remain regression guards.

**Scope of v1 (deliberately narrow, one sector):** entry/exit acts on **C-firms only** — the
winner-take-all and the zombies are in the consumption sector, and C-firms have capital so the
profit/capital signal is well-defined. K-sector demographics are v4.1.

---

## 0. The two endogenous forces (both anchored, not fiat)

- **Exit (death) = financial insolvency, sustained.** A C-firm with financial net worth
  `D − L < 0` (deposits minus debt) for `bankrupt_persist` consecutive ticks goes bankrupt. Uses
  the *financial* NW (matches B7; no capital valuation), and the persistence requirement doubles
  as the zombie-cleanup (a persistently insolvent firm = a zombie). Capital is scrapped on death.
- **Entry = profit above the interest rate.** When incumbent profitable C-firms earn a return
  (`profit / capital`, median over profitable firms) above the hurdle `r` (the interest rate =
  the economy's cost of capital / normal profit), new firms enter at a damped, capped rate. This
  is the "excess profit competed away" mechanism; r reuses an existing parameter (no new dial) and
  previews monetary transmission (higher r ⇒ higher entry hurdle ⇒ less entry).

Entry responds to profit, exit to solvency — so **firm count becomes an emergent quantity**, not
a fiat constant.

---

## 1. The accounting core — bad-debt writeoff conserves A5 (the crux)

An insolvent firm owes Λ it can't pay; that money was long since spent into households. Cancelling
the debt alone would raise net worth by Λ (A5 break). The conserving operation, a new ledger
primitive:

```
write_off(borrower, bank, Λ):   loans[borrower] -= Λ ;  deposits[bank] -= Λ    (together)
```
`ΣL` falls by Λ (net worth +Λ) and `ΣD` falls by Λ (net worth −Λ) → **net worth invariant (A5)**.
Economics: the money stays in households (broad money doesn't shrink); the **bank's equity absorbs
the loss**. A default is thus a net-worth *redistribution* bank→households, conserved exactly.

**Consequence — the bank needs genesis capital.** The bank's equity ≈ its deposits (retained
interest + initial). Writeoffs deplete it; if it hits zero the bank is insolvent. So the bank gets
a genesis capital endowment `d_bank0 > 0` (carved from M) as a loss-absorbing buffer. When its
deposits go **negative**, the bank is insolvent = a systemic credit crisis (single bank!) — we
**allow the negative balance and observe it**, not halt (it is a real state, not a bug). So the
bank account is exempt from the A4 non-negativity gate.

**Bankruptcy sequence (per dead firm), all A5-safe:**
1. `repay(firm, min(D, L))` — firm repays from cash (destroys money + debt; standard). Since
   `D < L` at death, this zeroes deposits and leaves `bad = L − D`.
2. `write_off(firm, bank, bad)` — bank equity absorbs the rest. `_writeoffs += bad`.
3. Scrap capital (real, not money — just drop it; uses the v2 real-vs-money distinction, no A5
   effect).
4. Remove the firm from the agent lists + its (now 0/0) ledger account.

---

## 2. Entry — funded by households, conserving

A new C-firm needs startup deposits (first wage bill) and initial capital (K>0 for Cobb-Douglas):
- **Deposits: transferred from a household** (`transfer(funder, new_firm, startup_deposits)`) —
  conserves money, and adds a household→firm→(wages)→household reflux channel. If no household can
  afford it, no entry that tick (entry is wealth-constrained — realistic).
- **Capital: a minimal initial stock created from nothing** (`startup_capital`). Capital is a real
  outside asset (not conserved — K-firms produce it, depreciation destroys it; genesis C-firms
  also start with K_firm0 from nothing), so this does **not** touch A5. (Cleaner "buy capital
  first" is a v4.1 refinement.)
- Unique id from a global counter (never reuse indices); cold-start seeded like a genesis C-firm.

**Entry rate (damped + capped, like λ_I for the accelerator):**
```
rates   = [f.profit / f.capital for f in c_firms if f.profit>0 and f.capital>0]
pr      = median(rates)               # incumbent profitable return (avoid zombie drag)
excess  = max(0, pr − r)
n_enter = min(entry_max, round(entry_beta * excess * len(c_firms)))
```
Conservative first: modest `entry_beta`, small `entry_max`, so entry can't overshoot into a
violent entry–shakeout cycle. Tune up only after it's shown stable.

---

## 3. Module-by-module

| module | change |
|---|---|
| `ledger.py` | `write_off(borrower, bank, amt)`; `add_account(id, dep=0)`; `remove_account(id)` (only if 0/0); a `_may_be_negative` set (the bank) exempt from `assert_non_negative`. |
| `config.py` | `firm_dynamics: bool`; `bankrupt_persist`, `entry_beta`, `entry_max`, `startup_deposits`, `startup_capital`; raise `d_bank0` (bank genesis capital). `Config.v4()`. |
| `agents.py` | `Firm.insolvent_ticks: int` (persistence counter). |
| `economy.py` | **Phase 4.7 — demographics** (after debt service, before the A5 check): update insolvency counters → bankrupt the dead → profit-driven entry. Dynamic `c_firms/firms/investing_firms`; global id counter; funder selection. Bank exempt from non-neg check. |
| `metrics.py` | firm_count, births, deaths, writeoffs (tick + cumulative), bank_equity (bank deposits), bank_insolvent flag. |
| tests | `write_off` conserves A5 + drives bank negative; a v4 run: A5 holds, zombies get cleared (no persistent D−L<0 firms), firm count stays bounded (not 0, not exploding); regression v1/v2/v3 green. |
| `run_v4.py` | v4 run + dashboard (firm count, births/deaths, bank equity, concentration) + the key readouts (are zombies gone? is monopoly *profit* competed down? is the bank solvent?). |

---

## 4. Build order (ledger-first)

1. `ledger`: `write_off` + `add_account`/`remove_account` + bank-negative exemption → unit tests
   (writeoff conserves A5; bank can go negative; add/remove don't break sums) + **v1/v2/v3
   regression green**.
2. `config` + `agents` (params, bank capital, insolvent_ticks).
3. `economy` Phase 4.7 (death → writeoff → entry; dynamic lists; ids).
4. `metrics` + `run_v4` + tests.

---

## 5. Conservation checkpoints (most bug-prone — be meticulous)

- New-firm startup deposits come from a **transfer** (household), never created (A5/M0).
- Bad debt cancelled only via `write_off` (borrower debt ↓ = bank deposits ↓); never a bare
  `loans -= x`.
- Scrapped capital removed from the real capital stock, but **not** from any money sum (capital
  isn't money).
- Firm-list add/remove: every per-firm loop and `c_firms/firms/investing_firms` stays consistent;
  no stale references; the ledger account for a removed firm is 0/0 before removal.
- The A5 gate `ΣD − ΣL = M` must hold every tick *including* through births, deaths, and writeoffs.

---

## 6. Acceptance (conservative — this is diagnostic, per the honest expectation)

v4 "done" is **not** "monopoly cured". It is:
1. **A5 holds** every tick (incl. writeoffs) to machine precision; bank insolvency (if any) is a
   recorded state, not a halt.
2. **Zombies cleared / credit unfrozen** — no firms sit persistently insolvent; the v3
   credit-freeze symptom is gone (borrowing/service no longer stuck at a frozen ΣL).
3. **Firm count is dynamically stable** — bounded away from 0 and from explosion; entry↔exit reach
   a balance.
4. (Watch, not gate) **Incumbent excess profit is competed toward r** — even if share-concentration
   persists (that would pin "increasing returns / scale cap" as the last piece).

Expected first-run caveat: entry is positive feedback; may show entry–shakeout oscillation or, if
the bank's buffer is too thin, early bank insolvency. Both are calibration (`entry_beta/max`,
`d_bank0`), not plumbing — as long as A5 holds.
