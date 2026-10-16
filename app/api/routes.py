"""
app/api/routes.py
All FastAPI routes. Secrets never appear in responses or logs.
"""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from ..config.settings import Settings, get_settings
from ..coverage.analytics import (
    country_coverage, expiry_alerts, india_board, overview_kpis, port_coverage,
)
from ..expiry.expiry import enrich_rate
from ..normalize.reference_data import (
    COUNTRIES, DEFAULT_WATCHED_COUNTRIES, DEFAULT_WATCHED_INDIA, DEFAULT_WATCHED_PORTS,
    INDIA_PORTS, is_indian_port,
)
from ..store import database as db
from ..sync.scheduler import get_sync_state, run_sync

router = APIRouter(prefix="/api")

# ── Rate limiting for /sync/now ───────────────────────────────────────────────
_last_manual_sync: float = 0.0
SYNC_COOLDOWN = 30  # seconds


def _settings() -> Settings:
    return get_settings()


# ── Auth helper ───────────────────────────────────────────────────────────────
def _check_admin(request: Request, settings: Settings) -> None:
    """Raise 403 if admin token is configured and the request doesn't supply it."""
    token = settings.radar_admin_token
    if not token:
        return
    provided = request.headers.get("X-Admin-Token", "")
    if provided != token:
        raise HTTPException(status_code=403, detail="Admin token required")


# ── Escape helper (prevent XSS from API-derived text) ────────────────────────
def _esc(v) -> str | None:
    if v is None:
        return None
    s = str(v)
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _esc_rate(r: dict) -> dict:
    """Escape all string fields in a rate record."""
    safe_fields = {
        "origin_raw", "destination_raw", "origin_port_name", "destination_port_name",
        "origin_country", "destination_country", "carrier_raw", "carrier_brand",
        "shipment_mode", "container_name", "direction", "source_status",
    }
    return {k: (_esc(v) if k in safe_fields else v) for k, v in r.items()}


# ── Config ────────────────────────────────────────────────────────────────────
@router.get("/config")
async def get_config(settings: Settings = Depends(_settings)):
    return settings.public_dict()


# ── Overview ──────────────────────────────────────────────────────────────────
@router.get("/overview")
async def get_overview(settings: Settings = Depends(_settings)):
    all_rates = db.get_all_rates_raw()
    watched_c = db.get_watched_countries() or DEFAULT_WATCHED_COUNTRIES
    watched_p = db.get_watched_ports()     or DEFAULT_WATCHED_PORTS
    kpis = overview_kpis(
        all_rates, watched_c, watched_p,
        settings.radar_min_carriers, settings.radar_expiry_threshold, settings.radar_timezone,
    )
    sync = get_sync_state()
    return {**kpis, "syncState": sync, "isDemo": settings.is_demo}


