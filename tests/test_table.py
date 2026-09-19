import random

import pytest

from webpokerdealer.game.cards import Card
from webpokerdealer.game.table import GameError, Street, Table


def make_table(*names, seed=42):
    table = Table("TEST", rng=random.Random(seed))
    for name in names:
        table.add_player(name)
    return table


def cards(text: str) -> list[Card]:
    return [Card(code[0], code[1]) for code in text.split()]


def test_add_player_assigns_seats_and_rejects_blanks():
    table = make_table("Alice", "Bob")
    assert [p.seat for p in table.seated] == [0, 1]
    with pytest.raises(GameError):
        table.add_player("   ")


def test_table_enforces_max_seats():
    table = Table("FULL", rng=random.Random(1), max_seats=2)
    table.add_player("A")
    table.add_player("B")
    with pytest.raises(GameError):
        table.add_player("C")


def test_default_table_caps_at_nine_players():
    # Each table seats at most 9 players by default.
    table = Table("NINE", rng=random.Random(0))
    assert table.max_seats == 9
    for i in range(9):
        table.add_player(f"P{i}")
    with pytest.raises(GameError):
        table.add_player("P10")


def test_start_hand_requires_two_players():
    table = make_table("Solo")
    with pytest.raises(GameError):
        table.start_hand()


def test_start_hand_deals_two_cards_each_and_sets_preflop():
    table = make_table("Alice", "Bob", "Cara")
    table.start_hand()
    assert table.street == Street.PREFLOP
    assert table.hand_number == 1
    for player in table.seated:
        assert len(player.hole) == 2
    # No duplicate cards were dealt.
    dealt = [card.code for p in table.seated for card in p.hole]
    assert len(dealt) == len(set(dealt)) == 6


def test_heads_up_button_is_small_blind():
    table = make_table("Alice", "Bob")
    table.start_hand()
    dealer = next(p for p in table.seated if p.is_dealer)
    assert dealer.is_small_blind
    assert not any(p.is_big_blind and p.is_dealer for p in table.seated)


def test_three_handed_blinds_follow_button():
    table = make_table("Alice", "Bob", "Cara")
    table.start_hand()
    assert sum(p.is_dealer for p in table.seated) == 1
    assert sum(p.is_small_blind for p in table.seated) == 1
    assert sum(p.is_big_blind for p in table.seated) == 1
    dealer = next(p for p in table.seated if p.is_dealer)
    sb = next(p for p in table.seated if p.is_small_blind)
    bb = next(p for p in table.seated if p.is_big_blind)
    seats = [p.seat for p in table.seated]
    n = len(seats)
    d = seats.index(dealer.seat)
    assert sb.seat == seats[(d + 1) % n]
    assert bb.seat == seats[(d + 2) % n]


def test_button_rotates_between_hands():
    table = make_table("Alice", "Bob", "Cara")
    table.start_hand()
    first = table.button_seat
    table.next_street()  # flop
    table.next_street()  # turn
    table.next_street()  # river
    table.showdown()
    assert table.street == Street.SHOWDOWN
    table.start_hand()
    assert table.button_seat != first
    assert table.hand_number == 2


def test_street_progression_reveals_correct_number_of_cards():
    table = make_table("Alice", "Bob", "Cara")
    table.start_hand()
    assert table.community == []

    table.next_street()
    assert table.street == Street.FLOP
    assert len(table.community) == 3

    table.next_street()
    assert table.street == Street.TURN
    assert len(table.community) == 4

    table.next_street()
    assert table.street == Street.RIVER
    assert len(table.community) == 5
    # Burned once before each of flop, turn and river.
    assert len(table.burned) == 3

    # The deal never advances to showdown on its own.
    with pytest.raises(GameError):
        table.next_street()
    assert table.street == Street.RIVER

    table.showdown()
    assert table.street == Street.SHOWDOWN
    with pytest.raises(GameError):
        table.next_street()
    with pytest.raises(GameError):
        table.showdown()


def test_showdown_before_the_river_is_rejected():
    table = make_table("Alice", "Bob")
    table.start_hand()
    with pytest.raises(GameError):
        table.showdown()  # preflop
    table.next_street()  # flop
    with pytest.raises(GameError):
        table.showdown()
    table.next_street()  # turn
    with pytest.raises(GameError):
        table.showdown()
    table.next_street()  # river
    table.showdown()
    assert table.street == Street.SHOWDOWN


def test_next_street_before_start_is_rejected():
    table = make_table("Alice", "Bob")
    with pytest.raises(GameError):
        table.next_street()


def test_showdown_before_start_is_rejected():
    table = make_table("Alice", "Bob")
    with pytest.raises(GameError):
        table.showdown()


