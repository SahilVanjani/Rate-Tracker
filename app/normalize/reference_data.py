"""
app/normalize/reference_data.py
Static lookup tables: countries, ports, India zones, carrier canonicalisation,
location parsing, trade-direction logic.
"""
from __future__ import annotations

import re

# ── Country registry ──────────────────────────────────────────────────────────
COUNTRIES: dict[str, dict] = {
    # North America
    "US": {"name": "United States",  "region": "North America"},
    "CA": {"name": "Canada",         "region": "North America"},
    "MX": {"name": "Mexico",         "region": "North America"},
    # Europe
    "GB": {"name": "United Kingdom", "region": "Europe"},
    "DE": {"name": "Germany",        "region": "Europe"},
    "NL": {"name": "Netherlands",    "region": "Europe"},
    "FR": {"name": "France",         "region": "Europe"},
    "IT": {"name": "Italy",          "region": "Europe"},
    "ES": {"name": "Spain",          "region": "Europe"},
    "BE": {"name": "Belgium",        "region": "Europe"},
    "PL": {"name": "Poland",         "region": "Europe"},
    "SE": {"name": "Sweden",         "region": "Europe"},
    "IE": {"name": "Ireland",        "region": "Europe"},
    "PT": {"name": "Portugal",       "region": "Europe"},
    "GR": {"name": "Greece",         "region": "Europe"},
    "TR": {"name": "Turkey",         "region": "Europe"},
    "RU": {"name": "Russia",         "region": "Europe"},
    # Middle East
    "AE": {"name": "UAE",            "region": "Middle East"},
    "SA": {"name": "Saudi Arabia",   "region": "Middle East"},
    "QA": {"name": "Qatar",          "region": "Middle East"},
    "KW": {"name": "Kuwait",         "region": "Middle East"},
    "OM": {"name": "Oman",           "region": "Middle East"},
    "BH": {"name": "Bahrain",        "region": "Middle East"},
    "IL": {"name": "Israel",         "region": "Middle East"},
    "JO": {"name": "Jordan",         "region": "Middle East"},
    # East Asia
    "CN": {"name": "China",          "region": "East Asia"},
    "HK": {"name": "Hong Kong",      "region": "East Asia"},
    "JP": {"name": "Japan",          "region": "East Asia"},
    "KR": {"name": "South Korea",    "region": "East Asia"},
    "TW": {"name": "Taiwan",         "region": "East Asia"},
    # SE Asia
    "SG": {"name": "Singapore",      "region": "SE Asia"},
    "MY": {"name": "Malaysia",       "region": "SE Asia"},
    "TH": {"name": "Thailand",       "region": "SE Asia"},
    "VN": {"name": "Vietnam",        "region": "SE Asia"},
    "ID": {"name": "Indonesia",      "region": "SE Asia"},
    "PH": {"name": "Philippines",    "region": "SE Asia"},
    # South Asia
    "IN": {"name": "India",          "region": "South Asia"},
    "PK": {"name": "Pakistan",       "region": "South Asia"},
    "BD": {"name": "Bangladesh",     "region": "South Asia"},
    "LK": {"name": "Sri Lanka",      "region": "South Asia"},
    # Oceania
    "AU": {"name": "Australia",      "region": "Oceania"},
    "NZ": {"name": "New Zealand",    "region": "Oceania"},
    # Africa
    "ZA": {"name": "South Africa",   "region": "Africa"},
    "EG": {"name": "Egypt",          "region": "Africa"},
    "KE": {"name": "Kenya",          "region": "Africa"},
    "NG": {"name": "Nigeria",        "region": "Africa"},
    "MA": {"name": "Morocco",        "region": "Africa"},
    "TZ": {"name": "Tanzania",       "region": "Africa"},
    # South America
    "BR": {"name": "Brazil",         "region": "South America"},
    "AR": {"name": "Argentina",      "region": "South America"},
    "CL": {"name": "Chile",          "region": "South America"},
    "CO": {"name": "Colombia",       "region": "South America"},
    "PE": {"name": "Peru",           "region": "South America"},
}

