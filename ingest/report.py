"""The build report and the review list (docs/build-plan.md §3 and §5).

Every build writes a report to data/reports/<build ID>/:
- report.md: the verdict and what the build was made from, each check's result, every failure (explained or
  not), and what's waiting for review. Curated rows the build skipped come first, marked !!, so a typo gets
  caught.
- checks.csv: every build_checks row.
Reports go when their build is pruned.

The review list, data/review/review.csv, is everything waiting for a person, one row per item:
  key      stable from build to build: the kind and what the item is about, by content (not by line number)
  kind     most pressing first:
             curated_row_skipped     a curated row names a player the cache has no record of (a typo?)
             held_out_event          a new event left out of the counts: its entrant sizes don't fit its mode
             unused_check_exception  a check_exceptions.csv row that explains no failure
             format_rule_tie         an event matched by rules of different formats at one priority
             phase_split             two events that may be phases of one competition
             new_event               an event without a row in events.csv, with its detected mode and format
             auto_merge              a tier-1 merge from data/review/auto_merges.csv, applied or dropped
             merge_candidate         an undecided pair from data/review/merge_candidates.csv
  subject, detail
  resolve  what settles it
A full build of the current cache rewrites the list. A dev build or a build of the past writes its own into its
report folder instead, so the main list stays whole.
"""

import csv
import json
import shutil
from collections import Counter, namedtuple

ReviewItem = namedtuple("ReviewItem", "key kind subject detail resolve")
KINDS = {  # kind: what settles it, in the order the list shows them
    "curated_row_skipped": "Fix the row if it has a typo. A row naming a real record with no official results"
                           " (such as hardymj's 632566) can stay.",
    "held_out_event": "Add a row to curation/events.csv with the format_override or mode_override its entrants fit."
                      " If its sizes are right as they are, also add an entrant_sizes row to check_exceptions.csv.",
    "unused_check_exception": "Remove the row from curation/check_exceptions.csv if the problem was fixed, or correct"
                              " its subject.",
    "format_rule_tie": "Give one of the rules a lower priority in curation/format_rules.csv, or set the event's"
                       " format_override in curation/events.csv.",
    "phase_split": "If they're phases of one competition, give both events one competition_id and a phase_order in"
                   " curation/events.csv; if not, add a row for each with no overrides.",
    "new_event": "If the detected mode and format are right, add a row to curation/events.csv with no overrides;"
                 " otherwise add the override.",
    "auto_merge": "To keep it, copy it into curation/player_merges.csv; to undo it, add the pair to"
                  " curation/merge_rejections.csv.",
    "merge_candidate": "One person: add the pair to curation/player_merges.csv. Two: add it to"
                       " curation/merge_rejections.csv.",
}
NAMES = {  # kind: (one, many), as the report names them
    "curated_row_skipped": ("curated row skipped", "curated rows skipped"),
    "held_out_event": ("held-out event", "held-out events"),
    "unused_check_exception": ("unused check exception", "unused check exceptions"),
    "format_rule_tie": ("format rule tie", "format rule ties"),
    "phase_split": ("possible phase split", "possible phase splits"),
    "new_event": ("new event", "new events"),
    "auto_merge": ("automatic merge", "automatic merges"),
    "merge_candidate": ("merge candidate", "merge candidates"),
}
FROM_CHECKS = {"entrant_sizes": "held_out_event", "format_rule_ties": "format_rule_tie", "phase_splits": "phase_split",
               "new_events": "new_event"}  # review checks whose listed rows are review items
SHOWN = 50  # failures shown per check in report.md; checks.csv has them all


def item(kind, key, subject, detail):
    return ReviewItem(f"{kind}:{key}", kind, subject, detail, KINDS[kind])


def review_items(build, outcomes, merge_candidates):
    """Everything waiting for a person, most pressing first. Reads the build's database, so it runs before the
    database is closed."""
    found = [item("curated_row_skipped", s.key, s.where, f"!! {s.reason}") for s in build.skipped]
    found += [item(FROM_CHECKS[o.check_id], o.subject, o.subject, o.detail)
              for o in outcomes if o.outcome == "listed" and o.check_id in FROM_CHECKS]
    found += [item("unused_check_exception", f"{e.check}:{e.subject}", f"check_exceptions.csv:{e.line}",
                   f"{e.check} for {e.subject}: no such failure in this build ({e.note or 'no note'})")
              for e in build.unused_exceptions]
    if build.curation:
        found += [item("auto_merge", f"{pid} {canonical}", f"{pid} {canonical}", f"applied: {note}")
                  for pid, canonical, note in build.db.execute(
                      "SELECT player_id, canonical_player_id, note FROM player_merges WHERE source = 'auto'"
                      " ORDER BY player_id")]
        found += [item("auto_merge", f"{m.player_id} {m.canonical_player_id}", f"{m.player_id} {m.canonical_player_id}",
                       f"dropped: {reason}") for m, reason in build.curation.dropped_auto]
        if build.events is None:  # a dev build has too few players to tell which pairs are decided
            found += candidate_items(build, merge_candidates)
    order = list(KINDS)
    return sorted(found, key=lambda i: order.index(i.kind))  # a stable sort keeps each kind's own order


