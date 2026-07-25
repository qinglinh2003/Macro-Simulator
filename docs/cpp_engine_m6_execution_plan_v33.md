# C++ Engine M6 Execution Plan

Status: executable plan  
Milestone: M6 — securities, equity, valuation, and firm lifecycle  
Base: accepted M5 commit `94b38d527f305ad0aa951e97d466b91c6376b5c5`  
Integration target: `refactor/cpp-engine-v33`  
Candidate branch: `refactor/cpp-m6-v33`

## 1. Objective

M6 extends the accepted native monetary closed economy with the financial and
firm frontier required by the latest complete playable Python engine:

- government bond contracts, issuance, coupons, maturity, and indexed holders;
- firm and bank common equity with explicit beneficial ownership;
- sparse household watchlists and batched, per-asset market clearing;
- margin-financed equity demand and household limited-liability resolution;
- priced firm statements and a one-way valuation service;
- equity-aware bank resolution and de-novo bank entry;
- firm insolvency, voluntary exit, entry, and product-sector switching;
- exact checkpoint, C ABI, Python binding, package, and performance support.

M6 does not target a historical preset or a historical model version. The
Python source files named below are semantic evidence from the current complete
engine, regardless of the version in which a mechanism first appeared.

## 2. Accepted base and non-negotiable contracts

M6 starts only from the accepted M5 SHA and preserves all M0-M5 contracts:

- generation-safe stable entity IDs and deterministic iteration order;
- canonical postings, reserves, loans, interbank contracts, central-bank
  operations, bank P&L, and bank capital;
- projection-first, validate-before-commit daily advancement;
- no Python callback from native `advance_ticks`;
- exact same-build checkpoint continuation;
- append-only C ABI evolution and isolated wheel/source-package validation;
- release, sanitizer, semantic, regression, and performance gates;
- English source, documentation, generated contracts, and commit subjects.

The M6 production target remains the latest complete playable engine.

## 3. Current semantic sources

The following current Python modules define the mechanisms to preserve:

| Domain | Current semantic source |
|---|---|
| Treasury bills and bonds | `macro_sim/systems/securities.py` |
| Firm equity market | `macro_sim/systems/equity.py` |
| Bank equity and entry | `macro_sim/systems/banking.py` |
| Priced firm statements | `macro_sim/systems/firm_balance_sheet.py` |
| Valuation | `macro_sim/systems/valuation.py` |
| Firm birth, insolvency, and exit | `macro_sim/systems/firm_demographics.py` |
| Product-sector switching | `macro_sim/systems/switching.py` |
| Financial primitives | accepted M2 and M5 native books |

Configuration fields are mapped from the current `Config` and policy schema,
not reconstructed from any old preset factory.

## 4. Scope boundary

### 4.1 Included

- Treasury-issued domestic-currency bonds held by households and banks.
- Per-lot coupon, issue tick, maturity tick, face, cost basis, and holder.
- Holder, issuer, maturity, and bank-portfolio indexes.
- Household-owned firm and bank common equity.
- Firm and bank issuer state: shares, quote, last quote, peak quote where
  relevant, fundamental, trend, residual-income or earnings signal, and
  outstanding shares.
- Deterministic genesis ownership and watchlists.
- Per-firm sparse watchlist demand and per-bank complete opportunity-set
  demand.
- Batched orders, per-asset pro-rata clearing, primary issuance, and settlement.
- Margin origination, repayment, write-off, and limited-liability bankruptcy.
- Replacement-value firm statements and borrowing-base observations.
- Firm insolvency/default, voluntary shell exit, startup funding, entry, and
  sector switching.
- Equity-dependent bank recapitalization/resolution and bank entry.
- Securities and firm-lifecycle metrics required to validate identities.
- Native checkpoint, bindings, installed SDK, distribution artifacts, and
  performance gates.

### 4.2 Deferred

