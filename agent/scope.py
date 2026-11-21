"""The scope check (decided 2026-11-20; docs/agent-mechanisms.md, M1): the scope words a question names reach every
template call that can take them, checked before the call runs. Live, "the strongest 1v1 player right now" was asked as
rank_players(by="wins", top=5), with no mode and no time, and answered with the most wins ever in both modes
(docs/web-app-testing-notes.md, finding 29).

The scope words, read from what the user wrote (scope):
- a mode: 1v1, 1s or singles; 2v2, 2s or doubles. Only one: a question naming both, or "both modes", has none;
- a year standing alone ('in 2024'). A year next to a word of official event names ('bcx 2022', '2024 worlds') is the
  event's, and isn't checked: in "did the winner of bcx 2022 win worlds", 2022 isn't a scope for the worlds lookup;
- a time window: since, after or from a year; before, until or through one; between two;
- a region: na, eu, sa, brz, sea, aus, mena, jpn, or a name for one ('north america', 'oce');
- the present: right now, currently, these days, nowadays, lately, recently, at the moment, this season.

What satisfies each, in a call (lacking): its own argument (mode, year, since or until, region), or the event argument
naming it ('winters 2023 na 1v1' holds a year, a region and a mode). A template that can't take a word isn't checked
for it: head_to_head and event_results take no mode, power_rankings no year, and power_rankings is the present
itself. The present needs a year or a window, which reading is the model's to choose and say (the prompt's rule).

A refused call that the model makes again unchanged runs (Turn.call in react.py): the words may not apply to one step
of a question about several things, and the model has been told why. Events aren't checked: they reach the calls
already, and the event check covers a name that finds nothing."""

import re
from dataclasses import dataclass, field

from tools import REGIONS, normalize_words

MODES = {"1v1": re.compile(r"\b(?:1v1s?|1s|singles)\b", re.I), "2v2": re.compile(r"\b(?:2v2s?|2s|doubles)\b", re.I)}
BOTH = re.compile(r"\b(?:both|all)\s+modes\b|\b(?:1v1|singles)\s*(?:and|&|/|or|\+)\s*(?:2v2|doubles)\b"
                  r"|\b(?:2v2|doubles)\s*(?:and|&|/|or|\+)\s*(?:1v1|singles)\b", re.I)
YEAR = r"(20[12]\d)"
SINCE = re.compile(rf"\b(?:since|after|from|starting(?:\s+in)?)\s+(?:the\s+(?:start|beginning)\s+of\s+)?{YEAR}\b", re.I)
UNTIL = re.compile(rf"\b(?:before|until|till|through|thru|up\s+to)\s+(?:the\s+end\s+of\s+)?{YEAR}\b", re.I)
BETWEEN = re.compile(rf"\bbetween\s+{YEAR}\s+and\s+{YEAR}\b|\b{YEAR}\s*(?:-|–|to)\s*{YEAR}\b", re.I)
ANY_YEAR = re.compile(rf"\b{YEAR}\b")
# The opponents' side of one player's records: who did best against them, beat them, or whom they lost to (q08 and
# q40 asked rank_pairs for the player's own side). A record against them is one nobody owns yet ("who has the best
# record against X", "the best 1v1 record against X"), not X's own: "X's best record against anyone", "X's record
# vs Y" (q27) and "he doesnt have big records vs raydish" (c1 turn 3) are X's side
AGAINST = re.compile(r"\b(?:who\s+(?:has|have|had)\s+|the\s+)(?:[\w-]+\s+){0,2}?(?:record|records|win\s*rate)\s+(?:against"
                     r"|vs\.?|versus|over)\s+(?!any|every|an?\s+opponent|opponents|other|them\b|their\b)\w|\b(?:lost|loses"
                     r"|lose|losing)\s+(?:to|against)\b|\bbeaten\s+by\b|\bwho\s+(?:has\s+|have\s+|had\s+)?(?:beat|beats|beaten"
                     r"|defeated)\s+\w", re.I)
# A player's best placement: player_results with no top, whose best column and results at the best placement answer
# it. Live, "best placement" was asked with top=1 and answered "no 1st places" (finding 26; c15, audit a03). Not a
# count such as "top 8 finishes", which needs its top
BEST = re.compile(r"\b(?:best|highest|peak)\s+(?:(?!\d+\s)[\w-]+\s+){0,2}?(?:placement|placing|finish|result|showing)s?\b",
                  re.I)
PRESENT = re.compile(r"\b(?:right\s+now|currently|these\s+days|nowadays|lately|recently|at\s+the\s+moment|this\s+season)\b",
                     re.I)
REGION_WORDS = re.compile(r"\b(?:north\s+american?|south\s+american?|southeast\s+asian?|middle\s+east(?:ern)?|europe(?:an)?"
                          r"|brazil(?:ian)?|australian?|oceania|japan(?:ese)?|na|eu|sa|brz|br|sea|aus|oce|mena|jpn|jp)\b", re.I)
