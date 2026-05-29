"""GameEnv：Gym 风格观测 / 动作编码 + 固定动作目录 + mask（PLAN §4.5 / M2）。

本阶段只把接口留好，不训练。关键设计：
  - **固定动作目录（canonical catalog）**：把「所有可能 Combo」按规范键枚举成稳定下标，
    动作 = 目录下标 + PASS；每步配 legal-action mask，保证策略网络输出维度恒定。
  - 目录键不含 `uses_joker`（带王与否由手牌物化时决定），故同一意图唯一对应一个下标；
    给定手牌时，一个下标至多物化出一个规范 Combo（与 `generate_all_combos` 一一对应）。
  - 观测信息不完全：只暴露己方手牌 + 他人**剩余张数**，绝不泄露他人具体牌。
"""

from __future__ import annotations

import numpy as np

from engine import engine
from engine.cards import DECK_SIZE, MAX_STRAIGHT_RANK, NUM_RANKS
from engine.combos import Action, Combo, ComboType
from engine.rules import generate_all_combos, legal_actions
from engine.state import GameState


ComboKey = tuple


def combo_key(c: Combo) -> ComboKey:
    """Combo → 规范目录键（不含 uses_joker，见模块 docstring）。"""
    if c.combo_type is ComboType.SINGLE:
        return ("single", c.rank_key)
    if c.combo_type is ComboType.PAIR:
        return ("pair", c.rank_key)
    if c.combo_type is ComboType.BOMB:
        return ("bomb", c.rank_key, len(c.cards))
    lo = c.rank_key - c.length + 1
    if c.combo_type is ComboType.STRAIGHT:
        return ("straight", lo, c.length)
    return ("consec", lo, c.length)  # CONSEC_PAIRS


def _build_catalog() -> list[ComboKey]:
    keys: list[ComboKey] = []
    for r in range(NUM_RANKS):
        keys.append(("single", r))
    for r in range(NUM_RANKS):
        keys.append(("pair", r))
    for r in range(NUM_RANKS):
        for size in (3, 4):
            keys.append(("bomb", r, size))
    for lo in range(MAX_STRAIGHT_RANK + 1):
        for length in range(4, MAX_STRAIGHT_RANK + 1 - lo + 1):
            keys.append(("straight", lo, length))
    for lo in range(MAX_STRAIGHT_RANK + 1):
        for pairs in range(2, MAX_STRAIGHT_RANK + 1 - lo + 1):
            keys.append(("consec", lo, pairs))
    return keys


ACTION_CATALOG: list[ComboKey] = _build_catalog()
KEY_TO_INDEX: dict[ComboKey, int] = {k: i for i, k in enumerate(ACTION_CATALOG)}
PASS_INDEX: int = len(ACTION_CATALOG)
ACTION_SPACE_SIZE: int = PASS_INDEX + 1

_TYPE_ORDER = [
    ComboType.SINGLE,
    ComboType.PAIR,
    ComboType.STRAIGHT,
    ComboType.CONSEC_PAIRS,
    ComboType.BOMB,
]


def legal_action_mask(state: GameState, player: int) -> np.ndarray:
    """长度 = ACTION_SPACE_SIZE 的 0/1 mask（含 PASS 位）。"""
    mask = np.zeros(ACTION_SPACE_SIZE, dtype=np.int8)
    for a in legal_actions(state.hands[player], state.live_play):
        if a.is_pass:
            mask[PASS_INDEX] = 1
        else:
            assert a.combo is not None
            mask[KEY_TO_INDEX[combo_key(a.combo)]] = 1
    return mask


def decode_action(state: GameState, player: int, action_index: int) -> Action:
    """动作下标 → 具体 Action（按规范物化）。下标非法 fail hard。"""
    if action_index == PASS_INDEX:
        return Action.passing()
    target = ACTION_CATALOG[action_index]
    for c in generate_all_combos(state.hands[player]):
        if combo_key(c) == target:
            return Action.play(c)
    raise ValueError(
        f"动作下标 {action_index}（{target}）在座位 {player} 手牌下无法物化"
    )


def encode_observation(state: GameState, player: int) -> dict[str, np.ndarray]:
    """per-player 信息不完全观测（PLAN §4.5）。绝不泄露他人具体手牌。"""
    hand = np.zeros(DECK_SIZE, dtype=np.int8)
    for cid in state.hands[player]:
        hand[cid] = 1

    live = np.zeros(len(_TYPE_ORDER) + 4, dtype=np.float32)
    lp = state.live_play
    if lp is not None:
        live[_TYPE_ORDER.index(lp.combo_type)] = 1.0
        live[len(_TYPE_ORDER) + 0] = lp.rank_key / 12.0
        live[len(_TYPE_ORDER) + 1] = lp.length / float(NUM_RANKS)
        live[len(_TYPE_ORDER) + 2] = 1.0 if lp.uses_joker else 0.0
        assert state.live_player is not None
        live[len(_TYPE_ORDER) + 3] = ((state.live_player - player) % 3) / 3.0

    counts = state.hand_counts()
    rel_counts = np.array(
        [counts[(player + i) % 3] / 18.0 for i in range(3)], dtype=np.float32
    )

    return {
        "hand": hand,
        "live": live,
        "hand_counts": rel_counts,  # [自己, 下家, 再下家] 相对座位
        "bombs_played": np.array([len(state.bombs_played)], dtype=np.float32),
        "leader_rel": np.array([(state.leader - player) % 3], dtype=np.int8),
        "legal_mask": legal_action_mask(state, player),
    }


class GameEnv:
    """单局 Gym 风格环境壳。reset(seed) / step(action_index) 确定性。"""

    def __init__(self) -> None:
        self.state: GameState | None = None

    def reset(
        self, seed: int, first_leader: int | None = None
    ) -> dict[str, np.ndarray]:
        self.state = GameState.new_game(seed, first_leader)
        return encode_observation(self.state, self.state.turn)

    def step(
        self, action_index: int
    ) -> tuple[dict[str, np.ndarray], list[int], bool, dict]:
        if self.state is None:
            raise ValueError("必须先 reset()")
        player = self.state.turn
        action = decode_action(self.state, player, action_index)
        result = engine.step(self.state, action)
        self.state = result.state
        obs = encode_observation(self.state, self.state.turn)
        return obs, result.reward, result.done, result.info
