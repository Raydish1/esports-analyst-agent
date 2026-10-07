"""The checks (docs/build-plan.md §3), run on a finished build to decide whether it can go live.

Each check returns outcomes, which become build_checks rows: one per subject that fails or is listed for review,
and one for the check as a whole (subject ''), whose detail says what was checked. The runner then:
- turns a failure that curation/check_exceptions.csv names into 'explained', with the row's note, and lists the
  exceptions that explain nothing (the problem was fixed, or the subject has a typo);
- settles each check's verdict, by its gate, in its '' row:
  - blocking: any unexplained failure fails it;
  - no_worse: it fails only if it has more unexplained failures than the live build had;
  - review: never fails; its items go to the review list (report.py).
A build passes when every check does. A dev build or a build of the past (--as-of) is checked the same way but
never goes live: it isn't compared with the live build's counts, and a dev build's regression check covers only
its events.

Subjects, as check_exceptions.csv names them:
  an event ID              winners, teams, completeness, match_presence, pro_series, entrant_sizes, regression,
                           event_totals, and the review checks
  '<player ID> <mode>'     pr_cross_check, e.g. '148006 1v1'
  '<event ID> <player ID>' stats_api_placements
  a match ID               no_contests
  integrity                '<table> -> <parent>', '<column> <value>', '<platform> player <ID>', 'standings',
                           'players.canonical_id'; and, listed for review, the curated rows skipped and the
                           exceptions that explain nothing ('<file>:<line>')
"""

import difflib
import json
import sqlite3
import time
from collections import Counter, defaultdict, namedtuple

import build_events
from build_events import players

Outcome = namedtuple("Outcome", "check_id gate subject outcome detail")  # a row of build_checks
BLOCKING, NO_WORSE, REVIEW = "blocking", "no_worse", "review"
MODES = {"1": "1v1", "2": "2v2"}  # ListEvents' gameMode
PR_LEFT_OUT = {"b009e9d1-e106-47e0-ffcc-08ddebf55676"}  # Brawlhalla Community Tournament #2, which PR doesn't count
PR_FIELDS = "top 8/top 32/gold/silver/bronze"
SPLIT_SHARE = 0.75  # a possible phase split: this share of the smaller event's players in the other's top finishers
SPLIT_NAMES = 0.9  # ... and names this alike (difflib's ratio), unless both are in one start.gg tournament
SPLIT_DAYS, SPLIT_DAYS_SAME_TOURNAMENT = 7, 31


def summary(check_id, gate, detail):
    """The row for a check as a whole; the runner settles its outcome."""
    return Outcome(check_id, gate, "", "pass", detail)


def fail(check_id, gate, subject, detail):
    return Outcome(check_id, gate, str(subject), "fail", detail)


def listed(check_id, subject, detail):
    return Outcome(check_id, REVIEW, str(subject), "listed", detail)


def ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def count(n, one, many):
    """e.g. count(1, 'series has', 'series have') -> '1 series has'."""
    return f"{n} {one if n == 1 else many}"


def events_named(db):
    """{event ID: 'tournament name event name (date)'} for details people read."""
    return {e: f"{t}{f' {n}' if n else ''} ({d})" for e, t, n, d in
            db.execute("SELECT event_id, tournament_name, event_name, start_date FROM v_events")}


# Check 1

def event_totals(build):
    """Check 1: the full ListEvents listings hold the same events as the per-year listings (the tie bug, schema
    proposal §3)."""
    full, by_year = defaultdict(set), defaultdict(set)
    for response in build.reader.responses("/event"):
        mode = MODES.get(response.params.get("gameMode"), response.params.get("gameMode"))
        found = {record["id"] for record in response.body.get("tournaments") or []}
        (by_year if "year" in response.params else full)[mode].update(found)
    out, parts = [], []
    for mode in sorted(set(full) | set(by_year)):
        parts.append(f"{mode}: {len(full[mode])} events in the full listing, {len(by_year[mode])} in the per-year ones")
        out += [fail("event_totals", BLOCKING, e, f"{mode}: in the full listing, not in a per-year one")
                for e in sorted(full[mode] - by_year[mode])]
        out += [fail("event_totals", BLOCKING, e, f"{mode}: in a per-year listing, not in the full one")
                for e in sorted(by_year[mode] - full[mode])]
    return [summary("event_totals", BLOCKING, "; ".join(parts) or "no listings in the cache")] + out


# Check 2

