"""
app/main.py
FastAPI application factory: middleware, static files, startup/shutdown lifecycle.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config.settings import get_settings
from .normalize.reference_data import (
    DEFAULT_WATCHED_COUNTRIES, DEFAULT_WATCHED_INDIA, DEFAULT_WATCHED_PORTS,
)
from .store import database as db
from .sync.scheduler import run_sync, start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Zipaworld Rate Radar",
        version="1.0.0",
        docs_url=None,  # disable Swagger UI in production
        redoc_url=None,
    )

    # ── Security headers middleware ────────────────────────────────────────
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self';"
        )
        return response

    # ── CORS (localhost only) ─────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["*"],
    )

    # ── API routes ────────────────────────────────────────────────────────
    app.include_router(router)

    # ── Static files ──────────────────────────────────────────────────────
    static_path = Path(__file__).parent.parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

        @app.get("/", include_in_schema=False)
        async def serve_root():
            index = static_path / "index.html"
            if index.exists():
                return FileResponse(str(index))
            return Response("Not found", status_code=404)

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            """Serve index.html for all non-API paths (SPA routing)."""
            index = static_path / "index.html"
            if index.exists():
                return FileResponse(str(index))
            return Response("Not found", status_code=404)

    # ── Lifecycle ─────────────────────────────────────────────────────────
    @app.on_event("startup")
    async def startup():
        logger.info("=== Zipaworld Rate Radar starting ===")
        logger.info("Mode: %s", settings.radar_mode.upper())

        # ── Critical: Database initialization & seeding ──────────────────────
        try:
            db.init_db()
            db.seed_defaults(DEFAULT_WATCHED_COUNTRIES, DEFAULT_WATCHED_PORTS, DEFAULT_WATCHED_INDIA)
        except Exception as exc:
            logger.critical("Fatal error during database initialization: %s", exc, exc_info=True)
            raise

        # ── Non-critical: Initial sync on startup ─────────────────────────────
        if settings.is_demo or settings.api_configured:
            logger.info("Running initial sync on startup…")
            try:
                await run_sync(settings, is_demo=settings.is_demo)
            except Exception as exc:
                logger.warning("Initial synchronization failed on startup (non-fatal): %s", exc, exc_info=True)

        # ── Non-critical: Auto-sync scheduler ─────────────────────────────────
        try:
            start_scheduler(settings)
        except Exception as exc:
            logger.warning("Could not start background scheduler (non-fatal): %s", exc, exc_info=True)

    @app.on_event("shutdown")
    async def shutdown():
        stop_scheduler()
        logger.info("=== Rate Radar shutdown ===")

    return app


app = create_app()
