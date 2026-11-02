#include "dialogs.h"

#include "icons.h"
#include "net.h"
#include "settings.h"
#include "util.h"

#include <string.h>

static GtkWidget *
dim_label (const char *text)
{
  GtkWidget *l = gtk_label_new (text);
  gtk_label_set_xalign (GTK_LABEL (l), 0);
  gtk_label_set_wrap (GTK_LABEL (l), TRUE);
  gtk_widget_add_css_class (l, "dim-label");
  return l;
}

static GtkWidget *
error_label (void)
{
  GtkWidget *l = gtk_label_new (NULL);
  gtk_label_set_xalign (GTK_LABEL (l), 0);
  gtk_label_set_wrap (GTK_LABEL (l), TRUE);
  gtk_label_set_selectable (GTK_LABEL (l), TRUE);
  gtk_widget_add_css_class (l, "error");
  gtk_widget_set_visible (l, FALSE);
  return l;
}

static void
show_error (GtkWidget *label, const char *text)
{
  gtk_label_set_text (GTK_LABEL (label), text);
  gtk_widget_set_visible (label, text && *text);
}

static char *
default_parent_dir (void)
{
  g_autofree char *git = g_build_filename (g_get_home_dir (), "Git", NULL);
  return g_strdup (g_file_test (git, G_FILE_TEST_IS_DIR) ? git : g_get_home_dir ());
}

/* Dialog with a header bar, scrollable body and a bottom button row */
static AdwDialog *
dialog_new (const char *title, int width, int height, GtkWidget **body_out, GtkWidget **buttons_out)
{
  AdwDialog *d = adw_dialog_new ();
  adw_dialog_set_title (d, title);
  adw_dialog_set_content_width (d, width);
  if (height > 0)
    adw_dialog_set_content_height (d, height);
  GtkWidget *view = adw_toolbar_view_new ();
  adw_toolbar_view_add_top_bar (ADW_TOOLBAR_VIEW (view), adw_header_bar_new ());
  GtkWidget *body = gtk_box_new (GTK_ORIENTATION_VERTICAL, 12);
  gtk_widget_set_margin_start (body, 18);
  gtk_widget_set_margin_end (body, 18);
  gtk_widget_set_margin_top (body, 6);
  gtk_widget_set_margin_bottom (body, 18);
  GtkWidget *buttons = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 8);
  gtk_widget_set_halign (buttons, GTK_ALIGN_END);
  GtkWidget *outer = gtk_box_new (GTK_ORIENTATION_VERTICAL, 12);
  gtk_widget_set_vexpand (body, TRUE);
  gtk_box_append (GTK_BOX (outer), body);
  gtk_widget_set_margin_start (buttons, 18);
  gtk_widget_set_margin_end (buttons, 18);
  gtk_widget_set_margin_bottom (buttons, 18);
  gtk_box_append (GTK_BOX (outer), buttons);
  adw_toolbar_view_set_content (ADW_TOOLBAR_VIEW (view), outer);
  adw_dialog_set_child (d, view);
  *body_out = body;
  *buttons_out = buttons;
  return d;
}

static GtkWidget *
primary_button (const char *label)
{
  GtkWidget *b = gtk_button_new_with_label (label);
  gtk_widget_add_css_class (b, "suggested-action");
  gtk_widget_add_css_class (b, "pill");
  return b;
}

/* "Local path" row with a Choose… button */
typedef struct {
  GtkWidget *row;
  GtkWindow *parent;
} PathRow;

static void
on_folder_chosen (GObject *src, GAsyncResult *res, gpointer data)
{
  GtkWidget *row = data;
  g_autoptr (GFile) folder = gtk_file_dialog_select_folder_finish (GTK_FILE_DIALOG (src), res, NULL);
  if (folder) {
    g_autofree char *path = g_file_get_path (folder);
    gtk_editable_set_text (GTK_EDITABLE (row), path);
  }
  g_object_unref (row);
}

static void
on_choose_folder (GtkButton *b, GtkWidget *row)
{
  g_autoptr (GtkFileDialog) fd = gtk_file_dialog_new ();
  gtk_file_dialog_set_title (fd, "Choose a folder");
  const char *current = gtk_editable_get_text (GTK_EDITABLE (row));
  if (current && *current) {
    g_autofree char *dir = g_file_test (current, G_FILE_TEST_IS_DIR) ? g_strdup (current) : g_path_get_dirname (current);
    g_autoptr (GFile) f = g_file_new_for_path (dir);
    gtk_file_dialog_set_initial_folder (fd, f);
  }
  gtk_file_dialog_select_folder (fd, GTK_WINDOW (gtk_widget_get_root (GTK_WIDGET (b))), NULL, on_folder_chosen,
                                 g_object_ref (row));
}

static GtkWidget *
path_row (const char *title, const char *initial)
{
  GtkWidget *row = adw_entry_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (row), title);
  gtk_editable_set_text (GTK_EDITABLE (row), initial);
  GtkWidget *b = gtk_button_new_with_label ("Choose…");
  gtk_widget_set_valign (b, GTK_ALIGN_CENTER);
  gtk_widget_add_css_class (b, "flat");
  g_signal_connect (b, "clicked", G_CALLBACK (on_choose_folder), row);
  adw_entry_row_add_suffix (ADW_ENTRY_ROW (row), b);
  return row;
}

/* ================================================================== */
/* Clone                                                               */
/* ================================================================== */

typedef struct {
  GdlWindow  *win;
  AdwDialog  *dialog;
  GtkWidget  *stack, *search, *owners, *list, *status, *url, *path, *error, *clone_button, *spinner;
  GdlAccount *account;   /* own copy when reloaded here */
  GPtrArray  *repos;     /* borrowed */
  char       *preselect;
  char       *parent_dir;
  gboolean    path_edited;
} CloneUi;

static void
clone_ui_free (CloneUi *ui)
{
  gdl_account_free (ui->account);
  g_free (ui->preselect);
  g_free (ui->parent_dir);
  g_free (ui);
}

static GdlGhRepo *
selected_repo (CloneUi *ui)
{
  GtkListBoxRow *row = gtk_list_box_get_selected_row (GTK_LIST_BOX (ui->list));
  return row ? g_object_get_data (G_OBJECT (row), "repo") : NULL;
}

static char *
clone_url (CloneUi *ui)
{
  if (g_str_equal (gtk_stack_get_visible_child_name (GTK_STACK (ui->stack)), "github")) {
    GdlGhRepo *r = selected_repo (ui);
    return r ? g_strdup (r->clone_url) : NULL;
  }
  const char *text = gtk_editable_get_text (GTK_EDITABLE (ui->url));
  return *text ? gdl_expand_clone_url (text) : NULL;
}

