"""Tests for the future-forecast snapshot (site/data/future*, results/prospective) and the later comparison script."""
import json, re, sys
from pathlib import Path
import numpy as np, pandas as pd, pytest
from gepf.data import ZONES
from gepf import horizon as H

ROOT = Path(__file__).resolve().parents[1]; SITE = ROOT / "site" / "data"
have = (SITE / "future_meta.json").exists()
skip = pytest.mark.skipif(not have, reason="future forecast not generated")
KEYS = {"h", "t", "k", "d", "f", "l80", "u80", "l95", "u95"}

@pytest.fixture(scope="module")
def meta(): return json.load(open(SITE / "future_meta.json"))
@pytest.fixture(scope="module")
def fut(): return {z: json.load(open(SITE / "future" / f"{z}.json")) for z in ZONES}

@skip
def test_forecast_file_has_expected_zones_hours_and_columns(fut, meta):
    assert set(fut) == set(ZONES)
    first, last = pd.Timestamp(meta["covers_first_utc"], tz="UTC"), pd.Timestamp(meta["covers_last_utc"], tz="UTC")
    expect = pd.date_range(first, last, freq="h")
    for z, d in fut.items():
        assert set(d) == {"zone", "unit", "days"} and d["zone"] == z
        ts = []
        for day, v in d["days"].items():
            assert set(v) == KEYS and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)
            n = len(v["h"]); assert 1 <= n <= 25 and all(len(v[k]) == n for k in KEYS)
            ts += list(pd.to_datetime(v["t"], utc=True))
        assert list(pd.DatetimeIndex(ts)) == list(expect), z                    # every hour from first to last, once, in order
    assert len(expect) >= 24 * 20

@skip
def test_quantiles_are_monotone_and_values_finite(fut):
    for z, d in fut.items():
        for day, v in d["days"].items():
            l95, l80, f, u80, u95 = (np.array(v[k], float) for k in ("l95", "l80", "f", "u80", "u95"))
            assert np.isfinite([l95, l80, f, u80, u95]).all()
            assert (l95 <= l80).all() and (l80 <= f).all() and (f <= u80).all() and (u80 <= u95).all(), (z, day)
            assert (f > 1000).all() and (f < 40000).all()

@skip
def test_no_actual_line_and_horizon_fields_consistent(fut, meta):
    origin = pd.Timestamp(meta["origin_utc"], tz="UTC")
    for z, d in fut.items():
        for v in d["days"].values():
            assert "a" not in v and "s" not in v                                 # a future file never carries actual load
            for t, k, dd in zip(pd.to_datetime(v["t"], utc=True), v["k"], v["d"]):
                assert t > origin and dd == int(np.ceil((t - origin) / pd.Timedelta(hours=1) / 24)) and k == H.day_to_model(dd)
    assert pd.Timestamp(meta["covers_first_utc"], tz="UTC") > pd.Timestamp(meta["generated_utc"], tz="UTC") - pd.Timedelta(hours=1)

@skip
def test_meta_has_accuracy_for_every_cell_and_attribution_fields(meta):
    assert set(meta["accuracy"]) == {f"{z}|{k}" for z in ZONES for k in H.HORIZONS + H.OUTLOOK}
    for v in meta["accuracy"].values(): assert {"val_mae", "val_gain_pct", "test_mae", "test_cov80", "test_cov95", "val_cov80_swapped_min"} <= set(v)
    assert meta["weather_used_up_to_day"] == 7 and meta["forecast_days"] == 16

PAST_SHA256 = {  # SHA-256 of the past-date map files as they were on main before the future-forecast feature
    "50Hertz.json": "96ec6fa8f822ee5b95e209c9e214750cbd039690d1e79b7e879abfbf5761f063", "Amprion.json": "01d7a0852797237a3985210cf0ee06ece15e4b4f18071b3a412528bc35d5ae87",
    "TenneT.json": "851e50fc5e5f4c718f4cef8d36af004da8443ccdf1524cb74012fcb36025bf0d", "TransnetBW.json": "a6d243a7f5f3a7b539a6e4e5c78ffbc0930bb2c274667532f821c812e54072a1",
    "meta.json": "70043680b4012b4e46b36e79b5776513ed1180436be1b5db30885b8bc91361ef"}

def test_past_dates_data_unchanged_by_this_feature():
    import hashlib
    for f, h in PAST_SHA256.items(): assert hashlib.sha256((SITE / f).read_bytes()).hexdigest() == h, f"{f} changed"

def test_compare_prospective_scores_a_tiny_log():
    sys.path.insert(0, str(ROOT / "scripts")); import compare_prospective as C
    idx = pd.date_range("2026-01-01", periods=24 * 10, freq="h", tz="UTC"); load = pd.Series(100.0, index=idx)
    origin = idx[24 * 5]; t = pd.date_range(origin + pd.Timedelta(hours=1), periods=24, freq="h", tz="UTC")
    log = {"meta": {"origin_utc": origin.isoformat()}, "forecast": {"Amprion": dict(t=[x.strftime("%Y-%m-%dT%H:00Z") for x in t], f=[100.0] * 24, l80=[90.0] * 24, u80=[110.0] * 24, l95=[80.0] * 24, u95=[120.0] * 24, k=[1] * 24, d=[1] * 24)}}
    S = C.score(log, {"Amprion": load})
    assert len(S) == 1 and S.MAE[0] == 0 and S.cov80[0] == 1 and S.hours_scored[0] == 24
    S2 = C.score(log, {"Amprion": load.iloc[: 24 * 5 + 6]})      # only 5 of the hours have happened
    assert S2.hours_scored[0] == 5 and S2.hours_in_log[0] == 24
