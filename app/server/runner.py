"""One conversation's agent, for the worker: react.Conversation with the hooks the page needs, and the model it asks.

- The model call is wrapped, so the page hears "what it is doing" before each step.
- ProgressTools reports each tool call as it starts; the step itself comes from on_step once it finishes.
- Replay mode (replay.py) gives each turn its recording's replies and examples; live mode (Live) asks the model
  server, as ask.py does.

The worker runs one question at a time, so one shared ProgressTools serves every conversation.
"""

import ask as asking
import react

import events
import figures
import replay


class ProgressTools(react.Tools):
    """react.Tools that tells listener(name, arguments) when a call starts. Loaded once: the name index takes a while."""

    listener = None

    def call(self, name, arguments):
        if self.listener:
            self.listener(name, react.parsed(arguments))
        return super().call(name, arguments)


class NoRecording(LookupError):
    pass


class Agent:
    """One conversation. ask(question, emit) answers a question, sending the page its events through emit, and returns
    the answer event."""

    def __init__(self, tools, source, cards=None):
        self.tools, self.source, self.cards = tools, source, cards
        self.emit, self.number, self.model, self.trace, self.previous = None, 0, None, None, None
        self.start()

    def start(self):
        """A conversation from the beginning (also after an error, which can leave it half-way through a turn)."""
        self.state = self.source.state()
        self.names = {}  # player IDs the conversation's tools returned, to their names: for the progress labels
        self.conversation = react.Conversation(self.tools, ask=self.chat, log=lambda *_: None, on_step=self.stepped,
                                               retriever=self.state.retriever, on_examples=self.examples,
                                               **self.source.model)

    def chat(self, messages, **model):
        self.number += 1
        self.emit(events.thinking(self.number, self.previous))
        return self.model(messages, **model)

    def stepped(self, step):
        self.previous = step
        events.player_names(step, self.names)
        self.emit(events.step(step))

    def examples(self, found):
        self.emit(events.examples(found))

    def started(self, name, arguments):
        self.emit(events.tool_started(self.number, name, arguments, self.names))

    def ask(self, question, emit):
        self.emit, self.number, self.trace, self.previous = emit, 0, None, None
        self.tools.listener = self.started
        try:
            self.model, about = self.source.begin(self.state, question)
            trace = self.trace = self.state.ask(self.conversation, question)
            out = events.answer(trace)
            extra = self.source.end(self.state, self.model)
            if about or extra:
                out["replay"] = {**(about or {}), **(extra or {})}
            return out
        except Exception:
            self.start()
            raise
        finally:
            self.tools.listener = None


    def figures(self):
        """The stat cards for the last answer, built from the app's own template calls (figures.Cards), or []."""
        return self.cards.build(self.trace) if self.cards and self.trace else []

    def shown(self, cards):
        """Tell the agent what the page showed beside the last answer (react.Conversation.shown), as one line
        (figures.summary), so a follow-up about a card's figure has it; and keep it in the transcript."""
        line = figures.summary(cards)
        if line:
            self.conversation.shown(line)
            self.state.shown(line)


class ReplayState:
    def __init__(self):
        self.asked, self.recording, self.retriever = [], None, replay.ReplayRetriever()

    def ask(self, conversation, question):
        return conversation.ask(question)

    def shown(self, line):
        pass  # a replay has no transcript


class Replay:
    """Replay mode: each question's recorded replies, found by the conversation's questions so far (replay.Index)."""

    model = {"model": react.MODEL, "think": True, "seed": 0}
    mode = "replay"

    def __init__(self, index, speed=0.1, most=2.0):
        self.index, self.speed, self.most = index, speed, most

    def state(self):
        return ReplayState()

    def begin(self, state, question):
        asked = [*state.asked, question]
        found = self.index.match(asked, state.recording)
        if found is None:
            raise NoRecording("There's no recording of this question in replay mode. Pick one of the example questions."
                              if len(asked) == 1 else
                              "There's no recording of this follow-up after the questions before it in replay mode.")
        state.asked, state.recording = asked, found
        trace = found.turns[len(asked) - 1]
        state.retriever.trace = trace
        return replay.ReplayModel(trace, self.speed, self.most), {"source": found.source, "seed": found.seed}

    def end(self, state, model):
        if model.left:
            used = len(model.steps) - model.left
            return {"mismatch": f"The current agent finished at step {used}; the recording went on to step"
                                f" {len(model.steps)}: the agent has changed since it was recorded."}
        return None


class LiveState:
    """A live conversation, whose transcript (ask.Session's format) is rewritten after each question."""

    def __init__(self, retriever, path, header):
        self.retriever, self.path, self.header, self.session = retriever, path, header, None

    def ask(self, conversation, question):
        if self.session is None or self.session.conversation is not conversation:
            self.session = asking.Session(conversation, self.path, self.header)
        return self.session.ask(question)

    def shown(self, line):
        """The transcript's last turn gets the line too (Session keeps its own copy of each trace)."""
        if self.session and self.session.traces:
            self.session.traces[-1]["shown"] = line
            self.session.save()


class Live:
    """Live mode: the model server at OLLAMA_BASE_URL (react.chat), with ask.py's settings, and the retriever of worked
    examples (retrieval.Retriever, or None without examples). Transcripts go to folder/<start>-<n>.md and .jsonl."""

    mode = "live"

    def __init__(self, retriever, header, folder, chat=react.chat, seed=0):
        self.retriever, self.header, self.folder, self.chat = retriever, header, folder, chat
        self.model = {"model": react.MODEL, "think": True, "seed": seed}
        self.count = 0

    def state(self):
        self.count += 1
        return LiveState(self.retriever, self.folder / f"{self.header['run']}-{self.count:03d}", self.header)

    def begin(self, state, question):
        return self.chat, None

    def end(self, state, model):
        return None
