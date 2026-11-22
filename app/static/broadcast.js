// Broadcast-style stat cards (broadcast.css): each a fixed 1920x1080 frame, scaled to its container. Every number
// comes from the card data (figures.py); a field the data doesn't have (PR rank, country, team, the event's logo) is
// left out, never invented. Built with textContent only.

const SVG = "http://www.w3.org/2000/svg";
const ROMAN = { first: "I.", second: "II.", third: "III." };
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

// Shapes traced from the lifetime reference (1206x665), scaled by 1920/1206.
const LIFETIME = {
  panel: "0,0 484,0 506,32 509,80 517,166 556,172 568,223 581,248 602,274 616,299 621,302 621,338 597,344 594,353 610,363 642,376 661,388 661,433 648,446 662,471 662,519 642,567 629,602 651,637 659,653 637,732 626,796 630,802 643,866 650,955 656,1059 656,1083 0,1080",
  border: "0,0 501,0 524,32 527,80 535,166 573,172 586,223 599,248 619,274 634,299 638,302 638,338 615,344 611,353 627,363 659,376 678,388 678,433 665,446 680,471 680,519 659,567 646,602 669,637 677,653 654,732 643,796 648,802 661,866 667,955 673,1059 673,1083 0,1080",
  bar: "0,302 624,302 615,312 627,323 611,338 0,338",
  shards: ["527,75 560,68 525,159", "630,271 650,263 635,315", "611,341 678,312 653,357", "648,449 681,459 653,465"],
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function polygon(points, fill) {
  const p = document.createElementNS(SVG, "polygon");
  p.setAttribute("points", points);
  p.setAttribute("fill", fill);
  return p;
}

function shapes(parts) {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "bc-shapes");
  svg.setAttribute("viewBox", "0 0 1920 1080");
  svg.setAttribute("aria-hidden", "true");
  for (const [points, fill] of parts) svg.append(polygon(points, fill));
  return svg;
}

// The heavy face: Proxima Nova Condensed Black when it loads (broadcast.css), at full width, as the broadcast sets it;
// else Proxima Nova Black squeezed to 87%, which measured closest to the condensed cut; else the fallback fonts, which
// were measured unscaled. fontsReady resolves once that's settled.
async function heavyFace() {
  const loads = async (family) => (await document.fonts.load(`900 100px "${family}"`).catch(() => [])).length > 0;
  if (await loads("BC Heavy")) document.documentElement.classList.add("bc-proxima-cond");
  else if (await loads("BC Heavy Wide")) document.documentElement.classList.add("bc-proxima");
}
export const fontsReady = heavyFace().catch(() => {});

const HEAVY = [".bc-name", ".bc-heading", ".bc-pname", ".bc-vs", ".bc-earnings",
  ".bc-count", ".bc-value", ".bc-money", ".bc-num", ".bc-pnum", ".bc-score", ".bc-wsets-heading", ".bc-wsets-side", ".bc-tile-event"]
  .map((c) => `${c}:not(.bc-missing)`).join(", ");

function squeezeWords(frame) {
  for (const node of frame.querySelectorAll(HEAVY)) {
    if (node.querySelector(".bc-missing") || !node.textContent) continue;
    node.replaceChildren(el("span", "bc-sq", node.textContent));
  }
  return frame;
}

function text(className, value) {
  return el("p", `bc-t ${className}`, value);
}

// A legend's idle pose, fitted into its slot and standing on the slot's floor, outlined in its player's color
// (broadcast.css). mirror: face left, as the broadcast turns the right-hand player's legend toward the opponent.
// A player with no main on record gets the random-legend silhouette, never a guessed legend.
const NO_MAIN = { url: "art/legends/random.webp", name: "No main on record" };

function legendSlot(legend, mirror = false) {
  const slot = el("div", "bc-legend");
  legend = legend?.url ? legend : NO_MAIN;
  const img = el("img");
  img.src = legend.url;
  img.alt = legend.name;
  img.style.transform = `translate(${legend.offset_x || 0}px, ${legend.offset_y || 0}px) scale(${legend.scale || 1})` +
    (mirror ? " scaleX(-1)" : "");
  img.addEventListener("error", () => img.remove());
  slot.append(img);
  return slot;
}

function years(p) {
  const from = p.first?.slice(0, 4);
  const to = p.latest?.slice(0, 4);
  if (!from) return null;
  return from === to ? `OFFICIAL RESULTS ${from}` : `OFFICIAL RESULTS ${from}–${to}`;
}

