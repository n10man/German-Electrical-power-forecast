"""I1: interval recalibration candidates, VALIDATION YEAR ONLY (rules: results/EXPERIMENTS.md entry I1, written before this was run).
  python scripts/run_interval_methods.py
Uses the locked models in models_future/ (never modified) to get raw quantiles on 2024-10-25..2025-10-24, then replays a rolling-origin
protocol: burn-in 13 weeks, scored 274 days, a score of hour t' is usable for hour t only if t' <= t - 24k.
Writes results/interval_val_cells.csv, results/interval_val_summary.csv, results/interval_selection.json. The sealed test file is never read."""
import sys, json, bisect, math
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from pathlib import Path
import numpy as np, pandas as pd, lightgbm as lgb
from gepf.data import ZONES
from gepf.quant import QS, BANDS, cqr_offset
from gepf import horizon as H

MODELS = Path("models_future"); BURN = 91 * 24
ROLL_N = [4, 8, 13]; GAMMAS = [0.005, 0.01, 0.02]
CANDIDATES = ["static"] + [f"rolling_{n}w" for n in ROLL_N] + [f"aci_g{g}" for g in GAMMAS]

def raw_validation(zone, k, load, cfg_info, arch, val0, test0, R):
    X, f = R.frame_for(zone, load, k, cfg_info["config"], arch)
    X = X.dropna(subset=[f"lag_{H.shift_hours(k)}h", f"lag_{H.week_lag(k)}h", "load_mw"] + [c for c in f if c.startswith("w_")])
    v = X[(X.index >= val0) & (X.index < test0)]
    P = np.sort(np.column_stack([lgb.Booster(model_file=str(MODELS / f"{zone}_k{k}_q{q}.txt")).predict(v[f]) for q in QS]), axis=1)
    full = pd.date_range(val0, test0 - pd.Timedelta(hours=1), freq="h", tz="UTC")
    out = pd.DataFrame(P, index=v.index, columns=[f"q{a}" for a in QS]).reindex(full); out["y"] = v.load_mw.reindex(full); return out

def scores_of(d, band):
    la, ha, nom = BANDS[band]; lo, hi, y = d[f"q{la}"].values, d[f"q{ha}"].values, d.y.values
    return lo, hi, y, np.maximum(lo - y, y - hi)

def _off(scores, nom):
    sc = scores[~np.isnan(scores)]; n = len(sc)
    if n == 0: return 0.0
    q = min(1.0, math.ceil((n + 1) * nom) / n); return float(np.quantile(sc, q, method="higher"))

def calib_static(s, k, nom): return np.full(len(s), _off(s[:BURN], nom))

def calib_rolling(s, k, nom, weeks):
    d = 24 * k; c = np.zeros(len(s))
    for day0 in range(BURN, len(s), 24):
        hi_i = day0 - d; lo_i = hi_i - weeks * 168       # scores known before the day starts (the earliest origin of its hours)
        c[day0: day0 + 24] = _off(s[max(0, lo_i): hi_i + 1], nom)
    return c

def calib_aci(s, k, nom, gamma, lo, hi, y):
    d = 24 * k; alpha = 1 - nom; n = len(s); c = np.zeros(n); err = np.zeros(n); cum = np.zeros(n + 1)     # cum[j+1] = sum_{j'<=j} (alpha - err_j')
    srt = sorted(x for x in s[:BURN] if not np.isnan(x)); added = BURN   # sorted scores known so far (burn-in first)
    nxt = 0
    for i in range(BURN, n):
        j = i - d                                                   # scores / errors up to index j are known at the origin
        while nxt <= j:
            if nxt >= BURN and not np.isnan(s[nxt]): bisect.insort(srt, s[nxt])
            nxt += 1
        nxt = max(nxt, BURN)
        a_t = alpha + gamma * (cum[j + 1] if j >= BURN else 0.0)
        level = min(1.0, max(0.0, 1 - a_t)); m = len(srt)
        c[i] = srt[min(m - 1, math.ceil(level * (m - 1)))] if m else 0.0
        e = np.nan if np.isnan(y[i]) else float(not (lo[i] - c[i] <= y[i] <= hi[i] + c[i]))
        err[i] = 0.0 if np.isnan(e) else e
        cum[i + 1] = cum[i] + (0.0 if np.isnan(e) else (alpha - e))
    return c

