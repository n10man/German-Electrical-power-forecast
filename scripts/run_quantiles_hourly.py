"""Phase 4b: hour-of-day conformal calibration (Q3 per hour, Q4 per 6h block). Validation only."""
import sys; sys.path.insert(0, "src")
import numpy as np, pandas as pd, json
from gepf.data import PROC, ZONES
from gepf.models import feats
from gepf.quant import *
df = pd.read_parquet(PROC / "trainval.parquet"); need = ["lag_336h", "lag_168h", "load_mw"]
tr = df[df.split == "train"].dropna(subset=need); va = df[df.split == "val"].dropna(subset=need).copy()
f = feats(True, False); mid = va.timestamp_utc.min() + (va.timestamp_utc.max() - va.timestamp_utc.min()) / 2
va["half"] = np.where(va.timestamp_utc <= mid, "A", "B")
rows = []; Q2W = {"80": 1318.0, "95": 2168.0}
for z in ZONES:
    t = tr[tr.zone == z]; v = va[va.zone == z]
    q = predict_quantiles(fit_quantiles(t, f), v, f); y = v.load_mw.values; hr = v.hour.values
    for b, (la, ha, nom) in BANDS.items():
        lo, hi = q[f"q{la}"].values, q[f"q{ha}"].values
        for name, grp in [("Q2_global", np.zeros(24, int)), ("Q3_hour", np.arange(24)), ("Q4_6h", np.arange(24) // 6)]:
            for ev in "AB":
                cal = "B" if ev == "A" else "A"; e = (v.half == ev).values; c = (v.half == cal).values
                off = np.zeros(len(v))
                for g in np.unique(grp):
                    hrs = np.where(grp == g)[0]; mc = c & np.isin(hr, hrs); me = np.isin(hr, hrs)
                    off[me] = cqr_offset(y[mc], lo[mc], hi[mc], nom)
                inn = (y >= lo - off) & (y <= hi + off); w = (hi + off) - (lo - off)
                for h in range(24):
                    m = e & (hr == h); rows.append(dict(method=name, zone=z, band=b, swap=f"{cal}->{ev}", hour=h, n=int(m.sum()), coverage=float(inn[m].mean()), nominal=nom, width=float(w[m].mean())))
R = pd.DataFrame(rows); R["err_pp"] = (R.coverage - R.nominal) * 100; R.to_csv("results/quantiles_hourly_cells.csv", index=False)
for name in ["Q2_global", "Q3_hour", "Q4_6h"]:
    r = R[R.method == name]; out = {}
    for b in ["80", "95"]:
        rb = r[r.band == b]; width = rb.groupby(["zone", "swap"]).apply(lambda d: np.average(d.width, weights=d.n), include_groups=False).mean()
        out[b] = dict(avg_width=round(width, 1), growth_vs_Q2=round(width / Q2W[b] - 1, 3), cells=len(rb), cells_fail=int((rb.err_pp.abs() > 5).sum()), worst_pp=round(rb.err_pp.abs().max(), 1), mean_abs_err_pp=round(rb.err_pp.abs().mean(), 2))
    print(name, json.dumps(out))
