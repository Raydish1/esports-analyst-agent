"""Model comparison: one-prompt text-to-SQL on the target questions (an exploratory experiment).

    python eval/model_comparison.py                     every configuration: each model, thinking on and off
    python eval/model_comparison.py --model qwen3:8b --think off --question 2

For each target question in ingest/target_questions.py, the model gets one prompt (PROMPT): a compact description
of the tables and views it needs, the counting rules, and the question. It's asked for one SQLite query, with no
agent loop and no second try. The query runs against the frozen snapshot data/db/eval/eval-v1.sqlite, read-only
and time-limited, and its result is checked against the key facts of the regression script's expected answer
(CHECKS), in whatever shape the query returns them.

It picks a model; it isn't the formal baseline, since the expected answers come from our own data.

Ollama runs on another machine, at OLLAMA_BASE_URL in .env. Sampling uses each model's defaults (temperature 0.6,
top_p 0.95, top_k 20) with a fixed seed, so a run repeats on the same server.

Results go to eval/results/<run>.json: one record per question and configuration, with the outcome, the query, any
error, the time and the tokens. The replies in full, thinking included, go to data/experiments/<run>/ (git-ignored).
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
from platform_clients import load_env  # noqa: E402
from target_questions import QUESTIONS  # noqa: E402

SNAPSHOT = ROOT / "data" / "db" / "eval" / "eval-v1.sqlite"
RESULTS = ROOT / "eval" / "results"
RAW = ROOT / "data" / "experiments"
MODELS = ["qwen3:4b", "qwen3:8b"]
OPTIONS = {"seed": 0, "num_ctx": 16384, "num_predict": 8192}  # the models' own sampling defaults otherwise
QUERY_SECONDS = 90  # a query running longer is stopped and counts as a timeout. The head-to-head views take about
# 50 s when the player's ID comes from a lookup inside the same query (0.1 s with the ID itself), so a correct query
# of that shape still finishes
REQUEST_SECONDS = 900
MAX_ROWS = 1000

PROMPT = """You write SQLite queries against a database of official Brawlhalla esports results (official events only,
from 2017 on). Query the views below. Every player_id in a view is a person's canonical ID.

Finding players and events
- player_aliases(alias, player_id, kind, shown_as, note): the names people use. alias is the name in lowercase
  letters and digits only, without any team tag: 'Hexo' -> 'hexo', 'Sting Ray' -> 'stingray'. kind is 'nickname'
  (curated, so it wins), 'display_name', 'without_tag' or 'former_name'. Several players can share an alias.
- players(player_id, name, canonical_id): name is the current display name; canonical_id is the person.
- A name becomes a person's ID like this: a nickname first, then the player with the most results.
    SELECT p.canonical_id FROM player_aliases a JOIN players p ON p.player_id = a.player_id
    WHERE a.alias = 'boomie'
    ORDER BY a.kind = 'nickname' DESC,
             (SELECT COUNT(*) FROM v_results r WHERE r.player_id = p.canonical_id) DESC
    LIMIT 1
