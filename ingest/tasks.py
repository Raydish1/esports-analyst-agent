"""Resumable task queue for the crawl (docs/schema-proposal.md §3, "Resuming").

Tasks live in data/db/crawl.sqlite next to the request log. A stage plans its tasks with
INSERT OR IGNORE, so planning twice adds nothing, then works through the pending ones. A
task that walks several pages is safe to repeat, because its pages come back from the cache.

Statuses: pending, running, done, failed (a timeout or server error; retried on the next
run, up to MAX_ATTEMPTS) and rejected (a client error; not retried).

Only one crawl runs at a time. A run records its process ID and a heartbeat, and a later
run takes over when that process is gone or has been silent for STALE_AFTER.
"""

import json
import os
import signal
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cache import CRAWL_DB

MAX_ATTEMPTS = 3
STALE_AFTER = timedelta(minutes=15)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  task_key    TEXT PRIMARY KEY,  -- e.g. 'placements:160000:1'
  stage       TEXT NOT NULL,     -- the crawl stage that runs it, e.g. 'histories'
  kind        TEXT NOT NULL,     -- which handler runs it
  params      TEXT NOT NULL,     -- JSON
  status      TEXT NOT NULL DEFAULT 'pending',
  attempts    INTEGER NOT NULL DEFAULT 0,
  last_error  TEXT,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tasks_stage ON tasks (stage, status);

CREATE TABLE IF NOT EXISTS runs (
  run_id        INTEGER PRIMARY KEY,
  stage         TEXT NOT NULL,
  pid           INTEGER NOT NULL,
  started_at    TEXT NOT NULL,
  heartbeat_at  TEXT NOT NULL,
  finished_at   TEXT,
  outcome       TEXT              -- finished | stopped | interrupted | crashed
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path=CRAWL_DB, schema=""):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")  # lets `status` read while a crawl writes
    db.executescript(SCHEMA + schema)
    return db


def pid_alive(pid):
    if os.name == "nt":  # os.kill(pid, 0) would terminate the process on Windows
        import ctypes
        synchronize, wait_timeout = 0x00100000, 0x00000102
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class TaskQueue:
    def __init__(self, db):
        self.db = db

    def add(self, stage, kind, key, params):
        """Plan a task; nothing happens if it's already planned. The caller commits."""
        self.db.execute("INSERT OR IGNORE INTO tasks (task_key, stage, kind, params, updated_at)"
                        " VALUES (?, ?, ?, ?, ?)", (key, stage, kind, json.dumps(params), now()))

    def requeue(self, stage):
        """At the start of a run: tasks a crashed run left 'running', and failed tasks with
        attempts left, go back to 'pending'. Returns how many of each."""
        with self.db:
            running = self.db.execute("UPDATE tasks SET status = 'pending', updated_at = ?"
                                      " WHERE stage = ? AND status = 'running'", (now(), stage)).rowcount
            failed = self.db.execute("UPDATE tasks SET status = 'pending', updated_at = ?"
                                     " WHERE stage = ? AND status = 'failed' AND attempts < ?",
                                     (now(), stage, MAX_ATTEMPTS)).rowcount
        return running, failed

    def claim(self, stage):
        """The next pending task, marked 'running', or None when the stage has none left."""
        row = self.db.execute(
            "SELECT task_key, kind, params FROM tasks WHERE stage = ? AND status = 'pending'"
            " ORDER BY rowid LIMIT 1", (stage,)).fetchone()
        if not row:
            return None
        with self.db:
            self.db.execute("UPDATE tasks SET status = 'running', updated_at = ? WHERE task_key = ?",
                            (now(), row[0]))
        return row[0], row[1], json.loads(row[2])

    def set_status(self, key, status, error=None):
        """Mark a task done, failed or rejected. The caller commits."""
        self.db.execute(
            "UPDATE tasks SET status = ?, last_error = ?, updated_at = ?,"
            " attempts = attempts + (CASE WHEN ? = 'failed' THEN 1 ELSE 0 END) WHERE task_key = ?",
            (status, error, now(), status, key))


class RunLock:
    """Records this run and refuses to start while another crawl is running."""

    def __init__(self, db, stage):
        self.db, self.stage, self.run_id = db, stage, None

    def acquire(self):
        cutoff = (datetime.now(timezone.utc) - STALE_AFTER).isoformat(timespec="seconds")
        for run_id, stage, pid, heartbeat in self.db.execute(
                "SELECT run_id, stage, pid, heartbeat_at FROM runs WHERE finished_at IS NULL").fetchall():
            if pid != os.getpid() and pid_alive(pid) and heartbeat >= cutoff:
                raise SystemExit(f"Another crawl is running ({stage}, process {pid}). Wait for it, or stop it first.")
            with self.db:
                self.db.execute("UPDATE runs SET finished_at = ?, outcome = 'interrupted' WHERE run_id = ?",
                                (heartbeat, run_id))
        with self.db:
            self.run_id = self.db.execute(
                "INSERT INTO runs (stage, pid, started_at, heartbeat_at) VALUES (?, ?, ?, ?)",
                (self.stage, os.getpid(), now(), now())).lastrowid

    def heartbeat(self):
        with self.db:
            self.db.execute("UPDATE runs SET heartbeat_at = ? WHERE run_id = ?", (now(), self.run_id))

    def release(self, outcome):
        with self.db:
            self.db.execute("UPDATE runs SET finished_at = ?, outcome = ? WHERE run_id = ?",
                            (now(), outcome, self.run_id))


class StopFlag:
    """The first Ctrl+C asks the run to stop after the current task; a second one stops it at once."""

    def __init__(self):
        self.requested = False

    def install(self, log):
        def handler(signum, frame):
            if self.requested:
                raise KeyboardInterrupt
            self.requested = True
            log("Stopping after the current task (press Ctrl+C again to stop now).")
        signal.signal(signal.SIGINT, handler)
