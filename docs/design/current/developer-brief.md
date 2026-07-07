# Developer Brief

This is the first document to read before changing the simulator.

## Current Frontier

The latest documented frontier is **v12.4**: the securities arc is closed.
The model has an un-consolidated Treasury/Central Bank structure, bonds with
face/book/market values, bank securities, variable reserve supply, OMO/QE, and
LoLR. The clean verified win is that **OMO can finally make reserves scarce
enough for the interbank layer to bind**, while QE can re-flood reserves and
make that layer latent again.

The next major development direction is **v13: search-and-matching labor**.
The current labor market clears too quickly and has no natural-rate floor:
when demand is strong enough, unemployment can fall to roughly zero. That is
correct for a frictionless labor market, but not realistic.

## Non-Negotiable Invariants

1. **Accounting first.** Every financial flow must be represented by an explicit
   ledger primitive or an equivalent paired accounting operation.
2. **A5 is the monetary hard gate.** With credit and bank securities live, the
   core private-money invariant is `sum(deposits) - sum(loans) - bank_securities = M`.
3. **Reserves are a separate overlay.** Reserve conservation is `sum(reserves) = reserve_M`;
   OMO/QE changes `reserve_M` through explicit reserve issue/retire primitives.
4. **Bonds have three values.** Face is for bond identity, book/cost is for
   accounting invariants, market value is for wealth and economic capital.
5. **Feature flags must preserve baselines.** A new mechanism should be off by
   default or have an explicit frontier config; old configs should remain
   bit-identical unless the change is a deliberate correctness fix.

## Current Structural Gaps

- **Labor:** no job spells, search friction, skill/job heterogeneity, bargaining,
  vacancies, or matching persistence. This is the largest realism gap.
- **Bank formation:** de-novo bank entry still depends too much on one household's
  liquid wealth. Joint founding, IPO-style capitalization, bridge banks, and
  recapitalization remain future work.
- **Open economy:** no foreign sector, exchange rate, trade, capital flows, or
  foreign labor. The model is still a closed economy.
- **Goods structure:** production and consumption are still abstract relative to
  a real sectoral economy; energy, durables, necessities, and luxury goods are
  not first-class categories.
- **Policy realism:** the fiscal/monetary stack is useful but still simplified:
  supply-side public investment works only strongly at above-anchor parameters,
  and monetary policy is constrained by fiscal dominance plus the job guarantee.

## How To Use The Long History

The long history is evidence, not the day-to-day entry point. Use it when you
need to understand why a design exists, why a tempting shortcut failed, or what
a diagnostic result means.

- Banking/securities questions: [`../history/arcs/09-banking-securities.md`](../history/arcs/09-banking-securities.md)
- Government/labor/central bank questions: [`../history/arcs/08-government-labor-monetary.md`](../history/arcs/08-government-labor-monetary.md)
- Firm/competition questions: [`../history/arcs/06-firms-competition-equity.md`](../history/arcs/06-firms-competition-equity.md)
- Household/portfolio questions: [`../history/arcs/07-households-portfolios-equity.md`](../history/arcs/07-households-portfolios-equity.md)
- Kernel/v2/v3 questions: [`../history/arcs/05-kernel-findings-v2-v3.md`](../history/arcs/05-kernel-findings-v2-v3.md)
