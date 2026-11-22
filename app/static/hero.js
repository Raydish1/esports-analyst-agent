// The particle hero (design: particle-hero.html, tuned in cortex-draft.html): each character's art is sampled into
// tens of thousands of particles that hold its shape, then morph into the next character's. Weapons glow, flow and
// throw sparks inside hand-drawn masks; a holo scan sweeps down; bright specks twinkle; partial clearing leaves trails.
// Settings, the background and the art with its masks come from hero/hero.json.
//
// The canvas background fades to exactly the page's navy at its edges, so there is no visible box. Rendering pauses
// while the hero is off-screen; characters refit when the canvas changes shape (wide art must fit the half column).

const GLYPHS = " .:-=+*#%@";

const particleVS = `
attribute vec3 aA, aB, aCA, aCB;
attribute vec4 aMA, aMB;
attribute vec4 aRnd;
uniform float uProgress, uTime, uAspect, uStagger, uBurst, uSwirl, uSize, uDpr, uCenterX, uMouseR;
uniform float uWeaponGlow, uWeaponFlow, uSparks, uScan, uScanSpeed, uTwinkle, uAscii, uAsciiSize, uAsciiDensity;
uniform float uAutoGlow, uLift, uHum, uRim;
uniform vec3 uRimColor;
uniform vec2 uRot, uMouse;
varying vec3 vCol;
varying float vAlpha, vGlyph, vGlow, vAsc;

float ease(float t) { return t < 0.5 ? 4.0*t*t*t : 1.0 - pow(-2.0*t + 2.0, 3.0) / 2.0; }
mat2 rot(float a) { float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }
vec3 heat(vec3 c) { return min(c * 1.45 + 0.06 + normalize(c + 0.001) * 0.12, vec3(1.0)); }

void main() {
  float local = clamp((uProgress - aRnd.w * uStagger) / (1.0 - uStagger), 0.0, 1.0);
  float e = ease(local);
  float arc = sin(3.14159265 * e);
  vec4 meta = mix(aMA, aMB, e);
  float weapon = meta.x * (1.0 - arc);       // weapon effects fade out mid-morph
  float speck = meta.y;
  float emis = meta.z * (1.0 - arc);
  float rimW = meta.w * (1.0 - arc);
  float energy = max(weapon, emis);

  vec3 base = mix(aA, aB, e);
  vec3 p = base;
  p += (aRnd.xyz - 0.5) * 2.0 * uBurst * arc;
  p.xz = rot(arc * uSwirl * (aRnd.w - 0.5) * 2.0) * p.xz;
  p += 0.006 * vec3(sin(uTime*1.3 + aRnd.x*40.0), cos(uTime*1.1 + aRnd.y*40.0), sin(uTime*0.9 + aRnd.z*40.0));
  p.z += energy * uLift;
  p += energy * uHum * vec3(sin(uTime*23.0 + aRnd.x*90.0), sin(uTime*19.0 + aRnd.y*90.0), 0.0);

  vec3 c = mix(aCA, aCB, e);
  float alpha = 0.92 - arc * 0.25;
  float size = uSize;
  float glow = 0.0;

  // weapon energy: a pulse, and a highlight travelling along the weapon
  float flow = pow(0.5 + 0.5 * sin((base.x * 0.6 - base.y) * 9.0 - uTime * 3.2), 6.0);
  float wg = weapon * uWeaponGlow * (0.35 + 0.2 * sin(uTime * 2.3) + uWeaponFlow * 0.9 * flow);
  c = mix(c, heat(c), clamp(wg * 0.85, 0.0, 1.0));
  size *= 1.0 + wg * 0.6;
  glow += wg;

  // auto energy: a brightness wave crawling across the most saturated pixels
  float crawl = 0.5 + 0.5 * sin(uTime * 2.6 + base.x * 14.0 + base.y * 7.0);
  float eg = emis * uAutoGlow * (0.3 + 0.9 * crawl * crawl);
  c = mix(c, heat(c), clamp(eg * 0.85, 0.0, 1.0));
  size *= 1.0 + eg * 0.5;
  glow += eg;

  // rim light on the silhouette
  c = mix(c, uRimColor, clamp(rimW * uRim, 0.0, 1.0) * 0.85);
  glow += rimW * uRim * 0.6;

  // sparks: some weapon particles drift up and fade, then respawn
  if (weapon > 0.5 && aRnd.y < uSparks) {
    float ph = fract(uTime * (0.25 + aRnd.z * 0.35) + aRnd.x * 7.0);
    p += vec3(sin(ph * 6.0 + aRnd.w * 30.0) * 0.04, ph * 0.38, (aRnd.z - 0.5) * 0.1 * ph);
    alpha *= 1.0 - ph;
    size *= 1.0 + (1.0 - ph) * 0.8;
    c = mix(c, c * 1.6 + 0.1, 0.5);
    glow += 1.0 - ph;
  }

  // twinkle on bright specks, and a rare glint anywhere
  float tw = (speck + step(0.992, aRnd.y) * 0.8) * uTwinkle *
             pow(0.5 + 0.5 * sin(uTime * (1.5 + aRnd.z * 4.0) + aRnd.x * 60.0), 10.0);
  c += tw * 0.8;
  size *= 1.0 + tw * 1.6;
  glow += tw;

  p.xz = rot(uRot.x) * p.xz;
  p.yz = rot(uRot.y) * p.yz;

  // holo scan band, sweeping top to bottom in model space
  float scanY = 1.25 - mod(uTime * uScanSpeed, 1.0) * 2.8;
  float sd = base.y - scanY;
  float sb = exp(-sd * sd / 0.0025) * uScan * (1.0 - arc);
  float trail = sd > 0.0 ? exp(-sd * 6.0) * 0.25 * uScan * (1.0 - arc) : 0.0;
  c += (sb * 0.7 + trail) * vec3(0.3, 0.7, 1.0);
  p.x += sb * 0.025 * sin(base.y * 180.0 + uTime * 20.0);
  size *= 1.0 + sb * 0.8;
  glow += sb;

  float camZ = 3.2;
  float persp = camZ / (camZ - p.z);
  vec2 screen = p.xy * persp;
  screen.x += uCenterX * uAspect;
  vec2 d = screen - uMouse;
  screen += normalize(d + 1e-5) * smoothstep(uMouseR, 0.0, length(d)) * uMouseR * 0.55;

  // ASCII: pick a glyph from brightness (with an occasional flicker)
  float lum = dot(c, vec3(0.299, 0.587, 0.114));
  float g = floor(clamp(lum, 0.0, 0.999) * 9.0) + 1.0;
  if (fract(uTime * 0.6 + aRnd.y * 13.0) > 0.97) g = floor(aRnd.z * 9.0) + 1.0;
  vGlyph = g;
  // mode 1: always ASCII; mode 2: glyphs mid-flight, dots again as they land
  float asc = uAscii > 1.5 ? step(0.3, arc) : step(0.5, uAscii);
  vAsc = asc;
  if (asc > 0.5) {
    if (uAscii < 1.5 && aRnd.z > uAsciiDensity && glow < 0.3) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); gl_PointSize = 0.0; return; }
    size = uAsciiSize * (1.0 + glow * 0.4);
  }

  gl_Position = vec4(screen.x / uAspect, screen.y, 0.0, 1.0);
  gl_PointSize = size * uDpr * persp * (1.0 + arc * 0.6);
  vCol = c;
  vAlpha = alpha;
  vGlow = glow;
}`;

