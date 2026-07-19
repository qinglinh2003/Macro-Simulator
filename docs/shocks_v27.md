# Shock Engine v27

Status: implemented on `feat/shock-engine-v27`. This document is the contract for
exogenous disturbances in the simulator.

## 1. Boundary

The model now has three deliberately separate authorities:

- `Config` defines immutable structural capabilities and genesis parameters.
- `Policy` is the live set of institution-controlled levers.
- `Controller` decides when and how institutions change `Policy`.
- `ShockEngine` supplies events outside those institutions' control.

A shock is not an arbitrary `setattr`. It names a registered economic channel and
changes an input to a mechanism. Prices, unemployment, output, defaults and policy
responses remain endogenous outcomes. For example, an oil embargo constrains energy
or trade capacity; it does not set the energy price. A financial crisis constrains
loan origination; it does not set GDP or force a rate cut.

Historical crises are compositions of generic shock primitives. Their actual policy
responses are intentionally absent and must come from a human, heuristic or RL
Controller.

## 2. Public API

The public package is `macro_sim.shocks`:

```python
from macro_sim.config import Config
from macro_sim.economy import Economy
from macro_sim.shocks import ShockSpec, ShockTape, ShockTarget

tape = ShockTape((
    ShockSpec(
        shock_id="oil_supply_1",
        kind="energy_capacity",
        start_tick=365,
        magnitude=0.40,
        target=ShockTarget(economy_ids=(0,), sectors=("energy",)),
        duration_ticks=180,
        announcement_tick=360,
    ),
))

economy = Economy(Config.v124(energy_enabled=True), shocks=tape)
```

`World(..., shocks=tape)` installs one World-owned engine. A multi-economy event is
validated and realized once, before any country's tick mutation. The same engine is
shared by every child `Economy`.

A concrete event may also be injected at a live boundary:

```python
world.schedule_shock(spec)
```

The ID must be new, and neither its start nor announcement may be backdated. A failed
schedule leaves the tape and economic state untouched.

## 3. Immutable tape contract

`ShockSpec` contains only JSON-safe data:

- stable `shock_id` and registered `kind`;
- target economies and optional semantic sectors;
- start, optional duration, ramp-in and ramp-out;
- signed magnitude (positive is adverse, negative is favorable where supported);
- announcement tick, visibility class and authorized roles;
- source, calibration note, correlation group and tags.

`ShockTape` sorts specs canonically, rejects duplicate IDs and unknown kinds, supports
strict JSON round trips, and exposes a SHA-256 `contract_hash`. It never serializes a
Python callback, property path or handler supplied by scenario data.

A finite event is active on `[start_tick, start_tick + duration_ticks)`. A duration of
`None` is a permanent step. Ramps live inside the duration. Continuous adverse effects
compose as a product of survival factors in stable shock-ID order:

```text
factor(channel, t) = product(1 - magnitude_i * intensity_i(t))
```

This makes overlapping pulses recover without storing and restoring mutable anchors.
Invalid, non-finite or explosively stacked factors are rejected before the tick changes.

One-shot capital losses also compose multiplicatively. Their complete aggregate is
prepared for every target economy before the first capital stock is changed.

## 4. Registered channels

| Kind | Mechanism input | Effect |
|---|---|---|
| `productivity` | `Economy._output_factor` | Sector output-factor multiplier used by planning and production. |
| `labor_availability` | effective labor entering production | Models attendance/available effective work; it does not set unemployment. |
| `energy_capacity` | E-firm `capacity_kappa * capital` ceiling | Constrains both energy planning and realized production without mutating `capacity_kappa`. |
| `household_demand` | desired household consumption budget | Applied after ordinary income/wealth planning and before household credit; realized spending remains cash- and market-constrained. |
| `import_capacity` | importer physical trade cap | Restricts delivered imports before goods-market clearing. |
| `export_capacity` | shared exporter shipping budget | Restricts aggregate source inventory that can be reserved across importers at one barrier. |
| `credit_supply` | loan-origination headroom | Scales the amount a bank may originate; existing debts and deposits are not rewritten. |
| `capital_destruction` | private/public physical capital stock | Idempotent one-shot real loss with a dedicated metric; no money is created or destroyed. |

Sector targets use `consumption`, `necessity`, `luxury`, `capital`, `energy` and
`public` (`c`, `k`, `e` are accepted aliases). Broad `consumption` includes necessity
and luxury firms. Capability mismatches such as an energy shock without an E-sector or
a trade shock without the World trade layer fail at binding/scheduling time.

## 5. Tick and Controller chronology

At simulation boundary `t`:

