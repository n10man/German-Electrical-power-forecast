"""Direct multi-horizon models, VALIDATION ONLY (the sealed test file is never read here).

  python scripts/run_horizon_models.py A      # calendar + horizon-safe load lags (all horizons incl. outlook 21)
  python scripts/run_horizon_models.py B      # A + archived temperature forecast (lead = horizon, from 2021-03), horizons <= 7
  python scripts/run_horizon_models.py C      # A + all five archived forecast variables (exist only from 2024-01-19), horizons <= 7
  python scripts/run_horizon_models.py X1     # reported only: horizon 10 with day-7 archived forecast as a stand-in (optimistic)
Rules are in results/EXPERIMENTS.md (entry H0). Output: results/horizon_val_<config>.csv
"""
import sys, json, argparse
sys.path.insert(0, "src")
from pathlib import Path
import numpy as np, pandas as pd
from gepf.data import ZONES, PROC, weather_features
from gepf.models import fit
from gepf.evalutil import mae, rmse, subsets
from gepf import horizon as H

ARCHIVE = Path("data/raw/forecast_archive.parquet")

def load_series(df, zone):
    s = df[df.zone == zone].set_index("timestamp_utc")["load_mw"].sort_index()
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="h", tz="UTC"))

def prepare(config):
    bi = json.load(open(PROC / "build_info.json")); val0, test0 = pd.Timestamp(bi["val_start"]), pd.Timestamp(bi["test_start"])
    df = pd.read_parquet(PROC / "trainval.parquet")           # train + validation only; no test rows exist in this file
    assert df.timestamp_utc.max() < test0
    arch = pd.read_parquet(ARCHIVE) if config in ("B", "C", "X1") else None
    return df, arch, val0, test0

def frame_for(zone, load, k, config, arch):
    if config == "A": return H.build_frame(zone, load, k, None), H.feature_names(k, False)
    if config in ("B", "C"):
        X = H.build_frame(zone, load, k, arch); f = H.feature_names(k, "T" if config == "B" else "ALL")
        return X.drop(columns=[c for c in H.WX if c not in f]), f
    if config == "X1":   # stand-in: day-7 forecast used for a horizon-10 model (NOT available at that lead in reality)
        X = H.build_frame(zone, load, 7, arch)
        Y = H.build_frame(zone, load, k, None)
        for c in H.WX: Y[c] = X[c]
        return Y, H.feature_names(k, False) + H.WX

def run(config, ks):
    df, arch, val0, test0 = prepare(config); rows = []
    for z in ZONES:
        load = load_series(df, z)
        obs = weather_features(z, load.index)               # OBSERVED temperature, only to rank hot/cold days (labels), never a model input
        for k in ks:
            X, f = frame_for(z, load, k, config, arch)
            need = [f"lag_{H.shift_hours(k)}h", f"lag_{H.week_lag(k)}h", "load_mw"]
            if config in ("B", "C", "X1"): need += [c for c in f if c.startswith("w_")]
            X = X.dropna(subset=need)
            t = X[X.index < val0]; v = X[(X.index >= val0) & (X.index < test0)]
            model = fit(t[f], t.load_mw); p = model.predict(v[f]); y = v.load_mw.values
            d = v.reset_index(names="timestamp_utc"); d["w_temperature_2m"] = obs.w_temperature_2m.reindex(v.index).values
            r = dict(config=config, zone=z, k=k, n_train=len(t), n_val=len(v), train_start=str(t.index.min()), n_features=len(f))
            for name, m in subsets(d).items():
                b = {c: v[c].values for c in ("B_day", "B_week", "B_wk4avg")}
                r[f"mae_{name}"] = mae(y[m], p[m])
                for c, a in b.items():
                    ok = m & ~np.isnan(a); r[f"{c}_{name}"] = mae(y[ok], a[ok]) if ok.any() else np.nan
                r[f"n_{name}"] = int(m.sum())
            r["rmse"] = rmse(y, p); rows.append(r); print(config, z, k, round(r["mae_all"]), "B_day", round(r["B_day_all"]), "B_week", round(r["B_week_all"]), flush=True)
    out = pd.DataFrame(rows); out.to_csv(f"results/horizon_val_{config}.csv", index=False); return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("config", choices=["A", "B", "C", "X1"]); a = ap.parse_args()
    ks = {"A": H.HORIZONS + H.OUTLOOK, "B": [k for k in H.HORIZONS if k <= H.WEATHER_MAX_K], "C": [k for k in H.HORIZONS if k <= H.WEATHER_MAX_K], "X1": [10]}[a.config]
    run(a.config, ks)
