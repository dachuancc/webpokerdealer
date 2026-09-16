from webpokerdealer.game.cards import Card
from webpokerdealer.game.evaluator import best_hand, hand_name


def cards(text: str) -> list[Card]:
    """Parse ``"As Kd Qh"`` into Card objects."""
    return [Card(code[0], code[1]) for code in text.split()]


def test_category_names_for_five_card_hands():
    assert hand_name(best_hand(cards("As Kd Qh Jc 9c"))) == "高牌"
    assert hand_name(best_hand(cards("As Ad Kh Qc Jc"))) == "一对"
    assert hand_name(best_hand(cards("As Ad Kh Kc Jc"))) == "两对"
    assert hand_name(best_hand(cards("As Ad Ah Qc Jc"))) == "三条"
    assert hand_name(best_hand(cards("9s 8d 7h 6c 5c"))) == "顺子"
    assert hand_name(best_hand(cards("As Ks Qs Js 9s"))) == "同花"
    assert hand_name(best_hand(cards("As Ad Ah Kc Kd"))) == "葫芦"
    assert hand_name(best_hand(cards("As Ad Ah Ac Kd"))) == "四条"
    assert hand_name(best_hand(cards("9s 8s 7s 6s 5s"))) == "同花顺"
    assert hand_name(best_hand(cards("As Ks Qs Js Ts"))) == "皇家同花顺"


def test_categories_are_ordered_low_to_high():
    ordered = [
        "As Kd Qh Jc 9c",  # high card
        "As Ad Kh Qc Jc",  # one pair
        "As Ad Kh Kc Jc",  # two pair
        "As Ad Ah Qc Jc",  # three of a kind
        "9s 8d 7h 6c 5c",  # straight
        "As Ks Qs Js 9s",  # flush
        "As Ad Ah Kc Kd",  # full house
        "As Ad Ah Ac Kd",  # four of a kind
        "9s 8s 7s 6s 5s",  # straight flush
        "As Ks Qs Js Ts",  # royal flush
    ]
    scores = [best_hand(cards(h)) for h in ordered]
    assert scores == sorted(scores)
    assert len(set(scores)) == len(scores)


def test_wheel_is_the_lowest_straight():
    wheel = best_hand(cards("As 2d 3h 4c 5c"))
    six_high = best_hand(cards("6s 5d 4h 3c 2c"))
    assert hand_name(wheel) == "顺子"
    assert wheel < six_high


def test_kickers_break_pair_ties():
    stronger = best_hand(cards("As Ad Kh Qc Jc"))
    weaker = best_hand(cards("As Ad Kh Qc Tc"))
    assert stronger > weaker


def test_identical_hands_are_equal():
    a = best_hand(cards("As Ad Kh Qc Jc"))
    b = best_hand(cards("Ah Ac Ks Qd Jd"))
    assert a == b


def test_best_five_is_chosen_from_seven():
    # Board pairs the ace twice; the best five is aces full of kings.
    assert hand_name(best_hand(cards("As Ad Ah Kc Kd 2h 3d"))) == "葫芦"
    # Four aces beats the boat.
    assert hand_name(best_hand(cards("As Ad Ah Ac Kd 2h 3d"))) == "四条"
    # Only one spade in hand, but five spades on the board makes a flush.
    assert hand_name(best_hand(cards("As 2s 5s 9s Ks 3h 4d"))) == "同花"


def test_best_hand_needs_at_least_five_cards():
    assert best_hand(cards("As Kd")) is None
    assert best_hand(cards("As Kd Qh Jc")) is None