def winners(build):
    """Check 2: one 1st place per counted event: one player in 1v1, a pair sharing a team in 2v2, one crew in a crew
    battle. The Pro Series finals, whose placements come from the Stats API without entrants, need a team of at
    least two (check 11 checks the teams)."""
    rows = build.db.execute("""
        SELECT v.event_id, v.counts_as, v.format,
               (SELECT COUNT(*) FROM placements p WHERE p.event_id = v.event_id AND p.placement = 1),
               (SELECT COUNT(DISTINCT s.entrant_key) FROM standings s WHERE s.event_id = v.event_id AND s.placement = 1),
               (SELECT COUNT(DISTINCT p.team_id) FROM placements p WHERE p.event_id = v.event_id AND p.placement = 1),
               (SELECT COUNT(*) FROM placements p WHERE p.event_id = v.event_id AND p.placement = 1
                  AND p.team_id IS NULL),
               EXISTS (SELECT 1 FROM standings s WHERE s.event_id = v.event_id)
        FROM v_events v WHERE v.counts_as IS NOT NULL ORDER BY v.start_time, v.event_id""").fetchall()
    out = []
    for event_id, mode, fmt, first, entrants, teams, teamless, standings in rows:
        if first == 0:
            problem = "no 1st place"
        elif standings and entrants > 1:
            problem = f"{entrants} entrants placed 1st ({players(first)})"
        elif fmt == "crew_battle":
            problem = f"1st place has {players(first)}, not a crew" if first < 2 else None
        elif mode == "1v1":
            problem = f"{first} players placed 1st" if first != 1 else None
        else:
            problem = (f"1st place has {players(first)}" if first != 2 else
                       "the 1st-place pair has no team" if teamless else
                       "the 1st-place players are in different teams" if teams != 1 else None)
        if problem:
            out.append(fail("winners", BLOCKING, event_id, problem))
    return [summary("winners", BLOCKING, f"{len(rows)} counted events")] + out


# Check 3

def pr_cross_check(build):
    """Check 3: each ranked player's PR counts against their placements, counted by PR's own rule: official events
    in the Stats API's own mode, standard format only (crew battles and side formats left out), and not Community
    Tournament #2. Per Stats API record, before merges; the newest PR list counts. PR seems to leave out events
    outside a player's region for some players who moved (marker_bh1's PR counts only their MENA events), so a
    mismatch isn't always a missing placement."""
    if build.events is not None:
        return [summary("pr_cross_check", NO_WORSE, "not run: a dev build has only some events' placements")]
    db, pr, names = build.db, {}, {}
    for pid, mode, region, *figures in db.execute("SELECT player_id, mode, region, top8, top32, gold, silver, bronze"
                                                  " FROM pr_snapshots ORDER BY as_of"):
        pr[(pid, mode)] = (region, tuple(figure or 0 for figure in figures))
    counted = defaultdict(lambda: [0, 0, 0, 0, 0])
    for event_id, twos, pid, place in db.execute(
            "SELECT p.event_id, v.is_twos, p.player_id, p.placement FROM placements p JOIN v_events v USING (event_id)"
            " WHERE v.format = 'standard' AND v.is_official = 1 AND p.player_id > 0"):
        key = (pid, "2v2" if twos else "1v1")
        if event_id in PR_LEFT_OUT or key not in pr:
            continue
        tally = counted[key]
        tally[0] += place <= 8
        tally[1] += place <= 32
        if place <= 3:
            tally[1 + place] += 1
    out = []
    for (pid, mode), (region, figures) in sorted(pr.items()):
        mine = tuple(counted[(pid, mode)]) if (pid, mode) in counted else (0, 0, 0, 0, 0)
        if mine != figures:
            if pid not in names:
                names[pid] = (db.execute("SELECT name FROM players WHERE player_id = ?", (pid,)).fetchone() or ["?"])[0]
            out.append(fail("pr_cross_check", NO_WORSE, f"{pid} {mode}",
                            f"{names[pid]} ({region}): PR {PR_FIELDS} {'/'.join(map(str, figures))}, placements give"
                            f" {'/'.join(map(str, mine))}"))
    ranked = len({pid for pid, _ in pr})
    return [summary("pr_cross_check", NO_WORSE, f"{len(pr)} PR rows of {ranked} ranked players: {PR_FIELDS}")] + out


# Check 4

