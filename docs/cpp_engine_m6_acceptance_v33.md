# C++ Engine M6 Acceptance

Status: accepted locally on macOS arm64

Engine version: `0.6.0-m6`

## Scope

M6 adds the native securities and firm-lifecycle frontier on top of the accepted
M5 monetary closed economy:

- indexed bond, equity, and ownership-lot books;
- deterministic bond issuance, coupons, maturity, and settlement;
- firm and bank equity valuation and trading;
- margin credit and security-backed settlement;
- firm statements, entry, exit, default, and residual distribution;
- bank entry and bank-equity lifecycle handling;
- stable digests, exact checkpoints, continuation, and corruption rejection;
- C ABI, Python binding, installed-artifact, wheel, and source-distribution
  boundaries;
- bounded workspaces and frozen performance budgets.

The implementation continues to use the current complete Python engine as the
regression authority for modules that have not yet crossed the native frontier.

## Correctness gates

The following gates passed on 2026-07-24:

- full Python regression: 1,586 passed, 11 skipped;
- release CTest: 27 of 27 passed;
- ASan and UBSan CTest: 18 of 18 passed;
- fresh-process M6 checkpoint continuation and digest equality;
- M6 semantic panel;
- installed C ABI smoke from an independent temporary CMake consumer;
- isolated wheel install, initialization, advancement, checkpoint, and
  continuation;
- source-distribution content smoke;
- source locks, current-target check, CJK scan, and `git diff --check`.

The full Python run emitted four existing Gymnasium warnings about infinite Box
observation bounds. They are warnings rather than test failures and are outside
the M6 engine boundary.

## Sanitizer finding resolved during acceptance

ASan found a stale firm dense-index mapping after an M6 firm exit. The next M5
debt-service phase could address a retired dense slot. M5 now synchronizes only
the topology-dependent account, bank, node, and firm maps at the start of each
tick and performs a defensive firm-work bound check. This preserves the stable
scratch-capacity contract while supporting firm and bank topology changes.

## Performance gates

All figures are release-build medians or p95 values on the local macOS arm64
host.

### M5 compatibility gate

| Scale | Median day | p95 day | Maximum allocations per day |
|---|---:|---:|---:|
| 1,000 households, 150 firms, 8 banks | 0.214 ms | 0.321 ms | 1 |
| 2,000 households, 300 firms, 16 banks | 0.309 ms | 0.356 ms | 1 |

The measured doubling ratio was 1.44. Scratch capacity remained unchanged.

### M6 securities gate

| Scale | Median day | p95 day | Maximum allocations per day |
|---|---:|---:|---:|
| 1,000 households, 150 firms, 8 banks | 8.41 ms | 8.90 ms | 43 |
| 2,000 households, 300 firms, 16 banks | 24.27 ms | 25.05 ms | 43 |

The measured doubling ratio was 2.89 against a maximum of 3.20. The P0 p95
result was below the 65 ms macOS platform budget, and the allocation count was
below the budget of 64. Scratch capacity remained unchanged.

The first cross-platform CI calibration produced these P0 measurements:

| Runner | p95 day | Doubling ratio | Frozen p95 budget |
|---|---:|---:|---:|
| macOS 14 arm64 | 52.42 ms | 3.05 | 65 ms |
| Ubuntu 24.04 x64 | 68.27 ms | 2.95 | 85 ms |
| Windows 2022 x64 | 66.55 ms | 3.04 | 80 ms |

The cross-platform scaling budget is 3.20. Allocation counts and scratch
capacity were stable on every runner. The budgets retain a bounded runner-noise
margin without weakening the allocation or topology-stability gates.

## Promotion rule

The M6 branch may be fast-forwarded into the V33 integration branch only after
the pushed M6 commit passes every required job in the native GitHub Actions
workflow. The development branch remains untouched.
