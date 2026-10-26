"""
tests/test_api.py
Tests for FastAPI routes: config endpoint, rates filtering, watchlists,
no CSV upload, credentials never in responses.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.normalize.reference_data import DEFAULT_WATCHED_COUNTRIES, DEFAULT_WATCHED_INDIA, DEFAULT_WATCHED_PORTS
from app.store import database as db


def d(delta: int) -> str:
    return (date.today() + timedelta(days=delta)).isoformat()


def _make_test_client(monkeypatch, tmp_path):
    """Create a TestClient with demo mode and a fresh DB."""
    monkeypatch.setenv("RADAR_MODE", "demo")
    monkeypatch.setenv("RADAR_SYNC_INTERVAL", "0")
    monkeypatch.setenv("ZIPAWORLD_API_KEY", "")
    import app.config.settings as cfg
    cfg._settings = None

    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.seed_defaults(DEFAULT_WATCHED_COUNTRIES, DEFAULT_WATCHED_PORTS, DEFAULT_WATCHED_INDIA, db_path)

    # Patch db module's DB_PATH for this test
    import app.store.database as dmod
    original_path = dmod.DB_PATH
    dmod.DB_PATH = db_path

    from app.main import create_app
    app = create_app()

    # Run startup manually to populate DB
    with TestClient(app) as client:
        yield client, db_path

    dmod.DB_PATH = original_path
    cfg._settings = None


class TestConfigEndpoint:
    def test_config_returns_public_only(self, monkeypatch, tmp_path):
        for client, _ in _make_test_client(monkeypatch, tmp_path):
            resp = client.get("/api/config")
            assert resp.status_code == 200
            data = resp.json()
            # Secrets must not appear
            assert "zipaworld_api_key" not in data
            assert "api_key" not in data
            assert "apiKey" not in data
            assert "isDemo" in data

    def test_config_shows_missing_settings_in_live_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RADAR_MODE", "live")
        monkeypatch.delenv("ZIPAWORLD_API_KEY", raising=False)
        monkeypatch.delenv("ZIPAWORLD_BASE_URL", raising=False)
        import app.config.settings as cfg
        cfg._settings = None
        s = cfg.get_settings()
        public = s.public_dict()
        assert "ZIPAWORLD_API_KEY" in public["missingSettings"]
        assert "ZIPAWORLD_BASE_URL" in public["missingSettings"]
        cfg._settings = None


class TestRatesEndpoint:
    def test_rates_returns_list(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, db_path = next(gen)
        resp = client.get("/api/rates")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data

    def test_rates_pagination(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        resp = client.get("/api/rates?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 10

    def test_rates_search_filter(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        resp = client.get("/api/rates?search=USNYC")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            codes = (item.get("destination_code") or "") + (item.get("origin_code") or "")
            assert "USNYC" in codes or "usnyc" in codes.lower()

    def test_rate_detail_endpoint(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        rates = client.get("/api/rates?page_size=1").json()
        if rates["items"]:
            rate_id = rates["items"][0]["id"]
            resp = client.get(f"/api/rates/{rate_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == rate_id
            assert "expiry" in data

    def test_rate_404(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        resp = client.get("/api/rates/NONEXISTENT_RATE_ID")
        assert resp.status_code == 404

    def test_status_filter_works(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        resp = client.get("/api/rates?status=ACTIVE")
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["expiry"]["status"] == "ACTIVE"


class TestNoCSVUpload:
    def test_no_csv_upload_route(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        # Any upload-like route should return 404 or 405
        resp = client.post("/api/upload", content=b"col1,col2\nv1,v2")
        assert resp.status_code in (404, 405, 422)
        resp2 = client.post("/api/rates/import", content=b"test")
        assert resp2.status_code in (404, 405, 422)

    def test_csv_export_exists(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        resp = client.get("/api/export/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")


class TestWatchlists:
    def test_get_watched_countries(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        resp = client.get("/api/watchlist/countries")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) > 0

    def test_update_watched_countries(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        resp = client.put("/api/watchlist/countries", json={"items": ["US", "GB", "SG"]})
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["items"]) == {"US", "GB", "SG"}

    def test_update_watched_ports(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        resp = client.put("/api/watchlist/ports", json={"items": ["GBLGP", "NLRTM"]})
        assert resp.status_code == 200
        assert "GBLGP" in resp.json()["items"]

    def test_invalid_country_code_rejected(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        resp = client.put("/api/watchlist/countries", json={"items": ["INVALID", "US"]})
        assert resp.status_code == 200
        # "INVALID" has more than 2 chars so should be filtered out
        assert "INVALID" not in resp.json()["items"]
        assert "US" in resp.json()["items"]


class TestSecurityHeaders:
    def test_security_headers_present(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        resp = client.get("/api/config")
        headers = resp.headers
        assert "x-content-type-options" in headers
        assert headers["x-content-type-options"] == "nosniff"
        assert "x-frame-options" in headers
        assert "content-security-policy" in headers

    def test_credentials_not_in_any_api_response(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZIPAWORLD_API_KEY", "SUPER_SECRET_KEY_12345")
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        # Check multiple endpoints
        for url in ["/api/config", "/api/rates", "/api/sync/status"]:
            resp = client.get(url)
            assert "SUPER_SECRET_KEY_12345" not in resp.text


class TestDemoBadge:
    def test_demo_mode_flagged_in_config(self, monkeypatch, tmp_path):
        gen = _make_test_client(monkeypatch, tmp_path)
        client, _ = next(gen)
        resp = client.get("/api/config")
        assert resp.json()["isDemo"] is True
        assert resp.json()["radarMode"] == "demo"


class TestServerlessDatabaseResolution:
    def test_default_path_when_vercel_env_set(self, monkeypatch):
        monkeypatch.setenv("VERCEL", "1")
        from app.store.database import _resolve_default_db_path
        assert _resolve_default_db_path() == Path("/tmp/rates.db")

    def test_default_path_when_aws_lambda_env_set(self, monkeypatch):
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "my_func")
        from app.store.database import _resolve_default_db_path
        assert _resolve_default_db_path() == Path("/tmp/rates.db")

    def test_custom_radar_db_path_takes_priority(self, monkeypatch):
        monkeypatch.setenv("RADAR_DB_PATH", "custom/db.sqlite")
        from app.store.database import _resolve_default_db_path
        assert _resolve_default_db_path() == Path("custom/db.sqlite")

    def test_init_db_falls_back_on_unwritable_path(self, tmp_path):
        import errno
        from unittest.mock import patch
        from app.store import database as dmod

        old_path = dmod.DB_PATH
        target_path = tmp_path / "simulated_readonly" / "rates.db"
        orig_mkdir = Path.mkdir

        def conditional_mkdir(self, *args, **kwargs):
            if str(self) == str(target_path.parent):
                raise OSError(errno.EROFS, "Read-only file system")
            return orig_mkdir(self, *args, **kwargs)

        try:
            with patch.object(Path, "mkdir", side_effect=conditional_mkdir, autospec=True):
                dmod.init_db(target_path)
            assert dmod.DB_PATH == Path("/tmp/rates.db")
        finally:
            dmod.DB_PATH = old_path

    def test_init_db_re_raises_unrelated_oserror(self, tmp_path):
        import errno
        from unittest.mock import patch
        from app.store import database as dmod

        target_path = tmp_path / "simulated_disk_full" / "rates.db"

        def enospc_mkdir(self, *args, **kwargs):
            raise OSError(errno.ENOSPC, "No space left on device")

        with patch.object(Path, "mkdir", side_effect=enospc_mkdir, autospec=True):
            with pytest.raises(OSError) as excinfo:
                dmod.init_db(target_path)
            assert excinfo.value.errno == errno.ENOSPC

    def test_critical_db_init_failure_raises(self):
        from unittest.mock import patch
        from app.main import create_app
        app = create_app()
        with patch("app.store.database.init_db", side_effect=RuntimeError("Fatal DB Error")):
            with pytest.raises(RuntimeError, match="Fatal DB Error"):
                with TestClient(app):
                    pass

    def test_noncritical_sync_failure_does_not_abort_startup(self, monkeypatch, tmp_path):
        from unittest.mock import patch
        from app.main import create_app
        monkeypatch.setenv("RADAR_DB_PATH", str(tmp_path / "test.db"))
        app = create_app()
        with patch("app.main.run_sync", side_effect=Exception("API connection timeout")):
            with TestClient(app) as client:
                resp = client.get("/api/config")
                assert resp.status_code == 200


