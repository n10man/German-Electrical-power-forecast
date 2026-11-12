"""Privacy, sharing metadata, touch handling and the recorded cross-engine check."""
import json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; SITE = ROOT / "site"
HTML = (SITE / "index.html").read_text(); JS = (SITE / "app.js").read_text(); CSS = (SITE / "style.css").read_text()

def test_head_has_title_description_favicon_theme_and_social_tags():
    for needle in ('<title>', 'name="description"', 'rel="icon"', 'name="theme-color"', 'property="og:title"', 'property="og:description"', 'property="og:image"', 'property="og:url"', 'name="twitter:card"', 'name="twitter:image"', 'viewport-fit=cover'):
        assert needle in HTML, needle
    assert (SITE / "favicon.svg").exists() and (SITE / "preview.jpg").stat().st_size > 10_000
    URL = "https://germany-electricity-forecast.netlify.app"            # the real address; scripts/set_site_url.py fills it into config.js and the tags below
    cfg = re.search(r'baseUrl:\s*"([^"]*)"', (SITE / "config.js").read_text()).group(1)
    assert cfg == URL, cfg                                                # no empty or placeholder address any more
    for prop, want in (('property="og:url"', URL + "/"), ('property="og:image"', URL + "/preview.jpg"), ('name="twitter:image"', URL + "/preview.jpg")):
        m = re.search(r'<meta ' + prop + r' content="([^"]*)"', HTML); assert m and m.group(1) == want, (prop, m and m.group(1))
    assert not re.search(r'<link rel="canonical"', HTML) or f'<link rel="canonical" href="{URL}/">' in HTML

def test_privacy_line_in_footer_and_licences_in_every_language_and_no_cookies():
    assert 'id="privacyLine"' in HTML and 'data-i18n="privacy_line"' in HTML and "privacy_line" in JS
    for l in ("en", "de", "ar"): assert json.load(open(SITE / f"i18n/{l}.json"))["privacy_line"]
    assert "no personal data" in json.load(open(SITE / "i18n/en.json"))["privacy_line"] and "no cookies" in json.load(open(SITE / "i18n/en.json"))["privacy_line"]
    assert "document.cookie" not in JS and not re.search(r"analytics|gtag|tracker|fonts\.googleapis", HTML + JS + CSS, re.I)

def test_source_code_and_method_links():
    assert "https://github.com/n10man/German-Electrical-power-forecast" in HTML and "docs/METHODS.md" in JS and "licences_code" in JS

def test_single_tap_opens_popup_no_hover_dependence():
    assert not re.search(r'addEventListener\("mouse(enter|over|move|leave)"', JS)                   # iOS would swallow the first tap
    assert 'e.pointerType === "mouse"' in JS and 'path.addEventListener("click"' in JS
    assert "prefers-reduced-motion" in CSS and "env(safe-area-inset" in CSS and "min-height:44px" in CSS and "font-size:16px" in CSS

def test_zone_files_are_loaded_lazily_and_errors_are_translated():
    assert "getJSON(`data/${z}.json`)" in JS and "zoneData(zone)" in JS and 'showLoadError("load_error_zone"' in JS
    init = JS[JS.index("async function init"):]; assert "data/Amprion" not in init and "zoneData(" not in init.split("openPopup")[0]

def test_recorded_browser_check_is_clean():
    p = ROOT / "results/site_browser_check.json"; r = json.load(open(p))
    assert r["with_problems"] == 0 and {x["engine"] for x in r["runs"]} >= {"chromium", "webkit"}
    assert sum(r["first_load_files_1440_en"].values()) < 1_000_000

def test_recorded_browser_check_includes_hover_results():
    r = json.load(open(ROOT / "results/site_browser_check.json"))["runs"]
    desk = [x["hover"] for x in r if "overlayOnHover" in x.get("hover", {})]; touch = [x["hover"] for x in r if "overlayCreatedByTouch" in x.get("hover", {})]
    assert desk and touch and all(all(v is True for v in h.values()) for h in desk) and all(h["overlayCreatedByTouch"] == 0 for h in touch)


def test_recorded_engine_checks_are_clean():
    r = json.load(open(ROOT / "results/site_browser_check.json"))["engine_checks"]
    assert set(r) >= {"chromium", "webkit"}
    for eng, d in r.items():
        assert set(d) == {"tooltip_every_state_every_language", "no_focus_rectangle_after_mouse_click_and_close", "keyboard_highlight_after_tab", "all_states_all_languages", "runtime_language_switch", "notes_block", "rewritten_texts_all_zones_states_languages", "previous_next_day_buttons"}
        assert all(v == [] for v in d.values()), (eng, d)
