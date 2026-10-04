"""The Stats API crawl (docs/schema-proposal.md §3), run one stage at a time.

    python ingest/crawl.py status                  progress of every stage
    python ingest/crawl.py events                  stage 0: every official event
    python ingest/crawl.py pr                      stage 1: the PR lists, which seed the players
    python ingest/crawl.py profiles                stage 2: profiles of known players
    python ingest/crawl.py histories [--sample N]  stage 3: official placements and teammates
    python ingest/crawl.py teams                   stage 4: official placements of each 2v2 pair
    python ingest/crawl.py matches                 stage 6: matches per player and event

A stage first plans its tasks from what earlier stages found, then works through them.
Re-running the same command picks up where it stopped: finished tasks are skipped, and
requests already made come back from the cache. Ctrl+C stops after the current task.
Stage 3 finds new players as teammates and stage 6 as opponents; re-running stages 2-4
and 6 crawls them, and that loop is stage 5, discovery. Each run also writes a log to
data/logs/crawl-<stage>.log.
"""

import argparse
import hashlib
import logging
import random
import sys
import time
from datetime import datetime, timezone

from cache import ROOT
from statsapi import ApiError, StatsApi
from tasks import MAX_ATTEMPTS, RunLock, StopFlag, TaskQueue, connect, pid_alive

PAGE_SIZE = 50  # the maximum for ListEvents, GetPlayerPlacements and GetPlayerTeammates
PR_PAGE_SIZE = 100
PROFILE_BATCH = 100  # player IDs per ListPlayers request
MODES = {1: "1v1", 2: "2v2"}
REGIONS = ["NA", "EU", "SA", "SEA", "MENA"]  # ListPr's regions with rows
FIRST_YEAR = 2017  # the API has nothing earlier
SAMPLE_SEED = 20261004  # fixes which players `histories --sample` picks
LOG_DIR = ROOT / "data" / "logs"

CRAWL_SCHEMA = """
-- What the crawl has learned so far, used to plan later stages. The builder reads the cache, not these.
CREATE TABLE IF NOT EXISTS crawl_events (       -- stage 0
  event_id    TEXT PRIMARY KEY,
  mode        INTEGER NOT NULL,
  host        TEXT,
  start_time  INTEGER
);
CREATE TABLE IF NOT EXISTS crawl_players (
  player_id        INTEGER PRIMARY KEY,
  found_by         TEXT NOT NULL,                -- 'pr' | 'teammate' | 'opponent'
  profile          INTEGER NOT NULL DEFAULT 0,   -- 0 to do, 1 planned, 2 fetched, 3 unknown to the API
  history_planned  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS crawl_pairs (        -- 2v2 partners, smaller ID first
  player1_id  INTEGER NOT NULL,
  player2_id  INTEGER NOT NULL,
  planned     INTEGER NOT NULL DEFAULT 0,
  events      INTEGER,                          -- official events together, once stage 4 has run
  PRIMARY KEY (player1_id, player2_id)
);
CREATE TABLE IF NOT EXISTS crawl_entries (      -- official events each player entered
  player_id  INTEGER NOT NULL,
  event_id   TEXT NOT NULL,
  mode       INTEGER NOT NULL,
  planned    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (player_id, event_id)
);
"""


def walk_pages(api, endpoint, params, rows_key, row_id, row_time, page_size, log=print):
    """Every row of a listing paged by timestamp tokens, working around the tie bug.

    The next page starts strictly before the token, so rows sharing the boundary timestamp
    can be skipped. Asking for the last timestamp + 1 instead re-reads the boundary, and
    de-duplicating by ID keeps each row once. A short page is the last one. If a full page
    brings nothing new (more ties than a page holds), fall back to the server's token.
    """
    rows, token = {}, None
    while True:
        body = api.get(endpoint, {**params, "maxResults": page_size, "nextToken": token})
        page = body.get(rows_key) or []
        new = [r for r in page if row_id(r) not in rows]
        rows.update((row_id(r), r) for r in new)
        if len(page) < page_size:
            return list(rows.values())
        if new:
            token = str(row_time(page[-1]) + 1)
        elif body.get("nextToken") and body["nextToken"] != token:
            log(f"  {endpoint}: a full page of known rows at {row_time(page[-1])}; using the server's token")
            token = body["nextToken"]
        else:
            return list(rows.values())


