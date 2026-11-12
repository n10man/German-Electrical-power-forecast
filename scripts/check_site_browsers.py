"""Cross-engine check of the map site with Playwright (optional tool, not a project dependency):

    python -m venv /tmp/pw && /tmp/pw/bin/pip install playwright && /tmp/pw/bin/playwright install chromium webkit firefox
    /tmp/pw/bin/python scripts/check_site_browsers.py [--shots docs/screenshots] [--engines chromium,webkit,firefox]

For every engine x size x language it checks: no horizontal scroll (page closed and popup open), touch targets >= 44 px on touch devices, form controls >= 16 px,
body text >= 14 px, chart labels >= 11 px, a single tap/click on a state opens the popup, the popup fits the viewport with its close button reachable,
and that every network request stays on this site. It also measures first-load weight and time. Writes results/site_browser_check.json."""
import argparse, functools, http.server, json, sys, threading, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(Path(__file__).resolve().parent))
SIZES = [("360x740", 360, 740), ("390x844", 390, 844), ("768x1024", 768, 1024), ("1024x768", 1024, 768), ("1440x900", 1440, 900), ("1920x1080", 1920, 1080),
         ("844x390 landscape", 844, 390), ("667x375 landscape", 667, 375), ("390x844 portrait-tall", 390, 844)]
LANGS = ["en", "de", "ar"]

