# V16 Labor Market Plan — Persistent Person-Level Employment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the daily spot labor market with persistent, PERSON-level employment
relationships — rosters, frictional matching, relationship wages — behind a flag, with
the spot path preserved verbatim.

**Why now — three standing threads share this root:**
1. **u ≡ 0 / no natural rate.** Matching completes every tick, so unemployment exists
   only in collapses; the Taylor φ_u and the fiscal deficit_u rule read a degenerate
   signal. Search friction (L2) creates u*, the Beveridge curve, and makes the JG a
   buffer against FRICTION rather than only against collapse.
2. **The pass-through blocker (v14 finding).** Productivity gains are absorbed into
   deflation because the free-hire wage drift (delta) cuts EVERYONE's nominal wage.
   Relationship wages (L3) confine drift to the POSTED wage; incumbent DNWR ratchets
   per person — productivity then reaches real wages, the Phase 2 level signal x_t
   finally gets secular drift, and the demographic transition machinery (armed and
   waiting since v14) receives its stimulus. This is the biggest single prize.
3. **Homogeneous labor blocks Phase 3.4.** Person-level relationships + an efficiency
   factor (L4) are the prerequisite for human-capital transmission and honest
   individual earnings distributions.

**Architecture decision (settled in design review): employment attaches to PERSONS.**
Rosters are (person, firm) pairs. The demographic layer is already person-level
(`labor_supply_for_person`, person claim sheets), labor income upgrades from
household-equal-split to per-person attribution (Phase 3 gauges read real work
histories), and hire dates are real calendar dates (the Person.birth_date machinery:
contracts don't need to know today's date, only their own age).

## Global Constraints

- The spot path is PRESERVED VERBATIM behind `labor_matching="spot"` (default).
  Every stage is flag-gated; flag-off runs stay bit-identical to the certified chain.
- New randomness uses dedicated substreams (seed + offset precedent); the main rng
  stream's consumption order is untouched.
- STOCK-FLOW HARD GATE from L0 on: E + U + S + JG + OLF == working-age persons every
  tick, and each stock's delta must equal its named flows (the labor A5; every future
  rare-event bug gets caught here first).
- Calendar discipline: every "annual" rate is applied as rate/365 with the existing
  date machinery — never scaled twice (the v13 365x coupon lesson). Anniversary
  events use real dates (leap-safe), never tick%365.
- Per-tick work is FLOW-sized (separations + hires + reviews, typically <2-3% of
  stock), never a full person scan inside the firm loop.
- Separation taxonomy is fixed at four classes and accounted separately:
  churn (exogenous quits + individual dismissals), demand-gap layoffs,
  bankruptcy mass layoffs, deaths.
- Calibration anchors: monthly churn 2-3%, monthly layoffs ~1.2%, u* 4-6%,
  vacancy duration ~30 days, negative Beveridge slope, Okun coefficient < 1.
- Layoff order is LIFO by hire date (flag for proportional-random) — recessions hit
  the young; the Phase 3 stratification gauges will see it.

---

## L0 — Labor Accounting (gauges + the hard gate, observation only)

- Person labor states E/U/S/JG/OLF as an explicit per-person field; the stock-flow
  identity gate; metrics: state stocks, hire/separation flows by class, vacancy stock,
  mean vacancy duration, tenure distribution, Beveridge pair (u, v).
- [x] Flag off => bit-identical; on => only observation columns move. (L0 freeze 08c3e67)
- [x] Identity gate holds through a 10y light run. (10y full-stack portrait, zero trips)

## L1 — Rosters & Separations (the foundation)

- Firms hold rosters of persons; hiring fills the gap toward N* (labor_demand_notional)
  from the searcher pool (instant fill in L1 — friction arrives in L2, so L1 isolates
  roster dynamics).
- Demand-gap layoffs WITH ADJUSTMENT DYNAMICS (this IS the old labor_adjust thread):
  fire-flow = lambda_fire x max(0, N - N* - hysteresis band), LIFO. Labor HOARDING
  emerges; technology-driven redundancy rides the same channel (a up => N* down);
  individual dismissals fold into the churn rate.
- Cash-crunch ladder, step 1+3: borrow (the existing credit-wage line is the first
  defense) -> forced LIFO layoffs to the affordable headcount. (Step 2 is L1b.)
