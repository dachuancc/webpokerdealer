import random

import pytest

from webpokerdealer.game.table import GameError, Street, Table


def make_table(*names, seed=42):
    table = Table("TEST", rng=random.Random(seed))
    for name in names:
        table.add_player(name)
    return table


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
    table.next_street()  # showdown
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

    table.next_street()
    assert table.street == Street.SHOWDOWN
    # Burned once before each of flop, turn and river.
    assert len(table.burned) == 3

    with pytest.raises(GameError):
        table.next_street()


def test_next_street_before_start_is_rejected():
    table = make_table("Alice", "Bob")
    with pytest.raises(GameError):
        table.next_street()


def test_cannot_start_while_hand_in_progress():
    table = make_table("Alice", "Bob")
    table.start_hand()
    with pytest.raises(GameError):
        table.start_hand()


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
    for _ in range(4):
        table.next_street()  # flop, turn, river, showdown
    assert table.street == Street.SHOWDOWN
    by_id = {p["id"]: p for p in table.board_state()["players"]}
    assert "hole" in by_id[alice.id]
    assert "hole" not in by_id[bob.id]


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