// What a frame counts, for its foot or top strip: the scope in the mode shown.
function scopeLine(mode, crew) {
  const parts = ["All official events, regional championships included",
    mode === "1v1 and 2v2" ? "1v1 and 2v2 together" : `${mode} only`];
  if (crew && mode !== "2v2") parts.push("crew battles count as 1v1");
  return parts.join(" · ");
}

function missing(className) {
  return el("span", `${className} bc-missing`.trim(), "not recorded");
}

// A card's frame, scaled to fit its container's width (and, for a frame narrower than 1920, at most maxHeight tall).
export function scaled(frame, width = 1920, height = 1080, maxHeight = Infinity) {
  const box = el("div", "bc-scale");
  box.style.aspectRatio = `${width} / ${height}`;
  if (width < 1920) box.style.maxWidth = `${(maxHeight * width) / height}px`;
  box.append(frame);
  const fit = () => { frame.style.transform = `scale(${box.clientWidth / width})`; };
  new ResizeObserver(fit).observe(box);
  return box;
}

export function lifetimeFrame(card, mode = "1v1 and 2v2") {
  const p = card.player;
  const m = p.modes[mode] || {};
  const frame = el("div", "bc-frame bc-lifetime");
  frame.setAttribute("role", "img");
  frame.setAttribute("aria-label", `Lifetime stats for ${p.name}`);
  frame.append(shapes([
    [LIFETIME.border, "var(--bc-orange)"], [LIFETIME.panel, "var(--bc-cream)"], [LIFETIME.bar, "var(--bc-orange)"],
    ...LIFETIME.shards.map((s) => [s, "var(--bc-cream)"]),
  ]));
  frame.append(legendSlot(p.legend));
  frame.append(text("bc-eyebrow", "LIFETIME STATS"), text("bc-name bc-heavy", (p.name || "").toUpperCase()));
  const span = years(p);
  if (span) frame.append(text("bc-bar-text", span));

  if ("earnings" in p) {
    frame.append(text("bc-heading bc-heavy bc-h-earnings", "EARNINGS"));
    const amount = p.earnings.amount;
    frame.append(amount === null || amount === undefined
      ? text("bc-earnings bc-missing", "not recorded")
      : text("bc-earnings bc-heavy", money.format(amount)));
  }

  frame.append(text("bc-heading bc-heavy bc-h-medals", "MEDALS"));
  [["first", "GOLD"], ["second", "SILVER"], ["third", "BRONZE"]].forEach(([key, label], i) => {
    const row = el("div", "bc-row bc-medal");
    row.style.top = `${640 + i * 54}px`;
    row.append(el("div", "bc-box"), el("span", "bc-label", label), el("span", "bc-circle", ROMAN[key]));
    const value = m[key];
    row.append(value === null || value === undefined ? missing("bc-count") : el("span", "bc-count bc-heavy", String(value)));
    frame.append(row);
  });

  frame.append(text("bc-heading bc-heavy bc-h-placement", "PLACEMENT"));
  const places = [["top8", "TOP 8"], ...(p.top32 ? [["top32", "TOP 32"]] : [])];  // no top32 column yet: no row
  places.forEach(([key, label], i) => {
    const row = el("div", "bc-row bc-place");
    row.style.top = `${914 + i * 54}px`;
    row.append(el("div", "bc-box"), el("span", "bc-label", label));
    const value = m[key];
    const cell = el("span", "bc-value bc-heavy", value === null || value === undefined ? "" : String(value));
    if (value === null || value === undefined) cell.append(missing(""));
    row.append(cell);
    frame.append(row);
  });

  const parts = [`${scopeLine(mode, p.crew)}.`];
  if ("earnings" in p && p.earnings.amount !== null) parts.push(`Earnings: career, all modes, ${p.earnings.source}, as of ${p.earnings.as_of}.`);
  frame.append(text("bc-scope", parts.join(" ")));
  recentRow(frame, p.recent?.[mode], mode);
  return squeezeWords(frame);
}

// Recent placements, in the lifetime card's empty bottom right: the player's latest official events in the mode shown,
// newest first, each its tournament's logo in a slanted box (or a badge drawn from its name, when there's no logo or
// it doesn't load), with the placement on a plate under it.
const SEASONS = [["autumn", "AUTUMN"], ["summer", "SUMMER"], ["spring", "SPRING"], ["winter", "WINTER"]];
const REGION_WORDS = [["north america", "NA"], ["south america", "SA"], ["southeast asia", "SEA"], ["europe", "EU"],
  ["middle east", "MENA"], ["australia", "AUS"], ["oceania", "OCE"], ["japan", "JPN"], ["brazil", "BRZ"]];

