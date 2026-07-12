# v16/v17 Parallel Log (append-only)

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
