// 前端主逻辑：human（人机对战）与 play（3 bot 观战）两种模式。
// 全部规则判定都在后端引擎；前端只做选牌→合法动作匹配、视角渲染、观战推进。

const $ = (sel) => document.querySelector(sel);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const state = {
  mode: null,         // 'human' | 'play'
  gameId: null,
  humanSeat: 0,
  view: null,         // 最近一次 GameView
  legal: null,        // human 轮到自己时的 LegalActionsResponse
  selected: new Set(),// 当前选中的 card id
  busy: false,
  autoplay: false,
  speedMs: 800,
};

// ---------- REST ----------
async function api(path, opts) {
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    throw new Error(`${resp.status}: ${await resp.text()}`);
  }
  return resp.json();
}
const jsonPost = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const createGame = (botSeats, seed) =>
  api("/games", jsonPost({ seed, bot_seats: botSeats }));
const fetchLegal = (gid, seat) => api(`/games/${gid}/legal?seat=${seat}`);
const submitAction = (gid, body) => api(`/games/${gid}/actions`, jsonPost(body));
const advance = (gid, seat, reveal) =>
  api(`/games/${gid}/advance?seat=${seat}&reveal=${reveal}`, { method: "POST" });

// ---------- 座位命名 ----------
function seatName(seat) {
  if (state.mode === "play") return "座位" + seat;
  if (seat === state.humanSeat) return "你";
  return seat === (state.humanSeat + 1) % 3 ? "下家" : "上家";
}
function seatEl(seat) {
  return document.getElementById(
    seat === 0 ? "seat-bottom" : seat === 1 ? "seat-left" : "seat-right",
  );
}

// ---------- 渲染 ----------
function renderScore(view) {
  for (let s = 0; s < 3; s++) {
    const chip = document.querySelector(`.score-chip[data-seat="${s}"]`);
    chip.querySelector(".who").textContent = seatName(s);
    chip.querySelector(".val").textContent = view.total_scores[s] + "/30";
    chip.classList.toggle(
      "winner",
      view.match_finished && view.match_winner === s,
    );
  }
  const meta = $("#meta");
  if (view.match_finished) {
    meta.textContent = "整场结束";
  } else {
    meta.innerHTML =
      `第 ${view.games_played + 1} 局 · 首家 ${seatName(view.first_leader)}<br>` +
      `本局炸弹 ${view.bombs_played} · 轮到 ${seatName(view.turn)}`;
  }
}

function renderSeats(view) {
  for (let seat = 0; seat < 3; seat++) {
    const el = seatEl(seat);
    el.querySelector(".name").textContent = seatName(seat);
    el.querySelector(".count-badge").textContent = view.hand_counts[seat] + " 张";
    const active =
      !view.match_finished && !view.round_finished && view.turn === seat;
    el.classList.toggle("active", active);

    const row = el.querySelector(".hand-row");
    row.innerHTML = "";
    const selectableNow =
      seat === state.humanSeat &&
      state.mode === "human" &&
      view.your_turn &&
      !state.busy;
    row.classList.toggle("selectable", selectableNow);

    let faceCards = null;
    if (view.all_hands) faceCards = view.all_hands[seat].map((c) => c.id);
    else if (seat === state.humanSeat) faceCards = view.hand.map((c) => c.id);

    if (faceCards) {
      for (const id of faceCards) {
        const c = Cards.cardElement(id);
        if (selectableNow && state.selected.has(id)) c.classList.add("selected");
        if (selectableNow) c.addEventListener("click", () => toggleSelect(id));
        row.appendChild(c);
      }
    } else {
      for (let i = 0; i < view.hand_counts[seat]; i++) {
        row.appendChild(Cards.cardElement(0, { faceDown: true }));
      }
    }
  }
}

function renderCenter(view) {
  const label = $("#live-label");
  const cards = $("#live-cards");
  cards.innerHTML = "";
  if (view.match_finished) {
    label.textContent = "整场结束";
    return;
  }
  if (view.live_play) {
    const ja = view.live_play.joker_assignment || {};
    label.textContent =
      "生效牌 · " + seatName(view.live_player) + " 打出 · " +
      Cards.comboDescribe(view.live_play);
    for (const id of view.live_play.cards) {
      const opt = {};
      if (Cards.isJoker(id) && id in ja) opt.assignedRank = ja[id];
      cards.appendChild(Cards.cardElement(id, opt));
    }
    const center = $("#center");
    center.classList.remove("flash");
    void center.offsetWidth; // 强制重排以重放动画
    center.classList.add("flash");
  } else {
    label.textContent = seatName(view.leader) + " 领出（自由出牌）";
  }
}

