"""Download SMARD national (DE) series used only for sanity checks, hourly resolution to be fast.
410 = Grid load (Netzlast), 4387 = Grid load incl. hydro pumped storage, 4359 = Residual load."""
import sys, time
from pathlib import Path
import requests, pandas as pd
OUT = Path("data/raw"); OUT.mkdir(parents=True, exist_ok=True)
def fetch(url, tries=8):
    time.sleep(0.15)
    for i in range(tries):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200: return r.json()
        except requests.RequestException: pass
        time.sleep(3 * (i + 1) ** 1.5)
    raise RuntimeError(url)
for fid in sys.argv[1:] or ["410", "4387", "4359"]:
    f = OUT / f"ref_DE_{fid}.parquet"
    if f.exists(): continue
    stamps = fetch(f"https://www.smard.de/app/chart_data/{fid}/DE/index_hour.json")["timestamps"]
    rows = [r for ts in stamps for r in fetch(f"https://www.smard.de/app/chart_data/{fid}/DE/{fid}_DE_hour_{ts}.json")["series"]]
    df = pd.DataFrame(rows, columns=["ts_ms", "mw"]); df["timestamp_utc"] = pd.to_datetime(df.ts_ms, unit="ms", utc=True)
    df.drop(columns="ts_ms").to_parquet(f); print(fid, len(df), flush=True)
