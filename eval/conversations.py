"""Multi-turn test conversations: what a user typed in the web app, played through react.Conversation as the web app
plays it, every turn scored by automatic checks (eval/questions/conversations.toml has the set and documents the
checks). The evaluation set and its harness (eval/harness.py) ask one question at a time; these measure what goes
wrong across turns, as testing the web app's live mode found (docs/web-app-testing-notes.md on claude/web-app,
2026-11-19): facts stated without a tool call, a reply to suggestions answered as another question, a follow-up
asked back.

    python eval/conversations.py review                   the page to verify the set from (conversations-review.md)
    py -3.14 eval/conversations.py run --seeds 0 1 2      every conversation, retrieval on (a run resumes)
    python eval/conversations.py score RUN                each turn's checks: eval/results/<run>-conversations.json
    python eval/conversations.py report RUN [RUN ...]     each turn's result per seed, a column per run

--set FILE plays and scores another set in the same format. With `heldout = true` in it, a held-out set, nothing
these commands print or write outside the run's traces holds its text: only its ids, turn numbers and check names.

A turn's checks read its window, what its model had in front of it: this turn's tool results and the previous
turn's, as react.Conversation keeps older turns as question and answer only (decided 2026-11-19). Scoring reads the
traces only, so a corrected check needs no rerun.
"""

import argparse
import http.client
import json
import re
import sqlite3
import sys
import time
import tomllib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT / "eval"))
import harness  # noqa: E402
import react  # noqa: E402
from number_check import Evidence, claims, stated  # noqa: E402
from result_checks import CHECKS as QUESTION_CHECKS, matches  # noqa: E402
from review_questions import flat, table  # noqa: E402
from tools import connect  # noqa: E402

SET = ROOT / "eval" / "questions" / "conversations.toml"
REVIEW = ROOT / "eval" / "questions" / "conversations-review.md"
QUESTIONS = ROOT / "eval" / "questions" / "questions.toml"
LONE_ID = re.compile(r"\bplayer\s*#?\s*\d{4,}\b|\*\*-?\d{5,}\*\*", re.I)  # "Player 147569", "**147569**"
QUERY_SECONDS = 120
VERDICTS = ("yes", "no", "partly")
DEFAULTS = {"grounded": True, "named": True}  # the checks every turn gets unless it turns them off


# The set

def load(path=SET):
    with open(path, "rb") as f:
        return tomllib.load(f)


def problems(data):
    """What's wrong with a set itself, as sentences: written without its text, so a held-out set's can be shown."""
    out, conversations = [], data.get("conversation", [])
    ids = Counter(c.get("id") for c in conversations)
    out += [f"{i}: the id is used {n} times" for i, n in ids.items() if n > 1]
    for c in conversations:
        name = c.get("id", "?")
        out += [f"{name}: no {field}" for field in ("id", "title", "turn") if not c.get(field)]
        verdict = str(c.get("verified", "")).strip().lower()
        if verdict and not verdict.startswith(VERDICTS):
            out.append(f"{name}: verified should be empty, or start with yes, no or partly")
        for n, turn in enumerate(c.get("turn", []), 1):
            where = f"{name} turn {n}"
            out += [f"{where}: no {field}" for field in ("say", "expect") if not str(turn.get(field, "")).strip()]
            out += [f"{where}: no check named {key!r}" for key in turn if key not in CHECKS and key not in
                    ("say", "expect", "query", "shown")]
            if turn.get("check") and QUESTION_CHECKS.get(turn["check"]) is None:
                out.append(f"{where}: check names {turn['check']!r}, which has no stage 2 check")
            out += [f"{where}: a query has no sql" for q in turn.get("query", []) if not q.get("sql")]
    return out


# A turn's window

def ran(call):
    """Whether a tool call ran: not refused by a check before it ran, and not an error."""
    return (call["observation"] is not None and not call.get("unreturned_players") and not call.get("name_filters")
            and "error" not in json.loads(call["observation"]))


