"""A message's context, settled in code before retrieval and the model see it (decided 2026-11-19, from the web app's
live testing: docs/web-app-testing-notes.md on claude/web-app, findings 0b and 3). The user's words stay the trace's
question; the settled text is what the model reads and the history keeps.
- A reply to suggestions (choice: an ordinal, a number or a candidate's name, such as "the first one") becomes the
  question it answers, with the chosen player written in, and resolve_player on the question's spelling returns that
  player (react.Conversation.call). Live, "the first one" was taken as a question of its own: retrieval found a worked
  example about Addymestic in its three words, and the model answered that.
- A follow-up becomes a question that stands on its own, in one of two ways, measured on the multi-turn test
  conversations (eval/questions/conversations.toml) before one is chosen:
  - by_cues, hand-written rules: a message that names no player and refers back ("the 2v2 record", "what about",
    "i meant", "and ...", "they"), or a fragment ("in 2v2?"), gets a note with what it continues: the previous
    question, and the players and events it was about. 'he' or 'she' gets the player when there was one;
  - by_model: one short model call (REWRITE) writes the message as a question of its own, or keeps it.
  Live, "tell me about the 2v2 record" retrieved worked examples of other readings, and the model asked which players
  it meant.
- Retrieval embeds the settled question (for a follow-up by cues, the previous question with it), and doesn't run on
  one that carries no question of its own (mentions.asks).
after() gives the context the next message may continue: the question as settled, its answer, the players and events
it was about, and, when it ended in suggestions, the names asked about with their candidates.
"""

import json
import re
import time
import urllib.error
from dataclasses import dataclass, field

import mentions  # which puts ingest/ on the path, for names
from mentions import FUNCTION, WORD, normalize
from names import normalize_full, normalize_words

EVENTS = 5  # the events a note lists at most
ANSWER = 1500  # the characters of the previous answer the rewrite reads
LONGEST = 400  # characters: a longer rewrite is an answer, not a question
PICKS = {"first": 0, "1st": 0, "1": 0, "second": 1, "2nd": 1, "2": 1, "two": 1, "third": 2, "3rd": 2, "3": 2,
         "three": 2, "last": -1}
CHOOSING = FUNCTION | {"option", "number", "pick", "choose", "chose", "player", "guy", "person", "thats", "correct",
                       "right"}  # words a choice may have beside the pick: "yes, the first one", "option 2"
OPENERS = ("and", "what about", "how about", "i meant", "i mean", "but", "also", "now", "same", "only", "just")
REFERS = re.compile(r"\b(?:the|that|this|these|those)\s+(?:[\w'’-]+\s+){0,3}?(?:one|ones|record|records|event|events"
                    r"|tournament|tournaments)\b", re.I)  # "the 2v2 record", "the north america one"
STARTS = {"in", "at", "for", "with", "against", "vs", "versus", "from", "since", "during", "before", "after",
          "without", "on", "by"}  # a fragment's first word: "in 2v2?", "at bcx 2022"
FRAGMENT = 4  # words at most
ONE = {"he", "him", "his", "she", "her", "hers"}
MANY = {"they", "them", "their", "theirs"}
REWRITE = (
    "You rewrite the latest message of a conversation about official Brawlhalla esports results as a question that can"
    " be understood without the conversation. If the message already makes sense on its own, reply with it unchanged."
    " If it continues the conversation, such as \"tell me about the 2v2 record\", \"what about 2023\", \"he\" or \"the"
    " north america one\", write out the question it asks, with the players, events, modes and years it leaves out"
    " taken from the conversation, by the names the conversation gives them. Add nothing else: no condition the user"
    " didn't ask for, and no facts. Never answer it. Reply with the question alone, on one line.")
LABEL = re.compile(r"^(?:the\s+)?(?:standalone\s+|rewritten\s+)?(?:question|rewrite)\s*:\s*", re.I)


@dataclass
class Settled:
    """What a message becomes: the text the model reads and the history keeps (text), the text retrieval embeds
    (retrieve), how it was settled, the players chosen from suggestions [(spelling, candidate)], the players and
    events it carries from the context [(name, id)], and the rewrite's reply when one was asked for."""
    text: str
    retrieve: str
    how: str = "as asked"
    chosen: list = field(default_factory=list)
    players: list = field(default_factory=list)
    events: list = field(default_factory=list)
    rewrite: dict = None

    def traced(self):
        """For the trace: the text and how, and what else applies."""
        out = {"text": self.text, "how": self.how}
        if self.retrieve != self.text:
            out["retrieved_on"] = self.retrieve
        if self.chosen:
            out["chosen"] = [{"spelling": s, "player_id": c["player_id"], "name": c["name"]} for s, c in self.chosen]
        if self.rewrite:
            out["rewrite"] = self.rewrite
        return out


