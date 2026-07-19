# Dealer bleed: design note (campaign finding #1)

**Status**: DRAFT for user review. No engine change yet.

## 1. The evidence

All 9 coupled campaign worlds ended with ΣNFA > 0 (0.87M aging ... 7.4M energy
crisis); by the B1 identity (ΣNFA + dealer_NW ≡ 0, held EXACTLY in every run)
the FX dealer's net worth is monotonically negative and unbounded. Intensity
ranks with FINANCIAL/settlement flow volume (banking crisis 5.4M >> trade-war
2.9M >> aging 0.87M), not trade volume.

## 2. Why the dealer bleeds (mechanism)

The dealer is a passthrough market-maker: it quotes the current rate vector,
absorbs any one-sided flow into inventory, and re-prices via the grope signal.
Three structural losses, none compensated:

1. **No spread**: every conversion is executed at mid. Real dealers earn
   bid-ask on volume; ours earns exactly zero on any round trip.
2. **Adverse-selection drift**: persistent one-way flows (remittances,
   factor-income settlement, reserve swaps, crisis flight) hand the dealer
   inventory in depreciating currencies and drain it in appreciating ones --
   it is short every trend, always.
3. **No resolution**: losses accumulate forever; nothing recapitalizes,
   mutualizes, or constrains the position.

## 3. Design options

| option | mechanism | realism | scope |
|---|---|---|---|
| A. bid-ask spread | dealer executes at mid*(1±s/2); spread revenue accrues to dealer equity | high (how real FX desks live) | small: one knob `fx_spread`, applied at the conversion seam; s=0 bit-identical |
| B. inventory-linked spread | s widens with |inventory| (stressed dealer quotes worse) | high | medium: couples to grope signal |
| C. clearing-union mutualization | member CBs periodically settle the dealer's realized loss pro-rata (a real cost to fiscal/CB accounts) | medium (BIS-style) | medium: new conserving transfer, makes the bleed VISIBLE as national cost instead of hidden |
| D. position limits | dealer refuses conversion beyond an inventory cap (flows queue) | medium | large: introduces rationing into every cross-border phase |

## 4. Recommendation

**A first (flagged), C second, B later, D avoid at P0.**
- A stops the *structural* subsidy: with volume-proportional revenue the dealer
  is compensated for making markets; calibrate s so long-run dealer NW drifts
  near zero in the portrait worlds (sweepable).
- C makes any residual loss an HONEST fiscal cost of the exchange-rate system
  rather than a leak: realized dealer loss settled annually against member
  fiscal accounts pro-rata by conversion volume. Conserving, visible in gauges.
- B is a refinement of A once A's level effects are understood.
- D changes every trade/remittance phase's semantics -- too invasive for a fix.

## 5. Acceptance

- flags off: digest 0fb412c8 exact.
- spread s>0: dealer NW no longer monotone; portrait rerun of X2/X4 shows
  bounded dealer NW; ΣNFA + dealer_NW identity still EXACT.
- C on: annual settlement events appear in fiscal accounts; world conservation
  holds to ledger tolerance.
