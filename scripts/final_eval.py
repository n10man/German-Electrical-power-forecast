"""FINAL evaluation on the sealed test period. Run ONCE:  python scripts/final_eval.py --confirm-final

Gate order (nothing touches the sealed file before all pass):
 1. --confirm-final must be given, otherwise exit 2.
 2. results/FINAL_EVAL_DONE must not exist (the final evaluation runs only once), otherwise exit 3.
 3. SHA-256 of every file in models/ must equal results/model_lock.json, otherwise exit 4.
--dummy swaps the sealed file for synthetic data (dry run); it never reads the sealed file, never writes the DONE marker and writes outputs to --out-dir.
"""
import sys, os, json, hashlib, argparse, subprocess, datetime
sys.path.insert(0, "src")
from pathlib import Path
import numpy as np, pandas as pd, lightgbm as lgb

SEALED = Path("data/processed/sealed_test.parquet"); DONE = Path("results/FINAL_EVAL_DONE")
LOCK = Path("results/model_lock.json"); MODELS = Path("models"); OUTDIR = Path("results")
from gepf.data import ZONES
from gepf.models import feats
from gepf.quant import QS, BANDS
from gepf.evalutil import mae, rmse, mape, subsets

def refuse(code, msg): print("REFUSED:", msg, file=sys.stderr); sys.exit(code)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def gate(args):
    if not args.confirm_final: refuse(2, "--confirm-final is required (the sealed test period is evaluated once).")
    if not args.dummy and DONE.exists(): refuse(3, f"{DONE} exists: the final evaluation has already been run.")
    lock = json.load(open(LOCK))["sha256"]; have = {p.name for p in MODELS.iterdir() if p.suffix in (".txt", ".json")}
    if set(lock) != have: refuse(4, f"model files differ from lock: {sorted(set(lock) ^ have)}")
    bad = [n for n, h in lock.items() if sha(MODELS / n) != h]
    if bad: refuse(4, f"SHA-256 mismatch for {bad}")
    return lock

def dummy_frame():
    rng = np.random.default_rng(0); idx = pd.date_range("2030-01-01", periods=24 * 40, freq="h", tz="UTC"); rows = []
    for z in ZONES:
        d = pd.DataFrame(index=idx); loc = idx.tz_convert("Europe/Berlin")
        d["hour"] = loc.hour; d["dow"] = loc.day_of_week; d["month"] = loc.month; d["doy"] = loc.dayofyear
        d["is_weekend"] = (d.dow >= 5).astype(int); d["holiday_share"] = (d.index.day == 6) * 1.0; d["bridge_day"] = 0
        base = 10000 + 3000 * np.sin(2 * np.pi * d.hour / 24) + rng.normal(0, 200, len(d)); d["load_mw"] = base
        for k in (24, 48, 168, 336): d[f"lag_{k}h"] = pd.Series(base, index=idx).shift(k)
        d["w_temperature_2m"] = rng.normal(5, 5, len(d)); d["w_relative_humidity_2m"] = rng.uniform(40, 100, len(d)); d["w_wind_speed_10m"] = rng.uniform(0, 10, len(d))
        d["w_shortwave_radiation"] = rng.uniform(0, 500, len(d)); d["w_cloud_cover"] = rng.uniform(0, 100, len(d))
        d["zone"] = z; d["split"] = "test"; rows.append(d)
    return pd.concat(rows).rename_axis("timestamp_utc").reset_index().dropna(subset=["lag_336h"])

def run(args):
    lock = gate(args)
    te = dummy_frame() if args.dummy else pd.read_parquet(SEALED)            # <- the ONLY place the sealed file is read
    te = te.dropna(subset=["lag_336h", "lag_168h", "load_mw"]).copy(); f = feats(True, False)
    off = json.load(open(MODELS / "cqr_offsets.json"))["offsets"]; rows, bands, hrs, subs = [], [], [], []
    for z in ZONES:
        v = te[te.zone == z].reset_index(drop=True); y = v.load_mw.values
        mean = lgb.Booster(model_file=str(MODELS / f"{z}_mean.txt")).predict(v[f])
        Q = np.sort(np.column_stack([lgb.Booster(model_file=str(MODELS / f"{z}_q{a}.txt")).predict(v[f]) for a in QS]), axis=1)
        q = dict(zip(QS, Q.T)); base = {"B0_yesterday": v.lag_24h.values, "B1_last_week": v.lag_168h.values, "M2_mean_model": mean, "q50_median": q[0.5]}
        for name, p in base.items(): rows.append(dict(zone=z, model=name, n=len(v), MAE=mae(y, p), RMSE=rmse(y, p), MAPE=mape(y, p)))
        for k, m in subsets(v).items():   # same definitions as rule v2: holiday, hottest/coldest 5% of days (ranked inside the test period)
            if m.sum(): subs.append(dict(zone=z, subset=k, n_hours=int(m.sum()), MAE_model=mae(y[m], mean[m]), MAE_B1=mae(y[m], v.lag_168h.values[m])))
        for b, (la, ha, nom) in BANDS.items():
            for method, o in [("raw", 0.0), ("cqr", off[f"{z}_{b}"])]:
                lo, hi = q[la] - o, q[ha] + o; inn = (y >= lo) & (y <= hi)
                bands.append(dict(zone=z, band=b, method=method, nominal=nom, coverage=float(inn.mean()), width=float((hi - lo).mean())))
                if method == "cqr":
                    for h, s in pd.Series(inn).groupby(v.hour.values).mean().items(): hrs.append(dict(zone=z, band=b, hour=h, coverage=float(s)))
    R = pd.DataFrame(rows); B = pd.DataFrame(bands); H = pd.DataFrame(hrs); S = pd.DataFrame(subs)
    OUT = Path(args.out_dir) if args.out_dir else OUTDIR
    if args.dummy and not args.out_dir: refuse(5, "--dummy needs --out-dir (outputs must not go to results/).")
    OUT.mkdir(parents=True, exist_ok=True); tag = "dummy" if args.dummy else "final_test"
    R.to_csv(OUT / f"{tag}_metrics.csv", index=False); B.to_csv(OUT / f"{tag}_coverage.csv", index=False); H.to_csv(OUT / f"{tag}_coverage_by_hour.csv", index=False); S.to_csv(OUT / f"{tag}_subsets.csv", index=False)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = dict(run_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), git_head=head, dummy=args.dummy, n_rows=len(te),
                test_start=str(te.timestamp_utc.min()), test_end=str(te.timestamp_utc.max()), model_lock_sha256_of_lockfile=sha(LOCK))
    json.dump(meta, open(OUT / f"{tag}_meta.json", "w"), indent=1)
    if not args.dummy: DONE.write_text(json.dumps(meta, indent=1))
    print(R.round(1).to_string(index=False)); print(S.round(1).to_string(index=False)); print(B.round(3).to_string(index=False)); return R, B, H

def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--confirm-final", action="store_true"); ap.add_argument("--dummy", action="store_true"); ap.add_argument("--out-dir")
    return run(ap.parse_args(argv))

if __name__ == "__main__": main()
