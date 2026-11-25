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
import textwrap
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape as xml_escape

VERSION = "0.29.0"

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
    gap_events: list = field(default_factory=list)
    # (gap_days, datetime the silence ended) for each recorded gap
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


def find_repos(root, depth=1, exclude=()):
    """Yield repo paths: root itself, plus subdirectories up to depth.

    Directories named in exclude are never entered: the Society
    does not dig where it is told not to dig.
    """
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
                if name.startswith(".") or name in exclude:
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
    gap_events = []
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
                gap_events.append((gap, prev))
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
        gap_events=gap_events,
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
                  now=None, exclude=()):
    """One cemetery over several folders. Projects are merged,
    duplicates (the same repo reached through two roots) are kept
    once, and succession is judged across the whole union: the
    Society has always suspected the replacement was started in a
    different folder."""
    now = now or datetime.now(timezone.utc)
    if len(roots) == 1:
        return build_cemetery(roots[0], dead_days=dead_days,
                              depth=depth, now=now, exclude=exclude)
    seen = {}
    for root in roots:
        part = build_cemetery(root, dead_days=dead_days, depth=depth,
                              now=now, exclude=exclude)
        for p in part.projects:
            seen[os.path.abspath(p.path)] = p
    projects = sorted(seen.values(), key=lambda p: p.born)
    assign_succession(projects)
    label = "%d grounds (%s)" % (
        len(roots), ", ".join(os.path.abspath(r) for r in roots))
    return Cemetery(root=label, generated=now, dead_days=dead_days,
                    projects=projects)


def build_cemetery(root, dead_days=DEFAULT_DEAD_DAYS, depth=1, now=None,
                   exclude=()):
    now = now or datetime.now(timezone.utc)
    cem = Cemetery(root=os.path.abspath(root), generated=now,
                   dead_days=dead_days)
    for path in find_repos(root, depth=depth, exclude=exclude):
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


# ---------------------------------------------------------------------------
# The House Awards: a ceremony for these grounds alone (v0.29.0)
# ---------------------------------------------------------------------------

_REVIVAL_RANK = {"Worth exhuming.": 2, "Long odds, but not none.": 1}


def _award_pick(candidates, metric, highest=True):
    """The deterministic winner: the best metric takes it, and a
    tie is broken by name, so the same grounds hold the same
    ceremony on every visit."""
    if not candidates:
        return None
    if highest:
        return sorted(candidates,
                      key=lambda p: (-metric(p), p.name))[0]
    return sorted(candidates, key=lambda p: (metric(p), p.name))[0]


def house_awards(cem):
    """The House Awards: one honour per category, and only where
    the record genuinely supports one. The Obituary Awards on the
    site are for the famous dead; this ceremony is for the grounds
    in front of the Society, judged from the same record as
    everything else here. A category with no qualifying project is
    omitted. The Society does not pad a programme."""
    awards = []
    dead = cem.deceased
    if dead:
        p = _award_pick(dead, lambda x: x.lifespan_days)
        awards.append({
            "award": "Longest Life",
            "project": p,
            "citation": "Lived %s, from %s to %s, across %d commits. "
                        "No one in these grounds had more life, and "
                        "the Society honours the whole of it."
                        % (_lifespan_text(p), _fmt_date(p.born),
                           _fmt_date(p.died), p.commits),
        })
        brief = [p for p in dead if p.lifespan_days >= 1]
        p = _award_pick(brief, lambda x: x.lifespan_days,
                        highest=False)
        if p is not None:
            awards.append({
                "award": "Briefest Life",
                "project": p,
                "citation": "Lived %s, from %s to %s, with %d commits "
                            "in all. A short life, formally noted: "
                            "brevity is not the same as insignificance."
                            % (_lifespan_text(p), _fmt_date(p.born),
                               _fmt_date(p.died), p.commits),
            })
        p = _award_pick(dead, lambda x: x.commits)
        awards.append({
            "award": "The Life's Work",
            "project": p,
            "citation": "%d commits, more than anyone else in these "
                        "grounds, across a life of %s. Whatever became "
                        "of the plan, the record of the work stands."
                        % (p.commits, _lifespan_text(p)),
        })
        quiet = [p for p in dead if p.longest_flatline >= 1]
        p = _award_pick(quiet, lambda x: x.longest_flatline)
        if p is not None:
            awards.append({
                "award": "The Quietest Passing",
                "project": p,
                "citation": "Before the end, it fell silent for %d "
                            "days, the longest premortem quiet in "
                            "these grounds, and still came back to "
                            "work before the record closed for good."
                            % p.longest_flatline,
            })
        hopeful = []
        for p in dead:
            a = autopsy(p)
            if a["revival_verdict"] in _REVIVAL_RANK:
                hopeful.append((p, a))
        if hopeful:
            p, a = sorted(
                hopeful,
                key=lambda pa: (-_REVIVAL_RANK[pa[1]["revival_verdict"]],
                                -pa[1]["revival_score"],
                                pa[0].name))[0]
            awards.append({
                "award": "Most Likely to Rise",
                "project": p,
                "citation": "The Autopsy Department's verdict: %s "
                            "The record in its favour: %s. If anyone "
                            "in these grounds comes back, the smart "
                            "money is here."
                            % (a["revival_verdict"],
                               "; ".join(a["revival_reasons"])),
            })
    if cem.alive:
        p = sorted(cem.alive, key=lambda x: (x.born, x.name))[0]
        age = max(0, (cem.generated - p.born).days)
        awards.append({
            "award": "The Elder",
            "project": p,
            "citation": "Born %s and still breathing, %s into its "
                        "life and counting. The elder of these "
                        "grounds, honoured among the living."
                        % (_fmt_date(p.born), _site_life_text(age)),
        })
    if cem.coma:
        p = _award_pick(cem.coma, lambda x: x.silence_days)
        awards.append({
            "award": "The Patient",
            "project": p,
            "citation": "In intensive care these %d days, last seen "
                        "%s. The Society does not bury the living, "
                        "and it does not forget them either."
                        % (p.silence_days, _fmt_date(p.died)),
        })
    risen = [p for p in cem.projects if p.resurrections >= 1]
    if risen:
        p = sorted(risen,
                   key=lambda x: (-x.resurrections,
                                  -x.longest_flatline, x.name))[0]
        times = ("once" if p.resurrections == 1
                 else "%d times" % p.resurrections)
        awards.append({
            "award": "The Comeback",
            "project": p,
            "citation": "Flatlined for %d days and came back %s. "
                        "The death was filed, and then, on the "
                        "evidence of the record, unfiled."
                        % (p.longest_flatline, times),
        })
    return awards


