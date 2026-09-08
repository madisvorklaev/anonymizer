"""SQLite storage for the mapping between a redaction ID and its
encrypted original content. This is what makes anonymization reversible."""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "redactions.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS redactions (
    redaction_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    page_num INTEGER NOT NULL,
    x0 REAL NOT NULL,
    y0 REAL NOT NULL,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    encrypted_snapshot BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_redaction(redaction_id: str, doc_id: str, page_num: int,
                      rect: tuple[float, float, float, float],
                      encrypted_snapshot: bytes) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO redactions "
            "(redaction_id, doc_id, page_num, x0, y0, x1, y1, encrypted_snapshot) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (redaction_id, doc_id, page_num, *rect, encrypted_snapshot),
        )


def get_redaction(redaction_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT redaction_id, doc_id, page_num, x0, y0, x1, y1, encrypted_snapshot "
            "FROM redactions WHERE redaction_id = ?",
            (redaction_id,),
        ).fetchone()
    return row
