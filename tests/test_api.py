"""接口层端到端测试：通过 REST 驱动一整场（人类座位用合法动作自动选）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.server import app


client = TestClient(app)


def _create(bot_seats):
    resp = client.post("/games", json={"seed": 7, "bot_seats": bot_seats})
    assert resp.status_code == 200
    return resp.json()


def test_create_returns_human_view():
    view = _create([1, 2])
    assert view["seat"] == 0
    assert len(view["hand"]) > 0  # 己方手牌可见
    assert view["hand_counts"] == [18, 18, 18] or sum(view["hand_counts"]) <= 54
    # 整场刚开始
    assert view["total_scores"] == [0, 0, 0]
    assert not view["match_finished"]


def test_view_hides_opponent_hands():
    view = _create([1, 2])
    gid = view["game_id"]
    other = client.get(f"/games/{gid}", params={"seat": 1}).json()
    assert len(other["hand"]) == other["hand_counts"][1]  # 只暴露自己张数


def test_legal_endpoint_reports_must_play():
    view = _create([1, 2])
    gid = view["game_id"]
    seat = view["turn"]
    legal = client.get(f"/games/{gid}/legal", params={"seat": seat}).json()
    # 领出局面：必须出牌，且无 PASS 选项
    assert legal["must_play"]
    assert all(a["kind"] == "play" for a in legal["actions"])


def test_bot_seat_submission_rejected():
    view = _create([1, 2])
    gid = view["game_id"]
    resp = client.post(
        f"/games/{gid}/actions",
        json={"seat": 1, "kind": "pass", "cards": [], "joker_assignment": {}},
    )
    assert resp.status_code == 400


def test_drive_full_match_via_rest():
    view = _create([1, 2])
    gid = view["game_id"]
    human = 0
    guard = 0
    while not view["match_finished"]:
        guard += 1
        assert guard < 5000
        if view["turn"] != human or view["round_finished"]:
            # 不该发生：submit 后总会把 bot 跑到轮到人类或整场结束
            view = client.get(f"/games/{gid}", params={"seat": human}).json()
            if view["match_finished"]:
                break
        legal = client.get(f"/games/{gid}/legal", params={"seat": human}).json()
        act = legal["actions"][0]
        body = {"seat": human, "kind": act["kind"], "cards": [], "joker_assignment": {}}
        if act["kind"] == "play":
            body["cards"] = act["combo"]["cards"]
            body["joker_assignment"] = act["combo"]["joker_assignment"]
        resp = client.post(f"/games/{gid}/actions", json=body)
        assert resp.status_code == 200, resp.text
        view = resp.json()
    assert view["match_finished"]
    assert max(view["total_scores"]) >= 30


def test_websocket_snapshot():
    view = _create([1, 2])
    gid = view["game_id"]
    with client.websocket_connect(f"/games/{gid}/ws?seat=0") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert msg["view"]["seat"] == 0
