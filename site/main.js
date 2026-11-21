// Dead Projects Society — Three.js graveyard.
// Loads projects.json, raises a tombstone for each departed project, and
// lets visitors walk the grounds. Click a stone to read its story.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const container = document.getElementById("scene-container");
const panel = document.getElementById("panel");
const fallbackBox = document.getElementById("fallback");
const statsEl = document.getElementById("grounds-stats");
const hintEl = document.getElementById("hint");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function showFallback(message) {
  if (message) {
    document.getElementById("fallback-text").textContent = message;
  }
  fallbackBox.hidden = false;
  statsEl.textContent = "The gates are stuck.";
}

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true });
} catch (e) {
  showFallback("WebGL is unavailable in this browser, so the 3D grounds cannot open.");
  throw e;
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
container.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0e12);
scene.fog = new THREE.FogExp2(0x0b0e12, 0.028);

const camera = new THREE.PerspectiveCamera(
  55, window.innerWidth / window.innerHeight, 0.1, 300);
camera.position.set(0, 2.7, 11);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 1.35, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.maxPolarAngle = Math.PI * 0.52;
controls.minDistance = 2.5;
controls.maxDistance = 30;
controls.autoRotate = !reducedMotion;
controls.autoRotateSpeed = 0.35;

// ---------- lights ----------
const ambient = new THREE.AmbientLight(0x2a3442, 1.1);
scene.add(ambient);

const moonLight = new THREE.DirectionalLight(0xaFC4e8, 1.6);
moonLight.position.set(-14, 20, -8);
moonLight.castShadow = true;
moonLight.shadow.mapSize.set(2048, 2048);
moonLight.shadow.camera.left = -22;
moonLight.shadow.camera.right = 22;
moonLight.shadow.camera.top = 22;
moonLight.shadow.camera.bottom = -22;
scene.add(moonLight);

const lantern = new THREE.PointLight(0xffb46b, 12, 18, 1.8);
lantern.position.set(0, 1.6, 4.5);
scene.add(lantern);

// ---------- moon ----------
function makeMoonSprite() {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(128, 128, 10, 128, 128, 128);
  grad.addColorStop(0, "rgba(242,247,253,1)");
  grad.addColorStop(0.32, "rgba(226,236,249,0.95)");
  grad.addColorStop(0.5, "rgba(190,208,235,0.32)");
  grad.addColorStop(1, "rgba(140,165,205,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 256);
  const tex = new THREE.CanvasTexture(c);
  const spr = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, transparent: true, depthWrite: false, fog: false }));
  spr.scale.set(14, 14, 1);
  spr.position.set(-6, 11, -36);
  return spr;
}
scene.add(makeMoonSprite());

// ---------- stars ----------
function makeStars(count) {
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2;
    const radius = 90 + Math.random() * 60;
    pos[i * 3] = Math.cos(angle) * radius;
    pos[i * 3 + 1] = 12 + Math.random() * 70;
    pos[i * 3 + 2] = Math.sin(angle) * radius;
  }
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.PointsMaterial({
    color: 0xcdd9ea, size: 1.6, sizeAttenuation: false,
    transparent: true, opacity: 0.8, fog: false, depthWrite: false });
  return new THREE.Points(geo, mat);
}
scene.add(makeStars(700));