// A badge for an event without a logo: its kind (a colour and a word), a short name, and the year.
export function badgeFor(event, date) {
  const name = (event || "").toLowerCase();
  const year = (date || "").slice(2, 4);
  const region = REGION_WORDS.find(([w]) => name.includes(w))?.[1] || (name.match(/\((na|eu|sa|sea|aus)\)/)?.[1] || "").toUpperCase();
  const season = SEASONS.find(([w]) => name.includes(w));
  if (/world championship expo|bcx/.test(name)) return { kind: "worlds", top: "WORLDS", big: "BCX", year };
  if (/world championship/.test(name)) return { kind: "worlds", top: "WORLDS", big: region || "BWC", year };
  if (/midseason/.test(name)) return { kind: "midseason", top: "MIDSEASON", big: "MSC", year };
  if (/crew battle|pro series/.test(name)) return { kind: "crew", top: "CREW BATTLE", big: region || "CB", year };
  if (season) return { kind: season[0], top: season[1], big: region || "BHC", year };
  const word = (event || "").replace(/^brawlhalla\s*/i, "").split(/[\s/-]+/).filter(Boolean)[0] || "";
  return { kind: "other", top: region || "OFFICIAL", big: word.slice(0, 4).toUpperCase(), year };
}

function badge(event, date) {
  const b = badgeFor(event, date);
  const node = el("div", `bc-badge bc-badge-${b.kind}`);
  node.append(el("span", "bc-badge-top", b.top), el("span", `bc-badge-big${b.big.length > 2 ? " bc-long" : ""}`, b.big));
  if (b.year) node.append(el("span", "bc-badge-year", `'${b.year}`));
  return node;
}

function recentRow(frame, results, mode) {
  if (!results?.length) return;
  const box = el("div", "bc-recent");
  box.append(el("p", "bc-recent-title bc-heavy", `RECENT PLACEMENTS${mode === "1v1 and 2v2" ? "" : ` · ${mode.toUpperCase()}`}`));
  const row = el("div", "bc-recent-row");
  for (const r of results) {
    const slot = el("div", "bc-recent-slot");
    slot.title = `${r.event} · ${r.date}`;
    const shape = el("div", "bc-recent-shape");
    const clip = el("div", "bc-recent-clip");
    if (r.image) {
      const img = el("img");
      img.src = r.image;
      img.alt = r.event;
      img.addEventListener("error", () => img.replaceWith(badge(r.event, r.date)));
      clip.append(img);
    } else {
      clip.append(badge(r.event, r.date));
    }
    shape.append(clip);
    const place = el("span", `bc-recent-place bc-heavy${r.placement === 1 ? " bc-gold" : r.placement <= 3 ? " bc-medal" : ""}`,
      ordinal(r.placement));
    slot.append(shape, place);
    row.append(slot);
  }
  box.append(row);
  frame.append(box);
}

// Head-to-head (reference: Godly vs Bamya). Shapes traced from the reference scaled to 1920 wide; the legends cover
// parts of the strip's edge there, so those stretches are smoothed.
const H2H = {
  strip: "0,973 96,978 112,963 144,950 176,957 240,959 304,962 336,952 352,963 400,966 464,960 480,944 592,924 606,968 688,960 704,978 752,942 768,908 864,939 960,923 1152,905 1166,948 1232,939 1264,932 1280,944 1296,964 1312,967 1408,949 1424,922 1440,919 1488,939 1504,969 1536,947 1616,962 1744,944 1776,958 1792,931 1840,905 1904,942 1920,945 1920,1080 0,1080",
  borderL: "0,957 96,962 112,947 144,934 176,941 240,943 304,946 336,936 352,947 400,950 464,944 480,928 592,908 606,952 688,944 704,962 752,926 768,892 768,908 752,942 704,978 688,960 606,968 592,924 480,944 464,960 400,966 352,963 336,952 304,962 240,959 176,957 144,950 112,963 96,978 0,973",
  borderR: "1152,891 1166,934 1232,925 1264,918 1280,930 1296,950 1312,953 1408,935 1424,908 1440,905 1488,925 1504,955 1536,933 1616,948 1744,930 1776,944 1792,917 1840,891 1904,928 1920,931 1920,945 1904,942 1840,905 1792,931 1776,958 1744,944 1616,962 1536,947 1504,969 1488,939 1440,919 1424,922 1408,949 1312,967 1296,964 1280,944 1264,932 1232,939 1166,948 1152,905",
  bar: 332,  // the longest placement bar, in px: the reference's scale
};

