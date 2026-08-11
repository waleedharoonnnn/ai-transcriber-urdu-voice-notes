import os
from contextlib import contextmanager
from typing import Iterator

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

_pool: SimpleConnectionPool | None = None


def _get_pool() -> SimpleConnectionPool:
    global _pool
    if _pool is None:
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL is not set.")
        _pool = SimpleConnectionPool(1, 10, dsn=dsn)
    return _pool


@contextmanager
def get_cursor(commit: bool = False) -> Iterator["psycopg2.extras.RealDictCursor"]:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def fetch_one(query: str, params: tuple = ()) -> dict | None:
    with get_cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(query: str, params: tuple = ()) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute(query, params)


def execute_returning(query: str, params: tuple = ()) -> list[dict]:
    with get_cursor(commit=True) as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]
