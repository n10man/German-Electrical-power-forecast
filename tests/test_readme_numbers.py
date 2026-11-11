"""The headline numbers in the README must match the results files."""
import sys, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import readme_results_table as T
README = (ROOT / "README.md").read_text()

def test_results_table_matches_results_files():
    for line in T.table(): assert line in README, line

def test_headline_coverage_numbers_match_site_meta():
    c80, c95 = T.coverage(); top = README.split("### Run the map locally")[0]
    assert c80 in top and c95 in top
    import json; z = json.load(open(ROOT / "site/data/meta.json"))["test_coverage_cqr_by_zone"]["TenneT"]
    assert f"TenneT {z['80']}% and {z['95']}%" in top

def test_limitations_come_before_results_and_placeholder_is_marked():
    top = README.split("### Run the map locally")[0]
    assert top.index("### Limitations first") < top.index("### Results")
    assert "`[URL to be added once hosting is decided]`" in top
    assert "AI assistance" in README and "corrections are welcome" in README

def test_other_readme_numbers_trace_to_files():
    import pandas as pd
    d = pd.read_csv(ROOT / "results/lag_ablation_val.csv").pivot(index="zone", columns="variant", values="mae_all"); pooled = d.sum() / d.sum()["M2_ref_24_48_168_336"] - 1
    assert round(100 * pooled["L1_48_168_336"], 1) == 8.7 and round(100 * pooled["L2_168_336"], 1) == 18.1 and "9% to 18%" in README     # without lag_24h / without lag_24h and lag_48h
    m = pd.read_csv(ROOT / "results/final_test_metrics.csv").set_index(["zone", "model"]).MAE
    o = pd.read_csv(ROOT / "results/official_forecast_comparison.csv"); v = o[(o.period == "validation") & o.model.str.startswith("our model")].set_index("zone").MAE
    rise = [100 * (m[(z, "M2_mean_model")] / v[z] - 1) for z in T.ZONES]
    assert round(min(rise)) == 5 and round(max(rise)) == 35 and "5% to 35%" in README

def test_interval_and_model_tables_match_results_files():
    for line in T.interval_rows() + T.model_rows(): assert line in README, line
    assert "<!-- PROSPECTIVE:START -->" in README and "<!-- PROSPECTIVE:END -->" in README
