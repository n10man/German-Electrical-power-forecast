"""Regression checks run in real WebKit and Chromium (Playwright; optional tool, see scripts/check_site_browsers.py): tooltip on every state in every language,
no browser focus rectangle after a mouse click and closing the popup three ways, and the keyboard highlight after Tab. Each function returns a list of problems (empty = fine)."""
LANGS = ["en", "de", "ar"]
INSIDE_JS = """(sid) => { const el = document.querySelector('#map>path[data-id=' + sid + ']'), r = el.getBoundingClientRect();
  for (let i = 0; i < 600; i++) { const x = r.left + ((i * 37) % 100) / 100 * r.width, y = r.top + ((i * 53) % 100) / 100 * r.height; if (document.elementFromPoint(x, y) === el) return [x, y]; } return null; }"""
TIP_JS = """() => { const t = document.getElementById('tip'), r = t.getBoundingClientRect(), c = getComputedStyle(t), n = t.querySelector('.tipname'), d = document.documentElement;
  return {hidden: t.hidden, w: r.width, h: r.height, inside: r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight, vis: c.visibility, op: c.opacity, disp: c.display,
          name: n ? n.textContent : '', px: n ? parseFloat(getComputedStyle(n).fontSize) : 0, noScroll: d.scrollWidth <= d.clientWidth && d.scrollHeight <= innerHeight + 1}; }"""
OUTLINES_JS = """() => [...document.querySelectorAll('*')].filter(e => { const c = getComputedStyle(e); return c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) > 0 && e.getClientRects().length > 0; }).map(e => e.tagName + '#' + (e.id || e.dataset.id || e.className)).slice(0, 6)"""
STATE_NAMES = {"en": None}

def tooltip_problems(browser, base):
    bad = []
    for lang in LANGS:
        p = browser.new_page(viewport={"width": 1440, "height": 900}); p.goto(f"{base}/index.html?lang={lang}"); p.wait_for_selector("#map>path")
        for sid in p.evaluate("[...document.querySelectorAll('#map>path')].map(x => x.dataset.id)"):
            pt = p.evaluate(INSIDE_JS, sid)
            if not pt: bad.append(f"{lang} {sid}: no point inside the state"); continue
            p.mouse.move(2, 2); p.mouse.move(pt[0], pt[1], steps=4); p.wait_for_timeout(100); t = p.evaluate(TIP_JS)
            if t["hidden"] or t["w"] < 10 or t["h"] < 10 or t["vis"] != "visible" or t["op"] != "1" or t["disp"] == "none": bad.append(f"{lang} {sid}: tooltip not visible {t}")
            elif not t["inside"]: bad.append(f"{lang} {sid}: tooltip outside the viewport {t}")
            elif not t["name"] or t["px"] < 20: bad.append(f"{lang} {sid}: tooltip name missing or smaller than 20px {t}")
            elif not t["noScroll"]: bad.append(f"{lang} {sid}: tooltip caused a scrollbar")
            p.mouse.move(2, 2); p.wait_for_timeout(60)
            if not p.evaluate("document.getElementById('tip').hidden"): bad.append(f"{lang} {sid}: tooltip stays after the pointer left")
        p.close()
    return bad

