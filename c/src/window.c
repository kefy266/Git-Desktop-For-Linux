#include "window.h"

#include "dialogs.h"
#include "diffview.h"
#include "icons.h"
#include "net.h"
#include "settings.h"
#include "util.h"

#include <string.h>

#define HISTORY_PAGE 100
#define AUTO_FETCH_SECONDS (30 * 60)

struct _GdlWindow {
  AdwApplicationWindow parent_instance;

  GdlRepo    *repo;
  GPtrArray  *files;          /* GdlFile*, current working-tree changes */
  GHashTable *unchecked;      /* paths the user unticked (everything else is included) */
  gboolean    syncing_checks;
  gboolean    busy;           /* a network operation is running */
  gint64      last_refresh;
  char       *head_hash;
  char       *undo_hash;      /* HEAD right after a commit made here */
  char       *undo_summary;
  char       *undo_description;
  guint       history_count;
  gboolean    history_done;
  char       *sync_mode;      /* fetch | pull | push | publish | none */
  guint       fetch_timer;

  GdlAccount *account;        /* NULL while loading */
  gboolean    account_loading;
  GdkTexture *avatar;

  /* toolbar */
  AdwToastOverlay *toasts;
  GtkWidget  *repo_button, *repo_title;
  GtkWidget  *branch_button, *branch_title;
  GtkWidget  *sync_button, *sync_icon, *sync_title, *sync_caption, *sync_spinner;
  GtkWidget  *profile_button, *profile_avatar, *account_box;

  /* popovers */
  GtkWidget  *repo_search, *repo_list;
  GtkWidget  *branch_search, *branch_list;

  /* sidebar */
  AdwToggleGroup *tabs;
  GtkWidget  *side_stack;
  GtkWidget  *select_all, *files_count, *files_list, *files_stack;
  GtkWidget  *history_scroller, *history_list;
  GtkWidget  *merge_banner, *merge_label;
  GtkWidget  *stash_banner;
  GtkWidget  *undo_banner, *undo_label;
  GtkWidget  *author_avatar, *summary_entry, *description_view, *commit_button;

  /* main area */
  GtkWidget  *main_stack;
  GdlDiffView *diff;
  GtkWidget  *blank;
  GtkWidget  *commit_avatar, *commit_title, *commit_body, *commit_meta, *commit_count, *commit_files;
  GdlDiffView *commit_diff;
  char       *shown_commit;
};

G_DEFINE_FINAL_TYPE (GdlWindow, gdl_window, ADW_TYPE_APPLICATION_WINDOW)

static void refresh_files (GdlWindow *self);
static void show_selected_change (GdlWindow *self);
static void show_commit (GdlWindow *self, const char *hash);
static void run_sync (GdlWindow *self, const char *mode, gboolean quiet);
static void apply_account (GdlWindow *self, GdlAccount *account);

/* Actions that only make sense with an open repository */
static const char *const REPO_ACTIONS[] = {
  "show-changes", "show-history", "branch-list", "new-branch", "rename-branch", "delete-branch", "merge",
  "abort-merge", "stash", "restore-stash", "discard-stash", "discard-all", "commit", "undo-commit", "push",
  "pull", "fetch", "sync", "remove-repo", "open-editor", "open-terminal", "file-manager", NULL,
};

/* ================================================================== */
/* Small helpers                                                       */
/* ================================================================== */

GdlRepo *
gdl_window_get_repo (GdlWindow *self)
{
  return self->repo;
}

GdlAccount *
gdl_window_get_account (GdlWindow *self)
{
  return self->account;
}

const char *
gdl_window_get_token (GdlWindow *self)
{
  return self->account ? self->account->token : NULL;
}

void
gdl_window_toast (GdlWindow *self, const char *message)
{
  adw_toast_overlay_add_toast (self->toasts, adw_toast_new (message));
}

void
gdl_window_error (GdlWindow *self, const char *title, const char *message)
{
  AdwDialog *d = adw_alert_dialog_new (title, message && *message ? message : "An unknown error occurred.");
  adw_alert_dialog_add_response (ADW_ALERT_DIALOG (d), "ok", "OK");
  adw_dialog_present (d, GTK_WIDGET (self));
}

static void
set_action_enabled (GdlWindow *self, const char *name, gboolean enabled)
{
  GAction *a = g_action_map_lookup_action (G_ACTION_MAP (self), name);
  if (a)
    g_simple_action_set_enabled (G_SIMPLE_ACTION (a), enabled);
}

static void
clear_list (GtkWidget *list)
{
  GtkWidget *child;
  while ((child = gtk_widget_get_first_child (list)))
    gtk_list_box_remove (GTK_LIST_BOX (list), child);
}

static GtkWidget *
label_new (const char *text, const char *css, float xalign)
{
  GtkWidget *l = gtk_label_new (text);
  gtk_label_set_xalign (GTK_LABEL (l), xalign);
  if (css)
    gtk_widget_add_css_class (l, css);
  return l;
}

/* Two-line toolbar content: icon · caption over title · optional chevron */
static GtkWidget *
toolbar_content (const char *icon, const char *caption, gboolean chevron,
                 GtkWidget **icon_out, GtkWidget **title_out, GtkWidget **caption_out)
{
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 10);
  GtkWidget *ic = gdl_icon_new (icon, 18);
  gtk_box_append (GTK_BOX (box), ic);
  GtkWidget *texts = gtk_box_new (GTK_ORIENTATION_VERTICAL, 0);
  gtk_widget_set_valign (texts, GTK_ALIGN_CENTER);
  GtkWidget *cap = label_new (caption, "caption-label", 0);
  GtkWidget *title = label_new ("", "title-label", 0);
  gtk_label_set_ellipsize (GTK_LABEL (title), PANGO_ELLIPSIZE_END);
  gtk_label_set_max_width_chars (GTK_LABEL (title), 22);
  gtk_label_set_ellipsize (GTK_LABEL (cap), PANGO_ELLIPSIZE_END);
  gtk_label_set_max_width_chars (GTK_LABEL (cap), 26);
  gtk_box_append (GTK_BOX (texts), cap);
  gtk_box_append (GTK_BOX (texts), title);
  gtk_box_append (GTK_BOX (box), texts);
  if (chevron) {
    GtkWidget *ch = gdl_icon_new ("chevron-down", 14);
    gtk_widget_add_css_class (ch, "dim-label");
    gtk_widget_set_margin_start (ch, 6);
    gtk_box_append (GTK_BOX (box), ch);
  }
  if (icon_out) *icon_out = ic;
  if (title_out) *title_out = title;
  if (caption_out) *caption_out = cap;
  return box;
}

/* ================================================================== */
/* Filterable popovers (repositories, branches)                        */
/* ================================================================== */

static GtkWidget *
section_row (const char *title)
{
  GtkWidget *row = gtk_list_box_row_new ();
  gtk_list_box_row_set_activatable (GTK_LIST_BOX_ROW (row), FALSE);
  gtk_list_box_row_set_selectable (GTK_LIST_BOX_ROW (row), FALSE);
  g_autofree char *upper = g_ascii_strup (title, -1);
  GtkWidget *l = label_new (upper, "section-label", 0);
  gtk_widget_add_css_class (row, "section-row");
  gtk_list_box_row_set_child (GTK_LIST_BOX_ROW (row), l);
  g_object_set_data (G_OBJECT (row), "kind", (gpointer) "section");
  return row;
}

static GtkWidget *
entry_row (const char *icon, const char *text, const char *value, const char *kind, gboolean bold, const char *tooltip)
{
  GtkWidget *row = gtk_list_box_row_new ();
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 10);
  GtkWidget *ic = gdl_icon_new (icon, 16);
  if (bold)
    gtk_widget_add_css_class (ic, "accent");
  else
    gtk_widget_add_css_class (ic, "dim-label");
  gtk_box_append (GTK_BOX (box), ic);
  GtkWidget *l = label_new (text, bold ? "heading" : NULL, 0);
  gtk_label_set_ellipsize (GTK_LABEL (l), PANGO_ELLIPSIZE_END);
  gtk_box_append (GTK_BOX (box), l);
  gtk_list_box_row_set_child (GTK_LIST_BOX_ROW (row), box);
  g_object_set_data_full (G_OBJECT (row), "value", g_strdup (value), g_free);
  g_object_set_data_full (G_OBJECT (row), "text", g_utf8_casefold (text, -1), g_free);
  g_object_set_data (G_OBJECT (row), "kind", (gpointer) kind);
  if (tooltip)
    gtk_widget_set_tooltip_text (row, tooltip);
  return row;
}

/* Hides rows that don't match; hides a section header when nothing below it matches */
static void
filter_list (GtkWidget *list, const char *query)
{
  g_autofree char *q = g_utf8_casefold (query ? query : "", -1);
  GtkWidget *section = NULL;
  gboolean section_match = FALSE;
  for (GtkWidget *row = gtk_widget_get_first_child (list); row; row = gtk_widget_get_next_sibling (row)) {
    const char *kind = g_object_get_data (G_OBJECT (row), "kind");
    if (kind && g_str_equal (kind, "section")) {
      if (section)
        gtk_widget_set_visible (section, section_match);
      section = row;
      section_match = FALSE;
      continue;
    }
    const char *text = g_object_get_data (G_OBJECT (row), "text");
    gboolean match = !*q || (text && strstr (text, q));
    gtk_widget_set_visible (row, match);
    section_match |= match;
  }
  if (section)
    gtk_widget_set_visible (section, section_match);
}

static GtkListBoxRow *
first_visible_row (GtkWidget *list)
{
  for (GtkWidget *row = gtk_widget_get_first_child (list); row; row = gtk_widget_get_next_sibling (row))
    if (gtk_widget_get_visible (row) && gtk_list_box_row_get_activatable (GTK_LIST_BOX_ROW (row)))
      return GTK_LIST_BOX_ROW (row);
  return NULL;
}

static GtkWidget *
filter_popover (const char *placeholder, GtkWidget *extra, GtkWidget **search_out, GtkWidget **list_out)
{
  GtkWidget *popover = gtk_popover_new ();
  gtk_widget_add_css_class (popover, "gdl-popover");
  gtk_popover_set_has_arrow (GTK_POPOVER (popover), FALSE);
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_VERTICAL, 6);
  gtk_widget_set_size_request (box, 360, 440);
  GtkWidget *top = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 6);
  gtk_widget_set_margin_start (top, 8);
  gtk_widget_set_margin_end (top, 8);
  gtk_widget_set_margin_top (top, 8);
  GtkWidget *search = gtk_search_entry_new ();
  gtk_search_entry_set_placeholder_text (GTK_SEARCH_ENTRY (search), placeholder);
  gtk_widget_set_hexpand (search, TRUE);
  gtk_box_append (GTK_BOX (top), search);
  if (extra)
    gtk_box_append (GTK_BOX (top), extra);
  gtk_box_append (GTK_BOX (box), top);
  GtkWidget *scroll = gtk_scrolled_window_new ();
  gtk_scrolled_window_set_policy (GTK_SCROLLED_WINDOW (scroll), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
  gtk_widget_set_vexpand (scroll, TRUE);
  GtkWidget *list = gtk_list_box_new ();
  gtk_list_box_set_selection_mode (GTK_LIST_BOX (list), GTK_SELECTION_NONE);
  gtk_widget_set_margin_bottom (list, 6);
  gtk_scrolled_window_set_child (GTK_SCROLLED_WINDOW (scroll), list);
  gtk_box_append (GTK_BOX (box), scroll);
  gtk_popover_set_child (GTK_POPOVER (popover), box);
  /* the search box keeps focus; Enter picks the first match */
  gtk_search_entry_set_key_capture_widget (GTK_SEARCH_ENTRY (search), box);
  *search_out = search;
  *list_out = list;
  return popover;
}

static void
on_filter_changed (GtkSearchEntry *entry, GtkWidget *list)
{
  filter_list (list, gtk_editable_get_text (GTK_EDITABLE (entry)));
}

static void
on_filter_activate (GtkSearchEntry *entry, GtkWidget *list)
{
  GtkListBoxRow *row = first_visible_row (list);
  if (row)
    g_signal_emit_by_name (list, "row-activated", row);
}

/* ---------------- repository popover ---------------- */

static GHashTable *
local_slugs (GPtrArray *recent)
{
  /* "owner/name" of recent repositories whose origin is on github.com */
  GHashTable *set = g_hash_table_new_full (g_str_hash, g_str_equal, g_free, NULL);
  for (guint i = 0; i < recent->len; i++) {
    g_autoptr (GdlRepo) r = gdl_repo_open (g_ptr_array_index (recent, i), NULL);
    if (!r)
      continue;
    g_autofree char *url = gdl_repo_remote_url (r, "origin");
    g_autofree char *slug = gdl_github_slug (url);
    if (slug)
      g_hash_table_add (set, g_utf8_casefold (slug, -1));
  }
  return set;
}

/* Shallow copy for sorting: must not inherit the source's free function */
static GPtrArray *
borrowed_copy (GPtrArray *src)
{
  GPtrArray *copy = g_ptr_array_copy (src, NULL, NULL);
  g_ptr_array_set_free_func (copy, NULL);
  return copy;
}

static gint
compare_owner (gconstpointer a, gconstpointer b, gpointer me)
{
  const GdlGhRepo *ra = *(GdlGhRepo **) a, *rb = *(GdlGhRepo **) b;
  gboolean ma = me && g_ascii_strcasecmp (ra->owner, me) == 0;
  gboolean mb = me && g_ascii_strcasecmp (rb->owner, me) == 0;
  if (ma != mb)
    return ma ? -1 : 1;
  return g_ascii_strcasecmp (ra->owner, rb->owner);
}

