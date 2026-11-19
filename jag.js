// Jagged edges, as brawlhalla.com cuts its panels: each element gets an SVG clipPath in objectBoundingBox units, with
// near-straight sides pushed in by a few pixels at a handful of points, and a small triangular chip or two bitten into
// an edge. The shapes are generated here (none of brawlhalla.com's path data), seeded per element so each keeps its
// shape, and refitted in pixels whenever the element resizes.
//
//   <div class="jag" data-jag="card" data-seed="21">   then jagify(root)
//
// clip-path clips shadows too, so put a shadow on an unclipped parent (filter: drop-shadow(...)).

export const JAG_STYLES = {
  card: { perSide: [3, 5], inset: 7, chips: [1, 2], chipW: [10, 18], chipD: [5, 9] },
  bubble: { perSide: [2, 3], inset: 3, chips: [0, 1], chipW: [6, 9], chipD: [3, 5] },
  input: { perSide: [2, 4], inset: 3, chips: [0, 1], chipW: [6, 10], chipD: [3, 5] },
  button: { perSide: [1, 2], inset: 3, chips: [0, 1], chipW: [5, 8], chipD: [3, 4] },
  "torn-left": { torn: "left" },
  "torn-bottom": { torn: "bottom" },
};

function rng(seed) {
  let s = seed >>> 0 || 1;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

// The clip path for a w x h element, in 0-1 units.
export function jagPath(w, h, style, seed) {
  const R = rng(seed);
  const between = (a, b) => a + (b - a) * R();
  const int = (a, b) => Math.floor(between(a, b + 1));
  const pts = [];
  if (style.torn === "left") {  // a ragged left edge, 0-14 px deep
    const edge = 14, step = 18;
    pts.push([edge * 0.5, 0], [w, 0], [w, h]);
    for (let y = h - step; y > 0; y -= step * between(0.5, 1.4)) {
      pts.push([R() < 0.1 ? between(0, 3) : between(4, 14), y]);
    }
  } else if (style.torn === "bottom") {  // flat top and sides, a ragged bottom like torn paper
    const bottom = h - 14, step = 16;
    pts.push([0, 0], [w, 0], [w, bottom + between(2, 10)]);
    for (let x = w - step; x > 0; x -= step * between(0.5, 1.4)) {
      pts.push([x, bottom + (R() < 0.12 ? between(9, 14) : between(0, 7))]);
    }
    pts.push([0, bottom + between(2, 10)]);
  } else {
    const I = style.inset;
    const edges = [  // top, right, bottom, left: t along the side, d inward
      (t, d) => [t * w, d], (t, d) => [w - d, t * h], (t, d) => [w - t * w, h - d], (t, d) => [d, h - t * h],
    ];
    const chipCount = int(...style.chips);
    const chipEdges = new Set();
    while (chipEdges.size < chipCount) chipEdges.add(int(0, 3));
    edges.forEach((edge, ei) => {
      const n = int(...style.perSide);
      const ts = [0];
      for (let k = 0; k < n; k++) ts.push(between(0.08, 0.92));
      ts.sort((a, b) => a - b);
      const len = ei % 2 ? h : w;
      let chipAt = chipEdges.has(ei) ? between(0.15, 0.85) : -1;
      ts.forEach((t, k) => {
        pts.push(edge(t, between(0, I) * (k === 0 ? 0.6 : 1)));
        const nextT = ts[k + 1] ?? 1;
        if (chipAt > t && chipAt < nextT) {  // a small triangular bite into the edge
          const cw = between(...style.chipW) / len;
          const cd = between(...style.chipD) + I * 0.5;
          pts.push(edge(chipAt - cw / 2, between(0, I * 0.6)), edge(chipAt + between(-0.3, 0.3) * cw, cd),
            edge(chipAt + cw / 2, between(0, I * 0.6)));
          chipAt = -1;
        }
      });
    });
  }
  return "M" + pts.map(([x, y]) => `${(x / w).toFixed(4)} ${(y / h).toFixed(4)}`).join("L") + "Z";
}

const SVG = "http://www.w3.org/2000/svg";
let defs = null;
let count = 0;

function clipDefs() {
  if (defs) return defs;
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("width", "0");
  svg.setAttribute("height", "0");
  svg.setAttribute("aria-hidden", "true");
  svg.style.position = "absolute";
  defs = document.createElementNS(SVG, "defs");
  svg.append(defs);
  document.body.prepend(svg);
  return defs;
}

// Cut one element: its clip path is made once and refitted to its current size.
export function applyJag(el) {
  if (!el.dataset.jagId) el.dataset.jagId = `jag${++count}`;
  const id = el.dataset.jagId;
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height) return;
  let cp = document.getElementById(id);
  if (!cp) {
    cp = document.createElementNS(SVG, "clipPath");
    cp.id = id;
    cp.setAttribute("clipPathUnits", "objectBoundingBox");
    cp.append(document.createElementNS(SVG, "path"));
    clipDefs().append(cp);
  }
  if (!el.dataset.seed) el.dataset.seed = String(Math.floor(Math.random() * 1e6));
  cp.firstChild.setAttribute("d", jagPath(r.width, r.height, JAG_STYLES[el.dataset.jag] || JAG_STYLES.card, +el.dataset.seed));
  el.style.clipPath = `url(#${id})`;
}

const observer = new ResizeObserver((entries) => entries.forEach((e) => applyJag(e.target)));

// Cut every .jag inside root (root itself too), and keep them fitted as they resize.
export function jagify(root = document) {
  const els = [...root.querySelectorAll(".jag")];
  if (root.classList?.contains("jag")) els.unshift(root);
  for (const el of els) {
    applyJag(el);
    observer.observe(el);
  }
}