function sided(tag, className, side, value) {
  return el(tag, `${className} bc-${side}`, value);
}

function absent(v) { return v === null || v === undefined; }

// The set record shown in a mode: the card's record for that mode (figures.py), or, from before cards had one per
// mode, its 1v1 record.
export function recordIn(card, mode) {
  return card.records ? card.records[mode] : card.record;
}

const RECORD_SCOPE = { "1v1": "official 1v1 sets", "2v2": "official 2v2 sets, the two on opposite teams",
  "1v1 and 2v2": "official 1v1 and 2v2 sets together" };

export function headToHeadFrame(card, mode = "1v1 and 2v2") {
  const [a, b] = card.players;
  const ma = a.modes[mode] || {};
  const mb = b.modes[mode] || {};
  const frame = el("div", "bc-frame bc-h2h");
  frame.setAttribute("role", "img");
  frame.setAttribute("aria-label", `${a.name} against ${b.name}`);
  frame.append(shapes([["0,0 1920,0 1920,37 0,37", "var(--bc-cream)"]]));
  const legendL = legendSlot(a.legend);
  legendL.classList.add("bc-l");
  const legendR = legendSlot(b.legend, true);
  legendR.classList.add("bc-r");
  frame.append(legendL, legendR);
  // The bottom strip goes over the legends' feet, as in the reference.
  frame.append(shapes([[H2H.borderL, "var(--bc-orange)"], [H2H.borderR, "var(--bc-teal)"], [H2H.strip, "var(--bc-cream)"]]));
  // The top strip's fields (PR, country, team, the round) aren't in the data: it states the card's scope instead.
  const strip = [scopeLine(mode, a.crew || b.crew)];
  const record = recordIn(card, mode);
  if (record) strip.push(`record: ${card.records ? RECORD_SCOPE[mode] : RECORD_SCOPE["1v1"]}${record.unscored ? `, ${record.unscored} with no recorded score` : ""}`);
  if ("earnings" in a && "earnings" in b) {
    const asOf = [...new Set([a, b].filter((p) => !absent(p.earnings.amount)).map((p) => `${p.earnings.source}, as of ${p.earnings.as_of}`))];
    if (asOf.length) strip.push(`earnings: career, ${asOf.join("; ")}`);
  }
  frame.append(text("bc-strip-text", strip.join(" · ").toUpperCase()));

  if ("earnings" in a && "earnings" in b) {
    frame.append(text("bc-heading bc-heavy bc-center bc-h-earnings", "EARNINGS"));
    for (const [p, side] of [[a, "l"], [b, "r"]]) {
      const amount = p.earnings.amount;
      frame.append(absent(amount) ? sided("p", "bc-t bc-money bc-missing", side, "not recorded")
        : sided("p", "bc-t bc-money bc-heavy", side, money.format(amount)));
    }
    const tri = document.createElementNS(SVG, "svg");
    tri.setAttribute("class", "bc-tri");
    tri.setAttribute("viewBox", "0 0 33 32");
    const t = polygon("3,3 30,3 16.5,29", "none");
    t.setAttribute("stroke", "#fff");
    t.setAttribute("stroke-width", "3.5");
    tri.append(t);
    frame.append(tri);
  }

  frame.append(text("bc-heading bc-heavy bc-center bc-h-medals", "MEDALS"));
  [["first", "GOLD"], ["second", "SILVER"], ["third", "BRONZE"]].forEach(([key, label], i) => {
    const row = el("div", "bc-mrow");
    row.style.top = `${373 + i * 55}px`;
    row.append(el("div", "bc-mlabel", label), sided("span", "bc-circle", "l", ROMAN[key]), sided("span", "bc-circle", "r", ROMAN[key]));
    for (const [v, side] of [[ma[key], "l"], [mb[key], "r"]]) {
      row.append(absent(v) ? sided("span", "bc-num bc-missing", side, "not recorded") : sided("span", "bc-num bc-heavy", side, String(v)));
    }
    frame.append(row);
  });

  frame.append(text("bc-heading bc-heavy bc-center bc-h-placements", "PLACEMENTS"));
  const rows = [["top8", "TOP 8"], ...(a.top32 && b.top32 ? [["top32", "TOP 32"]] : [])];  // no top32 column yet: no row
  const most = Math.max(1, ...rows.flatMap(([k]) => [ma[k] ?? 0, mb[k] ?? 0]));
  rows.forEach(([key, label], i) => {
    const row = el("div", "bc-prow");
    row.style.top = `${651 + i * 55}px`;
    row.append(el("div", "bc-plabel", label));
    for (const [v, side] of [[ma[key], "l"], [mb[key], "r"]]) {
      if (absent(v)) {
        row.append(sided("span", "bc-pnum bc-missing", side, "not recorded"));
        continue;
      }
      const bar = sided("div", "bc-pbar", side);
      bar.style.width = `${Math.round((v / most) * H2H.bar)}px`;
      row.append(bar, sided("span", "bc-pnum bc-heavy", side, String(v)));
    }
    frame.append(row);
  });

  for (const [p, side] of [[a, "l"], [b, "r"]]) {
    const name = (p.name || "").toUpperCase();
    const node = sided("p", "bc-t bc-pname bc-heavy", side, name);
    if (name.length > 9) node.style.fontSize = `${Math.max(48, Math.round((88 * 9) / name.length))}px`;  // keeps clear of the record
    frame.append(node);
  }
  if (record) {  // the set record in the bottom strip: the left player's wins, then losses, in the mode shown
    const r = record;
    frame.append(sided("p", "bc-t bc-score", "l", absent(r.wins) ? "–" : String(r.wins)), text("bc-vs bc-heavy", "VS"),
      sided("p", "bc-t bc-score", "r", absent(r.losses) ? "–" : String(r.losses)));
  } else {
    frame.append(text("bc-vs bc-heavy", "VS"));
  }
  return squeezeWords(frame);
}

