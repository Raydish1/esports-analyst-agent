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
    reversed: bool = False  # a record the results give the other way round for the player it's written about


class Row(list):
    """A result's row: its numbers, and the texts beside them, which say whom and which mode they're about; for a
    table's row, its columns and cells as the result gives them."""

    def __init__(self, columns=None, cells=None):
        super().__init__()
        self.texts = []
        self.columns, self.cells = columns, cells

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
        self.tables = []  # each table's rows, for a count word that counts tied rows (counts)
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

    def state(self, years=(), dates=()):
        """Facts the system prompt states about the data, which any answer may cite (react.prompt_facts): each year as
        a number, each date as a date only, so a date's day and month aren't numbers it holds."""
        for year in years:
            self.number(float(year), None)
        for y, m, d in dates:
            self.date(y, m, d)

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
            columns = value.get("columns") if isinstance(value.get("columns"), list) else None
            for key, item in value.items():
                if key == "rows" and isinstance(item, list):
                    group = []
                    for cells in item:
                        listed = Row(columns, cells if isinstance(cells, list) else None)
                        self.rows.append(listed)
                        group.append(listed)
                        self.walk(cells, listed)
                    self.tables.append(group)
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
        """The claims an answer states (stated) that nothing in the conversation supports, a count word counting a
        result's rows supported as Window.unsupported supports it (counted)."""
        said = stated(answer)
        spans, found = units(said), claims(said)
        return [c for c in found if not self.supports(c) and not counted(c, said, spans, found, [self])]

    def counts(self, n, values=(), top=False):
        """Whether a count word n counts rows of one result: n rows sharing one of the values (a tie, 'the two tied
        at 34'), or with top, a result of n rows or more ('the top two')."""
        return any((top and len(group) >= n) or any(sum(v in r for r in group) == n for v in values)
                   for group in self.tables)


