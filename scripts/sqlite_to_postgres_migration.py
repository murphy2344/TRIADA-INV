#!/usr/bin/env python3
"""Inventory SQLite storage and rehearse a one-time import into TRIADA staging PostgreSQL.

Safe by default: this script only reads the SQLite file and prints row counts.
Use --apply only for the designated staging database after reviewing the inventory.
It refuses unknown SQLite tables, schema mismatches, and non-empty destination tables.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "published_news": (
        "id", "news_id", "title", "source", "url", "published_at", "post_type",
    ),
    "bot_stats": ("id", "date", "posts_count", "errors_count"),
    "recommendations": (
        "id", "ticker", "subject", "recommendation", "price_at_post",
        "posted_at", "checked", "correct", "price_after", "signal_id",
        "entry_time", "category", "confidence", "source", "horizon_hours",
        "pnl_percent", "max_drawdown_percent", "direction_correct",
    ),
    "bot_meta": ("key", "value"),
    "user_portfolios": (
        "id", "user_id", "ticker", "quantity", "avg_price", "added_at",
    ),
    "user_alerts": (
        "id", "user_id", "ticker", "alert_type", "target_price", "direction",
        "params", "created_at", "triggered",
    ),
    "user_watchlists": ("id", "user_id", "ticker", "added_at"),
}
IDENTITY_TABLES = (
    "published_news", "bot_stats", "recommendations", "user_portfolios",
    "user_alerts", "user_watchlists",
)
STAGING_HOST_MARKER = "dpg-dbfpnjvavr4c73fj05ug-a"
STAGING_DB_MARKER = "triada_inv_postgres_staging"


def open_sqlite_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(
            f"SQLite file was not found at {path}. Do not create a new empty file "
            "and mistake it for the running bot's source database."
        )
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def inspect_source(conn: sqlite3.Connection) -> tuple[dict[str, int], list[str]]:
    existing = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    unknown = sorted(existing - set(TABLE_COLUMNS))
    report: dict[str, int] = {}
    problems: list[str] = []

    for table, expected_columns in TABLE_COLUMNS.items():
        if table not in existing:
            report[table] = 0
            problems.append(f"missing expected table: {table}")
            continue
        actual_columns = {
            row["name"] for row in conn.execute(f'PRAGMA table_info("{table}")')
        }
        missing = sorted(set(expected_columns) - actual_columns)
        if missing:
            problems.append(f"{table} missing columns: {', '.join(missing)}")
        report[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])

    if unknown:
        problems.append(f"unmapped tables: {', '.join(unknown)}")
    return report, problems


def print_inventory(path: Path, report: dict[str, int], problems: list[str]) -> None:
    print(f"SQLite source: {path.resolve()}")
    print("Table inventory (counts only; no user rows are printed):")
    for table, count in report.items():
        print(f"  {table}: {count}")
    print(f"TOTAL ROWS: {sum(report.values())}")
    if problems:
        print("SOURCE REVIEW REQUIRED:")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print("Source schema matches the seven known storage tables.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(os.getenv("SQLITE_PATH", "data/bot.db")),
        help="path to the existing SQLite file (default: SQLITE_PATH or data/bot.db)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="copy data into the designated TRIADA staging PostgreSQL database",
    )
    return parser.parse_args()


def require_staging_url(url: str) -> None:
    if not url.startswith(("postgres://", "postgresql://")):
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL.")
    if STAGING_HOST_MARKER not in url or STAGING_DB_MARKER not in url:
        raise RuntimeError(
            "This rehearsal script only writes to triada_inv_postgres_staging. "
            "The target URL did not match the designated staging database."
        )


def read_source_rows(
    conn: sqlite3.Connection, table: str
) -> list[tuple[Any, ...]]:
    columns = TABLE_COLUMNS[table]
    sql_columns = ", ".join(f'"{column}"' for column in columns)
    rows = conn.execute(f'SELECT {sql_columns} FROM "{table}" ORDER BY 1').fetchall()
    return [tuple(row[column] for column in columns) for row in rows]


def run_import(
    source_conn: sqlite3.Connection,
    source_report: dict[str, int],
    migration_path: Path,
    database_url: str,
) -> None:
    require_staging_url(database_url)
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "psycopg is required for --apply. Install project requirements in the "
            "environment that has access to both the source file and staging DB."
        ) from exc

    migration_sql = migration_path.read_text(encoding="utf-8")
    statements = [
        line.strip()
        for line in migration_sql.split(";")
        if line.strip() and not all(
            not part.strip() or part.lstrip().startswith("--")
            for part in line.splitlines()
        )
    ]

    # A single transaction makes the copy all-or-nothing.
    with psycopg.connect(database_url, sslmode="require", connect_timeout=10) as pg:
        with pg.transaction():
            with pg.cursor() as cur:
                for statement in statements:
                    # Strip full-line comments while retaining SQL itself.
                    cleaned = "\n".join(
                        line for line in statement.splitlines()
                        if not line.lstrip().startswith("--")
                    ).strip()
                    if cleaned:
                        cur.execute(cleaned)

                destination_counts: dict[str, int] = {}
                for table in TABLE_COLUMNS:
                    cur.execute(f'SELECT COUNT(*) FROM public."{table}"')
                    destination_counts[table] = int(cur.fetchone()[0])
                nonempty = {
                    table: count for table, count in destination_counts.items() if count
                }
                if nonempty:
                    raise RuntimeError(
                        "Staging destination is not empty; refusing to mix datasets. "
                        f"Non-empty tables: {nonempty}"
                    )

                for table, columns in TABLE_COLUMNS.items():
                    rows = read_source_rows(source_conn, table)
                    if not rows:
                        continue
                    column_sql = ", ".join(f'"{column}"' for column in columns)
                    placeholders = ", ".join(["%s"] * len(columns))
                    insert_sql = (
                        f'INSERT INTO public."{table}" ({column_sql}) '
                        f"VALUES ({placeholders})"
                    )
                    cur.executemany(insert_sql, rows)

                for table in IDENTITY_TABLES:
                    cur.execute(
                        f"SELECT setval(pg_get_serial_sequence('public.{table}', 'id'), "
                        f"(SELECT COALESCE(MAX(id), 1) FROM public.{table}), "
                        f"EXISTS (SELECT 1 FROM public.{table}))"
                    )

                verification: dict[str, int] = {}
                for table, expected in source_report.items():
                    cur.execute(f'SELECT COUNT(*) FROM public."{table}"')
                    actual = int(cur.fetchone()[0])
                    verification[table] = actual
                    if actual != expected:
                        raise RuntimeError(
                            f"Count mismatch for {table}: source={expected}, target={actual}"
                        )

        # Connection context commits only after the transaction succeeds.
    print("IMPORT PASS: all seven tables copied and row counts verified.")
    for table, count in source_report.items():
        print(f"  {table}: {count}")
    print(f"TOTAL ROWS VERIFIED: {sum(source_report.values())}")


def main() -> int:
    args = parse_args()
    migration_path = Path(__file__).resolve().parents[1] / "migrations" / "001_initial_postgres.sql"
    if not migration_path.is_file():
        print(f"ERROR: migration schema not found at {migration_path}", file=sys.stderr)
        return 2

    try:
        with open_sqlite_readonly(args.source) as source:
            report, problems = inspect_source(source)
            print_inventory(args.source, report, problems)

            # Inventory is always read-only. Import is explicitly opt-in and validates
            # the complete source schema before making any destination changes.
            if args.apply:
                if problems:
                    print("ERROR: cannot import until source schema issues are resolved.", file=sys.stderr)
                    return 2
                url = os.getenv("DATABASE_URL", "").strip()
                if not url:
                    print("ERROR: set DATABASE_URL to the staging URL in the execution environment.", file=sys.stderr)
                    return 2
                run_import(source, report, migration_path, url)
            else:
                print("DRY RUN ONLY: PostgreSQL was not modified.")
                print("To import, review the inventory, set DATABASE_URL to the staging URL, and rerun with --apply.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
