"""Storage for saved diagrams and published (expiring) links.

One small `Database` wrapper runs the same SQL on:
  - SQLite      (default; a file, nothing to install)       DATABASE_URL unset
  - PostgreSQL  (e.g. Neon free tier)                       DATABASE_URL=postgresql://...?sslmode=require
SQL is written with `?` placeholders and converted for Postgres. Tables are created on first start.
"""
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .models import Diagram, DiagramMeta, DiagramOut

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS diagrams (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, data TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS shares (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, data TEXT NOT NULL,
        created_at DOUBLE PRECISION NOT NULL, expires_at DOUBLE PRECISION NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS shares_expires ON shares (expires_at)",
    # monitoring accounts (created only with the CLI, see auth.py / admin.py)
    """CREATE TABLE IF NOT EXISTS admin_users (
        username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS admin_sessions (
        token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL,
        expires_at DOUBLE PRECISION NOT NULL, ip TEXT)""",
]


class Database:
    def __init__(self, url: str):
        self.postgres = url.startswith(("postgres://", "postgresql://"))
        self.url = url
        if not self.postgres:
            self.path = url.removeprefix("sqlite:///")
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        for statement in SCHEMA:
            self.run(statement)

    @contextmanager
    def _connect(self):
        if self.postgres:
            import psycopg  # only needed for Postgres
            from psycopg.rows import dict_row
            with psycopg.connect(self.url, row_factory=dict_row, connect_timeout=10) as conn:
                yield conn
        else:
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            try:
                with conn:  # commits on success
                    yield conn
            finally:
                conn.close()

    def run(self, sql: str, params: tuple = ()) -> tuple[list[dict], int]:
        """Executes one statement; returns (rows as dicts, affected row count)."""
        if self.postgres:
            sql = sql.replace("?", "%s")
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()] if cur.description else []
            return rows, cur.rowcount


class DiagramRepo:
    def __init__(self, db: Database):
        self.db = db

    def list(self) -> list[DiagramMeta]:
        rows, _ = self.db.run("SELECT id, title, updated_at FROM diagrams ORDER BY updated_at DESC")
        return [DiagramMeta(**r) for r in rows]

    def get(self, diagram_id: str) -> DiagramOut | None:
        rows, _ = self.db.run("SELECT * FROM diagrams WHERE id = ?", (diagram_id,))
        if not rows:
            return None
        r = rows[0]
        return DiagramOut(id=r["id"], title=r["title"], updated_at=r["updated_at"],
                          diagram=Diagram.model_validate_json(r["data"]))

    def create(self, title: str, diagram: Diagram) -> DiagramOut:
        out = DiagramOut(id=uuid.uuid4().hex[:12], title=title, updated_at=time.time(), diagram=diagram)
        self.db.run("INSERT INTO diagrams (id, title, data, updated_at) VALUES (?, ?, ?, ?)",
                    (out.id, out.title, diagram.model_dump_json(), out.updated_at))
        return out

    def update(self, diagram_id: str, title: str, diagram: Diagram) -> DiagramOut | None:
        now = time.time()
        _, count = self.db.run("UPDATE diagrams SET title = ?, data = ?, updated_at = ? WHERE id = ?",
                               (title, diagram.model_dump_json(), now, diagram_id))
        return DiagramOut(id=diagram_id, title=title, updated_at=now, diagram=diagram) if count else None

    def delete(self, diagram_id: str) -> bool:
        _, count = self.db.run("DELETE FROM diagrams WHERE id = ?", (diagram_id,))
        return count > 0


class ShareRepo:
    """Read-only published copies that expire. Expired rows are purged whenever a new one is published."""

    def __init__(self, db: Database):
        self.db = db

    def create(self, title: str, data_json: str, ttl_seconds: int) -> dict:
        now = time.time()
        self.db.run("DELETE FROM shares WHERE expires_at < ?", (now,))
        share_id = secrets.token_urlsafe(9)  # 12 unguessable characters
        self.db.run("INSERT INTO shares (id, title, data, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                    (share_id, title, data_json, now, now + ttl_seconds))
        return {"id": share_id, "title": title, "expires_at": now + ttl_seconds}

    def get(self, share_id: str) -> dict | None:
        rows, _ = self.db.run("SELECT * FROM shares WHERE id = ?", (share_id,))
        if not rows:
            return None
        row = rows[0]
        if row["expires_at"] < time.time():
            self.db.run("DELETE FROM shares WHERE id = ?", (share_id,))
            return None
        return row
