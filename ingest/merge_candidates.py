"""Merge candidates: Stats API records that may be one person (docs/schema-proposal.md §1).

    python ingest/merge_candidates.py

It reads only the crawl's cache and tables, so it makes no requests, and it can be re-run.

Two records are candidates when their names match once normalized, as aliases are (lowercase,
accents folded, no team tag or punctuation), and their official events don't overlap in time:
two records active in the same period are almost always two people. Pairs already in
curation/player_merges.csv or curation/merge_rejections.csv are skipped.

- Tier 1, accepted automatically: a start.gg-only record and a Challengermode-only record, the
  usual duplicate after the 2025 platform switch. Each must be the name's only record on its
  platform, with no record of the name linked to both, and both must be in the same region. They
  are added to curation/player_merges.csv with a note starting 'auto: tier 1'. A pair touching a
  record already in that file goes to review instead.
- Tier 2: such a cross-platform pair with one piece of that evidence missing: a region unknown,
  or more records of the name on one platform.
- Tier 3: the other cross-platform pairs, and two records on one platform (two start.gg accounts,
  as with Remmy) when the name has no other record, their regions don't conflict, and one of them
  has at least three official events.

Tiers 2 and 3 go to data/review/merge_candidates.csv, strongest first and, within a tier, the most
prominent players first. A decision goes in curation/player_merges.csv (merge) or
curation/merge_rejections.csv (not one person), and the pair isn't proposed again.

A record's region is its PR region, or else the region most of its official events name. Its
activity is every official event it placed in or played: start.gg standings and entrant lists,
Challengermode entrant lists (placed lineups only), and the Stats API placements of stages 3b and
3c.
"""

import collections
import csv
import gzip
import itertools
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone

from cache import CACHE_DIR, CRAWL_DB, ROOT

MERGES = ROOT / "curation" / "player_merges.csv"
REJECTIONS = ROOT / "curation" / "merge_rejections.csv"
REVIEW = ROOT / "data" / "review" / "merge_candidates.csv"
MIN_EVENTS = 3  # same-platform pairs: one record needs at least this many official events
REGION_WORDS = [  # (region, phrases in an event name, words in it); the first match wins
    ("NA", ["north america"], {"na", "us", "usa"}),
    ("EU", ["europe"], {"eu"}),
    ("SA", ["south america", "brazil"], {"sa", "brz"}),
    ("SEA", ["southeast asia", "s.e. asia"], {"sea"}),
    ("MENA", ["middle east"], {"mena"}),
    ("AUS", ["australia", "oceania"], {"aus", "oce"}),
    ("JPN", ["japan"], {"jpn"}),
]


def normalize(name):
    """A name as aliases are matched: no team tag ('Pink | Guichabou' -> 'Guichabou'), accents
    folded, lowercase, letters and digits only."""
    name = unicodedata.normalize("NFKD", (name or "").split("|")[-1])
    return re.sub(r"[\W_]+", "", "".join(c for c in name if not unicodedata.combining(c)).casefold())


def event_region(name):
    lowered = (name or "").lower()
    words = set(re.split(r"[^a-z]+", lowered))
    for region, phrases, tokens in REGION_WORDS:
        if any(p in lowered for p in phrases) or words & tokens:
            return region
    return None


def platform(record):
    return {(True, False): "start.gg", (False, True): "Challengermode", (True, True): "both"}.get(
        (bool(record.get("sggPlayerId")), bool(record.get("cmPlayerId"))), "neither")


class Person:
    """One Stats API record with what the crawl knows about it."""

    def __init__(self, record):
        self.id, self.record, self.name = record["playerId"], record, record.get("name") or ""
        self.platform = platform(record)
        self.events = {}  # event ID -> start time
        self.best = None  # best placement
        self.pr_region = None
        self.region = None

    def add(self, event_id, start, placement=None):
        self.events[event_id] = start
        if placement is not None and (self.best is None or placement < self.best):
            self.best = placement

    @property
    def span(self):
        return (min(self.events.values()), max(self.events.values())) if self.events else None


def separate(a, b):
    """True if the two records' official events don't overlap in time, None if one has none."""
    if not a.span or not b.span:
        return None
    return a.span[1] < b.span[0] or b.span[1] < a.span[0]


