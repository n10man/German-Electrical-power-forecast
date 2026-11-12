"""Browser checks (headless Chrome): the 'Today' logic with a fake clock, and page / dialog layout at 1440x900, 1920x1080 and 390x844.
Skipped when no Chrome/Chromium is installed. The page is served over a local http server on a free port; nothing leaves the machine."""
import functools, http.server, json, re, shutil, subprocess, sys, threading
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
CHROME = next((p for p in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")] if p and Path(p).exists()), None)
pytestmark = pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium found")

def dom(url, budget=120000):
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--virtual-time-budget={budget}", "--window-size=1500,1100", "--dump-dom", url], capture_output=True, text=True, timeout=300)
    m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout, re.S)
    assert m, r.stderr[-500:]
    import html
    return json.loads(html.unescape(m.group(1)))

@pytest.fixture(scope="module")
def server():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT)); handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"; srv.shutdown()

def test_today_button_logic_with_fake_clock():
    r = dom((ROOT / "tests/js/today_harness.html").as_uri())
    assert r["inside"]["kind"] == "set" and r["inside"]["date"] == "2026-11-15"                       # today inside the snapshot: set the picker to today
    assert r["inside_last_day_late_evening_utc"]["berlin"] == "2026-12-01" and r["inside_last_day_late_evening_utc"]["kind"] == "set"   # Berlin date, not UTC
    assert r["ended"]["berlin"] == "2026-12-02" and r["ended"]["kind"] == "ended" and r["ended"]["date"] == "2026-12-01"      # after the snapshot: disabled + notice
    assert r["ended_later"]["kind"] == "ended"
    assert (r["gap_nearer_to_real"]["kind"], r["gap_nearer_to_real"]["date"]) == ("nearest", "2026-10-24")  # in the gap: nearest available date
    assert (r["gap_nearer_to_forecast"]["kind"], r["gap_nearer_to_forecast"]["date"]) == ("nearest", "2026-11-11")
    assert (r["before_everything"]["kind"], r["before_everything"]["date"]) == ("nearest", "2024-10-26")
    assert r["inside_real_data"]["kind"] == "set"                                                      # a real-data day is itself available
    assert (r["no_snapshot"]["kind"], r["no_snapshot"]["date"]) == ("nearest", "2026-10-24")      # no snapshot loaded: nearest real-data day

def test_layout_at_three_viewports_and_three_languages(server):
    res = dom(f"{server}/tests/js/layout_harness.html")
    assert isinstance(res, list) and len(res) == 9, res
    for r in res:
        tag = f'{r["w"]}x{r["h"]} {r["lang"]}'; c = r["closed"]
        assert c["scrollW"] <= c["clientW"], ("horizontal scroll, page closed", tag, c)
        if r["w"] >= 1440: assert c["scrollH"] <= c["clientH"], ("page does not fit one screen", tag, c)
        assert c["dir"] == ("rtl" if r["lang"] == "ar" else "ltr") and c["lang"] == r["lang"]
        for mode in ("future", "past"):
            p = r[mode]
            assert p["open"] and p["scrollW"] <= p["clientW"] and p["dlgScrollW"] <= p["dlgClientW"], ("horizontal scroll, dialog open", tag, mode, p)
            assert p["dx"] <= 3 and p["dy"] <= 3, ("dialog not centred", tag, mode, p["dx"], p["dy"])
            assert p["width"] <= min(760, 0.961 * c["clientW"]) + 1 and p["heightRatio"] <= 0.921, ("dialog too big", tag, mode, p)
            assert p["activeIsDialog"] and not p["activeIsClose"] and p["dialogOutline"] == "none", ("focus", tag, mode, p)
            assert p["lockClass"] and p["htmlOverflow"] == "hidden", ("page scroll not locked", tag, mode, p)
            assert p["closedByBackdrop"] and p["lockReleased"], ("backdrop click / unlock", tag, mode, p)
            assert p["bands"] == (mode == "future") and p["details"] is False, ("defaults", tag, mode, p)
    en = next(r for r in res if r["lang"] == "en"); assert "hour of day (Berlin time)" in en["future"]["axisX"]

