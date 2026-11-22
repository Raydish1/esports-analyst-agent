# The public demo

The web app can be opened to anyone, and its tools offered to other people's models as an MCP server, from a machine
that runs the app, through a Cloudflare tunnel. DATA.md records the data sources' permission for a public deployment.

## Start it

On the machine that runs the app (it needs the Ollama server, `OLLAMA_BASE_URL` in `.env`, and the live build in
`data/db`), from the repository's folder:

```
powershell -ExecutionPolicy Bypass -File app/dev/public.ps1
```

It starts the app in live mode with `--public --mcp` on port 8001, then a Cloudflare quick tunnel to it, and prints the
public address (`https://<random words>.trycloudflare.com`). Ctrl+C stops both. The address changes on every start; a
fixed one (`cortex.<your domain>`) needs a free Cloudflare account and a domain, set up once as a named tunnel.

Once, before the first start: `winget install --id Cloudflare.cloudflared`.

## What public mode changes

- No paid model: only the local qwen3:30b is offered, so no visitor spends the Anthropic key.
- Earnings: only the Stats API's figures (DATA.md's permission covers them; the Esports Earnings snapshot's don't).
- At most 30 questions a visitor an hour (by the address Cloudflare reports), on top of the worker's limits (one
  question at a time on the one GPU, 20 waiting, 50 conversations).
- The model server's address never reaches the page (as always).

## The MCP server

The app serves the project's tools at `/mcp/` (Streamable HTTP): the agent's 14 tools (resolve_player,
resolve_event, run_sql and the templates) and four card tools that return the broadcast stat cards as images
(player_card, head_to_head_card, partnership_card, teams_card). A connecting model gets instructions on the data's
counting rules; the agent's own checks (number, name and no-tool checks) live in its loop, so that model's answers are
its own.

Connect a client to `https://<tunnel address>/mcp/`:
- Claude Code: `claude mcp add --transport http cortex https://<tunnel address>/mcp/`
- claude.ai: Settings, Connectors, add a custom connector with that address.
- Locally, without a tunnel: `http://127.0.0.1:8001/mcp/` with the app started with `--mcp`.

The card tools draw with the installed Edge (Playwright, `channel="msedge"`); `pip install -r requirements.txt` brings
the Python packages.
