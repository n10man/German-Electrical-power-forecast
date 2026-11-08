# Project: Germany electricity demand forecasting (zones) + interactive map

Goal: a portfolio baseline that forecasts hourly electricity load for Germany's four grid zones (50Hertz, Amprion, TenneT, TransnetBW), with honest prediction intervals, stress tests, and an interactive map. Not production-grade; be honest about limits.

## Data
- Load: SMARD (Bundesnetzagentur), no key. Total consumption per control area, quarter-hourly, from 2015. Resample to hourly. Verify all four zones exist for the full period; report gaps.
- Weather: free source such as Open-Meteo historical (no key), for a few representative points per zone, hourly.
- Holidays: python `holidays` package, per German state; build a zone-level holiday share feature.
- Timezone: store UTC; handle Europe/Berlin daylight-saving shifts correctly; test it.
- Dedupe, check gaps, document every cleaning step.
- State shapes: open GeoJSON of the 16 German states; check its licence and note it in the README.

## Phases (work through automatically; stop only at CHECKPOINTS)
0. Setup: .gitignore (data/, .venv, caches), venv, requirements.txt, folder layout, README skeleton, results/EXPERIMENTS.md, first local commit.
1. Data: download, clean, features, time-based split: train up to 2 years before the end, validation = next 12 months, test = last 12 months (sealed). Add automated leakage tests.
2. Baselines: same hour last week, same hour yesterday. Metrics per zone: MAE, RMSE, MAPE.
   >>> CHECKPOINT 1 (data + baselines)
3. Models: LightGBM per zone (or one model with zone as a feature; test both). Calendar, holiday, weather, and lag features (lags >= 24h only). Keep what beats the baselines on validation.
4. Uncertainty: quantile models (e.g. 2.5/10/50/90/97.5%) plus conformal calibration on validation. Report coverage: do the 80% and 95% bands actually contain that share of real values? Plot it.
   >>> CHECKPOINT 2 (models + uncertainty)
5. Stress tests: (a) error on public holidays, bridge days, heat waves, cold snaps; (b) train before 2020, evaluate 2020-22 to show shift; (c) add noise to weather inputs to simulate forecast error; (d) simulate missing weather/load hours. Report where the model fails.
6. Final: run scripts/final_eval.py --confirm-final ONCE on the sealed test period. Finish README: problem, data and licences, method, results table (baseline vs model), coverage, stress tests, limitations (grid load is not total consumption; zones not states; shifting patterns; not better than TSO forecasts), how to run.
   >>> CHECKPOINT 3 (before the map)
7. Map (static site in /site, no server): data from precomputed JSON per zone and date (actual, forecast, 80% and 95% bands, hourly). Own map from state GeoJSON, states coloured into 4 zone groups. Hover shows state and its zone. Click opens a small popup: pick a date (within validation+test periods), then an hour (or full day chart). Popup states clearly: "Forecast is for the [zone] grid zone." Build with plain HTML/JS (Leaflet or D3), no API keys. Test it locally.
8. (Only if the owner asks) future dates via a free weather-forecast API.

## Done = reproducible from README, all tests pass, local commits only, nothing pushed.

## Data verification (mandatory, Phase 1)
- Use SMARD "total load" / actual consumption (NOT residual load, NOT pumped-storage consumption, NOT generation, NOT prices). If several similar series exist, list them and say why you chose this one.
- Write data/DATA_SOURCES.md (committed, but not the raw data): exact SMARD series/filter IDs, region names, resolution, download URLs, download date, date range, licence/terms.
- Sanity checks, written as automated tests and reported at Checkpoint 1:
  - Hourly timestamps: no duplicates; gaps counted per zone; daylight-saving days handled.
  - Sum of the four zones is within a few percent of SMARD's national total load; report the difference.
  - Magnitudes are plausible: national average load roughly 50-60 GW, yearly total roughly 450-500 TWh. Flag anything far outside.
  - Clear daily and weekly cycles; Sundays/holidays lower than weekdays; winter higher than summer.
  - Plot one week and one year per zone.
- At Checkpoint 1 print a short "data card": series name, zones, period, units, row counts, gaps, the sanity-check results, and 3 specific timestamps with their values so the owner can compare them with the SMARD website.
- Note: on the SMARD website the correct series is called "Grid load" under Electricity consumption > Actual consumption. It is NOT "Residual load" and NOT "Hydro pumped storage". State in data/DATA_SOURCES.md which series name and ID you used.

## Known reference values (from the SMARD website, grid load, Germany total, hourly)
- 2022-06-02 00:00-01:00 local time: 60,003 MWh
- 2022-06-02 01:00-02:00 local time: 59,180 MWh
- 2022-06-02 02:00-03:00 local time: 56,841 MWh
Your hourly Germany-wide series must reproduce these (allowing for UTC vs local time, which you must state) or explain any difference. Use the "grid load" series (NOT "grid load incl. hydro pumped storage", NOT "residual load"), and say in data/DATA_SOURCES.md that the other variants exist and why you did not use them.
