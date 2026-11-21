"""The number check (agent/react.py): every number in an answer must come from a tool result in the conversation, or
from the user's question, as it stands or through one of the derivations below. An answer with a number that
neither holds goes back to the model once, naming it. After that, each claim holding one is replaced by a sentence
saying it couldn't be confirmed, so an unsupported number never reaches the user (decided 2026-11-17). Replayed on
recorded answers, it caught clock times converted wrongly from start_time (q20), games won added up wrongly (q04) and
career earnings no query had read (q32) (docs/experiments.md, 2026-11-17).

Evidence is what the tools returned: every number in a result, digits inside its text included ('BCX 2023' holds
2023) and a placement's word ('second' and 'silver' hold 2); each row's numbers apart; every date, an ISO date or a
start_time timestamp's UTC date; and each timestamp's UTC time. An error isn't evidence, since it repeats what the
call asked for. The numbers in a call's arguments are the query's own conditions, which only a scope phrase may
cite. The system prompt, the tool descriptions and the worked examples aren't evidence.

The derivations, by the kind of claim (KINDS, in the order an answer is read, so a date's parts aren't read again as
numbers):
    format     always: 1v1, 2v2
    list       always: a list's own numbering
    datetime   a result's date and UTC time: 2023-07-09T19:27
    date       a result's date, in any of these forms: 2024-03-10, March 10, 2024, 10 March 2024
    month      a result's date in that month: March 2024
    day        a result's date on that month and day: March 10
    time       a timestamp's UTC time, to the minute: 19:27 UTC, 7:27 PM. A time in another zone isn't
    money      the value at the precision shown, with k or M, keeping two significant digits: $258,984, $259K
    percent    a value as shown (0.64 or 64), or a/b or a/(a+b) of two numbers in one row: 60% from a 3-2 record
    category   always: categories the prompt defines, the medal places 1st, 2nd and 3rd, and top 3 and top 8
    scope      N in a result or a call's arguments: top 5, at least 5, 8th or better, in 2024, placement 2
    record     both numbers in one row, in either order: 5-4; for a range of years, each year: 2019-2021
    ordinal    the number: 49th
    number     the number; a decimal at the precision shown, or a rate as for percent: 48, 1,350, 0.98
    word       the number, for two to twenty and twice; after 'the', 'these' or 'those' a word refers back to
               what was named ('between the two'), and isn't read
Anything the user's question writes is supported as written, and its numbers, dates and place words are evidence.
What an answer asks and its code aren't claims (stated): a sentence ending in '?', and code, fenced or inline
(`top=1`). Live, a clarifying question went back for the 8 and 2022 of its examples (decided 2026-11-19). A name
ending in '?', bold or quoted (**acno?**), asks nothing (2026-11-20).
The replay on 20261117-grounding-before added top 3 and top 8, placement N and the words referring back: as numbers
to check, they made the sentences holding an answer's main claim go (q35 seed 0, q45 seed 1).
Arithmetic isn't a derivation: a sum, a difference or a count of rows the model made itself goes back, since the
prompt asks for the data reduced in SQL (decided 2026-11-17).

What it can't tell is what a number means: q20's answers on 2026-11-17 dated a set July 7, 2023, which a result held
as the event's start, though the set was played on July 9. And a wrong small number usually passes, since small
numbers are in nearly every result.

But a number about one player, or one mode, needs a row about them (Window.unsupported, decided 2026-11-20): each row
keeps its texts (Row), and a count, an ordinal or a record in a sentence naming one player in view, or one mode (1v1
or 2v2, not both together), is supported only by a row that doesn't name only other players, or only another mode
(fits). A row naming neither fits anything, and a year isn't checked so. Live, "Phazon's 12 gold medals in 1v1"
passed, as 12 was in the card line, though only as his 2v2 and both-modes figure (docs/web-app-testing-notes.md,
finding 22). A sentence about both modes together isn't checked against the modes: "12 in all" can mean all of a
question's one mode.
"""