static void
fill_repo_popover (GdlWindow *self)
{
  clear_list (self->repo_list);
  g_autoptr (GPtrArray) recent = settings_recent ();
  gtk_list_box_append (GTK_LIST_BOX (self->repo_list), section_row ("Recent"));
  for (guint i = 0; i < recent->len; i++) {
    const char *path = g_ptr_array_index (recent, i);
    g_autofree char *name = g_path_get_basename (path);
    gboolean current = self->repo && g_str_equal (path, gdl_repo_path (self->repo));
    gtk_list_box_append (GTK_LIST_BOX (self->repo_list), entry_row ("repo", name, path, "repo", current, path));
  }
  if (!recent->len) {
    GtkWidget *row = entry_row ("plus", "No repositories yet — use Add", "", "none", FALSE, NULL);
    gtk_list_box_row_set_activatable (GTK_LIST_BOX_ROW (row), FALSE);
    gtk_list_box_append (GTK_LIST_BOX (self->repo_list), row);
  }

  /* every repository of the GitHub account, grouped by owner; skip ones already on disk */
  if (!self->account || !self->account->profile) {
    gtk_list_box_append (GTK_LIST_BOX (self->repo_list), section_row ("GitHub.com"));
    if (self->account_loading) {
      GtkWidget *row = entry_row ("sync", "Loading your GitHub repositories…", "", "none", FALSE, NULL);
      gtk_list_box_row_set_activatable (GTK_LIST_BOX_ROW (row), FALSE);
      gtk_list_box_append (GTK_LIST_BOX (self->repo_list), row);
    } else {
      gtk_list_box_append (GTK_LIST_BOX (self->repo_list),
                           entry_row ("user", "Sign in to see your GitHub repositories…", "", "signin", FALSE, NULL));
    }
  } else if (self->account->repos) {
    g_autoptr (GHashTable) local = local_slugs (recent);
    g_autoptr (GPtrArray) sorted = borrowed_copy (self->account->repos);
    g_ptr_array_sort_with_data (sorted, compare_owner, self->account->profile->login);
    const char *owner = NULL;
    for (guint i = 0; i < sorted->len; i++) {
      GdlGhRepo *r = g_ptr_array_index (sorted, i);
      g_autofree char *key = g_utf8_casefold (r->full_name, -1);
      if (g_hash_table_contains (local, key))
        continue;
      if (!owner || g_ascii_strcasecmp (owner, r->owner) != 0) {
        owner = r->owner;
        g_autofree char *title = g_strdup_printf ("GitHub.com · %s", owner);
        gtk_list_box_append (GTK_LIST_BOX (self->repo_list), section_row (title));
      }
      g_autofree char *tip = g_strdup_printf ("%s\n%s\nClick to clone", r->full_name, r->description);
      gtk_list_box_append (GTK_LIST_BOX (self->repo_list),
                           entry_row (r->is_private ? "lock" : "cloud-down", r->name, r->full_name, "github", FALSE, tip));
    }
  }
  filter_list (self->repo_list, gtk_editable_get_text (GTK_EDITABLE (self->repo_search)));
}

static void
on_repo_row_activated (GtkListBox *list, GtkListBoxRow *row, GdlWindow *self)
{
  const char *kind = g_object_get_data (G_OBJECT (row), "kind");
  const char *value = g_object_get_data (G_OBJECT (row), "value");
  if (!kind)
    return;
  gtk_menu_button_popdown (GTK_MENU_BUTTON (self->repo_button));
  if (g_str_equal (kind, "repo"))
    gdl_window_open_repository (self, value);
  else if (g_str_equal (kind, "github"))
    gdl_clone_dialog_show (self, value);
  else if (g_str_equal (kind, "signin"))
    gdl_sign_in_dialog_show (self);
}

/* ---------------- branch popover ---------------- */

static void
fill_branch_popover (GdlWindow *self)
{
  clear_list (self->branch_list);
  if (!self->repo)
    return;
  g_autofree char *current = gdl_repo_branch (self->repo);
  g_autoptr (GPtrArray) local = gdl_repo_branches (self->repo, FALSE);
  g_autoptr (GPtrArray) remote = gdl_repo_branches (self->repo, TRUE);
  gtk_list_box_append (GTK_LIST_BOX (self->branch_list), section_row ("Local branches"));
  if (!local->len) {  /* unborn branch: show it anyway */
    GtkWidget *row = entry_row ("check", current, current, "local", TRUE, NULL);
    gtk_list_box_append (GTK_LIST_BOX (self->branch_list), row);
  }
  g_autoptr (GHashTable) locals = g_hash_table_new (g_str_hash, g_str_equal);
  for (guint i = 0; i < local->len; i++) {
    const char *b = g_ptr_array_index (local, i);
    g_hash_table_add (locals, (gpointer) b);
    gboolean is_current = g_str_equal (b, current);
    gtk_list_box_append (GTK_LIST_BOX (self->branch_list),
                         entry_row (is_current ? "check" : "branch", b, b, "local", is_current, NULL));
  }
  gboolean header = FALSE;
  for (guint i = 0; i < remote->len; i++) {
    const char *r = g_ptr_array_index (remote, i);
    const char *slash = strchr (r, '/');
    if (slash && g_hash_table_contains (locals, slash + 1))
      continue;  /* already checked out locally */
    if (!header) {
      gtk_list_box_append (GTK_LIST_BOX (self->branch_list), section_row ("Remote branches"));
      header = TRUE;
    }
    gtk_list_box_append (GTK_LIST_BOX (self->branch_list), entry_row ("cloud-down", r, r, "remote", FALSE, NULL));
  }
  filter_list (self->branch_list, gtk_editable_get_text (GTK_EDITABLE (self->branch_search)));
}

typedef struct {
  GdlWindow *self;
  char      *name;
  gboolean   remote;
} SwitchJob;

static void
switch_job_free (gpointer data, GClosure *closure)
{
  SwitchJob *job = data;
  g_free (job->name);
  g_free (job);
}

static void
do_switch (GdlWindow *self, const char *name, gboolean remote)
{
  g_autoptr (GError) error = NULL;
  gboolean ok = remote ? gdl_repo_checkout_remote (self->repo, name, &error)
                       : gdl_repo_checkout_branch (self->repo, name, &error);
  if (!ok)
    gdl_window_error (self, "Could not switch branch", error->message);
  g_clear_pointer (&self->undo_hash, g_free);
  gdl_window_refresh (self, TRUE);
}

static void
on_switch_response (AdwAlertDialog *dialog, const char *response, SwitchJob *job)
{
  GdlWindow *self = job->self;
  if (g_str_equal (response, "leave")) {
    g_autoptr (GError) error = NULL;
    if (!gdl_repo_stash_all (self->repo, &error)) {
      gdl_window_error (self, "Could not stash your changes", error->message);
      return;
    }
    do_switch (self, job->name, job->remote);
  } else if (g_str_equal (response, "bring")) {
    do_switch (self, job->name, job->remote);
  }
}

/* GitHub Desktop asks what to do with uncommitted changes before switching */
static void
switch_branch (GdlWindow *self, const char *name, gboolean remote)
{
  g_autofree char *current = gdl_repo_branch (self->repo);
  if (!remote && g_str_equal (name, current))
    return;
  if (!self->files || !self->files->len) {
    do_switch (self, name, remote);
    return;
  }
  const char *target = remote && strchr (name, '/') ? strchr (name, '/') + 1 : name;
  g_autofree char *body = g_strdup_printf ("You have changes on “%s”. What would you like to do with them?", current);
  AdwDialog *d = adw_alert_dialog_new ("Switch branch", body);
  g_autofree char *leave = g_strdup_printf ("Leave my changes on %s", current);
  g_autofree char *bring = g_strdup_printf ("Bring my changes to %s", target);
  adw_alert_dialog_add_responses (ADW_ALERT_DIALOG (d), "cancel", "Cancel", "bring", bring, "leave", leave, NULL);
  adw_alert_dialog_set_response_appearance (ADW_ALERT_DIALOG (d), "leave", ADW_RESPONSE_SUGGESTED);
  adw_alert_dialog_set_prefer_wide_layout (ADW_ALERT_DIALOG (d), TRUE);
  SwitchJob *job = g_new0 (SwitchJob, 1);
  job->self = self;
  job->name = g_strdup (name);
  job->remote = remote;
  g_signal_connect_data (d, "response", G_CALLBACK (on_switch_response), job, switch_job_free, 0);
  adw_dialog_present (d, GTK_WIDGET (self));
}

static void
on_branch_row_activated (GtkListBox *list, GtkListBoxRow *row, GdlWindow *self)
{
  const char *kind = g_object_get_data (G_OBJECT (row), "kind");
  const char *value = g_object_get_data (G_OBJECT (row), "value");
  if (!kind || g_str_equal (kind, "section"))
    return;
  gtk_menu_button_popdown (GTK_MENU_BUTTON (self->branch_button));
  switch_branch (self, value, g_str_equal (kind, "remote"));
}

/* Right-click on a local branch: Rename / Delete */
static void
on_branch_right_click (GtkGestureClick *gesture, int n, double x, double y, GdlWindow *self)
{
  GtkListBoxRow *row = gtk_list_box_get_row_at_y (GTK_LIST_BOX (self->branch_list), (int) y);
  const char *kind = row ? g_object_get_data (G_OBJECT (row), "kind") : NULL;
  if (!kind || !g_str_equal (kind, "local"))
    return;
  const char *name = g_object_get_data (G_OBJECT (row), "value");
  g_autoptr (GMenu) menu = g_menu_new ();
  g_menu_append (menu, "Rename…", g_strdup_printf ("win.rename-branch-named('%s')", name));
  g_menu_append (menu, "Delete…", g_strdup_printf ("win.delete-branch-named('%s')", name));
  GtkWidget *pop = gtk_popover_menu_new_from_model (G_MENU_MODEL (menu));
  gtk_widget_set_parent (pop, GTK_WIDGET (row));
  gtk_popover_set_has_arrow (GTK_POPOVER (pop), FALSE);
  g_signal_connect (pop, "closed", G_CALLBACK (gtk_widget_unparent), NULL);
  gtk_popover_popup (GTK_POPOVER (pop));
}

/* ================================================================== */
/* Changes list                                                        */
/* ================================================================== */

static gboolean
is_checked (GdlWindow *self, const char *path)
{
  return !g_hash_table_contains (self->unchecked, path);
}

static guint
checked_count (GdlWindow *self)
{
  guint n = 0;
  for (guint i = 0; self->files && i < self->files->len; i++)
    if (is_checked (self, ((GdlFile *) g_ptr_array_index (self->files, i))->path))
      n++;
  return n;
}

static void
update_commit_button (GdlWindow *self)
{
  g_autofree char *branch = self->repo ? gdl_repo_branch (self->repo) : g_strdup ("branch");
  gboolean merging = self->repo && gdl_repo_is_merging (self->repo);
  g_autofree char *label = merging ? g_strdup ("Commit merge") : g_strdup_printf ("Commit to %s", branch);
  gtk_button_set_label (GTK_BUTTON (self->commit_button), label);
  const char *summary = gtk_editable_get_text (GTK_EDITABLE (self->summary_entry));
  g_autofree char *trimmed = g_strstrip (g_strdup (summary));
  gtk_widget_set_sensitive (self->commit_button, *trimmed && (checked_count (self) > 0 || merging));
}

static void
sync_select_all (GdlWindow *self)
{
  guint total = self->files ? self->files->len : 0, n = checked_count (self);
  self->syncing_checks = TRUE;
  gtk_check_button_set_inconsistent (GTK_CHECK_BUTTON (self->select_all), n > 0 && n < total);
  gtk_check_button_set_active (GTK_CHECK_BUTTON (self->select_all), total > 0 && n == total);
  self->syncing_checks = FALSE;
}

static void
on_file_check_toggled (GtkCheckButton *check, GdlWindow *self)
{
  if (self->syncing_checks)
    return;
  const char *path = g_object_get_data (G_OBJECT (check), "path");
  if (gtk_check_button_get_active (check))
    g_hash_table_remove (self->unchecked, path);
  else
    g_hash_table_add (self->unchecked, g_strdup (path));
  sync_select_all (self);
  update_commit_button (self);
}

static void
on_select_all_toggled (GtkCheckButton *check, GdlWindow *self)
{
  if (self->syncing_checks)
    return;
  /* partial or none -> check all; all -> uncheck all (GitHub Desktop behavior) */
  gboolean target = checked_count (self) < (self->files ? self->files->len : 0);
  g_hash_table_remove_all (self->unchecked);
  if (!target)
    for (guint i = 0; i < self->files->len; i++)
      g_hash_table_add (self->unchecked, g_strdup (((GdlFile *) g_ptr_array_index (self->files, i))->path));
  self->syncing_checks = TRUE;
  for (GtkWidget *row = gtk_widget_get_first_child (self->files_list); row; row = gtk_widget_get_next_sibling (row)) {
    GtkWidget *cb = g_object_get_data (G_OBJECT (row), "check");
    if (cb)
      gtk_check_button_set_active (GTK_CHECK_BUTTON (cb), target);
  }
  self->syncing_checks = FALSE;
  sync_select_all (self);
  update_commit_button (self);
}

static void
on_file_right_click (GtkGestureClick *gesture, int n, double x, double y, GdlWindow *self)
{
  GtkListBoxRow *row = gtk_list_box_get_row_at_y (GTK_LIST_BOX (self->files_list), (int) y);
  if (!row)
    return;
  GdlFile *f = g_object_get_data (G_OBJECT (row), "file");
  g_autoptr (GVariant) target = g_variant_ref_sink (g_variant_new_string (f->path));
  g_autoptr (GMenu) menu = g_menu_new ();
  g_autoptr (GMenu) s1 = g_menu_new (), s2 = g_menu_new (), s3 = g_menu_new ();
  /* every item targets this file's path */
  struct { GMenu *sec; const char *label; const char *action; } items[] = {
    { s1, "Discard changes…", "win.discard-file" },
    { s2, "Ignore file (add to .gitignore)", "win.ignore-file" },
    { s2, "Ignore all files with this extension", "win.ignore-ext" },
    { s3, "Copy file path", "win.copy-path" },
    { s3, "Copy relative file path", "win.copy-relpath" },
    { s3, "Show in file manager", "win.show-in-folder" },
    { s3, "Open in external editor", "win.open-file-editor" },
  };
  for (guint i = 0; i < G_N_ELEMENTS (items); i++) {
    if (items[i].sec == s2 && f->status != GDL_ST_NEW)
      continue;  /* ignoring only makes sense for new files */
    GMenuItem *it = g_menu_item_new (items[i].label, NULL);
    g_menu_item_set_action_and_target_value (it, items[i].action, target);
    g_menu_append_item (items[i].sec, it);
    g_object_unref (it);
  }
  g_menu_append_section (menu, NULL, G_MENU_MODEL (s1));
  if (g_menu_model_get_n_items (G_MENU_MODEL (s2)))
    g_menu_append_section (menu, NULL, G_MENU_MODEL (s2));
  g_menu_append_section (menu, NULL, G_MENU_MODEL (s3));

  GtkWidget *pop = gtk_popover_menu_new_from_model (G_MENU_MODEL (menu));
  gtk_widget_set_parent (pop, GTK_WIDGET (row));
  gtk_popover_set_has_arrow (GTK_POPOVER (pop), FALSE);
  graphene_point_t p;
  if (gtk_widget_compute_point (self->files_list, GTK_WIDGET (row), &GRAPHENE_POINT_INIT (x, y), &p))
    gtk_popover_set_pointing_to (GTK_POPOVER (pop), &(GdkRectangle) { (int) p.x, (int) p.y, 1, 1 });
  g_signal_connect (pop, "closed", G_CALLBACK (gtk_widget_unparent), NULL);
  gtk_popover_popup (GTK_POPOVER (pop));
}

