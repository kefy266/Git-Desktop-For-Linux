"""Dialogs: clone, create, branch name, merge, options."""

import os
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
    QRadioButton, QTabWidget, QVBoxLayout, QWidget,
)

from ui import icons, theme
from ui.delegates import REPO_ROLE, SECTION_ROLE, RepoDelegate, group_repos
from ui.workers import run_async


def _path_row(line_edit: QLineEdit, parent) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addWidget(line_edit, 1)
    btn = QPushButton("Choose…")

    def choose():
        start = line_edit.text() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(parent, "Choose folder", start)
        if folder:
            line_edit.setText(folder)

    btn.clicked.connect(choose)
    row.addWidget(btn)
    return row


def _default_parent_dir() -> str:
    git_dir = os.path.expanduser("~/Git")
    return git_dir if os.path.isdir(git_dir) else os.path.expanduser("~")


def _error_label() -> QLabel:
    label = QLabel(wordWrap=True)
    label.setStyleSheet("color: #d73a49;")
    label.setVisible(False)
    return label


# ==================== CLONE ====================
class CloneDialog(QDialog):
    """GitHub.com tab (every repository of the account, grouped by owner) and URL tab."""

    def __init__(self, gh_service, parent=None, repos: Optional[List[dict]] = None,
                 preselect: str = "", me: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Clone a repository")
        self.resize(640, 600)
        self.gh = gh_service
        self.result_path = ""
        self._repos: List[dict] = []
        self._preselect = preselect
        self._me = me

        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        # --- GitHub.com tab ---
        gh_tab = QWidget()
        gl = QVBoxLayout(gh_tab)
        top = QHBoxLayout()
        self.gh_filter = QLineEdit(placeholderText="Filter your repositories")
        self.gh_filter.setClearButtonEnabled(True)
        self.gh_filter.addAction(icons.icon("search", theme.colors()["text_dim"]), QLineEdit.LeadingPosition)
        self.gh_filter.textChanged.connect(self._fill_repo_list)
        top.addWidget(self.gh_filter, 1)
        self.owner_combo = QComboBox()
        self.owner_combo.setMinimumWidth(150)
        self.owner_combo.currentIndexChanged.connect(self._fill_repo_list)
        top.addWidget(self.owner_combo)
        self.refresh_btn = QPushButton(objectName="FlatButton")
        self.refresh_btn.setIcon(icons.icon("sync", theme.colors()["text_dim"]))
        self.refresh_btn.setToolTip("Reload repositories from GitHub")
        self.refresh_btn.clicked.connect(self._load_repos)
        top.addWidget(self.refresh_btn)
        gl.addLayout(top)
        self.repo_list = QListWidget()
        self.repo_list.setItemDelegate(RepoDelegate(self.repo_list))
        self.repo_list.setMouseTracking(True)
        self.repo_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.repo_list.currentItemChanged.connect(self._on_repo_picked)
        self.repo_list.itemDoubleClicked.connect(lambda _i: self._clone())
        gl.addWidget(self.repo_list, 1)
        self.gh_status = QLabel("Loading your repositories…", objectName="Dim")
        gl.addWidget(self.gh_status)
        self.tabs.addTab(gh_tab, "GitHub.com")

        # --- URL tab ---
        url_tab = QWidget()
        ul = QVBoxLayout(url_tab)
        ul.addWidget(QLabel("Repository URL or GitHub username and repository\n(e.g. https://github.com/desktop/desktop or desktop/desktop)"))
        self.url_edit = QLineEdit(placeholderText="URL or username/repository")
        self.url_edit.textChanged.connect(self._suggest_path)
        ul.addWidget(self.url_edit)
        ul.addStretch(1)
        self.tabs.addTab(url_tab, "URL")
        self.tabs.currentChanged.connect(lambda _i: self._suggest_path())

        form = QFormLayout()
        self.path_edit = QLineEdit()
        form.addRow("Local path", _path_row(self.path_edit, self))
        lay.addLayout(form)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        lay.addWidget(self.progress)
        self.error = _error_label()
        lay.addWidget(self.error)

        self.buttons = QDialogButtonBox()
        self.clone_btn = self.buttons.addButton("Clone", QDialogButtonBox.AcceptRole)
        self.clone_btn.setObjectName("PrimaryButton")
        self.buttons.addButton(QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._clone)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

        self._parent_dir = _default_parent_dir()
        if repos:
            self._on_repos_loaded(repos)  # already fetched by the main window
        else:
            self._load_repos()

    def repositories(self) -> List[dict]:
        return list(self._repos)

    def _load_repos(self):
        self.gh_status.setText("Loading your repositories…")
        self.refresh_btn.setEnabled(False)

        def failed(err):
            self.refresh_btn.setEnabled(True)
            self.gh_status.setText(f"Could not load repositories: {err}")

        run_async(self.gh.get_user_repos, on_done=self._on_repos_loaded, on_error=failed)

    def _on_repos_loaded(self, repos):
        self.refresh_btn.setEnabled(True)
        self._repos = repos or []
        if not self._repos:
            self.gh_status.setText("Sign in under Options → Accounts to see your repositories, or use the URL tab.")
            self.tabs.setCurrentIndex(1)
        else:
            owners = len({r.get("owner") for r in self._repos})
            self.gh_status.setText(f"{len(self._repos)} repositories from {owners} account"
                                   f"{'s' if owners != 1 else ''}")
        # owner filter: "All accounts" + each owner (signed-in user first)
        current_owner = self.owner_combo.currentData()
        self.owner_combo.blockSignals(True)
        self.owner_combo.clear()
        self.owner_combo.addItem("All accounts", "")
        for owner, items in group_repos(self._repos, self._me):
            self.owner_combo.addItem(f"{owner} ({len(items)})", owner)
        if current_owner:
            self.owner_combo.setCurrentIndex(max(0, self.owner_combo.findData(current_owner)))
        self.owner_combo.blockSignals(False)
        self._fill_repo_list()

    def _fill_repo_list(self, *_):
        text = self.gh_filter.text().lower().strip()
        only_owner = self.owner_combo.currentData() or ""
        current = self.repo_list.currentItem()
        selected = self._preselect or ((current.data(REPO_ROLE) or {}).get("full_name", "") if current else "")
        self.repo_list.blockSignals(True)
        self.repo_list.clear()
        select_item = None
        for owner, items in group_repos(self._repos, self._me):
            if only_owner and owner != only_owner:
                continue
            matches = [r for r in items if not text or text in r["full_name"].lower()
                       or text in r["description"].lower()]
            if not matches:
                continue
            header = QListWidgetItem()
            header.setFlags(Qt.NoItemFlags)
            header.setData(SECTION_ROLE, f"{owner} · {len(matches)}")
            self.repo_list.addItem(header)
            for r in matches:
                item = QListWidgetItem(r["full_name"])
                item.setData(REPO_ROLE, r)
                item.setToolTip(r["description"] or r["full_name"])
                self.repo_list.addItem(item)
                if r["full_name"] == selected:
                    select_item = item
        self.repo_list.blockSignals(False)
        if select_item:
            self.repo_list.setCurrentItem(select_item)
            self.repo_list.scrollToItem(select_item)
        self._preselect = ""

    def _on_repo_picked(self, item, _prev):
        self._suggest_path()

    def _clone_url(self) -> str:
        if self.tabs.currentIndex() == 0:
            item = self.repo_list.currentItem()
            repo = item.data(REPO_ROLE) if item else None
            return repo["clone_url"] if repo else ""
        url = self.url_edit.text().strip()
        # "owner/repo" shorthand, as GitHub Desktop accepts
        if url and "://" not in url and "@" not in url and url.count("/") == 1:
            url = f"https://github.com/{url}.git"
        return url

    def _suggest_path(self, *_):
        item = self.repo_list.currentItem() if self.tabs.currentIndex() == 0 else None
        repo = item.data(REPO_ROLE) if item else None
        url = self._clone_url()
        name = repo["name"] if repo else url.rstrip("/").split("/")[-1].split(":")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        if name:
            self.path_edit.setText(os.path.join(self._parent_dir, name))

    def _clone(self):
        url, path = self._clone_url(), self.path_edit.text().strip()
        if not url or not path:
            self._show_error("Choose a repository and a local path.")
            return
        if os.path.exists(path) and os.listdir(path):
            self._show_error(f"'{path}' already exists and is not empty.")
            return
        self.error.setVisible(False)
        self.progress.setVisible(True)
        self.clone_btn.setEnabled(False)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        run_async(self.gh.clone_repo, url, path, on_done=lambda r: self._on_cloned(r, path),
                  on_error=self._on_clone_failed)

    def _on_cloned(self, result, path):
        ok, msg = result
        if ok:
            self.result_path = path
            self.accept()
        else:
            self._on_clone_failed(msg)

    def _on_clone_failed(self, msg):
        self.progress.setVisible(False)
        self.clone_btn.setEnabled(True)
        self._show_error(msg or "Clone failed.")

    def _show_error(self, msg):
        self.error.setText(msg)
        self.error.setVisible(True)


# ==================== CREATE ====================
class CreateRepoDialog(QDialog):
    def __init__(self, gh_service, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create a new repository")
        self.resize(480, 0)
        self.gh = gh_service
        self.result_path = ""

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(placeholderText="repository-name")
        form.addRow("Name", self.name_edit)
        self.path_edit = QLineEdit(_default_parent_dir())
        form.addRow("Local path", _path_row(self.path_edit, self))
        self.readme = QCheckBox("Initialize this repository with a README")
        self.readme.setChecked(True)
        form.addRow("", self.readme)
        lay.addLayout(form)
        self.error = _error_label()
        lay.addWidget(self.error)

        buttons = QDialogButtonBox()
        create = buttons.addButton("Create repository", QDialogButtonBox.AcceptRole)
        create.setObjectName("PrimaryButton")
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._create)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _create(self):
        ok, result = self.gh.init_new_repo(self.path_edit.text().strip(), self.name_edit.text().strip(),
                                           init_readme=self.readme.isChecked())
        if ok:
            self.result_path = result
            self.accept()
        else:
            self.error.setText(result)
            self.error.setVisible(True)


# ==================== BRANCH NAME ====================
class BranchNameDialog(QDialog):
    """New branch / rename branch, with live name validation."""

    def __init__(self, git, title: str, button: str, note: str = "", initial: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(420, 0)
        self.git = git
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Name"))
        self.name_edit = QLineEdit(initial)
        self.name_edit.selectAll()
        lay.addWidget(self.name_edit)
        if note:
            note_label = QLabel(note, wordWrap=True, objectName="Dim")
            note_label.setTextFormat(Qt.RichText)
            lay.addWidget(note_label)
        self.error = _error_label()
        lay.addWidget(self.error)
        buttons = QDialogButtonBox()
        self.ok_btn = buttons.addButton(button, QDialogButtonBox.AcceptRole)
        self.ok_btn.setObjectName("PrimaryButton")
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.name_edit.textChanged.connect(self._validate)
        self._initial = initial
        self._validate()

    def name(self) -> str:
        return self.name_edit.text().strip()

    def _validate(self, *_):
        name = self.name()
        ok, msg = self.git.validate_branch_name(name) if name else (False, "")
        if ok and name in self.git.get_branches()["local"] and name != self._initial:
            ok, msg = False, f"A branch named '{name}' already exists."
        self.error.setText(msg)
        self.error.setVisible(bool(name) and not ok)
        self.ok_btn.setEnabled(ok and name != self._initial)


# ==================== MERGE ====================
class MergeDialog(QDialog):
    """Pick a branch to merge into the current one."""

    def __init__(self, branches: List[str], current: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Merge into {current}")
        self.resize(420, 460)
        self.current = current
        lay = QVBoxLayout(self)
        self.filter = QLineEdit(placeholderText="Filter")
        lay.addWidget(self.filter)
        self.list = QListWidget()
        for b in branches:
            if b != current:
                self.list.addItem(b)
        lay.addWidget(self.list, 1)
        self.filter.textChanged.connect(self._filter)
        buttons = QDialogButtonBox()
        self.ok_btn = buttons.addButton("Merge", QDialogButtonBox.AcceptRole)
        self.ok_btn.setObjectName("PrimaryButton")
        self.ok_btn.setEnabled(False)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.list.currentItemChanged.connect(self._on_pick)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())

    def branch(self) -> str:
        item = self.list.currentItem()
        return item.text() if item else ""

    def _filter(self, text):
        for i in range(self.list.count()):
            self.list.item(i).setHidden(text.lower() not in self.list.item(i).text().lower())

    def _on_pick(self, item, _prev):
        self.ok_btn.setEnabled(item is not None)
        if item:
            self.ok_btn.setText(f"Merge {item.text()} into {self.current}")


# ==================== OPTIONS ====================
class OptionsDialog(QDialog):
    """Accounts, Git identity, Integrations and Appearance (GitHub Desktop's Options)."""

    def __init__(self, git, gh_service, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.resize(560, 400)
        self.git = git
        self.gh = gh_service
        self.account_changed = False

        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        # --- Accounts ---
        self.accounts = QWidget()
        self.acc_layout = QVBoxLayout(self.accounts)
        self.tabs.addTab(self.accounts, "Accounts")
        self._build_accounts()

        # --- Git ---
        git_tab = QWidget()
        gf = QFormLayout(git_tab)
        name, email = self.git.get_user_info()
        self.name_edit = QLineEdit(name)
        self.email_edit = QLineEdit(email)
        gf.addRow("Name", self.name_edit)
        gf.addRow("Email", self.email_edit)
        gf.addRow("", QLabel("Saved to your global git config and used for every commit.", objectName="Dim"))
        self.tabs.addTab(git_tab, "Git")

        # --- Integrations ---
        int_tab = QWidget()
        inf = QFormLayout(int_tab)
        self.editor_combo = QComboBox()
        self._editors = self.gh.detect_installed_editors()
        preferred = self.gh.get_preferred_editor()
        for ed in self._editors:
            self.editor_combo.addItem(ed["name"], ed["cmd"])
        if not self._editors:
            self.editor_combo.addItem("No supported editor found", "")
            self.editor_combo.setEnabled(False)
        elif preferred:
            self.editor_combo.setCurrentIndex(max(0, self.editor_combo.findData(preferred["cmd"])))
        inf.addRow("External editor", self.editor_combo)
        self.shell_edit = QLineEdit(self.gh.get_setting("terminal", ""))
        self.shell_edit.setPlaceholderText("auto-detect (konsole, gnome-terminal, kitty…)")
        inf.addRow("Terminal", self.shell_edit)
        self.tabs.addTab(int_tab, "Integrations")

        # --- Appearance ---
        app_tab = QWidget()
        al = QVBoxLayout(app_tab)
        self.theme_group = QButtonGroup(self)
        current_theme = self.gh.get_setting("theme", "system")
        for value, label in (("system", "Follow system"), ("light", "Light"), ("dark", "Dark")):
            rb = QRadioButton(label)
            rb.setProperty("value", value)
            rb.setChecked(value == current_theme)
            self.theme_group.addButton(rb)
            al.addWidget(rb)
        al.addStretch(1)
        self.tabs.addTab(app_tab, "Appearance")

        buttons = QDialogButtonBox()
        save = buttons.addButton("Save", QDialogButtonBox.AcceptRole)
        save.setObjectName("PrimaryButton")
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def selected_theme(self) -> str:
        btn = self.theme_group.checkedButton()
        return btn.property("value") if btn else "system"

    # ---- accounts ----
    def _clear_accounts(self):
        while self.acc_layout.count():
            item = self.acc_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # nested layouts hold widgets too
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

    def _build_accounts(self, error: str = ""):
        self._clear_accounts()
        self.acc_layout.addWidget(QLabel("Checking GitHub account…", objectName="Dim"))
        self.acc_layout.addStretch(1)
        run_async(self.gh.get_user_profile, on_done=lambda p: self._show_account(p, error),
                  on_error=lambda e: self._show_account(None, e))

    def _show_account(self, profile, error: str = ""):
        self._clear_accounts()
        if profile:
            title = QLabel(f"<b>{_esc(profile['name'])}</b><br>@{_esc(profile['login'])}")
            title.setTextFormat(Qt.RichText)
            self.acc_layout.addWidget(title)
            self.acc_layout.addWidget(QLabel("Signed in to GitHub.com. Pushes, pulls and clones over HTTPS use this account.",
                                             wordWrap=True, objectName="Dim"))
            out = QPushButton("Sign out")
            out.clicked.connect(self._sign_out)
            self.acc_layout.addWidget(out, alignment=Qt.AlignLeft)
        else:
            self.acc_layout.addWidget(QLabel("<b>GitHub.com</b>", textFormat=Qt.RichText))
            self.acc_layout.addWidget(QLabel(
                "Sign in with a personal access token (Settings → Developer settings → Tokens on github.com, "
                "with the <i>repo</i> scope). If you use the GitHub CLI (gh), you are signed in automatically.",
                wordWrap=True, objectName="Dim", textFormat=Qt.RichText))
            row = QHBoxLayout()
            self.token_edit = QLineEdit(placeholderText="ghp_…")
            self.token_edit.setEchoMode(QLineEdit.Password)
            row.addWidget(self.token_edit, 1)
            self.sign_in_btn = QPushButton("Sign in")
            self.sign_in_btn.clicked.connect(self._sign_in)
            self.token_edit.returnPressed.connect(self._sign_in)
            row.addWidget(self.sign_in_btn)
            self.acc_layout.addLayout(row)
            if error:
                err = _error_label()
                err.setText(error)
                err.setVisible(True)
                self.acc_layout.addWidget(err)
        self.acc_layout.addStretch(1)

    def _sign_in(self):
        token = self.token_edit.text().strip()
        if not token:
            return
        self.sign_in_btn.setEnabled(False)

        def done(profile):
            if profile:
                self.gh.set_token(token)
                self.account_changed = True
                self._show_account(profile)
            else:
                self._show_account(None, "Token is invalid or GitHub could not be reached.")

        run_async(self.gh.get_user_profile, token=token, on_done=done,
                  on_error=lambda e: self._show_account(None, e))

    def _sign_out(self):
        self.gh.logout()
        self.account_changed = True
        self._show_account(None)

    def _save(self):
        name, email = self.name_edit.text().strip(), self.email_edit.text().strip()
        if name and email:
            self.git.set_user_info(name, email, is_global=True)
        cmd = self.editor_combo.currentData()
        if cmd:
            self.gh.set_preferred_editor(cmd)
        self.gh.set_setting("terminal", self.shell_edit.text().strip())
        self.gh.set_setting("theme", self.selected_theme())
        self.accept()


def _esc(text) -> str:
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