import json
import math
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]
MONTHS = {**{name: i for i, name in enumerate(MONTH_NAMES, 1)}, **{name[:3]: i for i, name in enumerate(MONTH_NAMES, 1)},
          "Sept": 9}
MONTH = "(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"  # capitalized: 'may' is a verb
DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
END = r"(?![\w%/]|[.,]\d)"  # where a number ends: not inside a name, a fraction or a longer number
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)  # fenced code, then inline code
SENTENCE = re.compile(r"[.!?]+[*_)\]\"'”’]*(?=\s|$)|\n")  # where a sentence ends: a mark before a space, or a line break
NAMED = re.compile(r"(?:\*\*|__|[*_\"'“‘])[^\s*_\"'“”‘’]+\?+(?:\*\*|__|[*_\"'”’])$")  # one bold or quoted word: **acno?**
PLACES = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
          "ninth": 9, "tenth": 10, "gold": 1, "silver": 2, "bronze": 3}
WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
         "eighteen": 18, "nineteen": 19, "twenty": 20, "twice": 2}
EPOCHS = (1_000_000_000, 2_200_000_000)  # an integer in this range is a Unix timestamp (2001 to 2039), as start_time
UTC = {"UTC", "GMT", "Z"}
ZONES = UTC | {"ET", "EST", "EDT", "CT", "CST", "CDT", "MT", "MST", "MDT", "PT", "PST", "PDT", "BST", "CET", "CEST",
               "EET", "EEST", "BRT", "ART", "JST", "KST", "SGT", "AEST", "AEDT"}
SCALES = {"k": 1e3, "K": 1e3, "thousand": 1e3, "M": 1e6, "mil": 1e6, "million": 1e6}


@dataclass(frozen=True)
class Claim:
    kind: str  # a key of RULES
    text: str  # as the answer writes it
    start: int
    end: int
    value: tuple  # what the kind's rule reads
    about: str = ""  # for a claim a tool result holds only for another player or mode: whom and which mode it's about


class Row(list):
    """A result's row: its numbers, and the texts beside them, which say whom and which mode they're about."""

    def __init__(self):
        super().__init__()
        self.texts = []

    @property
    def text(self):
        return " ".join(self.texts).casefold()


def amount(text):
    """A number as written: (its value, the precision it shows): ('1,350') is (1350, 1), ('0.98') (0.98, 0.01)."""
    digits = text.replace(",", "")
    return float(digits), 10.0 ** -len(digits.partition(".")[2])


def money(m):
    """(value, precision, significant digits) of an amount: a whole number's trailing zeros are rounding, so $12,500
    shows hundreds."""
    digits = m[1].replace(",", "")
    whole, _, cents = digits.partition(".")
    scale = SCALES.get(m.groupdict().get("scale") or "", 1.0)
    precision = 10.0 ** -len(cents) if cents else 10.0 ** (len(whole) - len(whole.rstrip("0")) if whole.strip("0") else 0)
    significant = len((whole + cents).lstrip("0").rstrip("0") if not cents else (whole + cents).lstrip("0"))
    return float(digits) * scale, precision * scale, significant


def clock(m):
    hour, minute, half, zone = int(m[1]), int(m[2]), m[3], m[4]
    if half:
        hour = hour % 12 + (12 if half in "Pp" else 0)
    return hour, minute, zone


def number(m):
    return (int(next(g for g in m.groups() if g is not None)),)


