"""O1 benchmark vs SMARD's official day-ahead forecast: file checks only (no model, no sealed file)."""
import re
from pathlib import Path
import numpy as np, pandas as pd, pytest
from gepf.data import ZONES

ROOT = Path(__file__).resolve().parents[1]; CSV = ROOT / "results/official_forecast_comparison.csv"
pytestmark = pytest.mark.skipif(not CSV.exists(), reason="results/official_forecast_comparison.csv missing: run scripts/compare_official_forecast.py (needs the downloaded official forecast and site/data)")
OFF = "SMARD official day-ahead forecast (filter 411)"

@pytest.fixture(scope="module")
def R(): return pd.read_csv(CSV)

def test_schema_and_rows(R):
    assert list(R.columns) == ["period", "zone", "model", "n_hours_scored", "n_hours_in_our_eval", "MAE", "RMSE", "MAPE"]
    assert len(R) == 24 and set(R.zone) == set(ZONES) and set(R.period) == {"test", "validation"}
    assert np.isfinite(R.MAE).all() and (R.MAE > 0).all()
    assert (R[R.model == OFF][["MAE", "RMSE", "MAPE"]].notna().all()).all()

def test_our_model_numbers_are_copied_from_the_f1_log_not_recomputed(R):
    log = pd.read_csv(ROOT / "results/final_test_metrics.csv")
    for z in ZONES:
        for name, m in (("our model (logged, F1)", "M2_mean_model"), ("B1 last week (logged, F1)", "B1_last_week")):
            a = R[(R.period == "test") & (R.zone == z) & (R.model == name)].iloc[0]; b = log[(log.zone == z) & (log.model == m)].iloc[0]
            assert (a.MAE, a.RMSE, a.MAPE, a.n_hours_scored) == (b.MAE, b.RMSE, b.MAPE, b.n)

def test_hour_counts_and_missing_share(R):
    t = R[(R.period == "test") & (R.model == OFF)].set_index("zone")
    assert t.n_hours_in_our_eval.to_dict() == {"50Hertz": 8754, "Amprion": 8760, "TenneT": 8760, "TransnetBW": 8760}
    assert ((t.n_hours_in_our_eval - t.n_hours_scored) / t.n_hours_in_our_eval).max() <= 0.01      # like-for-like flag of the O1 rule

def test_scripts_do_not_read_the_sealed_file():
    for f in ("compare_official_forecast.py", "check_official_forecast_sanity.py", "download_official_forecast.py"):
        text = (ROOT / "scripts" / f).read_text()
        assert "sealed_test" not in text and "data/processed" not in text, f

def test_readme_states_caveats_and_matches_csv(R):
    readme = (ROOT / "README.md").read_text(); details = (ROOT / "docs/DETAILED_RESULTS.md").read_text()      # the full table moved to docs/DETAILED_RESULTS.md
    for needle in ("true day-ahead forecast", "rolling 24-hour-ahead", "favours us", "not like-for-like", "+8.7%", "+18.1%"):
        assert needle in details, needle                      # the long explanation moved to docs/DETAILED_RESULTS.md
    for needle in ("not a fair fight", "8.7%", "18.1%", "does not show that we beat the grid operators"): assert needle in readme, needle
    for z in ZONES:
        row = next(l for l in details.splitlines() if l.startswith(f"| {z} | ") and "official" not in l and len(l.split("|")) >= 9)
        cells = [c.strip() for c in row.strip("|").split("|")]
        t = R[(R.period == "test") & (R.zone == z)].set_index("model").MAE
        assert cells[1] == f"{t['B1 last week (logged, F1)']:.0f}" and cells[2] == f"{t[OFF]:.0f}" and cells[3] == f"{t['our model (logged, F1)']:.0f}", (z, cells)
