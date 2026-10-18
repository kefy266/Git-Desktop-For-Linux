"""Custom row painting for file and commit lists."""

import os

from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ui import icons, theme

FILE_ROLE = Qt.UserRole + 1     # dict with path / status / orig_path
COMMIT_ROLE = Qt.UserRole

_ROW_MARGIN_X = 6


def is_checked(index) -> bool:
    """PySide6 returns the check state as a plain int, not a Qt.CheckState."""
    value = index.data(Qt.CheckStateRole)
    return value is not None and Qt.CheckState(value) == Qt.Checked


def _row_rect(option) -> QRectF:
    return QRectF(option.rect).adjusted(_ROW_MARGIN_X, 1, -_ROW_MARGIN_X, -1)


def _paint_row_bg(painter, option):
    c = theme.colors()
    if option.state & QStyle.State_Selected:
        color = c["accent_soft"]
    elif option.state & QStyle.State_MouseOver:
        color = c["hover"]
    else:
        return
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(_row_rect(option), 8, 8)


class FileDelegate(QStyledItemDelegate):
    """Checkbox · file name (bold) + folder (dim) · status pill on the right."""

    ROW_H = 34
    BOX = 16

    def __init__(self, parent=None, checkable: bool = True):
        super().__init__(parent)
        self.checkable = checkable

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW_H)

    def _checkbox_rect(self, option) -> QRect:
        r = option.rect
        return QRect(r.left() + 16, r.center().y() - self.BOX // 2 + 1, self.BOX, self.BOX)

    def paint(self, painter, option, index):
        f = index.data(FILE_ROLE) or {}
        c = theme.colors()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        _paint_row_bg(painter, option)

        x = option.rect.left() + 16
        if self.checkable:
            box = QRectF(self._checkbox_rect(option))
            checked = is_checked(index)
            if checked:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(c["accent"]))
                painter.drawRoundedRect(box, 5, 5)
                painter.drawPixmap(box.adjusted(2, 2, -2, -2).toRect(), icons.pixmap("check", "#ffffff", 12))
            else:
                painter.setPen(QPen(QColor(c["text_dim"]), 1.5))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(box.adjusted(0.75, 0.75, -0.75, -0.75), 5, 5)
            x = int(box.right()) + 10

        badge = QRectF(option.rect.right() - _ROW_MARGIN_X - 30, option.rect.center().y() - 9 + 1, 20, 18)
        theme.paint_status_badge(painter, badge, f.get("status", "M"))

        text_rect = QRect(x, option.rect.top(), int(badge.left()) - x - 8, option.rect.height())
        path = f.get("path", index.data(Qt.DisplayRole) or "")
        name, folder = os.path.basename(path), os.path.dirname(path)
        if f.get("orig_path"):
            folder = f"{folder}  ← {f['orig_path']}".strip()

        bold = QFont(option.font)
        bold.setWeight(QFont.DemiBold)
        painter.setFont(bold)
        painter.setPen(QColor(c["text"]))
        fm = painter.fontMetrics()
        name_text = fm.elidedText(name, Qt.ElideMiddle, text_rect.width())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, name_text)
        used = fm.horizontalAdvance(name_text) + 8
        if folder and used < text_rect.width() - 20:
            painter.setFont(option.font)
            painter.setPen(QColor(c["text_dim"]))
            rest = QRect(text_rect.left() + used, text_rect.top(), text_rect.width() - used, text_rect.height())
            painter.drawText(rest, Qt.AlignVCenter | Qt.AlignLeft,
                             painter.fontMetrics().elidedText(folder, Qt.ElideLeft, rest.width()))
        painter.restore()

    def editorEvent(self, event, model, option, index):
        # Click on the checkbox toggles it without changing the selection
        if self.checkable and event.type() in (QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
            hit = self._checkbox_rect(option).adjusted(-8, -8, 8, 8)
            if hit.contains(event.position().toPoint()):
                if event.type() == QEvent.MouseButtonRelease:
                    model.setData(index, Qt.Unchecked if is_checked(index) else Qt.Checked, Qt.CheckStateRole)
                return True
        if self.checkable and event.type() == QEvent.MouseButtonPress:
            if self._checkbox_rect(option).adjusted(-8, -8, 8, 8).contains(event.position().toPoint()):
                return True
        return super().editorEvent(event, model, option, index)


class CommitDelegate(QStyledItemDelegate):
    """Avatar · bold summary · 'author · 2 hours ago'."""

    ROW_H = 54

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW_H)

    def paint(self, painter, option, index):
        commit = index.data(COMMIT_ROLE) or {}
        c = theme.colors()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        _paint_row_bg(painter, option)

        r = option.rect
        avatar = QRectF(r.left() + 16, r.center().y() - 14, 28, 28)
        theme.paint_avatar(painter, avatar, commit.get("author", ""), commit.get("email", ""))

        left = int(avatar.right()) + 12
        width = r.right() - _ROW_MARGIN_X - 10 - left
        line_h = option.fontMetrics.height()
        top = r.center().y() - line_h - 1

        bold = QFont(option.font)
        bold.setWeight(QFont.DemiBold)
        painter.setFont(bold)
        painter.setPen(QColor(c["text"]))
        painter.drawText(QRect(left, top, width, line_h), Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(commit.get("summary", ""), Qt.ElideRight, width))

        painter.setFont(option.font)
        painter.setPen(QColor(c["text_dim"]))
        sub = f"{commit.get('author', '')} · {commit.get('date', '')}"
        painter.drawText(QRect(left, top + line_h + 3, width, line_h), Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(sub, Qt.ElideRight, width))
        painter.restore()