KINDS = [(kind, re.compile(pattern, flags), parse) for kind, pattern, flags, parse in [
    ("format", r"\b\d+v\d+\b", 0, None),
    ("list", r"^[ \t>]*(?:[-*+][ \t]+)?\d+[.)](?=[ \t])", re.M, None),
    ("datetime", r"\b(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]00:?00)?(?!\d)", 0,
     lambda m: tuple(int(g) for g in m.groups())),
    ("date", r"\b(\d{4})-(\d{2})-(\d{2})\b", 0, lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    ("date", rf"\b{MONTH}[ \t]+{DAY},?[ \t]+(\d{{4}})\b", 0, lambda m: (int(m[3]), MONTHS[m[1]], int(m[2]))),
    ("date", rf"\b{DAY}[ \t]+(?:of[ \t]+)?{MONTH},?[ \t]+(\d{{4}})\b", 0, lambda m: (int(m[3]), MONTHS[m[2]], int(m[1]))),
    ("month", rf"\b{MONTH},?[ \t]+(\d{{4}})\b", 0, lambda m: (int(m[2]), MONTHS[m[1]])),
    ("day", rf"\b{MONTH}[ \t]+{DAY}\b", 0, lambda m: (MONTHS[m[1]], int(m[2]))),
    ("day", rf"\b{DAY}[ \t]+(?:of[ \t]+)?{MONTH}\b", 0, lambda m: (MONTHS[m[2]], int(m[1]))),
    ("time", r"\b(\d{1,2}):(\d{2})(?::\d{2})?(?:[ \t]*([AaPp])\.?[ \t]?[Mm]\.?)?"
             rf"(?:[ \t]*\(?({'|'.join(sorted(ZONES, key=len, reverse=True))})\b\)?)?", 0, clock),
    ("money", rf"\$[ \t]?({NUM})(?:[ \t]?(?P<scale>k|K|M|million|thousand|mil)\b)?", 0, money),
    ("money", rf"\b({NUM})[ \t]?(?:USD|dollars)\b", 0, money),
    ("money", rf"\bUSD[ \t]?({NUM})", 0, money),
    ("percent", r"\b(\d+(?:\.\d+)?)[ \t]?(?:%|percent\b)", 0, lambda m: amount(m[1])),
    ("category", r"\b(?:1st|2nd|3rd)\b|\btop[ \t-]?[38]s?\b", re.I, None),
    ("scope", r"\btop[ \t-]?(\d+)s?\b", re.I, number),
    ("scope", r"\bat[ \t]+least[ \t]+(\d+)\b", re.I, number),
    ("scope", r"\b(\d+)(?:st|nd|rd|th)?[ \t]+or[ \t]+(?:more|better|higher)\b", re.I, number),
    ("scope", r"\b(?:in|during|since|from|before|after|until|through|for)[ \t]+(\d{4})\b", re.I, number),
    ("scope", r"(?<![A-Za-z])(?:placement|placed|place|rank|ranked)[ \t]*(?:=|:|of|at)?[ \t]*(\d+)\b", re.I, number),
    ("record", rf"(?<![\w.,:/$-])(\d+)[ \t]*[-–—][ \t]*(\d+){END}", 0, lambda m: (int(m[1]), int(m[2]))),
    ("ordinal", r"(?<![\w.,])(\d+)(?:st|nd|rd|th)\b", 0, number),
    ("number", rf"(?<![\w.,$/])-?({NUM}){END}", 0, lambda m: amount(m[1])),
    ("word", rf"(?<!\bthe )(?<!\bthese )(?<!\bthose )\b({'|'.join(WORDS)})\b", re.I, lambda m: (WORDS[m[1].lower()],)),
]]


def stated(text):
    """A text as it states things, for the checks to read: its code (fenced, or inline such as `top=1`) and its
    questions (each sentence ending in '?') blanked, each character by one no pattern skips, so what's left keeps its
    place. A clarifying question states nothing by its examples: live, "Or a specific event's 2v2 bracket (e.g., "top
    8 of the Europe Summer 2022 2v2")?" went back for its 8 and 2022 (docs/web-app-testing-notes.md, finding 4).
    A '?' ending one bold or quoted word is a name's, such as **acno?**, and ends no sentence; and a question's
    blanking keeps the spaces before it, so the numbering before it is still a list's. On 2026-11-19, '3. **acno?**'
    lost both, and its 3 went back as a number no tool returned (q05 seeds 0 and 2; decided 2026-11-20)."""
    text = CODE.sub(lambda m: "\0" * len(m[0]), text)
    out, start = [], 0
    for m in SENTENCE.finditer(text):
        if "?" in m[0] and NAMED.search(text, max(0, m.start() - 60), m.end()):
            continue
        piece = text[start:m.end()]
        if "?" in m[0]:
            body = piece.lstrip()
            piece = piece[:len(piece) - len(body)] + "\0" * len(body)
        out.append(piece)
        start = m.end()
    return "".join(out) + text[start:]


def claims(text):
    """Every number-like claim in a text, in the order it's written. Each kind is read with the claims before it
    blanked out, so a date's day isn't also a number: blanked with a character no pattern skips, as a space would
    let 'placed 2nd of 32' read as a placement of 32."""
    found, rest = [], text
    for kind, pattern, parse in KINDS:
        for m in pattern.finditer(rest):
            found.append(Claim(kind, text[m.start():m.end()], m.start(), m.end(), parse(m) if parse else ()))
        rest = pattern.sub(lambda m: "\0" * len(m[0]), rest)
    return sorted(found, key=lambda c: c.start)


def squeeze(text):
    return " ".join(str(text).split()).casefold()


class Evidence:
    """What the tools returned in a conversation, and what the user asked (the module docstring)."""

    def __init__(self):
        self.values, self.rows, self.scope = set(), [], set()
        self.dates, self.months, self.days, self.times = set(), set(), set(), set()
        self.questions = []

    def ask(self, question):
        """A question from the user: anything it writes is supported as written, and its numbers, dates and place
        words count as a result's."""
        self.questions.append(squeeze(question))
        row = Row()
        self.rows.append(row)
        self.text(re.sub(r"\b\d+v\d+\b", " ", question), row)  # a format names a mode, not a number: '2v2' holds no 2
        for c in claims(question):
            if c.kind in ("date", "datetime"):
                self.date(*c.value[:3])
            elif c.kind == "month":
                self.months.add(c.value)
            elif c.kind == "day":
                self.days.add(c.value)

    def observe(self, observation):
        """A tool's result. An error isn't evidence: it repeats what the call asked for."""
        if isinstance(observation, dict) and "error" not in observation:
            self.walk(observation, None)

    def call(self, arguments):
        """A tool call that ran: its arguments' numbers are the query's own conditions, for a scope phrase."""
        text = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
        self.scope |= {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)}

    def walk(self, value, row):
        """A result's values: each dict, and each of a table's rows, is a row of its own."""
        if isinstance(value, dict):
            own = Row()
            self.rows.append(own)
            for key, item in value.items():
                if key == "rows" and isinstance(item, list):
                    for cells in item:
                        listed = Row()
                        self.rows.append(listed)
                        self.walk(cells, listed)
                else:
                    self.walk(item, own)
        elif isinstance(value, list):
            for item in value:
                self.walk(item, None if isinstance(item, dict) else row)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            self.number(float(value), row)
        elif isinstance(value, str):
            self.text(value, row)

    def number(self, value, row):
        value = abs(value)
        self.values.add(value)
        if row is not None:
            row.append(value)
        if value.is_integer() and EPOCHS[0] <= value <= EPOCHS[1]:
            moment = datetime.fromtimestamp(value, timezone.utc)
            self.date(moment.year, moment.month, moment.day)
            self.times.add((moment.hour, moment.minute))

    def text(self, text, row):
        """A text's numbers, each as many times as it's written, so a note's "won 11 and lost 11" holds 11 twice, as a
        row of 11 and 11 does: live, the right 11-11 was replaced (docs/web-app-testing-notes.md, finding 19). The
        parts of a number with a comma (1 and 350 of 1,350) count once."""
        if row is not None:
            row.texts.append(text)
        written = re.findall(NUM, text)
        for found in written + [n for n in dict.fromkeys(re.findall(r"\d+(?:\.\d+)?", text)) if n not in written]:
            self.number(amount(found)[0], row)
        for y, m, d, hour, minute in re.findall(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", text):
            self.date(int(y), int(m), int(d))
            if hour:
                self.times.add((int(hour), int(minute)))
        for word in re.findall(r"[a-z]+", text.casefold()):
            if word in PLACES or word in WORDS:
                self.number(float(PLACES.get(word) or WORDS[word]), row)

    def date(self, year, month, day):
        self.dates.add((year, month, day))
        self.months.add((year, month))
        self.days.add((month, day))

    def supports(self, claim, about=None):
        """Whether the claim is what a tool returned, or the question wrote, as such or by its kind's derivation.
        With about, (mode, player, names) for a claim of a kind in AGREES, only a row that fits it counts (fits)."""
        written = re.compile(rf"(?<!\w){re.escape(squeeze(claim.text))}(?!\w)")
        if any(written.search(q) for q in self.questions):
            return True
        if about and claim.kind in AGREES:
            rows = [r for r in self.rows if fits(r, *about)]
            if claim.kind == "record":
                return record(claim.value, rows)
            return any(claim.value[0] in r for r in rows)
        return RULES[claim.kind](claim.value, self)

    def unsupported(self, answer):
        """The claims an answer states (stated) that nothing in the conversation supports."""
        return [c for c in claims(stated(answer)) if not self.supports(c)]


class Window:
    """The evidence a turn's answer may cite: its own tool results and the previous turn's, each an Evidence, which is
    what the model has in view, as react.Conversation keeps older turns as question and answer only. An older turn's
    results, and every earlier answer, don't count (decided 2026-11-19): in the web app's live testing, an answer's
    small numbers stood because some tool result many turns back held them."""

    def __init__(self, *evidence, names=None):
        self.evidence = evidence
        self.names = names or {}  # the players in view, casefolded name -> as written, for about

    def supports(self, claim, about=None):
        return any(e.supports(claim, about) for e in self.evidence)

    def unsupported(self, answer):
        """The claims nothing in view supports, then those only a row about another player or mode supports, each
        with whom and which mode it's about (decided 2026-11-20): live, "Phazon's 12 gold medals in 1v1" passed, as
        12 was in the card line, though only as his 2v2 and both-modes figure (docs/web-app-testing-notes.md, finding
        22)."""
        said, out = stated(answer), []
        spans = units(said)
        for c in claims(said):
            if not self.supports(c):
                out.append(c)
                continue
            year = all(isinstance(v, (int, float)) and 1990 <= v <= 2100 for v in c.value[:1 + (c.kind == "record")])
            about = (self.about(said, c, spans) or None) if c.kind in AGREES and not year else None
            if about and not self.supports(c, about):
                mode, player, _ = about
                out.append(replace(c, about=" in ".join(x for x in (self.names.get(player), mode) if x)))
        return out

    def about(self, said, claim, spans):
        """(mode, player, names) for the claim's sentence, or (): the one mode it names, 1v1 or 2v2 and not both
        together, and the one player in view it names, either None if it names none or several."""
        a, b = next(((a, b) for a, b in spans if a <= claim.start < b), (claim.start, claim.end))
        text = said[a:b].casefold()
        named = modes(text)
        mode = next(iter(named)) if len(named) == 1 and "both" not in named else None
        players = [n for n in self.names if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text)]
        player = players[0] if len(players) == 1 else None
        return (mode, player, tuple(self.names)) if mode or player else ()


