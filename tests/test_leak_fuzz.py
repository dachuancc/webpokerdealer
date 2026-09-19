"""广撒网式底牌泄漏测试（守护 D3：牌只下发给该看到它的人）。

`test_table.py::test_board_state_hides_hole_cards_before_showdown` 这类用例验证的是
**我们想得到的场景**；本文件随机跑大量牌局，在每一步对真正会下发出去的 payload
（`board_state()` / `player_state()`）做两项检查：

1. **路径白名单**：递归遍历 payload，凡是「牌」这个 dict 形状（`{"code","rank","suit"}`）
   出现的位置必须落在已知的合法路径里。这样**任何新增的、未知的**带牌字段都会被抓出来
   ——包括"顺手加个调试字段"这种无声破口。
2. **规则与取值**：逐条核对核心不变量：摊牌前谁都不许带底牌；摊牌时只揭示**本局拿到牌
   且未弃牌**的人；历史里提前结束的局不写底牌、弃牌者的底牌不进历史（D11）；本人视图里
   必须正好是自己的两张牌；`you` 只出现在本人视图里。

为什么不按「牌面集合」比对：**每一局都会重新洗牌**，所以本局某张底牌与上一局历史里
已公开的牌可能是同一张（`Td` 重复出现）。按路径 + 逐项核对才能既严格又无误报。

另外两条不依赖牌面的断言：秘密字段（PIN / host_token / 玩家 token）不得出现在视图里；
公牌桌视图**必须**带 PIN（D12）。注入固定种子的 `random.Random`，失败可用同一 seed 复现。
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from webpokerdealer.game.cards import Card
from webpokerdealer.game.table import STREET_ORDER, Street, Table

CardKey = tuple[str, str]

# 每个 seed 走这么多局。默认在 1 秒量级；想更狠地撒网就加大。
HANDS_PER_SEED = 60
SEEDS = (1, 20260917)

CardPath = tuple[str | int, ...]

# 牌允许出现的位置（路径中的数字下标会被归一化掉，见 _norm_path）。
ALLOWED_CARD_PATHS: frozenset[CardPath] = frozenset(
    {
        ("community",),  # 公共牌：本来就是公开的
        ("history", "community"),  # 历史里的公共牌
        ("history", "players", "hole"),  # 历史里已亮出的底牌
        ("players", "hole"),  # 摊牌时的亮牌
        ("you", "hole"),  # 本人视角的自己的底牌
    }
)


# --------------------------------------------------------------------- 工具


def _card_key(card: Card | dict[str, Any]) -> CardKey:
    if isinstance(card, Card):
        return (card.rank, card.suit)
    return (card["rank"], card["suit"])


def _is_card(node: Any) -> bool:
    return isinstance(node, dict) and {"code", "rank", "suit"} <= node.keys()


def _norm_path(path: CardPath) -> CardPath:
    """去掉路径里的数字下标：`("players", 2, "hole", 0)` -> `("players", "hole")`。"""
    return tuple(part for part in path if not isinstance(part, int))


def _cards_by_path(node: Any) -> dict[CardPath, set[CardKey]]:
    """递归收集 payload 里的牌，按归一化路径归类。"""
    found: dict[CardPath, set[CardKey]] = {}
    stack: list[tuple[Any, CardPath]] = [(node, ())]
    while stack:
        item, path = stack.pop()
        if _is_card(item):
            found.setdefault(_norm_path(path), set()).add(_card_key(item))
            continue  # 牌不会再嵌套别的牌
        if isinstance(item, dict):
            stack.extend((value, (*path, key)) for key, value in item.items())
        elif isinstance(item, list):
            stack.extend((value, (*path, index)) for index, value in enumerate(item))
    return found


def _strings_in(node: Any) -> set[str]:
    """递归收集 payload 里所有字符串标量（用来查秘密字段）。"""
    found: set[str] = set()
    stack: list[Any] = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            found.add(item)
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


def _fmt(cards: set[CardKey]) -> str:
    return " ".join(f"{rank}{suit}" for rank, suit in sorted(cards))


def _hole_of(player: Any) -> set[CardKey]:
    return {_card_key(card) for card in player.hole}


# ------------------------------------------------------------------- 体检


def check_table_views(table: Table, where: str) -> None:
    """把当前牌桌的所有视图过一遍，断言没有泄漏。"""
    tokens = {p.token for p in table.players.values()}
    expected_views: list[tuple[dict[str, Any], str | None]] = [
        (table.board_state(), None),
        *((table.player_state(pid), pid) for pid in table.players),
    ]

    for payload, viewer in expected_views:
        who = "公牌桌" if viewer is None else f"玩家 {viewer}"
        _check_card_paths(payload, where, who)
        _check_current_hand_reveal(table, payload, where, who)
        _check_history(table, payload, where, who)
        _check_you(table, payload, viewer, where, who)

        strings = _strings_in(payload)
        assert not (strings & tokens), f"{where}: {who} 视图里带出了玩家 token"
        assert table.host_token not in strings, f"{where}: {who} 视图里带出了 host_token"
        if viewer is None:
            assert table.pin in strings, f"{where}: 公牌桌视图应带 PIN 供换设备用（D12）"
        else:
            assert table.pin not in strings, f"{where}: {who} 视图里带出了主持人 PIN（D12）"

    # 身份失效（token 过期 / 玩家已被移出）时不能退化成「看到全部」。
    stale = table.player_state("no-such-player")
    _check_card_paths(stale, where, "无效身份")
    _check_current_hand_reveal(table, stale, where, "无效身份")
    assert "you" not in stale, f"{where}: 无效身份的视图里出现了 you"

    # 摊牌：没被发到牌的人不得比牌或判赢（中途入座者本局旁观）。
    if table.street == Street.SHOWDOWN:
        winners = {w["id"] for w in table.board_state()["winners"]}
        for pid, player in table.players.items():
            if not player.in_hand:
                assert pid not in winners, f"{where}: 本局未发到牌的玩家被算进比牌"


def _check_card_paths(payload: dict[str, Any], where: str, who: str) -> None:
    """所有的牌必须出现在白名单路径上（抓未知字段）。"""
    for path, cards in _cards_by_path(payload).items():
        assert path in ALLOWED_CARD_PATHS, (
            f"{where}: {who} 视图在意外位置 {path} 带了牌 {_fmt(cards)}"
            "（可能是新增的通路，请确认是否泄漏底牌）"
        )


def _check_current_hand_reveal(
    table: Table, payload: dict[str, Any], where: str, who: str
) -> None:
    """本局：谁该带底牌、带的是不是他自己那两张。"""
    revealed_at_showdown = table.street == Street.SHOWDOWN
    for entry in payload["players"]:
        player = table.players[entry["id"]]
        expected = revealed_at_showdown and player.in_hand and not player.folded
        assert ("hole" in entry) == expected, (
            f"{where}: {who} 视图里 {player.name} 的亮牌状态不对"
            f"（street={table.street.value}, in_hand={player.in_hand}, folded={player.folded}）"
        )
        if expected:
            assert set(map(_card_key, entry["hole"])) == _hole_of(player), (
                f"{where}: {who} 视图里 {player.name} 的亮牌不是他自己的牌"
            )
            assert len(entry["hole"]) == 2


def _check_history(table: Table, payload: dict[str, Any], where: str, who: str) -> None:
    """历史是公开数据：提前结束的局不写底牌，弃牌者的底牌不入历史（D11）。"""
    for hand in payload["history"]:
        for entry in hand["players"]:
            if not hand["showdown"]:
                assert entry["hole"] is None, (
                    f"{where}: {who} 视图的历史里，未摊牌的一局（第 {hand['hand_number']} 局）"
                    f"写下了底牌"
                )
                continue
            if entry["folded"]:
                assert entry["hole"] is None, (
                    f"{where}: {who} 视图的历史里，弃牌者 {entry['name']} 的底牌被记下了"
                )
            if entry["hole"] is not None:
                assert len(entry["hole"]) == 2


def _check_you(
    table: Table, payload: dict[str, Any], viewer: str | None, where: str, who: str
) -> None:
    """`you` 只出现在本人视图里，且正好是自己的两张牌。"""
    if viewer is None:
        assert "you" not in payload, f"{where}: {who} 视图里不该有 you"
        return
    you = payload["you"]
    player = table.players[viewer]
    assert you["id"] == viewer, f"{where}: {who} 视图里的 you 不是本人"
    assert set(map(_card_key, you["hole"])) == _hole_of(player), (
        f"{where}: {who} 视图里 you.hole 不是自己的牌"
    )
    # 本人视角永远带自己的底牌；中途入座者本局无牌，就是空的（自己的信息，不算泄漏）。
    assert len(you["hole"]) == (2 if player.in_hand else 0)


# ------------------------------------------------------------------- 随机局


def _exercise(rng: random.Random, table: Table, label: str) -> None:
    """随机走一局，每一步都做体检。"""
    table.start_hand()
    check_table_views(table, f"{label} 发底牌后")

    # 随机弃牌（可能全弃光）。
    for _ in range(rng.randint(0, 3)):
        candidates = [p for p in table.seated if p.in_hand and not p.folded]
        if not candidates:
            break
        table.set_folded(rng.choice(candidates).id, True)
        check_table_views(table, f"{label} 弃牌后")

    # 随机扰动座位与身份。
    if len(table.players) < table.max_seats and rng.random() < 0.4:
        table.add_player(f"Late{rng.randint(0, 99)}")
        check_table_views(table, f"{label} 中途入座后")
    if rng.random() < 0.3:
        table.move_player(rng.choice(table.seated).id, rng.choice(["up", "down"]))
        check_table_views(table, f"{label} 移座后")
    if rng.random() < 0.3:
        table.set_dealer(rng.choice(table.seated).id)
        check_table_views(table, f"{label} 换庄后")
    if len(table.players) > 2 and rng.random() < 0.2:
        table.remove_player(rng.choice(list(table.players)))
        check_table_views(table, f"{label} 移出玩家后")

    # 推到随机某条街。
    target = rng.choice([Street.FLOP, Street.TURN, Street.RIVER])
    while STREET_ORDER.index(table.street) < STREET_ORDER.index(target):
        table.next_street()
        check_table_views(table, f"{label} 推进到 {table.street.value} 后")

    if table.street == Street.RIVER and rng.random() < 0.5:
        table.showdown()
        check_table_views(table, f"{label} 摊牌后")

    # 不论是否摊牌，都开下一局：覆盖「提前结束」时历史不得写底牌（D11）。
    if len(table.seated) >= 2:
        table.start_hand()
        check_table_views(table, f"{label} 开新局后")


@pytest.mark.parametrize("seed", SEEDS)
def test_no_hole_card_leaks_across_random_hands(seed: int):
    rng = random.Random(seed)
    for index in range(HANDS_PER_SEED):
        table = Table(f"T{index}", rng=rng, max_seats=rng.choice([2, 6, 9]))
        for i in range(rng.randint(2, min(6, table.max_seats))):
            table.add_player(f"P{i + 1}")
        check_table_views(table, f"seed{seed}/#{index} 建桌")
        _exercise(rng, table, f"seed{seed}/#{index}")


def test_full_table_of_nine_never_leaks():
    """满桌也要覆盖：9 人时座位映射与亮牌判断的边界。"""
    rng = random.Random(7)
    table = Table("FULL", rng=rng, max_seats=9)
    for i in range(9):
        table.add_player(f"P{i + 1}")
    for index in range(5):
        _exercise(rng, table, f"满桌#{index}")


def test_late_joiner_is_a_bystander_until_the_next_hand():
    """中途入座者本局彻底旁观：不带底牌、不比牌、不进历史。"""
    table = Table("LATE", rng=random.Random(83), max_seats=9)
    for name in ("Alice", "Bob"):
        table.add_player(name)
    table.start_hand()
    cara = table.add_player("Cara")

    while table.street != Street.RIVER:
        table.next_street()
    check_table_views(table, "中途入座未发牌")

    cara_pub = next(p for p in table.board_state()["players"] if p["id"] == cara.id)
    assert "hole" not in cara_pub
    assert table.player_state(cara.id)["you"]["hole"] == []

    table.showdown()
    check_table_views(table, "摊牌")
    assert table.history[-1]["players"][cara.seat]["hole"] is None

    table.start_hand()
    check_table_views(table, "下一局")
    assert len(cara.hole) == 2
