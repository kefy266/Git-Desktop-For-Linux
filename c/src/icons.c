#include "icons.h"

/* 24×24 outline drawings, 2px round strokes */
static const struct { const char *name; const char *path; } ICONS[] = {
  { "repo",         "M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5ZM5 19.5A1.5 1.5 0 0 0 6.5 21H19M9 7h6" },
  { "branch",       "M3.5 5A2.5 2.5 0 1 0 8.5 5A2.5 2.5 0 1 0 3.5 5ZM3.5 19A2.5 2.5 0 1 0 8.5 19A2.5 2.5 0 1 0 3.5 19Z"
                    "M15.5 7A2.5 2.5 0 1 0 20.5 7A2.5 2.5 0 1 0 15.5 7ZM6 7.5V16.5M18 9.5C18 14.5 12 13.5 6.8 17.1" },
  { "sync",         "M20 11A8 8 0 0 0 5.4 6.5L4 8M4 3V8H9M4 13A8 8 0 0 0 18.6 17.5L20 16M20 21V16H15" },
  { "arrow-up",     "M12 19V5M6 11L12 5L18 11" },
  { "arrow-down",   "M12 5V19M6 13L12 19L18 13" },
  { "upload",       "M12 15V3M7 8L12 3L17 8M4 15V19A2 2 0 0 0 6 21H18A2 2 0 0 0 20 19V15" },
  { "chevron-down", "M6 9L12 15L18 9" },
  { "check",        "M5 12.5L9.5 17L19 7.5" },
  { "plus",         "M12 5V19M5 12H19" },
  { "search",       "M4 11A7 7 0 1 0 18 11A7 7 0 1 0 4 11ZM20 20L16.5 16.5" },
  { "copy",         "M11 9H19A2 2 0 0 1 21 11V19A2 2 0 0 1 19 21H11A2 2 0 0 1 9 19V11A2 2 0 0 1 11 9Z"
                    "M5 15V5A2 2 0 0 1 7 3H17" },
  { "folder",       "M3 7A2 2 0 0 1 5 5H9L11 7H19A2 2 0 0 1 21 9V18A2 2 0 0 1 19 20H5A2 2 0 0 1 3 18Z" },
  { "code",         "M8 7L3 12L8 17M16 7L21 12L16 17M14 4L10 20" },
  { "terminal",     "M5 4H19A2 2 0 0 1 21 6V18A2 2 0 0 1 19 20H5A2 2 0 0 1 3 18V6A2 2 0 0 1 5 4ZM7 9L10 12L7 15M13 15H17" },
  { "commit",       "M8.5 12A3.5 3.5 0 1 0 15.5 12A3.5 3.5 0 1 0 8.5 12ZM3 12H8.5M15.5 12H21" },
  { "history",      "M3 12A9 9 0 1 0 6 5.3L3 8M3 3V8H8M12 7V12L15 14" },
  { "changes",      "M14 3H7A2 2 0 0 0 5 5V19A2 2 0 0 0 7 21H17A2 2 0 0 0 19 19V8ZM14 3V8H19M12 11V17M9 14H15" },
  { "settings",     "M4 6H13M17 6H20M4 12H7M11 12H20M4 18H15M19 18H20"
                    "M13 6A2 2 0 1 0 17 6A2 2 0 1 0 13 6ZM7 12A2 2 0 1 0 11 12A2 2 0 1 0 7 12Z"
                    "M15 18A2 2 0 1 0 19 18A2 2 0 1 0 15 18Z" },
  { "undo",         "M9 14L4 9L9 4M4 9H14.5A5.5 5.5 0 0 1 14.5 20H11" },
  { "box",          "M21 8L12 3L3 8L12 13ZM3 8V16L12 21L21 16V8M12 13V21" },
  { "alert",        "M12 3L22 21H2ZM12 10V14M12 17.5V18" },
  { "cloud-down",   "M7 18A5 5 0 0 1 6.4 8A6 6 0 0 1 18 9A4 4 0 0 1 18 17M12 12V21M8.5 17.5L12 21L15.5 17.5" },
  { "user",         "M8 8A4 4 0 1 0 16 8A4 4 0 1 0 8 8ZM4 21A8 8 0 0 1 20 21" },
  { "logout",       "M15 4H18A2 2 0 0 1 20 6V18A2 2 0 0 1 18 20H15M10 17L5 12L10 7M5 12H16" },
  { "external",     "M14 4H20V10M20 4L11 13M18 14V18A2 2 0 0 1 16 20H6A2 2 0 0 1 4 18V8A2 2 0 0 1 6 6H10" },
  { "sparkle",      "M12 3V7M12 17V21M3 12H7M17 12H21M6 6L8.5 8.5M15.5 15.5L18 18M6 18L8.5 15.5M15.5 8.5L18 6" },
  { "menu",         "M4 6H20M4 12H20M4 18H20" },
  { "trash",        "M4 7H20M9 7V4H15V7M6 7L7 20H17L18 7M10 11V16M14 11V16" },
  { "lock",         "M6 11H18V21H6ZM8 11V7A4 4 0 0 1 16 7V11" },
};

