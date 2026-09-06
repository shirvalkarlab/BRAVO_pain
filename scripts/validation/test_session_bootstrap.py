"""Exercise bootstrap with disposable local repositories; never contact a network."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "session_bootstrap.sh"
GIT = shutil.which("git")


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.upstream = self.root / "upstream"
        self.repo = self.root / "checkout"
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_ALLOW_PROTOCOL="file",
                        GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME="Synthetic", GIT_AUTHOR_EMAIL="test@example.invalid",
                        GIT_COMMITTER_NAME="Synthetic", GIT_COMMITTER_EMAIL="test@example.invalid")
        self.run_git(self.root, "init", "-b", "development", str(self.upstream))
        (self.upstream / "scripts").mkdir()
        shutil.copyfile(SCRIPT, self.upstream / "scripts/session_bootstrap.sh")
        (self.upstream / "fixture.txt").write_text("base\n")
        self.run_git(self.upstream, "add", ".")
        self.run_git(self.upstream, "commit", "-m", "synthetic base")
        self.run_git(self.upstream, "branch", "PS_closedloop_deployment")
        self.run_git(self.root, "clone", str(self.upstream), str(self.repo))
        self.run_git(self.repo, "switch", "-c", "aditya")
        self.run_git(self.repo, "branch", "PS_closedloop_deployment")
        self.run_git(self.repo, "remote", "set-url", "origin", "https://github.com/Fixel-Institute/BRAVO.git")
        self.run_git(self.repo, "remote", "add", "shirvalkar", "https://github.com/shirvalkarlab/BRAVO_pain.git")
        # Only fetch is redirected. URL verification still reads the real configured URLs.
        bindir = self.root / "bin"
        bindir.mkdir()
        wrapper = bindir / "git"
        wrapper.write_text('#!/bin/sh\nif [ "$1" = fetch ]; then\n'
                           '  [ -z "$TEST_FETCH_FAIL" ] || exit 17\n'
                           '  exec "$TEST_REAL_GIT" '
                           '-c "url.$TEST_REMOTE.insteadOf=https://github.com/Fixel-Institute/BRAVO.git" '
                           '-c "url.$TEST_REMOTE.insteadOf=https://github.com/shirvalkarlab/BRAVO_pain.git" "$@"\nfi\n'
                           'exec "$TEST_REAL_GIT" "$@"\n')
        wrapper.chmod(0o755)
        self.env.update(PATH=str(bindir) + os.pathsep + os.environ["PATH"],
                        TEST_REAL_GIT=GIT, TEST_REMOTE=str(self.upstream), TEST_FETCH_FAIL="")
        self.base = self.sha(self.repo, "aditya")
        (self.upstream / "fixture.txt").write_text("upstream update\n")
        self.run_git(self.upstream, "commit", "-am", "synthetic update")
        self.latest = self.sha(self.upstream, "HEAD")
        self.run_git(self.upstream, "branch", "-f", "PS_closedloop_deployment", self.latest)

    def run_git(self, cwd, *args):
        return subprocess.run([GIT, "-C", str(cwd), *args], env=self.env,
                              check=True, capture_output=True, text=True).stdout.strip()

    def sha(self, repo, ref):
        return self.run_git(repo, "rev-parse", ref)

    def bootstrap(self):
        return subprocess.run(["bash", str(self.repo / "scripts/session_bootstrap.sh")],
                              env=self.env, capture_output=True, text=True)

    def test_clean_only_source_branches_fast_forward(self):
        self.run_git(self.repo, "switch", "development")
        result = self.bootstrap()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.run_git(self.repo, "branch", "--show-current"), "aditya")
        for branch in ("development", "PS_closedloop_deployment"):
            self.assertEqual(self.sha(self.repo, branch), self.latest)
        self.assertEqual(self.sha(self.repo, "aditya"), self.base)
        self.assertEqual((self.repo / "fixture.txt").read_text(), "base\n")

    def test_dirty_preserves_every_local_branch_and_files_but_fetches(self):
        self.run_git(self.repo, "switch", "development")
        (self.repo / "fixture.txt").write_text("uncommitted work\n")
        (self.repo / "untracked.txt").write_text("keep me\n")
        result = self.bootstrap()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ALL local branches", result.stdout)
        for branch in ("aditya", "development", "PS_closedloop_deployment"):
            self.assertEqual(self.sha(self.repo, branch), self.base)
        self.assertEqual(self.sha(self.repo, "origin/development"), self.latest)
        self.assertEqual(self.run_git(self.repo, "branch", "--show-current"), "development")
        self.assertEqual((self.repo / "fixture.txt").read_text(), "uncommitted work\n")
        self.assertEqual((self.repo / "untracked.txt").read_text(), "keep me\n")

    def test_unique_source_commit_is_never_replaced(self):
        self.run_git(self.repo, "switch", "development")
        (self.repo / "local.txt").write_text("unique\n")
        self.run_git(self.repo, "add", "local.txt")
        self.run_git(self.repo, "commit", "-m", "unique local change")
        unique = self.sha(self.repo, "HEAD")
        result = self.bootstrap()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("unique commits or diverged", result.stdout)
        self.assertEqual(self.sha(self.repo, "development"), unique)

    def test_wrong_remote_stops_before_fetch_and_hides_url(self):
        bad = "https://private-user:private-password@example.invalid/repo"
        self.run_git(self.repo, "remote", "set-url", "shirvalkar", bad)
        result = self.bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(bad, result.stdout + result.stderr)
        self.assertEqual(self.sha(self.repo, "origin/development"), self.base)

    def test_fetch_failure_never_moves_local_branches(self):
        self.env["TEST_FETCH_FAIL"] = "1"
        result = self.bootstrap()
        self.assertNotEqual(result.returncode, 0)
        for branch in ("aditya", "development", "PS_closedloop_deployment"):
            self.assertEqual(self.sha(self.repo, branch), self.base)

    def test_source_branch_checked_out_elsewhere_is_untouched(self):
        self.run_git(self.repo, "worktree", "add", str(self.root / "linked"), "development")
        result = self.bootstrap()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("checked out in a worktree", result.stdout)
        self.assertEqual(self.sha(self.repo, "development"), self.base)


if __name__ == "__main__":
    unittest.main()
