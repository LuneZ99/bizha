"""Match：整场编排——多局累计分 / 首家链 / 到 30 分判定（PLAN §4.6，§规则 3/8）。

在单局 `engine.step` 之上做薄编排，不污染单局的纯函数性。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from random import Random

from engine import engine
from engine.combos import Action
from engine.state import GameState


Policy = Callable[[GameState, int], Action]

TARGET_SCORE = 30
NUM_PLAYERS = 3


def play_single_game(
    policies: list[Policy], seed: int, first_leader: int | None
) -> GameState:
    """用给定策略把一局打到结束，返回终局状态。first_leader=None → 黑桃 3 持有者。"""
    state = GameState.new_game(seed, first_leader)
    while not state.finished:
        action = policies[state.turn](state, state.turn)
        state = engine.step(state, action).state
    return state


@dataclass
class GameRecord:
    seed: int
    first_leader: int
    winner: int
    round_score: list[int]
    num_bombs: int


@dataclass
class Match:
    """一整场（到 30 分）。持有累计分、首家链、每局结果。"""

    total_scores: list[int] = field(default_factory=lambda: [0, 0, 0])
    games: list[GameRecord] = field(default_factory=list)
    match_winner: int | None = None

    def play(self, policies: list[Policy], master_seed: int) -> int:
        """打满整场直到有人 ≥30 分，返回整场赢家座位号（§规则 8）。"""
        rng = Random(master_seed)
        first_leader: int | None = None  # 第一局按黑桃 3 持有者
        while self.match_winner is None:
            seed = rng.randrange(2**31)
            state = play_single_game(policies, seed, first_leader)
            assert state.winner is not None
            for p in range(NUM_PLAYERS):
                self.total_scores[p] += state.round_score[p]
            self.games.append(
                GameRecord(
                    seed=seed,
                    first_leader=state.first_leader,
                    winner=state.winner,
                    round_score=list(state.round_score),
                    num_bombs=len(state.bombs_played),
                )
            )
            first_leader = state.winner  # 下一局首家 = 本局赢家
            if max(self.total_scores) >= TARGET_SCORE:
                self.match_winner = max(
                    range(NUM_PLAYERS), key=lambda p: self.total_scores[p]
                )
        return self.match_winner