GLUE = {"in", "of", "the", "at", "for", "during", "from", "since", "until", "before", "after", "by", "to", "and", "or",
        "a", "an", "on", "this", "that", "with", "was", "is"}


@dataclass
class Scope:
    """What a question names: one mode, the years standing alone, a window's ends (years), the regions (codes), and
    the present (the words)."""
    mode: str | None = None
    years: list = field(default_factory=list)
    since: str | None = None
    until: str | None = None
    regions: list = field(default_factory=list)
    present: str | None = None
    against: bool = False  # the opponents' side of one player's records (AGAINST)
    best: bool = False  # a best placement (BEST)

    def __bool__(self):
        return bool(self.mode or self.years or self.since or self.until or self.regions or self.present or self.against
                    or self.best)


def scope(question, events):
    """The scope words of a question (the module docstring); events is the EventResolver, for its words and regions."""
    text = str(question)
    modes = [m for m, pattern in MODES.items() if pattern.search(text)]
    mode = modes[0] if len(modes) == 1 and not BOTH.search(text) else None
    windows = [m.span() for p in (SINCE, UNTIL, BETWEEN) for m in p.finditer(text)]
    since = next((m[1] for m in SINCE.finditer(text)), None) or next((m[1] or m[3] for m in BETWEEN.finditer(text)), None)
    until = next((m[1] for m in UNTIL.finditer(text)), None) or next((m[2] or m[4] for m in BETWEEN.finditer(text)), None)
    tokens = [(t[0].casefold(), t.start()) for t in re.finditer(r"[\w?!]+", text)]
    years = []
    for i, (token, start) in enumerate(tokens):
        if not ANY_YEAR.fullmatch(token) or any(a <= start < b for a, b in windows):
            continue
        near = [tokens[j][0] for j in (i - 1, i + 1) if 0 <= j < len(tokens)]
        if not any(w in events.words and w not in GLUE for w in near):  # 'bcx 2022' and '2024 worlds' are events'
            years.append(token)
    regions = list(dict.fromkeys(found[0] for m in REGION_WORDS.finditer(text)
                                 for found in [events.region(m[0])] if found))
    present = PRESENT.search(text)
    return Scope(mode, list(dict.fromkeys(years)), since, until, regions, present and present[0],
                 bool(AGAINST.search(text)), bool(BEST.search(text)))


def lacking(asked, name, arguments, parameters, events):
    """What a template call leaves out of the question's scope: [(what the question says, what to pass)], or []."""
    if not asked:
        return []
    out, text = [], str(arguments.get("event") or "").casefold()
    takes = set(parameters)
    if asked.mode and "mode" in takes:
        given = str(arguments.get("mode") or "").strip().casefold()
        teams = name == "rank_pairs" and str(arguments.get("of", "")).casefold() in ("teammates", "partners", "teams", "duos")
        mode = ({"1v1": "1v1", "singles": "1v1", "2v2": "2v2", "doubles": "2v2"}.get(given)
                or ("2v2" if teams else "1v1" if name in ("rank_pairs", "power_rankings", "upsets") else None))
        if mode != asked.mode and asked.mode not in text:
            out.append((f"names {asked.mode}", f'mode="{asked.mode}"'))
    if len(asked.years) == 1 and ("year" in takes or name == "event_results"):
        year = asked.years[0]
        window = [str(arguments.get(k) or "") for k in ("since", "until")]
        if str(arguments.get("year") or "") != year and year not in text and not any(w.startswith(year) for w in window):
            out.append((f"names {year}", f"year={year}" if "year" in takes else f"the year in event ('... {year}')"))
    if asked.since and "since" in takes and not arguments.get("since") and asked.since not in text:
        out.append((f"asks from {asked.since} on", f'since="{asked.since}"'))
    if asked.until and "until" in takes and not arguments.get("until") and asked.until not in text:
        out.append((f"asks up to {asked.until}", f'until="{asked.until}"'))
    if len(asked.regions) == 1 and ("region" in takes or name == "event_results"):
        code = asked.regions[0]
        given = events.region(arguments["region"]) if arguments.get("region") else None
        named = bool(text) and events.phrase(code, normalize_words(text).split()) is not None
        if not (given and given[0] == code) and not named:
            out.append((f"names {REGIONS[code]}", f'region="{code}"' if "region" in takes
                        else f"the region in event ('... {code}')"))
    if (asked.against and name == "rank_pairs" and arguments.get("player_id") is not None
            and str(arguments.get("side") or "").strip().casefold() not in ("opponents", "opponent", "against")):
        out.append(("asks for the other players' records against that player (who did best against them, or whom they"
                    " lost to)", 'side="opponents"'))
    if asked.best and name == "player_results" and arguments.get("top") not in (None, ""):
        out.append(("asks for a best placement", "no top: the best column and the results at the best placement"
                    " give it"))
    if asked.present and "since" in takes and not any(arguments.get(k) for k in ("year", "since", "until")):
        out.append((f"asks about the present ('{asked.present}')", "a recent window (since) or year, or the official"
                    " Power Rankings (power_rankings)"))
    return out
