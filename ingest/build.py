"""The database builder (docs/build-plan.md): a new build in data/db/builds/ from the cache and
curation/ alone.

    python ingest/build.py                build, run the checks, and make the build live if they pass
    python ingest/build.py --no-publish   build and check, but leave the live build as it is
    python ingest/build.py --as-of TIME   build from the responses fetched up to TIME (ISO 8601, UTC
                                          unless it gives a zone); such a build of the past never goes live
    python ingest/build.py --event ID     a dev build of the events named (repeatable), never published
    python ingest/build.py --dev          a dev build of DEV_EVENTS, the awkward cases, never published
    python ingest/build.py status         the live build and the builds kept
    python ingest/build.py rollback       make the build that was live before live again

It makes no requests and doesn't read the crawl's planning tables, so it can run while a crawl
does. Without --as-of, the cutoff is the build's start, so a response fetched during the build
isn't used. Each build records what it was made from in its build_info table: the cutoff, the
newest response it saw, the code commit and a hash of every curation file.

The steps fill the tables in the build plan's order (§1), and the checks then decide whether the
build goes live (§3). Both arrive one step of the plan's order of work at a time. A check returns
outcomes, each with a gate, and for now a build passes unless a blocking check fails.
"""

import argparse
import hashlib
import json
import logging
import sqlite3
import subprocess
import sys
import time
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

import build_events
import build_placements
import build_players
import curation
from builds import BuildRunning, Builds
from cache import CACHE_DIR, CRAWL_DB, ROOT
from cache_reader import CacheReader, utc_stamp
from curation import AUTO_MERGES, CURATION_DIR
from problems import BuildStop

SCHEMA = Path(__file__).resolve().parent / "schema.sql"
LOG_DIR = ROOT / "data" / "logs"
DEV_EVENTS = [  # awkward cases for a dev build (docs/build-plan.md §6)
    "tournament/brawlhalla-world-championship-expo-2022/event/1v1",  # BCX 2022: big, with many DQs
    "tournament/brawlhalla-world-championship-expo-2022/event/2v2",
    "fcb7a286-3f0c-4f68-f9a5-08ded4cb1c05",  # Autumn Championship NA 2026 1v1, on Challengermode
    "774eaef2-3f11-4c7b-f9ab-08ded4cb1c05",  # its 2v2
    "tournament/europe-steelseries-championship-1/event/brawlhalla-championship-1v1",  # sets fetched pool by pool
    "tournament/north-america-crew-battle-invitational/event/brawlhalla-crew-battle-3v3",  # a crew battle on start.gg
    "d883b17c-e3b4-428b-6372-08debb341c9c",  # a crew battle on Challengermode (NA 2026)
    "series/pro-series-2019-na", "series/pro-series-2019-eu", "series/pro-series-2021-na",  # Stats API only
    "tournament/ceo-dreamland/event/brawlhalla-doubles",  # 2v2, filed as 1v1
    "tournament/brawl-league-masters-season-4-na-1/event/swiss",  # one competition in two phases
    "tournament/brawl-league-masters-season-4-na-1/event/top-8-finals",
    "tournament/sea-league-week-1-4/event/brawlhalla-singles",  # standings miss entrants who played
    "tournament/max-mode-2025/event/brawlhalla-1v1",
    "tournament/ceo-dreamland-2020/event/brawlhalla-1v1",
]

Outcome = namedtuple("Outcome", "check_id gate subject outcome detail")  # a row of build_checks


class Build:
    """What a step works with: the new database, the cache, the curation files, the events chosen for a
    dev build (None: all), the log, and build_info to add to."""

    def __init__(self, db, reader, curation_dir, log, events=None, auto_merges=AUTO_MERGES):
        self.db, self.reader, self.curation_dir, self.log = db, reader, Path(curation_dir), log
        self.events = set(events) if events is not None else None
        self.auto_merges = auto_merges
        self.curation = None  # set by the curation step
        self.players = None  # the player registry, set by the players step
        self.info = {}


