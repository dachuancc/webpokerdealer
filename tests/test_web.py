from fastapi.testclient import TestClient

from webpokerdealer.main import app

client = TestClient(app)


def create_table() -> str:
    res = client.post("/api/tables")
    assert res.status_code == 200
    return res.json()["code"]


def join(code: str, name: str) -> dict:
    res = client.post(f"/api/tables/{code}/join", json={"name": name})
    assert res.status_code == 200, res.text
    return res.json()


def test_healthz():
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_index_page_loads():
    res = client.get("/")
    assert res.status_code == 200
    assert "Web Poker Dealer" in res.text


def test_create_and_open_board_page():
    code = create_table()
    res = client.get(f"/board/{code}")
    assert res.status_code == 200
    assert code in res.text
    assert "<svg" in res.text  # QR code rendered


def test_board_page_unknown_table_is_404():
    assert client.get("/board/ZZZZ").status_code == 404


def test_join_rejects_blank_name():
    code = create_table()
    res = client.post(f"/api/tables/{code}/join", json={"name": ""})
    assert res.status_code == 422


def test_join_unknown_table_is_404():
    res = client.post("/api/tables/ZZZZ/join", json={"name": "Alice"})
    assert res.status_code == 404


def test_player_page_loads():
    code = create_table()
    res = client.get(f"/play/{code}")
    assert res.status_code == 200
    assert code in res.text


def test_board_websocket_start_hand_flow():
    code = create_table()
    join(code, "Alice")
    join(code, "Bob")

    with client.websocket_connect(f"/ws/{code}?role=board") as ws:
        state = ws.receive_json()
        assert state["type"] == "state"
        assert state["role"] == "board"
        assert len(state["state"]["players"]) == 2
        # No hole cards are leaked to the board before the showdown.
        assert all("hole" not in p for p in state["state"]["players"])

        ws.send_json({"type": "action", "action": "start_hand"})
        state = ws.receive_json()["state"]
        assert state["street"] == "preflop"
        assert state["hand_number"] == 1

        ws.send_json({"type": "action", "action": "next_street"})
        state = ws.receive_json()["state"]
        assert state["street"] == "flop"
        assert len(state["community"]) == 3


def test_board_showdown_is_a_separate_action():
    code = create_table()
    join(code, "Alice")
    join(code, "Bob")

    with client.websocket_connect(f"/ws/{code}?role=board") as ws:
        ws.receive_json()
        ws.send_json({"type": "action", "action": "start_hand"})
        ws.receive_json()
        # Advance only through the deal; the board never auto-shows-down.
        ws.send_json({"type": "action", "action": "next_street"})
        assert ws.receive_json()["state"]["street"] == "flop"
        ws.send_json({"type": "action", "action": "next_street"})
        assert ws.receive_json()["state"]["street"] == "turn"
        ws.send_json({"type": "action", "action": "next_street"})
        state = ws.receive_json()["state"]
        assert state["street"] == "river"
        # Now the explicit showdown reveals hands and records history.
        ws.send_json({"type": "action", "action": "showdown"})
        state = ws.receive_json()["state"]
        assert state["street"] == "showdown"
        assert state["history"][-1]["hand_number"] == 1
        assert state["history"][-1]["showdown"] is True


def test_board_can_start_next_hand_mid_hand():
    code = create_table()
    join(code, "Alice")
    join(code, "Bob")

    with client.websocket_connect(f"/ws/{code}?role=board") as ws:
        ws.receive_json()
        ws.send_json({"type": "action", "action": "start_hand"})
        ws.receive_json()
        # No showdown needed: the host may start hand 2 right away.
        ws.send_json({"type": "action", "action": "start_hand"})
        state = ws.receive_json()["state"]
        assert state["street"] == "preflop"
        assert state["hand_number"] == 2
        assert state["history"][-1]["hand_number"] == 1
        assert state["history"][-1]["showdown"] is False
        # The early-ended hand records no hole cards.
        assert all(p["hole"] is None for p in state["history"][-1]["players"])


def test_board_can_reorder_seats():
    code = create_table()
    alice = join(code, "Alice")
    join(code, "Bob")

    with client.websocket_connect(f"/ws/{code}?role=board") as ws:
        ws.receive_json()
        ws.send_json(
            {"type": "action", "action": "move_player", "player_id": alice["player_id"], "direction": "down"}
        )
        state = ws.receive_json()["state"]
        assert [p["name"] for p in state["players"]] == ["Bob", "Alice"]


def test_player_websocket_receives_own_hole_cards_only():
    code = create_table()
    alice = join(code, "Alice")
    bob = join(code, "Bob")

    with client.websocket_connect(f"/ws/{code}?role=player&token={alice['token']}") as ws:
        initial = ws.receive_json()
        assert initial["type"] == "state"
        assert initial["state"]["you"]["name"] == "Alice"

        # Board deals while the player is connected.
        with client.websocket_connect(f"/ws/{code}?role=board") as board:
            board.receive_json()
            board.send_json({"type": "action", "action": "start_hand"})
            board.receive_json()

        state = ws.receive_json()
        # Two broadcasts are queued (board connect, then deal); find the dealt one.
        if state["state"]["street"] != "preflop":
            state = ws.receive_json()
        assert state["state"]["you"]["hole"]
        assert len(state["state"]["you"]["hole"]) == 2
        # Other players' cards are still hidden.
        for player in state["state"]["players"]:
            assert "hole" not in player
        assert bob["player_id"] in {p["id"] for p in state["state"]["players"]}


def test_player_websocket_rejects_bad_token():
    code = create_table()
    join(code, "Alice")
    with client.websocket_connect(f"/ws/{code}?role=player&token=bad") as ws:
        message = ws.receive_json()
        assert message["type"] == "error"
        assert message["reason"] == "bad_token"


def test_websocket_unknown_table_reports_reason():
    # Clients use this reason to stop reconnecting to a table that is gone
    # (e.g. after the server restarts and in-memory state is cleared).
    with client.websocket_connect("/ws/ZZZZ?role=board") as ws:
        message = ws.receive_json()
        assert message["type"] == "error"
        assert message["reason"] == "table_missing"


def test_player_can_fold_over_websocket():
    code = create_table()
    alice = join(code, "Alice")
    join(code, "Bob")

    with client.websocket_connect(f"/ws/{code}?role=board") as board:
        board.receive_json()
        board.send_json({"type": "action", "action": "start_hand"})
        board.receive_json()

        with client.websocket_connect(f"/ws/{code}?role=player&token={alice['token']}") as ws:
            ws.receive_json()  # player's initial state (broadcast on connect)
            board.receive_json()  # board observes the player connecting
            ws.send_json({"type": "action", "action": "fold"})
            # The fold broadcast reaches the board next.
            state = board.receive_json()["state"]
            assert any(p["folded"] for p in state["players"])
