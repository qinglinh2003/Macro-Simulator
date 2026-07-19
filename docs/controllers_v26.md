# v26 — Policy Controllers: institutions, not functions

**Status**: IMPLEMENTED AND LOCALLY ACCEPTED — C1–C5 engineering and the complete
repository regression suite passed on 2026-07-18. The C1 lever and C3 observation
tables are the frozen P0 contracts for this implementation and may be reopened by a
later economic ruling.
**Branch**: `feat/controllers-v26` (off `feat/policy-module`; requires the v25
registry and batch mutation API).
**Design rule**: engine facts outrank prose. Any later implementation finding that
contradicts this document reopens the affected ruling instead of being hidden behind
compatibility code.

## 0. The one-sentence design

> A Controller does not "control the economy" — it occupies a policy-making seat
> constrained by information, authority, objective, cost, and time. Controllers only
> PROPOSE. A world-aware PolicyCoordinator owns scheduling, permission, approval,
> joint validation, pending state, and execution. Humans, heuristics, and RL use the
> same observations, costs, and proposal protocol.

The v26 boundary is deliberately institutional:

- `Policy` / `ExternalPolicy` are effective state;
- occupants decide, but never mutate that state;
- standing mechanisms execute effective policy every tick;
- the Coordinator is the single external gateway for humans, scripts, and AI;
- frontend vocabulary and Gym encodings are presentation adapters, not engine APIs.

## 1. Pipeline and execution authority

```text
Economy/World state
    ↓
ReleaseService          — publishes only information available by this boundary
    ↓
DecisionScheduler       — opens a regular or server-authorized emergency context
    ↓
ObservationService      — builds THIS seat's versioned DecisionContext
    ↓
Controller occupant     — human queue | scheduled | heuristic | fuzz | RL
    │                     emits a PolicyProposal against that context
    ↓
PolicyCoordinator       — authority, procedure, cost, pending conflicts,
    │                     projected timeline, and joint World validation
    ↓
PolicyDecision          — rejected | accepted_pending | accepted_noop
    ↓
PendingPolicyQueue      — accepted decisions wait for effective_tick
    ↓
WorldPolicyTransaction  — prepare ALL due decisions without mutating live state
    ↓
PolicyExecutor          — atomically commits the prepared World transaction
    ↓
Policy / ExternalPolicy + World derived state + versions + canonical events
```

### 1.1 One validation truth, two execution scopes

The v25 `apply_action_batch(econ, ...)` is the low-level, single-economy batch
primitive. It cannot by itself make a multi-economy decision atomic. v26 therefore
adds a world-level transaction boundary:

```python
prepared = prepare_world_policy_transaction(session, due_decisions)
commit_world_policy_transaction(session, prepared)
```

`prepare` is pure. It reuses Registry validators and transition specifications; it
does not duplicate field validation in the Coordinator. It must construct projected
Policy and ExternalPolicy views for every affected economy and validate:

1. canonical names, strict types, ranges, capabilities, `enabled_if`, and handlers;
2. authority, decision context, cooldown, min-hold, max-step, and admin capacity;
3. pending conflicts and the projected effective timeline;
4. dynamic references such as sanctions targets;
5. joint World constraints such as peg count, anchor validity, and cycles;
6. all transition side effects and World cache changes required at commit.

`prepare` first classifies individually stale/invalid decisions and minimal joint
conflict sets without mutating live state. Those decisions become
`failed_at_execution`; unrelated due decisions are prepared together. `commit` is
all-or-none across that prepared transaction. A commit failure must leave Policy,
ExternalPolicy, World vectors/caches, PegState, ledgers, cost budgets, versions,
pending status, and effective-event output untouched. Sequentially calling a mutating
per-economy API is not a World transaction.

This transaction API is an internal synchronous kernel primitive. For an interactive
server, one per-session mutex must remain held continuously from `prepare` through
`commit`; a prepared transaction must never be returned to a client, retained across
an `await`, or passed to another request/thread. Its `base_fingerprint` detects changes
to the policy/control projection used by this protocol. It is deliberately **not** a
general concurrency fingerprint for every mutable object in `World`, so it cannot
replace transport-level serialization.

Nothing outside the PolicyCoordinator/Executor path may make a discretionary policy
change. Engine-forced transitions (for example, a broken peg) use an internal system
transaction and the same version/event machinery. Genesis and executor-managed
transition committers are not frontend/controller mutation paths.