@dataclass
class Turn:
    """A turn of a played conversation, as its checks read it: the trace, and the previous turn's."""
    trace: dict
    previous: dict | None
    names: dict  # player_id -> name, for a player_id to count as its name

    @property
    def answer(self):
        return self.trace.get("answer") or ""

    @property
    def window(self):
        return [t for t in (self.previous, self.trace) if t]

    @cached_property
    def results(self):
        """The window's results as rows (harness.results): its queries', its templates' tables, resolve_event's."""
        return harness.results({"steps": [s for t in self.window for s in t["steps"]]}, self.names)

    @cached_property
    def text(self):
        return " ".join(c["observation"] for t in self.window for s in t["steps"] for c in s["tool_calls"]
                        if c["observation"]).casefold()

    @cached_property
    def evidence(self):
        """What the number check may cite in this turn's answer: the window's tool results and both questions."""
        found = Evidence()
        for t in self.window:
            found.ask(t["question"])
            for step in t["steps"]:
                for c in step["tool_calls"]:
                    if c["observation"] is not None:
                        observation = json.loads(c["observation"])
                        found.observe(observation)
                        if "error" not in observation:
                            found.call(c["arguments"])
        return found

    @cached_property
    def used(self):
        """The player_ids the turn's queries and template calls that ran use."""
        statements = [sql for name, _, _, sqls in harness.query_calls({"steps": [
            {**s, "tool_calls": [c for c in s["tool_calls"] if ran(c)]} for s in self.trace["steps"]]})
            for sql in sqls]
        return set().union(*map(harness.numbers, statements)) if statements else set()


def holds(row, pattern):
    """Whether a row holds every value of a pattern, a list in it being alternatives (result_checks.matches)."""
    return all(any(matches(alt, cell) for alt in (v if isinstance(v, list) else [v]) for cell in row) for v in pattern)


def held(turn, patterns):
    return [p for p in patterns if not any(holds(row, p) for rows in turn.results for row in rows)]


def folded(text):
    return " ".join(str(text).replace("*", "").split()).casefold()


def stated_numbers(answer):
    """The numbers an answer states (number_check.claims), as whole numbers: '5 sets', '2-3', 'five'. What it asks
    and its code don't count (number_check.stated), as for the agent's checks."""
    found = set()
    for c in claims(stated(answer)):
        if c.kind == "word":
            found.add(c.value[0])
        elif c.kind in ("number", "ordinal", "record", "scope", "category"):
            found |= {int(n) for n in re.findall(r"\d+", c.text)}
    return found


def grounded(turn, on):
    if not on or turn.trace.get("outcome") == "suggestions" or not turn.answer:
        return True, ""
    numbers = [c.text for c in turn.evidence.unsupported(turn.answer)]
    ids = [str(n) for n in react.cited_ids(stated(turn.answer)) if float(abs(n)) not in turn.evidence.values]
    bad = numbers + [f"player_id {i}" for i in ids if i not in numbers]
    return not bad, f"not in the window: {', '.join(bad)}" if bad else ""


def suggested(turn, player_id):
    offered = [ids for s in turn.trace["steps"] for ids in (s.get("suggestions") or {}).values()]
    first = offered[0][0] if offered and offered[0] else None
    return turn.trace.get("outcome") == "suggestions" and first == player_id, f"suggested {first} first" if offered else "no suggestions"


def missing_texts(turn, texts, where):
    found = [t for t in texts if folded(t) not in where]
    return not found, f"missing {', '.join(map(repr, found))}" if found else ""


def not_looked_up(turn, words):
    """Whether no resolve_player or resolve_event call of the turn, the loop's own lookups included, was given a name
    holding one of these words: live, the loop looked up "two" as a player and "say cody travis 24" as an event
    (docs/web-app-testing-notes.md, findings 10 and 14)."""
    bad = []
    for step in turn.trace["steps"]:
        for c in step["tool_calls"]:
            arguments = c["arguments"] if isinstance(c["arguments"], dict) else {}
            name = str(arguments.get("name") or arguments.get("event") or "")
            if c["name"] in ("resolve_player", "resolve_event") and {folded(w) for w in words} & set(folded(name).split()):
                bad.append(f"{c['name']}({name!r})")
    return not bad, f"looked up {', '.join(bad)}" if bad else ""


