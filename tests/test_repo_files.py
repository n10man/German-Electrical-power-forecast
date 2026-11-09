from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_mit_license_and_readme_section():
    lic = (ROOT / "LICENSE").read_text()
    assert lic.startswith("MIT License") and "Copyright (c) 2026 n10man" in lic and "Permission is hereby granted, free of charge" in lic
    readme = (ROOT / "README.md").read_text()
    sec = readme[readme.index("## Licence and data terms"):]; sec = sec[:sec.index("\n## ", 5)]
    for needle in ("MIT", "CC BY 4.0", "non-commercial", "dl-de/by-2-0", "portfolio", "LICENSE"): assert needle in sec, needle
    assert "no LICENSE file" not in readme and "no licence file" not in readme

def test_no_personal_email_in_tracked_text_files():
    import subprocess
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    for f in files:
        p = ROOT / f
        if p.suffix in (".png", ".jpg", ".parquet", ".json", ".geojson") and p.stat().st_size > 2_000_000: continue
        data = p.read_bytes().lower()
        assert b"ahmednomann" not in data and b"gmail.com" not in data, f
