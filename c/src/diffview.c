#include "diffview.h"

#include "diffparse.h"
#include "git.h"
#include "icons.h"
#include "util.h"

#include <gtksourceview/gtksource.h>

#define MAX_ROWS 20000

/* ------------------------------------------------------------------ */
/* Gutter renderer: one line-number column (old or new)                */
/* ------------------------------------------------------------------ */

#define GDL_TYPE_LINE_RENDERER (gdl_line_renderer_get_type ())
G_DECLARE_FINAL_TYPE (GdlLineRenderer, gdl_line_renderer, GDL, LINE_RENDERER, GtkSourceGutterRendererText)

struct _GdlLineRenderer {
  GtkSourceGutterRendererText parent_instance;
  GdlDiff *diff;      /* borrowed from the view */
  gboolean new_side;
};

G_DEFINE_FINAL_TYPE (GdlLineRenderer, gdl_line_renderer, GTK_SOURCE_TYPE_GUTTER_RENDERER_TEXT)

static GdlDiffRow *
row_at (GdlLineRenderer *self, guint line)
{
  if (!self->diff || line >= self->diff->rows->len)
    return NULL;
  return g_ptr_array_index (self->diff->rows, line);
}

static void
line_renderer_query_data (GtkSourceGutterRenderer *r, GtkSourceGutterLines *lines, guint line)
{
  GdlLineRenderer *self = GDL_LINE_RENDERER (r);
  GdlDiffRow *row = row_at (self, line);
  int n = row ? (self->new_side ? row->new_no : row->old_no) : 0;
  char buf[16] = "";
  if (n > 0)
    g_snprintf (buf, sizeof buf, "%d", n);
  gtk_source_gutter_renderer_text_set_text (GTK_SOURCE_GUTTER_RENDERER_TEXT (r), buf, -1);
}

static void
line_renderer_snapshot_line (GtkSourceGutterRenderer *r, GtkSnapshot *snapshot, GtkSourceGutterLines *lines, guint line)
{
  GdlLineRenderer *self = GDL_LINE_RENDERER (r);
  GdlDiffRow *row = row_at (self, line);
  if (row && (row->kind == GDL_ROW_ADD || row->kind == GDL_ROW_DEL || row->kind == GDL_ROW_HUNK)) {
    double y = 0, h = 0;
    gtk_source_gutter_lines_get_line_extent (lines, line, GTK_SOURCE_GUTTER_RENDERER_ALIGNMENT_MODE_CELL, &y, &h);
    GdkRGBA bg;
    if (row->kind == GDL_ROW_ADD)
      gdk_rgba_parse (&bg, "rgba(46,160,67,0.28)");
    else if (row->kind == GDL_ROW_DEL)
      gdk_rgba_parse (&bg, "rgba(248,81,73,0.26)");
    else
      gdk_rgba_parse (&bg, "rgba(56,139,253,0.14)");
    gtk_snapshot_append_color (snapshot, &bg, &GRAPHENE_RECT_INIT (0, y, gtk_widget_get_width (GTK_WIDGET (r)), h));
  }
  GTK_SOURCE_GUTTER_RENDERER_CLASS (gdl_line_renderer_parent_class)->snapshot_line (r, snapshot, lines, line);
}

static void
gdl_line_renderer_class_init (GdlLineRendererClass *klass)
{
  GTK_SOURCE_GUTTER_RENDERER_CLASS (klass)->query_data = line_renderer_query_data;
  GTK_SOURCE_GUTTER_RENDERER_CLASS (klass)->snapshot_line = line_renderer_snapshot_line;
}

static void
gdl_line_renderer_init (GdlLineRenderer *self)
{
  gtk_source_gutter_renderer_set_xpad (GTK_SOURCE_GUTTER_RENDERER (self), 8);
  gtk_source_gutter_renderer_set_alignment_mode (GTK_SOURCE_GUTTER_RENDERER (self),
                                                 GTK_SOURCE_GUTTER_RENDERER_ALIGNMENT_MODE_CELL);
  gtk_widget_add_css_class (GTK_WIDGET (self), "dim-label");
}