def test_start_hand_ends_previous_hand_early_and_records_it():
    # A hand can be won by betting without a showdown, so the host may start the
    # next hand at any time. Dealing and "next hand" are independent.
    table = make_table("Alice", "Bob", "Cara")
    table.start_hand()
    table.next_street()  # flop
    table.start_hand()
    assert table.street == Street.PREFLOP
    assert table.hand_number == 2
    assert len(table.history) == 1
    record = table.history[0]
    assert record["hand_number"] == 1
    assert record["showdown"] is False
    # No showdown -> no hole cards may leak into the history log.
    assert all(p["hole"] is None for p in record["players"])


def test_showdown_is_recorded_once_even_after_starting_next_hand():
    table = make_table("Alice", "Bob")
    table.start_hand()
    table.next_street()
    table.next_street()
    table.next_street()
    table.showdown()
    table.start_hand()
    assert len(table.history) == 1
    assert table.history[0]["showdown"] is True
    assert table.history[0]["hand_number"] == 1


def test_board_state_hides_hole_cards_before_showdown():
    table = make_table("Alice", "Bob")
    table.start_hand()
    state = table.board_state()
    for player in state["players"]:
        assert "hole" not in player
        assert player["card_count"] == 2


def test_player_state_includes_only_own_hole_cards():
    table = make_table("Alice", "Bob")
    table.start_hand()
    alice = table.seated[0]
    state = table.player_state(alice.id)
    assert len(state["you"]["hole"]) == 2
    for player in state["players"]:
        assert "hole" not in player


def test_showdown_reveals_only_players_who_did_not_fold():
    table = make_table("Alice", "Bob", "Cara")
    table.start_hand()
    alice, bob, _cara = table.seated
    table.set_folded(bob.id, True)
    for _ in range(3):
        table.next_street()  # flop, turn, river
    table.showdown()
    assert table.street == Street.SHOWDOWN
    by_id = {p["id"]: p for p in table.board_state()["players"]}
    assert "hole" in by_id[alice.id]
    assert "hole" not in by_id[bob.id]
    # History reveals exactly the same hands as the board did.
    record = table.history[0]
    hist = {p["id"]: p for p in record["players"]}
    assert hist[alice.id]["hole"] is not None
    assert hist[bob.id]["hole"] is None


def test_set_dealer_mid_hand_reassigns_blinds():
    table = make_table("Alice", "Bob", "Cara")
    table.start_hand()
    target = table.seated[2]
    table.set_dealer(target.id)
    assert target.is_dealer
    assert sum(p.is_dealer for p in table.seated) == 1
    assert sum(p.is_small_blind for p in table.seated) == 1
    assert sum(p.is_big_blind for p in table.seated) == 1
    # The next hand rotates on from the corrected button (starting a new hand
    # before the river settles the current one).
    table.start_hand()
    seats = [p.seat for p in table.seated]
    assert table.button_seat == seats[(seats.index(target.seat) + 1) % len(seats)]


def test_set_dealer_before_first_hand_skips_rotation():
    table = make_table("Alice", "Bob", "Cara")
    target = table.seated[2]
    table.set_dealer(target.id)
    table.start_hand()
    assert target.is_dealer


def test_set_dealer_rejects_unknown_player():
    table = make_table("Alice", "Bob")
    with pytest.raises(GameError):
        table.set_dealer("nope")


def test_showdown_evaluates_hands_and_marks_the_winner():
    table = make_table("Alice", "Bob")
    table.start_hand()
    alice, bob = table.seated
    alice.hole = cards("As Ad")
    bob.hole = cards("Kh Kd")
    table.community = cards("2c 7d 9h Js 3c")
    table.street = Street.RIVER
    table.showdown()
    state = table.board_state()
    by_id = {p["id"]: p for p in state["players"]}
    assert by_id[alice.id]["hand_name"] == "一对"
    assert by_id[alice.id]["is_winner"] is True
    assert by_id[bob.id]["is_winner"] is False
    assert state["winners"] == [{"id": alice.id, "name": "Alice"}]
    # The history log records the same result.
    record = table.history[0]
    hist = {p["id"]: p for p in record["players"]}
    assert hist[alice.id]["hand_name"] == "一对"
    assert hist[alice.id]["is_winner"] is True


def test_showdown_tie_marks_both_players_as_winners():
    table = make_table("Alice", "Bob")
    table.start_hand()
    alice, bob = table.seated
    alice.hole = cards("As Kd")
    bob.hole = cards("Ah Kc")
    table.community = cards("2c 7d 9h Js 3c")
    table.street = Street.RIVER
    table.showdown()
    winners = table.board_state()["winners"]
    assert {w["name"] for w in winners} == {"Alice", "Bob"}


def test_no_showdown_result_before_showdown():
    table = make_table("Alice", "Bob")
    table.start_hand()
    state = table.board_state()
    assert state["winners"] == []
    assert all("hand_name" not in p for p in state["players"])


