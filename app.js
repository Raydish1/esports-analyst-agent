// The Cortex page: the chat on the left asks the backend and follows each question's event stream; each answer's
// result card goes on the right, under the particle hero. Every value from the server goes into the page through
// textContent (or markdown.js and the card renderers, which use it too).

import { renderCards } from "./cards.js";
import { startHero } from "./hero.js";
import { how, tableBlock } from "./how.js";
import { jagify } from "./jag.js";
import { render } from "./markdown.js";

const $ = (id) => document.getElementById(id);
const messages = $("messages");
const right = $("right");
const form = $("composer");
const box = $("q");
const send = form.querySelector(".send");
const SUGGESTIONS = 4;

const state = { conversation: null, busy: false, results: 0 };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await response.json(); } catch { /* an empty or non-JSON body */ }
  if (!response.ok) {
    const detail = data && data.detail;
    throw Object.assign(new Error(typeof detail === "string" ? detail : `The server answered ${response.status}.`),
      { status: response.status });
  }
  return data;
}

async function newConversation() {
  state.conversation = (await api("/api/conversations", {})).conversation_id;
}

function setBusy(busy) {
  state.busy = busy;
  for (const b of [send, ...document.querySelectorAll("#suggest button")]) b.setAttribute("aria-disabled", String(busy));
}

// Chat

function addMsg(kind, ...content) {
  const m = el("div", `msg ${kind} jag`);
  m.dataset.jag = "bubble";
  m.append(...content);
  messages.append(m);
  jagify(m);
  messages.scrollTop = messages.scrollHeight;
  return m;
}

function typingBubble() {
  const row = el("div", "typing-row");
  const dots = el("span", "typing");
  dots.setAttribute("aria-label", "Working");
  dots.append(el("i"), el("i"), el("i"));
  const line = el("span", "progress-line");
  row.append(dots, line);
  const bubble = addMsg("bot", row);
  bubble.progress = (text) => { line.textContent = text; };
  return bubble;
}

function notesList(notes) {
  const list = el("ul", "notes");
  list.setAttribute("role", "note");
  for (const note of notes) list.append(el("li", null, note));
  return list;
}

// Buttons that answer "which player did you mean?": one sends its ordinal; with two names, Send sends both.
function suggestionButtons(groups) {
  const block = el("div", "suggestions");
  const chosen = {};
  const sendBoth = el("button", "choice", "Send");
  sendBoth.type = "button";
  sendBoth.disabled = true;
  const lock = () => block.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  for (const group of groups) {
    block.append(el("h3", null, groups.length > 1 ? `Which “${group.name}”?` : "Did you mean:"));
    const choices = el("div", "choices");
    group.options.forEach((option, i) => {
      const button = el("button", "choice");
      button.type = "button";
      button.setAttribute("aria-pressed", "false");
      button.append(el("span", "name", option.label));
      if (option.detail) button.append(el("span", "detail", option.detail));
      button.addEventListener("click", () => {
        if (state.busy) return;
        if (groups.length === 1) {
          button.setAttribute("aria-pressed", "true");
          lock();
          ask(option.reply);
          return;
        }
        chosen[group.name] = i;
        choices.querySelectorAll(".choice").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
        sendBoth.disabled = groups.some((g) => !(g.name in chosen));
      });
      choices.append(button);
    });
    block.append(choices);
  }
  if (groups.length > 1) {
    sendBoth.addEventListener("click", () => {
      if (state.busy) return;
      lock();
      ask(groups.map((g) => `${g.options[chosen[g.name]].reply} for ${g.name}`).join(", "));
    });
    block.append(sendBoth);
  }
  return block;
}

// Results

// The table a card shows when the answer has no stat card: the main table of the turn's last data tool call.
const MAIN_TABLE = { event_results: 1, player_results: 0, head_to_head: 0, rank_players: 0, run_sql: 0 };

function mainTable(steps) {
  for (const step of [...steps].reverse()) {
    for (const call of [...step.calls].reverse()) {
      if (!(call.tool in MAIN_TABLE) || call.result.kind === "error" || call.refused) continue;
      const tables = call.result.tables || [];
      const t = tables[MAIN_TABLE[call.tool]] || tables[0];
      if (t && t.rows && t.rows.length) return t;
    }
  }
  return null;
}

function scrollToResult(card) {
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  card.classList.remove("flash");
  void card.offsetWidth;
  card.classList.add("flash");
}

function resultCard(question, turn) {
  const n = ++state.results;
  const card = el("article", "result jag enter");
  card.dataset.jag = "card";
  card.id = `result-${n}`;
  const meta = el("div", "meta");
  meta.append(el("span", "tag", `Result #${n}`),
    el("span", "ts", new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })));
  const body = el("div", "result-body");
  if (turn.figures.length) {
    body.append(renderCards(turn.figures));
  } else {
    body.append(tableBlock(turn.table));
  }
  if (turn.steps.length) body.append(how(turn.steps, turn.examples));
  card.append(meta, el("h2", null, question), body);
  const wrap = el("div", "shadow-dark");
  wrap.append(card);
  right.append(wrap);
  jagify(wrap);
  requestAnimationFrame(() => scrollToResult(card));
  return { card, n };
}