def candidate_items(build, path):
    """The undecided pairs of data/review/merge_candidates.csv (merge_candidates.py): neither merged by now, as the
    build's canonical IDs show, nor rejected."""
    if not path or not path.exists():
        return []
    canonical = dict(build.db.execute("SELECT player_id, canonical_id FROM players"))
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    found = []
    for row in rows:
        a, b = int(row["player_id"]), int(row["other_player_id"])
        if frozenset((a, b)) in build.curation.rejections or canonical.get(a, a) == canonical.get(b, b):
            continue

        found.append(item("merge_candidate", f"{min(a, b)} {max(a, b)}", f"{a} {b}",
                          f"tier {row['tier']}: {row['evidence']}; {described(row, '')} and {described(row, 'other_')}"))
    return found


def described(row, prefix):
    """One record of a merge candidate, e.g. "'Tinix' (start.gg, EU, 2017-02-11 to 2025-03-01, 65 events, best 1)"."""
    value = lambda column: row[prefix + column]  # noqa: E731
    span = " to ".join(x for x in (value("first_event"), value("last_event")) if x)
    return (f"'{value('name')}' ({value('platform')}, {value('region') or 'region unknown'}, {span},"
            f" {value('events')} events, best {value('best_placement') or '-'})")


def write_review(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(ReviewItem._fields)
        writer.writerows(items)
    tmp.replace(path)


def named(kind, n):
    return f"{n} {NAMES[kind][n != 1]}"


def labelled(subject, events):
    """A subject as the report shows it: with the event's name when it names one event."""
    found = [events[part] for part in subject.split(" ") if part in events]
    return f"`{subject}` ({found[0]})" if len(found) == 1 else f"`{subject}`"


def cell(text):
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def write_report(folder, build_id, info, outcomes, items, review_path, outcome_note, skipped, events):
    """report.md and checks.csv in the build's report folder. events: {event ID: its name and date}."""
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "checks.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["check_id", "gate", "subject", "outcome", "detail"])
        writer.writerows(outcomes)
    heads = [o for o in outcomes if o.subject == ""]
    failed = [o.check_id for o in heads if o.outcome == "fail"]
    lines = [f"# Build {build_id}: {'failed' if failed else 'passed'}", ""]
    if skipped:
        lines += [f"!! **{len(skipped)} curated row{'s' if len(skipped) != 1 else ''} skipped.** Check each for a typo:",
                  ""] + [f"- !! {s}" for s in skipped] + [""]
    lines += [(f"**Failed:** {', '.join(failed)}." if failed else "**Every check passed.**") + f" {outcome_note}", ""]
    kinds = Counter(i.kind for i in items)
    scope = info.get("scope") or "?"
    if scope.startswith("["):
        scope = f"a dev build of {len(json.loads(scope))} events"
    lines += [f"- **Scope:** {scope}",
              f"- **Responses:** fetched up to {info.get('as_of')}; the newest is from {info.get('cache_cutoff')}",
              f"- **Code:** commit {(info.get('code_commit') or '?')[:12]}"
              + (", with uncommitted changes in ingest/" if info.get("code_changed") == "yes" else ""),
              f"- **Compared with:** {info.get('compared_with')}",
              f"- **Holds:** {info.get('events', '?')} events, {info.get('placements', '?')} placements,"
              f" {info.get('matches', '?')} matches; {info.get('held_out', '0')} events held out for review",
              f"- **Review list:** {review_path}, {len(items)} items"
              + (": " + ", ".join(named(kind, n) for kind, n in kinds.items()) if items else ""),
              "", "## Checks", "", "| Check | Gate | Result | Detail |", "|---|---|---|---|"]
    lines += [f"| {o.check_id} | {o.gate} | {o.outcome} | {cell(o.detail)} |" for o in heads]
    known = [o for o in outcomes if o.check_id == "known_events" and o.subject]
    if known:
        lines += ["", "## Known events (curation/known_events.csv)", ""]
        lines += [f"- **{o.outcome}** {labelled(o.subject, events)}: {o.detail}" for o in known]
    for title, wanted in (("Failures", "fail"), ("Explained by check_exceptions.csv", "explained")):
        rows = [o for o in outcomes if o.subject and o.outcome == wanted]
        if not rows:
            continue
        lines += ["", f"## {title}"]
        for check_id in dict.fromkeys(o.check_id for o in rows):
            mine = [o for o in rows if o.check_id == check_id]
            lines += ["", f"### {check_id} ({mine[0].gate}, {len(mine)})", ""]
            lines += [f"- {labelled(o.subject, events)}: {o.detail}" for o in mine[:SHOWN]]
            if len(mine) > SHOWN:
                lines.append(f"- and {len(mine) - SHOWN} more, in checks.csv")
    if items:
        lines += ["", "## Waiting for review", "", f"All {len(items)} are in {review_path}, most pressing first."]
        for kind in KINDS:
            mine = [i for i in items if i.kind == kind]
            if not mine:
                continue
            lines += ["", f"### {named(kind, len(mine))}", "", KINDS[kind], ""]
            if kind in ("new_event", "merge_candidate"):
                lines.append(f"Listed in {review_path}.")
            else:
                lines += [f"- {labelled(i.subject, events)}: {i.detail}" for i in mine[:SHOWN]]
                if len(mine) > SHOWN:
                    lines.append(f"- and {len(mine) - SHOWN} more")
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder / "report.md"


def prune(reports_dir, kept):
    """Remove the report folders of builds that no longer exist."""
    if reports_dir.exists():
        for folder in reports_dir.iterdir():
            if folder.is_dir() and folder.name not in kept:
                shutil.rmtree(folder, ignore_errors=True)
