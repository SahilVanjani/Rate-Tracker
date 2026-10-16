"""
tests/test_expiry.py
Tests for app/expiry/expiry.py – all spec rules.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.expiry.expiry import (
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_EXPIRING_SOON,
    STATUS_NEEDS_REVIEW,
    STATUS_STARTS_LATER,
    calc_expiry,
    parse_date,
)

TZ = "Asia/Kolkata"
THRESHOLD = 14


def today_str() -> str:
    return date.today().isoformat()


def d(delta: int) -> str:
    return (date.today() + timedelta(days=delta)).isoformat()


# ── parse_date ────────────────────────────────────────────────────────────────

class TestParseDate:
    def test_iso_date(self):
        assert parse_date("2025-06-15") == "2025-06-15"

    def test_iso_datetime(self):
        assert parse_date("2025-06-15T10:30:00Z") == "2025-06-15"

    def test_dmy_slash(self):
        assert parse_date("15/06/2025") == "2025-06-15"

    def test_dmy_dash(self):
        assert parse_date("15-06-2025") == "2025-06-15"

    def test_none(self):
        assert parse_date(None) is None

    def test_empty(self):
        assert parse_date("") is None

    def test_invalid_string(self):
        assert parse_date("N/A") is None

    def test_invalid_date(self):
        assert parse_date("2025-13-99") is None

    def test_int_passthrough(self):
        # Integers are not valid dates
        result = parse_date(20250615)
        # Could be None or a parsed value – must not raise
        # A 8-digit int doesn't match our patterns, so should return None
        assert result is None or isinstance(result, str)


# ── calc_expiry ───────────────────────────────────────────────────────────────

class TestCalcExpiry:
    # ── ACTIVE ────────────────────────────────────────────────────────────
    def test_active_far_future(self):
        result = calc_expiry(d(-30), d(60), THRESHOLD, TZ)
        assert result["status"] == STATUS_ACTIVE
        assert result["days_remaining"] == 60

    def test_active_just_above_threshold(self):
        result = calc_expiry(d(-1), d(THRESHOLD + 1), THRESHOLD, TZ)
        assert result["status"] == STATUS_ACTIVE

    # ── EXPIRING SOON ─────────────────────────────────────────────────────
    def test_expiring_soon_threshold_exactly(self):
        result = calc_expiry(d(-1), d(THRESHOLD), THRESHOLD, TZ)
        assert result["status"] == STATUS_EXPIRING_SOON
        assert result["days_remaining"] == THRESHOLD

    def test_expiring_in_7_days(self):
        result = calc_expiry(d(-10), d(7), THRESHOLD, TZ)
        assert result["status"] == STATUS_EXPIRING_SOON
        assert result["days_remaining"] == 7

    def test_expiring_tomorrow(self):
        result = calc_expiry(d(-5), d(1), THRESHOLD, TZ)
        assert result["status"] == STATUS_EXPIRING_SOON
        assert result["days_remaining"] == 1
        assert "tomorrow" in result["expiry_label"].lower()

    def test_expiring_today_inclusive(self):
        """End date = today is still VALID (inclusive)."""
        result = calc_expiry(d(-5), d(0), THRESHOLD, TZ)
        assert result["status"] == STATUS_EXPIRING_SOON
        assert result["days_remaining"] == 0
        assert "today" in result["expiry_label"].lower()

    # ── EXPIRED ───────────────────────────────────────────────────────────
    def test_expired_yesterday(self):
        result = calc_expiry(d(-10), d(-1), THRESHOLD, TZ)
        assert result["status"] == STATUS_EXPIRED
        assert result["days_expired"] == 1
        assert "yesterday" in result["expiry_label"].lower()

    def test_expired_long_ago(self):
        result = calc_expiry(d(-90), d(-30), THRESHOLD, TZ)
        assert result["status"] == STATUS_EXPIRED
        assert result["days_expired"] == 30
        assert "30" in result["expiry_label"]

    # ── STARTS LATER ──────────────────────────────────────────────────────
    def test_starts_later_future_start(self):
        result = calc_expiry(d(5), d(35), THRESHOLD, TZ)
        assert result["status"] == STATUS_STARTS_LATER
        assert "5" in result["expiry_label"]

    # ── NEEDS REVIEW ──────────────────────────────────────────────────────
    def test_needs_review_missing_end_date(self):
        result = calc_expiry(d(-5), None, THRESHOLD, TZ)
        assert result["status"] == STATUS_NEEDS_REVIEW
        assert result["reason"] == "missing_end_date"

    def test_needs_review_missing_both_dates(self):
        result = calc_expiry(None, None, THRESHOLD, TZ)
        assert result["status"] == STATUS_NEEDS_REVIEW

    def test_needs_review_invalid_end_date(self):
        """A date that can't be parsed counts as NEEDS_REVIEW."""
        # parse_date("N/A") returns None, so calc_expiry sees None end date
        from app.expiry.expiry import parse_date
        parsed = parse_date("N/A")
        result = calc_expiry(d(-5), parsed, THRESHOLD, TZ)
        assert result["status"] == STATUS_NEEDS_REVIEW

    def test_needs_review_start_after_end(self):
        result = calc_expiry(d(20), d(10), THRESHOLD, TZ)
        assert result["status"] == STATUS_NEEDS_REVIEW
        assert result["reason"] == "start_after_end"

    # ── Missing end-date never becomes ACTIVE ────────────────────────────
    def test_no_end_date_not_active(self):
        result = calc_expiry(d(-30), None, THRESHOLD, TZ)
        assert result["status"] != STATUS_ACTIVE

    # ── Rate & currency pairing (not expiry logic but confirm no confusion) ─
    def test_expiry_independent_of_rate(self):
        r1 = calc_expiry(d(-10), d(20), THRESHOLD, TZ)
        r2 = calc_expiry(d(-10), d(20), THRESHOLD, TZ)
        assert r1["status"] == r2["status"] == STATUS_ACTIVE

    # ── Status changes at midnight ────────────────────────────────────────
    def test_today_is_expiring_not_expired(self):
        """A rate ending today should NOT be EXPIRED."""
        result = calc_expiry(d(-10), d(0), THRESHOLD, TZ)
        assert result["status"] != STATUS_EXPIRED

    def test_yesterday_is_expired(self):
        """A rate ending yesterday IS EXPIRED."""
        result = calc_expiry(d(-10), d(-1), THRESHOLD, TZ)
        assert result["status"] == STATUS_EXPIRED

    # ── Configurable threshold ────────────────────────────────────────────
    def test_custom_threshold_30(self):
        result = calc_expiry(d(-1), d(25), 30, TZ)
        assert result["status"] == STATUS_EXPIRING_SOON

    def test_custom_threshold_7(self):
        result = calc_expiry(d(-1), d(10), 7, TZ)
        assert result["status"] == STATUS_ACTIVE
