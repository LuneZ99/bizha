"""牌型识别 + 比较单测（§规则 4/5/6）。"""

from __future__ import annotations

import pytest

from engine.cards import Rank, Suit, make_card
from engine.combos import ComboType, parse
from tests.conftest import (
    JOKER_A,
    card,
    joker_bomb,
    natural_bomb,
)


# ---------------- 牌型识别 ----------------


def test_single():
    c = parse((card(Rank.SEVEN),), {})
    assert c.combo_type is ComboType.SINGLE
    assert c.rank_key == Rank.SEVEN.value
    assert not c.uses_joker


def test_joker_single_as_two():
    c = parse((JOKER_A,), {JOKER_A: Rank.TWO.value})
    assert c.combo_type is ComboType.SINGLE
    assert c.rank_key == Rank.TWO.value
    assert c.uses_joker


def test_joker_single_cannot_exceed_two():
    with pytest.raises(ValueError):
        parse((JOKER_A,), {JOKER_A: 13})


def test_pair_and_joker_pair():
    nat = parse((card(Rank.KING, Suit.SPADE), card(Rank.KING, Suit.HEART)), {})
    assert nat.combo_type is ComboType.PAIR and not nat.uses_joker
    jok = parse((card(Rank.KING, Suit.SPADE), JOKER_A), {JOKER_A: Rank.KING.value})
    assert jok.combo_type is ComboType.PAIR and jok.uses_joker


def test_pair_mismatch_raises():
    with pytest.raises(ValueError):
        parse((card(Rank.KING), card(Rank.QUEEN)), {})


def test_straight():
    cards = tuple(card(r) for r in (Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX))
    c = parse(cards, {})
    assert c.combo_type is ComboType.STRAIGHT
    assert c.length == 4
    assert c.rank_key == Rank.SIX.value


def test_straight_with_joker_fills_gap():
    # 5 6 _ 8 → 王只能当 7，构成 5678 顺子
    cards = (card(Rank.FIVE), card(Rank.SIX), JOKER_A, card(Rank.EIGHT))
    c = parse(cards, {JOKER_A: Rank.SEVEN.value})
    assert c.combo_type is ComboType.STRAIGHT
    assert c.uses_joker
    assert c.rank_key == Rank.EIGHT.value


def test_straight_cannot_include_two():
    cards = (
        card(Rank.JACK),
        card(Rank.QUEEN),
        card(Rank.KING),
        card(Rank.ACE),
        card(Rank.TWO),
    )
    with pytest.raises(ValueError):
        parse(cards, {})


def test_straight_too_short():
    cards = (card(Rank.THREE), card(Rank.FOUR), card(Rank.FIVE))
    # 3 张连续不是顺子（顺子≥4），且点数不同也不是炸/对 → 非法
    with pytest.raises(ValueError):
        parse(cards, {})


def test_consec_pairs():
    cards = (
        card(Rank.THREE, Suit.SPADE),
        card(Rank.THREE, Suit.HEART),
        card(Rank.FOUR, Suit.SPADE),
        card(Rank.FOUR, Suit.HEART),
    )
    c = parse(cards, {})
    assert c.combo_type is ComboType.CONSEC_PAIRS
    assert c.length == 2
    assert c.rank_key == Rank.FOUR.value


def test_consec_pairs_cannot_include_two():
    cards = (
        card(Rank.ACE, Suit.SPADE),
        card(Rank.ACE, Suit.HEART),
        card(Rank.TWO, Suit.SPADE),
        card(Rank.TWO, Suit.HEART),
    )
    with pytest.raises(ValueError):
        parse(cards, {})


def test_bomb_three_and_four():
    b3 = natural_bomb(Rank.SEVEN, 3)
    b4 = natural_bomb(Rank.SEVEN, 4)
    assert b3.combo_type is ComboType.BOMB and len(b3.cards) == 3
    assert b4.combo_type is ComboType.BOMB and len(b4.cards) == 4


def test_bomb_five_is_illegal():
    cards = tuple(make_card(Rank.SEVEN.value, s) for s in range(4)) + (JOKER_A,)
    with pytest.raises(ValueError):
        parse(cards, {JOKER_A: Rank.SEVEN.value})


def test_missing_joker_assignment_raises():
    with pytest.raises(ValueError):
        parse((JOKER_A,), {})


# ---------------- 比较 / 压牌（§规则 6）----------------


def test_single_compare():
    two = parse((card(Rank.TWO),), {})
    ace = parse((card(Rank.ACE),), {})
    assert two.beats(ace)
    assert not ace.beats(two)


def test_joker_two_ties_natural_two():
    # R4：单张王当 2，压不过天然单张 2（并列，互不相压）
    nat2 = parse((card(Rank.TWO),), {})
    jok2 = parse((JOKER_A,), {JOKER_A: Rank.TWO.value})
    assert not jok2.beats(nat2)
    assert not nat2.beats(jok2)


def test_straight_same_length_only():
    s4 = parse(tuple(card(r) for r in (Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX)), {})
    s4_hi = parse(
        tuple(card(r) for r in (Rank.FOUR, Rank.FIVE, Rank.SIX, Rank.SEVEN)), {}
    )
    s5 = parse(
        tuple(
            card(r) for r in (Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX, Rank.SEVEN)
        ),
        {},
    )
    assert s4_hi.beats(s4)
    assert not s5.beats(s4)  # 不同长度不可比
    assert not s4.beats(s5)


def test_bomb_beats_non_bomb():
    bomb = natural_bomb(Rank.THREE, 3)
    single = parse((card(Rank.TWO),), {})
    assert bomb.beats(single)
    assert not single.beats(bomb)


def test_bomb_full_ordering():
    # 带王3 < 不带王3 < 带王4 < 不带王4（§规则 6.3）
    j3 = joker_bomb(Rank.TWO, 3)  # 带王 3 张，点数最大(2)
    n3 = natural_bomb(Rank.THREE, 3)  # 不带王 3 张，点数最小(3)
    j4 = joker_bomb(Rank.THREE, 4)  # 带王 4 张，点数最小
    n4 = natural_bomb(Rank.THREE, 4)  # 不带王 4 张
    assert n3.beats(j3)  # 不带王3 > 带王3（哪怕带王的点数更大）
    assert j4.beats(n3)  # 4 张 > 任意 3 张
    assert n4.beats(j4)  # 不带王4 > 带王4
    # 最大炸 = 不带王四个 2
    n4_two = natural_bomb(Rank.TWO, 4)
    assert n4_two.beats(n4)


def test_bomb_same_layer_rank():
    low = natural_bomb(Rank.THREE, 4)
    high = natural_bomb(Rank.ACE, 4)
    assert high.beats(low)
    assert not low.beats(high)