def focus_after_click_problems(browser, base):
    bad = []
    for lang in LANGS:
        for how in ("x", "escape", "backdrop"):
            p = browser.new_page(viewport={"width": 1440, "height": 900}); p.goto(f"{base}/index.html?lang={lang}"); p.wait_for_selector("#map>path")
            pt = p.evaluate(INSIDE_JS, "SH"); p.mouse.move(pt[0], pt[1], steps=3); p.mouse.click(pt[0], pt[1]); p.wait_for_selector("#popup[open]"); p.wait_for_timeout(300)
            if how == "x": p.click("#popup .close")
            elif how == "escape": p.mouse.move(4, 4); p.keyboard.press("Escape")      # pointer away from the state, so any highlight left would be a focus highlight
            else: p.mouse.click(4, 4)
            p.wait_for_timeout(300); o = p.evaluate(OUTLINES_JS); layer = p.evaluate("document.getElementById('hoverLayer').children.length"); mode = p.evaluate("document.documentElement.dataset.input")
            if o: bad.append(f"{lang} close by {how}: visible outline on {o}")
            if mode != "pointer": bad.append(f"{lang} close by {how}: input mode is {mode}")
            if layer: bad.append(f"{lang} close by {how}: a highlight is shown although the mouse was used last ({layer})")
            pt2 = p.evaluate(INSIDE_JS, "NI"); p.mouse.move(pt2[0], pt2[1], steps=5); p.wait_for_timeout(150)
            o = p.evaluate(OUTLINES_JS)
            if o: bad.append(f"{lang} close by {how}, then hovering: visible outline on {o}")
            if p.evaluate("document.getElementById('tip').hidden"): bad.append(f"{lang} close by {how}, then hovering: no tooltip")
            p.close()
    return bad

def keyboard_problems(browser, base):
    bad = []
    for lang in LANGS:
        p = browser.new_page(viewport={"width": 1440, "height": 900}); p.goto(f"{base}/index.html?lang={lang}"); p.wait_for_selector("#map>path"); p.mouse.move(2, 2)
        hit = False
        for _ in range(12):
            p.keyboard.press("Tab")
            if p.evaluate("document.activeElement.matches('#map>path')"): hit = True; break
        if not hit: bad.append(f"{lang}: Tab never reached a state"); p.close(); continue
        p.wait_for_timeout(250)
        info = p.evaluate("({mode: document.documentElement.dataset.input, layer: document.getElementById('hoverLayer').querySelectorAll('path').length, lit: document.querySelectorAll('#map>path.hl').length, pe: getComputedStyle(document.getElementById('hoverLayer')).pointerEvents})")
        if info["mode"] != "keyboard" or info["layer"] != 3 or not info["lit"] or info["pe"] != "none": bad.append(f"{lang}: keyboard focus does not show the highlight {info}")
        if p.evaluate(OUTLINES_JS): bad.append(f"{lang}: rectangular outline on keyboard focus {p.evaluate(OUTLINES_JS)}")
        p.mouse.move(700, 450); p.mouse.move(705, 455); p.wait_for_timeout(150)                       # pointer use switches the mode back and removes the highlight of the still-focused state
        if p.evaluate("document.documentElement.dataset.input") != "pointer": bad.append(f"{lang}: mode did not switch back to pointer")
        p.close()
    return bad

ALL = {"tooltip_every_state_every_language": tooltip_problems, "no_focus_rectangle_after_mouse_click_and_close": focus_after_click_problems, "keyboard_highlight_after_tab": keyboard_problems}

# ---------------- every state x every language (and after switching language at runtime) ----------------
import json as _json
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
NAMES = {l: _json.load(open(_ROOT / f"site/i18n/{l}.json")) for l in LANGS}
STATE_JS = """() => { const t = document.getElementById('tip'), r = t.getBoundingClientRect(), c = getComputedStyle(t), n = t.querySelector('.tipname'), L = document.getElementById('hoverLayer'), hv = L.querySelectorAll('.hv'), d = document.documentElement;
  const zones = [...new Set([...document.querySelectorAll('#map>path.hl')].map(x => x.dataset.zone))];
  return {tipVisible: !t.hidden && r.width > 10 && r.height > 10 && c.visibility === 'visible' && c.opacity === '1' && c.display !== 'none', tipInside: r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight,
          name: n ? n.textContent : '', namePx: n ? parseFloat(getComputedStyle(n).fontSize) : 0, nameWeight: n ? getComputedStyle(n).fontWeight : '', nameClipped: n ? n.scrollWidth > n.clientWidth + 1 : true,
          overlays: hv.length, layerPaths: L.querySelectorAll('path').length, zones: zones.length, noScroll: d.scrollWidth <= d.clientWidth && d.scrollHeight <= innerHeight + 1, rtl: d.dir}; }"""
