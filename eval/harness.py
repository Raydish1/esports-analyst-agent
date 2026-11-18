"""The evaluation harness: run the agent on the evaluation set (questions.toml) and the held-out set (heldout.toml),
score each run by the stage that failed first, and report by group, shape, category and stage.

    py -3.14 eval/harness.py run --ids q13 h09 q35 --seeds 0           a few questions, retrieval on
    py -3.14 eval/harness.py run --all --seeds 0 1 2                    every question, retrieval on
    py -3.14 eval/harness.py run --near-clean --seeds 0 1 2 --examples off
    python eval/harness.py score RUN [RUN ...]                          stages 1 and 2, and a judgments draft
    python eval/harness.py report RUN [RUN ...]                         the tables, with raw counts
    python eval/harness.py failures RUN                                 every run not right, as a page to read
    python eval/harness.py replay RUN                                   the number check and the name filter, offline

A run's traces go to data/experiments/<run>/traces.jsonl, one line per question and seed as each finishes, so an
interrupted run resumes where it stopped. Scoring reads the traces only, so a corrected check never needs a rerun.

Each run's verdict (right, partly, wrong) comes with the first stage that failed, in the pipeline's order:
1. name resolution: every player and event the question names resolved to the IDs its file gives, and those were
   the IDs the agent used (scored here);
2. SQL logic: the queries it ran and the templates it called (agent/templates.py), with the events resolve_event
   listed, returned the facts the answer needs (eval/result_checks.py; scored here);
3. empty or insufficient data: a "none", a "not held" or missing data told apart from a lookup mistake, said, and not
   filled in;
4. answer writing: the answer states what the results show, with what the question requires (the name, the minimum,
   the assumption), and nothing they don't.
Stages 3 and 4 are judged by hand: score drafts them in eval/results/<run>-judgments.toml as "needs review", to be
filled in and confirmed. A run that fails stage 1 or 2 is "wrong" there, marked "auto".

Groups (2026-11-08): the questions the agent was tuned on by the day of the run (TUNED); and every other question by
whether retrieval returns an example of a helpful shape (eval/questions/shapes.toml) above the threshold: "known
shape" or "new shape", for the existing and held-out sets apart.
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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT / "eval"))
from result_checks import NA, all_checks, load_questions  # noqa: E402
from names import normalize, normalize_full  # noqa: E402
from number_check import Evidence, without  # noqa: E402
from templates import TEMPLATES  # noqa: E402
from tools import add_views, name_filters, tables  # noqa: E402

CHECKS = all_checks()  # stage 2's check per question, of both sets
RAW = ROOT / "data" / "experiments"
RESULTS = ROOT / "eval" / "results"
SHAPES = ROOT / "eval" / "questions" / "shapes.toml"
SNAPSHOT = ROOT / "data" / "db" / "eval" / "eval-v1.sqlite"
# The questions the agent was tuned on, each with the day of the step that tuned on it (docs/experiments.md). A run
# counts a question as tuned from that day on, so an earlier run keeps its groups when it's reported again.
TUNED = {"q04": "20261018", "q06": "20261018", "q08": "20261018", "q21": "20261023", "q22": "20261023",
         "q05": "20261109", "q09": "20261109", "q33": "20261109", "q35": "20261109", "q36": "20261109",
         "q45": "20261109", "q15": "20261109", "q20": "20261109", "q44": "20261109",
         "q30": "20261117", "q31": "20261117", "q41": "20261117"}
# The existing questions retrieval gave no helpful example in its measurement (2026-10-26), less those tuned on since
# (q05, q09, q33, q35, q36 and q45, in step 1): the near-clean half of the retrieval-off arm, with the held-out set
NEAR_CLEAN = ["q14", "q15", "q23", "q32", "q34", "q39", "q42"]
STAGES = ["name resolution", "SQL logic", "empty or insufficient data", "answer writing", "no answer"]
TRIES, WAIT = 3, 60  # attempts at a run when the Ollama server fails, and seconds between them
VERDICTS = ["right", "partly", "wrong"]


# Reading a trace

def calls(trace, name):
    """(arguments, observation) of every call to a tool in a trace, in order."""
    out = []
    for step in trace["steps"]:
        for c in step["tool_calls"]:
            if c["name"] == name and c["observation"]:
                args = c["arguments"] if isinstance(c["arguments"], dict) else {}
                out.append((args, json.loads(c["observation"])))
    return out


def query_calls(trace):
    """(tool, arguments, observation, statements) of every call that queried the results, in order: a run_sql query,
    whose statement is its query, and a template call (agent/templates.py), whose statements are the SQL it executed,
    kept in the trace."""
    out = []
    for step in trace["steps"]:
        for c in step["tool_calls"]:
            if c["observation"] and (c["name"] == "run_sql" or c["name"] in TEMPLATES):
                args = c["arguments"] if isinstance(c["arguments"], dict) else {}
                statements = [args.get("query", "")] if c["name"] == "run_sql" else c.get("ran") or []
                out.append((c["name"], args, json.loads(c["observation"]), statements))
    return out


def queries(trace):
    """Every SQL statement the run executed: its run_sql queries and its templates' statements, which hold the player
    and event IDs a template was given or found."""
    return [sql for _, _, _, statements in query_calls(trace) for sql in statements]


ID_COLUMN = re.compile(r"(player|partner|opponent|winner)\d?_?id$", re.I)


def spread(row):
    """A row with a list cell's values in its place: a template gives a team's player_ids as one cell."""
    return [x for v in row for x in (v if isinstance(v, list) else [v])]


def results(trace, names=None):
    """The rows each query showed the agent (none for a result too large to show), a template's each table's rows,
    then the events each resolve_event call listed, as rows of their values: an event's status (cancelled) can come
    from there. With names ({player_id: name}), a player ID in an ID column also counts as the player's name, since
    an agent often fetches IDs first and names in a second query, but only if some tool result in the run holds that
    name: an answer of bare IDs didn't get the names (q14, seed 1, retrieval off, 2026-11-08)."""
    shown = [result for _, _, obs, _ in query_calls(trace) if "error" not in obs for result in tables(obs)]
    returned = {cell.casefold() for _, rows in shown for row in rows for cell in spread(row) if isinstance(cell, str)}
    returned |= {c["name"].casefold() for _, obs in calls(trace, "resolve_player") for c in obs.get("candidates", [])
                 if c.get("name")}
    out = []
    for columns, rows in shown:
        ids = [i for i, c in enumerate(columns) if ID_COLUMN.search(c)]
        if names and ids:
            rows = [list(r) + [names[r[i]] for i in ids if isinstance(r[i], int) and r[i] in names
                               and (names[r[i]] or "").casefold() in returned] for r in rows]
        out.append([spread(r) for r in rows])
    return out + [[list(e.values()) for e in obs["events"]] for _, obs in calls(trace, "resolve_event") if obs.get("events")]


