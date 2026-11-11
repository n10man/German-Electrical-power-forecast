"""Generate the FUTURE forecast snapshot (run by hand; no scheduler, no network except reading local files).
Inputs : data/raw/load_*.parquet (SMARD, latest download), the newest data/raw/forecast_current_*.parquet, models_future/ (SHA-256 verified).
Outputs: site/data/future/{zone}.json, site/data/future_meta.json, results/prospective/forecast_<origin>_<generated>.json (the dated log to be scored later).
The forecast origin is the last hour for which all four zones have actual load. Nothing here computes error metrics; accuracy numbers on the page are copied from results/*.csv."""
import sys, json, hashlib, subprocess, math, argparse
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from pathlib import Path
import numpy as np, pandas as pd, lightgbm as lgb
from gepf.data import ZONES, load_hourly
from gepf.quant import QS
from gepf import horizon as H

MODELS, LOCK, DONE = Path("models_future"), Path("results/model_lock_future.json"), Path("results/FINAL_EVAL_FUTURE_DONE")
SITE = Path("site/data"); sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
MAX_DAYS = 21

def verify():
    assert DONE.exists(), "sealed evaluation of the future models has not been run"
    lock = json.load(open(LOCK))["sha256"]
    assert set(lock) == {p.name for p in MODELS.iterdir() if p.suffix in (".txt", ".json")} and all(sha(MODELS / n) == h for n, h in lock.items()), "model lock mismatch"

def current_weather(path):
    w = pd.read_parquet(path); stamp = w.downloaded_utc.iloc[0]; out = {}
    for z in ZONES:
        m = w[w.zone == z].drop(columns=["zone", "point", "downloaded_utc"]).groupby("timestamp_utc").mean()
        m.columns = [f"w_{c}" for c in m.columns]; out[z] = m
    return out, stamp

