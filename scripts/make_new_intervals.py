"""Apply the interval method selected in I1 (results/interval_selection.json) to the EXISTING future snapshot, without touching the locked models,
the past-date files or the original dated log.  python scripts/make_new_intervals.py
- Rebuilds the raw quantile and mean predictions of the snapshot from the same inputs (origin, weather file named in the log) and checks that the point
  forecasts equal the logged ones.
- Calibration scores: ONLY hours after the sealed period (>= 2026-10-25 00:00 UTC) up to the origin, rolling window of N weeks, the formula of gepf.quant.cqr_offset;
  a cell with fewer than MIN_HOURS scores keeps its static offsets (rules: results/EXPERIMENTS.md entry I1).
- Writes results/interval_calibration_<method>.json, results/interval_lock.json (SHA-256), results/prospective/intervals_<method>_<stamp>.json (the new ranges for the
  same forecast, next to the original log) and updates the range columns of site/data/future/*.json and site/data/future_meta.json."""
import sys, json, hashlib, math, re
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from pathlib import Path
import numpy as np, pandas as pd, lightgbm as lgb
from gepf.data import ZONES, load_hourly
from gepf.quant import QS, BANDS
from gepf import horizon as H
import make_future_forecast as M
import run_horizon_models as R

AFTER_SEALED = pd.Timestamp("2026-10-25 00:00", tz="UTC"); MIN_HOURS = 168
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def offset(scores, nom):
    sc = np.asarray(scores, float); sc = sc[~np.isnan(sc)]; n = len(sc)
    if n == 0: return None
    q = min(1.0, math.ceil((n + 1) * nom) / n); return float(np.quantile(sc, q, method="higher"))

def raw_pred(z, k, X, f):
    P = np.sort(np.column_stack([lgb.Booster(model_file=str(M.MODELS / f"{z}_k{k}_q{q}.txt")).predict(X[f]) for q in QS]), axis=1)
    return pd.DataFrame(P, index=X.index, columns=QS)

