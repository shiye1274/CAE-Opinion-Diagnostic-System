# -*- coding: utf-8 -*-
"""SQLite 访问层（只读）。v0.5 用 SQLite；并发/多人使用时平滑迁移 PostgreSQL，接口不变。"""
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List

from .config import DB_PATH


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with get_conn() as c:
        rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def query_one(sql: str, params: tuple = ()):
    rows = query(sql, params)
    return rows[0] if rows else None
