"""The curated files the builder reads (docs/build-plan.md §2), loaded and checked before the build
reads the cache. A typo stops the build with every problem listed at once, by file and line, and the
live build stays.

This module checks each file's structure: columns, values, duplicate keys, and rows that contradict
each other. Whether an event or player a row names exists is checked by the build step that applies
the file.

    events.csv            mode and format overrides, phase splits, and events that weren't held
                          (status 'cancelled'). A row with no override records that an event's detected
                          format and mode were checked (the review list, §5). Its note goes into the
                          database, so an answer can give the reason.
    format_rules.csv      LIKE patterns on an event's lowercase name, each mapped to a format;
                          the lowest priority wins.
    event_aliases.csv     names people use for events that the data doesn't (BCX, Worlds)
    event_terms.csv       words people use for words in event names ('ltc' for 'low tier city', 'winters'
                          for 'winter championship'), so they keep working for events not yet held
    player_aliases.csv    nicknames
    player_merges.csv     two records that are one person, decided by hand or by a run of
                          merge_candidates.py
    merge_rejections.csv  two records that aren't
    data/review/auto_merges.csv  tier-1 merges an unattended run found (decision 2). A curated merge
                          of the same record, a rejection, or a loop drops one.
    check_exceptions.csv  known check failures that are explained (§3): check ID, subject, note. Whether
                          the subject exists is checked by the checks.
"""

import csv
import re
from collections import defaultdict, namedtuple
from pathlib import Path

from cache import ROOT
from names import normalize, normalize_words
from problems import CurationError

CURATION_DIR = ROOT / "curation"
AUTO_MERGES = ROOT / "data" / "review" / "auto_merges.csv"
MODES = ("1v1", "2v2")
STATUSES = ("cancelled",)  # events.csv status: an official event that was never held
CHECK_IDS = (  # the checks of the build plan's §3, by ID
    "event_totals", "winners", "pr_cross_check", "teams", "completeness", "match_presence", "earnings",
    "stats_api_placements", "no_contests", "snapshot_fallbacks", "pro_series", "integrity", "entrant_sizes",
    "regression", "known_events")
STANDARD = "standard"  # the format of an event no rule or override names
FORMAT_NAME = re.compile(r"^[a-z0-9][a-z0-9_]*$")
COLUMNS = {  # file: (required columns, optional ones); any other column is a typo
    "format_rules.csv": (("pattern", "format", "priority"), ("note",)),
    "events.csv": (("event_id",), ("format_override", "mode_override", "competition_id", "phase_order", "status",
                                   "note")),
    "event_aliases.csv": (("alias", "event_id"), ("note",)),
    "event_terms.csv": (("term", "means"), ("note",)),
    "player_aliases.csv": (("alias", "player_id"), ("note",)),
    "player_merges.csv": (("player_id", "canonical_player_id"), ("note",)),
    "merge_rejections.csv": (("player_id", "other_player_id"), ("note",)),
    "check_exceptions.csv": (("check", "subject"), ("note",)),
}

FormatRule = namedtuple("FormatRule", "pattern format priority")
EventOverride = namedtuple("EventOverride", "event_id format_override mode_override competition_id phase_order status"
                                            " note line")
EventAlias = namedtuple("EventAlias", "alias event_id note line")
EventTerm = namedtuple("EventTerm", "term means note")
PlayerAlias = namedtuple("PlayerAlias", "alias shown_as player_id note line")
Merge = namedtuple("Merge", "player_id canonical_player_id source note line")  # source: 'curated' | 'auto'
CheckException = namedtuple("CheckException", "check subject note line")


class Curation:
    """The curated rows the build steps apply."""

    def __init__(self):
        self.format_rules, self.events, self.event_aliases, self.event_terms, self.player_aliases = [], [], [], [], []
        self.merges = []          # curated merges, then the automatic ones that survived
        self.rejections = set()   # frozensets of two player IDs
        self.dropped_auto = []    # (Merge, reason) for automatic merges a curated row overrode
        self.check_exceptions = []

    def formats(self):
        """Every format an override may name."""
        return {STANDARD} | {rule.format for rule in self.format_rules}


def read(path, name, problems, optional=False):
    """(line number, row) for each row of a CSV file whose columns are as expected."""
    if not path.exists():
        if not optional:
            problems.append(f"{name}: missing")
        return []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        required, allowed = COLUMNS["player_merges.csv" if name.endswith("auto_merges.csv") else name]
        missing = [c for c in required if c not in columns]
        unknown = [c for c in columns if c not in required and c not in allowed]
        if missing or unknown:
            problems.append(f"{name}: " + "; ".join(([f"missing column(s) {', '.join(missing)}"] if missing else [])
                                                   + ([f"unknown column(s) {', '.join(unknown)}"] if unknown else [])))
            return []
        rows = []
        for line, row in enumerate(reader, 2):
            if None in row:  # csv puts fields beyond the header under None
                problems.append(f"{name}:{line}: more fields than columns (a value with a comma needs quotes)")
                continue
            rows.append((line, {k: (v or "").strip() for k, v in row.items()}))
        return rows


