"""Git Desktop For Linux — Qt edition, modeled on GitHub Desktop.

Run:
    .venv/bin/python app.py [path/to/repo]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication  # noqa: E402

from github_service import GitHubService  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.theme import apply_theme  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Git Desktop For Linux")
    app.setOrganizationName("GitDesktopLinux")
    app.setDesktopFileName("com.github.kefy266.GitDesktopLinux")

    theme_mode = GitHubService().get_setting("theme", "system")
    apply_theme(app, theme_mode)
    # Follow live light/dark switches of the desktop when set to "system"
    try:
        app.styleHints().colorSchemeChanged.connect(
            lambda _s: GitHubService().get_setting("theme", "system") == "system" and apply_theme(app, "system"))
    except AttributeError:
        pass

    repo = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    window = MainWindow(repo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
