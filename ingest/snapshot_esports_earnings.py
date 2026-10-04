"""One-time snapshot of Esports Earnings' Brawlhalla top-players list.

This is not part of the regular crawl. It fetches the list pages once, keeps the raw
HTML in data/raw/esportsearnings/ (git-ignored), and writes the parsed table to
curation/esports_earnings_snapshot.csv: one row per player with their Brawlhalla
total in USD. The builder uses it as the career-earnings fallback for players
without a Stats API figure (docs/schema-proposal.md §6a).

Pages already saved are reused, so re-running only re-parses unless --refresh is
given. The page also shows real names; they are never written out.

Usage: python ingest/snapshot_esports_earnings.py [--refresh]
"""

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "esportsearnings"
MANIFEST = RAW_DIR / "_manifest.json"
CSV_PATH = ROOT / "curation" / "esports_earnings_snapshot.csv"
BASE = "https://www.esportsearnings.com"
FIRST_PAGE = "/games/443-brawlhalla/top-players"  # Brawlhalla is game 443 on the site
NEXT_PAGES = re.compile(r'href="(/games/443-brawlhalla/top-players-x(\d+))"')
USER_AGENT = "esports-analyst-agent/0.1 (personal research project)"
MIN_GAP = 2.0  # seconds between requests
MAX_PAGES = 20  # safety stop; the site lists the top 500 (5 pages)
HEADER = ["Player ID", "Player Name", "Total (Game)", "Total (Overall)", "% of Total"]
MONEY = re.compile(r"\$([\d,]+\.\d{2})")
PLAYER_LINK = re.compile(r"^/players/(\d+)-")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # report 3xx as-is instead of following it


class Fetcher:
    """GETs one URL at a time, at least `gap` seconds apart, without following redirects."""

    def __init__(self, gap):
        self.gap = gap
        self.last = 0.0
        self.opener = urllib.request.build_opener(NoRedirect)

    def get(self, url):
        delay = self.gap - (time.monotonic() - self.last)
        if delay > 0:
            time.sleep(delay)
        self.last = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with self.opener.open(req, timeout=60) as res:
                return res.status, res.headers, res.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()


def check_robots(fetcher):
    """Return a robots parser (or None if robots.txt is unavailable) and a note for the manifest.

    Exits if robots.txt restricts access or can't be reached. On 2026-10-04 it redirected
    to itself, so it was unavailable. Under RFC 9309, a robots.txt not reached within five
    redirects may be treated as unavailable, which permits crawling, and the snapshot was
    approved on that basis.
    """
    url, seen = BASE + "/robots.txt", set()
    for _ in range(6):  # the first request plus up to five redirects
        seen.add(url)
        status, headers, body = fetcher.get(url)
        location = headers.get("Location") if 300 <= status < 400 else None
        if not location:
            break
        url = urllib.parse.urljoin(url, location)
        if url in seen:
            return None, f"unavailable: HTTP {status} redirects to itself ({url})"
    else:
        return None, "unavailable: more than five redirects"
    if status == 200:
        rules = urllib.robotparser.RobotFileParser()
        rules.parse(body.decode("utf-8", "replace").splitlines())
        delay = rules.crawl_delay(USER_AGENT)
        if delay and delay > fetcher.gap:
            fetcher.gap = float(delay)
        return rules, f"read (HTTP 200, crawl delay {delay})"
    if status in (401, 403) or status >= 500:
        sys.exit(f"robots.txt returned HTTP {status}; treating the site as off limits")
    return None, f"unavailable: HTTP {status}"


def page_file(path):
    offset = int(path.rsplit("-x", 1)[1]) if "-x" in path else 0
    return f"top-players_p{offset // 100 + 1:03d}.html"


def load_manifest():
    if not MANIFEST.exists():
        return {"pages": []}
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"pages": data}  # the first page was saved by hand


