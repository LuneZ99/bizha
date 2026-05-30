# 项目计划（bizha）

> 一个 3 人特殊扑克牌游戏的实现计划。规则见 [`rules.md`](./rules.md)，本文件只讲**怎么实现**。
> 后端 Python，分「引擎」与「接口」两层；前端用**原生 JS + 自绘 CSS 卡面**做牌面渲染（初版计划用 deck-of-cards，已改，见 §6）。
> **引擎从一开始就要设计成适合后续做强化学习（RL）训练打牌 AI**——但 RL 训练本身现在不做，只把接口和数据结构留好。

---

## 1. 目标与范围

### 1.1 本阶段做什么

- 一个**纯逻辑、可独立运行、确定性**的游戏引擎：**单局**（发牌 → 出牌 → 出完结算炸弹分）+ **整场编排**（多局累计，先到 **30 分**者赢得整场；每局赢家成为下一局首家）。
- 一个把引擎包成 **Gym 风格 `step()`** 的环境壳（为 RL 预留，但现在不训练）。
- 一个 **HTTP/WebSocket 接口层**，让前端（或脚本 bot）能创建对局、查询己方视角、提交动作。
- 一个**前端 MVP**：**原生 JS + 自绘卡面**，两种模式——**human**（人类 vs 2 bot，看牌/选牌/出牌/过牌）与 **play**（3 bot 观战，逐手/自动播放），都能看本局炸弹积分与**整场累计分（到 30 结束）**。
- 引擎核心的**单元测试**：牌型识别 / 比较（含炸弹大小序）/ 合法动作生成 / 「能压必须压」/ 积分结算 / 王替代边界。
  - 注：这一条**有意覆盖** workspace「除非主动要求不加单测」的默认——本引擎规则复杂且是 RL 正确性的根基，已确认要写。

### 1.2 本阶段不做什么

- **不做 RL 训练**（不写策略网络、不跑 self-play 训练循环）。只保证引擎/环境的接口对 RL 友好。
- 不做账号、对战匹配、持久化排行榜等运营功能。
- 不做联机多人房间（**只做单机：human=1 人 + 2 bot，play=3 bot 观战**；联机留到接口层成熟后）。
- **前端不用 React/Vue**：原生 JS 直接操作 DOM，自绘 CSS 卡面，无构建步骤。

---

## 2. 总体架构

三层，自下而上，依赖单向（上层依赖下层，下层绝不反向依赖）：

```
┌─────────────────────────────────────────────┐
│  web/   前端（原生 JS + 自绘卡面 + 交互）         │  ← 浏览器
└───────────────▲─────────────────────────────┘
                │  REST + WebSocket（JSON）
┌───────────────┴─────────────────────────────┐
│  api/   接口层（FastAPI）                        │
│   - 对局生命周期管理（内存态）                     │
│   - 「按玩家视角」序列化（隐藏他人手牌）              │
│   - 把前端动作翻译成引擎 Action                    │
└───────────────▲─────────────────────────────┘
                │  纯 Python 调用（无 I/O）
┌───────────────┴─────────────────────────────┐
│  engine/   引擎（纯逻辑，确定性，RL-ready）         │
│   - 牌 / 牌型 / 状态 数据模型                      │
│   - 牌型识别 + 比较                                │
│   - 合法动作生成（含「能压必须压」约束）             │
│   - 状态机推进 step() + 积分结算                   │
│   - GameEnv：Gym 风格观测/动作编码（给 RL）         │
└──────────────────────────────────────────────┘
```

**关键边界**：引擎层**不碰任何 I/O、不依赖 FastAPI/pydantic 的网络模型、不知道前端存在**。这样引擎才能被 RL 训练循环以极高频率、纯内存、可向量化地调用。

---

## 3. 目录结构（建议）

