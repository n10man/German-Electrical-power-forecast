"""I1 interval methods (validation protocol) and the integration artefacts. No test reads the sealed test file."""
import hashlib, json, sys
from pathlib import Path
import numpy as np, pandas as pd, pytest
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
import run_interval_methods as I

def scores(n=8760, seed=0):
    return np.random.default_rng(seed).normal(0, 100, n)

@pytest.mark.parametrize("k", [1, 7, 21])
def test_rolling_uses_only_scores_known_before_the_day_starts(k):
    s = scores(); c = I.calib_rolling(s, k, 0.8, 8); day0 = I.BURN + 24 * 30; d = 24 * k
    s2 = s.copy(); s2[day0 - d + 1:] += 1e6                                   # change everything the origin could not know
    assert np.allclose(c[day0: day0 + 24], I.calib_rolling(s2, k, 0.8, 8)[day0: day0 + 24])
    s3 = s.copy(); s3[day0 - d - 400: day0 - d + 1] += 1e6                    # the most recent known scores must matter
    assert not np.allclose(c[day0: day0 + 24], I.calib_rolling(s3, k, 0.8, 8)[day0: day0 + 24])

def test_rolling_window_length_and_static_is_frozen():
    s = np.concatenate([np.zeros(I.BURN), np.full(2000, 500.0), np.zeros(6000)])[:8760]
    st = I.calib_static(s, 1, 0.8); assert (st == st[0]).all() and st[0] <= 0.0
    r4 = I.calib_rolling(s, 1, 0.8, 4); assert r4[I.BURN + 24 * 3] == 0 and r4[I.BURN + 24 * 10] == 500    # big scores enter only after the 24h delay and once they exceed 20% of the window ...
    assert r4[I.BURN + 2000 + 24 * 40] == 0 and I.calib_rolling(s, 1, 0.8, 13)[I.BURN + 2000 + 24 * 40] == 500   # ... and leave a 4-week window earlier than a 13-week one

def test_aci_widens_after_misses_and_is_delayed():
    n = 8760; lo = np.zeros(n); hi = np.ones(n); y = np.full(n, 0.5); y[I.BURN + 100:] = 50.0                       # from here on every point is a miss
    s = np.maximum(lo - y, y - hi); s[: I.BURN] = np.linspace(-1, 0, I.BURN)
    c = I.calib_aci(s, 1, 0.8, 0.02, lo, hi, y)
    assert c[I.BURN + 100] < 1 and c[I.BURN + 100 + 23] < 1 and c[I.BURN + 500] > 10                                    # misses start at +100; no reaction for 24h, then the interval grows
    slow = I.calib_aci(s, 1, 0.8, 0.0001, lo, hi, y); assert slow[I.BURN + 300] < c[I.BURN + 300]                      # a smaller step reacts more slowly

def test_evaluate_matches_hand_calculation():
    lo = np.array([0.0] * 5000); hi = np.array([10.0] * 5000); y = np.full(5000, 5.0); y[I.BURN:I.BURN + 10] = 20.0; c = np.zeros(5000)
    r = I.evaluate(lo, hi, y, c, 0.8); n = 5000 - I.BURN; assert r["n"] == n and r["coverage"] == pytest.approx(1 - 10 / n) and r["width"] == 10
    assert r["interval_score"] == pytest.approx(10 + (2 / 0.2) * 10 * 10 / n)

def test_selection_follows_the_preregistered_rule_on_the_recorded_results():
    S = pd.read_csv(ROOT / "results/interval_val_summary.csv").set_index("candidate"); sel = json.load(open(ROOT / "results/interval_selection.json"))
    adm = S[(S.R_score_ratio_vs_static <= 1.10) & (S.index != "static")].sort_values("D_abs_cov_gap_pts"); best = adm.iloc[0]
    near = adm[adm.D_abs_cov_gap_pts <= best.D_abs_cov_gap_pts + 0.1].sort_values("R_score_ratio_vs_static").iloc[0]
    assert sel["selected"] == near.name and near.D_abs_cov_gap_pts < S.loc["static"].D_abs_cov_gap_pts
    assert not S.loc[[c for c in S.index if c.startswith("aci")]].admissible.any()          # recorded: ACI widened too much under the 24k-hour feedback delay
    assert set(pd.read_csv(ROOT / "results/interval_val_cells.csv").candidate) == set(I.CANDIDATES)

# ---- integration artefacts ----
CAL = ROOT / "results/interval_calibration_rolling_8w.json"
def test_lock_file_hashes_match_and_original_log_untouched():
    lock = json.load(open(ROOT / "results/interval_lock.json"))["sha256"]
    for name, h in lock.items():
        p = CAL if name == CAL.name else ROOT / "results" / name
        assert hashlib.sha256(p.read_bytes()).hexdigest() == h, name
    cal = json.load(open(CAL)); log = ROOT / "results/prospective" / cal["original_log"]
    assert hashlib.sha256(log.read_bytes()).hexdigest() == cal["original_log_sha256"] == "897be3dc27dda1d05a09cc2db677593c5bf52488166fd40360c663325f49cafe"

def test_calibration_uses_only_scores_after_the_sealed_period():
    cal = json.load(open(CAL)); assert len(cal["cells"]) == 72
    for k, v in cal["cells"].items():
        assert pd.Timestamp(v["first_score"]) >= pd.Timestamp("2026-10-25 00:00", tz="UTC") and pd.Timestamp(v["last_score"]) <= pd.Timestamp(cal["origin_utc"]) and v["n_scores"] >= cal["min_hours"] or v["fallback_to_static"]

def test_new_intervals_keep_point_forecasts_and_the_site_uses_them():
    cal = json.load(open(CAL)); P = ROOT / "results/prospective"; old = json.load(open(P / cal["original_log"]))["forecast"]
    new = json.load(open(P / f"intervals_rolling_8w_{cal['original_log'][len('forecast_'):]}"))["forecast"]
    for z in old:
        assert new[z]["t"] == old[z]["t"] and new[z]["f"] == old[z]["f"]
        for i in range(0, len(old[z]["t"]), 7):
            if new[z]["l80"][i] is None: continue
            assert new[z]["l95"][i] <= new[z]["l80"][i] <= new[z]["f"][i] <= new[z]["u80"][i] <= new[z]["u95"][i]
        site = json.load(open(ROOT / "site/data/future" / f"{z}.json")); idx = {t: i for i, t in enumerate(new[z]["t"])}
        for day in site["days"].values():
            for c in ("l80", "u80", "l95", "u95"): assert day[c] == [new[z][c][idx[t]] for t in day["t"]]
            assert day["f"] == [old[z]["f"][idx[t]] for t in day["t"]]
    assert json.load(open(ROOT / "site/data/future_meta.json"))["interval_method"]["name"] == "rolling_8w"
