"""Where the writable state lives — one answer, in one place.

``backend/data/`` is a mixed directory and that is the whole problem this module
exists to solve. It holds two kinds of file that look identical from the outside:

  READ-ONLY, shipped in the image — ``model_bundle.joblib``,
  ``otoscopy_model.joblib``, ``deep_ensemble.joblib``, ``otoscope_reference/``.
  About 12 MB, committed, and the app cannot start without them.

  WRITABLE, created at runtime — the patient database, the report verification
  store, the handout store, the feedback log, the provider configuration.

On every free container host the filesystem is ephemeral, so the writable half
is erased on each restart and redeploy. The dashboard still says "Saved". That
is the failure this fixes: a clinician records a visit, is told it is stored,
and it is not.

The obvious fix — mount a volume over ``/app/data`` — is wrong, because it
shadows the read-only half and the app stops booting. So the two are separated
instead: ``AUDIOSENSE_STATE_DIR`` moves only the writable files somewhere that
survives, and the model artifacts stay where they are.

DEFAULT IS UNCHANGED. With the variable unset this resolves to exactly the path
these files already used, so local development and the test suite behave as
before and deployment is opt-in.
"""
from __future__ import annotations

import os
from pathlib import Path

#: The directory the model artifacts and reference images ship in. Read-only in
#: practice; never point a volume at it.
PACKAGE_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def state_dir() -> Path:
    """Directory for files the application WRITES, read at call time.

    Call time rather than import time: ``backend/.env`` is loaded by
    ``app.main`` before the routers are imported, but a constant evaluated in
    this module would still freeze whatever happened to be set when the first
    importer touched it. AUDIOSENSE_SESSION_HOURS was silently ignored for
    exactly that reason, and this avoids repeating it.
    """
    configured = os.environ.get("AUDIOSENSE_STATE_DIR", "").strip()
    return Path(configured) if configured else PACKAGE_DATA_DIR


def state_path(filename: str) -> Path:
    """Full path to one writable file, with its directory created."""
    directory = state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / filename