### 1.2 Known v25 integration blockers for C1

The code audit found two concrete cases that v26 must close before controllers can be
enabled:

- an out-of-range sanctions target can be copied into the World sanctions cache before
  the later domain check raises;
- handing a peg from economy 0 to economy 1 can retain the old PegState, while legacy
  single-peg accessors continue selecting economy 0.

C1 owns the pure dynamic-reference validator, atomic World cache commit, active
PegState selection/removal, and regression tests for both cases. These are not
document-only caveats: random and human controllers will reach these states quickly.

## 2. Seats, authority, and occupants

A **seat** is a reduced-form ultimate policy authority with a calendar and an
information scope, per economy. It is not a claim that every jurisdiction uses the
same ministry boundary. P0 assigns exactly one owner to every lever; joint approvals
and jurisdiction-specific institutional maps are P1 extensions.

An **occupant** is the decision strategy currently assigned to a seat. Occupant
assignment is hot-swappable and logged, but swapping occupants never changes effective
policy by itself.

P0 seats:

| seat (`owner_role`) | reduced-form authority | regular decision groups |
|---|---|---|
| `central_bank` | monetary regime/manual rate, Taylor and sensor parameters, OMO/LoLR/reserve tools; P0 also owns peg/FX operational tools where joint approval is not yet modeled | monetary ~45 ticks; liquidity is standing/event-driven |
| `treasury` | general taxes, benefits/JG, deficit/investment, debt management and land fees; energy taxes, subsidy budgets, and cap compensation | fiscal stance ~91; structural tax/law ~365 |
| `regulator` | bank capital/exposure/resolution, bond-duration limits, deposit rules, mortgages, credit haircuts/DSCR, insolvency and eviction law | macroprudential ~91; structural law ~365 |
| `external_affairs` | tariff/quota/export subsidy, sanctions, migration and remittance policy | trade/migration ~91 + event-driven |
| `energy` | SPR target/flow, energy price cap, rationing, SOE ownership and operating-price rule | energy ~91 + event-driven |

The final owner of every lever is the C1 table's user-review surface. In particular,
capital controls, external settlement, FX regime, energy compensation, and SOE policy
must be reviewed explicitly rather than inferred from source-file location.

Meeting cadence belongs to `(seat, decision_group)`, not just the seat. The numbers
above are configurable model defaults, not universal facts about real institutions.
Calendar phase/offset is part of the run spec so every economy need not meet on the
same tick.

Occupant types:

- `NullOccupant`: submits explicit no-action decisions; bit-identity baseline;
- `ScheduledOccupant`: deterministic scripted proposals;
- `HeuristicOccupant`: a meeting-time, observation-based proposal rule, not an
  engine mechanism;
- `RandomFuzzOccupant`: legal-state exploration, clearly not a realism baseline;
- `HumanQueueOccupant`: proposals supplied by the frontend;
- `RLOccupant`: trained policy using the same DecisionContext.

The built-in occupants have canonical event-replay construction specs. A logged
`initialization="fresh"` accepts only an exact built-in instance in the same initial
state produced by its construction spec: pre-consumed random RNGs and preloaded
human/RL replay queues are rejected. One live/archive occupant object cannot occupy two
seats; archive restoration preserves that identity explicitly. An application-supplied
heuristic callable or RL model remains part of the pickled session
checkpoint when it is pickle-safe, but arbitrary executable/model bytes are never put
into the JSON event stream. P0 has no arbitrary-code replay factory: an application must
reconstruct a trusted custom occupant in the replay genesis outside the event tape, or
use the recorded-proposal trajectory mode described in section 11. Canonically logged
hot-swaps are therefore limited to occupants with built-in construction specs.

A human may hold several seats, and a world may mix occupants. One proposal belongs to
one seat/context; cross-seat coordination produces separate proposals collected at the
same boundary, not an unauthorized cross-mandate action batch.

### 2.1 Standing mechanism is not an occupant

Taylor rate setting, an already-enabled LoLR, automatic benefits/JG, OMO rules, and
SPR rules execute every tick from effective policy state. They are standing
mechanisms; no occupant is invoked to re-approve them daily.

