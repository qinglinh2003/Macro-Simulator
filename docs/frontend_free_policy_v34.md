# Free Policy Frontend v34

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

Desktop protocol v4 adds:

- `control_mode: "free_policy"` in schema and snapshots;
- `stage_policy`, whose `actions` array replaces the complete next-day batch;
- `free_policy`, containing `enabled`, `effective_tick`, and staged `actions`;
- free-policy lifecycle verdicts: `staged`, `cleared`, and `effective`.

The runtime retains controller mode for non-desktop consumers. The desktop server
constructs the runtime in free policy mode by default.

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
