import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
import anthropic_chat  # noqa: E402
import react  # noqa: E402
from test_agent import Fixture  # noqa: E402  the tiny database: Raydish (11) has 6 official results


def thinking(text, signature):
    return NS(type="thinking", thinking=text, signature=signature)


def text(words):
    return NS(type="text", text=words)


def tool_use(call_id, name, arguments):
    return NS(type="tool_use", id=call_id, name=name, input=arguments)


def response(*blocks, stop="end_turn", fresh=30, read=0, written=0, output=20):
    return NS(content=list(blocks), stop_reason=stop, usage=NS(input_tokens=fresh, cache_read_input_tokens=read,
                                                               cache_creation_input_tokens=written, output_tokens=output))


class FakeClient:
    """The SDK client as the backend uses it, client.beta.messages.create(**request), giving the responses it's given
    in order and keeping a copy of every request."""

    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **request):
        self.requests.append(json.loads(json.dumps(request)))
        return self.responses.pop(0)


class ReplyTest(unittest.TestCase):
    def test_a_response_reads_as_ollamas_reply_with_its_thinking_kept_and_usage_by_price(self):
        out, thought = anthropic_chat.reply(response(
            thinking("Look raydish up.", "s1"), text("Looking."), tool_use("toolu_1", "resolve_player", {"name": "raydish"}),
            stop="tool_use", fresh=30, read=1000, written=200, output=40))
        self.assertEqual(out["message"], {"role": "assistant", "content": "Looking.", "thinking": "Look raydish up.",
                                          "tool_calls": [{"id": "toolu_1", "function": {
                                              "name": "resolve_player", "arguments": {"name": "raydish"}}}]})
        self.assertEqual((out["prompt_eval_count"], out["prompt_eval_cached_count"], out["eval_count"]), (1230, 1000, 40))
        self.assertEqual(out["usage"], {"input_tokens": 30, "cache_creation_input_tokens": 200,
                                        "cache_read_input_tokens": 1000, "output_tokens": 40})
        self.assertEqual(thought, [{"type": "thinking", "thinking": "Look raydish up.", "signature": "s1"}])
        self.assertEqual(anthropic_chat.reply(response(text("Raydish has"), stop="max_tokens"))[0]["done_reason"], "length")


class ConversationTest(unittest.TestCase):
    def test_the_loops_history_becomes_alternating_turns_with_tool_results_after_their_calls(self):
        history = [
            {"role": "system", "content": "the prompt"},
            {"role": "user", "content": "has raydish won worlds"},
            {"role": "assistant", "content": "", "thinking": "Look both up.", "tool_calls": [
                {"id": "toolu_1", "function": {"name": "resolve_player", "arguments": {"name": "raydish"}}},
                {"id": "toolu_2", "function": {"name": "resolve_event", "arguments": '{"name": "worlds"}'}}]},
            {"role": "tool", "tool_name": "resolve_player", "content": '{"status": "confident"}'},
            {"role": "tool", "tool_name": "resolve_event", "content": '{"status": "confident"}'},
            {"role": "assistant", "content": "Raydish never won worlds.", "thinking": "No wins there."},
            {"role": "user", "content": "Before this answer is final: look it up."},
            {"role": "assistant", "content": "", "tool_calls": [  # the loop's own lookup (look_up): no id
                {"function": {"name": "resolve_player", "arguments": {"name": "raydish"}}}]},
            {"role": "tool", "tool_name": "resolve_player", "content": "{}"},
            {"role": "user", "content": "You answered again without looking anything up."}]
        looked = [{"type": "thinking", "thinking": "Look both up.", "signature": "s1"}]
        answered = [{"type": "thinking", "thinking": "No wins there.", "signature": "s2"}]
        kept = {"toolu_1": looked, "toolu_2": looked, "No wins there.": answered}
        system, messages = anthropic_chat.conversation(history, kept)
        self.assertEqual(system, [{"type": "text", "text": "the prompt", "cache_control": {"type": "ephemeral"}}])
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "user", "assistant", "user", "assistant", "user"])
        self.assertEqual(messages[1]["content"], looked + [
            {"type": "tool_use", "id": "toolu_1", "name": "resolve_player", "input": {"name": "raydish"}},
            {"type": "tool_use", "id": "toolu_2", "name": "resolve_event", "input": {"name": "worlds"}}])
        self.assertEqual([(b["type"], b["tool_use_id"]) for b in messages[2]["content"]],
                         [("tool_result", "toolu_1"), ("tool_result", "toolu_2")])
        self.assertEqual(messages[3]["content"], answered + [{"type": "text", "text": "Raydish never won worlds."}])
        self.assertEqual(messages[5]["content"][0]["id"], "toolu_loop_7_0")  # from its place: the same every request
        self.assertEqual([(b["type"], b.get("tool_use_id"), b.get("text")) for b in messages[6]["content"]],
                         [("tool_result", "toolu_loop_7_0", None),
                          ("text", None, "You answered again without looking anything up.")])

    def test_the_tools_keep_their_order_and_parameters_as_input_schemas(self):
        schemas = anthropic_chat.schemas(react.TOOLS)
        self.assertEqual([s["name"] for s in schemas], [t["function"]["name"] for t in react.TOOLS])
        self.assertEqual(schemas[0]["input_schema"], react.TOOLS[0]["function"]["parameters"])