def evaluate(lo, hi, y, c, nom):
    sl = slice(BURN, None); ok = ~np.isnan(y[sl]); L, U, Y, C = lo[sl][ok] - c[sl][ok], hi[sl][ok] + c[sl][ok], y[sl][ok], c[sl][ok]
    a = 1 - nom; w = U - L; score = w + (2 / a) * np.maximum(L - Y, 0) + (2 / a) * np.maximum(Y - U, 0)
    return dict(coverage=float(((Y >= L) & (Y <= U)).mean()), width=float(w.mean()), interval_score=float(score.mean()), n=int(ok.sum()))

def main():
    import run_horizon_models as R
    sel = json.load(open("results/horizon_selection.json")); df, arch, val0, test0 = R.prepare("C"); rows = []
    for z in ZONES:
        load = R.load_series(df, z)
        for k in H.HORIZONS + H.OUTLOOK:
            d = raw_validation(z, k, load, {"config": sel["choice"][f"{z}|{k}"]}, arch, val0, test0, R)
            for b in BANDS:
                lo, hi, y, s = scores_of(d, b); nom = BANDS[b][2]; cs = {"static": calib_static(s, k, nom)}
                for n in ROLL_N: cs[f"rolling_{n}w"] = calib_rolling(s, k, nom, n)
                for g in GAMMAS: cs[f"aci_g{g}"] = calib_aci(s, k, nom, g, lo, hi, y)
                for name, c in cs.items(): rows.append(dict(candidate=name, zone=z, k=k, band=b, nominal=nom, **evaluate(lo, hi, y, c, nom)))
            print(z, k, flush=True)
    cells = pd.DataFrame(rows); cells.to_csv("results/interval_val_cells.csv", index=False)
    st = cells[cells.candidate == "static"].set_index(["zone", "k", "band"]).interval_score; summ = []
    for name, g in cells.groupby("candidate", sort=False):
        g = g.set_index(["zone", "k", "band"])
        summ.append(dict(candidate=name, D_abs_cov_gap_pts=float((100 * (g.coverage - g.nominal)).abs().mean()), mean_coverage_80=float(100 * g[g.nominal == .8].coverage.mean()), mean_coverage_95=float(100 * g[g.nominal == .95].coverage.mean()),
                         min_cell_cov_80=float(100 * g[g.nominal == .8].coverage.min()), min_cell_cov_95=float(100 * g[g.nominal == .95].coverage.min()),
                         mean_width=float(g.width.mean()), mean_interval_score=float(g.interval_score.mean()), R_score_ratio_vs_static=float((g.interval_score / st).mean())))
    S = pd.DataFrame(summ); S["admissible"] = S.R_score_ratio_vs_static <= 1.10; S.to_csv("results/interval_val_summary.csv", index=False)
    stat = S[S.candidate == "static"].iloc[0]; adm = S[S.admissible & (S.candidate != "static")].sort_values("D_abs_cov_gap_pts")
    choice, why = "static", "no non-static candidate is admissible (score ratio <= 1.10)"
    if len(adm):
        best = adm.iloc[0]; near = adm[adm.D_abs_cov_gap_pts <= best.D_abs_cov_gap_pts + 0.1].sort_values("R_score_ratio_vs_static").iloc[0]
        if near.D_abs_cov_gap_pts < stat.D_abs_cov_gap_pts: choice, why = near.candidate, f"smallest coverage gap among admissible candidates (D={near.D_abs_cov_gap_pts:.2f} vs static {stat.D_abs_cov_gap_pts:.2f}; score ratio {near.R_score_ratio_vs_static:.3f})"
        else: why = "best admissible candidate does not beat the static coverage gap"
    json.dump({"selected": choice, "reason": why, "rule": "EXPERIMENTS.md I1"}, open("results/interval_selection.json", "w"), indent=1)
    print(S.round(3).to_string(index=False)); print("SELECTED:", choice, "-", why)

if __name__ == "__main__":
    main()
