"""接口层网络模型（pydantic）——仅在接口边界使用，与引擎解耦（PLAN §5 / §7.3）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CreateGameRequest(BaseModel):
    """新建一整场（到 30 分）。bot_seats 指定哪些座位由内置 bot 接管。"""

    seed: int = 42
    bot_seats: list[int] = Field(default_factory=lambda: [1, 2])


class CardView(BaseModel):
    id: int
    label: str


class ComboView(BaseModel):
    combo_type: str
    cards: list[int]
    length: int
    rank_key: int
    uses_joker: bool
    joker_assignment: dict[int, int]  # joker card_id → 代表的 rank order


class HistoryEntry(BaseModel):
    player: int
    kind: Literal["play", "pass"]
    combo: ComboView | None = None


class GameView(BaseModel):
    """按某座位视角裁剪后的对局状态（隐藏他人具体手牌）。"""

    game_id: str
    seat: int
    hand: list[CardView]  # 仅己方手牌
    hand_counts: list[int]  # 三家剩余张数（绝对座位）
    live_play: ComboView | None
    live_player: int | None
    turn: int
    leader: int
    first_leader: int
    round_finished: bool
    round_winner: int | None
    round_score: list[int]
    total_scores: list[int]  # 整场累计分（/30）
    games_played: int
    bombs_played: int
    match_finished: bool
    match_winner: int | None
    your_turn: bool
    history: list[HistoryEntry]


class LegalActionView(BaseModel):
    kind: Literal["play", "pass"]
    combo: ComboView | None = None


class LegalActionsResponse(BaseModel):
    seat: int
    must_play: bool  # 是否「能压必须压」（无 PASS 选项）
    actions: list[LegalActionView]


class ActionRequest(BaseModel):
    """提交动作。play 需带 cards（card_id 列表）+ 含王时的 joker_assignment。"""

    seat: int
    kind: Literal["play", "pass"]
    cards: list[int] = Field(default_factory=list)
    joker_assignment: dict[int, int] = Field(default_factory=dict)
