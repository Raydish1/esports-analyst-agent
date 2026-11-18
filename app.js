// The page: asks the backend, follows each question's event stream, and shows progress, then the answer.
// Every value from the server goes into the page through textContent (or markdown.js, which uses it too).

import { render } from "./markdown.js";

const $ = (id) => document.getElementById(id);
const thread = $("thread");
const welcome = $("welcome");
const form = $("composer");
const box = $("question");
const send = $("send");

const state = { conversation: null, busy: false, mode: null };

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
    const message = typeof detail === "string" ? detail : `The server answered ${response.status}.`;
    throw Object.assign(new Error(message), { status: response.status });
  }
  return data;
}

async function newConversation() {
  state.conversation = (await api("/api/conversations", {})).conversation_id;
}

function setBusy(busy) {
  state.busy = busy;
  send.disabled = busy;
  for (const b of document.querySelectorAll(".examples button")) b.disabled = busy;
}

// Progress

function summarize(call) {
  const r = call.result;
  if (call.refused) return "refused: a player ID no lookup returned";
  if (r.kind === "error") return "error";
  if (r.kind === "not run") return "not run";
  if (r.kind === "player") {
    const top = r.tables[0]?.rows?.[0];
    return top ? `${r.status.split(":")[0]}: ${top[1]}` : r.status.split(":")[0];
  }
  if (r.kind === "event") return r.status;
  const counts = r.tables.map((t) => (t.rows === null ? `${t.row_count} rows (too many to show the model)` : `${t.row_count} row${t.row_count === 1 ? "" : "s"}`));
  return counts.join(", ") || "no rows";
}

class Progress {
  constructor(parent) {
    this.list = el("ol", "progress");
    parent.append(this.list);
    this.waiting = null;
    this.stepTools = [];
  }

  item(text, cls = "active") {
    this.settle();
    const li = el("li", cls);
    li.append(el("span", "label", text));
    this.list.append(li);
    return li;
  }

  settle() {
    for (const li of this.list.querySelectorAll("li.active")) li.className = "done";
  }

  queued(event) {
    const text = event.ahead > 0 ? `Waiting: ${event.ahead} question${event.ahead === 1 ? "" : "s"} ahead of yours` : "Next in line";
    if (!this.waiting) this.waiting = this.item(text);
    else this.waiting.querySelector(".label").textContent = text;
  }

  started() {
    if (this.waiting) { this.waiting.remove(); this.waiting = null; }
  }

  thinking(event) { this.stepTools = []; this.item(event.label); }

  tool(event) { this.stepTools.push(this.item(event.label)); }

  step(event) {
    event.calls.forEach((call, i) => {
      const li = this.stepTools[i] || this.item(call.tool, "done");
      li.className = call.refused || call.result.kind === "error" ? "bad" : "done";
      li.querySelector(".result")?.remove();
      li.append(el("span", "result", `· ${summarize(call)}`));
    });
    this.settle();
    this.stepTools = [];
  }

  finish() {
    this.settle();
    this.list.classList.add("finished");
  }
}

// The answer

function notesBox(notes) {
  const list = el("ul", "notes");
  list.setAttribute("role", "note");
  for (const note of notes) list.append(el("li", null, note));
  return list;
}

function suggestionsBlock(groups, card) {
  const block = el("div", "suggestions");
  const chosen = {};
  const sendBoth = el("button", null, "Send");
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
  card.dataset.suggestions = "true";
  return block;
}

function metaLine(event) {
  const meta = el("div", "meta");
  if (event.steps) meta.append(el("span", null, `${event.steps} step${event.steps === 1 ? "" : "s"}`));
  if (event.model_seconds) meta.append(el("span", null, `${event.model_seconds} s with the model`));
  if (event.replay) {
    const seed = event.replay.seed === null || event.replay.seed === undefined ? "" : `, seed ${event.replay.seed}`;
    meta.append(el("span", null, `Replayed from ${event.replay.source}${seed}`));
    if (event.replay.mismatch) meta.append(el("span", "mismatch", event.replay.mismatch));
  }
  return meta;
}

