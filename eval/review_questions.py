"""The evaluation set's review page: eval/questions/review.md, made from eval/questions/questions.toml.

    python eval/review_questions.py

Every question's queries run on the frozen snapshot the set names (data/db/eval/eval-v1.sqlite), read-only, and the
page shows their results next to the candidate answer, with the player and event each name in the question was
resolved to. The answers are written by hand from those results, so the page lets a reviewer check them against the
data, and against what they know, before filling in `verified` in questions.toml.

It doesn't run the agent or score anything: that's the evaluation harness, still to come. It exits 1 if the set has a
problem (a missing field, an unknown category or player, a snapshot of another build) or a query fails.
"""

import sqlite3
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT / "eval"))
from model_comparison import run_query  # noqa: E402
from names import normalize, normalize_full, normalize_words  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions" / "questions.toml"
REVIEW = ROOT / "eval" / "questions" / "review.md"
CATEGORIES = {
    "player_record": "one player's results",
    "event_result": "one event's results",
    "head_to_head": "records between players",
    "multi_step": "comparisons, firsts, mosts and rankings",
    "unanswerable": "the data can't answer it, or only partly",
}
REQUIRED = ("id", "question", "category", "tests", "answer", "query")
VERDICTS = ("yes", "no", "partly")
QUERY_SECONDS = 60
SLOW_SECONDS = 5  # the agent's queries should be fast; a slower gold query is worth a look
SHOWN_ROWS = 25
KINDS = {"nickname": "a nickname", "display_name": "the display name", "former_name": "a former name",
         "without_tag": "the name without its team tag"}


def load(path=QUESTIONS):
    with open(path, "rb") as f:
        return tomllib.load(f)


def problems(data):
    """What's wrong with the set itself, as a list of sentences (empty if nothing)."""
    out, ids = [], Counter(q.get("id") for q in data.get("question", []))
    out += [f"{i}: the ID is used {n} times" for i, n in ids.items() if n > 1]
    for key in ("snapshot", "build"):
        if not data.get(key):
            out.append(f"the set doesn't name its {key}")
    for q in data.get("question", []):
        name = q.get("id", "?")
        out += [f"{name}: no {field}" for field in REQUIRED if not q.get(field)]
        if q.get("category") and q["category"] not in CATEGORIES:
            out.append(f"{name}: unknown category {q['category']!r}")
        if q.get("same_answer_as") and q["same_answer_as"] not in ids:
            out.append(f"{name}: same_answer_as names {q['same_answer_as']!r}, which isn't in the set")
        verdict = str(q.get("verified", "")).strip().lower()
        if verdict and not verdict.startswith(VERDICTS):
            out.append(f"{name}: verified should be empty, or start with yes, no or partly")
        out += [f"{name}: a query has no sql" for query in q.get("query", []) if not query.get("sql")]
    return out


# The page

def cell(value):
    if value is None:
        return "NULL"
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(columns, rows):
    lines = ["| " + " | ".join(map(cell, columns)) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(map(cell, row)) + " |" for row in rows[:SHOWN_ROWS]]
    if len(rows) > SHOWN_ROWS:
        lines.append(f"\n({len(rows)} rows; the first {SHOWN_ROWS} shown)")
    return "\n".join(lines) if rows else "(no rows)"


def player_line(db, name, player_id):
    """How a name in a question reaches the player it means: by which alias, and who else has it. None if there's no
    such player."""
    found = db.execute("SELECT name FROM players WHERE player_id = ?", (player_id,)).fetchone()
    if not found:
        return None
    keys = sorted({normalize(name), normalize_full(name)} - {""})
    matches = db.execute(f"SELECT DISTINCT q.canonical_id, a.kind FROM player_aliases a JOIN players q USING (player_id)"
                         f" WHERE a.alias IN ({', '.join('?' * len(keys))})", keys).fetchall() if keys else []

    def results(pid):
        return db.execute("SELECT COUNT(*) FROM v_results WHERE player_id = ?", (pid,)).fetchone()[0]

    kinds = sorted({KINDS[kind] for pid, kind in matches if pid == player_id})
    others = {pid for pid, _ in matches} - {player_id}
    line = f"**{name}** → {found[0]} ({player_id}, {plural(results(player_id), 'result')}), "
    line += f"by {' and '.join(kinds)}" if kinds else "no alias matches it"
    if others:
        line += (f"; {plural(len(others), 'other player')} with this name, with at most"
                 f" {plural(max(map(results, others)), 'result')}")
    return line


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def event_line(db, name, event_ids):
    """The events a name in a question means, and whether an event alias names them. None if one is unknown."""
    ids = [event_ids] if isinstance(event_ids, str) else list(event_ids)
    found = [db.execute("SELECT tournament_name, event_name, start_date FROM v_events WHERE event_id = ?", (e,))
             .fetchone() for e in ids]
    if not all(found):
        return None
    words = normalize_words(name).split()
    aliases = {" ".join(words), " ".join(w for w in words if w not in ("1v1", "2v2"))}
    named = {e for (e,) in db.execute(f"SELECT event_id FROM event_aliases WHERE alias IN ({', '.join('?' * len(aliases))})",
                                      sorted(aliases))}
    shown = "; ".join(f"{t}{' / ' + n if n else ''} ({d})" for t, n, d in found)
    return f"**{name}** → {shown}" + (", by event alias" if set(ids) <= named else "")


