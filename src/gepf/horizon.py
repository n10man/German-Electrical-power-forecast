"""Direct multi-horizon features ("one model per distance").

Model k (k = 1, 2, 3, 5, 7, 10, 14, 16, and the optional outlook model 21) forecasts target hour t using ONLY load
measured at or before t - 24k hours. A forecast origin O (the last hour with actual load) is at most 24k hours before
any target hour the model is used for (see DAY_TO_MODEL), so every load feature is known at the origin.
Weather features (models k <= 7 only) are ARCHIVED FORECASTS issued k days before the target hour (Open-Meteo Previous
Runs API, '<var>_previous_day<k>'), averaged over the zone's 3 cities, the same kind of input the model sees at serving.
Calendar features are deterministic and known in advance.
"""
import math
import numpy as np, pandas as pd
from gepf.data import calendar_features
from gepf.models import CAL, WX

HORIZONS = [1, 2, 3, 5, 7, 10, 14, 16]
OUTLOOK = [21]                                   # days 17-21, climatology-only (no weather forecast exists), shown only if it passes
WEATHER_MAX_K = 7                                # archived forecasts exist only up to 7 days of lead
BASE_VARS = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "shortwave_radiation", "cloud_cover"]

def day_to_model(day: int) -> int:
    """Forecast day (1 = first 24 h after the origin) -> the horizon model that serves it (the smallest k >= day)."""
    for k in HORIZONS + OUTLOOK:
        if day <= k: return k
    raise ValueError(day)

def shift_hours(k: int) -> int:
    return 24 * k

def week_lag(k: int) -> int:
    """Same weekday and hour in the latest week that is fully known: smallest multiple of 168 that is >= 24k."""
    return 168 * math.ceil(shift_hours(k) / 168)

def lag_hours(k: int):
    s, w = shift_hours(k), week_lag(k)
    return sorted({s, s + 24, w, w + 168})

def load_feature_names(k: int):
    return [f"lag_{L}h" for L in lag_hours(k)] + ["mean24_known", "mean168_known"]

WX_T = ["w_temperature_2m"]                      # archived lead forecasts exist for temperature from 2021-03, for the other four only from 2024-01-19

def weather_names(k: int, weather):
    """weather: False/None = none, 'T' = temperature forecast only, 'ALL' = all five variables."""
    if not weather or k > WEATHER_MAX_K: return []
    return WX_T if weather == "T" else WX

def feature_names(k: int, weather=False):
    return CAL + load_feature_names(k) + weather_names(k, weather)

def load_features(load: pd.Series, k: int) -> pd.DataFrame:
    """Load-derived features for horizon k. `load` is hourly, UTC, regular index (NaN = missing). Every column at time t
    is a function of load[<= t - 24k] only."""
    s = shift_hours(k)
    out = {f"lag_{L}h": load.shift(L) for L in lag_hours(k)}
    known = load.shift(s)                                   # known[t] = load[t - s]
    out["mean24_known"] = known.rolling(24, min_periods=18).mean()      # load over (t-s-23 .. t-s)
    out["mean168_known"] = known.rolling(168, min_periods=126).mean()   # load over (t-s-167 .. t-s)
    return pd.DataFrame(out)

def baselines(load: pd.Series, k: int) -> pd.DataFrame:
    """Simple seasonal-naive references that use the same information cutoff as model k."""
    s, w = shift_hours(k), week_lag(k)
    return pd.DataFrame({"B_day": load.shift(s),            # same hour k days earlier
                         "B_week": load.shift(w),           # same weekday+hour from the latest known week
                         "B_wk4avg": pd.concat([load.shift(w + 168 * j) for j in range(4)], axis=1).mean(axis=1, skipna=False)})

def forecast_weather(archive: pd.DataFrame, zone: str, k: int, index) -> pd.DataFrame:
    """Zone mean over its cities of the archived forecast issued k days before each target hour, columns named like WX."""
    a = archive[archive.zone == zone]
    cols = {f"{v}_previous_day{k}": f"w_{v}" for v in BASE_VARS}
    m = a.groupby("timestamp_utc")[list(cols)].mean().rename(columns=cols)
    return m.reindex(index)[WX]

def build_frame(zone: str, load: pd.Series, k: int, archive: pd.DataFrame | None = None) -> pd.DataFrame:
    """Features (+ weather if archive given and k <= 7) + target `load_mw` for horizon k on load.index."""
    idx = load.index
    X = pd.concat([calendar_features(idx, zone), load_features(load, k)], axis=1)
    if archive is not None and k <= WEATHER_MAX_K:
        X = pd.concat([X, forecast_weather(archive, zone, k, idx)], axis=1)
    X["load_mw"] = load
    for c, v in baselines(load, k).items(): X[c] = v
    X["zone"] = zone
    return X

def future_frame(zone: str, load: pd.Series, k: int, targets: pd.DatetimeIndex, wx: pd.DataFrame | None) -> pd.DataFrame:
    """Serving frame: `load` ends at the origin; `targets` are future hours. wx: forecast weather (columns WX) indexed by hour or None."""
    full = load.reindex(load.index.union(targets)).sort_index()
    full = full.reindex(pd.date_range(full.index.min(), full.index.max(), freq="h", tz="UTC"))
    X = pd.concat([calendar_features(full.index, zone), load_features(full, k)], axis=1)
    if wx is not None and k <= WEATHER_MAX_K: X = pd.concat([X, wx.reindex(full.index)[WX]], axis=1)
    for c, v in baselines(full, k).items(): X[c] = v
    return X.loc[targets]