static GtkWidget *
file_row (GdlWindow *self, GdlFile *f, gboolean checkable)
{
  GtkWidget *row = gtk_list_box_row_new ();
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 10);
  gtk_widget_add_css_class (box, "file-row");
  if (checkable) {
    GtkWidget *check = gtk_check_button_new ();
    gtk_check_button_set_active (GTK_CHECK_BUTTON (check), is_checked (self, f->path));
    g_object_set_data_full (G_OBJECT (check), "path", g_strdup (f->path), g_free);
    g_signal_connect (check, "toggled", G_CALLBACK (on_file_check_toggled), self);
    gtk_box_append (GTK_BOX (box), check);
    g_object_set_data (G_OBJECT (row), "check", check);
  } else {
    gtk_widget_set_margin_start (box, 8);
  }
  g_autofree char *dir = g_path_get_dirname (f->path);
  g_autofree char *base = g_path_get_basename (f->path);
  GtkWidget *name = label_new (base, "file-name", 0);
  gtk_label_set_ellipsize (GTK_LABEL (name), PANGO_ELLIPSIZE_MIDDLE);
  gtk_box_append (GTK_BOX (box), name);
  GtkWidget *folder = label_new (g_str_equal (dir, ".") ? "" : dir, "file-dir", 0);
  gtk_label_set_ellipsize (GTK_LABEL (folder), PANGO_ELLIPSIZE_START);
  gtk_widget_set_hexpand (folder, TRUE);
  gtk_box_append (GTK_BOX (box), folder);
  GtkWidget *badge = gdl_status_badge_new (f->status);
  gtk_widget_set_margin_end (badge, 4);
  gtk_box_append (GTK_BOX (box), badge);
  gtk_list_box_row_set_child (GTK_LIST_BOX_ROW (row), box);
  g_autofree char *tip = f->orig_path ? g_strdup_printf ("%s → %s\n%s", f->orig_path, f->path, gdl_status_label (f->status))
                                      : g_strdup_printf ("%s\n%s", f->path, gdl_status_label (f->status));
  gtk_widget_set_tooltip_text (row, tip);
  g_object_set_data (G_OBJECT (row), "file", f);
  return row;
}

static void
refresh_files (GdlWindow *self)
{
  g_autofree char *selected = NULL;
  GtkListBoxRow *sel = gtk_list_box_get_selected_row (GTK_LIST_BOX (self->files_list));
  if (sel)
    selected = g_strdup (((GdlFile *) g_object_get_data (G_OBJECT (sel), "file"))->path);

  g_autoptr (GError) error = NULL;
  GPtrArray *files = gdl_repo_status (self->repo, &error);
  if (!files)
    files = g_ptr_array_new_with_free_func ((GDestroyNotify) gdl_file_free);

  /* forget ticks of files that are gone */
  GHashTableIter it;
  gpointer key;
  g_hash_table_iter_init (&it, self->unchecked);
  while (g_hash_table_iter_next (&it, &key, NULL)) {
    gboolean present = FALSE;
    for (guint i = 0; i < files->len && !present; i++)
      present = g_str_equal (((GdlFile *) g_ptr_array_index (files, i))->path, key);
    if (!present)
      g_hash_table_iter_remove (&it);
  }

  clear_list (self->files_list);   /* rows point into the old array: clear first */
  g_clear_pointer (&self->files, g_ptr_array_unref);
  self->files = files;

  GtkListBoxRow *restore = NULL;
  for (guint i = 0; i < files->len; i++) {
    GdlFile *f = g_ptr_array_index (files, i);
    GtkWidget *row = file_row (self, f, TRUE);
    gtk_list_box_append (GTK_LIST_BOX (self->files_list), row);
    if (selected && g_str_equal (selected, f->path))
      restore = GTK_LIST_BOX_ROW (row);
  }
  g_autofree char *count = g_strdup_printf ("%u changed file%s", files->len, files->len == 1 ? "" : "s");
  gtk_label_set_text (GTK_LABEL (self->files_count), count);
  gtk_stack_set_visible_child_name (GTK_STACK (self->files_stack), files->len ? "list" : "empty");
  gtk_widget_set_sensitive (self->select_all, files->len > 0);
  sync_select_all (self);
  update_commit_button (self);
  if (!restore)
    restore = gtk_list_box_get_row_at_index (GTK_LIST_BOX (self->files_list), 0);
  if (restore)
    gtk_list_box_select_row (GTK_LIST_BOX (self->files_list), restore);
  else
    show_selected_change (self);
}

static GtkWidget *
clean_tree_actions (GdlWindow *self)
{
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_VERTICAL, 8);
  GdlSync s;
  gdl_repo_sync_status (self->repo, &s);
  if (s.ahead > 0) {
    g_autofree char *label = g_strdup_printf ("Push %d commit%s to origin", s.ahead, s.ahead > 1 ? "s" : "");
    gtk_box_append (GTK_BOX (box), gdl_action_card_new ("arrow-up", label, "Ctrl+P", "win.push"));
  }
  gdl_sync_clear (&s);
  gtk_box_append (GTK_BOX (box), gdl_action_card_new ("code", "Open the repository in your editor", "Ctrl+Shift+A", "win.open-editor"));
  gtk_box_append (GTK_BOX (box), gdl_action_card_new ("folder", "Show in your file manager", "Ctrl+Shift+F", "win.file-manager"));
  gtk_box_append (GTK_BOX (box), gdl_action_card_new ("terminal", "Open in terminal", "Ctrl+`", "win.open-terminal"));
  return box;
}

static void
show_selected_change (GdlWindow *self)
{
  if (!self->repo || !self->tabs || g_strcmp0 (adw_toggle_group_get_active_name (self->tabs), "changes") != 0)
    return;
  GtkListBoxRow *row = gtk_list_box_get_selected_row (GTK_LIST_BOX (self->files_list));
  if (!row) {
    gdl_diff_view_show_message (self->diff, "check", "No local changes",
                                "There are no uncommitted changes in this repository. Here are some friendly suggestions:",
                                clean_tree_actions (self));
    return;
  }
  GdlFile *f = g_object_get_data (G_OBJECT (row), "file");
  g_autofree char *diff = gdl_repo_file_diff (self->repo, f);
  gdl_diff_view_set_diff (self->diff, f->path, diff, f->status, f->status != GDL_ST_DELETED);
}

static void
on_file_selected (GtkListBox *list, GtkListBoxRow *row, GdlWindow *self)
{
  show_selected_change (self);
}

/* ================================================================== */
/* History                                                             */
/* ================================================================== */

static GtkWidget *
commit_row (GdlCommit *c)
{
  GtkWidget *row = gtk_list_box_row_new ();
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 12);
  gtk_widget_add_css_class (box, "commit-row");
  GtkWidget *avatar = adw_avatar_new (30, c->author, TRUE);
  gtk_box_append (GTK_BOX (box), avatar);
  GtkWidget *texts = gtk_box_new (GTK_ORIENTATION_VERTICAL, 2);
  gtk_widget_set_hexpand (texts, TRUE);
  GtkWidget *summary = label_new (c->summary, "commit-summary", 0);
  gtk_label_set_ellipsize (GTK_LABEL (summary), PANGO_ELLIPSIZE_END);
  gtk_label_set_single_line_mode (GTK_LABEL (summary), TRUE);
  g_autofree char *ago = gdl_time_ago (c->time);
  g_autofree char *meta_text = g_strdup_printf ("%s · %s", c->author, ago);
  GtkWidget *meta = label_new (meta_text, "commit-meta", 0);
  gtk_label_set_ellipsize (GTK_LABEL (meta), PANGO_ELLIPSIZE_END);
  gtk_box_append (GTK_BOX (texts), summary);
  gtk_box_append (GTK_BOX (texts), meta);
  gtk_box_append (GTK_BOX (box), texts);
  gtk_list_box_row_set_child (GTK_LIST_BOX_ROW (row), box);
  gtk_widget_set_tooltip_text (row, c->summary);
  g_object_set_data_full (G_OBJECT (row), "hash", g_strdup (c->hash), g_free);
  return row;
}

static void
load_history_page (GdlWindow *self)
{
  if (!self->repo || self->history_done)
    return;
  g_autoptr (GPtrArray) page = gdl_repo_history (self->repo, self->history_count, HISTORY_PAGE);
  for (guint i = 0; i < page->len; i++)
    gtk_list_box_append (GTK_LIST_BOX (self->history_list), commit_row (g_ptr_array_index (page, i)));
  self->history_count += page->len;
  self->history_done = page->len < HISTORY_PAGE;
}

static void
reload_history (GdlWindow *self)
{
  clear_list (self->history_list);
  self->history_count = 0;
  self->history_done = FALSE;
  load_history_page (self);
  /* keep the shown commit selected if it is still there */
  GtkWidget *target = NULL;
  for (GtkWidget *row = gtk_widget_get_first_child (self->history_list); row && self->shown_commit;
       row = gtk_widget_get_next_sibling (row))
    if (g_str_equal (g_object_get_data (G_OBJECT (row), "hash"), self->shown_commit))
      target = row;
  if (!target)
    target = GTK_WIDGET (gtk_list_box_get_row_at_index (GTK_LIST_BOX (self->history_list), 0));
  if (target)
    gtk_list_box_select_row (GTK_LIST_BOX (self->history_list), GTK_LIST_BOX_ROW (target));
  else
    show_commit (self, NULL);
}

static void
on_history_edge (GtkScrolledWindow *sw, GtkPositionType pos, GdlWindow *self)
{
  if (pos == GTK_POS_BOTTOM)
    load_history_page (self);
}

static void
on_history_selected (GtkListBox *list, GtkListBoxRow *row, GdlWindow *self)
{
  if (row && self->repo)
    show_commit (self, g_object_get_data (G_OBJECT (row), "hash"));
}

static void
on_commit_file_selected (GtkListBox *list, GtkListBoxRow *row, GdlWindow *self)
{
  if (!row || !self->shown_commit)
    return;
  GdlFile *f = g_object_get_data (G_OBJECT (row), "file");
  g_autofree char *diff = gdl_repo_commit_file_diff (self->repo, self->shown_commit, f->path, f->orig_path);
  gdl_diff_view_set_diff (self->commit_diff, f->path, diff, f->status, FALSE);
}

static void
show_commit (GdlWindow *self, const char *hash)
{
  clear_list (self->commit_files);
  g_free (self->shown_commit);
  self->shown_commit = g_strdup (hash);
  if (!hash || !self->repo) {
    gtk_label_set_text (GTK_LABEL (self->commit_title), "No commits yet");
    gtk_widget_set_visible (self->commit_body, FALSE);
    gtk_label_set_text (GTK_LABEL (self->commit_meta), "");
    gtk_label_set_text (GTK_LABEL (self->commit_count), "");
    gdl_diff_view_show_message (self->commit_diff, "history", "Your first commit will show up here", NULL, NULL);
    return;
  }
  GdlCommit *c = gdl_repo_commit_details (self->repo, hash);
  if (!c)
    return;
  adw_avatar_set_text (ADW_AVATAR (self->commit_avatar), c->author);
  gtk_label_set_text (GTK_LABEL (self->commit_title), c->summary);
  gtk_label_set_text (GTK_LABEL (self->commit_body), c->body);
  gtk_widget_set_visible (self->commit_body, *c->body != '\0');
  g_autoptr (GDateTime) dt = g_date_time_new_from_unix_local (c->time);
  g_autofree char *date = g_date_time_format (dt, "%d.%m.%Y %H:%M");
  g_autofree char *meta = g_strdup_printf ("%s <%s>  ·  %s  ·  %s", c->author, c->email, date, c->short_hash);
  gtk_label_set_text (GTK_LABEL (self->commit_meta), meta);
  gdl_commit_free (c);

  GPtrArray *files = gdl_repo_commit_files (self->repo, hash);
  /* rows keep pointers into `files`; let the list own it */
  g_object_set_data_full (G_OBJECT (self->commit_files), "files", files, (GDestroyNotify) g_ptr_array_unref);
  g_autofree char *count = g_strdup_printf ("%u changed file%s", files->len, files->len == 1 ? "" : "s");
  gtk_label_set_text (GTK_LABEL (self->commit_count), count);
  for (guint i = 0; i < files->len; i++)
    gtk_list_box_append (GTK_LIST_BOX (self->commit_files), file_row (self, g_ptr_array_index (files, i), FALSE));
  GtkListBoxRow *first = gtk_list_box_get_row_at_index (GTK_LIST_BOX (self->commit_files), 0);
  if (first)
    gtk_list_box_select_row (GTK_LIST_BOX (self->commit_files), first);
  else
    gdl_diff_view_show_message (self->commit_diff, "commit", "This commit has no file changes", NULL, NULL);
}

/* ================================================================== */
/* Refresh                                                             */
/* ================================================================== */

static void
update_sync_button (GdlWindow *self)
{
  g_free (self->sync_mode);
  if (self->busy) {
    self->sync_mode = g_strdup ("busy");
    return;
  }
  g_autoptr (GPtrArray) remotes = gdl_repo_remotes (self->repo);
  GdlSync s;
  gdl_repo_sync_status (self->repo, &s);
  g_autofree char *ago = gdl_time_ago (gdl_repo_last_fetch (self->repo));
  g_autofree char *fetched = g_strdup_printf ("Last fetched %s", ago);
  const char *icon, *title;
  g_autofree char *caption = NULL;
  if (!remotes->len) {
    self->sync_mode = g_strdup ("none");
    icon = "sync"; title = "No remote"; caption = g_strdup ("Add a remote to publish");
  } else if (!s.has_upstream) {
    self->sync_mode = g_strdup ("publish");
    icon = "upload"; title = "Publish branch"; caption = g_strdup ("Publish this branch to origin");
  } else if (s.behind > 0) {
    self->sync_mode = g_strdup ("pull");
    icon = "arrow-down"; title = "Pull origin";
    caption = s.ahead ? g_strdup_printf ("↓%d ↑%d · %s", s.behind, s.ahead, fetched)
                      : g_strdup_printf ("↓%d · %s", s.behind, fetched);
  } else if (s.ahead > 0) {
    self->sync_mode = g_strdup ("push");
    icon = "arrow-up"; title = "Push origin"; caption = g_strdup_printf ("↑%d · %s", s.ahead, fetched);
  } else {
    self->sync_mode = g_strdup ("fetch");
    icon = "sync"; title = "Fetch origin"; caption = g_strdup (fetched);
  }
  gdl_icon_set_name (GDL_ICON (self->sync_icon), icon);
  gtk_label_set_text (GTK_LABEL (self->sync_title), title);
  gtk_label_set_text (GTK_LABEL (self->sync_caption), caption);
  gtk_widget_set_sensitive (self->sync_button, remotes->len > 0);
  gdl_sync_clear (&s);
}

