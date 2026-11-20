"""The events the page gets while the agent answers, built from the agent's own step and trace dicts
(react.Conversation): nothing here calls the model or the database, so it's tested on saved traces alone.

An event is a dict with a "type" (queued, started, examples, thinking, tool_started, step, answer, error, done) and its
data. Every text that leaves the server goes through redact, which takes the model server's address out of it.
"""

import json
import os
import re
from urllib.parse import urlsplit

ORDINALS = ["first", "second", "third", "fourth", "fifth"]
TOP_WHAT = {1: "tournament wins", 3: "medals", 8: "top 8s"}
RANK_BY = {"wins": "tournament wins", "medals": "medals", "top8s": "top 8s"}
# What the page says while the model thinks, after a step a check sent back (the key is react's step key)
CHECK_LABELS = {
    "no_tool_check": "Double-checking: looking the facts up instead of answering from memory",
    "number_check": "Double-checking a number in the answer",
    "answer_check": "Double-checking a player the answer names",
    "lookup_check": "Checking why a lookup came back empty",
    "size_check": "The result was too big to read: narrowing it down",
}
NO_ANSWER = {
    "step limit": "No answer: the agent ran out of steps before it finished.",
    "cut off at the output cap": "No answer: the model's reply was cut off.",
    "empty reply": "No answer: the model sent an empty reply.",
    "tool call in the reply text, not parsed": "No answer: the model wrote a tool call the agent couldn't read.",
}


def secrets():
    """The texts never to send: the model server's address, and its host:port alone."""
    url = os.environ.get("OLLAMA_BASE_URL", "").strip().rstrip("/")
    if not url:
        return []
    found = [url]
    parts = urlsplit(url)
    if parts.netloc:
        found.append(parts.netloc)
    if parts.hostname:
        found.append(parts.hostname)
    return found


def redact(value):
    """A value with every secret text replaced, in strings nested anywhere inside it."""
    hidden = secrets()
    if not hidden:
        return value
    if isinstance(value, str):
        for text in hidden:
            value = value.replace(text, "[model server]")
        return value
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    return value


def arguments_of(call):
    """A tool call's arguments as a dict (the model sometimes sends them as JSON text)."""
    arguments = call.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return {"text": arguments}
    return arguments if isinstance(arguments, dict) else {}


def quoted(value):
    return f"“{value}”" if isinstance(value, str) and value.strip() else "(not given)"


def player_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def scope(arguments):
    """' in 2v2 in 2024 at “bcx”': a template's filters, as words."""
    parts = []
    if arguments.get("mode"):
        parts.append(f" in {arguments['mode']}")
    if arguments.get("year"):
        parts.append(f" in {arguments['year']}")
    if arguments.get("event"):
        parts.append(f" at {quoted(arguments['event'])}")
    return "".join(parts)


def tool_label(name, arguments, names=None):
    """What the page says while a tool runs: 'Figuring out who “boomie” is', 'Finding the set history between megD and
    Raydish'. names maps the player IDs the conversation has seen to their names; an unknown one is "a player"."""
    arguments = arguments if isinstance(arguments, dict) else {}
    names = names or {}

    def who(key):
        return names.get(player_id(arguments.get(key))) or "a player"

    top = player_id(arguments.get("top"))
    if name == "resolve_player":
        return f"Figuring out who {quoted(arguments.get('name'))} is"
    if name == "resolve_event":
        return f"Figuring out which event {quoted(arguments.get('name') or arguments.get('event'))} means"
    if name == "run_sql":
        return "Querying the database"
    if name == "event_results":
        what = "the winners of" if top == 1 else f"the top {top} of" if top else "the results of"
        return f"Getting {what} {quoted(arguments.get('event'))}"
    if name == "player_results":
        return f"Getting {who('player_id')}'s {TOP_WHAT.get(top, 'results')}{scope(arguments)}"
    if name == "head_to_head":
        return f"Finding the set history between {who('player_id')} and {who('opponent_id')}"
    if name == "rank_players":
        return f"Ranking players by {RANK_BY.get(arguments.get('by'), 'results')}{scope(arguments)}"
    return f"Calling {name}"


def observed(call):
    """A recorded call's observation as a dict (traces keep it as JSON text)."""
    value = call.get("observation")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def player_names(step, names):
    """Adds every player a step's tool results named (a dict with a player_id and a name) to names."""
    def walk(value):
        if isinstance(value, dict):
            pid, name = player_id(value.get("player_id")), value.get("name")
            if pid is not None and isinstance(name, str) and name:
                names.setdefault(pid, name)
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
    for call in step.get("tool_calls") or []:
        walk(observed(call))
    return names


