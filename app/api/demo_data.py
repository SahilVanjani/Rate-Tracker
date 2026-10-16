"""
app/api/demo_data.py
Synthetic rate data for RADAR_MODE=demo.
All dates are relative to today so statuses always match.
Never active in live mode.
"""
from __future__ import annotations

import json
from datetime import date, timedelta


def _d(delta: int) -> str:
    return (date.today() + timedelta(days=delta)).isoformat()


def generate_demo_rates() -> list[dict]:
    """
    Return ~55 raw-format rate dicts covering every status and scenario:
    ACTIVE, EXPIRING_SOON, EXPIRED, STARTS_LATER, NEEDS_REVIEW (missing/invalid dates),
    uncovered lanes, thin-cover situations, duplicate ID (for dedup test).
    """
    r = []

    def rate(id_, origin, dest, carrier, mode="FCL", container="40 Standard",
             rate_val=None, currency="USD", start=None, end=None,
             rate_type="OE", source_status="Active"):
        return {
            "id": id_,
            "originName": origin,
            "destinationName": dest,
            "shippingLineName": carrier,
            "shipmentMode": mode,
            "containerName": container,
            "rate": rate_val,
            "currency": currency,
            "validityStartDate": start,
            "validityEndDate": end,
            "rateType": rate_type,
            "status": source_status,
            "createdAt": _d(-60),
            "updatedAt": _d(-5),
        }

    # ── ACTIVE rates (end > today + 14) ──────────────────────────────────
    r.append(rate("D001", "INMUN,Mundra(India)",          "USNYC,New York(United States)",    "MSC AGENCY (INDIA) PVT. LTD",     rate_val=2500, start=_d(-30), end=_d(45)))
    r.append(rate("D002", "INMUN,Mundra(India)",          "GBLGP,London Gateway(United Kingdom)", "HAPAG-LLOYD AG",               rate_val=3200, start=_d(-15), end=_d(60)))
    r.append(rate("D003", "INMUN,Mundra(India)",          "DEHAM,Hamburg(Germany)",           "CMA CGM S.A.",                    rate_val=2800, start=_d(-10), end=_d(55)))
    r.append(rate("D004", "INNSA,Nhava Sheva(India)",     "SGSIN,Singapore(Singapore)",       "MAERSK LINE",                     rate_val=1500, start=_d(-20), end=_d(30)))
    r.append(rate("D005", "INNSA,Nhava Sheva(India)",     "AEJEA,Jebel Ali(UAE)",             "MSC AGENCY (INDIA) PVT. LTD",     rate_val=800,  start=_d(-5),  end=_d(90)))
    r.append(rate("D006", "INNSA,Nhava Sheva(India)",     "AUMEL,Melbourne(Australia)",       "OCEAN NETWORK EXPRESS PTE. LTD",  rate_val=2200, start=_d(-8),  end=_d(40)))
    r.append(rate("D007", "INMUN,Mundra(India)",          "NLRTM,Rotterdam(Netherlands)",     "MSC AGENCY (INDIA) PVT. LTD",     rate_val=2900, start=_d(-12), end=_d(50)))
    r.append(rate("D008", "INNSA,Nhava Sheva(India)",     "USHOU,Houston(United States)",     "CMA CGM S.A.",                    rate_val=2600, start=_d(-25), end=_d(35)))
    r.append(rate("D009", "INMAA,Chennai(India)",         "USNYC,New York(United States)",    "MAERSK LINE",                     rate_val=2400, start=_d(-18), end=_d(28)))
    r.append(rate("D010", "INCCU,Kolkata(India)",         "GBLGP,London Gateway(United Kingdom)", "HAPAG-LLOYD AG",              rate_val=3100, start=_d(-30), end=_d(55)))
    r.append(rate("D011", "INWFD,Bangalore ICD(India)",   "BEANR,Antwerp(Belgium)",           "EVERGREEN MARINE CORP.",          rate_val=2700, start=_d(-10), end=_d(75)))
    r.append(rate("D012", "INCOK,Cochin(India)",          "USNYC,New York(United States)",    "CMA CGM S.A.",                    rate_val=2550, start=_d(-7),  end=_d(42)))
    r.append(rate("D013", "INVTZ,Visakhapatnam(India)",   "GBLGP,London Gateway(United Kingdom)", "COSCO SHIPPING LINES CO. LTD", rate_val=3000, start=_d(-14), end=_d(48)))
    r.append(rate("D014", "INTKD,Tughlakabad ICD(India)", "DEHAM,Hamburg(Germany)",           "YANG MING MARINE TRANSPORT",      rate_val=2850, start=_d(-20), end=_d(33)))
    r.append(rate("D015", "INMUN,Mundra(India)",          "CAMTR,Montreal(Canada)",           "MSC AGENCY (INDIA) PVT. LTD",     rate_val=2300, start=_d(-6),  end=_d(66)))

    # ── EXPIRING SOON (end <= today + 14, >= today) ───────────────────────
    r.append(rate("D016", "INMUN,Mundra(India)",          "USNYC,New York(United States)",    "HAPAG-LLOYD AG",                  rate_val=2550, start=_d(-20), end=_d(7)))
    r.append(rate("D017", "INNSA,Nhava Sheva(India)",     "GBLGP,London Gateway(United Kingdom)", "CMA CGM S.A.",                rate_val=3100, start=_d(-30), end=_d(3)))
    r.append(rate("D018", "INMAA,Chennai(India)",         "SGSIN,Singapore(Singapore)",       "MSC AGENCY (INDIA) PVT. LTD",     rate_val=1600, start=_d(-14), end=_d(12)))
    r.append(rate("D019", "INCOK,Cochin(India)",          "DEHAM,Hamburg(Germany)",           "MAERSK LINE",                     rate_val=2900, start=_d(-10), end=_d(1)))
    r.append(rate("D020", "INWFD,Bangalore ICD(India)",   "USNYC,New York(United States)",    "OCEAN NETWORK EXPRESS PTE. LTD",  rate_val=2450, start=_d(-25), end=_d(10)))
    r.append(rate("D021", "INMUN,Mundra(India)",          "AEJEA,Jebel Ali(UAE)",             "ZIM INTEGRATED SHIPPING SERVICES", rate_val=750, start=_d(-5),  end=_d(0)))   # expires today
    r.append(rate("D022", "INNSA,Nhava Sheva(India)",     "AUMEL,Melbourne(Australia)",       "HAPAG-LLOYD AG",                  rate_val=2100, start=_d(-40), end=_d(14)))   # threshold edge
    r.append(rate("D023", "INCCU,Kolkata(India)",         "NLRTM,Rotterdam(Netherlands)",     "CMA CGM S.A.",                    rate_val=2800, start=_d(-15), end=_d(5)))

    # ── EXPIRED (end < today) ─────────────────────────────────────────────
    r.append(rate("D024", "INNSA,Nhava Sheva(India)",     "USNYC,New York(United States)",    "COSCO SHIPPING LINES CO. LTD",    rate_val=2300, start=_d(-60), end=_d(-5)))
    r.append(rate("D025", "INMUN,Mundra(India)",          "GBLGP,London Gateway(United Kingdom)", "HYUNDAI MERCHANT MARINE",      rate_val=3000, start=_d(-90), end=_d(-15)))
    r.append(rate("D026", "INNSA,Nhava Sheva(India)",     "AUMEL,Melbourne(Australia)",       "YANG MING MARINE TRANSPORT",      rate_val=2100, start=_d(-120), end=_d(-30)))
    r.append(rate("D027", "INCCU,Kolkata(India)",         "NLRTM,Rotterdam(Netherlands)",     "MSC AGENCY (INDIA) PVT. LTD",     rate_val=2700, start=_d(-80), end=_d(-45)))
    r.append(rate("D028", "INMAA,Chennai(India)",         "DEHAM,Hamburg(Germany)",           "HAPAG-LLOYD AG",                  rate_val=2850, start=_d(-70), end=_d(-1)))    # expired yesterday
    r.append(rate("D029", "INVTZ,Visakhapatnam(India)",   "USHOU,Houston(United States)",     "CMA CGM S.A.",                    rate_val=2600, start=_d(-100), end=_d(-20)))

    # ── STARTS LATER (start > today) ─────────────────────────────────────
    r.append(rate("D030", "INMUN,Mundra(India)",          "USNYC,New York(United States)",    "EVERGREEN MARINE CORP.",           rate_val=2450, start=_d(5),  end=_d(35)))
    r.append(rate("D031", "INNSA,Nhava Sheva(India)",     "GBLGP,London Gateway(United Kingdom)", "MSC AGENCY (INDIA) PVT. LTD", rate_val=3300, start=_d(10), end=_d(70)))
    r.append(rate("D032", "INCOK,Cochin(India)",          "BEANR,Antwerp(Belgium)",           "MAERSK LINE",                     rate_val=2750, start=_d(3),  end=_d(60)))

    # ── NEEDS REVIEW: missing end date ────────────────────────────────────
    r.append(rate("D033", "INMUN,Mundra(India)",          "CNSHA,Shanghai(China)",            "COSCO SHIPPING LINES CO. LTD",    rate_val=1200, start=_d(-10), end=None))
    r.append(rate("D034", "INTKD,Tughlakabad ICD(India)", "CAMTR,Montreal(Canada)",           "HAPAG-LLOYD AG",                  rate_val=2400))

    # ── NEEDS REVIEW: invalid date format ─────────────────────────────────
    r.append({
        "id": "D035", "originName": "INNSA,Nhava Sheva(India)",
        "destinationName": "JPYOK,Yokohama(Japan)",
        "shippingLineName": "ONE OCEAN NETWORK EXPRESS",
        "shipmentMode": "FCL", "containerName": "20 Standard",
        "rate": 1800, "currency": "USD",
        "validityStartDate": _d(-5), "validityEndDate": "N/A",
        "rateType": "OE", "status": "Active",
    })

    # ── NEEDS REVIEW: start after end ─────────────────────────────────────
    r.append(rate("D036", "INCOK,Cochin(India)",          "BEANR,Antwerp(Belgium)",           "ZIM INTEGRATED SHIPPING SERVICES", rate_val=2900, start=_d(20), end=_d(10)))

    # ── NEEDS REVIEW: missing both dates ─────────────────────────────────
    r.append(rate("D037", "INWFD,Bangalore ICD(India)",   "CAVAN,Vancouver(Canada)",          "YANG MING MARINE TRANSPORT",      rate_val=2200))

    # ── Duplicate ID (for dedup test, should produce only 1 record) ──────
    r.append(rate("D038", "INMUN,Mundra(India)",          "USNYC,New York(United States)",    "MSC AGENCY (INDIA) PVT. LTD",     rate_val=2480, start=_d(-15), end=_d(22)))
    r.append(rate("D038", "INMUN,Mundra(India)",          "USNYC,New York(United States)",    "MSC AGENCY (INDIA) PVT. LTD",     rate_val=2490, start=_d(-15), end=_d(22)))  # duplicate

    # ── Thin-cover lane: US has only 1 carrier from a port ───────────────
    r.append(rate("D039", "INPAV,Pipavav(India)",         "USLAX,Los Angeles(United States)", "MAERSK LINE",                     rate_val=2350, start=_d(-10), end=_d(40)))
    # (No second carrier for INPAV → USLAX, so it will show THIN_COVER)

    # ── GAP lane: South Africa – no rates at all ─────────────────────────
    # (no entry for ZA; keeps it a gap)

    # ── LCL rates ─────────────────────────────────────────────────────────
    r.append(rate("D040", "INMUN,Mundra(India)",          "SGSIN,Singapore(Singapore)",       "HAPAG-LLOYD AG",                  mode="LCL", container="LCL", rate_val=120, start=_d(-20), end=_d(25)))
    r.append(rate("D041", "INNSA,Nhava Sheva(India)",     "DEHAM,Hamburg(Germany)",           "CMA CGM S.A.",                    mode="LCL", container="LCL", rate_val=95,  start=_d(-15), end=_d(18)))

    # ── More destinations to enrich country coverage ──────────────────────
    r.append(rate("D042", "INMUN,Mundra(India)",          "CNSHA,Shanghai(China)",            "COSCO SHIPPING LINES CO. LTD",    rate_val=1300, start=_d(-10), end=_d(30)))
    r.append(rate("D043", "INMUN,Mundra(India)",          "CNSHA,Shanghai(China)",            "OCEAN NETWORK EXPRESS PTE. LTD",  rate_val=1350, start=_d(-10), end=_d(28)))
    r.append(rate("D044", "INNSA,Nhava Sheva(India)",     "AUSYD,Sydney(Australia)",          "MAERSK LINE",                     rate_val=2000, start=_d(-5),  end=_d(45)))
    r.append(rate("D045", "INMAA,Chennai(India)",         "SGSIN,Singapore(Singapore)",       "HAPAG-LLOYD AG",                  rate_val=1550, start=_d(-8),  end=_d(38)))
    r.append(rate("D046", "INCCU,Kolkata(India)",         "AEJEA,Jebel Ali(UAE)",             "MSC AGENCY (INDIA) PVT. LTD",     rate_val=850,  start=_d(-12), end=_d(33)))
    r.append(rate("D047", "INTKD,Tughlakabad ICD(India)", "USNYC,New York(United States)",    "HAPAG-LLOYD AG",                  rate_val=2600, start=_d(-18), end=_d(40)))
    r.append(rate("D048", "INNSA,Nhava Sheva(India)",     "CAVAN,Vancouver(Canada)",          "CMA CGM S.A.",                    rate_val=2400, start=_d(-10), end=_d(35)))
    r.append(rate("D049", "INMUN,Mundra(India)",          "NLRTM,Rotterdam(Netherlands)",     "HAPAG-LLOYD AG",                  rate_val=3000, start=_d(-8),  end=_d(28)))
    r.append(rate("D050", "INMAA,Chennai(India)",         "GBLGP,London Gateway(United Kingdom)", "MAERSK LINE",                  rate_val=3250, start=_d(-20), end=_d(50)))
    r.append(rate("D051", "INWFD,Bangalore ICD(India)",   "DEHAM,Hamburg(Germany)",           "MSC AGENCY (INDIA) PVT. LTD",     rate_val=2750, start=_d(-15), end=_d(44)))
    r.append(rate("D052", "INCOK,Cochin(India)",          "SGSIN,Singapore(Singapore)",       "COSCO SHIPPING LINES CO. LTD",    rate_val=1450, start=_d(-7),  end=_d(32)))
    r.append(rate("D053", "INVTZ,Visakhapatnam(India)",   "AEJEA,Jebel Ali(UAE)",             "HAPAG-LLOYD AG",                  rate_val=900,  start=_d(-10), end=_d(8)))   # expiring
    r.append(rate("D054", "INPAV,Pipavav(India)",         "GBLGP,London Gateway(United Kingdom)", "CMA CGM S.A.",                rate_val=3150, start=_d(-15), end=_d(36)))
    r.append(rate("D055", "INTKD,Tughlakabad ICD(India)", "AUMEL,Melbourne(Australia)",       "MAERSK LINE",                     rate_val=2250, start=_d(-25), end=_d(20)))
    r.append(rate("D056", "INPAV,Pipavav(India)",         "USNYC,New York(United States)",    "HAPAG-LLOYD AG",                  rate_val=2480, start=_d(-12), end=_d(-3)))  # expired
    r.append(rate("D057", "INNSA,Nhava Sheva(India)",     "BEANR,Antwerp(Belgium)",           "MSC AGENCY (INDIA) PVT. LTD",     rate_val=2850, start=_d(-20), end=_d(42)))
    r.append(rate("D058", "INMUN,Mundra(India)",          "AUSYD,Sydney(Australia)",          "HAPAG-LLOYD AG",                  rate_val=2150, start=_d(-5),  end=_d(55)))
    r.append(rate("D059", "INCCU,Kolkata(India)",         "USNYC,New York(United States)",    "CMA CGM S.A.",                    rate_val=2520, start=_d(-18), end=_d(30)))
    r.append(rate("D060", "INMAA,Chennai(India)",         "AUMEL,Melbourne(Australia)",       "EVERGREEN MARINE CORP.",          rate_val=2050, start=_d(-10), end=_d(46)))

    return r
