"""命令行入口：独立运行后端做测试（PLAN「后端可独立运行」目标）。

uv run python -m engine human  [--seat N] [--seed S]    # 你 vs 2 bot，终端交互对局
uv run python -m engine play   [--seed S] [--verbose]   # 跑一整场 3 bot 对局
uv run python -m engine sim    [--matches N] [--seed S]  # 批量对局统计
uv run python -m engine bench  [--iters N]               # 合法动作生成性能基准
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Iterable
from random import Random, SystemRandom

from engine import bots, engine
from engine.cards import RANK_LABELS, card_rank, card_suit, is_joker
from engine.combos import Action, ActionKind, Combo
from engine.match import Match
from engine.rules import generate_all_combos, legal_actions
from engine.state import GameState


# ---- 彩色 / 花色渲染（仅展示层；数据/接口仍用 cards.card_label）----
_RESET = "\033[0m"
_SUIT_GLYPH = ["♠", "♥", "♣", "♦"]  # 黑桃 / 红桃 / 梅花 / 方块（按 Suit order）
_SUIT_COLOR = ["\033[1;97m", "\033[91m", "\033[92m", "\033[94m"]  # 白红绿蓝
_JOKER_COLOR = "\033[1;93m"
COLOR_ENABLED = True


def _c(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}" if COLOR_ENABLED else text


def _card(cid: int, jmap: dict[int, int] | None = None) -> str:
    """渲染一张牌：普通牌为点数+花色色块；王为 🃏，在牌型里附带代表的点数。"""
    if is_joker(cid):
        if jmap and cid in jmap:
            return _c(f"🃏{RANK_LABELS[jmap[cid]]}", _JOKER_COLOR)
        return _c("🃏", _JOKER_COLOR)
    suit = card_suit(cid)
    return _c(f"{RANK_LABELS[card_rank(cid)]}{_SUIT_GLYPH[suit]}", _SUIT_COLOR[suit])


def _cards(cids: Iterable[int], jmap: dict[int, int] | None = None) -> str:
    return " ".join(_card(c, jmap) for c in cids)


def _combo_cards(c: Combo) -> str:
    return _cards(c.cards, dict(c.joker_assignment))


def _resolve_seed(seed: int | None) -> int:
    """没传 --seed 时用系统熵随机起一局（引擎仍按此 seed 完全确定性）。"""
    return seed if seed is not None else SystemRandom().randrange(2**31)


def _seat_name(seat: int, human: int | None) -> str:
    """从 human 视角称呼座位：你 / 下家((你+1)%3) / 上家((你+2)%3)。

    human=None（全 bot 模式）时退回「座位N」。
    """
    if human is None:
        return f"座位{seat}"
    if seat == human:
        return "你"
    return "下家" if seat == (human + 1) % 3 else "上家"


def _fmt_action(player: int, action: Action, human: int | None = None) -> str:
    name = _seat_name(player, human)
    if action.kind is ActionKind.PASS:
        return f"  {name}: 过"
    c = action.combo
    assert c is not None
    return f"  {name}: {_combo_cards(c)}"


def _prompt_human(state: GameState, seat: int) -> Action:
    """列出该座位的合法动作让人选编号；含王牌型已自动指派好替代点数。"""
    legal = legal_actions(state.hands[seat], state.live_play)
    print(f"\n  你的手牌({len(state.hands[seat])}): {_cards(state.hands[seat])}")
    if state.live_play is not None:
        assert state.live_player is not None
        owner = _seat_name(state.live_player, seat)
        print(f"  生效牌({owner}): {_combo_cards(state.live_play)}")
    else:
        print("  你领出，自由出牌。")

    if len(legal) == 1 and legal[0].is_pass:
        print("  压不过 → 只能过牌（自动 PASS）。")
        return legal[0]
    if state.live_play is not None:
        print("  ※ 能压必须压：以下都是能压过的选择，没有「过」。")
    for i, a in enumerate(legal):
        body = "过牌 (PASS)" if a.is_pass else _combo_cards(a.combo)  # type: ignore[arg-type]
        print(f"    [{i:>2}] {body}")
    while True:
        raw = input("  选择编号 (q 退出): ").strip()
        if raw.lower() == "q":
            raise SystemExit("已退出。")
        if raw.isdigit() and 0 <= int(raw) < len(legal):
            return legal[int(raw)]
        print("  无效输入，重选。")


def cmd_human(args: argparse.Namespace) -> None:
    human = args.seat
    seed = _resolve_seed(args.seed)
    rng = Random(seed)
    total = [0, 0, 0]
    first_leader = None
    game_no = 0
    print(
        f"你是座位 {human}。出牌顺序：你 → 下家 → 上家 → 你（下家、上家都是 bot）。"
        f"先到 30 分赢整场。"
    )
    print(f"本场随机种子={seed}（加 --seed {seed} 可复现这一整场）")
    while max(total) < 30:
        game_no += 1
        seed = rng.randrange(2**31)
        state = GameState.new_game(seed, first_leader)
        leader = _seat_name(state.first_leader, human)
        print(f"\n========== 第 {game_no} 局（首家={leader}）==========")
        while not state.finished:
            seat = state.turn
            if seat == human:
                action = _prompt_human(state, seat)
                print(_fmt_action(seat, action, human))
            else:
                action = bots.choose_action(state, seat)
                print(_fmt_action(seat, action, human))
            state = engine.step(state, action).state
        assert state.winner is not None
        for p in range(3):
            total[p] += state.round_score[p]
        tag = "（你赢了！）" if state.winner == human else ""
        print(
            f"\n  → 本局赢家={_seat_name(state.winner, human)}{tag} "
            f"本局分={state.round_score} 累计={total}"
        )
        first_leader = state.winner
    winner = max(range(3), key=lambda p: total[p])
    verdict = (
        "你赢得整场！🎉"
        if winner == human
        else f"{_seat_name(winner, human)}赢得整场。"
    )
    print(f"\n========== 整场结束：{verdict} 累计分 {total} ==========")


def cmd_play(args: argparse.Namespace) -> None:
    policies = [bots.choose_action] * 3
    seed = _resolve_seed(args.seed)
    print(f"随机种子={seed}（加 --seed {seed} 可复现）")
    if args.verbose:
        _play_verbose(policies, seed)
    else:
        match = Match()
        winner = match.play(policies, seed)
        print(
            f"整场结束：座位 {winner} 获胜 | 累计分 {match.total_scores} "
            f"| 共 {len(match.games)} 局"
        )
        for i, g in enumerate(match.games):
            print(
                f"  第{i + 1}局: 赢家={g.winner} 本局分={g.round_score} "
                f"炸弹数={g.num_bombs} (seed={g.seed})"
            )


def _play_verbose(policies, master_seed: int) -> None:
    rng = Random(master_seed)
    total = [0, 0, 0]
    first_leader = None
    game_no = 0
    while max(total) < 30:
        game_no += 1
        seed = rng.randrange(2**31)
        state = GameState.new_game(seed, first_leader)
        print(f"\n=== 第 {game_no} 局 (seed={seed}, 首家=座位{state.first_leader}) ===")
        for p in range(3):
            print(f"  座位{p}手牌: {_cards(state.hands[p])}")
        while not state.finished:
            action = policies[state.turn](state, state.turn)
            print(_fmt_action(state.turn, action))
            state = engine.step(state, action).state
        assert state.winner is not None
        for p in range(3):
            total[p] += state.round_score[p]
        print(f"  → 赢家=座位{state.winner} 本局分={state.round_score} 累计={total}")
        first_leader = state.winner
    winner = max(range(3), key=lambda p: total[p])
    print(f"\n整场结束：座位 {winner} 获胜 | 累计分 {total}")


def cmd_sim(args: argparse.Namespace) -> None:
    policies = [bots.choose_action] * 3
    wins = [0, 0, 0]
    total_games = 0
    t0 = time.perf_counter()
    for m in range(args.matches):
        match = Match()
        winner = match.play(policies, args.seed + m)
        wins[winner] += 1
        total_games += len(match.games)
    dt = time.perf_counter() - t0
    print(
        f"{args.matches} 整场 / 共 {total_games} 局 用时 {dt:.3f}s "
        f"({total_games / dt:.0f} 局/s)"
    )
    print(f"整场胜场分布(座位0/1/2): {wins}")
    print(f"平均每场局数: {total_games / args.matches:.1f}")


def cmd_bench(args: argparse.Namespace) -> None:
    """对「生成所有可能情况」做性能基准：采样真实对局中的手牌状态后反复生成。"""
    rng = Random(123)
    samples: list[tuple[list[int], object]] = []
    policies = [bots.choose_action] * 3
    # 采样：跑若干局，记录每一步的 (手牌, 生效牌) 作为基准输入。
    for _ in range(50):
        seed = rng.randrange(2**31)
        state = GameState.new_game(seed, None)
        while not state.finished:
            samples.append((list(state.hands[state.turn]), state.live_play))
            action = policies[state.turn](state, state.turn)
            state = engine.step(state, action).state
    print(f"采样状态数: {len(samples)}（来自 50 局真实对局）")

    iters = args.iters
    t0 = time.perf_counter()
    n = 0
    for _ in range(iters):
        hand, live = samples[n % len(samples)]
        generate_all_combos(hand)
        n += 1
    dt = time.perf_counter() - t0
    print(
        f"generate_all_combos: {iters} 次 用时 {dt:.4f}s "
        f"→ {dt / iters * 1e6:.2f} µs/次 ({iters / dt:.0f} 次/s)"
    )

    t0 = time.perf_counter()
    for i in range(iters):
        hand, live = samples[i % len(samples)]
        legal_actions(hand, live)  # type: ignore[arg-type]
    dt = time.perf_counter() - t0
    print(
        f"legal_actions:       {iters} 次 用时 {dt:.4f}s "
        f"→ {dt / iters * 1e6:.2f} µs/次 ({iters / dt:.0f} 次/s)"
    )

    # 最坏情况：手牌张数最多、王最多的状态单独看一眼。
    worst = max(samples, key=lambda s: (len(s[0]), sum(c >= 52 for c in s[0])))
    combos = generate_all_combos(worst[0])
    print(f"采样中最大手牌生成牌型数: {len(combos)}（手牌 {len(worst[0])} 张）")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="engine", description="bizha 后端命令行")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_human = sub.add_parser("human", help="你坐一个座位 vs 2 bot，终端交互对局")
    p_human.add_argument("--seat", type=int, default=0, choices=[0, 1, 2])
    p_human.add_argument("--seed", type=int, default=None, help="不传则随机洗牌")
    p_human.set_defaults(func=cmd_human)

    p_play = sub.add_parser("play", help="跑一整场 3 bot 对局")
    p_play.add_argument("--seed", type=int, default=None, help="不传则随机洗牌")
    p_play.add_argument("--verbose", action="store_true", help="逐手打印")
    p_play.set_defaults(func=cmd_play)

    p_sim = sub.add_parser("sim", help="批量对局统计")
    p_sim.add_argument("--matches", type=int, default=200)
    p_sim.add_argument("--seed", type=int, default=1000)
    p_sim.set_defaults(func=cmd_sim)

    p_bench = sub.add_parser("bench", help="合法动作生成性能基准")
    p_bench.add_argument("--iters", type=int, default=200000)
    p_bench.set_defaults(func=cmd_bench)

    args = parser.parse_args(argv)
    global COLOR_ENABLED
    COLOR_ENABLED = sys.stdout.isatty() and not args.no_color
    args.func(args)


if __name__ == "__main__":
    main()