def load_curation(build):
    """Step 1: every curated file, checked before the cache is read (curation.py)."""
    build.curation = cur = curation.load(build.curation_dir, build.auto_merges)
    auto = sum(1 for m in cur.merges if m.source == "auto")
    build.log(f"  {len(cur.events)} event rows, {len(cur.format_rules)} format rules, {len(cur.event_aliases)} event"
              f" aliases, {len(cur.event_terms)} event terms, {len(cur.player_aliases)} player aliases,"
              f" {len(cur.merges)} merges ({auto} automatic), {len(cur.rejections)} rejections")
    for merge, reason in cur.dropped_auto:
        build.log(f"  automatic merge of {merge.player_id} into {merge.canonical_player_id} dropped: {reason}")


STEPS = [  # (name, function(build)) in the build plan's order; each fills its tables
    ("curation", load_curation),
    ("events", build_events.step),
    ("players", build_players.players_step),
    ("standings", build_players.standings_step),
    ("placements", build_placements.step),
]
CHECKS = []  # functions(build) returning Outcomes


def stamp(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def code_version():
    """The commit the code was built from, and whether ingest/ had uncommitted changes then."""
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    commit = git("rev-parse", "HEAD")
    if not commit:
        return {"code_commit": "unknown", "code_changed": "unknown"}
    return {"code_commit": commit, "code_changed": "yes" if git("status", "--porcelain", "--", "ingest") else "no"}


def curation_hashes(curation_dir, auto_merges=None):
    """A short SHA-256 of every curation file, and of data/review/auto_merges.csv if there is one, so two
    builds' inputs can be compared."""
    hashes = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()[:16] for f in sorted(Path(curation_dir).glob("*.csv"))}
    if auto_merges and Path(auto_merges).exists():
        hashes["data/review/auto_merges.csv"] = hashlib.sha256(Path(auto_merges).read_bytes()).hexdigest()[:16]
    return hashes


def make_build(builds=None, as_of=None, publish=True, log=print, cache_dir=CACHE_DIR, crawl_db=CRAWL_DB,
               curation_dir=CURATION_DIR, auto_merges=AUTO_MERGES, events=None, steps=None, checks=None):
    """Make a build, and publish it if its checks pass and `publish` is set. Returns (build ID, passed).
    With `events`, a dev build of just those, which is never published.

    A step that raises leaves its partial file behind, and the next build's pruning removes it."""
    builds = builds or Builds()
    steps = STEPS if steps is None else steps
    checks = CHECKS if checks is None else checks
    with builds.lock(log=log):
        started = datetime.now(timezone.utc)
        build_id = builds.new_id(started)
        reader = CacheReader(cache_dir, crawl_db, as_of=as_of or started.isoformat())
        db = sqlite3.connect(builds.start(build_id))
        try:
            db.execute("PRAGMA journal_mode = OFF")  # an unfinished build is thrown away, so no rollback journal
            db.execute("PRAGMA synchronous = OFF")
            db.execute("PRAGMA cache_size = -262144")  # 256 MB, rather than 2 MB: the big tables fit
            db.execute("PRAGMA temp_store = MEMORY")  # sorts for windows and GROUP BYs stay off the disk
            db.executescript(SCHEMA.read_text(encoding="utf-8"))
            build = Build(db, reader, curation_dir, log, events, auto_merges)
            build.info.update(build_id=build_id, started_at=stamp(started), as_of=reader.as_of,
                              cache_cutoff=reader.cutoff(), **code_version(),
                              curation=json.dumps(curation_hashes(curation_dir, auto_merges)),
                              scope="all events" if events is None else json.dumps(sorted(events)))
            log(f"Build {build_id}: responses fetched up to {reader.as_of}; the newest is from {build.info['cache_cutoff']}")
            for name, step in steps:
                begun = time.monotonic()
                step(build)
                db.commit()
                log(f"  {name}: {time.monotonic() - begun:.1f} s")
            outcomes = [outcome for check in checks for outcome in check(build)]
            db.executemany("INSERT INTO build_checks (check_id, gate, subject, outcome, detail) VALUES (?, ?, ?, ?, ?)",
                           outcomes)
            passed = not any(o.gate == "blocking" and o.outcome == "fail" for o in outcomes)
            build.info.update(finished_at=stamp(datetime.now(timezone.utc)), verdict="pass" if passed else "fail")
            db.executemany("INSERT INTO build_info (key, value) VALUES (?, ?)", sorted(build.info.items()))
            db.commit()
            db.execute("PRAGMA journal_mode = DELETE")  # readers get one self-contained file
        finally:
            db.close()
            reader.close()
        builds.finish(build_id, passed)
        if not passed:
            log(f"Build {build_id} failed its checks, so it's kept as {builds.path(build_id, 'failed').name}"
                " and the live build stays")
        elif publish and events is None:
            builds.publish(build_id)
            log(f"Build {build_id} is live")
        else:
            log(f"Build {build_id} passed; not published ({'a dev build' if events is not None else 'as asked'})")
        builds.prune(log)
    return build_id, passed