def ended_empty(trace):
    """Whether the last query that ran found nothing, so the answer came after an empty result: no rows, or one row
    of nulls and zeros (an aggregate over no rows, such as COUNT(*) with SUMs); for a template, no rows in any of its
    tables."""
    done = [obs for _, _, obs, _ in query_calls(trace) if "error" not in obs]
    if not done:
        return False
    last = done[-1]
    if "tables" in last:
        return not any(rows for _, rows in tables(last))
    rows = last.get("rows")
    return last.get("row_count") == 0 or (rows is not None and len(rows) == 1 and all(c in (None, 0) for c in rows[0]))


def executed_queries(trace):
    """(SQL, observation) of every query the run executed, for the failures page: a run_sql query as written, and a
    template call as the call, in a comment, then each statement it executed."""
    out = []
    for name, args, obs, statements in query_calls(trace):
        if name == "run_sql":
            out.append((args.get("query", ""), obs))
        else:
            call = f"-- {name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"
            out.append(("\n".join([call] + [f"{sql};" for sql in statements]), obs))
    return out


def tool_calls(trace):
    """How many times the run called each tool."""
    return dict(Counter(c["name"] for step in trace["steps"] for c in step["tool_calls"]))


CHECKS_FIRED = {"size_check": "result-size check", "lookup_check": "lookup check", "no_tool_check": "no-tool check",
                "answer_check": "answer check"}
NEW_CHECKS = ["number check, sent back", "number check, claims replaced", "name filter, queries refused"]


def fired(trace):
    """How many times each check fired in a run: the steps it acted on; for the number check its send-backs and the
    claims it replaced apart, and for the name filter the queries it refused."""
    out = Counter()
    for step in trace["steps"]:
        out.update(label for key, label in CHECKS_FIRED.items() if step.get(key))
        number = step.get("number_check") or {}
        out["number check, sent back"] += number.get("action") == "sent back"
        out["number check, claims replaced"] += len(number.get("replaced") or [])
        out["name filter, queries refused"] += sum(bool(c.get("name_filters")) for c in step["tool_calls"])
    return {label: n for label, n in out.items() if n}


def replay(trace):
    """The number check and the name filter on a recorded run, offline: the claims of its final answer that nothing
    the run's tools returned or its question wrote supports, each with what replaces it, and the name filters of its
    run_sql queries. On a run from before them, what they would have done; on one after, nothing should be left."""
    evidence, named = Evidence(), []
    evidence.ask(trace["question"])
    for step in trace["steps"]:
        for c in step["tool_calls"]:
            arguments = c["arguments"] if isinstance(c["arguments"], dict) else {}
            if c["name"] == "run_sql" and isinstance(arguments.get("query"), str):
                named += name_filters(arguments["query"])
            if c["observation"] is not None:
                observation = json.loads(c["observation"])
                evidence.observe(observation)
                if "error" not in observation:
                    evidence.call(c["arguments"])
    answer = trace.get("answer") or ""
    flagged = evidence.unsupported(answer) if trace.get("outcome") != "suggestions" else []
    return (without(answer, flagged)[1] if flagged else []), named


