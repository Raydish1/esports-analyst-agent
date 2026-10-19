"""A minimal ReAct prototype: a local model answers a question about the data with two tools, resolve_player and
run_sql (agent/tools.py), through Ollama's native tool calling.

    python agent/react.py "Who has megd played with in 2v2 tournaments?"
    python agent/react.py --target 4 --target 6 --target 8          target questions (ingest/target_questions.py)

Each step is one model reply: its thinking, then either tool calls, whose results go back as observations, or the
answer. A question ends at the answer, or after MAX_STEPS replies; the observation before the last step says it's
the last. An answer that names a player no tool returned goes back to the model once, with the names, before it
counts (Shown.unreturned). The model is qwen3:8b with thinking on, as decided for development (docs/experiments.md),
with its own sampling defaults and a fixed seed, as in the model comparison. The system prompt (SYSTEM) is the
comparison prompt's description of the views and its counting rules, with the name lookup replaced by resolve_player,
a section on the views that hold each pairing more than once, and how to use the tools and write the answer.

The console shows each step in short. Every step in full (thinking, reply, tool calls and observations, exactly as
sent) goes to data/experiments/<run>/traces.jsonl and traces.md (git-ignored). A run of target questions also writes
a summary without the thinking to eval/results/<run>-react-prototype.json.
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
from names import normalize, normalize_full  # noqa: E402
from platform_clients import load_env  # noqa: E402
from tools import SNAPSHOT, SQL_ROWS, SQL_SECONDS, Resolver, run_sql  # noqa: E402

MODEL = "qwen3:8b"
OPTIONS = {"num_ctx": 32768, "num_predict": 8192}  # plus the seed. The comparison's 16,384-token context is too small
# here: the server's qwen3 template keeps every step's thinking in the prompt until the answer
MAX_STEPS = 8
REQUEST_SECONDS = 900
RESULTS = ROOT / "eval" / "results"
RAW = ROOT / "data" / "experiments"

SYSTEM = """You answer questions about official Brawlhalla esports results (official events only, from 2017 on), using two
tools: resolve_player finds the player a name means, and run_sql queries a SQLite database of the results. Every
player_id in a view is a person's canonical ID.

Using the tools
- Call resolve_player for every player the question names, before any SQL, and use the player_id it returns, as a
  number, in your queries. Don't look names up in SQL (players.name or player_aliases): people write names in other
  cases and spellings, and use nicknames and former names, which the resolver knows.
  - "confident": use the first candidate.
  - "ambiguous": use the first candidate unless the question points to another, and say in your answer which player
    you took the name to mean.
  - "not_found": the data has no such player; say so.
- resolve_player takes names only, never IDs. To get the name of a player_id, query players with run_sql.
- run_sql runs one read-only SQLite query (a SELECT; WITH is fine) and returns at most {rows} rows, with the total
  row count. If it returns an error, fix the query and try again.
- To count or summarize (how many, how often, the most, the best), aggregate in SQL with GROUP BY and COUNT, SUM, MIN
  or MAX, rather than listing raw rows.
- A result of more than {rows} rows comes back incomplete ("complete": false), with only its first {rows} rows. Never
  answer from an incomplete result: aggregate, filter or limit in SQL, and query again.
- The views are fast when filtered by a literal player_id. With a lookup inside the query, the head-to-head views
  take a minute or more, and run_sql stops a query after {seconds} seconds.

Tables
- players(player_id, name, canonical_id): name is the current display name. To show players' names, join players
  on player_id.