/* ------------------------------------------------------------------ */
/* Badges & cards                                                      */
/* ------------------------------------------------------------------ */

const char *
gdl_status_label (char status)
{
  switch (status) {
  case GDL_ST_NEW:        return "New";
  case GDL_ST_ADDED:      return "Added";
  case GDL_ST_DELETED:    return "Deleted";
  case GDL_ST_RENAMED:    return "Renamed";
  case GDL_ST_COPIED:     return "Copied";
  case GDL_ST_CONFLICTED: return "Conflicted";
  default:                return "Modified";
  }
}

GtkWidget *
gdl_status_badge_new (char status)
{
  const char *cls, *letter;
  switch (status) {
  case GDL_ST_NEW:        cls = "added";      letter = "U"; break;
  case GDL_ST_ADDED:
  case GDL_ST_COPIED:     cls = "added";      letter = "A"; break;
  case GDL_ST_DELETED:    cls = "deleted";    letter = "D"; break;
  case GDL_ST_RENAMED:    cls = "renamed";    letter = "R"; break;
  case GDL_ST_CONFLICTED: cls = "conflicted"; letter = "!"; break;
  default:                cls = "modified";   letter = "M"; break;
  }
  GtkWidget *label = gtk_label_new (letter);
  gtk_widget_add_css_class (label, "badge");
  gtk_widget_add_css_class (label, cls);
  gtk_widget_set_valign (label, GTK_ALIGN_CENTER);
  gtk_widget_set_tooltip_text (label, gdl_status_label (status));
  return label;
}

GtkWidget *
gdl_action_card_new (const char *icon, const char *label, const char *hint, const char *action_name)
{
  GtkWidget *button = gtk_button_new ();
  gtk_widget_add_css_class (button, "card");
  gtk_widget_add_css_class (button, "action-card");
  gtk_widget_set_halign (button, GTK_ALIGN_CENTER);
  gtk_actionable_set_action_name (GTK_ACTIONABLE (button), action_name);
  GtkWidget *box = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 12);
  GtkWidget *ic = gdl_icon_new (icon, 18);
  gtk_widget_add_css_class (ic, "accent");
  gtk_box_append (GTK_BOX (box), ic);
  GtkWidget *l = gtk_label_new (label);
  gtk_label_set_xalign (GTK_LABEL (l), 0);
  gtk_widget_add_css_class (l, "heading");
  gtk_widget_set_hexpand (l, TRUE);
  gtk_box_append (GTK_BOX (box), l);
  if (hint) {
    GtkWidget *h = gtk_label_new (hint);
    gtk_widget_add_css_class (h, "hint");
    gtk_box_append (GTK_BOX (box), h);
  }
  gtk_button_set_child (GTK_BUTTON (button), box);
  return button;
}

/* ------------------------------------------------------------------ */
/* View                                                                */
/* ------------------------------------------------------------------ */

struct _GdlDiffView {
  GtkBox           parent_instance;
  GtkWidget       *header;
  GtkWidget       *badge_slot;
  GtkWidget       *path_label;
  GtkWidget       *editor_button;
  GtkWidget       *stack;
  GtkSourceView   *view;
  GtkSourceBuffer *buffer;
  AdwStatusPage   *status;
  GdlLineRenderer *old_col, *new_col;
  GdlDiff         *diff;
  char            *path;
  gboolean         show_header;
  GtkTextTag      *tag_add, *tag_del, *tag_hunk, *tag_meta;
};

G_DEFINE_FINAL_TYPE (GdlDiffView, gdl_diff_view, GTK_TYPE_BOX)

enum { SIGNAL_OPEN, N_SIGNALS };
static guint signals[N_SIGNALS];

static void
update_scheme (GdlDiffView *self)
{
  gboolean dark = adw_style_manager_get_dark (adw_style_manager_get_default ());
  GtkSourceStyleScheme *scheme = gtk_source_style_scheme_manager_get_scheme (
    gtk_source_style_scheme_manager_get_default (), dark ? "Adwaita-dark" : "Adwaita");
  gtk_source_buffer_set_style_scheme (self->buffer, scheme);
}