def teams(build):
    """Check 4: every 2v2 placement has a team."""
    rows = build.db.execute("SELECT v.event_id, COUNT(*), SUM(p.team_id IS NULL) FROM placements p"
                            " JOIN v_events v USING (event_id) WHERE v.mode = '2v2' GROUP BY v.event_id").fetchall()
    out = [fail("teams", NO_WORSE, e, f"{missing} of {n} 2v2 placements have no team")
           for e, n, missing in rows if missing]
    return [summary("teams", NO_WORSE, f"{sum(r[1] for r in rows)} 2v2 placements at {len(rows)} events")] + out


# Check 5

def completeness(build):
    """Check 5: what each platform reported is all in the build, as far as the cached pages show. start.gg: the sets
    on the pages are as many as its own total, and the standings hold its count of entrants. Challengermode: every
    lineup in a bracket is in the entrant list, and every series between two lineups has a match. Both: every
    entrant who played maps to players and has a placement. The Pro Series finals have no platform data."""
    rows = build.db.execute("""
        SELECT s.event_id, s.platform, s.reported_entrants, s.reported_sets, s.sets_seen, s.entrants_unknown,
               s.series_without_match,
               (SELECT COUNT(DISTINCT st.entrant_key) FROM standings st WHERE st.event_id = s.event_id),
               (SELECT COUNT(*) FROM unplaced_entries u WHERE u.event_id = s.event_id)
        FROM event_sources s JOIN events e USING (event_id)
        WHERE s.platform IN ('startgg', 'challengermode') ORDER BY e.start_time, s.event_id""").fetchall()
    out, totals = [], Counter()
    for event_id, platform, entrants, sets, seen, unknown, empty, placed, unplaced in rows:
        problems = []
        if platform == "startgg":
            totals.update(sgg=1, seen=seen or 0, sets=sets or 0, placed=placed, entrants=entrants or 0)
            if seen is None:
                problems.append("no set pages in the cache")
            elif sets is not None and seen != sets:
                problems.append(f"{seen} sets on the cached pages, but start.gg reports {sets}")
            if entrants is None:
                problems.append("no standings in the cache")
            elif placed != entrants:
                problems.append(f"{placed} entrants in the standings, but start.gg reports {entrants}")
            if unknown:
                problems.append(f"{count(unknown, 'set entrant is', 'set entrants are')} in neither the standings nor"
                                " an entrant list, so their sets lack players")
        else:
            totals.update(cm=1, matches=seen or 0)
            if seen is None:
                problems.append("no bracket in the cache")
            if entrants is None:
                problems.append("no entrant list in the cache")
            if unknown:
                problems.append(f"{count(unknown, 'lineup in the bracket is', 'lineups in the bracket are')} missing"
                                " from the entrant list")
            if empty:
                problems.append(f"{count(empty, 'series between two lineups has', 'series between two lineups have')}"
                                " no match")
        if unplaced:
            problems.append(count(unplaced, "player who played has no placement: their entrant isn't",
                                  "players who played have no placement: their entrants aren't") + " in the standings")
        if problems:
            out.append(fail("completeness", BLOCKING, event_id, "; ".join(problems)))
    detail = (f"start.gg: {totals['sgg']} events, {totals['seen']} sets on the cached pages of {totals['sets']}"
              f" reported, {totals['placed']} entrants in the standings of {totals['entrants']}; Challengermode:"
              f" {totals['cm']} events, {totals['matches']} matches in the brackets")
    return [summary("completeness", BLOCKING, detail)] + out


# Check 6

def match_presence(build):
    """Check 6: placed players with no match at their event, apart from those DQ'd. An entrant whose only sets were
    byes can't be told apart, since byes aren't stored. (Each event's placed players with a match are counted by
    subtraction, as in v_event_coverage; the players are compared one by one only where some lack a match.)"""
    db = build.db
    rows = db.execute("""
        SELECT e.event_id,
               (SELECT COUNT(*) FROM placements p WHERE p.event_id = e.event_id),
               (SELECT COUNT(DISTINCT mp.player_id) FROM matches m JOIN match_players mp ON mp.match_id = m.match_id
                 WHERE m.event_id = e.event_id),
               (SELECT COUNT(*) FROM unplaced_entries u WHERE u.event_id = e.event_id)
        FROM events e ORDER BY e.start_time, e.event_id""").fetchall()
    out, missing_total = [], 0
    for event_id, placed, played, unplaced in rows:
        if placed - (played - unplaced) <= 0:
            continue
        had = {pid for (pid,) in db.execute("SELECT mp.player_id FROM matches m JOIN match_players mp"
                                            " ON mp.match_id = m.match_id WHERE m.event_id = ?", (event_id,))}
        dqs = {pid for (pid,) in db.execute("SELECT player_id FROM standings WHERE event_id = ? AND is_disqualified = 1",
                                            (event_id,))}
        missing = {pid for (pid,) in db.execute("SELECT player_id FROM placements WHERE event_id = ?", (event_id,))} - had
        dq = len(missing & dqs)
        missing_total += len(missing) - dq
        if len(missing) > dq:
            out.append(fail("match_presence", NO_WORSE, event_id,
                            f"{len(missing) - dq} of {placed} placed players have no match"
                            + (f" ({dq} more were DQ'd)" if dq else "")))
    placements = sum(r[1] for r in rows)
    return [summary("match_presence", NO_WORSE, f"{placements} placements at {sum(1 for r in rows if r[1])} events;"
                                                f" {missing_total} placed players have no match")] + out


