"""A regression check of the target questions (docs/schema-proposal.md §8) against a build.

    python ingest/target_questions.py               the live build
    python ingest/target_questions.py --build PATH  another build, e.g. data/db/eval/eval-v1.sqlite

It asks the ten questions Phase 1 answers (1-4, 6-8 and 10-12), each the way the agent should: names
resolved through player_aliases, then the views. Each answer is compared with the one expected, and it
exits 1 if any differs.

This is a regression check, not the evaluation gold set: its expected answers come from our own data.
They're the survey's (docs/api-survey.md §9) where the survey answered and agrees, adjusted where it
counted community events, and our own where it had no answer (questions 8, 11 and 12). So it catches a
build that changes an answer, not an answer that was wrong to begin with. New results will change some
answers, such as Raydish's wins: then update the expected answer, and its comment, on purpose.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

from builds import Builds
from checks import people_named


def person(db, name, player_id):
    """The player a name means. Several players can share a name (seven records are named Boomie), so the
    question gives the one it's about, and the name must reach that player through player_aliases."""
    found = people_named(db, name)
    if player_id not in found:
        raise LookupError(f"{name!r} doesn't find player {player_id} (it finds {sorted(found) or 'nobody'})")
    return player_id


def rows(db, sql, *args):
    return [tuple(r) for r in db.execute(sql, args)]


def q1(db):
    """What was the last tournament Boomie entered? The newest official event entered, side formats included,
    and the newest 1v1 one, which the survey also gave."""
    boomie = person(db, "Boomie", 146606)
    newest = "SELECT start_date, tournament_name, event_name, mode, placement FROM v_entries WHERE player_id = ?"
    return (rows(db, newest + " ORDER BY start_time DESC LIMIT 1", boomie),
            rows(db, newest + " AND mode = '1v1' ORDER BY start_time DESC LIMIT 1", boomie))


def q2(db):
    """How many majors has Raydish won? Official events, by mode; crew battles count as 1v1."""
    return rows(db, "SELECT mode, format, start_date, tournament_name FROM v_official_wins WHERE player_id = ?"
                    " ORDER BY start_time", person(db, "Raydish", 160000))


def q3(db):
    """Has Hexo ever placed top 8 in 1v1? 'hexo' is a curated nickname for Hexoo."""
    return rows(db, "SELECT start_date, tournament_name, placement FROM v_results WHERE player_id = ? AND mode = '1v1'"
                    " AND placement <= 8 ORDER BY start_time", person(db, "Hexo", 169084))


def q4(db):
    """What does Impala vs Balloonboy's history look like? The 1v1 record without DQs and forfeits, its sets,
    their 2v2 meetings, and the official events both entered."""
    impala, balloonboy = person(db, "Impala", 168635), person(db, "Balloonboy", 149305)
    record = rows(db, "SELECT wins, losses, matches, games_won, games_lost, unscored_matches FROM v_head_to_head_1v1"
                      " WHERE player_id = ? AND opponent_id = ?", impala, balloonboy)
    sets = rows(db, "SELECT a.start_date, v.tournament_name, a.games_won, a.games_lost FROM v_match_results a"
                    " JOIN v_match_results b ON b.match_id = a.match_id AND b.side <> a.side"
                    " JOIN v_events v ON v.event_id = a.event_id"
                    " WHERE a.player_id = ? AND b.player_id = ? AND a.mode = '1v1' AND a.side_players = 1"
                    " ORDER BY a.start_date", impala, balloonboy)
    twos = rows(db, "SELECT COUNT(*) FROM v_head_to_head_2v2 WHERE player_id = ? AND ? IN (opponent1_id, opponent2_id)",
                impala, balloonboy)
    shared = rows(db, "SELECT a.mode, COUNT(*) FROM v_results a JOIN v_results b ON b.event_id = a.event_id"
                      " WHERE a.player_id = ? AND b.player_id = ? GROUP BY a.mode ORDER BY a.mode", impala, balloonboy)
    return record, sets, twos, shared