// ---------- ground mist ----------
const mistSprites = [];
function makeMist() {
  const c = document.createElement("canvas");
  c.width = 256; c.height = 128;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(128, 64, 8, 128, 64, 120);
  grad.addColorStop(0, "rgba(190,205,220,0.55)");
  grad.addColorStop(1, "rgba(190,205,220,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 128);
  const tex = new THREE.CanvasTexture(c);
  for (let i = 0; i < 9; i++) {
    const spr = new THREE.Sprite(new THREE.SpriteMaterial({
      map: tex, transparent: true, depthWrite: false,
      opacity: 0.05 + Math.random() * 0.05 }));
    spr.scale.set(16 + Math.random() * 14, 4.5 + Math.random() * 2, 1);
    spr.position.set((Math.random() - 0.5) * 30, 0.8, (Math.random() - 0.5) * 30 - 4);
    spr.userData.speed = 0.08 + Math.random() * 0.12;
    mistSprites.push(spr);
    scene.add(spr);
  }
}
makeMist();

// ---------- ground ----------
const ground = new THREE.Mesh(
  new THREE.CircleGeometry(70, 48),
  new THREE.MeshStandardMaterial({ color: 0x11161c, roughness: 1 }));
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

// A worn path down the middle.
const path = new THREE.Mesh(
  new THREE.PlaneGeometry(2.2, 46),
  new THREE.MeshStandardMaterial({ color: 0x1a2027, roughness: 1 }));
path.rotation.x = -Math.PI / 2;
path.position.set(0, 0.01, -12);
path.receiveShadow = true;
scene.add(path);

// ---------- tombstones ----------
function wrapText(g, text, maxWidth) {
  // Split on spaces and hyphens so long repo names (one "word") can wrap.
  const words = String(text).split(/(?<=[-\s])/).filter(Boolean);
  const lines = [];
  let line = "";
  for (const w of words) {
    const trial = line + w;
    if (g.measureText(trial).width > maxWidth && line) {
      lines.push(line.trimEnd());
      line = w.trimStart();
    } else {
      line = trial;
    }
  }
  if (line) lines.push(line.trim());
  return lines;
}

// The concept sheet's other vision: the stone as a dead terminal, cyan
// monospace on near-black. Same facts, haunted by a different decade.
function makeTerminalPlaqueTexture(project) {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 640;
  const g = c.getContext("2d");
  g.fillStyle = "#04070a";
  g.fillRect(0, 0, 512, 640);
  g.strokeStyle = "rgba(127,231,255,0.35)";
  g.lineWidth = 3;
  g.strokeRect(14, 14, 484, 612);
  g.textAlign = "left";
  g.shadowColor = "rgba(127,231,255,0.8)";
  g.shadowBlur = 9;
  const cyan = "#7fe7ff";
  const dimCyan = "rgba(127,231,255,0.66)";
  const line = (text, y, size, color) => {
    g.font = size + "px 'Courier New', monospace";
    g.fillStyle = color || cyan;
    g.fillText(text, 44, y);
  };
  line("PROJECT: " + project.name.toUpperCase().slice(0, 24), 96, 30);
  const years = project.born === project.died
    ? String(project.born) : project.born + " - " + project.died;
  line("LIFESPAN: " + years, 148, 25, dimCyan);
  line("COMMITS: " + (project.commits != null ? project.commits : "—"),
    190, 25, dimCyan);
  line("LAST COMMIT: " + project.silence_days + " DAYS AGO", 232, 25,
    dimCyan);
  let y = 300;
  if (project.epitaph) {
    g.font = "25px 'Courier New', monospace";
    const words = wrapText(g, project.epitaph, 400).slice(0, 3);
    line("// LAST WORDS:", y, 25, dimCyan);
    y += 40;
    for (const w of words) {
      line(w.toUpperCase().slice(0, 26), y, 25);
      y += 38;
    }
  }
  y += 26;
  line("// " + (project.cause || "CAUSE UNKNOWN").toUpperCase().slice(0, 26),
    y, 25, dimCyan);
  y += 52;
  line("STATUS: ABANDONED", y, 28);
  line("x", y + 54, 28, dimCyan);
  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = 4;
  return tex;
}

function makePlaqueTexture(project) {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 640;
  const g = c.getContext("2d");
  g.clearRect(0, 0, 512, 640);
  g.textAlign = "center";

  const engrave = (text, y, font, color) => {
    g.font = font;
    g.fillStyle = "rgba(10,12,14,0.85)";
    g.fillText(text, 256, y + 2);
    g.fillStyle = color;
    g.fillText(text, 256, y);
  };
  const pale = "rgba(228,233,238,0.92)";
  const dim = "rgba(178,188,198,0.85)";

  engrave("R . I . P .", 92, "34px Georgia, serif", dim);

  // Shrink the name until its widest wrapped line fits the stone.
  let nameSize = 44;
  let nameLines = [];
  while (nameSize >= 28) {
    g.font = "bold " + nameSize + "px Georgia, serif";
    nameLines = wrapText(g, project.name, 420).slice(0, 3);
    const widest = Math.max(...nameLines.map((l) => g.measureText(l).width));
    if (widest <= 420) break;
    nameSize -= 4;
  }
  const nameFont = "bold " + nameSize + "px Georgia, serif";
  let y = 168;
  for (const line of nameLines) {
    engrave(line, y, nameFont, pale);
    y += nameSize + 8;
  }

  g.strokeStyle = "rgba(178,188,198,0.5)";
  g.lineWidth = 2;
  g.beginPath();
  g.moveTo(156, y + 6);
  g.lineTo(356, y + 6);
  g.stroke();

  const years = project.born === project.died
    ? String(project.born)
    : project.born + " — " + project.died;
  engrave(years, y + 58, "36px Georgia, serif", pale);

  if (project.epitaph) {
    g.font = "italic 30px Georgia, serif";
    const lines = wrapText(g, project.epitaph, 400).slice(0, 3);
    let ey = y + 122;
    for (const line of lines) {
      engrave(line, ey, "italic 30px Georgia, serif", dim);
      ey += 40;
    }
  }

  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = 4;
  return tex;
}

function makeStoneGeometry(style) {
  const s = new THREE.Shape();
  if (style === "gothic") {
    // Classic Gothic: straight sides rising to a pointed arch.
    s.moveTo(-0.5, 0);
    s.lineTo(-0.5, 0.95);
    s.quadraticCurveTo(-0.5, 1.42, 0, 1.78);
    s.quadraticCurveTo(0.5, 1.42, 0.5, 0.95);
    s.lineTo(0.5, 0);
  } else if (style === "tablet") {
    // Modern Tablet: a clean slab with barely rounded corners.
    s.moveTo(-0.52, 0);
    s.lineTo(-0.52, 1.38);
    s.quadraticCurveTo(-0.52, 1.5, -0.4, 1.5);
    s.lineTo(0.4, 1.5);
    s.quadraticCurveTo(0.52, 1.5, 0.52, 1.38);
    s.lineTo(0.52, 0);
  } else {
    s.moveTo(-0.5, 0);
    s.lineTo(-0.5, 1.05);
    s.absarc(0, 1.05, 0.5, Math.PI, 0, true);
    s.lineTo(0.5, 0);
  }
  s.closePath();
  const geo = new THREE.ExtrudeGeometry(s, {
    depth: 0.16, bevelEnabled: true, bevelThickness: 0.015,
    bevelSize: 0.015, bevelSegments: 1, curveSegments: 24,
  });
  geo.translate(0, 0, -0.08);
  return geo;
}
const stoneGeometries = {
  classic: makeStoneGeometry("classic"),
  gothic: makeStoneGeometry("gothic"),
  tablet: makeStoneGeometry("tablet"),
};
const stoneGeometry = stoneGeometries.classic;

// Weathered stone, painted once on a canvas: speckle, blotches, hairline
// cracks, and moss staining toward the base. No external assets.
function makeStoneTexture() {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 256;
  const g = c.getContext("2d");
  g.fillStyle = "#a7b0b8";
  g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 34; i++) {
    const x = Math.random() * 256, y = Math.random() * 256;
    const r = 18 + Math.random() * 52;
    const grad = g.createRadialGradient(x, y, 0, x, y, r);
    const tone = Math.random() < 0.5 ? "58,66,74" : "150,158,166";
    grad.addColorStop(0, "rgba(" + tone + ",0.36)");
    grad.addColorStop(1, "rgba(" + tone + ",0)");
    g.fillStyle = grad;
    g.fillRect(x - r, y - r, r * 2, r * 2);
  }
  for (let i = 0; i < 2600; i++) {
    g.fillStyle = Math.random() < 0.5
      ? "rgba(24,28,32," + (0.08 + Math.random() * 0.22) + ")"
      : "rgba(232,238,242," + (0.05 + Math.random() * 0.14) + ")";
    g.fillRect(Math.random() * 256, Math.random() * 256,
      1 + Math.random() * 2.4, 1 + Math.random() * 2.4);
  }
  g.strokeStyle = "rgba(30,34,38,0.55)";
  g.lineWidth = 1;
  for (let i = 0; i < 6; i++) {
    let x = Math.random() * 256, y = Math.random() * 90;
    g.beginPath();
    g.moveTo(x, y);
    const segs = 3 + Math.floor(Math.random() * 3);
    for (let k = 0; k < segs; k++) {
      x += (Math.random() - 0.5) * 22;
      y += 14 + Math.random() * 22;
      g.lineTo(x, y);
    }
    g.stroke();
  }
  const moss = g.createLinearGradient(0, 180, 0, 256);
  moss.addColorStop(0, "rgba(74,96,58,0)");
  moss.addColorStop(1, "rgba(74,96,58,0.4)");
  g.fillStyle = moss;
  g.fillRect(0, 180, 256, 76);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 4;
  return tex;
}
const stoneTexture = makeStoneTexture();

