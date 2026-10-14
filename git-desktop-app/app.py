import sys
import os
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GtkSource', '5')
from gi.repository import Gtk, Adw, Gdk

from ui.window import GitDesktopWindow

class GitDesktopApp(Adw.Application):
    def __init__(self, target_repo=None):
        super().__init__(
            application_id="com.github.kefy266.GitDesktopLinux",
            flags=0
        )
        self.target_repo = target_repo
        self.window = None

    def do_activate(self):
        self._load_custom_css()
        if not self.window:
            repo_path = self.target_repo or os.getcwd()
            # If launched from inside git-desktop-app, default to parent git repo if current isn't a repo
            if not os.path.exists(os.path.join(repo_path, ".git")) and os.path.exists(os.path.join(repo_path, "..", ".git")):
                repo_path = os.path.abspath(os.path.join(repo_path, ".."))

            self.window = GitDesktopWindow(self, initial_repo_path=repo_path)
        self.window.present()

    def _load_custom_css(self):
        css = """
        .card {
            background-color: alpha(currentColor, 0.04);
            border-radius: 8px;
            padding: 8px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_string(css)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    app = GitDesktopApp(target_repo=target)
    return app.run(sys.argv[:1])

if __name__ == "__main__":
    sys.exit(main())