# Check 8

def stats_api_placements(build):
    """Check 8: every Stats API placement in the cache at a platform event equals the placement the standings give
    that person (any of their records, so a merge can settle a mismatch). Exact. They come from the single-player
    GetPlayerPlacements pages of stages 3, 3b and 3c; the Pro Series finals' placements are the Stats API's own,
    so they aren't compared."""
    db, found = build.db, {}
    for response in build.reader.responses("/player/placement"):
        ids = response.params.get("playerIds", "")
        if not ids or "," in ids:  # a pair's page places the pair
            continue
        for row in response.body.get("playerPlacements") or []:
            found[(row["tournament"]["id"], int(ids))] = row["placement"]  # the newest response wins
    platforms = dict(db.execute("SELECT event_id, platform FROM event_sources"))
    out, compared = [], Counter()
    for (event_id, pid), place in sorted(found.items()):
        platform = platforms.get(event_id)
        if platform not in ("startgg", "challengermode"):
            continue  # a Pro Series final, or an event outside a dev build
        compared[platform] += 1
        person = db.execute("SELECT canonical_id, name FROM players WHERE player_id = ?", (pid,)).fetchone()
        held = [p for (p,) in db.execute(
            "SELECT p.placement FROM players q JOIN placements p ON p.player_id = q.player_id AND p.event_id = ?"
            " WHERE q.canonical_id = ?", (event_id, person[0]))] if person else []
        if place not in held:
            who = f"{person[1]} ({pid})" if person else f"player {pid}, who isn't in the build,"
            ours = (f"the standings place them {' and '.join(map(ordinal, sorted(held)))}" if held else
                    "the standings don't place them")
            out.append(fail("stats_api_placements", BLOCKING, f"{event_id} {pid}",
                            f"the Stats API places {who} {ordinal(place)}; {ours}"))
    detail = (f"{sum(compared.values())} Stats API placements at platform events (start.gg {compared['startgg']},"
              f" Challengermode {compared['challengermode']})")
    return [summary("stats_api_placements", BLOCKING, detail)] + out


# Check 9

