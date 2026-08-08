# Native no-shock baseline findings

Date: 2026-07-30  
Updated: 2026-08-03
Branch: `fix/native-calibration-v38`
Starting revision: `79a60e949e3b1b69f323f8564af844dd5b646303`

## 1. Decision

The reported 40% persistent unemployment was not a credible no-shock baseline.
It was the aggregate result of several implementation defects, daily-clock
calibration errors, and cold-start imbalances rather than a single labor-market
parameter.

After the repairs in this branch:

- a 100,000-person closed economy runs for ten years with annual mean
  unemployment between 3.8% and 10.8%, ending at 8.6%;
- a 1,000,000-person economy averages 4.0% unemployment in year one and ends at
  5.2%;
- three open economies of 100,000 people each run for five years with distinct
  trade, FX, migration, and current-account paths, ending at 4.8%, 5.6%, and
  8.1% unemployment;
- the actual Godot new-game contract at its reported day 514 now records 4.9%,
  5.0%, and 5.8% unemployment instead of 30.1%, 35.8%, and 38.0%;
- deterministic genesis matching now opens with approximately 95% of the
  participating labor force employed, removing the artificial 85.7% day-one
  unemployment release;
- a post-matcher 1,000,000-person run starts at 5.60% unemployment, averages
  3.16% in year one, and ends at 3.33%;
- no healthy bank ends a tested day with negative reserves;
- lender-of-last-resort advances have a repayment lifecycle instead of becoming
  permanent reserve creation;
- idle construction firms consolidate without destroying housing work in
  progress or registered dwellings;
- the 49-test pure-native release suite passes with eight workers.

This is now a credible simulation baseline, but it is not an empirical
calibration claim. Energy affordability, long-run capital replacement, housing
repricing, and labor-cycle amplitude remain explicit calibration frontiers.

## 2. What a no-shock path should do

“No exogenous shock” does not mean “unchanging steady state” in the current
engine. The default world still contains endogenous and deterministic motion:

- country profiles apply positive annual TFP growth;
- firms update expected demand, prices, wages, inventory, investment, and
  leverage;
- Calvo adjustment and sampled labor/goods matching create idiosyncratic
  variation;
- persistent jobs can be hired, suspended, recalled, separated, or replaced;
- credit, default, entry, exit, and bank competition remain active;
- fertility, mortality, household formation, retirement, and participation
  continue;
- housing resale, rent, mortgage, and construction mechanisms continue;
- open economies continue trade, capital-flow, FX, and migration adjustment.

The expected qualitative result is therefore a bounded stochastic growth path
with business-cycle variation, not a flat line. In the absence of a structural
imbalance, unemployment should not converge to 40%, banking reserves should
close cleanly, and inactive firms should not preserve large quantities of
money or physical assets forever.

## 3. Confirmed defects and repairs

