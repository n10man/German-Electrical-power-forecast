"""Real WebKit and Chromium (Playwright, optional): tooltip on every state in en/de/ar, no focus rectangle after mouse use, keyboard highlight after Tab.
Skipped when Playwright or its browsers are not installed (see scripts/check_site_browsers.py for the install line)."""
import functools, http.server, sys, threading
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
sync_api = pytest.importorskip("playwright.sync_api", reason="Playwright not installed")
import site_engine_checks as C

@pytest.fixture(scope="module")
def base():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT / "site"))); threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"; srv.shutdown()

@pytest.fixture(scope="module")
def pw():
    with sync_api.sync_playwright() as p: yield p

@pytest.mark.parametrize("engine", ["webkit", "chromium"])
@pytest.mark.parametrize("name", list(C.ALL))
def test_engine_check(pw, base, engine, name):
    try: browser = getattr(pw, engine).launch()
    except Exception as e: pytest.skip(f"{engine} cannot be launched here: {str(e)[:80]}")
    try: problems = C.ALL[name](browser, base)
    finally: browser.close()
    assert not problems, problems[:5]
