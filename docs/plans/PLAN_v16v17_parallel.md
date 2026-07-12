# V16 ∥ V17 Parallel Development Protocol

> **Audience:** both development agents (v16 labor, v17 energy). This document is the
> coordination contract. Read it TOGETHER with your own plan (PLAN_v16.md /
> PLAN_v17.md) before writing any code. It amends PLAN_v17.md's sequencing note
> ("v17 starts after the v16 arc") — the arcs run IN PARALLEL under the rules below.

**Verdict from the collision analysis:** the two arcs are parallel-safe. Each is a
"new module + hooks" structure; the modules (labor rosters/matching vs energy
sector/market) are disjoint, and the hooks collide in exactly three places — the labor
phase core loop, the B3 unit-cost formula, and the economy.step phase order. All three
are removed by ONE shared trunk refactor done BEFORE the branches fork. Everything
else reduces to file ownership plus an append-only protocol on four thin shared files.

## 0. Preconditions (state as of writing)

- dev = v14 complete (Phase 2+3 accepted).
- feat/housing-v15 = v15.0–15.5 complete, pending final gates + merge into dev.
- PLAN_v17.md currently sits UNTRACKED in the main checkout — the v17 agent commits it
  on the v17 branch as their first commit.
- **Nothing in this protocol starts until v15 is merged into dev AND the trunk
  refactor (§1) has landed on dev.**

## 1. The trunk refactor (one commit on dev, BEFORE forking — owner: v16 agent)

A bit-identical mechanical refactor both arcs require. Scope, exactly three items:

1. **Split production out of the labor phase.** `run_labor_phase` currently computes
   `f.produced` and folds `f.inventory += f.produced` at hire time (labor.py:60-61).
   Extract a `run_production_phase(econ)` that does production + inventory folding;
   the labor phase becomes hiring only. v16 needs the labor phase pure (matching);
   v17 needs to insert the energy market BETWEEN hiring and production
   (`y = min(a·L, energy/e_coeff)` needs energy bought first).
   NOTE: v15.4 builders reverse the generic inventory fold into `firm.wip`
   (housing/construction.py) — that reversal must keep working; move it or key it to
   the new phase, and re-run the housing batch.
2. **Extract the unit-cost helper.** B3's unit cost (`wagebill/produced` uses, e.g.,
   behavior/planning.py:110) becomes one small function `unit_cost(firm)` with the
   wage term on its own line. v16-L3 changes the wage side; v17.0 appends an energy
   term (`+ energy_used @ avg_cost`). Two lines, two owners, trivially mergeable.
3. **Fix the phase-order anchor points.** economy.step gains explicit comment anchors:
   `# [ANCHOR: post-labor]` (v17 inserts the energy market here),
   `# [ANCHOR: production]` (the new phase), so both agents insert single lines at
   named points instead of diffing against each other's context.

Acceptance for the refactor commit: full suite green + same-seed 400t smoke
BIT-IDENTICAL to dev (this is a pure reshuffle; any cell diff is a bug) + housing
batch green (builder WIP reversal intact).

## 2. Branch & worktree mechanics

```
dev (v15 merged + trunk refactor)
 ├─ feat/labor-v16   worktree ../macro-simulator-v16   (v16 agent)
 └─ feat/energy-v17  worktree ../macro-simulator-v17   (v17 agent)
```

- `git worktree add ../macro-simulator-<arc> -b feat/<arc> dev`
- Run tests with cwd = your worktree (cwd precedes the editable install on sys.path;
  scripts launched by absolute path need `PYTHONPATH=$(pwd)` — see the v15 sessions).
- Push your branch after every accepted stage (remote backup discipline).

## 3. File ownership map

