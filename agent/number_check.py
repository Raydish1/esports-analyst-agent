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
"""

import json
import math
import re
from dataclasses import dataclass
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
        row = []
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
            own = []
            self.rows.append(own)
            for key, item in value.items():
                if key == "rows" and isinstance(item, list):
                    for cells in item:
                        listed = []
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
        for found in {*re.findall(NUM, text), *re.findall(r"\d+(?:\.\d+)?", text)}:
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

    def supports(self, claim):
        """Whether the claim is what a tool returned, or the question wrote, as such or by its kind's derivation."""
        written = re.compile(rf"(?<!\w){re.escape(squeeze(claim.text))}(?!\w)")
        return any(written.search(q) for q in self.questions) or RULES[claim.kind](claim.value, self)

    def unsupported(self, answer):
        """The claims an answer states (stated) that nothing in the conversation supports."""
        return [c for c in claims(stated(answer)) if not self.supports(c)]


class Window:
    """The evidence a turn's answer may cite: its own tool results and the previous turn's, each an Evidence, which is
    what the model has in view, as react.Conversation keeps older turns as question and answer only. An older turn's
    results, and every earlier answer, don't count (decided 2026-11-19): in the web app's live testing, an answer's
    small numbers stood because some tool result many turns back held them."""

    def __init__(self, *evidence):
        self.evidence = evidence

    def supports(self, claim):
        return any(e.supports(claim) for e in self.evidence)

    def unsupported(self, answer):
        return [c for c in claims(stated(answer)) if not self.supports(c)]


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
    a, b = value
    if all(1900 <= n <= 2100 for n in value):  # a range of years
        return a in evidence.values and b in evidence.values
    return any(a in row and b in row and (a != b or row.count(a) > 1) for row in evidence.rows)


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


# Replacing the claims an answer can't keep

ABBREVIATIONS = {"vs", "e.g", "i.e", "etc", "approx", "no", "st", "jr", "sr", "mr", "ms", "dr", "inc", "ltd"}
STOP = {"a", "an", "the", "and", "or", "but", "with", "at", "on", "in", "for", "from", "to", "by", "as", "than", "of",
        "which", "that", "while", "after", "before", "since", "is", "are", "was", "were", "has", "have", "had"}
NOUNS = {"datetime": "the date and time", "date": "the date", "month": "the date", "day": "the date",
         "time": "the time", "money": "the amount", "percent": "the percentage", "record": "the record",
         "ordinal": "the placement", "scope": "the cutoff"}


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


def describe(claim, answer):
    """What a claim states, without its number: 'the time', 'the number of games won', 'the career earnings'. A
    player's claim (kind player, which react.py makes for a name no tool in view returned) is 'this about Zivai'."""
    if claim.kind == "player":
        return f"this about {claim.value[0]}"
    if claim.kind in ("number", "word") and re.search(r"\b(?:player[ _-]?)?id\b[\s:#=*]*$", answer[:claim.start], re.I):
        return "the player ID"
    words = []
    for token in answer[claim.end:].split()[:4]:
        core = re.match(r"[A-Za-z][\w'’-]*|\d+v\d+", token.strip("*_(\"“"))
        if not core or core[0].lower() in STOP:
            if words or claim.kind != "money" or not core:
                break
            continue  # '$12,500 in career earnings': the words after 'in'
        words.append(core[0])
        if len(words) == 3 or len(token.strip("*_(\"“")) > len(core[0]):
            break
    if words and claim.kind in ("money", "percent"):
        return "the " + " ".join(words)
    if claim.kind in ("number", "word"):
        if words:
            return "the number of " + " ".join(words)
        return "the year" if claim.kind == "number" and 1900 <= claim.value[0] <= 2100 else "the number"
    return NOUNS[claim.kind]


def joined(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def without(answer, flagged):
    """The answer with each claim (units) holding a flagged number replaced by a sentence saying what couldn't be
    confirmed, and what was replaced: [{claim, replacement, numbers}], in the answer's order."""
    spans, by_unit = units(answer), {}
    for c in flagged:
        unit = next(((a, b) for a, b in spans if a <= c.start < b), (c.start, c.end))
        by_unit.setdefault(unit, []).append(c)
    out, replaced = answer, []
    for (a, b), found in sorted(by_unit.items(), reverse=True):
        sentence = f"I couldn't confirm {joined(list(dict.fromkeys(describe(c, answer) for c in found)))} from the data."
        replaced.append({"claim": answer[a:b], "replacement": sentence, "numbers": [c.text for c in found]})
        out = out[:a] + sentence + out[b:]
    return out, replaced[::-1]
