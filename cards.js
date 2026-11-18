import { headToHeadFrame, lifetimeFrame, scaled, setsFrame } from "./broadcast.js";

// Stat cards (app/server/figures.py), drawn as broadcast frames (broadcast.js): lifetime figures, a head-to-head or
// comparison, and set lists. Every number comes from the figures event; a missing one reads "not recorded", never 0.
// Below each frame, outside the graphic: what it counts, and the mode switch. Built with textContent only.

const MODES = [["1v1 and 2v2", "Both"], ["1v1", "1v1"], ["2v2", "2v2"]];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

const count = new Intl.NumberFormat("en-US");

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

// a. Lifetime: the broadcast frame (broadcast.js), with the scope and the mode switch below it, outside the graphic

function lifetime(card) {
  const node = el("section", "stat-card broadcast");
  const holder = el("div", "bc-holder");
  const draw = (mode) => holder.replaceChildren(scaled(lifetimeFrame(card, mode)));
  draw(MODES[0][0]);
  node.append(holder, scopeBox(card.scope + (("earnings" in card.player) ? ` ${earningsNote(card.player.earnings)}.` : "")), modeSwitch(draw));
  return node;
}

// b. Head-to-head and comparison: the broadcast frame, the scope below it, the mode switch

function versus(card) {
  const node = el("section", "stat-card broadcast");
  const holder = el("div", "bc-holder");
  const draw = (mode) => holder.replaceChildren(scaled(headToHeadFrame(card, mode)));
  draw(MODES[0][0]);
  const [a, b] = card.players;
  const notes = [card.scope];
  if (card.record) {
    const r = card.record;
    const games = r.games_won === null || r.games_won === undefined ? "games not recorded" : `${r.games_won}–${r.games_lost} in games`;
    notes.push(`The record is ${a.name}'s official 1v1 sets against ${b.name}: ${r.wins}–${r.losses}, ${games}` +
      (r.unscored ? `, leaving out ${r.unscored} set${r.unscored === 1 ? "" : "s"} with no recorded score.` : "."));
  }
  if ("earnings" in a && "earnings" in b) {
    const sources = [...new Set([a, b].filter((p) => p.earnings.amount !== null).map((p) => `${p.earnings.source}, as of ${p.earnings.as_of}`))];
    notes.push(sources.length ? `Earnings: career, all modes · ${sources.join("; ")}.` : "Earnings: no figure in the data for either player.");
  }
  node.append(holder, scopeBox(notes.join(" ")), modeSwitch(draw));
  return node;
}

// c. Sets: the "Matches" sidebar frame, with the same sets as a plain list below it for reading and screen readers

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
  const node = el("section", "stat-card broadcast");
  const { frame, width } = setsFrame(card);
  node.append(scaled(frame, width, 1080, 560), scopeBox(card.scope));
  if (card.sets?.length) {
    const list = el("details", "set-details");
    list.append(el("summary", null, `The ${card.sets.length} set${card.sets.length === 1 ? "" : "s"} as a list`));
    const ol = el("ol", "set-list");
    ol.append(...card.sets.map(setRow));
    list.append(ol);
    node.append(list);
  } else if (card.sets === null) {
    node.append(el("p", "card-sub", `${count.format(card.total)} sets: too many to list here.`));
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
