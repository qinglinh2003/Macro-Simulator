# v26 Controller 默认观测表

本表是当前 `DEFAULT_OBSERVATION_SPEC` 的基础观测快照，共 **30** 个序列；另有 v27
加入的 12 个固定维度冲击观测，因此默认 schema v2 合计 **42** 个序列。
`window` 是聚合窗口，`frequency` 是发布周期，`lag` 是参考期结束后的额外发布滞后，
单位均为 tick。`normalization` 是前端/RL 的归一化尺度，不会改写引擎数值。

所有序列当前都要求完整窗口；预热不足、源字段缺失、尚未发布或无访问权时，
系统返回显式 `missing_reason`，不使用 NaN 哨兵值。`world.* [economy_id]` 表示从 World 向量中选取当前经济体的分量。

| series | source | unit | aggregation | window | frequency | lag | access | roles | missing | normalization |
|---|---|---|---|---:|---:|---:|---|---|---|---:|
| `price_index` | `economy.price_index` | `index` | `mean` | 7 | 7 | 2 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1 |
| `inflation` | `economy.inflation` | `per_tick` | `mean` | 7 | 7 | 2 | `public` | 全部 | 需完整窗口；否则显式缺失 | 0.01 |
| `real_output` | `economy.real_output` | `goods` | `sum` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1000 |
| `unemployment_rate` | `economy.unemployment_rate` | `share` | `mean` | 7 | 7 | 2 | `public` | 全部 | 需完整窗口；否则显式缺失 | 0.1 |
| `employment` | `economy.employment` | `fte` | `mean` | 7 | 7 | 2 | `public` | 全部 | 需完整窗口；否则显式缺失 | 100 |
| `avg_wage` | `economy.avg_wage` | `currency_per_tick` | `mean` | 7 | 7 | 2 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1 |
| `population_alive` | `economy.population_alive` | `persons` | `last` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1000 |
| `poverty_rate` | `economy.poverty_rate` | `share` | `mean` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 0.1 |
| `income_gini` | `economy.income_gini` | `index` | `last` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 0.5 |
| `gov_deficit_to_gdp` | `economy.gov_deficit_to_gdp` | `share` | `mean` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 0.1 |
| `gov_debt_to_gdp` | `economy.gov_debt_to_gdp` | `share` | `last` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1 |
| `policy_rate` | `economy.policy_rate` | `per_tick` | `last` | 1 | 1 | 0 | `public` | 全部 | 需完整窗口；否则显式缺失 | 0.01 |
| `bank_reserves_total` | `economy.bank_reserves_total` | `currency` | `last` | 1 | 1 | 0 | `operational` | `central_bank`, `regulator` | 需完整窗口；否则显式缺失 | 1000 |
| `reserve_floor_breach_share` | `economy.reserve_floor_breach_share` | `share` | `last` | 1 | 1 | 0 | `confidential` | `central_bank`, `regulator` | 需完整窗口；否则显式缺失 | 0.1 |
| `near_failure_bank_count` | `economy.near_failure_bank_count` | `banks` | `last` | 1 | 1 | 0 | `confidential` | `central_bank`, `regulator` | 需完整窗口；否则显式缺失 | 1 |
| `bank_failures` | `economy.n_bank_failures` | `banks` | `last` | 1 | 1 | 1 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1 |
| `credit_to_gdp` | `economy.credit_to_gdp` | `share` | `last` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1 |
| `energy_price` | `economy.energy_price` | `currency_per_unit` | `mean` | 7 | 7 | 2 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1 |
| `energy_stock` | `economy.energy_stock_total` | `energy_units` | `last` | 1 | 1 | 0 | `operational` | `energy` | 需完整窗口；否则显式缺失 | 1000 |
| `energy_unfilled` | `economy.energy_unfilled` | `energy_units` | `last` | 1 | 1 | 0 | `operational` | `energy` | 需完整窗口；否则显式缺失 | 100 |
| `energy_subsidy_paid` | `economy.energy_subsidy_paid` | `currency` | `sum` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1000 |
| `exchange_rate` | `world.e` `[economy_id]` | `numeraire_per_currency` | `last` | 1 | 1 | 0 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1 |
| `current_account` | `world.current_account` `[economy_id]` | `currency` | `sum` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1000 |
| `nfa` | `world.nfa` `[economy_id]` | `currency` | `last` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 1000 |
| `fx_reserves` | `world.reserves_by_economy[economy_id]` | `anchor_currency` | `last` | 1 | 1 | 0 | `operational` | `central_bank` | 需完整窗口；旧记录缺映射时显式缺失；从未持有储备/无账户为 0；退出 peg 后尚未清算的储备仍归原持有者 | 1000 |
| `migrant_stock` | `world.migrant_stock` `[economy_id]` | `persons` | `last` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 100 |
| `remittances` | `world.remittances` `[economy_id]` | `currency` | `sum` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 100 |
| `import_volume` | `world.import_volume` `[economy_id]` | `goods` | `sum` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 100 |
| `export_volume` | `world.export_shipped_volume` `[economy_id]` | `goods` | `sum` | 30 | 30 | 7 | `public` | 全部 | 需完整窗口；否则显式缺失 | 100 |
| `oracle_daily_output` | `economy.real_output` | `—` | `last` | 1 | 1 | 0 | `oracle` | `oracle` | 需完整窗口；否则显式缺失 | 100 |
