# Germany electricity demand forecasting (4 grid zones)

A portfolio baseline that forecasts **hourly grid load** for Germany's four TSO control areas (50Hertz, Amprion, TenneT, TransnetBW), with prediction intervals, stress tests and one sealed final test. It is not production-grade; see *Limitations*. **Status: data, models, uncertainty, stress tests and final evaluation are done. The interactive map (Phase 7) is not built yet.**

## Problem
Predict hourly load per zone, treating every load-based input as known at least 24 h before the target hour (lags of 24 h and more), so it mimics a day-ahead forecast. One important shortcut: the weather inputs are **observed/reanalysis values at the target hour**, not weather forecasts (see *Stress tests* for what weather error does).

## Data and licences
Details, series IDs, URLs and the reasoning for the series choice: [`data/DATA_SOURCES.md`](data/DATA_SOURCES.md). Raw data is not committed.
- **Load**: SMARD (Bundesnetzagentur) "Grid load", filter 410, quarter-hourly per control area (values are MWh per 15 min; the hourly value is the sum of the four). Downloaded 2026-11-08. Series 410 reproduces the three SMARD website reference values exactly (60,003 / 59,180 / 56,841 MWh at 2022-06-01 16:00-18:00 UTC; the brief had labelled them in the owner's UTC+8 time). The sum of the four zones matches SMARD's national total (median difference 0.000% on train+validation, 99% of hours within 2.4%).
- **Weather**: Open-Meteo historical archive (no key), hourly, three cities per zone averaged: temperature, humidity, wind speed, shortwave radiation, cloud cover.
- **Holidays**: Python `holidays` package per German state; the zone feature is the equal-weight share of the zone's states that have a holiday that Berlin-local day. The state-to-zone mapping in `src/gepf/data.py` is an approximation (TSO areas do not follow state borders).
- **Licences**: I recorded SMARD and Open-Meteo as CC BY 4.0 from memory and have **not verified** the current terms; check them before publishing. State shapes for the map: not chosen yet.
- Data checks (all automated in `tests/test_data_sanity.py`): no duplicate hours, regular hourly UTC index, no gaps inside train+validation (the 72-75 missing hours per zone in the raw range are almost all the empty days before 2015-01-01, plus a few unpublished newest hours), 23/25-hour daylight-saving days, plausible magnitudes (2019: 56.8 GW mean, 497 TWh), weekday > Sunday, winter > summer.

## Method
- **Split by time only**, dataset ends 14 days before the last available hour: train < 2024-10-25, validation 2024-10-25..2025-10-24, **test 2025-10-25..2026-10-24** (8,760 h each for validation and test). The test period lives in a separate file that was read once, by `scripts/final_eval.py --confirm-final`.
- **Features** (`src/gepf/data.py`, `src/gepf/models.py`): Berlin hour, weekday, month, day of year, weekend, bridge day (Monday/Friday next to a Tuesday/Thursday holiday), zone holiday share, five weather variables, and load lags 24/48/168/336 h. Leakage tests are in `tests/test_leakage.py`.
- **Model**: LightGBM 4.7.0, one regressor per zone (600 trees, learning rate 0.05, 31 leaves, seed 42). A pooled model with zone as a feature was 4% worse on validation. scikit-learn's HistGradientBoosting was not used because LightGBM imported.
- **Baselines**: B0 same hour yesterday, B1 same hour last week (B1 is the better one).
- **Intervals**: LightGBM quantile models (2.5/10/50/90/97.5%) trained on train only, plus conformalized quantile regression (CQR) with one offset per zone and band calibrated on the validation year. Calibration per hour of day (24 groups, or 6-hour blocks) was tried and rejected.
- Every experiment, rule (written before results), decision and commit: [`results/EXPERIMENTS.md`](results/EXPERIMENTS.md).

## Results
**Final sealed test (2025-10-25..2026-10-24), MAE in MWh/h, run once:**

| Zone | B1 last week | Model | Model vs B1 | Model MAPE | Validation MAE (model) |
|---|---|---|---|---|---|
| 50Hertz | 932 | 556 | -40% | 4.8% | 531 |
| Amprion | 1184 | 646 | -45% | 3.5% | 524 |
| TenneT | 948 | 479 | -50% | 3.1% | 355 |
| TransnetBW | 446 | 195 | -56% | 3.0% | 164 |

The model beat B1 in every zone, and also on public holidays, the hottest 5% and the coldest 5% of test days (model/B1 error ratio 0.20-0.29, 0.42-0.65 and 0.32-0.40). It was nevertheless worse on test than on validation (+5% to +35% MAE; part of that is a harder year, since B1 also got worse in Amprion and TenneT; I did not investigate further). B0 (yesterday) is worse than B1 wherever it is available; for 50Hertz it came out as NaN in the final run (missing lag_24h hours) and was not re-run. Full tables: `results/final_test_*.csv`.

## Prediction intervals
Nominal vs observed coverage, mean over the four zones:

| Band | Raw quantiles (test) | With CQR (validation, calibrated on the other half) | With CQR (test) |
|---|---|---|---|
| 80% | 58.0% | 80.0% | **72.5%** |
| 95% | 78.4% | 94.2% | **90.8%** |

So the intervals are **too narrow on new data**: calibration on one period does not transfer (only 50Hertz is near nominal on test: 78.9% / 94.4%). Coverage is worst around midday (80% band about 65-67% at 12-16 h on test) and over-covered at night. Plots: `results/figures/coverage.png`, example week `results/figures/fan_example.png`.

## Stress tests (all inside train+validation; `scripts/stress_tests.py`, details in EXPERIMENTS.md)
- **Rolling-origin backtest** (8 expanding-window folds: calendar years 2018-2023, 2024-01-01 to 2024-10-24, and the validation year): the model beats B1 in every window and zone.
- **Holidays etc.**: lower error than B1 on every subset, but higher than its own average on Christmas-New Year (1.3-1.7x), public holidays (1.2-1.5x) and bridge days (1.2-1.8x). Heat waves are easier than average, cold snaps about average.
- **Shift**: trained before 2020, evaluated 2020-22 without retraining: within 0-10% of the retrained model and far better than B1.
- **Weather error** (noise levels are my assumptions, not measured forecast errors): +2-9% MAE at level 1, +15-32% at level 4 for three zones; TransnetBW is much more sensitive (+25% at level 1, +60% at level 4).
- **Missing data** (no imputation): 30% missing weather hours cost about +12% (TransnetBW +31%). **Missing load history is the real weak spot**: 10% missing lags cost about +35-41%, 30% about +125-136%, and the model becomes worse than B1 in some zones.

## Limitations
- Weather inputs are observed values, so the headline numbers are optimistic for a real day-ahead setting (weather forecast error would add to them; see weather-noise results).
- Grid load is the SMARD "Grid load" series, not total electricity consumption; zones are TSO control areas, not states; the holiday-to-zone mapping is approximate.
- Prediction intervals do not hold their nominal coverage on the test year (above).
- Patterns shift over time (the test year was harder than validation); the model is retrained only once, on data before 2024-10-25.
- Holiday/bridge-day/heat statistics rest on few days; the stress-test noise levels are assumptions.
- The model has not been compared with the TSOs' own forecasts, and nothing here shows that it beats them.
- Licence terms of the data sources are not verified (see above). Not production-grade.

## How to run
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # on macOS LightGBM needs libomp: brew install libomp
python scripts/download_load.py            # slow: roughly 25-40 min per zone
python scripts/download_reference.py       # SMARD national series, used only for checks
python scripts/download_weather.py
python scripts/build_dataset.py            # writes data/processed/{trainval,sealed_test}.parquet
PYTHONPATH=src pytest                      # 20 tests
python scripts/data_card.py                # sanity numbers and plots (train+validation only)
python scripts/baselines.py
python scripts/run_models.py M1 M2 M3 M4
python scripts/run_quantiles.py && python scripts/run_quantiles_hourly.py
python scripts/stress_tests.py
python scripts/train_final.py              # train-only models, SHA-256 lock in results/model_lock.json
python scripts/final_eval.py --confirm-final    # sealed test; refuses to run twice (results/FINAL_EVAL_DONE)
```
