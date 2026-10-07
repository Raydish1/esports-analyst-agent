-- The database the builder makes (docs/build-plan.md). Tables keep what the platforms and the
-- Stats API reported. Curated values have their own columns and tables, and the views
-- (views.sql) apply the decided rules. The designs are the schema proposal's: §1 for the core
-- tables, §2 for format_rules, §6a for player_earnings, §7 for standings.
-- Changes from the proposal, decided in the build plan:
--   * match scores may be NULL, with the platform's reported winner as the fallback;
--   * merges record whether a person or an unattended run decided them;
--   * event aliases, events and player aliases keep their curated note, and events a curated status;
--   * players.canonical_id: the canonical record, set by the merges step, so the views can find a person's
--     records through an index;
--   * events.held_out: a new event left out of the counts until reviewed, set by the hold-outs step;
--   * new tables: event_terms, event_sources, unplaced_entries, build_info, build_checks.
-- Foreign keys aren't enforced while a build loads; the checks verify them.

-- Players (§1)

CREATE TABLE players (
  player_id      INTEGER PRIMARY KEY,   -- Stats API esports ID; negative for a platform-only player
  name           TEXT NOT NULL,         -- current display name (newest response)
  sgg_player_id  INTEGER,               -- start.gg player ID
  cm_player_id   TEXT,                  -- Challengermode user UUID
  brawlhalla_id  INTEGER,               -- in-game ID
  country        TEXT,                  -- no cached response has one (ListPlayers returns none): NULL for now
  twitter        TEXT,
  twitch         TEXT,
  in_stats_api   INTEGER GENERATED ALWAYS AS (player_id > 0) VIRTUAL,
  source         TEXT NOT NULL DEFAULT 'stats_api',  -- 'stats_api' | 'startgg' | 'challengermode'
  updated_at     TEXT NOT NULL,         -- fetch time of the response this row came from
  canonical_id   INTEGER NOT NULL       -- new (build plan): the person's canonical record, player_merges applied
                                        -- (player_id itself unless merged); v_player_ids reads it
);
CREATE INDEX players_sgg ON players (sgg_player_id);
CREATE INDEX players_canonical ON players (canonical_id);
CREATE INDEX players_cm  ON players (cm_player_id);

CREATE TABLE player_aliases (
  alias      TEXT NOT NULL,      -- normalized (names.py): lowercase, accents folded, no punctuation
  player_id  INTEGER NOT NULL REFERENCES players (player_id),
  kind       TEXT NOT NULL,      -- 'display_name' | 'former_name' | 'without_tag' | 'nickname'
  shown_as   TEXT NOT NULL,      -- original spelling, e.g. 'ECHO | Marckiemoo'
  source     TEXT NOT NULL,      -- 'stats_api' | 'startgg' | 'challengermode' | 'curated'
  note       TEXT,               -- new (build plan): a curated nickname's note, e.g. who else the name means
  PRIMARY KEY (alias, player_id)
);
CREATE INDEX player_aliases_player ON player_aliases (player_id);

