# Dead Projects Society

[![PyPI](https://img.shields.io/pypi/v/dead-projects-society)](https://pypi.org/project/dead-projects-society/)
[![Downloads](https://static.pepy.tech/badge/dead-projects-society)](https://pepy.tech/project/dead-projects-society)

**A funeral for your abandoned side projects.**

![Dead Projects Society reading the roll of the departed](https://raw.githubusercontent.com/littlestjames82-sys/dead-projects-society/main/assets/demo.gif)

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

Beyond the personal rows stand the **Public Grounds**: 55 famous
graves, the products the internet has lost (Google Reader, Vine,
Napster, Skype) and a Repository Wing of archived repositories
(Atom, AngularJS, PhantomJS), every one verified before burial.
And if you would like a verdict on a GitHub account instead of a
folder, the Society will **[bury a GitHub user](https://littlestjames82-sys.github.io/dead-projects-society/bury.html)**
by public push dates, archived paperwork included.

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

Try it without installing anything (needs [uv](https://docs.astral.sh/uv/)):

```bash
uvx dead-projects-society ~/projects
```

Or keep it (needs [pipx](https://pipx.pypa.io/)):

```bash
pipx install dead-projects-society
```

Or the classic way:

```bash
pip install dead-projects-society
```

Shell completions for bash and zsh live in the repository's
`completions/` folder, generated from the CLI's own flag list.

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
  verdict with its reasons, all from the record alone. The deepened
  report reads the shape of the life: the peak month and its share of
  all commits, the momentum (one bright burst, front-loaded, late
  surge, interrupted, steady burn), the longest premortem silence, and
  the neglect findings: no README, no remote, a bus factor of one. The
  same notes appear on each grave in the 3D cemetery.
- `--certificates DIR` issues a formal **Certificate of Death** (or of
  Completion, for the finished) for every project that earned one, and
  a **Certificate of Resurrection** for every project that flatlined
  past the death line and committed again, whether it is living still
  or fell a second time. The return is on the record. The same flag
  also issues the formal certificate as a **standalone SVG**, the
  frameable copy: dark grounds, gold rules, the project's dates,
  lifespan, and place of death, the coroner's cause and its last
  words, its commits and authors entered as witnesses, the Society's
  seal turned by an angle seeded from the project's name, and a
  certificate number computed from the name and the death date, so
  the same project carries the same number on every visit. The
  finished receive a **Certificate of Honourable Retirement** in the
  same form; the living receive nothing.
- `--badge FILE` writes a shields-style badge with the state of your
  grounds, for a README.
- `--square FILE` writes a 1080x1080 card sized for social feeds (the
  `--card` SVG stays the wide link-preview size).
- `--on-this-day` appends the anniversaries: projects that died on
  this month and day in an earlier year, and projects born on it. A
  reason to visit the grounds more than once.
- `--eulogy` composes **the full eulogy** for every buried or
  at-rest project: a short spoken-style paragraph woven from the
  life itself, its dates and commit count, its brightest month,
  the coroner's verdict, its last words, the successor that
  replaced it, and any resurrection on its record. At-rest
  projects are spoken of softly; they finished, they were not
  abandoned. The wording varies by project but is seeded from the
  project's name, so the same project receives the same eulogy on
  every visit. It appears in the terminal report, the Markdown and
  HTML obituaries, the JSON (`full_eulogy`), and the `--site`
  export, and only when the flag is given: a eulogy is read aloud
  on request, not by default.
- `--house-awards` holds **the House Awards**: a ceremony for
  your own grounds, one honour per category the record
  genuinely supports. Longest Life and Briefest Life among the
  buried, the Life's Work for the most commits, the Quietest
  Passing for the longest premortem silence, Most Likely to
  Rise on the Autopsy Department's revival verdict, the Elder
  among the still breathing, the Patient longest in intensive
  care, and the Comeback for a resurrection on the record. Each
  citation is composed from the winner's own numbers, ties are
  broken by name, and a category with no qualifying project is
  omitted, never padded. Not to be confused with the **Obituary
  Awards** on the site, which honour the famous dead; the House
  Awards are for the grounds in front of you. The ceremony
  appears in the terminal report, the Markdown and HTML
  obituaries, and the JSON (`awards`), and the `--site` export
  carries it as `house_awards.json`.
- `--wrapped [YEAR]` appends **the Society's Year in Review**:
  for the year you name (or this year), it counts the projects
  born, buried, and resurrected, every commit that landed across
  the grounds, the busiest month, the longest and shortest lives
  that ended, and the cause the coroner wrote most often, then
  closes with the oldest still-breathing survivor. A quiet year
  is reported as a quiet year. The review appears in the
  terminal, Markdown, and HTML reports and the JSON (`wrapped`),
  and writes a shareable SVG card, `wrapped-<year>.svg`, beside
  the other outputs.
- Several folders can be named at once; they are merged into one
  cemetery, and succession is judged across all of them. If the
  replacement was started in a different folder, the Society will
  still note the timing.
- `--adopt papers.md` writes adoption papers for the buried: one
  honest listing per project, its assessment, what it needs, and a
  line for a new keeper to sign.
- `--adoption-papers DIR` writes **one ready-to-post adoption
  listing per project** into DIR, with an index: the project's
  identity, why it is offered, the state of the estate, and the
  revival outlook, all drawn from its own record, a note where a
  successor exists, and Terms of adoption left blank for the
  owner to complete. At-rest projects are filed as retirement
  transfers. The still breathing and the intensive-care patients
  get no papers; they are not being offered.
- `--oneline` prints one line per project (name, state, silence,
  cause) for quick scans and pipes; the full report remains the
  ceremony.
- The HTML graveyard report carries each stone's autopsy line
  (pace, momentum, revival verdict), at parity with the terminal
  report and the web graveyard.
- The HTML graveyard report also carries the Groundskeeper's Log
  when the run uses `--diff`.
- `--deep-autopsy` (opt-in, the one code-aware mode): a bounded
  sample of each buried project (README, manifests, largest source
  files, final diffs) goes to Muse Ember, which writes a structured
  autopsy cited to files and commits. The budget cap is a hard
  cap, mechanically: every request carries an explicit output
  limit (2,500 tokens), the preflight check reserves that maximum
  cost at the model's rates and refuses any call that would not
  fit whole inside `--deep-budget` (default $10), and a call whose
  usage goes unreported is charged at the cap, never at a smaller
  assumption. Every call is recorded in a spend ledger. Pricing is
  per model: `muse-ember-1.0` is built in ($0.10 in / $0.50 out
  per million tokens); any other `--deep-model` must bring its own
  prices via `--deep-input-rate` and `--deep-output-rate` (USD per
  million tokens), or the department refuses to call — a guard
  priced at the wrong model's rates is not a guard. Before a
  sample is shown or sent it is swept for credential-looking
  strings (private keys, AWS keys, GitHub tokens, `api_key = ...`
  assignments, and friends), which are redacted and counted.
  `--deep-exclude GLOB` (repeatable) keeps matching files out of
  the sample entirely, diffs included. `--deep-dry-run` assembles
  the samples, prints the prices, and prints the **exact payload
  that would be sent**, after redaction, without calling. The
  standard scan never opens a file; this mode exists only
  because you asked, in so many flags.
- `--exclude NAME` (repeatable) keeps directories out of the scan:
  vendored checkouts, mirrors, other people's dead.
- `--fail-if-new-deaths`, with `--diff`, exits with code 3 when the
  Groundskeeper's Log finds a death it has not reported before: a
  project newly buried since the last visit, or one found already
  buried on a later visit. A script or a CI job can be told the
  moment something dies.
- `--wrapped-kit DIR` builds the year in review: an HTML page, an SVG
  card, and post-ready text covering everything of yours that ended in
  the year (`--year` picks which).
- The cemetery keeps **sections**: the JSON report counts the buried
  by era and by language, and the 3D cemetery's Registry can section
  the grounds the same way, by the decade a project died in or the
  language it was written in.
- The autopsy reads **dependency-era signals** from the commit record:
  how much of a life was bumps, upgrades, and migrations. A project
  whose final chapter is mostly upkeep earns the verdict it deserves:
  *Died maintaining.*
- `--diff` keeps the **Groundskeeper's Log**: run it against the same
  grounds over time and it reports what changed since your last visit:
  newly buried, newly at rest, risen, stirred in their graves, newly
  born. A grave counts as stirred when its commit count changes, even
  under the same last-commit date. Visits are recorded locally in
  `~/.dead-projects-society/state.json` (or `--state FILE`), keyed by
  each project's full path (two repositories that share a folder name
  are two different graves) and by the grounds themselves regardless
  of the order you list the folders in. The visit is written only
  after every requested report has been generated, and written
  atomically, so a failed run never consumes changes it did not
  report.
- The **HTML graveyard** is a single self-contained page of tombstones
  you can open, host, or send to a friend who also has a folder like yours.
- The **SVG card** is the shareable summary: buried count, commits buried,
  longest silence.

## How it reads a life

The standard scan reads only git metadata: commit dates, messages, author
count, whether a README or a remote exists, and file *names* (counted by
extension to name a project's language, never opened). **In the standard
scan, your code is never read**, everything runs locally, read-only, with
zero dependencies and no network. The one exception is the opt-in Deep
Autopsy (`--deep-autopsy`, above): only when you ask for it, in so many
flags, a bounded sample of a buried project's files is assembled locally,
swept for secrets, and sent to the model API. Pure Python standard
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
Changes are recorded in the [CHANGELOG](https://github.com/littlestjames82-sys/dead-projects-society/blob/main/CHANGELOG.md); the Society
keeps its own record as carefully as everyone else's.

## Also from Ghost Developer Studio

The Society judges the projects. Its sister tools judge the rest:

- **PIP**: reviews the developer from their own git history, with grades and a report card. `pip install on-a-pip`
- **Snap Judgment**: judges your screenshots folder from file metadata only, with a courtroom verdict. `pip install snap-judgment`
- **Ghost Hands**: governed browser automation for AI agents, with every action classified, policy checked, and trailed. `pip install ghost-hands`
- **Agent Seatbelt**: guardrails for AI coding agents, gating tool calls before they run. `pip install ghost-seatbelt`
