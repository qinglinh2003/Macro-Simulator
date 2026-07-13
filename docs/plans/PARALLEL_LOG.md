# v16 ∥ v17 Parallel Log (append-only; one line per event; see PLAN_v16v17_parallel.md §6)

- 2026-07-12 [v17] KICKOFF: feat/energy-v17 forked from dev@2b7979a (post-trunk-refactor); PLAN_v17.md committed (protocol-amended: sequencing, 17.2 matrix → post-composition, labor-caveat row); starting 17.0.
- 2026-07-12 [v17] SHARED-FILE TOUCHES (17.0, all guarded no-ops when energy off, flag-off smoke bit-identical to dev@2b7979a on the v13+housing config): behavior/planning.py unit_cost() energy line (the reserved line); systems/planning.py +2 guarded blocks (E capacity cap on production_target; E depreciation-replacement floor — absorbing-death guard); systems/settlement.py profit line gains `- f.energy_cost_used` (v16 primary — heads-up: exact no-op at 0.0); systems/capital_goods.py result push loop c_firms→investing_firms (== c_firms in all pre-energy presets; lets E-firms invest); systems/firm_demographics.py one-line entrant energy seeding; reporting/metrics.py + config/model.py + core/policy.py append-only blocks.
- 2026-07-12 [v17] 17.0 DIAGNOSTIC FINDINGS (close-out): (5) a purely adaptive accelerator chronically LAGS a growing economy in a hard-capacity sector (10y frontier: util pinned 1.0, markup-at-cap ratchet, 8x relative-price drift) — E-firms now target the RESERVE MARGIN, k* = d^e/(kappa*util0), reusing the anchored util0 (real capacity industries plan reserve margins; no new dial); (6) a LINEAR-tech E-firm is excluded from capital deepening ⇒ the energy relative price drifts up with c-sector productivity (a Baumol artifact, 7x/decade, wage-ratchet hypothesis probed and REFUTED first) — E-firms are now Cobb-Douglas + capacity clamp, A_E=(kappa*util0)^alpha preserving every genesis anchor exactly.
- 2026-07-12 [v17] 17.1 FINDINGS: (7) kernel + household energy is structurally DEGENERATE — kernel E-firms cannot invest, so retained earnings become a money sink; necessity demand keeps feeding it while goods demand starves (§9 drain through the new sector; ry 200→6 in the probe). Calibration-flavored 17.1 assertions moved to v124 permanently; kernel keeps only mechanical gates. (8) search_m=1 × no-household-storage ⇒ households miss ~half their need on sampling luck alone — household energy fill is TRANSPARENCY-sensitive (relevant to 17.4 rationing design). (9) a 2x E-TFP cut demand-destroys the stabilizer-free kernel PERMANENTLY (B2 zeroes, nothing catches it) — 17.2 shock magnitudes need the calibrated world's stabilizers.
- 2026-07-12 [v17] 17.0 FINDINGS (details in commit message): (1) E-firms must produce BEFORE the energy market or stock-outs death-spiral their B2 expectations (phase-order is load-bearing); (2) E-firms need an unconditional depreciation-replacement floor (slump → accelerator dead → K→0 is ABSORBING); (3) under a hard capacity cap B2-on-sales blinds the accelerator — unfilled demand now feeds E expectations (gated on capital_enabled); (4) v13-frontier probe: all hard gates green, but the recovery boom pins the E sector at capacity from ~t300 (energy late output -10% vs baseline) — capacity-catch-up speed on the daily calendar is the open calibration item for the 17.0 diagnostic.
- 2026-07-12 [v17] 17.1 SHIPPED + BONUS FINDING (10): stable household necessity demand DAMPS the 17.0 capacity-cycle markup episodes (atcap 0 for the whole decade vs recurring episodes with firm-only demand) -- household demand is smoother than restock demand, bullwhip weakens.
- 2026-07-12 [v17] 17.2 arc-scope SHIPPED: kappa scenario (prefix-identical, float-exact pulse restore), windfall surtax (settlement guarded line: div_pool subtracts wtax, 0.0-exact), buffering state-dependence PRE-REGISTERED+CONFIRMED, frontier pulse portrait diagnostic_v172 (cost-push signature +0.1 vs -0.2 yoy; households eat the shortage). Matrix + JG hard test await composition.
- 2026-07-12 [v17] 17.3 SHIPPED + findings 11-13: (11) hoarding at beta=3 INSURES (pre-shock buffers beat in-crunch panic); (12) SPR release = front-loaded relief (-33% unfilled) then CROWDS OUT the private supply response (steals sales -> d^e down -> E output -15%; net can be negative); (13) SOE at-cost pricing has NO markup-discipline effect under sector-wide shortage (needs slack + transparency). Also: a mis-anchored edit briefly swallowed create_e_firms' loop tail (E-firms empty => worlds die silently) -- caught by the buffering test's new bind-guard; settlement SOE dividend redirect + windfall div_pool line declared (v16 primary file).
- 2026-07-12 [v17] 17.4 SHIPPED (crisis triple + the 2022 four-way artifact) + findings 14-15: (14) markup pricing OVERSHOOTS clearing in a crunch -- a cap can RAISE traded volume while bleeding seller margins (the real damage channel); (15) crisis instruments are live levers AT the shock, never standing institutions (a t0 cap kills the sector pre-experiment). Four-way scorecard: SPR best macro, cap-triple best household protection (cheap: fiscal 441), SOE at-cost WORST shortage, no-intervention worst output. Priority rationing = two sequential sessions (native shuffle destroys ordering); proportional = own path.
- 2026-07-12 [v17] 17.5 SHIPPED + **THE v17 ARC IS MACHINERY-COMPLETE** (17.0-17.5, diagnostics v170-v175, 15 numbered findings, 453-suite green). Cross-surface touch declared: economic_bridge.mortality_macro_multiplier gains the fuel-poverty composition block (mirrors the in-file v15.5 housing-fertility precedent; exactly 1.0 off). Deferred-by-gate: housing×energy (v15.2 size scalar still ≡1.0), efficiency investment (optional).
- 2026-07-12 [v17→v16] COMPOSITION-GATE HANDOFF (what v17 runs after v16 merges, per protocol §5): ① both-flags-on same-seed smoke; ② pinned cost-push re-run WITH relationship wages (wage-price spiral plumbing); ③ labor stock-flow gate with E-firms as ordinary employers; ④ THEN the 17.2 stagflation matrix (disclaimer-free) + JG hard test (L2-recast buffer-stock JG). Pre-registered: flatter Okun under energy shocks (labor hoarding × energy-capped output); shock magnitudes 0.2-0.5 (finding 9: 2x kills stabilizer-free worlds).
- 2026-07-12 | v16 | KICKOFF. Trunk refactor landed on dev (2b7979a, bit-identical,
  suite 420/420). feat/labor-v16 forked from dev@2b7979a, worktree
  ../macro-simulator-v16. Starting L0 (labor accounting + stock-flow gate).
