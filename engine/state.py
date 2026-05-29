"""GameState：单局的唯一可序列化真相状态（PLAN §4.2）。

只描述**一局**；多局累计 / 首家链 / 到 30 分由 `match.py` 负责。
确定性纯状态机：同一 (state, action) 永远得到同一 next_state（RL 复现前提）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.cards import deal, spade_three_holder
from engine.combos import Action, Combo


@dataclass
class GameState:
    hands: list[list[int]]  # 三家完整手牌（对外按视角裁剪，见 api/views.py）
    turn: int  # 当前该谁出牌
    leader: int  # 本轮领出者
    live_play: Combo | None  # 桌面生效牌；None = 新一轮自由领出
    live_player: int | None  # 生效牌的打出者
    passed_since_live: int  # 自生效牌以来连续过牌数（达 2 重新领出）
    winner: int | None  # 本局赢家
    finished: bool
    bombs_played: list[tuple[int, Combo]]  # (player, 炸弹) 列表，用于结算
    round_score: list[int]  # 本局结算分（赢家收全场炸弹分，R1）
    first_leader: int  # 本局首家（由 Match 注入）
    history: list[tuple[int, Action]]  # 完整出牌历史（回放 / RL 观测）
    rng_seed: int

    @staticmethod
    def new_game(seed: int, first_leader: int | None = None) -> GameState:
        """发牌开一局。first_leader=None 时按黑桃 3 持有者定首家（第一局，§规则 3）。"""
        hands = deal(seed)
        leader = spade_three_holder(hands) if first_leader is None else first_leader
        return GameState(
            hands=hands,
            turn=leader,
            leader=leader,
            live_play=None,
            live_player=None,
            passed_since_live=0,
            winner=None,
            finished=False,
            bombs_played=[],
            round_score=[0, 0, 0],
            first_leader=leader,
            history=[],
            rng_seed=seed,
        )

    def clone(self) -> GameState:
        """深拷贝（step 走函数式：不就地改原状态，返回新状态）。"""
        return GameState(
            hands=[list(h) for h in self.hands],
            turn=self.turn,
            leader=self.leader,
            live_play=self.live_play,
            live_player=self.live_player,
            passed_since_live=self.passed_since_live,
            winner=self.winner,
            finished=self.finished,
            bombs_played=list(self.bombs_played),
            round_score=list(self.round_score),
            first_leader=self.first_leader,
            history=list(self.history),
            rng_seed=self.rng_seed,
        )

    def hand_counts(self) -> list[int]:
        return [len(h) for h in self.hands]


@dataclass
class StepResult:
    """step 的返回（Gym 风格，PLAN §4.4）。"""

    state: GameState
    reward: list[int]  # per-player；终局按 §规则 9+R1，否则全 0
    done: bool
    info: dict = field(default_factory=dict)