| Area | Confirmed problem | Repair |
|---|---|---|
| Desktop baseline regime | The start menu omitted its default `tfp_law=exogenous` value from the override object, while the native new-game builder seeded `stochastic=false`. Every Calvo wage and price draw was consequently fixed at one, so no adjustment probability below one could ever fire. | Seed the playable native baseline in the exogenous stochastic regime; an explicit learning-law override can still disable it. |
| Diagnostic/product parity | `NativeSimulationSession.create` independently translated `NewGameSpec` through Python `Config`, so native diagnostics could use different defaults from the Godot worker despite executing the same C++ dynamics. | Route product `NewGameSpec` construction through the same C++ parser and initial-policy application used by the desktop worker. |
| Daily monetary clock | The direct native new-game path retained period-rate defaults, including a 1% policy rate and 10% principal amortization every day. | Aligned native new-game monetary, Taylor, amortization, valuation, and maturity values with the daily clock. |
| Genesis demand | Opening expected demand was too high for the sustainable labor flow and caused an inventory boom followed by mass suspensions. | Set opening expected demand to 6.25 representative units. |
| Genesis inventory | Firms opened with roughly one day of stock while targeting fourteen days, creating an artificial inventory investment wave. | Seeded consumption and capital-goods inventory at 87.5 representative units, matching the fourteen-day target. |
| Household demand leakage | A 0.90 permanent-income propensity created persistent aggregate-demand leakage on a daily clock. | Raised the playable baseline propensity to 0.97. |
| Consumer rationing feedback | Transient genesis stockouts became a persistent positive demand signal and amplified the artificial cycle. | Kept the mechanism configurable but disabled it in the stable playable baseline. |
| Fiscal measurement | Transfers were omitted from the deficit impulse used by fiscal feedback. | Included transfers and separated fiscal quantities from the deficit regime. |
| Labor measurement | Suspended zero-hour workers were omitted from headline unemployment even though they produced no labor or income. | Included them in headline slack while retaining a separate suspended stock. |
| Labor demand | Notional vacancies could survive without finance and overstate usable demand. | Matching and reporting now distinguish effective funded labor demand. |
| Labor adjustment | Firing and suspension adjustment was too abrupt for a daily persistent-job model. | Recalibrated the M7 adjustment path and exposed the open/suspended decomposition. |
| Genesis labor stock | Genesis created an empty employment book, so the first published day showed approximately 85.7% unemployment even though the configured economy was not in a depression. | Deterministically seed 95% of participating people into full-hour consumption, capital, and energy jobs before the first tick; initialize firm labor history from worker efficiency. |
| Worker productivity | The playable native path left every person's labor efficiency at exactly one even when individual efficiency was enabled in `Config`. | Add deterministic, mean-preserving lognormal efficiency draws for genesis persons and births, and carry the rule through C++, C ABI, Python bindings, and checkpoints. |
| Suspended-worker participation | A worker could leave the labor force while retaining a suspended recall option; a later recall then sold labor above the household's reported capacity. | Close retained contracts on participation withdrawal and forbid recall for non-participants. |
| Large-population dividends | Independently accumulated dividend totals could differ from clearing cash by a few floating-point ulps, overdrawing the final household in a large equal distribution. | Distribute the projected clearing balance recursively and give the exact remaining balance to the last recipient. |
| Bank day-end order | Energy, housing, and other extension payments could occur after the first interbank close. | Added a final domestic interbank/LoLR liquidity close after extension settlement. |
| World settlement order | Trade, tariff, and remittance cash posted after domestic banks had already closed, leaving final reserve overdrafts. | Added a world-settlement liquidity close with explicit interbank loans and LoLR fallback. |
| LoLR lifecycle | LoLR advances accumulated indefinitely and permanently inflated reserves. | Added maturity servicing, principal retirement, interest payment, outstanding metrics, and operation-record reuse. |
| Bank entry | A founder could capitalize a new bank even when the founder’s source bank could not settle the reserve transfer. | Bank entry now requires both available deposits and available source-bank reserves. |
| Failed-bank reserves | Residual reserves could remain attached to failed banks. | Reassigned residual reserve positions during resolution. |
| Interbank default | Default losses were not allocated through a complete recovery and pro-rata loss path. | Added explicit recovery, pro-rata lender loss, and record closure. |
| Firm exit | Productive capital, inventory, energy stocks, builder WIP, or dwelling title could disappear at firm exit. | Transfers physical assets and recoverable debt to a live same-sector successor before retiring the firm. |
| Export reservation | An exporter could exit after goods were reserved but before world settlement. | Protects reserved exporters for the current world tick. |
| Construction lifecycle | Construction was excluded from subscale exit, so thousands of permanently idle builders retained cash and capital. | Construction participates in subscale consolidation while preserving at least one sector firm. |
| Housing genesis | A balanced initial housing stock still seeded builder demand and debt without uncovered buyers. | Set builder cold-start demand to zero and derive construction from uncovered demand. |
| Housing price path | Repeated stale-listing markdowns mechanically collapsed the national index. | Reduced ask decay, added a wage-based floor, and prevented forced sales from mechanically rebasing the index. |
| Energy genesis | Energy opened with inconsistent price, inventory cover, and demand forecasting. | Aligned opening price, household need, producer/downstream stocks, gap closing, and capacity-share forecasting. |
| Conservation tolerance | Fixed absolute reserve tolerances failed at large money scales. | Scaled reserve invariant tolerance to the conserved magnitude. |