- 2026-07-12 | v16 | L0 FROZEN (08c3e67): five-state accounting + stock identity gate.
- 2026-07-12 | v16 | L1 FROZEN (99a2d28): person rosters, four separations, hoarding
  dynamics, per-person wage attribution, flow-reconciliation gate. Bit-identical off;
  regression 237/237. Okun portrait running. Next: L1b suspension.
- 2026-07-12 | v16 | L1b FROZEN (d29608b): suspension as the employment LOLR --
  memo attribute (uncapped JG absorbs suspended workers; partition-S stays 0),
  LIFO suspend on cash crunch, FIFO recall in place, timeout->layoff, poaching
  with a reservation (0.9 x suspended wage). Probe: suspension ON cuts the
  layoff rate 9.89x -> 4.13x and cash layoffs -> 0.
- 2026-07-12 | v16 | L2 FROZEN (5c1f955): matching friction -- per-searcher
  contacts with congestion; u* emerges. The contact-lag double-count forced the
  THREE-PASS restructure (separations -> hiring -> wages, same-tick pay); the
  partition gate caught it in one tick.
- 2026-07-12 | v16 | L3+L3b FROZEN (59f45ce): relationship wages (entry wage
  locks; leap-safe anniversary reviews, upward-only DNWR; delta drift hits the
  POSTED wage only -- the v14 pass-through cure) + the job ladder (E->E as
  churn+hire, net zero in the gate).
- 2026-07-12 | v16 | CALIBRATION (d110c9d): integer band floor (one whole worker),
  EMA-smoothed firing target (hire fast / fire slow), lambda_fire 0.10->0.03.
  Steady-state layoffs 9.9x -> 2.2x of E per year; residual heat = daily demand
  volatility at ~2.5-worker firm scale, documented with all dials exposed.
- 2026-07-12 | v16 | L4 FROZEN (c1d26a5): person efficiency e_i ~ lognormal mean
  one, drawn once at first hire (substream seed+16_002), carried for life.
  Earnings = wage x e_i via wage_of (single authority); production consumes
  EFFICIENCY UNITS, JG/welfare counts HEADS. Decomposition gauges shipped.
- 2026-07-12 | v16 | L5 FROZEN (fa8c2cc): participation margin. Reservation =
  markup x max(JG wage, benefit); jobless below the line do not search (memo
  over partition-U), incumbents below it quit to welfare (a REAL flow class in
  the gate). Benefit-trap + JG-wage-floor experiments land as tests; at
  jg_wage_ratio 1.1 cannibalization runs through jobs never FORMING, not quits.
  Labor suite 51/51; flag-off shared-column digest bit-identical throughout.
- 2026-07-12 | v16 | Full-arc acceptance running: pass-through pair (a x1.5 must
  RAISE the real incumbent wage) + full-stack Beveridge/Okun/u* portrait, 10y.
