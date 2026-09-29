"""Patient records — SQLite persistence across visits.

Session storage is fine for a demo but makes the progression module a
two-point comparison forever. Real hearing conservation is longitudinal:
you need every visit a worker has ever had, so a 3 dB drift per year is
visible before it becomes a compensable injury.

Plain sqlite3 from the standard library — no ORM, no migrations, and the
database is a single file that a clinic can copy onto a USB stick.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.services.state_paths import state_dir

# Writable state. Resolved through state_paths so a deployment can move it
# onto a volume that survives a redeploy; unset, this is the original path.
DATA_DIR = state_dir()
DB_PATH = DATA_DIR / "records.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    age INTEGER,
    sex TEXT,
    occupation TEXT,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    test_date TEXT,
    recorded TEXT NOT NULL,
    right_pta REAL,
    left_pta REAL,
    grade TEXT,
    pattern TEXT,
    disability_pct REAL,
    record_json TEXT NOT NULL,
    analysis_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_visits_patient ON visits(patient_id, test_date);
"""


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Write-ahead logging: a reader no longer blocks a writer, which matters
    # once this is a real file on a volume with a clinician saving a visit
    # while the records list is open. The timeout replaces an instant
    # "database is locked" error with a short wait.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(SCHEMA)
    return conn


def find_or_create_patient(conn, name: str, age=None, sex=None, occupation=None) -> int:
    """Patients are matched on name — adequate for a clinic-scale demo."""
    row = conn.execute(
        "SELECT id FROM patients WHERE lower(name) = lower(?)", (name,)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE patients SET age = COALESCE(?, age), sex = COALESCE(?, sex), "
            "occupation = COALESCE(?, occupation) WHERE id = ?",
            (age, sex, occupation, row["id"]),
        )
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO patients (name, age, sex, occupation, created) VALUES (?,?,?,?,?)",
        (name, age, sex, occupation, datetime.now(timezone.utc).isoformat()),
    )
    return int(cur.lastrowid)


def save_visit(analysis: dict) -> dict:
    """Persist one analyzed test against its patient."""
    patient = analysis.get("patient") or {}
    name = (patient.get("name") or "").strip()
    if not name:
        return {"saved": False, "reason": "a patient name is required to save a visit"}

    rules = analysis.get("rules") or {}
    ml = analysis.get("ml") or {}
    right_pta = ((rules.get("right") or {}).get("ac_pta") or {}).get("value")
    left_pta = ((rules.get("left") or {}).get("ac_pta") or {}).get("value")
    grade = ((rules.get("right") or {}).get("who_grade") or {}).get("grade")
    pattern = (ml.get("right") or {}).get("pattern_label") if ml.get("right") else None
    disability = (rules.get("disability") or {}).get("binaural_pct")

    record = {
        "patient": patient,
        "right": (analysis.get("thresholds") or {}).get("right", {}),
        "left": (analysis.get("thresholds") or {}).get("left", {}),
    }

    with _connect() as conn:
        pid = find_or_create_patient(
            conn, name, patient.get("age"), patient.get("sex"), patient.get("occupation"))
        cur = conn.execute(
            "INSERT INTO visits (patient_id, test_date, recorded, right_pta, left_pta,"
            " grade, pattern, disability_pct, record_json, analysis_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pid, str(patient.get("test_date") or ""),
             datetime.now(timezone.utc).isoformat(),
             right_pta, left_pta, grade, pattern, disability,
             json.dumps(record, ensure_ascii=False, default=str),
             json.dumps({k: analysis.get(k) for k in ("rules", "ml", "sii", "battery")},
                        ensure_ascii=False, default=str)),
        )
        return {"saved": True, "patient_id": pid, "visit_id": int(cur.lastrowid)}


def list_patients(query: str = "") -> List[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT p.id, p.name, p.age, p.sex, p.occupation,"
            " COUNT(v.id) AS visits, MAX(v.test_date) AS last_visit"
            " FROM patients p LEFT JOIN visits v ON v.patient_id = p.id"
            " WHERE (? = '' OR lower(p.name) LIKE lower(?))"
            " GROUP BY p.id ORDER BY p.name",
            (query, f"%{query}%"),
        ).fetchall()
        return [dict(r) for r in rows]