def pair_tier(a, b, group):
    """(tier, evidence) for two records sharing a name, or None if they aren't candidates."""
    apart = separate(a, b)
    if apart is False:
        return None
    region = ("same" if a.region and a.region == b.region else
              "unknown" if not (a.region and b.region) else "different")
    by_platform = collections.Counter(p.platform for p in group)
    others = by_platform - collections.Counter((a.platform, b.platform))
    named = "; other records of the name: " + (", ".join(f"{n} {k}" for k, n in sorted(others.items())) or "none")
    if {a.platform, b.platform} == {"start.gg", "Challengermode"}:
        alone = (by_platform["start.gg"] == 1) + (by_platform["Challengermode"] == 1)
        unique = ("neither" if by_platform["both"] else  # a record of the name already links both platforms
                  "both" if alone == 2 else "one" if alone else "neither")
        evidence = f"cross-platform; region {region}{named}" + ("" if apart else "; activity unknown")
        if apart and unique == "both" and region == "same":
            return 1, evidence
        if apart and ((unique == "both" and region == "unknown") or (unique == "one" and region == "same")):
            return 2, evidence
        return 3, evidence
    if len(group) == 2 and region != "different" and max(len(a.events), len(b.events)) >= MIN_EVENTS:
        return 3, f"same platform ({a.platform} and {b.platform}); region {region}{named}"
    return None


def canonical(a, b):
    """The record that stays: the one with more official events, then the earlier one, then the lower ID."""
    return min((a, b), key=lambda p: (-len(p.events), p.span[0] if p.span else float("inf"), p.id))


def candidates(people, merged, rejected):
    """Every candidate pair as (tier, evidence, a, b), with a the record that would stay. Within a tier,
    names shared by fewer other records come first, then the more prominent players."""
    groups = collections.defaultdict(list)
    for person in people.values():
        key = normalize(person.name)
        if key:
            groups[key].append(person)
    found = []
    for group in groups.values():
        for a, b in itertools.combinations(sorted(group, key=lambda p: p.id), 2):
            pair = frozenset((a.id, b.id))
            if pair in rejected or merged.get(a.id, a.id) == merged.get(b.id, b.id):
                continue
            ranked = pair_tier(a, b, group)
            if not ranked:
                continue
            tier, evidence = ranked
            if tier == 1 and (a.id in merged or b.id in merged):
                tier, evidence = 2, evidence + "; one record is already in player_merges.csv"
            keep = canonical(a, b)
            found.append((tier, evidence, keep, b if keep is a else a, len(group)))
    found.sort(key=lambda c: (c[0], c[4], min(p.best or 10 ** 6 for p in c[2:4]), -max(len(p.events) for p in c[2:4]),
                              normalize(c[2].name)))
    return [c[:4] for c in found]


