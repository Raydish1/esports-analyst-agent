"""The project's tools as an MCP server, so another model (Claude, or any MCP client) can answer Brawlhalla questions
with them: mounted at /mcp by main.py (--mcp), over Streamable HTTP.

Tools:
- the agent's own 14 (react.TOOLS): resolve_player, resolve_event, run_sql (read-only, on the views) and the
  templates, with the schemas and descriptions the agent's model gets, run by react.Tools.call;
- four card tools, the web app's broadcast graphics as images (figures.Cards, drawn by card.html in a headless browser):
  player_card, head_to_head_card, partnership_card, teams_card. Each also returns the line the web app tells its
  agent (figures.summary), so the model can say what the card shows.

What it can't bring: the agent's checks (the number check, the name checks, the no-tool check) live in its loop
(react.Conversation), not in the tools, so the connecting model's answers are its own.

The data is the live build's, shown publicly under DATA.md's permission; the database itself never leaves the server.
"""

import asyncio
import base64
import io
import json
import random
from contextlib import asynccontextmanager

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

import figures
import react

BACKGROUNDS = ("savanna", "islands", "temple", "forest", "arena")  # art/backgrounds, as broadcast.js lists them
INSTRUCTIONS = """Brawlhalla esports results: official events only (from February 2017 to the newest results in the
data), from the official Esports Stats API, start.gg and Challengermode.

How to use the tools:
- Look players up with resolve_player and events with resolve_event first; every other tool takes the player_id it
  returns, never a name. If resolve_player isn't confident, ask the user which player they mean.
- Prefer a template (player_results, head_to_head, team_results, team_head_to_head, event_results, rank_players,
  rank_pairs, player_sets, dominant_wins, upsets, power_rankings) to run_sql: each applies the data's counting rules.
  run_sql runs one read-only SELECT on the views, whose definitions document their rules.
- Answer only from what the tools return; never count or rank rows by reading them, and say what was counted.

The counting rules: a medal is a 1st, 2nd or 3rd place; crew battles count as 1v1; side formats (3v3, Kung Foot...)
count toward neither 1v1 nor 2v2; a missing earnings figure is not $0; a cancelled event wasn't held; say "official
events", not "majors".

For a graphic, call player_card, head_to_head_card, partnership_card or teams_card with player_ids: each returns the
broadcast-style stat card as an image, and a line of what it shows."""

CARD_TOOLS = [
    types.Tool(name="player_card", description="One player's lifetime stat card as an image (earnings, medals, top 8s"
               " and top 32s, recent placements), and a line of what it shows. mode: '1v1', '2v2', or both (default).",
               inputSchema={"type": "object", "properties": {
                   "player_id": {"type": "integer", "description": "from resolve_player"},
                   "mode": {"type": "string", "enum": ["1v1", "2v2", "1v1 and 2v2"]}}, "required": ["player_id"]}),
    types.Tool(name="head_to_head_card", description="Two players' head-to-head card as an image (each one's lifetime"
               " figures and their record against each other), followed by their sets as a second image when they've"
               " met, and a line of what they show.",
               inputSchema={"type": "object", "properties": {
                   "player_id": {"type": "integer"}, "opponent_id": {"type": "integer"},
                   "mode": {"type": "string", "enum": ["1v1", "2v2", "1v1 and 2v2"]}},
                   "required": ["player_id", "opponent_id"]}),
    types.Tool(name="partnership_card", description="A 2v2 partnership's card as an image: each partner's figures and"
               " their results together.", inputSchema={"type": "object", "properties": {
                   "player_id": {"type": "integer"}, "partner_id": {"type": "integer"}},
                   "required": ["player_id", "partner_id"]}),
    types.Tool(name="teams_card", description="Two 2v2 teams' card as an image (the four players and the teams' record"
               " against each other), followed by their sets when they've met.",
               inputSchema={"type": "object", "properties": {
                   "player_id": {"type": "integer"}, "partner_id": {"type": "integer"},
                   "opponent_id": {"type": "integer"}, "opponent_partner_id": {"type": "integer"}},
                   "required": ["player_id", "partner_id", "opponent_id", "opponent_partner_id"]}),
]


