// 牌面渲染 + card id 映射（与后端 engine/cards.py 共用同一套 id 约定）。
//   普通牌 id 0–51 = rank_order*4 + suit_order；王 id 52、53（万能牌）。
//   rank_order: 0..12 → 3 4 5 6 7 8 9 10 J Q K A 2（§规则 2.2 大小序）。
//   suit_order: 0..3 → 黑桃 红桃 梅花 方块。

const RANK_LABELS = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"];
const SUIT_SYMBOLS = ["♠", "♥", "♣", "♦"]; // ♠ ♥ ♣ ♦
const NUM_SUITS = 4;
const NUM_NORMAL = 52;

function isJoker(id) {
  return id >= NUM_NORMAL;
}

function cardRank(id) {
  return Math.floor(id / NUM_SUITS);
}

function cardSuit(id) {
  return id % NUM_SUITS;
}

function rankLabel(order) {
  return RANK_LABELS[order];
}

// 渲染一张牌的 DOM 元素。
//   opts.assignedRank: 王在某牌型里代表的 rank_order（出过的含王牌型才有）。
//   opts.faceDown: 背面。
function cardElement(id, opts = {}) {
  const el = document.createElement("div");
  el.className = "card";
  el.dataset.id = id;

  if (opts.faceDown) {
    el.classList.add("back");
    return el;
  }

  if (isJoker(id)) {
    el.classList.add("joker");
    const tag = document.createElement("div");
    tag.className = "joker-tag";
    tag.textContent = "JOKER";
    const face = document.createElement("div");
    face.className = "joker-face";
    face.textContent = "🃏"; // 🃏
    el.append(tag, face);
    if (opts.assignedRank !== undefined && opts.assignedRank !== null) {
      const badge = document.createElement("div");
      badge.className = "assign-badge";
      badge.textContent = "=" + rankLabel(opts.assignedRank);
      el.appendChild(badge);
    }
    return el;
  }

  const suit = cardSuit(id);
  const red = suit === 1 || suit === 3;
  el.classList.add(red ? "red" : "black");
  const corner = document.createElement("div");
  corner.className = "corner";
  corner.innerHTML =
    '<span class="rank">' + RANK_LABELS[cardRank(id)] + "</span>" +
    '<span class="suit">' + SUIT_SYMBOLS[suit] + "</span>";
  const pip = document.createElement("div");
  pip.className = "pip";
  pip.textContent = SUIT_SYMBOLS[suit];
  el.append(corner, pip);
  return el;
}

const COMBO_TYPE_NAMES = {
  single: "单",
  pair: "对",
  straight: "顺子",
  consec_pairs: "连对",
  bomb: "炸弹",
};

// 把一个 combo（ComboView）描述成中文短语，便于在选择器/日志里读。
function comboDescribe(combo) {
  const t = combo.combo_type;
  if (t === "single" || t === "pair") {
    return COMBO_TYPE_NAMES[t] + rankLabel(combo.rank_key);
  }
  if (t === "straight") {
    const lo = combo.rank_key - combo.length + 1;
    return "顺子 " + rankLabel(lo) + "–" + rankLabel(combo.rank_key) +
      "（" + combo.length + "张）";
  }
  if (t === "consec_pairs") {
    const lo = combo.rank_key - combo.length + 1;
    return "连对 " + rankLabel(lo) + "–" + rankLabel(combo.rank_key) +
      "（" + combo.length + "对）";
  }
  // bomb
  const kind = combo.uses_joker ? "王炸" : "炸弹";
  let s = kind + " " + combo.cards.length + "×" + rankLabel(combo.rank_key);
  if (combo.uses_joker) {
    const reps = Object.values(combo.joker_assignment).map(rankLabel).join(",");
    s += "（🃏=" + reps + "）";
  }
  return s;
}

window.Cards = {
  isJoker,
  cardRank,
  cardSuit,
  rankLabel,
  cardElement,
  comboDescribe,
};