// A question

function follow(jobId, turn, bubble) {
  return new Promise((resolve) => {
    const source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);
    let ended = false;
    source.onmessage = (message) => {
      const event = JSON.parse(message.data);
      switch (event.type) {
        case "queued":
          bubble.progress(event.ahead > 0 ? `Waiting: ${event.ahead} question${event.ahead === 1 ? "" : "s"} ahead` : "Next in line");
          break;
        case "started": bubble.progress("Starting"); break;
        case "thinking": bubble.progress(event.label); break;
        case "tool_started": bubble.progress(event.label); break;
        case "step": turn.steps.push(event); break;
        case "examples": turn.examples = event.examples; break;
        case "answer": turn.answer = event; break;
        case "figures": turn.figures = event.figures; break;
        case "error": turn.error = event.message; break;
        case "done": ended = true; source.close(); resolve(); break;
      }
    };
    source.onerror = () => {
      if (!ended && source.readyState === EventSource.CLOSED) {
        turn.error = turn.error || "The connection to the server was lost.";
        resolve();
      }
    };
  });
}

function reply(question, turn) {
  if (turn.error) {
    const m = addMsg("bot error", el("p", null, turn.error));
    if (turn.steps.length) m.append(how(turn.steps, turn.examples));  // the steps before it stopped
    return;
  }
  const a = turn.answer;
  const parts = [];
  if (a.notes.length) parts.push(notesList(a.notes));
  if (a.problem) parts.push(el("p", "problem", a.problem));
  if (a.text) parts.push(render(a.text));
  if (a.suggestions.length) parts.push(suggestionButtons(a.suggestions));
  turn.table = a.outcome === "answered" && !turn.figures.length ? mainTable(turn.steps) : null;
  if (a.outcome === "answered" && (turn.figures.length || turn.table)) {
    const { card, n } = resultCard(question, turn);
    const chip = el("button", "result-chip", `View result #${n} →`);
    chip.type = "button";
    chip.addEventListener("click", () => scrollToResult(card));
    parts.push(chip);
  }
  addMsg("bot", ...parts);
}

async function ask(question) {
  question = question.trim();
  if (!question || state.busy) return;
  setBusy(true);
  addMsg("user", document.createTextNode(question));
  const bubble = typingBubble();
  const turn = { steps: [], examples: [], figures: [], answer: null, error: null, table: null };
  try {
    let job;
    try {
      job = await api(`/api/conversations/${state.conversation}/questions`, { question });
    } catch (error) {
      if (error.status !== 404) throw error;
      await newConversation();  // the conversation expired: start a new one
      job = await api(`/api/conversations/${state.conversation}/questions`, { question });
    }
    await follow(job.job_id, turn, bubble);
  } catch (error) {
    turn.error = error.message;
  }
  bubble.remove();
  if (!turn.answer && !turn.error) turn.error = "No answer came back.";
  reply(question, turn);
  setBusy(false);
  box.focus();
}

// Setup

form.addEventListener("submit", (e) => {
  e.preventDefault();
  if (!box.value.trim() || state.busy) return;
  const question = box.value;
  box.value = "";
  ask(question);
});

$("restart").addEventListener("click", async () => {
  if (state.busy) return;
  messages.querySelectorAll(".msg").forEach((m, i) => { if (i > 0) m.remove(); });  // keep the greeting
  right.querySelectorAll(".shadow-dark").forEach((r) => r.remove());
  state.results = 0;
  await newConversation();
  window.scrollTo({ top: 0, behavior: "smooth" });
  box.focus();
});

async function init() {
  const narrow = window.matchMedia("(max-width: 960px)");  // one column: the results come after the chat
  const where = () => { $("where").textContent = narrow.matches ? "below" : "on the right"; };
  where();
  narrow.addEventListener("change", where);
  jagify();
  startHero($("particles"), $("heroName"), $("hero"));
  try {
    const info = await api("/api/info");
    const badge = $("mode");
    badge.textContent = info.mode === "live" ? "Live" : "Replay";
    badge.title = info.mode === "live" ? "Answers come from the model now."
      : "Answers are recorded model replies, run again through the agent and its tools.";
    badge.classList.toggle("live", info.mode === "live");
    badge.hidden = false;
    const suggest = $("suggest");
    for (const q of info.examples.slice(0, SUGGESTIONS)) {
      const b = el("button", null, q);
      b.type = "button";
      b.addEventListener("click", () => ask(q));
      suggest.append(b);
    }
    await newConversation();
  } catch (error) {
    offline();
  }
}

// No backend answered: the page is on a static host (a preview, such as GitHub Pages) or the server is down. The page
// and the hero still work; questions are switched off, and the chat says why.
function offline() {
  addMsg("bot", el("p", null, "This is a preview of the page: the agent isn't connected here yet, so questions are off."));
  box.disabled = true;
  box.placeholder = "Questions are off in this preview";
  send.setAttribute("aria-disabled", "true");
  state.busy = true;
}

init();