@dataclass
class Context:
    """What the next message may continue: the last question as settled, its answer, the players and events it was
    about [(name, id)], and the names it asked the user about, [{name, candidates}], when it ended in suggestions."""
    question: str = ""
    answer: str = ""
    players: list = field(default_factory=list)
    events: list = field(default_factory=list)
    asked: list = field(default_factory=list)


def listed(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def unique(pairs):
    """(name, id) pairs, the first of each id, in order."""
    ids, out = set(), []
    for name, i in pairs:
        if i not in ids:
            ids.add(i)
            out.append((name, i))
    return out


def named(text, name):
    """Whether a text writes a name, compared as aliases are, with or without its team tag."""
    forms = {normalize(name), normalize_full(name)} - {""}
    return any(form in normalize_full(text) for form in forms)


def as_asked(message, how="as asked", rewrite=None):
    return Settled(message, message, how, rewrite=rewrite)


# A reply to suggestions

def choice(message, asked):
    """The candidates a reply to suggestions picks, [(spelling asked about, candidate)], or [] when it isn't a choice.
    A choice is a candidate's name ("i meant Radses"), or, when one name was asked about, an ordinal or a number
    ("the first one", "2"), with nothing else but function words. With several names asked about, a reply names its
    choices."""
    tokens = [t for t in (normalize(w) for w in WORD.findall(message)) if t]
    if not tokens or not asked:
        return []
    used, picked = set(), []
    for entry in asked:
        named_here = []
        for c in entry["candidates"]:
            forms = {normalize(c["name"]), normalize_full(c["name"])} - {""}
            span = next(((i, n) for n in (3, 2, 1) for i in range(len(tokens) - n + 1)
                         if "".join(tokens[i:i + n]) in forms), None)
            if span:
                named_here.append((c, span))
        if len(named_here) == 1:
            c, (i, n) = named_here[0]
            used |= set(range(i, i + n))
            picked.append((entry["name"], c))
    if not picked and len(asked) == 1:
        places, candidates = {PICKS[t] for t in tokens if t in PICKS}, asked[0]["candidates"]
        if len(places) == 1 and -len(candidates) <= min(places) < len(candidates):
            picked = [(asked[0]["name"], candidates[places.pop()])]
    rest = [t for i, t in enumerate(tokens) if i not in used and t not in CHOOSING and t not in PICKS]
    return picked if picked and not rest else []


def chosen(context, picked):
    """The question a choice answers: the one asked, each chosen player written in for the spelling asked about, with
    a note giving their player_id."""
    text, notes = context.question, []
    for spelling, c in picked:
        text = re.sub(rf"(?<!\w){re.escape(spelling)}(?!\w)", lambda m: c["name"], text, flags=re.I)
        notes.append(f'{c["name"]} is player_id {c["player_id"]}: the user chose them when asked which player'
                     f' "{spelling}" means')
    players = unique(context.players + [(c["name"], c["player_id"]) for _, c in picked])
    return Settled(f"{text} [{'; '.join(notes)}.]", mentions.unnoted(text), "a reply to suggestions", chosen=picked,
                   players=players, events=list(context.events))


def resolved(name, spelling, candidate):
    """resolve_player's result for a name the user settled by choosing from suggestions: the player chosen, alone."""
    display = candidate.get("display") or candidate["name"]
    return {"name": name, "status": "confident",
            "note": f'The user chose this player when asked which player "{spelling}" means. Use player_id'
                    f' {candidate["player_id"]}, and call them {display}.',
            "candidates": [{**candidate, "match": "chosen by the user", "score": 1.0}]}


# A follow-up, by cues

def by_cues(message, context, resolver):
    """A message as hand-written rules settle it: a follow-up gets a note on what it continues, and 'he' or 'she' the
    player meant (the module docstring)."""
    words = [w.lower().strip("'’") for w in WORD.findall(message)]
    if not context.question or not words:
        return as_asked(message)
    content, _ = mentions.words(message)
    names = [w for w in content if w not in mentions.REGIONS and mentions.player(resolver, w)]
    said = " ".join(words)
    fragment = len(words) <= FRAGMENT and words[0] in STARTS
    refers = (any(said == o or said.startswith(o + " ") for o in OPENERS) or bool(REFERS.search(message))
              or bool(MANY & set(words)))
    if fragment or (refers and not names):
        return continuing(message, context)
    he = next((w for w in words if w in ONE), None)
    if he and len(context.players) == 1:
        name, pid = context.players[0]
        return Settled(f"{message} [{he}: {name} (player_id {pid}), from the previous question.]", message,
                       "a pronoun (cues)", players=list(context.players))
    return as_asked(message)


def continuing(message, context):
    """A follow-up with a note on what it continues: the previous question, and the players and events it was
    about. Retrieval embeds the previous question with it."""
    previous = mentions.unnoted(context.question)
    about = [listed([f"{name} (player_id {pid})" for name, pid in context.players])] if context.players else []
    if context.events:  # by name: the IDs are in the previous question's results, and some are long slugs
        about.append("the events " + listed([name for name, _ in context.events[:EVENTS]]))
    note = f'This continues the previous question, "{previous}"' + (f", about {'; and '.join(about)}" if about else "")
    return Settled(f"{message} [{note}.]", f"{previous} {message}", "a follow-up (cues)", players=list(context.players),
                   events=list(context.events))


# A follow-up, by the model

def by_model(message, context, rephrase, **model):
    """A message as one short model call settles it (REWRITE); as asked when the call fails or gives no question.
    The rewrite's reply and time go to the trace."""
    if not context.question:
        return as_asked(message)
    request = [{"role": "system", "content": REWRITE}, {"role": "user", "content": rewrite_request(message, context)}]
    begun = time.monotonic()
    try:
        reply = rephrase(request, **model)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return as_asked(message, "as asked: the rewrite failed", {"error": f"{type(e).__name__}: {e}"})
    content = ((reply or {}).get("message") or {}).get("content") or ""
    out = {"reply": content, "seconds": round(time.monotonic() - begun, 2)}
    text = question_in(content)
    if not text:
        return as_asked(message, "as asked: the rewrite gave no question", out)
    if normalize_words(text) == normalize_words(message):
        return as_asked(message, "kept by the rewrite", out)
    return Settled(text, text, "rewritten", players=[p for p in context.players if named(text, p[0])], rewrite=out)


def rewrite_request(message, context):
    """What the rewrite reads: the previous question and its answer, who and what it was about, then the message."""
    lines = [f"Previous question: {mentions.unnoted(context.question)}"]
    if context.answer:
        lines.append("Previous answer: " + (context.answer if len(context.answer) <= ANSWER
                                            else context.answer[:ANSWER] + " ..."))
    if context.players:
        lines.append("Players it was about: " + ", ".join(name for name, _ in context.players))
    if context.events:
        lines.append("Events it was about: " + ", ".join(name for name, _ in context.events[:EVENTS]))
    return "\n".join(lines + ["", f"Latest message: {message}"])


def question_in(content):
    """The question a rewrite's reply gives: its first line, without a label or quotes; None when there's none, or
    it's too long to be one."""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
    line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    line = LABEL.sub("", line).strip().strip('*"“”').strip()
    return line if line and len(line) <= LONGEST else None


# The context after a turn

def after(trace, settled):
    """The context the next message may continue, from a turn's trace (react.Conversation.turn) and its settled
    text: the players it carried, resolve_player decided for names the text writes, or a template was about
    (player_results' player, head_to_head's two); the events it carried, or resolve_event or event_results found; and
    the names it asked the user about."""
    players, events = list(settled.players), list(settled.events)
    for step in trace["steps"]:
        for call in step["tool_calls"]:
            observation = json.loads(call["observation"]) if call.get("observation") else {}
            if not isinstance(observation, dict) or "error" in observation:
                continue
            if (call["name"] == "resolve_player" and observation.get("status") == "confident"
                    and observation.get("candidates") and named(settled.text, observation.get("name") or "")):
                first = observation["candidates"][0]
                players.append((first["name"], first["player_id"]))
            for key in ("player", "opponent"):
                who = observation.get(key)
                if isinstance(who, dict) and who.get("player_id") is not None:
                    players.append((who.get("name") or str(who["player_id"]), who["player_id"]))
            if call["name"] == "resolve_event":
                events += [(e["name"], e["event_id"]) for e in observation.get("events") or ()]
            for t in observation.get("tables") or ():  # event_results' events, by id when they're few
                if "event" in t.get("columns", ()) and "event_id" in t["columns"]:
                    i, j = t["columns"].index("event"), t["columns"].index("event_id")
                    events += [(row[i], row[j]) for row in t["rows"]]
    return Context(settled.text, trace.get("answer") or "", unique(players), unique(events)[:EVENTS],
                   trace.get("asked") or [])
