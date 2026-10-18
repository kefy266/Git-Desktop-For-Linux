"""Modern, rounded look: colors, Qt palettes, stylesheet, status badges, avatars."""

import hashlib
import os

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from ui import icons

LIGHT = {
    "bg": "#f5f6f8",          # window background
    "surface": "#ffffff",     # toolbar, sidebar, cards
    "surface2": "#f0f2f5",    # inputs, segmented control, secondary buttons
    "hover": "#e8ebf0",
    "border": "#e1e4ea",
    "text": "#1f2328",
    "text_dim": "#656d76",
    "accent": "#2f6feb",
    "accent_hover": "#2563d9",
    "accent_text": "#ffffff",
    "accent_soft": "#e4edfd",
    "warn_soft": "#fff6db",
    "warn_border": "#f0d58a",
    "diff_add_bg": "#e9f8ee",
    "diff_add_gutter": "#d3f2dd",
    "diff_del_bg": "#fdecee",
    "diff_del_gutter": "#fad7db",
    "diff_hunk_bg": "#eef3ff",
    "diff_hunk_text": "#57606a",
    "diff_gutter": "#ffffff",
    "diff_gutter_text": "#8c959f",
    "added": "#1a7f37",
    "modified": "#9a6700",
    "deleted": "#cf222e",
    "renamed": "#0969da",
    "conflicted": "#cf222e",
}

DARK = {
    "bg": "#14161b",
    "surface": "#1b1e25",
    "surface2": "#242833",
    "hover": "#2b303c",
    "border": "#2c313c",
    "text": "#e6e8ee",
    "text_dim": "#9aa3b2",
    "accent": "#4c8dff",
    "accent_hover": "#5f9aff",
    "accent_text": "#ffffff",
    "accent_soft": "#1f2c47",
    "warn_soft": "#2e2817",
    "warn_border": "#5c4b1f",
    "diff_add_bg": "#12261d",
    "diff_add_gutter": "#183426",
    "diff_del_bg": "#2a1619",
    "diff_del_gutter": "#3b1d22",
    "diff_hunk_bg": "#172036",
    "diff_hunk_text": "#8ea4d2",
    "diff_gutter": "#1b1e25",
    "diff_gutter_text": "#5d6575",
    "added": "#3fb950",
    "modified": "#d29922",
    "deleted": "#f85149",
    "renamed": "#58a6ff",
    "conflicted": "#f85149",
}

_current = dict(DARK)
_dark = True


def colors() -> dict:
    return _current


def is_dark() -> bool:
    return _dark


def system_prefers_dark(app: QApplication) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return app.palette().window().color().lightness() < 128


def _palette(c: dict) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: c["bg"], QPalette.WindowText: c["text"],
        QPalette.Base: c["surface"], QPalette.AlternateBase: c["surface2"],
        QPalette.Text: c["text"], QPalette.Button: c["surface2"], QPalette.ButtonText: c["text"],
        QPalette.Highlight: c["accent"], QPalette.HighlightedText: c["accent_text"],
        QPalette.ToolTipBase: c["surface"], QPalette.ToolTipText: c["text"],
        QPalette.PlaceholderText: c["text_dim"], QPalette.Link: c["accent"],
        QPalette.Mid: c["border"], QPalette.Light: c["surface"], QPalette.Dark: c["border"],
    }
    for role, value in roles.items():
        p.setColor(role, QColor(value))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(c["text_dim"]))
    return p


