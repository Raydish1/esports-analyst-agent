// Exploration survey of the Brawlhalla Esports Stats API (https://api.brawltools.com/v2)
// using the official SDK, @bmg-esports/sdk. Calls every SDK method at least once and
// saves each raw HTTP response body as its own JSON file in data/raw/survey/, plus a few
// _summary files. Findings are written up in docs/api-survey.md.
//
// The Stats API is for personal use only, so everything this script downloads stays in
// data/, which is git-ignored.
//
// Usage: cd ingest && npm install && npm run survey

import sdk from "@bmg-esports/sdk"; // CommonJS package: the default import is its exports object
import { mkdir, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const OUT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "data", "raw", "survey");
const DELAY_MS = 600; // pause before every request
const PAGE_SIZE = 50; // documented maximum for most list endpoints
const MAX_PAGES = 30; // safety cap for any paginated crawl
const NOW = Math.floor(Date.now() / 1000);
const MODE = { 1: "1v1", 2: "2v2" };

// Test players, as named. When search has no exact (case-insensitive) name match, `hint`
// picks the player to use and says why. See docs/api-survey.md section 8.
const TARGETS = [
  { key: "boomie", query: "Boomie", hint: { playerId: 146606, note: "not returned by search (no current PR, no Challengermode account); found as an opponent in megD's 2v2 matchups" } },
  { key: "raydish", query: "Raydish" },
  { key: "hexo", query: "Hexo", hint: { name: "Hexoo", note: "Hexo's current display name (confirmed)" } },
  { key: "impala", query: "Impala" },
  { key: "balloonboy", query: "Balloonboy", hint: { name: "BBBalloonBoy", note: "only search result for 'Balloonboy'" } },
  { key: "megd", query: "megd" },
  { key: "marckiemoo", query: "marckiemoo", hint: { query: "Marckie", name: "Marckiem00", note: "'marckiemoo' means Marckiem00 (confirmed); search for 'marckiemoo' returns nothing" } },
];

const SEARCH_VARIATIONS = [
  { kind: "case", query: "BOOMIE" },
  { kind: "case", query: "boomie" },
  { kind: "case", query: "RAYDISH" },
  { kind: "case", query: "rAyDiSh" },
  { kind: "case", query: "IMPALA" },
  { kind: "case", query: "MEGD" },
  { kind: "case", query: "bbballoonboy" },
  { kind: "case", query: "HEXOO" },
  { kind: "misspelling", query: "balonboy" },
  { kind: "misspelling", query: "Ballonboy" },
  { kind: "misspelling", query: "BBBalonBoy" },
  { kind: "misspelling", query: "Raydsh" },
  { kind: "misspelling", query: "Radyish" }, // transposition
  { kind: "misspelling", query: "Impla" },
  { kind: "misspelling", query: "Imapla" }, // transposition
  { kind: "misspelling", query: "Hexxo" },
  { kind: "misspelling", query: "megf" },
  { kind: "misspelling", query: "Marckiem0o" }, // one edit from the current name, Marckiem00
  { kind: "misspelling", query: "marckimoo" },
  { kind: "partial", query: "Balloon" },
  { kind: "partial", query: "Rayd" },
  { kind: "partial", query: "dish" },
  { kind: "partial", query: "Hex" },
  { kind: "partial", query: "Imp" },
  { kind: "partial", query: "pala" },
  { kind: "partial", query: "meg" },
  { kind: "partial", query: "Marckie" },
  { kind: "partial", query: "Boom" },
  { kind: "other", query: "Marckiem00" }, // current display name
  { kind: "other", query: "ECHO | Marckiemoo" }, // name with a team tag (space and pipe)
  { kind: "other", query: "Raydish " }, // trailing space
  { kind: "other", query: "Pink" }, // team tag of "Pink | Guichabou"
  { kind: "other", query: "Guichabou" }, // name after a team tag
  { kind: "other", query: "boy", maxResults: 50 }, // above the documented maximum of 25
  { kind: "other", query: "" }, // empty query
];

// --- HTTP capture -----------------------------------------------------------------
// The SDK calls the global fetch and hides status codes (404 becomes null or an empty
// list), so wrap fetch to keep the exact URL, status and body of every exchange.

