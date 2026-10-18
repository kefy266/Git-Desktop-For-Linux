"""'History' tab: commit list in the sidebar and the commit details pane."""

from typing import Callable, List, Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)

from ui import icons, theme
from ui.delegates import COMMIT_ROLE, FILE_ROLE, CommitDelegate, FileDelegate
from ui.diff_view import DiffView

PAGE_SIZE = 100


class HistoryList(QListWidget):
    commit_selected = Signal(dict)

    def __init__(self, load_page: Callable[[int, int], List[dict]], parent=None):
        super().__init__(parent)
        self._load_page = load_page
        self._exhausted = False
        self.setItemDelegate(CommitDelegate(self))
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)
        self.currentItemChanged.connect(lambda item, _p: self.commit_selected.emit(item.data(COMMIT_ROLE) if item else {}))
        self.verticalScrollBar().valueChanged.connect(self._maybe_load_more)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_menu)

    def reload(self):
        selected = self.current_hash()
        self.blockSignals(True)
        self.clear()
        self.blockSignals(False)
        self._exhausted = False
        self._append(self._load_page(PAGE_SIZE, 0))
        # keep the selection if that commit still exists
        for i in range(self.count()):
            if self.item(i).data(COMMIT_ROLE)["hash"] == selected:
                self.setCurrentRow(i)
                return
        if self.count() and not selected:
            self.setCurrentRow(0)
        elif not self.count():
            self.commit_selected.emit({})

    def current_hash(self) -> str:
        item = self.currentItem()
        return item.data(COMMIT_ROLE)["hash"] if item else ""

    def head_hash(self) -> str:
        return self.item(0).data(COMMIT_ROLE)["hash"] if self.count() else ""

    def _append(self, commits: List[dict]):
        if len(commits) < PAGE_SIZE:
            self._exhausted = True
        for commit in commits:
            item = QListWidgetItem()
            item.setData(COMMIT_ROLE, commit)
            item.setToolTip(commit["summary"])
            self.addItem(item)

    def _maybe_load_more(self, value):
        bar = self.verticalScrollBar()
        if not self._exhausted and value >= bar.maximum() - 5:
            self._append(self._load_page(PAGE_SIZE, self.count()))

    def _on_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        commit = item.data(COMMIT_ROLE)
        menu = QMenu(self)
        menu.addAction(icons.icon("copy", theme.colors()["text_dim"]), "Copy SHA",
                       lambda: QGuiApplication.clipboard().setText(commit["hash"]))
        menu.addAction("Copy summary", lambda: QGuiApplication.clipboard().setText(commit["summary"]))
        menu.exec(self.viewport().mapToGlobal(pos))


class _AuthorAvatar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.name = self.email = ""

    def paintEvent(self, _e):
        theme.paint_avatar(QPainter(self), QRectF(self.rect()), self.name, self.email)


class CommitView(QWidget):
    """Right pane in History: commit header, changed files, and the selected file's diff."""

    open_in_editor = Signal(str)

    def __init__(self, git, parent=None):
        super().__init__(parent)
        self.git = git
        self.commit: Optional[dict] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = QWidget(objectName="DiffHeader")
        self.header.setAttribute(Qt.WA_StyledBackground, True)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(18, 14, 14, 14)
        hl.setSpacing(12)
        self.avatar = _AuthorAvatar()
        hl.addWidget(self.avatar, 0, Qt.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        self.summary_label = QLabel(wordWrap=True, objectName="Title")
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary_label.setTextFormat(Qt.PlainText)  # commit text is not markup
        texts.addWidget(self.summary_label)
        self.body_label = QLabel(wordWrap=True)
        self.body_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body_label.setTextFormat(Qt.PlainText)
        texts.addWidget(self.body_label)
        self.meta_label = QLabel(objectName="Dim")
        self.meta_label.setTextFormat(Qt.PlainText)
        self.meta_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        texts.addWidget(self.meta_label)
        hl.addLayout(texts, 1)
        self.copy_btn = QPushButton(" Copy SHA")
        self.copy_btn.setIcon(icons.icon("copy", theme.colors()["text_dim"]))
        self.copy_btn.clicked.connect(lambda: self.commit and QGuiApplication.clipboard().setText(self.commit["hash"]))
        hl.addWidget(self.copy_btn, 0, Qt.AlignTop)
        lay.addWidget(self.header)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        files_box = QWidget(objectName="Sidebar")
        files_box.setAttribute(Qt.WA_StyledBackground, True)
        fl = QVBoxLayout(files_box)
        fl.setContentsMargins(0, 10, 0, 0)
        fl.setSpacing(4)
        self.files_count = QLabel(objectName="Dim")
        self.files_count.setContentsMargins(18, 0, 0, 0)
        fl.addWidget(self.files_count)
        self.files = QListWidget()
        self.files.setItemDelegate(FileDelegate(self.files, checkable=False))
        self.files.setMouseTracking(True)
        self.files.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.files.currentItemChanged.connect(self._on_file_changed)
        fl.addWidget(self.files, 1)
        self.diff = DiffView(show_header=False)
        self.splitter.addWidget(files_box)
        self.splitter.addWidget(self.diff)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([280, 700])
        lay.addWidget(self.splitter, 1)

    def show_commit(self, commit: dict):
        self.commit = commit or None
        self.files.blockSignals(True)
        self.files.clear()
        self.files.blockSignals(False)
        if not commit:
            self.summary_label.setText("No commits yet")
            self.body_label.clear()
            self.body_label.setVisible(False)
            self.meta_label.clear()
            self.files_count.clear()
            self.diff.show_message("Your first commit will show up here.", icon="history")
            return
        details = self.git.get_commit_details(commit["hash"]) or commit
        self.avatar.name, self.avatar.email = details.get("author", ""), details.get("email", "")
        self.avatar.update()
        self.summary_label.setText(details.get("summary", ""))
        self.body_label.setText(details.get("body", ""))
        self.body_label.setVisible(bool(details.get("body")))
        self.meta_label.setText(
            f"{details.get('author', '')}  ·  {details.get('full_date', details.get('date', ''))}"
            f"  ·  {details.get('short_hash', '')}"
        )
        files = self.git.get_commit_files(commit["hash"])
        self.files_count.setText(f"{len(files)} changed file{'s' if len(files) != 1 else ''}")
        for f in files:
            item = QListWidgetItem(f["path"])
            item.setData(FILE_ROLE, f)
            item.setToolTip(f["path"])
            self.files.addItem(item)
        if files:
            self.files.setCurrentRow(0)
        else:
            self.diff.show_message("This commit has no file changes.", icon="commit")

    def _on_file_changed(self, item, _prev):
        if not item or not self.commit:
            return
        f = item.data(FILE_ROLE)
        diff = self.git.get_commit_file_diff(self.commit["hash"], f["path"], f.get("orig_path", ""))
        self.diff.set_diff(f["path"], diff, f["status"], can_open=False)