`monetary_regime="taylor"` is policy state, not a `HeuristicOccupant`.
`monetary_regime="manual"` is also policy state, not evidence that a human holds the
seat. A human can retain Taylor and change its parameters; a `HeuristicOccupant` can propose
a manual regime. Hot-swapping either occupant leaves the current regime unchanged.

## 3. Four clocks and the normative tick boundary

v26 distinguishes four clocks:

1. **simulation clock** — market/accounting mechanisms run each tick;
2. **release clock** — data become observable according to publication rules;
3. **decision clock** — decision groups meet on regular or emergency calendars;
4. **effective clock** — approved actions land after their implementation lag.

Define `world.t` as the next tick not yet executed. The normative boundary is:

```text
BOUNDARY(t)
1. Publish releases due at t and evaluate triggers from state completed through t-1.
2. Open regular/emergency DecisionContexts for boundary t and build their
   role-scoped observations.
3. Collect proposals from ALL due seats/economies without mutating simulation state.
4. Jointly approve/reject proposals; enqueue decisions.
5. Prepare and atomically execute every decision with effective_tick == t,
   including newly approved implementation_lag == 0 decisions. The transaction
   includes transition side effects and the ExternalPolicy-derived World view.
6. Run and record simulation tick t; advance world.t to t+1.
```

Therefore `effective_tick=t` means the policy affects the first applicable read in
tick `t`, for domestic and external levers alike. There is no undocumented extra tick
for ExternalPolicy. Interactive pause occurs inside `BOUNDARY(t)` before step 5; while
paused, ticks, records, RNGs, pending effective state, and event cursors do not advance.

An event arising inside tick `t` can first open a discretionary human/AI emergency
session at `BOUNDARY(t+1)`. Same-tick protection must come from standing facilities
already in force. This is intentional: the model must not let a policymaker observe a
failure and travel backward within the same tick to prevent it.

### 3.1 Emergency trigger state machine

An emergency is server-issued, never client-declared. Each `TriggerSpec` defines:

```python
enter_threshold
exit_threshold          # hysteresis
min_persist_ticks
cooldown_ticks
context_expiry_tick
authorized_seats
```

Triggers fire on a threshold transition/re-arm, not every tick while a condition stays
true. Leading stress signals are preferred:

- bank liquidity/withdrawal coverage and capital stress;
- peg reserve coverage and prospective drain;
- energy stock coverage, unfilled demand, or a supply shock;
- persistent inflation/financial instability breaches where explicitly configured.

`bank_failure` may trigger an aftermath context, but it is too late to be the rescue
trigger. Emergency contexts bypass the regular calendar only. A lever's
`emergency=True` flag authorizes its use; it does not silently remove max-step,
implementation lag, cost, or dynamic validation. A separate
`emergency_implementation_lag` may be declared when reality justifies faster execution.
If several distinct triggers authorize the same seat and decision group at one boundary,
each trigger receives its own context and bulletin; their administrative capacity still
comes from the same institutional calendar-cycle budget.

## 4. Decision and policy lifecycle

Approval belongs to a Coordinator decision, never to the client proposal:

```text
submitted
 ├─ rejected
 ├─ accepted_noop
 └─ accepted_pending
      ├─ effective
      ├─ failed_at_execution
      ├─ cancelled
      └─ superseded
```

An action whose canonical target equals the projected effective value becomes
`accepted_noop`: it does not change a policy version, start a cooldown, reserve admin
capacity, consume adjustment cost, or create an effective action event. The explicit
no-action/timeout input is still logged for audit/replay.

`announced` is an event/display attribute, not a mutually exclusive lifecycle state.
P0 agents have no forward-looking expectations, so an announcement does not affect
behavior. This limitation remains visible rather than pretending that a UI label has
economic semantics.

Minimum protocol objects:

```python
DecisionContext(
    context_id, decision_window_id, economy_id, seat, decision_group,
    boundary_tick, expires_at_tick, policy_versions, observation,
)

PolicyProposal(
    proposal_id, idempotency_key, context_id, actions, reason,
    based_on_policy_versions, supersedes_proposal_id=None,
)

PolicyDecision(
    decision_id, proposal_id, status, reason_code, accepted_tick,
    effective_tick, accepted_sequence, reserved_admin_cost,
)
```

Economy, seat, role, emergency authority, and authenticated actor are derived from the
server-issued DecisionContext. They are not trusted client claims.

### 4.1 Pending, concurrency, and revalidation

