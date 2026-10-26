"""
app/config/settings.py
Pydantic-settings config. Secrets are NEVER logged or returned to the frontend.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Mode ──────────────────────────────────────────────────────────────
    radar_mode: Literal["live", "demo"] = "live"

    # ── App ───────────────────────────────────────────────────────────────
    port: int = 3000
    host: str = "127.0.0.1"
    radar_timezone: str = "Asia/Kolkata"
    radar_expiry_threshold: int = 14  # 1-90 days
    radar_min_carriers: int = 2       # 1-10
    radar_sync_interval: int = 60     # minutes; 0 = disabled
    radar_admin_token: str = ""

    # ── Zipaworld API (live mode) ─────────────────────────────────────────
    zipaworld_base_url: str = ""
    zipaworld_rates_path: str = ""
    zipaworld_auth_mode: str = ""          # "header" | "bearer"
    zipaworld_auth_header_name: str = "X-API-Key"
    zipaworld_api_key: str = ""            # SECRET – never serialised to frontend
    zipaworld_client_id: str = ""          # SECRET – never serialised to frontend
    zipaworld_items_path: str = ""
    zipaworld_pagination_style: str = "none"  # none|page|offset|cursor
    zipaworld_page_param: str = "page"
    zipaworld_page_size_param: str = "pageSize"
    zipaworld_page_size: int = 100
    zipaworld_offset_param: str = "offset"
    zipaworld_limit_param: str = "limit"
    zipaworld_cursor_param: str = "cursor"
    zipaworld_next_cursor_path: str = ""
    zipaworld_max_pages: int = 500

    # ── Computed ──────────────────────────────────────────────────────────
    @field_validator("radar_expiry_threshold")
    @classmethod
    def clamp_threshold(cls, v: int) -> int:
        return max(1, min(90, v))

    @field_validator("radar_min_carriers")
    @classmethod
    def clamp_carriers(cls, v: int) -> int:
        return max(1, min(10, v))

    # ── API readiness ─────────────────────────────────────────────────────
    _REQUIRED_API_KEYS = [
        "zipaworld_base_url",
        "zipaworld_rates_path",
        "zipaworld_auth_mode",
        "zipaworld_api_key",
        "zipaworld_items_path",
        "zipaworld_pagination_style",
    ]
    # Human-readable env-var names exposed in the "missing" list
    _REQUIRED_ENV_NAMES = [
        "ZIPAWORLD_BASE_URL",
        "ZIPAWORLD_RATES_PATH",
        "ZIPAWORLD_AUTH_MODE",
        "ZIPAWORLD_API_KEY",
        "ZIPAWORLD_ITEMS_PATH",
        "ZIPAWORLD_PAGINATION_STYLE",
    ]

    @property
    def is_demo(self) -> bool:
        return self.radar_mode == "demo"

    @property
    def missing_settings(self) -> list[str]:
        """Return env-var names that are empty (live mode only). Never returns values."""
        if self.is_demo:
            return []
        missing = []
        for attr, env_name in zip(self._REQUIRED_API_KEYS, self._REQUIRED_ENV_NAMES):
            if not getattr(self, attr):
                missing.append(env_name)
        return missing

    @property
    def api_configured(self) -> bool:
        return not self.is_demo and len(self.missing_settings) == 0

    def public_dict(self) -> dict:
        """Safe dict for the frontend – NO secrets."""
        return {
            "isDemo": self.is_demo,
            "radarMode": self.radar_mode,
            "apiConfigured": self.api_configured,
            "missingSettings": self.missing_settings,  # names only, never values
            "timezone": self.radar_timezone,
            "expiryThreshold": self.radar_expiry_threshold,
            "minCarriers": self.radar_min_carriers,
            "syncInterval": self.radar_sync_interval,
            "hasAdminToken": bool(self.radar_admin_token),
            "paginationStyle": self.zipaworld_pagination_style,
        }

    def auth_headers(self) -> dict[str, str]:
        """Build auth headers for the Zipaworld API. Used only on the backend."""
        if self.zipaworld_auth_mode == "bearer":
            return {"Authorization": f"Bearer {self.zipaworld_api_key}"}
        if self.zipaworld_auth_mode == "header":
            return {self.zipaworld_auth_header_name: self.zipaworld_api_key}
        return {}

    def load_field_map(self) -> dict:
        path = Path("config") / "field-map.json"
        if not path.exists():
            path = Path(__file__).resolve().parent.parent.parent / "config" / "field-map.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}


# Singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
