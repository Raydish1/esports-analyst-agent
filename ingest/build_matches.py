"""Build step 6 (docs/build-plan.md §1): `matches` and `match_players`, from start.gg sets and
Challengermode matches.

start.gg
- Every set of every chosen event, from the events' set pages and, for the four events over start.gg's
  10,000-set cap, their pools' pages.
  - A pool's page names only its pool. It's tied to its event through the event's first page (its
    phases) and the phases' pool pages.
  - A set seen twice keeps its newest response.
- Not stored: a set with fewer than two entrants (a bye), and one with no score and no winner (never
  played, including start.gg's 'preview' placeholders).
- Scores are kept as reported: -1 for a DQ, NULL where none was reported. A set with a winner but no score
  counts as a win and a loss whose games are unknown (decided 2026-10-05). Every set also keeps
  start.gg's own winner (reported_winner_side), so check 9 can compare it with the scores.
- Side 1 is the first slot.
- An entrant's players come from the standings, otherwise from the event's entrant list (P1b). Players
  met only there get their rows here, through the player registry, and a Stats API placement where the
  cache has one (stage 3c).

Challengermode
- Every completed match in a series between two lineups. A cancelled match that was replayed isn't stored.
- Side 1 is lineup number 0.
- A match with no scores is a forfeit, stored as 0-0, so it's a no-contest (decided 2026-10-04).
  reported_winner_side is the lineup the match result places first.
- The players are the match lineups' members.

event_sources gets start.gg's own set total and its phases' states, and what the cached pages held for check 5
(completeness): every set or match seen, stored or not; entrants whose players are unknown (start.gg set entrants
in neither the standings nor an entrant list, Challengermode bracket lineups missing from the entrant list); and
Challengermode series between two lineups with no match. unplaced_entries gets the players who played at an
event without a placement there.
"""

import collections
import heapq
import json
from datetime import datetime

import sources
from build_placements import stats_api_placements

MATCH_COLUMNS = "match_id, event_id, side1_score, side2_score, reported_winner_side, start_time, source, fetched_at"


def score(slot):
    return ((((slot.get("standing") or {}).get("stats") or {}).get("score")) or {}).get("value")


def unix_time(text):
    """Seconds since 1970 from Challengermode's ISO time ('2026-08-30T17:07:52.880Z'), or None."""
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()) if text else None


def cm_series(tournament):
    """Every match series of a Challengermode tournament, from every kind of stage (as crawl.cm_series)."""
    for stage in tournament.get("stages") or []:
        for bracket in stage.get("brackets") or [{"rounds": stage.get("rounds") or []}]:
            for rnd in bracket.get("rounds") or []:
                yield from (s for s in rnd.get("matchSeries") or [] if s)
        for group in stage.get("groups") or []:
            yield from (s for s in group.get("matchSeries") or [] if s)


class Attributor:
    """Who played for an entrant: the standings' participants, else the event's entrant list (P1b)."""

    def __init__(self, build, starts):
        self.players, self.starts = build.players, starts
        self.standing = collections.defaultdict(list)
        for event_id, key, pid in build.db.execute("SELECT event_id, entrant_key, player_id FROM standings"
                                                   " WHERE source = 'startgg' AND player_id IS NOT NULL"):
            self.standing[(event_id, key)].append(pid)
        self.listed = {}  # (event ID, entrant key) -> ([(start.gg player ID, gamer tag)], fetched_at)
        for response in build.reader.responses("startgg/Entrants", sources.ENTRANTS):
            slug = response.params["slug"]
            if slug in starts:
                for entrant in ((response.body["data"].get("event") or {}).get("entrants") or {}).get("nodes") or []:
                    parts = [(str(p["player"]["id"]), p.get("gamerTag")) for p in entrant.get("participants") or []
                             if (p.get("player") or {}).get("id") is not None]
                    self.listed[(slug, str(entrant["id"]))] = (parts, response.fetched_at)
        self.from_lists = set()  # (event ID, player ID) attributed through an entrant list
        self.unknown = set()  # (event ID, entrant key) in neither

    def players_of(self, event_id, entrant_key):
        pids = self.standing.get((event_id, entrant_key))
        if pids is not None:
            return pids
        if (event_id, entrant_key) not in self.listed:
            self.unknown.add((event_id, entrant_key))
            return []
        parts, fetched_at = self.listed[(event_id, entrant_key)]
        pids = [self.players.resolve("startgg", pid, tag, (self.starts[event_id], fetched_at)) for pid, tag in parts]
        self.standing[(event_id, entrant_key)] = pids  # resolve each entrant once
        self.from_lists.update((event_id, pid) for pid in pids)
        return pids


