"""Archived PAST weather forecasts from Open-Meteo's Previous Runs API (no key), hourly UTC, for the 12 points used so far.

For each valid time, '<var>_previous_dayK' is the forecast for that time that was issued K days earlier (K = 1..7);
plain '<var>' is the most recent short-lead value. 12 requests in total (one per city), each asking for ~5.9 years.
Output: data/raw/forecast_archive.parquet (+ forecast_archive_meta.json with download time and coverage). Gitignored."""
import json, sys, time
from pathlib import Path
import requests, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_weather import POINTS  # noqa: E402  (same 12 locations as the observed-weather download)

URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
BASE = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "shortwave_radiation", "cloud_cover"]
LEADS = range(1, 8)
HOURLY = BASE + [f"{v}_previous_day{k}" for v in BASE for k in LEADS]
START = "2021-01-01"
OUT = Path("data/raw")

def fetch(lat, lon, a, b):
    for attempt in range(8):
        try:
            r = requests.get(URL, params=dict(latitude=lat, longitude=lon, start_date=a, end_date=b,
                                              hourly=",".join(HOURLY), timezone="UTC"), timeout=600)
            if r.status_code == 200: return pd.DataFrame(r.json()["hourly"])
            print("retry", r.status_code, r.text[:120], flush=True)
        except requests.RequestException as e:
            print("retry", type(e).__name__, flush=True)
        time.sleep(60 * (attempt + 1))
    raise RuntimeError("download failed")

def main():
    end = pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
    parts = OUT / "fa_parts"; parts.mkdir(exist_ok=True)
    spans = [(f"{y}-01-01", min(f"{y}-12-31", end)) for y in range(2021, int(end[:4]) + 1)]  # one request per city and year
    frames = []
    for z, pts in POINTS.items():
        for name, lat, lon in pts:
            f = parts / f"{z}_{name}.parquet"
            if not f.exists():
                h = pd.concat([fetch(lat, lon, a, b) for a, b in spans], ignore_index=True)
                h["timestamp_utc"] = pd.to_datetime(h.pop("time"), utc=True); h["zone"], h["point"] = z, name
                h.to_parquet(f); time.sleep(20)
            h = pd.read_parquet(f); frames.append(h); print(z, name, len(h), flush=True)
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(OUT / "forecast_archive.parquet")
    cov = {c: [str(df.loc[df[c].notna(), "timestamp_utc"].min()), str(df.loc[df[c].notna(), "timestamp_utc"].max()),
               float(df[c].notna().mean())] for c in HOURLY}
    json.dump(dict(downloaded_utc=pd.Timestamp.now("UTC").isoformat(), url=URL, start=START, end=end, calls=len(frames) * len(spans),
                   coverage_first_last_fracnotna=cov), open(OUT / "forecast_archive_meta.json", "w"), indent=1)
    print("saved", df.shape)

if __name__ == "__main__":
    main()