class LoopTest(Fixture):
    def test_a_question_through_the_loop_replays_each_replys_thinking_unchanged_in_an_append_only_history(self):
        client = FakeClient(
            response(thinking("Look raydish up.", "s1"), tool_use("toolu_1", "resolve_player", {"name": "raydish"}),
                     stop="tool_use", written=900),
            response(thinking("And worlds.", "s2"), text("Now the event."),
                     tool_use("toolu_2", "resolve_event", {"name": "worlds"}), stop="tool_use", read=900, written=60),
            response(thinking("Raydish has 6.", "s3"), text("Raydish has 6 official results."), read=960, written=80))
        chat = anthropic_chat.AnthropicChat(client=client)
        trace = react.run("how many official results has raydish?", react.Tools(self.path), ask=chat, log=lambda *_: None,
                          model=anthropic_chat.MODEL, think=True, seed=0)
        self.assertEqual((trace["outcome"], trace["answer"]), ("answered", "Raydish has 6 official results."))
        first, second, third = client.requests
        for earlier, later in ((first, second), (second, third)):  # nothing earlier ever changes
            self.assertEqual(later["messages"][:len(earlier["messages"])], earlier["messages"])
        self.assertEqual([b["type"] for b in third["messages"][1]["content"]], ["thinking", "tool_use"])
        self.assertEqual(third["messages"][1]["content"][0], {"type": "thinking", "thinking": "Look raydish up.",
                                                              "signature": "s1"})
        self.assertEqual(third["messages"][3]["content"][0], {"type": "thinking", "thinking": "And worlds.",
                                                              "signature": "s2"})
        self.assertEqual(third["messages"][2]["content"][0]["tool_use_id"], "toolu_1")
        self.assertEqual([t["name"] for t in first["tools"]], [t["function"]["name"] for t in react.TOOLS])
        self.assertEqual((first["system"][-1]["cache_control"], first["cache_control"]), ({"type": "ephemeral"},) * 2)
        self.assertEqual((first["model"], first["thinking"], first["output_config"], first["betas"]),
                         ("claude-sonnet-5-5", anthropic_chat.THINKING, {"effort": "high"}, anthropic_chat.BETAS))
        self.assertFalse({"temperature", "top_p", "top_k", "seed"} & set(first))  # the model refuses sampling settings
        self.assertEqual(trace["steps"][2]["usage"], {"input_tokens": 30, "cache_creation_input_tokens": 80,
                                                      "cache_read_input_tokens": 960, "output_tokens": 20})

    def test_without_templates_the_request_offers_run_sql_and_the_lookups_only(self):
        client = FakeClient(response(text("I need a question to answer.")))
        react.run("hello", react.Tools(self.path, templates=False), ask=anthropic_chat.AnthropicChat(client=client),
                  log=lambda *_: None, model=anthropic_chat.MODEL, think=False, seed=0)
        self.assertEqual([t["name"] for t in client.requests[0]["tools"]], ["resolve_player", "resolve_event", "run_sql"])
        self.assertEqual(client.requests[0]["thinking"], {"type": "between_tools"})

    def test_a_refusal_ends_the_question_as_refused(self):
        client = FakeClient(response(stop="refusal"))
        trace = react.run("how many official results has raydish?", react.Tools(self.path),
                          ask=anthropic_chat.AnthropicChat(client=client), log=lambda *_: None,
                          model=anthropic_chat.MODEL, think=True, seed=0)
        self.assertEqual(trace["outcome"], "refused")


@unittest.skipUnless(anthropic_chat.anthropic, "the anthropic SDK isn't installed for this Python")
class ErrorTest(unittest.TestCase):
    def test_a_connection_failure_after_the_sdks_retries_is_the_loops_server_error(self):
        import urllib.error
        try:
            import httpx2 as httpx  # the SDK's HTTP library from 1.x on
        except ImportError:
            import httpx

        def fail(**request):
            raise anthropic_chat.anthropic.APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
        chat = anthropic_chat.AnthropicChat(client=NS(beta=NS(messages=NS(create=fail))))
        with self.assertRaises(urllib.error.URLError):
            chat([{"role": "system", "content": "p"}, {"role": "user", "content": "q"}], tools=react.TOOLS)
