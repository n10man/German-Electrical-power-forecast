"""Phase 5 stress tests S0-S4. Uses trainval.parquet only (test period sealed)."""
import sys; sys.path.insert(0, "src")
import numpy as np, pandas as pd, json
from gepf.data import PROC, ZONES
from gepf.models import feats, fit, WX, LAGS
from gepf.evalutil import mae, mape
RNG = 42; f = feats(True, False)
df = pd.read_parquet(PROC / "trainval.parquet").sort_values(["zone", "timestamp_utc"]).reset_index(drop=True)
bi = json.load(open(PROC / "build_info.json")); VAL0 = pd.Timestamp(bi["val_start"]); TEST0 = pd.Timestamp(bi["test_start"])
assert df.timestamp_utc.max() < TEST0
T = lambda s: pd.Timestamp(s, tz="UTC")
WINDOWS = [(f"{y}", T(f"{y}-01-01"), T(f"{y+1}-01-01")) for y in range(2018, 2024)] + [("2024a", T("2024-01-01"), VAL0), ("val", VAL0, TEST0)]
need = ["lag_336h", "lag_168h", "load_mw"]
def zone_df(z): return df[df.zone == z].reset_index(drop=True)
def day_label(d): return d.timestamp_utc.dt.tz_convert("Europe/Berlin").dt.normalize().dt.tz_localize(None)

# ---- S0: rolling-origin backtest
preds = []
for z in ZONES:
    d = zone_df(z); 
    for name, a, b in WINDOWS:
        tr = d[(d.timestamp_utc < a)].dropna(subset=need); ev = d[(d.timestamp_utc >= a) & (d.timestamp_utc < b)].dropna(subset=need).copy()
        m = fit(tr[f], tr.load_mw); ev["pred"] = m.predict(ev[f]); ev["b1"] = ev.lag_168h; ev["window"] = name; preds.append(ev)
P = pd.concat(preds); P.to_parquet(PROC / "backtest_preds.parquet")
rows = [dict(zone=z, window=w, n=len(g), mae_model=mae(g.load_mw, g.pred), mae_b1=mae(g.load_mw, g.b1), mape_model=mape(g.load_mw, g.pred), mape_b1=mape(g.load_mw, g.b1)) for (z, w), g in P.groupby(["zone", "window"])]
S0 = pd.DataFrame(rows); S0.to_csv("results/stress_s0_rolling.csv", index=False); print("S0 rolling-origin (MAE model / B1):"); print(S0.pivot(index="window", columns="zone", values="mae_model").round(0)); print(S0.pivot(index="window", columns="zone", values="mae_b1").round(0))

# ---- S1: subsets pooled over all windows
def runs_mask(day_series_flag, minlen=3):
    """flag per day (Series indexed by day, sorted) -> True where inside a run of >= minlen consecutive flagged days."""
    g = (day_series_flag != day_series_flag.shift()).cumsum(); size = day_series_flag.groupby(g).transform("size")
    return day_series_flag & (size >= minlen)
rows = []
for z in ZONES:
    g = P[P.zone == z].copy(); g["day"] = day_label(g)
    dm = g.groupby("day").w_temperature_2m.mean(); full = dm.reindex(pd.date_range(dm.index.min(), dm.index.max()))
    hw = runs_mask(full >= dm.quantile(.9)); cs = runs_mask(full <= dm.quantile(.1))
    hot5 = dm >= dm.quantile(.95); cold5 = dm <= dm.quantile(.05)
    mon = g.day.dt.month; dd = g.day.dt.day
    sub = {"all": np.ones(len(g), bool), "holiday": (g.holiday_share >= .5).values, "bridge_day": (g.bridge_day == 1).values,
           "xmas_newyear": (((mon == 12) & (dd >= 24)) | ((mon == 1) & (dd <= 1))).values,
           "heat_wave": g.day.map(hw).fillna(False).astype(bool).values, "cold_snap": g.day.map(cs).fillna(False).astype(bool).values,
           "hottest5pct_days": g.day.map(hot5).fillna(False).astype(bool).values, "coldest5pct_days": g.day.map(cold5).fillna(False).astype(bool).values}
    for k, m in sub.items():
        if m.sum() == 0: continue
        y = g.load_mw.values[m]; rows.append(dict(zone=z, subset=k, n_hours=int(m.sum()), mae_model=mae(y, g.pred.values[m]), mae_b1=mae(y, g.b1.values[m]), mape_model=mape(y, g.pred.values[m]), mape_b1=mape(y, g.b1.values[m])))
S1 = pd.DataFrame(rows); S1["ratio"] = S1.mae_model / S1.mae_b1; S1["fail_vs_b1"] = S1.mae_model > S1.mae_b1; S1.to_csv("results/stress_s1_subsets.csv", index=False)
print("\nS1 subsets (MAE model | B1 | ratio | hours):"); print(S1.pivot(index="subset", columns="zone", values="ratio").round(2)); print(S1.pivot(index="subset", columns="zone", values="n_hours")); print(S1.pivot(index="subset", columns="zone", values="mae_model").round(0))
print("S1 failures vs B1:", S1[S1.fail_vs_b1][["zone", "subset", "mae_model", "mae_b1"]].round(0).to_string(index=False) or "none")