def no_contests(build):
    """Check 9: no-contests and odd scores, counted by platform. Listed as failures: a scored set whose winner by
    the scores isn't the platform's reported winner, a tie other than a 0-0 forfeit (it counts for nobody), and a
    0-0 on start.gg. Sets with a winner but no score are counted, not listed: they count as a win and a loss
    (decided 2026-10-05). So are DQs whose reported winner is the DQ'd side: a DQ counts for nobody either way."""
    db = build.db
    figures = {source: rest for source, *rest in db.execute(
        "SELECT source, COUNT(*), SUM(is_dq), SUM(dq_side = 0), SUM(side1_score = 0 AND side2_score = 0),"
        " SUM(is_scored = 0 AND is_dq = 0), SUM(is_dq = 1 AND dq_side IN (1, 2) AND reported_winner_side = dq_side)"
        " FROM matches GROUP BY source")}
    unstored = json.loads(build.info.get("match_counts") or "{}")
    parts = []
    if "startgg" in figures:
        n, dqs, double, _, unscored, dq_won = figures["startgg"]
        parts.append(f"start.gg: {n} sets, {dqs} DQs ({double} double), {unscored} with a winner but no score,"
                     f" {dq_won} DQs whose reported winner is the DQ'd side; not stored:"
                     f" {unstored.get('start.gg byes', '?')} byes, {unstored.get('start.gg sets never played', '?')}"
                     " sets never played")
    if "challengermode" in figures:
        n, _, _, nil, _, _ = figures["challengermode"]
        forfeits = unstored.get("Challengermode forfeits (stored 0-0)")
        parts.append(f"Challengermode: {n} matches, {nil} at 0-0"
                     + (f" ({forfeits} forfeits, {nil - forfeits} draws)" if forfeits is not None else "")
                     + f"; not stored: {unstored.get('Challengermode byes', '?')} byes,"
                       f" {unstored.get('Challengermode matches not completed (cancelled)', '?')} cancelled matches")
    out, names = [], events_named(db)
    for match_id, event_id, one, two, reported, winner, source in db.execute(
            "SELECT match_id, event_id, side1_score, side2_score, reported_winner_side, winner_side, source"
            " FROM matches WHERE (is_no_contest = 0 AND is_scored = 1 AND (winner_side IS NULL"
            "   OR (reported_winner_side IS NOT NULL AND winner_side <> reported_winner_side)))"
            " OR (source = 'startgg' AND side1_score = 0 AND side2_score = 0) ORDER BY event_id, match_id"):
        platform = "start.gg" if source == "startgg" else "Challengermode"
        if one == 0 and two == 0:
            why = "a 0-0 on start.gg, so it counts as a forfeit"
        elif winner is None:
            why = "a tie, so it counts for nobody" + (f", though {platform} reports side {reported} as the winner"
                                                      if reported else "")
        else:
            why = f"{platform} reports side {reported} as the winner, but the scores make it side {winner}, as counted"
        out.append(fail("no_contests", NO_WORSE, match_id, f"{names.get(event_id, event_id)}: {one}-{two}: {why}"))
    return [summary("no_contests", NO_WORSE, "; ".join(parts) or "no matches")] + out


# Check 11

def pro_series(build):
    """Check 11: the Pro Series finals' placements (from the Stats API) form complete teams: the 1st place's
    players are a team, every place below holds whole teams of that size, and no place is skipped."""
    db, out, found = build.db, [], []
    for (event_id,) in db.execute("SELECT event_id FROM event_sources WHERE platform = 'stats_api' ORDER BY event_id"):
        places = dict(db.execute("SELECT placement, COUNT(*) FROM placements WHERE event_id = ? GROUP BY placement",
                                 (event_id,)))
        size, problems = places.get(1, 0), []
        if not places:
            problems.append("no placements")
        elif size < 2:
            problems.append(f"1st place has {players(size)}, not a team")
        else:
            skipped = [p for p in range(1, max(places) + 1) if p not in places]
            uneven = [p for p in sorted(places) if places[p] % size]
            if skipped:
                problems.append(f"no team placed {', '.join(map(ordinal, skipped))}")
            if uneven:
                problems.append(", ".join(f"{ordinal(p)} has {players(places[p])}" for p in uneven)
                                + f", not whole teams of {size}")
        if problems:
            out.append(fail("pro_series", BLOCKING, event_id, "; ".join(problems)))
        else:
            found.append(f"{event_id} {sum(places.values()) // size} teams of {size}")
    return [summary("pro_series", BLOCKING, "; ".join(found) or "no Pro Series finals")] + out


# New checks

def integrity(build):
    """Foreign keys, one player record per platform ID, every platform player looked up, standings rows that name a
    player, and canonical IDs that are canonical. The curated rows the build skipped, naming a player the cache has
    no record of, are listed for review: they're skipped rather than stopping the build (decided 2026-10-06)."""
    db, out = build.db, []
    broken = Counter((table, parent) for table, _, parent, _ in db.execute("PRAGMA foreign_key_check"))
    out += [fail("integrity", BLOCKING, f"{table} -> {parent}", f"{n} {table} rows point at a missing {parent} row")
            for (table, parent), n in sorted(broken.items())]
    for column in ("sgg_player_id", "cm_player_id"):
        out += [fail("integrity", BLOCKING, f"{column} {value}", f"{n} player records have it")
                for value, n in db.execute(f"SELECT {column}, COUNT(*) FROM players WHERE {column} IS NOT NULL"
                                           f" GROUP BY {column} HAVING COUNT(*) > 1")]
    unasked = sorted(build.players.unasked) if build.players else []
    out += [fail("integrity", BLOCKING, f"{platform} player {platform_id}",
                 "no Stats API lookup asked about this platform player") for platform, platform_id in unasked]
    nameless = db.execute("SELECT COUNT(*) FROM standings WHERE player_id IS NULL").fetchone()[0]
    if nameless:
        out.append(fail("integrity", BLOCKING, "standings",
                        f"{nameless} standings rows have no player, so they have no placement"))
    astray = db.execute("SELECT COUNT(*) FROM players p LEFT JOIN players c ON c.player_id = p.canonical_id"
                        " WHERE c.player_id IS NULL OR c.canonical_id <> c.player_id").fetchone()[0]
    if astray:
        out.append(fail("integrity", BLOCKING, "players.canonical_id",
                        f"{astray} players' canonical record is missing or is itself merged"))
    out += [listed("integrity", s.where, f"!! curated row skipped: {s.reason}") for s in build.skipped]
    return [summary("integrity", BLOCKING, "foreign keys, platform IDs, lookups, canonical IDs and curated rows")] + out


