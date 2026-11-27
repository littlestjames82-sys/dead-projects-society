# Changelog

All notable changes to Dead Projects Society. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the Society
records its own history with the same care it gives everyone else's.

## [Unreleased]

### Added
- The `--site` export now writes `survey.json` beside the grounds
  data: when the grounds were surveyed, by which version, and the
  census. The web graveyard displays the survey line in its
  Registry, so a snapshot never passes itself off as the present.
- The Deep Autopsy Department (opt-in, code-aware): `--deep-autopsy`
  sends a bounded sample of each buried or at-rest project to Muse
  Ember for a structured autopsy cited to files and commits, with
  `--deep-dry-run`, a priced-before-it-is-made estimate, a spend
  ledger, and a hard budget guard (`--deep-budget`). Built for the
  Muse Ember Hackathon; the first live call lands when the model
  id is confirmed. The standard scan still never opens a file.

## [0.32.0] - 2026-11-27

Tier 3 of the cold-review fix pass, and the last of it: with this
release all twelve findings of the 2026-11-26 review of 0.30.0
have been addressed — ten confirmed outright, two in part (#6's
cited filenames did not exist; the gap did. #7's stated trigger
did not reproduce; the defect did, and was fixed in 0.31.0).

### Fixed
- The web burial no longer stops reading at 300 repositories.
  `fetchRepos` follows GitHub's pages to the end, so the oldest
  and deadest repos — the ones sorted last, and the ones the page
  exists to pronounce on — are examined like all the rest.
- A repository with no push record (GitHub returns a null
  `pushed_at`, e.g. for empty repos) is no longer dated 1970 and
  credited with some twenty thousand days of silence. It is
  counted and listed under its own "No Push Record" heading, and
  it takes no part in silence figures or in honours — the Coldest
  Case is now always a repo with a real last push.
- The Deep Autopsy sampler's walk is bounded while it walks, not
  after: at most 20,000 files are examined per project, traversal
  runs in sorted order, and only what the sample uses is retained
  (the first 200 tree paths in sorted order, and candidates for
  the 3 largest source files). The sample is unchanged — byte for
  byte — for any project under the ceiling, and deterministic
  above it; `stats` now reports `walk_truncated` when the ceiling
  was reached.

### Added
- CI now validates the web graveyard: a `site` job parses every
  `site/*.json`, syntax-checks `site/main.js` and `site/bury.js`,
  and runs the standalone node checks in `tests/bury.test.js`
  (pagination past three pages, null-`pushed_at` handling) on
  every push and pull request.

## [0.31.0] - 2026-11-26

The cold-review fix pass: an outside review of 0.30.0 found twelve
issues, ten confirmed outright and two in part; this release fixes
the Deep Autopsy trust findings and the whole `--diff` cluster.
No new ceremony — the Department's promises are now kept by
mechanism instead of by assumption.

### Fixed
- The Deep Autopsy budget is now a hard cap in fact. Every API
  request carries an explicit output limit (2,500 tokens); the
  preflight check reserves that maximum cost and refuses a call
  that would not fit whole inside the budget; a call whose usage
  goes unreported is charged at the cap rather than at a smaller
  assumed figure; and reported output above the cap is clamped to
  it in the ledger. Previously the request carried no output
  limit at all, and a single verbose answer could carry recorded
  spend past the budget the README called hard.
- Deep Autopsy pricing is per model. `muse-ember-1.0` rates are
  built in; any other `--deep-model` must supply
  `--deep-input-rate` and `--deep-output-rate` (USD per million
  tokens), and without known pricing the department refuses to
  call instead of silently pricing an unknown model at Ember
  rates.
- `--json` output is pure again: combined with `--deep-dry-run`,
  `--site`, `--certificates`, `--adoption-papers`, or any other
  output flag, stdout carries the JSON document alone and all
  status messages go to stderr.
- `--diff` state is saved only after every requested output has
  been generated, and saved atomically (temporary file plus
  replace). A run that failed on an unwritable output path
  previously recorded the visit anyway, and the changes it never
  reported were lost from the log for good.
- `--diff` snapshots are keyed by each project's full path, not
  its folder name, so two repositories that share a name no
  longer overwrite each other's record. State written by older
  versions (name-keyed) is read gracefully: unmatched projects
  are treated as newly born, never a crash.