- One seat may have at most one active proposal per DecisionContext; replacing it
  before the window closes is idempotent and explicit.
- A pending action on the same canonical lever blocks another by default. Replacement
  requires `supersedes_proposal_id` and creates a lifecycle event.
- `max_step` and `min_hold_ticks` are checked against the projected value/timeline at
  the proposed `effective_tick`, not merely today's live value.
- Each lever has a version. Unrelated policy changes do not stale a pending decision;
  changes to touched levers or declared prerequisites do.
- The due set is revalidated jointly at execution. Failure produces
  `failed_at_execution` with no partial state change.
- If independently valid simultaneous proposals violate a joint World constraint, all
  proposals in the minimal conflicting set are rejected; unrelated proposals may
  proceed in the same prepared transaction.
- P0 supports cancellation before effectiveness. `supersedes_proposal_id` performs an
  atomic cancel-and-replace rather than exposing a race between two requests; refund
  policy is part of the CostSpec.

## 5. Registry extensions and review gates

C1 adds these per-lever fields:

```python
owner_role: str
decision_group: str
implementation_lag: int
emergency_implementation_lag: int | None
min_hold_ticks: int
emergency: bool
control_scale: float | None   # frontend step, RL normalization, cost distance
admin_weight: float
cost_class: str               # ordinary | major | regime_switch | operational
```

Existing Registry fields remain authoritative for strict types, range/nullability,
choices, capabilities, current-policy prerequisites, semantics, handlers, and
read-points.

The v25 baseline Registry contained 102 levers and declared no non-null `max_step`.
C1 now gives all 79 numeric levers a reviewed finite `control_scale` and `max_step`,
and installs the latter in the Registry validator as Controller governance metadata.
Frontend and RL adapters do not invent step sizes from raw min/max ranges.

The complete, implementation-aligned
[102-row C1 lever table](controller_levers_v26.md) is the frozen P0 review surface.
`ramp_ticks` remains P1 because a true phased implementation changes executor and
observation semantics; it must not be faked by repeated controller actions.

## 6. Wire protocol: absolute, canonical, and idempotent

Proposals carry absolute targets, never deltas:

```python
PolicyProposal(
    context_id="ctx:0:central_bank:180",
    proposal_id="client-uuid",
    idempotency_key="client-uuid",
    actions=[
        PolicyAction("manual_policy_rate", 0.0003),
        PolicyAction("monetary_regime", "manual"),
    ],
    reason="liquidity_stabilization",
)
```

Absolute targets are idempotent and replayable. Frontend +/- controls and RL
`{-step, 0, +step}` vocabularies calculate absolute values against the context's
versioned base state.

Canonical wire values are JSON-safe:

- finite JSON numbers, booleans, strings, integers, and null;
- economy sets are sorted integer arrays on the wire and immutable sets in the engine;
- aliases resolve before duplicate detection; duplicate canonical levers reject the
  whole proposal rather than "later value wins";
- actions are canonically sorted for hashing/logging; any UI display order is
  presentation-only and is not persisted in the executable proposal;
- a target equal to the projected canonical value normalizes to `accepted_noop`;
- no NaN, Infinity, Python repr, or unversioned frozenset enters the protocol.

Every request carries `schema_version`; stale contexts or policy versions receive a
machine-readable conflict response rather than silently rebasing an action.

## 7. Human control and frontend contract

The kernel never waits on stdin. `HumanQueueOccupant` consumes proposals associated
with an open DecisionContext; the orchestrator, not the engine kernel, controls pause:

- **Interactive**: a `HumanQueueOccupant` pauses at meetings/emergencies until an
  explicit proposal or no-action decision;
- **Real-time**: the transport/server owns the wall-clock deadline and calls the same
  deterministic timeout operation; no wall clock enters the simulation state;
- **Batch**: automated occupants answer contexts synchronously;
- **Replay**: the replay adapter injects recorded input events deterministically.

`run_mode` is therefore an audited execution-surface declaration, not four divergent
economic kernels. Occupant assignment and server timeout calls determine the actual
pause behavior.

Minimum server API shape (transport details belong to the server arc):

```text
GET    /runs/{run}/policy/schema?economy={id}&seat={seat}
GET    /runs/{run}/decision-contexts/{context_id}
GET    /runs/{run}/policy/pending?economy={id}
POST   /runs/{run}/decision-contexts/{context_id}/proposals
DELETE /runs/{run}/policy/pending/{decision_id}
POST   /runs/{run}/seat-assignments
```

