# How to run

Everything needed to run the map, reproduce the results and refresh the future-forecast snapshot. Back to the [README](../README.md).

## Run the map locally
```bash
python3 -m http.server -d site 8000   # then open http://localhost:8000
```
The page loads JSON files, so opening `index.html` directly (`file://`) does not work. Visitors' browsers make no requests to any other site, set no cookies and send nothing anywhere. Deep links work, for example `http://localhost:8000/#state=BY&date=2026-01-14&hour=12`.

## Reproduce
Install the pinned packages (`requirements.txt` for the models; `requirements-dev.txt` adds `shapely`, which is only needed to rebuild the state shapes), then follow the command list below (data download, dataset build, models, evaluation). Every experiment, with its rules written before the results, is in [`results/EXPERIMENTS.md`](../results/EXPERIMENTS.md).

## Full command list
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt        # exact versions (Python 3.14.5), incl. shapely for the map shapes; on macOS LightGBM needs libomp: brew install libomp
python scripts/download_load.py            # slow: roughly 25-40 min per zone
python scripts/download_reference.py       # SMARD national series, used only for checks
python scripts/download_weather.py
python scripts/build_dataset.py            # writes data/processed/{trainval,sealed_test}.parquet
python scripts/data_card.py                # sanity numbers and plots (train+validation only)
python scripts/baselines.py
python scripts/run_models.py M1 M2 M3 M4
python scripts/run_quantiles.py && python scripts/run_quantiles_hourly.py
python scripts/run_lag_ablation.py         # validation-only lag ablation
python scripts/download_official_forecast.py   # SMARD official day-ahead forecast (benchmark only)
python scripts/stress_tests.py
python scripts/train_final.py --force      # rebuilds models/ (gitignored) and OVERWRITES results/model_lock.json, see below
python scripts/download_states.py && python scripts/build_site_geo.py   # state shapes
python scripts/export_site_data.py         # map data from the locked models
python scripts/compare_official_forecast.py     # benchmark table; needs site/data and the downloaded official forecast
python scripts/check_official_forecast_sanity.py  # post-hoc sanity check of the official series
python scripts/download_forecast_archive.py   # Open-Meteo archived past forecasts (Previous Runs API), 72 requests, slow
python scripts/run_horizon_models.py A && python scripts/run_horizon_models.py B && python scripts/run_horizon_models.py C   # validation only
python scripts/select_horizons.py          # choice + show-on-map rule, validation only
python scripts/train_future.py --force     # rebuilds models_future/ (gitignored) and OVERWRITES results/model_lock_future.json
python scripts/final_eval_future.py --confirm-final   # ONE-SHOT: already done (exit 3); see EXPERIMENTS.md F2
python scripts/download_forecast_current.py && python scripts/make_future_forecast.py   # future snapshot for the map
python scripts/make_summary_chart.py       # the bar chart in the Results section of the README
PYTHONPATH=src pytest                      # last, so that no test is skipped; see the notes below
python3 -m http.server -d site 8000        # serve the map (keeps running; open http://localhost:8000)
```

## Tests and what they need
Run `PYTHONPATH=src pytest`. The data-sanity tests skip when `data/raw/` is absent, the site-data tests skip when `site/data/` is absent, and the model-dependent gate tests skip with the message "models/ is absent or empty" until `models/` exists (it is gitignored, so a fresh checkout has no models). Run `train_final.py` *before* `pytest` if you want all of them to run. On a fresh checkout without data or models some tests are therefore skipped, not passed.

## `train_final.py` and the committed lock
`results/model_lock.json` is committed and its hashes are quoted in `results/EXPERIMENTS.md` (entry F1). The script now refuses to run when that file exists unless you pass `--force`, because re-training may produce different hashes and would overwrite the lock. To check whether your rebuild reproduces the committed hashes, run it with `--force`, then `git diff results/model_lock.json` (no diff means identical hashes); restore the committed lock with `git checkout results/model_lock.json` if they differ.

## `final_eval.py` is one-shot
`python scripts/final_eval.py --confirm-final` evaluated the sealed test period exactly once (2026-11-08) and cannot be run again: it exits with code 3 because `results/FINAL_EVAL_DONE` exists (exit 2 without `--confirm-final`, exit 4 if a model file does not match the lock). The results are stored in `results/final_test_metrics.csv`, `final_test_subsets.csv`, `final_test_coverage.csv`, `final_test_coverage_by_hour.csv` and `final_test_meta.json`, and are committed. The "once" is enforced only by the marker file (a convention: deleting it would allow a second run, which would break the protocol). `--dummy --out-dir <dir>` runs the pipeline on synthetic data without touching the sealed file or `results/`.

## Refresh the future-forecast snapshot (one command)
```bash
scripts/refresh_snapshot.sh        # or: python scripts/refresh_snapshot.py
```
It updates the SMARD load files (the old ones are copied to `data/raw/_old_load_<time>/`), downloads the current 16-day weather forecast (12 requests, with the retry logic for HTTP 429 answers), regenerates the snapshot and a new dated log in `results/prospective/` (older logs are kept), runs the tests, and stops with an error if any past-date map file changed. It runs no git commands. Review the result and commit it yourself. The steps are tested with mocked downloads in `tests/test_refresh_snapshot.py`.

Note that a refresh uses the original (fixed) range method. The rolling recalibration of the ranges is applied afterwards with `python scripts/make_new_intervals.py`, which reads the dated log; I have not wired that into the refresh.

## Set the public address once hosting is decided
```bash
python scripts/set_site_url.py https://example.org/map    # fills site/config.js and the absolute image / URL tags used for social previews
python scripts/set_site_url.py ""                          # clears it again
```

## Browser checks (optional)
`tests/test_layout_browser.py` uses headless Chrome (skipped if Chrome is absent). `scripts/check_site_browsers.py` runs the page in Chromium and WebKit with Playwright (not a project dependency; the install line is in the script's docstring) and writes `results/site_browser_check.json`. I could not run Firefox in my setup.

## Hosting
The site is a static folder (`site/`) with relative links only, so it works on any static host. A GitHub Pages workflow is included.

**GitHub Pages.** In the GitHub repository choose Settings -> Pages -> Build and deployment -> Source: "GitHub Actions" (no folder to pick). The workflow `.github/workflows/pages.yml` then publishes the `site/` folder on every push to `main` that changes it, or when started by hand from the Actions tab; the map appears at `https://<your-github-username>.github.io/<repository-name>/`. The "Deploy from a branch" option does not work here, because it only offers the repository root or a `/docs` folder, not `site/`. I wrote the workflow and tested the site locally under a subpath, but the workflow has not completed a deployment yet.
