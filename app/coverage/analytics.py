"""
app/coverage/analytics.py
Carrier-depth coverage for countries, ports and India port board.
"""
from __future__ import annotations

from ..expiry.expiry import calc_expiry
from ..normalize.reference_data import (
    COUNTRIES, INDIA_PORTS, country_info, flag_emoji, port_label, is_indian_port,
)

# Coverage statuses (sort order as listed)
COV_GAP         = "GAP"
COV_ALL_EXPIRED = "ALL_EXPIRED"
COV_THIN        = "THIN_COVER"
COV_COVERED     = "COVERED"

_SORT_ORDER = {COV_GAP: 0, COV_ALL_EXPIRED: 1, COV_THIN: 2, COV_COVERED: 3}


def _coverage_sort_key(item: dict) -> tuple:
    """Sort: GAP < ALL_EXPIRED < THIN < expiring-COVERED < COVERED."""
    s = item.get("coverageStatus", COV_GAP)
    o = _SORT_ORDER.get(s, 9)
    expiring = item.get("hasExpiring", False)
    # Within COVERED, expiring comes before non-expiring (more urgent)
    return (o, 0 if expiring and s == COV_COVERED else 1)


def _carrier_chips(active: set, expiring: set, expired: set) -> list[dict]:
    chips = []
    for c in sorted(active - expiring):
        chips.append({"brand": c, "state": "active"})
    for c in sorted(expiring):
        chips.append({"brand": c, "state": "expiring"})
    for c in sorted(expired - active - expiring):
        chips.append({"brand": c, "state": "expired"})
    return chips


def _compute_coverage(
    rates: list[dict],
    min_carriers: int,
    threshold: int,
    tz: str,
) -> dict:
    """
    Core carrier-depth computation for a set of matching rates.
    Returns coverage summary dict.
    """
    if not rates:
        return {
            "coverageStatus": COV_GAP,
            "validCarrierCount": 0,
            "minCarriers": min_carriers,
            "hasExpiring": False,
            "nearestExpiry": None,
            "carrierChips": [],
            "totalRates": 0,
        }

    active_carriers:   set[str] = set()
    expiring_carriers: set[str] = set()
    expired_carriers:  set[str] = set()
    nearest_expiry: str | None = None

    for r in rates:
        brand = r.get("carrier_brand") or "Unknown"
        exp = calc_expiry(
            r.get("validity_start_date"),
            r.get("validity_end_date"),
            threshold=threshold,
            tz=tz,
        )
        status = exp["status"]
        if status == "ACTIVE":
            active_carriers.add(brand)
        elif status == "EXPIRING_SOON":
            active_carriers.add(brand)
            expiring_carriers.add(brand)
            ed = r.get("validity_end_date")
            if ed:
                if nearest_expiry is None or ed < nearest_expiry:
                    nearest_expiry = ed
        elif status == "EXPIRED":
            expired_carriers.add(brand)

    valid_carriers = active_carriers  # active includes expiring (still valid)
    has_expiring   = bool(expiring_carriers)

    if not valid_carriers and not expired_carriers:
        cov_status = COV_GAP
    elif not valid_carriers:
        cov_status = COV_ALL_EXPIRED
    elif len(valid_carriers) < min_carriers:
        cov_status = COV_THIN
    else:
        cov_status = COV_COVERED

    return {
        "coverageStatus": cov_status,
        "validCarrierCount": len(valid_carriers),
        "minCarriers": min_carriers,
        "hasExpiring": has_expiring,
        "nearestExpiry": nearest_expiry,
        "carrierChips": _carrier_chips(active_carriers, expiring_carriers, expired_carriers),
        "totalRates": len(rates),
    }


# ── Country coverage ──────────────────────────────────────────────────────────

def country_coverage(
    all_rates: list[dict],
    watched: list[str],
    min_carriers: int,
    threshold: int,
    tz: str,
) -> dict:
    """Return coverage analysis for each watched country."""
    # Index rates by destination_iso2
    by_country: dict[str, list[dict]] = {}
    for r in all_rates:
        iso2 = r.get("destination_iso2")
        if iso2:
            by_country.setdefault(iso2, []).append(r)

    results = []
    for iso2 in watched:
        rates_for = by_country.get(iso2.upper(), [])
        cov = _compute_coverage(rates_for, min_carriers, threshold, tz)
        ci = country_info(iso2)
        results.append({
            "iso2": iso2.upper(),
            "name": ci["name"],
            "region": ci["region"],
            "flag": ci["flag"],
            **cov,
        })

    results.sort(key=_coverage_sort_key)

    gaps    = [r for r in results if r["coverageStatus"] == COV_GAP]
    expired = [r for r in results if r["coverageStatus"] == COV_ALL_EXPIRED]
    thin    = [r for r in results if r["coverageStatus"] == COV_THIN]

    if not gaps and not expired and not thin:
        summary = "All watched countries have adequate coverage."
    else:
        parts = []
        if gaps:    parts.append(f"{len(gaps)} with no rate")
        if expired: parts.append(f"{len(expired)} all-expired")
        if thin:    parts.append(f"{len(thin)} below minimum carriers")
        summary = "Attention: " + ", ".join(parts) + "."

    return {"items": results, "summary": summary}