# ── Named ports ───────────────────────────────────────────────────────────────
PORTS: dict[str, str] = {
    "GBLGP": "London Gateway",
    "GBFXT": "Felixstowe",
    "GBSOU": "Southampton",
    "GBLIV": "Liverpool",
    "NLRTM": "Rotterdam",
    "DEHAM": "Hamburg",
    "BEANR": "Antwerp",
    "USNYC": "New York",
    "USLAX": "Los Angeles",
    "USSAV": "Savannah",
    "USHOU": "Houston",
    "CAMTR": "Montreal",
    "CAVAN": "Vancouver",
    "AEJEA": "Jebel Ali",
    "SGSIN": "Singapore",
    "AUSYD": "Sydney",
    "AUMEL": "Melbourne",
}

# ── India port zone mapping ────────────────────────────────────────────────────
INDIA_PORTS: dict[str, dict] = {
    # West
    "INNSA": {"name": "Nhava Sheva (JNPT)",  "zone": "West"},
    "INBOM": {"name": "Mumbai",              "zone": "West"},
    "INMUN": {"name": "Mundra",              "zone": "West"},
    "INPAV": {"name": "Pipavav",             "zone": "West"},
    "INHZA": {"name": "Hazira",              "zone": "West"},
    "INMRM": {"name": "Marmagao (Goa)",      "zone": "West"},
    "INKDL": {"name": "Kandla / Deendayal", "zone": "West"},
    # South
    "INMAA": {"name": "Chennai",             "zone": "South"},
    "INENR": {"name": "Ennore",              "zone": "South"},
    "INTUT": {"name": "Tuticorin",           "zone": "South"},
    "INCOK": {"name": "Cochin",              "zone": "South"},
    "INNML": {"name": "New Mangalore",       "zone": "South"},
    "INIXE": {"name": "Mangalore",           "zone": "South"},
    "INWFD": {"name": "Bangalore ICD",       "zone": "South"},
    "INBLR": {"name": "Bangalore",           "zone": "South"},
    # East
    "INCCU": {"name": "Kolkata",             "zone": "East"},
    "INHAL": {"name": "Haldia",              "zone": "East"},
    "INPRT": {"name": "Paradip",             "zone": "East"},
    "INVTZ": {"name": "Visakhapatnam",       "zone": "East"},
    "INKAK": {"name": "Kakinada",            "zone": "East"},
    "INKRI": {"name": "Krishnapatnam",       "zone": "East"},
    # North
    "INTKD": {"name": "Tughlakabad ICD (Delhi)", "zone": "North"},
    "INPPG": {"name": "Patparganj ICD (Delhi)",  "zone": "North"},
    "INLDH": {"name": "Ludhiana ICD",        "zone": "North"},
    "INJAI": {"name": "Jaipur ICD",          "zone": "North"},
    "INDAD": {"name": "Dadri ICD",           "zone": "North"},
    "INGRR": {"name": "Garhi Harsaru ICD",   "zone": "North"},
    # Central
    "INNGP": {"name": "Nagpur ICD",          "zone": "Central"},
    "INBPL": {"name": "Bhopal ICD",          "zone": "Central"},
}

DEFAULT_WATCHED_COUNTRIES = ["US", "CA", "GB", "DE", "NL", "AE", "SG", "AU", "CN"]
DEFAULT_WATCHED_PORTS     = ["GBLGP", "GBFXT"]
DEFAULT_WATCHED_INDIA     = [
    "INNSA", "INMUN", "INPAV", "INMAA", "INCOK", "INWFD", "INCCU", "INVTZ", "INTKD"
]
PRIORITY_CARRIERS = ["MSC", "Hapag-Lloyd", "CMA CGM", "Maersk"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def flag_emoji(iso2: str | None) -> str:
    if not iso2 or len(iso2) != 2:
        return "🌐"
    try:
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2.upper())
    except Exception:
        return "🌐"