The implemented `ControllerService` is a **privileged in-process kernel façade**, not
an authentication or authorization boundary. It intentionally accepts kernel IDs and
an already-derived actor. A future HTTP/WebSocket transport must authenticate the
principal, map that principal to allowed run/economy/seat scopes, derive `actor`
server-side, and filter schema, context, observation, and pending-decision reads to
those scopes. Client-supplied actor, economy, seat, context, or decision identifiers
are never proof of authority.

Submission uses an idempotency key. Authentication/seat assignment determines actor
and authority. The client cannot create an emergency context or choose its own role.
The server re-runs every validation; the frontend is never a trust boundary. A stale
page receives a conflict containing the latest context/policy versions. The transport
also owns a per-session mutex and serializes every proposal submission, cancellation,
seat assignment, timeout, and `advance` call. It must not expose a prepared policy
transaction across an `await` or thread boundary; `prepare` and `commit` run together
inside that same synchronous critical section.

Occupant hot-swap creates a `SeatAssignmentEvent`, is checkpointed and replayed, and
does not mutate policy. The assignment specifies how the new occupant's private state
is initialized or restored; the outgoing occupant state remains serializable if the
seat may later be handed back.

## 8. Observation contract: released information, not engine truth

The general object is `InstitutionObservation`, because regulator/central-bank data
may be confidential or operational. `PublicObservation` is its public subset.

Each release contains at least:

```python
Release(
    series_id, value, reference_start_tick, reference_end_tick,
    released_at_tick, vintage, revision, access_class, missing_reason,
)
```

`access_class` is `public`, `confidential`, or `operational`. Role authorization is
server-side. At boundary `t`, an occupant can receive only releases with
`released_at_tick <= t`. Rolling indicators are built from released vintages, not from
hidden daily engine truth; otherwise a quarterly GDP series would leak the unfinished
quarter through a rolling window.

Each DecisionContext includes:

- released observations and missing/warm-up masks (never sentinel NaNs);
- a deeply immutable `current_policy` snapshot for every lever owned by this seat in
  this economy, plus `policy_versions` for those levers and their declared
  prerequisites;
- pending targets and their `pending_effective_ticks` for the seat;
- `last_effective_ticks` and projected `next_eligibility_ticks` for every lever owned
  by the seat, including levers whose decision group is not open at this boundary;
- remaining/reserved admin capacity and visible cost estimates;
- permitted actions with stable, machine-readable forbidden reasons;
- a server-generated emergency bulletin when applicable;
- `observation_schema_version` and the elapsed ticks since the previous context.

Information scopes include public aggregates, central-bank system liquidity,
regulator per-bank stress, external trade/capital/FX data, and energy operational
stocks/shortages. `OracleObservation` exists only for debugging and explicitly labeled
oracle research. It cannot enter a human-comparable RL feature or normalization path.

C3 ships a user-reviewed
[observation table](controller_observations_v26.md):

| field | engine source | unit | reference/aggregation | release rule + lag | access/roles | warm-up/missing rule | normalization |
|---|---|---|---|---|---|---|---|

Publication frequencies and lags are configurable run-spec defaults, not claims that
all real jurisdictions publish on the same calendar. Revision noise is P1, but the
release type is revision-ready from day one.

## 9. Procedure, adjustment cost, and economic effects

Three layers must not be conflated:

1. **feasibility/procedure** — authority, meeting, lag, min-hold, cooldown, max-step,
   emergency whitelist, and admin capacity;
2. **decision friction** — explicit adjustment/credibility cost used by the seat's
   objective and human-visible score/cost ledger;
3. **endogenous economic effects** — fiscal spending, subsidy payments, market
   repricing, and other consequences already produced by the engine.

An engine subsidy payment is not a cost of changing the subsidy rule and must not be
charged twice. P0 does not invent a generic fiscal cash sink for all policy changes.
Real implementation costs are added lever-by-lever only when their accounting and
resource counterpart are modeled.

Run-level `AdjustmentCostSpec` supplies weights over Registry `control_scale` and
`cost_class`. Administrative capacity and decision friction are separate ledgers:

