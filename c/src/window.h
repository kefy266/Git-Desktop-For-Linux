/* Main window, modeled on GitHub Desktop (https://github.com/desktop/desktop). */
#pragma once

#include <adwaita.h>

#include "git.h"
#include "github.h"

G_BEGIN_DECLS

#define GDL_TYPE_WINDOW (gdl_window_get_type ())
G_DECLARE_FINAL_TYPE (GdlWindow, gdl_window, GDL, WINDOW, AdwApplicationWindow)

GdlWindow  *gdl_window_new             (AdwApplication *app, const char *repo_path);

/* Shared with dialogs.c */
GdlRepo    *gdl_window_get_repo        (GdlWindow *self);       /* NULL when no repository is open */
GdlAccount *gdl_window_get_account     (GdlWindow *self);       /* NULL while loading */
const char *gdl_window_get_token       (GdlWindow *self);
void        gdl_window_open_repository (GdlWindow *self, const char *path);
void        gdl_window_refresh         (GdlWindow *self, gboolean force);
void        gdl_window_reload_account  (GdlWindow *self);
void        gdl_window_toast           (GdlWindow *self, const char *message);
void        gdl_window_error           (GdlWindow *self, const char *title, const char *message);
void        gdl_window_apply_theme     (void);

/* Saves a PNG of the window after it has been shown (development aid: --screenshot) */
void        gdl_window_screenshot      (GdlWindow *self, const char *png_path, const char *view);

G_END_DECLS