def read_info(path):
    """A build file's build_info, or {} if it can't be read."""
    try:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            return dict(db.execute("SELECT key, value FROM build_info"))
        finally:
            db.close()
    except sqlite3.Error:
        return {}


def show_status(builds):
    live = builds.live()
    if live:
        before = [b for b in live["history"][:-1] if builds.path(b).exists()]
        print(f"Live build: {live['build']} ({live['how']} {live['at']}). Earlier live builds kept for a rollback:"
              f" {', '.join(reversed(before)) or 'none'}")
    else:
        print("No build is live yet.")
    files = builds.files()
    if not files:
        return
    print(f"\n{'Build':<20}{'State':<9}{'Size':>9}  {'Responses up to':<34}Newest response")
    for build_id, state in files:
        path = builds.path(build_id, state)
        info = read_info(path) if state != "partial" else {}
        mark = "  (live)" if live and build_id == live["build"] else ""
        print(f"{build_id:<20}{state:<9}{path.stat().st_size / 1e6:>7.1f}MB  {info.get('as_of') or '-':<34}"
              f"{info.get('cache_cutoff') or '-'}{mark}")


def make_logger():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("build")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_DIR / "build.log", encoding="utf-8")):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger.info


def main():
    sys.stdout.reconfigure(errors="replace")  # player names can't always be printed in the console's code page
    parser = argparse.ArgumentParser(description="Build the database from the cache and curation/, or manage builds.")
    parser.add_argument("command", nargs="?", default="build", choices=["build", "status", "rollback"])
    parser.add_argument("--as-of", metavar="TIME",
                        help="build from the responses fetched up to TIME (ISO 8601; UTC unless it gives a zone);"
                             " such a build never goes live")
    parser.add_argument("--no-publish", action="store_true", help="build and check, but leave the live build as it is")
    parser.add_argument("--event", action="append", metavar="ID",
                        help="a dev build of just this event (repeat for more); never published")
    parser.add_argument("--dev", action="store_true", help="a dev build of the awkward cases in DEV_EVENTS; never published")
    args = parser.parse_args()
    if args.command != "build" and (args.as_of or args.no_publish or args.event or args.dev):
        parser.error("--as-of, --no-publish, --event and --dev go with build")
    if args.as_of:
        try:
            utc_stamp(args.as_of)
        except ValueError:
            parser.error(f"--as-of: not an ISO 8601 time: {args.as_of}")
    builds = Builds()
    if args.command == "status":
        show_status(builds)
        return
    if args.command == "rollback":
        try:
            was = builds.live()["build"] if builds.live() else None
            print(f"Live build: {builds.rollback()} (rolled back from {was})")
        except ValueError as e:
            sys.exit(str(e))
        return
    log = make_logger()
    events = (args.event or []) + (DEV_EVENTS if args.dev else []) or None
    try:
        _, passed = make_build(builds, as_of=args.as_of, publish=not (args.no_publish or args.as_of), log=log,
                               events=events)
    except BuildRunning as e:
        log(str(e))
        sys.exit(2)
    except BuildStop as e:  # a curation error, or data the build can't work around
        log("The build stopped, and the live build stays. Fix these first:")
        for problem in e.problems:
            log(f"  {problem}")
        sys.exit(1)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
