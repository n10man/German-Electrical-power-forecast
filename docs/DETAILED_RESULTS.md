# Detailed results

The long tables and the details behind the [README](../README.md). All numbers come from the files in `results/`. MAE is the typical size of our miss, in megawatt-hours per hour (MWh/h). "Validation" means the year we used for tuning; "test" means the sealed final year.

## Contents
1. Final test table in full (24-hour rolling model)
2. SMARD's official day-ahead forecast: how we compared
3. Interval coverage and the recalibration experiment
4. Future forecast: caveats, method and the per-horizon table
5. Other models we tried (ridge, small neural network)
6. Lag ablation (how much the 24-hour-old load matters)
7. Data checks and how we split the data
8. Map data notes (missing hours, zone assignment)

## 1. Final test table in full
**Final sealed test (2025-10-25..2026-10-24), MAE in MWh/h, run once (rolling 24-hour-ahead with observed weather; see the README):**

| Zone | B1 last week | SMARD official day-ahead forecast | Model | Model vs B1 | Model vs official | Model MAPE | Validation MAE (model) |
|---|---|---|---|---|---|---|---|
| 50Hertz | 932 | 952 | 556 | -40% | -42% | 4.8% | 531 |
| Amprion | 1184 | 846 | 646 | -45% | -24% | 3.5% | 524 |
| TenneT | 948 | 1011 | 478 | -50% | -53% | 3.1% | 355 |
| TransnetBW | 446 | 459 | 195 | -56% | -58% | 3.0% | 164 |

The model beat B1 in every zone, and also on public holidays, the hottest 5% and the coldest 5% of test days (model/B1 error ratio 0.20-0.29, 0.42-0.65 and 0.32-0.40). It was nevertheless worse on test than on validation (+5% to +35% MAE; part of that is a harder year, since B1 also got worse in Amprion and TenneT; we did not investigate further). B0 (yesterday) is worse than B1 wherever it is available; for 50Hertz it came out as NaN in the final run (missing lag_24h hours) and was not re-run. Full tables: `results/final_test_*.csv`.

## 2. SMARD's official day-ahead forecast: how we compared
SMARD publishes a "Forecasted consumption" series for each of the four control areas (filter 411, quarter-hourly, from 2015; also for Germany as a whole), submitted by the TSOs the day before. We downloaded it (`scripts/download_official_forecast.py`) and scored it on the same sealed test hours as our model (`scripts/compare_official_forecast.py`, `results/official_forecast_comparison.csv`; the comparison rule was committed before the series was downloaded, see `results/EXPERIMENTS.md`, entry O1). This is reporting only: our model, its lock and its logged numbers are unchanged, and no new model metric was computed.

**Our model has the lower MAE in all four zones (24% to 58% lower), but this comparison favours us and is not like-for-like.** The official forecast is a true day-ahead forecast issued the day before (SMARD says the TSOs submit it the day before, based on day-ahead trading results, and that it may be updated afterwards if it changes by more than 10%; the downloaded series is the latest published one). Our model is a rolling 24-hour-ahead forecast that uses `lag_24h` and `lag_48h` and observed instead of forecast weather. To size the lag part of that difference, the validation-only ablation (see the lag ablation below) shows +8.7% mean validation MAE without `lag_24h` and +18.1% without `lag_24h` and `lag_48h`; we did not compute any adjusted test number, and the advantage from using observed weather is not measured. The gap to the official forecast is larger than the lag effect, but the two are not comparable one-to-one.

Other things to know about the official numbers: the per-zone official forecasts are no better than copying last week in three zones (MAE 952 vs 932 for 50Hertz, 1011 vs 948 for TenneT, 459 vs 446 for TransnetBW) and clearly better only in Amprion (846 vs 1184). As a sanity check of the series (a post-hoc check, labelled as such in the log), the national official forecast has MAPE 3.8% on the test year, a plausible size for a TSO forecast. TransnetBW's official forecast runs about 6% above actual load on both validation and test (a systematic offset we did not investigate); removing it would lower its MAE from 459 to 341, still well above our 195. The official series is missing 24 of TenneT's 8,760 test hours (0.27%), which are left out of the official TenneT score only.

