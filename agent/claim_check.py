"""Claims an answer makes that no tool makes (decided 2026-11-20; docs/agent-mechanisms.md, M3): the user sent to the
database, and a result judged wrong.

- A referral: the answer tells the user to run a query, or to look in the database, a view or a table, or says that
  further analysis would be needed, instead of running it. Live, an answer told the user to query v_player_medals
  themselves, a view it never queried, and another ended "To confirm their highest placement, further analysis ...
  would be needed" (docs/web-app-testing-notes.md, findings 22 and 26). The user can't run queries; the agent can.
- A judgment: the answer calls a result an anomaly, an error, a glitch, an inconsistency or a conflict, when no tool
  result in view says the data is wrong there. Live, Renivic's 513th place at Combo Breaker Online 2020 was "likely a
  data anomaly" (2,296 players placed there), and a card's figure was "in conflict" with a result of another mode
  (findings 22 and 27). A tool says the data is wrong where it marks a status (placements_unreliable, cancelled, held
  out) or unscored sets; with such a marker in view, or a question that asks about errors itself, judgments aren't
  checked. Nor is a judgment the answer denies ("this isn't an error").

Three more kinds since 2026-11-21 (round five):
- A placeholder: a slot where a fact should be, "[Opponent Name]", "[X]", "X wins", "X-Y". Live, an answer gave a
  template of slots for volst's best record and never queried again (docs/web-app-testing-notes.md, finding 33).
- A relaxation: the answer says it removed a condition (a filter, a minimum) right after a query that returned no
  rows, when no query ran without it (finding 33: "without the 5-set minimum", then slots).
- A characterization the record doesn't state: "dominates", "crushed", "one-sided", "far superior". Live, a 2-1 series
  was "Raydish dominates the head-to-head" (finding 35). Not checked when the question uses such a word itself ("the
  most dominant win" is a defined measure, and "dominant" isn't one of the words).

A referral or a relaxation states nothing, so it's left out with no line saying so (SILENT); the other kinds go with
the left-out line, as an unconfirmed number does.

Each found claim is a number_check.Claim, so number_check.without can leave it out of a final text."""

import re

from number_check import Claim, units

FLAGS = re.I
REFERRALS = [re.compile(p, FLAGS) for p in [
    r"\b(?:run|execute|use|try|write)\s+(?:this|the\s+following|a|an|the|your\s+own)\s+(?:sql\s+)?(?:quer(?:y|ies)|sql)\b",
    r"\bquery(?:ing)?\s+(?:the\s+)?(?:database|db|dataset|data\s+directly|view|table|v_\w+)\b",
    r"\b(?:you|users?|one)\s+(?:can|could|may|might|should|would\s+need\s+to|need\s+to|will\s+need\s+to)\s+"
    r"(?:query|run\s+(?:a|the|this)\s+query|write\s+a\s+query|check\s+the\s+(?:database|view|table)|look\s+(?:at|in)\s+the"
    r"\s+(?:database|view|table))\b",
    r"\b(?:check|look\s+(?:at|in|up\s+in)|consult|inspect|examine)\s+(?:the\s+)?(?:database|db|v_\w+(?:\s+view)?|\w+\s+"
    r"(?:view|table))\b",
    r"\bfurther\s+(?:analysis|queries|querying|investigation|checks?|research|review)\b(?:\s+[^\s.!?]+){0,8}?\s+"
    r"(?:would|will|may|might|is|are|could)(?:\s+be)?\s+(?:needed|required|necessary)\b",
    r"\b(?:would|will|may|might)\s+(?:need|require)\s+(?:further|additional|more|a\s+separate|another)\s+(?:analysis|quer(?:y|ies)"
    r"|investigation|checks?|research|data|lookups?)\b",
]]
SQL_CODE = re.compile(r"```[^\n]*\n(?:(?!```).)*?\bselect\b(?:(?!```).)*?```", re.I | re.S)  # a fenced block of SQL
JUDGMENTS = [re.compile(p, FLAGS) for p in [
    r"\banomal(?:y|ies|ous)\b",
    r"\bglitch(?:es|ed)?\b",
    r"\bdata\s+(?:error|errors|issue|issues|problem|problems|quality|entry\s+error|inconsistenc(?:y|ies)|discrepanc(?:y|ies))\b",
    r"\b(?:error|errors|mistake|mistakes|typo|bug)\s+in\s+the\s+(?:data|records?|database|results?|standings)\b",
    r"\binconsisten(?:t|cy|cies)\b",
    r"\bdiscrepanc(?:y|ies)\b",
    r"\bconflicts?\s+with\b|\bconflicting\b|\bin\s+conflict\b",
    r"\bcontradict(?:s|ed|ion|ions|ory)?\b",
    r"\b(?:(?:likely|probably|possibly|may\s+be|might\s+be|could\s+be)\s+|seems?\s+(?:to\s+be\s+)?|appears?\s+"
    r"(?:to\s+be\s+)?)(?:an?\s+)?(?:error|mistake|typo|incorrect|wrong|inaccurate|misrecorded|mislabell?ed|outlier)\b",
    r"\b(?:incorrectly|wrongly)\s+(?:recorded|entered|listed|reported)\b|\bmis(?:recorded|labell?ed|reported)\b",
]]
PLACEHOLDERS = [re.compile(p) for p in [
    r"\[(?!The page showed)[A-Z][A-Za-z ]{0,30}\](?!\()",  # [Opponent Name], not a link's [text](url)
    r"\[[XYNxyn]\]",
    r"\b[XY]\s+(?:wins|losses|sets|games|times|events|results|medals|placements)\b",
    r"(?<![\w-])[XY]\s*-\s*[XY](?![\w-])",
]]
RELAXED = re.compile(r"\b(?:removed|removing|relaxed|relaxing|dropped|dropping|lifted|lifting|ignored|ignoring|without)\s+"
                     r"(?:the\s+|that\s+|this\s+|a\s+|an\s+)?(?:[\w-]+\s+){0,3}?(?:condition|filter|minimum|requirement"
                     r"|threshold|restriction|limit|constraint|cutoff)s?\b", re.I)
