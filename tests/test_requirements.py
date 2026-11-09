"""The pinned requirements must be enough to train the models: LightGBM's scikit-learn API needs scikit-learn (found by a clean-clone run)."""
import numpy as np, lightgbm as lgb
from pathlib import Path

def test_lightgbm_sklearn_api_trains():
    rng = np.random.default_rng(0); X = rng.normal(size=(60, 3)); y = X[:, 0] + rng.normal(scale=0.1, size=60)
    m = lgb.LGBMRegressor(n_estimators=3, verbose=-1).fit(X, y)
    assert np.isfinite(m.predict(X)).all()

def test_requirements_are_pinned_and_include_scikit_learn():
    lines = [l.split("#")[0].strip() for l in (Path(__file__).resolve().parents[1] / "requirements.txt").read_text().splitlines()]
    reqs = [l for l in lines if l]
    assert all("==" in l for l in reqs), reqs
    assert any(l.startswith("scikit-learn==") for l in reqs)
