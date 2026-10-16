"""
app/client/zipaworld.py
Read-only Zipaworld API client.
- GET requests only
- Auth header never logged
- Exponential backoff retries
- Retry-After for 429
- Pagination: none | page | offset | cursor
- Safety: max pages cap, duplicate-cursor detection
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from ..config.settings import Settings

logger = logging.getLogger(__name__)
_REDACTED = "[REDACTED]"


def _safe_headers(headers: dict) -> dict:
    """Return a copy of headers with auth values redacted for logging."""
    safe = {}
    auth_keys = {"authorization", "x-api-key", "api-key", "apikey", "token"}
    for k, v in headers.items():
        if k.lower() in auth_keys or "secret" in k.lower() or "key" in k.lower():
            safe[k] = _REDACTED
        else:
            safe[k] = v
    return safe


def _get_nested(obj: Any, dotted: str) -> Any:
    """Resolve dotted path from a parsed JSON object."""
    parts = dotted.split(".")
    cur = obj
    for p in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


class ZipaworldAPIError(Exception):
    """Raised when the API returns an unrecoverable error."""
    def __init__(self, message: str, status_code: int | None = None):
        # Never include credential values in the message
        super().__init__(message)
        self.status_code = status_code


class ZipaworldClient:
    def __init__(self, settings: Settings):
        self._s = settings
        self._base_url = settings.zipaworld_base_url.rstrip("/")
        self._rates_path = settings.zipaworld_rates_path
        self._items_path = settings.zipaworld_items_path
        self._auth_headers = settings.auth_headers()  # secret lives only here

    async def fetch_all_rates(self) -> list[dict]:
        """
        Fetch all rate records using the configured pagination style.
        Returns the combined list of raw items.
        Raises ZipaworldAPIError on unrecoverable failure.
        """
        style = self._s.zipaworld_pagination_style.lower()
        if style == "page":
            return await self._fetch_page_style()
        elif style == "offset":
            return await self._fetch_offset_style()
        elif style == "cursor":
            return await self._fetch_cursor_style()
        else:  # "none"
            return await self._fetch_single()

    async def _request(
        self,
        params: dict | None = None,
        timeout: float = 30.0,
    ) -> dict:
        """
        Execute a single GET request with retries + exponential backoff.
        Returns the parsed JSON body.
        """
        url = f"{self._base_url}{self._rates_path}"
        max_retries = 4
        for attempt in range(max_retries):
            wait = 2 ** attempt  # 1, 2, 4, 8 seconds
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(
                        url,
                        headers={**self._auth_headers, "Accept": "application/json"},
                        params=params or {},
                    )
                # 429 – respect Retry-After
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", wait))
                    logger.warning("API rate-limited (429), waiting %ds", retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                # 401/403
                if response.status_code in (401, 403):
                    raise ZipaworldAPIError(
                        f"Authentication failed: HTTP {response.status_code}. "
                        "Check ZIPAWORLD_API_KEY and ZIPAWORLD_AUTH_MODE.",
                        status_code=response.status_code,
                    )
                response.raise_for_status()
                return response.json()

            except httpx.TimeoutException:
                logger.warning("API timeout on attempt %d/%d", attempt + 1, max_retries)
                if attempt == max_retries - 1:
                    raise ZipaworldAPIError("API request timed out after all retries")
                await asyncio.sleep(wait)

            except httpx.NetworkError as exc:
                logger.warning("Network error on attempt %d/%d: %s", attempt + 1, max_retries, type(exc).__name__)
                if attempt == max_retries - 1:
                    raise ZipaworldAPIError(f"Network error: {type(exc).__name__}")
                await asyncio.sleep(wait)

            except ZipaworldAPIError:
                raise

            except httpx.HTTPStatusError as exc:
                raise ZipaworldAPIError(
                    f"API HTTP error: {exc.response.status_code}",
                    status_code=exc.response.status_code,
                )

        raise ZipaworldAPIError("API request failed after all retries")

    def _extract_items(self, body: dict) -> list[dict]:
        items = _get_nested(body, self._items_path)
        if items is None:
            raise ZipaworldAPIError(
                f"Items path '{self._items_path}' not found in API response. "
                "Update ZIPAWORLD_ITEMS_PATH in .env."
            )
        if not isinstance(items, list):
            raise ZipaworldAPIError(
                f"Expected list at items path '{self._items_path}', got {type(items).__name__}."
            )
        return items

    async def _fetch_single(self) -> list[dict]:
        body = await self._request()
        return self._extract_items(body)

    async def _fetch_page_style(self) -> list[dict]:
        s = self._s
        page = 1
        all_items: list[dict] = []
        max_pages = s.zipaworld_max_pages

        for _ in range(max_pages):
            body = await self._request({
                s.zipaworld_page_param: page,
                s.zipaworld_page_size_param: s.zipaworld_page_size,
            })
            items = self._extract_items(body)
            if not items:
                break
            all_items.extend(items)
            logger.info("Page %d: fetched %d items (total %d)", page, len(items), len(all_items))
            if len(items) < s.zipaworld_page_size:
                break
            page += 1

        return all_items

    async def _fetch_offset_style(self) -> list[dict]:
        s = self._s
        offset = 0
        limit = s.zipaworld_page_size
        all_items: list[dict] = []
        max_pages = s.zipaworld_max_pages

        for _ in range(max_pages):
            body = await self._request({
                s.zipaworld_offset_param: offset,
                s.zipaworld_limit_param: limit,
            })
            items = self._extract_items(body)
            if not items:
                break
            all_items.extend(items)
            logger.info("Offset %d: fetched %d items (total %d)", offset, len(items), len(all_items))
            if len(items) < limit:
                break
            offset += limit

        return all_items

    async def _fetch_cursor_style(self) -> list[dict]:
        s = self._s
        cursor: str | None = None
        all_items: list[dict] = []
        seen_cursors: set[str] = set()
        max_pages = s.zipaworld_max_pages

        for _ in range(max_pages):
            params: dict = {}
            if cursor:
                params[s.zipaworld_cursor_param] = cursor
            body = await self._request(params)
            items = self._extract_items(body)
            all_items.extend(items)
            logger.info("Cursor page: fetched %d items (total %d)", len(items), len(all_items))

            next_cursor = _get_nested(body, s.zipaworld_next_cursor_path) if s.zipaworld_next_cursor_path else None
            if not next_cursor or not items:
                break
            next_str = str(next_cursor)
            if next_str in seen_cursors:
                logger.warning("Duplicate cursor detected – stopping pagination")
                break
            seen_cursors.add(next_str)
            cursor = next_str

        return all_items
