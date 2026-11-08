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