static void
suggest_path (CloneUi *ui)
{
  g_autofree char *url = clone_url (ui);
  GdlGhRepo *r = g_str_equal (gtk_stack_get_visible_child_name (GTK_STACK (ui->stack)), "github") ? selected_repo (ui) : NULL;
  g_autofree char *name = r ? g_strdup (r->name) : url ? gdl_clone_dir_name (url) : NULL;
  if (name && *name) {
    g_autofree char *path = g_build_filename (ui->parent_dir, name, NULL);
    gtk_editable_set_text (GTK_EDITABLE (ui->path), path);
  }
  gtk_widget_set_sensitive (ui->clone_button, url != NULL);
}

static GtkWidget *
repo_row (GdlGhRepo *r)
{
  GtkWidget *row = gtk_list_box_row_new ();
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 12);
  gtk_widget_set_margin_top (box, 6);
  gtk_widget_set_margin_bottom (box, 6);
  gtk_widget_set_margin_start (box, 8);
  gtk_widget_set_margin_end (box, 8);
  GtkWidget *ic = gdl_icon_new (r->is_private ? "lock" : "repo", 16);
  gtk_widget_add_css_class (ic, r->is_private ? "warning" : "accent");
  gtk_box_append (GTK_BOX (box), ic);
  GtkWidget *texts = gtk_box_new (GTK_ORIENTATION_VERTICAL, 1);
  gtk_widget_set_hexpand (texts, TRUE);
  GtkWidget *name = gtk_label_new (r->name);
  gtk_label_set_xalign (GTK_LABEL (name), 0);
  gtk_widget_add_css_class (name, "heading");
  gtk_label_set_ellipsize (GTK_LABEL (name), PANGO_ELLIPSIZE_END);
  gtk_box_append (GTK_BOX (texts), name);
  if (*r->description) {
    GtkWidget *desc = gtk_label_new (r->description);
    gtk_label_set_xalign (GTK_LABEL (desc), 0);
    gtk_widget_add_css_class (desc, "dim-label");
    gtk_label_set_ellipsize (GTK_LABEL (desc), PANGO_ELLIPSIZE_END);
    gtk_box_append (GTK_BOX (texts), desc);
  }
  gtk_box_append (GTK_BOX (box), texts);
  const char *tags[] = { r->is_archived ? "Archived" : NULL, r->is_fork ? "Fork" : NULL, r->is_private ? "Private" : NULL };
  for (guint i = 0; i < G_N_ELEMENTS (tags); i++) {
    if (!tags[i])
      continue;
    GtkWidget *t = gtk_label_new (tags[i]);
    gtk_widget_add_css_class (t, "tag");
    gtk_widget_set_valign (t, GTK_ALIGN_CENTER);
    gtk_box_append (GTK_BOX (box), t);
  }
  GtkWidget *date = gtk_label_new (r->updated_at);
  gtk_widget_add_css_class (date, "dim-label");
  gtk_box_append (GTK_BOX (box), date);
  gtk_list_box_row_set_child (GTK_LIST_BOX_ROW (row), box);
  gtk_widget_set_tooltip_text (row, r->full_name);
  g_object_set_data (G_OBJECT (row), "repo", r);
  return row;
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
compare_repo_owner (gconstpointer a, gconstpointer b, gpointer me)
{
  const GdlGhRepo *ra = *(GdlGhRepo **) a, *rb = *(GdlGhRepo **) b;
  gboolean ma = me && g_ascii_strcasecmp (ra->owner, me) == 0, mb = me && g_ascii_strcasecmp (rb->owner, me) == 0;
  if (ma != mb)
    return ma ? -1 : 1;
  return g_ascii_strcasecmp (ra->owner, rb->owner);
}

static const char *
me_login (CloneUi *ui)
{
  GdlAccount *a = ui->account ? ui->account : gdl_window_get_account (ui->win);
  return a && a->profile ? a->profile->login : NULL;
}

static void
fill_repo_list (CloneUi *ui)
{
  GtkWidget *child;
  while ((child = gtk_widget_get_first_child (ui->list)))
    gtk_list_box_remove (GTK_LIST_BOX (ui->list), child);
  if (!ui->repos)
    return;
  g_autofree char *q = g_utf8_casefold (gtk_editable_get_text (GTK_EDITABLE (ui->search)), -1);
  guint owner_idx = gtk_drop_down_get_selected (GTK_DROP_DOWN (ui->owners));
  GtkStringObject *owner_obj = owner_idx > 0 ? gtk_drop_down_get_selected_item (GTK_DROP_DOWN (ui->owners)) : NULL;
  const char *owner_filter = owner_obj ? gtk_string_object_get_string (owner_obj) : NULL;

  g_autoptr (GPtrArray) sorted = borrowed_copy (ui->repos);
  g_ptr_array_sort_with_data (sorted, compare_repo_owner, (gpointer) me_login (ui));
  const char *section = NULL;
  GtkWidget *select = NULL;
  for (guint i = 0; i < sorted->len; i++) {
    GdlGhRepo *r = g_ptr_array_index (sorted, i);
    if (owner_filter && !g_str_has_prefix (owner_filter, r->owner))
      continue;
    g_autofree char *hay = g_utf8_casefold (r->full_name, -1);
    g_autofree char *desc = g_utf8_casefold (r->description, -1);
    if (*q && !strstr (hay, q) && !strstr (desc, q))
      continue;
    if (!section || g_ascii_strcasecmp (section, r->owner) != 0) {
      section = r->owner;
      GtkWidget *h = gtk_list_box_row_new ();
      gtk_list_box_row_set_activatable (GTK_LIST_BOX_ROW (h), FALSE);
      gtk_list_box_row_set_selectable (GTK_LIST_BOX_ROW (h), FALSE);
      g_autofree char *up = g_ascii_strup (r->owner, -1);
      GtkWidget *l = gtk_label_new (up);
      gtk_label_set_xalign (GTK_LABEL (l), 0);
      gtk_widget_add_css_class (l, "section-label");
      gtk_widget_add_css_class (h, "section-row");
      gtk_list_box_row_set_child (GTK_LIST_BOX_ROW (h), l);
      gtk_list_box_append (GTK_LIST_BOX (ui->list), h);
    }
    GtkWidget *row = repo_row (r);
    gtk_list_box_append (GTK_LIST_BOX (ui->list), row);
    if (ui->preselect && g_ascii_strcasecmp (ui->preselect, r->full_name) == 0)
      select = row;
  }
  if (select) {
    gtk_list_box_select_row (GTK_LIST_BOX (ui->list), GTK_LIST_BOX_ROW (select));
    gtk_widget_grab_focus (select);
  }
}