def startgg_set_pages(reader, events, counts):
    """(event ID, fetched_at, body) for every set page of the chosen events, oldest first, and the events'
    first pages' totals: {event ID: (set total, phase states, fetched_at)}. A pool page that can't be tied to
    any event is counted: its sets would be missing."""
    firsts, phase_event, pool_event = {}, {}, {}
    event_pages = reader.entries("startgg/EventSets", sources.EVENT_SETS)
    for params, fetched_at, path in event_pages:  # every event's phases, so every pool page finds its event
        if params.get("page") == "1":
            event = reader.load(path)["data"].get("event") or {}
            phase_event.update((str(p["id"]), params["slug"]) for p in event.get("phases") or [])
            if params["slug"] in events:
                phases = [p for p in event.get("phases") or [] if not p.get("isExhibition")]
                firsts[params["slug"]] = (((event.get("sets") or {}).get("pageInfo") or {}).get("total"),
                                          ",".join(sorted({p.get("state") or "?" for p in phases})) or None, fetched_at)
    for response in reader.responses("startgg/PhasePools", sources.PHASE_POOLS):
        slug = phase_event.get(response.params["phaseId"])
        for pool in ((response.body["data"].get("phase") or {}).get("phaseGroups") or {}).get("nodes") or []:
            if slug:
                pool_event[str(pool["id"])] = slug
    pool_pages = reader.entries("startgg/PoolSets", sources.POOL_SETS)
    counts["start.gg pool pages tied to no event"] = sum(1 for e in pool_pages if e[0]["poolId"] not in pool_event)
    pages = heapq.merge(((at, path, params["slug"]) for params, at, path in event_pages if params["slug"] in events),
                        ((at, path, pool_event[params["poolId"]]) for params, at, path in pool_pages
                         if pool_event.get(params["poolId"]) in events))
    return ((slug, at, reader.load(path)) for at, path, slug in pages), firsts


def startgg_matches(build, starts, counts):
    """Store every played start.gg set of the chosen events. Returns the attributor."""
    db, who = build.db, Attributor(build, starts)
    stored, seen = set(), collections.defaultdict(set)
    pages, firsts = startgg_set_pages(build.reader, starts, counts)
    for event_id, fetched_at, body in pages:
        data = body["data"]
        matches, players, repeats = [], [], []
        for s in ((data.get("event") or data.get("phaseGroup") or {}).get("sets") or {}).get("nodes") or []:
            seen[event_id].add(str(s["id"]))
            slots = [x for x in sorted(s.get("slots") or [], key=lambda x: x.get("slotIndex") or 0) if x.get("entrant")]
            if len(slots) < 2:
                counts["start.gg byes"] += 1
                continue
            counts["start.gg sets with more than two entrants"] += len(slots) > 2
            scores, winner = [score(slots[0]), score(slots[1])], s.get("winnerId")
            if scores == [None, None] and winner is None:
                counts["start.gg sets never played"] += 1
                continue
            entrants = [slots[0]["entrant"]["id"], slots[1]["entrant"]["id"]]
            match_id = str(s["id"])
            if match_id in stored:
                repeats.append((match_id,))
            stored.add(match_id)
            matches.append((match_id, event_id, *scores, 1 + entrants.index(winner) if winner in entrants else None,
                            s.get("startedAt"), "startgg", fetched_at))
            sides = [who.players_of(event_id, str(e)) for e in entrants]
            both = set(sides[0]) & set(sides[1])
            counts["start.gg sets with a player on both sides"] += bool(both)
            players += [(match_id, side, pid) for side, pids in ((1, sides[0]), (2, sides[1])) for pid in pids
                        if not (side == 2 and pid in both)]
        db.executemany("DELETE FROM match_players WHERE match_id = ?", repeats)  # a newer response replaces a set
        db.executemany(f"INSERT OR REPLACE INTO matches ({MATCH_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", matches)
        db.executemany("INSERT OR IGNORE INTO match_players (match_id, side, player_id) VALUES (?, ?, ?)", players)
    db.executemany("UPDATE event_sources SET reported_sets = ?, state = COALESCE(?, state),"
                   " fetched_at = MAX(fetched_at, ?) WHERE event_id = ?",
                   [(total, states, at, event_id) for event_id, (total, states, at) in firsts.items()])
    unknown = collections.Counter(event_id for event_id, _ in who.unknown)
    db.executemany("UPDATE event_sources SET sets_seen = ?, entrants_unknown = ? WHERE event_id = ?",
                   [(len(ids), unknown[event_id], event_id) for event_id, ids in seen.items()])
    counts["start.gg entrants in neither standings nor an entrant list"] = len(who.unknown)
    return who


