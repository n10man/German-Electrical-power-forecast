"""Prospective check: scripts/compare_prospective.py on FAKE actuals (never real data), and the pinned hash of the pre-registered log."""
import hashlib, json, sys
from pathlib import Path
import numpy as np, pandas as pd, pytest
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import compare_prospective as C

LOG = ROOT / "results/prospective/forecast_20261110T07_20261111T053623Z.json"; LOG_SHA = "897be3dc27dda1d05a09cc2db677593c5bf52488166fd40360c663325f49cafe"

def fake(n_days=21, hours=None):
    idx = pd.date_range("2026-01-01", periods=24 * 60, freq="h", tz="UTC"); load = pd.Series(100.0, index=idx)
    origin = idx[24 * 20]; t = pd.date_range(origin + pd.Timedelta(hours=1), periods=24 * n_days, freq="h", tz="UTC"); d = np.ceil(np.arange(1, len(t) + 1) / 24).astype(int)
    k = [next(x for x in (1, 2, 3, 5, 7, 10, 14, 16, 21) if x >= v) for v in d]; n = len(t)
    f = dict(t=[x.strftime("%Y-%m-%dT%H:00Z") for x in t], f=[100.0] * n, l80=[90.0] * n, u80=[110.0] * n, l95=[80.0] * n, u95=[120.0] * n, k=k, d=[int(v) for v in d])
    log = {"meta": {"origin_utc": origin.isoformat(), "generated_utc": "x"}, "forecast": {"Amprion": f}}
    iv = {"forecast": {"Amprion": {c: [x if i % 50 else None for i, x in enumerate(f[c])] for c in ("l80", "u80", "l95", "u95")} | {"t": f["t"]}}}
    for c in ("l80", "u80", "l95", "u95"): iv["forecast"]["Amprion"][c] = [None if i % 50 == 0 else (v - 5 if "l" in c else v + 5) for i, v in enumerate(f[c])]
    return log, load, iv, t

def test_buckets_mae_baseline_and_coverage_on_fake_actuals():
    log, load, iv, t = fake(); load = load.copy(); load.loc[t] = 105.0                         # actual = 105 everywhere: inside the ranges, error 5
    S = C.score(log, {"Amprion": load}, by="bucket")
    assert set(S.days_ahead) == {"1", "2-3", "4-7", "8-14", "15-16", "17-21"} and (S.MAE == 5).all() and (S.cov80 == 1).all()
    assert (S.hours_scored == S.hours_in_log).all() and S.hours_scored.sum() == 24 * 21
    load.loc[t[:24]] = 200.0                                                                   # day 1 far outside every range
    S = C.score(log, {"Amprion": load}, by="bucket"); r = S[S.days_ahead == "1"].iloc[0]; assert r.cov80 == 0 and r.cov95 == 0 and r.MAE == 100

def test_missing_actuals_are_skipped_and_counted_and_nothing_scored_gives_a_message(tmp_path):
    log, load, iv, t = fake(); only = load.loc[: t[29]].copy()                               # only the first 30 forecast hours have an actual
    S = C.score(log, {"Amprion": only}, by="bucket"); assert S.hours_scored.sum() == 30 and S.hours_in_log.sum() > 30
    S, md = C.run(log, {"Amprion": load.loc[: t[0] - pd.Timedelta(hours=1)]}, out_md=str(tmp_path / "r.md"), out_csv=str(tmp_path / "r.csv"))
    assert len(S) == 0 and "No actual load is available yet" in (tmp_path / "r.md").read_text()

def test_new_intervals_scored_on_same_hours_with_missing_values_ignored(tmp_path):
    log, load, iv, t = fake(); load = load.copy(); load.loc[t] = 112.0                      # outside the old 80% range (110), inside the new one (115)
    S = C.score(log, {"Amprion": load}, iv, by="bucket")
    assert (S.cov80 == 0).all() and (S.cov80_new == 1).all() and (S.cov95 == 1).all() and (S.width80_new > S.width80).all()
    S, md = C.run(log, {"Amprion": load}, iv, out_md=str(tmp_path / "r.md"), out_csv=str(tmp_path / "r.csv")); assert "80% cov. (new)" in md and "Pooled" in md

def test_readme_table_is_replaced_between_markers(tmp_path):
    log, load, iv, t = fake(); load = load.copy(); load.loc[t] = 100.0; rd = tmp_path / "README.md"; rd.write_text("a\n<!-- PROSPECTIVE:START -->\nold\n<!-- PROSPECTIVE:END -->\nb\n")
    C.run(log, {"Amprion": load}, out_md=str(tmp_path / "r.md"), out_csv=str(tmp_path / "r.csv"), readme=str(rd)); s = rd.read_text()
    assert s.startswith("a\n") and s.endswith("b\n") and "old" not in s and "| zone |" in s

def test_script_does_not_touch_the_network_or_real_results():
    src = (ROOT / "scripts/compare_prospective.py").read_text(); assert "requests" not in src and "urlopen" not in src
    assert hashlib.sha256(LOG.read_bytes()).hexdigest() == LOG_SHA, "the pre-registered log changed"
    assert not (ROOT / "results/prospective_results.md").exists(), "the prospective check must not be run before the data exists"

def test_readme_and_experiments_record_the_log_hash():
    for f in ("README.md", "results/EXPERIMENTS.md"): assert LOG_SHA in (ROOT / f).read_text(), f
