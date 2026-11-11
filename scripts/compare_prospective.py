"""Score the pre-registered future forecast against the actual load once those hours have happened (the PROSPECTIVE CHECK). Run on or after about 2026-12-05
(SMARD load lags by a few days; the forecast covers up to 2026-12-01 07:00 UTC). Not run on real data before that.

  First update the SMARD load files (python scripts/download_load.py after moving the old raw load files away), then:
  python scripts/compare_prospective.py results/prospective/forecast_<...>.json [--intervals results/prospective/intervals_<method>_<...>.json] [--update-readme]

Per zone and horizon bucket (days ahead 1, 2-3, 4-7, 8-14, 15-16, 17-21) it reports hours scored, MAE, MAE of the simple same-hour-last-week baseline, coverage of the
80% / 95% ranges of the original (static) method and, if --intervals is given, of the new method on the same hours, plus mean widths. Hours without an actual yet are
skipped and counted. Writes results/prospective_results.md and results/prospective_results.csv; --update-readme replaces the table between the PROSPECTIVE markers in README.md.
It only reads the log, the optional intervals file and the raw load files; it fetches nothing."""
import sys, json, argparse
sys.path.insert(0, "src")
from pathlib import Path
import numpy as np, pandas as pd

BUCKETS = [(1, 1, "1"), (2, 3, "2-3"), (4, 7, "4-7"), (8, 14, "8-14"), (15, 16, "15-16"), (17, 21, "17-21")]
def bucket(d):
    for a, b, name in BUCKETS:
        if a <= d <= b: return name
    return "other"

def score(log: dict, loads: dict, intervals: dict | None = None, by: str = "k") -> pd.DataFrame:
    """by='k': one row per zone and horizon model k; by='bucket': per zone and days-ahead bucket. A zone with no actual hours at all gives no rows."""
    rows = []
    for z, f in log["forecast"].items():
        t = pd.to_datetime(f["t"], utc=True); df = pd.DataFrame({c: f[c] for c in ("f", "l80", "u80", "l95", "u95", "k", "d")}, index=t)
        if intervals is not None and z in intervals["forecast"]:
            for c in ("l80", "u80", "l95", "u95"): df[c + "_new"] = pd.to_numeric(pd.Series(intervals["forecast"][z][c], index=t, dtype="float64"))
        df["y"] = loads[z].reindex(t).values
        wk = 168 * np.ceil(24 * df.k.values / 168)                     # same weekday/hour of the latest week known at the origin (same cutoff as model k)
        df["base"] = [loads[z].get(ti - pd.Timedelta(hours=int(w)), np.nan) for ti, w in zip(t, wk)]
        df["grp"] = df.k if by == "k" else df.d.map(bucket); n_all = df.groupby("grp").size(); d = df.dropna(subset=["y"])
        for g, h in d.groupby("grp", sort=False):
            b = h.dropna(subset=["base"]); r = dict(zone=z, **{"k" if by == "k" else "days_ahead": g}, hours_scored=len(h), hours_in_log=int(n_all[g]), MAE=float(np.abs(h.f - h.y).mean()),
                MAE_baseline_last_week=float(np.abs(b.base - b.y).mean()) if len(b) else np.nan,
                cov80=float(((h.y >= h.l80) & (h.y <= h.u80)).mean()), cov95=float(((h.y >= h.l95) & (h.y <= h.u95)).mean()), width80=float((h.u80 - h.l80).mean()), width95=float((h.u95 - h.l95).mean()))
            if "l80_new" in h:
                hn = h.dropna(subset=["l80_new", "u80_new", "l95_new", "u95_new"])
                r.update(cov80_new=float(((hn.y >= hn.l80_new) & (hn.y <= hn.u80_new)).mean()), cov95_new=float(((hn.y >= hn.l95_new) & (hn.y <= hn.u95_new)).mean()),
                         width80_new=float((hn.u80_new - hn.l80_new).mean()), width95_new=float((hn.u95_new - hn.l95_new).mean()))
            rows.append(r)
    return pd.DataFrame(rows)

def markdown(S: pd.DataFrame, meta: dict, n_missing: int) -> str:
    new = "cov80_new" in S
    head = ["zone", "days ahead", "hours scored / in log", "MAE", "baseline MAE (last week)", "80% cov.", "95% cov."] + (["80% cov. (new)", "95% cov. (new)"] if new else [])
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for _, r in S.iterrows():
        cells = [r.zone, str(r.days_ahead), f"{r.hours_scored} / {r.hours_in_log}", f"{r.MAE:,.0f}", "n/a" if np.isnan(r.MAE_baseline_last_week) else f"{r.MAE_baseline_last_week:,.0f}", f"{100 * r.cov80:.1f}%", f"{100 * r.cov95:.1f}%"]
        if new: cells += [f"{100 * r.cov80_new:.1f}%", f"{100 * r.cov95_new:.1f}%"]
        out.append("| " + " | ".join(cells) + " |")
    pooled = S.assign(w=S.hours_scored)
    tot = f"\nPooled over all rows: MAE {np.average(S.MAE, weights=S.hours_scored):,.0f} vs baseline {np.average(S.MAE_baseline_last_week.fillna(S.MAE), weights=S.hours_scored):,.0f}; 80% coverage {100 * np.average(S.cov80, weights=S.hours_scored):.1f}%, 95% coverage {100 * np.average(S.cov95, weights=S.hours_scored):.1f}%"
    if new: tot += f"; new method {100 * np.average(S.cov80_new, weights=S.hours_scored):.1f}% / {100 * np.average(S.cov95_new, weights=S.hours_scored):.1f}%"
    return (f"# Prospective check\n\nForecast generated {meta.get('generated_utc')}, origin {meta.get('origin_utc')}. Hours without an actual yet were skipped ({n_missing} hours missing in total). Reported whatever the outcome.\n\n" + "\n".join(out) + tot + ".\n")

def update_readme(table_md: str, readme="README.md"):
    s = Path(readme).read_text(); a, b = "<!-- PROSPECTIVE:START -->", "<!-- PROSPECTIVE:END -->"
    assert a in s and b in s, "README markers missing"
    Path(readme).write_text(s[: s.index(a) + len(a)] + "\n" + table_md + "\n" + s[s.index(b):])

def run(log, loads, intervals=None, out_md="results/prospective_results.md", out_csv="results/prospective_results.csv", readme=None):
    S = score(log, loads, intervals, by="bucket")
    n_missing = sum(len(f["t"]) for f in log["forecast"].values()) - int(S.hours_scored.sum()) if len(S) else sum(len(f["t"]) for f in log["forecast"].values())
    if not len(S):
        md = f"# Prospective check\n\nNo actual load is available yet for any hour of this forecast (origin {log['meta'].get('origin_utc')}). Run again after the SMARD data has caught up.\n"; S.to_csv(out_csv, index=False)
    else: md = markdown(S, log["meta"], n_missing); S.to_csv(out_csv, index=False)
    Path(out_md).write_text(md)
    if readme and len(S): update_readme(md.split("\n\n", 2)[2], readme)
    return S, md

def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("log"); ap.add_argument("--intervals"); ap.add_argument("--update-readme", action="store_true"); a = ap.parse_args(argv)
    from gepf.data import ZONES, load_hourly
    log = json.load(open(a.log)); iv = json.load(open(a.intervals)) if a.intervals else None; loads = {z: load_hourly(z)[0] for z in ZONES}
    S, md = run(log, loads, iv, readme="README.md" if a.update_readme else None); print(md); return S

if __name__ == "__main__":
    main()
