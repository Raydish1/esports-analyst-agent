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
import operator
import re
import time
from dataclasses import asdict, dataclass
from typing import Annotated, TypedDict

import claim_check
import react

MAX_REVISIONS, MAX_RETURNS = 2, 1  # Checkpoint 5's limits: a draft revised at most twice, the analyst asked again once
ABSTAIN = react.NOT_CONFIRMED  # the single agent's words when no fact is left
RETURN = "{question}\n\n[What was looked up doesn't answer this yet: {missing} Look up what it still needs.]"
REVISE = ("A checker read your draft against the packet, and found what the packet doesn't support:\n{failures}\n"
          "Write the answer again from the packet: fix each one, or leave the claim out where the packet doesn't hold"
          " it. The user hasn't seen the draft: reply with the answer only, never as a correction of it.")
REPORTER = """You write the answer to a question about official Brawlhalla esports results (official events only, from
{first} on). The data's latest results are from {last}, so every event in it has been held, unless its status says it
wasn't. Another agent looked the answer up. Its evidence packet holds every tool call that returned data, with its
result: the players resolve_player found for the question's names, the events resolve_event found, and the rows. You
have no tools: write the answer from the packet alone, and reply with the answer only.

Reading the packet
- resolve_player: "confident" means the first candidate is the player meant, called by its display the first time you
  name them; "ambiguous" means the first was taken, so say in one short clause which player you took; "not_found"
  means the data has no such player, so say so.
- resolve_event: "ambiguous" means the name matched several tournaments or only some of its words, so say which event
  you took it to mean. Follow a note about an alias, such as 'msi' being a default someone may not mean.
- An event's status: "cancelled" means it wasn't held, and "placements_unreliable" that its placements are left out,
  so say why.
- A template's counts are counted and its ties are all there: don't recount its rows or drop a tied one.
- A career earnings figure is per player. A player with no row has no figure, which isn't $0.
- A series' regional championships (regional is 1: worlds 2020 and 2021): an answer that counts titles says whether it
  counted them.
- If the packet doesn't hold what the question asks, say what it holds and that the rest wasn't found. Never fill the
  gap from memory."""
# The agent prompt's sections the reporter keeps, without what's about calling tools or the loop's steps
READING = ("Reading the question", ["- Pass the question's scope"], [])
ANSWERING = ("Answering", ["- You have at most", "- When the user asks whether", '- A message "[The page showed'], [
    ("- Take every fact from what the tools returned in this conversation, and look facts up in every question,"
     " follow-ups\n  included: never answer from memory.", "- Take every fact from the evidence packet: never answer"
     " from memory."),
    ("- Run every query the answer needs yourself: never tell the user to query the data, a view or a table, or"
     " that\n  further analysis would be needed.", "- Never tell the user to query the data, a view or a table, or"
     " that further analysis would be needed.")])

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


def kept(title, drop, swaps):
    """A section of the agent's prompt without the bullets that start with one of drop, each swap made once."""
    out, skipping = [], False
    for line in section(title).split("\n"):
        if line.startswith("- "):
            skipping = line.startswith(tuple(drop))
        if not skipping:
            out.append(line)
    text = "\n".join(out)
    for old, new in swaps:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


def reporter_prompt(path):
    """The reporter's prompt: its role and how to read the packet, then the agent prompt's reading of the question,
    counting rules and answering, without what's about calling tools (Checkpoint 5: each role gets a shorter prompt
    that covers only its own task)."""
    first, last = react.coverage(path)
    return "\n\n".join([REPORTER.format(first=first, last=last), kept(*READING), section("Counting rules"),
                        kept(*ANSWERING)])


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


class State(TypedDict, total=False):
    """The graph's state: the question; the packet; the draft and the verifier's failures on it, what the packet lacks
    for the question, and the verifier's decision (next); the counters; the answer and its outcome; and, added to by
    every node, its model calls' steps, the analyst's passes and the nodes run (path)."""
    question: str
    packet: list
    draft: str | None
    failures: list
    missing: str
    next: str
    revisions: int
    returns: int
    swaps: list
    answer: str | None
    outcome: str
    steps: Annotated[list, operator.add]
    analyst: Annotated[list, operator.add]
    path: Annotated[list, operator.add]


def route(failures, missing, revisions, returns):
    """The verifier's decision on a draft (Checkpoint 5): a packet that can't answer the question goes back to the
    analyst once ("return"); a draft with no failures is the answer ("pass"); else it goes back to the reporter at
    most twice ("revise"); then the pipeline abstains."""
    if missing and returns < MAX_RETURNS:
        return "return"
    if not failures:
        return "pass"
    return "revise" if revisions < MAX_REVISIONS else "abstain"