static void
set_repos (CloneUi *ui, GPtrArray *repos)
{
  ui->repos = repos;
  /* owner filter: "All accounts" + each owner, signed-in user first */
  GtkStringList *model = gtk_string_list_new (NULL);
  gtk_string_list_append (model, "All accounts");
  if (repos) {
    g_autoptr (GPtrArray) sorted = borrowed_copy (repos);
    g_ptr_array_sort_with_data (sorted, compare_repo_owner, (gpointer) me_login (ui));
    const char *last = NULL;
    guint count = 0;
    for (guint i = 0; i <= sorted->len; i++) {
      GdlGhRepo *r = i < sorted->len ? g_ptr_array_index (sorted, i) : NULL;
      if (last && (!r || g_ascii_strcasecmp (last, r->owner) != 0)) {
        g_autofree char *label = g_strdup_printf ("%s (%u)", last, count);
        gtk_string_list_append (model, label);
        count = 0;
      }
      if (r) {
        last = r->owner;
        count++;
      }
    }
  }
  gtk_drop_down_set_model (GTK_DROP_DOWN (ui->owners), G_LIST_MODEL (model));
  g_object_unref (model);

  if (!repos || !repos->len) {
    gtk_label_set_text (GTK_LABEL (ui->status), "Sign in from the avatar menu to see your repositories, or use the URL tab.");
  } else {
    guint owners = g_list_model_get_n_items (gtk_drop_down_get_model (GTK_DROP_DOWN (ui->owners))) - 1;
    g_autofree char *text = g_strdup_printf ("%u repositories from %u account%s", repos->len, owners, owners == 1 ? "" : "s");
    gtk_label_set_text (GTK_LABEL (ui->status), text);
  }
  fill_repo_list (ui);
  suggest_path (ui);
}

static void
on_clone_account_loaded (GObject *src, GAsyncResult *res, gpointer data)
{
  CloneUi *ui = data;
  gdl_account_free (ui->account);
  ui->account = gdl_account_load_finish (res, NULL);
  set_repos (ui, ui->account ? ui->account->repos : NULL);
  g_object_unref (ui->dialog);
}

static void
on_clone_refresh (GtkButton *b, CloneUi *ui)
{
  gtk_label_set_text (GTK_LABEL (ui->status), "Loading your repositories…");
  gdl_account_load_async (NULL, on_clone_account_loaded, ui);
  g_object_ref (ui->dialog);
}

static void
on_clone_done (gboolean ok, const char *output, gpointer data)
{
  CloneUi *ui = data;
  gtk_widget_set_visible (ui->spinner, FALSE);
  gtk_widget_set_sensitive (ui->clone_button, TRUE);
  if (ok) {
    const char *path = gtk_editable_get_text (GTK_EDITABLE (ui->path));
    gdl_window_open_repository (ui->win, path);
    gdl_window_toast (ui->win, "Repository cloned");
    adw_dialog_force_close (ui->dialog);
  } else {
    g_autofree char *msg = gdl_net_explain_error (output);
    show_error (ui->error, msg);
  }
  g_object_unref (ui->dialog);
}

static void
on_clone_clicked (GtkButton *b, CloneUi *ui)
{
  g_autofree char *url = clone_url (ui);
  const char *path = gtk_editable_get_text (GTK_EDITABLE (ui->path));
  if (!url || !*path) {
    show_error (ui->error, "Choose a repository and a local path.");
    return;
  }
  g_autoptr (GFile) dest = g_file_new_for_path (path);
  g_autoptr (GFileEnumerator) en = g_file_enumerate_children (dest, "standard::name", 0, NULL, NULL);
  if (en && g_file_enumerator_next_file (en, NULL, NULL)) {
    g_autofree char *msg = g_strdup_printf ("“%s” already exists and is not empty.", path);
    show_error (ui->error, msg);
    return;
  }
  g_autofree char *parent = g_path_get_dirname (path);
  g_mkdir_with_parents (parent, 0755);
  show_error (ui->error, NULL);
  gtk_widget_set_visible (ui->spinner, TRUE);
  gtk_widget_set_sensitive (ui->clone_button, FALSE);
  g_object_ref (ui->dialog);
  gdl_net_clone (url, path, gdl_window_get_token (ui->win), on_clone_done, ui);
}

static void
on_clone_tab (AdwToggleGroup *tabs, GParamSpec *p, CloneUi *ui)
{
  gtk_stack_set_visible_child_name (GTK_STACK (ui->stack), adw_toggle_group_get_active_name (tabs));
  suggest_path (ui);
}

void
gdl_clone_dialog_show (GdlWindow *win, const char *preselect)
{
  CloneUi *ui = g_new0 (CloneUi, 1);
  ui->win = win;
  ui->preselect = g_strdup (preselect);
  ui->parent_dir = default_parent_dir ();
  GtkWidget *body, *buttons;
  ui->dialog = dialog_new ("Clone a repository", 660, 640, &body, &buttons);
  g_object_set_data_full (G_OBJECT (ui->dialog), "ui", ui, (GDestroyNotify) clone_ui_free);

  AdwToggleGroup *tabs = ADW_TOGGLE_GROUP (adw_toggle_group_new ());
  AdwToggle *t1 = adw_toggle_new (), *t2 = adw_toggle_new ();
  adw_toggle_set_name (t1, "github");
  adw_toggle_set_label (t1, "GitHub.com");
  adw_toggle_set_name (t2, "url");
  adw_toggle_set_label (t2, "URL");
  adw_toggle_group_add (tabs, t1);
  adw_toggle_group_add (tabs, t2);
  adw_toggle_group_set_homogeneous (tabs, TRUE);
  gtk_widget_set_halign (GTK_WIDGET (tabs), GTK_ALIGN_CENTER);
  gtk_widget_set_size_request (GTK_WIDGET (tabs), 260, -1);
  gtk_box_append (GTK_BOX (body), GTK_WIDGET (tabs));

  ui->stack = gtk_stack_new ();
  gtk_widget_set_vexpand (ui->stack, TRUE);

  /* GitHub.com */
  GtkWidget *gh = gtk_box_new (GTK_ORIENTATION_VERTICAL, 8);
  GtkWidget *top = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 6);
  ui->search = gtk_search_entry_new ();
  gtk_search_entry_set_placeholder_text (GTK_SEARCH_ENTRY (ui->search), "Filter your repositories");
  gtk_widget_set_hexpand (ui->search, TRUE);
  g_signal_connect_swapped (ui->search, "search-changed", G_CALLBACK (fill_repo_list), ui);
  gtk_box_append (GTK_BOX (top), ui->search);
  ui->owners = gtk_drop_down_new (NULL, NULL);
  g_signal_connect_swapped (ui->owners, "notify::selected", G_CALLBACK (fill_repo_list), ui);
  gtk_box_append (GTK_BOX (top), ui->owners);
  GtkWidget *refresh = gtk_button_new ();
  gtk_button_set_child (GTK_BUTTON (refresh), gdl_icon_new ("sync", 16));
  gtk_widget_set_tooltip_text (refresh, "Reload repositories from GitHub");
  g_signal_connect (refresh, "clicked", G_CALLBACK (on_clone_refresh), ui);
  gtk_box_append (GTK_BOX (top), refresh);
  gtk_box_append (GTK_BOX (gh), top);
  GtkWidget *scroll = gtk_scrolled_window_new ();
  gtk_scrolled_window_set_policy (GTK_SCROLLED_WINDOW (scroll), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
  gtk_widget_set_vexpand (scroll, TRUE);
  gtk_widget_add_css_class (scroll, "card");
  ui->list = gtk_list_box_new ();
  gtk_widget_add_css_class (ui->list, "navigation-sidebar");
  g_signal_connect_swapped (ui->list, "row-selected", G_CALLBACK (suggest_path), ui);
  g_signal_connect_swapped (ui->list, "row-activated", G_CALLBACK (on_clone_clicked), ui);
  gtk_scrolled_window_set_child (GTK_SCROLLED_WINDOW (scroll), ui->list);
  gtk_box_append (GTK_BOX (gh), scroll);
  ui->status = dim_label ("Loading your repositories…");
  gtk_box_append (GTK_BOX (gh), ui->status);
  gtk_stack_add_named (GTK_STACK (ui->stack), gh, "github");

  /* URL */
  GtkWidget *url_page = gtk_box_new (GTK_ORIENTATION_VERTICAL, 8);
  GtkWidget *group = adw_preferences_group_new ();
  adw_preferences_group_set_description (ADW_PREFERENCES_GROUP (group),
                                         "A repository URL, or a GitHub owner/name such as desktop/desktop.");
  ui->url = adw_entry_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (ui->url), "Repository URL or owner/name");
  g_signal_connect_swapped (ui->url, "changed", G_CALLBACK (suggest_path), ui);
  adw_preferences_group_add (ADW_PREFERENCES_GROUP (group), ui->url);
  gtk_box_append (GTK_BOX (url_page), group);
  gtk_stack_add_named (GTK_STACK (ui->stack), url_page, "url");
  gtk_box_append (GTK_BOX (body), ui->stack);
  g_signal_connect (tabs, "notify::active-name", G_CALLBACK (on_clone_tab), ui);

  GtkWidget *pg = adw_preferences_group_new ();
  ui->path = path_row ("Local path", ui->parent_dir);
  adw_preferences_group_add (ADW_PREFERENCES_GROUP (pg), ui->path);
  gtk_box_append (GTK_BOX (body), pg);
  ui->error = error_label ();
  gtk_box_append (GTK_BOX (body), ui->error);

  ui->spinner = adw_spinner_new ();
  gtk_widget_set_visible (ui->spinner, FALSE);
  gtk_box_append (GTK_BOX (buttons), ui->spinner);
  ui->clone_button = primary_button ("Clone");
  gtk_widget_set_sensitive (ui->clone_button, FALSE);
  g_signal_connect (ui->clone_button, "clicked", G_CALLBACK (on_clone_clicked), ui);
  gtk_box_append (GTK_BOX (buttons), ui->clone_button);

  GdlAccount *account = gdl_window_get_account (win);
  if (account && account->repos)
    set_repos (ui, account->repos);
  else if (account && !account->profile) {
    set_repos (ui, NULL);
    adw_toggle_group_set_active_name (tabs, "url");
  } else
    on_clone_refresh (NULL, ui);
  adw_dialog_present (ui->dialog, GTK_WIDGET (win));
}

