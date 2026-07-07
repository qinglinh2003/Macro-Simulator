# Implementation plan — v6.1 (capital-market deepening: per-firm equity)

> **Status: engineering plan, staged. Not started.** Turns the v6 aggregate index into a real
> per-firm stock market. Gated by `per_firm_equity` (off ⇒ v6 aggregate, bit-identical). The four
> deliverables the user named all land, in two stages that isolate the one dangerous new force
> (financial→real feedback) from the safe one (distribution).

## 0. What v6 lacks, and what v6.1 adds (the four)

v6 = one blended index + a side-pot (no feedback to production). v6.1 makes it a real market:

1. **Per-firm equity** — each firm has its own shares and price (not one blended price).
2. **Founder ownership** — the household that funds a startup (v4 entry) receives its shares
   (not an equal genesis hand-out to everyone).
3. **Earnings-based valuation** — value reflects profitability, not just net assets (book).
4. **q-driven investment** — a highly-valued firm actually invests more: the market steers the
   real economy (the one channel v6 deliberately lacked).

## 1. Staging (isolate the risk)

- **v6.1a — distribution only (SAFE).** Items 1–3. The market is still a side-pot (no q-investment,
  wealth effect stays off), so production is untouched → stable. Question it answers: does
  **founder ownership + capital gains** produce the **T8 wealth tail** (and maybe **T6** firm-size
  tail) — the multiplicative mechanism §15/§16 said was missing — *without* the endogenous-MPC
  thrift-paradox cost?
- **v6.1b — real feedback (DANGEROUS).** Item 4. q enters investment. This is the SECOND
  financial→real channel (the first, the consumption wealth effect, caused depression in v6), so it
  goes in alone, as a small multiplier, wealth effect still off. Question: does asset-price-driven
  investment produce a boom-bust / the 1929-2008 real-crisis seed?
- **v6.2 (deferred):** equity *finance* of investment (firms issue shares to fund capex) — a
  stronger financial→real loop; out of scope here.

## 2. Data model (agents.py, ledger.py)

| where | change |
|---|---|
| `Firm` | per-firm equity state: `shares_outstanding`, `share_price`, `share_last_price`, `share_trend`, `equity_fundamental`, `residual_income_ema` (for valuation). No new money on the firm. |
| `Household` | `holdings: dict[firm_id → shares]` (SPARSE); `watchlist: list[firm_id]` (the k firms it actively trades — always includes any firm it founded). Replaces v6's scalar `shares`. |
| `ledger` | **no new instrument** — share trades are deposit transfers (money conserves via `transfer`, as in v6). |

**Scale — sparse portfolios (the key engineering choice).** Dense per-firm holdings are
O(N_H·N_F) = 400k. Instead each household actively trades a **watchlist of k firms** (k~10–20,
random at creation + its own firm), so cost is O(N_H·k). Realistic (nobody holds every stock) and
tractable. Firms with few watchers → thin price discovery, held near book by the fundamentalist
anchor (§4).

## 3. Founder ownership + lifecycle (item 2)

- **Genesis firms:** `shares_outstanding` split across households (equal, or on watchlists).
- **Entrant firms (v4 birth):** the **funding household receives ALL** the new firm's shares, and
  the firm is added to its watchlist. Ownership now tracks entrepreneurship.
