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

def zone_frame(z, since_ms=None, get=fetch):
    """Quarter-hourly rows of one zone. since_ms: only weekly chunks that start at or after this timestamp (used by the snapshot refresh)."""
    stamps = get(IDX.format(z=z))["timestamps"]
    if since_ms is not None: stamps = [t for t in stamps if t >= since_ms]
    rows = []
    for ts in stamps:
        for t, v in get(BASE.format(z=z, ts=ts))["series"]:
            rows.append((t, v))
    df = pd.DataFrame(rows, columns=["ts_ms", "load_mw"])
    df["timestamp_utc"] = pd.to_datetime(df.ts_ms, unit="ms", utc=True)
    return df.drop(columns="ts_ms")

def main():
    for z in ZONES:
        f = OUT / f"load_{z}.parquet"
        if f.exists(): print("skip", z); continue
        df = zone_frame(z); df.to_parquet(f)
        print(z, len(df), df.timestamp_utc.min(), df.timestamp_utc.max(), df.load_mw.isna().sum(), "NaN")

if __name__ == "__main__":
    main()
