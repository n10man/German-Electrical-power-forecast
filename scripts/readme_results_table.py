"""Print the README's headline results table (test-year MAE, MWh/h) straight from results/*.csv, so the README numbers can be pasted and tested.
   python scripts/readme_results_table.py"""
import json
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]; ZONES = ["50Hertz", "Amprion", "TenneT", "TransnetBW"]

def table():
    m = pd.read_csv(ROOT / "results/final_test_metrics.csv").set_index(["zone", "model"]).MAE
    o = pd.read_csv(ROOT / "results/official_forecast_comparison.csv"); o = o[o.period == "test"].set_index(["zone", "model"]).MAE
    f = pd.read_csv(ROOT / "results/future_test_metrics.csv").set_index(["zone", "k"]).MAE_model
    rows = ["| Zone | Last week's load (simple baseline) | SMARD official day-ahead forecast | Our model, 24 h rolling | Our model, 7 days ahead | Our model, 21 days ahead |", "|---|---|---|---|---|---|"]
    for z in ZONES:
        rows.append(f"| {z} | {m[(z, 'B1_last_week')]:,.0f} | {o[(z, 'SMARD official day-ahead forecast (filter 411)')]:,.0f} | {m[(z, 'M2_mean_model')]:,.0f} | {f[(z, 7)]:,.0f} | {f[(z, 21)]:,.0f} |")
    return rows

def coverage():
    c = json.load(open(ROOT / "site/data/meta.json"))["test_coverage_cqr_mean"]
    return f"{c['80']}%", f"{c['95']}%"

if __name__ == "__main__":
    print("\n".join(table())); print("coverage 80/95:", *coverage())
