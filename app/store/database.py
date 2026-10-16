"""
app/store/database.py
SQLite persistence layer via stdlib sqlite3. All writes inside transactions.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path("data") / "rates.db"
_lock = threading.Lock()

# ── Schema ────────────────────────────────────────────────────────────────────
SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS rates (
    id                   TEXT PRIMARY KEY,
    is_derived_key       INTEGER NOT NULL DEFAULT 0,
    origin_raw           TEXT,
    origin_code          TEXT,
    origin_port_name     TEXT,
    origin_country       TEXT,
    origin_iso2          TEXT,
    destination_raw      TEXT,
    destination_code     TEXT,
    destination_port_name TEXT,
    destination_country  TEXT,
    destination_iso2     TEXT,
    shipment_mode        TEXT,
    container_name       TEXT,
    carrier_raw          TEXT,
    carrier_brand        TEXT,
    rate                 REAL,
    currency             TEXT,
    validity_start_date  TEXT,
    validity_end_date    TEXT,
    rate_type            TEXT,
    direction            TEXT,
    created_at           TEXT,
    updated_at           TEXT,
    source_status        TEXT,
    synced_at            TEXT NOT NULL,
    raw_json             TEXT
);

CREATE INDEX IF NOT EXISTS idx_rates_dest_iso2        ON rates(destination_iso2);
CREATE INDEX IF NOT EXISTS idx_rates_dest_code        ON rates(destination_code);
CREATE INDEX IF NOT EXISTS idx_rates_origin_code      ON rates(origin_code);
CREATE INDEX IF NOT EXISTS idx_rates_carrier_brand    ON rates(carrier_brand);
CREATE INDEX IF NOT EXISTS idx_rates_validity_end     ON rates(validity_end_date);
CREATE INDEX IF NOT EXISTS idx_rates_direction        ON rates(direction);
CREATE INDEX IF NOT EXISTS idx_rates_shipment_mode    ON rates(shipment_mode);

CREATE TABLE IF NOT EXISTS sync_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    status           TEXT NOT NULL,  -- running | success | failed
    records_fetched  INTEGER,
    records_stored   INTEGER,
    duplicates       INTEGER,
    error            TEXT,
    notes            TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_log_id  INTEGER NOT NULL REFERENCES sync_log(id),
    change_type  TEXT NOT NULL,  -- added | updated | removed
    rate_id      TEXT NOT NULL,
    field_name   TEXT,
    old_value    TEXT,
    new_value    TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist_countries (
    iso2 TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS watchlist_ports (
    code TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS watchlist_india_ports (
    code TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS india_port_overrides (
    code TEXT PRIMARY KEY,
    name TEXT,
    zone TEXT NOT NULL
);
"""


def init_db(path: Path | None = None) -> None:
    """Create data directory, database file and all tables if they don't exist."""
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(p)) as conn:
        conn.executescript(SCHEMA_SQL)


