"""Unified diff viewer: old/new line-number gutter and colored rows, like GitHub Desktop."""

import re
from typing import List, Optional, Tuple

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ui import theme

MAX_DIFF_LINES = 20000
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")

# One displayed row: (kind, old line no, new line no, text)
Row = Tuple[str, Optional[int], Optional[int], str]


def parse_diff(diff_text: str) -> Tuple[List[Row], bool]:
    """Turns `git diff` output into rows. File headers are dropped, as GitHub Desktop does.

    Returns (rows, is_binary).
    """
    rows: List[Row] = []
    old_no = new_no = 0
    in_hunk = False
    for line in diff_text.splitlines():
        if not in_hunk and line.startswith("Binary files"):
            return [], True
        m = _HUNK_RE.match(line)
        if m:
            in_hunk = True
            old_no, new_no = int(m.group(1)), int(m.group(2))
            rows.append(("hunk", None, None, line))
            continue
        if not in_hunk:
            continue  # diff --git / index / --- / +++ headers
        if line.startswith("diff --git"):
            in_hunk = False  # next file in a multi-file diff
            continue
        if line.startswith("+"):
            rows.append(("add", None, new_no, line))
            new_no += 1
        elif line.startswith("-"):
            rows.append(("del", old_no, None, line))
            old_no += 1
        elif line.startswith("\\"):
            rows.append(("meta", None, None, line))  # "\ No newline at end of file"
        else:
            rows.append(("ctx", old_no, new_no, line))
            old_no += 1
            new_no += 1
    return rows, False


class _Gutter(QWidget):
    def __init__(self, editor: "DiffEditor"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(self, event)


class DiffEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DiffEditor")
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.rows: List[Row] = []
        self.gutter = _Gutter(self)
        self.blockCountChanged.connect(self._update_margins)
        self.updateRequest.connect(self._on_update_request)
        self._update_margins()

    # ---- gutter geometry ----
    def _digits(self) -> int:
        biggest = max([max(r[1] or 0, r[2] or 0) for r in self.rows] or [0])
        return max(3, len(str(biggest)))

    def gutter_width(self) -> int:
        char = self.fontMetrics().horizontalAdvance("9")
        return 2 * (self._digits() * char + 12)

    def _update_margins(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _on_update_request(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, widget, event):
        c = theme.colors()
        painter = QPainter(widget)
        painter.fillRect(event.rect(), QColor(c["diff_gutter"]))
        col_w = self.gutter_width() // 2
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            n = block.blockNumber()
            if block.isVisible() and n < len(self.rows):
                kind, old_no, new_no, _ = self.rows[n]
                bg = {"add": "diff_add_gutter", "del": "diff_del_gutter",
                      "hunk": "diff_hunk_bg"}.get(kind)
                if bg:
                    painter.fillRect(0, top, widget.width(), height, QColor(c[bg]))
                painter.setPen(QColor(c["diff_gutter_text"]))
                for i, num in enumerate((old_no, new_no)):
                    if num is not None:
                        painter.drawText(i * col_w, top, col_w - 6, height,
                                         Qt.AlignRight | Qt.AlignVCenter, str(num))
            block = block.next()
            top += height
        painter.setPen(QColor(c["border"]))
        painter.drawLine(widget.width() - 1, event.rect().top(), widget.width() - 1, event.rect().bottom())

    # ---- content ----
    def set_rows(self, rows: List[Row]):
        self.rows = rows
        self.setPlainText("\n".join(r[3] for r in rows))
        c = theme.colors()
        backgrounds = {"add": c["diff_add_bg"], "del": c["diff_del_bg"], "hunk": c["diff_hunk_bg"]}
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        block = self.document().begin()
        for kind, *_ in rows:
            if not block.isValid():
                break
            if kind in backgrounds or kind == "hunk":
                fmt = QTextBlockFormat()
                fmt.setBackground(QColor(backgrounds[kind]))
                cursor.setPosition(block.position())
                cursor.setBlockFormat(fmt)
                if kind == "hunk":
                    char_fmt = cursor.charFormat()
                    char_fmt.setForeground(QColor(c["diff_hunk_text"]))
                    cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                    cursor.setCharFormat(char_fmt)
            block = block.next()
        cursor.endEditBlock()
        self._update_margins()
        self.moveCursor(QTextCursor.Start)


class DiffView(QWidget):
    """Header (file name + actions) above the diff, or a blank-slate message."""

    open_in_editor = Signal(str)

    def __init__(self, parent=None, show_header=True):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QWidget(objectName="DiffHeader")
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(12, 6, 8, 6)
        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hl.addWidget(self.path_label, 1)
        self.editor_btn = QPushButton("Open in editor")
        self.editor_btn.clicked.connect(lambda: self.current_path and self.open_in_editor.emit(self.current_path))
        hl.addWidget(self.editor_btn)
        self.header.setVisible(False)
        self.show_header = show_header
        layout.addWidget(self.header)

        self.stack = QStackedWidget()
        self.editor = DiffEditor()
        self.message = QLabel(alignment=Qt.AlignCenter, wordWrap=True)
        self.message.setObjectName("Dim")
        self.message.setMargin(24)
        self.stack.addWidget(self.editor)
        self.stack.addWidget(self.message)
        layout.addWidget(self.stack, 1)

        self.current_path: Optional[str] = None
        self.show_message("No file selected.")

    def show_message(self, text: str):
        self.current_path = None
        self.header.setVisible(False)
        self.message.setText(text)
        self.stack.setCurrentWidget(self.message)

    def set_diff(self, path: str, diff_text: str, status: str = "M", can_open: bool = True):
        self.current_path = path
        self.path_label.setText(f"<b>{_escape(path)}</b>"
                                f" &nbsp;<span style='color:{theme.colors()['text_dim']}'>"
                                f"{theme.STATUS_LABELS.get(status, '')}</span>")
        self.editor_btn.setVisible(can_open)
        self.header.setVisible(self.show_header)

        rows, binary = parse_diff(diff_text)
        if binary:
            self.message.setText("This binary file has changed.")
            self.stack.setCurrentWidget(self.message)
            return
        if not rows:
            text = "The file is empty." if status in ("A", "?") else "No content changes (e.g. mode change only)."
            self.message.setText(text)
            self.stack.setCurrentWidget(self.message)
            return
        if len(rows) > MAX_DIFF_LINES:
            rows = rows[:MAX_DIFF_LINES] + [("meta", None, None, f"… diff truncated at {MAX_DIFF_LINES} lines")]
        self.editor.set_rows(rows)
        self.stack.setCurrentWidget(self.editor)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
