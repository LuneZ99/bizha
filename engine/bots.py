"""SimpleBot：本阶段基线 AI（PLAN §5.3）。

复用引擎的 `legal_actions` / `Combo`，不另写规则。策略函数签名
`(state, player) -> Action`，将来可直接被 RL policy 替换，对局流程不变。偏好：
  1. 领出优先甩最长的连张（顺子 / 连对）；
  2. 出单 / 出对尽量低、不主动用王；
  3. 炸弹保守——还能出别的就绝不主动炸，只有强制必须炸时才炸，且挑最弱的炸。
"""

from __future__ import annotations

from engine.combos import Action, Combo, ComboType
from engine.rules import legal_actions
from engine.state import GameState


_CHAIN_TYPES = (ComboType.STRAIGHT, ComboType.CONSEC_PAIRS)


def _is_bomb(c: Combo) -> bool:
    return c.combo_type is ComboType.BOMB


def choose_action(state: GameState, player: int) -> Action:
    legal = legal_actions(state.hands[player], state.live_play)
    if len(legal) == 1 and legal[0].is_pass:
        return legal[0]

    combos = [a.combo for a in legal if a.combo is not None]
    non_bomb = [c for c in combos if not _is_bomb(c)]

    if state.live_play is None:
        return Action.play(_choose_lead(combos, non_bomb))
    return Action.play(_choose_follow(combos, non_bomb))


def _choose_lead(combos: list[Combo], non_bomb: list[Combo]) -> Combo:
    chains = [c for c in non_bomb if c.combo_type in _CHAIN_TYPES]
    if chains:
        # 甩最长的连张：先按张数最多，再点数最低（尽快处理长链 + 留大牌）。
        return max(chains, key=lambda c: (len(c.cards), -c.rank_key))
    simple = [c for c in non_bomb if c.combo_type in (ComboType.SINGLE, ComboType.PAIR)]
    if simple:
        # 出低牌、尽量不用王、对子优先（一次清两张）。
        return min(
            simple,
            key=lambda c: (c.uses_joker, c.rank_key, c.combo_type is ComboType.SINGLE),
        )
    # 满手只能拆成炸 —— 被迫领炸，挑最弱的。
    return min(combos, key=lambda c: c._bomb_key())


def _choose_follow(combos: list[Combo], non_bomb: list[Combo]) -> Combo:
    if non_bomb:
        # 能压必须压：用刚好压过的最小非炸牌，省下大牌与王。
        return min(non_bomb, key=lambda c: (c.uses_joker, c.rank_key, len(c.cards)))
    # 只能用炸压 —— 挑最弱的炸（保守，§规则 7.3 强制但不浪费大炸）。
    return min(combos, key=lambda c: c._bomb_key())