WON_LOST = re.compile(r"\b(?:w[oi]n(?:s|ning)?|lost|los(?:s|ses|ing))\b")


def says_record(turn, spec):
    """Whether one sentence or list item of the answer has one of spec's `about` words and states its `record` [a, b]:
    'a-b' (or with a dash), or a, then b, with a word for winning or losing. c3 turn 2's right answers wrote the 2v2
    record as "won 2 sets, lost 3 sets" and "2 wins, 3 losses", and a wrong one restated the 1v1 record, whose sets
    hold a 2 and a 3 too (decided 2026-11-20). What the answer asks and its code don't count (number_check.stated)."""
    a, b = map(str, spec["record"])
    for piece in re.split(r"(?<=[.!?])\s+|\n", re.sub(r"[*_`]", "", stated(turn.answer)).casefold()):
        if not any(word.casefold() in piece for word in spec["about"]):
            continue
        if re.search(rf"(?<![\w.]){a}\s*[-–—]\s*{b}(?!\w|\.\d)", piece):
            return True, ""
        numbers = re.findall(r"(?<![\w.])\d+(?!\w|\.\d)", re.sub(r"\b\d+v\d+\b", " ", piece))
        if a in numbers and b in numbers[numbers.index(a) + 1:] and WON_LOST.search(piece):
            return True, ""
    return False, f"no sentence about {' or '.join(map(repr, spec['about']))} states {a}-{b}"


CHECKS = {  # name -> (turn, the value in the set) -> (passed, detail): what each checks is in conversations.toml
    "rows": lambda t, ps: (lambda bad: (not bad, f"no row holds {bad}" if bad else ""))(held(t, ps)),
    "rows_any": lambda t, ps: (len(held(t, ps)) < len(ps), "no row holds any of them"),
    "window_has": lambda t, texts: missing_texts(t, texts, t.text),
    "check": lambda t, qid: (bool(QUESTION_CHECKS[qid](t.results)), f"{qid}'s stage 2 check"),
    "calls": lambda t, names: (lambda bad: (not bad, f"didn't call {', '.join(bad)}" if bad else ""))(
        [n for n in names if n not in harness.tool_calls(t.trace)]),
    "not_calls": lambda t, names: (lambda bad: (not bad, f"called {', '.join(bad)}" if bad else ""))(
        [n for n in names if n in harness.tool_calls(t.trace)]),
    "not_looked_up": not_looked_up,
    "players": lambda t, ids: (lambda bad: (not bad, f"didn't use {bad}" if bad else ""))(
        [i for i in ids if i not in t.used]),
    "not_players": lambda t, ids: (lambda bad: (not bad, f"used {bad}" if bad else ""))([i for i in ids if i in t.used]),
    "suggests": suggested,
    "says": lambda t, texts: missing_texts(t, texts, folded(t.answer)),
    "says_any": lambda t, texts: (any(folded(x) in folded(t.answer) for x in texts), "says none of them"),
    "not_says": lambda t, texts: (lambda bad: (not bad, f"says {', '.join(map(repr, bad))}" if bad else ""))(
        [x for x in texts if folded(x) in folded(t.answer)]),
    "says_numbers": lambda t, ns: (lambda bad: (not bad, f"doesn't state {bad}" if bad else ""))(
        [n for n in ns if n not in stated_numbers(t.answer)]),
    "says_record": says_record,
    "unconfirmed_at_most": lambda t, n: (lambda k: (k <= n, f"{k} claims replaced" if k > n else ""))(
        len(t.trace.get("unconfirmed") or [])),
    "grounded": grounded,
    "named": lambda t, on: (lambda m: (not (on and m), f"names {m[0]!r}" if on and m else ""))(LONE_ID.search(t.answer)),
}


def score_turn(turn, spec):
    """{check: {passed, detail}} for one turn, its own checks and the defaults it doesn't turn off."""
    wanted = {**DEFAULTS, **{k: v for k, v in spec.items() if k in CHECKS}}
    out = {}
    for name, value in wanted.items():
        passed, detail = CHECKS[name](turn, value)
        out[name] = {"passed": bool(passed), "detail": detail}
    return out