```
bizha/
├── rules.md                  # 规则（真相来源）
├── PLAN.md                   # 本文件
├── pyproject.toml            # uv 管理；engine 纯逻辑，api/dev 拆 optional extras
├── uv.lock                   # 锁定依赖（提交进仓库，保证可复现）
├── .python-version           # 固定 3.12
├── .pre-commit-config.yaml   # ruff / pycodestyle / pyright 钩子
├── engine/                   # 含 __init__.py（与 api / tests 同为 Python 包）
│   ├── cards.py              # Card / Rank / Suit / Deck，54 张牌定义
│   ├── combos.py             # Combo 牌型识别、王替代解析、比较 + Action
│   ├── state.py              # GameState + StepResult：手牌/当前轮/积分/历史
│   ├── rules.py              # 合法动作生成 + 「能压必须压」 + 结算
│   ├── engine.py             # step()：单局推进 / 终局判定（无 GameEngine 类，纯函数）
│   ├── match.py              # Match：多局编排——累计分 / 首家链 / 到 30 分判定
│   ├── env.py                # GameEnv：Gym 风格观测/动作编码（RL 入口）
│   ├── bots.py               # SimpleBot：choose_action(state, player)（基线 AI，§5.3）
│   ├── cli.py                # 命令行 human/play/sim/bench（后端独立可跑）
│   └── __main__.py           # `python -m engine ...` 入口
├── api/
│   ├── server.py             # FastAPI app + 静态资源挂载（web/ 同源托管）
│   ├── schemas.py            # pydantic 网络模型（与 engine 解耦）
│   ├── views.py              # GameState → 按玩家视角的 JSON
│   └── sessions.py           # 内存对局管理 + bot 服务端 tick
├── web/                      # 原生 JS，无构建步骤、无 CDN、自包含
│   ├── index.html           # 开始页（选模式/种子）+ 牌桌 + 记分板 + 弹窗
│   ├── styles.css           # 牌桌 / 卡面 / 弹窗样式
│   ├── cards.js             # card id↔牌面映射 + 自绘 54 张卡面（含两张王）
│   └── app.js               # human / play 两模式逻辑 + REST 调用 + 渲染
└── tests/                    # 引擎单测 + API 端到端：牌型/比较/合法动作/强制出牌/结算/王替代/接口
```

---

## 4. 引擎设计（核心，RL 友好）

### 4.1 数据模型

遵循 workspace 规范：**强类型、用枚举/明确结构表达，禁止弱类型兜底；未知值 fail hard**。

- **`Suit`**：枚举 `SPADE/HEART/CLUB/DIAMOND`，外加王无花色。
- **`Rank`**：枚举，承载**单牌大小序** `3<4<…<A<2`；提供 `order: int` 便于比较。王不属于普通 Rank。
- **`Card`**：`(rank, suit)` 或 `JOKER`（大小王不区分，§规则 2.1）。54 张在 `Deck` 里一次性定义。每张牌有稳定的 **id（0–53）**，用于 RL 编码与前端映射。
- **`ComboType`**：枚举 `SINGLE / PAIR / STRAIGHT / CONSEC_PAIRS / BOMB`。
- **`Combo`（一次出牌）**：
  - 组成的具体 `Card` 列表；
  - `combo_type`、`length`（顺子张数 / 连对的对数）、`rank_key`（用于同型比较的点数）；
  - **`joker_assignment`**：每张王**被指定代表的牌**（§规则 4.1，王替代由出牌人指定，歧义也由出牌人指定）。引擎只接收**已声明**的指派，不自行猜测。
  - `uses_joker: bool`（影响炸弹强弱与积分）。
  - 一个 `beats(other) -> bool`：实现 §规则 6 的全部比较（含炸弹三层大小序、炸压非炸）。
- **`Action`**：`PLAY(combo)` 或 `PASS`。

牌型识别 `Combo.parse(cards, joker_assignment)`：给定一组牌 + 王的指派，判定它是否构成某个合法牌型并返回 `Combo`；非法则**抛异常**（fail hard，不返回 None）。

### 4.2 状态 `GameState`

单一可序列化的真相状态，包含：

