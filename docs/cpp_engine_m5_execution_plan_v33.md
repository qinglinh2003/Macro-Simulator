# M5 Native Monetary Closed Economy Execution Plan

Status: implementation baseline  
Integration target: `refactor/cpp-engine-v33`  
Milestone branch: `refactor/cpp-m5-v33`  
Engine target: the current complete playable Python engine and the accepted M4
native vertical, never a historical version preset

## 1. Objective

M5 extends the accepted M4 native economy into a monetary closed economy. The
native tick must own fiscal policy, credit, commercial banks, reserves, RTGS,
interbank funding, central-bank operations, realized bank P&L, bank runs, and
the supported non-equity resolution path.

M5 is not a production cutover. Securities, equity ownership, firm lifecycle,
population, housing, energy, the world layer, controllers, and desktop
packaging remain assigned to later milestones.

## 2. Non-negotiable contracts

1. The latest playable engine is the economic source of truth.
2. Python is an independent differential and semantic oracle, not a phase in
   the native tick.
3. Every financial fact has exactly one canonical owner.
4. A tick validates its projected financial state before publishing any
   persistent mutation.
5. The steady hot path may not clone the root state or allocate merely because
   a tick advanced.
6. All order-sensitive operations use stable numeric IDs.
7. A failed phase leaves balances, reserves, contracts, policy sensors, RNG,
   metrics, and the tick counter unchanged.
8. M4 compatibility fixtures remain green.

## 3. Supported M5 capability boundary

M5 accepts:

- the M4 capital/fiscal vertical;
- commercial-bank credit;
- multiple settlement banks;
- bank-specific deposit relationships;
- reserve settlement and RTGS;
- interbank overnight funding;
- the three-state monetary regime;
- reserve absorption and injection operations;
- lender-of-last-resort advances;
- realized and maintained legacy bank P&L ordering;
- household and firm debt service;
- deposit competition and funding cost;
- deterministic bank-run and default crisis fixtures;
- non-equity failure resolution.

M5 rejects or leaves inert until their assigned milestone:

- government bonds and other securities;
- firm or bank equity;
- bank entry;
- firm entry and exit;
- mortgages, margin credit, and collateral;
- population-dependent pensions and estates;
- energy and housing tax bases;
- external positions, FX, pegs, sanctions, and migration;
- stateful exogenous shocks;
- controllers, Gym/RL, and native policy-model inference.

An M5 policy field whose state dependency belongs to a later milestone is not
silently approximated. It remains unavailable until that canonical state
exists.

## 4. Canonical ownership

| Economic fact | Canonical owner |
|---|---|
| customer, firm, Treasury, clearing, and bank cash | `PostingBook` |
| commercial-bank reserve positions and reserve stock | `ReserveBook` |
| loan principal, lender, borrower, rate, and maturity | `LoanBook` |
| interbank principal, accrued interest, lender, borrower, and maturity | `InterbankBook` |
| reserve absorption and lender-of-last-resort claims | `CentralBankOperationBook` |
| named realized bank income and expense legs | `BankPnlJournal` |
| loss-absorbing book capital and funding arrears | `BankCapitalState` |
| live domestic M5 policy | `M5PolicyState` |
| rate sensor, current rate, fear state, and lagged monetary observations | `M5Runtime` |
| a depositor's settlement bank | its canonical posting account settlement node |

`BankBalanceSheetView` is derived from these books. It is never serialized as
an independent balance mirror.

## 5. Tick transaction model

M4 is extended with an internal native tick-extension seam. The seam exposes
projected balances, reserve positions, account settlement nodes, loan
principal, and reusable scratch to M5, but never permits a hook to mutate
persistent state.

The accepted order is:

1. open tick journals;
2. apply the monetary regime and update the inflation sensor;
3. run deposit competition;
4. run central-bank reserve operations;
5. open the real economy and plan firms and households;
6. originate firm and household credit;
7. run labor, production, goods, and capital-goods markets;
8. full-P&L mode: service firm and household debt;
9. settle firms, dividends, taxes, transfers, and physical capital;
10. maintained legacy mode: service firm and household debt;
11. mature old interbank claims and clear new reserve deficits;
12. execute bank-run queues and lender-of-last-resort advances;
13. write off requested deterministic crisis defaults;
14. resolve insolvent banks without equity;
15. pay deposit funding cost and close realized bank P&L;
16. validate A4, A5, reserves, loans, interbank, central-bank operations,
    capital/P&L roll-forward, finite state, and canonical references;
17. publish all projected books and advance the tick.

Full-P&L mode includes realized firm interest in the corporate tax and
distribution base. The maintained legacy mode closes firm fiscal settlement
before debt service. Both orders are explicit fixtures.