def rounded(value, target, precision):
    """Whether a value, rounded half up or cut at the precision, gives the target."""
    q = value / precision
    return any(abs(n * precision - target) <= precision * 1e-6 for n in (math.floor(q + 0.5), math.floor(q)))


def rate(target, precision, scale, evidence):
    """Whether the target is a rate of two numbers in one row: a/b (a at most b) or a/(a+b), times the scale."""
    for row in evidence.rows:
        for i, a in enumerate(row):
            for j, b in enumerate(row):
                if i != j and ((0 < b and a <= b and rounded(scale * a / b, target, precision))
                               or (0 < a + b and rounded(scale * a / (a + b), target, precision))):
                    return True
    return False


def decimal(value, evidence):
    figure, precision = value
    if precision >= 1:
        return figure in evidence.values
    return (any(rounded(v, figure, precision) or rounded(100 * v, figure, precision) for v in evidence.values)
            or rate(figure, precision, 1, evidence) or rate(figure, precision, 100, evidence))


def percent(value, evidence):
    figure, precision = value
    return (any(rounded(v, figure, precision) or rounded(100 * v, figure, precision) for v in evidence.values)
            or rate(figure, precision, 100, evidence))


def dollars(value, evidence):
    figure, precision, significant = value
    return figure in evidence.values or (significant >= 2 and any(rounded(v, figure, precision) for v in evidence.values))