- event_aliases(alias, event_id, note): names people use for events, in lowercase words, e.g. 'bcx 2022'. One alias
  can name several events (a tournament's 1v1 and 2v2).

Views
- v_events(event_id, tournament_name, event_name, start_date, start_time, mode, format, counts_as, status,
  bracket_url): every official event. counts_as is '1v1', '2v2' or NULL for side formats.
- v_results(player_id, event_id, competition_key, mode, format, placement, team_id, tournament_name, event_name,
  start_date, start_time, bracket_url): one result per person per competition that counts. mode is '1v1' or '2v2'.
- v_entries(player_id, event_id, tournament_name, event_name, start_date, start_time, format, mode, placement): every
  official event a person entered, side formats included (their mode is NULL).
- v_official_wins: the rows of v_results with placement = 1.
- v_medals: the rows of v_results with placement <= 3, plus medal ('gold', 'silver' or 'bronze').
- v_player_medals(player_id, mode, gold, silver, bronze, medals): medal counts per person and mode.
- v_team_results(player_id, partner_id, event_id, placement, tournament_name, event_name, start_date): 2v2 results,
  one row per person per partner per event.
- v_match_results(player_id, match_id, side, side_players, event_id, competition_key, mode, start_date, is_scored,
  games_won, games_lost, won): one row per person per counted match.
- v_head_to_head_1v1(player_id, opponent_id, wins, losses, matches, games_won, games_lost, unscored_matches): a
  person's 1v1 record against an opponent.
- v_head_to_head_2v2(player_id, partner_id, opponent1_id, opponent2_id, wins, losses, matches, games_won, games_lost,
  unscored_matches): a team's record against another team.
- v_win_runs(player_id, event_id, competition_key, tournament_name, event_name, start_date, mode, format,
  is_crew_battle, sets_played, sets_dropped, games_won, games_lost, unscored_sets, no_contests): each official win
  with the winner's run through it.

Counting rules (the views already apply the first four)
- "Majors" means official events, and every event here is official.
- A medal is a 1st, 2nd or 3rd place.
- Crew battles count as 1v1. Other side formats (3v3, Triples, Brawlball, Kung Foot) count toward neither mode.
- DQs and forfeits count as neither a win nor a loss.
- The last event a player entered is their newest row in v_entries.
- The most dominant win has the fewest games_lost, then the fewest sets_dropped, then the most games_won. Runs with
  unscored_sets > 0 rank after fully scored ones, and crew battles (is_crew_battle = 1) are left out.
- The best record against someone is the highest win rate (wins / matches) among players with at least 5 matches
  against them.
- A first top 8 is the earliest result (by start_time) with placement <= 8.

Write one SQLite query that answers the question below. Reply with only the query, in a ```sql code block: a single
SELECT (WITH is fine) that runs as it is, with no placeholders and no explanation.

Question: {question}"""


# Talking to the model

def ollama(path, payload=None, timeout=60):
    """A request to the Ollama server, as parsed JSON."""
    url = os.environ["OLLAMA_BASE_URL"].rstrip("/") + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def ask(model, think, question):
    """One request: (reply text, thinking, the server's figures, seconds from request to reply)."""
    payload = {"model": model, "stream": False, "think": think, "options": OPTIONS,
               "messages": [{"role": "user", "content": PROMPT.format(question=question)}]}
    begun = time.monotonic()
    reply = ollama("/api/chat", payload, timeout=REQUEST_SECONDS)
    seconds = time.monotonic() - begun
    message = reply.get("message") or {}
    figures = {k: reply.get(k) for k in ("prompt_eval_count", "eval_count", "total_duration", "load_duration",
                                          "prompt_eval_duration", "eval_duration", "done_reason")}
    return message.get("content") or "", message.get("thinking") or "", figures, seconds


def extract_sql(reply):
    """The query in a reply: its last ```sql block, else its last ``` block, else its last SELECT or WITH statement.
    Thinking that leaked into the reply (<think>...</think>) is left out."""
    text = re.sub(r"<think>.*?</think>", "", reply, flags=re.S)
    blocks = re.findall(r"```sql\s*(.*?)```", text, flags=re.S | re.I) or re.findall(r"```\s*(.*?)```", text, flags=re.S)
    if blocks:
        return blocks[-1].strip().rstrip(";").strip() or None
    starts = [m.start() for m in re.finditer(r"(?im)^\s*(WITH|SELECT)\b", text)]
    return text[starts[-1]:].strip().rstrip(";").strip() if starts else None


# Running the query

def run_query(sql, path=SNAPSHOT, seconds=QUERY_SECONDS):
    """(rows, columns, error, seconds): the query on the snapshot, read-only, stopped after `seconds`."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.execute("PRAGMA query_only = ON")
    deadline = time.monotonic() + seconds
    db.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
    begun = time.monotonic()
    try:
        cursor = db.execute(sql)
        rows = [tuple(r) for r in cursor.fetchmany(MAX_ROWS)]
        return rows, [d[0] for d in cursor.description or []], None, time.monotonic() - begun
    except sqlite3.Error as e:
        return None, None, f"{type(e).__name__}: {e}", time.monotonic() - begun
    finally:
        db.close()


# Checking the result against the regression script's expected answer: the key facts the question asks for, in
# whatever shape the query returns them. Lenient by design: an answer that holds the facts and doesn't contradict
# them counts.

def norm(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value.strip().casefold() if isinstance(value, str) else value


def ints(row):
    return [v for v in map(norm, row) if isinstance(v, int) and not isinstance(v, bool)]


def says(row, text):
    """Whether any cell of a row contains the text, ignoring case."""
    return any(isinstance(v, str) and text.casefold() in v for v in map(norm, row))


def mentions(row, name, ids):
    return says(row, name) or ids.get(name) in ints(row)


def check_last_event(rows, expected, ids):  # 1: the newest official event entered
    return bool(rows) and says(rows[0], expected[0][0][1])


def check_wins(rows, expected, ids):  # 2: how many official wins: a count (or counts by mode), or the wins listed
    names = {row[3] for row in expected}
    if rows and all(len(ints(row)) == 1 for row in rows) and sum(ints(row)[0] for row in rows) == len(expected):
        return True
    return len(rows) == len(expected) and all(any(says(row, name) for row in rows) for name in names)


def check_top8(rows, expected, ids):  # 3: yes, once: names the event, or answers 1 / yes
    if any(says(row, expected[0][1]) for row in rows):
        return True
    return len(rows) == 1 and len(rows[0]) == 1 and norm(rows[0][0]) in (1, "yes", "true")


def check_head_to_head(rows, expected, ids):  # 4: the 1v1 record (from either side), or its sets
    wins, losses, matches, won, lost, _ = expected[0][0]
    for row in rows:
        found = set(ints(row))
        if {wins, losses} <= found and (matches in found or {won, lost} <= found):
            return True
    sets = [(a, b) for _, _, a, b in expected[1]]
    return len(rows) == len(sets) and all(any({a, b} <= set(ints(row)) for row in rows) for a, b in sets)


def check_partners(rows, expected, ids):  # 6: the top partners, and the first one's number of events
    top = expected[1]
    if not all(any(mentions(row, name, ids) for row in rows) for name, _, _ in top):
        return False
    name, events, _ = top[0]
    theirs = [row for row in rows if mentions(row, name, ids)]
    return any(events in ints(row) for row in theirs) or len(theirs) == events


def check_medals(rows, expected, ids):  # 7: the total, or each mode's count
    found = [n for row in rows for n in ints(row)]
    return sum(row[4] for row in expected) in found or all(row[4] in found for row in expected)


def check_best_record(rows, expected, ids):  # 8: the best record comes first
    return bool(rows) and mentions(rows[0], expected[0][0], ids)


def check_links(rows, expected, ids):  # 10: both bracket links
    found = {norm(v) for row in rows for v in row if isinstance(v, str)}
    return all(url.casefold() in found for (url,) in expected)


def check_dominant_win(rows, expected, ids):  # 11: the most dominant win comes first
    return bool(rows) and says(rows[0], expected[0][0][0])


def check_first_top8(rows, expected, ids):  # 12: the first top 8 in 1v1, or the earlier one in 2v2, comes first
    return bool(rows) and any(says(rows[0], first[0][2]) for first in expected[1])


CHECKS = {1: check_last_event, 2: check_wins, 3: check_top8, 4: check_head_to_head, 6: check_partners, 7: check_medals,
          8: check_best_record, 10: check_links, 11: check_dominant_win, 12: check_first_top8}
NAMED = ["Raydish", "hardymj", "Winged_Shell", "V3M_T4NQUIL0"]  # players a query may return by ID instead of name


def failure(sql, rows, error, done_reason=None):
    """What went wrong, as a short type. A reply cut off at the output cap counts as that, whatever query it held."""
    if done_reason == "length":
        return "cut off at the output cap"
    if sql is None:
        return "no SQL in the reply"
    if error:
        message = error.lower()
        for marker, kind in (("interrupted", "timeout"), ("no such column", "unknown column"),
                             ("no such table", "unknown table or view"), ("syntax error", "syntax error"),
                             ("incomplete input", "syntax error"), ("unrecognized token", "syntax error")):
            if marker in message:
                return kind
        return "other SQL error"
    return "empty result" if not rows else "wrong answer"


def preview(rows, limit=3, width=200):
    if rows is None:
        return None
    text = repr(rows[:limit]) + (f" ... ({len(rows)} rows)" if len(rows) > limit else "")
    return text if len(text) <= width else text[:width] + "..."


def summarize(records):
    """Per configuration: accuracy, mean seconds, mean tokens and the failure types, most common first."""
    out = {}
    for record in records:
        key = (record["model"], record["think"])
        s = out.setdefault(key, {"n": 0, "correct": 0, "seconds": 0.0, "tokens": 0, "failures": Counter()})
        s["n"] += 1
        s["correct"] += record["correct"]
        s["seconds"] += record["model_seconds"]
        s["tokens"] += record["output_tokens"] or 0
        if not record["correct"]:
            s["failures"][record["failure"]] += 1
    return out


def table(summary):
    lines = ["| Model | Thinking | Correct | Mean time (s) | Mean output tokens | Failures |", "|---|---|---|---|---|---|"]
    for (model, think), s in summary.items():
        failures = ", ".join(f"{kind} {n}" for kind, n in s["failures"].most_common()) or "none"
        lines.append(f"| {model} | {'on' if think else 'off'} | {s['correct']}/{s['n']} | {s['seconds'] / s['n']:.1f} |"
                     f" {s['tokens'] / s['n']:.0f} | {failures} |")
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Compare models on one-prompt text-to-SQL for the target questions"
                                                 " (exploratory; the expected answers come from our own data).")
    parser.add_argument("--model", action="append", help=f"a model (repeatable; default: {', '.join(MODELS)})")
    parser.add_argument("--think", action="append", choices=["off", "on"], help="thinking off or on (default: both)")
    parser.add_argument("--question", action="append", type=int, help="a question number (default: all ten)")
    parser.add_argument("--results", metavar="DIR", default=str(RESULTS), help="where the results go (default: eval/results)")
    args = parser.parse_args()
    load_env()
    models, thinks = args.model or MODELS, [t == "on" for t in (args.think or ["off", "on"])]
    questions = [q for q in QUESTIONS if not args.question or q[0] in args.question]
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = sqlite3.connect(SNAPSHOT.resolve().as_uri() + "?mode=ro", uri=True)
    build = dict(snapshot.execute("SELECT key, value FROM build_info WHERE key IN ('build_id', 'code_commit')"))
    ids = {name: pid for name in NAMED for (pid,) in snapshot.execute(
        "SELECT canonical_id FROM players WHERE name = ? ORDER BY player_id = canonical_id DESC LIMIT 1", (name,))}
    snapshot.close()
    server = ollama("/api/version")["version"]
    variants = {}
    for model in models:
        info = ollama("/api/show", {"model": model}).get("model_info", {})
        variants[model] = " ".join(str(info.get(k)) for k in ("general.basename", "general.size_label",
                                                               "general.finetune", "general.version") if info.get(k))
    print(f"Run {run}: Ollama {server}; snapshot {SNAPSHOT.name} (build {build.get('build_id')});"
          f" {len(questions)} questions; models {variants}")
    records, raw = [], []
    for model in models:
        ollama("/api/generate", {"model": model, "prompt": "", "keep_alive": "10m"}, timeout=REQUEST_SECONDS)  # load it
        for think in thinks:
            for number, question, _, expected in questions:
                record = {"model": model, "variant": variants[model], "think": think, "question": number,
                          "text": question}
                try:
                    reply, thinking, figures, seconds = ask(model, think, question)
                except (urllib.error.URLError, TimeoutError) as e:
                    reply, thinking, figures, seconds = "", "", {}, float(REQUEST_SECONDS)
                    record["request_error"] = str(e)
                sql = extract_sql(reply)
                rows, columns, error, query_seconds = run_query(sql) if sql else (None, None, None, 0.0)
                correct = rows is not None and CHECKS[number](rows, expected, ids)
                record.update(correct=correct, sql=sql,
                              failure=None if correct else failure(sql, rows, error, figures.get("done_reason")),
                              error=error, columns=columns, rows=len(rows) if rows is not None else None,
                              result=preview(rows), model_seconds=round(seconds, 2),
                              query_seconds=round(query_seconds, 3), prompt_tokens=figures.get("prompt_eval_count"),
                              output_tokens=figures.get("eval_count"), thinking_chars=len(thinking),
                              reply_chars=len(reply), done_reason=figures.get("done_reason"))
                records.append(record)
                raw.append({"model": model, "think": think, "question": number, "reply": reply, "thinking": thinking,
                            "figures": figures})
                print(f"  {model} thinking {'on ' if think else 'off'} Q{number:>2}: {'correct' if correct else record['failure']}"
                      f" ({seconds:.1f} s, {record['output_tokens']} tokens)")
    results = Path(args.results)
    results.mkdir(parents=True, exist_ok=True)
    out = results / f"{run}-model-comparison.json"
    out.write_text(json.dumps({
        "run": run, "kind": "exploratory model comparison (expected answers from our own data; not the formal baseline)",
        "ollama": server, "models": variants, "options": OPTIONS, "query_seconds": QUERY_SECONDS,
        "snapshot": {"file": str(SNAPSHOT.relative_to(ROOT).as_posix()), **build},
        "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()[:16], "prompt": PROMPT,
        "records": records}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (RAW / run).mkdir(parents=True, exist_ok=True)
    with open(RAW / run / "replies.jsonl", "w", encoding="utf-8") as f:
        for row in raw:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nResults: {out}; replies in full: data/experiments/{run}/replies.jsonl\n")
    print(table(summarize(records)))


if __name__ == "__main__":
    main()