/* ================================================================== */
/* Create                                                              */
/* ================================================================== */

typedef struct {
  GdlWindow *win;
  AdwDialog *dialog;
  GtkWidget *name, *path, *readme, *error;
} CreateUi;

static void
on_create_clicked (GtkButton *b, CreateUi *ui)
{
  g_autofree char *name = g_strstrip (g_strdup (gtk_editable_get_text (GTK_EDITABLE (ui->name))));
  const char *parent = gtk_editable_get_text (GTK_EDITABLE (ui->path));
  /* only a plain folder name: no "../", no sub-paths, no hidden dirs */
  if (!*name || g_str_equal (name, "..") || strchr (name, '/') || name[0] == '.') {
    show_error (ui->error, "Enter a plain folder name, e.g. my-project.");
    return;
  }
  g_autofree char *path = g_build_filename (parent, name, NULL);
  g_autoptr (GError) error = NULL;
  if (g_mkdir_with_parents (path, 0755) != 0 || !gdl_repo_init (path, &error)) {
    show_error (ui->error, error ? error->message : "Could not create the folder.");
    return;
  }
  if (adw_switch_row_get_active (ADW_SWITCH_ROW (ui->readme))) {
    g_autofree char *readme = g_build_filename (path, "README.md", NULL);
    if (!g_file_test (readme, G_FILE_TEST_EXISTS)) {
      g_autofree char *text = g_strdup_printf ("# %s\n\nCreated with Git Desktop For Linux.\n", name);
      g_file_set_contents (readme, text, -1, NULL);
      g_autoptr (GdlRepo) repo = gdl_repo_open (path, NULL);
      g_autoptr (GPtrArray) files = repo ? gdl_repo_status (repo, NULL) : NULL;
      if (files) {
        g_autoptr (GHashTable) all = g_hash_table_new (g_str_hash, g_str_equal);
        for (guint i = 0; i < files->len; i++)
          g_hash_table_add (all, ((GdlFile *) g_ptr_array_index (files, i))->path);
        g_autoptr (GError) cerr = NULL;
        if (!gdl_repo_commit (repo, files, all, "Initial commit", NULL, &cerr))
          gdl_window_toast (ui->win, cerr->message);
      }
    }
  }
  gdl_window_open_repository (ui->win, path);
  adw_dialog_force_close (ui->dialog);
}

void
gdl_create_dialog_show (GdlWindow *win)
{
  CreateUi *ui = g_new0 (CreateUi, 1);
  ui->win = win;
  GtkWidget *body, *buttons;
  ui->dialog = dialog_new ("Create a new repository", 520, -1, &body, &buttons);
  g_object_set_data_full (G_OBJECT (ui->dialog), "ui", ui, g_free);
  GtkWidget *group = adw_preferences_group_new ();
  ui->name = adw_entry_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (ui->name), "Name");
  g_autofree char *parent = default_parent_dir ();
  ui->path = path_row ("Local path", parent);
  ui->readme = adw_switch_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (ui->readme), "Initialize with a README");
  adw_switch_row_set_active (ADW_SWITCH_ROW (ui->readme), TRUE);
  adw_preferences_group_add (ADW_PREFERENCES_GROUP (group), ui->name);
  adw_preferences_group_add (ADW_PREFERENCES_GROUP (group), ui->path);
  adw_preferences_group_add (ADW_PREFERENCES_GROUP (group), ui->readme);
  gtk_box_append (GTK_BOX (body), group);
  ui->error = error_label ();
  gtk_box_append (GTK_BOX (body), ui->error);
  GtkWidget *create = primary_button ("Create repository");
  g_signal_connect (create, "clicked", G_CALLBACK (on_create_clicked), ui);
  g_signal_connect_swapped (ui->name, "entry-activated", G_CALLBACK (on_create_clicked), ui);
  gtk_box_append (GTK_BOX (buttons), create);
  adw_dialog_present (ui->dialog, GTK_WIDGET (win));
}

/* ================================================================== */
/* Add existing                                                        */
/* ================================================================== */

