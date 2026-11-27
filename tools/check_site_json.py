#!/usr/bin/env python3
"""Validate the web graveyard's checked-in data files.

Every site/*.json file must parse as JSON; the site renders
straight from these files, so a broken one is a broken page.
Standard library only. Exit 0 when all parse, 1 otherwise.
"""
import glob
import json
import os
import sys


def main():
    site = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "site")
    files = sorted(glob.glob(os.path.join(site, "*.json")))
    if not files:
        print("no site JSON files found", file=sys.stderr)
        return 1
    bad = 0
    for path in files:
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as fh:
                json.load(fh)
        except (OSError, ValueError) as exc:
            print("INVALID %s: %s" % (name, exc), file=sys.stderr)
            bad += 1
        else:
            print("ok %s" % name)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
