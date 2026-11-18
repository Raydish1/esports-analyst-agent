"""Retrieval of worked examples (agent/examples/examples.toml): questions of common shapes with the queries that
answer them, shown to the model beside a user's question as query patterns. An example a template answers
(agent/templates.py) also has the template call, which the model is shown instead of the SQL: shown SQL, it would keep
writing SQL. Its SQL stays as the reference the call is checked against.

    python agent/retrieval.py check          run every example's query and call on eval-v1, check that each call's
                                             result holds every row of the query's, and that its players aren't the
                                             evaluation set's
    py -3.14 agent/retrieval.py retrieve "question"
                                             the examples a question retrieves, with their scores

Only the examples' question text is embedded, with nomic-embed-text through Ollama (OLLAMA_BASE_URL), and stored in
a local Chroma collection (data/rag/chroma, git-ignored), rebuilt whenever the bank or the embedding changes. For a
user's question, the CANDIDATES most similar examples above THRESHOLD go through maximal marginal relevance (MMR),
which keeps the K that are similar to the question but not to each other. The database itself isn't embedded:
run_sql is the agent's structured retrieval, and the examples add retrieval by meaning over how questions are
answered.

Chroma runs only where its index library (chroma-hnswlib) has a build: not on Windows ARM64's Python, so on this
machine the agent runs with the x64 Python under emulation (py -3.14), and react.py and ask.py take --examples off
without it. Everything else here is the standard library.
"""

import argparse
import ast
import hashlib
import json
import math
import os
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
from names import fold  # noqa: E402
from tools import SNAPSHOT, connect, player_ids, run_sql, tables  # noqa: E402

EMBED_MODEL = "nomic-embed-text"
# nomic-embed-text's task prefix for comparing texts of one kind, here a question with questions. On the evaluation
# set's questions (docs/experiments.md, 2026-10-25), a relevant shape was in the top 3 for 35 of 39 with it, 36 with no
# prefix, 34 with search_query on both sides, and 30 with the search_query/search_document pair meant for passages.
PREFIX = "clustering: "
THRESHOLD = 0.70  # about the 10th percentile of the best relevant example's similarity on the evaluation set
CANDIDATES = 10
K = 3
LAMBDA = 0.7  # MMR: weight of similarity to the question against similarity to the examples already chosen
STORE = ROOT / "data" / "rag" / "chroma"
COLLECTION = "sql_examples"
NOTE = ("Worked examples, retrieved for questions shaped like this one. They show query patterns, not facts about"
        " players: their players, events and IDs are the examples' own. Look up this question's players and events"
        " with the tools, and answer only from what the tools return.")
EXAMPLES = ROOT / "agent" / "examples" / "examples.toml"
EVALUATION = [ROOT / "eval" / "questions" / "questions.toml", ROOT / "ingest" / "target_questions.py"]
FIELDS = {"id", "shape", "question", "note", "sql"}


def load(path=EXAMPLES):
    """The examples, each a dict with id, shape, question, note, sql and, for a query whose right result is empty,
    expect = 'empty'; and for an example a template answers, call and call_note (calls). A missing field, a call that
    doesn't parse or a repeated id is an error."""
    with open(path, "rb") as f:
        examples = tomllib.load(f)["example"]
    for e in examples:
        missing = FIELDS - set(e)
        if "call" in e and "call_note" not in e:
            missing.add("call_note")
        if missing:
            raise ValueError(f"example {e.get('id')!r} has no {', '.join(sorted(missing))}")
        calls(e)
    ids = [e["id"] for e in examples]
    if len(set(ids)) != len(ids):
        raise ValueError(f"repeated example ids: {sorted({i for i in ids if ids.count(i) > 1})}")
    return examples


def calls(example):
    """The template calls an example shows, as (tool, arguments): its call, one a line, written tool(argument=value,
    ...); none for an example without one."""
    out = []
    for line in example.get("call", "").strip().splitlines():
        try:
            node = ast.parse(line.strip(), mode="eval").body
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.args:
                raise ValueError
            out.append((node.func.id, {k.arg: ast.literal_eval(k.value) for k in node.keywords}))
        except (SyntaxError, ValueError):
            raise ValueError(f"example {example.get('id')!r}: {line.strip()!r} isn't a call with named arguments,"
                             " such as player_results(player_id=1, top=1)") from None
    return out


