import os
import threading
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Pango

# ==================== SETTINGS DIALOG ====================
class SettingsDialog(Adw.PreferencesWindow):
    def __init__(self, parent_window, git_service, gh_service, on_save_callback=None):
        super().__init__(transient_for=parent_window, modal=True)
        self.set_title("Preferences")
        self.set_default_size(520, 480)
        self.git_service = git_service
        self.gh_service = gh_service
        self.on_save_callback = on_save_callback

        # --- Page 1: Git Identity ---
        git_page = Adw.PreferencesPage()
        git_page.set_title("Git")
        git_page.set_icon_name("user-info-symbolic")

        id_group = Adw.PreferencesGroup()
        id_group.set_title("Git User Identity")
        id_group.set_description("This information will be associated with the commits you make locally.")

        cur_name, cur_email = self.git_service.get_user_info()

        self.name_row = Adw.EntryRow()
        self.name_row.set_title("Name")
        self.name_row.set_text(cur_name)
        id_group.add(self.name_row)

        self.email_row = Adw.EntryRow()
        self.email_row.set_title("Email")
        self.email_row.set_text(cur_email)
        id_group.add(self.email_row)
        git_page.add(id_group)

        # --- Editor Integration Group ---
        editor_group = Adw.PreferencesGroup()
        editor_group.set_title("External Editor / IDE")
        editor_group.set_description("Choose your preferred editor to open repositories and files.")

        installed = self.gh_service.detect_installed_editors()
        curr_editor = self.gh_service.get_preferred_editor()

        self.editor_combo = Adw.ComboRow()
        self.editor_combo.set_title("Default IDE")
        editor_names = [e["name"] for e in installed] or ["None detected"]
        self.editor_models = installed
        string_list = Gtk.StringList.new(editor_names)
        self.editor_combo.set_model(string_list)

        # Select current
        if curr_editor and installed:
            for idx, ed in enumerate(installed):
                if ed["cmd"] == curr_editor["cmd"]:
                    self.editor_combo.set_selected(idx)
                    break

        editor_group.add(self.editor_combo)
        git_page.add(editor_group)

        # Save Button
        save_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        save_box.set_halign(Gtk.Align.END)
        save_box.set_margin_top(16)
        save_btn = Gtk.Button(label="Save Preferences")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        save_box.append(save_btn)
        
        save_group = Adw.PreferencesGroup()
        save_group.add(save_box)
        git_page.add(save_group)

        self.add(git_page)

    def _on_save(self, _btn):
        name = self.name_row.get_text().strip()
        email = self.email_row.get_text().strip()
        if name and email:
            self.git_service.set_user_info(name, email, is_global=True)

        selected_idx = self.editor_combo.get_selected()
        if self.editor_models and selected_idx < len(self.editor_models):
            ed = self.editor_models[selected_idx]
            self.gh_service.set_preferred_editor(ed["cmd"])

        if self.on_save_callback:
            self.on_save_callback()
        self.close()


