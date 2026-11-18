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

const HEAVY = [".bc-name", ".bc-heading", ".bc-pname", ".bc-vs", ".bc-sets-heading", ".bc-sets-title", ".bc-earnings",
  ".bc-count", ".bc-value", ".bc-money", ".bc-num", ".bc-pnum", ".bc-score", ".bc-entry-score"]
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
function legendSlot(legend, mirror = false) {
  const slot = el("div", "bc-legend");
  if (legend?.url) {  // no entry, no file: the slot stays empty, never a guessed legend
    const img = el("img");
    img.src = legend.url;
    img.alt = legend.name;
    img.style.transform = `translate(${legend.offset_x || 0}px, ${legend.offset_y || 0}px) scale(${legend.scale || 1})` +
      (mirror ? " scaleX(-1)" : "");
    img.addEventListener("error", () => img.remove());
    slot.append(img);
  }
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
  return squeezeWords(frame);
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
  if (card.record) strip.push(`record: official 1v1 sets${card.record.unscored ? `, ${card.record.unscored} with no recorded score` : ""}`);
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
  if (card.record) {  // the set record in the bottom strip: the left player's wins, then losses
    const r = card.record;
    frame.append(sided("p", "bc-t bc-score", "l", absent(r.wins) ? "–" : String(r.wins)), text("bc-vs bc-heavy", "VS"),
      sided("p", "bc-t bc-score", "r", absent(r.losses) ? "–" : String(r.losses)));
  } else {
    frame.append(text("bc-vs bc-heavy", "VS"));
  }
  return squeezeWords(frame);
}

// Set list (reference: the "Matches" sidebar of IMG_2447, scaled to 1920 wide). Each sidebar column holds five sets, as
// the reference does, and columns sit side by side, up to SIDEBARS; past that the last slot says how many more.
export const SIDEBAR = { width: 236, perColumn: 5, pitch: 103, columns: 8 };

export function setsFrame(card) {
  const sets = card.sets || [];
  const slots = SIDEBAR.perColumn * SIDEBAR.columns;
  const shown = sets.length > slots ? sets.slice(0, slots - 1) : sets;
  const columns = Math.max(1, Math.ceil((shown.length + (sets.length > slots ? 1 : 0)) / SIDEBAR.perColumn));
  const width = columns * SIDEBAR.width;
  const frame = el("div", "bc-frame bc-sets");
  frame.style.width = `${width}px`;
  frame.setAttribute("role", "img");
  frame.setAttribute("aria-label", card.title);
  // The dark plate at the top (the reference's logo area, traced; the logo itself is left out) holds what the list is.
  const edge = [[236, 128], [232, 135], [136, 204], [104, 192], [80, 200], [72, 217], [0, 261]];
  const pts = (list) => list.map(([x, y]) => `${x},${y}`).join(" ");
  frame.append(shapes([
    [pts([...edge, ...edge.map(([x, y]) => [x, y + 12]).reverse()]), "var(--bc-orange)"],
    [`0,0 236,0 ${pts(edge)}`, "#170c08"],
  ]));
  frame.append(text("bc-sets-subject", (card.event ? `${card.event}${card.date ? ` · ${card.date}` : ""}` : card.title).toUpperCase()));
  frame.append(text("bc-sets-heading bc-heavy", "MATCHES"));
  // The first player of a head-to-head stays on top, with the score from their side; an event's winner is on top.
  const top = card.event ? null : (card.title.match(/^Sets between (.+) and (.+)$/) || [])[1];
  shown.forEach((s, i) => {
    const column = Math.floor(i / SIDEBAR.perColumn);
    const entry = el("div", "bc-entry");
    entry.style.left = `${column * SIDEBAR.width}px`;
    entry.style.top = `${347 + (i % SIDEBAR.perColumn) * SIDEBAR.pitch}px`;
    const flip = top && s.loser === top;
    const [upper, lower] = flip ? [s.loser, s.winner] : [s.winner, s.loser];
    const score = absent(s.winner_games) ? null
      : flip ? `${s.loser_games} - ${s.winner_games}` : `${s.winner_games} - ${s.loser_games}`;
    entry.append(el("span", "bc-entry-name", (upper || "").toUpperCase()),
      score === null ? el("span", "bc-entry-score bc-missing", "SCORE NOT RECORDED") : el("span", "bc-entry-score bc-heavy", score),
      el("span", "bc-entry-name", (lower || "").toUpperCase()));
    if (i % SIDEBAR.perColumn) entry.classList.add("bc-ruled");
    frame.append(entry);
  });
  if (sets.length > slots) {
    const more = el("div", "bc-entry bc-ruled bc-more");
    more.style.left = `${(SIDEBAR.columns - 1) * SIDEBAR.width}px`;
    more.style.top = `${347 + (SIDEBAR.perColumn - 1) * SIDEBAR.pitch}px`;
    more.append(el("span", "bc-entry-score bc-heavy", `+${sets.length - shown.length}`), el("span", "bc-entry-name", "MORE SETS"));
    frame.append(more);
  }
  if (!sets.length) frame.append(text("bc-sets-empty", card.sets === null ? `${card.total} SETS: TOO MANY TO LIST` : "NO SETS RECORDED"));
  const foot = el("div", "bc-sets-foot");  // the title and what it counts, stacked, so a long title can't overlap
  foot.append(el("p", "bc-sets-title bc-heavy", card.event ? card.title.toUpperCase() : "OFFICIAL 1V1 SETS"),
    el("p", "bc-sets-scope", card.scope));
  frame.append(foot);
  for (let c = 0; c < columns; c++) {  // each column's gold rule on its right edge
    const rule = el("div", "bc-sets-rule");
    rule.style.left = `${(c + 1) * SIDEBAR.width - 4}px`;
    frame.append(rule);
  }
  return { frame: squeezeWords(frame), width };
}
