"""Phase 7: hourly forecasts for validation + test with the LOCKED models -> site/data/{zone}.json (+ meta.json).
Computes NO error metrics. Verifies the model lock and that the final evaluation has been run."""
import sys, json, hashlib, subprocess; sys.path.insert(0, "src")
from pathlib import Path
import numpy as np, pandas as pd, lightgbm as lgb
from gepf.data import ZONES, PROC
from gepf.models import feats
from gepf.quant import QS
MODELS, LOCK, DONE, OUT = Path("models"), Path("results/model_lock.json"), Path("results/FINAL_EVAL_DONE"), Path("site/data")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
lock = json.load(open(LOCK))["sha256"]
assert DONE.exists(), "final evaluation has not been run"
assert set(lock) == {p.name for p in MODELS.iterdir() if p.suffix in (".txt", ".json")} and all(sha(MODELS / n) == h for n, h in lock.items()), "model lock mismatch"
bi = json.load(open(PROC / "build_info.json")); VAL0, TEST0 = pd.Timestamp(bi["val_start"]), pd.Timestamp(bi["test_start"])
df = pd.concat([pd.read_parquet(PROC / "trainval.parquet").query("split == 'val'"), pd.read_parquet(PROC / "sealed_test.parquet")])
need = ["lag_336h", "lag_168h", "load_mw"]; f = feats(True, False)
off = json.load(open(MODELS / "cqr_offsets.json"))["offsets"]; OUT.mkdir(parents=True, exist_ok=True)
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
summary = {}
for z in ZONES:
    d = df[df.zone == z].sort_values("timestamp_utc"); total = len(d); d = d.dropna(subset=need).reset_index(drop=True)
    mean = lgb.Booster(model_file=str(MODELS / f"{z}_mean.txt")).predict(d[f])
    Q = dict(zip(QS, np.sort(np.column_stack([lgb.Booster(model_file=str(MODELS / f"{z}_q{a}.txt")).predict(d[f]) for a in QS]), axis=1).T))
    loc = d.timestamp_utc.dt.tz_convert("Europe/Berlin"); day = loc.dt.strftime("%Y-%m-%d")
    cols = dict(a=d.load_mw.values, f=mean, l80=Q[0.1] - off[f"{z}_80"], u80=Q[0.9] + off[f"{z}_80"], l95=Q[0.025] - off[f"{z}_95"], u95=Q[0.975] + off[f"{z}_95"])
    days = {}
    for dd, idx in d.groupby(day.values).groups.items():
        idx = np.array(sorted(idx)); r = lambda v: [round(float(x), 1) for x in v[idx]]
        days[dd] = dict(h=[int(x) for x in loc.dt.hour.values[idx]], t=[x.strftime("%Y-%m-%dT%H:00Z") for x in d.timestamp_utc.dt.tz_convert("UTC").iloc[idx]],
                        s=[int(x) for x in (d.timestamp_utc.values[idx] >= np.datetime64(TEST0.tz_convert("UTC").tz_localize(None))).astype(int)], **{k: r(v) for k, v in cols.items()})
    json.dump(dict(zone=z, unit="MWh per hour (= average MW)", days=days), open(OUT / f"{z}.json", "w"), separators=(",", ":"))
    summary[z] = dict(hours_exported=len(d), hours_in_period=total, hours_left_out=total - len(d))
cov = pd.read_csv("results/final_test_coverage.csv", dtype={"band": str}); c = cov[cov.method == "cqr"]
meta = dict(val_start=str(VAL0), test_start=str(TEST0), first_full_local_day="2024-10-26", last_full_local_day="2026-10-24",
            test_coverage_cqr_mean={b: round(float(c[c.band == b].coverage.mean()) * 100, 1) for b in ("80", "95")},
            test_coverage_cqr_by_zone={z: {b: round(float(c[(c.zone == z) & (c.band == b)].coverage.iloc[0]) * 100, 1) for b in ("80", "95")} for z in ZONES},
            hours=summary, git_head=head, model_lock_file_sha256=sha(LOCK))
json.dump(meta, open(OUT / "meta.json", "w"), indent=1); print(json.dumps(meta, indent=1))
