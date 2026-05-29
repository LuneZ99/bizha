"""合法动作生成（含「能压必须压」）+ 积分结算 —— §规则 6/7/9。

生成策略（关键，决定动作空间是否爆炸，PLAN §4.3.3 / §9）：
  **王只用于补缺口，能用普通牌就不用王（canonical / 规范形式）。**
  - 单/对/炸：某点数需 k 张，先用尽该点数的普通牌，不足部分才用王。
  - 顺子/连对：某点数位上有普通牌就用普通牌，缺位才用王。
  这样同一「有效牌面 + 牌型」只保留一种规范出法，避免王的等价指派把动作空间炸开；
  被规范形式排除掉的都是「明明有普通牌却拿王去顶」的劣化变体，不影响「能否压」的判定。
"""

from __future__ import annotations

from engine.cards import (
    MAX_STRAIGHT_RANK,
    NUM_RANKS,
    card_rank,
    is_joker,
)
from engine.combos import Action, Combo, ComboType


def _index_hand(hand: list[int]) -> tuple[list[list[int]], list[int]]:
    """把手牌拆成 by_rank[r]=该点数普通牌 id 升序 + jokers=王 id 升序。"""
    by_rank: list[list[int]] = [[] for _ in range(NUM_RANKS)]
    jokers: list[int] = []
    for cid in sorted(hand):
        if is_joker(cid):
            jokers.append(cid)
        else:
            by_rank[card_rank(cid)].append(cid)
    return by_rank, jokers


def _make_group(
    rank: int,
    need: int,
    naturals: list[int],
    jokers: list[int],
    joker_cursor: int,
) -> tuple[list[int], list[tuple[int, int]], int] | None:
    """凑 need 张有效点数为 rank 的牌：先用普通牌，缺口用王（从 joker_cursor 起）。

    返回 (card_ids, [(joker_id, rank)...], 新 joker_cursor)；王不够则返回 None。
    """
    use_nat = min(len(naturals), need)
    need_jokers = need - use_nat
    if joker_cursor + need_jokers > len(jokers):
        return None
    cards = naturals[:use_nat]
    assign: list[tuple[int, int]] = []
    for _ in range(need_jokers):
        jid = jokers[joker_cursor]
        cards.append(jid)
        assign.append((jid, rank))
        joker_cursor += 1
    return cards, assign, joker_cursor


def _combo(
    cards: list[int],
    ctype: ComboType,
    length: int,
    rank_key: int,
    assign: list[tuple[int, int]],
) -> Combo:
    return Combo(
        cards=tuple(sorted(cards)),
        combo_type=ctype,
        length=length,
        rank_key=rank_key,
        uses_joker=bool(assign),
        joker_assignment=tuple(sorted(assign)),
    )


def generate_all_combos(hand: list[int]) -> list[Combo]:
    """枚举手牌能组成的所有合法牌型的规范形式（§规则 5，去重见模块 docstring）。"""
    by_rank, jokers = _index_hand(hand)
    cnt = [len(by_rank[r]) for r in range(NUM_RANKS)]
    nj = len(jokers)
    out: list[Combo] = []

    # ---- 单牌：每个点数一种规范单（有普通牌用普通牌，否则用王代该点数）----
    for r in range(NUM_RANKS):
        if cnt[r] >= 1:
            out.append(_combo([by_rank[r][0]], ComboType.SINGLE, 1, r, []))
        elif nj >= 1:
            out.append(_combo([jokers[0]], ComboType.SINGLE, 1, r, [(jokers[0], r)]))

    # ---- 对子：每个点数一种规范对 ----
    for r in range(NUM_RANKS):
        g = _make_group(r, 2, by_rank[r], jokers, 0)
        if g is not None:
            cards, assign, _ = g
            out.append(_combo(cards, ComboType.PAIR, 1, r, assign))

    # ---- 炸弹：每个点数 × {3,4} 张（带王/不带王由缺口决定，§规则 4.2/6.3）----
    for r in range(NUM_RANKS):
        for size in (3, 4):
            g = _make_group(r, size, by_rank[r], jokers, 0)
            if g is not None:
                cards, assign, _ = g
                out.append(_combo(cards, ComboType.BOMB, size, r, assign))

    # ---- 顺子：所有窗口 [lo, hi]，长度 ≥4，最高到 A（rank 11），不含 2 ----
    for lo in range(MAX_STRAIGHT_RANK + 1):
        cards: list[int] = []
        assign: list[tuple[int, int]] = []
        cursor = 0
        for hi in range(lo, MAX_STRAIGHT_RANK + 1):
            if cnt[hi] >= 1:
                cards.append(by_rank[hi][0])
            elif cursor < nj:
                jid = jokers[cursor]
                cards.append(jid)
                assign.append((jid, hi))
                cursor += 1
            else:
                break  # 这一位既无普通牌也无可用王 → 该 lo 起的更长窗口都不可能
            length = hi - lo + 1
            if length >= 4:
                out.append(
                    _combo(list(cards), ComboType.STRAIGHT, length, hi, list(assign))
                )

    # ---- 连对：所有窗口 [lo, hi]，对数 ≥2，最高到对 A，不含对 2 ----
    for lo in range(MAX_STRAIGHT_RANK + 1):
        cards = []
        assign = []
        cursor = 0
        for hi in range(lo, MAX_STRAIGHT_RANK + 1):
            g = _make_group(hi, 2, by_rank[hi], jokers, cursor)
            if g is None:
                break
            pc, pa, cursor = g
            cards.extend(pc)
            assign.extend(pa)
            pairs = hi - lo + 1
            if pairs >= 2:
                out.append(
                    _combo(list(cards), ComboType.CONSEC_PAIRS, pairs, hi, list(assign))
                )

    return out


def legal_actions(hand: list[int], live_play: Combo | None) -> list[Action]:
    """某玩家在当前桌面下的合法动作集（§规则 7.1/7.2/7.3）。

    - 领出（live_play is None）：所有合法牌型均可，**PASS 非法**（领出不能过）。
    - 跟牌：所有能压过 live_play 的组合；非空则「能压必须压」，**不含 PASS**；
      为空则唯一合法动作是 PASS。强制含炸、无豁免（R2）。
    """
    all_combos = generate_all_combos(hand)
    if live_play is None:
        return [Action.play(c) for c in all_combos]
    beating = [c for c in all_combos if c.beats(live_play)]
    if beating:
        return [Action.play(c) for c in beating]
    return [Action.passing()]


def settle_round(bombs_played: list[tuple[int, Combo]], winner: int) -> list[int]:
    """本局结算（§规则 9 / R1）：全场炸弹分之和全归赢家，另两家 0。"""
    total = sum(combo.bomb_score for _, combo in bombs_played)
    score = [0, 0, 0]
    score[winner] = total
    return score
