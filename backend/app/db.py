"""Small database layer: PostgreSQL when DATABASE_URL is set, SQLite otherwise.

Holds only the human-in-the-loop state (warnings, bulletins, data reviews,
feedback) and the audit log of agent actions. Market data stays in the pipeline
output files.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from functools import lru_cache

from backend.app.settings import DATABASE_URL, SQLITE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS warnings (
    id TEXT PRIMARY KEY, crop TEXT, market TEXT, type TEXT, date TEXT, magnitude REAL,
    en TEXT, te TEXT, status TEXT DEFAULT 'pending', reviewed_by TEXT, reviewed_at TEXT, note TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS bulletins (
    id {serial}, week_start TEXT, status TEXT, title_en TEXT, title_te TEXT, body_en TEXT, body_te TEXT,
    created_at TEXT, created_by TEXT, reviewed_by TEXT, reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS quality_reviews (
    record_id TEXT PRIMARY KEY, decision TEXT, reviewed_by TEXT, reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id {serial}, ts TEXT, agent TEXT, action TEXT, detail TEXT, actor TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
    id {serial}, ts TEXT, question TEXT, answer TEXT, helpful INTEGER, correction TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class DB:
    def __init__(self) -> None:
        self.kind = "postgres" if DATABASE_URL else "sqlite"
        self._lock = threading.Lock()
        if self.kind == "sqlite":
            self._conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        serial = "SERIAL PRIMARY KEY" if self.kind == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
        for stmt in SCHEMA.format(serial=serial).split(";"):
            if stmt.strip():
                self.execute(stmt)

    def _pg(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10, autocommit=True)

    def execute(self, sql: str, params: tuple = ()) -> int | None:
        """Run a statement; returns the new id for INSERT ... RETURNING id."""
        if self.kind == "postgres":
            with self._pg() as conn:
                cur = conn.execute(sql.replace("?", "%s"), params)
                if cur.description:
                    row = cur.fetchone()
                    return row["id"] if row else None
                return None
        with self._lock:
            cur = self._conn.execute(sql.replace(" RETURNING id", ""), params)
            self._conn.commit()
            return cur.lastrowid

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        if self.kind == "postgres":
            with self._pg() as conn:
                return [dict(r) for r in conn.execute(sql.replace("?", "%s"), params).fetchall()]
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def audit(self, agent: str, action: str, detail: str, actor: str = "system") -> None:
        try:
            self.execute("INSERT INTO audit_log (ts, agent, action, detail, actor) VALUES (?, ?, ?, ?, ?)",
                         (now(), agent, action, detail[:1000], actor))
        except Exception as exc:  # logging must never break a farmer's request
            print(f"audit failed: {exc}")


@lru_cache(maxsize=1)
def get_db() -> DB:
    return DB()
