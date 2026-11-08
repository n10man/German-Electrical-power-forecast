# Data sources

(Committed; the raw data itself is NOT committed — see .gitignore. Re-create with the scripts in `scripts/`.)

## Load — SMARD, Bundesnetzagentur
- Series used: **"Grid load" (Netzlast / Stromverbrauch: Gesamt)**, SMARD filter ID **410** (Electricity consumption > Actual consumption > Grid load).
- Regions: `50Hertz`, `Amprion`, `TenneT`, `TransnetBW` (control areas); `DE` (national) used only for sanity checks.
- Resolution: quarter-hourly (zones, `*_quarterhour_*`), hourly (DE reference). Values are **MWh per period**; hourly value = sum of the four quarter-hours (= average MW).
- URLs: `https://www.smard.de/app/chart_data/410/{region}/index_quarterhour.json` then `.../410_{region}_quarterhour_{timestamp}.json` (weekly chunks); reference: `.../{id}/DE/{id}_DE_hour_{timestamp}.json`. Scripts: `scripts/download_load.py`, `scripts/download_reference.py`.
- Download date: 2026-11-08. Data range: 2014-12-28 (empty before 2015-01-01) to 2026-11-08 (latest published quarter-hour 06:15 UTC).
- Licence/terms: SMARD content is published under CC BY 4.0 ("Bundesnetzagentur | SMARD.de"). **Verify the current terms on https://www.smard.de before publishing.**
- Other similar series that exist and were NOT used:
  - **4359 Residual load** (load minus wind/solar) — not total consumption.
  - **4387 Hydro pumped-storage consumption** — only pumping demand (~1 GW avg), not total load.
  - (SMARD also offers a "grid load incl. pumped storage" variant; not downloaded. The brief asks for plain grid load.)
  - Generation and price series — irrelevant.
- Why 410: the owner's reference values (SMARD website, grid load, DE hourly: 60,003 / 59,180 / 56,841 MWh) are reproduced **exactly** by series 410 at **2022-06-01 16:00, 17:00, 18:00 UTC**. The brief labelled them "2022-06-02 00:00-03:00 local"; that corresponds to UTC+8 (the owner's browser timezone), i.e. 18:00-21:00 Berlin time, not Berlin midnight. Series 4359 and 4387 do not match.
- Timestamps: stored in UTC. Berlin local time is used only for calendar features. DST days: 23 h (2022-03-27) and 25 h (2022-10-30) local; tested.

## Weather — Open-Meteo Historical Weather API (archive-api.open-meteo.com)
- No key. Hourly, UTC: temperature_2m, relative_humidity_2m, wind_speed_10m, shortwave_radiation, cloud_cover. Three representative cities per zone (see `scripts/download_weather.py`), averaged per zone.
- Licence: CC BY 4.0 (attribution to Open-Meteo; non-commercial free tier). Verify at https://open-meteo.com/en/terms.
- Caveat: these are reanalysis/observed-style values, i.e. "perfect" weather. A real day-ahead forecast would use forecast weather (errors) — addressed by the noise stress test in Phase 5. The newest days may be model-filled.

## Holidays
- Python `holidays` package (`holidays.Germany(subdiv=state)`), state-level. Zone-level feature `holiday_share` = equal-weight share of the zone's states with a holiday that local day. State-to-zone assignment is an approximation (TSO areas do not follow state borders).

## State shapes (Phase 7)
- To be chosen and licence-checked in Phase 7.
