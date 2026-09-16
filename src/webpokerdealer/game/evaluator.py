"""Poker hand evaluation (best 5 out of 7) for showdown results.

Pure and server-side. It only ever runs on hands that are already being
revealed at showdown, so it cannot leak hole cards (see D3).

A hand score is a tuple of ints: ``(category, *tiebreakers)``. Comparing two
scores as tuples gives the correct ordering, highest wins.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Sequence

from .cards import Card

RANK_VALUES: dict[str, int] = {
    rank: value for value, rank in enumerate("23456789TJQKA", start=2)
}

# Category ids, higher beats lower.
HIGH_CARD = 0
ONE_PAIR = 1
TWO_PAIR = 2
THREE_OF_A_KIND = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
FOUR_OF_A_KIND = 7
STRAIGHT_FLUSH = 8

CATEGORY_NAMES: tuple[str, ...] = (
    "高牌",
    "一对",
    "两对",
    "三条",
    "顺子",
    "同花",
    "葫芦",
    "四条",
    "同花顺",
)


def _straight_high(values: set[int]) -> int:
    """High card of a 5-card straight, or 0. Handles the A-2-3-4-5 wheel."""
    if len(values) != 5:
        return 0
    if max(values) - min(values) == 4:
        return max(values)
    if values == {14, 2, 3, 4, 5}:
        return 5  # the wheel: ace plays low, five is high
    return 0


def _score_five(cards: Sequence[Card]) -> tuple[int, ...]:
    values = sorted((RANK_VALUES[c.rank] for c in cards), reverse=True)
    counts = Counter(values)
    flush = len({c.suit for c in cards}) == 1
    straight = _straight_high(set(values))
    groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)

    if flush and straight:
        return (STRAIGHT_FLUSH, straight)
    if groups[0][1] == 4:
        quad = groups[0][0]
        return (FOUR_OF_A_KIND, quad, max(v for v in values if v != quad))
    if groups[0][1] == 3 and len(groups) > 1 and groups[1][1] >= 2:
        return (FULL_HOUSE, groups[0][0], groups[1][0])
    if flush:
        return (FLUSH, *values)
    if straight:
        return (STRAIGHT, straight)
    if groups[0][1] == 3:
        kickers = sorted((v for v in values if v != groups[0][0]), reverse=True)
        return (THREE_OF_A_KIND, groups[0][0], *kickers)
    if groups[0][1] == 2 and len(groups) > 1 and groups[1][1] == 2:
        high_pair, low_pair = sorted((groups[0][0], groups[1][0]), reverse=True)
        kicker = max(v for v in values if v not in (high_pair, low_pair))
        return (TWO_PAIR, high_pair, low_pair, kicker)
    if groups[0][1] == 2:
        pair = groups[0][0]
        kickers = sorted((v for v in values if v != pair), reverse=True)
        return (ONE_PAIR, pair, *kickers)
    return (HIGH_CARD, *values)


def best_hand(cards: Sequence[Card]) -> tuple[int, ...] | None:
    """Best 5-card score from ``cards`` (5-7 of them), or None if too few."""
    cards = list(cards)
    if len(cards) < 5:
        return None
    return max(_score_five(combo) for combo in combinations(cards, 5))


def hand_name(score: tuple[int, ...]) -> str:
    """Chinese name for a score, e.g. ``"两对"`` or ``"皇家同花顺"``."""
    if score[0] == STRAIGHT_FLUSH and score[1] == 14:
        return "皇家同花顺"
    return CATEGORY_NAMES[score[0]]
