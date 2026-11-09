"""Train the FINAL models on TRAIN only (validation untouched by fitting), calibrate CQR offsets on VALIDATION, save to models/, write results/model_lock.json (SHA-256).
Never reads data/processed/sealed_test.parquet."""
import sys, json, hashlib, subprocess, argparse; sys.path.insert(0, "src")
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument("--force", action="store_true", help="overwrite results/model_lock.json and models/")
args = ap.parse_args()
if Path("results/model_lock.json").exists() and not args.force:
    sys.exit("REFUSED: results/model_lock.json already exists. Re-training can change the model hashes and break the lock recorded in results/EXPERIMENTS.md (F1) and checked by final_eval.py. Pass --force to overwrite it deliberately.")
import numpy as np, pandas as pd
from gepf.data import PROC, ZONES
from gepf.models import feats, fit
from gepf.quant import QS, BANDS, fit_quantiles, predict_quantiles, cqr_offset
OUT = Path("models"); OUT.mkdir(exist_ok=True)
df = pd.read_parquet(PROC / "trainval.parquet"); need = ["lag_336h", "lag_168h", "load_mw"]
tr = df[df.split == "train"].dropna(subset=need); va = df[df.split == "val"].dropna(subset=need)
f = feats(True, False); offsets = {}
for z in ZONES:
    t, v = tr[tr.zone == z], va[va.zone == z]
    fit(t[f], t.load_mw).booster_.save_model(str(OUT / f"{z}_mean.txt"))
    qm = fit_quantiles(t, f)
    for a, m in qm.items(): m.booster_.save_model(str(OUT / f"{z}_q{a}.txt"))
    q = predict_quantiles(qm, v, f); y = v.load_mw.values
    for b, (la, ha, nom) in BANDS.items(): offsets[f"{z}_{b}"] = cqr_offset(y, q[f"q{la}"].values, q[f"q{ha}"].values, nom)
json.dump({"offsets": offsets, "features": f}, open(OUT / "cqr_offsets.json", "w"), indent=1)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
files = sorted(p for p in OUT.iterdir() if p.suffix in (".txt", ".json"))
lock = {"sha256": {p.name: sha(p) for p in files}, "train_end": str(tr.timestamp_utc.max()), "val_end": str(va.timestamp_utc.max()), "seed": 42}
json.dump(lock, open("results/model_lock.json", "w"), indent=1); print(json.dumps(lock, indent=1)); print(offsets)