def site_house_awards(cem):
    return [
        {
            "award": a["award"],
            "project_id": _site_slug(a["project"].name),
            "project_name": a["project"].name,
            "citation": a["citation"],
        }
        for a in house_awards(cem)
    ]


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


# ---------------------------------------------------------------------------
# Adoption listings: one ready-to-post paper per project (v0.28.0)
# ---------------------------------------------------------------------------


def adoption_subjects(cem):
    """Who may be offered: the buried, and the finished at rest.
    The still breathing and the intensive-care patients are not
    being offered, and the Society does not list them."""
    return cem.deceased + cem.resting


def adoption_listing_filename(p):
    return "%s-adoption.md" % _site_slug(p.name)


def _adoption_identity(p):
    """One line of introduction, from the record."""
    bits = []
    if p.language:
        bits.append("A %s project" % p.language)
    else:
        bits.append("A project")
    bits.append("lived from %s to %s (%s)"
                % (_fmt_date(p.born), _fmt_date(p.died),
                   _lifespan_text(p)))
    bits.append("%d commits by %s"
                % (p.commits,
                   "a single author" if p.authors == 1
                   else "%d authors" % p.authors))
    return ", ".join(bits) + "."


def render_adoption_listing(p, cem):
    """One ready-to-post adoption listing for a single project,
    drawn entirely from its own record. The buried are offered as
    the dead; the finished are offered as a retirement transfer,
    because they were completed, not felled."""
    a = autopsy(p)
    resting = p.status == "resting"
    lines = []
    if resting:
        lines += [
            "# Offered for a new keeper: %s" % p.name,
            "",
            "*A retirement transfer, filed by the Dead Projects "
            "Society. This project was finished, not felled; its "
            "author completed it and set it down. What it needs "
            "now is not a resurrection but a keeper.*",
            "",
        ]
    else:
        lines += [
            "# For adoption: %s" % p.name,
            "",
            "*An adoption listing, filed by the Dead Projects "
            "Society. Every project deserves a proper obituary; "
            "some deserve a second life. This one is offered for "
            "the second.*",
            "",
        ]
    lines += [_adoption_identity(p), ""]
    lines += ["## Why it is offered", ""]
    if resting:
        lines.append("The record closes with the coroner's note: %s"
                     % (p.cause or "Completed, by its author's word."))
        lines.append("It has been silent for %d days, not in "
                     "distress but in retirement."
                     % p.silence_days)
    else:
        lines.append("Cause of death, as the coroner wrote it: %s"
                     % (p.cause or "Cause unknown."))
        lines.append("The silence has lasted %d days."
                     % p.silence_days)
        lines.append("Its last words were \"%s\"."
                     % (p.last_words or "(none recorded)"))
    if p.will_status == "adoptable":
        lines.append("Its will asks for a new keeper, in writing.")
    if p.will_note:
        lines.append("Its author left word in the will: \"%s\""
                     % p.will_note)
    lines += ["", "## The state of the estate", ""]
    lines.append("Momentum, as the Autopsy Department read it: %s"
                 % a["momentum"])
    lines.append("Bus factor: %d. %s"
                 % (p.authors,
                    "A single pair of hands knew the whole story."
                    if p.authors <= 1 else
                    "The knowledge was not trapped in one head."))
    if a["findings"]:
        lines.append("")
        lines += ["- %s" % f for f in a["findings"]]
    lines += ["", "## Revival outlook", ""]
    lines.append("The Society's assessment: %s" % a["revival_verdict"])
    if a["revival_reasons"]:
        lines.append("The record in its favour: %s."
                     % "; ".join(a["revival_reasons"]))
    if resting:
        lines.append("To be plain: this one does not need reviving. "
                     "It needs a keeper willing to answer for it.")
    if p.survived_by and not p.survived_by.startswith(
            "Survived by no one"):
        lines += ["", "## A note on the succession", "",
                  p.survived_by,
                  "An adopter takes the elder line, with its full "
                  "history. The successor keeps its own name and its "
                  "own future; the Society records both.", ""]
    lines += [
        "## Terms of adoption",
        "",
        "- License: as recorded in the repository. (The owner "
        "confirms it here: ____________________)",
        "- Handover notes: ____________________",
        "- What the new keeper takes on: the project, its history, "
        "and its last words, and the promise to give it a future.",
        "",
        "The Society's standing word: nobody's project is modified, "
        "claimed, or republished without its owner's authorization. "
        "Memorializing a project is always free, and so is offering "
        "it a second life.",
        "",
        "---",
        "",
        "Filed by the Dead Projects Society, from the project's own "
        "record. The Society varnishes nothing.",
        "Give your own grounds the same courtesy: "
        "`pip install dead-projects-society`",
    ]
    return "\n".join(lines) + "\n"


def render_adoption_index(cem, subjects):
    """The index of listings in an adoption papers folder."""
    lines = [
        "# ADOPTION LISTINGS",
        "",
        "Issued by the Dead Projects Society, for the grounds at %s."
        % cem.root,
        "",
        "One listing per project offered, each drawn from the "
        "project's own record and ready to post wherever maintainers "
        "are found. The still breathing and the intensive-care "
        "patients are not listed; they are not being offered.",
        "",
    ]
    if not subjects:
        lines.append("No projects are offered at this time. The "
                     "grounds hold no one who needs a keeper.")
    for p in subjects:
        kind = ("retirement transfer" if p.status == "resting"
                else "adoption")
        lines.append("- [%s](%s): %s, %s to %s, %d commits."
                     % (p.name, adoption_listing_filename(p), kind,
                        _fmt_date(p.born), _fmt_date(p.died),
                        p.commits))
    lines += [
        "",
        "---",
        "",
        "The Society charges nothing for adoptions. It never has.",
        "`pip install dead-projects-society`",
    ]
    return "\n".join(lines) + "\n"


def write_adoption_papers(cem, folder):
    """Write one listing per offered project into folder, plus the
    index. Returns {project name: listing filename}. Deterministic:
    the same grounds produce byte-identical papers."""
    os.makedirs(folder, exist_ok=True)
    subjects = adoption_subjects(cem)
    files = {}
    for p in subjects:
        fname = adoption_listing_filename(p)
        with open(os.path.join(folder, fname), "w",
                  encoding="utf-8") as fh:
            fh.write(render_adoption_listing(p, cem))
        files[p.name] = fname
    with open(os.path.join(folder, "index.md"), "w",
              encoding="utf-8") as fh:
        fh.write(render_adoption_index(cem, subjects))
    return files


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


def _eulogy_pick(seed, salt, options):
    return options[(seed + salt) % len(options)]


