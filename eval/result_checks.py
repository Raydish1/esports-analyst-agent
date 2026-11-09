"""Stage 2 of the evaluation harness (eval/harness.py): whether the queries the agent ran returned the facts its
answer needs, for each question of the evaluation set and the held-out set.

A check reads the results of the agent's queries (the rows each run_sql observation showed it, then the events each
resolve_event call listed, which carry an event's status) and passes when the facts are in them, wherever the
answer then went. NA marks a question whose right answer needs no query result: the data can't answer it, or the
right answer is "none".

Values match cells loosely, so a check doesn't depend on how a query is written: numbers to two decimals (a number
written as text counts, as substr(start_date, 1, 4) gives), and text ignoring case, either equal to a cell or, for
four characters or more, inside one ("Raydish" in "megD / Raydish").

Each check is verified against its question's reference queries: python eval/result_checks.py
"""

import sqlite3
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = [ROOT / "eval" / "questions" / "questions.toml", ROOT / "eval" / "questions" / "heldout.toml"]
NA = None


def number(value):
    """A value as a number, or None: 7, 7.0 and '7' are 7."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def matches(want, cell):
    a, b = number(want), number(cell)
    if a is not None and b is not None:
        return abs(a - b) < 0.005
    if cell is None or isinstance(want, (int, float)):
        return False
    want, cell = str(want).casefold().strip(), str(cell).casefold().strip()
    return want == cell or (len(want) >= 4 and want in cell)


def has(row, values):
    return all(any(matches(v, c) for c in row) for v in values)


def row(*values):
    """Some result has a row holding every value."""
    return lambda results: any(has(r, values) for rows in results for r in rows)


def rows(*patterns):
    """One result has, for each pattern, a row holding its values."""
    return lambda results: any(all(any(has(r, p) for r in rs) for p in patterns) for rs in results)


def single(value):
    """Some result is one row holding the value: a count, a total, a best placement."""
    return lambda results: any(len(rs) == 1 and has(rs[0], [value]) for rs in results)


def listing(n, *values):
    """Some result has exactly n rows, one of them holding the values: a list of n wins, events or partners."""
    return lambda results: any(len(rs) == n and any(has(r, values) for r in rs) for rs in results)


def exactly(*values):
    """Some result has one row per value, holding it, and no others: a team's winners, say."""
    return lambda results: any(len(rs) == len(values) and all(any(has(r, [v]) for r in rs) for v in values)
                               for rs in results)


def any_of(*checks):
    return lambda results: any(check(results) for check in checks)


def winners(*names):
    """A 2v2 or crew result's winners: each name on a placement-1 row, separately or grouped in one cell. A query on
    v_official_wins may have no placement column: the checks add row(*names) for a grouped cell then."""
    return rows(*[(name, 1) for name in names])