def _asset_dir() -> str:
    """Stylesheets can only load images from files: write the few we need to the cache."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = os.path.join(base, "git-desktop-linux", "qss")
    os.makedirs(path, exist_ok=True)
    return path


def _write_asset(name: str, svg_bytes: bytes) -> str:
    path = os.path.join(_asset_dir(), name)
    try:
        with open(path, "wb") as f:
            f.write(svg_bytes)
    except OSError:
        return ""
    return path.replace("\\", "/")


def _stylesheet(c: dict) -> str:
    check = _write_asset("check.svg", icons.svg("check", "#ffffff"))
    dash = _write_asset("dash.svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                                    b'<path d="M6 12h12" stroke="#ffffff" stroke-width="3" stroke-linecap="round"/></svg>')
    chevron = _write_asset(f"chevron-{c['text_dim'][1:]}.svg", icons.svg("chevron-down", c["text_dim"]))
    return f"""
    * {{ outline: 0; }}
    QMainWindow, QDialog {{ background: {c['bg']}; }}
    QSplitter::handle {{ background: {c['border']}; }}
    QToolTip {{ color: {c['text']}; background: {c['surface']}; border: 1px solid {c['border']};
               border-radius: 6px; padding: 4px 8px; }}
    QLabel {{ background: transparent; }}

    /* ---------------- toolbar ---------------- */
    #Toolbar {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
    #ToolbarButton {{ background: transparent; border: 1px solid transparent; border-radius: 10px; }}
    #ToolbarButton:hover {{ background: {c['hover']}; }}
    #ToolbarButton[open="true"] {{ background: {c['surface2']}; border: 1px solid {c['border']}; }}
    #ToolbarCaption {{ color: {c['text_dim']}; font-size: 11px; }}
    #ToolbarTitle {{ color: {c['text']}; font-weight: 600; }}
    #ToolbarTitle:disabled, #ToolbarCaption:disabled {{ color: {c['text_dim']}; }}
    #ToolbarDivider {{ background: {c['border']}; }}
    #CountBadge {{ background: {c['accent']}; color: {c['accent_text']}; border-radius: 8px;
                  padding: 0 6px; font-size: 11px; font-weight: 600; }}

    /* ---------------- sidebar ---------------- */
    #Sidebar {{ background: {c['surface']}; }}
    #Segmented {{ background: {c['surface2']}; border-radius: 10px; }}
    #Segmented QTabBar::tab {{
        background: transparent; color: {c['text_dim']}; border: none; border-radius: 8px;
        padding: 6px 10px; margin: 3px; font-weight: 600;
    }}
    #Segmented QTabBar::tab:selected {{ background: {c['surface'] if not _dark else c['hover']}; color: {c['text']}; }}
    #Segmented QTabBar::tab:hover:!selected {{ color: {c['text']}; }}
    #SectionHeader {{ background: transparent; }}

    QListWidget, QListView {{ background: transparent; border: none; }}
    QListWidget::item {{ border-radius: 8px; margin: 1px 6px; padding: 6px 6px; color: {c['text']}; }}
    QListWidget::item:hover {{ background: {c['hover']}; }}
    QListWidget::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}

    QCheckBox {{ spacing: 8px; color: {c['text']}; }}
    QCheckBox::indicator, QListView::indicator {{
        width: 16px; height: 16px; border-radius: 5px;
        border: 1.5px solid {c['text_dim']}; background: transparent;
    }}
    QCheckBox::indicator:hover, QListView::indicator:hover {{ border-color: {c['accent']}; }}
    QCheckBox::indicator:checked, QListView::indicator:checked {{
        background: {c['accent']}; border-color: {c['accent']}; image: url({check});
    }}
    QCheckBox::indicator:indeterminate, QListView::indicator:indeterminate {{
        background: {c['accent']}; border-color: {c['accent']}; image: url({dash});
    }}
    QCheckBox::indicator:disabled {{ border-color: {c['border']}; }}

    /* ---------------- inputs & buttons ---------------- */
    QLineEdit, QPlainTextEdit, QComboBox {{
        background: {c['surface2']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 8px; padding: 6px 10px;
        selection-background-color: {c['accent']}; selection-color: {c['accent_text']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; background: {c['surface']}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox::down-arrow {{ image: url({chevron}); width: 14px; height: 14px; }}
    QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']};
                                   border-radius: 8px; selection-background-color: {c['accent_soft']}; }}

    QPushButton, QToolButton {{
        background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']};
        border-radius: 8px; padding: 6px 14px;
    }}
    QPushButton:hover, QToolButton:hover {{ background: {c['hover']}; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {c['border']}; }}
    QPushButton:disabled, QToolButton:disabled {{ color: {c['text_dim']}; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}
    QDialogButtonBox {{ dialogbuttonbox-buttons-have-icons: 0; }}
    #PrimaryButton {{
        background: {c['accent']}; color: {c['accent_text']}; border: none;
        border-radius: 8px; padding: 9px 14px; font-weight: 600;
    }}
    #PrimaryButton:hover {{ background: {c['accent_hover']}; }}
    #PrimaryButton:disabled {{ background: {c['surface2']}; color: {c['text_dim']}; border: 1px solid {c['border']}; }}
    #FlatButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
    #FlatButton:hover {{ background: {c['hover']}; }}
    #MenuButton {{ background: transparent; border: none; border-radius: 8px; padding: 7px 8px;
                   text-align: left; color: {c['text']}; }}
    #MenuButton:hover {{ background: {c['hover']}; }}
    #LinkButton {{ background: transparent; border: none; color: {c['accent']}; padding: 2px 4px; font-weight: 600; }}
    #LinkButton:hover {{ text-decoration: underline; }}

    /* ---------------- cards ---------------- */
    #CommitBox {{ background: {c['surface']}; border-top: 1px solid {c['border']}; }}
    #Banner {{ background: {c['accent_soft']}; border-radius: 10px; }}
    #Banner[warn="true"] {{ background: {c['warn_soft']}; border: 1px solid {c['warn_border']}; }}
    #Card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
    #Card:hover {{ border-color: {c['accent']}; }}
    #Dim {{ color: {c['text_dim']}; }}
    #Title {{ font-size: 15px; font-weight: 600; color: {c['text']}; }}
    #BigTitle {{ font-size: 22px; font-weight: 700; color: {c['text']}; }}
    #EmptyIcon {{ background: {c['surface2']}; border-radius: 36px; }}

    /* ---------------- popups & menus ---------------- */
    #PopupCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
    QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; color: {c['text']}; }}
    QMenu::item:selected {{ background: {c['accent_soft']}; }}
    QMenu::item:disabled {{ color: {c['text_dim']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
    QMenuBar {{ background: {c['surface']}; color: {c['text']}; }}
    QMenuBar::item {{ padding: 4px 10px; border-radius: 6px; background: transparent; }}
    QMenuBar::item:selected {{ background: {c['hover']}; }}

    /* ---------------- diff ---------------- */
    #DiffHeader {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
    #DiffEditor {{ background: {c['surface']}; border: none; border-radius: 0; padding: 0; }}
    #MainArea {{ background: {c['surface']}; }}

    /* ---------------- tabs in dialogs ---------------- */
    QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 10px; background: {c['surface']}; top: -1px; }}
    QTabWidget > QTabBar::tab {{ background: transparent; color: {c['text_dim']}; padding: 8px 14px;
                                 border: none; border-bottom: 2px solid transparent; }}
    QTabWidget > QTabBar::tab:selected {{ color: {c['text']}; border-bottom: 2px solid {c['accent']}; }}
    QProgressBar {{ background: {c['surface2']}; border: none; border-radius: 4px; height: 6px; }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}

    /* ---------------- scrollbars ---------------- */
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle {{ background: {c['border']}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
    QScrollBar::handle:hover {{ background: {c['text_dim']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """


def apply_theme(app: QApplication, mode: str = "system") -> bool:
    """mode: 'system' | 'light' | 'dark'. Returns True when dark is active."""
    global _dark
    _dark = system_prefers_dark(app) if mode == "system" else mode == "dark"
    _current.clear()
    _current.update(DARK if _dark else LIGHT)
    icons.clear_cache()
    app.setStyle("Fusion")
    font = app.font()
    if font.pointSizeF() < 10:  # 9pt system fonts look cramped in this layout
        font.setPointSizeF(10)
        app.setFont(font)
    app.setPalette(_palette(_current))
    app.setStyleSheet(_stylesheet(_current))
    return _dark


# ---------------- status badges & avatars ----------------
STATUS_LETTER = {"A": "A", "?": "U", "C": "C", "M": "M", "D": "D", "R": "R", "U": "!"}
STATUS_COLOR = {"A": "added", "?": "added", "C": "added", "M": "modified",
                "D": "deleted", "R": "renamed", "U": "conflicted"}
STATUS_LABELS = {"A": "Added", "?": "New", "C": "Copied", "M": "Modified",
                 "D": "Deleted", "R": "Renamed", "U": "Conflicted"}


def status_color(status: str) -> QColor:
    return QColor(_current[STATUS_COLOR.get(status, "modified")])


def paint_status_badge(painter, rect: QRectF, status: str):
    """Small rounded pill with a letter (M, A, D…) in the status color."""
    color = status_color(status)
    bg = QColor(color)
    bg.setAlphaF(0.16)
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(bg)
    painter.drawRoundedRect(rect, 5, 5)
    f = QFont(painter.font())
    f.setPixelSize(int(rect.height() * 0.62))
    f.setBold(True)
    painter.setFont(f)
    painter.setPen(color)
    painter.drawText(rect, Qt.AlignCenter, STATUS_LETTER.get(status, "M"))
    painter.restore()


_AVATAR_COLORS = ["#e5534b", "#c69026", "#57ab5a", "#39c5cf", "#539bf5", "#986ee2", "#e275ad", "#f69d50"]


def avatar_color(seed: str) -> QColor:
    digest = hashlib.md5((seed or "?").lower().encode()).digest()
    return QColor(_AVATAR_COLORS[digest[0] % len(_AVATAR_COLORS)])


def initials(name: str) -> str:
    parts = [p for p in (name or "?").replace(".", " ").split() if p]
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper() if parts else "?"


def paint_avatar(painter, rect: QRectF, name: str, seed: str = ""):
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(avatar_color(seed or name))
    painter.drawEllipse(rect)
    f = QFont(painter.font())
    f.setPixelSize(int(rect.height() * 0.42))
    f.setBold(True)
    painter.setFont(f)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(rect, Qt.AlignCenter, initials(name))
    painter.restore()
