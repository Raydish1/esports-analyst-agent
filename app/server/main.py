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
    GET  /api/jobs/{id}/poll?after=N            the same events as JSON, waiting up to POLL_WAIT s for one: for a
                                                tunnel that holds streams back (a Cloudflare quick tunnel does)
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
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
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
POLL_WAIT = 2  # seconds a poll waits for a new event before answering with none
PER_VISITOR = 30  # public mode: questions a visitor may ask in an hour (by the address the tunnel reports)
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


class Opening(BaseModel):
    model: str | None = Field(default=None, max_length=40)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=500)


def visitor(request):
    """Who asked: the address Cloudflare's tunnel reports (CF-Connecting-IP), else the one that connected."""
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


class Limiter:
    """At most `most` questions per visitor in any hour."""

    def __init__(self, most=PER_VISITOR, window=3600, clock=None):
        import time
        self.most, self.window, self.clock, self.asked = most, window, clock or time.monotonic, {}

    def allow(self, who):
        now = self.clock()
        recent = [t for t in self.asked.get(who, []) if now - t < self.window]
        if len(recent) >= self.most:
            self.asked[who] = recent
            return False
        self.asked[who] = recent + [now]
        return True


def create_app(source, tools, worker=None, examples=EXAMPLES, static=STATIC, earnings=True, preview=False, cards=None,
               public=False, mcp=None):
    """The app around one source of models (runner.Replay or runner.Live) and one shared runner.ProgressTools.
    public: the page is open to anyone (a tunnel): each visitor's questions are limited (Limiter), and cards show only
    the Stats API's earnings. mcp: an MCP server app (mcp_server.py) mounted at /mcp.
    earnings: whether stat cards show career earnings. preview: serve GET /api/preview/lifetime/{player_id}, a card
    without a question, for rendering and comparing cards (app/dev/compare_card.py); off unless asked for."""
    cards = cards or figures.Cards(tools, earnings=earnings, sources=("Stats API",) if public else None)
    limiter = Limiter() if public else None
    worker = worker or workers.Worker(lambda **o: runner.Agent(tools, source, cards, **o)).start()
    models = source.choices() if hasattr(source, "choices") else []
    offered = [q for q in examples if source.mode != "replay" or source.index.has(q)]
    asgi, lifespan = mcp if mcp is not None else (None, None)
    app = FastAPI(title="Brawlhalla esports analyst", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=(lambda _: lifespan()) if lifespan else None)
    app.state.worker = worker

    @app.get("/api/info")
    def info():
        return {"mode": source.mode, "examples": offered, "models": models}

    @app.post("/api/conversations")
    def conversation(body: Opening | None = None):
        chosen = body.model if body else None
        if chosen and chosen not in {m["id"] for m in models}:
            raise HTTPException(422, f"No model {chosen!r} here.")
        try:
            return {"conversation_id": (worker.open(backend=chosen) if chosen else worker.open()).id}
        except workers.Full as e:
            raise HTTPException(503, str(e))

    @app.post("/api/conversations/{conversation_id}/questions")
    def ask(conversation_id: str, body: Question, request: Request):
        if limiter and not limiter.allow(visitor(request)):
            raise HTTPException(429, f"That's {PER_VISITOR} questions this hour, the most one visitor can ask. Try again later.")
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

    @app.get("/api/jobs/{job_id}/poll")
    async def poll(job_id: str, after: int = 0):
        """The job's events from number after on, as soon as there is one or after POLL_WAIT seconds; next is the
        after to ask with next time, and finished says the job has no more."""
        job = worker.job(job_id)
        if job is None:
            raise HTTPException(404, "No such question.")
        found, finished = await asyncio.to_thread(job.wait, max(after, 0), POLL_WAIT)
        return {"events": [event for _, event in found], "next": max(after, 0) + len(found),
                "finished": finished and max(after, 0) + len(found) >= len(job.events)}

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

        @app.get("/api/preview/team/{player_id}/{partner_id}")
        def preview_team(player_id: int, partner_id: int):
            found = cards.team(player_id, partner_id)
            if found is None:
                raise HTTPException(404, "No such players.")
            return found

        @app.get("/api/preview/teams/{a}/{b}/{c}/{d}")
        def preview_teams(a: int, b: int, c: int, d: int, part: int = 0):
            found = cards.teams((a, b), (c, d))
            if len(found) <= part:
                raise HTTPException(404, "No such players." if not found else "No sets between these teams.")
            return found[part]

        @app.get("/api/preview/event/{event_id:path}")
        def preview_event(event_id: str):
            return cards.event_sets({"event_id": event_id, "name": "Preview event", "date": None})

        @app.get("/api/preview/leaderboard")
        def preview_leaderboard(name: str, args: str = "{}"):
            """A list tool's leaderboard card: ?name=rank_players&args={"by": "wins", "top": 5}."""
            from templates import TEMPLATES
            arguments = json.loads(args)
            card = cards.leaderboard(name, arguments, TEMPLATES[name].call(tools, arguments)) if name in TEMPLATES else None
            if card is None:
                raise HTTPException(404, "No leaderboard for this call.")
            return card

        @app.get("/api/preview/sets/{player_id}/{opponent_id}")
        def preview_sets(player_id: int, opponent_id: int):
            found = cards.head_to_head(player_id, opponent_id)
            if len(found) < 2:
                raise HTTPException(404, "No sets between these players.")
            return found[1]

    @app.get("/api/event-image")
    def event_image(id: str):
        return event_logo(cards, id)

    @app.middleware("http")
    async def revalidate(request, call_next):
        """The page's files are checked with the server on every load (an unchanged file costs a 304), so a page
        never keeps running scripts older than the server's."""
        if request.scope["path"] == "/mcp":  # the MCP server's address works with or without its trailing slash
            request.scope["path"], request.scope["raw_path"] = "/mcp/", b"/mcp/"
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    if asgi is not None:
        app.mount("/mcp", asgi)
    if static.exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="static")
    return app