def test_player_state_includes_own_hand_name_at_showdown():
    table = make_table("Alice", "Bob")
    table.start_hand()
    alice, bob = table.seated
    alice.hole = cards("As Ad")
    bob.hole = cards("Kh Kd")
    table.community = cards("2c 7d 9h Js 3c")
    table.street = Street.RIVER
    table.showdown()
    state = table.player_state(alice.id)
    assert state["you"]["hand_name"] == "一对"
    assert state["you"]["is_winner"] is True


def test_folded_players_are_not_evaluated():
    table = make_table("Alice", "Bob")
    table.start_hand()
    alice, bob = table.seated
    table.set_folded(bob.id, True)
    alice.hole = cards("As Ad")
    bob.hole = cards("Kh Kd")
    table.community = cards("2c 7d 9h Js 3c")
    table.street = Street.RIVER
    table.showdown()
    state = table.board_state()
    assert state["winners"] == [{"id": alice.id, "name": "Alice"}]
    by_id = {p["id"]: p for p in state["players"]}
    assert "hand_name" not in by_id[bob.id]


def test_fold_toggle():
    table = make_table("Alice", "Bob")
    table.start_hand()
    alice = table.seated[0]
    table.set_folded(alice.id, True)
    assert table.players[alice.id].folded is True
    table.set_folded(alice.id, False)
    assert table.players[alice.id].folded is False


def test_find_by_token():
    table = make_table("Alice")
    alice = table.seated[0]
    assert table.find_by_token(alice.token).id == alice.id
    assert table.find_by_token("nope") is None
    assert table.find_by_token("") is None


def test_host_pin_and_token_verification():
    table = make_table("Alice")
    assert len(table.pin) == 4 and table.pin.isdigit()
    assert table.verify_pin(table.pin)
    wrong = "0000" if table.pin != "0000" else "1111"
    assert not table.verify_pin(wrong)
    assert not table.verify_pin("")
    assert table.verify_host_token(table.host_token)
    assert not table.verify_host_token("nope")
    assert not table.verify_host_token("")


def test_reset_clears_everything():
    table = make_table("Alice", "Bob")
    table.start_hand()
    table.reset()
    assert table.players == {}
    assert table.street == Street.WAITING
    assert table.community == []
    assert table.hand_number == 0
    assert table.button_seat is None


def test_remove_player_frees_seat():
    table = make_table("Alice", "Bob")
    alice = table.seated[0]
    table.remove_player(alice.id)
    assert alice.id not in table.players
    cara = table.add_player("Cara")
    assert cara.seat == alice.seat


def test_add_player_is_allowed_mid_hand_but_not_dealt_in():
    table = make_table("Alice", "Bob")
    table.start_hand()
    cara = table.add_player("Cara")
    assert cara.hole == []
    table.start_hand()
    assert len(cara.hole) == 2


def test_mid_hand_joiner_is_not_scored_or_revealed_at_showdown():
    """中途入座者本局旁观：不得只凭公共牌参与比牌，也不该出现在亮牌里。

    回归：`_evaluate_showdown` 一度对每个未弃牌玩家求值，而中途入座者
    `hole == []` 时 `best_hand([] + community)` 仍能算出牌型——于是本局
    根本没被发牌的人会被判成赢家（`docs/DECISIONS.md` D13 的漏网分支）。
    """
    # seed=83：这一副公共牌本身就够强，修复前 Cara 会凭公共牌「赢」。
    table = make_table("Alice", "Bob", seed=83)
    table.start_hand()
    assert all(len(p.hole) == 2 for p in table.seated)
    cara = table.add_player("Cara")
    assert cara.hole == []
    while table.street != Street.RIVER:
        table.next_street()
    table.showdown()

    board = table.board_state()
    assert cara.id not in {w["id"] for w in board["winners"]}
    cara_pub = next(p for p in board["players"] if p["id"] == cara.id)
    assert "hole" not in cara_pub  # 没牌可亮
    assert "hand_name" not in cara_pub  # 不参与比牌

    # 历史是公开数据，也不该给旁观者写下空底牌
    cara_hist = next(p for p in table.history[-1]["players"] if p["id"] == cara.id)
    assert cara_hist["hole"] is None


def test_move_player_reorders_seats():
    table = make_table("Alice", "Bob", "Cara")
    order = [p.name for p in table.seated]
    table.move_player(table.seated[0].id, "down")
    assert [p.name for p in table.seated] == [order[1], order[0], order[2]]
    # The seat mapping stays consistent after the swap.
    assert all(table._seats[p.seat] == p.id for p in table.players.values())


def test_move_player_at_seat_edge_is_a_noop():
    table = make_table("Alice", "Bob")
    first, _last = table.seated
    table.move_player(first.id, "up")
    assert [p.name for p in table.seated] == ["Alice", "Bob"]
    with pytest.raises(GameError):
        table.move_player(first.id, "sideways")
