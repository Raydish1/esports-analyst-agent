"""Write each player's main legend for the stat cards, from the legends crawl (stage 5).

    python ingest/legend_mains.py

A main is the legend with the most games in the latest year of crawl.LEGEND_YEARS that has
any; otherwise the all-time leader; otherwise none, and the card shows its fallback. There's no
minimum: a legend seen in one game beats the fallback (decided 2026-11-19). Ties go to more
games all time.
The latest year first is what prostats.brawlhalla.com shows, from the same API.

The file is data/curated/player_legends.csv (player_id, legend, source, games, period), which
the web app reads. Rows whose source isn't 'stats_api' were added by hand: they're kept, and
win over the API's. Legends are written as the art's slugs (RED_RAPTOR -> redraptor).
"""

import collections
import csv
import sys

from cache import ROOT
from crawl import LEGEND_YEARS
from tasks import connect

MAINS = ROOT / "data" / "curated" / "player_legends.csv"
FIELDS = ["player_id", "legend", "source", "games", "period"]


def slug(name):
    return name.lower().replace("_", "")


def mains(rows):
    """{player_id: (legend, games, period)} from (player_id, period, legend, games) rows."""
    periods = [*(str(y) for y in sorted(LEGEND_YEARS, reverse=True)), "all"]
    counts = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for pid, period, legend, games in rows:
        if period in periods:
            counts[pid][period][legend] += games
    chosen = {}
    for pid in sorted(counts):
        alltime = counts[pid]["all"]
        for period in periods:
            games = counts[pid][period]
            if games:
                legend = max(games, key=lambda name: (games[name], alltime[name], name))
                chosen[pid] = (slug(legend), games[legend], period)
                break
    return chosen


def write(chosen, path=MAINS):
    """Rewrite the file: hand rows kept, the API's mains for everyone else. Returns (hand rows, API rows)."""
    hand = []
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            hand = [r for r in csv.DictReader(f) if r.get("player_id") and (r.get("source") or "hand") != "stats_api"]
    taken = {r["player_id"].strip() for r in hand}
    api = [{"player_id": pid, "legend": legend, "source": "stats_api", "games": games, "period": period}
           for pid, (legend, games, period) in sorted(chosen.items()) if str(pid) not in taken]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        out = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        out.writeheader()
        out.writerows([{**r, "source": r.get("source") or "hand"} for r in hand] + api)
    return len(hand), len(api)


def main():
    db = connect()
    rows = db.execute("SELECT player_id, period, legend, games FROM crawl_legends").fetchall()
    fetched = db.execute("SELECT COUNT(DISTINCT CAST(substr(task_key, 9) AS INTEGER)) FROM tasks"
                         " WHERE stage = 'legends' AND status = 'done'").fetchone()[0]
    chosen = mains(rows)
    hand, api = write(chosen)
    periods = collections.Counter(period for _, _, period in chosen.values())
    print(f"{fetched} players fetched; {len(chosen)} with a main ({', '.join(f'{n} from {p}' for p, n in sorted(periods.items()))}),"
          f" the rest with none recorded.")
    print(f"Wrote {MAINS.relative_to(ROOT)}: {hand} hand row(s) kept, {api} from the Stats API.")
    print("Mains:", ", ".join(f"{name} {n}" for name, n in collections.Counter(c[0] for c in chosen.values()).most_common()))


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    main()
