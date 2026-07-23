# Design Documentation

Version `v33` · Status: **v124 Python oracle; C++20 migration M0 in progress**

This directory is organized for development, not chronology. Start with the
short current-state documents, then drill into durable rules or historical arcs
only when the change needs them.

## Read First

1. [`current/developer-brief.md`](current/developer-brief.md) — the 10-minute brief: current frontier, invariants, active gaps.
2. [`current/development-rules.md`](current/development-rules.md) — rules to follow before changing model behavior.
3. [`current/module-map.md`](current/module-map.md) — where each economic subsystem lives conceptually and which history file explains it.
4. [`current/refactor-review.md`](current/refactor-review.md) — current code-architecture risks after the package refactor.
5. [`core/`](core/README.md) — durable design law: accounting, behavior, markets, validation discipline.
6. [`history/`](history/README.md) — research arcs, falsified hypotheses, diagnostics, and full changelog.

## Directory Map

| Directory | Use it for | Stability |
|---|---|---|
| [`current/`](current/README.md) | The first-stop development guide and active architecture map. | Updated whenever the frontier changes. |
| [`core/`](core/README.md) | Rules that should survive versions: axioms, scheduling, validation, kernel discipline. | High; change only after deliberate design review. |
| [`history/`](history/README.md) | Version arcs, experiment findings, reversals, old plans, and changelog. | Archival; preserve evidence even when conclusions change. |

## Task-Based Reading

| If you are changing... | Read first | Then read |
|---|---|---|
| Ledger, money, loans, bonds, reserves | [`core/01-accounting-axioms.md`](core/01-accounting-axioms.md), [`current/development-rules.md`](current/development-rules.md) | [`history/arcs/09-banking-securities.md`](history/arcs/09-banking-securities.md) |
| Agent behavior or parameters | [`core/02-behavioral-axioms.md`](core/02-behavioral-axioms.md) | The relevant arc under [`history/arcs/`](history/arcs/README.md) |
| Market clearing, scheduling, matching | [`core/03-market-institutional-axioms.md`](core/03-market-institutional-axioms.md) | [`history/arcs/06-firms-competition-equity.md`](history/arcs/06-firms-competition-equity.md) |
| Kernel or validation harness | [`core/04-validation-roadmap-kernel.md`](core/04-validation-roadmap-kernel.md) | [`history/arcs/05-kernel-findings-v2-v3.md`](history/arcs/05-kernel-findings-v2-v3.md) |
| Firms, competition, entry/exit | [`current/module-map.md`](current/module-map.md) | [`history/arcs/06-firms-competition-equity.md`](history/arcs/06-firms-competition-equity.md) |
| Households, portfolios, wealth | [`current/module-map.md`](current/module-map.md) | [`history/arcs/07-households-portfolios-equity.md`](history/arcs/07-households-portfolios-equity.md) |
| Fiscal, welfare, labor, central bank | [`current/developer-brief.md`](current/developer-brief.md) | [`history/arcs/08-government-labor-monetary.md`](history/arcs/08-government-labor-monetary.md) |
| Banks, reserves, securities, OMO/QE/LoLR | [`current/developer-brief.md`](current/developer-brief.md) | [`history/arcs/09-banking-securities.md`](history/arcs/09-banking-securities.md) |

## Status Tags

- **Canon:** durable rule or discipline; do not casually override.
- **Active Spec:** current architecture or intended behavior.
- **Finding:** empirical/diagnostic result from a run or sweep.
- **Archive:** preserved context, including falsified priors and superseded plans.
