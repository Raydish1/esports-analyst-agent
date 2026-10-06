"""The database builder (docs/build-plan.md): a new build in data/db/builds/ from the cache and
curation/ alone.

    python ingest/build.py                build, run the checks, and make the build live if they pass
    python ingest/build.py --no-publish   build and check, but leave the live build as it is
    python ingest/build.py --as-of TIME   build from the responses fetched up to TIME (ISO 8601, UTC
                                          unless it gives a zone); such a build of the past never goes live
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

from builds import BuildRunning, Builds
from cache import CACHE_DIR, CRAWL_DB, ROOT
from cache_reader import CacheReader, utc_stamp

SCHEMA = Path(__file__).resolve().parent / "schema.sql"
CURATION_DIR = ROOT / "curation"
LOG_DIR = ROOT / "data" / "logs"

Outcome = namedtuple("Outcome", "check_id gate subject outcome detail")  # a row of build_checks

STEPS = []   # (name, function(build)) in the build plan's order; each fills its tables
CHECKS = []  # functions(build) returning Outcomes


class Build:
    """What a step works with: the new database, the cache, the curation files, the log, and
    build_info to add to."""

    def __init__(self, db, reader, curation_dir, log):
        self.db, self.reader, self.curation_dir, self.log = db, reader, Path(curation_dir), log
        self.info = {}


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


def curation_hashes(curation_dir):
    """A short SHA-256 of every curation file, so two builds' inputs can be compared."""
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest()[:16] for f in sorted(Path(curation_dir).glob("*.csv"))}


def make_build(builds=None, as_of=None, publish=True, log=print, cache_dir=CACHE_DIR, crawl_db=CRAWL_DB,
               curation_dir=CURATION_DIR, steps=None, checks=None):
    """Make a build, and publish it if its checks pass and `publish` is set. Returns (build ID, passed).

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
            db.executescript(SCHEMA.read_text(encoding="utf-8"))
            build = Build(db, reader, curation_dir, log)
            build.info.update(build_id=build_id, started_at=stamp(started), as_of=reader.as_of,
                              cache_cutoff=reader.cutoff(), **code_version(),
                              curation=json.dumps(curation_hashes(curation_dir)))
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
        elif publish:
            builds.publish(build_id)
            log(f"Build {build_id} is live")
        else:
            log(f"Build {build_id} passed; not published, as asked")
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
    args = parser.parse_args()
    if args.command != "build" and (args.as_of or args.no_publish):
        parser.error("--as-of and --no-publish go with build")
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
    try:
        _, passed = make_build(builds, as_of=args.as_of, publish=not (args.no_publish or args.as_of), log=log)
    except BuildRunning as e:
        log(str(e))
        sys.exit(2)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