def compose_full_eulogy(p):
    """The full eulogy, in the spoken style, for the buried and
    for the at rest.

    Woven only from what the standard scan already knows: the
    dates, the lifespan, the commit count, the peak month, the
    coroner's verdict, the last words, the successor, and any
    resurrection on the record. No fact is invented, and nothing
    is read that the scan did not already read. The variety is
    seeded from the project's name, so the same project receives
    the same eulogy on every visit; the Society composes, it
    does not improvise. At-rest projects are spoken of softly:
    they were not abandoned, they finished.
    """
    if p.status not in ("deceased", "resting"):
        return None
    seed = zlib.crc32(p.name.encode("utf-8"))
    resting = p.status == "resting"
    parts = []
    if resting:
        parts.append(_eulogy_pick(seed, 0, [
            "We speak gently of %s, for it is not dead. It "
            "finished." % p.name,
            "No mourning is in order for %s. It completed its "
            "work and lies at rest." % p.name,
            "The Society keeps a softer voice for %s, a project "
            "that ended on purpose." % p.name,
        ]))
    else:
        parts.append(_eulogy_pick(seed, 0, [
            "We are gathered for %s." % p.name,
            "Friends, the roll of the departed stops today at "
            "%s." % p.name,
            "The Society calls the name of %s, and the grounds "
            "go quiet." % p.name,
        ]))
    parts.append(_eulogy_pick(seed, 1, [
        "It lived from %s to %s, %s in all, and left %d "
        "commits behind it." % (_fmt_date(p.born),
                                 _fmt_date(p.died),
                                 _lifespan_text(p), p.commits),
        "Born %s, last heard from %s: %s of work, and %d "
        "commits on the record." % (_fmt_date(p.born),
                                     _fmt_date(p.died),
                                     _lifespan_text(p), p.commits),
        "Its dates run from %s to %s. The tally of the life is "
        "%s and %d commits." % (_fmt_date(p.born),
                                _fmt_date(p.died),
                                _lifespan_text(p), p.commits),
    ]))
    record = autopsy(p)
    if record["peak_month"] and record["peak_commits"] >= 2 \
            and p.commits >= 10:
        parts.append(_eulogy_pick(seed, 2, [
            "Its brightest month was %s, when %d commits landed "
            "and the work was at full stride."
            % (record["peak_month"], record["peak_commits"]),
            "If you want to remember it living, remember %s: "
            "%d commits in a single month."
            % (record["peak_month"], record["peak_commits"]),
            "The record peaks in %s, with %d commits, before "
            "the quiet began."
            % (record["peak_month"], record["peak_commits"]),
        ]))
    elif p.lifespan_days < 31 and p.commits >= 2:
        parts.append("The whole life fits inside a single "
                     "month; there was no time for seasons.")
    if p.commits >= 500:
        parts.append("%d commits is not a fling. It was loved, "
                     "and the record shows it." % p.commits)
    elif p.commits >= 50:
        parts.append("That count says it was meant, not toyed "
                     "with.")
    elif p.commits >= 10:
        parts.append("That count says it was more than an idea.")
    elif p.commits >= 2:
        parts.append("It never grew large, and it did not need "
                     "to. Small lives get eulogies too.")
    else:
        parts.append("A single commit is nearly all that "
                     "remains, and the Society reads it twice.")
    if resting:
        if p.will_note:
            parts.append('Its will leaves a note, in its '
                         'author\'s own words: "%s"' % p.will_note)
        else:
            parts.append("Its author declared it complete, in "
                         "writing, and the Society honors the "
                         "declaration.")
    elif p.cause:
        parts.append(_eulogy_pick(seed, 3, [
            "The coroner records the cause plainly. %s" % p.cause,
            "How did it end? %s" % p.cause,
            "The record closes with the coroner's verdict. %s"
            % p.cause,
        ]))
    if p.last_words:
        parts.append(_eulogy_pick(seed, 4, [
            'Its last words were "%s".' % p.last_words,
            'When it spoke for the final time, it said: "%s".'
            % p.last_words,
            'The last thing it ever said was "%s".'
            % p.last_words,
        ]))
    else:
        parts.append("It left no last words. The silence was "
                     "the message.")
    if p.resurrections == 1:
        parts.append("And let the record show that it had "
                     "already flatlined for %d days once and "
                     "come back. This time, it did not."
                     % p.longest_flatline)
    elif p.resurrections > 1:
        parts.append("It came back from the dead %d times, the "
                     "longest silence lasting %d days, and the "
                     "Society admired the stubbornness. This "
                     "time, it stayed."
                     % (p.resurrections, p.longest_flatline))
    if p.survived_by:
        if p.survived_by.startswith("Survived by no one"):
            parts.append("Nothing has taken its place. The slot "
                         "is still open, and the Society keeps "
                         "the key.")
        else:
            parts.append(p.survived_by)
    if resting:
        parts.append(_eulogy_pick(seed, 5, [
            "Rest well, %s. Finished is a fine word." % p.name,
            "The Society closes the book on %s, gently." % p.name,
            "%s asked for nothing more, and neither do we."
            % p.name,
        ]))
    else:
        parts.append(_eulogy_pick(seed, 5, [
            "Go in peace, %s. The grounds remember." % p.name,
            "The Society lowers its hat. Rest well, %s." % p.name,
            "%s was worked on, and that is enough. The service "
            "is over." % p.name,
        ]))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# The Year in Review: the Society's Wrapped
# ---------------------------------------------------------------------------

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November",
                "December"]


def _monthly_counts(p):
    """Yield ((year, month), commits) for each month of a life, from
    the activity record the scan already keeps."""
    y, m = p.born.year, p.born.month
    for count in p.activity:
        yield (y, m), count
        m += 1
        if m > 12:
            y, m = y + 1, 1