# ── Port coverage ─────────────────────────────────────────────────────────────

def port_coverage(
    all_rates: list[dict],
    watched: list[str],
    min_carriers: int,
    threshold: int,
    tz: str,
) -> dict:
    """Return coverage analysis for each watched port (destination)."""
    by_port: dict[str, list[dict]] = {}
    for r in all_rates:
        code = r.get("destination_code")
        if code:
            by_port.setdefault(code.upper(), []).append(r)

    results = []
    for code in watched:
        rates_for = by_port.get(code.upper(), [])
        cov = _compute_coverage(rates_for, min_carriers, threshold, tz)
        iso2 = code[:2].upper() if len(code) >= 2 else ""
        results.append({
            "code": code.upper(),
            "name": port_label(code),
            "countryIso2": iso2,
            "flag": flag_emoji(iso2),
            **cov,
        })

    results.sort(key=_coverage_sort_key)

    needs = [r for r in results if r["coverageStatus"] in (COV_GAP, COV_ALL_EXPIRED, COV_THIN)]
    summary = (
        "All watched ports have adequate coverage."
        if not needs
        else f"Attention: {len(needs)} port(s) need attention."
    )
    return {"items": results, "summary": summary}


# ── India port board ──────────────────────────────────────────────────────────

def india_board(
    all_rates: list[dict],
    watched: list[str],
    overrides: dict[str, dict],
    min_carriers: int,
    threshold: int,
    tz: str,
) -> dict:
    """Return India zone board with auto-detected ports and override support."""
    # Index rates that touch Indian ports (either origin or destination)
    by_code: dict[str, list[dict]] = {}
    for r in all_rates:
        for field in ("origin_code", "destination_code"):
            code = r.get(field)
            if code and is_indian_port(code):
                by_code.setdefault(code.upper(), []).append(r)

    # Detect all Indian codes that appear in data
    detected_codes = set(by_code.keys())

    # Resolve zone for a code (overrides > static > Unclassified)
    def resolve_zone(code: str) -> str:
        ov = overrides.get(code)
        if ov:
            return ov["zone"]
        static = INDIA_PORTS.get(code)
        if static:
            return static["zone"]
        return "Unclassified"

    def resolve_name(code: str) -> str:
        ov = overrides.get(code)
        if ov and ov.get("name"):
            return ov["name"]
        static = INDIA_PORTS.get(code)
        if static:
            return static["name"]
        return code

    zones: dict[str, list[dict]] = {
        "West": [], "South": [], "East": [], "North": [], "Central": [], "Unclassified": []
    }

    watched_set = {w.upper() for w in watched}
    not_watched_detected: list[dict] = []

    all_known = watched_set | detected_codes

    for code in sorted(all_known):
        rates_for = by_code.get(code, [])
        cov = _compute_coverage(rates_for, min_carriers, threshold, tz)
        zone = resolve_zone(code)
        entry = {
            "code": code,
            "name": resolve_name(code),
            "zone": zone,
            "watched": code in watched_set,
            "detectedInData": code in detected_codes,
            "inStaticMapping": code in INDIA_PORTS,
            "hasOverride": code in overrides,
            "recordCount": len(rates_for),
            **cov,
        }
        if code in watched_set:
            zones[zone].append(entry)
        else:
            not_watched_detected.append(entry)

    # Zone summaries
    zone_summaries = {}
    for zone_name, entries in zones.items():
        if not entries:
            zone_summaries[zone_name] = {"count": 0, "missing": 0, "expiring": 0, "covered": 0}
            continue
        missing  = sum(1 for e in entries if e["coverageStatus"] in (COV_GAP, COV_ALL_EXPIRED))
        expiring = sum(1 for e in entries if e["hasExpiring"])
        covered  = sum(1 for e in entries if e["coverageStatus"] == COV_COVERED)
        zone_summaries[zone_name] = {
            "count": len(entries),
            "missing": missing,
            "expiring": expiring,
            "covered": covered,
        }

    return {
        "zones": {k: sorted(v, key=_coverage_sort_key) for k, v in zones.items()},
        "zoneSummaries": zone_summaries,
        "detectedNotWatched": sorted(not_watched_detected, key=lambda x: x["code"]),
    }


# ── Overview KPIs ─────────────────────────────────────────────────────────────

