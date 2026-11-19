# Testing the agent on the web app: findings (2026-11-19)

The user's own questions in live mode (qwen3:8b, `claude/agent` merged at a74fa73). Transcripts are in
`data/experiments/web/`. Findings in `agent/` are for the agent session; page findings are fixed on `claude/web-app`.

## For the agent session

### 1. An answer that looks nothing up survives the no-tool check (decided: fix it in code)

- **Seen:** "when was ceo 2025" (`20261119T233544Z-002`, turn 3). The model decided from its own knowledge that CEO isn't
  a Brawlhalla event and answered without a tool call, though its thinking said to call `resolve_event`. The no-tool
  check sent it back once; the reply again called no tool, and stood. The next question, "who got 2nd at ceo 2025",
  called `resolve_event("ceo 2025")`, which matched both CEO 2025 events by their names' words ("every word", 0.9). No
  alias was involved either time.
- **Also:** the check named "Autumn" as a player (a word from the previous turn's answer), and the thinking drifted to
  that turn's Autumn 2022 question.
- **Decided (2026-11-19, the user): fix 1.** When the reply to the no-tool check still calls no tool, the loop doesn't
  keep it: it runs the lookups itself on the question's names (`resolve_event`, `resolve_player`) and gives the model the
  results, or, failing that, replaces the answer with "I couldn't look this up", as the number check replaces claims.
  The model's own knowledge never settles that a player or event doesn't exist.