// Set list: the sets side by side on one 1920x1080 frame, newest first, each a tile with its event, its date and the
// score. A head-to-head's or two teams' sets (card.sides) keep the first side on the left, in orange, the other in teal,
// as the other cards do, with the record between them in the header; an event's sets name each set's two players.
// One to four sets fill one row; five to eight two rows; past eight the latest eight, and the header says so.
const SIDE = { edge: 24, slot: 200, overlap: 100, middle: 760 };  // header: legend slots, and the names' inner edge
export const TILES = { most: 8, perRow: 4, left: 60, top: 330, width: 1800, height: 710, gap: 30, maxWidth: 430 };

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
const REGIONS = [["North America", "NA"], ["South America", "SA"], ["Southeast Asia", "SEA"], ["Europe", "EU"],
  ["Middle East & North Africa", "MENA"], ["Middle East and North Africa", "MENA"], ["Australia", "AUS"],
  ["Oceania", "OCE"], ["Japan", "JPN"], ["Brazil", "BRZ"]];

// An event's name written short for a tile: the tournament without the event name after " / " or the mode, the
// regions abbreviated, "Brawlhalla" dropped ("Winter Championship - North America 2025 / Brawlhalla Championship 2v2"
// is "Winter Championship NA 2025"; "Brawlhalla World Championship Expo 2024" is "BCX 2024"). Display only: the list
// below the card keeps the full name.
export function shortEvent(name) {
  if (!name) return "";
  let s = name.split(" / ")[0].replace(/\s*\([^)]*\)\s*/g, " ").replace(/\s*-\s*(1v1|2v2)\s*$/i, "");
  s = s.replace(/^Brawlhalla World Championship Expo/i, "BCX").replace(/^Brawlhalla World Championship(?! Expo)/i, "Worlds");
  for (const [long, abbr] of REGIONS) s = s.replaceAll(long, abbr);
  s = s.replace(/^Brawlhalla\s*(-\s*)?/i, "").replace(/\s+-\s+/g, " ").replace(/\s{2,}/g, " ").trim();
  // "NA Spring Championship 2022" reads as the newer names do, "Spring Championship NA 2022"
  const lead = s.match(/^(NA|SA|SEA|EU|MENA|AUS|OCE|JPN|BRZ) (.+?)( \d{4})?$/);
  return lead ? `${lead[2]} ${lead[1]}${lead[3] || ""}` : s;
}