# ── Rates table ───────────────────────────────────────────────────────────────
@router.get("/rates")
async def list_rates(
    search: str = Query(""),
    direction: str = Query(""),
    mode: str = Query(""),
    dest_country: str = Query(""),
    dest_region: str = Query(""),
    carrier: str = Query(""),
    status: str = Query(""),
    end_date_from: str = Query(""),
    end_date_to: str = Query(""),
    sort_by: str = Query("validity_end_date"),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    settings: Settings = Depends(_settings),
):
    offset = (page - 1) * page_size
    rows, total = db.query_rates(
        search=search, direction=direction, mode=mode,
        dest_country=dest_country, dest_region=dest_region,
        carrier=carrier,
        end_date_from=end_date_from, end_date_to=end_date_to,
        sort_by=sort_by, sort_order=sort_order,
        limit=page_size, offset=offset,
    )

    enriched = []
    for r in rows:
        e = enrich_rate(r, settings.radar_expiry_threshold, settings.radar_timezone)
        # Filter by computed status if requested
        if status and e["expiry"]["status"] != status:
            continue
        enriched.append(_esc_rate(e))

    # Recalculate total when status-filtering (rough: skip re-query for now)
    # Note: for large datasets a cached status column would be better;
    # acceptable for a prototype given typical rate-dataset sizes.
    return {
        "items": enriched,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/rates/{rate_id}")
async def get_rate(rate_id: str, settings: Settings = Depends(_settings)):
    row = db.get_rate_by_id(rate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Rate not found")
    enriched = enrich_rate(row, settings.radar_expiry_threshold, settings.radar_timezone)
    return _esc_rate(enriched)


# ── Coverage ──────────────────────────────────────────────────────────────────
@router.get("/coverage/countries")
async def get_country_coverage(settings: Settings = Depends(_settings)):
    all_rates = db.get_all_rates_raw()
    watched = db.get_watched_countries() or DEFAULT_WATCHED_COUNTRIES
    return country_coverage(
        all_rates, watched,
        settings.radar_min_carriers, settings.radar_expiry_threshold, settings.radar_timezone,
    )


@router.get("/coverage/ports")
async def get_port_coverage(settings: Settings = Depends(_settings)):
    all_rates = db.get_all_rates_raw()
    watched = db.get_watched_ports() or DEFAULT_WATCHED_PORTS
    return port_coverage(
        all_rates, watched,
        settings.radar_min_carriers, settings.radar_expiry_threshold, settings.radar_timezone,
    )


@router.get("/coverage/india")
async def get_india_coverage(settings: Settings = Depends(_settings)):
    all_rates = db.get_all_rates_raw()
    watched   = db.get_watched_india_ports() or DEFAULT_WATCHED_INDIA
    overrides = db.get_india_overrides()
    return india_board(
        all_rates, watched, overrides,
        settings.radar_min_carriers, settings.radar_expiry_threshold, settings.radar_timezone,
    )


# ── Alerts ────────────────────────────────────────────────────────────────────
@router.get("/alerts")
async def get_alerts(settings: Settings = Depends(_settings)):
    all_rates = db.get_all_rates_raw()
    watched_c = db.get_watched_countries() or DEFAULT_WATCHED_COUNTRIES
    watched_p = db.get_watched_ports()     or DEFAULT_WATCHED_PORTS
    return expiry_alerts(
        all_rates, watched_c, watched_p,
        settings.radar_min_carriers, settings.radar_expiry_threshold, settings.radar_timezone,
    )


# ── History ───────────────────────────────────────────────────────────────────
@router.get("/history")
async def get_history():
    rows = db.get_history(limit=300)
    return {
        "items": rows,
        "disclaimer": (
            "Dashboard-stored snapshot diffs only. "
            "Not Zipaworld audit history. Shows changes detected between syncs."
        ),
        "hasHistory": len(rows) > 0,
    }


# ── Sync ──────────────────────────────────────────────────────────────────────
@router.post("/sync/now")
async def sync_now(request: Request, settings: Settings = Depends(_settings)):
    global _last_manual_sync
    _check_admin(request, settings)

    now = time.monotonic()
    if now - _last_manual_sync < SYNC_COOLDOWN:
        remaining = int(SYNC_COOLDOWN - (now - _last_manual_sync))
        raise HTTPException(status_code=429, detail=f"Sync rate-limited. Try again in {remaining}s.")

    if not settings.is_demo and not settings.api_configured:
        raise HTTPException(status_code=400, detail="API not configured. Check missing settings.")

    _last_manual_sync = now
    result = await run_sync(settings, is_demo=settings.is_demo)
    return result


@router.get("/sync/status")
async def sync_status():
    state = get_sync_state()
    log = db.get_sync_log(limit=20)
    last_ok = db.get_last_successful_sync()
    return {
        "state": state,
        "recentLog": log,
        "lastSuccessfulSync": last_ok,
    }


# ── Watchlists ────────────────────────────────────────────────────────────────

@router.get("/watchlist/countries")
async def get_watched_countries():
    items = db.get_watched_countries() or DEFAULT_WATCHED_COUNTRIES
    return {
        "items": items,
        "available": [
            {"iso2": k, "name": v["name"], "region": v["region"]}
            for k, v in sorted(COUNTRIES.items(), key=lambda x: x[1]["name"])
        ],
    }


@router.put("/watchlist/countries")
async def set_watched_countries(
    body: dict, request: Request, settings: Settings = Depends(_settings)
):
    _check_admin(request, settings)
    items = body.get("items", [])
    valid = [i.upper() for i in items if isinstance(i, str) and re.match(r"^[A-Z]{2}$", i.upper())]
    db.set_watched_countries(valid)
    return {"items": valid}


@router.get("/watchlist/ports")
async def get_watched_ports():
    return {"items": db.get_watched_ports() or DEFAULT_WATCHED_PORTS}


@router.put("/watchlist/ports")
async def set_watched_ports(
    body: dict, request: Request, settings: Settings = Depends(_settings)
):
    _check_admin(request, settings)
    items = body.get("items", [])
    valid = [i.upper() for i in items if isinstance(i, str) and re.match(r"^[A-Z]{2}[A-Z0-9]{3}$", i.upper())]
    db.set_watched_ports(valid)
    return {"items": valid}


@router.get("/watchlist/india")
async def get_watched_india():
    watched   = db.get_watched_india_ports() or DEFAULT_WATCHED_INDIA
    overrides = db.get_india_overrides()
    return {"items": watched, "overrides": overrides, "staticMapping": INDIA_PORTS}


@router.put("/watchlist/india")
async def set_watched_india(
    body: dict, request: Request, settings: Settings = Depends(_settings)
):
    _check_admin(request, settings)
    items = body.get("items", [])
    valid = [i.upper() for i in items if isinstance(i, str) and is_indian_port(i)]
    db.set_watched_india_ports(valid)
    return {"items": valid}


@router.put("/watchlist/india/{code}/zone")
async def set_india_zone_override(
    code: str,
    body: dict,
    request: Request,
    settings: Settings = Depends(_settings),
):
    _check_admin(request, settings)
    zone = body.get("zone", "")
    name = body.get("name")
    valid_zones = {"West", "South", "East", "North", "Central", "Unclassified"}
    if zone not in valid_zones:
        raise HTTPException(status_code=400, detail=f"Zone must be one of: {valid_zones}")
    if not is_indian_port(code):
        raise HTTPException(status_code=400, detail="Code must be an Indian UN/LOCODE (IN + 3 chars)")
    db.set_india_override(code.upper(), zone, name)
    return {"code": code.upper(), "zone": zone, "name": name}


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_user_settings(settings: Settings = Depends(_settings)):
    return settings.public_dict()


@router.put("/settings")
async def update_settings(
    body: dict, request: Request, settings: Settings = Depends(_settings)
):
    """
    Persist user-adjustable settings to DB (overrides env values for the session).
    Only non-secret settings allowed.
    """
    _check_admin(request, settings)
    allowed = {"radar_expiry_threshold", "radar_min_carriers", "radar_timezone"}
    updated = {}
    for k, v in body.items():
        if k in allowed:
            db.set_setting(k, str(v))
            updated[k] = v
    return {"updated": updated, "note": "Restart required for env-level changes."}


# ── CSV Export ────────────────────────────────────────────────────────────────

_FORMULA_RE = re.compile(r"^[=+\-@\t\r]")


def _csv_safe(v) -> str:
    """Protect against spreadsheet formula injection."""
    if v is None:
        return ""
    s = str(v)
    if _FORMULA_RE.match(s):
        s = "'" + s
    return s


@router.get("/export/csv")
async def export_csv(
    search: str = Query(""),
    direction: str = Query(""),
    mode: str = Query(""),
    dest_country: str = Query(""),
    dest_region: str = Query(""),
    carrier: str = Query(""),
    status: str = Query(""),
    end_date_from: str = Query(""),
    end_date_to: str = Query(""),
    settings: Settings = Depends(_settings),
):
    rows, _ = db.query_rates(
        search=search, direction=direction, mode=mode,
        dest_country=dest_country, dest_region=dest_region,
        carrier=carrier,
        end_date_from=end_date_from, end_date_to=end_date_to,
        limit=50000, offset=0,
    )

    enriched = []
    for r in rows:
        e = enrich_rate(r, settings.radar_expiry_threshold, settings.radar_timezone)
        if status and e["expiry"]["status"] != status:
            continue
        enriched.append(e)

    buf = io.StringIO()
    cols = [
        "id", "origin_code", "origin_port_name", "origin_iso2",
        "destination_code", "destination_port_name", "destination_iso2",
        "direction", "shipment_mode", "container_name", "carrier_brand",
        "rate", "currency",
        "validity_start_date", "validity_end_date",
        "calculated_status", "days_remaining", "expiry_label",
        "synced_at",
    ]
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for e in enriched:
        row = {c: _csv_safe(e.get(c)) for c in cols}
        row["calculated_status"] = _csv_safe(e.get("expiry", {}).get("status"))
        row["days_remaining"]    = _csv_safe(e.get("expiry", {}).get("days_remaining"))
        row["expiry_label"]      = _csv_safe(e.get("expiry", {}).get("expiry_label"))
        writer.writerow(row)

    content = buf.getvalue()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="rate-radar-export.csv"'},
    )


# ── Reference data ────────────────────────────────────────────────────────────

@router.get("/reference/countries")
async def ref_countries():
    return [
        {"iso2": k, "name": v["name"], "region": v["region"]}
        for k, v in sorted(COUNTRIES.items(), key=lambda x: x[1]["name"])
    ]
