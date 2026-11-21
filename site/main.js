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
camera.position.set(0, 3.2, 11);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 1.1, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.maxPolarAngle = Math.PI * 0.52;
controls.minDistance = 2.5;
controls.maxDistance = 30;
controls.autoRotate = !reducedMotion;
controls.autoRotateSpeed = 0.35;

// ---------- lights ----------
scene.add(new THREE.AmbientLight(0x2a3442, 1.1));

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
  const grad = g.createRadialGradient(128, 128, 30, 128, 128, 128);
  grad.addColorStop(0, "rgba(235,242,252,1)");
  grad.addColorStop(0.25, "rgba(200,216,240,0.85)");
  grad.addColorStop(0.6, "rgba(140,165,205,0.18)");
  grad.addColorStop(1, "rgba(140,165,205,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 256);
  const tex = new THREE.CanvasTexture(c);
  const spr = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, transparent: true, depthWrite: false, fog: false }));
  spr.scale.set(15, 15, 1);
  spr.position.set(-13, 12.5, -38);
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

  g.font = "bold 44px Georgia, serif";
  const nameLines = wrapText(g, project.name, 420).slice(0, 3);
  let y = 168;
  for (const line of nameLines) {
    engrave(line, y, "bold 44px Georgia, serif", pale);
    y += 52;
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

function makeStoneGeometry() {
  const s = new THREE.Shape();
  s.moveTo(-0.5, 0);
  s.lineTo(-0.5, 1.05);
  s.absarc(0, 1.05, 0.5, Math.PI, 0, true);
  s.lineTo(0.5, 0);
  s.closePath();
  const geo = new THREE.ExtrudeGeometry(s, {
    depth: 0.16, bevelEnabled: true, bevelThickness: 0.015,
    bevelSize: 0.015, bevelSegments: 1, curveSegments: 24,
  });
  geo.translate(0, 0, -0.08);
  return geo;
}
const stoneGeometry = makeStoneGeometry();

const interactive = [];
const stoneGroups = new Map();

function raiseStone(project, position, decorative) {
  const group = new THREE.Group();
  const tint = 0.92 + Math.random() * 0.16;
  const stoneMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color(0.42 * tint, 0.46 * tint, 0.5 * tint),
    roughness: 0.95, metalness: 0.02,
  });
  const body = new THREE.Mesh(stoneGeometry, stoneMat);
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
    const plaque = new THREE.Mesh(
      new THREE.PlaneGeometry(0.94, 1.18),
      new THREE.MeshBasicMaterial({
        map: makePlaqueTexture(project), transparent: true,
        opacity: Math.max(0.5, 1 - yearsDead * 0.05) }));
    plaque.position.set(0, 0.82, 0.098);
    group.add(plaque);
    group.userData.plaque = plaque;
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
  panel.hidden = false;
}

function closePanel() {
  selectedId = null;
  panel.hidden = true;
  document.querySelectorAll(".registry-list button.selected")
    .forEach((b) => b.classList.remove("selected"));
}
el("panel-close").addEventListener("click", closePanel);

// ---------- visiting a grave (click, registry, random, keys) ----------
let desiredCamPos = null;

function visitProject(project) {
  openPanel(project);
  const group = stoneGroups.get(project.id);
  if (!group) return;
  document.querySelectorAll(".registry-list button").forEach((b) => {
    b.classList.toggle("selected", b.dataset.id === project.id);
  });
  const p = group.position;
  desiredTarget.copy(p).add(new THREE.Vector3(0, 0.9, 0));
  // Stand on the path side of the stone, close enough to read it.
  const toward = new THREE.Vector3(-Math.sign(p.x), 0, 0.35).normalize();
  desiredCamPos = p.clone().add(toward.multiplyScalar(3.4));
  desiredCamPos.y = 1.9;
  userDrove = false;
  controls.autoRotate = false;
}

function cycleProject(step) {
  if (!allProjects.length) return;
  const idx = allProjects.findIndex((p) => p.id === selectedId);
  const next = allProjects[(idx + step + allProjects.length) % allProjects.length];
  visitProject(next);
}

window.addEventListener("keydown", (event) => {
  if (event.key === "ArrowRight") cycleProject(1);
  else if (event.key === "ArrowLeft") cycleProject(-1);
  else if (event.key === "Escape") closePanel();
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

renderer.domElement.addEventListener("pointermove", (event) => {
  hovered = castAt(event);
  renderer.domElement.style.cursor = hovered ? "pointer" : "";
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
    const pool = projects.filter((p) => p.id !== selectedId);
    const pick = pool[Math.floor(Math.random() * pool.length)] || projects[0];
    if (pick) visitProject(pick);
  });

  registry.hidden = false;
}

// ---------- build the grounds ----------
async function build() {
  let projects;
  try {
    const res = await fetch("projects.json");
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
  const perRow = 4;
  projects.forEach((project, i) => {
    const row = Math.floor(i / perRow);
    const col = i % perRow;
    const side = i % 2 === 0 ? -1 : 1;
    const pairIndex = Math.floor(col / 2);
    const x = side * (2.6 + pairIndex * 2.4) + (Math.random() - 0.5) * 0.5;
    const z = 2.5 - row * 3.1 + (Math.random() - 0.5) * 0.6;
    const group = raiseStone(project, new THREE.Vector3(x, 0, z), false);
    group.rotation.y = side * -0.18 + (Math.random() - 0.5) * 0.1;
  });

  // Weathered blank stones further out, pure set dressing.
  for (let i = 0; i < 26; i++) {
    const angle = Math.random() * Math.PI * 2;
    const radius = 13 + Math.random() * 16;
    const x = Math.cos(angle) * radius;
    const z = Math.sin(angle) * radius - 6;
    if (Math.abs(x) < 3.4) continue;
    raiseStone(null, new THREE.Vector3(x, 0, z), true)
      .lookAt(0, 0, z + 4);
  }

  allProjects = projects;
  buildRegistry(projects);

  const totalCommits = projects.reduce((n, p) => n + (p.commits || 0), 0);
  statsEl.textContent = totalCommits
    ? "Now resting: " + projects.length + " projects · " +
      totalCommits.toLocaleString() + " commits buried"
    : "Now resting: " + projects.length + " projects";
}
build();

// ---------- animate ----------
const clock = new THREE.Clock();
let prevT = 0;
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
