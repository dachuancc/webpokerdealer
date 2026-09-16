"""WebSocket layer: one connection per device, filtered state per connection.

Every device receives the state it is allowed to see:

* ``role=board``  -> :meth:`Table.board_state` (no hole cards before showdown)
* ``role=player`` -> :meth:`Table.player_state` (public info + own hole cards)

This is the one invariant that makes the whole thing work: hole cards never
leave the server except to their owner (and at showdown, to everyone).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..game.rooms import rooms
from ..game.table import GameError, Table

router = APIRouter()


class Connection:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.code: str = ""
        self.role: str = "player"
        self.player_id: str | None = None


class Hub:
    """Tracks live connections per table and broadcasts filtered state."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[Connection]] = {}

    def add(self, conn: Connection) -> None:
        self._rooms.setdefault(conn.code, set()).add(conn)

    def remove(self, conn: Connection) -> None:
        conns = self._rooms.get(conn.code)
        if conns is not None:
            conns.discard(conn)
            if not conns:
                self._rooms.pop(conn.code, None)

    async def send_state(self, conn: Connection, table: Table) -> None:
        if conn.role == "board":
            state = table.board_state()
        else:
            state = table.player_state(conn.player_id or "")
        await conn.ws.send_json({"type": "state", "role": conn.role, "state": state})

    async def broadcast(self, table: Table) -> None:
        for conn in list(self._rooms.get(table.code, ())):
            try:
                await self.send_state(conn, table)
            except Exception:
                # A dead socket must not break the broadcast to everyone else.
                self.remove(conn)


hub = Hub()


def _error(message: str) -> dict[str, Any]:
    return {"type": "error", "message": message}


async def _handle_message(conn: Connection, table: Table, msg: dict[str, Any]) -> None:
    if msg.get("type") == "ping":
        await conn.ws.send_json({"type": "pong"})
        return
    if msg.get("type") != "action":
        await conn.ws.send_json(_error("未知消息类型"))
        return

    action = msg.get("action")
    try:
        if conn.role == "board":
            if action == "start_hand":
                table.start_hand()
            elif action == "next_street":
                table.next_street()
            elif action == "reset":
                table.reset()
            elif action == "remove_player":
                table.remove_player(str(msg.get("player_id", "")))
            else:
                raise GameError("未知操作")
        else:
            if conn.player_id is None:
                raise GameError("身份无效")
            if action == "fold":
                table.set_folded(conn.player_id, True)
            elif action == "unfold":
                table.set_folded(conn.player_id, False)
            else:
                raise GameError("未知操作")
    except GameError as exc:
        await conn.ws.send_json(_error(str(exc)))
        return

    await hub.broadcast(table)


@router.websocket("/ws/{code}")
async def ws_endpoint(ws: WebSocket, code: str) -> None:
    await ws.accept()
    table = rooms.get(code)
    if table is None:
        await ws.send_json(_error("牌桌不存在或已过期"))
        await ws.close()
        return

    conn = Connection(ws)
    conn.code = table.code
    role = ws.query_params.get("role", "player")
    conn.role = "board" if role == "board" else "player"

    if conn.role == "player":
        player = table.find_by_token(ws.query_params.get("token", ""))
        if player is None:
            await ws.send_json(_error("身份校验失败，请重新入座"))
            await ws.close()
            return
        conn.player_id = player.id
        player.connected = True

    # Broadcast also delivers the initial state to this connection, so every
    # client gets exactly one state per change.
    hub.add(conn)
    await hub.broadcast(table)

    try:
        while True:
            msg = await ws.receive_json()
            await _handle_message(conn, table, msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        # Malformed payloads shouldn't kill the server; just drop the connection.
        pass
    finally:
        if conn.player_id is not None:
            player = table.players.get(conn.player_id)
            if player is not None:
                player.connected = False
        hub.remove(conn)
        await hub.broadcast(table)
