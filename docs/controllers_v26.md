# v26 — Policy Controllers: institutions, not functions

**Status**: design FROZEN pending user review of the C1 per-lever table.
**Branch**: `feat/controllers-v26` (off `feat/policy-module`; requires the v25 registry).
**Joint design**: user architecture proposal (2026-07-18) merged with the seat/occupant
draft; disagreement resolutions recorded in §11.

## 0. The one-sentence design

> A Controller does not "control the economy" — it **plays a policy-making
> institution** constrained by information, mandate, cost, and time.
> Controllers only PROPOSE; the PolicyCoordinator owns permission, schedule,
> cost, joint validation, and execution. Humans, heuristics, and RL all go
> through the same channel — same observations, same costs, same rules.

## 1. Pipeline

```
Economy/World state
    ↓
ObservationService     — what THIS institution is allowed to see, when
    ↓
DecisionScheduler      — is there a regular meeting / emergency session now?
    ↓
Controller (occupant)  — human queue | rule | heuristic | random | RL
    │                    emits PolicyProposal(actor_role, actions, reason)
    ↓
PolicyCoordinator      — mandate check, cost check, cooldown/min-hold,
    │                    joint validation, approval; REJECTS or ACCEPTS whole
    ↓
PendingPolicyQueue     — accepted proposals wait for effective_tick
    ↓
PolicyExecutor         — at effective_tick: apply_action_batch(...) (v25 API,
    │                    UNCHANGED — the only execution primitive in the system)
    ↓
Policy / ExternalPolicy
```

Nothing writes policy state except `apply_action_batch`. The frontend, RL,
and every controller in this document sit ABOVE the Coordinator. Direct field
assignment (`econ.policy.x = v`) remains for tests only.

## 2. Institutions (seats) and occupants

A **seat** is a mandate + calendar + information scope, per economy. An
**occupant** is whoever currently makes that seat's decisions. Occupants are
hot-swappable mid-run (a player takes over the central bank; hands it back to
the Taylor rule) — this IS the frontend contract.

P0 seats (per economy):

| seat (`owner_role`) | mandate (lever families) | regular cadence |
|---|---|---|
| `central_bank` | monetary_regime, manual_policy_rate, Taylor params, sensor params, OMO family, reserve/duration rules | 45 ticks |
| `treasury` | tax family, benefits/JG, deficit & investment, debt management (bond_*), land fees | 91 ticks (rate-like) / 365 (structural tax regime) |
| `regulator` | bank capital/exposure/resolution, mortgage regulation, haircuts, DSCR, insolvency & eviction law, unified RWA | 91 ticks |
| `external` | capital_control, tariffs/quotas/subsidies, sanctions, migration & remittance policy, fx_regime/peg family, settlement fraction | 91 ticks + event-driven |

`owner_role="energy"` is RESERVED in the enum (SPR/rationing/price caps are
not engine mechanisms yet — the shock arc will create them); until then the
few live energy levers (soe_efirm, soe_price_at_cost, energy taxes/subsidies)
sit under `treasury`/`external` per the C1 table.

Occupant types: `NullOccupant` (do nothing — bit-identity contract),
`RuleOccupant` (the built-in automatic institution, see §3),
`ScheduledOccupant` (scripted timeline), `HeuristicOccupant`,
`RandomOccupant` (test/fuzz), `HumanQueueOccupant` (§7), `RLOccupant` (§8).
A human player may hold several seats at once; seats in one world may be held
by a mix (human treasury + RL central bank + heuristic external).

## 3. Three layers of time

1. **Automatic institutions (every tick, no controller involved)** — laws
   already passed: the Taylor rule, LoLR, automatic benefits, OMO rules,
   JG. Occupants CHANGE these regimes at meetings; they do not re-approve
   them daily. (Engine reality already matches: `monetary_regime="taylor"`
   is the rule-occupant; `"manual"` is the seat deciding directly.)
2. **Regular meetings** — the DecisionScheduler wakes a seat only on its
   calendar ticks. Decisions hold until the next meeting (min_hold enforces
   this even across occupants).