ALIGN_JS = """(sid) => { const el = document.querySelector('#map>path[data-id=' + sid + ']'), hv = document.querySelector('#hoverLayer .hv'); if (!hv) return false; const a = el.getBoundingClientRect(), b = hv.getBoundingClientRect(), ctm = document.getElementById('map').getScreenCTM();
  const m = /translate\\(([-\\d.]+)px(?:, ([-\\d.]+)px)?\\) scale\\(([\\d.]+)\\)/.exec(hv.style.transform); if (!m) return false; const dx = +m[1] * ctm.a, dy = +(m[2] || 0) * ctm.d, s = +m[3];
  return Math.abs(a.left + a.width / 2 + dx - (b.left + b.width / 2)) < 1.5 && Math.abs(a.top + a.height / 2 + dy - (b.top + b.height / 2)) < 1.5 && Math.abs(b.width / a.width - s) < 0.03; }"""

def _one_state(p, lang, sid, tag):
    bad = []; exp = NAMES[lang]["state_" + sid]
    pt = p.evaluate(INSIDE_JS, sid)
    if not pt: return [f"{tag} {sid}: no point inside the state"]
    p.mouse.move(2, 2); p.mouse.move(pt[0], pt[1], steps=4); p.wait_for_timeout(260); h = p.evaluate(STATE_JS)
    if not h["tipVisible"]: bad.append(f"{tag} {sid}: tooltip not visible")
    else:
        if h["name"] != exp: bad.append(f"{tag} {sid}: tooltip name {h['name']!r} != {exp!r}")
        if not h["tipInside"]: bad.append(f"{tag} {sid}: tooltip outside the viewport")
        if h["namePx"] < 20 or h["nameWeight"] not in ("700", "bold"): bad.append(f"{tag} {sid}: name {h['namePx']}px weight {h['nameWeight']}")
        if h["nameClipped"]: bad.append(f"{tag} {sid}: name clipped")
    if h["overlays"] != 1 or h["layerPaths"] != 3: bad.append(f"{tag} {sid}: expected exactly one highlighted/zoomed state, got {h['overlays']}")
    if h["zones"] != 1: bad.append(f"{tag} {sid}: {h['zones']} zones lit")
    if not h["noScroll"]: bad.append(f"{tag} {sid}: scrollbars appeared")
    if not p.evaluate(ALIGN_JS, sid): bad.append(f"{tag} {sid}: zoomed copy is not centred on the state")
    p.mouse.click(pt[0], pt[1])
    try: p.wait_for_selector("#popup[open]", timeout=4000)
    except Exception: bad.append(f"{tag} {sid}: popup did not open"); return bad
    if p.inner_text("#pTitle") != exp: bad.append(f"{tag} {sid}: popup title {p.inner_text('#pTitle')!r}")
    p.mouse.move(4, 4); p.click("#popup .close"); p.wait_for_timeout(150); p.mouse.move(2, 2); p.wait_for_timeout(100)
    if p.evaluate(OUTLINES_JS): bad.append(f"{tag} {sid}: focus rectangle after mouse use {p.evaluate(OUTLINES_JS)}")
    if p.evaluate("document.getElementById('hoverLayer').children.length"): bad.append(f"{tag} {sid}: highlight left after the pointer was away")
    return bad

def _keyboard(p, lang, tag):
    bad = []; seen = set(); p.mouse.move(2, 2)
    for _ in range(40):
        p.keyboard.press("Tab")
        k = p.evaluate("(() => { const a = document.activeElement; return a.matches('#map>path') ? {id: a.dataset.id, mode: document.documentElement.dataset.input, layer: document.getElementById('hoverLayer').querySelectorAll('.hv').length, tip: !document.getElementById('tip').hidden, name: (document.querySelector('#tip .tipname') || {}).textContent} : null; })()")
        if k:
            if k["id"] in seen: break
            seen.add(k["id"]); p.wait_for_timeout(60)
            if k["mode"] != "keyboard" or k["layer"] != 1 or not k["tip"] or k["name"] != NAMES[lang]["state_" + k["id"]]: bad.append(f"{tag} Tab on {k['id']}: {k}")
            if p.evaluate(OUTLINES_JS): bad.append(f"{tag} Tab on {k['id']}: rectangular outline")
    if len(seen) != 16: bad.append(f"{tag}: Tab reached {len(seen)} of 16 states")
    return bad