def country_info(iso2: str | None) -> dict:
    if not iso2:
        return {"name": "Unknown", "region": "Other / unmapped", "flag": "🌐"}
    u = iso2.upper()
    c = COUNTRIES.get(u)
    if not c:
        return {"name": u, "region": "Other / unmapped", "flag": flag_emoji(u)}
    return {**c, "flag": flag_emoji(u)}


def port_label(code: str | None) -> str:
    if not code:
        return "Unknown port"
    u = code.upper()
    if u in PORTS:
        return PORTS[u]
    if u in INDIA_PORTS:
        return INDIA_PORTS[u]["name"]
    country = u[:2] if len(u) >= 2 else "??"
    return f"{u} ({country})"


def parse_location(raw: str | None) -> dict | None:
    """
    Parse a LOCODE-style string like "SGSIN,Singapore (Singapore)"
    or "INMUN,Mundra(India)" into {code, portName, countryName, countryIso2}.
    """
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    comma = s.find(",")
    if comma != -1:
        code = s[:comma].strip().upper()
        rest = s[comma + 1:].strip()
        m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", rest)
        if m:
            return {
                "code": code,
                "portName": m.group(1).strip(),
                "countryName": m.group(2).strip(),
                "countryIso2": code[:2].upper(),
            }
        return {
            "code": code,
            "portName": rest,
            "countryName": None,
            "countryIso2": code[:2].upper(),
        }
    # Just a code
    code = s.upper()
    return {
        "code": code,
        "portName": port_label(code),
        "countryName": country_info(code[:2]).get("name"),
        "countryIso2": code[:2].upper(),
    }


def canonicalise_carrier(name: str | None) -> str:
    """Map long legal carrier names to brand names (case-insensitive, priority order)."""
    if not name or not isinstance(name, str):
        return "Unknown"
    u = name.upper()
    if "MSC" in u or "MEDITERRANEAN" in u:
        return "MSC"
    if "HAPAG" in u or "HLAG" in u:
        return "Hapag-Lloyd"
    if "CMA" in u or "CGM" in u:
        return "CMA CGM"
    if any(x in u for x in ("MAERSK", "SEALAND", "SEA-LAND", "SAFMARINE", "HAMBURG SUD")):
        return "Maersk"
    if "OCEAN NETWORK" in u or re.search(r"\bONE\b", u):
        return "ONE"
    if "EVERGREEN" in u:
        return "Evergreen"
    if "COSCO" in u or "OOCL" in u:
        return "COSCO"
    if "HYUNDAI" in u or re.search(r"\bHMM\b", u):
        return "HMM"
    if "YANG MING" in u:
        return "Yang Ming"
    if re.search(r"\bZIM\b", u):
        return "ZIM"
    # Fallback: first two words
    words = name.strip().split()
    return " ".join(words[:2]) if words else "Unknown"


def trade_direction(
    rate_type: str | None,
    origin_iso2: str | None,
    dest_iso2: str | None,
) -> str:
    """Determine trade direction following the spec priority rules."""
    rt = (rate_type or "").upper()
    if rt in {"OE", "AE", "OEX", "AEX", "EXP"}:
        return "Export"
    if rt in {"OI", "AI", "OIM", "AIM", "IMP"}:
        return "Import"
    orig = (origin_iso2 or "").upper()
    dest = (dest_iso2 or "").upper()
    if orig == "IN" and dest != "IN":
        return "Export"
    if dest == "IN" and orig != "IN":
        return "Import"
    if orig == "IN" and dest == "IN":
        return "Domestic"
    return "Cross-trade"


def is_indian_port(code: str | None) -> bool:
    return bool(code and re.match(r"^IN[A-Z]{3}$", code.upper()))
