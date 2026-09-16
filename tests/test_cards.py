import random

from webpokerdealer.game.cards import Card, Deck, make_deck


def test_deck_has_52_unique_cards():
    deck = make_deck()
    assert len(deck) == 52
    assert len({card.code for card in deck}) == 52


def test_card_helpers():
    ace = Card("A", "h")
    assert ace.code == "Ah"
    assert ace.symbol == "\u2665"
    assert ace.label == "A"
    assert ace.is_red is True
    ten = Card("T", "s")
    assert ten.label == "10"
    assert ten.is_red is False
    data = ten.to_dict()
    assert data["code"] == "Ts"
    assert data["symbol"] == "\u2660"
    assert data["red"] is False


def test_deck_is_deterministic_with_seeded_rng():
    first = [Deck(random.Random(7)).draw().code for _ in range(5)]
    second = [Deck(random.Random(7)).draw().code for _ in range(5)]
    assert first == second


def test_draw_reduces_remaining_and_eventually_raises():
    deck = Deck(random.Random(1))
    assert deck.remaining == 52
    for _ in range(52):
        deck.draw()
    assert deck.remaining == 0
    assert deck.remaining == 0
    try:
        deck.draw()
    except RuntimeError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("expected RuntimeError on empty deck")