- Reordering the same folders on the command line no longer
  makes `--diff` treat them as new grounds: the state key is
  derived from the sorted set of roots, while the display label
  keeps the order given.
- The Groundskeeper's Log now reports a grave as stirred when
  its commit count changes under the same last-commit date
  (same-day work, rewritten history), not only when the date
  moves.
- Git output is decoded with an explicit replacement policy, so
  non-UTF-8 bytes in a committed file — which reach the sampler
  through `git log -p` — can no longer abort a scan or a Deep
  Autopsy sampling with a UnicodeDecodeError.

### Added
- Every Deep Autopsy sample is swept for credential-looking
  strings (private key blocks, AWS access keys, GitHub tokens,
  `sk-` style keys, Bearer tokens, and `api_key` / `password` /
  `token` assignments) and redacted before it is shown or sent;
  the run reports how many secrets were swept per project.
- `--deep-dry-run` now prints the exact payload that would be
  sent, per project, after redaction — not just counts and a
  price.
- `--deep-exclude GLOB` (repeatable) keeps matching files out of
  the Deep Autopsy sample entirely, including out of the
  final-commits diff.

### Changed
- The README's "How it reads a life" now scopes its "your code
  is never read / no network" claim to the standard scan, with
  the Deep Autopsy named as the opt-in exception it is; the
  square share card likewise stops claiming code is never read
  on runs where a deep autopsy actually ran.

## [0.30.0] - 2026-11-25

### Added
- The formal certificates, framed: `--certificates DIR` now also
  issues each Death Certificate as a standalone SVG, the frameable
  copy, beside the HTML certificates it has written since v0.8.0.
  Dark grounds and gold rules in the manner of the Society's
  cards, the project's name in large type, its born and died
  dates with its lifespan, the place of death given as the
  grounds folder's name, the coroner's cause, its last words,
  and its commit count and author count entered as witnesses.
  A successor, where the record names one, is noted as survived
  by. At-rest projects receive a Certificate of Honourable
  Retirement in place of a death certificate; the still
  breathing and the intensive-care patients receive none.
- Every certificate carries the Society's seal, a ringed star
  turned by an angle seeded from the project's name, and a
  certificate number (DPS-<death year>-<four digits>) computed
  from the project's name and death date, so the same project
  carries the same seal and the same number on every visit, and
  the same grounds issue byte-identical certificates on every
  run. The JSON report gains a per-project `certificate`
  filename and a `certificates` count in the summary when the
  flag is used, and the `--site` export carries the certificates
  in a `certificates` folder alongside the grounds data.

## [0.29.0] - 2026-11-25

### Added
- `--house-awards` holds the House Awards: a ceremony for your
  own grounds, as the Obituary Awards on the site are a ceremony
  for the famous dead. One honour per category, and only where
  the record genuinely supports one: Longest Life and Briefest
  Life among the buried (the briefest asks at least one full day
  of life, so a same-day scaffold does not win by default), the
  Life's Work for the most commits, the Quietest Passing for the
  longest premortem silence, Most Likely to Rise on the Autopsy
  Department's revival verdict, the Elder among the still
  breathing, the Patient longest in intensive care, and the
  Comeback for a resurrection on the record. Each award carries
  a citation composed from the winner's own numbers. Ties are
  broken by name, a category with no qualifying project is
  omitted rather than padded, and the same grounds hold the
  same ceremony on every visit. The ceremony appears in the
  terminal report, the Markdown and HTML obituaries, and the
  JSON (`awards`), and the `--site` export now writes
  `house_awards.json` beside the other grounds data.

## [0.28.0] - 2026-11-25

### Added
- `--adoption-papers DIR` writes one ready-to-post adoption
  listing (Markdown) per buried or at-rest project into DIR,
  with an `index.md` of them all. Each listing is drawn from the
  project's own record: its identity (language, lifespan,
  commits), why it is offered (the coroner's cause, the length
  of the silence, its last words), the state of the estate (peak
  month and momentum from the autopsy, bus factor, the README
  and remote findings, dependency-era signals where present),
  and the revival outlook (the autopsy's verdict and the record
  in its favour). A project survived by a successor says so, so
  an adopter knows the elder line is what is on offer. The
  Terms of adoption are left blank for the owner to complete,
  under the Society's standing word: nobody's project is
  modified, claimed, or republished without its owner's
  authorization, and memorializing is always free. At-rest
  projects are filed as retirement transfers, not deaths. The
  still breathing and the intensive-care patients receive no
  papers; they are not being offered. The JSON gains an
  `adoption_papers` count and a per-project `adoption_listing`
  filename when the flag is used, and with `--site` the papers
  are written into the export folder as well. The same grounds
  produce byte-identical papers.

