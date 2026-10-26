"""Retrieval of worked examples (agent/examples/examples.toml): questions of common shapes with the queries that
answer them, shown to the model beside a user's question as query patterns.

    python agent/retrieval.py check          run every example's query on eval-v1, and check its players aren't the
                                             evaluation set's

The database itself isn't embedded: run_sql is the agent's structured retrieval, and the examples add retrieval by
meaning over how questions are answered.
"""

import argparse
import re
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
from names import fold  # noqa: E402
from tools import SNAPSHOT, connect, run_sql  # noqa: E402

EXAMPLES = ROOT / "agent" / "examples" / "examples.toml"
EVALUATION = [ROOT / "eval" / "questions" / "questions.toml", ROOT / "ingest" / "target_questions.py"]
FIELDS = {"id", "shape", "question", "note", "sql"}
PLAYER_IDS = re.compile(r"\b(?:player_id|partner_id|opponent_id|opponent1_id|opponent2_id)\s*(?:=\s*(-?\d+)|IN\s*\(([-\d,\s]+)\))", re.I)


def load(path=EXAMPLES):
    """The examples, each a dict with id, shape, question, note, sql and, for a query whose right result is empty,
    expect = 'empty'. A missing field or a repeated id is an error."""
    with open(path, "rb") as f:
        examples = tomllib.load(f)["example"]
    for e in examples:
        missing = FIELDS - set(e)
        if missing:
            raise ValueError(f"example {e.get('id')!r} has no {', '.join(sorted(missing))}")
    ids = [e["id"] for e in examples]
    if len(set(ids)) != len(ids):
        raise ValueError(f"repeated example ids: {sorted({i for i in ids if ids.count(i) > 1})}")
    return examples


def player_ids(sql):
    """The player IDs a query filters on."""
    found = []
    for one, many in PLAYER_IDS.findall(sql):
        found += [int(one)] if one else [int(n) for n in many.split(",") if n.strip()]
    return found


def check(examples, path=SNAPSHOT):
    """Each example's problems on the snapshot: its query fails, is too large to show, has rows when it should have
    none or none when it should have some, or filters on a player the evaluation set names. {id: [problem]}, and the
    run's lines to print."""
    evaluation = fold(" ".join(p.read_text(encoding="utf-8") for p in EVALUATION))
    db = connect(path, 30)
    names = dict(db.execute("SELECT player_id, name FROM players"))
    db.close()
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
        for pid in player_ids(e["sql"]):
            name = names.get(pid)
            if name is None:
                found.append(f"no player {pid}")
            elif fold(name) in evaluation or fold(name.split("|")[-1].strip()) in evaluation:
                found.append(f"{name} ({pid}) is named in the evaluation set")
        if found:
            problems[e["id"]] = found
        first = out.get("rows", [None])[0] if out.get("rows") else None
        lines.append(f"{e['id']} {e['shape']:<18} {out.get('row_count', '-')!s:>4} rows {seconds:5.2f} s"
                     f"  {'; '.join(found) if found else first}")
    return problems, lines


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Retrieval of worked examples for the agent.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="run every example's query on eval-v1")
    args = parser.parse_args()
    examples = load()
    if args.command == "check":
        problems, lines = check(examples)
        print("\n".join(lines))
        print(f"\n{len(examples)} examples, {len(problems)} with problems")
        sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
