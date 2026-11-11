"""SECOND use of the sealed test year (2025-10-25..2026-10-24), for the future-horizon model family. Run ONCE:
    python scripts/final_eval_future.py --confirm-final
Gate order (nothing touches the sealed file before all pass):
 1. --confirm-final must be given, otherwise exit 2.
 2. results/FINAL_EVAL_FUTURE_DONE must not exist (unless --dummy), otherwise exit 3.
 3. SHA-256 of every file in models_future/ must equal results/model_lock_future.json, otherwise exit 4.
--dummy uses synthetic data (never reads the sealed file, never writes the DONE marker) and needs --out-dir."""
import sys, json, hashlib, argparse, subprocess, datetime
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from pathlib import Path
import numpy as np, pandas as pd, lightgbm as lgb
from gepf.data import ZONES, PROC
from gepf.quant import QS, BANDS
from gepf.evalutil import mae
from gepf import horizon as H

SEALED = PROC / "sealed_test.parquet"; DONE = Path("results/FINAL_EVAL_FUTURE_DONE")
LOCK = Path("results/model_lock_future.json"); MODELS = Path("models_future"); OUTDIR = Path("results")
ARCHIVE = Path("data/raw/forecast_archive.parquet")

def refuse(code, msg): print("REFUSED:", msg, file=sys.stderr); sys.exit(code)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def gate(args):
    if not args.confirm_final: refuse(2, "--confirm-final is required.")
    if not args.dummy and DONE.exists(): refuse(3, f"{DONE} exists: already run.")
    lock = json.load(open(LOCK))["sha256"]; have = {p.name for p in MODELS.iterdir() if p.suffix in (".txt", ".json")}
    if set(lock) != have: refuse(4, f"model files differ from lock: {sorted(set(lock) ^ have)[:5]}")
    bad = [n for n, h in lock.items() if sha(MODELS / n) != h]
    if bad: refuse(4, f"SHA-256 mismatch for {bad[:5]}")

def dummy_inputs():
    rng = np.random.default_rng(0); idx = pd.date_range("2030-01-01", periods=24 * 120, freq="h", tz="UTC"); loads, rows = {}, []
    for z in ZONES:
        loc = idx.tz_convert("Europe/Berlin")
        loads[z] = pd.Series(10000 + 3000 * np.sin(2 * np.pi * loc.hour / 24) + 1500 * (loc.day_of_week >= 5) + rng.normal(0, 200, len(idx)), index=idx)
        a = pd.DataFrame({f"{v}{s}": rng.normal(5, 3, len(idx)) for v in H.BASE_VARS for s in [""] + [f"_previous_day{k}" for k in range(1, 8)]})
        a["timestamp_utc"] = idx; a["zone"] = z; rows.append(a)
    return loads, pd.concat(rows), idx[0] + pd.Timedelta(days=45), idx[-1]

def real_inputs():
    bi = json.load(open(PROC / "build_info.json")); test0 = pd.Timestamp(bi["test_start"])
    tv = pd.read_parquet(PROC / "trainval.parquet")
    te = pd.read_parquet(SEALED)                              # <- the ONLY place the sealed file is read
    both = pd.concat([tv, te]); loads = {}
    for z in ZONES:
        s = both[both.zone == z].set_index("timestamp_utc")["load_mw"].sort_index()
        loads[z] = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="h", tz="UTC"))
    return loads, pd.read_parquet(ARCHIVE), test0, te.timestamp_utc.max()

def run(args):
    gate(args)
    import run_horizon_models as R
    loads, arch, t0, t1 = dummy_inputs() if args.dummy else real_inputs()
    sel = json.load(open("results/horizon_selection.json")); cj = json.load(open(MODELS / "cqr_offsets_future.json")); off = cj["offsets"]
    rows, bands = [], []
    for z in ZONES:
        for k in H.HORIZONS + H.OUTLOOK:
            cfg = sel["choice"][f"{z}|{k}"]; X, f = R.frame_for(z, loads[z], k, cfg, arch); assert f == cj["features"][f"{z}|{k}"]["features"]
            need = [f"lag_{H.shift_hours(k)}h", f"lag_{H.week_lag(k)}h", "load_mw"] + [c for c in f if c.startswith("w_")]
            v = X.dropna(subset=need); v = v[(v.index >= t0) & (v.index <= t1)]; y = v.load_mw.values
            mean = lgb.Booster(model_file=str(MODELS / f"{z}_k{k}_mean.txt")).predict(v[f])
            q = dict(zip(QS, np.sort(np.column_stack([lgb.Booster(model_file=str(MODELS / f"{z}_k{k}_q{a}.txt")).predict(v[f]) for a in QS]), axis=1).T))
            r = dict(zone=z, k=k, config=cfg, n=len(v), MAE_model=mae(y, mean))
            for c in ("B_day", "B_week", "B_wk4avg"):
                ok = ~np.isnan(v[c].values); r[f"MAE_{c}"] = mae(y[ok], v[c].values[ok]) if ok.any() else np.nan
            best = min(r["MAE_B_day"], r["MAE_B_week"]); r["MAE_best_simple_baseline"] = best; r["gain_vs_best_baseline"] = 1 - r["MAE_model"] / best; rows.append(r)
            for b, (la, ha, nom) in BANDS.items():
                for method, o in (("raw", 0.0), ("cqr", off[f"{z}|{k}|{b}"])):
                    lo, hi = q[la] - o, q[ha] + o
                    bands.append(dict(zone=z, k=k, band=b, method=method, nominal=nom, coverage=float(((y >= lo) & (y <= hi)).mean()), width=float((hi - lo).mean())))
    R_, B_ = pd.DataFrame(rows), pd.DataFrame(bands)
    OUT = Path(args.out_dir) if args.out_dir else OUTDIR
    if args.dummy and not args.out_dir: refuse(5, "--dummy needs --out-dir.")
    OUT.mkdir(parents=True, exist_ok=True); tag = "dummy_future" if args.dummy else "future_test"
    R_.to_csv(OUT / f"{tag}_metrics.csv", index=False); B_.to_csv(OUT / f"{tag}_coverage.csv", index=False)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = dict(run_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), git_head=head, dummy=args.dummy, test_start=str(t0), test_end=str(t1), lock_file_sha256=sha(LOCK))
    json.dump(meta, open(OUT / f"{tag}_meta.json", "w"), indent=1)
    if not args.dummy: DONE.write_text(json.dumps(meta, indent=1))
    print(R_.round(3).to_string(index=False)); print(B_[B_.method == "cqr"].round(3).to_string(index=False))

def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--confirm-final", action="store_true"); ap.add_argument("--dummy", action="store_true"); ap.add_argument("--out-dir")
    return run(ap.parse_args(argv))

if __name__ == "__main__": main()