def failure_line(failure):
    return f'- "{failure["claim"]}": {failure["why"]}' if failure["claim"] else f"- {failure['why']}"


def finished(tools, question, packet, content, previous=None, message=""):
    """A draft as the loop finishes an answer before checking it: the question's spellings and the misspellings of
    returned names corrected (react.correct_names, spelled_right), player_ids beside names taken out unless asked
    (unasked_ids). A revision has its talk about the draft taken out, and one that talks about the draft instead of
    giving it (react.is_meta) keeps the draft. Returns the draft and the names swapped."""
    if previous is not None and react.is_meta(content, previous, message):
        return previous, []
    view, resolver = checker(tools, question, packet).view, tools.resolver
    in_view = view.returned_now | view.returned_before
    content, swaps, _ = react.correct_names(content, resolved_in(question, packet), resolver, in_view)
    content, misspelled = react.spelled_right(content, resolver, in_view, view.words)
    if previous is not None:
        labelled = claim_check.without_draft_label(content)
        content = claim_check.without_draft_talk(labelled, view.states_facts)[0] or labelled
    content, _ = react.unasked_ids(content, question, resolver)
    return content.strip(), react.collapsed(swaps + misspelled)


class Pipeline:
    """One question's run through the graph (graph): the analyst's conversation, and the model calls of the reporter
    and the verifier (reply), all with the same model options (model, think, seed)."""

    def __init__(self, tools, ask=react.chat, max_steps=react.MAX_STEPS, log=print, retriever=None, reply=chat, **model):
        self.tools, self.reply, self.log, self.model = tools, reply, log, model
        self.conversation = react.Conversation(tools, ask, max_steps, log, retriever=retriever, evidence_only=True,
                                               **model)
        self.system = reporter_prompt(tools.path)

    def analyst(self, state):
        """The agent's loop, stopped before its answer. Sent back, it gets the question with what the packet lacks,
        in the same conversation, so it sees what it looked up before; the packet keeps both passes."""
        missing = state.get("missing")
        question = (RETURN.format(question=state["question"], missing=missing.rstrip(".") + ".") if missing
                    else state["question"])
        trace = self.conversation.ask(question)
        out = {"packet": state.get("packet", []) + packet_of(trace), "draft": None, "failures": [], "missing": "",
               "returns": state.get("returns", 0) + bool(missing), "path": ["analyst"],
               "steps": [{**s, "role": "analyst"} for s in trace["steps"]],
               "analyst": [{k: trace.get(k) for k in ("outcome", "draft", "settled", "examples", "answered_after_too_big",
                                                      "answered_after_lookup_miss")}]}
        if trace["outcome"] == "suggestions" or trace["outcome"].startswith("request error"):
            out.update(answer=trace["answer"], outcome=trace["outcome"])  # the user is asked, or the server failed
        self.log(f"  analyst: {trace['outcome']}, {len(out['packet'])} calls in the packet")
        return out

    def reporter(self, state):
        """One model call that writes the draft from the question and the packet; revising, it also sees its draft
        and the verifier's failures. The draft is finished as the loop finishes an answer (finished)."""
        revising = state.get("draft") is not None
        messages = [{"role": "system", "content": self.system},
                    {"role": "user", "content": f"Question: {state['question']}\n\nEvidence packet:\n"
                                                f"{shown(state['packet'])}"}]
        message = REVISE.format(failures="\n".join(failure_line(f) for f in state["failures"])) if revising else ""
        if revising:
            messages += [{"role": "assistant", "content": state["draft"]}, {"role": "user", "content": message}]
        begun = time.monotonic()
        step = step_of("reporter", self.reply(messages, **self.model), time.monotonic() - begun)
        draft, swaps = finished(self.tools, state["question"], state["packet"], step["content"],
                                state["draft"] if revising else None, message)
        step["draft"] = draft
        if swaps:
            step["name_swaps"] = swaps
        self.log(f"  reporter: {'revised' if revising else 'drafted'}: {react.short(draft, 200)}")
        return {"draft": draft, "revisions": state.get("revisions", 0) + revising, "swaps": swaps,
                "steps": [step], "path": ["reporter"]}

    def verifier(self, state):
        """The loop's answer checks and one model call on the draft (verify), and the decision on it (route)."""
        failures, missing, step = verify(self.tools, state["question"], state["packet"], state["draft"], self.reply,
                                         **self.model)
        decision = route(failures, missing, state.get("revisions", 0), state.get("returns", 0))
        step["verifier"]["decision"] = decision
        out = {"failures": failures, "missing": missing, "next": decision, "steps": [step], "path": ["verifier"]}
        if decision == "pass":
            out.update(answer=state["draft"], outcome="answered")
        self.log(f"  verifier: {len(failures)} failures{', missing: ' + missing if missing else ''}; {decision}")
        return out

    def abstain(self, state):
        self.log("  abstained")
        return {"answer": ABSTAIN, "outcome": "abstained", "path": ["abstain"]}


