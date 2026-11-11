"""Train the FUTURE-forecast models on TRAIN only, calibrate CQR offsets on VALIDATION, save to models_future/, write results/model_lock_future.json.
Configuration per zone and horizon comes from results/horizon_selection.json (validation-only choice). Never reads the sealed test file.
Also writes results/horizon_coverage_val.csv: honest per-horizon coverage on validation with swapped halves (calibrate on one half, score on the other)."""
import sys, json, hashlib, argparse
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument("--force", action="store_true"); args = ap.parse_args()
if Path("results/model_lock_future.json").exists() and not args.force:
    sys.exit("REFUSED: results/model_lock_future.json exists (it is committed before the sealed test run). Pass --force to overwrite deliberately.")
import numpy as np, pandas as pd
from gepf.data import ZONES
from gepf.models import fit
from gepf.quant import QS, BANDS, fit_quantiles, predict_quantiles, cqr_offset
from gepf import horizon as H
import run_horizon_models as R

OUT = Path("models_future"); OUT.mkdir(exist_ok=True)
sel = json.load(open("results/horizon_selection.json"))
df, arch, val0, test0 = R.prepare("C")
half = val0 + pd.DateOffset(months=6)
offsets, feats_used, cov = {}, {}, []
for z in ZONES:
    load = R.load_series(df, z)
    for k in H.HORIZONS + H.OUTLOOK:
        cfg = sel["choice"][f"{z}|{k}"]
        X, f = R.frame_for(z, load, k, cfg, arch)
        X = X.dropna(subset=[f"lag_{H.shift_hours(k)}h", f"lag_{H.week_lag(k)}h", "load_mw"] + [c for c in f if c.startswith("w_")])
        t = X[X.index < val0]; v = X[(X.index >= val0) & (X.index < test0)]
        fit(t[f], t.load_mw).booster_.save_model(str(OUT / f"{z}_k{k}_mean.txt"))
        qm = fit_quantiles(t, f)
        for a, m in qm.items(): m.booster_.save_model(str(OUT / f"{z}_k{k}_q{a}.txt"))
        q = predict_quantiles(qm, v, f); y = v.load_mw.values; hA = (v.index < half)
        for b, (la, ha, nom) in BANDS.items():
            lo, hi = q[f"q{la}"].values, q[f"q{ha}"].values
            offsets[f"{z}|{k}|{b}"] = cqr_offset(y, lo, hi, nom)
            for nm, cal, sc in (("A->B", hA, ~hA), ("B->A", ~hA, hA)):
                o = cqr_offset(y[cal], lo[cal], hi[cal], nom)
                cov.append(dict(zone=z, k=k, band=b, swap=nm, nominal=nom, coverage=float(((y[sc] >= lo[sc] - o) & (y[sc] <= hi[sc] + o)).mean()), width=float((hi[sc] - lo[sc] + 2 * o).mean())))
            cov.append(dict(zone=z, k=k, band=b, swap="raw", nominal=nom, coverage=float(((y >= lo) & (y <= hi)).mean()), width=float((hi - lo).mean())))
        feats_used[f"{z}|{k}"] = dict(config=cfg, features=f); print(z, k, cfg, flush=True)
json.dump({"offsets": offsets, "features": feats_used}, open(OUT / "cqr_offsets_future.json", "w"), indent=1)
pd.DataFrame(cov).to_csv("results/horizon_coverage_val.csv", index=False)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
files = sorted(p for p in OUT.iterdir() if p.suffix in (".txt", ".json"))
lock = {"sha256": {p.name: sha(p) for p in files}, "train_end": str(val0 - pd.Timedelta(hours=1)), "val_end": str(test0 - pd.Timedelta(hours=1)), "seed": 42}
json.dump(lock, open("results/model_lock_future.json", "w"), indent=1); print("locked", len(files), "files")
