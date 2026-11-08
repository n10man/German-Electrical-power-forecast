import numpy as np, pandas as pd, lightgbm as lgb
CAL = ["hour", "dow", "month", "doy", "is_weekend", "holiday_share", "bridge_day"]
LAGS = ["lag_24h", "lag_48h", "lag_168h", "lag_336h"]
WX = ["w_temperature_2m", "w_relative_humidity_2m", "w_wind_speed_10m", "w_shortwave_radiation", "w_cloud_cover"]
PARAMS = dict(objective="regression", learning_rate=0.05, n_estimators=600, num_leaves=31, min_child_samples=40,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=42, n_jobs=4, verbose=-1, deterministic=True, force_row_wise=True)

def feats(weather: bool, pooled: bool):
    return CAL + LAGS + (WX if weather else []) + (["zone_id"] if pooled else [])

def add_zone_id(df, zones):
    df = df.copy(); df["zone_id"] = pd.Categorical(df["zone"], categories=zones); return df

def fit(X, y, **over):
    p = {**PARAMS, **over}; return lgb.LGBMRegressor(**p).fit(X, y)