def fetch_pages(refresh):
    """Fetch every list page not saved yet, following the page links on each one."""
    manifest = load_manifest()
    saved = {p["file"] for p in manifest["pages"]} if not refresh else set()
    fetcher = Fetcher(MIN_GAP)
    rules, note = check_robots(fetcher)
    manifest["robots"] = {"note": note, "checked_at": now_iso()}
    print("robots.txt:", note)
    queue, done = [FIRST_PAGE], set()
    while queue and len(done) < MAX_PAGES:
        path = queue.pop(0)
        done.add(path)
        name, url = page_file(path), BASE + path
        if name not in saved:
            if rules and not rules.can_fetch(USER_AGENT, url):
                sys.exit(f"robots.txt disallows {url}")
            status, headers, body = fetcher.get(url)
            if status != 200:
                sys.exit(f"{url} returned HTTP {status}")
            (RAW_DIR / name).write_bytes(body)
            manifest["pages"] = [p for p in manifest["pages"] if p["file"] != name]
            manifest["pages"].append({"file": name, "url": url, "status": status,
                                      "content_type": headers.get("Content-Type"), "bytes": len(body),
                                      "fetched_at": now_iso()})
            print(f"fetched {url} ({len(body)} bytes)")
        html = (RAW_DIR / name).read_text(encoding="utf-8")
        for link, _ in sorted(set(NEXT_PAGES.findall(html)), key=lambda m: int(m[1])):
            if link not in done and link not in queue:
                queue.append(link)
    for p in manifest["pages"]:
        p["sha256"] = hashlib.sha256((RAW_DIR / p["file"]).read_bytes()).hexdigest()
    manifest["pages"].sort(key=lambda p: p["file"])
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


class ListTable(HTMLParser):
    """Collects the rows of the page's detail_list_table as lists of {text, links} cells."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0  # > 0 while inside the table
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and (self.depth or "detail_list_table" in (attrs.get("class") or "")):
            self.depth += 1
        elif self.depth and tag == "tr":
            self.row = []
        elif self.depth and tag in ("td", "th"):
            self.cell = {"text": "", "links": []}
        elif self.cell is not None and tag == "a":
            self.cell["links"].append(attrs.get("href") or "")

    def handle_endtag(self, tag):
        if self.depth and tag == "table":
            self.depth -= 1
        elif self.depth and tag in ("td", "th") and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
        elif self.depth and tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"] += data


def parse_page(path, url, as_of):
    table = ListTable()
    table.feed(path.read_text(encoding="utf-8"))
    header, *rows = table.rows
    if [c["text"].strip() for c in header[1:]] != HEADER:
        sys.exit(f"{path.name}: unexpected table header {[c['text'].strip() for c in header]}")
    out = []
    for cells in rows:
        rank, player, _real_name, game_total, overall_total, _share = cells  # real names are dropped
        player_id = next((m.group(1) for m in map(PLAYER_LINK.match, player["links"]) if m), None)
        game, overall = MONEY.fullmatch(game_total["text"].strip()), MONEY.fullmatch(overall_total["text"].strip())
        if not (player_id and game and overall and rank["text"].strip().endswith(".")):
            sys.exit(f"{path.name}: can't parse row {[c['text'].strip() for c in cells]}")
        out.append({"rank": int(rank["text"].strip().rstrip(".")),
                    "handle": " ".join(player["text"].split()),
                    "total_usd": game.group(1).replace(",", ""),
                    "source_url": url,
                    "as_of": as_of,
                    "ee_player_id": int(player_id),
                    "_overall": overall.group(1).replace(",", "")})
    return out


def check(rows):
    """Fail loudly on anything that suggests a parsing error."""
    ranks = [r["rank"] for r in rows]
    totals = [float(r["total_usd"]) for r in rows]
    ids = [r["ee_player_id"] for r in rows]
    problems = []
    if ranks != sorted(ranks) or ranks[0] != 1:
        problems.append("ranks are not ascending from 1")
    if any(b > a for a, b in zip(totals, totals[1:])):
        problems.append("totals are not in descending order")
    if len(set(ids)) != len(ids):
        problems.append("a player appears twice")
    if any(float(r["total_usd"]) > float(r["_overall"]) for r in rows):
        problems.append("a Brawlhalla total exceeds the player's all-games total")
    if problems:
        sys.exit("; ".join(problems))


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="fetch every page again")
    args = parser.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = fetch_pages(args.refresh)
    rows = []
    for page in manifest["pages"]:
        rows += parse_page(RAW_DIR / page["file"], page["url"], page["fetched_at"][:10])
    rows.sort(key=lambda r: r["rank"])
    check(rows)
    fields = ["rank", "handle", "total_usd", "source_url", "as_of", "ee_player_id"]
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows from {len(manifest['pages'])} pages to {CSV_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
