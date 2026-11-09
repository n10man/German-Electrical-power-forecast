"""L1/L2 lag ablation, VALIDATION ONLY (the sealed test file is never opened). Report-only: no locked model is touched."""
import sys; sys.path.insert(0, "src")
import numpy as np, pandas as pd
from gepf.data import PROC, ZONES
from gepf.models import CAL, WX, fit
from gepf.evalutil import score, rule_v2
VARIANTS = {"M2_ref_24_48_168_336": ["lag_24h", "lag_48h", "lag_168h", "lag_336h"], "L1_48_168_336": ["lag_48h", "lag_168h", "lag_336h"], "L2_168_336": ["lag_168h", "lag_336h"]}
df = pd.read_parquet(PROC / "trainval.parquet"); assert set(df.split) == {"train", "val"}
need = ["lag_336h", "lag_168h", "load_mw"]
tr = df[df.split == "train"].dropna(subset=need); va = df[df.split == "val"].dropna(subset=need)
rows = []
for name, lags in VARIANTS.items():
    f = CAL + lags + WX
    for z in ZONES:
        t, v = tr[tr.zone == z], va[va.zone == z]
        m = fit(t[f], t.load_mw); s = score(v, m.predict(v[f]), v["lag_168h"].values)
        s.update(variant=name, zone=z, n_lags=len(lags)); s["rule_v2"] = rule_v2(s, s["base_mae_all"]); rows.append(s)
R = pd.DataFrame(rows); R.to_csv("results/lag_ablation_val.csv", index=False)
cols = ["variant", "zone", "mae_all", "rmse", "mape", "base_mae_all", "mae_holiday", "base_mae_holiday", "mae_hot5", "base_mae_hot5", "mae_cold5", "base_mae_cold5", "rule_v2"]
print(R[cols].round(1).to_string(index=False))
g = R.groupby("variant").mae_all.mean(); ref = g["M2_ref_24_48_168_336"]
print("\nmean MAE over zones:", {k: round(v, 1) for k, v in g.items()}); print("change vs M2 (%):", {k: round(100 * (v / ref - 1), 1) for k, v in g.items()})
print("per-zone change vs M2 (%):"); print((R.pivot(index="zone", columns="variant", values="mae_all").pipe(lambda p: p.div(p["M2_ref_24_48_168_336"], axis=0) - 1) * 100).round(1))
print("rule v2 passes:", R.groupby("variant").rule_v2.sum().to_dict(), "of 4 zones")