function answerCard(event, turn) {
  const card = el("article", "card answer");
  if (event.notes.length) card.append(notesBox(event.notes));
  if (event.problem) card.append(el("p", "problem", event.problem));
  if (event.text) card.append(render(event.text));
  if (event.suggestions.length) card.append(suggestionsBlock(event.suggestions, card));
  const figures = el("div", "figures");  // stat graphics go here, built from the templates' output (figures.py)
  card.append(figures);
  card.append(metaLine(event));
  turn.answer = card;
  return card;
}

function errorCard(message) {
  const card = el("article", "card error");
  card.setAttribute("role", "alert");
  card.append(el("p", null, message));
  return card;
}

// A question

function follow(jobId, turn) {
  return new Promise((resolve) => {
    const source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);
    const progress = turn.progress;
    let ended = false;
    source.onmessage = (message) => {
      const event = JSON.parse(message.data);
      switch (event.type) {
        case "queued": progress.queued(event); break;
        case "started": progress.started(); break;
        case "thinking": progress.thinking(event); break;
        case "tool_started": progress.tool(event); break;
        case "step": progress.step(event); turn.steps.push(event); break;
        case "examples": turn.examples = event.examples; break;
        case "answer": progress.finish(); turn.node.append(answerCard(event, turn)); break;
        case "error": progress.finish(); turn.node.append(errorCard(event.message)); break;
        case "done": ended = true; source.close(); resolve(); break;
      }
      turn.node.scrollIntoView({ block: "end", behavior: "smooth" });
    };
    source.onerror = () => {
      if (!ended && source.readyState === EventSource.CLOSED) {
        progress.finish();
        turn.node.append(errorCard("The connection to the server was lost."));
        resolve();
      }
    };
  });
}

async function ask(question) {
  question = question.trim();
  if (!question || state.busy) return;
  setBusy(true);
  welcome.hidden = true;
  const node = el("section", "turn");
  node.append(el("div", "asked", question));
  const turn = { node, steps: [], examples: [], answer: null };
  thread.append(node);
  turn.progress = new Progress(node);
  try {
    let job;
    try {
      job = await api(`/api/conversations/${state.conversation}/questions`, { question });
    } catch (error) {
      if (error.status !== 404) throw error;
      await newConversation();  // the conversation expired: start a new one
      job = await api(`/api/conversations/${state.conversation}/questions`, { question });
    }
    await follow(job.job_id, turn);
  } catch (error) {
    turn.progress.finish();
    node.append(errorCard(error.message));
  } finally {
    setBusy(false);
    box.focus();
  }
}

// Setup

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const question = box.value;
  if (!question.trim() || state.busy) return;
  box.value = "";
  resize();
  ask(question);
});

box.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    form.requestSubmit();
  }
});

function resize() {
  box.style.height = "auto";
  box.style.height = `${Math.min(box.scrollHeight, 160)}px`;
}
box.addEventListener("input", resize);

$("restart").addEventListener("click", async () => {
  if (state.busy) return;
  for (const node of thread.querySelectorAll(".turn")) node.remove();
  welcome.hidden = false;
  await newConversation();
  box.focus();
});

async function init() {
  try {
    const info = await api("/api/info");
    state.mode = info.mode;
    const badge = $("mode");
    badge.textContent = info.mode === "live" ? "Live" : "Replay";
    badge.title = info.mode === "live" ? "Answers come from the model now." : "Answers are recorded model replies, run again through the agent and its tools.";
    badge.classList.toggle("live", info.mode === "live");
    badge.hidden = false;
    const examples = $("examples");
    for (const q of info.examples) {
      const b = el("button", null, q);
      b.type = "button";
      b.addEventListener("click", () => ask(q));
      examples.append(b);
    }
    await newConversation();
  } catch (error) {
    thread.append(errorCard(`The server isn't reachable: ${error.message}`));
  }
}

init();
