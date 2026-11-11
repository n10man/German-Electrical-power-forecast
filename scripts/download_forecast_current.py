"""Download the CURRENT 16-day Open-Meteo weather forecast (no key) for the 12 locations. 12 requests, run by hand (no scheduler).
Saves data/raw/forecast_current_<UTC timestamp>.parquet (gitignored) with the download time inside. Visitors' browsers never call Open-Meteo."""
import sys, time
from pathlib import Path
import requests, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_weather import POINTS  # noqa: E402

URL = "https://api.open-meteo.com/v1/forecast"
VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,cloud_cover"   # same variables and default units (wind km/h) as the archive

def main():
    stamp = pd.Timestamp.now("UTC"); frames = []
    for z, pts in POINTS.items():
        for name, lat, lon in pts:
            for attempt in range(6):
                r = requests.get(URL, params=dict(latitude=lat, longitude=lon, hourly=VARS, forecast_days=16, past_days=3, timezone="UTC"), timeout=120)
                if r.status_code == 200: break
                time.sleep(30 * (attempt + 1))
            r.raise_for_status()
            h = pd.DataFrame(r.json()["hourly"]); h["timestamp_utc"] = pd.to_datetime(h.pop("time"), utc=True)
            h["zone"], h["point"], h["downloaded_utc"] = z, name, stamp.isoformat(); frames.append(h); print(z, name, len(h), h.timestamp_utc.min(), h.timestamp_utc.max(), flush=True)
            time.sleep(2)
    out = Path("data/raw") / f"forecast_current_{stamp.strftime('%Y%m%dT%H%M%SZ')}.parquet"
    pd.concat(frames, ignore_index=True).to_parquet(out); print("saved", out)

if __name__ == "__main__":
    main()