def cm_matches(build, starts, counts):
    """Store every completed Challengermode match of the chosen events."""
    db, usernames, rosters = build.db, {}, {}
    for response in build.reader.responses("challengermode/Roster", sources.ROSTER):
        lineups = [lineup for lineup in ((((response.body["data"].get("tournament") or {}).get("attendance") or {})
                                          .get("roster") or {}).get("lineups") or []) if lineup]
        rosters[response.params["id"]] = {lineup.get("id") for lineup in lineups}
        for lineup in lineups:
            for member in lineup.get("members") or []:
                user = member.get("user") or {}
                if user.get("id"):
                    usernames[user["id"].lower()] = user.get("username")
    found = {}  # event ID -> (matches seen, bracket lineups missing from the entrant list, series without a match)
    for response in build.reader.responses("challengermode/Bracket", sources.BRACKET):
        event_id = response.params["id"]
        if event_id not in starts:
            continue
        matches, players, seen, unlisted, empty = [], [], set(), set(), 0
        for series in cm_series(response.body["data"].get("tournament") or {}):
            seen.update(m["id"] for m in series.get("matches") or [] if m)
            lineups = [lineup for lineup in series.get("lineups") or [] if lineup]
            unlisted.update(lineup.get("id") for lineup in lineups if lineup.get("id") not in rosters.get(event_id, ()))
            if len(lineups) < 2:
                counts["Challengermode byes"] += 1
                continue
            empty += not series.get("matches")
            for match in series.get("matches") or []:
                if match.get("state") != "COMPLETED":
                    counts["Challengermode matches not completed (cancelled)"] += 1
                    continue
                results = {r.get("lineupNumber"): r for r in (match.get("results") or {}).get("lineupResults") or []}
                scores = [(results.get(n) or {}).get("score") for n in (0, 1)]
                if scores == [None, None]:
                    scores = [0, 0]  # a forfeit
                    counts["Challengermode forfeits (stored 0-0)"] += 1
                first = [n for n, r in results.items() if r.get("placement") == 1]
                matches.append((match["id"], event_id, *scores, first[0] + 1 if len(first) == 1 and first[0] in (0, 1)
                                else None, unix_time(series.get("startedAt")), "challengermode", response.fetched_at))
                for lineup in match.get("lineups") or []:
                    for member in lineup.get("members") or []:
                        uid = ((member.get("user") or {}).get("id") or "").lower()
                        if uid and lineup.get("number") in (0, 1):
                            pid = build.players.resolve("challengermode", uid, usernames.get(uid),
                                                        (starts[event_id], response.fetched_at))
                            players.append((match["id"], lineup["number"] + 1, pid))
        db.executemany(f"INSERT OR REPLACE INTO matches ({MATCH_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", matches)
        db.executemany("INSERT OR IGNORE INTO match_players (match_id, side, player_id) VALUES (?, ?, ?)", players)
        found[event_id] = (len(seen), len(unlisted), empty)  # responses come oldest first, so the newest stays
    db.executemany("UPDATE event_sources SET sets_seen = ?, entrants_unknown = ?, series_without_match = ?"
                   " WHERE event_id = ?", [(*figures, event_id) for event_id, figures in found.items()])


def step(build):
    db, counts = build.db, collections.Counter()
    starts = dict(db.execute("SELECT event_id, start_time FROM events"))
    who = startgg_matches(build, starts, counts)
    cm_matches(build, starts, counts)

    # Stage 3c: the Stats API's placements of players met only through an entrant list.
    unplaced = {k for k in who.from_lists
                if not db.execute("SELECT 1 FROM placements WHERE event_id = ? AND player_id = ?", k).fetchone()}
    found = stats_api_placements(build.reader, {event_id for event_id, _ in unplaced}) if unplaced else {}
    db.executemany("INSERT INTO placements (event_id, player_id, placement, source, fetched_at)"
                   " VALUES (?, ?, ?, 'stats_api', ?)",
                   [(e, p, place, at) for (e, p), (place, at) in sorted(found.items()) if (e, p) in unplaced])
    written = build.players.flush(db)
    db.execute("INSERT INTO unplaced_entries (event_id, player_id) SELECT DISTINCT m.event_id, mp.player_id"
               " FROM match_players mp JOIN matches m ON m.match_id = mp.match_id WHERE NOT EXISTS"
               " (SELECT 1 FROM placements p WHERE p.event_id = m.event_id AND p.player_id = mp.player_id)")

    by_source = dict(db.execute("SELECT source, COUNT(*) FROM matches GROUP BY source"))
    build.info["matches"] = str(sum(by_source.values()))
    build.info["match_counts"] = json.dumps(dict(sorted(counts.items())))  # what wasn't stored, for check 9
    build.log(f"  {sum(by_source.values())} matches (start.gg {by_source.get('startgg', 0)}, Challengermode"
              f" {by_source.get('challengermode', 0)}), {db.execute('SELECT COUNT(*) FROM match_players').fetchone()[0]}"
              f" match players; {len({p for _, p in who.from_lists})} players met only in an entrant list,"
              f" {sum(1 for k in found if k in unplaced)} of them placed by the Stats API; {written} player rows written")
    build.log("  " + "; ".join(f"{k}: {v}" for k, v in sorted(counts.items()) if v))
