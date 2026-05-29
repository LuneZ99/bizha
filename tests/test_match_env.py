"""整场编排 + 环境壳单测（PLAN §4.5/4.6）。"""

from __future__ import annotations

import numpy as np

from engine import bots, env
from engine.cards import SPADE_THREE_ID, deal, spade_three_holder
from engine.match import TARGET_SCORE, Match, play_single_game
from engine.rules import legal_actions
from engine.state import GameState


def test_first_leader_is_spade_three_holder():
    state = GameState.new_game(seed=999)
    assert state.first_leader == spade_three_holder(state.hands)
    assert SPADE_THREE_ID in state.hands[state.first_leader]


def test_match_reaches_target_and_winner_has_max():
    policies = [bots.choose_action] * 3
    match = Match()
    winner = match.play(policies, master_seed=2024)
    assert max(match.total_scores) >= TARGET_SCORE
    assert match.total_scores[winner] == max(match.total_scores)
    # 首家链：每局首家 = 上一局赢家
    for i in range(1, len(match.games)):
        assert match.games[i].first_leader == match.games[i - 1].winner


def test_single_game_winner_consistent():
    policies = [bots.choose_action] * 3
    state = play_single_game(policies, seed=555, first_leader=None)
    assert state.finished and state.winner is not None
    assert state.first_leader == spade_three_holder(deal(555))


# ---------------- 环境壳 ----------------


def test_catalog_indices_unique():
    assert len(env.ACTION_CATALOG) == len(set(env.ACTION_CATALOG))
    assert env.PASS_INDEX == len(env.ACTION_CATALOG)


def test_mask_matches_legal_actions():
    state = GameState.new_game(seed=321)
    mask = env.legal_action_mask(state, state.turn)
    legal = legal_actions(state.hands[state.turn], state.live_play)
    assert int(mask.sum()) == len(legal)


def test_decode_roundtrips_every_legal_action():
    # 领出局面：每个 mask 命中的下标都能物化回合法 Combo
    state = GameState.new_game(seed=321)
    mask = env.legal_action_mask(state, state.turn)
    for idx in np.nonzero(mask)[0]:
        action = env.decode_action(state, state.turn, int(idx))
        assert action.combo is not None
        assert env.combo_key(action.combo) == env.ACTION_CATALOG[int(idx)]


def test_env_plays_full_game_with_masked_random():
    rng = np.random.default_rng(11)
    e = env.GameEnv()
    obs = e.reset(seed=7777)
    done = False
    steps = 0
    while not done:
        legal_idx = np.nonzero(obs["legal_mask"])[0]
        action_index = int(rng.choice(legal_idx))
        obs, reward, done, _ = e.step(action_index)
        steps += 1
        assert steps < 1000
    assert e.state is not None and e.state.winner is not None
    assert sum(reward) >= 0


def test_observation_hides_opponent_hands():
    state = GameState.new_game(seed=4242)
    obs = env.encode_observation(state, player=0)
    # 观测里只有己方 18 张手牌的 multi-hot，没有他人具体牌的字段
    assert int(obs["hand"].sum()) == len(state.hands[0])
    assert obs["hand_counts"].shape == (3,)
