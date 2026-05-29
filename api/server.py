"""FastAPI app：建局 / 视角查询 / 合法动作 / 提交动作 / WS 推送（PLAN §5.1）。

规则判定全部下沉到引擎；本层只做翻译、视角裁剪、bot 服务端 tick 与 WS 广播。
运行：uv run uvicorn api.server:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from api.schemas import (
    ActionRequest,
    CreateGameRequest,
    GameView,
    LegalActionsResponse,
)
from api.sessions import SessionManager


app = FastAPI(title="bizha", description="3 人特殊扑克牌游戏后端")
manager = SessionManager()
_ws_clients: dict[str, set[WebSocket]] = {}


@app.exception_handler(KeyError)
async def _key_error(_req, exc: KeyError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def _value_error(_req, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _default_human_seat(bot_seats: set[int]) -> int:
    for seat in range(3):
        if seat not in bot_seats:
            return seat
    raise HTTPException(status_code=400, detail="至少要留一个人类座位")


@app.post("/games", response_model=GameView)
def create_game(req: CreateGameRequest) -> GameView:
    session = manager.create(req.seed, req.bot_seats)
    human_seat = _default_human_seat(session.bot_seats)
    return session.view(human_seat)


@app.get("/games/{game_id}", response_model=GameView)
def get_game(game_id: str, seat: int) -> GameView:
    return manager.get(game_id).view(seat)


@app.get("/games/{game_id}/legal", response_model=LegalActionsResponse)
def get_legal(game_id: str, seat: int) -> LegalActionsResponse:
    return manager.get(game_id).legal(seat)


@app.post("/games/{game_id}/actions", response_model=GameView)
async def submit_action(game_id: str, req: ActionRequest) -> GameView:
    session = manager.get(game_id)
    events = session.submit(req)
    await _broadcast(game_id, events)
    return session.view(req.seat)


async def _broadcast(game_id: str, events: list[dict]) -> None:
    clients = _ws_clients.get(game_id, set())
    dead: set[WebSocket] = set()
    for ws in clients:
        try:
            for event in events:
                await ws.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            dead.add(ws)
    clients -= dead


@app.websocket("/games/{game_id}/ws")
async def game_ws(websocket: WebSocket, game_id: str, seat: int) -> None:
    session = manager.get(game_id)
    await websocket.accept()
    _ws_clients.setdefault(game_id, set()).add(websocket)
    await websocket.send_json(
        {"type": "snapshot", "view": session.view(seat).model_dump()}
    )
    try:
        while True:
            await websocket.receive_text()  # 保持连接；本阶段动作走 REST
    except WebSocketDisconnect:
        _ws_clients.get(game_id, set()).discard(websocket)