def cells(row):
    """A row's values as the check compares them: a list's items, and the names in a ' / '-joined cell (a team, an
    event's tournament and event), each on its own, since a query may join them in another order."""
    out = []
    for v in row:
        out += v if isinstance(v, list) else v.split(" / ") if isinstance(v, str) and " / " in v else [v]
    return out


def check(examples, path=SNAPSHOT):
    """Each example's problems on the snapshot: its query fails, is too large to show, has rows when it should have
    none or none when it should have some, or filters on a player the evaluation set names; its call fails, or its
    result doesn't hold every row of the query's (held). {id: [problem]}, and the run's lines to print."""
    import react  # here: react imports this module
    evaluation = fold(" ".join(p.read_text(encoding="utf-8") for p in EVALUATION))
    db = connect(path, 30)
    names = dict(db.execute("SELECT player_id, name FROM players"))
    db.close()
    agent_tools = react.Tools(path) if any(e.get("call") for e in examples) else None
    problems, lines = {}, []
    for e in examples:
        begun = time.monotonic()
        out = run_sql(e["sql"], path)
        seconds = time.monotonic() - begun
        found = []
        if "error" in out:
            found.append(f"error: {out['error']}")
        elif out["complete"] is False:
            found.append(f"too large to show: {out['row_count']} rows")
        elif (out["row_count"] == 0) != (e.get("expect") == "empty"):
            found.append(f"{out['row_count']} rows, expected {'none' if e.get('expect') == 'empty' else 'some'}")
        for pid in dict.fromkeys(player_ids(e["sql"] + "\n" + e.get("call", ""))):
            name = names.get(pid)
            if name is None:
                found.append(f"no player {pid}")
            elif fold(name) in evaluation or fold(name.split("|")[-1].strip()) in evaluation:
                found.append(f"{name} ({pid}) is named in the evaluation set")
        timed = ""
        if e.get("call"):
            begun = time.monotonic()
            found += held(e, out.get("rows", []), agent_tools)
            timed = f", call {time.monotonic() - begun:5.2f} s"
        if found:
            problems[e["id"]] = found
        first = out.get("rows", [None])[0] if out.get("rows") else None
        lines.append(f"{e['id']} {e['shape']:<18} {out.get('row_count', '-')!s:>4} rows {seconds:5.2f} s{timed}"
                     f"  {'; '.join(found) if found else first}")
    return problems, lines


def held(example, rows, agent_tools):
    """The problems of an example's calls against its query's rows: a call that fails, or a row of the query's that no
    row of the calls' tables holds, compared as stage 2 of the evaluation compares (result_checks.has, on cells)."""
    if str(ROOT / "eval") not in sys.path:
        sys.path.insert(0, str(ROOT / "eval"))
    from result_checks import has
    shown, found = [], []
    for name, arguments in calls(example):
        observation = agent_tools.call(name, arguments)
        if "error" in observation:
            found.append(f"{name} failed: {observation['error']}")
        shown += [cells(row) for _, table_rows in tables(observation) for row in table_rows]
    missing = [row for row in rows if not any(has(s, [v for v in cells(row) if v is not None]) for s in shown)]
    if missing:
        found.append(f"the call's result holds {len(rows) - len(missing)} of the query's {len(rows)} rows, not {missing[0]}")
    return found


# Embedding and retrieval

def ollama_embed(texts):
    """The embeddings of some texts, from nomic-embed-text through the Ollama server."""
    url = os.environ["OLLAMA_BASE_URL"].rstrip("/") + "/api/embed"
    request = urllib.request.Request(url, data=json.dumps({"model": EMBED_MODEL, "input": list(texts)}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)["embeddings"]


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a) * sum(y * y for y in b)) or 1.0)


def mmr(candidates, k=K, lam=LAMBDA):
    """Maximal marginal relevance over (id, similarity to the question, vector): each pick has the most similarity
    to the question less similarity to the picks before it, weighted by lam. [(id, similarity, score)], in order."""
    chosen, left = [], list(candidates)
    while left and len(chosen) < k:
        def score(c):
            return lam * c[1] - (1 - lam) * max((cosine(c[2], p[2]) for p in chosen), default=0.0)
        best = max(left, key=score)
        chosen.append((*best, score(best)))
        left.remove(best)
    return [(i, similarity, s) for i, similarity, _, s in chosen]