def all_states_problems(browser, base):
    bad = []
    for lang in LANGS:
        p = browser.new_page(viewport={"width": 1440, "height": 900}); p.goto(f"{base}/index.html?lang={lang}"); p.wait_for_selector("#map>path")
        for sid in p.evaluate("[...document.querySelectorAll('#map>path')].map(x => x.dataset.id)"): bad += _one_state(p, lang, sid, f"[{lang}]")
        bad += _keyboard(p, lang, f"[{lang}]"); p.close()
    return bad

def runtime_switch_problems(browser, base):
    """en -> de -> ar -> en without reloading: hover, tooltip, click and keyboard keep working in every language."""
    bad = []; p = browser.new_page(viewport={"width": 1440, "height": 900}); p.goto(f"{base}/index.html?lang=en"); p.wait_for_selector("#map>path")
    for lang in ["en", "de", "ar", "en"]:
        p.click(f"#langs button[data-lang={lang}]"); p.wait_for_timeout(300)
        if p.evaluate("document.documentElement.lang") != lang: bad.append(f"switch to {lang} failed")
        for sid in ("BY", "BE", "HB", "MV", "SH", "NW"): bad += _one_state(p, lang, sid, f"[switch->{lang}]")
        bad += _keyboard(p, lang, f"[switch->{lang}]")
    p.close(); return bad

ALL2 = {"all_states_all_languages": all_states_problems, "runtime_language_switch": runtime_switch_problems}

# ---------------- Notes block, the three rewritten texts, previous / next day buttons ----------------
from pathlib import Path as _Path
_SITE = _Path(__file__).resolve().parents[1] / "site"
_FM = _json.load(open(_SITE / "data/future_meta.json")); _META = _json.load(open(_SITE / "data/meta.json"))
_I18N = {l: _json.load(open(_SITE / f"i18n/{l}.json")) for l in LANGS}
_ZONE_OF = {f["properties"]["id"]: f["properties"]["zone"] for f in _json.load(open(_SITE / "data/states.geojson"))["features"]}
OLD_TEXTS = ["Please note", "Not production-grade", "Zone colours show the dominant", "narrower than their labels"]   # removed banner / notice sentences (English; German and Arabic are checked through the i18n keys)

def _open(browser, base, lang, w=1440, h=900, state="BY", date="2026-11-20", extra=""):
    p = browser.new_page(viewport={"width": w, "height": h}); p.goto("about:blank"); p.goto(f"{base}/index.html?lang={lang}#state={state}&date={date}&hour=day{extra}")
    p.wait_for_selector("#popup[open]"); p.wait_for_selector("#chart *", state="attached"); return p

