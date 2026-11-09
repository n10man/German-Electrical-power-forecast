"""O1: compare the official SMARD day-ahead 'Forecasted consumption' (filter 411) with the logged numbers of our model.
Reporting only. Our model's metrics are COPIED from results/final_test_metrics.csv (test) and results/lag_ablation_val.csv (validation);
actuals and hours come from the committed map files site/data/{zone}.json. The sealed parquet file is never read."""
import sys, json; sys.path.insert(0, "src")
import numpy as np, pandas as pd
from gepf.data import ZONES
from gepf.evalutil import mae, rmse, mape
TEST_LOG = pd.read_csv("results/final_test_metrics.csv"); VAL_LOG = pd.read_csv("results/lag_ablation_val.csv")
rows = []
for z in ZONES:
    d = json.load(open(f"site/data/{z}.json"))["days"]
    ours = pd.DataFrame([(t, a, s) for v in d.values() for t, a, s in zip(v["t"], v["a"], v["s"])], columns=["t", "actual", "test"])
    ours["timestamp_utc"] = pd.to_datetime(ours.t, utc=True); ours = ours.set_index("timestamp_utc")
    q = pd.read_parquet(f"data/raw/official_forecast_{z}.parquet").set_index("timestamp_utc").fc_mwh_qh
    hourly = q.resample("h").sum(min_count=4).where(q.resample("h").count() == 4)       # same rule as the load: 4 valid quarter-hours
    ours["official"] = hourly.reindex(ours.index)
    for period, flag in (("test", 1), ("validation", 0)):
        o = ours[ours.test == flag]; have = o.dropna(subset=["official"])
        rows.append(dict(period=period, zone=z, model="SMARD official day-ahead forecast (filter 411)", n_hours_scored=len(have), n_hours_in_our_eval=len(o),
                         MAE=mae(have.actual, have.official), RMSE=rmse(have.actual, have.official), MAPE=mape(have.actual, have.official)))
        if period == "test":
            for m in ("M2_mean_model", "B1_last_week"):
                r = TEST_LOG[(TEST_LOG.zone == z) & (TEST_LOG.model == m)].iloc[0]
                rows.append(dict(period="test", zone=z, model=("our model (logged, F1)" if m == "M2_mean_model" else "B1 last week (logged, F1)"), n_hours_scored=int(r.n), n_hours_in_our_eval=len(o), MAE=r.MAE, RMSE=r.RMSE, MAPE=r.MAPE))
        else:
            r = VAL_LOG[(VAL_LOG.zone == z) & (VAL_LOG.variant == "M2_ref_24_48_168_336")].iloc[0]
            rows.append(dict(period="validation", zone=z, model="our model (logged, M2)", n_hours_scored=len(o), n_hours_in_our_eval=len(o), MAE=r.mae_all, RMSE=r.rmse, MAPE=r.mape))
            rows.append(dict(period="validation", zone=z, model="B1 last week (logged)", n_hours_scored=len(o), n_hours_in_our_eval=len(o), MAE=r.base_mae_all, RMSE=np.nan, MAPE=np.nan))
R = pd.DataFrame(rows); R.to_csv("results/official_forecast_comparison.csv", index=False)
print(R.round(1).to_string(index=False))
print()
for period in ("test", "validation"):
    for z in ZONES:
        g = R[(R.period == period) & (R.zone == z)]; off = g[g.model.str.startswith("SMARD")].iloc[0]; our = g[g.model.str.startswith("our")].iloc[0]
        miss = 1 - off.n_hours_scored / off.n_hours_in_our_eval; rel = (our.MAE - off.MAE) / off.MAE
        verdict = "TIE (within 1%)" if abs(rel) <= 0.01 else ("OUR MODEL WINS" if rel < 0 else "OFFICIAL WINS")
        print(f"{period:10s} {z:11s} official MAE {off.MAE:7.1f}  ours {our.MAE:7.1f}  ({rel*100:+.1f}% vs official) -> {verdict}; official missing {miss*100:.2f}% of our hours" + ("  ** >1% missing: not like-for-like **" if miss > 0.01 else ""))
