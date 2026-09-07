"""Storage layer for the case tracker.

SQLite is the default and needs nothing configured. If DATABASE_URL is set to a
Postgres URL the same schema is used there instead, which makes the data survive
a Render redeploy. Both back ends speak the same small API.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from . import settings

_lock = threading.Lock()
_initialised = False


def uses_postgres() -> bool:
    url = settings.DATABASE_URL or ""
    return url.startswith("postgres://") or url.startswith("postgresql://")


def backend_name() -> str:
    return "postgres" if uses_postgres() else "sqlite"


def _postgres_url() -> str:
    url = settings.DATABASE_URL or ""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id            TEXT PRIMARY KEY,
    case_name     TEXT NOT NULL,
    court         TEXT NOT NULL DEFAULT '',
    case_number   TEXT NOT NULL DEFAULT '',
    cnr_number    TEXT NOT NULL DEFAULT '',
    parties       TEXT NOT NULL DEFAULT '',
    next_date     TEXT NOT NULL DEFAULT '',
    stage         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'Pending',
    priority      TEXT NOT NULL DEFAULT 'Normal',
    notes         TEXT NOT NULL DEFAULT '',
    hearings      TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cases_next_date ON cases (next_date);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id            TEXT PRIMARY KEY,
    case_name     TEXT NOT NULL,
    court         TEXT NOT NULL DEFAULT '',
    case_number   TEXT NOT NULL DEFAULT '',
    cnr_number    TEXT NOT NULL DEFAULT '',
    parties       TEXT NOT NULL DEFAULT '',
    next_date     TEXT NOT NULL DEFAULT '',
    stage         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'Pending',
    priority      TEXT NOT NULL DEFAULT 'Normal',
    notes         TEXT NOT NULL DEFAULT '',
    hearings      TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cases_next_date ON cases (next_date);
"""

COLUMNS = (
    "id", "case_name", "court", "case_number", "cnr_number", "parties", "next_date",
    "stage", "status", "priority", "notes", "hearings", "created_at", "updated_at",
)


@contextmanager
def connection() -> Iterator[Any]:
    if uses_postgres():
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(_postgres_url(), row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        settings.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(settings.SQLITE_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init() -> None:
    global _initialised
    with _lock:
        if _initialised:
            return
        with connection() as conn:
            if uses_postgres():
                with conn.cursor() as cursor:
                    for statement in POSTGRES_SCHEMA.strip().split(";"):
                        if statement.strip():
                            cursor.execute(statement)
            else:
                conn.executescript(SQLITE_SCHEMA)
        _initialised = True


def _placeholder(index: int) -> str:
    return "%s" if uses_postgres() else "?"


def query(sql: str, params: tuple = ()) -> list[dict]:
    init()
    if uses_postgres():
        sql = sql.replace("?", "%s")
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
    with connection() as conn:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def execute(sql: str, params: tuple = ()) -> int:
    init()
    if uses_postgres():
        sql = sql.replace("?", "%s")
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount
    with connection() as conn:
        cursor = conn.execute(sql, params)
        return cursor.rowcount


def row_to_case(row: dict) -> dict:
    case = dict(row)
    raw = case.get("hearings") or "[]"
    if isinstance(raw, str):
        try:
            case["hearings"] = json.loads(raw)
        except json.JSONDecodeError:
            case["hearings"] = []
    elif not isinstance(raw, list):
        case["hearings"] = []
    return case


def health() -> dict[str, Any]:
    try:
        init()
        count = query("SELECT COUNT(*) AS total FROM cases")[0]["total"]
        return {"backend": backend_name(), "ok": True, "cases": int(count)}
    except Exception as exc:  # noqa: BLE001 - health must never raise
        return {"backend": backend_name(), "ok": False, "error": str(exc)[:200]}
