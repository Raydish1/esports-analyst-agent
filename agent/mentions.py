"""What a question names, read from its words: its content words, those left once function words, the domain's own
words (record, wins, tournament, ...) and formats are out, and the players and events they name, by the resolvers
(tools.Resolver, tools.EventResolver). react.py uses it in a turn that called no tool:
- each content word must be in a tool result the model has in view, or the turn has to look it up: the model's own
  knowledge never settles that a player or an event exists or doesn't (decided 2026-11-19, from the web app's live
  testing: "when was ceo 2025" was answered without a lookup, as no Brawlhalla event);
- when the model still won't look anything up, the loop makes the lookups itself (lookups).
And retrieval doesn't run on a text that carries no question (asks: 'the first one', 'thanks'), as settling.py settles
a message before retrieval.
On the 23 questions of the two live sessions (data/experiments/web/20261119T233544Z-002 and -003), the players and
events found are every one they name and no other. Common words that are some player's name (autumn, rank, count,
north, cb) don't count as players: a player needs 5 official results and a match score of 0.7, and a region word is
an event's word.
named() finds the players a question names, in spans of up to three words ('cody travis'), for react.py's player
check, which refuses a call on a player a question that names players doesn't name (decided 2026-11-20). Number words
('two'), words about what was said ('say'), the words of official event names ('Trial') and 'brawlhalla' name no
player: matched as players, 'Brawlhalla', 'bracket', 'link', 'Trial' and 'final' were five of the 45 questions' words.
On the 45 questions it finds 31 names, each the player meant, and no other word.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
from names import normalize  # noqa: E402
from tools import CONFIDENT  # noqa: E402

FUNCTION = set("""
a an the and or but of in on at to for from with without vs versus against by about as is are was were be been being
has have had do does did doesnt dont didnt isnt wasnt cant can could would should will may might must what whats which
who whos whom whose when where why how many much more most less least any some all each every other others another
this that these those there here it its he she they him her them his hers their theirs me my i im you your we our us
one ones first second third 1st 2nd 3rd last latest next previous best worst big bigger biggest good better great top
tell show give list know mean meant like also etc please thanks thank ok okay yes yeah no not get got make made ever
still just only again now then than so really very hello hi hey guys look looking want see same different cool nice
awesome lol wow interesting perfect sure alright gotcha amazing sweet bye goodbye welcome np ty thx hmm oh ah um uh fine
two three four five six seven eight nine ten eleven twelve twenty hundred thousand both few several couple dozen once
twice say said says saying wrong right correct incorrect true false
""".split())  # function words, fillers, replies such as 'thanks' or 'cool', number words, and words about what was said:
# none carries a question or names anything. Live, the loop looked up "two" as a player and "say cody travis 24" as an
# event (docs/web-app-testing-notes.md on claude/web-app, findings 10 and 14)
DOMAIN = set("""
play played playing plays win wins won winning lose loses loss losses lost record records set sets game games match
matches score scores result results placement placements place placed finish finished finishes medal medals title titles
major majors tournament tournaments event events official community mode modes singles doubles team teams teammate
partner partners player players head h2h graphic card chart table image picture display stat stats history lifetime
career earnings money prize year years time times info information details detail count counts rank ranked ranking
legend legends main mains character characters overall total brawlhalla esports bracket brackets link links url final
finals grand semifinal semifinals round rounds pool pools seed seeding
""".split())  # the domain's own words: they give a question its shape, and name nothing to look up. 'brawlhalla',
# 'link' and 'final' are some players' names too: matched as players, they made q05, q33, q34 and q42 ambiguous
STOP = FUNCTION | DOMAIN
REGIONS = set("north south america americas europe european asia oceania brazil sea na eu sa oce mena aus jpn jp br brz".split())
YEAR = re.compile(r"(?:19|20)\d\d")
FORMAT = re.compile(r"\d+v\d+")
WORD = re.compile(r"[\w$!?|'’-]+")
MIN_RESULTS, MIN_SCORE = 5, 0.7


def unnoted(text):
    """A text without its notes in square brackets: the context settling.py writes into a question isn't the user's
    own words."""
    return re.sub(r"\s*\[[^\]]*\]", "", text).strip()


def tokens(question):
    """A question's words as written, with each one normalized as aliases are (names.normalize): [(word, normalized)],
    in order, its notes (unnoted) and possessive 's left out."""
    return [(w, normalize(w)) for w in WORD.findall(re.sub(r"['’]s\b", " ", unnoted(question)))]


