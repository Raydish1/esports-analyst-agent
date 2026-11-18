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

function text(className, value) {
  return el("p", `bc-t ${className}`, value);
}

function legendSlot(legend) {
  const slot = el("div", "bc-legend");
  if (legend?.url) {  // no entry, no file: the slot stays empty, never a guessed legend
    const img = el("img");
    img.src = legend.url;
    img.alt = legend.name;
    img.style.transform = `translate(${legend.offset_x || 0}px, ${legend.offset_y || 0}px) scale(${legend.scale || 1})`;
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

function missing(className) {
  return el("span", `${className} bc-missing`.trim(), "not recorded");
}

// A card's frame, scaled to fit its container's width.
export function scaled(frame) {
  const box = el("div", "bc-scale");
  box.append(frame);
  const fit = () => { frame.style.transform = `scale(${box.clientWidth / 1920})`; };
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

  const parts = [card.scope];
  if ("earnings" in p && p.earnings.amount !== null) parts.push(`Earnings: career, ${p.earnings.source}, as of ${p.earnings.as_of}.`);
  frame.append(text("bc-scope", parts.join(" ")));
  return frame;
}
