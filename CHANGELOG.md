# Changelog

All notable changes to Dead Projects Society. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the Society
records its own history with the same care it gives everyone else's.

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
