"""Apply the H0 choice rule and the show-on-map rule to the validation tables (results/horizon_val_{A,B,C}.csv).
Writes results/horizon_selection.csv and results/horizon_selection.json. Validation only."""
import json
import pandas as pd
A, B, C = (pd.read_csv(f"results/horizon_val_{c}.csv").set_index(["zone", "k"]) for c in "ABC")
rows = []
for (z, k), a in A.iterrows():
    cfg, r = "A", a
    if (z, k) in B.index and B.loc[(z, k)].mae_all <= 0.98 * a.mae_all: cfg, r = "B", B.loc[(z, k)]
    if (z, k) in C.index and C.loc[(z, k)].mae_all <= 0.98 * (r.mae_all if cfg == "B" else a.mae_all) and C.loc[(z, k)].mae_all <= 0.98 * a.mae_all:
        cfg, r = "C", C.loc[(z, k)]
    base = "B_day" if a.B_day_all < a.B_week_all else "B_week"          # best simple baseline (overall validation MAE; same for all configs)
    sub = {s: (r[f"mae_{s}"], a[f"{base}_{s}"]) for s in ("holiday", "hot5", "cold5")}
    ok1 = r.mae_all <= 0.95 * a[f"{base}_all"]; ok2 = all(m <= b for m, b in sub.values())
    rows.append(dict(zone=z, k=k, config=cfg, mae=r.mae_all, best_baseline=base, baseline_mae=a[f"{base}_all"], gain_vs_baseline=1 - r.mae_all / a[f"{base}_all"],
                     B_day=a.B_day_all, B_week=a.B_week_all, B_wk4avg=a.B_wk4avg_all, **{f"mae_{s}": m for s, (m, b) in sub.items()}, **{f"base_{s}": b for s, (m, b) in sub.items()},
                     rule1_5pct=bool(ok1), rule2_subsets=bool(ok2), passes=bool(ok1 and ok2)))
S = pd.DataFrame(rows); S.to_csv("results/horizon_selection.csv", index=False)
out = {"choice": {f"{z}|{k}": c for z, k, c in zip(S.zone, S.k, S.config)}, "passes": {f"{z}|{k}": p for z, k, p in zip(S.zone, S.k, S.passes)},
       "outlook_21_included": bool(S[S.k == 21].passes.all())}
json.dump(out, open("results/horizon_selection.json", "w"), indent=1)
pd.set_option("display.width", 250); print(S.round(3).to_string(index=False)); print(out["outlook_21_included"])
