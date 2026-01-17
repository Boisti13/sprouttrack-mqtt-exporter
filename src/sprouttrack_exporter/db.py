from __future__ import annotations

import sqlite3
from typing import Optional, Sequence, Tuple


def connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def query_one(cur: sqlite3.Cursor, sql: str, args: Sequence = ()) -> Optional[sqlite3.Row]:
    cur.execute(sql, args)
    return cur.fetchone()