@contextmanager
def get_conn(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Thread-safe connection context manager with WAL mode."""
    p = path or DB_PATH
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Rates ─────────────────────────────────────────────────────────────────────

def upsert_rates(records: list[dict], synced_at: str, path: Path | None = None) -> None:
    """Upsert normalised rate records inside a single transaction."""
    if not records:
        return
    cols = [
        "id", "is_derived_key",
        "origin_raw", "origin_code", "origin_port_name", "origin_country", "origin_iso2",
        "destination_raw", "destination_code", "destination_port_name",
        "destination_country", "destination_iso2",
        "shipment_mode", "container_name",
        "carrier_raw", "carrier_brand",
        "rate", "currency",
        "validity_start_date", "validity_end_date",
        "rate_type", "direction",
        "created_at", "updated_at", "source_status",
        "synced_at", "raw_json",
    ]
    placeholders = ", ".join("?" * len(cols))
    sql = (
        f"INSERT OR REPLACE INTO rates ({', '.join(cols)}) VALUES ({placeholders})"
    )
    with get_conn(path) as conn:
        rows = []
        for r in records:
            rows.append(tuple(
                r.get(c) if c != "synced_at" else synced_at
                for c in cols
            ))
        conn.executemany(sql, rows)


def get_snapshot_of_ids(path: Path | None = None) -> dict[str, dict]:
    """Return {id: {validity_end_date, rate, currency, carrier_brand}} for diffing."""
    with get_conn(path) as conn:
        rows = conn.execute(
            "SELECT id, validity_end_date, rate, currency, carrier_brand, "
            "validity_start_date FROM rates"
        ).fetchall()
    return {r["id"]: dict(r) for r in rows}


def remove_rates_not_in(ids: set[str], path: Path | None = None) -> int:
    """Delete rates whose IDs are not in the given set. Returns deleted count."""
    if not ids:
        return 0
    with get_conn(path) as conn:
        before = conn.execute("SELECT COUNT(*) FROM rates").fetchone()[0]
        # SQLite has a limit on IN clause size; batch if needed
        id_list = list(ids)
        placeholders = ",".join("?" * len(id_list))
        conn.execute(f"DELETE FROM rates WHERE id NOT IN ({placeholders})", id_list)
        after = conn.execute("SELECT COUNT(*) FROM rates").fetchone()[0]
    return before - after


def query_rates(
    search: str = "",
    direction: str = "",
    mode: str = "",
    dest_country: str = "",
    dest_region: str = "",
    carrier: str = "",
    end_date_from: str = "",
    end_date_to: str = "",
    sort_by: str = "validity_end_date",
    sort_order: str = "asc",
    limit: int = 50,
    offset: int = 0,
    path: Path | None = None,
) -> tuple[list[dict], int]:
    """Filtered, sorted query. Returns (rows, total_count)."""
    from ..normalize.reference_data import COUNTRIES

    conditions = []
    params: list[Any] = []

    if search:
        s = f"%{search}%"
        conditions.append(
            "(origin_code LIKE ? OR destination_code LIKE ? OR "
            "origin_raw LIKE ? OR destination_raw LIKE ? OR "
            "carrier_brand LIKE ? OR id LIKE ?)"
        )
        params.extend([s, s, s, s, s, s])
    if direction:
        conditions.append("direction = ?")
        params.append(direction)
    if mode:
        conditions.append("LOWER(shipment_mode) = LOWER(?)")
        params.append(mode)
    if dest_country:
        conditions.append("destination_iso2 = ?")
        params.append(dest_country.upper())
    if dest_region:
        # Expand region to country codes
        codes = [k for k, v in COUNTRIES.items() if v["region"] == dest_region]
        if codes:
            placeholders = ",".join("?" * len(codes))
            conditions.append(f"destination_iso2 IN ({placeholders})")
            params.extend(codes)
        else:
            conditions.append("1=0")  # no match
    if carrier:
        conditions.append("LOWER(carrier_brand) LIKE LOWER(?)")
        params.append(f"%{carrier}%")
    if end_date_from:
        conditions.append("validity_end_date >= ?")
        params.append(end_date_from)
    if end_date_to:
        conditions.append("validity_end_date <= ?")
        params.append(end_date_to)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Allowed sort columns (whitelist against injection)
    allowed_sorts = {
        "validity_end_date", "validity_start_date", "rate", "carrier_brand",
        "direction", "origin_code", "destination_code", "synced_at", "updated_at",
    }
    col = sort_by if sort_by in allowed_sorts else "validity_end_date"
    order = "ASC" if sort_order.lower() != "desc" else "DESC"

    with get_conn(path) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM rates {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM rates {where} ORDER BY {col} {order} LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return [dict(r) for r in rows], total


def get_rate_by_id(rate_id: str, path: Path | None = None) -> dict | None:
    with get_conn(path) as conn:
        row = conn.execute("SELECT * FROM rates WHERE id = ?", (rate_id,)).fetchone()
    return dict(row) if row else None


def get_all_rates_raw(path: Path | None = None) -> list[dict]:
    """Fetch all rates (for coverage/alert calculations)."""
    with get_conn(path) as conn:
        rows = conn.execute("SELECT * FROM rates").fetchall()
    return [dict(r) for r in rows]


def count_rates(path: Path | None = None) -> int:
    with get_conn(path) as conn:
        return conn.execute("SELECT COUNT(*) FROM rates").fetchone()[0]


# ── Sync log ──────────────────────────────────────────────────────────────────

def start_sync_log(started_at: str, path: Path | None = None) -> int:
    with get_conn(path) as conn:
        cur = conn.execute(
            "INSERT INTO sync_log (started_at, status) VALUES (?, 'running')",
            (started_at,),
        )
        return cur.lastrowid


def finish_sync_log(
    log_id: int,
    finished_at: str,
    status: str,
    records_fetched: int = 0,
    records_stored: int = 0,
    duplicates: int = 0,
    error: str = "",
    notes: str = "",
    path: Path | None = None,
) -> None:
    with get_conn(path) as conn:
        conn.execute(
            """UPDATE sync_log SET finished_at=?, status=?, records_fetched=?,
               records_stored=?, duplicates=?, error=?, notes=?
               WHERE id=?""",
            (finished_at, status, records_fetched, records_stored,
             duplicates, error or None, notes or None, log_id),
        )


def get_sync_log(limit: int = 20, path: Path | None = None) -> list[dict]:
    with get_conn(path) as conn:
        rows = conn.execute(
            "SELECT * FROM sync_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_last_successful_sync(path: Path | None = None) -> dict | None:
    with get_conn(path) as conn:
        row = conn.execute(
            "SELECT * FROM sync_log WHERE status='success' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


# ── Snapshots ─────────────────────────────────────────────────────────────────

def save_snapshot_diffs(log_id: int, diffs: list[dict], created_at: str, path: Path | None = None) -> None:
    if not diffs:
        return
    with get_conn(path) as conn:
        conn.executemany(
            """INSERT INTO snapshots (sync_log_id, change_type, rate_id, field_name,
               old_value, new_value, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (log_id, d["change_type"], d["rate_id"],
                 d.get("field_name"), d.get("old_value"), d.get("new_value"), created_at)
                for d in diffs
            ],
        )