class Window:
    """The evidence a turn's answer may cite: its own tool results and the previous turn's, each an Evidence, which is
    what the model has in view, as react.Conversation keeps older turns as question and answer only. An older turn's
    results, and every earlier answer, don't count (decided 2026-11-19): in the web app's live testing, an answer's
    small numbers stood because some tool result many turns back held them."""

    def __init__(self, *evidence, names=None, subject=None):
        self.evidence = evidence
        self.names = names or {}  # the players in view, casefolded name -> as written, for about
        self.subject = subject  # the one player the turn's results are about, casefolded, for a record's owner

    def supports(self, claim, about=None):
        return any(e.supports(claim, about) for e in self.evidence)

    def unsupported(self, answer):
        """The claims nothing in view supports, then those only a row about another player or mode supports, each
        with whom and which mode it's about (decided 2026-11-20): live, "Phazon's 12 gold medals in 1v1" passed, as
        12 was in the card line, though only as his 2v2 and both-modes figure (docs/web-app-testing-notes.md, finding
        22)."""
        said, out = stated(answer), []
        spans = units(said)
        found = claims(said)
        for c in found:
            if self.counted(c, said, spans, found):  # a count of a result's rows, about no one player or mode
                continue
            if not self.supports(c):
                out.append(c)
                continue
            year = all(isinstance(v, (int, float)) and 1990 <= v <= 2100 for v in c.value[:1 + (c.kind == "record")])
            about = (self.about(said, c, spans) or None) if c.kind in AGREES and not year else None
            if about and not self.supports(c, about):
                mode, player, _ = about
                out.append(replace(c, about=" in ".join(x for x in (self.names.get(player), mode) if x)))
                continue
            pair = self.owner(said, c, spans) if c.kind == "record" and not year else None
            if pair:
                owner, other = pair
                given = {(w, l) for e in self.evidence for row in e.rows for who, against, w, l, _ in sides(row, self.names)
                         if who == owner and (other is None or against in (other, None))}
                won, lost = c.value
                if (lost, won) in given and (won, lost) not in given:  # live, volst 2-1 where the rows say 1-2
                    against = f" against {self.names[other]}" if other else ""
                    out.append(replace(c, about=f"{self.names[owner]}{against}, whose record the results give as"
                                                f" {lost}-{won}", reversed=True))
        return out

    def lopsided(self, answer, claim):
        """Whether the record behind a characterization ('Raydish dominates') is lopsided: its owner's record against
        the other player, as the results give it, at least twice the losses in wins and 2 wins ahead (decided
        2026-11-21: finding 35's 2-1 isn't; 5-1 and 7-3 are). None when no such record is in view."""
        said = stated(answer)
        pair = self.owner(said, claim, units(said))
        if not pair:
            return None
        owner, other = pair
        other = other or (self.subject if self.subject != owner else None)  # 'Raydish dominates the series': volst's
        given = {(w, l) for e in self.evidence for row in e.rows for who, against, w, l, games in sides(row, self.names)
                 if who == owner and not games and (other is None or against in (other, None))}
        if not given:
            return None
        return any(w >= 2 * l and w - l >= 2 for w, l in given)

    def owner(self, said, claim, spans):
        """(whose record a record claim is, against whom or None), as its sentence writes it; or None.
        - The nearest player in view named before it who isn't an object ('Impala holds a 2-1 lead', 'Raydish beat
          volst 2-1': 'beat volst' is an object, and so is a name joined to one, 'against A and B'), or the first of
          names joined by 'and' ('A and B have a 2-1 record'), against the other player named.
        - But a player a list writes the record right after ('**Raydish** (3 sets, 2-1 record)', 'Raydish: 2-1'), in
          an answer about one subject who isn't named before it: the subject's record against them, unless the line
          names the player a winner ('Winner: Raydish (2-0)'). Live, volst's list of opponents had his 1-2 against
          Raydish as 2-1 (docs/web-app-testing-notes.md, finding 34). Under a rank_pairs(side="opponents") table
          about the subject, the list is of records against the subject, so each is the listed player's own: in round
          six's reruns, Marckiem00's right 6-1 against Zivai was sent back as reversed (a28).
        - None if no player is named before it, or a word for losing comes between ('lost 1-2 to'), as people write a
          loss in either order."""
        a, b = next(((a, b) for a, b in spans if a <= claim.start < b), (claim.start, claim.end))
        before, after = said[a:claim.start].casefold(), said[claim.end:b].casefold()
        found = sorted((m.start(), m.end(), n) for n in self.names
                       for m in re.finditer(rf"(?<!\w){re.escape(n)}(?!\w)", before))
        subjects, objects, last = [], set(), None  # an object's coordinated names are objects too ('against A and B')
        for start, end, n in found:
            joined = last is not None and JOINED.search(before[max(0, start - 10):start])
            if OBJECT.search(before[max(0, start - 12):start]) or (joined and last in objects):
                objects.add(n)
            else:
                subjects.append((start, end, n, bool(joined)))
            last = n
        if not subjects:
            return None
        while len(subjects) > 1 and subjects[-1][3]:  # 'A and B have a 2-1 record' is A's, the first of them
            subjects.pop()
        start, end, name, _ = subjects[-1]
        between = before[end:]
        if LOSING.search(between):
            return None
        others = [n for _, _, n in found if n != name] + [n for n in self.names if n != name and n in after
                                                          and re.search(rf"(?<!\w){re.escape(n)}(?!\w)", after)]
        if (self.subject and name != self.subject and self.subject not in before and LISTED.match(between)
                and not WINNER.search(before[max(0, start - 20):start])):
            return (name, self.subject) if self.against_subject() else (self.subject, name)
        return name, (others[0] if others else None)

    def against_subject(self):
        """Whether a rank_pairs(side="opponents") table about the subject is in view (its wins_vs_<subject> column)."""
        key = f"{VS}{self.subject}"
        return any(c.casefold() == key for e in self.evidence for row in e.rows for c in (row.columns or ()))

    def counted(self, claim, said, spans, found):
        return counted(claim, said, spans, found, self.evidence)

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


# A record's owner (Window.owner): a name after one of these is the record's object, and a word for losing between
# the owner and the record leaves the record unread, as people write a loss in either order
OBJECT = re.compile(r"\b(?:against|vs\.?|versus|over|to|with|from|beat|beats|beating|defeated|defeats)\W*$")
JOINED = re.compile(r"\b(?:and|or|&)\W*$|,\W*$")
WINNER = re.compile(r"\b(?:winner|winners|won|wins|champion|beat|beats)\b")
LISTED = re.compile(r"[\s*_\"'`]*(?:\(|:|-|–|—|\|)")  # a name a list writes a record right after: 'X (2-1)', 'X: 2-1'
LOSING = re.compile(r"\b(?:lost|loses|lose|losing|loss|fell|falls|beaten|defeated by|trails|trailing|behind)\b")
WON_LOST = re.compile(r"([^.;:()]+?)\s+won\s+(\d+)\s+and\s+lost\s+(\d+)([^;.]*)")
AGAINST = re.compile(r"([^.;:()]+?)\s+(\d+)\s*-\s*(\d+)\s+against\s+([^.;:()]+)")
VS = "wins_vs_"
SIDES = [(("player", "name", "player_name"), "wins", "losses", ("opponent", "opponent_name")),
         (("player",), "player_wins", "opponent_wins", ("opponent",)),
         (("winner", "winner_name"), "winner_games", "loser_games", ("loser", "loser_name"))]


