import os
import threading
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Pango

from git_service import GitService
from github_service import GitHubService
from ui.diff_view import DiffView
from ui.dialogs import SettingsDialog, NewBranchDialog, GitHubAccountDialog, RepositoryManagerDialog

class GitDesktopWindow(Adw.ApplicationWindow):
    def __init__(self, app, initial_repo_path=None):
        super().__init__(application=app)
        self.set_title("Git Desktop For Linux")
        self.set_default_size(1100, 720)

        self.gh_service = GitHubService()
        self.git = GitService(initial_repo_path or os.getcwd())

        # If it's a valid repo, add to recent repos list
        if self.git.is_git_repo():
            self.gh_service.add_recent_repo(self.git.repo_path)

        self.selected_file = None
        self.changed_files = []
        self.staged_state = {}

        self._build_ui()
        self.refresh_all()

    def _build_ui(self):
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_box)

        # ---------------- HEADER BAR ----------------
        self.header_bar = Adw.HeaderBar()
        root_box.append(self.header_bar)

        # 1. Repository Selector Button (Opens Repository Manager Dialog)
        self.repo_btn = Gtk.Button()
        self.repo_btn_content = Adw.ButtonContent(
            icon_name="folder-symbolic",
            label=self.git.get_repo_name() or "Select Repository"
        )
        self.repo_btn.set_child(self.repo_btn_content)
        self.repo_btn.connect("clicked", self._on_open_repo_manager)
        self.header_bar.pack_start(self.repo_btn)

        # 2. Branch Selector Button
        self.branch_menu_btn = Gtk.MenuButton()
        self.branch_btn_content = Adw.ButtonContent(
            icon_name="view-list-tree-symbolic",
            label="main"
        )
        self.branch_menu_btn.set_child(self.branch_btn_content)
        self.branch_popover = Gtk.Popover()
        self._setup_branch_popover()
        self.branch_menu_btn.set_popover(self.branch_popover)
        self.header_bar.pack_start(self.branch_menu_btn)

        # 3. External IDE Button (Center / Pack Start)
        self.ide_btn = Gtk.Button()
        self.ide_btn_content = Adw.ButtonContent(
            icon_name="text-editor-symbolic",
            label="Open in Visual Studio Code"
        )
        self.ide_btn.set_child(self.ide_btn_content)
        self.ide_btn.set_tooltip_text("Open current repository in your external IDE")
        self.ide_btn.connect("clicked", self._on_open_ide_clicked)
        self.header_bar.pack_start(self.ide_btn)

        # 4. Sync Action Button (Right Side)
        self.sync_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.sync_btn = Gtk.Button()
        self.sync_btn_content = Adw.ButtonContent(
            icon_name="view-refresh-symbolic",
            label="Fetch Origin"
        )
        self.sync_btn.set_child(self.sync_btn_content)
        self.sync_btn.connect("clicked", self._on_sync_clicked)
        self.sync_spinner = Gtk.Spinner()
        self.sync_box.append(self.sync_spinner)
        self.sync_box.append(self.sync_btn)
        self.header_bar.pack_end(self.sync_box)

        # 5. GitHub User Account Button
        self.gh_user_btn = Gtk.Button()
        self.gh_user_content = Adw.ButtonContent(
            icon_name="avatar-default-symbolic",
            label="GitHub"
        )
        self.gh_user_btn.set_child(self.gh_user_content)
        self.gh_user_btn.set_tooltip_text("GitHub Account & Login")
        self.gh_user_btn.connect("clicked", lambda _: GitHubAccountDialog(self, self.gh_service, self._on_github_account_changed).present())
        self.header_bar.pack_end(self.gh_user_btn)

        # 6. Preferences Button
        settings_btn = Gtk.Button(icon_name="emblem-system-symbolic")
        settings_btn.set_tooltip_text("Preferences")
        settings_btn.connect("clicked", lambda _: SettingsDialog(self, self.git, self.gh_service, self.refresh_all).present())
        self.header_bar.pack_end(settings_btn)

        # ---------------- MAIN CONTENT (PANED) ----------------
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(330)
        paned.set_vexpand(True)
        paned.set_hexpand(True)
        root_box.append(paned)

        # -------- LEFT SIDEBAR --------
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_box.set_size_request(280, -1)

        # Top Switcher: Changes | History
        switcher_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        switcher_box.add_css_class("linked")
        switcher_box.set_homogeneous(True)
        switcher_box.set_margin_start(10)
        switcher_box.set_margin_end(10)
        switcher_box.set_margin_top(8)
        switcher_box.set_margin_bottom(8)

        self.btn_tab_changes = Gtk.ToggleButton(label="Changes")
        self.btn_tab_changes.set_active(True)
        self.btn_tab_changes.connect("toggled", self._on_tab_toggle, "changes")
        switcher_box.append(self.btn_tab_changes)

        self.btn_tab_history = Gtk.ToggleButton(label="History")
        self.btn_tab_history.connect("toggled", self._on_tab_toggle, "history")
        switcher_box.append(self.btn_tab_history)

        sidebar_box.append(switcher_box)

        # Sidebar Stack
        self.sidebar_stack = Gtk.Stack()
        self.sidebar_stack.set_vexpand(True)
        sidebar_box.append(self.sidebar_stack)

        # --- Tab 1: Changes Page ---
        changes_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Changed files summary header
        ch_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ch_header.set_margin_start(12)
        ch_header.set_margin_end(12)
        ch_header.set_margin_top(4)
        ch_header.set_margin_bottom(6)

        self.select_all_check = Gtk.CheckButton()
        self.select_all_check.connect("toggled", self._on_select_all_toggled)
        ch_header.append(self.select_all_check)

        self.ch_count_label = Gtk.Label(label="0 changed files", xalign=0)
        self.ch_count_label.add_css_class("heading")
        self.ch_count_label.set_hexpand(True)
        ch_header.append(self.ch_count_label)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.add_css_class("flat")
        refresh_btn.set_tooltip_text("Refresh Status")
        refresh_btn.connect("clicked", lambda _: self.refresh_all())
        ch_header.append(refresh_btn)

        changes_page.append(ch_header)

        # Scrolled file list
        ch_scroll = Gtk.ScrolledWindow()
        ch_scroll.set_vexpand(True)
        self.files_listbox = Gtk.ListBox()
        self.files_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.files_listbox.connect("row-selected", self._on_file_selected)
        ch_scroll.set_child(self.files_listbox)
        changes_page.append(ch_scroll)

        # Commit Box (Pinned at bottom of Changes)
        commit_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        commit_box.set_margin_start(10)
        commit_box.set_margin_end(10)
        commit_box.set_margin_top(10)
        commit_box.set_margin_bottom(12)
        commit_box.add_css_class("card")

        self.commit_summary_entry = Gtk.Entry()
        self.commit_summary_entry.set_placeholder_text("Summary (required)")
        self.commit_summary_entry.connect("changed", self._update_commit_button_state)
        commit_box.append(self.commit_summary_entry)

        desc_scroll = Gtk.ScrolledWindow()
        desc_scroll.set_size_request(-1, 56)
        self.commit_desc_view = Gtk.TextView()
        self.commit_desc_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        desc_scroll.set_child(self.commit_desc_view)
        commit_box.append(desc_scroll)

        self.commit_btn = Gtk.Button(label="Commit to main")
        self.commit_btn.add_css_class("suggested-action")
        self.commit_btn.set_sensitive(False)
        self.commit_btn.connect("clicked", self._on_commit_clicked)
        commit_box.append(self.commit_btn)

        changes_page.append(commit_box)
        self.sidebar_stack.add_named(changes_page, "changes")

        # --- Tab 2: History Page ---
        history_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hist_scroll = Gtk.ScrolledWindow()
        hist_scroll.set_vexpand(True)
        self.history_listbox = Gtk.ListBox()
        self.history_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.history_listbox.connect("row-selected", self._on_commit_row_selected)
        hist_scroll.set_child(self.history_listbox)
        history_page.append(hist_scroll)

        self.sidebar_stack.add_named(history_page, "history")

        paned.set_start_child(sidebar_box)

        # -------- RIGHT MAIN AREA --------
        self.diff_view = DiffView(on_discard_callback=self._on_discard_file)
        paned.set_end_child(self.diff_view)

    # ---------------- BRANCH POPOVER ----------------
    def _setup_branch_popover(self):
        self.branch_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.branch_box.set_size_request(240, 280)
        self.branch_box.set_margin_start(10)
        self.branch_box.set_margin_end(10)
        self.branch_box.set_margin_top(10)
        self.branch_box.set_margin_bottom(10)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        lbl = Gtk.Label(label="<b>Branches</b>", use_markup=True, xalign=0)
        lbl.set_hexpand(True)
        header.append(lbl)

        btn_new = Gtk.Button(label="New Branch")
        btn_new.add_css_class("flat")
        btn_new.set_icon_name("list-add-symbolic")
        btn_new.connect("clicked", self._on_new_branch_clicked)
        header.append(btn_new)
        self.branch_box.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.branch_listbox = Gtk.ListBox()
        self.branch_listbox.connect("row-selected", self._on_branch_row_selected)
        scroll.set_child(self.branch_listbox)
        self.branch_box.append(scroll)

        self.branch_popover.set_child(self.branch_box)

    # ---------------- REFRESH & STATE ----------------
    def refresh_all(self):
        # 1. Update GitHub profile button in header
        profile = self.gh_service.get_user_profile()
        if profile:
            self.gh_user_content.set_label(f"@{profile['login']}")
        else:
            self.gh_user_content.set_label("Sign In")

        # 2. Update IDE Button in header
        preferred_editor = self.gh_service.get_preferred_editor()
        if preferred_editor:
            self.ide_btn_content.set_label(f"Open in {preferred_editor['name']}")
            self.ide_btn.set_visible(True)
        else:
            self.ide_btn.set_visible(False)

        # 3. Check if current folder is a git repo
        if not self.git.is_git_repo():
            self.diff_view.set_empty(
                "No Repository Open",
                f"The folder '{self.git.repo_path}' is not a git repository. Click '{self.git.get_repo_name() or 'Select Repository'}' at top left to open or clone a repo.",
                "dialog-error-symbolic"
            )
            self.repo_btn_content.set_label("Open Repository...")
            self.branch_btn_content.set_label("None")
            self.commit_btn.set_sensitive(False)
            self.sync_btn.set_sensitive(False)
            self.ide_btn.set_sensitive(False)
            return

        self.ide_btn.set_sensitive(True)
        self.sync_btn.set_sensitive(True)

        # 4. Update repo name & current branch
        self.repo_btn_content.set_label(self.git.get_repo_name())
        curr_branch = self.git.get_current_branch()
        self.branch_btn_content.set_label(curr_branch)
        self.commit_btn.set_label(f"Commit to {curr_branch}")

        # 5. Update Sync Status
        sync = self.git.get_sync_status()
        if sync['ahead'] > 0 and sync['behind'] > 0:
            self.sync_btn_content.set_label(f"Pull {sync['behind']} ↓ / Push {sync['ahead']} ↑")
        elif sync['ahead'] > 0:
            self.sync_btn_content.set_label(f"Push {sync['ahead']} ↑")
        elif sync['behind'] > 0:
            self.sync_btn_content.set_label(f"Pull {sync['behind']} ↓")
        else:
            self.sync_btn_content.set_label("Fetch Origin")

        # 6. Refresh Changed Files & History
        self.changed_files = self.git.get_status_files()
        self._populate_files_list()
        self._populate_history_list()
        self._populate_branch_list()

    def _populate_files_list(self):
        while row := self.files_listbox.get_first_child():
            self.files_listbox.remove(row)

        count = len(self.changed_files)
        self.ch_count_label.set_text(f"{count} changed file{'s' if count != 1 else ''}")

        if count == 0:
            self.diff_view.set_empty("No Local Changes", "Your working branch is clean. No uncommitted modifications.")
            self.commit_btn.set_sensitive(False)
            return

        for item in self.changed_files:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.set_margin_start(8)
            box.set_margin_end(8)
            box.set_margin_top(6)
            box.set_margin_bottom(6)

            # Checkbox
            check = Gtk.CheckButton()
            check.set_active(self.staged_state.get(item['path'], True))
            check.connect("toggled", self._on_file_check_toggled, item['path'])
            box.append(check)

            # Status Icon badge
            badge = Gtk.Label()
            status = item['status']
            if status in ('A', '?'):
                badge.set_markup("<span foreground='#2ec27e' weight='bold'>+</span>")
            elif status == 'D':
                badge.set_markup("<span foreground='#e01b24' weight='bold'>-</span>")
            elif status == 'R':
                badge.set_markup("<span foreground='#ff7800' weight='bold'>→</span>")
            else:
                badge.set_markup("<span foreground='#e5a50a' weight='bold'>●</span>")
            box.append(badge)

            # Text
            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            name_lbl = Gtk.Label(label=item['filename'], xalign=0)
            name_lbl.add_css_class("heading")
            name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            text_box.append(name_lbl)

            if item['dirname']:
                dir_lbl = Gtk.Label(label=item['dirname'], xalign=0)
                dir_lbl.add_css_class("dim-label")
                dir_lbl.add_css_class("caption")
                dir_lbl.set_ellipsize(Pango.EllipsizeMode.START)
                text_box.append(dir_lbl)

            box.append(text_box)
            row.set_child(box)
            row.file_data = item
            self.files_listbox.append(row)

        self._update_commit_button_state()
        if first := self.files_listbox.get_row_at_index(0):
            self.files_listbox.select_row(first)

    def _populate_history_list(self):
        while row := self.history_listbox.get_first_child():
            self.history_listbox.remove(row)

        commits = self.git.get_commit_history(40)
        for c in commits:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.set_margin_start(10)
            box.set_margin_end(10)
            box.set_margin_top(8)
            box.set_margin_bottom(8)

            top_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            summary_lbl = Gtk.Label(label=c['summary'], xalign=0)
            summary_lbl.add_css_class("heading")
            summary_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            summary_lbl.set_hexpand(True)
            top_line.append(summary_lbl)

            hash_badge = Gtk.Label(label=c['short_hash'])
            hash_badge.add_css_class("dim-label")
            hash_badge.add_css_class("caption")
            top_line.append(hash_badge)
            box.append(top_line)

            sub_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            author_lbl = Gtk.Label(label=f"{c['author']} • {c['date']}", xalign=0)
            author_lbl.add_css_class("dim-label")
            author_lbl.add_css_class("caption")
            sub_line.append(author_lbl)
            box.append(sub_line)

            row.set_child(box)
            row.commit_data = c
            self.history_listbox.append(row)

    def _populate_branch_list(self):
        while row := self.branch_listbox.get_first_child():
            self.branch_listbox.remove(row)

        branches = self.git.get_branches()
        curr = self.git.get_current_branch()

        for b in branches.get('local', []):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.set_margin_start(8)
            box.set_margin_end(8)
            box.set_margin_top(6)
            box.set_margin_bottom(6)

            icon = Gtk.Image(icon_name="view-list-tree-symbolic")
            box.append(icon)

            lbl = Gtk.Label(label=b, xalign=0)
            lbl.set_hexpand(True)
            if b == curr:
                lbl.add_css_class("heading")
                check = Gtk.Image(icon_name="emblem-ok-symbolic")
                box.append(check)
            box.append(lbl)

            row.set_child(box)
            row.branch_name = b
            self.branch_listbox.append(row)

    # ---------------- SELECTION & DIFF ----------------
    def _on_file_selected(self, _listbox, row):
        if not row:
            return
        item = getattr(row, 'file_data', None)
        if not item:
            return
        self.selected_file = item
        diff_text = self.git.get_diff(item['path'])
        self.diff_view.set_diff(
            item['path'],
            diff_text,
            is_untracked=(item['status'] == '?'),
            full_path=self.git.repo_path
        )

    def _on_commit_row_selected(self, _listbox, row):
        if not row:
            return
        c = getattr(row, 'commit_data', None)
        if not c:
            return
        diff_text = self.git.get_commit_diff(c['hash'])
        self.diff_view.set_commit_diff(c['summary'], c['hash'], diff_text)

    def _on_file_check_toggled(self, check, file_path):
        self.staged_state[file_path] = check.get_active()
        self._update_commit_button_state()

    def _on_select_all_toggled(self, check):
        active = check.get_active()
        for item in self.changed_files:
            self.staged_state[item['path']] = active

        row = self.files_listbox.get_first_child()
        while row:
            if hasattr(row, 'file_data'):
                box = row.get_child()
                first_widget = box.get_first_child()
                if isinstance(first_widget, Gtk.CheckButton):
                    first_widget.set_active(active)
            row = row.get_next_sibling()
        self._update_commit_button_state()

    def _update_commit_button_state(self, *_args):
        summary = self.commit_summary_entry.get_text().strip()
        has_staged = any(self.staged_state.get(f['path'], True) for f in self.changed_files)
        self.commit_btn.set_sensitive(bool(summary and has_staged))

    # ---------------- ACTIONS ----------------
    def _on_open_ide_clicked(self, _btn):
        if self.git.is_git_repo():
            self.gh_service.open_in_editor(self.git.repo_path)

    def _on_open_repo_manager(self, _btn):
        dialog = RepositoryManagerDialog(self, self.gh_service, self._on_switch_repo)
        dialog.present()

    def _on_switch_repo(self, new_repo_path):
        if os.path.exists(new_repo_path):
            self.git.set_repo_path(new_repo_path)
            self.gh_service.add_recent_repo(new_repo_path)
            self.refresh_all()

    def _on_github_account_changed(self):
        self.refresh_all()

    def _on_commit_clicked(self, _btn):
        summary = self.commit_summary_entry.get_text().strip()
        buf = self.commit_desc_view.get_buffer()
        start, end = buf.get_bounds()
        desc = buf.get_text(start, end, True).strip()

        for f in self.changed_files:
            path = f['path']
            if self.staged_state.get(path, True):
                self.git.stage_file(path)
            else:
                self.git.unstage_file(path)

        ok, msg = self.git.commit(summary, desc)
        if ok:
            self.commit_summary_entry.set_text("")
            buf.set_text("")
            self.refresh_all()
        else:
            self._show_alert("Commit Failed", msg)

    def _on_discard_file(self, file_path, is_untracked):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Discard changes?",
            body=f"Are you sure you want to discard changes in '{file_path}'? This action cannot be undone."
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("discard", "Discard")
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)

        def _on_response(_d, response):
            if response == "discard":
                self.git.discard_file(file_path, is_untracked)
                self.refresh_all()

        dialog.connect("response", _on_response)
        dialog.present()

    def _on_sync_clicked(self, _btn):
        self.sync_spinner.start()
        self.sync_btn.set_sensitive(False)

        def _worker():
            sync = self.git.get_sync_status()
            if sync['ahead'] > 0 and sync['behind'] == 0:
                ok, msg = self.git.push()
            elif sync['behind'] > 0 and sync['ahead'] == 0:
                ok, msg = self.git.pull()
            else:
                ok, msg = self.git.fetch()

            def _done():
                self.sync_spinner.stop()
                self.sync_btn.set_sensitive(True)
                if not ok:
                    self._show_alert("Sync Failed", msg)
                self.refresh_all()

            GLib.idle_add(_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_tab_toggle(self, btn, tab_name):
        if not btn.get_active():
            return
        if tab_name == "changes":
            self.btn_tab_history.set_active(False)
            self.sidebar_stack.set_visible_child_name("changes")
            if first := self.files_listbox.get_row_at_index(0):
                self.files_listbox.select_row(first)
        else:
            self.btn_tab_changes.set_active(False)
            self.sidebar_stack.set_visible_child_name("history")
            if first := self.history_listbox.get_row_at_index(0):
                self.history_listbox.select_row(first)

    def _on_branch_row_selected(self, _listbox, row):
        if not row:
            return
        branch = getattr(row, 'branch_name', None)
        if branch and branch != self.git.get_current_branch():
            ok, msg = self.git.checkout_branch(branch)
            self.branch_popover.popdown()
            if not ok:
                self._show_alert("Checkout Failed", msg)
            self.refresh_all()

    def _on_new_branch_clicked(self, _btn):
        self.branch_popover.popdown()
        NewBranchDialog(self, self.git.get_current_branch(), self._on_branch_created).present()

    def _on_branch_created(self, new_branch_name):
        ok, msg = self.git.create_and_checkout_branch(new_branch_name)
        if not ok:
            self._show_alert("Branch Creation Failed", msg)
        self.refresh_all()

    def _show_alert(self, title, message):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=title,
            body=message or "An error occurred."
        )
        dialog.add_response("ok", "OK")
        dialog.present()