def player_id(value, where, column, problems):
    try:
        number = int(value)
    except ValueError:
        problems.append(f"{where}: {column} isn't a player ID: {value!r}")
        return None
    if number == 0:
        problems.append(f"{where}: {column} can't be 0")
        return None
    return number


def chain_end(merges, start):
    """The record start's merges lead to, or None if they loop."""
    seen, current = {start}, start
    while current in merges:
        current = merges[current]
        if current in seen:
            return None
        seen.add(current)
    return current


def load(curation_dir=CURATION_DIR, auto_merges=AUTO_MERGES):
    """Every curated file the builder reads, checked. Raises CurationError listing every problem."""
    curation_dir, problems, cur = Path(curation_dir), [], Curation()
    load_format_rules(read(curation_dir / "format_rules.csv", "format_rules.csv", problems), cur, problems)
    load_events(read(curation_dir / "events.csv", "events.csv", problems), cur, problems)
    load_event_aliases(read(curation_dir / "event_aliases.csv", "event_aliases.csv", problems), cur, problems)
    load_event_terms(read(curation_dir / "event_terms.csv", "event_terms.csv", problems), cur, problems)
    load_player_aliases(read(curation_dir / "player_aliases.csv", "player_aliases.csv", problems), cur, problems)
    load_merges(read(curation_dir / "player_merges.csv", "player_merges.csv", problems),
                read(curation_dir / "merge_rejections.csv", "merge_rejections.csv", problems),
                read(Path(auto_merges), "data/review/auto_merges.csv", problems, optional=True) if auto_merges else [],
                cur, problems)
    load_check_exceptions(read(curation_dir / "check_exceptions.csv", "check_exceptions.csv", problems), cur, problems)
    if problems:
        raise CurationError(problems)
    return cur


def load_format_rules(rows, cur, problems):
    seen = set()
    for line, row in rows:
        where = f"format_rules.csv:{line}"
        pattern, fmt = row["pattern"], row["format"]
        if not pattern:
            problems.append(f"{where}: no pattern")
        elif pattern != pattern.lower():
            problems.append(f"{where}: patterns match a lowercase name, so write {pattern.lower()!r}")
        elif pattern in seen:
            problems.append(f"{where}: pattern {pattern!r} is listed twice")
        if not FORMAT_NAME.match(fmt):
            problems.append(f"{where}: format must be lowercase letters, digits and underscores: {fmt!r}")
        try:
            priority = int(row["priority"])
        except ValueError:
            problems.append(f"{where}: priority isn't a number: {row['priority']!r}")
            continue
        seen.add(pattern)
        cur.format_rules.append(FormatRule(pattern, fmt, priority))


def load_events(rows, cur, problems):
    formats, seen, phases = cur.formats(), set(), defaultdict(list)
    for line, row in rows:
        where = f"events.csv:{line}"
        event_id = row["event_id"]
        if not event_id:
            problems.append(f"{where}: no event_id")
            continue
        if event_id in seen:
            problems.append(f"{where}: {event_id} is listed twice")
            continue
        seen.add(event_id)
        fmt, mode = row.get("format_override", ""), row.get("mode_override", "")
        if fmt and fmt not in formats:
            problems.append(f"{where}: unknown format {fmt!r} (formats: {', '.join(sorted(formats))})")
        if mode and mode not in MODES:
            problems.append(f"{where}: mode_override must be 1v1 or 2v2, not {mode!r}")
        status = row.get("status", "")
        if status and status not in STATUSES:
            problems.append(f"{where}: status must be empty or {', '.join(STATUSES)}, not {status!r}")
        competition, order = row.get("competition_id", ""), row.get("phase_order", "")
        phase = None
        if bool(competition) != bool(order):
            problems.append(f"{where}: a phase needs both competition_id and phase_order")
        elif order:
            if not order.isdigit() or int(order) < 1:
                problems.append(f"{where}: phase_order must be 1, 2, ...: {order!r}")
            else:
                phase = int(order)
                phases[competition].append((phase, line))
        cur.events.append(EventOverride(event_id, fmt or None, mode or None, competition or None, phase,
                                        status or None, row.get("note") or None, line))
    for competition, members in sorted(phases.items()):
        orders = [order for order, _ in members]
        if len(members) < 2:
            problems.append(f"events.csv:{members[0][1]}: competition {competition!r} has only one phase")
        elif len(set(orders)) < len(orders):
            problems.append(f"events.csv:{members[0][1]}: competition {competition!r} repeats a phase_order")


