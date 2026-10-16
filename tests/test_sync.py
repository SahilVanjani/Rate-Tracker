"""
tests/test_sync.py
Tests for sync engine behaviour: empty response protection, credential safety,
pagination dedup, history from snapshots only.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest
import respx
import httpx

from app.sync.scheduler import run_sync
from app.store import database as db
from app.config.settings import Settings


def d(delta: int) -> str:
    return (date.today() + timedelta(days=delta)).isoformat()


def _demo_settings(monkeypatch, tmp_path) -> Settings:
    monkeypatch.setenv("RADAR_MODE", "demo")
    monkeypatch.setenv("RADAR_SYNC_INTERVAL", "0")
    monkeypatch.setenv("RADAR_TIMEZONE", "Asia/Kolkata")
    import app.config.settings as cfg
    cfg._settings = None
    s = cfg.get_settings()
    return s


def _live_settings(monkeypatch, tmp_path) -> Settings:
    monkeypatch.setenv("RADAR_MODE", "live")
    monkeypatch.setenv("ZIPAWORLD_BASE_URL", "https://fake-api.example.com")
    monkeypatch.setenv("ZIPAWORLD_RATES_PATH", "/rates")
    monkeypatch.setenv("ZIPAWORLD_AUTH_MODE", "header")
    monkeypatch.setenv("ZIPAWORLD_AUTH_HEADER_NAME", "X-Api-Key")
    monkeypatch.setenv("ZIPAWORLD_API_KEY", "SECRET_KEY_DO_NOT_LOG")
    monkeypatch.setenv("ZIPAWORLD_ITEMS_PATH", "data")
    monkeypatch.setenv("ZIPAWORLD_PAGINATION_STYLE", "none")
    monkeypatch.setenv("RADAR_SYNC_INTERVAL", "0")
    import app.config.settings as cfg
    cfg._settings = None
    return cfg.get_settings()


class TestDemoSync:
    def test_demo_sync_loads_records(self, monkeypatch, tmp_path):
        s = _demo_settings(monkeypatch, tmp_path)
        db_path = tmp_path / "rates.db"
        db.init_db(db_path)
        result = asyncio.get_event_loop().run_until_complete(
            run_sync(s, db_path=db_path, is_demo=True)
        )
        assert result["status"] == "success"
        assert result["recordsStored"] > 0

    def test_demo_sync_creates_history(self, monkeypatch, tmp_path):
        s = _demo_settings(monkeypatch, tmp_path)
        db_path = tmp_path / "rates.db"
        db.init_db(db_path)
        asyncio.get_event_loop().run_until_complete(
            run_sync(s, db_path=db_path, is_demo=True)
        )
        history = db.get_history(path=db_path)
        # First sync: all records are "added"
        added = [h for h in history if h["change_type"] == "added"]
        assert len(added) > 0

    def test_empty_api_response_does_not_wipe_data(self, monkeypatch, tmp_path):
        """If API returns 0 records and data is stored, keep stored data."""
        s = _demo_settings(monkeypatch, tmp_path)
        db_path = tmp_path / "rates.db"
        db.init_db(db_path)
        # First sync to populate
        asyncio.get_event_loop().run_until_complete(
            run_sync(s, db_path=db_path, is_demo=True)
        )
        count_before = db.count_rates(db_path)
        assert count_before > 0

        # Now simulate a sync that would return 0 records
        # We override generate_demo_rates temporarily
        import app.api.demo_data as dd
        original = dd.generate_demo_rates
        dd.generate_demo_rates = lambda: []
        try:
            result = asyncio.get_event_loop().run_until_complete(
                run_sync(s, db_path=db_path, is_demo=True)
            )
        finally:
            dd.generate_demo_rates = original

        assert result["status"] == "failed"
        count_after = db.count_rates(db_path)
        assert count_after == count_before  # data preserved


class TestLiveSyncErrorHandling:
    @respx.mock
    def test_auth_failure_handled(self, monkeypatch, tmp_path):
        s = _live_settings(monkeypatch, tmp_path)
        db_path = tmp_path / "rates.db"
        db.init_db(db_path)

        respx.get("https://fake-api.example.com/rates").mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )

        result = asyncio.get_event_loop().run_until_complete(
            run_sync(s, db_path=db_path, is_demo=False)
        )
        assert result["status"] == "failed"
        # Error message must NOT contain the API key
        assert "SECRET_KEY_DO_NOT_LOG" not in str(result.get("reason", ""))

    @respx.mock
    def test_credentials_never_in_error(self, monkeypatch, tmp_path):
        s = _live_settings(monkeypatch, tmp_path)
        db_path = tmp_path / "rates.db"
        db.init_db(db_path)

        respx.get("https://fake-api.example.com/rates").mock(
            return_value=httpx.Response(403, json={"error": "Forbidden"})
        )

        result = asyncio.get_event_loop().run_until_complete(
            run_sync(s, db_path=db_path, is_demo=False)
        )
        assert "SECRET_KEY_DO_NOT_LOG" not in str(result)

    @respx.mock
    def test_successful_sync_marks_live(self, monkeypatch, tmp_path):
        s = _live_settings(monkeypatch, tmp_path)
        db_path = tmp_path / "rates.db"
        db.init_db(db_path)

        respx.get("https://fake-api.example.com/rates").mock(
            return_value=httpx.Response(200, json={"data": [
                {
                    "id": "T1",
                    "originName": "INMUN,Mundra(India)",
                    "destinationName": "USNYC,New York(US)",
                    "shippingLineName": "MSC AGENCY",
                    "rate": 2500,
                    "currency": "USD",
                    "validityEndDate": d(30),
                    "rateType": "OE",
                }
            ]})
        )
        result = asyncio.get_event_loop().run_until_complete(
            run_sync(s, db_path=db_path, is_demo=False)
        )
        assert result["status"] == "success"
        assert db.count_rates(db_path) == 1

    @respx.mock
    def test_pagination_no_duplicate_records(self, monkeypatch, tmp_path):
        """Page-style pagination fetching same content twice should deduplicate."""
        monkeypatch.setenv("RADAR_MODE", "live")
        monkeypatch.setenv("ZIPAWORLD_BASE_URL", "https://fake-api.example.com")
        monkeypatch.setenv("ZIPAWORLD_RATES_PATH", "/rates")
        monkeypatch.setenv("ZIPAWORLD_AUTH_MODE", "bearer")
        monkeypatch.setenv("ZIPAWORLD_API_KEY", "TOKEN")
        monkeypatch.setenv("ZIPAWORLD_ITEMS_PATH", "items")
        monkeypatch.setenv("ZIPAWORLD_PAGINATION_STYLE", "page")
        monkeypatch.setenv("ZIPAWORLD_PAGE_PARAM", "page")
        monkeypatch.setenv("ZIPAWORLD_PAGE_SIZE_PARAM", "size")
        monkeypatch.setenv("ZIPAWORLD_PAGE_SIZE", "2")
        import app.config.settings as cfg
        cfg._settings = None
        s = cfg.get_settings()

        db_path = tmp_path / "rates.db"
        db.init_db(db_path)

        items_p1 = [
            {"id": "R1", "originName": "INMUN,Mundra(India)", "destinationName": "USNYC,New York(US)",
             "shippingLineName": "MSC", "rate": 1000, "currency": "USD", "validityEndDate": d(30)},
            {"id": "R2", "originName": "INNSA,Nhava Sheva(India)", "destinationName": "GBLGP,London(UK)",
             "shippingLineName": "Maersk", "rate": 2000, "currency": "USD", "validityEndDate": d(25)},
        ]

        call_count = {"n": 0}

        def side_effect(request: httpx.Request):
            call_count["n"] += 1
            page = request.url.params.get("page", "1")
            if page == "1":
                return httpx.Response(200, json={"items": items_p1})
            else:
                return httpx.Response(200, json={"items": []})

        respx.get("https://fake-api.example.com/rates").mock(side_effect=side_effect)

        result = asyncio.get_event_loop().run_until_complete(
            run_sync(s, db_path=db_path, is_demo=False)
        )
        assert result["status"] == "success"
        assert db.count_rates(db_path) == 2
        assert result.get("duplicates", 0) == 0


class TestHistory:
    def test_history_only_from_snapshots(self, monkeypatch, tmp_path):
        """History must come from real snapshot diffs, not fabricated."""
        s = _demo_settings(monkeypatch, tmp_path)
        db_path = tmp_path / "rates.db"
        db.init_db(db_path)

        # No sync yet → no history
        history = db.get_history(path=db_path)
        assert history == []

        # After sync → history from snapshots
        asyncio.get_event_loop().run_until_complete(
            run_sync(s, db_path=db_path, is_demo=True)
        )
        history = db.get_history(path=db_path)
        assert len(history) > 0
        # All entries are real DB rows with proper fields
        assert all("change_type" in h for h in history)
        assert all("rate_id" in h for h in history)
