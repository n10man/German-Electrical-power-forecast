"""Fill in the public site URL once hosting is decided:  python scripts/set_site_url.py https://example.org/map
Writes site/config.js (baseUrl) and the absolute og:image / og:url / twitter:image tags in site/index.html, which social-preview crawlers read without running JavaScript.
Pass an empty string to clear it again."""
import re, sys
from pathlib import Path
SITE = Path(__file__).resolve().parents[1] / "site"

def apply(url, site=SITE):
    base = url.rstrip("/")
    (site / "config.js").write_text(re.sub(r'baseUrl: "[^"]*"', f'baseUrl: "{base}"', (site / "config.js").read_text()))
    h = (site / "index.html").read_text()
    img = f"{base}/preview.jpg" if base else "preview.jpg"
    h = re.sub(r'(<meta (?:property="og:image"|name="twitter:image") content=")[^"]*(")', lambda m: m.group(1) + img + m.group(2), h)
    h = re.sub(r'(<meta property="og:url" content=")[^"]*(")', lambda m: m.group(1) + (base + "/" if base else "") + m.group(2), h)
    (site / "index.html").write_text(h)

if __name__ == "__main__":
    if len(sys.argv) != 2: sys.exit(__doc__)
    apply(sys.argv[1])