def ordinary(word):
    """Whether a normalized word names nothing to look up: a function or domain word, a format, a year or a bare
    number."""
    return not word or word in STOP or bool(FORMAT.fullmatch(word)) or bool(YEAR.fullmatch(word)) or word.isdigit()


def words(question):
    """(content words, years) of a question, each normalized as aliases are (names.normalize), in order, its notes
    left out (unnoted)."""
    found = [t for _, t in tokens(question)]
    return (list(dict.fromkeys(t for t in found if not ordinary(t))),
            list(dict.fromkeys(t for t in found if YEAR.fullmatch(t))))


def asks(text):
    """Whether a text carries a question of its own, for retrieval to run on: a word that isn't a function word or a
    bare number, such as a domain word ('record'), a name, a format or a year. 'the first one' and 'thanks' don't:
    live, "the first one" retrieved a worked example about another player, and the model answered it instead
    (docs/web-app-testing-notes.md on claude/web-app, finding 0b)."""
    tokens = [normalize(t) for t in WORD.findall(unnoted(text))]
    return any(t and t not in FUNCTION and (not t.isdigit() or YEAR.fullmatch(t)) for t in tokens)


def seen(texts):
    """The normalized words of some texts, such as the tool results in view, to look a question's words up in."""
    return {normalize(t) for text in texts for t in WORD.findall(str(text))} - {""}


def player(resolver, word):
    """The candidate a word names as a player, or None: 5 official results and a match score of 0.7 at least."""
    found = resolver.resolve(word)
    top = (found.get("candidates") or [None])[0]
    return top if top and top["official_results"] >= MIN_RESULTS and top["score"] >= MIN_SCORE else None


def named(question, resolver, event_words=frozenset(), least=CONFIDENT):
    """The players a question names, [(its words as written, resolve_player's result)], in the order it writes them:
    spans of one to three words, the longest first, each beginning and ending with a word that isn't ordinary, whose
    best match has MIN_RESULTS official results and scores `least` at least (a span of two or three words, CONFIDENT:
    a name of its own, not two names run together). A single word that's a region or a word of official event names
    (event_words: 'Trial', 'Winter') is the event's. Live, "kyna vs yuz" was answered with the previous turn's player
    for kyna, and "cody travis" was looked up word by word (docs/web-app-testing-notes.md, findings 10 and 13).
    A span is resolved only if an alias has it, or a spelling variant of one (resolver.known), unless `least` is below
    CONFIDENT: a similar spelling takes a scan of every alias, about 0.2 s, which only the loop's own lookups pay."""
    found_tokens = tokens(question)
    used, found = set(), []
    for n in (3, 2, 1):
        for i in range(len(found_tokens) - n + 1):
            span = set(range(i, i + n))
            first, last = found_tokens[i][1], found_tokens[i + n - 1][1]
            if span & used or ordinary(first) or ordinary(last):
                continue
            if n == 1 and (first in REGIONS or first in event_words):
                continue
            text = " ".join(w for w, _ in found_tokens[i:i + n])
            least_here = CONFIDENT if n > 1 else least
            if least_here >= CONFIDENT and not resolver.known(text):
                continue
            out = resolver.resolve(text)
            top = (out.get("candidates") or [None])[0]
            if top and top["official_results"] >= MIN_RESULTS and top["score"] >= least_here:
                used |= span
                found.append((i, text, out))
    return [(text, out) for _, text, out in sorted(found, key=lambda f: f[0])]


def lookups(question, gap, resolver, event_words=frozenset()):
    """The tool calls the loop makes for a model that answered twice without looking up the question's words no
    result in view holds (gap: normalized content words), (tool, arguments) each: resolve_player for each player the
    question names (named, similar spellings included) with one of those words, then resolve_event for the words left
    with the question's years ('cb' and 2022 as 'cb 2022'), if any is left. A word inside a player's name is the
    player's, and a bare number is no event: live, "so why did you say cody travis and phazon have won 24 2v2
    tournaments" was looked up as the event "say cody travis 24" (finding 10)."""
    players = [(text, out) for text, out in named(question, resolver, event_words, least=MIN_SCORE)
               if {normalize(w) for w in WORD.findall(text)} & set(gap)]
    inside = {normalize(w) for text, _ in players for w in WORD.findall(text)}
    rest = [w for w in gap if w not in inside and not ordinary(w)]
    calls = [("resolve_player", {"name": text}) for text, _ in players]
    if rest:
        calls.append(("resolve_event", {"name": " ".join(rest + words(question)[1])}))
    return calls