static void
on_init_here (AdwAlertDialog *d, const char *response, GdlWindow *win)
{
  const char *path = g_object_get_data (G_OBJECT (d), "path");
  if (!g_str_equal (response, "create"))
    return;
  g_autoptr (GError) error = NULL;
  if (!gdl_repo_init (path, &error))
    gdl_window_error (win, "Could not create repository", error->message);
  else
    gdl_window_open_repository (win, path);
}

static void
on_existing_chosen (GObject *src, GAsyncResult *res, gpointer data)
{
  GdlWindow *win = data;
  g_autoptr (GFile) folder = gtk_file_dialog_select_folder_finish (GTK_FILE_DIALOG (src), res, NULL);
  if (folder) {
    g_autofree char *path = g_file_get_path (folder);
    g_autoptr (GdlRepo) probe = gdl_repo_open (path, NULL);
    if (probe) {
      gdl_window_open_repository (win, path);
    } else {
      g_autofree char *body = g_strdup_printf ("“%s” does not appear to be a Git repository.\n\nCreate a repository here?", path);
      AdwDialog *d = adw_alert_dialog_new ("Not a Git repository", body);
      adw_alert_dialog_add_responses (ADW_ALERT_DIALOG (d), "cancel", "Cancel", "create", "Create repository", NULL);
      adw_alert_dialog_set_response_appearance (ADW_ALERT_DIALOG (d), "create", ADW_RESPONSE_SUGGESTED);
      g_object_set_data_full (G_OBJECT (d), "path", g_strdup (path), g_free);
      g_signal_connect (d, "response", G_CALLBACK (on_init_here), win);
      adw_dialog_present (d, GTK_WIDGET (win));
    }
  }
  g_object_unref (win);
}

void
gdl_add_existing_show (GdlWindow *win)
{
  g_autoptr (GtkFileDialog) fd = gtk_file_dialog_new ();
  gtk_file_dialog_set_title (fd, "Add local repository");
  gtk_file_dialog_select_folder (fd, GTK_WINDOW (win), NULL, on_existing_chosen, g_object_ref (win));
}

/* ================================================================== */
/* Branch name (new / rename)                                          */
/* ================================================================== */

typedef struct {
  GdlWindow *win;
  char      *old_name;
  GtkWidget *entry, *error;
  AdwDialog *dialog;
} BranchUi;

static void
branch_ui_free (BranchUi *ui)
{
  g_free (ui->old_name);
  g_free (ui);
}

static void
validate_branch (BranchUi *ui)
{
  const char *name = gtk_editable_get_text (GTK_EDITABLE (ui->entry));
  gboolean ok = gdl_branch_name_valid (name);
  const char *msg = NULL;
  if (*name && !ok)
    msg = "This is not a valid branch name (no spaces, “..”, or a leading “-”).";
  if (ok && ui->old_name && g_str_equal (name, ui->old_name))
    ok = FALSE;
  if (ok) {
    g_autoptr (GPtrArray) locals = gdl_repo_branches (gdl_window_get_repo (ui->win), FALSE);
    for (guint i = 0; i < locals->len; i++)
      if (g_str_equal (g_ptr_array_index (locals, i), name)) {
        ok = FALSE;
        msg = "A branch with this name already exists.";
      }
  }
  show_error (ui->error, msg);
  adw_alert_dialog_set_response_enabled (ADW_ALERT_DIALOG (ui->dialog), "ok", ok);
}

static void
on_branch_response (AdwAlertDialog *d, const char *response, BranchUi *ui)
{
  if (!g_str_equal (response, "ok"))
    return;
  const char *name = gtk_editable_get_text (GTK_EDITABLE (ui->entry));
  GdlRepo *repo = gdl_window_get_repo (ui->win);
  g_autoptr (GError) error = NULL;
  gboolean ok = ui->old_name ? gdl_repo_rename_branch (repo, ui->old_name, name, &error)
                             : gdl_repo_create_branch (repo, name, &error);
  if (!ok)
    gdl_window_error (ui->win, ui->old_name ? "Could not rename branch" : "Could not create branch", error->message);
  gdl_window_refresh (ui->win, TRUE);
}

void
gdl_branch_name_dialog_show (GdlWindow *win, const char *old_name)
{
  GdlRepo *repo = gdl_window_get_repo (win);
  if (!repo)
    return;
  BranchUi *ui = g_new0 (BranchUi, 1);
  ui->win = win;
  ui->old_name = g_strdup (old_name);
  g_autofree char *current = gdl_repo_branch (repo);
  g_autofree char *body = old_name ? g_strdup_printf ("Rename “%s” to:", old_name)
                                   : g_strdup_printf ("Your new branch will be based on “%s”.", current);
  ui->dialog = adw_alert_dialog_new (old_name ? "Rename branch" : "Create a branch", body);
  adw_alert_dialog_add_responses (ADW_ALERT_DIALOG (ui->dialog), "cancel", "Cancel",
                                  "ok", old_name ? "Rename" : "Create branch", NULL);
  adw_alert_dialog_set_response_appearance (ADW_ALERT_DIALOG (ui->dialog), "ok", ADW_RESPONSE_SUGGESTED);
  adw_alert_dialog_set_default_response (ADW_ALERT_DIALOG (ui->dialog), "ok");
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_VERTICAL, 6);
  ui->entry = gtk_entry_new ();
  gtk_entry_set_placeholder_text (GTK_ENTRY (ui->entry), "feature/my-change");
  gtk_entry_set_activates_default (GTK_ENTRY (ui->entry), TRUE);
  if (old_name)
    gtk_editable_set_text (GTK_EDITABLE (ui->entry), old_name);
  gtk_box_append (GTK_BOX (box), ui->entry);
  ui->error = error_label ();
  gtk_box_append (GTK_BOX (box), ui->error);
  adw_alert_dialog_set_extra_child (ADW_ALERT_DIALOG (ui->dialog), box);
  g_signal_connect_swapped (ui->entry, "changed", G_CALLBACK (validate_branch), ui);
  g_signal_connect (ui->dialog, "response", G_CALLBACK (on_branch_response), ui);
  g_object_set_data_full (G_OBJECT (ui->dialog), "ui", ui, (GDestroyNotify) branch_ui_free);
  validate_branch (ui);
  adw_dialog_present (ui->dialog, GTK_WIDGET (win));
  gtk_widget_grab_focus (ui->entry);
}

/* ================================================================== */
/* Merge                                                               */
/* ================================================================== */

typedef struct {
  GdlWindow *win;
  AdwDialog *dialog;
  GtkWidget *search, *list, *button;
  char      *current;
} MergeUi;

static void
merge_ui_free (MergeUi *ui)
{
  g_free (ui->current);
  g_free (ui);
}

static void
on_merge_selected (GtkListBox *list, GtkListBoxRow *row, MergeUi *ui)
{
  gtk_widget_set_sensitive (ui->button, row != NULL);
  if (row) {
    g_autofree char *label = g_strdup_printf ("Merge %s into %s", (char *) g_object_get_data (G_OBJECT (row), "name"),
                                              ui->current);
    gtk_button_set_label (GTK_BUTTON (ui->button), label);
  }
}

