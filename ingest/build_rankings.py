"""Build step 9 (docs/build-plan.md §1): `pr_snapshots` and `player_earnings`, from the Stats API's PR lists.

- pr_snapshots: one row per player, mode and list date (ListPr's lastUpdated), with the region the list was
  requested for. If a list is fetched again on the same date, the newest response wins.
- player_earnings: each ranked player's career earnings, source 'stats_api', as of the list date.
  - A ranked player's 0 is kept. The schema proposal (§6a) reads only an unranked player's 0 as unknown,
    and unranked players have no PR row.
  - The 1v1 and 2v2 lists give the same figure. If they ever differ, the newest response wins and the
    log says so.
- A dev build keeps only the players its events refer to.
"""

MODES = {"1": "1v1", "2": "2v2"}


def step(build):
    snapshots, earnings, figures = {}, {}, {}
    for response in build.reader.responses("/pr"):
        mode, as_of = MODES[response.params["gameMode"]], response.body.get("lastUpdated") or response.fetched_at[:10]
        for row in response.body.get("prPlayers") or []:
            pid = row["playerId"]
            snapshots[(pid, mode, as_of)] = (pid, mode, as_of, response.params.get("region"), row.get("powerRanking"),
                                             row.get("points"), row.get("top8"), row.get("top32"), row.get("gold"),
                                             row.get("silver"), row.get("bronze"))
            if row.get("earnings") is not None:
                earnings[pid] = (pid, "stats_api", row["earnings"], as_of, response.fetched_at)
                figures.setdefault(pid, set()).add(row["earnings"])
    have = set(build.players.written)
    build.db.executemany(
        "INSERT INTO pr_snapshots (player_id, mode, as_of, region, power_ranking, points, top8, top32, gold, silver,"
        " bronze) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [r for r in snapshots.values() if r[0] in have])
    build.db.executemany("INSERT INTO player_earnings (player_id, source, amount_usd, as_of, fetched_at)"
                         " VALUES (?, ?, ?, ?, ?)", [r for r in earnings.values() if r[0] in have])
    differing = sorted(pid for pid, values in figures.items() if len(values) > 1)
    if differing:
        build.log(f"  {len(differing)} players' 1v1 and 2v2 lists give different earnings (the newest is kept),"
                  f" e.g. {differing[:5]}")
    modes = dict(build.db.execute("SELECT mode, COUNT(*) FROM pr_snapshots GROUP BY mode"))
    paid, total = build.db.execute("SELECT SUM(amount_usd > 0), COUNT(*) FROM player_earnings").fetchone()
    build.log(f"  {sum(modes.values())} PR rows (1v1 {modes.get('1v1', 0)}, 2v2 {modes.get('2v2', 0)});"
              f" career earnings for {total} ranked players, {paid or 0} of them above $0")
