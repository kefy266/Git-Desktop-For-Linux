/* Diff pane: header (status badge, path, "Open in editor") over a read-only
 * GtkSourceView with old/new line-number columns, or an empty state. */
#pragma once

#include <adwaita.h>

G_BEGIN_DECLS

#define GDL_TYPE_DIFF_VIEW (gdl_diff_view_get_type ())
G_DECLARE_FINAL_TYPE (GdlDiffView, gdl_diff_view, GDL, DIFF_VIEW, GtkBox)

GtkWidget *gdl_diff_view_new          (gboolean show_header);
/* status: one of the GDL_ST_* letters */
void       gdl_diff_view_set_diff     (GdlDiffView *self, const char *path, const char *diff_text,
                                       char status, gboolean can_open);
/* Big empty state; `actions` is an optional box of action cards */
void       gdl_diff_view_show_message (GdlDiffView *self, const char *icon, const char *title,
                                       const char *description, GtkWidget *actions);
const char *gdl_diff_view_get_path    (GdlDiffView *self);

/* "open-in-editor" (char *path) */

/* Rounded action card for empty states: icon · label · dim shortcut hint */
GtkWidget *gdl_action_card_new (const char *icon, const char *label, const char *hint,
                                const char *action_name);

/* "modified"/"added"/… badge label for a status letter */
GtkWidget  *gdl_status_badge_new   (char status);
const char *gdl_status_label       (char status);

G_END_DECLS