const realFetch = globalThis.fetch;
let lastExchange = null;
globalThis.fetch = async (url, init) => {
  const started = Date.now();
  const res = await realFetch(url, init);
  const text = await res.clone().text();
  lastExchange = {
    url: String(url),
    status: res.status,
    ms: Date.now() - started,
    headers: Object.fromEntries(res.headers),
    text,
  };
  return res;
};

const manifest = [];
const usedNames = new Set(); // lowercased: Windows file names are case-insensitive
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const safeName = (s) => s.replace(/[^A-Za-z0-9._+-]+/g, "_");
const writeJson = (name, data) => writeFile(path.join(OUT_DIR, name), JSON.stringify(data, null, 2));

// Calls one SDK method, saves the raw response body to <file>.json and returns the
// SDK's result (null on error). Retries once on timeouts and 5xx responses.
async function call(file, fn, params) {
  let result = null;
  let error = null;
  for (let attempt = 1; attempt <= 2; attempt++) {
    await sleep(attempt === 1 ? DELAY_MS : 3000);
    lastExchange = null;
    error = null;
    try {
      result = await sdk[fn](params);
    } catch (e) {
      result = null;
      error = e.message;
    }
    const retryable = error && (/timed out/.test(error) || (lastExchange?.status ?? 0) >= 500);
    if (!retryable) break;
  }

  const ex = lastExchange;
  let body;
  if (!ex) body = { _noResponse: error };
  else {
    try {
      body = JSON.parse(ex.text);
    } catch {
      body = { _nonJsonBody: ex.text };
    }
  }
  let name = `${safeName(file)}.json`;
  for (let n = 2; usedNames.has(name.toLowerCase()); n++) name = `${safeName(file)}__${n}.json`;
  usedNames.add(name.toLowerCase());
  await writeJson(name, body);
  if (manifest.length === 0 && ex) await writeJson("_headers_sample.json", { url: ex.url, headers: ex.headers });
  manifest.push({ file: name, sdkFunction: fn, params, url: ex?.url ?? null, status: ex?.status ?? null, ms: ex?.ms ?? null, error });
  console.log(`[${String(manifest.length).padStart(3)}] ${ex?.status ?? "---"} ${fn} -> ${name}${error ? `  ERROR: ${error}` : ""}`);
  return result;
}

// Follows nextToken until the last page (or maxPages); saves each page separately.
async function paginate(file, fn, params, listKey, maxPages = MAX_PAGES) {
  const items = [];
  const seenTokens = new Set();
  let nextToken;
  for (let page = 1; page <= maxPages; page++) {
    const result = await call(`${file}__p${String(page).padStart(2, "0")}`, fn, nextToken ? { ...params, nextToken } : params);
    if (!result) break;
    items.push(...(result[listKey] ?? []));
    nextToken = result.nextToken;
    if (!nextToken) break;
    if (seenTokens.has(nextToken)) {
      console.log(`    nextToken ${nextToken} repeated; stopping`);
      break;
    }
    seenTokens.add(nextToken);
  }
  return items;
}

// --- Survey -------------------------------------------------------------------------

async function resolvePlayers() {
  const players = {};
  for (const t of TARGETS) {
    let hits = (await call(`searchPlayers__${t.key}`, "searchPlayers", { query: t.query, maxResults: 25 }))?.searchPlayers ?? [];
    let match = hits.find((h) => h.player.name.toLowerCase() === t.query.toLowerCase());
    let method = "exact";
    if (!match && t.hint) {
      method = "hint";
      if (t.hint.playerId) {
        match = await call(`getPlayer__${t.key}__hint`, "getPlayer", { playerId: t.hint.playerId });
      } else {
        if (t.hint.query) {
          hits = (await call(`searchPlayers__${t.key}__hint`, "searchPlayers", { query: t.hint.query, maxResults: 25 }))?.searchPlayers ?? [];
        }
        match = hits.find((h) => h.player.name === t.hint.name);
      }
    }
    players[t.key] = match
      ? { ...match.player, searchedFor: t.query, method, note: t.hint?.note ?? null }
      : { playerId: null, searchedFor: t.query, method: "unresolved" };
  }
  await writeJson("_players.json", players);
  return players;
}