static void
update_banners (GdlWindow *self)
{
  gboolean merging = gdl_repo_is_merging (self->repo);
  gtk_widget_set_visible (self->merge_banner, merging);
  g_autofree char *branch = gdl_repo_branch (self->repo);
  gtk_widget_set_visible (self->stash_banner, gdl_repo_find_stash (self->repo, branch) >= 0);

  /* Undo stays until the commit is pushed (GitHub Desktop rule) */
  GdlSync s;
  gdl_repo_sync_status (self->repo, &s);
  gboolean can_undo = self->undo_hash && g_strcmp0 (self->undo_hash, self->head_hash) == 0 &&
                      (!s.has_upstream || s.ahead > 0);
  gdl_sync_clear (&s);
  if (can_undo) {
    g_autofree char *esc = gdl_escape (self->undo_summary);
    g_autofree char *markup = g_strdup_printf ("<b>Committed just now</b>\n%s", esc);
    gtk_label_set_markup (GTK_LABEL (self->undo_label), markup);
  }
  gtk_widget_set_visible (self->undo_banner, can_undo);
}

void
gdl_window_refresh (GdlWindow *self, gboolean force)
{
  gint64 now = g_get_monotonic_time ();
  if (!force && now - self->last_refresh < G_USEC_PER_SEC)
    return;
  self->last_refresh = now;

  for (const char *const *a = REPO_ACTIONS; *a; a++)
    set_action_enabled (self, *a, self->repo != NULL);
  gtk_widget_set_sensitive (self->branch_button, self->repo != NULL);

  if (!self->repo) {
    gtk_window_set_title (GTK_WINDOW (self), "Git Desktop For Linux");
    gtk_label_set_text (GTK_LABEL (self->repo_title), "Add a repository");
    gtk_label_set_text (GTK_LABEL (self->branch_title), "—");
    gtk_label_set_text (GTK_LABEL (self->sync_title), "—");
    gtk_label_set_text (GTK_LABEL (self->sync_caption), "");
    gtk_widget_set_sensitive (self->sync_button, FALSE);
    gtk_widget_set_sensitive (self->side_stack, FALSE);
    gtk_stack_set_visible_child (GTK_STACK (self->main_stack), self->blank);
    return;
  }
  gtk_widget_set_sensitive (self->side_stack, TRUE);

  g_autofree char *name = gdl_repo_name (self->repo);
  g_autofree char *branch = gdl_repo_branch (self->repo);
  g_autofree char *title = g_strdup_printf ("%s — Git Desktop For Linux", name);
  gtk_window_set_title (GTK_WINDOW (self), title);
  gtk_label_set_text (GTK_LABEL (self->repo_title), name);
  gtk_label_set_text (GTK_LABEL (self->branch_title), branch);

  g_autofree char *who = NULL, *email = NULL;
  gdl_repo_identity (self->repo, &who, &email);
  adw_avatar_set_text (ADW_AVATAR (self->author_avatar), who ? who : "?");
  g_autofree char *tip = who ? g_strdup_printf ("Committing as %s <%s>", who, email)
                             : g_strdup ("Set your name and email in Preferences → Git");
  gtk_widget_set_tooltip_text (self->author_avatar, tip);

  char *head = gdl_repo_head_hash (self->repo);
  gboolean head_changed = g_strcmp0 (head, self->head_hash) != 0;
  g_free (self->head_hash);
  self->head_hash = head;

  refresh_files (self);
  if (head_changed || force)
    reload_history (self);
  update_sync_button (self);
  update_banners (self);

  const char *tab = adw_toggle_group_get_active_name (self->tabs);
  gtk_stack_set_visible_child_name (GTK_STACK (self->side_stack), tab);
  gtk_stack_set_visible_child_name (GTK_STACK (self->main_stack), tab);
}

void
gdl_window_open_repository (GdlWindow *self, const char *path)
{
  g_autoptr (GError) error = NULL;
  GdlRepo *repo = path ? gdl_repo_open (path, &error) : NULL;
  if (path && !repo) {
    settings_remove_recent (path);
    gdl_window_error (self, "Could not open repository", error->message);
  }
  if (!repo && self->repo)
    return;  /* keep what is open */
  g_clear_pointer (&self->repo, gdl_repo_free);
  self->repo = repo;
  g_hash_table_remove_all (self->unchecked);
  g_clear_pointer (&self->head_hash, g_free);
  g_clear_pointer (&self->undo_hash, g_free);
  g_clear_pointer (&self->shown_commit, g_free);
  gtk_editable_set_text (GTK_EDITABLE (self->summary_entry), "");
  gtk_text_buffer_set_text (gtk_text_view_get_buffer (GTK_TEXT_VIEW (self->description_view)), "", 0);
  if (repo) {
    settings_add_recent (gdl_repo_path (repo));
    settings_set_string ("last_repo", gdl_repo_path (repo));
  }
  gdl_window_refresh (self, TRUE);
}

/* ================================================================== */
/* Commit, undo, discard, stash                                        */
/* ================================================================== */

static char *
description_text (GdlWindow *self)
{
  GtkTextBuffer *buf = gtk_text_view_get_buffer (GTK_TEXT_VIEW (self->description_view));
  GtkTextIter a, b;
  gtk_text_buffer_get_bounds (buf, &a, &b);
  return gtk_text_buffer_get_text (buf, &a, &b, FALSE);
}

static void
do_commit (GdlWindow *self)
{
  if (!gtk_widget_get_sensitive (self->commit_button))
    return;
  const char *summary = gtk_editable_get_text (GTK_EDITABLE (self->summary_entry));
  g_autofree char *description = description_text (self);
  g_autoptr (GHashTable) checked = g_hash_table_new (g_str_hash, g_str_equal);
  for (guint i = 0; i < self->files->len; i++) {
    GdlFile *f = g_ptr_array_index (self->files, i);
    if (is_checked (self, f->path))
      g_hash_table_add (checked, f->path);
  }
  g_autoptr (GError) error = NULL;
  if (!gdl_repo_commit (self->repo, self->files, checked, summary, description, &error)) {
    gdl_window_error (self, "Commit failed", error->message);
    gdl_window_refresh (self, TRUE);
    return;
  }
  g_free (self->undo_hash);
  self->undo_hash = gdl_repo_head_hash (self->repo);
  g_free (self->undo_summary);
  g_free (self->undo_description);
  self->undo_summary = g_strstrip (g_strdup (summary));
  self->undo_description = g_strdup (description);
  gtk_editable_set_text (GTK_EDITABLE (self->summary_entry), "");
  gtk_text_buffer_set_text (gtk_text_view_get_buffer (GTK_TEXT_VIEW (self->description_view)), "", 0);
  gdl_window_refresh (self, TRUE);
}

static void
do_undo (GdlWindow *self)
{
  g_autofree char *summary = NULL, *description = NULL;
  g_autoptr (GError) error = NULL;
  if (!gdl_repo_undo_commit (self->repo, &summary, &description, &error)) {
    gdl_window_error (self, "Could not undo the commit", error->message);
    return;
  }
  gtk_editable_set_text (GTK_EDITABLE (self->summary_entry), summary);
  gtk_text_buffer_set_text (gtk_text_view_get_buffer (GTK_TEXT_VIEW (self->description_view)), description, -1);
  g_clear_pointer (&self->undo_hash, g_free);
  gdl_window_refresh (self, TRUE);
}

typedef struct {
  GdlWindow *self;
  char      *path;   /* NULL = all files */
} DiscardJob;

static void
discard_job_free (gpointer data, GClosure *closure)
{
  DiscardJob *job = data;
  g_free (job->path);
  g_free (job);
}

static void
on_discard_response (AdwAlertDialog *d, const char *response, DiscardJob *job)
{
  if (!g_str_equal (response, "discard"))
    return;
  GdlWindow *self = job->self;
  g_autoptr (GString) failed = g_string_new (NULL);
  for (guint i = 0; i < self->files->len; i++) {
    GdlFile *f = g_ptr_array_index (self->files, i);
    if (job->path && !g_str_equal (job->path, f->path))
      continue;
    g_autoptr (GError) error = NULL;
    if (!gdl_repo_discard (self->repo, f, &error))
      g_string_append_printf (failed, "%s: %s\n", f->path, error->message);
  }
  if (failed->len)
    gdl_window_error (self, "Discard failed", failed->str);
  gdl_window_refresh (self, TRUE);
}

static void
confirm_discard (GdlWindow *self, const char *path)
{
  if (!self->files || !self->files->len)
    return;
  g_autofree char *what = path ? g_strdup_printf ("all changes to “%s”", path)
                               : g_strdup_printf ("all %u changed files", self->files->len);
  g_autofree char *body = g_strdup_printf ("Are you sure you want to discard %s?\n\nNew files are moved to the "
                                           "trash. Changes to tracked files cannot be recovered.", what);
  AdwDialog *d = adw_alert_dialog_new ("Discard changes?", body);
  adw_alert_dialog_add_responses (ADW_ALERT_DIALOG (d), "cancel", "Cancel", "discard", "Discard", NULL);
  adw_alert_dialog_set_response_appearance (ADW_ALERT_DIALOG (d), "discard", ADW_RESPONSE_DESTRUCTIVE);
  DiscardJob *job = g_new0 (DiscardJob, 1);
  job->self = self;
  job->path = g_strdup (path);
  g_signal_connect_data (d, "response", G_CALLBACK (on_discard_response), job, discard_job_free, 0);
  adw_dialog_present (d, GTK_WIDGET (self));
}

/* ================================================================== */
/* Network                                                             */
/* ================================================================== */

typedef struct {
  GdlWindow *self;
  char      *mode;
  gboolean   quiet;
} SyncJob;

static void
set_busy (GdlWindow *self, gboolean busy, const char *label)
{
  self->busy = busy;
  gtk_widget_set_visible (self->sync_spinner, busy);
  gtk_widget_set_visible (self->sync_icon, !busy);
  gtk_widget_set_sensitive (self->sync_button, !busy);
  if (busy) {
    gtk_label_set_text (GTK_LABEL (self->sync_title), label);
    gtk_label_set_text (GTK_LABEL (self->sync_caption), "Working…");
  }
}

static void
on_sync_done (gboolean ok, const char *output, gpointer data)
{
  SyncJob *job = data;
  GdlWindow *self = job->self;
  set_busy (self, FALSE, NULL);
  if (!ok && !job->quiet) {
    g_autofree char *msg = gdl_net_explain_error (output);
    g_autofree char *title = g_strdup_printf ("%c%s failed", g_ascii_toupper (job->mode[0]), job->mode + 1);
    gdl_window_error (self, title, msg);
  } else if (ok && !job->quiet) {
    const char *done = g_str_equal (job->mode, "push") ? "Pushed to origin"
                     : g_str_equal (job->mode, "pull") ? "Pulled from origin"
                     : g_str_equal (job->mode, "publish") ? "Branch published" : "Fetched origin";
    gdl_window_toast (self, done);
  }
  if (self->repo)
    gdl_window_refresh (self, TRUE);
  g_object_unref (self);
  g_free (job->mode);
  g_free (job);
}

static void
run_sync (GdlWindow *self, const char *mode, gboolean quiet)
{
  if (self->busy || !self->repo)
    return;
  g_autoptr (GPtrArray) remotes = gdl_repo_remotes (self->repo);
  if (!remotes->len)
    return;
  if (!mode)
    mode = self->sync_mode ? self->sync_mode : "fetch";
  GdlSync s;
  gdl_repo_sync_status (self->repo, &s);
  if (g_str_equal (mode, "push") && !s.has_upstream)
    mode = "publish";
  gdl_sync_clear (&s);
  if (g_str_equal (mode, "none") || g_str_equal (mode, "busy"))
    return;

  SyncJob *job = g_new0 (SyncJob, 1);
  job->self = g_object_ref (self);
  job->mode = g_strdup (mode);
  job->quiet = quiet;
  const char *repo = gdl_repo_path (self->repo);
  const char *token = gdl_window_get_token (self);
  if (g_str_equal (mode, "pull")) {
    /* merge like GitHub Desktop unless the user configured pull.rebase / pull.ff */
    g_autofree char *rebase = gdl_repo_config_string (self->repo, "pull.rebase");
    g_autofree char *ff = gdl_repo_config_string (self->repo, "pull.ff");
    set_busy (self, TRUE, "Pulling origin…");
    gdl_net_pull (repo, token, !rebase && !ff, on_sync_done, job);
  } else if (g_str_equal (mode, "push")) {
    set_busy (self, TRUE, "Pushing to origin…");
    gdl_net_push (repo, token, NULL, on_sync_done, job);
  } else if (g_str_equal (mode, "publish")) {
    g_autofree char *branch = gdl_repo_branch (self->repo);
    set_busy (self, TRUE, "Publishing branch…");
    gdl_net_push (repo, token, branch, on_sync_done, job);
  } else {
    set_busy (self, TRUE, "Fetching origin…");
    gdl_net_fetch (repo, token, on_sync_done, job);
  }
}

static gboolean
auto_fetch (gpointer data)
{
  run_sync (GDL_WINDOW (data), "fetch", TRUE);
  return G_SOURCE_CONTINUE;
}

/* ================================================================== */
/* Account                                                             */
/* ================================================================== */

static void
clear_box (GtkWidget *box)
{
  GtkWidget *child;
  while ((child = gtk_widget_get_first_child (box)))
    gtk_box_remove (GTK_BOX (box), child);
}

static GtkWidget *
menu_row (const char *icon, const char *label, const char *action)
{
  GtkWidget *b = gtk_button_new ();
  gtk_widget_add_css_class (b, "flat");
  gtk_actionable_set_action_name (GTK_ACTIONABLE (b), action);
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 10);
  GtkWidget *ic = gdl_icon_new (icon, 16);
  gtk_widget_add_css_class (ic, "dim-label");
  gtk_box_append (GTK_BOX (box), ic);
  gtk_box_append (GTK_BOX (box), label_new (label, NULL, 0));
  gtk_button_set_child (GTK_BUTTON (b), box);
  return b;
}

