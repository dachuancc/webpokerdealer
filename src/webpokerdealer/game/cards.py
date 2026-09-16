"""Playing cards and a shuffleable deck.

Shuffling uses ``random.SystemRandom`` (backed by the OS CSPRNG) so the deal is
fair without any external dependency. Tests may inject a seeded ``random.Random``
for deterministic sequences.
"""

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass
from typing import Any

RANKS = "23456789TJQKA"
SUITS = "shdc"  # spades, hearts, diamonds, clubs

SUIT_SYMBOLS = {"s": "\u2660", "h": "\u2665", "d": "\u2666", "c": "\u2663"}
RED_SUITS = frozenset({"h", "d"})
RANK_LABELS = {"T": "10"}


@dataclass(frozen=True, slots=True)
class Card:
    """A single card, e.g. ``Card("A", "s")`` for the ace of spades."""

    rank: str
    suit: str

    @property
    def code(self) -> str:
        return f"{self.rank}{self.suit}"

    @property
    def symbol(self) -> str:
        return SUIT_SYMBOLS[self.suit]

    @property
    def label(self) -> str:
        return RANK_LABELS.get(self.rank, self.rank)

    @property
    def is_red(self) -> bool:
        return self.suit in RED_SUITS

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "rank": self.rank,
            "label": self.label,
            "suit": self.suit,
            "symbol": self.symbol,
            "red": self.is_red,
        }


def make_deck() -> list[Card]:
    """Return an ordered 52-card deck."""
    return [Card(rank, suit) for suit in SUITS for rank in RANKS]


class Deck:
    """A shuffled deck; draw from the top with :meth:`draw`."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng: random.Random = rng if rng is not None else secrets.SystemRandom()
        self._cards = make_deck()
        self._rng.shuffle(self._cards)
        self._index = 0

    def draw(self) -> Card:
        if self._index >= len(self._cards):
            raise RuntimeError("deck is exhausted")
        card = self._cards[self._index]
        self._index += 1
        return card

    def burn(self) -> Card:
        """Draw and discard the top card (real poker burns before the flop/turn/river)."""
        return self.draw()

    @property
    def remaining(self) -> int:
        return len(self._cards) - self._index
