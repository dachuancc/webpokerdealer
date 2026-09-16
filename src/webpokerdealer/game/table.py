"""Table state machine for Texas Hold'em dealing.

The table only *deals and reveals* cards; betting is done with real chips on the
physical table. Everything here is server-authoritative: the deck, the seats and
each player's hole cards live on the server, and every device receives a filtered
view (see :meth:`Table.board_state` and :meth:`Table.player_state`).
"""

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..config import settings
from .cards import Card, Deck


class GameError(Exception):
    """Raised for illegal actions (full table, dealing out of turn, ...)."""


class Street(str, Enum):
    WAITING = "waiting"
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"


# Order in which streets advance. WAITING is the initial state and is not part of
# the progression.
STREET_ORDER: tuple[Street, ...] = (
    Street.PREFLOP,
    Street.FLOP,
    Street.TURN,
    Street.RIVER,
    Street.SHOWDOWN,
)

# How many finished hands to keep for the board's history panel.
HISTORY_LIMIT = 100

STREET_LABELS: dict[Street, str] = {
    Street.WAITING: "等待开局",
    Street.PREFLOP: "翻牌前",
    Street.FLOP: "翻牌圈",
    Street.TURN: "转牌圈",
    Street.RIVER: "河牌圈",
    Street.SHOWDOWN: "摊牌",
}


@dataclass
class Player:
    id: str
    name: str
    seat: int
    token: str
    hole: list[Card] = field(default_factory=list)
    folded: bool = False
    connected: bool = False
    is_dealer: bool = False
    is_small_blind: bool = False
    is_big_blind: bool = False