static void
fill_account_box (GdlWindow *self)
{
  clear_box (self->account_box);
  GtkBox *box = GTK_BOX (self->account_box);
  if (self->account_loading) {
    gtk_box_append (box, label_new ("Checking your GitHub account…", "dim-label", 0));
    return;
  }
  GdlProfile *p = self->account ? self->account->profile : NULL;
  if (p) {
    GtkWidget *head = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 12);
    GtkWidget *av = adw_avatar_new (56, p->name, TRUE);
    if (self->avatar)
      adw_avatar_set_custom_image (ADW_AVATAR (av), GDK_PAINTABLE (self->avatar));
    gtk_box_append (GTK_BOX (head), av);
    GtkWidget *names = gtk_box_new (GTK_ORIENTATION_VERTICAL, 2);
    gtk_widget_set_valign (names, GTK_ALIGN_CENTER);
    gtk_box_append (GTK_BOX (names), label_new (p->name, "title-4", 0));
    g_autofree char *login = g_strdup_printf ("@%s", p->login);
    gtk_box_append (GTK_BOX (names), label_new (login, "dim-label", 0));
    gtk_box_append (GTK_BOX (head), names);
    gtk_box_append (box, head);
    if (self->account->repos) {
      g_autofree char *count = g_strdup_printf ("%u repositories on GitHub.com", self->account->repos->len);
      gtk_box_append (box, label_new (count, "dim-label", 0));
    }
    gtk_box_append (box, gtk_separator_new (GTK_ORIENTATION_HORIZONTAL));
    gtk_box_append (box, menu_row ("external", "Your profile on GitHub", "win.open-profile"));
    gtk_box_append (box, menu_row ("settings", "Preferences…", "win.preferences"));
    gtk_box_append (box, gtk_separator_new (GTK_ORIENTATION_HORIZONTAL));
    gtk_box_append (box, menu_row ("logout", "Sign out", "win.sign-out"));
  } else {
    gtk_box_append (box, label_new ("Not signed in", "title-4", 0));
    GtkWidget *hint = label_new ("Sign in to see your repositories and to push, pull and clone without passwords.",
                                 "dim-label", 0);
    gtk_label_set_wrap (GTK_LABEL (hint), TRUE);
    gtk_label_set_max_width_chars (GTK_LABEL (hint), 34);
    gtk_box_append (box, hint);
    GtkWidget *sign_in = gtk_button_new_with_label ("Sign in to GitHub.com");
    gtk_widget_add_css_class (sign_in, "suggested-action");
    gtk_widget_add_css_class (sign_in, "pill");
    gtk_actionable_set_action_name (GTK_ACTIONABLE (sign_in), "win.sign-in");
    gtk_box_append (box, sign_in);
    gtk_box_append (box, menu_row ("settings", "Preferences…", "win.preferences"));
  }
  /* any button in the card closes the card before its action runs */
  for (GtkWidget *w = gtk_widget_get_first_child (self->account_box); w; w = gtk_widget_get_next_sibling (w))
    if (GTK_IS_BUTTON (w))
      g_signal_connect_swapped (w, "clicked", G_CALLBACK (gtk_menu_button_popdown), self->profile_button);
}

static void
on_avatar_loaded (GObject *src, GAsyncResult *res, gpointer data)
{
  GdlWindow *self = data;
  g_autoptr (GBytes) bytes = gdl_avatar_load_finish (res, NULL);
  if (bytes) {
    g_clear_object (&self->avatar);
    self->avatar = gdk_texture_new_from_bytes (bytes, NULL);
    if (self->avatar) {
      adw_avatar_set_custom_image (ADW_AVATAR (self->profile_avatar), GDK_PAINTABLE (self->avatar));
      fill_account_box (self);  /* show the photo in the account card too */
    }
  }
  g_object_unref (self);
}

static void
apply_account (GdlWindow *self, GdlAccount *account)
{
  self->account_loading = FALSE;
  g_clear_pointer (&self->account, gdl_account_free);
  g_clear_object (&self->avatar);
  self->account = account;
  GdlProfile *p = account ? account->profile : NULL;
  adw_avatar_set_custom_image (ADW_AVATAR (self->profile_avatar), NULL);
  adw_avatar_set_text (ADW_AVATAR (self->profile_avatar), p ? p->name : NULL);
  adw_avatar_set_show_initials (ADW_AVATAR (self->profile_avatar), p != NULL);
  g_autofree char *tip = p ? g_strdup_printf ("Signed in as @%s", p->login) : g_strdup ("Sign in to GitHub.com");
  gtk_widget_set_tooltip_text (self->profile_button, tip);
  if (p && p->avatar_url && *p->avatar_url)
    gdl_avatar_load_async (p->avatar_url, NULL, on_avatar_loaded, g_object_ref (self));
  fill_account_box (self);
}

static void
on_account_loaded (GObject *src, GAsyncResult *res, gpointer data)
{
  GdlWindow *self = data;
  apply_account (self, gdl_account_load_finish (res, NULL));
  g_object_unref (self);
}

void
gdl_window_reload_account (GdlWindow *self)
{
  self->account_loading = TRUE;
  fill_account_box (self);
  gdl_account_load_async (NULL, on_account_loaded, g_object_ref (self));
}

static gboolean
open_sign_in_later (gpointer data)
{
  gdl_sign_in_dialog_show (GDL_WINDOW (data));
  return G_SOURCE_REMOVE;
}

static void
on_sign_out_response (AdwAlertDialog *d, const char *response, GdlWindow *self)
{
  if (!g_str_equal (response, "sign-out"))
    return;
  gdl_token_clear ();
  apply_account (self, NULL);
  /* straight to the sign-in screen */
  g_idle_add_full (G_PRIORITY_DEFAULT_IDLE, open_sign_in_later, g_object_ref (self), g_object_unref);
}

/* ================================================================== */
/* Integrations                                                        */
/* ================================================================== */

static const char *const EDITORS[] = { "code", "codium", "cursor", "zed", "subl", "kate", "gnome-text-editor", "gedit", NULL };
static const char *const TERMINALS[] = { "konsole", "gnome-terminal", "kgx", "ptyxis", "kitty", "alacritty",
                                         "wezterm", "foot", "xfce4-terminal", "tilix", "xterm", NULL };

static gboolean
spawn_in (GdlWindow *self, const char *cwd, const char *program, const char *arg)
{
  const char *argv[] = { program, arg, NULL };
  g_autoptr (GError) error = NULL;
  if (!g_spawn_async (cwd, (char **) argv, NULL, G_SPAWN_SEARCH_PATH | G_SPAWN_STDIN_FROM_DEV_NULL,
                      NULL, NULL, NULL, &error)) {
    gdl_window_error (self, "Could not start program", error->message);
    return FALSE;
  }
  return TRUE;
}

static void
open_in_editor (GdlWindow *self, const char *rel_path)
{
  g_autofree char *target = rel_path ? g_build_filename (gdl_repo_path (self->repo), rel_path, NULL)
                                     : g_strdup (gdl_repo_path (self->repo));
  g_autofree char *preferred = settings_get_string ("editor");
  if (preferred && g_find_program_in_path (preferred)) {
    spawn_in (self, gdl_repo_path (self->repo), preferred, target);
    return;
  }
  for (const char *const *e = EDITORS; *e; e++) {
    g_autofree char *found = g_find_program_in_path (*e);
    if (found) {
      spawn_in (self, gdl_repo_path (self->repo), *e, target);
      return;
    }
  }
  g_autoptr (GFile) file = g_file_new_for_path (target);
  g_autoptr (GtkFileLauncher) launcher = gtk_file_launcher_new (file);
  gtk_file_launcher_launch (launcher, GTK_WINDOW (self), NULL, NULL, NULL);
}

static void
open_terminal (GdlWindow *self)
{
  g_autofree char *preferred = settings_get_string ("terminal");
  const char *env = g_getenv ("TERMINAL");
  const char *first[] = { preferred, env };
  for (guint i = 0; i < G_N_ELEMENTS (first); i++) {
    g_autofree char *found = first[i] ? g_find_program_in_path (first[i]) : NULL;
    if (found) {
      spawn_in (self, gdl_repo_path (self->repo), first[i], NULL);
      return;
    }
  }
  for (const char *const *t = TERMINALS; *t; t++) {
    g_autofree char *found = g_find_program_in_path (*t);
    if (found) {
      spawn_in (self, gdl_repo_path (self->repo), *t, NULL);
      return;
    }
  }
  gdl_window_error (self, "No terminal found", "Set your terminal in Preferences → Integrations.");
}

static void
show_in_folder (GdlWindow *self, const char *rel_path)
{
  g_autofree char *target = rel_path ? g_build_filename (gdl_repo_path (self->repo), rel_path, NULL)
                                     : g_strdup (gdl_repo_path (self->repo));
  g_autoptr (GFile) file = g_file_new_for_path (target);
  g_autoptr (GtkFileLauncher) launcher = gtk_file_launcher_new (file);
  if (rel_path && g_file_query_exists (file, NULL))
    gtk_file_launcher_open_containing_folder (launcher, GTK_WINDOW (self), NULL, NULL, NULL);
  else
    gtk_file_launcher_launch (launcher, GTK_WINDOW (self), NULL, NULL, NULL);
}

static void
copy_text (GdlWindow *self, const char *text)
{
  gdk_clipboard_set_text (gtk_widget_get_clipboard (GTK_WIDGET (self)), text);
  gdl_window_toast (self, "Copied to clipboard");
}

/* ================================================================== */
/* Actions                                                             */
/* ================================================================== */

#define ACTION(name) static void act_##name (GSimpleAction *a, GVariant *p, gpointer data)
#define SELF GdlWindow *self = GDL_WINDOW (data)

ACTION (show_changes)  { SELF; adw_toggle_group_set_active_name (self->tabs, "changes"); }
ACTION (show_history)  { SELF; adw_toggle_group_set_active_name (self->tabs, "history"); }
ACTION (repo_list)     { SELF; gtk_menu_button_popup (GTK_MENU_BUTTON (self->repo_button)); }
ACTION (branch_list)   { SELF; gtk_menu_button_popup (GTK_MENU_BUTTON (self->branch_button)); }
ACTION (new_branch)    { SELF; gdl_branch_name_dialog_show (self, NULL); }
ACTION (merge)         { SELF; gdl_merge_dialog_show (self); }
ACTION (clone)         { SELF; gdl_clone_dialog_show (self, NULL); }
ACTION (new_repo)      { SELF; gdl_create_dialog_show (self); }
ACTION (add_repo)      { SELF; gdl_add_existing_show (self); }
ACTION (preferences)   { SELF; gdl_preferences_show (self); }
ACTION (sign_in)       { SELF; gdl_sign_in_dialog_show (self); }
ACTION (commit)        { SELF; do_commit (self); }
ACTION (undo_commit)   { SELF; do_undo (self); }
ACTION (push)          { SELF; run_sync (self, "push", FALSE); }
ACTION (pull)          { SELF; run_sync (self, "pull", FALSE); }
ACTION (fetch)         { SELF; run_sync (self, "fetch", FALSE); }
ACTION (sync)          { SELF; run_sync (self, NULL, FALSE); }
ACTION (refresh)       { SELF; gdl_window_refresh (self, TRUE); }
ACTION (open_editor)   { SELF; open_in_editor (self, NULL); }
ACTION (open_terminal) { SELF; open_terminal (self); }
ACTION (file_manager)  { SELF; show_in_folder (self, NULL); }
ACTION (discard_all)   { SELF; confirm_discard (self, NULL); }
ACTION (discard_file)  { SELF; confirm_discard (self, g_variant_get_string (p, NULL)); }
ACTION (open_file_editor) { SELF; open_in_editor (self, g_variant_get_string (p, NULL)); }
ACTION (show_in_folder)   { SELF; show_in_folder (self, g_variant_get_string (p, NULL)); }
ACTION (copy_relpath)     { SELF; copy_text (self, g_variant_get_string (p, NULL)); }

ACTION (rename_branch)
{
  SELF;
  g_autofree char *b = gdl_repo_branch (self->repo);
  gdl_branch_name_dialog_show (self, b);
}

ACTION (rename_branch_named) { SELF; gdl_branch_name_dialog_show (self, g_variant_get_string (p, NULL)); }

static void
on_delete_response (AdwAlertDialog *d, const char *response, GdlWindow *self)
{
  const char *name = g_object_get_data (G_OBJECT (d), "branch");
  if (!g_str_equal (response, "delete") && !g_str_equal (response, "force"))
    return;
  g_autoptr (GError) error = NULL;
  if (!gdl_repo_delete_branch (self->repo, name, g_str_equal (response, "force"), &error)) {
    if (g_error_matches (error, GDL_GIT_ERROR, GDL_GIT_ERROR_NOT_MERGED)) {
      g_autofree char *body = g_strdup_printf ("%s\n\nDelete it anyway? Its unmerged commits will be lost.", error->message);
      AdwDialog *again = adw_alert_dialog_new ("Delete unmerged branch?", body);
      adw_alert_dialog_add_responses (ADW_ALERT_DIALOG (again), "cancel", "Cancel", "force", "Delete anyway", NULL);
      adw_alert_dialog_set_response_appearance (ADW_ALERT_DIALOG (again), "force", ADW_RESPONSE_DESTRUCTIVE);
      g_object_set_data_full (G_OBJECT (again), "branch", g_strdup (name), g_free);
      g_signal_connect (again, "response", G_CALLBACK (on_delete_response), self);
      adw_dialog_present (again, GTK_WIDGET (self));
      return;
    }
    gdl_window_error (self, "Could not delete branch", error->message);
  }
  gdl_window_refresh (self, TRUE);
}

static void
confirm_delete_branch (GdlWindow *self, const char *name)
{
  g_autofree char *body = g_strdup_printf ("Delete the branch “%s”? This cannot be undone.", name);
  AdwDialog *d = adw_alert_dialog_new ("Delete branch?", body);
  adw_alert_dialog_add_responses (ADW_ALERT_DIALOG (d), "cancel", "Cancel", "delete", "Delete", NULL);
  adw_alert_dialog_set_response_appearance (ADW_ALERT_DIALOG (d), "delete", ADW_RESPONSE_DESTRUCTIVE);
  g_object_set_data_full (G_OBJECT (d), "branch", g_strdup (name), g_free);
  g_signal_connect (d, "response", G_CALLBACK (on_delete_response), self);
  adw_dialog_present (d, GTK_WIDGET (self));
}

