"""Privacy, sharing metadata, touch handling and the recorded cross-engine check."""
import json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; SITE = ROOT / "site"
HTML = (SITE / "index.html").read_text(); JS = (SITE / "app.js").read_text(); CSS = (SITE / "style.css").read_text()

def test_head_has_title_description_favicon_theme_and_social_tags():
    for needle in ('<title>', 'name="description"', 'rel="icon"', 'name="theme-color"', 'property="og:title"', 'property="og:description"', 'property="og:image"', 'property="og:url"', 'name="twitter:card"', 'name="twitter:image"', 'viewport-fit=cover'):
        assert needle in HTML, needle
    assert (SITE / "favicon.svg").exists() and (SITE / "preview.jpg").stat().st_size > 10_000
    assert 'baseUrl: ""' in (SITE / "config.js").read_text()          # empty until hosting is decided; scripts/set_site_url.py fills it

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