CREATE TABLE player_merges (     -- two records that are the same person
  player_id            INTEGER PRIMARY KEY REFERENCES players (player_id),
  canonical_player_id  INTEGER NOT NULL REFERENCES players (player_id),
  source               TEXT NOT NULL,  -- 'curated' (curation/player_merges.csv)
                                       -- | 'auto' (data/review/auto_merges.csv, an unattended run's tier 1)
  note                 TEXT
);

-- Events (§1)

CREATE TABLE tiers (               -- deferred (§5): stays empty, and events.tier stays NULL
  tier   TEXT PRIMARY KEY,         -- e.g. 'S'
  label  TEXT NOT NULL,            -- e.g. 'World Championship'
  rank   INTEGER NOT NULL          -- 1 = highest
);

CREATE TABLE events (
  event_id             TEXT PRIMARY KEY,  -- start.gg event slug, start.gg series slug (3 events) or Challengermode UUID
  host                 TEXT NOT NULL CHECK (host IN ('SGG', 'CM')),
  tournament_name      TEXT NOT NULL,
  event_name           TEXT,              -- always NULL for Challengermode
  sgg_tournament_slug  TEXT,              -- e.g. 'ceo-2025-6'; groups a start.gg tournament's events for display
  year                 INTEGER NOT NULL,
  start_time           INTEGER NOT NULL,  -- Unix seconds
  is_official          INTEGER NOT NULL,  -- 0/1, as reported
  is_twos              INTEGER NOT NULL,  -- 0/1, as reported (one known error; see mode_override)
  is_online            INTEGER NOT NULL,
  -- curated, from curation/events.csv; NULL means "no override"
  tier                 TEXT REFERENCES tiers (tier),  -- deferred: stays NULL
  format_override      TEXT,              -- beats format_rules for this event
  mode_override        TEXT CHECK (mode_override IN ('1v1', '2v2')),
  competition_id       TEXT,              -- shared by the phases of one competition
  phase_order          INTEGER,           -- 1, 2, ... within a competition
  status               TEXT CHECK (status IN ('cancelled')),  -- new (build plan): an official event never held
  note                 TEXT,              -- new (build plan): events.csv's note, e.g. why an event wasn't held
  -- set by the build, not curated
  held_out             TEXT,              -- new (build plan, decision 3): why a new event (no row in events.csv) stays
                                          -- out of the counts until reviewed: its entrant sizes don't fit its mode
  bracket_url          TEXT GENERATED ALWAYS AS (
                         CASE
                           WHEN host = 'SGG' AND event_id LIKE 'tournament/%'
                             THEN 'https://www.start.gg/' || event_id || '/brackets'
                           WHEN host = 'CM'
                             THEN 'https://www.challengermode.com/s/Brawlhalla/tournaments/' || event_id
                         END) VIRTUAL,            -- NULL for the 'series/...' IDs (no working URL)
  source               TEXT NOT NULL DEFAULT 'stats_api',
  fetched_at           TEXT NOT NULL
);
CREATE INDEX events_start ON events (start_time);

CREATE TABLE event_aliases (       -- curated: names people use for events
  alias     TEXT NOT NULL,         -- normalized, e.g. 'bcx 2022', 'worlds 2019', 'msi'
  event_id  TEXT NOT NULL REFERENCES events (event_id),
  note      TEXT,                  -- new (build plan): e.g. that an alias is a default someone may not mean ('msi')
  PRIMARY KEY (alias, event_id)
);

CREATE TABLE event_terms (         -- new (build plan), curated: words people use for words in event names
  term   TEXT NOT NULL,            -- normalized like an event alias, e.g. 'ltc', 'winters'
  means  TEXT NOT NULL,            -- the words it stands for in event names, normalized, e.g. 'low tier city'
  note   TEXT,                     -- e.g. a common mix-up the answer should check
  PRIMARY KEY (term, means)        -- a term can stand for several phrases ('winters': two kinds of seasonal)
);

CREATE TABLE format_rules (        -- curated, from curation/format_rules.csv; lowest priority wins (§2)
  pattern   TEXT PRIMARY KEY,      -- LIKE pattern on lower(tournament_name || ' ' || event_name)
  format    TEXT NOT NULL,
  priority  INTEGER NOT NULL
);

CREATE TABLE event_sources (       -- new (build plan): what the host platform reported about each event as a whole
  event_id           TEXT PRIMARY KEY REFERENCES events (event_id),
  platform           TEXT NOT NULL,  -- 'startgg' | 'challengermode' | 'stats_api' (the Pro Series finals)
  platform_event_id  TEXT,           -- start.gg event ID / Challengermode tournament UUID
  state              TEXT,           -- Challengermode's tournament state; start.gg's phase states, e.g. 'ACTIVE,COMPLETED'
  reported_entrants  INTEGER,        -- start.gg's standings total / Challengermode's roster lineupCount
  reported_sets      INTEGER,        -- start.gg's set total; NULL for Challengermode, which reports none
  -- what the cached pages held, for check 5 (completeness) and v_event_coverage:
  sets_seen          INTEGER,        -- sets (start.gg) or matches (Challengermode) on the pages, stored or not
                                     -- (byes, sets never played and cancelled matches aren't stored)
  entrants_unknown   INTEGER,        -- start.gg set entrants in neither the standings nor an entrant list (their sets
                                     -- lack players); Challengermode bracket lineups missing from the entrant list
  series_without_match INTEGER,      -- Challengermode series between two lineups with no match
  fetched_at         TEXT NOT NULL   -- the newest response these came from
);

-- Placements and 2v2 teams (§1)

CREATE TABLE teams (               -- a 2v2 pair, order-independent
  team_id     INTEGER PRIMARY KEY,
  player1_id  INTEGER NOT NULL REFERENCES players (player_id),
  player2_id  INTEGER NOT NULL REFERENCES players (player_id),
  CHECK (player1_id < player2_id),
  UNIQUE (player1_id, player2_id)
);

CREATE TABLE placements (
  event_id    TEXT NOT NULL REFERENCES events (event_id),
  player_id   INTEGER NOT NULL REFERENCES players (player_id),
  placement   INTEGER NOT NULL,
  team_id     INTEGER REFERENCES teams (team_id),  -- 2v2: the pair from the entrant
  source      TEXT NOT NULL,     -- 'startgg' (standings) | 'challengermode' (entrant lists)
                                 -- | 'stats_api' (the Pro Series finals)
  fetched_at  TEXT NOT NULL,
  PRIMARY KEY (event_id, player_id)
);
CREATE INDEX placements_player ON placements (player_id);

CREATE TABLE unplaced_entries (    -- new (build plan): players who played at an event but have no placement there
  event_id   TEXT NOT NULL REFERENCES events (event_id),   -- (SEA League Week 1/4's and MAX MODE 2025's entrants
  player_id  INTEGER NOT NULL REFERENCES players (player_id),  -- missing from their standings)
  PRIMARY KEY (event_id, player_id)
);

-- Matches (§1). Scores as reported: games won; -1 = DQ'd; 0-0 = a Challengermode forfeit (a match
-- with no scores). NULL = no score reported: a start.gg set with only a winner counts as a win and
-- a loss whose games are unknown (decided 2026-10-05), so is_scored lets game counts leave it out.

CREATE TABLE matches (
  match_id              TEXT PRIMARY KEY,  -- start.gg set ID, or Challengermode match UUID (not the series UUID)
  event_id              TEXT NOT NULL REFERENCES events (event_id),
  side1_score           INTEGER,
  side2_score           INTEGER,
  reported_winner_side  INTEGER CHECK (reported_winner_side IN (1, 2)),  -- the platform's own winner, as a side
  is_scored             INTEGER GENERATED ALWAYS AS (side1_score IS NOT NULL AND side2_score IS NOT NULL) VIRTUAL,
  is_dq                 INTEGER GENERATED ALWAYS AS (
                          COALESCE(side1_score < 0, 0) OR COALESCE(side2_score < 0, 0)) VIRTUAL,
  is_no_contest         INTEGER GENERATED ALWAYS AS (    -- a DQ or a forfeit: neither a win nor a loss
                          COALESCE(side1_score < 0, 0) OR COALESCE(side2_score < 0, 0)
                          OR COALESCE(side1_score = 0 AND side2_score = 0, 0)) VIRTUAL,
  dq_side               INTEGER GENERATED ALWAYS AS (
                          CASE WHEN side1_score < 0 AND side2_score < 0 THEN 0   -- both sides
                               WHEN side1_score < 0 THEN 1
                               WHEN side2_score < 0 THEN 2 END) VIRTUAL,
  winner_side           INTEGER GENERATED ALWAYS AS (
                          CASE WHEN COALESCE(side1_score < 0, 0) OR COALESCE(side2_score < 0, 0) THEN NULL
                               WHEN side1_score IS NULL OR side2_score IS NULL THEN reported_winner_side
                               WHEN side1_score > side2_score THEN 1
                               WHEN side2_score > side1_score THEN 2 END) VIRTUAL,   -- NULL for 0-0
  start_time            INTEGER,           -- start.gg startedAt / Challengermode series startedAt, when reported
  legends_json          TEXT,              -- per side, per game, when reported (Phase 3)
  maps_json             TEXT,
  source                TEXT NOT NULL,     -- 'startgg' (sets) | 'challengermode' (matches)
  fetched_at            TEXT NOT NULL
);
CREATE INDEX matches_event ON matches (event_id);

CREATE TABLE match_players (
  match_id   TEXT NOT NULL REFERENCES matches (match_id),
  side       INTEGER NOT NULL CHECK (side IN (1, 2)),
  player_id  INTEGER NOT NULL REFERENCES players (player_id),
  PRIMARY KEY (match_id, player_id)
);
CREATE INDEX match_players_player ON match_players (player_id);

-- Rankings (§1) and earnings (§6a)

CREATE TABLE pr_snapshots (        -- a PR row as the Stats API reported it
  player_id      INTEGER NOT NULL REFERENCES players (player_id),
  mode           TEXT NOT NULL CHECK (mode IN ('1v1', '2v2')),
  as_of          TEXT NOT NULL,    -- ListPr lastUpdated
  region         TEXT,
  power_ranking  INTEGER,
  points         REAL,
  top8           INTEGER,
  top32          INTEGER,
  gold           INTEGER,
  silver         INTEGER,
  bronze         INTEGER,
  source         TEXT NOT NULL DEFAULT 'stats_api',
  PRIMARY KEY (player_id, mode, as_of)
);

CREATE TABLE player_earnings (
  player_id   INTEGER NOT NULL REFERENCES players (player_id),
  source      TEXT NOT NULL,          -- 'stats_api' | 'esportsearnings_manual' (Phase 2)
  amount_usd  REAL NOT NULL,
  as_of       TEXT NOT NULL,          -- the date the figure is current to
  fetched_at  TEXT NOT NULL,
  PRIMARY KEY (player_id, source)
);

-- Platform standings (§7)

CREATE TABLE standings (           -- every placed entrant, one row per participant
  event_id         TEXT NOT NULL REFERENCES events (event_id),
  entrant_key      TEXT NOT NULL,  -- start.gg entrant ID / Challengermode lineup ID
  platform_player  TEXT NOT NULL,  -- start.gg player ID / Challengermode user ID
  player_id        INTEGER REFERENCES players (player_id),
  entrant_name     TEXT,           -- as shown at the event, e.g. 'Kingdom | Godly'; a party name on Challengermode
  gamer_tag        TEXT,           -- start.gg gamerTag at the event / Challengermode username
  prefix           TEXT,           -- start.gg team tag at the event
  placement        INTEGER NOT NULL,  -- start.gg placement / Challengermode bestPlacement
  worst_placement  INTEGER,        -- Challengermode worstPlacement ('5 - 6' -> 6)
  initial_seed     INTEGER,        -- start.gg initialSeedNum / Challengermode seed
  is_disqualified  INTEGER,        -- start.gg isDisqualified / Challengermode disqualified
  source           TEXT NOT NULL,  -- 'startgg' | 'challengermode'
  fetched_at       TEXT NOT NULL,
  PRIMARY KEY (event_id, entrant_key, platform_player)
);
CREATE INDEX standings_player ON standings (player_id);

-- The build itself (new in the build plan)

CREATE TABLE build_info (          -- what this build was made from, one value per key
  key    TEXT PRIMARY KEY,         -- e.g. 'build_id', 'as_of', 'cache_cutoff', 'code_commit', 'curation'
  value  TEXT
);

CREATE TABLE build_checks (        -- each check's outcome, written when the checks run (checks.py)
  check_id  TEXT NOT NULL,         -- e.g. 'winners', 'pr_cross_check'
  gate      TEXT NOT NULL CHECK (gate IN ('blocking', 'no_worse', 'review')),
  subject   TEXT NOT NULL DEFAULT '',  -- what failed or is listed, e.g. an event ID; '' for the check as a whole,
                                       -- whose outcome is the check's verdict under its gate
  outcome   TEXT NOT NULL CHECK (outcome IN ('pass', 'fail', 'explained', 'listed')),
                                   -- 'explained': a failure check_exceptions.csv explains; 'listed': for review
  detail    TEXT,
  PRIMARY KEY (check_id, subject)
);