async function surveySearchVariations() {
  const summary = [];
  for (const v of SEARCH_VARIATIONS) {
    const params = { query: v.query, maxResults: v.maxResults ?? 25 };
    const result = await call(`searchPlayers__var__${v.kind}__${v.query || "EMPTY"}`, "searchPlayers", params);
    const last = manifest.at(-1);
    summary.push({
      kind: v.kind,
      query: v.query,
      maxResults: params.maxResults,
      status: last.status,
      error: last.error,
      count: result?.searchPlayers?.length ?? 0,
      nextToken: result?.nextToken ?? null,
      results: (result?.searchPlayers ?? []).map((r) => `${r.player.name} (${r.player.playerId})`),
    });
  }
  // Does search paginate? Follow nextToken for a common fragment.
  await paginate("searchPlayers__var__pagination__boy", "searchPlayers", { query: "boy", maxResults: 10 }, "searchPlayers");
  await writeJson("_search_variations.json", summary);
}

async function surveyPlayer(key, p) {
  const id = p.playerId;
  const placements = {};
  await call(`getPlayer__${key}`, "getPlayer", { playerId: id });
  if (p.brawlhallaId) await call(`getPlayerByBrawlhallaId__${key}`, "getPlayerByBrawlhallaId", { brawlhallaId: p.brawlhallaId });
  if (p.sggPlayerId) await call(`getPlayerBySggId__${key}`, "getPlayerBySggId", { sggPlayerId: p.sggPlayerId });
  if (p.cmPlayerId) await call(`getPlayerByCmId__${key}`, "getPlayerByCmId", { cmPlayerId: p.cmPlayerId });

  for (const gm of [1, 2]) {
    await call(`getPlayerPR__${key}__${MODE[gm]}`, "getPlayerPR", { playerIds: [id], gameMode: gm });
    placements[gm] = await paginate(`getPlayerPlacements__${key}__${MODE[gm]}__all`, "getPlayerPlacements", { playerIds: [id], gameMode: gm, maxResults: PAGE_SIZE }, "playerPlacements");
    await paginate(`getPlayerPlacements__${key}__${MODE[gm]}__official`, "getPlayerPlacements", { playerIds: [id], gameMode: gm, isOfficial: true, maxResults: PAGE_SIZE }, "playerPlacements");
  }

  await paginate(`getPlayerTeammates__${key}__all`, "getPlayerTeammates", { playerId: id, maxResults: PAGE_SIZE }, "playerTeammates");
  await call(`getPlayerTeammates__${key}__official`, "getPlayerTeammates", { playerId: id, isOfficial: true, maxResults: PAGE_SIZE });

  await call(`getPlayerLegends__${key}__alltime`, "getPlayerLegends", { playerIds: [id], maxResults: 10 });
  await call(`getPlayerLegends__${key}__2025`, "getPlayerLegends", { playerIds: [id], year: 2025, maxResults: 10 });
  await call(`getPlayerRecentLegend__${key}`, "getPlayerRecentLegend", { playerId: id });

  // Match details from the player's most recent event in each mode.
  for (const gm of [1, 2]) {
    const latest = [...placements[gm]].sort((a, b) => b.tournament.startTime - a.tournament.startTime)[0];
    if (latest) {
      await call(`getPlayerMatches__${key}__${MODE[gm]}__latest`, "getPlayerMatches", { playerIds: [id], tournamentId: latest.tournament.id });
    }
  }
  return placements;
}

async function surveyPlayerLists(players) {
  const known = Object.values(players).filter((p) => p.playerId);
  const ids = known.map((p) => p.playerId);
  const bhIds = known.map((p) => p.brawlhallaId).filter(Boolean);
  const sggIds = known.map((p) => p.sggPlayerId).filter(Boolean);
  const cmIds = known.map((p) => p.cmPlayerId).filter(Boolean);
  await call("listPlayers__by_playerIds", "listPlayers", { playerIds: ids });
  await call("listPlayers__by_bhIds", "listPlayers", { bhIds });
  await call("listPlayers__by_sggIds", "listPlayers", { sggIds });
  await call("listPlayers__by_cmIds", "listPlayers", { cmIds });
  await call("listPlayers__mixed_id_types", "listPlayers", { playerIds: ids.slice(0, 1), bhIds: bhIds.slice(0, 1) }); // documented to 400
  for (const gm of [1, 2]) await call(`listPrPlayers__${MODE[gm]}`, "listPrPlayers", { playerIds: ids, gameMode: gm });
  await call("listPrPlayers__1v1__region_NA", "listPrPlayers", { playerIds: ids, gameMode: 1, region: "NA" });
}