const particleFS = `
precision mediump float;
uniform sampler2D uAtlas;
varying vec3 vCol;
varying float vAlpha, vGlyph, vGlow, vAsc;
void main() {
  if (vAsc > 0.5) {
    vec2 uv = vec2((vGlyph + gl_PointCoord.x) / 10.0, gl_PointCoord.y);
    float m = texture2D(uAtlas, uv).a;
    if (m < 0.05) discard;
    gl_FragColor = vec4(vCol, m * vAlpha);
    return;
  }
  vec2 q = gl_PointCoord - 0.5;
  float d = length(q);
  if (d > 0.5) discard;
  float core = smoothstep(0.5, 0.15, d);
  float halo = exp(-d * d * 18.0) * clamp(vGlow, 0.0, 1.5) * 0.6;   // soft bloom on glowing particles
  gl_FragColor = vec4(vCol, clamp(core * vAlpha + halo, 0.0, 1.0));
}`;

// The full-canvas background, drawn with partial alpha to leave motion trails.
const bgVS = `attribute vec2 aP; void main(){ gl_Position = vec4(aP, 0.0, 1.0); }`;
const bgFS = `
precision mediump float;
uniform vec2 uRes; uniform float uDpr, uFade; uniform vec3 uBgIn, uBgOut;
void main() {
  vec2 px = gl_FragCoord.xy / uDpr;
  vec2 res = uRes / uDpr;
  vec2 d = (px - res * vec2(0.5, 0.48)) / (res * 0.5);      // 1.0 at the canvas edges
  vec3 c = mix(uBgIn, uBgOut, smoothstep(0.0, 0.92, length(d)));
  gl_FragColor = vec4(c, uFade);
}`;