// Which concept from the design sheet a project gets: the biggest legacy
// earns the Celtic Cross; the rest split between Gothic and Tablet.
function styleFor(project, loudestId) {
  if (project.id === loudestId) return "cross";
  let h = 0;
  for (const ch of project.id) h += ch.charCodeAt(0);
  return h % 2 === 0 ? "gothic" : "tablet";
}

const interactive = [];
const stoneGroups = new Map();

function raiseStone(project, position, decorative, style) {
  const group = new THREE.Group();
  const tint = 0.92 + Math.random() * 0.16;
  const stoneMat = new THREE.MeshStandardMaterial({
    map: stoneTexture,
    color: new THREE.Color(0.66 * tint, 0.7 * tint, 0.74 * tint),
    roughness: 0.95, metalness: 0.02,
  });
  const geo = style === "cross" ? stoneGeometries.gothic
    : stoneGeometries[style] || stoneGeometries.classic;
  const body = new THREE.Mesh(geo, stoneMat);
  if (style === "cross") {
    // Celtic Cross, for the project that leaves a legacy beyond scope.
    const upright = new THREE.Mesh(
      new THREE.BoxGeometry(0.15, 0.66, 0.09), stoneMat);
    upright.position.set(0, 1.98, 0);
    upright.castShadow = true;
    group.add(upright);
    const bar = new THREE.Mesh(
      new THREE.BoxGeometry(0.46, 0.13, 0.09), stoneMat);
    bar.position.set(0, 2.06, 0);
    bar.castShadow = true;
    group.add(bar);
  }
  body.castShadow = true;
  body.receiveShadow = true;
  body.userData.baseColor = stoneMat.color.clone();
  group.add(body);

  if (!decorative) {
    // Weathering: the longer a project has been dead, the more its stone
    // leans and the fainter its engraving gets.
    const diedYear = parseInt(project.died, 10);
    const yearsDead = Number.isFinite(diedYear)
      ? Math.max(0, new Date().getFullYear() - diedYear) : 0;
    group.rotation.z += Math.min(0.09, yearsDead * 0.012) *
      (Math.random() < 0.5 ? -1 : 1);
    // Moss creeps in with the years.
    body.material.color.lerp(new THREE.Color(0.3, 0.4, 0.28),
      Math.min(0.45, yearsDead * 0.06));
    body.userData.baseColor.copy(body.material.color);
    const plaque = new THREE.Mesh(
      new THREE.PlaneGeometry(0.94, 1.18),
      new THREE.MeshBasicMaterial({
        map: makePlaqueTexture(project), transparent: true,
        opacity: Math.max(0.5, 1 - yearsDead * 0.05) }));
    plaque.position.set(0, 0.82, 0.098);
    group.add(plaque);
    group.userData.plaque = plaque;
    group.userData.plaqueCanvas = plaque.material.map.image;
    group.userData.engravedTex = plaque.material.map;
    if (project.resurrections > 0) {
      // A faint ring of light for the ones who came back at least once.
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.78, 0.98, 40),
        new THREE.MeshBasicMaterial({
          color: 0xd8c58f, transparent: true, opacity: 0.32,
          side: THREE.DoubleSide, depthWrite: false }));
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = 0.02;
      group.add(ring);
    }
    group.userData.body = body;
    group.userData.baseOpacity = plaque.material.opacity;
    body.userData.project = project;
    interactive.push(body);
    stoneGroups.set(project.id, group);
  }

  const scale = project && project.commits
    ? 1 + Math.min(0.35, Math.log10(project.commits + 1) * 0.09)
    : 1;
  group.scale.setScalar(scale * (decorative ? 0.75 + Math.random() * 0.4 : 1));
  group.position.copy(position);
  group.position.y = -0.03 - Math.random() * 0.04;
  group.rotation.y = (Math.random() - 0.5) * 0.14;
  group.rotation.z = (Math.random() - 0.5) * 0.03;
  scene.add(group);
  return group;
}

// ---------- fireflies ----------
function makeFireflies(count) {
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    pos[i * 3] = (Math.random() - 0.5) * 36;
    pos[i * 3 + 1] = 0.4 + Math.random() * 2.6;
    pos[i * 3 + 2] = (Math.random() - 0.5) * 36;
  }
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.PointsMaterial({
    color: 0xd8c58f, size: 0.07, transparent: true, opacity: 0.75,
    blending: THREE.AdditiveBlending, depthWrite: false });
  const pts = new THREE.Points(geo, mat);
  pts.userData.base = pos.slice();
  return pts;
}
const fireflies = makeFireflies(130);
scene.add(fireflies);

function setDimmed(project, dim) {
  const group = stoneGroups.get(project.id);
  if (!group || !group.userData.plaque) return;
  group.userData.plaque.material.opacity =
    dim ? group.userData.baseOpacity * 0.12 : group.userData.baseOpacity;
  const body = group.userData.body;
  body.material.color.copy(body.userData.baseColor)
    .multiplyScalar(dim ? 0.3 : 1);
}

// ---------- panel ----------
const el = (id) => document.getElementById(id);
let selectedId = null;
let allProjects = [];

function openPanel(project) {
  selectedId = project.id;
  el("panel-name").textContent = project.name;
  el("panel-years").textContent = project.born === project.died
    ? String(project.born)
    : project.born + " — " + project.died;
  el("panel-silent").textContent = project.silence_days
    ? "Silent for " + project.silence_days + " days now."
    : "";
  el("panel-rose").textContent = project.resurrections > 0
    ? "Back from the dead " +
      (project.resurrections === 1 ? "once" : project.resurrections + " times") +
      ": flatlined for " + project.longest_flatline_days + " days, then returned."
    : "";
  const tl = el("panel-timeline");
  const act = project.activity;
  if (Array.isArray(act) && act.length > 1) {
    el("panel-life").hidden = false;
    tl.hidden = false;
    const ctx = tl.getContext("2d");
    ctx.clearRect(0, 0, tl.width, tl.height);
    const peak = Math.max(...act, 1);
    const bw = tl.width / act.length;
    act.forEach((v, i) => {
      const h = Math.max(2, (v / peak) * (tl.height - 6));
      ctx.fillStyle = v === 0 ? "#2c3542" : "#c9a959";
      ctx.fillRect(i * bw + 0.5, tl.height - h, Math.max(1, bw - 1.5), h);
    });
  } else {
    el("panel-life").hidden = true;
    tl.hidden = true;
  }
  el("panel-cause").textContent = project.cause || "Cause unknown";
  el("panel-epitaph").textContent = project.epitaph || "";
  el("panel-epitaph").style.display = project.epitaph ? "" : "none";
  el("panel-description").textContent = project.description || "";
  const techRow = el("panel-tech");
  techRow.innerHTML = "";
  for (const t of project.tech || []) {
    const chip = document.createElement("span");
    chip.className = "tech-chip";
    chip.textContent = t;
    techRow.appendChild(chip);
  }
  const link = el("panel-url");
  if (project.url) {
    link.href = project.url;
    link.hidden = false;
  } else {
    link.hidden = true;
  }
  // Patients have no grave to deep-link to; the share button rests.
  el("panel-share").style.display = project.patient ? "none" : "";
  el("panel-cert").style.display = project.patient ? "none" : "";
  panel.hidden = false;
}

