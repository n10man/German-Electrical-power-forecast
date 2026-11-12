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
