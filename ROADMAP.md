# Dead Projects Society 2.0 — Roadmap

*Adopted November 21, 2026, from Ryan's review of the 2.0 vision. This
document reconciles that vision with what is already built, and sequences
the rest honestly.*

**Vision:** the destination for abandoned software. Every project deserves
a proper obituary. Some deserve a second life.

**Principles (do not trade away):**
- The local CLI reads git metadata only. It never reads your code and
  never uploads anything. Any deeper analysis is a separate, opt-in mode.
- Memorializing a project is always free.
- The cemetery works on its own. AI is an added capability, never a
  dependency.
- Nobody's project is modified, claimed, or republished without its
  owner's authorization.

## The five divisions

### I. The Graveyard — SHIPPED, improving
The CLI, the verdicts, the 3D cemetery.
- [x] Local scan, pulse bands, coroner verdicts, last words, successors
- [x] Resurrection detection and the Society's Honors
- [x] Terminal, Markdown, HTML, JSON, SVG card outputs
- [x] 3D cemetery: personal grounds, the Wards, Terminal mode
- [x] The Public Grounds: famous graves (shipped Nov 21, 2026)
- [x] Bury a GitHub user: web demo (shipped Nov 21, 2026)
- [x] Hall of Infamy: the Honors pointed the other way (site + CLI,
      v0.8.0)
- [x] Death Certificates: the formal, frameable artifact (v0.8.0)
- [x] Cemetery sections by language and era (language detection
      v0.11.0; Registry section filters and the JSON sections summary
      v0.13.0)
- [x] Certificates of Resurrection: the return, on the record
      (v0.15.0)
- [x] The square card, 1080x1080, for social feeds (v0.16.0), and a
      downloadable verdict card on the Bury demo itself
- [x] On This Day in the Grounds: death and birth anniversaries
      (v0.17.0)
- [x] Several folders, one cemetery: multi-root scans with
      succession judged across the union (v0.18.0)
- [x] The Obituary Awards: year-end honors for the famous dead
      (site, Nov 21, 2026)

### II. The Autopsy Department — SHIPPED (metadata edition)
Why did it die, and what would revival take? Evidence-based, and careful
about the Society's oldest mistake: silence is not abandonment.
- [x] Finished, not dead: completion verdicts and At Rest (CLI v0.7.0)
- [x] The Project Will: an owner leaves a PROJECT_WILL.md; the Society
      honors it (CLI v0.7.0)
- [x] Autopsy report from metadata: patterns of decline (peak month,
      momentum), bus factor, README and remote neglect (v0.8.0,
      deepened v0.12.0)
- [x] Dependency-era signals from the commit record (v0.14.0), and
      the Groundskeeper's Log: --diff between visits (v0.14.0)
- [x] The opt-in deep autopsy (code-aware) as a separate mode: sampler, budget ledger, and Ember client built Nov 23, 2026 for the Muse Ember Hackathon; first live call waits on hackathon selection and credits

### III. The Resurrection Department — LATER
AI-assisted revival under governance: isolated workspace, autopsy first,
a plan the owner approves, repairs by governed agents, verification, and
a resurrection certificate. Ghost Developer Studio supplies the
intelligence; the Society stays standalone. Requires the Autopsy
Department and an audience asking for it.

### IV. The Society — LATER
Members, submissions, adoption applications, competitions (Phoenix
Award, Lazarus Challenge, Digital Archaeologist), rankings, stories.
Requires the public platform work in the Afterlife Network and people
to compete.

### V. The Afterlife Network — LATER
Public API, embeddable badges, the adoption marketplace, the historical
archive (the Graveyard of the Internet: discontinued apps, frameworks,
APIs, games), preservation services. Requires accounts and hosting,
which are Ryan's spending and identity decisions, not engineering ones.

## Sequence from here
1. Launch the current product (PyPI + posts). An audience is the input
   every later division consumes.
2. Autopsy Department, metadata edition (v0.7.0 and following).
3. Hall of Infamy and Death Certificates on the site.
4. Revisit the platform divisions with real usage numbers in hand.