async function surveyMatchups(players) {
  const I = players.impala.playerId;
  const B = players.balloonboy.playerId;
  const M = players.marckiemoo.playerId;

  // Impala vs Balloonboy head-to-head.
  for (const gm of [1, 2]) {
    await call(`getMatchup__impala_vs_balloonboy__${MODE[gm]}`, "getMatchup", { entrant1PlayerIds: [I], entrant2PlayerIds: [B], gameMode: gm });
    const shared = await paginate(`getMatchupPlacements__impala_vs_balloonboy__${MODE[gm]}`, "getMatchupPlacements", { entrant1PlayerIds: [I], entrant2PlayerIds: [B], gameMode: gm, maxResults: PAGE_SIZE }, "matchupPlacements");
    for (const mp of shared.slice(0, 3)) {
      await call(`getMatchupMatches__impala_vs_balloonboy__${MODE[gm]}__${mp.tournament.id}`, "getMatchupMatches", { tournamentId: mp.tournament.id, entrant1PlayerIds: [I], entrant2PlayerIds: [B] });
    }
  }
  await call("getMatchup__impala_vs_balloonboy__1v1__official", "getMatchup", { entrant1PlayerIds: [I], entrant2PlayerIds: [B], gameMode: 1, isOfficial: true });

  // Everyone marckiemoo has played (for "who has the best record against marckiemoo").
  const opponents = await paginate("getMatchup__marckiemoo_vs_all__1v1", "getMatchup", { entrant1PlayerIds: [M], gameMode: 1, maxResults: PAGE_SIZE }, "matchups");
  await paginate("getMatchup__marckiemoo_vs_all__1v1__official", "getMatchup", { entrant1PlayerIds: [M], gameMode: 1, isOfficial: true, maxResults: PAGE_SIZE }, "matchups");

  // What a DQ looks like per match: an opponent whose record mixes a DQ (-1 games) with other matches.
  const dq = opponents.find((m) => m.games.some((g) => g < 0) && m.matches[0] + m.matches[1] >= 2);
  if (dq) {
    const opp = dq.opponent.map((p) => p.playerId);
    const vs = `marckiemoo_vs_${opp.join("+")}__1v1`;
    const shared = await paginate(`getMatchupPlacements__${vs}`, "getMatchupPlacements", { entrant1PlayerIds: [M], entrant2PlayerIds: opp, gameMode: 1, maxResults: PAGE_SIZE }, "matchupPlacements");
    for (const mp of shared.slice(0, 10)) {
      await call(`getMatchupMatches__${vs}__${mp.tournament.id}`, "getMatchupMatches", { tournamentId: mp.tournament.id, entrant1PlayerIds: [M], entrant2PlayerIds: opp });
    }
  }
}