static void
on_merge_filter (MergeUi *ui)
{
  g_autofree char *q = g_utf8_casefold (gtk_editable_get_text (GTK_EDITABLE (ui->search)), -1);
  for (GtkWidget *row = gtk_widget_get_first_child (ui->list); row; row = gtk_widget_get_next_sibling (row)) {
    g_autofree char *name = g_utf8_casefold (g_object_get_data (G_OBJECT (row), "name"), -1);
    gtk_widget_set_visible (row, !*q || strstr (name, q));
  }
}

static void
on_merge_clicked (MergeUi *ui)
{
  GtkListBoxRow *row = gtk_list_box_get_selected_row (GTK_LIST_BOX (ui->list));
  if (!row)
    return;
  const char *name = g_object_get_data (G_OBJECT (row), "name");
  g_autoptr (GError) error = NULL;
  GdlWindow *win = ui->win;
  if (!gdl_repo_merge (gdl_window_get_repo (win), name, &error)) {
    if (g_error_matches (error, GDL_GIT_ERROR, GDL_GIT_ERROR_CONFLICT))
      gdl_window_error (win, "Merge conflicts", "There are conflicts. Resolve them in your editor, then commit the merge.");
    else
      gdl_window_error (win, "Merge failed", error->message);
  } else {
    gdl_window_toast (win, "Merged");
  }
  adw_dialog_force_close (ui->dialog);
  gdl_window_refresh (win, TRUE);
}

void
gdl_merge_dialog_show (GdlWindow *win)
{
  GdlRepo *repo = gdl_window_get_repo (win);
  if (!repo)
    return;
  MergeUi *ui = g_new0 (MergeUi, 1);
  ui->win = win;
  ui->current = gdl_repo_branch (repo);
  GtkWidget *body, *buttons;
  g_autofree char *title = g_strdup_printf ("Merge into %s", ui->current);
  ui->dialog = dialog_new (title, 440, 520, &body, &buttons);
  g_object_set_data_full (G_OBJECT (ui->dialog), "ui", ui, (GDestroyNotify) merge_ui_free);
  ui->search = gtk_search_entry_new ();
  gtk_search_entry_set_placeholder_text (GTK_SEARCH_ENTRY (ui->search), "Filter branches");
  g_signal_connect_swapped (ui->search, "search-changed", G_CALLBACK (on_merge_filter), ui);
  gtk_box_append (GTK_BOX (body), ui->search);
  GtkWidget *scroll = gtk_scrolled_window_new ();
  gtk_widget_set_vexpand (scroll, TRUE);
  gtk_widget_add_css_class (scroll, "card");
  ui->list = gtk_list_box_new ();
  gtk_widget_add_css_class (ui->list, "navigation-sidebar");
  for (int remote = 0; remote < 2; remote++) {
    g_autoptr (GPtrArray) branches = gdl_repo_branches (repo, remote);
    for (guint i = 0; i < branches->len; i++) {
      const char *b = g_ptr_array_index (branches, i);
      if (g_str_equal (b, ui->current))
        continue;
      GtkWidget *row = gtk_list_box_row_new ();
      GtkWidget *box = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 10);
      gtk_widget_set_margin_top (box, 6);
      gtk_widget_set_margin_bottom (box, 6);
      gtk_widget_set_margin_start (box, 6);
      GtkWidget *ic = gdl_icon_new (remote ? "cloud-down" : "branch", 16);
      gtk_widget_add_css_class (ic, "dim-label");
      gtk_box_append (GTK_BOX (box), ic);
      gtk_box_append (GTK_BOX (box), gtk_label_new (b));
      gtk_list_box_row_set_child (GTK_LIST_BOX_ROW (row), box);
      g_object_set_data_full (G_OBJECT (row), "name", g_strdup (b), g_free);
      gtk_list_box_append (GTK_LIST_BOX (ui->list), row);
    }
  }
  g_signal_connect (ui->list, "row-selected", G_CALLBACK (on_merge_selected), ui);
  g_signal_connect_swapped (ui->list, "row-activated", G_CALLBACK (on_merge_clicked), ui);
  gtk_scrolled_window_set_child (GTK_SCROLLED_WINDOW (scroll), ui->list);
  gtk_box_append (GTK_BOX (body), scroll);
  ui->button = primary_button ("Merge");
  gtk_widget_set_sensitive (ui->button, FALSE);
  g_signal_connect_swapped (ui->button, "clicked", G_CALLBACK (on_merge_clicked), ui);
  gtk_box_append (GTK_BOX (buttons), ui->button);
  adw_dialog_present (ui->dialog, GTK_WIDGET (win));
}

/* ================================================================== */
/* Preferences                                                         */
/* ================================================================== */

static const char *const EDITOR_CMDS[]  = { "", "code", "codium", "cursor", "zed", "subl", "kate", "gnome-text-editor", "gedit", NULL };
static const char *const EDITOR_NAMES[] = { "Automatic", "Visual Studio Code", "VSCodium", "Cursor", "Zed", "Sublime Text",
                                            "Kate", "GNOME Text Editor", "Gedit", NULL };

typedef struct {
  GdlWindow *win;
  GtkWidget *name, *email, *editor, *terminal, *theme;
  GPtrArray *editor_cmds;  /* commands behind the combo items */
} PrefsUi;

static void
prefs_ui_free (PrefsUi *ui)
{
  g_ptr_array_unref (ui->editor_cmds);
  g_free (ui);
}

static void
on_theme_selected (AdwComboRow *row, GParamSpec *p, PrefsUi *ui)
{
  static const char *const values[] = { "system", "light", "dark" };
  settings_set_string ("theme", values[adw_combo_row_get_selected (row)]);
  gdl_window_apply_theme ();
}

static void
on_prefs_closed (AdwDialog *d, PrefsUi *ui)
{
  const char *name = gtk_editable_get_text (GTK_EDITABLE (ui->name));
  const char *email = gtk_editable_get_text (GTK_EDITABLE (ui->email));
  g_autofree char *old_name = NULL, *old_email = NULL;
  gdl_global_identity (&old_name, &old_email);
  if (*name && *email && (g_strcmp0 (name, old_name) || g_strcmp0 (email, old_email))) {
    g_autoptr (GError) error = NULL;
    if (!gdl_set_global_identity (name, email, &error))
      gdl_window_error (ui->win, "Could not save", error->message);
  }
  guint i = adw_combo_row_get_selected (ADW_COMBO_ROW (ui->editor));
  if (i < ui->editor_cmds->len)
    settings_set_string ("editor", g_ptr_array_index (ui->editor_cmds, i));
  settings_set_string ("terminal", gtk_editable_get_text (GTK_EDITABLE (ui->terminal)));
  gdl_window_refresh (ui->win, TRUE);
}

