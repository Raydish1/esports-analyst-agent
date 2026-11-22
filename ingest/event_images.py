"""Fetch each official event's logo for the stat cards' recent placements row.

    python ingest/event_images.py --pilot     the newest 5 events of each platform, and Raydish's latest 5 in each mode
    python ingest/event_images.py --all       every official event on start.gg or Challengermode
    python ingest/event_images.py status      how many events have a logo, how many don't, how many are left

The logo is the host tournament's: start.gg's tournament `profile` image (square, 500x500; the Brawlhalla events
themselves have none, so a tournament's 1v1 and 2v2 events share it), and Challengermode's `links.logo` at the size
LOGO_SIZE. Checked by hand on CEO 2024 and Autumn Championship NA 2026 (2026-11-22). The three Pro Series finals have no
platform page; they, and any event whose tournament has no logo, get the card's drawn badge.

The queries go through the existing clients, so every response is cached (data/raw/cache) with the usual gaps between
requests (1 s on start.gg, 3.5 s on Challengermode), and a rerun reads them from the cache. The images go to
data/raw/event_images/ and the list to data/curated/event_images.csv (event_id, platform, file, width, height,
source_url, fetched_at), which the web app reads. A rerun skips an image already on disk, so the run can be stopped
and started again. Nothing here is committed: it's all under data/ (the Stats API's terms, CLAUDE.md).

Events come from the live build (data/db/current.json).
"""

import argparse
import csv
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from cache import ROOT

IMAGES = ROOT / "data" / "raw" / "event_images"
LIST = ROOT / "data" / "curated" / "event_images.csv"
FIELDS = ["event_id", "platform", "file", "width", "height", "source_url", "fetched_at"]
LOGO_SIZE = "EXTRA_LARGE"  # Challengermode's LogoSize: SMALL, MEDIUM (64x64), LARGE, EXTRA_LARGE
PILOT = 5  # events per platform in --pilot
PILOT_PLAYER = 160000  # Raydish: the pilot also takes his latest PILOT events in each mode, for the card's preview
USER_AGENT = "esports-analyst-agent/0.1 (personal research)"
DOWNLOAD_GAP = 0.5  # seconds between image downloads
TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}

SGG_IMAGES = """
query TournamentImages($slug: String!) { tournament(slug: $slug) { id name images { type url width height ratio } } }"""
CM_LOGO = """
query TournamentLogo($id: UUID!, $size: LogoSize!) { tournament(tournamentId: $id) { id name
  links { logo(size: $size) { url width height } } } }"""


def live_build():
    pointer = json.loads((ROOT / "data" / "db" / "current.json").read_text(encoding="utf-8"))
    return ROOT / "data" / "db" / pointer["file"]


def events(db_path):
    """[(event_id, platform, key, start_time)], newest first: key is the start.gg tournament slug or the Challengermode
    tournament UUID. Events with no platform page (the Pro Series finals) are left out."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = db.execute(
            "SELECT e.event_id, s.platform, CASE s.platform WHEN 'startgg' THEN e.sgg_tournament_slug"
            " ELSE s.platform_event_id END, e.start_time FROM events e JOIN event_sources s ON s.event_id = e.event_id"
            " WHERE e.is_official = 1 AND s.platform IN ('startgg', 'challengermode') ORDER BY e.start_time DESC").fetchall()
    finally:
        db.close()
    return [r for r in rows if r[2]]


def player_latest(db_path, player_id):
    """A player's latest PILOT official events in each mode, as event IDs."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {r[0] for mode in ("1v1", "2v2") for r in db.execute(
            "SELECT event_id FROM v_results WHERE player_id = ? AND mode = ? ORDER BY start_date DESC LIMIT ?",
            (player_id, mode, PILOT))}
    finally:
        db.close()


def pick(found, pilot, also=()):
    """Every event, or for the pilot the newest PILOT events of each platform and the events in `also`."""
    if not pilot:
        return found
    out, seen = [], {"startgg": 0, "challengermode": 0}
    for row in found:
        if seen[row[1]] < PILOT or row[0] in also:
            seen[row[1]] += row[0] not in also
            out.append(row)
    return out


def logo_of(platform, data):
    """(url, width, height) of a tournament's logo from its query's data, or None."""
    t = (data or {}).get("tournament") or {}
    if platform == "startgg":
        image = next((i for i in t.get("images") or [] if i.get("type") == "profile" and i.get("url")), None)
    else:
        image = ((t.get("links") or {}).get("logo")) or None
        image = image if image and image.get("url") else None
    return (image["url"], image.get("width"), image.get("height")) if image else None