3. **Emergency sessions** — trigger predicates (bank failure, reserve drain
   rate, inflation breach, peg pressure) fire between tick t and t+1: the
   orchestrator pauses, wakes the relevant seat(s) with an emergency
   DecisionContext, applies accepted emergency proposals, resumes. Emergency
   actions are restricted to the per-lever `emergency=True` whitelist and may
   carry a cost premium. Within-tick crises are still handled by layer-1
   standing facilities (LoLR exists BEFORE the run starts — realism note:
   central banks do not invent LoLR after the bank has died).

## 4. Policy state lifecycle

```
proposed → (approved) → pending → effective
              ↓ rejected (logged with reason)
```

- `announced` exists in the enum and the event log **as a display state
  only**. P0 agents have no forward-looking expectations, so announcement
  cannot move behavior; implementing it would be a lie. Documented
  simplification; revisit with an expectations mechanism.
- `approval_state` field exists on Proposal from day one (always
  `auto_approved` in P0) so a future parliament/voting arc extends the
  protocol instead of rewriting it.

Frontend rendering enabled by this lifecycle:

```
Income tax:  current 20% | passed 25% (effective tick 180)
Next adjustment allowed: tick 240   |   admin capacity left this quarter: 2
```

## 5. Registry schema extensions (C1)

Five new per-lever columns (the C1 deliverable is the full 102-row table for
user review — the largest economic-judgment surface in this arc):

```python
owner_role: str            # central_bank | treasury | regulator | external | (energy reserved)
decision_group: str        # monetary | fiscal | macroprudential | trade | migration | fx | ...
implementation_lag: int    # ticks from approval to effective (0 = immediate)
min_hold_ticks: int        # cooldown after an effective change
emergency: bool            # allowed in emergency sessions
```

Existing columns keep their meaning (`max_step` = gradualism bound;
`enabled_if`/`requires`; `effective_semantics` — note bond_coupon stays
NEW_CONTRACTS: the POLICY changes immediately, the stock never restates).
`ramp_ticks` (gradual phase-in, e.g. public investment) is P1 — only a few
levers need it and it adds executor complexity.

## 6. Wire protocol: absolute values + max_step

Proposals carry **absolute target values**, never deltas:

```python
PolicyProposal(
    actor_role="treasury", actor="human:player1",
    actions=[PolicyAction("tax_income_rate", 0.25),
             PolicyAction("gov_deficit_target", 0.05)],
    reason="recession_response",
    emergency=False,
)
```

Rationale (resolution of the earlier direction×step draft): absolute values
are idempotent and replayable (no base ambiguity); gradualism is enforced by
`max_step` validation; the coarse "one notch up/down" EXPERIENCE lives in the
presentation layers — frontend ± buttons compute target values, the RL
adapter discretizes to {−step, 0, +step} and converts back. The protocol
stores values; vocabularies are surfaces.

## 7. Human control: queue, never blocking

The kernel never waits on stdin. `HumanQueueOccupant` drains a ProposalQueue
that the frontend fills; the ORCHESTRATOR (not the engine) decides pausing:

- **Interactive**: auto-pause at this seat's meetings and emergencies; resume
  on decision (or explicit "no action").
- **Real-time**: decision deadline; timeout = policy unchanged.
- **Batch/replay**: proposals replayed from an event log, deterministic.

Frontend API contract (server arc implements; engine side ships the types):

```
GET  /policy/schema           — registry + costs + permissions (form autogen)
GET  /observation             — role-scoped PublicObservation
GET  /decisions/current       — pending DecisionContext(s) for my seats
GET  /policy/pending          — queue with effective ticks
POST /policy/proposals
POST /policy/emergency-proposals
```

All validation re-runs server-side in the Coordinator; the frontend is a
convenience, never a trust boundary.

## 8. Observation: what a policymaker is allowed to know

`ObservationService` produces role-scoped `PublicObservation`, never the
Economy object:

- published macro series with **publication calendars and lags** (GDP
  quarterly & late, CPI/unemployment monthly), rolling 30/91/365 windows,
  warm-up flags;
- current + pending policy, time since last change, remaining admin capacity;
- `permitted_actions` with machine-readable reasons for the forbidden ones
  (missing capability, cooldown, not your mandate, out of range);
- emergency bulletin when in an emergency session.