function closePanel() {
  stopTour();
  selectedId = null;
  panel.hidden = true;
  document.querySelectorAll(".registry-list button.selected")
    .forEach((b) => b.classList.remove("selected"));
}
el("panel-close").addEventListener("click", closePanel);

el("panel-prev").addEventListener("click", () => { stopTour(); cycleProject(-1); });
el("panel-next").addEventListener("click", () => { stopTour(); cycleProject(1); });

el("panel-copy").addEventListener("click", async () => {
  const project = allProjects.find((p) => p.id === selectedId) ||
    allPatients.find((p) => p.id === selectedId) ||
    allPublic.find((p) => p.id === selectedId);
  if (!project) return;
  const years = project.born === project.died
    ? String(project.born) : project.born + " — " + project.died;
  const text = project.patient
    ? project.name + " (" + years + ") — " + project.cause + "\n" +
      (project.epitaph ? "Last words so far: \"" + project.epitaph + "\"\n" : "") +
      (project.description || "") + "\n" + location.origin + location.pathname
    : "R.I.P. " + project.name + " (" + years + ")\n" +
      "Cause of death: " + (project.cause || "Cause unknown") + "\n" +
      (project.epitaph ? "Last words: \"" + project.epitaph + "\"\n" : "") +
      (project.description || "") + "\n" +
      location.origin + location.pathname + "#grave=" +
      encodeURIComponent(project.id);
  const btn = el("panel-copy");
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = "Copied";
  } catch (e) {
    btn.textContent = "Copy failed";
  }
  setTimeout(() => { btn.textContent = "Copy obituary"; }, 2200);
});

el("panel-download").addEventListener("click", () => {
  const group = stoneGroups.get(selectedId) || wardGroups.get(selectedId);
  if (!group || !group.userData.plaqueCanvas) return;
  const src = group.userData.plaqueCanvas;
  const card = document.createElement("canvas");
  card.width = src.width;
  card.height = src.height;
  const g = card.getContext("2d");
  const grad = g.createLinearGradient(0, 0, 0, card.height);
  grad.addColorStop(0, "#59616a");
  grad.addColorStop(1, "#363d44");
  g.fillStyle = grad;
  g.fillRect(0, 0, card.width, card.height);
  g.drawImage(src, 0, 0);
  g.fillStyle = "rgba(207,214,221,0.75)";
  g.font = "22px Georgia, serif";
  g.textAlign = "center";
  g.fillText("DEAD PROJECTS SOCIETY", card.width / 2, card.height - 26);
  const a = document.createElement("a");
  a.download = selectedId + "-tombstone.png";
  a.href = card.toDataURL("image/png");
  a.click();
});

el("panel-cert").addEventListener("click", () => {
  const project = allProjects.find((p) => p.id === selectedId) ||
    allPublic.find((p) => p.id === selectedId);
  if (!project) return;
  const card = document.createElement("canvas");
  card.width = 1200;
  card.height = 850;
  const g = card.getContext("2d");
  g.fillStyle = "#101216";
  g.fillRect(0, 0, 1200, 850);
  g.strokeStyle = "#b08d57";
  g.lineWidth = 3;
  g.strokeRect(36, 36, 1128, 778);
  g.lineWidth = 1;
  g.strokeRect(52, 52, 1096, 746);
  g.textAlign = "center";
  g.fillStyle = "#8b96a0";
  g.font = "26px Georgia, serif";
  g.fillText("D E A D   P R O J E C T S   S O C I E T Y", 600, 130);
  g.fillStyle = "#e8e2d2";
  g.font = "52px Georgia, serif";
  g.fillText("CERTIFICATE OF DEATH", 600, 205);
  g.fillStyle = "#b08d57";
  g.font = "30px Georgia, serif";
  g.fillText("✦ ✦ ✦", 600, 262);
  g.fillStyle = "#8b96a0";
  g.font = "22px Georgia, serif";
  g.fillText("THIS CERTIFIES THE RECORD OF", 600, 330);
  g.fillStyle = "#f0ead8";
  g.font = "64px Georgia, serif";
  let name = project.name;
  while (g.measureText(name).width > 1000 && name.length > 4) {
    name = name.slice(0, -2);
    g.font = (parseInt(g.font, 10) - 4) + "px Georgia, serif";
  }
  g.fillText(name, 600, 415);
  g.fillStyle = "#aeb6ae";
  g.font = "28px Georgia, serif";
  g.fillText(project.born + " — " + project.died + " · silent for " +
    (project.silence_days != null
      ? project.silence_days.toLocaleString() + " days" : "ages"),
    600, 475);
  g.fillStyle = "#8b96a0";
  g.font = "20px Georgia, serif";
  g.fillText("CAUSE OF DEATH", 600, 545);
  g.fillStyle = "#d8d2c2";
  g.font = "italic 30px Georgia, serif";
  g.fillText(project.cause || "Cause unknown", 600, 590);
  g.fillStyle = "#8b96a0";
  g.font = "20px Georgia, serif";
  g.fillText("LAST WORDS", 600, 660);
  g.fillStyle = "#d8d2c2";
  g.font = "italic 26px Georgia, serif";
  let words = "“" + (project.epitaph || "(silence)") + "”";
  if (words.length > 58) words = words.slice(0, 57) + "…”";
  g.fillText(words, 600, 702);
  g.fillStyle = "#77828d";
  g.font = "20px Georgia, serif";
  g.fillText("Judged from the record alone. No code was read.", 600, 772);
  const a = document.createElement("a");
  a.download = selectedId + "-certificate.png";
  a.href = card.toDataURL("image/png");
  a.click();
});

