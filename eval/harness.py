"""The evaluation harness: run the agent on the evaluation set (questions.toml) and the held-out set (heldout.toml),
score each run by the stage that failed first, and report by group, shape, category and stage.

    py -3.14 eval/harness.py run --ids q13 h09 q35 --seeds 0           a few questions, retrieval on
    py -3.14 eval/harness.py run --all --seeds 0 1 2                    every question, retrieval on
    py -3.14 eval/harness.py run --near-clean --seeds 0 1 2 --examples off
    python eval/harness.py score RUN [RUN ...]                          stages 1 and 2, and a judgments draft
    python eval/harness.py report RUN [RUN ...]                         the tables, with raw counts

A run's traces go to data/experiments/<run>/traces.jsonl, one line per question and seed as each finishes, so an
interrupted run resumes where it stopped. Scoring reads the traces only, so a corrected check never needs a rerun.

Each run's verdict (right, partly, wrong) comes with the first stage that failed, in the pipeline's order:
1. name resolution: every player and event the question names resolved to the IDs its file gives, and those were
   the IDs the agent used (scored here);
2. SQL logic: the queries it ran returned the facts the answer needs (eval/result_checks.py; scored here);
3. empty or insufficient data: a "none", a "not held" or missing data told apart from a lookup mistake, said, and not
   filled in;
4. answer writing: the answer states what the results show, with what the question requires (the name, the minimum,
   the assumption), and nothing they don't.
Stages 3 and 4 are judged by hand: score drafts them in eval/results/<run>-judgments.toml as "needs review", to be
filled in and confirmed. A run that fails stage 1 or 2 is "wrong" there, marked "auto".

Groups (2026-11-08): the 5 questions the agent was tuned on; and every other question by whether retrieval returns
an example of a helpful shape (eval/questions/shapes.toml) above the threshold: "known shape" or "new shape", for
the existing and held-out sets apart.
"""

import argparse
import http.client
import json
import re
import sqlite3
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT / "eval"))
from result_checks import CHECKS, NA, load_questions  # noqa: E402
from names import normalize, normalize_full  # noqa: E402

RAW = ROOT / "data" / "experiments"
RESULTS = ROOT / "eval" / "results"
SHAPES = ROOT / "eval" / "questions" / "shapes.toml"
SNAPSHOT = ROOT / "data" / "db" / "eval" / "eval-v1.sqlite"
TUNED = ["q04", "q06", "q08", "q21", "q22"]  # changed the prompt, checks and examples (docs/experiments.md)
# The existing questions retrieval gave no helpful example in its measurement (2026-10-26): the near-clean half of
# the retrieval-off arm, with the held-out set
NEAR_CLEAN = ["q05", "q09", "q14", "q15", "q23", "q32", "q33", "q34", "q35", "q36", "q39", "q42", "q45"]
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


def queries(trace):
    return [args.get("query", "") for args, _ in calls(trace, "run_sql")]


def results(trace):
    """The rows each query showed the agent (none for a result too large to show)."""
    return [obs.get("rows", []) for _, obs in calls(trace, "run_sql") if "error" not in obs]


def flat(text):
    return " ".join(str(text).split()).casefold()


def same_name(a, b):
    a, b = {normalize(a), normalize_full(a)} - {""}, {normalize(b), normalize_full(b)} - {""}
    return bool(a & b) or any(x in y or y in x for x in a for y in b if min(len(x), len(y)) >= 4)


# Stage 1: name resolution

def accepts_suggestions(question):
    return any("suggestion" in a.get("answer", "") for a in question.get("accept", []))


def player_resolved(question, trace, name, pid):
    """Whether the agent took a player name to the right person: it queried with the player_id, or the resolver gave
    it first and the agent queried with no other candidate; or, where the question accepts it, suggested it first."""
    used = {int(n) for q in queries(trace) for n in re.findall(r"(?<![\w.])-?\d+(?![\w.])", q)}
    if trace.get("outcome") == "suggestions":
        offered = [ids for step in trace["steps"] for n, ids in (step.get("suggestions") or {}).items() if same_name(n, name)]
        if not accepts_suggestions(question):
            return False, f"asked the user, suggesting {offered[0] if offered else 'others'}, where an answer is expected"
        return bool(offered and offered[0][:1] == [pid]), f"suggested {offered[0] if offered else 'others'}"
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
    """{result: pass, fail or n/a, detail}."""
    expected = [("player", n, p) for n, p in (question.get("players") or {}).items()]
    expected += [("event", n, i if isinstance(i, list) else [i]) for n, i in (question.get("events") or {}).items()]
    if not expected:
        return {"result": "n/a", "detail": "names no player or event"}
    details, ok = [], True
    for kind, name, target in expected:
        good, how = player_resolved(question, trace, name, target) if kind == "player" else event_found(trace, target, db)
        ok &= good
        details.append(f"{name}: {how}")
    return {"result": "pass" if ok else "fail", "detail": "; ".join(details)}


