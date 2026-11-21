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

VERSION = "0.2.0"

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
    status: str = ""        # alive | coma | deceased
    cause: str = ""
    factors: list = field(default_factory=list)
    survived_by: str = ""

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
    )


# ---------------------------------------------------------------------------
# The coroner: status, cause of death, contributing factors, succession
# ---------------------------------------------------------------------------

_WIP_RE = re.compile(r"^(wip|temp|tmp|test|testing|asdf|checkpoint|save)\b",
                     re.IGNORECASE)
_FIX_RE = re.compile(r"\bfix", re.IGNORECASE)
_REFACTOR_RE = re.compile(
    r"\b(refactor|cleanup|clean up|reorganiz\w*|restructur\w*|tidy)\b",
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
    if p.born.month == 1 and life <= 45:
        return "New Year's resolution. You know how those go."
    if life <= 3 and p.commits <= 15:
        return "Weekend fling. It was never going to be a thing."
    if _FIX_RE.search(msg) and p.commits >= 20:
        return "Died as it lived: one more fix."
    if _REFACTOR_RE.search(msg) and p.commits >= 10:
        return ("Died in a refactor. It was going to be cleaner. "
                "It was going to be beautiful.")
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


def build_cemetery(root, dead_days=DEFAULT_DEAD_DAYS, depth=1, now=None):
    now = now or datetime.now(timezone.utc)
    cem = Cemetery(root=os.path.abspath(root), generated=now,
                   dead_days=dead_days)
    for path in find_repos(root, depth=depth):
        p = read_project(path, now)
        if p is None:
            continue
        classify(p, dead_days)
        if p.status == "deceased":
            p.cause = cause_of_death(p)
            p.factors = contributing_factors(p)
        cem.projects.append(p)
    assign_succession(cem.projects)
    cem.projects.sort(key=lambda p: p.died)
    return cem


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


def render_terminal(cem):
    out = []
    out.append("")
    out.append("=" * 64)
    out.append("  DEAD PROJECTS SOCIETY")
    out.append("  The roll of the departed, read aloud once a year"
               " whether you like it or not.")
    out.append("=" * 64)
    out.append("  Grounds: %s" % cem.root)
    out.append("  Buried: %d   In a coma: %d   Still breathing: %d"
               % (len(cem.deceased), len(cem.coma), len(cem.alive)))
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
        for f in p.factors:
            out.append("  Contributing: %s" % f)
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
            "status": p.status,
            "cause_of_death": p.cause or None,
            "contributing_factors": p.factors,
            "survived_by": p.survived_by or None,
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
            "buried_commits": cem.buried_commits,
            "average_lifespan_days": round(cem.avg_lifespan, 1),
        },
        "projects": [pd(p) for p in cem.projects],
    }


# ---------------------------------------------------------------------------
# Rendering: Markdown obituaries
# ---------------------------------------------------------------------------


def render_markdown(cem):
    out = ["# Dead Projects Society", ""]
    out.append("Grounds: `%s`" % cem.root)
    out.append("")
    out.append("**Buried: %d** · In a coma: %d · Still breathing: %d · "
               "Commits buried: %d"
               % (len(cem.deceased), len(cem.coma), len(cem.alive),
                  cem.buried_commits))
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
        for f in p.factors:
            out.append("- Contributing: %s" % f)
        out.append("- %s" % p.survived_by)
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
Still breathing: {alive} &middot; Commits buried: {commits}</div>
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
        stones.append(
            '<div class="stone"><div class="rip">R.I.P.</div>'
            "<h2>%s</h2>"
            '<div class="dates">%s &ndash; %s<br>aged %s &middot; %d commits'
            "</div>"
            '<div class="words">&ldquo;%s&rdquo;</div>'
            '<div class="cause">%s</div>%s'
            '<div class="survived">%s</div></div>'
            % (esc(p.name), _fmt_date(p.born), _fmt_date(p.died),
               _lifespan_text(p), p.commits,
               esc(p.last_words or "(silence)"), esc(p.cause), factors,
               esc(p.survived_by)))
    extra = []
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
        commits=cem.buried_commits, stones="\n".join(stones),
        extra="\n".join(extra))


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
        stone = {
            "id": _site_slug(p.name),
            "name": p.name,
            "born": p.born.strftime("%Y"),
            "died": p.died.strftime("%Y"),
            "cause": _site_cause_tag(p.cause),
            "epitaph": p.last_words or "",
            "description": desc,
            "tech": [],
            "commits": p.commits,
            "died_full": p.died.date().isoformat(),
            "silence_days": p.silence_days,
        }
        url = _site_github_url(p.path)
        if url:
            stone["url"] = url
        stones.append(stone)
    return stones


def site_wards(cem):
    def entry(p):
        return {
            "id": _site_slug(p.name),
            "name": p.name,
            "silence_days": p.silence_days,
            "commits": p.commits,
        }
    return {
        "intensive_care": [entry(p) for p in cem.coma],
        "still_breathing": [entry(p) for p in cem.alive],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="dead-projects-society",
        description="A funeral for your abandoned side projects. Reads "
                    "git history locally and builds the graveyard.")
    ap.add_argument("path", nargs="?", default=".",
                    help="Folder to scan (default: current folder)")
    ap.add_argument("--days", type=int, default=DEFAULT_DEAD_DAYS,
                    help="Days of silence before a project is pronounced "
                         "dead (default: %d)" % DEFAULT_DEAD_DAYS)
    ap.add_argument("--depth", type=int, default=1,
                    help="How deep to look for repositories (default: 1)")
    ap.add_argument("--html", metavar="FILE",
                    help="Write a walkable HTML graveyard")
    ap.add_argument("--card", metavar="FILE",
                    help="Write an SVG share card")
    ap.add_argument("--out", metavar="FILE",
                    help="Write Markdown obituaries")
    ap.add_argument("--json", action="store_true",
                    help="Print the full report as JSON")
    ap.add_argument("--site", metavar="DIR",
                    help="Write projects.json and wards.json for the 3D "
                         "web graveyard into DIR")
    ap.add_argument("--version", action="version",
                    version="dead-projects-society %s" % VERSION)
    args = ap.parse_args(argv)

    if not os.path.isdir(args.path):
        print("No such folder: %s" % args.path, file=sys.stderr)
        return 2
    cem = build_cemetery(args.path, dead_days=args.days, depth=args.depth)
    if not cem.projects:
        print("No bodies found. No git repositories under %s."
              % cem.root)
        return 2

    if args.json:
        print(json.dumps(cemetery_dict(cem), indent=2))
    else:
        print(render_terminal(cem))
    if args.html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(render_html(cem))
        print("Graveyard written to %s" % args.html)
    if args.card:
        with open(args.card, "w", encoding="utf-8") as fh:
            fh.write(render_card(cem))
        print("Share card written to %s" % args.card)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(cem))
        print("Obituaries written to %s" % args.out)
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
        print("Web graveyard data written to %s" % args.site)
    return 0


if __name__ == "__main__":
    sys.exit(main())
