"""Download SMARD 'Forecasted consumption' (filter 411, TSO day-ahead forecast of grid load) per control area, quarter-hourly,
for the validation + test years only (from 2024-10-18, one week before the validation start). Values: MWh per 15 min.
Used ONLY as an external benchmark (see results/EXPERIMENTS.md, entry O1)."""
import time
from pathlib import Path
import requests, pandas as pd
ZONES = ["50Hertz", "Amprion", "TenneT", "TransnetBW"]; FID = 411
START_MS = int(pd.Timestamp("2024-10-18", tz="UTC").timestamp() * 1000)
OUT = Path("data/raw"); OUT.mkdir(parents=True, exist_ok=True)

def fetch(url, tries=8):
    time.sleep(0.15)
    for i in range(tries):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200: return r.json()
        except requests.RequestException: pass
        time.sleep(3 * (i + 1) ** 1.5)
    raise RuntimeError(f"failed: {url}")

for z in ZONES:
    f = OUT / f"official_forecast_{z}.parquet"
    if f.exists(): print("skip", z); continue
    stamps = fetch(f"https://www.smard.de/app/chart_data/{FID}/{z}/index_quarterhour.json")["timestamps"]
    first = max([t for t in stamps if t <= START_MS] or stamps[:1]); use = [t for t in stamps if t >= first]
    rows = [r for ts in use for r in fetch(f"https://www.smard.de/app/chart_data/{FID}/{z}/{FID}_{z}_quarterhour_{ts}.json")["series"]]
    d = pd.DataFrame(rows, columns=["ts_ms", "fc_mwh_qh"]); d["timestamp_utc"] = pd.to_datetime(d.ts_ms, unit="ms", utc=True)
    d = d.drop(columns="ts_ms").drop_duplicates("timestamp_utc").sort_values("timestamp_utc"); d.to_parquet(f)
    print(z, len(d), d.timestamp_utc.min(), d.timestamp_utc.max(), "NaN:", int(d.fc_mwh_qh.isna().sum()), flush=True)