el("panel-share").addEventListener("click", async () => {
  if (!selectedId) return;
  const url = location.origin + location.pathname + "#grave=" +
    encodeURIComponent(selectedId);
  const btn = el("panel-share");
  try {
    await navigator.clipboard.writeText(url);
    btn.textContent = "Link copied";
  } catch (e) {
    btn.textContent = url;
  }
  setTimeout(() => { btn.textContent = "Share this grave"; }, 2200);
});

// ---------- visiting a grave (click, registry, random, keys) ----------
let desiredCamPos = null;

function visitProject(project) {
  openPanel(project);
  if (!project.patient) {
    try {
      history.replaceState(null, "", "#grave=" + encodeURIComponent(project.id));
    } catch (e) { /* file:// or sandboxed frames may refuse; the visit stands */ }
  }
  const group = stoneGroups.get(project.id) || wardGroups.get(project.id);
  if (!group) return;
  document.querySelectorAll(".registry-list button").forEach((b) => {
    b.classList.toggle("selected", b.dataset.id === project.id);
  });
  const p = group.position;
  // On portrait screens the panel is a bottom sheet covering the lower
  // half of the view, so aim lower on the stone: the engraving then sits
  // in the visible upper frame instead of behind the panel.
  const portrait = window.innerHeight > window.innerWidth;
  desiredTarget.copy(p).add(new THREE.Vector3(0, portrait ? 0.45 : 0.9, 0));
  // Stand on the path side of the stone, close enough to read it.
  const toward = new THREE.Vector3(-Math.sign(p.x), 0, 0.35).normalize();
  desiredCamPos = p.clone().add(toward.multiplyScalar(portrait ? 5.2 : 4.8));
  desiredCamPos.y = portrait ? 2.0 : 2.2;
  userDrove = false;
  controls.autoRotate = false;
}

function cycleProject(step) {
  if (!allProjects.length) return;
  const idx = allProjects.findIndex((p) => p.id === selectedId);
  const next = allProjects[(idx + step + allProjects.length) % allProjects.length];
  visitProject(next);
}

// ---------- the tour ----------
let tourTimer = null;
function stopTour() {
  if (tourTimer) {
    clearInterval(tourTimer);
    tourTimer = null;
  }
  const btn = el("tour-btn");
  if (btn) {
    btn.textContent = "Take the tour";
    btn.classList.remove("active");
  }
}
function startTour() {
  if (!allProjects.length) return;
  const btn = el("tour-btn");
  btn.textContent = "Stop the tour";
  btn.classList.add("active");
  cycleProject(1);
  tourTimer = setInterval(() => cycleProject(1), 6500);
}

window.addEventListener("keydown", (event) => {
  if (event.target && (event.target.tagName === "INPUT" ||
      event.target.tagName === "TEXTAREA")) return;
  if (event.key === "ArrowRight") cycleProject(1);
  else if (event.key === "ArrowLeft") cycleProject(-1);
  else if (event.key === "Escape") closePanel();
  else if (event.key === "r" || event.key === "R") {
    const pool = allProjects.filter((p) => p.id !== selectedId);
    const pick = pool[Math.floor(Math.random() * pool.length)];
    if (pick) { stopTour(); visitProject(pick); }
  } else if (event.key === "t" || event.key === "T") {
    if (tourTimer) stopTour(); else startTour();
  }
});

// A shared link followed while the grounds are already open should still
// walk to that grave, without a reload.
window.addEventListener("hashchange", () => {
  const m = location.hash.match(/grave=([^&]+)/);
  if (!m || !allProjects.length) return;
  const target = allProjects.find((p) => p.id === decodeURIComponent(m[1]));
  if (target && target.id !== selectedId) visitProject(target);
});

// ---------- picking ----------
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let hovered = null;
let desiredTarget = new THREE.Vector3(0, 1.1, 0);
let userDrove = false;

controls.addEventListener("start", () => {
  userDrove = true;
  desiredCamPos = null;
  stopTour();
  controls.autoRotate = false;
  hintEl.classList.add("faded");
});

function castAt(event) {
  pointer.x = (event.clientX / window.innerWidth) * 2 - 1;
  pointer.y = -(event.clientY / window.innerHeight) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(interactive, false);
  return hits.length ? hits[0].object : null;
}

const tooltip = el("tooltip");
renderer.domElement.addEventListener("pointermove", (event) => {
  hovered = castAt(event);
  renderer.domElement.style.cursor = hovered ? "pointer" : "";
  if (hovered) {
    tooltip.textContent = hovered.userData.project.name;
    tooltip.style.left = event.clientX + "px";
    tooltip.style.top = event.clientY + "px";
    tooltip.hidden = false;
  } else {
    tooltip.hidden = true;
  }
});
renderer.domElement.addEventListener("pointerleave", () => {
  tooltip.hidden = true;
});

let downAt = null;
renderer.domElement.addEventListener("pointerdown", (event) => {
  downAt = { x: event.clientX, y: event.clientY };
});
renderer.domElement.addEventListener("pointerup", (event) => {
  if (!downAt) return;
  const moved = Math.hypot(event.clientX - downAt.x, event.clientY - downAt.y);
  downAt = null;
  if (moved > 6) return; // it was a drag, not a click
  const hit = castAt(event);
  if (hit) {
    visitProject(hit.userData.project);
  } else {
    closePanel();
    desiredCamPos = null;
    desiredTarget.set(0, 1.1, 0);
  }
});

// ---------- wards: intensive care + still breathing ----------
let icuLight = null;

function makeWardPlaqueTexture(entry, label, accent) {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 640;
  const g = c.getContext("2d");
  g.textAlign = "center";
  const draw = (text, y, font, color) => {
    g.font = font;
    g.fillStyle = "rgba(10,12,14,0.85)";
    g.fillText(text, 256, y + 2);
    g.fillStyle = color;
    g.fillText(text, 256, y);
  };
  draw(label, 120, "30px Georgia, serif", accent);
  g.font = "bold 42px Georgia, serif";
  const lines = wrapText(g, entry.name, 420).slice(0, 3);
  let y = 210;
  for (const line of lines) {
    draw(line, y, "bold 42px Georgia, serif", "rgba(228,233,238,0.9)");
    y += 50;
  }
  draw("silent " + entry.silence_days + " days", y + 26,
    "italic 30px Georgia, serif", "rgba(178,188,198,0.85)");
  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = 4;
  return tex;
}