static void
account_group (PrefsUi *ui, AdwPreferencesGroup *group)
{
  GdlAccount *a = gdl_window_get_account (ui->win);
  GdlProfile *p = a ? a->profile : NULL;
  GtkWidget *row = adw_action_row_new ();
  GtkWidget *button;
  if (p) {
    adw_preferences_row_set_title (ADW_PREFERENCES_ROW (row), p->name);
    g_autofree char *sub = g_strdup_printf ("@%s · %u repositories", p->login, a->repos ? a->repos->len : 0);
    adw_action_row_set_subtitle (ADW_ACTION_ROW (row), sub);
    adw_action_row_add_prefix (ADW_ACTION_ROW (row), adw_avatar_new (40, p->name, TRUE));
    button = gtk_button_new_with_label ("Sign out");
    gtk_widget_add_css_class (button, "destructive-action");
    gtk_actionable_set_action_name (GTK_ACTIONABLE (button), "win.sign-out");
  } else {
    adw_preferences_row_set_title (ADW_PREFERENCES_ROW (row), "Not signed in");
    adw_action_row_set_subtitle (ADW_ACTION_ROW (row), "Sign in to push, pull and clone over HTTPS without passwords.");
    button = gtk_button_new_with_label ("Sign in…");
    gtk_widget_add_css_class (button, "suggested-action");
    gtk_actionable_set_action_name (GTK_ACTIONABLE (button), "win.sign-in");
  }
  gtk_widget_set_valign (button, GTK_ALIGN_CENTER);
  adw_action_row_add_suffix (ADW_ACTION_ROW (row), button);
  adw_preferences_group_add (group, row);
}

void
gdl_preferences_show (GdlWindow *win)
{
  PrefsUi *ui = g_new0 (PrefsUi, 1);
  ui->win = win;
  ui->editor_cmds = g_ptr_array_new_with_free_func (g_free);
  AdwDialog *d = adw_preferences_dialog_new ();
  g_object_set_data_full (G_OBJECT (d), "ui", ui, (GDestroyNotify) prefs_ui_free);

  /* Accounts & Git */
  AdwPreferencesPage *page = ADW_PREFERENCES_PAGE (adw_preferences_page_new ());
  adw_preferences_page_set_title (page, "General");
  adw_preferences_page_set_icon_name (page, "preferences-system-symbolic");
  AdwPreferencesGroup *acc = ADW_PREFERENCES_GROUP (adw_preferences_group_new ());
  adw_preferences_group_set_title (acc, "GitHub.com");
  account_group (ui, acc);
  adw_preferences_page_add (page, acc);

  AdwPreferencesGroup *git = ADW_PREFERENCES_GROUP (adw_preferences_group_new ());
  adw_preferences_group_set_title (git, "Git");
  adw_preferences_group_set_description (git, "Used for every commit you make (saved in your global git config).");
  g_autofree char *name = NULL, *email = NULL;
  gdl_global_identity (&name, &email);
  ui->name = adw_entry_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (ui->name), "Name");
  gtk_editable_set_text (GTK_EDITABLE (ui->name), name ? name : "");
  ui->email = adw_entry_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (ui->email), "Email");
  gtk_editable_set_text (GTK_EDITABLE (ui->email), email ? email : "");
  adw_preferences_group_add (git, ui->name);
  adw_preferences_group_add (git, ui->email);
  adw_preferences_page_add (page, git);

  /* Integrations */
  AdwPreferencesGroup *integ = ADW_PREFERENCES_GROUP (adw_preferences_group_new ());
  adw_preferences_group_set_title (integ, "Integrations");
  GtkStringList *editors = gtk_string_list_new (NULL);
  g_autofree char *current_editor = settings_get_string ("editor");
  guint selected = 0;
  for (guint i = 0; EDITOR_CMDS[i]; i++) {
    g_autofree char *found = *EDITOR_CMDS[i] ? g_find_program_in_path (EDITOR_CMDS[i]) : NULL;
    if (*EDITOR_CMDS[i] && !found)
      continue;  /* only installed editors */
    if (current_editor && g_str_equal (current_editor, EDITOR_CMDS[i]))
      selected = ui->editor_cmds->len;
    gtk_string_list_append (editors, EDITOR_NAMES[i]);
    g_ptr_array_add (ui->editor_cmds, g_strdup (EDITOR_CMDS[i]));
  }
  ui->editor = adw_combo_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (ui->editor), "External editor");
  adw_combo_row_set_model (ADW_COMBO_ROW (ui->editor), G_LIST_MODEL (editors));
  adw_combo_row_set_selected (ADW_COMBO_ROW (ui->editor), selected);
  g_object_unref (editors);
  ui->terminal = adw_entry_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (ui->terminal), "Terminal (empty = detect)");
  g_autofree char *term = settings_get_string ("terminal");
  gtk_editable_set_text (GTK_EDITABLE (ui->terminal), term ? term : "");
  adw_preferences_group_add (integ, ui->editor);
  adw_preferences_group_add (integ, ui->terminal);
  adw_preferences_page_add (page, integ);

  /* Appearance */
  AdwPreferencesGroup *look = ADW_PREFERENCES_GROUP (adw_preferences_group_new ());
  adw_preferences_group_set_title (look, "Appearance");
  const char *themes[] = { "Follow system", "Light", "Dark", NULL };
  ui->theme = adw_combo_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (ui->theme), "Theme");
  adw_combo_row_set_model (ADW_COMBO_ROW (ui->theme), G_LIST_MODEL (gtk_string_list_new (themes)));
  g_autofree char *theme = settings_get_string ("theme");
  adw_combo_row_set_selected (ADW_COMBO_ROW (ui->theme),
                              g_strcmp0 (theme, "light") == 0 ? 1 : g_strcmp0 (theme, "dark") == 0 ? 2 : 0);
  g_signal_connect (ui->theme, "notify::selected", G_CALLBACK (on_theme_selected), ui);
  adw_preferences_group_add (look, ui->theme);
  adw_preferences_page_add (page, look);

  adw_preferences_dialog_add (ADW_PREFERENCES_DIALOG (d), page);
  g_signal_connect (d, "closed", G_CALLBACK (on_prefs_closed), ui);
  adw_dialog_present (d, GTK_WIDGET (win));
}

/* ================================================================== */
/* Sign in                                                             */
/* ================================================================== */

typedef struct {
  GdlWindow *win;
  AdwDialog *dialog;
  GtkWidget *token, *status, *sign_in;
} SignInUi;

static void
signin_status (SignInUi *ui, const char *text, gboolean error)
{
  gtk_label_set_text (GTK_LABEL (ui->status), text);
  if (error)
    gtk_widget_add_css_class (ui->status, "error");
  else
    gtk_widget_remove_css_class (ui->status, "error");
  gtk_widget_set_visible (ui->status, TRUE);
}