- **Bankruptcy (v4 death):** the firm's shares are **wiped** from every holder (equity → 0). No
  money moves (equity isn't money), so A5 is untouched; holders bear the loss. Remove the firm from
  all watchlists/holdings.
- **The inequality loop (why this fixes T8 multiplicatively):** wealthy households can fund more
  startups (`_pick_funder` favours those who can afford) → own more equity → firms appreciate →
  wealthier → fund even more. A compounding, capital-gains-driven wealth spread — *without* the
  aggregate-demand cost of the endogenous-MPC route.

## 4. Valuation — floored residual income (item 3, robust; NOT raw Gordon)

Per firm, the fundamental is book PLUS a growth premium only for firms earning above the cost of
capital r:
$$\text{fundamental}_f=\text{book}_f+\frac{\max\!\big(0,\ \text{ema}(\pi_f-r\cdot\text{book}_f)\big)}{r},\qquad \text{book}_f=D_f-L_f+K_f.$$
Book is a floor (never collapses — the failure mode of the raw dividend/r Gordon anchor, which v6
already hit); r is the discount base (so the capital market couples to the interest rate as intended);
ROE=r ⇒ q=1, ROE>r ⇒ q>1 emerges endogenously. `r≈0` ⇒ falls back to book/share.

## 5. Per-firm market clearing (item 1) — same primitive as v6, per firm

For each firm, over its watchers: fundamentalist `w_f·(fundamental_f−p_f)/p_f` + chartist
`w_c·trend_f` → notional Δshares; **pro-rata ration** the long side (money via CLEARING, shares
matched) → **grope** `p_f ← p_f·(1+λ_p·excess_f)`; update `trend_f`. Both conservations hold per
firm. Households allocate `theta_equity` of wealth across their watchlist (split by attractiveness).

## 6. q-driven investment (item 4, v6.1b) — a MULTIPLIER, not a replacement

`q_f = market_cap_f / book_f = shares_f·p_f / book_f`. B5 becomes:
$$I^{*}_f=\underbrace{\big[\lambda_I(K^{*}-K_{t-1})+\delta_K K_{t-1}\big]}_{\text{v2 accelerator}}\times\ g(q_f),\quad g(q)=\text{clip}(1+\lambda_q(q_f-1),\ g_{\min},\ g_{\max}).$$
q>1 amplifies, q<1 damps. `λ_q` **small** by default; the accelerator still anchors investment, q
only tilts it. This is the single new financial→real link — turned on alone, wealth effect off.

## 7. Conservation

- **A5 (money) untouched** — share trades are deposit transfers.
- **Per-firm share conservation** (new gate): for every firm, `Σ_h holdings_h[f] == shares_outstanding_f`.
- Bankruptcy wipes shares (no money) → both invariants safe.

## 8. Config (parameter budget)

`per_firm_equity: bool=False` (master; off ⇒ v6 aggregate, bit-identical) · `watchlist_size:int`
· `lambda_q` (q→investment sensitivity, small) + `q_invest_floor/cap` · `resid_income_lambda`
(valuation ema speed). Reuse `w_chartist, w_fundamental, theta_equity, lambda_p, trend_lambda`.
`Config.v61a()` = v6 core + per_firm_equity, λ_q=0 (side-pot); `Config.v61b()` = + λ_q>0.

## 9. Metrics

Per-firm-equity block: `equity_market_cap_total`, `tobin_q_mean` / `tobin_q_dispersion`,
`share_price_dispersion`, `equity_ownership_gini` (concentration of who owns equity),
`hh_wealth_gini_incl_equity` (T8, now per-firm), `investment_q_corr` (v6.1b: does investment track
q?), `n_firms_q_above_1`. Plus a per-firm-price diagnostic panel.

## 10. Tests (tests/test_v61_per_firm_equity.py)

1. **Regression** — `per_firm_equity=False` ⇒ v6 bit-identical (full suite green).
2. **Per-firm share conservation** — Σ holdings == shares_outstanding, every firm, every tick.
3. **Money A5** — through per-firm trading and a bankruptcy (equity wiped, money intact).
4. **Founder ownership** — at a birth, the funder's holdings jump by the new firm's float; a
   non-funder's don't.
5. **Valuation** — a high-ROE firm gets fundamental > book (q>1); a break-even firm ⇒ q≈1.
6. **q-investment (v6.1b)** — high-q firms invest more than low-q firms (positive investment–q corr).
7. **T8 direction (v6.1a)** — founder ownership + capital gains raise wealth Gini / right-skew vs v6
   (equity concentrates), WITHOUT depressing output (contrast the endogenous-MPC thrift cost).

## 11. Milestones / acceptance (conservative)

- **v6.1a:** regression green; per-firm share + money conservation (incl. through bankruptcy);
  founder ownership works; residual-income valuation gives q>1 for profitable firms; **T8 improves
  via capital gains at NO output cost** (the clean multiplicative-inequality result); system stable
  and bounded.
- **v6.1b:** q-driven investment live and bounded; investment tracks q; observe (bonus) whether
  asset-price swings drive an investment boom-bust (financial→real). Full crisis chain (needs
  multi-bank contagion) stays out.

## 12. Open decisions to confirm before coding
1. **Sparse watchlists** (k firms/household) vs dense holdings — recommend sparse.
2. **q as accelerator multiplier, small λ_q** vs q replacing the accelerator — recommend multiplier.
3. **Floored residual-income valuation** vs raw Gordon dividend/r — recommend residual income.
4. **Wealth effect stays OFF** through v6.1 — recommend yes (isolate q as the only new channel).
5. **Equity finance of investment** → v6.2, not here — recommend defer.