function makeSign(text, width) {
  const w = width || 3.6;
  const c = document.createElement("canvas");
  c.width = 1024;
  c.height = 224;
  const g = c.getContext("2d");
  g.fillStyle = "#171310";
  g.fillRect(0, 0, 1024, 224);
  g.strokeStyle = "rgba(207,214,221,0.35)";
  g.lineWidth = 6;
  g.strokeRect(14, 14, 996, 196);
  g.fillStyle = "rgba(226,231,236,0.92)";
  g.textAlign = "center";
  let size = 64;
  const spaced = text.split("").join("\u200a");
  while (size > 30) {
    g.font = size + "px Georgia, serif";
    if (g.measureText(spaced).width <= 940) break;
    size -= 4;
  }
  g.fillText(spaced, 512, 138);
  const tex = new THREE.CanvasTexture(c);
  const group = new THREE.Group();
  const boardH = w * (224 / 1024);
  const boardY = 1.15 + boardH / 2;
  const board = new THREE.Mesh(
    new THREE.PlaneGeometry(w, boardH),
    new THREE.MeshStandardMaterial({ map: tex, roughness: 0.9 }));
  board.position.y = boardY;
  group.add(board);
  const postMat = new THREE.MeshStandardMaterial({ color: 0x241c12, roughness: 1 });
  for (const px of [-(w / 2 - 0.25), w / 2 - 0.25]) {
    const post = new THREE.Mesh(
      new THREE.CylinderGeometry(0.05, 0.05, boardY, 8), postMat);
    post.position.set(px, boardY / 2, -0.03);
    group.add(post);
  }
  return group;
}

// The entrance gate over the path.
const gate = makeSign("DEAD PROJECTS SOCIETY", 5.6);
gate.position.set(0, 0, 7.6);
scene.add(gate);

// Cypress trees around the grounds, from the concept sheet's skyline.
function makeCypress(x, z, h) {
  const tree = new THREE.Group();
  const trunk = new THREE.Mesh(
    new THREE.CylinderGeometry(0.06, 0.1, 0.8, 6),
    new THREE.MeshStandardMaterial({ color: 0x1a140e, roughness: 1 }));
  trunk.position.y = 0.4;
  tree.add(trunk);
  const leafMat = new THREE.MeshStandardMaterial({
    color: 0x0c130e, roughness: 1 });
  const tiers = [[0.62, 0.5], [0.46, 0.42], [0.28, 0.34]];
  let y = 0.6;
  for (const [r, frac] of tiers) {
    const cone = new THREE.Mesh(
      new THREE.ConeGeometry(r, h * frac, 8), leafMat);
    cone.position.y = y + (h * frac) / 2;
    cone.castShadow = true;
    tree.add(cone);
    y += h * frac * 0.72;
  }
  tree.position.set(x, 0, z);
  scene.add(tree);
}
for (let i = 0; i < 18; i++) {
  const angle = (i / 18) * Math.PI * 2 + (Math.random() - 0.5) * 0.2;
  const radius = 20 + Math.random() * 8;
  const x = Math.cos(angle) * radius;
  const z = Math.sin(angle) * radius - 6;
  if (z > 4 && Math.abs(x) < 6) continue; // keep the entrance clear
  makeCypress(x, z, 4.5 + Math.random() * 3);
}

// A distant spired skyline on the horizon, all silhouette. It ignores
// the fog on purpose: at fog density the far band would wash to the sky
// color and vanish, so the skyline is drawn flat, a shade off the sky.
{
  const silMat = new THREE.MeshBasicMaterial({ color: 0x161d26, fog: false });
  for (let x = -38; x <= 38; x += 5 + Math.random() * 3) {
    const h = 9 + Math.random() * 8;
    const tower = new THREE.Mesh(
      new THREE.BoxGeometry(3 + Math.random() * 2.5, h, 2), silMat);
    tower.position.set(x, h / 2 - 0.5, -38 + (Math.random() - 0.5) * 3);
    scene.add(tower);
    if (Math.random() < 0.65) {
      const spire = new THREE.Mesh(
        new THREE.ConeGeometry(1.4, 3.5 + Math.random() * 3, 4), silMat);
      spire.position.set(x, h - 0.5 + spire.geometry.parameters.height / 2,
        tower.position.z);
      scene.add(spire);
    }
  }
}

const wardGroups = new Map();
const allPatients = [];

function raiseWardStone(entry, label, accent, position, faceAngle) {
  const patient = {
    id: entry.id,
    name: entry.name,
    born: entry.born,
    died: entry.died,
    cause: label === "INTENSIVE CARE" ? "Intensive Care" : "Still Breathing",
    epitaph: entry.epitaph || "",
    description: entry.description || "",
    tech: [],
    url: entry.url,
    silence_days: entry.silence_days,
    resurrections: entry.resurrections || 0,
    longest_flatline_days: entry.longest_flatline_days || 0,
    patient: true,
  };
  const group = new THREE.Group();
  const body = new THREE.Mesh(stoneGeometries.tablet,
    new THREE.MeshStandardMaterial({
      map: stoneTexture, color: 0x9aa2a8, roughness: 0.97 }));
  body.castShadow = true;
  body.userData.project = patient;
  interactive.push(body);
  group.add(body);
  const plaque = new THREE.Mesh(
    new THREE.PlaneGeometry(0.94, 1.18),
    new THREE.MeshBasicMaterial({
      map: makeWardPlaqueTexture(entry, label, accent), transparent: true }));
  plaque.position.set(0, 0.82, 0.098);
  group.add(plaque);
  group.userData.plaqueCanvas = plaque.material.map.image;
  group.scale.setScalar(0.55);
  group.position.copy(position);
  group.rotation.y = faceAngle;
  scene.add(group);
  wardGroups.set(patient.id, group);
  allPatients.push(patient);
}

