import { BACKGROUNDS, headToHeadFrame, leaderboardFrame, lifetimeFrame, recordIn, scaled, setsFrame, teamsFrame } from "./broadcast.js";

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

function modeSwitch(onPick, initial = MODES[0][0]) {
  const group = el("div", "mode-switch");
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", "Mode");
  for (const [key, label] of MODES) {
    const b = el("button", null, label);
    b.type = "button";
    b.setAttribute("aria-pressed", String(key === initial));
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
  const said = (r, what) => {
    const games = r.games_won === null || r.games_won === undefined ? "games not recorded" : `${r.games_won}–${r.games_lost} in games`;
    return `${what}: ${r.wins}–${r.losses}, ${games}` +
      (r.unscored ? `, leaving out ${r.unscored} set${r.unscored === 1 ? "" : "s"} with no recorded score` : "");
  };
  if (card.records) {
    const one = recordIn(card, "1v1");
    const two = recordIn(card, "2v2");
    notes.push(`The record is from ${a.name}'s side, in the mode picked. ` +
      (one?.sets ? said(one, "1v1 sets") : "No 1v1 sets between them") + ". " +
      (two?.sets ? said(two, `2v2 sets with ${a.name} and ${b.name} on opposite teams, whoever their partners`)
        : "No 2v2 sets with them on opposite teams") + ". Both: the two added together.");
  } else if (card.record) {
    notes.push(said(card.record, `The record is ${a.name}'s official 1v1 sets against ${b.name}`) + ".");
  }
  if ("earnings" in a && "earnings" in b) {
    const sources = [...new Set([a, b].filter((p) => p.earnings.amount !== null).map((p) => `${p.earnings.source}, as of ${p.earnings.as_of}`))];
    notes.push(sources.length ? `Earnings: career, all modes · ${sources.join("; ")}.` : "Earnings: no figure in the data for either player.");
  }
  node.append(holder, scopeBox(notes.join(" ")), modeSwitch(draw));
  return node;
}

// 2v2: two teams, or one partnership (the elimination final's frame). It opens on 2v2, as the broadcast shows it; the
// switch changes each player's own figures, never the teams' record or their results together, which are 2v2 only.

function teams(card) {
  const node = el("section", "stat-card broadcast");
  const holder = el("div", "bc-holder");
  const draw = (mode) => holder.replaceChildren(scaled(teamsFrame(card, mode)));
  draw(card.mode);
  const notes = [card.scope];
  if (card.kind === "team") {
    const t = card.together;
    const [a, b] = card.players;
    notes.push(`Together: ${a.name} and ${b.name}'s official 2v2 events with each other, ${t.events} in all; WINS are 1st` +
      " places, MEDALS top 3s, BEST their best placement. The mode switch changes only each player's own figures.");
  } else {
    const r = card.record;
    notes.push(r.sets ? `${card.names[0]} ${r.wins}–${r.losses} against ${card.names[1]} in sets` +
      (absent(r.games_won) ? "" : `, ${r.games_won}–${r.games_lost} in games`) + ". The mode switch changes only each player's own figures."
      : `No official 2v2 sets between ${card.names[0]} and ${card.names[1]}.`);
  }
  node.append(holder, scopeBox(notes.join(" ")), modeSwitch(draw, card.mode));
  return node;
}

function absent(v) { return v === null || v === undefined; }

// c. Sets: the "Matches" sidebar frame, with the same sets as a plain list below it for reading and screen readers

function setRow(s) {
  const row = el("li", "set");
  const when = el("span", "when", [s.date, s.mode, s.event].filter(Boolean).join(" · "));
  const line = el("span", "line");
  const score = s.winner_games === null || s.winner_games === undefined
    ? el("span", "score missing", "score not recorded")
    : el("span", "score", `${s.winner_games} – ${s.loser_games}`);
  line.append(el("strong", "winner", s.winner), score, el("span", "loser", s.loser ?? ""));
  row.append(when, line);
  return row;
}

// A head-to-head's sets (card.modes) follow the mode switch, as its record does; an event's sets have one mode.
function inMode(card, mode) {
  if (!card.modes) return card;
  const total = mode === "1v1 and 2v2" ? card.total : card.totals?.[mode];
  const sets = card.sets && (mode === "1v1 and 2v2" ? card.sets : card.sets.filter((s) => s.mode === mode));
  return { ...card, mode, sets, total };
}

function sets(card) {
  const node = el("section", "stat-card broadcast");
  const holder = el("div", "bc-holder");
  const details = el("div");
  const draw = (mode) => {
    const shown = inMode(card, mode);
    holder.replaceChildren(scaled(setsFrame(shown).frame));
    details.replaceChildren();
    if (shown.sets?.length) {
      const list = el("details", "set-details");
      list.append(el("summary", null, `The ${shown.sets.length} set${shown.sets.length === 1 ? "" : "s"} as a list`));
      const ol = el("ol", "set-list");
      ol.append(...[...shown.sets].reverse().map(setRow));  // newest first, as the frame shows them
      list.append(ol);
      details.append(list);
    } else if (shown.sets === null) {
      details.append(el("p", "card-sub", `${count.format(shown.total)} sets: too many to list here.`));
    }
  };
  draw(MODES[0][0]);
  node.append(holder, scopeBox(card.scope));
  if (card.modes) node.append(modeSwitch(draw));
  node.append(details);
  return node;
}

// A list answer: the leaderboard frame, and what it counts; the full table follows the cards (app.js).
function leaderboard(card) {
  const node = el("section", "stat-card broadcast");
  const holder = el("div", "bc-holder");
  holder.append(scaled(leaderboardFrame(card)));
  const more = card.total > card.rows.length ? ` It shows the first ${card.rows.length} of ${card.total}; the table below has them all.` : "";
  node.append(holder, scopeBox(`${card.scope[0].toUpperCase()}${card.scope.slice(1)}. Tied places share a rank.${more}`));
  return node;
}

export function renderCards(cards) {
  const make = { lifetime, head_to_head: versus, comparison: versus, team: teams, teams, sets, leaderboard };
  const out = document.createDocumentFragment();
  for (const card of cards) {  // each card a background at random, kept through its mode switch
    card.background ??= BACKGROUNDS[Math.floor(Math.random() * BACKGROUNDS.length)];
    if (make[card.kind]) out.append(make[card.kind](card));
  }
  return out;
}
