"""Tests for the site translations (site/i18n/{en,de,ar}.json) and for the front end code. No browser needed."""
import json, re
from pathlib import Path
import pytest

SITE = Path(__file__).resolve().parents[1] / "site"
LANGS = ["en", "de", "ar"]
M = {l: json.load(open(SITE / "i18n" / f"{l}.json", encoding="utf8")) for l in LANGS}
JS = (SITE / "app.js").read_text(encoding="utf8"); HTML = (SITE / "index.html").read_text(encoding="utf8")
PH = lambda s: sorted(re.findall(r"\{(\w+)\}", s))
DYNAMIC = {"state_": {"SH", "HH", "NI", "HB", "NW", "HE", "RP", "BW", "BY", "SL", "BE", "BB", "MV", "SN", "ST", "TH"}, "cfg_": {"A", "B", "C"}}

def test_identical_key_sets():
    assert set(M["en"]) == set(M["de"]) == set(M["ar"]), (set(M["en"]) ^ set(M["de"]), set(M["en"]) ^ set(M["ar"]))

@pytest.mark.parametrize("lang", LANGS)
def test_no_empty_values(lang):
    for k, v in M[lang].items(): assert isinstance(v, str) and v.strip(), (lang, k)

def test_identical_placeholders():
    for k, v in M["en"].items():
        for l in ("de", "ar"): assert PH(M[l][k]) == PH(v), (l, k, PH(M[l][k]), PH(v))

def test_bold_markers_and_numbers_are_kept():
    for k, v in M["en"].items():
        for l in ("de", "ar"):
            assert M[l][k].count("**") == v.count("**"), (l, k)
    # every literal number in the English text must appear in the translation (percentages, days, years)
    for k, v in M["en"].items():
        if k in ("hour_first", "hour_second"): continue          # ordinals (1st / 2nd) are words in other languages
        nums = re.findall(r"\d+", re.sub(r"\{\w+\}", "", v))
        for l in ("de", "ar"):
            for n in nums: assert n in M[l][k], (l, k, n)

def test_every_key_used_in_code_and_html_exists_everywhere():
    called = set(re.findall(r"""\bt[m]?\(\s*["'](\w+)["']""", JS)) | set(re.findall(r"""\bth\(\s*["'](\w+)["']""", JS))
    prefixes = {k for k in called if k.endswith("_")}; called -= prefixes
    used = called | set(re.findall(r'data-i18n(?:-html|-aria|-title)?="(\w+)"', HTML))
    used |= set(re.findall(r"""["'](\w+)["']""", JS)) & set(M["en"])        # keys passed through variables or ternaries, e.g. t(ok ? "inside" : "outside")
    assert prefixes == set(DYNAMIC) and len(used) > 60
    for l in LANGS:
        for k in used: assert k in M[l], (l, k)
        for prefix, ids in DYNAMIC.items():
            for i in ids: assert prefix + i in M[l]
    assert 't("state_" + p.id)' in JS and 't("cfg_" + a.config)' in JS      # the only dynamic lookups
    dyn = {p + i for p, ids in DYNAMIC.items() for i in ids}
    for k in M["en"]: assert k in used or k in dyn, f"unused key {k}"

def strip_comments_and_collect_strings(src):
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i): i = src.find("\n", i); i = n if i < 0 else i
        elif src.startswith("/*", i): i = src.find("*/", i) + 2
        elif c in "\"'`":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == "\\": j += 1
                j += 1
            out.append(src[i + 1:j]); i = j + 1
        elif c == "/" and re.match(r"/[^/*\s][^/\n]*/[gimsuy]*", src[i:i + 80]) and re.search(r"[(=,:]\s*$", src[max(0, i - 3):i]):
            i = src.find("/", i + 1) + 1       # regex literal
        else: i += 1
    return out

ALLOWED_PHRASES = {"use strict", "python3 -m http.server -d site 8000", "http://localhost:8000", "Bundesnetzagentur | SMARD.de", "Weather data by Open-Meteo.com", "SMARD Control area", "MWh/h"}

def test_no_hard_coded_prose_in_js():
    for s in strip_comments_and_collect_strings(JS):
        s2 = re.sub(r"\$\{[^}]*\}", " ", s)
        if s2.strip().startswith(("#", ".", "[", "<")) and not re.search(r"[A-Za-z]{3,} [A-Za-z]{3,}", re.sub(r"<[^>]+>|[#.\[\]=\"\w-]+(?= |$)", "", s2)) and False: continue
        if re.fullmatch(r"[#.\[]?[\w .#\[\]=\"-]+", s2.strip()) and ("#" in s2 or "." in s2 or "[" in s2): continue      # CSS selectors
        if s2.strip().startswith("badge") or s2.strip() in ("in", "out"): continue                                        # CSS class names
        if s2.strip() in ALLOWED_PHRASES or s2.strip() in {"LightGBM", "Datenquellen", "CC BY 4.0"}: continue
        assert not re.search(r"[A-Za-z]{3,}[ ,]+[A-Za-z]{3,}", re.sub(r"<[^>]+>", " ", s2)) or s2.startswith(("M", "http")) and " " not in s2, f"hard-coded English in app.js: {s!r}"
    assert "؀" not in re.sub(r'العربية', "", JS), "Arabic prose in app.js"      # only the language label

def test_no_hard_coded_prose_in_html():
    body = re.sub(r"<(script|style|title)\b.*?</\1>", "", HTML, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", body)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    assert lines == ["Weather data by Open-Meteo.com"], lines         # the required attribution link text is the only literal text
    assert re.search(r"<title>Germany grid-load forecast map</title>", HTML)
    for attr in re.findall(r"(?<![\w-])(?:aria-label|title|alt|placeholder)=\"([^\"]*)\"", HTML): assert attr == "", attr

def test_language_setup_rtl_and_logical_css():
    assert 'ar: {label: "العربية", dir: "rtl"' in JS and 'de: {label: "Deutsch", dir: "ltr"' in JS and 'en: {label: "English", dir: "ltr"' in JS
    assert "document.documentElement.dir = LANGS[lang].dir" in JS and "document.documentElement.lang = lang" in JS
    assert "ar-u-nu-latn" in JS                               # Latin digits in Arabic
    css = (SITE / "style.css").read_text()
    for physical in ("margin-left", "margin-right", "padding-left", "padding-right", "text-align:left", "text-align:right"):
        assert physical not in css, physical
    assert "direction:ltr" in css                              # chart stays left-to-right
    assert "localStorage" in JS and re.search(r"try \{[^}]*localStorage", JS)   # wrapped in try/catch

def test_no_network_requests_beyond_own_files():
    code = JS
    for url in re.findall(r"""fetch\(([^)]*)\)""", code): assert "http" not in url, url
    assert not re.search(r"XMLHttpRequest|sendBeacon|WebSocket|EventSource|import\(", code)
    assert not re.search(r"""<(script|link|img|iframe)[^>]+(?:src|href)="https?://""", HTML)
    for u in re.findall(r"""fetch\(\s*[`'"]([^`'"]+)""", code): assert not u.startswith(("http", "//")), u
    # remote URLs in the code are only attribution links (shown as <a href>), never fetched
    assert "getJSON(`i18n/${l}.json`)" in code
