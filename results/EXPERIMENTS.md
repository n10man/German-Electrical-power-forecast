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
