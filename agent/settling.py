"""A message's context, settled in code before retrieval and the model see it (decided 2026-11-19, from the web app's
live testing: docs/web-app-testing-notes.md on claude/web-app, findings 0b and 3). The user's words stay the trace's
question; the settled text is what the model reads and the history keeps.
- A reply to suggestions (choice: an ordinal, a number or a candidate's name, such as "the first one") becomes the
  question it answers, with the chosen player written in, and resolve_player on the question's spelling returns that
  player (react.Conversation.call). Live, "the first one" was taken as a question of its own: retrieval found a worked
  example about Addymestic in its three words, and the model answered that.
- A follow-up becomes a question that stands on its own, by hand-written rules (by_cues): a message that names no
  player and refers back ("the 2v2 record", "what about", "i meant", "and ...", "they"), or a fragment ("in 2v2?"),
  gets a note with what it continues: the previous question, and the players and events it was about. 'he' or 'she'
  gets the player when there was one. Live, "tell me about the 2v2 record" retrieved worked examples of other
  readings, and the model asked which players it meant. A one-call model rewrite was measured against the cues on the
  test conversations (eval/questions/conversations.toml) and removed (decided 2026-11-20): it passed 29 of the 39
  later turns to the cues' 31, narrowed "who got 2nd at ceo 2025" to the singles event, and cost a call per turn
  (docs/experiments.md, 2026-11-19).
- Retrieval embeds the settled question (for a follow-up by cues, the previous question with it), and doesn't run on
  one that carries no question of its own (mentions.asks).
after() gives the context the next message may continue: the question as settled, the players and events it was
about, and, when it ended in suggestions, the names asked about with their candidates.
"""

import json
import re
from dataclasses import dataclass, field

import mentions  # which puts ingest/ on the path, for names
from mentions import FUNCTION, WORD, normalize
from names import normalize_full

EVENTS = 5  # the events a note lists at most
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
# A message questioning the previous answer: live, "so why did you say cody travis and phazon have won 24 2v2
# tournaments" was looked up as an event, and "there are not that many events" repeated the answer's numbers without
# a lookup (docs/web-app-testing-notes.md, findings 10 and 12)
DISPUTES = re.compile(r"\b(?:are you sure|you sure|why did you (?:say|write|tell|think|claim|put|count)|you (?:just )?"
                      r"(?:said|wrote|told)|that(?:'s|s| is| was) (?:not right|not true|not correct|wrong|incorrect|false)"
                      r"|you(?:'re| are) wrong|(?:is|was) that (?:right|true|correct)|not that many|(?:can'?t|cannot)"
                      r" be right|doesn'?t (?:sound|seem|look) right|too (?:many|few)|double.?check|check (?:that|it|this)"
                      r" again|where (?:does|do|did|is|are) (?:\S+ ){0,4}(?:come|coming) from|where did you get|how did"
                      r" you (?:get|count|work out))\b", re.I)
# A message about what the page showed beside the last answer, when it showed something: "on the card, where does
# phazon's 12 gold come from?" was looked up as the event "come" (docs/web-app-testing-notes.md, finding 23)
PAGE = re.compile(r"\b(?:on|in|from|about|of) (?:the|this|that|your|those|these) (?:stat )?(?:cards?|graphics?|charts?"
                  r"|images?|pictures?|page|screen)\b|\b(?:the|this|that) (?:stat )?(?:cards?|graphics?|charts?) (?:says?"
                  r"|shows?|said|showed)\b", re.I)
DISPUTED = "a question about the previous answer (cues)"


@dataclass
class Settled:
    """What a message becomes: the text the model reads and the history keeps (text), the text retrieval embeds
    (retrieve), how it was settled, the players chosen from suggestions [(spelling, candidate)], and the players and
    events it carries from the context [(name, id)]."""
    text: str
    retrieve: str
    how: str = "as asked"
    chosen: list = field(default_factory=list)
    players: list = field(default_factory=list)
    events: list = field(default_factory=list)

    def traced(self):
        """For the trace: the text and how, and what else applies."""
        out = {"text": self.text, "how": self.how}
        if self.retrieve != self.text:
            out["retrieved_on"] = self.retrieve
        if self.chosen:
            out["chosen"] = [{"spelling": s, "player_id": c["player_id"], "name": c["name"]} for s, c in self.chosen]
        return out


@dataclass
class Context:
    """What the next message may continue: the last question as settled, the players and events it was about
    [(name, id)], and the names it asked the user about, [{name, candidates}], when it ended in suggestions."""
    question: str = ""
    players: list = field(default_factory=list)
    events: list = field(default_factory=list)
    asked: list = field(default_factory=list)
    shown: str = ""  # what the page showed beside the last answer (react.Conversation.shown)


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


def as_asked(message):
    return Settled(message, message)


# A reply to suggestions

