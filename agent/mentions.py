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
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
from names import normalize  # noqa: E402

FUNCTION = set("""
a an the and or but of in on at to for from with without vs versus against by about as is are was were be been being
has have had do does did doesnt dont didnt isnt wasnt cant can could would should will may might must what whats which
who whos whom whose when where why how many much more most less least any some all each every other others another
this that these those there here it its he she they him her them his hers their theirs me my i im you your we our us
one ones first second third 1st 2nd 3rd last latest next previous best worst big bigger biggest good better great top
tell show give list know mean meant like also etc please thanks thank ok okay yes yeah no not get got make made ever
still just only again now then than so really very hello hi hey guys look looking want see same different cool nice
awesome lol wow interesting perfect sure alright gotcha amazing sweet bye goodbye welcome np ty thx hmm oh ah um uh fine
""".split())  # function words, fillers, and replies such as 'thanks' or 'cool': none carries a question
DOMAIN = set("""
play played playing plays win wins won winning lose loses loss losses lost record records set sets game games match
matches score scores result results placement placements place placed finish finished finishes medal medals title titles
major majors tournament tournaments event events official community mode modes singles doubles team teams teammate
partner partners player players head h2h graphic card chart table image picture display stat stats history lifetime
career earnings money prize year years time times info information details detail count counts rank ranked ranking
legend legends main mains character characters overall total
""".split())  # the domain's own words: they give a question its shape, and name nothing to look up
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


def words(question):
    """(content words, years) of a question, each normalized as aliases are (names.normalize), in order, its notes
    left out (unnoted)."""
    tokens = [normalize(t) for t in WORD.findall(re.sub(r"['’]s\b", " ", unnoted(question)))]
    content = [t for t in tokens if t and t not in STOP and not FORMAT.fullmatch(t) and not YEAR.fullmatch(t)]
    return list(dict.fromkeys(content)), list(dict.fromkeys(t for t in tokens if YEAR.fullmatch(t)))


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


def lookups(content, years, resolver):
    """The tool calls that look up some content words, (tool, arguments) each: resolve_player for each word that
    names a player, then resolve_event for the rest with the question's years ('cb' and 2022 as 'cb 2022')."""
    players = [w for w in content if w not in REGIONS and player(resolver, w)]
    rest = [w for w in content if w not in players]
    calls = [("resolve_player", {"name": w}) for w in players]
    if rest:
        calls.append(("resolve_event", {"name": " ".join(rest + years)}))
    return calls