def thinking_label(number, previous):
    """What the page says while the model thinks: what it's doing with the step before."""
    if number == 1 or not previous:
        return "Reading your question"
    for key, label in CHECK_LABELS.items():
        if str((previous.get(key) or {}).get("action") or "").startswith("sent back"):
            return label
    calls = previous.get("tool_calls") or []
    if not calls:
        return "Thinking it over"
    if any("error" in observed(c) for c in calls):
        return "Fixing a lookup that didn't work"
    if all(c.get("name") in ("resolve_player", "resolve_event") for c in calls):
        return "Working out what to look up next"
    return "Reading the results"


def tool_started(step, name, arguments, names=None):
    return {"type": "tool_started", "step": step, "tool": name, "label": tool_label(name, arguments, names)}


def thinking(step, previous=None):
    return {"type": "thinking", "step": step, "label": thinking_label(step, previous)}


def short_thought(text, width=240):
    """A step's thinking in short: its last sentences, where the model settles what to do next (as ask.thought)."""
    text = " ".join((text or "").split())
    kept = ""
    for sentence in reversed(re.split(r"(?<=[.!?])\s+", text)):
        if kept and len(sentence) + 1 + len(kept) > width:
            break
        kept = f"{sentence} {kept}".strip()
    kept = kept[-width:]
    return kept if kept == text else "... " + kept


def table(what, columns, rows, row_count=None, note=None):
    """One table as the page shows it. rows is None when the model wasn't shown them."""
    return {"what": what, "columns": columns, "rows": rows, "row_count": len(rows) if row_count is None else row_count,
            "note": note}


def candidate_rows(candidates):
    return [[c.get("player_id"), c.get("display") or c.get("name"), c.get("matched"), c.get("match"), c.get("score"),
             c.get("official_results"), c.get("results_from"), c.get("results_to")] for c in candidates]


def shown_result(name, observation):
    """A tool's observation as the page shows it: a status line, notes and tables."""
    if observation is None:
        return {"kind": "not run", "status": "Not run: no steps were left.", "notes": [], "tables": []}
    if "error" in observation:
        return {"kind": "error", "status": observation["error"], "notes": [], "tables": []}
    if "tables" in observation:  # a template
        tables = [table(t["what"], t["columns"], t.get("rows"), t.get("row_count"), t.get("note"))
                  for t in observation["tables"]]
        return {"kind": "template", "status": observation.get("scope"), "notes": observation.get("notes", []),
                "tables": tables}
    if name == "resolve_player":
        columns = ["player_id", "name", "matched", "match", "score", "official results", "from", "to"]
        return {"kind": "player", "status": f"{observation.get('status')}: {observation.get('note') or ''}".strip(" :"),
                "notes": [], "tables": [table("candidates", columns, candidate_rows(observation.get("candidates", [])))]}
    if name == "resolve_event":
        events = observation.get("events") or []
        columns = list(events[0]) if events else []
        rows = [[e.get(c) for c in columns] for e in events]
        status = f"{observation.get('status')}: {observation.get('event_count', 0)} events, {observation.get('matched')}"
        return {"kind": "event", "status": status, "notes": [n for n in [observation.get("note")] if n],
                "tables": [table("events", columns, rows, observation.get("event_count"))], "sql": observation.get("sql")}
    # run_sql
    rows = observation.get("rows")
    note = None
    if rows is None:
        note = "Too large to show the model: it got the row count and columns only."
    if observation.get("diagnosis"):
        note = observation["diagnosis"].get("note")
    return {"kind": "query", "status": f"{observation.get('row_count', 0)} rows", "notes": [],
            "tables": [table("result", observation.get("columns", []), rows, observation.get("row_count"), note)]}


def shown_call(call):
    name, arguments = call.get("name"), arguments_of(call)
    observation = None
    if call.get("observation") is not None:
        try:
            observation = json.loads(call["observation"])
        except ValueError:
            observation = {"error": call["observation"]}
    sql = [arguments["query"]] if name == "run_sql" and isinstance(arguments.get("query"), str) else list(call.get("ran") or [])
    return {"tool": name, "arguments": arguments, "sql": sql, "seconds": call.get("seconds"),
            "refused": bool(call.get("unreturned_players")), "result": shown_result(name, observation)}


CHECKS = {
    "size_check": "Result-size check",
    "lookup_check": "Lookup check",
    "no_tool_check": "No-tool check",
    "answer_check": "Answer check",
}