function day(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}` : "DATE NOT RECORDED";
}

// One tile's score from the left side's view: [left games, right games, whether the left side won].
function sidedScore(s, sides) {
  const leftWon = s.first_won === undefined ? s.winner === sides[0] : s.first_won;
  const [l, r] = leftWon ? [s.winner_games, s.loser_games] : [s.loser_games, s.winner_games];
  return { l, r, leftWon };
}

function tile(s, card) {
  const node = el("div", "bc-tile");
  const band = el("div", "bc-tile-band");
  // An event's sets share the event, which the header names: each band names the set's two players instead, the
  // winner first, as the score reads.
  band.append(el("span", "bc-tile-event bc-heavy", (card.sides ? shortEvent(s.event || card.event)
    : `${s.winner || ""} vs ${s.loser || ""}`).toUpperCase()));
  node.append(band);
  node.append(el("span", "bc-tile-date", [day(s.date), card.modes && s.mode ? s.mode.toUpperCase() : null].filter(Boolean).join(" · ")));
  const scored = !absent(s.winner_games);
  if (card.sides) {
    const { l, r, leftWon } = sidedScore(s, card.sides);
    const score = el("p", "bc-tile-score bc-heavy");
    if (scored) {
      score.append(el("span", leftWon ? "bc-l" : "bc-lost", String(l)), el("span", "bc-dash", "–"),
        el("span", leftWon ? "bc-lost" : "bc-r", String(r)));
    } else {
      score.classList.add("bc-missing");
      score.textContent = "SCORE NOT RECORDED";
    }
    node.append(score);
    const won = el("div", `bc-tile-won ${leftWon ? "bc-l" : "bc-r"}`);
    won.append(el("span", "bc-tile-won-word", "WON"), el("span", "bc-tile-won-name", (leftWon ? card.sides[0] : card.sides[1]).toUpperCase()));
    node.append(won);
  } else {  // an event's set: the score winner first, and who won
    const score = scored ? el("p", "bc-tile-score bc-heavy") : el("p", "bc-tile-score bc-missing", "SCORE NOT RECORDED");
    if (scored) score.append(el("span", "bc-l", String(s.winner_games)), el("span", "bc-dash", "–"), el("span", "bc-lost", String(s.loser_games)));
    const won = el("div", "bc-tile-won bc-l");
    won.append(el("span", "bc-tile-won-word", "WON"), el("span", "bc-tile-won-name", (s.winner || "").toUpperCase()));
    node.append(score, won);
  }
  return node;
}

export function setsFrame(card) {
  const sets = [...(card.sets || [])].reverse();  // newest first
  const shown = sets.slice(0, TILES.most);
  const frame = el("div", "bc-frame bc-wsets");
  frame.setAttribute("role", "img");
  frame.setAttribute("aria-label", card.title);
  frame.append(shapes([["0,0 1920,0 1920,37 0,37", "var(--bc-cream)"]]));
  frame.append(text("bc-strip-text", (card.scope || "").toUpperCase()));

  const heading = card.event ? card.title.toUpperCase()
    : card.mode === "2v2" ? "OFFICIAL 2V2 SETS" : !card.modes || card.mode === "1v1" ? "OFFICIAL 1V1 SETS" : "OFFICIAL SETS";
  frame.append(text("bc-wsets-heading bc-heavy", heading));
  if (card.sides) {
    const wins = sets.filter((s) => sidedScore(s, card.sides).leftWon).length;
    // Each side's legends on the outside of its name (one, or a team's two overlapping), facing the middle.
    const legends = card.legends || [[null], [null]];
    const reach = (n) => SIDE.slot + SIDE.overlap * (n - 1);
    legends.forEach((side, k) => side.forEach((legend, i) => {
      const slot = legendSlot(legend, k === 1);
      slot.classList.add("bc-wlegend", k ? "bc-r" : "bc-l");
      slot.style.left = `${k ? 1920 - SIDE.edge - reach(side.length) + i * SIDE.overlap : SIDE.edge + i * SIDE.overlap}px`;
      frame.append(slot);
    }));
    const left = el("p", "bc-t bc-wsets-side bc-l bc-heavy", card.sides[0].toUpperCase());
    const right = el("p", "bc-t bc-wsets-side bc-r bc-heavy", card.sides[1].toUpperCase());
    const inner = (n) => SIDE.edge + reach(n) + 16;  // where a side's name may start, from the frame's edge
    left.style.left = `${inner(legends[0].length)}px`;
    left.style.width = `${SIDE.middle - inner(legends[0].length)}px`;
    right.style.left = `${1920 - SIDE.middle}px`;
    right.style.width = `${SIDE.middle - inner(legends[1].length)}px`;
    for (const [node, side] of [[left, legends[0]], [right, legends[1]]]) if (side.length > 1) node.classList.add("bc-wsets-team");
    frame.append(left, right);
    if (card.sets) {
      const record = el("p", "bc-t bc-wsets-record bc-heavy");
      record.append(el("span", "bc-l", String(wins)), el("span", "bc-dash", "–"), el("span", "bc-r", String(sets.length - wins)));
      frame.append(record);
    }
  } else if (card.event) {
    frame.append(text("bc-wsets-event bc-heavy", `${card.event}${card.date ? ` · ${day(card.date)}` : ""}`.toUpperCase()));
  }
  if (sets.length > TILES.most) frame.append(text("bc-wsets-note", `THE LATEST ${TILES.most} OF ${sets.length} · NEWEST FIRST`));
  else if (sets.length > 1) frame.append(text("bc-wsets-note", "NEWEST FIRST"));

  const cols = Math.min(shown.length, TILES.perRow);
  const rows = Math.ceil(shown.length / TILES.perRow);
  if (shown.length) {
    const w = Math.min(TILES.maxWidth, (TILES.width - TILES.gap * (TILES.perRow - 1)) / TILES.perRow);
    const h = rows > 1 ? (TILES.height - TILES.gap) / 2 : 430;
    const top = TILES.top + (rows > 1 ? 0 : (TILES.height - h) / 2);
    shown.forEach((s, i) => {
      const inRow = i < TILES.perRow ? cols : shown.length - TILES.perRow;
      const rowWidth = inRow * w + (inRow - 1) * TILES.gap;
      const t = tile(s, card);
      t.style.left = `${TILES.left + (TILES.width - rowWidth) / 2 + (i % TILES.perRow) * (w + TILES.gap)}px`;
      t.style.top = `${top + Math.floor(i / TILES.perRow) * (h + TILES.gap)}px`;
      t.style.width = `${w}px`;
      t.style.height = `${h}px`;
      if (rows > 1) t.classList.add("bc-tile-short");
      frame.append(t);
    });
  } else {
    frame.append(text("bc-wsets-empty bc-heavy", card.sets === null ? `${card.total} SETS: TOO MANY TO LIST`
      : card.mode && card.mode !== "1v1 and 2v2" ? `NO ${card.mode.toUpperCase()} SETS` : "NO SETS RECORDED"));
  }
  return { frame: squeezeWords(frame), width: 1920 };
}

// 2v2 (reference: the North America elimination final, Moni & AnimeFan1266 vs Raydish & megD, scaled to 1920 wide).
// Four player columns, each with its own earnings, medals (bronze, silver, gold, as the reference orders them) and
// placements, and the row headings between the teams. kind "teams": two teams, with the record between them under the
// headings. kind "team": one partnership on the left, and their results together on the right.
const TEAMS = { x: [199, 586, 1334, 1721], w: 309,
  strip: "0,931 70,921 150,934 214,912 300,926 360,918 470,936 540,915 640,928 760,909 840,926 960,914 1080,926 1160,909 1280,928 1380,915 1450,936 1560,918 1620,926 1706,912 1770,934 1850,921 1920,931 1920,1080 0,1080" };
const RAISED = TEAMS.strip.replace(/(\d+),(\d+)/g, (all, x, y) => (Number(y) < 1000 ? `${x},${Number(y) - 14}` : all));

// A row of number boxes, each a colored number over a dark label, spanning `span` px centered on x.
function boxes(frame, x, top, cells, side, span = TEAMS.w, gap = 6) {
  const width = (span - gap * (cells.length - 1)) / cells.length;
  cells.forEach(([label, value], i) => {
    const box = el("div", `bc-tbox bc-${side}`);
    box.style.left = `${x - span / 2 + i * (width + gap)}px`;
    box.style.top = `${top}px`;
    box.style.width = `${width}px`;
    box.append(absent(value) ? el("span", "bc-tnum bc-missing", "not recorded") : el("span", "bc-tnum bc-heavy", String(value)),
      el("span", "bc-tlabel", label));
    frame.append(box);
  });
}

function column(frame, p, i, mode, side) {
  const x = TEAMS.x[i];
  const m = p.modes[mode] || {};
  if ("earnings" in p) {
    const box = el("div", `bc-tmoney bc-${side}`);
    box.style.left = `${x - TEAMS.w / 2}px`;
    box.style.width = `${TEAMS.w}px`;
    box.append(absent(p.earnings.amount) ? el("span", "bc-missing", "not recorded")
      : el("span", "bc-heavy", money.format(p.earnings.amount)));
    frame.append(box);
  }
  boxes(frame, x, 288, [["BRONZE", m.third], ["SILVER", m.second], ["GOLD", m.first]], side);
  boxes(frame, x, 452, [...(p.top32 ? [["TOP 32", m.top32]] : []), ["TOP 8", m.top8]], side);
  const legend = legendSlot(p.legend, side === "r");
  legend.classList.add("bc-tlegend", `bc-${side}`);
  legend.style.left = `${x - 180}px`;
  frame.append(legend);
}

function teamNames(frame, players) {
  players.forEach((p, i) => {
    const name = (p.name || "").toUpperCase();
    const node = el("p", "bc-t bc-tname bc-heavy", name);
    node.style.left = `${TEAMS.x[i]}px`;
    if (name.length > 9) node.style.fontSize = `${Math.max(30, Math.round((60 * 9) / name.length))}px`;
    frame.append(node);
  });
}

function ordinal(n) {
  const tens = n % 100;
  return `${n}${tens >= 11 && tens <= 13 ? "TH" : ({ 1: "ST", 2: "ND", 3: "RD" }[n % 10] || "TH")}`;
}

export function teamsFrame(card, mode = "2v2") {
  const team = card.kind === "team";
  const players = team ? card.players : card.teams.flat();
  const frame = el("div", "bc-frame bc-teams");
  frame.setAttribute("role", "img");
  frame.setAttribute("aria-label", team ? `${players[0].name} and ${players[1].name} as a team`
    : `${card.names[0]} against ${card.names[1]}`);
  frame.append(shapes([["0,0 1920,0 1920,37 0,37", "var(--bc-cream)"]]));
  const strip = [`players: ${scopeLine(mode, players.some((p) => p.crew))}`,
    team ? "together: official 2v2 results" : "record: official 2v2 sets between the teams"];
  frame.append(text("bc-strip-text", strip.join(" · ").toUpperCase()));

  players.forEach((p, i) => column(frame, p, i, mode, team || i < 2 ? "l" : "r"));
  // The bottom strip goes over the legends' feet, its border orange under the left team and teal under the right.
  frame.append(shapes([[RAISED, "var(--bc-orange)"]]));
  if (!team) {
    const teal = shapes([[RAISED, "var(--bc-teal)"]]);
    teal.style.clipPath = "inset(0 0 0 50%)";
    frame.append(teal);
  }
  frame.append(shapes([[TEAMS.strip, "var(--bc-dark)"]]));
  teamNames(frame, players);

  const headings = [["EARNINGS", 152], ["MEDALS", 300], ["PLACEMENTS", 464]];
  if (!players.some((p) => "earnings" in p)) headings.shift();
  for (const [word, top] of headings) {
    const h = text("bc-theading bc-heavy", word);
    h.style.top = `${top}px`;
    frame.append(h);
  }

  if (team) {
    const t = card.together;
    const [from, to] = [t.first?.slice(0, 4), t.latest?.slice(0, 4)];
    const span = from ? (from === to ? from : `${from}–${to}`) : null;
    frame.append(text("bc-together bc-heavy", "TOGETHER"), text("bc-together-sub", `2V2${span ? ` · ${span}` : ""}`));
    boxes(frame, 1528, 288, [["EVENTS", t.events], ["WINS", t.wins], ["MEDALS", t.medals]], "l", 696, 10);
    boxes(frame, 1528, 452, [["TOP 8", t.top8s], ["BEST", absent(t.best) ? null : ordinal(t.best)]], "l", 696, 10);
    frame.append(text("bc-tamp bc-heavy", "&"));
  } else {
    const r = card.record;
    frame.append(text("bc-vs bc-heavy", "VS"), text("bc-tsets bc-heavy", "2V2 SETS"));
    if (r.sets) {
      const score = el("p", "bc-t bc-tscore bc-heavy");
      score.append(el("span", "bc-l", String(r.wins)), el("span", "bc-dash", "–"), el("span", "bc-r", String(r.losses)));
      frame.append(score);
    } else {
      frame.append(text("bc-tnone", "NO SETS BETWEEN THEM"));
    }
  }
  return squeezeWords(frame);
}