def flat(text):
    return " ".join(str(text).split()).casefold()


def same_name(a, b):
    a, b = {normalize(a), normalize_full(a)} - {""}, {normalize(b), normalize_full(b)} - {""}
    return bool(a & b) or any(x in y or y in x for x in a for y in b if min(len(x), len(y)) >= 4)


# Stage 1: name resolution

def accepts_suggestions(question):
    return any("suggestion" in a.get("answer", "") for a in question.get("accept", []))


def numbers(query):
    return {int(n) for n in re.findall(r"(?<![\w.])-?\d+(?![\w.])", query)}


def player_resolved(question, trace, name, pid):
    """Whether the agent took a player name to the right person: it queried with the player_id, never in one query
    with another candidate for the name (which leaves the name unresolved), or the resolver gave it first and the
    agent queried with no other candidate; or, where the question accepts it, suggested it first."""
    used = set().union(*map(numbers, queries(trace)))
    if trace.get("outcome") == "suggestions":
        offered = [ids for step in trace["steps"] for n, ids in (step.get("suggestions") or {}).items() if same_name(n, name)]
        if not accepts_suggestions(question):
            return False, f"asked the user, suggesting {offered[0] if offered else 'others'}, where an answer is expected"
        return bool(offered and offered[0][:1] == [pid]), f"suggested {offered[0] if offered else 'others'}"
    rivals = {c["player_id"] for args, obs in calls(trace, "resolve_player") if same_name(args.get("name", ""), name)
              for c in obs.get("candidates", [])} - {pid}
    for query in queries(trace):
        if pid in numbers(query) and numbers(query) & rivals:
            return False, f"queried with it and other candidates {sorted(numbers(query) & rivals)} at once"
    if pid in used:
        return True, "queried with it"
    for args, obs in calls(trace, "resolve_player"):
        if not same_name(args.get("name", ""), name):
            continue
        ids = [c["player_id"] for c in obs.get("candidates", [])]
        if ids[:1] == [pid]:
            others = sorted(used & set(ids[1:]))
            return (not others), ("resolved first" if not others else f"resolved, but queried with {others}")
        if ids:
            return False, f"resolved to {ids[:3]}"
    return False, "not resolved"


def event_found(trace, ids, db):
    """Whether the agent's queries covered the events: their IDs in a query, a resolve_event condition the queries
    used that selects them, or their names in a result."""
    text = " ".join(queries(trace))
    if all(i in text for i in ids):
        return True, "IDs in a query"
    covered = set()
    for _, obs in calls(trace, "resolve_event"):
        condition = obs.get("sql")
        if condition and flat(condition) in flat(text):
            covered |= {e for (e,) in db.execute(f"SELECT event_id FROM v_events WHERE {condition}")}
    if set(ids) <= covered:
        return True, "resolve_event's condition"
    named = [db.execute("SELECT tournament_name, start_date FROM v_events WHERE event_id = ?", (i,)).fetchone() for i in ids]
    shown = flat(json.dumps(results(trace), ensure_ascii=False))
    if all(n and flat(n[0]) in shown and n[1][:4] in shown for n in named):  # a yearly series repeats its names
        return True, "name and year in a result"
    return False, "not found"


def stage1(question, trace, db):
    """{result: pass, fail or n/a, detail}. A run that called no tool tried no lookup, so its failure is the query it
    never ran (stage 2), not a lookup."""
    expected = [("player", n, p) for n, p in (question.get("players") or {}).items()]
    expected += [("event", n, i if isinstance(i, list) else [i]) for n, i in (question.get("events") or {}).items()]
    if not expected:
        return {"result": "n/a", "detail": "names no player or event"}
    if not any(step["tool_calls"] for step in trace["steps"]):
        return {"result": "n/a", "detail": "called no tool"}
    details, ok = [], True
    for kind, name, target in expected:
        good, how = player_resolved(question, trace, name, target) if kind == "player" else event_found(trace, target, db)
        ok &= good
        details.append(f"{name}: {how}")
    return {"result": "pass" if ok else "fail", "detail": "; ".join(details)}


# Stage 2: SQL logic

def stage2(question, trace, names=None):
    """{result: pass, fail or n/a, detail}: the question's check on the results the agent saw."""
    check = CHECKS[question["id"]]
    if check is NA:
        return {"result": "n/a", "detail": "the right answer needs no query result"}
    if trace.get("outcome") == "suggestions":
        return {"result": "n/a", "detail": "asked the user instead of querying"}
    shown = results(trace, names)
    return {"result": "pass" if check(shown) else "fail", "detail": f"{len(shown)} query results"}


# Shape and group