# ==================== GITHUB ACCOUNT DIALOG ====================
class GitHubAccountDialog(Adw.Window):
    def __init__(self, parent_window, gh_service, on_change_callback=None):
        super().__init__(transient_for=parent_window, modal=True)
        self.set_title("GitHub Account")
        self.set_default_size(440, 360)
        self.gh_service = gh_service
        self.on_change_callback = on_change_callback

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.box.set_margin_start(24)
        self.box.set_margin_end(24)
        self.box.set_margin_top(24)
        self.box.set_margin_bottom(24)
        self.set_content(self.box)

        self._refresh_content()

    def _clear_box(self):
        while child := self.box.get_first_child():
            self.box.remove(child)

    def _refresh_content(self, error_text=None):
        # Network request runs in a thread so the dialog never freezes
        self._clear_box()
        spinner = Gtk.Spinner(spinning=True, vexpand=True, valign=Gtk.Align.CENTER)
        spinner.set_size_request(32, 32)
        self.box.append(spinner)

        def _worker():
            profile = self.gh_service.get_user_profile()
            GLib.idle_add(self._render_content, profile, error_text)

        threading.Thread(target=_worker, daemon=True).start()

    def _render_content(self, profile, error_text=None):
        self._clear_box()
        if profile:
            # Logged In View
            title_lbl = Gtk.Label(label="Connected to GitHub", xalign=0)
            title_lbl.add_css_class("title-2")
            self.box.append(title_lbl)

            card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            card.add_css_class("card")
            card.set_margin_top(8)

            avatar_icon = Gtk.Image(icon_name="avatar-default-symbolic")
            avatar_icon.set_pixel_size(48)
            card.append(avatar_icon)

            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            name_lbl = Gtk.Label(label=f"<b>{GLib.markup_escape_text(profile['name'] or '')}</b>", use_markup=True, xalign=0)
            name_lbl.add_css_class("heading")
            info_box.append(name_lbl)

            login_lbl = Gtk.Label(label=f"@{profile['login']}", xalign=0)
            login_lbl.add_css_class("dim-label")
            info_box.append(login_lbl)

            if profile.get("bio"):
                bio_lbl = Gtk.Label(label=profile["bio"], xalign=0, wrap=True)
                bio_lbl.add_css_class("caption")
                info_box.append(bio_lbl)

            card.append(info_box)
            self.box.append(card)

            stats_lbl = Gtk.Label(label=f"Repositories: {profile.get('public_repos', 0)} public", xalign=0)
            stats_lbl.add_css_class("dim-label")
            self.box.append(stats_lbl)

            # Logout button
            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            btn_box.set_halign(Gtk.Align.END)
            btn_box.set_margin_top(16)

            logout_btn = Gtk.Button(label="Sign Out")
            logout_btn.add_css_class("destructive-action")
            logout_btn.connect("clicked", self._on_logout)
            btn_box.append(logout_btn)

            close_btn = Gtk.Button(label="Done")
            close_btn.connect("clicked", lambda _: self.close())
            btn_box.append(close_btn)

            self.box.append(btn_box)
        else:
            # Login Form
            title_lbl = Gtk.Label(label="Sign in to GitHub.com", xalign=0)
            title_lbl.add_css_class("title-2")
            self.box.append(title_lbl)

            desc = Gtk.Label(
                label="Sign in with your GitHub Personal Access Token (PAT) to clone and manage your repositories.",
                wrap=True,
                xalign=0
            )
            desc.add_css_class("dim-label")
            self.box.append(desc)

            self.token_entry = Adw.PasswordEntryRow()
            self.token_entry.set_title("Personal Access Token")
            self.token_entry.connect("entry-activated", self._on_sign_in)
            pref_group = Adw.PreferencesGroup()
            pref_group.add(self.token_entry)
            self.box.append(pref_group)

            if error_text:
                err_lbl = Gtk.Label(label=error_text, xalign=0, wrap=True)
                err_lbl.add_css_class("error")
                self.box.append(err_lbl)

            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            btn_box.set_halign(Gtk.Align.END)
            btn_box.set_margin_top(12)

            cancel_btn = Gtk.Button(label="Cancel")
            cancel_btn.connect("clicked", lambda _: self.close())
            btn_box.append(cancel_btn)

            self.sign_in_btn = Gtk.Button(label="Sign In")
            self.sign_in_btn.add_css_class("suggested-action")
            self.sign_in_btn.connect("clicked", self._on_sign_in)
            btn_box.append(self.sign_in_btn)

            self.box.append(btn_box)

    def _on_sign_in(self, _widget):
        token = self.token_entry.get_text().strip()
        if not token:
            return
        self.sign_in_btn.set_sensitive(False)

        # Validate the token against the API before saving it
        def _worker():
            profile = self.gh_service.get_user_profile(token=token)

            def _done():
                if profile:
                    self.gh_service.set_token(token)
                    if self.on_change_callback:
                        self.on_change_callback()
                    self._render_content(profile)
                else:
                    self._render_content(None, "Token geçersiz veya GitHub'a ulaşılamadı.")

            GLib.idle_add(_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_logout(self, _btn):
        self.gh_service.logout()
        if self.on_change_callback:
            self.on_change_callback()
        self._refresh_content()


# ==================== REPOSITORY MANAGER DIALOG ====================
class RepositoryManagerDialog(Adw.Window):
    def __init__(self, parent_window, gh_service, on_select_repo_callback):
        super().__init__(transient_for=parent_window, modal=True)
        self.set_title("Manage Repositories")
        self.set_default_size(680, 500)
        self.gh_service = gh_service
        self.on_select_repo_callback = on_select_repo_callback
        self.remote_repos = []

        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_box)

        # Tab View Switcher
        switcher_bar = Adw.HeaderBar()
        self.view_stack = Adw.ViewStack()

        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self.view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        switcher_bar.set_title_widget(switcher)
        root_box.append(switcher_bar)

        # 1. Page: Local / Recent Repositories
        self._build_recent_tab()

        # 2. Page: GitHub.com Repositories (Clone)
        self._build_github_tab()

        # 3. Page: Create New Repository
        self._build_create_tab()

        root_box.append(self.view_stack)

    def _build_recent_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_margin_start(16)
        page.set_margin_end(16)
        page.set_margin_top(12)
        page.set_margin_bottom(12)

        # Header with Search + Add local folder button
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.recent_search = Gtk.SearchEntry()
        self.recent_search.set_hexpand(True)
        self.recent_search.set_placeholder_text("Filter local repositories...")
        self.recent_search.connect("search-changed", self._on_recent_filter)
        top_bar.append(self.recent_search)

        btn_add_local = Gtk.Button(label="Add Existing...")
        btn_add_local.set_icon_name("folder-open-symbolic")
        btn_add_local.connect("clicked", self._on_browse_existing_repo)
        top_bar.append(btn_add_local)

        page.append(top_bar)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.recent_listbox = Gtk.ListBox()
        self.recent_listbox.add_css_class("boxed-list")
        self.recent_listbox.connect("row-selected", self._on_recent_repo_selected)
        scrolled.set_child(self.recent_listbox)
        page.append(scrolled)

        self._populate_recent_list()
        self.view_stack.add_titled_with_icon(page, "recent", "Local", "folder-symbolic")

    def _populate_recent_list(self, filter_text=""):
        while row := self.recent_listbox.get_first_child():
            self.recent_listbox.remove(row)

        repos = self.gh_service.get_recent_repos()
        filter_text = filter_text.lower()
        for r in repos:
            if filter_text and filter_text not in r["name"].lower() and filter_text not in r["path"].lower():
                continue
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_start(12)
            box.set_margin_end(12)
            box.set_margin_top(8)
            box.set_margin_bottom(8)

            icon = Gtk.Image(icon_name="folder-symbolic")
            box.append(icon)

            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            name_lbl = Gtk.Label(label=r["name"], xalign=0)
            name_lbl.add_css_class("heading")
            text_box.append(name_lbl)

            path_lbl = Gtk.Label(label=r["path"], xalign=0)
            path_lbl.add_css_class("dim-label")
            path_lbl.add_css_class("caption")
            text_box.append(path_lbl)
            text_box.set_hexpand(True)
            box.append(text_box)

            remove_btn = Gtk.Button(icon_name="edit-delete-symbolic")
            remove_btn.add_css_class("flat")
            remove_btn.set_tooltip_text("Remove from recent list")
            remove_btn.connect("clicked", self._on_remove_recent, r["path"])
            box.append(remove_btn)

            row.set_child(box)
            row.repo_path = r["path"]
            self.recent_listbox.append(row)

    def _on_recent_filter(self, entry):
        self._populate_recent_list(entry.get_text())

    def _on_remove_recent(self, _btn, path):
        self.gh_service.remove_recent_repo(path)
        self._populate_recent_list(self.recent_search.get_text())

    def _on_recent_repo_selected(self, _listbox, row):
        if row and hasattr(row, 'repo_path'):
            self.on_select_repo_callback(row.repo_path)
            self.close()

    def _on_browse_existing_repo(self, _btn):
        file_dialog = Gtk.FileDialog()
        file_dialog.set_title("Select Existing Git Repository")

        def _on_folder(dialog, res):
            try:
                folder = dialog.select_folder_finish(res)
                if folder:
                    path = folder.get_path()
                    if os.path.exists(os.path.join(path, ".git")):
                        self.gh_service.add_recent_repo(path)
                        self.on_select_repo_callback(path)
                        self.close()
            except Exception:
                pass
        file_dialog.select_folder(self, None, _on_folder)

    # ---------------- TAB 2: GITHUB.COM REPOSITORIES ----------------
    def _build_github_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_margin_start(16)
        page.set_margin_end(16)
        page.set_margin_top(12)
        page.set_margin_bottom(12)

        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.gh_search = Gtk.SearchEntry()
        self.gh_search.set_hexpand(True)
        self.gh_search.set_placeholder_text("Search GitHub repositories to clone...")
        self.gh_search.connect("search-changed", self._on_gh_filter)
        top_bar.append(self.gh_search)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh GitHub Repositories")
        refresh_btn.connect("clicked", lambda _: self._load_github_repos())
        top_bar.append(refresh_btn)
        page.append(top_bar)

        self.gh_spinner = Gtk.Spinner()
        page.append(self.gh_spinner)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.gh_listbox = Gtk.ListBox()
        self.gh_listbox.add_css_class("boxed-list")
        scrolled.set_child(self.gh_listbox)
        page.append(scrolled)

        self.view_stack.add_titled_with_icon(page, "github", "GitHub.com", "network-server-symbolic")
        # Auto load repos on thread
        self._load_github_repos()

    def _load_github_repos(self):
        self.gh_spinner.start()

        def _worker():
            repos = self.gh_service.get_user_repos(100)

            def _done():
                self.gh_spinner.stop()
                self.remote_repos = repos
                self._populate_gh_list()

            GLib.idle_add(_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _populate_gh_list(self, filter_text=""):
        while row := self.gh_listbox.get_first_child():
            self.gh_listbox.remove(row)

        filter_text = filter_text.lower()
        for r in self.remote_repos:
            if filter_text and filter_text not in r["name"].lower() and filter_text not in r["description"].lower():
                continue

            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_start(12)
            box.set_margin_end(12)
            box.set_margin_top(8)
            box.set_margin_bottom(8)

            icon_name = "channel-secure-symbolic" if r["is_private"] else "network-workgroup-symbolic"
            icon = Gtk.Image(icon_name=icon_name)
            box.append(icon)

            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            name_lbl = Gtk.Label(label=r["name"], xalign=0)
            name_lbl.add_css_class("heading")
            text_box.append(name_lbl)

            if r["description"]:
                desc_lbl = Gtk.Label(label=r["description"], xalign=0)
                desc_lbl.add_css_class("dim-label")
                desc_lbl.add_css_class("caption")
                desc_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                text_box.append(desc_lbl)

            text_box.set_hexpand(True)
            box.append(text_box)

            clone_btn = Gtk.Button(label="Clone")
            clone_btn.add_css_class("suggested-action")
            clone_btn.connect("clicked", self._on_clone_repo_clicked, r)
            box.append(clone_btn)

            row.set_child(box)
            self.gh_listbox.append(row)

    def _on_gh_filter(self, entry):
        self._populate_gh_list(entry.get_text())

    def _on_clone_repo_clicked(self, _btn, repo_info):
        file_dialog = Gtk.FileDialog()
        file_dialog.set_title(f"Choose Parent Directory to Clone '{repo_info['name']}' into")

        def _on_dest(dialog, res):
            try:
                parent_folder = dialog.select_folder_finish(res)
                if parent_folder:
                    parent_path = parent_folder.get_path()
                    target_dir = os.path.join(parent_path, repo_info["name"])

                    # Show cloning status dialog
                    clone_url = repo_info["clone_url"]
                    self._execute_clone(clone_url, target_dir)
            except Exception:
                pass
        file_dialog.select_folder(self, None, _on_dest)

    def _execute_clone(self, clone_url, target_dir):
        def _worker():
            ok, msg = self.gh_service.clone_repo(clone_url, target_dir)

            def _done():
                if ok:
                    self.gh_service.add_recent_repo(target_dir)
                    self.on_select_repo_callback(target_dir)
                    self.close()
                else:
                    self._show_alert("Clone Failed", msg)

            GLib.idle_add(_done)

        threading.Thread(target=_worker, daemon=True).start()

    # ---------------- TAB 3: CREATE NEW REPOSITORY ----------------
    def _build_create_tab(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.set_margin_start(24)
        page.set_margin_end(24)
        page.set_margin_top(16)
        page.set_margin_bottom(16)

        title = Gtk.Label(label="Create a New Repository", xalign=0)
        title.add_css_class("title-2")
        page.append(title)

        pref_group = Adw.PreferencesGroup()

        self.new_name_row = Adw.EntryRow()
        self.new_name_row.set_title("Repository Name")
        pref_group.add(self.new_name_row)

        self.new_path_row = Adw.ActionRow()
        self.new_path_row.set_title("Local Path")
        # Created on demand by init_new_repo, not just by opening this dialog
        default_dir = os.path.expanduser("~/Git")
        self.chosen_path = default_dir
        self.new_path_row.set_subtitle(self.chosen_path)

        browse_btn = Gtk.Button(label="Browse...")
        browse_btn.connect("clicked", self._on_browse_create_path)
        self.new_path_row.add_suffix(browse_btn)
        pref_group.add(self.new_path_row)

        self.readme_check = Adw.SwitchRow()
        self.readme_check.set_title("Initialize repository with a README")
        self.readme_check.set_active(True)
        pref_group.add(self.readme_check)

        page.append(pref_group)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(12)

        create_btn = Gtk.Button(label="Create Repository")
        create_btn.add_css_class("suggested-action")
        create_btn.connect("clicked", self._on_create_repo)
        btn_box.append(create_btn)
        page.append(btn_box)

        self.view_stack.add_titled_with_icon(page, "create", "Create New", "list-add-symbolic")

    def _on_browse_create_path(self, _btn):
        file_dialog = Gtk.FileDialog()
        file_dialog.set_title("Select Parent Directory for New Repository")

        def _on_path(dialog, res):
            try:
                folder = dialog.select_folder_finish(res)
                if folder:
                    self.chosen_path = folder.get_path()
                    self.new_path_row.set_subtitle(self.chosen_path)
            except Exception:
                pass
        file_dialog.select_folder(self, None, _on_path)

    def _on_create_repo(self, _btn):
        name = self.new_name_row.get_text().strip()
        if not name:
            self._show_alert("Missing Name", "Please provide a repository name.")
            return

        ok, result = self.gh_service.init_new_repo(
            self.chosen_path,
            name,
            init_readme=self.readme_check.get_active()
        )
        if ok:
            self.on_select_repo_callback(result)
            self.close()
        else:
            self._show_alert("Creation Failed", result)

    def _show_alert(self, title, message):
        dialog = Adw.MessageDialog(transient_for=self, heading=title, body=message or "Error")
        dialog.add_response("ok", "OK")
        dialog.present()


# ==================== NEW BRANCH DIALOG ====================
class NewBranchDialog(Adw.Window):
    def __init__(self, parent_window, current_branch, on_create_callback=None):
        super().__init__(transient_for=parent_window, modal=True)
        self.set_title("Create a Branch")
        self.set_default_size(400, 240)
        self.on_create_callback = on_create_callback

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(20)
        box.set_margin_bottom(20)

        title_lbl = Gtk.Label(label="Create a new branch", xalign=0)
        title_lbl.add_css_class("title-2")
        box.append(title_lbl)

        desc_lbl = Gtk.Label(
            label=f"Your new branch will be based on your currently checked out branch (<b>{GLib.markup_escape_text(current_branch)}</b>).",
            use_markup=True,
            xalign=0,
            wrap=True
        )
        desc_lbl.add_css_class("dim-label")
        box.append(desc_lbl)

        self.branch_entry = Gtk.Entry()
        self.branch_entry.set_placeholder_text("Name (e.g. feature/my-cool-feature)")
        self.branch_entry.connect("activate", self._on_create)
        box.append(self.branch_entry)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(12)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        create_btn = Gtk.Button(label="Create Branch")
        create_btn.add_css_class("suggested-action")
        create_btn.connect("clicked", self._on_create)
        btn_box.append(create_btn)

        box.append(btn_box)
        self.set_content(box)

    def _on_create(self, _widget):
        name = self.branch_entry.get_text().strip()
        if name and self.on_create_callback:
            self.on_create_callback(name)
            self.close()
