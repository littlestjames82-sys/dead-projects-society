import json
import os
import subprocess
import sys
import tempfile
import unittest
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