def shape(question, trace, labels):
    """'known shape' when the examples retrieved for the question include a helpful shape, else 'new shape'; None
    when the trace has no retrieval (the shape then comes from another run)."""
    found = trace.get("examples")
    if found is None:
        return None
    return "known shape" if {e["shape"] for e in found["examples"]} & set(labels.get(question["id"], [])) else "new shape"


def tuned(question, run_id=""):
    """Whether the agent had been tuned on a question by the day of a run, which its id starts with (an id without a
    day counts as today)."""
    day = run_id[:8] if run_id[:8].isdigit() else "99999999"
    return question["id"] in TUNED and TUNED[question["id"]] <= day


def group(question, known, run_id=""):
    if tuned(question, run_id):
        return "tuned"
    return f"{'held-out' if question['set'] == 'heldout' else 'existing'}, {known}"


def draft(record):
    """A judgment draft from the automatic stages: wrong at stage 1 or 2 (auto); wrong with no answer (the step limit,
    say) once those pass, for review to name the stage; otherwise blank, for review. Two automatic failures are only
    drafts: one at stage 1 where the right answer needs no query result (an unanswerable question, a true "none"),
    since the answer can be right without the lookup; and one at stage 2 whose last query came back empty, which is
    drafted as stage 3, since the empty result may be true (a cancelled event, unreliable placements) or a lookup
    mistake answered as a "none"."""
    for n, stage in ((1, "name resolution"), (2, "SQL logic")):
        if record[f"stage{n}"]["result"] == "fail":
            note = record[f"stage{n}"]["detail"]
            if n == 2 and record.get("ended_empty"):
                return {"verdict": "wrong", "stage": "empty or insufficient data", "review": "needs review",
                        "note": f"answered after an empty result; {note}"}
            review = "auto" if record.get("needs_data", True) else "needs review"
            return {"verdict": "wrong", "stage": stage, "review": review, "note": note}
    if record["outcome"] not in ("answered", "suggestions"):
        return {"verdict": "wrong", "stage": "no answer", "review": "needs review", "note": f"outcome: {record['outcome']}"}
    return {"verdict": "", "stage": "", "review": "needs review", "note": ""}


def kept(entry, fresh, record):
    """Whether a verdict judged earlier stays over the fresh draft: always once the user confirmed it; one blaming
    stage 1 or 2 only while the run fails that stage (it can turn an automatic "wrong" into "partly"); any other
    only while the fresh draft isn't automatic, so a corrected check needs no rerun."""
    if not entry or entry.get("review") == "auto":
        return False
    if entry.get("review") == "confirmed":
        return True
    if entry.get("stage") == "name resolution":
        return record["stage1"]["result"] == "fail"
    if entry.get("stage") == "SQL logic":
        return record["stage2"]["result"] == "fail"
    return fresh["review"] != "auto"


# Running

def run(questions, seeds, examples_on, run_id=None, log=print):
    """Ask every question once per seed, appending each trace as it finishes; a rerun with the same run_id resumes."""
    import react
    react.load_env()
    retriever = react.retriever_or_exit(examples_on, lambda message: sys.exit(message))
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RAW / run_id
    out.mkdir(parents=True, exist_ok=True)
    path = out / "traces.jsonl"
    done = {(t["id"], t["seed"]) for t in map(json.loads, path.read_text(encoding="utf-8").splitlines())} if path.exists() else set()
    header = react.run_header(run_id, seeds=seeds, title=f"Evaluation harness: run {run_id}",
                              examples=react.examples_header(examples_on))
    header["arm"] = "on" if examples_on else "off"
    (out / "header.json").write_text(json.dumps(header, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tools, todo = react.Tools(), [(s, q) for s in seeds for q in questions if (q["id"], s) not in done]
    log(f"Run {run_id}: {len(questions)} questions, seeds {seeds}, examples {header['arm']}; {len(todo)} to go")
    for n, (seed, q) in enumerate(todo, 1):
        for attempt in range(1, TRIES + 1):  # a run that fails isn't written, so the retry starts it afresh
            try:
                trace = react.run(q["question"], tools, retriever=retriever, log=lambda *_: None, model=react.MODEL,
                                  think=True, seed=seed)
                break
            # the server unreachable or timed out, or a reply cut off
            except (OSError, ValueError, http.client.HTTPException) as e:
                if attempt == TRIES:
                    raise
                log(f"  {q['id']} seed {seed}: {type(e).__name__}: {e}; trying again in {WAIT} s")
                time.sleep(WAIT)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": q["id"], "number": q["id"], "set": q["set"], "seed": seed, **trace},
                               ensure_ascii=False) + "\n")
        log(f"  [{n}/{len(todo)}] {q['id']} seed {seed}: {trace['outcome']} in {trace['steps_used']} steps,"
            f" {trace['model_seconds']} s")
    traces = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    (out / "traces.md").write_text(react.markdown(traces, header) + "\n", encoding="utf-8")
    return run_id


# Scoring