# The verifier's decisions (route) as the graph's edges are named, which its diagram shows: an edge named as its node
# would have no label
EDGES = {"pass": "pass", "revise": "revise, at most 2", "return": "return, once", "abstain": "limits reached"}


def graph(nodes):
    """The pipeline's graph (LangGraph), from the function of each node: analyst, reporter, verifier and abstain. The
    analyst's suggestions or a server error end it; else the reporter drafts and the verifier decides (route)."""
    from langgraph.graph import END, START, StateGraph  # here only: the rest of the module runs without LangGraph
    built = StateGraph(State)
    for name in ("analyst", "reporter", "verifier", "abstain"):
        built.add_node(name, nodes[name])
    built.add_edge(START, "analyst")
    built.add_conditional_edges("analyst", lambda s: "suggestions or error" if s.get("outcome") else "evidence",
                                {"evidence": "reporter", "suggestions or error": END})
    built.add_edge("reporter", "verifier")
    built.add_conditional_edges("verifier", lambda s: EDGES[s["next"]], {
        EDGES["pass"]: END, EDGES["revise"]: "reporter", EDGES["return"]: "analyst", EDGES["abstain"]: "abstain"})
    built.add_edge("abstain", END)
    return built.compile()


def diagram():
    """The graph's Mermaid diagram, drawn by LangGraph from the graph itself, for the slides."""
    return graph({name: (lambda state: {}) for name in ("analyst", "reporter", "verifier", "abstain")}).get_graph() \
        .draw_mermaid()


def traced(question, state):
    """The run as a trace shaped as the loop's (react.Conversation.turn), which the harness scores the same way: every
    model call's step in order, numbered, with its role; the pipeline's path and counters under 'pipeline'."""
    steps, passes = state["steps"], state["analyst"]
    for n, step in enumerate(steps, 1):
        step["step"] = n
    return {"question": question, "examples": passes[0]["examples"], "steps": steps, "answer": state.get("answer"),
            "outcome": state.get("outcome") or "no answer", "unreturned_names": {}, "unreturned_ids": [],
            "answered_after_too_big": any(p["answered_after_too_big"] for p in passes),
            "answered_after_lookup_miss": any(p["answered_after_lookup_miss"] for p in passes),
            "answered_without_tools": False, "answered_after_failed_calls": False,
            "name_swaps": state.get("swaps") or [], "unconfirmed": [],
            "pipeline": {"path": state["path"], "revisions": state.get("revisions", 0), "returns": state.get("returns", 0),
                         "analyst": [{k: p[k] for k in ("outcome", "draft", "settled")} for p in passes]},
            "steps_used": len(steps), "model_seconds": round(sum(s["seconds"] for s in steps), 1),
            "tool_seconds": round(sum(c.get("seconds") or 0 for s in steps for c in s["tool_calls"]), 1),
            "output_tokens": sum(s["output_tokens"] or 0 for s in steps),
            "largest_context": max(((s["prompt_tokens"] or 0) + (s["output_tokens"] or 0) for s in steps), default=0)}


def run(question, tools, ask=react.chat, max_steps=react.MAX_STEPS, log=print, retriever=None, reply=chat, **model):
    """Answer one question through the pipeline, as react.run answers it with the single agent: its trace."""
    pipeline = Pipeline(tools, ask, max_steps, log, retriever, reply, **model)
    built = graph({"analyst": pipeline.analyst, "reporter": pipeline.reporter, "verifier": pipeline.verifier,
                   "abstain": pipeline.abstain})
    state = built.invoke({"question": question, "packet": [], "draft": None, "failures": [], "missing": "",
                          "revisions": 0, "returns": 0, "steps": [], "analyst": [], "path": []})
    return traced(question, state)


if __name__ == "__main__":  # python agent/pipeline.py: the graph's diagram, as Mermaid, for docs/figures
    print(diagram())