- `hands: [list[Card] × 3]`（**完整信息**；对外暴露时再按视角裁剪，见 §6.2）。
- `turn: int`（当前该谁出牌）。
- `leader: int`（本轮领出者）。
- `live_play: Combo | None` + `live_player: int`（桌面生效牌及其打出者；`None` 表示新一轮自由领出）。
- `passed_since_live: int`（自生效牌以来连续过牌数；达到 2 即重新领出）。
- `winner: int | None`、`finished: bool`。
- `bombs_played: list[(player, Combo)]`（用于积分结算，§规则 9）。
- `round_score: [int × 3]`（**本局**结算：赢家 = 本局全场炸弹分之和，另两家 0，按 R1）。
- `first_leader: int`（本局首家；由 `Match` 注入——第 1 局为黑桃 3 持有者，之后为上一局赢家）。
- `history: list[(player, Action)]`（完整出牌历史，供前端回放与 RL 观测）。
- `rng_seed`（确定性发牌，便于复现）。

> `GameState` 只描述**一局**。多局累计、首家链、到 30 分结束由 §4.6 的 `Match` 负责。对 RL：默认**一局 = 一个 episode**，整场编排是可选外层（需要长程信用分配时再把整场当更长 episode）。

### 4.3 合法动作生成（关键）

`legal_actions(state, player) -> list[Action]`：

1. **领出**（`live_play is None`）：枚举该玩家手牌能组成的**所有**合法牌型（所有单/对/顺/连对/炸 + 所有合法王指派），全部可选；`PASS` **非法**（领出不能过）。
2. **跟牌**（有 `live_play`）：枚举所有能 `beats(live_play)` 的组合。
   - 按 §规则 7.3「**能压必须压**」：若该集合**非空**，则**不包含 `PASS`**（强制出牌，只能在能压的组合里选）；若为空，则**唯一合法动作是 `PASS`**。
   - 强制**含炸、无豁免**（rules.md R2）：用炸压非炸、用更大的炸压炸（含 4 张压 3 张）、带王炸——全部计入「能压必须压」，**不做开关**。
3. 王的指派枚举要去重（同样的牌面 + 同样的有效牌型只保留规范形式），避免动作空间因王的等价指派而爆炸。

### 4.4 推进 `step`

`engine.step(action) -> StepResult`：

- 校验 `action` 属于 `legal_actions`（否则 **抛异常**，不容忍非法动作）。
- 应用：从手牌移除打出的牌、更新 `live_play`、过牌计数、轮转 `turn`；连续两过则重置生效牌并把领出权给 `live_player`。
- 出炸时记入 `bombs_played`。
- 判定是否有人出完 → `winner`、`finished`、结算积分（§规则 9，归属按 R1：本局全场炸弹分归赢家）。
- 返回 `(next_state, reward_per_player, done, info)`。

### 4.5 RL 友好性（现在只留接口，不训练）

`env.py` 把引擎包成 Gym 风格：

- **观测（per-player，信息不完全）**：己方手牌（multi-hot over 54）、当前生效牌编码、各家**剩余张数**、本轮领出者/座位相对位、已出炸弹计数、历史摘要、合法动作 mask。**绝不泄露他人具体手牌**。
- **动作空间**：对「所有可能 Combo」建一个**固定枚举目录**（canonical catalog），动作 = 目录下标 + `PASS`；每步配一个 **legal-action mask**。固定目录保证策略网络输出维度稳定。
- **`reset(seed)` / `step(action_index)`**：确定性（发牌用传入 seed；引擎内**禁用** `Date.now()/random()` 式隐藏随机，所有随机走显式 RNG）。
- **reward**：默认稀疏——终局时按 §规则 9 + R1 口径给分；预留 shaping 钩子（如打炸即时奖励），但不写死。
- **自对弈友好**：状态纯内存、可深拷贝、可从任意 `GameState` 续跑；为后续向量化（batch 多局并行）保持无全局可变状态。