def record(value, evidence):
    """Both numbers in one row (evidence, or a list of rows), in either order; for a range of years, each year."""
    a, b = value
    rows = evidence if isinstance(evidence, list) else evidence.rows
    if all(1900 <= n <= 2100 for n in value):  # a range of years
        return any(a in row for row in rows) and any(b in row for row in rows)
    return any(a in row and b in row and (a != b or row.count(a) > 1) for row in rows)


# A claim of these kinds about one player or one mode needs a row about them (Window.unsupported)
AGREES = {"number", "word", "ordinal", "record"}
BOTH_MODES = re.compile(r"\b1v1s?\s*(?:and|&|/|\+|or)\s*2v2s?\b|\b2v2s?\s*(?:and|&|/|\+|or)\s*1v1s?\b|\bboth\s+modes\b"
                        r"|\ball\s+modes\b|\bcombined\b|\boverall\b|\bin\s+total\b|\bin\s+all\b")
ONE_MODE = {"1v1": re.compile(r"\b1v1s?\b|\bsingles\b"), "2v2": re.compile(r"\b2v2s?\b|\bdoubles\b")}


def modes(text):
    """The modes a casefolded text names: '1v1', '2v2', and 'both' for both together ('1v1 and 2v2', 'both modes',
    'in all'), whose words don't also count as each mode."""
    found = {"both"} if BOTH_MODES.search(text) else set()
    text = BOTH_MODES.sub(" ", text)
    return found | {m for m, pattern in ONE_MODE.items() if pattern.search(text)}


