# v25: The Policy Module (DRAFT — skeleton)

**Status**: blank scaffold, design not yet frozen · **Branch**: TBD (`feat/policy-module`, off dev after the v24 merge)
**Goal**: complete the existing Config/Policy split — every lever a real-world authority could
change at a meeting becomes runtime-mutable PolicyState, driven by pluggable controllers
(frontend player / scripted / random / heuristic / RL). The action stream doubles as the
save-container `events.log` and, later, the frontend network protocol.

---

## 0. Boundary principle

> Policy = what an authority (government / central bank / immigration office) can decide at
> runtime. Config = the physics of the world (preferences, technology, demography).

## 1. Lever inventory (P0 deliverable — TO FILL)

Full sweep of all ~330 Config fields, each classified `physics | policy | ambiguous(ruling)`.

| Domain | Levers (draft, unverified) | Notes |
|---|---|---|
| Fiscal | tax_income / tax_profit / tax_consumption / wealth tax + allowance; gov_consumption_share; gov_investment_share; gov_deficit_target; pension_replacement; JG wage | |
| Monetary | Taylor (target π, φπ, φu); rate floor/cap; OMO target/drain; LOLR on/off | |
| Macroprudential | bank_target_capital_ratio; bank_exposure_limit; LTV cap; margin rules | |
| External | capital_control; peg on/off/anchor; export subsidy / tariff | |
| Migration | immigration_cap; guest_worker_return | |
| Housing | property tax; transfer tax (already in Policy); permits | |

## 2. Architecture (three layers)

- **Controller** (pluggable): `Null` (constant, bit-identical) · `Scheduled` (tick→value script;
  the shock-module cousin) · `Random` (bounded walk, own RNG stream) · `Heuristic` ·
  `RLAdapter` (gym-style) · later `Frontend`.
- **PolicyState**: per-economy; each lever carries `(min, max, max_step_per_tick)` — the single
  declaration that is also the RL action space. World-level policies (capital_control, peg,
  migration) are OWNED by each economy's PolicyState; World reads them per tick.
- **Read-point migration**: modules read `econ.policy.X`, never `cfg.X`; genesis seeds
  policy ← cfg.

## 3. Disciplines (inherited from v24 lessons)

1. Bit-identity: NullController seeded from cfg == today's behavior; digest-gated.
   Decision point fixed at top-of-tick; controller uses an isolated RNG stream.
2. Checkpoint-able: controller state pickles; **policy is STATE and must resume exactly**
   (the inverse of the "tolerances are policy, not state" lesson).
3. Actions are events: every change logged `(tick, economy, lever, old, new, actor)` →
   `.msim` events.log slot → replay / audit / frontend protocol in one schema.
4. Explicit observation contract: `observe()` returns a curated snapshot — the RL observation
   space and the frontend UI data contract.

## 4. Phases & acceptance

| Phase | Content | Acceptance |
|---|---|---|
| P0 | Inventory + PolicyState extension + read-point migration | digest bit-identical; full suite green |
| P1 | Null/Scheduled/Random controllers + action log + checkpoint integration | Scheduled replay bit-identical; boundedness tests |
| P2 | observe() contract + demo heuristic (counter-cyclical fiscal) | 30y portrait A/B: heuristic vs Null |
| P3 | gym env adapter (step = N ticks; reward = injectable callable) | RL interface smoke with random policy |

## 5. Open questions (rulings pending)

- [ ] Reward left as injectable callable in P3 (research question, not module scope)?
- [ ] World-level policy ownership: per-economy PolicyState (proposed) vs World-held vectors?
- [ ] Lever set for P0: full sweep vs start with fiscal+monetary only?
- [ ] Action cadence: every tick vs policy-meeting interval (e.g. every 30 ticks)?

## 6. Relationship to the shock module (the OTHER v25 candidate)

ScheduledController already covers POLICY shocks. The exogenous-shock module (crises:
disasters, pandemics, embargoes, productivity/energy shocks) is a separate module hitting
PHYSICS levers — designed after this one; shares the events.log schema.
