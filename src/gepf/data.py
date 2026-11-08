"""Cleaning, features and time split. All timestamps UTC; Europe/Berlin only for calendar features."""
from pathlib import Path
import numpy as np, pandas as pd, holidays

ZONES = ["50Hertz", "Amprion", "TenneT", "TransnetBW"]
# German states (ISO subdivision codes) -> zone, approximate by TSO control-area share (documented simplification)
ZONE_STATES = {
    "50Hertz": ["BE", "BB", "MV", "SN", "ST", "TH", "HH"],
    "Amprion": ["NW", "RP", "SL"],
    "TenneT": ["BY", "HE", "NI", "SH", "BW"],  # BW placeholder removed below
    "TransnetBW": ["BW"],
}
ZONE_STATES["TenneT"] = ["BY", "HE", "NI", "SH", "HB"]
RAW = Path("data/raw"); PROC = Path("data/processed")

def load_hourly(zone, raw=RAW):
    """Quarter-hourly -> hourly mean. Dedupes, reports gaps. Returns (series indexed by UTC hour, report dict)."""
    df = pd.read_parquet(raw / f"load_{zone}.parquet")
    n0 = len(df)
    df = df.drop_duplicates("timestamp_utc").sort_values("timestamp_utc")
    s = df.set_index("timestamp_utc")["load_mw"]
    # drop trailing all-NaN (future placeholder) rows
    s = s[: s.last_valid_index()]
    full = pd.date_range(s.index.min().floor("h"), s.index.max().floor("h"), freq="h", tz="UTC")
    # SMARD quarter-hour values are MWh per 15 min -> hourly MWh = SUM of 4 (equals mean MW). Need 4 valid quarter-hours.
    cnt = s.resample("h").count()
    h = s.resample("h").sum(min_count=4).where(cnt == 4).reindex(full)
    rep = dict(zone=zone, raw_rows=n0, dup_rows=n0 - len(df), start=str(full[0]), end=str(full[-1]),
               hours=len(full), missing_hours=int(h.isna().sum()))
    return h.rename("load_mw"), rep

def holiday_share(index_utc, zone):
    """Share of zone's states (equal weight) with a public holiday on the Berlin local date."""
    dates = index_utc.tz_convert("Europe/Berlin").normalize().tz_localize(None)
    uniq = pd.DatetimeIndex(sorted(set(dates)))
    years = range(uniq.min().year, uniq.max().year + 1)
    cal = {st: holidays.Germany(subdiv=st, years=years) for st in ZONE_STATES[zone]}
    share = {d: np.mean([d.date() in cal[st] for st in cal]) for d in uniq}
    return np.array([share[d] for d in dates])

def calendar_features(idx_utc, zone):
    loc = idx_utc.tz_convert("Europe/Berlin")
    f = pd.DataFrame(index=idx_utc)
    f["hour"] = loc.hour; f["dow"] = loc.day_of_week; f["month"] = loc.month; f["doy"] = loc.dayofyear
    f["is_weekend"] = (loc.day_of_week >= 5).astype(int)
    f["holiday_share"] = holiday_share(idx_utc, zone)
    # bridge day: Mon/Fri adjacent to a (near-)national holiday on Tue/Thu
    hs = pd.Series(f["holiday_share"].values, index=loc.normalize().tz_localize(None))
    daily = hs.groupby(level=0).max()
    nxt = daily.shift(-1).reindex(hs.index).values; prv = daily.shift(1).reindex(hs.index).values
    f["bridge_day"] = (((loc.day_of_week == 0) & (nxt > .5)) | ((loc.day_of_week == 4) & (prv > .5))).astype(int)
    return f

def weather_features(zone, idx_utc, raw=RAW):
    w = pd.read_parquet(raw / "weather.parquet")
    w = w[w.zone == zone].drop(columns=["zone", "point"])
    m = w.groupby("timestamp_utc").mean().reindex(idx_utc)
    m.columns = [f"w_{c}" for c in m.columns]
    return m

def lag_features(load, lags=(24, 48, 168, 336)):
    """All lags >= 24h: every load feature known at least 24h before target hour."""
    return pd.DataFrame({f"lag_{k}h": load.shift(k) for k in lags})

def build_zone(zone):
    load, rep = load_hourly(zone)
    X = pd.concat([calendar_features(load.index, zone), weather_features(zone, load.index), lag_features(load)], axis=1)
    X["load_mw"] = load; X["zone"] = zone
    return X, rep

def split_bounds(end):
    """train: up to 2y before end; validation: next 12 months; test: last 12 months (sealed)."""
    end = pd.Timestamp(end)
    return dict(val_start=end - pd.DateOffset(years=2), test_start=end - pd.DateOffset(years=1), end=end)

def split_name(idx, b):
    return np.where(idx < b["val_start"], "train", np.where(idx < b["test_start"], "val", "test"))
