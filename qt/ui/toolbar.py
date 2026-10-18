"""Toolbar: Current repository / Current branch / Fetch origin, plus their dropdowns."""

from typing import List, Optional

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from ui import icons, theme
from ui.delegates import group_repos

VALUE_ROLE = Qt.UserRole
KIND_ROLE = Qt.UserRole + 1


class ToolbarButton(QPushButton):
    """Rounded toolbar button: icon, small caption over a bold title, optional chevron."""

    def __init__(self, icon_name: str, caption: str, dropdown: bool = True, width: int = 230, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolbarButton")
        self.setFixedHeight(48)
        self.setMinimumWidth(width)
        self.setCursor(Qt.PointingHandCursor)
        self.icon_name = icon_name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 4, 10, 4)
        lay.setSpacing(12)
        self.icon_label = QLabel(objectName="ToolbarIcon")
        self.icon_label.setFixedSize(20, 20)
        lay.addWidget(self.icon_label)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        self.caption = QLabel(caption, objectName="ToolbarCaption")
        self.title = QLabel("", objectName="ToolbarTitle")
        texts.addWidget(self.caption)
        texts.addWidget(self.title)
        lay.addLayout(texts, 1)
        self.chevron = QLabel()
        self.chevron.setVisible(dropdown)
        lay.addWidget(self.chevron)
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.refresh_icons()

    def refresh_icons(self):
        c = theme.colors()
        color = c["text"] if self.isEnabled() else c["text_dim"]
        self.icon_label.setPixmap(icons.pixmap(self.icon_name, color, 20))
        self.chevron.setPixmap(icons.pixmap("chevron-down", c["text_dim"], 16))

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.EnabledChange:
            self.refresh_icons()

    def set_texts(self, title: str, caption: str = None, icon_name: str = None):
        self.title.setText(title)
        if caption is not None:
            self.caption.setText(caption)
        if icon_name is not None and icon_name != self.icon_name:
            self.icon_name = icon_name
            self.refresh_icons()

    def set_open(self, is_open: bool):
        # dynamic property -> must re-polish for the stylesheet to pick it up
        self.setProperty("open", is_open)
        self.style().unpolish(self)
        self.style().polish(self)


class FilterPopup(QFrame):
    """Dropdown panel: filter box + sectioned list. Subclasses fill the list."""

    SHADOW = 16

    activated = Signal(str, str)   # value, kind
    closed = Signal()

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("Popup")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(380 + 2 * self.SHADOW, 460 + 2 * self.SHADOW)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.SHADOW, self.SHADOW - 4, self.SHADOW, self.SHADOW + 4)
        card = QFrame(objectName="PopupCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 90))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        self.header = QWidget(objectName="PopupHeader")
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(4, 4, 4, 4)
        self.header_layout.setSpacing(6)
        self.filter = QLineEdit(placeholderText=placeholder)
        self.filter.addAction(icons.icon("search", theme.colors()["text_dim"]), QLineEdit.LeadingPosition)
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        self.filter.returnPressed.connect(self._activate_first)
        self.filter.installEventFilter(self)
        self.header_layout.addWidget(self.filter, 1)
        lay.addWidget(self.header)

        self.list = QListWidget()
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setIconSize(QSize(16, 16))
        self.list.itemActivated.connect(self._on_activated)
        self.list.itemClicked.connect(self._on_activated)
        lay.addWidget(self.list, 1)

    def add_section(self, title: str):
        item = QListWidgetItem(title.upper())
        item.setFlags(Qt.NoItemFlags)
        item.setForeground(QColor(theme.colors()["text_dim"]))
        item.setData(KIND_ROLE, "section")
        f = item.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 0.85)
        item.setFont(f)
        self.list.addItem(item)

    def add_entry(self, text: str, value: str, kind: str, tooltip: str = "", bold: bool = False, icon_name: str = ""):
        item = QListWidgetItem(text)
        if icon_name:
            item.setIcon(icons.icon(icon_name, theme.colors()["accent" if bold else "text_dim"]))
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
        self.move(anchor.mapToGlobal(QPoint(-self.SHADOW, anchor.height() + 4 - self.SHADOW + 4)))
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
        add_btn = QToolButton(text=" Add")
        add_btn.setIcon(icons.icon("plus", theme.colors()["text"]))
        add_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        add_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(add_btn)
        menu.addAction("Clone repository…", self.clone)
        menu.addAction("Create new repository…", self.create)
        menu.addAction("Add existing repository…", self.add_existing)
        add_btn.setMenu(menu)
        self.header_layout.addWidget(add_btn)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_menu)

    def set_repositories(self, repos: List[dict], current_path: str, github: Optional[List[dict]] = None,
                         github_state: str = "ok", local_full_names=(), me: str = ""):
        """Recent local repositories, then the account's GitHub repositories grouped by owner.

        github_state: "ok" | "loading" | "signed_out". GitHub repos already on disk
        (their full name is in local_full_names) are not listed twice.
        """
        self.list.clear()
        self.add_section("Recent")
        for r in repos:
            self.add_entry(r["name"], r["path"], "repo", tooltip=r["path"], bold=r["path"] == current_path,
                           icon_name="repo")
        if not repos:
            self.add_entry("No repositories yet — use Add", "", "none").setFlags(Qt.NoItemFlags)

        if github_state == "signed_out":
            self.add_section("GitHub.com")
            self.add_entry("Sign in to see your GitHub repositories…", "", "signin", icon_name="cloud-down")
            return
        if github_state == "loading":
            self.add_section("GitHub.com")
            self.add_entry("Loading your GitHub repositories…", "", "none").setFlags(Qt.NoItemFlags)
            return
        local = {n.lower() for n in local_full_names}
        remaining = [g for g in (github or []) if g["full_name"].lower() not in local]
        for owner, items in group_repos(remaining, me):
            self.add_section(f"GitHub.com · {owner}")
            for g in items:
                self.add_entry(g["name"], g["full_name"], "github",
                               tooltip=f"{g['full_name']}\n{g['description']}\nClick to clone".strip(),
                               icon_name="cloud-down")

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
        new_btn = QPushButton(" New branch")
        new_btn.setIcon(icons.icon("plus", theme.colors()["text"]))
        new_btn.clicked.connect(lambda: (self.hide(), self.new_branch.emit()))
        self.header_layout.addWidget(new_btn)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_menu)

    def set_branches(self, local: List[str], remote: List[str], current: str):
        self.list.clear()
        self.add_section("Local branches")
        for b in local:
            self.add_entry(b, b, "local", bold=b == current, icon_name="check" if b == current else "branch")
        # remote branches that have no local counterpart yet
        locals_set = set(local)
        remote_only = [r for r in remote if r.split("/", 1)[-1] not in locals_set]
        if remote_only:
            self.add_section("Remote branches")
            for r in remote_only:
                self.add_entry(r, r, "remote", icon_name="cloud-down")

    def _on_menu(self, pos):
        item = self.list.itemAt(pos)
        if not item or item.data(KIND_ROLE) != "local":
            return
        name = item.data(VALUE_ROLE)
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: (self.hide(), self.rename_branch.emit(name)))
        menu.addAction("Delete…", lambda: (self.hide(), self.delete_branch.emit(name)))
        menu.exec(self.list.viewport().mapToGlobal(pos))