def choice(message, asked):
    """The candidates a reply to suggestions picks, [(spelling asked about, candidate)], or [] when it isn't a choice.
    A choice is a candidate's name ("i meant Radses"), or, when one name was asked about, an ordinal or a number
    ("the first one", "2"), with nothing else but function words. With several names asked about, a reply names its
    choices."""
    tokens = [t for t in (normalize(w) for w in WORD.findall(message)) if t]
    if not tokens or not asked:
        return []
    exact = written(message, asked)
    if exact:
        return [exact]
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


def written(message, asked):
    """The candidate a reply is exactly, as written in any case, when it's written with a mark the aliases'
    normalizing drops ('Dragon!', 'Frost | Dragon'): (spelling asked about, candidate), or None. Normalized, "Dragon!"
    is "dragon", which two of the three candidates for "dragon" are, so live it wasn't taken as a choice
    (docs/web-app-testing-notes.md, finding 18)."""
    said = " ".join(message.split()).casefold()
    if not re.search(r"[^\w\s]", said):
        return None
    exact = [(entry["name"], c) for entry in asked for c in entry["candidates"]
             if said in {" ".join(str(c.get(key) or "").split()).casefold() for key in ("name", "display", "matched")}]
    return exact[0] if len(exact) == 1 else None


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

def by_cues(message, context, resolver, event_words=frozenset()):
    """A message as hand-written rules settle it: a question about the previous answer gets a note to check it again,
    a follow-up a note on what it continues, and 'he' or 'she' the player meant (the module docstring)."""
    words = [w.lower().strip("'’") for w in WORD.findall(message)]
    if not context.question or not words:
        return as_asked(message)
    found = mentions.named(message, resolver, event_words, least=mentions.MIN_SCORE)
    names = unique([(c.get("display") or c["name"], c["player_id"]) for _, out in found if out.get("status") == "confident"
                    for c in out["candidates"][:1]])
    if DISPUTES.search(message) or (context.shown and PAGE.search(message)):
        return about_answer(message, context, names)
    said = " ".join(words)
    fragment = len(words) <= FRAGMENT and words[0] in STARTS
    opens = any(said == o or said.startswith(o + " ") for o in OPENERS)
    refers = opens or bool(REFERS.search(message)) or bool(MANY & set(words))
    if fragment or (refers and not found):
        return continuing(message, context)
    if opens and names:  # live, "what about cody travis and phazon?" after a ranking got their 1v1 record (finding 8)
        return continuing(message, context, names)
    he = next((w for w in words if w in ONE), None)
    if he and len(context.players) == 1:
        name, pid = context.players[0]
        return Settled(f"{message} [{he}: {name} (player_id {pid}), from the previous question.]", message,
                       "a pronoun (cues)", players=list(context.players))
    return as_asked(message)


def continuing(message, context, names=None):
    """A follow-up with a note on what it continues: the previous question, and the players and events it was
    about, or with names [(name, player_id)] the players the message names instead, now ('what about cody travis and
    phazon?' after a ranking: the ranking's question, now about them). Retrieval embeds the previous question with
    it."""
    previous = mentions.unnoted(context.question)
    players = names or context.players
    about = [listed([f"{name} (player_id {pid})" for name, pid in players])] if players else []
    if context.events:  # by name: the IDs are in the previous question's results, and some are long slugs
        about.append("the events " + listed([name for name, _ in context.events[:EVENTS]]))
    note = (f'This continues the previous question, "{previous}"'
            + (f", now about {listed([f'{name} (player_id {pid})' for name, pid in names])}" if names else
               f", about {'; and '.join(about)}" if about else ""))
    if names and context.events:
        note += f", at the events {listed([name for name, _ in context.events[:EVENTS]])}"
    return Settled(f"{message} [{note}.]", f"{previous} {message}",
                   "a follow-up with new names (cues)" if names else "a follow-up (cues)", players=list(players),
                   events=list(context.events))


def about_answer(message, context, names):
    """A question about the previous answer ('are you sure', 'why did you say', 'there are not that many'), with a
    note to check it again with the tools and say whether it was right, and the players it and the message are about.
    Retrieval embeds the previous question, the shape the check takes again. react.py sends back an answer to it
    that calls no tool."""
    previous = mentions.unnoted(context.question)
    players = unique(list(context.players) + list(names))
    about = f", about {listed([f'{name} (player_id {pid})' for name, pid in players])}" if players else ""
    if context.shown and PAGE.search(message):  # what the page showed, which the page's message above gives
        note = (f'This asks about what the page showed beside your answer to the previous question, "{previous}"{about}'
                ": answer from the page's message above, and check its figures with the tools (player_results with no"
                " top gives each mode, and both together, at once), then say plainly what they are")
    else:
        note = (f'This questions your answer to the previous question, "{previous}"{about}: check what it questions'
                " with the tools again, then say plainly whether that answer was right, and correct it if it wasn't")
    return Settled(f"{message} [{note}.]", previous, DISPUTED, players=players, events=list(context.events))


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
    return Context(settled.text, unique(players), unique(events)[:EVENTS], trace.get("asked") or [])
