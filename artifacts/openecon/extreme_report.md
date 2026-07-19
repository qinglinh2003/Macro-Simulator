# Extreme-world portrait campaign: 11 runs, cross-world report

**Campaign**: X1-X10 + X7b recalibration, 6-economy archetype world (China, India,
USA, Germany, Gulf, Hub), 30y x pop2 (X5: 60y x pop1), seeds 4242+.
**Engineering verdict: 11/11 IDENTITY PASS, zero crashes, zero conservation
violations** — across currency crisis, 24x-leverage banking stress, population
boom AND collapse, 12-36%-GDP fiscal blowout, -70% energy shock with hard
rationing, NIM banking, trade war with embargo, mortgage-at-scale, and a
60-year drift marathon. The v24 checkpoint/claims machinery held everywhere.

## Run matrix

| run | scenario | headline result |
|---|---|---|
| X1 | currency crisis (engineered) | MISFIRED: baseline-rate assumption wrong -> China was the HIGH-rate side -> reserves x19 (reserve mountain), peg never stressed |
| X2 | banking 24x leverage | 139 failures worldwide, system survived by rolling resolution; credit/GDP 41->5 (China); permanent deleveraging |
| X3 | population boom | **NEW BUG: construction stall** (+5 dwellings/30y everywhere); Gulf rent x8 with zero supply response |
| X4 | fiscal blowout 12-36% GDP | fiscal dominance: India CPI x36 w/ Taylor pinned at r_max; 87% of deficit monetized past the bond market |
| X5 | 60y century | **A5 drift is BOUNDED** (identity passes at t=21,900); civilizational decline (Hub: 11 adults, GDP 33); China house price = 0.00 exactly |
| X6 | aging collapse | open-borders Germany got ZERO migrants (global aging = no wage gaps = no one to attract); elder dependency ~1.0 |
| X7 | energy -40% | NULL: sector runs at 44% utilization, slack absorbed the shock entirely |
| X7b | energy -70% | rationing regime: utilization pinned 1.0, unfilled x550, China -7.6% then adapts; **India GDP -99% (destroyed)** — asymmetry to dissect |
| X8 | NIM banking | deposit interest is DEADLIER than leverage: China 29 failures -> 1 monopoly bank; **NEW BUG: silent deposit-interest default** (cash cap, no arrears) |
| X9 | trade war | no autarky: embargoed CN-US reroute via third countries; tariff revenue flows; machinery sound |
| X10 | mortgage boom | origination at scale works (272k cum, identity OK); **no bubble possible** — construction stall + floorless prices dominate credit fuel |

## Systematic findings (cross-world)

1. **DEALER BLEED — 9/9 worlds, ΣNFA always positive**: 7.4M (X7b) / 6.99M (X5)
   / 5.4M (X2) / 3.5M (X8) / 2.9M (X9) / 1.5M (X4) / 1.49M (X1) / 1.9M (X10) /
   0.87M (X6). Ranking correlates with FINANCIAL/settlement flow intensity, not
   trade volume (banking/crisis worlds bleed most, aging least). The FX dealer
   is the universal unbounded loss counterparty. **-> promote to next engine patch.**
2. **Construction stall (NEW)**: two-sided death spiral — shortage side: land fee
   (0.2 x price) unpayable by cash-poor builders -> WIP frozen forever; collapse
   side: price < unit cost -> demand-prior decay shuts builders down. Housing
   supply elasticity ~= 0 in EVERY world. Candidate fix: financeable/staged land
   fees (construction credit), builder seed recap tied to WIP.
3. **Floorless house prices (NEW, A1b family)**: 0.00 (X5 China), 0.21 (X6
   Germany), 0.79 (X5 Hub), 150 (X10 USA vs 1277 genesis). No floor in the sale
   market; degenerate ratios downstream. Fold into the A1b fix.
4. **Silent deposit-interest default (NEW)**: payment capped by bank cash with no
   arrears ledger — cash-starved banks stiff depositors without record (X8: owed
   ~167/tick, paid 0.23). Fix: arrears ledger or resolution trigger.
5. **Static peg pressure**: reserves NEVER moved in any equal-rate world (8000.0
   exact, 4 worlds); X1's misfire doubles as proof. FIXED in B5b (live rates) on
   feat/controllers-v26; X1/X4 reruns on new semantics = the natural experiment.
6. **Monetization / toothless nominal anchor** (v19 thread, fiscal edition):
   deficits bypass the demand-constrained bond market straight into ledger
   overdraft; Taylor pinned at r_max cannot chase. The monetary patch arc's
   test scenario is ready-made (X4).
7. **Zombie negative-capital bank** (X2 China): quantify persistence in a follow-up.
8. **India energy fragility** (X7b): -99% GDP under rationing while China adapts —
   dissect (deprivation cascade? energy-Leontief binding? population growth?).

## Emergent economics worth keeping (not bugs)

- Rolling banking crises end in near-zero credit worlds (X2) or monopoly banking
  (X8) — concentration dynamics from opposite causes.
- Global aging kills the migration lever: open borders attract no one when
  every wage gap closes (X6).
- Trade wars reroute rather than de-globalize at tariff 0.4 (X9).
- Fiscal dominance prints the textbook dispersion: same blowout -> x36 inflation
  (India) vs deflation (China) depending on capacity regime (X4).

## Experiment-calibration notes

- X1: setting only the pegger's r_interest is not a mismatch experiment — set ALL
  baselines explicitly (moot under B5b live-rate semantics).
- X7: check utilization headroom before sizing capacity shocks (44% slack ate -40%).

## Recommended queue (proposal)

1. Dealer bleed (engine patch, design first — universal, unbounded)
2. Construction stall (portrait-blocking: housing supply dead in every world)
3. Floorless prices (fold into A1b) + deposit-interest arrears (small, scoped)
4. B5b-semantics reruns of X1/X4 (validation of the peg fix, cheap)
5. India-X7b autopsy + zombie-bank quantification (analysis, no code)
