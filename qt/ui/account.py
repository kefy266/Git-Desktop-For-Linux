"""GitHub account: avatar button in the toolbar, profile card, and the sign-in dialog."""

import shutil
from typing import Optional

from PySide6.QtCore import QPoint, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from ui import icons, theme
from ui.workers import run_async

TOKEN_URL = ("https://github.com/settings/tokens/new?scopes=repo,read:org,workflow"
             "&description=Git%20Desktop%20For%20Linux")


def paint_profile_avatar(painter: QPainter, rect: QRectF, profile: Optional[dict], pixmap: Optional[QPixmap]):
    """Round GitHub avatar; initials while it loads; a person outline when signed out."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    if profile and pixmap and not pixmap.isNull():
        path = QPainterPath()
        path.addEllipse(rect)
        painter.setClipPath(path)
        painter.drawPixmap(rect.toRect(), pixmap)
    elif profile:
        theme.paint_avatar(painter, rect, profile.get("name") or profile.get("login", ""), profile.get("login", ""))
    else:
        c = theme.colors()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(c["surface2"]))
        painter.drawEllipse(rect)
        painter.setPen(QColor(c["text_dim"]))
        painter.setBrush(Qt.NoBrush)
        head = QRectF(rect.center().x() - rect.width() * 0.15, rect.top() + rect.height() * 0.2,
                      rect.width() * 0.3, rect.height() * 0.3)
        painter.drawEllipse(head)
        body = QRectF(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.58,
                      rect.width() * 0.56, rect.height() * 0.5)
        painter.drawArc(body, 0, 180 * 16)
    painter.restore()


class ProfileButton(QPushButton):
    """Round avatar in the toolbar. Click opens the account card."""

    def __init__(self, parent=None):
        super().__init__(parent, objectName="FlatButton")
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.profile: Optional[dict] = None
        self.avatar: Optional[QPixmap] = None
        self.set_profile(None)

    def set_profile(self, profile: Optional[dict], avatar: Optional[QPixmap] = None):
        self.profile, self.avatar = profile, avatar
        if profile:
            self.setToolTip(f"Signed in as @{profile.get('login', '')}")
        else:
            self.setToolTip("Sign in to GitHub.com")
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)  # hover background from the stylesheet
        paint_profile_avatar(QPainter(self), QRectF(self.rect()).adjusted(6, 6, -6, -6), self.profile, self.avatar)


class _BigAvatar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self.profile = self.pixmap = None

    def paintEvent(self, _e):
        paint_profile_avatar(QPainter(self), QRectF(self.rect()), self.profile, self.pixmap)


class AccountPopup(QFrame):
    """Card under the avatar: who is signed in, profile link, options, sign out / sign in."""

    sign_in = Signal()
    sign_out = Signal()
    options = Signal()

    SHADOW = 16

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(300 + 2 * self.SHADOW)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.SHADOW, self.SHADOW - 4, self.SHADOW, self.SHADOW + 4)
        self.card = QFrame(objectName="PopupCard")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)
        self.lay = QVBoxLayout(self.card)
        self.lay.setContentsMargins(16, 16, 16, 12)
        self.lay.setSpacing(10)
        self.profile_url = ""

    def _clear(self):
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().hide()  # deleteLater is deferred; hide so it can't affect the size now
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().hide()
                        sub.widget().deleteLater()

    def _menu_button(self, text: str, icon_name: str, slot) -> QPushButton:
        btn = QPushButton(f"  {text}", objectName="MenuButton")
        btn.setIcon(icons.icon(icon_name, theme.colors()["text_dim"]))
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: (self.hide(), slot()))
        return btn

    def set_profile(self, profile: Optional[dict], avatar: Optional[QPixmap], repo_count: Optional[int] = None,
                    loading: bool = False):
        self._clear()
        if loading:
            self.lay.addWidget(QLabel("Checking your GitHub account…", objectName="Dim"))
        elif profile:
            head = QHBoxLayout()
            head.setSpacing(12)
            big = _BigAvatar()
            big.profile, big.pixmap = profile, avatar
            head.addWidget(big)
            names = QVBoxLayout()
            names.setSpacing(2)
            name = QLabel(profile.get("name") or profile.get("login", ""), objectName="Title")
            name.setTextFormat(Qt.PlainText)
            names.addWidget(name)
            login = QLabel(f"@{profile.get('login', '')}", objectName="Dim")
            login.setTextFormat(Qt.PlainText)
            names.addWidget(login)
            head.addLayout(names, 1)
            self.lay.addLayout(head)
            if repo_count is not None:
                stats = QLabel(f"{repo_count} repositories on GitHub.com", objectName="Dim")
                self.lay.addWidget(stats)
            self.lay.addWidget(self._separator())
            self.profile_url = profile.get("html_url") or f"https://github.com/{profile.get('login', '')}"
            self.lay.addWidget(self._menu_button("Your profile on GitHub", "external",
                                                 lambda: QDesktopServices.openUrl(QUrl(self.profile_url))))
            self.lay.addWidget(self._menu_button("Options…", "settings", self.options.emit))
            self.lay.addWidget(self._separator())
            self.lay.addWidget(self._menu_button("Sign out", "logout", self.sign_out.emit))
        else:
            title = QLabel("Not signed in", objectName="Title")
            self.lay.addWidget(title)
            hint = QLabel("Sign in to see your repositories and to push, pull and clone without passwords.",
                          wordWrap=True, objectName="Dim")
            self.lay.addWidget(hint)
            btn = QPushButton("Sign in to GitHub.com", objectName="PrimaryButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda: (self.hide(), self.sign_in.emit()))
            self.lay.addWidget(btn)
            self.lay.addWidget(self._menu_button("Options…", "settings", self.options.emit))
        # shrink/grow to the new content (signed-in and signed-out cards differ in height)
        self.lay.activate()
        self.setFixedHeight(self.sizeHint().height())

    def _separator(self) -> QFrame:
        line = QFrame(objectName="ToolbarDivider")
        line.setAttribute(Qt.WA_StyledBackground, True)
        line.setFixedHeight(1)
        return line

    def popup_below(self, anchor: QWidget):
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(anchor.width(), anchor.height() + 4))
        self.move(pos.x() - self.width() + self.SHADOW, pos.y() - self.SHADOW + 4)
        self.show()


class SignInDialog(QDialog):
    """Sign in with a personal access token (validated before saving), or via the GitHub CLI."""

    def __init__(self, gh_service, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sign in to GitHub.com")
        self.setFixedWidth(480)
        self.gh = gh_service
        self.profile: Optional[dict] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 20)
        lay.setSpacing(12)
        title = QLabel("Sign in to GitHub.com", objectName="BigTitle")
        lay.addWidget(title)
        intro = QLabel("Your repositories will show up in Git Desktop, and pushing, pulling and cloning over "
                       "HTTPS will use this account.", wordWrap=True, objectName="Dim")
        lay.addWidget(intro)

        # --- step 1: create a token ---
        step1 = QLabel("<b>1.</b> Create a personal access token on GitHub (the <i>repo</i> scope is enough).",
                       wordWrap=True, textFormat=Qt.RichText)
        lay.addWidget(step1)
        open_btn = QPushButton("  Create a token on github.com")
        open_btn.setIcon(icons.icon("cloud-down", theme.colors()["accent"]))
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(TOKEN_URL)))
        lay.addWidget(open_btn, 0, Qt.AlignLeft)

        # --- step 2: paste it ---
        lay.addWidget(QLabel("<b>2.</b> Paste the token here:", textFormat=Qt.RichText))
        self.token_edit = QLineEdit(placeholderText="ghp_… or github_pat_…")
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.returnPressed.connect(self._sign_in)
        self.token_edit.textChanged.connect(lambda t: self.sign_in_btn.setEnabled(bool(t.strip())))
        lay.addWidget(self.token_edit)

        self.status = QLabel(wordWrap=True)
        self.status.setVisible(False)
        lay.addWidget(self.status)

        # --- alternative: GitHub CLI ---
        if shutil.which("gh"):
            cli = QLabel("Already use the GitHub CLI? Run <code>gh auth login</code> in a terminal, then press "
                         "<i>Check again</i>.", wordWrap=True, objectName="Dim", textFormat=Qt.RichText)
            lay.addWidget(cli)

        buttons = QDialogButtonBox()
        if shutil.which("gh"):
            again = buttons.addButton("Check again", QDialogButtonBox.ActionRole)
            again.clicked.connect(self._check_cli)
        self.sign_in_btn = buttons.addButton("Sign in", QDialogButtonBox.AcceptRole)
        self.sign_in_btn.setObjectName("PrimaryButton")
        self.sign_in_btn.setEnabled(False)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._sign_in)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _show_status(self, text: str, error: bool):
        color = theme.colors()["deleted" if error else "text_dim"]
        self.status.setStyleSheet(f"color: {color};")
        self.status.setText(text)
        self.status.setVisible(True)

    def _sign_in(self):
        token = self.token_edit.text().strip()
        if not token:
            return
        self.sign_in_btn.setEnabled(False)
        self._show_status("Checking the token…", error=False)

        def done(profile):
            if profile:
                self.gh.set_token(token)
                self.profile = profile
                self.accept()
            else:
                self.sign_in_btn.setEnabled(True)
                self._show_status("GitHub did not accept this token, or GitHub could not be reached.", error=True)

        run_async(self.gh.get_user_profile, token=token, on_done=done,
                  on_error=lambda e: (self.sign_in_btn.setEnabled(True), self._show_status(e, error=True)))

    def _check_cli(self):
        """After `gh auth login`: allow the gh token again and see if it works."""
        self.gh.set_setting("use_gh_cli", True)
        self._show_status("Checking the GitHub CLI login…", error=False)

        def done(profile):
            if profile:
                self.profile = profile
                self.accept()
            else:
                self._show_status("The GitHub CLI is not signed in yet. Run `gh auth login` first.", error=True)

        run_async(self.gh.get_user_profile, on_done=done,
                  on_error=lambda e: self._show_status(e, error=True))