// Doubles: a team is addressed by passing both players' IDs together.
async function surveyDoubles(players) {
  const D = players.megd.playerId;
  const team = [D, players.raydish.playerId];
  const together = await paginate("getPlayerPlacements__megd+raydish__2v2", "getPlayerPlacements", { playerIds: team, gameMode: 2, maxResults: PAGE_SIZE }, "playerPlacements");
  await call("getPlayerPR__megd+raydish__2v2", "getPlayerPR", { playerIds: team, gameMode: 2 });
  await call("getPlayerLegends__megd+raydish", "getPlayerLegends", { playerIds: team, maxResults: 10 });
  await call("getMatchup__megd_vs_all__2v2", "getMatchup", { entrant1PlayerIds: [D], gameMode: 2, maxResults: PAGE_SIZE });
  await call("getMatchup__megd+raydish_vs_all__2v2", "getMatchup", { entrant1PlayerIds: team, gameMode: 2, maxResults: PAGE_SIZE });
  // Teammate paging (tokens are dates), to compare with the single 50-row page.
  await paginate("getPlayerTeammates__megd__all__pagesize10", "getPlayerTeammates", { playerId: D, maxResults: 10 }, "playerTeammates");

  // Match detail from the team's most recent event together, and one opposing team.
  const latest = together[0];
  if (!latest) return;
  const tid = latest.tournament.id;
  const matches = (await call(`getPlayerMatches__megd+raydish__2v2__${tid}`, "getPlayerMatches", { playerIds: team, tournamentId: tid }))?.playerMatches ?? [];
  await call(`getPlayerMatches__megd__2v2__${tid}`, "getPlayerMatches", { playerIds: [D], tournamentId: tid });
  const opponents = matches.find((m) => m.opponent?.length === 2)?.opponent.map((p) => p.playerId);
  if (!opponents) return;
  const vs = `megd+raydish_vs_${opponents.join("+")}__2v2`;
  await call(`getMatchup__${vs}`, "getMatchup", { entrant1PlayerIds: team, entrant2PlayerIds: opponents, gameMode: 2 });
  await call(`getMatchupPlacements__${vs}`, "getMatchupPlacements", { entrant1PlayerIds: team, entrant2PlayerIds: opponents, gameMode: 2 });
  await call(`getMatchupMatches__${vs}__${tid}`, "getMatchupMatches", { tournamentId: tid, entrant1PlayerIds: team, entrant2PlayerIds: opponents });
}

async function surveyEvents(players, placements) {
  // Every event (community and official), both modes, newest first.
  for (const gm of [1, 2]) {
    await paginate(`listEvents__${MODE[gm]}__all`, "listEvents", { gameMode: gm, maxResults: PAGE_SIZE }, "tournaments", 99);
  }
  await call("listEvents__no_gameMode", "listEvents", { maxResults: 10 });
  await call("listEvents__1v1__isOfficial_false", "listEvents", { gameMode: 1, isOfficial: false, maxResults: PAGE_SIZE });
  for (const host of ["SGG", "CM"]) await call(`listEvents__1v1__host_${host}`, "listEvents", { gameMode: 1, host, maxResults: PAGE_SIZE });

  // Every official event, both modes.
  const official = {};
  for (const gm of [1, 2]) {
    official[gm] = await paginate(`listEvents__${MODE[gm]}__official`, "listEvents", { gameMode: gm, isOfficial: true, maxResults: PAGE_SIZE }, "tournaments");
  }

  // The year filter: first page of every year.
  const years = {};
  for (const gm of [1, 2]) {
    years[gm] = [];
    for (let y = 2014; y <= new Date().getFullYear() + 1; y++) {
      const r = await call(`listEvents__${MODE[gm]}__year_${y}`, "listEvents", { gameMode: gm, year: y, maxResults: PAGE_SIZE });
      years[gm].push({ year: y, firstPageCount: r?.tournaments?.length ?? 0, hasMore: Boolean(r?.nextToken) });
    }
  }

  // nextToken is a startTime. See what happens when a page boundary falls between two
  // events that share a startTime: page 1 ends on the first of the pair.
  let tieCheck = null;
  const ev = official[1];
  const i = ev.findIndex((e, j) => j >= 2 && e.startTime === ev[j - 1].startTime);
  if (i > 0) {
    const base = { gameMode: 1, isOfficial: true, maxResults: 1 };
    const p1 = await call("listEvents__1v1__official__tie_check__p01", "listEvents", { ...base, nextToken: String(ev[i - 2].startTime) });
    const p2 = p1?.nextToken ? await call("listEvents__1v1__official__tie_check__p02", "listEvents", { ...base, nextToken: p1.nextToken }) : null;
    tieCheck = { tiedPair: [ev[i - 1], ev[i]], page1: p1?.tournaments ?? null, page2: p2?.tournaments ?? null };
  }

  // One recent and one older official 1v1 event that a test player attended.
  const attendees = new Map(); // tournamentId -> [player keys]
  for (const [key, byMode] of Object.entries(placements)) {
    for (const p of byMode[1] ?? []) attendees.set(p.tournament.id, [...(attendees.get(p.tournament.id) ?? []), key]);
  }
  const attended = official[1].filter((t) => attendees.has(t.id)).sort((a, b) => b.startTime - a.startTime);
  const recent = attended.find((t) => t.startTime < NOW - 3 * 86400) ?? official[1][0];
  const older = attended.at(-1) ?? official[1].at(-1);
  const selected = { recent, older };
  for (const [label, event] of Object.entries(selected)) {
    if (!event) continue;
    const keys = attendees.get(event.id) ?? [];
    let firstMatch = null;
    for (const key of keys) {
      const r = await call(`getPlayerMatches__${label}_event__${key}__${event.id}`, "getPlayerMatches", { playerIds: [players[key].playerId], tournamentId: event.id });
      firstMatch ??= r?.playerMatches?.[0] ? { key, match: r.playerMatches[0] } : null;
    }
    if (firstMatch) {
      const opponentIds = firstMatch.match.opponent.map((p) => p.playerId);
      await call(`getMatchupMatches__${label}_event__${firstMatch.key}_vs_${opponentIds.join("+")}__${event.id}`, "getMatchupMatches", { tournamentId: event.id, entrant1PlayerIds: [players[firstMatch.key].playerId], entrant2PlayerIds: opponentIds });
    }
    selected[label] = { ...event, testPlayersAttending: keys };
  }
  await writeJson("_selected_events.json", { selected, yearsWithEvents: years, tieCheck });
}