static void
on_open_clicked (GdlDiffView *self)
{
  if (self->path)
    g_signal_emit (self, signals[SIGNAL_OPEN], 0, self->path);
}

static void
gdl_diff_view_dispose (GObject *obj)
{
  GdlDiffView *self = GDL_DIFF_VIEW (obj);
  if (self->old_col) self->old_col->diff = NULL;
  if (self->new_col) self->new_col->diff = NULL;
  g_clear_pointer (&self->diff, gdl_diff_free);
  g_clear_pointer (&self->path, g_free);
  G_OBJECT_CLASS (gdl_diff_view_parent_class)->dispose (obj);
}

static void
gdl_diff_view_class_init (GdlDiffViewClass *klass)
{
  G_OBJECT_CLASS (klass)->dispose = gdl_diff_view_dispose;
  signals[SIGNAL_OPEN] = g_signal_new ("open-in-editor", G_TYPE_FROM_CLASS (klass), G_SIGNAL_RUN_LAST,
                                       0, NULL, NULL, NULL, G_TYPE_NONE, 1, G_TYPE_STRING);
}

static void
gdl_diff_view_init (GdlDiffView *self)
{
  gtk_orientable_set_orientation (GTK_ORIENTABLE (self), GTK_ORIENTATION_VERTICAL);

  /* header */
  self->header = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 10);
  gtk_widget_add_css_class (self->header, "pane-header");
  self->badge_slot = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 0);
  gtk_box_append (GTK_BOX (self->header), self->badge_slot);
  self->path_label = gtk_label_new (NULL);
  gtk_label_set_xalign (GTK_LABEL (self->path_label), 0);
  gtk_label_set_ellipsize (GTK_LABEL (self->path_label), PANGO_ELLIPSIZE_START);
  gtk_label_set_selectable (GTK_LABEL (self->path_label), TRUE);
  gtk_widget_set_hexpand (self->path_label, TRUE);
  gtk_box_append (GTK_BOX (self->header), self->path_label);
  self->editor_button = gtk_button_new ();
  GtkWidget *eb = gtk_box_new (GTK_ORIENTATION_HORIZONTAL, 6);
  gtk_box_append (GTK_BOX (eb), gdl_icon_new ("code", 16));
  gtk_box_append (GTK_BOX (eb), gtk_label_new ("Open in editor"));
  gtk_button_set_child (GTK_BUTTON (self->editor_button), eb);
  g_signal_connect_swapped (self->editor_button, "clicked", G_CALLBACK (on_open_clicked), self);
  gtk_box_append (GTK_BOX (self->header), self->editor_button);
  gtk_widget_set_visible (self->header, FALSE);
  gtk_box_append (GTK_BOX (self), self->header);

  /* source view with two number columns */
  self->buffer = gtk_source_buffer_new (NULL);
  gtk_source_buffer_set_highlight_syntax (self->buffer, FALSE);
  self->view = GTK_SOURCE_VIEW (gtk_source_view_new_with_buffer (self->buffer));
  gtk_text_view_set_editable (GTK_TEXT_VIEW (self->view), FALSE);
  gtk_text_view_set_cursor_visible (GTK_TEXT_VIEW (self->view), FALSE);
  gtk_text_view_set_monospace (GTK_TEXT_VIEW (self->view), TRUE);
  gtk_text_view_set_left_margin (GTK_TEXT_VIEW (self->view), 8);
  gtk_text_view_set_top_margin (GTK_TEXT_VIEW (self->view), 4);
  gtk_text_view_set_bottom_margin (GTK_TEXT_VIEW (self->view), 12);
  gtk_widget_add_css_class (GTK_WIDGET (self->view), "diff-view");
  GtkSourceGutter *gutter = gtk_source_view_get_gutter (self->view, GTK_TEXT_WINDOW_LEFT);
  self->old_col = g_object_new (GDL_TYPE_LINE_RENDERER, NULL);
  self->new_col = g_object_new (GDL_TYPE_LINE_RENDERER, NULL);
  self->new_col->new_side = TRUE;
  gtk_source_gutter_insert (gutter, GTK_SOURCE_GUTTER_RENDERER (self->old_col), 0);
  gtk_source_gutter_insert (gutter, GTK_SOURCE_GUTTER_RENDERER (self->new_col), 1);

  GtkTextBuffer *tb = GTK_TEXT_BUFFER (self->buffer);
  self->tag_add = gtk_text_buffer_create_tag (tb, "add", "paragraph-background", "rgba(46,160,67,0.16)", NULL);
  self->tag_del = gtk_text_buffer_create_tag (tb, "del", "paragraph-background", "rgba(248,81,73,0.15)", NULL);
  self->tag_hunk = gtk_text_buffer_create_tag (tb, "hunk", "paragraph-background", "rgba(56,139,253,0.10)",
                                              "foreground", "#8b949e", NULL);
  self->tag_meta = gtk_text_buffer_create_tag (tb, "meta", "foreground", "#8b949e", "style", PANGO_STYLE_ITALIC, NULL);

  GtkWidget *scroll = gtk_scrolled_window_new ();
  gtk_scrolled_window_set_child (GTK_SCROLLED_WINDOW (scroll), GTK_WIDGET (self->view));
  gtk_widget_set_vexpand (scroll, TRUE);

  self->status = ADW_STATUS_PAGE (adw_status_page_new ());
  gtk_widget_set_vexpand (GTK_WIDGET (self->status), TRUE);
  gtk_widget_add_css_class (GTK_WIDGET (self->status), "compact");

  self->stack = gtk_stack_new ();
  gtk_stack_add_named (GTK_STACK (self->stack), scroll, "diff");
  gtk_stack_add_named (GTK_STACK (self->stack), GTK_WIDGET (self->status), "message");
  gtk_box_append (GTK_BOX (self), self->stack);

  update_scheme (self);
  g_signal_connect_object (adw_style_manager_get_default (), "notify::dark", G_CALLBACK (update_scheme),
                           self, G_CONNECT_SWAPPED);
}

