"""Phase 4: quantile LightGBM (Q1) + CQR conformal calibration (Q2). Validation only."""
import sys; sys.path.insert(0, "src")
import numpy as np, pandas as pd, json, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from gepf.data import PROC, ZONES
from gepf.models import feats, fit, PARAMS
from gepf.evalutil import mae
QS = [0.025, 0.1, 0.5, 0.9, 0.975]; BANDS = {"80": (0.1, 0.9, .80), "95": (0.025, 0.975, .95)}
df = pd.read_parquet(PROC / "trainval.parquet"); need = ["lag_336h", "lag_168h", "load_mw"]
tr = df[df.split == "train"].dropna(subset=need); va = df[df.split == "val"].dropna(subset=need).copy()
f = feats(True, False)
def pinball(y, q, a): d = y - q; return float(np.mean(np.maximum(a * d, (a - 1) * d)))
def cqr_offset(y, lo, hi, nominal):
    s = np.maximum(lo - y, y - hi); n = len(s); k = min(1.0, np.ceil((n + 1) * nominal) / n); return float(np.quantile(s, k, method="higher"))
Q = {}; mid = va.timestamp_utc.min() + (va.timestamp_utc.max() - va.timestamp_utc.min()) / 2
va["half"] = np.where(va.timestamp_utc <= mid, "A", "B")
for z in ZONES:
    t = tr[tr.zone == z]; v = va[va.zone == z]
    P = np.column_stack([fit(t[f], t.load_mw, objective="quantile", alpha=a).predict(v[f]) for a in QS])
    Q[z] = pd.DataFrame(np.sort(P, axis=1), index=v.index, columns=[f"q{a}" for a in QS])
rows, hours, months = [], [], []
OFF = {}
for z in ZONES:
    v = va[va.zone == z]; q = Q[z]; y = v.load_mw.values
    m2 = None
    for b, (lo_a, hi_a, nom) in BANDS.items():
        lo, hi = q[f"q{lo_a}"].values, q[f"q{hi_a}"].values
        for method in ["Q1_raw", "Q2_cqr"]:
            for ev in ["A", "B"]:
                cal = "B" if ev == "A" else "A"
                e = (v.half == ev).values; c = (v.half == cal).values
                off = cqr_offset(y[c], lo[c], hi[c], nom) if method == "Q2_cqr" else 0.0
                l, h = lo[e] - off, hi[e] + off; cov = float(np.mean((y[e] >= l) & (y[e] <= h)))
                rows.append(dict(zone=z, band=b, method=method, eval_half=ev, coverage=cov, err_pp=(cov - nom) * 100, width=float(np.mean(h - l)), offset=off))
        OFF[f"{z}_{b}"] = cqr_offset(y, lo, hi, nom)   # offset from ALL validation, for later use on test (Phase 6)
        # per hour / month coverage of raw and (full-val) conformal bands
        off = OFF[f"{z}_{b}"]
        for method, o in [("Q1_raw", 0), ("Q2_cqr_inSample", off)]:
            inn = (y >= lo - o) & (y <= hi + o)
            g = pd.DataFrame(dict(inn=inn, hour=v.hour.values, month=v.month.values))
            for h_, s in g.groupby("hour").inn.mean().items(): hours.append(dict(zone=z, band=b, method=method, hour=h_, coverage=s))
            for m_, s in g.groupby("month").inn.mean().items(): months.append(dict(zone=z, band=b, method=method, month=m_, coverage=s))
R = pd.DataFrame(rows); R.to_csv("results/quantiles_coverage.csv", index=False)
pd.DataFrame(hours).to_csv("results/coverage_by_hour.csv", index=False); pd.DataFrame(months).to_csv("results/coverage_by_month.csv", index=False)
json.dump(OFF, open("results/cqr_offsets_val.json", "w"), indent=1)
S = R.groupby(["method", "band"]).agg(coverage=("coverage", "mean"), mean_abs_err_pp=("err_pp", lambda s: s.abs().mean()), width=("width", "mean")).round(3)
print(S); print(R.pivot_table(index=["zone", "band"], columns=["method", "eval_half"], values="coverage").round(3))
print("mean coverage error over everything (pp):", R.groupby("method").err_pp.apply(lambda s: s.abs().mean()).round(2).to_dict())
# median model, pinball
for z in ZONES:
    v = va[va.zone == z]; q = Q[z]; y = v.load_mw.values
    print(z, "median MAE %.1f" % mae(y, q["q0.5"]), "| pinball", {a: round(pinball(y, q[f"q{a}"].values, a), 1) for a in QS})
# plot
fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
for i, b in enumerate(["80", "95"]):
    for method, ls in [("Q1_raw", "o"), ("Q2_cqr", "s")]:
        s = R[(R.band == b) & (R.method == method)].groupby("zone").coverage.mean().reindex(ZONES)
        ax[0].scatter(range(4), s.values, marker=ls, label=f"{b}% {method}", s=60)
ax[0].hlines([.8, .95], -.3, 3.3, colors="gray", linestyles="--"); ax[0].set_xticks(range(4), ZONES); ax[0].set_ylabel("empirical coverage"); ax[0].legend(fontsize=7); ax[0].set_title("Coverage per zone (mean of A/B halves)")
H = pd.DataFrame(hours)
for b, c in [("80", "C0"), ("95", "C1")]:
    for method, ls in [("Q1_raw", "-"), ("Q2_cqr_inSample", "--")]:
        s = H[(H.band == b) & (H.method == method)].groupby("hour").coverage.mean(); ax[1].plot(s.index, s.values, ls, color=c, label=f"{b}% {method}")
ax[1].hlines([.8, .95], 0, 23, colors="gray", linestyles=":"); ax[1].set_title("Coverage by hour of day (mean over zones)"); ax[1].set_xlabel("hour (Berlin)"); ax[1].legend(fontsize=7)
M = pd.DataFrame(months)
for b, c in [("80", "C0"), ("95", "C1")]:
    s = M[(M.band == b) & (M.method == "Q1_raw")].groupby("month").coverage.mean(); ax[2].plot(s.index, s.values, color=c, label=f"{b}% raw")
ax[2].hlines([.8, .95], 1, 12, colors="gray", linestyles=":"); ax[2].set_title("Raw quantile coverage by month"); ax[2].set_xlabel("month"); ax[2].legend(fontsize=7)
fig.tight_layout(); fig.savefig("results/figures/coverage.png", dpi=110)
# example fan chart: one week, Amprion, conformal(all-val) 80/95 bands
z = "Amprion"; v = va[va.zone == z]; q = Q[z]; w = v.timestamp_utc.between("2025-01-13", "2025-01-19 23:00").values
fig, a = plt.subplots(figsize=(11, 4)); x = v.timestamp_utc[w]
o95, o80 = OFF[f"{z}_95"], OFF[f"{z}_80"]
a.fill_between(x, q["q0.025"][w] - o95, q["q0.975"][w] + o95, alpha=.2, label="95% (CQR)"); a.fill_between(x, q["q0.1"][w] - o80, q["q0.9"][w] + o80, alpha=.35, label="80% (CQR)")
a.plot(x, q["q0.5"][w], label="median forecast"); a.plot(x, v.load_mw[w], "k", lw=1, label="actual"); a.legend(); a.set_title(f"{z}: validation week 2025-01-13 (bands calibrated on all validation, so in-sample)")
fig.tight_layout(); fig.savefig("results/figures/fan_example.png", dpi=110)