## 4. Playable baseline calibration

The principal baseline choices are now explicit in
`enable_complete_playable_modules` rather than inherited from historical model
versions:

- permanent-income consumption propensity: `0.97`;
- opening expected demand per representative firm: `6.25`;
- opening final- and capital-goods inventory: `87.5`;
- consumption rationing feedback: off by default;
- initial policy rate: `1.34e-4` per day;
- business-loan amortization: `1 / (365 * 2.5)` per day;
- household-loan amortization: `1 / (365 * 5)` per day;
- opening energy price: `1.20`;
- producer and downstream energy cover: fourteen days;
- downstream energy stock-gap closure: `0.02` per day;
- builder cold-start demand: `0`;
- stale housing ask decay: `0.005` per market session;
- housing ask floor: two annual wages;
- firm subscale exit and capital-firm entry: enabled.
- person-level labor efficiency: enabled, with lognormal sigma `0.35` and a
  mean-preserving correction;
- genesis employment coverage: `0.95` of the participating labor force.

Population overrides scale representative firm cash, inventory, capital, energy
cash, builder cash, and opening bank capital. This is necessary for a
100,000- or 1,000,000-person run to preserve the same per-person opening
balance-sheet geometry as a small run.

## 5. Dynamic evidence

All runs below use the actual `_native` module. Python is only the diagnostic
driver and JSON summarizer; it does not execute the legacy Python economy.
Sections 5.2-5.4 were collected before product-construction parity was enforced:
they exercise the same C++ dynamics through the Config bridge, but should not be
mistaken for byte-for-byte Godot new-game contracts. Section 5.5 is the direct
desktop contract and is the authoritative reproduction of the reported UI
failure. Sections 5.2-5.5 predate the explicit genesis employment matcher;
section 5.6 is the current post-matcher acceptance evidence.

### 5.1 Pure-native release regression

```text
ctest --test-dir build/native/m11-release \
  --output-on-failure -LE python-binding -j8
```

Result: 49/49 passed.

The unfiltered 74-test command also executed historical Python oracle and
binding tests. Four of those failed because they intentionally compare against
stale Python M4 goldens or import metric IDs from another worktree. They are not
part of the native-engine acceptance set and were not used to force the C++
engine back to the historical trajectory.

### 5.2 Closed economy: 100,000 people, ten years, seed 23

| Measure | Result |
|---|---:|
| Runtime | 191.9 s |
| Time per simulated day | 0.0526 s |
| Known retained memory | 338 MB |
| Year-one mean unemployment | 3.83% |
| Years 2-10 mean unemployment | 8.43% |
| End unemployment | 8.64% |
| End open unemployment | 4.27% |
| End suspended share | 4.37% |
| End participation | 80.65% |
| Real output per capita, first/last window | +10.6% |
| Price level, first/last window | -3.9% |
| Productive capital, first/last window | -7.9% |
| Population | -3.15% |
| Mean poverty after year one | 19.67% |
| End public debt / annual GDP | 49.0% |
| End credit / annual GDP | 13.8% |
| Bank failures | 0 |
| Minimum healthy-bank reserves | numerical zero (`-3e-13`) |
| LoLR advances / maximum outstanding | 0 / 0 |
| Builder firms | 625 to 1 |
| Housing stock | unchanged at 42,000 |
| House price | -38.3% |
| Physical energy shortage after year one | 0.69% |
| Unfilled desired energy after year one | 12.4% |

The energy difference is important: most unmet desired demand is an
affordability/finance signal rather than a physical production shortage.

### 5.3 Closed economy: 1,000,000 people, one year, seed 23

