from fastapi.testclient import TestClient

from webpokerdealer.main import app

client = TestClient(app)


# Host tokens are only returned when a table is created, so stash them here to
# authenticate board WebSocket connections in tests.
_HOST_TOKENS: dict[str, str] = {}


def create_table() -> str:
    res = client.post("/api/tables")
    assert res.status_code == 200
    data = res.json()
    _HOST_TOKENS[data["code"]] = data["host_token"]
    return data["code"]


def board_url(code: str) -> str:
    return f"/ws/{code}?role=board&token={_HOST_TOKENS[code]}"


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


def test_create_table_returns_pin_and_host_token():
    data = client.post("/api/tables").json()
    assert len(data["pin"]) == 4 and data["pin"].isdigit()
    assert data["host_token"]


def test_host_auth_exchanges_correct_pin_for_token():
    data = client.post("/api/tables").json()
    res = client.post(f"/api/tables/{data['code']}/host", json={"pin": data["pin"]})
    assert res.status_code == 200
    assert res.json()["host_token"] == data["host_token"]


def test_host_auth_rejects_wrong_pin():
    data = client.post("/api/tables").json()
    wrong = ("0" if data["pin"][0] != "0" else "1") + data["pin"][1:]
    res = client.post(f"/api/tables/{data['code']}/host", json={"pin": wrong})
    assert res.status_code == 403


def test_board_websocket_requires_host_token():
    code = create_table()
    join(code, "Alice")
    with client.websocket_connect(f"/ws/{code}?role=board") as ws:
        message = ws.receive_json()
        assert message["type"] == "error"
        assert message["reason"] == "bad_host"


def test_board_websocket_rejects_wrong_host_token():
    code = create_table()
    with client.websocket_connect(f"/ws/{code}?role=board&token=nope") as ws:
        assert ws.receive_json()["reason"] == "bad_host"


def test_second_board_connection_notifies_the_first():
    code = create_table()
    join(code, "Alice")
    join(code, "Bob")
    with client.websocket_connect(board_url(code)) as first:
        first.receive_json()  # initial state
        with client.websocket_connect(board_url(code)) as second:
            second.receive_json()  # the second board's initial state
            notice = first.receive_json()
            assert notice["type"] == "notice"
            assert notice["kind"] == "board_joined"
            # The first board still receives the normal state broadcast too.
            assert first.receive_json()["type"] == "state"


def test_pin_is_only_sent_to_the_board():
    code = create_table()
    alice = join(code, "Alice")
    join(code, "Bob")
    with client.websocket_connect(board_url(code)) as board:
        board_state = board.receive_json()["state"]
        assert len(board_state["pin"]) == 4
    with client.websocket_connect(f"/ws/{code}?role=player&token={alice['token']}") as ws:
        player_state = ws.receive_json()["state"]
        assert "pin" not in player_state


def test_join_rejects_blank_name():
    code = create_table()
    res = client.post(f"/api/tables/{code}/join", json={"name": ""})
    assert res.status_code == 422


def test_join_unknown_table_is_404():
    res = client.post("/api/tables/ZZZZ/join", json={"name": "Alice"})
    assert res.status_code == 404


def test_table_rejects_join_when_nine_seats_are_taken():
    code = create_table()
    for i in range(9):
        join(code, f"P{i}")
    res = client.post(f"/api/tables/{code}/join", json={"name": "P10"})
    assert res.status_code == 400
    assert "座位已满" in res.json()["detail"]


def test_player_page_loads():
    code = create_table()
    res = client.get(f"/play/{code}")
    assert res.status_code == 200
    assert code in res.text


def test_board_websocket_start_hand_flow():
    code = create_table()
    join(code, "Alice")
    join(code, "Bob")

    with client.websocket_connect(board_url(code)) as ws:
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

    with client.websocket_connect(board_url(code)) as ws:
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

    with client.websocket_connect(board_url(code)) as ws:
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

    with client.websocket_connect(board_url(code)) as ws:
        ws.receive_json()
        ws.send_json(
            {"type": "action", "action": "move_player", "player_id": alice["player_id"], "direction": "down"}
        )
        state = ws.receive_json()["state"]
        assert [p["name"] for p in state["players"]] == ["Bob", "Alice"]


def test_board_can_set_the_dealer():
    code = create_table()
    alice = join(code, "Alice")
    bob = join(code, "Bob")

    with client.websocket_connect(board_url(code)) as ws:
        ws.receive_json()
        ws.send_json({"type": "action", "action": "start_hand"})
        ws.receive_json()
        ws.send_json(
            {"type": "action", "action": "set_dealer", "player_id": bob["player_id"]}
        )
        state = ws.receive_json()["state"]
        by_id = {p["id"]: p for p in state["players"]}
        assert by_id[bob["player_id"]]["is_dealer"]
        assert not by_id[alice["player_id"]]["is_dealer"]


def test_player_websocket_receives_own_hole_cards_only():
    code = create_table()
    alice = join(code, "Alice")
    bob = join(code, "Bob")

    with client.websocket_connect(f"/ws/{code}?role=player&token={alice['token']}") as ws:
        initial = ws.receive_json()
        assert initial["type"] == "state"
        assert initial["state"]["you"]["name"] == "Alice"

        # Board deals while the player is connected.
        with client.websocket_connect(board_url(code)) as board:
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

    with client.websocket_connect(board_url(code)) as board:
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
