"""Build steps 7 and 8 (docs/build-plan.md §1): `player_aliases` and `player_merges`.

Aliases: one row per (alias, player), keeping the strongest kind when several give the same alias. In
order of strength:
- nickname: curation/player_aliases.csv, with its note;
- display_name: the player's current name, normalized whole ('Pink | Guichabou' -> 'pinkguichabou');
- without_tag: the same without the team tag ('guichabou'), when there is one;
- former_name: every other name the player was seen under, without its tag. Sources:
  - older Stats API names;
  - start.gg's tag at each event, from the standings and the entrant lists;
  - Challengermode usernames.
  shown_as gives the newest spelling, with the event's team prefix ('Kingdom | Godly').
A name made only of symbols normalizes to nothing and gets no alias.

Merges: curation/player_merges.csv, then the automatic merges of data/review/auto_merges.csv that no
curated row contradicts (curation.py).
- Their IDs are resolved as players are today: a negative ID through the platform ID it encodes.
- A merge that, once resolved, loops or makes two rejected records one person stops the build if it's
  curated, and is dropped if it's automatic.
- Chains (A -> B -> C) are collapsed, so every record points straight at its canonical player.

A curated row naming a player the cache has no record of is skipped and listed (build_info
'curated_rows_skipped'), not a reason to stop. Such a row may be a typo, or may name a real record with no
official results: hardymj's Challengermode record 632566, from the survey, is one. A merge with such a
player can't change any result.

A dev build writes only the rows whose players it has.
"""

import json

import sources
from curation import CurationError, chain_end, merge_conflict
from names import normalize, normalize_full

KINDS = {"nickname": 0, "display_name": 1, "without_tag": 2, "former_name": 3}  # strongest first


class Aliases:
    def __init__(self):
        self.rows = {}  # (alias, player ID) -> (strength, seen, kind, shown_as, source, note)

    def add(self, alias, pid, kind, shown_as, source, note=None, seen=(0, "")):
        """Keep the strongest kind for an alias, and among former names the newest spelling (by `seen`)."""
        if not alias:
            return
        old, new = self.rows.get((alias, pid)), (KINDS[kind], seen, kind, shown_as, source, note)
        if old is None or new[0] < old[0] or (new[0] == old[0] and seen > old[1]):
            self.rows[(alias, pid)] = new


def skip(build, where, reason):
    build.skipped.append(f"{where}: {reason}")
    build.log(f"  skipped {where}: {reason}")


def aliases_step(build):
    """Step 7."""
    db, players, aliases = build.db, build.players, Aliases()
    have = set(players.written)
    for pid, name, source in db.execute("SELECT player_id, name, source FROM players"):
        aliases.add(normalize_full(name), pid, "display_name", name, source)
        aliases.add(normalize(name), pid, "without_tag", name, source)
        for old, at in (players.names.get(pid) or {}).items():
            if old != name:
                aliases.add(normalize(old), pid, "former_name", old, "stats_api", seen=(0, at))
    for pid, tag, prefix, source, start, at in db.execute(
            "SELECT s.player_id, s.gamer_tag, s.prefix, s.source, e.start_time, s.fetched_at FROM standings s"
            " JOIN events e USING (event_id) WHERE s.player_id IS NOT NULL AND s.gamer_tag IS NOT NULL"):
        aliases.add(normalize(tag), pid, "former_name", f"{prefix} | {tag}" if prefix else tag, source, seen=(start, at))
    starts = dict(db.execute("SELECT event_id, start_time FROM events"))
    for response in build.reader.responses("startgg/Entrants", sources.ENTRANTS):
        if response.params["slug"] not in starts:
            continue
        for entrant in ((response.body["data"].get("event") or {}).get("entrants") or {}).get("nodes") or []:
            for part in entrant.get("participants") or []:
                sgg, tag = (part.get("player") or {}).get("id"), part.get("gamerTag")
                pid = players.current_id(-int(sgg)) if sgg is not None and tag else None
                if pid in have:
                    shown = f"{part['prefix']} | {tag}" if part.get("prefix") else tag
                    aliases.add(normalize(tag), pid, "former_name", shown, "startgg",
                                seen=(starts[response.params["slug"]], response.fetched_at))
    for a in build.curation.player_aliases:
        pid = players.current_id(a.player_id)
        if pid is None:
            skip(build, f"player_aliases.csv:{a.line}", f"the cache has no player {a.player_id}")
        elif pid in have:
            aliases.add(a.alias, pid, "nickname", a.shown_as, "curated", a.note)
    rows = [(alias, pid, kind, shown, source, note) for (alias, pid), (_, _, kind, shown, source, note)
            in sorted(aliases.rows.items()) if pid in have]
    db.executemany("INSERT INTO player_aliases (alias, player_id, kind, shown_as, source, note) VALUES (?, ?, ?, ?, ?, ?)",
                   rows)
    kinds = dict(db.execute("SELECT kind, COUNT(*) FROM player_aliases GROUP BY kind"))
    nameless = len(have - {pid for _, pid, *_ in rows})  # in Python: the alias index comes after the steps
    build.log(f"  {len(rows)} aliases: " + ", ".join(f"{kinds.get(k, 0)} {k}" for k in KINDS)
              + f"; {nameless} players have none (names made only of symbols)")


def merges_step(build):
    """Step 8."""
    db, players, cur = build.db, build.players, build.curation
    rejections = set()
    for pair in cur.rejections:
        resolved = {players.current_id(pid) for pid in pair}
        if None not in resolved and len(resolved) == 2:
            rejections.add(frozenset(resolved))
    merges, kept = {}, []
    for m in cur.merges:  # curated first, then the automatic ones
        where = f"{'player_merges.csv' if m.source == 'curated' else 'data/review/auto_merges.csv'}:{m.line}"
        pid, canonical = players.current_id(m.player_id), players.current_id(m.canonical_player_id)
        if pid is None or canonical is None:
            missing = m.player_id if pid is None else m.canonical_player_id
            skip(build, where, f"the cache has no player {missing}")
            continue
        if pid == canonical:
            skip(build, where, f"{m.player_id} and {m.canonical_player_id} are now the same player, {pid}")
            continue
        problem = f"{pid} is already merged into {merges[pid]}" if pid in merges else None
        if not problem:
            merges[pid] = canonical
            problem = merge_conflict(merges, rejections, pid)
            if problem:
                del merges[pid]
        if problem and m.source == "curated":
            raise CurationError([f"{where}: once IDs are resolved, {problem}"])
        if problem:
            skip(build, where, f"once IDs are resolved, {problem}")
            continue
        kept.append((pid, m))
    rows = [(pid, chain_end(merges, pid), m.source, m.note) for pid, m in kept]
    have = set(players.written)
    db.executemany("INSERT INTO player_merges (player_id, canonical_player_id, source, note) VALUES (?, ?, ?, ?)",
                   [r for r in rows if r[0] in have and r[1] in have])
    chained = sum(1 for pid, canonical, *_ in rows if canonical != merges[pid])
    build.info["curated_rows_skipped"] = json.dumps(build.skipped)
    build.log(f"  {len(rows)} merges ({sum(1 for r in rows if r[2] == 'auto')} automatic, {chained} through a chain)"
              f" into {len({r[1] for r in rows})} canonical players")
