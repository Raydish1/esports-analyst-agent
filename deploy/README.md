# The hosted server on Fly.io

Always on, with no laptop or GPU: the MCP server at `/mcp` (the 18 tools and the stat card images) and the demo page,
which plays the recorded answers to its sample questions. Live questions need a model, so they stay on the tunnel
(docs/public-demo.md).

What runs: `app/server/main.py --mode hosted` (main.hosted_app) in the `Dockerfile`'s image, on one machine
(`fly.toml`: shared CPU, 1 GB, always on; about $6 a month with the volume). The data is never in the image or in git
(DATA.md): it's a bundle (`deploy/bundle.py`) uploaded to the machine's volume, which `deploy/start.sh` unpacks.

## The first deploy

From this folder's repository root (the web-app worktree), with flyctl (`iwr https://fly.io/install.ps1 -useb | iex`
in PowerShell, if it isn't installed):

1. `fly auth login`
2. `fly apps create brawlhalla-cortex`. If the name is taken, pick another and put it in `fly.toml` (`app = ...`).
3. `fly volumes create cortex_data --region ord --size 2 --yes`
4. `fly deploy --ha=false` builds the image on Fly's builders and starts the machine. It waits for data.
5. `py -3.14 deploy/bundle.py` writes `data/deploy/bundle.tgz` (about 94 MB).
6. `fly ssh sftp shell`, then at its prompt `put data/deploy/bundle.tgz /data/bundle.tgz`, then Ctrl+D.
7. `fly apps restart brawlhalla-cortex`. It unpacks the bundle and starts; loading the players' names takes about
   20 s.

Then the page is `https://brawlhalla-cortex.fly.dev`, and the MCP server `https://brawlhalla-cortex.fly.dev/mcp`
(Claude Code: `claude mcp add --transport http cortex https://brawlhalla-cortex.fly.dev/mcp`; claude.ai: a custom
connector with that address).

## After a new event

Build it locally (docs/public-demo.md's "next tournament" steps), then steps 5 to 7 again: the new bundle replaces the
data. After a code change, `fly deploy` alone.

## Checking on it

`fly status`, `fly logs`, and `https://brawlhalla-cortex.fly.dev/healthz` (`{"ok": true}` once it's serving).
