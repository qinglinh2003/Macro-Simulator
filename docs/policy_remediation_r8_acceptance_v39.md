# Policy remediation R8 acceptance

- Status: `accepted`
- Packages: 9
- Native branches: 2376
- Cache hits: 0
- Population per country: 100,000
- Matched seeds: 8
- Native workers per session: 8
- Legacy Python simulator used: no
- Acceptance hash: `46c91525839f2bdf2114dbb565803d509ca9b9b4193b06f97527ff4272454aad`

## Package ledger

| Package | Crisis | Disposition | Primary | Guardrail | Withdrawal | Severity | Alternative state |
|---|---|---|---:|---:|---:|---:|---:|
| `recession_response` | `CR_DEMAND_RECESSION` | `package_guardrail_failure` | pass | fail | fail | pass | fail |
| `anti_inflation` | `CR_SUPPLY_STAGFLATION` | `package_no_supported_benefit` | fail | fail | fail | fail | fail |
| `bank_liquidity` | `CR_BANK_RUN` | `package_no_supported_benefit` | fail | fail | pass | fail | fail |
| `bank_solvency` | `CR_BANK_RUN` | `package_no_supported_benefit` | fail | fail | fail | fail | fail |
| `housing_cycle` | `CR_HOUSING_BUST` | `package_no_supported_benefit` | fail | fail | pass | fail | fail |
| `energy_emergency` | `CR_ENERGY_EMBARGO` | `package_guardrail_failure` | pass | fail | fail | pass | fail |
| `external_crisis` | `CR_PEG_PRESSURE` | `package_no_supported_benefit` | fail | fail | fail | fail | fail |
| `poverty_and_employment` | `CR_DEMAND_RECESSION` | `package_no_supported_benefit` | fail | fail | fail | fail | fail |
| `debt_sustainability` | `CR_SOVEREIGN_STRESS` | `package_no_supported_benefit` | fail | fail | fail | fail | fail |