def test_hover_layer_in_real_browser(server):
    import json as _j
    res = dom(f"{server}/tests/js/hover_harness.html")
    assert isinstance(res, list) and len(res) == 3, res
    heads = {"en": "Future forecast snapshot", "de": "Momentaufnahme der Zukunftsprognose", "ar": "لقطة التوقعات المستقبلية"}
    for r in res:
        tag = r["lang"]
        assert r["layerPointerEvents"] == "none" and r["layerAbove"] and r["before"] == 0, (tag, r)               # a separate top layer that ignores the pointer
        assert r["afterEnter"] == 1 and r["copyCount"] == 3 and r["copyD"] and r["copyPointerEvents"] == "none", (tag, r)   # hovering creates a copy of the state's path (outline, fill, white inner edge)
        assert r["fill"] != r["zoneFill"] and r["fill"].startswith("#"), (tag, r)                                   # lighter fill than the zone colour
        assert "scale(1.25" in r["scale"] and r["transition"] == "0.12s", (tag, r)                                   # large state: about 1.25, short transition
        assert float(r["smallScale"].split("scale(")[1][:-1]) >= 1.4, (tag, r)                                       # very small state (Berlin): about 1.45
        assert r["zoneLit"] == "TenneT" and r["afterMove"] == 3, (tag, r)                                            # zone highlight still works; moving inside the state keeps the layer
        assert r["afterLeave"] == 0 and r["zoneClearedOnLeave"], (tag, r)                                            # leaving cleans up
        assert r["noScrollHover"] and r["noScrollPopup"], (tag, r)                                                   # no scrollbars from the effect
        assert r["touchDuring"] == 0 and r["touchPressedZone"] and r["touchAfter"] == 0, (tag, r)                    # touch: pressed zone highlight, but no overlay
        assert r["tapOpensPopup"] and r["afterPopup"] == 0, (tag, r)                                                 # a click still opens the popup and clears the layer
        assert len(r["fit"]) == 16 and all(v["inside"] for v in r["fit"].values()), (tag, {k: v for k, v in r["fit"].items() if not v["inside"]})   # the enlarged copy never leaves the viewBox (all 16 states)
        for sid in ("BE", "HH", "HB", "BY", "SH"): assert sid in r["fit"], sid
        assert float(r["fit"]["BE"]["scale"].split("scale(")[1][:-1]) >= 1.4 and float(r["fit"]["HH"]["scale"].split("scale(")[1][:-1]) >= 1.4, (tag, r["fit"])
        for t in r["tip"]:                                                                                           # tooltip: big bold name, smaller second line, inside the viewport, no scrollbars
            assert t["namePx"] >= 20 and t["nameWeight"] in ("700", "bold") and t["restPx"] < t["namePx"] and t["inside"] and t["noScroll"] and t["pe"] == "none", (tag, t)
            assert t["bg"] == "rgb(17, 17, 17)" and t["fg"] == "rgb(255, 255, 255)" and t["name"] and t["rest"], (tag, t)
        assert not r["bannerToggle"] and r["bannerText"].count("\n") == 0 and "UTC" in r["bannerText"], (tag, r["bannerText"])      # the old banner is gone; the dates are one line in the Notes block
        assert heads[tag] in r["licHeading"] and "UTC" in r["licSnap"] and ("17" in r["licSnap"]), (tag, r["licHeading"], r["licSnap"][-400:])   # the long text now lives in the licences dialog
    assert {r["dir"] for r in res} == {"ltr", "rtl"}

# ---- every state x every language in real WebKit and Chromium (Playwright; skipped when it is not installed) ----
@pytest.fixture(scope="module")
def engines_base():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT / "site"))); threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"; srv.shutdown()

@pytest.mark.parametrize("engine", ["webkit", "chromium"])
@pytest.mark.parametrize("name", ["all_states_all_languages", "runtime_language_switch"])
def test_hover_tooltip_click_keyboard_all_states_all_languages(engines_base, engine, name):
    """3 languages x 16 states: exactly one highlighted and zoomed state (centred on it), visible translated tooltip inside the viewport (name >= 20 px bold, not clipped),
    click opens the popup, no focus rectangle after mouse use, Tab shows the keyboard highlight; also after switching language at runtime (en -> de -> ar -> en)."""
    sync_api = pytest.importorskip("playwright.sync_api", reason="Playwright not installed")
    sys.path.insert(0, str(ROOT / "scripts")); import site_engine_checks as C
    with sync_api.sync_playwright() as pw:
        try: browser = getattr(pw, engine).launch()
        except Exception as e: pytest.skip(f"{engine} cannot be launched here: {str(e)[:80]}")
        try: problems = C.ALL2[name](browser, engines_base)
        finally: browser.close()
    assert not problems, problems[:6]


@pytest.mark.parametrize("engine", ["webkit", "chromium"])
@pytest.mark.parametrize("name", ["notes_block", "rewritten_texts_all_zones_states_languages", "previous_next_day_buttons"])
def test_notes_block_rewritten_texts_and_day_buttons(engines_base, engine, name):
    """One plain Notes block (white, no orange/beige, ranges note + snapshot dates from future_meta.json, old banners gone, 360 px fine); the three rewritten texts for all 4 zones and 16 states
    in en/de/ar with the numbers from the data files; previous/next day across month, year and DST days, limits from the data, mirrored arrows in Arabic, 44 px targets, no overflow at 360 px."""
    sync_api = pytest.importorskip("playwright.sync_api", reason="Playwright not installed")
    sys.path.insert(0, str(ROOT / "scripts")); import site_engine_checks as C
    with sync_api.sync_playwright() as pw:
        try: browser = getattr(pw, engine).launch()
        except Exception as e: pytest.skip(f"{engine} cannot be launched here: {str(e)[:80]}")
        try: problems = C.ALL3[name](browser, engines_base)
        finally: browser.close()
    assert not problems, problems[:6]
