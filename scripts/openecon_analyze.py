#!/usr/bin/env python3
"""Cross-seed macro portrait from the openecon production runs.

Reads N seed directories (each holding economy_i.csv + world_series.csv +
summary.json as written by run_portrait) and emits a readable markdown portrait:
per-archetype headline metrics averaged across seeds (with cross-seed spread),
the identity-gate verdict per seed, and the cross-border picture (NFA, current
account, remittances, peg). Pure stdlib -- streams the wide CSVs, never loads
all 858 columns into memory at once.

Usage: python scripts/openecon_analyze.py DIR1 [DIR2 ...] [--out report.md]
"""
import csv, json, statistics, sys
from pathlib import Path

ARCHETYPES = ["China", "India", "USA", "Germany", "Gulf", "Hub"]

# economy_i.csv columns to summarize (exact names; guarded if absent).
# (label, column, kind) where kind in {level, rate, ratio}
ECON_COLS = [
    ("nominal GDP",        "nominal_gdp",                    "level"),
    ("GDP deflator",       "gdp_deflator",                   "ratio"),
    ("CPI (headline)",     "cpi_headline",                   "ratio"),
    ("CPI infl yoy",       "cpi_fixed_basket_inflation_yoy", "rate"),
    ("unemployment",       "person_unemployment_rate",       "rate"),
    ("JG employ rate",     "jg_employment_rate",             "rate"),
    ("policy rate",        "policy_rate",                    "rate"),
    ("avg wage",           "avg_wage",                       "level"),
    ("consumption",        "consumption_spending",           "level"),
    ("consumption gini",   "consumption_gini",               "ratio"),
    ("capital_output (raw)","capital_output",                "level"),
    ("adult pop",          "adult_population",               "level"),
    ("child pop",          "child_population",               "level"),
]
# world_series per-economy series (base name -> suffixed _0.._5), end-of-run value.
WORLD_BASES = [
    ("NFA",             "augmented_nfa"),
    ("current account", "current_account"),
    ("remittances",     "remittances"),
    ("factor inc unpaid","factor_income_unpaid_tick"),
]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def read_econ_series(path):
    """Return {column: [values...]} for the curated ECON_COLS present in the CSV."""
    with path.open(newline="") as fh:
        r = csv.DictReader(fh)
        cols = [c for _, c, _ in ECON_COLS if c in r.fieldnames]
        out = {c: [] for c in cols}
        for row in r:
            for c in cols:
                v = _f(row[c])
                if v is not None:
                    out[c].append(v)
    return out


def read_world_end(path):
    """Return (per_economy: {base: [v0..v5]}, scalars: {name: v}) at end of run."""
    last = None
    with path.open(newline="") as fh:
        r = csv.DictReader(fh)
        field = r.fieldnames
        for row in r:
            last = row
    if last is None:
        return {}, {}
    per = {}
    for label, base in WORLD_BASES:
        vals = []
        for i in range(len(ARCHETYPES)):
            col = f"{base}_{i}"
            vals.append(_f(last[col]) if col in last else None)
        if any(v is not None for v in vals):
            per[label] = vals
    scalars = {}
    for name in ("peg_intact",):
        if name in last:
            scalars[name] = last[name]
    # B1 lesson: SUM(NFA) is NOT zero by design -- its counterpart is the (unowned)
    # FX dealer's net worth. Surface both so the reader never mistakes the dealer's
    # cumulative revaluation losses for phantom private wealth.
    if "bop_numeraire" in last:
        scalars["dealer_net_worth"] = _f(last["bop_numeraire"])
    return per, scalars


def load_seed(d):
    d = Path(d)
    summ = json.loads((d / "summary.json").read_text()) if (d / "summary.json").exists() else {}
    econ = {}
    for i in range(len(ARCHETYPES)):
        p = d / f"economy_{i}.csv"
        if p.exists():
            econ[i] = read_econ_series(p)
    wper, wscal = ({}, {})
    if (d / "world_series.csv").exists():
        wper, wscal = read_world_end(d / "world_series.csv")
    return {"dir": d.name, "summary": summ, "econ": econ, "world_per": wper, "world_scal": wscal}


