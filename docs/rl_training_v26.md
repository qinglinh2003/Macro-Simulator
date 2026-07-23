# v26 RL training and deployment

**Status:** implemented. The module trains a masked semi-Markov PPO policy on
the real controlled simulation, exports a framework-free artifact, and evaluates
that artifact against paired random and heuristic baselines on held-out simulator
seeds.

This is an engineering and learning benchmark, not evidence that the current
objective is a complete social-welfare function or that one learned policy is
valid for every economy.

## 1. Time and data contract

`ControllerEnv` remains a semi-Markov environment:

- one action is submitted per server-issued `DecisionContext`;
- one `env.step(action)` advances from the current decision boundary to the next;
- a step may therefore contain many engine ticks;
- `info["elapsed_ticks"]` records the exact interval;
- a `per_tick` human-facing reward is multiplied by the interval duration before
  it enters PPO/evaluation, so it becomes an SMDP interval sum;
- PPO discounts continuation with `gamma ** elapsed_ticks`, and GAE additionally uses
  `lambda ** elapsed_ticks`;
- the reference task is a finite-horizon mandate and terminates with zero
  bootstrap. Generic time-limit truncations bootstrap their terminal observation
  but cut the GAE trace before the next episode.

The interval sum itself is undiscounted; `gamma ** elapsed_ticks` discounts the
continuation value. With `gamma < 1` this is the standard option-level SMDP
convention, not the exact sum of individually discounted within-interval tick
rewards. Use `gamma=1` when exact invariance to interval partitioning is required.

Training and deployment use the same versioned contracts:

- `ContextCodec` encodes only immutable `DecisionContext` data available to the
  controlled institution;
- `DirectionalActionCodec` maps each selected lever to `down / hold / up` and
  builds a conservative context-only mask;
- live Coordinator probes and exact live adjustment-cost matrices are not model
  inputs because a deployed `RLOccupant` cannot reconstruct them from a context;
- the Coordinator remains the final authority and rejects any globally illegal
  proposal.

The artifact embeds both codec schemas and their SHA-256 hashes. Policy-registry
or observation-schema drift therefore fails closed instead of silently changing
the meaning of a trained vector.

## 2. Reference learning task

`fiscal_stabilization_v1` is the first reproducible real-engine task:

- seat: `treasury`;
- action lever: `gov_deficit_target` only;
- decision calendar: every 15 ticks;
- episode horizon: 730 ticks;
- observations: the normal released institutional observation contract;
- mandate: unemployment in `[0, 0.08]`, inflation in
  `[-0.001, 0.001]`, higher real output, and the normal policy-adjustment cost;
- default world: 20 households, 15 consumption firms, 8 capital firms, 2 banks.

The intentionally narrow action space makes this a useful end-to-end gate: the
policy must discover whether and when to adjust fiscal support while respecting
implementation lag and minimum holding periods. More seats, levers, economies,
objectives, and randomized structural parameters should be added as separate,
versioned tasks rather than hidden inside this benchmark.

## 3. Install and train

The normal engine and portable model loader do not require PyTorch. Install the
training extra only on machines that train:

```bash
uv sync --extra train
```

Run the reference task:

```bash
uv run --extra train macro-rl train \
  --updates 50 \
  --num-envs 8 \
  --device cpu \
  --output-dir runs/rl-fiscal-v1
```

The trainer multiplies interval rewards by `--reward-scale` (default `0.01`)
before fitting PPO's policy and value heads. This is an optimizer-conditioning
transform only: evaluation, reported episode returns, and the economic objective
remain in the original unscaled units. The exact scale is checkpoint-bound and
recorded in artifact metadata, so an incompatible resume fails closed.

The output directory is never silently overwritten. It contains:

- `metrics.jsonl`: per-update throughput/loss metrics; an exact resume first
  atomically removes any rows newer than the loaded checkpoint;
- `checkpoint.pt`: atomic PPO/Adam/RNG/normalization checkpoint, loaded with
  PyTorch's restricted `weights_only=True` path;
- `policy.msrl`: portable inference artifact.

Resume while increasing the total update target:

```bash
uv run --extra train macro-rl train \
  --updates 100 \
  --num-envs 8 \
  --device cpu \
  --output-dir runs/rl-fiscal-v1 \
  --resume runs/rl-fiscal-v1/checkpoint.pt
```

The fixed-horizon trainer requires each rollout to contain a whole number of
episodes. This makes update checkpoints exact: it never claims to restore an
in-flight simulator worker that was not serialized.

Environment construction is process-isolated. Worker processes persist across
episodes and rebuild their environment in place for each new seed; use `--sync`
for debugging. Training workers return only the mask, elapsed time, and reward
normalization fields over IPC; frontend/debug traces stay worker-local. The
simulation is normally much more expensive than the small policy network, so
additional CPU workers tend to matter more than a GPU.

### Apple Silicon

The CLI defaults to `--device cpu`. `--device mps` explicitly uses Apple GPU
acceleration, while `--device auto` selects MPS when PyTorch reports it
available. A GPU is not required. Benchmark both CPU and MPS on the complete
workload: for small networks, inter-process simulation usually dominates and MPS
may provide little or no end-to-end speedup.