ACTION (delete_branch)
{
  SELF;
  g_autofree char *b = gdl_repo_branch (self->repo);
  confirm_delete_branch (self, b);
}

ACTION (delete_branch_named) { SELF; confirm_delete_branch (self, g_variant_get_string (p, NULL)); }

static void
on_abort_response (AdwAlertDialog *d, const char *response, GdlWindow *self)
{
  if (!g_str_equal (response, "abort"))
    return;
  g_autoptr (GError) error = NULL;
  if (!gdl_repo_abort_merge (self->repo, &error))
    gdl_window_error (self, "Could not abort the merge", error->message);
  gdl_window_refresh (self, TRUE);
}

ACTION (abort_merge)
{
  SELF;
  if (!gdl_repo_is_merging (self->repo))
    return;
  AdwDialog *d = adw_alert_dialog_new ("Abort merge?", "Return to the state before the merge started? "
                                                       "Changes made while resolving conflicts are lost.");
  adw_alert_dialog_add_responses (ADW_ALERT_DIALOG (d), "cancel", "Cancel", "abort", "Abort merge", NULL);
  adw_alert_dialog_set_response_appearance (ADW_ALERT_DIALOG (d), "abort", ADW_RESPONSE_DESTRUCTIVE);
  g_signal_connect (d, "response", G_CALLBACK (on_abort_response), self);
  adw_dialog_present (d, GTK_WIDGET (self));
}

ACTION (stash)
{
  SELF;
  if (!self->files || !self->files->len)
    return;
  g_autoptr (GError) error = NULL;
  if (!gdl_repo_stash_all (self->repo, &error))
    gdl_window_error (self, "Could not stash changes", error->message);
  else
    gdl_window_toast (self, "Changes stashed");
  gdl_window_refresh (self, TRUE);
}

ACTION (restore_stash)
{
  SELF;
  g_autofree char *branch = gdl_repo_branch (self->repo);
  int idx = gdl_repo_find_stash (self->repo, branch);
  g_autoptr (GError) error = NULL;
  if (idx >= 0 && !gdl_repo_stash_pop (self->repo, idx, &error))
    gdl_window_error (self, "Could not restore the stash", error->message);
  gdl_window_refresh (self, TRUE);
}

static void
on_drop_stash_response (AdwAlertDialog *d, const char *response, GdlWindow *self)
{
  if (!g_str_equal (response, "discard"))
    return;
  g_autofree char *branch = gdl_repo_branch (self->repo);
  int idx = gdl_repo_find_stash (self->repo, branch);
  if (idx >= 0)
    gdl_repo_stash_drop (self->repo, idx, NULL);
  gdl_window_refresh (self, TRUE);
}

ACTION (discard_stash)
{
  SELF;
  AdwDialog *d = adw_alert_dialog_new ("Discard stash?", "The stashed changes will be deleted. This cannot be undone.");
  adw_alert_dialog_add_responses (ADW_ALERT_DIALOG (d), "cancel", "Cancel", "discard", "Discard", NULL);
  adw_alert_dialog_set_response_appearance (ADW_ALERT_DIALOG (d), "discard", ADW_RESPONSE_DESTRUCTIVE);
  g_signal_connect (d, "response", G_CALLBACK (on_drop_stash_response), self);
  adw_dialog_present (d, GTK_WIDGET (self));
}

ACTION (remove_repo)
{
  SELF;
  settings_remove_recent (gdl_repo_path (self->repo));
  g_autoptr (GPtrArray) recent = settings_recent ();
  g_clear_pointer (&self->repo, gdl_repo_free);
  gdl_window_open_repository (self, recent->len ? g_ptr_array_index (recent, 0) : NULL);
}

ACTION (ignore_file)
{
  SELF;
  g_autoptr (GError) error = NULL;
  if (!gdl_repo_add_ignore (self->repo, g_variant_get_string (p, NULL), &error))
    gdl_window_error (self, "Could not update .gitignore", error->message);
  gdl_window_refresh (self, TRUE);
}

ACTION (ignore_ext)
{
  SELF;
  const char *path = g_variant_get_string (p, NULL);
  const char *dot = strrchr (path, '.');
  if (!dot || strchr (dot, '/'))
    return;
  g_autofree char *pattern = g_strdup_printf ("*%s", dot);
  g_autoptr (GError) error = NULL;
  if (!gdl_repo_add_ignore (self->repo, pattern, &error))
    gdl_window_error (self, "Could not update .gitignore", error->message);
  gdl_window_refresh (self, TRUE);
}

ACTION (copy_path)
{
  SELF;
  g_autofree char *full = g_build_filename (gdl_repo_path (self->repo), g_variant_get_string (p, NULL), NULL);
  copy_text (self, full);
}

ACTION (copy_sha)
{
  SELF;
  if (self->shown_commit)
    copy_text (self, self->shown_commit);
}

ACTION (open_profile)
{
  SELF;
  GdlProfile *prof = self->account ? self->account->profile : NULL;
  if (!prof)
    return;
  g_autoptr (GtkUriLauncher) l = gtk_uri_launcher_new (prof->html_url);
  gtk_uri_launcher_launch (l, GTK_WINDOW (self), NULL, NULL, NULL);
}

ACTION (sign_out)
{
  SELF;
  GdlProfile *prof = self->account ? self->account->profile : NULL;
  g_autofree char *body = g_strdup_printf ("Sign out of %s? Your local repositories stay as they are.",
                                           prof ? prof->login : "GitHub");
  AdwDialog *d = adw_alert_dialog_new ("Sign out?", body);
  adw_alert_dialog_add_responses (ADW_ALERT_DIALOG (d), "cancel", "Cancel", "sign-out", "Sign out", NULL);
  adw_alert_dialog_set_response_appearance (ADW_ALERT_DIALOG (d), "sign-out", ADW_RESPONSE_DESTRUCTIVE);
  g_signal_connect (d, "response", G_CALLBACK (on_sign_out_response), self);
  adw_dialog_present (d, GTK_WIDGET (self));
}

static const GActionEntry WIN_ACTIONS[] = {
  { "show-changes", act_show_changes }, { "show-history", act_show_history },
  { "repo-list", act_repo_list }, { "branch-list", act_branch_list },
  { "new-branch", act_new_branch }, { "rename-branch", act_rename_branch },
  { "delete-branch", act_delete_branch }, { "rename-branch-named", act_rename_branch_named, "s" },
  { "delete-branch-named", act_delete_branch_named, "s" }, { "merge", act_merge },
  { "abort-merge", act_abort_merge }, { "stash", act_stash }, { "restore-stash", act_restore_stash },
  { "discard-stash", act_discard_stash }, { "discard-all", act_discard_all },
  { "commit", act_commit }, { "undo-commit", act_undo_commit },
  { "push", act_push }, { "pull", act_pull }, { "fetch", act_fetch }, { "sync", act_sync },
  { "refresh", act_refresh }, { "clone", act_clone }, { "new-repo", act_new_repo }, { "add-repo", act_add_repo },
  { "remove-repo", act_remove_repo }, { "open-editor", act_open_editor }, { "open-terminal", act_open_terminal },
  { "file-manager", act_file_manager }, { "preferences", act_preferences },
  { "sign-in", act_sign_in }, { "sign-out", act_sign_out }, { "open-profile", act_open_profile },
  { "copy-sha", act_copy_sha },
  { "discard-file", act_discard_file, "s" }, { "ignore-file", act_ignore_file, "s" },
  { "ignore-ext", act_ignore_ext, "s" }, { "copy-path", act_copy_path, "s" },
  { "copy-relpath", act_copy_relpath, "s" }, { "show-in-folder", act_show_in_folder, "s" },
  { "open-file-editor", act_open_file_editor, "s" },
};

/* ================================================================== */
/* Layout                                                              */
/* ================================================================== */

static GtkWidget *
banner_new (const char *icon, gboolean warn, GtkWidget **label_out,
            const char *b1, const char *a1, const char *b2, const char *a2)
{
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 8);
  gtk_widget_add_css_class (box, "banner-card");
  if (warn)
    gtk_widget_add_css_class (box, "warn");
  GtkWidget *ic = gdl_icon_new (icon, 16);
  gtk_widget_add_css_class (ic, warn ? "warning" : "accent");
  gtk_widget_set_valign (ic, GTK_ALIGN_START);
  gtk_widget_set_margin_top (ic, 2);
  gtk_box_append (GTK_BOX (box), ic);
  GtkWidget *label = label_new ("", NULL, 0);
  gtk_label_set_wrap (GTK_LABEL (label), TRUE);
  gtk_widget_set_hexpand (label, TRUE);
  gtk_box_append (GTK_BOX (box), label);
  const char *labels[] = { b1, b2 }, *actions[] = { a1, a2 };
  for (int i = 0; i < 2; i++) {
    if (!labels[i])
      continue;
    GtkWidget *b = gtk_button_new_with_label (labels[i]);
    gtk_widget_add_css_class (b, "flat");
    gtk_widget_set_valign (b, GTK_ALIGN_CENTER);
    gtk_actionable_set_action_name (GTK_ACTIONABLE (b), actions[i]);
    gtk_box_append (GTK_BOX (box), b);
  }
  gtk_widget_set_visible (box, FALSE);
  *label_out = label;
  return box;
}

static void
on_summary_changed (GtkEditable *e, GdlWindow *self)
{
  update_commit_button (self);
}

static void
on_tab_changed (GdlWindow *self)
{
  const char *tab = self->tabs ? adw_toggle_group_get_active_name (self->tabs) : NULL;
  if (!self->repo || !tab)
    return;
  gtk_stack_set_visible_child_name (GTK_STACK (self->side_stack), tab);
  gtk_stack_set_visible_child_name (GTK_STACK (self->main_stack), tab);
  if (g_str_equal (tab, "changes"))
    show_selected_change (self);
}

static GtkWidget *
build_toolbar_buttons (GdlWindow *self, AdwHeaderBar *bar)
{
  /* repository */
  self->repo_button = gtk_menu_button_new ();
  gtk_widget_add_css_class (self->repo_button, "flat");
  gtk_widget_add_css_class (self->repo_button, "toolbar-button");
  gtk_menu_button_set_always_show_arrow (GTK_MENU_BUTTON (self->repo_button), FALSE);
  gtk_menu_button_set_child (GTK_MENU_BUTTON (self->repo_button),
                             toolbar_content ("repo", "Current repository", TRUE, NULL, &self->repo_title, NULL));
  GtkWidget *add = gtk_menu_button_new ();
  gtk_menu_button_set_label (GTK_MENU_BUTTON (add), "Add");
  gtk_menu_button_set_always_show_arrow (GTK_MENU_BUTTON (add), TRUE);
  g_autoptr (GMenu) add_menu = g_menu_new ();
  g_menu_append (add_menu, "Clone repository…", "win.clone");
  g_menu_append (add_menu, "Create new repository…", "win.new-repo");
  g_menu_append (add_menu, "Add existing repository…", "win.add-repo");
  gtk_menu_button_set_menu_model (GTK_MENU_BUTTON (add), G_MENU_MODEL (add_menu));
  GtkWidget *repo_pop = filter_popover ("Filter repositories", add, &self->repo_search, &self->repo_list);
  gtk_menu_button_set_popover (GTK_MENU_BUTTON (self->repo_button), repo_pop);
  g_signal_connect_swapped (repo_pop, "show", G_CALLBACK (fill_repo_popover), self);
  g_signal_connect (self->repo_search, "search-changed", G_CALLBACK (on_filter_changed), self->repo_list);
  g_signal_connect (self->repo_search, "activate", G_CALLBACK (on_filter_activate), self->repo_list);
  g_signal_connect (self->repo_list, "row-activated", G_CALLBACK (on_repo_row_activated), self);

  /* branch */
  self->branch_button = gtk_menu_button_new ();
  gtk_widget_add_css_class (self->branch_button, "flat");
  gtk_widget_add_css_class (self->branch_button, "toolbar-button");
  gtk_menu_button_set_child (GTK_MENU_BUTTON (self->branch_button),
                             toolbar_content ("branch", "Current branch", TRUE, NULL, &self->branch_title, NULL));
  GtkWidget *new_branch = gtk_button_new_with_label ("New branch");
  gtk_actionable_set_action_name (GTK_ACTIONABLE (new_branch), "win.new-branch");
  GtkWidget *branch_pop = filter_popover ("Filter branches", new_branch, &self->branch_search, &self->branch_list);
  gtk_menu_button_set_popover (GTK_MENU_BUTTON (self->branch_button), branch_pop);
  g_signal_connect_swapped (branch_pop, "show", G_CALLBACK (fill_branch_popover), self);
  g_signal_connect_swapped (new_branch, "clicked", G_CALLBACK (gtk_popover_popdown), branch_pop);
  g_signal_connect (self->branch_search, "search-changed", G_CALLBACK (on_filter_changed), self->branch_list);
  g_signal_connect (self->branch_search, "activate", G_CALLBACK (on_filter_activate), self->branch_list);
  g_signal_connect (self->branch_list, "row-activated", G_CALLBACK (on_branch_row_activated), self);
  GtkGesture *rc = gtk_gesture_click_new ();
  gtk_gesture_single_set_button (GTK_GESTURE_SINGLE (rc), GDK_BUTTON_SECONDARY);
  g_signal_connect (rc, "pressed", G_CALLBACK (on_branch_right_click), self);
  gtk_widget_add_controller (self->branch_list, GTK_EVENT_CONTROLLER (rc));

  /* sync */
  self->sync_button = gtk_button_new ();
  gtk_widget_add_css_class (self->sync_button, "flat");
  gtk_widget_add_css_class (self->sync_button, "toolbar-button");
  gtk_actionable_set_action_name (GTK_ACTIONABLE (self->sync_button), "win.sync");
  GtkWidget *sync_box = toolbar_content ("sync", "Never fetched", FALSE, &self->sync_icon, &self->sync_title,
                                         &self->sync_caption);
  self->sync_spinner = adw_spinner_new ();
  gtk_widget_set_size_request (self->sync_spinner, 18, 18);
  gtk_widget_set_visible (self->sync_spinner, FALSE);
  gtk_box_prepend (GTK_BOX (sync_box), self->sync_spinner);
  gtk_button_set_child (GTK_BUTTON (self->sync_button), sync_box);

  GtkWidget *row = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 0);
  gtk_box_append (GTK_BOX (row), self->repo_button);
  GtkWidget *d1 = gtk_separator_new (GTK_ORIENTATION_VERTICAL);
  gtk_widget_add_css_class (d1, "toolbar-divider");
  gtk_box_append (GTK_BOX (row), d1);
  gtk_box_append (GTK_BOX (row), self->branch_button);
  GtkWidget *d2 = gtk_separator_new (GTK_ORIENTATION_VERTICAL);
  gtk_widget_add_css_class (d2, "toolbar-divider");
  gtk_box_append (GTK_BOX (row), d2);
  gtk_box_append (GTK_BOX (row), self->sync_button);
  adw_header_bar_pack_start (bar, row);

  /* main menu + profile (right) */
  GtkWidget *menu_button = gtk_menu_button_new ();
  gtk_menu_button_set_icon_name (GTK_MENU_BUTTON (menu_button), "open-menu-symbolic");
  gtk_menu_button_set_primary (GTK_MENU_BUTTON (menu_button), TRUE);
  gtk_widget_set_tooltip_text (menu_button, "Main menu");
  g_autoptr (GMenu) menu = g_menu_new ();
  g_autoptr (GMenu) repo_sec = g_menu_new (), branch_sec = g_menu_new (), app_sec = g_menu_new ();
  g_menu_append (repo_sec, "Push", "win.push");
  g_menu_append (repo_sec, "Pull", "win.pull");
  g_menu_append (repo_sec, "Fetch", "win.fetch");
  g_menu_append (repo_sec, "Open in external editor", "win.open-editor");
  g_menu_append (repo_sec, "Open in terminal", "win.open-terminal");
  g_menu_append (repo_sec, "Show in file manager", "win.file-manager");
  g_menu_append (repo_sec, "Remove from list", "win.remove-repo");
  g_menu_append (branch_sec, "New branch…", "win.new-branch");
  g_menu_append (branch_sec, "Rename branch…", "win.rename-branch");
  g_menu_append (branch_sec, "Delete branch…", "win.delete-branch");
  g_menu_append (branch_sec, "Merge into current branch…", "win.merge");
  g_menu_append (branch_sec, "Stash all changes", "win.stash");
  g_menu_append (branch_sec, "Discard all changes…", "win.discard-all");
  g_menu_append (app_sec, "Preferences", "win.preferences");
  g_menu_append (app_sec, "Keyboard Shortcuts", "app.shortcuts");
  g_menu_append (app_sec, "About Git Desktop For Linux", "app.about");
  g_menu_append_submenu (menu, "Repository", G_MENU_MODEL (repo_sec));
  g_menu_append_submenu (menu, "Branch", G_MENU_MODEL (branch_sec));
  g_menu_append_section (menu, NULL, G_MENU_MODEL (app_sec));
  gtk_menu_button_set_menu_model (GTK_MENU_BUTTON (menu_button), G_MENU_MODEL (menu));

  self->profile_button = gtk_menu_button_new ();
  gtk_widget_add_css_class (self->profile_button, "flat");
  gtk_widget_add_css_class (self->profile_button, "circular");
  self->profile_avatar = adw_avatar_new (28, NULL, FALSE);
  gtk_menu_button_set_child (GTK_MENU_BUTTON (self->profile_button), self->profile_avatar);
  GtkWidget *acc_pop = gtk_popover_new ();
  self->account_box = gtk_box_new (GTK_ORIENTATION_VERTICAL, 10);
  gtk_widget_add_css_class (self->account_box, "account-card");
  gtk_popover_set_child (GTK_POPOVER (acc_pop), self->account_box);
  gtk_menu_button_set_popover (GTK_MENU_BUTTON (self->profile_button), acc_pop);

  adw_header_bar_pack_end (bar, menu_button);
  adw_header_bar_pack_end (bar, self->profile_button);
  return row;
}

