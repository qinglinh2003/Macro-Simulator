# Godot desktop prototype v28

This branch contains an intentionally narrow playable vertical slice. It validates
the desktop architecture before a larger game UI is designed.

## Architecture

- **Godot 4 client:** native desktop rendering, controls, charts, and input.
- **Python worker:** the authoritative `World`, `ControlledSimulationSession`, and
  `ControllerService` owner.
- **Local protocol:** newline-delimited JSON over TCP on loopback. The launcher owns
  both process lifetimes; Godot never imports or reimplements economic logic.

Every policy input is submitted through the controller proposal API. Every crisis
is scheduled through `World.schedule_shock`. A burst of requested ticks stops as
soon as a human decision context opens.

## Run

Requirements: Python 3.12+, `uv`, and Godot 4 available as `godot`.

```bash
./scripts/run_godot_prototype.sh
```

The prototype supports new game, single-step, play/pause, five-tick advance,
numeric Treasury policy decisions, no-change decisions, a productivity shock,
live metrics, a short history chart, and the controller event stream.

## Deliberate P0 limits

- One economy and one human Treasury seat.
- One local client and no authentication or remote transport.
- No save/load, scenario browser, world map, asset pipeline, or packaged `.app`.
- The UI exposes numeric levers first; boolean, enum, nullable, and bilateral policy
  editors belong in the next interaction pass.

The next milestone should validate the player loop with this executable before
expanding visual design or adding multiplayer/server concerns.
