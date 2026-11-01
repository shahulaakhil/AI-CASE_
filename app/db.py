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
CREATE TABLE IF NOT EXISTS judgment_documents (
    id              TEXT PRIMARY KEY,
    filename        TEXT NOT NULL DEFAULT '',
    embedding_model TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS judgment_chunks (
    document_id  TEXT NOT NULL,
    chunk_index  INTEGER NOT NULL,
    page_number  INTEGER,
    text         TEXT NOT NULL,
    embedding    TEXT NOT NULL,
    PRIMARY KEY (document_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_judgment_chunks_document ON judgment_chunks (document_id);
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
CREATE TABLE IF NOT EXISTS judgment_documents (
    id              TEXT PRIMARY KEY,
    filename        TEXT NOT NULL DEFAULT '',
    embedding_model TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS judgment_chunks (
    document_id  TEXT NOT NULL,
    chunk_index  INTEGER NOT NULL,
    page_number  INTEGER,
    text         TEXT NOT NULL,
    embedding    TEXT NOT NULL,
    PRIMARY KEY (document_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_judgment_chunks_document ON judgment_chunks (document_id);
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


def save_judgment(
    document_id: str,
    filename: str,
    embedding_model: str,
    chunks: list[dict[str, Any]],
) -> None:
    """Replace a judgment and all its chunks atomically."""
    init()
    from datetime import datetime, timezone

    created_at = datetime.now(timezone.utc).isoformat()
    with connection() as conn:
        if uses_postgres():
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM judgment_chunks WHERE document_id = %s", (document_id,))
                cursor.execute("DELETE FROM judgment_documents WHERE id = %s", (document_id,))
                cursor.execute(
                    "INSERT INTO judgment_documents (id, filename, embedding_model, created_at) "
                    "VALUES (%s, %s, %s, %s)",
                    (document_id, filename, embedding_model, created_at),
                )
                cursor.executemany(
                    "INSERT INTO judgment_chunks "
                    "(document_id, chunk_index, page_number, text, embedding) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [
                        (
                            document_id, chunk["chunk_index"], chunk["page_number"],
                            chunk["text"], json.dumps(chunk["embedding"]),
                        )
                        for chunk in chunks
                    ],
                )
        else:
            conn.execute("DELETE FROM judgment_chunks WHERE document_id = ?", (document_id,))
            conn.execute("DELETE FROM judgment_documents WHERE id = ?", (document_id,))
            conn.execute(
                "INSERT INTO judgment_documents (id, filename, embedding_model, created_at) "
                "VALUES (?, ?, ?, ?)",
                (document_id, filename, embedding_model, created_at),
            )
            conn.executemany(
                "INSERT INTO judgment_chunks "
                "(document_id, chunk_index, page_number, text, embedding) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        document_id, chunk["chunk_index"], chunk["page_number"],
                        chunk["text"], json.dumps(chunk["embedding"]),
                    )
                    for chunk in chunks
                ],
            )


def judgment(document_id: str) -> dict | None:
    rows = query(
        "SELECT id, filename, embedding_model, created_at "
        "FROM judgment_documents WHERE id = ?",
        (document_id,),
    )
    return rows[0] if rows else None


def judgment_chunks(document_id: str) -> list[dict]:
    rows = query(
        "SELECT chunk_index, page_number, text, embedding "
        "FROM judgment_chunks WHERE document_id = ? ORDER BY chunk_index",
        (document_id,),
    )
    for row in rows:
        row["embedding"] = json.loads(row["embedding"])
    return rows


def delete_judgment(document_id: str) -> bool:
    init()
    with connection() as conn:
        if uses_postgres():
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM judgment_chunks WHERE document_id = %s", (document_id,))
                cursor.execute("DELETE FROM judgment_documents WHERE id = %s", (document_id,))
                return cursor.rowcount > 0
        conn.execute("DELETE FROM judgment_chunks WHERE document_id = ?", (document_id,))
        cursor = conn.execute("DELETE FROM judgment_documents WHERE id = ?", (document_id,))
        return cursor.rowcount > 0


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