static gboolean
description_empty (GBinding *b, const GValue *from, GValue *to, gpointer data)
{
  const char *text = g_value_get_string (from);
  g_value_set_boolean (to, !text || !*text);
  return TRUE;
}

static GtkWidget *
build_sidebar (GdlWindow *self)
{
  GtkWidget *side = gtk_box_new (GTK_ORIENTATION_VERTICAL, 0);
  gtk_widget_add_css_class (side, "gdl-sidebar");
  gtk_widget_set_size_request (side, 300, -1);

  self->tabs = ADW_TOGGLE_GROUP (adw_toggle_group_new ());
  AdwToggle *t1 = adw_toggle_new (), *t2 = adw_toggle_new ();
  adw_toggle_set_name (t1, "changes");
  adw_toggle_set_label (t1, "Changes");
  adw_toggle_set_name (t2, "history");
  adw_toggle_set_label (t2, "History");
  adw_toggle_group_add (self->tabs, t1);
  adw_toggle_group_add (self->tabs, t2);
  adw_toggle_group_set_active_name (self->tabs, "changes");
  adw_toggle_group_set_homogeneous (self->tabs, TRUE);
  gtk_widget_add_css_class (GTK_WIDGET (self->tabs), "round");
  gtk_widget_set_margin_start (GTK_WIDGET (self->tabs), 12);
  gtk_widget_set_margin_end (GTK_WIDGET (self->tabs), 12);
  gtk_widget_set_margin_top (GTK_WIDGET (self->tabs), 12);
  gtk_widget_set_margin_bottom (GTK_WIDGET (self->tabs), 6);
  g_signal_connect_swapped (self->tabs, "notify::active-name", G_CALLBACK (on_tab_changed), self);
  gtk_box_append (GTK_BOX (side), GTK_WIDGET (self->tabs));

  self->side_stack = gtk_stack_new ();
  gtk_stack_set_transition_type (GTK_STACK (self->side_stack), GTK_STACK_TRANSITION_TYPE_CROSSFADE);
  gtk_widget_set_vexpand (self->side_stack, TRUE);

  /* ---- changes page ---- */
  GtkWidget *changes = gtk_box_new (GTK_ORIENTATION_VERTICAL, 0);
  GtkWidget *header = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 8);
  gtk_widget_set_margin_start (header, 18);
  gtk_widget_set_margin_end (header, 12);
  gtk_widget_set_margin_top (header, 4);
  gtk_widget_set_margin_bottom (header, 4);
  self->select_all = gtk_check_button_new ();
  gtk_widget_set_tooltip_text (self->select_all, "Include all files");
  g_signal_connect (self->select_all, "toggled", G_CALLBACK (on_select_all_toggled), self);
  gtk_box_append (GTK_BOX (header), self->select_all);
  self->files_count = label_new ("0 changed files", "dim-label", 0);
  gtk_box_append (GTK_BOX (header), self->files_count);
  gtk_box_append (GTK_BOX (changes), header);

  self->files_stack = gtk_stack_new ();
  gtk_widget_set_vexpand (self->files_stack, TRUE);
  GtkWidget *scroll = gtk_scrolled_window_new ();
  gtk_scrolled_window_set_policy (GTK_SCROLLED_WINDOW (scroll), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
  self->files_list = gtk_list_box_new ();
  gtk_widget_add_css_class (self->files_list, "navigation-sidebar");
  g_signal_connect (self->files_list, "row-selected", G_CALLBACK (on_file_selected), self);
  GtkGesture *rc = gtk_gesture_click_new ();
  gtk_gesture_single_set_button (GTK_GESTURE_SINGLE (rc), GDK_BUTTON_SECONDARY);
  g_signal_connect (rc, "pressed", G_CALLBACK (on_file_right_click), self);
  gtk_widget_add_controller (self->files_list, GTK_EVENT_CONTROLLER (rc));
  gtk_scrolled_window_set_child (GTK_SCROLLED_WINDOW (scroll), self->files_list);
  gtk_stack_add_named (GTK_STACK (self->files_stack), scroll, "list");
  GtkWidget *empty = adw_status_page_new ();
  adw_status_page_set_icon_name (ADW_STATUS_PAGE (empty), "object-select-symbolic");
  adw_status_page_set_title (ADW_STATUS_PAGE (empty), "No local changes");
  gtk_widget_add_css_class (empty, "compact");
  gtk_stack_add_named (GTK_STACK (self->files_stack), empty, "empty");
  gtk_box_append (GTK_BOX (changes), self->files_stack);

  /* banners */
  GtkWidget *banners = gtk_box_new (GTK_ORIENTATION_VERTICAL, 6);
  gtk_widget_set_margin_start (banners, 10);
  gtk_widget_set_margin_end (banners, 10);
  gtk_widget_set_margin_bottom (banners, 8);
  self->merge_banner = banner_new ("alert", TRUE, &self->merge_label, "Abort merge", "win.abort-merge", NULL, NULL);
  gtk_label_set_markup (GTK_LABEL (self->merge_label), "<b>Merge in progress</b>\nResolve the conflicts, then commit.");
  GtkWidget *stash_label;
  self->stash_banner = banner_new ("box", FALSE, &stash_label, "Restore", "win.restore-stash", "Discard", "win.discard-stash");
  gtk_label_set_markup (GTK_LABEL (stash_label), "<b>Stashed changes</b>\nsaved on this branch");
  self->undo_banner = banner_new ("commit", FALSE, &self->undo_label, "Undo", "win.undo-commit", NULL, NULL);
  gtk_box_append (GTK_BOX (banners), self->merge_banner);
  gtk_box_append (GTK_BOX (banners), self->stash_banner);
  gtk_box_append (GTK_BOX (banners), self->undo_banner);
  gtk_box_append (GTK_BOX (changes), banners);

  /* commit box */
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_VERTICAL, 8);
  gtk_widget_add_css_class (box, "commit-box");
  GtkWidget *row = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 8);
  self->author_avatar = adw_avatar_new (32, NULL, TRUE);
  gtk_box_append (GTK_BOX (row), self->author_avatar);
  self->summary_entry = gtk_entry_new ();
  gtk_entry_set_placeholder_text (GTK_ENTRY (self->summary_entry), "Summary (required)");
  gtk_widget_set_hexpand (self->summary_entry, TRUE);
  g_signal_connect (self->summary_entry, "changed", G_CALLBACK (on_summary_changed), self);
  g_signal_connect_swapped (self->summary_entry, "activate", G_CALLBACK (do_commit), self);
  gtk_box_append (GTK_BOX (row), self->summary_entry);
  gtk_box_append (GTK_BOX (box), row);
  GtkWidget *frame = gtk_scrolled_window_new ();
  gtk_widget_add_css_class (frame, "description-frame");
  gtk_widget_set_size_request (frame, -1, 84);
  self->description_view = gtk_text_view_new ();
  gtk_text_view_set_wrap_mode (GTK_TEXT_VIEW (self->description_view), GTK_WRAP_WORD_CHAR);
  gtk_text_view_set_accepts_tab (GTK_TEXT_VIEW (self->description_view), FALSE);
  gtk_scrolled_window_set_child (GTK_SCROLLED_WINDOW (frame), self->description_view);
  /* GtkTextView has no placeholder: overlay a dim label while it is empty */
  GtkWidget *overlay = gtk_overlay_new ();
  gtk_overlay_set_child (GTK_OVERLAY (overlay), frame);
  GtkWidget *hint = label_new ("Description", "dim-label", 0);
  gtk_widget_set_valign (hint, GTK_ALIGN_START);
  gtk_widget_set_halign (hint, GTK_ALIGN_START);
  gtk_widget_set_margin_start (hint, 10);
  gtk_widget_set_margin_top (hint, 7);
  gtk_widget_set_can_target (hint, FALSE);
  gtk_overlay_add_overlay (GTK_OVERLAY (overlay), hint);
  GtkTextBuffer *dbuf = gtk_text_view_get_buffer (GTK_TEXT_VIEW (self->description_view));
  g_object_bind_property_full (dbuf, "text", hint, "visible", G_BINDING_SYNC_CREATE,
                               description_empty, NULL, NULL, NULL);
  gtk_box_append (GTK_BOX (box), overlay);
  self->commit_button = gtk_button_new_with_label ("Commit to main");
  gtk_widget_add_css_class (self->commit_button, "suggested-action");
  gtk_widget_add_css_class (self->commit_button, "pill");
  gtk_widget_set_tooltip_text (self->commit_button, "Ctrl+Enter");
  g_signal_connect_swapped (self->commit_button, "clicked", G_CALLBACK (do_commit), self);
  gtk_box_append (GTK_BOX (box), self->commit_button);
  gtk_box_append (GTK_BOX (changes), box);
  gtk_stack_add_named (GTK_STACK (self->side_stack), changes, "changes");

  /* ---- history page ---- */
  self->history_scroller = gtk_scrolled_window_new ();
  gtk_scrolled_window_set_policy (GTK_SCROLLED_WINDOW (self->history_scroller), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
  self->history_list = gtk_list_box_new ();
  gtk_widget_add_css_class (self->history_list, "navigation-sidebar");
  g_signal_connect (self->history_list, "row-selected", G_CALLBACK (on_history_selected), self);
  g_signal_connect (self->history_scroller, "edge-reached", G_CALLBACK (on_history_edge), self);
  gtk_scrolled_window_set_child (GTK_SCROLLED_WINDOW (self->history_scroller), self->history_list);
  gtk_stack_add_named (GTK_STACK (self->side_stack), self->history_scroller, "history");

  gtk_box_append (GTK_BOX (side), self->side_stack);
  return side;
}