async function buildWards() {
  let wards;
  try {
    const res = await fetch("wards.json?v=17");
    if (!res.ok) return;
    wards = await res.json();
  } catch (e) {
    return; // the wards are optional; the buried are the main grounds
  }
  const icu = wards.intensive_care || [];
  const breathing = wards.still_breathing || [];

  if (icu.length) {
    const sign = makeSign("INTENSIVE CARE");
    sign.position.set(-10.5, 0, -2.2);
    sign.rotation.y = 0.5;
    scene.add(sign);
    icuLight = new THREE.PointLight(0xffb46b, 7, 13, 1.8);
    icuLight.position.set(-11.5, 1.7, -6.5);
    scene.add(icuLight);
    icu.forEach((entry, i) => {
      const col = i % 5, row = Math.floor(i / 5);
      raiseWardStone(entry, "INTENSIVE CARE", "rgba(216,162,74,0.95)",
        new THREE.Vector3(-9.8 - col * 1.9, 0, -5 - row * 2.6), 0.55);
    });
  }
  if (breathing.length) {
    const sign = makeSign("STILL BREATHING");
    sign.position.set(10.5, 0, -2.2);
    sign.rotation.y = -0.5;
    scene.add(sign);
    const light = new THREE.PointLight(0x86d97a, 6, 12, 1.8);
    light.position.set(11.5, 1.7, -6.5);
    scene.add(light);
    breathing.forEach((entry, i) => {
      const col = i % 5, row = Math.floor(i / 5);
      raiseWardStone(entry, "STILL BREATHING", "rgba(159,212,138,0.95)",
        new THREE.Vector3(9.8 + col * 1.9, 0, -5 - row * 2.6), -0.55);
    });
  }
  if (icu.length || breathing.length) {
    statsEl.textContent += " · " + icu.length + " in intensive care · " +
      breathing.length + " still breathing";
    const list = el("wards-list");
    for (const patient of allPatients) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.id = patient.id;
      btn.textContent = patient.name;
      const meta = document.createElement("span");
      meta.className = "registry-years";
      meta.textContent = patient.cause.toLowerCase() + " · silent " +
        patient.silence_days + "d";
      btn.appendChild(meta);
      btn.addEventListener("click", () => { stopTour(); visitProject(patient); });
      li.appendChild(btn);
      list.appendChild(li);
    }
    el("wards-section").hidden = false;
  }
}

// ---------- registry ----------
function buildRegistry(projects) {
  const registry = el("registry");
  const list = el("registry-list");
  for (const project of projects) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.id = project.id;
    btn.textContent = project.name;
    const years = document.createElement("span");
    years.className = "reg-years";
    years.textContent = project.born === project.died
      ? String(project.born) : project.born + " — " + project.died;
    btn.appendChild(years);
    btn.addEventListener("click", () => visitProject(project));
    li.appendChild(btn);
    list.appendChild(li);
  }

  const filters = el("cause-filters");
  const causes = ["All", ...new Set(projects.map((p) => p.cause || "Cause unknown"))];
  for (const cause of causes) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "filter-chip" + (cause === "All" ? " active" : "");
    chip.textContent = cause;
    chip.addEventListener("click", () => {
      filters.querySelectorAll(".filter-chip")
        .forEach((c) => c.classList.toggle("active", c === chip));
      for (const p of projects) {
        setDimmed(p, cause !== "All" && (p.cause || "Cause unknown") !== cause);
      }
    });
    filters.appendChild(chip);
  }

  el("random-grave").addEventListener("click", () => {
    stopTour();
    const pool = projects.filter((p) => p.id !== selectedId);
    const pick = pool[Math.floor(Math.random() * pool.length)] || projects[0];
    if (pick) visitProject(pick);
  });

  el("tour-btn").addEventListener("click", () => {
    if (tourTimer) stopTour();
    else startTour();
  });

  let terminalMode = false;
  el("terminal-btn").addEventListener("click", () => {
    terminalMode = !terminalMode;
    el("terminal-btn").textContent =
      terminalMode ? "Engraved mode" : "Terminal mode";
    for (const [id, group] of stoneGroups) {
      const plaque = group.userData.plaque;
      if (!plaque) continue;
      if (terminalMode) {
        if (!group.userData.terminalTex) {
          const project = allProjects.find((p) => p.id === id) ||
            allPublic.find((p) => p.id === id);
          if (!project) continue;
          group.userData.terminalTex = makeTerminalPlaqueTexture(project);
        }
        plaque.material.map = group.userData.terminalTex;
      } else {
        plaque.material.map = group.userData.engravedTex;
      }
      plaque.material.needsUpdate = true;
    }
  });

  el("registry-search").addEventListener("input", (event) => {
    const q = event.target.value.trim().toLowerCase();
    list.querySelectorAll("li").forEach((li) => {
      const btn = li.querySelector("button");
      li.style.display = !q || btn.dataset.id.includes(q) ||
        btn.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  });

  registry.hidden = false;
}

// ---------- build the grounds ----------
async function build() {
  let projects;
  try {
    const res = await fetch("projects.json?v=17");
    if (!res.ok) throw new Error("projects.json missing");
    projects = await res.json();
  } catch (e) {
    showFallback("The burial registry (projects.json) could not be loaded.");
    return;
  }
  if (!Array.isArray(projects) || projects.length === 0) {
    statsEl.textContent = "The grounds are empty. Nobody has been buried yet.";
    return;
  }

  // Rows of the departed, flanking the path.
  const loudestId = projects.reduce((a, b) =>
    (b.commits || 0) > (a.commits || 0) ? b : a, projects[0]).id;
  const perRow = 4;
  projects.forEach((project, i) => {
    const row = Math.floor(i / perRow);
    const col = i % perRow;
    const side = i % 2 === 0 ? -1 : 1;
    const pairIndex = Math.floor(col / 2);
    const x = side * (2.6 + pairIndex * 2.4) + (Math.random() - 0.5) * 0.5;
    const z = 2.5 - row * 3.1 + (Math.random() - 0.5) * 0.6;
    const group = raiseStone(project, new THREE.Vector3(x, 0, z), false,
      styleFor(project, loudestId));
    group.rotation.y = side * -0.18 + (Math.random() - 0.5) * 0.1;
  });

  // Weathered blank stones further out, pure set dressing.
  for (let i = 0; i < 26; i++) {
    const angle = Math.random() * Math.PI * 2;
    const radius = 13 + Math.random() * 16;
    const x = Math.cos(angle) * radius;
    const z = Math.sin(angle) * radius - 6;
    if (Math.abs(x) < 3.4) continue;
    const pick = ["classic", "gothic", "tablet"][i % 3];
    raiseStone(null, new THREE.Vector3(x, 0, z), true, pick)
      .lookAt(0, 0, z + 4);
  }

  allProjects = projects;
  buildRegistry(projects);

  const totalCommits = projects.reduce((n, p) => n + (p.commits || 0), 0);
  statsEl.textContent = totalCommits
    ? "Now resting: " + projects.length + " projects · " +
      totalCommits.toLocaleString() + " commits buried"
    : "Now resting: " + projects.length + " projects";

  buildWards();

  const m = location.hash.match(/grave=([^&]+)/);
  if (m) {
    const target = projects.find((p) => p.id === decodeURIComponent(m[1]));
    if (target) setTimeout(() => visitProject(target), 700);
  }
}
build();

async function loadHonors() {
  try {
    const res = await fetch("honors.json?v=17");
    if (!res.ok) return;
    const honors = await res.json();
    if (!Array.isArray(honors) || !honors.length) return;
    const list = el("honors-list");
    honors.forEach((h) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      const title = document.createElement("span");
      title.className = "honor-title";
      title.textContent = h.title + ": ";
      btn.appendChild(title);
      btn.appendChild(document.createTextNode(h.project_name));
      const detail = document.createElement("span");
      detail.className = "honor-detail";
      detail.textContent = h.detail;
      btn.appendChild(detail);
      btn.addEventListener("click", () => {
        const project = allProjects.find((p) => p.id === h.project_id);
        if (project) { stopTour(); visitProject(project); }
      });
      li.appendChild(btn);
      list.appendChild(li);
    });
    el("honors").hidden = false;
  } catch (e) { /* the honors are optional; the dead do not mind */ }
}
loadHonors();