def fingerprint(examples, prefix=PREFIX):
    """What the stored embeddings depend on: the model, the prefix and every example's question."""
    text = json.dumps([EMBED_MODEL, prefix, [(e["id"], e["question"]) for e in examples]], ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Retriever:
    """The examples' questions embedded in a Chroma collection, and the examples a question retrieves. client is a
    Chroma client (default: the persistent store), embed the embedding function (default: Ollama), prefix the task
    prefix put before every question embedded."""

    def __init__(self, examples=None, embed=ollama_embed, client=None, path=STORE, prefix=PREFIX):
        import chromadb  # only here: it has no build for Windows ARM64's Python (the module docstring)
        self.examples = {e["id"]: e for e in examples or load()}
        self.embed, self.prefix = embed, prefix
        if client is None:
            path.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(path), settings=chromadb.Settings(anonymized_telemetry=False))
        stamp = fingerprint(self.examples.values(), prefix)
        try:
            collection = client.get_collection(COLLECTION)
            if (collection.metadata or {}).get("fingerprint") != stamp:
                client.delete_collection(COLLECTION)
                collection = None
        except Exception:  # chromadb raises its own NotFoundError, whose class differs between versions
            collection = None
        if collection is None:
            collection = client.create_collection(COLLECTION, embedding_function=None,
                                                  metadata={"hnsw:space": "cosine", "fingerprint": stamp})
            ids = list(self.examples)
            collection.add(ids=ids, documents=[self.examples[i]["question"] for i in ids],
                           embeddings=self.embed([prefix + self.examples[i]["question"] for i in ids]),
                           metadatas=[{"shape": self.examples[i]["shape"]} for i in ids])
        self.collection = collection

    def retrieve(self, question, k=K, threshold=THRESHOLD):
        """{threshold, candidates, examples}: the examples for a question, best first, each with its id, shape,
        question, sql, note, its similarity to the question and its MMR score. candidates counts the examples above
        the threshold among the CANDIDATES most similar."""
        vector = self.embed([self.prefix + question])[0]
        found = self.collection.query(query_embeddings=[vector], n_results=min(CANDIDATES, len(self.examples)),
                                      include=["distances", "embeddings"])
        above = [(i, 1 - d, list(v)) for i, d, v in zip(found["ids"][0], found["distances"][0], found["embeddings"][0])
                 if 1 - d >= threshold]
        picked = [{**{f: self.examples[i][f] for f in ("id", "shape", "question", "sql", "note", "call", "call_note")
                      if f in self.examples[i]},
                   "similarity": round(similarity, 3), "mmr": round(score, 3)} for i, similarity, score in mmr(above, k)]
        return {"threshold": threshold, "candidates": len(above), "examples": picked}


def measure(retriever, questions, shapes, threshold=THRESHOLD):
    """Retrieval alone, per question: the examples it retrieves (id, shape, similarity), the shapes that would help
    (shapes, by question id), whether one of them is in the top K (hit) and first (first). hit and first are None for
    a question no shape helps."""
    rows = []
    for q in questions:
        found = retriever.retrieve(q["question"], threshold=threshold)
        top = [(e["id"], e["shape"], e["similarity"]) for e in found["examples"]]
        relevant = set(shapes.get(q["id"], ()))
        rows.append({"id": q["id"], "question": q["question"], "relevant": sorted(relevant), "retrieved": top,
                     "hit": bool(relevant & {s for _, s, _ in top}) if relevant else None,
                     "first": bool(top) and top[0][1] in relevant if relevant else None})
    return rows


def summarize(rows):
    """hit@K and hit@1 over the questions some shape helps, and the examples retrieved for the others."""
    labelled = [r for r in rows if r["relevant"]]
    others = [r for r in rows if not r["relevant"]]
    return {"questions": len(rows), "labelled": len(labelled), "hit_at_k": sum(r["hit"] for r in labelled),
            "hit_at_1": sum(r["first"] for r in labelled),
            "examples_for_labelled": sum(len(r["retrieved"]) for r in labelled),
            "unlabelled": len(others), "examples_for_unlabelled": sum(len(r["retrieved"]) for r in others),
            "misses": [r["id"] for r in labelled if not r["hit"]]}