## 6. Policy surface

### 6.1 Fiscal

- government consumption share;
- deficit target, unemployment reference, and cap;
- government investment share;
- profit, income, consumption, and wealth tax;
- income and wealth allowances;
- unemployment replacement;
- in-work income floor;
- minimum wage;
- job guarantee, wage ratio, and public-works share.

Population-dependent pensions are deferred to M7. Energy and housing fiscal
bases are deferred to M8. Bond financing is deferred to M6.

### 6.2 Monetary

`monetary_regime` has exactly three states:

- `exogenous`: the seed rate remains fixed and the inflation sensor is off;
- `taylor`: the sensor runs and the Taylor rule sets the rate;
- `manual`: the sensor runs and a required manual rate sets the rate.

Validation requires:

- manual if and only if a finite manual rate is present;
- no manual rate in exogenous or Taylor mode;
- finite nonnegative targets and coefficients;
- a finite positive rate ceiling;
- an inertia value in `[0, 1]`.

Quantity tools:

- reserve target;
- target indexation to deposits;
- gap-closing speed;
- reserve floor;
- lender of last resort.

### 6.3 Credit and prudential policy

- firm leverage limit;
- firm DSCR floor;
- household credit limit;
- bank capital constraint;
- unified bank risk-weighted envelope for the currently migrated unsecured
  assets;
- regulatory bank leverage ceiling;
- single-borrower exposure limit;
- target capital payout ratio;
- deposit-rate floor;
- borrower migration on failure;
- state resolution backstop.

Mortgage risk weights, duration limits, and equity-dependent resolution remain
disabled until their underlying books exist.

## 7. Structural rules

M5 structural rules include:

- bank count and opening capital;
- bank leverage-appetite distribution;
- bank assignment and search friction;
- rate and deposit spread dispersion;
- relationship lock-in;
- interbank-rate base and tightness response;
- realized versus maintained legacy P&L;
- firm and household amortization;
- household-credit enablement;
- deposit-interest arrears;
- bank-run enablement, sensitivity, book-health reference, and fear
  persistence;
- bank payout ratio.

Structural fields are immutable after genesis. Policies are mutable only at a
tick boundary.

## 8. Financial books

### 8.1 `InterbankBook`

Each active record contains:

- stable contract ID;
- lender and borrower bank IDs;
- principal;
- per-tick rate;
- accrued unpaid interest;
- originated and maturity ticks;
- active flag.

The book owns one record, not mirrored lender and borrower copies. Stable
lender and borrower indexes are derived and validated.

### 8.2 `CentralBankOperationBook`

Operations are typed as:

- reserve absorption: a bank claim on the central bank created when reserves
  are drained;
- lender-of-last-resort advance: a central-bank claim on a bank created when
  reserves are issued during a run.

Reserve redemption or repayment reduces the same contract. Aggregate assets,
liabilities, and reserve-stock changes reconcile by operation kind.

### 8.3 `BankPnlJournal`

The per-bank tick journal records:

- loan interest;
- interbank interest income;
- interbank interest expense;
- deposit funding cost;
- realized loan losses;
- realized interbank losses;
- resolution levies or backstop receipts;
- dividends;
- net income.

No accrued but unpaid household or firm interest is bank income.

### 8.4 `BankCapitalState`

The state owns:

- opening book capital;
- closing book capital;
- deposit-interest arrears;
- alive/resolution status;
- the most recent validated roll-forward tick.

Capital decisions read this state. The bank cash account remains an actual
posting account and must reconcile to the closed-economy M5 balance-sheet
fixture; it is not treated as the canonical definition of capital.

## 9. Settlement semantics

1. Ordinary transfers alter posting accounts and, when settlement nodes
   differ, reserves by the same amount.
2. Loan origination increases borrower deposits and loan principal together.
3. Principal repayment decreases borrower deposits and loan principal
   together.
4. A loan write-off decreases loan principal and the lender's loss-absorbing
   capital by the same amount.
5. Interbank principal settlement moves reserves only.
6. Interbank default reallocates book capital without pretending that reserves
   moved.
7. OMO reserve issuance or retirement changes reserve stock and the matching
   central-bank operation contract together.
8. Treasury transfers remain ordinary balanced postings.

## 10. Failure resolution

The M5 path is deliberately non-equity:

1. mark the bank unavailable for new relationships;
2. settle or default interbank liabilities exactly once;
3. transfer surviving interbank assets to a deterministic bridge bank;
4. migrate customer relationships when policy permits;
5. transfer any positive estate cash to the bridge bank or Treasury;
6. fill a negative residual through the state backstop when enabled;
7. otherwise levy surviving banks pro rata by positive reserves;
8. validate that no active contract points to an unresolved dead bank.

