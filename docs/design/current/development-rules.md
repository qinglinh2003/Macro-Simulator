# Development Rules

These rules are the shortest path to making changes without breaking the model.

## Before Changing Behavior

1. Identify which invariant the change touches: deposits, loans, reserves,
   securities, shares, real stocks, or pure observation.
2. Find the feature flag or config boundary. If none exists, add one unless this
   is a deliberate correctness fix.
3. Decide the conservation gate before writing the mechanism.
4. Decide which metric or diagnostic will prove the mechanism is active.
5. Write down the falsifiable expectation before running sweeps.

## Accounting Discipline

- Do not mutate balances directly from agents.
- Do not treat real stocks as money.
- Do not mix bond face, book, and market values.
- Do not use reserve movement as a substitute for a deposit-ledger transaction.
- Do not let a convenience shortcut bypass A5 or reserve conservation.

## Modeling Discipline

- Macro regularities are held-out tests, not targets to hard-code.
- A higher scorecard result is not automatically a better economy; welfare,
  stability, realism, and mechanism clarity can trade off.
- A failed pre-registered hypothesis is a finding. Preserve it in history.
- Do not tune a module to manufacture a phenomenon. Build the realistic
  mechanism and let the phenomenon emerge or remain latent.
- Prefer one new mechanism at a time, with the old configuration bit-identical.

## Documentation Discipline

- Durable rules belong in [`../core/`](../core/README.md).
- Current implementation guidance belongs in [`./`](README.md).
- Long explanations, diagnostics, and version narratives belong in
  [`../history/`](../history/README.md).
- If a conclusion changes, keep the old reasoning in history and update the
  current brief with the corrected conclusion.