def prompt(question, retrieved):
    """The question as the model reads it: the retrieved examples first, with what they are, then the question. An
    example with a template call shows the call and why, instead of its SQL."""
    if not retrieved or not retrieved.get("examples"):
        return question
    parts = [NOTE, ""]
    for n, e in enumerate(retrieved["examples"], 1):
        shown, why = (e["call"], e["call_note"]) if e.get("call") else (e["sql"], e["note"])
        parts += [f"Example {n}: {e['question']}", shown.strip(), f"Why: {why}", ""]
    return "\n".join(parts + [f"Question: {question}"])


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Retrieval of worked examples for the agent.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="run every example's query on eval-v1")
    ask = commands.add_parser("retrieve", help="the examples a question retrieves, with their scores")
    ask.add_argument("question", nargs="+")
    scored = commands.add_parser("measure", help="retrieval alone on the evaluation set: is a helpful example shape"
                                                 " in the top 3? Writes eval/results/<time>-retrieval.json")
    scored.add_argument("--prefix", help="another task prefix, compared without a threshold in a store of its own")
    args = parser.parse_args()
    examples = load()
    if args.command == "check":
        problems, lines = check(examples)
        print("\n".join(lines))
        print(f"\n{len(examples)} examples, {len(problems)} with problems")
        sys.exit(1 if problems else 0)
    from platform_clients import load_env  # in ingest/
    load_env()
    if args.command == "measure":
        report(examples, args.prefix)
        return
    found = Retriever(examples).retrieve(" ".join(args.question))
    print(f"{found['candidates']} candidates above {found['threshold']}")
    for e in found["examples"]:
        print(f"  {e['id']} {e['shape']:<18} similarity {e['similarity']:.3f}, MMR {e['mmr']:.3f}: {e['question']}")


def report(examples, prefix=None):
    """measure on the evaluation set, printed and written to eval/results: with the agent's settings, and with no
    threshold; or, for another prefix, with no threshold only."""
    from datetime import datetime, timezone
    with open(ROOT / "eval" / "questions" / "questions.toml", "rb") as f:
        questions = tomllib.load(f)["question"]
    with open(ROOT / "eval" / "questions" / "shapes.toml", "rb") as f:
        shapes = tomllib.load(f)["shapes"]
    if prefix is None:
        retriever, runs = Retriever(examples), {"agent": THRESHOLD, "no threshold": 0.0}
    else:
        import chromadb
        retriever = Retriever(examples, client=chromadb.EphemeralClient(settings=chromadb.Settings(anonymized_telemetry=False)),
                              prefix=prefix)
        runs = {"no threshold": 0.0}
    out = {"model": EMBED_MODEL, "prefix": retriever.prefix, "k": K, "candidates": CANDIDATES, "lambda": LAMBDA,
           "bank": len(examples), "runs": {}}
    for name, threshold in runs.items():
        rows = measure(retriever, questions, shapes, threshold)
        summary = summarize(rows)
        out["runs"][name] = {"threshold": threshold, **summary, "rows": rows}
        print(f"{name} (threshold {threshold}): a helpful shape in the top {K} for {summary['hit_at_k']} of"
              f" {summary['labelled']}, first for {summary['hit_at_1']}; {summary['examples_for_labelled']} examples for"
              f" them, {summary['examples_for_unlabelled']} for the {summary['unlabelled']} no shape helps;"
              f" misses {summary['misses']}")
    for r in out["runs"]["no threshold" if prefix else "agent"]["rows"]:
        mark = {True: "hit ", False: "MISS", None: "    "}[r["hit"]]
        print(f"  {mark} {r['id']} {'/'.join(r['relevant']) or '-':<34} "
              + "  ".join(f"{i} {s} {sim:.2f}" for i, s, sim in r["retrieved"]))
    if prefix is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = ROOT / "eval" / "results" / f"{stamp}-retrieval.json"
        path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Results: {path.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