def load_traces(run_id):
    header = json.loads((RAW / run_id / "header.json").read_text(encoding="utf-8"))
    traces = [json.loads(line) for line in (RAW / run_id / "traces.jsonl").read_text(encoding="utf-8").splitlines()]
    return header, traces


def score(run_ids, db, labels):
    """Each trace of the runs scored: {run_id: [record]}. A question's shape comes from a run with retrieval."""
    questions = {q["id"]: q for q in load_questions()}
    loaded = {r: load_traces(r) for r in run_ids}
    names = dict(db.execute("SELECT player_id, name FROM players")) if db else None
    shapes = {}
    for _, traces in loaded.values():
        for t in traces:
            known = shape(questions[t["id"]], t, labels)
            if known:
                shapes.setdefault(t["id"], known)
    out = {}
    for run_id, (header, traces) in loaded.items():
        records = []
        for t in traces:
            q = questions[t["id"]]
            known = shapes.get(t["id"], "unknown shape")
            found = t.get("examples")
            records.append({
                "id": q["id"], "set": q["set"], "category": q["category"], "seed": t["seed"], "arm": header["arm"],
                "question": q["question"], "expected": " ".join(q["answer"].split()), "outcome": t["outcome"],
                "answer": t["answer"],
                "stage1": stage1(q, t, db), "stage2": stage2(q, t, names), "shape": known, "group": group(q, known, run_id),
                "label": (labels.get(q["id"]) or ["none (no query answers it)"])[0], "needs_data": CHECKS[q["id"]] is not NA,
                "ended_empty": ended_empty(t),
                "examples": [(e["id"], e["shape"], e["similarity"]) for e in found["examples"]] if found else None,
                "checks": sorted({k for s in t["steps"] for k in ("size_check", "lookup_check", "no_tool_check",
                                                                   "answer_check", "number_check") if s.get(k)}),
                "fired": fired(t),
                "steps": t["steps_used"], "model_seconds": t["model_seconds"], "output_tokens": t["output_tokens"],
                "name_swaps": len(t.get("name_swaps") or []), "tools": tool_calls(t)})
        out[run_id] = records
    return out


def toml_string(value):
    return json.dumps(value, ensure_ascii=False)


