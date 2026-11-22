"""Checkpoint 5's three-agent pipeline (docs/experiments.md, 2026-11-22), an experiment arm beside the frozen single
agent (react.py), which it doesn't change. An analyst looks the answer up, a reporter writes it from what was looked
up, and a verifier checks it.
- The analyst is the agent's loop, stopped before its answer (react.Conversation with evidence_only). Every tool
  call of its turn that returned data, with its result, is the evidence packet (packet_of).
- The reporter is one model call that sees only the question and the packet; revising, its draft and the verifier's
  failures too.
- The verifier runs the loop's own answer checks on the draft in a view of the packet, then one model call that sees
  the question, the packet and the draft, and lists the claims the packet doesn't support (verify).
- A draft that fails goes back to the reporter, at most twice. A packet that can't answer the question goes back to
  the analyst once. Then the pipeline abstains.
LangGraph builds the graph, imported only where it's built, so the rest runs on any Python."""
import json
import re
import time
from dataclasses import asdict, dataclass

import react

# The verifier's model call answers in this form (Ollama's structured outputs)
VERDICT = {"type": "object", "required": ["unsupported", "answers_question", "missing"], "properties": {
    "unsupported": {"type": "array", "items": {"type": "object", "required": ["claim", "why"], "properties": {
        "claim": {"type": "string"}, "why": {"type": "string"}}}},
    "answers_question": {"type": "boolean"},
    "missing": {"type": "string"}}}
# What each kind of the claim check (claim_check.py) is, as the reporter is told of it
CLAIMS = {"referral": "sends the user to the database, though the user can't run queries",
          "judgment": "calls a result wrong, though no result in the packet says the data is wrong",
          "placeholder": "is a placeholder where a fact should be",
          "relaxed": "says a condition was removed, though no query ran without it",
          "characterization": "characterizes a result beyond what its record says: give the record by its numbers",
          "tool": "names the tools or calls used, though the user sees the answer, not the steps",
          "unasked": "speaks of an order the question didn't ask for"}
NO_DATA = "No tool call returned data."


def section(title):
    """A section of the agent's prompt (react.SYSTEM) whose title line starts with title: that line and its bullets,
    to the next blank line."""
    start = react.SYSTEM.index(f"\n\n{title}") + 2
    end = react.SYSTEM.find("\n\n", start)
    return react.SYSTEM[start:end if end != -1 else None]


VERIFIER = """You check a drafted answer to a question about official Brawlhalla esports results against the evidence
packet it was written from: every tool call that returned data, with its result. You see only the question, the
packet and the draft.
- List every claim in the draft that the packet doesn't support: a player, team, event, date, number, placement,
  record or ranking that no result in the packet gives; one the packet gives only for another player, event, mode or
  year; a record written from the other player's side; and a "never", "none" or "only" the packet doesn't show. A
  claim the packet supports in other words is supported. Don't list a claim for its wording or its order, nor for
  saying what the data doesn't cover.
- Then say whether the packet holds what the question asks for. If it doesn't, say in one sentence what's missing,
  as a lookup that would find it.
Reply with JSON only, in this form: {"unsupported": [{"claim": "the draft's words", "why": "what the packet says
instead"}], "answers_question": true, "missing": ""}

""" + section("Counting rules")


@dataclass(frozen=True)
class Failure:
    """What the verifier found wrong with a draft: by code (a check of the loop's) or by the model, the check, the
    draft's words, and why."""
    by: str
    check: str
    claim: str
    why: str


def chat(messages, model=react.MODEL, think=True, seed=0, format=None):
    """One model reply with no tools offered: the reporter's and the verifier's. With format, the reply is JSON in
    that form (Ollama's structured outputs)."""
    payload = {"model": model, "stream": False, "think": think, "messages": messages,
               "options": {**react.OPTIONS, "seed": seed}}
    if format:
        payload["format"] = format
    return react.ollama("/api/chat", payload, timeout=react.REQUEST_SECONDS)


def step_of(role, response, seconds):
    """A model call's step, shaped as the loop's steps are, so the harness counts it the same way."""
    message = response.get("message") or {}
    return {"step": None, "role": role, "seconds": round(seconds, 2), "prompt_tokens": response.get("prompt_eval_count"),
            "cached_tokens": response.get("prompt_eval_cached_count"), "output_tokens": response.get("eval_count"),
            "done_reason": response.get("done_reason"), "thinking": message.get("thinking") or "",
            "content": message.get("content") or "", "tool_calls": []}


def packet_of(trace):
    """The calls of an analyst's turn that returned data, oldest first, as the trace keeps them. A call refused or
    failed (an error) isn't evidence."""
    return [c for s in trace["steps"] for c in s["tool_calls"]
            if c.get("observation") and "error" not in json.loads(c["observation"])]


def result_of(call):
    """A packet call's result, without the loop's note to the model about its last step."""
    result = json.loads(call["observation"])
    result.pop("last_step", None)
    return result


