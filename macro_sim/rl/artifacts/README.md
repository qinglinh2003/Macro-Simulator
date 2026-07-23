# Built-in deployment artifacts

`fiscal_stabilization_v1.msrl` is the portable, framework-free Treasury policy
whose held-out evaluation is recorded in `docs/rl_training_v26.md`.

- Artifact SHA-256:
  `1cfc9b0f3b0d2f18ea9b54bbc4130ff447936cbb685aa14e01dd35ef28d107e6`
- Observation contract: v2
- Training: 20 PPO updates, 7,840 decision samples, 116,800 engine days
- Controlled seat: `treasury`
- Action surface: `gov_deficit_target`
- Loading path: `macro_sim.rl.load_artifact`

The desktop game loads it deterministically.  It is not valid for the other four
institutional seats, and the new-game contract rejects such assignments.