- event_aliases(alias, event_id, note): names people use for events, in lowercase words, e.g. 'bcx 2022'. One alias
  can name several events (a tournament's 1v1 and 2v2).

Views
- v_events(event_id, tournament_name, event_name, start_date, start_time, mode, format, counts_as, status,
  bracket_url): every official event. counts_as is '1v1', '2v2' or NULL for side formats.
- v_results(player_id, event_id, competition_key, mode, format, placement, team_id, tournament_name, event_name,
  start_date, start_time, bracket_url): one result per person per competition that counts. mode is '1v1' or '2v2'.
- v_entries(player_id, event_id, tournament_name, event_name, start_date, start_time, format, mode, placement): every
  official event a person entered, side formats included (their mode is NULL).
- v_official_wins: the rows of v_results with placement = 1.
- v_medals: the rows of v_results with placement <= 3, plus medal ('gold', 'silver' or 'bronze').
- v_player_medals(player_id, mode, gold, silver, bronze, medals): medal counts per person and mode.
- v_team_results(player_id, partner_id, event_id, placement, tournament_name, event_name, start_date): 2v2 results,
  one row per person per partner per event.
- v_match_results(player_id, match_id, side, side_players, event_id, competition_key, mode, start_date, is_scored,
  games_won, games_lost, won): one row per person per counted match.
- v_head_to_head_1v1(player_id, opponent_id, wins, losses, matches, games_won, games_lost, unscored_matches): a
  person's 1v1 record against an opponent.
- v_head_to_head_2v2(player_id, partner_id, opponent1_id, opponent2_id, wins, losses, matches, games_won, games_lost,
  unscored_matches): a team's record against another team.
- v_win_runs(player_id, event_id, competition_key, tournament_name, event_name, start_date, mode, format,
  is_crew_battle, sets_played, sets_dropped, games_won, games_lost, unscored_sets, no_contests): each official win
  with the winner's run through it.

Views that hold each pairing more than once
- v_head_to_head_1v1 holds every pairing twice, once from each player's side. The row with player_id = A and
  opponent_id = B is A's record against B; the row with player_id = B and opponent_id = A is the same matches from
  B's side, with wins and losses swapped. Read one side: never add the two rows together.
  - A's record against B: WHERE player_id = A AND opponent_id = B.
  - Everyone's record against B: WHERE opponent_id = B. Each row's wins and losses are its player_id's against B.
- v_head_to_head_2v2 holds every pairing of teams four times, once for each of the four players. The record of the
  team A and B: WHERE player_id = A AND partner_id = B.
- v_team_results holds every 2v2 result twice, once from each partner's side. A's partners: WHERE player_id = A,
  read from partner_id.

Counting rules (the views already apply the first four)
- "Majors" means official events, and every event here is official.
- A medal is a 1st, 2nd or 3rd place.
- Crew battles count as 1v1. Other side formats (3v3, Triples, Brawlball, Kung Foot) count toward neither mode.
- DQs and forfeits count as neither a win nor a loss.
- The last event a player entered is their newest row in v_entries.
- The most dominant win has the fewest games_lost, then the fewest sets_dropped, then the most games_won. Runs with
  unscored_sets > 0 rank after fully scored ones, and crew battles (is_crew_battle = 1) are left out.
- The best record against someone is the highest win rate (wins / matches) among players with at least 5 matches
  against them.
- A first top 8 is the earliest result (by start_time) with placement <= 8.

Answering
- You have at most {steps} steps, and each reply is one. When you have what the answer needs, reply with the answer
  and no tool call.
- Answer in plain English, and give the main facts the question asks for, with the figures they rest on.
- Name players by their current display name, spelled as the data spells it: the name resolve_player or the players
  table returns, not the one the question used. Name only players a tool returned.
- State the scope: official events (say "official events", not "majors") and the mode, as in "at official events, in
  1v1".
- If resolve_player was ambiguous, say which player you took the name to mean, and that other players share or
  resemble the name.
- Say what else you assumed, such as what was counted."""

TOOLS = [
    {"type": "function", "function": {
        "name": "resolve_player",
        "description": "Find the player a name means. Give the name as the question writes it: any case or spelling, a"
                       " nickname, a former name or a team tag. Returns a status (confident, ambiguous or not_found)"
                       " and candidates, best first, each with the player_id to use in SQL and its number of official"
                       " results.",
        "parameters": {"type": "object", "required": ["name"], "properties": {
            "name": {"type": "string", "description": "the player's name as the question writes it"}}}}},
    {"type": "function", "function": {
        "name": "run_sql",
        "description": f"Run one read-only SQLite query (SELECT or WITH) on the results database. Returns the column"
                       f" names, at most {SQL_ROWS} rows and the total row count, or an error.",
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string", "description": "one SQLite SELECT statement"}}}}},
]
LAST_STEP = "You have one step left: reply with your answer, without calling a tool."
CHECK = ("Before this answer is final: it names {names}, which no tool returned in this conversation. If that means a"
         " player, find them with a tool first (resolve_player for a name, run_sql for a player_id) and answer from what"
         " the tools return. If it isn't meant as a player, reply with the same answer again.")
NUMBERISH = re.compile(r"\d+(?:st|nd|rd|th|s|v\d+)?")  # numbers, ordinals and formats, normalized: 7th, 2v2, 1990s


# Talking to the model

def ollama(path, payload=None, timeout=60):
    """A request to the Ollama server, as parsed JSON."""
    url = os.environ["OLLAMA_BASE_URL"].rstrip("/") + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def chat(messages, model=MODEL, think=True, seed=0):
    """One model reply, with the tools offered: the server's /api/chat response."""
    return ollama("/api/chat", {"model": model, "stream": False, "think": think, "tools": TOOLS, "messages": messages,
                                "options": {**OPTIONS, "seed": seed}}, timeout=REQUEST_SECONDS)


class Tools:
    """The tools the model can call, by name, on one snapshot."""

    def __init__(self, path=SNAPSHOT):
        self.path = path
        db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            self.resolver = Resolver(db)
        finally:
            db.close()

    def call(self, name, arguments):
        """One tool call's observation, as a dict: its result, or an error the model can act on."""
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                pass
        arguments = arguments if isinstance(arguments, dict) else {}
        if name == "resolve_player":
            value = arguments.get("name")
            if isinstance(value, str) and value.strip():
                return self.resolver.resolve(value)
            return {"error": "resolve_player takes one argument, name: the player's name as the question writes it"}
        if name == "run_sql":
            value = arguments.get("query")
            if isinstance(value, str) and value.strip():
                return run_sql(value, self.path)
            return {"error": "run_sql takes one argument, query: one SQLite SELECT statement"}
        return {"error": f"there is no tool named {name!r}: the tools are resolve_player and run_sql"}


# The answer check

def name_spans(answer):
    """Where an answer may name a player, told apart from ordinary words without a dictionary: words shaped like gamer
    tags (letters with digits, an underscore, or a capital inside: tike36, V3M_T4NQUIL0, megD), and bold text of up to
    three words that isn't a label (**Raydish**, not **Notes:**), with a possessive 's dropped. A plain name outside
    bold, such as Raydish, isn't found: most ordinary words are some player's display name ('best', 'me', 'Winter')."""
    spans = []
    for token in answer.split():
        word = re.sub(r"['’]s$", "", token.strip("*_`'\"()[]{}.,;:!?’"))
        if re.search(r"[A-Za-z]", word) and re.search(r"\d|_|[a-z][A-Z]", word):
            spans.append(word)
    for text in re.findall(r"\*\*(.+?)\*\*", answer):
        text = re.sub(r"['’]s$", "", text.strip())
        if text and not text.endswith(":") and len(text.split()) <= 3:
            spans.append(text)
    return spans


class Shown:
    """What a question's conversation has shown the model: every word of the prompt, the question and the
    observations, and the players the tools returned (resolve_player's candidates, and any player ID in a query
    result)."""

    def __init__(self, resolver, *texts):
        self.resolver, self.words, self.players = resolver, set(), set()
        for text in texts:
            self.read(text)

    def read(self, text):
        tokens = str(text).split()
        for n in (1, 2, 3):  # names of up to three words, such as 'Titanium wrath09' or 'SiB | Wess'
            for i in range(len(tokens) - n + 1):
                span = " ".join(tokens[i:i + n])
                self.words |= {normalize(span), normalize_full(span)} - {""}

    def observe(self, name, observation):
        self.read(json.dumps(observation, ensure_ascii=False))
        if name == "resolve_player":
            self.players |= {c["player_id"] for c in observation.get("candidates", ())}
        canonical = self.resolver.canonical
        for row in observation.get("rows", ()):
            self.players |= {canonical[v] for v in row if isinstance(v, int) and v in canonical}

    def unreturned(self, answer):
        """The names in an answer (name_spans) that are only the current names of players no tool returned:
        {name: [player IDs]}. Numbers, ordinals and words the conversation already showed don't count."""
        found = {}
        for span in name_spans(answer):
            key = normalize(span)
            if len(key) < 2 or NUMBERISH.fullmatch(key) or key in self.words or normalize_full(span) in self.words:
                continue
            players = self.resolver.called(span)
            if players and not players & self.players:
                found[span] = sorted(players)[:5]
        return found


# The loop

def ending(content, done_reason):
    """How a reply without tool calls ends the question."""
    if done_reason == "length":
        return "cut off at the output cap"
    if "<tool_call>" in content:
        return "tool call in the reply text, not parsed"
    return "answered" if content.strip() else "empty reply"


def run(question, tools, ask=chat, max_steps=MAX_STEPS, log=print, **model):
    """Answer one question. The trace: each step's thinking, reply and tool calls with their observations, and any
    answer check; then the answer, the outcome ('answered', 'step limit', ...) and the names in the answer that no tool
    returned. An answer naming such players goes back once, if a step is left; the next answer counts either way."""
    messages = [{"role": "system", "content": SYSTEM.format(rows=SQL_ROWS, seconds=SQL_SECONDS, steps=max_steps)},
                {"role": "user", "content": question}]
    trace = {"question": question, "steps": [], "answer": None, "outcome": None, "unreturned_names": {}}
    shown, checked = Shown(tools.resolver, messages[0]["content"], question, json.dumps(TOOLS)), False
    for number in range(1, max_steps + 1):
        begun = time.monotonic()
        try:
            reply = ask(messages, **model)
        except (urllib.error.URLError, TimeoutError) as e:
            body = e.read().decode("utf-8", "replace")[:300] if isinstance(e, urllib.error.HTTPError) else ""
            trace["outcome"] = f"request error at step {number}: {e} {body}".strip()
            log(f"  {trace['outcome']}")
            break
        message = reply.get("message") or {}
        thinking, content, calls = message.get("thinking") or "", message.get("content") or "", message.get("tool_calls") or []
        step = {"step": number, "seconds": round(time.monotonic() - begun, 2), "prompt_tokens": reply.get("prompt_eval_count"),
                "cached_tokens": reply.get("prompt_eval_cached_count"), "output_tokens": reply.get("eval_count"),
                "done_reason": reply.get("done_reason"), "thinking": thinking, "content": content, "tool_calls": []}
        trace["steps"].append(step)
        log(f"  step {number}: {step['seconds']:.1f} s, {step['output_tokens']} tokens, thinking {len(thinking):,} characters")
        if not calls:
            outcome = ending(content, step["done_reason"])
            names = shown.unreturned(content) if outcome == "answered" else {}
            if names and not checked and number < max_steps:
                checked, message = True, CHECK.format(names=" and ".join(f"'{n}'" for n in names))
                if number == max_steps - 1:
                    message += " " + LAST_STEP
                step["answer_check"] = {"names": names, "action": "sent back", "message": message}
                messages += [{"role": "assistant", "content": content, "thinking": thinking},
                             {"role": "user", "content": message}]
                log(f"  answer check: {', '.join(names)} named, but no tool returned them; sent back")
                continue
            if names:
                step["answer_check"] = {"names": names, "action": "kept: sent back once already" if checked
                                        else "kept: no steps left"}
            trace["answer"], trace["outcome"], trace["unreturned_names"] = content.strip() or None, outcome, names
            log(f"  {trace['outcome']}: {short(content, 300)}")
            break
        if number == max_steps:
            step["tool_calls"] = [{"name": c["function"].get("name"), "arguments": c["function"].get("arguments"),
                                   "observation": None} for c in calls]
            trace["outcome"] = "step limit"
            log(f"  step limit: {len(calls)} more tool calls not run")
            break
        # The server's qwen3 template shows an assistant message's tool calls only when its content is empty, so any
        # text beside them (kept in the trace) stays out of the history
        messages.append({"role": "assistant", "content": "", "thinking": thinking, "tool_calls": calls})
        for i, call in enumerate(calls):
            name, arguments = call["function"].get("name"), call["function"].get("arguments")
            begun = time.monotonic()
            observation = tools.call(name, arguments)
            seconds = time.monotonic() - begun
            shown.observe(name, observation)
            if number == max_steps - 1 and i == len(calls) - 1:
                observation = {**observation, "last_step": LAST_STEP}
            text = json.dumps(observation, ensure_ascii=False)
            step["tool_calls"].append({"name": name, "arguments": arguments, "observation": text, "seconds": round(seconds, 3)})
            messages.append({"role": "tool", "tool_name": name, "content": text})
            log(f"    {name}({short(json.dumps(arguments, ensure_ascii=False), 160)}) -> {short(text, 200)}")
    trace["steps_used"] = len(trace["steps"])
    trace["model_seconds"] = round(sum(s["seconds"] for s in trace["steps"]), 1)
    trace["tool_seconds"] = round(sum(c.get("seconds") or 0 for s in trace["steps"] for c in s["tool_calls"]), 1)
    trace["output_tokens"] = sum(s["output_tokens"] or 0 for s in trace["steps"])
    trace["largest_context"] = max(((s["prompt_tokens"] or 0) + (s["output_tokens"] or 0) for s in trace["steps"]), default=0)
    return trace


def short(text, width):
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[:width] + "..."


# Writing the traces

def markdown(traces, header):
    """The traces, readable: each question's steps in full."""
    out = [f"# ReAct prototype traces: run {header['run']}", "",
           f"{header['model']} ({header['variant']}), thinking {'on' if header['think'] else 'off'}, seed {header['seed']};"
           f" snapshot {header['snapshot']['file']} (build {header['snapshot'].get('build_id')}); at most"
           f" {header['max_steps']} steps. Ollama {header['ollama']}.", ""]
    for t in traces:
        title = f"Question {t['number']}: {t['question']}" if t.get("number") else t["question"]
        out += [f"## {title}", "", f"**Outcome:** {t['outcome']}, {t['steps_used']} steps, {t['model_seconds']} s of model"
                f" time, {t['output_tokens']:,} output tokens, largest context {t['largest_context']:,} tokens.", ""]
        for s in t["steps"]:
            out += [f"### Step {s['step']}", "", f"{s['seconds']} s; prompt {s['prompt_tokens']} tokens ({s['cached_tokens']}"
                    f" cached), output {s['output_tokens']}; done: {s['done_reason']}.", "", "**Thinking**", "",
                    "```text", s["thinking"].strip() or "(none)", "```", ""]
            if s["content"].strip() and s["tool_calls"]:
                out += ["**Reply text beside the tool calls**", "", s["content"].strip(), ""]
            check = s.get("answer_check")
            if check:
                names = ", ".join(f"{n} ({', '.join(map(str, ids))})" for n, ids in check["names"].items())
                if check["action"] == "sent back":
                    out += ["**Reply**", "", s["content"].strip(), "", f"**Answer check:** it names {names}, which no tool"
                            " returned. Sent back with:", "", f"> {check['message']}", ""]
                else:
                    out += [f"**Answer check:** it names {names}, which no tool returned ({check['action']}).", ""]
            for c in s["tool_calls"]:
                args = c["arguments"]
                text = args.get("query") if c["name"] == "run_sql" and isinstance(args, dict) and "query" in args else json.dumps(args, ensure_ascii=False)
                out += [f"**Tool call:** `{c['name']}`", "", f"```{'sql' if c['name'] == 'run_sql' else 'json'}", str(text).strip(), "```", ""]
                if c["observation"] is None:
                    out += ["**Observation:** not run (step limit)", ""]
                else:
                    pretty = json.dumps(json.loads(c["observation"]), indent=1, ensure_ascii=False)
                    out += [f"**Observation** ({c['seconds']} s)", "", "```json", pretty, "```", ""]
        if t["answer"]:
            out += ["### Answer" if t["outcome"] == "answered" else f"### Last reply ({t['outcome']})", "", t["answer"], ""]
    return "\n".join(out)


def preview(observation, width=200):
    """A tool call's observation, in short, for the summary."""
    if observation is None:
        return "not run (step limit)"
    data = json.loads(observation)
    if "error" in data:
        return f"error: {data['error']}"
    if "status" in data:
        return f"{data['status']}: " + ", ".join(f"{c['player_id']} {c['name']}" for c in data["candidates"])
    rows = f"{data['row_count']} rows" + ("" if data.get("complete", True) else f", incomplete ({len(data['rows'])} shown)")
    text = f"{rows}: {json.dumps(data['rows'][:3], ensure_ascii=False)}"
    return text if len(text) <= width else text[:width] + "..."


def summary(trace):
    keep = ("number", "question", "outcome", "answer", "unreturned_names", "steps_used", "model_seconds",
            "tool_seconds", "output_tokens", "largest_context")
    calls = [{"step": s["step"], "name": c["name"], "arguments": c["arguments"], "result": preview(c["observation"])}
             for s in trace["steps"] for c in s["tool_calls"]]
    checks = [{"step": s["step"], "names": s["answer_check"]["names"], "action": s["answer_check"]["action"]}
              for s in trace["steps"] if s.get("answer_check")]
    return {**{k: trace.get(k) for k in keep}, "tool_calls": calls, "answer_checks": checks}


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="A minimal ReAct prototype: a local model answers questions with"
                                                 " resolve_player and run_sql, on the snapshot eval-v1.")
    parser.add_argument("question", nargs="*", help="a question (each argument is one)")
    parser.add_argument("--target", action="append", type=int, help="a target question's number (repeatable)")
    parser.add_argument("--model", default=MODEL, help=f"the model (default: {MODEL})")
    parser.add_argument("--think", choices=["on", "off"], default="on", help="thinking (default: on)")
    parser.add_argument("--seed", type=int, default=0, help="the sampling seed (default: 0)")
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS, help=f"model replies per question (default: {MAX_STEPS})")
    args = parser.parse_args()
    from target_questions import QUESTIONS  # in ingest/, on the path
    targets = {number: text for number, text, _, _ in QUESTIONS}
    unknown = [n for n in args.target or [] if n not in targets]
    if unknown or not (args.question or args.target):
        parser.error(f"no target question {unknown[0]}" if unknown else "give a question or --target N")
    asked = [(n, targets[n]) for n in args.target or []] + [(None, q) for q in args.question]
    load_env()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = sqlite3.connect(SNAPSHOT.resolve().as_uri() + "?mode=ro", uri=True)
    build = dict(snapshot.execute("SELECT key, value FROM build_info WHERE key IN ('build_id', 'code_commit')"))
    snapshot.close()
    info = ollama("/api/show", {"model": args.model}).get("model_info", {})
    header = {"run": run_id, "ollama": ollama("/api/version")["version"], "model": args.model,
              "variant": " ".join(str(info[k]) for k in ("general.basename", "general.size_label") if info.get(k)),
              "think": args.think == "on", "seed": args.seed, "options": OPTIONS, "max_steps": args.max_steps,
              "sql_seconds": SQL_SECONDS, "sql_rows": SQL_ROWS,
              "snapshot": {"file": SNAPSHOT.relative_to(ROOT).as_posix(), **build}}
    print(f"Run {run_id}: {args.model}, thinking {args.think}, seed {args.seed}, at most {args.max_steps} steps;"
          f" Ollama {header['ollama']}; snapshot build {build.get('build_id')}")
    tools = Tools()
    traces = []
    for number, question in asked:
        print(f"\n{'Q' + str(number) + ': ' if number else ''}{question}")
        trace = run(question, tools, max_steps=args.max_steps, model=args.model, think=header["think"], seed=args.seed)
        traces.append({"number": number, **trace})
    out = RAW / run_id
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "traces.jsonl", "w", encoding="utf-8") as f:
        for trace in traces:
            f.write(json.dumps({**header, **trace}, ensure_ascii=False) + "\n")
    (out / "traces.md").write_text(markdown(traces, header) + "\n", encoding="utf-8")
    print(f"\nTraces: data/experiments/{run_id}/traces.md and traces.jsonl")
    if args.target:
        prompt = SYSTEM.format(rows=SQL_ROWS, seconds=SQL_SECONDS, steps=args.max_steps)
        RESULTS.mkdir(parents=True, exist_ok=True)
        path = RESULTS / f"{run_id}-react-prototype.json"
        path.write_text(json.dumps({
            **header, "kind": "exploratory: the ReAct prototype on target questions (expected answers from our own"
                              " data; not the formal baseline)",
            "system_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16], "system_prompt": prompt,
            "tools": TOOLS, "records": [summary(t) for t in traces]}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Summary: {path.relative_to(ROOT).as_posix()}")
    for t in traces:
        print(f"  {'Q' + str(t['number']) if t['number'] else 'question'}: {t['outcome']} in {t['steps_used']} steps,"
              f" {t['model_seconds']} s")


if __name__ == "__main__":
    main()
