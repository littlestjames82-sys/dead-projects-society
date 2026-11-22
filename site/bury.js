"use strict";
// Bury a GitHub user: read the public record, pronounce on every repo.
// Bands match the CLI defaults: alive <= 30 days silent, intensive care
// 31-90, deceased beyond 90.

const DAY = 86400000;
const form = document.getElementById("bury-form");
const input = document.getElementById("bury-input");
const statusEl = document.getElementById("bury-status");
const resultsEl = document.getElementById("bury-results");
let lastVerdict = "";
let lastResult = null;

function setStatus(text) {
  statusEl.textContent = text;
  statusEl.hidden = !text;
}

function coroner(repo) {
  const spanDays = Math.max(0, Math.round(
    (repo.pushed - repo.created) / DAY));
  if (spanDays <= 3) return "Weekend fling";
  if (repo.created.getMonth() === 0 && spanDays <= 45) {
    return "New Year's resolution";
  }
  if (repo.silence >= 730) return "Cold case";
  if (spanDays >= 180) return "Faded away quietly";
  return "Cause unknown";
}

function fmtSpan(days) {
  if (days < 1) return "less than a day";
  if (days < 60) return days + (days === 1 ? " day" : " days");
  if (days < 730) {
    const m = Math.round(days / 30.44);
    return m + (m === 1 ? " month" : " months");
  }
  const y = Math.floor(days / 365.25);
  const m = Math.round((days - y * 365.25) / 30.44);
  return m > 0 ? y + "y " + m + "m" : y + "y";
}

function liFor(repo, kind) {
  const li = document.createElement("li");
  const a = document.createElement("a");
  a.href = repo.url;
  a.target = "_blank";
  a.rel = "noopener";
  a.textContent = repo.name;
  li.appendChild(a);
  const meta = document.createElement("span");
  meta.className = "bury-meta";
  if (kind === "dead") {
    meta.textContent = repo.created.getFullYear() + " — " +
      repo.pushed.getFullYear() + " · " + coroner(repo) +
      " · silent " + repo.silence.toLocaleString() + " days" +
      (repo.archived ? " · archived" : "");
  } else if (kind === "coma") {
    meta.textContent = "last push " + repo.silence + " days ago · lifespan " +
      fmtSpan((repo.pushed - repo.created) / DAY);
  } else {
    meta.textContent = "last push " + repo.silence + " days ago";
  }
  li.appendChild(meta);
  return li;
}

async function fetchRepos(user) {
  const repos = [];
  for (let page = 1; page <= 3; page++) {
    const res = await fetch("https://api.github.com/users/" +
      encodeURIComponent(user) + "/repos?per_page=100&sort=pushed&page=" +
      page);
    if (res.status === 404) throw new Error("No GitHub user by that name.");
    if (res.status === 403) {
      throw new Error("GitHub's public record office is busy (rate limit). " +
        "Try again in a little while.");
    }
    if (!res.ok) throw new Error("GitHub answered " + res.status + ".");
    const batch = await res.json();
    repos.push(...batch);
    if (batch.length < 100) break;
  }
  return repos;
}

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const user = input.value.trim().replace(/^@/, "");
  if (!user) return;
  resultsEl.hidden = true;
  setStatus("Reading the public record for " + user + "…");
  let raw;
  try {
    raw = await fetchRepos(user);
  } catch (e) {
    setStatus(e.message);
    return;
  }
  const now = Date.now();
  const repos = raw.filter((r) => !r.fork).map((r) => ({
    name: r.name,
    url: r.html_url,
    archived: !!r.archived,
    created: new Date(r.created_at),
    pushed: new Date(r.pushed_at),
    silence: Math.max(0, Math.floor((now - new Date(r.pushed_at)) / DAY)),
  }));
  if (!repos.length) {
    setStatus(user + " has no public repos of their own to pronounce on.");
    return;
  }
  const dead = repos.filter((r) => r.silence > 90)
    .sort((a, b) => b.silence - a.silence);
  const coma = repos.filter((r) => r.silence > 30 && r.silence <= 90)
    .sort((a, b) => b.silence - a.silence);
  const alive = repos.filter((r) => r.silence <= 30)
    .sort((a, b) => a.silence - b.silence);

  document.getElementById("bury-headline").textContent =
    "The Society has reviewed " + user + ".";
  const summary = dead.length + " buried · " + coma.length +
    " in intensive care · " + alive.length + " still breathing, of " +
    repos.length + " repos examined.";
  const archivedDead = dead.filter((r) => r.archived).length;
  document.getElementById("bury-summary").textContent = summary +
    (archivedDead ? " " + archivedDead + (archivedDead === 1
      ? " is" : " are") + " formally archived by GitHub itself." : "");

  const honors = [];
  if (dead.length) {
    const spans = dead.map((r) => ({
      r, span: (r.pushed - r.created) / DAY,
    }));
    const marathoner = spans.reduce((a, b) => (b.span > a.span ? b : a));
    const mayfly = spans.reduce((a, b) => (b.span < a.span ? b : a));
    const coldest = dead[0];
    honors.push(["The Marathoner", marathoner.r.name,
      fmtSpan(marathoner.span) + " of life"]);
    honors.push(["The Mayfly", mayfly.r.name,
      fmtSpan(mayfly.span) + " of life"]);
    honors.push(["The Coldest Case", coldest.name,
      "silent " + coldest.silence.toLocaleString() + " days"]);
  }
  const honorsEl = document.getElementById("bury-honors");
  honorsEl.innerHTML = "";
  for (const [title, name, detail] of honors) {
    const div = document.createElement("div");
    div.className = "bury-honor";
    div.innerHTML = "";
    const t = document.createElement("span");
    t.className = "bury-honor-title";
    t.textContent = title;
    const n = document.createElement("span");
    n.className = "bury-honor-name";
    n.textContent = name;
    const d = document.createElement("span");
    d.className = "bury-honor-detail";
    d.textContent = detail;
    div.append(t, n, d);
    honorsEl.appendChild(div);
  }

  const fill = (id, list, kind) => {
    const ul = document.getElementById(id);
    ul.innerHTML = "";
    if (!list.length) {
      const li = document.createElement("li");
      li.className = "bury-none";
      li.textContent = "None. The Society notes it.";
      ul.appendChild(li);
      return;
    }
    for (const repo of list) ul.appendChild(liFor(repo, kind));
  };
  fill("bury-dead", dead, "dead");
  fill("bury-coma", coma, "coma");
  fill("bury-alive", alive, "alive");

  lastResult = {
    user,
    dead: dead.length,
    coma: coma.length,
    alive: alive.length,
    total: repos.length,
    coldest: dead.length ? dead[0] : null,
  };
  lastVerdict = "Dead Projects Society reviewed @" + user + ": " + summary +
    (honors.length ? " Honors: " +
      honors.map((h) => h[0] + " — " + h[1]).join("; ") + "." : "") +
    " Bury your own: https://littlestjames82-sys.github.io/" +
    "dead-projects-society/bury.html";
  setStatus("");
  resultsEl.hidden = false;
});