- Persons, estates, inheritance, and household membership are M7. M6 ownership
  lots use `OwnerId::household`; M7 changes beneficial owners without creating
  a second mutable claim mirror.
- Energy-firm and housing-builder components are M8.
- Foreign-currency securities, external positions, and international capital
  flows are M9.
- Public release delays, complete reporting, controllers, and RL are M10.
- Native controller inference and production cutover are M11.

## 5. Canonical state design

### 5.1 Strong identifiers

Add non-interchangeable identifiers:

- `BondId`;
- `EquityId`;
- `SecurityLotId`.

IDs are append-only and never reused. An inactive contract or lot remains
addressable for replay and checkpoint diagnostics.

### 5.2 Security contracts

`SecurityBook` is the sole owner of contracts and beneficial lots.

`BondContract` contains:

- stable ID and issuer;
- issuer cash account;
- currency;
- issue and maturity ticks;
- coupon rate fixed at issuance;
- original and outstanding face;
- active and settled flags.

`EquityContract` contains:

- stable ID and issuer kind/ID;
- issuer cash account;
- currency;
- outstanding shares;
- current, prior, and peak quote;
- fundamental, trend, and residual-income/earnings signal;
- active and resolved flags.

`SecurityLot` contains:

- stable ID;
- security kind and contract ID;
- beneficial `OwnerId`;
- units;
- nominal cost basis;
- active flag.

Bond face and equity shares are never stored in a second household or bank
mirror.

### 5.3 Indexes

The book maintains deterministic compact indexes:

- holder → active lots;
- bond issuer → active contracts/lots;
- maturity tick → active bond contracts;
- bank holder → active bond lots;
- security → active lots.

Every mutation increments one version and updates all affected indexes before
it can become observable. Index order is stable lot-ID order. No accepted
economic result may depend on hash-table iteration.

`validate_indexes()` rebuilds an independent reference view and compares every
index. A fuzz test applies issue, transfer, split, merge, redeem, and retire
operations and validates after every mutation.

### 5.4 Ownership compatibility

The M2 `OwnershipBook` remains valid for generic fractional claims. M6 applies
the same generic `OwnerId` semantics to security lots, because traded securities
need units and cost basis rather than normalized fractions only. There is one
beneficial lot authority for each security. Household/person summary views are
derived consumers.

### 5.5 Firm issuer and statement state

Firm common columns gain only the issuer and lifecycle fields used every day.
M6 runtime records hold the richer statement:

- cash;
- loan principal and unpaid interest;
- productive capital units and replacement value;
- finished inventory and work-in-progress value;
- input inventory value when present;
- gross assets;
- book common equity;
- eligible collateral and borrowing-base proxy;
- current earnings and residual-income EMA;
- insolvency persistence, shell age, switch pressure, and consumption stratum.

The statement is a read-only valuation view. Revaluation creates no cash,
deposit, loan, reserve, or P&L posting.

## 6. Atomic tick integration

M5 receives an internal native extension seam; existing M5 callers use a
no-op hook and remain behaviorally unchanged. M6 supplies a hook that runs
inside the same M4 projection/validation/commit transaction:

1. `E0/E1`: M5 opens fiscal and financial books.
2. `E2`: M6 pays bond coupons and matures due contracts in projection.
3. `E4`: M5 plans and grants ordinary credit; M6 captures opening valuation
   and bounded watchlist demand inputs.
4. `E5/E6`: M4 production/trade and M5 debt/fiscal settlement run unchanged.
5. `E7a`: M6 closes firm statements and generates equity orders.
6. `E7b`: M6 clears firm and bank equity by stable asset ID and posts one
   balanced batch.
7. `E7c`: margin calls and household bankruptcy settle.
8. `E7d`: firm default/exit, sector switch, firm entry, equity-aware bank
   resolution/entry, and bond issuance are staged.
9. `E8`: M5 and M6 validate postings, loans, capital, securities, ownership,
   statements, and lifecycle projections.