1. ReleaseService exposes only shocks whose `announcement_tick <= t` and whose
   visibility permits that Controller seat.
2. Scheduled or emergency Controller contexts decide policy from those releases.
3. World atomically commits/validates due policy state.
4. ShockEngine prepares and realizes tick-`t` continuous overlays and one-shot events.
5. The trade barrier and domestic economic phases run.
6. Metrics, shock events and controller-derived events commit; the boundary becomes
   `t + 1`.

This gives a same-day surprise response without revealing the remainder of the tape.
An event announced before its start can be anticipated. A delayed or classified event
is absent from unauthorized observations even though the complete tape exists inside
the experiment.

Every `InstitutionObservation` carries:

- fixed **public-information** numeric releases for RL: announced/active counts,
  maximum severity, time to next disclosed event, and one severity feature per
  registered kind;
- typed `shock_bulletins` for humans/frontends, with ID, kind, target, magnitude,
  timing, status, source and calibration note, filtered to the observing seat.

`ControllerService.shock_bulletins(economy_id=..., seat=...)` is the read-only frontend
surface. Oracle access remains a separate research path. The default scheduler opens
same-boundary emergency contexts for sufficiently severe **publicly disclosed** supply,
energy, financial, trade or demand crises; existing policy capability,
implementation-lag, minimum-hold and adjustment-cost rules still apply. Classified
information can inform its authorized seat at the normal institutional cadence without
silently revealing the event by opening contexts for other seats.

## 6. Events, checkpoint and replay

ShockEngine owns a canonical SHA-256 event chain with `announced`, `started`, `ended`
and `realized` transitions. A controlled session mirrors new **public** transitions
into its global derived event stream, so input-only Controller replay regenerates and
compares the same public shock prefix. Operational/confidential transitions remain in
the checkpointed internal chain and reach occupants only through role-filtered
observations; this prevents the global Gym/frontend event feed from bypassing access
control.

The normal pickle checkpoint already captures the tape, active/announced/realized ID
sets and event chain. v27 additionally validates and records in `header.json`:

- shock tape contract hash;
- shock event count;
- shock event head hash.

A checkpoint is accepted only at a completed boundary (`shock_engine.current_tick ==
checkpoint_tick - 1`). Event IDs, active-set derivation, one-shot realization state,
World/child engine identity and Controller event cursor are checked before save and
after load. Consequently a capital-loss event cannot fire twice after resume.

The engine itself uses no random draws. Stochastic experiments first call
`generate_poisson_tape(...)`, which uses a dedicated seed and materializes every draw
as a concrete `ShockSpec`. Replay reads that tape and never resamples it.

## 7. Historical templates

The package includes reduced-form, explicitly non-calibrated scenario builders:

- `oil_embargo_scenario`;
- `global_financial_crisis_scenario`;
- `pandemic_scenario`;
- `natural_disaster_scenario`.

They contain causes available in the current engine, not observed outcomes and not
historical policy decisions. A template may require structural capabilities: the oil
package needs energy and trade, GFC needs banking, and the full pandemic template needs
banking plus trade (`include_trade=False` removes its trade legs). Source and
calibration caveats travel with every event into the frontend bulletin.

These packages are starting points for calibration, not labels that make a run a
historically faithful replication. A serious empirical scenario should freeze its
own tape JSON, data provenance, mapping assumptions and paired counterfactual.

## 8. Legacy energy compatibility

The three Config fields `energy_shock_at`, `energy_shock_magnitude` and
`energy_shock_duration` remain accepted. Economy/World genesis translates them into
an ordinary `energy_capacity` `ShockSpec` tagged `legacy_config`. The old
`apply_energy_shock` symbol remains as a compatibility shim, but no longer mutates or
restores `capacity_kappa`.

With no tape and no legacy energy event, `shock_engine` is `None`: no shock state,
RNG stream or shock-only metric fields are installed. Coupling seams read the exact
identity factor, preserving the existing economic baseline.

## 9. Acceptance gates

`tests/test_shocks_v27.py` proves:

- canonical serialization/hash and order-independent composition;
- an exact pre-shock economic prefix and recovery after a pulse;
- live scheduling and state-atomic rejection of backdating;
- all continuous coupling channels;
- one-shot capital loss, monetary conservation and exact checkpoint continuation;
- importer/exporter targeting in a coupled World;
- announcement/role filtering and absence of future leakage;
- emergency context routing with detailed bulletins;
- deterministic Controller event replay;
- deterministic stochastic tape materialization and policy-free historical packages.

The existing legacy energy, World, Controller, checkpoint and RL suites remain part of
the full v27 gate.
