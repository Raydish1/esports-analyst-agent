"""The agent's chat on the Anthropic Messages API (2026-11-22): a second model backend beside Ollama's, for the Sonnet
experiment the user asked for. AnthropicChat is called as react.chat is, with the loop's history in Ollama's message
format, and returns a reply shaped as Ollama's /api/chat response, so the loop, its checks and the traces don't change.

The boundary, both ways:
- Out: the system message becomes the system prompt, cached with an explicit breakpoint, since the tools and the
  prompt are the same for every question; the request caches the growing conversation automatically. An assistant
  message becomes its thinking blocks as the API returned them, then its text, then its tool calls as tool_use
  blocks. The tool messages after it become one user message of tool_result blocks, in the order of the calls, with
  any note the loop adds after them. A call the loop made itself (react.Conversation.look_up) gets an id from its
  place in the history.
- Back: the text, the thinking summaries, and the tool calls with their tool_use ids; the usage as prompt_eval_count
  (every input token, cached or not), prompt_eval_cached_count and eval_count, with the raw usage beside them for the
  cost.

Thinking is adaptive at the model's default effort, with summaries shown for the traces. A reply's thinking blocks go
back unchanged in every later request of the question (preserved thinking), found again by the reply's tool-call ids,
which the loop keeps, or by its thinking summary. Within a question nothing earlier in the history changes, as the
history-editing check requires; with drop_block, a block it finds after an edit anyway is dropped instead of failing
the request, and the reply's input_transformations record it.

No seed: the API has none, and the model refuses sampling parameters. No server-side fallbacks, so every reply is the
model's own, and a refusal ends the question as refused (react.ending). The key is ANTHROPIC_API_KEY, from .env only
(react.load_env), never written anywhere else."""

import json
import urllib.error

try:
    import anthropic
    TRANSIENT = (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError)
except ImportError:  # the Ollama backend runs without the SDK
    anthropic, TRANSIENT = None, ()