def q6(db):
    """Who has megd played with in 2v2 tournaments, and how did they place? Partners at official events (the
    two hardymj records are one, through player_merges), and the three most frequent with their best placement."""
    megd = person(db, "megd", 142100)
    count = rows(db, "SELECT COUNT(DISTINCT partner_id) FROM v_team_results WHERE player_id = ?", megd)
    top = rows(db, "SELECT p.name, COUNT(*), MIN(t.placement) FROM v_team_results t JOIN players p"
                   " ON p.player_id = t.partner_id WHERE t.player_id = ? GROUP BY t.partner_id"
                   " ORDER BY COUNT(*) DESC, MIN(t.placement) LIMIT 3", megd)
    return count, top


def q7(db):
    """How many medals does Balloonboy have? Top-3 placements at official events, by mode."""
    return rows(db, "SELECT mode, gold, silver, bronze, medals FROM v_player_medals WHERE player_id = ? ORDER BY mode",
                person(db, "Balloonboy", 149305))


def q8(db):
    """Who has the best record against marckiemoo? 1v1 win rate against Marckiem00 ('marckiemoo' is a curated
    nickname), at least 5 matches, DQs and forfeits left out: the top three."""
    return rows(db, "SELECT p.name, h.wins, h.losses FROM v_head_to_head_1v1 h JOIN players p ON p.player_id = h.player_id"
                    " WHERE h.opponent_id = ? AND h.matches >= 5 ORDER BY 1.0 * h.wins / h.matches DESC, h.matches DESC"
                    " LIMIT 3", person(db, "marckiemoo", 146052))


def q10(db):
    """Give me the bracket link of BCX 2022. The event alias finds both events."""
    return rows(db, "SELECT v.bracket_url FROM event_aliases a JOIN v_events v USING (event_id) WHERE a.alias = 'bcx 2022'"
                    " ORDER BY v.bracket_url")


def q11(db):
    """What is Raydish's most dominant tournament win? v_win_runs ranked as decided: fewest games lost, then fewest
    sets dropped, then most games won, with runs that have unscored sets after every fully scored one. A crew
    battle's sets are crew against crew, so its run isn't comparable and is left out."""
    raydish = person(db, "Raydish", 160000)
    ranked = rows(db, "SELECT tournament_name, sets_played, sets_dropped, games_won, games_lost FROM v_win_runs"
                      " WHERE player_id = ? AND is_crew_battle = 0 AND sets_played > 0"
                      " ORDER BY unscored_sets > 0, games_lost, sets_dropped, games_won DESC", raydish)
    crews = rows(db, "SELECT COUNT(*) FROM v_win_runs WHERE player_id = ? AND is_crew_battle = 1", raydish)
    return ranked, crews


def q12(db):
    """What was flowers' first top 8? 'flowers' is a curated nickname for flowerVS, and also the display name of
    Flowers (156897), whom the answer mentions. The first top 8 in each mode, at official events."""
    flower = person(db, "flowers", 169119)
    nickname = rows(db, "SELECT player_id FROM player_aliases WHERE alias = 'flowers' AND kind = 'nickname'")
    first = [rows(db, "SELECT mode, start_date, tournament_name, placement FROM v_results WHERE player_id = ?"
                      " AND mode = ? AND placement <= 8 ORDER BY start_time LIMIT 1", flower, mode) for mode in ("1v1", "2v2")]
    return nickname, first