def notes_problems(browser, base):
    bad = []
    for lang in LANGS:
        p = browser.new_page(viewport={"width": 1440, "height": 900}); p.goto(f"{base}/index.html?lang={lang}"); p.wait_for_selector("#map>path"); p.wait_for_selector("#notesSnapshot:not([hidden])")
        r = p.evaluate("""() => { const n = document.getElementById('notes'), c = getComputedStyle(n), m = document.getElementById('map').getBoundingClientRect(), b = n.getBoundingClientRect(), d = document.documentElement;
          const anc = []; for (let e = n; e; e = e.parentElement) anc.push(getComputedStyle(e).backgroundColor);
          return {count: document.querySelectorAll('#notes, .notes').length, h: n.querySelector('h2').textContent, bg: c.backgroundColor, border: c.borderTopWidth, color: c.color, items: [...n.querySelectorAll('li')].map(x => x.textContent), snap: document.getElementById('notesSnapshot').textContent,
            link: !!document.querySelector('#notesRanges button#notesDetails'), old: ['snapshot', 'disclaimer', 'how_zones'].filter(i => document.getElementById(i)).concat([...document.querySelectorAll('.disclaimer, .snapshot, .howto .note')].map(x => x.className)),
            side: b.left >= m.right - 1 || b.right <= m.left + 1, inAside: !!n.closest('aside.howto'), overflow: d.scrollWidth > d.clientWidth, body: document.body.innerText}; }""")
        T = _I18N[lang]
        if r["count"] != 1: bad.append(f"{lang}: {r['count']} notes blocks")
        if r["h"] != T["notes_title"]: bad.append(f"{lang}: heading {r['h']}")
        if r["bg"] != "rgb(255, 255, 255)" or r["border"] != "0px": bad.append(f"{lang}: notes background {r['bg']} border {r['border']} (must be white, no border)")
        if len(r["items"]) != 6 or not r["link"]: bad.append(f"{lang}: items {len(r['items'])}, ranges link {r['link']}")
        if T["notes_details"] not in r["items"][1]: bad.append(f"{lang}: ranges note lacks its see-details link text")
        for k in ("notes_1", "notes_3", "notes_4", "notes_5"):
            if T[k] not in r["items"]: bad.append(f"{lang}: note {k} missing")
        g, e = _FM["generated_utc"], _FM["covers_last_utc"]
        for need in (g[11:16], e[11:16], "UTC", g[:4]):
            if need not in r["snap"]: bad.append(f"{lang}: snapshot line lacks {need}: {r['snap']}")
        if r["old"]: bad.append(f"{lang}: old banners still present {r['old']}")
        if not r["inAside"] or not r["side"]: bad.append(f"{lang}: notes not in the right-hand panel beside the map")
        if r["overflow"]: bad.append(f"{lang}: horizontal overflow")
        if lang == "en":
            for o in OLD_TEXTS[:3]:
                if o in r["body"]: bad.append(f"old text still on the page: {o}")
        if "privacy" not in "privacy" or T["privacy_line"] not in p.evaluate("document.getElementById('notes').textContent"): bad.append(f"{lang}: privacy text missing from Notes")
        p.click("#notesDetails"); p.wait_for_selector("#licDialog[open]")
        if "licRanges" != p.evaluate("document.getElementById('licRanges') && document.getElementById('licRanges').id"): bad.append(f"{lang}: see-details target missing")
        p.close()
        p = browser.new_page(viewport={"width": 360, "height": 740}); p.goto(f"{base}/index.html?lang={lang}"); p.wait_for_selector("#notesSnapshot:not([hidden])")
        r = p.evaluate("() => { const n = document.getElementById('notes').getBoundingClientRect(), m = document.getElementById('map').getBoundingClientRect(), d = document.documentElement; return {below: n.top >= m.bottom - 1, right: n.right <= innerWidth + 0.5, ov: d.scrollWidth > d.clientWidth}; }")
        if not r["below"] or not r["right"] or r["ov"]: bad.append(f"{lang} 360px: notes below map {r['below']}, inside width {r['right']}, overflow {r['ov']}")
        p.close()
    return bad

def _fc_paragraphs(p):
    return p.evaluate("[...document.querySelectorAll('#fcNote p')].map(x => x.textContent)")

