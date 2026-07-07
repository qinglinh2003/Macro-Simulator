# PLAN v12.4 — the CB's quantity tools: OMO / QE / LoLR (activate the latent money market; unblock the bank drain)

Closes the securities arc (v12.0–v12.4). v12.3 built the bank balance sheet + duration/SVB **conservation-verified
but gated OFF** (`bank_bond_appetite=0`) because the live bank drain collapses the thin-equity sector with no Lender
of Last Resort. v12.4 gives the central bank the power to **create and destroy base money (reserves)** and uses it
for three policy operations. Every lever off-default ⇒ **bit-identical** to v12.3; `bonds=False` ⇒ v11.5.

---

## 0. The one architectural change: the reserve total becomes VARIABLE

Until now `Σ reserves = _reserve_M` is a FIXED constant (base money is conserved). The un-consolidated CB is the
**source and sink of base money** — OMO/QE/LoLR create or destroy reserves. So `_reserve_M` becomes a *variable*
that the CB moves, and the gate `Σ reserves = _reserve_M` **stays exact BY CONSTRUCTION** (every issue/retire updates
both sides by the same amount). The deposit ledger (`ΣD − ΣL − _bank_securities = M`) is **untouched** — reserves
are a separate overlay, so creating reserves never moves deposits. Two new ledger primitives:

- `issue_reserves(node, amount)`  → `_reserves[node] += amount; _reserve_M += amount`   (base money CREATED)
- `retire_reserves(node, amount)` → `_reserves[node] -= amount; _reserve_M -= amount`   (base money DESTROYED)

The CB's balance sheet becomes real: **assets** = `cb_bonds` (bonds it holds) + `cb_claim_on_tsy`; **liabilities** =
reserves it has issued + TGA. The identity `cb_bonds + cb_claim_on_tsy = (reserves issued) + TGA + cb_equity` is the
CB balance-sheet gate (§39 (2), finally non-trivial).

---

## 1. The three operations

### OMO — open-market operations (drain/inject reserves → the interbank keystone)
The interbank market (§37) ALREADY binds when a bank's reserves go negative (`_phase_interbank`) — it is latent
only because reserves are ample. OMO makes them scarce: the CB **sells bonds to banks** (bank reserves ↓ = drain)
or **buys bonds from banks** (reserves ↑ = inject). A drain below the payment-flow buffer ⇒ banks go into deficit ⇒
**the interbank market ACTIVATES** (`peak_intraday_overdraft`, `interbank_volume` turn positive — the pre-registered
signal). Modelled as a policy targeting a reserve level `omo_reserve_target` (or draining a `omo_drain_frac` per
tick): `retire_reserves(bank, x)` + `cb_bonds += x` (asset swap: the CB holds the bond, the bank holds fewer
reserves). QE is the mirror (`issue_reserves` + `cb_bonds` bought back) ⇒ reserves re-flood ⇒ interbank
**re-latents** — the post-2008 story.

### LoLR — lender of last resort (runs stop cascading)
In `_phase_bank_runs`, a bank whose OWN reserves are exhausted currently SUSPENDS (illiquidity failure). With LoLR
on, the CB lends it emergency reserves — `issue_reserves(bank, needed)` as a collateralised advance (a temporary CB
claim) — so it **honours the withdrawals and does NOT suspend**. This breaks the liquidity-cascade half of the v12.3
collapse. (LoLR is LIQUIDITY, not solvency: a bank that is genuinely INSOLVENT — economic_capital < 0 from SVB MTM
losses — still fails, but it fails ALONE instead of taking the sector with it.)

### Bank capital floor (the solvency half)
v12.3 showed banks are thinly capitalised (equity ~tens vs a bond book of thousands) ⇒ any MTM loss wipes them. A
regulatory floor: a bank may only put reserves into bonds up to a duration/exposure limit tied to its economic
capital (`bank_bond_duration_limit`), so a rate hike can't wipe the whole book. With LoLR + this floor, turning
`bank_bond_appetite > 0` ON should let the sector SURVIVE (a few SVB-style failures, not universal collapse) while
the strong drain sterilises reserves and the interbank market binds.

---

## 2. Config levers (all off-default ⇒ bit-identical to v12.3)
`omo` (bool), `omo_reserve_target` or `omo_drain_frac`, `lolr` (bool), `bank_bond_duration_limit` (cap bond book at
k·economic_capital). A `Config.v124()` = v123 + `omo`, `lolr`, a survivable `bank_bond_appetite`, and the floor.

## 3. Gates (each stage)
- **Off ⇒ bit-identical**: every new lever off ⇒ v12.3; `bonds=False` ⇒ v11.5.
- **Reserve conservation**: `Σ reserves = _reserve_M` every tick (now with a *moving* `_reserve_M`), ~1e-6.
- **Deposit A5** `ΣD − ΣL − _bank_securities = M` untouched by reserve ops.
- **CB balance sheet**: `cb_bonds + cb_claim_on_tsy = reserves_issued + TGA + cb_equity`.
- **PRE-REGISTERED (OMO activation)**: draining reserves below the buffer ⇒ `peak_intraday_overdraft > 0` AND
  `interbank_volume > 0` (the latent §37 keystone finally binds); QE ⇒ they fall back to 0 (re-latent).
- **PRE-REGISTERED (LoLR)**: with `bank_bond_appetite > 0` + `lolr` on, the sector does NOT collapse to 0 (vs the
  v12.3 universal collapse) — failures are LOCAL (SVB-style), banks_alive stays > 0, u bounded.

## 4. Build order (each gated)
1. Ledger `issue_reserves`/`retire_reserves` + CB balance-sheet state + gate → conservation gate.
2. OMO (drain/inject to target) → pre-registered activation (interbank binds; QE re-latents).
3. LoLR (emergency reserves in `_phase_bank_runs`) → run-suspension prevented.
4. Capital/duration floor + turn `bank_bond_appetite > 0` under LoLR → pre-registered survival + strong drain.
Then metrics (`cb_bonds`, `reserves_issued`, `lolr_advances`, re-surface interbank/overdraft), tests,
`diagnostic_v124.png`, DESIGNDOC §39.6, changelog, memory, full regression.