- Firm exit = mass layoff into the pool; firm ENTRY hires through the same market
  (entry speed becomes friction-limited from L2 on — recalibrate entry_beta then).
- Deaths remove from rosters via the existing on_death fault-line hooks.
- [x] Bit-identical off; identity gate green; separation classes each pinned-tested.
- [x] Okun coefficient emerges (<1) and employment lags output; joint calibration of
      lambda_fire with the inventory buffer phi (two serial buffers -- watch
      overdamping: employment must still respond to recessions).
      ACCEPTED with numbers: mature-period Okun slope -0.20 (corr -0.78) on the slack
      rate -- hoarding attenuates, employment still responds. Calibration round
      (d110c9d): integer band floor + EMA firing target + lambda_fire 0.10->0.03;
      layoffs 9.9x -> 0.4-0.6x E/yr at 3k-person scale (small-firm integer
      granularity was the heat source). HONEST NULL: "employment lags output" is NOT
      visible at quarterly frequency (corr(dY_t,dE_t+1) ~ -0.1) -- the uncapped-JG
      buffer absorbs the lag; revisit if a JG cap ever becomes a policy experiment.

## L1b — Suspension (furlough; flag, default off)

Liquidity =/= insolvency at the match level (the employment LOLR). Cash-crunch step 2:
instead of firing, suspend LIFO-reverse up to timer T (~30-60 ticks): no pay, no
work, no output, NO DEBT (zero new liability class — the wage-arrears variant is
indefinitely deferred as accounting-cost-maximal). Suspended workers:
- are caught by the existing benefit/JG machinery (labor_sold = 0);
- stay in the searcher pool as RECALL UNEMPLOYMENT: accept an outside offer iff
  posted >= theta x suspended wage (`suspension_quit_discount`, ~0.9; duration decay
  optional later) — dying firms drain to competitors person by person, no bang;
- are recalled in place if cash recovers within T (no re-matching friction);
  auto-convert to layoff at timeout.
- [x] Pinned credit freeze: suspensions spike while layoffs stay low; recall on thaw;
      scarring visibly deeper with the flag OFF (the counterfactual is the point).
      (test_labor_suspension 5/5; probe: flag ON kills ALL cash layoffs, total layoff
      rate halves 9.89x->4.13x at probe scale; 831 susp / 454 recalls / 2 timeouts)
- [x] Kurzarbeit slot documented (state subsidy to suspended matches = fiscal
      transfer on the existing rails; a later policy handle).

## L2 — Matching Friction (u* is born)

- Hires flow through a matching process over (searchers, vacancies) — implementation
  in the native sampled-search grammar (SampledCompareMatch precedent), NOT a
  Walrasian clear; vacancies persist and age.
- JG semantics recast: JG workers REMAIN in the searcher pool (buffer stock must
  drain back to private employment) — otherwise JG absorbs u* and L2 is vacuous.
- [x] Frictional u* in the 4-6% band at calibration anchors; Beveridge curve traced
      across a demand cycle; vacancy duration ~30 days.
      (mature slack rate 6.0%; Beveridge cloud clearly downward-sloping in
      diagnostic_v16.png. CAVEAT: v-rate LEVELS run hot (0.3-0.5) -- firms' daily
      notional targets overstate true openings; a standing level-calibration item,
      the SHAPE is right. Under the uncapped JG, partition-U==0: slack=(U+JG)/force.)
