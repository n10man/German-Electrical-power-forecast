"""Tests for the direct multi-horizon feature code and the gate of scripts/final_eval_future.py. None reads the sealed test file."""
import importlib.util, json, re, sys
from pathlib import Path
import numpy as np, pandas as pd, pytest
from gepf import horizon as H
from gepf.data import ZONES

ROOT = Path(__file__).resolve().parents[1]
ALL_K = H.HORIZONS + H.OUTLOOK

def test_every_load_lag_is_at_least_24k_hours():
    for k in ALL_K:
        for c in H.load_feature_names(k):
            if c.startswith("lag_"): assert int(re.search(r"\d+", c).group()) >= 24 * k, (k, c)
        assert H.week_lag(k) % 168 == 0 and H.week_lag(k) >= 24 * k

def test_each_day_is_served_by_a_model_whose_cutoff_is_before_the_origin():
    # origin O, target t = O + delta, delta in (24(d-1), 24d]; model k >= d uses load <= t - 24k <= O
    for d in range(1, 22):
        k = H.day_to_model(d); assert k >= d and k in ALL_K
        for delta in range(24 * (d - 1) + 1, 24 * d + 1): assert delta - 24 * k <= 0
    assert [H.day_to_model(d) for d in (1, 4, 6, 8, 11, 15, 17, 21)] == [1, 5, 7, 10, 14, 16, 21, 21]

@pytest.mark.parametrize("k", ALL_K)
def test_features_at_t_ignore_load_after_t_minus_24k(k):
    idx = pd.date_range("2024-01-01", periods=24 * 60, freq="h", tz="UTC")
    a = pd.Series(np.random.default_rng(1).normal(10000, 500, len(idx)), index=idx)
    t = 24 * 40; cut = t - 24 * k                       # position of the last load value the model may use for target hour t
    b = a.copy(); b.iloc[cut + 1:] += 1e6              # change everything the origin could not know
    fa, fb = H.load_features(a, k), H.load_features(b, k)
    assert np.allclose(fa.iloc[t].values, fb.iloc[t].values, equal_nan=True)
    ba, bb = H.baselines(a, k), H.baselines(b, k); assert np.allclose(ba.iloc[t].values, bb.iloc[t].values, equal_nan=True)
    c = a.copy(); c.iloc[cut] += 1e6                    # the last allowed value must matter (the mean24 feature uses it)
    assert H.load_features(c, k).iloc[t]["mean24_known"] != fa.iloc[t]["mean24_known"]

@pytest.mark.parametrize("k", ALL_K)
def test_future_frame_uses_only_load_up_to_the_origin(k):
    idx = pd.date_range("2024-01-01", periods=24 * 90, freq="h", tz="UTC")
    load = pd.Series(np.random.default_rng(2).normal(10000, 500, len(idx)), index=idx)
    origin = idx[24 * 40]; known = load[load.index <= origin]
    targets = pd.date_range(origin + pd.Timedelta(hours=1), origin + pd.Timedelta(hours=24 * k), freq="h", tz="UTC")   # every hour model k may serve
    wx = pd.DataFrame(0.0, index=targets, columns=H.WX)
    X = H.future_frame("Amprion", known, k, targets, wx)
    for c in H.load_feature_names(k): assert X[c].notna().all(), (k, c)      # all needed lags exist at the origin
    # equals the same computation done with the full series (nothing after the origin was needed)
    full = H.load_features(load, k).loc[targets]; assert np.allclose(X[H.load_feature_names(k)].values, full.values)

def test_weather_only_for_horizons_up_to_7_and_names():
    for k in ALL_K:
        assert (H.weather_names(k, "ALL") == []) == (k > 7)
        assert set(H.feature_names(k, False)) == set(H.feature_names(k, "T")) - {"w_temperature_2m"} or k > 7
    assert H.WX_T == ["w_temperature_2m"]

def test_saved_models_use_allowed_features_only():
    p = ROOT / "models_future" / "cqr_offsets_future.json"
    if not p.exists(): pytest.skip("models_future/ absent (gitignored): python scripts/train_future.py")
    feats = json.load(open(p))["features"]
    for key, v in feats.items():
        z, k = key.split("|"); k = int(k)
        for c in v["features"]:
            if c.startswith("lag_"): assert int(re.search(r"\d+", c).group()) >= 24 * k, key
            assert c not in ("load_mw",) and not c.startswith("B_")
        if k > 7: assert not any(c.startswith("w_") for c in v["features"]), key

def test_offsets_nonnegative_and_cover_every_cell():
    p = ROOT / "models_future" / "cqr_offsets_future.json"
    if not p.exists(): pytest.skip("models_future/ absent")
    off = json.load(open(p))["offsets"]
    assert set(off) == {f"{z}|{k}|{b}" for z in ZONES for k in ALL_K for b in ("80", "95")}

# ---- gate of scripts/final_eval_future.py ----
def load_mod():
    spec = importlib.util.spec_from_file_location("final_eval_future", ROOT / "scripts" / "final_eval_future.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

@pytest.fixture
def fe(monkeypatch, tmp_path):
    monkeypatch.chdir(ROOT); m = load_mod(); reads = []; real = pd.read_parquet
    monkeypatch.setattr(pd, "read_parquet", lambda p, *a, **k: (reads.append(str(p)), real(p, *a, **k))[1])
    monkeypatch.setattr(m, "DONE", tmp_path / "DONE"); m.reads = reads; return m
needs_models = pytest.mark.skipif(not (ROOT / "models_future").is_dir(), reason="models_future/ absent")

def test_future_refuses_without_confirm(fe):
    with pytest.raises(SystemExit) as e: fe.main([])
    assert e.value.code == 2 and fe.reads == []

def test_future_refuses_when_already_done(fe):
    fe.DONE.write_text("{}")
    with pytest.raises(SystemExit) as e: fe.main(["--confirm-final"])
    assert e.value.code == 3 and fe.reads == []

@needs_models
def test_future_refuses_on_tampered_lock(fe, monkeypatch, tmp_path):
    lock = json.load(open(ROOT / "results/model_lock_future.json")); k = next(iter(lock["sha256"])); lock["sha256"][k] = "0" * 64
    p = tmp_path / "lock.json"; p.write_text(json.dumps(lock)); monkeypatch.setattr(fe, "LOCK", p)
    with pytest.raises(SystemExit) as e: fe.main(["--confirm-final"])
    assert e.value.code == 4 and fe.reads == []

@needs_models
def test_future_dummy_run_touches_neither_sealed_file_nor_results(fe, tmp_path):
    before = {p.name for p in (ROOT / "results").iterdir()}
    fe.main(["--confirm-final", "--dummy", "--out-dir", str(tmp_path / "o")])
    assert not any("sealed_test" in r for r in fe.reads) and not fe.DONE.exists()
    assert {p.name for p in (ROOT / "results").iterdir()} == before and (tmp_path / "o" / "dummy_future_metrics.csv").exists()