| Surface | Owner | The other agent |
|---|---|---|
| labor.py, new labor module (rosters/matching/suspension), lifecycle/JG labor hooks | **v16** | do not touch |
| new energy module (E-firms, energy market, SPR, rationing), goods-side energy hooks | **v17** | do not touch |
| behavior/planning.py `unit_cost()` | shared | wage line = v16, energy line = v17; never reorder the function |
| economy.py step | shared | single-line insertions at YOUR named anchor only |
| config/model.py, core/policy.py | shared | append your own field block + validator block; never edit inside the other arc's block |
| reporting/metrics.py | shared | append your own `rec.update({...})` block |
| systems/settlement.py, credit.py | v16 primary | v17 announces before touching (energy excise remit may need a settlement line — coordinate) |
| demographics/* | v16 (person-level income attribution) | v17 reads gauges only |

Shared-file conflicts under this protocol are block-ordering conflicts only — resolve
by keeping BOTH blocks (the v15 merge of exactly this kind took minutes).

## 4. Discipline both agents inherit (non-negotiable, from the v13–v15 arcs)

- Every stage flag-gated, default off; flag-off same-seed 400t smoke BIT-IDENTICAL to
  the shared post-refactor baseline (NOT to your branch's previous stage only —
  cumulative discipline).
- New randomness on dedicated substreams (`seed + offset`); never perturb the main
  stream's consumption order.
- All annual rates applied as rate/365, never scaled twice (the v13 365x lesson).
- Every asset/claim-touching flow is atomic and posted through the person-claim APIs;
  the claim identity and stock-flow gates stay lethal in your runs. Expect the gates
  to catch 1–2 real bugs per arc (they did in every arc so far); that is them working.
- Per-stage diagnostic png + honest acceptance write-ups (nulls reported as nulls).
- No Co-Authored-By trailers in commits.

## 5. Merge order & the composition gate

1. **v16 merges into dev first** (core-loop depth outranks module breadth). v16
   stage-freezes are announced; **v17 rebases (or merges dev) at each v16 freeze** —
   小步跟进, never one big-bang reconciliation at the end.
2. After BOTH arcs land, a **composition acceptance** runs (owner: whichever agent
   merges second):
   - both-flags-on same-seed smoke: no gate violations;
   - the pinned cost-push test (17.0) re-run WITH relationship wages (v16-L3) on:
     energy price up ⇒ unit costs up ⇒ prices up while incumbent wages ratchet —
     the wage-price spiral plumbing verified end to end;
   - stock-flow labor gate green with the energy sector hiring (E-firms are ordinary
     employers on v16 rosters — no special-casing).
3. **The 17.2 stagflation experiment matrix runs AFTER the composition gate**, not
   before. PLAN_v17.md already disclaims frictionless-labor employment readings and
   mandates a re-run; running the matrix once, after composition, with the disclaimer
   DELETED, is strictly cheaper and is the payoff of parallelizing. (17.0/17.1
   plumbing acceptance is unaffected and proceeds inside the v17 arc.)
4. The v17 agent's runs before composition use dev-at-fork labor (spot market). That
   is fine for 17.0–17.1 acceptance: their gates are accounting/plumbing/quietness,
   not employment readings.

## 6. Communication protocol (minimum viable)

- A shared `docs/plans/PARALLEL_LOG.md` (append-only, one line per event): stage
  freezes, dev merges, shared-file touches outside your blocks, gate failures that
  implicate the other arc's surface.
- If a change you need crosses the ownership map (e.g., v17 needs a settlement hook),
  write the request in the log first; the owner lands it in their branch or blesses
  the patch. Do not land cross-surface changes silently.

## 7. What can go wrong anyway (known residual risks)

- **Baseline drift**: both arcs verify bit-identity against the post-refactor dev; if
  a hotfix lands on dev mid-arc, BOTH agents re-anchor (re-run their flag-off smoke)
  before their next stage freeze.
- **Perf interference in shared runs**: both arcs run heavy sims on this machine —
  coordinate big runs in the log; keep ≤3 concurrent heavy processes (thermal
  suspension history on this host; use caffeinate for overnight batches).
- **The unit-cost function is the one true shared hot spot** — if either arc needs to
  restructure it beyond its own line, that is a trunk change: stop, log, coordinate.
