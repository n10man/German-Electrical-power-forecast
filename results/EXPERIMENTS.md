# Experiments log

Per experiment: hypothesis, the ONE change, command, validation metrics, keep/revert rule (written BEFORE results), decision, commit hash.
Splits are by time only. Test period is sealed until Phase 6. Max 10 experiments per feature group.

## B0/B1 — Baselines (reference points, validation only)
- Hypothesis: simple seasonal-naive forecasts set the bar any model must beat.
- Change: none (B0 = same hour yesterday = lag_24h; B1 = same hour last week = lag_168h). Both only use load known >= 24h ahead.
- Command: `python scripts/baselines.py`
- Keep/revert rule (written before results): baselines are kept as reference. In Phase 3 a model is kept for a zone only if its validation MAE is lower than the BEST baseline's MAE for that zone by at least 5%; otherwise revert.
- Metrics: see results/baselines_val.csv and the section below (filled after running).
- Decision / commit: recorded below.

**B0/B1 results (validation 2024-11-08..2025-11-07, MWh/h):** best baseline per zone is B1 (last week):
50Hertz MAE 941 (MAPE 8.3%), Amprion 989 (5.2%), TenneT 798 (5.1%), TransnetBW 447 (7.1%). B0 (yesterday) is worse everywhere (MAE 634-1427). Full table: results/baselines_val.csv.
Decision: both kept as references. Bar for Phase 3 per the rule above (MAE <= 0.95 x B1): 50Hertz 894, Amprion 940, TenneT 758, TransnetBW 425.

## D1 — Dataset end moved back 14 days (owner request)
- Hypothesis: the newest load/weather values may still be revised; ending the dataset 14 days before the last available hour (last hour with all four zones valid: 2026-11-08 06:00 UTC) gives settled data.
- ONE change: `end = (last_valid - 14 days).floor(day)` in scripts/build_dataset.py. Windows keep 8,760 h each: train < 2024-10-25, val 2024-10-25..2025-10-24, sealed test 2025-10-25..2026-10-24 (not read).
- Command: `python scripts/build_dataset.py && pytest && python scripts/baselines.py`
- Result: 14 tests pass. Baselines re-scored on the new validation window (MAE, MWh/h): B1 last week 50Hertz 922, Amprion 1003, TenneT 791, TransnetBW 450 (previous numbers above are superseded). B0 worse everywhere.
- Decision: keep. Commit: see git log ("D1").

## RULE v2 (supersedes the earlier B0/B1 keep rule; written BEFORE any model was run)
A model configuration is KEPT for a zone only if ALL hold on VALIDATION:
1. Overall MAE is at least 5% below B1 (last week): bars 876 (50Hertz), 953 (Amprion), 751 (TenneT), 427 (TransnetBW) MWh/h (0.95 x B1 above).
2. MAE on public-holiday hours is not worse than B1's (holiday = zone `holiday_share` >= 0.5 on the Berlin local date).
3. MAE on the hottest 5% of days and the coldest 5% of days is not worse than B1's on those same days (days = Berlin local dates, ranked per zone by daily mean temperature of the zone-average weather, validation period only).
Otherwise REVERT (the zone falls back to B1). Pooled vs per-zone is decided by mean-over-zones validation MAE among configurations that pass the rule; ties (within 1%) go to the simpler per-zone model.
Planned experiments (feature group "model/features", max 10): M1 LightGBM per zone, calendar+holiday+lags (no weather); M2 = M1 + weather; M3 = pooled model with zone as categorical, all features; M4 = best of M2/M3 with one LightGBM hyperparameter change (lower learning rate + more trees, early stopping on validation is NOT used; fixed rounds). Fixed seed 42. Tuning on validation only.
Lags used: 24, 48, 168, 336 h (all >= 24 h). Weather features are observed values at the target hour (Phase 5 tests noise).

## M1-M4 — Phase 3 LightGBM (validation 2024-10-25..2025-10-24; LightGBM 4.7.0 imports, so it is used)
Command: `python scripts/run_models.py M1 M2 M3` and `... M4`; per-zone tables in results/models_val_*.csv. Seed 42. MAE in MWh/h; B1 = last week. Rule v2 applied (overall <=0.95 x B1, and not worse than B1 on holiday / hottest-5% / coldest-5% days; n per zone: 240-288 holiday hours, 456 hot hours, 456 cold hours).
Eval-helper bug (not a rule change): the first run had empty hot/cold masks (tz-aware vs naive day labels), fixed in src/gepf/evalutil.py before any decision; overall numbers were identical.
- M1 per-zone, calendar+holiday+lags, no weather. Mean MAE 432.5 (B1 791.6). 4/4 zones pass. Hypothesis: calendar+lags alone already beat B1. Result: yes. Keep as reference.
- M2 = M1 + 5 weather features (zone-average of 3 cities). ONE change: add weather. Mean MAE 393.5 (-9% vs M1); 4/4 pass. Zones: 50Hertz 531, Amprion 524, TenneT 355, TransnetBW 164. KEEP.
- M3 = pooled model, all features, zone as categorical. ONE change: pooled instead of per-zone. Mean MAE 409.7 (+4.1% vs M2); 4/4 pass. Not within 1% of M2 -> per-zone wins. REVERT.
- M4 = M2 with learning_rate 0.02, 1500 trees (ONE change). Mean MAE 391.9 (-0.4% vs M2), inside the 1% tie band -> simpler M2 stays. REVERT. (Amprion holiday MAE got worse, 606 vs 572.)
- Final Phase 3 model: M2, per-zone LightGBM. Caveats: the weather is observed, not forecast (Phase 5 adds noise); holiday/hot/cold subsets are small (about 10-12 holidays, 19 hot and 19 cold days), so "not worse than B1" there is a weak test; B1 is a weak holiday baseline (it copies a normal day), so passing is easy.
- Commit: see git log ("Phase 3").