## 4. Independent evaluation

Training return is not an acceptance result. Evaluate the exported artifact on
seeds disjoint from training:

```bash
uv run --extra train macro-rl evaluate \
  runs/rl-fiscal-v1/policy.msrl \
  --seeds 20 \
  --evaluation-seed-start 1000000 \
  --output runs/rl-fiscal-v1/evaluation.json
```

All policies see the same simulator seed in each paired comparison. The suite
runs:

- the trained model deterministically;
- a mask-aware seeded random policy;
- an active deterministic fiscal stabilizer using only released unemployment
  and inflation;
- a separate no-action/hold diagnostic.

"Better" is pre-registered rather than inferred from one mean: the candidate
must beat random, the active heuristic, and no-action, meet the minimum
paired-seed count and win rate, and have a paired bootstrap confidence-interval
lower bound strictly above the minimum effect. The three comparisons receive a
Bonferroni familywise correction. The command exits `0` only when the complete
verdict passes and `2` when the experiment ran correctly but superiority was not
established.

## 5. Engine deployment

Deployment has no PyTorch dependency and does not deserialize Python objects:

```python
from macro_sim.controllers import RLOccupant
from macro_sim.rl import load_artifact

policy = load_artifact("runs/rl-fiscal-v1/policy.msrl")
session.assign_seat(0, "treasury", RLOccupant(policy=policy), actor="deployment")
```

`policy.msrl` is a ZIP with canonical JSON and numeric-only NPZ arrays loaded
with `allow_pickle=False`. The loader bounds member sizes and validates member
sets, hashes, schemas, shapes, dtypes, and finite values before constructing the
NumPy inference policy. A live session can be checkpointed with the policy RNG
state intact; event replay reconstructs an inert RL occupant and replays recorded
proposals rather than embedding arbitrary model bytes in the event stream.

## 6. Current limits

- The reference benchmark demonstrates the training/deployment path for one
  treasury lever; it does not establish general macroeconomic optimality.
- Fixed-horizon vector workers currently require homogeneous episode boundaries
  and episode-aligned rollout checkpoints.
- The deployable base vector does not yet encode decision-group identity or the
  pure-context advisory mask as critic features; multi-group tasks should add a
  new codec schema rather than silently reuse v1.
- Hyperparameter search and structural domain randomization are explicit future
  experiment layers, not implicit behavior in the trainer.
- A production claim requires held-out seeds, robustness across plausible model
  calibrations, comparison with stronger domain heuristics, and economic review
  of the mandate itself.

## 7. Local learning-gate record — 2026-07-19

An Apple Silicon CPU run (8 simulator workers, 20 PPO updates, 7,840 decision
samples and 116,800 engine ticks in 376 seconds) was evaluated on the disjoint
seed range `[1200000, 1200020)`. The candidate artifact SHA-256 was
`d48222b8fe2cf9365327020f325ba86a17ead6080e080f03f2cb77dc45304779`.
Evaluation used `gamma=0.999`, 10,000 paired bootstrap resamples, a 50% minimum
win rate, and Bonferroni-corrected 98.33% intervals for three comparisons.

| policy / comparison | mean discounted return | candidate mean advantage | corrected interval | candidate win rate |
|---|---:|---:|---:|---:|
| trained model | -5,370.16 | — | — | — |
| active fiscal stabilizer | -11,199.19 | +5,829.03 | [4,148.17, 7,592.03] | 100% |
| mask-aware random | -9,488.33 | +4,118.17 | [2,080.50, 6,288.01] | 85% |
| no action | -18,210.33 | +12,840.17 | [10,419.32, 15,005.73] | 100% |

The complete pre-registered gate passed: every corrected lower bound was above
zero and every paired win rate exceeded the threshold. This establishes the
learning and deployment benchmark for this one real-engine task; it is not a
claim of general macroeconomic optimality or external validity.

## 8. Desktop built-in artifact refresh — 2026-07-23

Shock and population releases upgraded the institutional observation contract
from v1 to v2. The learning-gate artifact above correctly failed closed against
that new schema, so it was not force-loaded or silently padded.

The desktop branch trained a fresh `fiscal_stabilization_v1` policy on the
current v2 contract:

- 20 PPO updates, 7,840 decision samples and 116,800 simulated days;
- artifact SHA-256
  `1cfc9b0f3b0d2f18ea9b54bbc4130ff447936cbb685aa14e01dd35ef28d107e6`;
- context contract
  `9649f19990d977641c0c4a8d78edb408d548135ae75f66c2faf519f626daa0d6`;
- action contract
  `5cfb69b9d17fb365ceae9b4f7f44661920371385b6cf9024f22041dd0fd304cb`.

It completed a 365-day, three-country GFC desktop run as the live Treasury
`RLOccupant`. The portable file is pinned under
`macro_sim/rl/artifacts/fiscal_stabilization_v1.msrl`; non-fiscal Treasury
decision groups are routed to hold, and the model only acts on its trained
`fiscal_stance` group.

This refresh is a deployment-compatibility and playability gate. The full
20-seed superiority test in §7 has not yet been repeated for the v2 artifact, so
the older result must not be attributed to this new hash.