def shown(packet):
    """The packet as the reporter and the verifier read it: each call, its arguments and its result."""
    return "\n\n".join(f"[{n}] {c['name']} {json.dumps(react.parsed(c['arguments']), ensure_ascii=False)}\n"
                       f"{json.dumps(result_of(c), ensure_ascii=False)}" for n, c in enumerate(packet, 1)) or NO_DATA


def checker(tools, question, packet):
    """A conversation that never asks the model, whose view holds the question and the packet as the loop's holds
    a turn's: the verifier runs the loop's answer checks in it."""
    conversation = react.Conversation(tools, ask=None, log=lambda *_: None)
    conversation.view.ask(question)
    for c in packet:
        conversation.view.observe(c["name"], result_of(c), c.get("arguments"))
    return conversation


def resolved_in(question, packet):
    """The question's players that resolve_player decided, as the loop's names correction takes them (react.noted)."""
    resolved = []
    for c in packet:
        react.noted(question, c["name"], result_of(c), [], resolved)
    return resolved


def emptied(packet):
    """Whether the packet's last query found no rows (its result has a diagnosis): a claim to have removed a
    condition is then checked, as in the loop."""
    queries = [c for c in packet if c["name"] in react.QUERIES]
    return bool(queries) and "diagnosis" in result_of(queries[-1])


def code_failures(conversation, question, packet, draft):
    """The loop's answer checks on a draft, in the order the loop runs them: a name beside another player's player_id
    (the pairing check), names and player_ids no result returned (the answer check, with plain names after a result
    that gives player_ids alone), the claim check, and numbers no result holds (the number check)."""
    view, resolver = conversation.view, conversation.tools.resolver
    in_view = view.returned_now | view.returned_before
    _, _, pairings = react.correct_names(draft, resolved_in(question, packet), resolver, in_view)
    failures = [Failure("code", "pairing", react.paired_as(p), "pairs a name with another player's player_id")
                for p in pairings]
    names = view.unreturned(draft)
    if view.nameless():
        names.update({c.text: [] for c in view.named_claims(draft, question, conversation.tools.events.words)})
    failures += [Failure("code", "name", name, "names a player no result in the packet returned") for name in names]
    failures += [Failure("code", "id", str(pid), "cites a player_id no result in the packet returned")
                 for pid in view.unreturned_ids(draft)]
    failures += [Failure("code", c.kind, c.text, CLAIMS.get(c.kind, "isn't supported by the packet"))
                 for c in conversation.wrong(draft, question, False, emptied(packet))]
    for c in view.window.unsupported(view.without_ids(draft)):
        why = (f"is {c.about}'s record written the other way round" if c.reversed
               else f"is held in the packet only for another player or mode than {c.about}" if c.about
               else "is a number no result in the packet holds")
        failures.append(Failure("code", "number", c.text, why))
    return failures


def verdict_of(content):
    """The verifier model's reply as {"unsupported": [{"claim", "why"}], "answers_question", "missing"}, or None when
    it isn't that JSON."""
    found = re.search(r"\{.*\}", content, re.S)
    try:
        out = json.loads(found.group(0) if found else content)
    except json.JSONDecodeError:
        return None
    if not isinstance(out, dict) or not isinstance(out.get("unsupported"), list):
        return None
    claims = [u for u in out["unsupported"] if isinstance(u, dict) and str(u.get("claim") or "").strip()]
    return {"unsupported": [{"claim": str(u["claim"]).strip(), "why": str(u.get("why") or "").strip()} for u in claims],
            "answers_question": out.get("answers_question") is not False,
            "missing": str(out.get("missing") or "").strip()}


def verify(tools, question, packet, draft, reply=chat, **model):
    """The verifier: the loop's answer checks on the draft (code_failures), then one model call that sees the
    question, the packet and the draft. Returns its failures, what the packet lacks for the question ('' when it
    holds it), and the model call's step, which records both. A reply that isn't the JSON asked for adds no failure
    and is marked unparsed."""
    failures = code_failures(checker(tools, question, packet), question, packet, draft) if draft else [
        Failure("code", "empty", "", "no answer was written")]
    messages = [{"role": "system", "content": VERIFIER},
                {"role": "user", "content": f"Question: {question}\n\nEvidence packet:\n{shown(packet)}\n\n"
                                            f"Draft answer:\n{draft}"}]
    begun = time.monotonic()
    response = reply(messages, format=VERDICT, **model)
    step = step_of("verifier", response, time.monotonic() - begun)
    verdict = verdict_of(step["content"])
    failures += [Failure("model", "unsupported", u["claim"], u["why"]) for u in (verdict or {}).get("unsupported", [])]
    missing = "" if not verdict or verdict["answers_question"] else verdict["missing"] or "what the question asks"
    step["verifier"] = {"failures": [asdict(f) for f in failures], "missing": missing, "parsed": verdict is not None}
    return [asdict(f) for f in failures], missing, step
