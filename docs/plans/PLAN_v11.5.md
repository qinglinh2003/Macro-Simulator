# PLAN v11.5 — bank DEMOGRAPHICS & OWNERSHIP: entry (de novo) + equity-ification + runs

The gap the user spotted: banks currently only **die** (insolvency → dead → borrowers migrate to survivors),
never **born** — so the count decays monotonically toward oligopoly. v11.5 gives banks the same **entry/exit +
ownership** structure firms already have (v4 + v8.5): banks are **founded by owners** (de novo), **owned** (their
profit is a dividend to shareholders, not a payout to depositors), and can die from a **run** as well as from
write-offs — with owners bearing first loss and new entrants replacing the dead. It completes the firm↔bank symmetry.

Discipline as always: opt-in flags ⇒ prior versions **bit-identical**; A5 + reserve conservation hard-gated;
params anchored; emergent results **reported, not tuned**; parallelize sweeps. **Per-version diagnostic plot.**

---

## Honest up-front: what's fully active vs partly gated (the v11.4 lesson)

- **Entry (de novo) + equity-ification: FULLY ACTIVE.** They need no reserve scarcity — pure demographics +
  ownership. They will visibly change bank count, concentration, and the wealth distribution.
- **Runs: PARTLY active now.** The **panic-flight + contagion** dimension (depositors flee a weak bank →
  accelerates its failure, panic spreads) works in our ample-reserves economy. The pure **solvent-but-illiquid
  death** (a healthy bank killed purely by a liquidity wall) is **bond-gated** — with reserves hyper-abundant
  (§37) a fleeing bank can always source interbank reserves, so it shrinks/pays a funding cost rather than
  hitting a wall. So runs here = a **panic/solvency-acceleration** mechanism; its full liquidity-crisis form
  arrives with the bond layer. (Decision point below: build panic-flight runs now, or defer full runs to post-bonds.)

## A flagged ECONOMIC change (not just plumbing): who gets bank profit

Today the capital-ratio payout distributes bank profit to **depositors** ∝ deposits (`interest_by_deposits` — the
channel that recirculates loan interest broadly back to households, §33). **Equity-ification redirects it to bank
OWNERS** (a concentrated founder class) as **dividends**. So bank interest income turns from a **broad
recirculation** into a **concentrated owner-income stream** → a new **wealth-concentration channel** (bank profits
make owners richer). This is realistic (bank profits accrue to shareholders) but a genuine distributional shift —
a finding to seek + report, not a silent change. (Depositors then earn only the deposit rate, which is the
deposit-competition lever — off by default, §37.)

---

## CONFIRMED DECISIONS (from discussion)
- **Bank stock SECONDARY MARKET: YES** — banks get tradeable shares, a price, valuation, bubbles/crashes.
- **Bank profit → SHAREHOLDERS in full** (depositors get only the deposit rate, off by default). The
  wealth-concentration channel is embraced + reported.
- **Run health signal = BOTH candidates, blended**: the **market signal** (bank share price / valuation, the
  2008-style "stock crashes → run") AND the **book signal** (capital ratio = distance to insolvency). Depositors
  flee on a blend so a market crash OR a capital hole triggers flight.
- **Runs built now** — the queuing mechanism (below) is implemented; its panic/contagion/acceleration half is
  active, its liquidity-suspension half is latent (needs fractional reserves: thick credit / the bond layer).