10. `E9`: the base economy, M5 books, M6 book/runtime, and staged entity
    commands commit as one accepted day.

If any phase fails, no M6 persistent book, runtime, entity lifecycle, or quote
changes. The M5 runtime rollback contract remains intact.

## 7. Bond semantics

### 7.1 Pricing

For remaining tenor `n`, required return `r`, coupon `c`, and face `F`:

```text
P = F / (1+r)^n + cF * (1 - (1+r)^(-n)) / r
```

The `r≈0`, mature, invalid-negative-rate, and one-period zero-coupon par paths
are explicit and finite. Coupons are cohort terms stored on each contract.

### 7.2 Maturity and coupons

At E2:

- pay coupon once for each active due-period contract;
- credit bank coupon income to the projected bank journal;
- redeem matured household bonds from Treasury cash;
- redeem bank bonds through the Treasury/reserve settlement path;
- reduce outstanding face and retire lots/contracts exactly once.

### 7.3 Issuance

At E7, target bond financing is:

```text
target face = bond_finance_fraction * max(0, government debt)
issuance gap = max(0, target face - current outstanding face)
```

Household demand uses available deposits, expected-income liquidity buffers,
and the configured target bond share. Bank demand uses reserve headroom,
appetite, capital, and duration limits. Allocation preserves stable household
then bank order. Every purchase is a balanced cash/reserve transaction and one
lot issuance.

Maturity bucketing is a contract field. Consolidation merges only economically
fungible lots with equal holder, contract terms, and maturity; it cannot change
face, cost, market value, or holder totals.

## 8. Equity and valuation semantics

### 8.1 Genesis

- Each eligible firm and bank receives a stable equity contract.
- Shares are distributed either to deterministic sampled founders or across
  watchers according to current configuration.
- Firm watchlists are generated from a named counter RNG stream and bounded by
  `W`; reverse issuer watcher indexes are built once.
- Bank equity keeps the complete alive-bank opportunity set.

### 8.2 Firm fundamental

The required per-tick discount rate is:

```text
max(valuation floor, max(0, policy rate) + valuation risk premium)
```

Firm fundamental value is limited-liability book value plus a perpetuity of
positive residual income, divided by shares. A negative common-equity value
cannot create a negative quote.

### 8.3 Order generation

Households target an equity share of net worth. Firm attractiveness combines
fundamental mispricing and chartist trend. Only the bounded watchlist is
traversed for firm equity; every alive bank remains eligible for bank equity.

Orders are emitted into reusable contiguous arrays:

```text
(asset, side, owner, quantity, limit cash, stable ordinal)
```

No trade callback mutates household claims one order at a time.

### 8.4 Clearing

For each asset in stable ID order:

- aggregate buy, secondary sell, and permitted primary issue;
- execute `min(buy, sell + issue)`;
- allocate pro rata in stable order;
- post buyer cash to clearing, seller proceeds from clearing, and residual
  primary proceeds to the issuer;
- apply all lot deltas as one balanced security batch;
- update volume, excess demand, quote, trend, and issuer shares.

The clearing account must end at zero within accounting tolerance.

### 8.5 Margin

When enabled:

- target leverage respects `margin_max`;
- new margin principal respects `margin_ltv`, household credit limits, bank
  capacity, and available cash;
- calls repay principal from deposits;
- an insolvent household pays available cash, writes off remaining margin
  principal once, retires its margin memo, and preserves the canonical loan
  authority.

## 9. Firm statements and lifecycle

### 9.1 Priced statement

Capital uses the last committed replacement-capital price. Output inventory
uses the lower of posted realizable price and observable replacement unit cost.
Debt is canonical loan principal. Interest arrears remain a separate memo
liability. Collateral haircuts affect borrowing capacity but never default
recovery unless a later explicit contract says so.

### 9.2 Insolvency and voluntary exit

A firm exits when the configured insolvency persistence or shell rule binds.
The staged resolution:

