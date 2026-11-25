import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import dead_projects_society as dps

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_repo(path, commits, readme=False, remote=False):
    """commits: list of (iso_date, message)."""
    os.makedirs(path, exist_ok=True)
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1")
    def run(*args, date=None):
        e = dict(env)
        if date:
            if date.endswith("Z"):
                date = date[:-1] + "+00:00"
            elif "+" not in date and date.count("-") == 2:
                date = date + "+00:00"
            e["GIT_AUTHOR_DATE"] = date
            e["GIT_COMMITTER_DATE"] = date
        subprocess.run(["git", "-C", path, *args], env=e, check=True,
                       capture_output=True, text=True)
    run("init", "-b", "main")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test Author")
    if readme:
        with open(os.path.join(path, "README.md"), "w") as fh:
            fh.write("# fixture\n")
        run("add", "README.md")
        run("commit", "-m", "add readme", date=commits[0][0])
        commits = commits[1:]
    for date, msg in commits:
        run("commit", "--allow-empty", "-m", msg, date=date)
    if remote:
        run("remote", "add", "origin", "https://example.com/x.git")
    return path


class FixtureBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dps-test-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestDiscovery(FixtureBase):
    def test_finds_subdir_repos(self):
        make_repo(os.path.join(self.tmp, "alpha"),
                  [("2025-01-01T10:00:00", "start")])
        make_repo(os.path.join(self.tmp, "beta"),
                  [("2025-01-01T10:00:00", "start")])
        os.makedirs(os.path.join(self.tmp, "not-a-repo"))
        found = dps.find_repos(self.tmp, depth=1)
        self.assertEqual(len(found), 2)

    def test_root_itself_is_a_repo(self):
        make_repo(self.tmp, [("2025-01-01T10:00:00", "start")])
        found = dps.find_repos(self.tmp, depth=1)
        self.assertEqual(found, [os.path.abspath(self.tmp)])

    def test_hidden_dirs_skipped(self):
        make_repo(os.path.join(self.tmp, ".secret"),
                  [("2025-01-01T10:00:00", "start")])
        self.assertEqual(dps.find_repos(self.tmp, depth=1), [])


class TestReading(FixtureBase):
    def test_reads_history(self):
        p = make_repo(os.path.join(self.tmp, "proj"), [
            ("2025-03-01T10:00:00", "first breath"),
            ("2025-03-05T10:00:00", "middle"),
            ("2025-03-09T10:00:00", "last gasp"),
        ])
        proj = dps.read_project(p, NOW)
        self.assertEqual(proj.commits, 3)
        self.assertEqual(proj.first_words, "first breath")
        self.assertEqual(proj.last_words, "last gasp")
        self.assertEqual(proj.lifespan_days, 8)
        self.assertEqual(proj.name, "proj")

    def test_empty_repo_ignored(self):
        p = os.path.join(self.tmp, "empty")
        os.makedirs(p)
        subprocess.run(["git", "-C", p, "init", "-b", "main"],
                       check=True, capture_output=True)
        self.assertIsNone(dps.read_project(p, NOW))


class TestCoroner(FixtureBase):
    def build(self, specs, days=90):
        for name, commits, kw in specs:
            make_repo(os.path.join(self.tmp, name), commits, **kw)
        return dps.build_cemetery(self.tmp, dead_days=days, now=NOW)

    def test_one_commit_wonder(self):
        cem = self.build([("solo", [("2025-01-01T10:00:00", "init")], {})])
        p = cem.deceased[0]
        self.assertIn("One-commit wonder", p.cause)

    def test_same_day(self):
        cem = self.build([("flash", [
            ("2025-05-01T09:00:00", "born"),
            ("2025-05-01T22:00:00", "done"),
        ], {})])
        self.assertIn("same day", cem.deceased[0].cause)

    def test_died_mid_sentence(self):
        cem = self.build([("unfinished", [
            ("2025-05-01T09:00:00", "real work"),
            ("2025-05-20T09:00:00", "wip"),
        ], {})])
        self.assertIn("mid-sentence", cem.deceased[0].cause)

    def test_died_in_a_merge(self):
        cem = self.build([("merged", [
            ("2025-05-01T09:00:00", "real work"),
            ("2025-05-12T09:00:00", "Merge pull request #3 from x/y"),
        ], {})])
        self.assertIn("Died in a merge", cem.deceased[0].cause)

    def test_new_years_resolution(self):
        cem = self.build([("resolution", [
            ("2025-01-02T09:00:00", "new year new me"),
            ("2025-01-20T09:00:00", "gym stuff"),
        ], {})])
        self.assertIn("New Year's resolution", cem.deceased[0].cause)

    def test_cardiac_arrest(self):
        commits = [("2025-02-%02dT09:00:00" % (1 + i % 27), "work %d" % i)
                   for i in range(101)]
        commits.sort()
        cem = self.build([("marathon", commits, {})])
        self.assertIn("cardiac arrest", cem.deceased[0].cause)

    def test_alive_not_buried(self):
        cem = self.build([("living", [
            ("2025-12-20T09:00:00", "recent"),
            ("2025-12-30T09:00:00", "yesterday-ish"),
        ], {})])
        self.assertEqual(len(cem.deceased), 0)
        self.assertEqual(len(cem.alive), 1)

    def test_coma_band(self):
        cem = self.build([("sleeping", [
            ("2025-10-01T09:00:00", "start"),
            ("2025-11-15T09:00:00", "last sign"),
        ], {})])
        self.assertEqual(len(cem.coma), 1)
        self.assertEqual(cem.coma[0].cause, "")

    def test_succession(self):
        cem = self.build([
            ("old-thing", [
                ("2025-03-01T09:00:00", "start"),
                ("2025-03-10T09:00:00", "the end"),
            ], {}),
            ("shiny-new", [
                ("2025-03-15T09:00:00", "hello world"),
                ("2025-12-01T09:00:00", "still going"),
            ], {}),
        ])
        dead = cem.deceased[0]
        self.assertIn("shiny-new", dead.survived_by)
        self.assertIn("5 days later", dead.survived_by)

    def test_factors(self):
        cem = self.build([("bare", [
            ("2025-04-01T09:00:00", "a"),
            ("2025-04-02T09:00:00", "b"),
        ], {})])
        f = " ".join(cem.deceased[0].factors)
        self.assertIn("No README", f)
        self.assertIn("Never left the house", f)


class TestRendering(FixtureBase):
    def setUp(self):
        super().setUp()
        make_repo(os.path.join(self.tmp, "gone"), [
            ("2025-02-01T09:00:00", "ambitious start"),
            ("2025-02-03T09:00:00", "wip"),
        ], readme=True, remote=True)
        self.cem = dps.build_cemetery(self.tmp, now=NOW)

    def test_terminal(self):
        text = dps.render_terminal(self.cem)
        self.assertIn("R.I.P.  gone", text)
        self.assertIn("DEAD PROJECTS SOCIETY", text)

    def test_json_round_trip(self):
        data = json.loads(json.dumps(dps.cemetery_dict(self.cem)))
        self.assertEqual(data["summary"]["buried"], 1)
        self.assertEqual(data["projects"][0]["name"], "gone")

    def test_html(self):
        html = dps.render_html(self.cem)
        self.assertIn("R.I.P.", html)
        self.assertIn("gone", html)
        self.assertIn("</html>", html)

    def test_card_is_svg(self):
        card = dps.render_card(self.cem)
        self.assertTrue(card.startswith("<svg"))
        self.assertTrue(card.endswith("</svg>"))

    def test_markdown(self):
        md = dps.render_markdown(self.cem)
        self.assertIn("## R.I.P. gone", md)
        self.assertIn("Cause of death:", md)


