"""Ask the agent a question yourself: the ReAct prototype of agent/react.py, with its model (qwen3:8b, thinking on,
seed 0 unless --seed says otherwise), tools, prompt and retrieved examples (agent/retrieval.py). The Ollama server's
address is OLLAMA_BASE_URL in .env.

    py -3.14 agent/ask.py "Who has megd played with in 2v2 tournaments?"  one question: prints the answer
    py -3.14 agent/ask.py --trace "..."                                    also prints each step as it finishes
    py -3.14 agent/ask.py --seed 3 "..."                                   another sampling seed
    py -3.14 agent/ask.py                                                  a session: questions one after another
    python agent/ask.py --examples off "..."                               without examples, on any Python

Retrieval needs chromadb, which this machine's ARM64 Python can't install, so it runs under the x64 Python 3.14.

In a session, a follow-up builds on what came before ("now only 2v2"). The conversation keeps every question and
answer, and the previous question's tool calls and observations in full (react.Conversation). "exit" ends it.

Each session's transcript, every step in full, goes to data/experiments/sessions/<start>.md and .jsonl (git-ignored),
rewritten after each question.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import react
from platform_clients import load_env  # in ingest/, which react puts on the path

SESSIONS = react.RAW / "sessions"
EXIT = {"exit", "quit"}


# What --trace prints

def thought(thinking, width=240):
    """A step's thinking in short: its last sentences, where the model settles what to do next."""
    text = " ".join(thinking.split())
    if not text:
        return "(no thinking)"
    kept = ""
    for sentence in reversed(re.split(r"(?<=[.!?])\s+", text)):
        if kept and len(sentence) + 1 + len(kept) > width:
            break
        kept = f"{sentence} {kept}".strip()
    if len(kept) > width:
        kept = kept[-width:]
    return kept if kept == text else "... " + kept


def observed(text, rows=5, width=150):
    """An observation in short, as lines: the resolver's status and candidates, a query's row count and first rows
    (or only its columns, if it was too large to show), or the error."""
    data = json.loads(text)
    if "error" in data:
        return [f"error: {react.short(data['error'], width)}"]
    if "events" in data:
        return [react.short(f"{data['status']}: {data.get('event_count', 0)} events, {data.get('matched', 'no match')};"
                            f" sql {data.get('sql')}", 2 * width)]
    if "status" in data:
        found = "; ".join(f"{c['player_id']} {c['name']} ({c['match']}, score {c['score']},"
                          f" {c['official_results']} official results)" for c in data["candidates"][:3])
        return [react.short(f"{data['status']}: {found}" if found else data["status"], 2 * width)]
    columns = " | ".join(map(str, data["columns"]))
    if "rows" not in data:  # over the token budget (tools.TOKEN_BUDGET)
        return [f"{data['row_count']} rows, too large to show: no rows went to the model", react.short(columns, width)]
    if "diagnosis" in data:
        return ["0 rows", react.short(data["diagnosis"]["note"], 3 * width)]
    lines = [f"{data['row_count']} row{'' if data['row_count'] == 1 else 's'}", columns]
    lines += [" | ".join("NULL" if v is None else str(v) for v in row) for row in data["rows"][:rows]]
    if len(data["rows"]) > rows:
        lines.append(f"({len(data['rows']) - rows} more rows went to the model)")
    return [react.short(line, width) for line in lines]


