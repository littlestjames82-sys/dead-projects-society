#!/usr/bin/env python3
"""Dead Projects Society: a funeral for your abandoned side projects.

Point it at the folder where your projects go to die. It reads each git
repository's history (locally, read-only, metadata and commit messages
only) and builds a graveyard: a tombstone for every project that has gone
silent, with its lifespan, its last words (the final commit message), a
cause of death, and the successor project that suspiciously replaced it.

Projects still showing a pulse are listed separately. The Society does
not bury the living.

Pure Python standard library. No dependencies, no network, no telemetry.
Your code never leaves the machine; only git log metadata is read.

Usage:
    dead-projects-society [PATH] [--days N] [--depth N]
                          [--html FILE] [--card FILE] [--out FILE] [--json]
                          [--site DIR]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape as xml_escape

VERSION = "0.20.0"

DEFAULT_DEAD_DAYS = 90
COMA_DAYS = 30

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Project:
    name: str
    path: str
    born: datetime          # first commit
    died: datetime          # last commit
    commits: int
    first_words: str        # first commit message subject
    last_words: str         # last commit message subject
    authors: int
    has_readme: bool
    has_remote: bool
    silence_days: int       # days from last commit to "now"
    gaps: list = field(default_factory=list)  # silences > 30 days, in days
    status: str = ""        # alive | coma | deceased
    cause: str = ""
    factors: list = field(default_factory=list)
    survived_by: str = ""
    resurrections: int = 0      # flatlines >= the death line, then a commit
    longest_flatline: int = 0   # longest mid-life silence, in days
    activity: list = field(default_factory=list)  # commits per month
    language: str = ""          # top language, from file names only
    dep_commits: int = 0        # commits about dependencies/upkeep
    dep_tail_share: float = 0.0  # dep share of the newest 10 commits
    will_status: str = ""       # from PROJECT_WILL.md: complete | adoptable
    will_successor: str = ""    # named in the will, if anyone was
    will_note: str = ""         # a line from the will, in the author's words

    @property
    def lifespan_days(self):
        return max(0, (self.died - self.born).days)


@dataclass
class Cemetery:
    root: str
    generated: datetime
    dead_days: int
    projects: list = field(default_factory=list)

    @property
    def deceased(self):
        return [p for p in self.projects if p.status == "deceased"]

    @property
    def coma(self):
        return [p for p in self.projects if p.status == "coma"]

    @property
    def alive(self):
        return [p for p in self.projects if p.status == "alive"]

    @property
    def resting(self):
        return [p for p in self.projects if p.status == "resting"]

    @property
    def buried_commits(self):
        return sum(p.commits for p in self.deceased)

    @property
    def avg_lifespan(self):
        d = self.deceased
        if not d:
            return 0.0
        return sum(p.lifespan_days for p in d) / len(d)


# ---------------------------------------------------------------------------
# Git reading (read-only)
# ---------------------------------------------------------------------------


def _git(path, *args):
    try:
        out = subprocess.run(
            ["git", "-C", path, *args],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


def find_repos(root, depth=1):
    """Yield repo paths: root itself, plus subdirectories up to depth."""
    root = os.path.abspath(root)
    found = []

    def is_repo(p):
        return os.path.isdir(os.path.join(p, ".git")) or os.path.isfile(
            os.path.join(p, ".git"))

    if is_repo(root):
        found.append(root)
    level = [root]
    for _ in range(max(0, depth)):
        nxt = []
        for base in level:
            try:
                names = sorted(os.listdir(base))
            except OSError:
                continue
            for name in names:
                if name.startswith("."):
                    continue
                p = os.path.join(base, name)
                if os.path.isdir(p):
                    nxt.append(p)
                    if is_repo(p):
                        found.append(p)
        level = nxt
    # De-duplicate, keep order.
    seen, out = set(), []
    for p in found:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def read_project(path, now):
    log = _git(path, "log", "--format=%ct%x09%s")
    if not log:
        return None
    lines = [l for l in log.splitlines() if l.strip()]
    if not lines:
        return None

    def parse(line):
        ts, _, msg = line.partition("\t")
        try:
            when = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None, ""
        return when, msg.strip()

    newest = parse(lines[0])
    oldest = parse(lines[-1])
    if newest[0] is None or oldest[0] is None:
        return None
    died, last_words = newest
    born, first_words = oldest

    # Mid-life silences: gaps between consecutive commits (log is
    # newest-first). Only gaps past the coma line are worth recording.
    gaps = []
    months = {}
    prev = None
    for line in lines:
        when, _ = parse(line)
        if when is None:
            continue
        key = (when.year, when.month)
        months[key] = months.get(key, 0) + 1
        if prev is not None:
            gap = (prev - when).days
            if gap > COMA_DAYS:
                gaps.append(gap)
        prev = when
    activity = []
    if months:
        y, m = oldest[0].year, oldest[0].month
        end = (newest[0].year, newest[0].month)
        while (y, m) <= end and len(activity) < 240:
            activity.append(months.get((y, m), 0))
            m += 1
            if m > 12:
                y, m = y + 1, 1

    msgs = []
    for line in lines:
        _, m = parse(line)
        msgs.append(m)
    dep_hits = [1 if _DEP_RE.search(m) else 0 for m in msgs]
    dep_commits = sum(dep_hits)
    tail = dep_hits[:10]
    dep_tail_share = (sum(tail) / len(tail)) if tail else 0.0

    will_status, will_successor, will_note = _read_will(path)
    language = _detect_language(path)
    authors_raw = _git(path, "log", "--format=%an")
    authors = len({a for a in (authors_raw or "").splitlines() if a.strip()})
    remotes = _git(path, "remote")
    has_remote = bool(remotes and remotes.strip())
    has_readme = any(
        os.path.isfile(os.path.join(path, f))
        for f in ("README.md", "README", "README.rst", "README.txt",
                  "readme.md"))

    return Project(
        name=os.path.basename(path.rstrip("/")) or path,
        path=path,
        born=born,
        died=died,
        commits=len(lines),
        first_words=first_words,
        last_words=last_words,
        authors=max(authors, 1),
        has_readme=has_readme,
        has_remote=has_remote,
        silence_days=max(0, (now - died).days),
        gaps=gaps,
        activity=activity,
        language=language,
        dep_commits=dep_commits,
        dep_tail_share=dep_tail_share,
        will_status=will_status,
        will_successor=will_successor,
        will_note=will_note,
    )


_LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".rs": "Rust",
    ".go": "Go", ".rb": "Ruby", ".java": "Java", ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".cs": "C#", ".php": "PHP",
    ".swift": "Swift", ".kt": "Kotlin", ".sh": "Shell", ".lua": "Lua",
    ".pl": "Perl", ".r": "R", ".scala": "Scala", ".ex": "Elixir",
    ".hs": "Haskell", ".dart": "Dart", ".vue": "Vue",
    ".svelte": "Svelte", ".m": "Objective-C", ".ml": "OCaml",
}
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
              "dist", "build", "target", ".next", ".tox"}


def _detect_language(path):
    """The top language of a repo, from file names alone.

    File contents are never opened; this counts extensions the way
    the Society already checks whether a README exists.
    """
    counts = {}
    scanned = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for f in files:
            scanned += 1
            if scanned > 4000:
                break
            lang = _LANG_BY_EXT.get(os.path.splitext(f)[1].lower())
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
        if scanned > 4000:
            break
    if not counts:
        return ""
    return max(counts, key=counts.get)


_WILL_FILES = ("PROJECT_WILL.md", "PROJECT_WILL", "project_will.md")


def _read_will(path):
    """Read a project's will, if it left one.

    A will is a small file the author writes for whoever finds the
    project later (the Society's own convention). Only three lines are
    read: Status, Successor, Note. A will that says the work is
    complete is authoritative: the Society does not bury the finished.
    """
    for fname in _WILL_FILES:
        fpath = os.path.join(path, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8",
                      errors="replace") as fh:
                text = fh.read(4096)
        except OSError:
            return "", "", ""
        status = successor = note = ""
        for line in text.splitlines():
            key, sep, val = line.partition(":")
            if not sep:
                continue
            k = key.strip().lower().lstrip("#").strip()
            v = val.strip().strip("*").strip()
            if k == "status" and not status:
                status = v.lower()
            elif k == "successor" and not successor:
                successor = v
            elif k == "note" and not note:
                note = v
        normalized = ""
        if any(w in status for w in ("complete", "finish", "done",
                                     "retired")):
            normalized = "complete"
        elif "adopt" in status:
            normalized = "adoptable"
        return normalized, successor, note
    return "", "", ""


# ---------------------------------------------------------------------------
# The coroner: status, cause of death, contributing factors, succession
# ---------------------------------------------------------------------------

_WIP_RE = re.compile(r"^(wip|temp|tmp|test|testing|asdf|checkpoint|save)\b",
                     re.IGNORECASE)
_FIX_RE = re.compile(r"\bfix", re.IGNORECASE)
_REFACTOR_RE = re.compile(
    r"\b(refactor|cleanup|clean up|reorganiz\w*|restructur\w*|tidy)\b",
    re.IGNORECASE)
_RENAME_RE = re.compile(
    r"\b(rename|renamed|renaming|migrat\w+|moved to|switching to)\b",
    re.IGNORECASE)
_DOCS_RE = re.compile(r"\b(readme|docs?|documentation|changelog)\b",
                      re.IGNORECASE)
_WAIT_RE = re.compile(r"\b(todo|blocked|waiting on|waiting for|pending)\b",
                      re.IGNORECASE)
_SEQUEL_RE = re.compile(
    r"\b(v2|rewrite|rewriting|new version|next gen|rebuilt|2\.0)\b",
    re.IGNORECASE)
_DEP_RE = re.compile(
    r"\b(dependabot|bump\w*|upgrad\w*|dependencies|dependency|deps|"
    r"migrat\w*)\b",
    re.IGNORECASE)
_COMPLETE_RE = re.compile(
    r"(final release|stable release|release\s+v?\d|v?\d+\.\d+(\.\d+)?"
    r"\s+release|farewell|goodbye|project (is )?complete|archiv\w*|"
    r"sunset|end of life)",
    re.IGNORECASE)


def classify(p, dead_days):
    if p.silence_days <= COMA_DAYS:
        p.status = "alive"
    elif p.silence_days <= dead_days:
        p.status = "coma"
    else:
        p.status = "deceased"


def cause_of_death(p):
    life = p.lifespan_days
    msg = p.last_words or ""
    if p.commits == 1:
        return "One-commit wonder. Full confidence, no follow-through."
    if life == 0:
        return "Born and buried the same day. A beautiful 24 hours."
    if _WIP_RE.match(msg):
        return "Died mid-sentence. Its final commit was never finished."
    if msg.lower().startswith("merge "):
        return "Died in a merge. The paperwork was impeccable."
    if p.commits >= 10 and p.dep_tail_share >= 0.7:
        return ("Died maintaining. Its final chapter was dependency "
                "bumps, upgrades, and migrations; the work became "
                "upkeep, and then it stopped.")
    if _WAIT_RE.search(msg):
        return ("Died waiting. The thing it was waiting for never came.")
    if _RENAME_RE.search(msg) and p.commits >= 5:
        return "Killed by a rename. It answers to something else now."
    if p.born.month == 1 and life <= 45:
        return "New Year's resolution. You know how those go."
    if life <= 3 and p.commits <= 15:
        return "Weekend fling. It was never going to be a thing."
    if _FIX_RE.search(msg) and p.commits >= 20:
        return "Died as it lived: one more fix."
    if _DOCS_RE.search(msg) and p.commits >= 20:
        return ("Died writing the manual. The last thing it did was "
                "explain itself.")
    if _REFACTOR_RE.search(msg) and p.commits >= 10:
        return ("Died in a refactor. It was going to be cleaner. "
                "It was going to be beautiful.")
    if _COMPLETE_RE.search(msg) and p.commits >= 10:
        return ("Finished, by the look of it. The last words read like "
                "a farewell, not a collapse.")
    if p.commits >= 100:
        return ("Sudden cardiac arrest. %d commits, then silence."
                % p.commits)
    if life >= 180 and p.commits <= 12:
        return ("Starved. A commit every few weeks, then none. "
                "It needed feeding, not features.")
    if p.silence_days >= 730:
        return "Cold case. Even the trail has gone quiet."
    if life >= 180:
        return "Faded away quietly over %d days." % life
    return "Cause unknown. The trail simply ends."


def contributing_factors(p):
    f = []
    if not p.has_readme:
        f.append("No README. Nobody knew what it was for, including, "
                 "eventually, its author.")
    if not p.has_remote:
        f.append("Never left the house. No remote; nobody ever saw it.")
    if p.authors == 1:
        f.append("No witnesses. Sole author throughout.")
    if p.will_status == "adoptable":
        f.append("Left for adoption. Its will asks for a new keeper.")
    return f


def assign_succession(projects):
    """For each deceased project, find the next project born after it died.

    The Society notes the timing.
    """
    ordered = sorted(projects, key=lambda p: p.born)
    for p in projects:
        if p.status != "deceased":
            continue
        successor = None
        for cand in ordered:
            if cand is p:
                continue
            gap = (cand.born - p.died).days
            if 0 <= gap <= 60:
                successor = (cand, gap)
                break
        if successor:
            cand, gap = successor
            when = "the same day" if gap == 0 else (
                "1 day later" if gap == 1 else "%d days later" % gap)
            p.survived_by = ("Survived by %s, born %s. The Society notes "
                             "the timing." % (cand.name, when))
        else:
            p.survived_by = "Survived by no one. The last of its line, " \
                            "for now."


def build_grounds(roots, dead_days=DEFAULT_DEAD_DAYS, depth=1,
                  now=None):
    """One cemetery over several folders. Projects are merged,
    duplicates (the same repo reached through two roots) are kept
    once, and succession is judged across the whole union: the
    Society has always suspected the replacement was started in a
    different folder."""
    now = now or datetime.now(timezone.utc)
    if len(roots) == 1:
        return build_cemetery(roots[0], dead_days=dead_days,
                              depth=depth, now=now)
    seen = {}
    for root in roots:
        part = build_cemetery(root, dead_days=dead_days, depth=depth,
                              now=now)
        for p in part.projects:
            seen[os.path.abspath(p.path)] = p
    projects = sorted(seen.values(), key=lambda p: p.born)
    assign_succession(projects)
    label = "%d grounds (%s)" % (
        len(roots), ", ".join(os.path.abspath(r) for r in roots))
    return Cemetery(root=label, generated=now, dead_days=dead_days,
                    projects=projects)


def build_cemetery(root, dead_days=DEFAULT_DEAD_DAYS, depth=1, now=None):
    now = now or datetime.now(timezone.utc)
    cem = Cemetery(root=os.path.abspath(root), generated=now,
                   dead_days=dead_days)
    for path in find_repos(root, depth=depth):
        p = read_project(path, now)
        if p is None:
            continue
        classify(p, dead_days)
        p.longest_flatline = max(p.gaps, default=0)
        p.resurrections = sum(1 for g in p.gaps if g >= dead_days)
        if p.status == "deceased" and p.will_status == "complete":
            p.status = "resting"
            p.cause = ("Completed. The author left a will, and the will "
                       "says finished. The Society does not bury the "
                       "finished.")
            p.factors = contributing_factors(p)
        if p.status == "deceased":
            p.cause = cause_of_death(p)
            p.factors = contributing_factors(p)
        cem.projects.append(p)
    assign_succession(cem.projects)
    for p in cem.projects:
        if p.will_successor and p.status in ("deceased", "resting"):
            p.survived_by = ("Survived by %s, named in its will."
                             % p.will_successor)
        if (p.status == "deceased" and p.survived_by
                and not p.survived_by.startswith("Survived by no one")
                and _SEQUEL_RE.search(p.last_words or "")):
            p.cause = ("Died of a sequel. The replacement was already "
                       "on the way.")
    cem.projects.sort(key=lambda p: p.died)
    return cem


# ---------------------------------------------------------------------------
# The Society's Honors: superlatives, awarded without appeal
# ---------------------------------------------------------------------------


def society_honors(cem):
    honors = []
    dead = cem.deceased
    if dead:
        p = max(dead, key=lambda x: x.lifespan_days)
        honors.append({
            "title": "The Marathoner",
            "project": p,
            "detail": "Lived %s across %d commits before the end."
                      % (_site_life_text(p.lifespan_days), p.commits),
        })
        p = min(dead, key=lambda x: x.lifespan_days)
        honors.append({
            "title": "The Mayfly",
            "project": p,
            "detail": "Born and buried within %s. No wasted motion."
                      % _site_life_text(p.lifespan_days),
        })
        p = max(dead, key=lambda x: x.commits)
        honors.append({
            "title": "The Loudest Exit",
            "project": p,
            "detail": "%d commits, then silence." % p.commits,
        })
        p = max(dead, key=lambda x: x.silence_days)
        honors.append({
            "title": "The Coldest Case",
            "project": p,
            "detail": "Silent for %d days and counting." % p.silence_days,
        })
    risen = [p for p in cem.projects if p.resurrections >= 1]
    if risen:
        p = max(risen, key=lambda x: (x.resurrections, x.longest_flatline))
        honors.append({
            "title": "The Phoenix",
            "project": p,
            "detail": "Flatlined for %d days and came back %s."
                      % (p.longest_flatline,
                         "once" if p.resurrections == 1
                         else "%d times" % p.resurrections),
        })
    return honors


def hall_of_infamy(cem):
    """The Honors, pointed the other way. Entered without appeal."""
    infamy = []
    dead = cem.deceased
    if not dead:
        return infamy
    shooters = [p for p in dead
                if p.lifespan_days >= 1 and p.commits >= 10]
    if shooters:
        p = max(shooters,
                key=lambda x: x.commits / max(1, x.lifespan_days))
        infamy.append({
            "title": "The Shooting Star",
            "project": p,
            "detail": "%d commits in %s, then nothing. Burned brightest, "
                      "fastest." % (p.commits,
                                    _site_life_text(p.lifespan_days)),
        })
    crowds = [p for p in dead if p.authors >= 2]
    if crowds:
        p = max(crowds, key=lambda x: x.authors)
        infamy.append({
            "title": "The Crowd That Left",
            "project": p,
            "detail": "%d authors at its height. Every one of them gone."
                      % p.authors,
        })
    unknowns = [p for p in dead if not p.has_readme and not p.has_remote]
    if unknowns:
        p = max(unknowns, key=lambda x: x.commits)
        infamy.append({
            "title": "The Unknown Soldier",
            "project": p,
            "detail": "%d commits, no README, no remote. Did the most, "
                      "told no one." % p.commits,
        })
    stutters = [p for p in dead if len(p.gaps) >= 2]
    if stutters:
        p = max(stutters, key=lambda x: len(x.gaps))
        infamy.append({
            "title": "The Stutter",
            "project": p,
            "detail": "Stopped and started %d times, then stopped."
                      % len(p.gaps),
        })
    return infamy


_SPARK = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _month_label(born, offset):
    total = born.year * 12 + (born.month - 1) + offset
    year, month0 = divmod(total, 12)
    return "%s %d" % (_MONTH_ABBR[month0], year)


def sparkline(activity):
    """A life, in one line: commits per month, flatlines visible."""
    if not activity:
        return ""
    peak = max(activity) or 1
    return "".join(_SPARK[round(v / peak * 8)] for v in activity)


def autopsy(p):
    """The metadata autopsy: what the record shows, and revival odds.

    Reads only what the Society already lawfully knows: dates, counts,
    messages, and the will. No code is opened, here or anywhere.
    """
    life = max(1, p.lifespan_days)
    pace = p.commits / life * 30.44
    if p.will_status == "complete":
        end = "Declared complete by its author, in writing."
    elif _WIP_RE.match(p.last_words or ""):
        end = "Ended mid-sentence: the final commit was never finished."
    elif _COMPLETE_RE.search(p.last_words or ""):
        end = "Ended tidily: the last words read like a farewell."
    elif (p.last_words or "").lower().startswith("merge "):
        end = "Ended in paperwork: a merge, then silence."
    elif _FIX_RE.search(p.last_words or ""):
        end = "Ended mid-repair: one more fix, then silence."
    else:
        end = "Ended without ceremony: an ordinary commit, then silence."
    activity = list(p.activity or [])
    active_months = sum(1 for v in activity if v > 0)
    peak_commits = max(activity) if activity else 0
    peak_index = activity.index(peak_commits) if activity else -1
    peak_month = (_month_label(p.born, peak_index)
                  if peak_index >= 0 else None)
    peak_share = (peak_commits / p.commits * 100.0
                  if p.commits and peak_commits else 0.0)
    half = len(activity) // 2
    first_half = sum(activity[:half]) if half else 0
    second_half = sum(activity[half:]) if half else 0
    if not activity:
        momentum = ("No monthly record survives; the Department will "
                    "not invent a rhythm.")
    elif len(activity) <= 1:
        momentum = ("Too short to read: the whole life fits inside "
                    "one month.")
    elif peak_share >= 60:
        momentum = ("One bright burst: %.0f%% of the life landed in %s."
                    % (peak_share, peak_month))
    elif half and first_half and second_half <= first_half * 0.35:
        momentum = ("Front-loaded: the first half carried %d commits; "
                    "the second half faded to %d."
                    % (first_half, second_half))
    elif half and first_half and second_half >= first_half * 1.5:
        momentum = ("Late surge: the second half outpaced the first "
                    "(%d against %d), which makes the silence harder "
                    "to explain." % (second_half, first_half))
    elif p.longest_flatline >= 30:
        momentum = ("Interrupted life: it stopped for %d days at "
                    "least once before the final silence."
                    % p.longest_flatline)
    else:
        momentum = ("Steady burn: no single month owned the story; "
                    "it wound down rather than falling off a cliff.")
    findings = []
    if activity and p.commits >= 10 and peak_commits:
        findings.append("Peak month: %s, with %d commits (%.0f%% of "
                        "the life)." % (peak_month, peak_commits,
                                         peak_share))
    if p.longest_flatline >= 30:
        findings.append("Longest premortem silence: %d days."
                        % p.longest_flatline)
    if p.commits >= 10 and p.dep_commits:
        dep_share = p.dep_commits / p.commits * 100.0
        if dep_share >= 30:
            findings.append(
                "Dependency era: %d of %d commits (%.0f%%) were bumps, "
                "upgrades, and migrations."
                % (p.dep_commits, p.commits, dep_share))
    if not p.has_readme:
        findings.append("No README: a stranger arriving now gets no "
                        "explanation.")
    if not p.has_remote:
        findings.append("No remote: the only copy lived on one "
                        "machine.")
    if p.authors <= 1:
        findings.append("Bus factor one: a single pair of hands knew "
                        "the whole story.")
    elif p.authors >= 5:
        findings.append("Bus factor %d: the knowledge was not trapped "
                        "in one head." % p.authors)
    score = 0
    reasons = []
    if p.resurrections >= 1:
        score += 3
        reasons.append("it has risen before")
    if p.will_status == "adoptable":
        score += 2
        reasons.append("its will asks for a new keeper")
    if p.has_remote:
        score += 1
        reasons.append("the world can still reach it")
    if p.has_readme:
        score += 1
        reasons.append("it explains itself")
    if p.authors >= 2:
        score += 1
        reasons.append("more than one witness knows it")
    if p.silence_days < 365:
        score += 1
        reasons.append("the trail is still warm")
    if p.commits >= 50:
        score += 1
        reasons.append("there is real substance to revive")
    if p.will_status == "complete":
        verdict = "Let it rest. It finished."
    elif score >= 5:
        verdict = "Worth exhuming."
    elif score >= 3:
        verdict = "Long odds, but not none."
    else:
        verdict = "Let it rest."
    return {
        "pace_commits_per_month": round(pace, 1),
        "flatlines": len(p.gaps),
        "active_months": active_months,
        "peak_month": peak_month,
        "peak_commits": peak_commits,
        "peak_share_percent": round(peak_share, 1),
        "momentum": momentum,
        "findings": findings,
        "dependency_commits": p.dep_commits,
        "dependency_tail_share": round(p.dep_tail_share, 2),
        "end_pattern": end,
        "revival_score": score,
        "revival_verdict": verdict,
        "revival_reasons": reasons,
    }


def _adoption_needs(p):
    needs = []
    if p.will_status == "adoptable":
        needs.append("Only a keeper. Its will already asks for one.")
    verdict = autopsy(p)["revival_verdict"]
    if verdict.startswith("Worth exhuming"):
        needs.append("Mostly a decision. The record says it was "
                     "strong.")
    if not p.has_remote:
        needs.append("To be seen in public. It never left the house.")
    if not p.has_readme:
        needs.append("A README, and a reason.")
    if p.authors == 1:
        needs.append("A second pair of hands.")
    if not needs:
        needs.append("Time, and someone who remembers why it "
                     "mattered.")
    return needs


def render_adoption_papers(cem):
    """Adoption papers for the buried: one listing per project,
    pitched honestly from its own record."""
    lines = [
        "# ADOPTION PAPERS",
        "",
        "Issued by the Dead Projects Society, for the grounds at %s."
        % cem.root,
        "",
        "The following projects are deceased and available for "
        "adoption. Each listing is drawn from the project's own "
        "record; the Society varnishes nothing. Adoption is a "
        "promise, not a download: whoever signs below takes the "
        "project, its history, and its last words, and gives it a "
        "future.",
        "",
    ]
    buried = cem.deceased
    if not buried:
        lines.append("No projects are available for adoption. The "
                     "grounds hold no one who needs a keeper.")
    for p in buried:
        lines += [
            "## %s" % p.name,
            "",
            "- Died: %s (silent %d days). Lifespan %d days, %d "
            "commits." % (p.died.date().isoformat(), p.silence_days,
                          p.lifespan_days, p.commits),
            "- Cause: %s" % (p.cause or "Cause unknown."),
            "- Last words: \"%s\"" % (p.last_words or "(none)"),
            "- The Society's assessment: %s"
            % autopsy(p)["revival_verdict"],
            "- What it needs: %s" % " ".join(_adoption_needs(p)),
            "",
            "Adopted by: ____________________________   Date: "
            "____________",
            "",
        ]
    lines += [
        "---",
        "",
        "The Society charges nothing for adoptions. It never has.",
    ]
    return "\n".join(lines) + "\n"


def compose_eulogy(p):
    """A few kind sentences, assembled from the facts of the life."""
    life = p.lifespan_days
    if life < 7:
        opener = "It burned fast."
    elif life < 60:
        opener = "It had a short, bright season."
    elif life < 365:
        opener = "It had a real season."
    else:
        opener = "It had a long life, by side-project standards."
    if p.commits >= 500:
        middle = "Its %d commits say it was loved." % p.commits
    elif p.commits >= 50:
        middle = "Its %d commits say it was meant." % p.commits
    elif p.commits >= 10:
        middle = "Its %d commits say it was more than an idea." % p.commits
    elif p.commits >= 2:
        middle = "Its %d commits are nearly all that remain." % p.commits
    else:
        middle = "Its single commit is nearly all that remains."
    if p.survived_by and "no one" not in p.survived_by:
        closer = "The Society notes what replaced it."
    else:
        closer = "Nothing replaced it. The slot is still open."
    return "%s %s %s" % (opener, middle, closer)


# ---------------------------------------------------------------------------
# Rendering: terminal
# ---------------------------------------------------------------------------


def _fmt_date(dt):
    return dt.strftime("%b %d, %Y")


def _lifespan_text(p):
    d = p.lifespan_days
    if d == 0:
        return "less than a day"
    if d == 1:
        return "1 day"
    if d < 60:
        return "%d days" % d
    if d < 730:
        return "%d months" % round(d / 30.44)
    return "%.1f years" % (d / 365.25)


def on_this_day(cem):
    """Anniversaries in the grounds: projects that died on this
    month and day in an earlier year, and projects born on it.
    A reason to visit the cemetery more than once."""
    today = cem.generated.date()
    deaths, births = [], []
    for p in cem.deceased + cem.resting:
        if (p.died.month, p.died.day) == (today.month, today.day) \
                and p.died.year < today.year:
            deaths.append({"name": p.name,
                           "years_ago": today.year - p.died.year,
                           "status": p.status,
                           "cause": p.cause})
    for p in cem.projects:
        if (p.born.month, p.born.day) == (today.month, today.day) \
                and p.born.year < today.year:
            births.append({"name": p.name,
                           "years_ago": today.year - p.born.year,
                           "status": p.status})
    deaths.sort(key=lambda d: -d["years_ago"])
    births.sort(key=lambda d: -d["years_ago"])
    return {"date": today.isoformat(), "deaths": deaths, "births": births}


def _years_text(n):
    return "1 year ago" if n == 1 else "%d years ago" % n


_ONELINE_STATUS = {
    "deceased": "buried",
    "resting": "at rest",
    "coma": "intensive care",
    "alive": "still breathing",
}


def render_oneline(cem):
    """One line per project: name, state, silence, cause. For quick
    scans and for pipes; the full report remains the ceremony."""
    lines = []
    ordered = cem.deceased + cem.resting + cem.coma + cem.alive
    for p in ordered:
        parts = [p.name, _ONELINE_STATUS[p.status],
                 "silent %dd" % p.silence_days]
        if p.cause:
            parts.append(p.cause.split(".")[0].strip())
        lines.append(" - ".join(parts))
    return "\n".join(lines) + ("\n" if lines else "")


def render_terminal(cem, with_autopsy=False, with_on_this_day=False):
    out = []
    out.append("")
    out.append("=" * 64)
    out.append("  DEAD PROJECTS SOCIETY")
    out.append("  The roll of the departed, read aloud once a year"
               " whether you like it or not.")
    out.append("=" * 64)
    out.append("  Grounds: %s" % cem.root)
    counts = ("  Buried: %d   In a coma: %d   Still breathing: %d"
              % (len(cem.deceased), len(cem.coma), len(cem.alive)))
    if cem.resting:
        counts += "   At rest: %d" % len(cem.resting)
    out.append(counts)
    if cem.deceased:
        out.append("  Commits buried: %d   Average lifespan: %s"
                   % (cem.buried_commits,
                      "%.0f days" % cem.avg_lifespan))
    out.append("")
    for p in cem.deceased:
        out.append("-" * 64)
        out.append("  R.I.P.  %s" % p.name)
        out.append("  %s to %s  (aged %s, %d commits)"
                   % (_fmt_date(p.born), _fmt_date(p.died),
                      _lifespan_text(p), p.commits))
        out.append('  Last words: "%s"' % (p.last_words or "(silence)"))
        out.append("  Cause of death: %s" % p.cause)
        if p.resurrections >= 1:
            out.append("  Note: it had already flatlined for %d days once"
                       " and come back. This time it did not."
                       % p.longest_flatline)
        for f in p.factors:
            out.append("  Contributing: %s" % f)
        out.append("  %s" % p.survived_by)
    for p in cem.resting:
        out.append("-" * 64)
        out.append("  AT REST  %s" % p.name)
        out.append("  %s to %s  (aged %s, %d commits)"
                   % (_fmt_date(p.born), _fmt_date(p.died),
                      _lifespan_text(p), p.commits))
        out.append('  Last words: "%s"' % (p.last_words or "(silence)"))
        out.append("  %s" % p.cause)
        if p.will_note:
            out.append("  From its will: %s" % p.will_note)
        out.append("  %s" % p.survived_by)
    if cem.coma:
        out.append("-" * 64)
        out.append("  INTENSIVE CARE (silent %d to %d days; the Society"
                   " does not bury the living)"
                   % (COMA_DAYS + 1, cem.dead_days))
        for p in cem.coma:
            out.append("  ~ %s: last seen %s, %d days ago"
                       % (p.name, _fmt_date(p.died), p.silence_days))
    if cem.alive:
        out.append("-" * 64)
        out.append("  STILL BREATHING")
        for p in cem.alive:
            out.append("  + %s: active %d days ago"
                       % (p.name, p.silence_days))
    risen = [p for p in cem.projects if p.resurrections >= 1]
    if risen:
        out.append("-" * 64)
        out.append("  BACK FROM THE DEAD (flatlined past the death line,"
                   " then committed again)")
        for p in risen:
            times = ("once" if p.resurrections == 1
                     else "%d times" % p.resurrections)
            out.append("  * %s: flatlined for %d days, rose again %s"
                       % (p.name, p.longest_flatline, times))
    honors = society_honors(cem)
    if honors:
        out.append("-" * 64)
        out.append("  THE SOCIETY'S HONORS (awarded without appeal)")
        for h in honors:
            out.append("  ~ %s: %s. %s"
                       % (h["title"], h["project"].name, h["detail"]))
    infamy = hall_of_infamy(cem)
    if infamy:
        out.append("-" * 64)
        out.append("  HALL OF INFAMY (entered without appeal)")
        for h in infamy:
            out.append("  ~ %s: %s. %s"
                       % (h["title"], h["project"].name, h["detail"]))
    if with_autopsy:
        subjects = cem.deceased + cem.resting
        if subjects:
            out.append("-" * 64)
            out.append("  THE AUTOPSY DEPARTMENT (from the record alone)")
            for p in subjects:
                a = autopsy(p)
                line = ("  * %s: %.1f commits a month while it lived; "
                        "%s Revival: %s"
                        % (p.name, a["pace_commits_per_month"],
                           a["end_pattern"], a["revival_verdict"]))
                spark = sparkline(p.activity)
                if spark:
                    line += " Life: %s" % spark
                out.append(line)
                out.append("    Momentum: %s" % a["momentum"])
                if a["findings"]:
                    out.append("    Findings: %s"
                               % " ".join(a["findings"][:4]))
    if with_on_this_day:
        otd = on_this_day(cem)
        out.append("-" * 64)
        out.append("  ON THIS DAY IN THE GROUNDS")
        if not otd["deaths"] and not otd["births"]:
            out.append("  Nothing happened on this day. "
                       "The grounds are quiet.")
        for d in otd["deaths"]:
            out.append("  ~ %s died on this day, %s. %s"
                       % (d["name"], _years_text(d["years_ago"]),
                          d["cause"]))
        for b in otd["births"]:
            state = ("It is still breathing." if b["status"] == "alive"
                     else "The Society keeps its stone ready."
                     if b["status"] == "coma"
                     else "It rests in these grounds.")
            out.append("  ~ %s was born on this day, %s. %s"
                       % (b["name"], _years_text(b["years_ago"]), state))
    out.append("-" * 64)
    if cem.deceased:
        longest = max(cem.deceased, key=lambda p: p.silence_days)
        out.append("  Longest silence: %s, %d days and counting."
                   % (longest.name, longest.silence_days))
        out.append("  They are survived by your current project."
                   " It is not haunted. Probably.")
    else:
        out.append("  No bodies. Either you finish everything you start,"
                   " or you have not shown me the right folder.")
    out.append("")
    return "\n".join(out)


def _sections(cem):
    """The cemetery, sectioned: the buried and the resting, counted
    by the era they died in and the language they were written in."""
    by_era, by_language = {}, {}
    for p in cem.deceased + cem.resting:
        era = "%ds" % (p.died.year // 10 * 10)
        by_era[era] = by_era.get(era, 0) + 1
        if p.language:
            by_language[p.language] = by_language.get(p.language, 0) + 1
    return {
        "by_era": dict(sorted(by_era.items())),
        "by_language": dict(sorted(by_language.items())),
    }


# ---------------------------------------------------------------------------
# Rendering: JSON
# ---------------------------------------------------------------------------


def cemetery_dict(cem):
    def pd(p):
        return {
            "name": p.name,
            "path": p.path,
            "born": p.born.isoformat(),
            "died": p.died.isoformat(),
            "lifespan_days": p.lifespan_days,
            "commits": p.commits,
            "first_words": p.first_words,
            "last_words": p.last_words,
            "authors": p.authors,
            "has_readme": p.has_readme,
            "has_remote": p.has_remote,
            "silence_days": p.silence_days,
            "resurrections": p.resurrections,
            "longest_flatline_days": p.longest_flatline,
            "status": p.status,
            "will_status": p.will_status or None,
            "will_successor": p.will_successor or None,
            "will_note": p.will_note or None,
            "cause_of_death": p.cause or None,
            "contributing_factors": p.factors,
            "survived_by": p.survived_by or None,
            "eulogy": compose_eulogy(p) if p.status == "deceased" else None,
            "autopsy": autopsy(p) if p.status in ("deceased", "resting")
                       else None,
            "activity_monthly": p.activity,
            "language": p.language or None,
            "dependency_commits": p.dep_commits,
            "dependency_tail_share": round(p.dep_tail_share, 2),
        }
    return {
        "tool": "dead-projects-society",
        "version": VERSION,
        "grounds": cem.root,
        "dead_after_days": cem.dead_days,
        "summary": {
            "buried": len(cem.deceased),
            "coma": len(cem.coma),
            "alive": len(cem.alive),
            "at_rest": len(cem.resting),
            "buried_commits": cem.buried_commits,
            "average_lifespan_days": round(cem.avg_lifespan, 1),
            "back_from_the_dead": sum(
                1 for p in cem.projects if p.resurrections >= 1),
            "sections": _sections(cem),
        },
        "honors": [
            {"title": h["title"], "project": h["project"].name,
             "detail": h["detail"]}
            for h in society_honors(cem)
        ],
        "infamy": [
            {"title": h["title"], "project": h["project"].name,
             "detail": h["detail"]}
            for h in hall_of_infamy(cem)
        ],
        "projects": [pd(p) for p in cem.projects],
    }


# ---------------------------------------------------------------------------
# Rendering: Markdown obituaries
# ---------------------------------------------------------------------------


def render_markdown(cem):
    out = ["# Dead Projects Society", ""]
    out.append("Grounds: `%s`" % cem.root)
    out.append("")
    counts = ("**Buried: %d** · In a coma: %d · Still breathing: %d"
              % (len(cem.deceased), len(cem.coma), len(cem.alive)))
    if cem.resting:
        counts += " · At rest: %d" % len(cem.resting)
    counts += " · Commits buried: %d" % cem.buried_commits
    out.append(counts)
    out.append("")
    for p in cem.deceased:
        out.append("## R.I.P. %s" % p.name)
        out.append("")
        out.append("%s to %s · aged %s · %d commits"
                   % (_fmt_date(p.born), _fmt_date(p.died),
                      _lifespan_text(p), p.commits))
        out.append("")
        out.append('> Last words: "%s"' % (p.last_words or "(silence)"))
        out.append("")
        out.append("**Cause of death:** %s" % p.cause)
        out.append("")
        out.append("*%s*" % compose_eulogy(p))
        out.append("")
        if p.resurrections >= 1:
            out.append("It had already flatlined for %d days once and come "
                       "back. This time it did not." % p.longest_flatline)
            out.append("")
        for f in p.factors:
            out.append("- Contributing: %s" % f)
        out.append("- %s" % p.survived_by)
        out.append("")
    for p in cem.resting:
        out.append("## At Rest: %s" % p.name)
        out.append("")
        out.append("%s to %s · aged %s · %d commits"
                   % (_fmt_date(p.born), _fmt_date(p.died),
                      _lifespan_text(p), p.commits))
        out.append("")
        out.append('> Last words: "%s"' % (p.last_words or "(silence)"))
        out.append("")
        out.append("**%s**" % p.cause)
        out.append("")
        if p.will_note:
            out.append("From its will: %s" % p.will_note)
            out.append("")
        out.append("- %s" % p.survived_by)
        out.append("")
    honors = society_honors(cem)
    if honors:
        out.append("## The Society's Honors")
        out.append("")
        for h in honors:
            out.append("- **%s:** %s. %s"
                       % (h["title"], h["project"].name, h["detail"]))
        out.append("")
    infamy = hall_of_infamy(cem)
    if infamy:
        out.append("## Hall of Infamy")
        out.append("")
        for h in infamy:
            out.append("- **%s:** %s. %s"
                       % (h["title"], h["project"].name, h["detail"]))
        out.append("")
    if cem.coma:
        out.append("## Intensive care")
        out.append("")
        for p in cem.coma:
            out.append("- %s: last seen %s (%d days ago)"
                       % (p.name, _fmt_date(p.died), p.silence_days))
        out.append("")
    if cem.alive:
        out.append("## Still breathing")
        out.append("")
        for p in cem.alive:
            out.append("- %s: active %d days ago" % (p.name, p.silence_days))
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Rendering: HTML graveyard
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dead Projects Society</title>
<style>
  body {{ background:#101418; color:#cfd6dd; font-family:Georgia, serif;
         margin:0; padding:2rem 1rem 4rem; }}
  .wrap {{ max-width:880px; margin:0 auto; }}
  h1 {{ text-align:center; font-weight:normal; letter-spacing:.12em;
       color:#e8edf1; margin-bottom:.2rem; }}
  .sub {{ text-align:center; color:#8b96a0; font-style:italic;
         margin-bottom:2rem; }}
  .stats {{ text-align:center; color:#aeb8c0; margin-bottom:2.5rem;
           font-size:1.05rem; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,
          minmax(250px, 1fr)); gap:1.2rem; }}
  .stone {{ background:linear-gradient(180deg,#232a31,#1a2027);
           border:1px solid #333d46; border-radius:120px 120px 10px 10px;
           padding:2.2rem 1.2rem 1.2rem; text-align:center;
           box-shadow:0 4px 14px rgba(0,0,0,.45); }}
  .stone h2 {{ margin:.2rem 0 .4rem; font-size:1.15rem; color:#eef2f5;
              word-break:break-word; }}
  .rip {{ color:#7f8b96; letter-spacing:.3em; font-size:.8rem; }}
  .dates {{ color:#9aa6b1; font-size:.92rem; }}
  .words {{ font-style:italic; color:#c3ccd4; margin:.7rem 0 .3rem; }}
  .cause {{ color:#b08d57; font-size:.95rem; }}
  .eulogy {{ font-style:italic; color:#aeb9c2; margin-top:.55rem;
            font-size:.92rem; }}
  .risen {{ color:#d8c58f; font-size:.85rem; margin-top:.35rem; }}
  .factor, .survived {{ color:#77828d; font-size:.85rem; margin-top:.35rem; }}
  h3.section {{ color:#e8edf1; letter-spacing:.08em; margin:2.5rem 0 1rem;
               text-align:center; font-weight:normal; }}
  .living {{ text-align:center; color:#9aa6b1; line-height:1.7; }}
  footer {{ text-align:center; color:#5f6a74; margin-top:3rem;
           font-size:.85rem; }}
</style></head><body><div class="wrap">
<h1>DEAD PROJECTS SOCIETY</h1>
<div class="sub">est. the day you ran this command</div>
<div class="stats">Buried: {buried} &middot; In a coma: {coma} &middot;
Still breathing: {alive} &middot; At rest: {resting} &middot;
Commits buried: {commits}</div>
<div class="grid">
{stones}
</div>
{extra}
<footer>Judged locally from git history alone. No code was read, nothing
left this machine. The Society does not bury the living.</footer>
</div></body></html>
"""


def render_html(cem):
    def esc(s):
        return xml_escape(str(s), {'"': "&quot;"})

    stones = []
    for p in cem.deceased:
        factors = "".join(
            '<div class="factor">%s</div>' % esc(f) for f in p.factors)
        risen = ""
        if p.resurrections >= 1:
            risen = ('<div class="risen">It had already flatlined for %d '
                     "days once and come back. This time it did "
                     "not.</div>" % p.longest_flatline)
        stones.append(
            '<div class="stone"><div class="rip">R.I.P.</div>'
            "<h2>%s</h2>"
            '<div class="dates">%s &ndash; %s<br>aged %s &middot; %d commits'
            "</div>"
            '<div class="words">&ldquo;%s&rdquo;</div>'
            '<div class="cause">%s</div>'
            '<div class="eulogy">%s</div>%s%s'
            '<div class="survived">%s</div></div>'
            % (esc(p.name), _fmt_date(p.born), _fmt_date(p.died),
               _lifespan_text(p), p.commits,
               esc(p.last_words or "(silence)"), esc(p.cause),
               esc(compose_eulogy(p)), risen, factors,
               esc(p.survived_by)))
    extra = []
    honors = society_honors(cem)
    if honors:
        rows = "<br>".join(
            "%s: %s. %s" % (esc(h["title"]), esc(h["project"].name),
                            esc(h["detail"]))
            for h in honors)
        extra.append('<h3 class="section">THE SOCIETY&rsquo;S HONORS</h3>'
                     '<div class="living">%s</div>' % rows)
    if cem.resting:
        rows = "<br>".join(
            "%s &mdash; %s" % (esc(p.name), esc(p.cause))
            for p in cem.resting)
        extra.append('<h3 class="section">AT REST: FINISHED, NOT DEAD</h3>'
                     '<div class="living">%s</div>' % rows)
    infamy = hall_of_infamy(cem)
    if infamy:
        rows = "<br>".join(
            "%s: %s. %s" % (esc(h["title"]), esc(h["project"].name),
                            esc(h["detail"]))
            for h in infamy)
        extra.append('<h3 class="section">HALL OF INFAMY</h3>'
                     '<div class="living">%s</div>' % rows)
    if cem.coma:
        rows = "<br>".join(
            "%s &mdash; last seen %s (%d days ago)"
            % (esc(p.name), _fmt_date(p.died), p.silence_days)
            for p in cem.coma)
        extra.append('<h3 class="section">INTENSIVE CARE</h3>'
                     '<div class="living">%s</div>' % rows)
    if cem.alive:
        rows = "<br>".join(
            "%s &mdash; active %d days ago" % (esc(p.name), p.silence_days)
            for p in cem.alive)
        extra.append('<h3 class="section">STILL BREATHING</h3>'
                     '<div class="living">%s</div>' % rows)
    return _HTML.format(
        buried=len(cem.deceased), coma=len(cem.coma), alive=len(cem.alive),
        resting=len(cem.resting),
        commits=cem.buried_commits, stones="\n".join(stones),
        extra="\n".join(extra))


# ---------------------------------------------------------------------------
# Rendering: certificates
# ---------------------------------------------------------------------------

_CERT = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{kind_title} — {name}</title>
<style>
  body {{ background:#0d0f12; margin:0; padding:2.5rem 1rem;
         font-family:Georgia, serif; color:#d8d2c2; }}
  .cert {{ max-width:760px; margin:0 auto; border:3px double #b08d57;
          padding:3rem 3rem 2.4rem; text-align:center;
          background:linear-gradient(180deg,#14171c,#101216); }}
  .society {{ letter-spacing:.35em; color:#8b96a0; font-size:.8rem; }}
  h1 {{ font-weight:normal; letter-spacing:.14em; color:#e8e2d2;
       margin:.8rem 0 .2rem; }}
  .rule {{ color:#b08d57; margin:.6rem 0 1.4rem; }}
  .name {{ font-size:1.9rem; color:#f0ead8; margin:.4rem 0; }}
  .dates {{ color:#aeb6ae; }}
  .field {{ margin:1.05rem auto; max-width:560px; line-height:1.55; }}
  .label {{ display:block; letter-spacing:.25em; font-size:.68rem;
           color:#8b96a0; margin-bottom:.25rem; }}
  .seal {{ margin:1.8rem auto .4rem; width:74px; height:74px;
          border:2px solid #b08d57; border-radius:50%; color:#b08d57;
          line-height:74px; font-size:1.7rem; }}
  .issued {{ color:#77828d; font-size:.85rem; margin-top:1.2rem; }}
</style></head><body>
<div class="cert">
  <div class="society">DEAD PROJECTS SOCIETY</div>
  <h1>{kind_title}</h1>
  <div class="rule">✦ ✦ ✦</div>
  <div class="field"><span class="label">THIS CERTIFIES THE RECORD OF</span>
  <div class="name">{name}</div>
  <div class="dates">{born} &mdash; {died} &middot; aged {lifespan}
  &middot; {commits} commits &middot; {authors}</div></div>
  <div class="field"><span class="label">{cause_label}</span>{cause}</div>
  <div class="field"><span class="label">LAST WORDS</span>
  &ldquo;{last_words}&rdquo;</div>
  {will_block}
  <div class="field"><span class="label">SURVIVED BY</span>{survived_by}</div>
  <div class="seal">✦</div>
  <div class="issued">Issued {issued} &middot; Grounds: {grounds}<br>
  Judged locally from git history alone. No code was read.</div>
</div>
</body></html>
"""


def render_certificate(p, cem):
    def esc(s):
        return xml_escape(str(s), {'"': "&quot;"})

    resting = p.status == "resting"
    will_block = ""
    if p.will_note:
        will_block = ('<div class="field"><span class="label">FROM ITS '
                      'WILL</span>%s</div>' % esc(p.will_note))
    return _CERT.format(
        kind_title="CERTIFICATE OF COMPLETION" if resting
                   else "CERTIFICATE OF DEATH",
        name=esc(p.name),
        born=_fmt_date(p.born),
        died=_fmt_date(p.died),
        lifespan=_lifespan_text(p),
        commits=p.commits,
        authors="sole author" if p.authors == 1
                else "%d authors" % p.authors,
        cause_label="THE RECORD" if resting else "CAUSE OF DEATH",
        cause=esc(p.cause),
        last_words=esc(p.last_words or "(silence)"),
        will_block=will_block,
        survived_by=esc(p.survived_by),
        issued=_fmt_date(cem.generated),
        grounds=esc(cem.root),
    )


_RESURRECTION_CERT = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>CERTIFICATE OF RESURRECTION \u2014 {name}</title>
<style>
  body {{ background:#0c100c; margin:0; padding:2.5rem 1rem;
         font-family:Georgia, serif; color:#d5ddc9; }}
  .cert {{ max-width:760px; margin:0 auto; border:3px double #8fae6b;
          padding:3rem 3rem 2.4rem; text-align:center;
          background:linear-gradient(180deg,#141a13,#0f130e); }}
  .society {{ letter-spacing:.35em; color:#93a189; font-size:.8rem; }}
  h1 {{ font-weight:normal; letter-spacing:.14em; color:#eef3df;
       margin:.8rem 0 .2rem; }}
  .rule {{ color:#8fae6b; margin:.6rem 0 1.4rem; }}
  .name {{ font-size:1.9rem; color:#f4f8e8; margin:.4rem 0; }}
  .dates {{ color:#b3bfa5; }}
  .field {{ margin:1.05rem auto; max-width:560px; line-height:1.55; }}
  .label {{ display:block; letter-spacing:.25em; font-size:.68rem;
           color:#93a189; margin-bottom:.25rem; }}
  .seal {{ margin:1.8rem auto .4rem; width:74px; height:74px;
          border:2px solid #8fae6b; border-radius:50%; color:#8fae6b;
          line-height:74px; font-size:1.7rem; }}
  .issued {{ color:#77816e; font-size:.85rem; margin-top:1.2rem; }}
</style></head><body>
<div class="cert">
  <div class="society">DEAD PROJECTS SOCIETY</div>
  <h1>CERTIFICATE OF RESURRECTION</h1>
  <div class="rule">\u2726 \u2726 \u2726</div>
  <div class="field"><span class="label">THIS CERTIFIES THAT</span>
  <div class="name">{name}</div>
  <div class="dates">{born} &mdash; {died} &middot; {commits} commits</div></div>
  <div class="field"><span class="label">THE RETURN</span>{return_line}</div>
  <div class="field"><span class="label">PRESENT CONDITION</span>{condition}</div>
  <div class="seal">\u2726</div>
  <div class="issued">Issued {issued} &middot; Grounds: {grounds}<br>
  Judged locally from git history alone. No code was read.</div>
</div>
</body></html>
"""


def render_resurrection_certificate(p, cem):
    def esc(s):
        return xml_escape(str(s), {'"': "&quot;"})

    times = ("once" if p.resurrections == 1
             else "%d times" % p.resurrections)
    return_line = ("It flatlined for %d days, past every line the "
                   "Society draws, and then it committed again. "
                   "It has risen %s."
                   % (p.longest_flatline, times))
    if p.status in ("alive", "coma"):
        condition = ("Currently among the living. Last seen %d days "
                     "ago. The grave dug for it stands empty, and "
                     "the Society keeps the stone, just in case."
                     % p.silence_days)
    elif p.status == "resting":
        condition = ("It rose, finished its work, and rests on its "
                     "own terms. The Society does not begrudge it.")
    else:
        condition = ("It rose, and then it fell again. It rests once "
                     "more, but the return is on the record, and the "
                     "record stands.")
    return _RESURRECTION_CERT.format(
        name=esc(p.name),
        born=_fmt_date(p.born),
        died=_fmt_date(p.died),
        commits=p.commits,
        return_line=esc(return_line),
        condition=esc(condition),
        issued=_fmt_date(cem.generated),
        grounds=esc(cem.root),
    )


# ---------------------------------------------------------------------------
# Rendering: SVG share card
# ---------------------------------------------------------------------------


def render_card(cem):
    def esc(s):
        return xml_escape(str(s), {'"': "&quot;"})

    lines = []
    lines.append("My side projects, formally buried.")
    if cem.deceased:
        worst = max(cem.deceased, key=lambda p: p.silence_days)
        lines.append("Longest silence: %s, %d days."
                     % (worst.name, worst.silence_days))
    risen = [p for p in cem.projects if p.resurrections >= 1]
    if risen:
        p = max(risen, key=lambda x: x.longest_flatline)
        lines.append("Back from the dead: %s, after %d days."
                     % (p.name, p.longest_flatline))
    elif cem.deceased:
        marathoner = max(cem.deceased, key=lambda p: p.lifespan_days)
        lines.append("The Marathoner: %s, %s."
                     % (marathoner.name,
                        _site_life_text(marathoner.lifespan_days)))
    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" '
        'viewBox="0 0 1200 630">')
    parts.append('<rect width="1200" height="630" fill="#101418"/>')
    parts.append('<rect x="24" y="24" width="1152" height="582" rx="18" '
                 'fill="none" stroke="#333d46" stroke-width="2"/>')
    parts.append('<text x="600" y="120" text-anchor="middle" '
                 'font-family="Georgia, serif" font-size="30" fill="#7f8b96" '
                 'letter-spacing="8">DEAD PROJECTS SOCIETY</text>')
    stats = [
        ("BURIED", str(len(cem.deceased))),
        ("COMMITS BURIED", str(cem.buried_commits)),
        ("IN A COMA", str(len(cem.coma))),
        ("STILL BREATHING", str(len(cem.alive))),
    ]
    if cem.resting:
        stats.append(("AT REST", str(len(cem.resting))))
    x = 600 - (len(stats) - 1) * 140
    for i, (label, val) in enumerate(stats):
        cx = x + i * 280
        parts.append('<text x="%d" y="290" text-anchor="middle" '
                     'font-family="Georgia, serif" font-size="84" '
                     'fill="#eef2f5">%s</text>' % (cx, esc(val)))
        parts.append('<text x="%d" y="335" text-anchor="middle" '
                     'font-family="Georgia, serif" font-size="22" '
                     'fill="#8b96a0" letter-spacing="3">%s</text>'
                     % (cx, esc(label)))
    y = 430
    for line in lines:
        parts.append('<text x="600" y="%d" text-anchor="middle" '
                     'font-family="Georgia, serif" font-style="italic" '
                     'font-size="30" fill="#c3ccd4">%s</text>'
                     % (y, esc(line)))
        y += 48
    parts.append('<text x="600" y="565" text-anchor="middle" '
                 'font-family="Georgia, serif" font-size="20" '
                 'fill="#5f6a74">They are survived by my current project.'
                 "</text>")
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Web graveyard export: projects.json + wards.json for the 3D site
# ---------------------------------------------------------------------------


def _site_slug(name):
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")


def _site_cause_tag(cause):
    if not cause:
        return "Cause unknown"
    tag = cause.split(".")[0].strip()
    return tag[:1].upper() + tag[1:]


def _site_life_text(life):
    if life == 1:
        return "1 day"
    if life < 60:
        return "%d days" % life
    if life < 730:
        return "%d months" % round(life / 30.44)
    return "%.1f years" % (life / 365.25)


def _site_github_url(path):
    url = _git(path, "remote", "get-url", "origin")
    if not url:
        return None
    url = url.strip()
    m = re.match(r"git@github\.com:(.+?)(?:\.git)?$", url)
    if m:
        return "https://github.com/" + m.group(1)
    if url.startswith("https://github.com/"):
        return url[:-4] if url.endswith(".git") else url
    return None


def site_projects(cem):
    stones = []
    for p in cem.deceased:
        desc = "%d commits over %s. %s" % (
            p.commits, _site_life_text(p.lifespan_days), p.cause or "")
        for f in p.factors:
            desc += " " + f
        if p.survived_by:
            desc += " " + p.survived_by
        desc += " " + compose_eulogy(p)
        stone = {
            "id": _site_slug(p.name),
            "name": p.name,
            "born": p.born.strftime("%Y"),
            "died": p.died.strftime("%Y"),
            "cause": _site_cause_tag(p.cause),
            "epitaph": p.last_words or "",
            "description": desc,
            "tech": [p.language] if p.language else [],
            "commits": p.commits,
            "died_full": p.died.date().isoformat(),
            "born_full": p.born.date().isoformat(),
            "silence_days": p.silence_days,
            "resurrections": p.resurrections,
            "longest_flatline_days": p.longest_flatline,
            "activity": p.activity,
        }
        _a = autopsy(p)
        stone["autopsy"] = {
            "momentum": _a["momentum"],
            "findings": _a["findings"],
            "revival_verdict": _a["revival_verdict"],
            "peak_month": _a["peak_month"],
            "peak_commits": _a["peak_commits"],
            "peak_share_percent": _a["peak_share_percent"],
        }
        url = _site_github_url(p.path)
        if url:
            stone["url"] = url
        stones.append(stone)
    return stones


def site_honors(cem):
    return [
        {
            "title": h["title"],
            "project_id": _site_slug(h["project"].name),
            "project_name": h["project"].name,
            "detail": h["detail"],
        }
        for h in society_honors(cem)
    ]


def site_infamy(cem):
    return [
        {
            "title": h["title"],
            "project_id": _site_slug(h["project"].name),
            "project_name": h["project"].name,
            "detail": h["detail"],
        }
        for h in hall_of_infamy(cem)
    ]


def _patient_description(p):
    if p.status == "coma":
        desc = ("The Society does not bury the living. %d commits; "
                "last seen %d days ago." % (p.commits, p.silence_days))
    else:
        desc = ("Still active, %d days ago. %d commits and counting. "
                "Nothing to pronounce." % (p.silence_days, p.commits))
    if p.resurrections >= 1:
        desc += (" It has flatlined before, %d days at the longest, "
                 "and come back." % p.longest_flatline)
    return desc


def site_wards(cem):
    def entry(p):
        e = {
            "id": _site_slug(p.name),
            "name": p.name,
            "born": p.born.strftime("%Y"),
            "died": p.died.strftime("%Y"),
            "epitaph": p.last_words or "",
            "description": _patient_description(p),
            "tech": [p.language] if p.language else [],
            "silence_days": p.silence_days,
            "commits": p.commits,
            "resurrections": p.resurrections,
            "longest_flatline_days": p.longest_flatline,
            "activity": p.activity,
            "born_full": p.born.date().isoformat(),
            "died_full": p.died.date().isoformat(),
        }
        url = _site_github_url(p.path)
        if url:
            e["url"] = url
        return e
    return {
        "intensive_care": [entry(p) for p in cem.coma],
        "still_breathing": [entry(p) for p in cem.alive],
    }


def render_square_card(cem):
    """The 1080x1080 card, sized for social feeds (research, Nov 2026:
    square cards are the shareable unit there; the wide card stays
    the link-preview size)."""
    def esc(s):
        return xml_escape(str(s), {'"': "&quot;"})

    counts = "%d buried \u00b7 %d in a coma \u00b7 %d breathing" % (
        len(cem.deceased), len(cem.coma), len(cem.alive))
    if cem.resting:
        counts += " \u00b7 %d at rest" % len(cem.resting)
    lines = []
    if cem.deceased:
        worst = max(cem.deceased, key=lambda p: p.silence_days)
        lines.append("Longest silence: %s, %d days."
                     % (worst.name, worst.silence_days))
    risen = [p for p in cem.projects if p.resurrections >= 1]
    if risen:
        p = max(risen, key=lambda x: x.longest_flatline)
        lines.append("Back from the dead: %s, after %d days."
                     % (p.name, p.longest_flatline))
    elif cem.deceased:
        marathoner = max(cem.deceased, key=lambda p: p.lifespan_days)
        lines.append("The Marathoner: %s, %s."
                     % (marathoner.name,
                        _site_life_text(marathoner.lifespan_days)))
    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1080" '
        'height="1080" viewBox="0 0 1080 1080">')
    parts.append('<rect width="1080" height="1080" fill="#101418"/>')
    parts.append('<rect x="30" y="30" width="1020" height="1020" rx="20" '
                 'fill="none" stroke="#333d46" stroke-width="2"/>')
    parts.append('<rect x="44" y="44" width="992" height="992" rx="14" '
                 'fill="none" stroke="#232a31" stroke-width="1"/>')
    parts.append(
        '<text x="540" y="215" text-anchor="middle" font-family="Georgia, '
        'serif" font-size="44" letter-spacing="10" fill="#8b96a0">'
        'DEAD PROJECTS SOCIETY</text>')
    parts.append(
        '<text x="540" y="300" text-anchor="middle" font-family="Georgia, '
        'serif" font-size="31" fill="#c9cfc4">My side projects, '
        'formally buried.</text>')
    parts.append(
        '<text x="540" y="520" text-anchor="middle" font-family="Georgia, '
        'serif" font-size="230" fill="#e8e2d2">%d</text>'
        % len(cem.deceased))
    parts.append(
        '<text x="540" y="590" text-anchor="middle" font-family="Georgia, '
        'serif" font-size="34" letter-spacing="6" fill="#b08d57">'
        'BURIED</text>')
    parts.append(
        '<text x="540" y="680" text-anchor="middle" font-family="Georgia, '
        'serif" font-size="30" fill="#aeb6ae">%s</text>' % esc(counts))
    y = 770
    for line in lines:
        parts.append(
            '<text x="540" y="%d" text-anchor="middle" '
            'font-family="Georgia, serif" font-size="30" '
            'fill="#c9cfc4">%s</text>' % (y, esc(line)))
        y += 52
    parts.append(
        '<text x="540" y="985" text-anchor="middle" font-family="Georgia, '
        'serif" font-size="24" fill="#77828d">Judged locally from git '
        'metadata. Your code is never read.</text>')
    parts.append('</svg>')
    return "".join(parts)


def render_badge(cem):
    """A shields-style badge for a README: the state of the grounds."""
    def esc(s):
        return xml_escape(str(s), {'"': "&quot;"})

    label = "dead projects society"
    msg = "%d buried \u00b7 %d in a coma \u00b7 %d breathing" % (
        len(cem.deceased), len(cem.coma), len(cem.alive))
    if cem.resting:
        msg += " \u00b7 %d at rest" % len(cem.resting)
    color = "#4c1" if not cem.deceased else "#b08d57"
    lw = int(38 + len(label) * 6.5)
    mw = int(12 + len(msg) * 6.5)
    w = lw + mw
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="20" '
        'role="img" aria-label="%s: %s">'
        "<title>%s: %s</title>"
        '<rect width="%d" height="20" rx="3" fill="#555"/>'
        '<rect x="%d" width="%d" height="20" rx="3" fill="%s"/>'
        '<rect x="%d" width="4" height="20" fill="%s"/>'
        '<text x="%d" y="14" text-anchor="middle" '
        'font-family="Verdana, sans-serif" font-size="11" fill="#fff">%s'
        "</text>"
        '<text x="%d" y="14" text-anchor="middle" '
        'font-family="Verdana, sans-serif" font-size="11" fill="#fff">%s'
        "</text></svg>"
        % (w, esc(label), esc(msg), esc(label), esc(msg), w, lw, mw,
           color, lw, color, lw // 2, esc(label), lw + mw // 2, esc(msg)))


_WRAPPED = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dead Projects Society — {year} in the Grounds</title>
<style>
  body {{ background:#101418; color:#cfd6dd; font-family:Georgia, serif;
         margin:0; padding:2.5rem 1rem 4rem; text-align:center; }}
  .wrap {{ max-width:820px; margin:0 auto; }}
  h1 {{ font-weight:normal; letter-spacing:.12em; color:#e8edf1; }}
  .sub {{ color:#8b96a0; font-style:italic; margin-bottom:2.2rem; }}
  .big {{ display:flex; flex-wrap:wrap; gap:1rem; justify-content:center;
         margin-bottom:2.4rem; }}
  .stat {{ background:#171d24; border:1px solid #333d46; border-radius:10px;
          padding:1.1rem 1.4rem; min-width:130px; }}
  .stat .n {{ font-size:2.1rem; color:#eef2f5; }}
  .stat .l {{ color:#8b96a0; font-size:.8rem; letter-spacing:.18em; }}
  .stone {{ background:#171d24; border:1px solid #333d46; border-radius:10px;
           padding:1rem 1.2rem; margin:.7rem auto; max-width:560px;
           text-align:left; }}
  .stone b {{ color:#eef2f5; }}
  .cause {{ color:#b08d57; }}
  .words {{ font-style:italic; color:#c3ccd4; }}
  footer {{ color:#5f6a74; margin-top:2.6rem; font-size:.85rem; }}
</style></head><body><div class="wrap">
<h1>{year} IN THE GROUNDS</h1>
<div class="sub">Dead Projects Society &middot; the year, formally buried</div>
<div class="big">
  <div class="stat"><div class="n">{buried}</div>
  <div class="l">BURIED</div></div>
  <div class="stat"><div class="n">{commits}</div>
  <div class="l">COMMITS BURIED</div></div>
  <div class="stat"><div class="n">{resting}</div>
  <div class="l">FINISHED, AT REST</div></div>
  <div class="stat"><div class="n">{risen}</div>
  <div class="l">BACK FROM THE DEAD</div></div>
</div>
{stones}
<footer>Judged locally from git history alone. No code was read.</footer>
</div></body></html>
"""


def _year_cemetery(cem, year):
    """The year's dead: projects whose story ended in YEAR."""
    ended = [p for p in cem.projects
             if p.status in ("deceased", "resting")
             and p.died.year == year]
    return Cemetery(root=cem.root, generated=cem.generated,
                    dead_days=cem.dead_days, projects=ended)


def render_wrapped(cem, year):
    def esc(s):
        return xml_escape(str(s), {'"': "&quot;"})

    yc = _year_cemetery(cem, year)
    stones = []
    for p in sorted(yc.projects, key=lambda x: x.died):
        stones.append(
            '<div class="stone"><b>%s</b> &middot; %s<br>'
            '<span class="cause">%s</span><br>'
            '<span class="words">&ldquo;%s&rdquo;</span></div>'
            % (esc(p.name), _lifespan_text(p), esc(p.cause),
               esc(p.last_words or "(silence)")))
    if not stones:
        stones.append('<div class="stone">Nothing of yours ended in %d. '
                      "The Society notes it, with suspicion.</div>" % year)
    return _WRAPPED.format(
        year=year,
        buried=len(yc.deceased),
        commits=sum(p.commits for p in yc.projects),
        resting=len(yc.resting),
        risen=sum(1 for p in yc.projects if p.resurrections >= 1),
        stones="\n".join(stones))


def wrapped_text(cem, year):
    yc = _year_cemetery(cem, year)
    lines = [
        "My %d, formally buried by the Dead Projects Society:" % year,
        "%d buried, %d commits interred, %d finished and at rest."
        % (len(yc.deceased),
           sum(p.commits for p in yc.projects), len(yc.resting)),
    ]
    for p in sorted(yc.projects, key=lambda x: x.died):
        lines.append("%s: %s" % (p.name, p.cause.split(".")[0] + "."))
    lines.append("Bury yours: https://github.com/littlestjames82-sys/"
                 "dead-projects-society")
    return "\n".join(lines) + "\n"


def _snapshot(cem):
    return {
        p.name: {
            "status": p.status,
            "died": p.died.date().isoformat(),
            "commits": p.commits,
        }
        for p in cem.projects
    }


def groundskeeper_log(prev, cem):
    """What changed in the grounds since the last recorded visit.

    prev is the snapshot dict from the previous --diff run for this
    root, or None on the first visit.
    """
    cur = _snapshot(cem)
    if prev is None:
        return {"first_visit": True, "newly_buried": [],
                "newly_resting": [], "risen": [], "stirred": [],
                "newly_born": sorted(cur), "still_buried": 0}
    newly_buried, newly_resting, risen, stirred, newly_born = [], [], [], [], []
    still_buried = 0
    for name, now_s in cur.items():
        before = prev.get(name)
        if before is None:
            newly_born.append(name)
            continue
        was_dead = before.get("status") in ("deceased", "resting")
        is_dead = now_s["status"] in ("deceased", "resting")
        if is_dead and not was_dead:
            if now_s["status"] == "resting":
                newly_resting.append(name)
            else:
                newly_buried.append(name)
        elif was_dead and not is_dead:
            risen.append(name)
        elif was_dead and is_dead and now_s["died"] != before.get("died"):
            stirred.append(name)
        elif was_dead and is_dead:
            still_buried += 1
    return {"first_visit": False,
            "newly_buried": sorted(newly_buried),
            "newly_resting": sorted(newly_resting),
            "risen": sorted(risen),
            "stirred": sorted(stirred),
            "newly_born": sorted(newly_born),
            "still_buried": still_buried}


def render_groundskeeper_log(log):
    lines = ["-" * 64,
             "  THE GROUNDSKEEPER'S LOG (since your last visit)"]
    if log["first_visit"]:
        lines.append("  No previous visit on record. The log begins "
                     "today; %d projects entered into it."
                     % len(log["newly_born"]))
        return "\n".join(lines)
    rows = [("Newly buried", log["newly_buried"]),
            ("Finished, and at rest", log["newly_resting"]),
            ("Risen", log["risen"]),
            ("Stirred in their graves", log["stirred"]),
            ("Newly born", log["newly_born"])]
    if not any(names for _, names in rows):
        lines.append("  Nothing changed. The grounds are as you "
                     "left them.")
    for label, names in rows:
        if names:
            lines.append("  * %s: %s" % (label, ", ".join(names)))
    lines.append("  Still buried, undisturbed: %d."
                 % log["still_buried"])
    return "\n".join(lines)


def _load_state(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(path, state):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="dead-projects-society",
        description="A funeral for your abandoned side projects. Reads "
                    "git history locally and builds the graveyard.")
    ap.add_argument("path", nargs="*", default=None,
                    help="Folder(s) to scan (default: current folder). "
                         "Several folders are merged into one cemetery, "
                         "and succession is judged across all of them.")
    ap.add_argument("--days", type=int, default=DEFAULT_DEAD_DAYS,
                    help="Days of silence before a project is pronounced "
                         "dead (default: %d)" % DEFAULT_DEAD_DAYS)
    ap.add_argument("--depth", type=int, default=1,
                    help="How deep to look for repositories (default: 1)")
    ap.add_argument("--html", metavar="FILE",
                    help="Write a walkable HTML graveyard")
    ap.add_argument("--card", metavar="FILE",
                    help="Write an SVG share card")
    ap.add_argument("--square", metavar="FILE",
                    help="Write a 1080x1080 SVG card for social feeds")
    ap.add_argument("--badge", metavar="FILE",
                    help="Write an SVG status badge for a README")
    ap.add_argument("--wrapped-kit", metavar="DIR",
                    help="Write the year-in-review kit (HTML page, SVG "
                         "card, post text) into DIR")
    ap.add_argument("--year", type=int, default=None,
                    help="Year for the wrapped kit (default: this year)")
    ap.add_argument("--out", metavar="FILE",
                    help="Write Markdown obituaries")
    ap.add_argument("--json", action="store_true",
                    help="Print the full report as JSON")
    ap.add_argument("--site", metavar="DIR",
                    help="Write projects.json and wards.json for the 3D "
                         "web graveyard into DIR")
    ap.add_argument("--oneline", action="store_true",
                    help="Print one line per project (name, state, "
                         "silence, cause) instead of the full report")
    ap.add_argument("--adopt", metavar="FILE", default=None,
                    help="Write adoption papers (Markdown) for the "
                         "buried: one honest listing per project, "
                         "with a line for a new keeper to sign")
    ap.add_argument("--on-this-day", action="store_true",
                    help="Append anniversaries: projects that died or "
                         "were born on this month and day in earlier "
                         "years")
    ap.add_argument("--autopsy", action="store_true",
                    help="Append the Autopsy Department's findings "
                         "(metadata only) to the terminal report")
    ap.add_argument("--certificates", metavar="DIR",
                    help="Write a formal certificate (HTML) for every "
                         "buried or at-rest project into DIR")
    ap.add_argument("--diff", action="store_true",
                    help="Compare this scan with the last recorded "
                         "visit to these grounds and report what "
                         "changed (the Groundskeeper's Log); records "
                         "this visit either way")
    ap.add_argument("--state", metavar="FILE", default=None,
                    help="State file for --diff (default: "
                         "~/.dead-projects-society/state.json)")
    ap.add_argument("--version", action="version",
                    version="dead-projects-society %s" % VERSION)
    args = ap.parse_args(argv)

    roots = args.path or ["."]
    for root in roots:
        if not os.path.isdir(root):
            print("No such folder: %s" % root, file=sys.stderr)
            return 2
    cem = build_grounds(roots, dead_days=args.days, depth=args.depth)
    if not cem.projects:
        print("No bodies found. No git repositories under %s."
              % cem.root)
        return 2

    log = None
    if args.diff:
        state_path = args.state or os.path.join(
            os.path.expanduser("~"), ".dead-projects-society",
            "state.json")
        state = _load_state(state_path)
        entry = state.get(cem.root) or {}
        log = groundskeeper_log(entry.get("projects"), cem)
        state[cem.root] = {"visited": cem.generated.isoformat(),
                           "projects": _snapshot(cem)}
        _save_state(state_path, state)

    if args.json:
        data = cemetery_dict(cem)
        if log is not None:
            data["groundskeeper_log"] = log
        if args.on_this_day:
            data["on_this_day"] = on_this_day(cem)
        print(json.dumps(data, indent=2))
    elif args.oneline:
        print(render_oneline(cem), end="")
        if log is not None:
            print(render_groundskeeper_log(log))
    else:
        print(render_terminal(cem, with_autopsy=args.autopsy,
                              with_on_this_day=args.on_this_day))
        if log is not None:
            print(render_groundskeeper_log(log))
    if args.certificates:
        os.makedirs(args.certificates, exist_ok=True)
        subjects = cem.deceased + cem.resting
        for p in subjects:
            fname = "%s-certificate.html" % _site_slug(p.name)
            with open(os.path.join(args.certificates, fname), "w",
                      encoding="utf-8") as fh:
                fh.write(render_certificate(p, cem))
        risen = [p for p in cem.projects if p.resurrections >= 1]
        for p in risen:
            fname = "%s-resurrection-certificate.html" % _site_slug(p.name)
            with open(os.path.join(args.certificates, fname), "w",
                      encoding="utf-8") as fh:
                fh.write(render_resurrection_certificate(p, cem))
        print("Certificates written to %s (%d death or completion, "
              "%d resurrection)"
              % (args.certificates, len(subjects), len(risen)))
    if args.html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(render_html(cem))
        print("Graveyard written to %s" % args.html)
    if args.card:
        with open(args.card, "w", encoding="utf-8") as fh:
            fh.write(render_card(cem))
        print("Share card written to %s" % args.card)
    if args.square:
        with open(args.square, "w", encoding="utf-8") as fh:
            fh.write(render_square_card(cem))
        print("Square card written to %s" % args.square)
    if args.badge:
        with open(args.badge, "w", encoding="utf-8") as fh:
            fh.write(render_badge(cem))
        print("Badge written to %s" % args.badge)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(cem))
        print("Obituaries written to %s" % args.out)
    if args.adopt:
        with open(args.adopt, "w", encoding="utf-8") as fh:
            fh.write(render_adoption_papers(cem))
        print("Adoption papers: %s (%d projects listed)"
              % (args.adopt, len(cem.deceased)))
    if args.wrapped_kit:
        year = args.year or cem.generated.year
        os.makedirs(args.wrapped_kit, exist_ok=True)
        yc = _year_cemetery(cem, year)
        with open(os.path.join(args.wrapped_kit, "wrapped.html"), "w",
                  encoding="utf-8") as fh:
            fh.write(render_wrapped(cem, year))
        with open(os.path.join(args.wrapped_kit, "wrapped-card.svg"),
                  "w", encoding="utf-8") as fh:
            fh.write(render_card(yc))
        with open(os.path.join(args.wrapped_kit, "wrapped.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write(wrapped_text(cem, year))
        print("Wrapped kit for %d written to %s" % (year, args.wrapped_kit))
    if args.site:
        os.makedirs(args.site, exist_ok=True)
        with open(os.path.join(args.site, "projects.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(site_projects(cem), fh, indent=2)
            fh.write("\n")
        with open(os.path.join(args.site, "wards.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(site_wards(cem), fh, indent=2)
            fh.write("\n")
        with open(os.path.join(args.site, "honors.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(site_honors(cem), fh, indent=2)
            fh.write("\n")
        with open(os.path.join(args.site, "infamy.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(site_infamy(cem), fh, indent=2)
            fh.write("\n")
        print("Web graveyard data written to %s" % args.site)
    return 0


if __name__ == "__main__":
    sys.exit(main())
