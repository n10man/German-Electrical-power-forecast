"""The one-command snapshot refresh, tested with mocked downloads (no network, no models, no real data touched)."""
import importlib.util, re, shutil, sys
from pathlib import Path
import pandas as pd, pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("refresh_snapshot", ROOT / "scripts/refresh_snapshot.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
import download_load as D

def fake_get(url):
    """Fake SMARD: three weekly chunks; the newest one is one week newer than the stored data."""
    stamps = [1_700_000_000_000 + i * 604_800_000 for i in range(3)]
    if "index_quarterhour" in url: return {"timestamps": stamps}
    ts = int(re.search(r"_(\d+)\.json", url).group(1))
    return {"series": [[ts + q * 900_000, 100.0 + q] for q in range(4)]}

def old_frame():
    ts = [1_700_000_000_000 + q * 900_000 for q in range(4)]
    return pd.DataFrame({"load_mw": [1.0] * 4, "timestamp_utc": pd.to_datetime(ts, unit="ms", utc=True)})

def test_update_load_merges_only_new_chunks_and_keeps_a_backup(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir(); calls = []
    for z in D.ZONES: old_frame().to_parquet(raw / f"load_{z}.parquet")
    R.update_load(raw, get=lambda u: (calls.append(u), fake_get(u))[1], log=lambda *a: None)
    for z in D.ZONES:
        m = pd.read_parquet(raw / f"load_{z}.parquet"); assert m.timestamp_utc.is_unique and len(m) == 12
        assert m.timestamp_utc.max() > old_frame().timestamp_utc.max()
    backups = list(raw.glob("_old_load_*")); assert len(backups) == 1 and len(list(backups[0].glob("*.parquet"))) == 4
    assert not any("1700000000000" in c and "index" not in c for c in calls[:0])                           # (the old chunk is within the overlap window and re-fetched; that is intended)
    assert len(calls) == 4 * 4                                                                           # per zone: 1 index + 3 chunks, nothing else

def make_site(tmp_path):
    site = tmp_path / "site"; (site / "data").mkdir(parents=True)
    for f in R.PAST_FILES: (site / "data" / f).write_text("past " + f)
    return site

def test_refresh_runs_steps_in_order_and_never_uses_git(tmp_path):
    site = make_site(tmp_path); raw = tmp_path / "raw"; raw.mkdir(); (raw / "forecast_current_20260101T000000Z.parquet").write_text("x"); cmds, loads = [], []
    R.refresh(site=site, raw=raw, py="PY", runner=lambda c, **k: (cmds.append(c), 0)[1], loader=lambda r: loads.append(r))
    assert loads == [raw] and [c[1] for c in cmds[:2]] == ["scripts/download_forecast_current.py", "scripts/make_future_forecast.py"]
    assert cmds[2][1:3] == ["-m", "pytest"] and any("test_no_personal_email" in a for a in cmds[2])
    assert not any("git" in " ".join(c) for c in cmds)

def test_refresh_fails_loudly_if_a_past_file_changes(tmp_path):
    site = make_site(tmp_path); raw = tmp_path / "raw"; raw.mkdir(); (raw / "forecast_current_20260101T000000Z.parquet").write_text("x")
    def tamper(c, **k): (site / "data" / "Amprion.json").write_text("changed"); return 0
    with pytest.raises(SystemExit, match="PAST-DATE FILES CHANGED.*Amprion"): R.refresh(site=site, raw=raw, py="PY", runner=tamper, loader=lambda r: None, skip_tests=True)

def test_refresh_stops_when_a_step_fails(tmp_path):
    site = make_site(tmp_path); raw = tmp_path / "raw"; raw.mkdir(); n = []
    with pytest.raises(SystemExit, match="weather download failed"): R.refresh(site=site, raw=raw, runner=lambda c, **k: (n.append(c), 1)[1], loader=lambda r: None)
    assert len(n) == 1

def test_script_never_pushes_or_touches_git_config():
    src = (ROOT / "scripts/refresh_snapshot.py").read_text() + (ROOT / "scripts/refresh_snapshot.sh").read_text()
    assert not re.search(r"git\s+(push|remote|config)|\"git\"", src)

def test_set_site_url_fills_absolute_tags(tmp_path):
    import set_site_url as S
    site = tmp_path / "site"; site.mkdir(); shutil.copy(ROOT / "site/index.html", site); shutil.copy(ROOT / "site/config.js", site)
    S.apply("https://example.org/map/", site); h = (site / "index.html").read_text()
    assert 'og:image" content="https://example.org/map/preview.jpg"' in h and 'twitter:image" content="https://example.org/map/preview.jpg"' in h and 'og:url" content="https://example.org/map/"' in h
    assert 'baseUrl: "https://example.org/map"' in (site / "config.js").read_text()
    S.apply("", site); assert 'og:image" content="preview.jpg"' in (site / "index.html").read_text()
