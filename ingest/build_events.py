"""Build step 2 (docs/build-plan.md §1): `events`, `format_rules`, `event_aliases`, and one
`event_sources` row per event, from the Stats API's official-event listings and curation/.

Events come from the full ListEvents listings, every page of both modes. The per-year listings are
check 1's cross-check. An event listed in several responses takes the newest one.

curation/events.csv fills the curated columns. A curated row naming an event the listings don't have
stops the build, and so does a competition whose phases are in different modes. A dev build (--event,
--dev) loads only the chosen events, but it still checks every curated row, so it fails where a full
build would.

`event_sources` gets each event's platform here, from its ID. The steps that read the platforms'
responses fill in the rest: platform ID, state, and the platform's own totals.

`event_terms` stand for words in event names, so a term whose phrase matches no event yet (MSI) is
logged, not an error. Such a term still tells the agent what people mean.
"""

from collections import defaultdict

from curation import CurationError
from names import normalize_words

PLATFORMS = {"CM": "challengermode", "SGG": "startgg"}


def listed_events(reader):
    """{event ID: (record, fetched_at)} from the full listings, the newest response winning."""
    events = {}
    for response in reader.responses("/event"):
        if "year" in response.params:  # a per-year listing
            continue
        for record in response.body.get("tournaments") or []:
            events[record["id"]] = (record, response.fetched_at)  # responses come oldest first
    return events


def platform(event_id, host):
    """Where an event's placements come from: the 'series/...' finals are only in the Stats API."""
    return "stats_api" if event_id.startswith("series/") else PLATFORMS[host]


def mode(record, override):
    return override.mode_override if override and override.mode_override else ("2v2" if record["isTwos"] else "1v1")


def step(build):
    cur, listed = build.curation, listed_events(build.reader)
    chosen = set(listed) if build.events is None else build.events
    problems = [f"--event {eid}: not an official event in the cache" for eid in sorted(chosen - set(listed))]
    overrides = {o.event_id: o for o in cur.events}
    problems += [f"events.csv:{o.line}: no such event: {o.event_id}" for o in cur.events if o.event_id not in listed]
    problems += [f"event_aliases.csv:{a.line}: no such event: {a.event_id}"
                 for a in cur.event_aliases if a.event_id not in listed]
    competitions = defaultdict(list)
    for o in cur.events:
        if o.competition_id and o.event_id in listed:
            competitions[o.competition_id].append(o)
    for competition, phases in sorted(competitions.items()):
        if len({mode(listed[o.event_id][0], o) for o in phases}) > 1:
            problems.append(f"events.csv:{phases[0].line}: the phases of {competition!r} are in different modes")
    if problems:
        raise CurationError(problems)

    rows = []
    for event_id in sorted(chosen, key=lambda e: (listed[e][0]["startTime"], e)):
        record, fetched_at = listed[event_id]
        o = overrides.get(event_id)
        rows.append((event_id, record["host"], record["tournamentName"], record.get("eventName"),
                     event_id.split("/")[1] if event_id.startswith("tournament/") else None,
                     record["year"], record["startTime"], int(bool(record["isOfficial"])),
                     int(bool(record["isTwos"])), int(bool(record["isOnline"])),
                     o and o.format_override, o and o.mode_override, o and o.competition_id, o and o.phase_order,
                     fetched_at))
    build.db.executemany(
        "INSERT INTO events (event_id, host, tournament_name, event_name, sgg_tournament_slug, year, start_time,"
        " is_official, is_twos, is_online, format_override, mode_override, competition_id, phase_order, fetched_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    build.db.executemany("INSERT INTO format_rules (pattern, format, priority) VALUES (?, ?, ?)", cur.format_rules)
    build.db.executemany("INSERT INTO event_aliases (alias, event_id) VALUES (?, ?)",
                         [(a.alias, a.event_id) for a in cur.event_aliases if a.event_id in chosen])
    build.db.executemany("INSERT INTO event_terms (term, means, note) VALUES (?, ?, ?)", cur.event_terms)
    names = [f" {normalize_words(r['tournamentName'] + ' ' + (r.get('eventName') or ''))} " for r, _ in listed.values()]
    for term in cur.event_terms:
        if not any(f" {term.means} " in name for name in names):
            build.log(f"  event term {term.term!r}: no official event's name has {term.means!r} yet")
    build.db.executemany("INSERT INTO event_sources (event_id, platform, fetched_at) VALUES (?, ?, ?)",
                         [(r[0], platform(r[0], r[1]), r[-1]) for r in rows])
    twos = sum(r[8] for r in rows)
    curated = sum(1 for o in cur.events if o.event_id in chosen)
    build.info["events"] = str(len(rows))
    build.log(f"  {len(rows)} events ({len(rows) - twos} listed as 1v1, {twos} as 2v2), {curated} with a curated row;"
              f" {len(cur.format_rules)} format rules; {sum(1 for a in cur.event_aliases if a.event_id in chosen)}"
              f" event aliases")
