"""The demo web app's server: the agent behind a queue, its progress streamed to the page as Server-Sent Events.

    python app/server/main.py                        replay mode (the default): recorded model replies, no model server
    python app/server/main.py --replay-runs A B      replay only these runs' recordings (directories of data/experiments)
    py -3.14 app/server/main.py --mode live          live mode: the model server at OLLAMA_BASE_URL (.env)
    python app/server/main.py --mode live --examples off    live mode without worked examples, on any Python

Live mode uses the GPU the evaluation runs use: don't start it while an eval run is going. Its transcripts go to
data/experiments/web/, which replay mode never reads.

Then open http://127.0.0.1:8000. It binds 127.0.0.1 unless --host says otherwise. Nothing secret goes to the page:
the model server's address is read here only, and redacted from every text sent (events.redact).

Routes:
    GET  /api/info                              the mode and the example questions
    POST /api/conversations                     a new conversation: {"conversation_id"}
    POST /api/conversations/{id}/questions      {"question"}: {"job_id", "position"}
    GET  /api/jobs/{id}/events                  the job's events (text/event-stream), from Last-Event-ID on
"""

import argparse
import asyncio
import json
import os
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(HERE))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import figures  # noqa: E402
import react  # noqa: E402
from platform_clients import load_env  # noqa: E402  in ingest/, which react puts on the path
import replay  # noqa: E402
import runner  # noqa: E402
import worker as workers  # noqa: E402

STATIC = HERE.parent / "static"
KEEPALIVE = 15  # seconds between comments on a quiet stream, so proxies keep it open
# The example questions, one of each kind the page shows: a template's answer, a query's, suggestions, a follow-up,
# an event that wasn't held. In replay mode only those with a recording are offered.
EXAMPLES = [
    "who won worlds 2019 1v1",
    "whats bbballoonboy's 1v1 record vs impala",
    "rank the top 5 players by official 1v1 wins",
    "Who has megd played with in 2v2 tournaments, and how did they place?",
    "did markiemoo ever win worlds",
    "How many medals does Balloonboy have?",
    "who won ceo dreamland 2020",
    "What is Raydish's most dominant tournament win?",
]


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=500)