async function surveyPowerRankings() {
  const REGIONS = ["NA", "EU", "SA", "SEA", "MENA", "LAN"];
  for (const gm of [1, 2]) {
    for (const region of REGIONS) {
      await call(`listPR__${MODE[gm]}__${region}__by_earnings`, "listPR", { gameMode: gm, region, orderBy: "earnings DESC", maxResults: 100 });
    }
  }
  await call("listPR__1v1__NA__default_order", "listPR", { gameMode: 1, region: "NA" });
  await call("listPR__1v1__NA__default_order__page2", "listPR", { gameMode: 1, region: "NA", page: 2 });
  for (const region of ["AUS", "JPN", "BRZ", "ALL"]) {
    await call(`listPR__1v1__${region}__undocumented_region`, "listPR", { gameMode: 1, region, maxResults: 10 });
  }
}

async function surveyErrors(players) {
  const R = players.raydish.playerId;
  await call("error__getPlayer__nonexistent_id", "getPlayer", { playerId: 999999999 });
  await call("error__getPlayerPlacements__missing_gameMode", "getPlayerPlacements", { playerIds: [R] });
  await call("error__getPlayerPlacements__maxResults_200", "getPlayerPlacements", { playerIds: [R], gameMode: 1, maxResults: 200 });
  await call("error__getPlayerMatches__unknown_tournament", "getPlayerMatches", { playerIds: [R], tournamentId: "1" });
  await call("error__getMatchupMatches__no_entrant2", "getMatchupMatches", { tournamentId: "fcb7a286-3f0c-4f68-f9a5-08ded4cb1c05", entrant1PlayerIds: [R] });
}

async function main() {
  const started = Date.now();
  // Empty the output folder (rather than deleting it, which fails on Windows if it's in use).
  await mkdir(OUT_DIR, { recursive: true });
  for (const f of await readdir(OUT_DIR)) await rm(path.join(OUT_DIR, f), { recursive: true, force: true });
  try {
    const players = await resolvePlayers();
    await surveySearchVariations();
    const placements = {};
    for (const [key, p] of Object.entries(players)) {
      if (p.playerId) placements[key] = await surveyPlayer(key, p);
    }
    await surveyPlayerLists(players);
    await surveyMatchups(players);
    await surveyDoubles(players);
    await surveyEvents(players, placements);
    await surveyPowerRankings();
    await surveyErrors(players);
  } finally {
    await writeJson("_manifest.json", { ranAt: new Date().toISOString(), sdkVersion: "2.2.0", seconds: Math.round((Date.now() - started) / 1000), calls: manifest });
    const methods = new Set(manifest.map((m) => m.sdkFunction));
    const missing = Object.keys(sdk).filter((k) => typeof sdk[k] === "function" && k !== "overrideAPIURL" && !methods.has(k));
    console.log(`\n${manifest.length} requests in ${Math.round((Date.now() - started) / 1000)}s; SDK methods not called: ${missing.join(", ") || "none"}`);
  }
}

await main();