static GtkWidget *
build_commit_pane (GdlWindow *self)
{
  GtkWidget *pane = gtk_box_new (GTK_ORIENTATION_VERTICAL, 0);
  GtkWidget *header = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 12);
  gtk_widget_add_css_class (header, "pane-header");
  self->commit_avatar = adw_avatar_new (40, NULL, TRUE);
  gtk_widget_set_valign (self->commit_avatar, GTK_ALIGN_START);
  gtk_box_append (GTK_BOX (header), self->commit_avatar);
  GtkWidget *texts = gtk_box_new (GTK_ORIENTATION_VERTICAL, 3);
  gtk_widget_set_hexpand (texts, TRUE);
  self->commit_title = label_new ("", "commit-title", 0);
  gtk_label_set_wrap (GTK_LABEL (self->commit_title), TRUE);
  gtk_label_set_selectable (GTK_LABEL (self->commit_title), TRUE);
  self->commit_body = label_new ("", NULL, 0);
  gtk_label_set_wrap (GTK_LABEL (self->commit_body), TRUE);
  gtk_label_set_selectable (GTK_LABEL (self->commit_body), TRUE);
  self->commit_meta = label_new ("", "dim-label", 0);
  gtk_label_set_selectable (GTK_LABEL (self->commit_meta), TRUE);
  gtk_label_set_ellipsize (GTK_LABEL (self->commit_meta), PANGO_ELLIPSIZE_END);
  gtk_box_append (GTK_BOX (texts), self->commit_title);
  gtk_box_append (GTK_BOX (texts), self->commit_body);
  gtk_box_append (GTK_BOX (texts), self->commit_meta);
  gtk_box_append (GTK_BOX (header), texts);
  GtkWidget *copy = gtk_button_new ();
  GtkWidget *cb = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 6);
  gtk_box_append (GTK_BOX (cb), gdl_icon_new ("copy", 16));
  gtk_box_append (GTK_BOX (cb), gtk_label_new ("Copy SHA"));
  gtk_button_set_child (GTK_BUTTON (copy), cb);
  gtk_widget_set_valign (copy, GTK_ALIGN_START);
  gtk_actionable_set_action_name (GTK_ACTIONABLE (copy), "win.copy-sha");
  gtk_box_append (GTK_BOX (header), copy);
  gtk_box_append (GTK_BOX (pane), header);

  GtkWidget *paned = gtk_paned_new (GTK_ORIENTATION_HORIZONTAL);
  gtk_paned_set_position (GTK_PANED (paned), 280);
  gtk_paned_set_shrink_start_child (GTK_PANED (paned), FALSE);
  gtk_widget_set_vexpand (paned, TRUE);
  GtkWidget *files = gtk_box_new (GTK_ORIENTATION_VERTICAL, 4);
  gtk_widget_add_css_class (files, "gdl-sidebar");
  self->commit_count = label_new ("", "dim-label", 0);
  gtk_widget_set_margin_start (self->commit_count, 18);
  gtk_widget_set_margin_top (self->commit_count, 10);
  gtk_box_append (GTK_BOX (files), self->commit_count);
  GtkWidget *scroll = gtk_scrolled_window_new ();
  gtk_scrolled_window_set_policy (GTK_SCROLLED_WINDOW (scroll), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
  gtk_widget_set_vexpand (scroll, TRUE);
  self->commit_files = gtk_list_box_new ();
  gtk_widget_add_css_class (self->commit_files, "navigation-sidebar");
  g_signal_connect (self->commit_files, "row-selected", G_CALLBACK (on_commit_file_selected), self);
  gtk_scrolled_window_set_child (GTK_SCROLLED_WINDOW (scroll), self->commit_files);
  gtk_box_append (GTK_BOX (files), scroll);
  gtk_paned_set_start_child (GTK_PANED (paned), files);
  self->commit_diff = GDL_DIFF_VIEW (gdl_diff_view_new (FALSE));
  gtk_paned_set_end_child (GTK_PANED (paned), GTK_WIDGET (self->commit_diff));
  gtk_box_append (GTK_BOX (pane), paned);
  return pane;
}

static GtkWidget *
build_blank (void)
{
  GtkWidget *page = adw_status_page_new ();
  adw_status_page_set_icon_name (ADW_STATUS_PAGE (page), "starred-symbolic");
  adw_status_page_set_title (ADW_STATUS_PAGE (page), "Let's get started!");
  adw_status_page_set_description (ADW_STATUS_PAGE (page), "Add a repository to Git Desktop to start collaborating.");
  GtkWidget *cards = gtk_box_new (GTK_ORIENTATION_VERTICAL, 8);
  gtk_box_append (GTK_BOX (cards), gdl_action_card_new ("cloud-down", "Clone a repository from the Internet", "Ctrl+Shift+O", "win.clone"));
  gtk_box_append (GTK_BOX (cards), gdl_action_card_new ("plus", "Create a new repository", "Ctrl+N", "win.new-repo"));
  gtk_box_append (GTK_BOX (cards), gdl_action_card_new ("folder", "Add an existing repository", "Ctrl+O", "win.add-repo"));
  adw_status_page_set_child (ADW_STATUS_PAGE (page), cards);
  return page;
}

static void
on_active_changed (GdlWindow *self)
{
  /* GitHub Desktop re-reads the status whenever the window gets focus */
  if (gtk_window_is_active (GTK_WINDOW (self)) && self->repo)
    gdl_window_refresh (self, FALSE);
}

static gboolean
on_close_request (GdlWindow *self)
{
  int w = 0, h = 0;
  gtk_window_get_default_size (GTK_WINDOW (self), &w, &h);
  g_autofree char *size = g_strdup_printf ("%dx%d", w, h);
  settings_set_string ("window_size", size);
  settings_set_bool ("window_maximized", gtk_window_is_maximized (GTK_WINDOW (self)));
  return FALSE;
}

static void
gdl_window_dispose (GObject *obj)
{
  GdlWindow *self = GDL_WINDOW (obj);
  if (self->fetch_timer) {
    g_source_remove (self->fetch_timer);
    self->fetch_timer = 0;
  }
  /* lists emit row-selected while being destroyed: make the handlers no-ops */
  self->tabs = NULL;
  g_clear_pointer (&self->repo, gdl_repo_free);
  G_OBJECT_CLASS (gdl_window_parent_class)->dispose (obj);
}

static void
gdl_window_finalize (GObject *obj)
{
  GdlWindow *self = GDL_WINDOW (obj);
  gdl_repo_free (self->repo);
  if (self->files)
    g_ptr_array_unref (self->files);
  g_hash_table_unref (self->unchecked);
  g_free (self->head_hash);
  g_free (self->undo_hash);
  g_free (self->undo_summary);
  g_free (self->undo_description);
  g_free (self->sync_mode);
  g_free (self->shown_commit);
  gdl_account_free (self->account);
  g_clear_object (&self->avatar);
  G_OBJECT_CLASS (gdl_window_parent_class)->finalize (obj);
}

static void
gdl_window_class_init (GdlWindowClass *klass)
{
  G_OBJECT_CLASS (klass)->dispose = gdl_window_dispose;
  G_OBJECT_CLASS (klass)->finalize = gdl_window_finalize;
}

static void
gdl_window_init (GdlWindow *self)
{
  self->unchecked = g_hash_table_new_full (g_str_hash, g_str_equal, g_free, NULL);
  self->account_loading = TRUE;
  g_action_map_add_action_entries (G_ACTION_MAP (self), WIN_ACTIONS, G_N_ELEMENTS (WIN_ACTIONS), self);

  int w = 1200, h = 780;
  g_autofree char *size = settings_get_string ("window_size");
  if (size)
    sscanf (size, "%dx%d", &w, &h);
  gtk_window_set_default_size (GTK_WINDOW (self), MAX (w, 800), MAX (h, 560));
  if (settings_get_bool ("window_maximized", FALSE))
    gtk_window_maximize (GTK_WINDOW (self));

  GtkWidget *view = adw_toolbar_view_new ();
  GtkWidget *bar = adw_header_bar_new ();
  adw_header_bar_set_show_title (ADW_HEADER_BAR (bar), FALSE);
  build_toolbar_buttons (self, ADW_HEADER_BAR (bar));
  adw_toolbar_view_add_top_bar (ADW_TOOLBAR_VIEW (view), bar);

  GtkWidget *paned = gtk_paned_new (GTK_ORIENTATION_HORIZONTAL);
  gtk_paned_set_position (GTK_PANED (paned), 340);
  gtk_paned_set_shrink_start_child (GTK_PANED (paned), FALSE);
  gtk_paned_set_resize_start_child (GTK_PANED (paned), FALSE);
  gtk_paned_set_start_child (GTK_PANED (paned), build_sidebar (self));

  self->main_stack = gtk_stack_new ();
  gtk_stack_set_transition_type (GTK_STACK (self->main_stack), GTK_STACK_TRANSITION_TYPE_CROSSFADE);
  self->diff = GDL_DIFF_VIEW (gdl_diff_view_new (TRUE));
  g_signal_connect_swapped (self->diff, "open-in-editor", G_CALLBACK (open_in_editor), self);
  gtk_stack_add_named (GTK_STACK (self->main_stack), GTK_WIDGET (self->diff), "changes");
  gtk_stack_add_named (GTK_STACK (self->main_stack), build_commit_pane (self), "history");
  self->blank = build_blank ();
  gtk_stack_add_named (GTK_STACK (self->main_stack), self->blank, "blank");
  gtk_paned_set_end_child (GTK_PANED (paned), self->main_stack);

  adw_toolbar_view_set_content (ADW_TOOLBAR_VIEW (view), paned);
  self->toasts = ADW_TOAST_OVERLAY (adw_toast_overlay_new ());
  adw_toast_overlay_set_child (self->toasts, view);
  adw_application_window_set_content (ADW_APPLICATION_WINDOW (self), GTK_WIDGET (self->toasts));

  g_signal_connect (self, "notify::is-active", G_CALLBACK (on_active_changed), NULL);
  g_signal_connect (self, "close-request", G_CALLBACK (on_close_request), NULL);
  self->fetch_timer = g_timeout_add_seconds (AUTO_FETCH_SECONDS, auto_fetch, self);
  fill_account_box (self);
}

GdlWindow *
gdl_window_new (AdwApplication *app, const char *repo_path)
{
  GdlWindow *self = g_object_new (GDL_TYPE_WINDOW, "application", app, NULL);
  g_autofree char *last = settings_get_string ("last_repo");
  g_autoptr (GPtrArray) recent = settings_recent ();
  const char *path = repo_path ? repo_path : last ? last : recent->len ? g_ptr_array_index (recent, 0) : NULL;
  gdl_window_open_repository (self, path);
  gdl_window_reload_account (self);
  return self;
}

/* ================================================================== */
/* Theme & screenshots                                                 */
/* ================================================================== */

void
gdl_window_apply_theme (void)
{
  g_autofree char *theme = settings_get_string ("theme");
  AdwColorScheme scheme = ADW_COLOR_SCHEME_DEFAULT;
  if (g_strcmp0 (theme, "light") == 0)
    scheme = ADW_COLOR_SCHEME_FORCE_LIGHT;
  else if (g_strcmp0 (theme, "dark") == 0)
    scheme = ADW_COLOR_SCHEME_FORCE_DARK;
  adw_style_manager_set_color_scheme (adw_style_manager_get_default (), scheme);
}

typedef struct {
  GdlWindow *self;
  char      *path;
  char      *view;
} Shot;

static gboolean
take_screenshot (gpointer data)
{
  Shot *shot = data;
  GtkWidget *widget = GTK_WIDGET (shot->self);
  GtkWidget *button = g_strcmp0 (shot->view, "branches") == 0 ? shot->self->branch_button
                    : g_strcmp0 (shot->view, "repos") == 0 ? shot->self->repo_button
                    : g_strcmp0 (shot->view, "account") == 0 ? shot->self->profile_button : NULL;
  if (button)  /* popovers are separate surfaces: capture the popover itself */
    widget = GTK_WIDGET (gtk_menu_button_get_popover (GTK_MENU_BUTTON (button)));
  g_autoptr (GdkPaintable) paintable = gtk_widget_paintable_new (widget);
  int w = gtk_widget_get_width (widget), h = gtk_widget_get_height (widget);
  g_autoptr (GtkSnapshot) snapshot = gtk_snapshot_new ();
  gdk_paintable_snapshot (paintable, snapshot, w, h);
  g_autoptr (GskRenderNode) node = gtk_snapshot_to_node (snapshot);
  GskRenderer *renderer = gtk_native_get_renderer (GTK_NATIVE (widget));
  if (!renderer || w <= 0 || h <= 0) {
    g_printerr ("screenshot: target not mapped (%dx%d), capturing the window instead\n", w, h);
    widget = GTK_WIDGET (shot->self);
    g_clear_object (&paintable);
    paintable = gtk_widget_paintable_new (widget);
    w = gtk_widget_get_width (widget);
    h = gtk_widget_get_height (widget);
    g_clear_object (&snapshot);
    snapshot = gtk_snapshot_new ();
    gdk_paintable_snapshot (paintable, snapshot, w, h);
    g_clear_pointer (&node, gsk_render_node_unref);
    node = gtk_snapshot_to_node (snapshot);
    renderer = gtk_native_get_renderer (GTK_NATIVE (widget));
  }
  if (node && renderer) {
    g_autoptr (GdkTexture) tex = gsk_renderer_render_texture (renderer, node, &GRAPHENE_RECT_INIT (0, 0, w, h));
    gdk_texture_save_to_png (tex, shot->path);
    g_print ("screenshot: %s\n", shot->path);
  }
  /* an open dialog would block close-request: quit the app outright */
  g_application_quit (G_APPLICATION (gtk_window_get_application (GTK_WINDOW (shot->self))));
  g_free (shot->path);
  g_free (shot->view);
  g_free (shot);
  return G_SOURCE_REMOVE;
}

static gboolean
prepare_screenshot (gpointer data)
{
  Shot *shot = data;
  GdlWindow *self = shot->self;
  if (g_strcmp0 (shot->view, "history") == 0)
    adw_toggle_group_set_active_name (self->tabs, "history");
  else if (g_strcmp0 (shot->view, "branches") == 0)
    gtk_menu_button_popup (GTK_MENU_BUTTON (self->branch_button));
  else if (g_strcmp0 (shot->view, "repos") == 0)
    gtk_menu_button_popup (GTK_MENU_BUTTON (self->repo_button));
  else if (g_strcmp0 (shot->view, "account") == 0)
    gtk_menu_button_popup (GTK_MENU_BUTTON (self->profile_button));
  else if (g_strcmp0 (shot->view, "clone") == 0)
    gtk_widget_activate_action (GTK_WIDGET (self), "win.clone", NULL);
  else if (g_strcmp0 (shot->view, "prefs") == 0)
    gtk_widget_activate_action (GTK_WIDGET (self), "win.preferences", NULL);
  else if (g_strcmp0 (shot->view, "signin") == 0)
    gtk_widget_activate_action (GTK_WIDGET (self), "win.sign-in", NULL);
  else if (g_strcmp0 (shot->view, "newbranch") == 0)
    gtk_widget_activate_action (GTK_WIDGET (self), "win.new-branch", NULL);
  g_timeout_add (1200, take_screenshot, shot);
  return G_SOURCE_REMOVE;
}

void
gdl_window_screenshot (GdlWindow *self, const char *png_path, const char *view)
{
  Shot *shot = g_new0 (Shot, 1);
  shot->self = self;
  shot->path = g_strdup (png_path);
  shot->view = g_strdup (view);
  g_timeout_add (1500, prepare_screenshot, shot);
}
