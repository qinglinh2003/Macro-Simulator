# M10/M11 Acceptance Record

## Scope and branch

- Repository: `qinglinh2003/Macro-Simulator`
- Working branch: `refactor/cpp-m11-v34`
- Code acceptance commit: `19062454d83e49641212625c187ad941838064fb`
- Hosted CI: <https://github.com/qinglinh2003/Macro-Simulator/actions/runs/30377446044>

This document is retained as the completed release trace for M10 and M11.
The hosted platform matrix succeeded for the code acceptance commit.

## Locally accepted evidence

- The M11 release preset passed all 74 tests with eight workers.
- M10 P0, P1, P2, P5, and the P7 ten-year longevity gate passed on a clean
  macOS arm64 tree at the code acceptance commit.
- The M11 P3 desktop responsiveness gate passed on that same clean tree.
- The packaged Godot tests cover normal play, policy update, crisis, save/load,
  worker crash, launcher crash, and runtime cleanup.

## Hosted release matrix

The hosted matrix verifies Linux, macOS, and Windows builds; stable-ABI wheels;
packaged Godot applications; sanitizers; coverage; formatting; and static
analysis. The final result is recorded in the M10 and M11 acceptance documents.

## Finalization result

All 15 hosted jobs passed: Linux, macOS, and Windows wheels; packaged Godot
products; ASan, UBSan, and TSan; coverage; formatting; and clang-tidy. The
Windows wheel passed isolated CPython 3.12 and 3.14 smoke tests with the
static zlib dependency selected by CMake.
