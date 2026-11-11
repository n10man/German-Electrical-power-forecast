"""M5: LightGBM vs ridge vs small MLP, point forecasts, horizons 1/7/21, VALIDATION YEAR ONLY (rules: results/EXPERIMENTS.md entry M5, written before this was run).
  python scripts/run_model_comparison.py
Same frames / features / per-zone config / row filter as the locked models; train < 2024-10-25, score 2024-10-25..2025-10-24. The sealed test file is never read.
Comparison only: nothing here replaces or changes the map models. Writes results/model_comparison_val.csv and results/model_comparison_summary.json."""
import sys, json
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from gepf.data import ZONES
from gepf import horizon as H
import run_horizon_models as R

KS = [1, 7, 21]; ALPHAS = [0.01, 0.1, 1, 10, 100, 1000, 10000]; SEEDS = [0, 1, 2]
ONEHOT = {"hour": range(24), "dow": range(7), "month": range(1, 13)}

def encode(X, f, scaler=None, med=None):
    parts = []
    for c, cats in ONEHOT.items(): parts.append(pd.DataFrame({f"{c}_{v}": (X[c].values == v).astype(float) for v in cats}, index=X.index))
    parts.append(pd.DataFrame({"doy_sin": np.sin(2 * np.pi * X.doy.values / 366), "doy_cos": np.cos(2 * np.pi * X.doy.values / 366)}, index=X.index))
    num = [c for c in f if c not in ONEHOT and c != "doy"]
    N = X[num].values.astype(float)
    if med is None: med = np.nanmedian(N, axis=0)
    N = np.where(np.isnan(N), med, N)                       # M5a: NaNs in validation features -> training median (training NaN rows were dropped)
    if scaler is None: scaler = StandardScaler().fit(N)
    return np.hstack([p.values for p in parts] + [scaler.transform(N)]), (scaler, med)

def ridge_fit_predict(Xt, yt, Xv):
    best = None
    for a in ALPHAS:
        errs = []
        for tr, te in TimeSeriesSplit(5).split(Xt):
            m = Ridge(alpha=a).fit(Xt[tr], yt[tr]); errs.append(np.abs(m.predict(Xt[te]) - yt[te]).mean())
        if best is None or np.mean(errs) < best[0]: best = (np.mean(errs), a)
    return Ridge(alpha=best[1]).fit(Xt, yt).predict(Xv), best[1]

def mlp_fit_predict(Xt, yt, Xv, seed):
    mu, sd = yt.mean(), yt.std(); y = (yt - mu) / sd; cut = int(len(Xt) * 0.9)              # last 10% (in time) = early-stopping set
    m = MLPRegressor(hidden_layer_sizes=(64, 32), activation="relu", solver="adam", learning_rate_init=0.001, batch_size=256, alpha=1e-4, random_state=seed)
    rng = np.random.default_rng(seed); best, best_state, bad = np.inf, None, 0
    for ep in range(80):
        idx = rng.permutation(cut)
        for s in range(0, cut, 256): b = idx[s: s + 256]; m.partial_fit(Xt[b], y[b])
        e = np.abs(m.predict(Xt[cut:]) - y[cut:]).mean()
        if e < best - 1e-6: best, bad = e, 0; best_state = ([c.copy() for c in m.coefs_], [i.copy() for i in m.intercepts_])
        else:
            bad += 1
            if bad >= 8: break
    m.coefs_, m.intercepts_ = best_state
    return m.predict(Xv) * sd + mu, ep + 1

def main():
    sel = json.load(open("results/horizon_selection.json")); cj = json.load(open("models_future/cqr_offsets_future.json"))["features"]
    df, arch, val0, test0 = R.prepare("C"); rows = []
    for z in ZONES:
        load = R.load_series(df, z)
        for k in KS:
            cfg = sel["choice"][f"{z}|{k}"]; X, f = R.frame_for(z, load, k, cfg, arch); f = cj[f"{z}|{k}"]["features"]
            X = X.dropna(subset=[f"lag_{H.shift_hours(k)}h", f"lag_{H.week_lag(k)}h", "load_mw"] + [c for c in f if c.startswith("w_")])
            t = X[X.index < val0]; v = X[(X.index >= val0) & (X.index < test0)]; y = v.load_mw.values
            p_lgb = lgb.Booster(model_file=f"models_future/{z}_k{k}_mean.txt").predict(v[f]); mae = lambda p: float(np.abs(p - y).mean())
            num = [c for c in f if c not in ONEHOT and c != "doy"]; t2 = t.dropna(subset=num)           # M5a: drop training rows with NaN features (ridge / MLP only)
            Xt, (sc, med) = encode(t2, f); Xv, _ = encode(v, f, sc, med); yt = t2.load_mw.values
            p_r, a = ridge_fit_predict(Xt, yt, Xv); mm = []; eps = []
            for s in SEEDS: p, e = mlp_fit_predict(Xt, yt, Xv, s); mm.append(mae(p)); eps.append(e)
            rows.append(dict(zone=z, k=k, config=cfg, n_train=len(t2), n_train_lightgbm=len(t), n_val=len(v), mae_lightgbm=mae(p_lgb), mae_ridge=mae(p_r), ridge_alpha=a, mae_mlp_mean=float(np.mean(mm)), mae_mlp_min=float(min(mm)), mae_mlp_max=float(max(mm)),
                             mlp_epochs=",".join(map(str, eps)), best_baseline_week=float(np.nanmean(np.abs(v["B_week"].values - y))))); print(rows[-1], flush=True)
    D = pd.DataFrame(rows); D.to_csv("results/model_comparison_val.csv", index=False)
    def verdict(a, b):   # a beats b if lower by more than 1% of b
        w = int((D[a] < 0.99 * D[b]).sum()); l = int((D[b] < 0.99 * D[a]).sum()); return dict(wins=w, losses=l, ties=len(D) - w - l, pooled_a=float(D[a].sum()), pooled_b=float(D[b].sum()))
    out = {"cells": len(D), "ridge_vs_lightgbm": verdict("mae_ridge", "mae_lightgbm"), "mlp_vs_lightgbm": verdict("mae_mlp_mean", "mae_lightgbm"), "mlp_vs_ridge": verdict("mae_mlp_mean", "mae_ridge"),
           "pooled": {c: float(D[c].sum()) for c in ("mae_lightgbm", "mae_ridge", "mae_mlp_mean")}}
    json.dump(out, open("results/model_comparison_summary.json", "w"), indent=1); print(json.dumps(out, indent=1))

if __name__ == "__main__":
    main()
