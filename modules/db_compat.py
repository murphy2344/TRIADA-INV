"""Small async DB compatibility layer for SQLite and PostgreSQL.

Existing storage queries use aiosqlite-style '?' placeholders and cursor context
managers. This adapter keeps that API while PostgreSQL is introduced gradually.
"""
from __future__ import annotations

import os
import re
from typing import Any

import aiosqlite

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def is_postgres() -> bool:
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))


def connect(sqlite_path: str):
    if is_postgres():
        return _PostgresConnection(DATABASE_URL)
    return aiosqlite.connect(sqlite_path)


def _translate(sql: str, params: tuple[Any, ...] | None) -> tuple[str, tuple[Any, ...] | None]:
    query = sql.strip()
    # SQLite convenience syntax.
    if query.upper().startswith("INSERT OR IGNORE INTO"):
        query = re.sub(r"^INSERT OR IGNORE INTO", "INSERT INTO", query, flags=re.I)
        query = query.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    # Translate the SQLite datetime expressions used by modules/storage.py.
    # Do this before converting qmark parameters to psycopg placeholders.
    query = re.sub(r"datetime\(\s*'now'\s*\)", "CURRENT_TIMESTAMP", query, flags=re.I)
    query = re.sub(
        r"datetime\(\s*'now'\s*,\s*\?\s*\|\|\s*' hours'\s*\)",
        "(CURRENT_TIMESTAMP + (%s::text || ' hours')::interval)", query, flags=re.I
    )
    query = re.sub(
        r"datetime\(\s*'now'\s*,\s*\?\s*\|\|\s*' days'\s*\)",
        "(CURRENT_TIMESTAMP + (%s::text || ' days')::interval)", query, flags=re.I
    )
    query = re.sub(
        r"datetime\(\s*posted_at\s*,\s*'\+'\s*\|\|\s*COALESCE\(horizon_hours,\s*24\)\s*\|\|\s*' hours'\s*\)",
        "(posted_at + COALESCE(horizon_hours, 24) * INTERVAL '1 hour')", query, flags=re.I
    )
    # Replace remaining qmark placeholders after rewriting datetime expressions.
    query = query.replace("?", "%s")
    return query, params


class _Cursor:
    def __init__(self, connection: "_PostgresConnection", sql: str, params: tuple[Any, ...] | None):
        self.connection = connection
        self.sql = sql
        self.params = params
        self.cursor = None
        self._executed = False

    async def _run(self):
        if not self._executed:
            query, params = _translate(self.sql, self.params)
            self.cursor = await self.connection.raw.execute(query, params or ())
            self._executed = True
        return self

    def __await__(self):
        return self._run().__await__()

    async def __aenter__(self):
        return await self._run()

    async def __aexit__(self, exc_type, exc, tb):
        if self.cursor is not None:
            await self.cursor.close()

    async def fetchone(self):
        await self._run()
        row = await self.cursor.fetchone()
        return tuple(row) if row is not None else None

    async def fetchall(self):
        await self._run()
        return [tuple(row) for row in await self.cursor.fetchall()]


class _PostgresConnection:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.raw = None

    async def __aenter__(self):
        import psycopg
        from psycopg.rows import tuple_row
        self.raw = await psycopg.AsyncConnection.connect(
            self.dsn, row_factory=tuple_row, sslmode="require", connect_timeout=10
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.raw is not None:
            if exc_type:
                await self.raw.rollback()
            else:
                await self.raw.commit()
            await self.raw.close()

    def execute(self, sql: str, parameters: tuple[Any, ...] | None = None):
        return _Cursor(self, sql, parameters)

    async def commit(self):
        await self.raw.commit()