def entrant_sizes(build):
    """Decision 3: entrant sizes fit each counted event's mode and format (build_events.fitting_sizes). A reviewed
    event, one with a row in events.csv, that doesn't fit fails. A new one is held out of the counts until reviewed
    (the hold-outs step) and listed."""
    problems = build.size_problems
    if problems is None:
        problems = build_events.size_problems(build.db)
    reviewed = {o.event_id for o in build.curation.events} if build.curation else set()
    out = [fail("entrant_sizes", BLOCKING, e, why) if e in reviewed else
           listed("entrant_sizes", e, f"held out of the counts until reviewed: {why}") for e, why in problems.items()]
    counted = build.db.execute("SELECT COUNT(*) FROM v_events WHERE format IN ('standard', 'crew_battle')").fetchone()[0]
    return [summary("entrant_sizes", BLOCKING, f"{counted} events in a counted format")] + out


def counts_by_event(db, events=None):
    """{event ID: (placements, matches)}, for the regression check."""
    found = {e: [0, 0] for (e,) in db.execute("SELECT event_id FROM events")}
    for i, table in enumerate(("placements", "matches")):
        for event_id, n in db.execute(f"SELECT event_id, COUNT(*) FROM {table} GROUP BY event_id"):
            found.setdefault(event_id, [0, 0])[i] = n
    return {e: tuple(n) for e, n in found.items() if events is None or e in events}


