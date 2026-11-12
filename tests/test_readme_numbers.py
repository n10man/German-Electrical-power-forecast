"""The headline numbers in the README must match the results files."""
import sys, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import readme_results_table as T
README = (ROOT / "README.md").read_text()
DETAILS = (ROOT / "docs/DETAILED_RESULTS.md").read_text()

def test_results_table_matches_results_files():
    for line in T.table(): assert line in README, line

def test_future_and_short_interval_rows_match_results_files():
    for line in T.future_rows() + T.interval_short_rows(): assert line in README, line

def test_headline_coverage_numbers_match_site_meta():
    c80, c95 = T.coverage(); assert c80 in README and c95 in README
    import json; z = json.load(open(ROOT / "site/data/meta.json"))["test_coverage_cqr_by_zone"]["TenneT"]
    assert f"{z['80']}% and {z['95']}%" in README

def test_readme_structure_order_and_required_lines():
    heads = re.findall(r"^## (.+)$", README, re.M)
    assert heads == ["Data and licences", "The problem we set out to solve", "What we built", "How the results were tested", "Results", "How sure are we?", "Stress tests", "Other models we tried", "The interactive map",
                     "Prospective check (pending)", "Problems and mistakes we ran into", "Limitations", "Lessons for next time"], heads        # the problem section comes second; ends with Limitations, then Lessons
    assert README.startswith("# Germany electricity demand forecasting\n") and "In 60 seconds" not in README
    assert "\nLive map: https://germany-electricity-forecast.netlify.app\n" in README and "[link to be added]" not in README
    for d in ("docs/METHODS.md", "docs/DETAILED_RESULTS.md", "docs/HOW_TO_RUN.md", "results/EXPERIMENTS.md"): assert d in README.split("## Data and licences")[0], d
    assert "AI-assisted and not fully reviewed yet" in README and "Claude Code" not in README
    assert "<!-- PROSPECTIVE:START -->" in README and "<!-- PROSPECTIVE:END -->" in README

def test_required_credits_and_licence_lines_are_kept():
    for needle in ("Bundesnetzagentur \\| SMARD.de", "CC BY 4.0", "Weather data by [Open-Meteo.com](https://open-meteo.com/)", "non-commercial", "grey area", "dl-de/by-2-0", "https://sg.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_vg_nuts.pdf",
                   "`holidays` package", "MIT", "data/DATA_SOURCES.md", "Raw data is not committed"): assert needle in README, needle
    for old in ("has not been compared with the TSOs", "striped", "UTC+8", "the owner's", "In 60 seconds", "See *The problem we set out to solve*", "Good to know"): assert old not in README, old
    assert "problem we set out to solve" not in (ROOT / "docs/DETAILED_RESULTS.md").read_text().lower()
    assert "has not completed a deployment yet" in (ROOT / "docs/HOW_TO_RUN.md").read_text() and "billing" not in (ROOT / "docs/HOW_TO_RUN.md").read_text().lower()

def test_privacy_sentence():
    for needle in ("no cookies", "no tracking", "no requests to other websites", "saved only in your own browser", "standard server logs"): assert needle in README, needle

def test_headline_ranges_in_text_trace_to_files():
    import pandas as pd
    m = pd.read_csv(ROOT / "results/final_test_metrics.csv").set_index(["zone", "model"]).MAE
    gain = [100 * (1 - m[(z, "M2_mean_model")] / m[(z, "B1_last_week")]) for z in T.ZONES]; assert f"{round(min(gain))}% to {round(max(gain))}% smaller than copying last week" in README
    o = pd.read_csv(ROOT / "results/official_forecast_comparison.csv"); t = o[o.period == "test"]; off = t[t.model.str.startswith("SMARD")].set_index("zone").MAE
    g2 = [100 * (1 - m[(z, "M2_mean_model")] / off[z]) for z in T.ZONES]; assert f"({round(min(g2))}% to {round(max(g2))}% smaller)" in README
    f = pd.read_csv(ROOT / "results/future_test_metrics.csv"); gf = 100 * f.gain_vs_best_baseline; assert f"by {round(gf.min())}% to {round(gf.max())}%" in README and len(f) == 36
    mc = __import__("json").load(open(ROOT / "results/model_comparison_summary.json"))["pooled"]
    assert f"pooled average miss {mc['mae_mlp_mean']:,.0f} against {mc['mae_lightgbm']:,.0f}; ridge {mc['mae_ridge']:,.0f}" in README