def compute_wrapped(cem, year):
    """The Society's Year in Review for one calendar year, computed
    from the record alone: who was born, who was buried, who rose,
    and how the year was spent. Deterministic; a quiet year is
    reported as a quiet year."""
    born = sorted((p for p in cem.projects if p.born.year == year),
                  key=lambda p: p.born)
    ended = [p for p in cem.deceased + cem.resting if p.died.year == year]
    buried = sorted((p for p in ended if p.status == "deceased"),
                    key=lambda p: p.died)
    resting = sorted((p for p in ended if p.status == "resting"),
                     key=lambda p: p.died)
    risen = []
    for p in cem.projects:
        events = [end for gap, end in p.gap_events
                  if gap >= cem.dead_days and end.year == year]
        if events:
            risen.append(p)
    risen.sort(key=lambda p: p.name)
    commits_in_year = 0
    month_totals = {}
    for p in cem.projects:
        for (y, m), count in _monthly_counts(p):
            if y == year and count:
                commits_in_year += count
                month_totals[(y, m)] = month_totals.get((y, m), 0) + count
    busiest = None
    if month_totals:
        (by, bm), bc = sorted(month_totals.items(),
                              key=lambda kv: (-kv[1], kv[0]))[0]
        busiest = {"month": "%s %d" % (_MONTH_NAMES[bm - 1], by),
                   "commits": bc}
    longest = shortest = None
    if ended:
        lp = max(ended, key=lambda p: (p.lifespan_days, p.name))
        sp = min(ended, key=lambda p: (p.lifespan_days, p.name))
        longest = {"project": lp.name,
                   "lifespan_days": lp.lifespan_days,
                   "lifespan": _lifespan_text(lp)}
        shortest = {"project": sp.name,
                    "lifespan_days": sp.lifespan_days,
                    "lifespan": _lifespan_text(sp)}
    common_cause = None
    if buried:
        counts = {}
        for p in buried:
            counts[p.cause] = counts.get(p.cause, 0) + 1
        cause, n = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        common_cause = {"cause": cause, "count": n}
    survivor = None
    if cem.alive:
        sp = min(cem.alive, key=lambda p: (p.born, p.name))
        survivor = {"project": sp.name,
                    "born": sp.born.date().isoformat(),
                    "age_days": max(0, (cem.generated - sp.born).days)}
    return {
        "year": year,
        "born": {"count": len(born),
                 "projects": [p.name for p in born]},
        "buried": {"count": len(buried),
                   "projects": [p.name for p in buried]},
        "at_rest": {"count": len(resting),
                    "projects": [p.name for p in resting]},
        "resurrected": {"count": len(risen),
                        "projects": [p.name for p in risen]},
        "commits_in_year": commits_in_year,
        "busiest_month": busiest,
        "longest_life_ended": longest,
        "shortest_life_ended": shortest,
        "most_common_cause": common_cause,
        "oldest_survivor": survivor,
        "intensive_care_now": len(cem.coma),
        "still_breathing_now": len(cem.alive),
        "has_activity": bool(born or ended or risen or commits_in_year),
    }


def _wrapped_lines(w):
    """The Year in Review as plain lines, shared by the terminal
    report and the Markdown report."""
    lines = []
    if not w["has_activity"]:
        lines.append("Nothing was born, nothing was buried, and "
                     "nothing rose in %d. The Society records the "
                     "silence, and invents nothing to fill it."
                     % w["year"])
    else:
        lines.append("Born: %d (%s)"
                     % (w["born"]["count"],
                        ", ".join(w["born"]["projects"]) or "none"))
        lines.append("Buried: %d (%s)"
                     % (w["buried"]["count"],
                        ", ".join(w["buried"]["projects"]) or "none"))
        if w["at_rest"]["count"]:
            lines.append("Finished, and at rest: %d (%s)"
                         % (w["at_rest"]["count"],
                            ", ".join(w["at_rest"]["projects"])))
        lines.append("Back from the dead: %d (%s)"
                     % (w["resurrected"]["count"],
                        ", ".join(w["resurrected"]["projects"]) or "none"))
        lines.append("Commits landed across the grounds: %d"
                     % w["commits_in_year"])
        if w["busiest_month"]:
            lines.append("Busiest month: %s, with %d commits"
                         % (w["busiest_month"]["month"],
                            w["busiest_month"]["commits"]))
        if w["longest_life_ended"]:
            lines.append("Longest life that ended: %s, %s"
                         % (w["longest_life_ended"]["project"],
                            w["longest_life_ended"]["lifespan"]))
        if w["shortest_life_ended"]:
            lines.append("Shortest life that ended: %s, %s"
                         % (w["shortest_life_ended"]["project"],
                            w["shortest_life_ended"]["lifespan"]))
        if w["most_common_cause"]:
            lines.append("The coroner wrote it most often (%d): %s"
                         % (w["most_common_cause"]["count"],
                            w["most_common_cause"]["cause"]))
    if w["oldest_survivor"]:
        lines.append("Oldest still breathing: %s, born %s and not "
                     "done yet."
                     % (w["oldest_survivor"]["project"],
                        w["oldest_survivor"]["born"]))
    lines.append("As the year closes: %d in intensive care, %d still "
                 "breathing."
                 % (w["intensive_care_now"], w["still_breathing_now"]))
    return lines


def render_wrapped_card(cem, year):
    """The Wrapped card: the year's headline numbers, in the square
    card's language at link-preview size. Dark grounds, gold
    numerals, the Society's name."""
    def esc(s):
        return xml_escape(str(s), {'"': "&quot;"})

    w = compute_wrapped(cem, year)
    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" '
        'height="630" viewBox="0 0 1200 630">')
    parts.append('<rect width="1200" height="630" fill="#101418"/>')
    parts.append('<rect x="24" y="24" width="1152" height="582" rx="18" '
                 'fill="none" stroke="#333d46" stroke-width="2"/>')
    parts.append('<rect x="38" y="38" width="1124" height="554" rx="12" '
                 'fill="none" stroke="#232a31" stroke-width="1"/>')
    parts.append('<text x="600" y="112" text-anchor="middle" '
                 'font-family="Georgia, serif" font-size="28" '
                 'fill="#8b96a0" letter-spacing="8">DEAD PROJECTS '
                 'SOCIETY</text>')
    parts.append('<text x="600" y="172" text-anchor="middle" '
                 'font-family="Georgia, serif" font-size="46" '
                 'fill="#e8e2d2">%d IN REVIEW</text>' % year)
    stats = [
        ("BORN", str(w["born"]["count"])),
        ("BURIED", str(w["buried"]["count"])),
        ("RESURRECTED", str(w["resurrected"]["count"])),
        ("COMMITS", str(w["commits_in_year"])),
    ]
    for i, (label, val) in enumerate(stats):
        cx = 210 + i * 260
        parts.append('<text x="%d" y="330" text-anchor="middle" '
                     'font-family="Georgia, serif" font-size="92" '
                     'fill="#dcb968">%s</text>' % (cx, esc(val)))
        parts.append('<text x="%d" y="378" text-anchor="middle" '
                     'font-family="Georgia, serif" font-size="21" '
                     'fill="#b08d57" letter-spacing="3">%s</text>'
                     % (cx, esc(label)))
    notes = []
    if w["busiest_month"]:
        notes.append("Busiest month: %s, %d commits."
                     % (w["busiest_month"]["month"],
                        w["busiest_month"]["commits"]))
    if w["longest_life_ended"]:
        notes.append("Longest life that ended: %s, %s."
                     % (w["longest_life_ended"]["project"],
                        w["longest_life_ended"]["lifespan"]))
    if not w["has_activity"]:
        notes.append("A quiet year. The Society invents nothing.")
    y = 452
    for line in notes[:2]:
        parts.append('<text x="600" y="%d" text-anchor="middle" '
                     'font-family="Georgia, serif" font-style="italic" '
                     'font-size="27" fill="#c3ccd4">%s</text>'
                     % (y, esc(line)))
        y += 44
    parts.append('<text x="600" y="562" text-anchor="middle" '
                 'font-family="Georgia, serif" font-size="20" '
                 'fill="#5f6a74">The year, formally reviewed. Judged '
                 'locally from git metadata alone.</text>')
    parts.append("</svg>")
    return "".join(parts)


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