class TestCli(FixtureBase):
    def test_no_repos_exit_2(self):
        rc = dps.main([self.tmp])
        self.assertEqual(rc, 2)

    def test_missing_dir_exit_2(self):
        rc = dps.main([os.path.join(self.tmp, "nope")])
        self.assertEqual(rc, 2)

    def test_json_flag_runs(self):
        make_repo(os.path.join(self.tmp, "gone"), [
            ("2025-02-01T09:00:00", "a"),
            ("2025-02-03T09:00:00", "b"),
        ])
        rc = dps.main([self.tmp, "--json"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()


class TestNewCauses(FixtureBase):
    def test_died_in_a_refactor(self):
        commits = [("2025-01-05T10:00:00", "start")]
        for i in range(10):
            commits.append(("2025-0%d-15T10:00:00" % (i % 9 + 1),
                            "feature %d" % i))
        commits.append(("2025-06-01T10:00:00", "big refactor of the core"))
        make_repo(os.path.join(self.tmp, "refactored"), commits)
        cem = dps.build_cemetery(self.tmp, dead_days=90, depth=1)
        self.assertEqual(len(cem.deceased), 1)
        self.assertTrue(cem.deceased[0].cause.startswith("Died in a refactor"))

    def test_starved(self):
        make_repo(os.path.join(self.tmp, "starved"), [
            ("2025-01-01T10:00:00", "start"),
            ("2025-03-01T10:00:00", "a little more"),
            ("2025-05-01T10:00:00", "small step"),
            ("2025-06-15T10:00:00", "tiny tweak"),
            ("2025-08-01T10:00:00", "another small step"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, depth=1)
        self.assertEqual(len(cem.deceased), 1)
        self.assertTrue(cem.deceased[0].cause.startswith("Starved"))


class TestSiteExport(FixtureBase):
    def test_site_export_writes_both_files(self):
        make_repo(os.path.join(self.tmp, "gone"), [
            ("2024-01-01T10:00:00", "start"),
            ("2024-02-01T10:00:00", "last gasp"),
        ])
        make_repo(os.path.join(self.tmp, "sleepy"), [
            ("2026-11-01T10:00:00", "recent start"),
            ("2026-11-10T10:00:00", "still going"),
        ])
        outdir = os.path.join(self.tmp, "site-data")
        rc = dps.main([self.tmp, "--site", outdir])
        self.assertEqual(rc, 0)
        stones = json.load(open(os.path.join(outdir, "projects.json")))
        wards = json.load(open(os.path.join(outdir, "wards.json")))
        self.assertEqual([s["name"] for s in stones], ["gone"])
        self.assertEqual(stones[0]["cause"], "New Year's resolution")
        self.assertEqual(stones[0]["epitaph"], "last gasp")
        self.assertIn("silence_days", stones[0])
        names_icu = [e["name"] for e in wards["intensive_care"]]
        names_alive = [e["name"] for e in wards["still_breathing"]]
        self.assertEqual(names_icu + names_alive, ["sleepy"])


class TestResurrections(FixtureBase):
    def test_deceased_with_a_past_resurrection(self):
        make_repo(os.path.join(self.tmp, "phoenix"), [
            ("2025-01-01T10:00:00", "start"),
            ("2025-01-10T10:00:00", "going strong"),
            ("2025-06-01T10:00:00", "I am back"),   # 142-day flatline
            ("2025-06-05T10:00:00", "final words"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, depth=1)
        self.assertEqual(len(cem.deceased), 1)
        p = cem.deceased[0]
        self.assertEqual(p.resurrections, 1)
        self.assertEqual(p.longest_flatline, 142)
        self.assertIn("BACK FROM THE DEAD", dps.render_terminal(cem))
        data = dps.cemetery_dict(cem)
        self.assertEqual(data["summary"]["back_from_the_dead"], 1)
        self.assertEqual(data["projects"][0]["resurrections"], 1)

    def test_alive_project_that_came_back(self):
        make_repo(os.path.join(self.tmp, "boomerang"), [
            ("2025-01-01T10:00:00", "start"),
            ("2025-05-20T10:00:00", "returned"),    # 139-day flatline
            ("2026-11-15T10:00:00", "current work"),  # after a 544-day one
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, depth=1)
        self.assertEqual(len(cem.alive), 1)
        self.assertEqual(cem.alive[0].resurrections, 2)
        self.assertEqual(cem.alive[0].longest_flatline, 544)

    def test_short_gaps_do_not_count(self):
        make_repo(os.path.join(self.tmp, "steady"), [
            ("2025-01-01T10:00:00", "start"),
            ("2025-01-20T10:00:00", "regular work"),
            ("2025-02-10T10:00:00", "more work"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, depth=1)
        self.assertEqual(cem.projects[0].resurrections, 0)
        self.assertEqual(cem.projects[0].longest_flatline, 0)


class TestHonors(FixtureBase):
    def test_honors_awarded(self):
        from datetime import datetime as _dt, timedelta as _td
        base = _dt(2024, 1, 1, 10, 0, 0)
        commits = [("2024-01-01T10:00:00", "start")]
        for i in range(30):
            day = base + _td(days=15 * (i + 1))
            commits.append((day.strftime("%Y-%m-%dT10:00:00"),
                            "work %d" % i))
        commits.append(("2025-06-01T10:00:00", "the end"))
        make_repo(os.path.join(self.tmp, "longlived"), commits)
        make_repo(os.path.join(self.tmp, "mayfly"), [
            ("2025-03-01T10:00:00", "hi"),
            ("2025-03-02T10:00:00", "bye"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, depth=1)
        honors = {h["title"]: h["project"].name
                  for h in dps.society_honors(cem)}
        self.assertEqual(honors["The Marathoner"], "longlived")
        self.assertEqual(honors["The Mayfly"], "mayfly")
        self.assertEqual(honors["The Loudest Exit"], "longlived")
        self.assertIn("The Coldest Case", honors)
        self.assertNotIn("The Phoenix", honors)
        self.assertIn("THE SOCIETY'S HONORS", dps.render_terminal(cem))
        data = dps.cemetery_dict(cem)
        self.assertEqual(len(data["honors"]), 4)

    def test_phoenix_honor(self):
        make_repo(os.path.join(self.tmp, "phoenix"), [
            ("2025-01-01T10:00:00", "start"),
            ("2025-06-01T10:00:00", "back from a 151-day flatline"),
            ("2025-06-05T10:00:00", "final"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, depth=1)
        titles = [h["title"] for h in dps.society_honors(cem)]
        self.assertIn("The Phoenix", titles)


class TestEulogiesAndPatients(FixtureBase):
    def test_eulogy_scales_with_the_life(self):
        commits = [("2024-01-01T10:00:00", "start")]
        for i in range(60):
            commits.append(("2024-%02d-10T10:00:00" % (i % 12 + 1),
                            "work %d" % i))
        commits.append(("2025-03-01T10:00:00", "the end"))
        make_repo(os.path.join(self.tmp, "biglife"), commits)
        make_repo(os.path.join(self.tmp, "smalllife"), [
            ("2025-03-01T10:00:00", "hi"),
            ("2025-03-02T10:00:00", "bye"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, depth=1)
        by_name = {p.name: p for p in cem.deceased}
        big = dps.compose_eulogy(by_name["biglife"])
        small = dps.compose_eulogy(by_name["smalllife"])
        self.assertIn("was meant", big)
        self.assertIn("burned fast", small)
        self.assertNotEqual(big, small)
        data = dps.cemetery_dict(cem)
        eulogies = {d["name"]: d["eulogy"] for d in data["projects"]}
        self.assertTrue(all(eulogies.values()))

    def test_patient_records_are_complete(self):
        make_repo(os.path.join(self.tmp, "sleepy"), [
            ("2026-10-01T10:00:00", "start"),
            ("2026-10-20T10:00:00", "last words so far"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, depth=1)
        wards = dps.site_wards(cem)
        entries = wards["intensive_care"] + wards["still_breathing"]
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["epitaph"], "last words so far")
        self.assertEqual(e["born"], "2026")
        self.assertIn("does not bury the living", e["description"])


class TestFullEulogies(FixtureBase):
    """v0.26.0: the full eulogy, spoken style, behind --eulogy."""

    def _buried(self):
        commits = [("2024-01-05T10:00:00", "first breath")]
        for i in range(14):
            commits.append(("2024-%02d-10T10:00:00" % (i % 8 + 1),
                            "steady work %d" % i))
        commits.append(("2024-09-01T10:00:00", "wrapping up for now"))
        make_repo(os.path.join(self.tmp, "oldfaithful"), commits)
        return dps.build_cemetery(self.tmp, dead_days=90, now=NOW)

    def test_buried_eulogy_weaves_the_record(self):
        cem = self._buried()
        p = cem.deceased[0]
        text = dps.compose_full_eulogy(p)
        self.assertIn("oldfaithful", text)
        self.assertIn("Jan 05, 2024", text)
        self.assertIn("Sep 01, 2024", text)
        self.assertIn("16 commits", text)
        self.assertIn("Jan 2024", text)  # the peak month, named
        self.assertIn(p.cause, text)
        self.assertIn('"wrapping up for now"', text)
        self.assertNotIn("—", text)

    def test_eulogy_is_deterministic(self):
        cem = self._buried()
        p = cem.deceased[0]
        self.assertEqual(dps.compose_full_eulogy(p),
                         dps.compose_full_eulogy(p))
        again = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertEqual(dps.compose_full_eulogy(again.deceased[0]),
                         dps.compose_full_eulogy(p))

    def test_resurrected_eulogy_notes_the_return(self):
        make_repo(os.path.join(self.tmp, "phoenix"), [
            ("2024-01-01T10:00:00", "start"),
            ("2024-06-15T10:00:00", "back again"),
            ("2024-07-01T10:00:00", "final word"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        p = cem.deceased[0]
        self.assertEqual(p.resurrections, 1)
        text = dps.compose_full_eulogy(p)
        self.assertIn("flatlined for 166 days once and come back",
                      text)
        self.assertIn("This time, it did not.", text)

    def test_successor_is_named_in_the_eulogy(self):
        make_repo(os.path.join(self.tmp, "firsttry"), [
            ("2024-01-01T10:00:00", "start"),
            ("2024-02-01T10:00:00", "giving up"),
        ])
        make_repo(os.path.join(self.tmp, "secondtry"), [
            ("2024-02-10T10:00:00", "new beginning"),
            ("2024-03-01T10:00:00", "still going"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        by_name = {p.name: p for p in cem.projects}
        first = by_name["firsttry"]
        self.assertIn("secondtry", first.survived_by)
        self.assertIn("secondtry", dps.compose_full_eulogy(first))

    def test_at_rest_eulogy_is_softer(self):
        path = os.path.join(self.tmp, "donetools")
        dates = ["2025-03-01", "2025-03-15", "2025-04-01",
                 "2025-04-15", "2025-05-01", "2025-05-15",
                 "2025-05-20", "2025-05-24", "2025-05-27",
                 "2025-05-29", "2025-05-31"]
        commits = [("%sT10:00:00" % d, "work %d" % i)
                   for i, d in enumerate(dates, 1)]
        commits.append(("2025-06-01T10:00:00", "work twelve"))
        make_repo(path, commits)
        with open(os.path.join(path, "PROJECT_WILL.md"), "w") as fh:
            fh.write("# Will\nStatus: complete\n"
                     "Note: It did everything it was going to do.\n")
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertEqual(len(cem.resting), 1)
        text = dps.compose_full_eulogy(cem.resting[0])
        self.assertIn("did everything it was going to do", text)
        self.assertNotIn("coroner", text)
        self.assertNotIn("flatlined", text)

    def test_the_living_get_no_eulogy(self):
        make_repo(os.path.join(self.tmp, "aliveandwell"), [
            ("2025-12-20T10:00:00", "start"),
            ("2025-12-30T10:00:00", "recent work"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertEqual(len(cem.alive), 1)
        self.assertIsNone(dps.compose_full_eulogy(cem.alive[0]))
        data = dps.cemetery_dict(cem, with_eulogy=True)
        self.assertIsNone(data["projects"][0]["full_eulogy"])

    def test_flag_controls_every_surface(self):
        cem = self._buried()
        eulogy = dps.compose_full_eulogy(cem.deceased[0])
        self.assertIn("THE EULOGIES",
                      dps.render_terminal(cem, with_eulogy=True))
        self.assertNotIn("THE EULOGIES", dps.render_terminal(cem))
        self.assertIn(eulogy,
                      dps.render_markdown(cem, with_eulogy=True))
        self.assertNotIn(eulogy, dps.render_markdown(cem))
        self.assertIn('class="fulleulogy"',
                      dps.render_html(cem, with_eulogy=True))
        self.assertNotIn('class="fulleulogy"', dps.render_html(cem))
        on = dps.cemetery_dict(cem, with_eulogy=True)["projects"][0]
        off = dps.cemetery_dict(cem)["projects"][0]
        self.assertEqual(on["full_eulogy"], eulogy)
        self.assertIsNone(off["full_eulogy"])
        self.assertEqual(
            dps.site_projects(cem, with_eulogy=True)[0]["eulogy"],
            eulogy)
        self.assertNotIn("eulogy", dps.site_projects(cem)[0])

    def test_cli_eulogy_flag(self):
        self._buried()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dps.main([self.tmp, "--eulogy"])
        self.assertEqual(rc, 0)
        self.assertIn("THE EULOGIES", buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dps.main([self.tmp])
        self.assertEqual(rc, 0)
        self.assertNotIn("THE EULOGIES", buf.getvalue())


class TestHtmlAndCardParity(FixtureBase):
    def test_html_has_honors_and_eulogy(self):
        make_repo(os.path.join(self.tmp, "htmlproj"), [
            ("2025-01-01T10:00:00", "start"),
            ("2025-02-01T10:00:00", "the end"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, depth=1)
        page = dps.render_html(cem)
        self.assertIn("THE SOCIETY", page)
        self.assertIn("HONORS", page)
        self.assertIn("It had a short, bright season.", page)
        self.assertIn('class="eulogy"', page)

    def test_card_prefers_the_phoenix_line(self):
        make_repo(os.path.join(self.tmp, "phoenix"), [
            ("2025-01-01T10:00:00", "start"),
            ("2025-06-01T10:00:00", "back from a 151-day flatline"),
            ("2025-06-05T10:00:00", "final"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, depth=1)
        card = dps.render_card(cem)
        self.assertIn("Back from the dead: phoenix, after 151 days.", card)


class TestWills(FixtureBase):
    """v0.7.0: PROJECT_WILL.md, completion verdicts, At Rest."""

    def _repo(self, name="donetools", last="work twelve"):
        path = os.path.join(self.tmp, name)
        dates = ["2025-03-01", "2025-03-15", "2025-04-01", "2025-04-15",
                 "2025-05-01", "2025-05-15", "2025-05-20", "2025-05-24",
                 "2025-05-27", "2025-05-29", "2025-05-31"]
        commits = [("2025-%sT10:00:00" % d[5:], "work %d" % i)
                   for i, d in enumerate(dates, 1)]
        commits.append(("2025-06-01T10:00:00", last))
        return make_repo(path, commits)

    def _will(self, path, text):
        with open(os.path.join(path, "PROJECT_WILL.md"), "w") as fh:
            fh.write(text)

    def test_will_complete_moves_to_resting(self):
        path = self._repo()
        self._will(path, "# Will\nStatus: complete\n"
                         "Note: It did everything it was going to do.\n")
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertEqual(len(cem.resting), 1)
        self.assertEqual(len(cem.deceased), 0)
        p = cem.resting[0]
        self.assertEqual(p.will_status, "complete")
        self.assertIn("does not bury the finished", p.cause)
        self.assertIn("AT REST", dps.render_terminal(cem))
        data = dps.cemetery_dict(cem)
        self.assertEqual(data["summary"]["at_rest"], 1)
        self.assertEqual(data["projects"][0]["will_status"], "complete")
        self.assertIn("At Rest: donetools", dps.render_markdown(cem))
        self.assertIn("AT REST: FINISHED, NOT DEAD",
                      dps.render_html(cem))

    def test_will_successor_and_note(self):
        path = self._repo()
        self._will(path, "Status: finished\nSuccessor: newthing\n"
                         "Note: Be kind to it.\n")
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        p = cem.resting[0]
        self.assertEqual(p.survived_by,
                         "Survived by newthing, named in its will.")
        self.assertEqual(p.will_note, "Be kind to it.")

    def test_will_adoptable_stays_buried_with_factor(self):
        path = self._repo()
        self._will(path, "Status: adoptable\n")
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertEqual(len(cem.deceased), 1)
        self.assertEqual(len(cem.resting), 0)
        self.assertTrue(any("Left for adoption" in f
                            for f in cem.deceased[0].factors))

    def test_completion_last_words_without_will(self):
        self._repo(last="v1.0.0: final release")
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertEqual(len(cem.deceased), 1)
        self.assertTrue(cem.deceased[0].cause.startswith(
            "Finished, by the look of it."))

    def test_no_will_no_change(self):
        self._repo()
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertEqual(len(cem.deceased), 1)
        self.assertEqual(cem.deceased[0].will_status, "")
        self.assertEqual(dps.cemetery_dict(cem)["summary"]["at_rest"], 0)


def _proj(name, born, died, commits, authors=1, readme=True, remote=True,
          silence=200, gaps=None, last="work", status="deceased",
          resurrections=0, flatline=0, will_status=""):
    from datetime import datetime, timezone
    def d(s):
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    return dps.Project(
        name=name, path="/x/" + name, born=d(born), died=d(died),
        commits=commits, first_words="start", last_words=last,
        authors=authors, has_readme=readme, has_remote=remote,
        silence_days=silence, gaps=gaps or [], status=status,
        resurrections=resurrections, longest_flatline=flatline,
        will_status=will_status)


class TestInfamyAndAutopsy(unittest.TestCase):
    """v0.8.0: Hall of Infamy, metadata autopsy, certificates."""

    def _cem(self, projects):
        from datetime import datetime, timezone
        return dps.Cemetery(root="/x", generated=datetime(
            2026, 1, 1, tzinfo=timezone.utc), dead_days=90,
            projects=projects)

    def test_shooting_star_picks_fastest_burn(self):
        fast = _proj("fast", "2025-03-01", "2025-03-03", 20)
        slow = _proj("slow", "2025-03-01", "2025-05-30", 60)
        infamy = dps.hall_of_infamy(self._cem([fast, slow]))
        star = [h for h in infamy if h["title"] == "The Shooting Star"]
        self.assertEqual(len(star), 1)
        self.assertEqual(star[0]["project"].name, "fast")

    def test_crowd_and_unknown_soldier(self):
        crowd = _proj("crowd", "2025-01-10", "2025-06-01", 30, authors=4)
        ghost = _proj("ghost", "2025-02-01", "2025-05-01", 45,
                      readme=False, remote=False)
        titles = {h["title"]: h["project"].name
                  for h in dps.hall_of_infamy(self._cem([crowd, ghost]))}
        self.assertEqual(titles["The Crowd That Left"], "crowd")
        self.assertEqual(titles["The Unknown Soldier"], "ghost")

    def test_autopsy_rewards_the_risen(self):
        risen = _proj("risen", "2024-06-01", "2025-06-01", 120,
                      resurrections=1, flatline=120, silence=200)
        a = dps.autopsy(risen)
        self.assertEqual(a["revival_verdict"], "Worth exhuming.")
        self.assertIn("it has risen before", a["revival_reasons"])

    def test_autopsy_finished_stays_resting(self):
        done = _proj("done", "2024-06-01", "2025-06-01", 80,
                     status="resting", will_status="complete")
        a = dps.autopsy(done)
        self.assertEqual(a["revival_verdict"], "Let it rest. It finished.")
        self.assertTrue(a["end_pattern"].startswith("Declared complete"))

    def test_autopsy_end_patterns(self):
        wip = _proj("wip", "2025-03-01", "2025-05-01", 12, last="wip")
        self.assertIn("mid-sentence", dps.autopsy(wip)["end_pattern"])
        tidy = _proj("tidy", "2025-03-01", "2025-05-01", 12,
                     last="final release")
        self.assertIn("Ended tidily", dps.autopsy(tidy)["end_pattern"])

    def test_certificates_written_by_cli(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix="dps-cert-")
        self.addCleanup(lambda: __import__("shutil").rmtree(
            tmp, ignore_errors=True))
        grounds = os.path.join(tmp, "grounds")
        make_repo(os.path.join(grounds, "gone"), [
            ("2025-02-01T09:00:00", "a"),
            ("2025-02-03T09:00:00", "b"),
            ("2025-02-05T09:00:00", "c"),
        ])
        out = os.path.join(tmp, "certs")
        rc = dps.main([grounds, "--certificates", out])
        self.assertEqual(rc, 0)
        files = os.listdir(out)
        self.assertEqual(files, ["gone-certificate.html"])
        with open(os.path.join(out, files[0])) as fh:
            html = fh.read()
        self.assertIn("CERTIFICATE OF DEATH", html)
        self.assertIn("gone", html)


class TestTimelineAndNewVerdicts(FixtureBase):
    """v0.9.0: monthly activity, sparkline, four new verdicts."""

    def test_activity_buckets_include_empty_months(self):
        make_repo(os.path.join(self.tmp, "pulse"), [
            ("2025-01-05T10:00:00", "a"),
            ("2025-01-20T10:00:00", "b"),
            ("2025-03-10T10:00:00", "c"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertEqual(cem.projects[0].activity, [2, 0, 1])

    def test_sparkline_shape(self):
        self.assertEqual(dps.sparkline([0, 5, 10]), " ▄█")
        self.assertEqual(dps.sparkline([]), "")

    def test_died_waiting(self):
        commits = [("2025-03-%02dT10:00:00" % d, "work %d" % d)
                   for d in (1, 5, 9, 13, 17)]
        commits.append(("2025-03-21T10:00:00", "todo: finish the parser"))
        make_repo(os.path.join(self.tmp, "waiter"), commits)
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertTrue(cem.deceased[0].cause.startswith("Died waiting."))

    def test_killed_by_a_rename(self):
        commits = [("2025-03-%02dT10:00:00" % d, "work %d" % d)
                   for d in (1, 5, 9, 13, 17)]
        commits.append(("2025-03-21T10:00:00", "rename project to newthing"))
        make_repo(os.path.join(self.tmp, "renamed"), commits)
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertTrue(cem.deceased[0].cause.startswith(
            "Killed by a rename."))

    def test_died_writing_the_manual(self):
        commits = [("2025-0%d-%02dT10:00:00" % (3 + i // 8, 1 + i % 27),
                    "work %d" % i) for i in range(21)]
        commits.append(("2025-06-01T10:00:00", "update readme"))
        make_repo(os.path.join(self.tmp, "manual"), commits)
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertTrue(cem.deceased[0].cause.startswith(
            "Died writing the manual."))

    def test_died_of_a_sequel(self):
        make_repo(os.path.join(self.tmp, "oldtool"), [
            ("2025-03-01T10:00:00", "a"),
            ("2025-03-05T10:00:00", "b"),
            ("2025-03-09T10:00:00", "starting the v2 rewrite"),
        ])
        make_repo(os.path.join(self.tmp, "newtool"), [
            ("2025-03-19T10:00:00", "first commit"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        old = [p for p in cem.projects if p.name == "oldtool"][0]
        self.assertEqual(old.cause,
                         "Died of a sequel. The replacement was already "
                         "on the way.")


class TestBadge(FixtureBase):
    """v0.10.0: the README badge."""

    def test_badge_counts(self):
        make_repo(os.path.join(self.tmp, "gone"), [
            ("2025-02-01T09:00:00", "a"),
            ("2025-02-03T09:00:00", "b"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        badge = dps.render_badge(cem)
        self.assertIn("dead projects society", badge)
        self.assertIn("1 buried", badge)
        self.assertIn("<svg", badge)

    def test_badge_flag_writes_file(self):
        make_repo(os.path.join(self.tmp, "gone"), [
            ("2025-02-01T09:00:00", "a"),
            ("2025-02-03T09:00:00", "b"),
        ])
        out = os.path.join(self.tmp, "badge.svg")
        rc = dps.main([self.tmp, "--badge", out])
        self.assertEqual(rc, 0)
        with open(out) as fh:
            self.assertIn("1 buried", fh.read())


class TestLanguageAndWrapped(FixtureBase):
    """v0.11.0: language from file names, the wrapped kit."""

    def test_language_detected_from_file_names(self):
        path = os.path.join(self.tmp, "poly")
        make_repo(path, [("2025-02-01T09:00:00", "a"),
                         ("2025-02-03T09:00:00", "b")])
        for name in ("a.py", "b.py", "c.py", "d.js"):
            with open(os.path.join(path, name), "w") as fh:
                fh.write("x")
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        self.assertEqual(cem.projects[0].language, "Python")
        data = dps.cemetery_dict(cem)
        self.assertEqual(data["projects"][0]["language"], "Python")

    def test_wrapped_kit_writes_three_files(self):
        make_repo(os.path.join(self.tmp, "gone"), [
            ("2025-02-01T09:00:00", "a"),
            ("2025-02-03T09:00:00", "b"),
            ("2025-02-05T09:00:00", "c"),
        ])
        kit = os.path.join(self.tmp, "kit")
        rc = dps.main([self.tmp, "--wrapped-kit", kit, "--year", "2025"])
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(os.listdir(kit)),
                         ["wrapped-card.svg", "wrapped.html", "wrapped.txt"])
        with open(os.path.join(kit, "wrapped.html")) as fh:
            html = fh.read()
        self.assertIn("2025 IN THE GROUNDS", html)
        self.assertIn("gone", html)
        with open(os.path.join(kit, "wrapped.txt")) as fh:
            text = fh.read()
        self.assertIn("My 2025, formally buried", text)
        self.assertIn("1 buried", text)

    def test_wrapped_empty_year_is_honest(self):
        make_repo(os.path.join(self.tmp, "gone"), [
            ("2025-02-01T09:00:00", "a"),
            ("2025-02-03T09:00:00", "b"),
        ])
        html = None
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        html = dps.render_wrapped(cem, 1999)
        self.assertIn("Nothing of yours ended in 1999", html)


class TestDeepAutopsy(unittest.TestCase):
    """v0.12.0: the autopsy reads the shape of the life."""

    def test_peak_and_front_loaded(self):
        p = _proj("fader", "2026-01-01", "2026-12-01", 1567, authors=3)
        p.activity = [406, 632, 152, 19, 0, 0, 2, 11, 86, 108, 130, 21]
        a = dps.autopsy(p)
        self.assertEqual(a["peak_month"], "Feb 2026")
        self.assertEqual(a["peak_commits"], 632)
        self.assertAlmostEqual(a["peak_share_percent"], 40.3, places=1)
        self.assertTrue(a["momentum"].startswith("Front-loaded"))
        self.assertTrue(any(f.startswith("Peak month: Feb 2026")
                            for f in a["findings"]))

    def test_one_bright_burst(self):
        p = _proj("burst", "2025-01-01", "2025-06-01", 100)
        p.activity = [5, 80, 5, 5, 3, 2]
        a = dps.autopsy(p)
        self.assertTrue(a["momentum"].startswith("One bright burst"))

    def test_late_surge(self):
        p = _proj("surge", "2025-01-01", "2025-06-01", 100)
        p.activity = [5, 5, 10, 20, 25, 35]
        a = dps.autopsy(p)
        self.assertTrue(a["momentum"].startswith("Late surge"))

    def test_neglect_findings(self):
        p = _proj("neglected", "2025-01-01", "2025-05-01", 30,
                  readme=False, remote=False, authors=1)
        a = dps.autopsy(p)
        joined = " ".join(a["findings"])
        self.assertIn("No README", joined)
        self.assertIn("No remote", joined)
        self.assertIn("Bus factor one", joined)

    def test_terminal_autopsy_prints_notes(self):
        from datetime import datetime, timezone
        p = _proj("gone", "2025-01-01", "2025-05-01", 30,
                  readme=False, remote=False)
        cem = dps.Cemetery(root="/x", generated=datetime(
            2026, 1, 1, tzinfo=timezone.utc), dead_days=90, projects=[p])
        text = dps.render_terminal(cem, with_autopsy=True)
        self.assertIn("Momentum:", text)
        self.assertIn("Findings:", text)

    def test_site_export_carries_autopsy(self):
        from datetime import datetime, timezone
        p = _proj("gone", "2025-01-01", "2025-05-01", 30)
        p.cause = "Cause unknown. It simply stopped."
        cem = dps.Cemetery(root="/x", generated=datetime(
            2026, 1, 1, tzinfo=timezone.utc), dead_days=90, projects=[p])
        stones = dps.site_projects(cem)
        self.assertIn("autopsy", stones[0])
        self.assertIn("momentum", stones[0]["autopsy"])
        self.assertIn("revival_verdict", stones[0]["autopsy"])


class TestSections(FixtureBase):
    """v0.13.0: the cemetery, sectioned by era and language."""

    def test_sections_count_the_dead(self):
        path = os.path.join(self.tmp, "poly")
        make_repo(path, [("2025-02-01T09:00:00", "a"),
                         ("2025-02-03T09:00:00", "b")])
        for name in ("a.py", "b.py", "c.js"):
            with open(os.path.join(path, name), "w") as fh:
                fh.write("x")
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        sections = dps.cemetery_dict(cem)["summary"]["sections"]
        self.assertEqual(sections["by_era"], {"2020s": 1})
        self.assertEqual(sections["by_language"], {"Python": 1})

    def test_wards_carry_tech(self):
        path = os.path.join(self.tmp, "sick")
        make_repo(path, [("2026-10-20T09:00:00", "a"),
                         ("2026-10-25T09:00:00", "b")])
        with open(os.path.join(path, "app.js"), "w") as fh:
            fh.write("x")
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        wards = dps.site_wards(cem)
        entries = wards["intensive_care"] + wards["still_breathing"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["tech"], ["JavaScript"])


class TestDependencyEraAndLog(FixtureBase):
    """v0.14.0: dependency-era signals and the Groundskeeper's Log."""

    def test_died_maintaining(self):
        commits = [("2025-01-05T09:00:00", "initial commit"),
                   ("2025-02-05T09:00:00", "core feature"),
                   ("2025-03-05T09:00:00", "another feature"),
                   ("2025-04-05T09:00:00", "bump lodash"),
                   ("2025-04-20T09:00:00", "upgrade react"),
                   ("2025-05-05T09:00:00", "dependabot: bump axios"),
                   ("2025-05-20T09:00:00", "update dependencies"),
                   ("2025-06-05T09:00:00", "migration to new api"),
                   ("2025-06-20T09:00:00", "bump typescript"),
                   ("2025-07-05T09:00:00", "upgrade dependencies")]
        make_repo(os.path.join(self.tmp, "upkeep"), commits)
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        p = cem.deceased[0]
        self.assertGreaterEqual(p.dep_tail_share, 0.7)
        self.assertTrue(p.cause.startswith("Died maintaining"))

    def test_autopsy_dependency_finding(self):
        p = _proj("era", "2024-01-01", "2025-06-01", 100)
        p.dep_commits = 45
        a = dps.autopsy(p)
        self.assertTrue(any(f.startswith("Dependency era: 45 of 100")
                            for f in a["findings"]))
        self.assertEqual(a["dependency_commits"], 45)

    def test_log_first_visit_and_changes(self):
        from datetime import datetime, timezone
        dead = _proj("gone", "2025-01-01", "2025-05-01", 30)
        alive = _proj("alive", "2025-01-01", "2025-05-01", 30,
                      status="alive")
        cem = dps.Cemetery(root="/x", generated=datetime(
            2026, 1, 1, tzinfo=timezone.utc), dead_days=90,
            projects=[dead, alive])
        first = dps.groundskeeper_log(None, cem)
        self.assertTrue(first["first_visit"])
        prev = dps._snapshot(cem)
        # Time passes: the living one dies, the dead one rises.
        dead2 = _proj("gone", "2025-01-01", "2025-05-01", 31,
                      status="alive")
        alive2 = _proj("alive", "2025-01-01", "2025-05-01", 30,
                       status="deceased")
        cem2 = dps.Cemetery(root="/x", generated=datetime(
            2026, 6, 1, tzinfo=timezone.utc), dead_days=90,
            projects=[dead2, alive2])
        log = dps.groundskeeper_log(prev, cem2)
        self.assertEqual(log["risen"], ["gone"])
        self.assertEqual(log["newly_buried"], ["alive"])
        text = dps.render_groundskeeper_log(log)
        self.assertIn("Newly buried: alive", text)
        self.assertIn("Risen: gone", text)

    def test_diff_main_records_state(self):
        make_repo(os.path.join(self.tmp, "gone"), [
            ("2025-02-01T09:00:00", "a"),
            ("2025-02-03T09:00:00", "b"),
        ])
        state = os.path.join(self.tmp, "state.json")
        rc = dps.main([self.tmp, "--diff", "--state", state])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(state))
        rc = dps.main([self.tmp, "--diff", "--state", state])
        self.assertEqual(rc, 0)


class TestResurrectionCertificates(FixtureBase):
    """v0.15.0: the other certificate."""

    def _risen_repo(self):
        make_repo(os.path.join(self.tmp, "phoenix"), [
            ("2025-01-05T09:00:00", "a"),
            ("2025-01-15T09:00:00", "b"),
            ("2025-06-20T09:00:00", "it lives"),
            ("2025-06-25T09:00:00", "c"),
        ])

    def test_risen_project_detected(self):
        self._risen_repo()
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        p = cem.projects[0]
        self.assertEqual(p.resurrections, 1)
        self.assertGreaterEqual(p.longest_flatline, 90)

    def test_certificates_include_resurrection(self):
        self._risen_repo()
        out = os.path.join(self.tmp, "certs")
        rc = dps.main([self.tmp, "--certificates", out])
        self.assertEqual(rc, 0)
        files = sorted(os.listdir(out))
        self.assertEqual(files, ["phoenix-certificate.html",
                                 "phoenix-resurrection-certificate.html"])
        with open(os.path.join(out,
                               "phoenix-resurrection-certificate.html")) as fh:
            html = fh.read()
        self.assertIn("CERTIFICATE OF RESURRECTION", html)
        self.assertIn("It has risen once.", html)
        self.assertIn("fell again", html)

    def test_living_condition_wording(self):
        from datetime import datetime, timezone
        p = _proj("risen", "2025-01-01", "2025-06-01", 40,
                  status="alive", resurrections=1, flatline=120,
                  silence=3)
        cem = dps.Cemetery(root="/x", generated=datetime(
            2026, 1, 1, tzinfo=timezone.utc), dead_days=90, projects=[p])
        html = dps.render_resurrection_certificate(p, cem)
        self.assertIn("Currently among the living", html)


class TestSquareCard(FixtureBase):
    """v0.16.0: the 1080x1080 social-feed card."""

    def test_square_card_shape_and_counts(self):
        make_repo(os.path.join(self.tmp, "gone"),
                  [("2025-01-05T09:00:00", "start"),
                   ("2025-01-20T09:00:00", "wip")])
        make_repo(os.path.join(self.tmp, "alive"),
                  [(NOW.strftime("%Y-%m-%dT09:00:00"), "today")])
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        svg = dps.render_square_card(cem)
        self.assertIn('width="1080" height="1080"', svg)
        self.assertIn("1 buried", svg)
        self.assertIn("BURIED", svg)

    def test_square_cli_writes_file(self):
        make_repo(os.path.join(self.tmp, "gone"),
                  [("2025-01-05T09:00:00", "start")])
        out = os.path.join(self.tmp, "square.svg")
        self.assertEqual(dps.main([self.tmp, "--square", out]), 0)
        with open(out) as fh:
            self.assertIn("DEAD PROJECTS SOCIETY", fh.read())


class TestOnThisDay(FixtureBase):
    """v0.17.0: anniversaries in the grounds. NOW is Jan 1, 2026."""

    def _anniversary_repo(self):
        make_repo(os.path.join(self.tmp, "anniversary"), [
            ("2024-01-01T09:00:00", "born on the day"),
            ("2024-06-01T09:00:00", "work"),
            ("2025-01-01T09:00:00", "died on the day"),
        ])

    def test_death_and_birth_anniversaries(self):
        self._anniversary_repo()
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        otd = dps.on_this_day(cem)
        self.assertEqual(len(otd["deaths"]), 1)
        self.assertEqual(otd["deaths"][0]["name"], "anniversary")
        self.assertEqual(otd["deaths"][0]["years_ago"], 1)
        self.assertEqual(len(otd["births"]), 1)
        self.assertEqual(otd["births"][0]["years_ago"], 2)

    def test_quiet_day(self):
        make_repo(os.path.join(self.tmp, "plain"),
                  [("2025-03-05T09:00:00", "start"),
                   ("2025-03-20T09:00:00", "end")])
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        otd = dps.on_this_day(cem)
        self.assertEqual(otd["deaths"], [])
        self.assertEqual(otd["births"], [])

    def test_terminal_section_and_json(self):
        import io
        from contextlib import redirect_stdout
        from datetime import datetime, timezone
        # The CLI's "today" is the UTC date (build_cemetery's clock).
        today = datetime.now(timezone.utc).date()
        try:
            died = today.replace(year=today.year - 1)
            born = today.replace(year=today.year - 2)
        except ValueError:  # Feb 29
            died = today.replace(year=today.year - 1, day=28)
            born = today.replace(year=today.year - 2, day=28)
        fmt = "%Y-%m-%dT09:00:00"
        make_repo(os.path.join(self.tmp, "cli-anniversary"), [
            (born.strftime(fmt), "born on the day"),
            (died.strftime(fmt), "died on the day"),
        ])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(dps.main([self.tmp, "--on-this-day"]), 0)
        out = buf.getvalue()
        self.assertIn("ON THIS DAY IN THE GROUNDS", out)
        self.assertIn("died on this day, 1 year ago", out)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(
                dps.main([self.tmp, "--json", "--on-this-day"]), 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["on_this_day"]["deaths"][0]["name"],
                         "cli-anniversary")


class TestMultipleGrounds(FixtureBase):
    """v0.18.0: several folders, one cemetery."""

    def _two_roots(self):
        a = os.path.join(self.tmp, "grounds-a")
        b = os.path.join(self.tmp, "grounds-b")
        os.makedirs(a)
        os.makedirs(b)
        make_repo(os.path.join(a, "old-idea"), [
            ("2025-03-02T09:00:00", "initial commit"),
            ("2025-06-14T09:00:00", "wip"),
        ])
        make_repo(os.path.join(b, "shiny-replacement"), [
            ("2025-06-20T09:00:00", "initial commit"),
            ("2025-07-01T09:00:00", "setup"),
        ])
        return a, b

    def test_succession_across_roots(self):
        a, b = self._two_roots()
        cem = dps.build_grounds([a, b], dead_days=90, now=NOW)
        self.assertEqual(len(cem.projects), 2)
        dead = [p for p in cem.projects if p.name == "old-idea"][0]
        self.assertIn("shiny-replacement", dead.survived_by)

    def test_no_cross_succession_within_one_root(self):
        a, b = self._two_roots()
        cem = dps.build_grounds([a], dead_days=90, now=NOW)
        dead = cem.projects[0]
        self.assertNotIn("shiny-replacement", dead.survived_by)

    def test_duplicate_roots_deduped(self):
        a, b = self._two_roots()
        cem = dps.build_grounds([a, a, b], dead_days=90, now=NOW)
        self.assertEqual(len(cem.projects), 2)

    def test_cli_accepts_two_paths(self):
        import io, json
        from contextlib import redirect_stdout
        a, b = self._two_roots()
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dps.main([a, b, "--json"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["summary"]["buried"], 2)


class TestAdoptionPapers(FixtureBase):
    """v0.19.0: adoption papers and full dates in the site export."""

    def _build(self):
        make_repo(os.path.join(self.tmp, "old-game"), [
            ("2025-03-02T09:00:00", "initial commit"),
            ("2025-06-14T09:00:00", "wip"),
        ])
        rest = os.path.join(self.tmp, "resting-lib")
        make_repo(rest, [
            ("2025-03-02T09:00:00", "initial commit"),
            ("2025-06-14T09:00:00", "final tidy"),
        ])
        with open(os.path.join(rest, "PROJECT_WILL.md"), "w") as fh:
            fh.write("Status: complete\n")
        make_repo(os.path.join(self.tmp, "fresh-tool"), [
            ("2025-12-30T09:00:00", "initial commit"),
        ])

    def test_papers_list_the_buried_only(self):
        self._build()
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        papers = dps.render_adoption_papers(cem)
        self.assertIn("ADOPTION PAPERS", papers)
        self.assertIn("## old-game", papers)
        self.assertNotIn("## resting-lib", papers)
        self.assertIn("Adopted by:", papers)
        self.assertIn("charges nothing for adoptions", papers)

    def test_papers_pitch_from_the_record(self):
        self._build()
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        papers = dps.render_adoption_papers(cem)
        # old-game: no README, no remote, sole author
        self.assertIn("never left the house", papers)
        self.assertIn("A second pair of hands", papers)

    def test_site_export_carries_full_dates(self):
        self._build()
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        stone = dps.site_projects(cem)[0]
        self.assertIn("born_full", stone)
        self.assertIn("died_full", stone)
        wards = dps.site_wards(cem)
        entry = (wards["intensive_care"] + wards["still_breathing"])[0]
        self.assertIn("born_full", entry)
        self.assertIn("died_full", entry)


class TestOneline(FixtureBase):
    """v0.20.0: one line per project."""

    def test_oneline_covers_every_state(self):
        make_repo(os.path.join(self.tmp, "old-game"), [
            ("2025-03-02T09:00:00", "initial commit"),
            ("2025-06-14T09:00:00", "wip"),
        ])
        make_repo(os.path.join(self.tmp, "fresh-tool"), [
            ("2025-12-30T09:00:00", "initial commit"),
        ])
        cem = dps.build_cemetery(self.tmp, dead_days=90, now=NOW)
        out = dps.render_oneline(cem)
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        self.assertTrue(any(l.startswith("old-game - buried")
                            for l in lines))
        self.assertTrue(any(l.startswith("fresh-tool - still breathing")
                            for l in lines))

    def test_oneline_cli(self):
        import io
        from contextlib import redirect_stdout
        make_repo(os.path.join(self.tmp, "old-game"), [
            ("2025-03-02T09:00:00", "initial commit"),
            ("2025-06-14T09:00:00", "wip"),
        ])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dps.main([self.tmp, "--oneline"])
        self.assertEqual(rc, 0)
        self.assertIn("old-game - buried", buf.getvalue())
        self.assertNotIn("DEAD PROJECTS SOCIETY", buf.getvalue())


class TestFailIfNewDeaths(FixtureBase):
    """v0.21.0: --fail-if-new-deaths exit code with --diff."""

    def _run(self, state):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            return dps.main([self.tmp, "--diff", "--state", state,
                             "--fail-if-new-deaths"])

    def test_exit_codes(self):
        # The CLI reads the real clock, so the living fixture is
        # dated relative to today, not the fixture NOW.
        from datetime import datetime, timedelta, timezone
        recent = (datetime.now(timezone.utc) - timedelta(days=2)
                  ).strftime("%Y-%m-%dT09:00:00")
        state = os.path.join(self.tmp, "state.json")
        make_repo(os.path.join(self.tmp, "fresh-tool"), [
            (recent, "initial commit"),
        ])
        self.assertEqual(self._run(state), 0)   # first visit: baseline
        make_repo(os.path.join(self.tmp, "old-game"), [
            ("2025-03-02T09:00:00", "initial commit"),
            ("2025-06-14T09:00:00", "wip"),
        ])
        self.assertEqual(self._run(state), 3)   # a new death appeared
        self.assertEqual(self._run(state), 0)   # nothing new since


class TestHtmlAutopsy(FixtureBase):
    """v0.22.0: the HTML graveyard carries the autopsy line."""

    def test_html_includes_autopsy(self):
        make_repo(os.path.join(self.tmp, "gone"), [
            ("2025-02-01T09:00:00", "ambitious start"),
            ("2025-02-03T09:00:00", "wip"),
        ], readme=True, remote=True)
        cem = dps.build_cemetery(self.tmp, now=NOW)
        page = dps.render_html(cem)
        self.assertIn("Autopsy:", page)
        self.assertIn("commits a month", page)
        self.assertIn("Revival:", page)


class TestHtmlGroundskeeperLog(FixtureBase):
    """v0.23.0: the HTML report carries the log when --diff ran."""

    def _cem(self):
        make_repo(os.path.join(self.tmp, "gone"), [
            ("2025-02-01T09:00:00", "ambitious start"),
            ("2025-02-03T09:00:00", "wip"),
        ], readme=True, remote=True)
        return dps.build_cemetery(self.tmp, now=NOW)

    def test_log_section_present(self):
        log = {"first_visit": False, "newly_buried": ["gone"],
               "newly_resting": [], "risen": [], "stirred": [],
               "newly_born": [], "still_buried": 1}
        page = dps.render_html(self._cem(), log)
        self.assertIn("GROUNDSKEEPER", page)
        self.assertIn("Newly buried: gone", page)
        self.assertIn("Still buried, undisturbed: 1.", page)

    def test_no_log_no_section(self):
        page = dps.render_html(self._cem())
        self.assertNotIn("GROUNDSKEEPER", page)


class TestExclude(FixtureBase):
    """v0.24.0: --exclude keeps named directories out of the scan."""

    def _grounds(self):
        make_repo(os.path.join(self.tmp, "mine"), [
            ("2025-03-02T09:00:00", "initial commit"),
            ("2025-06-14T09:00:00", "wip"),
        ])
        make_repo(os.path.join(self.tmp, "vendored"), [
            ("2025-03-02T09:00:00", "initial commit"),
            ("2025-06-14T09:00:00", "wip"),
        ])

    def test_exclude_by_name(self):
        self._grounds()
        cem = dps.build_cemetery(self.tmp, now=NOW,
                                 exclude=["vendored"])
        self.assertEqual([p.name for p in cem.projects], ["mine"])

    def test_exclude_repeatable(self):
        self._grounds()
        cem = dps.build_cemetery(self.tmp, now=NOW,
                                 exclude=["vendored", "mine"])
        self.assertEqual(cem.projects, [])


class TestDeepAutopsyDepartment(FixtureBase):
    """v0.25.0: the opt-in Deep Autopsy Department. No network is
    touched: transports are fakes, keys are absent on purpose."""

    def _repo(self):
        path = os.path.join(self.tmp, "corpse")
        make_repo(path, [
            ("2025-03-02T09:00:00", "initial commit"),
            ("2025-06-14T09:00:00", "wip: parser half done"),
        ])
        with open(os.path.join(path, "README.md"), "w") as fh:
            fh.write("# Corpse\nA parser that never parsed.\n"
                     "MARKER_README\n")
        with open(os.path.join(path, "corpse.py"), "w") as fh:
            fh.write("def parse():\n    return None  # TODO\n")
        return path

    def _cem(self):
        self._repo()
        return dps.build_cemetery(self.tmp, now=NOW)

    def _args(self, **kw):
        base = dict(deep_budget=10.0, deep_model="fake-ember",
                    deep_max_tokens=120000, deep_ledger=None,
                    deep_dry_run=False, deep_post_fn=None)
        base.update(kw)
        return types.SimpleNamespace(**base)

    def test_sampler_reads_readme_and_bounds(self):
        cem = self._cem()
        p = cem.projects[0]
        text, stats = dps.sample_project(p, max_tokens=40)
        self.assertTrue(stats["truncated"])
        self.assertLessEqual(stats["est_tokens"], 60)
        text2, stats2 = dps.sample_project(p)
        self.assertIn("MARKER_README", text2)
        self.assertIn("corpse.py", stats2["files"])

    def test_estimate_math(self):
        in_t, cost = dps.deep_estimate("x" * 4000, out_tokens=1000)
        self.assertEqual(in_t, 1000)
        self.assertAlmostEqual(cost, 1000 * 0.10 / 1e6 + 1000 * 0.50 / 1e6)

    def test_ledger_round_trip(self):
        path = os.path.join(self.tmp, "ledger.jsonl")
        self.assertEqual(dps.deep_ledger_total(path), 0.0)
        dps.deep_ledger_append(path, {"cost_usd": 0.25})
        dps.deep_ledger_append(path, {"cost_usd": 0.5})
        self.assertAlmostEqual(dps.deep_ledger_total(path), 0.75)

    def test_missing_key_is_a_plain_refusal(self):
        os.environ.pop("META_API_KEY", None)
        with self.assertRaises(dps.DeepAutopsyError):
            dps.call_ember("prompt", "fake-ember")

    def test_budget_guard_refuses_and_spends_nothing(self):
        cem = self._cem()
        ledger = os.path.join(self.tmp, "ledger.jsonl")
        calls = []
        args = self._args(
            deep_budget=0.0, deep_ledger=ledger,
            deep_post_fn=lambda pr, mo: calls.append(1) or {})
        out = io.StringIO()
        with redirect_stdout(out):
            dps.run_deep_autopsies(cem, args)
        self.assertIn("BUDGET GUARD", out.getvalue())
        self.assertEqual(calls, [])
        self.assertEqual(dps.deep_ledger_total(ledger), 0.0)

    def test_fake_transport_run_records_spend(self):
        cem = self._cem()
        ledger = os.path.join(self.tmp, "ledger.jsonl")

        def fake(prompt, model):
            self.assertIn("CAUSE OF DEATH", prompt)
            return {"output_text": "It died of a TODO.",
                    "usage": {"input_tokens": 1000,
                              "output_tokens": 100}}

        args = self._args(deep_ledger=ledger, deep_post_fn=fake)
        out = io.StringIO()
        with redirect_stdout(out):
            dps.run_deep_autopsies(cem, args)
        text = out.getvalue()
        self.assertIn("DEEP AUTOPSY: corpse", text)
        self.assertIn("It died of a TODO.", text)
        self.assertAlmostEqual(dps.deep_ledger_total(ledger),
                               1000 * 0.10 / 1e6 + 100 * 0.50 / 1e6)
        self.assertEqual(cem.projects[0].deep_autopsy["cost_usd"],
                         round(1000 * 0.10 / 1e6 + 100 * 0.50 / 1e6, 4))

    def test_dry_run_cli_makes_no_call(self):
        self._repo()
        ledger = os.path.join(self.tmp, "ledger.jsonl")
        out = io.StringIO()
        with redirect_stdout(out):
            rc = dps.main([self.tmp, "--deep-dry-run",
                           "--deep-ledger", ledger])
        self.assertEqual(rc, 0)
        self.assertIn("DRY RUN corpse", out.getvalue())
        self.assertIn("No call was made", out.getvalue())
        self.assertFalse(os.path.exists(ledger))


class TestSurveyExport(FixtureBase):
    """The --site export carries its own provenance (survey.json)."""

    def test_survey_json_written(self):
        make_repo(os.path.join(self.tmp, "corpse"), [
            ("2025-03-02T09:00:00", "initial commit"),
            ("2025-06-14T09:00:00", "wip"),
        ])
        out = os.path.join(self.tmp, "site-data")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dps.main([self.tmp, "--site", out])
        self.assertEqual(rc, 0)
        with open(os.path.join(out, "survey.json")) as fh:
            survey = json.load(fh)
        self.assertEqual(survey["tool"], "dead-projects-society")
        self.assertEqual(survey["version"], dps.VERSION)
        self.assertEqual(survey["buried"], 1)
        self.assertIn("generated", survey)