def regression(build):
    """Compared with the live build: no event is lost, and no event's placements or matches decreased. A dev build
    is compared on its own events; a build of the past isn't compared."""
    if build.live is None:
        return [summary("regression", BLOCKING, f"not compared: {build.live_reason}")]
    try:
        live = sqlite3.connect(build.live.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            before = counts_by_event(live, build.events)
        finally:
            live.close()
    except sqlite3.Error as e:
        return [summary("regression", BLOCKING, f"not compared: the live build can't be read ({e})")]
    now, out = counts_by_event(build.db, build.events), []
    for event_id, (placements, matches) in sorted(before.items()):
        if event_id not in now:
            out.append(fail("regression", BLOCKING, event_id, "in the live build, not in this one"))
            continue
        fewer = [f"{what} {old} -> {new}" for what, old, new in
                 (("placements", placements, now[event_id][0]), ("matches", matches, now[event_id][1])) if new < old]
        if fewer:
            out.append(fail("regression", BLOCKING, event_id, f"fewer than in the live build: {', '.join(fewer)}"))
    return [summary("regression", BLOCKING, f"{len(before)} events compared with the live build {build.live.stem}")] + out


# Review checks: what a person should look at, never a reason to stop

def rules_matched(db):
    """{event ID: [(priority, pattern, format)]}, the format rules each event's name matches, strongest first."""
    found = defaultdict(list)
    for event_id, pattern, fmt, priority in db.execute(
            "SELECT e.event_id, r.pattern, r.format, r.priority FROM events e JOIN format_rules r"
            " ON lower(e.tournament_name || ' ' || COALESCE(e.event_name, '')) LIKE r.pattern"):
        found[event_id].append((priority, pattern, fmt))
    return {e: sorted(rules) for e, rules in found.items()}


def sizes_text(sizes):
    """e.g. '284 entrants of 1 player', or 'entrants of 1 player (603) and 2 players (1)'."""
    if not sizes or not sizes[0]:
        return "no standings"
    entrants = sizes[0]
    if len(entrants) == 1:
        (n, k), = entrants.items()
        return f"{k} entrants of {players(n)}"
    return "entrants of " + " and ".join(f"{players(n)} ({k})" for n, k in sorted(entrants.items()))


def new_events(build):
    """Review: every event without a row in events.csv, with its detected mode and format and its entrants' sizes.
    A row in events.csv, with or without overrides, records that the detection was checked (docs/build-plan.md §5)."""
    db = build.db
    reviewed = {o.event_id for o in build.curation.events} if build.curation else set()
    sizes = build.entrant_sizes if build.entrant_sizes is not None else build_events.entrant_sizes(db)
    rules, names, out = rules_matched(db), events_named(db), []
    rows = db.execute("SELECT event_id, mode, format, host FROM v_events ORDER BY start_time, event_id").fetchall()
    for event_id, mode, fmt, host in rows:
        if event_id in reviewed:
            continue
        how = (f"the rule '{rules[event_id][0][1]}'" if fmt != "standard" and rules.get(event_id) else "no format rule")
        platform = "the Stats API" if event_id.startswith("series/") else {"SGG": "start.gg", "CM": "Challengermode"}[host]
        out.append(listed("new_events", event_id, f"{names[event_id]}, {platform}: detected {mode}, "
                                                  f"{fmt.replace('_', ' ')} ({how}); {sizes_text(sizes.get(event_id))}"))
    return [summary("new_events", REVIEW, f"{len(out)} of {len(rows)} events have no row in events.csv")] + out


def format_rule_ties(build):
    """Review: an event whose name matches format rules of different formats at the same, lowest priority (step 2's
    note). The tie goes to the first pattern, which may not be what's meant."""
    db = build.db
    reviewed = {o.event_id for o in build.curation.events} if build.curation else set()
    out = []
    for event_id, rules in sorted(rules_matched(db).items()):
        top = [r for r in rules if r[0] == rules[0][0]]
        if event_id not in reviewed and len({fmt for _, _, fmt in top}) > 1:
            out.append(listed("format_rule_ties", event_id, f"matched by {', '.join(f'{p!r} ({f})' for _, p, f in top)}"
                                                            f" at priority {top[0][0]}; {top[0][1]!r} wins"))
    return [summary("format_rule_ties", REVIEW, f"{db.execute('SELECT COUNT(*) FROM format_rules').fetchone()[0]}"
                                                " format rules")] + out


def phase_splits(build):
    """Review: two events that may be phases of one competition (docs/build-plan.md §5): in one mode, either in one
    start.gg tournament within SPLIT_DAYS_SAME_TOURNAMENT days, or with near-identical names within SPLIT_DAYS
    days, where at least SPLIT_SHARE of the smaller event's players placed in the other's top 2n (n: the smaller
    event's players). Leaves out pairs already in one competition, and pairs whose events both have a row in
    events.csv (reviewed)."""
    db = build.db
    reviewed = {o.event_id for o in build.curation.events} if build.curation else set()
    events = db.execute("SELECT event_id, lower(tournament_name || ' ' || COALESCE(event_name, '')), start_time, mode,"
                        " sgg_tournament_slug, competition_id FROM v_events WHERE status IS NULL"
                        " ORDER BY start_time, event_id").fetchall()
    names, placed, out = events_named(db), {}, []

    def places(event_id):
        if event_id not in placed:
            placed[event_id] = {}
            for pid, place in db.execute("SELECT q.canonical_id, p.placement FROM placements p JOIN players q"
                                         " USING (player_id) WHERE p.event_id = ?", (event_id,)):
                placed[event_id][pid] = min(place, placed[event_id].get(pid, place))
        return placed[event_id]

    for i, (a, a_name, a_start, mode, a_slug, a_comp) in enumerate(events):
        for b, b_name, b_start, b_mode, b_slug, b_comp in events[i + 1:]:
            if b_start - a_start > SPLIT_DAYS_SAME_TOURNAMENT * 86400:
                break
            same = a_slug is not None and a_slug == b_slug
            if (b_mode != mode or (a in reviewed and b in reviewed) or (a_comp and a_comp == b_comp)
                    or not (same or (b_start - a_start <= SPLIT_DAYS * 86400
                                     and difflib.SequenceMatcher(None, a_name, b_name).ratio() >= SPLIT_NAMES))):
                continue
            larger, smaller = sorted((a, b), key=lambda e: -len(places(e)))
            big, small = places(larger), places(smaller)
            if not small or not big:
                continue
            top = sum(1 for pid in small if big.get(pid, 10 ** 9) <= 2 * len(small))
            if top >= SPLIT_SHARE * len(small):
                out.append(listed("phase_splits", f"{larger} {smaller}",
                                  f"{names[smaller]} may be a phase of {names[larger]}: {top} of its {len(small)}"
                                  f" players placed in the other's top {2 * len(small)}"))
    return [summary("phase_splits", REVIEW, f"{len(events)} events compared in pairs")] + out


CHECKS = [event_totals, winners, pr_cross_check, teams, completeness, match_presence, stats_api_placements, no_contests,
          pro_series, integrity, entrant_sizes, regression, new_events, format_rule_ties, phase_splits]


# The runner

def explain(outcomes, exceptions):
    """Turn each failure an exception names into 'explained'. Returns (outcomes, exceptions that explain nothing)."""
    notes = {(e.check, e.subject): e for e in exceptions}
    used, result = set(), []
    for o in outcomes:
        e = notes.get((o.check_id, o.subject)) if o.subject and o.outcome == "fail" else None
        if e:
            used.add((e.check, e.subject))
            o = o._replace(outcome="explained", detail=f"{o.detail}; check_exceptions.csv:{e.line}: {e.note or 'no note'}")
        result.append(o)
    return result, [e for e in exceptions if (e.check, e.subject) not in used]


def baseline(build):
    """{check ID: unexplained 'no worse' failures} in the live build, for the checks it ran; None when this build
    isn't compared with it (no live build, a dev build, a build of the past)."""
    if build.live is None or build.events is not None:
        return None
    try:
        live = sqlite3.connect(build.live.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            ran = {c for (c,) in live.execute("SELECT DISTINCT check_id FROM build_checks")}
            failed = dict(live.execute("SELECT check_id, COUNT(*) FROM build_checks WHERE gate = 'no_worse'"
                                       " AND subject <> '' AND outcome = 'fail' GROUP BY check_id"))
        finally:
            live.close()
    except sqlite3.Error:
        return None
    return {c: failed.get(c, 0) for c in ran}


def settle(outcomes, before):
    """Each check's '' row gets its verdict under its gate and a tally of its rows."""
    order, rows, heads = [], defaultdict(list), {}
    for o in outcomes:
        if o.check_id not in order:
            order.append(o.check_id)
        if o.subject == "":
            heads.setdefault(o.check_id, o)
        else:
            rows[o.check_id].append(o)
    settled = []
    for check_id in order:
        items = rows[check_id]
        head = heads.get(check_id) or Outcome(check_id, items[0].gate, "", "pass", "")
        tally = Counter(o.outcome for o in items)
        notes = [f"{tally[k]} {label}" for k, label in (("fail", "failed"), ("explained", "explained"),
                                                         ("listed", "listed for review")) if tally[k]]
        verdict = "pass"
        if head.gate == BLOCKING:
            verdict = "fail" if any(o.outcome == "fail" and o.gate == BLOCKING for o in items) else "pass"
        elif head.gate == NO_WORSE:
            now = sum(1 for o in items if o.outcome == "fail" and o.gate == NO_WORSE)
            if before is None:
                notes.append("not compared with the live build")
            elif check_id not in before:
                notes.append("the live build didn't run this check")
            else:
                notes.append(f"the live build had {before[check_id]}")
                verdict = "fail" if now > before[check_id] else "pass"
        detail = "; ".join(part for part in [head.detail] + notes if part)
        settled.append(head._replace(outcome=verdict, detail=detail))
        settled += items
    return settled


def run(build, checks=None, log=print):
    """Run the checks, apply check_exceptions.csv, and settle each check's verdict. Returns the outcomes."""
    outcomes = []
    for check in CHECKS if checks is None else checks:
        begun = time.monotonic()
        outcomes += check(build)
        if time.monotonic() - begun > 1:
            log(f"    {check.__name__}: {time.monotonic() - begun:.1f} s")
    outcomes, unused = explain(outcomes, build.curation.check_exceptions if build.curation else [])
    build.unused_exceptions = unused if build.events is None else []  # a dev build lacks most of the subjects
    outcomes += [listed("integrity", f"check_exceptions.csv:{e.line}",
                        f"{e.check} for {e.subject}: no such failure in this build, so the row explains nothing"
                        " (fixed since, or a typo in the subject)") for e in build.unused_exceptions]
    return settle(outcomes, baseline(build))


def passed(outcomes):
    """A build passes when every check's verdict ('' row) is a pass."""
    return not any(o.subject == "" and o.outcome == "fail" for o in outcomes)
