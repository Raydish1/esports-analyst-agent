"""The question audit (docs/question-audit.md, 2026-11-20): eval/questions/audit.toml asks each kind of question a fan
asks in at least two phrasings. This plays it through eval/conversations.py, as the web app plays a conversation, and
reports the checks that failed by mechanism and by kind, so the mechanisms with the most failures are fixed first
(docs/agent-mechanisms.md). Its checks look at how a turn went, not at verified facts: the set has none.

    py -3.14 eval/audit.py run --seeds 0 1 2     every question, retrieval on (a run resumes)
    python eval/audit.py report RUN              the failed checks by mechanism and by kind, and each failing turn

The user tests the web app's live mode on the same Ollama server, so ask before starting a run.
"""

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import conversations  # noqa: E402
import harness  # noqa: E402

AUDIT = ROOT / "eval" / "questions" / "audit.toml"
MECHANISMS = {"M1": "reading the question", "M2": "the tools", "M3": "facts the model makes", "M4": "the conversation"}


def tally(data, scored):
    """The failed checks by mechanism and by kind, from a run's scored conversations (conversations.score):
    ({group: Counter}, {group: Counter}, [failing turns]). A Counter has the turns, the turns failing any check, and
    each check's failures ('check calls_with'). A conversation probing several mechanisms counts under each."""
    specs = {c["id"]: c for c in data["conversation"]}
    by_mechanism, by_kind, failing = defaultdict(Counter), defaultdict(Counter), []
    for record in scored:
        spec = specs[record["id"]]
        groups = [(by_mechanism, m) for m in spec.get("mechanism", [])] + [(by_kind, spec.get("kind"))]
        for turn in record["turns"]:
            failed = [name for name, c in turn["checks"].items() if not c["passed"]]
            for table, group in groups:
                table[group].update(turns=1, failed=int(bool(failed)))
                table[group].update(f"check {name}" for name in failed)
            if failed:
                failing.append({"id": record["id"], "seed": record["seed"], "turn": turn["turn"], "title": spec["title"],
                                "checks": {n: turn["checks"][n].get("detail", "") for n in failed}})
    return by_mechanism, by_kind, failing


def lines(by_mechanism, by_kind, failing):
    """The report, as Markdown lines: the mechanisms by failing turns, most first, then the kinds, then the turns."""
    def rows(table, label):
        out = []
        for group, counts in sorted(table.items(), key=lambda item: (-item[1]["failed"], str(item[0]))):
            checks = ", ".join(f"{name[6:]} {n}" for name, n in counts.most_common() if name.startswith("check "))
            out.append(f"| {label(group)} | {counts['failed']} of {counts['turns']} | {checks or '-'} |")
        return out
    out = ["## By mechanism, the most failing turns first", "", "| Mechanism | Turns failing | Checks failed |",
           "|---|---|---|", *rows(by_mechanism, lambda m: f"{m} {MECHANISMS.get(m, '')}".strip()), "",
           "## By kind (docs/question-audit.md)", "", "| Kind | Turns failing | Checks failed |", "|---|---|---|",
           *rows(by_kind, lambda k: str(k)), "", "## The failing turns", ""]
    out += [f"- {t['id']} seed {t['seed']} turn {t['turn']} ({t['title']}): " + "; ".join(
        f"{name}{f' ({detail})' if detail else ''}" for name, detail in t["checks"].items()) for t in failing] or ["None."]
    return out


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="The question audit: play the audit set, report failures by mechanism.")
    commands = parser.add_subparsers(dest="command", required=True)
    go = commands.add_parser("run", help="play the audit set through the agent")
    go.add_argument("--seeds", nargs="+", type=int, default=[0])
    go.add_argument("--examples", choices=["on", "off"], default="on")
    go.add_argument("--ids", nargs="+", help="question ids, such as a01 a09")
    go.add_argument("--run", help="a run id to resume")
    reporting = commands.add_parser("report", help="the failed checks by mechanism and by kind")
    reporting.add_argument("run")
    args = parser.parse_args()
    data = conversations.load(AUDIT)
    issues = conversations.problems(data)
    if issues:
        sys.exit("The audit set has problems:\n  " + "\n  ".join(issues))
    if args.command == "run":
        print(conversations.run(data, AUDIT, args.seeds, args.examples == "on", args.run, args.ids))
        return
    db = sqlite3.connect(harness.SNAPSHOT.resolve().as_uri() + "?mode=ro", uri=True)
    names = dict(db.execute("SELECT player_id, name FROM players"))
    scored = conversations.score(data, conversations.load_run(args.run)[1], names)
    path = harness.RESULTS / f"{args.run}-audit.json"
    path.write_text(json.dumps(scored, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n".join([f"# The question audit, run {args.run}", "", *lines(*tally(data, scored))]))


if __name__ == "__main__":
    main()