def list_events(api, mode, year=None, log=print):
    """Every official event in one mode, and optionally one year."""
    return walk_pages(api, "/event", {"gameMode": mode, "isOfficial": True, "year": year},
                      "tournaments", lambda e: e["id"], lambda e: e["startTime"], PAGE_SIZE, log)


def placement_pages(api, player_ids, mode, log):
    return walk_pages(api, "/player/placement", {"playerIds": player_ids, "gameMode": mode, "isOfficial": True},
                      "playerPlacements", lambda r: r["tournament"]["id"], lambda r: r["tournament"]["startTime"],
                      PAGE_SIZE, log)


# Stage 0: events

def plan_events(db, queue, args):
    for mode in MODES:
        queue.add("events", "event_list", f"events:{mode}", {"mode": mode})
        for year in range(FIRST_YEAR, datetime.now(timezone.utc).year + 1):
            queue.add("events", "event_list", f"events:{mode}:{year}", {"mode": mode, "year": year})


def fetch_event_list(api, p, log):
    return list_events(api, p["mode"], p.get("year"), log)


def apply_event_list(db, p, events):
    if p.get("year") is None:
        db.executemany("INSERT OR REPLACE INTO crawl_events (event_id, mode, host, start_time) VALUES (?, ?, ?, ?)",
                       [(e["id"], p["mode"], e.get("host"), e["startTime"]) for e in events])
    return []


def check_events(db, api, log):
    """The full listing and the per-year listings must hold the same events (the tie bug check)."""
    ok = True
    for mode, label in MODES.items():
        full = {e["id"] for e in list_events(api, mode, log=log)}  # all from the cache by now
        by_year = set()
        for year in range(FIRST_YEAR, datetime.now(timezone.utc).year + 1):
            by_year |= {e["id"] for e in list_events(api, mode, year, log=log)}
        if full == by_year:
            log(f"{label}: {len(full)} official events; the per-year crawls agree")
        else:
            ok = False
            log(f"{label}: MISMATCH, {len(full)} in the full crawl and {len(by_year)} in the per-year crawls")
    return ok


# Stage 1: PR lists

def plan_pr(db, queue, args):
    for mode in MODES:
        for region in REGIONS:
            queue.add("pr", "pr_page", f"pr:{mode}:{region}:1", {"mode": mode, "region": region, "page": 1})


def fetch_pr_page(api, p, log):
    return api.get("/pr", {"gameMode": p["mode"], "region": p["region"], "page": p["page"],
                           "maxResults": PR_PAGE_SIZE})


def apply_pr_page(db, p, body):
    db.executemany("INSERT OR IGNORE INTO crawl_players (player_id, found_by) VALUES (?, 'pr')",
                   [(r["playerId"],) for r in body.get("prPlayers") or []])
    if p["page"] != 1:
        return []
    return [("pr", "pr_page", f"pr:{p['mode']}:{p['region']}:{page}", {**p, "page": page})
            for page in range(2, (body.get("totalPages") or 1) + 1)]


# Stage 2: profiles

def profile_task(ids):
    digest = hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()[:10]
    return "profiles", "profile_batch", f"profiles:{ids[0]}-{ids[-1]}:{digest}", {"player_ids": ids}


def plan_profiles(db, queue, args):
    ids = [r[0] for r in db.execute("SELECT player_id FROM crawl_players WHERE profile = 0 ORDER BY player_id")]
    for i in range(0, len(ids), PROFILE_BATCH):
        queue.add(*profile_task(ids[i:i + PROFILE_BATCH]))
    db.execute("UPDATE crawl_players SET profile = 1 WHERE profile = 0")


def fetch_profile_batch(api, p, log):
    try:
        return api.get("/players", {"playerIds": p["player_ids"]})
    except ApiError as e:
        if e.status and 400 <= e.status < 500 and e.status != 404 and len(p["player_ids"]) > 1:
            return {"split": True}  # too many IDs for one request: try each half
        raise