## 3. Interval coverage and the recalibration experiment
Nominal vs observed coverage, mean over the four zones:

| Band | Raw quantiles (test) | With CQR (validation, calibrated on the other half) | With CQR (test) |
|---|---|---|---|
| 80% | 58.0% | 80.0% | **72.5%** |
| 95% | 78.4% | 94.2% | **90.8%** |

So the intervals are **too narrow on new data**: calibration on one period does not transfer (only 50Hertz is near nominal on test: 78.9% / 94.4%). Coverage is worst around midday (80% band 64-67% at 12-16 h on test) and over-covered at night. Plots: `results/figures/coverage.png`, example week `results/figures/fan_example.png`.

### Fixing the ranges (validation year only; future days)
Hypothesis: a single offset calibrated once cannot follow changing conditions, so recalibrating on recent errors should keep coverage nearer to nominal. Rules were written before running anything (`results/EXPERIMENTS.md`, entry I1): a replay over the validation year with a 13-week burn-in and weekly-or-finer updates, where an error may only be used 24k hours after the hour it belongs to (horizon model k). One shared setting for all zones and horizons; selection = smallest gap to nominal coverage among methods whose interval score is not more than 10% worse than the fixed method's. The sealed test year was not used.

| Method | Mean coverage 80% / 95% | Worst cell 80% / 95% | Mean width (MWh/h) | Mean interval score | Score vs static | Admissible |
|---|---|---|---|---|---|---|
| static | 83.3% / 95.7% | 72.8% / 90.4% | 2,447 | 2,934 | 1.000 | yes |
| rolling_4w | 79.2% / 93.9% | 77.2% / 91.7% | 2,153 | 2,860 | 0.995 | yes |
| rolling_8w | 80.0% / 94.7% | 78.1% / 93.4% | 2,168 | 2,794 | 0.970 | yes |
| rolling_13w | 80.4% / 94.9% | 78.2% / 93.6% | 2,196 | 2,794 | 0.969 | yes |
| aci_g0.005 | 79.9% / 94.9% | 75.2% / 93.6% | 2,805 | 3,475 | 1.208 | no |
| aci_g0.01 | 79.7% / 94.8% | 75.2% / 93.4% | 3,268 | 4,055 | 1.413 | no |
| aci_g0.02 | 79.4% / 94.7% | 75.1% / 91.6% | 3,737 | 4,902 | 1.728 | no |

