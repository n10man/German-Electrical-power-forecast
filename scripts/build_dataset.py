"""Clean + features + time split. Writes data/processed/trainval.parquet and data/processed/sealed_test.parquet (never read before Phase 6)."""
import json, sys
sys.path.insert(0, "src")
import pandas as pd
from gepf.data import ZONES, PROC, build_zone, split_bounds, split_name

PROC.mkdir(parents=True, exist_ok=True)
frames, reps = [], []
for z in ZONES:
    X, rep = build_zone(z); frames.append(X); reps.append(rep)
df = pd.concat(frames)
# common end: last hour where every zone has a published value
last = min(X["load_mw"].last_valid_index() for X in frames)
end = last.floor("D") + pd.Timedelta(days=0)   # whole days only
df = df[(df.index >= "2015-01-01") & (df.index < end)]
b = split_bounds(end)
df["split"] = split_name(df.index, b)
df = df.reset_index(names="timestamp_utc")
df[df.split != "test"].to_parquet(PROC / "trainval.parquet")
df[df.split == "test"].to_parquet(PROC / "sealed_test.parquet")
info = dict(end=str(end), val_start=str(b["val_start"]), test_start=str(b["test_start"]),
            zone_reports=reps, rows=df.groupby(["zone", "split"]).size().unstack().to_dict())
json.dump(info, open(PROC / "build_info.json", "w"), indent=1, default=str)
print(json.dumps(info, indent=1, default=str))