def event_logo(cards, event_id):
    """An event's logo (figures.EventImages), as a 256-pixel WebP made once from the fetched image (data/raw/
    event_images; the hosted server has only the thumbs)."""
    name = cards.images.file(event_id)
    if not name:
        raise HTTPException(404, "No logo for this event.")
    source = figures.ROOT / "data" / "raw" / "event_images" / name
    thumb = source.parent / "thumbs" / (source.stem + ".webp")
    if not thumb.exists():
        if not source.exists():
            raise HTTPException(404, "No logo for this event.")
        from PIL import Image
        thumb.parent.mkdir(exist_ok=True)
        with Image.open(source) as im:
            im = im.convert("RGBA")
            im.thumbnail((256, 256))
            im.save(thumb, "WEBP", quality=88)
    return FileResponse(thumb, media_type="image/webp", headers={"Cache-Control": "max-age=86400"})


def hosted_app(path, base_url, static=STATIC):
    """The hosted server (Fly.io, deploy/): no model, so the MCP server at /mcp, the event logos, and the page, which
    finds no /api/info and plays the demo's recorded answers (app.js, offline). Stats API earnings only."""
    import mcp_server
    tools = react.Tools(path)
    cards = figures.Cards(tools, sources=("Stats API",))
    asgi, lifespan = mcp_server.build(path, base_url, earnings_sources=("Stats API",), tools=tools)
    app = FastAPI(title="Brawlhalla esports analyst", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lambda _: lifespan())

    @app.get("/api/event-image")
    def event_image(id: str):
        return event_logo(cards, id)

    @app.get("/healthz")
    def health():
        return {"ok": True}

    @app.middleware("http")
    async def slash(request, call_next):
        if request.scope["path"] == "/mcp":
            request.scope["path"], request.scope["raw_path"] = "/mcp/", b"/mcp/"
        response = await call_next(request)
        if not request.url.path.startswith(("/api/", "/mcp")):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.mount("/mcp", asgi)
    app.mount("/", StaticFiles(directory=static, html=True), name="static")
    return app


def replay_source(runs=None, speed=0.1):
    index = replay.Index(replay.recordings(react.RAW, runs=set(runs) if runs else None))
    if not index.recordings:
        sys.exit("No recordings to replay" + (f" in the runs {', '.join(runs)}." if runs else "."))
    return runner.Replay(index, speed=speed)