## Q1/Q2 — Phase 4 uncertainty (rules written BEFORE running)
- Q1: per-zone LightGBM quantile models (alpha 0.025, 0.1, 0.5, 0.9, 0.975), M2 features and hyperparameters, trained on train only; quantiles sorted to avoid crossing. Evaluated on all of validation (the models never saw it, so this coverage is honest).
- Q2 (ONE change on Q1): conformalized quantile regression (CQR) per zone and per band (80% = q10/q90, 95% = q2.5/q97.5). Calibration must not be scored on itself, so validation is split by TIME into halves A = first 6 months, B = last 6 months: calibrate on A, report coverage on B; calibrate on B, report coverage on A. (Halves cover different seasons, which is itself a test of shift.) The offsets used later on the test period are calibrated on all of validation.
- Targets: nominal 80% and 95%. Coverage error = |empirical - nominal|.
- Keep/revert: Q2 is kept over Q1 if its mean coverage error (over zones, both bands, both A/B cross-evaluations) is lower than Q1's on the same hours; else revert to raw Q1. Q1 as a whole is "acceptable" if the 80% band coverage is within 80 +/- 5 pp and the 95% band within 95 +/- 3 pp, on average over zones; if not, that is reported as a failure, not tuned away.
- Also reported: median-model MAE vs M2 (L2 mean model), pinball loss, average band width, coverage per zone, per hour-of-day and by month. Plot: results/figures/coverage.png.
- Caveat to state: CQR assumes exchangeable errors; load errors are autocorrelated and shift with season, so coverage is approximate.

### Q1/Q2 results (command: `python scripts/run_quantiles.py`; files: results/quantiles_coverage.csv, coverage_by_hour.csv, coverage_by_month.csv, cqr_offsets_val.json, figures/coverage.png, figures/fan_example.png)
- Q1 raw quantile bands (honest, never fit on validation): nominal 80% band covers 65.0%, nominal 95% band 84.0%; mean |coverage error| 13.0 pp. FAILS the pre-set acceptance (80 +/- 5, 95 +/- 3): bands far too narrow (quantile models trained on train years are over-confident out of sample).
- Q2 CQR (calibrate on one validation half, score on the other): 80% -> 80.0%, 95% -> 94.2% on average; mean |error| 4.4 pp (vs 13.0) -> KEEP Q2 over Q1 per the rule. Bands are wider (80%: 1318 vs 945 MWh; 95%: 2168 vs 1547 MWh average width).
- But per zone and half the coverage is uneven: 50Hertz 80% band 75.4% (A) vs 85.7% (B); Amprion 67.6% vs 90.8%; i.e. calibrating on one season-half does not transfer perfectly (TenneT is the most stable: 80.3/79.7%). Hour-of-day: coverage is lowest around midday (80% band about 72% in-sample after conformal; raw about 56-60%) and over-covered at night (the constant offset cannot follow the midday error growth, likely solar/PV and behind-the-meter effects). Month: raw 95% coverage ranges 80-90%.
- Median model (q50) MAE: 50Hertz 543, Amprion 523, TenneT 359, TransnetBW 166, close to M2's mean-model MAE (531/524/355/164).
- Decision: Phase 4 method = Q1 quantile models + Q2 CQR (offsets in results/cqr_offsets_val.json, calibrated on all validation, to be applied on the sealed test in Phase 6). Not tuned further (no hour-adaptive calibration tried; that would be a new experiment).
- Commit: see git log ("Phase 4").

## Q3/Q4 — Phase 4b: conformal calibration by hour of day (rules written BEFORE running; max 2 experiments)
- Hypothesis: Q2 (one global CQR offset per zone and band) leaves midday under-covered and night over-covered; an offset per hour of day fixes that.
- Q3 (ONE change on Q2): CQR offset computed separately for each of the 24 Berlin local hours of day, per zone and band. Q4 (only if Q3 is rejected; ONE change on Q3): offsets per 6-hour block (00-05, 06-11, 12-17, 18-23) instead of per hour, to reduce noise. Same quantile models as Q1/Q2 (trained on train only).
- Protocol: same swapped halves as Q2: calibrate on half A, score on half B, and the reverse.
- ACCEPT only if BOTH: (i) every cell (zone x band {80,95} x swap {A->B, B->A} x hour-of-day group) has coverage within 5 percentage points of nominal (80% or 95%); (ii) average band width (mean over zones and swaps, per band) grows by no more than 15% relative to Q2's average width (80%: 1318 MWh, 95%: 2168 MWh, from the Q2 run above).
- Otherwise REJECT and keep Q2 (global offsets). Logged either way. If both fail, both are reported as rejected.
- Note written in advance: criterion (i) is strict. With ~180 hours per hour-group per half, the sampling error of a coverage estimate is about 3 pp (80% band) and 1.6 pp (95% band), so even a perfectly calibrated method may fail a few of the 384 cells by chance. I will report the number of failing cells and the worst cell, but the accept/reject decision follows the rule as written.

### Q3/Q4 results (command: `python scripts/run_quantiles_hourly.py`; cells in results/quantiles_hourly_cells.csv). Cells = zone x band x swap x hour = 192 per band.
| method | band | avg width (MWh) | vs Q2 | cells outside +/-5 pp | worst cell | mean abs err |
|---|---|---|---|---|---|---|
| Q2 global (reference, reproduces earlier widths) | 80 | 1318 | 0% | 122 / 192 | 27.0 pp | 8.0 pp |
| Q2 global | 95 | 2168 | 0% | 40 / 192 | 20.7 pp | 4.1 pp |
| Q3 per hour | 80 | 1360 | +3.1% | 141 / 192 | 23.4 pp | 8.4 pp |
| Q3 per hour | 95 | 2233 | +3.0% | 39 / 192 | 15.3 pp | 3.8 pp |
| Q4 per 6 h block | 80 | 1328 | +0.7% | 133 / 192 | 23.4 pp | 7.9 pp |
| Q4 per 6 h block | 95 | 2164 | -0.2% | 42 / 192 | 16.4 pp | 3.9 pp |
- Criterion (ii) (width <= +15%) is met by both; criterion (i) (every cell within 5 pp) is FAILED by both by a wide margin. Decision: Q3 REJECT, Q4 REJECT; keep Q2 (global offset per zone and band). Max 2 experiments used.
- Interpretation: hour-specific offsets barely improve on global offsets (95% band mean abs error 3.8 vs 4.1 pp; 80% band no better). The dominant error is the difference between the two validation halves (calibrating on one season-half does not transfer to the other), not hour of day; per-hour sampling noise (about 3 pp at 80%) also contributes. Even Q2 fails 122 of 192 80%-band cells under this strict test.
- Commit: see git log ("Phase 4b").

