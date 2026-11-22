"""Replay mode: recorded model replies, given to the real agent loop (react.Conversation) and its real tools, so the
page is built and tested without the model server or the GPU.

A recording is one conversation from data/experiments/: a session of ask.py (data/experiments/sessions/*.jsonl, its
turns in order), or one question of a react.py or harness run (<run>/traces.jsonl). Each turn's trace keeps every
step's thinking, reply and tool calls, which ReplayModel hands back in order while the loop runs the tools itself.

The held-out set's traces are never read:
- a run whose name has "heldout" is skipped whole;
- a record with a set field counts only if it's "existing";
- a record without one (sessions and react.py runs) counts only from before the held-out set existed (HELDOUT_BEGAN),
  since such a record can't say which set its question came from.
heldout.toml and heldout_checks.py are never opened.
"""

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

HELDOUT_BEGAN = "20261108"  # the held-out set was verified on 2026-11-08 (CLAUDE.md)
OWN = {"web"}  # the app's own live transcripts aren't recordings


class Mismatch(RuntimeError):
    """The current agent asked for a step the recording doesn't have: it behaves differently from the recorded one."""


def normalized(question):
    """A question as recordings are matched: case, spacing and closing punctuation don't count."""
    return re.sub(r"\s+", " ", question).strip().rstrip("?.! ").casefold()


@dataclass
class Recording:
    source: str  # the run's or the session's name
    date: str  # YYYYMMDD, from the name
    seed: int | None
    turns: list = field(default_factory=list)  # traces, in order

    @property
    def questions(self):
        return [normalized(t["question"]) for t in self.turns]


def date_of(name):
    found = re.match(r"(\d{8})", name)
    return found.group(1) if found else ""


def allowed(record, date):
    """Whether a record may be replayed: never one of the held-out set's (the module docstring)."""
    if "set" in record:
        return record["set"] == "existing"
    return bool(date) and date < HELDOUT_BEGAN


def default_agent(folder):
    """Whether a run recorded the agent replay mode plays: the Ollama backend with the templates. The Sonnet experiment's
    runs (2026-11-22, backend "anthropic", one arm with templates "off") recorded another agent, and were newer than
    the demo's own recordings, so the demo replayed run_sql answers without cards."""
    try:
        header = json.loads((folder / "header.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return header.get("backend") in (None, "ollama") and header.get("templates") in (None, "on")


def recordings(root, runs=None):
    """Every recording under data/experiments (root), or only those of the named runs (directory names, or "sessions")."""
    root = Path(root)
    found = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        name = folder.name
        if "heldout" in name or name in OWN or (runs is not None and name not in runs):
            continue
        if name == "sessions":
            for path in sorted(folder.glob("*.jsonl")):
                records = read(path)
                date = date_of(path.stem)
                if records and all(allowed(r, date) for r in records):
                    found.append(Recording(f"session {path.stem}", date, (records[0].get("seeds") or [None])[0],
                                           sorted(records, key=lambda r: r.get("turn", 0))))
            continue
        path = folder / "traces.jsonl"
        if not path.exists() or not default_agent(folder):
            continue
        date = date_of(name)
        for record in read(path):
            if allowed(record, date):
                found.append(Recording(name, date, record.get("seed"), [record]))
    return found


def read(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class Index:
    """The recordings, found by the questions of a conversation so far."""

    def __init__(self, found):
        self.recordings = found

    def match(self, asked, current=None):
        """The recording to replay the last of the questions asked (all of the conversation's, in order): one whose
        first turns are those questions. The one already playing comes first, then the newest, at seed 0 if it has one.
        None if there's no such recording."""
        asked = [normalized(q) for q in asked]
        fits = [r for r in self.recordings if r.questions[:len(asked)] == asked]
        if current in fits:
            return current
        fits.sort(key=lambda r: (r.date, r.seed == 0 or r.seed is None), reverse=True)
        return fits[0] if fits else None

    def questions(self):
        """Every first question there's a recording of, once each, in its recorded spelling."""
        seen = {}
        for r in self.recordings:
            seen.setdefault(r.questions[0], r.turns[0]["question"])
        return list(seen.values())

    def has(self, question):
        return self.match([question]) is not None


def reply(step):
    """A recorded step as the model server's /api/chat response."""
    calls = [{"function": {"name": c.get("name"), "arguments": c.get("arguments")}} for c in step.get("tool_calls", [])]
    return {"message": {"role": "assistant", "content": step.get("content") or "", "thinking": step.get("thinking") or "",
                        "tool_calls": calls},
            "done_reason": step.get("done_reason") or "stop", "prompt_eval_count": step.get("prompt_tokens"),
            "prompt_eval_cached_count": step.get("cached_tokens"), "eval_count": step.get("output_tokens")}


class ReplayModel:
    """The model of one recorded turn: its steps' replies in order, each after its recorded time scaled by speed (a
    tenth by default) and capped at most seconds. Raises Mismatch when the loop asks for more steps than were recorded."""

    def __init__(self, trace, speed=0.1, most=2.0, sleep=time.sleep):
        self.steps, self.used, self.speed, self.most, self.sleep = list(trace.get("steps", [])), 0, speed, most, sleep

    def __call__(self, messages, **model):
        if self.used >= len(self.steps):
            raise Mismatch(f"the current agent asked for step {self.used + 1}, and the recording has {len(self.steps)}:"
                           " the agent has changed since it was recorded (a check may now send an answer back)")
        step = self.steps[self.used]
        self.used += 1
        wait = min(self.most, (step.get("seconds") or 0) * self.speed)
        if wait > 0:
            self.sleep(wait)
        return reply(step)

    @property
    def left(self):
        return len(self.steps) - self.used


class ReplayRetriever:
    """The worked examples a recorded turn retrieved, given back for its question (retrieval.Retriever's retrieve)."""

    def __init__(self):
        self.trace = None

    def retrieve(self, question):
        """The recorded turn's examples; for a turn recorded without any (retrieval off), none, in retrieval's own
        shape, since the agent reads what it was given (react.Conversation.examples)."""
        found = self.trace.get("examples") if self.trace else None
        return found or {"threshold": None, "candidates": 0, "examples": [],
                         "skipped": "the recording retrieved no examples"}
