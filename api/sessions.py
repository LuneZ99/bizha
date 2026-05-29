"""内存对局管理（PLAN §5.2）。一个 game_id = 一整场（多局到 30）。

职责：建局 / 推进 / bot 自动行动 / 局末结算与开新局 / 整场结束判定。
纯逻辑、无 I/O；WS 广播由 server 层负责（本层 submit 返回事件列表）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from random import Random

from api.schemas import (
    ActionRequest,
    GameView,
    LegalActionsResponse,
    LegalActionView,
)
from api.views import combo_view, hand_view, history_view
from engine import bots, engine
from engine.combos import Action, parse
from engine.match import NUM_PLAYERS, TARGET_SCORE, GameRecord
from engine.rules import legal_actions
from engine.state import GameState


@dataclass
class Session:
    game_id: str
    bot_seats: set[int]
    rng: Random
    state: GameState
    total_scores: list[int] = field(default_factory=lambda: [0, 0, 0])
    games: list[GameRecord] = field(default_factory=list)
    match_finished: bool = False
    match_winner: int | None = None

    # ---------- 视角 / 合法动作 ----------

    def view(self, seat: int) -> GameView:
        s = self.state
        return GameView(
            game_id=self.game_id,
            seat=seat,
            hand=hand_view(s, seat),
            hand_counts=s.hand_counts(),
            live_play=combo_view(s.live_play) if s.live_play else None,
            live_player=s.live_player,
            turn=s.turn,
            leader=s.leader,
            first_leader=s.first_leader,
            round_finished=s.finished,
            round_winner=s.winner,
            round_score=list(s.round_score),
            total_scores=list(self.total_scores),
            games_played=len(self.games),
            bombs_played=len(s.bombs_played),
            match_finished=self.match_finished,
            match_winner=self.match_winner,
            your_turn=(s.turn == seat and not s.finished and not self.match_finished),
            history=history_view(s),
        )

    def legal(self, seat: int) -> LegalActionsResponse:
        actions = legal_actions(self.state.hands[seat], self.state.live_play)
        must_play = not (len(actions) == 1 and actions[0].is_pass)
        views = [
            LegalActionView(
                kind="pass" if a.is_pass else "play",
                combo=combo_view(a.combo) if a.combo else None,
            )
            for a in actions
        ]
        return LegalActionsResponse(seat=seat, must_play=must_play, actions=views)

    # ---------- 推进 ----------

    def submit(self, req: ActionRequest) -> list[dict]:
        """提交人类动作，应用后自动跑 bot，直到轮到人类或整场结束。返回事件列表。"""
        if self.match_finished:
            raise ValueError("整场已结束")
        if req.seat != self.state.turn:
            raise ValueError(f"还没轮到座位 {req.seat}（当前轮到 {self.state.turn}）")
        if req.seat in self.bot_seats:
            raise ValueError(f"座位 {req.seat} 由 bot 接管，不能手动提交")
        action = self._build_action(req)
        events: list[dict] = []
        self._apply(req.seat, action, events)
        self._run_bots(events)
        return events

    def _build_action(self, req: ActionRequest) -> Action:
        if req.kind == "pass":
            return Action.passing()
        combo = parse(tuple(req.cards), dict(req.joker_assignment))
        return Action.play(combo)

    def _run_bots(self, events: list[dict]) -> None:
        while (
            not self.match_finished
            and not self.state.finished
            and self.state.turn in self.bot_seats
        ):
            seat = self.state.turn
            action = bots.choose_action(self.state, seat)
            self._apply(seat, action, events)

    def _apply(self, seat: int, action: Action, events: list[dict]) -> None:
        result = engine.step(self.state, action)
        self.state = result.state
        events.append(
            {
                "type": "action",
                "seat": seat,
                "action": "pass" if action.is_pass else "play",
                "combo": combo_view(action.combo).model_dump()
                if action.combo
                else None,
            }
        )
        if self.state.finished:
            self._on_round_end(events)

    def _on_round_end(self, events: list[dict]) -> None:
        s = self.state
        assert s.winner is not None
        for p in range(NUM_PLAYERS):
            self.total_scores[p] += s.round_score[p]
        self.games.append(
            GameRecord(
                seed=s.rng_seed,
                first_leader=s.first_leader,
                winner=s.winner,
                round_score=list(s.round_score),
                num_bombs=len(s.bombs_played),
            )
        )
        events.append(
            {
                "type": "round_end",
                "winner": s.winner,
                "round_score": list(s.round_score),
                "total_scores": list(self.total_scores),
            }
        )
        if max(self.total_scores) >= TARGET_SCORE:
            self.match_finished = True
            self.match_winner = max(
                range(NUM_PLAYERS), key=lambda p: self.total_scores[p]
            )
            events.append(
                {
                    "type": "match_end",
                    "winner": self.match_winner,
                    "total_scores": list(self.total_scores),
                }
            )
        else:
            # 开下一局：上一局赢家为首家，重新随机发牌（§规则 3/8）。
            seed = self.rng.randrange(2**31)
            self.state = GameState.new_game(seed, first_leader=s.winner)
            events.append(
                {
                    "type": "round_start",
                    "first_leader": self.state.first_leader,
                    "seed": seed,
                }
            )


class SessionManager:
    """game_id → Session 的内存表。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, seed: int, bot_seats: list[int]) -> Session:
        rng = Random(seed)
        first_seed = rng.randrange(2**31)
        state = GameState.new_game(first_seed, first_leader=None)
        game_id = uuid.uuid4().hex[:12]
        session = Session(
            game_id=game_id,
            bot_seats=set(bot_seats),
            rng=rng,
            state=state,
        )
        self._sessions[game_id] = session
        # 若首家是 bot，先把 bot 跑到轮到人类。
        events: list[dict] = []
        session._run_bots(events)
        return session

    def get(self, game_id: str) -> Session:
        if game_id not in self._sessions:
            raise KeyError(f"对局 {game_id} 不存在")
        return self._sessions[game_id]
