"""Tests for the Qt edition. Real git in temp repos, Qt offscreen (no display needed).

Run:
    cd qt
    .venv/bin/python -m unittest discover -s tests -v
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Isolate from the real user before importing anything that reads config
_SANDBOX = tempfile.mkdtemp(prefix="qt-tests-")
os.environ["HOME"] = _SANDBOX
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SANDBOX, ".config")
os.environ["GIT_CONFIG_GLOBAL"] = os.path.join(_SANDBOX, ".gitconfig")
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
for k, v in (("user.name", "Test"), ("user.email", "test@example.com"), ("init.defaultBranch", "main")):
    subprocess.run(["git", "config", "--global", k, v], check=True)

import github_service  # noqa: E402
from git_service import GitService, github_auth_args  # noqa: E402

# gh may read the real user's token from the system keyring; never use it here
_real_run = subprocess.run
github_service.subprocess.run = lambda args, *a, **kw: (
    subprocess.CompletedProcess(args, 1, "", "") if args and args[0] == "gh" else _real_run(args, *a, **kw))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from ui import theme  # noqa: E402
from ui.diff_view import parse_diff  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.workers import wait_for_tasks  # noqa: E402

theme.apply_theme(app, "light")


def tearDownModule():
    shutil.rmtree(_SANDBOX, ignore_errors=True)


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(dir=_SANDBOX)
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.git = GitService(self.repo)

    def write(self, name, content="x\n"):
        path = os.path.join(self.repo, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    def commit_all(self, msg="c"):
        self.git.stage_all()
        ok, out = self.git.git_commit(msg)
        self.assertTrue(ok, out)

    def add_remote(self):
        remote = tempfile.mkdtemp(dir=_SANDBOX)
        subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
        self.git.git_remote_add("origin", remote)
        return remote


# ==================== backend ====================
class TestBackend(RepoCase):
    def test_commit_files_and_diff(self):
        self.write("a.txt", "1\n")
        self.commit_all()
        self.write("a.txt", "2\n")
        self.write("ö/yeni.txt", "y\n")
        self.git.run_git("mv", "a.txt", "b.txt")
        self.commit_all("ikinci")
        head = self.git.get_commit_history(1)[0]["hash"]
        files = {f["path"]: f for f in self.git.get_commit_files(head)}
        self.assertEqual(files["ö/yeni.txt"]["status"], "A")
        self.assertIn("b.txt", files)
        diff = self.git.get_commit_file_diff(head, "ö/yeni.txt")
        self.assertIn("+y", diff)

    def test_root_commit_can_be_undone(self):
        self.write("a.txt")
        self.commit_all("ilk")
        ok, msg = self.git.undo_last_commit()
        self.assertTrue(ok, msg)
        self.assertFalse(self.git.has_commits())
        self.assertTrue(self.git.get_status_files()[0]["staged"])

    def test_history_paging(self):
        for i in range(5):
            self.write("a.txt", f"{i}\n")
            self.commit_all(f"c{i}")
        page1 = self.git.get_commit_history(3, 0)
        page2 = self.git.get_commit_history(3, 3)
        self.assertEqual([c["summary"] for c in page1 + page2], ["c4", "c3", "c2", "c1", "c0"])

    def test_desktop_stash_roundtrip(self):
        self.write("a.txt")
        self.commit_all()
        self.write("yeni.txt")
        ok, msg = self.git.stash_all()
        self.assertTrue(ok, msg)
        self.assertEqual(self.git.get_status_files(), [])
        self.assertTrue(self.git.get_desktop_stash("main").startswith("stash@{"))
        self.assertEqual(self.git.get_desktop_stash("baska"), "")

    def test_gitignore(self):
        self.write(".gitignore", "a")  # no trailing newline
        self.assertTrue(self.git.add_to_gitignore("*.log"))
        self.assertTrue(self.git.add_to_gitignore("*.log"))  # not duplicated
        with open(os.path.join(self.repo, ".gitignore")) as f:
            self.assertEqual(f.read(), "a\n*.log\n")

    def test_publish_and_divergent_pull(self):
        remote = self.add_remote()
        self.write("a.txt", "a\n")
        self.commit_all()
        ok, msg = self.git.git_publish_branch()
        self.assertTrue(ok, msg)
        # someone else pushes, we commit locally -> divergent
        other = tempfile.mkdtemp(dir=_SANDBOX)
        subprocess.run(["git", "clone", "-q", remote, other], check=True)
        with open(os.path.join(other, "b.txt"), "w") as f:
            f.write("b\n")
        subprocess.run(["git", "-C", other, "add", "."], check=True)
        subprocess.run(["git", "-C", other, "commit", "-qm", "uzak"], check=True)
        subprocess.run(["git", "-C", other, "push", "-q"], check=True)
        self.write("c.txt", "c\n")
        self.commit_all("yerel")
        self.git.git_fetch("origin")
        s = self.git.get_sync_status()
        self.assertEqual((s["ahead"], s["behind"]), (1, 1))
        ok, msg = self.git.git_pull()
        self.assertTrue(ok, msg)  # merged, not "need to specify how to reconcile"
        self.assertIsNotNone(self.git.get_last_fetch_time())

    def test_token_never_on_command_line(self):
        args, env = github_auth_args("ghp_secret")
        self.assertNotIn("ghp_secret", " ".join(args))
        self.assertEqual(env["GDL_GITHUB_TOKEN"], "ghp_secret")
        self.assertEqual(github_auth_args(None), ([], {}))

    def test_token_helper_answers_git(self):
        args, env = github_auth_args("ghp_secret")
        res = subprocess.run(
            ["git", *args, "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
            capture_output=True, text=True, env={**os.environ, **env, "GIT_TERMINAL_PROMPT": "0"})
        self.assertIn("password=ghp_secret", res.stdout)
        self.assertIn("username=x-access-token", res.stdout)


class TestDiffParser(unittest.TestCase):
    def test_line_numbers(self):
        diff = ("diff --git a/f b/f\nindex 1..2 100644\n--- a/f\n+++ b/f\n"
                "@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n")
        rows, binary = parse_diff(diff)
        self.assertFalse(binary)
        self.assertEqual([(k, o, n) for k, o, n, _ in rows],
                         [("hunk", None, None), ("ctx", 1, 1), ("del", 2, None), ("add", None, 2), ("ctx", 3, 3)])

    def test_binary(self):
        self.assertEqual(parse_diff("diff --git a/x b/x\nBinary files /dev/null and b/x differ\n"), ([], True))


# ==================== UI (offscreen) ====================
class UICase(RepoCase):
    def setUp(self):
        super().setUp()
        self.win = None

    def tearDown(self):
        if self.win:
            self.win.close()
            self.win.deleteLater()
        wait_for_tasks()
        app.processEvents()

    def open(self):
        self.win = MainWindow(self.repo)
        self.win.show()
        app.processEvents()
        return self.win

    def settle(self):
        wait_for_tasks()
        for _ in range(5):
            app.processEvents()


class TestMainWindow(UICase):
    def test_changes_list_and_commit_selected_only(self):
        self.write("a.txt")
        self.commit_all()
        self.write("seç.txt")
        self.write("atla.txt")
        w = self.open()
        self.assertEqual(w.changes.count_label.text(), "2 changed files")
        self.assertEqual(w.branch_btn.title.text(), "main")
        # uncheck one file, commit only the other
        for i in range(w.changes.list.count()):
            item = w.changes.list.item(i)
            if item.data(Qt.UserRole) == "atla.txt":
                item.setCheckState(Qt.Unchecked)
        self.assertEqual(w.changes.all_check.checkState(), Qt.PartiallyChecked)
        w.changes.summary.setText("Sadece seç")
        self.assertTrue(w.changes.commit_btn.isEnabled())
        w.changes.commit_btn.click()
        self.assertEqual(self.git.get_commit_history(1)[0]["summary"], "Sadece seç")
        remaining = [f["path"] for f in self.git.get_status_files()]
        self.assertEqual(remaining, ["atla.txt"])
        # undo banner appears and restores the message
        self.assertFalse(w.changes.undo_banner.isHidden())
        w.changes.undo_banner.btn1.click()
        self.assertEqual(w.changes.summary.text(), "Sadece seç")
        self.assertEqual(len(self.git.get_status_files()), 2)

    def test_commit_disabled_without_summary(self):
        self.write("a.txt")
        w = self.open()
        self.assertFalse(w.changes.commit_btn.isEnabled())
        self.assertEqual(w.changes.commit_btn.text(), "Commit to main")

    def test_history_tab_shows_commit_files(self):
        self.write("a.txt")
        self.commit_all("ilk")
        self.write("b.txt", "b\n")
        self.commit_all("ikinci")
        w = self.open()
        w.tabs.setCurrentIndex(1)
        app.processEvents()
        self.assertEqual(w.history.count(), 2)
        self.assertEqual(w.commit_view.summary_label.text(), "ikinci")
        self.assertEqual(w.commit_view.files.item(0).text(), "b.txt")
        self.assertIs(w.commit_view.diff.stack.currentWidget(), w.commit_view.diff.editor)

    def test_sync_button_publish_then_push(self):
        self.write("a.txt")
        self.commit_all()
        self.add_remote()
        w = self.open()
        self.assertEqual(w.sync_btn.title.text(), "Publish branch")
        w.sync_btn.click()
        self.settle()
        self.assertTrue(self.git.get_sync_status()["has_upstream"])
        self.assertEqual(w.sync_btn.title.text(), "Fetch origin")
        self.write("b.txt")
        self.commit_all()
        w.refresh(force=True)
        self.assertEqual(w.sync_btn.title.text(), "Push origin")
        w.sync_btn.click()
        self.settle()
        self.assertEqual(self.git.get_sync_status()["ahead"], 0)

    def test_switch_branch_leaving_changes_stashes_them(self):
        self.write("a.txt")
        self.commit_all()
        self.git.git_branch_create("dal")
        self.write("wip.txt")
        w = self.open()
        # answer "Leave my changes on main"
        orig_exec = QMessageBox.exec

        def fake_exec(box):
            box._clicked = next(b for b in box.buttons() if b.text().startswith("Leave"))
            return 0
        QMessageBox.exec = fake_exec
        QMessageBox.clickedButton = lambda box: box._clicked
        try:
            w.switch_branch("dal", "local")
        finally:
            QMessageBox.exec = orig_exec
            del QMessageBox.clickedButton
        self.assertEqual(self.git.get_current_branch(), "dal")
        self.assertEqual(w.changes.count_label.text(), "0 changed files")
        w.switch_branch("main", "local")
        self.assertFalse(w.changes.stash_banner.isHidden())
        w.changes.stash_banner.btn1.click()  # Restore
        self.assertEqual([f["path"] for f in self.git.get_status_files()], ["wip.txt"])

    def test_branch_popup_filter(self):
        self.write("a.txt")
        self.commit_all()
        for b in ("feature/giris", "fix/hata"):
            self.git.git_branch_create(b)
        w = self.open()
        w.show_branch_list()
        popup = w.branch_popup
        popup.filter.setText("giris")
        visible = [popup.list.item(i).text().strip() for i in range(popup.list.count())
                   if not popup.list.item(i).isHidden()]
        self.assertEqual(visible, ["LOCAL BRANCHES", "feature/giris"])
        popup.filter.returnPressed.emit()
        self.assertEqual(self.git.get_current_branch(), "feature/giris")

    def test_not_a_repo_shows_blank_slate(self):
        empty = tempfile.mkdtemp(dir=_SANDBOX)
        self.win = MainWindow(empty)
        self.assertIs(self.win.main_stack.currentWidget(), self.win.blank)
        self.assertFalse(self.win.branch_btn.isEnabled())

    def test_dark_theme_applies(self):
        self.assertTrue(theme.apply_theme(app, "dark"))
        self.assertEqual(theme.colors()["bg"], theme.DARK["bg"])
        theme.apply_theme(app, "light")


if __name__ == "__main__":
    unittest.main()