## [0.27.0] - 2026-11-25

### Added
- `--wrapped [YEAR]`: the Society's Year in Review for your own
  grounds. For the chosen year (this year, if none is named) it
  counts the projects born, the projects buried, and the
  resurrections, every commit that landed across the grounds,
  the busiest month, the longest and shortest lives that ended,
  and the cause the coroner wrote most often, closing with the
  oldest still-breathing survivor and the current intensive
  care census, labelled as the present and not the past. A
  project that rose twice in a year is entered once. A quiet
  year is reported as a quiet year; the Society invents
  nothing. The review joins the terminal report, the Markdown
  and HTML reports, and the JSON as `wrapped`, and writes a
  shareable SVG card, `wrapped-<year>.svg`, beside the other
  outputs. The `--site` export now also carries the current
  year's review as `wrapped.json`, ready for the web
  graveyard. The older `--wrapped-kit` keeps its narrower
  brief: the year, formally buried.

## [0.26.0] - 2026-11-25

### Added
- `--eulogy`: the full eulogy, composed for every buried or
  at-rest project and read aloud only on request. Each one is a
  short spoken-style paragraph woven from the record the scan
  already keeps: the project's dates and lifespan, its commit
  count, its brightest month, the coroner's verdict, its last
  words, the successor that replaced it, and any resurrection
  in its past. At-rest projects get a softer telling, because
  they finished rather than faded. The variety is seeded from
  the project's name, so repeat visits produce the identical
  text. The eulogy joins the terminal report as its own
  section, the Markdown and HTML obituaries, the JSON as
  `full_eulogy`, and the `--site` export as each stone's
  `eulogy`, ready for the web graveyard to display. Still
  metadata only: no file is opened, nothing leaves the machine.

## [0.24.0] — 2026-11-22

### Added
- `--exclude NAME` (repeatable): directories with that name are
  never entered during a scan, for vendored checkouts, mirrors,
  and other people's dead.
- CI now also runs the suite on macOS and Windows, so the grounds
  are proven on all three soils before the launch.

### Changed
- The package's Homepage link now points at the web graveyard
  itself, with the repository and issues one click further.

## [0.23.0] — 2026-11-22

### Added
- The HTML graveyard report carries the Groundskeeper's Log section
  when the run uses `--diff`, at parity with the terminal report
  and the JSON.
- The web graveyard's Public Grounds can be reordered: as buried,
  by longest silence, by most stars, or by name.

## [0.22.0] — 2026-11-21

### Added
- The HTML graveyard report now carries each stone's autopsy line
  (pace, momentum, revival verdict), at parity with the terminal
  report and the web graveyard.
- The Obituary Awards gained two Repository Wing honors: Most Stars
  on the Stone (Atom) and Buried Beside Its Parent (Nuclide).

## [0.21.0] — 2026-11-21

### Added
- `--fail-if-new-deaths`: with `--diff`, the CLI exits with code 3
  when the Groundskeeper's Log finds a death it has not reported
  before (newly buried since the last visit, or found already
  buried on a later one), so scripts and CI can react the moment
  something dies.
- The Bury demo's verdict card now carries its archived count, and
  the 3D grounds gained a Repository Wing sign where the archived
  repositories begin.

## [0.20.0] — 2026-11-21

### Added
- `--oneline`: one line per project (name, state, silence, cause)
  for quick scans and pipes.
- The graveyard's Registry search now searches the Public Grounds
  and the Wards as well as the personal graves, and Visit a random
  grave can land on a famous grave too.

## [0.19.0] — 2026-11-21

### Added
- `--adopt FILE`: adoption papers for the buried. One honest
  listing per project — cause, last words, the Society's revival
  assessment, what it needs — and a line for a new keeper to sign.
