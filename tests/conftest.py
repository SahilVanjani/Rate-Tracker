"""tests/conftest.py – shared fixtures for all tests."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.normalize.reference_data import DEFAULT_WATCHED_COUNTRIES, DEFAULT_WATCHED_INDIA, DEFAULT_WATCHED_PORTS
from app.store import database as db


@pytest.fixture
def tmp_db(tmp_path):
    """Fresh SQLite database for each test."""
    path = tmp_path / "test_rates.db"
    db.init_db(path)
    db.seed_defaults(DEFAULT_WATCHED_COUNTRIES, DEFAULT_WATCHED_PORTS, DEFAULT_WATCHED_INDIA, path)
    return path


@pytest.fixture
def demo_settings(monkeypatch):
    """Settings configured for demo mode."""
    monkeypatch.setenv("RADAR_MODE", "demo")
    monkeypatch.setenv("RADAR_EXPIRY_THRESHOLD", "14")
    monkeypatch.setenv("RADAR_MIN_CARRIERS", "2")
    monkeypatch.setenv("RADAR_TIMEZONE", "Asia/Kolkata")
    monkeypatch.setenv("RADAR_SYNC_INTERVAL", "0")
    # Clear singleton so settings re-reads env
    import app.config.settings as cfg
    cfg._settings = None
    s = cfg.get_settings()
    yield s
    cfg._settings = None


@pytest.fixture
def live_unconfigured_settings(monkeypatch):
    """Settings in live mode with missing API config."""
    monkeypatch.setenv("RADAR_MODE", "live")
    monkeypatch.delenv("ZIPAWORLD_API_KEY", raising=False)
    import app.config.settings as cfg
    cfg._settings = None
    s = cfg.get_settings()
    yield s
    cfg._settings = None


@pytest.fixture
def field_map():
    """Load the real field-map.json for normalisation tests."""
    import json
    p = Path("config") / "field-map.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"fields": {
        "id": {"paths": ["id"]},
        "originName": {"paths": ["originName"]},
        "destinationName": {"paths": ["destinationName"]},
        "shipmentMode": {"paths": ["shipmentMode"]},
        "containerName": {"paths": ["containerName"]},
        "shippingLineName": {"paths": ["shippingLineName"]},
        "rate": {"paths": ["rate"]},
        "currency": {"paths": ["currency"]},
        "validityStartDate": {"paths": ["validityStartDate"]},
        "validityEndDate": {"paths": ["validityEndDate"]},
        "rateType": {"paths": ["rateType"]},
        "createdAt": {"paths": ["createdAt"]},
        "updatedAt": {"paths": ["updatedAt"]},
        "sourceStatus": {"paths": ["status"]},
    }}
