"""Post-hoc sanity check of the official forecast series (added AFTER seeing the O1 numbers; not part of the O1 rule).
Question: is SMARD filter 411 per zone a forecast of the same quantity as my target (grid load, filter 410)? Uses only official series and actuals
from site/data and data/raw; no model, no sealed file."""
import sys, json, time; sys.path.insert(0, "src")
import numpy as np, pandas as pd, requests
from gepf.data import ZONES
def hourly(q): return q.resample("h").sum(min_count=4).where(q.resample("h").count() == 4)
rows = []; act = {}
for z in ZONES:
    d = json.load(open(f"site/data/{z}.json"))["days"]
    o = pd.DataFrame([(t, a, s) for v in d.values() for t, a, s in zip(v["t"], v["a"], v["s"])], columns=["t", "actual", "test"]); o.index = pd.to_datetime(o.t, utc=True)
    o["off"] = hourly(pd.read_parquet(f"data/raw/official_forecast_{z}.parquet").set_index("timestamp_utc").fc_mwh_qh).reindex(o.index); act[z] = o
    for per, f in (("test", 1), ("validation", 0)):
        g = o[o.test == f].dropna(subset=["off"]); e = g.off - g.actual
        rows.append(dict(period=per, zone=z, mean_actual=g.actual.mean(), mean_official=g.off.mean(), bias=e.mean(), bias_pct=100 * e.mean() / g.actual.mean(), MAE=e.abs().mean(),
                         MAE_after_removing_bias=(e - e.mean()).abs().mean(), corr=np.corrcoef(g.actual, g.off)[0, 1]))
print(pd.DataFrame(rows).round(2).to_string(index=False))
# national: sum of the four zones' official vs sum of actuals, and the DE-level official series vs DE actual (filter 410, hourly, already downloaded)
test = pd.concat({z: act[z][act[z].test == 1][["actual", "off"]] for z in ZONES}, axis=1).dropna()
na, no = sum(test[z]["actual"] for z in ZONES), sum(test[z]["off"] for z in ZONES)
print("\nnational (sum of the 4 zones) test: MAE %.0f MWh/h, MAPE %.2f%%, bias %.0f (%.2f%%), n=%d" % ((no - na).abs().mean(), 100 * ((no - na).abs() / na).mean(), (no - na).mean(), 100 * (no - na).mean() / na.mean(), len(na)))
def get(url):
    for i in range(6):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200: return r.json()
        except requests.RequestException: pass
        time.sleep(3 * (i + 1))
    raise RuntimeError(url)
idx = get("https://www.smard.de/app/chart_data/411/DE/index_hour.json")["timestamps"]; start = int(pd.Timestamp("2025-10-18", tz="UTC").timestamp() * 1000)
use = [t for t in idx if t >= max(x for x in idx if x <= start)]
s = pd.DataFrame([r for t in use for r in get(f"https://www.smard.de/app/chart_data/411/DE/411_DE_hour_{t}.json")["series"]], columns=["ms", "off"]); s.index = pd.to_datetime(s.ms, unit="ms", utc=True)
de_act = pd.read_parquet("data/raw/ref_DE_410.parquet").set_index("timestamp_utc").mw
j = pd.concat([de_act.rename("a"), s.off.rename("f")], axis=1).loc[test.index.min():test.index.max()].dropna()
print("DE-level official (series 411/DE) vs DE actual (410/DE), test window: MAE %.0f MWh/h, MAPE %.2f%%, bias %.0f (%.2f%%), n=%d" % ((j.f - j.a).abs().mean(), 100 * ((j.f - j.a).abs() / j.a).mean(), (j.f - j.a).mean(), 100 * (j.f - j.a).mean() / j.a.mean(), len(j)))
