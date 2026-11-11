"""Score a saved forecast log (results/prospective/forecast_*.json) against actual load once those hours have happened.
Run LATER, after re-downloading SMARD load (python scripts/download_load.py after moving the old raw load files away):
    python scripts/compare_prospective.py results/prospective/forecast_<...>.json [--out results/prospective/score_<...>.csv]
Per zone and model horizon k: hours scored, MAE, MAE of the same-hour-last-week baseline (latest known week from the origin), coverage of the 80% and 95% ranges.
Hours without actual load yet are skipped and counted. This script only reads the log and the raw load files; it fetches nothing."""
import sys, json, argparse, math
sys.path.insert(0, "src")
from pathlib import Path
import numpy as np, pandas as pd

def score(log: dict, loads: dict) -> pd.DataFrame:
    origin = pd.Timestamp(log["meta"]["origin_utc"]); rows = []
    for z, f in log["forecast"].items():
        t = pd.to_datetime(f["t"], utc=True); df = pd.DataFrame({k: f[k] for k in ("f", "l80", "u80", "l95", "u95", "k")}, index=t)
        y = loads[z].reindex(t); df["y"] = y.values
        wk = 168 * np.ceil(24 * df.k.values / 168)                     # same weekday/hour of the latest week known at the origin (same cutoff as model k)
        df["base"] = [loads[z].get(ti - pd.Timedelta(hours=int(w)), np.nan) for ti, w in zip(t, wk)]
        n_all = df.groupby("k").size()
        d = df.dropna(subset=["y"])
        for k, g in d.groupby("k"):
            b = g.dropna(subset=["base"])
            rows.append(dict(zone=z, k=k, hours_scored=len(g), hours_in_log=int(n_all[k]), MAE=float(np.abs(g.f - g.y).mean()),
                             MAE_baseline_last_week=float(np.abs(b.base - b.y).mean()) if len(b) else np.nan,
                             cov80=float(((g.y >= g.l80) & (g.y <= g.u80)).mean()), cov95=float(((g.y >= g.l95) & (g.y <= g.u95)).mean())))
    return pd.DataFrame(rows)

def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("log"); ap.add_argument("--out"); a = ap.parse_args(argv)
    from gepf.data import ZONES, load_hourly
    log = json.load(open(a.log)); loads = {z: load_hourly(z)[0] for z in ZONES}
    S = score(log, loads); print(S.round(3).to_string(index=False))
    if a.out: S.to_csv(a.out, index=False)
    return S

if __name__ == "__main__":
    main()
