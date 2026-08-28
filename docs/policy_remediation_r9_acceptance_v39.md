# Policy remediation R9 acceptance

Status: `accepted_with_explicit_limitations`

## Delivery and UI gates

### Delivery Gates

- `documented_delivery_ticks`: `passed`
- `emergency_exact_native_parity`: `passed`
- `free_immediate_exact_native_parity`: `passed`
- `human_ingress_exact_native_parity`: `passed`
- `institutional_regular_exact_native_parity`: `passed`
- `policies_reached_expected_state`: `passed`
- `released_observations_only`: `passed`

### Ui Gates

- `definitions_complete`: `passed`
- `evidence_catalog_bound`: `passed`
- `evidence_scopes_complete`: `passed`
- `free_policy_mode`: `passed`
- `read_points_complete`: `passed`
- `registry_domains_complete`: `passed`

### Occupant Gates

- `action_codec_match`: `passed`
- `context_codec_match`: `passed`
- `released_observations_only`: `passed`

## Occupant contract

- Classification: `explicit_cross_backend_transfer_probe`
- Training environment match: `False`
- Superiority claim allowed: `False`

## Explicit limitations

- Recorded human ingress validates transport, authority, timing, and native execution parity; it is not participant performance data.
- The shipped RL artifact matches the vector codecs but not the native training-environment contract; R9 treats it only as a transfer probe and makes no superiority claim.

## Hashes

- Policy evidence: `ef9101ea1514bb0c445fed0ba197be7ad43980765e1ee33e497a8de66bfe43db`
- R9 evidence: `5d4c132d3fc5fb199c8b3821ed23a157737f23b1c4fe5518eecab7663cd74f58`
- R9 acceptance: `0b8c1009539bb60ce522d5967e806cfa834d701e6829424e135d83fe325f605a`