## Stage A — bank EQUITY-IFICATION + a SECONDARY bank-stock market (the ownership foundation)
Sub-staged so A5 gates at each; reuses the v6.1 per-firm-equity *concepts* (a separate, bank-specific market).
- **A1 — ownership + dividends + valuation (no trading):**
  - Each bank gets `shares_outstanding`, `share_price`, and **owners** (`{household_id → shares}`). Genesis banks
    vest in a **founder class** (reuse v8.5 `genesis_founder_pool`).
  - **Valuation (mark-to-model):** `share_price = (bank net worth + smoothed-earnings premium) / shares` — a price
    that moves with bank capital & profit (the run's market signal), no trading yet.
  - **Dividends:** the capital-ratio `payable` goes to **owners** pro-rata to shares (was: depositors). A5-safe.
  - **Bank equity in wealth:** owner stake = shares·price → household wealth (metrics + wealth-tax base). On
    **failure**: price → 0, owners wiped (first-loss); residual negative beyond equity still cascades to interbank
    creditors (v11.4).
  - Config: `bank_equity: bool = False`. Off ⇒ depositor payout ⇒ **bit-identical**.
- **A2 — trading (the secondary market):** households hold a target bank-equity share and rebalance; the price
  **gropes** on excess demand (reuse the v6 groping), so bank stocks can bubble/crash. A crash is then a run
  trigger (Stage C). Config: `bank_equity_trading: bool = False` (⇒ A1 mark-to-model only, bit-identical when off).

## Stage B — bank ENTRY (de novo), profit-driven
- **Trigger (procyclical, like real de novo + v4 firm entry):** when the banking sector's **return on equity**
  (Σ interest income / Σ capital) exceeds a hurdle (≈ policy rate + a margin), entry is attractive → spawn up to
  `bank_entry_max` entrants/tick (damped).
- **Founder:** a random household that can afford `bank_min_capital` (a regulatory minimum). It **transfers**
  that capital to the new bank (conserved) and **owns it 100%** (Stage A). With v11.4 on, move the founder's
  reserve backing to the new bank's reserve node (keeps R_k = cap+dep−loans exact).
- **The entrant:** fresh id, a drawn κ, and a **competitive (low) loan-rate spread** so it can actually break in
  and win borrowers via v11.3 shopping (like firm entrants starting small/cheap — else a high random spread makes
  it stillborn). Starts with no book; grows by competing.
- Config: `bank_dynamics: bool = False`, `bank_min_capital`, `bank_entry_beta` (sensitivity), `bank_entry_max`.
  Off ⇒ **bit-identical** (fixed n_banks).
- **Result to seek:** bank count stabilises (entry balances exit) instead of decaying to oligopoly; entrants
  discipline concentration (a reverse force to v11.3's competition→concentration).

## Stage C — bank RUNS: queuing + panic-flight (liquidity-suspension latent)
- **Health signal (blended):** `health_k = w·(share_price_k / recent_peak) + (1−w)·(capital_k / loan_book_k)` —
  a **market** term (a stock crash relative to its own peak) + a **book** term (capital ratio). Either a crash or
  a capital hole lowers health.
- **Flight rule:** pure depositors at bank k flee with intensity rising as health falls (a logistic on the
  health gap), amplified by a system **`fear`** level (raised by recent failures/run volume, decays over time —
  the panic/contagion channel, fully active regardless of reserve scarcity).
- **The QUEUE (sequential service from own reserves):** a run is executed as a **sequential rationing loop**
  (idiomatic — like `_phase2_labor`): the fleeing depositors are queued (shuffled); each withdrawal ships reserves
  bk→(healthiest other bank) via `move_reserves` and moves the deposit relationship; the bank pays from **its own
  reserves only** (loans are illiquid) with the **interbank market FROZEN** (no one funds a bank being run). When
  reserves hit the floor, the bank **SUSPENDS** — the queue tail is frozen — and fails from **illiquidity**. This
  is exactly the v11.4 Stage-3 intra-tick RTGS blocking, now with a driver to fire.
- **Honest scope (the recurring structural fact):** suspension bites only if the bank is **fractionally reserved**
  (R_k = capital + deposits − loans < deposits ⟺ loans ≳ deposits). Our credit is thin (loans ≪ deposits) ⇒
  R_k ≈ deposits ⇒ nearly fully reserved ⇒ the queue rarely exhausts reserves ⇒ the **liquidity-suspension is
  latent** (awaits thick credit / the bond layer). The **panic-flight + contagion + acceleration of already-weak
  banks** is active NOW. Reported, not tuned.
- Config: `bank_runs: bool = False`, `run_sensitivity`, `run_health_ref`, `run_market_weight` (w),
  `run_fear_persistence`. Off ⇒ **bit-identical**.

---

## Metrics / tests / diagnostic
- Metrics: `n_banks_alive` over time, `bank_births`, `bank_deaths`, `bank_entry_roe`, `bank_equity_gini`
  (ownership concentration), `bank_deposit_flight` (run intensity), + reuse v11.3/v11.4 concentration metrics.
- `tests/test_v115_bank_demographics.py`: each flag off ⇒ prior bit-identical; A5 + reserve conservation hold
  through entry, dividends, and runs/failures; entry stabilises the bank count (vs monotonic decay); dividends
  reach owners (equity Gini > 0); a run drains a weak bank's deposits (flight observable).
- `plot_v115.py → diagnostic_v115.png` with a bank-demographics row (count/births/deaths, ownership Gini, flight).

## Build order & gates
A (equity) → B (entry, needs ownership) → C (runs). A5 + reserve-conservation gate at each; regression green at
each; report the distributional shift from A and the count-stabilisation from B honestly.

## Build order (all decisions confirmed)
A1 (bank equity ownership + dividends + valuation) → A2 (trading market) → B (entry) → C (runs: queue + panic).
A5 + reserve-conservation gated at each sub-stage; full regression green at each; each flag off ⇒ bit-identical.
Report honestly: the wealth-concentration shift (A), the count-stabilisation (B), and which half of runs is
active vs latent (C). Ship `test_v115_bank_demographics.py` + `plot_v115.py → diagnostic_v115.png` (§38).
