"""GameState → 按玩家视角的 JSON（PLAN §5.2）。隐藏他人具体手牌，只暴露张数。"""

from __future__ import annotations

from api.schemas import CardView, ComboView, HistoryEntry
from engine.cards import card_label
from engine.combos import ActionKind, Combo
from engine.state import GameState


def combo_view(combo: Combo) -> ComboView:
    return ComboView(
        combo_type=combo.combo_type.value,
        cards=list(combo.cards),
        length=combo.length,
        rank_key=combo.rank_key,
        uses_joker=combo.uses_joker,
        joker_assignment=dict(combo.joker_assignment),
    )


def history_view(state: GameState) -> list[HistoryEntry]:
    out: list[HistoryEntry] = []
    for player, action in state.history:
        if action.kind is ActionKind.PASS:
            out.append(HistoryEntry(player=player, kind="pass"))
        else:
            assert action.combo is not None
            out.append(
                HistoryEntry(player=player, kind="play", combo=combo_view(action.combo))
            )
    return out


def hand_view(state: GameState, seat: int) -> list[CardView]:
    return [CardView(id=c, label=card_label(c)) for c in state.hands[seat]]
