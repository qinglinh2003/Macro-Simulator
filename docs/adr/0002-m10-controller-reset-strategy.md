# ADR 0002: M10 controller reset uses an isolated deep native clone

## Status

Accepted for M10.

## Context

Controller and RL episode reset must reproduce the complete native economic,
metric-history, and controller-envelope state. The reset path must also remain
well below the frozen 250 ms p95 budget at 100,000 persons. Two implementation
families were considered:

1. restore every episode from the structured portable checkpoint; or
2. keep an immutable genesis composite and clone its native stores.

A copy-on-write store was also considered as an optimization of the second
option. It adds shared-page ownership, first-write detachment, and additional
fault-isolation states to every mutable store.

## Measurement

The release-build `tools/m10/performance_gate.py` probe constructs the complete
current engine at 100,000 persons, advances one day, and performs 20 isolated
native composite clones. On the M5 MacBook Pro development host the preliminary
measurement was approximately 3.2 ms median and 3.9 ms p95, with about 67.8 MiB
of capacity-accounted native state per clone. The same state took approximately
850 ms to parse from a 36.7 MiB structured checkpoint.

The checked acceptance artifact records the exact commit, platform, sample
distribution, state size, and command. The 250 ms requirement is enforced by
the M10 performance gate rather than by the preliminary numbers in this ADR.

## Decision

M10 keeps an immutable native genesis session and resets an episode by making a
deep native composite clone. Structured checkpoints remain the durable,
language-neutral save and interchange format; they are not the hot reset path.

Copy-on-write is deferred. The measured deep clone has substantial budget
headroom, has straightforward ownership, and preserves independent mutation and
fault isolation without shared-page rollback rules.

## Consequences

- Reset cost scales with live native capacity, but is explicitly measured.
- Each concurrently live environment owns its full mutable state.
- A failed environment cannot corrupt another environment or the genesis root.
- Checkpoint encoding changes cannot alter episode-reset behavior.
- Copy-on-write must be reconsidered if a future supported scale or vector batch
  fails the checked reset or memory budget.