# ---- S2: shift, static model trained < 2020
rows = []
for z in ZONES:
    d = zone_df(z); tr = d[d.timestamp_utc < T("2020-01-01")].dropna(subset=need); m = fit(tr[f], tr.load_mw)
    for y in (2019, 2020, 2021, 2022):
        ev = d[(d.timestamp_utc >= T(f"{y}-01-01")) & (d.timestamp_utc < T(f"{y+1}-01-01"))].dropna(subset=need)
        roll = P[(P.zone == z) & (P.window == str(y))]
        rows.append(dict(zone=z, year=y, mae_static=mae(ev.load_mw, m.predict(ev[f])) if y >= 2020 else np.nan, mae_rolling=mae(roll.load_mw, roll.pred), mae_b1=mae(roll.load_mw, roll.b1)))
S2 = pd.DataFrame(rows); S2["static_over_rolling"] = S2.mae_static / S2.mae_rolling; S2["fail"] = (S2.mae_static > S2.mae_b1) | (S2.static_over_rolling > 1.25); S2.to_csv("results/stress_s2_shift.csv", index=False)
print("\nS2 shift (static trained <2020):"); print(S2.round(2).to_string(index=False))

# ---- S3/S4 on validation year, M2 trained on train only
sig = {"w_temperature_2m": 1.5, "w_relative_humidity_2m": 8.0, "w_wind_speed_10m": 1.0, "w_shortwave_radiation": 80.0, "w_cloud_cover": 15.0}
rng = np.random.default_rng(RNG)
def noise(n, s, kind):
    e = rng.normal(size=n)
    if kind == "iid": return e * s
    a = 0.95; x = np.empty(n); x[0] = e[0]
    for i in range(1, n): x[i] = a * x[i - 1] + np.sqrt(1 - a * a) * e[i]
    return x * s
def clip(c, x): return np.clip(x, 0, 100) if c in ("w_relative_humidity_2m", "w_cloud_cover") else (np.clip(x, 0, None) if c in ("w_wind_speed_10m", "w_shortwave_radiation") else x)
def miss_mask(n, frac, kind):
    if kind == "random": return rng.random(n) < frac
    m = np.zeros(n, bool); nb = int(frac * n / 48)
    for s in rng.choice(n - 48, nb, replace=False): m[s:s + 48] = True
    return m
rows = []; models = {}
for z in ZONES:
    d = zone_df(z); tr = d[d.timestamp_utc < VAL0].dropna(subset=need); models[z] = fit(tr[f], tr.load_mw)
    vi = d.index[(d.timestamp_utc >= VAL0)]; ev = d.loc[vi].dropna(subset=need); y = ev.load_mw.values; b1 = ev.lag_168h.values
    clean = mae(y, models[z].predict(ev[f])); rows.append(dict(test="clean", scenario="-", zone=z, mae=clean, mae_b1=mae(y, b1), ratio_clean=1.0))
    for kind in ("iid", "ar1"):
        for lvl in (1, 2, 4):
            X = ev[f].copy()
            for c, s in sig.items(): X[c] = clip(c, X[c].values + noise(len(X), s * lvl, kind))
            e = mae(y, models[z].predict(X)); rows.append(dict(test="S3_weather_noise", scenario=f"{kind}_x{lvl}", zone=z, mae=e, mae_b1=mae(y, b1), ratio_clean=e / clean))
    for kind in ("random", "block48"):
        for frac in (.1, .3):
            X = ev[f].copy(); m = miss_mask(len(X), frac, kind)
            for c in WX: X.loc[m, c] = np.nan
            e = mae(y, models[z].predict(X)); rows.append(dict(test="S4_missing_weather", scenario=f"{kind}_{int(frac*100)}%", zone=z, mae=e, mae_b1=mae(y, b1), ratio_clean=e / clean))
            # missing load history on the FULL zone timeline: lag_k NaN where hour t-k is missing
            M = pd.Series(miss_mask(len(d), frac, kind), index=d.index); X = ev[f].copy()
            for lag in LAGS:
                k = int(lag[4:-1]); X[lag] = np.where(M.shift(k, fill_value=False).loc[ev.index].values, np.nan, X[lag])
            b1m = np.where(X["lag_168h"].isna(), np.nan, b1); e = mae(y, models[z].predict(X)); okb = ~np.isnan(b1m)
            rows.append(dict(test="S4_missing_load", scenario=f"{kind}_{int(frac*100)}%", zone=z, mae=e, mae_b1=mae(y[okb], b1m[okb]), ratio_clean=e / clean))
S34 = pd.DataFrame(rows); S34["fail"] = (S34.ratio_clean > 1.25) | (S34.mae > S34.mae_b1); S34.to_csv("results/stress_s3_s4.csv", index=False)
print("\nS3/S4 MAE ratio to clean (mean over zones) and FAIL count:"); print(S34.groupby(["test", "scenario"]).agg(ratio=("ratio_clean", "mean"), worst=("ratio_clean", "max"), fails=("fail", "sum")).round(2))
print(S34[S34.test == "clean"][["zone", "mae", "mae_b1"]].round(0).to_string(index=False))
