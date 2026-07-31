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
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
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
