"""Where writable state goes, and — the trap — where it must NOT go.

`backend/data/` mixes two kinds of file: the committed model artifacts the app
cannot boot without, and the runtime state a deployment has to keep. On an
ephemeral container the second kind is erased on every redeploy while the
dashboard still reports "Saved". These tests pin the separation that fixes it.
"""
import importlib

from app.services import state_paths


def test_the_default_is_the_original_path(monkeypatch):
    """Unset means unchanged. Local development and CI must not shift."""
    monkeypatch.delenv("AUDIOSENSE_STATE_DIR", raising=False)
    assert state_paths.state_dir() == state_paths.PACKAGE_DATA_DIR


def test_the_override_moves_writable_state(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIOSENSE_STATE_DIR", str(tmp_path))
    assert state_paths.state_dir() == tmp_path


def test_an_empty_value_falls_back_rather_than_writing_to_the_root(monkeypatch):
    """`AUDIOSENSE_STATE_DIR=` in a .env file is empty, not unset.

    Treating that as a real value would resolve to Path("") — the working
    directory — and scatter the patient database wherever the process started.
    """
    for blank in ("", "   "):
        monkeypatch.setenv("AUDIOSENSE_STATE_DIR", blank)
        assert state_paths.state_dir() == state_paths.PACKAGE_DATA_DIR


def test_state_path_creates_the_directory(monkeypatch, tmp_path):
    target = tmp_path / "nested" / "state"
    monkeypatch.setenv("AUDIOSENSE_STATE_DIR", str(target))
    p = state_paths.state_path("records.db")
    assert p.parent.is_dir(), "a fresh volume mount is an empty directory"
    assert p == target / "records.db"


def test_it_is_read_at_call_time_not_frozen_at_import(monkeypatch, tmp_path):
    """backend/.env is loaded before the routers import, but a constant here
    would still freeze at whatever the first importer saw. AUDIOSENSE_SESSION_
    HOURS was silently ignored for exactly that reason."""
    monkeypatch.setenv("AUDIOSENSE_STATE_DIR", str(tmp_path / "one"))
    first = state_paths.state_dir()
    monkeypatch.setenv("AUDIOSENSE_STATE_DIR", str(tmp_path / "two"))
    assert state_paths.state_dir() != first


# ------------------------------------------------------------- the trap ----


def test_the_model_artifacts_are_not_reached_through_the_state_dir(monkeypatch,
                                                                   tmp_path):
    """The obvious fix — mount a volume over /app/data — breaks the app.

    It shadows the committed 12 MB of model artifacts, which are read-only and
    load at import. They must resolve independently of the override, or a
    deployment that adds persistence stops booting.
    """
    monkeypatch.setenv("AUDIOSENSE_STATE_DIR", str(tmp_path))

    from app.ml import classifier
    from app.otoscopy import model as oto_model
    importlib.reload(classifier)
    importlib.reload(oto_model)
    try:
        for path in (classifier.MODEL_PATH, oto_model.ARTIFACT,
                     oto_model.REFERENCE_DIR):
            assert tmp_path not in path.parents, (
                f"{path} would move onto the state volume and disappear")
            assert path.exists(), f"{path} is a committed artifact and must ship"
    finally:
        monkeypatch.delenv("AUDIOSENSE_STATE_DIR", raising=False)
        importlib.reload(classifier)
        importlib.reload(oto_model)


def test_every_writable_store_moves_together(monkeypatch, tmp_path):
    """All five, or the operator persists some patient data and loses the rest."""
    monkeypatch.setenv("AUDIOSENSE_STATE_DIR", str(tmp_path))

    from app.routers import feedback, handout
    from app.services import ai_config, pdf, records
    mods = [records, pdf, handout, feedback, ai_config]
    for m in mods:
        importlib.reload(m)
    try:
        moved = {
            "records.db": records.DB_PATH,
            "verify_store.json": pdf.VERIFY_STORE,
            "handouts.json": handout.HANDOUT_STORE,
            "feedback.jsonl": feedback.FEEDBACK_PATH,
            "ai_config.json": ai_config.CONFIG_PATH,
        }
        for name, path in moved.items():
            assert path.parent == tmp_path, f"{name} did not follow the override"
            assert path.name == name
    finally:
        monkeypatch.delenv("AUDIOSENSE_STATE_DIR", raising=False)
        for m in mods:
            importlib.reload(m)


def test_records_survive_a_restart_of_the_module(monkeypatch, tmp_path):
    """The whole point: write, reload as a redeploy would, read it back."""
    monkeypatch.setenv("AUDIOSENSE_STATE_DIR", str(tmp_path))

    from app.services import records
    importlib.reload(records)
    try:
        records.save_visit({
            "patient": {"name": "Persist Me", "age": 40, "test_date": "2026-01-01"},
            "rules": {"right": {"ac_pta": {"value": 30.0}}},
            "thresholds": {"right": {}, "left": {}},
        })
        assert [p["name"] for p in records.list_patients()] == ["Persist Me"]

        importlib.reload(records)          # stand-in for a container restart
        assert [p["name"] for p in records.list_patients()] == ["Persist Me"], (
            "the visit did not survive — the state directory is not being used")
    finally:
        monkeypatch.delenv("AUDIOSENSE_STATE_DIR", raising=False)
        importlib.reload(records)