def file_name(key, content_type):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return safe + TYPES.get((content_type or "").split(";")[0].strip(), ".img")


def download(url, key):
    """The image at url saved under IMAGES, named for its tournament: (file name, whether it was fetched now)."""
    existing = [p for p in IMAGES.glob(file_name(key, "")[:-4] + ".*")] if IMAGES.exists() else []
    if existing:
        return existing[0].name, False
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        body, content_type = response.read(), response.headers.get("Content-Type")
    if (content_type or "").split(";")[0].strip() not in TYPES:
        raise ValueError(f"not an image: {content_type}")
    IMAGES.mkdir(parents=True, exist_ok=True)
    name = file_name(key, content_type)
    (IMAGES / name).write_bytes(body)
    return name, True


def read_list():
    if not LIST.exists():
        return {}
    with LIST.open(encoding="utf-8", newline="") as f:
        return {r["event_id"]: r for r in csv.DictReader(f)}


def write_list(rows):
    LIST.parent.mkdir(parents=True, exist_ok=True)
    with LIST.open("w", encoding="utf-8", newline="") as f:
        out = csv.DictWriter(f, fieldnames=FIELDS)
        out.writeheader()
        for event_id in sorted(rows):
            out.writerow({k: rows[event_id].get(k, "") for k in FIELDS})


def run(pilot):
    from challengermode import Challengermode
    from startgg import StartGG
    clients = {"startgg": StartGG(), "challengermode": Challengermode()}
    build = live_build()
    todo = pick(events(build), pilot, player_latest(build, PILOT_PLAYER) if pilot else ())
    rows = read_list()
    by_tournament = {}  # one query per tournament: a start.gg tournament's events share its logo
    counts = {"logo": 0, "none": 0, "failed": 0}
    for i, (event_id, platform, key, _) in enumerate(todo, 1):
        if (platform, key) not in by_tournament:
            try:
                if platform == "startgg":
                    data = clients[platform].query("TournamentImages", SGG_IMAGES, {"slug": key})
                else:
                    data = clients[platform].query("TournamentLogo", CM_LOGO, {"id": key, "size": LOGO_SIZE})
                by_tournament[(platform, key)] = logo_of(platform, data)
            except Exception as e:  # noqa: BLE001  an API error is reported, and the event gets the drawn badge
                print(f"  {event_id}: query failed: {e}", file=sys.stderr)
                by_tournament[(platform, key)] = "failed"
        logo = by_tournament[(platform, key)]
        if logo == "failed":
            counts["failed"] += 1
            continue
        if logo is None:
            counts["none"] += 1
            rows[event_id] = {"event_id": event_id, "platform": platform, "file": "", "fetched_at": now()}
            continue
        url, width, height = logo
        try:
            name, fetched = download(url, f"{platform}-{key}")
            if fetched:
                time.sleep(DOWNLOAD_GAP)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            print(f"  {event_id}: download failed: {e}", file=sys.stderr)
            counts["failed"] += 1
            continue
        counts["logo"] += 1
        rows[event_id] = {"event_id": event_id, "platform": platform, "file": name, "width": width, "height": height,
                          "source_url": url.split("?")[0], "fetched_at": now()}
        if i % 25 == 0:
            write_list(rows)
            print(f"{i} of {len(todo)} events", flush=True)
    write_list(rows)
    print(f"{len(todo)} events: {counts['logo']} with a logo, {counts['none']} without, {counts['failed']} failed"
          f" (rerun to retry). Requests made: start.gg {clients['startgg'].requests_made},"
          f" Challengermode {clients['challengermode'].requests_made}. List: {LIST.relative_to(ROOT)}")


def status():
    found = events(live_build())
    rows = read_list()
    have = sum(1 for e in found if rows.get(e[0], {}).get("file"))
    none = sum(1 for e in found if e[0] in rows and not rows[e[0]].get("file"))
    print(f"{len(found)} events with a platform page: {have} with a logo, {none} without one, {len(found) - have - none}"
          " not fetched yet.")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", choices=["status"])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pilot", action="store_true", help=f"the newest {PILOT} events of each platform")
    group.add_argument("--all", action="store_true", help="every official event with a platform page")
    args = parser.parse_args(argv)
    if args.command == "status":
        return status()
    if not (args.pilot or args.all):
        parser.error("say --pilot or --all (or status)")
    run(pilot=args.pilot)


if __name__ == "__main__":
    main()
