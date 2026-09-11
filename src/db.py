"""
SQLite layer: schema definition, init, and CRUD helpers for claims + audit log.

This is your SQL talking point for interviews — two tables, a clean
one-to-many relationship (one claim -> many audit events), and queries
you should be able to write live: joins, aggregates, filtering by status.

Run: python src/db.py   (creates/resets claims.db and loads claims.csv into it)
"""

import csv
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "claims.db"
CSV_PATH = Path(__file__).parent.parent / "data" / "claims.csv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id            TEXT PRIMARY KEY,
    customer_id         TEXT NOT NULL,
    policy_type         TEXT NOT NULL,
    claim_amount        REAL NOT NULL,
    date_filed          TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'Filed',
    claim_description   TEXT,
    customer_name        TEXT,     -- PII: redact before ever logging/displaying in audit trail
    customer_phone       TEXT,     -- PII: redact before ever logging/displaying in audit trail
    predicted_type       TEXT,     -- filled by classify.py
    urgency               TEXT,     -- filled by classify.py: Low / Medium / High
    classification_confidence REAL, -- filled by classify.py, 0-1
    summary               TEXT,     -- filled by classify.py
    routing_decision      TEXT      -- filled by routing.py: Auto-Approve / Escalate / Request-Info
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id     TEXT NOT NULL,
    event_type   TEXT NOT NULL,     -- e.g. 'classification', 'routing_decision', 'rag_query'
    event_detail TEXT,              -- PII-redacted before insert — see src/governance.py
    confidence   REAL,
    timestamp    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (claim_id) REFERENCES claims (claim_id)
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(reset: bool = False):
    if reset and DB_PATH.exists():
        DB_PATH.unlink()

    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"DB initialized at {DB_PATH}")


def load_claims_from_csv():
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"{CSV_PATH} not found — run `python data/generate_data.py` first."
        )

    conn = get_connection()
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    conn.executemany(
        """
        INSERT OR REPLACE INTO claims
            (claim_id, customer_id, policy_type, claim_amount, date_filed,
             status, claim_description, customer_name, customer_phone)
        VALUES (:claim_id, :customer_id, :policy_type, :claim_amount, :date_filed,
                :status, :claim_description, :customer_name, :customer_phone)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    print(f"Loaded {len(rows)} claims into {DB_PATH}")


def log_audit_event(claim_id: str, event_type: str, event_detail: str, confidence: float | None = None):
    """Insert an audit event. `event_detail` should already be PII-redacted
    by the caller (see src/governance.py) before it reaches this function."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO audit_log (claim_id, event_type, event_detail, confidence) VALUES (?, ?, ?, ?)",
        (claim_id, event_type, event_detail, confidence),
    )
    conn.commit()
    conn.close()


def get_all_claims():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM claims ORDER BY date_filed DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_claim(claim_id: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_claim_ai_fields(claim_id: str, **fields):
    """Update classification/summary/routing fields on a claim after pipeline runs."""
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [claim_id]

    conn = get_connection()
    conn.execute(f"UPDATE claims SET {set_clause} WHERE claim_id = ?", values)
    conn.commit()
    conn.close()


# --- Example queries worth having ready for a live SQL interview question ---

def example_queries():
    conn = get_connection()

    # 1. Claims count and avg amount per policy type (GROUP BY + aggregate)
    print(
        conn.execute(
            """
            SELECT policy_type, COUNT(*) AS num_claims, ROUND(AVG(claim_amount), 2) AS avg_amount
            FROM claims
            GROUP BY policy_type
            ORDER BY num_claims DESC
            """
        ).fetchall()
    )

    # 2. Claims with no classification yet (NULL handling, relevant to COALESCE-style questions)
    print(
        conn.execute(
            "SELECT claim_id, COALESCE(predicted_type, 'UNCLASSIFIED') AS predicted_type FROM claims"
        ).fetchall()
    )

    # 3. Join claims to their audit trail
    print(
        conn.execute(
            """
            SELECT c.claim_id, c.policy_type, a.event_type, a.timestamp
            FROM claims c
            JOIN audit_log a ON c.claim_id = a.claim_id
            ORDER BY a.timestamp DESC
            LIMIT 10
            """
        ).fetchall()
    )

    conn.close()


if __name__ == "__main__":
    init_db(reset=True)
    load_claims_from_csv()