def apply_profile_batch(db, p, body):
    ids = p["player_ids"]
    if body.get("split"):
        return [profile_task(ids[:len(ids) // 2]), profile_task(ids[len(ids) // 2:])]
    found = {pl["playerId"] for pl in body.get("players") or [] if pl}
    db.executemany("UPDATE crawl_players SET profile = ? WHERE player_id = ?",
                   [(2 if i in found else 3, i) for i in ids])
    return []


# Stage 3: histories

def plan_histories(db, queue, args):
    ids = [r[0] for r in db.execute("SELECT player_id FROM crawl_players WHERE history_planned = 0 ORDER BY player_id")]
    if getattr(args, "sample", None):
        seeds = [r[0] for r in db.execute("SELECT player_id FROM crawl_players WHERE found_by = 'pr' ORDER BY player_id")]
        chosen = set(random.Random(SAMPLE_SEED).sample(seeds, min(args.sample, len(seeds))))
        ids = [i for i in ids if i in chosen]
    for pid in ids:
        for mode in MODES:
            queue.add("histories", "placements", f"placements:{pid}:{mode}", {"player_id": pid, "mode": mode})
        queue.add("histories", "teammates", f"teammates:{pid}", {"player_id": pid})
    db.executemany("UPDATE crawl_players SET history_planned = 1 WHERE player_id = ?", [(i,) for i in ids])


def fetch_placements(api, p, log):
    return placement_pages(api, p["player_id"], p["mode"], log)


def apply_placements(db, p, rows):
    db.executemany("INSERT OR IGNORE INTO crawl_entries (player_id, event_id, mode) VALUES (?, ?, ?)",
                   [(p["player_id"], r["tournament"]["id"], p["mode"]) for r in rows])
    return []


def fetch_teammates(api, p, log):
    return walk_pages(api, "/player/teammate", {"playerId": p["player_id"], "isOfficial": True},
                      "playerTeammates", lambda r: r["player"]["playerId"], lambda r: r["lastTeamedDate"],
                      PAGE_SIZE, log)


def apply_teammates(db, p, rows):
    me, partners = p["player_id"], [r["player"]["playerId"] for r in rows]
    db.executemany("INSERT OR IGNORE INTO crawl_players (player_id, found_by) VALUES (?, 'teammate')",
                   [(q,) for q in partners])
    db.executemany("INSERT OR IGNORE INTO crawl_pairs (player1_id, player2_id) VALUES (?, ?)",
                   [(min(me, q), max(me, q)) for q in partners if q != me])
    return []


# Stage 4: teams

def plan_teams(db, queue, args):
    for a, b in db.execute("SELECT player1_id, player2_id FROM crawl_pairs WHERE planned = 0").fetchall():
        queue.add("teams", "team", f"team:{a}:{b}", {"player_ids": [a, b]})
    db.execute("UPDATE crawl_pairs SET planned = 1 WHERE planned = 0")


def fetch_team(api, p, log):
    return placement_pages(api, p["player_ids"], 2, log)


def apply_team(db, p, rows):
    db.execute("UPDATE crawl_pairs SET events = ? WHERE player1_id = ? AND player2_id = ?",
               (len(rows), *p["player_ids"]))
    return []


# Stage 6: matches (the Pro Series finals' 'series/...' IDs are rejected by GetPlayerMatches)

def plan_matches(db, queue, args):
    for pid, eid in db.execute("SELECT player_id, event_id FROM crawl_entries"
                               " WHERE planned = 0 AND event_id NOT LIKE 'series/%'").fetchall():
        queue.add("matches", "matches", f"matches:{pid}:{eid}", {"player_id": pid, "event_id": eid})
    db.execute("UPDATE crawl_entries SET planned = 1 WHERE planned = 0 AND event_id NOT LIKE 'series/%'")


def fetch_matches(api, p, log):
    return api.get("/player/match", {"tournamentId": p["event_id"], "playerIds": p["player_id"]})


def apply_matches(db, p, body):
    opponents = {o["playerId"] for m in body.get("playerMatches") or [] for o in m.get("opponent") or [] if o}
    db.executemany("INSERT OR IGNORE INTO crawl_players (player_id, found_by) VALUES (?, 'opponent')",
                   [(o,) for o in opponents])
    return []


STAGES = {  # name: (number, plan, check run once the stage has finished)
    "events": (0, plan_events, check_events),
    "pr": (1, plan_pr, None),
    "profiles": (2, plan_profiles, None),
    "histories": (3, plan_histories, None),
    "teams": (4, plan_teams, None),
    "matches": (6, plan_matches, None),
}
KINDS = {
    "event_list": (fetch_event_list, apply_event_list),
    "pr_page": (fetch_pr_page, apply_pr_page),
    "profile_batch": (fetch_profile_batch, apply_profile_batch),
    "placements": (fetch_placements, apply_placements),
    "teammates": (fetch_teammates, apply_teammates),
    "team": (fetch_team, apply_team),
    "matches": (fetch_matches, apply_matches),
}
UNPLANNED = {  # work a stage would add on its next run, as players and pairs get found
    "profiles": "SELECT COUNT(*) FROM crawl_players WHERE profile = 0",
    "histories": "SELECT COUNT(*) FROM crawl_players WHERE history_planned = 0",
    "teams": "SELECT COUNT(*) FROM crawl_pairs WHERE planned = 0",
    "matches": "SELECT COUNT(*) FROM crawl_entries WHERE planned = 0 AND event_id NOT LIKE 'series/%'",
}


def remaining(db, stage):
    return db.execute("SELECT COUNT(*) FROM tasks WHERE stage = ? AND (status IN ('pending', 'running')"
                      " OR (status = 'failed' AND attempts < ?))", (stage, MAX_ATTEMPTS)).fetchone()[0]


def run_stage(db, api, stage, args, log, stop, on_task=None):
    """Plan a stage, then run its tasks until none are left or a stop is requested.

    Returns 'finished' or 'stopped'. on_task, if given, is called after each task; the CLI
    uses it for the run's heartbeat, and tests to stop part-way.
    """
    queue = TaskQueue(db)
    interrupted, retried = queue.requeue(stage)
    if interrupted or retried:
        log(f"Pending again: {interrupted} task(s) an interrupted run left running, {retried} failed task(s) to retry")
    with db:
        STAGES[stage][1](db, queue, args)
    total = remaining(db, stage)
    log(f"{stage}: {total} task(s) to run")
    counts = {"done": 0, "failed": 0, "rejected": 0}
    in_a_row, started, last_report = 0, time.monotonic(), time.monotonic()
    while not stop.requested:
        claimed = queue.claim(stage)
        if not claimed:
            break
        key, kind, params = claimed
        fetch, apply = KINDS[kind]
        api.task = key
        try:
            result = fetch(api, params, log)
            with db:  # the task's findings, its follow-ups and its status are written together
                for follow in apply(db, params, result):
                    queue.add(*follow)
                queue.set_status(key, "done")
            status = "done"
        except Exception as e:
            if isinstance(e, ApiError):  # 404: nothing there; other 4xx: rejected; 5xx or no response: failed
                status = "done" if e.status == 404 else "rejected" if e.status and e.status < 500 else "failed"
                error = None if status == "done" else str(e)[:500]
            else:  # a bug or an unexpected response
                status, error = "failed", f"{type(e).__name__}: {e}"[:500]
            with db:
                queue.set_status(key, status, error)
            if error:
                log(f"  {status}: {key}: {error}")
        counts[status] += 1
        in_a_row = in_a_row + 1 if status == "failed" else 0
        if in_a_row >= 10:
            log("10 failures in a row, so stopping. Check the network and the last error, then re-run the same command.")
            return "stopped"
        if on_task:
            on_task()
        if time.monotonic() - last_report >= 30:
            last_report = time.monotonic()
            left, rate = remaining(db, stage), sum(counts.values()) / (time.monotonic() - started)
            log(f"  {sum(counts.values())} run ({counts['failed']} failed, {counts['rejected']} rejected),"
                f" {left} left, {api.requests_made} requests, about {left / rate / 60:.0f} min to go")
    left = remaining(db, stage)
    log(f"{stage}: {counts['done']} done, {counts['failed']} failed, {counts['rejected']} rejected, {left} left;"
        f" {api.requests_made} requests made, {api.cache_hits} answered from the cache,"
        f" {time.monotonic() - started:.0f} s")
    if left or stop.requested:
        if counts["failed"] and not stop.requested:
            log("Re-run the same command to retry the failed tasks.")
        return "stopped"
    check = STAGES[stage][2]
    if check and not check(db, api, log):
        return "stopped"
    return "finished"


def human_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def show_status(db):
    tasks = {}
    for stage, status, n in db.execute("SELECT stage, status, COUNT(*) FROM tasks GROUP BY stage, status"):
        tasks.setdefault(stage, {})[status] = n
    requests = {stage: (n, size or 0) for stage, n, size in db.execute(
        "SELECT COALESCE(t.stage, substr(r.task, 1, instr(r.task, ':') - 1), 'other'), COUNT(*), SUM(r.bytes)"
        " FROM requests r LEFT JOIN tasks t ON t.task_key = r.task GROUP BY 1")}
    print(f"{'Stage':<12}{'Tasks':>8}{'Done':>8}{'Left':>8}{'Failed':>8}{'To plan':>9}{'Requests':>10}{'Cache':>10}")
    for name, (number, _, _) in STAGES.items():
        t = tasks.get(name, {})
        left = remaining(db, name)
        failed = t.get("failed", 0) + t.get("rejected", 0)
        unplanned = db.execute(UNPLANNED[name]).fetchone()[0] if name in UNPLANNED else 0
        n, size = requests.get(name, (0, 0))
        print(f"{number} {name:<10}{sum(t.values()):>8}{t.get('done', 0):>8}{left:>8}{failed:>8}"
              f"{unplanned:>9}{n:>10}{human_bytes(size):>10}")
        last = db.execute("SELECT task_key, last_error, updated_at FROM tasks WHERE stage = ?"
                          " AND status IN ('failed', 'rejected') ORDER BY updated_at DESC LIMIT 1", (name,)).fetchone()
        if last:
            print(f"   last error {last[2]}: {last[0]}: {last[1][:150]}")
    found = dict(db.execute("SELECT found_by, COUNT(*) FROM crawl_players GROUP BY found_by").fetchall())
    print(f"\nPlayers known: {sum(found.values())} ({', '.join(f'{n} from {k}' for k, n in sorted(found.items()))});"
          f" pairs: {db.execute('SELECT COUNT(*) FROM crawl_pairs').fetchone()[0]};"
          f" player-event entries: {db.execute('SELECT COUNT(*) FROM crawl_entries').fetchone()[0]}")
    local = lambda stamp: datetime.fromisoformat(stamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
    for stage, pid, started, heartbeat, outcome, finished in db.execute(
            "SELECT stage, pid, started_at, heartbeat_at, outcome, finished_at FROM runs ORDER BY run_id DESC LIMIT 3"):
        state = (f"{outcome} at {local(finished)}" if finished else
                 f"running now (last heartbeat {local(heartbeat)})" if pid_alive(pid) else
                 "ended without finishing; re-running it resumes")
        print(f"Run: {stage}, started {local(started)}, {state}")


def make_logger(stage):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"crawl.{stage}")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_DIR / f"crawl-{stage}.log", encoding="utf-8")):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger.info


def main():
    sys.stdout.reconfigure(errors="replace")  # player names can't always be printed in the console's code page
    parser = argparse.ArgumentParser(description="Run one stage of the Stats API crawl, or show progress.")
    parser.add_argument("stage", choices=["status", *STAGES])
    parser.add_argument("--sample", type=int, help="histories only: plan just this many PR players (the pilot)")
    args = parser.parse_args()
    db = connect(schema=CRAWL_SCHEMA)
    if args.stage == "status":
        show_status(db)
        return
    log = make_logger(args.stage)
    lock = RunLock(db, args.stage)
    lock.acquire()
    stop = StopFlag()
    stop.install(log)
    outcome = "crashed"
    try:
        outcome = run_stage(db, StatsApi(), args.stage, args, log, stop, on_task=lock.heartbeat)
    except KeyboardInterrupt:
        outcome = "interrupted"
        log("Stopped at once; re-run the same command to continue.")
    finally:
        lock.release(outcome)
    log(f"Run {outcome}.")
    sys.exit(0 if outcome == "finished" else 1)


if __name__ == "__main__":
    main()
