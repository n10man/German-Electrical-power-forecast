# Germany electricity demand forecasting (4 grid zones) + interactive map

Status: skeleton (Phase 0). Sections are filled in as phases complete.

## Problem
Forecast hourly grid load for Germany's four TSO control areas (50Hertz, Amprion, TenneT, TransnetBW), with prediction intervals. Portfolio baseline, not production-grade. **Status: Phases 0-4 done (validation results only); stress tests, sealed-test evaluation and the map are still to do.**

## Data and licences
See `data/DATA_SOURCES.md` (SMARD grid load, series ID 410, CC BY 4.0 to be re-verified; Open-Meteo historical weather; `holidays` package). Hourly UTC; Berlin time only for calendar features. Dataset ends 14 days before the last available hour (`scripts/build_dataset.py`). Split by time only: train < 2024-10-25, validation 2024-10-25..2025-10-24, sealed test 2025-10-25..2026-10-24 (written to a separate file, not read before Phase 6).

## Method
- Features: calendar (Berlin hour, weekday, month, day of year, weekend, bridge day), zone holiday share, zone-average observed weather (temperature, humidity, wind, shortwave radiation, cloud cover), load lags 24/48/168/336 h (never <24 h; tested in `tests/test_leakage.py`).
- Model: **LightGBM** (v4.7.0), one regressor per zone (`src/gepf/models.py`). A pooled model with zone as a feature was tested and was 4% worse. scikit-learn HistGradientBoosting was not needed.
- Uncertainty: per-zone LightGBM quantile models (2.5/10/50/90/97.5%) plus conformalized quantile regression (CQR) calibrated on validation.
- Every experiment, rule and decision: `results/EXPERIMENTS.md`.

## Results (validation only, MAE in MWh/h)
| Zone | B1 last week | Model (M2) | median (q50) |
|---|---|---|---|
| 50Hertz | 922 | 531 | 543 |
| Amprion | 1003 | 524 | 523 |
| TenneT | 791 | 355 | 359 |
| TransnetBW | 450 | 164 | 166 |

Caveats: weather inputs are observed values, not forecasts (so this is optimistic; Phase 5 will test noise); holiday/hot/cold subsets are small.

## Prediction intervals / coverage
Raw quantile bands under-cover (nominal 80% -> 65%, 95% -> 84%). With CQR (calibrate on one validation half, score on the other) average coverage is 80.0% / 94.2%, but uneven by zone, season and hour (worst around midday). Plot: `results/figures/coverage.png`.

## Stress tests
To do (Phase 5).

## Limitations
To be completed in Phase 6 (grid load is not total consumption; zones not states; shifting patterns; not better than TSO forecasts).

## How to run
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # LightGBM needs libomp on macOS (brew install libomp)
python scripts/download_load.py && python scripts/download_reference.py && python scripts/download_weather.py   # slow (~1.5 h)
python scripts/build_dataset.py
PYTHONPATH=src pytest
python scripts/baselines.py && python scripts/run_models.py M1 M2 M3 M4 && python scripts/run_quantiles.py
```