def write_judgments(path, records, keep=None):
    """The judgments file: each run's verdict, stage and review mark. An automatic verdict (stage 1 or 2 failed) is
    recomputed every time, and a verdict judged earlier (keep: {(arm, id, seed): entry}) stays as kept() says. Each
    question's text and expected answer, and each run's answer, are there to judge from; scoring reads only the
    verdicts."""
    keep = keep or {}
    lines = ["# Verdicts for the harness's runs (eval/harness.py). stage is the first that failed: name resolution, SQL",
             "# logic, empty or insufficient data, answer writing, or no answer. review is \"auto\" for a stage 1 or 2",
             "# failure the code found, and \"needs review\" for a verdict drafted by hand, until the user confirms it",
             "# (\"confirmed\"). Fill in or correct verdict, stage and note; scoring keeps what's here.", ""]
    last = None
    for r in sorted(records, key=lambda r: (r["arm"], r["id"], r["seed"])):
        if (r["arm"], r["id"]) != last and r.get("question"):
            lines += [f"# {r['id']} (retrieval {r['arm']}): {r['question']}", f"# Expected: {r['expected']}", ""]
        last = (r["arm"], r["id"])
        fresh, earlier = draft(r), keep.get((r["arm"], r["id"], r["seed"]))
        entry = earlier if kept(earlier, fresh, r) else fresh
        lines += ["[[run]]", f"arm = {toml_string(r['arm'])}", f"question = {toml_string(r['id'])}", f"seed = {r['seed']}",
                  f"verdict = {toml_string(entry['verdict'])}", f"stage = {toml_string(entry['stage'])}",
                  f"review = {toml_string(entry['review'])}", f"note = {toml_string(entry.get('note', ''))}",
                  f"answer = {toml_string(r.get('answer') or '')}", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def read_judgments(path):
    if not Path(path).exists():
        return {}
    with open(path, "rb") as f:
        return {(j["arm"], j["question"], j["seed"]): j for j in tomllib.load(f).get("run", [])}


# Reporting

def counted(n, total):
    return f"{n}/{total} ({round(100 * n / total)}%)" if total else "0/0"


def tally(records, judged):
    """Runs right and partly, and questions right in every seed, for a set of records."""
    verdict = [judged.get((r["arm"], r["id"], r["seed"]), {}).get("verdict", "") for r in records]
    by_question = {}
    for r, v in zip(records, verdict):
        by_question.setdefault(r["id"], []).append(v)
    return {"runs": len(records), "right": verdict.count("right"), "partly": verdict.count("partly"),
            "unjudged": verdict.count(""), "questions": len(by_question),
            "all_right": sum(all(v == "right" for v in vs) for vs in by_question.values())}


def table(title, rows, label):
    """A table of tallies; a column of runs not yet judged while any are, so they don't read as wrong."""
    unjudged = any(t["unjudged"] for _, t in rows)
    out = [f"**{title}**", "", f"| {label} | Runs right | Runs partly | Questions right in every seed |"
           + (" Not judged yet |" if unjudged else ""), "|---|---|---|---|" + ("---|" if unjudged else "")]
    for name, t in rows:
        out.append(f"| {name} | {counted(t['right'], t['runs'])} | {counted(t['partly'], t['runs'])} |"
                   f" {counted(t['all_right'], t['questions'])} |" + (f" {t['unjudged']} |" if unjudged else ""))
    return out + [""]


def stages(title, columns, judged):
    """Runs not right by the stage that failed, a column per set of records."""
    failed = {name: [j for j in (judged.get((r["arm"], r["id"], r["seed"]), {}) for r in rs)
                     if j.get("verdict") in ("partly", "wrong")] for name, rs in columns}
    out = [f"**{title}** (each column's runs not right, by the first stage that failed)", "",
           "| Stage | " + " | ".join(f"{name}: {len(failed[name])} of {len(rs)} runs not right" for name, rs in columns) + " |",
           "|---|" + "---|" * len(columns)]
    for s in STAGES:
        out.append(f"| {s} | " + " | ".join(counted(sum(j.get("stage") == s for j in failed[name]), len(failed[name]))
                                             for name, _ in columns) + " |")
    return out + [""]


def tool_use(title, records):
    """How the runs used the tools: each tool's runs calling it and its calls, in all and per run, then steps and
    model seconds per run. run_sql's calls per run count the SQL the model wrote itself."""
    calls_made, runs = Counter(), Counter()
    for r in records:
        calls_made.update(r.get("tools") or {})
        runs.update(set(r.get("tools") or {}))
    order = ["resolve_player", "resolve_event", *TEMPLATES, "run_sql"]
    n = len(records)
    out = [f"**{title}**", "", "| Tool | Runs calling it | Calls | Calls per run |", "|---|---|---|---|"]
    for name in [t for t in order if t in calls_made] + sorted(set(calls_made) - set(order)):
        out.append(f"| {name} | {counted(runs[name], n)} | {calls_made[name]} | {calls_made[name] / n:.2f} |")
    return out + ["", f"Per run: {sum(r['steps'] for r in records) / n:.1f} steps and"
                      f" {sum(r['model_seconds'] for r in records) / n:.1f} s of model time, over {n} runs.", ""]


def check_use(title, records):
    """How often each check fired (fired): the runs it fired in, and the times in all."""
    out = [f"**{title}**", "", "| Check | Runs it fired in | Times |", "|---|---|---|"]
    for label in [*CHECKS_FIRED.values(), *NEW_CHECKS]:
        times = [r["fired"].get(label, 0) for r in records]
        out.append(f"| {label} | {counted(sum(n > 0 for n in times), len(records))} | {sum(times)} |")
    return out + [""]


def report(records, judged):
    """The summary tables, as markdown lines: retrieval on by group, the held-out set by shape, by the query's shape,
    by category and by failing stage; then the retrieval-off arm against the same questions and seeds with it on."""
    on = [r for r in records if r["arm"] == "on"]
    off = [r for r in records if r["arm"] == "off"]
    out = []

    def by(rs, key, values):
        return [(v, tally([r for r in rs if r[key] == v], judged)) for v in values if any(r[key] == v for r in rs)]

    groups = ["tuned", "existing, known shape", "existing, new shape", "held-out, known shape", "held-out, new shape"]
    out += table("Retrieval on, by group", by(on, "group", groups) + [("all", tally(on, judged))], "Group")
    held = [r for r in on if r["set"] == "heldout"]
    out += table("Held-out set, retrieval on, by shape",
                 [(name, tally([r for r in held if r["shape"] == s], judged))
                  for name, s in (("known shape, new names", "known shape"), ("new shape", "new shape"))], "Shape")
    out += table("Retrieval on, by the query's shape (the question's first label in shapes.toml)",
                 by(on, "label", sorted({r["label"] for r in on})), "Shape")
    out += table("Retrieval on, by category", by(on, "category", sorted({r["category"] for r in on})), "Category")
    if on:
        out += stages("Retrieval on, by failing stage", [("all", on)] + [
            (name, [r for r in on if r["group"] in members]) for name, members in
            (("tuned", ["tuned"]), ("existing", groups[1:3]), ("held-out", groups[3:]))], judged)
    if off:
        out += stages("Retrieval off, by failing stage", [("all", off)], judged)
        pairs = {(r["id"], r["seed"]) for r in off}
        same = [r for r in on if (r["id"], r["seed"]) in pairs]
        rows = []
        for name, chosen in (("held-out", "heldout"), ("existing, near-clean", "existing")):
            rows += [(f"{name}, off", tally([r for r in off if r["set"] == chosen], judged)),
                     (f"{name}, on", tally([r for r in same if r["set"] == chosen], judged))]
        out += table("The near-clean and held-out questions, retrieval off and on",
                     rows + [("all, off", tally(off, judged)), ("all, on", tally(same, judged))], "Questions, retrieval")
    for title, rs in (("Tool use, retrieval on", on), ("Tool use, retrieval off", off)):
        if rs and all("tools" in r for r in rs):  # records scored before the tools were counted have none
            out += tool_use(title, rs)
    for title, rs in (("Checks, retrieval on", on), ("Checks, retrieval off", off)):
        if rs and all("fired" in r for r in rs):  # nor, before 2026-11-17, the checks
            out += check_use(title, rs)
    review = sum(j.get("review") == "needs review" for j in judged.values())
    out.append(f"Judgments needing review: {review} of {len(judged)}.")
    return out


# The failures page

def quoted_text(text):
    """Text as a markdown quote, with its tags shown rather than rendered (one answer held <final_answer>)."""
    return "\n".join(f"> {line}" if line else ">" for line in str(text).replace("<", "&lt;").splitlines()) or ">"


def outcome(observation):
    if "error" in observation:
        return f"error: {observation['error']}"
    if "tables" in observation:  # a template: each table's rows
        return "; ".join(f"{t['what']}: {t['row_count']} row{'' if t['row_count'] == 1 else 's'}"
                         + (", too large to show" if t.get("complete") is False else "")
                         for t in observation["tables"]) or "no tables"
    if observation.get("complete") is False:
        return f"too large to show: {observation['row_count']} rows"
    n = observation.get("row_count", 0)
    return "no rows" if n == 0 else f"{n} row{'' if n == 1 else 's'}"


def failures(run_id, records, judged, questions, executed):
    """A run's failures page, as markdown lines: every run whose verdict isn't "right" (one not judged yet counts),
    grouped by question in the sets' order (questions: {id: question}, in that order). A contents table first, with
    each seed's verdict; then each question once (group, category, text, verified answer, accepted answers, notes),
    and each of its seeds not right with its verdict, stage, review mark, note and full answer, and the SQL it
    executed (executed: {(id, seed): [(query, observation)]}) folded away."""
    by = {}
    for r in records:
        by.setdefault(r["id"], {})[r["seed"]] = r
    seeds = sorted({r["seed"] for r in records})

    def judgment(r):
        return judged.get((r["arm"], r["id"], r["seed"])) or {}

    def verdict(r):
        return judgment(r).get("verdict") or "not judged"

    failing = [q for q in questions if q in by and any(verdict(r) != "right" for r in by[q].values())]
    runs = sum(verdict(r) != "right" for rs in by.values() for r in rs.values())
    out = [f"# Failures: run {run_id}", "",
           f"{runs} of {len(records)} runs aren't right, in {len(failing)} of {len(by)} questions. The verdicts are in"
           f" eval/results/{run_id}-judgments.toml, where \"needs review\" marks a draft.", "",
           "| Question | " + " | ".join(f"Seed {s}" for s in seeds) + " | Failing stage |",
           "|---|" + "---|" * len(seeds) + "---|"]
    for q in failing:
        rs = by[q]
        stages = dict.fromkeys(judgment(rs[s]).get("stage") for s in seeds if s in rs and verdict(rs[s]) != "right")
        out.append(f"| [{q}](#{q}) | " + " | ".join(verdict(rs[s]) if s in rs else "" for s in seeds)
                   + f" | {'; '.join(s for s in stages if s)} |")
    for q in failing:
        question, rs = questions[q], by[q]
        first = next(iter(rs.values()))
        out += ["", f'<a id="{q}"></a>', "", f"## {q}: {question['question']}", "",
                f"Group: {first['group']}. Category: {question['category']}.", "", "**Verified answer:**", "",
                quoted_text(question["answer"].strip())]
        for a in question.get("accept", []):
            out += ["", f"Also accepted, if {' '.join(a['assumption'].split())}: {' '.join(a['answer'].split())}"]
        if question.get("notes"):
            out += ["", f"**Notes:** {' '.join(question['notes'].split()).replace('<', '&lt;')}"]
        for s in seeds:
            r = rs.get(s)
            if r is None or verdict(r) == "right":
                continue
            j = judgment(r)
            head = ", ".join(x for x in (verdict(r), j.get("stage")) if x)
            out += ["", f"### Seed {s}: {head}" + (f" ({j['review']})" if j.get("review") else "")]
            if j.get("note"):
                out += ["", f"**Note:** {j['note'].replace('<', '&lt;')}"]
            out += ["", "**Answer:**", "", quoted_text(r["answer"] or f"(no answer: {r['outcome']})")]
            ran = executed.get((q, s), [])
            if not ran:
                out += ["", "No SQL was executed."]
                continue
            out += ["", f"<details><summary>SQL: {len(ran)} quer{'y' if len(ran) == 1 else 'ies'}</summary>", "", "```sql"]
            for i, (query, observation) in enumerate(ran):
                out += ([""] if i else []) + [query.strip(), f"-- {outcome(observation)}"]
            out += ["```", "", "</details>"]
    return out


def replayed(run_id, traces):
    """A run's replay page (replay), as markdown lines: each run whose final answer has a claim nothing supports, with
    what replaces each, then each run_sql query that looks a player up by name."""
    flagged, named = [], []
    for t in traces:
        claims, filters = replay(t)
        if claims:
            flagged.append((t, claims))
        named += [(t, f) for f in filters]
    out = [f"# Replay: run {run_id}", "", f"Of {len(traces)} runs, the number check flags {len(flagged)} final answers"
           f" and the name filter {len(named)} run_sql queries.", ""]
    for t, claims in flagged:
        out += [f"## {t['id']} seed {t['seed']}: {t['question']}", ""]
        for c in claims:
            out += [f"- {', '.join(c['numbers'])} in {c['claim']!r}", f"  becomes {c['replacement']!r}"]
        out.append("")
    if named:
        out += ["## Name filters", ""] + [f"- {t['id']} seed {t['seed']}: {f}" for t, f in named] + [""]
    return out


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Evaluate the agent on the evaluation and held-out sets.")
    commands = parser.add_subparsers(dest="command", required=True)
    go = commands.add_parser("run", help="run the agent on questions")
    pick = go.add_mutually_exclusive_group(required=True)
    pick.add_argument("--ids", nargs="+", help="question ids, such as q13 h09")
    pick.add_argument("--all", action="store_true", help="every question of both sets")
    pick.add_argument("--near-clean", action="store_true", help="the held-out set and the near-clean existing questions")
    go.add_argument("--seeds", nargs="+", type=int, default=[0])
    go.add_argument("--examples", choices=["on", "off"], default="on")
    go.add_argument("--run", help="a run id to resume")
    for name in ("score", "report"):
        p = commands.add_parser(name)
        p.add_argument("runs", nargs="+")
    page = commands.add_parser("failures", help="every run not right, with its answer and SQL, as a page to read")
    page.add_argument("run")
    page.add_argument("--out", help="where to write it (default: data/experiments/<run>/failures.md, by its traces)")
    again = commands.add_parser("replay", help="the number check and the name filter on a run's traces, offline")
    again.add_argument("run")
    args = parser.parse_args()
    if args.command == "replay":  # reads the run's traces and writes data/experiments/<run>/replay.md by them
        lines = replayed(args.run, load_traces(args.run)[1])
        (RAW / args.run / "replay.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{lines[2]}\n{RAW / args.run / 'replay.md'}")
        return
    questions = load_questions()
    if args.command == "failures":  # reads the run's scores, judgments and traces; changes none of them
        records = json.loads((RESULTS / f"{args.run}-scores.json").read_text(encoding="utf-8"))
        judged = read_judgments(RESULTS / f"{args.run}-judgments.toml")
        executed = {(t["id"], t["seed"]): executed_queries(t) for t in load_traces(args.run)[1]}
        path = Path(args.out) if args.out else RAW / args.run / "failures.md"
        lines = failures(args.run, records, judged, {q["id"]: q for q in questions}, executed)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(path)
        return
    if args.command == "run":
        if args.ids:
            unknown = set(args.ids) - {q["id"] for q in questions}
            if unknown:
                parser.error(f"no question {sorted(unknown)}")
            chosen = [q for q in questions if q["id"] in args.ids]
        elif args.near_clean:
            chosen = [q for q in questions if q["set"] == "heldout" or q["id"] in NEAR_CLEAN]
        else:
            chosen = questions
        print(run(chosen, args.seeds, args.examples == "on", args.run))
        return
    db = sqlite3.connect(SNAPSHOT.resolve().as_uri() + "?mode=ro", uri=True)
    add_views(db)  # as the agent's connections have them: a resolve_event condition can be on v_event_series
    with open(SHAPES, "rb") as f:
        labels = tomllib.load(f)["shapes"]
    scored = score(args.runs, db, labels)
    if args.command == "score":
        for run_id, records in scored.items():
            (RESULTS / f"{run_id}-scores.json").write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n",
                                                           encoding="utf-8")
            path = RESULTS / f"{run_id}-judgments.toml"
            write_judgments(path, records, read_judgments(path))
            auto = sum(draft(r)["review"] == "auto" for r in records)
            print(f"{run_id}: {len(records)} runs scored; {auto} wrong at stage 1 or 2 (auto); judgments in {path.name}")
        return
    judged = {}
    for run_id in args.runs:
        judged.update(read_judgments(RESULTS / f"{run_id}-judgments.toml"))
    print("\n".join(report([r for rs in scored.values() for r in rs], judged)))


if __name__ == "__main__":
    main()