def render_terminal(cem, with_autopsy=False, with_on_this_day=False,
                    with_eulogy=False, wrapped_year=None,
                    with_house_awards=False):
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
    if with_house_awards:
        awards = house_awards(cem)
        out.append("-" * 64)
        out.append("  THE HOUSE AWARDS (a ceremony for these grounds)")
        if awards:
            for a in awards:
                out.append("  ~ %s: %s. %s"
                           % (a["award"], a["project"].name,
                              a["citation"]))
        else:
            out.append("  No awards this year. The grounds hold no "
                       "one the record can honour, and the Society "
                       "does not invent honourees.")
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
    if with_eulogy:
        subjects = cem.deceased + cem.resting
        if subjects:
            out.append("-" * 64)
            out.append("  THE EULOGIES (read aloud, as is proper)")
            for p in subjects:
                out.append("")
                out.append("  For %s:" % p.name)
                for line in textwrap.wrap(compose_full_eulogy(p),
                                          62):
                    out.append("  " + line)
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
    if wrapped_year is not None:
        w = compute_wrapped(cem, wrapped_year)
        out.append("-" * 64)
        out.append("  %d IN REVIEW (the Society's Wrapped)"
                   % wrapped_year)
        for line in _wrapped_lines(w):
            out.append("  " + line)
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


def cemetery_dict(cem, with_eulogy=False, wrapped_year=None,
                  adoption_files=None, with_house_awards=False):
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
            "full_eulogy": (compose_full_eulogy(p)
                            if with_eulogy else None),
            "adoption_listing": (adoption_files.get(p.name)
                                 if adoption_files else None),
            "autopsy": autopsy(p) if p.status in ("deceased", "resting")
                       else None,
            "activity_monthly": p.activity,
            "language": p.language or None,
            "dependency_commits": p.dep_commits,
            "dependency_tail_share": round(p.dep_tail_share, 2),
            "deep_autopsy": getattr(p, "deep_autopsy", None),
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
            "adoption_papers": (len(adoption_files)
                                if adoption_files else 0),
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
        "wrapped": (compute_wrapped(cem, wrapped_year)
                    if wrapped_year is not None else None),
        "awards": ([{"award": a["award"],
                     "project": a["project"].name,
                     "citation": a["citation"]}
                    for a in house_awards(cem)]
                   if with_house_awards else None),
    }


# ---------------------------------------------------------------------------
# Rendering: Markdown obituaries
# ---------------------------------------------------------------------------