static void
on_token_validated (GObject *src, GAsyncResult *res, gpointer data)
{
  SignInUi *ui = data;
  g_autoptr (GError) error = NULL;
  GdlProfile *p = gdl_token_validate_finish (res, &error);
  gtk_widget_set_sensitive (ui->sign_in, TRUE);
  if (!p) {
    signin_status (ui, "GitHub did not accept this token, or GitHub could not be reached.", TRUE);
  } else {
    const char *token = gtk_editable_get_text (GTK_EDITABLE (ui->token));
    g_autoptr (GError) store_err = NULL;
    if (!gdl_token_store (token, &store_err)) {
      g_autofree char *msg = g_strdup_printf ("Could not save the token in the system keyring: %s", store_err->message);
      signin_status (ui, msg, TRUE);
    } else {
      g_autofree char *hello = g_strdup_printf ("Signed in as @%s", p->login);
      gdl_window_toast (ui->win, hello);
      gdl_window_reload_account (ui->win);
      adw_dialog_force_close (ui->dialog);
    }
    gdl_profile_free (p);
  }
  g_object_unref (ui->dialog);
}

static void
on_sign_in_clicked (SignInUi *ui)
{
  const char *token = gtk_editable_get_text (GTK_EDITABLE (ui->token));
  if (!*token)
    return;
  gtk_widget_set_sensitive (ui->sign_in, FALSE);
  signin_status (ui, "Checking the token…", FALSE);
  g_object_ref (ui->dialog);
  gdl_token_validate_async (token, NULL, on_token_validated, ui);
}

static void
on_cli_checked (GObject *src, GAsyncResult *res, gpointer data)
{
  SignInUi *ui = data;
  GdlAccount *a = gdl_account_load_finish (res, NULL);
  if (a && a->profile) {
    gdl_window_reload_account (ui->win);
    adw_dialog_force_close (ui->dialog);
  } else {
    signin_status (ui, "The GitHub CLI is not signed in yet. Run “gh auth login” in a terminal first.", TRUE);
  }
  gdl_account_free (a);
  g_object_unref (ui->dialog);
}

static void
on_check_cli (SignInUi *ui)
{
  settings_set_bool ("use_gh_cli", TRUE);
  signin_status (ui, "Checking the GitHub CLI login…", FALSE);
  g_object_ref (ui->dialog);
  gdl_account_load_async (NULL, on_cli_checked, ui);
}

static void
on_open_token_page (GtkButton *b, SignInUi *ui)
{
  g_autoptr (GtkUriLauncher) l = gtk_uri_launcher_new (GDL_TOKEN_URL);
  gtk_uri_launcher_launch (l, GTK_WINDOW (ui->win), NULL, NULL, NULL);
}

static void
on_token_changed (SignInUi *ui)
{
  gtk_widget_set_sensitive (ui->sign_in, *gtk_editable_get_text (GTK_EDITABLE (ui->token)) != '\0');
}

void
gdl_sign_in_dialog_show (GdlWindow *win)
{
  SignInUi *ui = g_new0 (SignInUi, 1);
  ui->win = win;
  GtkWidget *body, *buttons;
  ui->dialog = dialog_new ("Sign in to GitHub.com", 480, -1, &body, &buttons);
  g_object_set_data_full (G_OBJECT (ui->dialog), "ui", ui, g_free);

  GtkWidget *head = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 12);
  GtkWidget *ic = gdl_icon_new ("user", 32);
  gtk_widget_add_css_class (ic, "accent");
  gtk_box_append (GTK_BOX (head), ic);
  GtkWidget *title = gtk_label_new ("Sign in to GitHub.com");
  gtk_widget_add_css_class (title, "title-2");
  gtk_box_append (GTK_BOX (head), title);
  gtk_box_append (GTK_BOX (body), head);
  gtk_box_append (GTK_BOX (body), dim_label ("Your repositories will show up in Git Desktop, and pushing, pulling and "
                                             "cloning over HTTPS will use this account. The token is kept in your "
                                             "system keyring."));

  GtkWidget *step1 = gtk_label_new (NULL);
  gtk_label_set_markup (GTK_LABEL (step1), "<b>1.</b> Create a personal access token on GitHub (the <i>repo</i> scope is enough).");
  gtk_label_set_wrap (GTK_LABEL (step1), TRUE);
  gtk_label_set_xalign (GTK_LABEL (step1), 0);
  gtk_box_append (GTK_BOX (body), step1);
  GtkWidget *open = gtk_button_new ();
  GtkWidget *ob = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 8);
  gtk_box_append (GTK_BOX (ob), gdl_icon_new ("external", 16));
  gtk_box_append (GTK_BOX (ob), gtk_label_new ("Create a token on github.com"));
  gtk_button_set_child (GTK_BUTTON (open), ob);
  gtk_widget_set_halign (open, GTK_ALIGN_START);
  g_signal_connect (open, "clicked", G_CALLBACK (on_open_token_page), ui);
  gtk_box_append (GTK_BOX (body), open);

  GtkWidget *step2 = gtk_label_new (NULL);
  gtk_label_set_markup (GTK_LABEL (step2), "<b>2.</b> Paste the token here:");
  gtk_label_set_xalign (GTK_LABEL (step2), 0);
  gtk_box_append (GTK_BOX (body), step2);
  GtkWidget *group = adw_preferences_group_new ();
  ui->token = adw_password_entry_row_new ();
  adw_preferences_row_set_title (ADW_PREFERENCES_ROW (ui->token), "Personal access token");
  g_signal_connect_swapped (ui->token, "changed", G_CALLBACK (on_token_changed), ui);
  g_signal_connect_swapped (ui->token, "entry-activated", G_CALLBACK (on_sign_in_clicked), ui);
  adw_preferences_group_add (ADW_PREFERENCES_GROUP (group), ui->token);
  gtk_box_append (GTK_BOX (body), group);

  ui->status = dim_label ("");
  gtk_widget_set_visible (ui->status, FALSE);
  gtk_box_append (GTK_BOX (body), ui->status);

  g_autofree char *gh = g_find_program_in_path ("gh");
  if (gh) {
    GtkWidget *cli = gtk_label_new (NULL);
    gtk_label_set_markup (GTK_LABEL (cli), "Already use the GitHub CLI? Run <tt>gh auth login</tt> in a terminal, "
                                           "then press <i>Check again</i>.");
    gtk_label_set_wrap (GTK_LABEL (cli), TRUE);
    gtk_label_set_xalign (GTK_LABEL (cli), 0);
    gtk_widget_add_css_class (cli, "dim-label");
    gtk_box_append (GTK_BOX (body), cli);
    GtkWidget *again = gtk_button_new_with_label ("Check again");
    gtk_widget_add_css_class (again, "pill");
    g_signal_connect_swapped (again, "clicked", G_CALLBACK (on_check_cli), ui);
    gtk_box_append (GTK_BOX (buttons), again);
  }
  ui->sign_in = primary_button ("Sign in");
  gtk_widget_set_sensitive (ui->sign_in, FALSE);
  g_signal_connect_swapped (ui->sign_in, "clicked", G_CALLBACK (on_sign_in_clicked), ui);
  gtk_box_append (GTK_BOX (buttons), ui->sign_in);
  adw_dialog_present (ui->dialog, GTK_WIDGET (win));
}
