# C++ Engine M1 Execution Plan (V33)

Status: implementation plan  
Branch: `refactor/cpp-m1-v33`  
Base: `m0-contract-v33` / `38e7e5b37b8ae55fdd0c5f9180f0390b258e6597`  
Scope: native foundation only; no economic phase is translated in M1

## 1. Objective

M1 establishes a reproducible, packageable, rejectable C++20 foundation for
the later vertical migration. It does not alter the Python oracle's economic
semantics and does not make the native engine the production backend.

The milestone is complete only when a clean checkout can:

1. regenerate all checked M1 contract skeletons byte-for-byte;
2. configure and build the native core, C ABI, Python binding, tests, and
   benchmark targets;
3. pass native tests under the normal and ASan/UBSan profiles;
4. install and link a C-only program against the installed ABI;
5. build a wheel, install it into an isolated environment outside the source
   tree, and create/destroy an empty native session;
6. match checked Philox and portable-sampler vectors;
7. reject the checked config/policy invalid corpus identically in Python and
   C++;
8. reproduce the checkpoint prototype and canonical-encoding corruption
   vectors;
9. produce deterministic dependency/SBOM evidence;
10. pass the full Python regression without changing the M0 oracle contracts.

## 2. Invariants

- `m0-contract-v33` remains immutable and is an ancestor of every M1 commit.
- M1 consumes `schemas/m0/hashes.lock.json`; it never rewrites M0 inventory,
  fixture, benchmark, or expected-result files.
- M1 tools live under `tools/m1`, native sources under `native`, and generated
  M1 contracts under `schemas/m1`. This prevents post-M0 infrastructure files
  from changing the frozen Python module inventory.
- All generated output is canonical UTF-8 with LF endings, sorted stable IDs,
  no timestamps, and no absolute paths.
- The C ABI owns every allocation it returns and exposes an explicit destroy
  function. C++ exceptions never cross the ABI.
- Python binding calls are session/batch oriented. M1 exposes no per-agent
  callback or economic mutation API.
- The empty `EngineSession` has lifecycle and identity only. Its tick remains
  zero and it runs no Python or C++ economic phase.
- Cross-platform RNG and ABI claims are made only by the checked CI matrix,
  not inferred from one local platform.

## 3. Work packages

### M1-01 — Build, packaging, and bootstrap

Deliver:

- `native/CMakeLists.txt`;
- checked `CMakePresets.json` with debug, release, ASan/UBSan, TSan, coverage,
  and benchmark configure/build/test presets;
- targets `macro_sim_core`, `macro_sim_c`, `_native`, `macro_sim_native_tests`,
  and `macro_sim_benchmarks`;
- scikit-build-core and nanobind packaging;
- direct `cloudpickle` declaration for RL/train and a separate visualization
  extra for Matplotlib;
- `tools/m1/bootstrap.py` and `tools/m1/check.py`;
- install rules for C headers and the C ABI library.

Acceptance:

```bash
uv sync --extra rl --extra train --extra visualization --group dev --group m1
uv run python tools/m1/bootstrap.py --check
cmake --preset m1-debug
cmake --build --preset m1-debug
ctest --preset m1-debug
```

### M1-02 — Foundation types and empty session

Deliver:

- strong IDs with invalid sentinels and explicit underlying conversions;
- typed quantities for money, price, rate, ticks, and counts;
- stable error code taxonomy and `Status`/`Result`;
- owned byte buffers, immutable views, and aligned monotonic arena;
- `EngineSession` create/destroy/version/identity lifecycle;
- allocation, overflow, alignment, and lifecycle tests.

Acceptance:

- strong IDs do not implicitly mix;
- incompatible units do not compile in negative compile probes;
- arena allocation is aligned, bounded, and resettable;
- invalid allocation and lifecycle requests return typed failures;
- no C++ exception crosses the C boundary.

### M1-03 — Deterministic generated contracts

Inputs:

- the M0 config, policy, shock, metric, observation, phase, RNG, event,
  invariant, controller, desktop protocol, and scenario inventories;
- M0 aliases and the M0 aggregate contract hash.

Checked outputs:

- `schemas/m1/generated/contracts.json`;
- `schemas/m1/generated/python/contracts.py`;
- `native/include/macro_sim/generated/contracts.hpp`;
- `native/include/macro_sim/generated/invalid_cases.hpp`;
- `schemas/m1/invalid_contract_cases.json`;
- `schemas/m1/hashes.lock.json`.

The generator also creates explicit skeleton families for external policy,
checkpoint, and protocol contracts. Every family has stable sorted IDs,
source M0 hashes, count, ownership milestone, and generated enum/index tables.

Acceptance:

```bash
uv run python tools/m1/generate_contracts.py --check
git diff --exit-code -- schemas/m1 native/include/macro_sim/generated
```

### M1-04 — Philox and portable sampling

