import os
import subprocess
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GtkSource', '5')
from gi.repository import Gtk, Adw, GtkSource, Pango

class DiffView(Gtk.Box):
    def __init__(self, on_discard_callback=None, on_open_editor_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.on_discard_callback = on_discard_callback
        self.on_open_editor_callback = on_open_editor_callback
        self.current_file_path = None
        self.is_untracked = False

        # Header bar for the diff panel
        self.header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.header_box.set_margin_start(16)
        self.header_box.set_margin_end(16)
        self.header_box.set_margin_top(12)
        self.header_box.set_margin_bottom(12)

        # File Title and Subtitle
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_hexpand(True)

        self.title_label = Gtk.Label(xalign=0)
        self.title_label.add_css_class("title-4")
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        text_box.append(self.title_label)

        self.subtitle_label = Gtk.Label(xalign=0)
        self.subtitle_label.add_css_class("dim-label")
        self.subtitle_label.add_css_class("caption")
        self.subtitle_label.set_ellipsize(Pango.EllipsizeMode.START)
        text_box.append(self.subtitle_label)

        self.header_box.append(text_box)

        # Header Action Buttons
        self.action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.btn_editor = Gtk.Button(label="Open in Editor")
        self.btn_editor.set_icon_name("text-editor-symbolic")
        self.btn_editor.connect("clicked", self._on_open_in_editor)
        self.action_box.append(self.btn_editor)

        self.btn_discard = Gtk.Button(label="Discard")
        self.btn_discard.set_icon_name("edit-undo-symbolic")
        self.btn_discard.add_css_class("destructive-action")
        self.btn_discard.connect("clicked", self._on_discard_clicked)
        self.action_box.append(self.btn_discard)

        self.header_box.append(self.action_box)
        self.append(self.header_box)

        # Separator line
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)

        # Main content stack (Diff View vs Empty / Clean State)
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_hexpand(True)

        # 1. Diff Source View
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)

        self.source_buffer = GtkSource.Buffer()
        lm = GtkSource.LanguageManager.get_default()
        diff_lang = lm.get_language("diff")
        if diff_lang:
            self.source_buffer.set_language(diff_lang)

        sm = GtkSource.StyleSchemeManager.get_default()
        scheme = sm.get_scheme("Adwaita") or sm.get_scheme("Adwaita-dark")
        if scheme:
            self.source_buffer.set_style_scheme(scheme)

        self.source_view = GtkSource.View(buffer=self.source_buffer)
        self.source_view.set_editable(False)
        self.source_view.set_show_line_numbers(True)
        self.source_view.set_monospace(True)
        self.source_view.set_left_margin(12)
        self.source_view.set_right_margin(12)
        self.source_view.set_top_margin(8)
        self.source_view.set_bottom_margin(8)

        scrolled.set_child(self.source_view)
        self.stack.add_named(scrolled, "diff")

        # 2. Status Page (Clean / Empty state)
        self.status_page = Adw.StatusPage()
        self.status_page.set_title("No Local Changes")
        self.status_page.set_description("Your working branch is clean. Select a commit from History or create new edits.")
        self.status_page.set_icon_name("emblem-ok-symbolic")
        self.stack.add_named(self.status_page, "empty")

        self.append(self.stack)
        self.set_empty("No File Selected", "Select a changed file from the sidebar to view its diff.", "text-x-generic-symbolic")

    def set_diff(self, file_path: str, diff_text: str, is_untracked: bool = False, full_path: str = ""):
        self.current_file_path = file_path
        self.full_repo_path = full_path
        self.is_untracked = is_untracked

        filename = os.path.basename(file_path)
        dirname = os.path.dirname(file_path) or "./"

        self.title_label.set_text(filename)
        self.subtitle_label.set_text(dirname)
        self.header_box.set_visible(True)
        self.btn_discard.set_visible(True)
        self.btn_editor.set_visible(True)

        if not diff_text.strip():
            diff_text = "# No diff changes detected for this file."

        self.source_buffer.set_text(diff_text)
        self.stack.set_visible_child_name("diff")

    def set_commit_diff(self, commit_summary: str, commit_hash: str, diff_text: str):
        self.current_file_path = None
        self.title_label.set_text(commit_summary)
        self.subtitle_label.set_text(f"Commit: {commit_hash}")
        self.header_box.set_visible(True)
        self.btn_discard.set_visible(False)
        self.btn_editor.set_visible(False)

        self.source_buffer.set_text(diff_text)
        self.stack.set_visible_child_name("diff")

    def set_empty(self, title: str, description: str, icon_name: str = "emblem-ok-symbolic"):
        self.current_file_path = None
        self.header_box.set_visible(False)
        self.status_page.set_title(title)
        self.status_page.set_description(description)
        self.status_page.set_icon_name(icon_name)
        self.stack.set_visible_child_name("empty")

    def _on_discard_clicked(self, _btn):
        if self.current_file_path and self.on_discard_callback:
            self.on_discard_callback(self.current_file_path, self.is_untracked)

    def _on_open_in_editor(self, _btn):
        if not self.current_file_path:
            return
        # Prefer the editor chosen in Preferences
        if self.on_open_editor_callback and self.on_open_editor_callback(self.current_file_path):
            return

        target = self.current_file_path
        if hasattr(self, 'full_repo_path') and self.full_repo_path:
            target = os.path.join(self.full_repo_path, self.current_file_path)

        # Fallback: no known editor installed, let the desktop decide
        for cmd in ["xdg-open"]:
            try:
                subprocess.Popen([cmd, target])
                break
            except FileNotFoundError:
                continue