def rewritten_texts_problems(browser, base):
    bad = []; im = _FM["interval_method"]; seen = set()
    for lang in LANGS:
        p = _open(browser, base, lang, state="BY", date="2026-11-20", extra="&more=1")
        for sid, zone in _ZONE_OF.items():
            p.evaluate("document.getElementById('popup').open && document.getElementById('popup').close()")
            p.evaluate("sid => document.querySelector('#map>path[data-id=' + sid + ']').dispatchEvent(new MouseEvent('click', {bubbles: true}))", sid); p.wait_for_selector("#popup[open]")
            p.evaluate("() => { const d = document.getElementById('date'); d.value = '2026-11-20'; d.dispatchEvent(new Event('change')); }"); p.wait_for_selector("#fcNote:not([hidden]) p"); seen.add(zone)
            ps = _fc_paragraphs(p); txt = " ".join(ps); a1, aL = _FM["accuracy"][f"{zone}|1"], _FM["accuracy"][f"{zone}|21"]
            exp = p.evaluate("""(q) => [t('acc_intro', {zone: q.zone, a: MW(q.a), b: MW(q.b), c: MW(q.c), d: MW(q.d), L: N(21), o: N(17)}),
              t('intervals_future', {weeks: N(q.w), days: N(q.n), v80: PCT(q.v80, 1), v95: PCT(q.v95, 1)}),
              t('acc_weather', {v0: fmtDate('2024-10-25'), v1: fmtDate('2025-10-24')})]""", {"zone": zone, "a": a1["test_mae"], "b": aL["test_mae"], "c": a1["test_baseline_mae"], "d": aL["test_baseline_mae"], "w": im["window_weeks"], "n": im["calibration_days"], "v80": im["validation_cov80"], "v95": im["validation_cov95"]})
            for e in exp:
                if e not in ps: bad.append(f"{lang} {sid}/{zone}: text not shown as rendered from its template: {e[:70]}")
            if "{" in txt or "}" in txt or "undefined" in txt or "NaN" in txt: bad.append(f"{lang} {sid}: unresolved placeholder in {txt[:120]}")
            if lang == "en":
                n = lambda x: f"{x:,}"
                lit = [f"Accuracy gets worse the further ahead I look. For {zone}, the average error on the test year was {n(a1['test_mae'])} MWh/h for the 1-day model and {n(aL['test_mae'])} MWh/h for the 21-day model. Copying last week gives {n(a1['test_baseline_mae'])} MWh/h and {n(aL['test_baseline_mae'])} MWh/h. Days 17 to 21 are a low-confidence outlook.",
                       "Ranges for future days use a newer method. I reset them using the most recent forecast errors. The window should be 8 weeks, but only 16 days of newer data were available, so it is shorter. On the tuning year, this method covered 80.0% and 94.7% of real values (for the 80% and 95% ranges). I have not tested it on new data yet. I will check it with the saved forecast described in the README. Past days still show the older ranges, so past and future ranges cannot be compared.",
                       "I only had old weather forecasts for up to 7 days ahead. So only days 1 to 7 can use a weather forecast, and only where it helped on the tuning year (see the Inputs column; in most cases it did not). Days 8 to 21 use only the calendar and recent electricity use. The tuning year is 25 Oct 2024 to 24 Oct 2025. I used the test year once for the 24-hour model and a second time for these models. Weather forecasts for days 1 to 7 come from Open-Meteo. The models learned from older saved forecasts of the same kind, which may differ a little from today's forecasts."]
                for s in lit:
                    if not any(s in x for x in ps): bad.append(f"en {sid}/{zone}: wording differs from the requested text: {s[:70]}")
        p.close()
    if len(seen) != 4: bad.append(f"zones covered: {seen}")
    return bad

def _step(p, start, delta):
    p.evaluate("(v) => { const d = document.getElementById('date'); d.value = v; d.dispatchEvent(new Event('change')); }", start)
    p.click("#nextDay" if delta > 0 else "#prevDay"); return p.evaluate("document.getElementById('date').value")