- The site export now carries full birth and death dates, and the
  graveyard shows an "On this day in the grounds" line in the
  Registry, computed from them.

## [0.18.0] — 2026-11-21

### Added
- Several folders can be scanned at once and merged into one
  cemetery. Succession is judged across the whole union: if the
  replacement was started in a different folder, the Society will
  still note the timing. Duplicate roots are deduplicated.

## [0.17.0] — 2026-11-21

### Added
- `--on-this-day`: death and birth anniversaries in the grounds,
  in the terminal report and the JSON.

## [0.16.0] — 2026-11-21

### Added
- `--square FILE`: a 1080x1080 card sized for social feeds.
- README install lines for `uvx` (try without installing) and `pipx`.

## [0.15.0] — 2026-11-21

### Added
- Certificates of Resurrection from `--certificates`, for projects
  that flatlined past the death line and committed again, living or
  fallen a second time.

## [0.14.0] — 2026-11-21

### Added
- Dependency-era signals in the autopsy (bump and migration commits,
  counted from messages alone) and the "Died maintaining" verdict.
- The Groundskeeper's Log (`--diff`): what changed in the grounds
  since the last visit — newly buried, risen, stirred, newly born.

## [0.13.0] — 2026-11-21

### Added
- Cemetery sections by era and by language, in the JSON summary and
  as Registry filters in the 3D graveyard. Division I of the roadmap
  is complete.

## [0.12.0] — 2026-11-21

### Added
- A deepened autopsy: peak month, momentum classification, and
  findings (pre-mortem silence, bus factor, missing paperwork), in
  the CLI, the JSON, and the grave panels of the 3D site.

## [0.11.0] — 2026-11-21

### Added
- Language detection from file names only (contents never opened),
  so the site's stones carry real tech data.
- `--wrapped-kit`: the year in the grounds — an HTML page, a card,
  and post-ready text.

## [0.10.0] — 2026-11-21

### Added
- `--badge FILE`: a shields-style badge with the state of your
  grounds, for a README.
- The Public Grounds doubled to 24 famous graves: the Graveyard of
  the Internet.

## [0.9.0] — 2026-11-21

### Added
- Monthly activity timelines (JSON, site export, autopsy sparkline,
  grave-panel chart).
- Four new verdicts: Died waiting, Killed by a rename, Died writing
  the manual, Died of a sequel.

## [0.8.0] — 2026-11-21

### Added
- The Hall of Infamy: the Shooting Star, the Crowd That Left, the
  Unknown Soldier, the Stutter.
- The Autopsy Department (`--autopsy`): pace, end pattern, and a
  revival verdict from metadata alone.
- Death Certificates (`--certificates`) and a certificate button on
  every grave panel.

## [0.7.0] — 2026-11-21

### Added
- PROJECT_WILL.md support: projects whose will says finished are
  **At Rest**, not buried; adoptable wills are noted; a will-named
  successor overrides the timing guess.
- The completion-signal verdict ("Finished, by the look of it").
- ROADMAP.md, reconciling the Society's five-division future.

## [0.6.0] — 2026-11-20

### Added
- HTML graveyard parity: eulogies, resurrection notes, the Honors.
- The Public Grounds and the Bury a GitHub user demo joined the site
  across 0.5–0.6 (famous graves, judged by public push dates).

## [0.5.0] — 2026-11-20

### Added
- Eulogies: three sentences per tombstone, composed from the record.

## [0.4.0] — 2026-11-20

### Added
- The Society's Honors: the Marathoner, the Mayfly, the Loudest
  Exit, the Coldest Case, the Phoenix.

## [0.3.0] — 2026-11-20

### Added
- Resurrection detection: flatlines past the death line that ended
  in a commit are counted, in every output.

## [0.2.0] — 2026-11-20

### Added
- `--site DIR` export for the 3D web graveyard; two new verdicts
  (Died in a refactor, Starved).

## [0.1.0] — 2026-11-20

### Added
- The Society opens its gates: folder scan, tombstones with last
  words and rule-based causes of death, contributing factors,
  survived-by, terminal / HTML / Markdown / JSON reports, and the
  SVG share card. Pure Python standard library, zero dependencies.
  It reads git metadata and file names only. Your code is never read.