```text
A = proposal_admin_overhead + sum(admin_weight_i)

C_adjustment = sum(fixed_i * changed_i
                   + l1_i * abs((new_i-old_i)/control_scale_i)
                   + l2_i * ((new_i-old_i)/control_scale_i)^2)
```

L2 alone is forbidden as the only anti-churn device because splitting one large change
into many small changes makes squared cost cheaper. Fixed/L1 cost, min-hold, and admin
budgets address frequency directly.

Admin capacity is keyed by `(economy, seat, decision_group)` and replenished on its
configured institutional calendar. It is reserved when a decision is accepted so
pending reforms cannot overbook it, and settled when effective. Rejection costs
nothing. Cancellation, supersede, expiry, and failed execution refund rules are
explicit CostSpec fields and events. Emergency actions pay the configured premium but
cannot self-authorize.

"Symmetric for humans and RL" means the same Coordinator constraints, admin ledger,
realized engine effects, and visible objective accounting. It does not mean every
research reward term is silently imposed on a human player.

## 10. Institutional objectives and RL

Authority answers **what may this seat change**. A mandate/objective answers **what is
this seat trying to achieve**. They are separate.

P0 adds an injectable, versioned `ObjectiveSpec` rather than declaring one universal
welfare function:

```python
ObjectiveTerm(
    series_id, objective_kind, target_or_bounds, weight,
    normalization_scale, evaluation_window, reward_release_rule,
)
```

It also defines control-cost weight, reward time normalization (`per_tick` or `sum`),
and whether the profile is `human_comparable` or explicitly `oracle_research`.
Default templates may represent central-bank inflation/employment/stability, Treasury
activity/fiscal sustainability/welfare, regulator stability/credit access, external
balance/reserves, and energy shortage/affordability/fiscal cost. All weights remain
run-spec choices.

Human players see the same mandate dashboard and score components available to a
human-comparable RL occupant. A reward must not leak an unpublished target variable;
oracle social-welfare rewards are permitted only under the oracle label.

The Gym adapter exposes a **context base vector plus server-advisory action-mask/cost
metadata** and maps actions back into `PolicyProposal`. The base vector reads policy
values, versions, pending targets/timing, and admin balances exclusively from the
serialized `DecisionContext`; it never fills missing fields from live `World` or
`PolicyCoordinator` state. A synthetic horizon context is a newly refreshed immutable
snapshot, not a stale context combined with live reads.

For every action lever, the base vector contains the effective value/null mask, pending
target/null/presence mask, policy version, time since last effectiveness plus a
`never_effective` mask, delta to next eligibility, and pending-effective delta (masked
by pending presence). Thus two otherwise equal states with different implementation
lags or minimum-hold history remain distinguishable to a Markov policy.

This is a semi-Markov decision interface: one `env.step` advances to the next context
for that seat, which may be a regular or emergency interval. Reward accumulates over
intervening simulation ticks, is time-normalized according to `ObjectiveSpec`, and
returns `elapsed_ticks`. Discounting is not an `ObjectiveSpec` field: an SMDP trainer
applies `gamma ** elapsed_ticks` when bootstrapping. Any shared discount convention
belongs in an explicit, versioned training/run profile (a P1 contract), rather than
being silently imposed by the P0 environment. Vector action ingress validates the
original one-dimensional numeric representation before integer conversion: booleans,
fractional/non-finite values, strings, object arrays, wrong shapes, and codes outside
`0/1/2` are rejected without changing session state.

Action masks and directional cost estimates may consult current server-side
Coordinator/World metadata because they are explicitly advisory ergonomics, not part
of the Markov context snapshot and not authority. Stale or adversarial actions may still
reach the Coordinator and must be rejected safely. A trained occupant can replace a
human seat or coexist with humans under the same protocol.

## 11. Event log, replay, and checkpoint root

The canonical event stream distinguishes replayable ingress from transitions derived
from that ingress. `seat_assignment`, direct/automatic `proposal_submitted`,
`human_proposal_queued`, `timeout`, and cancel requests are `input` events. Context
opening, `human_proposal_collected`, accepted/rejected decisions, effective
transactions, triggers, and forced system transitions are `derived` events.

