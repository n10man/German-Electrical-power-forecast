"""Phase 3 experiments, validation only. usage: python scripts/run_models.py M1 M2 M3 [M4]"""
import sys; sys.path.insert(0, "src")
import numpy as np, pandas as pd
from gepf.data import PROC, ZONES
from gepf.models import feats, fit, add_zone_id
from gepf.evalutil import score, rule_v2
df = add_zone_id(pd.read_parquet(PROC / "trainval.parquet"), ZONES)
need = ["lag_336h", "lag_168h", "load_mw"]
tr = df[(df.split == "train")].dropna(subset=need); va = df[df.split == "val"].dropna(subset=need)
assert va.timestamp_utc.min() > tr.timestamp_utc.max()
CFG = {"M1": dict(weather=False, pooled=False, over={}), "M2": dict(weather=True, pooled=False, over={}),
       "M3": dict(weather=True, pooled=True, over={}),
       "M4": dict(weather=True, pooled=False, over=dict(learning_rate=0.02, n_estimators=1500))}   # M4 default; edited by decision
def run(name, c):
    f = feats(c["weather"], c["pooled"]); rows = []
    if c["pooled"]:
        m = fit(tr[f], tr.load_mw, **c["over"]); 
    for z in ZONES:
        t, v = tr[tr.zone == z], va[va.zone == z]
        if not c["pooled"]: m = fit(t[f], t.load_mw, **c["over"])
        s = score(v, m.predict(v[f]), v["lag_168h"].values); s.update(exp=name, zone=z)
        b1 = s["base_mae_all"]; s["keep_v2"] = rule_v2(s, b1); rows.append(s)
    return pd.DataFrame(rows)
if __name__ == "__main__":
    out = []
    for n in sys.argv[1:]:
        r = run(n, CFG[n]); out.append(r)
        print(r[["exp", "zone", "mae_all", "base_mae_all", "rmse", "mape", "mae_holiday", "base_mae_holiday", "mae_hot5", "base_mae_hot5", "mae_cold5", "base_mae_cold5", "keep_v2"]].round(1).to_string(index=False))
        print(n, "mean MAE over zones: %.1f" % r.mae_all.mean(), "| B1 mean: %.1f" % r.base_mae_all.mean(), "| zones kept:", int(r.keep_v2.sum()), flush=True)
    pd.concat(out).to_csv("results/models_val_" + "_".join(sys.argv[1:]) + ".csv", index=False)
