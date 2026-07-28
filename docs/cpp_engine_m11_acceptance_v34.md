# C++ Engine M11 Acceptance

Status: accepted

Engine version: `0.11.0-m11`

Acceptance commit: `19062454d83e49641212625c187ad941838064fb`

CI run: <https://github.com/qinglinh2003/Macro-Simulator/actions/runs/30377446044>

## Scope

M11 is the product cutover. It turns the native engine plus the M10 control
surface into a shippable desktop application and a distributable Python
extension:

- a native desktop worker (`macro_sim_server`) and launcher
  (`macro_sim_launcher`) with a capability-token bootstrap, owner-only runtime
  files, and a newline-delimited JSON protocol;
- the M11 session, coordinator, kernel, and policy contract that carry the
  governed decision boundary, adjustment costs, and pending decision timeline;
- strict `.msrl` artifact loading with golden inference behavior;
- new-game specification, save slots, crisis handling, and load with crash
  recovery;
- a packaged Godot desktop product that bundles the launcher, worker, RL
  artifact, and licenses;
- a `cp312-abi3` wheel and source distribution built through cibuildwheel.

## Product module disposition

The packaged product is verified by `tools/m11/packaged_godot_e2e.py`, which
asserts that every required module is present and content-addressed. No required
module is missing on any packaged platform.

| Module | Location in the package | Verification |
| --- | --- | --- |
| Desktop application | `Macro Command` game binary | exported and launched by the E2E flow |
| Launcher | platform launcher binary | launched by the E2E flow |
| Native worker | `native/macro_sim_server` | resolved and connected at runtime |
| RL artifact | `native/artifacts/fiscal_stabilization_v1.msrl` | SHA-256 compared against the source artifact |
| Licenses | `licenses/` | staged by the packaging scripts |

## Correctness gates

| Area | Tests |
| --- | --- |
| Artifact and golden inference | `macro_sim.m11_artifact`, `macro_sim.m11_artifact_golden`, `macro_sim.m11_kernel_golden` |
| Kernel, session, coordinator | `macro_sim.m11_kernel`, `macro_sim.m11_session`, `macro_sim.m11_coordinator` |
| Policy contract and release | `macro_sim.m11_policy_contract`, `macro_sim.m11_release` |
| Frontend and new game | `macro_sim.m11_frontend`, `macro_sim.m11_new_game` |
| Protocol and parser hardening | `macro_sim.m11_protocol`, `macro_sim.m11_parser_fuzz` |
| Worker and end to end | `macro_sim.m11_server`, `macro_sim.m11_godot_e2e`, `macro_sim.m11_launcher_e2e` |

Release suite result: 74 of 74 tests passed with `-j 8`.

## Packaged end-to-end flow

`tools/m11/packaged_godot_e2e.py` runs three flows against the built package on
every packaged platform:

1. `run_normal_flow` — new game, play, policy change, crisis, save, quit, load,
   including runtime permission validation on the worker directory;
2. `run_worker_crash_flow` — the worker process is killed after connect, and the
   launcher must refuse to accept the unexpected worker exit;
3. `run_launcher_crash_flow` — the launcher process is killed after connect, and
   the runtime must not survive as an orphan.

Flows 2 and 3 are the rollback and crash-path evidence required for acceptance.

## Commands

```bash
uv run python tools/m11/check.py --skip-build
uv run cmake --preset m11-release
uv run cmake --build --preset m11-release --parallel 8
ctest --preset m11-release -j 8 --output-on-failure
uv run python tools/m11/p3_desktop_gate.py \
    --server build/native/m11-release/native/macro_sim_server \
    --budget schemas/m10/performance_budget.json
uv run python tools/m11/packaged_godot_e2e.py --package <package> --platform <platform>
uv run cibuildwheel --output-dir dist
uv build --sdist
```

## Performance evidence

Captured on a clean tree at the final commit, macOS arm64.
Raw record: `build/evidence/m11/final/p3-desktop.json` (ignored by git).

| Gate | Result |
| --- | --- |
| P3 desktop snapshot p95 | 1.819 ms |
| P3 sixty-day batch plus snapshot p95 | 43.766 ms |

The gate reports an empty `failures` list against
`schemas/m10/performance_budget.json`.

## Platform coverage

| Platform | Wheel | Packaged desktop |
| --- | --- | --- |
| macOS arm64 | passed | passed |
| macOS x86_64 | passed | passed |
| Linux x86_64 | passed | passed |
| Linux aarch64 | passed | passed |
| Windows x86_64 | passed | passed |

The wheel is built against the CPython stable ABI as `cp312-abi3` and was smoke
tested on CPython 3.12 and 3.14.

## Full regression matrix

| Gate | Where |
| --- | --- |
| Release regression, eight workers | `ctest --preset m11-release -j 8` |
| Parser fuzz smoke | `macro_sim.m11_parser_fuzz` |
| ASan and UBSan | Ubuntu and macOS CI jobs |
| TSan | Ubuntu CI job |
| Coverage | Ubuntu CI job, `-fprofile-update=atomic` with eight workers |
| Format and clang-tidy | Ubuntu CI job, warnings as errors |
| Wheel smoke | every wheel job |
| Packaged end to end | every packaged Godot job |

## Release engineering notes

Five platform-specific defects were closed during acceptance. Each one was
exposed only by the release matrix, and none of the Windows-specific defects
reproduce on macOS or Linux:

1. `macro_sim_server.cpp` used `std::numeric_limits<int>::max()` in a
   translation unit that includes `winsock2.h`. `NOMINMAX` was defined after
   that include, so the Windows `max()` macro broke the MSVC parse. The call now
   uses the parenthesized form, which is portable regardless of macro state.
2. `scripts/package_m11_windows.ps1` drove the GUI subsystem Godot binary
   through the call operator. PowerShell does not wait for such a process, so
   the export returned a stale exit code, printed nothing, and left the staging
   bundle empty while both native binaries were present. The script now resolves
   shims and symlinks, prefers the console variant, runs Godot through
   `Start-Process` with an explicit wait, and dumps the staging and native
   output when a required artifact is missing.
3. The packaged Windows product shipped only the two executables. The worker
   links zlib through `macro_sim_core`, and vcpkg stages `z.dll` beside the
   build output, so outside the build tree the worker could not load and the
   launcher reported that it never became ready. The packaging script now copies
   every runtime library staged beside the native build output into both the
   bundle root, where the launcher runs, and the native directory, where the
   worker runs.
4. The Windows owner-only runtime check supplied the directory as a trailing
   PowerShell `-Command` argument. PowerShell did not bind that trailing value
   to `$args[0]`, so the verifier failed before inspecting the access control
   list. The verifier now passes a dedicated environment variable to PowerShell
   and still rejects every access rule not owned by the current user.
5. Windows Godot reports exit status `1` after a successful headless teardown.
   The packaged E2E verifier accepts that code only after it has observed the
   canonical shutdown marker, all normal-flow assertions, and runtime cleanup.
   It still rejects every other nonzero exit status and separately verifies the
   worker-crash and launcher-crash rollback flows.

The coverage job failed with negative gcov counters because eight parallel ctest
workers share the counters. `-fprofile-update=atomic` was added to the GCC
coverage flags; the worker count is unchanged.

The M5 source lock recorded a pre-edit hash of `.github/workflows/native.yml`,
which failed the contract gate on every wheel platform. The lock input set was
not the cause and is unchanged; only the recorded hashes were refreshed.
