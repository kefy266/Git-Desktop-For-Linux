/* Line icons drawn with GskPath strokes in the widget's CSS color,
 * so they follow light/dark themes and stay crisp at any scale. */
#pragma once

#include <gtk/gtk.h>

G_BEGIN_DECLS

#define GDL_TYPE_ICON (gdl_icon_get_type ())
G_DECLARE_FINAL_TYPE (GdlIcon, gdl_icon, GDL, ICON, GtkWidget)

GtkWidget *gdl_icon_new      (const char *name, int size);
void       gdl_icon_set_name (GdlIcon *self, const char *name);

G_END_DECLS