> 设计准则：**引擎是确定性纯函数式状态机**——同一 `(state, action)` 永远得到同一 `next_state`。这是 RL 可复现与可向量化的前提。

### 4.6 整场编排 `Match`（多局到 30 分）

`match.py` 在单局引擎之上做薄薄的多局编排：

- 持有三人**累计分** `total_scores: [int × 3]`、已打局数、每局结果历史。
- **首家链**（rules.md §3）：第 1 局首家 = **黑桃 3 持有者**；之后每局首家 = **上一局赢家**。
- 每局用 `GameEngine` 跑完 → 取本局赢家与 `round_score` → 累加进 `total_scores`，把赢家设为下一局首家、重新随机发牌开下一局。
- **整场结束**：任一玩家 `total_scores >= 30` 即整场结束，该玩家为**整场赢家**。
- 对 RL：`Match` 是**可选外层**，默认按一局一 episode 训练，不污染单局引擎的纯函数性。

---

## 5. 接口层设计（FastAPI）

与 workspace 技术栈一致（FastAPI + pydantic）。接口层**只做翻译与视角裁剪**，规则判定全部下沉到引擎。

### 5.1 端点（草案）

| 方法 | 路径 | 作用 |
|------|------|------|
| `POST` | `/games` | 新建一**整场**（到 30 分、含多局；带 `seed` + `bot_seats`），返回初始视角。`bot_seats=[1,2]` → human 模式；`bot_seats=[0,1,2]` 占满 3 座 → play 观战模式（返回 `all_hands` 全亮、不预跑整场） |
| `GET` | `/games/{id}?seat=N&reveal=bool` | 取第 N 座视角（`reveal=true` 亮三家手牌，观战用；默认只暴露他人张数） |
| `GET` | `/games/{id}/legal?seat=N` | 取该座当前合法动作（含「能压必须压」结果，便于前端高亮/禁过） |
| `POST` | `/games/{id}/actions` | 提交人类动作 `{seat, kind, cards, joker_assignment}`，应用后服务端把 bot 跑到下一个人类轮次 |
| `POST` | `/games/{id}/advance?seat=N&reveal=bool` | **play 观战模式**逐手推进：跑一步 bot 动作并回视角（供前端「单步 / 自动播放」做动画；当前轮非 bot 则报错） |
| `WS` | `/games/{id}/ws?seat=N` | 连接即推一次 `snapshot`；保活连接（本阶段动作走 REST，广播事件预留） |

### 5.2 设计要点

- **视角裁剪**：`views.py` 把 `GameState` 转成「己方看得到的信息」；他人手牌只暴露**张数**，绝不暴露具体牌（与 RL 观测同源逻辑，复用一套裁剪）。
- **王指派随动作上传**：前端出含王组合时，必须带上「每张王代表什么」（§规则 4.1）。歧义由前端让玩家选定后上传。
- **强制出牌在服务端兜底**：即便前端没禁好「过」，服务端 `legal_actions` 也会拒绝非法 `PASS`（**抛异常**，不静默纠正）。
- **bot 行动**：本阶段 bot（简单 Bot，实现在 `engine/bots.py`，见 §5.3）在服务端 tick；后续可替换为 RL policy，无需改协议。
  - **human 模式**：人类 `submit` 后 `_run_bots` 把 bot 连跑到下一个人类轮次（或整场结束）。
  - **play 观战模式**：建局时**不**预跑（否则 `_run_bots` 一口气把整场算完，没法做动画），改由前端反复打 `/advance` 逐手推进。
- **对局态**：先用 `sessions.py` 内存管理；持久化（如需）后置。
- **静态资源**：`server.py` 用 `StaticFiles` 把 `web/` 挂在 `/`（须放在所有 API 路由之后），前端与 API 同源，免 CORS。
- **多局编排**：一个 `game_id` = 一整场（到 30 分）。某局出完后服务端结算 → 累计分 → 以上一局赢家为下一局首家 → 重新发牌开下一局，并经 WS 推「新局开始」；累计到 30 即推「整场结束」。
- 序列化用前后端共用的 card id（0–53）约定（见 §6.1），前端按 id 自绘卡面。