def live_source(examples, fail, public=False):
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
    backends = {"qwen": runner.Backend(f"{react.MODEL} (local)", lambda: react.chat,
                                       {"model": react.MODEL, "think": True, "seed": 0})}
    try:
        import anthropic_chat  # never offered in public mode: it costs the key's owner per question
        if not public and anthropic_chat.anthropic is not None and os.environ.get("ANTHROPIC_API_KEY"):
            backends["sonnet"] = runner.Backend(f"{anthropic_chat.MODEL} (API, paid)", anthropic_chat.AnthropicChat,
                                                {"model": anthropic_chat.MODEL, "think": True, "seed": 0})
    except ImportError:
        pass
    return runner.Live(retriever, header, react.RAW / "web", backends=backends)


def database(which):
    """The database the app reads: the live build (data/db/current.json names it), which the updater moves on as new
    events are fetched, or the frozen evaluation snapshot (eval-v1), which the evaluation's verified answers rest on."""
    if which == "eval":
        return react.SNAPSHOT
    pointer = json.loads((react.ROOT / "data" / "db" / "current.json").read_text(encoding="utf-8"))
    return react.ROOT / "data" / "db" / pointer["file"]


def card_earnings(flag, env):
    """Whether stat cards show earnings: the flag, else CARD_EARNINGS, else on."""
    value = (flag or env or "on").strip().lower()
    if value not in ("on", "off", "1", "0", "true", "false", "yes", "no"):
        sys.exit(f"CARD_EARNINGS is {value!r}: use on or off.")
    return value in ("on", "1", "true", "yes")


def main(argv=None):
    parser = argparse.ArgumentParser(description="The demo web app: the agent behind a queue, streamed to the page.")
    parser.add_argument("--mode", choices=["replay", "live", "hosted"], default="replay",
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
    parser.add_argument("--db", choices=["live", "eval"], default="live",
                        help="live: the newest published build (default), with every event fetched; eval: the frozen"
                             " eval-v1 snapshot the evaluation uses")
    parser.add_argument("--public", action="store_true",
                        help="open to anyone (behind a tunnel): no paid model, Stats API earnings only, and at most"
                             f" {PER_VISITOR} questions a visitor an hour")
    parser.add_argument("--mcp", action="store_true",
                        help="also serve the tools and stat cards as an MCP server at /mcp (mcp_server.py)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.mode == "hosted":  # no model: the MCP server and the demo page (hosted_app)
        path = database(args.db)
        print(f"Hosted mode: the MCP server at /mcp and the demo page. Database: {path}. Loading the players' names...")
        import uvicorn
        uvicorn.run(hosted_app(path, f"http://127.0.0.1:{args.port}"), host=args.host, port=args.port)
        return
    if args.mode == "live":
        source = live_source(args.examples == "on", parser.error, public=args.public)
        print(f"Live mode: {', '.join(m['label'] for m in source.choices())}, examples {args.examples}."
              " Loading the players' names...")
    else:
        source = replay_source(args.replay_runs, args.speed)
        print(f"Replay mode: {len(source.index.recordings)} recordings. Loading the players' names...")
    earnings = card_earnings(args.card_earnings, os.environ.get("CARD_EARNINGS"))
    print(f"Earnings on stat cards: {'on' if earnings else 'off'}.")
    path = database(args.db)
    print(f"Database: {path.relative_to(react.ROOT).as_posix()}.")
    if args.mode == "live":  # the transcripts say which database answered
        source.header["snapshot"] = {**source.header.get("snapshot", {}), "file": path.relative_to(react.ROOT).as_posix()}
    tools = runner.ProgressTools(path)
    import uvicorn
    mcp = None
    if args.mcp:
        import mcp_server
        mcp = mcp_server.build(path, f"http://127.0.0.1:{args.port}",
                               earnings_sources=("Stats API",) if args.public else None)
        print("MCP server at /mcp.")
    uvicorn.run(create_app(source, tools, earnings=earnings, preview=args.preview, public=args.public, mcp=mcp),
                host=args.host, port=args.port)


if __name__ == "__main__":
    main()