def create_app(source, tools, worker=None, examples=EXAMPLES, static=STATIC, earnings=True, preview=False, cards=None):
    """The app around one source of models (runner.Replay or runner.Live) and one shared runner.ProgressTools.
    earnings: whether stat cards show career earnings. preview: serve GET /api/preview/lifetime/{player_id}, a card
    without a question, for rendering and comparing cards (app/dev/compare_card.py); off unless asked for."""
    cards = cards or figures.Cards(tools, earnings=earnings)
    worker = worker or workers.Worker(lambda: runner.Agent(tools, source, cards)).start()
    offered = [q for q in examples if source.mode != "replay" or source.index.has(q)]
    app = FastAPI(title="Brawlhalla esports analyst", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.worker = worker

    @app.get("/api/info")
    def info():
        return {"mode": source.mode, "examples": offered}

    @app.post("/api/conversations")
    def conversation():
        try:
            return {"conversation_id": worker.open().id}
        except workers.Full as e:
            raise HTTPException(503, str(e))

    @app.post("/api/conversations/{conversation_id}/questions")
    def ask(conversation_id: str, body: Question):
        question = " ".join(body.question.split())
        if not question:
            raise HTTPException(422, "The question is empty.")
        try:
            job = worker.submit(conversation_id, question)
        except KeyError:
            raise HTTPException(404, "This conversation has ended. Start a new one.")
        except workers.Busy as e:
            raise HTTPException(409, str(e))
        except workers.Full as e:
            raise HTTPException(503, str(e))
        return {"job_id": job.id, "position": job.position}

    @app.get("/api/jobs/{job_id}/events")
    async def stream(job_id: str, request: Request):
        job = worker.job(job_id)
        if job is None:
            raise HTTPException(404, "No such question.")
        try:
            after = int(request.headers.get("last-event-id", "-1")) + 1
        except ValueError:
            after = 0

        async def lines():
            nonlocal after
            while True:
                found, finished = await asyncio.to_thread(job.wait, after, KEEPALIVE)
                for number, event in found:
                    yield f"id: {number}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    after = number + 1
                if finished and after >= len(job.events):
                    return
                if not found:
                    if await request.is_disconnected():
                        return
                    yield ": waiting\n\n"

        return StreamingResponse(lines(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    if preview:
        @app.get("/api/preview/lifetime/{player_id}")
        def preview_lifetime(player_id: int):
            one = cards.lifetime(player_id)
            if one is None:
                raise HTTPException(404, "No such player.")
            return {"kind": "lifetime", "player": one, "scope": cards.scope([one])}

        @app.get("/api/preview/head_to_head/{player_id}/{opponent_id}")
        def preview_head_to_head(player_id: int, opponent_id: int):
            found = cards.head_to_head(player_id, opponent_id)
            if not found:
                raise HTTPException(404, "No such players.")
            return found[0]

        @app.get("/api/preview/sets/{player_id}/{opponent_id}")
        def preview_sets(player_id: int, opponent_id: int):
            found = cards.head_to_head(player_id, opponent_id)
            if len(found) < 2:
                raise HTTPException(404, "No sets between these players.")
            return found[1]

    @app.middleware("http")
    async def revalidate(request, call_next):
        """The page's files are checked with the server on every load (an unchanged file costs a 304), so a page
        never keeps running scripts older than the server's."""
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    if static.exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="static")
    return app


def replay_source(runs=None, speed=0.1):
    index = replay.Index(replay.recordings(react.RAW, runs=set(runs) if runs else None))
    if not index.recordings:
        sys.exit("No recordings to replay" + (f" in the runs {', '.join(runs)}." if runs else "."))
    return runner.Replay(index, speed=speed)


def live_source(examples, fail):
    """Live mode's source: the model server must be reachable, as ask.py requires."""
    load_env()
    start = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        header = react.run_header(start, seeds=[0], title=f"Web app session {start}",
                                  examples=react.examples_header(examples))
    except KeyError:
        fail("OLLAMA_BASE_URL isn't set: add it to .env (see .env.example).")
    except (urllib.error.URLError, TimeoutError) as e:
        fail(f"The model server at {os.environ['OLLAMA_BASE_URL']} isn't reachable: {e}")
    retriever = react.retriever_or_exit(examples, fail)
    return runner.Live(retriever, header, react.RAW / "web")


def card_earnings(flag, env):
    """Whether stat cards show earnings: the flag, else CARD_EARNINGS, else on."""
    value = (flag or env or "on").strip().lower()
    if value not in ("on", "off", "1", "0", "true", "false", "yes", "no"):
        sys.exit(f"CARD_EARNINGS is {value!r}: use on or off.")
    return value in ("on", "1", "true", "yes")


def main(argv=None):
    parser = argparse.ArgumentParser(description="The demo web app: the agent behind a queue, streamed to the page.")
    parser.add_argument("--mode", choices=["replay", "live"], default="replay",
                        help="replay: recorded model replies through the real loop and tools (the default); live: the"
                             " model server at OLLAMA_BASE_URL. Never live while an eval run is going")
    parser.add_argument("--examples", choices=["on", "off"], default="on",
                        help="live: retrieve worked examples for each question (default: on; needs chromadb)")
    parser.add_argument("--replay-runs", nargs="*", help="replay only these runs (directory names in data/experiments)")
    parser.add_argument("--speed", type=float, default=0.1, help="replay: the share of each step's recorded time to wait")
    parser.add_argument("--card-earnings", choices=["on", "off"], default=None,
                        help="show career earnings on stat cards (default: on, or the CARD_EARNINGS environment"
                             " variable; the flag wins)")
    parser.add_argument("--preview", action="store_true",
                        help="serve /api/preview/lifetime/{player_id}, for app/dev/compare_card.py (development only)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.mode == "live":
        source = live_source(args.examples == "on", parser.error)
        print(f"Live mode: {source.header['model']}, examples {args.examples}. Loading the players' names...")
    else:
        source = replay_source(args.replay_runs, args.speed)
        print(f"Replay mode: {len(source.index.recordings)} recordings. Loading the players' names...")
    earnings = card_earnings(args.card_earnings, os.environ.get("CARD_EARNINGS"))
    print(f"Earnings on stat cards: {'on' if earnings else 'off'}.")
    tools = runner.ProgressTools()
    import uvicorn
    uvicorn.run(create_app(source, tools, earnings=earnings, preview=args.preview), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