### 5.3 简单 Bot（Simple Bot，本阶段基线 AI）

实现在 `engine/bots.py`（不在 api 层；策略函数 `choose_action(state, player) -> Action`，CLI 与 API 共用）。逻辑刻意简单，**复用引擎的 `legal_actions` / `Combo`**，不另写规则：

- **候选枚举**：每当**自己手牌发生变化**（局初发牌、自己出牌后）就重新列出当前手牌能组成的所有合法牌型（顺子 / 连对 / 单 / 对 / 炸 等）。
- **出牌偏好**（领出「主动」与跟牌「被动」**同一套**）：
  1. **优先甩最长的连张**：能出最长的顺子 / 最长的连对就先出，尽快把长链处理掉。
  2. **出单 / 出对时尽量不拆长链**：选不破坏已有长顺子 / 长连对的单牌、对子；**只有被迫**（没有别的合法选择）时才拆。
  3. **炸弹保守**：**还能出别的就绝不主动炸**；仅当规则**强制必须炸**（R2：唯一能压手段是炸 / 必须用更大炸压炸）时才炸，并按规则挑合适的炸。
- **强制约束**：跟牌时若 `legal_actions` 中没有 `PASS`（即「能压必须压」生效），Bot 就在合法集合里按上述偏好挑一手；只有合法集合仅含 `PASS` 时才过。
- **可替换**：简单 Bot 只是个吃 `(observation, legal_actions)` 出 `action` 的策略函数；将来用 RL policy 直接替换它，协议与对局流程不变。

---

## 6. 前端设计（原生 JS + 自绘卡面）