QUESTIONS = [  # (number, question, function, expected answer)
    # The survey's answer, which our 2025-2026 data doesn't change: he hasn't entered an official event since.
    (1, "What was the last tournament Boomie entered?", q1,
     ([("2024-03-10", "Winter Doubles Championship - North America", "Brawlhalla Championship 2v2", "2v2", 2)],
      [("2023-11-03", "Brawlhalla World Championship Expo 2023", "1v1", "1v1", 49)])),
    # The survey's answer: 6, all 1v1, the crew battle included.
    (2, "How many majors has Raydish won?", q2,
     [("1v1", "standard", "2022-07-31", "North America - Summer Championship 2022"),
      ("1v1", "standard", "2023-02-05", "North America - Winter Championship 2023"),
      ("1v1", "standard", "2024-02-18", "Trial of Ymir - North America"),
      ("1v1", "standard", "2024-07-14", "Trial of Heimdall - North America (NSIG)"),
      ("1v1", "standard", "2024-08-25", "Trial of Laufey - North America (Moose Wars)"),
      ("1v1", "crew_battle", "2026-08-30", "Eternal Sports Crew Battle Championship 2026 - North America")]),
    # Adjusted: the survey's "8 times" counted community events; one was at an official event.
    (3, "Has Hexo ever placed top 8 in 1v1?", q3, [("2025-09-28", "Brawlhalla Community Tournament #2", 5)]),
    # The survey's record (Impala leads 2-1, 8-4 in games; he lost the BCX 2024 set 2-3; no 2v2 meetings).
    # Adjusted: the survey's 32 shared 1v1 and 4 shared 2v2 events counted community events.
    (4, "What does Impala vs Balloonboy's history look like?", q4,
     ([(2, 1, 3, 8, 4, 0)],
      [("2024-03-17", "Trial of Frigg - North America (Moose Wars)", 3, 0),
       ("2024-08-04", "Trial of Skuld - North America", 3, 1),
       ("2024-11-15", "Brawlhalla World Championship Expo 2024", 2, 3)],
      [(0,)], [("1v1", 23), ("2v2", 3)])),
    # Adjusted: the survey's 25 partners (Raydish 33 events) counted community events.
    (6, "Who has megd played with in 2v2 tournaments, and how did they place?", q6,
     ([(17,)], [("Raydish", 20, 2), ("hardymj", 4, 9), ("Winged_Shell", 3, 17)])),
    # The survey's answer: 27, 1v1 2/8/5 and 2v2 5/3/4.
    (7, "How many medals does Balloonboy have?", q7, [("1v1", 2, 8, 5, 15), ("2v2", 5, 3, 4, 12)]),
    # Our data: the survey gave only the method.
    (8, "Who has the best record against marckiemoo?", q8,
     [("V3M_T4NQUIL0", 3, 2), ("Raydish", 6, 7), ("gdsandstorm", 4, 7)]),
    # The survey's answer.
    (10, "Give me the bracket link of BCX 2022.", q10,
     [("https://www.start.gg/tournament/brawlhalla-world-championship-expo-2022/event/1v1/brackets",),
      ("https://www.start.gg/tournament/brawlhalla-world-championship-expo-2022/event/2v2/brackets",)]),
    # Our data (question 11 came after the survey): the Trial of Laufey, 9 sets, 2 games lost.
    (11, "What is Raydish's most dominant tournament win?", q11,
     ([("Trial of Laufey - North America (Moose Wars)", 9, 0, 25, 2),
       ("Trial of Heimdall - North America (NSIG)", 10, 0, 27, 7),
       ("North America - Winter Championship 2023", 10, 0, 25, 7),
       ("Trial of Ymir - North America", 10, 0, 27, 8),
       ("North America - Summer Championship 2022", 15, 1, 37, 9)], [(1,)])),
    # Our data (question 12 came after the survey): 7th at BCX 2024 in 1v1, and an earlier 7th in 2v2.
    (12, "What was flowers' first top 8?", q12,
     ([(169119,)], [[("1v1", "2024-11-15", "Brawlhalla World Championship Expo 2024", 7)],
                    [("2v2", "2024-07-21", "Summer Doubles Championship - North America", 7)]])),
]


def run(db, log=print):
    """Ask every question. Returns the numbers of those whose answer differs."""
    failed = []
    for number, question, ask, expected in QUESTIONS:
        try:
            answer = ask(db)
        except LookupError as e:
            answer = str(e)
        ok = answer == expected
        log(f"{'PASS' if ok else 'FAIL'} {number:>2}. {question}")
        if not ok:
            failed.append(number)
            log(f"        got:      {answer!r}")
            log(f"        expected: {expected!r}")
    return failed


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="A regression check of the target questions against a build. Its"
                                                 " expected answers come from our own data: not the evaluation gold set.")
    parser.add_argument("--build", metavar="PATH", help="a build file (default: the live build)")
    args = parser.parse_args()
    if args.build:
        db = sqlite3.connect(Path(args.build).resolve().as_uri() + "?mode=ro", uri=True)
    else:
        db = Builds().connect_live()
    try:
        build_id = (db.execute("SELECT value FROM build_info WHERE key = 'build_id'").fetchone() or ["?"])[0]
        print(f"Target questions on build {build_id} (a regression check: expected answers from our own data)")
        failed = run(db)
    finally:
        db.close()
    print(f"{len(QUESTIONS) - len(failed)} of {len(QUESTIONS)} answers as expected")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