- [x] CB φ_u and fiscal deficit_u re-validated against the now-meaningful u gap.
      (the 10y full-stack portrait runs the standard policy rule on the new
      dynamics: stable, no oscillation, slack settles at u*~6%; the
      unemployment_rate record's slack semantics are unchanged across eras.)

## L3 — Relationship Wages (the pass-through prize)

- Entry wage = firm posted wage at hire. Incumbents reprice ONLY at anniversary
  review (real hire dates; staggered smoothness for free; tenure = review count) with
  per-person DNWR. The free-hire drift delta applies to the POSTED wage only.
- Calendar-SYNCHRONIZED wage rounds (shunto-style, wage-price spiral experiments)
  are a future flag, not the default.
- [x] The v14 step-response rerun: productivity x1.5 now RAISES the real wage
      (the blocked-pass-through experiment is the acceptance test, inverted).
      **THE ARC'S PRIZE, WON: final-2y real incumbent wage ratio 1.490 vs 1.50
      theoretical full pass-through = 99.4%, against ~1.0 (all leaked) under the
      v14 spot market.** Pre-registered gate >=1.10: PASS. Accidental placebo:
      scaling only a/a_K (the C sector is Cobb-Douglas; its TFP is A) gives ratio
      0.999 -- the gain flows precisely through productivity->price->real wage.
      10y, 3k persons, L1+L1b+L2+L3+L3b. (diagnostic_v16.png, panel 6)
- [ ] Phase 2 x_t shows secular drift in a growth scenario; the transition channels
      fire without touching demographic code. (DEFERRED to v18: needs technology
      DRIFT, not a level step -- and x_t is stationary by design, so it needs
      re-derivation as deviation-from-trend under secular growth. v18 scope.)

## L3b — Job Ladder (on-the-job search = wage discipline)

- Employed workers sample k posted wages at a search rate; quit when posted >
  own wage x (1 + ladder premium). LOAD-BEARING for L3's health: without the quit
  threat, incumbent wages freeze below entrant wages forever.
- [x] Procyclical quits; incumbent wage distribution tracks posted wages with a lag;
      no permanent entrant/incumbent inversion.
      (corr(output growth, quit rate) = +0.42 mature; monthly corr(d posted,
      d incumbent) decays 0.67 -> 0.49 over 0-3m lags -- incumbents follow posted,
      slower. CAVEAT: E->E rate ~65%/yr vs real ~25%; ladder_intensity is a FREE
      dial, listed as a standing calibration item.)

## L4 — Person Efficiency (Phase 3.4 unlock)

- wage_i = w_firm x e_i with a person efficiency factor (the human-capital slot).
  Individual earnings gini becomes a real object; parent->child e transmission is
  Phase 3.4's coupling, NOT part of v16.
- [x] Off => e_i == 1 bit-identical; earnings dispersion decomposition
      (firm wage vs person efficiency) gauged.
      (300-tick persistent digest bit-identical vs pre-L4 HEAD; var(log e) 0.102 vs
      var(log w) 0.0008 among employed -- earnings dispersion is PERSON-driven;
      employed mean e = 1.02, mild positive selection: the low-e tail pools in
      JG/voluntary idle.)

## L5 — Participation Margin (reservation wage; policy lab)

- Voluntary exit to benefits: participate iff expected wage clears a reservation
  built on benefit_replacement (and JG wage). Deliberately LAST: it is a supply-side
  margin whose signal needs L3's stable wages, and whose categories (voluntary out vs
  frictional u) need L2 to exist at all.
- [x] Benefit-trap experiment: replacement rate sweep moves participation;
      JG wage-floor experiment: JG wage approaching market wage cannibalizes
      private employment (measurable, finally).
      (both live as tests: markup 0.8->2.0 grows the voluntarily-idle share of
      SUPPLY; jg_wage_ratio 0.5->1.1 halves private E -- and at 1.1 the dominant
      channel is jobs never FORMING (the search margin), not incumbent quits:
      welfare quits alone read ~0 because E~0. The finding is the measurement.)

---

## Interactions ledger

- **Demographics:** deaths are a separation class; person-level labor income feeds
  the claim sheets directly (Phase 3 gauges upgrade); leave-home/marriage move
  persons, not jobs — rosters follow persons, the fault-line sweeps must check
  roster membership on household events.
- **Phase 2/3:** L3 unlocks the growth->transition stimulus; LIFO layoffs shape the
  unemployment incidence the stratification gauges read.
- **Banking/credit:** credit-wage is the crunch ladder's first line; L1b mirrors
  LOLR semantics for matches; bank failures now transmit to visible layoffs.
- **Housing (v15):** rent burden and PTI read wage income — unchanged consumers of
  the same aggregates.
- **Firm demographics:** entry hiring becomes friction-limited (recalibrate
  entry_beta at L2); exit becomes a mass-layoff shock.

## Sequencing

After the v15 merge. One stage at a time, full acceptance before the next; L1b may
land with L1 or immediately after; L3b belongs to the L3 acceptance cycle.
