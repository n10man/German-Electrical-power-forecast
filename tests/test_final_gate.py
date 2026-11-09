"""Gate tests for scripts/final_eval.py. None of them may read the real sealed test file."""
import importlib.util, json, shutil, sys
from pathlib import Path
import pandas as pd, pytest

ROOT = Path(__file__).resolve().parents[1]
def load_mod():
    spec = importlib.util.spec_from_file_location("final_eval", ROOT / "scripts" / "final_eval.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

@pytest.fixture
def fe(monkeypatch, tmp_path):
    monkeypatch.chdir(ROOT); sys.path.insert(0, str(ROOT / "src"))
    m = load_mod(); reads = []; real = pd.read_parquet
    monkeypatch.setattr(pd, "read_parquet", lambda p, *a, **k: (reads.append(str(p)), real(p, *a, **k))[1])
    monkeypatch.setattr(m, "DONE", tmp_path / "DONE"); m.reads = reads; return m

MODEL_FILES = list((ROOT / "models").glob("*.txt")) if (ROOT / "models").is_dir() else []
needs_models = pytest.mark.skipif(not MODEL_FILES, reason="models/ is absent or empty (it is gitignored): run `python scripts/train_final.py --force` to rebuild the models, then re-run pytest")

def test_refuses_without_confirm(fe):
    with pytest.raises(SystemExit) as e: fe.main([])
    assert e.value.code == 2 and fe.reads == []

def test_dummy_without_confirm_refused(fe):
    with pytest.raises(SystemExit) as e: fe.main(["--dummy"])
    assert e.value.code == 2

def test_refuses_when_already_done(fe):
    fe.DONE.write_text("{}")
    with pytest.raises(SystemExit) as e: fe.main(["--confirm-final"])
    assert e.value.code == 3 and fe.reads == []          # sealed file never read

@needs_models
def test_refuses_on_tampered_lock(fe, monkeypatch, tmp_path):
    lock = json.load(open(ROOT / "results/model_lock.json")); k = next(iter(lock["sha256"])); lock["sha256"][k] = "0" * 64
    p = tmp_path / "lock.json"; p.write_text(json.dumps(lock)); monkeypatch.setattr(fe, "LOCK", p)
    with pytest.raises(SystemExit) as e: fe.main(["--confirm-final"])
    assert e.value.code == 4 and fe.reads == []

@needs_models
def test_dummy_run_never_touches_sealed_or_results(fe, tmp_path):
    before = {p.name for p in (ROOT / "results").iterdir()}
    fe.main(["--confirm-final", "--dummy", "--out-dir", str(tmp_path / "out")])
    assert not any("sealed_test" in r for r in fe.reads)
    assert not fe.DONE.exists() and {p.name for p in (ROOT / "results").iterdir()} == before
    assert (tmp_path / "out" / "dummy_metrics.csv").exists()

@needs_models
def test_dummy_requires_out_dir(fe):
    with pytest.raises(SystemExit) as e: fe.main(["--confirm-final", "--dummy"])
    assert e.value.code == 5

def test_train_final_refuses_to_overwrite_lock_without_force():
    import subprocess
    lock = ROOT / "results/model_lock.json"; before = lock.read_bytes()
    r = subprocess.run([sys.executable, str(ROOT / "scripts/train_final.py")], cwd=ROOT, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")})
    assert r.returncode != 0 and "--force" in r.stderr
    assert lock.read_bytes() == before
