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
- **v22.2 (optional)** — the labor-supply reallocation (the origin loses workers → tighter
  labor market / higher wages at home → convergence; the host gains labor). The real-side
  counterpart to the financial remittance flow.

## 4. Honest scope

v22.1 is the FINANCIAL side (remittances + current account) with the migrant stock as a
wage-driven gauge; the real labor-force reallocation (actually moving workers between the
economies' labor markets) is v22.2 — it touches each economy's labor/production internals
and is the deeper lift. Determinism/bit-identity inherited: migration off ⇒ v21 byte-identical.
