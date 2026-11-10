"""Stage 2's checks for the held-out set (eval/questions/heldout.toml), kept apart from the evaluation set's
(eval/result_checks.py, which has the matchers and says how a check reads results).

These lines hold the held-out answers' values. Don't open this file in a session that must leave the held-out set
unread: eval/harness.py reads it through result_checks.all_checks(), and python eval/result_checks.py verifies it.
"""

from result_checks import NA, any_of, every_row, exactly, listing, row, rows, single, winners  # noqa: F401

CHECKS = {
    "h01": any_of(single(4), row("2v2", 4), listing(4, "North America - Autumn Championship 2022")),
    "h02": any_of(single(4), row("1v1", 4), listing(4, "Trial of Heimdall - Europe (Brawl League)")),
    "h03": any_of(row("Brawlhalla Autumn Championship 2019 (EU)", 1), row("2019-09-28", 1), single(1)),
    "h04": row(4, 5, 9),
    "h05": any_of(winners("Zivai", "Blaze"), winners(147982, 149204), row("Zivai", "Blaze"), row(147982, 149204),
                  exactly("Zivai", "Blaze"), exactly(147982, 149204)),
    "h06": any_of(rows(("loreszz", 1), ("Marckiem00", 1), ("Ahmet_", 1)),
                  rows(("loreszz", "Autumn Royale"), ("Marckiem00", "Autumn Royale"), ("Ahmet_", "Autumn Royale")),
                  row("Ahmet_", 1), row("Ahmet_", "Autumn Royale 2025"), row(75405, "Autumn Royale 2025")),
    "h07": any_of(winners("Boomie", "capsar", "antireplay"), winners(146606, 147569, 158406),
                  exactly("Boomie", "capsar", "antireplay"), exactly(146606, 147569, 158406)),
    "h08": row("2021", 7),
    "h09": any_of(single(4), listing(4, "lopesbrawlhalla")),
    "h10": any_of(row("plumthegreat", 8), row(150037, 8)),  # the wins, with or without the 1 loss
    "h11": rows(("Zivai", 7), ("whoiskyna", 7)),
    "h12": row(30, 2),
    "h13": any_of(row("Pro Series 2021", 1), row("series/pro-series-2021-na", 1), row("Zinquer", 1), single(1)),
    "h14": NA,
    "h15": any_of(row("sphynx.", 36), row("Phazon", 28)),
    "h16": NA,
}