## S0-S4 — Phase 5 stress tests (definitions and failure criteria written BEFORE running). Test period stays sealed: everything uses trainval.parquet only.
- S0 rolling-origin backtest (expanding window): the Phase 3 model (M2: per-zone LightGBM, same features/hyperparameters, seed 42) is retrained for every evaluation window using only data strictly before the window start. Windows: calendar years 2018, 2019, 2020, 2021, 2022, 2023, then 2024-01-01..2024-10-24 (partial), then the validation year 2024-10-25..2025-10-24 (trained on train only, i.e. M2 itself). Purpose: many more holidays, bridge days, hot and cold days than validation alone has. Baseline B1 = same hour last week on the same hours.
- S1 (a) subset errors, pooled over all S0 windows, per zone: public holidays (zone holiday_share >= 0.5); bridge days (bridge_day == 1); Christmas-New Year (Dec 24-Jan 1); heat waves (>= 3 consecutive Berlin days with zone-mean temperature >= the zone's 90th percentile of daily means over the backtest span); cold snaps (>= 3 consecutive days <= 10th percentile); hottest 5% / coldest 5% days (as in rule v2). FAIL = model MAE > B1 MAE on that subset (reported per zone and per window where n allows).
- S2 (b) distribution shift: train on data before 2020-01-01 only (no retraining), evaluate 2020, 2021, 2022 separately; compare with B1 and with the S0 rolling-retrained model for the same year. FAIL = static-model MAE > B1 MAE, or static MAE > 1.25 x the rolling model's MAE for the same year.
- S3 (c) weather-forecast-error simulation on the validation year with the M2 models trained on train: Gaussian noise added to all five weather inputs at the target hours. Level 1 sigma = temperature 1.5 C, humidity 8 pp, wind 1.0 m/s, shortwave radiation 80 W/m2, cloud cover 15 pp; levels x1, x2, x4; two noise types: iid per hour, and AR(1) with phi = 0.95 (persistent errors, more realistic) with the same marginal sigma. Humidity and cloud clipped to 0-100, wind and radiation >= 0. Seed 42. FAIL = MAE more than 25% above the clean validation MAE of the same zone, or worse than B1.
- S4 (d) missing data on the validation year, no imputation (LightGBM native NaN handling): (i) weather inputs missing: 10% / 30% of hours at random, and 48-hour blocks totalling about 10% / 30%; (ii) load history missing: the same patterns applied to the load series, so lag_kh is NaN when the hour t-k is missing. Seed 42. Same FAIL criterion as S3.
- Decision logic: stress tests do not change the model (no tuning); they are reported as findings and failures go into the README limitations.

### S0-S4 results (command: `python scripts/stress_tests.py`; files results/stress_s0_rolling.csv, stress_s1_subsets.csv, stress_s2_shift.csv, stress_s3_s4.csv). No tuning, nothing reverted; these are findings. Test period not read.
- S0 rolling origin: the model beats B1 in every window and zone (MAE 2018-2024: 50Hertz 378-531 vs B1 691-922; Amprion 468-607 vs 905-1123; TenneT 307-373 vs 682-817; TransnetBW 133-165 vs 369-450). The "val" window reproduces M2 exactly (531/524/355/164), a consistency check.
- S1 (a) pooled over 8 windows (68,496 hours per zone): model MAE < B1 MAE on EVERY subset and zone (no FAIL vs B1; MAE ratio model/B1 0.13-0.65). But relative to its own overall MAE the model is worst on: Christmas-New Year (1.34-1.66x), public holidays (1.24-1.54x), bridge days (1.16-1.75x; TransnetBW and TenneT worst). Cold snaps/coldest 5% days are about average (1.01-1.07x). Heat waves and the hottest 5% of days are EASIER than average (0.72-0.91x). B1 is a weak comparison on holidays (it copies an ordinary week), so "beats B1" is a low bar there. Holiday n per zone: 1848-2231 hours (about 77-93 days) pooled.
- S2 (b) train <2020, evaluate 2020-22 without retraining: static MAE is within 0-10% of the rolling-retrained model (2021: 1.00-1.05x; 2022: 1.04-1.10x, worst Amprion 556 vs 507) and far below B1 in every case; no FAIL. (2020 static = rolling by construction, both trained before 2020.) So the COVID years and the 2022 energy crisis cost only a few percent here, mainly because the lag features (24-336 h) adapt to the level; the cost is in the trend (e.g., 2022 demand reduction).
- S3 (c) weather noise (sigma level x1 = 1.5 C, 8 pp, 1 m/s, 80 W/m2, 15 pp; my choice of plausible day-ahead errors, not measured): MAE grows 3-10% at x1, 5-18% at x2, 15-32% at x4 for 50Hertz/Amprion/TenneT; TransnetBW is far more sensitive (+25% at x1, +60% at x4) and FAILS the 25% criterion at every level (50Hertz, Amprion pass x1-x4; TenneT fails only at x4: +30-32%). iid and AR(1) noise give almost the same MAE. No scenario makes the model worse than B1.
- S4 (d) missing data, no imputation: missing WEATHER is tolerable (10%: +3-4%; 30%: +12% on average, TransnetBW +31%, i.e. FAIL for that zone). Missing LOAD HISTORY is the model's real weak spot: 10% of hours missing -> MAE +35-41% on average; 30% -> +125-136%, and MAE ends up WORSE than B1 in 3 zones with random gaps (50Hertz 924 vs 911, Amprion 1339 vs 1004, TenneT 964 vs 792) and in 2 zones with 48-hour blocks (Amprion 1214 vs 1010, TenneT 1031 vs 819). The model was not trained with missing lags, and LightGBM's NaN routing is not a substitute for imputing from other lags. Limitation: B1 itself is undefined when lag_168h is missing; its MAE here is computed on the hours where it exists.
- Where the model fails (summary): (1) holidays, bridge days and Christmas-New Year have clearly higher error (the data has few such days); (2) load-history gaps degrade it heavily; (3) the smallest zone, TransnetBW, is the most sensitive to weather error and missing weather; (4) constant-offset conformal bands do not hold across seasons (Phase 4).
- Caveats: noise levels are assumptions; holidays use an approximate state-to-zone share; S0 windows reuse the same hyperparameters chosen on the validation year (mild optimism for the "val" window only); backtest windows are inside train+validation, so these are not test results.
- Commit: see git log ("Phase 5").

## F1 — Final evaluation on the sealed test period (rules and lock written BEFORE running)
- Locked artefacts (models trained on TRAIN only, train_end 2024-10-24 23:00:00+00:00; CQR offsets calibrated on validation, val_end 2025-10-24 23:00:00+00:00; seed 42; produced by `python scripts/train_final.py`). Code + lock commit: **b1b1906c8b4df6ffd370e4c8caaf2305920f3198**. SHA-256 (also in results/model_lock.json, verified by scripts/final_eval.py before it reads any test data):

| file | SHA-256 |
|---|---|
| 50Hertz_mean.txt | 2a57221663eff89ee5a117300e803212faa643e7ce3d12f01d91d2e4041bf34b |
| 50Hertz_q0.025.txt | 4928afebd66a1f507ffbb4e135668998dd3d0b2527970f1e7a4d54ea7bebc395 |
| 50Hertz_q0.1.txt | cc618402bcda256aa1043a74d91aae2d73cfac5bb158c42ca99ed660f0455742 |
| 50Hertz_q0.5.txt | ef887185c3ccde2d8abbf910a48db5b79b682e0ef09331ebc05940db9c207852 |
| 50Hertz_q0.9.txt | dcc1736485ec3afe6cb3a04bd7c44733e47b15995cfa8b4137455f8dc54a117f |
| 50Hertz_q0.975.txt | 75413ced6a54d91d774c33cdd32e3c7aec21127f1c3d48d812e3db4d41f08f25 |
| Amprion_mean.txt | da65f3c095c275bd28faf040bea4c172d6587773ff65394dd10a39312521583d |
| Amprion_q0.025.txt | b7c7a45a6a002cf956d92f55d2014b5bc1b05c95ed4fed519798a501bfd1d79c |
| Amprion_q0.1.txt | ee5e41939864830c933c6b39145100b51d8b9d0a827cce6adee6b0600b621666 |
| Amprion_q0.5.txt | 7eec1869fe313545a51de3874c254606189af68f77b63a5d543e42a2948c8749 |
| Amprion_q0.9.txt | bece0118dee4e0499c569bc3e17e55c93cef615ed414cfd463778771fe4268dd |
| Amprion_q0.975.txt | 1d12772c6d6d2f22f231c9cde547def89e13a734e388a306cfb9850618e42b5c |
| TenneT_mean.txt | 43564041eb11ffe4d8d4c131e07a51bd883c62ba62b9dc6ab9ed17e749d60840 |
| TenneT_q0.025.txt | 947edfa229b08e389b9dfc514b8c365e7c4645691f5085a805b52bf172968102 |
| TenneT_q0.1.txt | df77644ae90d2e14b0a0dd543ee115f2cee9c349b74ccf0c58fbd9d3ca2d61c1 |
| TenneT_q0.5.txt | d1d102ef82843081586b1ed3fcd6a1cb21a9d3c847f7113367246ba0df1cdf48 |
| TenneT_q0.9.txt | f3993882fab9a9f2747c011c3602f528c86c0ce8c273c0c01fe369a5a50d1e8a |
| TenneT_q0.975.txt | 06a2dbec78acaad41443e999226165f14ebcc5b869d14a0bcac8e89c22df0a54 |
| TransnetBW_mean.txt | 8c64aee0fdf008fab56e3616fb6c44dec351fb7740b1dfee3a7f577eda4b5c47 |
| TransnetBW_q0.025.txt | b014e6a9a5d925851f14464e201ed8a5d9203b02e70a61bcdacd3bd3ab50962d |
| TransnetBW_q0.1.txt | 711a8180a60efef63968ae2efa955a608944faa8e84dd381d4a712bc0a9ad4ea |
| TransnetBW_q0.5.txt | 6511d3974943ebc485b46d89779c6ac05635ebd0e0c817276308b33233a810d5 |
| TransnetBW_q0.9.txt | cf207ef7930d1bf9b8d25bb9390ea464d0f82d713e4e1add15d894c7f9beeb16 |
| TransnetBW_q0.975.txt | e6e5ff2897502289e41f6f75f5aefbe41aebe6bc85356a918553dc36cbde740e |
| cqr_offsets.json | 89ec168093505dc3b9b891e583217696a261d0d6305f044629c7f046a4d72991 |
- Gate dry-run (done before this entry): without `--confirm-final` -> exit 2, no data read. With `--confirm-final --dummy --out-dir <scratch>`: runs the full pipeline on synthetic data, never reads data/processed/sealed_test.parquet, never writes results/FINAL_EVAL_DONE. 20 tests pass, including tests/test_final_gate.py (refusal without flag, refusal if FINAL_EVAL_DONE exists, refusal on SHA-256 mismatch, dummy run touches neither the sealed file nor results/).
- Command (run ONCE): `python scripts/final_eval.py --confirm-final`. It writes results/FINAL_EVAL_DONE, results/final_test_metrics.csv, final_test_subsets.csv, final_test_coverage.csv, final_test_coverage_by_hour.csv, final_test_meta.json.
- Hypothesis: the test-period results resemble validation: per-zone MAE at least 5% below B1 (last week), and CQR coverage near nominal but imperfect.
- Pass/fail definitions (the same as validated): rule v2 applied to the test period (overall MAE <= 0.95 x B1; not worse than B1 on public holidays, hottest 5% and coldest 5% of test days, ranked inside the test period); coverage targets 80 +/- 5 pp and 95 +/- 3 pp, averaged over zones.
- Decision rule: NO retuning, refitting or re-running after seeing the numbers, whatever they are. Failures are reported in the README as they are. If the run crashes before writing FINAL_EVAL_DONE, only the code bug may be fixed and the run repeated; this will be stated.

### F1 RESULTS — sealed test 2025-10-25 00:00 .. 2026-10-24 23:00 UTC, run ONCE on 2026-11-08 (git HEAD 6f21437088c6b896b2c2ceb8cd3e1689bd1b4c1a; files results/final_test_*.csv, FINAL_EVAL_DONE). No retuning, nothing re-run.
MAE in MWh/h, M2 = per-zone LightGBM mean model, B1 = same hour last week:
| zone | B1 | M2 | gain vs B1 | validation M2 | q50 median |
|---|---|---|---|---|---|
| 50Hertz | 931.7 | 555.8 | -40.3% | 531 | 561.5 |
| Amprion | 1184.4 | 645.7 | -45.5% | 524 | 655.4 |
| TenneT | 948.2 | 478.5 | -49.5% | 355 | 483.1 |
| TransnetBW | 445.9 | 194.8 | -56.3% | 164 | 196.7 |
(RMSE/MAPE for all models in results/final_test_metrics.csv; M2 MAPE 4.8 / 3.5 / 3.1 / 3.0 %. B0 yesterday: Amprion 1455, TenneT 1239, TransnetBW 632; 50Hertz B0 is NaN because some test hours have a missing lag_24h and the run's NaN handling for that reference was not masked; not re-run by rule; B0 is worse than B1 in every zone where it is available.)
- Rule v2 on the test period: PASS in all four zones. Overall MAE is 40-56% below B1 (needs >= 5%); on public holidays model/B1 MAE ratio is 0.20-0.29, on hottest-5% days 0.42-0.65, on coldest-5% days 0.32-0.40. Holidays n = 240-288 hours per zone.
- But the model is worse on test than on validation: MAE +5% (50Hertz), +23% (Amprion), +35% (TenneT), +19% (TransnetBW). B1 also got worse on test in Amprion (1184 vs 1003) and TenneT (948 vs 791), so part of the test year is simply harder; the cause was not investigated (no further analysis on test, to keep it a single look).
- Coverage (bands = quantile models + CQR offsets calibrated on validation): 80% band: 78.9 / 71.5 / 66.9 / 72.5 % (mean 72.5); 95% band: 94.4 / 90.7 / 87.1 / 91.1 % (mean 90.8). Targets (80 +/- 5, 95 +/- 3 pp averaged over zones): BOTH FAILED. Raw quantile bands (no conformal): 58.0 % and 78.4 %, much worse. Only 50Hertz is close to nominal. Coverage by hour of day (mean over zones, CQR): worst around midday (80% band: 0.65-0.67 at 12-16 h vs 0.75-0.78 at night; 95% band: 0.85-0.87 vs 0.93-0.94), the same pattern as in validation. Average width of the CQR bands: 80% 1319, 95% 2189 MWh.
- Conclusion: point forecasts generalise (well ahead of last-week and of holidays/heat/cold subsets); the prediction intervals do NOT hold their nominal coverage on new data, consistent with the Phase 4/4b/5 findings (calibration on validation does not transfer). Reported as is.

## P7 — Phase 7 map data (rules, written before building)
- Rule (owner): the test period is NOT re-evaluated, retuned or recalibrated. Headline metrics stay exactly as logged under F1. `scripts/export_site_data.py` only runs the LOCKED models (SHA-256 verified against results/model_lock.json; refuses unless results/FINAL_EVAL_DONE exists) to write hourly forecasts to site/data/*.json; it computes no error metrics. Coverage numbers shown in the map are copied from results/final_test_coverage.csv, not recomputed.
- Same row filter as the final evaluation: hours whose actual load, lag_168h or lag_336h is missing are left out (shown as "no data" in the map). Forecast = mean model (M2); bands = quantile models +/- the CQR offsets calibrated on validation.
- Test-period missing inputs (counted from the sealed file, no metrics): 50Hertz has 2 hours with missing actual load, and 4 more hours whose lag_168h or lag_336h partner is missing, so 6 hours were left out; 4 further evaluated rows have a missing lag_24h/lag_48h, which LightGBM handles natively (no imputation). Amprion, TenneT and TransnetBW: 0. No weather input is missing in any zone.

### P7 results
- Built: site/ (index.html, app.js, style.css), site/data/{50Hertz,Amprion,TenneT,TransnetBW}.json (17,514 / 17,520 / 17,520 / 17,520 hours), meta.json, states.geojson; scripts/export_site_data.py, download_states.py, build_site_geo.py; src/gepf/zones.py; tests/test_site_data.py. 29 tests pass. Tested in a browser: DST days (25 and 23 hours), the mixed validation/test day 2025-10-25, 50Hertz missing hours, a phone-width view; screenshots in docs/screenshots/.
- No new metrics were computed on the test period; coverage figures in the popup are copied from results/final_test_coverage.csv (72.5% / 90.8%).
- Zone assignment (dominant zone per state) is a judgement from qualitative sources; split states: NI, NW, HE, BW, BY.

## H1 — Commit hash mapping after the history rewrite of 2026-11-09 (appended; earlier entries above are NOT edited)
The history was rewritten on 2026-11-09: only the author/committer e-mail of every commit changed (to the GitHub noreply address), so every commit hash changed. Entries above that cite a commit hash (for example F1: b1b1906 and 6f21437) and the files results/FINAL_EVAL_DONE and results/final_test_meta.json (6f21437) and site/data/meta.json (85732f6) therefore name OLD hashes. They were left untouched on purpose (the model lock and the run record must not change). data/DATA_SOURCES.md cites no commit hash, so it needs no mapping.
Method: the old tip 09ed0f77a554ee4e46564c8258c2146c820fea92 (still present locally) was listed with `git rev-list --reverse <old tip>` and paired, in order, with the first 15 commits of `git rev-list --reverse HEAD`. For all 15 pairs the tree hash (`git rev-parse <commit>^{tree}`) is identical and the commit subject is identical: no mismatch, so no file content changed in the rewrite. Commits made after the rewrite (the audit fixes) are not part of the mapping.

| # | old commit | new commit | tree (first 12) | subject |
|---|---|---|---|---|
| 1 | 188aee8850a27c9b4e539cd6f356636db7679d68 | f789d4da0c5e3c0cee5bf99ad55f51cef5697b61 | f9abde2d8001 | Phase 0: project skeleton, gitignore, requirements, README s |
| 2 | 170d4539f55f50444e4aa327d055f4fcdc4e89ba | 289bb2d4024081abe7682a4990bb627f8f2dfb97 | 8240ae470666 | Phase 1: data download, cleaning, features, time split, sani |
| 3 | a7c6259820b9556efbb143985ffac454c193927c | 3b2ef626c150fb92d1ce877c6579c242943f7c66 | 1765129b2616 | Phase 2: seasonal-naive baselines on validation, log results |
| 4 | a0693898a5994f1b1952448a752b0f19d69b65c3 | 16e970f6bd71017ede750431785970df10abb516 | 9e7d53778cd0 | D1: end dataset 14 days before last hour, rerun tests/baseli |
| 5 | 567fd0c488423e11589fc5e909d077a99d75146b | c42dfd95df4e85d74a10217594f8a34b74d19577 | 0455f9d86723 | Phase 3: LightGBM per-zone models (M1-M4), rule v2 evaluatio |
| 6 | b8f7d83918e2ce473d0f2f541c360967d878723c | bec36c8919a450b26f91e5b586a13d39610a8fbf | f04a64fba431 | Phase 4: quantile LightGBM + CQR conformal calibration, cove |
| 7 | 5d78284b8f1cbb2d1094a9d4d3705a75e6698f97 | 9e2de3688a722b4e3036861ddf5a88964bf4a81b | 1a7fcdde27bd | Phase 4b: hour-of-day conformal calibration tried and reject |
| 8 | be1242baa6c8d4cad2e6818652d37442500c9b9a | a42fc3f961ee394602a660ff1b833ac3b1ebcf7a | 77d3b67a52cf | Phase 5: rolling-origin backtests and stress tests (holidays |
| 9 | 54942142a87de34e521d3e75fd5ba1c9496945fd | 4bc89336b591296893de3d1fb2d4caa8b97b0daa | ab1a122e2c0c | Phase 5: correct a count in the stress-test log |
| 10 | b1b1906c8b4df6ffd370e4c8caaf2305920f3198 | 2a5f7158a2f079e9983ac584148f6cac1630bf2c | 7040cf5a2853 | Phase 6 prep: train_final (train-only models, SHA-256 lock), |
| 11 | 6f21437088c6b896b2c2ceb8cd3e1689bd1b4c1a | 997c488cf5334f1da0cc348fdd20056ddfd45b5c | ff4e42089a5f | F1: lock model SHA-256 and commit hash, pre-register final e |
| 12 | 2b1b9c6ee2c57dc7c7748ac317254a31cfa40edd | 58dc54a6a3bec84b78be250d4edc71b58014eec0 | 0da6599f486b | F1: final evaluation on sealed test period (run once), resul |
| 13 | 055c1e7a2694a5792c7aec1ea311634cca1b5d10 | 4b4718045aa3fc1a43903c2602f3c7f0e9d9d982 | f03dd22953b6 | Phase 6: finish README with code-verified claims |
| 14 | 85732f6faaf866a05417db02f6772627fb81ebc0 | 49b067555d5a9daf739c693d3386667e261a4d4e | 8b3dd7d550ae | gitignore .claude |
| 15 | 09ed0f77a554ee4e46564c8258c2146c820fea92 | 574f3ddbb794fbd46b253c3e39546ff130f1b05f | b06b6818b9ad | Phase 7: static map (SVG, no tiles/keys), forecast JSON from |

## L1/L2 — Lag ablation: how much do lag_24h / lag_48h carry? (audit finding 1.1; rules written BEFORE running)
- Terminology: from now on the forecast is called **rolling 24-hour-ahead** (each hour forecast with inputs known >= 24 h earlier), not "day-ahead". Earlier log entries (for example S3, which speaks of "day-ahead errors") use "day-ahead" loosely in that sense; they are not rewritten.
- Question: a day-ahead forecast issued once per day (say at 10:00 on day D for the 24 hours of D+1) cannot use lag_24h for the hours of D+1 after the issue time. Lags of 48 h or more are known for every hour of D+1. How much worse is the model without lag_24h / lag_48h?
- Setup (VALIDATION ONLY, 2024-10-25..2025-10-24; train only on the train period; the sealed test file is not read; LOCKED models and the lock file are not touched): same per-zone LightGBM as M2 (same hyperparameters, seed 42, same weather and calendar features, same row filter), only the lag list changes.
  - L1 = lags 48, 168, 336 h (drop lag_24h). Valid for a single daily issue time.
  - L2 = lags 168, 336 h (drop lag_24h and lag_48h). The conservative "true day-ahead" variant, which does not use any load from the last 7 days.
  - Reference = M2 (lags 24, 48, 168, 336 h): mean MAE 393.5 over zones (531 / 524 / 355 / 164).
- This is a report-only experiment: it changes no model and nothing is "kept" or "reverted". I report per-zone and mean MAE, the change versus M2, and whether rule v2 (>= 5% below B1; not worse than B1 on holidays, hottest 5% and coldest 5% days) would still hold.
- Interpretation rule: if L2's mean MAE is more than 15% above M2's, the README says the headline MAEs depend materially on lag_24h/lag_48h and must not be read as day-ahead numbers; if it is at most 15% above, the README says the dependence is modest. The README limitation quotes the measured numbers either way.
- Command: `python scripts/run_lag_ablation.py`

### L1/L2 results (command: `python scripts/run_lag_ablation.py`; file results/lag_ablation_val.csv; validation only; rule committed first in 33e9d36)
MAE in MWh/h on the validation year, per-zone LightGBM, only the lag list changes. The reference row reproduces M2 exactly (mean 393.5), which checks the setup.
| variant | 50Hertz | Amprion | TenneT | TransnetBW | mean | vs M2 |
|---|---|---|---|---|---|---|
| M2 (lags 24, 48, 168, 336) | 530.9 | 524.3 | 354.8 | 164.1 | 393.5 | - |
| L1 (lags 48, 168, 336; drops lag_24h) | 548.0 | 581.4 | 392.3 | 190.0 | 427.9 | +8.7% |
| L2 (lags 168, 336; drops lag_24h and lag_48h) | 568.8 | 636.1 | 435.1 | 218.7 | 464.7 | +18.1% |
Per zone vs M2: L1 +3.2% / +10.9% / +10.6% / +15.8%; L2 +7.1% / +21.3% / +22.6% / +33.3% (50Hertz / Amprion / TenneT / TransnetBW). B1 (last week) for reference: 922.5 / 1003.1 / 791.0 / 449.9.
- Rule v2 (>= 5% below B1, and not worse than B1 on holidays, hottest 5%, coldest 5% days): still passes in all four zones for both variants.
- Interpretation rule applied as written: L2 is +18.1%, more than 15%, so the headline MAEs depend MATERIALLY on lag_24h/lag_48h and must not be read as day-ahead numbers. The variant valid for a single daily issue time (L1, lags >= 48 h) is +8.7% on average, up to +15.8% for TransnetBW. Even the conservative L2 is 41-51% below B1 in every zone, so the model still beats the baseline without the short lags.
- Decision: report only. The locked models, the lock file and the final-test results are unchanged; no sealed data was read.
- Commit: see the git log entry "Fix 1c".

## R1 — Record of every read of the sealed test file (added after the audit; earlier entries unchanged)
CLAUDE.md says the test period is touched once. Accurate record: ONE evaluation (scripts/final_eval.py --confirm-final, 2026-11-08, entry F1). The file data/processed/sealed_test.parquet was read in two further places, both after F1, neither computing an error metric nor changing any model, offset or result:
1. scripts/export_site_data.py (Phase 7, on the owner's instruction) read it to compute the map's hourly forecasts with the locked models.
2. A one-off snippet, run in the terminal and not saved as a script, counted NaN values per column and zone to document missing inputs. It is quoted here so it can be checked:
```python
t=pd.read_parquet("data/processed/sealed_test.parquet")
cols=["load_mw","lag_24h","lag_168h","lag_336h","w_temperature_2m","w_relative_humidity_2m","w_wind_speed_10m","w_shortwave_radiation","w_cloud_cover"]
t.groupby("zone")[cols].apply(lambda d: d.isna().sum())
need=["lag_336h","lag_168h","load_mw"]   # rows excluded = any of these NaN; also printed: NaN dates (min/max/count per zone)
```
Result: 50Hertz 2 hours with missing load (and so 2 with missing lag_24h, lag_168h, lag_336h each), 6 rows excluded in total, no missing weather; the other zones none. The numbers agree with site/data/meta.json (hours_left_out = 6, 0, 0, 0).
"Run once" is enforced only by the marker file results/FINAL_EVAL_DONE (a convention).

## H2 — Process note: which rules were committed before their results, and real commit hashes (added after the audit; earlier entries are NOT edited)
CLAUDE.md asks for "keep/revert rules written BEFORE seeing results" and a commit hash per experiment. Two honest corrections:
1. **Rule-first ordering is provable from git only for some entries.** For B0/B1, Q1/Q2, Q3/Q4, S0-S4 and P7 the rule text and the results were committed together (one commit each, see the table). In the working session the rule text was appended to this file before the script was run, but git cannot show that, and the session transcript is not part of the repository. Provable from git, because the rule was committed in an earlier commit than the results: RULE v2 and the M1-M4 plan (16e970f before the results in c42dfd9), F1 (rules and model lock in 997c488 before the run and its results in 58dc54a) and L1/L2 (33e9d36 before 5fd6627). The owner's "continue" approvals at the checkpoints are likewise in the session transcript, not in git. From now on a rule is committed in its own commit before the experiment is run.
2. **The entries that say "Commit: see git log (...)" are resolved here with real hashes** (the current hashes, after the history rewrite of 2026-11-09; the old hashes are in entry H1). A commit cannot contain its own hash, so a hash is recorded in the NEXT commit's log entry.

| entry | rule committed in | results committed in | rule before results in git? |
|---|---|---|---|
| Phase 0 setup | - | f789d4d | - |
| Phase 1 data / tests / data card | - | 289bb2d | - |
| B0/B1 baselines | 3b2ef62 | 3b2ef62 | no (same commit) |
| D1 dataset end moved 14 days | 16e970f | 16e970f | no (same commit) |
| RULE v2 + M-plan | 16e970f | - | yes (before c42dfd9) |
| M1-M4 models | 16e970f | c42dfd9 | yes |
| Q1/Q2 quantiles + CQR | bec36c8 | bec36c8 | no (same commit) |
| Q3/Q4 hour-of-day CQR (rejected) | 9e2de36 | 9e2de36 | no (same commit) |
| S0-S4 stress tests | a42fc3f | a42fc3f (count fix 4bc8933) | no (same commit) |
| Phase 6 prep (train_final, final_eval gate, tests) | - | 2a5f715 | - |
| F1 final evaluation | 997c488 (rules + SHA-256 lock) | 58dc54a (run once + results), 4b47180 (README) | yes |
| P7 map data and site | 574f3dd | 574f3dd | no (same commit) |
| gitignore .claude | - | 49b0675 | - |
| H1 hash mapping | - | 9aeab25 | - |
| L1/L2 lag ablation | 33e9d36 | 5fd6627 (+ README rename b19ad9c) | yes |
| R1 sealed-file reads | - | 8177c3e | - |
| Audit fix 2 (tests, train_final --force, README) | - | 52bf65c | - |
| Audit fix 4 (pinned requirements) | - | 6d1e03c | - |

## C1 — Corrections to numbers in earlier entries (appended after the audit; earlier entries are NOT edited)
Recomputed from the CSV files in results/:
- S3 (weather noise, level x1), three zones other than TransnetBW: MAE rises by 1.7-8.7% (all four zones: 1.7-25%), not "3-10%" as written in the S3 results above. The README already says +2-9%. Source: results/stress_s3_s4.csv.
- F1 coverage by hour: the 80% band covers 64.0-67.4% of test values at 12-16 h (mean over zones: 67.4, 66.6, 64.8, 64.0, 65.9%), not "0.65-0.67" as written in the F1 results above. The README now says 64-67%. Source: results/final_test_coverage_by_hour.csv.
- S4 missing load history: the "+35-41%" (10% missing) and "+125-136%" (30%) are averages over zones; per zone the 10% case is +19% (50Hertz) to +53% (Amprion), the 30% case +61% to +191%. Source: results/stress_s3_s4.csv.
- Popup wording: the split-state text no longer says that "most" of a state lies in its dominant zone, since no source gives shares (see the zone-assignment note in P7).

## O1 — Benchmark against SMARD's official "Forecasted consumption" (rule written BEFORE the series was downloaded or any number computed)
- Availability check (only listings and a few sample weeks were looked at, no comparison): SMARD filter **411**, quarter-hourly, exists for each of the four control areas (50Hertz, Amprion, TenneT, TransnetBW) and for DE, from 2015 to now, populated, same units as grid load 410 (MWh per 15 min; values of the same size as actual load). So the official forecast is available PER ZONE, not only nationally. Evidence for what it is: SMARD, "Electricity consumption" article (https://www.smard.de/en/wiki-article/5884/6036): predicted consumption is shown next to the actual one; "Transmission system operators submit the predicted value the day before on the basis of the results of day-ahead trading and other empirical data. Nevertheless, the data may be updated subsequently if there are significant changes, ie of more than 10%." SMARD "Forecast data" article (https://www.smard.de/page/en/wiki-article/5884/206318/forecast-data): the forecast data is submitted by the four German TSOs for their control areas and aggregated for Germany. I identified 411 by this documentation plus its scale; the API itself does not return a series name.
- What is compared: on the SEALED TEST YEAR (2025-10-25..2026-10-24 UTC), per zone, the official forecast (hourly = sum of the 4 quarter-hours, all 4 needed, UTC hours as for the load) against the same actual hourly load (series 410) that our model was scored on. The actuals and the hours come from the committed map files site/data/{zone}.json (hours with test flag s = 1, which are exactly the rows of the F1 evaluation: 8,754 / 8,760 / 8,760 / 8,760 hours); the sealed parquet file is NOT read again.
- Our model's numbers are NOT recomputed: they are copied from results/final_test_metrics.csv (M2 mean model and B1) as logged in F1. No new model, no retuning, no new model metric on the test year. As context only, the same comparison is shown on the VALIDATION year (our M2 numbers from the logged lag-ablation / M2 results, official computed the same way); validation is not a test result.
- Metrics for the official forecast: MAE, RMSE, MAPE (same definitions as src/gepf/evalutil.py), per zone. No national total and no holiday/hot/cold subsets (they would need new metrics for our model or reading the sealed file).
- If the official forecast is missing for some of our evaluated hours, those hours are dropped from the OFFICIAL metrics only and the hour counts are shown; our logged numbers are not recomputed on the intersection. If more than 1% of hours were missing, the comparison would be flagged as not like-for-like.
- Result reading rule (declared now): our model "wins" a zone if its logged test MAE is lower than the official MAE for that zone; differences within 1% of the official MAE are called a tie. The result is reported whether or not we win.
- Asymmetries that must be stated next to the result (README and log): the official forecast is a true day-ahead forecast, issued the day before (and per SMARD possibly updated if the change exceeds 10%), using day-ahead trading results and forecast information available at that time; our model is a rolling 24-hour-ahead forecast that uses lag_24h (and lag_48h) and observed weather instead of forecast weather. This favours our model. The size of the lag part, from the validation-only ablation (entry L1/L2, locked models unchanged): without lag_24h +8.7% mean validation MAE, without lag_24h and lag_48h +18.1%. These are validation figures; no adjusted test numbers are computed from them.
- Command (after this commit): `python scripts/download_official_forecast.py` then `python scripts/compare_official_forecast.py`.