**Selected: `rolling_8w`** (recalibrate on the errors of the latest 8 weeks). Adaptive conformal inference (Gibbs and Candes 2021) had the smallest coverage gap but widened the ranges so much (score 21% to 73% worse) that the rule excluded it; the 24k-hour feedback delay is a plausible reason, which we did not investigate. Caveats: the "static" row here is calibrated on only the first 13 weeks of validation and over-covers afterwards (the opposite sign from what happened on the test year), so the rows show the methods are *steadier*, not that the problem is solved; the choice among 7 methods is made on the same validation data it is judged on; validation had no shift as large as the test year.
**Where it is used.** Only the future snapshot (`results/interval_calibration_rolling_8w.json`, hashed in `results/interval_lock.json`; the same forecast's new ranges are in `results/prospective/intervals_rolling_8w_*.json`). Because the sealed test year may not be used, it could only be calibrated on the 16 days after it (392 hourly errors per cell), a window shorter than 8 weeks. **Past-date ranges on the map are unchanged**, so past and future popups use different methods and are not comparable. The "ranges are too narrow" warning stays until the prospective check says otherwise.

## 4. Future forecast
**What it is.** The map can also show dates that have not happened yet, for all four grid zones, as a **one-off snapshot**: `scripts/make_future_forecast.py` was run once and wrote `site/data/future/*.json` and `site/data/future_meta.json`. The page says "Forecast generated on <time> UTC, covers <start> to <end>". There is no scheduler and no GitHub Action, the page does not update itself, and visitors' browsers make no calls to Open-Meteo. Snapshot in this repository: forecast origin (last hour of actual load in all four zones) 2026-11-10 07:00 UTC, generated 2026-11-11 05:36 UTC, covering 2026-11-11 06:00 to 2026-12-01 07:00 UTC.

**Caveats first.**
- **Real weather forecasts reach only 7 days into the models, not 16.** Open-Meteo archives past forecasts by lead time only for leads of 1 to 7 days (Previous Runs API; humidity, wind, radiation and cloud only from 2024-01-19, temperature from 2021-03). A model cannot be trained honestly on a forecast it never saw, so the models for days 8 and later use **no weather at all** (calendar and recent load only); a stand-in experiment (day-7 forecast used for a later horizon) was worse on validation and was not used. Even for days 1-7, the forecast weather was used in only 6 of 36 zone-horizon models (it helped by 2-6% there and did not help in the other cells), so these are mostly **calendar and recent-load models**. The weather forecast download still happens, but 30 of 36 models ignore it.
- **Days 17-21 are a "low-confidence outlook"** (calendar and load only, no weather). It passed the same pre-registered rule as the other horizons, so it is shown, and it is labelled everywhere.
- **Accuracy falls with distance, but slowly, and the error is large from day 1.** E.g. test-year error for TenneT: 531 MWh/h at one day, 781 at 21 days (last-week baselines 948 and 1,218). The models were trained on data up to 2024-10 and **not refitted** on newer data, so they are about two years old.
- **The ranges are too narrow.** On the sealed test year the 80% ranges contained about 71-74% and the 95% ranges about 90% of actual values at every horizon (zones: 50Hertz 79/93, Amprion 70/89, TenneT 66/86, TransnetBW 74/92). The page says so.
- **Evaluation of the weather part uses archived forecasts**, the same kind of input as at serving time, but the forecast model mix behind Open-Meteo's default "best match" may change over time and the live forecast may differ from the archived one.
- **Second use of the test year.** 2025-10-25..2026-10-24 was already used once for the 24-hour model (F1). It was used a second time, exactly once, for this different model family (entry F2 in `results/EXPERIMENTS.md`): nothing was chosen or tuned on it; the horizons, configurations, show/hide rule and conformal offsets were fixed on the validation year and locked (SHA-256, `results/model_lock_future.json`) before the run. `scripts/final_eval_future.py --confirm-final` is one-shot (exit 3 afterwards).
- Still true for the map as a whole: the forecast is for the grid zone, not the state; the split-state notes and all earlier caveats stand. Not production-grade.

**Method.** One LightGBM model per zone and per distance k in {1, 2, 3, 5, 7, 10, 14, 16} days (plus 21 for the outlook), "direct" rather than chained: model k predicts hour t using only load measured at or before t-24k hours (same hour k days earlier and one day further back, the same weekday and hour of the latest known week and the week before, and the mean load of the last known 24 h and 168 h), calendar and holiday features, and for k up to 7 optionally archived forecast weather of lead k. Day d after the origin is served by the smallest k >= d (4 uses model 5, 6 uses 7, 8-9 use 10, 11-13 use 14, 15 uses 16, 17-21 use 21), which uses slightly older information than necessary (conservative). Ranges: quantile models plus a conformal offset per zone, horizon and band calibrated on the validation year. Seasonal-naive baselines use the same cut-off: same hour k days earlier, and the same weekday and hour of the latest known week; the better one on validation is the reference. **Rule (written before training):** a horizon is shown for a zone only if its validation MAE is at least 5% below that baseline and it is not worse on public holidays and the hottest and coldest 5% of days. All 36 zone-horizon cells passed, so nothing is hidden; the rule did not filter anything out. (`results/EXPERIMENTS.md` entries H0, H1, F2.)

**Accuracy per horizon** (MAE in MWh/h: validation / sealed test (best simple baseline on test); coverage of the CQR ranges). Validation coverage is measured with swapped halves of the validation year, so its mean is about nominal by construction; the worst zone-half cell shows the spread. Test coverage is the honest number.

| model k (days it serves) | 50Hertz val / test MAE (best baseline, test) | Amprion val / test MAE (best baseline, test) | TenneT val / test MAE (best baseline, test) | TransnetBW val / test MAE (best baseline, test) | test 80% / 95% coverage (mean of zones) | validation 80% / 95% coverage, swapped halves (mean; worst zone-half) |
|---|---|---|---|---|---|---|
| 1 (1) | 592 / 664 (932) | 550 / 690 (1184) | 402 / 531 (948) | 196 / 229 (446) | 72.4% / 89.8% | 80% / 94% (71% / 88%) |
| 2 (2) | 646 / 654 (932) | 636 / 796 (1184) | 460 / 634 (948) | 222 / 254 (446) | 73.1% / 90.5% | 80% / 95% (72% / 90%) |
| 3 (3) | 649 / 727 (931) | 668 / 852 (1184) | 479 / 668 (948) | 239 / 267 (446) | 71.9% / 90.4% | 80% / 94% (70% / 87%) |
| 5 (4-5) | 661 / 688 (932) | 689 / 911 (1184) | 503 / 701 (948) | 261 / 285 (446) | 72.8% / 90.7% | 80% / 95% (70% / 88%) |
| 7 (6-7) | 667 / 692 (932) | 727 / 940 (1184) | 520 / 706 (948) | 264 / 301 (446) | 72.7% / 90.6% | 80% / 94% (67% / 87%) |
| 10 (8-10) | 681 / 683 (961) | 807 / 984 (1373) | 557 / 746 (1066) | 299 / 354 (522) | 73.7% / 90.3% | 80% / 94% (62% / 82%) |
| 14 (11-14) | 680 / 687 (961) | 839 / 1009 (1373) | 591 / 759 (1066) | 301 / 360 (522) | 72.6% / 90.0% | 80% / 94% (66% / 83%) |
| 16 (15-16) | 695 / 708 (1053) | 833 / 1079 (1593) | 580 / 756 (1218) | 299 / 366 (592) | 71.1% / 89.8% | 80% / 94% (66% / 83%) |
| 21 (17-21 (outlook)) | 702 / 710 (1053) | 851 / 1126 (1593) | 590 / 781 (1218) | 305 / 391 (592) | 70.7% / 89.6% | 80% / 94% (65% / 83%) |

Reading it: the models beat the best simple baseline in all 36 cells on the test year (by 21% to 49%), but their test errors were 0.3% to 39% higher than on validation; the baselines used here are weak at long range (they copy a week that is old), so beating them is a low bar. Day-ahead accuracy is far from perfect: this is a portfolio baseline.

**Tests.** `tests/test_horizon.py` (no load feature uses information after the origin for its horizon; lags are at least 24k hours; the one-shot gate), `tests/test_future_forecast.py` (expected zones/hours/columns of the snapshot, monotone quantiles, no actual line in future files, accuracy table present, past-date map files byte-identical by SHA-256, the later comparison script).

## 5. Other models we tried (validation year only)
Question: could a ridge regression or a small neural network replace LightGBM? Rules first (`results/EXPERIMENTS.md`, entries M5 and M5a): same features, horizons, per-zone configuration and split as the locked models, trained on the training period only, scored on the validation year (2024-10-25 to 2025-10-24) with the 1% tie band. Ridge: standardised features, calendar one-hot, alpha by time-ordered cross-validation. Neural network: scikit-learn `MLPRegressor`, layers (64, 32), early stopping on the last 10% of the training data in time order, 3 seeds. Mean absolute error in MWh/h:

| Zone | Days ahead | LightGBM | Ridge | Small neural net (mean, range of 3 seeds) |
|---|---|---|---|---|
| 50Hertz | 1 | 592 | 642 | 636 (585-669) |
| 50Hertz | 7 | 667 | 695 | 655 (654-656) |
| 50Hertz | 21 | 702 | 765 | 682 (680-685) |
| Amprion | 1 | 550 | 733 | 559 (555-563) |
| Amprion | 7 | 727 | 829 | 727 (720-738) |
| Amprion | 21 | 851 | 995 | 878 (866-889) |
| TenneT | 1 | 402 | 565 | 395 (390-402) |
| TenneT | 7 | 520 | 659 | 509 (504-514) |
| TenneT | 21 | 590 | 879 | 584 (578-598) |
| TransnetBW | 1 | 196 | 316 | 191 (191-191) |
| TransnetBW | 7 | 264 | 342 | 266 (264-267) |
| TransnetBW | 21 | 305 | 499 | 298 (285-306) |
| **Pooled (sum of 12 cells)** | | 6,365 | 7,919 | 6,380 |

Ridge was clearly worse in all 12 cells. The small neural network was **practically indistinguishable in a pooled sense** (0.2% higher pooled error) and beat LightGBM by more than 1% in 6 of 12 cells, lost in 3 and tied in 3, so LightGBM is not clearly better here; we kept it because the models are locked and the comparison is validation-only (LightGBM's per-zone configuration was itself picked on this validation year, which slightly favours it). The test year was not used. The map models are unchanged.

## 6. Lag ablation
Every load input is known at least 24 h earlier, but a forecast issued once per day could not use `lag_24h` for the later hours of the next day. A validation-only ablation (`scripts/run_lag_ablation.py`, `results/lag_ablation_val.csv`; locked models unchanged) shows the dependence: without `lag_24h` the mean validation MAE rises by 8.7% (50Hertz +3.2%, Amprion +10.9%, TenneT +10.6%, TransnetBW +15.8%); without `lag_24h` and `lag_48h` it rises by 18.1% (+7.1%, +21.3%, +22.6%, +33.3%). Both variants still pass the keep rule and are far better than the last-week baseline, but by the threshold we set beforehand (15%) the headline MAEs depend materially on the short lags and **must not be read as day-ahead numbers**.

## 7. Data checks and how we split the data
- **Load source check.** Series 410 (SMARD "Grid load", quarter-hourly per control area, values in MWh per 15 minutes; the hourly value is the sum of the four) was downloaded on 2026-11-08. It reproduces the three SMARD website reference values exactly (60,003 / 59,180 / 56,841 MWh at 2022-06-01 16:00-18:00 UTC; they were first noted in UTC+8 local time). The sum of the four zones matches SMARD's national total (median difference 0.000% on train+validation, 99% of hours within 2.4%).
- **Weather and holidays.** Weather: Open-Meteo historical archive (no key), hourly, three cities per zone averaged: temperature, humidity, wind speed, shortwave radiation, cloud cover. Holidays: Python `holidays` package per German state; the zone feature is the equal-weight share of the zone's states that have a holiday that Berlin-local day. The state-to-zone mapping in `src/gepf/data.py` is an approximation (TSO areas do not follow state borders).
- Data checks (all automated in `tests/test_data_sanity.py`): no duplicate hours, regular hourly UTC index, no gaps inside train+validation (the 72-75 missing hours per zone in the raw range are almost all the empty days before 2015-01-01, plus a few unpublished newest hours), 23/25-hour daylight-saving days, plausible magnitudes (2019: 56.8 GW mean, 497 TWh), weekday > Sunday, winter > summer.

- **Split by time only**, dataset ends 14 days before the last available hour: train < 2024-10-25, validation 2024-10-25..2025-10-24, **test 2025-10-25..2026-10-24** (8,760 h each for validation and test). The test period lives in a separate file (`data/processed/sealed_test.parquet`). It was **evaluated once**, by `scripts/final_eval.py --confirm-final`. The file was read again afterwards in two places, with no metric computed and no model, offset or result changed: by `scripts/export_site_data.py` (to write the map's hourly forecasts) and by a one-off snippet that counted missing inputs per zone (not saved as a script in the repo; its code is quoted in `results/EXPERIMENTS.md`, entry R1). So the accurate statement is: one evaluation, three reads of the file.
- **Features** (`src/gepf/data.py`, `src/gepf/models.py`): Berlin hour, weekday, month, day of year, weekend, bridge day (Monday/Friday next to a Tuesday/Thursday holiday), zone holiday share, five weather variables, and load lags 24/48/168/336 h. Leakage tests are in `tests/test_leakage.py`.
- **Model**: LightGBM 4.7.0, one regressor per zone (600 trees, learning rate 0.05, 31 leaves, seed 42). A pooled model with zone as a feature was 4% worse on validation. scikit-learn's HistGradientBoosting was not used because LightGBM imported.
- **Baselines**: B0 same hour yesterday, B1 same hour last week (B1 is the better one).
- **Intervals**: LightGBM quantile models (2.5/10/50/90/97.5%) trained on train only, plus conformalized quantile regression (CQR) with one offset per zone and band calibrated on the validation year. Calibration per hour of day (24 groups, or 6-hour blocks) was tried and rejected.
- Every experiment, rule (written before results), decision and commit: [`results/EXPERIMENTS.md`](../results/EXPERIMENTS.md).

## 8. Map data notes
- **Data**: `scripts/export_site_data.py` runs the *locked* models (SHA-256 verified, refuses unless the final evaluation was already run) to write `site/data/{zone}.json` for validation and test hours. It computes no metrics; the test period was not re-evaluated, retuned or recalibrated for the map, and the headline numbers above are unchanged. Forecast = the mean model; ranges = quantile models plus the validation-calibrated conformal offsets (the same ones evaluated on the test period). The forecast lies inside the 95% range in 99.9% of hours.
- **Which hours have missing inputs (test year 2025-10-25..2026-10-24, counted by that one-off snippet from the sealed file; the 6 excluded hours are also visible as `hours_left_out` in `site/data/meta.json`)**: Amprion, TenneT and TransnetBW: none. 50Hertz: 6 of 8,760 hours (2 with a missing actual load value, and the 2 hours exactly one week and the 2 exactly two weeks later whose lag_168h / lag_336h partner is missing). **Handling**: these 6 hours are excluded from the final evaluation (that is why 50Hertz has n = 8,754 there) and are left out of the map, which shows them as missing; four of the remaining 50Hertz hours have a missing lag_24h or lag_48h, which LightGBM handles natively (no imputation). No weather input is missing in any zone. Validation has no missing hours.
- **Zone assignment**: each state is assigned its *dominant* grid zone (`src/gepf/zones.py`, the same mapping used for the holiday feature). Sources, all qualitative: SMARD, [Control area](https://www.smard.de/page/en/wiki-article/5884/205642) (50Hertz north and east, Amprion west and south-west, TransnetBW a large part of Baden-Württemberg, TenneT from Denmark to the Alps); Deutscher Bundestag, Wissenschaftliche Dienste, [WD 5 - 3000 - 117/16 (2017)](https://www.bundestag.de/resource/blob/494452/29f6a6424b8d97b6aad95ff22cfa6577/WD-5-117-16-pdf.pdf), section 2, which lists the states per operator and quotes the ewi study, which names more than one operator for Niedersachsen, Nordrhein-Westfalen, Hessen, Baden-Württemberg and Bayern. Those five states are flagged "split" (they carry a warning in the popup). **No source gives area or load shares**, so "dominant" is our judgement from the wording (e.g. TenneT for Hessen and Bayern, Amprion for Nordrhein-Westfalen) and could be wrong for Hessen in particular; we did not find the TSOs' own maps in a machine-readable form, and the sources are from 2012-2017.
