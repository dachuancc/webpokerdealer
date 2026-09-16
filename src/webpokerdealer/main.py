"""FastAPI application factory and entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import __version__
from .web.routes import router as http_router
from .web.ws import router as ws_router

BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    app = FastAPI(title="Web Poker Dealer", version=__version__)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    app.include_router(http_router)
    app.include_router(ws_router)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
