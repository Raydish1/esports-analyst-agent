"""One worker thread answering questions in order, a queue for those waiting, and the conversations they belong to.

A job keeps every event it sent, numbered, so a page that reconnects gets what it missed (the event stream's
Last-Event-ID). A waiting job hears its position whenever it changes.
"""

import collections
import secrets
import threading
import time
import traceback

import events
import replay

MAX_WAITING = 20
CONVERSATIONS = 50
IDLE_SECONDS = 30 * 60
JOB_SECONDS = 10 * 60  # how long a finished job's events are kept for a page to read


class Full(RuntimeError):
    pass


class Busy(RuntimeError):
    pass


class Job:
    def __init__(self, session, question):
        self.id, self.session, self.question = secrets.token_urlsafe(12), session, question
        self.events, self.finished, self.ended = [], False, None
        self.position = None
        self.changed = threading.Condition()

    def emit(self, event):
        with self.changed:
            self.events.append(event)
            self.changed.notify_all()

    def finish(self):
        with self.changed:
            self.events.append({"type": "done"})
            self.finished, self.ended = True, time.monotonic()
            self.changed.notify_all()

    def wait(self, after, timeout):
        """The events from number after on, waiting up to timeout seconds for one; and whether the job has finished."""
        with self.changed:
            if len(self.events) <= after and not self.finished:
                self.changed.wait(timeout)
            return list(enumerate(self.events))[after:], self.finished


class Session:
    """A conversation: its agent, whether a question of it is waiting or running, and when it was last used."""

    def __init__(self, agent):
        self.id, self.agent, self.busy, self.used = secrets.token_urlsafe(16), agent, False, time.monotonic()


class Worker:
    def __init__(self, make_agent, max_waiting=MAX_WAITING, conversations=CONVERSATIONS, idle=IDLE_SECONDS,
                 clock=time.monotonic):
        self.make_agent, self.max_waiting, self.max_conversations, self.idle, self.clock = (
            make_agent, max_waiting, conversations, idle, clock)
        self.sessions, self.jobs, self.waiting = {}, {}, collections.deque()
        self.lock = threading.Condition()
        self.thread, self.running = None, None

    # Conversations

    def open(self, **options):
        with self.lock:
            self.sweep()
            if len(self.sessions) >= self.max_conversations:
                idle = [s for s in self.sessions.values() if not s.busy]
                if not idle:
                    raise Full("Too many conversations are open. Try again in a few minutes.")
                del self.sessions[min(idle, key=lambda s: s.used).id]
        session = Session(self.make_agent(**options))
        session.used = self.clock()
        with self.lock:
            self.sessions[session.id] = session
        return session

    def sweep(self):
        now = self.clock()
        for sid in [s.id for s in self.sessions.values() if not s.busy and now - s.used > self.idle]:
            del self.sessions[sid]
        for jid in [j.id for j in self.jobs.values() if j.finished and time.monotonic() - j.ended > JOB_SECONDS]:
            del self.jobs[jid]

    # Jobs

    def submit(self, session_id, question):
        with self.lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            if session.busy:
                raise Busy("This conversation is already answering a question.")
            if len(self.waiting) >= self.max_waiting:
                raise Full("The queue is full. Try again in a few minutes.")
            session.busy, session.used = True, self.clock()
            job = Job(session, question)
            self.jobs[job.id] = job
            self.waiting.append(job)
            self.positions()
            self.lock.notify_all()
            return job

    def positions(self):
        """Tell each waiting job its position, when it has changed (1: next)."""
        for i, job in enumerate(self.waiting, start=1):
            if job.position != i:
                job.position = i
                job.emit({"type": "queued", "position": i, "ahead": i - 1 + (self.running is not None)})

    def figures(self, job):
        """The answer's stat cards, after the answer, so they never delay it. A card that fails is left out."""
        build = getattr(job.session.agent, "figures", None)
        if build is None:
            return
        try:
            cards = build()
        except Exception:
            traceback.print_exc()
            return
        if cards:
            job.emit(events.figures(cards))
            tell = getattr(job.session.agent, "shown", None)
            if tell is not None:
                try:
                    tell(cards)  # after the page has them: the line is for the next question
                except Exception:
                    traceback.print_exc()

    def job(self, job_id):
        with self.lock:
            return self.jobs.get(job_id)

    def start(self):
        self.thread = threading.Thread(target=self.loop, name="agent-worker", daemon=True)
        self.thread.start()
        return self

    def loop(self):
        while True:
            self.run_next(block=True)

    def run_next(self, block=False):
        """Run the next waiting job. Without block, return False at once if there's none."""
        with self.lock:
            while not self.waiting:
                if not block:
                    return False
                self.lock.wait()
            job = self.running = self.waiting.popleft()
            job.position = 0
            self.positions()
        try:
            job.emit({"type": "started"})
            job.emit(job.session.agent.ask(job.question, job.emit))
            self.figures(job)
        except LookupError as e:  # no recording, in replay mode
            job.emit(events.error(e.args[0] if e.args else "Not found."))
        except replay.Mismatch as e:
            job.emit(events.error(f"The recording doesn't match the current agent: {e}. The conversation starts over."))
        except Exception as e:
            traceback.print_exc()
            job.emit(events.error(f"The agent stopped with an error: {type(e).__name__}: {e}. The conversation"
                                  " starts over."))
        finally:
            with self.lock:
                self.running = None
                job.session.busy, job.session.used = False, self.clock()
            job.finish()
        return True

