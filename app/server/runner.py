"""One conversation's agent, for the worker: react.Conversation with the hooks the page needs, and the model it asks.

- The model call is wrapped, so the page hears "thinking (step N)" before each step.
- ProgressTools reports each tool call as it starts; the step itself comes from on_step once it finishes.
- Replay mode (replay.py) gives each turn its recording's replies and examples; live mode (Live) asks the model
  server, as ask.py does.

The worker runs one question at a time, so one shared ProgressTools serves every conversation.
"""

import react

import events
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

    def __init__(self, tools, source):
        self.tools, self.source = tools, source
        self.emit, self.number, self.model = None, 0, None
        self.start()

    def start(self):
        """A conversation from the beginning (also after an error, which can leave it half-way through a turn)."""
        self.state = self.source.state()
        self.conversation = react.Conversation(self.tools, ask=self.chat, log=lambda *_: None, on_step=self.stepped,
                                               retriever=self.state.retriever, on_examples=self.examples,
                                               **self.source.model)

    def chat(self, messages, **model):
        self.number += 1
        self.emit(events.thinking(self.number))
        return self.model(messages, **model)

    def stepped(self, step):
        self.emit(events.step(step))

    def examples(self, found):
        self.emit(events.examples(found))

    def started(self, name, arguments):
        self.emit(events.tool_started(self.number, name, arguments))

    def ask(self, question, emit):
        self.emit, self.number = emit, 0
        self.tools.listener = self.started
        try:
            self.model, about = self.source.begin(self.state, question)
            trace = self.state.ask(self.conversation, question)
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


class ReplayState:
    def __init__(self):
        self.asked, self.recording, self.retriever = [], None, replay.ReplayRetriever()

    def ask(self, conversation, question):
        return conversation.ask(question)


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