function loadImage(src) {
  return new Promise((resolve) => {
    const im = new Image();
    im.onload = () => resolve(im);
    im.onerror = () => resolve(null);  // missing art (it's git-ignored): that character is skipped
    im.src = src;
  });
}

function inPoly(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export async function startHero(canvas, caption, hero, settings = "hero/hero.json") {
  const gl = canvas.getContext("webgl", { antialias: false, alpha: false, preserveDrawingBuffer: true });
  if (!gl) return;  // no WebGL: the navy stage stays empty
  let spec;
  try {
    spec = await (await fetch(settings)).json();
  } catch {
    return;
  }
  const CONFIG = { ...spec.config };
  const theme = spec.theme;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    Object.assign(CONFIG, { holdMs: Infinity, scan: 0, twinkle: 0, sparks: 0, weaponFlow: 0, trails: 0 });
  }
  const loaded = await Promise.all(spec.images.map((i) => loadImage(i.src)));
  const images = spec.images.filter((_, i) => loaded[i]);
  const imgs = loaded.filter(Boolean);
  if (!imgs.length) return;

  let N = CONFIG.particleCount;
  // The particle count follows the hero's area on screen, so a big window keeps the density the settings were tuned
  // at (particleCount over REF_AREA, the hero in a window about 1300 px wide); a fixed count looked sparse full-screen.
  const REF_AREA = 420000, MIN_SCALE = 0.6, MAX_SCALE = 3.5;
  const particles = () => {
    const area = Math.max(1, canvas.clientWidth * canvas.clientHeight);
    const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, area / REF_AREA));
    return Math.round(CONFIG.particleCount * scale);
  };
  let aspect = 1, dpr = 1;

  function compile(type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  function program(vs, fs) {
    const p = gl.createProgram();
    gl.attachShader(p, compile(gl.VERTEX_SHADER, vs));
    gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }
  const prog = program(particleVS, particleFS);
  const bgProg = program(bgVS, bgFS);

  const quad = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quad);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const bgLoc = gl.getAttribLocation(bgProg, "aP");
  const bgU = {};
  for (const n of ["uBgIn", "uBgOut", "uRes", "uDpr", "uFade"]) bgU[n] = gl.getUniformLocation(bgProg, n);

  const buffers = {}, attrs = {};
  function attr(name, size, data) {
    const loc = gl.getAttribLocation(prog, name);
    const buf = buffers[name] || (buffers[name] = gl.createBuffer());
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
    attrs[name] = { loc, size, buf };
  }
  function bindParticleAttrs() {
    for (const { loc, size, buf } of Object.values(attrs)) {
      if (loc < 0) continue;
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0);
    }
  }
  const u = {};
  for (const n of ["uProgress", "uTime", "uAspect", "uStagger", "uBurst", "uSwirl", "uSize", "uDpr", "uCenterX", "uMouseR",
    "uRot", "uMouse", "uWeaponGlow", "uWeaponFlow", "uSparks", "uScan", "uScanSpeed", "uTwinkle", "uAscii", "uAsciiSize",
    "uAsciiDensity", "uAtlas", "uAutoGlow", "uLift", "uHum", "uRim", "uRimColor"]) u[n] = gl.getUniformLocation(prog, n);

  // The ASCII glyph atlas (ascii is off in the tuned look, but the shader samples it)
  const atlas = (() => {
    const cell = 48, c = document.createElement("canvas");
    c.width = cell * GLYPHS.length;
    c.height = cell;
    const x = c.getContext("2d");
    x.fillStyle = "#fff";
    x.textAlign = "center";
    x.textBaseline = "middle";
    x.font = `bold ${cell * 0.9}px ui-monospace, Menlo, Consolas, monospace`;
    [...GLYPHS].forEach((g, i) => x.fillText(g, i * cell + cell / 2, cell / 2 + 2));
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c);
    for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR],
      [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
    return tex;
  })();

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
    aspect = w / h;
  }

  // One character as particles: positions, colors, and per-particle weapon / speck / energy / rim weights.
  function sampleImage(img, info) {
    const s = CONFIG.sampleSize;
    const k = s / Math.max(img.width, img.height);
    const w = Math.round(img.width * k), h = Math.round(img.height * k);
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    const ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(img, 0, 0, w, h);
    const data = ctx.getImageData(0, 0, w, h).data;
    const L = (i) => (0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]) / 255;
    const opaque = [];
    for (let i = 0; i < w * h; i++) if (data[i * 4 + 3] > 140) opaque.push(i * 4);
    const emisOf = (i) => {
      const r = data[i] / 255, g = data[i + 1] / 255, b = data[i + 2] / 255;
      const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
      return Math.max(0, (mx > 0 ? (mx - mn) / mx : 0) - 0.5) * mx;
    };
    const sorted = opaque.map(emisOf).sort((a, b) => a - b);
    const emisThr = Math.max(1e-4, sorted[Math.floor(sorted.length * (1 - CONFIG.autoPercent))] || 1);
    // fit the height, but never wider than 90% of the canvas: wide art (Volkov's cape) must fit the half column
    const scale = Math.min(CONFIG.fitHeight / h, (CONFIG.fitHeight * 1.25) / w, (aspect * 2 * 0.9) / w);
    const lift = (v) => (CONFIG.colorFloor + (1 - CONFIG.colorFloor) * Math.pow(v / 255, 0.7)) * CONFIG.colorCeil;
    const weapons = info.weapons || [];
    const pts = new Array(N);
    for (let n = 0; n < N; n++) {
      const i = opaque[(Math.random() * opaque.length) | 0];
      const px = (i / 4) % w, py = ((i / 4) / w) | 0;
      const lum = L(i);
      let sum = 0, cnt = 0, edge = 0;
      for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) {
        const x2 = px + dx, y2 = py + dy;
        if (x2 < 0 || y2 < 0 || x2 >= w || y2 >= h) { edge = 1; continue; }
        const j = (y2 * w + x2) * 4;
        sum += L(j);
        cnt++;
        if (data[j + 3] < 60) edge = 1;  // next to transparency: the silhouette's rim
      }
      const emis = emisOf(i) >= emisThr ? 1 : 0;
      const speck = Math.max(0, Math.min(1, (lum - sum / cnt - 0.12) * 4));  // much brighter than around it
      const weapon = weapons.some((p) => inPoly(px / w, py / h, p)) ? 1 : 0;
      const x = (px + Math.random() - w / 2) * scale;
      const y = -(py + Math.random() - h / 2) * scale;
      const z = ((Math.random() - 0.5) * 0.6 + (lum - 0.5)) * CONFIG.depth;
      pts[n] = { x, y, z, r: lift(data[i]), g: lift(data[i + 1]), b: lift(data[i + 2]), weapon, speck, emis, edge,
        key: y + Math.random() * 0.08 };
    }
    pts.sort((a, b) => a.key - b.key);
    const pos = new Float32Array(N * 3), col = new Float32Array(N * 3), meta = new Float32Array(N * 4);
    pts.forEach((p, n) => {
      pos.set([p.x, p.y, p.z], n * 3);
      col.set([p.r, p.g, p.b], n * 3);
      meta.set([p.weapon, p.speck, p.emis, p.edge], n * 4);
    });
    return { pos, col, meta };
  }

  // Where the first character gathers from: each particle a short way from its own place in that character, inside
  // the box. A cloud of radius 1.4-2.6 around the middle reached past the canvas, so the gathering showed the
  // canvas's cut-off edges.
  function scatterCloud(target) {
    const pos = new Float32Array(N * 3), col = new Float32Array(N * 3), meta = new Float32Array(N * 4);
    const maxX = Math.max(0.2, aspect * 0.92), maxY = 0.92;
    const clamp = (v, m) => Math.max(-m, Math.min(m, v));
    for (let n = 0; n < N; n++) {
      const t = Math.random() * Math.PI * 2, r = 0.04 + Math.random() * 0.16;
      const x = target ? target.pos[n * 3] : 0, y = target ? target.pos[n * 3 + 1] : 0;
      pos.set([clamp(x + r * Math.cos(t) * 1.4, maxX), clamp(y + r * Math.sin(t), maxY), (Math.random() - 0.5) * 0.4], n * 3);
      col.set([0.45, 0.4, 0.9], n * 3);
    }
    return { pos, col, meta };
  }

  function makeRandoms() {
    const rnd = new Float32Array(N * 4);
    for (let i = 0; i < rnd.length; i++) rnd[i] = Math.random();
    attr("aRnd", 4, rnd);
  }

  function setPair(from, to) {
    attr("aA", 3, from.pos); attr("aCA", 3, from.col); attr("aMA", 4, from.meta);
    attr("aB", 3, to.pos); attr("aCB", 3, to.col); attr("aMB", 4, to.meta);
  }

  resize();
  N = particles();
  makeRandoms();
  gl.enable(gl.BLEND);
  let shapes = imgs.map((im, i) => sampleImage(im, images[i]));
  let cloud = scatterCloud(shapes[0]);
  let current = -1, next = 0, phase = "morph", phaseStart = performance.now(), fromIdx = -1;
  let visible = true;

  function startMorph(to, now) {
    fromIdx = current;
    setPair(current >= 0 ? shapes[current] : cloud, shapes[to]);
    next = to;
    phase = "morph";
    phaseStart = now;
    caption.textContent = images[to].name;
  }

  function resampleAll() {
    N = particles();
    shapes = imgs.map((im, i) => sampleImage(im, images[i]));
    cloud = scatterCloud(shapes[0]);
    makeRandoms();
    setPair(fromIdx >= 0 ? shapes[fromIdx] : cloud, shapes[next]);
  }

  function frame(now) {
    requestAnimationFrame(frame);
    if (!visible) return;
    const t = now / 1000;
    let progress = 1;
    if (phase === "morph") {
      progress = Math.min((now - phaseStart) / CONFIG.morphMs, 1);
      if (progress >= 1) { current = next; phase = "hold"; phaseStart = now; }
    } else if (now - phaseStart > CONFIG.holdMs && shapes.length > 1) {
      startMorph((current + 1) % shapes.length, now);
      progress = 0;
    }

    // background (partial alpha: trails)
    gl.useProgram(bgProg);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    for (let i = 0; i < 8; i++) gl.disableVertexAttribArray(i);
    gl.enableVertexAttribArray(bgLoc);
    gl.vertexAttribPointer(bgLoc, 2, gl.FLOAT, false, 0, 0);
    gl.uniform2f(bgU.uRes, canvas.width, canvas.height);
    gl.uniform1f(bgU.uDpr, dpr);
    gl.uniform3fv(bgU.uBgIn, theme.bgIn);
    gl.uniform3fv(bgU.uBgOut, theme.bgOut);
    gl.uniform1f(bgU.uFade, 1 - Math.min(CONFIG.trails, 0.97));
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    // particles
    gl.useProgram(prog);
    gl.disableVertexAttribArray(bgLoc);
    bindParticleAttrs();
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, atlas);
    gl.uniform1i(u.uAtlas, 0);
    const f = (k, v) => gl.uniform1f(u[k], v);
    f("uProgress", progress); f("uTime", t); f("uAspect", aspect); f("uDpr", dpr);
    f("uStagger", CONFIG.stagger); f("uBurst", CONFIG.burst); f("uSwirl", CONFIG.swirl); f("uSize", CONFIG.pointSize);
    f("uCenterX", aspect < 1 ? 0 : CONFIG.centerX); f("uMouseR", CONFIG.mouseRadius);
    f("uWeaponGlow", CONFIG.weaponGlow); f("uWeaponFlow", CONFIG.weaponFlow); f("uSparks", CONFIG.sparks);
    f("uScan", CONFIG.scan); f("uScanSpeed", CONFIG.scanSpeed); f("uTwinkle", CONFIG.twinkle);
    f("uAscii", +CONFIG.ascii); f("uAsciiSize", CONFIG.asciiSize); f("uAsciiDensity", CONFIG.asciiDensity);
    f("uAutoGlow", CONFIG.autoGlow); f("uLift", CONFIG.weaponLift); f("uHum", CONFIG.weaponHum); f("uRim", CONFIG.rim);
    const rim = parseInt(CONFIG.rimColor.slice(1), 16);
    gl.uniform3f(u.uRimColor, (rim >> 16 & 255) / 255, (rim >> 8 & 255) / 255, (rim & 255) / 255);
    gl.uniform2f(u.uRot, Math.sin(t * 0.35) * CONFIG.sway, Math.sin(t * 0.27) * 0.06 * (CONFIG.sway > 0 ? 1 : 0));
    gl.uniform2f(u.uMouse, 99, 99);
    gl.drawArrays(gl.POINTS, 0, N);
  }

  new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(hero);
  let lastAspect = aspect, lastN = N, refit;
  new ResizeObserver(() => {
    resize();
    const n = particles();
    if (Math.abs(aspect - lastAspect) > 0.05 || Math.abs(n - lastN) / lastN > 0.2) {
      clearTimeout(refit);
      refit = setTimeout(() => { lastAspect = aspect; lastN = particles(); resampleAll(); }, 150);
    }
  }).observe(canvas);

  startMorph(0, performance.now());
  requestAnimationFrame(frame);
}
