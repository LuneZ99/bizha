"""牌 / 点数 / 花色 / 牌堆 —— 54 张牌的稳定定义。

card id 约定（前后端 + RL 共用，见 PLAN §4.1 / §6.1）：
  - 普通牌：id = rank_order * 4 + suit_order，范围 0–51。
  - 王（大小王不区分，§规则 2.1）：id 52、53，均为万能牌。
  - 黑桃 3 = rank_order 0 + suit SPADE(0) = id 0（第一局首家判定，§规则 3）。
"""

from __future__ import annotations

from enum import IntEnum


class Suit(IntEnum):
    """花色。只用于区分物理牌与第一局首家（黑桃 3），不参与牌型比较。"""

    SPADE = 0
    HEART = 1
    CLUB = 2
    DIAMOND = 3


class Rank(IntEnum):
    """单牌点数，承载大小序 3<4<…<A<2（§规则 2.2）。`value` 即比较用的 order。"""

    THREE = 0
    FOUR = 1
    FIVE = 2
    SIX = 3
    SEVEN = 4
    EIGHT = 5
    NINE = 6
    TEN = 7
    JACK = 8
    QUEEN = 9
    KING = 10
    ACE = 11
    TWO = 12


# 顺子最高连到 A（rank 11），不含 2（rank 12）；连对同理（§规则 5）。
MAX_STRAIGHT_RANK = Rank.ACE.value
NUM_RANKS = 13
NUM_SUITS = 4
NUM_NORMAL = NUM_RANKS * NUM_SUITS  # 52
NUM_JOKERS = 2
DECK_SIZE = NUM_NORMAL + NUM_JOKERS  # 54
JOKER_IDS = (52, 53)
SPADE_THREE_ID = 0

RANK_LABELS = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"]
SUIT_LABELS = ["S", "H", "C", "D"]


def is_joker(card_id: int) -> bool:
    return card_id >= NUM_NORMAL


def card_rank(card_id: int) -> int:
    """普通牌的点数 order；王没有固定点数，调用前必须自行排除。"""
    if is_joker(card_id):
        raise ValueError(f"王（id={card_id}）没有固定点数")
    return card_id // NUM_SUITS


def card_suit(card_id: int) -> int:
    if is_joker(card_id):
        raise ValueError(f"王（id={card_id}）没有花色")
    return card_id % NUM_SUITS


def make_card(rank: int, suit: int) -> int:
    return rank * NUM_SUITS + suit


def card_label(card_id: int) -> str:
    if is_joker(card_id):
        return "JOKER"
    return f"{RANK_LABELS[card_rank(card_id)]}{SUIT_LABELS[card_suit(card_id)]}"


def deal(seed: int) -> list[list[int]]:
    """按显式 RNG 把 54 张随机发给 3 人，每人 18 张（§规则 3）。

    确定性：同一 seed 永远得到同一发牌（RL 复现前提，PLAN §4.5）。
    """
    import random

    rng = random.Random(seed)
    cards = list(range(DECK_SIZE))
    rng.shuffle(cards)
    hands = [sorted(cards[i * 18 : (i + 1) * 18]) for i in range(3)]
    return hands


def spade_three_holder(hands: list[list[int]]) -> int:
    """返回持有黑桃 3 的座位号（第一局首家，§规则 3）。"""
    for seat, hand in enumerate(hands):
        if SPADE_THREE_ID in hand:
            return seat
    raise ValueError("发牌结果中找不到黑桃 3，发牌逻辑有误")
