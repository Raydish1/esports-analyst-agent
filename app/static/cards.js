import { lifetimeFrame, scaled } from "./broadcast.js";

// Stat cards (app/server/figures.py): lifetime figures, a head-to-head or comparison, and set lists. Every number
// comes from the figures event; a missing one reads "not recorded", never 0. Built with textContent only.

const MODES = [["1v1 and 2v2", "Both"], ["1v1", "1v1"], ["2v2", "2v2"]];
const MEDALS = [["first", "Gold", "gold"], ["second", "Silver", "silver"], ["third", "Bronze", "bronze"]];
const SETS_SHOWN = 10;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const count = new Intl.NumberFormat("en-US");

function figure(value, format = (v) => count.format(v)) {
  return value === null || value === undefined ? el("span", "missing", "not recorded") : el("span", "value", format(value));
}

function years(player) {
  const from = player.first?.slice(0, 4);
  const to = player.latest?.slice(0, 4);
  if (!from) return "No official results";
  return from === to ? `Official results in ${from}` : `Official results ${from}–${to}`;
}

function scopeBox(text) {
  const box = el("p", "scope");
  box.append(el("strong", null, "What this counts: "), document.createTextNode(text));
  return box;
}

function earningsNote(e) {
  if (!e || e.amount === null || e.amount === undefined) return "No career earnings figure in the data";
  return `Career, all modes · ${e.source}, as of ${e.as_of}`;
}

function modeSwitch(onPick) {
  const group = el("div", "mode-switch");
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", "Mode");
  for (const [key, label] of MODES) {
    const b = el("button", null, label);
    b.type = "button";
    b.setAttribute("aria-pressed", String(key === MODES[0][0]));
    b.addEventListener("click", () => {
      group.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      onPick(key);
    });
    group.append(b);
  }
  return group;
}

function head(eyebrow, title, sub) {
  const header = el("header", "card-head");
  header.append(el("p", "eyebrow", eyebrow));
  if (title) header.append(el("h3", null, title));
  if (sub) header.append(el("p", "card-sub", sub));
  return header;
}

// a. Lifetime: the broadcast frame (broadcast.js), with the scope and the mode switch below it, outside the graphic

function lifetime(card) {
  const node = el("section", "stat-card broadcast");
  const holder = el("div", "bc-holder");
  const draw = (mode) => holder.replaceChildren(scaled(lifetimeFrame(card, mode)));
  draw(MODES[0][0]);
  node.append(holder, scopeBox(card.scope + (("earnings" in card.player) ? ` ${earningsNote(card.player.earnings)}.` : "")), modeSwitch(draw));
  return node;
}

// b. Head-to-head and comparison

function bar(value, most, side) {
  const cell = el("div", `side ${side}`);
  const track = el("div", "track");
  if (value !== null && value !== undefined && most > 0) {
    const fillBar = el("div", "bar");
    fillBar.style.width = `${Math.max(value > 0 ? 3 : 0, (value / most) * 100)}%`;
    track.append(fillBar);
  }
  cell.append(track);
  return cell;
}

function versus(card) {
  const [a, b] = card.players;
  const node = el("section", `stat-card versus ${card.kind}`);
  node.append(head(card.kind === "head_to_head" ? "Head-to-head" : "Comparison", null, null));
  const names = el("div", "names");
  names.append(el("span", "name a", a.name));
  const middle = el("div", "record");
  if (card.record) {
    const r = card.record;
    middle.append(el("span", "big", `${r.wins} – ${r.losses}`), el("span", "label", "1v1 sets"));
    const games = r.games_won === null || r.games_won === undefined ? "games not recorded" : `${r.games_won} – ${r.games_lost} games`;
    middle.append(el("span", "games", games));
  } else {
    middle.append(el("span", "label", "vs"));
  }
  names.append(middle, el("span", "name b", b.name));
  node.append(names);
  if (card.record?.unscored) {
    const n = card.record.unscored;
    node.append(el("p", "card-sub center", `Games leave out ${n} set${n === 1 ? "" : "s"} with no recorded score.`));
  }
  node.append(scopeBox(card.scope));
  const rows = el("div", "rows");
  const earned = "earnings" in a && "earnings" in b;
  const fill = (mode) => {
    const lines = [];
    if (earned) lines.push(["Earnings", a.earnings.amount, b.earnings.amount, (v) => money.format(v)]);
    for (const [key, label] of MEDALS) lines.push([label, a.modes[mode]?.[key], b.modes[mode]?.[key]]);
    lines.push(["Top 8", a.modes[mode]?.top8, b.modes[mode]?.top8]);
    if (a.top32 && b.top32) lines.push(["Top 32", a.modes[mode]?.top32, b.modes[mode]?.top32]);
    rows.replaceChildren(...lines.map(([label, x, y, format]) => {
      const most = Math.max(x ?? 0, y ?? 0);
      const row = el("div", "row");
      const left = bar(x, most, "a");
      left.prepend(figure(x, format));
      const right = bar(y, most, "b");
      right.append(figure(y, format));
      row.append(left, el("span", "row-label", label), right);
      return row;
    }));
  };
  fill(MODES[0][0]);
  node.append(modeSwitch(fill), rows);
  const notes = [];
  if (earned) {
    const sources = [...new Set([a, b].filter((p) => p.earnings.amount !== null).map((p) => `${p.earnings.source}, as of ${p.earnings.as_of}`))];
    notes.push(sources.length ? `Earnings: career, all modes · ${sources.join("; ")}` : "Earnings: no figure in the data for either player");
  }
  notes.push(`${a.name}: ${years(a)} · ${b.name}: ${years(b)}`);
  if (card.record_scope) notes.push(`Record: ${card.record_scope}`);
  for (const n of notes) node.append(el("p", "card-foot", n));
  return node;
}

// c. Sets

function setRow(s) {
  const row = el("li", "set");
  const when = el("span", "when", s.event ? `${s.date} · ${s.event}` : s.date);
  const line = el("span", "line");
  const score = s.winner_games === null || s.winner_games === undefined
    ? el("span", "score missing", "score not recorded")
    : el("span", "score", `${s.winner_games} – ${s.loser_games}`);
  line.append(el("strong", "winner", s.winner), score, el("span", "loser", s.loser ?? ""));
  row.append(when, line);
  return row;
}

function sets(card) {
  const node = el("section", "stat-card sets");
  const sub = card.event ? `${card.event}${card.date ? ` · ${card.date}` : ""}` : null;
  node.append(head("Sets", card.title, sub), scopeBox(card.scope));
  if (card.sets === null) {
    node.append(el("p", "card-sub", `${count.format(card.total)} sets: too many to list here.`));
    return node;
  }
  if (!card.sets.length) {
    node.append(el("p", "card-sub", "No sets are recorded for these players here."));
    return node;
  }
  const list = el("ol", "set-list");
  const show = (all) => list.replaceChildren(...(all ? card.sets : card.sets.slice(0, SETS_SHOWN)).map(setRow));
  show(false);
  node.append(list);
  if (card.sets.length > SETS_SHOWN) {
    const more = el("button", "more", `Show all ${card.sets.length} sets`);
    more.type = "button";
    more.addEventListener("click", () => { show(true); more.remove(); });
    node.append(more);
  }
  return node;
}

export function renderCards(cards) {
  const make = { lifetime, head_to_head: versus, comparison: versus, sets };
  const out = document.createDocumentFragment();
  for (const card of cards) {
    if (make[card.kind]) out.append(make[card.kind](card));
  }
  return out;
}