GtkWidget *
gdl_diff_view_new (gboolean show_header)
{
  GdlDiffView *self = g_object_new (GDL_TYPE_DIFF_VIEW, NULL);
  self->show_header = show_header;
  gdl_diff_view_show_message (self, "changes", "No file selected", NULL, NULL);
  return GTK_WIDGET (self);
}

const char *
gdl_diff_view_get_path (GdlDiffView *self)
{
  return self->path;
}

/* Our line-icon names → symbolic theme icons for the big status-page icon */
static const char *
status_icon (const char *icon)
{
  static const struct { const char *ours, *theme; } map[] = {
    { "check", "object-select-symbolic" },        { "changes", "document-edit-symbolic" },
    { "history", "document-open-recent-symbolic" }, { "box", "package-x-generic-symbolic" },
    { "commit", "media-record-symbolic" },        { "sparkle", "starred-symbolic" },
    { "repo", "folder-symbolic" },                { "alert", "dialog-warning-symbolic" },
  };
  for (guint i = 0; icon && i < G_N_ELEMENTS (map); i++)
    if (g_str_equal (map[i].ours, icon))
      return map[i].theme;
  return icon;
}

void
gdl_diff_view_show_message (GdlDiffView *self, const char *icon, const char *title,
                            const char *description, GtkWidget *actions)
{
  g_clear_pointer (&self->path, g_free);
  gtk_widget_set_visible (self->header, FALSE);
  adw_status_page_set_icon_name (self->status, status_icon (icon));
  adw_status_page_set_title (self->status, title ? title : "");
  adw_status_page_set_description (self->status, description);
  adw_status_page_set_child (self->status, actions);
  gtk_stack_set_visible_child_name (GTK_STACK (self->stack), "message");
}

static void
show_inline (GdlDiffView *self, const char *icon, const char *title)
{
  adw_status_page_set_icon_name (self->status, status_icon (icon));
  adw_status_page_set_title (self->status, title);
  adw_status_page_set_description (self->status, NULL);
  adw_status_page_set_child (self->status, NULL);
  gtk_stack_set_visible_child_name (GTK_STACK (self->stack), "message");
}