def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k): pass
    h = functools.partial(Quiet, directory=str(ROOT / "site"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h); threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"

PAGE_JS = """() => { const d = document.documentElement; const out = {scrollW: d.scrollWidth, clientW: d.clientWidth, scrollH: d.scrollHeight, clientH: d.clientHeight};
  const small = []; const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden'; };
  for (const e of document.querySelectorAll('button, summary, select, input:not([type=checkbox]), label.switch, .foot a')) { if (!e.closest('dialog:not([open])') && vis(e)) { const r = e.getBoundingClientRect(); if (r.width < 43.5 || r.height < 43.5) small.push((e.id || e.className || e.tagName) + ':' + Math.round(r.width) + 'x' + Math.round(r.height)); } }
  out.smallTargets = small;
  out.smallFont = [...document.querySelectorAll('select, input[type=date]')].filter(vis).filter(e => parseFloat(getComputedStyle(e).fontSize) < 16).map(e => e.id);
  out.bodyFont = parseFloat(getComputedStyle(document.body).fontSize);
  const tiny = []; for (const e of document.querySelectorAll('p, li, td, th, label, summary, button, a, h1, h2')) { if (vis(e) && e.textContent.trim() && parseFloat(getComputedStyle(e).fontSize) < 13.9) tiny.push((e.id || e.className || e.tagName) + ':' + getComputedStyle(e).fontSize); }
  out.smallText = [...new Set(tiny)];
  const ct = [...document.querySelectorAll('#chart text')].map(t => { const s = t.ownerSVGElement, k = s.getBoundingClientRect().width / s.viewBox.baseVal.width; return parseFloat(t.getAttribute('font-size')) * k; }); out.minChartFont = ct.length ? Math.min(...ct) : null;
  return out; }"""
DLG_JS = """() => { const dlg = document.getElementById('popup'), c = dlg.querySelector('.close'), r = dlg.getBoundingClientRect(), cr = c.getBoundingClientRect(); dlg.scrollTop = dlg.scrollHeight; const cr2 = c.getBoundingClientRect();
  return {open: dlg.open, left: r.left, right: r.right, top: r.top, bottom: r.bottom, vw: innerWidth, vh: innerHeight, dlgScrollW: dlg.scrollWidth, dlgClientW: dlg.clientWidth, closeW: cr.width, closeH: cr.height,
          closeVisibleAfterScroll: cr2.top >= r.top - 1 && cr2.bottom <= r.bottom + 1 && cr2.left >= r.left - 1 && cr2.right <= r.right + 1}; }"""

def hover_checks(page, w, h):
    """Real mouse hover and keyboard focus on desktop-type contexts: the overlay copy appears, ignores the pointer, survives movement inside the state, disappears on leave, and never scrolls the page."""
    path = page.locator('#map>path[data-id="BY"]'); path.scroll_into_view_if_needed(); bx = path.bounding_box()
    cx, cy = bx["x"] + bx["width"] / 2, bx["y"] + bx["height"] / 2; q = lambda js: page.evaluate(js); res = {}
    page.mouse.move(2, 2); page.mouse.move(cx, cy); page.wait_for_timeout(250)
    res["overlayOnHover"] = q("document.querySelectorAll('#hoverLayer path').length") == 3 and q("getComputedStyle(document.getElementById('hoverLayer')).pointerEvents") == "none"
    res["hoveredStaysSame"] = q("document.elementFromPoint(%f, %f).dataset.id" % (cx, cy)) == "BY"                       # the layer does not steal the pointer
    page.mouse.move(cx + 6, cy + 6, steps=4); page.wait_for_timeout(100); res["survivesMove"] = q("document.querySelectorAll('#hoverLayer path').length") == 3
    res["noScroll"] = q("document.documentElement.scrollWidth <= document.documentElement.clientWidth && document.documentElement.scrollHeight <= innerHeight + 1")
    page.mouse.move(2, 2); page.wait_for_timeout(100); res["removedOnLeave"] = q("document.getElementById('hoverLayer').children.length") == 0
    page.evaluate("document.activeElement && document.activeElement.blur()"); page.keyboard.press("Tab"); q("document.querySelector('#map>path[data-id=BY]').focus()"); page.wait_for_timeout(250)     # a key press first, so the focus counts as keyboard focus (:focus-visible)
    res["keyboardFocusShowsLayer"] = q("document.activeElement.matches('#map>path') && document.querySelectorAll('#hoverLayer path').length === 3")
    page.evaluate("document.activeElement && document.activeElement.blur()"); page.mouse.move(2, 2)
    return res

def run(engines, shots):
    srv, base = serve(); report = []; weights = {}
    with sync_playwright() as pw:
        for eng in engines:
            browser = getattr(pw, eng).launch()
            for label, w, h in SIZES:
                phone = min(w, h) <= 768 and (w, h) != (1024, 768)
                for lang in LANGS:
                    kw = dict(viewport={"width": w, "height": h}, has_touch=phone and eng != "firefox", is_mobile=phone and eng == "chromium", device_scale_factor=2 if shots else 1, locale={"en": "en-GB", "de": "de-DE", "ar": "ar"}[lang])
                    ctx = browser.new_context(**kw); page = ctx.new_page(); reqs = []; errs = []
                    page.on("request", lambda r: reqs.append(r.url)); page.on("pageerror", lambda e: errs.append(str(e))); page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
                    t0 = time.time(); resp = {}
                    page.on("response", lambda r: resp.__setitem__(r.url, r))
                    page.goto(f"{base}/index.html?lang={lang}", wait_until="networkidle"); page.wait_for_selector("#map path"); load_ms = round((time.time() - t0) * 1000)
                    first = {u: len(r.body() or b"") for u, r in resp.items()}; r0 = {"engine": eng, "size": label, "lang": lang, "load_ms": load_ms, "initial_requests": len(first), "initial_bytes": sum(first.values())}
                    if (eng, label, lang) == (engines[0], SIZES[4][0], "en"): weights = {u.replace(base, ""): n for u, n in first.items()}
                    r0["closed"] = page.evaluate(PAGE_JS)
                    path = page.locator('#map>path[data-id="BY"]')            # one tap / click, no hover first
                    page.evaluate("window.__hv = 0; new MutationObserver(m => { window.__hv += m.reduce((n, x) => n + x.addedNodes.length, 0); }).observe(document.getElementById('hoverLayer'), {childList: true})")
                    if not kw["has_touch"]: r0["hover"] = hover_checks(page, w, h)
                    path.scroll_into_view_if_needed(); box = path.bounding_box()
                    x0, x1, y0, y1 = max(box["x"], 0), min(box["x"] + box["width"], w), max(box["y"], 0), min(box["y"] + box["height"], h)   # the visible part of the state
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                    if kw["has_touch"]: page.touchscreen.tap(cx, cy)
                    else: page.mouse.click(cx, cy)
                    page.wait_for_selector("#popup[open]", timeout=8000); page.wait_for_selector("#chart text"); time.sleep(.3)
                    if kw["has_touch"]: r0["hover"] = {"overlayCreatedByTouch": page.evaluate("window.__hv")}
                    r0["tapOpensPopup"] = True; r0["open"] = page.evaluate(PAGE_JS); r0["dialog"] = page.evaluate(DLG_JS)
                    r0["zoneBytes"] = sum(len(r.body() or b"") for u, r in resp.items() if "/data/" in u and u not in first)
                    if shots and eng == "chromium" and label in ("390x844", "1440x900", "844x390 landscape") and lang in LANGS:
                        page.evaluate("document.getElementById('more').open = false; document.getElementById('popup').scrollTop = 0"); page.screenshot(path=str(Path(shots) / f"s3_{lang}_{label.split()[0]}_popup.jpg"), type="jpeg", quality=82)
                        page.keyboard.press("Escape"); page.wait_for_timeout(200); page.screenshot(path=str(Path(shots) / f"s3_{lang}_{label.split()[0]}_overview.jpg"), type="jpeg", quality=82)
                    r0["offsite_requests"] = [u for u in reqs if not u.startswith(base)]; r0["errors"] = errs
                    report.append(r0); ctx.close()
            browser.close()
    srv.shutdown(); return report, weights

def verdict(r):
    bad = []
    for k in ("closed", "open"):
        if r[k]["scrollW"] > r[k]["clientW"]: bad.append(f"horizontal scroll ({k})")
        if r[k]["smallFont"]: bad.append(f"form font <16px {r[k]['smallFont']}")
        if r[k]["bodyFont"] < 14: bad.append("body font <14px")
        if r[k]["minChartFont"] is not None and r[k]["minChartFont"] < 10.95: bad.append(f"chart font {r[k]['minChartFont']:.1f}px")
    touch = r["size"] not in ("1440x900", "1920x1080", "1024x768")
    if touch and r["open"]["smallTargets"]: bad.append(f"touch targets <44px {r['open']['smallTargets']}")
    if touch and r["closed"]["smallTargets"]: bad.append(f"touch targets <44px (page) {r['closed']['smallTargets']}")
    hv = r.get("hover", {})
    if "overlayCreatedByTouch" in hv and hv["overlayCreatedByTouch"]: bad.append("hover overlay created on a touch device")
    if "overlayOnHover" in hv:
        for k in ("overlayOnHover", "hoveredStaysSame", "survivesMove", "noScroll", "removedOnLeave"):
            if not hv[k]: bad.append(f"hover check failed: {k}")
        if not hv["keyboardFocusShowsLayer"]: bad.append("keyboard focus does not show the layer")
    d = r["dialog"]
    if d["left"] < -1 or d["right"] > d["vw"] + 1 or d["top"] < -1 or d["bottom"] > d["vh"] + 1: bad.append("popup outside viewport")
    if d["dlgScrollW"] > d["dlgClientW"]: bad.append("popup scrolls horizontally")
    if not d["closeVisibleAfterScroll"]: bad.append("close button not reachable after scrolling")
    if r["offsite_requests"]: bad.append(f"off-site requests {r['offsite_requests']}")
    if r["errors"]: bad.append(f"console errors {r['errors'][:2]}")
    return bad

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--engines", default="chromium,webkit,firefox"); ap.add_argument("--shots"); ap.add_argument("--out", default="results/site_browser_check.json"); a = ap.parse_args()
    if a.shots: Path(a.shots).mkdir(parents=True, exist_ok=True)
    rep, weights = run(a.engines.split(","), a.shots); problems = 0
    for r in rep:
        b = verdict(r); r["problems"] = b; problems += bool(b)
        if b: print(r["engine"], r["size"], r["lang"], "->", "; ".join(b))
    import site_engine_checks as EC                                   # regression checks: tooltip on every state/language, no focus rectangle after mouse use, keyboard highlight after Tab
    engine_checks = {}
    with sync_playwright() as pw:
        for eng in a.engines.split(","):
            br = getattr(pw, eng).launch(); srv2, base2 = serve(); engine_checks[eng] = {name: fn(br, base2) for name, fn in {**EC.ALL, **EC.ALL2, **EC.ALL3}.items()}; br.close(); srv2.shutdown()
    for eng, d in engine_checks.items():
        for name, probs in d.items():
            if probs: problems += 1; print(eng, name, "->", probs[:3])
    json.dump({"checked": len(rep), "with_problems": problems, "engine_checks": engine_checks, "first_load_files_1440_en": weights, "runs": rep}, open(ROOT / a.out, "w"), indent=1)
    print(f"{len(rep)} runs, {problems} with problems; first load (1440 en): {sum(weights.values())} bytes in {len(weights)} files")