async function loadInfamy() {
  try {
    const res = await fetch("infamy.json?v=17");
    if (!res.ok) return;
    const infamy = await res.json();
    if (!Array.isArray(infamy) || !infamy.length) return;
    const list = el("infamy-list");
    infamy.forEach((h) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      const title = document.createElement("span");
      title.className = "honor-title";
      title.textContent = h.title + ": ";
      btn.appendChild(title);
      btn.appendChild(document.createTextNode(h.project_name));
      const detail = document.createElement("span");
      detail.className = "honor-detail";
      detail.textContent = h.detail;
      btn.appendChild(detail);
      btn.addEventListener("click", () => {
        const project = allProjects.find((p) => p.id === h.project_id);
        if (project) { stopTour(); visitProject(project); }
      });
      li.appendChild(btn);
      list.appendChild(li);
    });
    el("infamy").hidden = false;
  } catch (e) { /* infamy is optional too; the dead do not mind */ }
}
loadInfamy();

// ---------- the Public Grounds: famous graves ----------
const allPublic = [];

async function loadPublicGrounds() {
  let entries;
  try {
    const res = await fetch("public.json?v=17");
    if (!res.ok) return;
    entries = await res.json();
  } catch (e) {
    return; // the famous are patient; the personal grounds come first
  }
  if (!Array.isArray(entries) || !entries.length) return;
  const sign = makeSign("THE PUBLIC GROUNDS", 4.8);
  sign.position.set(0, 0, -12.4);
  scene.add(sign);
  entries.forEach((entry, i) => {
    const project = Object.assign({ patient: false, famous: true }, entry);
    allPublic.push(project);
    const row = Math.floor(i / 6), col = i % 6;
    const x = -13.5 + col * 5.4 + (Math.random() - 0.5) * 0.7;
    const z = -15.5 - row * 3.4 + (Math.random() - 0.5) * 0.5;
    const group = raiseStone(project, new THREE.Vector3(x, 0, z), false,
      entry.style || styleFor(project, null));
    group.rotation.y = (Math.random() - 0.5) * 0.16;
  });
  const list = el("public-list");
  for (const project of allPublic) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.id = project.id;
    btn.textContent = project.name;
    const meta = document.createElement("span");
    meta.className = "registry-years";
    meta.textContent = project.born + " — " + project.died;
    btn.appendChild(meta);
    btn.addEventListener("click", () => { stopTour(); visitProject(project); });
    li.appendChild(btn);
    list.appendChild(li);
  }
  el("public-section").hidden = false;
  statsEl.textContent += " · " + allPublic.length +
    " famous graves in the Public Grounds";
  const m = location.hash.match(/#grave=([^&]+)/);
  if (m) {
    const target = allPublic.find(
      (p) => p.id === decodeURIComponent(m[1]));
    if (target) setTimeout(() => visitProject(target), 900);
  }
}
loadPublicGrounds();

// ---------- animate ----------
const clock = new THREE.Clock();
let prevT = 0;
let nextFlash = 14 + Math.random() * 20;
let flashStart = -1;
function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();
  const dt = Math.min(0.05, t - prevT);
  prevT = t;

  if (!reducedMotion) {
    for (const spr of mistSprites) {
      spr.position.x += spr.userData.speed * dt;
      if (spr.position.x > 22) spr.position.x = -22;
    }
    const pos = fireflies.geometry.attributes.position;
    const base = fireflies.userData.base;
    for (let i = 0; i < pos.count; i++) {
      pos.array[i * 3] = base[i * 3] + Math.sin(t * 0.24 + i * 1.7) * 0.6;
      pos.array[i * 3 + 1] = base[i * 3 + 1] + Math.sin(t * 0.4 + i * 2.3) * 0.25;
    }
    pos.needsUpdate = true;
    lantern.intensity = 11 + Math.sin(t * 7.3) * 1.2 + Math.sin(t * 13.7) * 0.7;
    if (icuLight) icuLight.intensity = 6.5 + Math.sin(t * 2.2) * 1.8;

    // Distant lightning, now and then: a soft double blink on the horizon.
    if (t > nextFlash) {
      flashStart = t;
      nextFlash = t + 18 + Math.random() * 26;
    }
    if (flashStart > 0) {
      const age = t - flashStart;
      const env = age < 0.08 ? age / 0.08
        : age < 0.15 ? 0.3
        : age < 0.34 ? Math.max(0, 1 - (age - 0.15) / 0.19) : 0;
      ambient.intensity = 1.1 + env * 2.2;
      moonLight.intensity = 1.6 + env * 1.8;
      if (age >= 0.34) {
        flashStart = -1;
        ambient.intensity = 1.1;
        moonLight.intensity = 1.6;
      }
    }
  }

  if (hovered) {
    hovered.material.emissive = hovered.material.emissive || new THREE.Color();
    hovered.material.emissive.setHex(0x1c2733);
  }
  for (const body of interactive) {
    if (body !== hovered && body.material.emissive) {
      body.material.emissive.setHex(
        body.userData.project && body.userData.project.id === selectedId
          ? 0x27313d : 0x000000);
    }
  }

  if (!userDrove || selectedId) {
    controls.target.lerp(desiredTarget, 0.04);
  }
  if (desiredCamPos) {
    camera.position.lerp(desiredCamPos, 0.045);
    if (camera.position.distanceTo(desiredCamPos) < 0.06) desiredCamPos = null;
  }
  controls.update();
  renderer.render(scene, camera);
}
animate();

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});
