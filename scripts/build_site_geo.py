"""Simplify the BKG state boundaries and attach zone assignment -> site/data/states.geojson"""
import sys, json; sys.path.insert(0, "src")
from shapely.geometry import shape, mapping, MultiPolygon
from gepf.zones import STATES
g = json.load(open("data/raw/vg250_lan.geojson")); feats = []; vintage = set()
for f in g["features"]:
    p = f["properties"]; iso, name, zone, others = STATES[p["sn_l"]]; vintage.add(str(p["beginn"])[:10])
    geom = shape(f["geometry"]); parts = sorted(geom.geoms, key=lambda x: -x.area)
    keep = [x for x in parts if x.area >= 0.002] or parts[:1]            # drop tiny islands (< ~20 km2)
    s = MultiPolygon(keep).simplify(0.006, preserve_topology=True)
    feats.append({"type": "Feature", "properties": {"id": iso, "name": name, "zone": zone, "also_served_by": others, "split": bool(others)},
                  "geometry": json.loads(json.dumps(mapping(s), default=list))})
def rnd(c): return [round(x, 3) for x in c] if isinstance(c[0], (int, float)) else [rnd(x) for x in c]
for f in feats: f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
out = {"type": "FeatureCollection", "attribution": "© BKG (2026) dl-de/by-2-0, Datenquellen: https://sg.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_vg_nuts.pdf; geometry simplified", "source_feature_start_dates": sorted(vintage), "features": feats}
json.dump(out, open("site/data/states.geojson", "w"), separators=(",", ":"), ensure_ascii=False)
import os; print(os.path.getsize("site/data/states.geojson"), "bytes", len(feats), "states", sorted(vintage))
