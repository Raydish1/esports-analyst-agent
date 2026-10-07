"""Build step 2 (docs/build-plan.md §1): `events`, `format_rules`, `event_aliases`, and one
`event_sources` row per event, from the Stats API's official-event listings and curation/.

Events come from the full ListEvents listings, every page of both modes. The per-year listings are
check 1's cross-check. An event listed in several responses takes the newest one.

curation/events.csv fills the curated columns, including an event's status ('cancelled': never held) and
its note, which an answer can quote. A curated row naming an event the listings don't have
stops the build, and so does a competition whose phases are in different modes. A dev build (--event,
--dev) loads only the chosen events, but it still checks every curated row, so it fails where a full
build would.

`event_sources` gets each event's platform here, from its ID. The steps that read the platforms'
responses fill in the rest: platform ID, state, and the platform's own totals.

`event_terms` stand for words in event names, so a term whose phrase matches no event yet (MSI) is
logged, not an error. Such a term still tells the agent what people mean.

The hold-outs step, after the matches step, applies decision 3: a new event whose entrant sizes don't fit its
mode and format stays out of the counts until a person reviews it. "New" means it has no row in events.csv;
adding one, with overrides or without, records the review (docs/build-plan.md §5). A held-out event keeps its
rows, and events.held_out says why, which v_events turns into counts_as NULL. Only the formats that count are
held to a size: a standard event's entrants have the mode's one or two players, a crew battle's at least two.
Side formats count toward neither mode, so their sizes change no count.
"""

from collections import Counter, defaultdict

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
                     o and o.status, o and o.note, fetched_at))
    build.db.executemany(
        "INSERT INTO events (event_id, host, tournament_name, event_name, sgg_tournament_slug, year, start_time,"
        " is_official, is_twos, is_online, format_override, mode_override, competition_id, phase_order, status, note,"
        " fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    build.db.executemany("INSERT INTO format_rules (pattern, format, priority) VALUES (?, ?, ?)", cur.format_rules)
    build.db.executemany("INSERT INTO event_aliases (alias, event_id, note) VALUES (?, ?, ?)",
                         [(a.alias, a.event_id, a.note) for a in cur.event_aliases if a.event_id in chosen])
    build.db.executemany("INSERT INTO event_terms (term, means, note) VALUES (?, ?, ?)", cur.event_terms)
    names = [f" {normalize_words(r['tournamentName'] + ' ' + (r.get('eventName') or ''))} " for r, _ in listed.values()]
    for term in cur.event_terms:
        if not any(f" {term.means} " in name for name in names):
            build.log(f"  event term {term.term!r}: no official event's name has {term.means!r} yet")
    build.db.executemany("INSERT INTO event_sources (event_id, platform, fetched_at) VALUES (?, ?, ?)",
                         [(r[0], platform(r[0], r[1]), r[-1]) for r in rows])
    for o in cur.events:
        if o.status and o.event_id in chosen:
            build.log(f"  {o.event_id}: {o.status}")
    twos = sum(r[8] for r in rows)
    curated = sum(1 for o in cur.events if o.event_id in chosen)
    build.info["events"] = str(len(rows))
    build.log(f"  {len(rows)} events ({len(rows) - twos} listed as 1v1, {twos} as 2v2), {curated} with a curated row;"
              f" {len(cur.format_rules)} format rules; {sum(1 for a in cur.event_aliases if a.event_id in chosen)}"
              f" event aliases")


def entrant_sizes(db):
    """{event ID: (entrant sizes, match side sizes)}, each a Counter of players -> how many, for every event with
    standings or matches. An entrant's size is its players in the standings; a side's, its players in a stored
    match. A side with no players is left to check 5, which counts entrants whose players are unknown."""
    sizes = defaultdict(lambda: (Counter(), Counter()))
    for event_id, size, n in db.execute(  # in the standings' key order, so no sort
            "SELECT event_id, size, COUNT(*) FROM (SELECT event_id, entrant_key, COUNT(*) AS size FROM standings"
            " GROUP BY event_id, entrant_key) GROUP BY event_id, size"):
        sizes[event_id][0][size] += n
    for event_id, side1, side2, n in db.execute(  # in match_players' key order, so no sort
            "SELECT m.event_id, x.side1, x.side2, COUNT(*) FROM (SELECT match_id, SUM(side = 1) AS side1,"
            " SUM(side = 2) AS side2 FROM match_players GROUP BY match_id) x JOIN matches m USING (match_id)"
            " GROUP BY m.event_id, x.side1, x.side2"):
        for size in (side1, side2):
            if size:
                sizes[event_id][1][size] += n
    return dict(sizes)


def fitting_sizes(mode, fmt):
    """(fewest, most) players per entrant that fit an event's mode and format; most is None for no limit. None if
    any size fits: a side format counts toward neither mode."""
    if fmt == "standard":
        return (2, 2) if mode == "2v2" else (1, 1)
    if fmt == "crew_battle":
        return 2, None
    return None


def players(n):
    return f"{n} player{'s' if n != 1 else ''}"


def size_problems(db, sizes=None):
    """{event ID: why its entrant sizes don't fit} for the events that count, as detected (held_out aside)."""
    sizes = entrant_sizes(db) if sizes is None else sizes
    problems = {}
    for event_id, mode, fmt in db.execute("SELECT event_id, mode, format FROM v_events ORDER BY start_time, event_id"):
        fits = fitting_sizes(mode, fmt)
        if fits is None or event_id not in sizes:
            continue
        fewest, most = fits
        wrong = []
        for what, found in zip(("entrants", "match sides"), sizes[event_id]):
            bad = {n: k for n, k in found.items() if n < fewest or (most is not None and n > most)}
            if bad:
                wrong.append(f"{what} of {', '.join(f'{players(n)} ({k} of {sum(found.values())})' for n, k in sorted(bad.items()))}")
        if wrong:
            expect = players(fewest) if most == fewest else f"at least {players(fewest)}"
            label = mode if fmt == "standard" else f"{mode} {fmt.replace('_', ' ')}"
            problems[event_id] = f"a {label} event should have entrants of {expect}, but it has {' and '.join(wrong)}"
    return problems


def hold_out_step(build):
    """New events whose entrant sizes don't fit their mode and format stay out of the counts until reviewed."""
    build.entrant_sizes = entrant_sizes(build.db)
    build.size_problems = size_problems(build.db, build.entrant_sizes)
    reviewed = {o.event_id for o in build.curation.events}
    held = {event_id: why for event_id, why in build.size_problems.items() if event_id not in reviewed}
    build.db.executemany("UPDATE events SET held_out = ? WHERE event_id = ?", [(why, e) for e, why in held.items()])
    for event_id, why in held.items():
        build.log(f"  held out until reviewed (a row in events.csv): {event_id}: {why}")
    build.info["held_out"] = str(len(held))
    build.log(f"  {len(build.entrant_sizes)} events with entrants or matches; {len(build.size_problems)} counted events"
              f" whose sizes don't fit, {len(held)} of them new and held out")
