"""claude/ sürümü için testler.

Gerçek git komutlarıyla geçici depolarda çalışır. Kullanıcının ~/.gitconfig'ine
ve ~/.config/git-desktop-linux klasörüne dokunmaz (HOME ve XDG_CONFIG_HOME geçici).

Çalıştırma:
    cd claude
    python3 -m unittest discover -s tests -v
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Isolate from the real user before importing anything that reads config
_SANDBOX = tempfile.mkdtemp(prefix="claude-tests-")
os.environ["HOME"] = _SANDBOX
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SANDBOX, ".config")
os.environ["GIT_CONFIG_GLOBAL"] = os.path.join(_SANDBOX, ".gitconfig")
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
subprocess.run(["git", "config", "--global", "user.name", "Test"], check=True)
subprocess.run(["git", "config", "--global", "user.email", "test@example.com"], check=True)
subprocess.run(["git", "config", "--global", "init.defaultBranch", "main"], check=True)

from git_service import GitService  # noqa: E402
import github_service  # noqa: E402
from github_service import GitHubService  # noqa: E402

# gh may read the real user's token from the system keyring; never let tests use it
_real_subprocess_run = subprocess.run


def _run_without_gh(args, *a, **kw):
    if args and args[0] == "gh":
        return subprocess.CompletedProcess(args, 1, "", "gh disabled in tests")
    return _real_subprocess_run(args, *a, **kw)


github_service.subprocess.run = _run_without_gh


def tearDownModule():
    shutil.rmtree(_SANDBOX, ignore_errors=True)


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(dir=_SANDBOX)
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.git = GitService(self.repo)

    def write(self, name, content="x\n", mode="w"):
        path = os.path.join(self.repo, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode) as f:
            f.write(content)
        return path

    def commit_all(self, msg="c"):
        self.assertTrue(self.git.stage_all())
        ok, out = self.git.git_commit(msg)
        self.assertTrue(ok, out)


class TestStatusParsing(RepoTestCase):
    def test_turkish_filename_can_be_staged(self):
        self.write("özet şablonu.txt")
        files = self.git.get_status_files()
        self.assertEqual(files[0]["path"], "özet şablonu.txt")
        self.assertTrue(self.git.stage_file(files[0]["path"]))
        self.assertTrue(self.git.get_status_files()[0]["staged"])

    def test_rename_reports_new_and_original_path(self):
        self.write("eski.txt")
        self.commit_all()
        self.git.run_git("mv", "eski.txt", "yeni.txt")
        files = self.git.get_status_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["status"], "R")
        self.assertEqual(files[0]["path"], "yeni.txt")
        self.assertEqual(files[0]["orig_path"], "eski.txt")

    def test_merge_conflict_is_reported(self):
        self.write("a.txt", "base\n")
        self.commit_all()
        self.git.create_and_checkout_branch("dal")
        self.write("a.txt", "dal\n")
        self.commit_all()
        self.git.checkout_branch("main")
        self.write("a.txt", "main\n")
        self.commit_all()
        ok, _ = self.git.git_branch_merge("dal")
        self.assertFalse(ok)
        files = self.git.get_status_files()
        self.assertEqual(files[0]["status"], "U")


class TestDiff(RepoTestCase):
    def test_untracked_text_diff(self):
        self.write("yeni.txt", "merhaba\n")
        diff = self.git.get_diff("yeni.txt")
        self.assertIn("+merhaba", diff)

    def test_untracked_binary_is_not_dumped(self):
        self.write("resim.bin", b"\x00\x01\x02PNG" * 100, mode="wb")
        diff = self.git.get_diff("resim.bin")
        self.assertIn("Binary", diff)


class TestCommitAndBranches(RepoTestCase):
    def test_commit_with_description(self):
        self.write("a.txt")
        self.git.stage_all()
        ok, _ = self.git.git_commit("Özet", "Açıklama")
        self.assertTrue(ok)
        c = self.git.get_commit_history(1)[0]
        self.assertEqual(c["summary"], "Özet")
        self.assertEqual(c["body"], "Açıklama")

    def test_empty_summary_rejected(self):
        ok, _ = self.git.git_commit("   ")
        self.assertFalse(ok)

    def test_invalid_branch_names_rejected(self):
        self.write("a.txt")
        self.commit_all()
        for bad in ("-f", "a..b", "with space", ""):
            ok, _ = self.git.create_and_checkout_branch(bad)
            self.assertFalse(ok, bad)
        ok, _ = self.git.create_and_checkout_branch("feature/özellik")
        self.assertTrue(ok)
        self.assertEqual(self.git.get_current_branch(), "feature/özellik")


class TestMisc(RepoTestCase):
    def test_local_user_info_written_to_repo(self):
        self.assertTrue(self.git.set_user_info("Yerel", "yerel@example.com", is_global=False))
        res = self.git.run_git("config", "--local", "user.name")
        self.assertEqual(res.stdout.strip(), "Yerel")

    def test_tag_push_requires_name(self):
        ok, _ = self.git.git_tag_push("origin", "")
        self.assertFalse(ok)

    def test_stash_with_message(self):
        self.write("a.txt", "1\n")
        self.commit_all()
        self.write("a.txt", "2\n")
        ok, out = self.git.git_stash_save("geçici iş")
        self.assertTrue(ok, out)
        self.assertIn("geçici iş", self.git.git_stash_list()[0])

    def test_sync_status_without_upstream(self):
        s = self.git.get_sync_status()
        self.assertEqual((s["ahead"], s["behind"], s["has_upstream"]), (0, 0, False))

    def test_network_ops_fail_fast_instead_of_prompting(self):
        # Would hang waiting for a username without GIT_TERMINAL_PROMPT=0
        start = time.time()
        ok, _ = self.git.git_clone("https://github.com/this-user-does-not-exist-xyz/nope.git",
                                   os.path.join(self.repo, "clone"))
        self.assertFalse(ok)
        self.assertLess(time.time() - start, 60)


class TestGitHubService(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(github_service.CONFIG_DIR, ignore_errors=True)
        self.gh = GitHubService()

    def test_config_inside_sandbox(self):
        self.assertTrue(github_service.CONFIG_DIR.startswith(_SANDBOX))

    def test_token_file_is_private(self):
        self.gh.set_token("ghp_test")
        mode = stat.S_IMODE(os.stat(github_service.CONFIG_FILE).st_mode)
        self.assertEqual(mode, 0o600)

    def test_logout_disables_gh_cli_fallback(self):
        self.gh.set_token("ghp_test")
        self.gh.logout()
        self.assertIsNone(self.gh.get_token())

    def test_init_new_repo_rejects_path_names(self):
        parent = tempfile.mkdtemp(dir=_SANDBOX)
        for bad in ("../kacis", "a/b", ".", "..", ""):
            ok, _ = self.gh.init_new_repo(parent, bad)
            self.assertFalse(ok, bad)
        ok, path = self.gh.init_new_repo(parent, "proje")
        self.assertTrue(ok, path)
        self.assertTrue(os.path.isdir(os.path.join(path, ".git")))


def _has_display():
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


@unittest.skipUnless(_has_display(), "GTK smoke test needs a display")
class TestWindowSmoke(RepoTestCase):
    """Drives the real window: these paths crashed with AttributeError before."""

    @classmethod
    def setUpClass(cls):
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, GLib
        cls.GLib = GLib
        Adw.init()
        from ui.window import GitDesktopWindow
        from ui.dialogs import GitHubAccountDialog
        cls.Window = GitDesktopWindow
        cls.AccountDialog = GitHubAccountDialog

    def pump(self, until, timeout=30):
        ctx = self.GLib.MainContext.default()
        end = time.time() + timeout
        while not until() and time.time() < end:
            ctx.iteration(False)
            time.sleep(0.01)
        return until()

    def test_commit_button(self):
        self.write("ö.txt")
        win = self.Window(None, initial_repo_path=self.repo)
        win.commit_summary_entry.set_text("GUI commit")
        win._on_commit_clicked(None)
        self.assertEqual(self.git.get_commit_history(1)[0]["summary"], "GUI commit")
        win.destroy()

    def test_sync_button_pushes(self):
        remote = tempfile.mkdtemp(dir=_SANDBOX)
        subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
        self.write("a.txt")
        self.commit_all()
        self.git.git_remote_add("origin", remote)
        self.git.git_push("origin", "main", set_upstream=True)
        self.write("b.txt")
        self.commit_all("ikinci")
        self.assertEqual(self.git.get_sync_status()["ahead"], 1)

        win = self.Window(None, initial_repo_path=self.repo)
        win._on_sync_clicked(None)
        self.assertTrue(self.pump(lambda: self.git.get_sync_status()["ahead"] == 0))
        self.assertTrue(self.pump(lambda: win.sync_btn.get_sensitive()))
        win.destroy()

    def test_account_dialog_login_form_builds(self):
        win = self.Window(None, initial_repo_path=self.repo)
        dlg = self.AccountDialog(win, win.gh_service)
        # No token in the sandbox: the login form (PasswordEntryRow) must render
        self.assertTrue(self.pump(lambda: hasattr(dlg, "token_entry")))
        dlg.destroy()
        win.destroy()


if __name__ == "__main__":
    unittest.main()
