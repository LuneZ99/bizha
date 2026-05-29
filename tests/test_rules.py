"""合法动作生成 + 「能压必须压」+ 结算单测（§规则 7.3/9）。"""

from __future__ import annotations

from engine.cards import Rank, Suit, make_card
from engine.combos import ActionKind, ComboType, parse
from engine.rules import generate_all_combos, legal_actions, settle_round
from tests.conftest import JOKER_A, JOKER_B, card, natural_bomb


def _has_pass(actions) -> bool:
    return any(a.kind is ActionKind.PASS for a in actions)


def test_lead_never_allows_pass():
    hand = [card(Rank.THREE, Suit.SPADE), card(Rank.SEVEN, Suit.HEART)]
    actions = legal_actions(hand, None)
    assert actions and not _has_pass(actions)


def test_must_beat_when_possible():
    # 手里有 K 单，桌面是 Q 单 → 能压必须压，不允许 PASS
    hand = [card(Rank.KING, Suit.SPADE), card(Rank.THREE, Suit.HEART)]
    live = parse((card(Rank.QUEEN),), {})
    actions = legal_actions(hand, live)
    assert not _has_pass(actions)
    assert all(
        a.combo is not None and a.combo.rank_key == Rank.KING.value for a in actions
    )


def test_pass_only_when_cannot_beat():
    # 手里全是小单，桌面是 2 单 → 压不过，唯一动作 PASS
    hand = [card(Rank.THREE, Suit.SPADE), card(Rank.FOUR, Suit.HEART)]
    live = parse((card(Rank.TWO),), {})
    actions = legal_actions(hand, live)
    assert len(actions) == 1 and actions[0].kind is ActionKind.PASS


def test_forced_bomb_against_non_bomb():
    # 桌面单张 A；手里没有更大的单，但有三个 5（炸）→ 必须炸（R2，含炸无豁免）
    hand = [
        make_card(Rank.FIVE.value, 0),
        make_card(Rank.FIVE.value, 1),
        make_card(Rank.FIVE.value, 2),
        card(Rank.THREE, Suit.HEART),
    ]
    live = parse((card(Rank.ACE),), {})
    actions = legal_actions(hand, live)
    assert not _has_pass(actions)
    assert all(
        a.combo is not None and a.combo.combo_type is ComboType.BOMB for a in actions
    )


def test_forced_bigger_bomb_against_bomb():
    # 桌面三个 5 炸；手里有四个 6（更大炸）→ 必须用更大的炸压（含 4 压 3）
    hand = [make_card(Rank.SIX.value, s) for s in range(4)] + [card(Rank.THREE)]
    live = natural_bomb(Rank.FIVE, 3)
    actions = legal_actions(hand, live)
    assert not _has_pass(actions)
    assert all(a.combo is not None and a.combo.beats(live) for a in actions)


def test_generate_canonical_no_wasted_joker():
    # 有两张天然 9 + 一张王：对子 9 应是天然对（不拿王去顶），王留作他用
    hand = [make_card(Rank.NINE.value, 0), make_card(Rank.NINE.value, 1), JOKER_A]
    combos = generate_all_combos(hand)
    pairs9 = [
        c
        for c in combos
        if c.combo_type is ComboType.PAIR and c.rank_key == Rank.NINE.value
    ]
    assert len(pairs9) == 1
    assert not pairs9[0].uses_joker


def test_settle_round_winner_takes_all_bomb_points():
    # 两个炸：天然(3分) + 带王(1分)，赢家是座位 1 → 全归座位 1
    nat = natural_bomb(Rank.SEVEN, 4)  # 3 分
    jok = parse(
        (make_card(Rank.EIGHT.value, 0), make_card(Rank.EIGHT.value, 1), JOKER_A),
        {JOKER_A: Rank.EIGHT.value},
    )  # 带王 → 1 分
    score = settle_round([(0, nat), (2, jok)], winner=1)
    assert score == [0, 4, 0]


def test_two_jokers_make_consec_pairs():
    # 两张天然 3 + 一张天然 4 + 一张王 → 33 44（王补一张 4）连对
    hand = [
        make_card(Rank.THREE.value, 0),
        make_card(Rank.THREE.value, 1),
        make_card(Rank.FOUR.value, 0),
        JOKER_A,
    ]
    combos = generate_all_combos(hand)
    cps = [c for c in combos if c.combo_type is ComboType.CONSEC_PAIRS]
    assert any(c.rank_key == Rank.FOUR.value and c.uses_joker for c in cps)


def test_no_duplicate_combos():
    # 含两张王的手牌也不应生成重复 Combo（规范去重）
    hand = [make_card(r * 4 + 0, 0) if False else make_card(r, 0) for r in range(0, 13)]
    hand += [JOKER_A, JOKER_B]
    combos = generate_all_combos(hand)
    keys = [
        c.cards + (c.combo_type.value,) + tuple(sorted(c.joker_assignment))
        for c in combos
    ]
    assert len(keys) == len(set(keys))
