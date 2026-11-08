"""Data verification tests (need data/raw downloaded). Run: pytest tests/test_data_sanity.py"""
import numpy as np, pandas as pd, pytest
from pathlib import Path
from gepf.data import ZONES, load_hourly, RAW

pytestmark = pytest.mark.skipif(not all((RAW / f"load_{z}.parquet").exists() for z in ZONES) or not (RAW / "ref_DE_410.parquet").exists(),
                                reason="raw data not downloaded")

@pytest.fixture(scope="module")
def hourly():
    return {z: load_hourly(z)[0] for z in ZONES}

@pytest.fixture(scope="module")
def national(hourly):
    return pd.concat(hourly, axis=1).sum(axis=1, min_count=4)

def test_no_duplicate_hours_and_regular_index(hourly):
    for z, s in hourly.items():
        assert s.index.is_unique and s.index.is_monotonic_increasing
        assert (s.index.to_series().diff().dropna() == pd.Timedelta("1h")).all(), z
        assert str(s.index.tz) == "UTC"

def test_gaps_are_small(hourly):
    for z, s in hourly.items():
        assert s.isna().mean() < 0.01, (z, s.isna().sum())

def test_dst_days_handled(hourly):
    s = hourly["Amprion"]
    loc = s.index.tz_convert("Europe/Berlin")
    n = pd.Series(1, index=loc).groupby(loc.normalize()).sum()
    assert n[pd.Timestamp("2022-03-27", tz="Europe/Berlin")] == 23   # spring forward
    assert n[pd.Timestamp("2022-10-30", tz="Europe/Berlin")] == 25   # fall back
    assert n[pd.Timestamp("2022-06-01", tz="Europe/Berlin")] == 24

def test_reference_values_2022_06_02():
    # SMARD website grid load DE (filter 410). The brief's labels (2022-06-02 00:00-03:00) were read in the
    # owner's browser timezone UTC+8 = 2022-06-01 16:00-19:00 UTC (= 18:00-21:00 Berlin). Exact match expected.
    ref = pd.read_parquet(RAW / "ref_DE_410.parquet").set_index("timestamp_utc")["mw"]
    for t, v in {"2022-06-01 16:00": 60003, "2022-06-01 17:00": 59180, "2022-06-01 18:00": 56841}.items():
        assert ref[pd.Timestamp(t, tz="UTC")] == v

def test_sum_of_zones_vs_national_total(national):
    ref = pd.read_parquet(RAW / "ref_DE_410.parquet").set_index("timestamp_utc")["mw"]
    j = pd.concat([national.rename("sum"), ref.rename("de")], axis=1).dropna()
    rel = ((j["sum"] - j["de"]) / j["de"]).abs()
    assert rel.median() < 0.03

def test_magnitudes_plausible(national):
    yr = national["2019":"2019"].dropna()
    assert 45_000 < yr.mean() < 65_000
    assert 400 < yr.mean() * 8760 / 1e6 < 560   # TWh

def test_cycles(hourly):
    for z, s in hourly.items():
        loc = s.dropna().loc["2019":"2019"]; l = loc.index.tz_convert("Europe/Berlin")
        assert loc[l.hour == 12].mean() > 1.15 * loc[l.hour == 3].mean(), z       # daily cycle
        assert loc[l.day_of_week == 2].mean() > loc[l.day_of_week == 6].mean(), z     # Sunday lower
        assert loc[l.month.isin([12, 1, 2])].mean() > loc[l.month.isin([6, 7, 8])].mean(), z
