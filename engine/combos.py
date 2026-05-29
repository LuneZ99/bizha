"""牌型识别（含王替代解析）与比较 —— §规则 4、5、6。

设计要点（与 workspace 规范一致：强类型 / fail hard / 不吞异常）：
  - `Combo.parse(cards, joker_assignment)`：给定一手牌 + 每张王代表的点数，
    判定它构成哪种合法牌型；非法直接 `raise ValueError`，绝不返回 None。
  - 王替代由出牌人显式指定（§规则 4.1），引擎不猜测：`joker_assignment`
    把每个王的 card_id 映射到它代表的 rank order。
  - `beats(other)`：实现 §规则 6 全部比较（炸弹三层大小序、炸压非炸）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from engine.cards import (
    MAX_STRAIGHT_RANK,
    Rank,
    card_rank,
    is_joker,
)


class ComboType(Enum):
    SINGLE = "single"
    PAIR = "pair"
    STRAIGHT = "straight"
    CONSEC_PAIRS = "consec_pairs"
    BOMB = "bomb"


class ActionKind(Enum):
    PLAY = "play"
    PASS = "pass"


@dataclass(frozen=True)
class Combo:
    """一次出牌。frozen → 可哈希、可作为字典键、可安全深拷贝（RL 友好）。

    - `cards`：参与的物理 card_id（升序），唯一确定消耗了哪些牌。
    - `combo_type` / `length` / `rank_key`：比较所需的归一化信息。
        * length：SINGLE/PAIR=1；STRAIGHT=张数；CONSEC_PAIRS=对数；BOMB=张数。
        * rank_key：用于同型比较的点数（顺子/连对取最高张点数）。
    - `joker_assignment`：每个王 card_id → 它代表的 rank order（§规则 4.1）。
    - `uses_joker`：是否含王（影响炸弹强弱与积分，§规则 6.3 / §9）。
    """

    cards: tuple[int, ...]
    combo_type: ComboType
    length: int
    rank_key: int
    uses_joker: bool
    joker_assignment: tuple[tuple[int, int], ...]  # (joker_card_id, rank) 升序

    def beats(self, other: Combo) -> bool:
        """self 是否严格压过 other（§规则 6）。点数相等不算压（须严格更大）。"""
        self_bomb = self.combo_type is ComboType.BOMB
        other_bomb = other.combo_type is ComboType.BOMB
        if self_bomb and not other_bomb:
            return True
        if other_bomb and not self_bomb:
            return False
        if self_bomb and other_bomb:
            return self._bomb_key() > other._bomb_key()
        # 非炸：仅「同牌型 + 同长度」可比，比点数（§规则 6.1/6.2）。
        if self.combo_type is not other.combo_type or self.length != other.length:
            return False
        return self.rank_key > other.rank_key

    def _bomb_key(self) -> tuple[int, int, int]:
        """炸弹三层大小序（§规则 6.3）：① 张数 → ② 是否带王 → ③ 点数。

        不带王记 1、带王记 0，使「不带王 > 带王」；元组字典序即整体大小序。
        """
        return (len(self.cards), 0 if self.uses_joker else 1, self.rank_key)

    @property
    def bomb_score(self) -> int:
        """该炸弹的积分（§规则 9）：带王 1 分，不带王 3 分。非炸调用即 bug。"""
        if self.combo_type is not ComboType.BOMB:
            raise ValueError("只有炸弹才有积分")
        return 1 if self.uses_joker else 3


@dataclass(frozen=True)
class Action:
    """一个动作：PLAY(combo) 或 PASS（§规则 7）。frozen → 可哈希、可比较。"""

    kind: ActionKind
    combo: Combo | None = None

    @staticmethod
    def play(combo: Combo) -> Action:
        return Action(ActionKind.PLAY, combo)

    @staticmethod
    def passing() -> Action:
        return Action(ActionKind.PASS, None)

    @property
    def is_pass(self) -> bool:
        return self.kind is ActionKind.PASS


def _effective_ranks(cards: tuple[int, ...], jmap: dict[int, int]) -> list[int]:
    """把每张牌映射成「有效点数」：普通牌取本身点数，王取声明代表的点数。"""
    out: list[int] = []
    for cid in cards:
        if is_joker(cid):
            if cid not in jmap:
                raise ValueError(f"含王动作必须声明王 id={cid} 代表的点数（§规则 4.1）")
            out.append(jmap[cid])
        else:
            out.append(card_rank(cid))
    return out


def parse(cards: tuple[int, ...], joker_assignment: dict[int, int]) -> Combo:
    """识别牌型；非法组合直接抛异常（fail hard，PLAN §4.1）。

    `joker_assignment`：每个王 card_id → 代表的 rank order（0–12）。普通牌不得出现。
    """
    cards = tuple(sorted(cards))
    if not cards:
        raise ValueError("空出牌不是合法牌型")

    jokers = tuple(cid for cid in cards if is_joker(cid))
    for cid in joker_assignment:
        if not is_joker(cid) or cid not in cards:
            raise ValueError(f"joker_assignment 的 key {cid} 不是本手牌里的王")
    for cid in jokers:
        if cid not in joker_assignment:
            raise ValueError(f"王 id={cid} 缺少替代声明（§规则 4.1）")
        r = joker_assignment[cid]
        if not (0 <= r <= Rank.TWO.value):
            raise ValueError(f"王替代点数 {r} 越界")

    uses_joker = bool(jokers)
    jassign = tuple(sorted((cid, joker_assignment[cid]) for cid in jokers))
    eff = _effective_ranks(cards, dict(jassign))
    n = len(cards)

    # ---- SINGLE ----
    if n == 1:
        r = eff[0]
        # 单张王最高只能当 2（§规则 4.2）；普通牌天然 ≤ 2。
        if r > Rank.TWO.value:
            raise ValueError("单牌点数越界")
        return Combo(cards, ComboType.SINGLE, 1, r, uses_joker, jassign)

    # ---- PAIR ----
    if n == 2:
        if eff[0] != eff[1]:
            raise ValueError("两张牌点数不同，不是对子")
        return Combo(cards, ComboType.PAIR, 1, eff[0], uses_joker, jassign)

    # ---- BOMB（3 或 4 张同点数）----
    if len(set(eff)) == 1 and n in (3, 4):
        # §规则 4.2：炸弹最多 4 张，王也不能凑出 5 张以上 —— n>4 已落到下面的非法分支。
        return Combo(cards, ComboType.BOMB, n, eff[0], uses_joker, jassign)

    # ---- STRAIGHT（≥4 张连续单牌，最高到 A，不含 2，不回绕）----
    if n >= 4 and len(set(eff)) == n:
        lo, hi = min(eff), max(eff)
        if hi <= MAX_STRAIGHT_RANK and hi - lo == n - 1:
            return Combo(cards, ComboType.STRAIGHT, n, hi, uses_joker, jassign)

    # ---- CONSEC_PAIRS（≥2 对连续对子，最高到对 A，不含对 2）----
    if n >= 4 and n % 2 == 0:
        eff_sorted = sorted(eff)
        pairs_ok = all(
            eff_sorted[2 * i] == eff_sorted[2 * i + 1] for i in range(n // 2)
        )
        rank_seq = [eff_sorted[2 * i] for i in range(n // 2)]
        if (
            pairs_ok
            and len(set(rank_seq)) == n // 2
            and max(rank_seq) <= MAX_STRAIGHT_RANK
            and rank_seq[-1] - rank_seq[0] == n // 2 - 1
        ):
            return Combo(
                cards, ComboType.CONSEC_PAIRS, n // 2, rank_seq[-1], uses_joker, jassign
            )

    raise ValueError(f"牌 {cards}（王替代 {jassign}）不构成任何合法牌型（§规则 5）")