> **与初版计划的偏差（已落地）**：原计划用 [deck-of-cards](https://github.com/deck-of-cards/deck-of-cards) 库。实际改为**自绘 CSS 卡面**——该库不含大小王、依赖 CDN/DOM 动画，对「三人跟牌 + 选牌 + 王指派」这套交互集成更别扭；自绘方案离线自包含、无构建步骤，且天然解决王的渲染。功能目标不变；若日后想要发牌动画再切回库。

### 6.1 卡面与 id 映射（`web/cards.js`）

- 自绘 54 张卡面：普通牌（点数 + 花色色块）+ **两张王**（紫色 🃏，含王牌型在牌面角标出「代表的点数」如 `=A`）。
- 前后端共用一套 **card id（0–53）↔ 牌面** 映射（普通牌 `id = rank_order*4 + suit_order`；王 52/53），与 `engine/cards.py` 完全一致，避免两边各自约定。
- 暴露 `cardElement(id, opts)`（`opts.faceDown` 背面、`opts.assignedRank` 王角标）与 `comboDescribe(combo)`（把 ComboView 描述成中文短语）。

### 6.2 两种模式（`web/app.js`）

- **human（人机对战）**：`bot_seats=[1,2]`，你坐 0 号位 vs 2 bot。
- **play（观战）**：`bot_seats=[0,1,2]`，3 bot 自动对局，「单步 / 自动播放 / 间隔滑块」逐手推进（打 `/advance`），全程亮三家手牌。
- 开始页选模式 + 可选随机种子（留空则前端随机生成）。

### 6.3 UI 布局（MVP）

- 底部：**自己**的手牌，human 模式可点选；选中后「出牌 / 过牌 / 清空选择」按钮可用。
- 上方两侧：两个对手 —— human 模式显示**背面牌 + 剩余张数**；play 模式亮出正面手牌。
- 中央：当前**生效牌**（live play）+ 打出者 + 牌型描述；新生效牌有 `pop` 入场动画；领出时提示「自由出牌」。
- 顶栏记分板：三人**整场累计分（/30）**、本局已出炸弹数、第几局、首家、轮到谁；当前出牌座位高亮。
- 底部日志：本局逐手出牌 / 过牌记录。

### 6.4 交互要点

- **合法动作匹配**：选牌后用后端 `/legal` 返回的合法动作集做匹配（**不在前端重写规则**）；选中牌集合恰好等于某合法 combo 的 `cards` 才允许出。
- **「能压必须压」体验**：合法集合无 PASS（`must_play`）时**禁用「过」按钮**并红字提示「本轮必须出牌」；只有合法集合仅含 PASS 时才允许过（§规则 7.3）。
- **含王歧义**：选中的牌集合可能对应多个合法 combo（如单张王可当 3..2、或不同牌型解读）——点「出牌」后弹窗列出所有解读（`comboDescribe`），玩家选定后才带 `joker_assignment` 提交（§规则 4.1）。唯一解则直接提交。
- **整场结束**：弹窗显示整场赢家 + 累计分，可「再来一场」回开始页。
- 动画：出牌入场 `pop`、当前座位高亮；发牌/清台动画暂未做（自绘方案的可选增强）。

---

## 7. 工程规范（务必遵守）

### 7.0 开发环境（UV + Python 3.12）

> **本仓库统一用 [uv](https://docs.astral.sh/uv/) 管理环境，Python 固定 3.12。所有命令都走 `uv run`，不要直接调系统 `python` / `pip` / 全局 `pytest`，也不要手动 `pip install`。** 环境已初始化完毕（`pyproject.toml` + `uv.lock` + `.venv`）。

- **Python 版本**：`3.12`（`.python-version` 已固定；`requires-python = ">=3.12"`，ruff/pyright 的 `target-version` / `pythonVersion` 同为 `py312`）。
- **依赖分层（optional extras）**：
  - 默认依赖：引擎层只需 `numpy` + `pydantic`，保持轻量、可高频调用。
  - `api`：FastAPI + uvicorn + websockets，接口层才装。
  - `dev`：pre-commit / ruff / pycodestyle / pyright / pytest 全家桶。
- **常用命令**：

  ```bash
  uv sync --extra dev --extra api        # 安装/同步依赖（首次 + 改 deps 后）
  uv run python -m ...                   # 跑脚本
  uv run pytest                          # 跑单测
  uv run ruff check --fix . && uv run ruff format .   # lint + 格式化
  uv add <pkg>                           # 新增依赖（自动写回 pyproject + uv.lock）
  ```

- **提交前必跑**（与 workspace 规范一致）：

  ```bash
  uv sync --frozen --extra dev && uv run pre-commit run --all-files
  ```

  pre-commit 已 `install`，钩子顺序：`ruff format` → `ruff check --fix` → `pycodestyle`（max-line-length=88，忽略 `E203,E501,W503,E704`）→ `pyright`。

### 7.1 ruff / lint / 类型

- **ruff**：`line-length = 88`、双引号、4 空格缩进。lint 规则集 `E/F/I/UP/ARG` + `B006/B008/B039/RUF012`（捕获可变默认值等陷阱）。isort 把 `engine` / `api` 视为 first-party。
- **pyright**：`typeCheckingMode = "standard"`，`include = ["engine", "api"]`（`tests` / `web` 不纳入类型检查）。
- **测试豁免**：`tests/**/*.py` 忽略 `ARG`（fixtures / 接口实现常有未用参数）。

### 7.2 单测（pytest）

- 测试放 `tests/`，文件 `test_*.py`、类 `Test*`、函数 `test_*`。
- 默认 `addopts` 已带 `-n auto`（xdist 并行）+ `--tb=short`，并 `-m 'not integration'` 排除集成测试；标 `@pytest.mark.integration` 的用例需显式 `-m integration` 才跑。
- 引擎单测是本项目少数**主动要写**的单测（§1.1 已说明，覆盖牌型/比较/合法动作/强制出牌/结算/王替代边界），覆盖了 workspace「默认不写单测」的约定。

### 7.3 编码约束（摘自 workspace CLAUDE.md）

- **不吞异常**：让异常向上冒泡，保留堆栈；禁止防御性 `try-except`、禁止 `except: return None`。非法牌型 / 非法动作一律 **fail hard**。
- **无前向兼容 / fallback**：完整实现新逻辑，不留兼容层、deprecated wrapper、旧字段。
- **强类型、上游结构优先**：用枚举 / 明确数据类表达牌、牌型、动作；禁止 `dict[str, Any]`、`getattr(..., default)`、`hasattr` 探测。未知枚举 / 缺字段 fail hard，不映射成「看起来安全」的默认值。
- **组合优于继承**，避免过度设计，不堆无关抽象。
- **简洁日志**：关键信息整合到单行。
- **引擎确定性**：所有随机走显式 RNG（seed 可注入），不用隐藏随机源。
- **pydantic 只在接口边界**：网络模型放 `api/schemas.py`；引擎内部用轻量、可高频调用、可深拷贝的结构（为 RL 性能）。

> 提交前检查命令见 §7.0。

---

## 8. 里程碑

| 阶段 | 产出 | 说明 |
|------|------|------|
| **M0 规则定稿** | `rules.md` + 本文件 | ✅ 已冻结：R1–R5 全部裁定完毕（rules.md §10），可直接进入 M1 |
| **M1 引擎核心** | `cards/combos/state/rules/engine/match` + `tests/` | 牌型识别 + 比较（含炸弹大小序）+ 合法动作生成（含强制出牌）+ step + 积分结算 + **整场编排（多局到 30、首家链）**；**同步写引擎单测**（边界：王替代、强制炸、炸弹大小序、积分归属） |
| **M2 环境壳** | `env.py` | Gym 风格观测/动作编码 + mask + seed 复现（为 RL 留好，不训练） |
| **M3 接口层** | `api/` | ✅ 建局 / 视角查询 / 合法动作 / 提交动作 / `/advance` 逐手 / WS snapshot；内存对局；简单 bot（在 `engine/bots.py`）；静态资源同源托管 |
| **M4 前端 MVP** | `web/` | ✅ 原生 JS + 自绘卡面（含两张王）；**human + play 两模式**完整可玩；强制出牌、含王歧义弹窗、累计分到 30、观战逐手/自动播放 |
| **M5（未来）RL 训练** | 训练脚本 | self-play / 策略网络 / reward 调参——**本阶段不做**，仅确认 M1–M2 接口够用 |

依赖关系：**M0 → M1 → {M2, M3} → M4**；M3 依赖 M1，M4 依赖 M3（+ M1 的 id 映射）。

---

## 9. 关键注意点

> 规则侧问题已全部裁定（rules.md §10 R1–R5），不再是开放项。剩余为实现注意点：

- **前端不用 deck-of-cards**：已改自绘 CSS 卡面（见 §6 偏差说明），两张王自绘搞定。
- **动作空间因王指派膨胀**：合法动作生成需对王的等价指派**去重**（同牌面 + 同有效牌型只留规范形式），保持动作目录可控（M1/M2 注意）。
- **强制出牌的服务端兜底**：所有出牌都是强制（R2），合法动作中几乎不出现自由 `PASS`；前端务必正确禁用「过」，服务端对非法 `PASS` 直接 fail hard。
- **play 观战模式不能预跑**：全 bot 建局若调 `_run_bots` 会一次算完整场；必须靠前端 `/advance` 逐手推进才能做动画（见 §5.2）。
- **运行方式**：`uv run uvicorn api.server:app --reload` 后开 `http://127.0.0.1:8000/`（前端与 API 同源）；独立后端测试用 `uv run python -m engine human|play|sim|bench`。

---

> **当前状态（2026-05）**：M0–M4 全部完成并通过测试（51 引擎单测 + 6 API 端到端、pyright/ruff/pre-commit 全绿）。human 与 play 两模式可在浏览器完整对局。剩 M5（RL 训练）按计划本阶段不做，§4.5 环境接口已留好。
