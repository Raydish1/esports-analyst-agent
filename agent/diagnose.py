"""Why a query returned no rows: which of its conditions emptied the result, and whether a value it filters on occurs
in that column at all. tools.run_sql adds this to an empty result's observation, so the model can find the condition
responsible instead of trusting the empty result ("megD never played 2v2", from format = '2v2', a value format never
has; docs/experiments.md).

The model's queries are mostly one SELECT whose WHERE joins conditions with AND. So, without a SQL parser:
- conditions() finds the top-level WHERE and HAVING clauses and splits each at its top-level ANDs: not inside quotes,
  comments or parentheses, and not the AND of a BETWEEN. A clause with a top-level OR stays one condition, and a
  compound query (UNION, INTERSECT, EXCEPT) gets none. A condition in a JOIN's ON isn't tested.
- diagnose() reruns the query without each condition in turn and counts its rows. For a condition comparing a column
  with a value (format = '2v2', player_id = 142100), it checks whether the value occurs in the column across the
  query's FROM, and lists the column's values when it has few. Each probe stops after PROBE_SECONDS, and all of them
  together after PROBES_SECONDS.
"""

import re
import time

PROBE_SECONDS = 4
PROBES_SECONDS = 12
COUNTED = 1000  # rows counted without a condition; more is "more than 1000"
VALUES = 12  # a column's values are listed when it has at most this many
KEYWORD = re.compile(r"(SELECT|FROM|WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT|WINDOW|UNION|INTERSECT|EXCEPT|AND|OR|BETWEEN)"
                     r"\b", re.I)
ENDS = {"WHERE": {"GROUP BY", "HAVING", "ORDER BY", "LIMIT", "WINDOW"}, "HAVING": {"ORDER BY", "LIMIT", "WINDOW"}}
COMPARISON = re.compile(r"((?:\w+\.)?\w+)\s*(==|=|\bLIKE\b)\s*('(?:[^']|'')*'|-?\d+)", re.I)


def top_level(query):
    """The keywords at a query's top level, outside quotes, comments and parentheses: [(start, end, KEYWORD)]."""
    found, depth, i, n = [], 0, 0, len(query)
    while i < n:
        c = query[i]
        if c in "'\"`[":
            close, i = ("]" if c == "[" else c), i + 1
            while i < n and not (query[i] == close and query[i + 1:i + 2] != close):
                i += 2 if query[i] == close else 1  # a doubled quote escapes itself
            i += 1
        elif query.startswith("--", i):
            i = query.find("\n", i) + 1 or n
        elif query.startswith("/*", i):
            i = query.find("*/", i + 2) + 2 if "*/" in query[i + 2:] else n
        elif c in "()":
            depth += 1 if c == "(" else -1
            i += 1
        elif c.isalpha() or c == "_":
            word = re.match(r"\w+", query[i:]).group()
            m = KEYWORD.match(query, i) if depth == 0 else None
            if m:
                found.append((m.start(), m.end(), " ".join(m.group(1).upper().split())))
            i = m.end() if m else i + len(word)
        else:
            i += 1
    return found


def conditions(query):
    """The top-level conditions of a query's WHERE and HAVING clauses, as (start, end) spans of its text."""
    words = top_level(query)
    if any(w in ("UNION", "INTERSECT", "EXCEPT") for _, _, w in words):
        return []
    spans = []
    for clause in ("WHERE", "HAVING"):
        start = next((e for s, e, w in words if w == clause), None)
        if start is None:
            continue
        end = next((s for s, _, w in words if s > start and w in ENDS[clause]), len(query))
        inside = [(s, e, w) for s, e, w in words if start <= s < end]
        if any(w == "OR" for _, _, w in inside):
            spans.append((start, end))
            continue
        bounds, between = [start], False
        for s, e, w in inside:
            if w == "BETWEEN":
                between = True
            elif w == "AND" and between:
                between = False
            elif w == "AND":
                bounds += [s, e]
        spans += zip(bounds[::2], bounds[1::2] + [end])
    return [(a, b) for a, b in spans if query[a:b].strip()]


def literal(text):
    """A SQL literal's value: '2v2' -> 2v2, 142100 -> 142100."""
    return text[1:-1].replace("''", "'") if text.startswith("'") else int(text)


def diagnose(query, run):
    """{note, conditions}: why a query found no rows. run(sql, seconds) runs a probe and returns its rows, or None if
    it failed or ran out of time."""
    query = query.strip().rstrip(";").strip()
    deadline = time.monotonic() + PROBES_SECONDS

    def probe(sql):
        left = min(PROBE_SECONDS, deadline - time.monotonic())
        return run(sql, left) if left > 0.05 else None

    words = top_level(query)
    select = next((s for s, _, w in words if w == "SELECT"), None)
    source = next((e for s, e, w in words if w == "FROM" and select is not None and s > select), None)
    source_end = next((s for s, _, w in words if source and s > source and w in ENDS["WHERE"] | {"WHERE"}), len(query))
    prefix, sources = (query[:select], query[source:source_end]) if source else ("", None)
    findings = []
    for a, b in conditions(query):
        found = {"condition": " ".join(query[a:b].split())}
        rows = probe(f"SELECT COUNT(*) FROM (SELECT 1 FROM ({query[:a]} 1=1 {query[b:]}) LIMIT {COUNTED + 1})")
        found["rows_without_it"] = ("not tested: too slow" if rows is None else
                                    rows[0][0] if rows[0][0] <= COUNTED else f"more than {COUNTED}")
        m = COMPARISON.fullmatch(query[a:b].strip())
        if m and sources:
            column, operator, value = m.group(1), m.group(2).upper(), m.group(3)
            values = probe(f"{prefix}SELECT DISTINCT {column} FROM {sources} LIMIT {VALUES + 1}") if operator != "LIKE" else None
            if values is not None and len(values) <= VALUES:
                found["values"] = [v for (v,) in values]
                found["value_found"] = literal(value) in found["values"]
            else:
                hit = probe(f"{prefix}SELECT 1 FROM {sources} WHERE {column} {operator} {value} LIMIT 1")
                if hit is not None:
                    found["value_found"] = bool(hit)
        findings.append(found)
    return {"note": note(findings), "conditions": findings}


def note(findings):
    """The diagnosis in a few sentences, ending with what the model should do about it."""
    out = []
    emptied = [f for f in findings if f["rows_without_it"] not in (0, "not tested: too slow")]
    out += [f"Without {f['condition']}, the query returns {f['rows_without_it']} rows." for f in emptied[:3]]
    for f in findings:
        if f.get("value_found") is False:
            values = f" Its column's values there: {', '.join(map(repr, f['values']))}." if f.get("values") else ""
            out.append(f"No row has {f['condition']}.{values}")
    if findings and not emptied:
        out.append("No single condition explains it: without any one of them, the query still returns no rows.")
    if not findings:
        out.append("Its conditions couldn't be tested one by one.")
    out.append("Check the condition responsible, and that each player_id came from resolve_player. If you relax a"
               " condition, say in your answer which one and why. Never relax a condition silently.")
    return " ".join(out)