def date(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%d") if stamp is not None else ""


def describe(p):
    """e.g. "'Tinix' on start.gg, 2017-2025, 65 events"."""
    first, last = (date(s)[:4] for s in p.span)
    events = f"{len(p.events)} event{'s' if len(p.events) != 1 else ''}"
    return f"'{p.name}' on {p.platform}, {first if first == last else f'{first}-{last}'}, {events}"


def load(db):
    """Every Stats API record the crawl holds, with its events, best placement and region."""
    records = {}
    for (path,) in db.execute("SELECT path FROM requests WHERE endpoint = '/players' AND status = 200 ORDER BY fetched_at"):
        for record in json.loads(gzip.decompress((CACHE_DIR / path).read_bytes())).get("players") or []:
            if record and record.get("playerId") is not None:
                records[record["playerId"]] = record  # the newest response wins
    people = {pid: Person(r) for pid, r in records.items()}
    by_sgg = {r["sggPlayerId"]: people[pid] for pid, r in records.items() if r.get("sggPlayerId")}
    by_cm = {r["cmPlayerId"].lower(): people[pid] for pid, r in records.items() if r.get("cmPlayerId")}
    start = dict(db.execute("SELECT event_id, start_time FROM crawl_events"))
    for eid, sgg, placement in db.execute(
            "SELECT event_id, sgg_player_id, placement FROM crawl_standings WHERE sgg_player_id IS NOT NULL"
            " UNION ALL SELECT e.event_id, e.sgg_player_id, NULL FROM crawl_entrants e JOIN crawl_set_entrants s"
            " USING (event_id, entrant_id) WHERE e.sgg_player_id IS NOT NULL"):
        if sgg in by_sgg:
            by_sgg[sgg].add(eid, start[eid], placement)
    for eid, user, placement in db.execute("SELECT event_id, user_id, placement FROM crawl_cm_entrants"
                                           " WHERE placement IS NOT NULL"):
        if user.lower() in by_cm:
            by_cm[user.lower()].add(eid, start[eid], placement)
    for eid, pid, placement in db.execute("SELECT event_id, player_id, placement FROM crawl_series_placements"
                                          " UNION ALL SELECT event_id, player_id, placement FROM crawl_gap_placements"):
        if pid in people:
            people[pid].add(eid, start[eid], placement)
    for params, path in db.execute("SELECT params, path FROM requests WHERE endpoint = '/pr' AND status = 200"
                                   " ORDER BY fetched_at"):
        p = dict(json.loads(params))
        for row in json.loads(gzip.decompress((CACHE_DIR / path).read_bytes())).get("prPlayers") or []:
            person = people.get(row["playerId"])
            if person and (p["gameMode"] == "1" or not person.pr_region):
                person.pr_region = p["region"]  # 1v1's PR region first
    names = {}
    for (path,) in db.execute("SELECT path FROM requests WHERE endpoint = '/event' AND status = 200"):
        for e in json.loads(gzip.decompress((CACHE_DIR / path).read_bytes())).get("tournaments") or []:
            names[e["id"]] = f"{e.get('tournamentName') or ''} {e.get('eventName') or ''}"
    for person in people.values():
        counts = collections.Counter(event_region(names.get(eid)) for eid in person.events)
        counts.pop(None, None)
        top = counts.most_common(2)
        majority = top[0][0] if top and (len(top) == 1 or top[0][1] > top[1][1]) else None
        person.region = person.pr_region or majority
    return people


def read_csv(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    sys.stdout.reconfigure(errors="replace")
    db = sqlite3.connect(CRAWL_DB)
    people = load(db)
    merges = read_csv(MERGES)
    merged = {int(r["player_id"]): int(r["canonical_player_id"]) for r in merges}
    for row in merges:  # a canonical record maps to itself, so its merged records count as its pair
        merged.setdefault(int(row["canonical_player_id"]), int(row["canonical_player_id"]))
    if not REJECTIONS.exists():
        REJECTIONS.write_text("player_id,other_player_id,note\n", encoding="utf-8")
    rejected = {frozenset((int(r["player_id"]), int(r["other_player_id"]))) for r in read_csv(REJECTIONS)}
    found = candidates(people, merged, rejected)

    accepted = [(keep, other) for tier, evidence, keep, other in found if tier == 1]
    text = MERGES.read_text(encoding="utf-8")
    with open(MERGES, "a", encoding="utf-8", newline="") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        writer = csv.writer(f, lineterminator="\n")
        for keep, other in accepted:
            writer.writerow([other.id, keep.id, f"auto: tier 1 ({describe(other)}; {describe(keep)}; both {keep.region})"])

    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    columns = ["name", "platform", "region", "first_event", "last_event", "events", "best_placement"]
    with open(REVIEW, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["tier", "evidence", "player_id", *columns, "other_player_id", *(f"other_{c}" for c in columns)])
        for tier, evidence, keep, other in found:
            if tier == 1:
                continue
            row = [tier, evidence]
            for person in (keep, other):
                span = person.span or (None, None)
                row += [person.id, person.name, person.platform, person.region or "", date(span[0]), date(span[1]),
                        len(person.events), person.best or ""]
            writer.writerow(row)
    tiers = collections.Counter(tier for tier, *_ in found)
    print(f"{len(people)} records; candidates: tier 1 {tiers[1]} (added to {MERGES.name}), tier 2 {tiers[2]},"
          f" tier 3 {tiers[3]} (in {REVIEW.relative_to(ROOT).as_posix()})")


if __name__ == "__main__":
    main()
