"""测试公共构造助手。"""

from __future__ import annotations

from engine.cards import Rank, Suit, make_card
from engine.combos import Combo, parse


JOKER_A = 52
JOKER_B = 53


def card(rank: Rank, suit: Suit = Suit.SPADE) -> int:
    return make_card(rank.value, suit.value)


def natural_bomb(rank: Rank, size: int) -> Combo:
    suits = [Suit.SPADE, Suit.HEART, Suit.CLUB, Suit.DIAMOND][:size]
    return parse(tuple(make_card(rank.value, s.value) for s in suits), {})


def joker_bomb(rank: Rank, size: int) -> Combo:
    """size 张炸弹，含 1–2 张王（其余天然），王代表该点数。"""
    nat = size - 1 if size == 3 else size - 2
    jokers = [JOKER_A] if size == 3 else [JOKER_A, JOKER_B]
    suits = [Suit.SPADE, Suit.HEART, Suit.CLUB][:nat]
    cards = tuple(make_card(rank.value, s.value) for s in suits) + tuple(jokers)
    return parse(cards, {j: rank.value for j in jokers})