def render(data, path, log=print):
    """The review page, and what went wrong: (markdown, problems). Each query's row count and time go to log."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return _render(data, db, path, log)
    finally:
        db.close()


def _render(data, db, path, log):
    issues = []
    build = (db.execute("SELECT value FROM build_info WHERE key = 'build_id'").fetchone() or ["?"])[0]
    if build != data["build"]:
        issues.append(f"the snapshot is build {build}, but the answers were computed on {data['build']}")
    questions = data["question"]
    verified = [q for q in questions if str(q.get("verified", "")).strip()]
    count = Counter(q["category"] for q in questions)
    out = ["# Evaluation set v1: review", "",
           "Made by `python eval/review_questions.py` from [`questions.toml`](questions.toml), which is the file to edit.",
           "",
           f"{len(questions)} questions, with candidate answers computed from the frozen snapshot `{data['snapshot']}`"
           f" (build {data['build']}). Each question shows its candidate answer, the players and events its names were"
           f" resolved to, and the queries behind the answer with their results.",
           "",
           "**To verify:** check each candidate answer against what you know, or against start.gg, Challengermode or"
           " Liquipedia, then fill in `verified` in `questions.toml`: `yes`, or `no: ...` or `partly: ...` with what's"
           " right. Then re-run the script to update this page.",
           "",
           f"**Verified:** {len(verified)} of {len(questions)}.",
           "",
           "| Category | What it covers | Questions |", "|---|---|---|"]
    out += [f"| {c} | {about} | {count[c]} |" for c, about in CATEGORIES.items()]
    out += ["", "| Id | Question | Category | Verified |", "|---|---|---|---|"]
    out += [f"| [{q['id']}](#{q['id']}) | {cell(q['question'])} | {q['category']} | {cell(q.get('verified', ''))} |"
            for q in questions]
    for q in questions:
        out += ["", f'<a id="{q["id"]}"></a>', "", f"## {q['id']}. {q['question']}", "",
                " · ".join([q["category"]] + q["tests"]), ""]
        for name, pid in q.get("players", {}).items():
            line = player_line(db, name, pid)
            if line is None:
                issues.append(f"{q['id']}: no player {pid} ({name!r})")
            out.append(f"- {line or f'**{name}** → no player {pid}'}")
        for name, ids in q.get("events", {}).items():
            line = event_line(db, name, ids)
            if line is None:
                issues.append(f"{q['id']}: an unknown event among {ids!r} ({name!r})")
            out.append(f"- {line or f'**{name}** → an unknown event'}")
        out += ["", "**Candidate answer:**", "", q["answer"].strip(), ""]
        if q.get("same_answer_as"):
            out += [f"**Same answer as:** [{q['same_answer_as']}](#{q['same_answer_as']})", ""]
        if q.get("notes", "").strip():
            out += [f"**Notes:** {q['notes'].strip()}", ""]
        for n, query in enumerate(q["query"], 1):
            sql = query["sql"].strip()
            rows, columns, error, seconds = run_query(sql, path, QUERY_SECONDS)
            log(f"  {q['id']} query {n}: {'error' if error else f'{len(rows)} rows'}, {seconds:.2f} s"
                + (" (slow)" if seconds > SLOW_SECONDS else ""))
            if error:
                issues.append(f"{q['id']} query {n}: {error}")
            out += [f"**Query {n}:** {query.get('purpose', '')}", "", "```sql", sql, "```", "",
                    f"Error: `{error}`" if error else table(columns, rows), ""]
        out += [f"**Verified:** {q.get('verified', '').strip() or 'not yet'}"]
    return "\n".join(out) + "\n", issues


def main():
    sys.stdout.reconfigure(errors="replace")
    data = load()
    issues = problems(data)
    if issues:
        print("The set has problems:\n  " + "\n  ".join(issues))
        sys.exit(1)
    print(f"Running {sum(len(q['query']) for q in data['question'])} queries of {len(data['question'])} questions"
          f" on {data['snapshot']}")
    page, issues = render(data, ROOT / data["snapshot"])
    REVIEW.write_text(page, encoding="utf-8")
    print(f"Wrote {REVIEW.relative_to(ROOT).as_posix()}")
    if issues:
        print("Problems:\n  " + "\n  ".join(issues))
        sys.exit(1)


if __name__ == "__main__":
    main()