void
gdl_diff_view_set_diff (GdlDiffView *self, const char *path, const char *diff_text, char status, gboolean can_open)
{
  g_free (self->path);
  self->path = g_strdup (path);

  /* header: badge · folder/ (dim) name (bold) */
  GtkWidget *old_badge = gtk_widget_get_first_child (self->badge_slot);
  if (old_badge)
    gtk_box_remove (GTK_BOX (self->badge_slot), old_badge);
  gtk_box_append (GTK_BOX (self->badge_slot), gdl_status_badge_new (status));
  g_autofree char *dir = g_path_get_dirname (path);
  g_autofree char *base = g_path_get_basename (path);
  g_autofree char *edir = gdl_escape (dir);
  g_autofree char *ebase = gdl_escape (base);
  g_autofree char *markup = g_str_equal (dir, ".") ? g_strdup_printf ("<b>%s</b>", ebase)
                                                   : g_strdup_printf ("<span alpha=\"60%%\">%s/</span><b>%s</b>", edir, ebase);
  gtk_label_set_markup (GTK_LABEL (self->path_label), markup);
  gtk_widget_set_visible (self->editor_button, can_open);
  gtk_widget_set_visible (self->header, self->show_header);

  GdlDiff *diff = gdl_diff_parse (diff_text, MAX_ROWS);
  self->old_col->diff = self->new_col->diff = NULL;
  g_clear_pointer (&self->diff, gdl_diff_free);
  self->diff = diff;

  if (diff->binary) {
    show_inline (self, "box", "This binary file has changed");
    return;
  }
  if (diff->rows->len == 0) {
    show_inline (self, "changes", status == GDL_ST_NEW || status == GDL_ST_ADDED ? "The file is empty"
                                                                                 : "No content changes");
    return;
  }

  /* text: one buffer line per row */
  g_autoptr (GString) text = g_string_new (NULL);
  for (guint i = 0; i < diff->rows->len; i++) {
    GdlDiffRow *row = g_ptr_array_index (diff->rows, i);
    if (i)
      g_string_append_c (text, '\n');
    g_string_append (text, row->text);
  }
  GtkTextBuffer *tb = GTK_TEXT_BUFFER (self->buffer);
  gtk_text_buffer_set_text (tb, text->str, (int) text->len);
  for (guint i = 0; i < diff->rows->len; i++) {
    GdlDiffRow *row = g_ptr_array_index (diff->rows, i);
    GtkTextTag *tag = row->kind == GDL_ROW_ADD ? self->tag_add : row->kind == GDL_ROW_DEL ? self->tag_del
                    : row->kind == GDL_ROW_HUNK ? self->tag_hunk : row->kind == GDL_ROW_META ? self->tag_meta : NULL;
    if (!tag)
      continue;
    GtkTextIter start, end;
    gtk_text_buffer_get_iter_at_line (tb, &start, (int) i);
    end = start;
    gtk_text_iter_forward_line (&end);
    gtk_text_buffer_apply_tag (tb, tag, &start, &end);
  }

  /* number columns sized for the widest line number */
  self->old_col->diff = self->new_col->diff = diff;
  g_autofree char *widest = g_strdup_printf ("%d", diff->max_line);
  g_autofree char *sample = g_strnfill (MAX (3, strlen (widest)), '9');
  int w = 0, h = 0;
  gtk_source_gutter_renderer_text_measure (GTK_SOURCE_GUTTER_RENDERER_TEXT (self->old_col), sample, &w, &h);
  gtk_widget_set_size_request (GTK_WIDGET (self->old_col), w + 16, -1);
  gtk_widget_set_size_request (GTK_WIDGET (self->new_col), w + 16, -1);
  gtk_widget_queue_draw (GTK_WIDGET (self->view));

  GtkTextIter start;
  gtk_text_buffer_get_start_iter (tb, &start);
  gtk_text_buffer_place_cursor (tb, &start);
  gtk_adjustment_set_value (gtk_scrollable_get_vadjustment (GTK_SCROLLABLE (self->view)), 0);
  gtk_stack_set_visible_child_name (GTK_STACK (self->stack), "diff");
}
