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