Successful frontend ingress appends `human_proposal_queued` immediately and atomically
with the mailbox write; an exact idempotent retry appends nothing. Likewise,
`timeout_context` appends `timeout` when the deadline decision is recorded. Polling a
mailbox later appends `human_proposal_collected`. Coordinator submission does not append
a second proposal/timeout input for either path. Automatic occupants still produce
`proposal_submitted` during boundary advancement and mark their input origin so replay
can regenerate them. A caller that bypasses session ingress with a direct mailbox write
may be backfilled only while that context is already `awaiting_human`; a proposal
preloaded before context opening is rejected with complete boundary rollback because no
canonical input position exists inside the atomic opening operation.

These human/timeout event payloads contain the canonical proposal and identifiers, never
the `DecisionContext` or its observation. Confidential/operational releases therefore do
not leak into the event tape. The checkpoint root retains and validates an explicit set
of open contexts whose human ingress is already recorded; replay semantics do not infer
this fact from the current occupant type.

Replay injects only `input` events in global-sequence order. Derived events are
regenerated and compared, so replay must not execute a forced peg break twice. An inert
RL replay occupant is privately seeded from the recorded automatic proposal; normal
poll/commit then regenerates `proposal_submitted` at its original sequence without a
synthetic human queue event. At an `until_tick` that ends inside a human decision window,
replay first advances a pickled probe. It opens or polls the live terminal boundary only
when the probe remains paused, and never crosses the requested simulation tick merely to
reproduce a terminal suffix.

Every event contains at least:

```text
schema_version, global_sequence, event_id, transaction_id, event_type,
replay_class, boundary_tick, phase, economy_id, seat, actor,
context/proposal/decision ids, status/reason, requested_actions,
effective_changes, policy_versions_before/after
```

A single Coordinator assigns `global_sequence`. Sets use canonical sorted-array JSON;
transition-handler companion changes appear in `effective_changes`. System transitions
also advance the relevant policy version.

Controller-enabled runs checkpoint a picklable `ControlledSimulationSession` root:

```text
ControlledSimulationSession
├── World
├── PolicyCoordinator + global versions/idempotency/event cursor
├── DecisionScheduler + trigger latches + open context/window
├── PendingPolicyQueue + admin/cooldown state
└── seats + occupant state/RNG
```

Legacy uncontrolled runs may continue checkpointing a bare World. Session checkpoints
are taken only at a named boundary/awaiting-decision phase. The header records session
phase, world policy version, event count, and event head hash. Load verifies that the
snapshot and event prefix agree.

Replay acceptance compares engine records, final Policy/ExternalPolicy, active
PegState/World coupling state, pending queue, coordinator/controller state, and the
canonical event hash. The historical records-only digest is insufficient. This full
continuation-state comparison applies to canonically constructible built-in occupants.

For an application-supplied `RLOccupant`, `replay_mode="recorded_proposals"` has a
narrower, explicit contract: it reproduces the source proposal/decision/event and engine
trajectory through the end of the tape using an inert RL placeholder, without
deserializing arbitrary model bytes. It does **not** reconstruct model/private training
state and cannot continue autonomous decisions after the tape ends. A normal session
checkpoint does retain a pickle-safe live model and is the supported bit-identical
continuation mechanism; continuing an event-only RL replay requires an explicit trusted
model reassignment/factory.

## 12. Frozen rulings and explicit non-goals

Rulings retained by this revision:

1. absolute target values are the canonical protocol; directional controls are adapters;
2. announcement has no behavioral effect before an expectations mechanism exists;
3. emergency authorization is Registry metadata plus a server-issued context;
4. standing engine rules are independent from occupant type;
5. effective tick means the first actually affected simulation tick;
6. the energy seat is P0 because its mechanisms already exist;
7. Registry/World pure validators are the validation truth; a per-economy mutator is
   not the top-level World transaction boundary.

Explicit v1 non-goals:

- parliament, elections, parties, and multi-seat bargaining;
- jurisdiction-specific joint-approval maps;
- announcement/expectation effects;
- data revision noise and gradual `ramp_ticks` implementation;
- discretionary human intervention in the middle of an already-running tick;
- the frontend implementation itself (v26 ships engine/server contracts);
- a universal normative reward or political-preference model.

## 13. Batches and acceptance

