import numpy as np, pandas as pd
from gepf.models import feats, fit
QS = [0.025, 0.1, 0.5, 0.9, 0.975]
BANDS = {"80": (0.1, 0.9, .80), "95": (0.025, 0.975, .95)}

def fit_quantiles(t, f):
    """One LightGBM quantile model per alpha; returns dict alpha -> model."""
    return {a: fit(t[f], t.load_mw, objective="quantile", alpha=a) for a in QS}

def predict_quantiles(models, X, f):
    P = np.column_stack([models[a].predict(X[f]) for a in QS])
    return pd.DataFrame(np.sort(P, axis=1), index=X.index, columns=[f"q{a}" for a in QS])

def cqr_offset(y, lo, hi, nominal):
    s = np.maximum(lo - y, y - hi); n = len(s)
    if n == 0: return 0.0
    k = min(1.0, np.ceil((n + 1) * nominal) / n); return float(np.quantile(s, k, method="higher"))
