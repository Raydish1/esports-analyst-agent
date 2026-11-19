"""Export a few recorded conversations as a demo for the static site (GitHub Pages, where there's no backend).

    python app/dev/export_demo.py      writes app/static/demo/demo.json

Each conversation is asked through the real app in replay mode (main.create_app, in-process, recorded model replies
through the real loop, tools and stat cards), and every event the page would have received is kept. The page plays
them back (app.js) when it can't reach the server. Only these questions work there; anything else gets a note.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "app" / "server"))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import runner  # noqa: E402

OUT = ROOT / "app" / "static" / "demo" / "demo.json"
# Conversations with a recording, chosen to show each kind of result: a head-to-head with its sets, a lifetime card,
# a comparison, an event's top 8 sets, a table, and a "which player?" question answered by its button.
CONVERSATIONS = [
    ["whats bbballoonboy's 1v1 record vs impala"],
    ["How many medals does Balloonboy have?"],
    ["who has more medals, boomie or sandstorm?"],
    ["who won worlds 2019 1v1"],
    ["rank the top 5 players by official 1v1 wins"],
    ["did markiemoo ever win worlds", "the first one"],
]
KEEP = {"thinking", "tool_started", "step", "examples", "answer", "figures", "error"}


def events(client, conversation, question):
    job = client.post(f"/api/conversations/{conversation}/questions", json={"question": question}).json()["job_id"]
    found = []
    with client.stream("GET", f"/api/jobs/{job}/events") as response:
        for line in response.iter_lines():
            if line.startswith("data: "):
                event = json.loads(line[6:])
                if event["type"] in KEEP:
                    found.append(event)
    return found


def main_():
    source = main.replay_source(None, speed=0)
    client = TestClient(main.create_app(source, runner.ProgressTools()))
    conversations = []
    for questions in CONVERSATIONS:
        conversation = client.post("/api/conversations").json()["conversation_id"]
        turns = []
        for q in questions:
            found = events(client, conversation, q)
            kinds = [e["type"] for e in found]
            if "error" in kinds or "answer" not in kinds:
                sys.exit(f"{q!r} didn't replay cleanly: {kinds}")
            turns.append({"question": q, "events": found})
            print(f"{q}: {len(found)} events, {sum(len(e['figures']) for e in found if e['type'] == 'figures')} cards")
        conversations.append(turns)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"about": __doc__.strip().splitlines()[0], "conversations": conversations},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main_()