| batch | content | acceptance |
|---|---|---|
| C1 | full 102-lever authority/time/control/cost table; Proposal/Decision types; `ControlledSimulationSession` root; pure Registry projection; atomic WorldPolicyTransaction; dynamic-reference and peg-state fixes; minimal global version/event core | no-controller frontier digest exact; every numeric lever has reviewed scale and explicit max-step ruling; cross-economy failure leaves no partial Policy/World/PegState/ledger/cost/version/event; sanctions bounds and same-tick peg handoff pass; effective_tick domestic/external first-read tests; pending/version/event state survives a checkpoint round trip |
| C2 | five seats; decision-group calendars; pending timeline; CostSpec; trigger state machines; Null/Scheduled/Heuristic/RandomFuzz occupants | Null-attached and no-controller **engine/frontier** digests are identical (their session-event streams intentionally differ); pause consumes no tick/RNG; trigger hysteresis/cooldown prevents repeated sessions; 30y legal fuzz runs x3 seeds conserve and never crash; emergency peg drill succeeds only when causally early enough |
| C3 | InstitutionObservation, Release calendar/access control, permitted-action reasons, full observation table, ObjectiveSpec/score components | at boundary t only releases with released_at<=t are visible; rolling values use released vintages; role/access and missing-reason tests; human and Gym serializers receive byte-equivalent contexts; oracle data/reward cannot enter human-comparable profile |
| C4 | HumanQueueOccupant, four execution-surface modes, hot-swap, server API types, full session checkpoint coverage, canonical input/derived replay | idempotent retries do not double-charge/log; stale and forged emergency submissions reject; timeout/no-action/swap replay; checkpoint with pending action or open human context resumes bit-identically; full session/event digest matches for canonical built-in occupants; opaque RL event replay obeys the recorded-proposal contract above |
| C5 | Gym semi-Markov adapter, action normalization/masking, checkpoint reset | a fixed canonical proposal trace through Gym and direct Coordinator paths is bit-identical; elapsed-tick reward normalization is correct; masked agent emits legal proposals while adversarial/stale actions are still safely rejected by Coordinator |
| C6 | versioned context/action codecs, masked SMDP PPO, persistent process sampling, exact trainer checkpoints, safe portable artifacts, paired independent evaluation | training and deployed occupants encode/decode the same immutable context; `gamma ** elapsed_ticks` and terminal bootstrap semantics pass; continuous and resumed training are bit-identical; CPU/MPS checkpoints restore safely; malformed artifacts and contract drift fail closed; a disjoint-seed candidate clears the registered random, active-heuristic, and no-action superiority gate |

### 13.1 Local acceptance record — 2026-07-18

- machine contract audit: Registry = control specs = lever table = **102** exact
  names; default observation spec = observation table = **29** exact names; all
  **79** numeric levers have finite positive control scales and max steps;
- Controller suite: **260 passed, 3 skipped** (the three opt-in long runs);
- 30-year legal random-controller conservation runs: **3 passed** with the long-run
  gate enabled;
- policy/open-economy/peg/ledger regression slice: **155 passed, 8 skipped**;
- complete repository suite with the RL extra: **1329 passed, 11 conditionally
  skipped, 0 failed** in 1:20:38;
- `compileall` and `git diff --check` passed. The only test warnings are four
  Gymnasium advisories about intentionally unbounded `Box` observation limits.

The C1 lever table and C3 observation table remain separate economic review surfaces.
This branch's P0 implementation treats their current no-`TODO` contents as frozen; a
later change to ownership, timing, visibility, or normalization is a new economic ruling,
not an incidental refactor.

### 13.2 RL extension acceptance — 2026-07-19

- **123** focused Controller/Gym/RL tests covering masked SMDP PPO training,
  exact checkpoint/resume, CPU/MPS restore, compact
  persistent process workers, safe artifact loading, train/deploy codec parity,
  and CLI trust-boundary tests passed;
- the current `reward_scale=0.01` CPU artifact trained for **20 updates**, **7,840
  decision samples**, and **116,800 engine ticks** in **376 seconds**;
- on 20 disjoint held-out seeds it passed all three corrected comparisons:
  **100%** wins against the active fiscal heuristic, **85%** against mask-aware
  random, and **100%** against no action; full statistics and caveats are in
  [`rl_training_v26.md`](rl_training_v26.md);
- complete repository suite with the training extra: **1406 passed, 11 skipped,
  4 warnings, 0 failed** in **1:06:56**. The warnings are the four existing
  Gymnasium advisories about intentionally unbounded `Box` limits.
