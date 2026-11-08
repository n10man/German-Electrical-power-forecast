import numpy as np, pandas as pd

def mae(y, p): return float(np.mean(np.abs(np.asarray(y) - np.asarray(p))))
def rmse(y, p): return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))
def mape(y, p): return float(np.mean(np.abs((np.asarray(y) - np.asarray(p)) / np.asarray(y))) * 100)

def subsets(d, temp_col="w_temperature_2m"):
    """d: one zone, validation rows with timestamp_utc, holiday_share, temp. Returns dict name -> boolean mask.
    Hot/cold = hottest/coldest 5% of Berlin local days by daily mean temperature (ranked inside d)."""
    day = d["timestamp_utc"].dt.tz_convert("Europe/Berlin").dt.normalize().dt.tz_localize(None)
    dm = d.groupby(day)[temp_col].mean()
    hot_days = dm[dm >= dm.quantile(.95)].index; cold_days = dm[dm <= dm.quantile(.05)].index
    return {"all": np.ones(len(d), bool),
            "holiday": (d["holiday_share"] >= 0.5).values,
            "hot5": day.isin(hot_days).values, "cold5": day.isin(cold_days).values}

def score(d, pred, base):
    """d: zone rows; pred/base: arrays aligned to d. Returns dict of MAE/RMSE/MAPE overall + subset MAEs for model and baseline."""
    out = {}
    for k, m in subsets(d).items():
        y = d["load_mw"].values[m]
        out[f"mae_{k}"] = mae(y, pred[m]); out[f"base_mae_{k}"] = mae(y, base[m]); out[f"n_{k}"] = int(m.sum())
        if k == "all": out["rmse"] = rmse(y, pred[m]); out["mape"] = mape(y, pred[m])
    return out

def rule_v2(s, b1_all):
    """RULE v2 (see results/EXPERIMENTS.md)."""
    return bool(s["mae_all"] <= 0.95 * b1_all and s["mae_holiday"] <= s["base_mae_holiday"]
                and s["mae_hot5"] <= s["base_mae_hot5"] and s["mae_cold5"] <= s["base_mae_cold5"])