struct _GdlIcon {
  GtkWidget parent_instance;
  GskPath  *path;
  int       size;
};

G_DEFINE_FINAL_TYPE (GdlIcon, gdl_icon, GTK_TYPE_WIDGET)

static void
gdl_icon_measure (GtkWidget *widget, GtkOrientation o, int for_size, int *min, int *nat, int *mb, int *nb)
{
  *min = *nat = GDL_ICON (widget)->size;
}

static void
gdl_icon_snapshot (GtkWidget *widget, GtkSnapshot *snapshot)
{
  GdlIcon *self = GDL_ICON (widget);
  if (!self->path)
    return;
  GdkRGBA color;
  gtk_widget_get_color (widget, &color);
  float w = gtk_widget_get_width (widget), h = gtk_widget_get_height (widget);
  float scale = MIN (w, h) / 24.0f;
  g_autoptr (GskStroke) stroke = gsk_stroke_new (2.0f);
  gsk_stroke_set_line_cap (stroke, GSK_LINE_CAP_ROUND);
  gsk_stroke_set_line_join (stroke, GSK_LINE_JOIN_ROUND);
  gtk_snapshot_save (snapshot);
  gtk_snapshot_translate (snapshot, &GRAPHENE_POINT_INIT ((w - 24 * scale) / 2, (h - 24 * scale) / 2));
  gtk_snapshot_scale (snapshot, scale, scale);
  gtk_snapshot_append_stroke (snapshot, self->path, stroke, &color);
  gtk_snapshot_restore (snapshot);
}

static void
gdl_icon_finalize (GObject *obj)
{
  g_clear_pointer (&GDL_ICON (obj)->path, gsk_path_unref);
  G_OBJECT_CLASS (gdl_icon_parent_class)->finalize (obj);
}

static void
gdl_icon_class_init (GdlIconClass *klass)
{
  GTK_WIDGET_CLASS (klass)->measure = gdl_icon_measure;
  GTK_WIDGET_CLASS (klass)->snapshot = gdl_icon_snapshot;
  G_OBJECT_CLASS (klass)->finalize = gdl_icon_finalize;
  gtk_widget_class_set_css_name (GTK_WIDGET_CLASS (klass), "gdl-icon");
}

static void
gdl_icon_init (GdlIcon *self)
{
  self->size = 16;
}

void
gdl_icon_set_name (GdlIcon *self, const char *name)
{
  g_clear_pointer (&self->path, gsk_path_unref);
  for (guint i = 0; i < G_N_ELEMENTS (ICONS); i++)
    if (g_str_equal (ICONS[i].name, name)) {
      self->path = gsk_path_parse (ICONS[i].path);
      break;
    }
  if (!self->path)
    g_warning ("Unknown icon '%s'", name);
  gtk_widget_queue_draw (GTK_WIDGET (self));
}

GtkWidget *
gdl_icon_new (const char *name, int size)
{
  GdlIcon *self = g_object_new (GDL_TYPE_ICON, NULL);
  self->size = size;
  gdl_icon_set_name (self, name);
  gtk_widget_set_valign (GTK_WIDGET (self), GTK_ALIGN_CENTER);
  return GTK_WIDGET (self);
}