def score(data, records, names):
    """Each played conversation's turns scored: [{id, seed, turns: [{turn, outcome, passed, checks}]}]. A held-out
    set's details, which can quote its answers, are left out."""
    specs = {c["id"]: c for c in data["conversation"]}
    blind = bool(data.get("heldout"))
    out = []
    for record in records:
        spec, turns, scored = specs[record["id"]], record["turns"], []
        for k, (trace, wanted) in enumerate(zip(turns, spec["turn"])):
            checks = score_turn(Turn(trace, turns[k - 1] if k else None, names), wanted)
            if blind:
                checks = {name: {"passed": c["passed"]} for name, c in checks.items()}
            scored.append({"turn": k + 1, "outcome": trace["outcome"], "passed": all(c["passed"] for c in checks.values()),
                           "checks": checks})
        out.append({"id": record["id"], "seed": record["seed"], "turns": scored})
    return out


# Playing

def play(spec, conversation):
    """A conversation's turns, each the trace react.Conversation.ask returns, numbered."""
    return [{"turn": n, **conversation.ask(turn["say"])} for n, turn in enumerate(spec["turn"], 1)]


def run(data, set_path, seeds, examples_on, run_id=None, ids=None, log=print):
    """Play every conversation once per seed, appending each as it finishes; a rerun with the same run_id resumes."""
    react.load_env()
    retriever = react.retriever_or_exit(examples_on, lambda message: sys.exit(message))
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = harness.RAW / run_id
    out.mkdir(parents=True, exist_ok=True)
    path = out / "conversations.jsonl"
    done = {(r["id"], r["seed"]) for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())} if path.exists() else set()
    header = react.run_header(run_id, seeds=seeds, title=f"Conversations: run {run_id}",
                              examples=react.examples_header(examples_on))
    where = Path(set_path).resolve()
    header.update(arm="on" if examples_on else "off", heldout=bool(data.get("heldout")),
                  set=where.relative_to(ROOT).as_posix() if where.is_relative_to(ROOT) else str(where))
    (out / "header.json").write_text(json.dumps(header, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tools = react.Tools()
    chosen = [c for c in data["conversation"] if not ids or c["id"] in ids]
    todo = [(s, c) for s in seeds for c in chosen if (c["id"], s) not in done]
    log(f"Run {run_id}: {len(chosen)} conversations, seeds {seeds}, examples {header['arm']}; {len(todo)} to go")
    for n, (seed, spec) in enumerate(todo, 1):
        for attempt in range(1, harness.TRIES + 1):  # a conversation that fails isn't written, so it starts afresh
            try:
                conversation = react.Conversation(tools, log=lambda *_: None, retriever=retriever, model=react.MODEL,
                                                  think=True, seed=seed)
                turns = play(spec, conversation)
                break
            except (OSError, ValueError, http.client.HTTPException) as e:
                if attempt == harness.TRIES:
                    raise
                log(f"  {spec['id']} seed {seed}: {type(e).__name__}; trying again in {harness.WAIT} s")
                time.sleep(harness.WAIT)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": spec["id"], "seed": seed, "turns": turns}, ensure_ascii=False) + "\n")
        log(f"  [{n}/{len(todo)}] {spec['id']} seed {seed}: {', '.join(t['outcome'] for t in turns)}")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    (out / "conversations.md").write_text("\n".join(
        f"# {r['id']}, seed {r['seed']}\n\n" + react.markdown(r["turns"], header) for r in records) + "\n", encoding="utf-8")
    return run_id


def load_run(run_id):
    header = json.loads((harness.RAW / run_id / "header.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in (harness.RAW / run_id / "conversations.jsonl").read_text(encoding="utf-8").splitlines()]
    return header, records


# Reporting

def report(runs, data):
    """Each turn's result per seed, a column per run, as markdown lines: "pass", or the checks that failed. A held-out
    set's titles are left out."""
    blind = bool(data.get("heldout"))
    seeds = sorted({r["seed"] for _, scored in runs for r in scored})
    by = {(run_id, r["id"], r["seed"]): r["turns"] for run_id, scored in runs for r in scored}
    out = ["| Conversation | Turn | " + " | ".join(f"{run_id}, seed {s}" for run_id, _ in runs for s in seeds) + " |",
           "|---|---|" + "---|" * (len(runs) * len(seeds))]
    for c in data["conversation"]:
        label = c["id"] if blind else f"{c['id']} {c['title']}"
        for k in range(len(c["turn"])):
            cells = []
            for run_id, _ in runs:
                for s in seeds:
                    turns = by.get((run_id, c["id"], s))
                    if not turns or k >= len(turns):
                        cells.append("")
                        continue
                    failed = [name for name, check in turns[k]["checks"].items() if not check["passed"]]
                    cells.append("pass" if not failed else ", ".join(failed))
            out.append(f"| {label if k == 0 else ''} | {k + 1} | " + " | ".join(cells) + " |")
    out.append("")
    for run_id, scored in runs:
        turns = [t for r in scored for t in r["turns"]]
        whole = sum(all(t["passed"] for t in r["turns"]) for r in scored)
        out.append(f"**{run_id}:** {harness.counted(sum(t['passed'] for t in turns), len(turns))} turns pass every"
                   f" check, and {harness.counted(whole, len(scored))} conversations pass in every turn.")
    return out


# The review page

def run_query(sql, path):
    """(rows, columns, error, seconds): a reference query on the snapshot, read-only, with the views the agent's
    connections add to it (tools.connect: v_sets_1v1 and v_event_series)."""
    db = connect(path, QUERY_SECONDS)
    begun = time.monotonic()
    try:
        cursor = db.execute(sql)
        return [tuple(r) for r in cursor.fetchall()], [d[0] for d in cursor.description or []], None, time.monotonic() - begun
    except (sqlite3.Error, sqlite3.Warning) as e:
        return None, None, f"{type(e).__name__}: {e}", time.monotonic() - begun
    finally:
        db.close()


def review(data, path):
    """The set's review page, and what went wrong: (markdown, problems). Each turn's queries run on the snapshot,
    and its rows and rows_any patterns must hold on their results, as on the agent's."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    harness.add_views(db)
    try:
        build = (db.execute("SELECT value FROM build_info WHERE key = 'build_id'").fetchone() or ["?"])[0]
    finally:
        db.close()
    issues = [] if build == data["build"] else [f"the snapshot is build {build}, but the facts were computed on {data['build']}"]
    with open(QUESTIONS, "rb") as f:
        answers = {q["id"]: q["answer"] for q in tomllib.load(f)["question"]}
    conversations = data["conversation"]
    verified = [c for c in conversations if str(c.get("verified", "")).strip()]
    out = ["# Test conversations: review", "",
           "Made by `python eval/conversations.py review` from [`conversations.toml`](conversations.toml), which is the"
           " file to edit.", "",
           f"{len(conversations)} conversations, {sum(len(c['turn']) for c in conversations)} turns, with expected facts"
           f" computed from the frozen snapshot `{data['snapshot']}` (build {data['build']}). Each turn shows what a right"
           " answer says, the automatic checks scoring it, and the queries behind them with their results.", "",
           "**To verify:** check each turn's expected answer against what you know, then fill in `verified` for its"
           " conversation in `conversations.toml`: `yes`, or `no: ...` or `partly: ...` with what's right. Then re-run the"
           " command to update this page.", "",
           f"**Verified:** {len(verified)} of {len(conversations)}.", "",
           "| Id | Conversation | Turns | Measures | Verified |", "|---|---|---|---|---|"]
    out += [f"| [{c['id']}](#{c['id']}) | {c['title']} | {len(c['turn'])} | {'; '.join(c.get('measures', []))} |"
            f" {c.get('verified', '')} |" for c in conversations]
    for c in conversations:
        out += ["", f'<a id="{c["id"]}"></a>', "", f"## {c['id']}. {c['title']}", "", f"From {c['source']}.", ""]
        for n, turn in enumerate(c["turn"], 1):
            checks = {k: v for k, v in turn.items() if k in CHECKS}
            out += [f"### Turn {n}: {turn['say']}", "", f"**Expected:** {flat(turn['expect'])}", ""]
            if turn.get("check"):
                out += [f"**{turn['check']}'s verified answer:** {flat(answers[turn['check']])}", ""]
            out += ["**Checks:** " + "; ".join(f"{k} {json.dumps(v, ensure_ascii=False)}" for k, v in checks.items())
                    + ("; " if checks else "") + "grounded and named (every turn)", ""]
            if turn.get("shown"):
                out += [f"**Shown on the page after this turn:** {flat(turn['shown'])}", ""]
            results = []
            for m, query in enumerate(turn.get("query", []), 1):
                sql = query["sql"].strip()
                rows, columns, error, seconds = run_query(sql, path)
                if error:
                    issues.append(f"{c['id']} turn {n} query {m}: {error}")
                results.append(rows or [])
                out += [f"**Query {m}:** {flat(query.get('purpose', ''))}", "", "```sql", sql, "```", "",
                        f"Error: `{error}`" if error else table(columns, rows), ""]
            if turn.get("query"):
                missing = [p for p in turn.get("rows", []) if not any(holds(r, p) for rows in results for r in rows)]
                if missing:
                    issues.append(f"{c['id']} turn {n}: its queries' rows hold none of {missing}")
                if turn.get("rows_any") and not any(holds(r, p) for p in turn["rows_any"] for rows in results for r in rows):
                    issues.append(f"{c['id']} turn {n}: its queries' rows hold none of its rows_any")
        out += [f"**Verified:** {c.get('verified', '').strip() or 'not yet'}"]
    return "\n".join(out) + "\n", issues


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Multi-turn test conversations for the agent.")
    parser.add_argument("--set", default=str(SET), help="the conversations file (default: eval/questions/conversations.toml)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("review", help="write the review page, with each turn's queries run on eval-v1")
    go = commands.add_parser("run", help="play the conversations through the agent")
    go.add_argument("--seeds", nargs="+", type=int, default=[0])
    go.add_argument("--examples", choices=["on", "off"], default="on")
    go.add_argument("--ids", nargs="+", help="conversation ids, such as c1 c3")
    go.add_argument("--run", help="a run id to resume")
    scoring = commands.add_parser("score", help="score each turn of a run")
    scoring.add_argument("run")
    reporting = commands.add_parser("report", help="each turn's result per seed, a column per run")
    reporting.add_argument("runs", nargs="+")
    args = parser.parse_args()
    data = load(args.set)
    issues = problems(data)
    if issues:
        print("The set has problems:\n  " + "\n  ".join(issues))
        sys.exit(1)
    if args.command == "review":
        if data.get("heldout"):
            sys.exit("A held-out set gets no review page here: it would show its text.")
        page, issues = review(data, ROOT / data["snapshot"])
        REVIEW.write_text(page, encoding="utf-8")
        print(f"Wrote {REVIEW.relative_to(ROOT).as_posix()}")
        if issues:
            print("Problems:\n  " + "\n  ".join(issues))
            sys.exit(1)
        return
    if args.command == "run":
        print(run(data, args.set, args.seeds, args.examples == "on", args.run, args.ids))
        return
    db = sqlite3.connect(harness.SNAPSHOT.resolve().as_uri() + "?mode=ro", uri=True)
    names = dict(db.execute("SELECT player_id, name FROM players"))
    if args.command == "score":
        scored = score(data, load_run(args.run)[1], names)
        path = harness.RESULTS / f"{args.run}-conversations.json"
        path.write_text(json.dumps(scored, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        turns = [t for r in scored for t in r["turns"]]
        print(f"{args.run}: {sum(t['passed'] for t in turns)} of {len(turns)} turns pass every check; {path.name}")
        return
    runs = [(r, json.loads((harness.RESULTS / f"{r}-conversations.json").read_text(encoding="utf-8"))) for r in args.runs]
    print("\n".join(report(runs, data)))


if __name__ == "__main__":
    main()
