"""Main window, modeled on GitHub Desktop (https://github.com/desktop/desktop)."""

import os
import shutil
import subprocess
import time
from typing import Optional

from PySide6.QtCore import QEvent, QFile, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QSplitter, QStackedWidget, QTabBar, QVBoxLayout, QWidget,
)

from git_service import GitService
from github_service import GitHubService
from ui import theme
from ui.changes_view import ChangesView
from ui.dialogs import BranchNameDialog, CloneDialog, CreateRepoDialog, MergeDialog, OptionsDialog
from ui.diff_view import DiffView
from ui.history_view import CommitView, HistoryList
from ui.toolbar import BranchPopup, RepositoryPopup, ToolbarButton
from ui.workers import run_async

AUTO_FETCH_MS = 30 * 60 * 1000
TERMINALS = ["konsole", "gnome-terminal", "kgx", "kitty", "alacritty", "wezterm", "foot",
             "xfce4-terminal", "tilix", "xterm"]


def time_ago(ts: Optional[float]) -> str:
    if not ts:
        return "Never fetched"
    secs = max(0, int(time.time() - ts))
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if secs >= size:
            n = secs // size
            return f"Last fetched {n} {unit}{'s' if n > 1 else ''} ago"
    return "Last fetched just now"


class MainWindow(QMainWindow):
    def __init__(self, initial_repo: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("Git Desktop For Linux")
        self.resize(1180, 760)

        self.gh = GitHubService()
        self.git = GitService(os.getcwd())
        self.settings = QSettings("GitDesktopLinux", "qt")
        self._busy = False             # a network operation is running
        self._last_refresh = 0.0
        self._undo_hash = ""           # HEAD right after a commit made here
        self._undo_message = ("", "")

        self._build_toolbar()
        self._build_body()
        self._build_menus()

        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        self.fetch_timer = QTimer(self)
        self.fetch_timer.setInterval(AUTO_FETCH_MS)
        self.fetch_timer.timeout.connect(lambda: self.sync("fetch", quiet=True))
        self.fetch_timer.start()

        self._load_token()
        repo = initial_repo or self.gh.get_setting("last_repo") or \
            next((r["path"] for r in self.gh.get_recent_repos()), None)
        if repo:
            self.open_repository(repo)
        else:
            self.refresh()

    # ======================================================================
    # Layout
    # ======================================================================
    def _build_toolbar(self):
        bar = QWidget(objectName="Toolbar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.repo_btn = ToolbarButton("▣", "Current repository", width=260)
        self.repo_btn.clicked.connect(self.show_repository_list)
        self.branch_btn = ToolbarButton("⎇", "Current branch", width=240)
        self.branch_btn.clicked.connect(self.show_branch_list)
        self.sync_btn = ToolbarButton("⟳", "Never fetched", dropdown=False, width=230)
        self.sync_btn.clicked.connect(lambda: self.sync())
        for b in (self.repo_btn, self.branch_btn, self.sync_btn):
            lay.addWidget(b)
        lay.addStretch(1)

        self.repo_popup = RepositoryPopup(self)
        self.repo_popup.activated.connect(lambda path, _k: self.open_repository(path))
        self.repo_popup.add_existing.connect(self.add_existing_repository)
        self.repo_popup.clone.connect(self.clone_repository)
        self.repo_popup.create.connect(self.create_repository)
        self.repo_popup.remove_repo.connect(self._remove_recent)
        self.repo_popup.closed.connect(lambda: self.repo_btn.set_open(False))

        self.branch_popup = BranchPopup(self)
        self.branch_popup.activated.connect(self.switch_branch)
        self.branch_popup.new_branch.connect(self.new_branch)
        self.branch_popup.rename_branch.connect(self.rename_branch)
        self.branch_popup.delete_branch.connect(self.delete_branch)
        self.branch_popup.closed.connect(lambda: self.branch_btn.set_open(False))

        self.toolbar_widget = bar

    def _build_body(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.toolbar_widget)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)

        # ---- sidebar ----
        sidebar = QWidget(objectName="Sidebar")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self.tabs = QTabBar()
        self.tabs.setExpanding(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setDrawBase(False)
        self.tabs.addTab("Changes")
        self.tabs.addTab("History")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        sl.addWidget(self.tabs)

        self.side_stack = QStackedWidget()
        self.changes = ChangesView()
        self.changes.file_selected.connect(self._on_change_selected)
        self.changes.commit_requested.connect(self.commit)
        self.changes.file_context_menu.connect(self._fill_file_menu)
        self.changes.discard_all_requested.connect(self.discard_all_changes)
        self.changes.undo_requested.connect(self.undo_commit)
        self.changes.restore_stash_requested.connect(self.restore_stash)
        self.changes.discard_stash_requested.connect(self.discard_stash)
        self.changes.abort_merge_requested.connect(self.abort_merge)
        self.history = HistoryList(lambda limit, skip: self.git.get_commit_history(limit, skip))
        self.history.commit_selected.connect(self._on_commit_selected)
        self.side_stack.addWidget(self.changes)
        self.side_stack.addWidget(self.history)
        sl.addWidget(self.side_stack, 1)
        self.splitter.addWidget(sidebar)

        # ---- main area ----
        self.main_stack = QStackedWidget()
        self.diff = DiffView()
        self.diff.open_in_editor.connect(lambda p: self.open_in_editor(p))
        self.commit_view = CommitView(self.git)
        self.blank = self._build_blank_slate()
        self.main_stack.addWidget(self.diff)
        self.main_stack.addWidget(self.commit_view)
        self.main_stack.addWidget(self.blank)
        self.splitter.addWidget(self.main_stack)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([320, 860])
        state = self.settings.value("splitter")
        if state is not None:
            self.splitter.restoreState(state)

        root.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

    def _build_blank_slate(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        title = QLabel("Let's get started!", objectName="BlankTitle", alignment=Qt.AlignCenter)
        lay.addWidget(title)
        lay.addWidget(QLabel("Add a repository to Git Desktop to start collaborating",
                             objectName="Dim", alignment=Qt.AlignCenter))
        lay.addSpacing(16)
        for text, slot in (("Clone a repository from the Internet…", self.clone_repository),
                           ("Create a New Repository on your hard drive…", self.create_repository),
                           ("Add an Existing Repository from your hard drive…", self.add_existing_repository)):
            btn = QPushButton(text)
            btn.setMinimumWidth(380)
            btn.setMinimumHeight(36)
            btn.clicked.connect(slot)
            lay.addWidget(btn, alignment=Qt.AlignCenter)
        return w

    def _build_menus(self):
        mb = self.menuBar()
        self.repo_actions = []  # enabled only while a repository is open

        def act(menu, text, slot, shortcut=None, needs_repo=True):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(lambda _checked=False: slot())
            menu.addAction(a)
            if needs_repo:
                self.repo_actions.append(a)
            return a

        m = mb.addMenu("&File")
        act(m, "New repository…", self.create_repository, "Ctrl+N", False)
        act(m, "Add local repository…", self.add_existing_repository, "Ctrl+O", False)
        act(m, "Clone repository…", self.clone_repository, "Ctrl+Shift+O", False)
        m.addSeparator()
        act(m, "Options…", self.show_options, "Ctrl+,", False)
        m.addSeparator()
        act(m, "Exit", self.close, "Ctrl+Q", False)

        m = mb.addMenu("&View")
        act(m, "Changes", lambda: self.tabs.setCurrentIndex(0), "Ctrl+1")
        act(m, "History", lambda: self.tabs.setCurrentIndex(1), "Ctrl+2")
        act(m, "Repository list", self.show_repository_list, "Ctrl+T", False)
        act(m, "Branches list", self.show_branch_list, "Ctrl+B")
        m.addSeparator()
        act(m, "Refresh", lambda: self.refresh(force=True), "F5")

        m = mb.addMenu("&Repository")
        act(m, "Push", lambda: self.sync("push"), "Ctrl+P")
        act(m, "Pull", lambda: self.sync("pull"), "Ctrl+Shift+P")
        act(m, "Fetch", lambda: self.sync("fetch"), "Ctrl+Shift+T")
        act(m, "Remove from list", lambda: self._remove_recent(self.git.repo_path))
        m.addSeparator()
        act(m, "Open in external editor", lambda: self.open_in_editor(), "Ctrl+Shift+A")
        act(m, "Open in terminal", self.open_in_terminal, "Ctrl+`")
        act(m, "Show in file manager", lambda: self.show_in_file_manager(), "Ctrl+Shift+F")

        m = mb.addMenu("&Branch")
        act(m, "New branch…", self.new_branch, "Ctrl+Shift+N")
        act(m, "Rename…", lambda: self.rename_branch(self.git.get_current_branch()), "Ctrl+Shift+R")
        act(m, "Delete…", lambda: self.delete_branch(self.git.get_current_branch()), "Ctrl+Shift+D")
        m.addSeparator()
        act(m, "Discard all changes…", self.discard_all_changes, "Ctrl+Shift+Backspace")
        act(m, "Stash all changes", self.stash_changes, "Ctrl+Shift+S")
        act(m, "Restore stash", self.restore_stash)
        m.addSeparator()
        act(m, "Merge into current branch…", self.merge_into_current, "Ctrl+Shift+M")
        act(m, "Abort merge", self.abort_merge)

        m = mb.addMenu("&Help")
        act(m, "About Git Desktop For Linux", self.show_about, None, False)

    # ======================================================================
    # Repository state
    # ======================================================================
    def open_repository(self, path: Optional[str]):
        if not path or not os.path.isdir(path):
            if path:
                self._remove_recent(path, refresh=False)
            self.git.set_repo_path(os.path.expanduser("~"))
            self.refresh(force=True)
            return
        self.git.set_repo_path(path)
        if self.git.is_git_repo():
            # open the top level even if a subfolder was chosen
            top = self.git.run_git("rev-parse", "--show-toplevel").stdout.strip()
            if top:
                self.git.set_repo_path(top)
            self.gh.add_recent_repo(self.git.repo_path)
            self.gh.set_setting("last_repo", self.git.repo_path)
        self._undo_hash = ""
        self.changes.clear_message()
        self.refresh(force=True)

    def refresh(self, force: bool = False):
        """Re-read local git state. Cheap (no network), so it runs on the GUI thread."""
        now = time.time()
        if not force and now - self._last_refresh < 1.0:
            return
        self._last_refresh = now

        is_repo = self.git.is_git_repo()
        for a in self.repo_actions:
            a.setEnabled(is_repo)
        self.branch_btn.setEnabled(is_repo)
        self.tabs.setEnabled(is_repo)
        self.side_stack.setEnabled(is_repo)

        if not is_repo:
            self.setWindowTitle("Git Desktop For Linux")
            self.repo_btn.set_texts("Add a repository")
            self.branch_btn.set_texts("—")
            self.sync_btn.set_texts("—", "")
            self.sync_btn.setEnabled(False)
            self.changes.set_files([])
            self.history.clear()
            self.main_stack.setCurrentWidget(self.blank)
            return

        name = self.git.get_repo_name()
        branch = self.git.get_current_branch()
        self.setWindowTitle(f"{name} — Git Desktop For Linux")
        self.repo_btn.set_texts(name)
        self.branch_btn.set_texts(branch)

        merging = self.git.is_merging()
        self.changes.set_branch(branch, merging)
        self.changes.set_files(self.git.get_status_files())
        self.changes.stash_banner.setVisible(bool(self.git.get_desktop_stash(branch)))

        head = self.git.run_git("rev-parse", "-q", "--verify", "HEAD").stdout.strip()
        if self.history.head_hash() != head or force:
            self.history.reload()
        sync = self._update_sync_button()
        # "Undo" stays available until the commit is pushed (GitHub Desktop rule)
        can_undo = bool(self._undo_hash) and head == self._undo_hash and \
            (not sync["has_upstream"] or sync["ahead"] > 0)
        self.changes.show_undo(self._undo_message[0] if can_undo else "")
        self._on_tab_changed(self.tabs.currentIndex())

    def _update_sync_button(self) -> dict:
        sync = self.git.get_sync_status()
        self.sync_btn.setEnabled(not self._busy)
        if self._busy:
            return sync
        has_remote = bool(self.git.git_remote_list())
        if not has_remote:
            self._sync_mode = "none"
            self.sync_btn.set_texts("No remote", "Add a remote to publish", "⟳")
            self.sync_btn.setEnabled(False)
        elif not sync["has_upstream"]:
            self._sync_mode = "publish"
            self.sync_btn.set_texts("Publish branch", "Publish this branch to origin", "↑")
        elif sync["behind"] > 0:
            self._sync_mode = "pull"
            extra = f"  ↑{sync['ahead']}" if sync["ahead"] else ""
            self.sync_btn.set_texts("Pull origin", f"↓{sync['behind']}{extra}  {time_ago(self.git.get_last_fetch_time())}", "↓")
        elif sync["ahead"] > 0:
            self._sync_mode = "push"
            self.sync_btn.set_texts("Push origin", f"↑{sync['ahead']}  {time_ago(self.git.get_last_fetch_time())}", "↑")
        else:
            self._sync_mode = "fetch"
            self.sync_btn.set_texts("Fetch origin", time_ago(self.git.get_last_fetch_time()), "⟳")
        return sync

    def event(self, e):
        # GitHub Desktop re-reads status whenever the window regains focus
        if e.type() == QEvent.WindowActivate:
            QTimer.singleShot(0, self.refresh)
        return super().event(e)

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.saveState())
        super().closeEvent(e)

    # ======================================================================
    # Selection -> main area
    # ======================================================================
    def _on_tab_changed(self, index: int):
        if not self.git.is_git_repo():
            return
        self.side_stack.setCurrentIndex(index)
        if index == 0:
            self.main_stack.setCurrentWidget(self.diff)
            self._on_change_selected(self._current_change())
        else:
            self.main_stack.setCurrentWidget(self.commit_view)
            if self.history.currentItem() is None and self.history.count():
                self.history.setCurrentRow(0)
            elif self.history.currentItem() is not None:
                # selection may have changed while the Changes tab was showing
                commit = self.history.currentItem().data(Qt.UserRole)
                if not self.commit_view.commit or self.commit_view.commit["hash"] != commit["hash"]:
                    self.commit_view.show_commit(commit)
            else:
                self.commit_view.show_commit({})

    def _current_change(self) -> dict:
        item = self.changes.list.currentItem()
        return item.data(Qt.UserRole + 1) if item else {}

    def _on_change_selected(self, f: dict):
        if self.tabs.currentIndex() != 0:
            return
        if not f:
            self.diff.show_message("No local changes.\n\nThere are no uncommitted changes in this repository.")
            return
        self.diff.set_diff(f["path"], self.git.get_diff(f["path"]), f["status"], can_open=f["status"] != "D")

    def _on_commit_selected(self, commit: dict):
        if self.tabs.currentIndex() == 1:
            self.commit_view.show_commit(commit)

    # ======================================================================
    # Popups & repository management
    # ======================================================================
    def show_repository_list(self):
        self.repo_popup.set_repositories(self.gh.get_recent_repos(), self.git.repo_path)
        self.repo_btn.set_open(True)
        self.repo_popup.popup_below(self.repo_btn)

    def show_branch_list(self):
        if not self.git.is_git_repo():
            return
        branches = self.git.get_branches()
        self.branch_popup.set_branches(branches["local"], branches["remote"], self.git.get_current_branch())
        self.branch_btn.set_open(True)
        self.branch_popup.popup_below(self.branch_btn)

    def add_existing_repository(self):
        path = QFileDialog.getExistingDirectory(self, "Add local repository", os.path.expanduser("~"))
        if not path:
            return
        probe = GitService(path)
        if not probe.is_git_repo():
            answer = QMessageBox.question(
                self, "Not a Git repository",
                f"'{path}' does not appear to be a Git repository.\n\nCreate a repository here?")
            if answer != QMessageBox.Yes:
                return
            ok, msg = probe.git_init()
            if not ok:
                self._error("Could not create repository", msg)
                return
        self.open_repository(path)

    def clone_repository(self):
        dlg = CloneDialog(self.gh, self)
        if dlg.exec() and dlg.result_path:
            self.open_repository(dlg.result_path)

    def create_repository(self):
        dlg = CreateRepoDialog(self.gh, self)
        if dlg.exec() and dlg.result_path:
            self.open_repository(dlg.result_path)

    def _remove_recent(self, path: str, refresh: bool = True):
        self.gh.remove_recent_repo(path)
        if refresh and os.path.abspath(path) == self.git.repo_path:
            nxt = next((r["path"] for r in self.gh.get_recent_repos()), None)
            self.gh.set_setting("last_repo", nxt)
            self.open_repository(nxt)

    # ======================================================================
    # Branches
    # ======================================================================
    def switch_branch(self, name: str, kind: str = "local"):
        current = self.git.get_current_branch()
        if kind == "local" and name == current:
            return
        target = name.split("/", 1)[-1] if kind == "remote" else name
        if self.changes.all_files():
            box = QMessageBox(self)
            box.setWindowTitle("Switch branch")
            box.setText(f"You have changes on <b>{_esc(current)}</b>.")
            box.setInformativeText("What would you like to do with them?")
            leave = box.addButton(f"Leave my changes on {current}", QMessageBox.AcceptRole)
            bring = box.addButton(f"Bring my changes to {target}", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is leave:
                ok, msg = self.git.stash_all()
                if not ok:
                    self._error("Could not stash changes", msg)
                    return
            elif box.clickedButton() is not bring:
                return
        ok, msg = (self.git.checkout_remote_branch(name) if kind == "remote" else self.git.checkout_branch(name))
        if not ok:
            self._error(f"Could not switch to {target}", msg)
        self._undo_hash = ""
        self.refresh(force=True)

    def new_branch(self):
        current = self.git.get_current_branch()
        dlg = BranchNameDialog(self.git, "Create a branch", "Create branch",
                               note=f"Your new branch will be based on <b>{_esc(current)}</b>.", parent=self)
        if dlg.exec():
            ok, msg = self.git.create_and_checkout_branch(dlg.name())
            if not ok:
                self._error("Could not create branch", msg)
            self.refresh(force=True)

    def rename_branch(self, name: str):
        dlg = BranchNameDialog(self.git, "Rename branch", "Rename", initial=name, parent=self)
        if dlg.exec():
            ok, msg = self.git.git_branch_rename(name, dlg.name())
            if not ok:
                self._error("Could not rename branch", msg)
            self.refresh(force=True)

    def delete_branch(self, name: str):
        if name == self.git.get_current_branch():
            self._error("Delete branch", f"'{name}' is the current branch. Switch to another branch first.")
            return
        answer = QMessageBox.question(self, "Delete branch", f"Delete the branch '{name}'?\n\nThis cannot be undone.")
        if answer != QMessageBox.Yes:
            return
        ok, msg = self.git.git_branch_delete(name)
        if not ok and "not fully merged" in msg:
            again = QMessageBox.question(self, "Delete branch",
                                         f"'{name}' has commits that are not merged anywhere.\nDelete it anyway?")
            if again == QMessageBox.Yes:
                ok, msg = self.git.git_branch_delete(name, force=True)
            else:
                return
        if not ok:
            self._error("Could not delete branch", msg)
        self.refresh(force=True)

    def merge_into_current(self):
        branches = self.git.get_branches()
        current = self.git.get_current_branch()
        dlg = MergeDialog(branches["local"] + branches["remote"], current, self)
        if dlg.exec() and dlg.branch():
            ok, msg = self.git.git_branch_merge(dlg.branch())
            if not ok:
                if self.git.is_merging():
                    QMessageBox.information(self, "Merge conflicts",
                                            "There are conflicts. Resolve them in your editor, then commit the merge.")
                else:
                    self._error("Merge failed", msg)
            self.refresh(force=True)

    def abort_merge(self):
        if not self.git.is_merging():
            return
        if QMessageBox.question(self, "Abort merge", "Abort the merge and return to the state before it?") == QMessageBox.Yes:
            ok, msg = self.git.merge_abort()
            if not ok:
                self._error("Could not abort merge", msg)
            self.refresh(force=True)

    # ======================================================================
    # Commit, undo, discard, stash
    # ======================================================================
    def commit(self, summary: str, description: str):
        checked = self.changes.checked_files()
        checked_paths = {f["path"] for f in checked}
        # Stage exactly what is checked; renames need the old path too
        stage = [p for f in checked for p in (f["path"], f.get("orig_path")) if p]
        if stage and not self.git.stage_paths(stage):
            self._error("Commit failed", "Could not stage the selected files.")
            return
        for f in self.changes.all_files():
            if f["path"] not in checked_paths and f["staged"]:
                self.git.unstage_file(f["path"])

        ok, msg = self.git.git_commit(summary, description)
        if not ok:
            self._error("Commit failed", msg)
            self.refresh(force=True)
            return
        self._undo_hash = self.git.run_git("rev-parse", "HEAD").stdout.strip()
        self._undo_message = (summary, description)
        self.changes.clear_message()
        self.refresh(force=True)

    def undo_commit(self):
        ok, msg = self.git.undo_last_commit()
        if not ok:
            self._error("Could not undo commit", msg)
            return
        self.changes.set_message(*self._undo_message)
        self._undo_hash = ""
        self.refresh(force=True)

    def _confirm_discard(self, what: str) -> bool:
        return QMessageBox.question(
            self, "Discard changes",
            f"Are you sure you want to discard {what}?\n\nNew files are moved to the trash; "
            f"changes to tracked files cannot be recovered."
        ) == QMessageBox.Yes

    def _discard(self, f: dict) -> bool:
        if f["status"] == "?":
            # like GitHub Desktop: untracked files go to the trash, not oblivion
            res = QFile.moveToTrash(os.path.join(self.git.repo_path, f["path"]))
            if (res[0] if isinstance(res, tuple) else res):
                return True
        return self.git.discard_file(f["path"], is_untracked=f["status"] == "?")

    def discard_file(self, f: dict):
        if self._confirm_discard(f"all changes to '{f['path']}'"):
            if not self._discard(f):
                self._error("Discard failed", f"Could not discard changes to '{f['path']}'.")
            self.refresh(force=True)

    def discard_all_changes(self):
        files = self.changes.all_files()
        if files and self._confirm_discard(f"all {len(files)} changed files"):
            failed = [f["path"] for f in files if not self._discard(f)]
            if failed:
                self._error("Discard failed", "Could not discard:\n" + "\n".join(failed))
            self.refresh(force=True)

    def stash_changes(self):
        if not self.changes.all_files():
            return
        ok, msg = self.git.stash_all()
        if not ok:
            self._error("Could not stash changes", msg)
        self.refresh(force=True)

    def restore_stash(self):
        ref = self.git.get_desktop_stash(self.git.get_current_branch())
        if not ref:
            return
        res = self.git.run_git("stash", "pop", ref)
        if res.returncode != 0:
            self._error("Could not restore stash", res.stderr.strip() or res.stdout.strip())
        self.refresh(force=True)

    def discard_stash(self):
        ref = self.git.get_desktop_stash(self.git.get_current_branch())
        if ref and QMessageBox.question(self, "Discard stash", "Discard the stashed changes? This cannot be undone.") == QMessageBox.Yes:
            self.git.git_stash_drop(ref)
            self.refresh(force=True)

    def _fill_file_menu(self, f: dict, menu):
        abs_path = os.path.join(self.git.repo_path, f["path"])
        exists = os.path.exists(abs_path)
        menu.addAction("Discard changes…", lambda: self.discard_file(f))
        menu.addSeparator()
        if f["status"] == "?":
            menu.addAction("Ignore file (add to .gitignore)", lambda: self._ignore(f["path"]))
            ext = os.path.splitext(f["path"])[1]
            if ext:
                menu.addAction(f"Ignore all {ext} files", lambda: self._ignore(f"*{ext}"))
            menu.addSeparator()
        menu.addAction("Copy file path", lambda: QGuiApplication.clipboard().setText(abs_path))
        menu.addAction("Copy relative file path", lambda: QGuiApplication.clipboard().setText(f["path"]))
        menu.addSeparator()
        a = menu.addAction("Show in file manager", lambda: self.show_in_file_manager(os.path.dirname(abs_path)))
        a.setEnabled(os.path.isdir(os.path.dirname(abs_path)))
        a = menu.addAction("Open in external editor", lambda: self.open_in_editor(f["path"]))
        a.setEnabled(exists)
        a = menu.addAction("Open with default program", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(abs_path)))
        a.setEnabled(exists)

    def _ignore(self, pattern: str):
        if not self.git.add_to_gitignore(pattern):
            self._error("Could not update .gitignore", f"Could not add '{pattern}' to .gitignore.")
        self.refresh(force=True)

    # ======================================================================
    # Network: fetch / pull / push / publish (background)
    # ======================================================================
    def sync(self, mode: Optional[str] = None, quiet: bool = False):
        if self._busy or not self.git.is_git_repo() or not self.git.git_remote_list():
            return
        mode = mode or getattr(self, "_sync_mode", "fetch")
        if mode == "none":
            return
        if mode == "push" and not self.git.get_sync_status()["has_upstream"]:
            mode = "publish"
        jobs = {
            "fetch": ("Fetching origin…", lambda: self.git.git_fetch("origin")),
            "pull": ("Pulling origin…", self.git.git_pull),
            "push": ("Pushing to origin…", self.git.git_push),
            "publish": ("Publishing branch…", self.git.git_publish_branch),
        }
        label, job = jobs[mode]
        self._busy = True
        self.sync_btn.setEnabled(False)
        self.sync_btn.set_texts(label, "", "⟳")

        def finished(result):
            self._busy = False
            ok, msg = result if isinstance(result, tuple) else (False, str(result))
            if not ok and not quiet:
                self._error(f"{mode.capitalize()} failed", self._explain_network_error(msg))
            self.refresh(force=True)

        def failed(err):
            finished((False, err))

        run_async(job, on_done=finished, on_error=failed)

    def _explain_network_error(self, msg: str) -> str:
        if "could not read Username" in msg or "Authentication failed" in msg or "terminal prompts disabled" in msg:
            return (msg + "\n\nGitHub asked for credentials. Sign in under File → Options → Accounts, "
                    "or run `gh auth login` in a terminal.")
        return msg

    def _load_token(self):
        def done(token):
            self.git.github_token = token
        run_async(self.gh.get_token, on_done=done)

    # ======================================================================
    # Integrations
    # ======================================================================
    def open_in_editor(self, rel_path: Optional[str] = None):
        if not self.gh.open_in_editor(self.git.repo_path, rel_path):
            target = os.path.join(self.git.repo_path, rel_path) if rel_path else self.git.repo_path
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(target)):
                self._error("No editor found", "Install an editor such as VS Code or Kate, then pick it in Options → Integrations.")

    def show_in_file_manager(self, path: Optional[str] = None):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path or self.git.repo_path))

    def open_in_terminal(self):
        preferred = self.gh.get_setting("terminal", "")
        candidates = ([preferred] if preferred else []) + [os.environ.get("TERMINAL", "")] + TERMINALS
        for cmd in candidates:
            if cmd and shutil.which(cmd):
                subprocess.Popen([cmd], cwd=self.git.repo_path, stdin=subprocess.DEVNULL, start_new_session=True)
                return
        self._error("No terminal found", "Set your terminal in Options → Integrations.")

    def show_options(self):
        dlg = OptionsDialog(self.git, self.gh, self)
        accepted = dlg.exec()
        if accepted:
            from ui.theme import apply_theme
            apply_theme(QApplication.instance(), self.gh.get_setting("theme", "system"))
            self.refresh(force=True)
        if dlg.account_changed:
            self._load_token()

    def show_about(self):
        QMessageBox.about(
            self, "About Git Desktop For Linux",
            "<b>Git Desktop For Linux</b> (Qt)<br><br>"
            "A simple Git client for Linux, modeled on "
            "<a href='https://github.com/desktop/desktop'>GitHub Desktop</a>.<br><br>"
            "Developer: Kağan Efe TOPÇU (<a href='https://github.com/kefy266'>@kefy266</a>)")

    def _error(self, title: str, msg: str):
        QMessageBox.warning(self, title, msg or "An unknown error occurred.")


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