Information privileges by role: the central bank sees reserves and system
liquidity; the regulator sees per-bank stress; external sees trade/capital
flows and FX reserves; the public (and default observers) see aggregates
only. `OracleObservation` (engine truth) exists for debugging ONLY — RL and
humans both train/play on `PublicObservation`, or the trained policy holds an
information advantage no human can have.

Revision noise (first print vs revised) is P1; the Release type carries a
`revision` field from day one.

## 9. Costs: symmetric for humans and RL

Costs are Coordinator-enforced quantities, visible in the frontend and
identical in the RL observation/reward — never a reward-only fiction:

- **admin capacity** budget per quarter (K major actions);
- min-hold / cooldown (per-lever);
- per-action adjustment costs (institutional friction);
- real implementation costs where the engine has them (they already exist as
  economics, e.g. fiscal cost of subsidies);
- P1: credibility cost for regime flips (peg churn, regime whiplash).

Emergency sessions bypass the calendar but pay a premium and only touch the
emergency whitelist.

## 10. RL is a seat occupant, nothing more

```
HumanQueueOccupant ─┐
HeuristicOccupant   ├─→ PolicyProposal → PolicyCoordinator → ... → apply_action_batch
RLOccupant ─────────┘
```

The Gym adapter maps `DecisionContext` → vectors and RL actions →
`PolicyProposal`. A trained policy can replace a human seat, or co-govern a
world with humans. Episode reset uses the v24 checkpoint system (fixed .msim
snapshots as initial states). Action masking = `permitted_actions`.

## 11. Resolved disagreements (record)

1. Coordinator **layers on top of** `apply_action_batch` — one execution
   primitive, no second validation truth. (draft merged)
2. `announced` demoted to display-only in P0 — no expectations mechanism, no
   fake semantics. (user plan amended)
3. Absolute-value protocol beats direction×step encoding; coarse vocabulary
   is presentation-layer. (draft superseded by user plan)
4. EnergyController deferred: enum reserved, levers seated under
   treasury/external until the shock arc creates real energy mechanisms.
   (user plan amended)
5. External-policy timing: effective_tick releases the stance; the WORLD
   effect lands at the next coupling barrier (B5a atomic derivation) — up to
   one extra tick, shown honestly in the frontend as part of the effective
   date. (clarified)
6. Emergency whitelist is a registry column, not a separate list. (clarified)

## 12. Explicit non-goals for v1

- Parliament, elections, parties, approval votes (protocol placeholder only).
- Announcement/expectation effects (§4).
- Revision noise; ramp_ticks (P1).
- The frontend itself (server/UI arc) — v26 ships the engine-side contract.
- Multi-seat bargaining/games between institutions.

## 13. Batches & acceptance

| batch | content | acceptance |
|---|---|---|
| C1 | registry +5 columns, **full 102-lever table** (user review gate); Proposal/Coordinator/PendingQueue/Executor on top of batch API | frontier digest EXACT with no controllers attached; coordinator rejection matrix tests (mandate/cooldown/capacity/emergency); replay: same proposal log → bit-identical run |
| C2 | 4 seats + DecisionScheduler (calendars, emergency triggers + pause orchestration); Null/Scheduled/Heuristic/Random occupants | NullOccupant world = digest exact; 30y RandomOccupant wasteland ×3 seeds: zero crashes, conservation holds, all actions legal; emergency drill: reserve-drain trigger wakes external seat, orderly peg exit executes |
| C3 | ObservationService: PublicObservation v1 (publication calendar, lags, warm-up, role scoping), DecisionContext (permitted + reasons + costs) | policymaker at tick t sees only data published ≤ t; role-scope tests; forbidden-action reasons complete |
| C4 | HumanQueueOccupant + 3 run modes + Proposal API types (engine side) + full event-log replay | replay a recorded human session → bit-identical; real-time timeout = no-op; interactive pause/resume determinism |
| C5 | Gym adapter (DecisionContext↔vector, action↔Proposal, masking, checkpoint reset) | random agent via gym == RandomOccupant trajectories (same seed); masked illegal actions never reach the Coordinator |

Wasteland portraits (C2 acceptance) feed the standing 30y bug-hunting loop
immediately — random-but-legal policy sequences reach states no hand-written
scenario does.
