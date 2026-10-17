"""Sidebar 'Changes' tab: checkable file list, banners and the commit box."""

from typing import Dict, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ui import theme

PATH_ROLE = Qt.UserRole
DATA_ROLE = Qt.UserRole + 1


class Banner(QWidget):
    """Thin strip with a message and up to two buttons (Undo, Restore, Abort...)."""

    def __init__(self, parent=None):
        super().__init__(parent, objectName="Banner")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        self.label = QLabel(wordWrap=True)
        lay.addWidget(self.label, 1)
        self.btn1 = QPushButton()
        self.btn2 = QPushButton()
        lay.addWidget(self.btn1)
        lay.addWidget(self.btn2)
        self.setVisible(False)


class ChangesView(QWidget):
    file_selected = Signal(dict)
    commit_requested = Signal(str, str)
    file_context_menu = Signal(dict, QMenu)   # main window fills the menu
    discard_all_requested = Signal()
    undo_requested = Signal()
    restore_stash_requested = Signal()
    discard_stash_requested = Signal()
    abort_merge_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked: Dict[str, bool] = {}
        self._files: List[dict] = []
        self._branch = ""
        self._merging = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- header: tri-state "select all" + count ----
        header = QWidget(objectName="SectionHeader")
        header.setAttribute(Qt.WA_StyledBackground, True)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 6, 10, 6)
        self.all_check = QCheckBox()
        self.all_check.setTristate(True)
        self.all_check.clicked.connect(self._on_all_clicked)
        hl.addWidget(self.all_check)
        self.count_label = QLabel("0 changed files")
        hl.addWidget(self.count_label, 1)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_menu)
        lay.addWidget(header)

        # ---- files ----
        self.list = QListWidget()
        self.list.setUniformItemSizes(True)
        self.list.setTextElideMode(Qt.ElideLeft)  # keep the file name visible
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentItemChanged.connect(self._on_current_changed)
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_file_menu)
        lay.addWidget(self.list, 1)

        self.empty_label = QLabel("No local changes", alignment=Qt.AlignCenter, objectName="Dim")
        self.empty_label.setVisible(False)
        lay.addWidget(self.empty_label, 1)

        # ---- banners ----
        self.merge_banner = Banner()
        self.merge_banner.btn1.setText("Abort merge")
        self.merge_banner.btn1.clicked.connect(self.abort_merge_requested)
        self.merge_banner.btn2.setVisible(False)
        lay.addWidget(self.merge_banner)

        self.stash_banner = Banner()
        self.stash_banner.label.setText("Stashed changes on this branch")
        self.stash_banner.btn1.setText("Restore")
        self.stash_banner.btn1.clicked.connect(self.restore_stash_requested)
        self.stash_banner.btn2.setText("Discard")
        self.stash_banner.btn2.clicked.connect(self.discard_stash_requested)
        lay.addWidget(self.stash_banner)

        self.undo_banner = Banner()
        self.undo_banner.btn1.setText("Undo")
        self.undo_banner.btn1.clicked.connect(self.undo_requested)
        self.undo_banner.btn2.setVisible(False)
        lay.addWidget(self.undo_banner)

        # ---- commit box ----
        box = QWidget(objectName="CommitBox")
        box.setAttribute(Qt.WA_StyledBackground, True)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(10, 10, 10, 10)
        bl.setSpacing(6)
        self.summary = QLineEdit(placeholderText="Summary (required)")
        self.summary.textChanged.connect(self._update_commit_button)
        self.summary.returnPressed.connect(self._commit)
        bl.addWidget(self.summary)
        self.description = QPlainTextEdit(placeholderText="Description")
        self.description.setFixedHeight(80)
        bl.addWidget(self.description)
        self.commit_btn = QPushButton("Commit to main", objectName="PrimaryButton")
        self.commit_btn.setToolTip("Ctrl+Enter")
        self.commit_btn.clicked.connect(self._commit)
        bl.addWidget(self.commit_btn)
        lay.addWidget(box)

        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            sc = QShortcut(QKeySequence(seq), box)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(self._commit)

        self._update_commit_button()

    # ---------------- data ----------------
    def set_files(self, files: List[dict]):
        current = self.current_path()
        paths = {f["path"] for f in files}
        # forget check state of files that are no longer changed
        self._checked = {p: v for p, v in self._checked.items() if p in paths}
        self._files = files

        self.list.blockSignals(True)
        self.list.clear()
        restore_row = 0
        for i, f in enumerate(files):
            text = f["path"] if not f.get("orig_path") else f"{f['orig_path']} → {f['path']}"
            item = QListWidgetItem(theme.status_icon(f["status"]), text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if self._checked.get(f["path"], True) else Qt.Unchecked)
            item.setData(PATH_ROLE, f["path"])
            item.setData(DATA_ROLE, f)
            item.setToolTip(f"{f['path']}\n{theme.STATUS_LABELS.get(f['status'], '')}")
            self.list.addItem(item)
            if f["path"] == current:
                restore_row = i
        self.list.blockSignals(False)

        n = len(files)
        self.count_label.setText(f"{n} changed file{'s' if n != 1 else ''}")
        self.list.setVisible(n > 0)
        self.empty_label.setVisible(n == 0)
        self.all_check.setEnabled(n > 0)
        self._sync_all_check()
        self._update_commit_button()
        if n:
            self.list.setCurrentRow(restore_row)
        else:
            self.file_selected.emit({})

    def set_branch(self, branch: str, merging: bool = False):
        self._branch = branch
        self._merging = merging
        self.merge_banner.label.setText("Merge in progress. Resolve conflicts, then commit." if merging else "")
        self.merge_banner.setVisible(merging)
        self._update_commit_button()

    def show_undo(self, summary: str):
        self.undo_banner.label.setText(f"Committed just now: <b>{_escape(summary)}</b>")
        self.undo_banner.setVisible(bool(summary))

    def checked_files(self) -> List[dict]:
        return [f for f in self._files if self._checked.get(f["path"], True)]

    def all_files(self) -> List[dict]:
        return list(self._files)

    def current_path(self) -> str:
        item = self.list.currentItem()
        return item.data(PATH_ROLE) if item else ""

    def set_message(self, summary: str, description: str):
        self.summary.setText(summary)
        self.description.setPlainText(description)

    def clear_message(self):
        self.set_message("", "")

    # ---------------- internals ----------------
    def _on_current_changed(self, item, _prev):
        self.file_selected.emit(item.data(DATA_ROLE) if item else {})

    def _on_item_changed(self, item):
        self._checked[item.data(PATH_ROLE)] = item.checkState() == Qt.Checked
        self._sync_all_check()
        self._update_commit_button()

    def _sync_all_check(self):
        states = [self._checked.get(f["path"], True) for f in self._files]
        if states and all(states):
            state = Qt.Checked
        elif any(states):
            state = Qt.PartiallyChecked
        else:
            state = Qt.Unchecked
        self.all_check.blockSignals(True)
        self.all_check.setCheckState(state)
        self.all_check.blockSignals(False)

    def _on_all_clicked(self):
        # Partial or none -> check all; all -> uncheck all (GitHub Desktop behavior)
        target = not all(self._checked.get(f["path"], True) for f in self._files)
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setCheckState(Qt.Checked if target else Qt.Unchecked)
            self._checked[item.data(PATH_ROLE)] = target
        self.list.blockSignals(False)
        self._sync_all_check()
        self._update_commit_button()

    def _update_commit_button(self, *_):
        branch = self._branch or "branch"
        self.commit_btn.setText(f"Commit merge" if self._merging else f"Commit to {branch}")
        has_summary = bool(self.summary.text().strip())
        has_files = bool(self.checked_files())
        self.commit_btn.setEnabled(has_summary and (has_files or self._merging))

    def _commit(self):
        if self.commit_btn.isEnabled():
            self.commit_requested.emit(self.summary.text().strip(), self.description.toPlainText().strip())

    def _on_file_menu(self, pos):
        item = self.list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        self.file_context_menu.emit(item.data(DATA_ROLE), menu)
        if not menu.isEmpty():
            menu.exec(self.list.viewport().mapToGlobal(pos))

    def _on_header_menu(self, pos):
        if not self._files:
            return
        menu = QMenu(self)
        menu.addAction("Discard all changes…", self.discard_all_requested)
        menu.exec(self.sender().mapToGlobal(pos))


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
