"""
app/normalize/normaliser.py
Transforms raw API items into the internal rate model using field-map.json.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .reference_data import (
    canonicalise_carrier,
    parse_location,
    trade_direction,
)
from ..expiry.expiry import parse_date


def _get_path(obj: dict, dotted: str) -> Any:
    """Resolve a dotted path from a dict. Returns None if any segment is missing."""
    parts = dotted.split(".")
    cur = obj
    for p in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
        if cur is None:
            return None
    return cur


def _resolve(obj: dict, paths: list[str] | str) -> Any:
    """Return the first non-null value from a list of dotted paths."""
    if isinstance(paths, str):
        paths = [paths]
    for p in paths:
        v = _get_path(obj, p)
        if v is not None and v != "":
            return v
    return None


def _build_resolver(field_map: dict):
    """Return a closure that resolves a named internal field from a raw record."""
    fields: dict = field_map.get("fields", {})

    def resolve_field(raw: dict, field_name: str) -> Any:
        defn = fields.get(field_name)
        if not defn:
            return None
        paths = defn.get("paths", [])
        return _resolve(raw, paths)

    return resolve_field


def _derive_key(raw: dict, resolve_field) -> str:
    """Stable derived key when the API provides no ID."""
    parts = [
        str(resolve_field(raw, k) or "")
        for k in ("originName", "destinationName", "shipmentMode",
                  "containerName", "shippingLineName", "validityEndDate")
    ]
    digest = hashlib.md5("|".join(parts).encode()).hexdigest()[:12]
    return f"DERIVED:{digest}"


def normalise_record(raw: dict, field_map: dict, source_index: int = 0) -> dict:
    """Normalise a single raw API record into the internal model."""
    rf = _build_resolver(field_map)

    # ── ID ────────────────────────────────────────────────────────────────
    raw_id = rf(raw, "id")
    is_derived = raw_id is None
    record_id = str(raw_id) if raw_id is not None else _derive_key(raw, rf)

    # ── Locations ─────────────────────────────────────────────────────────
    origin_raw = rf(raw, "originName")
    dest_raw   = rf(raw, "destinationName")
    op = parse_location(origin_raw)
    dp = parse_location(dest_raw)

    # Fall back to dedicated port-code fields if location string is absent
    origin_code = (op or {}).get("code") or (str(rf(raw, "originPortCode") or "").upper() or None)
    dest_code   = (dp or {}).get("code") or (str(rf(raw, "destinationPortCode") or "").upper() or None)
    origin_iso2 = origin_code[:2].upper() if origin_code else None
    dest_iso2   = dest_code[:2].upper()   if dest_code   else None

    # ── Carrier ───────────────────────────────────────────────────────────
    carrier_raw   = rf(raw, "shippingLineName")
    carrier_brand = canonicalise_carrier(carrier_raw)

    # ── Dates ─────────────────────────────────────────────────────────────
    validity_start = parse_date(rf(raw, "validityStartDate"))
    validity_end   = parse_date(rf(raw, "validityEndDate"))

    # ── Rate ──────────────────────────────────────────────────────────────
    rate_raw = rf(raw, "rate")
    try:
        rate_value = float(rate_raw) if rate_raw is not None else None
    except (TypeError, ValueError):
        rate_value = None
    currency = rf(raw, "currency")

    # ── Direction ─────────────────────────────────────────────────────────
    rate_type = rf(raw, "rateType")
    direction = trade_direction(rate_type, origin_iso2, dest_iso2)

    return {
        "id": record_id,
        "is_derived_key": is_derived,

        "origin_raw": origin_raw,
        "origin_code": origin_code,
        "origin_port_name": (op or {}).get("portName"),
        "origin_country": (op or {}).get("countryName"),
        "origin_iso2": origin_iso2,

        "destination_raw": dest_raw,
        "destination_code": dest_code,
        "destination_port_name": (dp or {}).get("portName"),
        "destination_country": (dp or {}).get("countryName"),
        "destination_iso2": dest_iso2,

        "shipment_mode": rf(raw, "shipmentMode"),
        "container_name": rf(raw, "containerName"),

        "carrier_raw": carrier_raw,
        "carrier_brand": carrier_brand,

        "rate": rate_value,
        "currency": currency,

        "validity_start_date": validity_start,
        "validity_end_date": validity_end,

        "rate_type": rate_type,
        "direction": direction,

        "created_at": rf(raw, "createdAt"),
        "updated_at": rf(raw, "updatedAt"),
        "source_status": rf(raw, "sourceStatus"),

        "raw_json": json.dumps(raw, ensure_ascii=False),
    }


def normalise_all(raw_items: list[dict], field_map: dict) -> tuple[list[dict], int]:
    """
    Normalise a list of raw items.
    Returns (records, duplicate_count).
    Deduplicates on ID, keeping the last occurrence.
    """
    seen: dict[str, dict] = {}
    dups = 0
    for i, item in enumerate(raw_items):
        rec = normalise_record(item, field_map, i)
        if rec["id"] in seen:
            dups += 1
        seen[rec["id"]] = rec
    return list(seen.values()), dups
