"""与第三方评估器（treys）的**差分测试**。

为什么需要它：自写的评估器最容易错在**边界**（轮子、同花顺的排序），
而随机测试几乎碰不到稀有牌型（7 张出同花顺的概率约 0.031%）。

做法：用 treys 作**独立参照**。
关键点——**不要求任何一方给出"真值"**，只要求两个独立实现在**排序**上一致。
这叫 differential testing：不需要 oracle，只需要两个实现互相独立。

treys 只在 **dev 依赖**里（`uv sync` 会装），运行时依赖仍为零。
"""

from __future__ import annotations

import random
from itertools import combinations

import pytest

treys = pytest.importorskip("treys")  # 未装 dev 依赖时跳过，而不是报错

from treys import Card as TCard  # noqa: E402
from treys import Evaluator  # noqa: E402

from webpokerdealer.game.cards import Card, make_deck  # noqa: E402
from webpokerdealer.game.evaluator import best_hand, hand_name  # noqa: E402

EVALUATOR = Evaluator()

# 5 张手牌的已知等价类总数（Cactus Kev 的经典结论），treys 的 rank 取值即 1..7462
FIVE_CARD_RANKS = 7462


def cards(text: str) -> list[Card]:
    """Parse ``"As Kd Qh"`` into Card objects."""
    return [Card(code[0], code[1]) for code in text.split()]


def reference_rank(hand: list[Card]) -> int:
    """treys 的 rank：**数字越小越强**（与 ``best_hand`` 方向相反）。"""
    parsed = [TCard.new(card.code) for card in hand]
    return EVALUATOR.evaluate(parsed[:5], parsed[5:])


def compare(left, right) -> int:
    """把比较压成 -1 / 0 / 1（1 表示 left 更强）。"""
    return (left > right) - (left < right)


# --------------------------------------------------------------------------- #
# 1) 显式边界：随机测试覆盖不到的稀有牌型
# --------------------------------------------------------------------------- #
EDGE_CASES = [
    ("轮子是最小的顺子", "As 2h 3d 4c 5s Kd Qh", "顺子"),
    ("6-high 顺", "2s 3h 4d 5c 6s Kd Qh", "顺子"),
    ("钢轮（同花轮子）", "As 2s 3s 4s 5s Kd Qh", "同花顺"),
    ("皇家同花顺", "As Ks Qs Js Ts 2d 3h", "皇家同花顺"),
    ("同花（含 A 高）", "As Ks 9s 5s 2s Qd Jh", "同花"),
    ("葫芦", "As Ah Ad Ks Kh 2c 3d", "葫芦"),
    ("四条", "As Ah Ad Ac Kh 2c 3d", "四条"),
]


@pytest.mark.parametrize(("label", "hand", "expected"), EDGE_CASES, ids=[c[0] for c in EDGE_CASES])
def test_edge_case_categories(label: str, hand: str, expected: str):
    assert hand_name(best_hand(cards(hand))) == expected


def test_wheel_ranks_below_six_high_straight():
    """扑克最反直觉的一点：A 在轮子里当 1 用，所以轮子是最小的顺子。"""
    wheel = cards("As 2h 3d 4c 5s Kd Qh")
    six_high = cards("2s 3h 4d 5c 6s Kd Qh")
    assert compare(best_hand(wheel), best_hand(six_high)) == -1
    # 参照实现必须同意（treys 数字越小越强）
    assert reference_rank(wheel) > reference_rank(six_high)


# --------------------------------------------------------------------------- #
# 2) 随机对拍：排序一致性
# --------------------------------------------------------------------------- #
def test_ordering_agrees_with_reference():
    """随机取两手 7 张牌，两边对「谁更强」的判断必须一致。

    固定种子 → 失败可复现。
    """
    rng = random.Random(20240917)
    deck = make_deck()
    mismatches = []

    for _ in range(3000):
        left, right = rng.sample(deck, 7), rng.sample(deck, 7)
        mine = compare(best_hand(left), best_hand(right))
        theirs = -compare(reference_rank(left), reference_rank(right))  # treys 方向相反
        if mine != theirs:
            mismatches.append((left, right, mine, theirs))

    assert not mismatches, (
        f"{len(mismatches)} 处排序不一致，前 3 例：\n"
        + "\n".join(
            f"  L={' '.join(c.code for c in l)} R={' '.join(c.code for c in r)} "
            f"我={m} treys={t}"
            for l, r, m, t in mismatches[:3]
        )
    )


def test_category_distribution_agrees_with_reference():
    """宏观检查：随机手牌的牌型频次两边应一致（抓系统性偏差）。"""
    rng = random.Random(7)
    deck = make_deck()
    pairs = set()
    for _ in range(3000):
        hand = rng.sample(deck, 7)
        mine = hand_name(best_hand(hand))
        theirs = EVALUATOR.class_to_string(EVALUATOR.get_rank_class(reference_rank(hand)))
        pairs.add((mine, theirs))

    # 中英文各 10 类，映射应是一一对应，不应出现「同一种牌型被分成两类」
    assert len({mine for mine, _ in pairs}) == len({theirs for _, theirs in pairs})
    assert len(pairs) == len({mine for mine, _ in pairs})


# --------------------------------------------------------------------------- #
# 3) 穷举：在 5 张手牌空间上做**完备**验证（默认不跑）
# --------------------------------------------------------------------------- #
@pytest.mark.slow
@pytest.mark.timeout(900)
def test_exhaustive_five_card_space_matches_reference():
    """穷举全部 C(52,5) = 2,598,960 手 5 张牌。

    断言两边构成**双射**（既不误合并、也不误区分）：
      - 同一个 ``best_hand`` 分数 ⟺ 同一个 treys rank
      - 两边各自恰好 7462 个等价类（5 张手牌的已知 rank 总数）

    跑法：``uv run pytest -m slow``（实测约 15 秒）。
    默认不跑的理由不是慢，而是它比其余全部用例加起来还大一个量级。
    """
    seen: dict[tuple, int] = {}
    for combo in combinations(make_deck(), 5):
        hand = list(combo)
        score = best_hand(hand)
        rank = reference_rank(hand)
        previous = seen.setdefault(score, rank)
        assert previous == rank, f"同一 best_hand 分数对应了不同 rank: {hand}"

    assert len(seen) == FIVE_CARD_RANKS, f"等价类数应为 {FIVE_CARD_RANKS}，实得 {len(seen)}"
    assert len(set(seen.values())) == FIVE_CARD_RANKS, "存在 rank 被合并，两边不是双射"
