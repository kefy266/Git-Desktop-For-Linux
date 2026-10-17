"""'History' tab: commit list in the sidebar and the commit details pane."""

from typing import Callable, List, Optional

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton,
    QSplitter, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ui import theme
from ui.diff_view import DiffView

COMMIT_ROLE = Qt.UserRole
PAGE_SIZE = 100


class _CommitDelegate(QStyledItemDelegate):
    """Two lines per commit: bold summary, then 'author • time ago'."""

    def sizeHint(self, option, index):
        fm = option.fontMetrics
        return QSize(option.rect.width(), fm.height() * 2 + 14)

    def paint(self, painter, option, index):
        commit = index.data(COMMIT_ROLE) or {}
        painter.save()
        selected = option.state & QStyle.State_Selected
        c = theme.colors()
        if selected:
            painter.fillRect(option.rect, QColor(c["selection"]))
        r = option.rect.adjusted(10, 6, -10, -6)
        bold = QFont(option.font)
        bold.setWeight(QFont.DemiBold)
        main_color = QColor(c["selection_text"] if selected else c["text"])
        dim_color = QColor(c["selection_text"] if selected else c["text_dim"])

        painter.setFont(bold)
        painter.setPen(main_color)
        line_h = option.fontMetrics.height()
        summary = painter.fontMetrics().elidedText(commit.get("summary", ""), Qt.ElideRight, r.width())
        painter.drawText(QRect(r.left(), r.top(), r.width(), line_h), Qt.AlignLeft | Qt.AlignVCenter, summary)

        painter.setFont(option.font)
        painter.setPen(dim_color)
        sub = f"{commit.get('author', '')} • {commit.get('date', '')}"
        sub = painter.fontMetrics().elidedText(sub, Qt.ElideRight, r.width())
        painter.drawText(QRect(r.left(), r.top() + line_h + 2, r.width(), line_h), Qt.AlignLeft | Qt.AlignVCenter, sub)

        painter.setPen(QColor(c["border"]))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()


class HistoryList(QListWidget):
    commit_selected = Signal(dict)

    def __init__(self, load_page: Callable[[int, int], List[dict]], parent=None):
        super().__init__(parent)
        self._load_page = load_page
        self._exhausted = False
        self.setItemDelegate(_CommitDelegate(self))
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
        menu.addAction("Copy SHA", lambda: QGuiApplication.clipboard().setText(commit["hash"]))
        menu.addAction("Copy summary", lambda: QGuiApplication.clipboard().setText(commit["summary"]))
        menu.exec(self.viewport().mapToGlobal(pos))


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
        hl = QVBoxLayout(self.header)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(4)
        self.summary_label = QLabel(wordWrap=True)
        f = self.summary_label.font()
        f.setPointSizeF(f.pointSizeF() * 1.25)
        f.setWeight(QFont.DemiBold)
        self.summary_label.setFont(f)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary_label.setTextFormat(Qt.PlainText)  # commit text is not markup
        hl.addWidget(self.summary_label)
        self.body_label = QLabel(wordWrap=True)
        self.body_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body_label.setTextFormat(Qt.PlainText)
        hl.addWidget(self.body_label)
        meta_row = QHBoxLayout()
        self.meta_label = QLabel(objectName="Dim")
        self.meta_label.setTextFormat(Qt.PlainText)
        self.meta_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        meta_row.addWidget(self.meta_label, 1)
        self.copy_btn = QPushButton("Copy SHA")
        self.copy_btn.clicked.connect(lambda: self.commit and QGuiApplication.clipboard().setText(self.commit["hash"]))
        meta_row.addWidget(self.copy_btn)
        hl.addLayout(meta_row)
        lay.addWidget(self.header)

        self.splitter = QSplitter(Qt.Horizontal)
        self.files = QListWidget()
        self.files.setTextElideMode(Qt.ElideLeft)
        self.files.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.files.currentItemChanged.connect(self._on_file_changed)
        self.diff = DiffView(show_header=False)
        self.splitter.addWidget(self.files)
        self.splitter.addWidget(self.diff)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([260, 700])
        lay.addWidget(self.splitter, 1)

    def show_commit(self, commit: dict):
        self.commit = commit or None
        self.files.blockSignals(True)
        self.files.clear()
        self.files.blockSignals(False)
        if not commit:
            self.summary_label.setText("No commits yet")
            self.body_label.clear()
            self.meta_label.clear()
            self.diff.show_message("")
            return
        details = self.git.get_commit_details(commit["hash"]) or commit
        self.summary_label.setText(details.get("summary", ""))
        self.body_label.setText(details.get("body", ""))
        self.body_label.setVisible(bool(details.get("body")))
        self.meta_label.setText(
            f"{details.get('author', '')} <{details.get('email', '')}> · "
            f"{details.get('full_date', details.get('date', ''))} · {details.get('short_hash', '')}"
        )
        files = self.git.get_commit_files(commit["hash"])
        for f in files:
            item = QListWidgetItem(theme.status_icon(f["status"]), f["path"])
            item.setData(Qt.UserRole, f)
            item.setToolTip(f["path"])
            self.files.addItem(item)
        if files:
            self.files.setCurrentRow(0)
        else:
            self.diff.show_message("This commit has no file changes.")

    def _on_file_changed(self, item, _prev):
        if not item or not self.commit:
            return
        f = item.data(Qt.UserRole)
        diff = self.git.get_commit_file_diff(self.commit["hash"], f["path"], f.get("orig_path", ""))
        self.diff.set_diff(f["path"], diff, f["status"], can_open=False)
