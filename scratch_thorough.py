"""THOROUGH v8.5-vs-v9 diagnosis (one batch, 5 seeds, proper scale, full 4000 ticks).
Answers: (A) the T3/T6 causal chain the government breaks; (B) better-or-worse across every dimension."""
import sys
from multiprocessing import Pool
import numpy as np
from config import Config
from economy import Economy

SEEDS = [0, 1, 2, 3, 4]
NC, NK, NH, TICKS, BURN = 200, 100, 2000, 4000, 1000


def cyclical(x, w=201):
    x = np.asarray(x, float)
    trend = np.convolve(x, np.ones(w) / w, mode="same")
    return (x - trend)[w:-w]


def comov(series, y):  # cyclical comovement of `series` with output `y`
    sc, yc = cyclical(series), cyclical(y)
    return float(np.corrcoef(sc, yc)[0, 1]) if sc.std() > 1e-12 and yc.std() > 1e-12 else 0.0


def analyze(args):
    factory, seed = args
    rec = Economy(getattr(Config, factory)(n_firms_c=NC, n_firms_k=NK, n_households=NH,
                                            n_ticks=TICKS, seed=seed)).run()
    def col(k): return np.array([r.get(k, 0.0) for r in rec], float)
    def late(k, a=3500, b=4000): return col(k)[a:b].mean()
    def win(k): return [col(k)[300:800].mean(), col(k)[1800:2200].mean(), col(k)[3500:4000].mean()]
    u = col("unemployment_rate")[BURN:]
    y = col("real_output")[BURN:]
    tot = col("total_credit")[BURN:]
    hh = col("household_debt_total")[BURN:]
    mg = col("household_margin_debt")[BURN:]
    firm_credit = tot - hh - mg
    g = np.diff(np.log(np.clip(y, 1e-9, None)))
    return dict(
        # --- Part B: welfare/stability battery ---
        u_mean=u.mean(), u_sd=u.std(), u_win=win("unemployment_rate"),
        u_gt50=float((u > 0.5).mean()), u_max=float(u.max()),
        y_mean=y.mean(), y_cv=y.std() / max(1e-9, y.mean()),
        rcons_mean=col("real_consumption")[BURN:].mean(),
        price_early=col("price_index")[300:800].mean(), price_late=late("price_index"),
        infl_mean=col("inflation")[BURN:].mean(),
        income_gini=late("income_gini"), wealth_gini=late("hh_wealth_gini_incl_equity"),
        cons_gini=late("consumption_gini"), hh_money_share=late("hh_money_share"),
        growth_kurt=float(((g - g.mean())**4).mean() / max(1e-12, g.std()**4) - 3.0),
        # --- Part A: firm structure (T6) ---
        firms_win=win("n_firms_producing"), births=col("births")[BURN:].mean(),
        deaths=col("deaths")[BURN:].mean(), fsize_gini=late("firm_size_gini_output"),
        pareto=late("firm_size_pareto_slope"),
        # --- Part A: credit cycle (T3/T7) ---
        credit_comov=comov(tot, y), firm_credit_comov=comov(firm_credit, y),
        hh_debt_comov=comov(hh, y), margin_comov=comov(mg, y),
        inv_comov=comov(col("investment_spending")[BURN:], y),
        cons_comov=comov(col("consumption_spending")[BURN:], y),
        lev_comov=comov(col("aggregate_leverage")[BURN:], y),
    )


def agg(rows, k):
    v = [r[k] for r in rows]
    if isinstance(v[0], list):
        return np.array(v).mean(axis=0)
    return float(np.mean(v)), float(np.std(v))


if __name__ == "__main__":
    with Pool(min(2 * len(SEEDS), 10)) as p:
        out = p.map(analyze, [(f, s) for f in ("v85", "v9") for s in SEEDS])
    R = {"v85": out[:len(SEEDS)], "v9": out[len(SEEDS):]}
    def show(k, fmt="{:.3f}", label=None):
        a, b = R["v85"], R["v9"]
        if isinstance(a[0][k], list):
            va, vb = agg(a, k), agg(b, k)
            print(f"  {label or k:22s} v85={[round(x,2) for x in va]}   v9={[round(x,2) for x in vb]}")
        else:
            (ma, sa), (mb, sb) = agg(a, k), agg(b, k)
            print(f"  {label or k:22s} v85={fmt.format(ma)}±{fmt.format(sa)}   v9={fmt.format(mb)}±{fmt.format(sb)}")
    print("=== PART B: welfare & stability (v8.5 vs v9, 5 seeds) ===")
    for k, lab in [("u_mean","unemployment mean"),("u_sd","unemployment sd"),("u_gt50","frac u>0.5"),
                   ("u_win","u early/mid/late"),("y_mean","real output"),("y_cv","output CV"),
                   ("rcons_mean","real consumption"),("price_late","price index (late)"),
                   ("infl_mean","inflation/tick"),("income_gini","income Gini"),("wealth_gini","wealth Gini"),
                   ("cons_gini","consumption Gini"),("hh_money_share","hh money share"),("growth_kurt","growth kurtosis")]:
        show(k, label=lab)
    print("\n=== PART A1: firm structure / T6 ===")
    for k, lab in [("firms_win","active firms e/m/l"),("births","births/tick"),("deaths","deaths/tick"),
                   ("fsize_gini","firm-size Gini"),("pareto","Pareto slope (Zipf=-1)")]:
        show(k, label=lab)
    print("\n=== PART A2: credit cycle / T3,T7 (cyclical comovement with output) ===")
    for k, lab in [("credit_comov","total credit"),("firm_credit_comov","firm credit"),
                   ("hh_debt_comov","hh consumption debt"),("margin_comov","margin debt"),
                   ("inv_comov","investment"),("cons_comov","consumption"),("lev_comov","leverage")]:
        show(k, "{:+.2f}", label=lab)