def get_history(limit: int = 200, path: Path | None = None) -> list[dict]:
    with get_conn(path) as conn:
        rows = conn.execute(
            """SELECT s.*, l.started_at as sync_started_at
               FROM snapshots s JOIN sync_log l ON s.sync_log_id = l.id
               ORDER BY s.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "", path: Path | None = None) -> str:
    with get_conn(path) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str, path: Path | None = None) -> None:
    with get_conn(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )


# ── Watchlists ────────────────────────────────────────────────────────────────

def _get_watchlist(table: str, col: str, path: Path | None = None) -> list[str]:
    with get_conn(path) as conn:
        rows = conn.execute(f"SELECT {col} FROM {table}").fetchall()
    return [r[0] for r in rows]


def _set_watchlist(table: str, col: str, items: list[str], path: Path | None = None) -> None:
    with get_conn(path) as conn:
        conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            f"INSERT OR IGNORE INTO {table} ({col}) VALUES (?)",
            [(i.upper(),) for i in items],
        )


def get_watched_countries(path: Path | None = None) -> list[str]:
    return _get_watchlist("watchlist_countries", "iso2", path)


def set_watched_countries(items: list[str], path: Path | None = None) -> None:
    _set_watchlist("watchlist_countries", "iso2", items, path)


def get_watched_ports(path: Path | None = None) -> list[str]:
    return _get_watchlist("watchlist_ports", "code", path)


def set_watched_ports(items: list[str], path: Path | None = None) -> None:
    _set_watchlist("watchlist_ports", "code", items, path)


def get_watched_india_ports(path: Path | None = None) -> list[str]:
    return _get_watchlist("watchlist_india_ports", "code", path)


def set_watched_india_ports(items: list[str], path: Path | None = None) -> None:
    _set_watchlist("watchlist_india_ports", "code", items, path)


def get_india_overrides(path: Path | None = None) -> dict[str, dict]:
    with get_conn(path) as conn:
        rows = conn.execute("SELECT code, name, zone FROM india_port_overrides").fetchall()
    return {r["code"]: {"name": r["name"], "zone": r["zone"]} for r in rows}


def set_india_override(code: str, zone: str, name: str | None = None, path: Path | None = None) -> None:
    with get_conn(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO india_port_overrides (code, name, zone) VALUES (?, ?, ?)",
            (code.upper(), name, zone),
        )


def seed_defaults(
    watched_countries: list[str],
    watched_ports: list[str],
    watched_india: list[str],
    path: Path | None = None,
) -> None:
    """Seed default watchlists only if they are currently empty."""
    if not get_watched_countries(path):
        set_watched_countries(watched_countries, path)
    if not get_watched_ports(path):
        set_watched_ports(watched_ports, path)
    if not get_watched_india_ports(path):
        set_watched_india_ports(watched_india, path)
