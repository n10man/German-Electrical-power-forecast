"""Seasonal-naive baselines on VALIDATION only. B0 = same hour yesterday (lag_24h), B1 = same hour last week (lag_168h)."""
import sys; sys.path.insert(0, "src")
import numpy as np, pandas as pd
from gepf.data import PROC, ZONES
df = pd.read_parquet(PROC / "trainval.parquet"); v = df[df.split == "val"]
def metrics(y, p):
    e = y - p; return dict(MAE=np.abs(e).mean(), RMSE=np.sqrt((e**2).mean()), MAPE=(np.abs(e) / y).mean() * 100)
rows = []
for name, col in [("B0_yesterday", "lag_24h"), ("B1_last_week", "lag_168h")]:
    for z in ZONES:
        d = v[v.zone == z].dropna(subset=[col, "load_mw"])
        rows.append(dict(baseline=name, zone=z, n=len(d), **metrics(d.load_mw, d[col])))
r = pd.DataFrame(rows); r.to_csv("results/baselines_val.csv", index=False)
print(r.round(2).to_string(index=False))
print("val period:", v.timestamp_utc.min(), "->", v.timestamp_utc.max())