class Table:
    """One poker table (one room code)."""

    def __init__(
        self,
        code: str,
        *,
        rng: random.Random | None = None,
        max_seats: int | None = None,
    ) -> None:
        self.code = code
        self.rng = rng
        self.max_seats = max_seats if max_seats is not None else settings.max_seats
        self.players: dict[str, Player] = {}
        self._seats: dict[int, str] = {}
        self.button_seat: int | None = None
        self.deck = Deck(rng)
        self.community: list[Card] = []
        self.burned: list[Card] = []
        self.street = Street.WAITING
        self.hand_number = 0
        self.history: list[dict[str, Any]] = []
        # True once the current hand has been written to ``history`` (or when no
        # hand is in progress), so a hand is never recorded twice.
        self._hand_recorded = True

    # ------------------------------------------------------------------ seats

    @property
    def seated(self) -> list[Player]:
        """Players ordered by seat, clockwise."""
        return sorted(self.players.values(), key=lambda p: p.seat)

    @property
    def seats_taken(self) -> dict[int, Player]:
        return {p.seat: p for p in self.players.values()}

    def add_player(self, name: str) -> Player:
        # Players may join at any time. Someone joining mid-hand simply sits out
        # the current hand (they are dealt in when the next one starts).
        name = name.strip()
        if not name:
            raise GameError("昵称不能为空")
        if len(name) > 16:
            raise GameError("昵称最多 16 个字")
        if len(self.players) >= self.max_seats:
            raise GameError("座位已满")
        seat = self._next_free_seat()
        player = Player(
            id=secrets.token_hex(6),
            name=name,
            seat=seat,
            token=secrets.token_urlsafe(24),
        )
        self.players[player.id] = player
        self._seats[seat] = player.id
        return player

    def remove_player(self, player_id: str) -> None:
        player = self.players.pop(player_id, None)
        if player is not None:
            self._seats.pop(player.seat, None)

    def move_player(self, player_id: str, direction: str) -> None:
        """Swap a player with its neighbour to reflect the physical seating.

        Seat order is clockwise and drives button rotation, blinds and the deal
        order, so reordering seats is how the host matches the real table.
        """
        order = self.seated
        idx = next((i for i, p in enumerate(order) if p.id == player_id), None)
        if idx is None:
            raise GameError("玩家不存在")
        if direction == "up":
            swap = idx - 1
        elif direction == "down":
            swap = idx + 1
        else:
            raise GameError("未知的移动方向")
        if swap < 0 or swap >= len(order):
            return  # already at the end, nothing to do
        a, b = order[idx], order[swap]
        a.seat, b.seat = b.seat, a.seat
        self._seats = {p.seat: p.id for p in self.players.values()}

    def find_by_token(self, token: str) -> Player | None:
        if not token:
            return None
        for player in self.players.values():
            if secrets.compare_digest(player.token, token):
                return player
        return None

    def _next_free_seat(self) -> int:
        for seat in range(self.max_seats):
            if seat not in self._seats:
                return seat
        raise GameError("座位已满")

    # ------------------------------------------------------------- hand flow

    def start_hand(self) -> None:
        """Rotate the button, shuffle and deal two hole cards to each player.

        A hand may end early (everyone folds, or the host simply calls it), so
        starting a new hand is allowed from any street and implicitly settles
        the current one. Dealing and "next hand" are therefore independent.
        """
        active = self.seated
        if len(active) < 2:
            raise GameError("至少需要 2 名玩家")
        if self.street != Street.WAITING:
            self._finish_hand(showdown=self.street == Street.SHOWDOWN)

        self.hand_number += 1
        self.deck = Deck(self.rng)
        self.community = []
        self.burned = []
        self._hand_recorded = False
        for player in active:
            player.hole = []
            player.folded = False
            player.is_dealer = False
            player.is_small_blind = False
            player.is_big_blind = False

        self._rotate_button(active)
        self._assign_blinds(active)
        self._deal_hole_cards(active)
        self.street = Street.PREFLOP

    def next_street(self) -> None:
        """Burn and reveal the next community street (flop / turn / river).

        This never reaches showdown: revealing is one thing, settling the hand
        is another. Showdown is an explicit action (:meth:`showdown`).
        """
        if self.street == Street.WAITING:
            raise GameError("尚未开始")
        if self.street == Street.SHOWDOWN:
            raise GameError("本局已结束，请开新局")
        if self.street == Street.RIVER:
            raise GameError("已发完河牌，请摊牌或开新局")

        target = STREET_ORDER[STREET_ORDER.index(self.street) + 1]
        if target == Street.FLOP:
            self.burned.append(self.deck.burn())
            self.community.extend(self.deck.draw() for _ in range(3))
        else:  # turn / river
            self.burned.append(self.deck.burn())
            self.community.append(self.deck.draw())
        self.street = target

    def showdown(self) -> None:
        """Settle the hand and reveal the hole cards of everyone still in.

        Only called when a showdown is actually needed (e.g. the river is out
        and nobody folded). Everyone who folded is mucked.
        """
        if self.street == Street.WAITING:
            raise GameError("尚未开始")
        if self.street == Street.SHOWDOWN:
            raise GameError("本局已结束，请开新局")
        self.street = Street.SHOWDOWN
        self._finish_hand(showdown=True)

    def set_folded(self, player_id: str, folded: bool) -> None:
        player = self.players.get(player_id)
        if player is None:
            raise GameError("玩家不存在")
        if self.street in (Street.WAITING, Street.SHOWDOWN):
            raise GameError("当前不能弃牌")
        player.folded = folded

    def reset(self) -> None:
        """Clear all players and start over with a brand new table."""
        self.players.clear()
        self._seats.clear()
        self.button_seat = None
        self.deck = Deck(self.rng)
        self.community = []
        self.burned = []
        self.street = Street.WAITING
        self.hand_number = 0
        self.history = []
        self._hand_recorded = True

    def _finish_hand(self, *, showdown: bool) -> None:
        """Append the current hand to the public history log.

        Folded players' hole cards are never written down, and an early-settled
        hand (no showdown) records no hole cards at all. This keeps the D3
        invariant: history only ever contains cards that were publicly revealed.
        """
        if self._hand_recorded or self.street == Street.WAITING:
            return
        players = []
        for player in self.seated:
            reveal = showdown and not player.folded
            players.append(
                {
                    "id": player.id,
                    "name": player.name,
                    "seat": player.seat,
                    "folded": player.folded,
                    "is_dealer": player.is_dealer,
                    "is_small_blind": player.is_small_blind,
                    "is_big_blind": player.is_big_blind,
                    "hole": [c.to_dict() for c in player.hole] if reveal else None,
                }
            )
        self.history.append(
            {
                "hand_number": self.hand_number,
                "street": self.street.value,
                "street_label": STREET_LABELS[self.street],
                "showdown": showdown,
                "community": [c.to_dict() for c in self.community],
                "players": players,
            }
        )
        self._hand_recorded = True
        if len(self.history) > HISTORY_LIMIT:
            del self.history[:-HISTORY_LIMIT]

    # ----------------------------------------------------------- dealing math

    def _rotate_button(self, active: list[Player]) -> None:
        seats = [p.seat for p in active]
        if self.button_seat is None or self.button_seat not in seats:
            self.button_seat = seats[0]
        else:
            idx = seats.index(self.button_seat)
            self.button_seat = seats[(idx + 1) % len(seats)]

    def _assign_blinds(self, active: list[Player]) -> None:
        seats = [p.seat for p in active]
        n = len(active)
        dealer_idx = seats.index(self.button_seat)  # type: ignore[arg-type]
        if n == 2:
            # Heads-up: the button is also the small blind.
            sb_idx, bb_idx = dealer_idx, (dealer_idx + 1) % n
        else:
            sb_idx, bb_idx = (dealer_idx + 1) % n, (dealer_idx + 2) % n
        for i, player in enumerate(active):
            player.is_dealer = i == dealer_idx
            player.is_small_blind = i == sb_idx
            player.is_big_blind = i == bb_idx

    def _deal_hole_cards(self, active: list[Player]) -> None:
        n = len(active)
        dealer_idx = next(i for i, p in enumerate(active) if p.is_dealer)
        order = [active[(dealer_idx + 1 + k) % n] for k in range(n)]
        for _ in range(2):  # one card at a time, twice around
            for player in order:
                player.hole.append(self.deck.draw())

    # ------------------------------------------------------------ serializing

    def _player_public(self, player: Player, *, reveal: bool) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": player.id,
            "name": player.name,
            "seat": player.seat,
            "folded": player.folded,
            "connected": player.connected,
            "is_dealer": player.is_dealer,
            "is_small_blind": player.is_small_blind,
            "is_big_blind": player.is_big_blind,
            "card_count": len(player.hole),
        }
        if reveal:
            data["hole"] = [card.to_dict() for card in player.hole]
        return data

    def _common_state(self) -> dict[str, Any]:
        reveal = self.street == Street.SHOWDOWN
        players = []
        for player in self.seated:
            # At showdown we reveal everyone who has not folded; folded hands are mucked.
            players.append(self._player_public(player, reveal=reveal and not player.folded))
        return {
            "code": self.code,
            "street": self.street.value,
            "street_label": STREET_LABELS[self.street],
            "hand_number": self.hand_number,
            "community": [card.to_dict() for card in self.community],
            "burned_count": len(self.burned),
            "button_seat": self.button_seat,
            "seats": self.max_seats,
            "players": players,
            "history": list(self.history),
        }

    def board_state(self) -> dict[str, Any]:
        """The shared/board view: community cards and public player info."""
        return self._common_state()

    def player_state(self, player_id: str) -> dict[str, Any]:
        """The private view for one player: everything public plus own hole cards."""
        state = self._common_state()
        player = self.players.get(player_id)
        if player is not None:
            state["you"] = {
                "id": player.id,
                "name": player.name,
                "seat": player.seat,
                "folded": player.folded,
                "is_dealer": player.is_dealer,
                "is_small_blind": player.is_small_blind,
                "is_big_blind": player.is_big_blind,
                "hole": [card.to_dict() for card in player.hole],
            }
        return state
