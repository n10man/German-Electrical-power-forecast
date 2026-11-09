"""Schema / consistency tests for the map data in site/data (no model, no sealed file needed)."""
import json, re
from pathlib import Path
import numpy as np, pandas as pd, pytest
from gepf.data import ZONES, ZONE_STATES
from gepf.zones import STATES

SITE = Path(__file__).resolve().parents[1] / "site"; DATA = SITE / "data"
pytestmark = pytest.mark.skipif(not (DATA / "meta.json").exists(), reason="site data not exported")
KEYS = ["h", "t", "s", "a", "f", "l80", "u80", "l95", "u95"]

@pytest.fixture(scope="module")
def meta(): return json.load(open(DATA / "meta.json"))
@pytest.fixture(scope="module")
def zdata(): return {z: json.load(open(DATA / f"{z}.json")) for z in ZONES}

def test_zone_files_schema_and_names(zdata):
    for z, d in zdata.items():
        assert d["zone"] == z and set(d) == {"zone", "unit", "days"}
        for day, v in d["days"].items():
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) and set(v) == set(KEYS)
            n = len(v["h"]); assert 1 <= n <= 25 and all(len(v[k]) == n for k in KEYS)

def test_no_nan_or_inf_and_sane_values(zdata):
    for z, d in zdata.items():
        for day, v in d["days"].items():
            for k in ["a", "f", "l80", "u80", "l95", "u95"]:
                x = np.array(v[k], float); assert np.isfinite(x).all(), (z, day, k)
            assert (np.array(v["a"]) > 1000).all() and (np.array(v["a"]) < 40000).all()

def test_ranges_are_nested_and_contain_forecast_mostly(zdata):
    tot = inside = 0
    for d in zdata.values():
        for v in d["days"].values():
            l95, l80, u80, u95, f = (np.array(v[k]) for k in ("l95", "l80", "u80", "u95", "f"))
            assert (l95 <= l80).all() and (l80 <= u80).all() and (u80 <= u95).all()
            tot += len(f); inside += int(((f >= l95) & (f <= u95)).sum())
    assert inside / tot > 0.99      # forecast is the mean model, ranges come from quantile models

def test_timestamps_hours_and_dst(zdata):
    for z, d in zdata.items():
        for day, v in d["days"].items():
            t = pd.to_datetime(v["t"], utc=True); assert t.is_monotonic_increasing and t.is_unique
            loc = t.tz_convert("Europe/Berlin"); assert (loc.strftime("%Y-%m-%d") == day).all()
            assert list(loc.hour) == v["h"]
    d = zdata["Amprion"]["days"]; assert len(d["2025-10-26"]["h"]) == 25 and len(d["2026-03-29"]["h"]) == 23

def test_period_flags_match_test_start(zdata, meta):
    t0 = pd.Timestamp(meta["test_start"])
    for d in zdata.values():
        for v in d["days"].values():
            assert v["s"] == [int(pd.Timestamp(x) >= t0) for x in v["t"]]

def test_date_range_and_hour_counts(zdata, meta):
    for z, d in zdata.items():
        full = [k for k in d["days"] if meta["first_full_local_day"] <= k <= meta["last_full_local_day"]]
        assert len(full) == (pd.Timestamp(meta["last_full_local_day"]) - pd.Timestamp(meta["first_full_local_day"])).days + 1
        n = sum(len(v["h"]) for v in d["days"].values()); assert n == meta["hours"][z]["hours_exported"]
        assert meta["hours"][z]["hours_in_period"] == 17520
        assert meta["hours"][z]["hours_left_out"] == 17520 - n
    assert [meta["hours"][z]["hours_left_out"] for z in ZONES] == [6, 0, 0, 0]   # 50Hertz: missing source data (documented in README)

def test_coverage_numbers_come_from_final_results(meta):
    c = pd.read_csv(Path(__file__).resolve().parents[1] / "results/final_test_coverage.csv", dtype={"band": str}); c = c[c.method == "cqr"]
    for b in ("80", "95"): assert meta["test_coverage_cqr_mean"][b] == round(c[c.band == b].coverage.mean() * 100, 1)
    assert (meta["test_coverage_cqr_mean"]["80"], meta["test_coverage_cqr_mean"]["95"]) == (72.5, 90.8)

def test_states_geojson_and_zone_assignment():
    g = json.load(open(DATA / "states.geojson")); f = g["features"]
    assert len(f) == 16 and len({x["properties"]["id"] for x in f}) == 16
    assert {x["properties"]["zone"] for x in f} == set(ZONES)
    by_zone = {z: sorted(x["properties"]["id"] for x in f if x["properties"]["zone"] == z) for z in ZONES}
    assert by_zone == {z: sorted(s) for z, s in ZONE_STATES.items()}          # same mapping as the holiday feature
    for x in f:
        p = x["properties"]; assert p["split"] == bool(p["also_served_by"]) and p["zone"] not in p["also_served_by"]
        assert x["geometry"]["type"] in ("Polygon", "MultiPolygon") and "dl-de/by-2-0" in g["attribution"]
    assert {s[0] for s in STATES.values()} == {x["properties"]["id"] for x in f}

def test_site_files_reference_existing_assets():
    html = (SITE / "index.html").read_text(); js = (SITE / "app.js").read_text()
    for ref in re.findall(r'(?:src|href)="([^"#]+\.(?:js|css))"', html): assert (SITE / ref).exists(), ref
    assert not re.search(r"https?://[^\"' ]+\.(?:js|png|json)\b", html + js)          # no external scripts/tiles
    assert "api_key" not in js.lower() and "apikey" not in js.lower()
    for needle in ("Bundesnetzagentur | SMARD.de", "Weather data by Open-Meteo.com", "dl-de/by-2-0", "not the state", "Unseen test period", "Validation period (used for tuning and calibration)", "Backtest using observed weather, not a live forecast."):
        assert needle in js or needle in html, needle

def test_site_is_deployable_under_a_subpath_and_has_a_pages_workflow():
    # GitHub Pages serves a project site under /<repo>/, so every URL must be relative (no leading slash, no origin).
    html = (SITE / "index.html").read_text(); js = (SITE / "app.js").read_text(); css = (SITE / "style.css").read_text()
    assert not re.search(r'(?:src|href)="/(?!/)', html), "root-absolute URL in index.html"
    assert not re.search(r"fetch\(\s*[`'\"]/", js) and not re.search(r"getJSON\(\s*[`'\"]/", js), "root-absolute fetch in app.js"
    assert not re.search(r"url\(\s*['\"]?/", css)
    wf = (SITE.parent / ".github/workflows/pages.yml").read_text()
    assert "actions/upload-pages-artifact" in wf and "actions/deploy-pages" in wf and re.search(r"path:\s*site\s*$", wf, re.M)
    assert "git push" not in wf
    for needed in ("index.html", "app.js", "style.css", "data/meta.json", "data/states.geojson"): assert (SITE / needed).exists(), needed
