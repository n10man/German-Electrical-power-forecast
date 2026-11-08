"""Data card + plots, using train/val only (sealed test never read)."""
import sys; sys.path.insert(0, "src")
import json, pandas as pd, numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from gepf.data import ZONES, PROC, RAW
df = pd.read_parquet(PROC / "trainval.parquet")
W = df.pivot(index="timestamp_utc", columns="zone", values="load_mw")[ZONES]
nat = W.sum(axis=1, min_count=4)
ref = pd.read_parquet(RAW / "ref_DE_410.parquet").set_index("timestamp_utc")["mw"].reindex(W.index)
j = pd.concat([nat.rename("sum"), ref.rename("de")], axis=1).dropna()
rel = (j["sum"] - j["de"]) / j["de"]
print("ZONE ROWS (hourly, UTC):", W.shape[0], W.index.min(), "->", W.index.max())
print("missing hours per zone:", W.isna().sum().to_dict())
print("zone-sum vs SMARD DE total: median %.3f%%, mean %.3f%%, p99 abs %.3f%%" % (rel.median()*100, rel.mean()*100, rel.abs().quantile(.99)*100))
for y in (2016, 2019, 2023):
    s = nat[str(y)]; print(f"{y}: mean {s.mean()/1000:.1f} GW, total {s.sum()/1e6:.0f} TWh (incl. NaN as 0)")
print("zone mean GW (all train+val):", (W.mean()/1000).round(2).to_dict())
loc = nat.dropna(); l = loc.index.tz_convert("Europe/Berlin")
print("weekday vs Sunday mean GW: %.1f / %.1f" % (loc[l.day_of_week<5].mean()/1e3, loc[l.day_of_week==6].mean()/1e3))
print("winter vs summer mean GW: %.1f / %.1f" % (loc[l.month.isin([12,1,2])].mean()/1e3, loc[l.month.isin([6,7,8])].mean()/1e3))
g = W.isna().any(axis=1); runs = (g != g.shift()).cumsum()[g]
print("longest gap (hours, any zone):", (runs.value_counts().max() if g.any() else 0), "; gap clusters:", runs.nunique())
for t in ["2022-06-01 16:00", "2019-01-15 08:00", "2023-12-24 03:00"]:
    t = pd.Timestamp(t, tz="UTC"); print(t, "UTC /", t.tz_convert("Europe/Berlin"), (W.loc[t].round(1).to_dict()), "sum", round(nat[t], 1), "SMARD DE", ref[t])
Path = __import__("pathlib").Path; Path("results/figures").mkdir(parents=True, exist_ok=True)
fig, ax = plt.subplots(4, 1, figsize=(10, 9), sharex=True)
wk = W["2022-06-06":"2022-06-12 23:00"]
for a, z in zip(ax, ZONES): a.plot(wk.index, wk[z]); a.set_ylabel(f"{z}\nMWh/h")
ax[0].set_title("One week per zone (2022-06-06..12, UTC)"); fig.tight_layout(); fig.savefig("results/figures/week_per_zone.png", dpi=110)
fig, ax = plt.subplots(4, 1, figsize=(10, 9), sharex=True)
yr = W.loc["2023"]
for a, z in zip(ax, ZONES): a.plot(yr.index, yr[z], lw=.4); a.plot(yr[z].rolling(168, min_periods=100).mean(), c="r", lw=1); a.set_ylabel(f"{z}\nMWh/h")
ax[0].set_title("One year per zone (2023, UTC; red = 7-day mean)"); fig.tight_layout(); fig.savefig("results/figures/year_per_zone.png", dpi=110)
