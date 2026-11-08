"""Automated leakage / split tests. These never read data/processed/sealed_test.parquet."""
import re, numpy as np, pandas as pd, pytest
from gepf.data import ZONES, PROC, lag_features, split_bounds, split_name, calendar_features

def test_lags_are_at_least_24h():
    load = pd.Series(np.arange(500.0), index=pd.date_range("2020-01-01", periods=500, freq="h", tz="UTC"))
    lf = lag_features(load)
    for c in lf:
        k = int(re.search(r"lag_(\d+)h", c).group(1)); assert k >= 24
        assert (lf[c].iloc[k:].values == load.shift(k).iloc[k:].values).all()
        assert lf[c].iloc[:k].isna().all()

def test_no_feature_uses_current_or_future_load():
    # perturbing load at t must not change any lag feature at t (or earlier than t+24h)
    idx = pd.date_range("2020-01-01", periods=400, freq="h", tz="UTC")
    a = pd.Series(np.random.default_rng(0).normal(size=400), index=idx); b = a.copy(); b.iloc[200] += 1000
    d = (lag_features(a) - lag_features(b)).abs().fillna(0)
    assert (d.iloc[:224].values == 0).all()

def test_split_is_chronological_and_sized():
    end = pd.Timestamp("2026-11-08", tz="UTC"); b = split_bounds(end)
    idx = pd.date_range(pd.Timestamp("2015-01-01", tz="UTC"), end, freq="h", inclusive="left")
    s = pd.Series(split_name(idx, b), index=idx)
    assert s.index[s == "train"].max() < s.index[s == "val"].min() < s.index[s == "val"].max() < s.index[s == "test"].min()
    assert (s == "val").sum() == 8760 and (s == "test").sum() == 8760

trainval = PROC / "trainval.parquet"
@pytest.mark.skipif(not trainval.exists(), reason="dataset not built")
def test_trainval_file_has_no_test_rows():
    df = pd.read_parquet(trainval)
    assert set(df.split) == {"train", "val"}
    import json; b = split_bounds(pd.Timestamp(json.load(open(PROC / "build_info.json"))["end"]))
    assert df.timestamp_utc.max() < b["test_start"]
    assert df.groupby("zone").timestamp_utc.apply(lambda s: s.is_unique).all()

@pytest.mark.skipif(not trainval.exists(), reason="dataset not built")
def test_feature_columns_have_no_raw_target_copy():
    df = pd.read_parquet(trainval)
    feats = [c for c in df.columns if c not in ("timestamp_utc", "zone", "split", "load_mw")]
    for c in feats:
        assert not np.allclose(df[c].fillna(-1).values, df["load_mw"].fillna(-1).values), c
        assert not c.startswith("lag_") or int(re.search(r"\d+", c).group()) >= 24

def test_calendar_dst_hours_local():
    idx = pd.date_range("2022-03-26 22:00", "2022-03-27 23:00", freq="h", tz="UTC")
    f = calendar_features(idx, "Amprion")
    local = idx.tz_convert("Europe/Berlin")
    assert (f["hour"].values == local.hour).all()
    assert 2 not in set(f.loc[local.date == pd.Timestamp("2022-03-27").date(), "hour"])  # 02:00 does not exist

def test_holiday_features():
    idx = pd.date_range("2022-12-24 12:00", periods=3, freq="D", tz="UTC")  # Dec 25 = Sun & holiday nationwide
    f = calendar_features(idx, "TenneT")
    assert f.loc[idx[1], "holiday_share"] == 1.0 and f.loc[idx[0], "holiday_share"] == 0.0
