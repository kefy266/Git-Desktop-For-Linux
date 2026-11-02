/* Secondary windows: clone, create, branch name, merge, preferences, sign in. */
#pragma once

#include "window.h"

G_BEGIN_DECLS

void gdl_clone_dialog_show       (GdlWindow *win, const char *preselect_full_name);
void gdl_create_dialog_show      (GdlWindow *win);
void gdl_add_existing_show       (GdlWindow *win);
void gdl_merge_dialog_show       (GdlWindow *win);
void gdl_preferences_show        (GdlWindow *win);
void gdl_sign_in_dialog_show     (GdlWindow *win);

/* New branch (old_name == NULL) or rename. Validates as you type. */
void gdl_branch_name_dialog_show (GdlWindow *win, const char *old_name);

G_END_DECLS
