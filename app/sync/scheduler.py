"""
app/sync/scheduler.py
Sync engine: fetch → normalise → diff → persist → log.
APScheduler with asyncio lock (no concurrent syncs).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..client.zipaworld import ZipaworldClient, ZipaworldAPIError
from ..config.settings import Settings
from ..normalize.normaliser import normalise_all
from ..store import database as db

logger = logging.getLogger(__name__)

_sync_lock = asyncio.Lock()
_scheduler: AsyncIOScheduler | None = None

# Track sync state (in-memory only)
_sync_state: dict = {
    "running": False,
    "lastSyncAt": None,
    "lastSyncStatus": None,   # "success" | "failed" | None
    "lastError": None,
    "isLive": False,          # True only after a real successful sync
}


def get_sync_state() -> dict:
    return dict(_sync_state)


async def run_sync(settings: Settings, db_path: Path | None = None, is_demo: bool = False) -> dict:
    """
    Execute one sync cycle:
    1. Fetch all pages from Zipaworld (or load demo data)
    2. Normalise
    3. Diff against stored snapshot
    4. Upsert + remove stale records
    5. Log result
    Returns summary dict.
    """
    global _sync_state

    if _sync_state["running"]:
        return {"status": "skipped", "reason": "sync_already_running"}

    async with _sync_lock:
        _sync_state["running"] = True
        now_iso = datetime.now(timezone.utc).isoformat()
        log_id = db.start_sync_log(now_iso, db_path)

        try:
            field_map = settings.load_field_map()

            # ── Fetch ─────────────────────────────────────────────────────
            if is_demo:
                from ..api.demo_data import generate_demo_rates
                raw_items = generate_demo_rates()
                logger.info("DEMO mode: loaded %d synthetic rates", len(raw_items))
            else:
                client = ZipaworldClient(settings)
                raw_items = await client.fetch_all_rates()
                logger.info("Fetched %d raw items from API", len(raw_items))

            # Guard: treat 0 records as failure if we have stored data
            stored_count = db.count_rates(db_path)
            if not raw_items and stored_count > 0:
                msg = "API returned 0 records while data is stored – treating as failure"
                logger.error(msg)
                db.finish_sync_log(log_id, datetime.now(timezone.utc).isoformat(),
                                   "failed", error=msg, path=db_path)
                _sync_state.update({"running": False, "lastSyncStatus": "failed",
                                    "lastError": msg})
                return {"status": "failed", "reason": msg}

            # ── Normalise ─────────────────────────────────────────────────
            records, duplicates = normalise_all(raw_items, field_map)
            logger.info("Normalised %d records (%d duplicates removed)", len(records), duplicates)

            # ── Diff snapshot ─────────────────────────────────────────────
            old_snapshot = db.get_snapshot_of_ids(db_path)
            new_ids = {r["id"] for r in records}
            diffs: list[dict] = []

            for r in records:
                rid = r["id"]
                if rid not in old_snapshot:
                    diffs.append({"change_type": "added", "rate_id": rid})
                else:
                    old = old_snapshot[rid]
                    for field in ("validity_end_date", "rate", "currency", "carrier_brand", "validity_start_date"):
                        ov = str(old.get(field) or "")
                        nv = str(r.get(field) or "")
                        if ov != nv:
                            diffs.append({
                                "change_type": "updated",
                                "rate_id": rid,
                                "field_name": field,
                                "old_value": ov,
                                "new_value": nv,
                            })

            for old_id in old_snapshot:
                if old_id not in new_ids:
                    diffs.append({"change_type": "removed", "rate_id": old_id})

            # ── Persist ───────────────────────────────────────────────────
            db.upsert_rates(records, now_iso, db_path)
            removed = db.remove_rates_not_in(new_ids, db_path)
            diff_ts = datetime.now(timezone.utc).isoformat()
            db.save_snapshot_diffs(log_id, diffs, diff_ts, db_path)

            # ── Finish log ────────────────────────────────────────────────
            db.finish_sync_log(
                log_id,
                datetime.now(timezone.utc).isoformat(),
                "success",
                records_fetched=len(raw_items),
                records_stored=len(records),
                duplicates=duplicates,
                notes=f"Removed {removed} stale records. {len(diffs)} changes.",
                path=db_path,
            )

            _sync_state.update({
                "running": False,
                "lastSyncAt": now_iso,
                "lastSyncStatus": "success",
                "lastError": None,
                "isLive": not is_demo,
            })
            logger.info("Sync complete: %d records stored, %d diffs", len(records), len(diffs))
            return {
                "status": "success",
                "recordsFetched": len(raw_items),
                "recordsStored": len(records),
                "duplicates": duplicates,
                "diffs": len(diffs),
                "removedStale": removed,
            }

        except ZipaworldAPIError as exc:
            msg = str(exc)  # never contains credentials
            logger.error("Sync failed (API error): %s", msg)
            db.finish_sync_log(log_id, datetime.now(timezone.utc).isoformat(),
                               "failed", error=msg, path=db_path)
            _sync_state.update({"running": False, "lastSyncStatus": "failed",
                                "lastError": msg})
            return {"status": "failed", "reason": msg}

        except Exception as exc:
            msg = f"Unexpected sync error: {type(exc).__name__}"
            logger.exception("Sync failed unexpectedly")
            db.finish_sync_log(log_id, datetime.now(timezone.utc).isoformat(),
                               "failed", error=msg, path=db_path)
            _sync_state.update({"running": False, "lastSyncStatus": "failed",
                                "lastError": msg})
            return {"status": "failed", "reason": msg}

        finally:
            _sync_state["running"] = False


def start_scheduler(settings: Settings, db_path: Path | None = None) -> None:
    """Start APScheduler with the configured interval. No-op if interval == 0."""
    global _scheduler
    interval = settings.radar_sync_interval
    if interval <= 0:
        logger.info("Auto-sync disabled (RADAR_SYNC_INTERVAL=0)")
        return

    is_demo = settings.is_demo

    async def _job():
        await run_sync(settings, db_path, is_demo=is_demo)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_job, "interval", minutes=interval, id="auto_sync",
                       max_instances=1, coalesce=True)
    _scheduler.start()
    logger.info("Auto-sync scheduler started: every %d minutes", interval)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