def main(log_path=None, method=None):
    sel = json.load(open("results/interval_selection.json")); method = method or sel["selected"]
    if method == "static": sys.exit("static method selected in I1: nothing to apply")
    weeks = int(re.fullmatch(r"rolling_(\d+)w", method).group(1))
    M.verify(); log_path = Path(log_path or sorted(Path("results/prospective").glob("forecast_*.json"))[0]); log = json.load(open(log_path)); stamp = log_path.stem.replace("forecast_", "")
    origin = pd.Timestamp(log["meta"]["origin_utc"]); wx, _ = M.current_weather(Path("data/raw") / log["meta"]["weather_file"])
    cj = json.load(open(M.MODELS / "cqr_offsets_future.json")); off = cj["offsets"]; chs = json.load(open("results/horizon_selection.json"))["choice"]
    arch = pd.read_parquet(R.ARCHIVE); loads = {z: load_hourly(z)[0] for z in ZONES}
    calib, newlog, ident = {}, {}, []
    for z in ZONES:
        full = loads[z]; known = full[full.index <= origin]; t = pd.to_datetime(log["forecast"][z]["t"], utc=True); kk = np.array(log["forecast"][z]["k"]); parts = []
        for k in sorted(set(kk)):
            f = cj["features"][f"{z}|{k}"]["features"]; tk = t[kk == k]
            Xs = H.future_frame(z, known, k, tk, wx[z] if any(c.startswith("w_") for c in f) else None).dropna(subset=[f"lag_{H.shift_hours(k)}h", f"lag_{H.week_lag(k)}h"] + [c for c in f if c.startswith("w_")])
            Q = raw_pred(z, k, Xs, f); mean = pd.Series(lgb.Booster(model_file=str(M.MODELS / f"{z}_k{k}_mean.txt")).predict(Xs[f]), index=Xs.index)
            ident.append(float(np.abs(np.round(mean.values, 1) - np.array(log["forecast"][z]["f"])[np.isin(t, Xs.index) & (kk == k)]).max()))
            # calibration scores: hours after the sealed period, known at the origin, model k's own predictions
            Xh, _ = R.frame_for(z, full, k, chs[f"{z}|{k}"], arch); Xh = Xh.dropna(subset=[f"lag_{H.shift_hours(k)}h", f"lag_{H.week_lag(k)}h", "load_mw"] + [c for c in f if c.startswith("w_")])
            Xh = Xh[(Xh.index >= AFTER_SEALED) & (Xh.index <= origin)]; Qh = raw_pred(z, k, Xh, f); y = Xh.load_mw
            lo_win = origin - pd.Timedelta(weeks=weeks)
            out = pd.DataFrame(index=Xs.index)
            for b, (la, ha, nom) in BANDS.items():
                s = np.maximum(Qh[la].values - y.values, y.values - Qh[ha].values); s = pd.Series(s, index=Xh.index); s = s[s.index > lo_win]
                c = offset(s, nom) if len(s) >= MIN_HOURS else None; fallback = c is None; c = off[f"{z}|{k}|{b}"] if fallback else c
                calib[f"{z}|{k}|{b}"] = dict(offset=c, static_offset=off[f"{z}|{k}|{b}"], n_scores=int(len(s)), fallback_to_static=fallback, first_score=str(s.index.min()), last_score=str(s.index.max()))
                out[f"lo{b}"], out[f"hi{b}"] = Q[la] - c, Q[ha] + c
            d = pd.DataFrame(dict(f=mean, l80=np.minimum(out.lo80, mean), u80=np.maximum(out.hi80, mean), l95=np.minimum(out.lo95, mean), u95=np.maximum(out.hi95, mean)), index=Xs.index); parts.append(d)
        D = pd.concat(parts).sort_index(); D["l95"] = np.minimum(D.l95, D.l80); D["u95"] = np.maximum(D.u95, D.u80)
        newlog[z] = D.reindex(t)
    assert max(ident) < 0.11, f"point forecasts differ from the log by {max(ident)}"      # same inputs, same models -> same forecast
    cal = dict(method=method, window_weeks=weeks, origin_utc=str(origin), scores_only_after=str(AFTER_SEALED), min_hours=MIN_HOURS, cells=calib,
               original_log=log_path.name, original_log_sha256=sha(log_path), interval_selection_sha256=sha("results/interval_selection.json"), validation_summary_sha256=sha("results/interval_val_summary.csv"), script_sha256=sha(__file__))
    cp = Path(f"results/interval_calibration_{method}.json"); json.dump(cal, open(cp, "w"), indent=1)
    json.dump({"sha256": {cp.name: sha(cp), "interval_selection.json": sha("results/interval_selection.json"), "interval_val_summary.csv": sha("results/interval_val_summary.csv")}}, open("results/interval_lock.json", "w"), indent=1)
    nl = {z: {c: [None if pd.isna(v) else round(float(v), 1) for v in newlog[z][c]] for c in ("l80", "u80", "l95", "u95")} | {"t": log["forecast"][z]["t"], "k": log["forecast"][z]["k"], "d": log["forecast"][z]["d"], "f": log["forecast"][z]["f"]} for z in ZONES}
    ip = log_path.with_name(f"intervals_{method}_{stamp}.json")
    json.dump(dict(meta=dict(method=method, same_forecast_as=log_path.name, original_log_sha256=sha(log_path), calibration_file=cp.name, unit="MWh/h"), forecast=nl), open(ip, "w"), separators=(",", ":"))
    n_fb = sum(v["fallback_to_static"] for v in calib.values()); print("cells", len(calib), "fallback", n_fb, "max point diff", max(ident), "->", ip)
    # site: replace only the range columns for the published hours; the point forecast stays
    for z in ZONES:
        p = Path("site/data/future") / f"{z}.json"; j = json.load(open(p)); idx = {x: i for i, x in enumerate(nl[z]["t"])}
        for day in j["days"].values():
            ii = [idx[x] for x in day["t"]]
            for c in ("l80", "u80", "l95", "u95"): day[c] = [nl[z][c][i] for i in ii]
        json.dump(j, open(p, "w"), separators=(",", ":"))
    fm = json.load(open("site/data/future_meta.json")); S = pd.read_csv("results/interval_val_summary.csv").set_index("candidate").loc[method]
    fm["interval_method"] = dict(name=method, window_weeks=weeks, scores_after=str(AFTER_SEALED), validation_cov80=round(float(S.mean_coverage_80), 1), validation_cov95=round(float(S.mean_coverage_95), 1), calibration_sha256=sha(cp), cells_fallback_to_static=n_fb)
    json.dump(fm, open("site/data/future_meta.json", "w"), indent=1)

if __name__ == "__main__":
    main()