def render_markdown(cem, with_eulogy=False, wrapped_year=None,
                    with_house_awards=False):
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
        if with_eulogy:
            out.append("**The eulogy, as read at the service:** %s"
                       % compose_full_eulogy(p))
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
        if with_eulogy:
            out.append("**The eulogy, as read at the service:** %s"
                       % compose_full_eulogy(p))
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
    if with_house_awards:
        awards = house_awards(cem)
        out.append("## The House Awards")
        out.append("")
        if awards:
            for a in awards:
                out.append("- **%s:** %s. %s"
                           % (a["award"], a["project"].name,
                              a["citation"]))
        else:
            out.append("No awards this year. The grounds hold no one "
                       "the record can honour, and the Society does "
                       "not invent honourees.")
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
    if wrapped_year is not None:
        w = compute_wrapped(cem, wrapped_year)
        out.append("## %d in Review: the Society's Wrapped"
                   % wrapped_year)
        out.append("")
        for line in _wrapped_lines(w):
            out.append("- %s" % line)
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
  .fulleulogy {{ text-align:left; color:#c3ccd4; margin-top:.7rem;
            font-size:.95rem; line-height:1.55; }}
  .autopsy {{ color:#8b96a0; font-size:.85rem; margin-top:.55rem; }}
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


def render_html(cem, log=None, with_eulogy=False, wrapped_year=None,
                with_house_awards=False):
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
        aut = autopsy(p)
        autopsy_line = (
            '<div class="autopsy">Autopsy: %.1f commits a month'
            " &middot; %s &middot; Revival: %s</div>"
            % (aut["pace_commits_per_month"], esc(aut["momentum"]),
               esc(aut["revival_verdict"])))
        full_eulogy = ""
        if with_eulogy:
            full_eulogy = ('<div class="fulleulogy">%s</div>'
                           % esc(compose_full_eulogy(p)))
        stones.append(
            '<div class="stone"><div class="rip">R.I.P.</div>'
            "<h2>%s</h2>"
            '<div class="dates">%s &ndash; %s<br>aged %s &middot; %d commits'
            "</div>"
            '<div class="words">&ldquo;%s&rdquo;</div>'
            '<div class="cause">%s</div>'
            '<div class="eulogy">%s</div>%s%s%s%s'
            '<div class="survived">%s</div></div>'
            % (esc(p.name), _fmt_date(p.born), _fmt_date(p.died),
               _lifespan_text(p), p.commits,
               esc(p.last_words or "(silence)"), esc(p.cause),
               esc(compose_eulogy(p)), full_eulogy, risen, factors,
               autopsy_line, esc(p.survived_by)))
    extra = []
    if log:
        if log["first_visit"]:
            log_body = ("No previous visit on record. The log begins "
                        "today; %d projects entered into it."
                        % len(log["newly_born"]))
        else:
            log_rows = [("Newly buried", log["newly_buried"]),
                        ("Finished, and at rest", log["newly_resting"]),
                        ("Risen", log["risen"]),
                        ("Stirred in their graves", log["stirred"]),
                        ("Newly born", log["newly_born"])]
            parts = ["%s: %s" % (label, ", ".join(esc(n) for n in names))
                     for label, names in log_rows if names]
            if not parts:
                parts = ["Nothing changed. The grounds are as you "
                         "left them."]
            parts.append("Still buried, undisturbed: %d."
                         % log["still_buried"])
            log_body = "<br>".join(parts)
        extra.append('<h3 class="section">THE GROUNDSKEEPER&rsquo;S '
                     'LOG</h3><div class="living">%s</div>' % log_body)
    honors = society_honors(cem)
    if honors:
        rows = "<br>".join(
            "%s: %s. %s" % (esc(h["title"]), esc(h["project"].name),
                            esc(h["detail"]))
            for h in honors)
        extra.append('<h3 class="section">THE SOCIETY&rsquo;S HONORS</h3>'
                     '<div class="living">%s</div>' % rows)
    if cem.resting:
        if with_eulogy:
            rows = "<br><br>".join(
                "%s &mdash; %s<br><em>%s</em>"
                % (esc(p.name), esc(p.cause),
                   esc(compose_full_eulogy(p)))
                for p in cem.resting)
        else:
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
    if with_house_awards:
        awards = house_awards(cem)
        if awards:
            rows = "<br>".join(
                "%s: %s. %s" % (esc(a["award"]),
                                esc(a["project"].name),
                                esc(a["citation"]))
                for a in awards)
        else:
            rows = ("No awards this year. The grounds hold no one "
                    "the record can honour, and the Society does not "
                    "invent honourees.")
        extra.append('<h3 class="section">THE HOUSE AWARDS</h3>'
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
    if wrapped_year is not None:
        w = compute_wrapped(cem, wrapped_year)
        rows = "<br>".join(esc(line) for line in _wrapped_lines(w))
        extra.append('<h3 class="section">%d IN REVIEW: THE '
                     'SOCIETY&rsquo;S WRAPPED</h3>'
                     '<div class="living">%s</div>' % (wrapped_year, rows))
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


def site_projects(cem, with_eulogy=False):
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
        if with_eulogy:
            stone["eulogy"] = compose_full_eulogy(p)
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



# ------------------------------------------------------------------
# The Deep Autopsy Department (opt-in, code-aware, Ember-powered)
#
# The standard scan reads git metadata only and never opens a file.
# This department is the one deliberate exception, and it is opt-in
# twice over: the --deep-autopsy flag, and a Meta Model API key the
# user supplies. When it runs, a bounded sample of the project (its
# README, manifests, largest source files, and final diffs) is sent
# to Muse Ember, which writes a structured autopsy cited to files
# and commits. Every call is priced before it is made, recorded in
# a ledger, and refused when it would cross the budget cap. The
# Society's rule stands: nobody's code is read without the owner
# asking, in so many flags.
# ------------------------------------------------------------------

import urllib.error
import urllib.request

DEEP_API_URL = "https://api.meta.ai/v1/responses"
DEEP_MODEL_DEFAULT = os.environ.get("DPS_DEEP_MODEL", "muse-ember-1.0")
DEEP_INPUT_USD_PER_TOKEN = 0.10 / 1000000
DEEP_OUTPUT_USD_PER_TOKEN = 0.50 / 1000000
DEEP_DEFAULT_BUDGET_USD = 10.00
DEEP_DEFAULT_MAX_TOKENS = 120000
DEEP_ASSUMED_OUTPUT_TOKENS = 2500
_DEEP_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv",
                   "venv", "dist", "build", "target", ".next",
                   "vendor", ".hg", ".svn"}


class DeepAutopsyError(Exception):
    """A deep autopsy could not be performed; the reason is plain."""


def _est_tokens(text):
    return (len(text) + 3) // 4


def _read_bounded(path, cap):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(cap)
    except OSError:
        return ""


def sample_project(p, max_tokens=DEEP_DEFAULT_MAX_TOKENS):
    """Assemble the bounded sample of one project for Ember.

    Returns (text, stats). The sample is the ONLY thing that leaves
    the machine, and it is assembled entirely from the owner's own
    folder at the owner's explicit request.
    """
    root = p.path
    parts = []
    files = []
    head = ["PROJECT: %s" % p.name,
            "LIFESPAN: %s to %s (%d commits, %d author(s))"
            % (p.born.date(), p.died.date(), p.commits, p.authors),
            "LAST WORDS: %s" % (p.last_words or "")]
    meta = autopsy(p)
    if meta:
        head.append("METADATA AUTOPSY: %s; revival verdict: %s"
                    % (meta["momentum"], meta["revival_verdict"]))
    parts.append("\n".join(head))

    for name in sorted(os.listdir(root)):
        if name.lower().startswith("readme") and \
                os.path.isfile(os.path.join(root, name)):
            text = _read_bounded(os.path.join(root, name), 12000)
            if text:
                parts.append("===== %s =====\n%s" % (name, text))
                files.append(name)
            break

    for name in ("package.json", "pyproject.toml", "Cargo.toml",
                 "go.mod", "Gemfile", "requirements.txt",
                 "composer.json", "pom.xml"):
        path = os.path.join(root, name)
        if os.path.isfile(path):
            text = _read_bounded(path, 4000)
            if text:
                parts.append("===== %s =====\n%s" % (name, text))
                files.append(name)

    tree, sized = [], []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _DEEP_SKIP_DIRS
                   and not d.startswith(".")]
        for name in names:
            full = os.path.join(base, name)
            rel = os.path.relpath(full, root)
            tree.append(rel)
            ext = os.path.splitext(name)[1].lower()
            if ext in _LANG_BY_EXT:
                try:
                    sized.append((os.path.getsize(full), rel, full))
                except OSError:
                    pass
    tree.sort()
    parts.append("===== FILE TREE (%d files) =====\n%s"
                 % (len(tree), "\n".join(tree[:200])))

    sized.sort(reverse=True)
    for _size, rel, full in sized[:3]:
        text = _read_bounded(full, 15000)
        if text:
            parts.append("===== %s =====\n%s" % (rel, text))
            files.append(rel)

    diff = _git(root, "log", "-p", "-3")
    if diff:
        parts.append("===== FINAL COMMITS (git log -p -3) =====\n%s"
                     % diff[:20000])
        files.append("git log -p -3")

    text = "\n\n".join(parts)
    truncated = False
    if _est_tokens(text) > max_tokens:
        text = text[: max_tokens * 4]
        cut = text.rfind("\n")
        if cut > 0:
            text = text[:cut]
        truncated = True
    stats = {"files": files, "chars": len(text),
             "est_tokens": _est_tokens(text), "truncated": truncated}
    return text, stats


def deep_ledger_default():
    return os.path.join(os.path.expanduser("~"),
                        ".dead-projects-society", "deep-ledger.jsonl")


def deep_ledger_total(path):
    total = 0.0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    total += float(json.loads(line).get("cost_usd", 0))
                except (ValueError, TypeError):
                    continue
    except OSError:
        return 0.0
    return total


def deep_ledger_append(path, entry):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def deep_estimate(sample_text,
                  out_tokens=DEEP_ASSUMED_OUTPUT_TOKENS):
    in_tokens = _est_tokens(sample_text)
    cost = (in_tokens * DEEP_INPUT_USD_PER_TOKEN
            + out_tokens * DEEP_OUTPUT_USD_PER_TOKEN)
    return in_tokens, cost


_DEEP_PROMPT = """You are the Deep Autopsy surgeon of the Dead Projects Society. Below is a bounded sample of a dead software project: its metadata verdict, README, manifests, file tree, largest source files, and final commits. Everything you claim must be cited to something in the sample: a file path, a commit, a line of the README. Where the sample does not show something, write "the sample does not show" instead of guessing. Do not invent dates, people, or events.

Write the autopsy in exactly these sections:

CAUSE OF DEATH, CONFIRMED FROM THE BODY
The specific technical or human cause the evidence supports, with its citations.

CONTRIBUTING CONDITIONS
What weakened it before the end: unfinished work, dependency weight, scope, silence in the record.

LEFT UNFINISHED
What the record shows was started and never completed.

SALVAGEABLE PARTS
What a new project could honestly take from this one.

REVIVAL
Difficulty (low, moderate, high, or do not attempt) and the first three concrete steps.

FINAL NOTE
One or two sentences in the Society's register: factual, unsentimental, a little kind.

THE SAMPLE
"""


def build_deep_prompt(p, sample_text):
    return _DEEP_PROMPT + sample_text


def _post_responses(prompt, model, api_key, timeout=180):
    payload = json.dumps({"model": model, "input": prompt}).encode()
    req = urllib.request.Request(
        DEEP_API_URL, data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + api_key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_output_text(parsed):
    if isinstance(parsed.get("output_text"), str):
        return parsed["output_text"]
    out = []
    for item in parsed.get("output") or []:
        for part in item.get("content") or []:
            if part.get("type") in ("output_text", "text") \
                    and isinstance(part.get("text"), str):
                out.append(part["text"])
    return "\n".join(out)


def _extract_usage(parsed):
    usage = parsed.get("usage") or {}
    in_t = usage.get("input_tokens", usage.get("prompt_tokens"))
    out_t = usage.get("output_tokens", usage.get("completion_tokens"))
    return in_t, out_t


def call_ember(prompt, model, api_key=None, post_fn=None):
    """One Ember autopsy call. Returns (text, in_tokens, out_tokens);
    token counts are None when the API does not report usage."""
    if post_fn is not None:
        parsed = post_fn(prompt, model)
    else:
        key = api_key or os.environ.get("META_API_KEY")
        if not key:
            raise DeepAutopsyError(
                "No Meta Model API key. The Deep Autopsy Department "
                "needs one: set META_API_KEY, or use --deep-dry-run "
                "to see the sample and the price without calling.")
        try:
            parsed = _post_responses(prompt, model, key)
        except urllib.error.HTTPError as exc:
            raise DeepAutopsyError(
                "The model API refused the call (HTTP %d). Check the "
                "key and the model id (%s)." % (exc.code, model))
        except (urllib.error.URLError, OSError) as exc:
            raise DeepAutopsyError(
                "The model API could not be reached (%s)." % exc)
    text = _extract_output_text(parsed)
    if not text:
        raise DeepAutopsyError("The model returned no autopsy text.")
    in_t, out_t = _extract_usage(parsed)
    return text, in_t, out_t


def run_deep_autopsies(cem, args):
    """The opt-in department at work. Prints its own section and
    records each report on its project for the JSON output."""
    budget = getattr(args, "deep_budget", DEEP_DEFAULT_BUDGET_USD)
    model = getattr(args, "deep_model", DEEP_MODEL_DEFAULT)
    max_tokens = getattr(args, "deep_max_tokens",
                         DEEP_DEFAULT_MAX_TOKENS)
    ledger = getattr(args, "deep_ledger", None) or deep_ledger_default()
    dry = getattr(args, "deep_dry_run", False)
    post_fn = getattr(args, "deep_post_fn", None)
    targets = [p for p in cem.projects
               if p.status in ("deceased", "resting")]
    print()
    print("THE DEEP AUTOPSY DEPARTMENT (opt-in, code-aware)")
    print("Samples assembled from your own folders are sent to the "
          "model API. The standard scan never does this.")
    if not targets:
        print("No bodies on the table: nothing buried or at rest in "
              "these grounds.")
        return
    spent = deep_ledger_total(ledger)
    print("Budget: $%.2f of $%.2f spent (ledger: %s)"
          % (spent, budget, ledger))
    for p in targets:
        sample, stats = sample_project(p, max_tokens=max_tokens)
        _in_t, est = deep_estimate(sample)
        if spent + est > budget:
            print("BUDGET GUARD: %s refused. $%.2f spent of $%.2f; "
                  "this autopsy is estimated at $%.4f."
                  % (p.name, spent, budget, est))
            break
        if dry:
            print("DRY RUN %s: %d sources sampled, ~%d tokens, "
                  "estimated $%.4f. No call was made."
                  % (p.name, len(stats["files"]), stats["est_tokens"],
                     est))
            continue
        try:
            text, u_in, u_out = call_ember(
                build_deep_prompt(p, sample), model, post_fn=post_fn)
        except DeepAutopsyError as exc:
            print("DEEP AUTOPSY FAILED for %s: %s" % (p.name, exc))
            break
        if u_in is None:
            u_in = stats["est_tokens"]
        if u_out is None:
            u_out = DEEP_ASSUMED_OUTPUT_TOKENS
        cost = (u_in * DEEP_INPUT_USD_PER_TOKEN
                + u_out * DEEP_OUTPUT_USD_PER_TOKEN)
        deep_ledger_append(ledger, {
            "time": cem.generated.isoformat(), "project": p.name,
            "model": model, "input_tokens": u_in,
            "output_tokens": u_out, "cost_usd": round(cost, 6)})
        spent += cost
        p.deep_autopsy = {"model": model, "input_tokens": u_in,
                          "output_tokens": u_out,
                          "cost_usd": round(cost, 4), "report": text}
        print()
        print("DEEP AUTOPSY: %s (model %s, $%.4f)"
              % (p.name, model, cost))
        print(text)


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
    ap.add_argument("--wrapped", type=int, nargs="?", const=0,
                    default=None, metavar="YEAR",
                    help="Append the Society's Year in Review "
                         "(Wrapped) for YEAR (default: this year) to "
                         "the terminal, Markdown, HTML, and JSON "
                         "reports, and write the Wrapped SVG card")
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
    ap.add_argument("--exclude", action="append", default=[],
                    metavar="NAME",
                    help="Skip directories with this name while "
                         "scanning (repeatable): vendored checkouts, "
                         "mirrors, other people's dead")
    ap.add_argument("--deep-autopsy", action="store_true",
                    help="Opt-in and code-aware: send a bounded "
                         "sample of each buried or at-rest project "
                         "to Muse Ember for a structured deep "
                         "autopsy (needs META_API_KEY; every call "
                         "is priced first and recorded in a ledger)")
    ap.add_argument("--deep-dry-run", action="store_true",
                    help="With the deep autopsy: assemble the "
                         "samples and print the estimated prices, "
                         "but make no API call")
    ap.add_argument("--deep-budget", type=float,
                    default=DEEP_DEFAULT_BUDGET_USD, metavar="USD",
                    help="Hard cap on recorded deep-autopsy spend "
                         "(default: $10.00)")
    ap.add_argument("--deep-model", default=DEEP_MODEL_DEFAULT,
                    metavar="ID",
                    help="Model id for the deep autopsy "
                         "(default: %(default)s)")
    ap.add_argument("--deep-max-tokens", type=int,
                    default=DEEP_DEFAULT_MAX_TOKENS, metavar="N",
                    help="Sample size cap in estimated tokens "
                         "(default: %(default)s)")
    ap.add_argument("--deep-ledger", default=None, metavar="FILE",
                    help="Spend ledger for deep autopsies (default: "
                         "~/.dead-projects-society/deep-ledger.jsonl)")
    ap.add_argument("--fail-if-new-deaths", action="store_true",
                    help="With --diff: exit with code 3 when the "
                         "Groundskeeper's Log finds a death it has "
                         "not reported before: a project newly buried "
                         "since the last visit, or one found already "
                         "buried on a later visit (for scripts and CI)")
    ap.add_argument("--oneline", action="store_true",
                    help="Print one line per project (name, state, "
                         "silence, cause) instead of the full report")
    ap.add_argument("--adopt", metavar="FILE", default=None,
                    help="Write adoption papers (Markdown) for the "
                         "buried: one honest listing per project, "
                         "with a line for a new keeper to sign")
    ap.add_argument("--adoption-papers", metavar="DIR", default=None,
                    help="Write one ready-to-post adoption listing "
                         "(Markdown) per buried or at-rest project "
                         "into DIR, with an index: the estate, the "
                         "revival outlook, and blank terms for the "
                         "owner to complete")
    ap.add_argument("--on-this-day", action="store_true",
                    help="Append anniversaries: projects that died or "
                         "were born on this month and day in earlier "
                         "years")
    ap.add_argument("--autopsy", action="store_true",
                    help="Append the Autopsy Department's findings "
                         "(metadata only) to the terminal report")
    ap.add_argument("--eulogy", action="store_true",
                    help="Compose the full eulogy for every buried "
                         "or at-rest project and include it in the "
                         "terminal report, the Markdown and HTML "
                         "obituaries, the JSON, and the site export")
    ap.add_argument("--house-awards", action="store_true",
                    help="Hold the House Awards: a ceremony for "
                         "these grounds alone, one honour per "
                         "category the record genuinely supports "
                         "(longest life, briefest life, the life's "
                         "work, the quietest passing, most likely "
                         "to rise, the elder, the patient, the "
                         "comeback), in the terminal report, the "
                         "Markdown and HTML obituaries, and the "
                         "JSON; not to be confused with the "
                         "Obituary Awards, which are for the famous")
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
    cem = build_grounds(roots, dead_days=args.days, depth=args.depth,
                        exclude=args.exclude)
    if not cem.projects:
        print("No bodies found. No git repositories under %s."
              % cem.root)
        return 2

    if args.deep_autopsy or args.deep_dry_run:
        run_deep_autopsies(cem, args)

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

    wrapped_year = None
    if args.wrapped is not None:
        wrapped_year = args.wrapped or cem.generated.year

    adoption_files = None
    if args.adoption_papers:
        adoption_files = write_adoption_papers(cem,
                                               args.adoption_papers)

    if args.json:
        data = cemetery_dict(cem, with_eulogy=args.eulogy,
                             wrapped_year=wrapped_year,
                             adoption_files=adoption_files,
                             with_house_awards=args.house_awards)
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
                              with_on_this_day=args.on_this_day,
                              with_eulogy=args.eulogy,
                              wrapped_year=wrapped_year,
                              with_house_awards=args.house_awards))
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
            fh.write(render_html(cem, log if args.diff else None,
                                 with_eulogy=args.eulogy,
                                 wrapped_year=wrapped_year,
                                 with_house_awards=args.house_awards))
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
            fh.write(render_markdown(cem, with_eulogy=args.eulogy,
                                     wrapped_year=wrapped_year,
                                     with_house_awards=args.house_awards))
        print("Obituaries written to %s" % args.out)
    if wrapped_year is not None:
        out_path = None
        for candidate in (args.out, args.html, args.card, args.square):
            if candidate:
                out_path = candidate
                break
        folder = (os.path.dirname(os.path.abspath(out_path))
                  if out_path else os.getcwd())
        card_path = os.path.join(folder, "wrapped-%d.svg" % wrapped_year)
        with open(card_path, "w", encoding="utf-8") as fh:
            fh.write(render_wrapped_card(cem, wrapped_year))
        if not args.json:
            print("Wrapped card for %d written to %s"
                  % (wrapped_year, card_path))
    if args.adopt:
        with open(args.adopt, "w", encoding="utf-8") as fh:
            fh.write(render_adoption_papers(cem))
        print("Adoption papers: %s (%d projects listed)"
              % (args.adopt, len(cem.deceased)))
    if adoption_files is not None:
        print("Adoption listings written to %s (%d papers, plus "
              "index.md)"
              % (args.adoption_papers, len(adoption_files)))
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
            json.dump(site_projects(cem, with_eulogy=args.eulogy),
                      fh, indent=2)
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
        with open(os.path.join(args.site, "wrapped.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(compute_wrapped(cem, cem.generated.year),
                      fh, indent=2)
            fh.write("\n")
        with open(os.path.join(args.site, "house_awards.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(site_house_awards(cem), fh, indent=2)
            fh.write("\n")
        with open(os.path.join(args.site, "survey.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({
                "generated": cem.generated.date().isoformat(),
                "tool": "dead-projects-society",
                "version": VERSION,
                "buried": len(cem.deceased),
                "at_rest": len(cem.resting),
                "coma": len(cem.coma),
                "alive": len(cem.alive),
            }, fh, indent=2)
            fh.write("\n")
        if adoption_files is not None:
            write_adoption_papers(
                cem, os.path.join(args.site, "adoption-papers"))
        print("Web graveyard data written to %s" % args.site)
    if args.fail_if_new_deaths and log and not log.get("first_visit"):
        dead_now = {p.name for p in cem.deceased}
        new_deaths = set(log.get("newly_buried", []))
        new_deaths |= set(log.get("newly_born", [])) & dead_now
        if new_deaths:
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