1. repays principal from available cash;
2. writes off remaining principal against the lender once;
3. distributes a solvent voluntary-exit residual pro rata to owners, while an
   insolvent resolution follows the configured bank/Treasury rule;
4. retires every equity lot and contract once;
5. closes the account and removes the firm through the generation-safe store;
6. records one exit event and one lifecycle metric.

M7 later adds employee and estate consequences.

### 9.3 Entry

The current real entry signal uses the median return across the whole eligible
sector, avoiding survivor conditioning. Entry is capped, funded by a household,
and creates no free deposits. A new firm receives a stable entity ID, account,
bank relationship, physical startup state, statement, equity contract, founder
lot, and watchlist membership in one staged command.

### 9.4 Sector switching

Eligible consumption firms accumulate pressure only while the other stratum
outperforms by the configured sustained gap. A named deterministic hazard
selects switches. Retooling destroys the configured fraction of real capital,
not money. Sector membership and counters update atomically.

## 10. Bank equity, resolution, and entry

Bank fundamental value derives one-way from:

- canonical cash and reserves;
- loan, interbank, bond, and central-bank-operation assets/liabilities;
- `BankCapitalState`;
- realized earnings EMA.

Securities code may consume this balance-sheet view; banking headers must not
depend on the securities implementation.

Before non-equity failure resolution, a bank may receive qualifying primary
equity capital if demand exists and the configured resolution policy permits
it. Otherwise M5 resolution closes the failed balance sheet once and M6 retires
its equity contract/lots once.

Bank entry uses current viable incumbent ROE, congestion, configured caps, and
a deterministic founder search. The founder funds capital from deposits or
bond redemption before charter creation. A new bank receives a stable ID,
account, reserve node, capital/P&L rows, equity contract, and founder lot in one
staged command.

## 11. Public interfaces

### 11.1 C++

Add:

- `core/securities.hpp`;
- `simulation/m6.hpp`;
- `simulation/m6_checkpoint.hpp`;
- `build_m6_genesis`;
- `advance_m6_ticks`;
- typed read-only contract, lot, statement, and metric accessors.

### 11.2 C ABI

Append opaque M6 session functions:

- create/destroy;
- advance;
- apply supported M6 policy;
- save/load;
- metrics and digest;
- paged read-only bond/equity/firm-statement inspection.

Existing symbols and layouts do not change.

### 11.3 Python

Expose `M6Session`, immutable specifications/policies/rules, metrics, checkpoint
bytes, and typed security/statement snapshots. The Python binding owns the
native session and releases the GIL for multi-day advancement.

## 12. Checkpoint and digest

M6 checkpoint magic is `MSM6CP01`. It contains:

- an embedded accepted M5 checkpoint;
- security contracts, lots, and index-independent canonical rows;
- M6 policy, rules, runtime, statements, watchlists, lifecycle state, metrics,
  RNG counters, and tick.

Indexes are rebuilt and validated on load, never trusted from serialized
derived state. The payload is length-delimited, schema-versioned, hashed, size
bounded, and rejects trailing or corrupt input.

The exact state digest includes every persistent M6 canonical row and runtime
field, but excludes capacities and derived indexes.

## 13. Verification matrix

### 13.1 Unit and contract tests

- bond price edge cases and cohort coupon preservation;
- issue/coupon/maturity settlement;
- holder, issuer, maturity, security, and bank indexes;
- lot split/transfer/merge/retire fuzzing;
- firm and bank equity genesis identity;
- sparse watchlists and complete bank opportunity sets;
- pro-rata clearing, issuance, cash conservation, and zero clearing balance;
- margin origination, call, repayment, write-off, and bankruptcy;
- priced statement dimensions and no-cash revaluation;
- firm default, voluntary exit, entry, and sector switch;
- equity-aware bank failure and bank entry;
- invalid specs, NaN/Infinity, stale IDs, and fault rollback.

