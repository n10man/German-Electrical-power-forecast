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

def interval_rows():
    """Validation replay of the interval methods (I1): coverage, width, interval score, from results/interval_val_summary.csv."""
    S = pd.read_csv(ROOT / "results/interval_val_summary.csv")
    rows = ["| Method | Mean coverage 80% / 95% | Worst cell 80% / 95% | Mean width (MWh/h) | Mean interval score | Score vs static | Admissible |", "|---|---|---|---|---|---|---|"]
    for _, r in S.iterrows():
        rows.append(f"| {r.candidate} | {r.mean_coverage_80:.1f}% / {r.mean_coverage_95:.1f}% | {r.min_cell_cov_80:.1f}% / {r.min_cell_cov_95:.1f}% | {r.mean_width:,.0f} | {r.mean_interval_score:,.0f} | {r.R_score_ratio_vs_static:.3f} | {'yes' if r.admissible else 'no'} |")
    return rows

def model_rows():
    """LightGBM vs ridge vs MLP (M5), validation MAE, from results/model_comparison_val.csv."""
    D = pd.read_csv(ROOT / "results/model_comparison_val.csv")
    rows = ["| Zone | Days ahead | LightGBM | Ridge | Small neural net (mean, range of 3 seeds) |", "|---|---|---|---|---|"]
    for _, r in D.iterrows():
        rows.append(f"| {r.zone} | {r.k} | {r.mae_lightgbm:,.0f} | {r.mae_ridge:,.0f} | {r.mae_mlp_mean:,.0f} ({r.mae_mlp_min:,.0f}-{r.mae_mlp_max:,.0f}) |")
    s = json.load(open(ROOT / "results/model_comparison_summary.json"))
    rows.append(f"| **Pooled (sum of 12 cells)** | | {s['pooled']['mae_lightgbm']:,.0f} | {s['pooled']['mae_ridge']:,.0f} | {s['pooled']['mae_mlp_mean']:,.0f} |")
    return rows

def future_rows():
    """Multi-day models on the sealed test year (1, 7 and 21 days ahead): MAE of our model and, in brackets, of the best simple baseline at the same distance."""
    f = pd.read_csv(ROOT / "results/future_test_metrics.csv").set_index(["zone", "k"])
    rows = ["| Zone | 1 day ahead | 7 days ahead | 21 days ahead |", "|---|---|---|---|"]
    for z in ZONES:
        cell = lambda k: f"{f.loc[(z, k), 'MAE_model']:,.0f} ({f.loc[(z, k), 'MAE_best_simple_baseline']:,.0f})"
        rows.append(f"| {z} | {cell(1)} | {cell(7)} | {cell(21)} |")
    return rows

def interval_summary_rows():
    """The short 3-row version for the README: static, the selected rolling method, and the best adaptive method (excluded by the rule). Lines identical to interval_rows()."""
    r = interval_rows(); keep = {"static", "rolling_8w", "aci_g0.005"}
    return r[:2] + [l for l in r[2:] if l.split("|")[1].strip() in keep]

def interval_short_rows():
    """The README's 3-row table: plain labels, typical coverage and average width, from results/interval_val_summary.csv."""
    S = pd.read_csv(ROOT / "results/interval_val_summary.csv").set_index("candidate")
    labels = [("static", "Old method: one fixed setting (`static`)"), ("rolling_8w", "New method: reset on the last 8 weeks (`rolling_8w`)"), ("aci_g0.005", "Self-adjusting method, left out because the ranges got too wide (`aci_g0.005`)")]
    rows = ["| Method | Typical share of real values inside the 80% and 95% ranges | Average width of the 80% range plus 95% range, in MWh/h |", "|---|---|---|"]
    for k, lab in labels:
        r = S.loc[k]; rows.append(f"| {lab} | {r.mean_coverage_80:.1f}% and {r.mean_coverage_95:.1f}% | {r.mean_width:,.0f} |")
    return rows