Deliver:

- Philox4x32-10 block and counter stream;
- deterministic `u32`, `u64`, open/closed uniform, Bernoulli, bounded integer,
  choice, shuffle, sample-without-replacement, normal, and Poisson primitives;
- explicit stream/key/counter inputs;
- checked integer and IEEE-754 bit-pattern vectors;
- Python reference vector generator and C++ vector tests.

Acceptance:

- Random123 Philox known-answer vectors pass;
- checked vectors match C++ and Python;
- bounded draws show no modulo operation in their implementation;
- sequence results are independent of host endianness;
- CI runs the same vector tests on macOS, Linux, and Windows.

### M1-05 — C ABI and Python binding

Deliver:

- versioned public C header;
- create/destroy/session-id/tick/version/status APIs;
- installed C-only linker smoke;
- nanobind `_native` module with `EngineSession`;
- scalar contract validation through both C++ and Python binding paths.

Acceptance:

- C smoke includes no C++ header and links the installed library;
- repeated create/destroy and null/error paths pass under sanitizers;
- `_native` can be imported from an installed wheel outside the repository;
- an installed wheel can create and destroy a session;
- the extension does not import the Python simulation engine.

### M1-06 — Canonical encoding and checkpoint ADR

Deliver:

- `CanonicalEncodingVersion = 1`;
- exact canonical JSON rules and corruption corpus;
- pinned dependency/license/SHA records for JSON, FlatBuffers,
  ZIP/deflate, SHA-256, and NPY/NPZ;
- an executable FlatBuffers checkpoint-envelope prototype;
- size/time, schema-evolution, and corruption evidence;
- ADR selecting the M2 checkpoint representation and boundary rules.

Acceptance:

- duplicate keys, nonfinite numbers, invalid UTF-8, unknown required fields,
  noncanonical integer/float encodings, truncation, and checksum corruption
  are rejected;
- Unicode and endian boundary vectors are checked;
- prototype bytes and semantic digest are reproducible;
- dependency report is stable and contains license plus immutable source
  identity for every native dependency.

### M1-07 — CI and installed artifacts

Deliver:

- native CI matrix for macOS, Linux, and Windows;
- warnings-as-errors build;
- normal native tests and RNG/ABI tests on every platform;
- ASan/UBSan job on supported Unix platforms;
- wheel build and installed-wheel smoke;
- source distribution/offline-input and SBOM checks;
- format/tidy hooks that fail clearly when tools are unavailable locally.

Cross-platform results are accepted only from CI artifacts produced by the
same commit and contract hash.

### M1-08 — Gate graph and freeze

Deliver:

- `schemas/m1/manifests/gates.yaml`;
- deterministic M1 final audit;
- PR, nightly, milestone, and release classes;
- normalized repeatability comparison using the M0 artifact framework;
- checked M1 contract and source hashes.

Local milestone acceptance:

```bash
uv run python scripts/cpp_migration/run_m0_gate.py \
  --manifest schemas/m1/manifests/gates.yaml \
  --class milestone \
  --artifact-root artifacts/migration/m1-milestone
```

## 4. Commit sequence

1. `docs: define M1 native foundation execution plan`
2. `build: add native CMake and Python packaging foundation`
3. `feat: add native foundation types and empty session`
4. `feat: generate M1 native contract skeletons`
5. `feat: add Philox and portable sampling primitives`
6. `feat: expose versioned C ABI and nanobind session`
7. `docs: decide M1 canonical encoding and checkpoint format`
8. `ci: add native cross-platform build and wheel gates`
9. `test: freeze M1 native foundation gate`

Commits may be split further when a generated-output or packaging change needs
independent review, but economic implementation is not allowed into M1.

## 5. Local acceptance matrix

| Gate | Required result |
|---|---|
| bootstrap | tool versions and Python 3.12 accepted |
| generation | byte-identical checked outputs |
| debug | configure/build/CTest pass |
| release | configure/build/CTest/benchmark smoke pass |
| sanitizer | ASan/UBSan CTest pass |
| installed C ABI | C-only executable links and runs |
| wheel | isolated installed import/session lifecycle pass |
| invalid corpus | Python/C++ status and error code match |
| RNG | all integer and float-bit vectors match |
| checkpoint prototype | deterministic, evolvable, corruption-safe |
| SBOM | deterministic and complete |
| Python regression | full suite green |
| final audit | clean tree, M0 ancestor, all hashes current |

## 6. Freeze and integration

After local and required CI gates pass:

1. run the milestone graph repeatedly from clean worktrees;
2. compare normalized evidence trees;
3. fast-forward `refactor/cpp-engine-v33` to the accepted M1 commit;
4. tag the commit `m1-native-foundation-v33`;
5. retain `refactor/cpp-m1-v33` and its worktree as the milestone audit branch.

No merge to `dev` occurs as part of M1.