REPO_ROLE = Qt.UserRole + 2     # GitHub repository dict; None for a section header
SECTION_ROLE = Qt.UserRole + 3  # section title text


class RepoDelegate(QStyledItemDelegate):
    """GitHub repository row: icon · name + description · Private/Fork tags · updated date.

    Rows without REPO_ROLE are owner section headers.
    """

    ROW_H = 50
    SECTION_H = 30

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW_H if index.data(REPO_ROLE) else self.SECTION_H)

    def paint(self, painter, option, index):
        c = theme.colors()
        repo = index.data(REPO_ROLE)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        r = option.rect
        if not repo:
            f = QFont(option.font)
            f.setBold(True)
            f.setPointSizeF(f.pointSizeF() * 0.85)
            painter.setFont(f)
            painter.setPen(QColor(c["text_dim"]))
            painter.drawText(r.adjusted(16, 0, -10, -2), Qt.AlignLeft | Qt.AlignBottom,
                             (index.data(SECTION_ROLE) or "").upper())
            painter.restore()
            return

        _paint_row_bg(painter, option)
        icon_name = "box" if repo.get("is_archived") else "repo"
        painter.drawPixmap(r.left() + 16, r.center().y() - 8,
                           icons.pixmap(icon_name, c["accent"] if not repo.get("is_private") else c["modified"], 16))

        # right side: date + tags
        right = r.right() - _ROW_MARGIN_X - 10
        painter.setFont(option.font)
        fm = painter.fontMetrics()
        date = repo.get("updated_at", "")
        if date:
            w = fm.horizontalAdvance(date)
            painter.setPen(QColor(c["text_dim"]))
            painter.drawText(QRect(right - w, r.top(), w, r.height()), Qt.AlignVCenter, date)
            right -= w + 10
        tag_font = QFont(option.font)
        tag_font.setPointSizeF(tag_font.pointSizeF() * 0.82)
        tag_font.setWeight(QFont.DemiBold)
        for tag, key in (("Archived", "is_archived"), ("Fork", "is_fork"), ("Private", "is_private")):
            if not repo.get(key):
                continue
            painter.setFont(tag_font)
            tw = painter.fontMetrics().horizontalAdvance(tag) + 14
            pill = QRectF(right - tw, r.center().y() - 9, tw, 18)
            painter.setPen(QPen(QColor(c["border"]), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(pill, 9, 9)
            painter.setPen(QColor(c["text_dim"]))
            painter.drawText(pill, Qt.AlignCenter, tag)
            right = int(pill.left()) - 6

        left = r.left() + 44
        width = right - left - 8
        line_h = option.fontMetrics.height()
        desc = repo.get("description", "")
        top = r.center().y() - (line_h if desc else line_h // 2) - (1 if desc else 0)
        bold = QFont(option.font)
        bold.setWeight(QFont.DemiBold)
        painter.setFont(bold)
        painter.setPen(QColor(c["text"]))
        painter.drawText(QRect(left, top, width, line_h), Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(repo.get("name", ""), Qt.ElideRight, width))
        if desc:
            painter.setFont(option.font)
            painter.setPen(QColor(c["text_dim"]))
            painter.drawText(QRect(left, top + line_h + 2, width, line_h), Qt.AlignLeft | Qt.AlignVCenter,
                             painter.fontMetrics().elidedText(desc, Qt.ElideRight, width))
        painter.restore()


def group_repos(repos, me: str = ""):
    """[(owner, [repos])] with the signed-in user first, then organizations A→Z."""
    groups = {}
    for repo in repos:
        groups.setdefault(repo.get("owner") or repo["full_name"].split("/")[0], []).append(repo)
    order = sorted(groups, key=lambda o: (o.lower() != (me or "").lower(), o.lower()))
    return [(o, groups[o]) for o in order]