CHARACTERIZATIONS = re.compile(r"\bdominat(?:es|ed|ing|ion)\b|\bcrush(?:es|ed|ing)\b|\bdestroy(?:s|ed|ing)\b|\boutclass"
                               r"(?:es|ed|ing)?\b|\bone-sided\b|\blopsided\b|\b(?:clearly|far|much|vastly|significantly)\s+"
                               r"(?:better|superior|stronger)\b|\bsuperior\b|\bunstoppable\b|\buntouchable\b", re.I)
ASKS_STRONG = re.compile(r"\b(?:dominan\w*|dominat\w*|crush\w*|destroy\w*|one-sided|lopsided|superior|outclass\w*)", re.I)
# A sentence about part of a series ('dominated the early matches', 'in 2025', 'their last three meetings'), whose
# overall record isn't the yardstick for a characterization of it
PART = re.compile(r"\b(?:early|earlier|recent|recently|lately|last|latest|first|later|since|before|after)\b|\b(?:19|20)\d\d\b",
                  re.I)
SILENT = {"referral", "relaxed"}  # kinds that state nothing: left out with no line saying so
NEGATION = re.compile(r"\b(?:no|not|isn't|isn’t|wasn't|wasn’t|aren't|aren’t|without|nor|never|neither)\b(?:\s+\S+){0,3}\s*$",
                      re.I)
# A tool result in view that says the data is wrong somewhere: a status, or sets with no recorded score
MARKERS = ("placements_unreliable", "unreliable", "cancelled", "held_out", "held out", "no recorded score", "unscored")
# A question that asks about errors itself, which an answer may take up
ASKS_ERRORS = re.compile(r"\b(?:error|errors|wrong|mistakes?|anomal\w*|discrepanc\w*|inconsisten\w*|conflict\w*|"
                         r"contradict\w*|typo|bug|glitch\w*|incorrect|accurate|reliable|add\s+up|make\s+sense)\b", re.I)


def found(patterns, text):
    """Each match of the patterns in a text as a Claim of the kind given, in the text's order, overlaps dropped."""
    out = []
    for kind, pattern in patterns:
        out += [Claim(kind, m[0], m.start(), m.end(), ()) for m in pattern.finditer(text)]
    out.sort(key=lambda c: (c.start, -c.end))
    kept, end = [], -1
    for c in out:
        if c.start >= end:
            kept.append(c)
            end = c.end
    return kept


def referrals(answer):
    """The answer's sentences that send the user to the database, and its fenced blocks of SQL."""
    return found([("referral", p) for p in REFERRALS] + [("referral", SQL_CODE)], answer)


def judgments(answer, question, in_view):
    """The answer's judgments that a result is wrong, unless a tool result in view (its text, in_view) marks the data
    as wrong somewhere, or the question asks about errors itself; a denied one doesn't count."""
    if ASKS_ERRORS.search(question) or any(m in in_view.casefold() for m in MARKERS):
        return []
    return [c for c in found([("judgment", p) for p in JUDGMENTS], answer)
            if not NEGATION.search(answer[max(0, c.start - 40):c.start])]


def placeholders(answer):
    """The answer's slots where a fact should be ('[Opponent Name]', '[X] wins')."""
    return found([("placeholder", p) for p in PLACEHOLDERS], answer)


def relaxed(answer):
    """The answer's claims to have removed a condition ('without the 5-set minimum'), for a turn whose last query
    found no rows: react.py checks them only then."""
    return found([("relaxed", RELAXED)], answer)


def characterizations(answer, question):
    """The answer's words for a result that its record doesn't state ('dominates'), unless the question uses one, or
    the sentence is about part of a series (PART). react.py keeps only those whose record in view is close
    (number_check.Window.lopsided)."""
    if ASKS_STRONG.search(question):
        return []
    spans = units(answer)
    def part(c):
        a, b = next(((a, b) for a, b in spans if a <= c.start < b), (c.start, c.end))
        return bool(PART.search(answer[a:b]))
    return [c for c in found([("characterization", CHARACTERIZATIONS)], answer)
            if not NEGATION.search(answer[max(0, c.start - 40):c.start]) and not part(c)]


def without_code(answer):
    """The answer with its fenced blocks of SQL taken out, which without() can't leave out line by line."""
    return re.sub(r"\n{3,}", "\n\n", SQL_CODE.sub("", answer)).strip()