def load_check_exceptions(rows, cur, problems):
    seen = set()
    for line, row in rows:
        where = f"check_exceptions.csv:{line}"
        if row["check"] not in CHECK_IDS:
            problems.append(f"{where}: unknown check {row['check']!r} (checks: {', '.join(CHECK_IDS)})")
        elif not row["subject"]:
            problems.append(f"{where}: no subject (an event or player ID)")
        elif (row["check"], row["subject"]) in seen:
            problems.append(f"{where}: {row['check']} for {row['subject']} is listed twice")
        else:
            seen.add((row["check"], row["subject"]))
            cur.check_exceptions.append(CheckException(row["check"], row["subject"], row.get("note") or None, line))


def load_event_aliases(rows, cur, problems):
    seen = set()
    for line, row in rows:
        where = f"event_aliases.csv:{line}"
        alias = normalize_words(row["alias"])
        if not alias or not row["event_id"]:
            problems.append(f"{where}: needs an alias and an event_id")
        elif (alias, row["event_id"]) in seen:
            problems.append(f"{where}: {alias!r} for {row['event_id']} is listed twice")
        else:
            seen.add((alias, row["event_id"]))
            cur.event_aliases.append(EventAlias(alias, row["event_id"], row.get("note") or None, line))


def load_event_terms(rows, cur, problems):
    seen = set()
    for line, row in rows:
        where = f"event_terms.csv:{line}"
        term, means = normalize_words(row["term"]), normalize_words(row["means"])
        if not term or not means:
            problems.append(f"{where}: needs a term and what it means")
        elif term == means:
            problems.append(f"{where}: {term!r} means itself")
        elif (term, means) in seen:
            problems.append(f"{where}: {term!r} for {means!r} is listed twice")
        else:
            seen.add((term, means))
            cur.event_terms.append(EventTerm(term, means, row.get("note") or None))


def load_player_aliases(rows, cur, problems):
    seen = set()
    for line, row in rows:
        where = f"player_aliases.csv:{line}"
        alias = normalize(row["alias"])
        pid = player_id(row["player_id"], where, "player_id", problems)
        if not alias:
            problems.append(f"{where}: no alias")
        elif pid is not None and (alias, pid) in seen:
            problems.append(f"{where}: {alias!r} for {pid} is listed twice")
        elif pid is not None:
            seen.add((alias, pid))
            cur.player_aliases.append(PlayerAlias(alias, row["alias"], pid, row.get("note") or None, line))


def load_merges(curated_rows, rejection_rows, auto_rows, cur, problems):
    for line, row in rejection_rows:
        where = f"merge_rejections.csv:{line}"
        a = player_id(row["player_id"], where, "player_id", problems)
        b = player_id(row["other_player_id"], where, "other_player_id", problems)
        if a is not None and b is not None:
            if a == b:
                problems.append(f"{where}: a record can't be rejected as a duplicate of itself")
            cur.rejections.add(frozenset((a, b)))
    merges = {}
    for source, file, rows in (("curated", "player_merges.csv", curated_rows),
                               ("auto", "data/review/auto_merges.csv", auto_rows)):
        for line, row in rows:
            where = f"{file}:{line}"
            pid = player_id(row["player_id"], where, "player_id", problems)
            canonical = player_id(row["canonical_player_id"], where, "canonical_player_id", problems)
            if pid is None or canonical is None:
                continue
            merge = Merge(pid, canonical, source, row.get("note", ""), line)
            if pid == canonical:
                problems.append(f"{where}: a record can't be merged into itself")
            elif source == "curated" and pid in merges:
                problems.append(f"{where}: {pid} is already merged into {merges[pid]}")
            elif source == "auto" and pid in merges:
                cur.dropped_auto.append((merge, f"{pid} already has a curated merge, into {merges[pid]}"))
            else:
                merges[pid] = canonical
                problem = merge_conflict(merges, cur.rejections, pid)
                if problem and source == "curated":
                    problems.append(f"{where}: {problem}")
                elif problem:
                    del merges[pid]
                    cur.dropped_auto.append((merge, problem))
                else:
                    cur.merges.append(merge)


def merge_conflict(merges, rejections, pid):
    """Why the merge of pid just added can't stand: a loop, or two records rejected as one person."""
    if chain_end(merges, pid) is None:
        return f"merging {pid} into {merges[pid]} makes a loop"
    for pair in rejections:
        a, b = sorted(pair)
        if chain_end(merges, a) == chain_end(merges, b) and chain_end(merges, a) is not None:
            return f"{a} and {b} would be one person, but merge_rejections.csv says they aren't"
    return None
