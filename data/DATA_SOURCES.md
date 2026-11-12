# Data sources

(Committed; the raw data itself is NOT committed — see .gitignore. Re-create with the scripts in `scripts/`.)

## Load — SMARD, Bundesnetzagentur
- Series used: **"Grid load" (Netzlast / Stromverbrauch: Gesamt)**, SMARD filter ID **410** (Electricity consumption > Actual consumption > Grid load).
- Regions: `50Hertz`, `Amprion`, `TenneT`, `TransnetBW` (control areas); `DE` (national) used only for sanity checks.
- Resolution: quarter-hourly (zones, `*_quarterhour_*`), hourly (DE reference). Values are **MWh per period**; hourly value = sum of the four quarter-hours (= average MW).
- URLs: `https://www.smard.de/app/chart_data/410/{region}/index_quarterhour.json` then `.../410_{region}_quarterhour_{timestamp}.json` (weekly chunks); reference: `.../{id}/DE/{id}_DE_hour_{timestamp}.json`. Scripts: `scripts/download_load.py`, `scripts/download_reference.py`.
- Download date: 2026-11-08. Data range: 2014-12-28 (empty before 2015-01-01) to 2026-11-08 (latest published quarter-hour 06:15 UTC).
- Licence/terms: checked on 2026-11-09, see "Terms of use" at the end of this file (CC BY 4.0, credit "Bundesnetzagentur | SMARD.de"; flags there).
- Other similar series that exist and were NOT used:
  - **4359 Residual load** (load minus wind/solar) — not total consumption.
  - **4387 Hydro pumped-storage consumption** — only pumping demand (~1 GW avg), not total load.
  - (SMARD also offers a "grid load incl. pumped storage" variant; not downloaded. I use plain grid load.)
  - Generation and price series — irrelevant.
- Why 410: the reference values I checked against (SMARD website, grid load, DE hourly: 60,003 / 59,180 / 56,841 MWh) are reproduced **exactly** by series 410 at **2022-06-01 16:00, 17:00, 18:00 UTC**. They were first noted as "2022-06-02 00:00-03:00 local"; that corresponds to UTC+8 (the browser timezone they were read in), i.e. 18:00-21:00 Berlin time, not Berlin midnight. Series 4359 and 4387 do not match.
- Timestamps: stored in UTC. Berlin local time is used only for calendar features. DST days: 23 h (2022-03-27) and 25 h (2022-10-30) local; tested.

## Weather — Open-Meteo Historical Weather API (archive-api.open-meteo.com)
- No key. Hourly, UTC: temperature_2m, relative_humidity_2m, wind_speed_10m, shortwave_radiation, cloud_cover. Three representative cities per zone (see `scripts/download_weather.py`), averaged per zone.
- Licence/terms: checked on 2026-11-09, see "Terms of use" at the end of this file (CC BY 4.0, but the free API is **non-commercial only**; flags there).
- Caveat: these are reanalysis/observed-style values, i.e. "perfect" weather. A real (rolling 24-hour-ahead) forecast would use forecast weather (errors) — addressed by the noise stress test in Phase 5. The newest days may be model-filled.

## Holidays
- Python `holidays` package (`holidays.Germany(subdiv=state)`), state-level. Zone-level feature `holiday_share` = equal-weight share of the zone's states with a holiday that local day. State-to-zone assignment is an approximation (TSO areas do not follow state borders).