MODEL = "claude-sonnet-5-5"
EFFORT = "high"  # the model's default, set so the run's header records it
MAX_TOKENS = 16000  # thinking counts toward it; a request without streaming stays under the SDK's timeout
BETAS = ["thinking-binding-controls-2026-08-01"]  # drop_block, and the input_transformations that report a drop
THINKING = {"type": "adaptive", "display": "summarized", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
THINKING_OFF = {"type": "between_tools"}  # think=False: no thinking, and it takes no other field
CACHED = {"type": "ephemeral"}


def schemas(tools):
    """The loop's tools, Ollama function schemas, as the Messages API takes them, in the same order."""
    return [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
             "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}} for t in tools]


def arguments(value):
    """A tool call's arguments as a dict: Ollama's are a dict or JSON text."""
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def call_ids(message, index):
    """The tool_use ids of an assistant message's calls: the API's, or, for a call the loop made itself, one from its
    place in the history, the same in every request."""
    return [c.get("id") or f"toolu_loop_{index}_{j}" for j, c in enumerate(message.get("tool_calls") or [])]


def assistant(message, index, kept):
    """An assistant message's content blocks: its thinking blocks as the API returned them (kept, by its first call's
    id or its thinking summary), its text, then its tool calls."""
    ids = call_ids(message, index)
    thought = kept.get(ids[0]) if ids else None
    if thought is None and message.get("thinking"):
        thought = kept.get(message["thinking"])
    blocks = list(thought or [])
    if (message.get("content") or "").strip():
        blocks.append({"type": "text", "text": message["content"]})
    blocks += [{"type": "tool_use", "id": i, "name": c["function"]["name"],
                "input": arguments(c["function"].get("arguments"))}
               for i, c in zip(ids, message.get("tool_calls") or [])]
    return blocks or [{"type": "text", "text": "(no reply)"}]


def conversation(messages, kept):
    """The loop's history as (system, messages) for the Messages API (the module docstring)."""
    system, out, pending = [], [], []
    for index, m in enumerate(messages):
        if m["role"] == "system":
            system.append({"type": "text", "text": m["content"]})
            continue
        if m["role"] == "assistant":
            out.append({"role": "assistant", "content": assistant(m, index, kept)})
            pending = call_ids(m, index)
            continue
        text = m.get("content") or "(empty)"
        block = ({"type": "tool_result", "tool_use_id": pending.pop(0), "content": text}
                 if m["role"] == "tool" and pending else {"type": "text", "text": text})
        if out and out[-1]["role"] == "user":
            out[-1]["content"].append(block)
        else:
            out.append({"role": "user", "content": [block]})
    if system:
        system[-1]["cache_control"] = CACHED
    return system, out


def kept_block(block):
    """A thinking block, or an input transformation, as the API gave it, for a request or a trace."""
    return block.model_dump(mode="json", exclude_none=True) if hasattr(block, "model_dump") else dict(vars(block))


def reply(response):
    """A Messages API response as the loop reads Ollama's (the module docstring), and its thinking blocks to keep."""
    blocks = response.content
    thought = [kept_block(b) for b in blocks if b.type in ("thinking", "redacted_thinking")]
    usage = response.usage
    read, written = usage.cache_read_input_tokens or 0, usage.cache_creation_input_tokens or 0
    out = {"message": {"role": "assistant", "content": "".join(b.text for b in blocks if b.type == "text"),
                       "thinking": "\n\n".join(b.thinking for b in blocks if b.type == "thinking" and b.thinking),
                       "tool_calls": [{"id": b.id, "function": {"name": b.name, "arguments": b.input}}
                                      for b in blocks if b.type == "tool_use"]},
           "done_reason": "length" if response.stop_reason == "max_tokens" else response.stop_reason,
           "prompt_eval_count": usage.input_tokens + read + written, "prompt_eval_cached_count": read,
           "eval_count": usage.output_tokens,
           "usage": {"input_tokens": usage.input_tokens, "cache_creation_input_tokens": written,
                     "cache_read_input_tokens": read, "output_tokens": usage.output_tokens}}
    changed = getattr(response, "input_transformations", None)
    if changed:
        out["input_transformations"] = [kept_block(t) for t in changed]
    return out, thought


class AnthropicChat:
    """react.chat's stand-in on the Messages API, called with the loop's history, model, think, seed and tools. It
    keeps each reply's thinking blocks (kept) to send back unchanged. client is the SDK's client, made on the first
    call unless given."""

    def __init__(self, client=None, effort=EFFORT, max_tokens=MAX_TOKENS):
        self.client, self.effort, self.max_tokens = client, effort, max_tokens
        self.kept = {}

    def request(self, messages, model, think, tools):
        """The Messages API request for the loop's history."""
        system, history = conversation(messages, self.kept)
        return {"model": model, "max_tokens": self.max_tokens, "system": system, "messages": history,
                "tools": schemas(tools), "thinking": THINKING if think else THINKING_OFF,
                "output_config": {"effort": self.effort}, "cache_control": CACHED, "betas": BETAS}

    def __call__(self, messages, model=MODEL, think=True, seed=0, tools=()):
        if self.client is None:
            if anthropic is None:
                raise RuntimeError("the Anthropic backend needs the SDK: pip install anthropic")
            self.client = anthropic.Anthropic(max_retries=4)  # ANTHROPIC_API_KEY, from .env
        try:
            response = self.client.beta.messages.create(**self.request(messages, model, think, tools))
        except TRANSIENT as e:  # after the SDK's retries: the loop's error for a model server that failed
            raise urllib.error.URLError(f"{type(e).__name__}: {e}") from e
        out, thought = reply(response)
        for call in out["message"]["tool_calls"]:
            self.kept[call["id"]] = thought
        if out["message"]["thinking"]:
            self.kept.setdefault(out["message"]["thinking"], thought)
        return out

    def describe(self):
        """How the backend asks, for a run's header."""
        return {"backend": "anthropic", "sdk": getattr(anthropic, "__version__", None), "effort": self.effort,
                "max_tokens": self.max_tokens, "thinking": THINKING, "betas": BETAS, "fallbacks": "none"}
