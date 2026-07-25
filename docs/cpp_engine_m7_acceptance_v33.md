# C++ Engine M7 Acceptance

Status: accepted locally on macOS arm64

Engine version: `0.7.0-m7`

## Scope

M7 adds the native population, household, relationship, and persistent-labor
frontier on top of the accepted M6 securities economy:

- stable person identities with a dense alive view and cold archive;
- canonical household membership and person beneficial ownership;
- deterministic births, deaths, estates, inheritance, and public residuals;
- symmetric unions, lineage, guardianship, divorce, and leaving home;
- persistent primary and secondary jobs, rosters, suspensions, recall,
  job-to-job moves, and wage anniversaries;
- participation, job-guarantee, labor stock/flow accounting, and typed sensors;
- exact marriage matching with bounded normalized scaling;
- stable digests, exact checkpoints, continuation, and corruption rejection;
- C ABI, Python binding, installed-artifact, wheel, and source-distribution
  boundaries;
- bounded workspaces and frozen population, matching, and roster budgets.

The implementation continues to use the current complete Python engine as the
regression authority for modules that have not yet crossed the native frontier.

## Correctness gates

The following gates passed on 2026-07-24:

- full Python regression with eight workers: 1,586 passed, 11 skipped;
- release CTest: 34 of 34 passed;
- focused M7 ASan and UBSan CTest: 3 of 3 passed;
- fresh-process M7 checkpoint continuation and digest equality;
- M7 semantic panel;
- installed C ABI smoke from an independent temporary CMake consumer;
- isolated wheel install, initialization, advancement, checkpoint, and
  continuation;
- source-distribution content smoke;
- source locks, current-target check, CJK scan, and `git diff --check`.

The eight-worker Python regression completed in 49 minutes 53 seconds and
emitted four existing Gymnasium warnings about infinite Box observation bounds.
They are warnings rather than failures and are outside the M7 engine boundary.

## Sanitizer finding resolved during acceptance

ASan found a stale pointer in beneficial-claim genesis. Creating a new lot could
grow the backing vector after a pointer to an existing lot had been retained.
The implementation now copies the owner and share before the mutating call and
never reads through an invalidated address.

## Semantic findings resolved during acceptance

- Job-ladder search now draws one search-intensity decision and one destination
  firm per worker, preserving the maintained Python choice cadence without a
  firm-by-worker nested search.
- A secondary job is atomically promoted when the primary job separates.
- An estate without a spouse, child, parent, or co-resident heir now settles to
  the public residual instead of selecting an unrelated person.
- Reverse lineage indexes are validated for every live parent reference.
- Firm exits separate every remaining native job before the firm disappears.
- Generic ownership lots are rekeyed exactly once when an empty household
  account closes.

## Performance gates

All figures are release-build medians or p95 values on the local macOS arm64
host.

### M7 population and labor gate

| Scale | Median day | p95 day | Maximum allocations per day |
|---|---:|---:|---:|
| 1,000 persons, 400 households, 60 firms | 9.68 ms | 10.40 ms | 1,011 |
| 2,000 persons, 800 households, 120 firms | 25.89 ms | 27.41 ms | 1,936 |

The measured daily doubling ratio was 2.67 against a maximum of 3.20. The P0
p95 result was below the 120 ms macOS platform budget, and the allocation count
was below the budget of 2,200. Scratch capacity remained unchanged in the
no-topology panel.

### Exact matching gate

| Candidates | Median exact-match time |
|---:|---:|
| 400 | 27.0 us |
| 800 | 65.8 us |
| 1,600 | 178.0 us |
| 3,200 | 421.4 us |

The 400-to-3,200 normalized scaling ratio was 1.95 against a maximum of 2.60.
The implementation uses one stable age ordering and a balanced search index;
it preserves deterministic score and tie ordering without recursive
partitioning allocations.

### Large-employer roster gate

| Active jobs | Median roster mutation time |
|---:|---:|
| 400 | 0.92 us |
| 3,200 | 7.96 us |

The normalized scaling ratio was 1.08 against a maximum of 1.50.

## Promotion rule

The M7 branch may be fast-forwarded into the V33 integration branch only after
the pushed M7 commit passes every required job in the native GitHub Actions
workflow. The development branch remains untouched.
