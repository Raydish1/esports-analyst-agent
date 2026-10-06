"""Build files and the pointer to the live build (docs/build-plan.md §5).

Each build is its own file in data/db/builds/, named by its UTC start time:
- <build-id>.partial.sqlite while it's being made;
- <build-id>.sqlite once its checks pass;
- <build-id>.failed.sqlite if they fail, kept for a look.

data/db/current.json names the live build, and lists the builds that were live before it.
Publishing rewrites that small file rather than a database the app may have open (Windows won't
replace an open file), so readers move to the new build on their next connection. Rolling back
returns to the build that was live before. So a build that passed but never went live (built with
--no-publish or --as-of) is never a rollback target, and neither is a build already rolled back
from.

Pruning, at the end of every build, keeps:
- the live build and the KEEP builds live before it;
- the KEEP_OTHER newest builds that passed but never went live;
- the KEEP_FAILED newest failed ones.
It skips a file still in use, and never touches data/db/eval/, where frozen evaluation snapshots
live. One build runs at a time: a second one waits for the first one's lock file to go.
"""

import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from cache import ROOT
from tasks import pid_alive

DB_DIR = ROOT / "data" / "db"
KEEP = 3  # builds kept from before the live one, so a rollback has somewhere to go
KEEP_OTHER = 2  # passed builds that never went live
KEEP_FAILED = 2
HISTORY = 20  # live builds the pointer remembers
LOCK_WAIT = 20 * 60  # seconds a build waits for another to finish
BUILD_FILE = re.compile(r"^(\d{8}T\d{6}Z(?:-\d+)?)(\.partial|\.failed)?\.sqlite$")
STATES = {None: "passed", ".partial": "partial", ".failed": "failed"}


class BuildRunning(Exception):
    pass


def order(build_id):
    """Sort key: a build ID's start time, then its -2, -3, ... suffix."""
    start, _, n = build_id.partition("-")
    return start, int(n or 1)


class Builds:
    def __init__(self, db_dir=DB_DIR):
        self.db_dir = Path(db_dir)
        self.dir = self.db_dir / "builds"
        self.pointer = self.db_dir / "current.json"
        self.lock_file = self.dir / "build.lock"

    def path(self, build_id, state="passed"):
        suffix = {"passed": "", "partial": ".partial", "failed": ".failed"}[state]
        return self.dir / f"{build_id}{suffix}.sqlite"

    def files(self):
        """(build ID, state) of every build file, oldest first."""
        found = []
        for f in self.dir.glob("*.sqlite") if self.dir.exists() else []:
            match = BUILD_FILE.match(f.name)
            if match:
                found.append((match.group(1), STATES[match.group(2)]))
        return sorted(found, key=lambda item: order(item[0]))

    def passed(self):
        return [build_id for build_id, state in self.files() if state == "passed"]

    def new_id(self, started):
        """A build's ID: its UTC start time, plus -2, -3, ... if another build started in the same second."""
        base = started.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        taken = {build_id for build_id, _ in self.files()}
        build_id, n = base, 1
        while build_id in taken:
            n += 1
            build_id = f"{base}-{n}"
        return build_id

    def start(self, build_id):
        """The file a new build is made in."""
        self.dir.mkdir(parents=True, exist_ok=True)
        return self.path(build_id, "partial")

    def finish(self, build_id, passed):
        """Name a finished build for its checks' outcome."""
        target = self.path(build_id, "passed" if passed else "failed")
        os.replace(self.path(build_id, "partial"), target)
        return target

    def live(self):
        """The pointer's contents ({build, file, how, at, history}), or None before the first publish."""
        try:
            return json.loads(self.pointer.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def live_path(self):
        live = self.live()
        return self.db_dir / live["file"] if live else None

    def connect_live(self):
        """A read-only connection to the live build, as the agent opens it."""
        path = self.live_path()
        if path is None:
            raise FileNotFoundError("no build has been published yet: run python ingest/build.py")
        return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)

    def publish(self, build_id):
        """Make a build whose checks passed the live one."""
        if not self.path(build_id).exists():
            raise FileNotFoundError(f"build {build_id} has no passed build file")
        current = self.live()
        self._point((current["history"] if current else []) + [build_id], "published")

    def rollback(self):
        """Make the build that was live before the live one live again, and return its ID."""
        current = self.live()
        if current is None:
            raise ValueError("no build is live, so there's nothing to roll back")
        history = current["history"][:-1]
        while history and not self.path(history[-1]).exists():  # pruned since
            history.pop()
        if not history:
            raise ValueError(f"no build that was live before {current['build']} is kept")
        self._point(history, "rolled back")
        return history[-1]

    def _point(self, history, how):
        self.db_dir.mkdir(parents=True, exist_ok=True)
        data = {"build": history[-1], "file": f"builds/{history[-1]}.sqlite", "how": how,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "history": history[-HISTORY:]}
        tmp = self.pointer.with_name(self.pointer.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        for _ in range(50):  # a reader may hold the pointer open for an instant, and Windows won't replace it then
            try:
                os.replace(tmp, self.pointer)
                return
            except PermissionError:
                time.sleep(0.1)
        os.replace(tmp, self.pointer)

    def prune(self, log=print):
        """Delete the builds beyond those kept. Runs at the end of a build, under its lock, so any
        partial file left is from a build that crashed."""
        history = (self.live() or {}).get("history", [])
        keep = set(history[-(KEEP + 1):])
        passed = self.passed()
        keep |= set([b for b in passed if b not in history][-KEEP_OTHER:])
        failed = [b for b, state in self.files() if state == "failed"]
        doomed = [self.path(b) for b in passed if b not in keep]
        doomed += [self.path(b, "failed") for b in failed[:max(len(failed) - KEEP_FAILED, 0)]]
        doomed += [self.path(b, "partial") for b, state in self.files() if state == "partial"]
        for path in doomed:
            try:
                path.unlink()
                log(f"Removed {path.name}")
            except PermissionError:
                log(f"Kept {path.name} for now: it's still in use")

    @contextmanager
    def lock(self, wait=LOCK_WAIT, log=print):
        """Hold the build lock. If another build holds it, wait up to `wait` seconds for it to finish;
        a lock left by a process that's gone is taken over."""
        self.dir.mkdir(parents=True, exist_ok=True)
        deadline, waiting = time.monotonic() + wait, False
        while True:
            try:
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                holder = self._lock_holder()
                if holder is None or not pid_alive(holder):  # that build crashed
                    self.lock_file.unlink(missing_ok=True)
                    continue
                if time.monotonic() >= deadline:
                    raise BuildRunning(f"another build (process {holder}) is still running; if it isn't,"
                                       f" delete {self.lock_file}") from None
                if not waiting:
                    log(f"Waiting for another build (process {holder}) to finish")
                    waiting = True
                time.sleep(2)
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        try:
            yield
        finally:
            self.lock_file.unlink(missing_ok=True)

    def _lock_holder(self):
        try:
            return int(self.lock_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None