def test_other_readme_numbers_trace_to_files():
    import pandas as pd
    d = pd.read_csv(ROOT / "results/lag_ablation_val.csv").pivot(index="zone", columns="variant", values="mae_all"); pooled = d.sum() / d.sum()["M2_ref_24_48_168_336"] - 1
    assert round(100 * pooled["L1_48_168_336"], 1) == 8.7 and round(100 * pooled["L2_168_336"], 1) == 18.1 and "grew by 8.7%" in README and "by 18.1%" in README     # without lag_24h / without lag_24h and lag_48h
    m = pd.read_csv(ROOT / "results/final_test_metrics.csv").set_index(["zone", "model"]).MAE
    o = pd.read_csv(ROOT / "results/official_forecast_comparison.csv"); v = o[(o.period == "validation") & o.model.str.startswith("our model")].set_index("zone").MAE
    rise = [100 * (m[(z, "M2_mean_model")] / v[z] - 1) for z in T.ZONES]
    assert round(min(rise)) == 5 and round(max(rise)) == 35 and "(5% to 35% more error)" in README

def test_detailed_results_tables_match_results_files():
    for line in T.interval_rows() + T.model_rows(): assert line in DETAILS, line
    import pandas as pd
    m = pd.read_csv(ROOT / "results/final_test_metrics.csv").set_index(["zone", "model"]).MAE
    o = pd.read_csv(ROOT / "results/official_forecast_comparison.csv"); t = o[o.period == "test"].set_index(["zone", "model"]).MAE
    for z in T.ZONES:       # the full 8-column final table (moved here from the README)
        row = next(l for l in DETAILS.splitlines() if l.startswith(f"| {z} | ") and len(l.split("|")) >= 9); c = [x.strip() for x in row.strip("|").split("|")]
        assert c[1] == f"{m[(z, 'B1_last_week')]:.0f}" and c[2] == f"{t[(z, 'SMARD official day-ahead forecast (filter 411)')]:.0f}" and c[3] == f"{m[(z, 'M2_mean_model')]:.0f}", (z, c)


def test_jargon_free_readme_and_moved_items_are_in_detailed_results():
    for word in ("lag_24h", "lag_48h", "MAE", "conformal", "conformalized", ".py", "test_", "pytest"): assert word not in README, word
    assert "SHA-256" in README and "35791f5ee8372a29edf7cfdef3316c0c37b9a1f6" in README
    assert "## 10. More limitations and small issues" in DETAILS
    for moved in ("Missing hours for 50Hertz", "HTTP 429", "Hessen and Frankfurt", "main()` guard", "Few examples for special days", "Observed weather in the headline numbers", "Browsers and translations"): assert moved in DETAILS, moved
    assert "Reuse notes" in (ROOT / "data/DATA_SOURCES.md").read_text()
    assert "problem we set out to solve" not in README.split("## The problem we set out to solve")[0]       # no pointer to that section from anywhere above it
    for line in T.interval_short_rows(): assert line in README

def test_map_colours_named_in_readme_match_the_site():
    js = (ROOT / "site/app.js").read_text(); assert '"50Hertz": "#0072B2", "Amprion": "#E69F00", "TenneT": "#009E73", "TransnetBW": "#CC79A7"' in js
    assert "50Hertz is blue, Amprion is orange, TenneT is green and TransnetBW is pink" in README