def fmt(v, kind):
    if v is None:
        return "  --"
    if kind == "rate":
        return f"{100*v:5.1f}%"
    if kind == "ratio":
        return f"{v:6.3f}"
    if abs(v) >= 1e4:
        return f"{v:8.3g}"
    return f"{v:8.1f}"


def mean_sd(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None, None
    m = statistics.mean(xs)
    s = statistics.pstdev(xs) if len(xs) > 1 else 0.0
    return m, s


def main():
    argv = sys.argv[1:]
    out_path = None
    if "--out" in argv:
        i = argv.index("--out")
        out_path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("usage: openecon_analyze.py DIR1 [DIR2 ...] [--out report.md]")
        return
    seeds = [load_seed(d) for d in args]
    L = []
    L.append(f"# Open-economy production portrait — {len(seeds)} seed(s)\n")

    # Identity verdicts
    L.append("## Identity gates\n")
    for s in seeds:
        ident = (s["summary"].get("identity") or {})
        v = ident.get("all_checks_passed")
        n = ident.get("n_checks", "?")
        failed = ident.get("failed_checks", [])
        badge = "PASS" if v else ("FAIL" if v is False else "?")
        L.append(f"- **{s['dir']}**: {badge} ({n} checks)"
                 + (f" — failed: {failed}" if failed else ""))
        meta = s["summary"]
        if meta.get("wall_seconds"):
            L.append(f"  - wall {meta['wall_seconds']:.0f}s, {meta.get('ticks','?')} ticks, "
                     f"{meta.get('ticks_per_second','?')} t/s")
    L.append("")

    # Per-archetype headline: end-of-run value per metric, mean±sd across seeds
    L.append("## Per-archetype headline (end of run, mean across seeds; ±sd if >1 seed)\n")
    for i, name in enumerate(ARCHETYPES):
        L.append(f"### {i}. {name}\n")
        L.append("| metric | value |")
        L.append("|---|---|")
        for label, col, kind in ECON_COLS:
            ends = []
            for s in seeds:
                ser = s["econ"].get(i, {}).get(col)
                if ser:
                    ends.append(ser[-1])
            m, sd = mean_sd(ends)
            cell = fmt(m, kind)
            if m is not None and len(ends) > 1:
                cell += f"  (±{fmt(sd, kind).strip()})"
            L.append(f"| {label} | {cell} |")
        # summary.json end-state extras
        pe = None
        for s in seeds:
            for row in (s["summary"].get("per_economy") or []):
                if row.get("economy") == i:
                    pe = row
        if pe:
            L.append(f"| real GDP (summary) | {fmt(pe.get('real_gdp'),'level')} |")
            L.append(f"| K/annual GDP | {fmt(pe.get('K_over_annual_gdp'),'ratio')} |")
        L.append("")

    # Cross-border
    L.append("## Cross-border (end of run)\n")
    L.append("| economy | " + " | ".join(l for l, _ in WORLD_BASES) + " |")
    L.append("|" + "---|" * (len(WORLD_BASES) + 1))
    for i, name in enumerate(ARCHETYPES):
        cells = []
        for label, _ in WORLD_BASES:
            vals = [s["world_per"].get(label, [None]*6)[i] for s in seeds]
            m, _sd = mean_sd(vals)
            cells.append(fmt(m, "level"))
        L.append(f"| {i} {name} | " + " | ".join(cells) + " |")
    L.append("")
    pegs = [s["world_scal"].get("peg_intact") for s in seeds]
    if any(p is not None for p in pegs):
        L.append(f"- peg_intact (China→USD) per seed: {pegs}\n")
    dnw = [s["world_scal"].get("dealer_net_worth") for s in seeds]
    if any(v is not None for v in dnw):
        L.append("- FX-dealer net worth per seed (the counterpart of SUM(NFA); "
                 "large negative = the unowned dealer subsidising private external wealth): "
                 + ", ".join("--" if v is None else f"{v:+.3g}" for v in dnw) + "\n")

    text = "\n".join(L)
    if out_path:
        Path(out_path).write_text(text)
        print(f"wrote {out_path} ({len(text)} bytes)")
    print(text)


if __name__ == "__main__":
    main()
