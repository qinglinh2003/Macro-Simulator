# Implementation plan — v5 (diseconomies of scale) + the competition phase diagram

> **⚠️ FALSIFIED PRIOR — kept intact on purpose (see DESIGNDOC §14).** This plan pre-registered the
> hypothesis that competition needs transparency **and** diseconomies *together* (§1–§2 below), and
> that a diseconomy at m=1 is inert. The phase diagram showed the **reverse**: competition emerges at
> **low** transparency (m=1) + diseconomy + entry/exit, and m≥2 winner-take-all is *antagonistic*. Two
> corrections the data forced: the diseconomy scales with **output**, not employment N (the winner is
> capital-intensive, N≈1.8); and `Config.v5()` ships the **m=1** competitive cell, not m≥2. The value
> of this document now is as the falsified prior against which §14's surprise is legible.

**The deliverable is not "a diseconomy parameter" — it is a phase diagram of competition.** v5
adds a Lucas span-of-control coordination cost, but its point is to complete a picture: every
market-structure mechanism we tried *alone* failed (transparency ⇒ concentration; entry/exit ⇒
revolving door; diseconomies alone ⇒ inert), because **competition is a multi-condition
conjunction**. v5 lets us map where those conditions jointly produce competition.

---

## 0. The mechanism (small, core-touching)

A coordination cost rising with employment N enters the **unit cost → price** (B3):
$$uc = uc_{\text{labor}}\,\big(1 + \texttt{dis\_slope}\cdot N\big),\qquad N = \text{planned employment (span of control)}.$$
Bigger firms (more workers) post higher prices. This is Lucas span-of-control: a micro cost slope
is fiat; optimal size / concentration / firm count **emerge** (§0-ii). `dis_slope=0` ⇒ v1–v4
unchanged (uc identical → bit-identical regression). It touches the *core* cost structure, so
old phenomena (drain, cycles) must be re-read under the new costs.

## 1. The load-bearing coupling — diseconomies need price-sensitive buyers (m≥2)

The diseconomy's **only** feedback path is: high cost → high price → **lost demand** → firm
shrinks. "Lost demand" physically requires buyers who compare prices. So with m=1 (blind matching)
a big firm's high price is *not punished* → it keeps its share → keeps growing → the diseconomy is
an **inert parameter**. Therefore **v5 ships diseconomies and search_m≥2 together** (`Config.v5()`
sets both). The single most common trap: "I added a diseconomy and nothing changed" — because m=1.
The negative feedback runs on **two** channels, both requiring m≥2: pricing (this tick) and the
accelerator (high price → fewer sales → lower y^e → lower K* → stops accumulating).

## 2. The competition phase diagram (the deliverable)

The conjunction thesis, made empirical. Sweep the two structural dials with firm-dynamics ON:
- **m** (information transparency, §5/§11.6) × **dis_slope** (diseconomies, §14).
Measure, at the tail: firm-size **Gini** (concentration), **avg markup** (monopoly profit),
**# producing firms**. The predicted structure (each mechanism necessary-not-sufficient):

| | m=1 (blind) | m≥2 (compare) |
|---|---|---|
| **dis_slope=0** | slow monopoly (capital advantage) | fast monopoly (cheapest=biggest wins, §11.6) |
| **dis_slope>0** | still monopoly (high price unpunished) | **competition / oligopoly** ✓ |

Only the bottom-right cell (transparency AND diseconomies together) should show competition
(Gini falls to an oligopoly level, markup drops, and — the real test — **Gini does not re-climb**
the way it did under entry/exit alone in v4). Produce a heatmap (Gini, markup, #firms over the
m × dis_slope grid) as the headline artifact.

## 3. The dimensionality control — is competition a 2-D or 3-D conjunction?

Firm entry/exit (v4) is a third market-structure mechanism, also necessary-not-sufficient alone
(revolving door). At a (m, dis_slope) cell that shows competition, **toggle firm_dynamics OFF** and
see whether competition survives:
- survives ⇒ competition is a **2-D conjunction** (transparency + diseconomies suffice; entry/exit
  only cleared zombies).
- collapses back to monopoly ⇒ competition is a **3-D conjunction** — entry/exit is independently
  necessary, empirically confirming the three classic perfect-competition pillars (no increasing
  returns, full information, free entry/exit) as *independent* necessary conditions in our model.
Either outcome is clean knowledge and is a headline result.

## 4. Module-by-module (small)

| module | change |
|---|---|
| `config.py` | `dis_slope: float = 0.0` (FREE, core v5 dial); `Config.v5()` = v4 + `search_m=5` + `dis_slope=0.02` (the two delivered together). |
| `agents.py` | `Firm.dis_slope` per-agent field, set from cfg in all factories. |
| `behavior.py` | `unit_cost` multiplies base by `(1 + dis_slope·N)`. Only change. |
| tests | v1–v4 regression (dis_slope=0 bit-identical); a v5 test: with (m≥2, dis_slope>0) Gini and markup are materially below the (m≥2, dis_slope=0) monopoly baseline. |
| experiment | `phase diagram` script: m × dis_slope heatmaps + the firm_dynamics-off control. |

## 5. Acceptance

1. **Regression** — v1–v4 bit-identical at `dis_slope=0`.
2. **The coupling holds** — at m=1, varying dis_slope barely moves concentration (inert); at m≥2,
   raising dis_slope materially lowers Gini and markup. (This *is* the conjunction, in data.)
3. **The phase diagram** — a clean map with a competition region only where m≥2 AND dis_slope>0;
   and the firm_dynamics-off control resolving the 2-D vs 3-D question.
4. A5 / conservation untouched (v5 is a pricing change, no money-flow change).

Expected caveat: at large dis_slope firms may be pinned small (low output) — a too-strong
diseconomy over-corrects. The interesting regime is the intermediate slope where oligopoly (not
monopoly, not atomistic collapse) emerges. Calibrate the slope to firm employment N so the overhead
spans ~0 to ~2×.
