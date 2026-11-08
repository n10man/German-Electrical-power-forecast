"""Open-Meteo historical weather (no key), hourly, UTC, for representative points per zone."""
import time
from pathlib import Path
import requests, pandas as pd

POINTS = {  # zone -> [(name, lat, lon)]  representative load centres
    "50Hertz": [("Berlin", 52.52, 13.40), ("Hamburg", 53.55, 9.99), ("Leipzig", 51.34, 12.37)],
    "Amprion": [("Cologne", 50.94, 6.96), ("Dortmund", 51.51, 7.47), ("Frankfurt", 50.11, 8.68)],
    "TenneT": [("Munich", 48.14, 11.58), ("Hannover", 52.37, 9.73), ("Nuremberg", 49.45, 11.08)],
    "TransnetBW": [("Stuttgart", 48.78, 9.18), ("Mannheim", 49.49, 8.47), ("Freiburg", 47.99, 7.85)],
}
VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,cloud_cover"
URL = "https://archive-api.open-meteo.com/v1/archive"
OUT = Path("data/raw"); OUT.mkdir(parents=True, exist_ok=True)
START, END = "2014-12-31", pd.Timestamp.utcnow().strftime("%Y-%m-%d")

frames = []
for z, pts in POINTS.items():
    for name, lat, lon in pts:
        for attempt in range(6):
            r = requests.get(URL, params=dict(latitude=lat, longitude=lon, start_date=START, end_date=END,
                                              hourly=VARS, timezone="UTC"), timeout=120)
            if r.status_code == 200: break
            time.sleep(15 * (attempt + 1))
        r.raise_for_status()
        h = pd.DataFrame(r.json()["hourly"])
        h["timestamp_utc"] = pd.to_datetime(h.pop("time"), utc=True)
        h["zone"], h["point"] = z, name
        frames.append(h); print(z, name, len(h), flush=True)
pd.concat(frames).to_parquet(OUT / "weather.parquet")