function renderLog(view) {
  const list = $("#log-list");
  list.innerHTML = "";
  for (const h of view.history) {
    const div = document.createElement("div");
    if (h.kind === "pass") {
      div.className = "pass";
      div.textContent = seatName(h.player) + "：过";
    } else {
      div.textContent = seatName(h.player) + "：" + Cards.comboDescribe(h.combo);
    }
    list.appendChild(div);
  }
  list.scrollTop = list.scrollHeight;
}

function applyView(view) {
  state.view = view;
  renderScore(view);
  renderSeats(view);
  renderCenter(view);
  renderLog(view);
  if (state.mode === "play") refreshPlayControls();
  if (view.match_finished) showMatchOver(view);
}

// ---------- human 模式 ----------
function legalPlays() {
  return (state.legal?.actions || []).filter((a) => a.kind === "play");
}
function sameSet(arr, set) {
  return arr.length === set.size && arr.every((x) => set.has(x));
}
function matchingPlays() {
  return legalPlays().filter((a) => sameSet(a.combo.cards, state.selected));
}

function toggleSelect(id) {
  if (state.selected.has(id)) state.selected.delete(id);
  else state.selected.add(id);
  renderSeats(state.view);
  updateActionButtons();
}

function setHumanIdle(msg) {
  $("#play-btn").disabled = true;
  $("#pass-btn").disabled = true;
  $("#clear-btn").disabled = true;
  const s = $("#human-status");
  s.className = "status";
  s.textContent =
    msg || (state.view && state.view.match_finished ? "整场结束" : "等待对手出牌…");
}

function updateActionButtons() {
  const view = state.view;
  const legal = state.legal;
  const status = $("#human-status");
  const passAvail = legal.actions.some((a) => a.kind === "pass");
  const onlyPass =
    legal.actions.length === 1 && legal.actions[0].kind === "pass";
  const matches = matchingPlays();

  $("#pass-btn").disabled = !passAvail;
  $("#clear-btn").disabled = state.selected.size === 0;
  $("#play-btn").disabled = matches.length === 0;

  let msg;
  status.className = "status";
  if (onlyPass) {
    msg = "你压不过，只能过牌";
  } else if (!view.live_play) {
    msg = "你领出，自由出牌";
  } else if (!passAvail) {
    msg = "⚠ 能压必须压：本轮必须出牌";
    status.className = "status warn";
  } else {
    msg = "轮到你";
  }
  if (state.selected.size > 0 && !onlyPass) {
    if (matches.length === 0) msg += " · 当前选择不构成合法出牌";
    else if (matches.length === 1)
      msg += " · 将出 " + Cards.comboDescribe(matches[0].combo);
    else msg += " · 含王多解，点「出牌」后选择";
  }
  status.textContent = msg;
}

async function humanTurnIfNeeded() {
  const view = state.view;
  if (state.mode !== "human") return;
  if (view.match_finished || !view.your_turn) {
    setHumanIdle();
    return;
  }
  state.legal = await fetchLegal(state.gameId, state.humanSeat);
  state.selected.clear();
  renderSeats(view);
  updateActionButtons();
}

async function doSubmitPlay(combo) {
  state.busy = true;
  setHumanIdle("出牌中…");
  const view = await submitAction(state.gameId, {
    seat: state.humanSeat,
    kind: "play",
    cards: combo.cards,
    joker_assignment: combo.joker_assignment,
  });
  state.busy = false;
  state.selected.clear();
  applyView(view);
  await humanTurnIfNeeded();
}

async function onPlayClick() {
  const matches = matchingPlays();
  if (matches.length === 0) return;
  if (matches.length === 1) {
    await doSubmitPlay(matches[0].combo);
    return;
  }
  openChooser(matches);
}

async function onPassClick() {
  state.busy = true;
  setHumanIdle("过牌中…");
  const view = await submitAction(state.gameId, {
    seat: state.humanSeat,
    kind: "pass",
    cards: [],
    joker_assignment: {},
  });
  state.busy = false;
  state.selected.clear();
  applyView(view);
  await humanTurnIfNeeded();
}

function openChooser(matches) {
  const list = $("#chooser-list");
  list.innerHTML = "";
  for (const m of matches) {
    const btn = document.createElement("button");
    btn.textContent = Cards.comboDescribe(m.combo);
    btn.addEventListener("click", async () => {
      $("#chooser").classList.add("hidden");
      await doSubmitPlay(m.combo);
    });
    list.appendChild(btn);
  }
  $("#chooser").classList.remove("hidden");
}

