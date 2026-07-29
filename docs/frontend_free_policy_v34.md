# Free Policy Frontend v35

Status: implemented on the native desktop path.

## Product contract

The desktop client is an unrestricted simulation console, not a governance game.
Every policy lever registered by the engine remains visible. A player may replace
the value of any installed, in-domain lever at any clean day boundary.

Editing a control replaces that lever in a single next-day batch. The current
simulation day is immutable. Immediately before the next day is simulated, the
engine validates and atomically commits the complete batch; that day's economic
dynamics therefore use the new values.

## Removed governance rules

Free policy mode does not use:

- policy seats as permissions;
- meetings or decision windows;
- proposals, votes, or emergency whitelists;
- administrative capacity or adjustment cost;
- implementation lag, cooldown, minimum hold, or controller maximum step;
- human, heuristic, scheduled, fuzz, or RL seat occupants.

The policy-area tabs remain as navigation only. Existing dashboards, household,
firm, market, world, bulletin, and timeline visualizations are unchanged.

## Invariants retained

Removing governance does not permit invalid engine state. The runtime still
enforces:

- registered value types, nullability, and absolute domains;
- capabilities required by the configured economy and world;
- linked-policy requirements such as manual monetary regime plus a manual rate;
- state-transition handlers, external-policy caches, ledgers, and world-level
  exchange-rate and peg invariants;
- atomic application: a failed batch does not partially mutate the live world.

## Protocol

Desktop protocol v5 exposes:

- `control_mode: "free_policy"` in schema and snapshots;
- `stage_policy`, whose `actions` array replaces the complete next-day batch;
- `free_policy`, containing `enabled`, `effective_tick`, and staged `actions`;
- free-policy lifecycle verdicts: `staged`, `cleared`, and `effective`.

The runtime retains controller mode for non-desktop consumers. The desktop server
constructs the runtime in free policy mode by default.

Playback is interruptible at every day boundary. The speed buttons control how
often Godot requests one simulated day; they no longer turn a high speed into one
opaque multi-day desktop request. Explicit protocol clients may still request a
larger interval, but controller decision calendars never interrupt that interval
in free-policy mode.

## New simulation flow

The start flow now has five steps: scenario, world, countries, initial policy, and
review. Seat assignment and meeting-mode configuration are not shown or serialized
as active controllers; compatibility seat fields are emitted as `null` occupants.

## Acceptance criteria

1. Staging does not change the current tick or live policy value.
2. Advancing one day applies the complete batch before that day's simulation.
3. A change may exceed controller step, lag, cost, and hold metadata.
4. Invalid linked batches fail atomically and remain editable.
5. The client never pauses merely because a policy is edited.
6. No meeting, seat permission, emergency whitelist, or administrative limit
   blocks a desktop policy control.

## Acceptance evidence

- Native protocol coverage proves staging, next-day effectiveness, linked-policy
  rejection without partial mutation, uninterrupted bulk advance, and staged
  action save/load.
- Godot-to-native coverage creates a real world, stages a fiscal policy at day
  zero, advances one day, observes the new live value, and confirms that no human
  decision context pauses the session.
- The complete `m11-release` suite passes with 74 tests and eight workers.

## Converged follow-up plan

### S1 — Finish the sandbox player loop

- Add a player-facing save browser, autosave, and reliable continue flow.
- Enforce the configured end date in the runtime and produce an end-of-run report.
- Replace raw engine validation errors with linked-policy explanations and direct
  navigation to the missing companion control.
- Add undo/reset for the complete staged next-day batch.

Exit criterion: a player can create, run, modify, save, resume, and finish a
simulation without using a terminal or interpreting an engine identifier.

### S2 — Make policy experiments legible

- Draw policy-effective markers on relevant charts and the event timeline.
- Add before/after windows, run notes, and a compact change history.
- Allow a save to be cloned into two branches and compare their released
  indicators without exposing future information.
- Export a reproducible run manifest and selected time series.

Exit criterion: a player can answer what changed, when it changed, and how two
policy paths differed.

### S3 — Improve explanation without pretending certainty

- Add baseline forecasts, nowcasts, revisions, and uncertainty displays.
- Separate observed correlation, engine accounting decomposition, and inferred
  policy attribution.
- Surface representative households and firms selected from real engine state.

Exit criterion: the interface explains plausible transmission paths while clearly
distinguishing facts, estimates, and counterfactuals.

### S4 — Prototype optional game layers

- Build scenario challenges and long-form country management above the generic
  engine action/observation interface.
- Keep political capital, mandates, implementation delays, objectives, and
  victory conditions in a removable game-rules layer.
- Preserve this unrestricted sandbox as a permanent product mode and regression
  oracle for every constrained mode.

Exit criterion: game rules can be enabled or removed without changing economic
engine invariants or the free-policy protocol.