Bank ownership, shareholder bail-in, and de-novo entry are M6 responsibilities.

## 11. Invariants

Every tick executes:

- `invariant.ledger.nonnegative-balances` for accounts without a declared
  overdraft exception;
- A4 customer-deposit and payment feasibility;
- A5 aggregate net-financial-worth;
- reserve position sum equals reserve stock after tracked roundoff;
- every active loan has one live lender and one canonical borrower account;
- loan aggregate principal equals lender and borrower projections;
- every interbank contract has distinct live counterparties unless it is being
  resolved in the current transaction;
- interbank assets equal interbank liabilities by construction;
- central-bank operation principal equals the associated reserve-stock bridge;
- bank P&L net income equals its named legs;
- closing capital equals opening capital plus recognized income, losses,
  levies/backstops, and distributions;
- all finite and domain-bounded state;
- no active customer relationship points to an unavailable bank after
  migration-enabled resolution.

## 12. Persistence and interfaces

Deliver:

- an M5 checkpoint envelope containing the accepted M4 state plus M5 runtime
  and financial books;
- exact same-process and fresh-process continuation;
- C++ session APIs for M5 genesis, policy update, tick advance, snapshot,
  digest, checkpoint save, and checkpoint restore;
- an appended C ABI capability and M5 structs/functions;
- nanobind M5 specs, policy, advance, and snapshot surfaces;
- isolated source and wheel smoke tests.

No old checkpoint compatibility is required.

## 13. Verification panels

### 13.1 Deterministic fixtures

- same-bank and cross-bank RTGS;
- firm and household origination and repayment;
- full-P&L versus maintained legacy settlement ordering;
- deposit funding cost and arrears;
- policy-rate exogenous, Taylor, and manual transitions;
- OMO drain, redemption, and deposit-indexed target;
- overnight interbank advance, interest, rollover, and default;
- lender-of-last-resort run rescue;
- suspended run and non-equity failure;
- state backstop and mutualized resolution;
- loan write-off and creditor failure cascade.

### 13.2 Semantic panels

- expansionary fiscal impulse raises near-term nominal demand;
- higher income tax reduces disposable household income;
- a higher manual policy rate raises debt service and weakens credit demand;
- a binding capital constraint reduces new lending;
- reserve drain increases interbank tightness;
- lender of last resort prevents an otherwise deterministic liquidity failure.

### 13.3 Stochastic panels

Frozen multi-seed panels cover:

- bank search and relationship concentration;
- depositor migration;
- run-flight volume;
- failure frequency;
- credit growth and interest income.

### 13.4 Fault and persistence

- every M5 phase fault leaves the pre-tick digest unchanged;
- direct run equals save/fresh-process/load continuation;
- corrupt size, digest, enum, ID, reference, and numeric fields fail before
  session publication.

## 14. Performance budgets

The M5 hot path targets:

- credit aggregation: `O(H + F + L + B)`;
- RTGS: `O(number of transfers)`;
- deposit competition: `O(H * search_m + B)`;
- interbank clearing: `O(B^2)` only over the explicitly complete bank market;
- bank P&L and capital close: `O(B + L)`;
- zero allocations in a steady tick without new contracts or entity changes;
- no household-by-bank full scan when the economic rule uses bounded search;
- no repeated full loan-book scan per loan request.

Benchmarks report median, p95, allocation count, loan count, transfer count,
and bank-count scaling.

## 15. Commit sequence

1. `docs: define M5 monetary closed economy plan`
2. `feat: add canonical M5 financial books`
3. `feat: add atomic M5 tick extension`
4. `feat: implement monetary credit and banking phases`
5. `feat: add M5 persistence and public interfaces`
6. `test: add M5 crises semantic panels and benchmarks`
7. `chore: lock and accept M5 monetary closed economy`

## 16. Exit gate

M5 is accepted only when:

- all M4 gates remain green;
- A4, A5, reserve, interbank, loan, P&L, and capital gates pass every M5 tick;
- deterministic run, default, and non-equity resolution fixtures pass;
- monetary and fiscal impulse panels pass their frozen semantic rules;
- fresh-process checkpoint continuation is exact;
- debug, release, ASan, and UBSan native suites pass;
- C ABI, Python binding, source artifact, and isolated wheel smoke tests pass;
- the complete existing Python regression remains green;
- macOS, Linux, Windows, and sanitizer CI jobs pass on the same commit;
- bank and posting performance gates pass;
- target headers have no banking-to-securities dependency cycle;
- the branch is clean, pushed, and fast-forwarded into
  `refactor/cpp-engine-v33`;
- the accepted commit receives tag `m5-monetary-closed-economy-v33`.
