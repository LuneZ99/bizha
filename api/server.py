"""FastAPI app：建局 / 视角查询 / 合法动作 / 提交动作 / WS 推送（PLAN §5.1）。

规则判定全部下沉到引擎；本层只做翻译、视角裁剪、bot 服务端 tick 与 WS 广播。
运行：uv run uvicorn api.server:app --reload
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.schemas import (
    ActionRequest,
    CreateGameRequest,
    GameView,
    LegalActionsResponse,
)
from api.sessions import SessionManager
from engine.match import NUM_PLAYERS


WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="bizha", description="3 人特殊扑克牌游戏后端")
manager = SessionManager()
_ws_clients: dict[str, set[WebSocket]] = {}


@app.exception_handler(KeyError)
async def _key_error(_req, exc: KeyError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def _value_error(_req, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.post("/games", response_model=GameView)
def create_game(req: CreateGameRequest) -> GameView:
    """建一整场。bot_seats 占满 3 座 = play 观战模式（亮全手牌）；否则 human 模式。"""
    session = manager.create(req.seed, req.bot_seats)
    human_seats = sorted(set(range(NUM_PLAYERS)) - session.bot_seats)
    if not human_seats:
        return session.view(0, reveal_all=True)
    return session.view(human_seats[0])


@app.get("/games/{game_id}", response_model=GameView)
def get_game(game_id: str, seat: int, reveal: bool = False) -> GameView:
    return manager.get(game_id).view(seat, reveal_all=reveal)


@app.get("/games/{game_id}/legal", response_model=LegalActionsResponse)
def get_legal(game_id: str, seat: int) -> LegalActionsResponse:
    return manager.get(game_id).legal(seat)


@app.post("/games/{game_id}/actions", response_model=GameView)
async def submit_action(game_id: str, req: ActionRequest) -> GameView:
    session = manager.get(game_id)
    events = session.submit(req)
    await _broadcast(game_id, events)
    return session.view(req.seat)


@app.post("/games/{game_id}/advance", response_model=GameView)
async def advance_game(game_id: str, seat: int = 0, reveal: bool = False) -> GameView:
    """play 观战模式逐手推进：跑一步 bot 动作，回当前视角。"""
    session = manager.get(game_id)
    events = session.advance_one()
    await _broadcast(game_id, events)
    return session.view(seat, reveal_all=reveal)


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


# 前端静态资源同源托管（须放在所有 API 路由之后，"/" 挂载会兜底其余路径）。
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