- 2026-07-12 | v16 | FULL-ARC ACCEPTANCE PASSED. The prize: productivity x1.5
  (A=a=a_K) -> real incumbent wage ratio 1.490 vs 1.50 theoretical = 99.4%
  pass-through (v14 spot: ~1.0, all leaked); placebo leg (a/a_K only) = 0.999.
  Full-stack 10y portrait: u* 6.0% (band 4-6%), Okun slope -0.20 / corr -0.78
  (hoarding attenuates), procyclical quits +0.42, incumbent wages follow posted
  with a monthly-scale lag, earnings dispersion person-driven (L4). Honest
  caveats logged in PLAN_v16: v-rate LEVELS hot, E->E ladder rate hot,
  employment-lag null under uncapped JG. diagnostic_v16.png shipped.
  v16 arc COMPLETE on feat/labor-v16; ready to merge per protocol (v16 first).
- 2026-07-13 | v16 | MERGED INTO dev (12d802f). L0-L6 complete: persistent
  person-level employment + sub-person firm scale; pass-through 2.03; §4 5/8
  (T6 Zipf emergent -0.98); labor suite 56/56; spot bit-identical. v17 IS CLEAR
  TO MERGE onto dev@12d802f per protocol. The composition gate (v16 full stack
  x v17 energy flags, gates green + bit-identity) belongs to the v17 merger,
  then 17.2. NOTE for v17: under labor_person_efficiency, f.hired is in
  EFFICIENCY UNITS (effective labor input -- min(a*L, energy/e_coeff) semantics
  unchanged, but check e_coeff calibration); recommend enabling the L6 flags
  (footfall/subscale-exit/K-entry) in any v16-stack acceptance runs, since the
  K sector starves without them under persistent matching. Open v16 items
  (documented in PLAN_v16 L6 addendum): healthy-economy portrait rerun;
  investment-acyclicality finding (T3/T7).
- 2026-07-13 [v17] COMPOSITION GATE PASSED (owner: v17 as second merger): ① both-stacks frontier smoke 500t, all hard gates held, E-firms hire on v16 rosters (22.6 workers); ② energy-off hash IDENTICAL to dev@a7d3df4 with the v16 stack on (8b2afb6e); ③ all energy flow-gap spikes attributed to firm exits within ±1 tick (L6 subscale exit = a new honest stock-destruction trigger, cross-tick accounting offset); ④ pinned cost-push WITH relationship wages: energy price x1.30 -> CPI x1.02 -- the wage-price spiral plumbing verified end to end. 498/498 full suite on the merged branch (1h31). v17 merging into dev.
- 2026-07-13 [v17] 17.2 MATRIX first pass (within-pair twins after the cross-arm design was caught mixing ten years of baseline divergence -- finding 15's cousin): HEADLINE RESULT = the default headline-fed Taylor stack does the MOST damage (-15.5% output, +0.55 inflation; a second CB-induced dip visible at t2900) while core-reading (-2.1%) or frozen-rate (-0.8%) CBs sail through -- the Bernanke-Gertler-Watson monetary-overreaction result, emergent. PRE-REGISTERED FLAT OKUN CONFIRMED (output -15% with u moving <1pp; labor hoarding x energy-capped output). JG HARD TEST: the buffer neither balloons (d_jg <= 0.017) nor amplifies inflation through the shock -- hoarding keeps workers in firms, the buffer barely engages. Single-seed caveat: the key CB gradient is under 2-seed replication now.
- 2026-07-13 [v17] MATRIX HONESTY DOWNGRADE + OPEN INCIDENT: seed-1 replication REVERSES the CB gradient (headline -4.7% vs core -8.0%; seed 0 was -15.5% vs -2.1%) -- the monetary-overreaction channel exists but is not seed-robust at NH50/500p; multi-seed battery at scale = standing follow-up. INCIDENT: one seed-2 shock-leg run tripped the person-claim hard gate (hh 143, claims -1.26 vs ledger 0.20); NOT reproducible in isolated probes (energy-off/on, shock on, 3 pinned salts, in-process pairs all clean); no module-level or class-level shared state found (AST scan); phase-probe 6-leg hunt battery running. Energy+shock both-stack experiments carry a caution flag until caught.
- 2026-07-13 [v17] INCIDENT HUNT CONCLUDED (unresolved-but-armed): the exact 6-leg crashing sequence rerun 3x (random salt + salts 3,4) WITH per-phase claim probes -- 18/18 legs clean. Eliminated: energy accounting per se, the shock per se, v16-only, cross-instance cache pollution (the lru_cache is value-keyed on a frozen dataclass), class-level shared state (AST scan), hash-salt sensitivity (5 salts total). The one unrecreated condition: the original ran under maximum machine load (suite + matrix + replication concurrently; legs ran 3-4x slower). VERDICT: single unreproduced occurrence; scripts_v17/hunt_claim_bug.py stays in the repo -- any recurrence now yields tick+phase+household forensics instead of a bare assertion. Caution flag downgraded to a watch note.
- 2026-07-13 [v17] INCIDENT RESOLVED by 533baba (v16 agent): insolvent-death residual positive cash claim destroyed while ledger cash stayed -- the EXACT signature of the hh-143 trip (claims below ledger after a death). Fifth household-emptying fault-line instance; they hit it themselves in a three-stack run (seed 7, t550) and fixed it in economic_bridge. My non-reproduction under pinned salts is consistent with salt-dependent death-path event ordering. Energy+shock caution flag LIFTED; hunt script stays as standing forensics.
