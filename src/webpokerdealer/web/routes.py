"""HTTP routes: landing page, table creation, joining, board and player pages."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from ..config import settings
from ..game.rooms import rooms
from ..game.table import GameError
from .ws import hub

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _asset_version() -> str:
    """Short hash of the static assets, used to bust browser caches.

    Static files change without a build step, so templates append ``?v=<hash>``.
    The hash changes whenever any JS/CSS file changes (recomputed on restart).
    """
    digest = hashlib.sha256()
    for path in sorted((BASE_DIR / "static").rglob("*")):
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:8]


templates.env.globals["asset_v"] = _asset_version()

router = APIRouter()


class JoinRequest(BaseModel):
    name: str = Field(min_length=1, max_length=16)


class HostAuthRequest(BaseModel):
    pin: str = Field(min_length=1, max_length=12)


def _require_table(code: str):
    table = rooms.get(code)
    if table is None:
        raise HTTPException(status_code=404, detail="牌桌不存在或已过期")
    return table


def _public_base_url(request: Request) -> str:
    """Best-effort external base URL, so QR codes work from other devices."""
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def _qr_svg(data: str) -> str:
    image = qrcode.make(
        data,
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=10,
        border=2,
    )
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@router.post("/api/tables")
async def create_table() -> dict[str, str]:
    table = rooms.create()
    # The creator is the host: hand back the PIN (to show/recover) and the token
    # the board page stores locally.
    return {"code": table.code, "pin": table.pin, "host_token": table.host_token}


@router.post("/api/tables/{code}/host")
async def host_auth(code: str, body: HostAuthRequest) -> dict[str, str]:
    """Exchange the host PIN for the host token (used by the board page)."""
    table = _require_table(code)
    if not table.verify_pin(body.pin):
        raise HTTPException(status_code=403, detail="PIN 不正确")
    return {"host_token": table.host_token}


@router.post("/api/tables/{code}/join")
async def join_table(code: str, body: JoinRequest) -> dict[str, object]:
    table = _require_table(code)
    try:
        player = table.add_player(body.name)
    except GameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await hub.broadcast(table)
    return {"player_id": player.id, "token": player.token, "seat": player.seat, "code": table.code}


@router.get("/board/{code}", response_class=HTMLResponse)
async def board_page(request: Request, code: str) -> HTMLResponse:
    table = _require_table(code)
    join_url = f"{_public_base_url(request)}/play/{table.code}"
    return templates.TemplateResponse(
        request,
        "board.html",
        {"code": table.code, "join_url": join_url, "qr_svg": _qr_svg(join_url)},
    )


@router.get("/play/{code}", response_class=HTMLResponse)
async def player_page(request: Request, code: str) -> HTMLResponse:
    table = _require_table(code)
    return templates.TemplateResponse(request, "player.html", {"code": table.code})