| Measure | Result |
|---|---:|
| Runtime | 173.8 s |
| Time per simulated day | 0.476 s |
| Known retained memory | 1.08 GB |
| Mean unemployment | 4.01% |
| End unemployment | 5.15% |
| End open unemployment | 1.91% |
| End suspended share | 3.24% |
| End participation | 80.28% |
| End poverty | approximately 18.8% mean over the year |
| Bank count | 80 |
| Minimum healthy-bank reserves | 38,427 |
| LoLR advances / maximum outstanding | 0 / 0 |
| Bank failures | 0 |

Day one reports 85.7% unemployment because genesis creates people and firms but
does not pre-assign a complete employment network. It falls to 32.9% by day
seven, 1.5% by day 30, and 0.9% by day 90. This is a visible creation transient,
not the long-run state. It should either be hidden behind an initialization
period or replaced by an explicit genesis employment matcher before first
release.

### 5.4 Open world: 3 x 100,000 people, five years, seed 23

| Measure | Economy 1 | Economy 2 | Economy 3 |
|---|---:|---:|---:|
| End unemployment | 4.77% | 5.57% | 8.10% |
| Mean unemployment after year one | 6.19% | 6.43% | 7.94% |
| Real output per capita | +7.8% | +23.0% | -2.0% |
| Price level | +11.9% | +18.0% | +13.3% |
| Productive capital | -6.1% | -3.2% | -8.4% |
| Population | -1.74% | +0.77% | +0.15% |
| End FX rate | 0.794 | 0.775 | 1.625 |
| End NFA | +630,293 | +68,816 | -178,658 |
| Minimum healthy-bank reserves | 0 | 231 | 0 |
| LoLR maximum outstanding | 0 | 0 | 0 |
| Builder firms | 1 | 1 | 1 |

Total runtime was 96.4 seconds, or 0.0528 seconds per three-country world day,
with eight workers and approximately 505 MB of known retained memory.

The nonzero world-NFA residual is currently explained partly by FX dealer
spread and valuation bookkeeping. It is small relative to five years of world
output but should remain an explicit identity diagnostic rather than be called
zero.

### 5.5 Godot product contract: default three-country sandbox, seed 7

The exact start-menu manifest was parsed by
`parse_m11_native_new_game`, with the default profile populations of 100,000,
150,000, and 80,000 people. Before the repair, the day-514 result reproduced the
user-visible failure exactly:

| Economy | Before repair | After repair | Price index after repair |
|---|---:|---:|---:|
| Advanced | 30.10% | 4.85% | 1.067 |
| Developing | 35.83% | 4.98% | 1.086 |
| Petrostate | 38.05% | 5.84% | 1.097 |

Before the repair, all three price indexes remained exactly at their opening
value of 0.800 through day 514. That invariant was the identifying symptom:
Calvo wage and price adjustment was not merely slow; it was unreachable.

The product path was also rerun through the unified diagnostic session with
three 100,000-person economies to day 545. Unemployment ended at 4.27%, 5.63%,
and 5.46%, while all three price indexes moved to approximately 1.09-1.11.

### 5.6 Post-matcher native acceptance, 2026-08-03

The current product-construction path was rerun after genesis employment and
person efficiency were wired into the native engine. Every run used eight
workers and the C++ `_native` engine; Python was only the command-line driver
and JSON summarizer.

Three independent 100,000-person, two-year closed-economy seeds produced:

| Seed | Day-one unemployment | Year-one mean | Year-two mean | Day-730 unemployment | Open / suspended at day 730 |
|---:|---:|---:|---:|---:|---:|
| 7 | 5.64% | 3.28% | 5.80% | 10.82% | 6.73% / 4.10% |
| 23 | 5.64% | 3.25% | 6.09% | 11.59% | 6.08% / 5.51% |
| 101 | 5.60% | 3.17% | 5.78% | 8.95% | 5.45% / 3.50% |

All three runs completed without bank failure or invariant violation. A repeated
30-day, seed-7 run produced the identical state digest
`11079879754119722460`; the complete summaries were byte-identical after
removing timing and module-path metadata.

The 1,000,000-person, one-year seed-23 run produced:

