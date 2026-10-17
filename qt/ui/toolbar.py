"""Toolbar: Current repository / Current branch / Fetch origin, plus their dropdowns."""

from typing import List

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QPushButton, QToolButton, QVBoxLayout, QWidget,
)

VALUE_ROLE = Qt.UserRole
KIND_ROLE = Qt.UserRole + 1


class ToolbarButton(QPushButton):
    """Wide button with a small caption over a bold title, like GitHub Desktop's toolbar."""

    def __init__(self, glyph: str, caption: str, dropdown: bool = True, width: int = 230, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolbarButton")
        self.setFixedHeight(52)
        self.setMinimumWidth(width)
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(10)
        self.icon_label = QLabel(glyph, objectName="ToolbarIcon")
        f = self.icon_label.font()
        f.setPointSizeF(f.pointSizeF() * 1.3)
        self.icon_label.setFont(f)
        lay.addWidget(self.icon_label)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.caption = QLabel(caption, objectName="ToolbarCaption")
        self.title = QLabel("", objectName="ToolbarTitle")
        texts.addWidget(self.caption)
        texts.addWidget(self.title)
        lay.addLayout(texts, 1)
        if dropdown:
            lay.addWidget(QLabel("▾", objectName="ToolbarArrow"))
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_texts(self, title: str, caption: str = None, glyph: str = None):
        self.title.setText(title)
        if caption is not None:
            self.caption.setText(caption)
        if glyph is not None:
            self.icon_label.setText(glyph)

    def set_open(self, is_open: bool):
        # dynamic property -> must re-polish for the stylesheet to pick it up
        self.setProperty("open", is_open)
        for w in [self, *self.findChildren(QLabel)]:
            w.style().unpolish(w)
            w.style().polish(w)


class FilterPopup(QFrame):
    """Dropdown panel: filter box + sectioned list. Subclasses fill the list."""

    activated = Signal(str, str)   # value, kind
    closed = Signal()

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("Popup")
        self.setFixedSize(360, 440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = QWidget(objectName="PopupHeader")
        self.header.setAttribute(Qt.WA_StyledBackground, True)
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(8, 8, 8, 8)
        self.filter = QLineEdit(placeholderText=placeholder)
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        self.filter.returnPressed.connect(self._activate_first)
        self.filter.installEventFilter(self)
        self.header_layout.addWidget(self.filter, 1)
        lay.addWidget(self.header)

        self.list = QListWidget()
        self.list.itemActivated.connect(self._on_activated)
        self.list.itemClicked.connect(self._on_activated)
        lay.addWidget(self.list, 1)

    def add_section(self, title: str):
        item = QListWidgetItem(title.upper())
        item.setFlags(Qt.NoItemFlags)
        item.setData(KIND_ROLE, "section")
        f = item.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 0.85)
        item.setFont(f)
        self.list.addItem(item)

    def add_entry(self, text: str, value: str, kind: str, tooltip: str = "", bold: bool = False):
        item = QListWidgetItem(text)
        item.setData(VALUE_ROLE, value)
        item.setData(KIND_ROLE, kind)
        if tooltip:
            item.setToolTip(tooltip)
        if bold:
            f = item.font()
            f.setBold(True)
            item.setFont(f)
        self.list.addItem(item)
        return item

    def popup_below(self, anchor: QWidget):
        self.filter.clear()
        self.move(anchor.mapToGlobal(QPoint(0, anchor.height())))
        self.show()
        self.filter.setFocus()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.closed.emit()

    def eventFilter(self, obj, event):
        # Down arrow in the filter box jumps into the list
        if obj is self.filter and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Down:
            for i in range(self.list.count()):
                item = self.list.item(i)
                if not item.isHidden() and item.flags() & Qt.ItemIsEnabled:
                    self.list.setCurrentItem(item)
                    self.list.setFocus()
                    return True
        return super().eventFilter(obj, event)

    def _apply_filter(self, text: str):
        text = text.lower().strip()
        section = None
        section_has_match = False
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(KIND_ROLE) == "section":
                if section is not None:
                    section.setHidden(not section_has_match)
                section, section_has_match = item, False
                continue
            match = not text or text in item.text().lower()
            item.setHidden(not match)
            section_has_match |= match
        if section is not None:
            section.setHidden(not section_has_match)

    def _activate_first(self):
        def usable(it):
            return it is not None and not it.isHidden() and bool(it.flags() & Qt.ItemIsEnabled)

        item = self.list.currentItem()
        if not usable(item):
            item = next((self.list.item(i) for i in range(self.list.count()) if usable(self.list.item(i))), None)
        if item:
            self._on_activated(item)

    def _on_activated(self, item):
        kind = item.data(KIND_ROLE)
        # itemClicked and itemActivated can both fire for one click; act once
        if kind and kind != "section" and self.isVisible():
            self.hide()
            self.activated.emit(item.data(VALUE_ROLE), kind)


class RepositoryPopup(FilterPopup):
    add_existing = Signal()
    clone = Signal()
    create = Signal()
    remove_repo = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Filter", parent)
        add_btn = QToolButton(text="Add ▾")
        add_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(add_btn)
        menu.addAction("Clone repository…", self.clone)
        menu.addAction("Create new repository…", self.create)
        menu.addAction("Add existing repository…", self.add_existing)
        add_btn.setMenu(menu)
        self.header_layout.addWidget(add_btn)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_menu)

    def set_repositories(self, repos: List[dict], current_path: str):
        self.list.clear()
        self.add_section("Recent")
        for r in repos:
            self.add_entry(r["name"], r["path"], "repo", tooltip=r["path"], bold=r["path"] == current_path)
        if not repos:
            self.add_entry("No repositories yet — use Add", "", "none").setFlags(Qt.NoItemFlags)

    def _on_menu(self, pos):
        item = self.list.itemAt(pos)
        if not item or item.data(KIND_ROLE) != "repo":
            return
        menu = QMenu(self)
        menu.addAction("Remove from list", lambda: self.remove_repo.emit(item.data(VALUE_ROLE)))
        menu.exec(self.list.viewport().mapToGlobal(pos))


class BranchPopup(FilterPopup):
    new_branch = Signal()
    rename_branch = Signal(str)
    delete_branch = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Filter", parent)
        new_btn = QPushButton("New branch")
        new_btn.clicked.connect(lambda: (self.hide(), self.new_branch.emit()))
        self.header_layout.addWidget(new_btn)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_menu)

    def set_branches(self, local: List[str], remote: List[str], current: str):
        self.list.clear()
        self.add_section("Local branches")
        for b in local:
            self.add_entry(("✓ " if b == current else "    ") + b, b, "local", bold=b == current)
        # remote branches that have no local counterpart yet
        locals_set = set(local)
        remote_only = [r for r in remote if r.split("/", 1)[-1] not in locals_set]
        if remote_only:
            self.add_section("Remote branches")
            for r in remote_only:
                self.add_entry("    " + r, r, "remote")

    def _on_menu(self, pos):
        item = self.list.itemAt(pos)
        if not item or item.data(KIND_ROLE) != "local":
            return
        name = item.data(VALUE_ROLE)
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: (self.hide(), self.rename_branch.emit(name)))
        menu.addAction("Delete…", lambda: (self.hide(), self.delete_branch.emit(name)))
        menu.exec(self.list.viewport().mapToGlobal(pos))