def overview_kpis(
    all_rates: list[dict],
    watched_countries: list[str],
    watched_ports: list[str],
    min_carriers: int,
    threshold: int,
    tz: str,
) -> dict:
    """Compute KPI values for the overview page."""
    from ..expiry.expiry import STATUS_ACTIVE, STATUS_EXPIRING_SOON, STATUS_EXPIRED
    from ..expiry.expiry import STATUS_STARTS_LATER, STATUS_NEEDS_REVIEW

    total = len(all_rates)
    # Unique lanes: origin + destination + mode
    lanes = {
        (r.get("origin_code"), r.get("destination_code"), r.get("shipment_mode"))
        for r in all_rates
    }

    counts = {
        STATUS_ACTIVE: 0, STATUS_EXPIRING_SOON: 0, STATUS_EXPIRED: 0,
        STATUS_STARTS_LATER: 0, STATUS_NEEDS_REVIEW: 0,
    }
    dest_countries_with_active: set[str] = set()
    next_expiries: list[dict] = []

    for r in all_rates:
        exp = calc_expiry(
            r.get("validity_start_date"),
            r.get("validity_end_date"),
            threshold=threshold,
            tz=tz,
        )
        s = exp["status"]
        counts[s] = counts.get(s, 0) + 1

        if s in (STATUS_ACTIVE, STATUS_EXPIRING_SOON):
            iso2 = r.get("destination_iso2")
            if iso2:
                dest_countries_with_active.add(iso2)

        if s == STATUS_EXPIRING_SOON and r.get("validity_end_date"):
            next_expiries.append({
                "id": r["id"],
                "lane": f"{r.get('origin_code','?')} → {r.get('destination_code','?')}",
                "carrier": r.get("carrier_brand"),
                "endDate": r["validity_end_date"],
                "daysRemaining": exp["days_remaining"],
                "expiryLabel": exp["expiry_label"],
            })

    next_expiries.sort(key=lambda x: (x["endDate"] or "9999-99-99"))
    next_expiries = next_expiries[:10]

    # Coverage alerts: watched items needing attention
    cc = country_coverage(all_rates, watched_countries, min_carriers, threshold, tz)
    pc = port_coverage(all_rates, watched_ports, min_carriers, threshold, tz)
    attention = [
        i for i in cc["items"] + pc["items"]
        if i["coverageStatus"] in (COV_GAP, COV_ALL_EXPIRED, COV_THIN)
    ]

    return {
        "total": total,
        "uniqueLanes": len(lanes),
        "active": counts[STATUS_ACTIVE],
        "expiringSoon": counts[STATUS_EXPIRING_SOON],
        "expired": counts[STATUS_EXPIRED],
        "startsLater": counts[STATUS_STARTS_LATER],
        "needsReview": counts[STATUS_NEEDS_REVIEW],
        "countriesCovered": len(dest_countries_with_active),
        "coverageAlerts": len(attention),
        "nextExpiries": next_expiries,
        "needsAttention": attention[:5],
        "statusBar": counts,
    }


# ── Expiry alerts ─────────────────────────────────────────────────────────────

def expiry_alerts(
    all_rates: list[dict],
    watched_countries: list[str],
    watched_ports: list[str],
    min_carriers: int,
    threshold: int,
    tz: str,
) -> dict:
    """Group rates into alert buckets."""
    from ..expiry.expiry import (
        STATUS_ACTIVE, STATUS_EXPIRING_SOON, STATUS_EXPIRED,
        STATUS_STARTS_LATER, STATUS_NEEDS_REVIEW,
    )

    expired_list:    list[dict] = []
    within3:         list[dict] = []
    within4_7:       list[dict] = []
    within8_14:      list[dict] = []
    future_list:     list[dict] = []
    needs_review:    list[dict] = []

    for r in all_rates:
        exp = calc_expiry(
            r.get("validity_start_date"),
            r.get("validity_end_date"),
            threshold=threshold,
            tz=tz,
        )
        s = exp["status"]
        dr = exp.get("days_remaining")
        entry = {**r, "expiry": exp}

        if s == STATUS_EXPIRED:
            expired_list.append(entry)
        elif s == STATUS_EXPIRING_SOON:
            if dr is not None and dr <= 3:
                within3.append(entry)
            elif dr is not None and dr <= 7:
                within4_7.append(entry)
            else:
                within8_14.append(entry)
        elif s == STATUS_STARTS_LATER:
            future_list.append(entry)
        elif s == STATUS_NEEDS_REVIEW:
            needs_review.append(entry)

    # Coverage gaps
    cc = country_coverage(all_rates, watched_countries, min_carriers, threshold, tz)
    pc = port_coverage(all_rates, watched_ports, min_carriers, threshold, tz)
    gaps = [i for i in cc["items"] + pc["items"] if i["coverageStatus"] == COV_GAP]

    def _sort(lst: list[dict]) -> list[dict]:
        return sorted(lst, key=lambda x: (x.get("validity_end_date") or "9999-99-99"))

    return {
        "expired": _sort(expired_list),
        "within3Days": _sort(within3),
        "within4to7Days": _sort(within4_7),
        "within8to14Days": _sort(within8_14),
        "futurEffective": future_list,
        "needsReview": needs_review,
        "coverageGaps": gaps,
    }