def accuracy_table(sel):
    v = pd.read_csv("results/horizon_selection.csv").set_index(["zone", "k"]); cv = pd.read_csv("results/horizon_coverage_val.csv", dtype={"band": str})
    cv = cv[cv.swap.isin(["A->B", "B->A"])]; tm = pd.read_csv("results/future_test_metrics.csv").set_index(["zone", "k"])
    tc = pd.read_csv("results/future_test_coverage.csv", dtype={"band": str}); tc = tc[tc.method == "cqr"].set_index(["zone", "k", "band"]).coverage
    acc = {}
    for z in ZONES:
        for k in H.HORIZONS + H.OUTLOOK:
            r = v.loc[(z, k)]; c = cv[(cv.zone == z) & (cv.k == k)]; t = tm.loc[(z, k)]
            acc[f"{z}|{k}"] = dict(config=r.config, shown=bool(r.passes), val_mae=round(r.mae), val_baseline_mae=round(r.baseline_mae), val_gain_pct=round(100 * r.gain_vs_baseline),
                                   val_cov80_swapped_mean=round(100 * c[c.band == "80"].coverage.mean(), 1), val_cov80_swapped_min=round(100 * c[c.band == "80"].coverage.min(), 1),
                                   val_cov95_swapped_mean=round(100 * c[c.band == "95"].coverage.mean(), 1), val_cov95_swapped_min=round(100 * c[c.band == "95"].coverage.min(), 1),
                                   test_mae=round(t.MAE_model), test_baseline_mae=round(t.MAE_best_simple_baseline), test_gain_pct=round(100 * t.gain_vs_best_baseline),
                                   test_cov80=round(100 * tc[(z, k, "80")], 1), test_cov95=round(100 * tc[(z, k, "95")], 1))
    return acc

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--weather"); a = ap.parse_args(); verify()
    wpath = Path(a.weather) if a.weather else sorted(Path("data/raw").glob("forecast_current_*.parquet"))[-1]; wx, wstamp = current_weather(wpath)
    loads = {z: load_hourly(z)[0] for z in ZONES}
    origin = min(s.dropna().index.max() for s in loads.values())            # last hour with actual load in ALL four zones
    known = {z: s[s.index <= origin] for z, s in loads.items()}
    targets = pd.date_range(origin + pd.Timedelta(hours=1), periods=24 * MAX_DAYS, freq="h", tz="UTC")
    delta = np.arange(1, len(targets) + 1); dday = np.ceil(delta / 24).astype(int); kmod = np.array([H.day_to_model(int(d)) for d in dday])
    sel = json.load(open("results/horizon_selection.json")); cj = json.load(open(MODELS / "cqr_offsets_future.json")); off = cj["offsets"]
    include_outlook = bool(sel["outlook_21_included"]); acc = accuracy_table(sel)
    generated = pd.Timestamp.now("UTC"); head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    zones_out, log, dropped = {}, {}, {}
    for z in ZONES:
        parts = []
        for k in H.HORIZONS + H.OUTLOOK:
            m = kmod == k; tk = targets[m]
            if not acc[f"{z}|{k}"]["shown"] or (k == 21 and not include_outlook): continue
            f = cj["features"][f"{z}|{k}"]["features"]; X = H.future_frame(z, known[z], k, tk, wx[z] if any(c.startswith("w_") for c in f) else None)
            need = [f"lag_{H.shift_hours(k)}h", f"lag_{H.week_lag(k)}h"] + [c for c in f if c.startswith("w_")]
            X = X.dropna(subset=need); dropped[f"{z}|{k}"] = int(m.sum() - len(X))
            P = {q: lgb.Booster(model_file=str(MODELS / f"{z}_k{k}_q{q}.txt")).predict(X[f]) for q in QS}
            Q = dict(zip(QS, np.sort(np.column_stack([P[q] for q in QS]), axis=1).T))
            mean = lgb.Booster(model_file=str(MODELS / f"{z}_k{k}_mean.txt")).predict(X[f]); o80, o95 = off[f"{z}|{k}|80"], off[f"{z}|{k}|95"]
            lo80, hi80, lo95, hi95 = Q[0.1] - o80, Q[0.9] + o80, Q[0.025] - o95, Q[0.975] + o95
            # keep the point forecast inside its own ranges (the mean model and the quantile models are separate fits)
            parts.append(pd.DataFrame(dict(f=mean, l80=np.minimum(lo80, mean), u80=np.maximum(hi80, mean), l95=np.minimum(lo95, mean), u95=np.maximum(hi95, mean),
                                           k=k, d=[int(math.ceil((t - origin) / pd.Timedelta(hours=1) / 24)) for t in X.index]), index=X.index))
        D = pd.concat(parts).sort_index(); D["l95"] = np.minimum(D.l95, D.l80); D["u95"] = np.maximum(D.u95, D.u80)
        P_ = D[D.index > generated.floor("h")]       # the map shows only hours that have not started when the snapshot is made; the dated log keeps all hours from the origin on
        loc = P_.index.tz_convert("Europe/Berlin"); day = loc.strftime("%Y-%m-%d"); days = {}
        for dd in sorted(set(day)):
            idx = np.where(day == dd)[0]; r = lambda c: [round(float(x), 1) for x in P_[c].values[idx]]
            days[dd] = dict(h=[int(x) for x in loc.hour.values[idx]], t=[x.strftime("%Y-%m-%dT%H:00Z") for x in P_.index[idx]], k=[int(x) for x in P_.k.values[idx]], d=[int(x) for x in P_.d.values[idx]],
                            **{c: r(c) for c in ("f", "l80", "u80", "l95", "u95")})
        zones_out[z] = days; (SITE / "future").mkdir(parents=True, exist_ok=True)
        json.dump(dict(zone=z, unit="MWh per hour (= average MW)", days=days), open(SITE / "future" / f"{z}.json", "w"), separators=(",", ":"))
        log[z] = dict(t=[x.strftime("%Y-%m-%dT%H:00Z") for x in D.index], **{c: [round(float(x), 1) for x in D[c].values] for c in ("f", "l80", "u80", "l95", "u95")}, k=[int(x) for x in D.k], d=[int(x) for x in D.d])
    firsts = [min(d) for d in zones_out.values()]; lasts = [max(d) for d in zones_out.values()]
    meta = dict(generated_utc=generated.strftime("%Y-%m-%d %H:%M"), origin_utc=origin.strftime("%Y-%m-%d %H:%M"), weather_downloaded_utc=wstamp[:16].replace("T", " "),
                covers_first_utc=min(pd.Timestamp(v["t"][0]) for d in zones_out.values() for v in d.values()).strftime("%Y-%m-%d %H:%M"), covers_last_utc=max(pd.Timestamp(v["t"][-1]) for d in zones_out.values() for v in d.values()).strftime("%Y-%m-%d %H:%M"), covers_first_local_date=min(firsts), covers_last_local_date=max(lasts), forecast_days=16, outlook_included=include_outlook, outlook_first_day=17,
                outlook_starts_utc=(origin + pd.Timedelta(hours=24 * 16 + 1)).strftime("%Y-%m-%d %H:%M"),
                weather_used_up_to_day=H.WEATHER_MAX_K, hours_dropped_missing_inputs=dropped, accuracy=acc, git_head=head, model_lock_file_sha256=sha(LOCK))
    json.dump(meta, open(SITE / "future_meta.json", "w"), indent=1)
    Path("results/prospective").mkdir(parents=True, exist_ok=True)
    json.dump(dict(meta=dict(generated_utc=generated.isoformat(), origin_utc=origin.isoformat(), weather_file=wpath.name, git_head=head, model_lock_file_sha256=sha(LOCK), unit="MWh/h"), forecast=log),
              open(f"results/prospective/forecast_{origin.strftime('%Y%m%dT%H')}_{generated.strftime('%Y%m%dT%H%M%SZ')}.json", "w"), separators=(",", ":"))
    print(json.dumps({k: v for k, v in meta.items() if k != "accuracy"}, indent=1))

if __name__ == "__main__":
    main()