def step_lines(step):
    """A step as --trace prints it: the thought in short, each tool call with its observation, any answer check."""
    lines = [f"Step {step['step']} ({step['seconds']:.1f} s): {thought(step['thinking'])}"]
    for call in step["tool_calls"]:
        args = call["arguments"] if isinstance(call["arguments"], dict) else {}
        what = args.get("query" if call["name"] == "run_sql" else "name", call["arguments"])
        lines.append(f"  -> {call['name']}: {react.short(what, 300)}")
        if call["observation"] is None:
            lines.append("  <- not run: no steps left")
        else:
            first, *rest = observed(call["observation"])
            lines += [f"  <- {first}"] + [f"     {line}" for line in rest]
    if step.get("suggestions"):
        lines.append(f"  !! low-confidence match for {', '.join(step['suggestions'])}: the user is asked which one")
    size = step.get("size_check")
    if size:
        lines.append(f"  !! result-size check: answered right after a result too large to show ({size['action']})")
    lookup = step.get("lookup_check")
    if lookup:
        lines.append(f"  !! lookup check: answered right after no row had {' and '.join(lookup['conditions'])}"
                     f" ({lookup['action']})")
    told = step.get("no_tool_check")
    if told:
        lines.append(f"  !! no-tool check: no tool was called, yet it states {', '.join(told['facts'])}"
                     f" ({told['action']})")
    check = step.get("answer_check")
    if check:
        lines.append(f"  !! answer check: it {react.unreturned(check['names'], check.get('ids') or [])}, which no tool"
                     f" returned ({check['action']})")
    return lines


def report(trace, out):
    """The answer, and what it took."""
    out("")
    out(trace["answer"] if trace["outcome"] in ("answered", "suggestions") else
        f"(No answer: {trace['outcome']}.)" + (f"\n{trace['answer']}" if trace["answer"] else ""))
    steps = trace["steps_used"]
    out(f"({steps} step{'' if steps == 1 else 's'}, {trace['model_seconds']} s)")


# A session

class Session:
    """Questions to one conversation, with the transcript rewritten after each: <path>.md and <path>.jsonl."""

    def __init__(self, conversation, path, header):
        self.conversation, self.path, self.header, self.traces = conversation, Path(path), header, []

    def ask(self, question):
        trace = {"turn": len(self.traces) + 1, **self.conversation.ask(question)}
        self.traces.append(trace)
        self.save()
        return trace

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_suffix(".jsonl"), "w", encoding="utf-8") as f:
            for trace in self.traces:
                f.write(json.dumps({**self.header, **trace}, ensure_ascii=False) + "\n")
        self.path.with_suffix(".md").write_text(react.markdown(self.traces, self.header) + "\n", encoding="utf-8")


def interactive(session, read=input, out=print):
    """Questions one after another, until "exit" or the end of the input."""
    out('Ask about official Brawlhalla results. Follow-ups build on the answers before them; "exit" quits.')
    while True:
        try:
            question = read("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            out("")
            break
        if question.lower() in EXIT:
            break
        if question:
            report(session.ask(question), out)


def main(argv=None, read=input, out=print):
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Ask the agent a question (the ReAct prototype, on eval-v1). Without"
                                                 " a question, start a session: questions one after another.")
    parser.add_argument("question", nargs="*", help="the question (quotes are optional)")
    parser.add_argument("--trace", action="store_true", help="also print each step: its thinking in short, its tool"
                                                             " calls and their observations")
    parser.add_argument("--seed", type=int, default=0, help="the sampling seed (default: 0, as react.py's)")
    parser.add_argument("--examples", choices=["on", "off"], default="on", help="retrieve worked examples for each"
                                                                                " question (default: on; needs chromadb)")
    args = parser.parse_args(argv)
    load_env()
    start = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        header = react.run_header(start, seeds=[args.seed], title=f"Agent session {start}",
                                  examples=react.examples_header(args.examples == "on"))
    except KeyError:
        sys.exit("OLLAMA_BASE_URL isn't set: add it to .env (see .env.example).")
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f"The Ollama server at {os.environ['OLLAMA_BASE_URL']} isn't reachable: {e}")
    out("Loading the players' names...")
    retriever = react.retriever_or_exit(args.examples == "on", parser.error)
    show = (lambda step: [out(line) for line in step_lines(step)]) if args.trace else None
    conversation = react.Conversation(react.Tools(), log=lambda *_: None, on_step=show, retriever=retriever,
                                      model=react.MODEL, think=True, seed=args.seed)
    session = Session(conversation, SESSIONS / start, header)
    if args.question:
        report(session.ask(" ".join(args.question)), out)
    else:
        interactive(session, read, out)
    if session.traces:
        out(f"\nTranscript: {session.path.with_suffix('.md').relative_to(react.ROOT).as_posix()}")


if __name__ == "__main__":
    main()
