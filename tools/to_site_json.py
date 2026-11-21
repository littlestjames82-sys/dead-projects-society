#!/usr/bin/env python3
"""Convert Dead Projects Society --json output into site/projects.json.

Usage:
    dead-projects-society ~/projects --json > cemetery.json
    python3 tools/to_site_json.py cemetery.json site/projects.json

Only the deceased are buried. The epitaph is the project's last words,
the description is composed from the coroner's report, and the URL is
taken from the repo's origin remote when it points at GitHub (edit the
result freely; projects.json is yours).
"""

import json
import os
import re
import subprocess
import sys


def cause_tag(cause):
    if not cause:
        return "Cause unknown"
    tag = cause.split(".")[0].strip()
    return tag[:1].upper() + tag[1:]


def github_url(path):
    try:
        out = subprocess.run(
            ["git", "-C", path, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10)
    except OSError:
        return None
    url = (out.stdout or "").strip()
    if not url:
        return None
    m = re.match(r"git@github\.com:(.+?)(?:\.git)?$", url)
    if m:
        return "https://github.com/" + m.group(1)
    if url.startswith("https://github.com/"):
        return url[:-4] if url.endswith(".git") else url
    return None


def convert(data):
    stones = []
    for p in data.get("projects", []):
        if p.get("status") != "deceased":
            continue
        born = p["born"][:4]
        died = p["died"][:4]
        life = p["lifespan_days"]
        life_text = ("%d day" % life if life == 1 else
                     "%d days" % life if life < 60 else
                     "%d months" % round(life / 30.44) if life < 730 else
                     "%.1f years" % (life / 365.25))
        desc = "%d commits over %s. %s" % (p["commits"], life_text,
                                           p.get("cause_of_death") or "")
        for f in p.get("contributing_factors") or []:
            desc += " " + f
        if p.get("survived_by"):
            desc += " " + p["survived_by"]
        stone = {
            "id": re.sub(r"[^a-z0-9-]+", "-", p["name"].lower()).strip("-"),
            "name": p["name"],
            "born": born,
            "died": died,
            "cause": cause_tag(p.get("cause_of_death")),
            "epitaph": p.get("last_words") or "",
            "description": desc,
            "tech": [],
            "commits": p["commits"],
        }
        url = github_url(p["path"])
        if url:
            stone["url"] = url
        stones.append(stone)
    return stones


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    with open(sys.argv[1], encoding="utf-8") as fh:
        data = json.load(fh)
    stones = convert(data)
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        json.dump(stones, fh, indent=2)
        fh.write("\n")
    print("Wrote %d tombstone(s) to %s" % (len(stones), sys.argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