### 13.2 Identity gates

Every accepted tick checks:

- bond outstanding face equals active contract face and active lot face;
- per-security lots equal outstanding face/shares;
- holder, issuer, maturity, and bank indexes match canonical rows;
- Treasury debt and A5 private net financial worth;
- firm/bank common equity and cash identities;
- loan and margin principal authority;
- bank capital/P&L, reserve, and interbank M5 identities;
- clearing account zero;
- every exited issuer/contract settles once.

### 13.3 Determinism and recovery

- one-shot versus split native advancement;
- save/load in-process and fresh-process continuation;
- identical seed/action inputs yield exact native digest;
- injected failures before every M6 commit stage expose old state only;
- source and contract locks reject stale generated artifacts.

### 13.4 Semantic panels

Registered deterministic panels cover:

- rate increase lowers long-duration bond value;
- coupon and maturity cash signs;
- primary equity issuance raises issuer cash and shares together;
- profitable firms have stronger fundamentals and entry signal;
- persistent insolvency produces one exit/write-off;
- sustained relative return produces only permitted sector switches;
- bank loss lowers equity value and either recapitalizes or resolves once.

### 13.5 Performance

The P0 M6 workload extends the accepted M5 workload with:

- 2,000 households;
- 300 firms;
- 16 banks;
- watchlist size 15;
- active bonds, firm equity, bank equity, margin, and lifecycle checks.

Required complexity and allocation contracts:

- firm equity intent generation: `O(F + H*W)`;
- bank equity intent generation: `O(H*B)` because all banks are economically
  eligible;
- bond daily work: `O(active lots + due contracts + H + B)`;
- no `H*F` full scan;
- no per-order claim callback;
- reusable order/index scratch in steady state;
- doubled-entity scaling and allocation budgets are frozen before CI evidence
  is observed.

The accepted M5 benchmark remains green. M6 adds a separate absolute and
scaling gate rather than weakening M5.

## 14. Build and CI

Add debug, release, ASan, and UBSan presets and targets for:

- M6 core tests;
- index fuzz test;
- C smoke;
- checkpoint fresh-process test;
- semantic panel;
- performance benchmark/gate;
- installed C SDK consumer;
- wheel and source distribution smoke.

The release workflow must pass:

- macOS release and wheel;
- Linux release and wheel;
- Windows release and wheel;
- macOS ASan/UBSan;
- Linux ASan/UBSan.

Promotion requires all five jobs green on the same candidate SHA.

## 15. Commit and promotion sequence

1. Define M6 plan and frozen contracts.
2. Add strong IDs and canonical security book.
3. Add index validation and fuzz tests.
4. Add the internal M5 extension seam without changing M5 behavior.
5. Add bond phases and identities.
6. Add statements and one-way valuation.
7. Add firm and bank equity clearing plus margin.
8. Add firm/bank lifecycle commands.
9. Add atomic M6 tick, checkpoint, digest, C ABI, and Python binding.
10. Add semantic, recovery, performance, package, and CI gates.
11. Run full native and maintained Python regressions.
12. Commit and push a clean English-only candidate.
13. Wait for all cross-platform jobs.
14. Fast-forward only into `refactor/cpp-engine-v33`.
15. Tag `m6-securities-firm-lifecycle-v33`.

No merge into `dev` is part of M6.

## 16. Acceptance decision rule

M6 is accepted only if:

- every included current mechanism has a canonical native owner and live test;
- no included switch is inert;
- all identities and index fuzz tests pass;
- firm/bank exit and entry settle each contract once;
- checkpoint continuation is exact;
- M5 behavior and performance remain accepted;
- the frozen M6 performance contracts pass;
- C++, C ABI, Python binding, wheel, source distribution, and installed SDK
  smokes pass;
- all five CI jobs are green on one SHA;
- the branch is clean and contains no Chinese source, documentation, generated
  contract, or commit subject.