def day_buttons_problems(browser, base):
    bad = []
    cases = [("2025-01-31", 1, "2025-02-01"), ("2025-03-01", -1, "2025-02-28"), ("2024-12-31", 1, "2025-01-01"), ("2026-01-01", -1, "2025-12-31"), ("2026-02-28", 1, "2026-03-01"), ("2025-03-29", 1, "2025-03-30"), ("2025-03-30", 1, "2025-03-31"), ("2025-03-31", -1, "2025-03-30"),
             ("2025-10-25", 1, "2025-10-26"), ("2025-10-26", 1, "2025-10-27"), ("2025-10-27", -1, "2025-10-26"), ("2026-03-28", 1, "2026-03-29"), ("2026-03-29", 1, "2026-03-30"), ("2026-03-30", -1, "2026-03-29"), ("2026-11-30", 1, "2026-12-01")]
    for lang in LANGS:
        T = _I18N[lang]; p = _open(browser, base, lang, date="2025-06-10")
        lim = p.evaluate("() => ({min: document.getElementById('date').min, max: document.getElementById('date').max})")
        if lim != {"min": _META["first_full_local_day"], "max": _FM["covers_last_local_date"]}: bad.append(f"{lang}: limits {lim}")
        if lim["min"] != "2024-10-26" or lim["max"] != "2026-12-01": bad.append(f"{lang}: unexpected limits {lim}")
        for start, d, want in cases:
            got = _step(p, start, d)
            if got != want: bad.append(f"{lang}: {start} {'next' if d > 0 else 'prev'} -> {got}, expected {want}")
        # hour (or Full day) is kept; on the 23-hour day the same clock hour moves to a different list position
        p.evaluate("() => { const d = document.getElementById('date'); d.value = '2025-03-29'; d.dispatchEvent(new Event('change')); const s = document.getElementById('hour'); s.value = '5'; s.dispatchEvent(new Event('change')); }")
        p.click("#nextDay"); r = p.evaluate("() => ({h: cur.day.h[+document.getElementById('hour').value], n: document.getElementById('hour').options.length, d: document.getElementById('date').value})")
        if r["h"] != 5 or r["n"] != 24 or r["d"] != "2025-03-30": bad.append(f"{lang}: hour not kept across the 23-hour day {r}")
        p.click("#nextDay"); r = p.evaluate("() => ({h: cur.day.h[+document.getElementById('hour').value], n: document.getElementById('hour').options.length})")
        if r["h"] != 5 or r["n"] != 25: bad.append(f"{lang}: hour not kept after the 23-hour day {r}")
        p.evaluate("() => { const d = document.getElementById('date'); d.value = '2025-10-26'; d.dispatchEvent(new Event('change')); }"); n25 = p.evaluate("document.getElementById('hour').options.length")
        if n25 != 26: bad.append(f"{lang}: 2025-10-26 should list 25 hours, has {n25 - 1}")
        p.click("#nextDay")
        if p.evaluate("document.getElementById('hour').value") != "day": bad.append(f"{lang}: Full day not kept")
        # update of badge, headline and chart
        before = p.evaluate("() => [document.getElementById('badge').textContent, document.getElementById('headline').textContent, document.getElementById('chart').innerHTML.length]")
        _step(p, "2026-10-24", 1); mid = p.evaluate("document.getElementById('badge').textContent"); p.click("#nextDay"); gap = p.evaluate("document.getElementById('badge').textContent")
        _step(p, "2026-11-10", 1); fut = p.evaluate("() => [document.getElementById('badge').textContent, document.getElementById('headline').textContent]")
        if mid != T["badge_past"] or gap != T["badge_none"] or fut[0] != T["badge_future"] or not fut[1].startswith(T["head_future_day"][:10]): bad.append(f"{lang}: badge/headline do not follow the date: {mid!r} {gap!r} {fut!r}")
        # limits
        for v, which, dis in (("2024-10-26", "prevDay", True), ("2024-10-27", "prevDay", False), ("2026-12-01", "nextDay", True), ("2026-11-30", "nextDay", False)):
            p.evaluate("(v) => { const d = document.getElementById('date'); d.value = v; d.dispatchEvent(new Event('change')); }", v)
            if p.evaluate(f"document.getElementById('{which}').disabled") != dis: bad.append(f"{lang}: {which} disabled should be {dis} at {v}")
        p.evaluate("() => { const d = document.getElementById('date'); d.value = '2024-10-26'; d.dispatchEvent(new Event('change')); }"); p.click("#prevDay", force=True)
        if p.evaluate("document.getElementById('date').value") != "2024-10-26": bad.append(f"{lang}: moved past the earliest date")
        # accessible names, sizes, mirrored arrows, order
        r = p.evaluate("""() => { const pr = document.getElementById('prevDay'), nx = document.getElementById('nextDay'), g = e => e.getBoundingClientRect();
          return {pa: pr.getAttribute('aria-label'), na: nx.getAttribute('aria-label'), pw: g(pr).width, ph: g(pr).height, nw: g(nx).width, nh: g(nx).height, px: g(pr).left, nx: g(nx).left, dx: g(document.getElementById('date')).left,
                  tp: getComputedStyle(pr.querySelector('.arrow')).transform, tn: getComputedStyle(nx.querySelector('.arrow')).transform, dir: document.documentElement.dir}; }""")
        if r["pa"] != T["day_prev"] or r["na"] != T["day_next"]: bad.append(f"{lang}: aria labels {r['pa']} {r['na']}")
        if min(r["pw"], r["ph"], r["nw"], r["nh"]) < 44: bad.append(f"{lang}: touch target below 44px {r}")
        if lang == "ar":
            if r["tp"] == "none" or r["tn"] == "none" or not (r["px"] > r["dx"] > r["nx"]): bad.append(f"ar: arrows not mirrored / order not reversed {r}")
        elif r["tp"] != "none" or not (r["px"] < r["dx"] < r["nx"]): bad.append(f"{lang}: arrows or order wrong {r}")
        # keyboard focus visible after Tab, no rectangle after a mouse click
        p.evaluate("document.getElementById('date').focus()"); p.keyboard.press("Shift+Tab")
        if p.evaluate("document.activeElement.id") == "prevDay" or True:
            for _ in range(3):
                if p.evaluate("document.activeElement.id") == "nextDay": break
                p.keyboard.press("Tab")
            if p.evaluate("document.activeElement.id") == "nextDay":
                o = p.evaluate("() => { const c = getComputedStyle(document.activeElement); return [c.outlineStyle, parseFloat(c.outlineWidth)]; }")
                if o[0] == "none" or o[1] < 2: bad.append(f"{lang}: no visible keyboard focus on the next-day button {o}")
        p.evaluate("() => { const d = document.getElementById('date'); d.value = '2025-06-10'; d.dispatchEvent(new Event('change')); }"); p.click("#nextDay")
        o = p.evaluate(OUTLINES_JS)
        if o: bad.append(f"{lang}: focus rectangle after a mouse click {o}")
        p.close()
        for w in (360, 320):
            p = _open(browser, base, lang, w=w, h=740, date="2025-06-10")
            r = p.evaluate("() => { const d = document.documentElement, dl = document.getElementById('popup'); return {pageOv: d.scrollWidth > d.clientWidth, dlgOv: dl.scrollWidth > dl.clientWidth}; }")
            if r["pageOv"] or r["dlgOv"]: bad.append(f"{lang} {w}px: horizontal overflow {r}")
            p.close()
    # limits come from the data: patch future_meta.json and the next-day button follows
    p = browser.new_page(viewport={"width": 1440, "height": 900})
    def patched(route):
        m = dict(_FM); m["covers_last_local_date"] = "2026-11-20"; route.fulfill(status=200, content_type="application/json", body=_json.dumps(m))
    p.route("**/data/future_meta.json", patched); p.goto(f"{base}/index.html?lang=en#state=BY&date=2026-11-19&hour=day"); p.wait_for_selector("#popup[open]")
    if p.evaluate("document.getElementById('nextDay').disabled"): bad.append("limit from data: next disabled one day early")
    p.click("#nextDay")
    if not p.evaluate("document.getElementById('nextDay').disabled"): bad.append("limit from data: next not disabled at the patched last date")
    p.close()
    return bad

ALL3 = {"notes_block": notes_problems, "rewritten_texts_all_zones_states_languages": rewritten_texts_problems, "previous_next_day_buttons": day_buttons_problems}
