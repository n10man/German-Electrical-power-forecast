"""Download SMARD grid load (filter 410) per control area, quarter-hourly, weekly chunks. Saves raw JSON-derived parquet to data/raw."""
import json, time, sys
from pathlib import Path
import requests, pandas as pd

ZONES = ["50Hertz", "Amprion", "TenneT", "TransnetBW"]
BASE = "https://www.smard.de/app/chart_data/410/{z}/410_{z}_quarterhour_{ts}.json"
IDX = "https://www.smard.de/app/chart_data/410/{z}/index_quarterhour.json"
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
    f = OUT / f"load_{z}.parquet"
    if f.exists(): print("skip", z); continue
    stamps = fetch(IDX.format(z=z))["timestamps"]
    rows = []
    for ts in stamps:
        for t, v in fetch(BASE.format(z=z, ts=ts))["series"]:
            rows.append((t, v))
    df = pd.DataFrame(rows, columns=["ts_ms", "load_mw"])
    df["timestamp_utc"] = pd.to_datetime(df.ts_ms, unit="ms", utc=True)
    df.drop(columns="ts_ms").to_parquet(f)
    print(z, len(df), df.timestamp_utc.min(), df.timestamp_utc.max(), df.load_mw.isna().sum(), "NaN")