def named(text, names, last=False):
    """The player in view a text fragment names, the last one in it with last, else the first; or None."""
    found = sorted((m.start(), n) for n in names for m in re.finditer(rf"(?<!\w){re.escape(n)}(?!\w)", text))
    return (found[-1] if last else found[0])[1] if found else None


def sides(row, names):
    """Each (player, against whom or None, wins, losses, whether they're one set's games) a row gives from one
    player's side: a table's columns (a player's wins and losses, player_wins and opponent_wins, a set's winner_games
    and loser_games), and its texts' "X won 1 and lost 2 ... against Y" and "X 1-5 against Y", each for both players it
    names. Names are the casefolded names in view."""
    out = []
    if row.columns and row.cells and len(row.columns) == len(row.cells):
        cell = dict(zip(row.columns, row.cells))
        def who(keys):
            return next((v.casefold() for k in keys for v in [cell.get(k)] if isinstance(v, str) and v.casefold() in names),
                        None)
        for subject, w, l, other in SIDES:
            if all(isinstance(cell.get(k), (int, float)) and not isinstance(cell.get(k), bool) for k in (w, l)):
                a, b, games = who(subject), who(other), w == "winner_games"
                out += ([(a, b, cell[w], cell[l], games)] if a else []) + ([(b, a, cell[l], cell[w], games)] if b else [])
        for key in cell:  # rank_pairs(side="opponents"): each row player's record against the player in its columns
            other = key[len(VS):] if key.startswith(VS) else None
            w, l = key, f"losses_vs_{other}"
            if other and all(isinstance(cell.get(k), int) and not isinstance(cell.get(k), bool) for k in (w, l)):
                a, b = who(("player",)), other.casefold() if other.casefold() in names else None
                out += ([(a, b, cell[w], cell[l], False)] if a else []) + ([(b, a, cell[l], cell[w], False)] if b else [])
    for text in row.texts:
        t = text.casefold()
        for m in WON_LOST.finditer(t):
            a = named(m[1], names, last=True)
            b = named(m[4].split("against", 1)[1], names) if "against" in m[4] else None
            out += [(a, b, int(m[2]), int(m[3]), False)] if a else []
        for m in AGAINST.finditer(t):
            a, b = named(m[1], names, last=True), named(m[4], names)
            out += ([(a, b, int(m[2]), int(m[3]), False)] if a else []) + ([(b, a, int(m[3]), int(m[2]), False)] if b else [])
    return out


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


def counted(claim, said, spans, found, evidence):
    """Whether a count word counts a result's rows (Evidence.counts) in any of the evidence: after 'top', a ranking of
    that many rows or more; else that many rows of one result sharing a number its sentence states. Live, "the top two
    tied at 34 sets" was cut for its "two", under a right list (docs/web-app-testing-notes.md, finding 30). The
    agent's check (Window) and the scorers' (Evidence) both read it so."""
    if claim.kind != "word" or not 2 <= claim.value[0] <= 10:
        return False
    top = said[max(0, claim.start - 4):claim.start].casefold() == "top "
    a, b = next(((a, b) for a, b in spans if a <= claim.start < b), (claim.start, claim.end))
    values = [c.value[0] for c in found if a <= c.start < b and c is not claim and c.kind in ("number", "ordinal")]
    return any(e.counts(claim.value[0], values, top) for e in evidence)


def restates(replaced, kept):
    """Whether every claim left out restates numbers the answer keeps: each left-out claim has numbers besides the
    ones that took it out, and the kept text states them all. Then no line says something was left out: live, such a
    line under a right list read as the answer being doubtful (finding 30)."""
    numbers = {c.value[0] for c in claims(stated(kept)) if c.kind in ("number", "ordinal")}
    for r in replaced:
        own = {c.value[0] for c in claims(stated(r["claim"])) if c.kind in ("number", "ordinal")
               and c.text not in r["numbers"]}
        if not own or not own <= numbers:
            return False
    return bool(replaced)


def left_out(replaced):
    """The line ending an answer that without() left claims out of, with no number of its own to check."""
    return ("(I left out a statement I couldn't confirm from the data.)" if len(replaced) == 1 else
            "(I left out some statements I couldn't confirm from the data.)")
