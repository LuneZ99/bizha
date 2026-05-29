"""GameEngine：单局状态机 reset / step / 终局判定（PLAN §4.4）。

确定性纯函数式：step 不就地修改传入状态，返回新状态。非法动作 fail hard。
"""

from __future__ import annotations

from engine.combos import Action, ActionKind, Combo, ComboType
from engine.rules import generate_all_combos, settle_round
from engine.state import GameState, StepResult


NUM_PLAYERS = 3


def _next_player(p: int) -> int:
    return (p + 1) % NUM_PLAYERS


def _validate(state: GameState, player: int, action: Action) -> None:
    """结构化校验动作合法性（§规则 7）。非法 fail hard。

    PLAY 接受**任意**满足约束的合法组合（不限定规范形式里的具体花色选择），
    这样人类用不同花色凑同一牌型也能被接受；只校验：牌来自手牌、牌型合法、
    （有生效牌时）必须压过。PASS 仅在「确实无任何组合能压」时合法（能压必须压）。
    """
    hand = state.hands[player]
    if action.kind is ActionKind.PASS:
        if state.live_play is None:
            raise ValueError(f"座位 {player} 领出不能 PASS（§规则 7.1）")
        if any(c.beats(state.live_play) for c in generate_all_combos(hand)):
            raise ValueError(f"座位 {player} 能压必须压，不允许 PASS（§规则 7.3）")
        return
    combo = action.combo
    assert combo is not None
    if not set(combo.cards).issubset(hand):
        raise ValueError(f"座位 {player} 出的牌不在手牌中：{combo.cards}")
    if state.live_play is not None and not combo.beats(state.live_play):
        raise ValueError(
            f"座位 {player} 出的 {combo.combo_type.value} 压不过生效牌（§规则 6/7.2）"
        )


def step(state: GameState, action: Action) -> StepResult:
    """推进一步（§规则 7）。校验合法性 → 应用 → 轮转 / 结算。"""
    if state.finished:
        raise ValueError("本局已结束，不能继续出牌")

    player = state.turn
    _validate(state, player, action)

    s = state.clone()
    s.history.append((player, action))

    if action.kind is ActionKind.PASS:
        return _apply_pass(s, player)
    return _apply_play(s, player, action.combo)


def _apply_pass(s: GameState, player: int) -> StepResult:
    s.passed_since_live += 1
    if s.passed_since_live >= NUM_PLAYERS - 1:
        # 其余两人都过 → 生效牌打出者赢本轮，由他重新领出（§规则 7.4）。
        winner_of_trick = s.live_player
        assert winner_of_trick is not None
        s.live_play = None
        s.live_player = None
        s.passed_since_live = 0
        s.leader = winner_of_trick
        s.turn = winner_of_trick
    else:
        s.turn = _next_player(player)
    return StepResult(state=s, reward=[0, 0, 0], done=False, info={"action": "pass"})


def _apply_play(s: GameState, player: int, combo: Combo | None) -> StepResult:
    assert combo is not None
    for cid in combo.cards:
        s.hands[player].remove(cid)
    s.live_play = combo
    s.live_player = player
    s.passed_since_live = 0
    if combo.combo_type is ComboType.BOMB:
        s.bombs_played.append((player, combo))

    if not s.hands[player]:
        # 最早出完者获胜，本局立即结束（§规则 8 / R5）。
        s.winner = player
        s.finished = True
        s.round_score = settle_round(s.bombs_played, player)
        return StepResult(
            state=s,
            reward=list(s.round_score),
            done=True,
            info={"action": "play", "winner": player},
        )

    s.turn = _next_player(player)
    return StepResult(state=s, reward=[0, 0, 0], done=False, info={"action": "play"})
