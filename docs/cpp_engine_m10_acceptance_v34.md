# C++ Engine M10 Acceptance

Status: accepted

Engine version: `0.11.0-m11`

Acceptance commit: `19062454d83e49641212625c187ad941838064fb`

CI run: <https://github.com/qinglinh2003/Macro-Simulator/actions/runs/30377446044>

## Scope

M10 moves control, reporting, and release filtering into the native engine and
makes the desktop product native-backed:

- stable metric identities projected from every maintained M4-M9 metric, with a
  capacity-bounded history ring and paged read-only frames through C++ and
  nanobind;
- an atomic World policy boundary that validates every domestic bundle and
  external policy before any live write, then applies domestic and external
  policy as one operation with generation checks and exact rollback;
- `HybridControlledBridge`, which owns the canonical controller envelope and
  exposes operation-keyed `update_controller` plus exclusive
  `prepare_boundary` / `commit_boundary` / `abort_boundary` leases;
- stable Python controller and Gym wrappers backed by native controlled
  sessions, native composite clone/reset, and homogeneous vector batches;
- role-filtered release snapshots derived from native source frames plus the
  envelope, and typed native probes replacing private-field diagnostics;
- `macro_sim.desktop.SimulationRuntime` native-backed by default, preserving
  desktop protocol compatibility and explicit Python-oracle backend selection.

Python is not called for any economic phase during native advancement.

## Authoritative invariants

The eight invariants in `docs/cpp_engine_m10_execution_plan_v34.md` hold. The
two that this acceptance re-verified after the CI remediation are:

1. a public boundary exposes either the complete old composite or the complete
   new composite, never a partial one;
2. history memory is bounded independently of simulation duration, which the P7
   longevity gate measures directly.

## Correctness gates

All gates below are named ctest tests in the `m11-release` preset, which
contains 74 tests and runs with eight workers.

| Area | Tests |
| --- | --- |
| Policy boundary and reporting | `macro_sim.m10_policy`, `macro_sim.m10_reporting`, `macro_sim.m10_control` |
| Bindings and facade | `macro_sim.m10_binding_smoke`, `macro_sim.m10_native_facade` |
| History streams | `macro_sim.m10_native_history_stream`, `macro_sim.m10_controller_history_stream` |
| Controller and desktop | `macro_sim.m10_native_controller`, `macro_sim.m10_native_desktop` |
| Stress | `macro_sim.m10_policy_stress` |

The installed C package is verified separately, outside that preset:
`tools/m1/installed_c_smoke.py` installs the native ABI, configures the
standalone consumer project in `tests/native/installed_consumer`, and runs its
single `macro_sim.installed_c_abi` test against the installed package.

Golden inference and control behavior is covered by
`macro_sim.m11_kernel_golden` and `macro_sim.m11_artifact_golden`, which pin the
`.msrl` evaluation semantics M10.4 preserved.

## Commands

```bash
uv run python tools/m11/check.py --skip-build
uv run cmake --preset m11-release
uv run cmake --build --preset m11-release --parallel 8
ctest --preset m11-release -j 8 --output-on-failure
uv run python tools/m1/installed_c_smoke.py \
    --build-dir build/native/m11-release --prefix build/install/m11-ci
uv run python tools/m10/performance_gate.py \
    --native-dir build/native/m11-release/native
uv run python tools/m10/p7_longevity.py \
    --native-dir build/native/m11-release/native
uv run python tools/m11/static_analysis.py --build-dir build/native/m11-debug
```

## Performance evidence

Captured on a clean tree at the final commit, macOS arm64.
Raw records: `build/evidence/m11/final/m10-performance.json` and
`build/evidence/m11/final/p7-longevity.json` (ignored by git).

| Gate | Result |
| --- | --- |
| P0 tick | median 294,542 ns, p95 311,625 ns |
| P1 | median 2.794 ms, p95 3.042 ms |
| P2 | median 3.379 ms, p95 3.824 ms |
| P5 throughput | 6,451.79 engine-days/s |
| P7 longevity | 10,000 population for 3,650 days in 12.803 s |
| P7 memory | final p95 RSS 148,389,888 bytes against a 202,807,705 byte limit |

Every gate reports an empty `failures` list against
`schemas/m10/performance_budget.json`.

## CI remediation recorded during acceptance

The M10 and M11 implementation was feature complete before this acceptance. The
work that closed it out was release engineering, and four defects were found by
the strict gates rather than by the functional suites:

1. `native/src/control/m11_session.cpp` built an operation identifier from
   `next.boundary_sequence` in the same call that moved `next`. Function
   argument evaluation is indeterminately sequenced, so the read could observe
   a moved-from object and corrupt the replay and idempotency key rather than
   crash. Fixed by sequencing the read before the move.
2. `native/src/desktop/m11_protocol.cpp` dereferenced the `new_game` optional on
   a path guarded only by the session pointer. The invariant held in practice
   but was implicit; the save path now returns a protocol fault instead.
3. The M11 policy write macros dereferenced the numeric optional without a
   guard, so a non-numeric value routed to a numeric lever was undefined
   behavior. The macros now reject the value with `invalid_argument`.
4. `tests/native/installed_c_smoke.c` still asserted the M9 engine version
   string. The assertion now derives the expected version from the installed
   package, so it cannot go stale on a milestone version bump.

Two clang-tidy checks are disabled repository wide with rationale recorded in
`.clang-tidy`: `performance-enum-size`, because the flagged enums are part of
the published C ABI consumed by the `cp312-abi3` wheel and the packaged client,
and `clang-analyzer-optin.performance.Padding`, because `M5PolicyState` and
`M6Rules` field order is pinned by the M5 contract lock and by checkpoint
serialization. Three findings are clang-tidy false positives and carry scoped
`NOLINT` comments with reasons: the M10 metric-count macro fragments cannot be
parenthesized without a syntax error, and `Result::take` is rvalue qualified so
its `std::move` is load bearing. Every other finding was fixed in code.

## Promotion rule

M10 promotes only with M11, because M10.5 makes the desktop product
native-backed and the packaged product is the M11 deliverable. See
`docs/cpp_engine_m11_acceptance_v34.md`.