function drawVerdictCard() {
  // The 1080x1080 card: the shareable unit, drawn from the verdict.
  const r = lastResult;
  const canvas = document.createElement("canvas");
  canvas.width = 1080;
  canvas.height = 1080;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#101418";
  ctx.fillRect(0, 0, 1080, 1080);
  ctx.strokeStyle = "#333d46";
  ctx.lineWidth = 2;
  ctx.strokeRect(30, 30, 1020, 1020);
  ctx.strokeStyle = "#232a31";
  ctx.lineWidth = 1;
  ctx.strokeRect(44, 44, 992, 992);
  ctx.textAlign = "center";
  ctx.fillStyle = "#8b96a0";
  ctx.font = "44px Georgia, serif";
  ctx.fillText("DEAD PROJECTS SOCIETY", 540, 215);
  ctx.fillStyle = "#c9cfc4";
  ctx.font = "31px Georgia, serif";
  ctx.fillText("The Society has reviewed @" + r.user + ".", 540, 300);
  ctx.fillStyle = "#e8e2d2";
  ctx.font = "230px Georgia, serif";
  ctx.fillText(String(r.dead), 540, 540);
  ctx.fillStyle = "#b08d57";
  ctx.font = "34px Georgia, serif";
  ctx.fillText("B U R I E D", 540, 610);
  ctx.fillStyle = "#aeb6ae";
  ctx.font = "30px Georgia, serif";
  ctx.fillText(r.dead + " buried · " + r.coma + " in intensive care · " +
    r.alive + " still breathing", 540, 700);
  ctx.fillStyle = "#c9cfc4";
  ctx.font = "30px Georgia, serif";
  if (r.coldest) {
    ctx.fillText("The Coldest Case: " + r.coldest.name + ", silent " +
      r.coldest.silence.toLocaleString() + " days.", 540, 790);
  }
  ctx.fillStyle = "#77828d";
  ctx.font = "25px Georgia, serif";
  ctx.fillText("Bury your own: littlestjames82-sys.github.io/" +
    "dead-projects-society/bury.html", 540, 985);
  return canvas;
}

document.getElementById("bury-card").addEventListener("click", () => {
  if (!lastResult) return;
  drawVerdictCard().toBlob((blob) => {
    if (!blob) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "dead-projects-society-" + lastResult.user + ".png";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }, "image/png");
});

document.getElementById("bury-copy").addEventListener("click", async () => {
  if (!lastVerdict) return;
  try {
    await navigator.clipboard.writeText(lastVerdict);
    const note = document.getElementById("bury-copied");
    note.hidden = false;
    setTimeout(() => { note.hidden = true; }, 2000);
  } catch (e) { /* clipboard unavailable; the verdict stays on screen */ }
});
