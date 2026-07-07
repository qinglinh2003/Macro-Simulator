# Core Design

This directory holds durable design law. These files should be read as the
model's constitution rather than as a version log.

| File | Role | Stability |
|---|---|---|
| [`00-purpose-notation.md`](00-purpose-notation.md) | Purpose, epistemic stance, status tags, notation. | Canon |
| [`01-accounting-axioms.md`](01-accounting-axioms.md) | A1-A5 accounting and stock-flow invariants. | Canon |
| [`02-behavioral-axioms.md`](02-behavioral-axioms.md) | B1-B7 behavioral primitives. | Canon / active spec |
| [`03-market-institutional-axioms.md`](03-market-institutional-axioms.md) | M0-M3 market, money, and scheduling rules. | Canon / active spec |
| [`04-validation-roadmap-kernel.md`](04-validation-roadmap-kernel.md) | Held-out validation, kernel specification, parameter budget, handoff discipline. | Canon plus early kernel spec |

If a rule here must change, update [`../current/developer-brief.md`](../current/developer-brief.md)
with the new operational consequence and preserve the old reasoning under
[`../history/`](../history/README.md).