CHECKS = {
    "q01": any_of(row("Winter Doubles Championship - North America"), row("2024-03-10", 2)),
    "q02": any_of(single(6), row("1v1", 6), listing(6, "Trial of Laufey - North America (Moose Wars)")),
    "q03": any_of(row("Brawlhalla Community Tournament #2"), row("2025-09-28", 5)),
    "q04": any_of(row(2, 1, 3), rows(("2024-03-17",), ("2024-08-04",), ("2024-11-15",))),
    "q05": rows(("gdsandstorm", 258984.17), ("Raydish", 83825)),
    "q06": any_of(rows(("Raydish", 20), ("hardymj", 4), ("Winged_Shell", 3)), rows((160000, 20), (145900, 4), (143709, 3))),
    "q07": any_of(rows(("1v1", 15), ("2v2", 12)), rows((2, 8, 5), (5, 3, 4)), rows((15,), (12,)), single(27)),
    "q08": any_of(row("V3M_T4NQUIL0", 3, 2), row(71736, 3, 2), row("Ahmet_", 3, 1), row(75405, 3, 1)),
    "q09": NA,
    "q10": rows(("https://www.start.gg/tournament/brawlhalla-world-championship-expo-2022/event/1v1/brackets",),
                ("https://www.start.gg/tournament/brawlhalla-world-championship-expo-2022/event/2v2/brackets",)),
    "q11": row("Trial of Laufey - North America (Moose Wars)", 25, 2),
    "q12": any_of(row("Brawlhalla World Championship Expo 2024", 7), row("Summer Doubles Championship - North America", 7)),
    "q13": any_of(row("Raydish", 1), row(160000, 1)),
    "q14": rows(("Raydish", 1), ("Bunny meow", 5), ("antireplay", 7)),
    "q15": any_of(row("Zivai", 1), row(147982, 1), single(2)),  # 2: Zivai's wins among the two events
    "q16": any_of(winners("SiB | Wess", "V3M_T4NQUIL0"), winners(37977, 71736)),
    "q17": rows(("Marckiem00", 1), ("BBBalloonBoy", 2), ("V3M_T4NQUIL0", 5), ("yüz", 7)),
    "q18": any_of(winners("bestjava", "fakey7"), winners(145913, 159255)),
    "q19": any_of(row("BBBalloonBoy", 1), row(149305, 1)),
    "q20": any_of(row("Impala", 3, 0), row(168635, 3, 0)),
    "q21": any_of(single(7), rows(("1v1", 2), ("2v2", 5)), listing(7, "Midseason Championship 2026 1v1")),
    "q22": any_of(row("Brawlhalla World Championship Expo 2025 - 1v1", 1), row("c979b223-7428-4534-97f9-08dd8e232c2e", 1)),
    "q23": row(3, 3, 6),
    "q24": any_of(row("luna", 1), row("BBBalloonBoy", 1)),
    "q25": any_of(single(6), single(5), row("1v1", 6), listing(6, "Trial of Laufey - North America (Moose Wars)")),
    "q26": any_of(rows(("1v1", 15), ("2v2", 12)), rows((2, 8, 5), (5, 3, 4)), rows((15,), (12,)), single(27),
                  single(26), single(29)),
    "q27": row(1, 2, 3),
    "q28": any_of(row("gdsandstorm", 1), row(74433, 1)),
    "q29": any_of(row("gdsandstorm", 1), row(74433, 1)),
    "q30": row("cancelled"),
    "q31": any_of(row("placements_unreliable"), row("TigerBrawlhalla", 6, 0)),
    "q32": NA,
    "q33": NA,
    "q34": NA,
    "q35": NA,
    "q36": NA,
    "q37": any_of(row("gdsandstorm", 48), row(74433, 48), row("Boomie", 42), row(146606, 42)),
    "q38": any_of(rows(("gdsandstorm", 30), ("TigerBrawlhalla", 26), ("Zivai", 23), ("Kylar Alice", 19)),
                  rows(("gdsandstorm", 28), ("TigerBrawlhalla", 26), ("Zivai", 22), ("Kylar Alice", 19))),
    "q39": any_of(rows(("Boomie", 80), ("gdsandstorm", 69)), rows(("Boomie", "1v1", 34), ("gdsandstorm", "1v1", 42)),
                  rows((146606, 80), (74433, 69)), rows((146606, "1v1", 34), (74433, "1v1", 42))),
    "q40": any_of(row("gdsandstorm", 10), row(74433, 10)),  # the losses, with or without the 3 wins
    "q41": any_of(row("gdsandstorm", 3), row(74433, 3), rows(("gdsandstorm", 2), ("yüz", 2))),
    "q42": any_of(row("North America - SteelSeries Championship", 7240), row("Low Tier City Midseason Online (NA)", 10451),
                  row("north-america-steelseries-championship", 7240), row(18298), row(22666)),  # or its event ID
    "q43": any_of(row("Summer Championship - North America 2026 - 1v1"), row("2026-07-19")),
    "q44": any_of(single(3), listing(3, "Autumn Championship - Europe 2026 - 1v1")),
    "q45": any_of(row("Raydish", 83825), row(160000, 83825)),
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


def load_questions(paths=QUESTIONS):
    """Every question of the evaluation and held-out sets, each with its set ('existing' or 'heldout')."""
    out = []
    for path in paths:
        with open(path, "rb") as f:
            for q in tomllib.load(f)["question"]:
                out.append({**q, "set": "heldout" if path.name == "heldout.toml" else "existing"})
    return out


def verify(db):
    """Each check against its question's reference queries: [(id, problem)] for a check that fails on them, a question
    without a check, or a check without a question."""
    problems = []
    questions = load_questions()
    for q in questions:
        if q["id"] not in CHECKS:
            problems.append((q["id"], "no check"))
            continue
        check = CHECKS[q["id"]]
        if check is NA:
            continue
        results = [db.execute(x["sql"]).fetchall() for x in q.get("query", [])]
        if not check(results):
            problems.append((q["id"], "fails on its reference queries"))
    problems += [(i, "no such question") for i in sorted(set(CHECKS) - {q["id"] for q in questions})]
    return problems


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    db = sqlite3.connect((ROOT / "data" / "db" / "eval" / "eval-v1.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    found = verify(db)
    print("\n".join(f"{i}: {p}" for i, p in found) or f"all {len(CHECKS)} checks pass on their reference queries")
    sys.exit(1 if found else 0)