// ---------- play 观战模式 ----------
function refreshPlayControls() {
  const auto = $("#auto-btn");
  const step = $("#step-btn");
  const status = $("#play-status");
  const done = state.view && state.view.match_finished;
  auto.textContent = state.autoplay ? "暂停" : "自动播放";
  auto.disabled = !!done;
  step.disabled = state.autoplay || state.busy || !!done;
  if (done) status.textContent = "整场结束";
  else if (state.autoplay) status.textContent = "自动播放中…";
  else status.textContent = "点「单步」或「自动播放」推进对局";
}

async function stepPlay() {
  if (state.busy || !state.view || state.view.match_finished) return;
  state.busy = true;
  refreshPlayControls();
  const view = await advance(state.gameId, 0, true);
  state.busy = false;
  applyView(view);
}

function toggleAuto() {
  if (state.autoplay) {
    state.autoplay = false;
    refreshPlayControls();
    return;
  }
  state.autoplay = true;
  refreshPlayControls();
  runAuto();
}

async function runAuto() {
  while (state.autoplay && state.view && !state.view.match_finished) {
    await stepPlay();
    if (!state.autoplay) break;
    await sleep(state.speedMs);
  }
  state.autoplay = false;
  refreshPlayControls();
}

// ---------- 整场结束 / 导航 ----------
function showMatchOver(view) {
  state.autoplay = false;
  $("#match-result").textContent =
    state.mode === "human" && view.match_winner === state.humanSeat
      ? "你赢得整场！🎉"
      : seatName(view.match_winner) + " 赢得整场";
  $("#match-scores").textContent =
    "累计分：" +
    view.total_scores.map((v, i) => seatName(i) + " " + v).join(" · ");
  $("#match-over").classList.remove("hidden");
}

function showGameUI(mode) {
  $("#start").classList.add("hidden");
  $("#match-over").classList.add("hidden");
  $("#scoreboard").classList.remove("hidden");
  $("#table").classList.remove("hidden");
  $("#log").classList.remove("hidden");
  $("#controls").classList.toggle("hidden", mode !== "human");
  $("#play-controls").classList.toggle("hidden", mode !== "play");
}

function backToStart() {
  Object.assign(state, {
    mode: null,
    gameId: null,
    view: null,
    legal: null,
    busy: false,
    autoplay: false,
  });
  state.selected.clear();
  for (const id of ["scoreboard", "table", "log", "controls", "play-controls", "match-over", "chooser"]) {
    $("#" + id).classList.add("hidden");
  }
  $("#start").classList.remove("hidden");
  $("#start-error").textContent = "";
}

function resolveSeed() {
  const raw = $("#seed-input").value.trim();
  if (raw === "") return Math.floor(Math.random() * 2147483647);
  const n = parseInt(raw, 10);
  if (Number.isNaN(n)) throw new Error("种子必须是整数");
  return n;
}

async function start(mode) {
  $("#start-error").textContent = "";
  let seed;
  try {
    seed = resolveSeed();
  } catch (e) {
    $("#start-error").textContent = e.message;
    return;
  }
  try {
    state.mode = mode;
    state.humanSeat = 0;
    state.busy = false;
    state.autoplay = false;
    state.selected.clear();
    showGameUI(mode);
    const botSeats = mode === "human" ? [1, 2] : [0, 1, 2];
    const view = await createGame(botSeats, seed);
    state.gameId = view.game_id;
    applyView(view);
    if (mode === "human") await humanTurnIfNeeded();
  } catch (e) {
    backToStart();
    $("#start-error").textContent = "建局失败：" + e.message;
  }
}

// ---------- 事件绑定 ----------
function bind() {
  for (const card of document.querySelectorAll(".mode-card")) {
    card.addEventListener("click", () => start(card.dataset.mode));
  }
  $("#play-btn").addEventListener("click", onPlayClick);
  $("#pass-btn").addEventListener("click", onPassClick);
  $("#clear-btn").addEventListener("click", () => {
    state.selected.clear();
    renderSeats(state.view);
    updateActionButtons();
  });
  $("#auto-btn").addEventListener("click", toggleAuto);
  $("#step-btn").addEventListener("click", stepPlay);
  $("#speed-range").addEventListener("input", (e) => {
    // 滑块越大越慢，方便阅读；speedMs = 范围值。
    state.speedMs = parseInt(e.target.value, 10);
  });
  $("#new-game-btn").addEventListener("click", backToStart);
  $("#again-btn").addEventListener("click", backToStart);
  // 点选择器遮罩空白处取消（不被含王歧义弹窗困住）。
  $("#chooser").addEventListener("click", (e) => {
    if (e.target.id === "chooser") $("#chooser").classList.add("hidden");
  });
}

bind();
