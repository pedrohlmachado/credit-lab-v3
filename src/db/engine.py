"""Factory de conexao SQLite + aplicacao do schema.

Unico ponto do projeto que abre uma conexao sqlite3 diretamente. Repository
e ingest sempre passam por get_connection().
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "credit_lab.db"
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or _DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def get_db_path() -> Path:
    return _DB_PATH