## State shapes (Phase 7 map)
- BKG (Bundesamt für Kartographie und Geodäsie) VG250, layer `vg250_lan` (land areas, gf=4), downloaded 2026-11-08 from the official WFS `https://sgx.geodatenzentrum.de/wfs_vg250` as GeoJSON (`scripts/download_states.py`); 16 features.
- Licence: Datenlizenz Deutschland – Namensnennung 2.0 (https://www.govdata.de/dl-de/by-2-0), as stated in the service's own capabilities document. Required credit line (BKG's own wording): "© BKG (Jahr des letzten Datenbezugs) dl-de/by-2-0, Datenquellen: https://sg.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_vg_nuts.pdf", used with the year 2026 (download year). My `site/data/states.geojson` is a simplified derivative (tiny islands dropped, coordinates rounded).

## Grid-zone assignment of states (Phase 7 map)
- SMARD "Control area": https://www.smard.de/page/en/wiki-article/5884/205642 (qualitative description of the four areas).
- Deutscher Bundestag, Wissenschaftliche Dienste, WD 5 - 3000 - 117/16 (2017), section 2 (lists states per operator; quotes netztransparenz.de and the ewi Energy Research & Scenarios study): https://www.bundestag.de/resource/blob/494452/29f6a6424b8d97b6aad95ff22cfa6577/WD-5-117-16-pdf.pdf
- Also read: netzentwicklungsplan.de "Basisinformationen Übertragungsnetzbetreiber und ihre Regelzonen" (2012), qualitative only. Amprion's own page states only that its network spans seven federal states.
- Limits: no source gives area or load shares; the dominant zone per state is a judgement and five states are flagged as split (NI, NW, HE, BW, BY).

## Official day-ahead forecast (benchmark only, added after Phase 7)
- SMARD "Forecasted consumption", filter ID **411**, regions 50Hertz / Amprion / TenneT / TransnetBW (and DE for a sanity check), quarter-hourly, MWh per 15 min; URLs `https://www.smard.de/app/chart_data/411/{region}/411_{region}_quarterhour_{timestamp}.json`; downloaded 2026-11-09 for 2024-10-18 onwards (`scripts/download_official_forecast.py`). The API does not return a series name; I identified 411 from SMARD's documentation plus its scale (same size as grid load 410).
- What it is (SMARD): the TSOs submit the predicted value the day before, based on day-ahead trading results and other empirical data, and it may be updated if the change exceeds 10% (https://www.smard.de/en/wiki-article/5884/6036); the forecast data is submitted by the four TSOs for their control areas and aggregated for Germany (https://www.smard.de/page/en/wiki-article/5884/206318/forecast-data).
- Same terms as the load series (see "Terms of use" below).

## Terms of use: what the providers actually say (pages fetched 2026-11-09)
Only short quotes; read the live pages before relying on them. This is a reading of public pages, not legal advice.

### SMARD (Bundesnetzagentur): load and official forecast
Page: https://www.smard.de/en/datennutzung ("Data use"). Wording:
- "In accordance with section 111d of the Energy Industry Act (Energiewirtschaftsgesetz - EnWG), the data published on this platform has been made freely available for public use. Therefore, data from this website can be downloaded and saved free of charge."
- "Data from the section Market data visuals, which can be downloaded showing longer periods of time from the Download section, is licensed under a Creative Commons Attribution 4.0 International Licence." (licence text: https://creativecommons.org/licenses/by/4.0/)
- "Data under a CC BY 4.0 licence may be shared, redistributed and adapted as long as appropriate credit is given. Data from the website www.smard.de should be attributed to "Bundesnetzagentur | SMARD.de"."
- "The Bundesnetzagentur does not assume any responsibility for the correctness and completeness of the data."
- Imprint (https://smard.de/en/impressum): "Unless otherwise indicated, the content of this website is licensed under the Creative Commons Attribution-No Derivative 4.0 International Licence" and points to the Data use page for market data. This covers the website's text and layout, not the data; nothing of the site's text or layout is copied here.

What this means here: CC BY 4.0 allows sharing and adapting, including commercial use (that is a property of CC BY 4.0; the Data use page adds no restriction), provided the credit is given and changes are indicated. The repository therefore credits "Bundesnetzagentur | SMARD.de" in the README and in the map footer, and states that the quarter-hourly values were summed to hourly and used to train and evaluate models (a change). The committed files that contain SMARD values are `site/data/{zone}.json` (hourly actual load) and the results tables.

Flags (unclear or to watch):
1. **Unofficial endpoint.** I downloaded the data from the JSON endpoints behind the SMARD charts (`https://www.smard.de/app/chart_data/...`), not from the "Download section" that the licence sentence names. They are undocumented, and the Data use page says nothing about automated access or rate limits. The data is the same as in the charts, but the terms for this access path are not stated.
2. **The terms may change.** The page says: "We are currently conducting a thorough examination of legal licensing issues relating to wholesale prices as part of the ongoing HEDWIG determination proceedings." and "We are aiming to develop a new concept for the use of the data." This project does not use prices, but the data-use concept as a whole may change.
3. The forecast series (filter 411) and the national totals are part of the same market-data visuals; the page does not single them out.

### Open-Meteo: weather
Pages: https://open-meteo.com/en/terms ("Terms & Privacy") and https://open-meteo.com/en/licence. Wording:
- "By using the Free API for non-commercial use you agree to following terms: Less than 10'000 API calls per day, 5'000 per hour and 600 per minute. You may only use the free API services for non-commercial purposes. You accept to the CC-BY 4.0 licence, as specified in the licence conditions."
- Examples that qualify as non-commercial: "Private or non-profit websites or apps that do not have subscriptions or advertising.", "Public research conducted at public institutions.", "Use in educational content."
- Examples considered commercial: "Websites or apps that have subscriptions or display advertisements.", "Commercial products or promotional activities.", "Undisclosed research at commercial entities."
- "If you plan to use our service for commercial purposes or require additional API calls, we kindly request you to consider subscribing to our API plans" (https://open-meteo.com/en/pricing).
- Licence page: "API data are offered under Attribution 4.0 International (CC BY 4.0)" and "You must give appropriate credit, provide a link to the licence, and indicate if changes were made." and "You must include a link next to any location Open-Meteo data are displayed", for example "Weather data by Open-Meteo.com" linking to https://open-meteo.com/. The same page lists the underlying sources (for example "Weather reanalysis ... from Copernicus Climate Change Service C3S" and ECMWF forecasts under CC-BY) with their own licence links.

What this means here: the weather download made 12 requests (one per city), far below the call limits. No Open-Meteo data is committed (`data/` is gitignored); only model outputs derived from it are. The README and the map footer carry the credit "Weather data by Open-Meteo.com" with the licence link, and say that the values were averaged over three cities per zone.

Flags (unclear or restricted):
1. **Commercial use is restricted.** The free API is for non-commercial use only. Anyone who re-runs `scripts/download_weather.py` for a commercial purpose (ads, subscriptions, a commercial product, undisclosed research at a company) needs a paid plan. The CC BY 4.0 licence on the data is a separate matter from this API restriction.
2. **A public portfolio is a grey area.** A public, ad-free GitHub repository fits "private or non-profit ... apps that do not have subscriptions or advertising", but the terms also list "promotional activities" as commercial, and a portfolio used to promote its author's work could be read that way. The terms do not decide this. If that matters to you, ask Open-Meteo, or switch to a paid plan, before relying on the free API for this repository.
3. **Underlying source terms not checked.** I read Open-Meteo's own pages, not the separate licence pages of the reanalysis and weather-service sources it lists. I did not pass a model selection to the archive API, so I do not know which underlying dataset produced each value.
4. The terms say Open-Meteo "reserve[s] the right to block applications and IP addresses that misuse our service" and can change terms; I did not see a version or date on the pages.

### BKG state boundaries
Terms as stated by the service itself (see the "State shapes" section above): Datenlizenz Deutschland - Namensnennung 2.0, with BKG's own credit line. Not re-fetched beyond the capabilities document.

### Not covered
The Python `holidays` package (MIT licence, verified on 2026-11-12 from the installed package: version 0.108, licence expression MIT, licence file included in its distribution metadata), the Bundestag paper (cited, not redistributed), and the repository's own licence: the code is MIT-licensed (see `LICENSE`, copyright 2026 n10man); that does not change the data terms above, which stay with the data and anything derived from it.

## Future forecast (added 2026-11-11, branch feature/future-forecast)
### SMARD load, downloaded again
`scripts/download_load.py` was re-run on 2026-11-10 (same filter 410, same four control areas, same verification rules); the old raw files were kept in `data/raw/_old_load_20261110/` (gitignored). The new download reaches 2026-11-10 for the latest valid hours (trailing quarter-hours are empty placeholders). `data/processed/` was NOT rebuilt, so every earlier result, model and map file is unchanged. The forecast origin is the last hour for which all four zones have actual load: 2026-11-10 07:00 UTC (Amprion was the slowest zone). The newest hours of SMARD may still be revised.

### Open-Meteo: archived past forecasts and the current forecast
- **Past forecasts (training/validation/test inputs).** Previous Runs API, `https://previous-runs-api.open-meteo.com/v1/forecast`, variables `temperature_2m, relative_humidity_2m, wind_speed_10m, shortwave_radiation, cloud_cover` and their `_previous_day1` ... `_previous_day7` versions (the forecast for a time issued K days earlier), hourly, UTC, default units (wind in km/h), 12 city points (same as the observed weather), 2021-01-01 to 2026-11-10, downloaded 2026-11-10/11 by `scripts/download_forecast_archive.py` into `data/raw/forecast_archive.parquet` (not committed). **Coverage found:** temperature leads 1-7 from 2021-03-24..30; humidity, wind, radiation and cloud leads 1-7 only from 2024-01-19..25; no leads beyond 7 days. The "Historical Forecast API" (`historical-forecast-api.open-meteo.com`) was probed too: it reaches back to 2017 but is a stitch of the first hours of each model run, so it does not represent a forecast made several days ahead and was not used. Default "best match" model selection was used (not pinned), so the underlying model mix can differ over time and from the live forecast.
- **Current forecast (serving input).** `https://api.open-meteo.com/v1/forecast`, same five variables, `forecast_days=16`, `past_days=3`, 12 requests (one per city), run by hand by `scripts/download_forecast_current.py` on 2026-11-11 05:34 UTC into `data/raw/forecast_current_20261111T053447Z.parquet` (the download time is also stored in the file and shown on the page). Not scheduled; visitors' browsers never call Open-Meteo. Only days 1-7 can enter a model, and only 6 of 36 models use weather.
- **Terms relied on** (https://open-meteo.com/en/terms, re-read 2026-11-11): "By using the Free API for non-commercial use you agree to following terms: Less than 10'000 API calls per day, 5'000 per hour and 600 per minute. You may only use the free API services for non-commercial purposes. You accept to the CC-BY 4.0 licence, as specified in the licence conditions." and the examples "Private or non-profit websites or apps that do not have subscriptions or advertising." (non-commercial) versus "Commercial products or promotional activities." (commercial). The grey-area flag above (a portfolio) still applies. Attribution (CC BY 4.0, licence page): the map page and the README carry a visible link "Weather data by Open-Meteo.com" to https://open-meteo.com/ and say CC BY 4.0.
- **Usage and an honest slip.** Open-Meteo counts a request as several calls when it asks for many days or variables. The archive download (72 requests of one year each, 40 variables) plus probes tripped the **per-minute and per-hour limits** (HTTP 429; the script waited and retried until it succeeded). I cannot see the server-side counter; by my estimate of the weighted calls, the day total stayed below 10,000, but it was not far from the 5,000-per-hour limit. In addition, an import side effect of my own script briefly started a re-download of the observed weather (about 4 requests) before I stopped it; it wrote nothing (`data/raw/weather.parquet` unchanged, dated 2026-11-08), and `scripts/download_weather.py` now has a `main()` guard. The current-forecast download itself was 12 small requests.

## Reuse notes (moved from the README on 2026-11-12)
- I fetched SMARD data from the undocumented endpoints behind its charts, not from its download section, and SMARD says it is reviewing its data-use concept (see the SMARD flags above).
- The MIT licence of my code does not change the data terms. Files in this repository that contain or come from these data (`site/data/`, the results tables) keep the credits and terms of their sources.
- This is a non-commercial portfolio project with no advertising or subscriptions. Anyone who re-runs the download scripts for a commercial purpose must check the terms first; Open-Meteo requires a paid plan for commercial use.
- The terms pages were read on 2026-11-09. This is my reading of public terms, not legal advice.