def patient_history(patient_id: int) -> Optional[dict]:
    """Every visit for one patient, oldest first, with the trend."""
    with _connect() as conn:
        p = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        if not p:
            return None
        rows = conn.execute(
            "SELECT id, test_date, recorded, right_pta, left_pta, grade, pattern,"
            " disability_pct, record_json FROM visits WHERE patient_id = ?"
            " ORDER BY COALESCE(NULLIF(test_date,''), recorded)",
            (patient_id,),
        ).fetchall()

    visits = []
    for r in rows:
        v = dict(r)
        v["record"] = json.loads(v.pop("record_json"))
        visits.append(v)

    trend = None
    if len(visits) >= 2:
        first, last = visits[0], visits[-1]
        def delta(key):
            if first[key] is None or last[key] is None:
                return None
            return round(last[key] - first[key], 1)
        trend = {
            "visits": len(visits),
            "span": f"{first['test_date'] or '?'} → {last['test_date'] or '?'}",
            "right_change": delta("right_pta"),
            "left_change": delta("left_pta"),
            "worsening": any(
                d is not None and d >= 10 for d in (delta("right_pta"), delta("left_pta"))
            ),
        }

    return {"patient": dict(p), "visits": visits, "trend": trend}


def delete_patient(patient_id: int) -> bool:
    with _connect() as conn:
        conn.execute("DELETE FROM visits WHERE patient_id = ?", (patient_id,))
        cur = conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        return cur.rowcount > 0


# ------------------------------------------------------------ backup ----
#
# The database's whole design brief is "a single file a clinic can copy onto
# a USB stick" — these two functions are that brief made into endpoints, for
# hosts whose disk does not survive a redeploy (every free tier now). WAL
# journaling makes a naive file copy unsafe: recent writes live in the -wal
# sidecar, so a copy of records.db alone can be missing the last visits.
# The sqlite3 backup API checkpoints into the destination, which makes the
# snapshot complete and consistent even while a visit is being saved.


def _unlink_with_sidecars(path: Path) -> None:
    """Remove a temp database AND its -wal/-shm sidecars.

    The snapshot inherits journal_mode=WAL from the live database (the mode
    is stored in the file header), so merely opening it spawns sidecar
    files. Unlinking only the .db leaves a -wal/-shm pair behind on every
    backup and restore — litter that accumulates for the life of a server.
    """
    for p in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        p.unlink(missing_ok=True)


def backup_bytes() -> bytes:
    """A consistent snapshot of the whole database, safe under WAL."""
    if not DB_PATH.exists():
        raise FileNotFoundError("no records database yet")
    src = _connect()
    try:
        fd, tmp = tempfile.mkstemp(suffix=".db", dir=DATA_DIR)
        os.close(fd)
        tmp_path = Path(tmp)
        try:
            dest = sqlite3.connect(tmp)
            try:
                src.backup(dest)
            finally:
                dest.close()
            return tmp_path.read_bytes()
        finally:
            _unlink_with_sidecars(tmp_path)
    finally:
        src.close()


def restore_bytes(data: bytes) -> dict:
    """Validate an uploaded backup and copy it over the live database.

    The file is proven to be a SQLite database holding the expected tables
    BEFORE anything is replaced — a failed restore must leave the live
    records exactly as they were.

    The copy goes through SQLite's backup API rather than os.replace: on
    Windows a file cannot be swapped while any connection still holds it
    open, so a file-level replace works exactly until a second request has
    touched the database, then fails with EACCES. The backup API rewrites
    the destination page by page through its own connection, which takes
    the locks it needs and leaves WAL state consistent on every platform.
    """
    if not data.startswith(b"SQLite format 3\x00"):
        raise ValueError("that file is not a SQLite database")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".db", dir=DATA_DIR)
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        tmp_path.write_bytes(data)
        try:
            check = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
            try:
                tables = {r[0] for r in check.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"patients", "visits"} <= tables:
                    raise ValueError(
                        "that database is not an AudioSense records backup "
                        "(missing the patients/visits tables)")
                patients = check.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
                visits = check.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
            finally:
                check.close()
        except sqlite3.DatabaseError as e:
            raise ValueError(f"that file could not be read as a database: {e}")

        src = sqlite3.connect(tmp)
        try:
            dest = _connect()
            try:
                src.backup(dest)
            finally:
                dest.close()
        finally:
            src.close()
        return {"patients": patients, "visits": visits}
    finally:
        _unlink_with_sidecars(tmp_path)

