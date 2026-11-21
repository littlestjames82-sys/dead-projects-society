# Dead Projects Society

**A funeral for your abandoned side projects.**

Point it at the folder where your projects go to die. It reads each git
repository's history and builds a graveyard: a tombstone for every project
that has gone silent, with its lifespan, its **last words** (the final
commit message, which is always something like `wip` or `almost done`), a
**cause of death**, and the successor project that was born suspiciously
soon after it died.

Projects still showing a pulse are listed under *Still Breathing*. The
Society does not bury the living.

```
----------------------------------------------------------------
  R.I.P.  weather-app-2
  Jan 03, 2025 to Jan 19, 2025  (aged 16 days, 23 commits)
  Last words: "final fix for real this time"
  Cause of death: New Year's resolution. You know how those go.
  Contributing: No README. Nobody knew what it was for, including,
  eventually, its author.
  Survived by shiny-new-idea, born 2 days later. The Society notes
  the timing.
```

## Walk the grounds

The Society keeps a **3D graveyard** on the web: a Three.js cemetery where
every buried project gets a stone you can click to read its story.

**[Enter the graveyard](https://littlestjames82-sys.github.io/dead-projects-society/)**

The stones there are generated from a real run. To raise your own, feed the
CLI's JSON through the converter and drop the result in `site/projects.json`:

```bash
dead-projects-society ~/projects --json > cemetery.json
python3 tools/to_site_json.py cemetery.json site/projects.json site/wards.json
```

The optional `wards.json` fills the side wards: small stones under an
INTENSIVE CARE sign for projects in a coma, and a STILL BREATHING corner for
the ones still alive. Every grave also gets a deep link
(`#grave=<id>`) and a Share button in its panel.

## Install

```bash
pip install dead-projects-society
```

Or run it straight from a checkout, no install needed:

```bash
PYTHONPATH=. python3 dead_projects_society.py ~/projects
```

## Usage

```bash
dead-projects-society ~/projects            # bury the folder's dead
dead-projects-society . --days 30           # pronounce death sooner
dead-projects-society ~/code --depth 2      # look deeper for bodies
dead-projects-society ~/projects --html graveyard.html
dead-projects-society ~/projects --card card.svg
dead-projects-society ~/projects --out obituaries.md
dead-projects-society ~/projects --json
dead-projects-society ~/projects --site site/   # feed the 3D graveyard
```

- A project silent **30 days or less** is alive. **31 to 90 days** puts it
  in intensive care. Past that, it gets a tombstone. `--days` moves the
  line.
- Projects that flatlined past the death line and then committed again are
  listed as **back from the dead**, with their longest flatline on record.
  Even the buried ones confess their earlier resurrections.
- Every report ends with **the Society's Honors**: the Marathoner, the
  Mayfly, the Loudest Exit, the Coldest Case, and, when one exists, the
  Phoenix. Awarded without appeal.
- Silence is not abandonment. A project whose last words read like a
  farewell gets the verdict **Finished, by the look of it**, and a project
  that left a **Project Will** is honored exactly as written:

  ```markdown
  # PROJECT_WILL.md
  Status: complete        (or: adoptable)
  Successor: new-project  (who carries the work on)
  Note: It did everything it was ever going to do.
  ```

  A will that says *complete* moves the project to **At Rest**: finished,
  not dead, and the Society does not bury the finished. A will that says
  *adoptable* stays buried, with the appeal for a new keeper on record.
- The **Hall of Infamy** keeps the other ledger: the Shooting Star, the
  Crowd That Left, the Unknown Soldier, the Stutter.
- `--autopsy` opens the **Autopsy Department**: for every buried or
  at-rest project, the pace it lived at, how it ended, and a revival
  verdict with its reasons, all from the record alone.
- `--certificates DIR` issues a formal **Certificate of Death** (or of
  Completion, for the finished) for every project that earned one.
- The **HTML graveyard** is a single self-contained page of tombstones
  you can open, host, or send to a friend who also has a folder like yours.
- The **SVG card** is the shareable summary: buried count, commits buried,
  longest silence.

## How it reads a life

Only git metadata: commit dates, messages, author count, whether a README
or a remote exists. **Your code is never opened.** Everything runs locally,
read-only, with zero dependencies and no network. Pure Python standard
library, Python 3.9+.

Causes of death are determined by a small, very judgmental coroner:
one-commit wonders, weekend flings, projects that died mid-sentence on a
`wip`, New Year's resolutions, sudden cardiac arrests after hundreds of
commits, projects that died in a refactor, projects that starved on a
commit every few weeks, cold cases silent for two years, and more.

## The Society's rules

1. The Society does not bury the living.
2. The successor's timing is always noted.
3. Everyone's folder looks like this. Everyone's.

## License

MIT. By [Ghost Developer Studio](https://ghostdeveloperstudio.com).

*See also: [PIP](https://github.com/littlestjames82-sys/pip-pip), which
reviews the developer, and [Snap Judgment](https://github.com/littlestjames82-sys/snap-judgment),
which judges the screenshots folder. The Society judges the projects.*
