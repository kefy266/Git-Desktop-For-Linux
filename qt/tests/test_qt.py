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
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QPushButton  # noqa: E402

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

    def test_file_rows_paint_and_toggle_checkbox(self):
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QStyleOptionViewItem
        from ui.delegates import is_checked
        self.write("a.txt")
        w = self.open()
        lst = w.changes.list
        index = lst.model().index(0, 0)
        self.assertTrue(is_checked(index))  # delegate must see the item as checked
        option = QStyleOptionViewItem()
        option.rect = lst.visualRect(index)
        delegate = lst.itemDelegate()
        box = delegate._checkbox_rect(option).center()
        click = QMouseEvent(QEvent.MouseButtonRelease, QPointF(box), QPointF(box),
                            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        delegate.editorEvent(click, lst.model(), option, index)
        self.assertFalse(is_checked(index))
        self.assertFalse(w.changes.commit_btn.isEnabled() and w.changes.checked_files())

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




# ==================== GitHub repositories ====================
def _fake_repo(owner, name, **extra):
    return {"name": name, "full_name": f"{owner}/{name}", "owner": {"login": owner},
            "description": extra.get("description", ""), "clone_url": f"https://github.com/{owner}/{name}.git",
            "ssh_url": "", "html_url": "", "private": extra.get("private", False), "fork": False,
            "archived": False, "stargazers_count": 0, "updated_at": "2026-10-01T00:00:00Z"}


class _FakeResponse:
    def __init__(self, items, next_url=None):
        self.status_code = 200
        self._items = items
        self.links = {"next": {"url": next_url}} if next_url else {}

    def json(self):
        return self._items


class TestGitHubRepos(unittest.TestCase):
    def setUp(self):
        self.gh = github_service.GitHubService()
        self.gh.get_token = lambda: "ghp_test"
        self._orig_get = github_service.requests.get

    def tearDown(self):
        github_service.requests.get = self._orig_get

    def test_follows_all_pages(self):
        pages = {
            "p1": _FakeResponse([_fake_repo("me", f"r{i}") for i in range(100)], "p2"),
            "p2": _FakeResponse([_fake_repo("org", f"o{i}") for i in range(100)], "p3"),
            "p3": _FakeResponse([_fake_repo("org", "last")]),
        }
        calls = []

        def fake_get(url, headers=None, timeout=None):
            calls.append(url)
            return pages["p1"] if "api.github.com" in url else pages[url]

        github_service.requests.get = fake_get
        repos = self.gh.get_user_repos()
        self.assertEqual(len(repos), 201)  # used to stop at 100
        self.assertEqual(len(calls), 3)
        self.assertIn("affiliation=owner,collaborator,organization_member", calls[0])
        self.assertEqual(repos[-1]["owner"], "org")

    def test_grouping_puts_me_first(self):
        from ui.delegates import group_repos
        repos = [{"full_name": f"{o}/x", "owner": o} for o in ("zeta-org", "me", "acme")]
        self.assertEqual([o for o, _ in group_repos(repos, "me")], ["me", "acme", "zeta-org"])


class TestRepoPopupGitHub(UICase):
    def _github_repos(self):
        return [{"name": n, "full_name": f"{o}/{n}", "owner": o, "description": "", "clone_url": "",
                 "is_private": False, "is_fork": False, "is_archived": False, "updated_at": ""}
                for o, n in (("me", "app"), ("me", "dotfiles"), ("acme", "site"))]

    def test_popup_lists_account_repos_grouped(self):
        self.write("a.txt")
        self.commit_all()
        w = self.open()
        w.github_repos, w.github_login = self._github_repos(), "me"
        w.show_repository_list()
        texts = [w.repo_popup.list.item(i).text().strip() for i in range(w.repo_popup.list.count())]
        self.assertIn("GITHUB.COM · ME", texts)
        self.assertIn("GITHUB.COM · ACME", texts)
        self.assertLess(texts.index("GITHUB.COM · ME"), texts.index("GITHUB.COM · ACME"))
        self.assertIn("dotfiles", texts)
        w.repo_popup.hide()

    def test_cloned_repo_not_listed_twice(self):
        self.write("a.txt")
        self.commit_all()
        self.git.git_remote_add("origin", "https://github.com/me/app.git")
        w = self.open()
        w.github_repos, w.github_login = self._github_repos(), "me"
        w.show_repository_list()
        github_entries = [w.repo_popup.list.item(i).data(Qt.UserRole) for i in range(w.repo_popup.list.count())
                          if w.repo_popup.list.item(i).data(Qt.UserRole + 1) == "github"]
        self.assertNotIn("me/app", github_entries)
        self.assertIn("me/dotfiles", github_entries)
        w.repo_popup.hide()

    def test_signed_out_shows_sign_in_entry(self):
        w = self.open()
        w.github_repos, w._signed_out = None, True
        w.show_repository_list()
        kinds = [w.repo_popup.list.item(i).data(Qt.UserRole + 1) for i in range(w.repo_popup.list.count())]
        self.assertIn("signin", kinds)
        w.repo_popup.hide()

    def test_clone_dialog_preselects_and_groups(self):
        from ui.dialogs import CloneDialog
        from ui.delegates import REPO_ROLE
        dlg = CloneDialog(github_service.GitHubService(), repos=self._github_repos(), preselect="me/dotfiles", me="me")
        self.assertEqual(dlg.repo_list.currentItem().data(REPO_ROLE)["full_name"], "me/dotfiles")
        self.assertTrue(dlg.path_edit.text().endswith("dotfiles"))
        self.assertEqual(dlg.owner_combo.count(), 3)  # All + me + acme
        dlg.owner_combo.setCurrentIndex(dlg.owner_combo.findData("acme"))
        names = [dlg.repo_list.item(i).text() for i in range(dlg.repo_list.count())
                 if dlg.repo_list.item(i).data(REPO_ROLE)]
        self.assertEqual(names, ["acme/site"])
        self.assertIn("3 repositories from 2 accounts", dlg.gh_status.text())


# ==================== account: sign in / sign out ====================
class TestAccount(UICase):
    PROFILE = {"login": "kefy266", "name": "Kağan Efe", "avatar_url": "", "html_url": "https://github.com/kefy266"}

    def setUp(self):
        super().setUp()
        self.gh_cls = github_service.GitHubService
        self._orig = (self.gh_cls.get_user_profile, self.gh_cls.get_user_repos)
        valid = "ghp_valid"
        self.gh_cls.get_user_profile = lambda s, token=None: dict(self.PROFILE) if (token or s.get_token()) == valid else None
        self.gh_cls.get_user_repos = lambda s, limit=None: [{"name": "app", "full_name": "kefy266/app", "owner": "kefy266",
                                                              "description": "", "clone_url": "", "is_private": False,
                                                              "is_fork": False, "is_archived": False, "updated_at": ""}]

    def tearDown(self):
        self.gh_cls.get_user_profile, self.gh_cls.get_user_repos = self._orig
        github_service.GitHubService().logout()
        super().tearDown()

    def popup_texts(self, w):
        return [lbl.text() for lbl in w.account_popup.findChildren(QLabel)] + \
               [b.text().strip() for b in w.account_popup.findChildren(QPushButton)]

    def test_signed_out_card_offers_sign_in(self):
        w = self.open()
        self.settle()
        self.assertIsNone(w.github_profile)
        w.show_account_menu()
        self.settle()
        self.assertIn("Sign in to GitHub.com", self.popup_texts(w))
        w.account_popup.hide()

    def test_sign_in_dialog_rejects_bad_token_then_signs_in(self):
        from ui.account import SignInDialog
        gh = github_service.GitHubService()
        dlg = SignInDialog(gh)
        dlg.token_edit.setText("ghp_wrong")
        dlg._sign_in()
        self.settle()
        self.assertFalse(dlg.status.isHidden())
        self.assertIsNone(gh.config.get("token"))  # bad token is never saved
        dlg.token_edit.setText("ghp_valid")
        dlg._sign_in()
        self.settle()
        self.assertEqual(dlg.result(), QDialog.Accepted)
        self.assertEqual(github_service.GitHubService().config.get("token"), "ghp_valid")

    def test_signed_in_profile_then_sign_out(self):
        github_service.GitHubService().set_token("ghp_valid")
        w = self.open()
        self.settle()
        self.assertEqual(w.github_login, "kefy266")
        self.assertEqual(w.git.github_token, "ghp_valid")
        self.assertEqual(w.profile_btn.toolTip(), "Signed in as @kefy266")
        w.show_account_menu()
        texts = self.popup_texts(w)
        self.assertIn("Kağan Efe", texts)
        self.assertIn("@kefy266", texts)
        self.assertIn("1 repositories on GitHub.com", texts)
        self.assertIn("Sign out", texts)
        w.account_popup.hide()

        from ui import account
        opened = []
        orig_q, orig_exec = QMessageBox.question, account.SignInDialog.exec
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        account.SignInDialog.exec = lambda dlg: opened.append(dlg) or 0  # user cancels
        try:
            w.sign_out()
            app.processEvents()
        finally:
            QMessageBox.question, account.SignInDialog.exec = orig_q, orig_exec
        self.assertEqual(len(opened), 1)  # sign-in screen opens right after signing out
        self.assertIsNone(w.github_profile)
        self.assertIsNone(w.git.github_token)
        self.assertIsNone(w.github_repos)
        self.assertIsNone(github_service.GitHubService().get_token())
        w.show_repository_list()
        kinds = [w.repo_popup.list.item(i).data(Qt.UserRole + 1) for i in range(w.repo_popup.list.count())]
        self.assertIn("signin", kinds)
        w.repo_popup.hide()

    def test_revoked_token_counts_as_signed_out(self):
        github_service.GitHubService().set_token("ghp_revoked")
        w = self.open()
        self.settle()
        self.assertIsNone(w.github_profile)
        self.assertIsNone(w.git.github_token)


if __name__ == "__main__":
    unittest.main()
