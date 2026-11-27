"use strict";
// Standalone node checks for site/bury.js — no dependencies.
// fetchRepos must paginate to exhaustion (no 300-repo cap), and
// classifyRepos must treat a null pushed_at as "no push record",
// never as the 1970 epoch. Run: node tests/bury.test.js
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const el = () => ({ addEventListener() {}, textContent: "", hidden: false });

let pages = [];
let requests = [];
const context = {
  console,
  URL,
  setTimeout,
  document: {
    getElementById: () => el(),
    createElement: () => el(),
  },
  fetch: async (url) => {
    requests.push(url);
    const page = Number(new URL(url).searchParams.get("page"));
    const batch = pages[page - 1] || [];
    return { status: 200, ok: true, json: async () => batch };
  },
};
vm.createContext(context);
vm.runInContext(
  fs.readFileSync(path.join(__dirname, "..", "site", "bury.js"), "utf8"),
  context);

const { fetchRepos, classifyRepos } = context;
assert.equal(typeof fetchRepos, "function", "fetchRepos is defined");
assert.equal(typeof classifyRepos, "function", "classifyRepos is defined");

function repo(name, created_at, pushed_at, extra) {
  return Object.assign({
    name,
    html_url: "https://github.com/u/" + name,
    fork: false,
    archived: false,
    created_at,
    pushed_at,
  }, extra);
}

function pageOf(n, offset) {
  return Array.from({ length: n }, (_, i) =>
    repo("r" + (offset + i), "2020-01-01T00:00:00Z", "2020-06-01T00:00:00Z"));
}

async function main() {
  // Pagination: 350 repos over 4 pages — past the old 3-page cap.
  pages = [pageOf(100, 0), pageOf(100, 100), pageOf(100, 200),
    pageOf(50, 300)];
  requests = [];
  const all = await fetchRepos("someone");
  assert.equal(all.length, 350, "all 350 repos fetched");
  assert.equal(requests.length, 4, "four pages requested");

  // An exact multiple of the page size ends on an empty page.
  pages = [pageOf(100, 0), pageOf(100, 100)];
  requests = [];
  const exact = await fetchRepos("someone");
  assert.equal(exact.length, 200, "all 200 repos fetched");
  assert.equal(requests.length, 3, "empty third page ends the walk");

  // Classification: null pushed_at is "no push record".
  const now = Date.parse("2026-01-01T00:00:00Z");
  const raw = [
    repo("old", "2020-01-01T00:00:00Z", "2020-06-01T00:00:00Z"),
    repo("fresh", "2025-01-01T00:00:00Z", "2025-12-27T00:00:00Z"),
    repo("empty", "2019-01-01T00:00:00Z", null),
    repo("forked-old", "2018-01-01T00:00:00Z", "2018-06-01T00:00:00Z",
      { fork: true }),
  ];
  const { repos, dead, coma, alive, unrecorded } = classifyRepos(raw, now);
  assert.equal(repos.length, 3, "fork excluded from the record");
  assert.deepEqual(dead.map((r) => r.name), ["old"]);
  assert.deepEqual(alive.map((r) => r.name), ["fresh"]);
  assert.equal(coma.length, 0);
  assert.deepEqual(unrecorded.map((r) => r.name), ["empty"]);
  const empty = unrecorded[0];
  assert.equal(empty.pushed, null, "no Date is manufactured");
  assert.equal(empty.silence, null, "no silence is invented");
  assert.ok(repos.every((r) => !r.pushed ||
    r.pushed.getFullYear() > 1970), "nothing is dated 1970");
  assert.equal(dead[0].name, "old",
    "the Coldest Case is a repo with a real last push");

  console.log("bury.test.js: all checks passed");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
