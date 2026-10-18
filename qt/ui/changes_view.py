"""Sidebar 'Changes' tab: checkable file list, banners and the commit box."""

from typing import Dict, List

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ui import icons, theme
from ui.delegates import FILE_ROLE, FileDelegate

PATH_ROLE = Qt.UserRole
DATA_ROLE = FILE_ROLE


class Avatar(QWidget):
    """Round initials avatar of the committer, as in GitHub Desktop's commit box."""

    def __init__(self, size=28, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.name, self.email = "", ""

    def set_identity(self, name: str, email: str):
        self.name, self.email = name, email
        self.setToolTip(f"Committing as {name} <{email}>" if name else "Set your name in Options → Git")
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        theme.paint_avatar(p, QRectF(self.rect()), self.name, self.email)


class Banner(QWidget):
    """Rounded card with an icon, a message and up to two buttons (Undo, Restore…)."""

    def __init__(self, icon_name: str, warn: bool = False, parent=None):
        super().__init__(parent, objectName="Banner")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("warn", warn)
        self.icon_name = icon_name
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 8, 8, 8)
        outer.setSpacing(8)
        self.icon = QLabel()
        outer.addWidget(self.icon, 0, Qt.AlignTop)
        self.label = QLabel(wordWrap=True)
        self.label.setTextFormat(Qt.RichText)
        outer.addWidget(self.label, 1)
        self.btn1 = QPushButton(objectName="LinkButton")
        self.btn2 = QPushButton(objectName="LinkButton")
        outer.addWidget(self.btn1)
        outer.addWidget(self.btn2)
        self.refresh_icon()
        self.setVisible(False)

    def refresh_icon(self):
        c = theme.colors()
        color = c["modified"] if self.property("warn") else c["accent"]
        self.icon.setPixmap(icons.pixmap(self.icon_name, color, 16))


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
        hl = QHBoxLayout(header)
        hl.setContentsMargins(22, 8, 12, 6)
        self.all_check = QCheckBox()
        self.all_check.setTristate(True)
        self.all_check.clicked.connect(self._on_all_clicked)
        hl.addWidget(self.all_check)
        self.count_label = QLabel("0 changed files", objectName="Dim")
        hl.addWidget(self.count_label, 1)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_menu)
        lay.addWidget(header)

        # ---- files ----
        self.list = QListWidget()
        self.list.setItemDelegate(FileDelegate(self.list, checkable=True))
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setUniformItemSizes(True)
        self.list.currentItemChanged.connect(self._on_current_changed)
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_file_menu)
        self.list.installEventFilter(self)
        lay.addWidget(self.list, 1)

        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.setAlignment(Qt.AlignCenter)
        empty_icon = QLabel(alignment=Qt.AlignCenter)
        empty_icon.setPixmap(icons.pixmap("check", theme.colors()["text_dim"], 28))
        el.addWidget(empty_icon)
        el.addWidget(QLabel("No local changes", objectName="Dim", alignment=Qt.AlignCenter))
        self.empty_label = self.empty
        self.empty.setVisible(False)
        lay.addWidget(self.empty, 1)

        # ---- banners (rounded cards above the commit box) ----
        banners = QVBoxLayout()
        banners.setContentsMargins(10, 0, 10, 8)
        banners.setSpacing(6)
        self.merge_banner = Banner("alert", warn=True)
        self.merge_banner.btn1.setText("Abort merge")
        self.merge_banner.btn1.clicked.connect(self.abort_merge_requested)
        self.merge_banner.btn2.setVisible(False)
        banners.addWidget(self.merge_banner)

        self.stash_banner = Banner("box")
        self.stash_banner.label.setText("<b>Stashed changes</b><br>saved on this branch")
        self.stash_banner.btn1.setText("Restore")
        self.stash_banner.btn1.clicked.connect(self.restore_stash_requested)
        self.stash_banner.btn2.setText("Discard")
        self.stash_banner.btn2.clicked.connect(self.discard_stash_requested)
        banners.addWidget(self.stash_banner)

        self.undo_banner = Banner("commit")
        self.undo_banner.btn1.setText("Undo")
        self.undo_banner.btn1.clicked.connect(self.undo_requested)
        self.undo_banner.btn2.setVisible(False)
        banners.addWidget(self.undo_banner)
        lay.addLayout(banners)

        # ---- commit box ----
        box = QWidget(objectName="CommitBox")
        box.setAttribute(Qt.WA_StyledBackground, True)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(12, 12, 12, 12)
        bl.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.avatar = Avatar(32)
        row.addWidget(self.avatar)
        self.summary = QLineEdit(placeholderText="Summary (required)")
        self.summary.setMinimumHeight(34)
        self.summary.textChanged.connect(self._update_commit_button)
        self.summary.returnPressed.connect(self._commit)
        row.addWidget(self.summary, 1)
        bl.addLayout(row)
        self.description = QPlainTextEdit(placeholderText="Description")
        self.description.setFixedHeight(84)
        bl.addWidget(self.description)
        self.commit_btn = QPushButton("Commit to main", objectName="PrimaryButton")
        self.commit_btn.setToolTip("Ctrl+Enter")
        self.commit_btn.setCursor(Qt.PointingHandCursor)
        self.commit_btn.clicked.connect(self._commit)
        bl.addWidget(self.commit_btn)
        lay.addWidget(box)

        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            sc = QShortcut(QKeySequence(seq), box)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(self._commit)

        self._update_commit_button()

    # ---------------- data ----------------
    def set_identity(self, name: str, email: str):
        self.avatar.set_identity(name, email)

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
            item = QListWidgetItem(f["path"])
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
        self.empty.setVisible(n == 0)
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
        self.merge_banner.label.setText("<b>Merge in progress</b><br>Resolve the conflicts, then commit." if merging else "")
        self.merge_banner.setVisible(merging)
        self._update_commit_button()

    def show_undo(self, summary: str):
        self.undo_banner.label.setText(f"<b>Committed just now</b><br>{_escape(summary)}")
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
    def eventFilter(self, obj, event):
        # Space toggles the checkbox of the current file, like GitHub Desktop
        if obj is self.list and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            item = self.list.currentItem()
            if item:
                item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
                return True
        return super().eventFilter(obj, event)

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
        self.list.viewport().update()
        self._sync_all_check()
        self._update_commit_button()

    def _update_commit_button(self, *_):
        branch = self._branch or "branch"
        self.commit_btn.setText("Commit merge" if self._merging else f"Commit to {branch}")
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