# Stage 2: SQL logic

def stage2(question, trace):
    """{result: pass, fail or n/a, detail}: the question's check on the results the agent saw."""
    check = CHECKS[question["id"]]
    if check is NA:
        return {"result": "n/a", "detail": "the right answer needs no query result"}
    if trace.get("outcome") == "suggestions":
        return {"result": "n/a", "detail": "asked the user instead of querying"}
    shown = results(trace)
    return {"result": "pass" if check(shown) else "fail", "detail": f"{len(shown)} query results"}


# Shape and group

def shape(question, trace, labels):
    """'known shape' when the examples retrieved for the question include a helpful shape, else 'new shape'; None
    when the trace has no retrieval (the shape then comes from another run)."""
    found = trace.get("examples")
    if found is None:
        return None
    return "known shape" if {e["shape"] for e in found["examples"]} & set(labels.get(question["id"], [])) else "new shape"


def group(question, known):
    if question["id"] in TUNED:
        return "tuned"
    return f"{'held-out' if question['set'] == 'heldout' else 'existing'}, {known}"


def draft(record):
    """A judgment draft from the automatic stages: wrong at stage 1 or 2 (auto); wrong with no answer (the step limit,
    say) once those pass, for review to name the stage; otherwise blank, for review."""
    for n, stage in ((1, "name resolution"), (2, "SQL logic")):
        if record[f"stage{n}"]["result"] == "fail":
            return {"verdict": "wrong", "stage": stage, "review": "auto", "note": record[f"stage{n}"]["detail"]}
    if record["outcome"] not in ("answered", "suggestions"):
        return {"verdict": "wrong", "stage": "no answer", "review": "needs review", "note": f"outcome: {record['outcome']}"}
    return {"verdict": "", "stage": "", "review": "needs review", "note": ""}


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
                "stage1": stage1(q, t, db), "stage2": stage2(q, t), "shape": known, "group": group(q, known),
                "label": (labels.get(q["id"]) or ["none (no query answers it)"])[0],
                "examples": [(e["id"], e["shape"], e["similarity"]) for e in found["examples"]] if found else None,
                "checks": sorted({k for s in t["steps"] for k in ("size_check", "lookup_check", "no_tool_check",
                                                                   "answer_check") if s.get(k)}),
                "steps": t["steps_used"], "model_seconds": t["model_seconds"], "output_tokens": t["output_tokens"]})
        out[run_id] = records
    return out


def toml_string(value):
    return json.dumps(value, ensure_ascii=False)


def write_judgments(path, records, keep=None):
    """The judgments file: each run's verdict, stage and review mark. An automatic verdict (stage 1 or 2 failed) is
    recomputed every time, so a corrected check needs no rerun; a verdict judged by hand (keep: {(arm, id, seed):
    entry}) stays unless the run now fails stage 1 or 2, and one the user confirmed always stays. Each question's
    text and expected answer, and each run's answer, are there to judge from; scoring reads only the verdicts."""
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
        fresh, kept = draft(r), keep.get((r["arm"], r["id"], r["seed"]))
        by_hand = kept and kept.get("review") != "auto"
        entry = kept if by_hand and (kept.get("review") == "confirmed" or fresh["review"] != "auto") else fresh
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
    review = sum(j.get("review") == "needs review" for j in judged.values())
    out.append(f"Judgments needing review: {review} of {len(judged)}.")
    return out


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Evaluate the agent on the evaluation and held-out sets.")
    commands = parser.add_subparsers(dest="command", required=True)
    go = commands.add_parser("run", help="run the agent on questions")
    pick = go.add_mutually_exclusive_group(required=True)
    pick.add_argument("--ids", nargs="+", help="question ids, such as q13 h09")
    pick.add_argument("--all", action="store_true", help="every question of both sets")
    pick.add_argument("--near-clean", action="store_true", help="the held-out set and the 13 near-clean existing questions")
    go.add_argument("--seeds", nargs="+", type=int, default=[0])
    go.add_argument("--examples", choices=["on", "off"], default="on")
    go.add_argument("--run", help="a run id to resume")
    for name in ("score", "report"):
        p = commands.add_parser(name)
        p.add_argument("runs", nargs="+")
    args = parser.parse_args()
    questions = load_questions()
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
