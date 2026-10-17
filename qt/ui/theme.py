"""GitHub Desktop look: colors (Primer palette), Qt palettes, stylesheet, status icons."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#ffffff",
    "bg_alt": "#f6f8fa",
    "border": "#e1e4e8",
    "text": "#24292e",
    "text_dim": "#586069",
    "blue": "#0366d6",
    "blue_disabled": "#94bfea",
    "selection": "#0366d6",
    "selection_text": "#ffffff",
    "toolbar_bg": "#24292e",
    "toolbar_hover": "#2f363d",
    "toolbar_open": "#ffffff",
    "toolbar_open_text": "#24292e",
    "toolbar_text": "#ffffff",
    "toolbar_caption": "#959da5",
    "banner_bg": "#fffbdd",
    "banner_border": "#e5d68e",
    "diff_add_bg": "#e6ffed",
    "diff_add_gutter": "#cdffd8",
    "diff_del_bg": "#ffeef0",
    "diff_del_gutter": "#ffdce0",
    "diff_hunk_bg": "#f1f8ff",
    "diff_hunk_text": "#586069",
    "diff_gutter": "#ffffff",
    "diff_gutter_text": "#959da5",
    "added": "#28a745",
    "modified": "#dbab09",
    "deleted": "#d73a49",
    "renamed": "#0366d6",
    "conflicted": "#d73a49",
}

DARK = {
    "bg": "#24292e",
    "bg_alt": "#1f2428",
    "border": "#141414",
    "text": "#d1d5da",
    "text_dim": "#959da5",
    "blue": "#2f81f7",
    "blue_disabled": "#2d4a6e",
    "selection": "#1f6feb",
    "selection_text": "#ffffff",
    "toolbar_bg": "#1f2428",
    "toolbar_hover": "#2f363d",
    "toolbar_open": "#24292e",
    "toolbar_open_text": "#ffffff",
    "toolbar_text": "#ffffff",
    "toolbar_caption": "#959da5",
    "banner_bg": "#3b3221",
    "banner_border": "#6b5a2b",
    "diff_add_bg": "#1f3a2a",
    "diff_add_gutter": "#244a33",
    "diff_del_bg": "#41262a",
    "diff_del_gutter": "#542d32",
    "diff_hunk_bg": "#1c2b3c",
    "diff_hunk_text": "#959da5",
    "diff_gutter": "#24292e",
    "diff_gutter_text": "#6a737d",
    "added": "#34d058",
    "modified": "#ffdf5d",
    "deleted": "#ea4a5a",
    "renamed": "#79b8ff",
    "conflicted": "#ea4a5a",
}

_current = dict(LIGHT)


def colors() -> dict:
    """Colors of the active theme."""
    return _current


def system_prefers_dark(app: QApplication) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # very old Qt: guess from the default palette
        return app.palette().window().color().lightness() < 128


def _palette(c: dict) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: c["bg"],
        QPalette.WindowText: c["text"],
        QPalette.Base: c["bg"],
        QPalette.AlternateBase: c["bg_alt"],
        QPalette.Text: c["text"],
        QPalette.Button: c["bg_alt"],
        QPalette.ButtonText: c["text"],
        QPalette.Highlight: c["selection"],
        QPalette.HighlightedText: c["selection_text"],
        QPalette.ToolTipBase: c["bg_alt"],
        QPalette.ToolTipText: c["text"],
        QPalette.PlaceholderText: c["text_dim"],
        QPalette.Link: c["blue"],
        QPalette.Mid: c["border"],
    }
    for role, value in roles.items():
        p.setColor(role, QColor(value))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(c["text_dim"]))
    return p


def _stylesheet(c: dict) -> str:
    return f"""
    QMainWindow, QDialog {{ background: {c['bg']}; }}
    QSplitter::handle {{ background: {c['border']}; }}
    QToolTip {{ color: {c['text']}; background: {c['bg_alt']}; border: 1px solid {c['border']}; }}

    /* ---------- toolbar (always dark, like GitHub Desktop) ---------- */
    #Toolbar {{ background: {c['toolbar_bg']}; border-bottom: 1px solid #000; }}
    #ToolbarButton {{
        background: transparent; border: none; border-right: 1px solid #000;
        color: {c['toolbar_text']}; text-align: left; padding: 0;
    }}
    #ToolbarButton:hover {{ background: {c['toolbar_hover']}; }}
    #ToolbarButton[open="true"] {{ background: {c['toolbar_open']}; }}
    #ToolbarButton[open="true"] QLabel {{ color: {c['toolbar_open_text']}; }}
    #ToolbarButton:disabled QLabel {{ color: #6a737d; }}
    #ToolbarCaption {{ color: {c['toolbar_caption']}; font-size: 11px; }}
    #ToolbarTitle {{ color: {c['toolbar_text']}; font-weight: 600; }}
    #ToolbarIcon, #ToolbarArrow {{ color: {c['toolbar_text']}; }}

    /* ---------- sidebar ---------- */
    #Sidebar {{ background: {c['bg']}; }}
    QTabBar::tab {{
        background: {c['bg']}; color: {c['text']}; padding: 8px 12px;
        border: none; border-bottom: 1px solid {c['border']};
    }}
    QTabBar::tab:selected {{ border-bottom: 2px solid {c['blue']}; font-weight: 600; }}
    QTabBar::tab:hover:!selected {{ background: {c['bg_alt']}; }}
    #SectionHeader {{ background: {c['bg_alt']}; border-bottom: 1px solid {c['border']}; }}
    QListWidget, QListView {{
        background: {c['bg']}; border: none; outline: 0;
    }}
    QListWidget::item {{ padding: 4px 6px; }}
    QListWidget::item:selected {{ background: {c['selection']}; color: {c['selection_text']}; }}

    #CommitBox {{ background: {c['bg_alt']}; border-top: 1px solid {c['border']}; }}
    QLineEdit, QPlainTextEdit {{
        background: {c['bg']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 4px; padding: 4px 6px;
        selection-background-color: {c['selection']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {c['blue']}; }}
    #PrimaryButton {{
        background: {c['blue']}; color: #ffffff; border: none; border-radius: 4px;
        padding: 6px 12px; font-weight: 600;
    }}
    #PrimaryButton:disabled {{ background: {c['blue_disabled']}; color: #e8f1fb; }}
    #PrimaryButton:hover:!disabled {{ background: #035fc7; }}
    #Banner {{ background: {c['banner_bg']}; border-top: 1px solid {c['banner_border']}; }}
    #Dim {{ color: {c['text_dim']}; }}
    #BlankTitle {{ font-size: 20px; font-weight: 600; }}

    /* ---------- popups ---------- */
    #Popup {{ background: {c['bg']}; border: 1px solid {c['border']}; }}
    #PopupHeader {{ background: {c['bg_alt']}; border-bottom: 1px solid {c['border']}; }}
    #ListSection {{ color: {c['text_dim']}; font-weight: 600; }}

    /* ---------- diff ---------- */
    #DiffHeader {{ background: {c['bg_alt']}; border-bottom: 1px solid {c['border']}; }}
    #DiffEditor {{ border: none; border-radius: 0; padding: 0; }}
    """


def apply_theme(app: QApplication, mode: str = "system") -> bool:
    """mode: 'system' | 'light' | 'dark'. Returns True when dark is active."""
    dark = system_prefers_dark(app) if mode == "system" else mode == "dark"
    _current.clear()
    _current.update(DARK if dark else LIGHT)
    app.setStyle("Fusion")
    app.setPalette(_palette(_current))
    app.setStyleSheet(_stylesheet(_current))
    return dark


# status -> (color key, glyph)
_STATUS = {
    "A": ("added", "+"),
    "?": ("added", "+"),
    "C": ("added", "+"),
    "M": ("modified", "•"),
    "D": ("deleted", "−"),
    "R": ("renamed", "→"),
    "U": ("conflicted", "!"),
}

_icon_cache: dict = {}


def status_icon(status: str) -> QIcon:
    """Small rounded square with a glyph, like GitHub Desktop's file status icons."""
    key_name, glyph = _STATUS.get(status, _STATUS["M"])
    color = QColor(_current[key_name])
    cache_key = (status, color.name())
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    size = 32  # drawn large, Qt scales it down crisply
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(color, 3))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(3, 3, size - 6, size - 6), 6, 6)
    font = QFont()
    font.setPixelSize(22)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRectF(0, -1, size, size), Qt.AlignCenter, glyph)
    p.end()

    icon = QIcon(pm)
    _icon_cache[cache_key] = icon
    return icon


STATUS_LABELS = {
    "A": "Added", "?": "New", "C": "Copied", "M": "Modified",
    "D": "Deleted", "R": "Renamed", "U": "Conflicted",
}
