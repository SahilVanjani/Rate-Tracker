"""
app/expiry/expiry.py
Date-only expiry status calculations with zoneinfo timezone support.
Statuses are always computed at call time so they change at midnight.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo
import re

# ── Status constants ──────────────────────────────────────────────────────────
STATUS_ACTIVE        = "ACTIVE"
STATUS_EXPIRING_SOON = "EXPIRING_SOON"
STATUS_EXPIRED       = "EXPIRED"
STATUS_STARTS_LATER  = "STARTS_LATER"
STATUS_NEEDS_REVIEW  = "NEEDS_REVIEW"

ALL_STATUSES = [
    STATUS_ACTIVE, STATUS_EXPIRING_SOON, STATUS_EXPIRED,
    STATUS_STARTS_LATER, STATUS_NEEDS_REVIEW,
]


def today_local(tz: str = "Asia/Kolkata") -> date:
    """Return today's date in the given timezone. Called at request time."""
    try:
        return datetime.now(ZoneInfo(tz)).date()
    except Exception:
        return date.today()


def parse_date(raw) -> str | None:
    """
    Parse a raw value into a canonical YYYY-MM-DD string.
    Returns None if unparseable (never raises).
    """
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    if not s:
        return None
    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            date.fromisoformat(s)
            return s
        except ValueError:
            return None
    # ISO with time → take date part
    if re.match(r"^\d{4}-\d{2}-\d{2}T", s):
        part = s[:10]
        try:
            date.fromisoformat(part)
            return part
        except ValueError:
            return None
    # DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"^(\d{2})[/\-](\d{2})[/\-](\d{4})$", s)
    if m:
        candidate = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        try:
            date.fromisoformat(candidate)
            return candidate
        except ValueError:
            return None
    # MM/DD/YYYY
    m2 = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", s)
    if m2:
        candidate = f"{m2.group(3)}-{m2.group(1).zfill(2)}-{m2.group(2).zfill(2)}"
        try:
            date.fromisoformat(candidate)
            return candidate
        except ValueError:
            pass
    return None


def days_diff(base: date, target: date) -> int:
    """(target - base).days — integer, can be negative."""
    return (target - base).days


def expiry_label(
    status: str,
    days_remaining: int | None,
    days_expired: int | None,
    start_str: str | None,
    today: date,
) -> str:
    if status in (STATUS_ACTIVE, STATUS_EXPIRING_SOON):
        d = days_remaining or 0
        if d == 0:
            return "Expires today"
        if d == 1:
            return "Expires tomorrow"
        return f"Expires in {d} days"
    if status == STATUS_EXPIRED:
        d = days_expired or 0
        if d == 1:
            return "Expired yesterday"
        return f"Expired {d} days ago"
    if status == STATUS_STARTS_LATER and start_str:
        try:
            start = date.fromisoformat(start_str)
            d = days_diff(today, start)
            if d == 1:
                return "Starts tomorrow"
            return f"Starts in {d} days"
        except ValueError:
            pass
    return "Validity date unavailable"


def calc_expiry(
    validity_start_date: str | None,
    validity_end_date: str | None,
    threshold: int = 14,
    tz: str = "Asia/Kolkata",
) -> dict:
    """
    Compute expiry status for a rate record.
    Returns a dict with: status, reason, days_remaining, days_expired, expiry_label, today.
    """
    today = today_local(tz)
    today_str = today.isoformat()

    def _result(status, reason, dr=None, de=None):
        label = expiry_label(status, dr, de, validity_start_date, today)
        return {
            "status": status,
            "reason": reason,
            "days_remaining": dr,
            "days_expired": de,
            "expiry_label": label,
            "today": today_str,
        }

    # NEEDS REVIEW: missing end date
    if not validity_end_date:
        return _result(STATUS_NEEDS_REVIEW, "missing_end_date")

    # NEEDS REVIEW: start after end
    if validity_start_date and validity_start_date > validity_end_date:
        return {
            "status": STATUS_NEEDS_REVIEW,
            "reason": "start_after_end",
            "days_remaining": None,
            "days_expired": None,
            "expiry_label": "Start date after end date",
            "today": today_str,
        }

    try:
        end_date = date.fromisoformat(validity_end_date)
    except ValueError:
        return _result(STATUS_NEEDS_REVIEW, "invalid_end_date_format")

    # STARTS LATER: valid start date is in the future
    if validity_start_date:
        try:
            start_date = date.fromisoformat(validity_start_date)
            if start_date > today:
                dr = days_diff(today, end_date)
                return _result(STATUS_STARTS_LATER, "future_start", dr=dr)
        except ValueError:
            pass

    d_to_end = days_diff(today, end_date)  # negative = expired

    # EXPIRED
    if d_to_end < 0:
        de = abs(d_to_end)
        return _result(STATUS_EXPIRED, "past_end_date", dr=0, de=de)

    # EXPIRING SOON (end date >= today, within threshold)
    if d_to_end <= threshold:
        return _result(STATUS_EXPIRING_SOON, f"expires_within_{threshold}_days", dr=d_to_end)

    # ACTIVE
    return _result(STATUS_ACTIVE, "valid", dr=d_to_end)


def enrich_rate(rate: dict, threshold: int = 14, tz: str = "Asia/Kolkata") -> dict:
    """
    Add expiry calculations to a normalised rate dict (non-destructive).
    Returns a new dict with 'expiry' key added.
    """
    exp = calc_expiry(
        rate.get("validity_start_date"),
        rate.get("validity_end_date"),
        threshold=threshold,
        tz=tz,
    )
    return {**rate, "expiry": exp}
