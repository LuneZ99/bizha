"""引擎 step / 终局 / 结算单测（§规则 7/8/9）。"""

from __future__ import annotations

import pytest

from engine import engine
from engine.cards import Rank, Suit, make_card
from engine.combos import Action, parse
from engine.rules import legal_actions
from engine.state import GameState
from tests.conftest import card


def _make_state(hands, turn, live=None, live_player=None) -> GameState:
    return GameState(
        hands=[list(h) for h in hands],
        turn=turn,
        leader=turn,
        live_play=live,
        live_player=live_player,
        passed_since_live=0,
        winner=None,
        finished=False,
        bombs_played=[],
        round_score=[0, 0, 0],
        first_leader=turn,
        history=[],
        rng_seed=0,
    )


def test_illegal_pass_when_must_beat_raises():
    # 座位 0 能压（K > Q）却尝试 PASS → fail hard
    state = _make_state(
        hands=[[card(Rank.KING, Suit.SPADE)], [card(Rank.THREE)], [card(Rank.FOUR)]],
        turn=0,
        live=parse((card(Rank.QUEEN),), {}),
        live_player=2,
    )
    with pytest.raises(ValueError):
        engine.step(state, Action.passing())


def test_play_removes_cards_and_advances_turn():
    state = _make_state(
        hands=[
            [card(Rank.SEVEN, Suit.SPADE), card(Rank.NINE)],
            [card(Rank.THREE)],
            [card(Rank.FOUR)],
        ],
        turn=0,
    )
    combo = parse((card(Rank.SEVEN, Suit.SPADE),), {})
    res = engine.step(state, Action.play(combo))
    assert card(Rank.SEVEN, Suit.SPADE) not in res.state.hands[0]
    assert res.state.turn == 1
    assert res.state.live_player == 0
    assert not res.done


def test_two_passes_reset_trick_to_live_player():
    state = _make_state(
        hands=[
            [card(Rank.NINE, Suit.SPADE), card(Rank.THREE)],
            [card(Rank.FOUR)],
            [card(Rank.FIVE)],
        ],
        turn=0,
    )
    # 座位0领出9
    state = engine.step(
        state, Action.play(parse((card(Rank.NINE, Suit.SPADE),), {}))
    ).state
    assert state.turn == 1
    # 座位1压不过 → PASS
    state = engine.step(state, Action.passing()).state
    assert state.turn == 2 and state.passed_since_live == 1
    # 座位2压不过 → PASS，两过 → 座位0重新领出
    state = engine.step(state, Action.passing()).state
    assert state.live_play is None
    assert state.turn == 0 and state.leader == 0
    assert state.passed_since_live == 0


def test_win_on_empty_hand_and_scoring():
    # 座位 0 手里只剩一个天然 4 张炸（3分），打出即出完获胜
    bomb_cards = [make_card(Rank.SEVEN.value, s) for s in range(4)]
    state = _make_state(
        hands=[bomb_cards, [card(Rank.THREE)], [card(Rank.FOUR)]],
        turn=0,
    )
    combo = parse(tuple(bomb_cards), {})
    res = engine.step(state, Action.play(combo))
    assert res.done
    assert res.state.winner == 0
    assert res.state.finished
    assert res.state.round_score == [3, 0, 0]
    assert res.reward == [3, 0, 0]


def test_accepts_non_canonical_card_choice():
    # 手里有三张 9（S/H/C），玩家用 S+C 出对子（非规范的最低两花色）也应被接受
    nines = [make_card(Rank.NINE.value, s) for s in range(3)]
    state = _make_state(
        hands=[nines + [card(Rank.THREE)], [card(Rank.FOUR)], [card(Rank.FIVE)]],
        turn=0,
    )
    chosen = (make_card(Rank.NINE.value, 0), make_card(Rank.NINE.value, 2))
    res = engine.step(state, Action.play(parse(chosen, {})))
    assert make_card(Rank.NINE.value, 2) not in res.state.hands[0]
    assert make_card(Rank.NINE.value, 1) in res.state.hands[0]  # 中间那张 9 仍在手


def test_rejects_cards_not_in_hand():
    state = _make_state(
        hands=[[card(Rank.THREE)], [card(Rank.FOUR)], [card(Rank.FIVE)]], turn=0
    )
    with pytest.raises(ValueError):
        engine.step(state, Action.play(parse((card(Rank.KING),), {})))


def test_cannot_step_after_finished():
    state = _make_state(hands=[[card(Rank.THREE)], [], []], turn=0)
    state.finished = True
    state.winner = 1
    with pytest.raises(ValueError):
        engine.step(state, Action.passing())


def test_full_random_game_is_legal_and_terminates():
    # 用引擎自身合法动作驱动随机一局，验证始终合法且能终局
    import random

    rng = random.Random(7)
    state = GameState.new_game(seed=12345)
    steps = 0
    while not state.finished:
        legal = legal_actions(state.hands[state.turn], state.live_play)
        action = rng.choice(legal)
        state = engine.step(state, action).state
        steps += 1
        assert steps < 1000
    assert state.winner is not None
    # 赢家手牌为空，另两家非空
    assert len(state.hands[state.winner]) == 0
    assert sum(1 for h in state.hands if not h) == 1