| Measure | Result |
|---|---:|
| Runtime / time per simulated day | 195.6 s / 0.536 s |
| Known retained memory | 1.10 GB |
| Day-one / year-mean / year-end unemployment | 5.60% / 3.16% / 3.33% |
| End open unemployment / suspended share | 1.32% / 2.01% |
| End participation | 79.71% |
| Mean poverty / end price index | 17.31% / 1.062 |
| Healthy banks / failures / negative reserves | 80 / 0 / 0 |
| LoLR advances | 0 |

Finally, the three-country product path with 100,000 people per economy ran to
day 545. Unemployment started at 5.64%, 5.25%, and 5.80%, and ended at 4.89%,
5.16%, and 5.59%. All three price levels and exchange rates moved, and no bank
failed or ended with negative reserves. This is the current authoritative
answer to the reported 30-40% unemployment failure.

## 6. Remaining model limitations

These findings did not justify another emergency bug fix, but they should guide
the next calibration round:

1. **Labor-cycle amplitude.** The genesis discontinuity is resolved, but the
   100,000-person two-year seeds can finish near 9-12% unemployment as vacancies
   collapse late in the second year. This is an endogenous cycle rather than a
   30-40% steady-state failure, but hiring, suspension, and recall parameters
   still need observed-data calibration over longer multi-seed panels.
2. **Energy affordability.** Physical shortage is low in the ten-year closed
   run, yet desired energy demand remains materially unfilled and mature energy
   markups can reach the cap. Entry, price competition, affordability, and
   working-capital demand need separate ablations.
3. **Capital replacement.** Productive capital falls 3-8% in most tested
   long-run paths despite positive TFP. This can be plausible during structural
   reallocation, but the replacement/user-cost equation needs a stationary
   calibration target.
4. **Suspension persistence.** Roughly half of end unemployment can be
   suspended contracts. The decomposition is now correct, but recall hazards,
   employer option value, and maximum suspension duration need empirical
   calibration.
5. **Housing correction.** Falling population and excess initial stock explain
   part of the house-price decline, but a 38% ten-year correction should be
   tested against fixed-population and tighter-stock counterfactuals.
6. **Sector entry.** Construction consolidates correctly, but there is no
   endogenous builder revival when uncovered demand returns. Energy entry is
   also limited. A sector-specific entry mechanism is preferable to disabling
   consolidation.
7. **Firm concentration.** Many surviving capital and energy firms report zero
   current sales or hires. The subscale lifecycle is now active, but sector
   viability thresholds should be calibrated by representative-agent scale.
8. **National accounts.** The expenditure residual is small, while the income
   residual remains larger at million-agent scale. It must remain visible until
   accrual coverage is complete.
9. **Bank entry.** Bank entry is now settlement-feasible, but profitability can
   still double bank count in a decade. Entry probability and minimum efficient
   scale need a stationary target.
10. **Empirical calibration.** The present acceptance target is internal
    credibility and bounded dynamics. Matching real unemployment, inflation,
    wealth, housing, credit, and demographic distributions requires a separate
    observed-data calibration exercise with multiple seeds.

## 7. Reproduction

```bash
cmake --build build/native/m11-release -j8
ctest --test-dir build/native/m11-release \
  --output-on-failure -LE python-binding -j8

PYTHONPATH="$PWD/build/native/m11-release/native:$PWD" \
  .venv/bin/python \
  scripts/native_baseline_profile.py \
  --population 100000 --countries 1 --days 730 \
  --seed 23 --workers 8 --chunk-days 30

PYTHONPATH="$PWD/build/native/m11-release/native:$PWD" \
  .venv/bin/python \
  scripts/native_baseline_profile.py \
  --population 1000000 --countries 1 --days 365 \
  --seed 23 --workers 8 --chunk-days 15

PYTHONPATH="$PWD/build/native/m11-release/native:$PWD" \
  .venv/bin/python \
  scripts/native_baseline_profile.py \
  --population 100000 --countries 3 --days 545 \
  --seed 7 --workers 8 --chunk-days 15
```

The diagnostic driver stores bounded metric history and reads only public
native history/probe interfaces. It does not access private simulation state.
