# V22 Migration & Remittances Plan — Layer A's people flow + the full current account

> **STATUS: IMPLEMENTED — v22.0–v22.1 built/tested/committed on `feat/migration-v22`
> (forked from v21@3b3ef29).** v22 adds Layer A's people flow + remittances, completing the
> current account. Reuses the v20/v21 machinery whole. 4 v22 tests green (migration off ⇒
> v21 exactly); diagnostic_v221.
>
> **What landed (v22.1, `world/migration.py`, commit e4ec57b):** workers migrate toward
> higher REAL wages (a wage-gap-driven, bounded residency stock); migrants remit a share
> home via a conserving dealer-routed transfer (host households → dealer → origin
> households). The full current account = trade + factor income + remittances is gauged.
> **Finding:** the low-wage economy is the net labor EXPORTER and remittance RECEIVER, and
> remittances lift its current account from deficit to surplus (the Philippines/Bangladesh
> pattern) — and are the v18 deprivation escape valve, now present.
>
> **Honest scope:** v22.1 is the FINANCIAL side (remittances + current account) with the
> migrant stock a wage-driven gauge; the REAL labor-force reallocation (v22.2 — actually
> shrinking the origin's workforce / growing the host's, driving wage convergence) touches
> each economy's labor internals and is the deeper, still-open lift.
>
> ### Findings forced by the accounting fix (the identity audit paid for itself)
>
> Making factor income a REAL money flow and the peg's reserves a REAL account broke two
> migration tests — and the breakage exposed that the ORIGINAL demo rested on a false premise:
>
> 1. **The "poor vs rich" pair was a fiction.** It was built on a productivity gap
>    (`a`=0.7 vs 1.3), but this model is **DEMAND-CONSTRAINED**: doubling `a` moved neither
>    output (206 vs 202) nor nominal wages (1.317 vs 1.327) nor employment (both full) — the
>    same demand simply needs fewer workers. **There was no wage gap at all**, so the
>    migration direction was decided by noise and flipped whenever anything perturbed it.
>    (This is v20 finding #2 resurfacing, and it also means the v20.3 `CountryProfile`
>    productivity axis is largely inert — the wage/price anchors are the live lever.)
> 2. **Two mechanism bugs the fiction had hidden:**
>    (a) migration keyed off the INSTANTANEOUS real wage, so on a noisy series BOTH economies
>    momentarily out-earned each other and each started "sending" people — now smoothed (an
>    EMA: nobody emigrates on a one-tick flicker);
>    (b) it used wage/own-price-index, but **remittances raise the origin's price level**,
>    depressing its measured real wage and pulling in MORE migrants — a perverse loop that a
>    quota (cutting remittances) would flip outright. Now it uses the **migrant's actual
>    calculus**: the foreign wage converted home at the exchange rate vs the home wage.
>
> With a genuine WAGE gap (via `w_firm0`/`p_firm0`: realized wages 0.92 vs 1.80) the flow is
> one-directional and robust across every policy: open ⇒ 50 migrants, quota 3% ⇒ exactly 6,
> remittance tax ⇒ unchanged (it does not alter the migration incentive).

## 0. What crosses now: people

The v20 seed was "an agent wants a foreign good"; v22's is "**a worker wants a foreign
wage**." A worker migrates from a low-wage to a high-wage economy (residency changes), earns
in the host, and **remits** a share home. Remittances are a cross-border TRANSFER — money
one way, no goods or asset claim the other (unlike trade or capital) — the current account's
secondary-income line. This is also the deprivation escape valve v18 flagged as missing in a
closed economy: labor can now leave a poor economy for a richer one.

## 1. Objects

1. **Migrant stock.** `S_i` = accumulated net emigrants from economy i working abroad,
   driven by the real wage differential (migrate toward higher wages), bounded by a share
   of the population (friction: not everyone moves).
2. **Remittances.** Migrants remit `share × (migrant earnings)` home: a conserving
   cross-border transfer HOST → ORIGIN, routed through the dealer (host-currency collected
   from host households — the migrants are host residents — converted, distributed to
   origin households). The origin's secondary-income credit.
3. **The full current account.** `CA_i = trade_balance_i + factor_income_i + remittances_i`.
   Remittances make a labor-exporting economy's CA systematically stronger than its trade
   balance alone (the Philippines/Bangladesh pattern).

## 2. Load-bearing lever

**Migration friction / labor mobility** (how freely labor chases the wage gap): high ⇒
large migrant stocks, big remittance flows, strong wage convergence; low ⇒ near-immobile
labor. The people-flow analog of v20 trade friction and v21 capital mobility.

## 3. Staging

- **v22.0** — this plan.
- **v22.1** — migrant stock (wage-driven) + remittance transfer (conserving, dealer-routed)
  + the full current-account gauge. Gate: migration off ⇒ v21 exactly; conservation; the
  labor-exporting economy's CA > its trade balance (remittance wedge).
- **v22.1-policy (DONE)** — migration POLICY (run-time government levers, distinct from the
  structural knobs): the **immigration cap/quota** (a host admits ≤ `cap × pop`; binding ⇒
  the flow is throttled and wage convergence is blocked) and the **remittance tax** (the
  origin skims inbound remittances to its fiscal account). First tools of the border-
  governance layer (§12 Layer C), the migration analog of v20 tariffs / v21 capital controls.
- **v22.2 (optional)** — the labor-supply reallocation (the origin loses workers → tighter
  labor market / higher wages at home → convergence; the host gains labor). The real-side
  counterpart to the financial remittance flow.

## 4. Honest scope

v22.1 is the FINANCIAL side (remittances + current account) with the migrant stock as a
wage-driven gauge; the real labor-force reallocation (actually moving workers between the
economies' labor markets) is v22.2 — it touches each economy's labor/production internals
and is the deeper lift. Determinism/bit-identity inherited: migration off ⇒ v21 byte-identical.
