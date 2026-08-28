# Policy remediation R7 acceptance

- Status: `accepted`
- Populations per country: 100,000 and 1,000,000
- Matched seeds: 4
- Native workers: 8
- Legacy Python simulator used: no
- Acceptance hash: `60d079d45a39084cab5c5af0cb59c07d1b76676702bfc91a5e71cda8d6e150d3`

## Scale ledger

| Lever | R6 class | R7 scale disposition | Budget |
|---|---|---|---:|
| `mortgage_foreclosure_ltv` | `conditional` | `finite_size_confirmed` | pass |
| `gov_investment_share` | `expert_only` | `finite_size_confirmed` | pass |
| `bankrupt_persist` | `conditional` | `finite_size_confirmed` | pass |
| `rental_eviction_arrears` | `conditional` | `finite_size_confirmed` | pass |
| `soe_efirm` | `structural` | `finite_size_dependency_modeled` | pass |
| `tariff` | `expert_only` | `finite_size_dependency_modeled` | pass |
| `fx_regime` | `structural` | `finite_size_dependency_modeled` | pass |

A modeled dependency preserves the matched-seed effect direction but does not follow the preregistered first-order population elasticity. The fitted power-law exponent is retained in the machine report; it is not silently described as scale invariant.