class Renderer:
    """Draws cards with card.html in one headless browser (Playwright, the installed Edge or Chrome), launched on first
    use. Each card becomes a 1280x720 JPEG, small enough for a model's context."""

    def __init__(self, base_url, channel="msedge"):
        self.base_url, self.channel, self.page, self.lock = base_url.rstrip("/"), channel, None, asyncio.Lock()

    async def start(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(channel=self.channel)
        self.page = await self.browser.new_page(viewport={"width": 1920, "height": 1080})
        await self.page.goto(f"{self.base_url}/card.html")
        await self.page.wait_for_selector("body[data-ready=true]")

    async def draw(self, card, mode=None):
        from PIL import Image
        async with self.lock:  # one page, one card at a time
            if self.page is None:
                await self.start()
            await self.page.evaluate("([card, mode]) => window.draw(card, mode)", [card, mode])
            await self.page.wait_for_timeout(150)
            png = await self.page.locator("#out").screenshot(type="png")
        out = io.BytesIO()
        Image.open(io.BytesIO(png)).convert("RGB").resize((1280, 720), Image.LANCZOS).save(out, "JPEG", quality=85)
        return base64.b64encode(out.getvalue()).decode()

    async def close(self):
        if self.page is not None:
            await self.browser.close()
            await self.playwright.stop()


def build(path, base_url, earnings_sources=("Stats API",)):
    """The MCP server on the database at path, its cards drawn from the app at base_url. Returns (asgi app, lifespan)."""
    tools = react.Tools(path)  # its own, so its calls never show up in a web visitor's progress
    cards = figures.Cards(tools, sources=earnings_sources)
    renderer = Renderer(base_url)
    server = Server("brawlhalla-cortex", instructions=INSTRUCTIONS)
    offered = [types.Tool(name=t["function"]["name"], description=t["function"]["description"],
                          inputSchema=t["function"]["parameters"],
                          annotations=types.ToolAnnotations(readOnlyHint=True, openWorldHint=False))
               for t in react.TOOLS] + CARD_TOOLS
    names = {t.name for t in offered}

    @server.list_tools()
    async def list_tools():
        return offered

    async def images(found, mode=None):
        content = []
        for card in found:
            card["background"] = random.choice(BACKGROUNDS)
            content.append(types.ImageContent(type="image", data=await renderer.draw(card, mode), mimeType="image/jpeg"))
        line = figures.summary(found)
        return content + [types.TextContent(type="text", text=line or "No card: no such players or no results.")]

    @server.call_tool()
    async def call_tool(name, arguments):
        arguments = arguments or {}
        if name not in names:
            return [types.TextContent(type="text", text=json.dumps({"error": f"there is no tool named {name!r}"}))]
        try:
            if name == "player_card":
                one = await anyio.to_thread.run_sync(cards.lifetime, int(arguments["player_id"]))
                found = [{"kind": "lifetime", "player": one, "scope": cards.scope([one])}] if one else []
                return await images(found, arguments.get("mode"))
            if name == "head_to_head_card":
                found = await anyio.to_thread.run_sync(cards.head_to_head, int(arguments["player_id"]),
                                                       int(arguments["opponent_id"]))
                return await images(found, arguments.get("mode"))
            if name == "partnership_card":
                one = await anyio.to_thread.run_sync(cards.team, int(arguments["player_id"]), int(arguments["partner_id"]))
                return await images([one] if one else [])
            if name == "teams_card":
                found = await anyio.to_thread.run_sync(
                    cards.teams, (int(arguments["player_id"]), int(arguments["partner_id"])),
                    (int(arguments["opponent_id"]), int(arguments["opponent_partner_id"])))
                return await images(found or [])
            out = await anyio.to_thread.run_sync(tools.call, name, arguments)
            out.pop("sql", None) if isinstance(out, dict) and name != "run_sql" else None
            return [types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False, default=str))]
        except (KeyError, TypeError, ValueError) as e:
            return [types.TextContent(type="text", text=json.dumps({"error": f"bad arguments for {name}: {e}"}))]

    manager = StreamableHTTPSessionManager(app=server, stateless=True, json_response=True)

    async def asgi(scope, receive, send):
        await manager.handle_request(scope, receive, send)

    @asynccontextmanager
    async def lifespan():
        async with manager.run():
            try:
                yield
            finally:
                await renderer.close()

    return asgi, lifespan