def step(raw):
    """A finished step (react.Conversation's on_step) as the page shows it in "How I got this"."""
    checks = [{"check": label, "action": raw[key].get("action"), "message": raw[key].get("message")}
              for key, label in CHECKS.items() if raw.get(key)]
    if raw.get("meta_reply"):
        checks.append({"check": "Reply about the answer", "action": raw["meta_reply"].get("action"), "message": None})
    return redact({"type": "step", "step": raw.get("step"), "seconds": raw.get("seconds"),
                   "thought": short_thought(raw.get("thinking")), "calls": [shown_call(c) for c in raw.get("tool_calls", [])],
                   "checks": checks, "name_swaps": raw.get("name_swaps", []), "suggested": bool(raw.get("suggestions"))})


def examples(found):
    if not found:
        return {"type": "examples", "examples": []}
    return {"type": "examples", "examples": [{"id": e.get("id"), "shape": e.get("shape"), "question": e.get("question")}
                                             for e in found.get("examples", [])]}


def listed(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def notes(trace):
    """What the checks let through without confirming: one plain sentence each, for the box above the answer."""
    found = []
    names, ids = trace.get("unreturned_names") or {}, trace.get("unreturned_ids") or []
    if names or ids:
        what = [f"“{n}”" for n in names] + [f"player ID {i}" for i in ids]
        found.append(f"Couldn't confirm: the answer names {listed(what)}, which the data lookups didn't return.")
    if trace.get("answered_after_too_big"):
        found.append("Couldn't confirm: the answer came after a result too large to read, so its counts may come from"
                     " partial data.")
    if trace.get("answered_after_lookup_miss"):
        conditions = [c for s in trace.get("steps", []) for c in (s.get("lookup_check") or {}).get("conditions", [])]
        what = listed([f"a row with {c}" for c in dict.fromkeys(conditions)]) if conditions else "what it looked for"
        found.append(f"Couldn't confirm: a lookup found no {what}, so a “none” here may be a lookup mistake.")
    if trace.get("answered_without_tools"):
        found.append("Couldn't confirm: the answer states facts without looking them up in the data.")
    return found


def suggestions(trace):
    """For an answer that asks which player a name meant: each unsure name's candidates as buttons, and the reply each
    sends, its ordinal ("the first one"): names repeat, so the name alone could mean another player."""
    if trace.get("outcome") != "suggestions":
        return []
    last = trace["steps"][-1]
    asked = last.get("suggestions") or {}
    observed = {}
    for call in last.get("tool_calls", []):
        if call.get("name") == "resolve_player" and call.get("observation"):
            data = json.loads(call["observation"])
            observed[data.get("name")] = {c["player_id"]: c for c in data.get("candidates", [])}
    groups = []
    for name, ids in asked.items():
        options = []
        for i, pid in enumerate(ids):
            c = observed.get(name, {}).get(pid, {})
            years = sorted({d[:4] for d in (c.get("results_from"), c.get("results_to")) if d})
            n = c.get("official_results")
            detail = ", ".join(x for x in [f"{n} official result{'' if n == 1 else 's'}" if n is not None else "",
                                           " to ".join(years)] if x)
            options.append({"label": c.get("display") or c.get("name") or f"player {pid}", "detail": detail,
                            "reply": f"the {ORDINALS[i]} one"})
        groups.append({"name": name, "options": options})
    return groups


def suggestion_reply(groups, chosen):
    """The message the Send button sends for one choice per unsure name: 'the first one', or with two names
    'the first one for markiemoo, the second one for godly'. chosen: {name: index}."""
    if len(groups) == 1:
        return groups[0]["options"][chosen[groups[0]["name"]]]["reply"]
    return ", ".join(f"{g['options'][chosen[g['name']]]['reply']} for {g['name']}" for g in groups)


def answer(trace):
    """The answer event: the text, the notes, the suggestion buttons, and what it took."""
    outcome = trace.get("outcome") or ""
    text = trace.get("answer")
    problem = None
    if outcome not in ("answered", "suggestions"):
        problem = NO_ANSWER.get(outcome) or (f"No answer: {outcome}." if outcome else "No answer.")
    return redact({"type": "answer", "text": text, "outcome": outcome, "problem": problem, "notes": notes(trace),
                   "suggestions": suggestions(trace), "name_swaps": trace.get("name_swaps", []),
                   "steps": trace.get("steps_used"),
                   "model_seconds": trace.get("model_seconds")})


def figures(cards):
    """The stat cards for an answer (figures.Cards), sent after it."""
    return redact({"type": "figures", "figures": cards})


def error(message):
    return {"type": "error", "message": redact(str(message))}