def fits(row, mode, player, names):
    """Whether a row may support a claim about one mode and one player (either None): unless it names modes and not
    that one, or names players in view and not that one. A row naming neither fits anything."""
    text = row.text
    if mode:
        named = modes(text)
        if named and mode not in named:
            return False
    if player:
        named = [n for n in names if n in text and re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text)]
        if named and player not in named:
            return False
    return True


RULES = {
    "format": lambda value, evidence: True,
    "list": lambda value, evidence: True,
    "category": lambda value, evidence: True,
    "datetime": lambda value, evidence: value[:3] in evidence.dates and value[3:] in evidence.times,
    "date": lambda value, evidence: value in evidence.dates,
    "month": lambda value, evidence: value in evidence.months,
    "day": lambda value, evidence: value in evidence.days,
    "time": lambda value, evidence: (value[2] is None or value[2] in UTC) and value[:2] in evidence.times,
    "money": dollars,
    "percent": percent,
    "scope": lambda value, evidence: value[0] in evidence.values or value[0] in evidence.scope,
    "record": record,
    "ordinal": lambda value, evidence: value[0] in evidence.values,
    "number": decimal,
    "word": lambda value, evidence: value[0] in evidence.values,
}


# Leaving out the claims an answer can't keep

ABBREVIATIONS = {"vs", "e.g", "i.e", "etc", "approx", "no", "st", "jr", "sr", "mr", "ms", "dr", "inc", "ltd"}


def units(answer):
    """The answer's claims as (start, end): each table cell, and each sentence of any other line, without the line's
    markup ('- ', '1. ', '### ', '> ')."""
    spans, offset = [], 0
    for line in answer.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if body.lstrip().startswith("|"):
            spans += [(offset + m.start(), offset + m.end()) for m in re.finditer(r"[^|]+", body) if m[0].strip()]
        else:
            start = re.match(r"[ \t]*(?:#{1,6}[ \t]+|>[ \t]*|[-*+][ \t]+|\d+[.)][ \t]+)*", body).end()
            for end in sentence_ends(body, start):
                spans.append((offset + start, offset + end))
                start = end
        offset += len(line)
    return [(a + len(answer[a:b]) - len(answer[a:b].lstrip()), b - len(answer[a:b]) + len(answer[a:b].rstrip()))
            for a, b in spans if answer[a:b].strip()]


def sentence_ends(body, start):
    """Where each sentence of a line ends: after a full stop, question or exclamation mark (and any bold, quote or
    bracket closing it) that whitespace follows, unless it ends an abbreviation such as 'vs.'; then the line's end."""
    for i in range(start, len(body)):
        if body[i] not in ".!?":
            continue
        j = i + 1
        while j < len(body) and body[j] in "*_\"'”’)]":
            j += 1
        word = re.search(r"([A-Za-z.]+)$", body[start:i])
        if j < len(body) and body[j].isspace() and not (body[i] == "." and word and word[1].lower() in ABBREVIATIONS):
            yield j
            start = j
    yield len(body)


MARKUP = re.compile(r"[ \t]*(?:#{1,6}[ \t]+|>[ \t]*|[-*+][ \t]+|\d+[.)][ \t]+)*")  # a line's markup before its text
NOT_CONFIRMED_CELL = "not confirmed"


def without(answer, flagged):
    """The answer with each claim (units) holding a flagged number left out, and what was left out: [{claim,
    replacement, numbers}], in the answer's order. A sentence goes; a list item or a heading that is its line's only
    claim goes with its line; a table cell says "not confirmed", so the table keeps its shape. left_out gives the
    line that says so (decided 2026-11-20): live, sentences that replaced claims ("I couldn't confirm the number from
    the data.") read as noise cut loose from what they replaced, and one answer was half such lines
    (docs/web-app-testing-notes.md, findings 11 and 15)."""
    spans, by_unit = units(answer), {}
    for c in flagged:
        unit = next(((a, b) for a, b in spans if a <= c.start < b), (c.start, c.end))
        by_unit.setdefault(unit, []).append(c)
    out, replaced = answer, []
    for (a, b), found in sorted(by_unit.items(), reverse=True):
        start = out.rfind("\n", 0, a) + 1
        end = len(out) if out.find("\n", b) < 0 else out.find("\n", b)
        if out[start:end].lstrip().startswith("|"):
            new, cut = NOT_CONFIRMED_CELL, (a, b)
        elif MARKUP.fullmatch(out[start:a]) and not out[b:end].strip():
            new, cut = "", (start, min(end + 1, len(out)))
        else:
            stop = b
            while stop < end and out[stop] in " \t":
                stop += 1
            new, cut = "", (a, stop)
        replaced.append({"claim": answer[a:b], "replacement": new, "numbers": [c.text for c in found]})
        out = out[:cut[0]] + new + out[cut[1]:]
    return re.sub(r"\n{3,}", "\n\n", out).strip(), replaced[::-1]


def left_out(replaced):
    """The line ending an answer that without() left claims out of, with no number of its own to check."""
    return ("(I left out a statement I couldn't confirm from the data.)" if len(replaced) == 1 else
            "(I left out some statements I couldn't confirm from the data.)")
